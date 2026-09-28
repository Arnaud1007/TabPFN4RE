$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Raw | ConvertFrom-Json
$snapshot = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'snapshot.json') -Raw | ConvertFrom-Json
$verification = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'verification.json') -Raw | ConvertFrom-Json

if ($manifest.environment_lock_path -ne 'locks/nyc-capture-environment.json') {
    throw 'Unexpected environment lock path'
}
$lockPath = Join-Path $projectRoot $manifest.environment_lock_path
$lockHash = (Get-FileHash -LiteralPath $lockPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($lockHash -ne $manifest.environment_lock_sha256) {
    throw 'Environment lock hash mismatch'
}

$verifiedCount = 0
foreach ($item in $manifest.immutable_run_files_sha256.PSObject.Properties) {
    $path = Join-Path $projectRoot $item.Name
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing immutable run file: $($item.Name)"
    }
    $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $item.Value) {
        throw "Immutable run file hash mismatch: $($item.Name)"
    }
    $verifiedCount++
}

$rawName = [string]$snapshot.raw_filename
if ($rawName -ne [IO.Path]::GetFileName($rawName)) {
    throw 'Snapshot filename is not a basename'
}
$rawPath = Join-Path $projectRoot (Join-Path 'data\raw\nyc_dof' $rawName)
if (-not (Test-Path -LiteralPath $rawPath -PathType Leaf)) {
    throw 'Private snapshot is unavailable; obtain the authorised source file before replay'
}
$rawHash = (Get-FileHash -LiteralPath $rawPath -Algorithm SHA256).Hash.ToLowerInvariant()
$rawSize = (Get-Item -LiteralPath $rawPath).Length
if ($rawHash -ne $snapshot.sha256 -or $rawSize -ne $snapshot.bytes) {
    throw 'Private snapshot hash or byte size mismatch'
}
if ($verification.independent_sha256 -ne $snapshot.sha256 -or
    $verification.parsed_rows -ne $snapshot.rows -or
    $snapshot.source_count_before -ne $snapshot.rows -or
    $snapshot.source_count_after -ne $snapshot.rows) {
    throw 'Snapshot aggregate verification mismatch'
}
Write-Output "Verified $verifiedCount immutable run files, environment lock, and private NYC snapshot hash, size and recorded count."
