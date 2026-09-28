# Final source-status replay

The parent runner was called with `-OutputDirectory 'runs/synthetic conformal replay 20260928T191000Z'`. It captured Git source-tree status before creating its output directory, then passed 277 tests with zero skips and 90.93% package statement coverage. Lint, formatting, package checks and the pinned dependency audit exited zero. The output path contains spaces and coverage JSON succeeded. The original run's test and coverage hashes remained unchanged and its verifier passed after the replay.

The checkout was already dirty from uncommitted implementation work when this replay began, so the recorded `dirty_tree: true` is correct. This synthetic replay does not establish real interval calibration or G-US acceptance.
