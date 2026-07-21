# Phase 4 plan: historical AI usage backfill

## Objective

Recover historical AI usage that was recorded locally before live OpenTelemetry collection began, normalize it into an auditable usage model, and make it available in Grafana without fabricating missing data or double-counting the live period.

Phase 4 covers historical usage for:

- Codex CLI and Codex desktop on the main Windows PC;
- Hermes `main` and `owashota` in `backup-secretary`;
- OpenCode after the Phase 3 storage format has been inspected on the real machine.

Historical Linux/Windows host CPU, memory, disk, and network telemetry is not recoverable unless an existing trusted monitoring source is discovered. Phase 4 does not estimate infrastructure history from unrelated logs.

## Roadmap position and prerequisites

Phase 4 is implemented after Phase 3 in the roadmap.

Required prerequisites:

1. Phase 1 live Codex/Hermes telemetry is stable and its actual attributes are documented.
2. Phase 3 has identified the installed OpenCode storage schema and live telemetry fields.
3. A per-source and per-instance live cutover timestamp has been recorded.
4. Private and shared Grafana/data boundaries are working and tested.
5. Source databases/files have been backed up before any importer is run.

A read-only historical inventory may be performed earlier, but no production import should happen until the live cutover and canonical token semantics are fixed.

## Core rules

1. **Exact data beats estimates.** Missing token counts remain `NULL`/unknown. Do not infer tokens from character counts, elapsed time, message count, rate-limit percentages, or billing-plan limits.
2. **Sources are read-only.** Importers operate on snapshots or SQLite backups, never on a live source database in write mode.
3. **Every row has provenance.** Record source system, source instance, opaque source record ID, parser version, import run, quality, and source hash.
4. **Imports are idempotent.** Re-running the same source produces no duplicate usage.
5. **Backfill and live periods do not overlap.** The cutover policy is explicit and testable.
6. **Token subsets are not added twice.** Cache tokens are a subset/breakdown of input where reported; reasoning tokens are a subset/breakdown of output where reported.
7. **Private/shared separation remains intact.** Personal Codex and OpenCode history never enters the shared Hermes data domain.
8. **No content collection.** Parsers extract metadata and usage only; prompts, responses, reasoning text, tool arguments/results, and message bodies are excluded.

## Canonical token semantics

The normalized model uses these fields:

| Field | Meaning |
|---|---|
| `input_tokens` | Provider-reported input/prompt tokens. |
| `output_tokens` | Provider-reported output/completion tokens. |
| `cached_input_tokens` | Cache-read input tokens; treated as a subset/breakdown, not added to total. |
| `cache_write_tokens` | Cache-creation/write tokens; kept as a breakdown, not blindly added to total. |
| `reasoning_tokens` | Reasoning/thinking output tokens; treated as a subset/breakdown of output. |
| `total_tokens` | Provider-reported total when available, otherwise `input_tokens + output_tokens`; cache/reasoning are not added again. |

Unknown values are stored as `NULL`, not zero. A real reported zero may be stored as zero.

Cost fields are separate:

- `estimated_cost_usd`;
- `actual_cost_usd`;
- `cost_quality` (`reported`, `estimated`, `unknown`);
- `pricing_version` when an estimate depends on a price table.

ChatGPT/Codex subscription credits or plan quota are not reconstructed from token counts.

## Recommended storage model

### Canonical usage ledger

The baseline design is a dedicated SQL usage ledger, preferably PostgreSQL because Grafana has a built-in PostgreSQL data source and PostgreSQL supports transactional, idempotent historical upserts.

Do not use the live Tempo/Mimir ingestion path as the canonical backfill target by default. Historical OTLP timestamps, backend retention windows, out-of-order metrics, and replay behavior must not be assumed safe. Synthetic OTLP backfill is allowed only after a documented spike proves:

- old timestamps are accepted for the required historical range;
- replays are idempotent or safely removable;
- retention does not immediately delete imported data;
- metrics are not rejected as out of order;
- private/shared routing cannot leak Codex/OpenCode data.

### Private and shared ledgers

- **Private ledger:** Codex, Hermes, and OpenCode historical usage.
- **Shared ledger:** Hermes-only historical usage approved for all Access-authorized viewers.

The shared Grafana receives credentials only for the shared Hermes database/service. Prefer a separate database/service for Phase 4. A shared PostgreSQL server with separate databases/users is acceptable only after tests prove that the shared Grafana credential cannot enumerate or query private objects.

### Live plus historical all-time views

Real-time dashboards continue to query the live OTel backends.

All-time dashboards query normalized SQL views containing:

- `record_origin = 'backfill'` for pre-cutover historical rows;
- `record_origin = 'live_rollup'` for idempotent closed-bucket rollups produced from the live backends after cutover.

