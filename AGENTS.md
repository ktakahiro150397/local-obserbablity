# Codex implementation instructions

This repository is designed for **Codex-led implementation on the real local server and main Windows PC**. It is not a fully autonomous deployment: account authentication, secret entry, security decisions, interactive login tests, Discord-user actions, and some desktop/network actions require the repository owner.

Codex must read and follow [`docs/human-actions.md`](docs/human-actions.md). At every human gate, finish all safe preparation first, then provide an exact numbered instruction packet and wait for the owner to perform only the unavoidable human action. Never silently skip a gate or claim that an untested account/UI step works.

## Required reading

Read completely before changing files:

1. [`docs/architecture.md`](docs/architecture.md)
2. [`docs/phase-1-plan.md`](docs/phase-1-plan.md)
3. [`docs/public-access.md`](docs/public-access.md)
4. [`docs/human-actions.md`](docs/human-actions.md)
5. [`docs/privacy.md`](docs/privacy.md)
6. [`integrations/hermes/README.md`](integrations/hermes/README.md)

## Scope and order

Implement only Phase 1 first:

1. private observability backend on the local server;
2. Codex CLI and Codex desktop telemetry from the main Windows PC;
3. Hermes telemetry from `backup-secretary` using `briancaffey/hermes-otel`;
4. a physically/logically separate Hermes-only shared backend and Grafana;
5. `observe.yanelmo.net` through Cloudflare Tunnel and Cloudflare Access;
6. Grafana dashboards, individual accounts, and end-to-end verification.

Do not implement Linux host monitoring, Docker monitoring, OpenCode or Windows host monitoring until Phase 1 acceptance criteria pass.

## Human-in-the-loop protocol

Classify work as `CODEX`, `HUMAN`, or `JOINT` using `docs/human-actions.md`.

Codex must:

- create an untracked `notes/human-actions.local.md` checklist;
- complete all automatable prerequisites before asking the owner to act;
- explain why a human is required;
- give the exact dashboard path, fields, expected values, and prohibited options;
- tell the owner where to store secrets locally without echoing them;
- specify exactly what non-secret result the owner should report;
- verify the result after the owner finishes;
- provide a rollback for security-sensitive changes;
- record only sanitized evidence in Git/PRs.

Codex must not ask the owner to “configure Cloudflare,” “set up Google,” or “test Grafana” without detailed steps. It must not ask the owner to paste tunnel tokens, OAuth client secrets, passwords, approved emails, Access AUD values, or real Discord IDs into chat.

Human presence or approval is required for at least:

- Cloudflare account/domain/Zero Trust authentication;
- named-tunnel authorization or local tunnel-token entry;
- Google Cloud OAuth consent/client creation and secret entry;
- exact Access allow-list and session-duration decision;
- first Google and OTP logins;
- initial owner Grafana-account creation and Admin promotion;
- approved/unapproved identity tests;
- real Discord turns from one or more people;
- full Codex desktop restart and interactive desktop turn when needed;
- router port-forwarding confirmation and security-sensitive firewall decisions;
- destructive actions or permission weakening.

## First actions on the real machines

Before editing implementation files, inspect and record:

- local-server OS, CPU architecture, Docker Engine and Docker Compose versions;
- available disk space and intended private/shared telemetry-data directories;
- listening ports, especially 3000, 4317 and 4318;
- server LAN address and firewall configuration;
- the installed Codex version and effective `CODEX_HOME` on Windows;
- whether Codex CLI and desktop use the same user-level config;
- the current `backup-secretary` branch, Compose topology, Dockerfile and Hermes data mounts;
- the exact installed Hermes Agent version and plugin support;
- reachability from Windows to the private collector and from Hermes containers to both approved destinations;
- Cloudflare zone/account/team and tunnel-management mode, with the owner performing authentication;
- whether Google OAuth and OTP identity providers already exist;
- the current router exposure state as confirmed by the owner.

