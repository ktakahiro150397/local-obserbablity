#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
cd -- "${repo_dir}"
backup_root=${1:-${HOME}/local-observability-backups}
backup_dir="${backup_root}/phase4-$(date -u +%Y%m%dT%H%M%SZ)"
umask 077
mkdir -p -- "${backup_dir}"
chmod 700 -- "${backup_root}" "${backup_dir}"

for domain in private shared; do
  docker compose exec -T "${domain}-ledger" \
    pg_dump --username ledger_admin --dbname usage_ledger --format custom \
    >"${backup_dir}/${domain}-ledger.dump"
  docker compose exec -T "${domain}-ledger" pg_restore --list \
    <"${backup_dir}/${domain}-ledger.dump" >/dev/null
done
sha256sum "${backup_dir}/private-ledger.dump" "${backup_dir}/shared-ledger.dump" \
  >"${backup_dir}/SHA256SUMS"
chmod 600 -- "${backup_dir}"/*
printf 'Ledger backup complete with two verified dump candidates.\n'
