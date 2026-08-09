# Countdown prior/noise calibration grid

## Preregistration status

This document freezes the development calibration design before any result from
the calibration grid is generated, summarized, or inspected. It must not be
edited in response to a grid outcome. A later correction requires a new
versioned contract and a fresh seed cohort; it cannot silently replace this
experiment.

The experiment selects at most one **calibration configuration** for a later
held-out comparison. It does not select a perturbation source and cannot by
itself establish QMC superiority.

## Post-run errata, 2026-07-26

This section is an explicit post-run correction layer. It does not alter the
machine preregistration, seed cohort, grid, eligibility, ranking, or frozen
decision.

- “Common random number” is too broad for the IID/Sobol contrast. Random values
  are reused across configurations and provider snapshots within each source.
  IID and Sobol use distinct source-specific streams and form matched
  dual-stream blocks, not IID/Sobol CRN blocks.
- The frozen v1 summary stores paired means and seed variances but omits the
  paired conditional intervals promised below. They are reconstructed by the
  independent post-hoc adversarial audit rather than inserted into the frozen
  summary.
- Full `--replay` now requires both original provider artifact directories and
  revalidates them on scratch copies. `--replay-search-only` is the explicit
  self-contained mode that reconstructs search bytes without claiming original
  source revalidation.
- “Source-robust” below means only that a configuration passed the frozen
  gates. It does not mean source effects are small or statistically stable.
- The selected-only held-out plan below cannot estimate calibration transfer.
  It is superseded by
  `docs/strategy/countdown_next_experiment_v2.md`, which includes the frozen
  `(0.1,1)` baseline and simple search baselines.

## Frozen development inputs

The grid uses the same two public Countdown development tasks as the matched
source ablation:

- `(1, 1, 1, 1, 1, 1) -> 6`
- `(1, 1, 1, 1, 1, 2) -> 10`

The proposal policies are the already frozen provider snapshots:

- Anthropic behavior digest:
  `9eaee49f6e100d26100b10b0eb8d9f9ba75f74cb0109d2b25634590117682868`
- GPT-5.6 behavior digest:
  `529b7dd51458cda3a6899a7b0b406dd8880317b413f39fe0fc08786c4eff8862`

Both original provider artifacts must pass their existing validators on
complete scratch copies before any row is copied into the calibration
artifact. The source directories remain byte-immutable. The grid constructs no
provider client and makes no network call.

## Frozen grid

Only two positive scalar parameters vary:

```text
prior_bonus        = {0.1, 0.5, 1.0}
posterior_sd_scale = {0.25, 0.5, 1.0}
```

For action `a`, configuration `(b, c)` uses:

```text
base_a   = mean_a + b * exp(prior_logp_a)
sd_a     = c / sqrt(visits_a + 1)
sample_a = base_a + sd_a * z_a
```

The nine cells are ordered before observation by `prior_bonus` ascending and
then `posterior_sd_scale` ascending. The current calibration
`(prior_bonus=0.1, posterior_sd_scale=1.0)` is the preregistered baseline and is
part of the grid.

Every cell contains both:

- `matched_iid_thompson_8`
- `qmc_thompson_8`

Everything else is fixed:

- eight complete five-edge simulations;
- exact terminal reward `1/0`;
- reverse path updates and `gamma=1`;
- maximum action count 14;
- canonical-index tie breaking;
- no shaped reward;
- no pruning;
- no semantic routing;
- `m2` retained for audit but unused in selection.

Each accepted run closes with exactly:

- eight terminal verifications;
- 40 edge selections and transitions;
- 40 posterior updates;
- eight root visits;
- 40 full-vector reads and 560 coordinates for each stored source;
- zero budget overshoot.

Selection action-score work is the number of real legal actions encountered.
It is reported and may differ after trajectories diverge; it is not padded to
force equality.

## Fresh common-random-number cohort

The exploration seeds are exactly `2048..2175`, inclusive: 128 fresh seeds
disjoint from the source-ablation cohort `1024..1151`.

One new immutable dual-source perturbation bank is generated for every
`(task, canonical state, exploration seed)`. The same stored bank is reused by
all nine configurations and both provider snapshots. Provider, method, and
calibration configuration are excluded from bank seed identity. Seed identity
contains only:

- task fingerprint;
- canonical state;
- action-order digest;
- exploration seed;
- perturbation source.

For this exact task and seed cohort, the preregistered seed plan is:

