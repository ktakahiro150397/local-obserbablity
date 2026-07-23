BEGIN;

ALTER TABLE usage.usage_records
  ADD COLUMN IF NOT EXISTS client text
  CHECK (client IS NULL OR length(client) BETWEEN 1 AND 100);

SELECT 'ALTER TABLE usage.live_rollup_checkpoints '
       'DROP CONSTRAINT IF EXISTS live_rollup_checkpoints_source_system_check'
WHERE :'ledger_domain' = 'private'
\gexec

SELECT 'ALTER TABLE usage.live_rollup_checkpoints '
       'ADD CONSTRAINT private_live_rollup_sources '
       'CHECK (source_system IN (''codex'', ''hermes''))'
WHERE :'ledger_domain' = 'private'
  AND NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'private_live_rollup_sources'
  )
\gexec

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
  quality_reason,
  client
FROM usage.usage_records;

CREATE OR REPLACE VIEW grafana.codex_usage_api_equivalent AS
WITH normalized AS (
  SELECT
    r.record_id,
    r.source_instance,
    COALESCE(r.occurred_at, r.period_end) AS event_time,
    r.record_granularity,
    r.client,
    COALESCE(r.response_model, r.request_model) AS model_id,
    COALESCE(r.input_tokens, 0)::bigint AS input_tokens,
    COALESCE(r.output_tokens, 0)::bigint AS output_tokens,
    LEAST(
      COALESCE(r.cached_input_tokens, 0),
      COALESCE(r.input_tokens, 0)
    )::bigint AS cached_input_tokens,
    LEAST(
      COALESCE(r.cache_write_tokens, 0),
      GREATEST(
        COALESCE(r.input_tokens, 0) - LEAST(
          COALESCE(r.cached_input_tokens, 0),
          COALESCE(r.input_tokens, 0)
        ),
        0
      )
    )::bigint AS cache_write_tokens,
    COALESCE(r.reasoning_tokens, 0)::bigint AS reasoning_tokens,
    COALESCE(r.total_tokens, 0)::bigint AS total_tokens
  FROM usage.usage_records AS r
  WHERE r.source_system = 'codex'
), priced AS (
  SELECT
    n.*,
    COALESCE(a.canonical_model_id, n.model_id) AS canonical_model_id,
    p.provider_name AS price_provider,
    p.pricing_version,
    p.pricing_notes,
    p.input_usd_per_million,
    p.cached_input_usd_per_million,
    p.cache_write_usd_per_million,
    p.output_usd_per_million,
    CASE
      WHEN p.long_context_threshold_tokens IS NOT NULL
        AND n.record_granularity IN ('api_call', 'turn', 'message')
        AND (
          n.input_tokens > p.long_context_threshold_tokens
          OR (
            p.long_context_threshold_inclusive
            AND n.input_tokens = p.long_context_threshold_tokens
          )
        )
      THEN p.long_context_input_multiplier
      ELSE 1
    END AS input_multiplier,
    CASE
      WHEN p.long_context_threshold_tokens IS NOT NULL
        AND n.record_granularity IN ('api_call', 'turn', 'message')
        AND (
          n.input_tokens > p.long_context_threshold_tokens
          OR (
            p.long_context_threshold_inclusive
            AND n.input_tokens = p.long_context_threshold_tokens
          )
        )
      THEN p.long_context_output_multiplier
      ELSE 1
    END AS output_multiplier,
    e.public_reason
  FROM normalized AS n
  LEFT JOIN usage.api_model_aliases AS a
    ON a.alias_model_id = n.model_id
  LEFT JOIN usage.api_model_prices AS p
    ON p.model_id = COALESCE(a.canonical_model_id, n.model_id)
  LEFT JOIN usage.api_model_unpriced_reasons AS e
    ON e.model_id = n.model_id
)
SELECT
  record_id,
  source_instance,
  event_time,
  record_granularity,
  client,
  model_id,
  input_tokens,
  output_tokens,
  cached_input_tokens,
  cache_write_tokens,
  reasoning_tokens,
  total_tokens,
  price_provider,
  pricing_version,
  (pricing_version IS NOT NULL) AS pricing_matched,
  CASE
    WHEN pricing_version IS NULL THEN NULL
    ELSE ROUND((
      (
        GREATEST(
          input_tokens - cached_input_tokens - cache_write_tokens,
          0
        ) * input_usd_per_million
        + cached_input_tokens * cached_input_usd_per_million
        + cache_write_tokens * cache_write_usd_per_million
      ) * input_multiplier
      + output_tokens * output_usd_per_million * output_multiplier
    ) / 1000000.0, 8)
  END AS estimated_api_cost_usd,
  CASE
    WHEN pricing_version IS NOT NULL THEN canonical_model_id
    ELSE NULL
  END AS priced_model_id,
  pricing_notes,
  CASE
    WHEN pricing_version IS NOT NULL THEN NULL
    WHEN model_id IS NULL OR model_id = ''
      THEN 'Model identifier missing from telemetry.'
    WHEN public_reason IS NOT NULL THEN public_reason
    ELSE 'No verified official API price is registered yet.'
  END AS unpriced_reason
FROM priced;

INSERT INTO usage.schema_migrations(version, name)
VALUES (6, 'private Codex live rollup and dashboard view')
ON CONFLICT (version) DO NOTHING;

COMMIT;
