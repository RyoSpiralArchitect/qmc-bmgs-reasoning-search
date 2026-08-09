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
- Stochastic canary methods use exploration seeds `7168..7171`. Deterministic
  greedy, beam, and PUCT each contribute exactly one row at seed `0`; they are
  never copied across fake seed labels. Locked stochastic evaluation uses
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

The canary proposal cross is also frozen. `uniform/v1` and
`greedy_rollout_target_error/v1` each run the complete seven-method matrix.
`oracle_path_count_positive_control/v1` runs greedy only and is excluded from
all fair comparisons. With 12 tasks and two budget profiles this produces 936
planned cells: 456 uniform, 456 heuristic, and 24 oracle-greedy. The full
method-spec digest, not the shared Thompson `method_id`, is part of every cell
identity. A runtime-bound method-manifest digest is also included so equal
method specs from a different numerical runtime are not interchangeable.

A later mechanism experiment may add randomized stratified or Latin-hypercube
normal points. That is the appropriate control for separating marginal
stratification from Sobol joint dependence; it is not required to answer the
first engineering benchmark.

## Randomization and materialization

- Do not materialize the frozen exploration streams until the task manifest is
  frozen.
- A node stream has one canonical identity containing the task fingerprint,
  canonical serialized state, exploration seed, action count, action-order
  digest, perturbation source, and stream implementation version. Its digest is
  the SHA-256 digest of that complete canonical identity.
- A point identity contains the node-stream digest and the zero-based
  node-local visit index. The visit index is a point coordinate within one
  stream; it is not a new stream seed.
- Configuration, search method, and budget-profile identifiers are excluded
  from the node-stream identity. Consequently, whenever two runs using the
  same perturbation source reach the same state at the same node-local visit,
  they consume the same point. This is the paired configuration contract even
  after their global trajectories diverge.
- IID points use a versioned counter mapping from full point and coordinate
  identities. Sobol points use one versioned node-local Sobol stream. A Sobol
  engine must never be re-seeded per visit and then sampled at its first point;
  point `i` is the `i`th point of the same node stream.
- The Sobol implementation must use an explicitly versioned deterministic
  randomized shift (including a Cranley-Patterson rotation), digital shift, or
  scramble whose key material is derived from the full 256-bit node-stream
  SHA-256 digest. Reducing that digest to a library seed is not sufficient. The
  direction-number version, bit width, key expansion, shift or scramble
  algorithm, and normal-transform version are sealed in the method manifest.
- Reuse each source-specific stream across configurations and budget profiles
  where a paired contrast is desired. Method exclusion from stream identity
  also makes points agree at any shared `(state, local visit)` across stochastic
  methods; this is not a claim that divergent whole trajectories are common
  random numbers.
- IID and Sobol remain distinct matched streams.
- Use counter-based or deterministic node-local generation so storage is
  proportional to visited states.
- Record actual action coordinates used, not only padded coordinates.

Lazy replay has two mandatory stages. First, **generative material replay**
recomputes legal-action order, stream and point identities, uniforms, the
normal transform, and every visited-state vector from the sealed manifests; it
must not trust stored vectors merely because their local digest is
self-consistent. Second, **search replay** consumes only material that passed
the first stage, reconstructs selection, transitions, updates, and all ledger
counters from events, and compares the canonical deterministic search records
byte-for-byte. Volatile telemetry such as wall time, process identifiers, and
resident-memory observations is stored outside the byte-identical replay core.

## Budgets

Match and report multiple work axes:

- verifier calls;
- edge selections and transitions;
- proposal state evaluations;
- legal-action scores;
- generated perturbation coordinates;
- peak live nodes and bytes;
- wall time as descriptive telemetry.

The two action-score counters have distinct meanings:

- `proposal_action_scores` charges once per legal arm when an uncached proposal
  policy evaluates that arm. A cached proposal lookup does not charge it again.
- `legal_action_scores` charges once per legal arm whose current Thompson
  sample, UCB/PUCT index, best-first priority, or deterministic selection value
  is computed or recomputed to select or expand an action. Reading a cached
  proposal value as an input to the current selection formula still incurs this
  selection charge.

Earlier design prose used `selection_action_scores` for the latter quantity;
that is a legacy explanatory alias only. The canonical Track A ledger and all
new manifests use `legal_action_scores`.

