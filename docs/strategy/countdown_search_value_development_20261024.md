# Search-value development diagnostic, 2026-10-24

**Status: design only; not an executable plan or execution authorization.**
This follows the [research-state correction](../research_status_20261024.md).
No new cohort, mean-off implementation, experiment or provider call exists from
this proposal. Its structured companion is a
[non-executable design specification](../preregistrations/countdown_search_value_development_20261024.design.json),
not a replacement for any sealed historical plan.

## Decision to make

At a fixed legal-action-score ceiling, is the **current** single16 policy more
useful than a simple fixed PUCT baseline on the same unseen sources? Separately,
does using the learned terminal-return mean improve this policy beyond its prior
and visit-dependent perturbation schedule?

The original goal was useful search, not QMC use or an increasing number of
branches. Previous portfolio/diversity/allocation results remain valid within
their scopes. They do not compare the current kernel with simple baselines, and
do not justify another allocation ratio or an adaptive scheduler. This design
returns to that missing search-strength gate before adding architecture.

## Five methods; only one scientific primary

All methods use the same canonical Countdown task, legal-action order, exact
verifier and `greedy_rollout_target_error/v1` proposal. Each cell starts with an
empty, isolated graph/cache. No cross-method work sharing, hidden warm start,
success-dependent rerun or budget transfer is allowed.

| Method | Per-source rows | Fixed behavior | Role |
| --- | ---: | --- | --- |
| single16 | 4 | Existing IID dimension-normalized scaled-dense Thompson; prior/noise coefficients1, scale16, no greedy anchor; one full512 stream | Current policy; primary treatment |
| selection-mean-off | 4 | Same rules and terminal updates as single16, but selection alone uses mean coefficient0 | Diagnostic for use of the learned mean |
| greedy | 1 | Existing deterministic maximum-prior policy; canonical tie break; one natural trajectory | Simple baseline diagnostic |
| beam2 | 1 | Existing layer-synchronous beam width2 with cumulative proposal log probability | Simple baseline diagnostic |
| PUCT | 1 | Existing binary-exact terminal return, c_puct1, no root noise, canonical tie break | Fixed primary comparator |

The sole primary is **single16 minus PUCT**. This compares two configured
methods, including their different feedback/exploration rules. It is **not** a
one-factor test of Thompson versus PUCT, nor evidence for Bayesian uncertainty,
dense feedback alone, QMC, or an LM. PUCT is not retuned or given a new dense
reward in response to these results. Greedy/beam are retained even if they
outperform the preselected comparator; no best-looking baseline replaces the
primary after outcomes are inspected.

### Precisely what mean-off means

The new method must only change the use of `edge_mean` in selection:

```text
single16: mean + prior + dimension/visit-normalized IID perturbation
mean-off:    0 + prior + dimension/visit-normalized IID perturbation
```

It must retain the same updates of visits, means and m2, return scale/rule,
proposal, normal material, action enumeration, transaction accounting, terminal
verification and readout. The stored means remain available for passive
diagnostics. This is not scale0 (exact-success-only feedback), frozen visits,
zero noise, shuffled outcomes or a complete removal of learning/state effects.

After policies choose different actions their visited states, counts and costs
can differ. "Same update rule" does not mean identical realized visits. Material
must agree at the same task/state/local-visit/action-order/stream-key coordinate;
divergent whole trajectories are not called common random numbers.

An additive versioned method identity and replay support are required later.
Existing single16, PUCT, source files and old trace semantics must not be silently
redefined to implement this intervention. Synthetic fixtures must prove both an
identical zero-mean control and a constructed nonzero-mean selection difference,
without using evaluation outcomes to select the implementation.

## Prospective data and scale

- 128 new, source-multiset-unique solvable Countdown tasks.
- Existing six-input recipe: integers1..10, target100..999, generator seed
  **26102401**, maximum **10,000 attempts**. Keep the first128 eligible sources in
  generated order and all acceptance/rejection identities. If insufficient,
  stop without replacing the seed or relaxing eligibility.
