$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$gate = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'test_gate.json') -Raw | ConvertFrom-Json

function Get-LowerHash([string]$path) {
    return (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
}

if ($gate.run_id -ne 'u0-cook-review-code-20261003T012707Z' -or
    $gate.protocol -ne 'cook-source-review-v1' -or
    $gate.status -ne 'PASS' -or
    -not $gate.inputs_stable_during_gate -or
    $gate.sample_rows -ne 200 -or
    $gate.certified_sale_labels -ne 0 -or
    $gate.u0_gate -ne 'PENDING' -or
    $gate.g_us_gate -ne 'PENDING' -or
    @($gate.results).Count -ne 8) {
    throw 'Cook review code gate differs from its frozen contract'
}
if ((Get-LowerHash (Join-Path $projectRoot 'scripts\review_cook_sales_sample.py')) -ne $gate.code_sha256 -or
    (Get-LowerHash (Join-Path $projectRoot 'tests\test_review_cook_sales_sample.py')) -ne $gate.tests_sha256 -or
    (Get-LowerHash (Join-Path $projectRoot 'decisions\0052-cook-private-review-ledger.md')) -ne $gate.decision_sha256 -or
    (Get-LowerHash (Join-Path $PSScriptRoot 'environment_lock.txt')) -ne '92d4969aa37973d021c9215c67448b26ac689ca8d6f5b4414c701f126f4ac3e7') {
    throw 'Cook review code or environment differs from gated bytes'
}
foreach ($result in $gate.results) {
    if ($result.exit_code -ne 0 -or
        [IO.Path]::GetFileName([string]$result.output) -ne $result.output -or
        (Get-LowerHash (Join-Path $PSScriptRoot $result.output)) -ne $result.output_sha256) {
        throw "Cook review gate output differs: $($result.name)"
    }
}
Push-Location $projectRoot
try {
    & $python -c "from scripts import review_cook_sales_sample as r; rows=r._capture_rows(); assert len(rows)==200; print('200 pinned rows and private ACLs verified')" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Cook private capture replay failed' }
}
finally { Pop-Location }
Write-Output 'Cook review code evidence verified; zero certified labels; U0 and G-US pending'
