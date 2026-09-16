param([string]$RuntimeDirectory="$env:USERPROFILE\AIUsage")
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath($RuntimeDirectory)
@{enabled=$false} | ConvertTo-Json | Set-Content -Encoding utf8 "$root/control.local.json"
foreach ($file in @('supervisor.local.json','tunnel.local.json')) {
  if (Test-Path "$root/$file") {
    $record=Get-Content -Raw "$root/$file" | ConvertFrom-Json
    $p=Get-Process -Id $record.pid -ErrorAction SilentlyContinue
    if ($p -and $p.Path -eq $record.exe -and $p.StartTime.ToUniversalTime() -eq ([datetime]$record.started).ToUniversalTime()) { Stop-Process -Id $p.Id }
  }
}
$records=Get-Content -Raw "$root/processes.local.json" | ConvertFrom-Json
foreach ($name in @('grafana','collector','receiver')) {
  $record=$records.$name
  $p=Get-Process -Id $record.pid -ErrorAction SilentlyContinue
  if (-not $p) { continue }
  if ($p.Path -ne $record.exe -or $p.StartTime.ToUniversalTime() -ne ([datetime]$record.started).ToUniversalTime()) {
    throw "$name PID no longer belongs to the recorded process; nothing stopped"
  }
  Stop-Process -Id $p.Id
}
& "$root/bin/postgres-17.11/pgsql/bin/pg_ctl.exe" stop -D "$root/postgres" -m fast -w
if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL stop failed' }
Write-Output 'Portable processes stopped; database and durable queue preserved.'
