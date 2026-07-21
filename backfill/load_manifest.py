#!/usr/bin/env python3
"""Validate and transactionally load one content-safe Phase 4 JSONL manifest."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

from backfill.importers.common import (
    RECORD_FIELDS,
    RECORD_NAMESPACE,
    canonical_hash,
    utc_timestamp,
)


HEX64 = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_SOURCES = {
    ("codex", "main-windows"),
    ("hermes", "hermes-main"),
    ("hermes", "hermes-owashota"),
}
TOKEN_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cached_input_tokens",
    "cache_write_tokens",
    "reasoning_tokens",
    "total_tokens",
)
COPY_FIELDS = RECORD_FIELDS


@dataclass(frozen=True)
class ManifestMetadata:
    import_run_id: str
    source_system: str
    source_instance: str
    parser_name: str
    parser_version: str
    source_snapshot_hash: str
    cutover: str
    record_count: int
    exact_count: int
    derived_count: int
    partial_count: int
    missing_count: int
    quarantined_count: int
    coverage_summary: dict[str, Any]
    shared_manifest: bool


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _uuid(value: Any, field: str) -> str:
    _require(isinstance(value, str), f"{field} must be a UUID string")
    try:
        return str(uuid.UUID(value))
    except ValueError as error:
        raise ValueError(f"{field} is not a UUID") from error


def _timestamp(value: Any, field: str, *, nullable: bool) -> str | None:
    if value is None and nullable:
        return None
    _require(isinstance(value, str), f"{field} must be an ISO timestamp string")
    normalized = utc_timestamp(value)
    _require(normalized is not None, f"{field} must not be empty")
    return normalized


def _bounded_text(value: Any, field: str, limit: int, *, nullable: bool) -> str | None:
    if value is None and nullable:
        return None
    _require(isinstance(value, str), f"{field} must be text")
    _require(1 <= len(value) <= limit, f"{field} length is invalid")
    _require("\x00" not in value, f"{field} contains a NUL byte")
    return value


def _nonnegative_integer(value: Any, field: str) -> int | None:
    if value is None:
        return None
    _require(isinstance(value, int) and not isinstance(value, bool), f"{field} must be an integer")
    _require(value >= 0, f"{field} must be nonnegative")
    return value


def _validate_record(record: Any, line_number: int, cutover: str) -> dict[str, Any]:
    prefix = f"manifest line {line_number}: "
    _require(isinstance(record, dict), prefix + "record must be an object")
    _require(set(record) == set(RECORD_FIELDS), prefix + "record fields do not match the allowlist")
    _require(record["record_origin"] == "backfill", prefix + "record_origin must be backfill")
    pair = (record["source_system"], record["source_instance"])
    _require(pair in ALLOWED_SOURCES, prefix + "source is not approved for Phase 4")
    _require(HEX64.fullmatch(str(record["source_record_id"])) is not None, prefix + "source_record_id is invalid")
    _require(HEX64.fullmatch(str(record["source_record_hash"])) is not None, prefix + "source_record_hash is invalid")
    _require(HEX64.fullmatch(str(record["source_snapshot_hash"])) is not None, prefix + "source_snapshot_hash is invalid")
    record_id = _uuid(record["record_id"], prefix + "record_id")
    _uuid(record["import_run_id"], prefix + "import_run_id")
    stable_key = f'{record["source_system"]}:{record["source_instance"]}:backfill:{record["source_record_id"]}'
    _require(record_id == str(uuid.uuid5(RECORD_NAMESPACE, stable_key)), prefix + "record_id is not deterministic")
    expected_hash = canonical_hash({
        key: value
        for key, value in record.items()
        if key not in {"record_id", "source_record_hash", "import_run_id"}
    })
    _require(record["source_record_hash"] == expected_hash, prefix + "source_record_hash mismatch")

    for field, limit, nullable in (
        ("source_instance", 100, False),
        ("parser_name", 100, False),
        ("parser_version", 100, False),
        ("source_record_id", 300, False),
        ("user_id", 200, True),
        ("request_model", 200, True),
        ("response_model", 200, True),
        ("provider", 200, True),
        ("pricing_version", 100, True),
        ("quality_reason", 100, False),
    ):
        _bounded_text(record[field], prefix + field, limit, nullable=nullable)

    occurred = _timestamp(record["occurred_at"], prefix + "occurred_at", nullable=True)
    period_start = _timestamp(record["period_start"], prefix + "period_start", nullable=True)
    period_end = _timestamp(record["period_end"], prefix + "period_end", nullable=True)
    _require(occurred is not None or (period_start is not None and period_end is not None), prefix + "record has no usable time")
    if period_start and period_end:
        _require(datetime.fromisoformat(period_end) >= datetime.fromisoformat(period_start), prefix + "period is reversed")
    boundary = datetime.fromisoformat(cutover)
    for field, value in (("occurred_at", occurred), ("period_end", period_end)):
        if value is not None:
            _require(datetime.fromisoformat(value) < boundary, prefix + f"{field} is at or after cutover")

    for field in TOKEN_FIELDS:
        _nonnegative_integer(record[field], prefix + field)
    _require(record["record_granularity"] in {"api_call", "turn", "message", "session", "day", "hour"}, prefix + "granularity is invalid")
    _require(record["quality"] in {"exact", "derived", "partial"}, prefix + "quality is invalid")
    _require(record["cost_quality"] in {"reported", "unknown"}, prefix + "estimated cost quality is prohibited")
    _require(record["estimated_cost_usd"] is None, prefix + "estimated cost is prohibited")
    _require(record["pricing_version"] is None, prefix + "pricing version is prohibited without estimates")
    actual = record["actual_cost_usd"]
    if actual is not None:
        _require(isinstance(actual, str), prefix + "actual cost must be a decimal string")
        try:
            decimal = Decimal(actual)
            _require(decimal.is_finite() and decimal >= 0, prefix + "actual cost must be finite and nonnegative")
        except InvalidOperation as error:
            raise ValueError(prefix + "actual cost is invalid") from error
        _require(record["cost_quality"] == "reported", prefix + "actual cost must be provider-reported")
    else:
        _require(record["cost_quality"] == "unknown", prefix + "reported cost requires a value")
    _require(isinstance(record["shared_eligible"], bool), prefix + "shared_eligible must be boolean")
    _require(record["source_system"] != "codex" or not record["shared_eligible"], prefix + "Codex cannot be shared eligible")
    return record


def _safe_report(
    report_path: Path, records: list[dict[str, Any]], cutover: str
) -> tuple[dict[str, Any], int, int, bool]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    _require(isinstance(report, dict), "report must be an object")
    _require(report.get("content_fields_persisted") is False, "report does not affirm content exclusion")
    _require(report.get("normalized_records") == len(records), "report record count does not match manifest")
    _require(utc_timestamp(report.get("cutover")) == cutover, "report cutover does not match approved cutover")
    first = records[0]
    for field in ("source_system", "source_instance", "parser_name", "parser_version", "import_run_id", "source_snapshot_hash"):
        _require(report.get(field) == first[field], f"report {field} does not match manifest")
    counts = report.get("counts", {})
    _require(isinstance(counts, dict), "report counts must be an object")
    safe_counts: dict[str, int] = {}
    for key, value in counts.items():
        _require(isinstance(key, str) and re.fullmatch(r"[a-z0-9_]+", key) is not None, "report count key is invalid")
        _require(isinstance(value, int) and not isinstance(value, bool) and value >= 0, "report count must be nonnegative")
        safe_counts[key] = value
    missing = sum(safe_counts.get(key, 0) for key in (
        "token_events_without_usable_cumulative",
        "files_without_token_events",
        "invalid_json_lines",
        "invalid_discord_user_ids",
    ))
    quarantined = sum(safe_counts.get(key, 0) for key in (
        "quarantined_boundary_sessions",
        "quarantined_boundary_model_rows",
    ))
    summary = {
        "format": 1,
        "normalized_records": len(records),
        "source_units": report.get("source_files", report.get("source_sessions", len(records))),
        "excluded_counts": safe_counts,
        "estimated_values_included": False,
        "content_fields_persisted": False,
        "shared_manifest": report.get("shared_manifest") is True,
    }
    _require(isinstance(summary["source_units"], int) and not isinstance(summary["source_units"], bool) and summary["source_units"] >= 0, "report source unit count is invalid")
    return summary, missing, quarantined, summary["shared_manifest"]


def validate_manifest(manifest_path: Path, report_path: Path, cutovers_path: Path) -> tuple[list[dict[str, Any]], ManifestMetadata]:
    cutovers = json.loads(cutovers_path.read_text(encoding="utf-8"))
    _require(cutovers.get("status") == "approved", "cutovers are not BF2-approved")
    approved = cutovers.get("sources")
    _require(isinstance(approved, dict), "approved cutovers are missing")
    records: list[dict[str, Any]] = []
    metadata: tuple[Any, ...] | None = None
    seen_record_ids: set[str] = set()
    seen_source_ids: set[str] = set()
    with manifest_path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, 1):
            _require(raw.endswith("\n"), f"manifest line {line_number}: truncated line")
            item = json.loads(raw)
            pair = (item.get("source_system"), item.get("source_instance")) if isinstance(item, dict) else (None, None)
            cutover_key = f"{pair[0]}-{str(pair[1]).removeprefix('hermes-')}" if pair[0] == "hermes" else "codex-main-windows"
            _require(cutover_key in approved, f"manifest line {line_number}: no approved cutover")
            cutover = _timestamp(approved[cutover_key], f"cutover {cutover_key}", nullable=False)
            assert cutover is not None
            record = _validate_record(item, line_number, cutover)
            current = tuple(record[field] for field in (
                "import_run_id", "source_system", "source_instance", "parser_name", "parser_version", "source_snapshot_hash"
            )) + (cutover,)
            if metadata is None:
                metadata = current
            _require(current == metadata, f"manifest line {line_number}: mixed manifest metadata")
            _require(record["record_id"] not in seen_record_ids, f"manifest line {line_number}: duplicate record_id")
            _require(record["source_record_id"] not in seen_source_ids, f"manifest line {line_number}: duplicate source_record_id")
            seen_record_ids.add(record["record_id"])
            seen_source_ids.add(record["source_record_id"])
            records.append(record)
    _require(records, "manifest must contain at least one record")
    assert metadata is not None
    report_summary, missing_count, quarantined_count, shared_manifest = _safe_report(
        report_path, records, metadata[6]
    )
    qualities = Counter(record["quality"] for record in records)
    result = ManifestMetadata(
        import_run_id=metadata[0], source_system=metadata[1], source_instance=metadata[2],
        parser_name=metadata[3], parser_version=metadata[4], source_snapshot_hash=metadata[5],
        cutover=metadata[6], record_count=len(records), exact_count=qualities["exact"],
        derived_count=qualities["derived"], partial_count=qualities["partial"],
        missing_count=missing_count, quarantined_count=quarantined_count,
        coverage_summary=report_summary, shared_manifest=shared_manifest,
    )
    return records, result


def validate_shared_publication(
    records: Iterable[dict[str, Any]], meta: ManifestMetadata
) -> None:
    """Enforce the BF4 Hermes-only, cost-free shared publication boundary."""
    _require(meta.shared_manifest, "shared publication requires a --shared report")
    _require(meta.source_system == "hermes", "shared publication accepts Hermes only")
    for line_number, record in enumerate(records, 1):
        prefix = f"shared manifest line {line_number}: "
        _require(record["source_system"] == "hermes", prefix + "source must be Hermes")
        _require(record["shared_eligible"] is True, prefix + "shared_eligible must be true")
        _require(
            record["estimated_cost_usd"] is None
            and record["actual_cost_usd"] is None
            and record["pricing_version"] is None
            and record["cost_quality"] == "unknown",
            prefix + "cost publication is not approved",
        )
        user_id = record["user_id"]
        _require(
            user_id is None or re.fullmatch(r"discord:[0-9]+", user_id) is not None,
            prefix + "user_id is not an approved Discord accounting ID",
        )


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _copy_value(value: Any) -> str:
    if value is None:
        return r"\N"
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value)
    return text.replace("\\", "\\\\").replace("\t", r"\t").replace("\n", r"\n").replace("\r", r"\r")


def _sql_prefix(
    meta: ManifestMetadata,
    *,
    approval_ref: str = "BF2-2026-07-22-owner-approved",
) -> str:
    fields = ",".join(COPY_FIELDS)
    values = {name: _sql_literal(str(getattr(meta, name))) for name in (
        "import_run_id", "source_system", "source_instance", "parser_name", "parser_version", "source_snapshot_hash", "cutover"
    )}
    return f"""\\set ON_ERROR_STOP on