A scheduled rollup job reconciles closed UTC time buckets from live Tempo/Mimir into the ledger. This avoids fragile arithmetic across unrelated Grafana data sources and gives one deduplicated all-time source of truth. Current-day real-time panels may continue using OTel until the bucket closes.

## Canonical record fields

The implementation should support at least:

```text
record_id                  stable normalized ID
record_origin              backfill | live_rollup
source_system              codex | hermes | opencode
source_instance            main-windows | hermes-main | hermes-owashota | ...
source_record_id           opaque source-native key
source_record_hash         SHA-256 or equivalent content-independent fingerprint
source_snapshot_hash       hash of the source snapshot/manifest
parser_name
parser_version
import_run_id
occurred_at                original UTC event/session time
period_start
period_end
record_granularity         api_call | turn | message | session | day
user_id                    nullable; Discord ID only for Hermes
request_model              nullable
response_model             nullable
provider                   nullable
input_tokens               nullable
output_tokens              nullable
cached_input_tokens        nullable
cache_write_tokens         nullable
reasoning_tokens           nullable
total_tokens               nullable
estimated_cost_usd         nullable
actual_cost_usd            nullable
quality                    exact | derived | partial
quality_reason             short machine-readable reason
shared_eligible            boolean
imported_at
```

Do not store a full source path when it contains a Windows username, private host path, or other identifying data. Store an opaque path ID/hash and keep the local manifest ignored by Git.

## Source-specific plan

### Hermes

Expected primary source: each instance's `state.db` snapshot.

Current Hermes storage can contain session source, `user_id`, model, timestamps, input/output/cache/reasoning tokens, provider/billing metadata, cost, and API-call counts. Newer schemas may also include per-model usage rows.

Importer policy:

1. Create a consistent SQLite backup/copy while Hermes remains available.
2. Inspect `schema_version`, table names, and columns from the snapshot.
3. Prefer a per-model usage table when present and populated.
4. Otherwise import session aggregate usage from `sessions` and mark model attribution `derived` when only one session-level model is known.
5. Never sum both a per-model usage table and the session aggregate for the same session.
6. Keep `main` and `owashota` source instances separate.
7. Map Discord gateway `user_id` to `user.id=discord:<ID>` only after validating the real stored value.
8. Treat compression/session lineage as grouping metadata; do not collapse additive child-session usage unless reconciliation proves the parent contains duplicate totals.
9. Query usage tables only. Do not select message content, system prompts, reasoning text, tool payloads, or FTS tables.
10. Use older JSONL/session artifacts only when the real installation predates SQLite and a separate parser is justified by evidence.

Private import contains all approved Hermes rows. Shared import contains only content-free Hermes usage fields and the authorized Discord accounting ID.

### Codex

Expected source: the actual `CODEX_HOME` session/rollout history discovered on Windows.

Modern rollout data may contain:

- session metadata and source/client information;
- turn context with model and provider;
- cumulative `total_token_usage`;
- `last_token_usage` breakdowns;
- input, cached-input, output, reasoning-output, and total tokens.

Coverage is version- and mode-dependent. Some interactive or older sessions may lack token-count events, and ephemeral sessions may have no persisted history.

Importer policy:

1. Discover the effective `CODEX_HOME`; do not assume a path.
2. Inventory file versions/shapes before parsing.
3. Parse JSONL streaming; never load or export message content.
4. Use absolute cumulative `total_token_usage` as the preferred accounting source and calculate monotonic deltas between successive events within one logical thread segment.
5. Detect reset/decrease/resume/fork boundaries and start a new segment rather than producing a negative delta.
6. Use the model/provider active at the token event. If model attribution is ambiguous, retain session-level usage with `quality='partial'` rather than guessing.
7. Use `last_token_usage` only as a validation/fallback field after the installed format proves its semantics and duplicate/replay behavior.
8. If a session has metadata but no token usage, include it in the coverage report but do not create zero-token usage.
9. Do not attempt to reconstruct deleted or `--ephemeral` sessions.
10. Keep all Codex backfill in the private ledger.

### OpenCode

OpenCode backfill begins only after Phase 3 inspects the installed version.

Current OpenCode implementations can aggregate stored sessions/messages by provider/model, input/output/reasoning/cache tokens, cost, tools, and date range. The importer must use the actual local database/API schema rather than scraping formatted CLI text as its only source.

Importer policy:

1. Snapshot the real OpenCode database/storage.
2. Prefer assistant-message usage records for model/provider attribution.
3. Reconcile imported totals against `opencode stats` for the same time range when that command exists in the installed version.
4. Keep reasoning and cache as breakdowns; do not reproduce display formulas that double-count subsets in `total_tokens`.
5. Keep OpenCode backfill private unless a later explicit sharing decision changes the scope.

