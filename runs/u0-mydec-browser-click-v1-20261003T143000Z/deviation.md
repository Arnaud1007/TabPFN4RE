# Private browser-profile retention deviation

The three frozen access plans scoped retained evidence to public-page HTML,
DOM captures, timestamps and hashes. The local Chrome and Playwright launch
also created two isolated browser profiles under protected, Git-ignored
`data/raw/illinois_mydec/`. They contain browser cache and session files and
are **not** required to verify the captured DOMs. Neither browser used a
personal Chrome profile or logged in to MyDec.

After review, a scoped recursive removal of these two generated profile
directories was attempted only after checking their resolved paths stayed
inside this project's private raw-data directory and rejecting reparse
points. Automatic approval review rejected the removal command as
**blocked by policy**. No profile file was removed. The profiles currently
occupy about 40.3 MB in total (20,988,740 and 19,352,193 bytes by a read-only
recursive size check). They remain protected by the private run-directory
ACLs and ignored by Git. Do not treat them as source evidence or include them
in a release. Remove them only through an approved, scoped cleanup path.
