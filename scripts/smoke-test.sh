#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd -- "${repo_dir}"

set -a
# shellcheck disable=SC1091
source ./.env
set +a

tmp_dir=$(mktemp -d)
trap 'rm -rf -- "${tmp_dir}"' EXIT
now_nanos=$(date +%s)000000000
end_nanos=$((now_nanos + 1000000))

write_trace() {
  local service_name=$1
  local trace_id=$2
  local span_id=$3
  local output=$4
  cat >"${output}" <<EOF
{"resourceSpans":[{"resource":{"attributes":[{"key":"service.name","value":{"stringValue":"${service_name}"}},{"key":"service.instance.id","value":{"stringValue":"synthetic-smoke"}}]},"scopeSpans":[{"scope":{"name":"phase1-smoke"},"spans":[{"traceId":"${trace_id}","spanId":"${span_id}","name":"agent","kind":1,"startTimeUnixNano":"${now_nanos}","endTimeUnixNano":"${end_nanos}","attributes":[{"key":"phase1.synthetic","value":{"boolValue":true}},{"key":"user.id","value":{"stringValue":"discord:SYNTHETIC"}},{"key":"gen_ai.usage.total_tokens","value":{"intValue":"7"}},{"key":"input.value","value":{"stringValue":"phase1-content-must-be-dropped"}},{"key":"gen_ai.tool.call.arguments","value":{"stringValue":"phase1-content-must-be-dropped"}},{"key":"hermes.tool.command","value":{"stringValue":"phase1-content-must-be-dropped"}},{"key":"hermes.tool.target","value":{"stringValue":"phase1-content-must-be-dropped"}},{"key":"error.message","value":{"stringValue":"phase1-content-must-be-dropped"}}]}]}]}]}
EOF
}

codex_trace_id=$(python3 -c 'import secrets; print(secrets.token_hex(16))')
hermes_trace_id=$(python3 -c 'import secrets; print(secrets.token_hex(16))')
write_trace "codex-phase1-smoke" "${codex_trace_id}" "${codex_trace_id:0:16}" "${tmp_dir}/private.json"
write_trace "backup-secretary-hermes" "${hermes_trace_id}" "${hermes_trace_id:0:16}" "${tmp_dir}/hermes.json"

post_trace() {
  curl --fail --silent --show-error \
    --retry 5 \
    --retry-connrefused \
    --retry-delay 1 \
    -H 'Content-Type: application/json' \
    --data-binary "@${1}" \
    "http://${OTLP_HTTP_BIND}:${OTLP_HTTP_PORT}/v1/traces" >/dev/null
}
post_trace "${tmp_dir}/private.json"
post_trace "${tmp_dir}/hermes.json"

query_trace_exists() {
  local port=$1
  local user=$2
  local password=$3
  local trace_id=$4
  local status
  status=$(curl --silent --show-error \
    --output /dev/null \
    --write-out '%{http_code}' \
    --user "${user}:${password}" \
    "http://127.0.0.1:${port}/api/datasources/proxy/uid/tempo/api/traces/${trace_id}")
  case "${status}" in
    200) echo 1 ;;
    404) echo 0 ;;
    *)
      echo "Unexpected Tempo trace lookup status: ${status}" >&2
      return 1
      ;;
  esac
}

query_blocked_attribute_count() {
  local port=$1
  local user=$2
  local password=$3
  local trace_id=$4
  curl --fail --silent --show-error \
    --user "${user}:${password}" \
    "http://127.0.0.1:${port}/api/datasources/proxy/uid/tempo/api/traces/${trace_id}" |
    python3 -c '
import json
import sys

blocked = {
    "input.value", "output.value", "gen_ai.tool.call.arguments",
    "gen_ai.tool.call.result", "hermes.tool.command", "hermes.tool.target",
    "hermes.turn.tool_commands", "hermes.turn.tool_targets", "error.message",
    "exception.message", "exception.stacktrace",
}

def count(value):
    if isinstance(value, dict):
        own = 1 if value.get("key") in blocked else 0
        return own + sum(count(item) for item in value.values())
    if isinstance(value, list):
        return sum(count(item) for item in value)
    return 0

print(count(json.load(sys.stdin)))
'
}

