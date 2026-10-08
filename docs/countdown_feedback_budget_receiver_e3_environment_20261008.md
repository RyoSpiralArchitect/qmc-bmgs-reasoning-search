# Receiver E3: environment reconstruction — 2026-10-08

Status: **READ_ONLY_E3_ENVIRONMENT_AND_32_TRACE_BASELINE_REPRODUCED —
PARTIAL_RECONSTRUCTION, NOT_ADMITTED, NOT_AUTHORIZED**.

After explicit approval to insert a new receiver-case design/review, the
separately scoped E3 path was implemented and run once. The earlier E2
device-drift rejection remains a rejection; no old admission, candidate,
certificate, policy or recorded device was changed.

## What advanced

A fresh process independently checked E0, E1 and the E2 observation against
the exact E3 endpoint (16777232), authenticated the retained evidence, and then
genuinely reconstructed the original environment and 32-trace baseline.
All five environment fields equal the authenticated original candidate in full.
This is the environment portion of D2, not a completed receiver proof.

| Evidence | Fresh result |
| --- | --- |
| E0 device16777233 | 3 owning-field-bound chains directly match E3 |
| E1 device16777231 | 8 owning-field-bound chains directly match E3 |
| E2 observation, device16777234 | 6 observational chains directly match E3 |
| Fixed historical anchors | 16 authenticated again, plus the pinned E2 observation |
| Retained PUBLIC archives | 2,054 files / 272,846,815 bytes hash/schema/linkage-closed; zero numerical traces replayed |
| Original environment | Full source/runtime/baseline/authorities/admission-context comparison matches |
| Baseline | 32 traces recomputed through the unchanged matrix; full reproduced analysis matches |
| Original sealed 64-source acceptance | Saved bytes preserved; acceptance order not regenerated here |

E2 adds observational history for all six roles, including the old bridge
bundle. It does not invent an E0/E1 bundle identity or prove physical-disk
identity or reboot cause. Any later endpoint change rejects again; there is
no automatic rebinding or general device allowlist.

## Source and actual-operation evidence

The new three-file closure is the
[checker](../scripts/check_feedback_budget_receiver_e3_environment.py),
[tests](../tests/test_feedback_budget_receiver_e3_environment.py), and
[fixed-case policy](strategy/countdown_feedback_budget_receiver_e3_environment.md).
Implementation: `85f90035cdfa57f75393500cae72b2aba1e96e96`.
Source digest: `c1ff9702b58a68eb75cb7514371626c3e599663992f5046c9700fb3c1082f435`.

Actual invocation started **2026-10-08 08:13:51 UTC**; completion was observed at
**08:23:33 UTC**, exit0. The exact checkout remained clean at the implementation
HEAD. This was one genuine invocation, separate from mocked wiring tests.

Observation digest:
`032f4d1da89d3f3fb119dfc102e961a2467396bac6d672a69a000422d65b8cb3`.
Saved bytes: 194,443; SHA-256:
`24f44d2ede0a2a23746e0f61fd5e1fc50be10a37a9deef3a980116b20a9a1344`.
Baseline reproduced-analysis digest:
`1e9df9e0b7c54f6de0b5c6c75976c23a362a7d4cbc3cd347b9f95d2dace97fc5`.

The frozen `R.environment(B.ORIGINAL_SOURCE)` performs genuine runtime,
lower v5/v6 identity-authority verification and `qualify_baseline()`.
The v6 authority recipe reconstructs its original 12 tasks for exclusions;
this is not the sealed 64-source replication acceptance or a new cohort.
Source/runtime/evidence/HEAD/current identity/unused-state checks run again
before a successful observation can return.

Both PUBLIC inventories remain
`e5f3bfdb78ee0bfe103c3d2b8a9547d71be9e453bc7363c3c1e918aa9233d1ed`
and `1431a40bc3e8d3f462443d29aa55fc1b10b222cb54110820fb50f7e79d4e3733`.
Their saved success flags remain historical. Each PUBLIC archive contains
64 definitions from one source multiset, not 64 independent sources.

## Validation, preservation and claim ceiling

Focused boundaries: **33 tests passed in 10.203s**; the unchanged E2 tests also
passed (30 tests in 10.642s). The intermediate test-edit failure is retained and
explained in the review, not relabeled as a pass.

Full `python3 scripts/validate.py` at the frozen implementation exited0:
**1,403 tests passed in 905.427s, zero skips**, followed by successful artifact,
provenance and CLI checks. Started 08:23:56 UTC; completion observed 08:42:02 UTC.
The final marker was `repository validation: PASS`. The complete captured log
contains 287,895 bytes, SHA-256
`4797aea52949a70219eba3e011d90ac4970c66014f249765ae218b7b2e3fc52a`.
This is local regression evidence, not CI or numerical exploration-performance
evidence. Actual environment reconstruction and these tests are separate results.

The original 353 tracked files (79,204,349 bytes) retain their exact bytes and
full file modes. The three old ledger records are unchanged. The original
production claim/output/v2 summary remain absent; the old failed entrypoint
has not acquired a successful preflight receipt.

The checker has no admission, publication, candidate, consent or execution API.
It does not use old forward-fsync archive/claim inspectors. No certificate or
candidate was issued, no new PUBLIC attempt or experimental replication was run,
and no provider/GPU call, push, PR or merge was performed. Regression and baseline
reproduction establish neither improved exploration nor causal/scientific claims.

See the [saved observation](qualifications/countdown_feedback_budget_receiver_e3_environment_20261008.observation.json),
[operations receipt](qualifications/countdown_feedback_budget_receiver_e3_environment_20261008.operations.json),
and [bounded local review](reviews/countdown_feedback_budget_receiver_e3_environment_20261008.md).
The review is single-agent/local, not independent-agent or external approval.

## Next unmet gate

Add explicit historical summary projections, then genuinely replay both retained
PUBLIC archives: 1,024 saved cells and 512 budget prefixes each, comparing each
complete receipt and summary to its authenticated historical bytes. Keep old
admission references historical; do not fabricate old Transport/Proof/Inputs
objects or use this observation as a qualification callback.

After that remain the exact original sealed acceptance-order reconstruction and
independent whole-result verification. A new receiver proof and any new execution
integration have separate publication/qualification gates. Production still needs
candidate review and explicit exact-new-digest consent for the unchanged study.