BEGIN;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
SELECT pg_advisory_xact_lock(hashtextextended({values['source_system']} || ':' || {values['source_instance']}, 0));
INSERT INTO usage.cutovers(source_system,source_instance,cutover_at,approval_ref,approved_at)
VALUES ({values['source_system']},{values['source_instance']},{values['cutover']},{_sql_literal(approval_ref)},CURRENT_TIMESTAMP)
ON CONFLICT DO NOTHING;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM usage.cutovers WHERE source_system={values['source_system']} AND source_instance={values['source_instance']} AND cutover_at={values['cutover']}::timestamptz) THEN
    RAISE EXCEPTION 'approved cutover mismatch';
  END IF;
END $$;
INSERT INTO usage.import_runs(import_run_id,source_system,source_instance,parser_name,parser_version,source_snapshot_hash,status)
VALUES ({values['import_run_id']}::uuid,{values['source_system']},{values['source_instance']},{values['parser_name']},{values['parser_version']},{values['source_snapshot_hash']},'importing')
ON CONFLICT DO NOTHING;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM usage.import_runs WHERE import_run_id={values['import_run_id']}::uuid AND source_system={values['source_system']} AND source_instance={values['source_instance']} AND parser_name={values['parser_name']} AND parser_version={values['parser_version']} AND source_snapshot_hash={values['source_snapshot_hash']} AND status <> 'rolled_back') THEN
    RAISE EXCEPTION 'import run metadata mismatch or run was rolled back';
  END IF;
