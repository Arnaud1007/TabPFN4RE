# TabPFN4RealEstate

Evidence-first research workspace for residential sale-price prediction. Work begins with U0, the legacy-project and data audit. The only executable model so far is an Ames engineering smoke baseline; it is not a US release or an accuracy claim.

In Visual Studio 2022, choose **File > Open > Folder** and select this directory.

## Current evidence

- [migration_report.md](migration_report.md) records verified inputs, missing legacy artifacts and the hardware audit.
- [requirements.yaml](requirements.yaml) tracks requirement IDs and evidence status.
- [next_action.md](next_action.md) gives the current runnable task and blockers.

Use Python 3.11.6 for the U0 smoke package. Raw source files, derived data and model checkpoints stay outside Git. The application, real-world US evaluation and international stages remain gated by the supplied specification.
