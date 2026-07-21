#!/usr/bin/env python3
from __future__ import annotations

import argparse
import collections
import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from backfill.importers.common import (
    decimal_string,
    make_record,
    nonnegative_int,
    normalized_total,
    sha256_file,
    summarize_records,
    timestamp_before,
    utc_timestamp,
    write_outputs,
)


PARSER_NAME = "hermes-state"
PARSER_VERSION = "0.2.0"
SUPPORTED_SCHEMA_VERSIONS = {11, 13, 20}
SESSION_COLUMNS = (
    "id",
    "source",
    "user_id",
    "parent_session_id",
    "model",
    "started_at",
    "ended_at",
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "reasoning_tokens",
    "billing_provider",
    "estimated_cost_usd",
    "actual_cost_usd",
    "cost_status",
    "cost_source",
    "pricing_version",
)
MODEL_COLUMNS = (
    "session_id",
    "model",
    "billing_provider",
    "billing_mode",
    "api_call_count",
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "reasoning_tokens",
    "estimated_cost_usd",
    "actual_cost_usd",
    "cost_status",
    "cost_source",
    "first_seen",
    "last_seen",
)


def _rows(connection: sqlite3.Connection, table: str, columns: tuple[str, ...]):
    connection.row_factory = sqlite3.Row
    selected = ",".join('"' + column + '"' for column in columns)
    return connection.execute(f'SELECT {selected} FROM "{table}"').fetchall()


def _discord_user(source: Any, user_id: Any) -> str | None:
    if source != "discord" or user_id is None:
        return None
    candidate = str(user_id)
    if candidate.isascii() and candidate.isdigit():
        return f"discord:{candidate}"
    if candidate.startswith("discord:") and candidate[8:].isascii() and candidate[8:].isdigit():
        return candidate
    return None


def _resolve_discord_users(
    sessions: dict[str, sqlite3.Row],
) -> tuple[dict[str, str | None], dict[str, str]]:
    """Resolve only evidenced Discord lineage; never infer by time or model."""
    resolved: dict[str, str | None] = {}
    provenance: dict[str, str] = {}

    def resolve(session_id: str, trail: set[str]) -> tuple[str | None, str]:
        if session_id in resolved:
            return resolved[session_id], provenance[session_id]
        if session_id in trail:
            return None, "cycle"
        session = sessions.get(session_id)
        if session is None:
            return None, "parent_missing"
        direct = _discord_user(session["source"], session["user_id"])
        if direct is not None:
            resolved[session_id] = direct
            provenance[session_id] = "direct"
            return direct, "direct"
        parent_id = session["parent_session_id"]
        if not parent_id:
            resolved[session_id] = None
            provenance[session_id] = "unknown"
            return None, "unknown"
        parent_user, parent_provenance = resolve(str(parent_id), trail | {session_id})
        if parent_user is not None:
            resolved[session_id] = parent_user
            provenance[session_id] = "inherited"
            return parent_user, "inherited"
        resolved[session_id] = None
        provenance[session_id] = parent_provenance
        return None, parent_provenance

    for session_id in sessions:
        resolve(session_id, set())
    return resolved, provenance


def _user_quality_reason(base: str, provenance: str) -> str:
    return f"{base}_user_inherited" if provenance == "inherited" else base


def _cost(row: sqlite3.Row, shared: bool) -> tuple[str | None, str | None, str]:
    if shared:
        return None, None, "unknown"
    status = str(row["cost_status"] or "unknown")
    if status in {"reported", "actual", "included"}:
        actual = decimal_string(row["actual_cost_usd"])
        return (None, actual, "reported") if actual is not None else (None, None, "unknown")
    return None, None, "unknown"


def _has_nonzero_usage(values: dict[str, Any]) -> bool:
    return any(
        (values[field] or 0) > 0
        for field in (
            "input_tokens",
            "output_tokens",
            "cached_input_tokens",
            "cache_write_tokens",
            "reasoning_tokens",
            "total_tokens",
        )
    )


