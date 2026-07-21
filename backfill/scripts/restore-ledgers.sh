#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
cd -- "${repo_dir}"

if [[ ${H10_APPROVED:-no} != yes || ${1:-} != --confirm-restore ]]; then
  echo "Ledger restore replaces imported usage and requires H10 approval." >&2
  echo "After approval: H10_APPROVED=yes $0 --confirm-restore <backup-dir>" >&2
  exit 2
fi

backup_dir=${2:-}
if [[ -z "${backup_dir}" || ! -f "${backup_dir}/SHA256SUMS" ]]; then
  echo "A ledger backup directory containing SHA256SUMS is required." >&2
  exit 2
fi
(cd -- "${backup_dir}" && sha256sum -c SHA256SUMS)
for domain in private shared; do
  [[ -f "${backup_dir}/${domain}-ledger.dump" ]]
  docker compose exec -T "${domain}-ledger" pg_restore --list \
    <"${backup_dir}/${domain}-ledger.dump" >/dev/null
done

rollback_root="${HOME}/local-observability-restore-rollback/phase4-$(date -u +%Y%m%dT%H%M%SZ)"
umask 077
mkdir -p -- "${rollback_root}"
chmod 700 -- "${rollback_root}"
for domain in private shared; do
  docker compose exec -T "${domain}-ledger" \
    pg_dump --username ledger_admin --dbname usage_ledger --format custom \
    >"${rollback_root}/${domain}-ledger.dump"
done
sha256sum "${rollback_root}/private-ledger.dump" "${rollback_root}/shared-ledger.dump" \
  >"${rollback_root}/SHA256SUMS"
chmod 600 -- "${rollback_root}"/*

restore_dump() {
  local domain=$1
  local dump=$2
  docker compose exec -T "${domain}-ledger" pg_restore \
    --username ledger_admin \
    --dbname usage_ledger \
    --clean --if-exists --exit-on-error \
    <"${dump}"
}

restore_failed=false
for domain in private shared; do
  if ! restore_dump "${domain}" "${backup_dir}/${domain}-ledger.dump"; then
    restore_failed=true
    break
  fi
done

if ${restore_failed}; then
  echo "Restore failed; restoring the automatic pre-restore dumps." >&2
  for domain in private shared; do
    restore_dump "${domain}" "${rollback_root}/${domain}-ledger.dump"
  done
  exit 1
fi

./backfill/scripts/verify-ledgers.sh
echo "Ledger restore complete; recoverable pre-restore dumps were retained."
