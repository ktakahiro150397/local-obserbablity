BEGIN;

ALTER TABLE usage.api_model_prices
  ADD COLUMN IF NOT EXISTS pricing_notes text NOT NULL DEFAULT 'Standard API list price.';
ALTER TABLE usage.api_model_prices
  ADD COLUMN IF NOT EXISTS long_context_threshold_inclusive boolean NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS usage.api_model_aliases (
  alias_model_id text PRIMARY KEY CHECK (length(alias_model_id) BETWEEN 1 AND 200),
  canonical_model_id text NOT NULL REFERENCES usage.api_model_prices(model_id)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  alias_notes text NOT NULL CHECK (length(alias_notes) BETWEEN 1 AND 500)
);

CREATE TABLE IF NOT EXISTS usage.api_model_unpriced_reasons (
  model_id text PRIMARY KEY CHECK (length(model_id) BETWEEN 1 AND 200),
  public_reason text NOT NULL CHECK (length(public_reason) BETWEEN 1 AND 500),
  source_url text NOT NULL CHECK (source_url ~ '^https://'),
  verified_on date NOT NULL
);

CREATE TABLE IF NOT EXISTS usage.hermes_user_aliases (
  user_id text PRIMARY KEY CHECK (user_id ~ '^discord:[0-9]{5,32}$'),
  display_name text NOT NULL UNIQUE
    CHECK (length(display_name) BETWEEN 1 AND 100),
  updated_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE usage.api_model_aliases IS
  'Observed model-name aliases mapped to one verified canonical API price row.';
COMMENT ON TABLE usage.api_model_unpriced_reasons IS
  'Sanitized explanation for models that intentionally remain outside API-equivalent pricing.';
COMMENT ON TABLE usage.hermes_user_aliases IS
  'Local-only Discord user.id to display-name mappings; values must never be committed.';

INSERT INTO usage.api_model_prices (
  model_id,
  provider_name,
  pricing_version,
  input_usd_per_million,
  cached_input_usd_per_million,
  cache_write_usd_per_million,
  output_usd_per_million,
  long_context_threshold_tokens,
  long_context_threshold_inclusive,
  long_context_input_multiplier,
  long_context_output_multiplier,
  source_url,
  verified_on,
  pricing_notes
)
VALUES
  (
    'gpt-5.5', 'OpenAI', '2026-07-22-standard-list',
    5.00, 0.50, 5.00, 30.00, 272000, false, 2.0, 1.5,
    'https://developers.openai.com/api/docs/pricing', DATE '2026-07-22',
    'Standard API pricing. Cache writes use normal input price because no separate cache-write price is published. Requests over 272K input tokens use 2x input and 1.5x output.'
  ),
  (
    'kimi-k2.6', 'Kimi', '2026-07-22-standard-list',
    0.95, 0.16, 0.95, 4.00, NULL, false, 1.0, 1.0,
    'https://platform.kimi.ai/docs/pricing/chat-k26', DATE '2026-07-22',
    'Cache hit uses the published cache-hit rate; cache writes use the published cache-miss input rate.'
  ),
  (
    'kimi-k2.7-code', 'Kimi', '2026-07-22-standard-list',
    0.95, 0.19, 0.95, 4.00, NULL, false, 1.0, 1.0,
    'https://platform.kimi.ai/', DATE '2026-07-22',
    'Cache hit uses the published cache-hit rate; cache writes use the published input rate.'
  ),
  (
    'grok-4.3', 'xAI', '2026-07-22-standard-list',
    1.25, 0.20, 1.25, 2.50, 200000, true, 2.0, 2.0,
    'https://docs.x.ai/developers/pricing', DATE '2026-07-22',
    'Standard API pricing. Cache writes use normal input price. Requests at or above 200K prompt tokens use the published 2x long-context rates.'
  ),
  (
    'qwen3.6-27b', 'Alibaba Cloud Model Studio', '2026-07-22-singapore-international-list',
    0.60, 0.60, 0.60, 3.60, NULL, false, 1.0, 1.0,
    'https://www.alibabacloud.com/help/en/model-studio/model-pricing', DATE '2026-07-22',
    'Singapore International standard list price. This model is not marked for context-cache discounts, so all input buckets use the normal input rate.'
  ),
  (
    'claude-sonnet-4-6', 'Anthropic', '2026-07-22-global-standard-list',
    3.00, 0.30, 3.75, 15.00, NULL, false, 1.0, 1.0,
    'https://platform.claude.com/docs/en/about-claude/pricing', DATE '2026-07-22',
    'Global standard pricing. The undifferentiated cache-write token bucket uses the standard five-minute cache-write rate.'
  )
ON CONFLICT (model_id) DO UPDATE SET
  provider_name = EXCLUDED.provider_name,
  pricing_version = EXCLUDED.pricing_version,
  input_usd_per_million = EXCLUDED.input_usd_per_million,
  cached_input_usd_per_million = EXCLUDED.cached_input_usd_per_million,
  cache_write_usd_per_million = EXCLUDED.cache_write_usd_per_million,
  output_usd_per_million = EXCLUDED.output_usd_per_million,
  long_context_threshold_tokens = EXCLUDED.long_context_threshold_tokens,
  long_context_threshold_inclusive = EXCLUDED.long_context_threshold_inclusive,
  long_context_input_multiplier = EXCLUDED.long_context_input_multiplier,
  long_context_output_multiplier = EXCLUDED.long_context_output_multiplier,
  source_url = EXCLUDED.source_url,
  verified_on = EXCLUDED.verified_on,
  pricing_notes = EXCLUDED.pricing_notes;

INSERT INTO usage.api_model_aliases (alias_model_id, canonical_model_id, alias_notes)
VALUES
  ('openai/gpt-5.5', 'gpt-5.5', 'Provider-qualified alias observed in Hermes telemetry.'),
  ('moonshotai/kimi-k2.6', 'kimi-k2.6', 'Provider-qualified alias observed in Hermes telemetry.'),
  ('deepseek/deepseek-v4-pro', 'deepseek-v4-pro', 'Provider-qualified alias observed in Hermes telemetry.'),
  ('qwen/qwen3.6-27b', 'qwen3.6-27b', 'Provider-qualified alias observed in Hermes telemetry.')
ON CONFLICT (alias_model_id) DO UPDATE SET
  canonical_model_id = EXCLUDED.canonical_model_id,
  alias_notes = EXCLUDED.alias_notes;

INSERT INTO usage.api_model_unpriced_reasons (
  model_id,
  public_reason,
  source_url,
  verified_on
)
VALUES (
  'google/gemma-4-31b-it',
  'No official per-token API list price: Google documents this 31B model as self-deployed infrastructure.',
  'https://cloud.google.com/blog/products/ai-machine-learning/gemma-4-available-on-google-cloud',
  DATE '2026-07-22'
)
ON CONFLICT (model_id) DO UPDATE SET
  public_reason = EXCLUDED.public_reason,
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
    END AS output_multiplier
  FROM normalized AS n
  LEFT JOIN usage.api_model_aliases AS a ON a.alias_model_id = n.model_id
  LEFT JOIN usage.api_model_prices AS p
    ON p.model_id = COALESCE(a.canonical_model_id, n.model_id)
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

CREATE OR REPLACE VIEW grafana.hermes_usage_dashboard AS
SELECT
  b.*,
  COALESCE(u.display_name, b.user_id) AS user_label,
  CASE
    WHEN b.pricing_matched THEN COALESCE(a.canonical_model_id, b.model_id)
    ELSE NULL
  END AS priced_model_id,
  p.pricing_notes,
  CASE
    WHEN b.pricing_matched THEN NULL
    WHEN b.model_id IS NULL OR b.model_id = '' THEN 'Model identifier missing from telemetry.'
    WHEN e.public_reason IS NOT NULL THEN e.public_reason
    ELSE 'No verified official API price is registered yet.'
  END AS unpriced_reason
FROM grafana.hermes_usage_api_equivalent AS b
LEFT JOIN usage.hermes_user_aliases AS u ON u.user_id = b.user_id
LEFT JOIN usage.api_model_aliases AS a ON a.alias_model_id = b.model_id
LEFT JOIN usage.api_model_prices AS p
  ON p.model_id = COALESCE(a.canonical_model_id, b.model_id)
LEFT JOIN usage.api_model_unpriced_reasons AS e ON e.model_id = b.model_id;

INSERT INTO usage.schema_migrations(version, name)
VALUES (4, 'pricing aliases, exclusions, and local Hermes user display names')
ON CONFLICT (version) DO NOTHING;

COMMIT;
