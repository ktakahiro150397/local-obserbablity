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
{"resourceSpans":[{"resource":{"attributes":[{"key":"service.name","value":{"stringValue":"${service_name}"}},{"key":"service.instance.id","value":{"stringValue":"synthetic-smoke"}}]},"scopeSpans":[{"scope":{"name":"phase1-smoke"},"spans":[{"traceId":"${trace_id}","spanId":"${span_id}","name":"agent","kind":1,"startTimeUnixNano":"${now_nanos}","endTimeUnixNano":"${end_nanos}","attributes":[{"key":"phase1.synthetic","value":{"boolValue":true}},{"key":"user.id","value":{"stringValue":"discord:SYNTHETIC"}},{"key":"gen_ai.usage.total_tokens","value":{"intValue":"7"}}]}]}]}]}
EOF
}

write_trace "codex-phase1-smoke" "11111111111111111111111111111111" "1111111111111111" "${tmp_dir}/private.json"
write_trace "backup-secretary-hermes" "22222222222222222222222222222222" "2222222222222222" "${tmp_dir}/hermes.json"

post_trace() {
  curl --fail --silent --show-error \
    -H 'Content-Type: application/json' \
    --data-binary "@${1}" \
    "http://${OTLP_HTTP_BIND}:${OTLP_HTTP_PORT}/v1/traces" >/dev/null
}
post_trace "${tmp_dir}/private.json"
post_trace "${tmp_dir}/hermes.json"

sleep "${SMOKE_SETTLE_SECONDS:-12}"

query_count() {
  local port=$1
  local user=$2
  local password=$3
  local service_name=$4
  curl --fail --silent --show-error \
    --user "${user}:${password}" \
    --get \
    --data-urlencode "q={ resource.service.name = \"${service_name}\" }" \
    "http://127.0.0.1:${port}/api/datasources/proxy/uid/tempo/api/search" |
    python3 -c 'import json,sys; print(len(json.load(sys.stdin).get("traces", [])))'
}

private_codex=$(query_count "${PRIVATE_GRAFANA_PORT}" "${PRIVATE_GRAFANA_ADMIN_USER}" "${PRIVATE_GRAFANA_ADMIN_PASSWORD}" "codex-phase1-smoke")
private_hermes=$(query_count "${PRIVATE_GRAFANA_PORT}" "${PRIVATE_GRAFANA_ADMIN_USER}" "${PRIVATE_GRAFANA_ADMIN_PASSWORD}" "backup-secretary-hermes")
shared_codex=$(query_count "${SHARED_GRAFANA_PORT}" "${SHARED_GRAFANA_ADMIN_USER}" "${SHARED_GRAFANA_ADMIN_PASSWORD}" "codex-phase1-smoke")
shared_hermes=$(query_count "${SHARED_GRAFANA_PORT}" "${SHARED_GRAFANA_ADMIN_USER}" "${SHARED_GRAFANA_ADMIN_PASSWORD}" "backup-secretary-hermes")

if (( private_codex < 1 || private_hermes < 1 || shared_hermes < 1 || shared_codex != 0 )); then
  echo "Smoke test failed: private_codex=${private_codex} private_hermes=${private_hermes} shared_codex=${shared_codex} shared_hermes=${shared_hermes}" >&2
  exit 1
fi

echo "Smoke test passed: private accepts both sources; shared accepts Hermes and rejects synthetic Codex."
