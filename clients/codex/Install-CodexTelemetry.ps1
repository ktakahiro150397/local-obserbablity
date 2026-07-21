[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$EndpointBase,

    [string]$CodexHome = $(
        if ($env:CODEX_HOME) { $env:CODEX_HOME }
        else { Join-Path $env:USERPROFILE '.codex' }
    ),

    [switch]$SkipCodexValidation
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

try {
    $endpoint = [Uri]$EndpointBase
} catch {
    throw 'EndpointBase must be an absolute HTTP(S) URI without a signal path.'
}

if (-not $endpoint.IsAbsoluteUri -or $endpoint.Scheme -notin @('http', 'https')) {
    throw 'EndpointBase must be an absolute HTTP(S) URI.'
}
if ($endpoint.Host -ieq 'observe.yanelmo.net') {
    throw 'Codex telemetry must use the private collector, never the shared public hostname.'
}
if (($endpoint.AbsolutePath -ne '/') -or $endpoint.Query -or $endpoint.Fragment) {
    throw 'EndpointBase must not include a path, query, or fragment.'
}

$base = $EndpointBase.TrimEnd('/')
$configPath = Join-Path $CodexHome 'config.toml'
$timestamp = Get-Date -Format 'yyyyMMddTHHmmss'
$backupPath = "$configPath.phase1-backup.$timestamp"
$hadConfig = Test-Path -LiteralPath $configPath

function Remove-OtelTables {
    param([string]$Text)

    $kept = [System.Collections.Generic.List[string]]::new()
    $skip = $false
    foreach ($line in [regex]::Split($Text, '\r?\n')) {
        if ($line -match '^\s*\[([^\]]+)\]\s*(?:#.*)?$') {
            $table = $Matches[1].Trim()
            $skip = ($table -eq 'otel' -or $table.StartsWith('otel.', [StringComparison]::Ordinal))
        }
        if (-not $skip) {
            $kept.Add($line)
        }
    }
    return ($kept -join [Environment]::NewLine).TrimEnd()
}

function ConvertTo-TomlBasicString {
    param([string]$Value)
    return $Value.Replace('\', '\\').Replace('"', '\"')
}

if (-not $PSCmdlet.ShouldProcess($configPath, 'Back up and merge Codex OpenTelemetry settings')) {
    return
}

New-Item -ItemType Directory -Path $CodexHome -Force | Out-Null
$existing = if ($hadConfig) { Get-Content -LiteralPath $configPath -Raw } else { '' }
if ($hadConfig) {
    Copy-Item -LiteralPath $configPath -Destination $backupPath
}

$preserved = Remove-OtelTables -Text $existing
$preserved = ($preserved -replace '(?m)^# Phase 1 local observability\. Managed by Install-CodexTelemetry\.ps1\.\r?\n?', '').TrimEnd()
$metricsEndpoint = ConvertTo-TomlBasicString "$base/v1/metrics"
$traceEndpoint = ConvertTo-TomlBasicString "$base/v1/traces"
$block = @"
# Phase 1 local observability. Managed by Install-CodexTelemetry.ps1.
[otel]
environment = "home"
log_user_prompt = false
exporter = "none"

[otel.metrics_exporter."otlp-http"]
endpoint = "$metricsEndpoint"
protocol = "binary"

[otel.trace_exporter."otlp-http"]
endpoint = "$traceEndpoint"
protocol = "binary"
"@

$merged = if ($preserved) {
    $preserved + [Environment]::NewLine + [Environment]::NewLine + $block.Trim() + [Environment]::NewLine
} else {
    $block.Trim() + [Environment]::NewLine
}

$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText($configPath, $merged, $utf8NoBom)

try {
    if (-not $SkipCodexValidation) {
        if (-not (Get-Command codex -ErrorAction SilentlyContinue)) {
            throw 'codex was not found; rerun with -SkipCodexValidation only for offline preparation.'
        }
        $previousCodexHome = $env:CODEX_HOME
        try {
            $env:CODEX_HOME = $CodexHome
            & codex features list 2>&1 | Out-Null
            if ($LASTEXITCODE -ne 0) {
                throw "Codex rejected the merged configuration (exit $LASTEXITCODE)."
            }
        } finally {
            $env:CODEX_HOME = $previousCodexHome
        }
    }
} catch {
    if ($hadConfig) {
        Copy-Item -LiteralPath $backupPath -Destination $configPath -Force
    } else {
        Remove-Item -LiteralPath $configPath -Force
    }
    throw "Configuration validation failed and the original was restored. $($_.Exception.Message)"
}

Write-Output 'Codex user configuration merged and validated; unrelated settings were preserved.'
if ($hadConfig) {
    Write-Output "Rollback backup: $backupPath"
}
Write-Output 'A full Codex desktop restart remains required at H8.'
