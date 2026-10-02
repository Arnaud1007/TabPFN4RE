# ADR 0043: version-62 ready-status response contract

Date: 2026-10-01
Owner: project implementation
Status: approved for a separately versioned read-only capture
Protocol: `nyc-ready-rolling-archive-v2`
Requirements: US05, US08, US22, US24

## Failed v1 evidence

The reviewed v1 collector was pushed at `7878dbecd52657599ac69ad2398dfbe0d2bcc305`
before its live request. The [preserved failed run](../runs/u0-nyc-ready-archive-v1-failed-20261001T104628Z/report.md)
made only the metadata and status GETs. Status reported `done` for the pinned
backend dataset and version 62 but contained four additional storage fields.
V1 required an exact two-field `value` object and stopped **before** the CSV
GET. No v1 collector manifest or archive CSV exists. The v1 result stays
failed; this decision does not reinterpret it as a successful capture.

## V2 change

Keep ADR 0042's dataset, version, five fixed GETs, response limits, private
storage, code-before-data push, replay and interpretation. Only the status
parser changes. Require an exact six-field `value` object:

- `datasetName` exactly `foxtrot.67157` and integer `version` exactly `62`;
- `rowLocation` exactly
  `compressed/materializations/v3/foxtrot.67157/62/rows`;
- `columnLocation` exactly
  `compressed/materializations/v3/foxtrot.67157/62/columns`;
- positive integer `refSize` no greater than 128 MiB;
- boolean `gzipped` equal to `true`.

These fields describe internal archive storage. `gzipped` does not authorize
a compressed HTTP CSV response; ADR 0042's identity HTTP encoding check
still applies. Require the full validated status object to agree before and
after the CSV. Reject unknown keys, a different storage path, missing or
ill-typed values and a status other than `done`. Do not publish the returned
status response or storage paths in public run artifacts. The pinned paths
listed above remain visible in this protocol and the collector code. The
public aggregate contains counts and hashes only.

Use a new private run ID. Tests must show the v1 response shape is rejected
under v2 and the observed six-field shape passes; malformed or changed paths,
refSize and gzipped fail before CSV or leave an incomplete run. Review, test,
commit and push v2 code before any new live GET. Keep all U0 and G-US gates
pending until source timing, target, rights and unit/transfer semantics are
qualified independently.
