# Phase 1 plan: Codex and Hermes

## Objective

Collect persistent, queryable telemetry from:

- Codex CLI on the main Windows PC;
- Codex desktop on the main Windows PC;
- Hermes main in `backup-secretary`;
- Hermes owashota in `backup-secretary`.

The result must show token usage, model/provider, latency and source. Hermes Discord traffic must also be attributable to the Discord sender ID.

Phase 1 also publishes a **Hermes-only shared Grafana** at `https://observe.yanelmo.net`. Approved Discord users authenticate individually through Cloudflare Access using either Google or email one-time PIN (OTP), then receive Grafana Viewer accounts. Personal Codex telemetry remains in a separate private backend/Grafana that is not routed through Cloudflare.

## Execution model

This is a **Codex-led, human-in-the-loop** implementation. Read [`human-actions.md`](human-actions.md) before starting.

Responsibility labels used below:

- **CODEX** — Codex implements and verifies without delegating normal engineering work.
- **HUMAN** — the owner must make the account/security decision or perform the action.
- **JOINT** — Codex prepares exact values and verification; the owner authenticates, enters a secret, approves, or performs the interactive step.

Codex must keep an untracked `notes/human-actions.local.md` checklist. At each human gate it must finish safe preparation first, then provide the exact `HUMAN ACTION REQUIRED` packet from `human-actions.md`. A checkbox involving Cloudflare, Google, browser login, Discord users, Codex desktop, router state, or destructive operations is not complete until the human action and Codex verification have both occurred.

## Non-goals

Deferred until later phases:

- Linux host and Docker resource monitoring;
- OpenCode;
- Windows host monitoring;
- exposing personal Codex or infrastructure telemetry to Discord users;
- prompt, response, tool payload or general-log collection;
- production-scale HA or multi-node storage.

## Work package 0: environment inventory

- [ ] **CODEX** Clone `local-obserbablity` on the local server.
- [ ] **CODEX** Check Docker/Compose versions and CPU architecture.
- [ ] **CODEX** Check required ports and existing bindings.
- [ ] **JOINT** Select persistent data locations for private and shared backends.
- [ ] **CODEX** Record server LAN reachability and host firewall state locally.
- [ ] **CODEX** Check the installed Codex version and effective `%USERPROFILE%\.codex\config.toml`.
- [ ] **JOINT** Confirm whether Codex CLI and desktop read the same user config.
- [ ] **CODEX** Inspect the current `backup-secretary` Dockerfile, Compose services and mounted Hermes homes.
- [ ] **CODEX** Confirm the installed Hermes version is compatible with a reviewed pinned `hermes-otel` release.
- [ ] **HUMAN H1** Sign in to the intended Cloudflare account and confirm `yanelmo.net` is active there.
- [ ] **JOINT H1** Record the Cloudflare Zero Trust team name and tunnel-management mode locally.
- [ ] **JOINT H3/H4** Record whether Google and One-time PIN identity providers already exist.
- [ ] **JOINT H3** Record the Google OAuth project/client state without copying secrets into the repository.
- [ ] **HUMAN H9** Confirm current router port-forwarding state.

Do not commit the environment inventory if it contains private machine details, Cloudflare identifiers, Google OAuth identifiers, email addresses or credentials.

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

- [ ] **CODEX** Add a pinned private `grafana/otel-lgtm` service or reviewed equivalent.
- [ ] **CODEX** Persist private backend data.
- [ ] **JOINT** Configure Grafana admin credentials through an ignored local secret.
- [ ] **CODEX** Do not expose the private Grafana through Cloudflare.
- [ ] **CODEX** Bind private Grafana only to localhost/trusted LAN as required.
- [ ] **CODEX** Bind OTLP only to trusted interfaces; never publish OTLP through Cloudflare.
- [ ] **CODEX** Add health checks.
- [ ] **CODEX** Create a stable Docker network such as `local-observability-net`.
- [ ] **CODEX** Add start/stop/status/logs/backup/restore commands.
- [ ] **CODEX** Add a telemetry smoke test.
- [ ] **CODEX** Confirm clean startup and persistent data after recreation.

Acceptance:

