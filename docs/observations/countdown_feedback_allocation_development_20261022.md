# More continuation narrows the equal-split deficit in this cohort

The fixed **384/128** allocation reached **46/512** exact successes, compared
with **48/512** for full continuation and **40/512** for the equal split. Against
full continuation it gained three paired successes and lost five, a net
**−2/512**. Against equal splitting it gained 14 and lost eight, a net +6/512.
The primary comparison provides no observed improvement over full continuation
in this development cohort. No new default or optimal split is selected.

Exactly one authorized run and one separate-process complete analysis/replay
completed: **1,536 cells, 2,560 branch searches per pass, 2,048 prefix pairs
and 512 structural blocks**. The source, dense scale 16, shared seeds, seven
caps and prespecified contrasts stayed fixed. The 64 source clusters have
eight repeated seeds each; the 512 blocks are not 512 independent sources.

## Exact success, paired gains and losses

| Allocation | Exact successes | Observed fraction |
| --- | ---: | ---: |
| 512/0 full continuation | 48/512 | 9.375000% |
| 256/256 equal split | 40/512 | 7.812500% |
| 384/128 weighted split | 46/512 | 8.984375% |

The first contrast below is primary. Weighted versus equal is diagnostic;
equal versus full continuation is retained as a reference. Minimum-error
columns are wins / ties / losses / missing, each with denominator 512.

| Contrast | Gains | Losses | Net | Minimum-error W / T / L / missing |
| --- | ---: | ---: | ---: | ---: |
| weighted16 − single16 | 3 | 5 | -2/512 | 69 / 334 / 109 / 0 |
| weighted16 − equal16 | 14 | 8 | +6/512 | 121 / 290 / 101 / 0 |
| equal16 − single16 | 11 | 19 | -8/512 | 139 / 185 / 188 / 0 |

Every cell and every one of the 2,560 branches reached at least one verified
terminal. Minimum-error missingness is zero. Single-branch overlap remains
null rather than being converted to an observed zero. Both split arms have
0/512 identical primary-versus-secondary first trajectories and 0/512 identical
whole action sequences. Different trajectories do not prove statistically
independent streams or a practical improvement.

## What the allocation changes

| Arm | Primary successes | Secondary successes | Both succeed | Union |
| --- | ---: | ---: | ---: | ---: |
| 512/0 | 48 | absent | not applicable | 48 |
| 256/256 | 28 | 13 | 1 | 40 |
| 384/128 | 43 | 4 | 1 | 46 |

Moving primary capacity from 256 to 384 adds 15 primary successes, while
reducing secondary capacity from 256 to 128 removes nine secondary successes.
One of those lost secondary successes is recovered by the longer primary;
the practical weighted-versus-equal comparison therefore has **14 gains and
eight losses**, not 15 gains and nine losses. Fourteen of the equal split's
19 losses against full continuation disappear; eight of its 11 new successes
against full continuation also disappear. These are matched observed traces,
not estimates for another unrun allocation.

At 384/128, the primary has 43 successes, the secondary adds three successes
not found by the primary, and its fourth success overlaps a primary success:
`46 = 43 + 4 − 1`. The three secondary-only successes are all practical gains
against full continuation. They do not rescue any of the five late full-branch
successes that are lost. At 256/256, 12 secondary-only successes include one
rescue of a late full success and 11 practical gains: `40 = 28 + 13 − 1`.

Weighted allocation's five lost full successes first occur at legal-score
counts **395, 405, 455, 465, 466**, all beyond 384. Its three practical
secondary gains first occur at **61, 69, 121**, within 128.
The equal split's lost full successes occur at
**276, 281, 297, 297, 299, 306, 321, 334, 336, 339, 347, 362, 369, 379, 395, 405, 455, 465, 466**; its practical secondary gains occur at
**61, 69, 121, 146, 177, 178, 202, 208, 221, 229, 250**. All 19 equal-split losses are beyond its primary
cap 256. The first-hit evidence and matched event/work prefixes support
capacity truncation of these saved primary searches, not forgetting of an
already reached exact result.

