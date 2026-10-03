# Read-only review notes

Date: 2026-10-03. Scope: the synthetic OFF median v2 bundle, serving view,
as-of version constant and focused tests. These are reviewer findings from
this checkpoint, not a production release approval.

| Review | Observed finding and response |
| --- | --- |
| Code | The first format expanded a huge finite Decimal before the byte cap. A pre-format width check and regression test now reject it. In v2, no critical or high issue remained. The medium limitation is that assembler semantics need a manual policy-version bump; one fixed snapshot canary does not cover all behavior. |
| Security | The first format exposed raw training row IDs and per-row hashes. V2 uses a separate serving object with only count and aggregate hash. The follow-up found no critical or high issue for the synthetic checkpoint. Trusted local bundle paths and a separately pinned digest remain required. |
| Python | Follow-up found no critical or high issue; Python 3.11 focused tests and Ruff passed. Rare descriptor-open/temporary-cleanup failures and power-loss directory durability remain outside the tested recovery guarantee. |

The remaining limitations are described in [ADR 0069](../../decisions/0069-synthetic-off-bundle-v2.md)
and the [run report](report.md). No reviewer classified this as a real-market
bundle or an accepted U6 release.
