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

The Hermes inventory queries only `schema_version`, `sessions`, and, when
present, `session_model_usage`. It never selects `messages`, FTS tables,
prompt/system columns, reasoning, tool payloads, display names, IDs, or paths.
Per-model usage is preferred for current schema v20. Legacy schemas 11 and 13
have no per-model table, so their session aggregate is the import candidate and
model attribution is marked derived.

## Verification

```text
python -m unittest discover -s backfill/tests -v
```

Fixtures are synthetic. Inventory canaries fail on content or identity output;
importer canaries fail on content or unhashed native session identifiers while
allowing only the approved normalized Discord accounting ID.

## Content-safe dry run

Normalize the approved snapshots into ignored JSONL manifests before BF2. The
commands refuse to overwrite an existing manifest or report. Cutovers use UTC
timestamps taken from the first verified live usage span for each instance.

```powershell
python -m backfill.importers.codex `
  --snapshot-root <CODEX_SNAPSHOT_DATA> `
  --snapshot-manifest <CODEX_SNAPSHOT_MANIFEST> `
  --cutover <CODEX_CUTOVER_UTC> `
  --output-manifest backfill/staging/codex-private.local.jsonl `
  --output-report backfill/reports/codex-dry-run.local.json
```

```bash
python3 -m backfill.importers.hermes \
  --snapshot <HERMES_STATE_DB_SNAPSHOT> \
  --instance <main|owashota> \
  --cutover <INSTANCE_CUTOVER_UTC> \
  --output-manifest backfill/staging/hermes-private.local.jsonl \
  --output-report backfill/reports/hermes-dry-run.local.json
```

The JSONL shape is an exact allow-list matching the ledger schema. Native file,
session, and source record identifiers are one-way hashed except for approved
Hermes `user_id=discord:<numeric-id>` accounting values. Reports contain only
aggregate coverage, token, cost-quality, and dimension counts. Neither output
contains prompt, response, reasoning, message, tool, or path fields.

Hermes rows with no direct Discord user may inherit one only by recursively
following the same immutable database's `parent_session_id` chain to a session
with a valid direct Discord user. This covers delegated subagents and
compression continuations without time/model heuristics. Missing parents,
cycles, and chains that never reach a direct Discord identity remain unknown.
Inherited rows carry a `_user_inherited` suffix in `quality_reason`; raw parent
or session IDs are never written to the manifest.

`--shared` is only a manifest-generation test until BF4. It strips all cost and
pricing fields and does not authorize loading or publishing the result.

## Ledger services

Phase 4 uses two independently persisted PostgreSQL 17.10 services. The private
service can hold Codex and Hermes. The shared service has database constraints
that reject every non-Hermes row and every row not marked `shared_eligible`.
Shared Grafana receives only a read-only login for shared views; it has no
network route or credential for the private ledger.

`scripts/init-local-env.sh` creates six unrelated mode-0600 passwords under the
ignored `secrets/` directory. PostgreSQL copies them into a private in-container
tmpfs before dropping privileges; host secret modes are not weakened.

```bash
./scripts/init-local-env.sh
./scripts/stack.sh up
./backfill/scripts/verify-ledgers.sh
./backfill/scripts/backup-ledgers.sh
```

Apply an idempotent schema update with `migrate-ledgers.sh`. A ledger restore is
destructive, creates automatic rollback dumps first, and requires immediate H10
approval through the guard in `restore-ledgers.sh`.

## BF3 manifest validation and private import

`load_manifest.py` validates every JSONL field, deterministic record ID, source
record hash, approved cutover, report metadata, timestamp, UUID, token/cost
type, and the no-estimates rule before opening PostgreSQL. Validation does not
need credentials and is safe before BF3:

```bash
python3 -m backfill.load_manifest \
  --manifest <IGNORED_PRIVATE_MANIFEST> \
  --report <IGNORED_PRIVATE_REPORT> \
  --cutovers <IGNORED_APPROVED_CUTOVERS> \
  --validate-only
```

After the exact pre-import backup and BF3 approval, the same artifact can be
loaded into the private ledger with:

```bash
BF3_APPROVED=yes python3 -m backfill.load_manifest \
  --manifest <IGNORED_PRIVATE_MANIFEST> \
  --report <IGNORED_PRIVATE_REPORT> \
  --cutovers <IGNORED_APPROVED_CUTOVERS> \
  --write-private
```

Each manifest is one serializable transaction. A record-ID/hash conflict or a
cutover violation aborts the whole transaction. Re-running an unchanged
manifest keeps its original import run and reports `inserted=0`. The
`--write-isolated-test` operation is restricted to a container named with the
`phase4-loader-test-` prefix and separately requires `BF3_TEST_ONLY=yes`; it
cannot target the Compose private ledger.

Rolling back completed import runs deletes only their private usage/error/
coverage rows, marks the runs rolled back, and requires a separate immediate
approval guard:

```bash
BF3_ROLLBACK_APPROVED=yes ./backfill/scripts/rollback-import-runs.sh \
  --confirm-private-rollback <IMPORT_RUN_UUID> [<IMPORT_RUN_UUID> ...]
```

The verified pre-import dump remains the full-database recovery path. No shared
ledger write is implemented or authorized before BF4.
