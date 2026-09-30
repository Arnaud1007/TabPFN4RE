$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$privateDir = Join-Path $projectRoot 'data\raw\nyc_dof\representation-diagnostic-v2-20260930T152830Z-460cba306f9d'
$expected = @{
    'intent.json' = '1b87392277fd57298192bbd037c0b3f5805b0119554bdcac4a90a41e45e6624a'
    'result.json' = '2b7b7643c6b07a763e0e3cd842b5f60b2819805acb50341d485c7aa910141199'
    'public.json' = 'e3ae01bd7d551a66cf84f8862668e90f0a4071c3352ce8ac622d22938c4d766f'
    'hash_manifest.json' = 'a0cba0b35b4d9cc683d2df64119d05f16212e74cf372a7735b640443fe222fe1'
}
$actualNames = @(Get-ChildItem -LiteralPath $privateDir -Force -Name | Sort-Object)
if (($actualNames -join ',') -ne ((@($expected.Keys) | Sort-Object) -join ',')) {
    throw 'Private representation artifact inventory differs'
}
foreach ($name in $expected.Keys) {
    $actual = (Get-FileHash -LiteralPath (Join-Path $privateDir $name) -Algorithm SHA256).Hash.ToLower()
    if ($actual -ne $expected[$name]) { throw "Private representation artifact differs: $name" }
}
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Raw | ConvertFrom-Json
$aggregatePath = Join-Path $PSScriptRoot 'aggregate.json'
$aggregate = Get-Content -LiteralPath $aggregatePath -Raw | ConvertFrom-Json
$testGate = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'test_gate.json') -Raw | ConvertFrom-Json
$intent = Get-Content -LiteralPath (Join-Path $privateDir 'intent.json') -Raw | ConvertFrom-Json
$hashes = Get-Content -LiteralPath (Join-Path $privateDir 'hash_manifest.json') -Raw | ConvertFrom-Json
$aggregateHash = (Get-FileHash -LiteralPath $aggregatePath -Algorithm SHA256).Hash.ToLower()
$reportHash = (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'report.md') -Algorithm SHA256).Hash.ToLower()
$testGateHash = (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'test_gate.json') -Algorithm SHA256).Hash.ToLower()
$lockHash = (Get-FileHash -LiteralPath (Join-Path $projectRoot 'locks\nyc-representation-diagnostic-v2-environment.json') -Algorithm SHA256).Hash.ToLower()
if ($manifest.status -ne 'VERIFIED_REPRESENTATION_CANDIDATES_ONLY' -or
    $manifest.code_commit -ne 'cbbc14e3f3351b75a32956e4841f219fba314745' -or
    $manifest.private_intent_sha256 -ne $expected['intent.json'] -or
    $manifest.private_result_sha256 -ne $expected['result.json'] -or
    $manifest.private_public_sha256 -ne $expected['public.json'] -or
    $manifest.private_hash_manifest_sha256 -ne $expected['hash_manifest.json'] -or
    $manifest.public_aggregate_sha256 -ne $aggregateHash -or
    $manifest.report_sha256 -ne 'c24ed79f973ff210c6c288a1fd264cc48d4cf43e295443a1ba0cf1f184889d46' -or
    $manifest.test_gate_sha256 -ne 'a3b135c5e48213eb431b7d68617d3fc3f6659e823232ab7ce18947730dcc2d73' -or
    $reportHash -ne $manifest.report_sha256 -or
    $testGateHash -ne $manifest.test_gate_sha256 -or
    $manifest.environment_lock_sha256 -ne $lockHash -or
    $aggregateHash -ne $expected['public.json'] -or
    $hashes.intent_sha256 -ne $expected['intent.json'] -or
    $hashes.result_sha256 -ne $expected['result.json'] -or
    $hashes.public_sha256 -ne $expected['public.json'] -or
    $intent.code_commit -ne $manifest.code_commit -or
    $intent.dirty_tree -or
    $intent.environment_lock_sha256 -ne $lockHash -or
    $testGate.sale_labels_certified -ne 0 -or
    $aggregate.csv_frame_rows -ne 62792 -or
    $aggregate.xlsx_frame_rows -ne 62792 -or
    $aggregate.boroughs.Count -ne 4 -or
    $aggregate.sale_labels_certified -ne 0) {
    throw 'Representation manifest, provenance or frame differs'
}
$expectedPublic = @{
    Bronx = @{ rows = 6424; pairs = 6242; format = 1483 }
    Brooklyn = @{ rows = 23041; pairs = 22599; format = 8425 }
    Queens = @{ rows = 26461; pairs = 26184; format = 8960 }
}
foreach ($borough in @('Bronx', 'Brooklyn', 'Queens')) {
    $item = @($aggregate.boroughs | Where-Object { $_.borough -eq $borough })
    $fixed = $expectedPublic[$borough]
    if ($item.Count -ne 1 -or
        $item[0].csv_rows -ne $fixed.rows -or
        $item[0].xlsx_rows -ne $fixed.rows -or
        $item[0].counts.tiers.K0.unique_candidate_edges -ne 0 -or
        $item[0].counts.tiers.K1.unique_candidate_edges -ne $fixed.pairs -or
        $item[0].counts.tiers.K2.unique_candidate_edges -ne 0 -or
        $item[0].counts.tiers.K3.unique_candidate_edges -ne $fixed.pairs -or
        $item[0].counts.tiers.K4.unique_candidate_edges -ne $fixed.pairs -or
        $item[0].counts.isolated_pairs -ne $fixed.pairs -or
        $item[0].counts.format_only_candidates -ne $fixed.format -or
        $item[0].sale_labels_certified -ne 0) {
        throw "Public representation result differs: $borough"
    }
}
$staten = @($aggregate.boroughs | Where-Object { $_.borough -eq 'Staten Island' })
if ($staten.Count -ne 1 -or
    $staten[0].csv_rows -ne 6866 -or
    $staten[0].xlsx_rows -ne 6866 -or
    $null -ne $staten[0].counts -or
    $staten[0].suppression_reason -ne 'staten_cross_version_protection' -or
    $staten[0].sale_labels_certified -ne 0) {
    throw 'Staten Island suppression differs'
}
Write-Output 'verified_nyc_v2_representation_candidates_zero_labels'