END $$;
CREATE TEMP TABLE manifest_records (LIKE usage.usage_records INCLUDING DEFAULTS) ON COMMIT DROP;
\\copy manifest_records ({fields}) FROM STDIN WITH (FORMAT text, DELIMITER E'\\t', NULL '\\N')
"""


def _sql_suffix(
    meta: ManifestMetadata, *, result_prefix: str = "BF3_RESULT"
) -> str:
    values = {name: _sql_literal(str(getattr(meta, name))) for name in ("import_run_id", "source_system", "source_instance", "cutover")}
    summary = _sql_literal(json.dumps(meta.coverage_summary, sort_keys=True, separators=(",", ":")))
    return f"""\\.
DO $$ BEGIN
  IF (SELECT count(*) FROM manifest_records) <> {meta.record_count} THEN RAISE EXCEPTION 'manifest row count mismatch'; END IF;
  IF EXISTS (SELECT 1 FROM manifest_records WHERE import_run_id <> {values['import_run_id']}::uuid OR source_system <> {values['source_system']} OR source_instance <> {values['source_instance']} OR record_origin <> 'backfill') THEN RAISE EXCEPTION 'manifest metadata changed during COPY'; END IF;
  IF EXISTS (SELECT 1 FROM manifest_records WHERE occurred_at >= {values['cutover']}::timestamptz OR period_end >= {values['cutover']}::timestamptz) THEN RAISE EXCEPTION 'manifest crosses approved cutover'; END IF;
  IF EXISTS (SELECT 1 FROM manifest_records m JOIN usage.usage_records u USING (record_id) WHERE (u.source_system,u.source_instance,u.record_origin,u.source_record_id,u.source_record_hash) IS DISTINCT FROM (m.source_system,m.source_instance,m.record_origin,m.source_record_id,m.source_record_hash)) THEN RAISE EXCEPTION 'record_id collision'; END IF;
  IF EXISTS (SELECT 1 FROM manifest_records m JOIN usage.usage_records u USING (source_system,source_instance,record_origin,source_record_id) WHERE (u.record_id,u.source_record_hash) IS DISTINCT FROM (m.record_id,m.source_record_hash)) THEN RAISE EXCEPTION 'source record changed since prior import'; END IF;
