# Diversity comparison: implementation review and completed qualification

This is an additive, not-yet-executed development plan after merged PR #29.
The operator reviewed the new API, runner, seed derivation, fixed recipe,
reduction, structural checks and regression tests. The earlier fresh-eye agent
review applied to PR #29 only; no independent reviewer of this new code is
claimed. All 451 files of merged base c0a59722f3d23d4703d0b834bfccc68da218d786
remain unchanged.

## Design checks

- All three arms use dense scale 16 and the same proposal, method and readout.
  Single16 receives the full cap; paired16 and diverse16 split every work axis.
- Domain-separated stream keys preserve the same primary branch across the
  paired/diverse comparison. Derived seed collision checks run before search
  and replay, and across the entire planned table before cohort generation.
- No cache, posterior, unused work or success signal is shared. Both branches
  execute even when the first succeeds. No runtime setting or old engine was
  modified to produce a desired result.
- The primary performance contrast is diverse16 versus single16. Nonloss
  versus duplicated paired16 is a subset guarantee, not evidence that splitting
  the budget beats continuation.
- Full-byte generative replay precedes all reductions. All fixed coordinates,
  prefixes, shared-primary identities, duplicate paired streams and subset
  success relations are checked, with postflight evidence rechecks.
- Diagnostics preserve missing terminals and include first-success work,
  action overlap, complementary successes and lost late full-budget successes.
  Single-arm overlap is null with a zero two-branch denominator.
- The previous eight source multisets are excluded using the authenticated
  cohort bytes. The new cohort is not generated during plan construction.

## Local checks before full qualification

Ruff passed. All 30 new scoped tests passed in 6.423 seconds, without skips.
They cover seed derivation/binding/collision, seven-axis allocation, exact
engine equivalence, charge-derived diagnostics, missingness, replay tampering,
closed input types, fixture-only lifecycle, fixed matrix/structural checks,
immutable evidence and rejection of retry/resume. Regression search uses
excluded all-ones fixtures, not the new cohort.

While adapting the successful-readout test, the old short-budget success
assumption no longer held under the new derived seed. A proposed two-input
fixture was rejected by the D6 adapter. The final test uses a larger cap on
the existing excluded six-input all-ones fixture; the actual study budgets,
seeds, method and generation recipe were not changed in response. These were
unit-test development failures, not failed or retried study attempts.

Full repository validation passed at candidate commit
`3082cffbd6ad7f7bde7af6a907b9c5597e7fa8ea`: 1,718 tests in 909.836 seconds,
OK, no skips, exit 0 and `repository validation: PASS`. The captured operation
ran from 2026-10-21T17:23:23.468932+00:00 to
2026-10-21T17:41:05.874715+00:00, with no postcondition errors.

The accompanying `countdown_feedback_diversity_development_20261022.validation.json`
receipt binds the actual logs, inputs, helper and plan. Read-only postflight
confirmed all 458 tracked Git bytes, 451 unchanged merged-base files, 3,752
protected files and their directory memberships, including the original 2,099
raw files and previous development's 517 output files. Original-study four
slots, E4 production two slots and the new experiment directory remain absent
at this qualification boundary. All 53 plan source references remain unchanged.
The raw review receipt and tracked receipt are byte-identical. This subsequent
records-only commit does not represent another full-suite execution or a new
independent reviewer.

## Execution approval boundary

Candidate plan digest:
`b9277ed5f4d537276dd612861bde6bb3bb322f53afae50b8456713839fefc4a4`.

32 source multisets × 8 root seeds × 2 budgets × 3 conditions = 1,536 cells,
2,560 branch runs and 768 prefix pairs; maximum 589,824 legal-action scores.
Plan generation is outcome-blind and no real study cells have run. Exact-plan
approval, full validation and unchanged source/runtime must precede execution.
Original C5, locked evaluation, providers, old E4 reruns, adaptive allocation
and any additional experiment remain outside this candidate's authority.
