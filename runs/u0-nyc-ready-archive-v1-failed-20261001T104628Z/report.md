# NYC ready-archive v1: preserved failed capture

Status: **FAILED_STATUS_SCHEMA**. Code commit: `7878dbecd52657599ac69ad2398dfbe0d2bcc305`.
Protocol: [ADR 0042](../../decisions/0042-nyc-ready-rolling-archive-capture.md).

The fixed capture command started from a clean, pushed tree on 2026-10-01.
The first archival metadata GET passed and was saved privately. The first
status GET returned HTTP 200 with `type=done`, version `62` and the pinned
backend dataset identity. Its `value` object also contained storage fields
`rowLocation`, `columnLocation`, `refSize` and `gzipped`. The v1 parser required
only two fields in that object and raised `ValueError: Pinned archive is not
already generated`. That error describes **a schema rejection**, not evidence
that the archive was unavailable.

Only two GETs completed. The CSV route was **not requested**. The private
directory has the two original JSON responses and no collector manifest;
it remains an incomplete run. The [failure manifest](manifest.json) stores
their byte counts and hashes without response bodies. Raw JSON stays under
ignored `data/raw/nyc_dof/ready-archive-v1-20261001T104628Z/` with a checked
private ACL. No property rows or sale labels were acquired.

The next protocol version must accept and validate this exact documented
status shape while retaining the fixed dataset/version identity, status-before
gate, response limits and read-only GET restriction. Retry only in a new
private run directory after tests, review, commit and push. V1 stays failed;
do not rewrite its manifest or count this as a successful archive retrieval.
NYC certified sale labels: **0**. U0 and G-US: **PENDING**.
