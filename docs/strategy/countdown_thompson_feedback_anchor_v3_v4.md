# Countdown Thompson feedback and anchor ablations v3/v4

## Purpose

The Track A canary identified two defects after the many-arm scale mismatch:
failed terminal trajectories all backed up zero, and a fixed 256-score budget
bought only about two verified trajectories per adaptive run. This milestone
adds two nested, versioned diagnostic methods after the dimension-normalized
v2. It opens no new task outcomes and does not promote either method.

The nesting is deliberate:

1. v2: probability prior + action-dimension-normalized normal noise + binary
   exact terminal value;
2. v3: v2 selection plus bounded reciprocal absolute-error terminal value;
3. v4: v3 plus one explicit greedy proposal trajectory before posterior
   perturbation selection.

Each step changes one search factor. Existing v1 and v2 factories, method
payloads, and canonical trace bytes remain unchanged.

## V3 reciprocal absolute-error terminal value

For a valid complete Countdown trajectory with positive final integer `x` and
positive target `t`, let `e = |x - t|`. V3 backs up

```text
terminal_value = 1 / (1 + e)
```

Exact success remains one. Every non-exact complete value is at most one half,
so a near miss cannot approach the exact-success value arbitrarily closely.
The rule supplies a monotone absolute-error gradient without reading a
solution witness. The value is copied unchanged to every edge on the
trajectory with discount one, using the existing reverse Welford update.

The rule id is `reciprocal_absolute_error/v1`; the method id is
`thompson_reciprocal_error_terminal_dimnorm_noise/v3`. Backup events record
the integer absolute error, numerator `1`, denominator `1 + e`, rule id, and
applied float. Stage-one replay checks their exact arithmetic closure and
stage two independently re-verifies the trajectory and regenerates the exact
backup bytes.

This is reward shaping for an engineering diagnostic. It is not a Bayesian
posterior likelihood and cannot be credited as a QMC improvement.

## V4 one greedy trajectory, then Thompson

V4 uses the proposal log probabilities as the complete selection vector for
trajectory index zero, so that trajectory is reproducibly identical in actions
and states to deterministic greedy decoding. It backs that trajectory up with
the v3 terminal rule. From trajectory index one onward, it uses the v3
posterior-perturbation selection unchanged.

The method id is
`thompson_greedy_anchor_reciprocal_error_terminal_dimnorm_noise/v4`; the
selection rule id is
`one_greedy_trajectory_then_probability_prior_sqrt_2_ln_action_noise/v1`.
Every selection event declares `greedy_anchor` or `posterior_perturbation` and
how its perturbation point is used.

The anchor trajectory does not generate, charge, store, reference, or consume
IID/Sobol points. Its selection receipts charge legal-action scoring and the
transition only. From trajectory one onward, each visited node starts its
source-local sequence at visit zero. Consequently

```text
generated coordinates
  = legal-action scores
  - sum(anchor selection action counts)
```

This makes the anchor an explicit deterministic initialization cost rather
than unused random work. Any success on trajectory zero belongs to the
anchor; evidence for additional Thompson value must come from later
trajectories or additional successful witnesses.

## Diagnostic boundary

The future source-disjoint diagnostic must report, separately for v2, v3, and
v4:

- root proposal-rank retention and selected prior mass;
- node visits and revisitation;
- terminal shaped value and absolute error;
- exact first-hit trajectory index;
- for v4, anchor success and post-anchor added success separately;
- complete ledger and replay closure.

V4 cannot justify proceeding merely by reproducing the greedy baseline. A
future IID/Sobol source comparison is opened only if a non-anchor stochastic
method becomes competitive with greedy, beam, and PUCT at the fixed score
budget, or if v4 contributes an exact post-anchor success that the deterministic
anchor did not already provide.
