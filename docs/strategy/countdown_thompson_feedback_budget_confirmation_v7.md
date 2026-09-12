# Countdown feedback × budget v7: source-disjoint replication design

Scientific recipe fixed: 2026-09-13. Evidence base:
`aabf9ef55829ca2723d3c3504ff71c0a49059ad2`.

## Status, question and claim ceiling

This is **design only**, not a cohort seal, runner, production analyzer,
qualification receipt or execution authorization. No new task, solvability
calibration, search trace or outcome is generated here. v7 names the experiment;
the underlying search method remains the unchanged v5 method.

The [v6 development observation](../observations/countdown_feedback_budget_v6_development_20260910.md)
found arm counts `(0,0,3,5)` over 48 task/seed blocks: interaction and high-budget
uplift `2/48`, two rescued task/seed pairs on two task identities, and no lost
exact successes. High-budget minimum-error comparisons were `7/39/2` wins/ties/
losses. The development result remains selection evidence, including its adverse
cases; it is never pooled into the new primary denominator.

The confirmation question is narrowly operational:

> On a separately sealed, source-disjoint 64-task cohort, does the unchanged
> feedback × budget comparison reproduce the previously fixed effect floor,
> task breadth, exact-success guard and leave-one-task-out stability?

“Confirmation” here means **finite-cohort replication against an engineering
screen**, not a significance test or a population-performance guarantee. No
p-value, confidence interval, bootstrap, randomization inference, power claim,
causal mediation, general intelligence gain, QMC superiority or locked-128 result
is licensed by this design. A positive result must be named
`SOURCE_DISJOINT_REPLICATION_SCREEN_PASS`, with that limited meaning visible.
It is not permission to run anything else.

## Fixed factors and resource envelope

Increase distinct problem identities, not seeds on the already observed
12 problems. Keep the method, proposal, four exploration seeds and four arms
unchanged so that the new comparison changes the cohort, not the scientific
intervention. Using the same seed integers does not reuse mutable search state;
the unchanged random key also contains task/state/action/visit identity.

| Component | Fixed value |
| --- | --- |
| Experiment identity | `feedback_budget_confirmation_64_seed_26091301/v1` |
| Future production domain | `qmc-bmgs-countdown-thompson-feedback-budget-confirmation/v1` |
| Task count | 64, unique in both full-task and source-multiset identity |
| Generator / seed / maximum attempts | `sha256-counter-mod/v1` / `26091301` / `10000` |
| Rules / ranges | existing Countdown-D6 positive integers and exact division; six inputs `[1,10]`, target `[100,999]` |
| Acceptance | unchanged exhaustive-solvability filter, generator order, no hardness filter |
| Exploration seeds in order | `8192,8193,8194,8195` |
| Feedback scales / primary budgets | `0,16` / `256,512` legal-action scores |
| Search / proposal | unchanged dimension-normalized scaled dense Thompson v5, IID only / `greedy_rollout_target_error/v1` |
| Prior bonus / posterior SD scale | `1.0 / 1.0` |
| Backup | unchanged reverse Welford, discount one, no greedy anchor |
| Cell order | task acceptance order, budget, scale, exploration seed |

The new generation seed is a date-coded design choice made before any new
generation, not the best of several seeds. Failure to seal 64 accepted tasks
within 10,000 attempts stops this recipe; no changed seed, relaxed exclusion,
extended attempt count or replacement cohort is allowed without a separately
reviewed amendment that preserves the failure.

The matrix is **1,024 cells, 256 four-arm blocks, 512 same-scale budget-prefix
pairs and 64 task clusters**. Each arm denominator is 256. Task means average
four seeds first and then weight the 64 tasks equally. Seeds/cells are not
additional independent problem identities.

64 is a bounded resource/breadth choice, not an 80%-power calculation from two
development rescues. It gives a finite-cohort net-count resolution of `1/256`
instead of `1/48`, but does not establish reduced estimator variance or a
confidence interval. The matrix has `16/3` times the development cell count;
the total configured legal-action cap is `393216`. Neither ratio predicts wall
time: qualification, generation, IO and independent replay are separate costs.
This turn approves none of those future operations.

Reuse the two v6 profiles exactly. Only the legal-action cap differs:

| Hard-work axis | B=256 | B=512 |
| --- | ---: | ---: |
| proposal_state_evaluations | 172 | 172 |
| proposal_action_scores | 573 | 573 |
| legal_action_scores | 256 | 512 |
| generated_perturbation_coordinates | 572 | 572 |
| edge_selections | 171 | 171 |
| transitions | 171 | 171 |
| verifier_calls | 35 | 35 |

