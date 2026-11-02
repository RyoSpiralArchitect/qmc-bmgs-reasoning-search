# Search-value development result, 2026-10-25

## Outcome and scope

The current single16 search did **not** show useful search value against the
fixed PUCT baseline on this sealed development cohort. Single16 solved55/512
rooted cells (10.7422%); PUCT solved73/128 source cells (57.0313%).
The sole primary source-mean difference is **−237/512 = −0.462890625**
(−46.2891 percentage points). The predeclared readout remains **IMPRECISE**:
the model half-width0.0788406872 exceeds0.05, and that precision gate comes
before the practical-uplift gate. A negative interval must not be used to
silently change the decision order. This is an observed negative development
result, not a winner/default, population-causal claim, or proof that learning
or stochastic search in general cannot help.

This note documents the one approved execution and one separate-process
generative analysis of candidate
`db475199e65666f187782182fef4056917287b5f`, plan digest
`db7a96cf89355d7dfa379d21573f1ce5967536294190bea3dadbd9b947a907e5`.
The cohort contains128 source clusters, not512 independent sources.
Single16 and selection-mean-off each have four fixed roots131072..131075;
greedy, beam2 and PUCT each have one physical row per source. The shared
deterministic PUCT row is referenced in four descriptive pair comparisons,
not generated or counted as four independent observations.

## Complete method readout

Every cell has a legal-action-score cap512 and six other caps100,000.
Greedy and beam2 retain their natural stopping; unused work is not spent by
hidden repetition, shared or transferred. Total actual primary work is
605,613/720,896, with115,283 unused. All1,408 cells are budget-valid and
missing-terminal count is0.

| Method | Exact successes / rows | Rate | Actual primary total | Primary per row | Unused primary |
| --- | ---: | ---: | ---: | ---: | ---: |
| single16 | 55/512 | 10.7422% | 255,540 | 499.1016 | 6,604 |
| selection-mean-off | 45/512 | 8.7891% | 255,255 | 498.5449 | 6,889 |
| greedy | 53/128 | 41.4063% | 11,813 | 92.2891 | 53,723 |
| beam2 | 57/128 | 44.5313% | 19,081 | 149.0703 | 46,455 |
| PUCT | 73/128 | 57.0313% | 63,924 | 499.4063 | 1,612 |

The rates average the fixed roots within each source; the table is not a
comparison of equally large independent samples. All seven charged work axes,
per-source/root totals and unspent vectors are retained in the
[summary](../qualifications/countdown_search_value_development_20261025.summary.json)
and [saved-event diagnostics](../qualifications/countdown_search_value_development_20261025.diagnostics.json).

| Charged axis | Total |
| --- | ---: |
| legal_action_scores | 605,613 |
| edge_selections | 33,855 |
| transitions | 33,855 |
| generated_perturbation_coordinates | 510,795 |
| proposal_state_evaluations | 23,112 |
| proposal_action_scores | 335,872 |
| verifier_calls | 6,523 |

These counters do not establish equal total computation, latency, energy or
hardware efficiency. Proposal-internal work is additional: reconstructed
completion-action evaluations are3,021,556 /3,491,962 /393,426 /531,209 /488,759
for the methods in the table order. Internal transition evaluations are
439,424 /516,578 /45,438 /67,615 /63,566. Root proposal-action counts overlap
the charged proposal-action axis and must not be added twice. The kernel
reconstructed internal counts during the already completed generative replay;
the separate event checker verifies materializations, root-action counts and
stored internal-transition counters, but does **not** independently re-enumerate
completion actions. No live-instrumentation or independent-proof claim is made
for that last counter.

## Primary, secondary comparisons and sensitivity

| single16 minus baseline | Gain | Loss | Net /512 descriptive pairs | Minimum-error win/tie/loss/missing |
| --- | ---: | ---: | ---: | --- |
| PUCT — sole primary | 2 | 239 | −237 | 4/87/421/0 |
| selection-mean-off — diagnostic | 14 | 4 | +10 | 61/422/29/0 |
| greedy — diagnostic | 7 | 164 | −157 | 18/105/389/0 |
| beam2 — diagnostic | 5 | 178 | −173 | 14/104/394/0 |

The primary exact source sample variance is51735/260096. The fixed
`mean +/- 2*source_sd/sqrt(128)` model interval is
[−0.5417313121730879, −0.3840499378269121], half-width
0.07884068717308788. The practical threshold remains+0.02. Source uniqueness
under deterministic, solvability-filtered, non-replacement generation does
not establish independence, exchangeability or interval coverage. In
particular, IMPRECISE does not erase the large observed negative difference,
and the negative difference does not authorize changing the predeclared gate.

Across sources the primary is positive in2, negative in72 and tied in54.
Root-specific primary nets are−55,−62,−61,−59, each over128 source pairs.
Leaving one source out yields net−238..−233 over508 descriptive pairs;
leaving one root out yields−182..−175 over384. These are sensitivity
descriptions, not new confidence intervals or independent replications.

The diagnostic mean-on advantage is+10/512 =+1.953125pp, with12 positive,
3 negative and113 tied sources. Its root nets are+7,0,0,+3; source omission
nets+8..+11/508 and root omission+3..+10/384. It cannot replace the primary
or establish that learned means are generally helpful. Mean-off removes only
the selection mean; backups, visits and visit-dependent noise remain.

## Complementarity, first exact work and censoring

