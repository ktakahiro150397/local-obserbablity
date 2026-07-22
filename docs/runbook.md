# Phase 1 operations runbook

This runbook operates the standalone `local-observability` project on the local server. The repository directory, Compose project, data directories, and pull request are separate from `backup-secretary`. The only coupling is the external Docker network `local-observability-net`, which lets Hermes reach `otel-router` by Docker DNS.

Read `docs/human-actions.md` before an account, firewall, router, browser-login, Discord, restart, or destructive step. Secrets and private environment values belong only in ignored local files.

## Boundaries

| Surface | Binding or route | Intended audience |
|---|---|---|
| Private Grafana | server localhost, default port 3002 | owner through local access or SSH forwarding |
| Shared Grafana origin | server localhost, default port 3003 | break-glass/API administration only |
| OTLP/HTTP | trusted server LAN address, default port 4318 | main Windows PC and approved Docker clients |
| Collector health | server localhost, default port 13133 | local operations |
| Public hostname | `https://observe.yanelmo.net` through Cloudflare Tunnel | exact Access-approved identities |

Private Grafana, OTLP, collector health, Tempo, Prometheus, and backend APIs must never be Cloudflare routes or router forwards.

## One-time server preparation

Use a dedicated clone directory outside `backup-secretary`, then run:

```bash
git switch feat/phase-1-implementation
chmod +x scripts/*.sh
./scripts/init-local-env.sh
./scripts/stack.sh config
```

The initializer:

- creates ignored `.env` and `secrets/` files with mode 0600;
- creates independent private/shared data directories with mode 0700;
- creates separate private/shared Tempo runtime directories rather than granting container-root write access;
- records their owner UID:GID so both LGTM containers run non-root with all Linux capabilities dropped;
- generates unrelated Grafana passwords and secret keys;
- detects the server LAN address without printing secrets;
- validates the rendered Compose configuration.

It preserves an existing `.env`. Review only the keys, file modes, resolved directories, and bind classes; do not paste values into chat or Git.

Do not start `otel-router` on its LAN binding until H9 confirms no router forwarding and approves the binding/firewall decision.

## Start and inspect the private/shared backends

After H9:

```bash
./scripts/stack.sh up
./scripts/stack.sh status
./scripts/stack.sh logs private-lgtm shared-lgtm otel-router
curl --fail --silent http://127.0.0.1:13133/
```

Expected state:

- `private-lgtm`, `shared-lgtm`, and `otel-router` are healthy;
- only localhost Grafana bindings and the approved LAN OTLP binding exist;
- the two LGTM containers use different host data directories and different internal networks;
- private Grafana's localhost port uses a dedicated admin bridge that no other project service joins;
- `shared-lgtm` has only its own Prometheus and Tempo data sources;
- no logs pipeline exists in the router.

The initial memory limits fit the inventoried server but are not permanent capacity promises. The private LGTM limit is higher than the shared limit because real Codex TraceQL verification exhausted the original 1800 MiB private limit. Health checks probe Grafana, Tempo, and Prometheus directly and declare the aggregate container unhealthy after three consecutive failures so a failed child process cannot remain falsely healthy. Check container restarts, OOM events, free memory, swap, and disk growth after representative use.

### Hermes live rollup

`scripts/stack.sh up` migrates both ledgers before starting
`hermes-live-rollup`. The worker reads only completed Hermes root `agent` spans
from shared Tempo and writes the approved usage fields to the shared ledger.
It is a healthy no-op until the approved Hermes cutover rows exist.

Defaults are a five-minute poll, a 30-minute re-read overlap, a two-minute
settling delay, and a two-hour catch-up window. A persistent checkpoint means a
longer outage catches up in successive windows instead of losing everything
older than the overlap. Recovery is bounded by Tempo retention, so investigate
an unhealthy worker before the source retention window expires.

Inspect only sanitized service output:

```bash
docker compose ps hermes-live-rollup
docker compose logs --tail 100 hermes-live-rollup
docker compose exec -T shared-ledger psql \
  --username ledger_admin --dbname usage_ledger \
  --command "SELECT source_instance,checkpoint_at,last_success_at FROM usage.live_rollup_checkpoints ORDER BY source_instance;"
```

Run one immediate idempotence pass when diagnosing a delay:

```bash
docker compose run --rm hermes-live-rollup --once
```

