# Dense-scale feedback opportunity audit v1

[audit.json](audit.json) is an exact copy of the exclusively published,
existing-artifact-only post-hoc audit receipt. It retains all 336 positive-scale
/ scale-zero pairs from the original 384-cell development run.

- audit status: `PASS` (pinned bytes, event hash chains, seven-axis accounting,
  original-summary cross-checks, and descriptive reductions);
- original decision: `STOP_REPAIR_NO_LOCKED_128_RUN`, unchanged;
- new search / generative replay / provider calls within this audit: `0 / 0 / 0`;
- source revision: `55ee28a5c413ed8d64eb383cf485954e348ece1a`;
- audit file SHA-256:
  `b4cdd03febe1c292b8a740dfdb99a0bf8a5c5a4db5dfd2d2768962a5b9ed1d1a`;
- audit bytes: `1159701`;
- audit deterministic digest:
  `2ee8b685ab917d3b155fb69a4aaf0240ae54f19e0b14b615e3f71cc96cacd090`;
- original publication:
  `/Users/ryohiga/SpiralReality/qmc-bmgs-dense-scale-v5-20260904/audit/feedback-opportunity-v1.json`.

The receipt includes exact source/design hashes, all nine original input file
hashes (summary, evidence inventory, authorization, and six raw lifecycle files),
full preceding backup support, score margins as exact rationals of stored
binary64 values, and both sides' budget/opportunity windows. Raw JSONL is not
copied into Git.

See the [fixed post-hoc definitions](../../strategy/countdown_thompson_dense_feedback_opportunity_audit.md),
[observation](../../observations/countdown_thompson_feedback_opportunity_20260904.md),
and [review record](../../reviews/countdown_thompson_feedback_opportunity_20260904.md).
Historical PR #24 replay PASS is not a fresh replay performed by this audit.

## Tool usage

Pure synthetic smoke check, without original artifact access:

```sh
python3 -P -B scripts/audit_dense_feedback_opportunity.py --self-test
```

For the recorded operation, the source checkout was clean and the cache directory
was owned, empty, and mode `0700`:

```sh
PYTHONPYCACHEPREFIX=/Users/ryohiga/SpiralReality/qmc-bmgs-dense-scale-v5-20260904/cache/feedback-audit-v1 \
python3 -P -B scripts/audit_dense_feedback_opportunity.py \
  --repository-root /Users/ryohiga/SpiralReality/qmc-bmgs-reasoning-search \
  --raw-parent /Users/ryohiga/SpiralReality/qmc-bmgs-dense-scale-v5-20260904/raw \
  --output /Users/ryohiga/SpiralReality/qmc-bmgs-dense-scale-v5-20260904/audit/feedback-opportunity-v1.json
```

That destination is now occupied and must never be overwritten. Repeating the
command cannot replace it. A separately named audit output is only a re-audit of
the same immutable evidence, never a retry of the consumed search authorization.
The tool accepts no replacement expected hashes or alternative experiment inputs.
