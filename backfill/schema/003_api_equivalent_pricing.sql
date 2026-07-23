BEGIN;

CREATE TABLE IF NOT EXISTS usage.api_model_prices (
  model_id text PRIMARY KEY CHECK (length(model_id) BETWEEN 1 AND 200),
  provider_name text NOT NULL CHECK (length(provider_name) BETWEEN 1 AND 100),
  pricing_version text NOT NULL CHECK (length(pricing_version) BETWEEN 1 AND 100),
  input_usd_per_million numeric(20, 8) NOT NULL CHECK (input_usd_per_million >= 0),
  cached_input_usd_per_million numeric(20, 8) NOT NULL CHECK (cached_input_usd_per_million >= 0),
  cache_write_usd_per_million numeric(20, 8) NOT NULL CHECK (cache_write_usd_per_million >= 0),
  output_usd_per_million numeric(20, 8) NOT NULL CHECK (output_usd_per_million >= 0),
  long_context_threshold_tokens bigint CHECK (long_context_threshold_tokens > 0),
  long_context_input_multiplier numeric(10, 4) NOT NULL DEFAULT 1
    CHECK (long_context_input_multiplier >= 1),
  long_context_output_multiplier numeric(10, 4) NOT NULL DEFAULT 1
    CHECK (long_context_output_multiplier >= 1),
  source_url text NOT NULL CHECK (source_url ~ '^https://'),
  verified_on date NOT NULL
);

COMMENT ON TABLE usage.api_model_prices IS
  'Current standard API list prices used only for API-equivalent dashboard estimates; not billed cost.';

INSERT INTO usage.api_model_prices (
  model_id,
  provider_name,
  pricing_version,
  input_usd_per_million,
  cached_input_usd_per_million,
  cache_write_usd_per_million,
  output_usd_per_million,
  long_context_threshold_tokens,
  long_context_input_multiplier,
  long_context_output_multiplier,
  source_url,
  verified_on
)
VALUES
  ('gpt-5.6-sol', 'OpenAI', '2026-07-22-standard-list', 5.00, 0.50, 6.25, 30.00, 272000, 2.0, 1.5, 'https://developers.openai.com/api/docs/pricing', DATE '2026-07-22'),
  ('gpt-5.6-terra', 'OpenAI', '2026-07-22-standard-list', 2.50, 0.25, 3.125, 15.00, 272000, 2.0, 1.5, 'https://developers.openai.com/api/docs/pricing', DATE '2026-07-22'),
  ('gpt-5.6-luna', 'OpenAI', '2026-07-22-standard-list', 1.00, 0.10, 1.25, 6.00, 272000, 2.0, 1.5, 'https://developers.openai.com/api/docs/pricing', DATE '2026-07-22'),
  ('deepseek-v4-flash', 'DeepSeek', '2026-07-22-standard-list', 0.14, 0.0028, 0.14, 0.28, NULL, 1.0, 1.0, 'https://api-docs.deepseek.com/quick_start/pricing/', DATE '2026-07-22'),
  ('deepseek-v4-pro', 'DeepSeek', '2026-07-22-standard-list', 0.435, 0.003625, 0.435, 0.87, NULL, 1.0, 1.0, 'https://api-docs.deepseek.com/quick_start/pricing/', DATE '2026-07-22'),
  ('kimi-k3', 'Kimi', '2026-07-22-standard-list', 3.00, 0.30, 3.00, 15.00, NULL, 1.0, 1.0, 'https://platform.kimi.ai/', DATE '2026-07-22')
ON CONFLICT (model_id) DO UPDATE SET
  provider_name = EXCLUDED.provider_name,
  pricing_version = EXCLUDED.pricing_version,
  input_usd_per_million = EXCLUDED.input_usd_per_million,
  cached_input_usd_per_million = EXCLUDED.cached_input_usd_per_million,
  cache_write_usd_per_million = EXCLUDED.cache_write_usd_per_million,
  output_usd_per_million = EXCLUDED.output_usd_per_million,
  long_context_threshold_tokens = EXCLUDED.long_context_threshold_tokens,
  long_context_input_multiplier = EXCLUDED.long_context_input_multiplier,
  long_context_output_multiplier = EXCLUDED.long_context_output_multiplier,
  source_url = EXCLUDED.source_url,
  verified_on = EXCLUDED.verified_on;

CREATE OR REPLACE VIEW grafana.api_model_prices AS
SELECT
  model_id,
  provider_name,
  pricing_version,
  input_usd_per_million,
  cached_input_usd_per_million,
  cache_write_usd_per_million,
  output_usd_per_million,
  long_context_threshold_tokens,
  long_context_input_multiplier,
  long_context_output_multiplier,
  source_url,
  verified_on
FROM usage.api_model_prices;

CREATE OR REPLACE VIEW grafana.hermes_usage_api_equivalent AS
WITH normalized AS (
  SELECT
    r.record_id,
    r.source_instance,
    COALESCE(r.occurred_at, r.period_end) AS event_time,
    r.record_granularity,
    r.user_id,
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
    COALESCE(r.total_tokens, 0)::bigint AS total_tokens
  FROM usage.usage_records AS r
  WHERE r.source_system = 'hermes'
), priced AS (
  SELECT
    n.*,
    p.provider_name AS price_provider,
    p.pricing_version,
    p.input_usd_per_million,
    p.cached_input_usd_per_million,
    p.cache_write_usd_per_million,
    p.output_usd_per_million,
    CASE
      WHEN p.long_context_threshold_tokens IS NOT NULL
        AND n.record_granularity IN ('api_call', 'turn', 'message')
        AND n.input_tokens > p.long_context_threshold_tokens
      THEN p.long_context_input_multiplier
      ELSE 1
    END AS input_multiplier,
    CASE
      WHEN p.long_context_threshold_tokens IS NOT NULL
        AND n.record_granularity IN ('api_call', 'turn', 'message')
        AND n.input_tokens > p.long_context_threshold_tokens
      THEN p.long_context_output_multiplier
      ELSE 1
    END AS output_multiplier
  FROM normalized AS n
  LEFT JOIN usage.api_model_prices AS p USING (model_id)
)
SELECT
  record_id,
  source_instance,
  event_time,
  record_granularity,
  user_id,
  model_id,
  input_tokens,
  output_tokens,
  cached_input_tokens,
  cache_write_tokens,
  total_tokens,
  price_provider,
  pricing_version,
  (pricing_version IS NOT NULL) AS pricing_matched,
  CASE
    WHEN pricing_version IS NULL THEN NULL
    ELSE ROUND((
      (
        GREATEST(input_tokens - cached_input_tokens - cache_write_tokens, 0)
          * input_usd_per_million
        + cached_input_tokens * cached_input_usd_per_million
        + cache_write_tokens * cache_write_usd_per_million
      ) * input_multiplier
      + output_tokens * output_usd_per_million * output_multiplier
    ) / 1000000.0, 8)
  END AS estimated_api_cost_usd
FROM priced;

INSERT INTO usage.schema_migrations(version, name)
VALUES (3, 'current API-equivalent model pricing')
ON CONFLICT (version) DO NOTHING;

COMMIT;
