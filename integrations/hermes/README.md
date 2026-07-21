# Hermes integration

Phase 1 integrates both `backup-secretary` Hermes instances with the observability system using [`briancaffey/hermes-otel`](https://github.com/briancaffey/hermes-otel).

Do not create a replacement telemetry plugin unless a reproduced compatibility defect makes the existing plugin unusable.

## Routing model

Hermes telemetry has two approved destinations:

1. **Private storage/Grafana** — all approved content-free Hermes telemetry, visible to the owner.
2. **Shared Hermes-only storage/Grafana** — the same approved content-free Hermes telemetry needed for household usage dashboards, visible to authorized Discord users.

Personal Codex, future server telemetry, OpenCode, and Windows host telemetry must never be routed into the shared backend.

Preferred topology:

```text
Hermes main / owashota
  -> central OTel collector/router
       -> private backend
       -> shared Hermes-only backend

Codex CLI / desktop
  -> central OTel collector/router
       -> private backend only
```

A direct `hermes-otel` multi-backend fan-out is acceptable only if real-host validation shows it preserves the same isolation, fail-open behavior, bounded queues, and operability. The implementation must prove Codex/private signals are absent from shared storage.

## Selected telemetry

Collect:

- model and provider;
- input/output/cache/reasoning token counts when reported;
- request and turn duration;
- status, error type, and retry metadata;
- tool names, counts, and outcomes;
- Hermes instance (`main` or `owashota`);
- Discord sender ID.

Do not collect in Phase 1:

- prompt or response bodies;
- conversation history;
- tool arguments or results;
- general application logs.

Required plugin settings:

```yaml
capture_previews: false
capture_conversation_history: false
capture_sender_id: true
capture_logs: false
```

Use [`config.yaml.example`](config.yaml.example) only as a reviewed starting point. Verify the selected plugin version and installed Hermes hook payload before applying it.

## Discord sender identity

With sender capture enabled, a Discord turn is expected to produce:

```text
hermes.sender.id=<raw Discord sender ID>
user.id=discord:<raw Discord sender ID>
```

The root `agent` span should contain the same `user.id` and the session's rolled-up token totals. This allows usage by person to be calculated without adding a high-cardinality Discord ID label to every Prometheus metric.

Initial query shape:

```traceql
{ resource.service.name = "backup-secretary-hermes" && span:name = "agent" }
| sum_over_time(span."gen_ai.usage.total_tokens") by (span."user.id")
```

Create panels only from attributes confirmed on real spans. Cache and reasoning attributes vary by provider and plugin version.

Never commit real query results, screenshots containing sender IDs, or an ID-to-name mapping.

## Installation model

Install the plugin and OTel dependencies while building the Hermes image in `backup-secretary`.

Do not rely on manual `pip install` or `hermes plugins install` inside an already-running container because those changes disappear on recreation and cannot be reviewed reliably.

The `backup-secretary` implementation must:

1. start from a new branch based on its current default branch;
2. pin a reviewed `hermes-otel` release or commit;
3. install the plugin and dependencies into the same Python environment as Hermes;
4. expose it through Hermes' supported plugin discovery mechanism;
5. provide appropriate generated/local plugin configuration for each Hermes home;
6. keep endpoints and credentials outside the public repository;
7. rebuild and restart cleanly without post-start mutation;
8. use a separate PR from the `local-obserbablity` implementation PR.

Initial review baseline:

```text
release: 0.11.0
commit: 0180c5e63b9d035ee0754d9a0d75c3499a8def26
```

Re-check upstream compatibility and security fixes before selecting the actual pin.

## Instance identity

Both instances should use:

```text
service.name=backup-secretary-hermes
service.namespace=backup-secretary
```

They differ by:

```text
service.instance.id=main
service.instance.id=owashota
```

The selected plugin/configuration mechanism must be verified to stamp these values on real spans and metrics.

## Network model

Preferred:

- `local-obserbablity` owns a stable external Docker network such as `local-observability-net`;
- the central collector/router joins that network;
- both Hermes services join that network in addition to their existing application network;
- Hermes sends OTLP/HTTP to the collector's Docker DNS name;
- the collector routes Hermes to private and shared storage and Codex to private storage only.

If real-host constraints require host-LAN routing instead, document container-to-host reachability, firewall impact, and failure behavior.

## Verification

After installation:

1. start private and shared observability components;
2. rebuild and restart both Hermes instances from the pinned image;
3. send one test message through Discord;
4. find the root `agent` trace and descendant LLM/API/tool spans;
5. verify `user.id=discord:<ID>` and rolled-up tokens coexist on the root span;
6. verify prompts, responses, conversation history, tool arguments/results, and general logs are absent;
7. verify the same Hermes data reaches private and shared storage;
8. verify no personal Codex data exists in shared storage/Grafana;
9. repeat for the other Hermes instance;
10. repeat with a second Discord user when safely available;
11. stop private storage, shared storage, and the tunnel separately and verify Hermes continues responding;
12. restore components and verify new telemetry resumes without container mutation.

Real Discord turns are human gate `H7`. Participants should be informed that stable Discord IDs and aggregate usage metadata are collected.

## Friendly names

Committed dashboards display raw `user.id` values by default.

Any Discord-ID-to-friendly-name mapping must remain in ignored local configuration or private Grafana customization. It must not be committed to this repository or `backup-secretary`.