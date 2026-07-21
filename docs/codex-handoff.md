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
5. [`privacy.md`](privacy.md)
6. [`../integrations/hermes/README.md`](../integrations/hermes/README.md)

## First prompt for Codex

```text
Implement Phase 1 of this repository on the real machines.
Read AGENTS.md, docs/phase-1-plan.md, docs/public-access.md and docs/privacy.md completely before changing files.
First inspect and record the actual server, Docker, Codex, backup-secretary and Cloudflare environment in an untracked local file. Do not guess addresses, paths, ports, versions, Compose topology, Cloudflare team names, tunnel IDs, Access AUD values, email addresses or credentials.

Implement a private pinned Grafana/OTel backend for all Codex and Hermes telemetry. Integrate Windows Codex CLI and desktop through the user-level Codex config, and integrate both backup-secretary Hermes instances through a pinned briancaffey/hermes-otel installation.

Also implement a physically/logically separate Hermes-only shared backend and Grafana. Publish only that shared Grafana at https://observe.yanelmo.net through a named outbound-only Cloudflare Tunnel protected by Cloudflare Access. Use Access identity email with Grafana auth-proxy auto-provisioning. All new users must be Viewer; only the owner's Access-backed account and local break-glass account may be Admin. Do not publish OTLP or the private Grafana.

Grafana OSS data-source access is not a sufficient boundary, so personal Codex and future host telemetry must not exist in the shared datasource/backend. Mirror only the approved Hermes signal set to the shared stack.

Hermes must capture Discord sender IDs for per-user accounting, while prompt/response/conversation/tool payloads and general logs remain disabled. Verify user.id=discord:<ID> and rolled-up token counts coexist on the root agent span. Keep local-obserbablity and backup-secretary changes in separate commits and PRs. Do not start Phase 2 until all Phase 1 acceptance criteria pass.
```

## Completion output expected from Codex

- summary of detected server, Windows, Docker and Cloudflare environment;
- files changed in each repository;
- selected pinned versions;
- exact sanitized validation commands/results;
- proof that private and shared data boundaries are separate;
- proof that approved Access users become distinct Viewer accounts;
- proof that an unapproved identity is denied;
- remaining limitations;
- PR links for both repositories where changes are required;
- explicit confirmation that Discord IDs are collected but content payloads are not;
- explicit confirmation that Codex telemetry is absent from the shared backend and Grafana.
