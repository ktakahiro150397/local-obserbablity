#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd -- "${repo_dir}"

env_file=${ENV_FILE:-.env}
if [[ ! -s "${env_file}" ]]; then
  echo "Missing ${env_file}. Run scripts/init-local-env.sh first." >&2
  exit 1
fi

rendered=$(mktemp)
trap 'rm -f -- "${rendered}"' EXIT
docker compose --env-file "${env_file}" --profile public --profile private-access \
  config --format json >"${rendered}"

python3 - "${rendered}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    config = json.load(handle)

services = config["services"]

def network_names(service):
    networks = services[service].get("networks", {})
    return set(networks if isinstance(networks, dict) else networks)

def published_bind(service, target):
    for port in services[service].get("ports", []):
        if int(port.get("target", -1)) == target:
            return str(port.get("host_ip", "")), int(port.get("published", 0))
    raise AssertionError(f"{service} has no published target {target}")

assert network_names("cloudflared") == {"shared-proxy"}
assert network_names("private-cloudflared") == {"private-admin"}
assert network_names("private-lgtm") == {"private-admin", "private-backend"}
assert "shared-proxy" not in network_names("private-cloudflared")
assert "private-admin" not in network_names("cloudflared")

private_bind, private_port = published_bind("private-lgtm", 3000)
shared_bind, shared_port = published_bind("shared-lgtm", 3000)
assert private_bind == "127.0.0.1"
assert shared_bind == "127.0.0.1"
assert private_port != shared_port

private_command = services["private-cloudflared"].get("command", [])
assert "/run/secrets/cloudflare_private_tunnel_token" in private_command
assert services["private-cloudflared"].get("read_only") is True
assert services["private-cloudflared"].get("cap_drop") == ["ALL"]
assert services["private-cloudflared"].get("security_opt") == ["no-new-privileges:true"]

print("Private Access topology preflight passed.")
PY

verify_running_networks() {
  local service=$1
  local expected=$2
  local container_id
  container_id=$(
    docker compose --env-file "${env_file}" --profile public \
      --profile private-access ps -q "${service}"
  )
  if [[ -z "${container_id}" ]]; then
    return 0
  fi

  local actual
  actual=$(
    docker inspect "${container_id}" \
      --format '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}}{{"\n"}}{{end}}' |
      sed '/^$/d' |
      sort |
      paste -sd, -
  )
  if [[ "${actual}" != "${expected}" ]]; then
    echo "${service} has unexpected runtime networks." >&2
    exit 1
  fi
}

verify_running_networks cloudflared local-observability-shared-proxy
verify_running_networks private-cloudflared local-observability-private-admin

if [[ "${VERIFY_PUBLIC:-0}" == "1" ]]; then
  private_status=$(
    curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
      https://private-observe.yanelmo.net/
  )
  shared_status=$(
    curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
      https://observe.yanelmo.net/
  )

  if [[ "${private_status}" != "302" ]]; then
    echo "Private hostname did not return the expected unauthenticated Access redirect." >&2
    exit 1
  fi
  if [[ "${shared_status}" != "302" ]]; then
    echo "Shared hostname no longer returns the expected unauthenticated Access redirect." >&2
    exit 1
  fi
  echo "Both Access applications return unauthenticated redirects."
fi

echo "Private/shared connector network isolation passed."