- Exclude all historical/fixture sources and reserved C5/locked sources,
  including portfolio8, diversity32 and allocation256. Reserved data are read
  for authenticated identity exclusions only, never search outcomes, difficulty
  or solver witnesses. Final exclusion paths, digests and counts must be bound
  in the later executable candidate; the design file is not that manifest.
- Four fixed fresh root seeds **131072..131075** for each stochastic method.
  Use the existing versioned diversity-stream derivation with branch index0,
  shared across single16 and mean-off and excluded from method identity.
  Validate seed/exclusion collisions before sealing; a collision blocks this
  design rather than silently choosing alternatives.
- Deterministic methods run once per source (`selected_source=none`, seed0),
  not four duplicate rows. No perturbation coordinates are generated for them.
- Fixed matrix: `128 × (4 + 4 + 1 + 1 + 1) = 1,408 cells`, one search per cell.
  There are128 source clusters, not512 independent stochastic tasks. No second
  budget, uniform-proposal matrix, ratio sweep or provider stratum is added.

Already observed cohorts may support implementation fixtures and diagnostics,
not new confirmation. Seal the final candidate implementation/runtime/methods,
generation recipe/exclusions, seeds, budgets, analysis and attempt identity
before opening new search outcomes. Generate the new cohort only under separate
authority for that candidate; this design PR generates nothing.

## Budget and cost boundaries

| Work axis | Per-cell limit | Function |
| --- | ---: | --- |
| legal_action_scores | 512 | Only primary stopping budget |
| proposal_state_evaluations | 100,000 | Non-primary integrity guard |
| proposal_action_scores | 100,000 | Non-primary integrity guard |
| generated_perturbation_coordinates | 100,000 | Non-primary integrity guard |
| edge_selections | 100,000 | Non-primary integrity guard |
| transitions | 100,000 | Non-primary integrity guard |
| verifier_calls | 100,000 | Non-primary integrity guard |

Maximum combined primary work is **720,896 scores**. Every method uses the same
limits, but deterministic methods may naturally finish early; do not repeat
their work to spend a cap. Adaptive methods keep their original continuation
semantics after success. A rejected next atomic transaction consumes no partial
work. Any non-primary guard binding is an integrity failure, not an excluded
unfavorable cell or a valid cheaper performance point.

Report actual and unspent values for all seven axes by method/source/seed, plus
proposal-internal completion transitions and, in the later implementation,
the internal legal-action evaluations those completions require. Count repeated
cache misses; do not count a shared proposal precomputation as free. Log elapsed
time/peak RSS separately from deterministic work and alternate run order by a
presealed schedule if interpreting timings. Do not alter the old ledger's
meaning or retroactively insert new counters into old artifacts.

This is **not equal-total-compute**. The primary can establish only competitiveness
at this score cap and proposal recipe. Systems-efficiency claims remain blocked
without a separately justified cost model or matched-cost comparison. More
diagnostic counters alone do not complete that gate. No speed or energy claim
is licensed by the logical-work ceiling or by warm-cache timing.

## Primary estimand and predeclared readout

For source s, let S_sr be the binary exact-success outcome of single16 at root r
and P_s be the one deterministic PUCT outcome. The source contrast is
`D_s = (sum_r S_sr)/4 - P_s`. Compute the mean over128 sources and the unbiased
sample variance over those128 values (denominator127), with exact rational
moments saved. PUCT's one outcome is referenced in four paired descriptions,
not turned into four independent rows. Report its success denominator128 and
single16's repeated-row denominator512 explicitly.

Use the inherited transparent approximate model interval
`mean(D) ± 2 * sample_sd(D) / sqrt(n_sources)`. Its assumptions include sufficiently
independent/exchangeable accepted source clusters and an adequate approximation
for the mean. Deterministic, solvability-filtered, non-replacement generation and
different hashes establish none of those assumptions or interval coverage. It
is not a population-causal claim, a probability assigned to a fixed parameter,
or a seed-population estimate.

The design chooses practical uplift **+0.02** and maximum half-width **0.05**.
These are policy choices, not values fitted to new results. With128 sources,
source SD0.2/0.4/0.6 would give half-widths about0.0354/0.0707/0.1061; the
design is a bounded diagnostic, **not guaranteed power to detect2pp**. Do not
increase the sample after seeing a wide interval.