The [frozen v6 design](countdown_thompson_feedback_budget_factorial_v6.md) remains
authoritative for the unchanged reward, guards, accepted-event prefix and
completion bounds. There is no provider call, Sobol arm, learned proposal,
budget-adaptive selection, early-success stopping or cross-cell mutable cache.

## Exclusions, sealing and outcome access

Before generation, verify and freeze the complete exclusion manifest, containing
both full-task and source-multiset identities of:

- historical-2, canary-12, reserved locked-128, diagnostic-12 and v5 development-12;
- all v6 PUBLIC qualification and full-shaped fixture identities;
- **all 12 v6 development tasks**, whether they succeeded, failed or deteriorated;
- all additional v7 PUBLIC qualification/full-shaped fixture identities fixed
  before generation, including every fixture variant actually used.

The locked reservation is an identity exclusion only, not permission to inspect
solutions, generate qualification runs on it or evaluate it. Exclude a source
even if its target, label or seed differs. The new 64 tasks must also be mutually
unique in source identity. No reuse of a prior task under a new ID is acceptable.

The historical exclusion inputs and v6 seal are fixed references; the complete
v7 fixture/exclusion manifest is a **missing implementation gate**, not something
this design checker certifies. Do not generate first and add fixture exclusions
afterward. Preserve rejection counts and accepted order, but no solution
witnesses, calibration profiles or outcome-dependent difficulty selection.
The resulting estimand is conditional on this recipe and exclusion history,
not an unconditional random sample of Countdown or even of source multisets.

After separately authorized sealing, freeze the exact 64 identities and the
1,024 task-keyed schedule before opening search outcomes. Four cells of each
task/seed begin with separate empty mutable state. The complete matrix must run
without success-based stopping, optional sample-size extension, seed replacement
or selective reruns. Operational failure retains a consumed study identity and
partial evidence; a new output path/candidate does not replenish authorization.

## Estimands, exact thresholds and mandatory outputs

For each task `i`, seed `r`, scale `s` and budget `b`, `Y[i,r,s,b]` is one iff
a valid complete cell contains a verified exact terminal. Valid budget exhaustion
without success is zero; missing/corrupt/unreplayable data is not zero.

```text
D[i,b]   = sum_r(Y[i,r,16,b] - Y[i,r,0,b]) / 4
I[i]     = D[i,512] - D[i,256]
Delta[b] = sum_i D[i,b] / 64
I        = sum_i I[i] / 64
         = sum_i,r(Y16,512 - Y0,512 - Y16,256 + Y0,256) / 256
```

Keep the development **rational** effect floor `1/24 = 2/48`, not its rounded
percentage rendering or a fixed two-cell count. At denominator 256 this requires
an integer numerator of `ceil(256/24) = 11` for both `I` and `Delta[512]`:
10 fails; 11 passes. The smallest attainable passing fraction is `11/256`,
about 4.30 percentage points; `1/24` itself is about 4.17 percentage points.
Those are distinct, display-rounded quantities.

Likewise retain the development task-breadth fraction `2/12 = 1/6`, not an
absolute two-task rule: at least `ceil(64/6) = 11` distinct tasks must have a
new high-budget success. Several rescued seeds on one task count once for
breadth. A paired rescue is not necessarily a newly solved task identity: report
any-seed solved task counts separately for each arm.

The future production analyzer must emit every output, including on a failed
screen:

- all four 256-denominator success counts, both budget uplifts and their interaction;
- all 64 task rows, per-budget new/lost/net success counts, rescued task counts and
  any-seed solved task counts, without merging these denominators;
- all 16 four-bit patterns in order `(Y0,256,Y16,256,Y0,512,Y16,512)`, including
  the seven forbidden zero rows required by valid budget prefixes;
- all 64 leave-one-task-out high-budget uplifts and interactions, denominator
  252 before reduction; no deletion of an inconvenient task;
- full terminal-error vectors, first-hit index or null, per-budget error W/T/L
  and ordinal error interaction with denominator 256, including every loss;
- all 512 cross-scale mechanism pairs, all 256 four-arm budget-extension rows,
  no-divergence/missing-support states, and 0/1/2+ suffix-completion bins.