Thus the 256-score endpoint is exactly
`legal_action_scores <= 256`; it is neither
`proposal_action_scores <= 256` nor the sum of the two counters. Proposal
scoring remains an independently reported and hard-guarded work axis.

The perturbation-material source charges only
`generated_perturbation_coordinates`; generating a vector is not itself a
selection score. Before the method matrix is implemented, the common harness
must add a single transaction or preauthorization spanning the selection-score
and coordinate work required by one Thompson choice. Sequentially accepting
two independent charges would permit a half-completed selection and does not
satisfy the all-or-nothing contract below.

Primary comparisons should use both a fixed-verifier slice and a fixed
legal-action-score slice. A method that visits cheaper trajectories should not
be described as equal arithmetic merely because it used the same number of
five-edge simulations.

The frozen v2 slices are:

- primary: at most **256 legal-action scores**;
- secondary: at most **8 verifier calls**.

These slices are executed as two separate frozen budget profiles, not as two
competing stopping limits in one run:

- `score256`: `legal_action_scores` is the stopping axis with limit `256`;
  the verifier and every other work axis are non-primary hard guards.
- `verifier8`: `verifier_calls` is the stopping axis with limit `8`;
  selection scoring and every other work axis are non-primary hard guards.

The complete work limits are frozen before canary search, in canonical work-axis
order:

| profile | proposal states | proposal scores | legal scores | coordinates | edges | transitions | verifiers |
|---|---:|---:|---:|---:|---:|---:|---:|
| `score256` | 87 | 317 | 256 | 316 | 86 | 86 | 18 |
| `verifier8` | 41 | 1121 | 1121 | 1121 | 41 | 41 | 8 |

These guards are outcome-blind structural bounds with explicit headroom for
the next atomic action vector.
For a nonterminal Countdown state the legal-action count is at least three and
at most `4*C(n,2)`. Across state widths six through two the maxima are
`60,40,24,12,4`: at most 140 scores and five transitions per trajectory.
Thus score256 can accept at most 85 ordinary selections and 17 terminal
trajectories, while verifier8 can consume at most 1120 scores and 40
transitions. The width-two beam completes within 220 scores and ten retained
edges. A canary cell is budget-invalid if a non-primary guard rejects work or
finishes at exact exhaustion; locked evaluation may begin only if every cell
retains positive non-primary headroom.

The score256 primary and Thompson coordinates are charged in the same atomic
selection receipt. The coordinate guard therefore admits the primary limit
plus a full maximum-width next vector (`256 + 60 = 316`). Proposal scores add
one strict unit (`317`), while proposal-state evaluations admit 85 accepted
selections, one next miss, and one strict unit (`87`). The earlier version-one
`257` guards were superseded before any sealed canary outcome after a
source-disjoint non-canary fixture reproduced coordinate co-blocking.

Each method must stop before overshooting its profile's stopping axis. Before
starting another `verifier8` trajectory, the runner preflights that one verifier
call remains. If none remains, it stops before state lookup, proposal/cache
access, node creation, stream access, or any event or value update. Execution
of a run is single-threaded across this preflight and the terminal verifier
charge.

Every multi-axis charge is atomic. A rejected charge leaves unchanged the
complete ledger, proposal and graph caches, live-node set, node-local visit
indices, IID/Sobol stream positions, materialized points, proposal/selection/
terminal event buffers, learned values, and readout candidates. Search code
charges before cache or node insertion, perturbation generation, transition,
verifier execution, or value update. Proposal evaluations, generated
perturbation coordinates, transitions, live nodes, peak bytes, and wall time
remain required telemetry, but are not substituted for the two matched primary
work axes.

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

1. execute the exact 936-cell proposal/method/budget schedule; deterministic
   methods occur once at seed zero and only stochastic methods use all four
   canary seeds;
2. require no action truncation and exact action-order agreement;
3. require generative material replay followed by byte-identical search replay
   from persisted visited-state material;
4. require fixed budget closure on each profile's stopping axis and prove that
   every non-primary guard was nonbinding in every canary cell;
5. require greedy/best-first/PUCT baselines to be functional;
6. estimate projected provider calls, bank bytes, and wall time;
7. publish the exclusion/task/proposal/method/budget/analysis manifests and
   their byte-level seal before executing any cell.

The canary has no inferential or promotion authority. It reports raw 12-task
vectors and descriptive point estimates only: no confidence interval, p-value,
or winner label. A method comparison is promoted, rejected, or called
non-inferior only by the separately locked 128-task analysis below.

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
