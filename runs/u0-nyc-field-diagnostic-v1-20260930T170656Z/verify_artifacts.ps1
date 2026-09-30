$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$privateDir = Join-Path $projectRoot 'data\raw\nyc_dof\field-diagnostic-v1-20260930T170656Z-f94fe9bb66b3'
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$analyzer = Join-Path $projectRoot 'scripts\diagnose_nyc_representation_fields_v1.py'
& $python $analyzer replay $privateDir | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Protected field diagnostic replay or privacy checks failed' }
$expectedPrivate = @{
    'intent.json' = '5b7df90539122602add45e2720a5ce619872e86b7300cd57f8509f2ecc83b636'
    'result.json' = '6a9361a7e4b9985f9ee855cd0720ee23b69cc521895012b2be4bb9ae4e27bbd8'
    'public.json' = '86758481e8a47f0a516d9a826e39a3b5da33cbacb04dcebf037a13191610c5cd'
    'hash_manifest.json' = '86b9029b470651649ee53a2a1c67644552864a233a4b7d9151eae74b3f836028'
}
$actualNames = @(Get-ChildItem -LiteralPath $privateDir -Force -Name | Sort-Object)
if (($actualNames -join ',') -ne ((@($expectedPrivate.Keys) | Sort-Object) -join ',')) {
    throw 'Protected field diagnostic artifact inventory differs'
}
foreach ($name in $expectedPrivate.Keys) {
    $actualHash = (Get-FileHash -LiteralPath (Join-Path $privateDir $name) -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $expectedPrivate[$name]) { throw "Protected field diagnostic artifact differs: $name" }
}

$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Raw | ConvertFrom-Json
$aggregatePath = Join-Path $PSScriptRoot 'aggregate.json'
$aggregate = Get-Content -LiteralPath $aggregatePath -Raw | ConvertFrom-Json
$testGate = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'test_gate.json') -Raw | ConvertFrom-Json
$fullSuiteLogPath = Join-Path $PSScriptRoot 'full_suite.log'
$aggregateHash = (Get-FileHash -LiteralPath $aggregatePath -Algorithm SHA256).Hash.ToLowerInvariant()
$reportHash = (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'report.md') -Algorithm SHA256).Hash.ToLowerInvariant()
$testGateHash = (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'test_gate.json') -Algorithm SHA256).Hash.ToLowerInvariant()
$fullSuiteLogHash = (Get-FileHash -LiteralPath $fullSuiteLogPath -Algorithm SHA256).Hash.ToLowerInvariant()
$fullSuiteLog = Get-Content -LiteralPath $fullSuiteLogPath -Raw
$loggedSuite = @($testGate.checks | Where-Object { $_.output_artifact -eq 'runs/u0-nyc-field-diagnostic-v1-20260930T170656Z/full_suite.log' })
$lockHash = (Get-FileHash -LiteralPath (Join-Path $projectRoot 'locks\nyc-v2-field-diagnostic-environment.json') -Algorithm SHA256).Hash.ToLowerInvariant()
$analyzerHash = (Get-FileHash -LiteralPath (Join-Path $projectRoot 'scripts\diagnose_nyc_representation_fields_v1.py') -Algorithm SHA256).Hash.ToLowerInvariant()
$testsHash = (Get-FileHash -LiteralPath (Join-Path $projectRoot 'tests\test_nyc_representation_fields_v1.py') -Algorithm SHA256).Hash.ToLowerInvariant()
$decisionHash = (Get-FileHash -LiteralPath (Join-Path $projectRoot 'decisions\0035-nyc-v2-field-diagnostic.md') -Algorithm SHA256).Hash.ToLowerInvariant()
if ($manifest.run_id -ne 'u0-nyc-field-diagnostic-v1-20260930T170656Z' -or
    $manifest.protocol -ne 'nyc-dof-v2-field-diagnostic-v1' -or
    $manifest.status -ne 'VERIFIED_PRIVATE_FIELD_DIAGNOSTIC_ONLY' -or
    $manifest.code_commit -ne 'adbb1e1fc3f726d2e51047dbf17cb808cdb6d0d0' -or
    $manifest.dirty_tree_at_analysis -or
    $manifest.environment_lock_sha256 -ne $lockHash -or
    $manifest.analyzer_sha256 -ne $analyzerHash -or
    $manifest.tests_sha256 -ne $testsHash -or
    $manifest.decision_sha256 -ne $decisionHash -or
    $manifest.source_v2_run_id -ne 'representation-diagnostic-v2-20260930T152830Z-460cba306f9d' -or
    $manifest.source_v2_result_sha256 -ne '2b7b7643c6b07a763e0e3cd842b5f60b2819805acb50341d485c7aa910141199' -or
    $manifest.private_run_id -ne 'field-diagnostic-v1-20260930T170656Z-f94fe9bb66b3' -or
    $manifest.private_intent_sha256 -ne $expectedPrivate['intent.json'] -or
    $manifest.private_result_sha256 -ne $expectedPrivate['result.json'] -or
    $manifest.private_public_sha256 -ne $expectedPrivate['public.json'] -or
    $manifest.private_hash_manifest_sha256 -ne $expectedPrivate['hash_manifest.json'] -or
    $manifest.public_aggregate_sha256 -ne $aggregateHash -or
    $aggregateHash -ne $expectedPrivate['public.json'] -or
    $manifest.report_sha256 -ne $reportHash -or
    $manifest.test_gate_sha256 -ne $testGateHash -or
    $manifest.full_suite_log_sha256 -ne $fullSuiteLogHash -or
    $loggedSuite.Count -ne 1 -or
    $loggedSuite[0].output_sha256 -ne $fullSuiteLogHash -or
    $loggedSuite[0].exit_code -ne 0 -or
    $fullSuiteLog -notmatch '(?m)^Ran 749 tests in 147\.323s\r?$' -or
    $fullSuiteLog -notmatch '(?m)^OK\r?$' -or
    $manifest.public_projection -ne 'private_only_v1' -or
    $manifest.sale_labels_certified -ne 0 -or
    $manifest.u0_gate -ne 'PENDING' -or
    $manifest.g_us_gate -ne 'PENDING' -or
    $testGate.sale_labels_certified -ne 0 -or
    $testGate.u0_gate -ne 'PENDING' -or
    $testGate.g_us_gate -ne 'PENDING') {
    throw 'Field diagnostic manifest, provenance or gate differs'
}
if ($aggregate.protocol -ne $manifest.protocol -or
    $aggregate.v2_result_sha256 -ne $manifest.source_v2_result_sha256 -or
    $aggregate.label_status -ne 'unqualified' -or
    $aggregate.sale_labels_certified -ne 0 -or
    $aggregate.boroughs.Count -ne 4) {
    throw 'Public field diagnostic projection differs'
}
$expectedBoroughs = @('Bronx', 'Brooklyn', 'Queens', 'Staten Island')
for ($index = 0; $index -lt $expectedBoroughs.Count; $index++) {
    $entry = $aggregate.boroughs[$index]
    if ($entry.borough -ne $expectedBoroughs[$index] -or
        $null -ne $entry.flags -or
        $null -ne $entry.disagreement_headers -or
        $entry.suppression_reason -ne 'private_only_v1') {
        throw 'Public field diagnostic suppression differs'
    }
}
Write-Output 'verified_nyc_private_field_diagnostic_zero_labels'
