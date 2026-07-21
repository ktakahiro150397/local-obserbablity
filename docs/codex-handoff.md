# Codex handoff: Phase 1

Work from this branch on the real local server and main Windows PC:

```text
feat/phase-1-codex-hermes
```

## Required reading

1. [`../AGENTS.md`](../AGENTS.md)
2. [`architecture.md`](architecture.md)
3. [`phase-1-plan.md`](phase-1-plan.md)
4. [`privacy.md`](privacy.md)
5. [`../integrations/hermes/README.md`](../integrations/hermes/README.md)

## First prompt for Codex

```text
Implement Phase 1 of this repository on the real machines.
Read AGENTS.md and docs/phase-1-plan.md completely before changing files.
First inspect and record the actual server, Docker, Codex and backup-secretary environment in an untracked local file. Do not guess addresses, paths, ports, versions or Compose topology.

Then implement the local pinned Grafana/OTel backend, integrate Windows Codex CLI and desktop through the user-level Codex config, and integrate both backup-secretary Hermes instances through a pinned briancaffey/hermes-otel installation.

Hermes must capture Discord sender IDs for per-user accounting, while prompt/response/conversation/tool payloads and general logs remain disabled. Verify user.id=discord:<ID> and rolled-up token counts coexist on the root agent span. Keep local-obserbablity and backup-secretary changes in separate commits and PRs. Do not start Phase 2 until all Phase 1 acceptance criteria pass.
```

## Completion output expected from Codex

- summary of detected environment;
- files changed in each repository;
- selected pinned versions;
- exact sanitized validation commands/results;
- remaining limitations;
- PR links for both repositories where changes are required;
- explicit confirmation that Discord IDs are collected but content payloads are not.
