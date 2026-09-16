param(
  [string]$RuntimeDirectory = "$env:USERPROFILE\AIUsage",
  [string]$PythonPath,
  [string]$GrafanaHome
)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath($RuntimeDirectory)
if (-not $PythonPath) { $PythonPath="$root/python/Scripts/python.exe" }
if (-not $GrafanaHome) { $GrafanaHome="$root/bin/grafana-13.2.2/grafana-13.2.2" }
New-Item -ItemType Directory -Force -Path $root | Out-Null
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
& icacls $root /inheritance:r /grant:r "${identity}:(OI)(CI)F" 'SYSTEM:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Failed to restrict runtime storage' }
New-Item -ItemType Directory -Force -Path "$root/logs" | Out-Null
$pg = Join-Path $root 'bin/postgres-17.11/pgsql/bin'
. "$PSScriptRoot/Initialize-Usage.ps1" -SecretDirectory "$root/secrets"
if (-not (Test-Path -LiteralPath "$root/postgres/PG_VERSION")) {
  & "$pg/initdb.exe" -D "$root/postgres" --username=ledger_admin --auth=scram-sha-256 --encoding=UTF8 --no-locale --data-checksums --pwfile="$root/secrets/admin"
  if ($LASTEXITCODE -ne 0) { throw 'initdb failed; no existing cluster changed' }
  @'
listen_addresses = '127.0.0.1'
port = 15432
shared_buffers = '64MB'
max_connections = 30
work_mem = '4MB'
log_statement = 'none'
log_min_error_statement = 'panic'
log_parameter_max_length_on_error = 0
'@ | Add-Content -LiteralPath "$root/postgres/postgresql.conf"
}
& "$pg/pg_ctl.exe" status -D "$root/postgres" | Out-Null
if ($LASTEXITCODE -ne 0) {
  $pgStart = Start-Process -FilePath "$pg/pg_ctl.exe" -ArgumentList @('start','-D',('"'+$root+'/postgres"'),'-l',('"'+$root+'/logs/postgres.log"'),'-w') -WindowStyle Hidden -PassThru
  $pgStart.WaitForExit()
  if ($pgStart.ExitCode -ne 0) { throw 'PostgreSQL start failed' }
}
$env:USAGE_RUNTIME_DIR=$root
& $PythonPath "$PSScriptRoot/configure_native.py"
if ($LASTEXITCODE -ne 0) { throw 'Native config failed' }
& "$root/bin/otel/otelcol-contrib.exe" validate --config="$root/collector.yaml"
if ($LASTEXITCODE -ne 0) { throw 'Collector validation failed' }
$env:PGHOST='127.0.0.1'; $env:PGPORT='15432'; $env:PGPASSWORD_FILE="$root/secrets/writer"
$env:LISTEN_HOST='127.0.0.1'; $env:LISTEN_PORT='14320'
$env:GOMEMLIMIT='160MiB'
$processes = @{}
if (Test-Path -LiteralPath "$root/processes.local.json") {
  $saved = Get-Content -Raw "$root/processes.local.json" | ConvertFrom-Json
  foreach ($property in $saved.PSObject.Properties) { $processes[$property.Name]=$property.Value }
}
foreach ($spec in @(
  @{Name='receiver'; File=$PythonPath; Args=@(('"'+$root+'/app/receiver.py"')); Port=14320},
  @{Name='collector'; File="$root/bin/otel/otelcol-contrib.exe"; Args=@('--config',('"'+$root+'/collector.yaml"')); Port=14318},
  @{Name='grafana'; File="$GrafanaHome/bin/grafana.exe"; Args=@('server','--homepath',('"'+$GrafanaHome+'"'),'--config',('"'+$root+'/grafana.ini"')); Port=13002}
)) {
  $listener = Get-NetTCPConnection -State Listen -LocalPort $spec.Port -ErrorAction SilentlyContinue
  if ($listener) {
    $record = $processes[$spec.Name]
    $owned = $record -and ($listener.OwningProcess -contains $record.pid)
    if ($record -and -not $owned) {
      $child = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener[0].OwningProcess)"
      $owned = $child.ParentProcessId -eq $record.pid
    }
    if (-not $owned) { throw "Port $($spec.Port) is owned by an unrecorded process; nothing stopped" }
    $actual=Get-Process -Id $listener[0].OwningProcess
    $processes[$spec.Name]=@{pid=$actual.Id;exe=$actual.Path;started=$actual.StartTime.ToUniversalTime().ToString('o')}
    Write-Output ($spec.Name + ' already listening; preserved')
    continue
  }
  $p = Start-Process -FilePath $spec.File -ArgumentList $spec.Args -WindowStyle Hidden -PassThru -RedirectStandardOutput "$root/logs/$($spec.Name).out.log" -RedirectStandardError "$root/logs/$($spec.Name).err.log"
  for ($attempt=0; $attempt -lt 50; $attempt++) {
    $listener=Get-NetTCPConnection -State Listen -LocalPort $spec.Port -ErrorAction SilentlyContinue
    if ($listener) { break }
    Start-Sleep -Milliseconds 200
  }
  if (-not $listener) { throw "$($spec.Name) did not listen; inspect its private error log" }
  $actual=Get-Process -Id $listener[0].OwningProcess
  $processes[$spec.Name]=@{pid=$actual.Id;exe=$actual.Path;started=$actual.StartTime.ToUniversalTime().ToString('o')}
}
$processes | ConvertTo-Json | Set-Content -Encoding utf8 "$root/processes.local.json"
Write-Output 'Portable processes started; verify health before routing producers.'
