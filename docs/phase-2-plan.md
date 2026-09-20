# Phase 2 plan: Linux and Docker observability

## Status and objective

Phase 1 and the authorized Codex/Hermes Phase 4 backfill are complete. Phase 2
is the next implementation phase.

Phase 2 adds private-only telemetry for:

- Linux CPU, memory, load, paging, uptime, disk, filesystem, and network;
- Docker container CPU, memory, network, block I/O, health, and restart state;
- capacity and availability alerts after a representative baseline exists.

No Phase 2 signal may enter the shared Hermes backend or shared Grafana.
Collection must fail open: stopping the monitoring agents must not affect
Docker workloads, Hermes, the private/shared backends, or Cloudflare access.

## Sanitized readiness inventory

The authoritative local server was inspected before this plan was written.

- Linux is `x86_64`, uses cgroup v2 with systemd, and runs current Docker Engine
  and Compose v2 releases.
- The server has 4 logical CPUs and about 8 GiB of RAM.
- Swap pressure is already material, so Phase 2 must measure before adding
  expensive cardinality or process-wide collection.
- Both the system disk and the telemetry disk have useful free capacity.
- No host-metrics or Docker-metrics collector is currently installed.
- TCP 9100 is already used by an unrelated application. Phase 2 must not assume
  or claim that port.
- Docker daemon metrics are not enabled.
- The private Prometheus currently self-scrapes; the central collector already
  promotes selected resource identity into private metrics.

Private addresses, mount paths, hostnames, and the unrelated service name stay
in ignored local notes.

## Chosen topology

Use a dedicated, private-only OpenTelemetry Collector Contrib instance for
infrastructure collection:

```text
read-only host filesystems -> hostmetrics receiver ─┐
                                                    ├─> private metrics backend
restricted Docker API ----> docker_stats receiver ─┘
```

The infrastructure collector is separate from the central application
telemetry router. This keeps host mounts and Docker API authority out of the
router that accepts Codex and Hermes traffic.

The implementation branch starts from current `main` and defaults to
`feat/phase-2-implementation` or a non-conflicting suffix. It must not reuse a
Phase 1 or Phase 4 branch.

## Security boundary

### Host metrics

Run the collector with the minimum read-only host mounts required by the
OpenTelemetry `hostmetrics` receiver. Configure its `root_path` for a
containerized collector and explicitly select scrapers. Do not grant
`--privileged`, host PID, host network, or writable host mounts merely for
convenience.

Process-level collection is out of the initial deployment. Add it only after
measuring cost and reviewing whether command lines, users, or paths could
become attributes.

### Docker metrics

Treat Docker API access as a security-sensitive capability. Before enabling
`docker_stats`, prepare and compare:

1. a least-privilege Docker socket proxy that exposes only the read operations
   actually required by the receiver; and
2. direct read-only socket mounting in an isolated collector.

The owner must approve the selected boundary. A read-only filesystem mount of
`docker.sock` is not a read-only Docker API permission. Never expose the Docker
API on a LAN or public listener.

### Network

- Prefer no new host listener. Export over the existing private Docker network.
- Do not use TCP 9100.
- Do not add router forwarding.
- Do not route Phase 2 ingestion, collector, or backend APIs through Cloudflare.
- Keep private Grafana owner-only; the reviewed dedicated owner-only Grafana web
  route does not change the private-only storage boundary.
- Prove the shared collector, shared storage, and shared Grafana contain no host
  or container telemetry.

## Resource identity and cardinality

Use local configuration for machine-specific values. The committed defaults
are:

| Source | `service.name` | Stable dimensions |
|---|---|---|
| Linux host | `local-server` | local-only instance ID |
| Docker | `docker` | container name, image name, Compose project/service when emitted |

Do not promote container IDs, image digests, mount paths, command lines, or
private hostnames into unbounded metric labels. Keep high-cardinality
identifiers available only when a concrete diagnostic use justifies them.

## Work packages

### P2.1 — Baseline and version review

- Re-run the sanitized server inventory.
- Record current collector/back-end image digests and free capacity.
- Re-check official `hostmetrics` and `docker_stats` receiver documentation
  against the exact collector version selected for deployment.
- Measure current private/shared stack memory before adding collection.
- Store private values only in `notes/environment.local.md`.

### P2.2 — Host collector

- Add a separately pinned infrastructure collector service.
- Configure explicit CPU, load, memory, paging, filesystem, disk, network, and
  system scrapers.
- Exclude pseudo-filesystems, ephemeral mounts, and loop devices based on
  observed names.
- Add bounded memory, batch, and retry processors.
- Persist no host content or general logs.
- Add health checks and a safe configuration-validation command.

### P2.3 — Docker collector

- Complete the Docker API security review and human gate.
- Enable only the required receiver/API surface.
- Limit metrics to operational container dimensions.
- Verify stopped/unhealthy/restarted containers are represented without
  generating uncontrolled series churn.
- Prove loss of Docker API access affects monitoring only.

### P2.4 — Private dashboards

Provision:

1. **Server overview** — CPU, load, memory, swap, filesystem use, disk I/O,
   network, uptime, and collector health.
2. **Docker overview** — container CPU, memory, network, block I/O, status,
   restart/health state, and top consumers.

Build panels from actual received metric names. Do not assume names from a
different collector version or backend normalization.

### P2.5 — Baseline and alerts

- Observe at least seven representative days before choosing normal thresholds
  where practical.
- Start with collector-down, disk-capacity, sustained memory/swap pressure, and
  repeated container-restart candidates.
- Document duration, recovery condition, and expected false positives for each
  alert.
- Route notifications only after the owner approves the destination and test
  behavior.

### P2.6 — Verification and handoff

- Validate config and container health.
- Verify persistence through a collector/backend restart.
- Stop the infrastructure collector and prove application workloads remain
  healthy.
- Revoke Docker API access and prove fail-open behavior.
- Query the shared backends for host/container service identities and require
  zero results.
- Update runbook, verification ledger, backup/restore scope, and capacity notes.

## Human gates

### P2-H1 — Docker API boundary

Owner approval is required immediately before granting any process access to
the Docker API. The packet must show the exact service, mount/proxy rule,
allowed operations, verification query, rollback, and prohibited public
exposure.

### P2-H2 — Host permission or firewall change

Owner approval is required before adding privileged capabilities, weakening
permissions, or changing the host firewall. The default design should require
none of these.

### P2-H3 — Alert destination and thresholds

The owner chooses notification destinations and accepts initial thresholds
after baseline evidence is available. Do not commit destination credentials.

## Acceptance criteria

Phase 2 is complete only when:

1. real host and Docker metrics render in private Grafana;
2. actual metric names and stable dimensions are recorded;
3. monitoring loss does not affect applications;
4. collector privileges match the approved minimum;
5. no new public listener or router forwarding exists;
6. the shared domain returns zero host/container telemetry;
7. storage and memory impact are measured and acceptable;
8. dashboards, validation, rollback, and operational procedures are committed;
9. every human gate is verified or an explicit limitation is accepted.
