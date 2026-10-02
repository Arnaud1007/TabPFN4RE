$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$privateRun = Join-Path $projectRoot 'data\raw\nyc_dof\ready-archive-v2-20261002T210520Z'
$publicManifestPath = Join-Path $PSScriptRoot 'manifest.json'
$privateManifestPath = Join-Path $privateRun 'manifest.json'
$publicAggregatePath = Join-Path $PSScriptRoot 'aggregate.json'
$privateAggregatePath = Join-Path $privateRun 'aggregate.json'

function Assert-HashEqual([string]$left, [string]$right) {
    $leftHash = (Get-FileHash -LiteralPath $left -Algorithm SHA256).Hash.ToLowerInvariant()
    $rightHash = (Get-FileHash -LiteralPath $right -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($leftHash -ne $rightHash) { throw "Artifact hash differs: $left" }
}

Assert-HashEqual $publicManifestPath $privateManifestPath
Assert-HashEqual $publicAggregatePath $privateAggregatePath
$manifest = Get-Content -LiteralPath $publicManifestPath -Raw | ConvertFrom-Json
$aggregate = Get-Content -LiteralPath $publicAggregatePath -Raw | ConvertFrom-Json
if ($manifest.code_commit -ne 'a4e99bc2963a1e9f4cd5a0c00b600ab3ba238867' -or
    $manifest.dirty_tree_at_start -or
    $manifest.protocol -ne 'nyc-ready-rolling-archive-v2' -or
    $manifest.version -ne 62 -or
    $manifest.requests.Count -ne 5 -or
    $aggregate.rows -ne 81567 -or
    $aggregate.bytes -ne 11302195 -or
    $aggregate.csv_sha256 -ne '0746355101b245fb469ce97e19e088fa2b16f0f95728d7a5b07dd670e98c345f' -or
    $aggregate.historical_asof_eligible -or
    $aggregate.sale_labels_certified -ne 0) {
    throw 'Pinned archive evidence differs'
}
$expectedStages = @('list_before', 'status_before', 'csv', 'status_after', 'list_after')
$expectedFiles = @('list-before.json', 'status-before.json', 'archive.csv', 'status-after.json', 'list-after.json')
for ($index = 0; $index -lt $expectedStages.Count; $index++) {
    $request = $manifest.requests[$index]
    if ($request.stage -ne $expectedStages[$index] -or $request.file -ne $expectedFiles[$index]) {
        throw "Archive request identity differs at index $index"
    }
    $path = Join-Path $privateRun $request.file
    $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    $bytes = (Get-Item -LiteralPath $path).Length
    if ($hash -ne $request.sha256 -or $bytes -ne $request.bytes) {
        throw "Private archive response differs: $($request.file)"
    }
}
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$collector = Join-Path $projectRoot 'scripts\capture_nyc_generated_archive.py'
$replayed = & $python $collector replay $privateRun
if ($LASTEXITCODE -ne 0) { throw 'Offline archive replay failed' }
$replayAggregate = $replayed | ConvertFrom-Json
if ($replayAggregate.csv_sha256 -ne $aggregate.csv_sha256 -or
    $replayAggregate.rows -ne $aggregate.rows -or
    $replayAggregate.bytes -ne $aggregate.bytes -or
    $replayAggregate.sale_labels_certified -ne 0) {
    throw 'Offline replay aggregate differs'
}
Write-Output 'NYC version-62 archive: private hashes and offline replay verified; zero labels certified; U0 and G-US pending'
