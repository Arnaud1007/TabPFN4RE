$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$privateDir = Join-Path $projectRoot 'data\raw\nyc_dof\worksheet-inspection-20260929T091128Z-c241c261e987'
$expectedPrivate = @{
    'intent.json' = 'c6a51945f3e2bc5a203b481138e9f9b7ccb922a10170cf1d9a578a0cd8e3edbd'
    'result.json' = '9f137b893533d6184babf1f5adda9b8b6ad21bc13cb426be8d29fb7153a4ae03'
    'hash_manifest.json' = '0970179b9f68872136b2499b0f565d9eff91c1f691a60cf059e1661e8e8f8169'
}
$names = @(Get-ChildItem -LiteralPath $privateDir -Force -Name | Sort-Object)
if (($names -join ',') -ne ((@($expectedPrivate.Keys) | Sort-Object) -join ',')) {
    throw 'Private v2 inspection inventory differs from the frozen run'
}
foreach ($name in $expectedPrivate.Keys) {
    $actual = (Get-FileHash -LiteralPath (Join-Path $privateDir $name) -Algorithm SHA256).Hash.ToLower()
    if ($actual -ne $expectedPrivate[$name]) {
        throw "Private v2 inspection hash differs: $name"
    }
}
$expectedPublic = @{
    'aggregate.json' = '9f137b893533d6184babf1f5adda9b8b6ad21bc13cb426be8d29fb7153a4ae03'
    'replay.json' = '997f2ebabf045eb36b14d66b89bc951f7f74df52bb2c2e2a233f7b19fb875181'
    'manifest.json' = '496647b5d0820ac9de96d7482821d907cfb518afe8b604b680da87976b72f7fc'
}
foreach ($name in $expectedPublic.Keys) {
    $actual = (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $name) -Algorithm SHA256).Hash.ToLower()
    if ($actual -ne $expectedPublic[$name]) {
        throw "Public v2 inspection hash differs: $name"
    }
}
$aggregate = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'aggregate.json') -Raw | ConvertFrom-Json
$replay = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'replay.json') -Raw | ConvertFrom-Json
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Raw | ConvertFrom-Json
if ($aggregate.protocol -ne 'nyc-borough-worksheet-inspection-v2' -or
    $manifest.protocol -ne 'nyc-borough-worksheet-inspection-v2' -or
    $manifest.code_commit -ne '2a74e0f1cbcb63414399e3a1250581fa09c89122' -or
    $manifest.private_result_sha256 -ne $expectedPrivate['result.json'] -or
    $manifest.qualified_borough_count -ne 0 -or
    $aggregate.qualified_borough_count -ne 0 -or $aggregate.files.Count -ne 5 -or
    $replay.qualified_borough_count -ne 0 -or $replay.files.Count -ne 5 -or
    @($aggregate.files | Where-Object { $_.status -ne 'unqualified' -or $_.header_status -ne 'mismatch' }).Count -ne 0 -or
    @($replay.files | Where-Object { $_.status -ne 'unqualified' -or $_.header_status -ne 'mismatch' }).Count -ne 0 -or
    ($aggregate.files | Measure-Object physical_rows -Sum).Sum -ne 82370 -or
    ($replay.files | Measure-Object physical_rows -Sum).Sum -ne 82370) {
    throw 'V2 inspection or replay status differs from frozen header mismatch'
}
Write-Output 'verified_nyc_worksheet_v2_replayed_header_mismatch'
