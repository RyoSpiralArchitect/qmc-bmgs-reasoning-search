# Diversity exists; equal splitting does not establish an improvement

The fixed development comparison and separate-process full generative replay
completed: 1,536 cells, 2,560 branch searches, 768 budget-prefix pairs and 512
structural blocks. All three arms used the same dense-16 policy. There are
32 source clusters and eight seeds, not 256 independent sources per arm/budget.
This is exploratory evidence, not original C5, locked evaluation, QMC-versus-IID,
or a provider/LM evaluation. `winner` and `scientific_decision` remain null.

## Practical result

Each success denominator below is 256 task-seed blocks. Gains and losses compare
diverse16 with the full-budget single16 in the same block.

| Total primary cap | single16 | paired16 duplicate halves | diverse16 distinct halves | Gains / losses | Net |
| --- | ---: | ---: | ---: | ---: | ---: |
| 256 | 15/256 | 9/256 | 17/256 | 8 / 6 | +2/256 |
| 512 | 30/256 | 15/256 | 29/256 | 11 / 12 | -1/256 |

The keyed streams changed behavior: diverse16 has **0/256 identical first
trajectories and 0/256 identical whole action sequences at both budgets**;
paired16 has 256/256 of each. Different paths are therefore observed, but they
do not establish better full-budget exact success. The counts are not a proof
of probabilistically independent streams or population effects.

All 1,536 cells have at least one verified terminal. Missing minimum error is
zero in this matrix, while single-arm overlap remains explicitly null because
there is no second branch. No null was converted to an observed zero.

## Where the success difference comes from

The shared primary half-budget branch makes paired16 a subset control.
Its nonloss against diverse16 is structural, not a performance discovery.

| Budget | Primary-half successes | Extra successes from full continuation | Secondary-only successes | Secondary rescues a late full success | Truly new vs full | Full successes still lost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 256 | 9 | 6 | 8 | 0 | 8 | 6 |
| 512 | 15 | 15 | 14 | 3 | 11 | 12 |

At 512, the arithmetic is `29 = 15 + 14`, while `30 = 15 + 15`.
Of the 14 secondary-only successes, three overlap the later full-continuation
successes. Thus the practical comparison is 11 gains and 12 losses, not 14
gains. No diverse block had both branches succeed: its 29 successes are 15
primary-only and 14 secondary-only. The low-budget 17 are similarly 9 + 8.

The lost full successes were first observed at these legal-action-score counts:

- Budget 256, half cap 128: **187, 193, 201, 225, 244, 253**.
- Budget 512, half cap 256: **292, 317, 330, 331, 338, 363, 393, 406, 417, 425, 440, 499**.

All losses occur after the half-budget cutoff. The exact matched-prefix checks
support a concrete budget-truncation account for the saved primary trajectories;
they do not isolate every proposal, caching or scheduling mechanism. This is
failure to reach an eventual success, not forgetting an already found solution.

Additional secondary successes at 512 first appear at
**85, 88, 98, 99, 105, 111, 136, 165, 217, 223, 253** scores.
Six of these 11 practical gains occur by 128, and five require more. Retaining
more primary continuation would therefore have a real competing cost; the
current data do not demonstrate an optimal split.

## Minimum-error and work tradeoffs

Exact success is sparse. Minimum verified terminal error favors full
continuation more often than equal diversified splitting:

| Budget | diverse vs single error wins | ties | losses | missing |
| --- | ---: | ---: | ---: | ---: |
| 256 | 76 | 85 | 95 | 0 |
| 512 | 70 | 83 | 103 | 0 |

Against duplicate halves, diverse16 improves minimum error in 119/256 and
124/256 blocks, with no error losses. That union/subset advantage is not the
relevant full-continuation superiority claim. Paired16 versus single16 has
0 error wins and 132/151 losses at the two budgets, respectively.

Caps are matched, **actual work is not identical**. The full seven-axis table
is retained below; columns use exact summed charged work across 256 blocks.

| Budget / arm | Legal scores | Perturbation coordinates | Proposal scores | Proposal states | Edge selections | Transitions | Verifier calls |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 256 single16 | 61554 | 61554 | 41008 | 2571 | 3292 | 3292 | 603 |
| 256 paired16 | 57384 | 57384 | 49644 | 2740 | 3020 | 3020 | 532 |
| 256 diverse16 | 57562 | 57562 | 49653 | 2729 | 3017 | 3017 | 525 |
| 512 single16 | 127722 | 127722 | 65478 | 4576 | 6919 | 6919 | 1324 |
| 512 paired16 | 123108 | 123108 | 82016 | 5142 | 6584 | 6584 | 1206 |
| 512 diverse16 | 123220 | 123220 | 81885 | 5131 | 6585 | 6585 | 1211 |

