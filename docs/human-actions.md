# Human-in-the-loop execution guide

## Purpose

Phase 1 is **Codex-led, not fully autonomous**. Codex should implement and verify everything it can on the real machines, but several steps require the repository owner to authenticate, make an account-level decision, enter a secret, or perform an interactive test.

Codex must use this document as an execution protocol. It must not silently skip human-only work, claim completion before it is done, or ask the owner to paste secrets into chat or a public issue.

## Responsibility labels

Use these labels in plans, progress reports, and the untracked local checklist:

- **CODEX** — safe to implement and verify from the terminal or repository without an account-owner decision.
- **HUMAN** — must be performed by the owner or another explicitly authorized person.
- **JOINT** — Codex prepares the exact values/commands and verifies the result; the human performs authentication, approval, secret entry, or the interactive action.

Codex should create and maintain an untracked file such as:

```text
notes/human-actions.local.md
```

It may contain completion state and non-secret identifiers, but never passwords, OAuth client secrets, tunnel tokens, approved email lists, real Discord IDs, or private screenshots.

## Required behavior at a human gate

Before stopping for a human action, Codex must complete all safe preparatory work first. It must then present one actionable instruction packet in this format:

```text
HUMAN ACTION REQUIRED — <gate ID and title>

Why a human is required:
<authentication, account ownership, security decision, physical interaction, etc.>

Do:
1. <exact UI path or local action>
2. <exact field/value, using placeholders for secrets>
3. <what must not be enabled or exposed>

Store secrets locally in:
<exact ignored file, secret manager, or environment variable name>

Return to Codex:
- say "<gate ID> complete";
- provide only the listed non-secret values or observable outcome;
- do not paste any secret.

Codex will verify:
- <commands, HTTP checks, API/UI outcome, or configuration diff>

Rollback:
- <how to undo or disable the change>
```

Codex must avoid vague requests such as “configure Cloudflare.” It should name the dashboard path, expected values, failure conditions, and the next verification step. If the vendor UI differs from the current documentation, Codex should explain what invariant is required rather than inventing a button name.

## Secret-handling rule

The human may be asked to enter a secret into a local ignored file, OS credential store, Cloudflare dashboard, Google Cloud dashboard, or secret manager. Codex may create the template and verify that a value exists without printing it.

Codex must never ask the human to paste any of the following into chat, a Git commit, a PR, an issue, or command output that will be recorded:

- Cloudflare tunnel token or tunnel credential JSON;
- Cloudflare Access application AUD;
- Google OAuth Client Secret;
- Grafana administrator password;
- API/provider keys;
- approved user email list;
- real Discord user IDs or ID-to-name mappings.

When a command would echo a secret, Codex must use a safer input method or tell the human exactly how to enter it locally.

## Phase 1 human gates

### H1 — Cloudflare account and domain ownership

**Owner: HUMAN / JOINT**

The owner must:

- sign in to the Cloudflare account that controls `yanelmo.net`;
- confirm the zone is active and that Zero Trust is available in the intended account;
- choose or confirm the Cloudflare Access team name;
- approve the use of `observe.yanelmo.net`.

Codex can prepare the hostname, configuration templates, DNS/tunnel checks, and a local record of non-secret values. It cannot take ownership of the account or approve domain-level changes on the owner's behalf.

### H2 — Named Cloudflare Tunnel authentication

**Owner: JOINT**

Codex may install a pinned `cloudflared`, prepare the container/service, and initiate a browser-based login or provide the dashboard path. The owner must authenticate and authorize the tunnel against the correct zone/account.

If a dashboard-managed tunnel token is used, the owner stores it in an ignored local secret file or secret manager. Codex verifies only that the service starts and that the public hostname reaches the shared Grafana. The token must never be returned in chat.

### H3 — Google identity provider

**Owner: HUMAN / JOINT**

The owner must sign in to Google Cloud and create or select the project used for Access authentication. The owner performs or approves:

- OAuth consent-screen configuration;
- External audience when ordinary Google accounts are allowed;
- OAuth Web application client creation;
- the Cloudflare Access team origin and callback URI;
- the OAuth application's testing/production publishing decision;
- entry of the Client ID and Client Secret into Cloudflare Zero Trust.

