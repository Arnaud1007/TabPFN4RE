# Market candidate validation reviews

Date: 2026-10-03. Scope: public candidate manifest, pinned Census workbook
validator and tests. Code, Python and security reviewers performed independent
read-only reviews.

The initial review found that the CLI hashed workbook bytes and then reopened
the path to parse them. A concurrent file replacement could have attached the
approved digest to different geography. The validator now parses the exact
bounded byte buffer it hashed. The JSON manifest is likewise parsed and
hashed from one bounded buffer. Source-card paths resolve inside the checked
directory; no XLSX member is extracted to disk.

Review also identified malformed nested JSON that could raise raw Python
exceptions. The validator now checks container shapes and critical field
types before constructing ID sets or indexing nested values. Fifteen focused
tests passed with 84% branch-aware coverage after those corrections. All three
reviewers found no remaining pre-push blocker. Their residual observation is
that the nonmetro entries define candidate rules, not a verified county list;
the validator and report explicitly keep that claim unverified.

The public files contain geographic names, source-card links and hashes only.
No parcel, address, party, real sale row, secret, model score or certification
label was added.

Pre-push packaging also preserved the exact line endings of the hashed
planning files through explicit Git attributes, and removed trailing Markdown
spaces from ADR 0085. The evidence hashes were regenerated after this change.
