#!/usr/bin/env bash
set -euo pipefail

if [[ $(id -u) -eq 0 ]]; then
  install -o postgres -g postgres -m 600 \
    /run/secrets/ledger_admin_password \
    /run/ledger-secrets/ledger_admin_password
  install -o postgres -g postgres -m 600 \
    /run/secrets/ledger_writer_password \
    /run/ledger-secrets/ledger_writer_password
  install -o postgres -g postgres -m 600 \
    /run/secrets/ledger_grafana_password \
    /run/ledger-secrets/ledger_grafana_password
fi

export POSTGRES_PASSWORD_FILE=/run/ledger-secrets/ledger_admin_password
exec /usr/local/bin/docker-entrypoint.sh "$@"