The service stores only instance, timestamps, `user.id`, model/provider when
truthfully available, token fields, quality, and opaque hashes. It never stores
prompt/response bodies, conversation history, tool payloads, logs, or raw
Tempo trace/span IDs. Stopping the worker does not affect Hermes or live Tempo
ingestion; after restart it resumes from its checkpoint.

The writer password remains mode 0600. Compose file secrets preserve host
ownership, so `scripts/init-local-env.sh` records the owning non-root UID/GID
for the rollup container. Do not make the secret group/world-readable to solve
an ownership mismatch.

### Shared usage and API-equivalent cost dashboard

`Hermes usage & API-equivalent cost` reads only the shared PostgreSQL ledger.
Its default range is one week; Grafana's time picker can select any other
range. User colors use the stable `user.id` series name with Grafana's classic
palette-by-name mode, so the token, cost, and time-series panels agree.

The dollar panels apply the current standard API list prices in
`usage.api_model_prices`. They are a comparison estimate, not the provider
invoice or subscription charge. Cache-read and cache-write buckets are priced
without adding them to input a second time. The OpenAI long-context multiplier
is applied only to live request-granularity rows; a historical session aggregate
cannot prove that a single request crossed the threshold. Tool fees, taxes,
regional uplifts, and unrecognized models are excluded. The dashboard exposes
both pricing coverage and unpriced tokens so an unknown model cannot silently
become zero cost.

Before changing a rate, verify it on the provider's official pricing page and
add a new numbered schema migration. Update the dashboard's verification date
and re-run `backfill/scripts/migrate-ledgers.sh`; do not treat an old committed
rate as current without re-verification.

## Synthetic isolation test

```bash
./scripts/smoke-test.sh
```

The test creates content-free synthetic traces. It must find synthetic Codex and Hermes in private Tempo, find Hermes in shared Tempo, and find no synthetic Codex in shared Tempo. It uses a clearly synthetic `user.id` and does not contain a real Discord ID.

## Windows Codex configuration

Run from PowerShell on the main Windows PC after the private OTLP endpoint is reachable:

```powershell
.\clients\codex\Install-CodexTelemetry.ps1 -EndpointBase 'http://<PRIVATE_COLLECTOR>:4318'
.\clients\codex\Test-CodexTelemetry.ps1
```

The installer updates the effective user-level `%USERPROFILE%\.codex\config.toml` (or `CODEX_HOME`), creates a timestamped backup, replaces only OTel tables, and validates the result with the installed Codex CLI. It keeps structured log export disabled and `log_user_prompt=false`.

Run a real non-sensitive CLI turn, then complete H8 for a full desktop process restart and a separate desktop turn. Query actual traces to determine the stable CLI/desktop distinguishing attributes before finalizing dashboard dimensions. A configuration check alone does not satisfy H8.

Rollback uses the backup path printed by the installer:

```powershell
.\clients\codex\Restore-CodexConfig.ps1 -BackupPath '<BACKUP_PATH>' -Confirm
```

## Hermes integration boundary

All Hermes code changes belong to a fresh `backup-secretary` branch and PR based on its latest default branch. Do not edit or switch a dirty live checkout.

The Hermes image must contain the pinned `briancaffey/hermes-otel` source and pinned Python OTel dependencies at build time. Each service mounts a reviewed config at `~/.hermes/plugins/hermes_otel/config.yaml`, enables the plugin through Hermes' supported loader, joins `local-observability-net`, and sends only to `http://otel-router:4318`.

The committed instance configs may identify `main` and `owashota`, but must not contain endpoints with private addresses, credentials, Discord IDs, or identity mappings. Required privacy values are:

```yaml
capture_previews: false
capture_conversation_history: false
capture_full_prompts: false
capture_full_responses: false
capture_sender_id: true
capture_logs: false
```

The router is the only fan-out point. Hermes does not connect directly to shared storage.

## Cloudflare Tunnel and Access

Complete H2, H3, and H4 in order using the exact packets issued by Codex. The remotely managed tunnel origin must be:

```text
http://shared-lgtm:3000
```

Start `cloudflared` only after the exact-email Access policy, Google, OTP, disabled instant authentication, and origin protection are configured:

```bash
./scripts/stack.sh public-up
./scripts/stack.sh status
./scripts/stack.sh logs cloudflared
```

The tunnel token is stored only in ignored `secrets/cloudflare-tunnel.token` with mode 0600. Never pass it on a command line that may enter shell history or process listings.

