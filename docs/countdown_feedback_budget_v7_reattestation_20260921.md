# v7 receiver re-attestation — 2026-09-21

The original evidence and sealed 64-task cohort were independently reproduced
at the current receiver location. A new **non-authorizing** candidate was
prepared, promoted without byte changes, committed and independently verified.
No replication search ran; the original fixed replication claim remains unused.

This is recovery of evidence/admission continuity, not a new experimental result.
It does not prove physical disk identity or that reboot caused the device-number
change. The historical strict-location runner remains unchanged and rejects the
old physical binding. The additive receiver policy is explicit and separately
source-attested.

## Completed checks

| Check | Observed result |
| --- | --- |
| Full repository validation | PASS, exit 0; 1,214 tests in 844.218 s; 0 skips |
| New boundary/fault tests | 31 passed, included in the full suite |
| Original PUBLIC archive | Closed 1,027-file transaction and exact reviewed COMMIT |
| Original PUBLIC reproduction | 32 baseline traces, 1,024 replayed traces, 512 budget-prefix pairs; original receipt and complete summary byte-identical |
| Original sealed cohort | Exact 64-task acceptance order, rejection manifest, three-file seal and input projection reproduced |
| Candidate preparation | PASS, exit 0; separate certificate/candidate/COMMIT, no study consumption |
| Independent candidate verification | PASS, exit 0; fresh process/cache and exact committed candidate/certificate reconstructed |
| Replication | **0 cells; output absent; fixed claim absent** |

All original protected source files, old receipts, old candidate and seal bytes
are unchanged. Relative to the pre-work commit, this change only adds files.
The ledger still contains only the original spent PUBLIC claim.

Full validation ran against implementation
`951d273ccf4072b8e0557970cc71095951b843b7` from 2026-09-20 16:51:19 UTC;
completion was observed at 17:09:16 UTC. Preparation ran in parallel against the
same fixed source and completed at 17:14:44 UTC. Independent verification started
at 17:16:16 UTC, with successful completion observed at 17:32:44 UTC. These are
operator verification timings, **not** search-performance benchmark measurements.

## Exact candidate and source identities

- New candidate digest:
  `fa6947915c170158fcce4ef524988771648fddfe03e442648a9faf1dd9cf08b6`
- Certificate digest:
  `d616348c1fa9ecced27e5df60af7cbfe0d13fe3d8a532dae37308c41b0b66fc1`
- Independent verification receipt digest:
  `93212283a37b4edcf66980f2f1080204b820577e43f897d5ba0a6ba67b67729c`
- Artifact review commit:
  `bf83efbaa94af3dc9b6863a19202acffa815ad74`
- Bridge implementation commit:
  `951d273ccf4072b8e0557970cc71095951b843b7`
- Bridge source-receipt digest:
  `053832fad5596c2666b3bbf3c591904416ebc408c2507ca3d5d6109bbbe3cc86`
- Unchanged historical qualified implementation:
  `91359c9327861210c03ad0bc4e267af240f4ec93`
- Original candidate/evidence review anchor:
  `b57b16ee107eddf07aa94bcf7b20763577aab3a8`

The original candidate digest remains
`27c579f553e44ba3d307d74a5d5b9fa26b9e613150488ecab48e280e518d610f`.
Its earlier approval has not been transferred to the new candidate.

The only changed original candidate fields are `schema_version`, `output_parent`
and `deterministic_digest`. The only added fields are `bridge_source` and
`receiver_certificate`. Every other original field is byte-equivalent, including
all scientific inputs, schedule, budgets, contract, historical environment and
original PUBLIC qualification reference.

The input-manifest digest remains
`4a969fc46e506d2fc81e0b9a45c841bb8e27f81fb7190ff73abbd72d9fe284b3`.
The schedule remains 64 task clusters × 4 seeds × 2 scales × 2 budgets = 1,024
cells, with 512 budget pairs and 256 four-arm blocks. These are not 256 independent
tasks. No new cohort, reroll, witness/hardness selection or search outcome was used.

## Artifacts and byte preservation

- [Candidate](preregistrations/countdown_feedback_budget_v7_reattest_20260921.authorization.json)
  — 157,179 bytes; SHA-256
  `06946c43632d61d51f240bf43518ffe4c603ff689fbb69f7186fb41a84075b7f`.
