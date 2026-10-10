# Receiver E4: original-input reconstruction and whole-result verification — 2026-10-10

The original sealed 64-source inputs, complete generation/acceptance/rejection
history, and both retained PUBLIC archives were reconstructed in one genuine
fresh process at the fixed E4 endpoint. This is input/evidence reconstruction,
not execution of the 64-source replication study. A second fresh process repeated
all computation and matched the entire saved observation byte for byte.

The operation's status label is
`ORIGINAL_STUDY_FULLY_RECONSTRUCTED_NOT_ADMITTED`. Here "reconstructed" covers
the preregistered inputs and retained PUBLIC evidence, **not unexecuted study
outcomes**. Current receiver admission and all new execution authority remain
false.

## Exact reproduction, per pass

| Component | Recomputed work | Comparison |
| --- | --- | --- |
| Original environment | Complete five-field environment and 32 baseline traces | Entire environment matches original candidate and pinned E3 |
| Original v7 PUBLIC | 1024 traces, 512 full-event budget prefixes | Entire receipt and entire summary byte-identical |
| Receiver-v2 PUBLIC | 1024 traces, 512 full-event budget prefixes | Entire receipt and entire summary byte-identical |
| Original sealed cohort | 102 attempts, 64 accepted sources, 38 rejections | All ordered tasks and the entire generation manifest/rejection log equal |
| Original sealed inputs | Three seal transaction files and full 1024-cell input projection | Entire canonical bytes equal |

The 38 rejections retain 27 unsolvable candidates, 8 previously excluded source
multisets and 3 duplicate source multisets. Both full-task rejection categories
remain zero. These are the original counts, not newly selected conditions.
The cohort is conditioned on exhaustive solvability, uses seed 26091301 and
the unchanged 243-task / 179-source exclusion identities. No calibration profile
or solution witness was accessed by the reconstruction layer or persisted.

The 64-source input manifest remains
`4a969fc46e506d2fc81e0b9a45c841bb8e27f81fb7190ff73abbd72d9fe284b3`;
schedule remains
`0da39f97a3bd1e6068d33dae9658c7c3656b3a76aa8854e0a4820683b622352b`.
The complete regenerated input projection is 1109241 bytes; seal
`b457706230403b6c2a7ccb1bd6f5ce7ef027bf45fc5fb49995825611ada53479`
is unchanged. Its original v7 generation-qualification reference is preserved,
not replaced by receiver-v2 or E4.

Both retained PUBLIC archives share one fixed source multiset each, with
64 task definitions. Their total 2048 replays are not source-disjoint replication.
The two complete historical summaries still have `screen_conjunction=false`.
Reconstruction PASS does not turn those negative screens into positive results.

## Fixed E4 case and implementation

Device16777234 is the current fixed E4 metadata endpoint. Its recurrence after
E3/device16777232 does not identify E4 with E2, establish physical disk identity
or show reboot causality. All 23 direct historical path/component/inode checks
were independently performed: original-v7/E0 3, receiver-20260921/E1 8,
E2-observation 6 and E3-observation 6. All 16 historical reviewed anchors and the
three pinned E2/E3 observations were authenticated before numerical work.

The new exact three-file source closure is
[implementation](../scripts/reconstruct_feedback_budget_receiver_e4.py),
[tests](../tests/test_feedback_budget_receiver_e4.py), and
[policy](strategy/countdown_feedback_budget_receiver_e4.md), frozen at
`c19db4a7994eeb5f33c610cdee3ebc0c72e2a004`.
Source digest:
`52deaa2df32b9b03786bd6afeaedb885146a68ddc7de9d0a195f5462275f2456`.

This chains the unchanged E3 PUBLIC replay, E3 environment, E2 inspection and
original numerical implementations. No old device policy, receipt, source,
certificate, candidate, claim or fence was rewritten. The Oct10 E3 rejection and
diagnostic remain retained separately. No old Transport/Proof/Inputs/Admitted
object or qualification callback is fabricated. Genuine lower environment,
PUBLIC reducer and original cohort generator execute in their fixed order.

Metadata-inspection fields such as `acceptance_order_reconstructed=false` in
`sealed_metadata` and `numerical_replay_performed=false` in archive closures
describe the earlier metadata-only stage. The separate numerical reconstruction
records show the later completed work. Historical authority metadata inside
PUBLIC records remains historical even though the numerical recomputation is
fresh; no `authorization_consumed` or coordinator flag is adopted as E4 authority.

## Two fresh processes and exact saved receipts

The first complete reconstruction ran from **2026-10-10 06:18:18 UTC** to
completion observed **06:39:31 UTC**, exit0. A separate fresh-process verification
ran from **06:40:06 UTC** to completion observed **07:03:05 UTC**, exit0.
Both used the same clean frozen source HEAD, absolute repository `src` in
`PYTHONPATH`, `python3 -P -B`, and separate fresh private empty bytecode caches.
No source or tracked documentation changed between these numerical passes.

