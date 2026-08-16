# 2026-08-16 local observability memory-pressure incident

## Scope

This record covers only services owned by `local-obserbablity`. Other
repositories have separate remediation threads and were not changed. Evidence
is sanitized: it contains no private address, hostname, username, account
identifier, Discord ID, credential, raw trace, command argument, or general
application-log content.

## Read-only diagnosis

The checkout and freshly fetched `origin/main` both resolved to
`7225a0a216e3ea91ec420c9e55722f52919a4483`. Diagnosis then ran from the fresh
`feat/phase-2-implementation` branch.

The shared aggregate container had remained running, but its Tempo child was
absent. Grafana, Prometheus, and Loki still returned readiness while Tempo did
not. Kernel cgroup evidence identifies one `tempo` OOM at 2026-08-04 16:07 JST;
the selected Tempo process had about 1.12 GiB anonymous RSS. The current
container began after the previously documented July recovery, so this is a
new event rather than the accepted July flag.

Docker health correctly became `unhealthy`, but Docker does not restart a
container merely because its health state changes. The bundled PID 1 survived
the child OOM, so `restart: unless-stopped` never ran. The shared Tempo outage
therefore remained latent.

The live rollup last advanced its two sanitized checkpoints on 2026-08-04. Its
health file was about 12 days old and its structured operational events contain
6,524 `TempoError` results after the source disappeared. It remains a running,
fail-open process and did not affect Hermes or private ingestion.

Both PostgreSQL ledgers experienced short cgroup OOM bursts between 03:01 and
03:07 JST on 2026-08-16. The selected victims were only `pg_isready` or the
short-lived container exec initializer; PostgreSQL itself survived. The
private and shared ledgers were healthy at diagnosis with approximately 106
MiB and 13 MiB databases, respectively. Their defaults nevertheless reserved
128 MiB shared buffers inside a 384 MiB cgroup and allowed 100 connections,
leaving too little burst headroom during host pressure.

During diagnosis the host fell to about 1.4 GiB available RAM with memory PSI
`full avg10` around 15.6% and I/O PSI around 29.4%. The final strict preflight
improved to about 1.8 GiB and near-zero current PSI, but swap remained exhausted
and the 3 GiB restart threshold still failed. There were no D-state tasks or
recent kernel OOM. The local observability containers had no zombie processes;
host-wide zombie ownership and non-observability workloads are outside this
repository.

## Prepared remediation

- Mount an explicit Tempo 3.0.2 configuration in both pinned LGTM containers.
  It enables cgroup-aware Go memory limiting at a 0.35 ratio, limits querier
  concurrency to two jobs and batches to one, and disables unused
  metrics-generator processors. The central collector already exports the
  approved metrics, and no provisioned dashboard queries the generated
  `traces_spanmetrics_*` or service-graph series.
- Replace the passive LGTM health command with a content-free check that waits
  through a three-minute startup period, requires four consecutive failures,
  and then terminates the surviving bundle PID 1. Docker's existing restart
  policy can consequently restore a dead child without Docker socket access or
  a new host privilege.
- Reduce both ledgers to 64 MiB shared buffers, 2 MiB work memory, 32 MiB
  maintenance work memory, and 32 connections while retaining the 384 MiB hard
  limit and existing named volumes.
- Add a bounded recovery worker that reads only the allowlisted Hermes service
  and approved instances from private Tempo and writes through the existing
  shared-ledger constraint. It cannot select Codex or arbitrary telemetry.
- Add an execution guard that refuses recovery until available memory, PSI,
  swap-in rate, D-state count, and recent OOM evidence are within the reviewed
  safety envelope.

No retention reduction, data deletion, privilege increase, firewall change,
Docker API grant, public listener, or cross-repository change is included.

## Recovery ordering

The normal rollup must be stopped before shared Tempo is recreated. If it ran
against the empty outage interval in shared Tempo, it could advance the durable
checkpoint without recovering traces that remained only in the private mirror.
The pinned Tempo binary reports a 336-hour default block retention, so the
oldest part of the August 4 outage begins aging out around August 18. Recovery
should run as soon as the host passes the pressure gate; data that has expired
from the private mirror must be reported as unavailable rather than estimated.

