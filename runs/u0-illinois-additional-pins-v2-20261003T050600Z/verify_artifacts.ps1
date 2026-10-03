$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Push-Location $projectRoot
try {
    $verification = @'
import json
from pathlib import Path
from scripts import probe_illinois_additional_pins as probe

private = Path('data/raw/illinois_ptax203/ptax-additional-v2-130b5169ff81ccbc')
public = Path('runs/u0-illinois-additional-pins-v2-20261003T050600Z/aggregate.json')
if probe.verify(private) != json.loads(public.read_text(encoding='utf-8')):
    raise SystemExit('Additional PINs aggregate differs from pinned private evidence')
print('additional_pins_private_and_public_replay_pass')
'@
    $env:PYTHONDONTWRITEBYTECODE = '1'
    $verification | & '.\.venv\Scripts\python.exe' -B -
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}
