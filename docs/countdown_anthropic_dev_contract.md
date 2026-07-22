# Anthropic-backed Countdown development-run contract

## Role and claim boundary

This is the first provider-backed end-to-end plumbing run on Countdown-D6. It
tests credential isolation, strict action-score acquisition, physical cost
guards, immutable proposal replay, four local search methods, exact verification,
and artifact reconstruction.

It is not a locked benchmark and makes no claim that one method, QMC, Anthropic,
or any reasoning system is superior. The two tasks are public development
fixtures selected for complete, inexpensive proposal-cache coverage. They never
enter a later evaluation denominator. Its artifacts remain scratch plumbing
evidence and are not eligible for promotion as locked comparative evidence.

## Credential and external-data boundary

`ANTHROPIC_API_KEY` is read by the Anthropic SDK from the process environment.
It is never accepted as a CLI argument, written to a file, copied into an
artifact, included in an exception, or committed. `.env` files are ignored by
Git, but the development runner does not load them.

For a live run, provision the key into the runner's child-process environment
through a secret manager or ephemeral session wrapper. Do not place the raw key
in a command, shell history, `.env`, repository file, artifact, log, or
persistent clipboard. A credential must never be printed during a presence
check. Unset `ANTHROPIC_LOG` for live acquisition; the runner rejects a live run
when that logging variable is present.

Each provider request contains only:

- the ruleset identifier;
- the positive integer target;
- the current sorted integer multiset;
- every canonical legal action with a local integer action ID.

Original source bindings, search traces, exhaustive calibration metrics,
solution counts, witnesses, distances, local paths, and task fingerprints are
not transmitted. The model is asked for bounded integer heuristic scores only,
with no rationale or chain of thought.

## Frozen provider surface

The development run uses:

- Claude API model `claude-haiku-4-5-20251001`, not a moving alias;
- Messages API `/v1/messages` with API version `2023-06-01`;
- Anthropic Python SDK `0.116.0`;
- JSON-schema structured output;
- providerへ送るschemaは対応済みの構造keywordだけを使い、配列件数・score範囲・
  `action_id`完全性はstrict local decoderで再検証する;
- `temperature=0`, `max_tokens=512`, and SDK retries disabled;
- exactly one score in `[0, 1000]` for every legal action ID.

Temperature zero is not treated as a determinism guarantee. The response model,
request ID, stop reason, token usage, allowlisted response text, and request /
response digests are retained. Missing, duplicate, unknown, non-integral, or
non-finite scores; a non-`end_turn` stop; and model-identity drift invalidate the
provider row. There is no free parse retry.

Scores are elicited heuristics, not token log-probabilities. Every method shares
the same versioned conversion:

```text
prior_logp(a | s) = log_softmax(raw_score(a) / 100)
```

The normalization version and behavior-only proposal digest are recorded
separately from nondeterministic provider metadata.

## Development fixtures and immutable acquisition

The full nonterminal state DAG is acquired for exactly two tasks:

1. `(1, 1, 1, 1, 1, 1) -> 6` (24 nonterminal states);
2. `(1, 1, 1, 1, 1, 2) -> 10` (40 nonterminal states).

All 64 proposal rows are acquired serially before search. Enumeration uses only
legal transitions, never solution metadata. Search then runs offline against
the frozen snapshot. Thus every method sees the same response for the same
state, provider nondeterminism cannot become a method-order effect, and replay
requires no credential or network.

## Physical provider budget

Pricing was frozen from Anthropic's public pricing page on 2026-07-22 for Claude
Haiku 4.5: USD 1 / MTok base input, USD 1.25 / MTok cache creation, USD 0.10 /
MTok cache read, and USD 5 / MTok output. Prompt caching is not requested.

Before each request, the runner reserves one call, 4,096 possible input tokens,
512 possible output tokens, and their worst-case base cost. The development cap
is 64 attempts and USD 0.50. The 64-request worst-case base reservation is USD
0.425984. A reservation that would cross either cap fails before the request.
Actual input, output, cache, latency, and USD estimates are recorded separately.
A transport failure is retained as a possibly billable attempt and aborts the
run; it is not silently retried.

Official references:

- <https://platform.claude.com/docs/en/about-claude/models/model-ids-and-versions>
- <https://platform.claude.com/docs/en/build-with-claude/structured-outputs>
- <https://platform.claude.com/docs/en/about-claude/pricing>
- <https://platform.claude.com/docs/en/api/versioning>
- <https://platform.claude.com/docs/en/manage-claude/authentication>

## Local methods

All methods use the complete legal action set, frozen priors, exact terminal
success only, no shaped reward, no pruning, and a shared cache-only readout.

- `greedy`: one five-action trace, choosing maximal prior with canonical ties.
  It is a low-cost anchor, not an equal-compute competitor.
- `top_p_best_of_8`: eight independent rollouts with `top_p=0.95` and a
  counter-based IID stream.
- `iid_thompson_8`: eight simulations, terminal return `1/0`, reverse backup,
  `gamma=1`, prior bonus `0.1`, and IID normal action perturbations.
- `best_first_8`: proposal-log-probability best-first expansion over canonical
  DAG states, continuing until eight already-generated terminal traces have
  been exactly verified or a hard guard stops the run.

Search limits are common guards, not a claim of equal realized compute:

| Axis | Limit |
|---|---:|
| proposal batch calls | 64 |
| proposal state items | 64 |
| proposal input values | 448 |
| proposal action scores | 256 |
| selection action scores | 512 |
| edge selections | 128 |
| transitions | 128 |
| verifier calls | 8 |

Every rejected charge occurs before RNG draw, cache insertion, frontier change,
transition, verification, or value update. Greedy and best-first are run once per
task; stochastic methods use development seeds 0 and 1. The independent unit is
not inferred from these rows because this is not an effectiveness analysis.

## Readout and replay artifact

Readout considers only terminal traces already verified inside the budget. It
chooses the first observed exact trace, otherwise the terminal with greatest
cumulative proposal log-probability, with canonical trace ties. It performs no
new provider, transition, or verifier work.

The scratch artifact stores strict JSONL proposal rows and search records plus a
summary and byte manifest. Validation recomputes legal actions, normalization,
digests, every exact terminal verification, ledger closure, and readout. A
network-free replay must reproduce the deterministic search records byte for
byte. The API key and any calibration oracle fields must be absent from every
artifact byte.
