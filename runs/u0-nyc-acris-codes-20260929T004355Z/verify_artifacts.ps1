$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Raw | ConvertFrom-Json
$aggregate = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'aggregate.json') -Raw | ConvertFrom-Json

if ($manifest.run_id -ne 'u0-nyc-acris-codes-20260929T004355Z' -or
    $aggregate.run_id -ne $manifest.run_id -or
    $aggregate.status -ne 'verified_current_code_table_inventory_only' -or
    $aggregate.dataset_id -ne '7isb-wh4c' -or
    $aggregate.row_count -ne 126 -or
    $aggregate.unique_code_count -ne 126 -or
    $aggregate.property_rows_queried -ne 0 -or
    $aggregate.u0_accepted -ne $false -or
    $aggregate.g_us_status -ne 'PENDING') {
    throw 'Code-table run identity, content, or gate status mismatch'
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
    if ($item.Name -notmatch '^runs/u0-nyc-acris-codes-20260929T004355Z/[A-Za-z0-9_.-]+$' -and
        $item.Name -ne 'data/source_cards/nyc_acris_document_control_codes.yaml') {
        throw "Unexpected code-table artifact path: $($item.Name)"
    }
    $path = Join-Path $root $item.Name
    if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or
        ((Get-Item -LiteralPath $path).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
        (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $item.Value) {
        throw "Code-table artifact missing, redirected, or changed: $($item.Name)"
    }
    $checked++
}

$rawRoot = Join-Path $root 'data\raw\nyc_dof'
$metadataPath = Join-Path $rawRoot 'acris-document-control-codes-7isb-wh4c-metadata-20260929.json'
$rowsPath = Join-Path $rawRoot 'acris-document-control-codes-7isb-wh4c-rows-20260929.json'
foreach ($path in @($metadataPath, $rowsPath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or
        ((Get-Item -LiteralPath $path).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw 'Private code-table response missing or redirected'
    }
}
if ((Get-FileHash -LiteralPath $metadataPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $aggregate.metadata_sha256 -or
    (Get-Item -LiteralPath $metadataPath).Length -ne $aggregate.metadata_bytes -or
    (Get-FileHash -LiteralPath $rowsPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $aggregate.rows_sha256 -or
    (Get-Item -LiteralPath $rowsPath).Length -ne $aggregate.rows_bytes) {
    throw 'Private code-table response hash or size mismatch'
}
$metadata = Get-Content -LiteralPath $metadataPath -Raw | ConvertFrom-Json
$rows = Get-Content -LiteralPath $rowsPath -Raw | ConvertFrom-Json
if ($metadata.id -ne '7isb-wh4c' -or
    $rows.Count -ne 126 -or
    @($rows.doc__type | Sort-Object -Unique).Count -ne 126 -or
    ($rows | Where-Object { -not $_.doc__type -or -not $_.doc__type_description -or -not $_.class_code_description -or -not $_.record_type }).Count -ne 0) {
    throw 'Private code-table response content mismatch'
}
$cdec = @($rows | Where-Object { $_.doc__type -eq 'CDEC' })
if ($cdec.Count -ne 1 -or
    $cdec[0].doc__type_description -ne 'CONDO DECLARATION' -or
    $cdec[0].class_code_description -ne 'DEEDS AND OTHER CONVEYANCES') {
    throw 'CDEC code meaning differs from captured inventory'
}
foreach ($group in $aggregate.class_counts.PSObject.Properties) {
    $actual = @($rows | Where-Object { $_.class_code_description -eq $group.Name }).Count
    if ($actual -ne $group.Value) {
        throw "Document class count mismatch: $($group.Name)"
    }
}

$snapshotText = @($aggregate.metadata_sha256, $aggregate.rows_sha256) -join '|'
$sha = [Security.Cryptography.SHA256]::Create()
try {
    $bytes = $sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($snapshotText))
    $snapshotHash = [BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
} finally { $sha.Dispose() }
if ($snapshotHash -ne $manifest.data_snapshot_hash) {
    throw 'Composite code-table snapshot hash mismatch'
}
Write-Output "Verified $checked immutable code-table files and two private responses. No property rows were queried."
