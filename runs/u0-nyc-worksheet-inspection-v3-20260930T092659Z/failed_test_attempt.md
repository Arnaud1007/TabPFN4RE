# Preserved full-suite failure before the HCPA test correction

The first full-suite run on the final v3 parser ran 608 tests in 176.672 seconds and exited 1. The only failure was `test_hcpa_code_table.HcpaCodeTableTest.test_aggregate_hashes_labels_and_no_private_rows`: its `assertNotIn("9999", json.dumps(report))` matched the unrelated SHA-256 text `...01899992...` in the generated source archive hash. No private code-label row was emitted. The synthetic test has random archive bytes, so a digest substring was an unstable redaction assertion.

The correction asserts the exact allowed report key set and absence of deleted code `9999` from `selected_code_labels`; the existing exact expected label mapping remains. Sixteen focused HCPA tests passed afterward. A subsequent full-suite run passed 608 tests in 166.150 seconds. This failure is retained as an invalid test assertion, not counted as a passing first attempt or a source-data finding.
