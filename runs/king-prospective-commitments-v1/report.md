# King public receipt commitment checkpoint

Status: **privacy-safe synthetic workflow evidence; not certification**  
Prepared: `2026-10-05T19:24:03Z`

The v2 King receipt workflow captured the synthetic request from clean commit
`b59ac89d1d0dbc36de509f36b673eaa60dd5ad01`, then prepared the public
commitment in this directory. Committing and pushing the JSON records its
nonce-hardened whole-receipt digest in the remote repository without
publishing the private receipt.

## Public artifact

- Commitment ID: `2be035f8288fa53b2ad90a29`
- Private receipt byte count: `3,009`
- Nonce-hardened receipt SHA-256:
  `2be035f8288fa53b2ad90a297d25818fdc490c73b16abc647a8bb1808668db4f`
- Model SHA-256:
  `cead625a3b87d73f46fdf740bfb366b9ff3b17d52434011a63e0ca91849f0033`
- Model manifest SHA-256:
  `32c11c3ac12e69126d2e1b2b58ab9eb5403a001836cfeb102442b234fef7cbe9`

The exact private receipt remains ignored under `data/raw/`. Its 256-bit
privacy nonce hardens the public whole-receipt digest against enumeration. A
96-bit nonce prefix appears only in the private receipt ID; 160 nonce bits
remain undisclosed.

## Privacy verification

The committed JSON contains none of the following: property fields or values,
prediction amount, canonical or raw request hashes, response hash, enrollment
reference hash, private receipt ID, or local prediction capture time. An
automated canary comparison against the private receipt reported zero forbidden
matches. The artifact explicitly records `property_inputs_published: false`,
`certification_eligible: false` and `g_us_gate: PENDING`.

## Validation evidence

- Receipt and commitment tests passed three consecutive runs.
- The focused suite passed 12 tests; the broader King integration set passed
  50 tests.
- The two receipt modules reached 80% combined branch-aware coverage.
- Concurrent publishers produced one complete artifact and one controlled
  create-only failure.

The exact commands, repetitions, counts and exit codes are retained in
[`test_gate.json`](test_gate.json). Read-only Python and security reviews were
completed in the implementation session; all blocking findings were addressed.

## Evidence boundary

This is a synthetic workflow check. Repository publication commits the private
receipt bytes but does not authenticate the workstation clock, prove that a
real outcome was unknown, supply a matured sale, or measure accuracy. It cannot
advance G-US by itself. Real prospective evidence requires pre-outcome capture
of enrolled properties, prompt commitment publication, a frozen matching and
eligibility rule, and later qualifying outcomes.
