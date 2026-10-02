$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$privateRun = Join-Path $projectRoot 'data\raw\nyc_dof\ready-archive-v1-20261001T104628Z'
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Raw | ConvertFrom-Json
$expected = @('list-before.json', 'status-before.json')
$actual = @(Get-ChildItem -LiteralPath $privateRun -File -Name | Sort-Object)
if (($actual -join ',') -ne ($expected -join ',') -or
    $manifest.status -ne 'FAILED_STATUS_SCHEMA' -or
    $manifest.code_commit -ne '7878dbecd52657599ac69ad2398dfbe0d2bcc305' -or
    $manifest.requests_completed -ne 2 -or
    $manifest.csv_requested -or
    $manifest.manifest_written_by_collector -or
    $manifest.sale_labels_certified -ne 0 -or
    $manifest.historical_asof_eligible -or
    $manifest.u0_gate -ne 'PENDING' -or
    $manifest.g_us_gate -ne 'PENDING') {
    throw 'Failed archive run state differs'
}
foreach ($name in $expected) {
    $path = Join-Path $privateRun $name
    $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    $size = (Get-Item -LiteralPath $path).Length
    if ($hash -ne $manifest.private_response_files.$name.sha256 -or
        $size -ne $manifest.private_response_files.$name.bytes) {
        throw "Failed archive response differs: $name"
    }
}
Write-Output 'NYC archive v1 failure: preserved; CSV not requested; U0 and G-US pending'
