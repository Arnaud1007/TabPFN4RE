$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$runName = 'official-exports-20260929T031155Z-e3f467c372ad'
$privateDir = Join-Path $projectRoot "data\raw\nyc_dof\$runName"
if (-not (Test-Path -LiteralPath $privateDir -PathType Container)) {
    throw 'Private failed-run directory is missing'
}
$names = @(Get-ChildItem -LiteralPath $privateDir -Force -Name | Sort-Object)
if (($names -join ',') -ne 'failure.json,intent.json') {
    throw 'Failed-run private files differ from the frozen inventory'
}
$expected = @{
    'intent.json' = 'd928bc184ca71eb996044ec120f5a4e4cdb840a9330bf49dd16fea1465c3f80e'
    'failure.json' = '8fe19c03ecad4175e12b50f6299928f48ae47a6b025d025e04cc22b5a15c8ae2'
}
foreach ($name in $expected.Keys) {
    $path = Join-Path $privateDir $name
    $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLower()
    if ($actual -ne $expected[$name]) {
        throw "Failed-run private hash differs: $name"
    }
}
$failure = Get-Content -LiteralPath (Join-Path $privateDir 'failure.json') -Raw | ConvertFrom-Json
if ($failure.run_status -ne 'incomplete' -or $failure.request_ordinal -ne 1 -or $failure.phase -ne 'request') {
    throw 'Failed-run status differs from the frozen manifest'
}
Write-Output 'verified_failed_source_request_v1'
