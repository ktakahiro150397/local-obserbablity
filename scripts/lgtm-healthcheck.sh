#!/usr/bin/env bash
set -euo pipefail

# Docker records an unhealthy state but does not apply the service restart
# policy to it. The otel-lgtm PID 1 also survives when a bundled child such as
# Tempo is OOM-killed. After a startup grace period and repeated failures, this
# check therefore terminates PID 1 so Docker can recreate the whole bundle.

state_dir=${LGTM_HEALTHCHECK_STATE_DIR:-/tmp/lgtm-healthcheck}
failure_limit=${LGTM_HEALTHCHECK_FAILURE_LIMIT:-4}
minimum_uptime=${LGTM_HEALTHCHECK_MIN_UPTIME_SECONDS:-180}
restart_enabled=${LGTM_HEALTHCHECK_RESTART_ENABLED:-true}
restart_pid=${LGTM_HEALTHCHECK_RESTART_PID:-1}
now=${LGTM_HEALTHCHECK_NOW_EPOCH:-$(date +%s)}
instance_token=${LGTM_HEALTHCHECK_INSTANCE_TOKEN:-$(awk '{print $22}' /proc/1/stat)}

case ${failure_limit} in
  ''|*[!0-9]*|0) echo "invalid LGTM health failure limit" >&2; exit 2 ;;
esac
case ${minimum_uptime} in
  ''|*[!0-9]*) echo "invalid LGTM health minimum uptime" >&2; exit 2 ;;
esac

mkdir -p -- "${state_dir}"
chmod 700 -- "${state_dir}"
state_file=${state_dir}/state

stored_token=
first_seen=${now}
failures=0
if [[ -r ${state_file} ]]; then
  read -r stored_token first_seen failures <"${state_file}" || true
fi
if [[ ${stored_token} != "${instance_token}" ]]; then
  first_seen=${now}
  failures=0
fi

failed=()
check_endpoint() {
  local label=$1
  local url=$2
  if ! curl --fail --silent --output /dev/null --max-time 4 "${url}" 2>/dev/null; then
    failed+=("${label}")
  fi
}

check_endpoint grafana http://127.0.0.1:3000/api/health
check_endpoint tempo http://127.0.0.1:3200/ready
check_endpoint prometheus http://127.0.0.1:9090/-/ready

if (( ${#failed[@]} == 0 )); then
  printf '%s %s 0\n' "${instance_token}" "${first_seen}" >"${state_file}"
  exit 0
fi

failures=$((failures + 1))
printf '%s %s %s\n' "${instance_token}" "${first_seen}" "${failures}" >"${state_file}"
age=$((now - first_seen))
printf 'required LGTM endpoints unavailable: %s (failure %s/%s, process age %ss)\n' \
  "$(IFS=,; echo "${failed[*]}")" "${failures}" "${failure_limit}" "${age}" >&2

if (( age >= minimum_uptime && failures >= failure_limit )); then
  if [[ ${restart_enabled} == true ]]; then
    echo "terminating LGTM PID 1 after sustained child failure" >&2
    kill -TERM "${restart_pid}"
  fi
fi
exit 1
