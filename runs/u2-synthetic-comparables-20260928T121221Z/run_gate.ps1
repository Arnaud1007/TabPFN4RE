Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$projectRoot = (Resolve-Path '.').Path
$runDirectory = Join-Path $projectRoot 'runs/u2-synthetic-comparables-20260928T121221Z'
$testPython = Join-Path $projectRoot '.venv/Scripts/python.exe'
$env:AMES_ARFF_PATH = (Resolve-Path 'data/raw/openml/house_prices-42165.arff').Path

function Invoke-GateStep {
    param(
        [string]$Name,
        [string]$Executable,
        [string[]]$Arguments
    )
    $outputPath = Join-Path $runDirectory "$Name.log"
    $timer = [System.Diagnostics.Stopwatch]::StartNew()
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $Executable @Arguments 2>&1 | Out-File -LiteralPath $outputPath -Encoding utf8
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousPreference
    $timer.Stop()
    return [ordered]@{
        name = $Name
        command = @($Executable) + $Arguments
        exit_code = $exitCode
        duration_seconds = [math]::Round($timer.Elapsed.TotalSeconds, 3)
        output = "$Name.log"
        output_sha256 = (Get-FileHash -LiteralPath $outputPath -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}

$steps = @(
    (Invoke-GateStep 'tests' $testPython @('-m', 'coverage', 'run', '--source=tabpfn4realestate', '-m', 'unittest', 'discover', '-s', 'tests', '-q'))
    (Invoke-GateStep 'coverage_report' $testPython @('-m', 'coverage', 'report', '--show-missing'))
    (Invoke-GateStep 'coverage_json' $testPython @('-m', 'coverage', 'json', '-o', (Join-Path $runDirectory 'coverage.json')))
    (Invoke-GateStep 'lint' 'python' @('-m', 'ruff', 'check', 'src', 'tests'))
    (Invoke-GateStep 'format' 'python' @('-m', 'ruff', 'format', '--check', 'src', 'tests'))
)
$testLog = Get-Content -LiteralPath (Join-Path $runDirectory 'tests.log') -Raw
$skipped = $testLog -match 'skipped='
$passed = ($steps | Where-Object { $_.exit_code -ne 0 }).Count -eq 0 -and -not $skipped
$manifest = [ordered]@{
    run_id = 'u2-synthetic-comparables-20260928T121221Z'
    status = if ($passed) { 'complete' } else { 'failed' }
    milestone = 'U2-synthetic-comparable-engineering'
    executed_at_utc = (Get-Date).ToUniversalTime().ToString('o')
    code_commit = (git rev-parse HEAD).Trim()
    dirty_tree = -not [string]::IsNullOrWhiteSpace((git status --porcelain))
    environment_lock_sha256 = (Get-FileHash 'locks/synthetic-engineering-environment.json' -Algorithm SHA256).Hash.ToLowerInvariant()
    source_snapshot_sha256 = (Get-FileHash -LiteralPath $env:AMES_ARFF_PATH -Algorithm SHA256).Hash.ToLowerInvariant()
    synthetic_fixture_sha256 = (Get-FileHash 'tests/test_u2_comparables.py' -Algorithm SHA256).Hash.ToLowerInvariant()
    split_hash = $null
    feature_policy_hash = (Get-FileHash 'policies/ames-smoke.json' -Algorithm SHA256).Hash.ToLowerInvariant()
    configuration_hash = (Get-FileHash 'src/tabpfn4realestate/features/comparables.py' -Algorithm SHA256).Hash.ToLowerInvariant()
    checkpoint_identity = $null
    certification_eligible = $false
    python_version = (& $testPython --version).Trim()
    ruff_version = (python -m ruff --version).Trim()
    results = $steps
    coverage_json_sha256 = (Get-FileHash -LiteralPath (Join-Path $runDirectory 'coverage.json') -Algorithm SHA256).Hash.ToLowerInvariant()
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $runDirectory 'test_gate.json') -Encoding utf8
if (-not $passed) { exit 1 }
