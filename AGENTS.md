# Codex implementation instructions

This repository is designed for **Codex-led implementation on the real local server and main Windows PC**. It is not a fully autonomous deployment: account authentication, secret entry, security decisions, interactive login tests, Discord-user actions, and some desktop/network actions require the repository owner.

Codex must read and follow [`docs/human-actions.md`](docs/human-actions.md). At every human gate, finish all safe preparation first, then provide one exact numbered `HUMAN ACTION REQUIRED` packet and wait for the owner to perform only the unavoidable human action. Never silently skip a gate or claim that an untested account/UI step works.

## Start from the merged planning state

Before implementation:

1. verify this checkout is based on the latest remote `main` containing the Phase 1 planning documents;
2. do not implement directly on `main`;
3. create a fresh implementation branch from updated `main` (default: `feat/phase-1-implementation`; use a non-conflicting suffix if it already exists);
4. do not continue on the merged planning branch `feat/phase-1-codex-hermes`;
5. create a separate new branch and pull request for all `backup-secretary` changes.

Issue #1 remains the implementation tracker. The planning PR does not complete or close it.

## Required reading

Read completely before changing implementation files:

1. [`README.md`](README.md)
2. [`docs/architecture.md`](docs/architecture.md)
3. [`docs/phase-1-plan.md`](docs/phase-1-plan.md)
4. [`docs/public-access.md`](docs/public-access.md)
5. [`docs/human-actions.md`](docs/human-actions.md)
6. [`docs/privacy.md`](docs/privacy.md)
7. [`docs/references.md`](docs/references.md)
8. [`integrations/hermes/README.md`](integrations/hermes/README.md)

## Scope and order

Implement only Phase 1 first:

1. private observability backend on the local server;
2. Codex CLI and Codex desktop telemetry from the main Windows PC;
3. Hermes telemetry from `backup-secretary` using a pinned `briancaffey/hermes-otel`;
4. a physically or logically separate Hermes-only shared backend and Grafana;
5. `observe.yanelmo.net` through Cloudflare Tunnel and Cloudflare Access;
6. Google and email OTP login, account roles, dashboards, and end-to-end verification.

Do not implement Linux/Docker host monitoring, OpenCode, or Windows host monitoring until Phase 1 acceptance criteria pass or a limitation is explicitly documented.

Phase 4 historical backfill is a separate roadmap item described in [`docs/phase-4-backfill.md`](docs/phase-4-backfill.md). It is not part of Issue #1. During Phase 1, do not scan historical Codex/Hermes/OpenCode content, create a backfill ledger, or import old usage. Live collection and per-instance cutovers must be established first; Phase 4 production work begins after Phase 3 unless the owner explicitly authorizes an earlier read-only inventory.

## Human-in-the-loop protocol

Classify work as `CODEX`, `HUMAN`, or `JOINT` using `docs/human-actions.md`.

Codex must:

- create and maintain untracked `notes/environment.local.md` and `notes/human-actions.local.md` files;
- complete every safe prerequisite before asking the owner to act;
- explain why a human is required;
- give the exact dashboard/UI path, values, expected result, and prohibited options;
- tell the owner where a secret must be entered or stored locally without echoing it;
- specify exactly which non-secret result the owner should return;
- verify the result after the owner finishes;
- provide a rollback for security-sensitive changes;
- record only sanitized evidence in Git and pull requests.

Codex must not ask the owner to “configure Cloudflare,” “set up Google,” or “test Grafana” without detailed steps. It must not request tunnel tokens, OAuth client secrets, passwords, approved email lists, Access AUD values, or real Discord IDs in chat, issues, PRs, or recorded command output.

Human presence or approval is required for at least:

- Cloudflare account/domain/Zero Trust authentication;
- named-tunnel authorization or local tunnel-token entry;
- Google Cloud OAuth consent/client creation and secret entry;
- exact Access allow-list and session-duration decisions;
- first Google and OTP logins;
- initial owner Grafana account creation and organization-Admin promotion;
- approved/unapproved identity tests;
- real Discord turns from one or more people;
- full Codex desktop restart and an interactive desktop turn when needed;
- router port-forwarding confirmation and security-sensitive firewall decisions;
- destructive actions or permission weakening.

## First actions on the real machines

Before editing implementation files, inspect and record:

- local-server OS, CPU architecture, Docker Engine, and Docker Compose versions;
- available disk space and intended private/shared telemetry-data directories;
- listening ports and existing service bindings;
- server LAN address and firewall configuration;
- installed Codex version and effective `CODEX_HOME` on Windows;
- whether Codex CLI and desktop use the same user-level configuration;
- current `backup-secretary` branch, Compose topology, Dockerfile, Hermes versions, plugin support, and data mounts;
- reachability from Windows to private OTLP and from Hermes containers to approved collector endpoints;
- Cloudflare zone/account/team and tunnel-management mode, with owner authentication;
- whether Google and OTP identity providers already exist;
- current router exposure state as confirmed by the owner.

Do not commit private addresses, hostnames, usernames, emails, Discord IDs, account identifiers, or secrets.

## Repository and branch handling

- Keep `local-obserbablity` and `backup-secretary` changes in separate branches, commits, and PRs.
- Never force-push or rewrite existing history.
- Keep generated telemetry, historical source snapshots, database dumps, manifests containing private paths, and runtime state outside Git.
- Pin external images and `hermes-otel`; do not leave deployment files on floating `latest` or `main` references.
- Re-check upstream security/compatibility fixes before selecting versions and document the selection.

Initial `hermes-otel` review baseline:

- release: `0.11.0`;
- reviewed commit: `0180c5e63b9d035ee0754d9a0d75c3499a8def26`.

