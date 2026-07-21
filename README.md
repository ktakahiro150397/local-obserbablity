# local-obserbablity

Local observability for personal AI tools, shared Hermes usage, and later home-server infrastructure.

> The repository name intentionally follows the existing GitHub repository spelling: `local-obserbablity`.

## Phase 1 goal

Phase 1 collects and visualizes:

- personal Codex CLI and Codex desktop telemetry from the main Windows PC;
- Hermes telemetry from the `main` and `owashota` instances in `backup-secretary`;
- Discord sender IDs for Hermes usage accounting;
- model/provider, token, latency, error, and tool-summary metadata;
- no prompt, response, conversation-history, tool-argument, tool-result, or general-log content.

The observability path must fail open. Codex and Hermes must continue working when collectors, backends, Grafana, or Cloudflare are unavailable.

## Security domains

Phase 1 deliberately uses two data domains.

```text
Personal Codex CLI / desktop ─────┐
                                  ├─> private collector/backend/Grafana
Hermes main / owashota ───────────┤       - owner only
                                  │       - Codex + Hermes
                                  │
                                  └─> shared Hermes-only backend/Grafana
                                          - Hermes only
                                          - Discord user accounting
                                          - no personal Codex or host telemetry

Approved users
  -> https://observe.yanelmo.net
  -> Cloudflare Access (Google or email OTP)
  -> outbound-only Cloudflare Tunnel
  -> shared Grafana
```

Grafana OSS dashboard and folder permissions are not used as the hard boundary for personal data. The shared Grafana connects only to Hermes-only storage.

## Access model

- `https://observe.yanelmo.net` publishes only the shared Hermes Grafana.
- Cloudflare Access permits exact approved email identities.
- Google login is the normal path; Cloudflare One-time PIN is the fallback.
- Both login methods must remain selectable.
- New Access-backed Grafana users default to Viewer.
- The owner's Access-backed user receives organization Admin only after first login and explicit promotion.
- A separate local break-glass server administrator remains available without Cloudflare.
- OTLP, private Grafana, backend APIs, and administration interfaces are never routed publicly.

## Human-in-the-loop deployment

The implementation is Codex-led but not fully autonomous. Cloudflare and Google account authentication, secret entry, allow-list decisions, first browser logins, real Discord turns, desktop restarts, router confirmation, and destructive/security-sensitive actions require the owner.

Codex must prepare everything safe first and then issue one exact `HUMAN ACTION REQUIRED` packet using [`docs/human-actions.md`](docs/human-actions.md). It must never request secrets, approved email lists, real Discord IDs, or private account identifiers in chat or a public PR.

## Phase 1 implementation layout

- [`compose.yaml`](compose.yaml) owns a standalone `local-observability` Compose project. It is not placed inside the `backup-secretary` directory or Compose project.
- [`collector/config.yaml`](collector/config.yaml) fans all approved telemetry into private storage and admits only `service.name=backup-secretary-hermes` into the separate shared storage.
- [`grafana/private`](grafana/private) and [`grafana/shared`](grafana/shared) contain independent provisioning and dashboards.
- [`clients/codex`](clients/codex) contains an idempotent user-level Codex configuration installer and verifier.
- [`integrations/hermes`](integrations/hermes) documents the separately reviewed `backup-secretary` integration.
- [`scripts`](scripts) contains safe stack, smoke-test, backup, restore, and Grafana-role helpers.
- [`docs/runbook.md`](docs/runbook.md) is the operator procedure; [`docs/verification.md`](docs/verification.md) is the acceptance ledger.

Machine-specific paths, addresses, tunnel credentials, approved identities, and Grafana secrets live only in ignored local files.

## Required reading

- [`AGENTS.md`](AGENTS.md)
- [`docs/architecture.md`](docs/architecture.md)
- [`docs/phase-1-plan.md`](docs/phase-1-plan.md)
- [`docs/public-access.md`](docs/public-access.md)
- [`docs/human-actions.md`](docs/human-actions.md)
- [`docs/privacy.md`](docs/privacy.md)
- [`docs/references.md`](docs/references.md)
- [`integrations/hermes/README.md`](integrations/hermes/README.md)

## Roadmap

### Phase 1 — Codex, Hermes, and shared Hermes dashboard

- private Codex/Hermes telemetry;
- Hermes per-Discord-user accounting;
- private and shared Grafana dashboards;
- Cloudflare Access and Tunnel for the shared dashboard;
- Google and OTP login;
- account roles, backup/restore, privacy validation, and runbook.

### Phase 2 — Local server

- Linux host CPU, memory, disk, network, load, and uptime;
- Docker container CPU, memory, network, I/O, and restart status;
- alerts after a baseline is measured.

### Phase 3 — OpenCode and Windows

- OpenCode model, token, cost, latency, and tool telemetry;
- Windows host CPU, memory, disk, network, and selected service/process health.

### Phase 4 — Historical AI usage backfill

- read-only inventory of persisted Codex, Hermes, and OpenCode history;
- exact/derived/partial quality and coverage reporting;
- idempotent import with provenance, cutovers, deduplication, and rollback;
- private all-time usage by source/model/provider/token type;
- shared all-time Hermes usage by Discord user and model;
- no fabricated token counts or pre-monitoring host telemetry.

See [`docs/phase-4-backfill.md`](docs/phase-4-backfill.md).

## Repository boundaries

- `local-obserbablity` owns collection, storage, routing, dashboards, shared access, historical-usage normalization, and runbooks.
- `backup-secretary` owns Hermes and contains only the minimum pinned dependency/configuration needed to export telemetry.
- Neither runtime may require the other to be healthy.

## Privacy

Discord IDs and Access-backed Grafana email identities are personal data. Never commit real IDs, approved emails, ID-to-name mappings, private addresses, secrets, account/tunnel identifiers, historical source snapshots, or exported telemetry.

See [`docs/privacy.md`](docs/privacy.md).

## Related repositories

- [`ktakahiro150397/backup-secretary`](https://github.com/ktakahiro150397/backup-secretary)
- [`briancaffey/hermes-otel`](https://github.com/briancaffey/hermes-otel)

## Status

Phase 1 implementation is in progress on `feat/phase-1-implementation`. H1 discovery is complete in the local operator ledger; real deployment and the remaining human gates are not yet complete. Issue #1 stays open until the full acceptance matrix passes. Phase 4 backfill remains out of scope.