The guarded recovery therefore performs this order:

1. pass the strict pressure and private-source preflight;
2. build the already pinned rollup image before any service interruption;
3. repeat the complete strict preflight after the build, because the build can
   temporarily increase host pressure;
4. stop only the live rollup and create a verified two-ledger backup;
5. recreate only shared LGTM with its existing persistent mounts;
6. recover in bounded private-Tempo batches with pressure checks between them;
7. require current checkpoints, zero duplicate keys, and zero shared-isolation
   violations;
8. recreate each ledger individually with the reduced working set;
9. recreate the normal rollup and verify healthy operation.

If a recovery batch stops, the normal rollup deliberately stays stopped so the
checkpoint is not advanced incorrectly. Rerunning the idempotent recovery is
the preferred continuation. Restoring the pre-write ledger backup is
destructive and remains a separate H10 action.

## Validation before live action

- Tempo 3.0.2 accepted the committed configuration with
  `-config.verify=true` in a disposable container using the exact pinned LGTM
  image digest.
- Compose validation passed for the base and recovery override using synthetic
  secrets and paths.
- Ten rollup unit tests and the LGTM health-state test passed.
- Shell syntax validation passed for both health and recovery scripts.
- No live service was stopped, restarted, recreated, or reconfigured while the
  strict pressure gate was failing.
- The owner approved the exact P2-H4 recovery packet. Post-approval monitoring
  never reached the 3 GiB available-memory threshold. The final sample improved
  to about 2.0 GiB available memory, low PSI, one D-state task, and no recent
  OOM evidence, but correctly remained a failed gate.
- The guarded executor never started: its process was absent, its lock was
  free, the affected containers retained their prior start times, and both
  durable rollup checkpoints retained their August 4 values. No backup, build,
  stop, restart, recreate, deployment, or ledger write occurred.
- Cross-thread coordination later found that a separate repository had first
  validated a different Docker daemon. The actual monitored daemon still ran
  an old unbounded container that held about 3.5 GiB memory, 1 GiB swap, and
  more than 350 PIDs. Its responsible thread then recreated only that service
  with finite memory/PID limits and swap disabled.
- The host briefly passed the P2-H4 gate after that correction, but the guarded
  executor rejected the first attempt because the other service had emitted a
  new OOM during its transition. After the required 20-minute quiet window,
  the other service had again grown to about 3.4 GiB and the host had only
  about 1.5 GiB available, so the executor rejected the second attempt before
  any local-observability live action.
- Content-free process metadata attributed most of the renewed external cgroup
  growth to one s6-managed `run` process rather than to the local-observability
  stack. The external container subsequently recorded another child OOM while
  remaining healthy. That repository remains the blocking owner; its files and
  services were not changed from this branch.
- A later sample reached exactly the 3 GiB available-memory threshold, but the
  executor's own preflight eight seconds later measured about 3.0 GiB minus
  18 MiB and rejected the run before even building. This short-lived pass/fail
  confirms that the external cgroup is not yet stable enough for a controlled
  recovery; repeated attempts were stopped rather than waiting for a transient
  sample to slip through.
- The next hourly one-shot check found a new OOM selection at
  2026-08-16 02:37:12 UTC in `backup-secretary-hermes-owashota`; the selected
  process type was again `run`. Its current cgroup records one OOM and one OOM
  kill. The private/shared ledger and shared LGTM cumulative counters were
  unchanged, and the live rollup still records zero current-cgroup OOM events.
- Host swap free recovered to about 807 MiB and available memory was about
  3.1 GiB in that one sample, but memory/IO full PSI avg10 was about 13/22.
  Per the hourly-monitor contract this was recorded once and did not start a
  short-interval monitor or another gate-wait attempt.

The query-memory controls follow Grafana's guidance to lower querier work when
OOM occurs, and the custom config mount follows the documented otel-lgtm
override path. The pinned aggregate image remains a bootstrap limitation and
should be reassessed for a later split-component migration.
