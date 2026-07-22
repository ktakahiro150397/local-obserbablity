# Phase 4 backfill runbook

This runbook covers BF1 through BF4 for Codex and Hermes only. BF3 private and
BF4 cost-free Hermes shared imports are complete. Further shared dimensions,
cost publication, rollback, source deletion, and OpenCode remain separately
gated.

## Approved BF1 scope

- effective `CODEX_HOME` session and archived-session JSONL;
- Hermes `main` and `owashota` `state.db` snapshots;
- pre-migration main/owashota and profile `state.db` files discovered in the
  retained migration data directory, as explicitly authorized after BF1;
- oldest retained history through each source's later-approved cutover;
- provider-recorded costs in private inventory only, without estimates;
- no OpenCode, host history, content fields, credentials, or identity mappings;
- snapshots retained through BF3 verification plus 30 days unless superseded by
  an explicit retention decision.

## Safety invariants

1. Run inventory without production database credentials.
2. Never point the Hermes inventory at the live bind-mounted source; use the
   SQLite backup produced by `snapshot-hermes.sh`.
3. Keep snapshots, manifests, reports, hashes, paths, IDs, and totals in ignored
   restricted local storage.
4. Do not commit or paste local reports into issues or pull requests.
5. A changed-during-copy Codex file blocks use of that snapshot.
6. Do not delete snapshots without the applicable destructive-action approval.

## Work package 0 sequence

1. Run the Codex snapshot dry-run and confirm the required/free-byte summary.
2. Create the Codex snapshot and require `unstable_files=0`.
3. Create one SQLite snapshot for each Hermes instance and verify its sidecar.
4. Run `backfill.inventory` against the Codex source and both Hermes snapshots.
5. Store the three reports outside Git under `backfill/reports/`.
6. Record only sanitized feasibility counts and schema compatibility in the PR.
7. Propose source-specific cutovers and coverage for BF2; do not import yet.

## BF2 dry-run sequence

1. Query private Tempo for the earliest retained, verified usage-bearing live
   span for Codex, Hermes main, and Hermes owashota.
2. Store proposed UTC cutovers only in ignored `backfill/cutovers.local.json`.
3. Run the Codex and Hermes importers from `backfill/README.md` against the BF1
   snapshots. Do not provide database credentials.
4. Review aggregate record quality, token sums, dimension coverage, cost
   quality, live-period exclusions, and boundary quarantines.
5. Verify the manifest uses only the canonical allow-listed fields and that the
   synthetic content canary tests pass.
6. Present one BF2 approval packet. Production import remains blocked until the
   owner approves the exact cutovers and documented gaps.

## BF3 preparation and execution

1. Set the ignored cutover file status to `approved` only after BF2 approval.
2. Generate final private manifests from the immutable snapshots. Zero-usage
   Hermes rows and all events at/after the approved cutover remain excluded;
   boundary rows are quarantined rather than prorated.
   For Hermes only, resolve a missing user through `parent_session_id` when the
   chain reaches a valid direct Discord identity; mark the row inherited and
   leave every missing/ambiguous chain unknown.
3. Validate each manifest with `backfill.load_manifest --validate-only`.
4. Load all final manifests twice into an isolated test PostgreSQL container.
   The first pass must equal the reviewed counts; every second-pass result must
   say `inserted=0`.
5. Prove a changed source-record hash aborts its complete transaction without
   changing row/import-run counts.
6. Start and migrate the empty production ledger services without loading
   usage, verify private/shared constraints, and create the exact verified
   pre-import dumps.
7. Present one BF3 packet containing final counts/totals, import-run UUIDs,
   backup stamp, import command, rerun expectation, and rollback command.
8. Only after approval, set `BF3_APPROVED=yes` for the reviewed commands. Do not
   set the guard persistently or use it for isolated tests.
9. Re-run the same ten manifests, require zero inserts, reconcile source and
   database sums, and preserve sanitized evidence.

If a later approved rollback is required, pass exactly the reviewed import-run
UUIDs to `rollback-import-runs.sh`. Restoring both database dumps is a broader
destructive action and still uses the separate H10 restore gate.

