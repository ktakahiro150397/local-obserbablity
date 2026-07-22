#!/usr/bin/env bash
set -euo pipefail

: "${POSTGRES_USER:?}"
: "${POSTGRES_DB:?}"
: "${LEDGER_DOMAIN:?}"
[[ "${LEDGER_DOMAIN}" == private || "${LEDGER_DOMAIN}" == shared ]]

writer_password=$(</run/ledger-secrets/ledger_writer_password)
grafana_password=$(</run/ledger-secrets/ledger_grafana_password)

psql --set ON_ERROR_STOP=1 \
  --username "${POSTGRES_USER}" \
  --dbname "${POSTGRES_DB}" \
  --set "writer_password=${writer_password}" \
  --set "grafana_password=${grafana_password}" \
  --set "ledger_domain=${LEDGER_DOMAIN}" <<'SQL'
SELECT format('CREATE ROLE ledger_writer LOGIN PASSWORD %L', :'writer_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ledger_writer') \gexec
SELECT format('ALTER ROLE ledger_writer PASSWORD %L', :'writer_password') \gexec

SELECT format('CREATE ROLE ledger_grafana LOGIN PASSWORD %L', :'grafana_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ledger_grafana') \gexec
SELECT format('ALTER ROLE ledger_grafana PASSWORD %L', :'grafana_password') \gexec

ALTER ROLE ledger_writer NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
ALTER ROLE ledger_grafana NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
REVOKE ALL ON DATABASE usage_ledger FROM PUBLIC;
GRANT CONNECT ON DATABASE usage_ledger TO ledger_writer, ledger_grafana;
GRANT TEMPORARY ON DATABASE usage_ledger TO ledger_writer;

\ir /opt/ledger/schema/001_init.sql
\ir /opt/ledger/schema/002_live_rollup.sql
\ir /opt/ledger/schema/003_api_equivalent_pricing.sql

SELECT 'ALTER TABLE usage.usage_records ADD CONSTRAINT shared_hermes_only '
       'CHECK (source_system = ''hermes'' AND shared_eligible)'
WHERE :'ledger_domain' = 'shared'
  AND NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'shared_hermes_only'
  ) \gexec
SELECT 'ALTER TABLE usage.import_runs ADD CONSTRAINT shared_import_runs_hermes_only '
       'CHECK (source_system = ''hermes'')'
WHERE :'ledger_domain' = 'shared'
  AND NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'shared_import_runs_hermes_only'
  ) \gexec
SELECT 'ALTER TABLE usage.cutovers ADD CONSTRAINT shared_cutovers_hermes_only '
       'CHECK (source_system = ''hermes'')'
WHERE :'ledger_domain' = 'shared'
  AND NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'shared_cutovers_hermes_only'
  ) \gexec

REVOKE ALL ON SCHEMA usage, grafana FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA usage, grafana FROM PUBLIC;
GRANT USAGE ON SCHEMA usage TO ledger_writer;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA usage TO ledger_writer;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA usage TO ledger_writer;
ALTER DEFAULT PRIVILEGES IN SCHEMA usage
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ledger_writer;
ALTER DEFAULT PRIVILEGES IN SCHEMA usage
  GRANT USAGE, SELECT ON SEQUENCES TO ledger_writer;

GRANT USAGE ON SCHEMA grafana TO ledger_grafana;
GRANT SELECT ON ALL TABLES IN SCHEMA grafana TO ledger_grafana;
ALTER DEFAULT PRIVILEGES IN SCHEMA grafana GRANT SELECT ON TABLES TO ledger_grafana;
SQL

unset writer_password grafana_password
