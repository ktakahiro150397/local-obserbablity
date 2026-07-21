# Phase 1 plan: Codex and Hermes

## Objective

Collect persistent, queryable telemetry from:

- Codex CLI on the main Windows PC;
- Codex desktop on the main Windows PC;
- Hermes main in `backup-secretary`;
- Hermes owashota in `backup-secretary`.

The result must show token usage, model/provider, latency and source. Hermes Discord traffic must also be attributable to the Discord sender ID.

## Non-goals

Deferred until later phases:

- Linux host and Docker resource monitoring;
- OpenCode;
- Windows host monitoring;
- public/remote access;
- prompt, response, tool payload or general-log collection;
- production-scale HA or multi-node storage.

## Work package 0: environment inventory

- [ ] Clone `local-obserbablity` on the local server.
- [ ] Check Docker/Compose versions and CPU architecture.
- [ ] Check available ports 3000, 4317 and 4318.
- [ ] Select a persistent data location with adequate free space.
- [ ] Record server LAN reachability and firewall rules locally.
- [ ] Check installed Codex version and effective `%USERPROFILE%\.codex\config.toml`.
- [ ] Confirm whether CLI and desktop read the same user config.
- [ ] Inspect the current `backup-secretary` Dockerfile, Compose services and mounted Hermes homes.
- [ ] Confirm the installed Hermes version is compatible with `hermes-otel` 0.11.0 or a newer reviewed release.

Do not commit the environment inventory if it contains private machine details.

## Work package 1: local telemetry backend

Expected repository additions:

```text
compose.yaml
.env.example
scripts/
grafana/provisioning/
grafana/dashboards/
docs/runbook.md
```

Tasks:

- [ ] Add pinned `grafana/otel-lgtm` service.
- [ ] Persist `/data`.
- [ ] Configure Grafana admin credentials via local environment/secrets.
- [ ] Bind Grafana and OTLP to the required LAN interface only.
- [ ] Add health checks.
- [ ] Create stable Docker network `local-observability-net`.
- [ ] Add start/stop/status/logs/backup/restore commands.
- [ ] Add a telemetry smoke-test script or use an official OTel checker.
- [ ] Confirm `docker compose config` and clean startup.
- [ ] Confirm data persists after container recreation.

Acceptance:

- Grafana is reachable from the main PC.
- OTLP/HTTP 4318 is reachable from the main PC.
- No port is reachable from outside the trusted LAN.
- Data remains after `docker compose down` followed by `up` when the persistent volume is retained.

## Work package 2: Codex telemetry

Expected repository additions:

```text
clients/codex/config.fragment.toml.example
clients/codex/install.ps1
clients/codex/verify.ps1
```

Tasks:

- [ ] Create a user-level Codex config fragment for local OTLP.
- [ ] Disable OTel log export in Phase 1.
- [ ] Enable OTLP/HTTP metrics and traces.
- [ ] Keep `log_user_prompt = false`.
- [ ] Add stable custom span/resource attributes only where officially supported.
- [ ] Write an idempotent PowerShell installer that backs up and merges the existing config.
- [ ] Avoid duplicate `[otel]` tables and preserve unrelated settings.
- [ ] Write a verification script for server reachability and effective config.
- [ ] Fully restart Codex CLI/desktop after configuration changes.

Target config shape; verify against the installed Codex version before applying:

```toml
[otel]
environment = "home"
log_user_prompt = false
exporter = "none"
metrics_exporter = { otlp-http = {
  endpoint = "http://<LOCAL_SERVER_IP>:4318/v1/metrics",
  protocol = "binary"
}}
trace_exporter = { otlp-http = {
  endpoint = "http://<LOCAL_SERVER_IP>:4318/v1/traces",
  protocol = "binary"
}}
```

Validation:

- [ ] Run a fresh CLI turn.
- [ ] Run a fresh desktop turn.
- [ ] Find `codex.turn.token_usage` data.
- [ ] Verify token-type breakdown where supplied.
- [ ] Verify model and app version.
- [ ] Identify the values that distinguish CLI and desktop (`originator`, `session_source`, or current equivalents).
- [ ] Confirm no prompt body or tool-result content is stored.

Do not assume the metric name remains dotted after backend translation. Grafana/Mimir may expose normalized Prometheus-style names; inspect received data and build dashboards from actual names.

## Work package 3: Hermes integration

Changes belong primarily in a separate `backup-secretary` branch/PR. `local-obserbablity` should hold examples and documentation.

Expected `local-obserbablity` additions:

```text
integrations/hermes/config.yaml.example
integrations/hermes/README.md
```

Expected `backup-secretary` changes:

- Hermes image installs a pinned `hermes-otel` version/commit and OTel dependencies.
- Plugin is enabled through Hermes' plugin mechanism.
- Each Hermes home receives an appropriate plugin config.
- Hermes services join `local-observability-net` or use a documented fallback endpoint.
- Main and owashota get distinct instance attributes.

Required plugin settings:

```yaml
capture_previews: false
capture_conversation_history: false
capture_sender_id: true
capture_logs: false
```

Tasks:

- [ ] Review the selected `hermes-otel` release and pin it.
- [ ] Install it at image build time.
- [ ] Configure an LGTM/OTLP backend with traces and metrics enabled, logs disabled.
- [ ] Set `project_name: backup-secretary-hermes`.
- [ ] Set `service.instance.id` separately for main and owashota through resource attributes.
- [ ] Verify exporter failure is non-blocking.
- [ ] Verify a Discord turn supplies `sender_id` to the Hermes hooks.
- [ ] Verify spans include `hermes.sender.id` and `user.id=discord:<ID>`.
- [ ] Verify the root `agent` span includes rolled-up token totals.

User-accounting validation:

- [ ] Generate a Discord turn from one user.
- [ ] Find the root `agent` span.
- [ ] Confirm the same span contains `user.id` and token totals.
- [ ] When safely possible, generate a turn from a second user and confirm a distinct series.
- [ ] Confirm no real ID or screenshot exposing it is committed to the public repository/PR.

Initial TraceQL metrics query shape:

```traceql
{ resource.service.name = "backup-secretary-hermes" && span:name = "agent" }
| sum_over_time(span."gen_ai.usage.total_tokens") by (span."user.id")
```

Create parallel queries for:

- `gen_ai.usage.input_tokens`;
- `gen_ai.usage.output_tokens`;
- `gen_ai.usage.cache_read.input_tokens` and/or the actual compatibility alias emitted;
- `gen_ai.usage.cache_creation.input_tokens`;
- `gen_ai.usage.reasoning.output_tokens`.

Use only attributes confirmed in real spans.

## Work package 4: dashboards

Provision dashboard JSON in Git.

### AI overview

- total tokens by source;
- requests/turns by source;
- model/provider breakdown;
- input/output/cache/reasoning split;
- recent error count;
- request/turn latency.

### Codex

- CLI versus desktop;
- token usage by type and model;
- turn duration and time-to-first-token if exported;
- tool calls by tool and result;
- API request count/error/duration.

### Hermes

- main versus owashota;
- token usage by type, model and provider;
- API duration/error;
- tool usage;
- recent sessions/traces.

### Hermes users

- total tokens by `user.id`;
- input and output by `user.id`;
- cache/reasoning by `user.id` where available;
- turn count and average tokens per turn;
- selectable Hermes instance and time range.

Display raw Discord IDs by default. A friendly-name mapping may be added only through a local, ignored configuration or private Grafana customization.

## Work package 5: hardening and runbook

- [ ] Document startup, shutdown, update and rollback.
- [ ] Document how to disable each client exporter.
- [ ] Document data backup, restore and full deletion.
- [ ] Document how to remove telemetry for a Discord ID where backend capabilities allow it.
- [ ] Document firewall rules without committing private addressing.
- [ ] Measure one week of storage growth before setting retention.
- [ ] Record pinned versions and upgrade procedure.

## Final Phase 1 acceptance criteria

Phase 1 is complete only when all are true:

1. The stack starts cleanly from a fresh clone plus local `.env`.
2. Storage persists across recreation.
3. Codex CLI telemetry appears.
4. Codex desktop telemetry appears and is distinguishable from CLI.
5. Hermes main telemetry appears.
6. Hermes owashota telemetry appears or is explicitly deferred with a documented reason.
7. A Discord Hermes turn can be attributed to `user.id=discord:<ID>`.
8. Per-user token totals render in Grafana.
9. Prompts, responses and tool payloads are absent.
10. Stopping the stack does not break Codex or Hermes operation.
11. No secrets, private IPs, real Discord IDs or telemetry data are committed.
12. Runbook and sanitized verification evidence are complete.

## Questions to resolve from real evidence

- Exact `grafana/otel-lgtm` version to pin.
- Whether LGTM's bundled Tempo has TraceQL metrics enabled as needed for `sum_over_time`.
- Effective Codex config schema and desktop-app behavior for the installed version.
- Actual backend-normalized Codex metric names.
- Exact Hermes hook payload produced by the installed Discord gateway version.
- Whether the shared external Docker network or the host LAN endpoint is more reliable on this server.
- Retention and storage limits after real usage is measured.
