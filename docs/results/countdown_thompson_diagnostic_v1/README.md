# Countdown Thompson diagnostic v1 post-hoc receipts

## Selection-margin sensitivity

`selection_margin_v1.json` is the canonical read-only selection-margin receipt.

- schema: `qmc-bmgs-countdown-thompson-selection-margin/v3`
- deterministic digest:
  `8efff0561f1ba65bc45580573ba422371bfaefe285269434ca785bebc83fc252`
- raw SHA-256:
  `8414267365ef8b172bb6ebef6a9886a60560058079ae93d16f3d0c6c3e67afc0`
- byte count: 2,003,163
- source revision: `a14f0ffeacf87a37bebc51633f9483b2b06c474b`
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
Schema v2 additionally bound the loaded audit, post-hoc, analyzer, publication,
trace, and package import origins to regular clean-HEAD blobs. A second fresh
rereview reproduced a timestamp-based `.pyc` substitution that retained the
clean `.py` origin. Schema v3 therefore requires audit mode to run with `-P -B`
and a dedicated empty mode-`0700` `-X pycache_prefix=...`; all eight project
modules must use the exact `SourceFileLoader`, have cache paths inside that
prefix, and have no cache file. The check runs before any frozen input path is
resolved.

The required interpreter envelope is:

```sh
cache_prefix="$(mktemp -d /tmp/qmc-bmgs-selection-margin-pycache.XXXXXX)"
PYTHONPATH="$PWD/src" python3 -P -B -X "pycache_prefix=$cache_prefix" \
  -m qmc_bmgs.experiments.countdown_thompson_selection_margin \
  <all frozen path and digest arguments>
rmdir "$cache_prefix"
```

This binds ordinary source-file imports, a statically present bytecode-cache
substitution, and clean-HEAD file bytes. It does not attest a hostile interpreter
or import hook, concurrent cache deletion before the first attestation,
in-memory code mutation, or kernel compromise.

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
