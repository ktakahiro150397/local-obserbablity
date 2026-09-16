"""Content-free OTLP/JSON adapters. Only request facts enter the ledger.

No raw payload, arbitrary attribute dictionary, prompt or exception is retained.
Replayed batches and out-of-order spans use the same immutable source key.
"""
from datetime import datetime, timezone
import hashlib
import re

TOKEN_FIELDS = ("input", "output", "cache_read", "cache_write", "reasoning", "total")
SAFE_TEXT = re.compile(r"^[A-Za-z0-9_.:/@-]{1,200}$")


def attributes(items):
    result = {}
    for item in items or []:
        value = item.get("value", {})
        if "stringValue" in value:
            result[item.get("key")] = value["stringValue"]
        elif "intValue" in value:
            try:
                result[item.get("key")] = int(value["intValue"])
            except (ValueError, TypeError):
                pass
    return result


def text(value, default=None):
    return value if isinstance(value, str) and SAFE_TEXT.fullmatch(value) else default


def integer(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 2**63-1 else None


def timestamp(ns):
    # OTLP nanosecond timestamps are JSON strings; never use receive time as
    # the event time when the producer failed to supply a timestamp.
    try:
        seconds = int(ns) / 1e9
        if not 946684800 <= seconds <= 7258118400:
            return None
        return datetime.fromtimestamp(seconds, timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def records(payload):
    for resource_spans in payload.get("resourceSpans", []):
        resource = attributes(resource_spans.get("resource", {}).get("attributes"))
        service = resource.get("service.name")
        instance = text(resource.get("service.instance.id"), "default")
        for scope in resource_spans.get("scopeSpans", []):
            for span in scope.get("spans", []):
                a = attributes(span.get("attributes"))
                name = span.get("name")
                source = client = granularity = None
                contract = a.get("usage.contract")
                if service == "backup-secretary-hermes" and contract == "hermes.request.v1" and name == "gen_ai.request":
                    source, client, granularity = "hermes", "hermes", "request"
                    tokens = {k: integer(a.get("usage.tokens." + k)) for k in TOKEN_FIELDS}
                elif service in {"codex_exec", "codex-app-server", "Codex Desktop"}:
                    # Schema observed in the existing verification ledger. Do
                    # not add turn totals to request usage from the same client.
                    source = "codex"
                    client = "cli" if service == "codex_exec" else "desktop"
                    if name == "session_task.turn":
                        granularity = "turn"
                        keys = {"input": "input_tokens", "output": "output_tokens", "total": "total_tokens",
                                "cache_read": "cached_input_tokens", "cache_write": "cache_write_input_tokens",
                                "reasoning": "reasoning_output_tokens"}
                        tokens = {k: integer(a.get("codex.turn.token_usage." + keys[k])) if k in keys else None for k in TOKEN_FIELDS}
                    else:
                        continue
                elif contract == "gen_ai.request.v1" and name == "gen_ai.request":
                    source, client, granularity = "otlp", text(service, "unknown"), "request"
                    tokens = {k: integer(a.get("usage.tokens." + k)) for k in TOKEN_FIELDS}
                else:
                    continue
                trace, sid = span.get("traceId", ""), span.get("spanId", "")
                if not re.fullmatch(r"[0-9a-fA-F]{32}", trace) or not re.fullmatch(r"[0-9a-fA-F]{16}", sid):
                    continue
                if int(trace,16)==0 or int(sid,16)==0:
                    continue
                occurred = timestamp(span.get("endTimeUnixNano"))
                started = timestamp(span.get("startTimeUnixNano"))
                if not occurred or not started or int(span["endTimeUnixNano"]) < int(span["startTimeUnixNano"]):
                    continue
                # Input includes cache; output includes reasoning. Recompute
                # total only from those two buckets, never sum every column.
                if tokens["input"] is not None and tokens["output"] is not None:
                    total = tokens["input"] + tokens["output"]
                    if total > 2**63-1:
                        continue
                    tokens["total"] = total
                quality = "reported" if tokens["input"] is not None and tokens["output"] is not None else (
                    "partial" if any(v is not None for v in tokens.values()) else "missing")
                user = text(a.get("usage.user.id"), "unattributed") if source == "hermes" else "local"
                if user not in {"system", "unattributed"} and source == "hermes" and not user.startswith("discord:"):
                    user = "unattributed"
                yield dict(
                    event_key=hashlib.sha256(f"{source}:{instance}:{trace.lower()}:{sid.lower()}".encode()).hexdigest(),
                    source=source, client=client, instance=instance,
                    profile=text(a.get("usage.profile")), user_id=user,
                    channel_id=text(a.get("usage.channel.id")), thread_id=text(a.get("usage.thread.id")),
                    session_id=text(a.get("usage.session.id") or a.get("conversation.id") or a.get("gen_ai.conversation.id") or (
                        a.get("thread.id") if source == "codex" and re.fullmatch(r"[0-9a-fA-F-]{36}",str(a.get("thread.id",""))) else None)),
                    turn_id=text(a.get("usage.turn.id") or a.get("turn.id")),
                    request_id=text(a.get("usage.request.id")), parent_turn_id=text(a.get("usage.parent.turn.id")),
                    provider=text(a.get("gen_ai.provider.name") or a.get("gen_ai.system")),
                    model=text(a.get("gen_ai.response.model") or a.get("gen_ai.request.model") or a.get("model")),
                    granularity=granularity, quality=quality,
                    outcome=a.get("usage.outcome") if a.get("usage.outcome") in {"ok", "error", "unknown"} else (
                        "error" if span.get("status", {}).get("code") == 2 else "unknown"),
                    retry=integer(a.get("usage.retry")) if isinstance(a.get("usage.retry"),int) and a["usage.retry"]<=2**31-1 else None,
                    started_at=started, occurred_at=occurred,
                    **{k + "_tokens": v for k, v in tokens.items()})