```text
version:               sha256-uint32-linear-probe/v1
entries:               16,384
collision_resolutions: 0
max_probe:             0
seed_map_digest:       1d5e37cd950b87351de27e04cf571e8bb90aad4bfb2400068b2647e82e9e70b0
```

Both sources store `8 x 14` CPU float64 uniforms and normals. The transform is:

```text
z = sqrt(2) * erfinv(2 * clip(u, 2^-53, 1 - 2^-53) - 1)
```

Transform identity is checked when the artifact is created. Ordinary replay
consumes the stored normals and does not regenerate Sobol points.

The complete workload is:

```text
9 configurations x 2 providers x 2 tasks x 2 sources x 128 seeds
= 9,216 search records
= 4,608 paired IID/QMC blocks
```

The artifact stores 256 shared bank records and 1,024 search records per
configuration. Search records may be sharded by configuration, but all nine
shards are one indivisible experiment.

## Preregistered readout

### Reward conversion

- exact-success count and rate;
- IID/QMC paired discordance;
- success AUC over the eight verifier calls;
- exact-terminal count;
- first exact verifier;
- simulations before the first positive backup;
- positive posterior action and update counts.

### QMC mechanism

- root coordinate-wise star discrepancy;
- root unique arms, normalized visit entropy, and maximum visit share;
- unique states, edges, and terminal traces;
- local IID/Sobol choice disagreement.

Root discrepancy is the clean manipulation check because every root coordinate
receives all eight points. Deeper adaptive trajectories are not interpreted as
an equally direct discrepancy experiment.

### Proposal preservation

- proposal top-set retention;
- normalized proposal rank;
- prior regret;
- proposal-top override rate;
- root proposal-top visit fraction;
- root JSD from the proposal prior.

### Audit and stability

- complete compute counters and cache telemetry;
- seed variance and paired conditional intervals;
- bank, vector, trace, record, summary, and manifest digests.

Conditional intervals describe sampler randomization on each fixed task. They
are descriptive and are not an alpha-based promotion decision.

## Validity gate

The grid is valid only if every condition below passes:

1. Exactly 64 copied proposal rows exist for each provider, 256 bank records
   exist, and all 9,216 search records exist.
2. Every one of the 4,608 provider/task/configuration/seed blocks contains
   exactly one IID and one QMC record.
3. Missing, duplicate, unknown, or reordered task/action/configuration
   identities are zero.
4. All records reference the exact preregistered grid, seed range, formulas,
   source behavior digests, action ordering, and shared bank digest.
5. Shared `(task, state, seed, source)` vectors have zero digest mismatches
   across provider snapshots and configurations.
6. Every run satisfies the fixed compute closure and has zero overshoot.
7. The source validators, credential guard, network denial, seed-plan check,
   normal-transform check, raw-record reconstruction, and summary
   recomputation all pass.
8. The complete temporary artifact validates before atomic publication.

Any failure yields `INVALID_GRID`. No calibration decision is evaluated from a
partial or repaired-in-place result.

## Eligibility gate

Eligibility is evaluated independently for every calibration configuration
using full-precision values. Rounded report values are never decision inputs.

### Mechanism activity

- On each task, Sobol root discrepancy must be lower than IID for at least 95%
  of the 128 seeds.
- In every provider-by-task stratum:
  - `QMC - IID root_visit_entropy >= 0.02`;
  - `QMC - IID unique_edge_count >= 1.0`.

The discrepancy condition is a property of the common bank and therefore does
not create nine independent manipulation checks.

### Terminal-feedback entry

Every one of the eight
`provider x task x perturbation-source` cells must have at least one
exact-success seed. In particular, a configuration with zero QMC successes on
the `->10` task under either provider snapshot is ineligible.

### Proposal-preservation guardrail

For every provider-by-task-by-source cell, compare the candidate with the
preregistered `(0.1, 1.0)` baseline on the same fresh banks:

```text
candidate top_set_retention
    >= baseline top_set_retention - 0.02

candidate mean_normalized_prior_rank
    <= baseline mean_normalized_prior_rank + 0.02
```

These tolerances cannot be relaxed after observing the grid.

## Source-symmetric decision rule

The signed QMC-minus-IID success delta is not a selection objective. Eligible
configurations are ranked lexicographically by the following frozen tuple:

1. maximize the minimum exact-success rate across all eight
   provider/task/source cells;