settle_timeout=${SMOKE_SETTLE_SECONDS:-60}
poll_interval=${SMOKE_POLL_SECONDS:-5}
deadline=$((SECONDS + settle_timeout))

while true; do
  private_codex=$(query_trace_exists "${PRIVATE_GRAFANA_PORT}" "${PRIVATE_GRAFANA_ADMIN_USER}" "${PRIVATE_GRAFANA_ADMIN_PASSWORD}" "${codex_trace_id}")
  private_hermes=$(query_trace_exists "${PRIVATE_GRAFANA_PORT}" "${PRIVATE_GRAFANA_ADMIN_USER}" "${PRIVATE_GRAFANA_ADMIN_PASSWORD}" "${hermes_trace_id}")
  shared_codex=$(query_trace_exists "${SHARED_GRAFANA_PORT}" "${SHARED_GRAFANA_ADMIN_USER}" "${SHARED_GRAFANA_ADMIN_PASSWORD}" "${codex_trace_id}")
  shared_hermes=$(query_trace_exists "${SHARED_GRAFANA_PORT}" "${SHARED_GRAFANA_ADMIN_USER}" "${SHARED_GRAFANA_ADMIN_PASSWORD}" "${hermes_trace_id}")

  if (( private_codex >= 1 && private_hermes >= 1 && shared_hermes >= 1 )); then
    break
  fi
  if (( SECONDS >= deadline )); then
    break
  fi
  sleep "${poll_interval}"
done

if (( private_codex >= 1 && private_hermes >= 1 && shared_hermes >= 1 )); then
  sleep "${poll_interval}"
  shared_codex=$(query_trace_exists "${SHARED_GRAFANA_PORT}" "${SHARED_GRAFANA_ADMIN_USER}" "${SHARED_GRAFANA_ADMIN_PASSWORD}" "${codex_trace_id}")
fi

private_codex_blocked=1
private_hermes_blocked=1
shared_hermes_blocked=1
if (( private_codex >= 1 && private_hermes >= 1 && shared_hermes >= 1 )); then
  private_codex_blocked=$(query_blocked_attribute_count "${PRIVATE_GRAFANA_PORT}" "${PRIVATE_GRAFANA_ADMIN_USER}" "${PRIVATE_GRAFANA_ADMIN_PASSWORD}" "${codex_trace_id}")
  private_hermes_blocked=$(query_blocked_attribute_count "${PRIVATE_GRAFANA_PORT}" "${PRIVATE_GRAFANA_ADMIN_USER}" "${PRIVATE_GRAFANA_ADMIN_PASSWORD}" "${hermes_trace_id}")
  shared_hermes_blocked=$(query_blocked_attribute_count "${SHARED_GRAFANA_PORT}" "${SHARED_GRAFANA_ADMIN_USER}" "${SHARED_GRAFANA_ADMIN_PASSWORD}" "${hermes_trace_id}")
fi

if (( private_codex < 1 || private_hermes < 1 || shared_hermes < 1 || shared_codex != 0 || private_codex_blocked != 0 || private_hermes_blocked != 0 || shared_hermes_blocked != 0 )); then
  echo "Smoke test failed: private_codex=${private_codex} private_hermes=${private_hermes} shared_codex=${shared_codex} shared_hermes=${shared_hermes} blocked_private_codex=${private_codex_blocked} blocked_private_hermes=${private_hermes_blocked} blocked_shared_hermes=${shared_hermes_blocked}" >&2
  exit 1
fi

echo "Smoke test passed: private accepts both sources; shared accepts only Hermes; blocked content attributes are absent."
