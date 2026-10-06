# King TabPFN 3.5 preflight

Date: 2026-10-06  
Code commit: `c57a104`  
Status: **BLOCKED before labels**

## Result

The project now has a bounded local evaluation path for the newest official
TabPFN family: package `tabpfn==9.1.0`, model TabPFN 3.5, and checkpoint
`tabpfn-v3.5-20260909.safetensors`. The real preflight exited with the expected
blocked status (`3`) without opening King labels, downloading weights, accepting
license terms, or calling remote inference.

Observed blockers:

- `tabpfn==9.1.0` is not installed.
- Installed Torch is CPU only, so CUDA is unavailable to Python.
- The private output volume had 130,052,096 free bytes; the registered safety
  floor is 8,589,934,592 bytes before accounting for a checkpoint copy.
- The authorized checkpoint revision and SHA-256 are unresolved.
- The checkpoint is not present locally.
- No owner-authored license decision exists for the exact checkpoint.

The NVIDIA RTX 3060 Laptop GPU is visible to the driver with 6 GiB VRAM, but the
registered full TabPFN 3.5 candidate requires at least 8 GiB and the installed
Torch build has no CUDA support. These are capability findings, not model
results.

## Current comparison status

No TabPFN prediction score exists yet. The current strongest King development
candidate remains XGBoost with log absolute-error objective: 8.27% MdAPE,
57.34% within 10%, 26.95% P90 APE, and -0.81% median signed percentage error on
5,108 November 2014 through February 2015 development sales. It does not pass
the project release thresholds.

## Resume condition

Execution becomes eligible only when the exact local checkpoint and owner
license decision are hash pinned, `tabpfn==9.1.0` and a matching CUDA Torch
runtime are installed, the registered GPU requirement passes, and the private
volume has the required free space. The runner then executes the same four
frozen windows with a 10,000-row context and reports a reduced-context
operational comparison against the full-history XGBoost incumbent.
