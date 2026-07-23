#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 --container <name> --instance <main|owashota> --output-dir <directory> [--dry-run]" >&2
}

container=""
instance=""
output_dir=""
dry_run=false
while (($#)); do
  case "$1" in
    --container) container=${2:?}; shift 2 ;;
    --instance) instance=${2:?}; shift 2 ;;
    --output-dir) output_dir=${2:?}; shift 2 ;;
    --dry-run) dry_run=true; shift ;;
    *) usage; exit 2 ;;
  esac
done

[[ -n "${container}" && -n "${instance}" && -n "${output_dir}" ]] || { usage; exit 2; }
[[ "${instance}" == "main" || "${instance}" == "owashota" ]] || { usage; exit 2; }
docker inspect "${container}" >/dev/null
docker exec "${container}" test -f /opt/data/state.db

if ${dry_run}; then
  printf '{"dry_run":true,"instance":"%s","source_present":true}\n' "${instance}"
  exit 0
fi

umask 077
mkdir -p -- "${output_dir}"
[[ ! -e "${output_dir}/${instance}-state.db" ]] || {
  echo "Snapshot already exists; refusing to overwrite." >&2
  exit 1
}
container_tmp="/tmp/phase4-${instance}-state.db"
cleanup() { docker exec "${container}" rm -f -- "${container_tmp}" >/dev/null 2>&1 || true; }
trap cleanup EXIT
cleanup

docker exec -i "${container}" python - "${container_tmp}" <<'PY'
import sqlite3
import sys

source = sqlite3.connect("file:/opt/data/state.db?mode=ro", uri=True)
target = sqlite3.connect(sys.argv[1])
try:
    source.backup(target)
finally:
    target.close()
    source.close()
PY

docker cp "${container}:${container_tmp}" "${output_dir}/${instance}-state.db" >/dev/null
chmod 600 -- "${output_dir}/${instance}-state.db"
sha256sum "${output_dir}/${instance}-state.db" >"${output_dir}/${instance}-state.db.sha256"
chmod 600 -- "${output_dir}/${instance}-state.db.sha256"
printf '{"instance":"%s","snapshot_created":true}\n' "${instance}"
