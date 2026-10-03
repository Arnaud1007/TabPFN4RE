# U0 Cook County Socrata system-field probe

Run ID: `u0-cook-system-fields-v1-20261003T030715Z`  
Baseline code commit: `ba29f63b6ef16324bf12e562884e712290df8a9c`  
Requirements: US02, US05, US08, US24  
Status: **platform timestamps exposed for one pinned source row; U0 and G-US PENDING**

## Question and result

The [frozen plan](plan.md) asked whether the official Cook Parcel Sales API
exposes Socrata's hidden row creation and update fields for a row already in
the protected 200-row audit sample. A single anonymous read-only GET returned
HTTP 200 in **526 ms** with one identity-matched row and exactly the requested
four fields. The 133-byte response remains private. The
[public aggregate](aggregate.json) records only field names, counts and hashes.
The exact request URL and response are in an ACL-restricted, Git-ignored
directory. No new sale row, personal name, address or price was requested.

An exploratory full-dataset aggregate query first timed out after 20 seconds
and saved no data. A separate, one-row endpoint health request returned HTTP
200 and 568 bytes but saved no source row. Neither was part of the frozen
probe. The bounded probe above was performed once without retry.

## Interpretation

The result changes the source inventory: this SODA endpoint can return
`:created_at` and `:updated_at` for the checked row when explicitly selected.
[Socrata's documentation](https://dev.socrata.com/docs/system-fields.html)
defines them as platform row creation and update timestamps, and notes that
full dataset replacement can update all rows. The timestamps do **not**
establish first public availability, a transaction closing date or historical
attribute availability. [ADR 0056](../../decisions/0056-cook-socrata-system-timestamp-boundary.md)
keeps them diagnostic only. **Zero Cook sale labels are certified.**

## Reproduction and remaining work

The query selected `:id,:created_at,:updated_at,row_id`, filtered to one pinned
private `row_id`, and set `$limit=1` against the official `wvhk-k5uv` resource.
It used a 12-second timeout and a 16 KiB cap. The private manifest contains
the exact encoded URL, UTC capture time, HTTP status, duration and SHA-256 of
the response. The [offline verifier](verify_artifacts.ps1) checks those bytes,
the pinned sample, response shape, identifier equality, query scope and
private ACL without making a network request:

```powershell
& 'runs/u0-cook-system-fields-v1-20261003T030715Z/verify_artifacts.ps1'
```

The [execution gate](test_gate.json) records exit codes, durations and output
hashes for the verifier, 21 focused private-ledger tests, `pip check` and
`pip-audit`; all exited 0. No package implementation changed in this run.

First-publication history, recorded-versus-closing semantics, transfer scope,
attribute vintages, rights and the remaining Cook manual reviews still need
authoritative evidence. No training, calibration or final test occurred. Split,
feature-policy and checkpoint hashes are inapplicable to this source probe.
