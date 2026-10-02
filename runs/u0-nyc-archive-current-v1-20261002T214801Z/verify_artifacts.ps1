$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$privateRun = Join-Path $projectRoot 'data\raw\nyc_dof\archive-current-v1-20261002T214801Z-d4b589edff65'
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Raw | ConvertFrom-Json
$aggregatePath = Join-Path $PSScriptRoot 'aggregate.json'
$aggregate = Get-Content -LiteralPath $aggregatePath -Raw | ConvertFrom-Json
$intentPath = Join-Path $privateRun 'intent.json'
$resultPath = Join-Path $privateRun 'result.json'
$privatePublicPath = Join-Path $privateRun 'public.json'
$hashManifestPath = Join-Path $privateRun 'hash_manifest.json'
$intent = Get-Content -LiteralPath $intentPath -Raw | ConvertFrom-Json
$hashes = Get-Content -LiteralPath $hashManifestPath -Raw | ConvertFrom-Json

function Get-LowerHash([string]$path) {
    return (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
}

if ($manifest.protocol -ne 'nyc-archive-current-concordance-v1' -or
    $manifest.code_commit -ne '635e621b256e3a2a07c3e34072bf6b3be8714294' -or
    $manifest.remote_tracking_commit -ne $manifest.code_commit -or
    $manifest.dirty_tree_at_start -or
    $manifest.archive_csv_sha256 -ne '0746355101b245fb469ce97e19e088fa2b16f0f95728d7a5b07dd670e98c345f' -or
    $manifest.current_csv_sha256 -ne '84c06057c52a2822f982cd98fb77ef7edf2c14134d00f46b073d2e4b762b2ef2' -or
    $manifest.sale_labels_certified -ne 0 -or
    $manifest.historical_asof_eligible) {
    throw 'Pinned public comparison manifest differs'
}
if ($aggregate.protocol -ne $manifest.protocol -or
    $aggregate.archive_rows -ne 81567 -or
    $aggregate.current_rows -ne 82345 -or
    $aggregate.raw_overlap_bucket -ne 'zero' -or
    $aggregate.date_overlap_bucket -ne '1000_plus' -or
    $aggregate.sale_labels_certified -ne 0 -or
    $aggregate.historical_asof_eligible -or
    $aggregate.u0_status -ne 'PENDING' -or
    $aggregate.g_us_status -ne 'PENDING') {
    throw 'Public comparison aggregate differs'
}
if ((Get-LowerHash $aggregatePath) -ne $manifest.aggregate_sha256 -or
    (Get-LowerHash $privatePublicPath) -ne $manifest.aggregate_sha256) {
    throw 'Public and protected projection hashes differ'
}
if ((Get-LowerHash $intentPath) -ne $hashes.intent_sha256 -or
    (Get-LowerHash $resultPath) -ne $hashes.result_sha256 -or
    (Get-LowerHash $privatePublicPath) -ne $hashes.public_sha256) {
    throw 'Protected comparison artifact hashes differ'
}
if ($intent.code_commit -ne $manifest.code_commit -or
    $intent.remote_tracking_commit -ne $manifest.remote_tracking_commit -or
    $intent.configuration_sha256 -ne $manifest.configuration_sha256 -or
    $intent.environment_lock_sha256 -ne $manifest.environment_lock_sha256 -or
    $intent.archive_csv_sha256 -ne $manifest.archive_csv_sha256 -or
    $intent.current_csv_sha256 -ne $manifest.current_csv_sha256 -or
    $intent.code_hashes.'scripts/compare_nyc_archive_snapshot_v1.py' -ne $manifest.code_sha256 -or
    (Get-LowerHash (Join-Path $projectRoot 'scripts\compare_nyc_archive_snapshot_v1.py')) -ne $manifest.code_sha256) {
    throw 'Protected comparison intent differs from committed code or inputs'
}
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$comparator = Join-Path $projectRoot 'scripts\compare_nyc_archive_snapshot_v1.py'
$replayed = & $python $comparator replay $privateRun
if ($LASTEXITCODE -ne 0) { throw 'Offline comparison replay failed' }
$replayAggregate = $replayed | ConvertFrom-Json
foreach ($name in @('archive_rows', 'current_rows', 'raw_overlap_bucket', 'date_overlap_bucket', 'sale_labels_certified', 'historical_asof_eligible', 'u0_status', 'g_us_status')) {
    if ($replayAggregate.$name -ne $aggregate.$name) {
        throw "Offline replay projection differs: $name"
    }
}
Write-Output 'NYC archive/current v1: pinned private hashes and offline replay verified; zero labels certified; U0 and G-US pending'
