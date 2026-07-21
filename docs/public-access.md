# Public access: Cloudflare Access and shared Grafana

## Goal

Publish a curated Hermes usage dashboard at:

```text
https://observe.yanelmo.net
```

Every permitted Discord user signs in with an individual identity. The repository owner keeps administrative access. No router port forwarding or publicly reachable origin port is allowed.

## Security boundary

Cloudflare Access and Grafana have separate responsibilities:

- **Cloudflare Access** decides who may reach the hostname.
- **Grafana authentication proxy** turns the authenticated Access email into an individual Grafana user.
- **Grafana roles and teams** decide whether that user is a Viewer or Administrator.
- **Telemetry routing/storage** decides which data is present in the shared Grafana at all.

Do not rely on dashboard or folder permissions to hide sensitive data while the same Grafana organization can query a broader data source. Grafana OSS does not provide data-source permissions. The shared Grafana/backend therefore receives only telemetry approved for all permitted Discord users.

## Recommended topology

```text
Codex CLI / desktop ────────┐
                            │
Hermes main / owashota ─────┼─> central OTel Collector
                            │       ├─> private backend + private Grafana
                            │       │     - all Codex telemetry
                            │       │     - all Hermes telemetry
                            │       │     - future server/Windows telemetry
                            │       │
                            │       └─> shared Hermes-only backend + Grafana
                            │             - Hermes usage only
                            │             - Discord sender accounting
                            │             - no content payloads or general logs
                            │
Internet user
  -> observe.yanelmo.net
  -> Cloudflare Access
  -> Cloudflare Tunnel
  -> shared Grafana only
```

The private Grafana remains local-only. The Cloudflare tunnel must not route to the private Grafana.

## Why the shared backend is separate

In Grafana OSS, a user in an organization can query its data sources even when individual dashboards are hidden. Folder and dashboard permissions are useful for UI organization, but are not a sufficient hard security boundary for personal Codex or host telemetry.

The public-facing Grafana must therefore use a data source that physically/logically contains only shared Hermes telemetry. Acceptable implementations are:

1. a second pinned LGTM stack receiving Hermes only; or
2. a proven multi-tenant backend where the shared Grafana data sources are locked to a Hermes-only tenant.

For Phase 1, prefer the second LGTM stack unless real-machine testing demonstrates a simpler tenant design with an equally strong boundary.

## Cloudflare configuration

### Tunnel

- Run `cloudflared` as a pinned container or pinned host service.
- Use an outbound-only named tunnel.
- Publish `observe.yanelmo.net` to the internal shared Grafana service.
- Do not expose shared Grafana on `0.0.0.0` at the host.
- Keep the tunnel token/credentials outside Git.
- Enable Access protection for the published application.
- Where supported by the chosen tunnel-management mode, require `cloudflared` to validate the Access JWT/AUD before proxying.

### Access application

Create a self-hosted Access application for exactly `observe.yanelmo.net`.

Initial policy:

- action: `Allow`;
- include: exact approved user email addresses;
- authentication: individual identity through Cloudflare Access, such as email one-time PIN or a configured identity provider;
- no `Everyone` rule;
- no bypass policy;
- no shared account;
- session duration selected deliberately and documented locally.

Adding or removing a user from the Access policy controls whether the user can reach Grafana at all.

## Grafana authentication

Use Grafana auth-proxy mode with the Access identity header:

```ini
[users]
allow_sign_up = false
auto_assign_org = true
auto_assign_org_role = Viewer

[auth.proxy]
enabled = true
header_name = Cf-Access-Authenticated-User-Email
header_property = email
auto_sign_up = true
sync_ttl = 0
```

Equivalent `GF_*` environment variables may be used in Compose.

Additional requirements:

- Set `root_url` to `https://observe.yanelmo.net`.
- Default every auto-created account to `Viewer`.
- Keep the built-in local admin as a break-glass account with a strong secret.
- Promote the owner's Access-backed email account to organization/Grafana administrator after its first login.
- Never map an Access-provided header directly to an Admin role.
- Restrict auth-proxy requests to the dedicated `cloudflared` container/network using Grafana's proxy whitelist or an equivalent fixed trusted-proxy boundary.
- Keep the shared Grafana and `cloudflared` on a dedicated internal Docker network containing no unrelated workloads.

## Account and team model

Recommended accounts:

- owner: Grafana/organization administrator;
- all approved Discord users: Viewer;
- optional `discord-viewers` team: Viewer permission on the shared dashboard folder.

Automatic IdP group-to-team synchronization is not assumed. Add users to Grafana teams manually after first login unless a reviewed supported mechanism is introduced.

## Shared dashboards

The shared stack may show:

- Hermes total token usage;
- usage grouped by `user.id=discord:<sender_id>`;
- model/provider breakdown;
- input/output/cache/reasoning breakdown;
- request count, errors and duration;
- main versus owashota instance.

It must not receive or display:

- personal Codex CLI/desktop telemetry;
- server or Windows host telemetry;
- prompts or responses;
- conversation history;
- tool arguments/results;
- general logs;
- secrets or private network details.

Friendly Discord names may be applied only through ignored/private provisioning. Never commit the ID-to-name mapping.

## Break-glass access

Document a recovery path that does not depend on Cloudflare:

- shared Grafana is reachable only from the server itself or through an SSH port forward;
- the local admin credential is stored in a local secret manager/file excluded from Git;
- disabling auth proxy or resetting the administrator is documented;
- deleting the Access application or tunnel cannot lock the owner out of the underlying data.

## Verification checklist

- [ ] `observe.yanelmo.net` resolves through the named Cloudflare tunnel.
- [ ] No router port-forwarding rule exists.
- [ ] An unapproved email is denied by Cloudflare Access.
- [ ] Each approved email creates a distinct Grafana user.
- [ ] New users receive Viewer, never Editor/Admin.
- [ ] The owner account has Admin.
- [ ] A Viewer can open the shared Hermes dashboards.
- [ ] The shared Grafana contains no Codex/private/server data source.
- [ ] A Viewer cannot reach the private Grafana through the tunnel.
- [ ] Direct requests without Access identity cannot impersonate another user.
- [ ] Removing an email from Access prevents the next authenticated session.
- [ ] Cloudflare/tunnel failure does not interrupt telemetry ingestion or Hermes/Codex operation.
- [ ] Local break-glass administration works.