Mechanism rows use the unchanged outcome-redacted common-prefix ordering before
terminal-error/success reduction. Separate already-divergent-low from newly-
divergent-high blocks. Report unfinished-trajectory completions separately from
later-trajectory successes. Terminal completions are not distinct witnesses;
prefix-error improvements are not wins against the other scale; neither is
causal mediation. Do not make a new gate from the two selected v6 rescue paths.

## Complete decision rule, not an executable analyzer

First require exact source/runtime and new-domain qualifications, 1,024-cell
closure, independent trace replay, all 512 full accepted-event prefixes, sole
primary-budget stopping and zero provider calls. Each valid cell must have a
terminal; at B=512 require at least three, plus at least one additional terminal
over its same-scale B=256 prefix. Nonprimary blocking, missing data or a forbidden
success pattern invalidates the whole matrix; it is not an unfavorable zero.

After integrity, require the conjunction of:

1. `I >= 1/24` and `Delta[512] >= 1/24` (both numerators at least 11).
2. `Delta[256] >= 0`, so low-budget net harm disappearing cannot explain a pass.
3. Zero high-budget **lost exact successes**, and new high-budget successes
   spanning at least 11 distinct tasks. Nonexact-error losses remain reportable;
   their absence is not implied by this exact-success guard.
4. Every leave-one-task-out high-budget uplift and interaction is strictly positive.
   These sensitivity summaries are not confidence intervals. At this sample size,
   the effect floor plus valid bounded task contrasts already implies positivity;
   retain the check/output for consistency, not as independent corroboration.
5. Every high-budget new-success pair has the unchanged common-prefix differing
   applied-backup support before its first differing action.

Similarly, eleven rescued tasks and zero high-budget lost successes already
imply at least eleven high-budget net successes. These are transparent,
overlapping requirements, not independent statistical tests whose evidence can
be multiplied. The interaction floor remains separate from that implication.

Only this full conjunction yields `SOURCE_DISJOINT_REPLICATION_SCREEN_PASS`.
A valid completed matrix failing any component yields
`STOP_REPAIR_REPLICATION_SCREEN_NOT_MET`; this means the specified screen was
not met, not proof of zero effect, harm or infeasibility. Integrity failure yields
`INVALID_ANALYSIS` instead. All historical STOP results and consumed claims stay
unchanged. None of these labels grants new experiment or locked-128 authority.

The standard-library checker only validates the design's byte anchors, ordinal
layout, exact threshold arithmetic and synthetic numerical counterexamples. It
does not check task provenance, raw events, mechanism support or source/runtime
qualification, and **cannot emit a production screen decision**. It accepts no
experimental input path and has no cohort/search/analysis/authorization entrypoint.

```sh
python3 -P -B scripts/check_feedback_budget_confirmation_design.py
python3 -P -B scripts/check_feedback_budget_confirmation_design.py --self-test
```

Default status is `REPLICATION_DESIGN_CHECKS_PASS_NOT_EXECUTABLE`; self-test
status is `SYNTHETIC_REPLICATION_MATH_PASS`. Both explicitly report zero new
tasks/search/provider operations and false execution/production-assessment flags.

## Ordered gates after this design

1. Review this exact recipe and checker. A scientifically material change gets
   a new design digest and explicit rationale; do not amend the v6 design/results.
2. Implement separately domain-bound, outcome-blind exclusion/manifest/schedule
   construction. Old 192-cell candidate/runner/analyzer/claim domains must not
   admit this 1,024-cell study by changing a count or relabeling a v6 receipt.
3. Independently qualify the unchanged search factors and the new full-shaped
   PUBLIC pipeline, including positive/negative synthetic gates, identity,
   prefix, publication/consumption and analyzer failures. Freeze all fixture
   identities and exact source/runtime receipts before any new cohort generation.
   Existing receipts are historical support, not qualification of the new pipeline.
4. Obtain separate cohort-generation authority; generate and independently verify
   one sealed 64-task cohort and its exact schedule, with all exclusions closed.
5. Review an exact non-authorizing candidate binding the design, seal, source,
   runtime, qualification, full reviewed revision and output/one-shot study identity.
6. Obtain explicit permission for that candidate's one complete run and independent
   analysis/verification. Sealing, passing a checker, or this design request does
   not satisfy this gate. Keep publication and merge separate from execution.

The next missing step is the new outcome-blind contract and its qualification
plan, **not execution of the old connector**. No new generation, trial search,
API call, GitHub publication, merge, retry or locked-128 evaluation accompanies
this design change.