`scripts/init-local-env.sh` also sets `CLOUDFLARED_UID_GID` to the owner of that 0600 token file. File-backed Compose secrets retain host ownership because they are bind-mounted, so the pinned cloudflared container must run as that same non-root numeric user. Do not make the token world-readable to work around a permissions error.

After the owner completes `wrangler login`, the Windows helper can fetch the token through the Cloudflare API and transfer it to the server only over SSH standard input. It refuses to overwrite a non-empty remote token file and does not start the connector:

```powershell
pwsh -File scripts/store-cloudflare-tunnel-token.ps1
```

Stop public access without stopping telemetry collection:

```bash
docker compose --profile public stop cloudflared
```

## Grafana roles

Cloudflare Access supplies `Cf-Access-Authenticated-User-Email` only through the dedicated proxy network. New auth-proxy users default to Viewer.

After the owner's first Access login (H5), store the exact email locally without printing it:

```bash
install -m 600 /dev/null secrets/owner-email
${EDITOR:?set EDITOR} secrets/owner-email
./scripts/bootstrap-grafana-owner.sh
```

The helper promotes that existing user to organization Admin and fails if the user is a Grafana server administrator. The separate local `breakglass` account remains the server administrator and is used through the localhost origin/API independently of Cloudflare.

## Routine operations

```bash
./scripts/stack.sh status
./scripts/stack.sh logs
./scripts/stack.sh stop
./scripts/stack.sh start
```

`down` removes containers and project networks but not bind-mounted data:

```bash
./scripts/stack.sh down
```

Never use `docker compose down -v` for this project. Do not prune Docker images, volumes, or networks without H10 and exact target validation.

## Backup

```bash
./scripts/backup.sh
```

The script briefly stops whichever of the router/private/shared services were running, creates separate private/shared archives and checksums, then restores only that prior running set. It deliberately excludes `.env`, tunnel credentials, and account data; store those separately in an approved secret store.

Verify archive readability and preserve filesystem permissions. A backup is not accepted until a restore rehearsal succeeds.

## Restore

Restore is destructive to the current live data and requires H10. After Codex validates the exact source, targets, free space, and rollback directory, use only the issued command:

```bash
H10_APPROVED=yes ./scripts/restore.sh --confirm-restore <BACKUP_DIRECTORY>
```

The script verifies checksums, moves current data into a timestamped recoverable rollback directory, restores both archives, and starts the stack. Do not delete the rollback directory until post-restore verification is complete.

## Privacy reset

If validation finds a content-bearing attribute in stored Phase 1 telemetry, stop further emission or add the collector scrub first. Resetting the private and shared stores is irreversible and requires immediate H10 approval. After Codex verifies the exact default data targets and confirms that no account gate depends on the current Grafana database, use only:

```bash
H10_APPROVED=yes ./scripts/reset-phase1-telemetry.sh --confirm-reset-telemetry
```

The helper stops only the router and two LGTM containers, moves both stores into a temporary restricted quarantine, creates clean stores, restarts the stack, and runs the content-scrubbing isolation smoke test. It restores the quarantined data automatically on failure. On success it permanently deletes the quarantine; the removed telemetry cannot be recovered.

## Failure and rollback expectations

- Collector or backend down: Codex/Hermes requests continue; bounded exporters may drop telemetry after retry limits.
- Shared backend down: private ingestion continues.
- Private backend down: shared Hermes ingestion continues.
- Tunnel down: only remote shared-dashboard access fails.
- Access or auth-proxy problem: stop `cloudflared`; use the localhost break-glass account/API; fix the policy before restarting the tunnel.
- Hermes plugin problem: revert only the separate `backup-secretary` branch/image/config; the observability project remains independent.
- Live rollup down: Hermes and Tempo ingestion continue; restart the worker before Tempo retention expires so the checkpoint can catch up.
- Codex exporter problem: restore the user config backup and fully restart desktop.

Record only sanitized counts, statuses, versions, and pass/fail results in Git. Detailed paths, identities, addresses, and raw trace output stay in `notes/*.local.md` or other ignored local evidence.

## Accepted authentication-test limitation

The owner accepted completion without the remaining H6 second-identity and
unapproved-identity browser tests because no second approved identity was
available and the denial test was declined. Same-email Google/OTP convergence,
initial Viewer assignment, owner organization-Admin promotion, break-glass
server administration, and origin/header-spoof protection were verified.

Do not represent persistent Viewer/different-email separation or unapproved-email
denial as tested. Reopen H6 if another suitable identity becomes available.
