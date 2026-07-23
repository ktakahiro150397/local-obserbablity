# Privacy and data handling

## Intentional personal identifiers

Phase 1 intentionally records the Discord sender ID for Hermes traffic so household/shared-instance usage can be grouped by user.

Expected telemetry attributes:

```text
hermes.sender.id=<Discord sender ID>
user.id=discord:<Discord sender ID>
```

This is opt-in behavior from `hermes-otel` and must be enabled with:

```yaml
capture_sender_id: true
```

The raw Discord ID is stable enough for accounting but must be treated as personal data.

The shared Grafana authentication layer also processes each approved user's email address through Cloudflare Access. Google and OTP authentication both resolve to the Access-authenticated email, which Grafana uses as its individual account identity.

Discord IDs and Access/Grafana emails are separate identifiers. Any mapping between them is personal data and must remain local and outside Git.

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

Not collected by telemetry design:

- raw user prompts;
- assistant response bodies;
- conversation history;
- tool arguments;
- tool output/results;
- general Hermes/Codex application logs;
- Discord display names, avatars or message content;
- Google profile information beyond the email identity supplied to Access/Grafana;
- Google access or refresh tokens in repository-managed telemetry.

Required Hermes settings:

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
exporter = "none"
```

Metrics and traces may still be enabled through their dedicated exporters.

## Private versus shared boundary

The private stack may hold Codex and Hermes telemetry and later host telemetry.

The shared Cloudflare-published stack must receive only Hermes telemetry that every approved Discord user is allowed to inspect. It must not have a data source pointing at the private all-data backend.

This separation is required because Grafana OSS dashboard/folder permissions do not create a hard data-source boundary. Do not rely on hiding dashboards to protect personal Codex or infrastructure data.

## Phase 4 historical source policy

Phase 4 may read historical Codex, Hermes, and OpenCode storage, which can contain far more sensitive content than the usage fields being imported. Historical importers therefore use a stricter extraction boundary:

- operate on read-only snapshots or SQLite backups;
- inspect schemas and usage metadata without selecting message/prompt/reasoning/tool-content columns;
- stream JSONL and discard content-bearing records/fields rather than copying them into staging;
- persist only normalized usage, provenance, quality, opaque source IDs/hashes, and original timestamps;
- keep full local paths, Windows usernames, database dumps, source snapshots, and detailed manifests outside Git;
- use synthetic fixtures in tests;
- never improve coverage by estimating tokens from message content, character counts, elapsed time, or rate limits.

The private historical ledger may contain Codex, Hermes, and OpenCode usage. The shared historical ledger/data source may contain only the approved content-free Hermes subset and must not have credentials capable of querying private historical tables.

The Codex live rollup uses the same strict extraction boundary. It reads only
approved Codex service names, the `session_task.turn` span, turn timestamps,
the model identifier, and `codex.turn.token_usage.*` numeric attributes. It
does not copy prompt/response text, tool payloads, paths, session identifiers,
trace IDs, span IDs, account fields, or general attributes. Raw trace/span IDs
are used only in memory to derive opaque deduplication keys.

Discord IDs retained in Hermes backfill remain personal data. Access/Grafana email identities are not added to historical telemetry. Any email-to-Discord-ID or friendly-name mapping remains local and ignored.

Source snapshots should be retained only as long as required for verified import/rollback under an owner-approved local retention policy. Deleting an original source snapshot must not silently remove provenance from imported rows; imported rows keep opaque hashes and import-run metadata.

See [`phase-4-backfill.md`](phase-4-backfill.md) for cutover, provenance, quality, deduplication, and rollback requirements.

## Access identity policy

- Google and One-time PIN may both authenticate a user.
- Authorization uses exact approved email addresses.
- Users should use the same email for Google and OTP to avoid duplicate Grafana accounts.
- Google group membership is not the Phase 1 authorization boundary.
- Do not use shared mailboxes or shared Grafana identities.
- Removing an email from Cloudflare Access must revoke future access.
- Access and Grafana audit/user data must be treated as personal data.

## Public repository rules

Never commit:

- real Discord IDs;
- Discord-ID-to-name or Discord-ID-to-email aliases;
- approved user email addresses;
- Google OAuth Client ID or Client Secret;
- Cloudflare account, team, tunnel or Access application identifiers;
- Access AUD values;
- tunnel tokens or credential files;
- private hostnames/IP addresses;
- Grafana passwords;
- OTLP authentication headers;
- API/provider keys;
- live or historical telemetry database files;
- Codex/Hermes/OpenCode source snapshots or database dumps;
- backfill manifests containing private paths, source identifiers, or real aggregate results;
- screenshots containing personal IDs, email addresses or private infrastructure details.

Examples must use obvious placeholders such as `<DISCORD_USER_ID>`, `<APPROVED_EMAIL>` or `<CLOUDFLARE_TEAM_NAME>`.

## Friendly user names

Committed dashboards should group by raw `user.id` unless a private friendly-name mapping is configured locally.

Mappings such as:

```text
discord:123... -> Alice
```

or:

```text
person@example.com -> discord:123...
```

must live only in ignored local files or private Grafana customization.

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
- Offer Google and One-time PIN as login methods.
- Allow exact approved individual email identities only.
- Do not use an `Everyone` rule, bypass policy, shared login or Google group authorization.
- Auto-create Grafana users from the authenticated Access email with Viewer role.
- Keep the owner and local break-glass account as the only administrators unless intentionally changed.
- Trust the Access identity header only from the dedicated tunnel/proxy network.
- Never publish OTLP, private Grafana or the private backend through the tunnel.
- Removing an email from Access must be part of user offboarding.

## Retention and deletion

Initial live retention is intentionally undecided until storage growth is measured.

The Phase 1 runbook must document:

- where private and shared telemetry data are stored;
- where Grafana user/account data are stored;
- how to back up and restore both stacks;
- how to delete all telemetry;
- how to revoke an Access email;
- how to disable/delete a Grafana user;
- whether the selected backend can selectively delete traces for one Discord ID;
- what to do when selective deletion is unavailable.

The Phase 4 runbook must additionally document:

- historical source snapshot locations and retention;
- private/shared ledger backup and restore;
- rollback by `import_run_id`;
- deletion/re-import after parser corrections;
- deletion of historical rows for a Discord ID where supported;
- what provenance remains after source snapshots are deleted.

If selective deletion is unavailable, removal may require deleting a retention window or resetting the relevant telemetry/ledger store. State this limitation plainly.

## Dashboard and PR evidence

Before attaching screenshots or logs to a public issue/PR:

- redact Discord IDs;
- redact emails;
- redact Google OAuth and Cloudflare identifiers;
- redact private addresses, hostnames, source paths, and snapshot hashes tied to local inventory;
- redact tokens and credentials;
- crop prompt/response content if any appears unexpectedly;
- prefer text assertions using synthetic IDs, emails, paths, and totals.
