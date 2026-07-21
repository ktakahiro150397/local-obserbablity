from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from backfill.importers.codex import normalize as normalize_codex
from backfill.importers.hermes import normalize as normalize_hermes


CANARY = "IMPORTER-CONTENT-CANARY"


class CodexImporterTest(unittest.TestCase):
    def test_cumulative_deltas_and_reset_do_not_emit_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data = root / "data"
            path = data / "sessions" / "fixture.jsonl"
            path.parent.mkdir(parents=True)
            manifest = root / "manifest.json"
            manifest.write_text('{"synthetic":true}\n')

            def token(timestamp: str, total: int, input_tokens: int, output: int):
                usage = {
                    "input_tokens": input_tokens,
                    "output_tokens": output,
                    "cached_input_tokens": 2,
                    "cache_write_input_tokens": 0,
                    "reasoning_output_tokens": 1,
                    "total_tokens": total,
                }
                return {
                    "timestamp": timestamp,
                    "type": "event_msg",
                    "payload": {"type": "token_count", "info": {"total_token_usage": usage}},
                }

            rows = [
                {"timestamp": "2026-01-01T00:00:00Z", "type": "session_meta", "payload": {"id": "secret-session", "model_provider": "provider", "base_instructions": CANARY}},
                {"timestamp": "2026-01-01T00:00:01Z", "type": "turn_context", "payload": {"model": "model", "user_instructions": CANARY}},
                {"timestamp": "2026-01-01T00:00:02Z", "type": "event_msg", "payload": {"type": "user_message", "message": CANARY}},
                token("2026-01-01T00:00:03Z", 15, 10, 5),
                token("2026-01-01T00:00:04Z", 24, 16, 8),
                token("2026-01-01T00:00:05Z", 6, 4, 2),
            ]
            path.write_text("".join(json.dumps(row) + "\n" for row in rows))
            records, report = normalize_codex(
                data,
                manifest,
                cutover="2026-01-01T00:00:06Z",
                import_run_id="00000000-0000-0000-0000-000000000001",
            )
            self.assertEqual([record["total_tokens"] for record in records], [15, 9, 6])
            self.assertEqual(report["counts"]["cumulative_resets"], 1)
            self.assertEqual(report["summary"]["token_totals"]["total_tokens"], 30)
            encoded = json.dumps(records)
            self.assertNotIn(CANARY, encoded)
            self.assertNotIn("secret-session", encoded)
            self.assertTrue(all(not record["shared_eligible"] for record in records))


class HermesImporterTest(unittest.TestCase):
    def _database(self, path: Path) -> None:
        connection = sqlite3.connect(path)
        connection.executescript(
            """
            CREATE TABLE schema_version(version INTEGER);
            INSERT INTO schema_version VALUES (20);
            CREATE TABLE messages(content TEXT, reasoning TEXT);
            CREATE TABLE sessions(
              id TEXT, source TEXT, user_id TEXT, model TEXT,
              started_at REAL, ended_at REAL,
              input_tokens INTEGER, output_tokens INTEGER,
              cache_read_tokens INTEGER, cache_write_tokens INTEGER,
              reasoning_tokens INTEGER, billing_provider TEXT,
              estimated_cost_usd REAL, actual_cost_usd REAL,
              cost_status TEXT, cost_source TEXT, pricing_version TEXT
            );
            CREATE TABLE session_model_usage(
              session_id TEXT, model TEXT, billing_provider TEXT, billing_mode TEXT,
              api_call_count INTEGER, input_tokens INTEGER, output_tokens INTEGER,
              cache_read_tokens INTEGER, cache_write_tokens INTEGER,
              reasoning_tokens INTEGER, estimated_cost_usd REAL,
              actual_cost_usd REAL, cost_status TEXT, cost_source TEXT,
              first_seen REAL, last_seen REAL
            );
            """
        )
        connection.execute("INSERT INTO messages VALUES (?,?)", (CANARY, CANARY))
        sessions = [
            ("s1", "discord", "12345", "fallback", 1000.0, 1010.0, 10, 5, 2, 0, 1, "provider", 0, 0, "unknown", "none", None),
            ("s2", "discord", "67890", "session-model", 2000.0, 2020.0, 30, 15, 4, 0, 2, "provider", 0, 0, "included", "none", None),
        ]
        connection.executemany("INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", sessions)
        model_rows = [
            ("s2", "m1", "provider", "included", 1, 20, 10, 3, 0, 1, 0, 0, "included", "none", 2000.0, 2010.0),
            ("s2", "m2", "provider", "included", 1, 10, 5, 1, 0, 1, 0, 0, "included", "none", 2010.0, 2020.0),
        ]
        connection.executemany("INSERT INTO session_model_usage VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", model_rows)
        connection.commit()
        connection.close()

    def test_per_model_preferred_and_fallback_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "state.db"
            self._database(path)
            records, report = normalize_hermes(path, "main", import_run_id="00000000-0000-0000-0000-000000000001")
            self.assertEqual(len(records), 3)
            self.assertEqual(sum(record["total_tokens"] for record in records), 66)
            self.assertEqual(sorted(record["user_id"] for record in records), ["discord:12345", "discord:67890", "discord:67890"])
            self.assertNotIn(CANARY, json.dumps(records))
            self.assertEqual(report["counts"]["exact_records"], 2)
            self.assertEqual(report["counts"]["derived_records"], 1)
            self.assertEqual(report["summary"]["dimension_coverage"]["distinct_user_ids"], 2)

    def test_shared_manifest_removes_cost(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "state.db"
            self._database(path)
            records, _ = normalize_hermes(path, "main", shared=True, import_run_id="00000000-0000-0000-0000-000000000001")
            self.assertTrue(all(record["shared_eligible"] for record in records))
            self.assertTrue(all(record["actual_cost_usd"] is None for record in records))
            self.assertTrue(all(record["estimated_cost_usd"] is None for record in records))
            self.assertTrue(all(record["pricing_version"] is None for record in records))


if __name__ == "__main__":
    unittest.main()
