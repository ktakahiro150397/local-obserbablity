from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from live_rollup import (  # noqa: E402
    SYSTEM_SELF_IMPROVEMENT_USER_ID,
    complete_trace_search,
    extract_records,
)


def attribute(key: str, value: object) -> dict[str, object]:
    if isinstance(value, int):
        encoded = {"intValue": str(value)}
    else:
        encoded = {"stringValue": str(value)}
    return {"key": key, "value": encoded}


def trace_fixture(
    *,
    total_tokens: int | None = 17,
    parent_span_id: str | None = None,
    include_content: bool = True,
    include_sender: bool = True,
    include_self_improvement: bool = False,
) -> dict[str, object]:
    span_attributes = [
        attribute("gen_ai.request.model", "synthetic-model"),
        attribute("gen_ai.response.model", "synthetic-model-response"),
        attribute("gen_ai.provider.name", "discord"),
        attribute("gen_ai.usage.input_tokens", 12),
        attribute("gen_ai.usage.output_tokens", 5),
        attribute("gen_ai.usage.cache_read.input_tokens", 7),
        attribute("gen_ai.usage.reasoning.output_tokens", 2),
    ]
    if include_sender:
        span_attributes.extend(
            [
                attribute("user.id", "discord:synthetic-user"),
                attribute("hermes.sender.id", "synthetic-user"),
            ]
        )
    if total_tokens is not None:
        span_attributes.append(attribute("gen_ai.usage.total_tokens", total_tokens))
    if include_content:
        span_attributes.extend(
            [
                attribute("gen_ai.prompt", "CANARY_PROMPT"),
                attribute("gen_ai.completion", "CANARY_RESPONSE"),
                attribute("tool.arguments", "CANARY_TOOL_ARGUMENT"),
            ]
        )
    span: dict[str, object] = {
        "traceId": "a" * 32,
        "spanId": "b" * 16,
        "name": "agent",
        "startTimeUnixNano": "1784600000000000000",
        "endTimeUnixNano": "1784600005000000000",
        "attributes": span_attributes,
    }
    if parent_span_id is not None:
        span["parentSpanId"] = parent_span_id
    spans = [span]
    if include_self_improvement:
        spans.append(
            {
                "traceId": "a" * 32,
                "spanId": "c" * 16,
                "parentSpanId": "b" * 16,
                "name": "tool.skill_manage",
                "startTimeUnixNano": "1784600001000000000",
                "endTimeUnixNano": "1784600002000000000",
                "attributes": [attribute("tool.name", "skill_manage")],
            }
        )
    return {
        "batches": [
            {
                "resource": {
                    "attributes": [
                        attribute("service.name", "backup-secretary-hermes"),
                        attribute("service.instance.id", "main"),
                    ]
                },
                "scopeSpans": [{"spans": spans}],
            }
        ]
    }


class ExtractRecordTests(unittest.TestCase):
    def test_extracts_allowlisted_usage_and_drops_content(self) -> None:
        records = extract_records(
            trace_fixture(),
            expected_service="backup-secretary-hermes",
            instance_prefix="hermes-",
        )

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["source_instance"], "hermes-main")
        self.assertEqual(record["user_id"], "discord:synthetic-user")
        self.assertEqual(record["request_model"], "synthetic-model")
        self.assertEqual(record["response_model"], "synthetic-model-response")
        self.assertIsNone(record["provider"])
        self.assertEqual(record["input_tokens"], 12)
        self.assertEqual(record["output_tokens"], 5)
        self.assertEqual(record["cached_input_tokens"], 7)
        self.assertEqual(record["reasoning_tokens"], 2)
        self.assertEqual(record["total_tokens"], 17)
        serialized = str(record)
        self.assertNotIn("CANARY_PROMPT", serialized)
        self.assertNotIn("CANARY_RESPONSE", serialized)
        self.assertNotIn("CANARY_TOOL_ARGUMENT", serialized)

    def test_derives_total_when_input_and_output_are_present(self) -> None:
        record = extract_records(
            trace_fixture(total_tokens=None),
            expected_service="backup-secretary-hermes",
            instance_prefix="hermes-",
        )[0]

        self.assertEqual(record["total_tokens"], 17)
        self.assertEqual(record["quality"], "derived")

    def test_rejects_descendant_agent_span(self) -> None:
        records = extract_records(
            trace_fixture(parent_span_id="c" * 16),
            expected_service="backup-secretary-hermes",
            instance_prefix="hermes-",
        )
        self.assertEqual(records, [])

    def test_classifies_unattributed_skill_management_as_self_improvement(self) -> None:
        record = extract_records(
            trace_fixture(include_sender=False, include_self_improvement=True),
            expected_service="backup-secretary-hermes",
            instance_prefix="hermes-",
        )[0]

        self.assertEqual(record["user_id"], SYSTEM_SELF_IMPROVEMENT_USER_ID)

    def test_keeps_other_unattributed_turns_unknown(self) -> None:
        record = extract_records(
            trace_fixture(include_sender=False),
            expected_service="backup-secretary-hermes",
            instance_prefix="hermes-",
        )[0]

        self.assertIsNone(record["user_id"])

    def test_sender_attribution_wins_when_skill_management_is_present(self) -> None:
        record = extract_records(
            trace_fixture(include_self_improvement=True),
            expected_service="backup-secretary-hermes",
            instance_prefix="hermes-",
        )[0]

        self.assertEqual(record["user_id"], "discord:synthetic-user")


class SaturatedClient:
    def __init__(self) -> None:
        self.calls: list[tuple[datetime, datetime]] = []

    def search(self, **values):
        start = values["start"]
        end = values["end"]
        self.calls.append((start, end))
        if (end - start).total_seconds() > 60:
            return ["a", "b"]
        return [f"{int(start.timestamp()):x}"]


class CompleteSearchTests(unittest.TestCase):
    def test_splits_a_saturated_search_without_losing_ids(self) -> None:
        client = SaturatedClient()
        start = datetime(2026, 7, 22, tzinfo=timezone.utc)
        result = complete_trace_search(
            client,  # type: ignore[arg-type]
            service_name="backup-secretary-hermes",
            instance="main",
            start=start,
            end=start + timedelta(minutes=4),
            limit=2,
            minimum_split_seconds=30,
        )

        self.assertGreater(len(client.calls), 1)
        self.assertEqual(len(result), 4)


if __name__ == "__main__":
    unittest.main()
