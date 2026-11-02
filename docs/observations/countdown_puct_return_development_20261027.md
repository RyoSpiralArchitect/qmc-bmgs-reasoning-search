# Fixed-PUCT terminal return development: 2026-10-27

## Readout and claim ceiling

The one registered dense16-return candidate did not improve exact-solution
discovery over unchanged binary-return PUCT on this development cohort.
The sole primary, source-paired dense16 minus binary success, is
**-82/512 = -0.16015625** (-16.015625 percentage points).
The unchanged precision-first rule returns **NO_PRACTICAL_UPLIFT_SIGNAL**.
No winner, default promotion, population causal conclusion, general rejection
of learning, or QMC/transfer result follows.

| Physical deterministic arm | Exact successes | Denominator | Rate |
| --- | ---: | ---: | ---: |
| puct-dense16 | 205 | 512 source runs | 40.0390625% |
| puct, unchanged binary return | 287 | 512 source runs | 56.0546875% |

There are 512 paired source clusters and 1,024 physical cells, not 1,024
independent source observations. Root0 is an identity, not a random repetition.
Gain0/loss82/tie430; both succeed205, binary-only82, dense-only0, neither225.
Minimum terminal error is better for dense on0 sources, equal352, worse160;
missing0. Of the160 losses on minimum error,82 are binary-only successes and78
occur among the225 pairs where neither succeeds. All outcomes are retained.

Exact source moments: mean=-41/256, sample variance=8815/65408 (denominator511).
The registered approximate model interval is
[-0.19260445959554562, -0.12770804040445438], half-width0.032448209595545605.
Half-width<=0.05, then upper<=+0.02: the original decision order is satisfied.
This is not a coverage guarantee. Deterministic solvability filtering,
nonreplacement and identity uniqueness do not establish independence or
population representativeness. Leave-one-source-out net is -82..-81 over511;
this sensitivity check is not another confidence interval. Root omission is
inapplicable; there are no stochastic roots or secondary experimental arms.

## Fixed question and design

Candidate369221b73d91099a21c6ba67e6f2ede2b0857e26 and
[plan](../preregistrations/countdown_search_value_puct_return_20261027.plan.json),
digest722dcf39711678e7c14dc06d1bcf024e8999c4b26f494fb6c20b0e025e1791df,
were fixed before generation. The base is PR37's merge0b0381b; all549 old tracked
files remained byte-identical and only8 candidate files were added.

Both arms use the same deterministic c1 PUCT selector,
Q + p*sqrt(1+sum(visits))/(1+edge_visits), including binary64 operation order,
heuristic greedy-rollout prior, proposal, canonical ties, visits, arithmetic
mean/m2, DAG sharing and full-budget stopping. This is not an LM prior.
Only the scalar terminal backup changes: dense16 uses16/(16+absolute error),
control exact1/otherwise0. Original binary engine bytes are untouched.
There is no RNG, root noise, extra mean-off arm, coefficient sweep, alternative
prior or redistribution. The scale16 value predates this cohort.

Generator26102701 admitted the first512 eligible unique solvable sources
(six inputs1..10, target100..999, max10,000 attempts), excluding987 task and929
source identities and the fixed tracked-Python fixture superset. The plan seals
62 source refs and180 fixture-source refs. Static literal extraction is not
proof of discovering arbitrary dynamic fixtures. Arm order alternates by source.
All cells have legal_action_scores cap512 and six separate guards100,000.
Equal main-axis caps are not equal total computation.

The previously completed candidate qualification ran1,896 tests in997.043s,
OK/skip0, exit0/PASS, 2026-10-26T23:56:16.155010Z to
2026-10-27T00:15:56.536163Z. It qualifies the candidate, not this later result
package. Candidate-time pending/authorization-false records remain snapshots.

## Discovery, censoring and revisitation

Both methods have205 exact first terminal observations. All205 dense successes
are these first-terminal successes; dense finds no additional exact solutions
after an initially non-exact terminal. Binary PUCT finds82 additional successes.
On the205 common successful sources, first-hit main-axis work is identical:
min49/median89/max132. Among the82 binary-only successes it is
min142/median282/max480.

The arm-wide success-only medians are89 (dense, n205) and98 (binary, n287).
They condition on different successful sets and **do not show that dense is
faster overall**. No-hit records are right-censored at actual consumed work,
not assigned a zero first-hit cost. Dense has307 censored sources with
min472/median504/max512 scores; binary has225 with min469/median502/max512.
Missing terminal observations are0 in both arms. Every cell ends at
primary_budget_blocked; no non-primary guard binds.

