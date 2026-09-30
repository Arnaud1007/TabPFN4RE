$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$privateDir = Join-Path $projectRoot 'data\raw\nyc_dof\row-concordance-v1-20260930T132740Z-93eb58530149'
$expected = @{
    'intent.json' = 'c10ad7081062043e1116a1b83c94069aba6b95302eeb5b272180d0cd304685b5'
    'result.json' = '5fd432e081911ff47df78bf183a40df99da00077d0e666175ca79840f18451ee'
    'public.json' = '4d52add2b6a65df050c9bf0a920e0f9ccc4e7fad8959f1d7e6c1154fb84ea524'
    'hash_manifest.json' = '3d454e3b7dcd6ec0ab9d2d6e3766b16ab61da7aa1cd00573f323b7d46ac6ca7b'
}
$actualNames = @(Get-ChildItem -LiteralPath $privateDir -Force -Name | Sort-Object)
if (($actualNames -join ',') -ne ((@($expected.Keys) | Sort-Object) -join ',')) {
    throw 'Private concordance artifact inventory differs'
}
foreach ($name in $expected.Keys) {
    $actual = (Get-FileHash -LiteralPath (Join-Path $privateDir $name) -Algorithm SHA256).Hash.ToLower()
    if ($actual -ne $expected[$name]) { throw "Private concordance artifact differs: $name" }
}
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Raw | ConvertFrom-Json
$aggregatePath = Join-Path $PSScriptRoot 'aggregate.json'
$aggregate = Get-Content -LiteralPath $aggregatePath -Raw | ConvertFrom-Json
$intent = Get-Content -LiteralPath (Join-Path $privateDir 'intent.json') -Raw | ConvertFrom-Json
$hashes = Get-Content -LiteralPath (Join-Path $privateDir 'hash_manifest.json') -Raw | ConvertFrom-Json
$aggregateHash = (Get-FileHash -LiteralPath $aggregatePath -Algorithm SHA256).Hash.ToLower()
$reportHash = (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'report.md') -Algorithm SHA256).Hash.ToLower()
$testGateHash = (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'test_gate.json') -Algorithm SHA256).Hash.ToLower()
$lockHash = (Get-FileHash -LiteralPath (Join-Path $projectRoot 'locks\nyc-row-concordance-environment.json') -Algorithm SHA256).Hash.ToLower()
if ($manifest.status -ne 'VERIFIED_EXACT_CONCORDANCE_NOT_DEMONSTRATED' -or
    $manifest.code_commit -ne '642f6afa284b444b342535ef4b241c3d75fd6932' -or
    $manifest.private_intent_sha256 -ne $expected['intent.json'] -or
    $manifest.private_result_sha256 -ne $expected['result.json'] -or
    $manifest.private_public_sha256 -ne $expected['public.json'] -or
    $manifest.private_hash_manifest_sha256 -ne $expected['hash_manifest.json'] -or
    $manifest.public_aggregate_sha256 -ne $aggregateHash -or
    $manifest.report_sha256 -ne '60d81039e6e61cb93e68fa40c33911baeaaa3b3d83df6b7e512437f2c5b90763' -or
    $manifest.test_gate_sha256 -ne '4333c771b0dd06186893fc99c415ec7ada45d4aa002b3f478486fd4df05fbb8f' -or
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
    $aggregate.csv_frame_rows -ne 62792 -or
    $aggregate.xlsx_frame_rows -ne 62792 -or
    $aggregate.boroughs.Count -ne 4 -or
    $aggregate.sale_labels_certified -ne 0) {
    throw 'Concordance manifest, provenance or frame differs'
}
foreach ($borough in @('Bronx', 'Brooklyn', 'Queens')) {
    $item = @($aggregate.boroughs | Where-Object { $_.borough -eq $borough })
    if ($item.Count -ne 1 -or
        $item[0].counts.unique_key_pairs -ne 0 -or
        $item[0].counts.exact_full_row_multiset_matches -ne 0 -or
        $item[0].sale_labels_certified -ne 0) {
        throw "Public concordance result differs: $borough"
    }
}
$staten = @($aggregate.boroughs | Where-Object { $_.borough -eq 'Staten Island' })
if ($staten.Count -ne 1 -or
    $null -ne $staten[0].counts -or
    $staten[0].suppression_reason -ne 'small_positive_cell_1_to_4' -or
    $staten[0].sale_labels_certified -ne 0) {
    throw 'Staten Island suppression differs'
}
Write-Output 'verified_nyc_v1_exact_mismatch_zero_labels'
