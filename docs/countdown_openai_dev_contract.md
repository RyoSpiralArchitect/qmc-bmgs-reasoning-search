# GPT-5.6-backed Countdown development-run contract

## Role and claim boundary

This runner is the OpenAI counterpart to the Anthropic provider-plumbing
canary. It tests strict Responses API acquisition, physical cost guards,
immutable proposal replay, four existing local search methods, exact
verification, and byte-identical network-free reconstruction.

It is not a benchmark. The two public development tasks are not eligible for a
later evaluation denominator. No result from this run establishes model,
provider, method, or QMC superiority; QMC is not included in these four local
methods.

## Credential and transmission boundary

`OPENAI_API_KEY` is resolved by the OpenAI SDK from the live runner process
environment. It is never accepted as a CLI argument or stored in an artifact.
Live execution rejects `OPENAI_LOG`, `OPENAI_BASE_URL`,
`OPENAI_CUSTOM_HEADERS`, `OPENAI_ORG_ID`, and `OPENAI_PROJECT_ID`; the client is
fixed to `https://api.openai.com/v1`, uses no SDK retries, and has a 30-second
request timeout.

Each request contains only:

- the Countdown ruleset identifier;
- the positive integer target;
- the current sorted positive-integer multiset;
- every canonical legal action with a local integer action ID.

Search traces, solution witnesses, exhaustive calibration data, task
fingerprints, local paths, and credentials are not transmitted. The model is
asked only for bounded heuristic scores, with no rationale or chain of thought.

## Frozen provider surface

The run uses:

- model `gpt-5.6-sol` rather than the moving `gpt-5.6` alias;
- Responses API `/v1/responses`;
- OpenAI Python SDK `2.45.0`;
- `reasoning.effort="none"`;
- strict Structured Outputs through `text.format`;
- `text.verbosity="low"`, `store=false`, and `truncation="disabled"`;
- `service_tier="default"`;
- `max_output_tokens=512`;
- no temperature, top-p, conversation state, tools, or free retry.

The provider schema intentionally uses a reduced shared subset. Exact array
cardinality, score range `[0, 1000]`, duplicate JSON keys, and one-of-each
action identity are revalidated locally. Optional reasoning output items are
allowed, but exactly one completed assistant message with exactly one
`output_text` block is required. Refusals, incomplete responses, extra
messages, model drift, service-tier drift, and invalid returned JSON cause the
acquisition to fail closed.

Scores are elicited heuristics rather than token log-probabilities. All methods
share the same frozen conversion:

```text
prior_logp(a | s) = log_softmax(raw_score(a) / 100)
```

## Development fixture and shared local search

The exact same fixture as the Anthropic canary is acquired:

1. `(1, 1, 1, 1, 1, 1) -> 6` (24 nonterminal states);
2. `(1, 1, 1, 1, 1, 2) -> 10` (40 nonterminal states).

All 64 state rows are acquired serially before search. The runner imports the
same proposal snapshot, normalization, RNG, greedy, top-p best-of-8, IID
Thompson, best-first, reverse backup, exact verifier, readout, and compute
ledger implementation used by the Anthropic canary. Only provider acquisition,
token accounting, pricing, identity checks, and artifact schemas differ.

## Physical provider budget

Pricing was frozen from the official GPT-5.6 Sol model page on 2026-07-24:
USD 5 / MTok uncached input, USD 0.50 / MTok cached input, USD 30 / MTok
output, and cache writes at 1.25 times uncached input, or USD 6.25 / MTok.

Before each request the runner reserves one attempt, up to 4,096 input tokens
at the cache-write rate, and up to 512 output tokens. The 64-request reservation
is USD 2.62144 under a USD 3.00 hard cap. The ledger records uncached, cached,
cache-write, output, and reasoning token details separately. Reasoning tokens
are included in output tokens and are not charged twice. A transport,
strict-validation, or usage-settlement failure is retained and aborts
acquisition without a hidden retry.

Official references:

- <https://developers.openai.com/api/docs/models/gpt-5.6-sol>
- <https://developers.openai.com/api/docs/guides/model-guidance?model=gpt-5.6>
- <https://developers.openai.com/api/docs/guides/structured-outputs>
- <https://developers.openai.com/api/reference/resources/responses/methods/create>
- <https://developers.openai.com/api/docs/guides/prompt-caching>

## Replay artifact

The scratch artifact contains the proposal rows, per-attempt journal,
acquisition checkpoint, local search records, summary, and byte manifest.
Validation recomputes request identity, legal actions, score decoding,
normalization, provider usage and cost closure, exact terminal verification,
search ledgers, and readout. Offline replay reconstructs search records
byte-for-byte without a key or network.

Provider token counts, latency, and cost are system telemetry. They are not
directly comparable model-efficiency measures because providers use different
tokenizers, structured-output processing, pricing, and network paths.
