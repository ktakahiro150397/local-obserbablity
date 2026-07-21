# Codex implementation instructions

This repository is designed to be implemented by Codex while running on the real local server and main Windows PC.

## Scope and order

Implement only Phase 1 first:

1. observability backend on the local server;
2. Codex CLI and Codex desktop telemetry from the main Windows PC;
3. Hermes telemetry from `backup-secretary` using `briancaffey/hermes-otel`;
4. Grafana dashboards and end-to-end verification.

Do not implement Linux host monitoring, Docker monitoring, OpenCode or Windows host monitoring until Phase 1 acceptance criteria pass.

## First actions on the real machines

Before editing files, inspect and record:

- local-server OS, CPU architecture, Docker Engine and Docker Compose versions;
- available disk space and the intended persistent telemetry-data directory;
- listening ports, especially 3000, 4317 and 4318;
- server LAN address and firewall configuration;
- the installed Codex version and the effective `CODEX_HOME` on Windows;
- whether Codex CLI and the desktop app use the same user-level config;
- the current `backup-secretary` branch, Compose topology, Dockerfile and Hermes data mounts;
- the exact installed Hermes Agent version and plugin support;
- reachability from Windows to the server and from Hermes containers to the collector.

Write machine-specific findings to an untracked local file such as `notes/environment.local.md`. Do not commit private IPs, usernames, Discord IDs or secrets.

## Repository and branch handling

- Work on `feat/phase-1-codex-hermes`.
- Keep `local-obserbablity` and `backup-secretary` changes in separate commits and pull requests.
- Never force-push or rewrite the user's existing history.
- Keep generated telemetry and runtime data outside Git.
- Pin external images and `hermes-otel`; do not leave production files on an unpinned `latest` or floating `main`.

Initial `hermes-otel` review baseline:

- release: `0.11.0`;
- reviewed main commit: `0180c5e63b9d035ee0754d9a0d75c3499a8def26`.

Re-check for security or compatibility fixes before pinning. If changing the baseline, document the selected version and why.

## Phase 1 implementation requirements

### Local backend

- Bootstrap with `grafana/otel-lgtm` unless real-host constraints require a split stack.
- Persist `/data`.
- Add a health check and documented backup/restore procedure.
- Expose Grafana and OTLP only as required for LAN clients.
- Restrict access with the host firewall; do not expose the stack to the public Internet.
- Put host-specific values in `.env`; commit only `.env.example`.
- Make `docker compose config` succeed without secrets.

### Codex

- Modify the user-level `%USERPROFILE%\.codex\config.toml`, not a project-level config.
- Back up the existing file before changing it.
- Merge idempotently; do not replace unrelated Codex settings.
- Use separate signal endpoints:
  - metrics: `/v1/metrics`;
  - traces: `/v1/traces`;
  - logs: disabled in Phase 1 unless explicitly needed for debugging.
- Keep `log_user_prompt = false`.
- Confirm both Codex CLI and Codex desktop emit data and can be distinguished by `originator` and/or `session_source`.
- Validate `codex.turn.token_usage` with token types `total`, `input`, `cached_input`, `output` and `reasoning_output` where emitted.

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

- install the plugin and its OTel dependencies in the Hermes image, not by mutating a running container manually;
- keep Hermes functional when the collector is down;
- identify each Hermes instance with a stable `service.name` and `service.instance.id`;
- ensure Discord gateway turns carry `hermes.sender.id` and `user.id=discord:<sender_id>`;
- never commit real sender IDs or an ID-to-name mapping;
- verify root `agent` spans contain both `user.id` and rolled-up token attributes;
- keep separate data for the main and `owashota` Hermes instances.

The preferred cross-Compose connection is a named Docker network shared with `backup-secretary`. Windows sends OTLP to the server's LAN endpoint. If a shared Docker network is unsuitable on the real host, document the alternative and its firewall implications.

### Dashboards

Provision dashboards from files, not only by editing Grafana interactively.

Minimum dashboards:

1. **AI overview** — token totals and request volume by source/model.
2. **Codex** — token type, model, CLI vs desktop, API duration and tools.
3. **Hermes** — instance, model/provider, token type, API duration and tools.
4. **Hermes users** — total/input/output/cache/reasoning tokens grouped by `user.id`.

For Phase 1, Hermes per-user token totals may be computed directly from Tempo with TraceQL metrics against root `agent` spans. Avoid modifying `hermes-otel` merely to add high-cardinality user labels to every metric.

## Privacy and security

- No raw prompts, assistant responses, tool arguments, tool results or conversation history in Phase 1.
- Discord sender IDs are intentionally collected but must remain inside the local backend.
- Do not include real IDs in screenshots attached to a public issue or pull request.
- Set a non-default Grafana admin password through local secrets.
- Do not publish 3000, 4317 or 4318 through a router, tunnel or public reverse proxy.

## Required verification evidence

Record commands and sanitized results in the pull request:

- `docker compose config`;
- container health/status;
- persistent storage survives container recreation;
- Windows can reach OTLP and Grafana;
- one fresh Codex CLI turn appears;
- one fresh Codex desktop turn appears;
- one fresh Discord turn appears with a sender ID and token totals;
- a second Discord user produces a distinct `user.id` series, when safely testable;
- stopping the observability stack does not stop or break Hermes;
- restart restores collection without manual container mutation.

## Deliverables

Expected Phase 1 files include:

```text
compose.yaml
.env.example
Makefile or scripts/
grafana/provisioning/
grafana/dashboards/
clients/codex/
integrations/hermes/
docs/runbook.md
docs/verification.md
```

Adjust the exact layout when implementation evidence justifies it, but keep client setup, backend configuration and cross-repository integration clearly separated.
