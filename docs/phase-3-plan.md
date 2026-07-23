# Phase 3 plan: OpenCode and Windows observability

## Status and objective

Phase 3 follows Phase 2 and adds private-only telemetry for:

- live OpenCode model, provider, token, cost, latency, error, and tool-summary
  behavior, limited to fields proved content-free;
- Windows CPU, memory, paging, filesystem, disk, network, uptime, and selected
  service health;
- an optional OpenCode historical-usage extension after the live schema and
  privacy boundary pass verification.

OpenCode and Windows telemetry must never enter the shared Hermes backend,
shared usage ledger, or shared Grafana.

## Sanitized readiness inventory

The authoritative main Windows PC was inspected without reading prompt,
message, credential, or tool-result values.

- OpenCode `1.17.8` is installed from `opencode-ai`.
- `opencode stats` supports date, model, project, and tool-oriented summaries.
- The current SQLite database is about 1 GiB.
- Schema-only inspection found aggregate `session` columns for model, cost,
  input/output/reasoning/cache-read/cache-write tokens.
- The same database also contains content and credential-bearing tables and
  columns. Generic database export or unrestricted queries are prohibited.
- No Windows host collector/exporter is installed and no candidate telemetry
  listener was found.
- OpenCode source at tag `v1.17.8` enables OTLP traces and also constructs an
  OTLP log exporter when `OTEL_EXPORTER_OTLP_ENDPOINT` is set.
- AI SDK model spans additionally require
  `experimental.openTelemetry = true`.

The installed version and live received signals remain authoritative at
implementation time.

## Chosen topology

```text
OpenCode -> dedicated private OTLP ingress/privacy filter -> private traces/metrics
Windows hostmetrics collector ---------------------------> private metrics
```

Use a dedicated OpenCode ingress or dedicated pipelines in the private router
so its log behavior can be rejected independently. Do not point OpenCode
directly at shared storage or a receiver that forwards logs by default.

Use a pinned OpenTelemetry Collector Contrib Windows service for host metrics
unless implementation evidence shows a material compatibility problem.
Outbound OTLP/HTTP to the existing private endpoint is preferred over opening a
new Windows scrape port.

The Phase 3 implementation branch starts from current `main` after Phase 2 and
defaults to `feat/phase-3-implementation` or a non-conflicting suffix.

## Privacy-first OpenCode spike

OpenCode live collection is blocked until this spike passes:

1. Create a synthetic local project and use unique canary prompt/tool strings.
2. Enable the exact `v1.17.8` OTel settings against a disposable, private
   collector pipeline.
3. Configure no OpenCode logs pipeline/exporter; reject or drop the log signal.
4. Capture only schema/attribute names and sanitized scalar examples.
5. Search the disposable backend for every canary and require zero matches.
6. Verify prompt, response, tool arguments/results, paths, titles, repository
   names, account values, and credentials are absent.
7. Confirm model/provider/token/cost/duration/error/tool-summary fields that are
   safe and useful.
8. Stop the collector and prove OpenCode turns still succeed.
9. Destroy the disposable test data after recording sanitized evidence.

If the installed version cannot export useful traces without also transmitting
content-bearing logs to the receiver, do not deploy live OpenCode OTel. Prefer
an allowlisted adapter or wait for an upstream control; do not weaken the
content policy.

## Windows host policy

- Enable explicit hostmetrics scrapers only.
- Do not collect event logs, command lines, clipboard data, usernames, process
  arguments, or general application logs.
- Add process/service metrics only for a small reviewed allow-list.
- Store the local stable instance ID, install path, endpoint, and service
  account details in ignored configuration.
- Prefer outbound-only OTLP/HTTP; keep OTLP limited to the trusted LAN.
- Do not add router forwarding or any Cloudflare route for Phase 3 ingestion,
  collectors, or backend APIs. The reviewed owner-only private Grafana web route
  is independent of Phase 3 collection.

## OpenCode live identity and fields

Expected resource identity, subject to real verification:

| Field | Planned value |
|---|---|
| `service.name` | `opencode` |
| `service.instance.id` | stable local-only ID |
| client | actual emitted `opencode.client` |
| version | actual installed version |

Only allowlisted fields may proceed from the OpenCode ingress. The allow-list is
created from the synthetic spike and committed without real paths, prompts,
session IDs, project names, or account identifiers.

## Historical OpenCode extension

