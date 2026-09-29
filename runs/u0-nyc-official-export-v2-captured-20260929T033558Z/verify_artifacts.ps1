$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$privateDir = Join-Path $projectRoot 'data\raw\nyc_dof\official-exports-20260929T033558Z-62ad417fb39f'
$expected = @{
    'bronx.xlsx' = 'd8e1490eec2555dc0094979da0a56b71ee367f78ab760fb4b01ea89867d542d5'
    'brooklyn.xlsx' = '4d609a75ceb49a753def6ef203fe8f923fb8893d04eb4cd578393c733f27daae'
    'intent.json' = '7c53d74270afe27a2c72d71a1099561992957957ae4602b0b982cec7313a5805'
    'manhattan.xlsx' = '8903566fa59c9ce4c2b427ce24e268cc448d8c04f8c779839df942f29a05397a'
    'manifest.json' = 'e29928b44a1b1f733219dac86b8d7e18704bf8c301b458afc2bf1a53895bb9e2'
    'queens.xlsx' = '0852a3c9b8a05e31b4850aae6d6a1bbf201b8e29e6f2f00b29e50ad1be1adcf9'
    'receipt-bronx.json' = 'e09e69c0bf894a35b584be71dc8d91571055ed155e37222c02b186fc9f832bb7'
    'receipt-brooklyn.json' = '1d68fd24544078680963c81dc6f029327c910b1ce65b2ae722fc9dcb71c8cedd'
    'receipt-manhattan.json' = '4458126757460640cf0128787dd3ed44f1f971613cc089ac4547e5ce84926f9d'
    'receipt-queens.json' = '71234a1c8c2d72b44434cc18b839a4d26fce481dcf3e10561c4a7f6ea69b8312'
    'receipt-staten_island.json' = '149eda275826712669ec95ec7b1d0fe886f9e6416053960207fe53febf5ed5f1'
    'staten_island.xlsx' = '2590b4119fdfb3b05b5fdde72ef039726ce5f404e3d9245e7c9f07bc36a0b455'
}
$names = @(Get-ChildItem -LiteralPath $privateDir -Force -Name | Sort-Object)
if (($names -join ',') -ne ((@($expected.Keys) | Sort-Object) -join ',')) {
    throw 'Private capture inventory differs from the frozen run'
}
foreach ($name in $expected.Keys) {
    $actual = (Get-FileHash -LiteralPath (Join-Path $privateDir $name) -Algorithm SHA256).Hash.ToLower()
    if ($actual -ne $expected[$name]) {
        throw "Private capture hash differs: $name"
    }
}
$replay = Join-Path $PSScriptRoot 'replay.json'
$replayHash = (Get-FileHash -LiteralPath $replay -Algorithm SHA256).Hash.ToLower()
if ($replayHash -ne '94921f4eb7dc7727199b182176ae01b71c0b0f254077f1d04a1fe40b59b67572') {
    throw 'Public offline replay hash differs'
}
$privateManifest = Get-Content -LiteralPath (Join-Path $privateDir 'manifest.json') -Raw | ConvertFrom-Json
if ($privateManifest.bundle_status -ne 'bytes_captured_content_unqualified' -or
    $privateManifest.protocol -ne 'nyc-official-borough-xlsx-v2' -or
    $privateManifest.user_agent -ne 'TabPFN4RealEstate-U0/1.0' -or
    $privateManifest.code_commit -ne '841e20ec9127ae2126b8496870d07e4f27159a62' -or
    $privateManifest.dirty_tree -ne $false -or
    $privateManifest.files.Count -ne 5) {
    throw 'Private capture manifest does not match the frozen v2 status'
}
$totalBytes = ($privateManifest.files | Measure-Object -Property bytes -Sum).Sum
if ($totalBytes -ne 8094187) {
    throw 'Private workbook byte total differs'
}
Write-Output 'verified_nyc_official_export_v2_bytes_content_unqualified'
