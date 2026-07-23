BEGIN;

CREATE SCHEMA IF NOT EXISTS usage;
CREATE SCHEMA IF NOT EXISTS grafana;
REVOKE ALL ON SCHEMA usage FROM PUBLIC;
REVOKE ALL ON SCHEMA grafana FROM PUBLIC;

CREATE TABLE IF NOT EXISTS usage.schema_migrations (
  version integer PRIMARY KEY,
  name text NOT NULL,
  applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS usage.import_runs (
  import_run_id uuid PRIMARY KEY,
  source_system text NOT NULL CHECK (source_system IN ('codex', 'hermes', 'opencode')),
  source_instance text NOT NULL CHECK (length(source_instance) BETWEEN 1 AND 100),
  parser_name text NOT NULL CHECK (length(parser_name) BETWEEN 1 AND 100),
  parser_version text NOT NULL CHECK (length(parser_version) BETWEEN 1 AND 100),
  source_snapshot_hash char(64) NOT NULL CHECK (source_snapshot_hash ~ '^[0-9a-f]{64}$'),
  status text NOT NULL CHECK (
    status IN ('inventory', 'dry_run', 'importing', 'complete', 'failed', 'rolled_back')
  ),
  started_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,
  inserted_count bigint NOT NULL DEFAULT 0 CHECK (inserted_count >= 0),
  updated_count bigint NOT NULL DEFAULT 0 CHECK (updated_count >= 0),
  skipped_count bigint NOT NULL DEFAULT 0 CHECK (skipped_count >= 0),
  error_count bigint NOT NULL DEFAULT 0 CHECK (error_count >= 0),
  CHECK (finished_at IS NULL OR finished_at >= started_at)
);

CREATE TABLE IF NOT EXISTS usage.cutovers (
  source_system text NOT NULL CHECK (source_system IN ('codex', 'hermes', 'opencode')),
  source_instance text NOT NULL CHECK (length(source_instance) BETWEEN 1 AND 100),
  cutover_at timestamptz NOT NULL,
  approval_ref text NOT NULL CHECK (length(approval_ref) BETWEEN 1 AND 100),
  approved_at timestamptz NOT NULL,
  PRIMARY KEY (source_system, source_instance)
);

CREATE TABLE IF NOT EXISTS usage.usage_records (
  record_id uuid PRIMARY KEY,
  record_origin text NOT NULL CHECK (record_origin IN ('backfill', 'live_rollup')),
  source_system text NOT NULL CHECK (source_system IN ('codex', 'hermes', 'opencode')),
  source_instance text NOT NULL CHECK (length(source_instance) BETWEEN 1 AND 100),
  source_record_id text NOT NULL CHECK (length(source_record_id) BETWEEN 1 AND 300),
  source_record_hash char(64) NOT NULL CHECK (source_record_hash ~ '^[0-9a-f]{64}$'),
  source_snapshot_hash char(64) NOT NULL CHECK (source_snapshot_hash ~ '^[0-9a-f]{64}$'),
  parser_name text NOT NULL CHECK (length(parser_name) BETWEEN 1 AND 100),
  parser_version text NOT NULL CHECK (length(parser_version) BETWEEN 1 AND 100),
  import_run_id uuid NOT NULL REFERENCES usage.import_runs(import_run_id),
  occurred_at timestamptz,
  period_start timestamptz,
  period_end timestamptz,
  record_granularity text NOT NULL CHECK (
    record_granularity IN ('api_call', 'turn', 'message', 'session', 'day', 'hour')
  ),
  user_id text CHECK (user_id IS NULL OR length(user_id) BETWEEN 1 AND 200),
  request_model text CHECK (request_model IS NULL OR length(request_model) <= 200),
  response_model text CHECK (response_model IS NULL OR length(response_model) <= 200),
  provider text CHECK (provider IS NULL OR length(provider) <= 200),
  input_tokens bigint CHECK (input_tokens IS NULL OR input_tokens >= 0),
  output_tokens bigint CHECK (output_tokens IS NULL OR output_tokens >= 0),
  cached_input_tokens bigint CHECK (cached_input_tokens IS NULL OR cached_input_tokens >= 0),
  cache_write_tokens bigint CHECK (cache_write_tokens IS NULL OR cache_write_tokens >= 0),
  reasoning_tokens bigint CHECK (reasoning_tokens IS NULL OR reasoning_tokens >= 0),
  total_tokens bigint CHECK (total_tokens IS NULL OR total_tokens >= 0),
  estimated_cost_usd numeric(20, 8) CHECK (
    estimated_cost_usd IS NULL OR estimated_cost_usd >= 0
  ),
  actual_cost_usd numeric(20, 8) CHECK (actual_cost_usd IS NULL OR actual_cost_usd >= 0),
  cost_quality text NOT NULL CHECK (cost_quality IN ('reported', 'estimated', 'unknown')),
  pricing_version text CHECK (pricing_version IS NULL OR length(pricing_version) <= 100),
  quality text NOT NULL CHECK (quality IN ('exact', 'derived', 'partial')),
  quality_reason text NOT NULL CHECK (length(quality_reason) BETWEEN 1 AND 100),
  shared_eligible boolean NOT NULL DEFAULT false,
  imported_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source_system, source_instance, record_origin, source_record_id),
  CHECK (period_end IS NULL OR period_start IS NULL OR period_end >= period_start),
  CHECK (occurred_at IS NOT NULL OR (period_start IS NOT NULL AND period_end IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS usage_records_time_idx
  ON usage.usage_records (source_system, source_instance, COALESCE(occurred_at, period_end));
CREATE INDEX IF NOT EXISTS usage_records_user_time_idx
  ON usage.usage_records (user_id, COALESCE(occurred_at, period_end))
  WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS usage_records_import_run_idx
  ON usage.usage_records (import_run_id);

CREATE TABLE IF NOT EXISTS usage.import_errors (
  import_error_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  import_run_id uuid NOT NULL REFERENCES usage.import_runs(import_run_id),
  opaque_record_key char(64) NOT NULL CHECK (opaque_record_key ~ '^[0-9a-f]{64}$'),
  error_class text NOT NULL CHECK (length(error_class) BETWEEN 1 AND 100),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (import_run_id, opaque_record_key, error_class)
);

CREATE TABLE IF NOT EXISTS usage.coverage_reports (
  import_run_id uuid PRIMARY KEY REFERENCES usage.import_runs(import_run_id),
  source_records bigint NOT NULL CHECK (source_records >= 0),
  exact_records bigint NOT NULL CHECK (exact_records >= 0),
  derived_records bigint NOT NULL CHECK (derived_records >= 0),
  partial_records bigint NOT NULL CHECK (partial_records >= 0),
  missing_records bigint NOT NULL CHECK (missing_records >= 0),
  quarantined_records bigint NOT NULL CHECK (quarantined_records >= 0),
  summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE VIEW grafana.usage_all_time AS
SELECT
  record_id,
  record_origin,
  source_system,
  source_instance,
  COALESCE(occurred_at, period_end) AS event_time,
  period_start,
  period_end,
  record_granularity,
  user_id,
  request_model,
  response_model,
  provider,
  input_tokens,
  output_tokens,
  cached_input_tokens,
  cache_write_tokens,
  reasoning_tokens,
  total_tokens,
  estimated_cost_usd,
  actual_cost_usd,
  cost_quality,
  quality,
  quality_reason
FROM usage.usage_records;

CREATE OR REPLACE VIEW grafana.coverage AS
SELECT
  r.source_system,
  r.source_instance,
  r.parser_name,
  r.parser_version,
  r.status,
  r.started_at,
  r.finished_at,
  c.source_records,
  c.exact_records,
  c.derived_records,
  c.partial_records,
  c.missing_records,
  c.quarantined_records
FROM usage.import_runs AS r
LEFT JOIN usage.coverage_reports AS c USING (import_run_id);

INSERT INTO usage.schema_migrations(version, name)
VALUES (1, 'initial usage ledger')
ON CONFLICT (version) DO NOTHING;

COMMIT;
