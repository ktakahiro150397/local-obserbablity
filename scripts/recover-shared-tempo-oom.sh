#!/usr/bin/env bash
set -euo pipefail

repo_dir=${RECOVERY_REPO_DIR:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}
cd -- "${repo_dir}"

action=${1:---preflight}
strict_min_available_mib=${RECOVERY_MIN_AVAILABLE_MIB:-3072}
strict_max_memory_psi=${RECOVERY_MAX_MEMORY_PSI_FULL_AVG10:-10}
strict_max_io_psi=${RECOVERY_MAX_IO_PSI_FULL_AVG10:-20}
query_min_available_mib=${RECOVERY_QUERY_MIN_AVAILABLE_MIB:-1536}
query_max_memory_psi=${RECOVERY_QUERY_MAX_MEMORY_PSI_FULL_AVG10:-20}
query_max_io_psi=${RECOVERY_QUERY_MAX_IO_PSI_FULL_AVG10:-35}
max_swap_in_kib=${RECOVERY_MAX_SWAP_IN_KIB_PER_SECOND:-4096}
approval_phrase=shared-tempo-oom-recovery-2026-08-16
override=ops/hermes-gap-recovery.compose.yaml

usage() {
  echo "Usage: $0 {--preflight|--execute}" >&2
}

number_le() {
  awk -v left="$1" -v right="$2" 'BEGIN{exit !(left <= right)}'
}

pressure_check() {
  local minimum_available_mib=$1
  local maximum_memory_psi=$2
  local maximum_io_psi=$3
  local available_kib swap_free_kib memory_psi io_psi d_state swap_in recent_oom
  available_kib=$(awk '/^MemAvailable:/{print $2}' /proc/meminfo)
  swap_free_kib=$(awk '/^SwapFree:/{print $2}' /proc/meminfo)
  memory_psi=$(awk '/^full /{for(i=1;i<=NF;i++)if($i~/^avg10=/){sub(/^avg10=/,"",$i);print $i}}' /proc/pressure/memory)
  io_psi=$(awk '/^full /{for(i=1;i<=NF;i++)if($i~/^avg10=/){sub(/^avg10=/,"",$i);print $i}}' /proc/pressure/io)
  d_state=$(ps -eo stat= | awk '/^D/{count++} END{print count+0}')
  swap_in=$(vmstat 1 3 | tail -n 2 | awk '{sum+=$7} END{printf "%.0f",sum/2}')
  recent_oom=$(journalctl -k --since '-20 minutes' --no-pager -o cat 2>/dev/null \
    | grep -Eci 'out of memory|oom-kill|killed process' || true)

  printf 'pressure mem_available_mib=%s swap_free_mib=%s memory_psi_full_avg10=%s io_psi_full_avg10=%s d_state=%s swap_in_kib_per_second=%s recent_oom_lines=%s\n' \
    "$((available_kib / 1024))" "$((swap_free_kib / 1024))" "${memory_psi}" \
    "${io_psi}" "${d_state}" "${swap_in}" "${recent_oom}"

  (( available_kib >= minimum_available_mib * 1024 )) || return 1
  number_le "${memory_psi}" "${maximum_memory_psi}" || return 1
  number_le "${io_psi}" "${maximum_io_psi}" || return 1
  (( d_state <= 4 )) || return 1
  (( swap_in <= max_swap_in_kib )) || return 1
  (( recent_oom == 0 )) || return 1
}

service_health() {
  local name=$1
  docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${name}"
}

tempo_ready() {
  local name=$1
  docker exec "${name}" curl --fail --silent --output /dev/null --max-time 5 \
    http://127.0.0.1:3200/ready
}

wait_healthy() {
  local name=$1
  local attempts=${2:-60}
  local attempt
  for ((attempt=1; attempt<=attempts; attempt++)); do
    if [[ $(service_health "${name}") == healthy ]]; then
      return 0
    fi
    sleep 5
  done
  return 1
}

checkpoints_current() {
  [[ $(docker compose exec -T shared-ledger psql \
    --username ledger_admin --dbname usage_ledger --no-align --tuples-only \
    --command "SELECT COALESCE(bool_and(checkpoint_at >= CURRENT_TIMESTAMP - interval '10 minutes'),false) FROM usage.live_rollup_checkpoints WHERE source_system='hermes';") == t ]]
}

preflight() {
  [[ -s .env ]] || { echo "missing ignored .env" >&2; return 1; }
  docker compose config --quiet
  [[ $(service_health local-observability-private-lgtm) == healthy ]]
  [[ $(service_health local-observability-private-ledger) == healthy ]]
  [[ $(service_health local-observability-shared-ledger) == healthy ]]
  tempo_ready local-observability-private-lgtm
  pressure_check "${strict_min_available_mib}" "${strict_max_memory_psi}" "${strict_max_io_psi}"
  echo "recovery preflight passed"
}

