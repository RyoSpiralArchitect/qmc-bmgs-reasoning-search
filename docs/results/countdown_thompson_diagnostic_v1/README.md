# Countdown Thompson diagnostic v1 post-hoc receipts

`posthoc_mechanism_v2.json` is the canonical receipt.

- schema: `qmc-bmgs-countdown-thompson-posthoc-mechanism/v2`
- deterministic digest:
  `380660d5f68fb41b805864bded9d68f8d55263551c8b2dc6061489fcaefa6851`
- raw SHA-256:
  `c606f9c26145f7676a9eb567868f044fbcff21d17de8464cb16877a4976da764`
- source revision: `d366af83b0e06bf2a32bab6356425405b136cb8c`
- handoff decision: `STOP_REPAIR_NO_LOCKED_128_RUN`

`posthoc_mechanism.json` is the retained schema-v1 receipt. A fresh review found
that v1 hashed caller path spelling and did not materialize two supporting
validation claims. Schema v2 resolves all input paths before hashing and adds a
clearly separated `supplemental_validation` block. The frozen performance
reductions are identical between v1 and v2.

Neither receipt authorizes a retry, a provider call, a new outcome-bearing
cohort, or locked-128 execution. Integrity `PASS` is provenance, replay,
coverage, and deterministic reduction closure only.
