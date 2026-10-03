# Separate host audit result

The first dependency audit command was `py -3.14 -m pip_audit --local
--progress-spinner off`. It audited the global Python 3.14 installation,
not the project's Python 3.11 `.venv`, and exited **1** after 34.6 seconds.
Its output reports 229 advisory rows in 29 host packages. The exact raw log
is retained locally at Git-ignored
`data/raw/local_audits/u1-synthetic-validity-v1-20261003T160514Z-host-pip-audit.log`
with SHA-256
`4a5791bf3292ad832f08d7694df5520ac68a08f5148ea772d3698d2740eddf7e`.
It is not a passing check and is not a claim about the project environment.

The later scoped audit uses `--path .venv/Lib/site-packages`; its actual
command, exit and output are in `project_audit_gate.json` and
`project_pip_audit.log`. The project environment passed with no known
vulnerabilities among auditable packages; the local editable package itself
was skipped. No host packages were installed, upgraded or removed in this run.
