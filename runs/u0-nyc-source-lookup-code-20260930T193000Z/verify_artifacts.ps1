$ErrorActionPreference = 'Stop'
$runDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $runDirectory '..\..'))
$manifest = Get-Content -LiteralPath (Join-Path $runDirectory 'manifest.json') -Raw | ConvertFrom-Json

if ($manifest.run_id -ne 'u0-nyc-source-lookup-code-20260930T193000Z') {
    throw 'Code verification run ID differs'
}

foreach ($entry in $manifest.file_hashes.PSObject.Properties) {
    $target = [System.IO.Path]::GetFullPath((Join-Path $projectRoot $entry.Name))
    if (-not $target.StartsWith($projectRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'Manifest path escapes the project'
    }
    $actual = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $entry.Value) {
        throw "Artifact hash differs: $($entry.Name)"
    }
}

$gate = Get-Content -LiteralPath (Join-Path $runDirectory 'test_gate.json') -Raw | ConvertFrom-Json
if (@($gate.checks | Where-Object { $_.exit_code -ne 0 }).Count -ne 0) {
    throw 'A mandatory code verification check failed'
}
if ($gate.sale_labels_certified -ne 0 -or $gate.u0_gate -ne 'PENDING' -or $gate.g_us_gate -ne 'PENDING') {
    throw 'Run scope or gate status differs'
}
Write-Output 'verified_nyc_lookup_code_only_zero_labels'
