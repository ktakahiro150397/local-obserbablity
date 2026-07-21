# Cloudflare deployment notes

This directory contains examples and operator guidance for publishing only the shared Hermes Grafana at:

```text
https://observe.yanelmo.net
```

Read [`../docs/public-access.md`](../docs/public-access.md) and [`../docs/human-actions.md`](../docs/human-actions.md) before implementation.

## Authentication model

The `observe.yanelmo.net` Access application must offer exactly the two intended end-user methods:

- Google login;
- Cloudflare One-time PIN login.

Google is the normal path; OTP is the fallback. Users who switch methods must use the same email address if they should remain one Grafana account.

Cloudflare may automatically create or select the **Cloudflare identity provider** for newer Zero Trust organizations. For this application, inspect the Login methods tab and deselect any unintended provider. Do not leave Cloudflare IdP selected merely because it is the account default. Disable instant authentication so the Access login page visibly offers both Google and OTP.

Authorization uses exact approved email addresses. Do not use:

- `Everyone`;
- bypass policies;
- shared accounts or shared mailboxes;
- broad email-domain rules;
- Google/IdP group membership as the Phase 1 boundary;
- Cloudflare account membership as an alternate boundary;
- instant authentication while two methods must remain visible.

## Codex-led, human-in-the-loop deployment

Codex owns the engineering preparation: pinned `cloudflared` service, Compose/network configuration, secret-file templates, Grafana auth-proxy settings, health checks, verification commands, and rollback instructions.

The owner must perform or approve the account-bound actions:

- Cloudflare account/zone/Zero Trust login;
- named-tunnel authorization or local tunnel-token entry;
- Google Cloud OAuth consent/client creation and secret entry;
- exact Access allow-list, login-method selection, and session-duration decision;
- first Google and OTP logins;
- owner Grafana organization-Admin promotion after first login;
- approved/unapproved identity tests;
- router/no-port-forward confirmation.

At each gate Codex must use the `HUMAN ACTION REQUIRED` packet in `docs/human-actions.md`. The owner must never paste a token, OAuth secret, password, approved email list, Access AUD, or real Discord ID into chat.

## Google OAuth placeholders

The Google OAuth client must be a Web application with the actual Cloudflare Access team domain configured as follows:

```text
Authorized JavaScript origin:
https://<CLOUDFLARE_TEAM_NAME>.cloudflareaccess.com

Authorized redirect URI:
https://<CLOUDFLARE_TEAM_NAME>.cloudflareaccess.com/cdn-cgi/access/callback
```

The Google Cloud account owner must configure or approve:

- the project;
- OAuth consent screen;
- External audience when ordinary Google accounts must authenticate;
- OAuth Web application client;
- testing/production publishing decision;
- Client ID and Client Secret entry in Cloudflare Zero Trust.

Codex prepares the exact team-domain values after discovery. The owner enters secrets directly in Google/Cloudflare or a private local secret manager.

Do not replace placeholders with real account values in tracked files.

Never commit:

- Google OAuth Client ID or Client Secret;
- Cloudflare account/team/tunnel identifiers;
- tunnel tokens or credential files;
- approved user email addresses;
- Access application AUD values;
- real Discord IDs or mappings.

## One-time PIN behavior

- OTP is single-use and time-limited.
- A newly requested code invalidates the previous code.
- Cloudflare sends a code only when the identity is allowed, while the public UI may avoid disclosing whether an address was allowed.
- Mail security/link-scanning tools can consume a code; request a new code if necessary.
- OTP and Google must use the same email to resolve to one Grafana user.

## Tunnel boundary

Use a named outbound-only Cloudflare Tunnel. The tunnel routes only to the shared Grafana service.

It must not publish:

- private Grafana;
- OTLP receivers;
- Tempo/Mimir/Loki or other backend APIs;
- Docker administration;
- host administration;
- any unrelated local application.

Do not configure router port forwarding.

For a locally managed tunnel, copy [`cloudflared.example.yml`](cloudflared.example.yml) to an ignored local file and replace placeholders. Where supported, require `cloudflared` to validate the Access JWT/AUD before proxying.

## Grafana identity and roles

Cloudflare Access supplies the authenticated email in:

```text
Cf-Access-Authenticated-User-Email
```

Grafana auth proxy converts that email into an individual user.

- New users: Viewer.
- Owner Access-backed user: organization Admin after first login and explicit promotion.
- Local break-glass user: separate Grafana server administrator.

Do not automatically map an Access header to server administrator. Trust the identity header only from the dedicated `cloudflared`/proxy network or fixed source range.

The local login form remains available solely for break-glass access over localhost or an SSH port forward. The shared Grafana origin port must not be exposed to the general LAN or Internet unless a later reviewed design explicitly changes that boundary.

## Required verification

- Only Google and OTP are visible for the application.
- Instant authentication is disabled.
- An approved user can use Google.
- An approved user can use OTP.
- The same email through both methods maps to one Grafana account.
- Different emails create different Grafana accounts.
- An unapproved email is denied before Grafana.
- New users are Viewer.
- The owner is organization Admin but not automatically server administrator.
- Local break-glass server administration works without Cloudflare.
- Only Hermes telemetry is available in shared Grafana.
- Personal Codex/private/host data sources are absent.
- Direct requests cannot spoof the Access identity header.
- No origin or OTLP port is publicly forwarded.
- Tunnel failure affects shared dashboard access only, not telemetry collection or agents.

Each browser/account result must be exercised by a human and then verified by Codex; documentation alone does not satisfy the test.