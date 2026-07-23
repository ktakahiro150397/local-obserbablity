# Codex implementation instructions

This repository is designed for **Codex-led implementation on the real local server and main Windows PC**. It is not a fully autonomous deployment: account authentication, secret entry, security decisions, interactive login tests, Discord-user actions, and some desktop/network actions require the repository owner.

Codex must read and follow [`docs/human-actions.md`](docs/human-actions.md). At every human gate, finish all safe preparation first, then provide one exact numbered `HUMAN ACTION REQUIRED` packet and wait for the owner to perform only the unavoidable human action. Never silently skip a gate or claim that an untested account/UI step works.

## Start from the current merged state

Before implementation:

1. verify this checkout is based on the latest remote `main`;
2. do not implement directly on `main`;
3. create a fresh Phase 2 implementation branch from updated `main` (default:
   `feat/phase-2-implementation`; use a non-conflicting suffix if necessary);
4. after Phase 2 is merged, create a separate fresh Phase 3 branch (default:
   `feat/phase-3-implementation`);
5. do not continue on a Phase 1, Phase 4, dashboard, or readiness branch;
6. create a separate new branch and pull request for all `backup-secretary` changes.

Phase 1 and the authorized Codex/Hermes Phase 4 scope are complete. Issue #1 is
historical; Phase 2 and Phase 3 use separate implementation trackers.

## Required reading

Read completely before changing implementation files:

1. [`README.md`](README.md)
2. [`docs/architecture.md`](docs/architecture.md)
3. [`docs/phase-2-plan.md`](docs/phase-2-plan.md)
4. [`docs/phase-3-plan.md`](docs/phase-3-plan.md)
5. [`docs/human-actions.md`](docs/human-actions.md)
6. [`docs/privacy.md`](docs/privacy.md)
7. [`docs/runbook.md`](docs/runbook.md)
8. [`docs/verification.md`](docs/verification.md)
9. [`docs/references.md`](docs/references.md)
10. [`docs/phase-4-backfill.md`](docs/phase-4-backfill.md) only when preparing
    the optional OpenCode historical extension

## Scope and order

Implement in this order:

1. Phase 2 private Linux host and Docker monitoring;
2. Phase 2 baseline, dashboards, fail-open, and private/shared-isolation checks;
3. merge and accept Phase 2;
4. Phase 3 private Windows host monitoring;
5. Phase 3 synthetic OpenCode privacy spike and, only if it passes, live
   OpenCode telemetry;
6. optionally prepare OpenCode historical import under a separate explicit
   owner authorization.

Preserve the deployed Phase 1/4 services, persisted data, secret files, shared
access, live Hermes rollup, and accepted H6 limitation. Do not reopen or rewrite
completed Codex/Hermes history. OpenCode history is a Phase 3 extension because
it was outside the completed authorized import.

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
- granting a collector access to the Docker API;
- installing or changing a Windows service;
- a full OpenCode restart and synthetic interactive turn;
- an OpenCode historical snapshot or import;
- alert destination and threshold decisions.

## First actions on the real machines

Before editing implementation files, inspect and record the relevant current
state. Reuse committed sanitized evidence, but verify that it has not changed:

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
- Linux cgroup mode, memory/swap pressure, collector memory, and existing port
  ownership;
- whether host metrics, Docker metrics, or Docker daemon metrics already exist;
- the minimum host mounts required by the selected hostmetrics receiver;
- the exact Docker API access proposed for the Docker receiver;
- installed OpenCode version, OTel behavior, and SQLite schema metadata without
  reading content or credentials;
- installed Windows monitoring services, candidate listeners, and service
  account constraints.

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

## Completed Phase 1 invariants

The following deployed requirements remain hard compatibility and security
constraints for Phase 2 and Phase 3.

### Private backend

- Use a pinned `grafana/otel-lgtm` stack or an evidence-backed equivalent.
- Persist all private data.
- Add health checks and backup/restore procedures.
- Expose private Grafana only to the owner over trusted LAN, localhost,
  documented SSH forwarding, or the dedicated owner-only Cloudflare Access
  route at `https://private-observe.yanelmo.net`.
- Expose OTLP only to trusted Windows and Docker clients.
- Do not route OTLP or backend APIs through Cloudflare or router forwarding.
- The private Grafana Cloudflare route is the only exception: use a second
  named tunnel and connector attached only to the private admin network. Never
  attach the shared connector to the private network or the private connector
  to shared storage.
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

Publish only the two reviewed Grafana web applications:

```text
https://observe.yanelmo.net
https://private-observe.yanelmo.net
```

Requirements:

- use separate named outbound-only Cloudflare Tunnels for shared and private
  Grafana;
- do not open router ports for Grafana or OTLP;
- create separate Access self-hosted applications for the two exact hostnames;
- keep the shared application on the existing exact approved-user list and make
  the private application exact-owner-only;
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

## Phase 2 requirements

- Follow [`docs/phase-2-plan.md`](docs/phase-2-plan.md).
- Use a separately pinned, private-only infrastructure collector.
- Mount only the read-only host filesystems required by `hostmetrics`; do not
  use privileged mode, host PID, or host network without reproduced need and
  owner approval.
- Do not use TCP 9100; it is occupied by an unrelated service.
- Treat Docker API access as security-sensitive. A read-only socket mount does
  not restrict Docker API methods.
- Prefer a restricted socket proxy or an equivalently reviewed isolated
  boundary. Never expose the Docker API on the LAN or Internet.
- Build dashboards from actual received metrics and measure resource/cardinality
  impact before enabling alerts.
- Send host and container telemetry only to private storage.
- Prove monitoring failure does not affect applications and shared queries
  return zero host/container results.

## Phase 3 requirements

- Follow [`docs/phase-3-plan.md`](docs/phase-3-plan.md).
- Use a pinned, checksummed Windows collector and prefer outbound-only OTLP.
- Do not collect Windows event logs, command lines, clipboard data, usernames,
  process arguments, or general logs.
- Run the synthetic OpenCode privacy spike before production live collection.
- Reject OpenCode logs and allowlist attributes from actual content-free test
  evidence.
- Never export prompts, responses, tool payloads, paths, project names, account
  values, credentials, or arbitrary persisted JSON.
- Keep OpenCode and Windows telemetry private and prove the shared domain
  returns zero results.
- Historical OpenCode work requires separate authorization and may read only
  explicit aggregate columns from a consistent snapshot. Schema inspection is
  not import authorization.

## Privacy and security

Do not export raw prompts, responses, conversation history, tool arguments,
tool results, credentials, private paths, or general application logs in any
phase.

Discord sender IDs are intentionally present in private and authorized shared Hermes telemetry. Access-backed Grafana emails are used for authentication/authorization but must not be added to Hermes telemetry.

Only the two reviewed Grafana web UIs may be routed through Cloudflare. The
private route must use its dedicated owner-only tunnel and Access application.
Keep a documented private Grafana break-glass path independent of Cloudflare.

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

## Completion reports

Each Phase 2/3 report must include:

- environment summary;
- files and PRs changed;
- pinned versions;
- sanitized validation results;
- proof of private/shared isolation;
- remaining limitations;
- a phase-specific human-gate table showing owner action and Codex verification;
- fail-open and rollback evidence;
- confirmation that Phase 2/3 telemetry is absent from shared storage/Grafana;
- measured resource/cardinality impact;
- explicit confirmation that content and credential payloads were not
  collected.

The accepted Phase 1 H6 limitation must remain described accurately. Do not
retroactively claim that its deferred second-identity or denied-identity
interactive tests passed.
