from __future__ import annotations

import json
import tempfile
import unittest
import uuid
from pathlib import Path

from backfill.importers.common import make_record, sha256_file
from backfill.load_manifest import _copy_value, _sql_suffix, validate_manifest


def _fixture(tmp_path: Path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    snapshot = tmp_path / "state.db"
    snapshot.write_bytes(b"synthetic")
    run_id = str(uuid.uuid4())
    record = make_record(
        source_system="hermes",
        source_instance="hermes-main",
        native_key=("session", "synthetic"),
        snapshot_hash=sha256_file(snapshot),
        parser_name="hermes-state",
        parser_version="0.2.0",
        import_run_id=run_id,
        values={
            "occurred_at": "2026-07-20T00:00:00+00:00",
            "period_start": "2026-07-20T00:00:00+00:00",
            "period_end": "2026-07-20T00:01:00+00:00",
            "record_granularity": "session",
            "user_id": "discord:123456",
            "request_model": "synthetic-model",
            "response_model": "synthetic-model",
            "provider": "synthetic-provider",
            "input_tokens": 10,
            "output_tokens": 2,
            "cached_input_tokens": 3,
            "cache_write_tokens": 0,
            "reasoning_tokens": 1,
            "total_tokens": 12,
            "estimated_cost_usd": None,
            "actual_cost_usd": None,
            "cost_quality": "unknown",
            "pricing_version": None,
            "quality": "exact",
            "quality_reason": "per_model_usage",
            "shared_eligible": True,
        },
    )
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    report = tmp_path / "report.json"
    report.write_text(json.dumps({
        "source_system": "hermes", "source_instance": "hermes-main",
        "parser_name": "hermes-state", "parser_version": "0.2.0",
        "import_run_id": run_id, "source_snapshot_hash": record["source_snapshot_hash"],
        "cutover": "2026-07-21T12:18:20.169098+00:00",
        "normalized_records": 1, "source_sessions": 1, "counts": {"exact_records": 1},
        "content_fields_persisted": False,
    }), encoding="utf-8")
    cutovers = tmp_path / "cutovers.json"
    cutovers.write_text(json.dumps({
        "status": "approved",
        "sources": {"hermes-main": "2026-07-21T12:18:20.169098+00:00"},
    }), encoding="utf-8")
    return manifest, report, cutovers, record


class LoaderTest(unittest.TestCase):
    def test_validate_manifest_and_render_transaction(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            manifest, report, cutovers, _ = _fixture(Path(temp))
            records, metadata = validate_manifest(manifest, report, cutovers)
            self.assertEqual(len(records), metadata.record_count)
            self.assertEqual(metadata.exact_count, 1)
            sql = _sql_suffix(metadata)
            self.assertIn("ON CONFLICT (source_system,source_instance,record_origin,source_record_id) DO NOTHING", sql)
            self.assertIn("source record changed since prior import", sql)
            self.assertIn("COMMIT;", sql)

    def test_rejects_estimates_and_cutover_overlap(self) -> None:
        from backfill.importers.common import canonical_hash

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest, report, cutovers, record = _fixture(root)
            record["estimated_cost_usd"] = "1.00"
            hash_input = {key: value for key, value in record.items() if key not in {"record_id", "source_record_hash", "import_run_id"}}
            record["source_record_hash"] = canonical_hash(hash_input)
            manifest.write_text(json.dumps(record) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "estimated cost is prohibited"):
                validate_manifest(manifest, report, cutovers)

            manifest, report, cutovers, record = _fixture(root / "second")
            record["occurred_at"] = "2026-07-22T00:00:00+00:00"
            record["period_end"] = "2026-07-22T00:00:00+00:00"
            hash_input = {key: value for key, value in record.items() if key not in {"record_id", "source_record_hash", "import_run_id"}}
            record["source_record_hash"] = canonical_hash(hash_input)
            manifest.write_text(json.dumps(record) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "at or after cutover"):
                validate_manifest(manifest, report, cutovers)

    def test_copy_text_escaping(self) -> None:
        self.assertEqual(_copy_value(None), r"\N")
        self.assertEqual(_copy_value("a\tb\\c\n"), r"a\tb\\c\n")


if __name__ == "__main__":
    unittest.main()
