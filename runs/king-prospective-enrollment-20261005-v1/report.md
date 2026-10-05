# King prospective enrollment checkpoint

Date: 2026-10-05  
Requirement: US21, US23  
Gate: G-US remains **PENDING**

## Result

The local King County form can now create one historical research prediction and
record it in one action. The action writes an access-restricted private receipt
and a privacy-safe public commitment. It reuses the model already loaded by the
form and does not train a model.

If public commitment publication fails after the receipt is durable, the form
blocks another capture and offers a commit-only retry. Pending current-version
receipts are restored at startup. Retained v1 receipts are ignored by the v2
retry scanner. An exact existing public commitment makes retry idempotent.

## Verification

- Ruff format and lint: pass.
- 44 focused unit and Tk integration tests: pass.
- Branch coverage over the four enrollment modules: 80%.
- Saved-model integration: one receipt and one commitment; estimate
  `$542,149.7940648721`; commitment gate `PENDING`.
- Actual private-directory scan: completed with one pending current-version
  receipt while retaining the legacy v1 receipt.

The saved-model integration used the private legacy replay environment because
the small test environment does not contain XGBoost. No private receipt or
property input was added to Git.

## Scope

The estimate is still `historical_research_only`, based on the saved 2015 King
County checkpoint. This workflow records evidence before outcomes mature; it
does not make the estimate current, calibrated, or eligible for G-US.

## Commands

```powershell
& '.venv/Scripts/python.exe' -m unittest tests.test_capture_king_prediction tests.test_prepare_king_receipt_commitment tests.test_king_prospective_enrollment tests.test_king_research_form
& '.venv/Scripts/python.exe' -m coverage report --include='scripts/capture_king_prediction.py,scripts/prepare_king_receipt_commitment.py,scripts/king_prospective_enrollment.py,scripts/king_research_form.py' --fail-under=80
```

## Next action

Use **Predict + record** for a real, pre-outcome property observation with an
opaque reference. Keep the private receipt local and wait for a qualifying sale
to mature before any prospective accuracy claim.

