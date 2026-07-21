# Phase 1 verification ledger

Phase 1 is complete only when every required real-machine result below is tested. Planning, configuration validation, synthetic tests, or a human saying a UI step was performed do not replace Codex verification of the observable result.

The live local ledger is `notes/human-actions.local.md`; environment evidence is `notes/environment.local.md`. Both are ignored. Committed evidence must be sanitized and contain no addresses, hostnames, usernames, emails, Discord IDs, Cloudflare identifiers, Access AUD values, secrets, payloads, or raw telemetry exports.

## Human gates

| Gate | Owner action | Codex verification | Completion rule |
|---|---|---|---|
| H1 | Authenticate to Cloudflare and record the chosen account/zone/team/mode locally | Validate required non-secret fields and tunnel mode without printing identifiers | Discovery values are present and internally consistent |
| H2 | Authorize/create the named tunnel and enter its token locally | Tunnel exists, token file permissions are correct, route targets only shared Grafana | No token appears in chat, Git, history, or process arguments |
| H3 | Create/configure Google OAuth and enter the client values in Cloudflare | Google appears as a selectable Access method and callback values match the team domain | No OAuth secret is exported |
| H4 | Decide exact allow-list/session duration and configure Access | Exact-email include rules only; Google and OTP selected; instant auth off; no bypass/Everyone/domain/group policy | Unapproved policy paths are absent |
| H5 | First approved Google login | One Grafana user created as Viewer; identity header is accepted only from the tunnel boundary | Role and source boundary verified |
| H6 | First approved OTP login using the same email | Same Grafana user ID is reused; different approved email creates a different user | Convergence/separation verified without recording emails |
| H7 | Send real Discord turns after disclosure | Both instances emit root `agent` spans with matching sender/user ID and rolled-up tokens; content fields absent | One or two people tested as available |
| H8 | Fully exit/restart Codex desktop and perform a non-sensitive turn | CLI and desktop telemetry both present privately; stable distinguishing attributes documented; shared remains empty of Codex | Process restart, not window reload |
| H9 | Confirm router exposure and approve LAN/firewall binding | No router forwarding; only intended local/LAN listeners; public probes cannot reach Grafana/OTLP | Exact approved exposure only |
| H10 | Approve an exact destructive or permission-weakening action | Targets and rollback checked before action; result and recovery verified afterward | Approval is action-specific and time-bounded |

Sanitized final gate status:

| Gate | Status | Remaining limitation |
|---|---|---|
| H1 | Complete | None |
| H2 | Complete | None |
| H3 | Complete | None |
| H4 | Complete | None |
| H5 | Complete | None |
| H6 | Deferred and accepted | No second approved identity was available, so persistent Viewer/different-email separation and unapproved-identity denial were not exercised. Same-email Google/OTP convergence and initial Viewer assignment were verified. |
| H7 | Complete | A second person was not required; both Hermes instances were verified with informed real turns. |
| H8 | Complete | None |
| H9 | Complete | None |
| H10 | Complete | None |

## Configuration and health

Run on the server:

```bash
./scripts/stack.sh config
./scripts/stack.sh status
curl --fail --silent http://127.0.0.1:13133/
docker compose --profile public config --images
```

Verify:

- every external image is tag-and-digest pinned;
- `hermes-otel` and Python OTel dependencies are pinned in the separate `backup-secretary` change;
- all enabled containers are healthy without restart loops or OOM events;
- private/shared data paths differ;
- Grafana ports bind only to localhost;
- OTLP binds only to the approved trusted interface;
- no router port forwards exist;
- no logs pipeline or Loki data source is provisioned.

## Storage persistence and recovery

1. Record baseline trace counts without raw payloads.
2. Recreate containers with `docker compose up -d --force-recreate`.
3. Confirm counts and Grafana users persist.
4. Run `scripts/backup.sh` and verify both checksum entries.
5. At H10, rehearse `scripts/restore.sh` from the selected backup.
6. Confirm private/shared counts, dashboards, users, and new ingestion after restore.
7. Confirm the pre-restore rollback directory remains recoverable.

Record archive sizes, elapsed time, and pass/fail only. Keep backup paths local.

## Private/shared isolation

First run:

```bash
./scripts/smoke-test.sh
```