- Private Grafana is reachable by the owner from the trusted network or documented SSH forwarding.
- OTLP/HTTP is reachable from the main PC.
- No OTLP endpoint is reachable from the public Internet.
- Data remains after stack recreation when volumes are retained.

## Work package 2: Codex telemetry

Expected repository additions:

```text
clients/codex/config.fragment.toml.example
clients/codex/install.ps1
clients/codex/verify.ps1
```

Tasks:

- [ ] **CODEX** Create a user-level Codex config fragment for local OTLP.
- [ ] **CODEX** Disable OTel log export in Phase 1.
- [ ] **CODEX** Enable OTLP/HTTP metrics and traces.
- [ ] **CODEX** Keep `log_user_prompt = false`.
- [ ] **CODEX** Add stable custom attributes only where officially supported.
- [ ] **CODEX** Write an idempotent PowerShell installer that backs up and merges existing config.
- [ ] **CODEX** Avoid duplicate `[otel]` tables and preserve unrelated settings.
- [ ] **CODEX** Write a verification script for server reachability and effective config.
- [ ] **JOINT H8** Fully restart Codex CLI/desktop after configuration changes.
- [ ] **CODEX** Route Codex only to the private backend.

Target shape; verify against the installed Codex version before applying:

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

- [ ] **CODEX** Run a fresh CLI turn and verify its telemetry.
- [ ] **JOINT H8** The owner runs a fresh desktop turn after a full application restart.
- [ ] **CODEX** Find Codex token-usage telemetry.
- [ ] **CODEX** Verify token-type breakdown where supplied.
- [ ] **CODEX** Verify model and app version.
- [ ] **CODEX** Identify actual dimensions distinguishing CLI and desktop.
- [ ] **CODEX** Confirm prompt bodies and tool-result content are absent.
- [ ] **CODEX** Confirm no Codex data appears in the shared backend/Grafana.

Build dashboards from actual received names because backends may normalize metric names.

## Work package 3: Hermes integration

Changes belong primarily in a separate `backup-secretary` branch/PR. `local-obserbablity` holds examples and documentation.

Expected `local-obserbablity` additions:

```text
integrations/hermes/config.yaml.example
integrations/hermes/README.md
```

Expected `backup-secretary` changes:

- Hermes image installs a pinned `hermes-otel` version/commit and dependencies.
- Plugin is enabled through Hermes' plugin mechanism.
- Each Hermes home receives appropriate plugin config.
- Hermes services join the observability network or use a documented fallback endpoint.
- Main and owashota get distinct instance attributes.

Required settings:

```yaml
capture_previews: false
capture_conversation_history: false
capture_sender_id: true
capture_logs: false
```

Tasks:

- [ ] **CODEX** Review and pin `hermes-otel`.
- [ ] **CODEX** Install it at image build time.
- [ ] **CODEX** Configure traces and metrics; keep logs disabled.
- [ ] **CODEX** Set `project_name: backup-secretary-hermes`.
- [ ] **CODEX** Set `service.instance.id` separately for main and owashota.
- [ ] **CODEX** Verify exporter failure is non-blocking.
- [ ] **JOINT H7** Verify a real Discord turn supplies `sender_id` to the hooks.
- [ ] **CODEX** Verify spans include `hermes.sender.id` and `user.id=discord:<ID>`.
- [ ] **CODEX** Verify the root `agent` span includes rolled-up token totals.
- [ ] **CODEX** Route Hermes to the private backend and mirror only the approved content-free Hermes signal set to the shared backend.

User-accounting validation:

- [ ] **HUMAN H7** A real Discord user generates a test turn after being informed of ID/usage collection.
- [ ] **CODEX** Find the root `agent` span and verify identity plus token totals.
- [ ] **HUMAN H7** A second user generates a turn when safely available.
- [ ] **CODEX** Confirm a distinct identity without committing either real ID.
- [ ] **CODEX** Confirm no real ID or screenshot exposing it is committed.

Initial TraceQL query shape:

```traceql
{ resource.service.name = "backup-secretary-hermes" && span:name = "agent" }
| sum_over_time(span."gen_ai.usage.total_tokens") by (span."user.id")
```