Write machine-specific findings to an untracked local file such as `notes/environment.local.md`. Do not commit private IPs, usernames, email addresses, Discord IDs, account identifiers or secrets.

## Repository and branch handling

- Work on `feat/phase-1-codex-hermes`.
- Keep `local-obserbablity` and `backup-secretary` changes in separate commits and pull requests.
- Never force-push or rewrite the user's existing history.
- Keep generated telemetry and runtime data outside Git.
- Pin external images and `hermes-otel`; do not leave deployment files on an unpinned `latest` or floating `main`.

Initial `hermes-otel` review baseline:

- release: `0.11.0`;
- reviewed main commit: `0180c5e63b9d035ee0754d9a0d75c3499a8def26`.

Re-check for security or compatibility fixes before pinning. If changing the baseline, document the selected version and why.

## Phase 1 implementation requirements

### Private backend

- Bootstrap with a pinned `grafana/otel-lgtm` or an evidence-backed equivalent.
- Persist all data required for private Codex and Hermes telemetry.
- Add health checks and documented backup/restore procedures.
- Expose private Grafana only to the owner/trusted LAN or documented SSH forwarding.
- Expose OTLP only as required for trusted Windows/Hermes clients.
- Restrict access with the host firewall; do not expose private Grafana or OTLP through Cloudflare or router forwarding.
- Put host-specific values in `.env`; commit only examples.
- Make `docker compose config` succeed without real secrets.

### Codex

- Modify the user-level `%USERPROFILE%\.codex\config.toml`, not a project-level config.
- Back up the existing file before changing it.
- Merge idempotently; do not replace unrelated Codex settings.
- Use separate signal endpoints:
  - metrics: `/v1/metrics`;
  - traces: `/v1/traces`;
  - logs: disabled in Phase 1 unless explicitly needed for local debugging.
- Keep `log_user_prompt = false`.
- Send Codex only to the private backend; it must never be mirrored to the shared backend.
- Confirm both Codex CLI and Codex desktop emit data and can be distinguished by actual emitted attributes such as `originator` or `session_source`.
- Validate `codex.turn.token_usage` and actual token-type values where emitted.

### Hermes / backup-secretary

Use `briancaffey/hermes-otel`; do not write a new telemetry plugin unless a confirmed compatibility defect blocks it.

Required privacy settings:

```yaml
capture_previews: false
capture_conversation_history: false
capture_sender_id: true
capture_logs: false
```

Requirements:

- install the plugin and OTel dependencies in the Hermes image, not by mutating a running container manually;
- keep Hermes functional when either observability destination is down;
- identify each Hermes instance with a stable `service.name` and `service.instance.id`;
- ensure Discord gateway turns carry `hermes.sender.id` and `user.id=discord:<sender_id>`;
- never commit real sender IDs or an ID-to-name mapping;
- verify root `agent` spans contain both `user.id` and rolled-up token attributes;
- keep main and `owashota` distinguishable;
- send Hermes to the private backend and mirror only the approved content-free Hermes signal set to the shared Hermes-only backend.

The preferred cross-Compose connection is a named Docker network shared with `backup-secretary`. Windows sends OTLP to the private server LAN endpoint. If real-host evidence requires another route, document its security and firewall implications.

### Shared Hermes-only backend and Grafana

- Use a separate backend/tenant containing only telemetry approved for all authorized Discord users.
- Do not rely on Grafana OSS dashboard/folder permissions as the data-isolation boundary.
- The shared Grafana must not have a data source that can query personal Codex or future host telemetry.
- Default auto-created Access-backed users to `Viewer`.
- Keep the owner's Access-backed account and a local break-glass account as the only administrators unless explicitly changed.
- Provision dashboards from files where possible.
- Do not enable anonymous access.

### Cloudflare and Google authentication

Publish only the shared Grafana at:

```text
https://observe.yanelmo.net
```

Requirements:

