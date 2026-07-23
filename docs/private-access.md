# Owner-only private Grafana access

## Goal

Publish the private Grafana web UI at:

```text
https://private-observe.yanelmo.net
```

This is an owner-only convenience route. It does not change where telemetry is
collected or stored. OTLP, Prometheus, Tempo, Loki, collector health, Docker,
and host administration remain private and have no Cloudflare or router route.

## Hard boundary

Use a dedicated, remotely managed named tunnel:

```text
local-observability-private
```

Its only published application route is:

```text
private-observe.yanelmo.net -> http://private-lgtm:3000
```

The `private-cloudflared` container joins only `private-admin`. The existing
`cloudflared` container continues to join only `shared-proxy` and continues to
serve `observe.yanelmo.net -> http://shared-lgtm:3000`.

Do not combine the two connectors. A connector that can reach both Grafana
origins would weaken the private/shared network boundary.

## Access application

Create a separate self-hosted Access application for exactly
`private-observe.yanelmo.net`.

- Policy action: `Allow`.
- Include rule: the owner's exact email only, entered directly in Cloudflare.
- Session duration: deliberately approved by the owner; initially mirror the
  existing observability application unless the owner chooses otherwise.
- Login methods: Google and One-time PIN.
- Instant authentication: off.
- Forbidden selectors: `Everyone`, email domain, group, account member,
  broad allow, bypass, or service-token access.
- Protect the route with Access before starting its connector.
- Require `cloudflared` origin-side Access token validation where the dashboard
  exposes that option.

The approved email, application/tunnel identifiers, Access AUD, and token stay
outside Git and chat.

Private Grafana keeps its existing Grafana login as a second layer. Do not
enable auth proxy for the private stack. The localhost/SSH route and local
Grafana administrator remain the Cloudflare-independent break-glass path.

## Prepared runtime

Initialize ignored local files:

```bash
./scripts/init-local-env.sh
```

After the owner creates the named tunnel, retrieve and transfer its token
without displaying it:

```powershell
pwsh -File scripts/store-cloudflare-tunnel-token.ps1 `
  -TunnelName local-observability-private `
  -RemoteTokenFileName cloudflare-private-tunnel.token `
  -RemoteRepoName local-obserbablity-private-access
```

Start only after the Access application and route are protected:

```bash
./scripts/stack.sh private-access-up
./scripts/stack.sh status
./scripts/stack.sh logs private-cloudflared
VERIFY_PUBLIC=1 ./scripts/verify-private-access.sh
```

## Verification

1. Unauthenticated requests to both hostnames redirect to Cloudflare Access.
2. The private login page offers only Google and OTP.
3. The owner's approved identity reaches Grafana and still must authenticate to
   private Grafana.
4. An unapproved identity is denied before Grafana.
5. The private connector has only `private-admin`; the shared connector has
   only `shared-proxy`.
6. Shared Grafana has no private data source and returns no Codex, host,
   container, Windows, or OpenCode telemetry.
7. Stopping either connector affects only its matching web route and does not
   affect agents, collectors, storage, or the other connector.
8. Localhost or SSH-forwarded private Grafana remains usable with
   `private-cloudflared` stopped.

## Rollback

Immediate, non-destructive rollback:

```bash
./scripts/stack.sh private-access-stop
```

Then remove or disable, in this order:

1. the `private-observe.yanelmo.net` published application route;
2. its exact-host Access application;
3. the `local-observability-private` tunnel after confirming no connector uses
   it.

Remove the private DNS record created by the route if Cloudflare does not remove
it automatically. Do not delete the shared application, shared tunnel, private
Grafana data, or local break-glass account.
