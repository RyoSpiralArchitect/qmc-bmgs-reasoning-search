# Countdown v6: feedback × budget development observation

Date: 2026-09-10. One authorized fixed-cohort experiment; local result, not an external release.

Specification: [frozen v6 design](../strategy/countdown_thompson_feedback_budget_factorial_v6.md),
[sealed cohort and exact candidate](../countdown_feedback_budget_sealed_cohort_v6.md).

## Bottom line

固定した開発screenは **DEVELOPMENT_SIGNAL_FOR_SEPARATE_CONFIRMATION_DESIGN**。
予算を256から512へ増やしたとき、scale 16のscale 0に対するexact-successの
上積みは `0 → 2/48` となった。差の差は `2/48 = 1/24`
（約4.17 percentage points、表示だけ丸めた値）。

これは、独立した確認試験の**設計を提案できる、小さな開発signal**である。
効果と広がりはいずれも事前に固定した最低基準ちょうど：
追加正解2 task/seed pairs、2 task clusters。確認、因果的媒介、母集団性能、
一般的な知能向上、QMCの優位性、locked-128の実行許可は意味しない。

12問 × 4 seed × 2 scale × 2 budget = 192 cells。
推論上のtask clustersは12であり、48 blocksや192 cellsを独立した問題数にしない。
cohortは凍結した可解性フィルタ・重複除外を条件とする12問で、
無条件のCountdown母集団からの標本ではない。

両条件は同じIID Thompson探索（v5）、同じheuristic proposal、同じseed構造を使う。
変更因子はfeedback scale 0/16とlegal-action score上限256/512だけで、
他6軸のguardは共通。上限を対応させた比較であり、受理された仕事量や実時間が
毎セル厳密に同じという主張ではない。今回の実験にはSobolもprovider呼出しもない。

## Integrity, authorization and verification

- Exact reviewed/execution commit: `a91e34f4916f5ade43f85e40906859bd6e653eca`.
- Qualified producing connector source: `47cb90880b1e437095d3668ac887165d9bc55c03`.
  Computation, admission, source/runtime contracts and the frozen design were unchanged.
- Exact candidate digest:
  `0c35ff3e916142b8d122c68b9229d8e35ecf542e06f281bac9c82e38fc88e3e8`.
  Candidate JSON flags remained false; separate explicit user authorization covered
  one complete run and independent analysis/verification, not retries or locked-128.
- [Fresh candidate review](../reviews/countdown_feedback_budget_candidate_20260910.md):
  no actionable P1/P2 in its bounded scope; hidden project files restored before execution.
- Single producer invocation: exit 0; 192 cells, exact 195-file closure,
  31,899,843 bytes. The fixed study claim is consumed and retained.
- Independent analyzer: separate fresh-cache process, exit 0.
- Saved-summary verification: third separate fresh-cache process, exit 0;
  canonical bytes/SHA-256 identical to the independent analyzer's saved summary.
- All 192 traces replayed byte-identically; all 96 full accepted-event budget prefixes,
  sole-primary-budget and completion checks passed. Provider calls: 0.
- Separate readonly arithmetic/hash audit reconstructed arm counts, all 48 success
  patterns, task rows and leave-one-task-out fractions directly from the saved terminal
  success flags; all agreed with the independently analyzed summary. No search/replay
  was performed by that extra audit. Its view was smoke-tested on the older PUBLIC fixture.
- Complete `python3 -B scripts/validate.py` surface: PASS in the restored,
  byte-identical complete clone at the same reviewed commit/tree
  (`abb5f5a7f1c0864e127ed70eaeeb91bc9be72e5d`):
  1,016 tests, no skips, unit-suite time 677.720 s, plus compilation, Ruff,
  artifact/ancestry/design checks, outside-checkout CLIs and historical v5 seal verification.
  This is local validation, not hosted CI or a substitute for the original raw-run analysis.

Validation replays verify the same fixed cells; they do not add independent experimental
conditions. Wall-clock operation logs include admission, old PUBLIC reanalysis, fixed
seal reconstruction, replay and durable IO—not just search time.

