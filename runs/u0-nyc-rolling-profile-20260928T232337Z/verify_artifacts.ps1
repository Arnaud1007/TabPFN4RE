$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Raw | ConvertFrom-Json
$aggregate = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'aggregate.json') -Raw | ConvertFrom-Json
$verification = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'verification.json') -Raw | ConvertFrom-Json

if ($manifest.run_id -ne 'u0-nyc-rolling-profile-20260928T232337Z') {
    throw 'Unexpected run ID'
}
if ($manifest.environment_lock_path -ne 'locks/nyc-profile-environment.json') {
    throw 'Unexpected environment lock path'
}
$lockPath = Join-Path $projectRoot $manifest.environment_lock_path
if (((Get-Item -LiteralPath $lockPath).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw 'Environment lock is a reparse point'
}
if ((Get-FileHash -LiteralPath $lockPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.environment_lock_sha256) {
    throw 'Environment lock hash mismatch'
}

$verifiedCount = 0
foreach ($item in $manifest.immutable_run_files_sha256.PSObject.Properties) {
    if ($item.Name -ne 'runs/u0-nyc-rolling-snapshot-20260928T225512Z/snapshot.json' -and
        $item.Name -notmatch '^runs/u0-nyc-rolling-profile-20260928T232337Z/[A-Za-z0-9_.-]+$') {
        throw "Unexpected immutable run path: $($item.Name)"
    }
    $path = Join-Path $projectRoot $item.Name
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing immutable run file: $($item.Name)"
    }
    if (((Get-Item -LiteralPath $path).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Run file is a reparse point: $($item.Name)"
    }
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $item.Value) {
        throw "Immutable run file hash mismatch: $($item.Name)"
    }
    $verifiedCount++
}

if ($manifest.source_snapshot_manifest -ne 'runs/u0-nyc-rolling-snapshot-20260928T225512Z/snapshot.json') {
    throw 'Unexpected source snapshot manifest path'
}
$snapshot = Get-Content -LiteralPath (Join-Path $projectRoot $manifest.source_snapshot_manifest) -Raw | ConvertFrom-Json
if ($snapshot.sha256 -ne $manifest.data_snapshot_hash -or $snapshot.rows -ne $aggregate.rows) {
    throw 'Snapshot manifest or aggregate denominator mismatch'
}
$rawName = [string]$snapshot.raw_filename
if ($rawName -ne [IO.Path]::GetFileName($rawName)) {
    throw 'Snapshot filename is not a basename'
}
$rawPath = Join-Path $projectRoot (Join-Path 'data\raw\nyc_dof' $rawName)
if (-not (Test-Path -LiteralPath $rawPath -PathType Leaf)) {
    throw 'Private snapshot unavailable; obtain the authorised source file before replay'
}
if (((Get-Item -LiteralPath $rawPath).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw 'Private snapshot is a reparse point'
}
if ((Get-FileHash -LiteralPath $rawPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $snapshot.sha256 -or
    (Get-Item -LiteralPath $rawPath).Length -ne $snapshot.bytes) {
    throw 'Private snapshot hash or size mismatch'
}
foreach ($name in $manifest.private_profile_filenames) {
    if ($name -ne [IO.Path]::GetFileName($name)) {
        throw 'Profile filename is not a basename'
    }
    $path = Join-Path $projectRoot (Join-Path 'data\raw\nyc_dof' $name)
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing private profile: $name"
    }
    if (((Get-Item -LiteralPath $path).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Private profile is a reparse point: $name"
    }
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $verification.aggregate_sha256) {
        throw "Private profile hash mismatch: $name"
    }
}
if (-not $verification.all_denominators_reconcile -or -not $verification.byte_identical_replay -or
    $verification.borough_sum -ne $aggregate.rows -or $verification.price_state_sum -ne $aggregate.rows) {
    throw 'Aggregate verification failed'
}
Write-Output "Verified $verifiedCount immutable run files, environment lock, raw snapshot and two private profile copies."
