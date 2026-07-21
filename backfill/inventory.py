#!/usr/bin/env python3
"""Content-safe, read-only inventory for Codex JSONL and Hermes SQLite snapshots."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Iterable


PARSER_VERSION = "0.1.0"
TOKEN_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)
HERMES_TOKEN_COLUMNS = (
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "reasoning_tokens",
)
SAFE_DIMENSION = re.compile(r"^[A-Za-z0-9_.:/ +()-]{1,100}$")


def _counter_dict(counter: collections.Counter[str]) -> dict[str, int]:
    return dict(sorted(counter.items()))


def _safe_dimension(value: Any) -> str:
    if isinstance(value, str) and SAFE_DIMENSION.fullmatch(value) and "@" not in value:
        return value
    return "<redacted-or-non-scalar>"


def _path_id(relative_path: Path) -> str:
    return hashlib.sha256(relative_path.as_posix().encode("utf-8")).hexdigest()


def _update_range(current: list[str | None], value: Any) -> None:
    if not isinstance(value, str) or not value:
        return
    if current[0] is None or value < current[0]:
        current[0] = value
    if current[1] is None or value > current[1]:
        current[1] = value


def _codex_files(root: Path) -> Iterable[tuple[Path, Path]]:
    for folder in ("sessions", "archived_sessions"):
        base = root / folder
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.jsonl")):
            if path.is_file():
                yield path, path.relative_to(root)


def inventory_codex(root: Path) -> dict[str, Any]:
    event_types: collections.Counter[str] = collections.Counter()
    event_msg_kinds: collections.Counter[str] = collections.Counter()
    cli_versions: collections.Counter[str] = collections.Counter()
    originators: collections.Counter[str] = collections.Counter()
    model_providers: collections.Counter[str] = collections.Counter()
    models: collections.Counter[str] = collections.Counter()
    token_value_types: collections.Counter[str] = collections.Counter()
    timestamp_range: list[str | None] = [None, None]
    total_bytes = total_lines = invalid_lines = token_events = 0
    files_with_tokens = 0
    file_records: list[dict[str, Any]] = []

    for path, relative in _codex_files(root):
        stat = path.stat()
        total_bytes += stat.st_size
        file_lines = file_invalid = file_token_events = 0
        file_range: list[str | None] = [None, None]
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for raw in handle:
                total_lines += 1
                file_lines += 1
                try:
                    item = json.loads(raw)
                except (TypeError, ValueError):
                    invalid_lines += 1
                    file_invalid += 1
                    continue
                if not isinstance(item, dict):
                    continue
                _update_range(timestamp_range, item.get("timestamp"))
                _update_range(file_range, item.get("timestamp"))
                item_type = item.get("type")
                if not isinstance(item_type, str):
                    item_type = "<missing>"
                event_types[item_type] += 1
                payload = item.get("payload")
                if not isinstance(payload, dict):
                    continue
                if item_type == "session_meta":
                    cli_versions[_safe_dimension(payload.get("cli_version"))] += 1
                    originators[_safe_dimension(payload.get("originator"))] += 1
                    model_providers[_safe_dimension(payload.get("model_provider"))] += 1
                elif item_type == "turn_context":
                    models[_safe_dimension(payload.get("model"))] += 1
                elif item_type == "event_msg":
                    event_kind = payload.get("type")
                    if not isinstance(event_kind, str):
                        event_kind = "<missing>"
                    event_msg_kinds[event_kind] += 1
                    if event_kind != "token_count":
                        continue
                    token_events += 1
                    file_token_events += 1
                    info = payload.get("info")
                    if not isinstance(info, dict):
                        token_value_types["missing_info"] += 1
                        continue
                    for bucket in ("total_token_usage", "last_token_usage"):
                        usage = info.get(bucket)
                        if not isinstance(usage, dict):
                            token_value_types[f"{bucket}:missing"] += 1
                            continue
                        for field in TOKEN_FIELDS:
                            value = usage.get(field)
                            token_value_types[
                                f"{bucket}.{field}:{type(value).__name__}"
                            ] += 1
        if file_token_events:
            files_with_tokens += 1
        file_records.append(
            {
                "path_id": _path_id(relative),
                "bytes": stat.st_size,
                "lines": file_lines,
                "invalid_json_lines": file_invalid,
                "token_events": file_token_events,
                "timestamp_min": file_range[0],
                "timestamp_max": file_range[1],
            }
        )

    return {
        "inventory_format": 1,
        "parser": {"name": "codex-jsonl-inventory", "version": PARSER_VERSION},
        "source_system": "codex",
        "source_instance": "main-windows",
        "source_root": "<effective-CODEX_HOME>",
        "read_only": True,
        "content_fields_persisted": False,
        "summary": {
            "files": len(file_records),
            "bytes": total_bytes,
            "lines": total_lines,
            "invalid_json_lines": invalid_lines,
            "files_with_token_events": files_with_tokens,
            "token_events": token_events,
            "timestamp_min": timestamp_range[0],
            "timestamp_max": timestamp_range[1],
        },
        "dimensions": {
            "event_types": _counter_dict(event_types),
            "event_msg_kinds": _counter_dict(event_msg_kinds),
            "cli_versions": _counter_dict(cli_versions),
            "originators": _counter_dict(originators),
            "model_providers": _counter_dict(model_providers),
            "models": _counter_dict(models),
            "token_value_types": _counter_dict(token_value_types),
        },
        "files": file_records,
    }


def _quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _table_columns(connection: sqlite3.Connection, table: str) -> list[str]:
    return [
        str(row[1])
        for row in connection.execute(f"PRAGMA table_info({_quote_identifier(table)})")
    ]


def _require_columns(actual: list[str], required: Iterable[str], table: str) -> None:
    missing = sorted(set(required) - set(actual))
    if missing:
        raise ValueError(f"{table} is missing required usage columns: {', '.join(missing)}")


def _aggregate_usage(
    connection: sqlite3.Connection, table: str, token_columns: tuple[str, ...]
) -> dict[str, Any]:
    columns = _table_columns(connection, table)
    _require_columns(columns, token_columns, table)
    selected = [
        "COUNT(*) AS rows",
        *[
            f"SUM(CASE WHEN {_quote_identifier(column)} IS NOT NULL THEN 1 ELSE 0 END) "
            f"AS {_quote_identifier(column + '_present')}"
            for column in token_columns
        ],
        *[
            f"SUM({_quote_identifier(column)}) AS {_quote_identifier(column + '_sum')}"
            for column in token_columns
        ],
    ]
    cursor = connection.execute(
        f"SELECT {', '.join(selected)} FROM {_quote_identifier(table)}"
    )
    names = [description[0] for description in cursor.description]
    row = cursor.fetchone()
    assert row is not None
    return dict(zip(names, row))


def inventory_hermes(snapshot: Path, instance: str) -> dict[str, Any]:
    uri = snapshot.resolve().as_uri() + "?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    try:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        required_tables = {"schema_version", "sessions"}
        missing_tables = sorted(required_tables - tables)
        if missing_tables:
            raise ValueError(f"missing required tables: {', '.join(missing_tables)}")

        schema_version = connection.execute(
            "SELECT version FROM schema_version LIMIT 1"
        ).fetchone()
        sessions_columns = _table_columns(connection, "sessions")
        has_model_usage = "session_model_usage" in tables
        model_columns = (
            _table_columns(connection, "session_model_usage")
            if has_model_usage
            else []
        )
        _require_columns(
            sessions_columns,
            ("id", "user_id", "started_at", "ended_at", *HERMES_TOKEN_COLUMNS),
            "sessions",
        )
        if has_model_usage:
            _require_columns(
                model_columns,
                (
                    "session_id",
                    "model",
                    "billing_provider",
                    "first_seen",
                    "last_seen",
                    *HERMES_TOKEN_COLUMNS,
                ),
                "session_model_usage",
            )

        session_usage = _aggregate_usage(connection, "sessions", HERMES_TOKEN_COLUMNS)
        model_usage = (
            _aggregate_usage(
                connection, "session_model_usage", HERMES_TOKEN_COLUMNS
            )
            if has_model_usage
            else None
        )
        coverage = connection.execute(
            """
            SELECT
              COUNT(*) AS sessions,
              SUM(CASE WHEN user_id IS NOT NULL AND user_id <> '' THEN 1 ELSE 0 END)
                AS sessions_with_user_id,
              MIN(started_at) AS started_at_min,
              MAX(COALESCE(ended_at, started_at)) AS effective_end_max
            FROM sessions
            """
        ).fetchone()
        model_coverage = (
            connection.execute(
                """
                SELECT
                  COUNT(*) AS rows,
                  COUNT(DISTINCT session_id) AS sessions,
                  SUM(CASE WHEN model IS NOT NULL AND model <> '' THEN 1 ELSE 0 END)
                    AS rows_with_model,
                  SUM(CASE WHEN billing_provider IS NOT NULL AND billing_provider <> ''
                           THEN 1 ELSE 0 END) AS rows_with_provider,
                  MIN(first_seen) AS first_seen_min,
                  MAX(last_seen) AS last_seen_max
                FROM session_model_usage
                """
            ).fetchone()
            if has_model_usage
            else (0, 0, 0, 0, None, None)
        )
        cost_table = "session_model_usage" if has_model_usage else "sessions"
        cost_source_columns = model_columns if has_model_usage else sessions_columns
        cost_columns = [
            column
            for column in ("estimated_cost_usd", "actual_cost_usd")
            if column in cost_source_columns
        ]
        cost_coverage: dict[str, Any] = {}
        for column in cost_columns:
            value = connection.execute(
                f"SELECT COUNT({_quote_identifier(column)}), "
                f"SUM({_quote_identifier(column)}) "
                f"FROM {_quote_identifier(cost_table)}"
            ).fetchone()
            cost_coverage[column] = {"present": value[0], "sum": value[1]}

        return {
            "inventory_format": 1,
            "parser": {"name": "hermes-sqlite-inventory", "version": PARSER_VERSION},
            "source_system": "hermes",
            "source_instance": instance,
            "source_snapshot": "<opaque-local-snapshot>",
            "snapshot_bytes": snapshot.stat().st_size,
            "read_only": True,
            "content_tables_queried": False,
            "schema_version": schema_version[0] if schema_version else None,
            "schema": {
                "sessions_columns": sessions_columns,
                "session_model_usage_columns": model_columns,
            },
            "coverage": {
                "sessions": coverage[0],
                "sessions_with_user_id": coverage[1],
                "started_at_min": coverage[2],
                "effective_end_max": coverage[3],
                "model_usage_rows": model_coverage[0],
                "model_usage_sessions": model_coverage[1],
                "model_usage_rows_with_model": model_coverage[2],
                "model_usage_rows_with_provider": model_coverage[3],
                "model_usage_first_seen_min": model_coverage[4],
                "model_usage_last_seen_max": model_coverage[5],
            },
            "session_aggregate": session_usage,
            "preferred_model_usage": model_usage,
            "cost_coverage": cost_coverage,
            "accounting_note": (
                "preferred_model_usage is the import candidate and session_aggregate "
                "is reconciliation-only"
                if has_model_usage
                else "session_aggregate is the import candidate for this legacy schema"
            ),
        }
    finally:
        connection.close()


def _write_result(result: dict[str, Any], output: Path | None) -> None:
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if output is None:
        sys.stdout.write(encoded)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing report: {output}")
    output.write_text(encoded, encoding="utf-8")
    print(
        json.dumps(
            {
                "report_written": True,
                "source_system": result["source_system"],
                "source_instance": result["source_instance"],
            }
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="source", required=True)
    codex = subparsers.add_parser("codex", help="inventory Codex rollout JSONL")
    codex.add_argument(
        "--source-root",
        type=Path,
        default=Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex")),
    )
    codex.add_argument("--output", type=Path)
    hermes = subparsers.add_parser("hermes", help="inventory a Hermes state.db snapshot")
    hermes.add_argument("--snapshot", type=Path, required=True)
    hermes.add_argument("--instance", choices=("main", "owashota"), required=True)
    hermes.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.source == "codex":
        result = inventory_codex(args.source_root)
    else:
        result = inventory_hermes(args.snapshot, args.instance)
    _write_result(result, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
