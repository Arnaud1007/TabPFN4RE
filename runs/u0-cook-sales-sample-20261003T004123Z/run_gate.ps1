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

$checks = @(
    @{name='capture_coverage'; arguments=@('-m','coverage','run','--branch','--source=capture_cook_sales_audit','-m','unittest','tests.test_capture_cook_sales_audit','-q')},
    @{name='capture_coverage_report'; arguments=@('-m','coverage','report','-m')},
    @{name='aggregate_privacy'; arguments=@('-m','unittest','tests.test_cook_aggregate_privacy','-q')},
    @{name='private_replay'; arguments=@('scripts/capture_cook_sales_audit.py','--verify','data/raw/cook_county/cook-sales-v1-20261003T004123.032937Z-c08de13e9f1d')},
    @{name='aggregate_replay'; arguments=@('runs/u0-cook-sales-sample-20261003T004123Z/rebuild_aggregate.py','--check')},
    @{name='full_suite'; arguments=@('-m','unittest','discover','-s','tests','-q')},
    @{name='ruff_check'; arguments=@('-m','ruff','check','src','tests','scripts/capture_cook_sales_audit.py','runs/u0-cook-sales-sample-20261003T004123Z/rebuild_aggregate.py')},
    @{name='ruff_format'; arguments=@('-m','ruff','format','--check','src','tests','scripts/capture_cook_sales_audit.py','runs/u0-cook-sales-sample-20261003T004123Z/rebuild_aggregate.py')},
    @{name='pip_check'; arguments=@('-m','pip','check')},
    @{name='pip_audit'; arguments=@('-m','pip_audit','--progress-spinner','off')}
)

Push-Location $projectRoot
try {
    $results = @()
    foreach ($check in $checks) {
        $arguments = $check.arguments
        $watch = [Diagnostics.Stopwatch]::StartNew()
        $ErrorActionPreference = 'Continue'
        $outputText = (& $python @arguments 2>&1 | Out-String)
        $exitCode = $LASTEXITCODE
        $ErrorActionPreference = 'Stop'
        $watch.Stop()
        $redacted = $outputText.Replace($env:USERPROFILE, 'C:\Users\<redacted>').Replace($env:USERNAME, '<redacted>')
        $logName = "$($check.name).log"
        $logPath = Join-Path $PSScriptRoot $logName
        Write-NewText $logPath $redacted
        $results += [pscustomobject]@{
            name = $check.name
            command = @('.\.venv\Scripts\python.exe') + $arguments
            exit_code = $exitCode
            duration_seconds = [Math]::Round($watch.Elapsed.TotalSeconds, 3)
            output = $logName
            output_sha256 = (Get-FileHash -LiteralPath $logPath -Algorithm SHA256).Hash.ToLowerInvariant()
            output_redacted_user_profile = $true
            output_redacted_username = $true
        }
    }
    $aggregate = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'aggregate.json') -Raw | ConvertFrom-Json
    $failed = @($results | Where-Object exit_code -ne 0).Count
    $gate = [pscustomobject]@{
        run_id = 'u0-cook-sales-sample-20261003T004123Z'
        protocol = 'adr-0051-cook-sales-v1'
        capture_code_commit = '4851fb9dc86f38262a7a170a36f2332c514729b5'
        environment_lock_sha256 = $aggregate.environment_lock_sha256
        data_snapshot_sha256 = $aggregate.data_snapshot_sha256
        sample_rows = $aggregate.sample_rows
        manual_rubrics_complete = 0
        certified_sale_labels = 0
        u0_gate = 'PENDING'
        g_us_gate = 'PENDING'
        results = $results
        status = $(if ($failed -eq 0) { 'PASS' } else { 'FAIL' })
    }
    Write-NewText (Join-Path $PSScriptRoot 'test_gate.json') (($gate | ConvertTo-Json -Depth 8) + [Environment]::NewLine)
    Write-Output ("gate_status={0} checks={1} failed={2}" -f $gate.status, $results.Count, $failed)
    if ($failed -ne 0) { exit 1 }
}
finally { Pop-Location }
