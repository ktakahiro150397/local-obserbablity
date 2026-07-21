#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
env_file="${repo_dir}/.env"
data_root="${LOCAL_OBSERVABILITY_DATA_ROOT:-${HOME}/local-observability-data}"

umask 077

if ! command -v openssl >/dev/null 2>&1; then
  echo "openssl is required to generate local Grafana secrets." >&2
  exit 1
fi

lan_ip=${LOCAL_OBSERVABILITY_LAN_IP:-}
if [[ -z "${lan_ip}" ]]; then
  lan_ip=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i=1;i<=NF;i++) if ($i=="src") {print $(i+1); exit}}')
fi
if [[ ! "${lan_ip}" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
  echo "Could not determine a LAN IPv4 address. Set LOCAL_OBSERVABILITY_LAN_IP." >&2
  exit 1
fi

mkdir -p -- "${data_root}/private" "${data_root}/shared" "${repo_dir}/secrets"
chmod 700 -- "${data_root}" "${data_root}/private" "${data_root}/shared" "${repo_dir}/secrets"

token_file="${repo_dir}/secrets/cloudflare-tunnel.token"
if [[ ! -e "${token_file}" ]]; then
  : >"${token_file}"
fi
chmod 600 -- "${token_file}"

if [[ ! -e "${env_file}" ]]; then
  private_password=$(openssl rand -hex 24)
  private_secret=$(openssl rand -hex 32)
  shared_password=$(openssl rand -hex 24)
  shared_secret=$(openssl rand -hex 32)

  cat >"${env_file}" <<EOF
PRIVATE_DATA_DIR=${data_root}/private
SHARED_DATA_DIR=${data_root}/shared
PRIVATE_GRAFANA_BIND=127.0.0.1
PRIVATE_GRAFANA_PORT=3002
PRIVATE_GRAFANA_ROOT_URL=http://localhost:3002
SHARED_GRAFANA_BIND=127.0.0.1
SHARED_GRAFANA_PORT=3003
OTLP_HTTP_BIND=${lan_ip}
OTLP_HTTP_PORT=4318
OTEL_HEALTH_PORT=13133
PRIVATE_GRAFANA_ADMIN_USER=admin
PRIVATE_GRAFANA_ADMIN_PASSWORD=${private_password}
PRIVATE_GRAFANA_SECRET_KEY=${private_secret}
SHARED_GRAFANA_ADMIN_USER=breakglass
SHARED_GRAFANA_ADMIN_PASSWORD=${shared_password}
SHARED_GRAFANA_SECRET_KEY=${shared_secret}
PROMETHEUS_EXTRA_ARGS=--storage.tsdb.retention.time=30d
TEMPO_EXTRA_ARGS=
PRIVATE_LGTM_MEMORY_LIMIT=1800m
SHARED_LGTM_MEMORY_LIMIT=1800m
OTEL_ROUTER_MEMORY_LIMIT=384m
CLOUDFLARED_MEMORY_LIMIT=128m
PRIVATE_LGTM_CPU_LIMIT=1.5
SHARED_LGTM_CPU_LIMIT=1.5
OTEL_ROUTER_CPU_LIMIT=0.5
CLOUDFLARED_CPU_LIMIT=0.25
EOF
  chmod 600 -- "${env_file}"
  unset private_password private_secret shared_password shared_secret
  echo "Created an ignored .env and separate private/shared data directories."
else
  echo "Existing .env preserved."
fi

cd -- "${repo_dir}"
docker compose config --quiet
echo "Compose configuration is valid. No secret values were printed."
