# Countdown provider development observation — 2026-07-24

## Status

This is a development observation, not a benchmark result.

Both live providers completed the same 64-state acquisition, strict artifact
validation, 12 local-search records, and byte-identical offline replay. The
useful engineering signal is that proposal shape materially changes search
behavior—and that the current IID Thompson configuration failed to exploit the
stronger-looking GPT proposal on these two tasks.

It does **not** establish Anthropic/OpenAI/model/method superiority. There are
only two public development tasks, two stochastic seeds, no repeated provider
samples, divergent realized search work, and no QMC method in this canary.

## Frozen local sources

| Surface | Anthropic | OpenAI |
|---|---|---|
| Scratch artifact | `artifacts/work/countdown_anthropic_dev_20260722_live_v3` | `artifacts/work/countdown_openai_dev_20260724_live_v2` |
| Model | `claude-haiku-4-5-20251001` | `gpt-5.6-sol` |
| API / SDK | Messages `2023-06-01` / `0.116.0` | Responses / `2.45.0` |
| Reasoning setting | n/a | `effort=none` |
| Manifest SHA-256 | `843b2437000818e225315029e3e9f08cb7325c765406e8505a34fa6dd46c7005` | `f69f1a04065a93da495c97a191f38fe7d4a67a603ed58dfbe3930f1adedc8e51` |
| Proposal behavior digest | `9eaee49f6e100d26100b10b0eb8d9f9ba75f74cb0109d2b25634590117682868` | `529b7dd51458cda3a6899a7b0b406dd8880317b413f39fe0fc08786c4eff8862` |

These artifacts remain ignored scratch evidence. The digests make this note
auditable but do not promote the underlying rows into locked benchmark data.

An earlier OpenAI `live_v1` completed, but was excluded after review found that
the adapter did not prove the absence of unknown non-message output items.
`live_v2` was reacquired after restricting output items to `reasoning|message`
and requiring one assistant-role message. All 64 v2 responses contained one
message and no reasoning item. The excluded v1 incurred an estimated
USD 0.214965; audited v2 incurred USD 0.214875, for USD 0.429840 estimated
OpenAI spend during this iteration.

## Pairing gate

The comparison joins on task fingerprint, canonical state, and full action
identity—not provider-local action IDs alone.

- 2/2 task identities match.
- 64/64 state identities match.
- 352/352 legal actions and action ordering match.
- 64/64 provider payloads and payload digests match.
- 64/64 output-schema digests match.
- The system instruction and `log_softmax(score / 100)` normalization match.
- Both provider validators and network-free replay pass.

The acquisition workload is 259 input values and 352 action scores. The larger
numbers in each search record are per-search hard ceilings, not acquisition
totals.

## Provider acquisition telemetry

| Metric | Anthropic live-v3 | GPT-5.6 live-v2 |
|---|---:|---:|
| Attempts / valid responses | 64 / 64 | 64 / 64 |
| Failures / recovered rows | 0 / 0 | 0 / 0 |
| Input tokens | 31,718 | 17,025 |
| Output tokens | 4,410 | 4,325 |
| Cache read / write tokens | 0 / 0 | 0 / 0 |
| Reasoning tokens | n/a | 0 |
| Estimated actual USD | 0.053768 | 0.214875 |
| Reserved USD | 0.425984 | 2.621440 |
| Summed serial latency | 96.520 s | 128.483 s |
| Median request latency | 1.354 s | 1.740 s |
| p95 request latency | 2.463 s | 3.358 s |
| Maximum request latency | 3.936 s | 5.041 s |

Token, price, and latency values are systems telemetry only. Tokenizers,
structured-output accounting, prices, and network paths differ, so this table
must not be read as a model-efficiency ranking.

## Proposal snapshot shape

| Metric across 64 states / 352 actions | Anthropic | GPT-5.6 |
|---|---:|---:|
| Distinct integer scores | 21 | 32 |
| Scores equal to 0 | 104 | 109 |
| Scores equal to 1000 | 25 | 69 |
| States containing a 1000 | 21 | 44 |
| All-action ties | 6 | 1 |
| Tied maxima | 14 | 20 |
| Mean normalized entropy | 0.4367 | 0.3784 |
| Median normalized entropy | 0.4048 | 0.4018 |
| Mean top-action mass | 0.7073 | 0.6812 |
| Median top-action mass | 0.7830 | 0.5975 |

The GPT scores use a wider/extremer range and hit 1000 more often, but they
also create more tied maxima. “GPT is more confident” is therefore not a safe
summary. The supported description is: **more extreme scores, with more
upper-bound ties and a heterogeneous prior shape**.

At the two roots the difference is concrete:

