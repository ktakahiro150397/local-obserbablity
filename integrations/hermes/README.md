# Hermes integration

Phase 1 integrates the two `backup-secretary` Hermes instances with the local OTLP backend by using [`briancaffey/hermes-otel`](https://github.com/briancaffey/hermes-otel).

Do not create a separate Hermes telemetry plugin unless a reproduced compatibility defect makes the existing plugin unusable.

## Selected behavior

The integration must collect:

- model and provider;
- input/output/cache/reasoning token counts when reported;
- request and turn duration;
- errors and retries;
- tool names, counts and outcomes;
- Hermes instance (`main` or `owashota`);
- Discord sender ID.

It must not collect prompt, response, conversation-history, tool-argument, tool-result or general-log content in Phase 1.

Use the settings in [`config.yaml.example`](config.yaml.example):

```yaml
capture_previews: false
capture_conversation_history: false
capture_sender_id: true
capture_logs: false
```

## Discord sender identity

With sender capture enabled, a Discord session is expected to produce:

```text
hermes.sender.id=<raw Discord sender ID>
user.id=discord:<raw Discord sender ID>
```

The root `agent` span receives the session's rolled-up token totals and the same `user.id`. This allows Grafana/Tempo to calculate token usage by person without adding a high-cardinality Discord ID label to every Prometheus metric.

Initial query shape:

```traceql
{ resource.service.name = "backup-secretary-hermes" && span:name = "agent" }
| sum_over_time(span."gen_ai.usage.total_tokens") by (span."user.id")
```

Build similar panels from attributes actually confirmed on real spans:

- `gen_ai.usage.input_tokens`;
- `gen_ai.usage.output_tokens`;
- cache-read/cache-creation aliases emitted by the selected plugin version;
- `gen_ai.usage.reasoning.output_tokens`.

Do not commit real query results or screenshots containing sender IDs.

## Installation model

Install the plugin and its Python dependencies while building the Hermes image in `backup-secretary`.

Do not rely on manually running `pip install` or `hermes plugins install` inside an already-running container, because those changes disappear when the container is recreated.

The implementation in `backup-secretary` should:

1. pin a reviewed `hermes-otel` release or commit;
2. install its OTel dependencies into the same Python environment as Hermes;
3. make the plugin available through Hermes' supported plugin discovery mechanism;
4. supply a separate generated/configured `config.yaml` for each Hermes home;
5. keep endpoints and any credentials outside the public Git repository;
6. restart cleanly without post-start container mutation.

## Instance identity

Both instances use:

```text
service.name=backup-secretary-hermes
service.namespace=backup-secretary
```

They differ by:

```text
service.instance.id=main
service.instance.id=owashota
```

This permits combined and per-instance dashboards while keeping one logical service name.

## Network model

Preferred:

- `local-obserbablity` owns a named external Docker network such as `local-observability-net`;
- its OTLP receiver joins that network;
- both Hermes services join the same network;
- Hermes uses the collector's Docker DNS name and port 4318.

The existing `backup-secretary` application network remains in place. Hermes may join both networks.

## Verification

After installation:

1. Start the observability backend.
2. Rebuild and restart Hermes from the pinned image.
3. Send one test message through Discord.
4. Confirm an `agent` trace and descendant LLM/API/tool spans appear.
5. Confirm the root span has both `user.id=discord:<ID>` and token totals.
6. Confirm no prompt, response or tool payload appears.
7. Repeat with the other Hermes instance.
8. Stop the observability backend and confirm Hermes continues responding.
9. Restart the backend and confirm new telemetry resumes without modifying the Hermes container.

## Friendly names

The public repository and provisioned default dashboards should display the raw local `user.id` value.

Any Discord-ID-to-friendly-name mapping must be stored in a private, ignored local file or private Grafana configuration. It must not be committed here or to `backup-secretary`.
