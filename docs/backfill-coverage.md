# Phase 4 BF1 sanitized coverage

Inventory date: 2026-07-22. Detailed reports, paths, hashes, IDs, model totals,
and costs remain in ignored restricted local storage.

## Codex

| Check | Result |
|---|---:|
| JSONL files | 367 |
| Bytes | approximately 3.81 GB |
| JSONL records | 439,194 |
| Invalid JSON records | 0 |
| Files containing token events | 365 |
| Files without token events | 2 |
| Token events | 143,926 |
| Retained timestamp range | 2026-04-21 through 2026-07-21 UTC |
| Snapshot files changed during copy | 0 |

The retained data contains the planned cumulative `total_token_usage` and
`last_token_usage` structures. Input, output, cached input, cache-write input,
reasoning output, and total token fields are numeric where present. Multiple
Codex CLI/Desktop versions and originators exist, so parser compatibility must
be based on observed record shapes rather than one client version.

Two files have no token event. They remain coverage records and must not become
zero-token usage rows.

## Hermes

### Current schema-v20 snapshots

| Check | `main` | `owashota` |
|---|---:|---:|
| Schema version | 20 | 20 |
| Sessions | 14 | 1,790 |
| Sessions with a user ID | 10 | 88 |
| Per-model usage rows | 14 | 1,790 |
| Sessions represented by per-model rows | 14 | 1,776 |
| Sessions without a per-model row | 0 | 14 |
| Extra rows from multi-model sessions | 0 | 14 |
| Per-model/session token sums reconcile | Yes | Yes |
| Non-null estimated/actual cost columns | 14 | 1,790 |
| Cost status | 14 unknown | 1,584 included; 206 unknown |
| Retained usage range | 2026-07-12 through 2026-07-21 UTC | 2026-07-12 through 2026-07-21 UTC |

Both snapshots contain `session_model_usage`. The importer must choose usage per
session: import all populated per-model rows for that session, otherwise import
the session aggregate once. It must never add the complete per-model and session
representations together.

Non-null cost columns are not sufficient proof of an actual charge. Rows with
`cost_status=unknown` remain unknown. `included` rows may retain their reported
zero actual cost privately; shared manifests remove all cost fields until BF4.
Rows marked `estimated` or `calculated` are also normalized to unknown because
BF1 approved provider-reported cost only and explicitly rejected estimates.

Hermes schema v20 stores uncached input, cache-read input, and cache-write input
as separate additive buckets. This was confirmed against the installed Hermes
`CanonicalUsage.prompt_tokens` and the plugin's live OTel mapping. The importer
therefore normalizes `input_tokens` as their sum, retains both cache fields as
breakdowns, and calculates `total_tokens` as normalized input plus output. This
matches the live `gen_ai.usage.input_tokens` and avoids treating cache as an
additional amount a second time in dashboards.

### Pre-migration snapshots

The July deployment migration preserved separate SQLite usage databases outside
the current runtime directories. Online SQLite backups were added to the
restricted BF1 snapshot set. All passed `integrity_check`, and no session ID is
duplicated across legacy, profile, or current snapshots.

| Snapshot role | Schema | Sessions | Nonzero usage sessions | Retained range (UTC) |
|---|---:|---:|---:|---|
| main legacy primary | 11 | 613 | 504 | 2026-04-26 through 2026-05-19 |
| main coordinator profile | 11 | 317 | 302 | 2026-05-19 through 2026-07-01 |
| main researcher profile | 11 | 5 | 5 | 2026-05-19 |
| owashota legacy primary | 13 | 1,743 | 1,670 | 2026-05-01 through 2026-07-12 |
| owashota legacy profiles | 13 | 13 | 13 | 2026-06-03 |

Legacy schemas do not contain `session_model_usage`; their session aggregate is
the only exact token bucket available and model attribution is marked derived.
The owashota database has retained sessions beginning May 1, but its first
nonzero token session begins May 6 UTC (May 7 JST). Zero-usage sessions are
coverage-only and are not emitted as usage rows.

## Privacy and feasibility result

- Inventory retained no prompt, response, reasoning, tool, message, email,
  Discord-ID value, repository path, host path, credential, or secret.
- Hermes `messages` and FTS tables were not queried.
- Codex credential/state files outside session and archived-session JSONL were
  not opened.
- Codex and current/legacy Hermes sources are feasible for importer
  implementation.
- Cost values remain private; shared cost publication is deferred to BF4.
- No production ledger row has been written.
