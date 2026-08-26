# Countdown Thompson dense terminal-value scale dose response v5

Date frozen: 2026-08-26

## Status and question

This document freezes a source-disjoint development experiment before any
search outcome from the new cohort is opened.  It asks one narrow question:

> Holding the task cohort, proposal, IID perturbation stream, selection rule,
> budget, and exploration seeds fixed, does increasing the strength of
> reciprocal absolute-error terminal feedback produce a reproducible
> mechanism response and any exact-success gain over binary terminal feedback?

This is an engineering dose-response study.  It is not a QMC comparison, a
method-superiority test, a retry of the preceding diagnostic, or authorization
to execute the locked 128-task cohort.

## Frozen evidence boundary

The scale grid is motivated only by the already published selection-margin
audit.  On the old 12-task diagnostic, 94 of 370 v2/v3 common-prefix decision
surfaces had nonzero dense score displacement, four changed action at the
observed scale, 81 had a later positive boundary, 64 required a local scale
greater than 16, and nine had no positive boundary in the observed direction.
Those are exploratory results on the old cohort; they do not predict that a
particular scale will solve a new task.

Frozen authority:

- merged base revision:
  `2bf4ce85947c39cc05a6f32a19576ea7d6e6790a`;
- diagnostic bundle id:
  `countdown_thompson_diagnostic_12_seed_26081001/v1`;
- diagnostic seal deterministic digest:
  `cc633b9ee3ffda6a9115af07f0cc047a1bd8cd7af5e11d07f6ddb0faa4e5f975`;
- selection-margin receipt schema:
  `qmc-bmgs-countdown-thompson-selection-margin/v4`;
- selection-margin deterministic digest:
  `fff949f9552b1898013b4b61fe515e9d34ecc5d5a1edc192c21eff264f5e9e09`.

The new preregistration must verify the tracked diagnostic bundle before using
its identities as exclusions.  No old outcome artifact is an input to cohort
generation, scheduling, execution, or the frozen decision rule.

## Frozen development cohort

Generate exactly 12 solvable Countdown-D6 tasks with generation seed
`26082601`, after excluding both full task fingerprints and source-multiset
fingerprints from all of the following authorities:

1. the two historical tasks;
2. the 12 canary tasks;
3. the reserved, unexecuted locked 128 tasks;
4. the preceding 12-task Thompson diagnostic.

The generator acceptance order is the task order.  The 12 accepted full-task
fingerprints and 12 source-multiset fingerprints must each be unique.  The
sealed bundle persists task definitions and the generator receipt, but no
solution witness, calibration profile, proposal row, perturbation point,
search record, provider output, or outcome.

This cohort is a development cohort.  It may select a scale for a later,
separately preregistered source-disjoint confirmation; it cannot directly open
locked-128.

## One-factor method family

All cells use dimension-normalized Thompson selection with:

- heuristic proposal `greedy_rollout_target_error/v1`;
- IID perturbations only;
- `prior_bonus=1.0`;
- `posterior_sd_scale=1.0`;
- no greedy anchor;
- unchanged reverse Welford backup with discount one;
- the unchanged `score256` hard work budget.

Only the terminal-value scale changes.  For absolute terminal error
`e = abs(final_value - target)` and integer scale `s`, define:

```text
V_s(e) = 1                         when e = 0
V_s(e) = 0                         when e > 0 and s = 0
V_s(e) = max(s / (s + e), 2^-1074) when e > 0 and s > 0
```

The frozen scale order is:

```text
0, 1, 2, 4, 8, 16, 32, 64
```

This parameterization supplies two exact anchors: `s=0` has the existing v2
binary terminal semantics, and `s=1` has the existing v3 reciprocal-error
terminal semantics.  For every frozen positive scale, exact success stays one
and every failure stays strictly below one.  The scale therefore changes the
strength of failure feedback without allowing a failed terminal to outrank an
exact success by terminal value alone.

