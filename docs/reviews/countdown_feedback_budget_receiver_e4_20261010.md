# E4 reconstruction: bounded local adversarial review — 2026-10-10

Scope: the three-file additive source closure at c19db4a7994eeb5f33c610cdee3ebc0c72e2a004. This is the implementing agent's bounded local review, not a fresh-agent review, external review, CI, or numerical evidence. The older 367 tracked files were preserved byte-for-byte including full POSIX modes.

Reviewed the staged implementation and its frozen lower call paths: direct owned metadata correspondence, exact pinned-before-parse observations, whole fresh environment/PUBLIC projections, original generation reference, read-only cohort capture, genuine M._cohort and full rejection/acceptance/seal/input comparisons, final state checks and whole-result fresh-process comparison.

Resolved items before source freeze:

- Test fixture used informal E0/E1 labels instead of retained original_v7/receiver_20260921 registry labels. Corrected the fixture; registry and historical source were not changed.
- Inode mutation can be rejected earlier by the within-epoch shared-prefix check. Accepted both precise rejection paths in that negative test, without weakening production checks.
- Fixture used a nonexistent keyword for the frozen ExecutionFailure constructor. Corrected to its actual positional signature.
- Retain completed 32-trace baseline work immediately after genuine R.environment returns, even if a later whole historical environment comparison rejects. Added a regression test, plus final-revalidation and fresh-verification drift accounting tests.
- During initial code inspection, aligned generated cohort accounting with the frozen manifest's actual accepted_count and attempt_count keys, before the first fixture run.

First focused run: 42 tests, two failures and one error, all from the three fixture issues above. Preserved complete test output separately. Intermediate 42-test rerun passed. Final focused run: 46 tests in 19.126s, all passed. Fixtures and mocked wiring do not demonstrate actual numerical replay.

Adversarial boundaries exercised: recurring device identifier without epoch collapse; every owner/path/device/inode/role closure; pinned provenance before parse; no old admission/publication or sealed-loader call; source closure/callable/HEAD drift; original v7 generation reference not replaceable by v2; complete task order and rejection log changes; complete seal transaction and input projection changes; unknown partial counts; retained completed work after errors; no in-operation retry; saved verification must dispatch full reconstruction and compare even an otherwise unselected output field.

Independent verification means a separate fresh process using the same frozen implementation and a new empty private cache. It is not algorithmic implementation independence. No hash receipt, fixture, historical coordinator qualification or same-device coincidence qualifies current execution. Snapshot and callable checks are not a hostile-interpreter sandbox or an atomic concurrent-mutation lock.

Remaining gates after numerical success: reviewed certificate design/publication, separately approved fixed new PUBLIC coordinator exercise and independent saved-summary verification, candidate review and exact-new-digest production consent. No certificate, candidate, new PUBLIC attempt, study claim, production cell or locked-128 execution is created here.

## Actual execution and preservation follow-through

Full validation at the frozen source passed 1484 tests in 848.033s, zero skips,
plus compile/lint/artifact/provenance/CLI checks and final repository PASS.
Two separately launched fresh processes genuinely completed the ordered numerical
path; the second matched all 215556 bytes of the first observation.
Per pass: 32 baseline traces, 2048 retained PUBLIC replays, 1024 exact prefixes,
and the original 102-attempt / 64-accepted / 38-rejected cohort reconstruction.
Entire historical receipts, summaries, original cohort and three-file seal and
full input projection matched. This is not a mock-based completion claim.

Reconstruction observation digest:
`d546836a203b3c947dfaa903a49b26b815b07b50a8eebb56f4783c9db855280b`.
Fresh-process verification digest:
`0b0c41275034b94d763b29c58d1d020defacc054036e8e0429444b6f9514d73f`.
Operations digest:
`d653610ea2fc852c89303effb4f2e9d94c796c417bc720e53c84902345d679a8`.

The postflight check preserved all 367 old tracked files (79749024 bytes) and
full modes, both PUBLIC inventories (2054 files / 272846815 bytes combined), original seal,
three old ledger records and four absent study/preflight slots. It also checked
unchanged source bytes and current location chains.

The result's "ORIGINAL_STUDY_FULLY_RECONSTRUCTED" label describes original inputs
and retained PUBLIC evidence only; original replication-policy outcomes remain
unexecuted. Historical negative PUBLIC screens are preserved. No current
admission, certificate, candidate or production authority follows from this label.
