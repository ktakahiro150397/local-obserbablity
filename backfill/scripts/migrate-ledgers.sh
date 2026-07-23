#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
cd -- "${repo_dir}"

for domain in private shared; do
  docker compose exec -T \
    --env "LEDGER_DOMAIN=${domain}" \
    "${domain}-ledger" \
    bash /opt/ledger/schema/init-ledger.sh
done

./backfill/scripts/verify-ledgers.sh
