$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$private = Join-Path $projectRoot 'data\raw\cook_county\manual-review-v1'
$initial = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'init_aggregate.json') -Raw | ConvertFrom-Json
$partial = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'partial_aggregate.json') -Raw | ConvertFrom-Json
$captureSha = '130b5169ff81ccbc0a729cba98400f2fb377ff9a25999316aaac1960e38a3cf7'

function Get-LowerHash([string]$path) {
    return (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
}

if ((Get-LowerHash (Join-Path $PSScriptRoot 'init_aggregate.json')) -ne '3c76896d5a983fbd4fc92760ab89597fdc60a4a24c2a3912afd9ca57963a0b8b' -or
    (Get-LowerHash (Join-Path $PSScriptRoot 'replay_aggregate.json')) -ne '3c76896d5a983fbd4fc92760ab89597fdc60a4a24c2a3912afd9ca57963a0b8b' -or
    (Get-LowerHash (Join-Path $PSScriptRoot 'partial_aggregate.json')) -ne '5d3283eacc6eb1749cf56806e947c826687bdf968d1d7201fd3f9a2c5a827bdf' -or
    (Get-LowerHash (Join-Path $PSScriptRoot 'replay_after_partial.json')) -ne '5d3283eacc6eb1749cf56806e947c826687bdf968d1d7201fd3f9a2c5a827bdf' -or
    $initial.protocol -ne 'cook-source-review-v1' -or
    $initial.capture_sha256 -ne $captureSha -or
    $initial.historical_asof_eligible -or
    $initial.sample_count -ne 200 -or
    $initial.unreviewed_records -ne 200 -or
    $initial.partial_records -ne 0 -or
    $initial.complete_records -ne 0 -or
    $initial.certified_sale_labels -ne 0 -or
    $initial.ledger_sha256 -ne 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855' -or
    $partial.protocol -ne 'cook-source-review-v1' -or
    $partial.capture_sha256 -ne $captureSha -or
    $partial.sample_count -ne 200 -or
    $partial.unreviewed_records -ne 199 -or
    $partial.partial_records -ne 1 -or
    $partial.complete_records -ne 0 -or
    $partial.certified_sale_labels -ne 0 -or
    $partial.historical_asof_eligible -or
    $partial.ledger_sha256 -ne 'c12b5a161299d5e7a5f0eabec3bf3a2423c02378a72325bab2e65c551f12b043') {
    throw 'Cook private review public summary differs from the pinned run'
}
if ((Get-LowerHash (Join-Path $private 'manifest.json')) -ne '4a13d92583b5d23eeb71a4048a69eb4531966c0d2bb12d9048cd073d00905d32' -or
    (Get-LowerHash (Join-Path $private 'worklist.jsonl')) -ne '3c97e76a0a7f3ea21fd19dfdbadb2dcac223f98ea69b6dc1eab650c3692d90ac' -or
    (Get-LowerHash (Join-Path $private 'ledger-snapshot-u0-cook-review-init-20261003T013215Z.jsonl')) -ne $partial.ledger_sha256) {
    throw 'Cook private review manifest, worklist or snapshot differs'
}
Push-Location $projectRoot
try {
    & 'runs/u0-cook-review-code-20261003T012707Z/verify_artifacts.ps1' | Out-Null
    $projection = & $python -c "import json; from scripts import review_cook_sales_sample as r, private_review_io as p; d=r.RAW_ROOT/r.REVIEW_NAME; rows=r._capture_rows(); p.real_directory(d,r.RAW_ROOT); p.verify_acl(d); m=r._manifest(d,rows); s=p.private_path(d/'ledger-snapshot-u0-cook-review-init-20261003T013215Z.jsonl',d,must_exist=True).read_bytes(); entries,latest=r._history(s,rows,m['ledger_id'],m['created_at']); print(json.dumps(r._summary(s,latest),sort_keys=True))" | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or
        $projection.ledger_sha256 -ne $partial.ledger_sha256 -or
        $projection.partial_records -ne 1 -or
        $projection.complete_records -ne 0 -or
        $projection.certified_sale_labels -ne 0) {
        throw 'Cook private ledger snapshot replay differs'
    }
}
finally { Pop-Location }
Write-Output 'Cook private review snapshot verified; one partial, zero complete, zero certified labels; U0 and G-US pending'
