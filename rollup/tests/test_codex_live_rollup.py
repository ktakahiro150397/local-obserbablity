from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from codex_live_rollup import extract_records  # noqa: E402


def attribute(key: str, value: object) -> dict[str, object]:
    encoded = (
        {"intValue": str(value)}
        if isinstance(value, int)
        else {"stringValue": str(value)}
    )
    return {"key": key, "value": encoded}


def trace_fixture(
    *,
    service_name: str = "codex_exec",
    duplicate_batch: bool = False,
    include_content: bool = True,
    total_tokens: int | None = 17,
) -> dict[str, object]:
    attributes = [
        attribute("model", "synthetic-model"),
        attribute("codex.turn.token_usage.input_tokens", 12),
        attribute("codex.turn.token_usage.output_tokens", 5),
        attribute("codex.turn.token_usage.cached_input_tokens", 7),
        attribute("codex.turn.token_usage.cache_write_input_tokens", 1),
        attribute("codex.turn.token_usage.reasoning_output_tokens", 2),
    ]
    if total_tokens is not None:
        attributes.append(
            attribute("codex.turn.token_usage.total_tokens", total_tokens)
        )
    if include_content:
        attributes.extend(
            [
                attribute("prompt", "CANARY_PROMPT"),
                attribute("response", "CANARY_RESPONSE"),
                attribute("tool.arguments", "CANARY_TOOL_ARGUMENT"),
                attribute("cwd", "CANARY_PRIVATE_PATH"),
            ]
        )
    batch = {
        "resource": {
            "attributes": [attribute("service.name", service_name)]
        },
        "scopeSpans": [
            {
                "spans": [
                    {
                        "traceId": "a" * 32,
                        "spanId": "b" * 16,
                        "parentSpanId": "c" * 16,
                        "name": "session_task.turn",
                        "startTimeUnixNano": "1784600000000000000",
                        "endTimeUnixNano": "1784600005000000000",
                        "attributes": attributes,
                    }
                ]
            }
        ],
    }
    return {"batches": [batch, batch] if duplicate_batch else [batch]}


class ExtractCodexRecordTests(unittest.TestCase):
    def test_extracts_cli_turn_and_drops_content(self) -> None:
        records = extract_records(
            trace_fixture(),
            expected_services=("codex_exec", "codex-app-server"),
            source_instance="main-windows",
        )
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["source_system"], "codex")
        self.assertEqual(record["source_instance"], "main-windows")
        self.assertEqual(record["client"], "cli")
        self.assertEqual(record["request_model"], "synthetic-model")
        self.assertEqual(record["input_tokens"], 12)
        self.assertEqual(record["output_tokens"], 5)
        self.assertEqual(record["cached_input_tokens"], 7)
        self.assertEqual(record["cache_write_tokens"], 1)
        self.assertEqual(record["reasoning_tokens"], 2)
        self.assertEqual(record["total_tokens"], 17)
        self.assertFalse(record["shared_eligible"])
        serialized = str(record)
        self.assertNotIn("CANARY_PROMPT", serialized)
        self.assertNotIn("CANARY_RESPONSE", serialized)
        self.assertNotIn("CANARY_TOOL_ARGUMENT", serialized)
        self.assertNotIn("CANARY_PRIVATE_PATH", serialized)

    def test_maps_desktop_service_and_deduplicates_tempo_batches(self) -> None:
        records = extract_records(
            trace_fixture(
                service_name="codex-app-server", duplicate_batch=True
            ),
            expected_services=("codex_exec", "codex-app-server"),
            source_instance="main-windows",
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["client"], "desktop")

    def test_derives_total_only_from_input_and_output(self) -> None:
        record = extract_records(
            trace_fixture(total_tokens=None),
            expected_services=("codex_exec",),
            source_instance="main-windows",
        )[0]
        self.assertEqual(record["total_tokens"], 17)
        self.assertEqual(record["quality"], "derived")

    def test_rejects_unapproved_service(self) -> None:
        records = extract_records(
            trace_fixture(service_name="unapproved-service"),
            expected_services=("codex_exec",),
            source_instance="main-windows",
        )
        self.assertEqual(records, [])


if __name__ == "__main__":
    unittest.main()
