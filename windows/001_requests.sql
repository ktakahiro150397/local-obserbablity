-- Additive, private-only request ledger. Legacy history is never rewritten.
BEGIN;
CREATE SCHEMA IF NOT EXISTS usage;
CREATE SCHEMA IF NOT EXISTS grafana;
REVOKE ALL ON SCHEMA usage, grafana FROM PUBLIC;
CREATE TABLE IF NOT EXISTS usage.requests (
  event_key char(64) PRIMARY KEY,
  source text NOT NULL CHECK (source IN ('hermes','codex','otlp')),
  client text NOT NULL, instance text NOT NULL, profile text,
  user_id text NOT NULL, channel_id text, thread_id text,
  session_id text, turn_id text, request_id text, parent_turn_id text,
  provider text, model text,
  granularity text NOT NULL CHECK (granularity IN ('request','turn')),
  quality text NOT NULL CHECK (quality IN ('reported','partial','missing')),
  outcome text NOT NULL CHECK (outcome IN ('ok','error','unknown')),
  retry integer, started_at timestamptz NOT NULL, occurred_at timestamptz NOT NULL,
  received_at timestamptz NOT NULL DEFAULT now(),
  input_tokens bigint CHECK (input_tokens >= 0), output_tokens bigint CHECK (output_tokens >= 0),
  cache_read_tokens bigint CHECK (cache_read_tokens >= 0), cache_write_tokens bigint CHECK (cache_write_tokens >= 0),
  reasoning_tokens bigint CHECK (reasoning_tokens >= 0), total_tokens bigint CHECK (total_tokens >= 0),
  CHECK (occurred_at >= started_at)
);
CREATE INDEX IF NOT EXISTS requests_time ON usage.requests(occurred_at);
CREATE INDEX IF NOT EXISTS requests_user_thread ON usage.requests(user_id,thread_id,occurred_at);
CREATE OR REPLACE VIEW grafana.requests AS SELECT * FROM usage.requests;
CREATE OR REPLACE VIEW grafana.usage_health AS
SELECT source,instance,min(occurred_at) AS measurement_start,max(occurred_at) AS last_event,
       max(received_at) AS last_received,count(*) AS records,
       count(*) FILTER (WHERE quality != 'reported') AS incomplete_records,
       count(*) FILTER (WHERE user_id='unattributed') AS unattributed_records
FROM usage.requests GROUP BY source,instance;
GRANT USAGE ON SCHEMA usage TO ledger_writer;
GRANT SELECT,INSERT ON usage.requests TO ledger_writer;
GRANT USAGE ON SCHEMA grafana TO ledger_grafana;
GRANT SELECT ON grafana.requests,grafana.usage_health TO ledger_grafana;
CREATE TABLE IF NOT EXISTS usage.pipeline_health (
  observed_at timestamptz NOT NULL DEFAULT now(),
  component text NOT NULL,
  healthy boolean NOT NULL,
  queue_bytes bigint,
  failures double precision,
  PRIMARY KEY (observed_at,component)
);
CREATE OR REPLACE VIEW grafana.pipeline_health AS SELECT * FROM usage.pipeline_health;
GRANT SELECT ON grafana.pipeline_health TO ledger_grafana;
COMMIT;
