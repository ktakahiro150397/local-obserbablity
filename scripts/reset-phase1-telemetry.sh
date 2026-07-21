#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd -- "${repo_dir}"

if [[ ${H10_APPROVED:-no} != yes || ${1:-} != --confirm-reset-telemetry ]]; then
  echo "Telemetry reset is irreversible and requires immediate H10 approval." >&2
  echo "After approval: H10_APPROVED=yes $0 --confirm-reset-telemetry" >&2
  exit 2
fi

set -a
# shellcheck disable=SC1091
source ./.env
set +a

expected_root="${HOME}/local-observability-data"
for target in "${PRIVATE_DATA_DIR}" "${SHARED_DATA_DIR}"; do
  case "${target}" in
    "${expected_root}/private"|"${expected_root}/shared") ;;
    *) echo "Refusing unexpected telemetry reset target." >&2; exit 3 ;;
  esac
  [[ -d "${target}" ]] || { echo "Telemetry reset target is missing." >&2; exit 3; }
  [[ "$(readlink -f -- "${target}")" == "${target}" ]] || {
    echo "Telemetry reset target must not be a symlink." >&2
    exit 3
  }
done

quarantine_parent="${HOME}/local-observability-reset-quarantine"
quarantine_root="${quarantine_parent}/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p -- "${quarantine_root}"
chmod 700 -- "${quarantine_parent}" "${quarantine_root}"

rollback() {
  local status=$?
  trap - ERR INT TERM
  set +e
  docker compose stop otel-router private-lgtm shared-lgtm >/dev/null 2>&1
  if [[ -d "${quarantine_root}/private" ]]; then
    rm -rf -- "${PRIVATE_DATA_DIR}"
    mv -- "${quarantine_root}/private" "${PRIVATE_DATA_DIR}"
  fi
  if [[ -d "${quarantine_root}/shared" ]]; then
    rm -rf -- "${SHARED_DATA_DIR}"
    mv -- "${quarantine_root}/shared" "${SHARED_DATA_DIR}"
  fi
  rmdir -- "${quarantine_root}" 2>/dev/null || true
  docker compose up -d --wait private-lgtm shared-lgtm otel-router >/dev/null 2>&1
  echo "Telemetry reset failed; the prior data was restored." >&2
  exit "${status}"
}
trap rollback ERR INT TERM

docker compose stop otel-router private-lgtm shared-lgtm
mv -- "${PRIVATE_DATA_DIR}" "${quarantine_root}/private"
mv -- "${SHARED_DATA_DIR}" "${quarantine_root}/shared"
mkdir -p -- \
  "${PRIVATE_DATA_DIR}/tempo-runtime" \
  "${SHARED_DATA_DIR}/tempo-runtime"
chmod 700 -- \
  "${expected_root}" \
  "${PRIVATE_DATA_DIR}" \
  "${PRIVATE_DATA_DIR}/tempo-runtime" \
  "${SHARED_DATA_DIR}" \
  "${SHARED_DATA_DIR}/tempo-runtime"

docker compose up -d --wait private-lgtm shared-lgtm otel-router
./scripts/smoke-test.sh

trap - ERR INT TERM
resolved_quarantine=$(readlink -f -- "${quarantine_root}")
case "${resolved_quarantine}" in
  "${quarantine_parent}"/*) ;;
  *) echo "Refusing unexpected quarantine deletion target." >&2; exit 4 ;;
esac
rm -rf -- "${resolved_quarantine}"

echo "Phase 1 telemetry reset complete; prior private/shared data was permanently removed after a successful clean-stack smoke test."