| Saved-event diagnostic, summed over512 cells per arm | dense16 | binary |
| --- | ---: | ---: |
| selections | 14,820 | 14,711 |
| repeated states in ordinary selection events | 12,256 | 10,047 |
| terminal verifications | 2,840 | 2,829 |
| exact terminal observations, including repeats | 1,107 | 1,379 |
| unique complete action sequences, counted within each cell then summed | 513 | 1,365 |
| repeated terminal observations within cells | 2,327 | 1,464 |
| non-exact positive backups | 1,733 | 0 |
| cells with only one unique terminal action sequence | 511 | 205 |
| unique root actions per cell, min/median/max | 1/1/2 | 1/2/3 |

Dense source179 is the sole cell with two unique terminal action sequences and
two selected root actions; all other dense cells have one of each.
Binary unique-terminal-sequence histogram is1:205,2:60,3:53,4:103,5:82,6:5,7:3,8:1.
Counts are not global unique solutions: the same sequence in distinct sources
is counted separately. Maximum within-cell terminal multiplicity is14 dense
and10 binary. Revisit means repeated states in ordinary selection_committed,
not an alternative state-space coverage estimator.

All512 first trajectories match between arms. All205 fully matching action
sequences correspond to their common successes. The remaining307 pairs first
diverge at selection index10 (zero-based), and all divergences are at the same
state. Neither sequence merely ends at the common prefix. The saved pair
records retain the Q values, prior probabilities, visits, exploration bonuses,
scores and selected actions on both actual histories.

On the actual dense histories, passive removal of Q changes9,693/14,820
choices;5,996/10,098 pre-first-exact choices change. Binary has
4,403/14,711 such changes overall, but0/8,947 before the first exact observation.
The latter follows the frozen source property: zero-initialized binary means
stay zero before exact success, although visits and the prior still guide
exploration. It does not imply post-success equivalence or failure of learning
in other targets. No counterfactual rollouts were run.

Dense selects a non-max-prior action2/14,820 times, versus1,387/14,711 for binary.
The selected Q exceeds its exploration bonus12,235/14,820 dense choices and
5,741/14,711 binary choices. These are same-history descriptive decompositions,
not independent interventions on Q, visits or prior. Together with the repeated
terminal counts, they are consistent with positive near-miss returns favoring
already visited branches in this configuration; they do not identify a universal
mechanism or justify tuning the registered result away.

An open research question is whether strictly positive near-miss targets,
relative to unseen edges initialized at zero, create avoidable concentration.
A separately justified return-centering or initialization intervention could
test that hypothesis. No next candidate, coefficient, experiment or default
has been selected or authorized here. The next step remains research design,
not more budget bookkeeping or a sweep of the current cohort.

## All seven work axes

| Axis | dense16 actual / unspent | binary actual / unspent |
| --- | ---: | ---: |
| legal_action_scores | 256,244 / 5,900 | 255,817 / 6,327 |
| edge_selections | 14,820 / 51,185,180 | 14,711 / 51,185,289 |
| transitions | 14,820 / 51,185,180 | 14,711 / 51,185,289 |
| verifier_calls | 2,840 / 51,197,160 | 2,829 / 51,197,171 |
| proposal_action_scores | 45,178 / 51,154,822 | 70,156 / 51,129,844 |
| proposal_state_evaluations | 2,564 / 51,197,436 | 4,664 / 51,195,336 |
| generated_perturbation_coordinates | 0 / 51,200,000 | 0 / 51,200,000 |

Total primary use512,061 of524,288, unspent12,227. Unspent guards are separate
axis capacities, not convertible compute or performance bonuses.
Proposal-internal transition evaluations are171,839 dense and243,969 binary;
completion legal-action enumerations1,439,251 and1,815,409. Equal charged
legal-score caps therefore do not mean equal proposal work, wall time or memory.
Historical PR36/37 cohorts differ; their success rates cannot identify paired
improvement over the current candidate.

## Execution, replay, separate check and retained failure

Ryō's exact-candidate response「うん、進めよう~!」to the fixed commit/digest,
512x2 matrix and one-run/one-analysis scope authorizes the experiment.
This is distinct from implementation permission and monitoring consent.
[Approval](../qualifications/countdown_puct_return_development_20261027.approval.json)
contains that question/answer and closed scope, not a new source of authority.

- Run: 2026-10-27T02:47:14.189849Z–02:51:40.070848Z, exit0/postflight true,
  errors empty, before=after, all1,024 cells/512 sources/1,027 initial files.
