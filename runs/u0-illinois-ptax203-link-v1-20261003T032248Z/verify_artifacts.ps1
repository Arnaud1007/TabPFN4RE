$ErrorActionPreference = 'Stop'
$env:PYTHONDONTWRITEBYTECODE = '1'
@'
import json
from pathlib import Path
from scripts.probe_illinois_ptax203 import verify
run = Path("data/raw/illinois_ptax203/ptax-link-v1-130b5169ff81ccbc")
public = Path("runs/u0-illinois-ptax203-link-v1-20261003T032248Z/aggregate.json")
expected = json.loads(public.read_text(encoding="utf-8"))
if verify(run) != expected:
    raise SystemExit("PTAX offline replay differs from committed aggregate")
print("PTAX offline replay matched committed aggregate")
'@ | & .\.venv\Scripts\python.exe -
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
