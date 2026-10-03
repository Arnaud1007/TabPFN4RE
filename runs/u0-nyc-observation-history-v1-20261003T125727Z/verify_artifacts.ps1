$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$python = Join-Path $root '.venv/Scripts/python.exe'
$rawRoot = Join-Path $root 'data/raw/nyc_dof'
$ledgerRoot = Join-Path $root 'data/derived/nyc_dof/observation_history'
$evidence = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'evidence_manifest.json') -Raw |
    ConvertFrom-Json
$cases = @(
    @{
        Manifest = 'runs/u0-nyc-rolling-snapshot-20260928T225512Z/snapshot.json'
        Expected = 'first_replay.json'
        KnownBy = '2026-09-28T22:55:43.929203Z'
        Added = '100_plus'
    },
    @{
        Manifest = 'runs/u0-nyc-rolling-resnapshot-v1-20261003T101029Z/snapshot.json'
        Expected = 'second_replay.json'
        KnownBy = '2026-10-03T10:13:06.833850Z'
        Added = 'zero'
    }
)

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'Locked local Python environment is missing'
}
if (-not (Test-Path -LiteralPath $ledgerRoot -PathType Container)) {
    throw 'Private observation ledger is missing'
}
if ($evidence.run_id -ne 'u0-nyc-observation-history-v1-20261003T125727Z' -or
    $evidence.protocol -ne 'nyc-observation-v1' -or
    $evidence.status -ne 'verified_source_inventory_only' -or
    $evidence.source_capture_manifests_sha256.Count -ne 2 -or
    $evidence.private_observation_sha256.Count -ne 2 -or
    $evidence.certified_sale_labels -ne 0 -or
    $evidence.u0_gate -ne 'PENDING' -or $evidence.g_us_gate -ne 'PENDING') {
    throw 'Frozen evidence manifest has unexpected identity or status'
}
$lockPath = Join-Path $root $evidence.environment_lock_path
if ((Get-FileHash -LiteralPath $lockPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne
    $evidence.environment_lock_sha256) {
    throw 'Environment lock differs from frozen evidence'
}
$planPath = Join-Path $PSScriptRoot 'plan.md'
if ((Get-FileHash -LiteralPath $planPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne
    $evidence.configuration_hash) {
    throw 'Frozen plan differs from configuration hash'
}
$codeAtRun = git -C $root rev-parse "$($evidence.code_commit_replayed):src/tabpfn4realestate/data/nyc_observation_history.py"
if ($LASTEXITCODE -ne 0) {
    throw 'Recorded code commit is unavailable'
}
$currentCode = git -C $root hash-object (Join-Path $root 'src/tabpfn4realestate/data/nyc_observation_history.py')
if ($LASTEXITCODE -ne 0 -or $currentCode.Trim() -ne $codeAtRun.Trim()) {
    throw 'Current observation code differs from recorded commit'
}
git -C $root check-ignore -q -- $ledgerRoot
if ($LASTEXITCODE -ne 0) {
    throw 'Private observation ledger is not Git-ignored'
}

$entries = @(Get-ChildItem -LiteralPath $ledgerRoot -Filter '*.json' -File)
if ($entries.Count -ne 2) {
    throw "Expected exactly two private observations, found $($entries.Count)"
}
if (Test-Path -LiteralPath (Join-Path $ledgerRoot '.write.lock')) {
    throw 'Private observation ledger has an active or stale write lock'
}

for ($index = 0; $index -lt $cases.Count; $index++) {
    $case = $cases[$index]
    $manifestPath = Join-Path $root $case.Manifest
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    if ($manifest.sha256 -ne $evidence.source_snapshot_sha256) {
        throw 'Source CSV digest differs from frozen evidence'
    }
    $privateCsv = Join-Path $rawRoot $manifest.raw_filename
    git -C $root check-ignore -q -- $privateCsv
    if ($LASTEXITCODE -ne 0) {
        throw 'Private source CSV is not Git-ignored'
    }
    $output = & $python -m tabpfn4realestate.data.nyc_observation_history `
        --manifest $manifestPath --raw-root $rawRoot --ledger-root $ledgerRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Observation replay failed: $($case.Manifest)"
    }
    $actual = $output | ConvertFrom-Json
    $expected = Get-Content -LiteralPath (Join-Path $PSScriptRoot $case.Expected) -Raw |
        ConvertFrom-Json
    if (($actual | ConvertTo-Json -Depth 8 -Compress) -ne
        ($expected | ConvertTo-Json -Depth 8 -Compress)) {
        throw "Observation replay differs from saved result: $($case.Expected)"
    }
    if ($actual.rows -ne 82345 -or
        $actual.known_by_utc -ne $case.KnownBy -or
        $actual.added_occurrences_bucket -ne $case.Added -or
        $actual.removed_occurrences_bucket -ne 'zero' -or
        $actual.write_status -ne 'replayed' -or
        $actual.capture_status -ne 'inventory_only' -or
        $actual.asof_eligible -ne $false -or
        $actual.first_public_availability_verified -ne $false -or
        $actual.certified_sale_labels -ne 0) {
        throw "Unexpected inventory or gate status: $($case.Expected)"
    }
    if ($actual.manifest_sha256 -ne $evidence.source_capture_manifests_sha256[$index] -or
        $actual.manifest_sha256 -ne
        (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant()) {
        throw "Capture manifest hash mismatch: $($case.Manifest)"
    }
    if ($actual.observation_sha256 -ne $evidence.private_observation_sha256[$index] -or
        $actual.observation_sha256 -notin @(
        $entries | ForEach-Object { (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
    )) {
        throw "Private observation hash mismatch: $($case.Expected)"
    }
}

Write-Output 'NYC observation history verified: two captures, no later representation delta, zero certified labels.'
