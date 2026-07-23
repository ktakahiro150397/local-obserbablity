from __future__ import annotations

import argparse
import hashlib
import os
import re
import signal
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event
from typing import Any

from live_rollup import (
    RollupError,
    TempoClient,
    TempoError,
    _attributes,
    _canonical_hash,
    _first_nonnegative_int,
    _first_text,
    _log,
    _opaque_id,
    _utc_from_nanos,
    psycopg,
)


PARSER_NAME = "codex-tempo-live-rollup"
PARSER_VERSION = "1.0.0"
RECORD_NAMESPACE = uuid.UUID("6f875a12-f2db-5c83-adf1-49542e2bd989")
RUN_NAMESPACE = uuid.UUID("f0c06121-6176-59bc-809c-12d79a95b9bd")
LIVE_SOURCE_HASH = hashlib.sha256(b"codex-tempo-live-rollup:v1").hexdigest()
SAFE_INSTANCE = re.compile(r"^[A-Za-z0-9_.-]+$")
SAFE_SERVICE = re.compile(r"^[A-Za-z0-9_. -]+$")

TOKEN_KEYS = {
    "input_tokens": ("codex.turn.token_usage.input_tokens",),
    "output_tokens": ("codex.turn.token_usage.output_tokens",),
    "total_tokens": ("codex.turn.token_usage.total_tokens",),
    "cached_input_tokens": ("codex.turn.token_usage.cached_input_tokens",),
    "cache_write_tokens": ("codex.turn.token_usage.cache_write_input_tokens",),
    "reasoning_tokens": ("codex.turn.token_usage.reasoning_output_tokens",),
}

CLIENT_BY_SERVICE = {
    "codex_exec": "cli",
    "codex-app-server": "desktop",
    "Codex Desktop": "desktop-subprocess",
}


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
    source_instance: str
    service_names: tuple[str, ...]
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
        source_instance = os.environ.get(
            "ROLLUP_SOURCE_INSTANCE", "main-windows"
        ).strip()
        if not SAFE_INSTANCE.fullmatch(source_instance):
            raise ValueError("ROLLUP_SOURCE_INSTANCE contains an invalid value")
        service_names = tuple(
            part.strip()
            for part in os.environ.get(
                "ROLLUP_SERVICE_NAMES",
                "codex_exec,codex-app-server,Codex Desktop",
            ).split(",")
            if part.strip()
        )
        if not service_names or any(
            not SAFE_SERVICE.fullmatch(item) for item in service_names
        ):
            raise ValueError("ROLLUP_SERVICE_NAMES contains an invalid value")
        tempo_url = os.environ.get(
            "TEMPO_URL", "http://private-lgtm:3200"
        ).rstrip("/")
        if not tempo_url.startswith(("http://", "https://")):
            raise ValueError("TEMPO_URL must use http or https")
        return cls(
            tempo_url=tempo_url,
            postgres_host=os.environ.get("POSTGRES_HOST", "private-ledger"),
            postgres_port=_int_env("POSTGRES_PORT", 5432),
            postgres_database=os.environ.get("POSTGRES_DB", "usage_ledger"),
            postgres_user=os.environ.get("POSTGRES_USER", "ledger_writer"),
            postgres_password_file=Path(
                os.environ.get(
                    "POSTGRES_PASSWORD_FILE",
                    "/run/secrets/ledger_writer_password",
                )
            ),
            source_instance=source_instance,
            service_names=service_names,
            interval_seconds=_int_env("ROLLUP_INTERVAL_SECONDS", 300),
            overlap_seconds=_int_env(
                "ROLLUP_OVERLAP_SECONDS", 1800, minimum=0
            ),
            grace_seconds=_int_env("ROLLUP_GRACE_SECONDS", 120, minimum=0),
            max_window_seconds=_int_env("ROLLUP_MAX_WINDOW_SECONDS", 7200),
            search_limit=_int_env("ROLLUP_SEARCH_LIMIT", 1000),
            minimum_split_seconds=_int_env(
                "ROLLUP_MINIMUM_SPLIT_SECONDS", 60
            ),
            http_timeout_seconds=_int_env(
                "ROLLUP_HTTP_TIMEOUT_SECONDS", 30
            ),
            health_file=Path(
                os.environ.get(
                    "ROLLUP_HEALTH_FILE", "/tmp/codex-rollup-last-success"
                )
            ),
        )


def _run_id(source_instance: str) -> uuid.UUID:
    return uuid.uuid5(
        RUN_NAMESPACE, f"codex:{source_instance}:live_rollup"
    )


