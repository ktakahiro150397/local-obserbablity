param([string]$RuntimeDirectory="$env:USERPROFILE\AIUsage",[switch]$AtLogin)
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath($RuntimeDirectory)
@{enabled=$true} | ConvertTo-Json | Set-Content -Encoding utf8 "$root/control.local.json"
$shell=(Get-Command powershell.exe).Source
Start-Process $shell -WindowStyle Hidden -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+$root+'/source/Supervisor.ps1"'),'-RuntimeDirectory',('"'+$root+'"'))
if ($AtLogin) {
  $startup=[Environment]::GetFolderPath('Startup')
  $link=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $startup 'Private AI Usage.lnk'))
  $link.TargetPath=$shell
  $link.Arguments='-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "'+$root+'/source/Start-UsageSupervisor.ps1" -RuntimeDirectory "'+$root+'"'
  $link.WindowStyle=7
  $link.Save()
}
Write-Output 'User-session supervisor started. Login startup is opt-in; no Windows service installed.'
