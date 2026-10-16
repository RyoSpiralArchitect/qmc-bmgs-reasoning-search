# E4 PUBLIC: what the false screen contains

Date: 2026-10-16 JST. Post-hoc diagnosis of one fixed PUBLIC fixture.

Status: **SAVED-DATA DIAGNOSTICS RECONCILED; NO NEW EXPERIMENT OR AUTHORITY.**
The separate coordinator saved-summary verification and package validation have
their own operation/review records; this note does not certify those operations.

要点: フィードバックは確かに探索を分岐させている。しかし高予算では
32件の救済に対して24件の取りこぼしがあり、差し引きは8/256。
その純増は1つのseedに集中する。次に調べたいのは「分岐の量」よりも
「正解への経路を失わずに、役立つ分岐を選べるか」である。
既存のfalseを変更せず、改善案は別の開発計画として扱う。

## 1. What was compared, and what was not

The fixture contains targets 1–64, all using **the same input multiset
[1,2,3,4,5,6]**. Four fixed seeds (8192–8195), two score budgets (256/512),
and terminal-value scales 0/16 produce 1,024 cells, 512 same-scale budget-prefix
pairs and 256 four-arm target/seed blocks. The unit for a paired outcome is a
target/seed block; it is not an independent source multiset.

Both arms use IID Thompson action perturbation with the same dimension-normalized
noise and `greedy_rollout_target_error/v1` proposal. There is no LM/provider,
QMC-versus-IID, semantic-routing or pruning intervention in this comparison.
Budget is **legal-action scores**, not tokens, completed trajectories or wall time.

Scale 0 is **exact-success-only feedback**, not feedback disabled. The terminal
reward is 1 for zero error; for nonzero error `e`, it is `scale / (scale + e)`.
Thus scale 16 gives error 1 reward 16/17, error 2 reward 8/9, error 4 reward 4/5,
and error 16 reward 1/2. The heuristic proposal, learned mean return, and
visit-count-scaled IID noise are separate terms in action selection. The stored
`m2` statistic is not used in this selection score; it would be wrong to explain
these score changes as empirical variance adaptation.

These are actual recorded results, but this is a repeatedly inspected PUBLIC
connection fixture. It is not the sealed 64-source original study, a new
independent replication, or evidence of population-level search improvement.

## 2. Headline and the exact failed conditions

Arm order throughout is `[Y0_256, Y16_256, Y0_512, Y16_512]`.

| Score budget | Exact-only successes | Dense successes | Paired gains | Paired losses | Net uplift |
| --- | ---: | ---: | ---: | ---: | ---: |
| 256 | 70/256 (27.34375%) | 74/256 (28.90625%) | 12 | 8 | 4/256 (1.5625 pp) |
| 512 | 128/256 (50%) | 136/256 (53.125%) | 32 | 24 | 8/256 (3.125 pp) |

Interaction = high-budget uplift minus low-budget uplift = **4/256 = 1/64**.
Increasing budget adds 58 successes in exact-only and 62 in dense, not 62
successes attributable to dense feedback. The matched net difference is four.

| Frozen screen component | Observed | Result |
| --- | --- | --- |
| High uplift at least 1/24 | 8/256; at least 11 net successes required | FAIL; short by 3 |
| Interaction at least 1/24 | 4/256; at least 11 net successes required | FAIL; short by 7 |
| Low uplift nonnegative | 4/256 | PASS |
| No high-budget lost success | 24; required 0 | FAIL |
| Rescue at least 11 task definitions at high budget | 25/64 have at least one rescued seed | PASS |
| Leave one task definition out: high uplift and interaction positive | High 5–10/252; interaction 1–6/252 | PASS |
| All high-budget new successes have common-prefix feedback support | 32/32 | PASS |

The conjunction remains **false**. Arithmetic shortfalls are not an optimization
target or permission to change the fixture/gates. `scientific_decision` remains
`null`, and original-study execution remains unauthorized by this result.

"Lost success" means the matched exact-only cell succeeds while the dense cell
does not. It does **not** mean an already-discovered dense solution was forgotten.
All same-scale low-to-high prefixes preserve successes. A best-so-far answer cache
alone therefore would not fix these 24 losses.

At least one seed succeeds on `[44,44,55,57]` task definitions. The 25 rescued
definitions are not 25 newly solved definitions: other seeds or the other arm
may already solve them. High-budget losses occur on 21 task definitions.

## 3. Where the extra budget changes the contrast

All 16 binary patterns were counted, including seven prefix-forbidden patterns
with zero observations. The nonzero patterns are:

| Four-arm pattern | Blocks | Contribution to interaction numerator |
| --- | ---: | ---: |
| 0000 | 96 | 0 |
| 0001 | 25 | +25 |
| 0010 | 19 | −19 |
| 0011 | 34 | 0 |
| 0101 | 7 | 0 |
| 0111 | 5 | −5 |
| 1010 | 5 | 0 |
| 1011 | 3 | +3 |
| 1111 | 62 | 0 |
| Total | 256 | +4 |

