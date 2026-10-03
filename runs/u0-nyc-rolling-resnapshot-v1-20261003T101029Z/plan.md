# NYC rolling-sales repeat source snapshot: frozen plan

Run ID: `u0-nyc-rolling-resnapshot-v1-20261003T101029Z`  
Protocol: `nyc-rolling-resnapshot-v1`  
Status before source read: **planned**  
Requirements: US02, US05, US06, US08, US22, US24

## Question and prior evidence

Capture the official `usep-8jbt` current CSV once and compare its **file bytes**
with the private snapshot completed on 2026-09-28. A changed source file will
establish only that this project's two observations differ. An identical file
will establish byte equality at the two observed captures. Neither result
establishes first publication of a row, a true close date, a dwelling transfer,
or permission for model training or commercial use.

The prior public snapshot manifest is
`runs/u0-nyc-rolling-snapshot-20260928T225512Z/snapshot.json`, SHA-256
`45049ce1622ba4a819f29c79097869c9f3601d049139869982ec7327ee11962b`.
It records 82,345 rows, 10,397,977 bytes, CSV SHA-256
`84c06057c52a2822f982cd98fb77ef7edf2c14134d00f46b073d2e4b762b2ef2`,
and capture completion `2026-09-28T22:55:43.929203Z`.

## Frozen execution

- Use committed `scripts/capture_nyc_rolling_snapshot.py`, SHA-256
  `4d4b8e8bba32a432c3b9fd4261db84ea491c32b852087acdfb7d9e138a0f3b`.
  The script pins the official URLs, rejects redirects, checks metadata and
  independent row counts before and after, and keeps raw CSV under ignored
  `data/raw/nyc_dof/`.
- Use `locks/nyc-capture-environment.json`, SHA-256
  `36704b74db06542538d2e4b3c8c1359d523872500729f1a433764b25532dd751`.
  Record the actual code commit, dirty-tree state and environment in the report.
- One live CSV capture only; 128 MiB / 150,000-row caps, 30-second request
  timeout and 240-second transfer cap. No paid service. Preserve an incomplete
  attempt with its error if the source changes during transfer. Do not retry
  merely to obtain a favorable comparison.
- Save `snapshot.json` with the script's aggregate result. Verify its private
  CSV SHA-256, bytes, parsed row count, schema, and Git exclusion independently.
  Save no address, unit, price, identifier or row-level hash in tracked files.
- Compare only the new and prior CSV SHA-256 and byte count in the public
  report. If the files differ, register a later private, bounded source-row
  comparison before characterizing any row change. No model, split or label
  artifact is created; their hashes and checkpoint identity are not applicable.

## Adoption and stop rule

Treat the result as a repeat source observation and update the source card's
capture history. Keep NYC at source-inventory status and U0/G-US PENDING with
zero certified labels. Do not infer row-first-availability from the portal's
version timestamps, HTTP headers or snapshot difference. Do not start another
capture under this run ID after a completed result.
