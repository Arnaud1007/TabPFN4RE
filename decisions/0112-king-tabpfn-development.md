# 0112 — King TabPFN 3.5 bounded development candidate

Status: implemented preflight; execution blocked by unresolved authorized weights and local capability

## Decision

Add exactly one TabPFN 3.5 research candidate to the frozen King County November 2014 through February 2015 rolling development protocol. The candidate uses `tabpfn==9.1.0`, official source release `v9.1.0` at commit `0b1a081`, the official model repository `Prior-Labs/tabpfn_3_5`, and filename `tabpfn-v3.5-20260909.safetensors`.

The official weights are gated. Package code calls its licence-acceptance guard before Hugging Face retrieval and offers no direct-download fallback. The project owner has not accepted those terms in this workspace. The exact authorized model revision, byte size, and SHA-256 therefore remain unresolved. They are deliberately `null` in the lock rather than invented.

## Fail-safe preflight

The preflight runs before any King source labels or frozen prediction rows are opened. It requires all of the following:

- Python-side package version exactly 9.1.0;
- a usable CUDA device with at least 8 GiB VRAM;
- at least 8 GiB free local disk;
- an already-local regular checkpoint no larger than 10 GiB;
- an exact pinned revision and SHA-256 in the hash-bound lock;
- a separate owner-authored licence decision authorizing the exact checkpoint for local research.

It never downloads a checkpoint, accepts terms, calls remote inference, or prints local paths. A blocked result is a valid privacy-safe capability finding and must not open source labels.

## Bounded candidate

If every prerequisite is later satisfied, run four fits on the existing frozen windows. Select at most the 10,000 most recent training rows independently inside each window, reuse the frozen training-only feature encoder, predict log price locally, and exponentiate positive point predictions. Preserve private row predictions and a hash-bound manifest. The candidate remains research-only, commercially ineligible, promotion-ineligible, and cannot change G-US from PENDING.

The 10,000-row context is an operational comparison with less sample access than the full-history tree candidates. No hyperparameter search is authorized. A later evidence commit may add scorecards only after the exact checkpoint and licence decision pass preflight.

## Evidence boundary

This change proves only that the newest documented TabPFN family has an executable, non-downloading admission gate and bounded local runner. It does not claim a TabPFN result, successful checkpoint access, licence eligibility, model superiority, or a completed US14 comparison.

## Hardened execution controls

The environment lock additionally pins Python 3.11.6, NumPy 2.4.6 and Torch 2.10.0. A completed run records package versions, Torch build, CUDA runtime, NVIDIA driver, platform and machine. It records the exact code commit, configuration hash, checkpoint ID/revision/SHA-256, and declared lock hash.

The runner verifies the private root's real path and ACL, copies the already-authorized checkpoint into an ACL-protected staging directory, verifies that snapshot before every model construction and again after all predictions, and removes the checkpoint copy before publishing artifacts. Hugging Face Hub, Transformers and datasets offline flags plus disabled TabPFN telemetry remain active throughout model construction, fit and all predictions. No token or cache authorization is attempted.

Each window records its exact selected context row count and row-ID hash. Each fitted model produces three prediction passes. The frozen maximum variation is USD 0.01 absolute and 1e-6 relative; exceeding either rejects the run. The exact candidate remains `random_state=42`, `n_estimators=8`.

Scorecards use the shared metric engine for every window and the pooled cohort. The frozen operational beat rule requires a 2% relative pooled MdAPE gain, improvement in at least three of four windows, within-10 degradation no greater than 0.5 percentage points, and P90 APE degradation no greater than 0.5 percentage points. This remains a reduced-context TabPFN versus full-history tree operational comparison. The manifest prohibits superiority wording because no matched-sample-access tree comparator exists.

The five-minute per-fit and twenty-minute overall limits are post-hoc rejection caps. They identify an over-budget completed call but cannot interrupt a hung native model call.