### Server and Windows host telemetry

Do not fabricate pre-monitoring CPU, memory, disk, network, container, or process history. Import only if a pre-existing trusted metrics source is found and separately approved. Ordinary logs are not converted into resource-usage estimates.

## Cutover and double-counting policy

Record a cutover timestamp for every source instance:

```text
codex-main-windows
hermes-main
hermes-owashota
opencode-main-windows
```

Rules:

1. Backfill normally imports records whose effective end/event time is strictly before the instance cutover.
2. Live rollup starts at or after the same cutover.
3. A session that ends before cutover may be imported in full.
4. A session that starts before and ends after cutover is quarantined unless exact turn-level usage can split it at the boundary.
5. Never prorate a session by elapsed time.
6. The quarantine report lists every excluded boundary record and reason.
7. Cutover values live in ignored local configuration and are recorded in sanitized form in the runbook without private host details.

## Deduplication and import runs

Use a stable unique key independent of importer version, for example:

```text
(source_system, source_instance, source_record_id)
```

Maintain separate tables for:

- `import_runs` — parser version, start/end time, source snapshot hash, status, counts;
- `usage_records` — normalized immutable/upserted rows;
- `import_errors` — opaque record key, error class, no message content;
- `cutovers` — source instance and effective timestamp;
- `coverage_reports` — exact/derived/partial/missing counts.

Required behaviors:

- `--inventory` performs no writes;
- `--dry-run` parses, normalizes, and reconciles without production inserts;
- `--import` is transactional per source/import run;
- repeating the same import inserts zero duplicates;
- parser upgrades produce an explicit migration/reconciliation report rather than silently duplicating rows;
- every production import can be rolled back by `import_run_id` after an automatic pre-import ledger backup.

## Reconciliation and quality report

Before production import, generate a local report for each source/instance:

```text
source records discovered
records with exact token usage
records with derived usage
records with partial dimensions
records without usable token data
records quarantined at cutover
input/output/cache/reasoning/total sums
model/provider coverage
user-ID coverage for Hermes
estimated/actual/unknown cost coverage
parse errors
```

Validation methods:

- **Hermes:** compare importer sums with read-only SQL aggregates from the snapshot; compare per-model and per-session totals without summing both representations.
- **Codex:** compare a sample of normalized deltas against raw cumulative events; verify reset/resume handling; report session-file coverage by version/mode.
- **OpenCode:** compare the same date range with the installed `opencode stats` output and direct database aggregates.

A discrepancy must be explained or block import. Do not add an unexplained balancing row.

## Privacy and sharing

Importers may read local source files, but they must not persist or emit:

- prompt/message content;
- assistant responses;
- reasoning text;
- system prompts;
- tool arguments/results;
- Git repository paths or private host paths;
- Cloudflare/Grafana emails;
- secrets or credentials.

The shared ledger may contain:

- Hermes instance;
- Discord accounting ID;
- model/provider;
- token breakdowns;
- cost only if already approved for the shared dashboard;
- time bucket and quality metadata.

It must not contain Codex, OpenCode, server, or Windows history.

## Human gates for Phase 4

### BF1 — Source and retention scope

**Owner: HUMAN / JOINT**

The owner approves which historical directories/databases are scanned, the earliest date, and whether cost is imported. Codex prepares an inventory command that does not print content or secrets.

### BF2 — Cutover and coverage review

**Owner: JOINT**

Codex proposes per-instance cutovers and presents the dry-run coverage/quality report. The owner approves exclusions and accepts documented gaps; no token estimates are introduced to improve coverage.

### BF3 — Production import

**Owner: JOINT**

Codex creates a pre-import backup and exact rollback command. The owner approves the write after reviewing totals. Codex imports and verifies idempotence by running the same manifest again.

### BF4 — Shared publication

**Owner: HUMAN / JOINT**

The owner approves which Hermes historical dimensions/costs are visible to all authorized Discord users. Codex proves the shared data source contains no Codex/OpenCode/private rows before exposing the all-time panels.

## Work packages

### Work package 0 — Read-only inventory

- [ ] Discover actual Codex, Hermes, and OpenCode storage locations and versions.
- [ ] Record counts, date ranges, sizes, schemas, and file-format variants without reading/exporting content fields.
- [ ] Create source snapshots/backups and SHA-256 manifests outside Git.
- [ ] Produce a feasibility matrix and expected coverage.

### Work package 1 — Ledger and schema

- [ ] Add a pinned SQL ledger service and migrations.
- [ ] Create private and Hermes-only shared databases/users.
- [ ] Add least-privilege Grafana read-only users.
- [ ] Implement import-run, cutover, provenance, quality, and rollback tables.
- [ ] Add backup/restore and schema-migration tests.

