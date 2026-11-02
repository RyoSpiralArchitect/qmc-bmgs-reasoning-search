# Perturbing only unvisited root bonuses: ten additional solves, below the practical threshold

**Fixed study: 2026-10-30.** Evidence through the saved-event check completed 2026-11-02 at 16:28:15 UTC (2026-11-03, 01:28 JST). Local development evidence; no independent reviewer or hosted CI.

## Result on 512 fresh sources

The QMC arm solved **1,122/2,048** source–root rows (54.78515625%) and fixed PUCT solved **278/512** problems (54.296875%). Averaging the four QMC roots within each problem and subtracting that problem's one PUCT outcome gives **5/1,024 = +0.48828125 percentage points**. The prespecified approximate model interval is **[+0.0758118, +0.9007507] points**. Even its upper end is below the +2-point practical threshold: **NO_PRACTICAL_UPLIFT_SIGNAL**. A positive observed difference is not a claim of a practically useful gain, a zero effect or equivalence.

QMC gained ten source–root outcomes across seven problems and lost none here; the other 505 problems tied on all four comparisons. IID solved **1,120/2,048** (54.6875%). QMC's two-row net advantage over IID is descriptive, with an interval crossing zero. These data do not establish that Sobol draws, as opposed to perturbing an unvisited bonus, supplied the advantage. Neither a winner nor a scientific decision was assigned.

