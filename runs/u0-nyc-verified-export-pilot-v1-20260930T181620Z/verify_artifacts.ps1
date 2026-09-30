$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$privateDir = Join-Path $projectRoot 'data\raw\nyc_dof\verified-export-pilot-v1-20260930T181620Z-70ed3ced7f7d'
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$runner = Join-Path $projectRoot 'scripts\verify_nyc_review_artifacts_v2.py'
& $python $runner replay $privateDir | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Protected comparison replay or privacy checks failed' }

function Get-Sha([string]$path) {
    return (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
}

$expectedPrivate = @{
    'intent.json' = '64b90c7ad529e1a4f7642ad0a1e4f658dd3ac5ec71ade067f011352c2e2629af'
    'result.json' = '84c69593fdeabc0afcd943071ad01e83f09013d31f7888f5a1f4b4d525060519'
    'public.json' = '6ad0e9dae7c55b69e966af179df30fb0033fcb041a053cfa01c8a4f36f5c78a2'
    'hash_manifest.json' = 'a40dfc53fb1b6ffc7bfabfa9ffefebeb7eea109f99f4301847d7af7b459b49fd'
}
$actualNames = @(Get-ChildItem -LiteralPath $privateDir -Force -Name | Sort-Object)
if (($actualNames -join ',') -ne ((@($expectedPrivate.Keys) | Sort-Object) -join ',')) {
    throw 'Protected comparison artifact inventory differs'
}
foreach ($name in $expectedPrivate.Keys) {
    if ((Get-Sha (Join-Path $privateDir $name)) -ne $expectedPrivate[$name]) {
        throw "Protected comparison artifact differs: $name"
    }
}

$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Raw | ConvertFrom-Json
$aggregate = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'aggregate.json') -Raw | ConvertFrom-Json
$gate = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'test_gate.json') -Raw | ConvertFrom-Json
$tracked = @{
    'environment_lock_sha256' = 'locks\nyc-verified-export-pilot-environment.json'
    'decision_sha256' = 'decisions\0036-nyc-verified-export-pilot.md'
    'core_sha256' = 'scripts\nyc_verified_export_core.py'
    'runner_sha256' = 'scripts\verify_nyc_review_artifacts_v2.py'
    'core_tests_sha256' = 'tests\test_nyc_verified_export_core.py'
    'runner_tests_sha256' = 'tests\test_verify_nyc_review_artifacts_v2.py'
}
foreach ($field in $tracked.Keys) {
    if ($manifest.$field -ne (Get-Sha (Join-Path $projectRoot $tracked[$field]))) {
        throw "Tracked code or protocol differs: $field"
    }
}
$evidence = @{
    'plan_sha256' = 'plan.json'
    'public_aggregate_sha256' = 'aggregate.json'
    'report_sha256' = 'report.md'
    'test_gate_sha256' = 'test_gate.json'
    'full_suite_log_sha256' = 'full_suite.log'
    'focused_tests_log_sha256' = 'focused_tests.log'
    'coverage_log_sha256' = 'coverage.log'
    'quality_checks_log_sha256' = 'quality_checks.log'
}
foreach ($field in $evidence.Keys) {
    if ($manifest.$field -ne (Get-Sha (Join-Path $PSScriptRoot $evidence[$field]))) {
        throw "Tracked evidence differs: $field"
    }
}
$fullLog = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'full_suite.log') -Raw
$focusedLog = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'focused_tests.log') -Raw
$coverageLog = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'coverage.log') -Raw
$plan = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'plan.json') -Raw | ConvertFrom-Json
if ($manifest.run_id -ne 'u0-nyc-verified-export-pilot-v1-20260930T181620Z' -or
    $manifest.protocol -ne 'nyc-verified-export-pilot-v1' -or
    $manifest.status -ne 'VERIFIED_PRIVATE_SAME_PUBLISHER_COMPARISON_ONLY' -or
    $manifest.code_commit -ne 'bbb881bd7a342dc302e3599df58867ee22c80314' -or
    $manifest.dirty_tree_at_analysis -or
    $manifest.source_sample_sha256 -ne 'e137de2cf73aa4a9fea6d024e4564ef6e907020e73fc8dbec3e4026786b189ca' -or
    $manifest.source_csv_snapshot_sha256 -ne '84c06057c52a2822f982cd98fb77ef7edf2c14134d00f46b073d2e4b762b2ef2' -or
    $manifest.source_capture_manifest_sha256 -ne 'e29928b44a1b1f733219dac86b8d7e18704bf8c301b458afc2bf1a53895bb9e2' -or
    $manifest.source_v3_result_sha256 -ne '61dcb9bce362658c475df5e43fa2407e18cb0d85779654941ab67bbb8ee00f83' -or
    $manifest.private_run_id -ne 'verified-export-pilot-v1-20260930T181620Z-70ed3ced7f7d' -or
    $manifest.private_intent_sha256 -ne $expectedPrivate['intent.json'] -or
    $manifest.private_result_sha256 -ne $expectedPrivate['result.json'] -or
    $manifest.private_public_sha256 -ne $expectedPrivate['public.json'] -or
    $manifest.private_hash_manifest_sha256 -ne $expectedPrivate['hash_manifest.json'] -or
    $manifest.public_aggregate_sha256 -ne $expectedPrivate['public.json'] -or
    $manifest.public_projection -ne 'private_only_v1' -or
    $manifest.sale_labels_certified -ne 0 -or
    $manifest.manual_reviews_completed -ne 0 -or
    $manifest.u0_gate -ne 'PENDING' -or
    $manifest.g_us_gate -ne 'PENDING' -or
    $gate.sale_labels_certified -ne 0 -or
    $gate.u0_gate -ne 'PENDING' -or
    $gate.g_us_gate -ne 'PENDING' -or
    $gate.checks.Count -ne 11 -or
    @($gate.checks | Where-Object { $_.exit_code -ne 0 }).Count -ne 0 -or
    $fullLog -notmatch '(?m)^Ran 786 tests in 186\.814s\r?$' -or
    $fullLog -notmatch '(?m)^OK\r?$' -or
    $focusedLog -notmatch '(?m)^Ran 16 tests in ' -or
    $focusedLog -notmatch '(?m)^Ran 21 tests in ' -or
    $coverageLog -notmatch '(?m)^TOTAL\s+318\s+23\s+106\s+14\s+91%') {
    throw 'Comparison manifest, tests, provenance or gate differs'
}
if ($plan.protocol -ne $manifest.protocol -or
    $plan.status -ne 'plan_only_no_private_read' -or
    $plan.sale_labels_certified -ne 0 -or
    $plan.label_status -ne 'unqualified' -or
    $plan.sample_sha256 -ne $manifest.source_sample_sha256 -or
    $plan.csv_snapshot_sha256 -ne $manifest.source_csv_snapshot_sha256 -or
    $plan.capture_manifest_sha256 -ne $manifest.source_capture_manifest_sha256 -or
    $plan.v3_result_sha256 -ne $manifest.source_v3_result_sha256) {
    throw 'Public comparison plan differs'
}
if ($aggregate.protocol -ne $manifest.protocol -or
    $aggregate.label_status -ne 'unqualified' -or
    $aggregate.sale_labels_certified -ne 0 -or
    $aggregate.boroughs.Count -ne 4) {
    throw 'Public comparison projection differs'
}
$expectedBoroughs = @('Bronx', 'Brooklyn', 'Queens', 'Staten Island')
for ($index = 0; $index -lt $expectedBoroughs.Count; $index++) {
    $entry = $aggregate.boroughs[$index]
    if ($entry.borough -ne $expectedBoroughs[$index] -or
        $null -ne $entry.findings -or
        $entry.suppression_reason -ne 'private_only_v1') {
        throw 'Public comparison suppression differs'
    }
}
Write-Output 'verified_nyc_private_export_comparison_zero_labels'