- use a named outbound-only Cloudflare Tunnel;
- do not open router ports for Grafana or OTLP;
- create a Cloudflare Access self-hosted application for exactly the shared hostname;
- enable both Google and Cloudflare One-time PIN as selectable login methods;
- authorize exact approved email addresses only;
- do not use `Everyone`, bypass, shared-account, broad-domain, or Google-group rules in Phase 1;
- use the same email through Google and OTP when one person should map to one Grafana user;
- trust the Access identity header only from the dedicated tunnel/proxy boundary;
- keep Google OAuth secrets, tunnel credentials, approved emails, account/team identifiers and Access AUD values outside Git.

The owner must perform the account authentication, OAuth consent/client creation, secret entry, allow-list decision, and browser login tests. Codex must prepare exact values and verify outcomes as described in `docs/human-actions.md`.

### Dashboards

Provision dashboards from files, not only through interactive edits.

Private minimum dashboards:

1. **AI overview** — token totals and request volume by source/model.
2. **Codex** — token type, model, CLI vs desktop, API duration and tools.
3. **Hermes** — instance, model/provider, token type, API duration and tools.

Shared minimum dashboard:

4. **Hermes users** — total/input/output/cache/reasoning tokens grouped by `user.id`, with instance and time filters.

Hermes per-user token totals may be computed from Tempo with TraceQL metrics against root `agent` spans. Avoid modifying `hermes-otel` merely to add high-cardinality user labels to every metric.

## Privacy and security

- No raw prompts, assistant responses, conversation history, tool arguments, tool results or general application logs in Phase 1.
- Discord sender IDs are intentionally collected in private and authorized shared Hermes telemetry; they are personal data.
- Do not include real IDs, emails or private infrastructure in public screenshots or verification evidence.
- Set non-default Grafana administrator passwords through local secrets.
- Do not publish private Grafana, OTLP, backend APIs, Docker administration, or host administration through Cloudflare.
- Only the shared Grafana may be routed by the tunnel.
- Keep a documented local break-glass path independent of Cloudflare.

## Required verification evidence

Record commands and sanitized results in the pull request:

- `docker compose config` for private/shared stacks;
- container health/status;
- persistent storage survives container recreation;
- Windows can reach private OTLP and the owner can reach private Grafana;
- one fresh Codex CLI turn appears privately;
- one fresh Codex desktop turn appears privately and is distinguishable;
- one fresh Discord turn appears with sender ID and token totals;
- a second Discord user produces a distinct `user.id` series when safely testable;
- shared Grafana contains Hermes data but no Codex/private datasource;
- Google and OTP are both offered by Access;
- the same email through both methods maps to one Grafana user;
- approved users are Viewer and an unapproved identity is denied;
- the owner is Admin and local break-glass access works;
- direct origin/header-spoofing attempts are blocked;
- no router port forwarding exists, as confirmed by the owner;
- stopping either observability stack or the tunnel does not stop Codex or Hermes;
- restart restores collection without manual container mutation.

## Deliverables

Expected Phase 1 files include:

```text
compose.yaml
.env.example
Makefile or scripts/
grafana/private/
grafana/shared/
cloudflare/
clients/codex/
integrations/hermes/
docs/human-actions.md
docs/runbook.md
docs/verification.md
```

Adjust the exact layout when implementation evidence justifies it, but keep client setup, private/shared backend configuration, public access, human gates and cross-repository integration clearly separated.

## Completion report

Codex's final Phase 1 report must include:

- environment summary;
- files and PRs changed in each repository;
- selected pinned versions;
- sanitized validation results;
- proof of the private/shared data boundary;
- remaining limitations;
- a human-gate table listing every `H1`–`H10` gate as completed, not applicable, or explicitly deferred;
- explicit confirmation that Discord IDs are collected but content payloads are not;
- explicit confirmation that personal Codex telemetry is absent from the shared backend/Grafana.

Do not describe Phase 1 as complete while a required human gate is untested or merely assumed.