Of 12 low-budget gains, seven persist and five disappear because exact-only
catches up. Of eight low-budget losses, five persist and three disappear because
dense catches up. New high-budget gains (25) and losses (19) contribute +6;
the changed low-budget contrasts contribute −2. This reconciles to +4 exactly.

The outcome-redacted mechanism labels give another exhaustive partition:

| Divergence class | Blocks | Low net | High gains/losses | High net | Interaction numerator |
| --- | ---: | ---: | --- | ---: | ---: |
| Already diverged at budget 256 | 86 | +4 | 16/13 | +3 | −1 |
| First diverged with budget 512 | 110 | 0 | 16/11 | +5 | +5 |
| No action divergence | 60 | 0 | 0/0 | 0 | 0 |
| Total | 256 | +4 | 32/24 | +8 | +4 |

The original reducer constructs mechanism labels without success/error fields
before reducing outcomes. Joining outcomes to those labels is nevertheless a
**post-treatment descriptive analysis**, not a causal mediation estimate.

## 4. More opportunity is not sufficient

"Opportunity" here is the observed number of completed terminal trajectories
after the first differing action, not a wall-clock allowance or a direct count
of remaining score budget.

| Budget | Completed terminals after divergence | Pairs | Gains | Losses | Ties |
| --- | --- | ---: | ---: | ---: | ---: |
| 256 | No divergence | 170 | 0 | 0 | 170 |
| 256 | 0 | 3 | 0 | 0 | 3 |
| 256 | 1 | 83 | 12 | 8 | 63 |
| 256 | 2+ | 0 | 0 | 0 | 0 |
| 512 | No divergence | 60 | 0 | 0 | 60 |
| 512 | 0 | 10 | 0 | 0 | 10 |
| 512 | 1 | 41 | 5 | 3 | 33 |
| 512 | 2+ | 145 | 27 | 21 | 97 |

All 86 low-budget and 196 high-budget divergent pairs have preceding differing
applied backup values. At high budget this includes **both 32/32 gains and
24/24 losses**. Feedback support establishes that the signal reaches selection;
it does not establish that the resulting direction is useful.

Of the 24 losses, 23 first diverge at the root and one at depth 1. Of the 32 gains,
30 first diverge at the root and two at depth 1. First divergence occurs after
one to three completed trajectories for these outcome-changing cases. Both
groups are affected by early steering, not just late changes with no time left.

An exploratory score comparison gives median exact-only winner margin 0.1681
in losses versus 0.4433 in gains. Median increase in the dense-chosen action's
score is 0.7132 versus 0.7810. These are outcome-selected groups, not validated
thresholds; their medians neither identify a safe margin rule nor prove that
smaller rewards would retain gains. Full values and denominators are saved.

## 5. Seed sensitivity is a stronger warning than target leave-one-out

| Seed | Four arm successes, denominator 64 each | Low net | High net | Interaction numerator |
| --- | --- | ---: | ---: | ---: |
| 8192 | [18,21,31,39] | +3 | +8 | +5 |
| 8193 | [20,21,32,31] | +1 | −1 | −2 |
| 8194 | [17,20,32,33] | +3 | +1 | −2 |
| 8195 | [15,12,33,33] | −3 | 0 | +3 |

The full high-budget net +8 equals seed 8192's contribution; the other three
seeds sum to zero. Omitting 8192 gives high uplift **0/192**, low uplift **1/192**,
and interaction **−1/192**. This is sensitivity of the fixed finite matrix,
not a four-seed population confidence interval.

Post-hoc target bands also differ: high gains/losses are 9/6 for targets 1–16,
6/7 for 17–32, 8/7 for 33–48, and 9/4 for 49–64. These bands are not independent
sources or a basis for choosing favorable future targets. Passing target-level
leave-one-out does not establish seed- or source-level robustness.

## 6. Exact success and error quality do not move together

Compare each cell's minimum verified terminal absolute error; a win means dense
has smaller error than exact-only on the same target, seed and budget.

| Budget | Wins | Ties | Losses | Ordinal net |
| --- | ---: | ---: | ---: | ---: |
| 256 | 23 | 215 | 18 | +5/256 |
| 512 | 43 | 174 | 39 | +4/256 |

Ordinal-error interaction is **−1/256**, whereas exact-success interaction is
+4/256. This is not a mean-error effect size; it counts the direction of paired
minimum-error comparisons. It prevents a blanket claim that denser reward
uniformly improves terminal quality.

Completed terminal counts are `[512,511,1030,1034]`; exact-terminal observations
are `[95,99,270,284]`. Low-budget cells finish 1–2 trajectories, high-budget cells
4–5. Terminal observations are not unique witnesses or successful-cell counts.
Every cell stops on the primary budget with no overshoot and nonbinding secondary
guards. Actual charged legal-action scores sum to `[59270,59691,125606,125782]`;
the caps match, but indivisible action-set charges leave unequal remainders.
The four additional dense terminals at high budget alone cannot explain the
direction of the 32 gains and 24 losses.

## 7. Trace-level examples, selected symmetrically

Selection rule: first three `(task_slot, seed)`-ordered high-budget losses and
first three gains. This rule was chosen post-hoc and is not a representative
sample. Terminal error sequences are chronological; full actions, expressions,
cell hashes and common-prefix backup values are in the diagnostic JSON.

