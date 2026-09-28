# Incomplete gate capture

The first PowerShell gate launcher stopped while piping the test runner's normal stderr summary to a log. `$ErrorActionPreference = 'Stop'` treated the native stderr stream as a terminating `NativeCommandError`. It did not write a gate manifest, so this attempt is **incomplete** and no test result is claimed from it. The partial `tests.log` and original launcher are retained. The corrected launcher uses a new run ID and leaves this attempt untouched.