def _usage_values(
    row: sqlite3.Row,
    *,
    user_id: str | None,
    request_model: Any,
    provider: Any,
    occurred_at: str | None,
    period_start: str | None,
    period_end: str | None,
    quality: str,
    quality_reason: str,
    pricing_version: Any,
    shared: bool,
) -> dict[str, Any]:
    uncached_input_tokens = nonnegative_int(row["input_tokens"])
    output_tokens = nonnegative_int(row["output_tokens"])
    cached_input_tokens = nonnegative_int(row["cache_read_tokens"])
    cache_write_tokens = nonnegative_int(row["cache_write_tokens"])
    input_parts = (
        uncached_input_tokens,
        cached_input_tokens,
        cache_write_tokens,
    )
    input_tokens = sum(input_parts) if all(
        value is not None for value in input_parts
    ) else None
    estimated_cost, actual_cost, cost_quality = _cost(row, shared)
    return {
        "occurred_at": occurred_at,
        "period_start": period_start,
        "period_end": period_end,
        "record_granularity": "session",
        "user_id": user_id,
        "request_model": str(request_model) if request_model else None,
        "response_model": str(request_model) if request_model else None,
        "provider": str(provider) if provider else None,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_input_tokens": cached_input_tokens,
        "cache_write_tokens": cache_write_tokens,
        "reasoning_tokens": nonnegative_int(row["reasoning_tokens"]),
        "total_tokens": normalized_total(input_tokens, output_tokens),
        "estimated_cost_usd": estimated_cost,
        "actual_cost_usd": actual_cost,
        "cost_quality": cost_quality,
        "pricing_version": None,
        "quality": quality,
        "quality_reason": quality_reason,
        "shared_eligible": True,
    }


