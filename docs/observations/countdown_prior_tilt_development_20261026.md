# Prior-anchored return tilt: development observation, 2026-10-26

## Readout

The fixed prior-preserving candidate did not close the gap to fixed PUCT on
this fresh cohort. The sole primary, prior-tilt16 minus PUCT, is
−129/1024 = −0.1259765625 (−12.60 percentage points). The registered
precision-first readout is **NO_PRACTICAL_UPLIFT_SIGNAL**. Its approximate
source model interval is [−0.165115389583868, −0.086837735416132], with
half-width 0.039138827083868, below the 0.05 target. The practical threshold
remains +0.02. This is neither a population-causal conclusion nor proof that
learning generally cannot help. `winner` and `scientific_decision` remain null.

There are 256 source clusters, four within-source roots for each stochastic
policy, and one physical PUCT run per source. The source mean averages four
root outcomes before subtracting PUCT. The 1,024 descriptive pair references
do not turn the 256 PUCT runs into 1,024 independent observations.

| Fixed method | Exact successes / physical cells | Rate | Sources with any success |
| --- | ---: | ---: | ---: |
| prior-tilt16 | 427 / 1,024 | 41.70% | 152 / 256 |
| prior-mean-off | 443 / 1,024 | 43.26% | 155 / 256 |
| PUCT | 139 / 256 | 54.30% | 139 / 256 |

The four-root union spends up to four per-source budgets. Its 152-source
coverage is not an equal-budget win over PUCT's 139. Prior-tilt's union shares
127 successful sources with PUCT, adds 25, misses 12, and both miss 92.
Mean-off shares 129, adds 26, misses 10, and both miss 91.

## Frozen question and scope

Candidate `2e323cc91a9bebb7d6dc58f336bcf5e6edb72a25` was fixed before generation.
Plan digest is `ca4174b8ec1f4d4c2606b64da490c23d858dbefe0c8d8cf697eecbab6fe9ad20`.
The [policy](../strategy/countdown_prior_tilt_development_20261026.md) and
[registered plan](../preregistrations/countdown_search_value_prior_tilt_20261026.plan.json)
define the first 256 eligible, unique, solvable Countdown sources, generator
26102601, six inputs 1..10, target 100..999, maximum 10,000 attempts and roots
262144..262147. Historical task/source identities and conservative literal
fixtures are excluded. No selection uses candidate search success or witnesses.
Deterministic solvability filtering and uniqueness do not establish independent
sampling, exchangeability, population representativeness or interval coverage.

The stochastic scores are `(log prior + Q16) + Gumbel(original uniform)`;
coefficients are one, and mean-off zeros only selection use of Q. Updates,
visits, m2 and material remain. Normal values are generated and charged but
unused in this selector. Finite keyed uniforms do not provide an exact
continuous categorical law. PUCT remains c=1 with binary exact return. The
primary compares complete policies, not a single isolated noise change.

Ryō delegated steps 1→2 before this candidate digest existed; the
[authority receipt](../qualifications/countdown_prior_tilt_development_20261026.approval.json)
records `delegated_candidate_selection`, not invented exact-digest consent.
One experiment and one separate generative analysis were executed. No provider,
C5, locked evaluation, sweep, extra condition, new default or QMC/transfer run
was performed. Old authorization=false/pending snapshots remain historical.

## Paired gains, losses and sensitivity

| Contrast (1,024 descriptive pairs) | Gains | Losses | Net | Minimum-error win / tie / loss / missing |
| --- | ---: | ---: | ---: | --- |
| prior-tilt16 − PUCT (primary) | 28 | 157 | −129 | 36 / 693 / 295 / 0 |
| prior-tilt16 − prior-mean-off (diagnostic) | 15 | 31 | −16 | 37 / 928 / 59 / 0 |