## Four arms and exact estimand

Every arm has 48 task/seed observations; percentages below are display-only rounding.

| Legal-action budget | Scale 0 exact success | Scale 16 exact success | Paired new / lost / net | Uplift |
| ---: | ---: | ---: | ---: | ---: |
| 256 | 0/48 (0%) | 0/48 (0%) | 0 / 0 / 0 | 0 |
| 512 | 3/48 (6.25%) | 5/48 (10.42%) | 2 / 0 / 2 | 2/48 = 1/24 |

`I = (5 - 3 - 0 + 0)/48 = 1/24`.
Both methods benefited from extra budget; the fixed-cohort difference in that benefit
was two additional scale-16 successes. It was not low-budget harm disappearing.

The two paired rescues are task slots 3 and 10. This does **not** mean two extra
previously unsolved task identities: at high budget, any-seed solved tasks are 2/12
for scale 0 and 3/12 for scale 16, because task 10 already has a baseline success
at another seed. Multiple exact terminals inside one cell count as one cell success.

### All task rows

Arm order: `Y0_256, Y16_256, Y0_512, Y16_512`.
Counts use four seeds per task; task-level fractions use denominator 4 before reduction.

| Task slot | Y0,256 | Y16,256 | Y0,512 | Y16,512 | Low uplift | High uplift | Interaction |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 3 | 0 | 0 | 0 | 1 | 0 | 1/4 | 1/4 |
| 4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 6 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 7 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 8 | 0 | 0 | 2 | 2 | 0 | 0 | 0 |
| 9 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 10 | 0 | 0 | 1 | 2 | 0 | 1/4 | 1/4 |
| 11 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

### All leave-one-task-out contrasts

These are fixed sensitivity summaries, not confidence intervals or resampling inference.
All have 44 remaining task/seed blocks. Omitting either rescue task leaves only
`1/44`; omitting another task leaves `2/44 = 1/22`.

| Omitted task | Blocks | High uplift | Interaction |
| ---: | ---: | ---: | ---: |
| 0 | 44 | 1/22 | 1/22 |
| 1 | 44 | 1/22 | 1/22 |
| 2 | 44 | 1/22 | 1/22 |
| 3 | 44 | 1/44 | 1/44 |
| 4 | 44 | 1/22 | 1/22 |
| 5 | 44 | 1/22 | 1/22 |
| 6 | 44 | 1/22 | 1/22 |
| 7 | 44 | 1/22 | 1/22 |
| 8 | 44 | 1/22 | 1/22 |
| 9 | 44 | 1/22 | 1/22 |
| 10 | 44 | 1/44 | 1/44 |
| 11 | 44 | 1/22 | 1/22 |

### All 16 patterns, including forbidden zeros

Bit order: `(Y0,256, Y16,256, Y0,512, Y16,512)`.

| Pattern | Count / 48 | Forbidden by prefix |
| --- | ---: | --- |
| 0000 | 43 | no |
| 0001 | 2 | no |
| 0010 | 0 | no |
| 0011 | 3 | no |
| 0100 | 0 | yes |
| 0101 | 0 | no |
| 0110 | 0 | yes |
| 0111 | 0 | no |
| 1000 | 0 | yes |
| 1001 | 0 | yes |
| 1010 | 0 | no |
| 1011 | 0 | no |
| 1100 | 0 | yes |
| 1101 | 0 | yes |
| 1110 | 0 | yes |
| 1111 | 0 | no |

## Mechanism and observed conversion

The unchanged analyzer froze outcome-redacted common-prefix mechanism rows before
terminal-error and exact-success reduction. The following are descriptive counts,
not causal mediator estimates. All comparisons retain the 48-block denominator.

“Different backup” means a scale-dependent applied backup on the observable common
prefix; it is distinct from a feedback-supported action divergence. Completion counts
refer to scale 16 after the first differing selection. Prefix improvement compares
its suffix to its own shared-prefix best error—not to scale 0.

