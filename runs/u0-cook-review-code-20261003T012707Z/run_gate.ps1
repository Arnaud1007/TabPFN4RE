$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = (Resolve-Path (Join-Path $projectRoot '.venv\Scripts\python.exe')).Path
$env:AMES_ARFF_PATH = (Resolve-Path (Join-Path $projectRoot 'data\raw\openml\house_prices-42165.arff')).Path

function Write-NewText([string]$path, [string]$value) {
    $stream = [IO.File]::Open($path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
    try {
        $writer = [IO.StreamWriter]::new($stream, [Text.UTF8Encoding]::new($false))
        try { $writer.Write($value); $writer.Flush() }
        finally { $writer.Dispose() }
    }
    finally { $stream.Dispose() }
}

function Get-LowerHash([string]$path) {
    return (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
}

$code = Join-Path $projectRoot 'scripts\review_cook_sales_sample.py'
$tests = Join-Path $projectRoot 'tests\test_review_cook_sales_sample.py'
$decision = Join-Path $projectRoot 'decisions\0052-cook-private-review-ledger.md'
$before = @{
    code = Get-LowerHash $code
    tests = Get-LowerHash $tests
    decision = Get-LowerHash $decision
}
$checks = @(
    @{name='focused_coverage'; arguments=@('-m','coverage','run','--branch','--source=scripts.review_cook_sales_sample','-m','unittest','tests.test_review_cook_sales_sample','-q')},
    @{name='focused_coverage_report'; arguments=@('-m','coverage','report','-m','scripts/review_cook_sales_sample.py')},
    @{name='private_capture_acl_replay'; arguments=@('-c',"from scripts import review_cook_sales_sample as r; rows=r._capture_rows(); assert len(rows)==200; print('200 pinned rows and private ACLs verified')")},
    @{name='full_suite'; arguments=@('-m','unittest','discover','-s','tests','-q')},
    @{name='ruff_check'; arguments=@('-m','ruff','check','src','tests','scripts','runs/u0-cook-sales-sample-20261003T004123Z/rebuild_aggregate.py')},
    @{name='ruff_format'; arguments=@('-m','ruff','format','--check','src','tests','scripts','runs/u0-cook-sales-sample-20261003T004123Z/rebuild_aggregate.py')},
    @{name='pip_check'; arguments=@('-m','pip','check')},
    @{name='pip_audit'; arguments=@('-m','pip_audit','--progress-spinner','off')}
)

Push-Location $projectRoot
try {
    $results = @()
    foreach ($check in $checks) {
        $watch = [Diagnostics.Stopwatch]::StartNew()
        $ErrorActionPreference = 'Continue'
        $outputText = (& $python @($check.arguments) 2>&1 | Out-String)
        $exitCode = $LASTEXITCODE
        $ErrorActionPreference = 'Stop'
        $watch.Stop()
        $redacted = $outputText.Replace($env:USERPROFILE, 'C:\Users\<redacted>')
        if ($env:USERNAME) { $redacted = $redacted.Replace($env:USERNAME, '<redacted>') }
        $logName = "$($check.name).log"
        $logPath = Join-Path $PSScriptRoot $logName
        Write-NewText $logPath $redacted
        $results += [pscustomobject]@{
            name = $check.name
            command = @('.\.venv\Scripts\python.exe') + @($check.arguments)
            exit_code = $exitCode
            duration_seconds = [Math]::Round($watch.Elapsed.TotalSeconds, 3)
            output = $logName
            output_sha256 = Get-LowerHash $logPath
        }
    }
    $after = @{
        code = Get-LowerHash $code
        tests = Get-LowerHash $tests
        decision = Get-LowerHash $decision
    }
    $stable = ($before.code -eq $after.code -and $before.tests -eq $after.tests -and $before.decision -eq $after.decision)
    $failed = @($results | Where-Object exit_code -ne 0).Count
    $gate = [pscustomobject]@{
        run_id = 'u0-cook-review-code-20261003T012707Z'
        protocol = 'cook-source-review-v1'
        baseline_commit = (git rev-parse HEAD).Trim()
        dirty_tree_at_run = $true
        capture_manifest_sha256 = '130b5169ff81ccbc0a729cba98400f2fb377ff9a25999316aaac1960e38a3cf7'
        code_sha256 = $after.code
        tests_sha256 = $after.tests
        decision_sha256 = $after.decision
        inputs_stable_during_gate = $stable
        sample_rows = 200
        certified_sale_labels = 0
        u0_gate = 'PENDING'
        g_us_gate = 'PENDING'
        results = $results
        status = $(if ($failed -eq 0 -and $stable) { 'PASS' } else { 'FAIL' })
    }
    Write-NewText (Join-Path $PSScriptRoot 'test_gate.json') (($gate | ConvertTo-Json -Depth 8) + [Environment]::NewLine)
    Write-Output ("gate_status={0} checks={1} failed={2} inputs_stable={3}" -f $gate.status, $results.Count, $failed, $stable)
    if ($gate.status -ne 'PASS') { exit 1 }
}
finally { Pop-Location }
