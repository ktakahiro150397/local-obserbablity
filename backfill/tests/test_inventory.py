from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from backfill.inventory import inventory_codex, inventory_hermes


CANARY = "CONTENT-CANARY-MUST-NOT-APPEAR"


class CodexInventoryTest(unittest.TestCase):
    def test_inventory_persists_only_metadata_and_usage_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "sessions" / "2026" / "fixture.jsonl"
            path.parent.mkdir(parents=True)
            rows = [
                {
                    "timestamp": "2026-01-01T00:00:00Z",
                    "type": "session_meta",
                    "payload": {
                        "cli_version": "1.2.3",
                        "originator": "codex_cli_rs",
                        "model_provider": "openai",
                        "cwd": CANARY,
                    },
                },
                {
                    "timestamp": "2026-01-01T00:01:00Z",
                    "type": "turn_context",
                    "payload": {"model": "gpt-test", "user_instructions": CANARY},
                },
                {
                    "timestamp": "2026-01-01T00:02:00Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "user_message",
                        "message": CANARY,
                    },
                },
                {
                    "timestamp": "2026-01-01T00:03:00Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "token_count",
                        "info": {
                            "total_token_usage": {
                                "input_tokens": 10,
                                "output_tokens": 5,
                                "cached_input_tokens": 2,
                                "cache_write_input_tokens": 0,
                                "reasoning_output_tokens": 1,
                                "total_tokens": 15,
                            },
                            "last_token_usage": {
                                "input_tokens": 10,
                                "output_tokens": 5,
                                "cached_input_tokens": 2,
                                "cache_write_input_tokens": 0,
                                "reasoning_output_tokens": 1,
                                "total_tokens": 15,
                            },
                        },
                    },
                },
            ]
            path.write_text("".join(json.dumps(row) + "\n" for row in rows))
            result = inventory_codex(root)
            encoded = json.dumps(result)
            self.assertNotIn(CANARY, encoded)
            self.assertNotIn(str(root), encoded)
            self.assertEqual(result["summary"]["token_events"], 1)
            self.assertEqual(result["summary"]["files_with_token_events"], 1)


class HermesInventoryTest(unittest.TestCase):
    def test_inventory_never_queries_or_emits_message_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "state.db"
            connection = sqlite3.connect(path)
            connection.executescript(
                """
                CREATE TABLE schema_version(version INTEGER NOT NULL);
                INSERT INTO schema_version VALUES (23);
                CREATE TABLE messages(id TEXT, content TEXT, reasoning TEXT);
                CREATE TABLE sessions(
                  id TEXT, user_id TEXT, started_at TEXT, ended_at TEXT,
                  input_tokens INTEGER, output_tokens INTEGER,
                  cache_read_tokens INTEGER, cache_write_tokens INTEGER,
                  reasoning_tokens INTEGER
                );
                CREATE TABLE session_model_usage(
                  session_id TEXT, model TEXT, billing_provider TEXT,
                  first_seen TEXT, last_seen TEXT,
                  input_tokens INTEGER, output_tokens INTEGER,
                  cache_read_tokens INTEGER, cache_write_tokens INTEGER,
                  reasoning_tokens INTEGER,
                  estimated_cost_usd REAL, actual_cost_usd REAL
                );
                """
            )
            connection.execute("INSERT INTO messages VALUES ('m', ?, ?)", (CANARY, CANARY))
            connection.execute(
                "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?)",
                ("s", "discord:synthetic", "2026-01-01", "2026-01-02", 10, 5, 2, 0, 1),
            )
            connection.execute(
                "INSERT INTO session_model_usage VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                ("s", "model", "provider", "2026-01-01", "2026-01-02", 10, 5, 2, 0, 1, 0.1, None),
            )
            connection.commit()
            connection.close()
            result = inventory_hermes(path, "main")
            encoded = json.dumps(result)
            self.assertNotIn(CANARY, encoded)
            self.assertNotIn("discord:synthetic", encoded)
            self.assertTrue(result["read_only"])
            self.assertFalse(result["content_tables_queried"])
            self.assertEqual(result["preferred_model_usage"]["rows"], 1)


if __name__ == "__main__":
    unittest.main()
