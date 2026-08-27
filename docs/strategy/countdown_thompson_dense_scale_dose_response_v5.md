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

Anchor equivalence is a pre-execution, nondiagnostic implementation
qualification, not a development-matrix comparison.  It uses exactly one
public fixture: inputs `(1,2,3,4,5,6)`, target `720`, heuristic proposal,
exploration seed `7168`, and both `iid` and `sobol`.  Its budget profile id is
`dense_scale_anchor_fixture_verifier3`, its primary axis is `verifier_calls`,
its verifier-call limit is `3`, and each of the other six work-axis limits is
`20000`.  For each source, run only v2 versus v5 scale zero and v3 versus v5
scale one.  All eight fixture traces must pass canonical validation and
two-stage byte replay under their own method before applying the frozen
projection `countdown_track_a_anchor_equivalence/v1`.  The projection then:

1. removes only the top-level deterministic/final event digests and each
   event's hash-link fields;
2. replaces `run_identity.method_id` and `run_identity.configuration_id` with
   `binary_terminal_anchor` for v2 versus scale zero, or
   `reciprocal_error_anchor` for v3 versus scale one;
3. requires every `selection_committed.payload.method` to equal its sealed
   method spec, then replaces that one field with the same anchor label;
4. requires `search_finished.payload.summary.method` and
   `search_finished.payload.summary.run_identity_digest` to match the sealed
   method and original run identity, then replaces both with the same anchor
   label;
5. removes exactly `terminal_absolute_error`, `terminal_value_denominator`,
   `terminal_value_floor`, `terminal_value_floor_applied`,
   `terminal_value_numerator`, `terminal_value_rule_id`, and
   `terminal_value_scale` from each `trajectory_backed_up` payload; and
6. after replay has independently closed each storage receipt, replaces only
   `ledger_snapshot.live_storage.bytes` and
   `ledger_snapshot.peak_live_storage.bytes` with the anchor label because the
   extra v5 evidence bytes are schema overhead; and
7. preserves every other run-identity field, top-level field, event index,
   kind, charge receipt, payload field, terminal value, posterior update,
   proposal/node/point material, stop event, and ledger field/component.

The two resulting canonical projections must be exactly equal.  The frozen
qualification receipt records, for each source and anchor pair, the authority
trace SHA-256, scaled trace SHA-256, and common projection digest.  Raw fixture
traces are not persisted.  Every execution environment must reproduce all four
receipt rows before opening development results.  A digest, projection, or
replay mismatch invalidates the experiment before terminal errors or successes
are read.

```text
iid binary
  authority=1a712c7b766dc5e6aa138edb718432636fac838f75e7ca1e4274fd17a4bca9e4
  scaled=0d0dc2eb4c52697e78bcb744a48c3a407cac4dc3025b0b9f393e08144efc320b
  projection=18534a6eb89bb0a23cf0c6de104f7d1ed810eb4c5a662377fb4957d3690ba8ff
iid reciprocal
  authority=036ab50644b600cacf8488f74210c9e9725db441b8e8a3b78e90561eb2445763
  scaled=0657acaf773f995a5c624bb18ad7f45cc0b8349edfd037222b04d50a657fcf22
  projection=f0628fdeda9f93f41ed6ad60f4718738b6cfad3f0ea967c6f4b3391a2d757310
sobol binary
  authority=651d1c5a6dd5395dbb54768eeea3c9a8f2e6d6a1f60e399301120dc59f93531f
  scaled=2058e56a97de725c61b78efc338c75c868386fe6fd1e6879a0d5cf32c2f81b0f
  projection=75c80b1a60ec85328ee9a88259c81da13ac81ea3ea8719a5e5049754350a482c
sobol reciprocal
  authority=6be047dad38bfbee09e42ca2c07e88df75e1f493efdecc171b1a26a4f7852d31
  scaled=e1136f466718b762cbd50549bbecb8fd9c14553361d54461ee8883739ba6596c
  projection=5cbccc2eb19780909b3942ec509ad61424f12d401fff03df071909600a742b4b
```

No v2 or v3 trace may be executed on any of the 12 development tasks.  Such a
trace would be an unregistered, outcome-bearing extra cell.  The development
schedule contains exactly the 384 v5 cells below; the fixture qualification is
outside that schedule and does not authorize retries or auxiliary controls.
This definition deliberately normalizes only schema/evidence overhead fixed
before the experiment and leaves no analysis-time choice of fields.

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

1. reproduce the sealed nondiagnostic anchor-qualification receipt without
   opening development material;
2. provenance, exact-cell closure, budget closure, and two-stage byte replay;
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
exact reduced rational arithmetic.  For a sorted nonempty integer vector of
length `n`, the median is element `n//2` when `n` is odd and the reduced
rational `(x[n//2 - 1] + x[n//2]) / 2` when `n` is even; an empty required
vector invalidates the analysis.  Binary64 summaries are descriptive and must
preserve their fixed iteration order.  No p-values, confidence intervals,
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
