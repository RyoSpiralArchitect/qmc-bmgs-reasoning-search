# Countdown Track A search contract

## Scope and claim boundary

This milestone places provider-neutral Countdown proposal policies and the
complete minimum method matrix behind one accounting, trace, and replay
contract.  It is an engineering substrate for the 12-task canary.  It does
not itself seal a canary manifest, open canary outcomes, establish that search
beats a deterministic baseline, or establish an IID-versus-Sobol effect.

The method matrix is:

- deterministic greedy proposal decoding;
- deterministic layer-synchronous beam search with width two;
- PUCT with no root noise;
- Thompson search at `(prior_bonus=.1, posterior_sd_scale=1)` with IID and
  Sobol points;
- Thompson search at `(prior_bonus=1, posterior_sd_scale=1)` with IID and
  Sobol points.

Deterministic methods are one run per task and budget profile.  They use
`selected_source="none"` and `exploration_seed=0`; stochastic seed replication
must not be fabricated for them.  The exact-oracle proposal is an explicitly
separate positive-control stratum and is not part of a fair primary comparison.

## Provider-neutral proposal policies

Every method consumes the same immutable proposal row for one canonical
Countdown state and its exact canonical legal-action order.  The row stores
the policy identifier, task and state identities, ordered actions, finite raw
scores, stable log-softmax priors, internal diagnostic work, and a digest.

The version-one policies are:

- `uniform/v1`: all actions have equal score;
- `greedy_rollout_target_error/v1`: for each candidate action, a deterministic
  completion repeatedly chooses the legal action minimizing
  `(abs(action_result - target), canonical_action_index)`.  Root candidates are
  totally ordered by `(terminal_abs_error, immediate_abs_error,
  root_canonical_index)`, and their raw logits are the negative integer ranks;
- `oracle_path_count_positive_control/v1`: the raw logit is the finite-float
  form of the exact memoized solution-path count downstream of each candidate
  action.

The rollout policy is a provider-neutral heuristic, not a value oracle.  The
path-count policy uses exhaustive knowledge and is reported only as a positive
control.  Internal rollout or recursive work is retained as diagnostic
telemetry; it is not claimed to have provider-equivalent cost.

A proposal-cache miss charges one `proposal_state_evaluations` and one
`proposal_action_scores` per legal action.  A hit charges neither.  Evaluation
and cache insertion occur only after an accepted search-step transaction.

## One atomic search-step transaction

The search session, not the perturbation source, owns every selection receipt.
For one ordinary greedy, PUCT, or Thompson edge, the proposed transaction is:

```text
proposal_state_evaluations       = 1 on proposal miss, otherwise 0
proposal_action_scores           = A on proposal miss, otherwise 0
legal_action_scores              = A
generated_perturbation_coordinates = A for Thompson, otherwise 0
edge_selections                  = 1
transitions                      = 1
```

Here `A` is the exact current legal-action count.  A beam layer scores the
union of the outgoing actions from its live parents and charges only the edges
and transitions retained into the next width-two layer.  It never pads or
truncates an action vector.

Before a transaction is accepted, the session validates task, state, action
order, method specification, proposal-cache state, perturbation point identity,
and required trace capacity.  A rejected transaction leaves the ledger,
proposal cache, graph, posterior values, frontier, node-local point visits,
material tables, witnesses, and trace byte-for-byte unchanged.

After acceptance, an unexpected exception poisons the run.  A poisoned run is
not resumable or finalizable as valid evidence.  The implementation does not
pretend that a general ledger rollback can undo already performed external or
random work.

The terminal verifier is a separate atomic receipt with
`verifier_calls=1`.  Under the `verifier8` profile, one verifier call is
preflighted before a new trajectory is allowed to inspect a state, proposal,
graph node, or perturbation stream.  After the eighth verifier, a ninth
trajectory performs no partial work.

## Search semantics

Countdown states are canonical and may merge into a DAG.  Complete action and
state sequences remain attached to each trajectory, so a merged node never
erases the terminal witness that reached it.

Terminal reward is binary exact success, discount is one, and completed
trajectories are backed up in reverse order with Welford mean and second-moment
updates.  There is no reward shaping, pruning, semantic routing, rollout value,
Dirichlet root noise, or hidden optimistic leaf value in this milestone.

Greedy chooses the maximum proposal probability at every state, breaking ties
by canonical action index, and naturally ends after one terminal verification.

Beam search is layer-synchronous with frozen width two.  It ranks partial
trajectories by cumulative proposal log probability and uses the complete
canonical action-trace key as its final tie breaker.  This avoids the
depth-bias of comparing incomplete paths at different depths in one naïve
best-first heap.

PUCT recomputes every legal arm at each selection using

```text
mean(a) + c_puct * prior(a) * sqrt(1 + N(state)) / (1 + N(state,a))
```

with canonical-index tie breaking.  Version one freezes `c_puct=1`.

Thompson search recomputes every legal arm using

```text
mean(a)
+ prior_bonus * prior(a)
+ posterior_sd_scale / sqrt(N(state,a) + 1) * normal(a)
```

The selected IID or Sobol vector has exact dimension `A`.  Configuration and
method identifiers remain outside the node-stream identity, so matching
source, task, state, exploration seed, action order, and node-local visit use
the same point across the two Thompson calibrations.

The post-canary dimension-normalized v2 is an explicit new method-spec branch;
it does not silently alter either version-one calibration.  It retains the
same probability prior and posterior update but divides the normal term by
the complete action vector's extreme-value scale:

```text
d(A) = 1 if A == 1 else sqrt(2 * log(A))

mean(a)
+ prior_bonus * prior(a)
+ posterior_sd_scale / (d(A) * sqrt(N(state,a) + 1)) * normal(a)
```

The first v2 freezes both coefficients at one.  Its method and selection-rule
identities are versioned separately, while its node-local point identity stays
paired with v1 until their selected paths diverge.  This isolates one proposed
repair for the canary's many-arm noise mismatch; it is not performance or QMC
evidence.  The rationale and falsification boundary are in the
[v2 strategy note](strategy/countdown_thompson_dimension_normalization_v2.md).

Two post-v2 diagnostic methods are explicit new method-spec branches. V3
keeps the v2 selector and replaces binary failure backup with

```text
1 / (1 + abs(final_value - target))
```

for every valid complete positive-integer Countdown trajectory. V4 first runs
one complete greedy proposal trajectory, backs it up with that v3 value, and
then uses v3 Thompson selection from trajectory index one. The anchor generates
and charges no perturbation coordinates. Later stochastic selections begin
their node-local streams at visit zero, and every anchor selection explicitly
binds `point_digest=null` plus zero coordinate work. This preserves semantic
work accounting without hiding the anchor's deterministic cost. The exact
ablation and attribution boundary is in the
[v3/v4 strategy note](strategy/countdown_thompson_feedback_anchor_v3_v4.md).

PUCT and Thompson continue after a first exact hit until the active budget
profile stops them or the method has no further legal work.  This permits the
preregistered first-hit, exact-terminal reuse, and successful-terminal
diversity diagnostics.  Greedy and beam may finish naturally before a budget
limit.

## Budget profiles and stopping

`score256` and `verifier8` are separate runs.  They are never simultaneous
primary stopping axes.

- `score256` stops before the next whole selection would make
  `legal_action_scores > 256`.  Because action counts are dynamic, exact usage
  of 256 is not required.  The final record stores the rejected next delta and
  blocked axis as closure evidence.
- `verifier8` stops before starting a ninth trajectory.  Its selection and all
  other limits are non-primary guards.

Canary execution is invalid if any non-primary guard rejects work or finishes
with exactly zero remaining capacity.  Exact exhaustion is conservatively not
called nonbinding even when a deterministic method naturally completes on the
same operation.  Exact guard values remain intentionally unsealed until the
method harness is complete and its download-free tests expose realistic upper
bounds.  They must be frozen before the first canary search output is opened.

A score-profile rejection may occur after earlier edges of an incomplete
trajectory were validly explored.  Those accepted work events remain in the
trace, but the incomplete trajectory performs no terminal verification or
posterior backup.  Replay reconstructs the same discarded partial trajectory.

## Search trace and two-stage replay

The search trace stores typed events for proposal materialization, optional
perturbation node and point material, the committed selection and transition,
terminal verification, reverse backup, and final stopping evidence.  Exactly
one selection event owns each search-step receipt.  Perturbation material
events inside a search trace are uncharged and are referenced by digest from
that selection event.

The accounting invariants are:

```text
ledger.legal_action_scores
  == sum(len(event.scored_action_indices) for ordinary selection events)
   + sum(
       len(parent.scored_action_indices)
       for beam layer events
       for parent in event.scored_parents
     )

ledger.generated_perturbation_coordinates
  == sum(len(referenced_point.uniforms) for stochastic selection events)
```

Deterministic selections reference no point and generate zero coordinates.
Every accepted receipt index has exactly one owning event.

A dimension-normalized v2 ordinary selection additionally records
`selection_semantics` with the exact action count, rule id, and
`sqrt(2 log A)` normalizer.  Stage-one replay recomputes this diagnostic rather
than trusting it; version-one selections do not gain the field and retain
their historical bytes.

V3 backup events additionally bind the reciprocal absolute-error rule and its
integer numerator/denominator evidence. V4
selection events bind whether a selection is the one greedy anchor or a later
posterior-perturbation step. Stage one requires no point and zero coordinate
work for the anchor, and one replay-bound point per later selection. Stage two
re-verifies the terminal and regenerates the complete search from empty state.

The run identity binds digests of the complete proposal, method, runtime, and
budget-profile specifications.  In particular, the primary stopping axis is
bound independently of the human-readable profile label and hard-limit map;
two profiles with the same label and limits but different primary axes cannot
share a run identity.  These run-level fields remain outside node-stream
identity so intended source-specific point pairing is unchanged.

Replay has two independent stages:

1. Generative material replay regenerates every proposal row, canonical action
   order, stream and point identity, uniform vector, normal transform, and
   material digest from the externally expected task and run identity.
2. Search replay starts from empty caches, graph, posterior state, frontier,
   and ledger; supplies only stage-one-validated material; reruns the method;
   and requires byte-identical canonical trace output.

Internal hash consistency alone is insufficient.  Rehashed tampering of a
proposal, action order, selected arm, child state, point, charge, terminal
result, backup, stop reason, or event order must fail one of the two stages.

Track A version one is single-threaded within a run.  Parallelism is permitted
only across independent runs.  Wall time, resident memory samples, host paths,
and process identity remain descriptive telemetry outside the byte-identical
core.

The deterministic `live_bytes` gauge is explicitly a canonical-JSON byte
proxy for retained search state: graph rows, posteriors, active paths,
perturbation-source state, terminal witnesses, and trace events.  It is not an
estimate of the Python heap or allocator overhead.  Actual RSS and wall time
remain separate descriptive measurements for later experiment runners.