The second process genuinely repeated the entire environment, both PUBLIC
archives and original cohort generation. It then compared **all 215556 canonical
observation bytes**, not a field subset or just a stored success flag. They are
byte-identical. This is operational fresh-process independence using the same
frozen implementation, **not algorithmically independent implementations**.
Two passes do not make 128 independent sources or two new studies.

Invocation records (not approval to retry):

```sh
PYTHONPATH="$PWD/src" PYTHONPYCACHEPREFIX="$(mktemp -d "$HOME/.qmc-e4-actual-XXXXXXXX")" python3 -P -B scripts/reconstruct_feedback_budget_receiver_e4.py --reconstruct --implementation-revision c19db4a7994eeb5f33c610cdee3ebc0c72e2a004
PYTHONPATH="$PWD/src" PYTHONPYCACHEPREFIX="$(mktemp -d "$HOME/.qmc-e4-verify-XXXXXXXX")" python3 -P -B scripts/reconstruct_feedback_budget_receiver_e4.py --verify-saved --implementation-revision c19db4a7994eeb5f33c610cdee3ebc0c72e2a004
```

The fixed saved-comparator mode also requires the same observation HEAD.
Later documentation commits do not retroactively change the completed evidence,
but are not interchangeable with that frozen runtime HEAD for this command.

- [Reconstruction observation](qualifications/countdown_feedback_budget_receiver_e4_20261010.observation.json):
  215556 bytes; digest
  `d546836a203b3c947dfaa903a49b26b815b07b50a8eebb56f4783c9db855280b`;
  SHA-256 `c4b36d346bfbe641dc292948dc1410d429298fb06b2ee14b0de7a666d08e86c8`.
- [Fresh-process verification](qualifications/countdown_feedback_budget_receiver_e4_20261010.verification.json):
  6006 bytes; digest
  `0b0c41275034b94d763b29c58d1d020defacc054036e8e0429444b6f9514d73f`;
  SHA-256 `8d332314e656cbfdd8e6d999a92f3ba43a7c4d35c667e85844199b75fa292dcd`.
- [Operations receipt](qualifications/countdown_feedback_budget_receiver_e4_20261010.operations.json):
  digest `d653610ea2fc852c89303effb4f2e9d94c796c417bc720e53c84902345d679a8`.

Each merged raw JSONL capture contains 18 informational progress items and one
final result. First capture: 231626 bytes, SHA-256
`79147112edcd364976546096457d1c4f92841fa991308095a23d373d05188abb`.
Verification capture: 22076 bytes, SHA-256
`7aa6c1ba2f0354a8a10815b12ce05bcdfb2dce08da22ca0eadeb72070b40cae7`.
Informational progress is not standalone proof or admission.

## Preservation

A separate read-only postflight check validated the canonical receipts and
digests, complete log/result linkage, source bytes, current identity chains,
the original generation identity, negative PUBLIC screens and all preserved data.

All **367 prior tracked files / 79749024 bytes** retain exact bytes and full POSIX
modes. Both PUBLIC archives retain all **2054 files / 272846815 bytes**, matching
their pinned inventories. The original three-file seal and all three old ledger
records are unchanged; public claims are still bound to their authenticated old
STARTED records. Original production output, replication claim, receiver-v2
summary and the old failed preflight's success-receipt path remain absent.
All three new implementation-closure files also remain exact frozen source bytes.

The postflight check performs no numerical reconstruction. Its digest is
`a8dcca0daec099fea492e03442a8fe9dabc3dab0314a243ef69d4df30d6c145b`; the exact check script, saved check and prior
preservation baseline are referenced in the operations receipt.

## Validation and review

Focused boundary tests: 46 passed in 19.126s. The first 42-test run had two fixture
assertion failures and one fixture constructor error; the full failed log is
retained. Fixtures were corrected without changing old source or production
checks. Local review also strengthened completed-baseline failure accounting.

Full repository validation at the frozen implementation: 1484 tests in 848.033s,
zero skips, plus compile/lint/artifact/provenance/CLI checks; final
`repository validation: PASS`, exit0. Launch: 2026-10-10 06:01:04 UTC.
Completion observed: 2026-10-10 06:17:50 UTC. This is local validation, not CI. The complete log is 302486 bytes,
SHA-256 `6beaefec03e44681a41cf57235eea020545c588fffa51e926904f54e6df5e000`.

Review is bounded local self-review, not fresh-agent or external review. See the
[review record](reviews/countdown_feedback_budget_receiver_e4_20261010.md).
Mocked tests are not numerical reconstruction evidence; fresh-process
recomputation is not an algorithmically independent implementation.

## Remaining gates and interpretation

No certificate or candidate was issued; no new PUBLIC exercise, new coordinator
qualification, replication-policy search, production cell or locked-128
evaluation was executed. The original study output, claim and receiver-v2
summary slots remain unused. No positive search-performance, causal or population
generalization claim is supported by these reproductions.

The next gate is review/design of the current receiver evidence bundle and its
separately authorized publication. A reviewed successor coordinator then requires
an expressly approved fixed new PUBLIC exercise and independent saved-summary
verification. Candidate review and exact-new-digest production consent remain
separate. The reconstruction observation and verification receipt cannot be
passed to old APIs as admission tokens.
