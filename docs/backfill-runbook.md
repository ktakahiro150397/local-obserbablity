# Phase 4 backfill runbook

This runbook currently covers BF1 read-only inventory and snapshots for Codex
and Hermes only. It does not authorize production ledger writes.

## Approved BF1 scope

- effective `CODEX_HOME` session and archived-session JSONL;
- Hermes `main` and `owashota` `state.db` snapshots;
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

## Rollback

Inventory makes no source or production-ledger writes. Before BF3, rollback means
removing only the newly created ignored report/snapshot directory after verifying
the exact path and retention approval. Source Codex/Hermes data is never changed.
