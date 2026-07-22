# Hermes live rollup

This service copies only approved, content-free Hermes root-span usage fields
from the shared Tempo backend into the isolated shared PostgreSQL ledger.

It runs every five minutes by default. Each normal poll re-reads the previous
30 minutes and upserts by an opaque hash of the Tempo trace/span identity. A
persistent checkpoint catches up after longer outages while the source traces
remain inside Tempo retention.

Stored fields are limited to:

- source instance and event timestamps;
- stable `user.id` or the sender-ID fallback;
- request/response model and a real model provider when present;
- input, output, cache-read, cache-write, reasoning, and total tokens;
- provenance, quality, and opaque deduplication identifiers.

Prompt/response bodies, conversation history, tool arguments/results, logs,
trace IDs, and span IDs are not stored. Transport values such as `discord` are
not misrepresented as the model provider.

An otherwise unattributed trace containing the `tool.skill_manage` span is
classified as `system:self-improvement`. A trace with a real sender keeps that
sender even when it also uses `skill_manage`; other unattributed work remains
unclassified. Grafana renders the system ID as `Hermes self-improvement` so
automatic maintenance usage is not charged to a Discord user.

The worker refuses to advance an instance without its approved cutover row.
It therefore remains a healthy no-op on a new installation until the Phase 4
cutover is present.

Configuration defaults:

| Variable | Default | Meaning |
|---|---:|---|
| `ROLLUP_INTERVAL_SECONDS` | `300` | Poll frequency |
| `ROLLUP_OVERLAP_SECONDS` | `1800` | Re-read overlap |
| `ROLLUP_GRACE_SECONDS` | `120` | Delay before considering spans settled |
| `ROLLUP_MAX_WINDOW_SECONDS` | `7200` | Maximum catch-up query window |
| `ROLLUP_SEARCH_LIMIT` | `1000` | Tempo search limit before recursive splitting |

Run unit tests:

```bash
python -m unittest discover -s rollup/tests -v
```

Run one containerized cycle after the stack and schema migration are ready:

```bash
docker compose run --rm hermes-live-rollup --once
```

Re-read existing live unattributed records while their traces remain in Tempo:

```bash
docker compose run --rm hermes-live-rollup --reconcile-unattributed
```

This mode is idempotent, does not move the normal checkpoint backwards, and
reports only counts. It updates rows only when the content-free trace classifier
changes their attribution.