- [Certificate](qualifications/countdown_feedback_budget_v7_reattest_20260921.certificate.json)
  — 8,481 bytes; SHA-256
  `f1355e545df237e7b1df7f631ff29664040cb5192dd09f748dedde1bebe49abb`.
- [Candidate COMMIT](qualifications/countdown_feedback_budget_v7_reattest_20260921.commit.json)
  — 550 bytes; SHA-256
  `3bcfce7df0e781706a0af84f769219a09a6742d68ce970f798a8daa850fc17cd`.
- [Independent verification result](qualifications/countdown_feedback_budget_v7_reattest_20260921.verification.json)
  — exact captured successful verifier result, SHA-256
  `fcdef81612cc3983f6876c142af999d2dd565264f33d86078f5f63f2ca088517`.

The first three files are exact copies of the successful no-overwrite bundle at
`artifacts/work/feedback-budget-v7-reattest-20260921-a`. Its closed transaction
digest is `e4cbf1a4c864094586bd7334d00c6e78bf4e296cbc7845ea28a1285fe78ca236`.
The fourth file is the captured verifier response, not another executed study or
a replacement for the original receipts.

Retained local logs (under `artifacts/work/`):

- `feedback-budget-v7-reattest-20260921.validation.captured.log` — SHA-256
  `c028dfb3498bbde72dbdb4855073d2e5bc9585f1c9003141af0a8be554e7aa5f`.
- `feedback-budget-v7-reattest-20260921.prepare.captured.log` — SHA-256
  `e219ad4b15cbb4769b958239a0422b2ef7b4d30e78fc3f583021a78fed0af1ce`.
- `feedback-budget-v7-reattest-20260921.verify.captured.log` — SHA-256
  `d7df85c2b12faaeb0db0b4480b171a00cbffec6a034a796a8776bdb5c2d36db2`.

The earlier validator and prepare at `69046466fddbced273e858cc6d6f0cd8473ff629`
were deliberately interrupted before editing the STARTED authentication order.
Their `aborted-6904646` logs remain local and are **not** counted as PASS. Neither
had published a candidate bundle or consumed the replication claim. The final
successful preparation did not overwrite or adopt a partial bundle.

## Review and authority boundaries

The [fork-review record](reviews/countdown_feedback_budget_v7_reattestation_design_20260921.md)
separates outside review from stateful interpretation. The initial design review
identified six gates; the later bounded static implementation review found no
confirmed P1/P2 defect. Project instructions were restored immediately after each
review. Subsequent operator checks tightened result-delivery status and ensured
STARTED is authenticated **before** reading its referenced authorization path;
both changes have dedicated tests and are covered by the final validation.

The device correspondence is restricted to `16777233 -> 16777231` with exactly
the recorded paths and inode numbers. The certificate pins the current PUBLIC,
cohort, output-parent and ledger identities. It does not permit a future device
change automatically. Output-parent/ledger timestamps are intentionally not
frozen: consumption and publication are expected mutations, while immutable
evidence bytes remain pinned.

The original study claim remains:
`artifacts/work/feedback-budget-v7-authorization-ledger/replication-548114440db6e0fa49226e28d519fbe1c0f113d5edfe76f282e7ebc29c0bfc3c.json`.
Preparation and verification checked its absence; neither can replenish it.
Post-consumption analysis instead requires the exact persisted claim.

**Still not established:** a new end-to-end PUBLIC execution through the bridge's
execution orchestration. The positive runs here qualify original-evidence
reconstruction and the new input-admission path; they reuse the unchanged
previously qualified numerical/publication functions. Structural/mocked tests,
source review and old PUBLIC replay must not be described as a new full PUBLIC
execution. Any such extra qualification is a separate next step.

No replication execution, provider call, locked-128 evaluation, causal claim,
population inference or QMC superiority follows. A new explicit decision about
the exact candidate is required before replication. This turn did not push,
create a pull request or merge anything.

See the [frozen receiver policy](strategy/countdown_feedback_budget_v7_reattestation.md)
and [implementation](../scripts/feedback_budget_replication_reattest.py) for the
source-only startup, exact CLI arguments and fail-closed run/analysis boundaries.
