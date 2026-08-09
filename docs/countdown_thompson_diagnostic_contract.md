# Countdown Thompson diagnostic preregistration contract

## Purpose and claim boundary

This bundle reserves the still-unopened Track A locked cohort and seals a small
engineering diagnostic before any diagnostic search outcome exists. It asks
whether the current Thompson family is becoming a competitive search method and
why its action selection changes. It does not test a general QMC advantage,
authorize semantic routing or pruning, or support a task-transfer claim.

The builder may run the exhaustive Countdown solver only to condition task-suite
selection on solvability. It does not persist calibration profiles or solution
witnesses. It must not evaluate proposal rows, construct IID points, run search,
call a provider, or inspect terminal outcomes from any of the 240 cells.

## Authority and cohort order

The order is fixed and causal:

1. independently verify the tracked canary-v2 bundle and exact seal
   `5799c9f17686f064b7c50ee741d79bfbb14a4d61b9048672068a586b258fd437`;
2. reconstruct the historical two tasks from `exclusions.json` and the canary
   twelve tasks from `tasks.json` as exact `CountdownTask` rows;
3. reserve 128 solvable tasks with seed `26072602`, excluding all fourteen
   authorities by both full task fingerprint and source-multiset fingerprint;
4. construct twelve diagnostic tasks with seed `26081001`, excluding the
   historical, canary, and locked cohorts—142 identities—on both axes;
5. require all 154 final task fingerprints and all 154 source-multiset
   fingerprints to be unique.

The locked tasks are persisted only as an unopened reservation. Their presence
in the preregistration is not authorization to execute the locked evaluation.

## Sealed files

The canonical directory has exactly nine regular files:

- `authorities.json`
- `locked_reservation.json`
- `diagnostic_tasks.json`
- `proposals.json`
- `methods.json`
- `budgets.json`
- `analysis.json`
- `preregistration.json`
- `seal.json`

Every component has a deterministic digest. The seal binds each component's
canonical byte count, SHA-256, and deterministic digest, plus the PR #10 merge
base `9f0f0c9d07d9e7bf66caff5f664792b2160b4ea4`. Verification requires strict JSON,
canonical bytes, exact directory closure, regular no-follow reads, local receipt
closure, full deterministic regeneration, and an unchanged final snapshot.

Publication is atomic and no-overwrite. A raced or pre-existing destination is
an error; it is never replaced.

## Exact 240-cell schedule

Only `score256` is used. Its frozen budget is inherited byte-for-byte from
canary-v2:

```text
proposal_state_evaluations          87
proposal_action_scores             317
legal_action_scores                256  primary
generated_perturbation_coordinates 316
edge_selections                     86
transitions                         86
verifier_calls                      18
```

The heuristic proposal is `greedy_rollout_target_error/v1`. It is crossed with:

- greedy, beam width 2, and PUCT once per task at deterministic seed 0;
- candidate IID v1, dimension-normalized IID v2, dense-terminal IID v3, and
  greedy-anchor dense-terminal IID v4 at seeds 7168–7171.

This gives 36 deterministic and 192 stochastic heuristic cells. The oracle
proposal `oracle_path_count_positive_control/v1` is crossed only with greedy at
seed 0, adding 12 positive-control cells. Total: 240.

Deterministic methods are never copied under fake stochastic seeds. Sobol is not
in this diagnostic: source comparison remains closed until base search is
competitive. Each cell ID binds task and task-manifest identities, proposal
label/spec, method label/spec and full method/runtime manifest, budget label/spec,
exploration seed, bundle ID, and schema.

## Analysis order

The analysis order is an interpretive sequence, not a blinding mechanism:

1. integrity, exact coverage, budget closure, and two-stage byte replay;
2. proposal-rank and action-dimension mechanism metrics without reading
   terminal/error/success fields;
3. dense terminal absolute-error and reciprocal-value summaries;
4. exact success and the engineering escalation gate.

Proposal rank is ordered by descending finite `prior_logp`, with canonical legal
action index as the exact tie-break. The scored vector must equal the full legal
action order without padding or truncation. Normalized rank is
`(rank-1)/(action_count-1)` (or zero for a one-action state).

For every stochastic method there are exactly 48 root-rank events in diagnostic
task acceptance order and seed order 7168–7171. The event is the first
perturbation-selected root action; v4's no-RNG anchor is excluded and its next
root visit is used. Root action identity is
`(action_order_digest, canonical_action_index)`.

Action-count bins are fixed to 3–7, 8–15, 16–31, and 32–60. An occupied-bin gap
is the maximum minus minimum event-weighted mean normalized proposal rank among
bins containing at least one perturbation selection. Normalized ranks, group
means, diversity means, improvements, and gaps are reduced exact rational values
serialized as plain-integer `{numerator, denominator}` and compared by integer
cross multiplication; decimal display never controls a gate.
Fewer than two occupied bins, a missing one of the required 48 root events, or a
zero-observation aggregate fails the diagnostic before metric emission.

The v2 mechanism checks are:

- top-5 root retention improves by at least 8/48 over v1;
- mean normalized root rank improves by at least 0.10 over v1;
- mean root-action diversity across tasks is at least 1.5;
- at least 6/12 tasks use multiple root actions across the four seeds;
- occupied action-bin rank gap is at most 0.15.

Absolute-error means and even medians are reduced exact rational numbers encoded
as plain-integer `{numerator, denominator}`. Terminal-value means use
`math.fsum` in the sealed cell and within-cell trajectory order.

## Engineering escalation gate

For a stochastic method, task score is the arithmetic mean of its four ordered
binary successes. A deterministic baseline contributes one binary value. For
each task, subtract the baseline score from the candidate score, then take the
equal-weight mean of the twelve ordered task deltas.

Candidate methods are evaluated in v2, v3, v4 order. The first candidate must
simultaneously satisfy:

- candidate minus greedy at least +0.03;
- candidate minus beam width 2 at least +0.03;
- candidate minus PUCT at least -0.02.

The task-level comparison lies on a denominator-48 lattice. Therefore the exact
`+3/100` rule requires at least two additional successes (`2/48 = 1/24`), while
the exact `-1/50` PUCT rule requires a success-count difference of at least zero;
one fewer success would be `-1/48`, which is below the sealed threshold. These
integer consequences are stored directly in `analysis.json` and are not rounded.

For v4, at least one run must also show an unsuccessful greedy-anchor terminal
followed by a later exact-success terminal. Passing yields only
`READY_TO_PREREGISTER_LOCKED_128_EXECUTION`; it is not a superiority claim.
Failure yields `STOP_REPAIR_NO_LOCKED_128_RUN`.

Any missing, duplicate, extra, replay-invalid, budget-invalid, provider-calling,
action-drifted, or non-primary-guard-bound cell invalidates the entire diagnostic
before task scores. The oracle greedy positive control must succeed in all 12
cells and is excluded from readiness margins.

## Source-checkout operation

The authority is a tracked repository bundle, not wheel package data. The CLI
therefore requires an explicit source checkout root and is intentionally not a
packaged entry point:

```bash
PYTHONPATH=src python -m \
  qmc_bmgs.experiments.countdown_thompson_diagnostic_manifest \
  --verify docs/preregistrations/countdown_thompson_diagnostic_v1 \
  --repository-root .
```

This command regenerates both reserved cohorts and can take several minutes. A
successful verification proves preregistration identity and provenance only; it
does not open or validate diagnostic performance.