END $$;
CREATE TEMP TABLE attempt_result(inserted_count bigint NOT NULL);
WITH inserted AS (
  INSERT INTO usage.usage_records ({','.join(COPY_FIELDS)}) SELECT {','.join(COPY_FIELDS)} FROM manifest_records
  ON CONFLICT (source_system,source_instance,record_origin,source_record_id) DO NOTHING RETURNING 1
) INSERT INTO attempt_result SELECT count(*) FROM inserted;
UPDATE usage.import_runs SET status='complete',finished_at=COALESCE(finished_at,CURRENT_TIMESTAMP),
  inserted_count=(SELECT count(*) FROM usage.usage_records WHERE import_run_id={values['import_run_id']}::uuid),updated_count=0,skipped_count=0,error_count=0
WHERE import_run_id={values['import_run_id']}::uuid;
INSERT INTO usage.coverage_reports(import_run_id,source_records,exact_records,derived_records,partial_records,missing_records,quarantined_records,summary)
VALUES ({values['import_run_id']}::uuid,{meta.record_count},{meta.exact_count},{meta.derived_count},{meta.partial_count},{meta.missing_count},{meta.quarantined_count},{summary}::jsonb)
ON CONFLICT (import_run_id) DO UPDATE SET source_records=EXCLUDED.source_records,exact_records=EXCLUDED.exact_records,derived_records=EXCLUDED.derived_records,partial_records=EXCLUDED.partial_records,missing_records=EXCLUDED.missing_records,quarantined_records=EXCLUDED.quarantined_records,summary=EXCLUDED.summary;
COMMIT;
SELECT {_sql_literal(result_prefix + ' inserted=')} || inserted_count || ' linked=' || (SELECT count(*) FROM usage.usage_records WHERE import_run_id={values['import_run_id']}::uuid) FROM attempt_result;
"""


def stream_psql(
    records: Iterable[dict[str, Any]],
    meta: ManifestMetadata,
    *,
    service: str | None = None,
    isolated_test_container: str | None = None,
    phase: str = "BF3",
) -> str:
    _require((service is None) != (isolated_test_container is None), "choose one PostgreSQL target")
    if service is not None:
        command = ["docker", "compose", "exec", "-T", service]
    else:
        assert isolated_test_container is not None
        _require(isolated_test_container.startswith("phase4-loader-test-"), "isolated test container name is unsafe")
        command = ["docker", "exec", "-i", isolated_test_container]
    command += ["psql", "--quiet", "--tuples-only", "--no-align", "--username", "ledger_writer", "--dbname", "usage_ledger"]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert process.stdin is not None
    try:
        approval_ref = (
            "BF4-2026-07-22-owner-approved"
            if phase == "BF4"
            else "BF2-2026-07-22-owner-approved"
        )
        process.stdin.write(
            _sql_prefix(meta, approval_ref=approval_ref).encode("utf-8")
        )
        for record in records:
            row = "\t".join(_copy_value(record[field]) for field in COPY_FIELDS) + "\n"
            process.stdin.write(row.encode("utf-8"))
        result_prefix = "BF4_RESULT" if phase == "BF4" else "BF3_RESULT"
        process.stdin.write(
            _sql_suffix(meta, result_prefix=result_prefix).encode("utf-8")
        )
        process.stdin.close()
        stdout = process.stdout.read() if process.stdout else b""
        stderr = process.stderr.read() if process.stderr else b""
        return_code = process.wait()
    except BaseException:
        process.kill()
        process.wait()
        raise
    if return_code != 0:
        message = stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"transactional ledger load failed; PostgreSQL rolled back: {message}")
    result_prefix = "BF4_RESULT" if phase == "BF4" else "BF3_RESULT"
    lines = [
        line
        for line in stdout.decode("utf-8", errors="replace").splitlines()
        if line.startswith(result_prefix + " ")
    ]
    _require(len(lines) == 1, "ledger did not return one import result")
    return lines[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--cutovers", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--validate-shared-only", action="store_true")
    parser.add_argument("--write-private", action="store_true")
    parser.add_argument("--write-shared", action="store_true")
    parser.add_argument("--write-isolated-test", metavar="CONTAINER")
    parser.add_argument(
        "--isolated-domain", choices=("private", "shared"), default="private"
    )
    args = parser.parse_args()
    _require(
        sum(
            (
                args.validate_only,
                args.validate_shared_only,
                args.write_private,
                args.write_shared,
                bool(args.write_isolated_test),
            )
        )
        == 1,
        "choose exactly one operation",
    )
    records, metadata = validate_manifest(args.manifest, args.report, args.cutovers)
    shared_operation = (
        args.validate_shared_only
        or args.write_shared
        or (bool(args.write_isolated_test) and args.isolated_domain == "shared")
    )
    if shared_operation:
        validate_shared_publication(records, metadata)
    if args.validate_only:
        print(json.dumps({"validated_records": metadata.record_count, "source_system": metadata.source_system, "source_instance": metadata.source_instance}, sort_keys=True))
        return 0
    if args.validate_shared_only:
        print(
            json.dumps(
                {
                    "validated_records": metadata.record_count,
                    "source_system": metadata.source_system,
                    "source_instance": metadata.source_instance,
                    "shared_publication": True,
                    "cost_publication": False,
                },
                sort_keys=True,
            )
        )
        return 0
    if args.write_isolated_test:
        test_guard = "BF4_TEST_ONLY" if shared_operation else "BF3_TEST_ONLY"
        _require(
            os.environ.get(test_guard) == "yes",
            f"isolated test write requires {test_guard}=yes",
        )
        print(
            stream_psql(
                records,
                metadata,
                isolated_test_container=args.write_isolated_test,
                phase="BF4" if shared_operation else "BF3",
            )
        )
        return 0
    if args.write_shared:
        _require(
            os.environ.get("BF4_APPROVED") == "yes",
            "production shared write requires BF4_APPROVED=yes",
        )
        print(stream_psql(records, metadata, service="shared-ledger", phase="BF4"))
        return 0
    _require(os.environ.get("BF3_APPROVED") == "yes", "production private write requires BF3_APPROVED=yes")
    print(stream_psql(records, metadata, service="private-ledger"))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(2)