Apply in this order:

1. An incomplete/invalid matrix: `INCOMPLETE_OR_INVALID`; no complete-study
   readout from the surviving rows. Preserve partial evidence.
2. Fewer than64 sources or zero source variance: interval/precision null and
   `UNRESOLVED`; no degenerate zero-width certainty. The planned matrix still
   requires exactly128 sources.
3. Half-width >0.05: `IMPRECISE`, regardless of point estimate.
4. Lower bound >0.02: `PROMISING_FOR_FRESH_CONFIRMATION` only.
5. Upper bound <=0.02: `NO_PRACTICAL_UPLIFT_SIGNAL` for this model/design, not
   equivalence, universal inferiority or proof of no effect.
6. Otherwise `UNRESOLVED`.

Every status keeps `winner: null` and `scientific_decision: null`. A promising
primary is not a declaration of superiority to all baselines, a cost-efficiency
pass, typed-DSL transfer, default adoption or confirmation.

## Diagnostics that cannot replace the primary

Predeclare single16−mean-off, single16−greedy and single16−beam2 as descriptive
comparisons. Keep every method and both directions of gains/losses, minimum
verified error win/tie/loss/missing, by-source/by-seed tables and leave-one-source
and leave-one-root sensitivity. An absent verified terminal means exact success
false but error/readout/first-hit null; do not impute an error of zero. A paired
error is missing when either operand lacks a verified terminal.

For first-hit work, retain failures and their stopping work as censored/no-hit
observations. Do not compare only successful runs and call that a speed gain.
Record complete action sequences, revisit counts, completed terminal counts,
the first actual branch divergence and its current-state mean/prior/noise
contributions. Passive alternative scores on the same stored history may locate
a choice flip; they are not a counterfactual full rollout or a new search.

Report exact source moments and model-interval caveats for the mean-off
diagnostic too, without giving it a confirmatory pass/fail or multiplicity-free
promotion role. A small point difference or a wide interval cannot establish
that learning is useless. Even a precise small difference is specific to this
feedback/proposal/budget, not evidence against learning generally. Means can
matter while the full method still loses to PUCT; these are different questions.

## Candidate, validation and execution gates

This proposal leaves implementation/runtime hashes and an executable plan digest
unassigned. Before any new data/run, a separate implementation candidate must:

1. Version and test mean-off, its identities and both replay stages while keeping
   all existing methods and artifacts unchanged. Check root/no-history parity,
   controlled mean intervention, budget rejection, deterministic baselines and
   full-cell enumeration on synthetic/public fixtures only.
2. Authenticate all exclusions; bind exact source/runtime hashes, method specs,
   seed derivation table, limits, cell order, complete readout and new exclusive
   attempt slots. Do not use the original C5/locked or consumed attempt paths.
3. Pass full repository validation and a source/claim review. Qualification
   tests are not evidence for the candidate's scientific primary.
4. Obtain explicit human authority for the exact candidate/plan and one run plus
   separate-process complete replay/analysis. Approval of this design PR is not
   that authority.

The eventual analyzer must generatively replay all1,408 cells and independently
rebuild complete source-level reductions from saved terminal/charge events.
Do not invent a 768/6,144 prefix count from earlier allocation studies: this is
one budget and has no planned cross-budget prefix matrix. Validate shared
material at actual common coordinates, not equality of divergent trajectories.

Freeze code, plans and historical evidence during actual operations. Retain
logs, partial output, missingness and UNKNOWNs on failure. No automatic retry,
resume, replacement source, output overwrite, extra condition or changed primary.

## Decisions after evidence, not a preselected winner

If the current method is not competitive, investigate its selection/feedback
or full-action cost before investing in another scheduler. If the mean-off
diagnostic is unresolved, retain that uncertainty rather than declaring return
learning ineffective. If competitiveness is promising, require fresh confirmation
and cost evaluation before the originally reserved no-retuning typed-DSL gate.
No branch of this decision tree automatically authorizes a new experiment.