| Budget | Different backup / 48 | First divergence / 48 | At least one post-divergence terminal / 48 | Shared-prefix best-error improvement / 48 | Divergent suffixes 0 / 1 / 2+ terminals |
| ---: | ---: | ---: | ---: | ---: | --- |
| 256 | 48 | 16 | 8 | 0 | 8 / 6 / 2 |
| 512 | 48 | 35 | 32 | 12 | 3 / 5 / 27 |

At B=512 the 35 divergent pairs split into 16 already divergent at B=256 and
19 newly divergent at high budget; 13/48 never diverged. Do not pool these
strata into an inferred mediation rate.

- All eight low-budget unfinished divergent trajectories completed in their
  observed high-budget continuation, separately on both scales.
- Additional completed terminals after the low-budget prefix: 141 for scale 0,
  144 for scale 16 across the 48 matched budget pairs per scale.
  These are terminal completions, not necessarily distinct witnesses or successes.
- Both high-budget paired rescues came from the 16 already-divergent-low blocks.
  The 19 newly-divergent-high blocks produced no paired exact rescue in this cohort.
- High-budget prefix improvements were 12, but high-budget wins against scale 0
  on minimum error were seven. These are different comparisons.

### The two rescues have different windows

Trajectory indices below are zero-based. They are selected-case descriptions,
not an estimate over successful-only cases.

| Task / seed | First divergence | Low-budget scaled suffix terminals | First high-budget exact trajectory | Minimum errors in arm order |
| --- | --- | ---: | ---: | --- |
| Slot 3, seed 8193; `[1,6,6,8,9,10] → 526` | trajectory 2 / depth 0; `8*10 → 9*10` | 0 | 2 | `[15,15,15,0]` |
| Slot 10, seed 8192; `[2,3,3,4,4,5] → 722` | trajectory 1 / depth 1; `3*4 → 4*20` | 2 | 3 | `[4,4,4,0]` |

Slot 3: low-budget traces ended with terminal errors `[428,15]` on both scales.
The diverged trajectory itself was unfinished. At high budget, scale 16 continued
to `[428,15,0,0,0]`; scale 0 to `[428,15,401,427,22]`.
The first exact hit is the formerly unfinished trajectory 2.

Slot 10: low-budget errors were `[4,239,232]` versus `[4,4,233]`.
The divergent trajectory had already completed; neither method found exact success.
High budget extended these to `[4,239,232,118,62,717]` versus
`[4,4,233,0,0,239]`. The first scaled exact hit is the later trajectory 3.

Thus one observed rescue is an unfinished divergence completing, while the other
requires further continuation after already-completed divergence. The matched
budget prefixes make these actual continuations, but do not by themselves identify
which downstream update causally mediated success.

## Terminal error: retain the adverse cases

Comparison is scale 16 versus scale 0 on minimum verified terminal absolute error,
over all 48 pairs at each budget. A win means a smaller error.

| Budget | Wins | Ties | Losses |
| ---: | ---: | ---: | ---: |
| 256 | 0 | 47 | 1 |
| 512 | 7 | 39 | 2 |

Ordinal error interaction: `((7-2)-(0-1))/48 = 6/48 = 1/8`.
This is an ordinal contrast, not a percent reduction in mean error.
No lost exact successes does **not** imply absence of nonexact-error harm:
the two high-budget error losses remain in task slots 4 and 8.

| Task | Low-budget error W/T/L | High-budget error W/T/L | Ordinal error interaction |
| ---: | --- | --- | ---: |
| 0 | 0/4/0 | 1/3/0 | 1/4 |
| 1 | 0/4/0 | 0/4/0 | 0 |
| 2 | 0/4/0 | 1/3/0 | 1/4 |
| 3 | 0/4/0 | 1/3/0 | 1/4 |
| 4 | 0/4/0 | 0/3/1 | -1/4 |
| 5 | 0/4/0 | 1/3/0 | 1/4 |
| 6 | 0/4/0 | 1/3/0 | 1/4 |
| 7 | 0/4/0 | 0/4/0 | 0 |
| 8 | 0/3/1 | 0/3/1 | 0 |
| 9 | 0/4/0 | 1/3/0 | 1/4 |
| 10 | 0/4/0 | 1/3/0 | 1/4 |
| 11 | 0/4/0 | 0/4/0 | 0 |

