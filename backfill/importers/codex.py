#!/usr/bin/env python3
from __future__ import annotations

import argparse
import collections
import json
import uuid
from pathlib import Path
from typing import Any

from backfill.importers.common import (
    make_record,
    nonnegative_int,
    opaque_id,
    sha256_file,
    summarize_records,
    timestamp_before,
    utc_timestamp,
    write_outputs,
)


PARSER_NAME = "codex-rollout-cumulative"
PARSER_VERSION = "0.1.0"
FIELDS = (
    "input_tokens",
    "output_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)


def _jsonl_files(root: Path):
    for folder in ("sessions", "archived_sessions"):
        base = root / folder
        if base.is_dir():
            for path in sorted(base.rglob("*.jsonl")):
                if path.is_file():
                    yield path, path.relative_to(root)


def _usage(value: Any) -> dict[str, int | None] | None:
    if not isinstance(value, dict):
        return None
    result = {field: nonnegative_int(value.get(field)) for field in FIELDS}
    if any(result[field] is None for field in ("input_tokens", "output_tokens", "total_tokens")):
        return None
    return result


def _decreased(current: dict[str, int | None], previous: dict[str, int | None]) -> bool:
    return any(
        current[field] is not None
        and previous[field] is not None
        and current[field] < previous[field]
        for field in FIELDS
    )


def _delta(
    current: dict[str, int | None],
    previous: dict[str, int | None] | None,
    reset: bool,
) -> tuple[dict[str, int | None], bool]:
    partial = False
    result: dict[str, int | None] = {}
    for field in FIELDS:
        value = current[field]
        before = previous[field] if previous else None
        if value is None:
            result[field] = None
            partial = True
        elif previous is None or reset:
            result[field] = value
        elif before is None:
            result[field] = None
            partial = True
        else:
            result[field] = value - before
    return result, partial


def normalize(
    root: Path,
    snapshot_manifest: Path,
    *,
    cutover: str | None = None,
    import_run_id: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    snapshot_hash = sha256_file(snapshot_manifest)
    run_id = import_run_id or str(uuid.uuid4())
    records: list[dict[str, Any]] = []
    counts: collections.Counter[str] = collections.Counter()
    file_count = 0

    for path, relative in _jsonl_files(root):
        file_count += 1
        path_id = opaque_id(relative.as_posix())
        provider = model = session_id = None
        previous: dict[str, int | None] | None = None
        segment = 0
        token_ordinal = 0
        before_cutover = after_cutover = False
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for raw in handle:
                try:
                    item = json.loads(raw)
                except (TypeError, ValueError):
                    counts["invalid_json_lines"] += 1
                    continue
                if not isinstance(item, dict):
                    continue
                payload = item.get("payload")
                if not isinstance(payload, dict):
                    continue
                if item.get("type") == "session_meta":
                    session_id = payload.get("id") or payload.get("session_id")
                    provider = payload.get("model_provider")
                    continue
                if item.get("type") == "turn_context":
                    model = payload.get("model") or model
                    continue
                if item.get("type") != "event_msg" or payload.get("type") != "token_count":
                    continue
                token_ordinal += 1
                info = payload.get("info")
                current = _usage(info.get("total_token_usage") if isinstance(info, dict) else None)
                if current is None:
                    counts["token_events_without_usable_cumulative"] += 1
                    continue
                event_time = utc_timestamp(item.get("timestamp"))
                is_before = timestamp_before(event_time, cutover)
                before_cutover = before_cutover or is_before
                after_cutover = after_cutover or not is_before
                reset = previous is not None and _decreased(current, previous)
                if reset:
                    segment += 1
                    counts["cumulative_resets"] += 1
                delta, partial = _delta(current, previous, reset)
                previous = current
                if all((delta[field] or 0) == 0 for field in ("input_tokens", "output_tokens", "total_tokens")):
                    counts["zero_delta_events"] += 1
                    continue
                if not is_before:
                    counts["live_period_events"] += 1
                    continue
                if model is None or provider is None:
                    partial = True
                quality = "partial" if partial else "derived"
                reason = "missing_dimension" if partial else ("cumulative_reset" if reset else "cumulative_delta")
                values = {
                    "occurred_at": event_time,
                    "period_start": None,
                    "period_end": None,
                    "record_granularity": "api_call",
                    "user_id": None,
                    "request_model": str(model) if model else None,
                    "response_model": str(model) if model else None,
                    "provider": str(provider) if provider else None,
                    "input_tokens": delta["input_tokens"],
                    "output_tokens": delta["output_tokens"],
                    "cached_input_tokens": delta["cached_input_tokens"],
                    "cache_write_tokens": delta["cache_write_input_tokens"],
                    "reasoning_tokens": delta["reasoning_output_tokens"],
                    "total_tokens": delta["total_tokens"],
                    "estimated_cost_usd": None,
                    "actual_cost_usd": None,
                    "cost_quality": "unknown",
                    "pricing_version": None,
                    "quality": quality,
                    "quality_reason": reason,
                    "shared_eligible": False,
                }
                records.append(make_record(
                    source_system="codex",
                    source_instance="main-windows",
                    native_key=(path_id, session_id, segment, token_ordinal),
                    snapshot_hash=snapshot_hash,
                    parser_name=PARSER_NAME,
                    parser_version=PARSER_VERSION,
                    import_run_id=run_id,
                    values=values,
                ))
                counts[f"{quality}_records"] += 1
        if token_ordinal == 0:
            counts["files_without_token_events"] += 1
        if cutover and before_cutover and after_cutover:
            counts["files_split_at_cutover"] += 1

    report = {
        "format": 1,
        "source_system": "codex",
        "source_instance": "main-windows",
        "parser_name": PARSER_NAME,
        "parser_version": PARSER_VERSION,
        "import_run_id": run_id,
        "source_snapshot_hash": snapshot_hash,
        "cutover": cutover,
        "source_files": file_count,
        "normalized_records": len(records),
        "counts": dict(sorted(counts.items())),
        "summary": summarize_records(records),
        "content_fields_persisted": False,
    }
    return records, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-root", type=Path, required=True)
    parser.add_argument("--snapshot-manifest", type=Path, required=True)
    parser.add_argument("--cutover")
    parser.add_argument("--output-manifest", type=Path, required=True)
    parser.add_argument("--output-report", type=Path, required=True)
    args = parser.parse_args()
    records, report = normalize(
        args.snapshot_root, args.snapshot_manifest, cutover=args.cutover
    )
    write_outputs(records, report, args.output_manifest, args.output_report)
    print(json.dumps({
        "source_instance": report["source_instance"],
        "normalized_records": len(records),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
