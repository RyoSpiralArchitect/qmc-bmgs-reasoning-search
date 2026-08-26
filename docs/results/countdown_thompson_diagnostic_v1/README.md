# Countdown Thompson diagnostic v1 post-hoc receipts

## Selection-margin sensitivity

`selection_margin_v1.json` is the canonical read-only selection-margin receipt.

- schema: `qmc-bmgs-countdown-thompson-selection-margin/v2`
- deterministic digest:
  `4b21ce04fe9c41b2553eea13925b1ffa17a9321c4f13c48c653a43c0d7a25f38`
- raw SHA-256:
  `14e87c3fac746918546ecb9e63e75822bab464899d4977452ce16eae60e93828`
- byte count: 2,002,183
- source revision: `09c7ce34d8576deffbd2bc91b22771db4b7950db`
- handoff decision: `STOP_REPAIR_NO_LOCKED_128_RUN`

It reconstructs the recorded posterior before each feedback-informed
selection, reports exact-rational local scale boundaries, and pairs v2/v3 only
while their pre-decision surface remains identical. It evaluates no terminal
performance counterfactual.

A fresh review of the initial PR found that caller-supplied hashes could stand
in for the frozen anchors, the tracked receipt itself was absent from the test
surface, and imported publication failures escaped the canonical CLI error
boundary. The source revision above pins every frozen identity in code,
cross-checks stable post-hoc authority metadata, validates this tracked receipt
in the repository suite, and returns canonical `INVALID` for those failures.
Schema v2 additionally binds the loaded audit, post-hoc, analyzer, publication,
trace, and package import origins to regular clean-HEAD blobs. This is an
ordinary-Python import/file-byte claim; it does not attest a hostile interpreter
or in-memory code mutation.

## Mechanism and outcome reductions

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

No receipt in this directory authorizes a retry, a provider call, a new
outcome-bearing cohort, or locked-128 execution. Integrity `PASS` is
provenance, replay, coverage, and deterministic reduction closure only.
