[CmdletBinding()]
param(
    [string]$CodexHome = $(
        if ($env:CODEX_HOME) { $env:CODEX_HOME }
        else { Join-Path $env:USERPROFILE '.codex' }
    )
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$configPath = Join-Path $CodexHome 'config.toml'
if (-not (Test-Path -LiteralPath $configPath)) {
    throw 'Codex user config.toml was not found.'
}

$config = Get-Content -LiteralPath $configPath -Raw
$checks = @(
    '(?m)^\s*\[otel\]\s*$',
    '(?m)^\s*log_user_prompt\s*=\s*false\s*$',
    '(?m)^\s*exporter\s*=\s*"none"\s*$',
    '(?m)^\s*\[otel\.metrics_exporter\."otlp-http"\]\s*$',
    '(?m)^\s*endpoint\s*=\s*"https?://[^"/]+(?::\d+)?/v1/metrics"\s*$',
    '(?m)^\s*\[otel\.trace_exporter\."otlp-http"\]\s*$'
)
foreach ($pattern in $checks) {
    if ($config -notmatch $pattern) {
        throw 'Codex OTel configuration is incomplete or malformed.'
    }
}
if ($config -notmatch '(?m)^\s*endpoint\s*=\s*"https?://[^"/]+(?::\d+)?/v1/traces"\s*$') {
    throw 'Codex trace exporter endpoint is missing.'
}
if ($config -match '(?i)observe\.yanelmo\.net' -or $config -match '(?m)^\s*log_user_prompt\s*=\s*true\s*$') {
    throw 'Unsafe Codex telemetry routing or prompt logging was detected.'
}

$previousCodexHome = $env:CODEX_HOME
try {
    $env:CODEX_HOME = $CodexHome
    & codex features list 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Codex rejected config.toml (exit $LASTEXITCODE)."
    }
} finally {
    $env:CODEX_HOME = $previousCodexHome
}

Write-Output 'Codex telemetry configuration is syntactically valid and content export remains disabled.'
Write-Output 'This check does not replace the real CLI and desktop trace verification in H8.'
