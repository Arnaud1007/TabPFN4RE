$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Set-Location -LiteralPath $root
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Raw | ConvertFrom-Json
$gate = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'test_gate.json') -Raw | ConvertFrom-Json
if ($manifest.status -ne 'complete' -or $manifest.certification_eligible -or
    $gate.status -ne 'complete' -or $gate.certification_eligible -or
    $gate.tests_observed -ne 277 -or $gate.tests_skipped -or
    $gate.statement_coverage_percent -lt 80) {
    throw 'Unexpected synthetic gate status, count or coverage'
}
foreach ($item in $manifest.artifacts) {
    $actual = (Get-FileHash -LiteralPath $item.path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $item.sha256) { throw "Artifact hash mismatch: $($item.path)" }
}
foreach ($result in $gate.results) {
    if ($result.exit_code -ne 0) { throw "Check failed: $($result.name)" }
    $path = Join-Path $PSScriptRoot $result.output
    $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $result.output_sha256) { throw "Log hash mismatch: $($result.name)" }
}
Write-Output 'PASS: synthetic gate, 277 tests, coverage and artifact hashes'