### Work package 2 — Hermes importer

- [ ] Support the real `state.db` schemas for both instances.
- [ ] Prefer per-model usage rows without duplicating session aggregates.
- [ ] Preserve Discord accounting and model/provider dimensions.
- [ ] Exclude all content-bearing columns/tables.
- [ ] Reconcile and test with synthetic SQLite fixtures.

### Work package 3 — Codex importer

- [ ] Support actual rollout variants found under `CODEX_HOME`.
- [ ] Calculate deltas from cumulative token totals with reset/fork detection.
- [ ] Attribute model/provider only when evidenced.
- [ ] Report files/sessions with no token events.
- [ ] Test malformed, truncated, resumed, forked, duplicate, and reset fixtures.

### Work package 4 — OpenCode importer

- [ ] Confirm the installed storage/API schema after Phase 3.
- [ ] Extract assistant usage by provider/model and token type.
- [ ] Reconcile with direct database totals and `opencode stats` when available.
- [ ] Test duplicate message updates and missing usage fields.

### Work package 5 — Live rollup and all-time views

- [ ] Store per-source cutovers.
- [ ] Add idempotent rollups for closed live buckets.
- [ ] Create normalized private all-time views.
- [ ] Create Hermes-only shared all-time views.
- [ ] Prove no overlap or gap at each cutover, except documented quarantined boundary sessions.

### Work package 6 — Dashboards

Private dashboards:

- [ ] all-time tokens by source, model, provider, and token type;
- [ ] backfill versus live-rollup coverage;
- [ ] exact/derived/partial quality;
- [ ] missing/unrecoverable session counts;
- [ ] estimated versus actual/unknown cost.

Shared dashboards:

- [ ] all-time Hermes tokens by Discord `user.id`;
- [ ] model/provider and instance breakdown;
- [ ] backfill/live and quality indicators;
- [ ] no Codex/OpenCode/server/Windows data source or row.

### Work package 7 — Runbook and verification

- [ ] inventory, snapshot, dry-run, import, reconcile, rollback, and rerun procedures;
- [ ] source-version compatibility table;
- [ ] cutover and quarantine procedures;
- [ ] private/shared backup and deletion procedures;
- [ ] parser-upgrade procedure;
- [ ] sanitized coverage evidence with no real IDs, paths, emails, or content.

## Expected repository layout

```text
backfill/
├── README.md
├── schema/
├── importers/
│   ├── codex/
│   ├── hermes/
│   └── opencode/
├── rollup/
├── tests/
│   └── fixtures/          # synthetic only
└── scripts/

docs/
├── phase-4-backfill.md
├── backfill-runbook.md
└── backfill-coverage.example.md

grafana/
├── private/dashboards/
└── shared/dashboards/
```

No real source snapshot, telemetry row, Discord ID, email, private path, or database dump is committed.

## Acceptance criteria

Phase 4 is complete only when all are true:

1. Source snapshots are read-only and backed up.
2. Inventory and dry-run work without writing production rows.
3. Every imported row has provenance, parser version, import run, quality, and original time.
4. Canonical totals do not add cache/reasoning subsets twice.
5. Re-running the same manifest produces zero duplicates.
6. A production import can be rolled back by import run and restored from backup.
7. Backfill stops before each live cutover; live rollup starts at/after it.
8. Boundary-spanning records are exactly split or quarantined, never prorated.
9. Hermes source totals reconcile and both instances remain distinguishable.
10. Codex coverage and unrecoverable sessions are reported honestly.
11. OpenCode totals reconcile against the installed database/CLI behavior.
12. Private all-time dashboards combine historical and live-rollup data without double count.
13. Shared all-time dashboards contain Hermes only and preserve Discord user/model accounting.
14. No prompt, response, reasoning text, tool payload, private path, email, or secret is imported.
15. Missing fields remain unknown; no fabricated token or infrastructure history exists.
16. BF1–BF4 are completed or explicitly deferred with the limitation documented.
17. Runbook, tests, rollback, and sanitized verification evidence are complete.

## Known limitations to preserve visibly

- Deleted, ephemeral, or never-persisted sessions cannot be recovered.
- Codex historical coverage may differ between CLI modes and versions.
- Old Hermes schemas may not contain cache, reasoning, cost, or per-model dimensions.
- A session-level aggregate cannot be assigned precisely across multiple models without per-model evidence.
- Historical latency, retries, tool duration, and errors may be unavailable even when token totals exist.
- Plan/subscription credit consumption is not equivalent to tokens and is not reconstructed.
- Historical host resource telemetry is unavailable unless it was already recorded by a trusted monitoring system.
