$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$privateRun = Join-Path $projectRoot 'data\raw\nyc_dof\system-timestamps-v1-20260930T212636Z'
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$runner = Join-Path $projectRoot 'scripts\probe_nyc_system_timestamps.py'
$expectedPublicNames = @('aggregate.json', 'manifest.json', 'report.md', 'test_gate.json', 'verify_artifacts.ps1')
$actualPublicNames = @(Get-ChildItem -LiteralPath $PSScriptRoot -Force -Name | Sort-Object)
if (($actualPublicNames -join ',') -ne ($expectedPublicNames -join ',')) {
    throw 'Public timestamp run artifact inventory differs'
}

if (-not (Test-Path -LiteralPath $privateRun -PathType Container)) {
    throw 'Private timestamp capture is unavailable; cannot verify the public evidence'
}

$replayed = & $python $runner replay $privateRun | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Private replay failed' }

foreach ($name in @('aggregate.json', 'manifest.json')) {
    $local = (Get-FileHash -LiteralPath (Join-Path $privateRun $name) -Algorithm SHA256).Hash
    $public = (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $name) -Algorithm SHA256).Hash
    if ($local -ne $public) { throw "Public $name differs from verified private capture" }
}

$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Raw | ConvertFrom-Json
$gate = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'test_gate.json') -Raw | ConvertFrom-Json
$public = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'aggregate.json') -Raw | ConvertFrom-Json
$expectedGateKeys = @('code_gate', 'g_us_gate', 'historical_asof_eligible', 'live_capture_exit_code', 'metadata_stable_views', 'offline_replay_exit_code', 'protocol', 'requested_views', 'requests', 'sale_labels_certified', 'status', 'u0_gate')
$actualGateKeys = @($gate.PSObject.Properties.Name | Sort-Object)
if (($actualGateKeys -join ',') -ne ($expectedGateKeys -join ',') -or
    $gate.historical_asof_eligible -isnot [bool]) {
    throw 'Timestamp diagnostic gate schema differs'
}
$codeGatePath = Join-Path $projectRoot 'runs\u0-nyc-system-timestamps-code-20260930T212103Z\full_tests_gate.json'
$codeGate = Get-Content -LiteralPath $codeGatePath -Raw | ConvertFrom-Json
if ($manifest.code_commit -ne '0e04e327c4ba48f995c12c6f15cb00a97d1baf86' -or
    $manifest.dirty_tree_at_start -or
    $manifest.run_id -ne 'system-timestamps-v1-20260930T212636Z' -or
    $manifest.requests.Count -ne 6 -or
    $gate.protocol -ne 'nyc-row-system-timestamps-v1' -or
    $gate.status -ne 'PASS_DIAGNOSTIC_ONLY' -or
    $gate.code_gate -ne 'runs/u0-nyc-system-timestamps-code-20260930T212103Z/full_tests_gate.json' -or
    $codeGate.exit_code -ne 0 -or
    $gate.live_capture_exit_code -ne 0 -or
    $gate.offline_replay_exit_code -ne 0 -or
    $gate.metadata_stable_views -ne 2 -or
    $gate.requested_views -ne 2 -or
    $gate.requests -ne 6 -or
    $gate.sale_labels_certified -ne 0 -or
    $gate.historical_asof_eligible -or
    $gate.u0_gate -ne 'PENDING' -or
    $gate.g_us_gate -ne 'PENDING' -or
    $public.status -ne 'diagnostic_only' -or
    $replayed.status -ne 'diagnostic_only' -or
    $public.sale_labels_certified -ne 0 -or
    $public.historical_asof_eligible -or
    $public.datasets.'usep-8jbt'.row_count -ne 82345 -or
    $public.datasets.'w2pb-icbu'.row_count -ne 845607 -or
    -not $public.datasets.'usep-8jbt'.metadata_stable -or
    -not $public.datasets.'w2pb-icbu'.metadata_stable) {
    throw 'Timestamp diagnostic public gate differs'
}

Write-Output 'NYC row timestamp diagnostic: VERIFIED; zero certified labels; U0 and G-US pending'
