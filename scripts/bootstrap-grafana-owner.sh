#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd -- "${repo_dir}"

owner_file="${repo_dir}/secrets/owner-email"
if [[ ! -s "${owner_file}" ]]; then
  echo "Missing secrets/owner-email. Complete the H5 first login and store only the owner's exact Access email there." >&2
  exit 2
fi

set -a
# shellcheck disable=SC1091
source ./.env
set +a
owner_email=$(tr -d '\r\n' <"${owner_file}")
if [[ ! "${owner_email}" =~ ^[^[:space:]@]+@[^[:space:]@]+$ ]]; then
  echo "Owner email file is malformed." >&2
  exit 2
fi

base_url="http://127.0.0.1:${SHARED_GRAFANA_PORT}"
auth="${SHARED_GRAFANA_ADMIN_USER}:${SHARED_GRAFANA_ADMIN_PASSWORD}"
encoded_email=$(python3 -c 'import sys,urllib.parse; print(urllib.parse.quote(sys.stdin.read().strip(), safe=""))' <<<"${owner_email}")
lookup=$(curl --fail --silent --show-error --user "${auth}" "${base_url}/api/users/lookup?loginOrEmail=${encoded_email}")
user_id=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])' <<<"${lookup}")

curl --fail --silent --show-error --user "${auth}" \
  -H 'Content-Type: application/json' \
  -X PATCH -d '{"role":"Admin"}' \
  "${base_url}/api/org/users/${user_id}" >/dev/null

server_user=$(curl --fail --silent --show-error --user "${auth}" "${base_url}/api/admin/users/${user_id}")
is_server_admin=$(python3 -c 'import json,sys; print(str(bool(json.load(sys.stdin).get("isGrafanaAdmin"))).lower())' <<<"${server_user}")
if [[ "${is_server_admin}" != false ]]; then
  echo "Refusing: the Access-backed owner unexpectedly has server-administrator privileges." >&2
  exit 3
fi

org_role=$(curl --fail --silent --show-error --user "${auth}" "${base_url}/api/org/users" |
  OWNER_ID="${user_id}" python3 -c 'import json,os,sys; uid=int(os.environ["OWNER_ID"]); print(next(u["role"] for u in json.load(sys.stdin) if u["userId"]==uid))')
if [[ "${org_role}" != Admin ]]; then
  echo "Owner organization role verification failed." >&2
  exit 3
fi

unset owner_email auth lookup server_user
echo "Owner Access account is organization Admin and is not a Grafana server administrator."