Codex provides the exact origin and callback values after discovering the real Access team name. The human stores the Client Secret only in Google/Cloudflare or a private local secret manager.

### H4 — Cloudflare Access policy and login methods

**Owner: HUMAN / JOINT**

The owner approves the exact people who may access the dashboard and enters their email addresses directly in Cloudflare Access. The policy must:

- apply only to `observe.yanelmo.net`;
- enable both Google and One-time PIN;
- allow only exact approved email identities;
- contain no `Everyone`, bypass, shared-account, or broad email-domain rule unless the owner explicitly changes the security model;
- use a deliberately selected session duration.

Codex can provide a checklist and later verify allow/deny behavior with test accounts, but it must not commit or display the approved email list.

### H5 — Grafana first login and owner promotion

**Owner: JOINT**

The owner first signs in through Cloudflare Access so the owner's Access-backed Grafana account exists. New accounts must default to Viewer.

Codex may then run a local bootstrap script or give the exact Grafana administration steps to promote only the owner's Access-backed account to Admin. A local break-glass administrator remains separate. Administrator credentials are entered locally and never pasted into chat.

### H6 — Interactive authentication tests

**Owner: HUMAN / JOINT**

At least the following browser tests require human interaction:

- owner login through Google;
- owner or approved-user login through OTP using the same email;
- verification that both methods resolve to one Grafana account;
- approved Viewer login;
- unapproved-email denial;
- logout/session-expiry behavior where practical.

Codex provides the test script/checklist and inspects Grafana user/role state or sanitized HTTP evidence after each test.

### H7 — Discord usage tests

**Owner: HUMAN / JOINT**

A real Discord user must send the test request that exercises Hermes. A second user should send a separate test request when safely available so distinct `user.id` values can be verified.

Participants should be informed that stable Discord IDs and aggregate usage metadata are collected. Codex verifies the resulting spans and dashboards but must not place real IDs in committed evidence.

### H8 — Codex desktop restart and interactive turn

**Owner: HUMAN / JOINT**

Codex can install/merge the Windows Codex configuration and verify the file. The owner may need to fully close and restart the desktop application and submit a fresh turn. Codex then verifies that desktop telemetry arrived and is distinguishable from CLI telemetry.

### H9 — Network and router confirmation

**Owner: HUMAN / JOINT**

Codex can inspect host firewall state and propose or apply narrowly scoped local rules when authorized. The owner must confirm the router has no inbound port-forwarding rule for Grafana, OTLP, or the origin service and must approve any change to home-network policy.

Only the shared Grafana hostname is published through the outbound Cloudflare Tunnel. OTLP and private Grafana remain private.

### H10 — Destructive or security-sensitive changes

**Owner: HUMAN**

Codex must request explicit approval immediately before:

- deleting telemetry or persistent volumes;
- deleting or disabling Access/Grafana users;
- changing DNS away from the intended tunnel;
- publishing or rotating Google OAuth credentials;
- weakening an Access policy;
- granting Editor/Admin to another user;
- opening router ports or broad firewall rules;
- changing retention in a way that deletes existing data.

Codex should prepare the command or UI steps and a rollback plan before requesting approval.

## Work Codex should complete without delegating to the human

Codex should not offload ordinary engineering work. It is expected to handle, where access permits:

- repository/branch/PR management;
- Docker Compose, pinned images, networks, health checks, volumes, backup scripts, and configuration validation;
- private and shared backend separation;
- Grafana provisioning, dashboards, default Viewer policy, and bootstrap tooling;
- `cloudflared` service templates and local networking;
- Codex configuration backup/merge/verification scripts;
- pinned `hermes-otel` integration in `backup-secretary`;
- privacy defaults and fail-open behavior;
- smoke tests, endpoint checks, data-boundary tests, and sanitized verification records;
- detection of incomplete human gates and generation of the next exact instruction packet.

## Completion rule

Phase 1 is not complete until every required human gate is either:

1. completed and verified; or
2. explicitly deferred with the resulting limitation documented in the PR and runbook.

Codex's final report must contain a table with: gate ID, status, human action performed, Codex verification, and any remaining risk. It must not use “configured” or “working” for a Cloudflare, Google, Grafana-account, Windows-desktop, router, or Discord-user step that has not actually been exercised.