The SQLite lineage correction applies only before the cutover. The separate
`backup-secretary` fix now propagates the parent's sender/user accounting onto
delegated child root, LLM, and API spans, and a real delegated Discord turn was
verified in both private and shared telemetry. Container recreation must still
preserve the reviewed fixed image and collector-network attachment until the
separate runtime Compose change is merged.

## BF4 preparation and execution

1. Generate fresh cost-free shared manifests from the same nine immutable
   Hermes snapshots used for BF3, with the same approved per-instance cutovers.
   Never republish the private manifests.
2. Validate every candidate with `--validate-shared-only`. Require Hermes-only
   rows, `shared_eligible=true`, numeric Discord accounting IDs or null, and no
   estimated/actual cost or pricing fields.
3. Load all candidates twice into an isolated shared-schema PostgreSQL
   container. First-pass inserted counts must equal the manifests; every
   second-pass result must say `BF4_RESULT inserted=0`.
4. Reconcile record/token totals and lineage-inherited counts with the approved
   BF3 Hermes subset. A difference blocks publication.
5. Prove the production shared ledger contains no historical usage, no Codex or
   OpenCode rows, and no non-Hermes import/cutover metadata.
6. Create and hash-verify an exact pre-write private/shared ledger backup. The
   private dump is included so the isolation baseline is recoverable, even
   though BF4 writes only shared.
7. Present one BF4 packet containing the publication dimensions, cost exclusion,
   exact counts/totals, import-run UUIDs, backup stamp, guarded commands, rerun
   expectation, and rollback command.
8. Only after approval, set `BF4_APPROVED=yes` for each reviewed
   `--write-shared` command. Do not persist the guard.
9. Re-run the same nine manifests, require zero inserts, reconcile all sums, and
   verify shared contains only approved Hermes history while private counts are
   unchanged.
10. Provision the historical shared dashboard only after the shared-data checks
    pass. It may expose instance, numeric Discord accounting ID, model/provider,
    token breakdown, time, and quality metadata; it must not expose cost or any
    content field.

The safe BF4 default is cost-free. Publishing provider-reported costs later
requires a separate explicit owner decision and regenerated/revalidated
artifacts; the BF4 loader rejects costs in shared candidates.

## Inventory rollback

Inventory makes no source or production-ledger writes. Before BF3, rollback means
removing only the newly created ignored report/snapshot directory after verifying
the exact path and retention approval. Source Codex/Hermes data is never changed.

## Ledger operations

The pinned ledger image is PostgreSQL `17.10-bookworm` at OCI index digest
`sha256:4f736ae292687621d4dbe0d499ffd024a36bd2ee7d8ca6f2ccd4c800f047b394`.
Private and shared use different containers, named volumes, networks, admin
passwords, writer passwords, and Grafana reader passwords.

```bash
./scripts/init-local-env.sh
./scripts/stack.sh up
./backfill/scripts/migrate-ledgers.sh
./backfill/scripts/verify-ledgers.sh
./backfill/scripts/backup-ledgers.sh
```

The shared schema rejects Codex/OpenCode and rows without `shared_eligible=true`.
Grafana readers can query `grafana.*` views only and cannot use the underlying
`usage` schema.

After BF4 cutovers, `hermes-live-rollup` advances a separate checkpoint per
Hermes instance and writes `record_origin='live_rollup'` rows at or after the
approved cutover. It runs every five minutes, re-reads 30 minutes, and upserts
by an opaque trace/span-derived key. The historical importer remains strictly
before cutover, so the two origins do not overlap.

Ledger restore replaces data and requires a fresh H10 packet. After approval,
Codex supplies the exact backup directory to:

```bash
H10_APPROVED=yes ./backfill/scripts/restore-ledgers.sh \
  --confirm-restore <LEDGER_BACKUP_DIRECTORY>
```

The restore verifies hashes and archive structure, creates private/shared
pre-restore dumps, automatically rolls back on failure, and retains the rollback
dumps after success.
