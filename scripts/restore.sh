#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd -- "${repo_dir}"

if [[ ${H10_APPROVED:-no} != yes || ${1:-} != --confirm-restore ]]; then
  echo "Restore replaces live telemetry data and requires H10 approval." >&2
  echo "After approval: H10_APPROVED=yes $0 --confirm-restore <backup-dir>" >&2
  exit 2
fi

backup_dir=${2:-}
if [[ -z "${backup_dir}" || ! -f "${backup_dir}/SHA256SUMS" ]]; then
  echo "A backup directory containing SHA256SUMS is required." >&2
  exit 2
fi

set -a
# shellcheck disable=SC1091
source ./.env
set +a

(cd -- "${backup_dir}" && sha256sum -c SHA256SUMS)

for target in "${PRIVATE_DATA_DIR}" "${SHARED_DATA_DIR}"; do
  case "${target}" in
    "${HOME}"/local-observability-data/private|"${HOME}"/local-observability-data/shared) ;;
    *) echo "Refusing unexpected restore target: ${target}" >&2; exit 3 ;;
  esac
done

rollback_root="${HOME}/local-observability-restore-rollback/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p -- "${rollback_root}"
chmod 700 -- "${rollback_root}"

docker compose stop otel-router private-lgtm shared-lgtm
mv -- "${PRIVATE_DATA_DIR}" "${rollback_root}/private"
mv -- "${SHARED_DATA_DIR}" "${rollback_root}/shared"
mkdir -p -- "$(dirname -- "${PRIVATE_DATA_DIR}")" "$(dirname -- "${SHARED_DATA_DIR}")"
tar --numeric-owner --xattrs -C "$(dirname -- "${PRIVATE_DATA_DIR}")" -xzf "${backup_dir}/private.tar.gz"
tar --numeric-owner --xattrs -C "$(dirname -- "${SHARED_DATA_DIR}")" -xzf "${backup_dir}/shared.tar.gz"
docker compose up -d --wait private-lgtm shared-lgtm otel-router

echo "Restore complete. Recoverable pre-restore data is at ${rollback_root}."