All 192 terminal-error vectors, all first-hit-or-null fields, all 96 cross-scale
mechanism pairs, all 48 budget-extension rows and all task summaries remain in the
canonical summary; no absent/failed rows were imputed.

## Fixed screen and next boundary

All required components passed:

| Frozen component | Observed |
| --- | --- |
| Full integrity / source/runtime / 192 cells / 96 prefixes / zero provider calls | PASS |
| Interaction numerator at least 2 | 2, exactly the floor |
| High-budget uplift numerator at least 2 | 2, exactly the floor |
| No low-budget net harm | 0 exact-success difference |
| No high-budget lost exact successes | 0 |
| High-budget new successes on at least two tasks | 2, exactly the floor |
| All leave-one-task-out high uplifts and interactions strictly positive | minimum 1/44 |
| All high-budget new successes follow differing common-prefix backup support | 2/2 |

The next admissible research step is a **separately frozen, source-disjoint
confirmation design**, with its own review and execution permission. Keep this
12-task cohort and its two rescues as development/selection evidence.
Do not tune on them and relabel the result as confirmation.

No additional experiment, new cohort, scale/threshold change, provider run, PR merge,
GitHub result publication or locked-128 evaluation was performed in this execution turn.
Old STOP decisions and prior consumed authorizations were not changed.

## Artifact anchors and local reproduction boundary

[Canonical independently verified summary](../results/countdown_feedback_budget_v6_development_20260910/summary.json)
and [producer COMMIT](../results/countdown_feedback_budget_v6_development_20260910/COMMIT.json)
are unchanged copies of the local originals.

| Artifact / identity | Digest or SHA-256 |
| --- | --- |
| Summary deterministic digest | `a9087a60d439d7d8e48d3a26da9028e1f9b230b21853ec8b0f678bb8063918a8` |
| Summary file SHA-256 (764,595 bytes) | `81149bbcc5f5d7e9a1c54e0192155d9125e58d9bed1163a63ea80a965f98c8dc` |
| COMMIT deterministic digest | `9e06588a70c605752314c3fba0719355c26f920e758801d745fe8aee0288a0ec` |
| COMMIT file SHA-256 | `3ff307a32b6bd8e7f845164d4e055b7cba8639049e13ca30311404634fa8d0d0` |
| RECEIPT deterministic digest | `8008c2b48f0cb60b3307ddd2f6a926bb7415a71e4d01d2fca1f842d52e7c07aa` |
| RECEIPT file SHA-256 (700,156 bytes) | `d43de6ea24ce420c7ec6f28d4f8f9edfeba4dd2909f594ef9edbd3a56fb60950` |
| Run-binding digest | `145ed6652641dce818ff8a0ce11785ca53b3ad5c9171978fa6a301eb6a670a7b` |
| Cohort seal digest | `e4533c2a3a6eb8425d5773445e835bf81797ea1f507d4fb76c5b18c24d8a7d34` |

Original private raw directory:
`artifacts/work/feedback-budget-development-v6-20260910`.
Original saved summary: the sibling `feedback-budget-development-v6-20260910.summary.json`.
The fixed study claim remains under
`artifacts/work/feedback-budget-v6-authorization-ledger/development-b5bacc808ee81015aca12cb25f05eed8ca3fbf56b20ef12f0b616e67f1c80475.json`.

Exact operation commands, exit results and stdout hashes are retained in local ignored
`feedback-budget-v6-run-20260910.log`, `feedback-budget-v6-analysis-20260910.log`,
`feedback-budget-v6-verify-20260910.log` and `feedback-budget-v6-validation-20260910.log`
under `artifacts/work`. The separate user-authorization note is local and not an
executable token. Tracked summary/COMMIT files alone do not substitute for raw traces,
the original claim/seal/candidate, exact runtime or history-preserving source ancestry.
