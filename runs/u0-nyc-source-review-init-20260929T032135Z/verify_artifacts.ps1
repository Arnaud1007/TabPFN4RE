$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$privateDir = Join-Path $projectRoot 'data\raw\nyc_dof\manual-review-v1'
$snapshotDir = Join-Path $privateDir 'init-snapshot-20260929T032135Z'
$runDir = $PSScriptRoot
$expectedPrivate = @{
    'manifest.json' = '474d8f38731e5f62eed1e0920f74263e2707c8e481d22ddb0bbb808e324a0216'
    'reviews.jsonl' = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
}
$actualNames = @(Get-ChildItem -LiteralPath $snapshotDir -Force -Name | Sort-Object)
if (($actualNames -join ',') -ne 'manifest.json,reviews.jsonl') {
    throw 'Private review files differ from the frozen empty-ledger inventory'
}
foreach ($name in $expectedPrivate.Keys) {
    $actual = (Get-FileHash -LiteralPath (Join-Path $snapshotDir $name) -Algorithm SHA256).Hash.ToLower()
    if ($actual -ne $expectedPrivate[$name]) {
        throw "Private review artifact changed: $name"
    }
}
$expectedAggregate = 'ee68bae54aaf46a350bb04ba8963403670583a86900efbad16ce8ea9efa747e6'
foreach ($name in @('aggregate.json', 'replay.json')) {
    $actual = (Get-FileHash -LiteralPath (Join-Path $runDir $name) -Algorithm SHA256).Hash.ToLower()
    if ($actual -ne $expectedAggregate) {
        throw "Review aggregate or replay changed: $name"
    }
}
$aggregate = Get-Content -LiteralPath (Join-Path $runDir 'aggregate.json') -Raw | ConvertFrom-Json
if ($aggregate.sampled_records -ne 200 -or $aggregate.reviewed_records -ne 0 -or $aggregate.unreviewed_records -ne 200) {
    throw 'Review counts differ from the frozen initialization'
}
Write-Output 'verified_empty_nyc_review_ledger'
