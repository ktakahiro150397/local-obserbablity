# Codex handoff: Phase 1

Work from this branch on the real local server and main Windows PC:

```text
feat/phase-1-codex-hermes
```

## Required reading

1. [`../AGENTS.md`](../AGENTS.md)
2. [`architecture.md`](architecture.md)
3. [`phase-1-plan.md`](phase-1-plan.md)
4. [`public-access.md`](public-access.md)
5. [`human-actions.md`](human-actions.md)
6. [`privacy.md`](privacy.md)
7. [`references.md`](references.md)
8. [`../integrations/hermes/README.md`](../integrations/hermes/README.md)

## First prompt for Codex

```text
Implement Phase 1 of this repository on the real machines.

Read AGENTS.md, docs/phase-1-plan.md, docs/public-access.md, docs/human-actions.md and docs/privacy.md completely before changing files.

This is a Codex-led, human-in-the-loop deployment. Classify work as CODEX, HUMAN or JOINT. Create an untracked notes/human-actions.local.md checklist. Complete all safe preparatory work before each human gate. When the owner must authenticate, approve a security decision, enter a secret, use a browser/app, perform a Discord test, or confirm router state, stop and give one exact HUMAN ACTION REQUIRED packet using the format in docs/human-actions.md. Never ask for secrets in chat and never claim an untested human/UI step is complete.

First inspect and record the actual server, Docker, Codex, backup-secretary, Cloudflare and Google OAuth environment in an untracked local file. Do not guess addresses, paths, ports, versions, Compose topology, Cloudflare team names, tunnel IDs, Access AUD values, Google OAuth identifiers, email addresses or credentials.

Implement a private pinned Grafana/OTel backend for all Codex and Hermes telemetry. Integrate Windows Codex CLI and desktop through the user-level Codex config, and integrate both backup-secretary Hermes instances through a pinned briancaffey/hermes-otel installation.

Also implement a physically/logically separate Hermes-only shared backend and Grafana. Publish only that shared Grafana at https://observe.yanelmo.net through a named outbound-only Cloudflare Tunnel protected by Cloudflare Access.

Configure both Google and Cloudflare One-time PIN as Access login methods. Google is the normal login path and OTP is the fallback. Use exact approved email addresses in the Access policy; do not depend on Google group membership. Verify both choices appear on the Access login page, both login paths work, and the same email through Google or OTP resolves to one Grafana user.

Configure the Google OAuth client as a Web application using the actual Cloudflare Access team domain as the JavaScript origin and https://<TEAM>.cloudflareaccess.com/cdn-cgi/access/callback as the redirect URI. Keep the Client Secret and all OAuth/account identifiers outside Git.

Use the Access-authenticated email with Grafana auth-proxy auto-provisioning. All new users must be Viewer; only the owner's Access-backed account and local break-glass account may be Admin. Do not publish OTLP or the private Grafana.

Grafana OSS data-source access is not a sufficient boundary, so personal Codex and future host telemetry must not exist in the shared datasource/backend. Mirror only the approved content-free Hermes signal set to the shared stack.

Hermes must capture Discord sender IDs for per-user accounting, while prompt/response/conversation/tool payloads and general logs remain disabled. Verify user.id=discord:<ID> and rolled-up token counts coexist on the root agent span. Keep local-obserbablity and backup-secretary changes in separate commits and PRs. Do not start Phase 2 until all Phase 1 acceptance criteria and required human gates pass or a limitation is explicitly documented.
```

## Expected human-action behavior

Codex must lead the owner through, rather than merely list, the human-only steps. The expected sequence includes:

1. Cloudflare account/domain/Zero Trust confirmation (`H1`).
2. Named-tunnel authorization or local token entry (`H2`).
3. Google Cloud OAuth project/consent/client creation and secret entry (`H3`).
4. Exact Access allow-list, Google+OTP selection, and session-duration decision (`H4`).
5. First owner login and controlled Grafana Admin promotion (`H5`).
6. Google, OTP, Viewer, and denied-user browser tests (`H6`).
7. One or two real Discord-user turns (`H7`).
8. Codex desktop restart and fresh interactive turn (`H8`).
9. Router/no-port-forward confirmation and approved firewall decisions (`H9`).
10. Explicit confirmation immediately before destructive or permission-weakening changes (`H10`).

For each gate, Codex prepares exact values and files first, tells the owner only what cannot be automated, and then verifies the result.

## Completion output expected from Codex

- summary of detected server, Windows, Docker, Cloudflare and Google OAuth environment;
- files changed in each repository;
- selected pinned versions;
- exact sanitized validation commands/results;
- proof that private and shared data boundaries are separate;
- proof that approved Access users become distinct Viewer accounts;
- proof that Google and OTP both work;
- proof that the same email through Google and OTP maps to the same Grafana account;
- proof that an unapproved identity is denied;
- proof that owner Admin and local break-glass access work;
- a table for human gates `H1`–`H10`, including owner action and Codex verification;
- remaining limitations;
- PR links for both repositories where changes are required;
- explicit confirmation that Discord IDs are collected but content payloads are not;
- explicit confirmation that Codex telemetry is absent from the shared backend and Grafana;
- explicit confirmation that no Google Client Secret, approved email or Cloudflare credential was committed.

Codex must not report “Phase 1 complete” while a required human gate is only documented, assumed, or waiting for an interactive test.