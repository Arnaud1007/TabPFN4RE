param([Parameter(Mandatory = $true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Set-Location -LiteralPath $root
if ([System.IO.Path]::IsPathRooted($OutputDirectory)) {
    throw 'OutputDirectory must be relative to the project root'
}
$runDir = [System.IO.Path]::GetFullPath((Join-Path $root $OutputDirectory))
$runsRoot = [System.IO.Path]::GetFullPath((Join-Path $root 'runs'))
$runsPrefix = $runsRoot + [System.IO.Path]::DirectorySeparatorChar
if (-not $runDir.StartsWith($runsPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'OutputDirectory must be a new directory under runs'
}
if (-not [string]::Equals((Split-Path -Parent $runDir), $runsRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'OutputDirectory must be a direct child of runs'
}
if (((Get-Item -LiteralPath $runsRoot).Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw 'runs must not be a junction or symlink'
}
if (Test-Path -LiteralPath $runDir) {
    throw 'OutputDirectory already exists; recorded runs are immutable'
}
$sourceDirty = [bool](git status --porcelain)
New-Item -ItemType Directory -Path $runDir | Out-Null

$python = (Resolve-Path '.venv\Scripts\python.exe').Path
$env:AMES_ARFF_PATH = (Resolve-Path 'data\raw\openml\house_prices-42165.arff').Path
$env:COVERAGE_FILE = Join-Path $runDir '.coverage'
$utf8 = New-Object System.Text.UTF8Encoding($false)
$checks = @(
    @{ name = 'tests'; args = @('-m', 'coverage', 'run', '--source=tabpfn4realestate', '-m', 'unittest', 'discover', '-s', 'tests', '-q') },
    @{ name = 'coverage_report'; args = @('-m', 'coverage', 'report', '--show-missing') },
    @{ name = 'coverage_json'; args = @('-m', 'coverage', 'json', '-o', (Join-Path $runDir 'coverage.json')) },
    @{ name = 'lint'; args = @('-m', 'ruff', 'check', 'src', 'tests') },
    @{ name = 'format'; args = @('-m', 'ruff', 'format', '--check', 'src', 'tests') },
    @{ name = 'pip_check'; args = @('-m', 'pip', 'check') },
    @{ name = 'dependency_audit'; args = @('-m', 'pip_audit', '-r', 'locks/local-date-requirements.txt', '--disable-pip', '--no-deps', '--progress-spinner', 'off') }
)
$results = @()
foreach ($check in $checks) {
    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    $arguments = @($check.args | ForEach-Object { '"' + $_.Replace('"', '\"') + '"' })
    $stdout = Join-Path $runDir ($check.name + '.stdout.tmp')
    $stderr = Join-Path $runDir ($check.name + '.stderr.tmp')
    $process = Start-Process -FilePath $python -ArgumentList $arguments -WindowStyle Hidden -PassThru -Wait -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    $exitCode = $process.ExitCode
    $watch.Stop()
    $log = Join-Path $runDir ($check.name + '.log')
    $output = [System.IO.File]::ReadAllText($stdout) + [System.IO.File]::ReadAllText($stderr)
    [System.IO.File]::WriteAllText($log, $output, $utf8)
    Remove-Item -LiteralPath $stdout, $stderr
    $results += [ordered]@{
        name = $check.name
        command = @($python) + @($check.args)
        exit_code = $exitCode
        duration_seconds = [math]::Round($watch.Elapsed.TotalSeconds, 3)
        output = ($check.name + '.log')
        output_sha256 = (Get-FileHash -LiteralPath $log -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}

$testsLog = [System.IO.File]::ReadAllText((Join-Path $runDir 'tests.log'))
$testMatch = [regex]::Match($testsLog, 'Ran (\d+) tests')
$testCount = if ($testMatch.Success) { [int]$testMatch.Groups[1].Value } else { 0 }
$skipped = $testsLog -match 'skipped=\d+'
$coverageText = Get-Content -LiteralPath (Join-Path $runDir 'coverage.json') -Raw
$coverageMatch = [regex]::Match($coverageText, '"totals":\s*\{[^}]*"percent_covered":\s*([0-9.]+)')
if (-not $coverageMatch.Success) { throw 'Coverage total was not found' }
$percent = [double]::Parse($coverageMatch.Groups[1].Value, [System.Globalization.CultureInfo]::InvariantCulture)
$complete = (@($results | Where-Object { $_.exit_code -ne 0 }).Count -eq 0) -and
    ($testCount -gt 0) -and (-not $skipped) -and ($percent -ge 80)
$runId = Split-Path -Leaf $runDir
$gate = [ordered]@{
    run_id = $runId
    status = if ($complete) { 'complete' } else { 'failed' }
    milestone = 'U5-synthetic-interval-engineering'
    executed_at_utc = [datetime]::UtcNow.ToString('o')
    code_commit = (git rev-parse HEAD).Trim()
    dirty_tree = $sourceDirty
    environment_lock_sha256 = (Get-FileHash 'locks/local-date-requirements.txt' -Algorithm SHA256).Hash.ToLowerInvariant()
    source_snapshot_sha256 = $null
    synthetic_fixture_sha256 = (Get-FileHash 'tests/test_conformal_calibration.py' -Algorithm SHA256).Hash.ToLowerInvariant()
    split_hash = $null
    feature_policy_hash = $null
    configuration_hash = (Get-FileHash 'decisions/0016-synthetic-split-conformal.md' -Algorithm SHA256).Hash.ToLowerInvariant()
    checkpoint_identity = $null
    certification_eligible = $false
    python_version = (& $python --version)
    tests_observed = $testCount
    tests_skipped = $skipped
    statement_coverage_percent = $percent
    coverage_json_sha256 = (Get-FileHash (Join-Path $runDir 'coverage.json') -Algorithm SHA256).Hash.ToLowerInvariant()
    results = $results
}
$gatePath = Join-Path $runDir 'test_gate.json'
$temporary = $gatePath + '.tmp'
[System.IO.File]::WriteAllText($temporary, ($gate | ConvertTo-Json -Depth 8), $utf8)
Move-Item -LiteralPath $temporary -Destination $gatePath
if (-not $complete) { throw 'Synthetic conformal gate failed; see test_gate.json' }
Write-Output "PASS: $testCount tests, $([math]::Round($percent, 2))% package coverage, lint, format, package and dependency checks"
