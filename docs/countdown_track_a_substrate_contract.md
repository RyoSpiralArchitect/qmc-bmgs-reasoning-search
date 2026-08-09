# Countdown Track A substrate contract

## Scope

This milestone supplies the provider-neutral accounting and perturbation layer
needed by the frozen Track A benchmark. It does **not** implement the search
method matrix, seal canary tasks, run held-out outcomes, or establish an IID or
QMC performance claim. The legacy fixed-14-dimensional calibration artifacts
and schemas remain unchanged.

The executable surface is:

```bash
qmc-bmgs-countdown-track-a-substrate --self-test
```

The download-free self-test uses a real Countdown root with 53 legal actions,
materializes exactly 53 selected-source coordinates, and requires byte-identical
generative replay. It intentionally charges zero legal-action scores because
this milestone generates perturbations but does not execute a selection rule.

## Atomic work ledger

`TrackAWorkLedger` gives every future Track A method the same seven hard axes:

- proposal state evaluations;
- proposal action scores;
- legal-action scores, meaning current selection/expansion scores;
- generated perturbation coordinates;
- edge selections;
- transitions;
- verifier calls.

All limits are explicit non-negative integers. One multi-axis charge either
updates every requested counter or updates nothing. Rejection does not change
usage, charge index, live-storage gauges, or peaks. Search integration must call
the ledger before RNG generation, cache or node insertion, transitions,
verification, or value updates.

Live nodes and bytes are current/peak telemetry, not a substitute for a work
budget. Wall time and process telemetry remain outside the deterministic core.

The later method harness will define `score256` and `verifier8` as separate
budget profiles, as specified in
[`countdown_next_experiment_v2.md`](strategy/countdown_next_experiment_v2.md).
Their non-primary guard values are intentionally not guessed in this substrate
milestone; they must be sealed before canary execution and must remain
nonbinding in every canary cell.

## Dynamic node-local streams

There is no padded vocabulary-wide or reachable-DAG bank. A node is
materialized only after an accepted coordinate-generation charge and only for
the selected source. Perturbation generation charges
`generated_perturbation_coordinates` only; it neither performs nor claims
`legal_action_scores`. The future method harness owns selection scoring as a
separate semantic operation. Its dimension is exactly the legal-action count
returned by the task adapter. The complete ordered action list and its digest
are persisted. A
reordered, missing, extra, or terminal action request fails before charge or
stream advancement.

Schema v1 seals the exact `CountdownTask` implementation, not merely its
serialized fields or fingerprint. Subclasses are rejected at identity build,
live generation, source construction, and replay boundaries so an override of
`legal_actions` cannot retain the same persisted identity with different
behavior.

The stream identity contains:

- task fingerprint and ruleset;
- canonical state;
- exploration seed;
- exact action count and action-order digest;
- source and generator/runtime version.

Method, calibration configuration, and budget-profile names are excluded. Two
paired configurations that reach the same state, source, and node-local visit
therefore receive the same point. IID and Sobol remain different sources.

The point identity is the stream digest plus its zero-based node-local visit.
IID coordinates use a SHA-256 counter mapping to exactly open-unit 51-bit
midpoints. The extra binary64 spacing prevents either endpoint from appearing.
Sobol visits use consecutive points from one fixed node-local sequence; a visit
is never implemented by reseeding and taking another first point.

IID metadata and runtime conformance are source-specific: IID construction,
generation, and replay do not instantiate a Sobol engine or inherit Sobol
dimension/depth bounds. IID retains independent generic serialization and
allocation safety bounds.

PyTorch's scrambled Sobol seed effectively aliases at 32 bits in the pinned
development runtime. Track A therefore does not treat a wider integer passed to
that API as a full-width stream key. It uses the fixed unscrambled CPU float64
Sobol sequence followed by a coordinate-wise Cranley-Patterson rotation keyed
from the full stream SHA-256 identity. Generator, direction-number bounds,
runtime, dtype, architecture, a fixed runtime-conformance digest, and the
inverse-normal transform are stored and versioned. This is the exact Track A
schema-v1 randomized-QMC source; it is not described as an Owen scramble.

Track A v2 uses a single-threaded deterministic scheduler. Parallel calls into
one source/trace are outside this schema because they would make node-local
visit order scheduler-dependent. A future parallel implementation requires a
new versioned allocation and replay contract. Until then, parallelism is only
allowed across independent runs, never within one run.

## Trace and replay

Every deterministic event contains its index, predecessor digest, payload,
optional accepted charge delta and usage receipt, and its own SHA-256 digest.
The final record binds the event count, final chain digest, run identity, and
complete ledger snapshot. Strict loading rejects duplicate JSON keys,
non-finite values, noncanonical bytes, field drift, broken event order, usage
that cannot be reaggregated, and any overshoot.

Before charging a draw, the source atomically reserves the one event slot
needed for an existing node or the two slots needed for a new node plus its
point. Insufficient capacity fails before ledger, source, or trace mutation. A
budget rejection releases a successful reservation before returning. Direct
appends cannot consume capacity reserved by another operation.

The typed run identity separately binds task-manifest digest, selected source,
exploration seed, runtime digest, method, configuration, budget profile, and
work limits. Method/configuration/profile are intentionally absent from the
node stream identity but remain present at the run layer. Replay requires the
externally sealed run-identity digest, preventing substitution of a different
internally valid source or seed. One live source also binds to one ledger after
its first accepted draw.

The substrate implements **generative material replay**: it recalculates the
task's canonical action order, stream identity, Sobol/IID uniforms, normal
transform, point vectors, coordinate-only charge deltas, event chain, and final
ledger. It does
not trust a stored vector merely because an attacker also recomputed the local
digests. Every perturbation-draw receipt must replay with
`legal_action_scores == 0`; a self-consistent trace that folds selection work
into this materialization event is rejected.

This separation is not yet a transaction for a complete Thompson selection.
The next method harness must add one common preauthorization/transaction for
selection scores plus coordinates; two sequential accepted charges would not
meet the frozen all-or-nothing selection contract.

Full **search replay** remains a gate for the next method-harness milestone. It
must consume only material that passed generative replay and reconstruct
selection, transitions, posterior updates, terminal decisions, and budget
closure byte-for-byte. No canary or locked evaluation is authorized by this
substrate alone.

If an unexpected generator or trace exception occurs after an accepted charge,
the source is permanently poisoned. The partial run cannot be finalized as a
valid trace and must be discarded; execution never continues from partially
committed work.

## Current engineering claims

Tests establish only that:

- a 53-action state is handled without truncation or padding;
- a rejected coordinate charge or event-capacity preflight consumes no node,
  point, event, reservation, or node-local visit;
- sequential and random-access node-local points agree under state
  interleaving;
- paired identities reproduce while IID and Sobol remain distinct;
- the full-SHA rotation separates identities that alias under a 32-bit library
  seed;
- self-consistent vector tampering fails independent generative replay.

These are substrate and integrity results, not evidence that QMC search is
stronger than greedy, best-first, PUCT, or IID Thompson search.
