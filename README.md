# TabPFN4RealEstate

Evidence-first research workspace for residential sale-price prediction. Work begins with U0, the legacy-project and data audit. The Ames engineering smoke baseline and retrospective legacy five-fold replay are available; neither is a US release or a real-world accuracy claim.

In Visual Studio 2022, choose **File > Open > Folder** and select this directory.

## Current evidence

- [migration_report.md](migration_report.md) records recovered and missing legacy inputs, the replay outcome, and the hardware audit.
- [U0 legacy replay report](runs/u0-legacy-replay-20260928T145000Z/report.md) records the original split, repeatability, archived-score mismatch and verification evidence.
- [requirements.yaml](requirements.yaml) tracks requirement IDs and evidence status.
- [next_action.md](next_action.md) gives the current runnable task and blockers.

Use Python 3.11.6 for the U0 smoke package. Raw source files, row-level predictions, derived data and model checkpoints stay outside Git. The application, real-world US evaluation and international stages remain gated by the supplied specification.
