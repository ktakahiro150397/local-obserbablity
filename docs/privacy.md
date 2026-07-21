# Privacy and data handling

## Intentional personal identifier

Phase 1 intentionally records the Discord sender ID for Hermes traffic so household/shared-instance usage can be grouped by user.

Expected attributes:

```text
hermes.sender.id=<Discord sender ID>
user.id=discord:<Discord sender ID>
```

This is opt-in behavior from `hermes-otel` and must be enabled with:

```yaml
capture_sender_id: true
```

The raw ID is stable enough for accounting but must be treated as personal data.

## Phase 1 collection policy

Collected:

- Discord sender ID for Hermes gateway turns;
- source/client/instance;
- model and provider;
- token counts;
- cache and reasoning token breakdown when supplied;
- request/turn durations;
- status and error type;
- tool name/count/outcome;
- application/version metadata.

Not collected by design:

- raw user prompts;
- assistant response bodies;
- conversation history;
- tool arguments;
- tool output/results;
- general Hermes/Codex application logs;
- Discord display names, avatars or message content.

Required settings for Hermes:

```yaml
capture_previews: false
capture_conversation_history: false
capture_sender_id: true
capture_logs: false
```

Required Codex policy:

```toml
[otel]
log_user_prompt = false
exporter = "none" # Disable structured OTel log events in Phase 1.
```

Metrics and traces may still be enabled through their dedicated exporters.

## Public repository rules

Never commit:

- real Discord IDs;
- ID-to-name aliases;
- private hostnames/IP addresses;
- Grafana passwords;
- OTLP authentication headers;
- API/provider keys;
- telemetry database files;
- screenshots containing personal IDs or private infrastructure details.

Examples must use obvious placeholders such as `123456789012345678` or `<DISCORD_USER_ID>`.

## Friendly user names

The public dashboards should group by raw `user.id`.

A friendly mapping such as:

```text
discord:123... -> Alice
```

must live only in an ignored local file or private Grafana customization. It must not be committed to this public repository.

## Access control

- Keep Grafana and OTLP on the trusted LAN.
- Use a non-default Grafana admin password.
- Do not configure router port forwarding.
- Do not expose the stack using a public tunnel.
- Restrict the server firewall to the main PC/trusted subnet where practical.
- Do not enable anonymous Grafana access.

## Retention and deletion

Initial retention is intentionally undecided until storage growth is measured.

The Phase 1 runbook must document:

- where data is stored;
- how to back it up and restore it;
- how to delete all telemetry;
- whether the selected backend can selectively delete traces for one Discord ID;
- what to do when selective deletion is unavailable.

If selective deletion is unavailable, the practical removal procedure may require deleting the relevant retention window or resetting the local telemetry store. This limitation must be stated plainly.

## Dashboard and PR evidence

Before attaching screenshots or logs to a public issue/PR:

- redact Discord IDs;
- redact private addresses and hostnames;
- redact tokens and credentials;
- crop prompt/response content if any appears unexpectedly;
- prefer text-based assertions with synthetic test IDs.
