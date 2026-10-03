$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$evidence = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'evidence_manifest.json') -Raw |
    ConvertFrom-Json

if ($evidence.run_id -ne 'u0-ames-source-integration-v1-20261003T132308Z' -or
    $evidence.protocol -ne 'ames_source_integration_v1' -or
    $evidence.status -ne 'verified_engineering_source_integration' -or
    $evidence.source_id -ne 'openml_42165_v1' -or
    $evidence.focused_tests -ne 1 -or $evidence.full_tests -ne 1172 -or
    $evidence.full_skipped -ne 0 -or $evidence.certified_sale_labels -ne 0 -or
    $evidence.u0_gate -ne 'PENDING' -or $evidence.g_us_gate -ne 'PENDING') {
    throw 'Unexpected run identity, scope or gate status'
}

$commit = git -C $root rev-parse --verify "$($evidence.code_commit)^{commit}"
if ($LASTEXITCODE -ne 0 -or $commit.Trim() -ne $evidence.code_commit) {
    throw 'Recorded code commit is unavailable'
}
$plan = Join-Path $PSScriptRoot 'plan.md'
if ((Get-FileHash -LiteralPath $plan -Algorithm SHA256).Hash.ToLowerInvariant() -ne
    $evidence.configuration_hash) {
    throw 'Frozen plan differs from recorded configuration'
}
$lock = Join-Path $root $evidence.environment_lock_path
if ((Get-FileHash -LiteralPath $lock -Algorithm SHA256).Hash.ToLowerInvariant() -ne
    $evidence.environment_lock_sha256) {
    throw 'Environment lock differs from recorded hash'
}

$source = Join-Path $root 'data/raw/openml/house_prices-42165.arff'
$file = Get-Item -LiteralPath $source -Force -ErrorAction Stop
if ($file.PSIsContainer -or ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
    $file.Length -ne $evidence.source_bytes) {
    throw 'Private source file type or size differs from recorded input'
}
git -C $root check-ignore -q -- $source
if ($LASTEXITCODE -ne 0) {
    throw 'Private OpenML ARFF is not Git-ignored'
}
if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -ne
    $evidence.source_sha256 -or
    (Get-FileHash -LiteralPath $source -Algorithm MD5).Hash.ToLowerInvariant() -ne
    $evidence.source_md5) {
    throw 'Private OpenML ARFF differs from recorded source hashes'
}

foreach ($artifact in $evidence.artifact_sha256.PSObject.Properties) {
    $path = Join-Path $PSScriptRoot $artifact.Name
    if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or
        (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne
        $artifact.Value) {
        throw "Saved test artifact differs from recorded hash: $($artifact.Name)"
    }
}
$focused = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'focused_gate.json') -Raw |
    ConvertFrom-Json
$full = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'full_gate.json') -Raw |
    ConvertFrom-Json
if ($focused.exit_code -ne 0 -or $full.exit_code -ne 0 -or
    $focused.wall_seconds -le 0 -or $full.wall_seconds -le 0 -or
    $focused.source_sha256 -ne $evidence.source_sha256 -or
    $full.source_sha256 -ne $evidence.source_sha256) {
    throw 'Test process exit, duration or source hash is invalid'
}

$focusedLog = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'focused_stderr.log') -Raw
$fullLog = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'full_stderr.log') -Raw
if ($focusedLog -notmatch '(?m)^Ran 1 test in [0-9.]+s\r?$' -or
    $focusedLog -notmatch '(?m)^OK\r?$' -or
    $focusedLog -match 'skipped=' -or
    $fullLog -notmatch '(?m)^Ran 1172 tests in [0-9.]+s\r?$' -or
    $fullLog -notmatch '(?m)^OK\r?$' -or
    $fullLog -match 'skipped=') {
    throw 'Saved unittest output does not show the expected no-skip pass'
}

Write-Output 'Ames source integration verified: 1 focused and 1172 full tests passed, zero skips; U0/G-US pending.'
