# U0 NYC rolling sales source snapshot

Run ID: `u0-nyc-rolling-snapshot-20260928T225512Z`  
Capture code commit: `aaa86ff016cd9a2a6fd9a6674d23f2e57e7c549c`  
Requirements: US05, US06, US08, US22, US23, US24  
Status: **source inventory only; U0 pending; G-US pending**

## Objective and changes

Freeze one current [NYC Citywide Rolling Calendar Sales](https://data.cityofnewyork.us/dataset/NYC-Citywide-Rolling-Calendar-Sales/usep-8jbt)
CSV privately for later source qualification. [ADR 0019](../../decisions/0019-nyc-rolling-archive-correction.md)
corrects the earlier claim that the portal retains no older versions: its
indexed changelog shows eight dated Export Archive controls. Archived CSV bytes
and anonymous access remain unverified.

The committed capture script fixes the official source URLs, rejects redirects,
limits bytes and rows, checks the export schema against metadata, compares an
independent official API `count(*)` before and after, and publishes the raw CSV
with a no-overwrite hard link. Only [snapshot.json](snapshot.json) and aggregate
verification data are tracked. The source file stays in ignored
`data/raw/nyc_dof/`.

## Observed result

| Check | Result |
| --- | ---: |
| Official API count before and after | 82,345 / 82,345 rows |
| Parsed CSV rows | 82,345 |
| CSV bytes | 10,397,977 |
| CSV columns | 21 |
| CSV SHA-256 | `84c06057c52a2822f982cd98fb77ef7edf2c14134d00f46b073d2e4b762b2ef2` |
| Capture completed | 2026-09-28 22:55:43.929203 UTC |

An independent read of the stored file reproduced its SHA-256, byte size and
parsed row count ([verification.json](verification.json)). `git check-ignore`
confirmed `.gitignore` excludes the private CSV. The tracked records do not
include address or sale rows. The CSV is an unchanged source export; no
canonical transaction, eligibility decision, model row or prediction was made.

The capture completion time is a conservative **known by** bound for this
snapshot. HTTP `Last-Modified`, portal metadata versions and sale dates do not
establish each row's first availability. The 82,345 rows are portal records,
not unique residential transfers. This capture does not justify historical
training, a 90-day close-origin backtest, or a performance claim.

The environment record and configuration JSON were written after the capture
from the observed Python/test-tool versions and the already committed script
constants. They are reproducibility records, not evidence that a separate
environment lock was frozen before this source read.

## Commands and acceptance checks

The live capture ran from the project root with this PowerShell command, using
the committed `capture_snapshot()` function:

```powershell
@'
import json
from pathlib import Path
import sys
sys.path.insert(0, 'scripts')
from capture_nyc_rolling_snapshot import capture_snapshot
run = Path('runs/u0-nyc-rolling-snapshot-20260928T225512Z')
run.mkdir(parents=True, exist_ok=False)
result = capture_snapshot()
(run / 'snapshot.json').write_text(
    json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8'
)
print(json.dumps({key: result[key] for key in (
    'capture_status', 'rows', 'bytes', 'sha256', 'raw_filename',
    'capture_completed_at_utc')}, sort_keys=True))
'@ | .\.venv\Scripts\python.exe -
```

The CLI `.\.venv\Scripts\python.exe scripts/capture_nyc_rolling_snapshot.py
--capture` issues a **new** capture and must not be used to replay this run.
Verify this frozen run with `& 'runs/u0-nyc-rolling-snapshot-20260928T225512Z/verify_artifacts.ps1'`.

Synthetic checks: 19 tests passed; 81% branch-aware capture-script coverage.
The full suite passed 372 tests, zero skips. Ruff check and format, `pip check`,
and a scoped `pip-audit` of the local-date lock passed. The complete command,
exit-code and duration record is [test_gate.json](test_gate.json). Code,
Python and security reviews found no remaining high or critical issue.
Two local temporary-path prefixes in the saved full-suite log were replaced
with `<LOCAL_TEMP>` before the evidence manifest was frozen; test results were
not changed.

## Open defects and next action

Archive revision IDs and anonymous CSV access are unverified; no Export Archive
generation was requested. Source-specific reuse/redistribution, close-date
meaning, first row availability, tax-lot/unit identity, transfer scope and
historical physical-attribute vintages remain unresolved. The next independent
work is to qualify those contracts and audit 200 stratified source records
before building a certified adapter. The ongoing HCPA 200-record manual audit
also remains incomplete.

If a future capture fails after file publication but before temporary-file
cleanup, its private CSV may remain without a returned manifest. Treat it as
an incomplete run, reverify hashes and counts, and never silently promote it.