Full-branch first-exact counts at the fixed 128, 256, 384 and 512 boundaries
are **8, 28, 43 and 48**. The secondary stream finds four successes by 128 and
13 by 256. These are descriptive counts from actual traces; they do not choose
a new ratio. All 512 secondary branches capped at 128 reached a first terminal,
with first-terminal legal-score usage ranging from 52 to 127.
That is observed feasibility for this cohort, not a universal guarantee.

All four applicable prefix relations passed for every block: primary
256→384, 384→512 and 256→512, plus secondary 128→256. The analysis also checked
primary-success inclusion in each union and seven-axis cap conservation.

## Source and seed interpretation

Source means are paired exact-success differences averaged over the eight
fixed seeds. The standard errors below are descriptive source-level summaries,
not confidence intervals, hypothesis tests or population confirmation.

| Contrast | Mean difference (percentage points) | Descriptive SE (percentage points) | Positive / tied / negative source means |
| --- | ---: | ---: | ---: |
| weighted16 − single16 | -0.390625 | 0.479680 | 2 / 58 / 4 |
| weighted16 − equal16 | +1.171875 | 0.992858 | 10 / 49 / 5 |
| equal16 − single16 | -1.562500 | 1.096051 | 7 / 43 / 14 |

Weighted-versus-full gains span three sources and two seeds; losses span five
sources and four seeds. Equal-versus-full gains span nine sources and seven
seeds; losses span 17 sources and all eight seeds. All 64 source strata and
all fixed-seed strata remain in the JSON summaries, including offsetting gains
and losses within a source. No source was dropped based on its outcome.

| Contrast | Leave one source out: net / remaining blocks | Leave one seed out: net / remaining blocks |
| --- | ---: | ---: |
| weighted16 − single16 | -3..-1 / 504 | -3..+0 / 448 |
| weighted16 − equal16 | +3..+8 / 504 | +3..+7 / 448 |
| equal16 − single16 | -10..-5 / 504 | -9..-5 / 448 |

The weighted-versus-full deficit remains negative under each single-source
omission and can become a tie under a single-seed omission. Weighted versus
equal stays positive under these prespecified omissions. These finite-sample
sensitivity checks neither authorize omission nor establish a population effect.

| Root seed | weighted − full: G / L / net | weighted − equal: G / L / net | equal − full: G / L / net |
| --- | ---: | ---: | ---: |
| 65536 | 0 / 0 / +0 | 1 / 1 / +0 | 1 / 1 / +0 |
| 65537 | 0 / 1 / -1 | 1 / 0 / +1 | 0 / 2 / -2 |
| 65538 | 0 / 0 / +0 | 2 / 1 / +1 | 1 / 2 / -1 |
| 65539 | 0 / 0 / +0 | 1 / 2 / -1 | 2 / 1 / +1 |
| 65540 | 0 / 2 / -2 | 2 / 3 / -1 | 3 / 4 / -1 |
| 65541 | 2 / 1 / +1 | 1 / 0 / +1 | 2 / 2 / +0 |
| 65542 | 1 / 1 / +0 | 3 / 0 / +3 | 1 / 4 / -3 |
| 65543 | 0 / 0 / +0 | 3 / 1 / +2 | 1 / 3 / -2 |

## Actual work and matched caps

Each arm has 512 cells with legal cap 512 per cell, or 262,144 in total; each
other axis has cap 100,000 per cell, or 51,200,000 per arm. Both branches run
even after success. Repeated proposal work is charged and residual work is
never transferred. All secondary guards remained nonbinding.

| Arm | Legal scores | Perturbation coordinates | Proposal scores | Proposal states | Edge selections | Transitions | Verifier calls |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| single16 | 255,927 | 255,927 | 132,265 | 9,637 | 14,751 | 14,751 | 2,823 |
| equal16 | 249,164 | 249,164 | 163,626 | 10,839 | 14,132 | 14,132 | 2,608 |
| weighted16 | 248,672 | 248,672 | 157,883 | 10,516 | 14,177 | 14,177 | 2,627 |

