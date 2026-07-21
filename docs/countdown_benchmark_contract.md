# Countdown-D6 benchmark substrate contract

## Role

This milestone replaces exact token-prefix states with a small executable
planning environment. It establishes a shared task adapter, exact verifier,
canonical graph state, compute ledger, and exhaustive difficulty calibrator.

It is plumbing and task-definition work, not evidence that QMC-BMGS is stronger
than a baseline. Search methods and a locked evaluation cohort come next.

## Task rules

`countdown_d6_v1` supplies exactly six positive integers and one positive target.
Every source number must be used exactly once. A valid solution therefore has
five action chunks and leaves one value equal to the target.

An action selects two currently available values and one operator:

- addition and multiplication are commutative and use a canonical operand order;
- subtraction is oriented and legal only when the result is positive;
- division is oriented and legal only for an exact positive integer quotient.

Zero, negative, fractional, and source-reusing transitions are invalid. Equal
source values are indistinguishable at the search-state level: choosing either
copy produces the same future numeric state and is one arm, not duplicated arms.
Operator-labelled actions remain distinct even when they reach the same child;
for example, `2 + 2` and `2 * 2` are two parallel arms that both produce `4`.

## State and graph identity

The numeric state is the sorted multiset of current integer values. Any cache or
policy graph key must namespace it by a deterministic task/ruleset fingerprint
that hashes the ruleset version, sorted source multiset, and target. Input
permutations of the same problem therefore have one identity. A bare multiset must never collide
across tasks, because terminal success and a target-aware proposal are task-local.

Expression provenance is not part of numeric state identity. This merge is
Markov-safe inside one task because future legal actions and transitions depend
only on the current multiset, while terminal success also receives the namespaced
task target. Readout must retain a trace-specific root-to-terminal action list;
it must not reconstruct an expression from one parent pointer on a merged node.
The verifier independently replays that complete trace from the original sources.

Different action orders may reach the same multiset. Countdown is therefore a
real directed acyclic graph rather than the exact-prefix tree used by Role-Lock.
The number of remaining values strictly decreases at every transition.

## Exact verifier and feedback boundary

The verifier independently replays action chunks from the original six values,
reconstructs an expression, checks every operation, checks that all sources were
consumed exactly once, and compares the final integer with the target.
When equal current values have different provenance, replay uses a canonical
term/AST order so expression and witness digests do not depend on Python traversal
order.

Search feedback in the first benchmark is terminal exact only. The exhaustive
solver's witness, solution count, distance, and reachable-state information are
calibration metadata and must never enter proposal logits, action values,
semantic routing, pruning, or readout.

Operator family may be used as an exploration stratum. It is a routing label
only; values are not shared across actions or states because they share `+`,
`-`, `*`, or `/`.

## Exhaustive calibration

The download-free calibrator exhaustively enumerates the canonical DAG and
reports strict, deterministic metadata including:

- unique states by remaining-value count;
- legal action edges and branching totals;
- unique terminal values and exact-solution reachability;
- exact canonical action-label-sequence counts and solution-path counts;
- root actions that can reach a solution;
- multi-parent/transposition edges;
- operator-family action counts;
- a deterministic state-space digest.

One witness may be returned for verifier self-tests or explicit single-task
debugging (`--include-witness`), but ordinary outputs and locked task manifests
store at most a witness digest. Candidate generation and calibration use an
explicit seed, sample targets independently from a fixed range, and reject
duplicate full task fingerprints. Calibration tasks and locked evaluation tasks
must be unique and disjoint by canonical fingerprint, not merely by RNG seed.
The primary suite also keeps canonical source multisets unique and disjoint
across splits; otherwise statistical resampling must cluster at source-multiset
level rather than treating different targets over the same numbers as independent.
Each generated split records the count and digest of every excluded task/source
identity set; `--exclude-suite` verifies and imports those identities from the
prior split rather than relying on a different seed as evidence of disjointness.
The locked primary cohort is conditioned on exhaustive solvability; generation
manifests retain attempt counts and duplicate/unsolvable rejection reasons.
Unsolvable tasks may form a separate verifier negative-control cohort, but are
not mixed into the primary success denominator.

Path counts treat different operator labels and different orders of independent
operations as different action sequences. They do not multiply paths because
indistinguishable copies of the same operand could have been assigned different
source indices.

Because all-six-use tasks always have five actions, path length is not a
difficulty signal. Solution-path density, solution-bearing root-arm fraction,
branching, and transposition structure are calibration descriptors rather than
claims of a single true difficulty scale.
Evaluation tasks are never selected, removed, or reweighted from method results.

## Matched compute ledger

No weighted scalar is called "equal compute" in this substrate milestone. Every
method must share atomic hard limits and exact integer counters for:

- proposal batch calls and state items in those batches;
- proposal input values, counting the target feature as well as current values;
- proposal action scores for every legal arm scored before top-p truncation;
- selection action scores recomputed while choosing a Thompson/PUCT/best-first arm;
- edge selections;
- transition evaluations;
- verifier evaluations.

Cache hits/misses and unique canonical states are recorded separately. A charge
that would exceed any axis fails before changing any counter. Common ceilings
alone are not called equal compute: methods must continue to the declared cap,
match actual primary proposal/model-work usage, and keep transition, edge, and
verifier axes as hard guards. Readout may not consume hidden proposal, transition,
or verifier work. Wall time remains a secondary systems measure.

Search code must charge before node creation, cache insertion, RNG draw, or value
update. A rejected charge leaves the complete ledger snapshot, graph/cache, RNG
state, and learned values unchanged. Any deterministic outside-budget final
readout uses existing cached state only and is recorded in a separate
evaluation-only counter.

## Next locked comparison

The next experiment will share tasks, candidates, proposal prior, cache policy,
readout, and compute limits across:

1. greedy;
2. top-p best-of-N;
3. plain IID Thompson;
4. PUCT or best-first search;
5. the fixed Sobol-routing / IID-action QMC profile.

Pruning and shaped rewards stay off in the first comparison. The independent
statistical unit is the task, with exploration seeds nested inside task. Primary
uncertainty is therefore task-clustered rather than treating every task/seed run
as an independent replicate. Each task receives equal weight after averaging its
seed replicates, and paired resampling carries every method/seed row for a task
together. Reusing the same seed label after methods diverge is not by itself a
claim of common random numbers.

## Promotion and transfer gate

Arithmetic calibration may freeze shared settings, but it cannot by itself
establish a general search advantage. Promotion requires higher exact success at
matched compute, or matched success at clearly lower compute, followed by an
unchanged transfer to a small typed-DSL synthesis environment with an executable
verifier.

Standard telemetry carries forward correct-path reach only when a path is used
for offline diagnosis, final-action selection rate, canonical-state coverage,
transposition reuse, time-to-first exact solution, and the concentration of exact
solutions across tasks and seeds.
