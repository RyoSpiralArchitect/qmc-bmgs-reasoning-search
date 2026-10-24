# Search-value design review, 2026-10-24

Scope: review of a **design proposal**, not an implementation qualification,
new experiment, external approval or authorization. The implementing agent
performed this review; it is not a second fresh reviewer or a human review.

## Findings addressed in the design

| Risk from the global review | Design response | Remaining limit |
| --- | --- | --- |
| Only comparing allocation variants inside one kernel | Current single16 versus fixed PUCT primary; greedy and beam retained | Winning against PUCT would not mean best among all methods |
| Conflating scale0 with no learning | Mean-off removes only selection use of the mean; all update rules remain | Visit-dependent state/noise remains adaptive; this is not all-learning-off |
| Mistaking a method comparison for a one-factor causal effect | PUCT binary feedback and single16 dense feedback are explicit | Primary cannot attribute a gain to Thompson, dense feedback or uncertainty alone |
| Reusing favorable outcomes to choose a cohort or comparator | New128 sources, fixed four roots, identity exclusions and fixed PUCT primary | Generator assumptions do not establish population independence/coverage |
| Copying deterministic rows across seeds | Each deterministic method has one row per source | Its outcome is referenced in nested pair descriptions, not replicated evidence |
| Calling a small difference proof of useless learning | Exact source moments, interval/precision limits, unresolved status | Mean-off comparisons remain diagnostic and cannot replace the primary |
| Treating score caps as total compute | All seven axes, unused caps and proposal-internal work reported separately | No equal-total-cost or speed claim; a later systems gate is still required |
| New qualification ceremony substituting for algorithmic progress | One bounded 1,408-cell question with a single primary | Actual method implementation and qualified execution still require separate work |

## Arithmetic and planned boundaries

`128 × (2 stochastic methods × 4 roots + 3 deterministic methods) = 1,408`.
At a maximum512 legal-action scores per cell, combined primary work is720,896.
The inference unit is128 source means, not the512 stochastic rows,1,408 cells,
or a pooled set of method outcomes. Prior sources and reserved identities are
excluded; no C5/locked outcome is opened to choose the new cohort.

The design companion explicitly sets implementation, data generation and
execution authorization to false, with no candidate/runtime/executable-plan
digest. It is intentionally not accepted by an experiment runner as a plan.
It fixes prospective choices for review, not a generated cohort or run receipt.

Zero variance is not zero uncertainty. Precision failure is not a negative
scientific finding. A non-primary guard failure or incomplete matrix is not a
license to analyze only successful rows. Model intervals, leave-one-out
sensitivity and saved-history choice diagnostics have separate meanings.

## Implementation review items, still open

- Add a separately versioned mean-off selector/trace contract; preserve old
  method bytes and semantics. Prove the intervention with synthetic fixtures.
- Specify passive proposal-internal counters without mislabeling them as a
  complete runtime cost model or changing old ledger semantics.
- Materialize authenticated exclusions, seed table and full identities only in
  a later qualified candidate. Any collision or inability to accept128 sources
  blocks that candidate; no silent substitution or resampling.
- Freeze analysis outputs, null handling, attempt identities and failure rules.
- Qualify the actual candidate and seek exact-candidate execution authority.

These are gates for later work, not missing implementation claimed complete by
this PR. There is no current candidate success/failure result.

## Document checks

The proposal is cross-checked against the current selection/backup code, the
[Track A contract](../countdown_track_a_search_contract.md), and the
[allocation statistical rules](../strategy/countdown_feedback_allocation_development_20261023.md).
The documents deliberately do not alter frozen sources, receipts or statistical
functions from any previous attempt. Local link/arithmetic/schema checks and
the exact combined-tree full-suite status are reported in the PRs and retained
validation logs; this design text does not predeclare them PASS.
