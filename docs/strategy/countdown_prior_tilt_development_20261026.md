# Prior-anchored return tilt development, 2026-10-26

## Research decision and authority

Following the completed search-value study and merged PR35/36, the next question
is whether a prior-anchored stochastic policy can be competitive with fixed
PUCT, with return use isolated inside that new policy. The old observed primary
was negative and its precision-first readout was IMPRECISE. Neither is revised.
The old cohort is excluded from new generation, not used for coefficient tuning.

Ryō directly answered the proposal to (1) fix a prior-preserving candidate and
(2) compare it, its mean-off control and fixed PUCT on fresh sources:
「うお！良きだね❤️‍🔥これでまず１ー＞２まで行こうか🌀」.
This delegates candidate selection, qualification, registration and one new
development comparison through full separate-process analysis. It is recorded
as `delegated_candidate_selection`, not fabricated exact-digest approval of a
commit that did not exist at consent. The separate operator receipt binds the
actual proposal/instruction, frozen candidate commit and executable plan digest.
The plan's authorization=false is a candidate-time snapshot, not the sole
authority. No old one-run approval is reused as authority for this new study.

There is one candidate, one run and one separate all-cell generative analysis.
Failure stops for human direction; no automatic retry, resume, replacement slot,
extra condition, coefficient sweep, new default, provider, original C5 or locked
evaluation. Merge and a later QMC/transfer experiment are not included.

## One fixed selector

For action a with proposal probability p(a) and stored scale16 terminal mean Q(a):

```
g(a) = -log(-log(u(a)))
score(a) = log p(a) + Q(a) + g(a)          prior-tilt16
score(a) = log p(a) + 0.0 + g(a)           prior-mean-off
```

All three coefficients are fixed at one, except the diagnostic mean coefficient
zero. There is no public beta/temperature parameter, sweep, visit-dependent
Gumbel scale, action-dimension normalization or initial greedy trajectory.
With independent continuous uniform draws this selects with conditional law
`q(a) = p(a)*exp(Q(a))/sum_b p(b)*exp(Q(b))`. Equal means recover p. Since Q is
in [0,1], the learned term changes pairwise prior odds by at most exp(1); this
unit bounded effect is a simple pre-outcome design choice, not an optimum.
The implementation uses finite keyed uniforms and binary64 arithmetic; it does
not claim exact continuous-distribution sampling or a Bayesian posterior.
Canonical action-index tie-breaking is retained.

The categorical Gumbel-Max construction is described in
[Kool et al., ICML 2019](https://proceedings.mlr.press/v97/kool19a.html).
This candidate uses ordinary with-replacement local draws, not that paper's
sequence-level without-replacement algorithm, Gumbel AlphaZero, or its claimed
task performance. No policy-improvement guarantee is transferred here.

The original proposal, scale16 terminal reward `16/(16+absolute_error)` (exact=1),
terminal verification, updates of visits/mean/m2, task namespaces, DAG, work
ledger and stopping semantics remain. Unvisited means are zero. Visits/m2 remain
stored and updated but do not directly affect new selection. The mean-off
control changes selection use only, not updates or keyed material.

The additive adapter reuses the frozen transactional engine. Its material source
still generates and stores authenticated uniform/normal pairs and charges the
existing coordinate axis. Gumbels are computed directly from the original
uniforms, never by applying a normal CDF to clipped normals. Normal values are
generated/charged but unused for selection; this redundant computation is not a
new efficiency claim. New method/configuration/event identities prevent legacy
replay from accepting the policy by relabeling. Replay authenticates unchanged
material through a metadata projection, then runs the actual new selector from
empty state and requires all bytes to match.

Fixed PUCT remains the existing c_puct=1, binary-exact-terminal policy, without
root noise. Its inner trace is byte-identical to the original control. Thus the
primary compares complete policies, not only a noise distribution. Switching
probability prior to log prior and removing visit-scaled noise are joint changes;
this study cannot uniquely attribute a change versus old single16 to either.

## Fixed matrix and fresh identities

Generate the first256 eligible solvable source-multiset-unique Countdown tasks:
six inputs1..10, target100..999, generator26102601, maximum10,000 attempts.
Exclude the authenticated historical registry and64/8/32/256 cohorts, the latest
128-source search-value cohort, and the conservative tracked-Python literal
fixture superset. Selection never uses search success, difficulty or witnesses.
Static literal extraction does not prove arbitrary dynamic fixture discovery.

Roots262144..262147 use branch0 of the existing versioned stream derivation.
All registered historical seeds and fixture seeds are excluded, with a collision
blocking the fixed plan instead of choosing a replacement. Common material is
shared only at actually common state/visit/action coordinates; divergent whole
trajectories are not claimed to remain paired random-number sequences.

`256 × (4 prior-tilt16 + 4 prior-mean-off + 1 PUCT) = 2,304 cells`.
The sole primary cap is512 legal-action scores per cell, maximum1,179,648 total.
Each other axis remains100,000; binding a non-primary guard invalidates the
attempt and preserves its partial raw. No budget redistribution, repeated
deterministic baseline, shared state or hidden use of unspent work. The paired
methods alternate order, with source-rotated pair/PUCT groups.

The larger fixed256-source cohort provides more source-level observations than
the previous study without trying sizes until a favorable decision appears.
It does not guarantee a 0.05 half-width or power for a +0.02 uplift. Four roots
are within-source repetitions; one PUCT row is not four independent observations.

## Fixed readout and evidence

Only `prior-tilt16-minus-puct` is primary. Average the four rooted exact-success
flags within each source, subtract that source's single PUCT outcome, then use
the exact rational source mean and sample variance (denominator255).
Reuse the existing `mean +/- 2*source_sd/sqrt(n)` approximate model interval and
ordered gates: incomplete/invalid; fewer than64 or zero variance => null interval
UNRESOLVED; half-width>0.05 => IMPRECISE; lower>+0.02 =>
PROMISING_FOR_FRESH_CONFIRMATION; upper<=+0.02 => NO_PRACTICAL_UPLIFT_SIGNAL;
otherwise UNRESOLVED. Diagnostic mean-on-minus-mean-off never replaces primary.
Source uniqueness with deterministic filtered non-replacement generation does
not establish independence, exchangeability or interval coverage. Preserve null
winner/scientific_decision, negative results and missing terminals.

Retain every source/root/cell's actual/unspent seven-axis work, first exact work
or no-hit censoring, minimum error, terminal/revisit counts, gain/loss/net and
source/root leave-one-out sensitivity (not confidence intervals). Proposal-
internal work reconstruction stays separate from ledger work and search timing.
Same-history mean-toggle scores and the first divergent choices are passive
diagnostics, not counterfactual rollouts. Equal caps are not equal total compute.

Planning is outcome-blind, seals source/runtime/exclusion bytes, and generates
no cohort. A clean exact candidate and full `scripts/validate.py` PASS/skip0 are
required before execution. Exclusive run/analysis fences and complete membership
checks are reused from the previous harness, not a new budget-control framework.
Separate analysis regenerates the cohort, replays every cell byte-identically,
and reconstructs all source-level reductions and1,024 paired choice diagnostics.
One budget means zero cross-budget prefix pairs. Outer pair cache2 is not a
total-RSS bound. Results require separate saved-event checks and documentation;
the result package is validated separately from candidate qualification.

Full qualification/log receipts and human authority remain separate from focused
unit fixtures, same-agent review, independent implementation checks, hosted CI
and external review approval. Old raw, failures, manifests and pending snapshots
are not rewritten. QMC action sampling, semantic routing and no-retuning transfer
are later questions, only after this search-strength gate.