The primary exact source sample variance is 34133/348160 (denominator 255
before rational simplification). Source-average differences have 25 positive,
71 negative and 160 tied sources. The mean-off diagnostic has 12 positive,
28 negative and 216 tied sources; mean −1/64, variance 3/272, approximate model
interval [−0.02875262578776259, −0.0024973742122374083]. It has no promotion
readout and does not replace the primary.

| Root | Tilt successes / 256 | Mean-off successes / 256 | Tilt−PUCT net / 256 | Tilt−off net / 256 |
| --- | ---: | ---: | ---: | ---: |
| 262144 | 112 | 118 | −27 | −6 |
| 262145 | 108 | 113 | −31 | −5 |
| 262146 | 103 | 108 | −36 | −5 |
| 262147 | 104 | 104 | −35 | 0 |

Deleting one source gives primary net −131..−125 over 1,020 references;
deleting one root gives −102..−93 over 768. The corresponding mean-off nets
are −18..−14 and −16..−10. These are descriptive omission sensitivities,
not confidence intervals or fresh confirmations. Every source/root row and
every gain/loss case is retained in the diagnostics JSON.

## Search behavior, first hits and censoring

All 2,304 cells have terminal observations: missing-terminal count is zero,
not imputed. Minimum-error medians are 1, 1 and 0 for tilt, mean-off and PUCT;
maxima are 202, 202 and 16. All stop at the primary-budget boundary; no
non-primary guard binds. Failed cells retain right-censoring at actual work,
not a fictitious first-hit value of 512.

| Method | First-hit legal-score min / median / max (successful cells only) | No-hit count; censor min / median / max | Verified terminals | Exact terminals | Selection-state revisits |
| --- | --- | --- | ---: | ---: | ---: |
| prior-tilt16 | 41 / 178 / 508 (427 cells) | 597; 461 / 503 / 512 | 5,560 | 1,092 | 15,342 |
| prior-mean-off | 41 / 188 / 509 (443 cells) | 581; 461 / 503 / 512 | 5,548 | 888 | 13,347 |
| PUCT | 38 / 100 / 511 (139 cells) | 117; 462 / 503 / 512 | 1,393 | 680 | 4,932 |

First-hit distributions condition on success and are not unbiased speed
comparisons. Exact-terminal counts include repeated observations, not distinct
solved sources. Tilt has more exact terminal events but fewer successful cells
than mean-off; repeated success is not breadth. The revisit measure is repeated
states in ordinary selection events, not unique new states or computational
waste by definition. Tilt materializes 13,573 proposal rows versus 15,557 for
mean-off, while making almost the same number of selections (28,915/28,904).
This is compatible with more concentrated reuse, not proof of its cause.

All 1,024 paired first trajectories match. Entire action sequences match in
213 pairs; the remaining 811 have a first divergence at the same state, and
none differ solely because one sequence ends at the common prefix. All 25,424
actually common keyed state/visit material records match. Divergent trajectories
are not globally identical random-number sequences.

Passive same-history removal/addition of mean changes 2,004/28,915 tilt choices
and 1,595/28,904 mean-off choices. The saved decompositions retain current means,
visits, log-prior terms, Gumbels and chosen scores for each first divergence.
The independent checker computes Gumbels from original uniforms, ignores normals
for selection, and reproduces binary64 score association and canonical ties.
These are passive rescoring diagnostics, not alternative rollouts: they do not
prove which particular changed choice caused an eventual gain or loss.

## Actual work: all seven axes

Each cell has a 512 legal-action-score cap and six separate 100,000 guards.
Amounts below are aggregate charged work, not equal-total-compute or wall time.

| Axis | prior-tilt16 | prior-mean-off | PUCT | Total |
| --- | ---: | ---: | ---: | ---: |
| edge_selections | 28,915 | 28,904 | 7,251 | 65,070 |
| generated_perturbation_coordinates | 512,069 | 512,104 | 0 | 1,024,173 |
| legal_action_scores | 512,069 | 512,104 | 128,082 | 1,152,255 |
| proposal_action_scores | 190,373 | 214,705 | 35,785 | 440,863 |
| proposal_state_evaluations | 13,573 | 15,557 | 2,319 | 31,449 |
| transitions | 28,915 | 28,904 | 7,251 | 65,070 |
| verifier_calls | 5,560 | 5,548 | 1,393 | 12,501 |

