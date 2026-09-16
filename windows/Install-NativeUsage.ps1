param([string]$RuntimeDirectory="$env:USERPROFILE\AIUsage",[string]$Python='python')
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath($RuntimeDirectory)
New-Item -ItemType Directory -Force -Path "$root/downloads","$root/bin/otel","$root/bin/grafana-13.2.2","$root/bin/postgres-17.11" | Out-Null
$manifest=Get-Content -Raw "$PSScriptRoot/versions.json" | ConvertFrom-Json
foreach ($entry in $manifest.PSObject.Properties) {
  $package=$entry.Value
  $archive=Join-Path "$root/downloads" $package.file
  if (-not (Test-Path -LiteralPath $archive)) { Invoke-WebRequest $package.url -OutFile $archive }
  if ((Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash.ToLowerInvariant() -ne $package.sha256) {
    throw "Checksum mismatch: $($entry.Name); archive preserved for diagnosis"
  }
}
if (-not (Test-Path "$root/bin/postgres-17.11/pgsql/bin/postgres.exe")) {
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  $zip=[IO.Compression.ZipFile]::OpenRead("$root/downloads/postgresql-17.11.zip")
  try {
    foreach ($entry in $zip.Entries) {
      if ($entry.FullName -notmatch '^pgsql/(bin|lib|share)/' -or -not $entry.Name) { continue }
      $target=[IO.Path]::GetFullPath((Join-Path "$root/bin/postgres-17.11" $entry.FullName))
      if (-not $target.StartsWith([IO.Path]::GetFullPath("$root/bin/postgres-17.11")+[IO.Path]::DirectorySeparatorChar)) { throw 'Unsafe archive path' }
      New-Item -ItemType Directory -Force -Path (Split-Path $target) | Out-Null
      [IO.Compression.ZipFileExtensions]::ExtractToFile($entry,$target,$false)
    }
  } finally { $zip.Dispose() }
}
foreach ($spec in @(
  @{Exe="$root/bin/otel/otelcol-contrib.exe";Archive=$manifest.collector.file;Directory="$root/bin/otel"},
  @{Exe="$root/bin/grafana-13.2.2/grafana-13.2.2/bin/grafana.exe";Archive=$manifest.grafana.file;Directory="$root/bin/grafana-13.2.2"}
)) {
  if (-not (Test-Path $spec.Exe)) {
    & tar -xzf "$root/downloads/$($spec.Archive)" -C $spec.Directory
    if ($LASTEXITCODE -ne 0) { throw 'Archive extraction failed' }
  }
}
if (-not (Test-Path "$root/python/Scripts/python.exe")) {
  & $Python -m venv "$root/python"
  if ($LASTEXITCODE -ne 0) { throw 'Python venv creation failed' }
}
& "$root/python/Scripts/python.exe" -m pip install --disable-pip-version-check 'psycopg[binary]==3.3.4' 'PyYAML==6.0.3'
if ($LASTEXITCODE -ne 0) { throw 'Python dependency install failed' }
if ([IO.Path]::GetFullPath($PSScriptRoot) -ne [IO.Path]::GetFullPath("$root/source")) {
  New-Item -ItemType Directory -Force -Path "$root/source" | Out-Null
  Copy-Item "$PSScriptRoot/*" "$root/source" -Recurse -Force
}
& "$root/source/Start-NativeUsage.ps1" -RuntimeDirectory $root