def extract_records(
    trace: dict[str, Any],
    *,
    expected_services: tuple[str, ...],
    source_instance: str,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen_spans: set[tuple[str, str]] = set()
    allowed_services = set(expected_services)

    for batch in trace.get("batches", []):
        resource = _attributes(batch.get("resource", {}).get("attributes"))
        service_name = _first_text(resource, ("service.name",))
        if service_name not in allowed_services:
            continue
        for scope in batch.get("scopeSpans", []):
            for span in scope.get("spans", []):
                if span.get("name") != "session_task.turn":
                    continue
                trace_id = str(span.get("traceId") or "")
                span_id = str(span.get("spanId") or "")
                span_key = (trace_id, span_id)
                if not trace_id or not span_id or span_key in seen_spans:
                    continue
                seen_spans.add(span_key)

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
                        token_values["input_tokens"]
                        + token_values["output_tokens"]
                    )
                    quality = "derived"
                    quality_reason = "tempo_codex_turn_total_derived"
                else:
                    quality = "exact"
                    quality_reason = "tempo_codex_turn"

                period_start = _utc_from_nanos(
                    span.get("startTimeUnixNano")
                )
                period_end = _utc_from_nanos(span.get("endTimeUnixNano"))
                if (
                    period_start is None
                    or period_end is None
                    or period_end < period_start
                ):
                    continue

                model = _first_text(
                    attributes,
                    (
                        "model",
                        "gen_ai.response.model",
                        "gen_ai.request.model",
                    ),
                )
                source_record_id = _opaque_id(
                    "tempo", trace_id, span_id
                )
                stable_key = (
                    f"codex:{source_instance}:live_rollup:{source_record_id}"
                )
                record = {
                    "record_id": uuid.uuid5(RECORD_NAMESPACE, stable_key),
                    "record_origin": "live_rollup",
                    "source_system": "codex",
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
                    "user_id": None,
                    "request_model": model,
                    "response_model": model,
                    "provider": None,
                    "client": CLIENT_BY_SERVICE[service_name],
                    **token_values,
                    "estimated_cost_usd": None,
                    "actual_cost_usd": None,
                    "cost_quality": "unknown",
                    "pricing_version": None,
                    "quality": quality,
                    "quality_reason": quality_reason,
                    "shared_eligible": False,
                }
                hash_input = {
                    key: value
                    for key, value in record.items()
                    if key
                    not in {
                        "record_id",
                        "source_record_hash",
                        "import_run_id",
                    }
                }
                record["source_record_hash"] = _canonical_hash(hash_input)
                records.append(record)
    return records


