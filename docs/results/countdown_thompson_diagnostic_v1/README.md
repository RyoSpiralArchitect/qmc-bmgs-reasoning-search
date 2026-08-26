# Countdown Thompson diagnostic v1 post-hoc receipts

`posthoc_mechanism_v3.json` is the canonical receipt.

- schema: `qmc-bmgs-countdown-thompson-posthoc-mechanism/v3`
- deterministic digest:
  `02a0ecd90f6e695d22f06d77ee74a41210045811913c9e5b2bd793110089c262`
- raw SHA-256:
  `07c747aaaef5709c3b215b7c7645d34e8968712c5b273fe29b016510d9ac596c`
- source revision: `a4e4d8809146b7a861c6bf0dee645794683dddd0`
- handoff decision: `STOP_REPAIR_NO_LOCKED_128_RUN`

`posthoc_mechanism.json` is the retained schema-v1 receipt. A fresh review found
that v1 hashed caller path spelling and did not materialize two supporting
validation claims. Schema v2 resolves all input paths before hashing and adds a
clearly separated `supplemental_validation` block. The frozen performance
reductions are identical between v1 and v2.

`posthoc_mechanism_v2.json` is also retained. A focused rereview found that
`Path.resolve()` alone preserves caller casing on the case-insensitive host
filesystem. Schema v3 walks device/inode identities and records actual parent
directory-entry spelling. Independent runs supplied lowercase `/users/...` and
normal `/Users/...` input paths and produced byte-identical v3 receipts. V1,
v2, and v3 frozen reductions are identical; v2 and v3 supplemental values are
identical.

Neither receipt authorizes a retry, a provider call, a new outcome-bearing
cohort, or locked-128 execution. Integrity `PASS` is provenance, replay,
coverage, and deterministic reduction closure only.