case ${action} in
  --preflight)
    preflight
    exit
    ;;
  --execute)
    ;;
  *)
    usage
    exit 2
    ;;
esac

if [[ ${OBSERVABILITY_RECOVERY_APPROVED:-} != "${approval_phrase}" ]]; then
  echo "live recovery requires the exact one-time approval phrase" >&2
  echo "After approval: OBSERVABILITY_RECOVERY_APPROVED=${approval_phrase} $0 --execute" >&2
  exit 2
fi

exec 9>/tmp/local-observability-shared-tempo-recovery.lock
flock -n 9 || { echo "another shared Tempo recovery is active" >&2; exit 2; }
preflight

branch=$(git branch --show-current)
[[ -n ${branch} && ${branch} != main ]] || {
  echo "recovery must run from a dedicated non-main branch" >&2
  exit 2
}
git diff --quiet
git diff --cached --quiet

# Build the bounded recovery worker before changing any live service.
docker compose build hermes-live-rollup

before_rows=$(docker compose exec -T shared-ledger psql \
  --username ledger_admin --dbname usage_ledger --no-align --tuples-only \
  --command "SELECT count(*) FROM usage.usage_records WHERE source_system='hermes' AND record_origin='live_rollup';")
echo "shared live rows before recovery=${before_rows}"

# The normal worker must remain stopped until the private Tempo mirror has
# advanced the existing checkpoints; otherwise an empty shared-source window
# would be accepted as complete and the gap would become harder to recover.
docker compose stop hermes-live-rollup
./backfill/scripts/backup-ledgers.sh

docker compose up -d --no-deps --force-recreate shared-lgtm
wait_healthy local-observability-shared-lgtm 60
tempo_ready local-observability-shared-lgtm

complete=false
for batch in $(seq 1 20); do
  if checkpoints_current; then
    complete=true
    break
  fi
  pressure_check "${query_min_available_mib}" "${query_max_memory_psi}" "${query_max_io_psi}" \
    || { echo "pressure gate stopped recovery before batch ${batch}" >&2; exit 1; }
  set +e
  docker compose -f compose.yaml -f "${override}" --profile recovery run --rm --no-deps \
    hermes-gap-recovery --catch-up --catch-up-max-cycles 12 \
    --catch-up-pause-seconds 5
  status=$?
  set -e
  case ${status} in
    0) complete=true; break ;;
    3) echo "recovery batch ${batch} reached its bounded cycle limit" ;;
    *) echo "recovery worker failed in batch ${batch}" >&2; exit 1 ;;
  esac
done

${complete} || { echo "checkpoints did not catch up within the bounded recovery" >&2; exit 1; }
checkpoints_current

# Apply the lower PostgreSQL working-set defaults one ledger at a time. Named
# volumes and all existing rows remain in place.
docker compose up -d --no-deps --force-recreate --wait shared-ledger
docker compose up -d --no-deps --force-recreate --wait private-ledger

docker compose up -d --no-deps --force-recreate hermes-live-rollup
wait_healthy local-observability-hermes-live-rollup 72
./backfill/scripts/verify-ledgers.sh

after_rows=$(docker compose exec -T shared-ledger psql \
  --username ledger_admin --dbname usage_ledger --no-align --tuples-only \
  --command "SELECT count(*) FROM usage.usage_records WHERE source_system='hermes' AND record_origin='live_rollup';")
isolation_violations=$(docker compose exec -T shared-ledger psql \
  --username ledger_admin --dbname usage_ledger --no-align --tuples-only \
  --command "SELECT count(*) FROM usage.usage_records WHERE source_system<>'hermes' OR shared_eligible IS DISTINCT FROM true;")
duplicate_keys=$(docker compose exec -T shared-ledger psql \
  --username ledger_admin --dbname usage_ledger --no-align --tuples-only \
  --command "SELECT count(*) FROM (SELECT source_system,source_instance,record_origin,source_record_id FROM usage.usage_records GROUP BY 1,2,3,4 HAVING count(*)>1) duplicated;")

[[ ${isolation_violations} == 0 ]]
[[ ${duplicate_keys} == 0 ]]
tempo_ready local-observability-shared-lgtm
echo "shared live rows after recovery=${after_rows}"
echo "shared isolation violations=${isolation_violations} duplicate keys=${duplicate_keys}"
echo "shared Tempo OOM recovery completed"
