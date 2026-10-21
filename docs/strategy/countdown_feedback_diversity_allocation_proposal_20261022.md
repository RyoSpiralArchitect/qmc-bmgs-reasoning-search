# Step 3: allocation proposal, not a new execution authorization

## Decision from the completed comparison

Keep the diversity mechanism available for development, but do not promote
equal-budget diverse16 as a new default. It produced different first
trajectories in every one of 256 paired blocks at both budgets, yet practical
net exact success versus full continuation was +2/256 at 256 and -1/256 at 512.
Minimum-error wins/losses were 76/95 and 70/103. The high-budget sign changes
under source/seed omissions. No population improvement or optimal split is
established. The [observation note](../observations/countdown_feedback_diversity_development_20261022.md)
retains the complete positive, negative and null results.

The obstacle is no longer the previous experiment's nearly duplicate paths.
At 512, full continuation adds 15 successes after its first half; a second
stream adds 14 successes to that half, three overlapping the full stream's late
successes. Therefore the diversified union gains 11 and loses 12 against the
full stream. Preserving more continuation is a testable hypothesis, not a
deduction that it must improve the union.

## Smallest useful next comparison to preregister separately

Propose one **512-total-budget** development matrix with three fixed policies:

| Policy | Primary key 0 | Secondary key 1 | Purpose |
| --- | ---: | ---: | --- |
| Full continuation | 512 | none | Practical baseline |
| Equal diverse split | 256 | 256 | Current reference |
| Continuation-weighted diverse split | 384 | 128 | One allocation hypothesis |

This 3:1 split is deliberately a single, interpretable, post-result hypothesis,
not an optimized ratio or an outcome-selected winner. Do not scan ratios and
report the best. Keep dense scale 16, proposal, prior, return estimator,
uncertainty, routing, pruning, readout, branch-key construction and no-sharing
semantics unchanged. Split all seven caps according to the declared policy;
both branches execute, repeated work is charged and residual work is not
transferred. Implementation must first test the applicable common-prefix
properties at these new boundaries, rather than assuming the existing 128/256
checks prove the new 384 boundary.

Do **not** apply 3:1 indiscriminately at total 256: its secondary cap would be
64, while all observed secondary exact discoveries in the current low-budget
matrix require 85–111 scores. A ratio should not silently starve the first
complete trajectory. The proposed matrix holds total budget at 512 to isolate
allocation; extending budget, adding an adaptive scheduler or testing a
minimum-viable-trajectory rule would introduce another question.

Even at 512 there is no guaranteed improvement. Six of the current 12 lost
single successes first appear by 384 and six later; six of the 11 truly new
secondary successes appear by 128 and five later. These are descriptive counts
from already observed trajectories, **not counterfactual results for 384/128**.
They explain why both benefit and harm remain plausible. No new allocation
outcome has been estimated or generated here.

## Required design before any execution

- Use a fresh source-unique development cohort, excluding all current and prior
  accepted source multisets and historical identities. Use newly fixed root
  seeds rather than choosing favorable current seeds. Freeze the complete
  recipe, identity exclusions and attempt bounds before generation; retain
  unsolvable/exclusion counts without hardness selection.
- Declare the sample size and precision aim before running. The present 32
  clusters are not a power calculation. Keep source-cluster and repeated-seed
  denominators separate, and avoid claiming confirmation from a small net.
- Make 384/128 minus 512 the primary practical contrast; use 384/128 minus
  256/256 diagnostically. Preserve gains, losses, minimum-error missingness,
  all work axes, source/seed strata and prespecified omission diagnostics.
- Record branch first-exact work, spent/unspent work, complementary successes,
  and lost full-continuation successes. Explicitly separate differing caps from
  equal actual cost; do not infer wall-clock performance.
- Test isolated engine equivalence, seven-axis conservation, stream identity,
  first-trajectory feasibility, subset/prefix claims where applicable and
  fail-closed input/output binding. Retain every cell and require a separate
  process to regenerate the cohort and replay every branch.
- Review and validate the new implementation, freeze its exact plan digest and
  commit, then request new explicit human authorization for one run/analysis.
  The current approval covers neither this implementation nor its execution.

Adaptive allocation, shared caches/posteriors, success-triggered stopping,
learned value changes, further reward tuning, original C5, locked evaluation and
provider calls remain outside this proposal. The deliverable of this step is
the decision and bounded next-study hypothesis, not code or another experiment.
