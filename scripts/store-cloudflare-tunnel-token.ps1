[CmdletBinding()]
param(
    [string]$WranglerVersion = '4.112.0',
    [string]$ZoneName = 'yanelmo.net',
    [string]$TunnelName = 'local-observability-shared',
    [string]$RemoteTokenFileName = 'cloudflare-tunnel.token',
    [string]$RemoteRepoName = 'local-obserbablity',
    [string]$SshHost = 'yanelmoserver'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

if ($WranglerVersion -notmatch '^\d+\.\d+\.\d+$') {
    throw 'WranglerVersion must be an exact semantic version.'
}
if ($RemoteTokenFileName -notmatch '^[a-z0-9][a-z0-9.-]*\.token$') {
    throw 'RemoteTokenFileName must be a simple lowercase .token filename.'
}
if ($RemoteRepoName -notmatch '^[a-z0-9][a-z0-9.-]*$') {
    throw 'RemoteRepoName must be a simple lowercase directory name.'
}

$apiBearer = $null
$tunnelToken = $null

try {
    $wranglerPackage = "wrangler@$WranglerVersion"
    $authRaw = (& npx --yes $wranglerPackage auth token --json 2>$null | Out-String)
    if ($LASTEXITCODE -ne 0) {
        throw 'Wrangler authentication is unavailable. Run wrangler login first.'
    }

    $jsonStart = $authRaw.IndexOf('{')
    $jsonEnd = $authRaw.LastIndexOf('}')
    if ($jsonStart -lt 0 -or $jsonEnd -le $jsonStart) {
        throw 'Wrangler did not return a valid authentication response.'
    }

    $authObject = $authRaw.Substring($jsonStart, $jsonEnd - $jsonStart + 1) | ConvertFrom-Json
    $apiBearer = [string]$authObject.token
    if ([string]::IsNullOrWhiteSpace($apiBearer)) {
        throw 'Wrangler returned no OAuth token.'
    }

    $headers = @{ Authorization = "Bearer $apiBearer" }
    try {
        $accounts = Invoke-RestMethod -Method Get -Uri 'https://api.cloudflare.com/client/v4/accounts?per_page=50' -Headers $headers
    }
    catch {
        throw 'Cloudflare account lookup failed.'
    }

    if (-not $accounts.success) {
        throw 'Cloudflare account lookup failed.'
    }

    $tunnelMatches = @()
    foreach ($account in @($accounts.result)) {
        $accountId = [string]$account.id
        $escapedAccountId = [uri]::EscapeDataString($accountId)

        try {
            $zoneUri = 'https://api.cloudflare.com/client/v4/zones?name=' +
                [uri]::EscapeDataString($ZoneName) +
                '&status=active&account.id=' + $escapedAccountId
            $zones = Invoke-RestMethod -Method Get -Uri $zoneUri -Headers $headers
        }
        catch {
            continue
        }

        if (-not $zones.success -or @($zones.result).Count -ne 1) {
            continue
        }

        try {
            $tunnelUri = 'https://api.cloudflare.com/client/v4/accounts/' + $escapedAccountId +
                '/cfd_tunnel?is_deleted=false&name=' + [uri]::EscapeDataString($TunnelName)
            $tunnels = Invoke-RestMethod -Method Get -Uri $tunnelUri -Headers $headers
        }
        catch {
            continue
        }

        if (-not $tunnels.success) {
            continue
        }

        foreach ($tunnel in @($tunnels.result)) {
            if ([string]$tunnel.name -eq $TunnelName -and [bool]$tunnel.remote_config) {
                $tunnelMatches += [pscustomobject]@{
                    AccountId = $accountId
                    TunnelId = [string]$tunnel.id
                }
            }
        }
    }

    if ($tunnelMatches.Count -ne 1) {
        throw "Expected one remotely managed '$TunnelName' tunnel in the '$ZoneName' account; found $($tunnelMatches.Count)."
    }

    $selected = $tunnelMatches[0]
    try {
        $tokenUri = 'https://api.cloudflare.com/client/v4/accounts/' +
            [uri]::EscapeDataString($selected.AccountId) + '/cfd_tunnel/' +
            [uri]::EscapeDataString($selected.TunnelId) + '/token'
        $tokenResponse = Invoke-RestMethod -Method Get -Uri $tokenUri -Headers $headers
    }
    catch {
        throw 'Cloudflare Tunnel token lookup failed.'
    }

    if (-not $tokenResponse.success) {
        throw 'Cloudflare Tunnel token lookup failed.'
    }

    $tunnelToken = [string]$tokenResponse.result
    if ([string]::IsNullOrWhiteSpace($tunnelToken) -or $tunnelToken.Length -lt 50) {
        throw 'Cloudflare returned an invalid Tunnel token.'
    }

    $remoteCommand = @'
set -euo pipefail
repo="$HOME/repo/__REPO_NAME__"
dest="$repo/secrets/__TOKEN_FILE_NAME__"
test -d "$repo/secrets"
if [ -s "$dest" ]; then
  echo TOKEN_DEST_ALREADY_NONEMPTY
  exit 23
fi
tmp=$(mktemp "$repo/secrets/.cloudflare-tunnel.token.XXXXXX")
cleanup() { rm -f -- "$tmp"; }
trap cleanup EXIT
cat > "$tmp"
test -s "$tmp"
chmod 600 "$tmp"
mv -- "$tmp" "$dest"
trap - EXIT
test "$(stat -c %a "$dest")" = 600
echo TOKEN_FILE_WRITTEN
'@
    $remoteCommand = $remoteCommand.Replace('__REPO_NAME__', $RemoteRepoName)
    $remoteCommand = $remoteCommand.Replace('__TOKEN_FILE_NAME__', $RemoteTokenFileName)

    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = 'ssh'
    $null = $startInfo.ArgumentList.Add($SshHost)
    $null = $startInfo.ArgumentList.Add($remoteCommand)
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardInput = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true

    $sshProcess = [System.Diagnostics.Process]::new()
    $sshProcess.StartInfo = $startInfo
    if (-not $sshProcess.Start()) {
        throw 'Could not start SSH.'
    }

    $stdoutTask = $sshProcess.StandardOutput.ReadToEndAsync()
    $stderrTask = $sshProcess.StandardError.ReadToEndAsync()
    $sshProcess.StandardInput.Write($tunnelToken)
    $sshProcess.StandardInput.Close()
    $sshProcess.WaitForExit()
    $remoteOutput = $stdoutTask.GetAwaiter().GetResult()
    $null = $stderrTask.GetAwaiter().GetResult()

    if ($sshProcess.ExitCode -eq 23) {
        throw 'The remote Tunnel token file is already non-empty; refusing to overwrite it.'
    }
    if ($sshProcess.ExitCode -ne 0 -or $remoteOutput -notmatch 'TOKEN_FILE_WRITTEN') {
        throw "Secure Tunnel token transfer failed with SSH exit $($sshProcess.ExitCode)."
    }

    Write-Output 'Tunnel token saved to the server with mode 0600. The connector was not started.'
}
finally {
    $apiBearer = $null
    $tunnelToken = $null
}