- `(1,1,1,1,1,1) -> 6`: Anthropic scores `+`, `*`, `/` equally at 167;
  GPT scores them 1000, 0, 0.
- `(1,1,1,1,1,2) -> 10`: Anthropic's top action is `1*2` at 200;
  GPT's top action is `1+2` at 1000, followed by `1*2` at 950.

## Tie-safe paired diagnostics

Jensen–Shannon divergence uses the common normalized priors and is divided by
`ln(2)`. Kendall tau-b retains tied ranks. The preferred aggregate first
averages states within each task and then weights both tasks equally.

| Diagnostic | Pooled states | Equal-task macro |
|---|---:|---:|
| Nonempty top-set overlap | 41/64 = 0.6406 | 0.6542 |
| Exact top-set equality | 22/64 = 0.3438 | 0.3250 |
| Top-set Jaccard | 0.4551 | 0.4460 |
| Unique-top agreement | 22/35 = 0.6286 | 0.6200 |
| Kendall tau-b | 0.5809 over 57 defined states | 0.5553 |
| Normalized JSD | 0.3550 | 0.3622 |
| Entropy delta, GPT − Anthropic | −0.0583 | −0.0702 |
| Top-mass delta, GPT − Anthropic | −0.0261 | −0.0121 |

The snapshots have moderate positive rank agreement, but they are far from the
same proposal policy. Top-set equality on only 22/64 states and JSD around
0.36 are large enough that downstream search should be expected to branch
differently.

## Local search observation

All rows use exact terminal reward only. Greedy is a low-cost anchor; the other
methods share hard guards but do not necessarily realize equal work.

| Method | Exact rows, Anthropic | Exact rows, GPT | Verifiers A / GPT | Transitions A / GPT | Selection scores A / GPT |
|---|---:|---:|---:|---:|---:|
| `greedy` | 0/2 | 2/2 | 2 / 2 | 10 / 10 | 60 / 70 |
| `best_first_8` | 1/2 | 2/2 | 16 / 16 | 110 / 70 | 278 / 277 |
| `top_p_best_of_8` | 0/4 | 3/4 | 32 / 32 | 160 / 160 | 843 / 1,034 |
| `iid_thompson_8` | 0/4 | 0/4 | 32 / 32 | 160 / 160 | 828 / 839 |

With the GPT snapshot, prior-following greedy, best-first, and top-p produced
exact traces; the current IID Thompson method did not. This does not identify a
cause, but it sharply narrows the next engineering question.

The present Thompson configuration has only eight terminal-return simulations,
uses `posterior_sd = 1 / sqrt(visits + 1)`, and gives proposal probability a
coefficient of 0.1. Its stored `m2` is not used in selection.
When no early exact terminal is found, the reverse backup supplies no positive
signal and posterior noise can dominate useful proposal ordering. The
implementation uses `0.1 * exp(prior_logp)`, so at the GPT `->6` root the
prior-component gap between the 0.9999 action and each 0.000045 action is only
about `0.099986`, roughly one tenth of the initial unit-scale Thompson noise.
This is a testable mechanism hypothesis, not a post-hoc conclusion.

## Next experiment

Use both frozen snapshots with no further provider calls:

1. Add `qmc_thompson_8` beside the existing IID Thompson implementation.
2. Change only the posterior perturbation source first: IID normal versus
   randomized Sobol normal. Keep semantic routing off for this comparison.
3. Match simulations, scalar draws, selection-score charges, transition and
   verifier ceilings, seed hierarchy, and terminal reward.
4. Record proposal-top-set retention, chosen-action rank, visit allocation,
   unique states, exact success, and run-to-run variance.
5. On these development fixtures, separately sweep a small preregistered grid
   of prior-bonus and uncertainty-floor values to see whether either IID or QMC
   can preserve strong proposal guidance.
6. Freeze the configuration before evaluating a held-out Countdown suite.

The engineering target is not “make QMC win.” It is to learn whether
low-discrepancy posterior exploration spends the same budget more reliably
without destroying an already useful proposal policy.

This source-only comparison was completed with 128 fresh seeds per task and
snapshot. Sobol improved root coverage but did not improve equal-task exact
success; see
[the matched Thompson observation](countdown_thompson_source_n128_20260724.md).

## Reproduction

No credential or network is required:

```bash
PYTHONPATH=src python scripts/compare_countdown_provider_snapshots.py \
  --anthropic-dir artifacts/work/countdown_anthropic_dev_20260722_live_v3 \
  --openai-dir artifacts/work/countdown_openai_dev_20260724_live_v2
```

The script validates both artifacts before computing the pairing gate,
telemetry, snapshot structure, tied-rank diagnostics, and local-search
aggregates.
