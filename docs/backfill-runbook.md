# Phase 4 backfill runbook

This runbook currently covers BF1 read-only inventory and BF2 dry-run
preparation for Codex and Hermes only. It does not authorize production ledger
writes.

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

## Rollback

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

Ledger restore replaces data and requires a fresh H10 packet. After approval,
Codex supplies the exact backup directory to:

```bash
H10_APPROVED=yes ./backfill/scripts/restore-ledgers.sh \
  --confirm-restore <LEDGER_BACKUP_DIRECTORY>
```

The restore verifies hashes and archive structure, creates private/shared
pre-restore dumps, automatically rolls back on failure, and retains the rollback
dumps after success.
