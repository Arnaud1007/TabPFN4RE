# ADR 0069: Synthetic OFF median serving bundle

Date: 2026-10-03
Owner: project implementation
Status: verified engineering contract, subject to the linked test report
Affected requirements: US14, US22, US23 T10
Affected protocol: `synthetic_off_median_v2`; no real-market release protocol

## Context and alternatives

The U1 `GuardedOffMedian` could predict from an in-memory object but could not
be reloaded as a checked artifact. Pickle was excluded because deserializing an
untrusted object is unsafe. A direct JSON copy of the training object was
rejected after security review: it would expose economic-transfer row IDs and
per-row feature hashes in a portable bundle. Replacing those IDs with invented
values on load would misrepresent the training manifest.

## Decision

The training object keeps its row IDs for fit-time split and leakage checks;
the separate serving view omits them. `save_off_median_bundle` writes this view as
strict, versioned UTF-8 JSON. It includes the price, training cutoff, row
count and one digest of the ordered feature-snapshot hashes. It contains no
training row IDs or per-row hashes. The serving view shares the same OFF
prediction path and as-of guard with the training object.

The writer bounds file and fixed-decimal size, fsyncs a temporary file, and
publishes via a create-only hard link on the same local filesystem. A failed
link leaves no accepted target. The loader caps reads and requires a
caller-supplied SHA-256; the caller must pin that digest in a separate trusted
manifest. It rejects duplicate/unknown JSON
fields, validates the model and refuses incompatible mode, currency, schema,
policy or format. A digest stored next to a bundle would be only an integrity
checksum, so the caller must pin the expected digest separately. Bundle
directories and their parents are trusted local paths.

The bundle carries `certification_eligible: false`. It has no intervals,
calibrator, approved source cohort, real split or release ID. The input-schema
fingerprint covers canonical dataclass fields and types. The feature-policy
fingerprint covers the declared OFF feature set and an explicit as-of assembler
policy version. These checks do not automatically detect a semantic code
change if a maintainer forgets to bump that version. A fixed synthetic
prediction-snapshot hash in the test suite provides one behavior canary; a
real release requires broader compatibility evidence and a complete bundle.
The current hard-link publication is tested for process exceptions on NTFS,
but power-loss durability of its directory entry is not established.

## Evidence and next step

The [bundle tests](../tests/test_off_baseline_bundle.py) exercise prediction
parity, UTC-offset round trip, deterministic bytes, digest and schema checks,
privacy, no-overwrite and failed-publish cleanup. Commands, coverage and
limits are in the [run report](../runs/u1-synthetic-off-bundle-v2-20261003T122750Z/report.md).
Keep U0, U6 and G-US pending. A real model bundle must be designed after the
eligible source, feature policy, model family and calibration contract are
frozen; the synthetic median format is never promoted to a US release.
