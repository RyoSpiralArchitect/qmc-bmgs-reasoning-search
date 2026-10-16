# Receiver E3: both retained PUBLIC archives reproduced — 2026-10-08

Status: **RETAINED_PUBLIC_RECEIPTS_AND_SUMMARIES_REPRODUCED_NOT_ADMITTED**.
The environment and retained-PUBLIC portions of D2 are now reconstructed for
this fixed E3 case. Full receiver proof, new execution-path qualification and
production authorization remain incomplete.

This follows the [E3 environment observation](countdown_feedback_budget_receiver_e3_environment_20261008.md).
One fresh process genuinely recomputed the environment and 32-trace baseline,
then separately replayed both complete retained PUBLIC archives. Neither archive
was deduplicated or substituted with a saved success record.

## What reproduced

| Archive | Replayed traces | Full budget-prefix comparisons | Entire receipt | Entire summary |
| --- | ---: | ---: | --- | --- |
| Original v7 PUBLIC | 1,024 | 512 | Byte-identical | Byte-identical |
| Receiver v2 PUBLIC | 1,024 | 512 | Byte-identical | Byte-identical |
| Total retained replay | 2,048 | 1,024 | 2 / 2 | 2 / 2 |

The fresh 32-trace baseline is additional to this retained-replay denominator.
All five environment fields — source, runtime, baseline, authorities and
admission context — match the authenticated original candidate and the pinned
prior E3 observation in full.

Both PUBLIC archives use the same fixed input-manifest digest,
`c07eb38ada5d555d56075047242370c49f4e0dee120d96e1e489c981f00ae7ab`.
Each contains 64 task definitions from **one source multiset**, not 64 independent
sources. Replaying two archives is not source-disjoint replication, a new PUBLIC
exercise, a performance improvement, or evidence that a new coordinator works.

The full historical receipt digests are:

- Original: `68f6eff9dbd65af7f6342cf423240471d0c3e29111f4b37189911f86de5dfe71`.
- Receiver v2: `2e79fd20afa953ccb79a33c345c524ffdc2ab686abbd31fd21d3c5e1d117cf28`.

The original summary is 4,019,917 bytes, digest
`4511f9bc8ea0c5dacac292ae3d90f6009af8820b5744f46b8b85c1e5a72f57ec`.
The v2 summary is 3,869,769 bytes, digest
`a85537a8b496a4a39be765686eda8d9e26fd9b66df252125a5a8ba1df86e7757`.
Both complete receipt files are 3,865,645 bytes. Every canonical byte was compared,
not only these digests or selected result fields. Negative outcomes remain
unchanged in the reconstructed full reductions.
Both historical PUBLIC summaries retain `screen_conjunction=false`. Replay PASS
is an integrity result, not a favorable numerical screen or a new study result.

## How this was checked

The [fixed-case implementation](../scripts/replay_feedback_budget_receiver_e3_public.py),
[35 boundary tests](../tests/test_feedback_budget_receiver_e3_public_replay.py), and
[policy](strategy/countdown_feedback_budget_receiver_e3_public_replay.md) form the
exact new three-file source closure. Frozen revision:
`575fee9a235779ac982ab13be2f10577474a6c84`.
Source digest:
`b04934e1fb1d9e69bd78135ceded8f305bac38615e56fc6f838699e41b424aff`.

Actual invocation started **2026-10-08 12:35:41 UTC**;
completion was observed **2026-10-08 12:52:16 UTC**,
exit0. This was one fresh process with an empty private bytecode cache, absolute
repository `src` in `PYTHONPATH`, and `python3 -P -B`. The checkout stayed clean
at that frozen HEAD for the qualified operation.

```sh
PYTHONPATH="$PWD/src" PYTHONPYCACHEPREFIX="$(mktemp -d "$HOME/.qmc-e3-retained-public-XXXXXXXX")" python3 -P -B scripts/replay_feedback_budget_receiver_e3_public.py --replay --implementation-revision 575fee9a235779ac982ab13be2f10577474a6c84
```

This command is the invocation record, not an approval to retry. It rejects any
changed fixed endpoint, evidence, source/HEAD, or occupied original study slot.