2. maximize the minimum success AUC across those eight cells;
3. maximize the minimum mean exact-terminal count across those eight cells;
4. minimize the maximum absolute IID/QMC exact-success-rate gap across the four
   provider/task strata;
5. maximize the minimum QMC-minus-IID root-entropy delta across the four
   provider/task strata;
6. minimize distance from the current baseline, where
   `distance = abs(log(prior_bonus / 0.1))
   + abs(log(posterior_sd_scale / 1.0))`;
7. resolve any remaining tie by the preregistered numeric cell order.

Except for the explicit QMC mechanism checks, interchanging the IID and QMC
labels leaves this decision unchanged. The grid therefore selects a
source-robust calibration region, not the cell with the most favorable
post-hoc QMC contrast.

If no configuration is eligible, the completed experiment emits:

```text
selection_status: NO_STABLE_CALIBRATION_REGION
selected_config: null
```

This is a valid negative engineering result, not a pipeline failure. The grid
must not be widened, thresholds must not be changed, and a visually favorable
ineligible cell must not be carried forward under this contract.

If a configuration is selected, its status is
`CALIBRATION_CANDIDATE_FROZEN`. That label is not a QMC performance claim.

## Freeze before held-out

Before any held-out search output is opened, the selected configuration is
written to an immutable freeze record containing:

- the complete grid and decision-rule version;
- every eligibility result and the selected lexicographic tuple;
- selected configuration or explicit null selection;
- code commit SHA and runtime provenance;
- source behavior and copied-proposal digests;
- development task fingerprints;
- exploration seed range, seed-map digest, and perturbation-bank digest;
- raw shard, summary, and manifest digests;
- held-out task-manifest and held-out proposal-snapshot digests.

The held-out runner must refuse configuration, source, task-manifest, code, or
digest drift from this freeze record.

## Held-out prerequisites

The current frozen proposal snapshots cover only the 64 nonterminal states of
the two development tasks. They cannot score a genuinely unseen Countdown
task suite.

Before the calibration summary is inspected, held-out evaluation therefore
requires one of:

1. a held-out task manifest and complete provider proposal snapshots acquired,
   validated, and sealed without exposing held-out search outcomes; or
2. a separately preregistered deterministic local proposal policy capable of
   scoring every held-out state.

Without one of these, the project may preserve the grid as development
evidence but cannot claim task transfer. Provider acquisition performed after
configuration selection must not be silently treated as the same frozen-source
experiment.

The reserved held-out sampler cohort is `4096..4223`, inclusive. Only the
frozen configuration and its matched IID/QMC pair may run on held-out tasks.
Tasks, not nested sampler seeds, are the independent transfer unit; tasks
receive equal weight and providers remain separate strata.

## Claim boundary

This grid is a calibration diagnostic conditional on:

- two public development tasks;
- two frozen proposal snapshots;
- one fixed eight-simulation Thompson kernel;
- the preregistered seed cohort and scalar grid.

It does not establish:

- general QMC superiority;
- provider or model superiority;
- task generalization;
- an independent sample of 9 x 128 experiments;
- a causal explanation for success or failure;
- a reusable optimal prior/noise setting outside this workload.

Common-random-number reuse makes grid cells deliberately correlated. Seed-level
intervals quantify Monte Carlo stability within the two tasks and must not be
reported as task-level uncertainty.

## Replay contract

Replay is credential-free and network-denied. It must:

1. validate both frozen source artifacts on scratch copies without mutation;
2. verify copied proposal bytes, behavior receipts, task/action identity, and
   preregistered grid metadata;
3. verify the exact fresh seed plan and every stored bank/vector digest;
4. process all nine configuration shards, preferably sequentially, and
   reconstruct their canonical JSONL bytes;
5. recompute terminal traces, per-run metrics, compute closure, cell summaries,
   eligibility, lexicographic selection, and the top-level summary solely from
   raw records plus this frozen contract;
6. verify summary and manifest digests and reject missing, extra, or reordered
   shards;
7. reproduce `NO_STABLE_CALIBRATION_REGION` as successfully as a selected
   configuration.

Production run/replay mode accepts no grid or seed override. A separate
self-test may use a reduced cohort, but it cannot emit an evidentiary decision.
The `(0.1, 1.0)` generalized kernel must also have a regression test against the
finalized matched-source kernel, while the finalized v2 artifact and replay
digests remain unchanged.
