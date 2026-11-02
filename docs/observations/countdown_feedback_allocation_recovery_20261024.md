# Allocation development: more continuation helped, but did not beat the full stream

The predeclared primary result is **NO_PRACTICAL_UPLIFT_SIGNAL** under the
specified development model. The 384/128 allocation gained 34 and lost 51
exact successes versus one 512-budget stream: net −17/2,048 (−0.8301 percentage
points). It improved on equal splitting by 10/2,048, but that secondary result
does not replace the primary. `winner` and `scientific_decision` remain null.

This observation uses the original, completed experiment, not a repeat.
Its interrupted first analysis remains UNKNOWN. An explicitly authorized new
recovery attempt replayed all saved data from cell zero, then a separate
stdlib-only arithmetic implementation checked the saved terminal events.

## What was compared

The experiment contains 256 distinct accepted source multisets, eight fixed
root seeds 65536–65543, total primary cap 512, and three fixed conditions:
6,144 cells / 10,240 branch searches. There are **256 source clusters**, not
2,048 independent sources per arm. All seven work caps were split before
search; there was no sharing, early-success stop, spare-budget transfer, or
adaptive allocation. Feedback scale16, proposal, stream keys, and readout
were fixed. This is neither QMC-versus-IID nor an LM/provider evaluation.

The deterministic recipe took 403 generation attempts: 256 accepted, 96
unsolvable, 35 excluded source identities, and 16 duplicate source identities.
No candidate was selected by the experimental arms' search results. Filtering
for solvability and unique identities does not establish random sampling or
independent source clusters.

| Condition | Primary / secondary caps | Exact successes | Rate |
| --- | ---: | ---: | ---: |
| single16 | 512 / absent | 212 / 2,048 | 10.3516% |
| equal16 | 256 / 256 | 185 / 2,048 | 9.0332% |
| weighted16 | 384 / 128 | 195 / 2,048 | 9.5215% |

| Paired contrast | Gains | Losses | Net | Minimum-error win / tie / loss / missing |
| --- | ---: | ---: | ---: | --- |
| **weighted16 − single16 (primary)** | 34 | 51 | −17 | 296 / 1,300 / 452 / 0 |
| weighted16 − equal16 (diagnostic) | 56 | 46 | +10 | 461 / 1,135 / 452 / 0 |
| equal16 − single16 (diagnostic) | 74 | 101 | −27 | 595 / 700 / 753 / 0 |

Every contrast has denominator2,048. All 6,144 cells had at least one verified
terminal; missing error remained distinct from zero and was not imputed.
Single-stream branch-overlap fields remain null, not zero.

## The fixed primary readout

For each source, the paired success differences are averaged over the eight
fixed seeds. Recalculation from terminal flags gives:

- Exact source mean: −17/2,048 = −0.00830078125.
- Sample source variance: 27,103/4,177,920, with source denominator255.
- Model interval `mean ± 2 × source_sd / sqrt(256)`:
  [−0.01836867527936405, +0.0017671127793640502], or approximately
  [−1.8369, +0.1767] percentage points.
- Half-width0.01006789402936405 (1.0068 percentage points), below the
  predeclared0.05 target. The upper bound is below the practical uplift0.02;
  the fixed rule therefore returns `NO_PRACTICAL_UPLIFT_SIGNAL`.

The interval includes zero: this is not a declaration of a confirmed negative
population effect or equivalence. It is an approximate model-based interval,
conditional on the fixed seed set, generator and exclusions. Exchangeability,
sufficient source independence and coverage are assumptions, not conclusions
from unique hashes or the deterministic, filtered, non-replacement generator.
The threshold and precision target were not changed after observing results.

## Where gains and losses came from

The second stream was behaviorally different: full action sequences matched
in 0/2,048 blocks for both two-stream arms; first trajectories matched in
1/2,048. Diversity was present, but its opportunity cost mattered.

For **384/128**, the first stream solved161 blocks by384 scores. The second
128-score stream solved38: four overlapped the first stream and34 were pure
additions against the full512 stream. None rescued a late full-stream success.
The full first stream found51 more successes after384, with first discoveries
at388–511 scores. All51 became losses under384/128. Thus:

`161 first-stream successes + 34 unique second-stream successes = 195`,
versus `161 + 51 late continuation successes = 212`.

For **256/256**, the first stream solved95, the second96, with six overlaps.
The90 secondary-only successes comprised74 pure additions and16 rescues of
successes that the full first stream also found later. Full continuation added
117 successes after256;16 were rescued and101 lost. “Secondary-only” and
“gain over full continuation” are not interchangeable.

The observed **weighted-versus-equal** comparison isolates the fixed trade:
all56 gains were discoveries in primary256→384 when secondary256 failed;
all46 losses were discoveries in secondary128→256 when primary384 failed.
The extra first-stream depth helped relative to equal splitting, but did not
make up the cost relative to keeping all512 in one stream.

These are descriptions of actual verified prefix traces. Lost successes mean
the shortened branch never reached their first discovery, not that the search
forgot an already found solution. Discovery-time distributions do not estimate
any unrun allocation, adaptive policy, or new default.

## Source and seed sensitivity

Primary gains span30 sources and losses38, with both present across all eight
seeds. Source net signs are25 positive,32 negative and199 zero; sources may
contain both gains and losses. This is not a story about one exceptional seed.