The Codex/Hermes Phase 4 production scope is complete. OpenCode history is a
Phase 3 follow-on because its installed storage did not exist in the original
authorized import scope.

If the owner authorizes it:

- make a consistent read-only snapshot of the SQLite database;
- query only explicit aggregate/session columns needed for usage accounting;
- never select credential values, prompt-bearing columns, message/part data,
  titles, paths, project directories, or arbitrary JSON blobs;
- use opaque source hashes and a recorded live cutover;
- keep every OpenCode row private;
- reconcile totals with `opencode stats` for the same date range;
- reuse the idempotency, provenance, rollback, and cutover rules in
  `phase-4-backfill.md`.

Schema discovery alone does not authorize importing history.

## Work packages

### P3.1 — Version and configuration review

- Re-check installed OpenCode, Windows, and collector versions.
- Review the exact installed OpenCode OTel source/config behavior.
- Record only sanitized version and capability evidence.
- Prepare ignored backups of OpenCode config and Windows service configuration.

### P3.2 — OpenCode privacy spike

- Build the disposable private pipeline.
- Run synthetic CLI and any relevant desktop/TUI flows.
- Produce the content-absence matrix and actual safe attribute allow-list.
- Decide go/no-go for production live OTel.

### P3.3 — Windows host collector

- Install from a pinned artifact with checksum/signature verification.
- Configure bounded queues/retries and explicit host scrapers.
- Register the Windows service with least privilege.
- Add health/diagnostic commands and an exact uninstall rollback.
- Verify reboot persistence only with owner approval for the reboot.

### P3.4 — Production OpenCode route

- Merge config idempotently while preserving unrelated settings.
- Route only to the private domain.
- Reject logs and disallowed attributes at the earliest controlled boundary.
- Verify fail-open operation during collector and backend outages.
- Record actual metric/span names before creating dashboards.

### P3.5 — Dashboards

Provision:

1. **OpenCode** — tokens by type/model/provider, requests, duration, errors,
   cost metadata, tools, and client/version where safely emitted.
2. **Windows host** — CPU, memory, paging, disk/filesystem, network, uptime,
   collector health, and reviewed service health.
3. **AI overview update** — add live OpenCode while preserving private/shared
   separation.

Do not display content, private project names, paths, or user/account identity.

### P3.6 — Optional historical extension

- Require separate owner authorization.
- Snapshot, inventory, dry-run, validate, back up, import, and reconcile.
- Prove no OpenCode row or data source exists in shared storage/Grafana.

### P3.7 — Verification and handoff

- Verify configuration, service health, persistence, and restart behavior.
- Exercise an interactive OpenCode turn after a full restart when required.
- Prove Windows/OpenCode collection failures do not block normal work.
- Search for synthetic canaries and prohibited attribute names.
- Require zero OpenCode/Windows results in every shared domain.
- Update runbook, verification ledger, capacity notes, and rollback.

## Human gates

### P3-H1 — Windows service installation

The owner must approve elevation immediately before installing or changing a
Windows service. Codex prepares the pinned artifact, checksum, config,
least-privilege account choice, exact command, expected result, and rollback.

### P3-H2 — OpenCode restart and interactive turn

The owner fully restarts the relevant OpenCode process and submits only the
synthetic test turn specified in the packet. Codex then verifies telemetry and
content absence.

### P3-H3 — Historical OpenCode import

Schema inspection is read-only preparation. Snapshotting and importing the
historical database requires explicit authorization after the allowlist,
cutover, row counts, backup, and rollback are prepared.

### P3-H4 — Firewall or reboot

Owner approval is required before a firewall change or reboot. The preferred
outbound-only design should require no inbound firewall rule.

## Acceptance criteria

Phase 3 is complete only when:

1. Windows host metrics render in private Grafana from a pinned service;
2. the OpenCode privacy spike passes or live OTel is explicitly disabled with
   the limitation documented;
3. actual safe OpenCode fields and client distinctions are recorded;
4. synthetic canaries and prohibited content are absent from retained data;
5. OpenCode and Windows remain usable when monitoring is unavailable;
6. no public listener, router forwarding, or Phase 3 ingestion/backend
   Cloudflare route was added;
7. the shared domain returns zero OpenCode/Windows telemetry;
8. service install, upgrade, uninstall, dashboards, and rollback are documented;
9. any historical extension is separately authorized, private, idempotent, and
   reconciled;
10. every human gate is verified or an explicit limitation is accepted.
