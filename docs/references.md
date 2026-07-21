# Implementation references

These are the primary references reviewed while preparing Phase 1. Codex should re-check them against the versions and account settings found on the real machines before implementation.

## Codex

- OpenAI Codex advanced configuration: <https://developers.openai.com/codex/config-advanced>
- OpenAI Codex configuration reference: <https://developers.openai.com/codex/config-reference>
- OpenAI Codex repository: <https://github.com/openai/codex>
- Reviewed source commit: `1836ae0612052137d0cabaff7807ff8314cee940`

Relevant conclusions:

- telemetry routing belongs in the user-level Codex config;
- logs, metrics and traces use separate exporters;
- OTLP/HTTP endpoints are signal-specific;
- Codex emits token-type telemetry where available;
- `originator` and `session_source` are candidate dimensions for distinguishing CLI and desktop.

Treat the installed Codex version as the source of truth for exact syntax and emitted attributes.

## Hermes

- Hermes Agent repository: <https://github.com/NousResearch/hermes-agent>
- Hermes OTel plugin: <https://github.com/briancaffey/hermes-otel>
- Reviewed plugin release: `0.11.0`
- Reviewed plugin main commit: `0180c5e63b9d035ee0754d9a0d75c3499a8def26`

Relevant conclusions:

- `capture_sender_id: true` is required for Discord user accounting;
- sender identity is exported as `hermes.sender.id` and `user.id=discord:<ID>`;
- the root `agent` span rolls up token usage and sender identity;
- `project_name` controls the resource `service.name`;
- LGTM/generic OTLP backends support traces and metrics;
- prompt/tool previews and logs can be disabled independently.

## Grafana/OpenTelemetry

- Grafana Docker OpenTelemetry LGTM: <https://grafana.com/docs/opentelemetry/docker-lgtm/>
- Grafana Tempo TraceQL metrics: <https://grafana.com/docs/tempo/latest/traceql/metrics-queries/>
- Grafana auth proxy: <https://grafana.com/docs/grafana/latest/setup-grafana/configure-access/configure-authentication/auth-proxy/>
- Grafana dashboard/folder permissions: <https://grafana.com/docs/grafana/latest/administration/user-management/manage-dashboard-permissions/>
- OpenTelemetry Collector: <https://opentelemetry.io/docs/collector/>

Relevant conclusions:

- `grafana/otel-lgtm` is suitable for initial local development/testing and packages the required signals in one container;
- `/data` must be persisted;
- `sum_over_time` can aggregate numeric span attributes and group by `user.id` when TraceQL metrics are available;
- Grafana OSS dashboard/folder permissions are not a hard data-source isolation boundary;
- the shared Grafana/backend must therefore contain only Hermes telemetry approved for all viewers;
- Grafana auth proxy can create individual users from a trusted upstream email header;
- long-term retention and a production-style split deployment should be reconsidered after actual volume is measured.

## Cloudflare Access and Tunnel

- Cloudflare Tunnel: <https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/>
- Cloudflare Access identity providers: <https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/>
- Cloudflare Google identity provider: <https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/google/>
- Cloudflare One-time PIN: <https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/one-time-pin/>
- Cloudflare identity FAQ: <https://developers.cloudflare.com/cloudflare-one/faq/authentication-faq/>
- Cloudflare Access policies: <https://developers.cloudflare.com/cloudflare-one/access-controls/policies/>

Relevant conclusions:

- Cloudflare Access supports multiple identity providers simultaneously;
- Google and One-time PIN can both be enabled so users choose their login method;
- ordinary Google accounts can be used without Google Workspace when the Google OAuth consent audience permits them;
- the Google OAuth client must use the Cloudflare Access team domain as the JavaScript origin;
- the callback URI is `https://<TEAM>.cloudflareaccess.com/cdn-cgi/access/callback`;
- the Google Client Secret must remain outside Git;
- OTP sends a single-use code only to identities allowed by Access policy;
- exact approved emails work consistently for both Google and OTP;
- IdP group membership should not be used as the Phase 1 authorization boundary because a later OTP login does not retain Google/IdP group context;
- Cloudflare Tunnel is outbound-only and avoids router port forwarding;
- only the shared Grafana hostname is published; OTLP and private Grafana remain private.

## Source review policy

- Prefer official documentation and source repositories.
- Pin implementations rather than floating tags.
- Record selected versions in the implementation PR.
- Store account-specific values and credentials only in ignored local configuration or the service dashboards.
- When documentation and installed behavior differ, capture sanitized evidence and follow the installed/account behavior.
