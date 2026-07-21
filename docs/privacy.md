# Privacy and data handling

## Intentional personal identifiers

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

The shared Grafana also stores the authenticated Cloudflare Access email as the Grafana account identity. That email is used for login and permissions only; it is not added to Hermes telemetry or used as the Discord usage key.

## Phase 1 collection policy

Collected in the private stack:

- Discord sender ID for Hermes gateway turns;
- source/client/instance;
- model and provider;
- token counts;
- cache and reasoning token breakdown when supplied;
- request/turn durations;
- status and error type;
- tool name/count/outcome;
- application/version metadata;
- Codex CLI/desktop telemetry;
- Grafana account metadata required for administration.

Collected in the shared stack:

- Hermes telemetry approved for every permitted Discord user;
- Discord sender ID accounting attributes;
- model/provider/token/duration/error/tool summary metadata;
- Access-backed Grafana user email and role in the Grafana user database.

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

## Private versus shared boundary

The private stack may hold Codex and Hermes telemetry and later host telemetry.

The shared Cloudflare-published stack must receive only Hermes telemetry that every approved Discord user is allowed to inspect. It must not have a data source pointing at the private all-data backend.

This separation is required because Grafana OSS dashboard/folder permissions do not create a hard data-source boundary. Do not rely on hiding dashboards to protect personal Codex or infrastructure data.

## Public repository rules

Never commit:

- real Discord IDs;
- ID-to-name aliases;
- approved user email addresses;
- Cloudflare account/team identifiers when they reveal private configuration;
- tunnel UUIDs, credentials or tokens;
- Access audience tags;
- private hostnames/IP addresses;
- Grafana passwords;
- OTLP authentication headers;
- API/provider keys;
- telemetry database files;
- screenshots containing personal IDs, email addresses or private infrastructure details.

Examples must use obvious placeholders such as `123456789012345678`, `<DISCORD_USER_ID>`, `<ACCESS_EMAIL>` and `<TUNNEL_TOKEN>`.

## Friendly user names

The committed dashboards should group by raw `user.id`.

A friendly mapping such as:

```text
discord:123... -> Alice
```

must live only in an ignored local file or private Grafana customization. It must not be committed to this public repository.

## Access control

### Private stack

- Keep private Grafana local-only or restricted to the owner/trusted LAN.
- Keep OTLP on the trusted LAN.
- Use a non-default Grafana administrator password.
- Do not configure router port forwarding.
- Do not enable anonymous Grafana access.

### Shared stack

- Publish only `observe.yanelmo.net` through an outbound-only named Cloudflare Tunnel.
- Protect it with a Cloudflare Access self-hosted application.
- Allow exact approved individual email identities only.
- Do not use an `Everyone` rule, bypass policy or shared login.
- Auto-create Grafana users from the authenticated Access email with Viewer role.
- Keep the owner and local break-glass account as the only administrators unless intentionally changed.
- Trust the Access identity header only from the dedicated tunnel/proxy network.
- Never publish OTLP, the private Grafana or the private backend through the tunnel.
- Removing an email from the Access policy must be part of the user offboarding procedure.

## Retention and deletion

Initial retention is intentionally undecided until storage growth is measured.

The Phase 1 runbook must document:

- where private and shared data are stored;
- how to back up and restore each stack;
- how to delete all telemetry;
- how to delete or disable a Grafana user account;
- how to remove an email from Cloudflare Access;
- whether the selected backend can selectively delete traces for one Discord ID;
- what to do when selective deletion is unavailable.

If selective deletion is unavailable, the practical removal procedure may require deleting the relevant retention window or resetting the local telemetry store. This limitation must be stated plainly.

## Dashboard and PR evidence

Before attaching screenshots or logs to a public issue/PR:

- redact Discord IDs;
- redact user email addresses;
- redact private addresses and hostnames;
- redact Cloudflare tunnel/account/AUD identifiers;
- redact tokens and credentials;
- crop prompt/response content if any appears unexpectedly;
- prefer text-based assertions with synthetic test IDs and emails.
