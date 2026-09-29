$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Raw | ConvertFrom-Json
$aggregate = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'aggregate.json') -Raw | ConvertFrom-Json

if ($manifest.run_id -ne 'u0-nyc-acris-inventory-20260929T000000Z' -or
    $manifest.environment_lock_path -ne 'locks/nyc-acris-inventory-environment.json' -or
    $aggregate.status -ne 'metadata_and_count_inventory_only' -or
    $aggregate.row_level_acris_queries -ne 0 -or
    $aggregate.matched_sample_records -ne 0) {
    throw 'Inventory run identity or scope mismatch'
}
$lockPath = Join-Path $projectRoot $manifest.environment_lock_path
if (-not (Test-Path -LiteralPath $lockPath -PathType Leaf) -or
    ((Get-Item -LiteralPath $lockPath).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
    (Get-FileHash -LiteralPath $lockPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.environment_lock_sha256) {
    throw 'Environment lock missing, redirected or changed'
}
$configurationPath = Join-Path $PSScriptRoot 'configuration.json'
if ((Get-FileHash -LiteralPath $configurationPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.configuration_hash) {
    throw 'Configuration hash mismatch'
}
$checked = 0
foreach ($item in $manifest.immutable_files_sha256.PSObject.Properties) {
    if ($item.Name -notmatch '^runs/u0-nyc-acris-inventory-20260929T000000Z/[A-Za-z0-9_.-]+$' -and
        $item.Name -ne 'data/source_cards/nyc_acris_master.yaml' -and
        $item.Name -ne 'data/source_cards/nyc_acris_legals.yaml' -and
        $item.Name -ne 'decisions/0022-nyc-acris-linkage-pilot.md') {
        throw "Unexpected immutable path: $($item.Name)"
    }
    $path = Join-Path $projectRoot $item.Name
    if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or
        ((Get-Item -LiteralPath $path).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
        (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $item.Value) {
        throw "Inventory artifact missing, redirected or changed: $($item.Name)"
    }
    $checked++
}

$sources = @(
    @{ Kind = 'master'; Id = 'bnx9-e6tj' },
    @{ Kind = 'legals'; Id = '8h5j-fqxa' }
)
foreach ($source in $sources) {
    $kind = $source.Kind
    $id = $source.Id
    $record = $aggregate.sources.$kind
    if ($record.dataset_id -ne $id) { throw "Dataset ID mismatch: $kind" }
    $prefix = "acris-$kind-$id"
    $metadataPath = Join-Path $projectRoot "data\raw\nyc_dof\$prefix-metadata-20260929.json"
    $countPath = Join-Path $projectRoot "data\raw\nyc_dof\$prefix-count-20260929.json"
    foreach ($path in @($metadataPath, $countPath)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or
            ((Get-Item -LiteralPath $path).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Private inventory response missing or redirected: $kind"
        }
    }
    if ((Get-FileHash -LiteralPath $metadataPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $record.metadata_sha256 -or
        (Get-Item -LiteralPath $metadataPath).Length -ne $record.metadata_bytes -or
        (Get-FileHash -LiteralPath $countPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $record.count_response_sha256 -or
        (Get-Item -LiteralPath $countPath).Length -ne $record.count_response_bytes) {
        throw "Private inventory response hash or size mismatch: $kind"
    }
    $metadata = Get-Content -LiteralPath $metadataPath -Raw | ConvertFrom-Json
    $count = Get-Content -LiteralPath $countPath -Raw | ConvertFrom-Json
    if ($metadata.id -ne $id -or @($count).Count -ne 1 -or
        [int64]$count[0].count -ne $record.current_api_rows_at_inventory) {
        throw "Private inventory response content mismatch: $kind"
    }
}
$snapshotText = @(
    $aggregate.sources.master.metadata_sha256,
    $aggregate.sources.master.count_response_sha256,
    $aggregate.sources.legals.metadata_sha256,
    $aggregate.sources.legals.count_response_sha256
) -join '|'
$sha = [Security.Cryptography.SHA256]::Create()
try {
    $bytes = $sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($snapshotText))
    $snapshotHash = [BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
} finally { $sha.Dispose() }
if ($snapshotHash -ne $manifest.data_snapshot_hash) {
    throw 'Composite source snapshot hash mismatch'
}
Write-Output "Verified $checked immutable inventory files and four private metadata/count responses. No ACRIS row lookup was performed."