Primary usage totals **550550/589824**, leaving 39274 unspent. Unused work is
not transferred. At 512, diverse16 uses 4502 fewer legal scores but 16407 more
proposal scores than single16. Isolated restarts repeat proposal work, which is
charged. Do not infer wall-clock speed or equal actual compute from matched
caps or one scalar budget. All secondary guards remained nonbinding.

## Source and seed sensitivity

At 256, eight gains span seven sources and five seeds; six losses span five
sources and three seeds. Leave-one-source-out net is 0..+3/248, and
leave-one-seed-out net is 0..+6/224. Neither is a confidence interval.

At 512, 11 gains span nine sources and all eight seeds; 12 losses span nine
sources and seven seeds. Leave-one-source-out net ranges **-2..+2/248**;
leave-one-seed-out ranges **-4..+1/224**. The sign is sensitive to these
omissions. Source slot 15 contributes three losses and no gains at 512; omitting
it changes net -1 to +2, which is a sensitivity description, not permission to
exclude that source.

| Seed | 256 gains / losses / net | 512 gains / losses / net |
| --- | ---: | ---: |
| 32768 | 0 / 4 / -4 | 1 / 3 / -2 |
| 32769 | 1 / 0 / +1 | 1 / 2 / -1 |
| 32770 | 2 / 1 / +1 | 3 / 0 / +3 |
| 32771 | 2 / 0 / +2 | 2 / 1 / +1 |
| 32772 | 0 / 0 / 0 | 1 / 3 / -2 |
| 32773 | 1 / 0 / +1 | 1 / 1 / 0 |
| 32774 | 2 / 1 / +1 | 1 / 1 / 0 |
| 32775 | 0 / 0 / 0 | 1 / 1 / 0 |

All 32 source strata, eight seed strata, omissions, block identities and
first-discovery observations are in the diagnostics JSON, including zero and
negative strata. Do not pool the nested budgets or select the favorable one as
confirmation. No p-value, causal population claim or winner is introduced.

## Decision and evidence

**Share with caveats within the reviewed scope:** stream diversity and
complementary solutions are observed, but equal splitting is not supported as
a replacement for full continuation. The next proposal isolates allocation
while retaining the same diversity mechanism; see the
[allocation proposal](../strategy/countdown_feedback_diversity_allocation_proposal_20261022.md).
It is a post-result hypothesis, not an authorized new experiment or implemented
scheduler. In particular, a quarter of 256 is only 64, below every observed
secondary exact discovery in this study; a uniform 3:1 rule is not justified.

Generation made 37 attempts: 32 accepted, one excluded source multiset, and four
unsolvable tasks. Eligibility was fixed before generation; there was no
outcome/hardness selection or retained witness-driven policy. Every accepted
source is new relative to the 252 excluded source identities.

Reproduction: `python3 -P -B docs/observations/countdown_feedback_diversity_development_20261022.py`
from the repository, with the retained local raw files present. The script uses
only the standard library, authenticates every COMMIT-bound cell, recomputes
terminal flags, readout, all charge deltas, path diagnostics, structural/prefix
checks, all planned strata/omissions and the entire saved reduction. It imports
neither experiment reducers nor search engines. This is an independent
implementation, **not an independent reviewer or another generative replay**.
An initial style-only Ruff finding was corrected in the diagnostic script; its
first output remains retained and all non-source numerical contents match the
final output. The actual experiment and analyzer were never retried.

- [Frozen plan](../preregistrations/countdown_feedback_diversity_development_20261022.plan.json)
- [COMMIT](../qualifications/countdown_feedback_diversity_development_20261022.commit.json)
- [Complete saved summary](../qualifications/countdown_feedback_diversity_development_20261022.summary.json)
- [Independent recomputation and allocation diagnostics](../qualifications/countdown_feedback_diversity_development_20261022.diagnostics.json)
- [Operation and approval chain](../qualifications/countdown_feedback_diversity_development_20261022.execution.json)
- [Result-package review and validation status](../reviews/countdown_feedback_diversity_development_result_20261022.md)

Candidate full validation passed 1,718 tests at 3082cff. All experimental work
ran at records-only descendant cbc8abc. Result-package full validation has its
own recorded commit/status; these stages must not be conflated with hosted CI.
