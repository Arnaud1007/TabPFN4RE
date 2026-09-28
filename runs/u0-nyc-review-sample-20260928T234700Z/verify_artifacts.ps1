$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Raw | ConvertFrom-Json
$aggregate = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'aggregate.json') -Raw | ConvertFrom-Json
$verification = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'verification.json') -Raw | ConvertFrom-Json
$configuration = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'configuration.json') -Raw | ConvertFrom-Json

if ($manifest.run_id -ne 'u0-nyc-review-sample-20260928T234700Z' -or
    $manifest.environment_lock_path -ne 'locks/nyc-review-sample-environment.json' -or
    $manifest.source_snapshot_manifest -ne 'runs/u0-nyc-rolling-snapshot-20260928T225512Z/snapshot.json' -or
    $manifest.source_profile_path -ne 'runs/u0-nyc-rolling-profile-20260928T232337Z/aggregate.json' -or
    $manifest.protocol_path -ne 'decisions/0021-nyc-manual-audit-sample.md') {
    throw 'Unexpected run, lock, source or protocol path'
}
$lockPath = Join-Path $projectRoot $manifest.environment_lock_path
if (-not (Test-Path -LiteralPath $lockPath -PathType Leaf) -or
    ((Get-Item -LiteralPath $lockPath).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
    (Get-FileHash -LiteralPath $lockPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.environment_lock_sha256) {
    throw 'Environment lock missing, redirected or changed'
}

$verifiedCount = 0
foreach ($item in $manifest.immutable_files_sha256.PSObject.Properties) {
    if ($item.Name -notmatch '^runs/u0-nyc-review-sample-20260928T234700Z/[A-Za-z0-9_.-]+$' -and
        $item.Name -ne $manifest.source_snapshot_manifest -and
        $item.Name -ne $manifest.source_profile_path -and
        $item.Name -ne $manifest.protocol_path) {
        throw "Unexpected immutable path: $($item.Name)"
    }
    $path = Join-Path $projectRoot $item.Name
    if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or
        ((Get-Item -LiteralPath $path).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
        (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $item.Value) {
        throw "Immutable file missing, redirected or changed: $($item.Name)"
    }
    $verifiedCount++
}

$snapshot = Get-Content -LiteralPath (Join-Path $projectRoot $manifest.source_snapshot_manifest) -Raw | ConvertFrom-Json
if ($snapshot.sha256 -ne $manifest.data_snapshot_hash -or
    $snapshot.rows -ne $aggregate.source_rows -or
    $configuration.protocol_sha256 -ne $manifest.protocol_sha256 -or
    $aggregate.profile_sha256 -ne $manifest.source_profile_sha256 -or
    $aggregate.ledger_sha256 -ne $manifest.private_ledger_sha256) {
    throw 'Source, protocol, aggregate or private-ledger manifest mismatch'
}
if ((Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'configuration.json') -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.configuration_hash) {
    throw 'Configuration hash mismatch'
}
$rawName = [string]$snapshot.raw_filename
if ($rawName -ne 'nyc-usep-8jbt-20260928T225530.250496Z-2d84779d0195.csv') {
    throw 'Unexpected snapshot filename'
}
$rawPath = Join-Path $projectRoot (Join-Path 'data\raw\nyc_dof' $rawName)
if (-not (Test-Path -LiteralPath $rawPath -PathType Leaf) -or
    ((Get-Item -LiteralPath $rawPath).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
    (Get-FileHash -LiteralPath $rawPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $snapshot.sha256 -or
    (Get-Item -LiteralPath $rawPath).Length -ne $snapshot.bytes) {
    throw 'Private source snapshot missing, redirected or changed'
}

$firstLedger = $null
if (@($manifest.private_ledger_filenames).Count -ne 2) {
    throw 'Expected exactly two private ledgers'
}
foreach ($name in $manifest.private_ledger_filenames) {
    if ($name -notmatch '^review-usep-8jbt-20260928T234700Z(-replay)?\.jsonl$') {
        throw 'Unexpected private ledger filename'
    }
    $path = Join-Path $projectRoot (Join-Path 'data\raw\nyc_dof' $name)
    if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or
        ((Get-Item -LiteralPath $path).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
        (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.private_ledger_sha256) {
        throw "Private ledger missing, redirected or changed: $name"
    }
    if ($null -eq $firstLedger) { $firstLedger = $path }
}

$rows = @(Get-Content -LiteralPath $firstLedger | ForEach-Object { $_ | ConvertFrom-Json })
if ($rows.Count -ne 200 -or @($rows | Select-Object -ExpandProperty ordinal -Unique).Count -ne 200) {
    throw 'Private ledger lacks 200 distinct ordinals'
}
$sha = [Security.Cryptography.SHA256]::Create()
try {
    foreach ($row in $rows) {
        $rankText = "nyc-review-v1|$($snapshot.sha256)|42|$($row.ordinal)"
        $rankBytes = $sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($rankText))
        $rankHex = [BitConverter]::ToString($rankBytes).Replace('-', '').ToLowerInvariant()
        if ($row.rank -ne $rankHex) { throw 'Private ledger rank mismatch' }
    }
} finally { $sha.Dispose() }

foreach ($bucket in $aggregate.primary_bucket_counts.PSObject.Properties) {
    if (@($rows | Where-Object primary_bucket -eq $bucket.Name).Count -ne $bucket.Value) {
        throw "Private ledger primary bucket count mismatch: $($bucket.Name)"
    }
}
foreach ($borough in $aggregate.structural_counts.PSObject.Properties) {
    foreach ($cell in $borough.Value.PSObject.Properties) {
        $cellName = "$($borough.Name):$($cell.Name)"
        if (@($rows | Where-Object { $_.primary_bucket -eq 'structural' -and $_.structural_cell -eq $cellName }).Count -ne $cell.Value) {
            throw "Private ledger structural cell count mismatch: $cellName"
        }
    }
}
if (-not $verification.byte_identical_replay -or $verification.manual_reviewed_records -ne 0 -or
    $aggregate.selected_rows -ne 200 -or $verification.selected_rows -ne 200) {
    throw 'Run verification or review status mismatch'
}
Write-Output "Verified $verifiedCount immutable files, source, private ledgers and 200 distinct ranks/quotas. Manual review remains pending."
