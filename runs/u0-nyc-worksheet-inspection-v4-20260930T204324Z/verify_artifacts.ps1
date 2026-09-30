$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$privateRoot = Join-Path $projectRoot 'data\raw\nyc_dof'
$source = Join-Path $privateRoot 'official-exports-20260929T033558Z-62ad417fb39f'
$privateRun = Join-Path $privateRoot 'worksheet-inspection-v4-20260930T204324Z-417da725ab3d'
$diagnosticRun = Join-Path $privateRoot 'manhattan-formula-v1-20260930T201602Z-6d714e014144'
$v3Run = Join-Path $privateRoot 'worksheet-inspection-v3-20260930T092659Z-6acaf2c84265'
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$v4Runner = Join-Path $projectRoot 'scripts\inspect_nyc_dof_borough_exports_v4.py'
$v3Runner = Join-Path $projectRoot 'scripts\inspect_nyc_dof_borough_exports_v3.py'

$v4Replay = & $python $v4Runner replay $source $privateRun | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Private v4 replay failed' }
$v3Replay = & $python $v3Runner replay $source $v3Run | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Preserved private v3 replay failed' }

$actualNames = @(Get-ChildItem -LiteralPath $privateRun -Force -Name | Sort-Object)
$expectedNames = @('hash_manifest.json', 'intent.json', 'public.json', 'result.json')
if (($actualNames -join ',') -ne ($expectedNames -join ',')) {
    throw 'Private v4 artifact inventory differs'
}

$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Raw | ConvertFrom-Json
$gate = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'test_gate.json') -Raw | ConvertFrom-Json
$public = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'aggregate.json') -Raw | ConvertFrom-Json
$intent = Get-Content -LiteralPath (Join-Path $privateRun 'intent.json') -Raw | ConvertFrom-Json
$diagnostic = Get-Content -LiteralPath (Join-Path $diagnosticRun 'result.json') -Raw | ConvertFrom-Json
$diagnosticHashes = Get-Content -LiteralPath (Join-Path $diagnosticRun 'hash_manifest.json') -Raw | ConvertFrom-Json

$checks = @{
    'public_aggregate_sha256' = Join-Path $PSScriptRoot 'aggregate.json'
    'plan_sha256' = Join-Path $PSScriptRoot 'plan.md'
    'report_sha256' = Join-Path $PSScriptRoot 'report.md'
    'test_gate_sha256' = Join-Path $PSScriptRoot 'test_gate.json'
    'full_suite_log_sha256' = Join-Path $projectRoot 'runs\u0-nyc-worksheet-v4-code-20260930T203800Z\full_suite.log'
    'decision_sha256' = Join-Path $projectRoot 'decisions\0039-nyc-manhattan-preamble-formula-v4.md'
    'runner_sha256' = $v4Runner
    'core_sha256' = Join-Path $projectRoot 'scripts\nyc_workbook_xml_v4.py'
    'runner_tests_sha256' = Join-Path $projectRoot 'tests\test_inspect_nyc_dof_borough_exports_v4.py'
    'core_tests_sha256' = Join-Path $projectRoot 'tests\test_nyc_workbook_xml_v4.py'
    'environment_lock_sha256' = Join-Path $projectRoot 'locks\nyc-worksheet-v3-environment.json'
    'capture_manifest_sha256' = Join-Path $source 'manifest.json'
    'manhattan_workbook_sha256' = Join-Path $source 'manhattan.xlsx'
}
foreach ($key in $checks.Keys) {
    $hash = (Get-FileHash -LiteralPath $checks[$key] -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($hash -ne $manifest.$key) { throw "V4 artifact differs: $key" }
}
$privatePublicHash = (Get-FileHash -LiteralPath (Join-Path $privateRun 'public.json') -Algorithm SHA256).Hash.ToLowerInvariant()
if ($privatePublicHash -ne $manifest.public_aggregate_sha256) {
    throw 'Private and public v4 projections differ'
}

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
    if (($diagnostic.formula.expression.Length -gt 0 -and $body.Contains($diagnostic.formula.expression)) -or
        $body.Contains($diagnosticHashes.result_sha256)) {
        throw 'Private Manhattan formula or fingerprint was published'
    }
}

if ($manifest.run_id -ne 'u0-nyc-worksheet-inspection-v4-20260930T204324Z' -or
    $manifest.protocol -ne 'nyc-borough-worksheet-inspection-v4' -or
    $manifest.status -ne 'VERIFIED_FIVE_OF_FIVE_STRUCTURAL_ONLY' -or
    $manifest.reviewed_code_commit -ne '80af77fdd4faafedafd7c0e85ecd3bf0d100a078' -or
    $manifest.analysis_commit -ne 'c1c2b5a82dc5f077b63e551ffecd99eb2c45b256' -or
    $manifest.dirty_tree_at_analysis -or
    $intent.code_commit -ne $manifest.analysis_commit -or
    $intent.dirty_tree -or
    $intent.environment_lock_sha256 -ne $manifest.environment_lock_sha256 -or
    $intent.capture_manifest_sha256 -ne $manifest.capture_manifest_sha256 -or
    $intent.diagnostic_run_id -ne $manifest.diagnostic_run_id -or
    $manifest.private_run_id -ne 'worksheet-inspection-v4-20260930T204324Z-417da725ab3d' -or
    $manifest.v3_worksheet_qualified_count -ne 4 -or
    $manifest.v4_worksheet_qualified_count -ne 5 -or
    $manifest.post_header_source_rows -ne 82345 -or
    $manifest.sale_labels_certified -ne 0 -or
    $manifest.u0_gate -ne 'PENDING' -or
    $manifest.g_us_gate -ne 'PENDING' -or
    $gate.status -ne 'PASS_FIVE_OF_FIVE_STRUCTURAL_ONLY' -or
    $gate.full_tests -ne 841 -or
    $gate.full_skipped -ne 0 -or
    $gate.full_exit_code -ne 0 -or
    $gate.v3_private_replay_exit_code -ne 0 -or
    $gate.v4_private_inspection_exit_code -ne 0 -or
    $gate.v4_offline_replay_exit_code -ne 0 -or
    $gate.sale_labels_certified -ne 0 -or
    $v3Replay.worksheet_qualified_count -ne 4 -or
    $v4Replay.worksheet_qualified_count -ne 5 -or
    $public.worksheet_qualified_count -ne 5 -or
    $public.label_status -ne 'unqualified' -or
    $public.sale_labels_certified -ne 0 -or
    $public.files.Count -ne 5) {
    throw 'V4 provenance, gate, or projection differs'
}

$expectedBoroughs = @('Manhattan', 'Bronx', 'Brooklyn', 'Queens', 'Staten Island')
for ($index = 0; $index -lt $expectedBoroughs.Count; $index++) {
    $file = $public.files[$index]
    if ($file.borough -ne $expectedBoroughs[$index] -or
        $file.status -ne 'worksheet_qualified' -or
        -not $file.worksheet_qualified -or
        $file.formula_exception_count -ne [int]($index -eq 0) -or
        $file.sale_labels_certified -ne 0 -or
        $file.PSObject.Properties.Name -contains 'formula') {
        throw 'V4 borough result or redaction differs'
    }
}
if ($public.files[0].v3_worksheet_qualified -or $v3Replay.files[0].worksheet_qualified) {
    throw 'Manhattan v3 result was retroactively changed'
}
$sourceRows = ($public.files | Measure-Object -Property data_rows -Sum).Sum
if ($sourceRows -ne 82345) { throw 'V4 source row count differs' }

Write-Output 'verified_nyc_v4_five_structural_zero_labels'