## Phase 1 requirements

### Private backend

- Use a pinned `grafana/otel-lgtm` stack or an evidence-backed equivalent.
- Persist all private data.
- Add health checks and backup/restore procedures.
- Expose private Grafana only to the owner over trusted LAN, localhost, or documented SSH forwarding.
- Expose OTLP only to trusted Windows and Docker clients.
- Do not route private Grafana, OTLP, or backend APIs through Cloudflare or router forwarding.
- Put machine-specific values and secrets in ignored local configuration.

### Codex

- Modify `%USERPROFILE%\.codex\config.toml`, not project-local `.codex/config.toml`.
- Back up and merge the existing file idempotently; preserve unrelated settings.
- Enable OTLP/HTTP metrics and traces with signal-specific endpoints.
- Disable structured OTel log export for Phase 1 and keep `log_user_prompt = false`.
- Send Codex only to private storage.
- Verify CLI and desktop both emit data and identify the actual attributes that distinguish them.
- Build dashboards from actual received names; do not assume backend-normalized metric names.

### Hermes and `backup-secretary`

Use `briancaffey/hermes-otel`; do not write a replacement unless a reproduced incompatibility blocks it.

Required privacy settings:

```yaml
capture_previews: false
capture_conversation_history: false
capture_sender_id: true
capture_logs: false
```

Requirements:

- install the pinned plugin and OTel dependencies at image-build time;
- do not mutate running containers as the installation method;
- keep Hermes working when collectors/backends are down;
- identify `main` and `owashota` with stable instance attributes;
- verify Discord turns contain `hermes.sender.id` and `user.id=discord:<sender_id>`;
- verify root `agent` spans contain the same user ID and rolled-up token attributes;
- send Hermes to private storage and mirror only the approved content-free Hermes signal set to shared storage;
- never commit real sender IDs or ID-to-name mappings.

### Shared Hermes-only backend and Grafana

- Use separate storage or a proven isolated tenant that contains only Hermes telemetry approved for all viewers.
- Do not treat Grafana OSS folder/dashboard permissions as the hard data boundary.
- Shared Grafana must have no data source capable of querying personal Codex or future host telemetry.
- Default Access-backed users to Viewer.
- Promote the owner's Access-backed user to **organization Admin**, not server administrator, after first login.
- Keep a separate local break-glass **server administrator** independent of Cloudflare.
- Disable anonymous access and provision dashboards from files where possible.

### Cloudflare and Google authentication

Publish only:

```text
https://observe.yanelmo.net
```

Requirements:

- use a named outbound-only Cloudflare Tunnel;
- do not open router ports for Grafana or OTLP;
- create an Access self-hosted application for exactly the shared hostname;
- enable both Google and Cloudflare One-time PIN as selectable login methods;
- do not enable instant authentication while both choices must be visible;
- authorize exact approved email identities only;
- do not use `Everyone`, bypass, shared-account, broad-domain, or Google-group authorization in Phase 1;
- use the same email through Google and OTP when one person should map to one Grafana account;
- configure Grafana auth proxy from the Access-authenticated email;
- trust identity headers only from the dedicated tunnel/proxy boundary;
- keep OAuth secrets, tunnel credentials, approved emails, account/team identifiers, and Access AUD values outside Git.

### Dashboards

Private minimum dashboards:

1. **AI overview** — tokens and requests by source/model.
2. **Codex** — token type, model, CLI vs desktop, duration, and tools.
3. **Hermes** — instance, model/provider, token type, duration, errors, and tools.

Shared minimum dashboard:

4. **Hermes users** — total/input/output/cache/reasoning tokens grouped by `user.id`, with instance and time filters.

Use only attributes confirmed on real spans. Avoid adding Discord IDs as labels to every Prometheus metric solely for dashboard convenience.

## Privacy and security

Do not export raw prompts, responses, conversation history, tool arguments, tool results, or general application logs in Phase 1.

Discord sender IDs are intentionally present in private and authorized shared Hermes telemetry. Access-backed Grafana emails are used for authentication/authorization but must not be added to Hermes telemetry.

Only shared Grafana may be routed through Cloudflare. Keep a documented break-glass path independent of Cloudflare.

## Required verification

Record sanitized evidence for:

- configuration validation and container health;
- storage persistence and backup/restore;
- Codex CLI and desktop turns in private storage;
- distinction between CLI and desktop;
- one or two Discord turns with per-user accounting;
- absence of content payloads;
- private/shared data separation and absence of Codex in shared storage;
- Google and OTP login choices and successful tests;
- same-email identity convergence and different-email separation;
- Viewer defaults, owner organization Admin, and break-glass server admin;
- unapproved identity denial;
- direct-origin/header-spoofing protection;
- no router port forwarding;
- fail-open behavior when stacks or tunnel are stopped.

## Deliverables

Expected implementation additions include:

```text
compose.yaml
.env.example
scripts/
grafana/private/
grafana/shared/
cloudflare/
clients/codex/
integrations/hermes/
docs/runbook.md
docs/verification.md
```

Adjust layout only when real evidence justifies it, while preserving private/shared isolation and cross-repository separation.

## Completion report

The final Phase 1 report must include:

- environment summary;
- files and PRs changed in each repository;
- pinned versions;
- sanitized validation results;
- proof of private/shared isolation;
- remaining limitations;
- a human-gate table for `H1`–`H10` showing owner action and Codex verification;
- confirmation that Discord IDs are collected but content payloads are not;
- confirmation that personal Codex telemetry is absent from shared storage/Grafana.

Do not describe Phase 1 as complete while a required human gate is untested, assumed, or merely documented.
