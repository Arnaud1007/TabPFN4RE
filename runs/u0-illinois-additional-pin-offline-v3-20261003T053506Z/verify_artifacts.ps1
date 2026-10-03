$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Push-Location $projectRoot

try {
    $verification = @'
import json
from pathlib import Path
from scripts import audit_illinois_additional_pins as audit

source = Path('data/raw/illinois_ptax203/ptax-additional-v2-130b5169ff81ccbc')
private = Path('data/raw/illinois_ptax203/ptax-additional-offline-v3-130b5169ff81ccbc')
public = Path('runs/u0-illinois-additional-pin-offline-v3-20261003T053506Z/aggregate.json')
if audit.verify(private, source) != json.loads(public.read_text(encoding='utf-8')):
    raise SystemExit('Offline aggregate differs from pinned private evidence')
print('offline_private_and_public_replay_pass')
'@
    $verification | & '.\.venv\Scripts\python.exe' -B -
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}
