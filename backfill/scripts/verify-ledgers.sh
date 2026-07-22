#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
cd -- "${repo_dir}"

for domain in private shared; do
  docker compose exec -T "${domain}-ledger" psql \
    --username ledger_admin --dbname usage_ledger --tuples-only --no-align \
    --command "SELECT current_setting('server_version'), count(*) FROM usage.schema_migrations;"
done

for domain in private shared; do
  migration_count=$(docker compose exec -T "${domain}-ledger" psql \
    --username ledger_admin --dbname usage_ledger --tuples-only --no-align \
    --command "SELECT count(*) FROM usage.schema_migrations WHERE version IN (2,3);")
  checkpoint_table=$(docker compose exec -T "${domain}-ledger" psql \
    --username ledger_admin --dbname usage_ledger --tuples-only --no-align \
    --command "SELECT to_regclass('usage.live_rollup_checkpoints') IS NOT NULL;")
  price_table=$(docker compose exec -T "${domain}-ledger" psql \
    --username ledger_admin --dbname usage_ledger --tuples-only --no-align \
    --command "SELECT to_regclass('usage.api_model_prices') IS NOT NULL;")
  price_view=$(docker compose exec -T "${domain}-ledger" psql \
    --username ledger_admin --dbname usage_ledger --tuples-only --no-align \
    --command "SELECT to_regclass('grafana.hermes_usage_api_equivalent') IS NOT NULL;")
  [[ "${migration_count}" == 2 && "${checkpoint_table}" == t && "${price_table}" == t && "${price_view}" == t ]]
done

private_reject=$(docker compose exec -T private-ledger psql \
  --username ledger_admin --dbname usage_ledger --tuples-only --no-align \
  --command "SELECT count(*) FROM pg_constraint WHERE conname='shared_hermes_only';")
shared_guard=$(docker compose exec -T shared-ledger psql \
  --username ledger_admin --dbname usage_ledger --tuples-only --no-align \
  --command "SELECT count(*) FROM pg_constraint WHERE conname='shared_hermes_only';")
[[ "${private_reject}" == 0 && "${shared_guard}" == 1 ]]

for domain in private shared; do
  docker compose exec -T "${domain}-ledger" psql \
    --username ledger_admin --dbname usage_ledger --tuples-only --no-align \
    --command "SELECT has_schema_privilege('ledger_grafana','usage','USAGE'), has_schema_privilege('ledger_grafana','grafana','USAGE'), has_table_privilege('ledger_grafana','grafana.usage_all_time','SELECT'), has_table_privilege('ledger_grafana','grafana.hermes_usage_api_equivalent','SELECT');"
done

echo "Ledger schema, pricing view, isolation guard, and Grafana least-privilege checks passed."
