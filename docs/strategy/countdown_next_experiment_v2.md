# Countdown next experiment v2

## Objective

The next stage should answer an engineering question:

> At fixed real search work, does the calibrated search find exact solutions
> more reliably than the frozen uncalibrated search and simple deterministic
> baselines across unseen tasks?

It should not be designed primarily to prove QMC or to extend the current
two-task selection ceremony.

## Stop conditions inherited from review

- Do not run the redundant `(1,1) -> (.5,.5)` post-positive switch.
- Do not call IID/Sobol pairs CRN.
- Do not open held-out search outputs before task, proposal, method, budget, and
  analysis manifests are sealed.
- Do not use a fixed 14-dimensional bank for a task suite with a larger action
  bound.
- Do not precompute a full reachable-DAG bank or full provider snapshot for a
  broad suite.

## Two-track design

### Track A: provider-neutral algorithm benchmark

This is the primary engineering benchmark.

1. Seal a source-multiset-disjoint Countdown task suite before search.
2. Use one or more deterministic, hashable proposal policies with controlled
   quality. At minimum:
   - uniform proposal;
   - deterministic heuristic proposal;
   - oracle-correlated positive control, labeled as such.
3. Generate proposals and perturbations lazily for visited states.
4. Derive action dimension from each state or the sealed suite manifest.
5. Persist visited-state inputs, action order, selected vectors, and digests;
   do not persist unused full-DAG banks.

This track measures the exploration algorithm without provider temperature,
API cost, or snapshot coverage as hidden factors.

### Track B: provider-conditioned confirmation

This is secondary and smaller.

1. Select a bounded task subset whose proposal acquisition is affordable.
2. Seal complete proposal inputs before search outcomes are opened.
3. Keep Anthropic and OpenAI as separate strata.
4. Normalize or explicitly report prior concentration so that equal
   `prior_bonus` is not interpreted as equal effective guidance.

## Frozen sampling frame and scale

These are the v2 defaults. Any change requires a new dated preregistration
before evaluation search output exists.

### Track A cohorts

- **Canary/development:** 12 solvable, source-multiset-unique tasks from
  `generate_solvable_task_suite(count=12, seed=26072601)`.
- **Locked evaluation:** 128 solvable, source-multiset-unique tasks from
  `generate_solvable_task_suite(count=128, seed=26072602)`.
- Both calls import the full-task and source-multiset exclusions from the two
  historical development tasks. The evaluation call additionally excludes all
  canary identities.
- Solvability is the only outcome-based inclusion condition and is computed by
  the existing exhaustive generator before search. No task may be removed,
  replaced, or reweighted from any method result.
- Canary uses exploration seeds `7168..7171`. Locked evaluation uses
  `4096..4111`, giving 16 nested perturbation runs per task and method.

The generator already freezes input range `1..10`, target range `100..999`,
canonical fingerprinting, source-multiset uniqueness, attempt counts, and
rejection reasons. The generated task/profile manifest and all exclusion
digests must be committed before evaluation execution.

### Track B cohort

Track B uses exactly 16 of the 128 locked Track A tasks. Rank tasks by

```text
SHA256("provider-track-v1|" + task_fingerprint)
```

and take the lowest 16 bytewise. This selection is independent of search and
provider outcomes. It uses the same 16 exploration seeds. For this bounded
track only, snapshot every reachable proposal state before search. Abort Track
B as `NOT_RUN_COST_GATE` without shrinking the task set if the exhaustive
profile projects more than 25,000 proposal state items per provider. Provider
proposal snapshots and prior-concentration summaries must be complete and
sealed before search; Anthropic and OpenAI remain separate reporting strata.

## Methods

The minimum matched method set is:

- greedy proposal decoding;
- deterministic best-first or beam search;
- PUCT/UCB-style tree search;
- frozen baseline `(prior_bonus=.1, posterior_sd_scale=1)` with IID;
- frozen baseline with Sobol;
- development candidate `(1,1)` with IID;
- development candidate with Sobol.

The selected and baseline configurations are both required. Without both, the
experiment cannot estimate calibration transfer.

A later mechanism experiment may add randomized stratified or Latin-hypercube
normal points. That is the appropriate control for separating marginal
stratification from Sobol joint dependence; it is not required to answer the
first engineering benchmark.

## Randomization and materialization

- Do not materialize the frozen exploration streams until the task manifest is
  frozen.
- Seed identity must include task, canonical state, visit index, action-order
  digest, source, and version.
- Reuse each source-specific stream across configurations where a paired
  configuration contrast is desired.
- IID and Sobol remain distinct matched streams.
- Use counter-based or deterministic node-local generation so storage is
  proportional to visited states.
