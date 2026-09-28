# Incomplete gate capture

The corrected launcher ran its commands but stopped while evaluating its overall status. Under PowerShell strict mode, an empty pipeline result has no `.Count` property. No gate manifest was written, so this attempt is **incomplete** and its individual logs are retained as diagnostic artifacts. A new run ID is used for the corrected status calculation.