Create parallel queries for input, output, cache-read, cache-write and reasoning attributes confirmed in real spans.

## Work package 4: dashboards

Provision dashboard JSON in Git only when it contains no personal mappings or machine-specific identifiers.

### Private dashboards

- total tokens by source;
- Codex CLI versus desktop;
- model/provider breakdown;
- input/output/cache/reasoning split;
- request/turn latency and errors;
- Hermes main versus owashota;
- tool name/count/outcome;
- recent sessions/traces.

### Shared Hermes dashboard

- total tokens by `user.id`;
- input/output/cache/reasoning by `user.id` where available;
- turn count and average tokens per turn;
- model/provider breakdown;
- main versus owashota selector;
- no Codex, server, Windows or private data source.

Display raw Discord IDs by default. Friendly names may be added only through local ignored provisioning.

## Work package 5: Cloudflare Access and shared Grafana

Read [`public-access.md`](public-access.md) and [`human-actions.md`](human-actions.md) completely before implementation.

Expected additions:

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
       -> Google OR email OTP
  -> named Cloudflare Tunnel
  -> shared Grafana
  -> Hermes-only shared backend
```

### Tunnel and shared stack

- [ ] **CODEX** Deploy a pinned outbound-only `cloudflared` service or documented host-service alternative.
- [ ] **JOINT H2** The owner authorizes the named tunnel or enters its token into an ignored local secret; Codex verifies it.
- [ ] **CODEX** Publish exactly `observe.yanelmo.net` through the named tunnel.
- [ ] **CODEX** Do not route private Grafana or OTLP through the tunnel.
- [ ] **JOINT** Where supported, configure and verify Access JWT/AUD validation without exposing the AUD.
- [ ] **CODEX** Keep shared Grafana connected only to the Hermes-only shared backend.

### Google identity provider

- [ ] **HUMAN H3** Sign in to Google Cloud and create or select the OAuth project.
- [ ] **HUMAN H3** Configure the OAuth consent screen and choose the appropriate audience/publishing state.
- [ ] **HUMAN H3** Create a Web application OAuth client.
- [ ] **JOINT H3** Register the exact Access-team JavaScript origin prepared by Codex.
- [ ] **JOINT H3** Register the exact Access callback URI prepared by Codex.
- [ ] **HUMAN H3** Enter the Client ID and Client Secret into Cloudflare without returning the secret to Codex/chat.
- [ ] **JOINT H3** Test the Google connection in Cloudflare Zero Trust.

### One-time PIN provider

- [ ] **HUMAN H4** Enable One-time PIN in the Access account/application.
- [ ] **CODEX** Document OTP delivery and mail-link-scanner troubleshooting.
- [ ] **HUMAN H4** Confirm no shared mailbox is used as a shared identity.

### Access policy

- [ ] **JOINT H4** Create a self-hosted Access application for `observe.yanelmo.net`.
- [ ] **HUMAN H4** Select both Google and One-time PIN as login methods.
- [ ] **HUMAN H4** Enter only exact approved email addresses directly in Access.
- [ ] **HUMAN H4** Select and document the session duration locally.
- [ ] **CODEX** Verify no `Everyone`, bypass, shared-account, broad-domain or Google-group authorization exists.
- [ ] **CODEX** Document adding, removing and revoking a user's email.

### Grafana identity and roles

- [ ] **CODEX** Enable Grafana auth proxy using `Cf-Access-Authenticated-User-Email`.
- [ ] **CODEX** Auto-create Access-backed accounts as Viewer only.
- [ ] **HUMAN H5** The owner performs the first Access-backed Grafana login.
- [ ] **JOINT H5** Promote only the owner's Access-backed account through a local/bootstrap procedure.
- [ ] **JOINT H5** Create and verify a separate local break-glass administrator.
- [ ] **CODEX** Restrict auth-proxy trust to the dedicated `cloudflared` network/address.
- [ ] **CODEX** Set `root_url=https://observe.yanelmo.net` and secure-cookie settings.
- [ ] **CODEX** Keep email-to-Discord-ID aliases outside Git.

### Interactive account tests

