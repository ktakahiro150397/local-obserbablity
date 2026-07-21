# local-obserbablity

Local observability stack for personal AI tools and home-server infrastructure.

> The repository name intentionally follows the existing GitHub repository spelling: `local-obserbablity`.

## Goal

Collect and visualize telemetry from AI clients and the local server without coupling the observability stack to `backup-secretary`.

```text
Windows main PC                 Local server
├─ Codex CLI ───────────────┐   ├─ local-obserbablity
├─ Codex desktop app ───────┼──▶│  ├─ OTLP receiver
└─ OpenCode (Phase 3) ──────┘   │  ├─ Grafana
                                │  ├─ Tempo
backup-secretary                │  ├─ metrics backend
├─ Hermes main ────────────────▶│  └─ logs backend
└─ Hermes owashota ────────────▶│
                                └─ host/container telemetry (Phase 2)
```

The observability stack must be optional and fail-open. Codex and Hermes must continue working when it is stopped or unreachable.

## Roadmap

### Phase 1: Codex and Hermes

- Start a persistent local Grafana OpenTelemetry backend.
- Receive Codex CLI and Codex desktop telemetry from the main Windows PC.
- Integrate [`briancaffey/hermes-otel`](https://github.com/briancaffey/hermes-otel) into `backup-secretary`.
- Capture Discord sender IDs intentionally so shared-Hermes usage can be grouped by user.
- Do not capture prompts, conversation history, tool arguments, tool results, or logs by default.
- Provision initial Codex and Hermes dashboards.

### Phase 2: Local server

- Linux host CPU, memory, disk, network, load and uptime.
- Docker container CPU, memory, network, I/O and restart status.
- Add alerts only after baseline data is available.

### Phase 3: OpenCode and Windows

- Collect OpenCode model, token, cost and tool usage.
- Collect Windows host CPU, memory, disk, network and selected service/process health.

## Phase 1 decisions

- Bootstrap with `grafana/otel-lgtm` because it packages Grafana, an OTel Collector, Tempo, Loki and a metrics backend into one local stack.
- Persist `/data` to a Docker volume or bind mount.
- Pin container images and the `hermes-otel` dependency. Do not use unpinned `latest` in the completed implementation.
- Keep OTLP and Grafana LAN-only. Firewall access should be limited to the main PC and local Docker workloads.
- Configure Codex telemetry only in the user-level `%USERPROFILE%\.codex\config.toml`; project-local Codex config cannot override telemetry routing.
- Enable Hermes `capture_sender_id`, which produces `user.id=discord:<sender_id>` on spans.
- Build per-user Hermes token panels from the root `agent` spans, where the sender ID and rolled-up token counts coexist.

## Privacy boundary

Discord IDs are personal identifiers and are collected deliberately for household usage accounting. The public repository must never contain:

- real Discord IDs;
- Discord ID-to-name mappings;
- prompts or conversation content;
- API keys, passwords, tokens or private hostnames/IP addresses;
- exported telemetry data.

See [`docs/privacy.md`](docs/privacy.md).

## Codex handoff

The implementation order and acceptance criteria are in:

- [`AGENTS.md`](AGENTS.md)
- [`docs/architecture.md`](docs/architecture.md)
- [`docs/phase-1-plan.md`](docs/phase-1-plan.md)
- [`docs/privacy.md`](docs/privacy.md)

## Related repositories

- [`ktakahiro150397/backup-secretary`](https://github.com/ktakahiro150397/backup-secretary)
- [`briancaffey/hermes-otel`](https://github.com/briancaffey/hermes-otel)

## Status

Planning scaffold only. The next step is Phase 1 implementation on the real local server and main Windows PC.
