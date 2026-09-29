$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Raw | ConvertFrom-Json
$aggregate = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'aggregate.json') -Raw | ConvertFrom-Json
$config = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'configuration.json') -Raw | ConvertFrom-Json

if ($manifest.run_id -ne 'u0-nyc-acris-pilot-20260929T003102Z' -or
    $aggregate.run_id -ne $manifest.run_id -or
    $aggregate.status -ne 'incomplete' -or
    $aggregate.failure_kind -ne 'saturated' -or
    $aggregate.http_requests -ne 3 -or
    $aggregate.saved_private_responses -ne 2 -or
    $aggregate.manual_reviews_completed -ne 0 -or
    $aggregate.sale_labels_certified -ne 0 -or
    $aggregate.u0_accepted -ne $false -or
    $aggregate.g_us_status -ne 'PENDING' -or
    $config.protocol -ne 'nyc-acris-pilot-v1') {
    throw 'Run identity, failure, or gate status differs from frozen evidence'
}

$lockPath = Join-Path $root $manifest.environment_lock_path
if (-not (Test-Path -LiteralPath $lockPath -PathType Leaf) -or
    ((Get-Item -LiteralPath $lockPath).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
    (Get-FileHash -LiteralPath $lockPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.environment_lock_sha256) {
    throw 'Environment lock missing, redirected, or changed'
}
if ((Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'configuration.json') -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.configuration_hash) {
    throw 'Configuration hash mismatch'
}

$checked = 0
foreach ($item in $manifest.immutable_files_sha256.PSObject.Properties) {
    if ($item.Name -notmatch '^runs/u0-nyc-acris-pilot-20260929T003102Z/[A-Za-z0-9_.-]+$' -and
        $item.Name -ne 'scripts/audit_nyc_acris_matches.py' -and
        $item.Name -ne 'tests/test_audit_nyc_acris_matches.py' -and
        $item.Name -ne 'decisions/0022-nyc-acris-linkage-pilot.md') {
        throw "Unexpected immutable path: $($item.Name)"
    }
    $path = Join-Path $root $item.Name
    if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or
        ((Get-Item -LiteralPath $path).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
        (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $item.Value) {
        throw "Tracked pilot artifact missing, redirected, or changed: $($item.Name)"
    }
    $checked++
}

$rawRoot = Join-Path $root 'data\raw\nyc_dof'
$statePath = Join-Path $rawRoot 'acris-pilot-20260929T003102Z\state.json'
if (-not (Test-Path -LiteralPath $statePath -PathType Leaf) -or
    ((Get-Item -LiteralPath $statePath).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
    (Get-Item -LiteralPath $statePath).Length -ne $aggregate.private_artifacts.state_bytes -or
    (Get-FileHash -LiteralPath $statePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $aggregate.private_artifacts.state_sha256) {
    throw 'Private pilot state missing, redirected, or changed'
}
$state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
if ($state.status -ne 'incomplete' -or
    $state.aggregate.failure_kind -ne 'saturated' -or
    $state.aggregate.http_requests -ne 3 -or
    $state.responses.Count -ne 2 -or
    $aggregate.private_artifacts.saved_responses.Count -ne 2) {
    throw 'Private pilot state does not match failed run'
}
$index = 0
foreach ($record in $aggregate.private_artifacts.saved_responses) {
    if ($record.filename -notmatch '^response-[0-9]{3}\.json$' -or
        $state.responses[$index].filename -ne $record.filename -or
        $state.responses[$index].sha256 -ne $record.sha256) {
        throw 'Private response metadata mismatch'
    }
    $path = Join-Path (Split-Path -Parent $statePath) $record.filename
    if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or
        ((Get-Item -LiteralPath $path).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
        (Get-Item -LiteralPath $path).Length -ne $record.bytes -or
        (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $record.sha256) {
        throw 'Private saved response missing, redirected, or changed'
    }
    $rows = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
    if ($rows.Count -ne $record.rows) { throw 'Private response row count mismatch' }
    if ($index -eq 0 -and
        ($rows.Count -ne 27 -or @($rows.document_id | Sort-Object -Unique).Count -ne 24)) {
        throw 'First BBL aggregate count mismatch'
    }
    $index++
}

$sourcePath = Join-Path $rawRoot 'nyc-usep-8jbt-20260928T225530.250496Z-2d84779d0195.csv'
$ledgerPath = Join-Path $rawRoot 'review-usep-8jbt-20260928T234700Z.jsonl'
foreach ($path in @($sourcePath, $ledgerPath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or
        ((Get-Item -LiteralPath $path).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw 'Pinned private source or ledger missing or redirected'
    }
}
if ((Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $aggregate.snapshot_sha256 -or
    (Get-FileHash -LiteralPath $ledgerPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $aggregate.ledger_sha256) {
    throw 'Pinned private source or ledger hash mismatch'
}
$snapshotText = @($aggregate.snapshot_sha256, $aggregate.ledger_sha256, $aggregate.private_artifacts.state_sha256) -join '|'
$sha = [Security.Cryptography.SHA256]::Create()
try {
    $bytes = $sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($snapshotText))
    $snapshotHash = [BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
} finally { $sha.Dispose() }
if ($snapshotHash -ne $manifest.data_snapshot_hash) {
    throw 'Composite pilot snapshot hash mismatch'
}
Write-Output "Verified $checked immutable pilot files, pinned source and ledger, state, and two saved responses. Pilot remains INCOMPLETE."
