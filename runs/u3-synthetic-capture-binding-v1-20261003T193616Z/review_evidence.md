# Review evidence

Date: 2026-10-03. Reviewed: synthetic capture parser and guarded fit,
replay verifier, fixture data, run evidence and release claims.

The code, Python and security reviewers found no remaining high or medium
production correctness or leakage finding after the following corrections:

- A byte-binding marker could be spoofed by constructing a model directly.
  Added `verify_synthetic_calendar_capture` to rehash, refit and compare the
  full saved model; the report limits its claim to a verified replay.
- A property observation exactly at the next source-local midnight could
  pass the date-only publication boundary. A failing boundary test preceded
  the `>=` guard; it now rejects that observation.
- The saved run verifier read bytes without the production file size cap and
  left redundant replay summary fields unchecked. It now uses a bounded
  read and checks the summary against the replayed model, protocol and exact
  frozen calibration/test ID list. Three summary tampering probes were
  rejected.
- The full-suite log retained a local account path. It was redacted before
  publication. The synthetic JSONL contains no real parcel, address or sale
  identifiers.

The remaining limitation is inherent to the fixture: its source ID, prices,
arm's-length status and publication dates are artificial. The model marker
alone cannot prove provenance, and no real-source rights or timing claims are
made. The verifier assumes a trusted local repository and is not an
untrusted-file execution sandbox.
