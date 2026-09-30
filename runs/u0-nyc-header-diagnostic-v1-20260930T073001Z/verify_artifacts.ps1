$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$privateDir = Join-Path $projectRoot 'data\raw\nyc_dof\header-diagnostic-20260930T073001Z-79529824f388'
$expectedPrivate = @{
    'intent.json' = 'c33191acee2fa1f275f59e306c8767e8804957c49f2a190e55df7e6724fee096'
    'result.json' = 'cafb257e0321d5608dd13f175d866d1c39112d6cd0805e169f1aa2e4609a1ffb'
    'public.json' = 'd595267290ab703247bc8077221dd999cbde33f8b7450c9c7314785b464d7811'
    'hash_manifest.json' = 'dc46ea0ed3a75ce23cb1b403ced2b14bae3198ed22908262eab0c3ada9ff9c93'
}
$actualNames = @(Get-ChildItem -LiteralPath $privateDir -Force -Name | Sort-Object)
if (($actualNames -join ',') -ne ((@($expectedPrivate.Keys) | Sort-Object) -join ',')) {
    throw 'Private header diagnostic inventory differs'
}
foreach ($name in $expectedPrivate.Keys) {
    $actual = (Get-FileHash -LiteralPath (Join-Path $privateDir $name) -Algorithm SHA256).Hash.ToLower()
    if ($actual -ne $expectedPrivate[$name]) {
        throw "Private header diagnostic hash differs: $name"
    }
}
$aggregateHash = (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'aggregate.json') -Algorithm SHA256).Hash.ToLower()
if ($aggregateHash -ne $expectedPrivate['public.json']) {
    throw 'Public aggregate differs from redacted private projection'
}
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Raw | ConvertFrom-Json
$aggregate = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'aggregate.json') -Raw | ConvertFrom-Json
if ($manifest.status -ne 'PRELIMINARY_PROVENANCE_MISMATCH' -or
    $manifest.code_commit -ne '757540b694cef30109046021e8e97ff4cf52efd7' -or
    $manifest.private_intent_sha256 -ne $expectedPrivate['intent.json'] -or
    $manifest.private_result_sha256 -ne $expectedPrivate['result.json'] -or
    $manifest.private_hash_manifest_sha256 -ne $expectedPrivate['hash_manifest.json'] -or
    $aggregate.scope -ne 'candidate_only' -or
    $aggregate.label_status -ne 'unqualified' -or
    $aggregate.qualified_borough_count -ne 0 -or
    $aggregate.files.Count -ne 5 -or
    @($aggregate.files | Where-Object { $_.status -ne 'candidate_found' -or $_.candidate.score -ne 20 }).Count -ne 0) {
    throw 'Header diagnostic status differs from frozen preliminary result'
}
Write-Output 'verified_nyc_header_diagnostic_preliminary_provenance_mismatch'
