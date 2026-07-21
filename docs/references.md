# Implementation references

These are the primary references reviewed while preparing Phase 1. Codex must re-check them against the installed versions and actual Cloudflare/Google/Grafana account state before implementation.

## Codex

- OpenAI Codex advanced configuration: <https://developers.openai.com/codex/config-advanced>
- OpenAI Codex configuration reference: <https://developers.openai.com/codex/config-reference>
- OpenAI Codex repository: <https://github.com/openai/codex>
- Reviewed source commit: `1836ae0612052137d0cabaff7807ff8314cee940`

Relevant conclusions:

- telemetry routing belongs in user-level Codex configuration;
- logs, metrics, and traces use separate exporters;
- OTLP/HTTP endpoints are signal-specific;
- Codex emits token-type telemetry where available;
- `originator` and `session_source` are candidate dimensions for distinguishing CLI and desktop.

Treat the installed Codex version as the source of truth for exact syntax and emitted attributes.

## Hermes

- Hermes Agent repository: <https://github.com/NousResearch/hermes-agent>
- Hermes OTel plugin: <https://github.com/briancaffey/hermes-otel>
- Reviewed plugin release: `0.11.0`
- Reviewed plugin commit: `0180c5e63b9d035ee0754d9a0d75c3499a8def26`

Relevant conclusions:

- `capture_sender_id: true` is required for Discord accounting;
- sender identity is exported as `hermes.sender.id` and `user.id=discord:<ID>`;
- the root `agent` span rolls up token usage and sender identity;
- `project_name` controls resource `service.name`;
- LGTM/generic OTLP backends support traces and metrics;
- prompt/tool previews and logs can be disabled independently;
- multi-backend fan-out exists, but a central router is preferred when it provides clearer private/shared isolation.

## Grafana and OpenTelemetry

- Grafana Docker OpenTelemetry LGTM: <https://grafana.com/docs/opentelemetry/docker-lgtm/>
- Grafana Tempo TraceQL metrics: <https://grafana.com/docs/tempo/latest/traceql/metrics-queries/>
- Grafana auth proxy: <https://grafana.com/docs/grafana/latest/setup-grafana/configure-access/configure-authentication/auth-proxy/>
- Grafana roles and permissions: <https://grafana.com/docs/grafana/latest/administration/roles-and-permissions/>
- Grafana data-source permissions API: <https://grafana.com/docs/grafana/latest/developer-resources/api-reference/http-api/api-legacy/datasource_permissions/>
- OpenTelemetry Collector: <https://opentelemetry.io/docs/collector/>

Relevant conclusions:

- `grafana/otel-lgtm` is suitable as an initial local bootstrap stack, not an excuse to ignore retention, updates, backup, or later migration;
- persistent data must be stored outside the ephemeral container layer;
- TraceQL metrics can aggregate numeric span attributes and group by `user.id` when supported by the selected Tempo configuration;
- by default, Grafana organization users can query organization data sources, while data-source permissions are an Enterprise/Cloud feature;
- shared storage/Grafana must therefore contain only Hermes telemetry approved for all viewers;
- Grafana auth proxy can create individual users from a trusted upstream email header;
- the owner Access-backed account should receive organization Admin only, while a separate local break-glass account retains server administration.

## Cloudflare Access and Tunnel

- Cloudflare Tunnel: <https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/>
- Cloudflare identity providers: <https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/>
- Cloudflare Google identity provider: <https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/google/>
- Cloudflare One-time PIN: <https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/one-time-pin/>
- Cloudflare identity FAQ: <https://developers.cloudflare.com/cloudflare-one/faq/authentication-faq/>
- Cloudflare Access policies: <https://developers.cloudflare.com/cloudflare-one/access-controls/policies/>
- Cloudflare Access authorization cookie/JWT: <https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/>
- Cloudflared tunnel configuration API (`originRequest.access`): <https://developers.cloudflare.com/api/resources/zero_trust/subresources/tunnels/subresources/cloudflared/>
- 2026 Cloudflare IdP default change: <https://developers.cloudflare.com/changelog/post/2026-06-18-cloudflare-idp-default/>

Relevant conclusions:

- Access supports multiple identity providers simultaneously;
- Google and OTP can both be enabled so users choose their method;
- ordinary Google accounts can be used without Google Workspace when the OAuth audience permits them;
- the Google OAuth client uses the Cloudflare Access team domain as origin and callback base;
- OTP is single-use and sent only to identities allowed by policy, without the public page necessarily disclosing allow/deny state;
- exact approved emails work consistently across Google and OTP;
- IdP group membership is not a reliable cross-method boundary because later OTP authentication does not retain IdP group context;
- newer Zero Trust organizations may have Cloudflare's own IdP configured by default, so implementation must explicitly select only Google and OTP for this application and disable instant authentication;
- `cloudflared` can validate the Access JWT/AUD before proxying when configured with `originRequest.access`;
- Tunnel is outbound-only and avoids router port forwarding;
- only shared Grafana is published; OTLP and private Grafana remain private.

## Google OAuth

- Google OAuth consent-screen guidance: <https://support.google.com/cloud/answer/15549945>
- Google OAuth app verification/branding guidance: <https://support.google.com/cloud/answer/13463073>

Treat Google Cloud's current console and policy notices as authoritative. The owner must make the audience and publishing decision; Codex must not invent approval status.

## Source review policy

- Prefer official documentation and source repositories.
- Pin implementations rather than floating tags.
- Record selected versions and review date in the implementation PR.
- Store account-specific values and credentials only in ignored local configuration or provider dashboards.
- When documentation and installed/account behavior differ, capture sanitized evidence and follow the observed supported behavior.
- Re-check current documentation immediately before security-sensitive account or deployment changes.