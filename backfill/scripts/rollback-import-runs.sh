#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
cd -- "${repo_dir}"

if [[ ${BF3_ROLLBACK_APPROVED:-no} != yes || ${1:-} != --confirm-private-rollback ]]; then
  echo "Deleting imported private usage requires explicit BF3 rollback approval." >&2
  echo "After approval: BF3_ROLLBACK_APPROVED=yes $0 --confirm-private-rollback <import-run-id> [...]" >&2
  exit 2
fi
shift
if [[ $# -eq 0 ]]; then
  echo "At least one import-run UUID is required." >&2
  exit 2
fi
for run_id in "$@"; do
  [[ ${run_id} =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$ ]] || {
    echo "Invalid import-run UUID." >&2
    exit 2
  }
done

{
  printf '\\set ON_ERROR_STOP on\nBEGIN;\n'
  for run_id in "$@"; do
    printf "DO \$\$ BEGIN IF NOT EXISTS (SELECT 1 FROM usage.import_runs WHERE import_run_id='%s'::uuid AND status='complete' FOR UPDATE) THEN RAISE EXCEPTION 'import run is missing or not complete'; END IF; END \$\$;\n" "${run_id}"
    printf "DELETE FROM usage.usage_records WHERE import_run_id='%s'::uuid;\n" "${run_id}"
    printf "DELETE FROM usage.coverage_reports WHERE import_run_id='%s'::uuid;\n" "${run_id}"
    printf "DELETE FROM usage.import_errors WHERE import_run_id='%s'::uuid;\n" "${run_id}"
    printf "UPDATE usage.import_runs SET status='rolled_back',finished_at=CURRENT_TIMESTAMP,inserted_count=0,updated_count=0,skipped_count=0 WHERE import_run_id='%s'::uuid;\n" "${run_id}"
  done
  printf 'COMMIT;\n'
} | docker compose exec -T private-ledger psql \
  --quiet --username ledger_writer --dbname usage_ledger

echo "Approved private import runs were rolled back; the pre-import backup remains the full restore path."
