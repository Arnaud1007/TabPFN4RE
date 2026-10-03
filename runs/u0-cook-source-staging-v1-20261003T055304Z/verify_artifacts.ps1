$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Push-Location $projectRoot

try {
    $verification = @'
import json
from pathlib import Path
from scripts import assemble_cook_parcel_observations as stage

private = Path('data/raw/cook_county/parcel-staging-v1-130b5169ff81ccbc')
public = Path('runs/u0-cook-source-staging-v1-20261003T055304Z/aggregate.json')
if stage.verify(private) != json.loads(public.read_text(encoding='utf-8')):
    raise SystemExit('Cook staged aggregate differs from pinned private evidence')
print('cook_source_staging_private_and_public_replay_pass')
'@
    $verification | & '.\.venv\Scripts\python.exe' -B -
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}
