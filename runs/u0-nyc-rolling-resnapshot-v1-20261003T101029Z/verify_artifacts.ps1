$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Raw | ConvertFrom-Json
$current = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'snapshot.json') -Raw | ConvertFrom-Json
$prior = Get-Content -LiteralPath (Join-Path $root 'runs/u0-nyc-rolling-snapshot-20260928T225512Z/snapshot.json') -Raw | ConvertFrom-Json
$verification = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'verification.json') -Raw | ConvertFrom-Json

if ($manifest.run_id -ne 'u0-nyc-rolling-resnapshot-v1-20261003T101029Z' -or
    $manifest.code_commit_at_capture -ne 'e1e3f1337315bb51c3f94ca2819f0906b6647bc9' -or
    $manifest.environment_lock_path -ne 'locks/nyc-capture-environment.json') {
    throw 'Unexpected run identity'
}
foreach ($item in $manifest.immutable_run_files_sha256.PSObject.Properties) {
    $path = Join-Path $root $item.Name
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing immutable run file: $($item.Name)"
    }
    $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $item.Value) {
        throw "Immutable run file hash mismatch: $($item.Name)"
    }
}
$lock = Join-Path $root $manifest.environment_lock_path
if ((Get-FileHash -LiteralPath $lock -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.environment_lock_sha256) {
    throw 'Environment lock hash mismatch'
}
$codeSpec = "$($manifest.code_commit_at_capture):scripts/capture_nyc_rolling_snapshot.py"
$codeBlob = git -C $root rev-parse $codeSpec
if ($LASTEXITCODE -ne 0 -or $codeBlob.Trim() -ne $manifest.capture_code_git_blob) {
    throw 'Capture code commit or Git blob mismatch'
}

$privateRoot = (Resolve-Path (Join-Path $root 'data/raw/nyc_dof')).Path
foreach ($record in @($prior, $current)) {
    $name = [string]$record.raw_filename
    if ($name -ne [IO.Path]::GetFileName($name)) {
        throw 'Snapshot filename is not a basename'
    }
    $path = Join-Path $privateRoot $name
    $file = Get-Item -LiteralPath $path -Force -ErrorAction Stop
    if ($file.PSIsContainer -or ($file.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Private snapshot is not a direct regular file'
    }
    $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($hash -ne $record.sha256 -or $file.Length -ne $record.bytes) {
        throw 'Private CSV hash or size mismatch'
    }
    git -C $root check-ignore -q -- $file.FullName
    if ($LASTEXITCODE -ne 0) {
        throw 'Private CSV is not Git ignored'
    }
}
if ($current.sha256 -ne $prior.sha256 -or $current.bytes -ne $prior.bytes -or
    $current.rows -ne $prior.rows -or $current.rows -ne $current.source_count_before -or
    $current.rows -ne $current.source_count_after -or
    $verification.current.sha256 -ne $current.sha256 -or
    $verification.previous.sha256 -ne $prior.sha256 -or
    $verification.current.bytes -ne $current.bytes -or
    $verification.previous.bytes -ne $prior.bytes -or
    $verification.current.rows -ne $current.rows -or
    $verification.previous.rows -ne $prior.rows -or
    $verification.current.columns -ne 21 -or $verification.previous.columns -ne 21 -or
    $verification.current.ignored_by_git -ne $true -or
    $verification.previous.ignored_by_git -ne $true -or
    $current.capture_status -ne 'inventory_only_not_asof_eligible' -or
    $verification.status -ne 'verified_source_inventory_only' -or
    $verification.exact_file_sha256_and_size_equal -ne $true -or
    $verification.historical_asof_eligible -ne $false -or
    $verification.sale_labels_certified -ne 0 -or $verification.u0_status -ne 'PENDING' -or
    $verification.g_us_status -ne 'PENDING') {
    throw 'Source comparison or gate state mismatch'
}
Write-Output 'NYC repeat CSV snapshot verified: exact source bytes equal; zero labels certified; U0 and G-US pending.'
