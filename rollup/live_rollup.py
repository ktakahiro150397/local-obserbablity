from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    import psycopg
except ImportError:  # Unit tests for parsing do not require the database driver.
    psycopg = None


PARSER_NAME = "hermes-tempo-live-rollup"
PARSER_VERSION = "1.0.0"
RECORD_NAMESPACE = uuid.UUID("3b36c86c-3502-5ac5-9864-044bc977e311")
RUN_NAMESPACE = uuid.UUID("825648c5-6122-5778-b8ab-d8db832ef95b")
LIVE_SOURCE_HASH = hashlib.sha256(b"tempo-live-rollup:v1").hexdigest()
SAFE_INSTANCE = re.compile(r"^[A-Za-z0-9_.-]+$")
ROOT_PARENT_IDS = {None, "", "0" * 16, "0" * 32}
TRANSPORT_PROVIDERS = {"discord", "telegram", "gateway"}

TOKEN_KEYS = {
    "input_tokens": (
        "gen_ai.usage.input_tokens",
        "llm.token_count.prompt",
    ),
    "output_tokens": (
        "gen_ai.usage.output_tokens",
        "llm.token_count.completion",
    ),
    "total_tokens": (
        "gen_ai.usage.total_tokens",
        "llm.token_count.total",
    ),
    "cached_input_tokens": (
        "gen_ai.usage.cache_read.input_tokens",
        "gen_ai.usage.cache_read_input_tokens",
        "llm.token_count.prompt_details.cache_read",
    ),
    "cache_write_tokens": (
        "gen_ai.usage.cache_creation.input_tokens",
        "gen_ai.usage.cache_write.input_tokens",
        "gen_ai.usage.cache_write_input_tokens",
        "llm.token_count.prompt_details.cache_write",
    ),
    "reasoning_tokens": (
        "gen_ai.usage.reasoning.output_tokens",
        "llm.token_count.completion_details.reasoning",
    ),
}


class RollupError(RuntimeError):
    pass


class TempoError(RollupError):
    pass


def _int_env(name: str, default: int, *, minimum: int = 1) -> int:
    value = int(os.environ.get(name, str(default)))
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


@dataclass(frozen=True)
class Settings:
    tempo_url: str
    postgres_host: str
    postgres_port: int
    postgres_database: str
    postgres_user: str
    postgres_password_file: Path
    service_name: str
    instances: tuple[str, ...]
    ledger_instance_prefix: str
    interval_seconds: int
    overlap_seconds: int
    grace_seconds: int
    max_window_seconds: int
    search_limit: int
    minimum_split_seconds: int
    http_timeout_seconds: int
    health_file: Path

    @classmethod
    def from_env(cls) -> "Settings":
        instances = tuple(
            part.strip()
            for part in os.environ.get("ROLLUP_INSTANCES", "main,owashota").split(",")
            if part.strip()
        )
        if not instances or any(not SAFE_INSTANCE.fullmatch(item) for item in instances):
            raise ValueError("ROLLUP_INSTANCES contains an invalid instance name")
        tempo_url = os.environ.get("TEMPO_URL", "http://shared-lgtm:3200").rstrip("/")
        if not tempo_url.startswith(("http://", "https://")):
            raise ValueError("TEMPO_URL must use http or https")
        return cls(
            tempo_url=tempo_url,
            postgres_host=os.environ.get("POSTGRES_HOST", "shared-ledger"),
            postgres_port=_int_env("POSTGRES_PORT", 5432),
            postgres_database=os.environ.get("POSTGRES_DB", "usage_ledger"),
            postgres_user=os.environ.get("POSTGRES_USER", "ledger_writer"),
            postgres_password_file=Path(
                os.environ.get(
                    "POSTGRES_PASSWORD_FILE", "/run/secrets/ledger_writer_password"
                )
            ),
            service_name=os.environ.get(
                "ROLLUP_SERVICE_NAME", "backup-secretary-hermes"
            ),
            instances=instances,
            ledger_instance_prefix=os.environ.get(
                "ROLLUP_LEDGER_INSTANCE_PREFIX", "hermes-"
            ),
            interval_seconds=_int_env("ROLLUP_INTERVAL_SECONDS", 300),
            overlap_seconds=_int_env("ROLLUP_OVERLAP_SECONDS", 1800, minimum=0),
            grace_seconds=_int_env("ROLLUP_GRACE_SECONDS", 120, minimum=0),
            max_window_seconds=_int_env("ROLLUP_MAX_WINDOW_SECONDS", 7200),
            search_limit=_int_env("ROLLUP_SEARCH_LIMIT", 1000),
            minimum_split_seconds=_int_env("ROLLUP_MINIMUM_SPLIT_SECONDS", 60),
            http_timeout_seconds=_int_env("ROLLUP_HTTP_TIMEOUT_SECONDS", 30),
            health_file=Path(
                os.environ.get("ROLLUP_HEALTH_FILE", "/tmp/rollup-last-success")
            ),
        )


