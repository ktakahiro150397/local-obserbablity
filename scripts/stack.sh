#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd -- "${repo_dir}"

if [[ ! -s .env ]]; then
  echo "Missing .env. Run scripts/init-local-env.sh first." >&2
  exit 1
fi

action=${1:-status}
shift || true

case "${action}" in
  config)
    docker compose config --quiet
    ;;
  up)
    docker compose up -d --wait private-lgtm shared-lgtm otel-router private-ledger shared-ledger
    ./backfill/scripts/migrate-ledgers.sh
    docker compose up -d --wait hermes-live-rollup
    ;;
  public-up)
    if [[ ! -s secrets/cloudflare-tunnel.token ]]; then
      echo "Tunnel token file is empty. Complete H2 before starting cloudflared." >&2
      exit 1
    fi
    docker compose up -d --wait private-lgtm shared-lgtm otel-router private-ledger shared-ledger
    ./backfill/scripts/migrate-ledgers.sh
    docker compose up -d --wait hermes-live-rollup
    docker compose --profile public up -d --wait cloudflared
    ;;
  private-access-up)
    if [[ ! -s secrets/cloudflare-private-tunnel.token ]]; then
      echo "Private Tunnel token file is empty. Complete PA1 before starting private-cloudflared." >&2
      exit 1
    fi
    if [[ -z "$(docker compose ps -q private-lgtm)" ]]; then
      docker compose up -d --wait private-lgtm
    fi
    docker compose --profile private-access up -d --wait --no-deps private-cloudflared
    ;;
  private-access-stop)
    docker compose --profile private-access stop private-cloudflared
    ;;
  stop)
    docker compose --profile public --profile private-access stop
    ;;
  start)
    docker compose start private-lgtm shared-lgtm otel-router private-ledger shared-ledger
    ./backfill/scripts/migrate-ledgers.sh
    docker compose up -d --wait hermes-live-rollup
    ;;
  down)
    docker compose --profile public --profile private-access down
    ;;
  status)
    docker compose --profile public --profile private-access ps
    ;;
  logs)
    docker compose --profile public --profile private-access logs --tail "${LOG_TAIL:-200}" "$@"
    ;;
  *)
    echo "Usage: $0 {config|up|public-up|private-access-up|private-access-stop|stop|start|down|status|logs [service...]}" >&2
    exit 2
    ;;
esac
