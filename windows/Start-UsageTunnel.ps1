param([Parameter(Mandatory)][string]$SshHost,[Parameter(Mandatory)][string]$RemoteSocket)
$ErrorActionPreference = 'Stop'
if ($SshHost -notmatch '^[A-Za-z0-9_.@-]+$') { throw 'Use a configured SSH host alias' }
if ($RemoteSocket -notmatch '^/[A-Za-z0-9_./-]+/otlp\.sock$') { throw 'Use the prepared private socket path' }
& ssh -o BatchMode=yes -o ConnectTimeout=5 $SshHost python3 .config/ai-usage/docker/prepare-socket.py $RemoteSocket
if ($LASTEXITCODE -ne 0) { throw 'Remote socket not ready; no active endpoint was replaced' }
# Server listens only on an owner-private Unix socket shared with forwarder.
# No Windows ingress firewall rule, public binding or router change is needed.
& ssh -N -T -o BatchMode=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -o StreamLocalBindUnlink=yes -R "${RemoteSocket}:127.0.0.1:14317" $SshHost
