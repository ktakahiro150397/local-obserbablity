BEGIN;

CREATE OR REPLACE VIEW grafana.hermes_usage_dashboard AS
SELECT
  b.*,
  COALESCE(
    u.display_name,
    CASE b.user_id
      WHEN 'system:self-improvement' THEN 'Hermes self-improvement'
      ELSE b.user_id
    END
  ) AS user_label,
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
VALUES (5, 'friendly label for Hermes self-improvement usage')
ON CONFLICT (version) DO NOTHING;

COMMIT;
