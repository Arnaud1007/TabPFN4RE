$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$private = Join-Path $projectRoot 'data\raw\cook_county\manual-review-v1'
$expectedLedger = 'f8a25a6f098ea62b5891e1c1a852a4d20826302725664814e54ee3a112f36436'
$expectedAggregate = 'b72ec03a5bc7d9295c89db436f457edd046c95cfa5774091f4aa3f99c57bfabb'

function Get-LowerHash([string]$path) {
    return (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
}

if ((Get-LowerHash (Join-Path $PSScriptRoot 'aggregate.json')) -ne $expectedAggregate -or
    (Get-LowerHash (Join-Path $PSScriptRoot 'replay_aggregate.json')) -ne $expectedAggregate -or
    (Get-LowerHash (Join-Path $private 'ledger-snapshot-u0-cook-review-progress-20261003T025709Z.jsonl')) -ne $expectedLedger) {
    throw 'Cook review progress artifacts differ from the frozen run'
}

$aggregate = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'aggregate.json') -Raw | ConvertFrom-Json
if ($aggregate.protocol -ne 'cook-source-review-v1' -or
    $aggregate.ledger_sha256 -ne $expectedLedger -or
    $aggregate.sample_count -ne 200 -or
    $aggregate.unreviewed_records -ne 198 -or
    $aggregate.partial_records -ne 1 -or
    $aggregate.complete_records -ne 1 -or
    $aggregate.certified_sale_labels -ne 0 -or
    $aggregate.historical_asof_eligible) {
    throw 'Cook review progress aggregate differs from the frozen run'
}

Push-Location $projectRoot
try {
    & 'runs/u0-cook-review-init-20261003T013215Z/verify_artifacts.ps1' | Out-Null
    $projection = & $python -c "import json; from scripts import review_cook_sales_sample as r, private_review_io as p; d=r.RAW_ROOT/r.REVIEW_NAME; rows=r._capture_rows(); p.real_directory(d,r.RAW_ROOT); p.verify_acl(d); m=r._manifest(d,rows); s=p.private_path(d/'ledger-snapshot-u0-cook-review-progress-20261003T025709Z.jsonl',d,must_exist=True).read_bytes(); entries,latest=r._history(s,rows,m['ledger_id'],m['created_at']); print(json.dumps(r._summary(s,latest),sort_keys=True))" | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or
        $projection.ledger_sha256 -ne $expectedLedger -or
        $projection.unreviewed_records -ne 198 -or
        $projection.partial_records -ne 1 -or
        $projection.complete_records -ne 1 -or
        $projection.certified_sale_labels -ne 0) {
        throw 'Cook private ledger snapshot replay differs'
    }
}
finally { Pop-Location }

Write-Output 'Cook review progress snapshot verified; one complete, one partial, zero certified labels; U0 and G-US pending'