| Root seed | Primary gains | Primary losses | Net / 256 blocks |
| --- | ---: | ---: | ---: |
| 65536 | 5 | 8 | −3 |
| 65537 | 4 | 7 | −3 |
| 65538 | 5 | 6 | −1 |
| 65539 | 7 | 6 | +1 |
| 65540 | 4 | 11 | −7 |
| 65541 | 4 | 5 | −1 |
| 65542 | 2 | 3 | −1 |
| 65543 | 3 | 5 | −2 |

Leaving out one source yields primary net−19..−14 over2,040 blocks; leaving
out one seed yields−18..−10 over1,792. Equal-minus-single also stays negative
(−30..−24 /2,040 and−31..−18 /1,792). Weighted-minus-equal stays positive
(+7..+12 /2,040 and+3..+13 /1,792). These are descriptive sensitivity ranges,
not confidence intervals, additional tests, or independent replications.
Every source/seed and omission row is retained in the diagnostic JSON.

## Actual work under equal caps

| Work axis | single16 | equal16 | weighted16 | Combined |
| --- | ---: | ---: | ---: | ---: |
| legal_action_scores | 1,022,951 | 995,513 | 993,056 | 3,011,520 |
| generated_perturbation_coordinates | 1,022,951 | 995,513 | 993,056 | 3,011,520 |
| proposal_action_scores | 532,710 | 654,437 | 634,405 | 1,821,552 |
| proposal_state_evaluations | 38,452 | 42,909 | 41,940 | 123,301 |
| edge_selections | 58,398 | 55,827 | 56,092 | 170,317 |
| transitions | 58,398 | 55,827 | 56,092 | 170,317 |
| verifier_calls | 11,195 | 10,212 | 10,430 | 31,837 |

Each arm's primary ceiling is1,048,576; unspent primary work is25,625,
53,063 and55,520 respectively. Combined usage is3,011,520/3,145,728,
leaving134,208. Each other axis has a deliberately loose per-arm ceiling
204,800,000. All seven unspent totals are retained. Equal caps do not mean
identical realized work. Both two-stream arms used more proposal work despite
fewer legal-action scores; this is accounting, not a wall-clock speed claim.
No unused work was silently reassigned or excluded from the denominator.

## Recovery and evidence boundaries

Original run commit35f3b1b and raw COMMIT remain unchanged. The first analysis
lost its process after a host restart; its completion, exit and progress remain
UNKNOWN, as does the restart trigger. A detailed-record retention risk was
identified, but it was not proven to cause the restart.

Recovery candidate91e6460 added only five files and preserved all480 prior
tracked files. The first qualification stopped before tests because the
temporary socket path was too long (exit1, zero tests). That failure remains
recorded. After explicit approval, an environment-only qualification with a
shorter private path passed1,775 tests, skip0, exit0. No implementation or
manifest change was made between those qualification attempts.

The new recovery ran2026-10-23T17:18:15.752851Z–17:47:55.220187Z and exited0
with postflight PASS. It regenerated the cohort for verification, generatively
replayed all10,240 branches from cell zero, checked6,144 branch prefixes and
2,048 structural blocks, and reproduced the complete unchanged reduction.
Summary and captured stdout match all6,489,859 bytes. The original directory
still has no summary; the new recovery summary lives in its own attempt slot.

The detailed cache peaked at3 cells; measured peak RSS was435,879,936 bytes
(415.6875MiB). Transient checks and compact reductions also allocate memory:
this is not constant total memory, a three-cell RSS bound, or an OOM diagnosis.
Wall time and RSS are diagnostics separate from scientific work.

The [read-only arithmetic script](countdown_feedback_allocation_recovery_20261024.py)
uses only stdlib. It authenticates every COMMIT-bound cell, rebuilds terminal
success/minimum error/readout and all charge totals, checks saved prefix
projections, and independently reconstructs all planned aggregates, exact
source moments and the original readout. The saved-event checker derives from
the earlier diversity observation script; neither imports the experimental
engine or reducer. All results match the complete recovery reduction. This is
an independent implementation by the same agent, not an independent reviewer,
a second experiment, or another generative replay.

## What this changes next

The hypothesis that a fixed3:1 split would retain enough continuation while
capturing complementary successes was **not supported by this primary
development comparison**. Do not promote384/128, declare single16 universally
best, retune ratios on these sources, or turn the secondary+10 into a winner.

A next design should first separate two unresolved questions: whether an
observable pre-decision signal can justify sacrificing continuation, and how
unusable budget remnants/proposal overhead affect a multi-stream policy.
An adaptive or shared-state scheme would change the mechanism and needs its
own invariants, fresh-data plan and approval; hindsight access to first-solve
times is not a deployable allocation rule. These are proposals only. No new
ratio, scheduler, experiment, default, C5/locked evaluation, or provider call
was implemented or executed here.

## Reproduce and audit

From the repository, with the retained local raw files:

```sh
python3 -P -B docs/observations/countdown_feedback_allocation_recovery_20261024.py
```

It writes only stdout and does not call search. The tracked diagnostics contain
the complete output for readers without the ignored raw files.

- [Recovered summary](../qualifications/countdown_feedback_allocation_recovery_20261024.summary.json)
- [Complete arithmetic diagnostics](../qualifications/countdown_feedback_allocation_recovery_20261024.diagnostics.json)
- [Operation and authorization chain](../qualifications/countdown_feedback_allocation_recovery_20261024.execution.json)
- [Result-package review and validation state](../reviews/countdown_feedback_allocation_recovery_result_20261024.md)
