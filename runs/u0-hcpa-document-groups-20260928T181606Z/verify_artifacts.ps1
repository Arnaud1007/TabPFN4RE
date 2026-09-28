$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Set-Location -LiteralPath $projectRoot

$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Raw | ConvertFrom-Json
$aggregate = Get-Content -LiteralPath $manifest.aggregate_path -Raw | ConvertFrom-Json
$pairs = @(
    @('data/raw/hcpa/allsales_09_18_2026.zip', $manifest.source_snapshot_sha256),
    @($manifest.private_sample_path, $manifest.sample_sha256),
    @($manifest.private_flags_path, $manifest.private_flags_sha256),
    @($manifest.private_replay_flags_path, $manifest.private_replay_flags_sha256),
    @($manifest.aggregate_path, $manifest.aggregate_sha256),
    @($manifest.aggregate_replay_path, $manifest.aggregate_replay_sha256),
    @($manifest.script_path, $manifest.script_sha256),
    @($manifest.tests_path, $manifest.tests_sha256),
    @($manifest.configuration_path, $manifest.configuration_sha256),
    @($manifest.environment_lock_path, $manifest.environment_lock_sha256)
)
foreach ($pair in $pairs) {
    $actual = (Get-FileHash -LiteralPath $pair[0] -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $pair[1]) { throw "Artifact hash mismatch: $($pair[0])" }
}

$expectedKeys = @(
    'active_rows', 'blank_document_rows', 'deleted_rows', 'document_groups',
    'header_record_count', 'interpretation', 'max_group_size', 'member',
    'member_crc32', 'member_uncompressed_bytes', 'nonblank_document_rows',
    'repeated_group_signals', 'repeated_group_size_histogram', 'repeated_groups',
    'rows_in_repeated_groups', 'sample_blank_document_rows',
    'sample_group_size_histogram', 'sample_repeated_document_rows',
    'sample_repeated_document_signals', 'sample_rows', 'sample_sha256',
    'sample_singleton_document_rows', 'singleton_groups', 'source_archive_sha256'
)
if (Compare-Object ($aggregate.PSObject.Properties.Name | Sort-Object) ($expectedKeys | Sort-Object)) {
    throw 'Unexpected aggregate field'
}
foreach ($section in @(
    $aggregate.repeated_group_signals,
    $aggregate.repeated_group_size_histogram,
    $aggregate.sample_group_size_histogram,
    $aggregate.sample_repeated_document_signals
)) {
    foreach ($property in $section.PSObject.Properties) {
        if ($property.Value -isnot [int] -and $property.Value -isnot [long]) {
            throw 'A nested aggregate field is not an integer count'
        }
    }
}

$groupBuckets = ($aggregate.repeated_group_size_histogram.PSObject.Properties.Value | Measure-Object -Sum).Sum
$privateRows = (Get-Content -LiteralPath $manifest.private_flags_path | Measure-Object -Line).Lines
$spools = @(Get-ChildItem -LiteralPath 'data/raw/hcpa' -Filter '.hcpa-document-groups-spool-*')
$ignored = git check-ignore $manifest.private_flags_path
if (
    $aggregate.header_record_count -ne 2453187 -or
    $aggregate.blank_document_rows -ne 269947 -or
    $aggregate.nonblank_document_rows -ne ($aggregate.singleton_groups + $aggregate.rows_in_repeated_groups) -or
    $aggregate.document_groups -ne ($aggregate.singleton_groups + $aggregate.repeated_groups) -or
    $aggregate.repeated_groups -ne $groupBuckets -or
    $aggregate.sample_rows -ne ($aggregate.sample_blank_document_rows + $aggregate.sample_singleton_document_rows + $aggregate.sample_repeated_document_rows) -or
    $privateRows -ne 200 -or $spools.Count -ne 0 -or
    $ignored -ne $manifest.private_flags_path
) {
    throw 'Count, private-path or spool reconciliation failed'
}

Write-Output 'PASS: artifact hashes, exact replay, aggregate schema, source and sample counts, private path, spool cleanup'