- [ ] **HUMAN H6** Sign in with Google using an approved email.
- [ ] **HUMAN H6** Sign in with OTP using the same email.
- [ ] **CODEX** Verify both methods resolve to the same Grafana account.
- [ ] **HUMAN H6** Test a regular approved Viewer account.
- [ ] **CODEX** Verify that account is Viewer, not Editor/Admin.
- [ ] **HUMAN H6** Attempt access with an unapproved email.
- [ ] **CODEX** Verify denial occurs before Grafana.

Acceptance:

- An approved user can sign in using Google.
- An approved user can sign in using OTP.
- Both methods are visible on the Access login page.
- The same email maps to one Grafana Viewer account across both methods.
- An unapproved email is denied before Grafana.
- The owner has Admin; regular users do not.
- Shared Grafana displays Hermes usage grouped by Discord sender ID.
- Private Codex data is absent from the shared backend and UI.
- No inbound router port forwarding exists, confirmed by the owner and recorded without private details.
- Tunnel or Access failure does not interrupt collection, Codex or Hermes.

## Work package 6: hardening and runbook

- [ ] **CODEX** Document startup, shutdown, update and rollback for both stacks.
- [ ] **CODEX** Document how to disable each exporter.
- [ ] **CODEX** Document backup, restore and full deletion.
- [ ] **CODEX** Document deletion limitations for one Discord ID.
- [ ] **CODEX** Document Cloudflare Access user add/remove/revoke procedures.
- [ ] **CODEX** Document Google OAuth client/secret rotation, without containing a real secret.
- [ ] **CODEX** Document OTP fallback and logout.
- [ ] **CODEX** Document local break-glass Grafana access.
- [ ] **JOINT H9** Document firewall/router invariants without private addresses.
- [ ] **JOINT** Measure one week of storage growth before setting long-term retention.
- [ ] **CODEX** Record pinned versions and upgrade procedure.
- [ ] **CODEX** Include the `H1`–`H10` human-gate status table in verification/final report.

## Final Phase 1 acceptance criteria

Phase 1 is complete only when all are true:

1. Private and shared stacks start cleanly from a fresh clone plus local secrets/configuration.
2. Private and shared storage persists across recreation.
3. Codex CLI telemetry appears privately.
4. Codex desktop telemetry appears privately and is distinguishable from CLI after a real desktop turn.
5. Hermes main telemetry appears privately.
6. Hermes owashota telemetry appears or is explicitly deferred with a documented reason.
7. A real Discord Hermes turn is attributable to `user.id=discord:<ID>`.
8. Per-user Hermes token totals render in private and shared Grafana.
9. `observe.yanelmo.net` is protected by Access and a named tunnel.
10. Both Google and OTP login are visibly available and work for approved users.
11. The same email maps to the same Grafana account across both methods.
12. Approved users receive individual Viewer accounts; the owner has Admin and break-glass access works.
13. An unapproved identity is denied before Grafana.
14. Personal Codex telemetry is absent from shared storage and Grafana.
15. Prompts, responses, conversation history and tool payloads are absent.
16. Stopping either stack or the tunnel does not break Codex or Hermes.
17. No OTLP or Grafana origin port is publicly forwarded.
18. No secrets, private IPs, real Discord IDs, user emails, OAuth identifiers/credentials, tunnel credentials or telemetry data are committed.
19. Every required human gate is completed and verified or explicitly deferred with its limitation stated.
20. Runbook and sanitized verification evidence are complete.

## Questions to resolve from real evidence

- Exact `grafana/otel-lgtm` version to pin.
- Whether a second LGTM stack or reviewed multi-tenant topology is the simplest strong isolation boundary.
- Whether bundled Tempo supports required TraceQL metrics queries.
- Effective Codex config schema and desktop behavior for the installed version.
- Actual backend-normalized Codex metric names.
- Exact Hermes hook payload produced by the installed Discord gateway.
- Best server networking path between Compose projects.
- Cloudflare tunnel-management mode and actual team name.
- Google OAuth application audience/publishing state suitable for ongoing use.
- Stable trusted-proxy addressing for Grafana auth proxy.
- Retention and storage limits after real usage is measured.