def normalize(
    snapshot: Path,
    instance: str,
    *,
    cutover: str | None = None,
    shared: bool = False,
    import_run_id: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    snapshot_hash = sha256_file(snapshot)
    run_id = import_run_id or str(uuid.uuid4())
    uri = snapshot.resolve().as_uri() + "?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    try:
        schema_version = connection.execute(
            "SELECT version FROM schema_version"
        ).fetchone()[0]
        if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            raise ValueError(f"unsupported Hermes schema version: {schema_version}")
        sessions = {
            str(row["id"]): row
            for row in _rows(connection, "sessions", SESSION_COLUMNS)
        }
        resolved_users, user_provenance = _resolve_discord_users(sessions)
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        model_rows: dict[str, list[sqlite3.Row]] = collections.defaultdict(list)
        if "session_model_usage" in tables:
            for row in _rows(connection, "session_model_usage", MODEL_COLUMNS):
                model_rows[str(row["session_id"])].append(row)
    finally:
        connection.close()

    records: list[dict[str, Any]] = []
    counts: collections.Counter[str] = collections.Counter()
    for session_id, session in sessions.items():
        started_at = utc_timestamp(session["started_at"])
        ended_at = utc_timestamp(session["ended_at"] or session["started_at"])
        if not timestamp_before(ended_at, cutover):
            if cutover and started_at and timestamp_before(started_at, cutover):
                counts["quarantined_boundary_sessions"] += 1
            else:
                counts["live_period_sessions"] += 1
            continue
        user_id = resolved_users[session_id]
        provenance = user_provenance[session_id]
        if session["source"] == "discord" and session["user_id"] and _discord_user(session["source"], session["user_id"]) is None:
            counts["invalid_discord_user_ids"] += 1
        if provenance == "inherited":
            counts["inherited_discord_user_sessions"] += 1
        elif session["parent_session_id"] and user_id is None:
            counts[f"unresolved_parent_user_{provenance}_sessions"] += 1
        rows = model_rows.get(session_id, [])
        if rows:
            for index, row in enumerate(sorted(rows, key=lambda item: (
                str(item["first_seen"]), str(item["last_seen"]),
                str(item["model"]), str(item["billing_provider"]),
            ))):
                period_start = utc_timestamp(row["first_seen"] or session["started_at"])
                period_end = utc_timestamp(row["last_seen"] or session["ended_at"] or session["started_at"])
                if not timestamp_before(period_end, cutover):
                    if cutover and period_start and timestamp_before(period_start, cutover):
                        counts["quarantined_boundary_model_rows"] += 1
                    else:
                        counts["live_period_model_rows"] += 1
                    continue
                values = _usage_values(
                    row,
                    user_id=user_id,
                    request_model=row["model"],
                    provider=row["billing_provider"],
                    occurred_at=period_end,
                    period_start=period_start,
                    period_end=period_end,
                    quality="exact",
                    quality_reason=_user_quality_reason("per_model_usage", provenance),
                    pricing_version=session["pricing_version"],
                    shared=shared,
                )
                if not _has_nonzero_usage(values):
                    counts["rows_without_nonzero_usage"] += 1
                    continue
                records.append(make_record(
                    source_system="hermes",
                    source_instance=f"hermes-{instance}",
                    native_key=("model", session_id, row["model"], row["billing_provider"], row["first_seen"], row["last_seen"], index),
                    snapshot_hash=snapshot_hash,
                    parser_name=PARSER_NAME,
                    parser_version=PARSER_VERSION,
                    import_run_id=run_id,
                    values=values,
                ))
                counts["exact_records"] += 1
                if provenance == "inherited":
                    counts["inherited_discord_user_records"] += 1
        else:
            quality = "derived" if session["model"] else "partial"
            reason = "session_aggregate_single_model" if session["model"] else "session_aggregate_model_unknown"
            values = _usage_values(
                session,
                user_id=user_id,
                request_model=session["model"],
                provider=session["billing_provider"],
                occurred_at=ended_at,
                period_start=started_at,
                period_end=ended_at,
                quality=quality,
                quality_reason=_user_quality_reason(reason, provenance),
                pricing_version=session["pricing_version"],
                shared=shared,
            )
            if not _has_nonzero_usage(values):
                counts["sessions_without_nonzero_usage"] += 1
                continue
            records.append(make_record(
                source_system="hermes",
                source_instance=f"hermes-{instance}",
                native_key=("session", session_id),
                snapshot_hash=snapshot_hash,
                parser_name=PARSER_NAME,
                parser_version=PARSER_VERSION,
                import_run_id=run_id,
                values=values,
            ))
            counts[f"{quality}_records"] += 1
            if provenance == "inherited":
                counts["inherited_discord_user_records"] += 1

    report = {
        "format": 1,
        "source_system": "hermes",
        "source_instance": f"hermes-{instance}",
        "parser_name": PARSER_NAME,
        "parser_version": PARSER_VERSION,
        "schema_version": schema_version,
        "per_model_usage_present": "session_model_usage" in tables,
        "import_run_id": run_id,
        "source_snapshot_hash": snapshot_hash,
        "cutover": cutover,
        "shared_manifest": shared,
        "source_sessions": len(sessions),
        "normalized_records": len(records),
        "counts": dict(sorted(counts.items())),
        "summary": summarize_records(records),
        "content_fields_persisted": False,
    }
    return records, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--instance", choices=("main", "owashota"), required=True)
    parser.add_argument("--cutover")
    parser.add_argument("--shared", action="store_true")
    parser.add_argument("--import-run-id")
    parser.add_argument("--output-manifest", type=Path, required=True)
    parser.add_argument("--output-report", type=Path, required=True)
    args = parser.parse_args()
    records, report = normalize(
        args.snapshot,
        args.instance,
        cutover=args.cutover,
        shared=args.shared,
        import_run_id=args.import_run_id,
    )
    write_outputs(records, report, args.output_manifest, args.output_report)
    print(json.dumps({
        "source_instance": report["source_instance"],
        "normalized_records": len(records),
        "shared_manifest": args.shared,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
