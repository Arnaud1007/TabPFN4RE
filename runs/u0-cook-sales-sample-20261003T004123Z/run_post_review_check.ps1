$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$resultPath = Join-Path $PSScriptRoot 'post_review_check.json'
if (Test-Path -LiteralPath $resultPath) {
    throw 'Post-review evidence already exists; preserve the original result'
}

function Get-LowerHash([string]$path) {
    return (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
}

$checks = @(
    @{ name = 'privacy_three_tests'; arguments = @('-m', 'unittest', 'tests.test_cook_aggregate_privacy', '-q') },
    @{ name = 'aggregate_replay'; arguments = @('runs/u0-cook-sales-sample-20261003T004123Z/rebuild_aggregate.py', '--check') },
    @{ name = 'ruff_changed_python'; arguments = @('-m', 'ruff', 'check', 'runs/u0-cook-sales-sample-20261003T004123Z/rebuild_aggregate.py', 'tests/test_cook_aggregate_privacy.py') }
)
$results = @()
Push-Location $projectRoot
try {
    foreach ($check in $checks) {
        $watch = [Diagnostics.Stopwatch]::StartNew()
        $priorPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            $output = & $python @($check.arguments) 2>&1 | Out-String
            $exitCode = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $priorPreference
            $watch.Stop()
        }
        $output = $output.Replace($HOME, '<user-profile>')
        if ($env:USERNAME) {
            $output = $output.Replace($env:USERNAME, '<username>')
        }
        $logName = "post_review_$($check.name).log"
        $logPath = Join-Path $PSScriptRoot $logName
        [IO.File]::WriteAllText($logPath, $output, [Text.UTF8Encoding]::new($false))
        $results += @{
            name = $check.name
            command = @('.\.venv\Scripts\python.exe') + @($check.arguments)
            exit_code = $exitCode
            duration_seconds = [Math]::Round($watch.Elapsed.TotalSeconds, 3)
            output = $logName
            output_sha256 = Get-LowerHash $logPath
        }
    }
}
finally {
    Pop-Location
}
$status = if (@($results | Where-Object { $_.exit_code -ne 0 }).Count -eq 0) { 'PASS' } else { 'FAIL' }
$record = [ordered]@{
    run_id = 'u0-cook-sales-sample-20261003T004123Z'
    reason = 'timestamp-order fix and added regression after the original ten-check gate'
    original_gate = 'test_gate.json'
    original_gate_unchanged = $true
    rebuild_aggregate_sha256 = Get-LowerHash (Join-Path $PSScriptRoot 'rebuild_aggregate.py')
    privacy_tests_sha256 = Get-LowerHash (Join-Path $projectRoot 'tests\test_cook_aggregate_privacy.py')
    checks = $results
    status = $status
}
$record | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $resultPath -Encoding UTF8
Write-Output "Post-review status: $status"
if ($status -ne 'PASS') { exit 1 }