def _log(event: str, **fields: Any) -> None:
    print(
        json.dumps({"event": event, **fields}, sort_keys=True, separators=(",", ":")),
        flush=True,
    )


def _otel_value(encoded: Any) -> Any:
    if not isinstance(encoded, dict):
        return None
    for key in ("stringValue", "intValue", "doubleValue", "boolValue"):
        if key in encoded:
            return encoded[key]
    return None


def _attributes(items: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if not isinstance(items, list):
        return result
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("key"), str):
            continue
        result[item["key"]] = _otel_value(item.get("value"))
    return result


def _first_text(attributes: dict[str, Any], keys: Iterable[str]) -> str | None:
    for key in keys:
        value = attributes.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _first_nonnegative_int(
    attributes: dict[str, Any], keys: Iterable[str]
) -> int | None:
    for key in keys:
        value = attributes.get(key)
        if value is None or isinstance(value, bool):
            continue
        try:
            integer = int(value)
        except (TypeError, ValueError):
            continue
        if integer >= 0 and str(integer) == str(value).split(".", 1)[0]:
            return integer
    return None


def _utc_from_nanos(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        nanos = int(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(nanos / 1_000_000_000, timezone.utc)


def _canonical_hash(value: dict[str, Any]) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=lambda item: item.isoformat() if isinstance(item, datetime) else str(item),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _opaque_id(*parts: Any) -> str:
    return hashlib.sha256(
        json.dumps(parts, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _run_id(source_instance: str) -> uuid.UUID:
    return uuid.uuid5(RUN_NAMESPACE, f"hermes:{source_instance}:live_rollup")


def extract_records(
    trace: dict[str, Any], *, expected_service: str, instance_prefix: str
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for batch in trace.get("batches", []):
        resource = _attributes(batch.get("resource", {}).get("attributes"))
        if resource.get("service.name") != expected_service:
            continue
        tempo_instance = _first_text(resource, ("service.instance.id",))
        if tempo_instance is None or not SAFE_INSTANCE.fullmatch(tempo_instance):
            continue
        source_instance = f"{instance_prefix}{tempo_instance}"
        for scope in batch.get("scopeSpans", []):
            for span in scope.get("spans", []):
                if span.get("name") != "agent" or span.get("parentSpanId") not in ROOT_PARENT_IDS:
                    continue
                attributes = _attributes(span.get("attributes"))
                token_values = {
                    name: _first_nonnegative_int(attributes, keys)
                    for name, keys in TOKEN_KEYS.items()
                }
                if token_values["total_tokens"] is None:
                    if (
                        token_values["input_tokens"] is None
                        or token_values["output_tokens"] is None
                    ):
                        continue
                    token_values["total_tokens"] = (
                        token_values["input_tokens"] + token_values["output_tokens"]
                    )
                    quality = "derived"
                    quality_reason = "tempo_root_agent_total_derived"
                else:
                    quality = "exact"
                    quality_reason = "tempo_root_agent"

                period_start = _utc_from_nanos(span.get("startTimeUnixNano"))
                period_end = _utc_from_nanos(span.get("endTimeUnixNano"))
                if period_start is None or period_end is None or period_end < period_start:
                    continue

                user_id = _first_text(attributes, ("user.id",))
                if user_id is None:
                    sender_id = _first_text(attributes, ("hermes.sender.id",))
                    if sender_id is not None:
                        user_id = f"discord:{sender_id}"

                provider = _first_text(
                    attributes,
                    ("gen_ai.provider.name", "llm.provider", "gen_ai.system"),
                )
                if provider is not None and provider.lower() in TRANSPORT_PROVIDERS:
                    provider = None

                trace_id = str(span.get("traceId") or "")
                span_id = str(span.get("spanId") or "")
                if not trace_id or not span_id:
                    continue
                source_record_id = _opaque_id("tempo", trace_id, span_id)
                stable_key = (
                    f"hermes:{source_instance}:live_rollup:{source_record_id}"
                )
                record = {
                    "record_id": uuid.uuid5(RECORD_NAMESPACE, stable_key),
                    "record_origin": "live_rollup",
                    "source_system": "hermes",
                    "source_instance": source_instance,
                    "source_record_id": source_record_id,
                    "source_record_hash": "",
                    "source_snapshot_hash": LIVE_SOURCE_HASH,
                    "parser_name": PARSER_NAME,
                    "parser_version": PARSER_VERSION,
                    "import_run_id": _run_id(source_instance),
                    "occurred_at": period_end,
                    "period_start": period_start,
                    "period_end": period_end,
                    "record_granularity": "turn",
                    "user_id": user_id,
                    "request_model": _first_text(
                        attributes,
                        ("gen_ai.request.model", "llm.model_name"),
                    ),
                    "response_model": _first_text(
                        attributes,
                        ("gen_ai.response.model", "gen_ai.request.model", "llm.model_name"),
                    ),
                    "provider": provider,
                    **token_values,
                    "estimated_cost_usd": None,
                    "actual_cost_usd": None,
                    "cost_quality": "unknown",
                    "pricing_version": None,
                    "quality": quality,
                    "quality_reason": quality_reason,
                    "shared_eligible": True,
                }
                hash_input = {
                    key: value
                    for key, value in record.items()
                    if key not in {"record_id", "source_record_hash", "import_run_id"}
                }
                record["source_record_hash"] = _canonical_hash(hash_input)
                records.append(record)
    return records


class TempoClient:
    def __init__(self, base_url: str, timeout_seconds: int):
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds

    def _get_json(self, path: str, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        if parameters:
            url = f"{url}?{urlencode(parameters)}"
        request = Request(url, headers={"Accept": "application/json"})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return json.load(response)
        except HTTPError as error:
            raise TempoError(f"Tempo HTTP {error.code}") from None
        except (URLError, TimeoutError, json.JSONDecodeError):
            raise TempoError("Tempo request failed") from None

    def search(
        self,
        *,
        service_name: str,
        instance: str,
        start: datetime,
        end: datetime,
        limit: int,
    ) -> list[str]:
        query = (
            f'{{ resource.service.name = "{service_name}" '
            f'&& resource."service.instance.id" = "{instance}" '
            '&& span:name = "agent" '
            '&& span."gen_ai.usage.total_tokens" != nil }'
        )
        payload = self._get_json(
            "/api/search",
            {
                "q": query,
                "start": int(start.timestamp()),
                "end": int(end.timestamp()),
                "limit": limit,
            },
        )
        return sorted(
            {
                str(item["traceID"])
                for item in payload.get("traces", [])
                if isinstance(item, dict) and item.get("traceID")
            }
        )

    def trace(self, trace_id: str) -> dict[str, Any]:
        if not re.fullmatch(r"[A-Fa-f0-9]+", trace_id):
            raise TempoError("Tempo returned an invalid trace identifier")
        return self._get_json(f"/api/traces/{trace_id}")


def complete_trace_search(
    client: TempoClient,
    *,
    service_name: str,
    instance: str,
    start: datetime,
    end: datetime,
    limit: int,
    minimum_split_seconds: int,
) -> list[str]:
    trace_ids = client.search(
        service_name=service_name,
        instance=instance,
        start=start,
        end=end,
        limit=limit,
    )
    if len(trace_ids) < limit:
        return trace_ids
    duration = (end - start).total_seconds()
    if duration <= minimum_split_seconds:
        raise TempoError("Tempo search limit remains saturated at minimum window")
    midpoint = start + (end - start) / 2
    left = complete_trace_search(
        client,
        service_name=service_name,
        instance=instance,
        start=start,
        end=midpoint,
        limit=limit,
        minimum_split_seconds=minimum_split_seconds,
    )
    right = complete_trace_search(
        client,
        service_name=service_name,
        instance=instance,
        start=midpoint,
        end=end,
        limit=limit,
        minimum_split_seconds=minimum_split_seconds,
    )
    return sorted(set(left) | set(right))


UPSERT_SQL = """
INSERT INTO usage.usage_records (
  record_id,record_origin,source_system,source_instance,source_record_id,
  source_record_hash,source_snapshot_hash,parser_name,parser_version,import_run_id,
  occurred_at,period_start,period_end,record_granularity,user_id,request_model,
  response_model,provider,input_tokens,output_tokens,cached_input_tokens,
  cache_write_tokens,reasoning_tokens,total_tokens,estimated_cost_usd,
  actual_cost_usd,cost_quality,pricing_version,quality,quality_reason,shared_eligible
) VALUES (
  %(record_id)s,%(record_origin)s,%(source_system)s,%(source_instance)s,%(source_record_id)s,
  %(source_record_hash)s,%(source_snapshot_hash)s,%(parser_name)s,%(parser_version)s,%(import_run_id)s,
  %(occurred_at)s,%(period_start)s,%(period_end)s,%(record_granularity)s,%(user_id)s,%(request_model)s,
  %(response_model)s,%(provider)s,%(input_tokens)s,%(output_tokens)s,%(cached_input_tokens)s,
  %(cache_write_tokens)s,%(reasoning_tokens)s,%(total_tokens)s,%(estimated_cost_usd)s,
  %(actual_cost_usd)s,%(cost_quality)s,%(pricing_version)s,%(quality)s,%(quality_reason)s,%(shared_eligible)s
)
ON CONFLICT (source_system,source_instance,record_origin,source_record_id)
DO UPDATE SET
  source_record_hash=EXCLUDED.source_record_hash,
  source_snapshot_hash=EXCLUDED.source_snapshot_hash,
  parser_name=EXCLUDED.parser_name,
  parser_version=EXCLUDED.parser_version,
  occurred_at=EXCLUDED.occurred_at,
  period_start=EXCLUDED.period_start,
  period_end=EXCLUDED.period_end,
  record_granularity=EXCLUDED.record_granularity,
  user_id=EXCLUDED.user_id,
  request_model=EXCLUDED.request_model,
  response_model=EXCLUDED.response_model,
  provider=EXCLUDED.provider,
  input_tokens=EXCLUDED.input_tokens,
  output_tokens=EXCLUDED.output_tokens,
  cached_input_tokens=EXCLUDED.cached_input_tokens,
  cache_write_tokens=EXCLUDED.cache_write_tokens,
  reasoning_tokens=EXCLUDED.reasoning_tokens,
  total_tokens=EXCLUDED.total_tokens,
  estimated_cost_usd=EXCLUDED.estimated_cost_usd,
  actual_cost_usd=EXCLUDED.actual_cost_usd,
  cost_quality=EXCLUDED.cost_quality,
  pricing_version=EXCLUDED.pricing_version,
  quality=EXCLUDED.quality,
  quality_reason=EXCLUDED.quality_reason,
  shared_eligible=EXCLUDED.shared_eligible,
  imported_at=CURRENT_TIMESTAMP
WHERE usage.usage_records.source_record_hash IS DISTINCT FROM EXCLUDED.source_record_hash
RETURNING (xmax = 0) AS inserted
"""


class RollupWorker:
    def __init__(self, settings: Settings, tempo: TempoClient):
        if psycopg is None:
            raise RollupError("psycopg is required to run the rollup worker")
        self.settings = settings
        self.tempo = tempo

    def _connect(self):
        password = self.settings.postgres_password_file.read_text(
            encoding="utf-8"
        ).strip()
        if not password:
            raise RollupError("ledger writer password file is empty")
        return psycopg.connect(
            host=self.settings.postgres_host,
            port=self.settings.postgres_port,
            dbname=self.settings.postgres_database,
            user=self.settings.postgres_user,
            password=password,
            connect_timeout=10,
            application_name=PARSER_NAME,
        )

    def _position(self, source_instance: str) -> tuple[datetime | None, datetime | None]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT c.cutover_at, p.checkpoint_at
                FROM usage.cutovers c
                LEFT JOIN usage.live_rollup_checkpoints p
                  USING (source_system, source_instance)
                WHERE c.source_system='hermes' AND c.source_instance=%s
                """,
                (source_instance,),
            )
            row = cursor.fetchone()
        if row is None:
            return None, None
        return row[0], row[1]

    def _write_window(
        self,
        *,
        source_instance: str,
        cutover: datetime,
        checkpoint: datetime,
        records: list[dict[str, Any]],
    ) -> tuple[int, int, int]:
        run_id = _run_id(source_instance)
        inserted = updated = skipped = 0
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"hermes:{source_instance}:live_rollup",),
            )
            cursor.execute(
                """
                SELECT cutover_at FROM usage.cutovers
                WHERE source_system='hermes' AND source_instance=%s
                FOR SHARE
                """,
                (source_instance,),
            )
            row = cursor.fetchone()
            if row is None or row[0] != cutover:
                raise RollupError("approved cutover changed during live rollup")
            if any(
                record["source_instance"] != source_instance
                or record["occurred_at"] < cutover
                for record in records
            ):
                raise RollupError("live record crosses the approved cutover boundary")

            if records:
                cursor.execute(
                    """
                    INSERT INTO usage.import_runs(
                      import_run_id,source_system,source_instance,parser_name,parser_version,
                      source_snapshot_hash,status,finished_at
                    ) VALUES (%s,'hermes',%s,%s,%s,%s,'complete',CURRENT_TIMESTAMP)
                    ON CONFLICT (import_run_id) DO UPDATE SET
                      parser_version=EXCLUDED.parser_version,
                      status='complete',
                      finished_at=CURRENT_TIMESTAMP
                    """,
                    (
                        run_id,
                        source_instance,
                        PARSER_NAME,
                        PARSER_VERSION,
                        LIVE_SOURCE_HASH,
                    ),
                )
                for record in records:
                    cursor.execute(UPSERT_SQL, record)
                    result = cursor.fetchone()
                    if result is None:
                        skipped += 1
                    elif result[0]:
                        inserted += 1
                    else:
                        updated += 1
                cursor.execute(
                    """
                    UPDATE usage.import_runs SET
                      inserted_count=(
                        SELECT count(*) FROM usage.usage_records WHERE import_run_id=%s
                      ),
                      updated_count=updated_count + %s,
                      skipped_count=skipped_count + %s,
                      error_count=0,
                      finished_at=CURRENT_TIMESTAMP
                    WHERE import_run_id=%s
                    """,
                    (run_id, updated, skipped, run_id),
                )

            cursor.execute(
                """
                INSERT INTO usage.live_rollup_checkpoints(
                  source_system,source_instance,checkpoint_at,last_success_at,last_run_id
                ) VALUES ('hermes',%s,%s,CURRENT_TIMESTAMP,%s)
                ON CONFLICT (source_system,source_instance) DO UPDATE SET
                  checkpoint_at=GREATEST(
                    usage.live_rollup_checkpoints.checkpoint_at,
                    EXCLUDED.checkpoint_at
                  ),
                  last_success_at=CURRENT_TIMESTAMP,
                  last_run_id=COALESCE(EXCLUDED.last_run_id,usage.live_rollup_checkpoints.last_run_id)
                """,
                (source_instance, checkpoint, run_id if records else None),
            )
        return inserted, updated, skipped

    def run_instance(self, instance: str, now: datetime) -> dict[str, Any]:
        source_instance = f"{self.settings.ledger_instance_prefix}{instance}"
        cutover, prior_checkpoint = self._position(source_instance)
        if cutover is None:
            return {"instance": instance, "status": "waiting_for_cutover"}
        target = now - timedelta(seconds=self.settings.grace_seconds)
        if target <= cutover:
            return {"instance": instance, "status": "waiting_for_live_window"}
        base = prior_checkpoint or cutover
        start = max(cutover, base - timedelta(seconds=self.settings.overlap_seconds))
        end = min(
            target,
            start + timedelta(seconds=self.settings.max_window_seconds),
        )
        trace_ids = complete_trace_search(
            self.tempo,
            service_name=self.settings.service_name,
            instance=instance,
            start=start,
            end=end,
            limit=self.settings.search_limit,
            minimum_split_seconds=self.settings.minimum_split_seconds,
        )
        by_record_id: dict[str, dict[str, Any]] = {}
        for trace_id in trace_ids:
            trace = self.tempo.trace(trace_id)
            for record in extract_records(
                trace,
                expected_service=self.settings.service_name,
                instance_prefix=self.settings.ledger_instance_prefix,
            ):
                if (
                    record["source_instance"] == source_instance
                    and record["occurred_at"] >= cutover
                ):
                    by_record_id[record["source_record_id"]] = record
        records = list(by_record_id.values())
        inserted, updated, skipped = self._write_window(
            source_instance=source_instance,
            cutover=cutover,
            checkpoint=end,
            records=records,
        )
        caught_up = end >= target
        return {
            "instance": instance,
            "status": "caught_up" if caught_up else "catching_up",
            "traces": len(trace_ids),
            "records": len(records),
            "inserted": inserted,
            "updated": updated,
            "skipped": skipped,
        }

    def run_cycle(self) -> bool:
        now = datetime.now(timezone.utc)
        success = True
        for instance in self.settings.instances:
            try:
                result = self.run_instance(instance, now)
                _log("rollup_window", **result)
            except Exception as error:
                success = False
                _log(
                    "rollup_error",
                    instance=instance,
                    error_class=type(error).__name__,
                )
        if success:
            self.settings.health_file.write_text(
                now.isoformat() + "\n", encoding="utf-8"
            )
        return success


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Roll up content-free Hermes spans")
    parser.add_argument("--once", action="store_true", help="run one cycle and exit")
    args = parser.parse_args(argv)
    settings = Settings.from_env()
    worker = RollupWorker(
        settings,
        TempoClient(settings.tempo_url, settings.http_timeout_seconds),
    )
    if args.once:
        return 0 if worker.run_cycle() else 1

    stopped = Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    _log(
        "rollup_started",
        interval_seconds=settings.interval_seconds,
        overlap_seconds=settings.overlap_seconds,
        instances=len(settings.instances),
    )
    while not stopped.is_set():
        worker.run_cycle()
        stopped.wait(settings.interval_seconds)
    _log("rollup_stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