- Separate analysis:03:06:17.790479Z–03:11:04.291672Z, exit0/postflight true,
  cohort regenerated and all1,024 cells generatively byte-identical;512 pairs,
  512 source clusters,0 cross-budget prefix pairs;1,027 inputs unchanged,
  1,030 final output files. Native peak RSS397,836,288 bytes; outer detail cache2
  is not a total-memory bound.
- Initial additional checker:03:26:55.372602Z–03:26:59.990948Z, exit1.
  Its incorrect assumption required16/16 even for an exact terminal; the frozen
  engine correctly stores1/1 with scale16. The first conflicting saved evidence
  is cell3, source1/dense16/root0, event11. Numerical reward is1 either way.
  Twelve synthetic tests omitted this dense exact-hit representation.
  [Failure receipt](../qualifications/countdown_puct_return_development_20261027.checker-failure.json)
  and unchanged failed source/process/logs are retained, not recast as success.
- Ryō answered「うんうん！やろ１」to repairing only the checker and one separately
  captured saved-event check, then documentation/result qualification/PR38.
  [Repair authority](../qualifications/countdown_puct_return_development_20261027.checker-approval.json)
  excludes experiment or generative-analysis reruns. The source change handles
  exact1/1 and preserves non-exact16/(16+error);18 synthetic tests/skip0 and Ruff
  pass, including wrong-but-equivalent exact encodings and malformed evidence.
- Repaired check:03:49:09.456622Z–03:49:17.840421Z, exit0/postflight true,
  errors/stderr empty,17,085 preserved file refs unchanged. It independently
  reconstructs all terminal arithmetic, error/hit/censor reductions, PUCT
  scores and mean/m2 updates, all7 charged axes, method/source aggregates,
  rational moments,512 leave-one-source-out checks and512 pair diagnostics.
  All match the saved analysis. It imports neither engine nor reducer.
  It is an independent implementation, not an independent reviewer, new
  experiment, generative replay or counterfactual rollout.
  Proposal completion action enumeration alone is carried from authenticated
  replayed raw, not independently re-enumerated by this checker.

The failure evidence audit initially assumed scalar before_digest keys for
the run/analysis receipts; those receipts use before/after objects. The failed
read-only audit source/stderr and the corrected inspection receipt are retained.
That inspection correction did not run the experiment, analysis or checker.

### Known status-label defect

The immutable runner/summary still says
ALL_CELLS_REPLAYED_PRIOR_TILT_ANALYSIS_COMPLETE. This copy-over label was
disclosed before execution and was not silently fixed or normalized.
Identity instead binds the current candidate/plan/COMMIT, outer schema
countdown_puct_return_cell/v1, reduction puct_return_source_reduction/v1,
two deterministic methods,512 sources and1,024 cells. The processing functions
are PUCT-return replay/reduction, not the historical prior-tilt experiment.
A later label fix would be separate implementation work; it is not done here.

## Saved evidence and package status

[Summary](../qualifications/countdown_puct_return_development_20261027.summary.json),
[diagnostics](../qualifications/countdown_puct_return_development_20261027.diagnostics.json),
[COMMIT](../qualifications/countdown_puct_return_development_20261027.commit.json),
[cohort](../qualifications/countdown_puct_return_development_20261027.cohort.json),
[candidate qualification](../qualifications/countdown_puct_return_development_20261027.validation.json)
and [operations](../qualifications/countdown_puct_return_development_20261027.execution.json)
are initial same-byte mirrors of local raw records, not regenerated summaries.
The [result review](../reviews/countdown_puct_return_development_result_20261027.md)
owns the result-package qualification state and later completion receipt.
The candidate's earlier PASS is not the later package's PASS.

COMMIT SHA256:aea0fd597fa7f68bfe86d683b7aec829fe6b4f7c5a184b0749fe90e4b91042b4,
digestf46ad13a00d7dfbe3a1c9dbfba66a00ab627ea56abe24d5318084a6ea1f62d38.
Summary SHA256:1241dc1e6a320bebc54c1127b20be5b0e887fdef2ed60cf832542842f15de5c4,
digesteaf7e514aa05f8ec3be2b03dd59c9c14d54429e3426113c79e3ef3030313c0bf.
Repaired diagnostics SHA256:57e2e9b9d034ce025faca24dbb1e0f99b54516e6ebaf7ec1ec091036620cdd48,
digest3e5dfbc93f14f0d34a420092771427c60479aaf5f96e8e73dcad436760807c42.

All557 candidate tracked files, original549 files, historical negative results,
failures and UNKNOWN causes remain unchanged. No provider/C5/locked evaluation,
additional conditions, automatic retry, default promotion, QMC/transfer or merge
was performed. Validation guidance preserved units, missingness, exact
recomputation, negative evidence and claim ceilings without changing the
registered primary or decision rule.
