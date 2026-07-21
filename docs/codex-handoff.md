# Codex handoff: Phase 1

This document is the copy-ready handoff for real-machine implementation **after the planning scaffold has been merged into `main`**.

## Repository start state

Codex must:

1. fetch the latest remote state;
2. start from the updated `main` branch containing this document;
3. create a fresh implementation branch (default: `feat/phase-1-implementation`; use a non-conflicting suffix if necessary);
4. not implement directly on `main`;
5. not reuse the merged planning branch `feat/phase-1-codex-hermes`;
6. create a separate new branch and PR for changes in `backup-secretary`.

Issue #1 remains the implementation tracker.

## Required reading

1. [`../README.md`](../README.md)
2. [`../AGENTS.md`](../AGENTS.md)
3. [`architecture.md`](architecture.md)
4. [`phase-1-plan.md`](phase-1-plan.md)
5. [`public-access.md`](public-access.md)
6. [`human-actions.md`](human-actions.md)
7. [`privacy.md`](privacy.md)
8. [`references.md`](references.md)
9. [`../integrations/hermes/README.md`](../integrations/hermes/README.md)

## Prompt to give Codex

```text
Implement Phase 1 of this repository on the real local server and main Windows PC.

First update this checkout to the latest remote main containing the planning/handoff documents. Do not implement on main and do not reuse the merged planning branch feat/phase-1-codex-hermes. Create a fresh local-obserbablity implementation branch from updated main (default feat/phase-1-implementation, or a non-conflicting suffix). Create a separate new branch and pull request for any backup-secretary changes.

Read README.md, AGENTS.md, docs/architecture.md, docs/phase-1-plan.md, docs/public-access.md, docs/human-actions.md, docs/privacy.md, docs/references.md, and integrations/hermes/README.md completely before changing implementation files.

This is a Codex-led, human-in-the-loop deployment. Classify work as CODEX, HUMAN, or JOINT. Create untracked notes/environment.local.md and notes/human-actions.local.md files. Complete every safe preparatory action before a human gate. When account authentication, secret entry, a security decision, browser/app interaction, a Discord-user action, a desktop restart, router confirmation, or a destructive action is unavoidable, stop and provide one exact HUMAN ACTION REQUIRED packet using docs/human-actions.md. Never request a secret, approved email list, Access AUD value, private account identifier, or real Discord ID in chat or committed output. Never claim an untested account/UI step is complete.

Inspect the actual server, Docker, Codex, backup-secretary, Cloudflare, Google OAuth, Grafana, network, and router environment before choosing ports, paths, versions, endpoints, branch names, or topology. Record private findings only in ignored local notes.

Implement a pinned persistent private Grafana/OpenTelemetry domain for personal Codex and Hermes telemetry. Integrate Windows Codex CLI and desktop through the user-level Codex config. Integrate both backup-secretary Hermes instances through a reviewed pinned briancaffey/hermes-otel installation at image-build time.

Implement a separate Hermes-only shared backend and Grafana. Personal Codex and future server/Windows/OpenCode telemetry must not exist in the shared storage or shared Grafana data sources. Grafana OSS dashboard/folder permissions are not a sufficient isolation boundary.

Publish only the shared Grafana at https://observe.yanelmo.net through a named outbound-only Cloudflare Tunnel protected by Cloudflare Access. Do not publish OTLP, private Grafana, backend APIs, Docker administration, or host administration. Do not add router port forwarding.

Configure Google and Cloudflare One-time PIN as selectable Access login methods. Google is the normal path and OTP is the fallback. Allow exact approved email identities only. Do not use Everyone, bypass, shared accounts, broad email-domain rules, Google-group authorization, or instant authentication while both choices must remain visible. Verify that the same email through Google and OTP maps to one Grafana user and that different emails map to different users.

Use the Access-authenticated email with Grafana auth proxy. Auto-create regular users as Viewer. Promote the owner's Access-backed user to organization Admin only after first login. Keep a separate local break-glass server administrator. Trust the identity header only from the dedicated cloudflared/proxy boundary.

Hermes must intentionally capture Discord sender IDs for per-user accounting with capture_sender_id: true while prompt previews, responses, conversation history, tool arguments/results, and general logs remain disabled. Verify user.id=discord:<ID> and rolled-up token counts coexist on the root agent span. Mirror only the approved content-free Hermes signal set into shared storage.

Provision dashboards and scripts from Git-tracked examples without committing secrets, approved emails, real Discord IDs, private addresses, account/tunnel identifiers, or telemetry data. Validate fail-open behavior, private/shared isolation, backup/restore, Google and OTP login, user roles, unapproved-user denial, Discord accounting, Codex CLI/desktop collection, and no router exposure.

Do not start Phase 2 until every Phase 1 acceptance criterion and required human gate has passed or the remaining limitation is explicitly documented.
```

## Human gates Codex must lead

Codex must prepare exact values and verification for:

1. `H1` — Cloudflare account/domain/Zero Trust confirmation.
2. `H2` — named-tunnel authorization or local tunnel-token entry.
3. `H3` — Google Cloud OAuth project, consent screen, client, and secret entry.
4. `H4` — exact Access allow-list, Google+OTP methods, and session duration.
5. `H5` — first owner login and organization-Admin promotion.
6. `H6` — Google, OTP, Viewer, denied-user, and logout/session tests.
7. `H7` — real Discord turns from one or two users.
8. `H8` — Codex desktop full restart and fresh interactive turn.
9. `H9` — router no-port-forward and approved firewall confirmation.
10. `H10` — explicit approval immediately before destructive or permission-weakening changes.

## Expected completion output

Codex's final response and implementation PRs must include:

- detected environment summary;
- files changed in each repository;
- selected pinned versions;
- sanitized validation commands/results;
- proof of private/shared data separation;
- proof that Codex is absent from shared storage/Grafana;
- proof that approved Access users are distinct Viewer accounts;
- proof that Google and OTP both work;
- proof that the same email maps to one Grafana account across both methods;
- proof that an unapproved identity is denied;
- proof that owner organization Admin and local break-glass server admin work;
- a table for `H1`–`H10` with owner action, Codex verification, status, and remaining risk;
- PR links for `local-obserbablity` and `backup-secretary`;
- explicit confirmation that Discord IDs are collected but content payloads are not;
- explicit confirmation that no OAuth secret, tunnel credential, approved email list, real Discord ID, or private identifier was committed.

Codex must not report “Phase 1 complete” while a required human gate is only documented, assumed, or awaiting an interactive test.