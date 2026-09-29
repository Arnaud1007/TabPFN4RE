$ErrorActionPreference = 'Stop'
$runId = 'u0-nyc-acris-v2-20260929T012700Z'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Raw | ConvertFrom-Json
$aggregate = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'aggregate.json') -Raw | ConvertFrom-Json
$config = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'configuration.json') -Raw | ConvertFrom-Json

function Get-Sha256Text([string] $value) {
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try {
        $digest = $algorithm.ComputeHash([Text.Encoding]::UTF8.GetBytes($value))
        return [BitConverter]::ToString($digest).Replace('-', '').ToLowerInvariant()
    } finally {
        $algorithm.Dispose()
    }
}

function Assert-FileHash([string] $path, [string] $expected, [string] $label) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or
        ((Get-Item -LiteralPath $path).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
        (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) {
        throw "$label missing, redirected, or changed"
    }
}

if ($manifest.run_id -ne $runId -or $aggregate.run_id -ne $runId -or
    $config.run_id -ne $runId -or $aggregate.protocol -ne 'nyc-acris-pilot-v2' -or
    $config.protocol -ne 'nyc-acris-pilot-v2' -or
    $aggregate.status -ne 'INCOMPLETE_ERROR' -or
    $aggregate.http_requests -ne 9 -or
    $aggregate.four_bbl_queries_finished -ne $true -or
    $aggregate.document_triage_finished -ne $false -or
    $aggregate.manual_reviews_completed -ne 0 -or
    $aggregate.sale_labels_certified -ne 0 -or
    $aggregate.u0_accepted -ne $false -or
    $aggregate.g_us_status -ne 'PENDING' -or
    $manifest.code_commit_at_execution -ne $config.code_commit) {
    throw 'Run identity, observed status, or gate differs from frozen evidence'
}

Assert-FileHash (Join-Path $root $manifest.environment_lock_path) $manifest.environment_lock_sha256 'Environment lock'
Assert-FileHash (Join-Path $PSScriptRoot 'configuration.json') $manifest.configuration_hash 'Configuration'
$checked = 0
foreach ($item in $manifest.immutable_files_sha256.PSObject.Properties) {
    $allowedRunPath = $item.Name -match '^runs/u0-nyc-acris-v2-20260929T012700Z/[A-Za-z0-9_.-]+$'
    $allowedSource = $item.Name -in @(
        '.gitattributes',
        'scripts/audit_nyc_acris_matches_v2.py',
        'tests/test_audit_nyc_acris_matches_v2.py',
        'decisions/0023-nyc-acris-document-triage-v2.md'
    )
    if (-not ($allowedRunPath -or $allowedSource)) {
        throw "Unexpected immutable path: $($item.Name)"
    }
    Assert-FileHash (Join-Path $root $item.Name) $item.Value 'Tracked pilot artifact'
    $checked++
}

$privateDir = Join-Path $root $config.private_run_dir
if (-not (Test-Path -LiteralPath $privateDir -PathType Container) -or
    ((Get-Item -LiteralPath $privateDir).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw 'Private run directory is missing or redirected'
}
$acl = Get-Acl -LiteralPath $privateDir
$ownerSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$allowedSids = @($ownerSid, 'S-1-5-18', 'S-1-5-32-544')
$accessSids = @($acl.Access | ForEach-Object {
    $_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value
})
if (-not $acl.AreAccessRulesProtected -or
    $accessSids.Count -eq 0 -or
    $accessSids -notcontains $ownerSid -or
    @($accessSids | Where-Object { $_ -notin $allowedSids }).Count -ne 0) {
    throw 'Private run directory ACL differs from the restricted policy'
}

$statePath = Join-Path $privateDir 'state.json'
Assert-FileHash $statePath $aggregate.private_artifacts.state_sha256 'Private pilot state'
if ((Get-Item -LiteralPath $statePath).Length -ne $aggregate.private_artifacts.state_bytes) {
    throw 'Private pilot state byte count differs'
}
$state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
if ($state.protocol -ne $aggregate.protocol -or
    $state.aggregate.status -ne $aggregate.status -or
    $state.aggregate.http_requests -ne $aggregate.http_requests -or
    $state.aggregate.query_sha256 -ne $aggregate.query_sha256 -or
    $state.intents.Count -ne $aggregate.http_requests -or
    $state.selected.Count -ne 4) {
    throw 'Private pilot state does not agree with the aggregate'
}

$responseHashes = @()
foreach ($intent in $state.intents) {
    if ($intent.body_file -notmatch '^response-[0-9]{3}\.bin$' -or
        $intent.body_sha256 -notmatch '^[0-9a-f]{64}$') {
        throw 'Private response metadata is missing or invalid'
    }
    $responsePath = Join-Path $privateDir $intent.body_file
    Assert-FileHash $responsePath $intent.body_sha256 'Private saved response'
    if ((Get-Item -LiteralPath $responsePath).Length -gt 1048577) {
        throw 'Private response exceeds the bounded read cap'
    }
    $responseHashes += $intent.body_sha256
}
if ($responseHashes.Count -ne $aggregate.private_artifacts.response_files -or
    @(Get-ChildItem -LiteralPath $privateDir -Filter 'response-*.bin' -File).Count -ne $responseHashes.Count -or
    (Get-Sha256Text ($responseHashes -join '|')) -ne $aggregate.private_artifacts.response_hash_list_sha256) {
    throw 'Private response inventory differs from frozen evidence'
}

foreach ($field in @('snapshot_path', 'ledger_path', 'code_table_path')) {
    $expected = switch ($field) {
        'snapshot_path' { $aggregate.snapshot_sha256 }
        'ledger_path' { $aggregate.ledger_sha256 }
        'code_table_path' { $aggregate.code_table_sha256 }
    }
    Assert-FileHash (Join-Path $root $config.$field) $expected 'Pinned private input'
}
$composite = @(
    $aggregate.snapshot_sha256,
    $aggregate.ledger_sha256,
    $aggregate.code_table_sha256,
    $aggregate.private_artifacts.state_sha256
) -join '|'
if ((Get-Sha256Text $composite) -ne $manifest.data_snapshot_hash) {
    throw 'Composite data snapshot hash differs'
}
Write-Output 'Verified frozen NYC ACRIS v2 hashes and nine private responses. Pilot remains INCOMPLETE_ERROR.'