Then verify with real sources:

- private Tempo contains Codex and Hermes;
- shared Tempo contains only `service.name=backup-secretary-hermes`;
- shared Grafana contains only its own Prometheus and Tempo data sources;
- no shared data source URL resolves or routes to the private backend;
- Codex service names/attributes return zero shared results;
- stopped shared storage does not stop private ingestion, and vice versa.

Test auth-proxy spoof resistance from a non-whitelisted source on the proxy network. A forged `Cf-Access-Authenticated-User-Email` must not create or authenticate a user. Do not use a real email in the test.

## Codex

Configuration acceptance:

```powershell
.\clients\codex\Test-CodexTelemetry.ps1
```

Real acceptance:

1. Confirm the CLI and desktop use the same effective user config.
2. Run a short non-sensitive CLI turn and locate it in private Tempo.
3. Complete H8, run a desktop turn, and locate it in private Tempo.
4. Compare actual resource/span attributes and choose the stable CLI/desktop dimension.
5. Verify token type, model, duration, and tool panels with actual received names.
6. Search shared Tempo for all observed Codex service names/attributes; expect zero.
7. Inspect representative spans and confirm no prompt body, response body, tool arguments, tool results, or structured logs were exported.

Real-machine Phase 1 observation uses `service.name=codex_exec` for a standalone
terminal CLI and `service.name=codex-app-server` for the desktop application.
`Codex Desktop` can appear on a subprocess that inherits the desktop originator,
so dashboards include it defensively but do not use it as the canonical desktop
identity.

The observed token schemas also differ. CLI rollups are on `session_task.turn`
under `codex.turn.token_usage.*`. Desktop turns start at `turn/start`, while each
model response reports `gen_ai.usage.*`, `codex.usage.total_tokens`, and
`codex.usage.reasoning_output_tokens` on `handle_responses`. Dashboard queries
keep these two schemas separate to avoid silently dropping desktop usage.

Do not assume backend-normalized metric names or a client attribute until observed.

## Hermes

For both `main` and `owashota`, verify:

- the image build contains the pinned plugin and dependencies before startup;
- Hermes discovers and registers the plugin without runtime installation;
- resource attributes include the approved service name, namespace, and stable instance ID;
- a real Discord turn contains `hermes.sender.id` and `user.id=discord:<same ID>`;
- the root `agent` span has the same `user.id` and rolled-up token attributes;
- descendant model/provider, duration, error, and tool-name metadata is useful;
- prompt/response/history/tool payload attributes and general logs are absent;
- matching approved telemetry appears in private and shared storage;
- no real ID or mapping is copied into committed evidence.

Stop the collector, each backend, and the tunnel separately. Hermes must continue answering. Restore each component and verify telemetry resumes without installing or editing anything inside a running container.

## Cloudflare, identities, and roles

Through human browser tests and Codex-side state checks, verify:

- the only published hostname is `https://observe.yanelmo.net`;
- only Google and One-time PIN are offered, with instant authentication off;
- exact approved identities pass and an unapproved identity is denied before Grafana;
- same email through Google and OTP maps to one Grafana user;
- different approved emails map to different Grafana users;
- new users are Viewer;
- the owner is organization Admin, not server administrator;
- the local break-glass account is a separate server administrator and works with the tunnel stopped;
- the shared Grafana origin cannot be reached remotely or by direct router forwarding;
- a forged identity header outside the fixed tunnel source is rejected.

Screenshots containing emails, team names, account IDs, or Access identifiers remain local and are not attached to public issues or pull requests.

## Dashboard acceptance

Private dashboards:

1. AI overview — requests/tokens by observed source and model.
2. Codex — observed token types, model, CLI/desktop, duration, and tools.
3. Hermes — instance, model/provider, observed token types, duration, errors, and tools.

Shared dashboard:

4. Hermes users — total/input/output/cache/reasoning token panels grouped by `user.id`, with time and instance filters.

Remove or annotate any panel whose required real attribute is absent. Raw Discord IDs are permitted in the authorized shared dashboard but never in committed screenshots or mappings.

## Sanitized completion record

The final report must include:

- environment class and versions without private identifiers;
- files, commits, branches, and pull requests for each repository;
- exact pins and reviewed upstream commits;
- health, persistence, restore, fail-open, identity, role, privacy, and isolation results;
- an H1–H10 table with owner action and Codex verification;
- explicit confirmation that Discord IDs are collected but content payloads are not;
- explicit confirmation that personal Codex telemetry and data sources are absent from shared storage/Grafana;
- remaining limitations and unpassed tests.

Phase 1 is accepted with the explicit H6 limitation above. Do not claim that the
deferred second-identity or unapproved-identity outcomes were tested.

## Phase 4 BF3 sanitized verification — 2026-07-22

BF3 imported only the approved Codex and Hermes manifests into the private SQL
ledger. The shared ledger remained empty and BF4-gated.

| Source | Records | Total tokens | Parent-inherited user rows |
|---|---:|---:|---:|
| Codex main Windows | 136,659 | 18,499,230,194 | 0 |
| Hermes main | 824 | 729,721,300 | 83 |
| Hermes owashota | 3,465 | 2,607,730,387 | 129 |
| **Total** | **140,948** | **21,836,681,881** | **212** |

Verification results:

- both PostgreSQL 17.10 ledgers were healthy with zero restarts/OOM state;
- private/shared schemas, the shared Hermes-only constraint, and Grafana reader
  least privilege passed before import;
- a verified two-ledger backup was created while both ledgers contained zero
  usage/import/cutover/coverage rows;
- all 21 selected manifest/report/cutover artifacts passed their SHA-256 list;
- the first private import inserted the ten reviewed manifest counts exactly;
- re-running the same ten manifests inserted zero rows for every import run;
- private has 140,948 rows and 140,948 distinct canonical source keys;
- all ten import runs are complete, all three approved cutovers are present,
  and there are zero import errors or cutover violations;
- zero rows contain estimated cost, zero rows have zero total usage, and every
  row has `record_origin=backfill`;
- shared remains at zero usage rows, import runs, reports, errors, and cutovers;
- the pre-import backup checksums passed again after verification.

Hermes user inheritance follows only an explicit same-database
`parent_session_id` chain that reaches a direct valid Discord identity. The
importer does not infer from time, model, or neighboring sessions, and marks
inherited rows in `quality_reason`. This corrects pre-cutover SQLite history
only. The separate `backup-secretary` fix now propagates parent user accounting
onto delegated child root, LLM, and API spans. A real delegated Discord turn
reached private and shared telemetry with consistent user attribution, complete
root token rollup, and no blocked content attributes. Existing pre-fix live
spans were not rewritten.

## Phase 4 BF4 pre-publication verification — 2026-07-22

Nine fresh `--shared` Hermes manifests were generated from the same immutable
snapshots and approved cutovers used for BF3. The private manifests were not
republished. Every shared candidate removes estimated/actual cost and pricing
and passed the dedicated Hermes-only validator.

| Source | Records | Total tokens | Known-user rows | Unknown-user rows | Parent-inherited rows |
|---|---:|---:|---:|---:|---:|
| Hermes main | 824 | 729,721,300 | 361 | 463 | 83 |
| Hermes owashota | 3,465 | 2,607,730,387 | 521 | 2,944 | 129 |
| **Total** | **4,289** | **3,337,451,687** | **882** | **3,407** | **212** |

There are seven distinct known numeric Discord accounting IDs across both
instances; no ID value or identity mapping is committed. Row-by-row comparison
with BF3 proved that every non-cost publication field is unchanged. Differences
are limited to the new import-run metadata, derived record hash, and removal of
cost/pricing values.

An isolated PostgreSQL 17.10 shared-schema test inserted all nine reviewed
manifest counts on the first pass and inserted zero on every unchanged rerun.
It reconciled to 4,289 rows, 3,337,451,687 total tokens, nine complete runs, two
cutovers, 212 inherited-user rows, zero Codex rows, zero cost rows, and zero
import errors. Historical dashboard SQL passed through the read-only Grafana
role.

Production remains unchanged pending owner BF4 approval: private still has the
BF3 total of 140,948 rows and shared has zero usage, import, coverage, error, and
cutover rows. The three shared Hermes-only constraints are active. A new exact
two-ledger pre-write backup was archive- and checksum-verified with directory
mode 0700 and file mode 0600. No shared production row has been written.
