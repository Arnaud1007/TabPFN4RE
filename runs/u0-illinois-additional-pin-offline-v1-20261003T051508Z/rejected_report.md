# Additional PIN offline plan v1: rejected before execution

The frozen v1 plan transcribed the prior Cook/PTAX private worklist SHA-256 incorrectly as `7981f32fe1970afcb2c20768271c8831e3e69cf3e464e75c02e0`. The committed prior aggregate and a fresh hash of the unchanged private worklist both give `7981f32fe1970afcb2c20768271c5c0c58dc05ff9a3905fe94981aeef9f8ac8e`.

Architecture review found this discrepancy before code execution, private Additional-PIN inspection or Cook-to-Additional comparison. No v1 diagnostic directory, worklist or aggregate was created. Preserve v1 as a rejected plan. [ADR 0062](../../decisions/0062-illinois-additional-pin-offline-input-hash-correction.md) registers v2 with the verified hash and a new create-only run identity. Zero sale labels remain certified; U0 and G-US remain PENDING.
