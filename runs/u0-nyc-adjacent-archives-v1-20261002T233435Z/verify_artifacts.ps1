$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$runName = 'archive-adjacent-v1-20261002T233435Z-6db0ca9ec142'
$privateRun = Join-Path $projectRoot "data\raw\nyc_dof\$runName"

function Assert-HashEqual([string]$left, [string]$right) {
    $leftHash = (Get-FileHash -LiteralPath $left -Algorithm SHA256).Hash.ToLowerInvariant()
    $rightHash = (Get-FileHash -LiteralPath $right -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($leftHash -ne $rightHash) { throw "Artifact hash differs: $left" }
}

foreach ($name in @('intent.json', 'public.json')) {
    Assert-HashEqual (Join-Path $PSScriptRoot $name) (Join-Path $privateRun $name)
}
$hashes = Get-Content -LiteralPath (Join-Path $privateRun 'hash_manifest.json') -Raw | ConvertFrom-Json
foreach ($entry in @(
    @('intent.json', 'intent_sha256'),
    @('result.json', 'result_sha256'),
    @('public.json', 'public_sha256')
)) {
    $actual = (Get-FileHash -LiteralPath (Join-Path $privateRun $entry[0]) -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $hashes.($entry[1])) { throw "Private aggregate hash differs: $($entry[0])" }
}
$intent = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'intent.json') -Raw | ConvertFrom-Json
$public = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'public.json') -Raw | ConvertFrom-Json
if ($intent.run_id -ne $runName -or
    $intent.code_commit -ne '9dfa171cbb0e85527b549eea01638365edb33921' -or
    $intent.remote_tracking_commit -ne $intent.code_commit -or
    $intent.dirty_tree_at_start -or
    $intent.protocol -ne 'nyc-adjacent-archives-v1' -or
    $public.protocol -ne $intent.protocol -or
    $public.v61_rows -ne 79335 -or
    $public.v62_rows -ne 81567 -or
    $public.raw_overlap_bucket -ne '1000_plus' -or
    $public.date_overlap_bucket -ne '1000_plus' -or
    $public.sale_labels_certified -ne 0 -or
    $public.historical_asof_eligible -or
    $public.u0_status -ne 'PENDING' -or
    $public.u3_status -ne 'PENDING' -or
    $public.g_us_status -ne 'PENDING') {
    throw 'Pinned adjacent-archive evidence differs'
}
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$runner = Join-Path $projectRoot 'scripts\compare_nyc_adjacent_archives_v1.py'
$replayed = & $python $runner replay $privateRun
if ($LASTEXITCODE -ne 0) { throw 'Offline adjacent-archive replay failed' }
$replayPublic = $replayed | ConvertFrom-Json
if ($replayPublic.protocol -ne $public.protocol -or
    $replayPublic.v61_rows -ne $public.v61_rows -or
    $replayPublic.v62_rows -ne $public.v62_rows -or
    $replayPublic.raw_overlap_bucket -ne $public.raw_overlap_bucket -or
    $replayPublic.date_overlap_bucket -ne $public.date_overlap_bucket -or
    $replayPublic.sale_labels_certified -ne 0 -or
    $replayPublic.historical_asof_eligible) {
    throw 'Offline adjacent-archive public projection differs'
}
Write-Output 'NYC adjacent archives: private hashes and offline replay verified; zero labels certified; U0, U3 and G-US pending'
