# Phase 1 plan: Codex and Hermes

## Objective

Collect persistent, queryable telemetry from:

- Codex CLI on the main Windows PC;
- Codex desktop on the main Windows PC;
- Hermes main in `backup-secretary`;
- Hermes owashota in `backup-secretary`.

The result must show token usage, model/provider, latency and source. Hermes Discord traffic must also be attributable to the Discord sender ID.

Phase 1 also publishes a **Hermes-only shared Grafana** at `https://observe.yanelmo.net`. Approved Discord users authenticate individually through Cloudflare Access and receive Grafana Viewer accounts. Personal Codex telemetry remains in a separate private backend/Grafana that is not routed through Cloudflare.

## Non-goals

Deferred until later phases:

- Linux host and Docker resource monitoring;
- OpenCode;
- Windows host monitoring;
- exposing personal Codex or infrastructure telemetry to Discord users;
- prompt, response, tool payload or general-log collection;
- production-scale HA or multi-node storage.

## Work package 0: environment inventory

- [ ] Clone `local-obserbablity` on the local server.
- [ ] Check Docker/Compose versions and CPU architecture.
- [ ] Check available ports 3000, 4317 and 4318.
- [ ] Select persistent data locations with adequate free space for private and shared backends.
- [ ] Record server LAN reachability and firewall rules locally.
- [ ] Check installed Codex version and effective `%USERPROFILE%\.codex\config.toml`.
- [ ] Confirm whether CLI and desktop read the same user config.
- [ ] Inspect the current `backup-secretary` Dockerfile, Compose services and mounted Hermes homes.
- [ ] Confirm the installed Hermes version is compatible with `hermes-otel` 0.11.0 or a newer reviewed release.
- [ ] Confirm `yanelmo.net` is active in the intended Cloudflare account.
- [ ] Record the Cloudflare Zero Trust team name, tunnel-management mode and Access identity provider locally.

Do not commit the environment inventory if it contains private machine details, Cloudflare account identifiers or user email addresses.

## Work package 1: private local telemetry backend

Expected repository additions:

```text
compose.yaml
.env.example
scripts/
grafana/private/provisioning/
grafana/private/dashboards/
docs/runbook.md
```

Tasks:

- [ ] Add a pinned private `grafana/otel-lgtm` service or equivalent reviewed LGTM topology.
- [ ] Persist all private backend data.
- [ ] Configure Grafana admin credentials via local environment/secrets.
- [ ] Do not expose the private Grafana through Cloudflare.
- [ ] Bind private Grafana only to localhost/trusted LAN as required for owner administration.
- [ ] Bind OTLP only to the required trusted interface; never publish OTLP through Cloudflare.
- [ ] Add health checks.
- [ ] Create stable Docker network `local-observability-net`.
- [ ] Add start/stop/status/logs/backup/restore commands.
- [ ] Add a telemetry smoke-test script or use an official OTel checker.
- [ ] Confirm `docker compose config` and clean startup.
- [ ] Confirm data persists after container recreation.

Acceptance:

- Private Grafana is reachable by the owner from the trusted network or documented SSH forwarding.
- OTLP/HTTP 4318 is reachable from the main PC.
- No OTLP port is reachable from the public Internet.
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
- [ ] Route Codex only to the private backend; it must not be mirrored to the shared backend.

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
- [ ] Confirm no Codex data appears in the shared Grafana/backend.

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
- [ ] Route Hermes telemetry to the private backend and mirror the approved Hermes-only signal set to the shared backend.

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

Provision dashboard JSON in Git where it contains no personal mappings or machine-specific identifiers.

### Private AI overview

- total tokens by source;
- requests/turns by source;
- model/provider breakdown;
- input/output/cache/reasoning split;
- recent error count;
- request/turn latency.

### Private Codex

- CLI versus desktop;
- token usage by type and model;
- turn duration and time-to-first-token if exported;
- tool calls by tool and result;
- API request count/error/duration.

### Private Hermes

- main versus owashota;
- token usage by type, model and provider;
- API duration/error;
- tool usage;
- recent sessions/traces.

### Shared Hermes users

- total tokens by `user.id`;
- input and output by `user.id`;
- cache/reasoning by `user.id` where available;
- turn count and average tokens per turn;
- selectable Hermes instance and time range;
- no Codex, server, Windows or private datasource.

Display raw Discord IDs by default. A friendly-name mapping may be added only through a local, ignored configuration or private Grafana customization.

## Work package 5: Cloudflare Access and shared Grafana

Read [`public-access.md`](public-access.md) before implementing this work package.

Expected repository additions:

```text
cloudflare/
  README.md
  cloudflared.example.yml
grafana/shared/
  provisioning/
  dashboards/
  grafana.ini.example
scripts/
  bootstrap-grafana-user.*
```

Required topology:

```text
observe.yanelmo.net
  -> Cloudflare Access
  -> named Cloudflare Tunnel
  -> shared Grafana
  -> Hermes-only shared backend
```

Tasks:

- [ ] Create a pinned outbound-only `cloudflared` service or document a pinned host-service alternative.
- [ ] Create a named tunnel and publish exactly `observe.yanelmo.net`.
- [ ] Store tunnel credentials/token outside Git.
- [ ] Create a Cloudflare Access self-hosted application for the hostname.
- [ ] Allow only exact approved user email identities.
- [ ] Do not create `Everyone`, bypass or shared-account access.
- [ ] Where supported, require `cloudflared` to validate the Access JWT/AUD before proxying.
- [ ] Enable Grafana auth proxy using `Cf-Access-Authenticated-User-Email` as the email identity.
- [ ] Auto-create Access-backed Grafana accounts with Viewer role only.
- [ ] Promote the owner's Access-backed account to Admin through a local/bootstrap procedure.
- [ ] Keep a separate local break-glass administrator.
- [ ] Restrict Grafana auth-proxy trust to the dedicated `cloudflared` container/network.
- [ ] Set Grafana `root_url=https://observe.yanelmo.net` and secure-cookie settings.
- [ ] Provision the shared Hermes dashboard.
- [ ] Confirm the shared stack has no private Codex/server/Windows datasource.
- [ ] Confirm direct origin access and header spoofing are blocked by topology/whitelist.
- [ ] Document adding, removing and deauthorizing a Discord user's email.

Acceptance:

- An approved user can sign into `observe.yanelmo.net` and receives a distinct Viewer account.
- An unapproved identity is denied before Grafana.
- The owner has Admin; regular users do not.
- The shared dashboard displays Hermes usage grouped by Discord sender ID.
- Private Codex data is absent from the shared backend and UI.
- No inbound router port forwarding exists.
- Tunnel or Access failure does not interrupt telemetry collection, Codex or Hermes.

## Work package 6: hardening and runbook

- [ ] Document startup, shutdown, update and rollback for private and shared stacks.
- [ ] Document how to disable each client exporter.
- [ ] Document data backup, restore and full deletion.
- [ ] Document how to remove telemetry for a Discord ID where backend capabilities allow it.
- [ ] Document Cloudflare Access user add/remove/revoke procedures.
- [ ] Document local break-glass Grafana access.
- [ ] Document firewall rules without committing private addressing.
- [ ] Measure one week of storage growth before setting retention.
- [ ] Record pinned versions and upgrade procedure.

## Final Phase 1 acceptance criteria

Phase 1 is complete only when all are true:

1. The private and shared stacks start cleanly from a fresh clone plus local secrets/configuration.
2. Private and shared storage persists across recreation.
3. Codex CLI telemetry appears in the private backend.
4. Codex desktop telemetry appears in the private backend and is distinguishable from CLI.
5. Hermes main telemetry appears in the private backend.
6. Hermes owashota telemetry appears or is explicitly deferred with a documented reason.
7. A Discord Hermes turn can be attributed to `user.id=discord:<ID>`.
8. Per-user Hermes token totals render in private and shared Grafana.
9. `observe.yanelmo.net` is protected by Cloudflare Access and a named tunnel.
10. Approved users receive individual Viewer accounts; the owner has Admin.
11. Personal Codex telemetry is not present in the shared backend or shared Grafana.
12. Prompts, responses and tool payloads are absent.
13. Stopping either observability stack or the Cloudflare tunnel does not break Codex or Hermes operation.
14. No OTLP or Grafana origin port is publicly forwarded from the router.
15. No secrets, private IPs, real Discord IDs, user emails, tunnel credentials or telemetry data are committed.
16. Runbook and sanitized verification evidence are complete.

## Questions to resolve from real evidence

- Exact `grafana/otel-lgtm` version to pin.
- Whether a second LGTM stack or a reviewed multi-tenant topology is the simplest strong isolation boundary.
- Whether LGTM's bundled Tempo has TraceQL metrics enabled as needed for `sum_over_time`.
- Effective Codex config schema and desktop-app behavior for the installed version.
- Actual backend-normalized Codex metric names.
- Exact Hermes hook payload produced by the installed Discord gateway version.
- Whether the shared external Docker network or the host LAN endpoint is more reliable on this server.
- Cloudflare tunnel-management mode and Access identity provider for this account.
- Stable trusted-proxy addressing/whitelist for Grafana auth proxy.
- Retention and storage limits after real usage is measured.
