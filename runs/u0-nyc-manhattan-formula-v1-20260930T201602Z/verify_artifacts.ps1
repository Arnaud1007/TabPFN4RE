$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$privateRoot = Join-Path $projectRoot 'data\raw\nyc_dof'
$source = Join-Path $privateRoot 'official-exports-20260929T033558Z-62ad417fb39f'
$privateRun = Join-Path $privateRoot 'manhattan-formula-v1-20260930T201602Z-6d714e014144'
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$runner = Join-Path $projectRoot 'scripts\diagnose_nyc_manhattan_formula_v1.py'

& $python $runner replay $source $privateRun | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Private Manhattan diagnostic replay failed' }

$actualNames = @(Get-ChildItem -LiteralPath $privateRun -Force -Name | Sort-Object)
$expectedNames = @('hash_manifest.json', 'intent.json', 'public.json', 'result.json')
if (($actualNames -join ',') -ne ($expectedNames -join ',')) {
    throw 'Private Manhattan diagnostic artifact inventory differs'
}

$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Raw | ConvertFrom-Json
$gate = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'test_gate.json') -Raw | ConvertFrom-Json
$public = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'aggregate.json') -Raw | ConvertFrom-Json
$intent = Get-Content -LiteralPath (Join-Path $privateRun 'intent.json') -Raw | ConvertFrom-Json

$checks = @{
    'public_aggregate_sha256' = Join-Path $PSScriptRoot 'aggregate.json'
    'plan_sha256' = Join-Path $PSScriptRoot 'plan.md'
    'report_sha256' = Join-Path $PSScriptRoot 'report.md'
    'test_gate_sha256' = Join-Path $PSScriptRoot 'test_gate.json'
    'full_suite_log_sha256' = Join-Path $projectRoot 'runs\u0-nyc-manhattan-formula-code-20260930T201000Z\full_suite.log'
    'decision_sha256' = Join-Path $projectRoot 'decisions\0038-nyc-manhattan-preamble-formula-diagnostic.md'
    'runner_sha256' = $runner
    'xml_reader_sha256' = Join-Path $projectRoot 'scripts\nyc_manhattan_formula_xml_v1.py'
    'runner_tests_sha256' = Join-Path $projectRoot 'tests\test_diagnose_nyc_manhattan_formula_v1.py'
    'xml_tests_sha256' = Join-Path $projectRoot 'tests\test_nyc_manhattan_formula_xml_v1.py'
    'environment_lock_sha256' = Join-Path $projectRoot 'locks\nyc-worksheet-v3-environment.json'
    'capture_manifest_sha256' = Join-Path $source 'manifest.json'
    'manhattan_workbook_sha256' = Join-Path $source 'manhattan.xlsx'
}
foreach ($key in $checks.Keys) {
    $hash = (Get-FileHash -LiteralPath $checks[$key] -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($hash -ne $manifest.$key) { throw "Manhattan diagnostic artifact differs: $key" }
}
$privatePublicHash = (Get-FileHash -LiteralPath (Join-Path $privateRun 'public.json') -Algorithm SHA256).Hash.ToLowerInvariant()
if ($privatePublicHash -ne $manifest.public_aggregate_sha256) {
    throw 'Private and public Manhattan projections differ'
}
$privateResult = Get-Content -LiteralPath (Join-Path $privateRun 'result.json') -Raw | ConvertFrom-Json
$privateHashes = Get-Content -LiteralPath (Join-Path $privateRun 'hash_manifest.json') -Raw | ConvertFrom-Json
$publishedPaths = @(
    (Join-Path $PSScriptRoot 'plan.md'),
    (Join-Path $PSScriptRoot 'report.md'),
    (Join-Path $PSScriptRoot 'test_gate.json'),
    (Join-Path $PSScriptRoot 'manifest.json'),
    (Join-Path $PSScriptRoot 'aggregate.json'),
    (Join-Path $projectRoot 'requirements.yaml'),
    (Join-Path $projectRoot 'next_action.md')
)
foreach ($path in $publishedPaths) {
    $body = Get-Content -LiteralPath $path -Raw
    if (($privateResult.formula.expression.Length -gt 0 -and $body.Contains($privateResult.formula.expression)) -or
        $body.Contains($privateHashes.result_sha256)) {
        throw 'Manhattan private formula or fingerprint was published'
    }
}

if ($manifest.run_id -ne 'u0-nyc-manhattan-formula-v1-20260930T201602Z' -or
    $manifest.protocol -ne 'nyc-manhattan-formula-diagnostic-v1' -or
    $manifest.status -ne 'VERIFIED_PRIVATE_DIAGNOSTIC_ONLY' -or
    $manifest.reviewed_code_commit -ne 'dc9cf39c0789df8ac758048c926846e9beea2603' -or
    $manifest.analysis_commit -ne 'a38edfd5d15ebb45e6e02a462b5f67e23b0ce2cc' -or
    $manifest.dirty_tree_at_analysis -or
    $intent.code_commit -ne $manifest.analysis_commit -or
    $intent.dirty_tree -or
    $intent.environment_lock_sha256 -ne $manifest.environment_lock_sha256 -or
    $intent.capture_manifest_sha256 -ne $manifest.capture_manifest_sha256 -or
    $intent.manhattan_sha256 -ne $manifest.manhattan_workbook_sha256 -or
    $manifest.private_run_id -ne 'manhattan-formula-v1-20260930T201602Z-6d714e014144' -or
    $manifest.sale_labels_certified -ne 0 -or
    $manifest.u0_gate -ne 'PENDING' -or
    $manifest.g_us_gate -ne 'PENDING' -or
    $gate.status -ne 'PASS_DIAGNOSTIC_ONLY' -or
    $gate.full_tests -ne 829 -or
    $gate.full_skipped -ne 1 -or
    $gate.full_exit_code -ne 0 -or
    $gate.private_diagnostic_exit_code -ne 0 -or
    $gate.offline_replay_exit_code -ne 0 -or
    $gate.sale_labels_certified -ne 0 -or
    $public.protocol -ne $manifest.protocol -or
    $public.projection -ne 'private_only_v1' -or
    -not $public.diagnostic_completed -or
    $public.v3_worksheet_qualified -or
    $public.sale_labels_certified -ne 0) {
    throw 'Manhattan diagnostic provenance, test gate or public projection differs'
}

Write-Output 'verified_private_manhattan_formula_diagnostic_zero_labels'
