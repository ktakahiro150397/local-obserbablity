[CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
param(
    [Parameter(Mandatory)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$BackupPath,

    [string]$CodexHome = $(
        if ($env:CODEX_HOME) { $env:CODEX_HOME }
        else { Join-Path $env:USERPROFILE '.codex' }
    )
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$configPath = Join-Path $CodexHome 'config.toml'
if (-not $PSCmdlet.ShouldProcess($configPath, "Restore from $BackupPath")) {
    return
}

if (Test-Path -LiteralPath $configPath) {
    $safetyCopy = "$configPath.before-restore.$(Get-Date -Format 'yyyyMMddTHHmmss')"
    Copy-Item -LiteralPath $configPath -Destination $safetyCopy
}
Copy-Item -LiteralPath $BackupPath -Destination $configPath -Force

$previousCodexHome = $env:CODEX_HOME
try {
    $env:CODEX_HOME = $CodexHome
    & codex features list 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Restored Codex configuration is invalid.' }
} finally {
    $env:CODEX_HOME = $previousCodexHome
}

Write-Output 'Codex configuration restored. Fully restart Codex desktop before testing.'