V5 must use a new method-spec schema and terminal-rule id.  Backup events must
record the plain-integer scale, absolute error, exact numerator and denominator,
binary64 floor, floor-use flag, rule id, and applied float.  Stage-one
validation and stage-two fresh replay must reconstruct these values.  Existing
v1-v4 specs and canonical behavior remain unchanged.

## Frozen execution matrix

Use exploration seeds `7168, 7169, 7170, 7171` at every scale.  The same
task/state/seed/visit identity must receive the same IID coordinates until
scale-dependent action divergence changes the visited state.

The exact matrix is:

```text
12 tasks x 8 scales x 4 exploration seeds x 1 proposal x 1 budget
= 384 cells
```

Cells are ordered by task generator acceptance order, scale order, then seed
order.  Missing, duplicate, extra, replay-invalid, or budget-invalid cells
invalidate the whole experiment before any aggregate is emitted.  Execution
is all-or-nothing: no outcome-aware retry, replacement task, scale addition,
seed addition, or early stopping is permitted.

## Frozen analysis order

Analysis proceeds in this order:

1. provenance, exact-cell closure, budget closure, and two-stage byte replay;
2. scale-0/scale-1 anchor equivalence checks;
3. mechanism reductions that do not read terminal success or error;
4. terminal-error reductions;
5. exact-success reductions and the development handoff rule.

For every task/seed, pair each positive scale with scale zero.  Compare actual
selection events only while both traces share the same pre-decision surface:
trajectory index, depth, state, canonical action order, proposal digest,
perturbation-point digest, selection-rule id, noise normalizer, and posterior
visit vector.  Include the first action-divergent decision and stop pairing
immediately afterward.  Record whether the divergence was feedback-informed,
its coordinate, both selected actions, both score vectors, and the terminal
scale values already backed up on the shared prefix.  Do not synthesize the
unobserved counterfactual continuation.

For each scale, report in fixed task/seed order:

- exact-success count and success vector;
- first-hit trajectory index or `null`;
- minimum terminal absolute error per cell;
- complete ordered terminal-error and terminal-value vectors;
- paired new successes, lost successes, and net success difference versus
  scale zero;
- paired minimum-error wins, ties, and losses versus scale zero;
- feedback-informed first-divergence count and coordinate distribution.

Aggregate integer counts exactly.  Means and medians of integer errors use
exact reduced rational arithmetic.  Binary64 summaries are descriptive and
must preserve their fixed iteration order.  No p-values, confidence intervals,
bootstrap intervals, or outcome-based row filtering are authorized.

## Frozen development handoff rule

Among scales `1,2,4,8,16,32,64`, choose the scale with the largest exact-success
count across the 48 task/seed cells; break ties by the lower scale.  Call it
`s*`.  The result is eligible only for
`READY_TO_PREREGISTER_SOURCE_DISJOINT_CONFIRMATION` when all of the following
hold:

1. every integrity and replay gate passes;
2. `s*` has at least two more exact successes than scale zero;
3. at least two scale-zero failures become exact successes at `s*`;
4. every such new-success pair has a first action divergence after at least one
   scale-dependent terminal backup on the common prefix.

The threshold is an engineering screen on a 48-cell lattice, not a statistical
claim.  A passing scale must be tested once on a newly generated,
source-disjoint confirmation cohort under a separately frozen design.  It does
not authorize locked-128.

If no positive scale passes every condition, the status is
`STOP_REPAIR_NO_LOCKED_128_RUN`.  The complete dose-response, including a null
or adverse result, remains part of the record.

## Claim boundary

The experiment may establish that this exact scale intervention caused a
different deterministic search trajectory under matched tasks, IID streams,
and budgets, and may report exact successes observed in this development
cohort.  It may not establish general method superiority, task transfer,
statistical significance, QMC benefit, a Bayesian posterior interpretation,
or performance on the locked cohort.

Integrity `PASS` means only that provenance, schedule, budget, and replay
closed.  It is not a positive scientific result.
