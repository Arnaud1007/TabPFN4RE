$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$privateDir = Join-Path $projectRoot 'data\raw\nyc_dof\worksheet-inspection-20260929T080639Z-f6acd14ef745'
$expectedPrivate = @{
    'intent.json' = 'd20ea9ef1ae6e02b3fc43d2abd70592c916b6d0a7949782df634b4e8fee7daea'
    'result.json' = 'c2368f050a24a538f365e38d24115f8bb2f2254ddd2b73e54ad3844ac894c948'
    'hash_manifest.json' = '0573b8cfcadb9622378a214fe151fc79d08de23e8c990d0ab200fe8af9a9f8e5'
}
$names = @(Get-ChildItem -LiteralPath $privateDir -Force -Name | Sort-Object)
if (($names -join ',') -ne ((@($expectedPrivate.Keys) | Sort-Object) -join ',')) {
    throw 'Private inspection inventory differs from the frozen run'
}
foreach ($name in $expectedPrivate.Keys) {
    $actual = (Get-FileHash -LiteralPath (Join-Path $privateDir $name) -Algorithm SHA256).Hash.ToLower()
    if ($actual -ne $expectedPrivate[$name]) {
        throw "Private inspection hash differs: $name"
    }
}
$expectedPublic = @{
    'aggregate.json' = 'c2368f050a24a538f365e38d24115f8bb2f2254ddd2b73e54ad3844ac894c948'
    'replay.json' = 'a22b34f24df9066f2359cba45768ab4eabb40863682405fb889bfe49065da4da'
    'manifest.json' = '6894c88403dea558730ade7c4d94b99861d7f56071b162299b6842e8c02f8860'
}
foreach ($name in $expectedPublic.Keys) {
    $actual = (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $name) -Algorithm SHA256).Hash.ToLower()
    if ($actual -ne $expectedPublic[$name]) {
        throw "Public inspection hash differs: $name"
    }
}
$aggregate = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'aggregate.json') -Raw | ConvertFrom-Json
$replay = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'replay.json') -Raw | ConvertFrom-Json
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Raw | ConvertFrom-Json
if ($aggregate.protocol -ne 'nyc-borough-worksheet-inspection-v1' -or
    $manifest.protocol -ne 'nyc-borough-worksheet-inspection-v1' -or
    $manifest.code_commit -ne 'ea356c94671624b160104b8b4d77b39728a4ec93' -or
    $manifest.private_result_sha256 -ne $expectedPrivate['result.json'] -or
    $manifest.qualified_borough_count -ne 0 -or
    $aggregate.qualified_borough_count -ne 0 -or $aggregate.files.Count -ne 5 -or
    $replay.qualified_borough_count -ne 0 -or $replay.files.Count -ne 5 -or
    @($aggregate.files | Where-Object { $_.status -ne 'rejected_package' }).Count -ne 0 -or
    @($replay.files | Where-Object { $_.status -ne 'rejected_package' }).Count -ne 0) {
    throw 'Inspection or replay status differs from the frozen rejection'
}
Write-Output 'verified_nyc_worksheet_v1_replayed_source_rejection'
