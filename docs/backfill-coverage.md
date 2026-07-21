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
| Provider-recorded estimated cost rows | 14 | 1,790 |
| Provider-recorded actual cost rows | 14 | 1,790 |
| Retained usage range | 2026-07-12 through 2026-07-21 UTC | 2026-07-12 through 2026-07-21 UTC |

Both snapshots contain `session_model_usage`. The importer must choose usage per
session: import all populated per-model rows for that session, otherwise import
the session aggregate once. It must never add the complete per-model and session
representations together.

## Privacy and feasibility result

- Inventory retained no prompt, response, reasoning, tool, message, email,
  Discord-ID value, repository path, host path, credential, or secret.
- Hermes `messages` and FTS tables were not queried.
- Codex credential/state files outside session and archived-session JSONL were
  not opened.
- Codex and both Hermes sources are feasible for importer implementation.
- Cost values remain private; shared cost publication is deferred to BF4.
- No production ledger row has been written.
