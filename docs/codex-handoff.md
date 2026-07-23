# Codex handoff: Phase 2 and Phase 3

This is the copy-ready handoff for the next implementation work on the
authoritative local server and main Windows PC.

## Repository start state

Phase 1 is complete with the accepted H6 limitation recorded in
`verification.md`. The authorized Codex/Hermes Phase 4 import and live rollup
are complete. OpenCode history is not part of that completed import.

Codex must:

1. fetch and fast-forward to the latest remote `main`;
2. create a fresh Phase 2 branch, defaulting to
   `feat/phase-2-implementation`;
3. not implement directly on `main`;
4. not reuse a Phase 1, Phase 4, dashboard, or readiness branch;
5. finish and merge Phase 2 before starting a fresh Phase 3 branch;
6. keep any future `backup-secretary` change in its own branch and PR.

## Required reading

1. [`../README.md`](../README.md)
2. [`../AGENTS.md`](../AGENTS.md)
3. [`architecture.md`](architecture.md)
4. [`phase-2-plan.md`](phase-2-plan.md)
5. [`phase-3-plan.md`](phase-3-plan.md)
6. [`human-actions.md`](human-actions.md)
7. [`privacy.md`](privacy.md)
8. [`runbook.md`](runbook.md)
9. [`verification.md`](verification.md)
10. [`references.md`](references.md)
11. [`phase-4-backfill.md`](phase-4-backfill.md) only for the optional
    OpenCode historical extension

## Prompt to give Codex

```text
Prepare and implement Phase 2, followed by Phase 3, on the real local server
and main Windows PC.

First update to the latest remote main. Do not implement on main and do not
reuse an old Phase 1, Phase 4, dashboard, or readiness branch. Create a fresh
Phase 2 implementation branch. Merge Phase 2 before creating the separate
Phase 3 implementation branch.

Read README.md, AGENTS.md, docs/architecture.md, docs/phase-2-plan.md,
docs/phase-3-plan.md, docs/human-actions.md, docs/privacy.md, docs/runbook.md,
docs/verification.md, docs/references.md, and the relevant parts of
docs/phase-4-backfill.md completely before changing implementation files.

Treat the real yanelmoserver deployment and main Windows PC as authoritative.
Preserve the running Phase 1/4 topology, data, secrets, and accepted H6
limitation. Record machine-specific findings only in ignored
notes/environment.local.md and notes/human-actions.local.md.

Implement Phase 2 first: private-only Linux host and Docker monitoring. Use a
separate pinned infrastructure collector with minimum read-only host mounts.
Treat Docker API access as a security-sensitive human gate; a read-only socket
mount is not a read-only Docker permission. Do not use TCP 9100, which is
already occupied. Do not add public listeners, router forwarding, Cloudflare
routes, host telemetry to the shared backend, or general logs. Build dashboards
from actual received metric names and set alerts only after baseline evidence.

After Phase 2 is accepted and merged, implement Phase 3 on a fresh branch:
private-only Windows host and OpenCode telemetry. Use outbound OTLP where
possible. Before production OpenCode telemetry, run the synthetic privacy spike
from docs/phase-3-plan.md because the installed OpenCode version constructs an
OTLP log exporter when its endpoint is enabled. Reject logs and prove prompt,
response, tool payload, path, project, account, and credential content is
absent. If useful content-free traces cannot be isolated, document the
limitation instead of weakening privacy.

The completed Phase 4 scope covers Codex and Hermes. Historical OpenCode import
is an optional Phase 3 follow-on, requires separate owner authorization, reads
only explicit aggregate columns from a consistent snapshot, and remains
private. Never scan or export credential-, prompt-, message-, title-, path-, or
arbitrary JSON-bearing columns.

At each human gate, finish every safe prerequisite and provide one exact
numbered HUMAN ACTION REQUIRED packet. Never ask for secrets or private
identifiers in chat. Verify every action after the owner completes it and
provide rollback for permission, service, firewall, reboot, or import changes.
```

## Expected Phase 2 output

- pinned collector version/digest and reviewed receiver configuration;
- measured memory, storage, and series impact;
- private server and Docker dashboards;
- approved Docker API boundary;
- fail-open and shared-isolation evidence;
- baseline/alert decision record;
- exact rollback and upgrade procedure.

## Expected Phase 3 output

- pinned Windows collector artifact and checksum;
- synthetic OpenCode privacy-spike evidence;
- actual safe OpenCode attribute allow-list;
- private OpenCode and Windows dashboards;
- service install/uninstall and fail-open evidence;
- shared-domain zero-result proof;
- separately authorized and reconciled OpenCode history, if performed;
- remaining limitations and human-gate table.
