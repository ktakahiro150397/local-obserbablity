param([string]$SecretDirectory = "$env:USERPROFILE\AIUsage\secrets")
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path $SecretDirectory | Out-Null
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
& icacls $SecretDirectory /inheritance:r /grant:r "${identity}:(OI)(CI)F" 'SYSTEM:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Failed to restrict the secret directory' }
foreach ($name in @('admin','writer','grafana','ui')) {
  $path = Join-Path $SecretDirectory $name
  if (-not (Test-Path -LiteralPath $path)) {
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($bytes)
    $rng.Dispose()
    [System.IO.File]::WriteAllText($path, [Convert]::ToBase64String($bytes))
  }
}
$env:USAGE_SECRETS_DIR = $SecretDirectory.Replace('\','/')
Write-Output 'Private credentials prepared. Existing values preserved; no credentials printed.'
