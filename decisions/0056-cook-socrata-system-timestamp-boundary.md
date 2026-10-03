# ADR 0056: Cook Socrata system timestamp evidence boundary

- Date: 2026-10-03
- Owner: project implementation
- Affected requirements: US02, US05, US08, US24
- Protocol: `cook-system-fields-v1`

## Question and alternatives

The Cook Parcel Sales source card had no row-availability field among the
publisher columns in the frozen capture. Official Socrata documentation
describes hidden `:created_at` and `:updated_at` system fields. We considered
ignoring them, treating them as first-publication dates, or testing whether
they are exposed while keeping their platform meaning distinct from public
availability. The third option adds source evidence without weakening the
as-of gate.

## Evidence and choice

The [frozen probe plan](../runs/u0-cook-system-fields-v1-20261003T030715Z/plan.md)
limited a read-only query to one row already in the protected 200-row sample.
The [public aggregate](../runs/u0-cook-system-fields-v1-20261003T030715Z/aggregate.json)
records HTTP 200, one identity-matched result and the four requested fields.
The exact response and URL are hashed and held in ACL-restricted storage.
The [run report](../runs/u0-cook-system-fields-v1-20261003T030715Z/report.md)
records the command, replay and limits. It does not publish row identifiers or
timestamp values.

Socrata calls `:created_at` platform record creation and `:updated_at` last
platform update. Its [official system-field documentation](https://dev.socrata.com/docs/system-fields.html)
warns that full dataset replacement can update all rows. The docs do not say
that either value proves when a row first became publicly visible. The source
metadata also describes Assessor sale entries arriving months after recording.
One live row response cannot establish historical availability for the source.

Keep the fields as **platform chronology diagnostics**. Do not map either to
the certified `available_at` field without dated publisher evidence or an
explicit custodian clarification. Keep zero certified labels and the primary
90-day benchmark blocked. A future historical snapshot programme can record
first *observed* dates prospectively, with its own coverage limitations.

No split, model, calibration, licence or service-scope protocol changes.
