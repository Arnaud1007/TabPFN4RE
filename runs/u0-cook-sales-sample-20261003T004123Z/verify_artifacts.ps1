$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$aggregate = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'aggregate.json') -Raw | ConvertFrom-Json
$gate = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'test_gate.json') -Raw | ConvertFrom-Json
$postReview = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'post_review_check.json') -Raw | ConvertFrom-Json
$private = Join-Path $projectRoot 'data\raw\cook_county\cook-sales-v1-20261003T004123.032937Z-c08de13e9f1d'

function Get-LowerHash([string]$path) {
    return (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
}

if ($aggregate.run_id -ne 'u0-cook-sales-sample-20261003T004123Z' -or
    $aggregate.code_commit -ne '4851fb9dc86f38262a7a170a36f2332c514729b5' -or
    $aggregate.sample_rows -ne 200 -or
    $aggregate.manual_rubrics_complete -ne 0 -or
    $aggregate.certified_sale_labels -ne 0 -or
    $aggregate.historical_asof_eligible -or
    $aggregate.primary_90_day_close_origin_eligible -or
    $gate.status -ne 'PASS' -or
    $gate.u0_gate -ne 'PENDING' -or
    $gate.g_us_gate -ne 'PENDING' -or
    @($gate.results).Count -ne 10) {
    throw 'Cook sample public evidence differs from the pinned run'
}
if ((Get-LowerHash (Join-Path $private 'manifest.json')) -ne $aggregate.data_snapshot_sha256 -or
    (Get-LowerHash (Join-Path $private 'metadata-before.json')) -ne $aggregate.source_metadata_sha256 -or
    (Get-LowerHash (Join-Path $PSScriptRoot 'environment_lock.txt')) -ne $aggregate.environment_lock_sha256 -or
    (Get-LowerHash (Join-Path $projectRoot 'decisions\0051-cook-sales-private-audit-sample.md')) -ne $aggregate.configuration_sha256) {
    throw 'Cook sample source, protocol or environment hash differs'
}
foreach ($result in $gate.results) {
    if ($result.exit_code -ne 0 -or
        [IO.Path]::GetFileName([string]$result.output) -ne $result.output -or
        (Get-LowerHash (Join-Path $PSScriptRoot $result.output)) -ne $result.output_sha256) {
        throw "Cook sample gate output differs: $($result.name)"
    }
}
if ($postReview.run_id -ne $aggregate.run_id -or
    $postReview.status -ne 'PASS' -or
    -not $postReview.original_gate_unchanged -or
    @($postReview.checks).Count -ne 3 -or
    (Get-LowerHash (Join-Path $PSScriptRoot 'rebuild_aggregate.py')) -ne $postReview.rebuild_aggregate_sha256 -or
    (Get-LowerHash (Join-Path $projectRoot 'tests\test_cook_aggregate_privacy.py')) -ne $postReview.privacy_tests_sha256) {
    throw 'Cook post-review check differs from the current code'
}
foreach ($result in $postReview.checks) {
    if ($result.exit_code -ne 0 -or
        [IO.Path]::GetFileName([string]$result.output) -ne $result.output -or
        (Get-LowerHash (Join-Path $PSScriptRoot $result.output)) -ne $result.output_sha256) {
        throw "Cook post-review output differs: $($result.name)"
    }
}
Push-Location $projectRoot
try {
    $replay = & $python 'scripts/capture_cook_sales_audit.py' --verify $private | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or $replay.sample_rows -ne 200 -or $replay.historical_asof_eligible) {
        throw 'Private Cook response replay failed'
    }
    & $python 'runs/u0-cook-sales-sample-20261003T004123Z/rebuild_aggregate.py' --check | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Cook public aggregate replay failed' }
}
finally { Pop-Location }
Write-Output 'Cook private sample and public evidence verified; zero labels certified; U0 and G-US pending'
