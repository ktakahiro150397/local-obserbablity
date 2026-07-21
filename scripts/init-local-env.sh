#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
env_file="${repo_dir}/.env"
data_root="${LOCAL_OBSERVABILITY_DATA_ROOT:-${HOME}/local-observability-data}"
lgtm_uid_gid="$(id -u):$(id -g)"
cloudflared_uid_gid="$(id -u):$(id -g)"

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

mkdir -p -- \
  "${data_root}/private/tempo-runtime" \
  "${data_root}/shared/tempo-runtime" \
  "${repo_dir}/secrets"
chmod 700 -- \
  "${data_root}" \
  "${data_root}/private" \
  "${data_root}/private/tempo-runtime" \
  "${data_root}/shared" \
  "${data_root}/shared/tempo-runtime" \
  "${repo_dir}/secrets"

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
LGTM_UID_GID=${lgtm_uid_gid}
CLOUDFLARED_UID_GID=${cloudflared_uid_gid}
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
PRIVATE_LGTM_MEMORY_LIMIT=3000m
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
  added_env_fields=()
  if ! grep -q '^LGTM_UID_GID=' "${env_file}"; then
    printf '\nLGTM_UID_GID=%s\n' "${lgtm_uid_gid}" >>"${env_file}"
    added_env_fields+=(LGTM_UID_GID)
  fi
  if ! grep -q '^CLOUDFLARED_UID_GID=' "${env_file}"; then
    printf '\nCLOUDFLARED_UID_GID=%s\n' "${cloudflared_uid_gid}" >>"${env_file}"
    added_env_fields+=(CLOUDFLARED_UID_GID)
  fi
  if ((${#added_env_fields[@]} > 0)); then
    chmod 600 -- "${env_file}"
    echo "Existing .env preserved; added missing non-secret container owner mappings."
  else
    echo "Existing .env preserved."
  fi
fi

cd -- "${repo_dir}"
docker compose config --quiet
echo "Compose configuration is valid. No secret values were printed."
