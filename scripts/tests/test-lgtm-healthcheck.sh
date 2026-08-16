#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
check=${repo_dir}/scripts/lgtm-healthcheck.sh
tmp=$(mktemp -d)
trap 'rm -rf -- "${tmp}"' EXIT

mkdir -p -- "${tmp}/bin" "${tmp}/state"
cat >"${tmp}/bin/curl" <<'EOF'
#!/usr/bin/env bash
[[ ${TEST_CURL_RESULT:-ok} == ok ]]
EOF
chmod +x "${tmp}/bin/curl"

run_check() {
  PATH="${tmp}/bin:${PATH}" \
  LGTM_HEALTHCHECK_STATE_DIR="${tmp}/state" \
  LGTM_HEALTHCHECK_INSTANCE_TOKEN=test-instance \
  LGTM_HEALTHCHECK_MIN_UPTIME_SECONDS=0 \
  LGTM_HEALTHCHECK_FAILURE_LIMIT=2 \
  LGTM_HEALTHCHECK_RESTART_ENABLED=false \
  LGTM_HEALTHCHECK_NOW_EPOCH=${1} \
  TEST_CURL_RESULT=${2} \
    bash "${check}" >/dev/null 2>&1
}

run_check 100 ok
if run_check 101 fail; then
  echo "first failed probe unexpectedly passed" >&2
  exit 1
fi
if run_check 102 fail; then
  echo "sustained failed probe unexpectedly passed" >&2
  exit 1
fi
run_check 103 ok

read -r token first_seen failures <"${tmp}/state/state"
[[ ${token} == test-instance ]]
[[ ${first_seen} == 100 ]]
[[ ${failures} == 0 ]]
echo "LGTM healthcheck state tests passed"
