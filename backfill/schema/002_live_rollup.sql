BEGIN;

CREATE TABLE IF NOT EXISTS usage.live_rollup_checkpoints (
  source_system text NOT NULL CHECK (source_system = 'hermes'),
  source_instance text NOT NULL CHECK (length(source_instance) BETWEEN 1 AND 100),
  checkpoint_at timestamptz NOT NULL,
  last_success_at timestamptz NOT NULL DEFAULT now(),
  last_run_id uuid REFERENCES usage.import_runs(import_run_id),
  PRIMARY KEY (source_system, source_instance),
  FOREIGN KEY (source_system, source_instance)
    REFERENCES usage.cutovers(source_system, source_instance)
    ON DELETE CASCADE
);

INSERT INTO usage.schema_migrations(version, name)
VALUES (2, 'hermes live rollup checkpoints')
ON CONFLICT (version) DO NOTHING;

COMMIT;
