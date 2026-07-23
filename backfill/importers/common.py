from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable


RECORD_NAMESPACE = uuid.UUID("3b36c86c-3502-5ac5-9864-044bc977e311")
RECORD_FIELDS = (
    "record_id",
    "record_origin",
    "source_system",
    "source_instance",
    "source_record_id",
    "source_record_hash",
    "source_snapshot_hash",
    "parser_name",
    "parser_version",
    "import_run_id",
    "occurred_at",
    "period_start",
    "period_end",
    "record_granularity",
    "user_id",
    "request_model",
    "response_model",
    "provider",
    "input_tokens",
    "output_tokens",
    "cached_input_tokens",
    "cache_write_tokens",
    "reasoning_tokens",
    "total_tokens",
    "estimated_cost_usd",
    "actual_cost_usd",
    "cost_quality",
    "pricing_version",
    "quality",
    "quality_reason",
    "shared_eligible",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def opaque_id(*parts: Any) -> str:
    encoded = json.dumps(parts, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def canonical_hash(value: dict[str, Any]) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def utc_timestamp(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc).isoformat()
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None
        if candidate.replace(".", "", 1).isdigit():
            return datetime.fromtimestamp(float(candidate), timezone.utc).isoformat()
        if candidate.endswith("Z"):
            candidate = candidate[:-1] + "+00:00"
        parsed = datetime.fromisoformat(candidate)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    raise ValueError(f"unsupported timestamp type: {type(value).__name__}")


def timestamp_before(value: str | None, cutover: str | None) -> bool:
    if cutover is None:
        return True
    if value is None:
        return False
    normalized_value = utc_timestamp(value)
    normalized_cutover = utc_timestamp(cutover)
    if normalized_value is None or normalized_cutover is None:
        return False
    return datetime.fromisoformat(normalized_value) < datetime.fromisoformat(
        normalized_cutover
    )


def nonnegative_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"token value is not numeric: {type(value).__name__}")
    integer = int(value)
    if integer != value or integer < 0:
        raise ValueError("token value is negative or non-integral")
    return integer


def decimal_string(value: Any) -> str | None:
    if value is None or value == "":
        return None
    decimal = Decimal(str(value))
    if decimal < 0:
        raise ValueError("cost is negative")
    return format(decimal, "f")


def normalized_total(input_tokens: int | None, output_tokens: int | None) -> int | None:
    if input_tokens is None or output_tokens is None:
        return None
    return input_tokens + output_tokens


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    token_fields = (
        "input_tokens",
        "output_tokens",
        "cached_input_tokens",
        "cache_write_tokens",
        "reasoning_tokens",
        "total_tokens",
    )
    token_totals = {
        field: sum(
            record[field] for record in records if record[field] is not None
        )
        for field in token_fields
    }
    token_known_records = {
        field: sum(record[field] is not None for record in records)
        for field in token_fields
    }
    cost_quality: dict[str, int] = {}
    for record in records:
        quality = record["cost_quality"]
        cost_quality[quality] = cost_quality.get(quality, 0) + 1
    return {
        "token_totals": token_totals,
        "token_known_records": token_known_records,
        "dimension_coverage": {
            "request_model_records": sum(
                record["request_model"] is not None for record in records
            ),
            "provider_records": sum(
                record["provider"] is not None for record in records
            ),
            "user_id_records": sum(
                record["user_id"] is not None for record in records
            ),
            "distinct_user_ids": len({
                record["user_id"]
                for record in records
                if record["user_id"] is not None
            }),
        },
        "cost_quality_records": dict(sorted(cost_quality.items())),
        "cost_totals_usd": {
            "estimated": format(sum(
                Decimal(record["estimated_cost_usd"])
                for record in records
                if record["estimated_cost_usd"] is not None
            ), "f"),
            "actual": format(sum(
                Decimal(record["actual_cost_usd"])
                for record in records
                if record["actual_cost_usd"] is not None
            ), "f"),
        },
    }


def make_record(
    *,
    source_system: str,
    source_instance: str,
    native_key: Iterable[Any],
    snapshot_hash: str,
    parser_name: str,
    parser_version: str,
    import_run_id: str,
    values: dict[str, Any],
) -> dict[str, Any]:
    source_record_id = opaque_id(*native_key)
    stable_key = f"{source_system}:{source_instance}:backfill:{source_record_id}"
    record = {
        "record_id": str(uuid.uuid5(RECORD_NAMESPACE, stable_key)),
        "record_origin": "backfill",
        "source_system": source_system,
        "source_instance": source_instance,
        "source_record_id": source_record_id,
        "source_record_hash": "",
        "source_snapshot_hash": snapshot_hash,
        "parser_name": parser_name,
        "parser_version": parser_version,
        "import_run_id": import_run_id,
        **values,
    }
    missing = sorted(set(RECORD_FIELDS) - set(record))
    extra = sorted(set(record) - set(RECORD_FIELDS))
    if missing or extra:
        raise ValueError(f"record shape mismatch; missing={missing}, extra={extra}")
    hash_input = {
        key: value
        for key, value in record.items()
        if key not in {"record_id", "source_record_hash", "import_run_id"}
    }
    record["source_record_hash"] = canonical_hash(hash_input)
    return record


def write_outputs(
    records: list[dict[str, Any]],
    report: dict[str, Any],
    manifest_path: Path,
    report_path: Path,
) -> None:
    for path in (manifest_path, report_path):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite existing output: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")))
            handle.write("\n")
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
