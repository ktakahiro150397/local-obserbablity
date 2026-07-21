# Implementation references

These are the primary references reviewed while preparing Phase 1. Codex should re-check them against the versions installed on the real machines before implementation.

## Codex

- OpenAI Codex advanced configuration: <https://developers.openai.com/codex/config-advanced>
- OpenAI Codex configuration reference: <https://developers.openai.com/codex/config-reference>
- OpenAI Codex repository: <https://github.com/openai/codex>
- Reviewed source commit: `1836ae0612052137d0cabaff7807ff8314cee940`

Relevant conclusions:

- telemetry routing belongs in the user-level Codex config;
- logs, metrics and traces use separate exporters;
- OTLP/HTTP endpoints are signal-specific;
- `codex.turn.token_usage` reports token-type breakdown where available;
- `originator` and `session_source` are candidate dimensions for distinguishing CLI and desktop.

Treat the installed Codex version as the source of truth for exact syntax and emitted attributes.

## Hermes

- Hermes Agent repository: <https://github.com/NousResearch/hermes-agent>
- Hermes OTel plugin: <https://github.com/briancaffey/hermes-otel>
- Reviewed plugin release: `0.11.0`
- Reviewed plugin main commit: `0180c5e63b9d035ee0754d9a0d75c3499a8def26`

Relevant conclusions:

- `capture_sender_id: true` is required for Discord user accounting;
- sender identity is exported as `hermes.sender.id` and `user.id=discord:<ID>`;
- the root `agent` span rolls up token usage and sender identity;
- `project_name` controls the resource `service.name`;
- LGTM/generic OTLP backends support traces and metrics;
- prompt/tool previews and logs can be disabled independently.

## Grafana/OpenTelemetry

- Grafana Docker OpenTelemetry LGTM: <https://grafana.com/docs/opentelemetry/docker-lgtm/>
- Grafana Tempo TraceQL metrics: <https://grafana.com/docs/tempo/latest/traceql/metrics-queries/>
- OpenTelemetry Collector: <https://opentelemetry.io/docs/collector/>

Relevant conclusions:

- `grafana/otel-lgtm` is suitable for initial local development/testing and packages the required signals in one container;
- `/data` must be persisted;
- `sum_over_time` can aggregate numeric span attributes and group by `user.id` when TraceQL metrics are available;
- long-term retention and a production-style split deployment should be reconsidered after actual data volume is measured.

## Source review policy

- Prefer official documentation and source repositories.
- Pin implementations rather than floating tags.
- Record the selected versions in the implementation PR.
- When documentation and installed behavior differ, capture sanitized evidence and follow the installed version.
