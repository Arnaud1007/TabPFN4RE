$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$runId = 'u0-nyc-archive-metadata-20260929T021258Z'
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Raw | ConvertFrom-Json
$aggregate = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'aggregate.json') -Raw | ConvertFrom-Json
$replay = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'replay.json') -Raw | ConvertFrom-Json

function Assert-Hash([string]$relativePath, [string]$expectedHash) {
    $path = Join-Path $projectRoot $relativePath
    if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or
        ((Get-Item -LiteralPath $path).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
        (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedHash) {
        throw "Missing, redirected or changed artifact: $relativePath"
    }
}

if ($manifest.run_id -ne $runId -or
    $manifest.status -ne 'verified_metadata_inventory_only' -or
    $manifest.code_commit_at_capture -ne 'c70f00844b064de50e5f5ed04ac5e126d0839866' -or
    $manifest.protocol_path -ne 'decisions/0024-nyc-archive-metadata-probe.md' -or
    $manifest.environment_lock_path -ne 'locks/nyc-archive-metadata-environment.json' -or
    $manifest.private_raw_path -ne 'data/raw/nyc_dof/archive-metadata-20260929T021258Z/metadata.bin' -or
    $manifest.private_manifest_path -ne 'data/raw/nyc_dof/archive-metadata-20260929T021258Z/manifest.json') {
    throw 'Run identity or path mismatch'
}

Assert-Hash $manifest.environment_lock_path $manifest.environment_lock_sha256
Assert-Hash $manifest.private_raw_path $manifest.data_snapshot_hash
Assert-Hash $manifest.private_manifest_path $manifest.private_manifest_sha256
if ((Get-Item -LiteralPath (Join-Path $projectRoot $manifest.private_raw_path)).Length -ne $manifest.private_raw_bytes) {
    throw 'Private metadata byte count mismatch'
}
$privateManifest = Get-Content -LiteralPath (Join-Path $projectRoot $manifest.private_manifest_path) -Raw | ConvertFrom-Json
if ($privateManifest.run_status -ne 'metadata_captured' -or
    $privateManifest.http_status -ne 200 -or
    $privateManifest.metadata_sha256 -ne $manifest.data_snapshot_hash) {
    throw 'Private metadata capture was not complete'
}

$expectedNames = @('configuration.json', 'aggregate.json', 'replay.json', 'test_gate.json')
$paths = @($manifest.immutable_files_sha256.PSObject.Properties)
if ($paths.Count -ne $expectedNames.Count) { throw 'Unexpected immutable artifact count' }
foreach ($item in $paths) {
    $expectedPath = "runs/$runId/$(Split-Path -Leaf $item.Name)"
    if ($item.Name -ne $expectedPath -or (Split-Path -Leaf $item.Name) -notin $expectedNames) {
        throw 'Unexpected immutable artifact path'
    }
    Assert-Hash $item.Name $item.Value
}
if ($manifest.configuration_hash -ne $manifest.immutable_files_sha256."runs/$runId/configuration.json" -or
    $aggregate.metadata_sha256 -ne $manifest.data_snapshot_hash -or
    $aggregate.metadata_bytes -ne $manifest.private_raw_bytes -or
    $aggregate.http_status -ne 200 -or
    $aggregate.captured_at_utc -ne $privateManifest.captured_at_utc -or
    $aggregate.content_type -ne $privateManifest.content_type -or
    $aggregate.archive_availability -ne 'unverified' -or
    $aggregate.certification -ne 'none' -or
    @($aggregate.versions).Count -ne 13 -or
    @($replay.versions).Count -ne 13 -or
    $manifest.immutable_files_sha256."runs/$runId/aggregate.json" -ne $manifest.immutable_files_sha256."runs/$runId/replay.json") {
    throw 'Public aggregate, replay or configuration mismatch'
}
$commitPath = "$($manifest.code_commit_at_capture):scripts/probe_nyc_archives.py"
$protocolPath = "$($manifest.code_commit_at_capture):$($manifest.protocol_path)"
if ((& git -C $projectRoot rev-parse $commitPath).Trim() -ne $manifest.code_blob -or
    (& git -C $projectRoot rev-parse $protocolPath).Trim() -ne $manifest.protocol_blob) {
    throw 'Frozen code or protocol blob mismatch'
}
Write-Output 'Verified frozen metadata capture, 13 visible revisions, exact offline replay and private/public hashes. Archive availability and U0 remain pending.'