Primary unused work is 12,219 + 12,184 + 2,990 = 27,393 of 1,179,648.
All other unspent axes are retained per cell/source/root in the JSON and equal
their respective cap minus actual work. There is no pooled/reallocated budget.
Proposal-internal transition evaluations are 633,412 / 704,783 / 125,281 and
completion action enumerations 4,474,952 / 4,856,390 / 952,466; they remain
separate from charged legal scores. The latter counter is carried from the
generatively authenticated raw record, not independently re-enumerated by the
new event checker. No total-runtime efficiency conclusion follows.

## Evidence, failures and verification boundaries

The first full qualification failed before descendant analysis when an existing
384-cell public fixture runner exceeded its unchanged 240-second limit:
1,864 tests, one error, zero skips. Cause remains UNKNOWN. Ryō explicitly
authorized one fixed-candidate retry; that distinct attempt passed 1,864 tests
in 1,065.795s with zero skips. Neither the failure nor its logs were rewritten.
Two saved-evidence audit parser assumptions were corrected with their failed
source/log snapshots retained; they were not scientific reruns.

The experiment ran 2026-10-26 15:32:26–15:41:59 UTC; separate all-cell analysis
ran 15:56:19–16:07:59 UTC. Both exited 0 with complete postflight, no errors
and unchanged inputs. The run's 2,307 files survived analysis byte-identically;
final output has 2,310 files. All 2,304 cells replayed generatively, all 1,024
pairs were checked, and cross-budget prefix count is zero (one budget).
Peak native analysis RSS was 423,624,704 bytes; outer detail cache limit 2 is
not a total-memory bound.

The [stdlib event checker](countdown_prior_tilt_development_20261026.py) imports
no engine/reducer. Seven synthetic fixtures cover Gumbel/log-prior/mean toggles,
unused normals, forged scores/charges/material, missingness/censoring and
precision-first gates. Its one captured saved-data execution (16:20:43–16:20:59
UTC) exited 0, stderr empty, all 15,952 protected files unchanged. It exactly
recomputed terminal/error/first-hit/censoring/seven-charge reductions, all
method/source/root and leave-one-out rows, exact source moments and 1,024 pairs.
This is an independent implementation, not an independent reviewer or another
generative replay. `validate-data` guidance informed denominator, missingness,
calculation and claim checks without changing the registered statistical rule.

Tracked first mirrors: [summary](../qualifications/countdown_prior_tilt_development_20261026.summary.json),
[diagnostics](../qualifications/countdown_prior_tilt_development_20261026.diagnostics.json),
[execution chain](../qualifications/countdown_prior_tilt_development_20261026.execution.json),
[qualification](../qualifications/countdown_prior_tilt_development_20261026.validation.json),
[first failure](../qualifications/countdown_prior_tilt_development_20261026.qualification-failure.json).
The [result review](../reviews/countdown_prior_tilt_development_result_20261026.md)
tracks the separate result-package suite. Candidate PASS is not result-package
PASS; local validation is not hosted CI or external approval.

## Next question — proposal only

Do not promote this candidate or proceed directly to QMC/transfer on an assumed
strength gain. The old search-value study used a different cohort; its larger
negative gap cannot be subtracted from this gap as a paired improvement estimate.
The matched evidence here is a negative primary and a modest negative mean-use
diagnostic. The most useful next design question is whether learned return is
being used to revisit already-good paths rather than improve new-solution
coverage, while retaining a strong PUCT comparator. A separately reviewed,
frozen candidate could test how returns influence traversal/backup, not add a
coefficient sweep or budget-administration framework. This is a hypothesis and
planning direction only: no new implementation, data generation or experiment
is authorized or performed by this result package.
