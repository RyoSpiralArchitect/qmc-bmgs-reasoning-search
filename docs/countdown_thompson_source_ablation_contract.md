# Countdown matched Thompson source ablation

## Purpose

This is an API-free mechanism comparison over the two frozen Countdown
development proposal snapshots. It asks whether randomized Sobol posterior
perturbations spend eight Thompson simulations differently from IID
perturbations when the search kernel, proposal prior, reward, backup, action
coordinates, and hard guards are fixed.

It is conditional robustness evidence on two public development tasks. Seeds
measure sampler randomization on those fixed tasks; they are not independent
task samples, a held-out benchmark, or evidence of general QMC superiority.

## Why this uses a new IID control

The historical `iid_thompson_8` provider records use a global SHA-counter
Box--Muller stream. Pairing them directly with inverse-CDF Sobol would change
the uniform source, normal transform, stream topology, and scalar allocation at
once.

The clean pair is therefore versioned separately:

- `matched_iid_thompson_8`
- `qmc_thompson_8`

Both read one immutable perturbation bank. The selected source is their only
behavioral factor.

## Frozen workload

- Anthropic proposal behavior:
  `9eaee49f6e100d26100b10b0eb8d9f9ba75f74cb0109d2b25634590117682868`
- GPT-5.6 proposal behavior:
  `529b7dd51458cda3a6899a7b0b406dd8880317b413f39fe0fc08786c4eff8862`
- two tasks, 64 nonterminal states, 259 proposal input values, 352 legal
  actions, and maximum action count 14
- exploration seeds 1024 through 1151 inclusive
- 2 providers x 2 tasks x 2 methods x 128 seeds = 1,024 search records

Both original provider artifacts must pass their offline validators on complete
scratch copies before the proposal bytes are copied into the ablation artifact.
The original source directories remain byte-immutable. No provider client is
constructed. The runner refuses to start while either provider key is present
and denies socket creation for the complete run. Provider calls and estimated
provider cost are fixed at zero.

## Perturbation bank

For every `(task, canonical state, exploration seed)` the artifact stores two
`8 x 14` CPU float64 matrices:

- IID uniforms from a local `torch.Generator`
- scrambled Sobol uniforms from `SobolEngine(...).draw_base2(3)`

Provider and method names are excluded from seed derivation. Canonical state,
task fingerprint, action-order digest, exploration seed, and source name are
included. SHA-256-derived uint32 seeds use deterministic collision resolution,
and the complete seed-map digest is recorded.

Both sources use exactly:

```text
z = sqrt(2) * erfinv(2 * clip(u, 2^-53, 1 - 2^-53) - 1)
```

Uniforms and transformed normals are both persisted. Artifact creation verifies
the transform exactly under the recorded runtime. Ordinary search replay reads
the stored normals and does not regenerate Sobol points or require future Torch
`erfinv` bit identity. Torch and Python versions remain provenance, not silent
assumptions.

At selection time both source vectors are read as audit instrumentation and
only coordinates `0..A-1` in canonical action order are active. The other
coordinates are padding. Non-selected-source generation is not counted as
deployment search compute.

## Fixed Thompson kernel

For action `a`:

```text
base_a    = mean_a + 0.1 * exp(prior_logp_a)
sd_a      = 1 / sqrt(visits_a + 1)
sample_a  = base_a + sd_a * z_a
```

The maximum sampled action is selected with canonical-index ties. Each run
uses eight complete five-edge simulations, exact terminal reward `1/0`,
reverse path updates, `gamma=1`, no shaped reward, no pruning, and no semantic
routing. `m2` is retained for audit but is not used in selection.

Every accepted run must close with:

- eight terminal verifications
- 40 edge selections and transitions
- 40 posterior updates
- eight root visits
- 40 full-vector reads and 560 coordinates per source
- one cache-only readout and zero budget overshoot

Selection action-score work remains the number of real legal actions. It may
differ after trajectories diverge and is reported rather than forced equal.

## Engineering readout

Per run, the artifact records:

- exact success, exact-terminal count, first-hit verifier, and success AUC
- proposal-top-set retention, normalized proposal rank, and prior regret
- noise override and local IID/Sobol choice disagreement
- root visit histogram, entropy, proposal-top visit fraction, and JSD
- unique states/edges/traces, cache reuse, and positive-backup dynamics
- raw multi-axis compute and dual-source instrumentation accounting

The root manipulation check reports one-dimensional star discrepancy for each
active coordinate. The root receives all eight points in every run; deeper
nodes are adaptive and are not treated as an equally clean QMC diagnostic.

Pairing is by provider snapshot, task, and exploration seed. Reports include
IID/QMC discordant successes, conditional McNemar p-values, paired metric
deltas, and seed variance. Intervals describe Monte Carlo stability on each
fixed development task, not task-generalization uncertainty.

## Reproduction

No key or network is allowed:

```bash
env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY \
  PYTHONPATH=src python -m \
  qmc_bmgs.experiments.countdown_thompson_source_ablation \
  --run \
  --anthropic-dir artifacts/work/countdown_anthropic_dev_20260722_live_v3 \
  --openai-dir artifacts/work/countdown_openai_dev_20260724_live_v2 \
  --output-dir artifacts/work/countdown_thompson_source_n128_v2

env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY \
  PYTHONPATH=src python -m \
  qmc_bmgs.experiments.countdown_thompson_source_ablation \
  --replay artifacts/work/countdown_thompson_source_n128_v2
```

The temporary artifact must pass full validation before it is atomically
published. Replay verifies copied proposal bytes, frozen source receipts,
bank/state/seed identities, record digests, exact terminal traces, compute
closure, paired latent-vector digests, summary recomputation, and byte-identical
search JSONL reconstruction.
