# Credit-assignment mechanism diagnostic contract

## Role

This is a post-validation mechanism diagnostic, not a fresh performance
validation. The routing-only substrate and the terminal-only control were
selected and observed before this diagnostic was specified.

The engineering question is narrow: when the correct Role-Lock D4 path is
already discoverable, can denser search feedback convert the same verifier-call
budget into more exact readout successes?

## Fixed comparison

Both conditions use `sobol_routing_only`: Sobol coverage gate and cluster
quantile, IID action perturbations, embedding strata, posterior SD 1.0, and
pruning disabled. The existing benchmark configuration is unchanged, including
`gamma = 1.0`, the candidate set, LM-prior role, and deterministic readout rule.

For generated tokens `x` without BOS, define exact success and correct-prefix
length as

\[
e(x)=\mathbf 1[x=(2,3,4,1)]
\]

\[
L(x)=\max\{\ell\in\{0,\ldots,4\}:x_{1:\ell}=(2,3,4,1)_{1:\ell}\}.
\]

The conditions are fixed to:

- terminal-only control: `r(x) = 5 e(x)`;
- prefix-progress challenger: `r(x) = 5 L(x) / 4`.

There is no reward-scale sweep, nonlinear shaping, sampler switch, additional
sampler profile, pruning change, or posterior-noise change.

## Cohort and immutable control

- Paired exploration seeds: 704–831, 128 groups.
- New search runs: the 128 prefix-progress rows only.
- Control source: promoted artifact
  `role_lock_d4_20260718_two_phase_validation_n128` filtered to
  `method.name == "sobol_routing_only"`.
- Frozen control outcome: 52/128 exact readout successes at request 700.
- Full control raw SHA-256:
  `ec035850f61c75ca9a01f2e38f14d59841cbde9b2a046adb852a1d65c512360a`.
- Canonical compact-JSONL SHA-256 of the 128-row filtered subset:
  `6fcd2d613976c965ba9786fbf6f2487c4b75f4310086db5ed8b812760c85d60e`.

The control rows remain byte-immutable. They are neither copied into the new
raw schema nor rehashed. Before any new run, the full promoted control is
validated with its historical validator, then paired by exploration seed.

## Matched budget

- Search verifier feedback calls: exactly 700 per row.
- Passive checkpoints: 64, 128, 256, 384, 512, 700.
- LM-node integrity ceiling: 1111, with strictly positive headroom.
- Normal edge bound: 2800.
- Edge integrity ceiling: 3500, with strictly positive headroom.
- Final deterministic readout: one evaluation outside the search budget,
  reused from checkpoint 700.

The candidate set, LM, tokenizer, task, seeds, routing/action streams, prior,
readout rule, and guard semantics are unchanged. Wall time is informational and
is not a paired endpoint because the control was generated in an earlier run.

## Exact success is separate from feedback

Positive prefix feedback is not success. Every verifier event records:

- request index and endpoint kind;
- generated token IDs;
- independently recomputed `L(x)`;
- exact token equality;
- applied feedback as an integer numerator over denominator 4;
- logical LM-node count at the event.

The raw record keeps separate feedback and exact-success ledgers. In
particular, `feedback > 0`, `L > 0`, and `best feedback > 0` must never update
the exact-success ledger. Compatibility `first_success` counters retain exact
token-equality semantics.

## Primary and secondary endpoints

The only primary is exact readout success at verifier request 700. Report:

- count, rate, and Wilson 95% interval for each condition;
- paired risk difference, progress minus terminal;
- paired percentile-bootstrap 95% interval with 5,000 resamples and seed 313;
- exact two-sided McNemar p-value and discordant counts.

There is one primary contrast, so no multiplicity adjustment is added.

Descriptive secondary endpoints are ever-observed exact success, restricted
first-exact request with unobserved values set to 701, checkpoint exact-success
curves, final correct-prefix length, LM nodes, prefix tokens, edges, feedback
exposure, and exact-success observation count.

## Fixed decision rule

- `data_quality_failure`: do not interpret. Repair analysis-only faults from the
  same raw; rerun only the same 704–831 progress rows for a search/ledger fault.
- `supported_credit_gain`: point delta is positive, bootstrap lower bound is
  above zero, and exact McNemar p is below 0.05. Freeze this oracle feedback as
  a positive control and move to a fresh harder task or non-oracle verifier.
- `directional_only`: point delta is positive but the support rule is not met.
  Do not add D4 seeds or tune the feedback; carry the fixed challenger only to
  a bounded harder benchmark.
- `no_gain`: point delta is nonpositive. End Role-Lock sampler/feedback tuning.

Even `supported_credit_gain` is fixed-verifier evidence, not equal-total-compute
superiority. If resource work rises, the next comparison must match total
compute. No result authorizes another D4 reward or threshold sweep.

## Required data quality

- Validate the promoted control bytes, schema, full paired blocks, and subset
  hash before starting new search.
- Require 128 unique progress seeds and 128 exact paired groups.
- Recompute every event's prefix length, rational feedback, endpoint kind, and
  exact equality from its tokens.
- Close event aggregates into checkpoint and final ledgers exactly.
- Require exact budgets, positive guard headroom, candidate identity, no
  pruning, routing-only source accounting, passive collector behavior, strict
  JSON, deterministic digests, canonical order, and disk-reloaded summary
  equality.
- In self-test, a partial positive event must leave exact success false, and a
  terminal-only compatibility run must match the historical runner's behavior
  digests and counters.
