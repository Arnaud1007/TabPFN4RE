$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$privateDir = Join-Path $projectRoot 'data\raw\nyc_dof\header-diagnostic-20260930T075500Z-ab8936b58a5a'
$expectedPrivate = @{
    'intent.json' = 'eee1484b59d60fc8ecfc80884cafad4821b028333f0ecf6ff36fd089d33b8e18'
    'result.json' = 'cafb257e0321d5608dd13f175d866d1c39112d6cd0805e169f1aa2e4609a1ffb'
    'public.json' = 'd595267290ab703247bc8077221dd999cbde33f8b7450c9c7314785b464d7811'
    'hash_manifest.json' = '2a8b5a26bc937dbafe9aade3ba0b3b5a6570680e1e847f187705cbd05f98be94'
}
$actualNames = @(Get-ChildItem -LiteralPath $privateDir -Force -Name | Sort-Object)
if (($actualNames -join ',') -ne ((@($expectedPrivate.Keys) | Sort-Object) -join ',')) {
    throw 'Private verified header diagnostic inventory differs'
}
foreach ($name in $expectedPrivate.Keys) {
    $actual = (Get-FileHash -LiteralPath (Join-Path $privateDir $name) -Algorithm SHA256).Hash.ToLower()
    if ($actual -ne $expectedPrivate[$name]) {
        throw "Private verified header diagnostic hash differs: $name"
    }
}
$aggregateHash = (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'aggregate.json') -Algorithm SHA256).Hash.ToLower()
if ($aggregateHash -ne $expectedPrivate['public.json']) {
    throw 'Public aggregate differs from redacted private projection'
}
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Raw | ConvertFrom-Json
$aggregate = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'aggregate.json') -Raw | ConvertFrom-Json
$intent = Get-Content -LiteralPath (Join-Path $privateDir 'intent.json') -Raw | ConvertFrom-Json
$diagnosticLock = (Get-FileHash -LiteralPath (Join-Path $projectRoot 'locks\nyc-header-diagnostic-environment.json') -Algorithm SHA256).Hash.ToLower()
$inspectionLock = (Get-FileHash -LiteralPath (Join-Path $projectRoot 'locks\nyc-workbook-inspection-environment.json') -Algorithm SHA256).Hash.ToLower()
if ($manifest.status -ne 'VERIFIED_CANDIDATE_ONLY' -or
    $manifest.code_commit -ne '7d7ba0759e84bd4f7d5b127749ffece858ef3e4c' -or
    $manifest.private_intent_sha256 -ne $expectedPrivate['intent.json'] -or
    $manifest.private_result_sha256 -ne $expectedPrivate['result.json'] -or
    $manifest.private_hash_manifest_sha256 -ne $expectedPrivate['hash_manifest.json'] -or
    $intent.code_commit -ne $manifest.code_commit -or $intent.dirty_tree -or
    $intent.environment_lock_sha256 -ne $diagnosticLock -or
    $intent.worksheet_inspection_environment_lock_sha256 -ne $inspectionLock -or
    $aggregate.scope -ne 'candidate_only' -or
    $aggregate.label_status -ne 'unqualified' -or
    $aggregate.qualified_borough_count -ne 0 -or
    $aggregate.files.Count -ne 5 -or
    ($aggregate.files | Measure-Object physical_rows -Sum).Sum -ne 82370 -or
    @($aggregate.files | Where-Object {
        $_.status -ne 'candidate_found' -or
        $_.candidate.source_row_number -ne 5 -or
        $_.candidate.physical_ordinal -ne 5 -or
        $_.candidate.score -ne 20 -or
        $_.candidate.formula_cells -ne 0 -or
        $_.candidate.fingerprint_sha256 -ne '4f8efb3fe379c1adb05938d397271d6c38002b6c2fdbe2224b3c4aa68d529e95'
    }).Count -ne 0) {
    throw 'Verified header diagnostic status differs from frozen candidate-only result'
}
Write-Output 'verified_nyc_header_diagnostic_candidate_only'