Public evidence: [frozen plan](../preregistrations/countdown_search_value_puct_qmc_unvisited_20261030.plan.json), [source-level outcomes](../results/puct_qmc_series/outcomes.csv), [local verification summary](../results/README.md#verification--検証).

## What changed and what did not

Candidate `fd7d6b29943fbfd8382e98ad5c5b41cc918c56b0`, plan digest `77e32d57733a8d573fbeb98d1b97245ff655c86fce5a1192551d4bb7b20d5871`. All arms retain the same ordinal-rank greedy-rollout-error heuristic prior (not an LM or calibrated error-gap weight), binary exact/miss returns, c=1 PUCT, arithmetic mean/visits/m2, DAG, proposals, canonical ties, stopping and budget rules. There is no learned value, semantic routing or pruning.

Let U(a) = p(a) × sqrt(1 + total visits) / (1 + edge visits). The entire first trajectory and all non-root selections use Q+U. On subsequent root selections only an edge with zero pre-selection visits uses Q+U×(0.5+its original uniform); a visited edge still uses Q+U. The action mask never scales Q or uses m2, normal variates, root-action rank or final outcome. Fixed non-root decisions are made on the arm's actual history, not a counterfactual PUCT history.

The mask changes scores, not point dimension: every active root consumes one point covering **all** canonical legal actions, including visited coordinates and unused normals. Even if all actions are visited, the full point is generated, stored and charged. Anchor and deep selections do not plan, generate, charge, consume or advance the stream. Actual committed root draws are contiguous from zero. The no-planning statement relies on frozen source and generative replay; saved traces alone verify observed material, charges and indices. Sobol uses `torch-sobol-full-sha256-cp-rotation-float51/v2`; IID uses `sha256-counter-open-unit-float51/v2`. Neither mechanism is Owen scrambling, Gumbel selection or Bayesian inference. Matched labels do not imply common draws or adaptive-QMC convergence.

This branch was motivated post hoc by the [preceding root-only study](countdown_puct_qmc_root_development_20261029.md): it had 22 gains/2 losses, and 5 of those 22 gains initially diverged toward a more-visited action. The present mask might lose gains as well as avoid losses. The old +0.9765625-point result and its no-practical-signal readout stand. The two cohorts are disjoint: comparing their gain/loss counts is not a paired estimate of changing the mask.

The first 512 eligible solvable unique source multisets used six inputs (1–10), target 100–999, generator 26103001 and at most 10,000 attempts. The plan excludes 2,523 prior task identities and 2,465 source identities, including all 512 preceding root-only sources. Roots 2097152–2097155 use the existing branch-0 derivation. Physical rows: 2,048 QMC + 2,048 IID + 512 fixed PUCT. Each has a 512 legal-action-score cap and six 100,000 guards. Four descriptive references to one PUCT row are **not** four independent controls.

## Comparisons and sensitivity

Gains/losses/ties count paired descriptions out of 2,048. The statistical unit is 512 sources, with sample variance denominator 511. Intervals are fixed mean ± 2 × source SD / sqrt(512), in percentage points, not guaranteed-coverage confidence intervals.

| Contrast | Gain / loss / tie | Mean (points) | Model interval (points) | Source signs + / − / tie |
|---|---|---|---|---|
| QMC − PUCT (primary) | 10 / 0 / 2,038 | +0.48828125 | +0.0758118 to +0.9007507 | 7 / 0 / 505 |
| QMC − IID | 10 / 8 / 2,030 | +0.09765625 | -0.3169793 to +0.5122918 | 5 / 4 / 503 |
| IID − PUCT | 10 / 2 / 2,036 | +0.390625 | -0.0451659 to +0.8264159 | 7 / 1 / 504 |

| Contrast | Exact mean | Exact source variance | Min-error better / tie / worse / missing | LOO source net (of 2,044) | LOO root nets (of 1,536) |
|---|---|---|---|---|---|
| QMC − PUCT (primary) | 5/1024 | 2279/1046528 | 21 / 2,027 / 0 / 0 | 7 to 10 | 6, 9, 9, 6 |
| QMC − IID | 1/1024 | 329/149504 | 19 / 2,016 / 13 / 0 | 0 to 4 | 0, 4, 5, -3 |
| IID − PUCT | 1/256 | 159/65408 | 17 / 2,029 / 2 / 0 | 6 to 10 | 6, 5, 4, 9 |

Primary interval in probability units: [0.0007581183422437996, 0.0090075066577562], half-width 0.0041246941577562. The plan first checks sufficient sources (n≥64) and nonzero variance, then half-width ≤0.05, then improvement relative to 0.02. The secondary readouts remain null; leave-one-out (LOO) changes the set of included observations and is sensitivity analysis, not another interval.

| Root | QMC / 512 | IID / 512 | QMC–PUCT gains/losses | QMC–IID gains/losses | IID–PUCT gains/losses |
|---|---|---|---|---|---|
| 2097152 | 282 | 280 | 4/0 | 3/1 | 2/0 |
| 2097153 | 279 | 281 | 1/0 | 1/3 | 4/1 |
| 2097154 | 279 | 282 | 1/0 | 1/4 | 4/0 |
| 2097155 | 282 | 277 | 4/0 | 5/0 | 0/1 |

## Anchors, complementarity and losses

All nine rows for each of the 512 sources share the same first-trajectory actions and terminal verification. For 203 sources that first terminal was exact (812 QMC rows, 812 IID rows and 203 fixed PUCT rows). Later exact hits added 310, 308 and 75 rows respectively, with the unequal physical denominators above.

| Candidate vs fixed PUCT | Both succeed | Candidate only | PUCT only | Neither | Sources with gain / loss |
|---|---|---|---|---|---|
| puct-qmc | 1,112 | 10 | 0 | 926 | 7 / 0 |
| puct-iid | 1,110 | 10 | 2 | 926 | 7 / 1 |

All ten QMC gains are listed below. “Hit” is cumulative legal-action scores at the first exact result; “censor” is stopping work without an exact result. A censor is not an imputed hit. No QMC loss was observed on this cohort; preserving all future PUCT successes is not a property of the algorithm.

| Source slot | Root | QMC hit | PUCT censor | PUCT minimum error |
|---|---|---|---|---|
| 140 | 2097155 | 456 | 492 | 1 |
| 154 | 2097152 | 468 | 509 | 1 |
| 154 | 2097153 | 468 | 509 | 1 |
| 154 | 2097154 | 468 | 509 | 1 |
| 222 | 2097152 | 509 | 512 | 1 |
| 330 | 2097155 | 431 | 505 | 3 |
| 441 | 2097152 | 407 | 504 | 2 |
| 486 | 2097155 | 511 | 510 | 1 |
| 510 | 2097152 | 468 | 512 | 2 |
| 510 | 2097155 | 468 | 512 | 2 |

Both IID losses are source 217, roots 2097153 and 2097155: PUCT hit at 338, IID stopped without a hit at 486 (minimum error 2). All IID gains and losses, both-success and neither-success rows, per-source/root metrics and all LOO rows are in the diagnostics. The four-root unions (285 QMC, 285 IID versus 278 PUCT) consume four caps per stochastic arm, not one. All-four-root success counts are 278 and 277.

## Did the mask act only where intended?

| Observed event or coordinate | QMC | IID |
|---|---|---|
| Active root selections / full points | 11,814 | 11,809 |
| Eligible unvisited coordinates | 281,158 | 281,197 |
| Stored and charged but unused visited coordinates | 16,306 | 16,253 |
| Selected an unvisited edge | 1,413 | 1,383 |
| Selected a visited edge | 10,401 | 10,426 |
| Fully visited root point (observed) | 0 | 0 |
| Fixed deep selections | 51,388 | 51,385 |
| Fixed deep selections after anchor | 43,196 | 43,193 |
| Deep same-history score flips | 0 | 0 |

The two coordinate classes sum to every charged coordinate in each arm. Fully visited roots occurred **zero** times in the scientific data; full generation/charging in that case was tested synthetically, not observed in a study row. Changing an unused visited uniform does not change its score but its stored digest still binds it. Reconstructing those bindings is distinct from regenerating the draws.

Of 2,048 QMC/IID pairs, 1,166 have identical complete action sequences; 882 first differ at the same root state, depth zero. No sequence ended early at the common prefix. The zero-based index of first divergence: 5: 312; 10: 444; 15: 37; 25: 13; 30: 41; 35: 25; 40: 9; 45: 1. The passive unperturbed choice differs from the recorded action in 866/65,250 QMC and 877/65,242 IID selections; before the first exact observation the counts are 861/39,278 and 874/39,297. These compare scores on a **single saved history**, not alternative rollouts. First-trajectory choices contain no random coordinates.

| Recorded concentration measure | QMC | IID | Fixed PUCT |
|---|---|---|---|
| Repeated-state selections / all selections | 45,674 / 65,250 | 45,732 / 65,242 | 11,537 / 16,306 |
| Distinct terminal action sequences, summed per cell | 6,044 | 6,043 | 1,479 |
| Repeated terminal observations | 6,495 | 6,490 | 1,653 |
| Distinct root choices per cell: min / median / max | 1 / 2 / 3 | 1 / 2 / 3 | 1 / 2 / 3 |

## First exact, missingness and censoring

| Arm | Success-only first-hit scores: min / median / max | No-hit censor scores: min / median / max | Missing terminal |
|---|---|---|---|
| puct-qmc | 48 / 89 / 511 (n=1,122) | 461 / 504 / 512 (n=926) | 0 |
| puct-iid | 48 / 89 / 509 (n=1,120) | 461 / 504 / 512 (n=928) | 0 |
| puct | 48 / 89 / 489 (n=278) | 461 / 504 / 512 (n=234) | 0 |

All 4,608 cells have a terminal record and all stopped on a blocked primary-budget transaction. No-hit is distinct from missing terminal evidence. The equal success-only medians (89) do not establish equal speed: the successful sets differ. Among both-success references, QMC was earlier/equal/later in 62/978/72 (difference min/median/max −117/0/+185 scores); IID in 56/985/69 (−141/0/+192). These are conditional descriptions.

## All charged work, and what is outside that ledger

| Axis | QMC actual | IID actual | PUCT actual | QMC unspent | IID unspent | PUCT unspent |
|---|---|---|---|---|---|---|
| edge_selections | 65,250 | 65,242 | 16,306 | 204,734,750 | 204,734,758 | 51,183,694 |
| generated_perturbation_coordinates | 297,464 | 297,450 | 0 | 204,502,536 | 204,502,550 | 51,200,000 |
| legal_action_scores | 1,027,022 | 1,027,209 | 256,791 | 21,554 | 21,367 | 5,353 |
| proposal_action_scores | 269,389 | 268,423 | 65,945 | 204,530,611 | 204,531,577 | 51,134,055 |
| proposal_state_evaluations | 19,576 | 19,510 | 4,769 | 204,780,424 | 204,780,490 | 51,195,231 |
| transitions | 65,250 | 65,242 | 16,306 | 204,734,750 | 204,734,758 | 51,183,694 |
| verifier_calls | 12,539 | 12,533 | 3,132 | 204,787,461 | 204,787,467 | 51,196,868 |

Primary actual **2,311,022** of 2,359,296, leaving **48,274**. Unspent guard capacity is not savings in wall time. The normal variates and unused visited-action coordinates remain part of the material cost; coordinate dimensions are charged once, not separately per uniform and per normal.

| Proposal counter | QMC | IID | PUCT |
|---|---|---|---|
| materialized_rows | 19,576 | 19,510 | 4,769 |
| root_action_evaluations | 269,389 | 268,423 | 65,945 |
| completion_legal_action_evaluations | 6,374,425 | 6,353,831 | 1,571,858 |
| internal_transition_evaluations | 914,128 | 910,836 | 224,319 |

Root-action evaluations already correspond to proposal action scores, not an eighth charge. Completion-action enumeration is carried from the previously regenerated raw rows, not independently re-enumerated by the saved-event checker. Other proposal-internal work is not charged to the seven-axis ledger; equal primary caps are not equal total compute.


## Verification and scope of this public edition

The [saved-event checker source](countdown_puct_qmc_unvisited_development_20261030.py) is public. A separate process reproduced all 4,608 cells byte for byte. The saved-event checker then agreed on the source reductions, 2,048 QMC/IID pairs and all 512 initial trajectories. The local result package passed 2,055 tests, with no skips. Its first synthetic checker suite had 57 passes and one failure (a shared test input). The failed case alone passed a targeted retest after isolating that input; the checker itself did not change. The frozen policy’s trailing-blank-line warning was retained. These are local checks, not independent review or external replication.

This public edition contains the scientific observations, not operational receipts or per-action traces. The frozen development rule names no winner. A fixed cap on legal-action evaluations is not an equal-total-compute claim, and comparisons across the three disjoint cohorts do not identify the effect of switching policies.
