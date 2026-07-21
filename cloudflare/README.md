# Cloudflare deployment notes

This directory contains examples and instructions for publishing only the shared Hermes Grafana at:

```text
https://observe.yanelmo.net
```

Read both of these before implementing:

- [`../docs/public-access.md`](../docs/public-access.md)
- [`../docs/human-actions.md`](../docs/human-actions.md)

## Codex-led, human-in-the-loop deployment

Codex owns the engineering preparation: pinned `cloudflared` service, Compose/network configuration, secret-file templates, Grafana auth-proxy settings, health checks, verification commands, and rollback instructions.

The owner must perform or approve the account-bound actions:

- Cloudflare account/zone/Zero Trust login;
- named-tunnel authorization or entry of a dashboard-managed tunnel token into an ignored local secret;
- Google Cloud OAuth consent/client creation and entry of the Client ID/Secret into Cloudflare;
- exact Access allow-list and session-duration decision;
- first Google and OTP logins;
- owner Grafana Admin promotion after the Access-backed account exists;
- approved/unapproved identity tests;
- router/no-port-forward confirmation.

Codex must not merely say “configure Cloudflare.” At each gate it must use the `HUMAN ACTION REQUIRED` packet defined in `docs/human-actions.md`, including exact UI path or invariant, values, local secret destination, verification, and rollback. The owner must never paste a token, OAuth secret, password, approved email list, Access AUD, or real Discord ID into chat.

## Authentication model

Cloudflare Access must offer both:

- Google login;
- One-time PIN login.

The Access application authorizes exact approved email addresses. It must not use `Everyone`, bypass policies, shared accounts, broad email-domain rules, or Google group membership as the Phase 1 authorization boundary.

Google is the normal path; OTP is the fallback. Users who switch between the two must use the same email address if they should remain one Grafana account.

## Google OAuth placeholders

The Google OAuth client must be a Web application with:

```text
Authorized JavaScript origin:
https://<CLOUDFLARE_TEAM_NAME>.cloudflareaccess.com

Authorized redirect URI:
https://<CLOUDFLARE_TEAM_NAME>.cloudflareaccess.com/cdn-cgi/access/callback
```

Do not replace these placeholders in tracked files. Codex discovers the real team name after the owner authenticates and records it only in ignored local documentation or service configuration.

Never commit:

- Google OAuth Client ID or Client Secret;
- Cloudflare account/team/tunnel identifiers;
- tunnel tokens or credential files;
- approved user email addresses;
- Access application AUD values.

## Tunnel boundary

The named tunnel routes only to the shared Grafana service. It must not publish:

- private Grafana;
- OTLP receivers;
- Tempo/Mimir/Loki APIs;
- Docker or host administration interfaces.

Use an outbound-only tunnel and do not configure router port forwarding.

## Grafana identity

Cloudflare Access supplies the authenticated email in:

```text
Cf-Access-Authenticated-User-Email
```

Grafana auth proxy converts that email into an individual account. New users are Viewer by default. The owner is promoted separately, and a local break-glass administrator remains available without Cloudflare.

## Required verification

- Google and OTP are both visible on the Access login page.
- An approved user can use each login method.
- The same email through both methods maps to one Grafana account.
- An unapproved email is denied before Grafana.
- New users are Viewer.
- The owner is Admin.
- Local break-glass administration works.
- Only Hermes telemetry is available in the shared Grafana.
- Direct requests cannot spoof the Access identity header.
- No router port forwarding exists.

Each browser/account result must be exercised by a human and then verified by Codex; documentation alone does not satisfy the test.