| Sign | Target / seed | Exact-only terminal errors | Dense terminal errors | First differing action, exact-only → dense |
| --- | --- | --- | --- | --- |
| Loss | 2 / 8192 | [13,2,0,0] | [13,2,1,1] | root, trajectory 2: 4+6 → 6−4 |
| Loss | 7 / 8193 | [4,713,4,0] | [4,4,21,4] | root, trajectory 1: 2×5 → 3−1 |
| Loss | 9 / 8194 | [6,8,0,0] | [6,8,8,3] | root, trajectory 2: 1×2 → 4+5 |
| Gain | 4 / 8195 | [22,6,1,16] | [22,6,1,0] | depth 1, trajectory 3: 5−3 → 6−5 |
| Gain | 7 / 8195 | [4,1,10,24] | [4,4,1,0] | depth 1, trajectory 1: 2+5 → 3+4 |
| Gain | 8 / 8192 | [12,64,1,1] | [12,12,0,3] | root, trajectory 1: 3×4 → 6−4 |

Trajectory indices are zero-based. Target 2 shows the central concern plainly:
after the shared [13,2] errors, dense improves to error 1 but never hits exact
zero, while exact-only finds zero twice. Target 4 shows the opposite outcome:
a late dense divergence converts error 1 to an exact solution. Neither example
establishes the counterfactual outcome of a different reward or routing policy.

## 8. What this suggests testing next — not implemented or executed

1. **Calibrate the influence of nonexact reward.** The scale-16 signal can be close
   to an exact reward after only one observation. A separate exact-return channel
   and bounded nonexact shaping channel, or a smaller shaping influence, is a
   plausible design candidate. The first diagnostic should measure common-prefix
   action-score changes and later gained/lost successes separately. We have not
   shown which scale, coefficient or timing is better; no sweep was performed.
2. **Treat lost routes as a resource tradeoff.** A baseline-protected allocation
   could preserve coverage, but running a full 512-score baseline plus extra dense
   search is not a matched-512 comparison. A fair design must charge both branches
   within the same total budget and explicitly measure sacrificed dense gains.
   Saving found answers is necessary bookkeeping, not protection against a route
   that was never explored. No zero-loss guarantee is established.
3. **Validate outside the inspected fixture.** Freeze a small, separately reviewed
   development matrix with multiple source multisets and held-out seeds before
   choosing a winner. Preserve the current PUBLIC negative result and do not use
   another pass on this fixture as independent confirmation. The existing C5
   study and locked-128 are not available by implication; any new experiment and
   its inputs require a separate scope/approval decision.

Priority is 1 → 2 → 3 as design work, with both gains and losses, exact success,
minimum error, score charges and seed/source sensitivity reported. More budget
or more feedback-informed divergences is not itself the objective. Current
evidence justifies those questions, not a claim that any proposed fix works.

## 9. Reproducibility and validation limits

- [Pinned summary](../qualifications/countdown_feedback_budget_receiver_e4_public_20261015.summary.json):
  digest `c01943578e9d1d6788adab6479b67c3c03d7ec57b828ea4e4dd889f7d2207274`,
  3,873,320 bytes, SHA-256 `83250ff7c3eb3833a8273252b282a5961149b736f2d59b957fe1c80d48735e5d`.
- [Exact diagnostic tables and cases](../qualifications/countdown_feedback_budget_receiver_e4_public_20261016.diagnostics.json):
  65,646 bytes, SHA-256 `ce9c7978beeeb993f2169b878545ad797e2b6507206c508a509183b5f009b0cc`.
- [Executed companion notebook](countdown_feedback_budget_receiver_e4_public_20261016.ipynb):
  five code cells executed without error; standalone calculation embedded in full.
  It reruns saved-data arithmetic, **not** search or generative replay.

The standalone calculation authenticated all 1,024 COMMIT-indexed raw cell byte
counts/hashes, strict JSON and record digests; checked the complete unique
cross-product; independently recounted terminal success/error vectors and all
256 blocks; matched common-prefix selection coordinates/actions/scores and
post-divergence terminal counts for 512 pairs; and reconciled all seven frozen
screen components. Notebook execution recomputed the saved diagnostic JSON
exactly. Every exhaustive cut reconciles to its stated parent denominator.

This is a same-agent second implementation of the arithmetic, not an independent
human review. The separate coordinator analysis/verification provides the full
generative replay and whole-summary comparison; this notebook does not replace
it. A Git-only checkout without the retained raw bundle cannot fully rerun the
notebook and must fail closed rather than use a summary-only substitute.

The original-public and receiver-v2-public summaries have exactly the same arm
counts, gain/loss counts, patterns, task rows and seven screen components. The
receiver-v2 whole reduction is byte-value identical to E4's; the older original
PUBLIC whole reduction is not claimed identical. E4's false screen is not a new
numerical regression. Reproducing these same outcomes is engineering evidence,
not three independent scientific replications.

No new raw search result, candidate, fixed attempt, provider call, production run,
C5 decision, merge or release is created by this diagnosis. All historical
negative outcomes remain unchanged.
