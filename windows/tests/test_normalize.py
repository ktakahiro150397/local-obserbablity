import copy
from datetime import datetime
import importlib.util
import json
from pathlib import Path
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from normalize import records


def kv(values):
    return [{"key": k, "value": {"intValue": str(v)} if isinstance(v,int) else {"stringValue": v}} for k,v in values.items()]


def payload(service="backup-secretary-hermes", name="gen_ai.request", attrs=None, span_id=1):
    return {"resourceSpans": [{"resource": {"attributes": kv({"service.name":service,"service.instance.id":"synthetic"})},
        "scopeSpans":[{"spans":[{"name":name,"traceId":"a"*32,"spanId":f"{span_id:016x}",
        "startTimeUnixNano":"1789563600000000000","endTimeUnixNano":"1789563601000000000",
        "attributes":kv(attrs or {"usage.contract":"hermes.request.v1","usage.user.id":"discord:synthetic-a",
                                  "usage.tokens.input":100,"usage.tokens.output":10,"usage.tokens.cache_read":80,
                                  "usage.tokens.reasoning":5,"usage.tokens.total":999})}]}]}]}


class NormalizeTest(unittest.TestCase):
    def test_subsets_and_retry_dedup_key(self):
        p=payload()
        row=list(records(p))[0]
        self.assertEqual(row["total_tokens"],110)
        self.assertEqual(row["quality"],"reported")
        self.assertEqual(row["event_key"],list(records(copy.deepcopy(p)))[0]["event_key"])
        self.assertNotEqual(row["event_key"],list(records(payload(span_id=2)))[0]["event_key"])

    def test_missing_not_zero_and_zero_is_reported(self):
        for usage,quality,total in [({},"missing",None),({"usage.tokens.input":10},"partial",None),
                                    ({"usage.tokens.input":0,"usage.tokens.output":0},"reported",0)]:
            row=list(records(payload(attrs={"usage.contract":"hermes.request.v1",**usage})))[0]
            self.assertEqual(row["quality"],quality)
            self.assertEqual(row["total_tokens"],total)

    def test_content_status_and_resource_never_retained(self):
        p=payload(attrs={"usage.contract":"hermes.request.v1","input.value":"SECRET_CANARY",
                         "error.message":"SECRET_CANARY","tool.arguments":"SECRET_CANARY"})
        span=p["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
        span.update(events=[{"name":"SECRET_CANARY"}],status={"code":2,"message":"SECRET_CANARY"})
        self.assertNotIn("SECRET_CANARY",json.dumps(list(records(p))))

    def test_root_child_totals_ignored_only_requests_count(self):
        self.assertEqual(list(records(payload(name="agent"))),[])
        self.assertEqual(list(records(payload(name="llm.test"))),[])
        self.assertEqual(len(list(records(payload()))),1)

    def test_cli_turn_and_app_requests_do_not_overlap(self):
        a={"codex.turn.token_usage.input_tokens":25,"codex.turn.token_usage.output_tokens":5}
        row=list(records(payload("codex_exec","session_task.turn",a)))[0]
        self.assertEqual((row["client"],row["granularity"],row["total_tokens"]),("cli","turn",30))
        desktop=list(records(payload("codex-app-server","session_task.turn",a)))[0]
        self.assertEqual((desktop["client"],desktop["granularity"],desktop["total_tokens"]),("desktop","turn",30))
        b={"gen_ai.usage.input_tokens":30,"gen_ai.usage.output_tokens":5}
        self.assertEqual(list(records(payload("codex-app-server","handle_responses",b))),[])
        self.assertEqual(list(records(payload("codex_exec","handle_responses",b))),[])

    def test_other_client_explicit_contract(self):
        row=list(records(payload("synthetic-client","gen_ai.request",{
            "usage.contract":"gen_ai.request.v1","usage.tokens.input":9,"usage.tokens.output":1})))[0]
        self.assertEqual((row["source"],row["client"],row["total_tokens"]),("otlp","synthetic-client",10))
        self.assertEqual(list(records(payload("arbitrary-client"))),[])

    def test_invalid_time_and_identifiers_dropped(self):
        p=payload(); span=p["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
        span["endTimeUnixNano"]="missing"
        self.assertEqual(list(records(p)),[])
        span["endTimeUnixNano"]="1789563601000000000";span["spanId"]="invalid"
        self.assertEqual(list(records(p)),[])


if __name__ == '__main__':
    unittest.main()