- Record actual action coordinates used, not only padded coordinates.

## Budgets

Match and report multiple work axes:

- verifier calls;
- edge selections and transitions;
- proposal state evaluations;
- legal-action scores;
- generated perturbation coordinates;
- peak live nodes and bytes;
- wall time as descriptive telemetry.

Primary comparisons should use both a fixed-verifier slice and a fixed
legal-action-score slice. A method that visits cheaper trajectories should not
be described as equal arithmetic merely because it used the same number of
five-edge simulations.

The frozen v2 slices are:

- primary: at most **256 legal-action scores**;
- secondary: at most **8 verifier calls**.

Each method must stop before overshooting its slice. Proposal evaluations,
generated perturbation coordinates, transitions, live nodes, peak bytes, and
wall time remain required telemetry, but are not substituted for the two
matched primary work axes.

## Primary estimands

Keep these separate:

1. **Calibration transfer**

   ```text
   success(candidate) - success(frozen baseline)
   ```

   Report separately for IID and Sobol.

2. **Source effect at the candidate**

   ```text
   success(Sobol) - success(IID)
   ```

3. **Search-algorithm value**

   ```text
   candidate search - greedy/best-first/PUCT baseline
   ```

Secondary diagnostics:

- success AUC and first-hit work;
- exact-terminal reuse after first hit;
- successful-terminal diversity;
- root and depth-wise breadth;
- proposal-rank retention;
- cache and memory telemetry.

## Statistical unit and analysis

Tasks are the independent transfer unit. Exploration seeds are nested
randomization within task.

- For task `t`, method `m`, source `s`, and budget `b`, define the task score as
  the fraction of its 16 exploration seeds that produced at least one exact
  solution before budget `b`. Deterministic baselines contribute their binary
  task result once; they are not duplicated into fake seed samples.
- weight the 128 tasks equally;
- keep provider/proposal strata separate;
- use 10,000 paired percentile task-bootstrap draws with bootstrap seed
  `26072603`;
- report per-task values and the number of tasks;
- do not use thousands of nested seeds as if they were independent tasks;
- a missing or budget-invalid method/task cell fails the gate and is never
  silently dropped; zero-success cells remain zero.

The primary calibration-transfer endpoint is the equal-IID/Sobol average of
candidate-minus-frozen-baseline task-score differences under the deterministic
heuristic proposal and 256-score budget.

Multiplicity is handled in three frozen families:

1. the single primary calibration endpoint uses a two-sided 95% task-bootstrap
   interval;
2. three calibration guardrails use simultaneous 98.333% intervals
   (Bonferroni family alpha `0.05`);
3. three simple-baseline contrasts use simultaneous 98.333% intervals.

The calibration guardrails are the two source-specific 256-score contrasts
and the equal-source 8-verifier contrast. All unlisted task slices,
provider-neutral controls, telemetry, and mechanism measures are exploratory.
Track B provider guardrails form their own two-comparison family with
simultaneous 97.5% intervals.

## Gates

Before the full benchmark:

1. canary every method on all 12 canary tasks and all four canary seeds;
2. require no action truncation and exact action-order agreement;
3. require byte-identical lazy replay from persisted visited-state material;
4. require fixed budget closure on all primary axes;
5. require greedy/best-first/PUCT baselines to be functional;
6. estimate projected provider calls, bank bytes, and wall time;
7. publish the task/proposal/method manifest and its digest.

If canary success is zero for all search methods, repair the substrate before
spending a large seed budget. If simple baselines dominate, treat that as the
engineering result instead of adding semantic routing or pruning.

## Quantitative decision

Use `3 percentage points` as the minimum useful improvement and `-2 percentage
points` as the material-regression boundary.

The `(1,1)` calibration is promoted over `(0.1,1)` only if:

1. the primary calibration-transfer point estimate is at least `+3pp` and its
   95% lower bound is above zero;
2. every calibration guardrail lower bound is above `-2pp`.

The base search is called competitive only if candidate IID:

1. exceeds greedy and deterministic best-first by at least `+3pp`, with both
   simultaneous lower bounds above zero; and
2. is non-inferior to PUCT, with its simultaneous lower bound above `-2pp`.

Sobol action perturbation is promoted separately only if:

1. candidate Sobol-minus-IID is at least `+2pp` at the primary Track A slice
   and its 95% lower bound is above zero; and
2. both provider-conditioned Track B lower bounds are above `-2pp`.

Failure of any gate is a retained engineering result, not permission to change
task weights, margins, method definitions, or the candidate. Breadth alone is
mechanism evidence, not a promotion criterion.

Semantic routing and Bayesian pruning remain downstream experiments. They
should be introduced only after this benchmark identifies a competitive,
scalable base search.
