# ADR 0019: NYC rolling dataset archive correction

Date: 2026-09-29

Owner: project implementation

Affected requirements: US02, US05, US08, US11, US22

## Evidence and correction

[ADR 0006](0006-nyc-king-source-feasibility.md) and the first NYC rolling
source card said that older portal versions were not retained. That conclusion
was too broad. The official [NYC Citywide Rolling Calendar Sales dataset
page](https://data.cityofnewyork.us/dataset/NYC-Citywide-Rolling-Calendar-Sales/usep-8jbt)
has an indexed Dataset Changelog with dated **Export Archive** entries. Indexed
entries include 2025-08-13, 2025-10-07, 2025-10-15, 2025-11-18, 2026-01-27,
2026-04-20, 2026-07-15 and 2026-08-28. The 2026-09-15 update is the current
view. These are observed portal entries, not locally recovered CSV files.

The platform's [archive documentation](https://support.socrata.com/hc/en-us/articles/9486838238743-Introducing-Dataset-Archiving)
says viewers without edit permission can request an archived CSV export. It
also says the archive is reconstructed from changes, so generation may take
time. The general [NYC Open Data terms](https://data.cityofnewyork.us/stories/s/Terms-of-Use/k9k7-3cje/)
still allow source updates; that does not prove this particular dataset has no
recoverable versions.

An attempt to open the dataset in the available in-app browser failed before a
tab was created (`failed to write kernel assets: The system cannot find the
path specified`). No archive export was requested or downloaded in this
decision. The public page and platform documentation establish a candidate
route, not yet verified local archive bytes or a complete historical series.

A read-only check of the page's client endpoints found anonymous changelog
requests under `/revision/usep-8jbt/changes` and `/revision/usep-8jbt` returning
HTTP 404 from this environment. A status GET to `/api/archival` for the current
replication version returned `not_started`. The page's archive-generation route
uses PUT; it was **not** invoked. These observations do not prove that the
dated archives are anonymously downloadable or reveal their revision numbers.

## Decision

Correct the source card and acquisition backlog. Audit the visible archive
route and recover a bounded archived CSV when access and reuse conditions are
settled. Preserve original bytes and the associated revision timestamp and
schema. Capture the current rolling CSV as an independent prospective snapshot
so later availability is evidenced without relying on portal retention.

Neither archive revision timestamps nor the current HTTP `Last-Modified`
header establish when each transaction row was first published. In particular,
[Socrata's system-field documentation](https://dev.socrata.com/docs/system-fields)
describes full replacements that reset row update timestamps. An archived
dataset can support a conservative **known by archive date** assertion for its
contents after its exact bytes and revision are verified; older row-level
availability requires further evidence. Do not infer close dates, unit identity
or commercial reuse rights from the existence of an export button.

## Alternatives considered

- Treat current rolling rows as historical records available at their sale
  dates: rejected because event date and first source availability differ.
- Treat the archive list as completed historical qualification: rejected because
  no archive bytes, rights decision or row-level semantics have been verified.
- Continue with only current-view snapshots: useful for prospective work, but
  would overlook a potentially valuable official vintage source.

US real-data training and certification remain blocked by rights, target/date
semantics, source availability and economic-transfer identity checks.

## Prospective capture contract

Before fetching the current rolling CSV, pin its exact official export URL,
allow at most 128 MiB and 150,000 parsed rows, and compare source metadata
and an independent official API `count(*)` before and after the transfer. The
capture must fail on schema or row-count mismatch, truncation, source change or
existing output path. Preserve full bytes only
under ignored `data/raw/nyc_dof/`; track a manifest with hashes, counts,
headers and capture times, without property rows or addresses. The earliest
time this capture demonstrates for its contents is completion of the download.
It cannot support an earlier valuation origin. This is a source inventory
capture, not a model-training authorization.

If a crash or temporary-file cleanup error occurs after hard-link publication,
the command can fail while a complete private CSV remains. Treat that file as
an **incomplete run** until its byte hash, schema, row count and source version
are checked against a separately saved capture manifest. Do not retry into or
overwrite the same filename, and do not infer that a failed command produced a
usable historical source.