One search pass used **753,763/786,432 legal scores**,
leaving **32,669 unspent**: 6,217 for full continuation, 12,980 for equal and
13,472 for weighted. Across all arms the other charged totals are 753,763
perturbation coordinates, 453,774 proposal scores, 30,992 proposal states,
43,060 edge selections, 43,060 transitions and 8,058 verifier calls; each has
the declared cap 153,600,000. The generative replay reproduces the same search
ledgers; combined run-plus-replay legal charges are **1,507,526**
against ceiling 1,572,864. Material regeneration, trace validation, generation,
report arithmetic and qualification overhead are outside those search ledgers.

Weighted uses 7,255 fewer legal scores than full continuation but **25,618 more
proposal scores**. Its actual cost therefore cannot be summarized as equal
compute, free diversity or a measured speedup. No wall-clock comparison of the
arms is claimed. The complete work and unspent-work vectors remain in the data.

## Cohort, execution and evidence

Generation accepted the first 64 eligible source-unique solvable tasks from
**92 attempts** using the frozen seed 26102231. The 28 rejected attempts comprise
17 unsolvable tasks and 11 pre-excluded source multisets, with zero duplicate
task/source rejections. All rejection identities and reasons remain in the
cohort record. The 354 task / 288 source exclusion inventories and 2,000-attempt
bound were unchanged; no witness, hardness ranking or search outcome selected
the cohort. Solvability conditioning and the deterministic generator constrain
generalization despite fresh source identities.

Human authorization was recorded from the explicit 2026-10-22 00:32:39 UTC
decision. The run and separate analysis both used operation commit `04bbe3c5bcf7380fc1b889b4e8a1de5598a19aae`,
which preserves qualified candidate `4795f91686de2715696e689d52661976d8d57ad2`
and v3 plan `18f4dd53afd152ef88618e92091e822d56111b6ad04bb67c0aed5755b90da9ed`. The run receipt completed at 00:45:44 UTC and analysis
at 00:52:05 UTC. These timestamps include capture/validation overhead, not an
arm-level runtime experiment. No retry, resume, extra budget or ratio scan ran.

Before/after checks preserve 489 operation tracked files, 5,808 original files,
20 original directory memberships, six absent historical study/production slots,
32 earlier local evidence files across six directories, and all 58 frozen
source references. The original proposal filename and historical bytes remain
unchanged. The original failed qualification and interruption evidence remain.

A separate stdlib-only report checker recomputed every cell summary from saved
events, every planned reduction, all 2,048 prefixes and 512 structural blocks;
the complete reduction matched the frozen analyzer byte-for-byte. It imported
no engine/reducer, generated no cohort and performed no additional search or
generative replay. This is an independent reduction implementation, not an
independent reviewer. Result-package full repository qualification follows in
a separate immutable record; this observation note alone does not claim it.

- [Frozen v3 plan](../preregistrations/countdown_feedback_allocation_development_20261022.v3.plan.json)
- [Approval](../qualifications/countdown_feedback_allocation_development_20261022.approval.json)
- [Cohort and retained rejections](../qualifications/countdown_feedback_allocation_development_20261022.cohort.json)
- [COMMIT / raw cell manifest](../qualifications/countdown_feedback_allocation_development_20261022.commit.json)
- [Complete analysis](../qualifications/countdown_feedback_allocation_development_20261022.summary.json)
- [Capture and preservation receipt](../qualifications/countdown_feedback_allocation_development_20261022.execution.json)
- [Independent arithmetic diagnostics](../qualifications/countdown_feedback_allocation_development_20261022.diagnostics.json)
- [Read-only recomputation script](countdown_feedback_allocation_development_20261022.py)

The raw 1,541-file output set stays local and ignored, with every byte bound by
the manifests. This result is model-free, bounded development evidence. It is
not original C5, locked evaluation, a provider/LM result or a QMC-versus-IID
comparison. No new default, release, deployment or PR31 merge is authorized by
these observations.
