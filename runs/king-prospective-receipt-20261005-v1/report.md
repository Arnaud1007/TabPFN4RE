# King local prediction receipt checkpoint

Run ID: `king-prospective-receipt-20261005-v1`  
Captured: `2026-10-05T18:58:08Z`  
Status: **verified local research workflow; not prospective certification**

## Result

The committed King research predictor created one access-restricted receipt
from the synthetic 15-field request. The terminal acknowledgement reported a
historical 2015 estimate of **$542,149.79 USD** without printing the property
inputs or enrollment reference.

| Field | Observed value |
| --- | --- |
| Receipt ID | `20261005T185808Z-bfb011357e08-64322df0c213` |
| Receipt bytes | `2,575` |
| Receipt file SHA-256 | `2f7e8d1a06e9e1fd658f7ae019fb109d255f04bbc42f6f38eee3e48a0ea80d7f` |
| Request SHA-256 | `bfb011357e08b374171034e7f0792b9ec5a046f6c03cfbc9d754d4895bc36942` |
| Response SHA-256 | `5076e40dabfae0b26f07932dba5dff3cdb27d061a1774909ce1cb21c68a6fc90` |
| Model SHA-256 | `cead625a3b87d73f46fdf740bfb366b9ff3b17d52434011a63e0ca91849f0033` |
| Manifest SHA-256 | `32c11c3ac12e69126d2e1b2b58ab9eb5403a001836cfeb102442b234fef7cbe9` |
| Code commit | `d32c5cbc7f50f8e4f937efc1546e27d08c4e389a` |
| Dirty tree at capture | `false` |
| Private directory ACL protected | `true` |

The exact receipt is intentionally excluded from Git because it contains the
validated property request. The receipt and its parent directory were checked
locally without printing those inputs.

## Verification

- Ruff passed for the capture command and its tests.
- Six focused receipt tests passed.
- The new module reached 81% branch-aware statement coverage.
- Forty-four King serving, form, launcher, HPI and receipt tests passed in the
  model environment.
- Python and security review found no critical, high or medium findings.
- The local and remote `audit/u0` heads both identified commit `d32c5cb` before
  this evidence report was written.

## Evidence boundary

This capture used the synthetic example and the historical 2015 model. It has
no future sale outcome. Its timestamp comes from the local workstation and has
no external timestamp or commitment. The local owner can modify or delete the
private file. It therefore proves the capture workflow only; it does not prove
a pre-outcome prediction, current valuation accuracy, a 90-day estimate, or a
G-US result. `certification_eligible` remains `false` and G-US remains
`PENDING`.

The next evidence upgrade is to add an authorised external commitment that
reveals no property inputs, then capture real enrolled properties before their
outcomes are available and wait for qualifying sales to mature.
