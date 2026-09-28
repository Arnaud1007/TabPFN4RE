$ErrorActionPreference = 'Stop'
$run = 'runs/u0-hcpa-pin-gaps-20260928T222200Z'
$manifest = Get-Content -LiteralPath "$run/manifest.json" -Raw | ConvertFrom-Json

foreach ($entry in $manifest.immutable_run_files_sha256.PSObject.Properties) {
    $actual = (Get-FileHash -LiteralPath $entry.Name -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $entry.Value) {
        throw "Run file SHA-256 mismatch: $($entry.Name)"
    }
}

$configHash = (Get-FileHash -LiteralPath $manifest.configuration_path -Algorithm SHA256).Hash.ToLowerInvariant()
if ($configHash -ne $manifest.configuration_hash) {
    throw 'Configuration SHA-256 mismatch'
}

$privateHash = (Get-FileHash -LiteralPath $manifest.private_flags_path -Algorithm SHA256).Hash.ToLowerInvariant()
if ($privateHash -ne $manifest.private_flags_sha256) {
    throw 'Private flags SHA-256 mismatch'
}

$replayPath = 'data/raw/hcpa/pin-gap-flags-20260928T222200Z-replay.jsonl'
$replayHash = (Get-FileHash -LiteralPath $replayPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($replayHash -ne $manifest.private_replay_flags_sha256) {
    throw 'Private replay flags SHA-256 mismatch'
}

$fileCount = @($manifest.immutable_run_files_sha256.PSObject.Properties).Count
Write-Output "Verified $fileCount immutable run files, configuration and both private flag hashes."
