# Review record

Reviewed scope: date-only property, attribute and prior-sale contracts; local-date
v2 assembly; exact/v1 compatibility; guarded synthetic median integration.

| Review | Finding | Resolution |
| --- | --- | --- |
| Python | A deed could appear once with an exact timestamp and once with a local date under conflicting identities. | Reconcile both raw source/deed and economic-transfer IDs across precisions; adversarial tests pass. |
| Code and Python | A later date-only expiry could not be applied to an earlier exact property or attribute without violating the exact class. | Added immutable typed reconciliation records and old/new version tests preserving both publication precisions. |
| Code | The shared assembler exceeded the project file limit. | Extracted guarded prior-sale selection into `asof_prior.py`; assembler is below 800 lines. |
| Python | The first internal reconciliation representation obscured field types and selector return types. | Replaced it with explicit typed property/attribute records, widened internal result types and narrowed exact/v1 selectors. |
| Security | No further critical or high finding after the mixed-precision identity fix; no secrets or unsafe execution, deserialization, shell, network or UI sink in the changed modules. | Dependency and lint gates are recorded separately. |

Code and Python reviewers approved the corrected feature path with no remaining
high or medium correctness/leakage finding. Mypy and Pyright were unavailable
in the local environment, so static type checking was not executed. The
reviews are code inspection evidence, not real-data source certification.