The operation authenticated 16 historical anchors plus the pinned E2 and E3
observations, checked all 17 direct E0/E1/E2-to-E3 metadata chains, and hash-closed
both archives before numerical work. E3 remains exactly device16777232; no old
device number, source, certificate, candidate, policy or saved receipt was edited.

It called genuine frozen `R.environment(B.ORIGINAL_SOURCE)`, genuine PUBLIC
`R.load_inputs`, and two separate `R.reduce_rows` calls. Explicit historical
summary projections combine freshly reproduced numerical results with
authenticated historical metadata; they do not use saved-summary templates,
forged old admission/transport/input objects, or a caller's proof callback.

The unchanged lower environment checks also reconstruct their original v5/v6
identity-authority material. That work is not regeneration of the sealed
64-source study. Source/runtime/evidence/current identities/HEAD and unused study
slots were revalidated before the successful observation returned.

Historical `authorization_consumed=true` and
`public_coordinator_qualified=true` inside reproduced old summaries remain facts
about those historical runs. Current admission and new coordinator qualification
are explicitly false. The `public_archive_hash_closures` entries retain their
metadata-inspector field `numerical_replay_performed=false`: that field describes
the earlier hash-inspection stage only. The separate `public_replays` records and
overall result record the subsequent genuine numerical reconstruction.

## Receipts, validation and preservation

Observation digest:
`c2ad3d97bd1e2ee30dcf255c2b5a1ca10faf0b533256862994ad484492564c3c`.
Saved bytes: **197,823**; SHA-256:
`924e1118ca0861d336b5266a2b809f0fb784ae31a446a3ab08d879e7a13f7fb3`.
The merged capture contains 16 informational progress items and one final result,
208,217 bytes, SHA-256
`563227c208f27b9aa396c69559ad220528857571b166b4ef3651826939b90519`.
Informational stages are not standalone qualification receipts.

Focused tests: **35 passed in 19.508s**. These are projection fixtures and mocked
boundary/wiring checks, not evidence that actual archived traces were replayed.

Full `scripts/validate.py` at the frozen source passed:
**1,438 tests in 879.899s, zero skips**, plus compile/lint/artifact/provenance/CLI
checks and final `repository validation: PASS`, exit0.
Started 2026-10-08 12:16:56 UTC; completion observed
2026-10-08 12:34:50 UTC.
The complete 294,634-byte log has SHA-256
`4f3bd6ce5221a7640783132c6b0f73da4ba91cbafb9707bb92fe0ddb180005e1`.
This is local validation, not CI or an independent receiver-proof verification.

A subsequent saved-receipt/hash consistency check verified canonical bytes,
object digests, source references, the full saved environment, both receipt and
summary byte references, and both archive inventories. It performed no new
numerical reconstruction and is not independent whole-proof verification.

All prior **360 tracked files / 79,465,437 bytes** retain their exact bytes and full
file modes. Both archives retain all **2,054 files / 272,846,815 bytes**; the three
old ledger records are unchanged. Original production output, claim and v2
summary remain absent, as does a successful receipt for the old failed preflight.

See the [saved observation](qualifications/countdown_feedback_budget_receiver_e3_public_replay_20261008.observation.json),
[operations receipt](qualifications/countdown_feedback_budget_receiver_e3_public_replay_20261008.operations.json),
and [bounded local review](reviews/countdown_feedback_budget_receiver_e3_public_replay_20261008.md).
Operations digest: `cf8d3f0cd177637949a6e4da2479cc5e1ebdfb4daaa54307f0726340aea34462`.

## Claim ceiling and next gate

This completes the retained-PUBLIC numerical portion, not all of D2. No sealed
64-source acceptance/rejection-order reconstruction, full receiver proof,
certificate/candidate issuance, new coordinator qualification, new PUBLIC
attempt, provider/GPU call or experimental replication was performed. No push,
PR or merge was made. Path/inode/device agreement still does not prove physical
disk identity or reboot cause; unchanged numerical results do not establish
exploration gain, causality, population generalization or locked-128 readiness.

The next bounded step is to reconstruct the **exact original sealed acceptance
and rejection order**, preserving its original generation qualifier, full input
projection and schedule. Independent whole-result verification remains after
that. New proof publication, new execution integration and its expressly approved
fixed PUBLIC qualification, candidate review and exact-new-digest production
consent remain separate later gates. The original study remains unspent.
