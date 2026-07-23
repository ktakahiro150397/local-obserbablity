# local-obserbablity

Local observability for personal AI tools, shared Hermes usage, and later home-server infrastructure.

> The repository name intentionally follows the existing GitHub repository spelling: `local-obserbablity`.

## Implemented foundation

The deployed Phase 1 foundation collects and visualizes:

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

Owner
  -> https://private-observe.yanelmo.net
  -> owner-only Cloudflare Access
  -> separate outbound-only Cloudflare Tunnel
  -> private Grafana
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
- `https://private-observe.yanelmo.net` is the only Cloudflare route to the
  private Grafana. It uses a separate tunnel, owner-only Access policy, and
  private-only Docker network.
- OTLP, backend APIs, collector endpoints, and other administration interfaces
  are never routed through Cloudflare or router forwarding.

## Human-in-the-loop deployment

The implementation is Codex-led but not fully autonomous. Cloudflare and Google account authentication, secret entry, allow-list decisions, first browser logins, real Discord turns, desktop restarts, router confirmation, and destructive/security-sensitive actions require the owner.

Codex must prepare everything safe first and then issue one exact `HUMAN ACTION REQUIRED` packet using [`docs/human-actions.md`](docs/human-actions.md). It must never request secrets, approved email lists, real Discord IDs, or private account identifiers in chat or a public PR.

## Implementation layout

- [`compose.yaml`](compose.yaml) owns a standalone `local-observability` Compose project. It is not placed inside the `backup-secretary` directory or Compose project.
- [`collector/config.yaml`](collector/config.yaml) fans all approved telemetry into private storage and admits only `service.name=backup-secretary-hermes` into the separate shared storage.
- [`grafana/private`](grafana/private) and [`grafana/shared`](grafana/shared) contain independent provisioning and dashboards.
- [`clients/codex`](clients/codex) contains an idempotent user-level Codex configuration installer and verifier.
- [`integrations/hermes`](integrations/hermes) documents the separately reviewed `backup-secretary` integration.
- [`scripts`](scripts) contains safe stack, smoke-test, backup, restore, and Grafana-role helpers.
- [`rollup`](rollup) continuously copies approved Hermes usage fields from shared Tempo into the isolated shared usage ledger.
- [`docs/runbook.md`](docs/runbook.md) is the operator procedure; [`docs/verification.md`](docs/verification.md) is the acceptance ledger.
- [`docs/phase-2-plan.md`](docs/phase-2-plan.md) and
  [`docs/phase-3-plan.md`](docs/phase-3-plan.md) define the next private-only
  infrastructure, OpenCode, and Windows work.

Machine-specific paths, addresses, tunnel credentials, approved identities, and Grafana secrets live only in ignored local files.

## Required reading

- [`AGENTS.md`](AGENTS.md)
- [`docs/architecture.md`](docs/architecture.md)
- [`docs/phase-1-plan.md`](docs/phase-1-plan.md)
- [`docs/phase-2-plan.md`](docs/phase-2-plan.md)
- [`docs/phase-3-plan.md`](docs/phase-3-plan.md)
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

Status: complete with the explicitly accepted H6 second-identity and denied-
identity test limitation recorded in [`docs/verification.md`](docs/verification.md).

### Phase 2 — Local server

- Linux host CPU, memory, disk, network, load, and uptime;
- Docker container CPU, memory, network, I/O, and restart status;
- alerts after a baseline is measured.

Status: ready for implementation. The real server has been inventoried, TCP
9100 is known to be occupied, and Docker API access is defined as a human
security gate. See [`docs/phase-2-plan.md`](docs/phase-2-plan.md).

### Phase 3 — OpenCode and Windows

- OpenCode model, token, cost, latency, and tool telemetry;
- Windows host CPU, memory, disk, network, and selected service/process health.

Status: ready after Phase 2. OpenCode `1.17.8` and its current SQLite schema
were inspected without reading content. A synthetic privacy spike is mandatory
because this version's OTLP endpoint also initializes log export. See
[`docs/phase-3-plan.md`](docs/phase-3-plan.md).

### Phase 4 — Historical AI usage backfill

- read-only inventory of persisted Codex, Hermes, and OpenCode history;
- exact/derived/partial quality and coverage reporting;
- idempotent import with provenance, cutovers, deduplication, and rollback;
- private all-time usage by source/model/provider/token type;
- shared all-time Hermes usage by Discord user and model;
- no fabricated token counts or pre-monitoring host telemetry.

Status: the authorized Codex/Hermes import, shared publication, dashboards, and
live Hermes rollup are complete. OpenCode history is an optional Phase 3
follow-on and is not implied by schema inspection.

See [`docs/phase-4-backfill.md`](docs/phase-4-backfill.md).

Codex/Hermes BF1 tooling and sanitized results are documented in
[`backfill/README.md`](backfill/README.md),
[`docs/backfill-runbook.md`](docs/backfill-runbook.md), and
[`docs/backfill-coverage.md`](docs/backfill-coverage.md).

After the approved Hermes cutovers, the shared ledger also receives a
five-minute live rollup. It re-reads a 30-minute overlap, uses opaque
trace/span-derived deduplication keys, and never stores content payloads.

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

Phase 1 and the authorized Codex/Hermes Phase 4 scope are merged and deployed.
The authoritative runtime is the real local server. Phase 2 is the next
implementation target, followed by Phase 3 on a separate branch. Existing
private/shared isolation, persisted data, and the accepted H6 limitation must be
preserved.
