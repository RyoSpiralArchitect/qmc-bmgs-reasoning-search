# Countdown Thompson action-dimension normalization v2

## Decision

The first post-canary Thompson repair changes one factor only: it divides the
normal perturbation by the asymptotic many-arm extreme-value scale.  It keeps
the proposal probability, binary terminal backup, posterior update, complete
legal-action set, work accounting, and node-local IID/Sobol streams unchanged.

For a state with `A` legal actions, proposal log probability `logp(a)`,
posterior mean `mean(a)`, visit count `N(a)`, and independently materialized
normal coordinate `z(a)`, v2 uses

```text
d(A) = 1                              if A == 1
       sqrt(2 * log(A))               otherwise

index_v2(a)
  = mean(a)
  + prior_bonus * exp(logp(a))
  + posterior_sd_scale / (d(A) * sqrt(N(a) + 1)) * z(a)
```

The first explicit v2 configuration freezes `prior_bonus=1` and
`posterior_sd_scale=1`.  Canonical action index remains the final tie break.
This is a dimension-normalized posterior-perturbation heuristic, not an exact
Bayesian posterior or a claim that quasi-Monte Carlo is beneficial.

Version-one factories and trace bytes remain unchanged.  V2 has method id
`thompson_binary_terminal_dimnorm_noise/v2`, method-spec schema v2, and
selection rule id `probability_prior_sqrt_2_ln_action_noise/v1`.  Its selection
event records the action count and recomputed normalizer.  Replay rejects
stored action-count, rule-id, or normalizer drift and regenerates the complete
selection from independently validated proposal and perturbation material.

## Outcome-free scale audit

The completed canary exposed 27--55 root arms.  Before choosing v2, the first
root proposal row and first stored normal vector were read from the 48
heuristic `score256` candidate runs per source.  Exact-success labels, terminal
values, and winning paths were not used in this calculation.

| Formula | Source | Top-5 retained | Median selected prior rank |
|---|---|---:|---:|
| `p + z` | IID | `11/48` | 15.5 |
| `p + z` | Sobol | `12/48` | 17.5 |
| `p + z / sqrt(2 log A)` | IID | `28/48` | 2.0 |
| `p + z / sqrt(2 log A)` | Sobol | `22/48` | 9.0 |

At the observed action counts, `d(A)` is approximately 2.57--2.83.  The
unvisited coordinate standard deviation therefore becomes approximately
0.39--0.35, while the expected maximum across the action vector stays order
one instead of growing with `sqrt(2 log A)`.  The remaining IID/Sobol rank
difference is retained as a falsification signal; it is not tuned away.

The same audit found that `0.5 * zscore(logp)` plus dimension-normalized noise
was more source-stable.  It is deliberately not part of v2 because that would
change proposal representation and perturbation scale at once.  If this
single-factor repair fails on source-disjoint tasks, that hybrid is the
predeclared, separately versioned v2.1 candidate rather than an in-place
retune.

## Edge semantics

- A uniform proposal contributes the same `1/A` constant to every action and
  creates no arbitrary ordering.
- `A=1` uses `d(A)=1`; the sole coordinate and legal score are still generated
  and charged.
- `A=0` remains invalid for an ordinary selection.
- The denominator uses the state's complete legal-action count, never a
  changing count of unvisited or active actions.
- Only the existing per-arm `1/sqrt(N+1)` factor changes across visits.
- Finite log probabilities that underflow through `exp` retain the existing
  zero-contribution behavior.

## Next diagnostic and falsification boundary

No canary task is rerun in this implementation milestone.  Before a new task
cohort is opened, the diagnostic must seal root proposal-rank retention,
normalized rank, selected prior mass, unique root actions, v1/v2 paired first
action agreement, action-count bins, node revisit distribution, and verified
terminals per legal-action-score budget.

Reject the scale mechanism if source-disjoint data shows no rank-retention
improvement, if selection rank still depends materially on action count, or if
diversity collapses to greedy/PUCT-like behavior.  Exact success and terminal
error are evaluated only after those mechanism metrics.  The first diagnostic
uses IID only for base-search repair; a matched IID/Sobol comparison resumes
only if the repaired method becomes competitive with the deterministic and
PUCT baselines at equal work.

