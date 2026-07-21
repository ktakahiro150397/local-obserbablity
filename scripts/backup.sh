#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd -- "${repo_dir}"

if [[ ! -s .env ]]; then
  echo "Missing .env." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source ./.env
set +a

backup_root=${1:-${HOME}/local-observability-backups}
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
backup_dir="${backup_root}/${timestamp}"
mkdir -p -- "${backup_dir}"
chmod 700 -- "${backup_root}" "${backup_dir}"

mapfile -t running_before < <(docker compose ps --status running --services)
restart_services=()
for service in private-lgtm shared-lgtm otel-router; do
  for running in "${running_before[@]}"; do
    if [[ "${running}" == "${service}" ]]; then
      restart_services+=("${service}")
      break
    fi
  done
done

restart_needed=0
restart_stacks() {
  if [[ "${restart_needed}" -eq 1 && "${#restart_services[@]}" -gt 0 ]]; then
    docker compose up -d --wait "${restart_services[@]}" >/dev/null
  fi
}
trap restart_stacks EXIT

if [[ "${#restart_services[@]}" -gt 0 ]]; then
  docker compose stop "${restart_services[@]}"
fi
restart_needed=1

tar --numeric-owner --xattrs -C "$(dirname -- "${PRIVATE_DATA_DIR}")" \
  -czf "${backup_dir}/private.tar.gz" "$(basename -- "${PRIVATE_DATA_DIR}")"
tar --numeric-owner --xattrs -C "$(dirname -- "${SHARED_DATA_DIR}")" \
  -czf "${backup_dir}/shared.tar.gz" "$(basename -- "${SHARED_DATA_DIR}")"

sha256sum "${backup_dir}/private.tar.gz" "${backup_dir}/shared.tar.gz" \
  >"${backup_dir}/SHA256SUMS"
chmod 600 -- "${backup_dir}"/*

restart_stacks
restart_needed=0
trap - EXIT

echo "Backup complete: ${backup_dir}"
echo "The ignored .env and tunnel token are not included; back them up separately in an approved secret store."