Single16 has an exact result in at least one root on38 sources; PUCT on73.
There are36 overlapping sources,37 PUCT-only sources and2 single16-only
sources. The last two are source slots65/root131073 (first exact at328 scores)
and100/root131072 (414). The four-root union spends up to four times a
single-row cap, so it is descriptive, not an equal-budget alternative method.

| Method | Successful rows | First exact primary min / median / max | First exact at <=128 / <=256 / <=384 | No-hit rows; stopping primary range |
| --- | ---: | --- | --- | --- |
| single16 | 55 | 67 /342 /511 | 12 /21 /31 | 457; 461..512 |
| selection-mean-off | 45 | 67 /347 /511 | 11 /20 /28 | 467; 461..512 |
| greedy | 53 | 58 /91 /131 | 51 /53 /53 | 75; 58..124 |
| beam2 | 57 | 94 /153 /205 | 6 /57 /57 | 71; 103..191 |
| PUCT | 73 | 58 /102 /443 | 51 /58 /70 | 55; 464..512 |

No-hit cells retain null first-exact work and censoring at actual stopping
work, not a fabricated failure time at512. Successful rows retain the whole
seven-axis first-hit vector. Earlier PUCT hits and additional successes are
observations on this cohort; they do not identify a causal mechanism.
All successful/lost source-root cases remain in the diagnostics, including
the72 sources contributing239 primary losses.

## What the observed choices show

Single16 and mean-off have the same first-trajectory projection in512/512
pairs. Their entire action sequences are identical in201/512 and diverge in311.
Every first divergence is at the same observed state; none is merely one
sequence ending at a common prefix. All11,888 actual common keyed random
coordinates match. This is common material at encountered coordinates, not
a guarantee of common whole trajectories after histories diverge.

On the stored histories, toggling the mean changes1,570/14,218 single16
choices and755/14,220 mean-off choices. These are passive score comparisons,
not counterfactual rollouts or attributable success counts. Single16 chooses
a non-maximum-prior action7,419/14,218 times; mean-off8,416/14,220.
The absolute selected noise term exceeds its selected prior term in
8,149 and9,333 choices respectively. Those comparisons omit competing-action
margins and cannot by themselves prove that noise caused the performance gap.
Full first-divergence mean/prior/noise/visit arrays are retained.

Terminal observations are2,733 /2,735 /128 /256 /671 in table order;
exact terminal observations are131 /49 /53 /85 /328, distinct from successful
cell counts. Ordinary-selection repeated-state counts are4,909 /3,297 /0 /0 /
2,341. Beam's zero is **not** a claim of no repeated beam states: the sealed
reducer defines that metric on `selection_committed` events, whereas beam
emits `beam_layer_selection_committed`. The supplementary checker explicitly
retains beam-layer counts, selected-child counts and layer-sequence digests;
ordinary first-trajectory diagnostics for beam are null/not applicable.

## Evidence, repair history and validation boundaries

Candidate qualification:1,822 tests, zero skips, exit0, repository PASS on the
exact candidate. The original run completed2026-10-24 21:48:39–21:53:45 UTC;
separate analysis completed21:55:12–22:01:15 UTC. All1,408 cells were
generatively replayed byte-identically, with128 source reductions,512 pair
diagnostics and zero cross-budget prefix pairs. Peak native RSS observed by
analysis was421,298,176 bytes; the outer pair-cache limit2 is not a total RSS
bound. Raw run/analyze process receipts, logs and approval references are
bound in the [execution record](../qualifications/countdown_search_value_development_20261025.execution.json).
The existing plan's authorization=false and candidate review's pending text
remain historical snapshots.

A new independent-implementation saved-event checker initially failed at
cell9/beam2 because it equated ordinary selection events with charged edges.
Its failed source, empty stdout, traceback and exit1 remain intact. Ryō
explicitly approved repairing only that checker and using separate logs.
Five synthetic regression tests then passed. The repaired checker completed
2026-10-26 04:50:52–04:51:02 UTC (13:50:52–13:51:02 JST), exit0, empty stderr.
All terminal/error/first-hit/seven-axis work reductions, source/root/leave-one-out
tables, exact rational moments and512 choice diagnostics match the saved
summary. All13,551 frozen files in that check remained unchanged. Neither the
experiment nor the scientific analyzer was rerun.

The [reproducible checker](countdown_search_value_development_20261025.py) imports
no search engine or candidate reducer. It is an independent implementation,
not an independent reviewer. The `validate-data` authoring checks kept the
denominator/grain, nulls, precision-first gate and failed-checker provenance
explicit. Sharing is appropriate only with these caveats and the result-package
validation status in the [result review](../reviews/countdown_search_value_development_result_20261025.md).

## Research implication — proposal only

Do not promote this single16 setting. The observed mean contribution can alter
later choices and mildly help against mean-off, yet the whole search loses
substantially against PUCT and even the cheap greedy/beam diagnostics. The next
scientific question should separate the prior/perturbation balance and useful
exploration from learned-mean bookkeeping, with PUCT kept as an external
baseline and all work axes retained. A prior-preserving/noise-control or
matched exploration assay could distinguish those hypotheses on genuinely
fresh sources, after a new plan and explicit approval.

This is not approval to sweep noise, tune against these128 sources, remove
the prior, change the kernel, generate new data, run an adaptive scheduler or
merge. No extra experiment, implementation improvement, default or scientific
winner is produced by this package.