class CodexTempoClient(TempoClient):
    def search(
        self,
        *,
        service_name: str,
        instance: str,
        start: datetime,
        end: datetime,
        limit: int,
    ) -> list[str]:
        del instance
        query = (
            f'{{ resource.service.name =~ "{service_name}" '
            '&& span:name = "session_task.turn" '
            '&& span."codex.turn.token_usage.total_tokens" != nil }'
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


def complete_codex_trace_search(
    client: CodexTempoClient,
    *,
    service_name: str,
    instance: str,
    start: datetime,
    end: datetime,
    limit: int,
    minimum_split_seconds: int,
) -> list[str]:
    try:
        trace_ids = client.search(
            service_name=service_name,
            instance=instance,
            start=start,
            end=end,
            limit=limit,
        )
    except TempoError:
        trace_ids = None
    if trace_ids is not None and len(trace_ids) < limit:
        return trace_ids
    duration = (end - start).total_seconds()
    if duration <= minimum_split_seconds:
        if trace_ids is None:
            raise TempoError(
                "Tempo search timed out at the minimum Codex window"
            )
        raise TempoError(
            "Tempo search limit remains saturated at the minimum Codex window"
        )
    midpoint = start + (end - start) / 2
    left = complete_codex_trace_search(
        client,
        service_name=service_name,
        instance=instance,
        start=start,
        end=midpoint,
        limit=limit,
        minimum_split_seconds=minimum_split_seconds,
    )
    right = complete_codex_trace_search(
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
  response_model,provider,client,input_tokens,output_tokens,cached_input_tokens,
  cache_write_tokens,reasoning_tokens,total_tokens,estimated_cost_usd,
  actual_cost_usd,cost_quality,pricing_version,quality,quality_reason,shared_eligible
) VALUES (
  %(record_id)s,%(record_origin)s,%(source_system)s,%(source_instance)s,%(source_record_id)s,
  %(source_record_hash)s,%(source_snapshot_hash)s,%(parser_name)s,%(parser_version)s,%(import_run_id)s,
  %(occurred_at)s,%(period_start)s,%(period_end)s,%(record_granularity)s,%(user_id)s,%(request_model)s,
  %(response_model)s,%(provider)s,%(client)s,%(input_tokens)s,%(output_tokens)s,%(cached_input_tokens)s,
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
  client=EXCLUDED.client,
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


class CodexRollupWorker:
    def __init__(self, settings: Settings, tempo: CodexTempoClient):
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

    def _position(self) -> tuple[datetime | None, datetime | None]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT c.cutover_at, p.checkpoint_at
                FROM usage.cutovers c
                LEFT JOIN usage.live_rollup_checkpoints p
                  USING (source_system, source_instance)
                WHERE c.source_system='codex' AND c.source_instance=%s
                """,
                (self.settings.source_instance,),
            )
            row = cursor.fetchone()
        if row is None:
            return None, None
        return row[0], row[1]

    def _write_window(
        self,
        *,
        cutover: datetime,
        checkpoint: datetime,
        records: list[dict[str, Any]],
    ) -> tuple[int, int, int]:
        source_instance = self.settings.source_instance
        run_id = _run_id(source_instance)
        inserted = updated = skipped = 0
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"codex:{source_instance}:live_rollup",),
            )
            cursor.execute(
                """
                SELECT cutover_at FROM usage.cutovers
                WHERE source_system='codex' AND source_instance=%s
                FOR SHARE
                """,
                (source_instance,),
            )
            row = cursor.fetchone()
            if row is None or row[0] != cutover:
                raise RollupError(
                    "approved cutover changed during live rollup"
                )
            if any(
                record["source_instance"] != source_instance
                or record["occurred_at"] < cutover
                or record["shared_eligible"]
                for record in records
            ):
                raise RollupError(
                    "live record violates the private cutover boundary"
                )

            if records:
                cursor.execute(
                    """
                    INSERT INTO usage.import_runs(
                      import_run_id,source_system,source_instance,parser_name,parser_version,
                      source_snapshot_hash,status,finished_at
                    ) VALUES (%s,'codex',%s,%s,%s,%s,'complete',CURRENT_TIMESTAMP)
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
                ) VALUES ('codex',%s,%s,CURRENT_TIMESTAMP,%s)
                ON CONFLICT (source_system,source_instance) DO UPDATE SET
                  checkpoint_at=GREATEST(
                    usage.live_rollup_checkpoints.checkpoint_at,
                    EXCLUDED.checkpoint_at
                  ),
                  last_success_at=CURRENT_TIMESTAMP,
                  last_run_id=COALESCE(
                    EXCLUDED.last_run_id,
                    usage.live_rollup_checkpoints.last_run_id
                  )
                """,
                (
                    source_instance,
                    checkpoint,
                    run_id if records else None,
                ),
            )
        return inserted, updated, skipped

    def run_cycle(self) -> bool:
        now = datetime.now(timezone.utc)
        try:
            cutover, prior_checkpoint = self._position()
            if cutover is None:
                _log(
                    "codex_rollup_window",
                    status="waiting_for_cutover",
                )
                self.settings.health_file.write_text(
                    now.isoformat() + "\n", encoding="utf-8"
                )
                return True
            target = now - timedelta(seconds=self.settings.grace_seconds)
            if target <= cutover:
                _log(
                    "codex_rollup_window",
                    status="waiting_for_live_window",
                )
                self.settings.health_file.write_text(
                    now.isoformat() + "\n", encoding="utf-8"
                )
                return True
            base = prior_checkpoint or cutover
            start = max(
                cutover,
                base
                - timedelta(seconds=self.settings.overlap_seconds),
            )
            end = min(
                target,
                start
                + timedelta(seconds=self.settings.max_window_seconds),
            )
            service_pattern = "^(" + "|".join(
                name.replace(".", r"\.")
                for name in self.settings.service_names
            ) + ")$"
            trace_ids = complete_codex_trace_search(
                self.tempo,
                service_name=service_pattern,
                instance=self.settings.source_instance,
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
                    expected_services=self.settings.service_names,
                    source_instance=self.settings.source_instance,
                ):
                    if record["occurred_at"] >= cutover:
                        by_record_id[record["source_record_id"]] = record
            records = list(by_record_id.values())
            inserted, updated, skipped = self._write_window(
                cutover=cutover,
                checkpoint=end,
                records=records,
            )
            _log(
                "codex_rollup_window",
                status="caught_up" if end >= target else "catching_up",
                traces=len(trace_ids),
                records=len(records),
                inserted=inserted,
                updated=updated,
                skipped=skipped,
            )
            self.settings.health_file.write_text(
                now.isoformat() + "\n", encoding="utf-8"
            )
            return True
        except Exception as error:
            _log(
                "codex_rollup_error",
                error_class=type(error).__name__,
            )
            return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Roll up content-free Codex turn spans"
    )
    parser.add_argument(
        "--once", action="store_true", help="run one cycle and exit"
    )
    args = parser.parse_args(argv)
    settings = Settings.from_env()
    worker = CodexRollupWorker(
        settings,
        CodexTempoClient(
            settings.tempo_url, settings.http_timeout_seconds
        ),
    )
    if args.once:
        return 0 if worker.run_cycle() else 1

    stopped = Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    _log(
        "codex_rollup_started",
        interval_seconds=settings.interval_seconds,
        overlap_seconds=settings.overlap_seconds,
        services=len(settings.service_names),
    )
    while not stopped.is_set():
        worker.run_cycle()
        stopped.wait(settings.interval_seconds)
    _log("codex_rollup_stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
