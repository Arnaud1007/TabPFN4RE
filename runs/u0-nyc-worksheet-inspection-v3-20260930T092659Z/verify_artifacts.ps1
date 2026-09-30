$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$privateDir = Join-Path $projectRoot 'data\raw\nyc_dof\worksheet-inspection-v3-20260930T092659Z-6acaf2c84265'
$expectedPrivate = @{
    'intent.json' = '9bfa345ed8dbdb155fdc4b79395ef340e3cbfb40db365ea78047ab677a02a486'
    'result.json' = '61dcb9bce362658c475df5e43fa2407e18cb0d85779654941ab67bbb8ee00f83'
    'public.json' = 'f2a76cf11a47580f3534366474646695eb427ac2149370465955040863fdd314'
    'hash_manifest.json' = 'e375dbb7480ad909d5d49cbbf33d0a042549d53bcaeab303d4a4f3f9baa7e880'
}
$actualNames = @(Get-ChildItem -LiteralPath $privateDir -Force -Name | Sort-Object)
if (($actualNames -join ',') -ne ((@($expectedPrivate.Keys) | Sort-Object) -join ',')) {
    throw 'Private v3 inspection inventory differs'
}
foreach ($name in $expectedPrivate.Keys) {
    $actual = (Get-FileHash -LiteralPath (Join-Path $privateDir $name) -Algorithm SHA256).Hash.ToLower()
    if ($actual -ne $expectedPrivate[$name]) {
        throw "Private v3 inspection hash differs: $name"
    }
}
$aggregateHash = (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'aggregate.json') -Algorithm SHA256).Hash.ToLower()
if ($aggregateHash -ne $expectedPrivate['public.json']) {
    throw 'Public v3 aggregate differs from redacted private projection'
}
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Raw | ConvertFrom-Json
$aggregate = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'aggregate.json') -Raw | ConvertFrom-Json
$intent = Get-Content -LiteralPath (Join-Path $privateDir 'intent.json') -Raw | ConvertFrom-Json
$v3Lock = (Get-FileHash -LiteralPath (Join-Path $projectRoot 'locks\nyc-worksheet-v3-environment.json') -Algorithm SHA256).Hash.ToLower()
$v2Lock = (Get-FileHash -LiteralPath (Join-Path $projectRoot 'locks\nyc-workbook-inspection-environment.json') -Algorithm SHA256).Hash.ToLower()
if ($manifest.status -ne 'VERIFIED_FOUR_OF_FIVE_STRUCTURAL_ONLY' -or
    $manifest.code_commit -ne 'aae83e201710f8e5d04a40f64d44f6c1305bb7ed' -or
    $manifest.private_intent_sha256 -ne $expectedPrivate['intent.json'] -or
    $manifest.private_result_sha256 -ne $expectedPrivate['result.json'] -or
    $manifest.private_hash_manifest_sha256 -ne $expectedPrivate['hash_manifest.json'] -or
    $intent.code_commit -ne $manifest.code_commit -or $intent.dirty_tree -or
    $intent.environment_lock_sha256 -ne $v3Lock -or
    $intent.worksheet_inspection_environment_lock_sha256 -ne $v2Lock -or
    $aggregate.protocol -ne 'nyc-borough-worksheet-inspection-v3' -or
    $aggregate.worksheet_qualified_count -ne 4 -or
    $aggregate.label_status -ne 'unqualified' -or
    $aggregate.sale_labels_certified -ne 0 -or
    $aggregate.files.Count -ne 5 -or
    ($aggregate.files | Measure-Object physical_rows -Sum).Sum -ne 82370 -or
    ($aggregate.files | Measure-Object data_rows -Sum).Sum -ne 82345 -or
    @($aggregate.files | Where-Object {
        $_.header_status -ne 'exact_pinned_alias' -or
        $_.raw_header_sha256 -ne '4f8efb3fe379c1adb05938d397271d6c38002b6c2fdbe2224b3c4aa68d529e95' -or
        $_.sale_labels_certified -ne 0
    }).Count -ne 0 -or
    @($aggregate.files | Where-Object {
        $_.borough -eq 'Manhattan' -and
        ($_.status -ne 'unqualified' -or $_.formula_preamble -ne 1 -or $_.worksheet_qualified)
    }).Count -ne 0 -or
    @($aggregate.files | Where-Object {
        $_.borough -ne 'Manhattan' -and
        ($_.status -ne 'worksheet_qualified' -or $_.formula_cells -ne 0 -or -not $_.worksheet_qualified)
    }).Count -ne 0) {
    throw 'V3 inspection status differs from frozen structural-only result'
}
Write-Output 'verified_nyc_v3_four_structural_zero_labels'
