# Feedback portfolio development results and allocation costs

Neither proposed intervention improved exact success in this fixed development
comparison. At 512 legal-action scores, the original strong-feedback control
solved 6 of 64 task-seed blocks, exact-only and weaker feedback each solved 3,
and the protected half-and-half portfolio solved 1. The portfolio duplicated
most of its two channels' choices while cutting each channel's depth of search.
These results motivate testing diversity and allocation separately, not adopting
the protected recipe as an improvement.

The [fixed plan](../preregistrations/countdown_feedback_portfolio_development_20261020.plan.json)
was approved before task generation. Ten generator attempts produced eight
accepted, source-unique solvable tasks and two identity exclusions, without
hardness or observed-outcome selection. Eight seeds, two budgets and four arms
give 512 cells, 640 branch searches and 64 paired blocks per arm and budget.
There are **eight source clusters**, not 64 independent tasks. All branches were
replayed in a separate process; all 256 same-arm budget-prefix pairs matched.

## Exact success and paired differences

| Arm | Budget 256 | Budget 512 |
| --- | ---: | ---: |
| exact, exact-success-only feedback | 1/64 | 3/64 |
| dense16, original strong approximate feedback | 1/64 | 6/64 |
| calibrated1, weaker approximate feedback | 1/64 | 3/64 |
| protected1, isolated exact and calibrated half budgets | 1/64 | 1/64 |

All four predeclared contrasts have zero exact gains and losses at budget 256.
At budget 512:

| Intervention minus comparator | Gains | Losses | Net per 64 | Minimum error win / tie / loss / missing |
| --- | ---: | ---: | ---: | --- |
| calibrated1 minus dense16 | 0 | 3 | −3 | 3 / 53 / 8 / 0 |
| protected1 minus calibrated1 | 0 | 2 | −2 | 0 / 24 / 40 / 0 |
| protected1 minus exact | 0 | 2 | −2 | 0 / 23 / 41 / 0 |
| dense16 minus exact | 3 | 0 | +3 | 9 / 51 / 4 / 0 |

The low-budget minimum-error counts are respectively 3/58/3/0,
0/26/37/1, 0/26/37/1 and 4/58/2/0. The missing pair is retained, not
treated as a perfect answer or removed from the denominator. All outcomes,
source and seed strata, and omission checks are in the
[complete summary](../qualifications/countdown_feedback_portfolio_development_20261020.summary.json).

## Weakening feedback removed useful steering in these observations

At high budget, calibrated1 and exact chose the same complete action sequence
in 54/64 blocks; dense16 and exact did so in 26/64. At low budget the counts
are 62/64 and 49/64. Here an action sequence includes state, action, trajectory
index and depth, not posterior values or the full trace bytes.

All three strong-feedback gains occur on two sources: slot 2 at seed 16385,
and slot 3 at seeds 16384 and 16391. Calibrated1 ends these cases at minimum
errors 20, 18 and 30 instead of zero. Dense16 reaches its first exact solution
after 471, 420 and 271 legal-action scores. Its positive net remains +1 to +3
out of 56 blocks after omitting any one source, and +2 to +3 after omitting
any one seed. This is descriptive robustness within eight sources, not a
population significance result.

The old E4 losses do not establish that strong feedback is generally harmful:
the old repeatedly inspected single-source PUBLIC observation and this fresh
multi-source development observation differ. Nor do these three gains establish
that scale 16 is generally optimal. The evidence does reject the simple local
hypothesis that replacing scale 16 with scale 1 would improve this matrix.

## The protected channels repeated work rather than complementing each other

At both budgets the two protected channels have identical complete action
sequences in 62/64 blocks and identical first-trajectory choices in all 64.
Their one successful block is shared by both channels; there are zero
exact-only or calibrated-only successes. Same-seed pairing plus little early
feedback divergence gives little observed diversity in this recipe.

At total budget 512, each protected channel's decision and charge events match
its standalone budget-256 counterpart in all 64 blocks. Secondary caps differ
but never bind. The two exact-only successes lost by the portfolio are slot 1,
seed 16386 and slot 3, seed 16385. The full-budget baseline first finds them at
374 and 331 scores, beyond its protected allocation of 256. The protected
answers have minimum errors 109 and 190. These are successes never reached,
not solutions that were found and forgotten.

At total budget 256, slot 4, seed 16385 has no verified terminal in either
protected channel. Each spends 126 of its 128 scores and cannot afford the next
three-score action. Its returned answer and minimum error remain null. A larger
total budget is not silently substituted to repair the observation.

## Work and fragmentation

Every branch stops on the primary score cap; no secondary cap invalidates a
cell. Total primary work is 188,370 of the predeclared maximum 196,608. Other
axes remain fully reported; matching primary caps is not equal wall time or
equal proposal cost.

| Arm | Unused primary scores at 256 | Unused at 512 | Verified terminals at 256 | Verified terminals at 512 |
| --- | ---: | ---: | ---: | ---: |
| exact | 788 | 782 | 157 | 350 |
| dense16 | 740 | 782 | 160 | 349 |
| calibrated1 | 798 | 759 | 157 | 351 |
| protected1 | 2,003 | 1,586 | 130 | 314 |

These are totals over 64 blocks, not means. Two isolated channels also pay for
their own proposal caches: at high budget protected1 uses 21,643 proposal-action
scores versus 19,150 for exact and 16,962 for dense16, despite producing fewer
verified terminals. The traces support duplication and fragmented remaining
budget as observed costs. They do not isolate the causal contribution of each
cost from the changed feedback mix and allocation.

## Next hypotheses without changing this attempt

1. Separate diversity from reward scaling. A controlled next design could compare
   two paired channels, independently keyed channels and one continued channel
   under the same total seven-axis caps. Report overlap and complementary
   successes; changing seeds alone is not assumed to improve performance.
2. Test allocation that preserves useful continuation. Predeclare a scheduler
   that avoids repeatedly paying the same startup work and accounts for every
   transferred unit. Retain a full-budget single-channel control. Neither
   full-baseline protection nor cost-free cache sharing may be claimed.
3. Keep exact-success evidence and approximate-progress evidence explicit in
   the inference interface. A separate success signal and bounded progress
   signal are a design hypothesis, not a result of this four-arm comparison.
   Changing the reward, prior, uncertainty term and scheduling simultaneously
   would make the next result difficult to interpret.

The current winner and scientific decision remain null. This provider-free IID
development comparison is not a QMC comparison, an LM evaluation, C5 approval
or a locked-set result. No additional experiment or parameter sweep followed
these outcomes.

## Reproducible accounting

The [read-only recount](countdown_feedback_portfolio_development_20261020.py)
uses only the standard library and COMMIT-bound raw files. It imports no search
engine, performs no generative replay, recomputes success and minimum errors
from terminal flags, sums every charge delta, and reproduces the entire planned
reduction including source, seed and omission strata. It also records the
posthoc channel, missingness and discovery-cost diagnostics above in
[diagnostics JSON](../qualifications/countdown_feedback_portfolio_development_20261020.diagnostics.json).

Run `python3 -B docs/observations/countdown_feedback_portfolio_development_20261020.py`
from the repository to reproduce that JSON on stdout while the local raw files
remain available. The [execution record](../qualifications/countdown_feedback_portfolio_development_20261020.execution.json)
binds approval, source, run, separate analysis, raw hashes and byte-identical
review mirrors. This is an operator review plus independent aggregation code,
not an independent human or model review.
