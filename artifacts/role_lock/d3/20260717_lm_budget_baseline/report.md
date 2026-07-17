# QMC-BMGS Role-Lock D3 benchmark

## Outcome

The benchmark harness works, and the first controlled result separates two
claims that were previously bundled together:

1. **Aligned embedding strata help strongly in this positive-control task.**
2. **Sobol/QMC is not yet better than IID posterior sampling.**

This is evidence that the routing mechanism can exploit a useful partition. It
is not evidence that static LM token embeddings represent real reasoning roles,
nor that QMC is superior on this search problem.

## Experiment contract

- Task: `Role-Lock D3`
- Exact terminal target: `PROBE -> DERIVE -> EOS`
- Reward: `+5` only for the exact terminal sequence; all other returns are `0`
- Candidate set: 10 fixed tokens at every prefix
- QMC tail: disabled
- LM prior: behavior guidance only for search methods
- Semantic routing: uniform over clusters (`semantic_uniform_mix=1.0`)
- Search seeds: 32 paired exploration seeds
- Random null: 4 exact size-matched partitions per exploration seed
- LM-prefix-evaluation caps: 16, 32, 48, 64
- Verifier cap: 16 times the LM cap, used only as a saturation guard
- Confidence interval: bootstrap over the 32 exploration seeds; random
  partitions are averaged inside each seed before resampling

The embedding-aligned condition assigns `PROBE` and `DERIVE` to singleton
clusters. The matched-random condition preserves cluster sizes. The misleading
condition instead assigns irrelevant `NULL` tokens to singleton clusters.

## Readout success at each LM-evaluation cap

| Method | 16 | 32 | 48 | 64 |
|---|---:|---:|---:|---:|
| Greedy prior | 0.0% | 0.0% | 0.0% | 0.0% |
| Top-p best-of-N | 0.0% | 0.0% | 3.1% | 3.1% |
| IID Thompson, no strata | 0.0% | 3.1% | 9.4% | 12.5% |
| Sobol Thompson, no strata | 3.1% | 6.2% | 6.2% | 6.2% |
| IID Thompson + embedding strata | 6.2% | 18.8% | 46.9% | **68.8%** |
| Sobol + random size-matched strata | 0.8% | 3.1% | 6.2% | 7.0% |
| Sobol + embedding strata | 3.1% | 6.2% | 25.0% | **56.2%** |
| Sobol + misleading strata | 0.0% | 0.0% | 3.1% | 3.1% |
| Sobol + embedding strata + pruning | 3.1% | 6.2% | 25.0% | **56.2%** |

At cap 64, seed-level bootstrap intervals were:

- IID + embedding: 68.8% `[53.1%, 84.4%]`
- Sobol + embedding: 56.2% `[37.5%, 75.0%]`
- Sobol + random matched: 7.0% `[1.6%, 14.8%]`
- Sobol + misleading: 3.1% `[0.0%, 9.4%]`
- Sobol global: 6.2% `[0.0%, 15.6%]`

The paired cap-64 difference versus global Sobol was:

- Sobol + embedding: `+50.0 pp`, bootstrap `[+31.2, +68.8]`
- Sobol + random matched: `+0.8 pp`, bootstrap `[-7.0, +7.0]`
- Sobol + misleading: `-3.1 pp`, bootstrap `[-9.4, 0.0]`
- IID + embedding: `+62.5 pp`, bootstrap `[+43.8, +81.2]`

## What the controls say

The aligned partition beats both an equal-size random partition and an
explicitly misleading partition. This rules out the simplest explanation that
*any* forced stratification produces the gain.

The random partitions also show the expected alignment gradient at cap 64:

- zero target singleton overlap: 4.2% success
- one target singleton overlap: 15.6% success

That is a useful positive-control result for the routing mechanism.

## What is not supported yet

QMC superiority is not supported. Global Sobol did not beat global IID, and
IID + embedding was numerically stronger than Sobol + embedding in this task.
The intervals overlap, so this is not proof that IID is better either. It means
the next QMC claim must be tested directly across more randomized scrambles,
posterior-noise settings, depths, and task families.

Pruning also produced no success-rate gain here. At cap 64 it deactivated 202
arms across 139 prune batches, with zero oracle-edge prune errors, but the mean
verifier usage rose because the smaller active set repeatedly exploited known
paths. Pruning therefore cannot be called a compute win from LM calls alone;
the verifier-cost dimension matters.

## Claim boundary

Role-Lock is deliberately oracle-aligned. It proves that the current search can
use a helpful partition. It does not prove that
`model.get_input_embeddings().weight` supplies such a partition for natural
language reasoning. Contextual one-step states or short action chunks should be
tested only after retaining the random/misleading controls and charging their
extra model work to the budget.

## Reproduction

```bash
PYTHONPATH=src python3 -m qmc_bmgs.benchmarks.role_lock \
  --depths 3 \
  --seeds 32 \
  --budgets 16,32,48,64 \
  --random-partition-replicates 4 \
  --verifier-budget-multiplier 16 \
  --runs-jsonl artifacts/work/d3_lm_runs.jsonl \
  --summary-json artifacts/work/d3_lm_summary.json
```

Validation completed with `ruff`, `py_compile`, the harness self-test, strict
JSON parsing, candidate-manifest assertions, and zero budget overshoot across
all 1,536 run records.
