$ErrorActionPreference = 'Stop'
$runDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $runDirectory '..\..'))
$manifest = Get-Content -LiteralPath (Join-Path $runDirectory 'manifest.json') -Raw | ConvertFrom-Json

function Assert-OrdinaryPath {
    param([string] $Root, [string] $Target)
    $resolvedRoot = [System.IO.Path]::GetFullPath($Root)
    $resolvedTarget = [System.IO.Path]::GetFullPath($Target)
    if (-not $resolvedTarget.StartsWith($resolvedRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'Artifact path escapes its approved root'
    }
    $cursor = $resolvedTarget
    while ($true) {
        $item = Get-Item -LiteralPath $cursor -Force
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'Artifact path traverses a reparse point'
        }
        if ($cursor -eq $resolvedRoot) { break }
        $cursor = [System.IO.Path]::GetDirectoryName($cursor)
    }
    return $resolvedTarget
}

if ($manifest.run_id -ne 'u0-nyc-source-lookup-live-v1-20260930T193830Z') {
    throw 'NYC lookup run ID differs'
}
$runPath = 'runs/u0-nyc-source-lookup-live-v1-20260930T193830Z'
$requiredFiles = @(
    "$runPath/plan.md", "$runPath/aggregate.json", "$runPath/test_gate.json",
    "$runPath/report.md", "$runPath/verify_artifacts.ps1",
    'scripts/collect_nyc_review_lookups_v1.py',
    'scripts/audit_nyc_acris_matches_v2.py',
    'scripts/audit_nyc_acris_matches.py',
    'scripts/review_nyc_sample.py',
    'scripts/private_review_io.py',
    'scripts/profile_nyc_rolling_snapshot.py',
    'decisions/0037-nyc-bounded-review-lookups.md',
    'locks/nyc-review-ledger-environment.json'
)
$listedFiles = @($manifest.file_hashes.PSObject.Properties.Name)
if (@(Compare-Object -ReferenceObject $requiredFiles -DifferenceObject $listedFiles).Count -ne 0) {
    throw 'Required public artifact inventory differs'
}
foreach ($entry in $manifest.file_hashes.PSObject.Properties) {
    $target = Assert-OrdinaryPath $projectRoot (Join-Path $projectRoot $entry.Name)
    $actual = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $entry.Value) {
        throw "Public artifact hash differs: $($entry.Name)"
    }
}

$privateRoot = Join-Path $projectRoot 'data/raw/nyc_dof'
$privateEvidence = Join-Path $privateRoot 'manual-review-v1/source-lookup-evidence-20260930T193830Z.json'
$privateEvidence = Assert-OrdinaryPath $projectRoot $privateEvidence
$privateDigest = (Get-FileHash -LiteralPath $privateEvidence -Algorithm SHA256).Hash.ToLowerInvariant()
if ($privateDigest -ne $manifest.private_evidence_manifest_sha256) {
    throw 'Protected evidence manifest hash differs'
}
$privateManifest = Get-Content -LiteralPath $privateEvidence -Raw | ConvertFrom-Json
$privateRun = Join-Path $privateRoot 'source-lookup-v1-20260930T193830Z'
$privateRun = Assert-OrdinaryPath $projectRoot $privateRun
$requiredPrivate = @('state.json', 'ledger-snapshot.jsonl')
$listedPrivate = @($privateManifest.private_files_sha256.PSObject.Properties.Name)
if (@($requiredPrivate | Where-Object { $_ -notin $listedPrivate }).Count -ne 0) {
    throw 'Required protected evidence missing'
}
$actualPrivate = @(Get-ChildItem -LiteralPath $privateRun -Force | ForEach-Object { $_.Name })
if (@(Compare-Object -ReferenceObject $listedPrivate -DifferenceObject $actualPrivate).Count -ne 0) {
    throw 'Protected evidence inventory differs'
}
foreach ($entry in $privateManifest.private_files_sha256.PSObject.Properties) {
    if ($entry.Name -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$') {
        throw 'Protected evidence file name invalid'
    }
    $privateFile = Assert-OrdinaryPath $privateRoot (Join-Path $privateRun $entry.Name)
    $actual = (Get-FileHash -LiteralPath $privateFile -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $entry.Value) {
        throw 'Protected evidence file hash differs'
    }
}
$expectedLogs = @{
    capture_stdout = 'manual-review-v1/lookup-capture-20260930T193830Z.log'
    replay_stdout = 'manual-review-v1/lookup-replay-20260930T193830Z.log'
}
if (@(Compare-Object -ReferenceObject @($expectedLogs.Keys) -DifferenceObject @($privateManifest.private_command_log_sha256.PSObject.Properties.Name)).Count -ne 0) {
    throw 'Protected command log inventory differs'
}
foreach ($entry in $privateManifest.private_command_log_sha256.PSObject.Properties) {
    $logPath = Assert-OrdinaryPath $privateRoot (Join-Path $privateRoot $expectedLogs[$entry.Name])
    $actual = (Get-FileHash -LiteralPath $logPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $entry.Value) {
        throw 'Protected command log hash differs'
    }
}
$timingPath = Assert-OrdinaryPath $privateRoot (Join-Path $privateRoot 'manual-review-v1/source-lookup-timing-20260930T193830Z.json')
if ((Get-FileHash -LiteralPath $timingPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.private_timing_sha256) {
    throw 'Protected timing hash differs'
}

$python = Join-Path $projectRoot '.venv/Scripts/python.exe'
$collector = Join-Path $projectRoot 'scripts/collect_nyc_review_lookups_v1.py'
& $python $collector replay --source (Join-Path $privateRoot 'nyc-usep-8jbt-20260928T225530.250496Z-2d84779d0195.csv') --sample (Join-Path $privateRoot 'review-usep-8jbt-20260928T234700Z.jsonl') --code-table (Join-Path $privateRoot 'acris-document-control-codes-7isb-wh4c-rows-20260929.json') --private-run-dir $privateRun | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'Protected offline replay failed'
}

$gate = Get-Content -LiteralPath (Join-Path $runDirectory 'test_gate.json') -Raw | ConvertFrom-Json
$aggregate = Get-Content -LiteralPath (Join-Path $runDirectory 'aggregate.json') -Raw | ConvertFrom-Json
if (@($gate.checks).Count -ne 3 -or @($gate.checks | Where-Object { $_.exit_code -ne 0 }).Count -ne 0 -or $aggregate.projection -ne 'private_only_v1' -or $aggregate.manual_reviews_appended -ne 0 -or $aggregate.sale_labels_certified -ne 0 -or $aggregate.u0_gate -ne 'PENDING' -or $aggregate.g_us_gate -ne 'PENDING') {
    throw 'Source qualification gate differs'
}
Write-Output 'verified_nyc_one_home_lookup_zero_labels'
