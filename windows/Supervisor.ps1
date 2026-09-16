param([string]$RuntimeDirectory="$env:USERPROFILE\AIUsage")
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath($RuntimeDirectory)
$mutex=[Threading.Mutex]::new($false,'Local\AIUsageSupervisor')
if (-not $mutex.WaitOne(0)) { exit }
$me=Get-Process -Id $PID
@{pid=$PID;exe=$me.Path;started=$me.StartTime.ToUniversalTime().ToString('o')} | ConvertTo-Json | Set-Content -Encoding utf8 "$root/supervisor.local.json"
function Save-Process($process,$path) {
  @{pid=$process.Id;exe=$process.Path;started=$process.StartTime.ToUniversalTime().ToString('o')} | ConvertTo-Json | Set-Content -Encoding utf8 $path
}
try {
  while ((Get-Content -Raw "$root/control.local.json" | ConvertFrom-Json).enabled) {
    try {
      $ready=$true
      foreach ($url in @('http://127.0.0.1:14320/health','http://127.0.0.1:14333/','http://127.0.0.1:13002/api/health')) {
        try { $null=Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 3 } catch { $ready=$false }
      }
      if (-not $ready) { & "$root/source/Start-NativeUsage.ps1" -RuntimeDirectory $root | Out-Null }
      if (Test-Path "$root/connection.local.json") {
        $connection=Get-Content -Raw "$root/connection.local.json" | ConvertFrom-Json
        $alive=$false
        if (Test-Path "$root/tunnel.local.json") {
          $record=Get-Content -Raw "$root/tunnel.local.json" | ConvertFrom-Json
          $p=Get-Process -Id $record.pid -ErrorAction SilentlyContinue
          $alive=$p -and $p.Path -eq $record.exe -and $p.StartTime.ToUniversalTime() -eq ([datetime]$record.started).ToUniversalTime()
        }
        if (-not $alive) {
          if ($connection.SshHost -notmatch '^[A-Za-z0-9_.@-]+$' -or $connection.RemoteSocket -notmatch '^/[A-Za-z0-9_./-]+/otlp\.sock$') { throw 'Invalid private SSH connection configuration' }
          & ssh -o BatchMode=yes -o ConnectTimeout=5 $connection.SshHost python3 .config/ai-usage/docker/prepare-socket.py $connection.RemoteSocket | Out-Null
          if ($LASTEXITCODE -ne 0) { throw 'Remote socket was not ready; active or unexpected endpoint preserved' }
          $tunnelArguments=@('-N','-T','-o','BatchMode=yes','-o','ConnectTimeout=5','-o','ExitOnForwardFailure=yes','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3','-o','StreamLocalBindUnlink=yes','-R',"$($connection.RemoteSocket):127.0.0.1:14317",$connection.SshHost)
          $p=Start-Process ssh -ArgumentList $tunnelArguments -WindowStyle Hidden -PassThru -RedirectStandardError "$root/logs/tunnel.err.log"
          Start-Sleep -Milliseconds 300
          if ($p.HasExited) { throw 'SSH tunnel startup failed; inspect the private error log' }
          Save-Process $p "$root/tunnel.local.json"
        }
      }
      $env:USAGE_RUNTIME_DIR=$root
      & "$root/python/Scripts/python.exe" "$root/source/status.py" --record | Set-Content -Encoding utf8 "$root/health.local.json"
    } catch {
      # Do not dump process arguments, environment, credentials or remote output.
      @{at=(Get-Date).ToUniversalTime().ToString('o');healthy=$false;error_type=$_.Exception.GetType().Name} | ConvertTo-Json | Set-Content "$root/supervisor-health.local.json"
    }
    Start-Sleep -Seconds 30
  }
} finally { $mutex.ReleaseMutex();$mutex.Dispose() }
