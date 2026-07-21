# Phase 4 backfill tooling

The first work package inventories Codex and Hermes history without persisting
prompt, response, reasoning, tool, message, repository-path, or host-path data.
OpenCode is deliberately out of scope for this implementation slice.

## Codex inventory

The inventory reads only `sessions/**/*.jsonl` and
`archived_sessions/**/*.jsonl` beneath the effective `CODEX_HOME`. It parses all
records as a stream but retains only event classifications, safe client/model
dimensions, timestamp coverage, token-field types, opaque path hashes, and file
statistics.

```powershell
python -m backfill.inventory codex `
  --output backfill/reports/codex-inventory.local.json
```

It never reads `auth.json` or other Codex credential/state files. The output
directory is ignored by Git and an existing report is never overwritten.

Create the BF1-approved local snapshot only after checking free space:

```powershell
python -m backfill.snapshot_codex `
  --destination backfill/snapshots/codex-<UTC_TIMESTAMP> `
  --dry-run
python -m backfill.snapshot_codex `
  --destination backfill/snapshots/codex-<UTC_TIMESTAMP>
```

The snapshot refuses an existing destination, requires at least twice the source
size as free space, and reports any source file that changed while it was copied.
An unstable snapshot is not eligible for import.

## Hermes snapshots and inventory

Run the snapshot helper on the Docker host. It uses SQLite's online backup API
against `/opt/data/state.db` in read-only mode, copies the result to a restricted
host directory, and writes a SHA-256 sidecar.

```bash
./backfill/scripts/snapshot-hermes.sh \
  --container <HERMES_CONTAINER> \
  --instance main \
  --output-dir <IGNORED_RESTRICTED_SNAPSHOT_DIR> \
  --dry-run
```

Repeat for `owashota`, then inventory each copied snapshot:

```bash
python3 -m backfill.inventory hermes \
  --snapshot <SNAPSHOT_STATE_DB> \
  --instance main \
  --output backfill/reports/hermes-main-inventory.local.json
```

The Hermes inventory queries only `schema_version`, `sessions`, and
`session_model_usage`. It never selects `messages`, FTS tables, prompt/system
columns, reasoning, tool payloads, display names, IDs, or paths. Per-model usage
is the preferred import candidate; session aggregates are reconciliation-only
and must not be added to it.

## Verification

```text
python -m unittest discover -s backfill/tests -v
```

Fixtures are synthetic. A canary test fails if content or a user ID is emitted.
