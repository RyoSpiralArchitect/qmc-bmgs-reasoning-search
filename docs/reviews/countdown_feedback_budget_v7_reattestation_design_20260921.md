# Fresh-eye design review and stateful response

## Outside review (read-only, no inherited conversation)

The reviewer inspected the repository with project AGENTS instructions temporarily
hidden by fork-review. It ran no generator, replay, validator, provider or study.
Project instructions were restored before implementation. This is best-effort
context separation, not a guarantee that all prior knowledge was erased.

The outside review found these design gates:

- P1: Added bridge code needs its own source authority; old protected-file receipts
  do not cover it. Use implementation -> generated evidence -> review -> approval.
- P1: The original sealed-input loader returns through the strict old PUBLIC
  inspector. Break that dependency explicitly by reproducing original PUBLIC
  evidence first, not by substituting a callback or fabricating admission objects.
- P1: Storage bindings and mutable Admission objects are data, not proof of admission.
- P1: Close all anchored historical bytes and all path components. A uniform
  device-number correspondence is not proof that a reboot caused the change.
- P1: Separate immutable evidence from expected ledger/output-parent mutations;
  persistent claim absence would invalidate consume -> publish -> analyze.
- P2: Preserve the lower v5/diagnostic/canary and v6 identity verification chain.
  Its observed filesystem generations are process-local, not persisted remount
  bindings. Do not introduce a universal device-number exception.

The review also distinguished PUBLIC replay from execution of any newly written
orchestration/publication path. The latter needs separately described evidence.

## Stateful response

All six points are accepted. The implementation is additive, source-attested and
closed to one original candidate. The old source, seals, receipts, PUBLIC claim,
replication study identity and physical-location checks are preserved. A new
certificate is independently reconstructed, with exact current identities and
explicit pre-/post-consumption checks. No production execution is authorized by
this review or by preparation. The implementation and validation results will be
recorded separately after running them; this design review is not a PASS receipt.

## Second outside review: implemented bridge

> No confirmed P1/P2 defect found in this bounded static review.

The separate fresh reviewer traced the actual implementation through the original
source/runtime checks, historical v5/v6 authority reconstruction, baseline,
PUBLIC replay/reduction and cohort reconstruction. Its findings were:

- Historical COMMIT closure authenticates every PUBLIC cell, STARTED, receipt,
  authorization and claim before replay.
- New source authority is additive; candidate/certificate review precedes
  independent reconstruction and scientific-input regeneration.
- Scientific candidate fields are preserved; the old runner rejects the new schema.
- The original fixed claim is consumed, and post-consumption analysis checks the
  exact persisted claim instead of absence.
- Location bindings exclude mutable parent/ledger timestamps, allowing expected
  claim and publication creation without invalidating their own certificate.
- No evident original-summary reconstruction mismatch was found. Candidate and
  summary have matching source/admission/baseline digests; the seal references the
  expected promoted summary path.

The reviewer observed matching component inodes and device correspondence
16777233 -> 16777231, private owned directories, and private inspected historical
controls. It explicitly did **not** qualify the correspondence by observation.
It ran no tests, generator, replay, search or replication. Remaining actual gates
were clean-source attestation, descriptor readiness, positive prepare/promotion/
fresh verification, full validation, and any new full PUBLIC orchestration run.
Its 29-test reference described the preceding structural/mocked test result only.

## Stateful annotation after restoration

The outside findings are accepted with those limits. Project instructions were
restored immediately when the reviewer completed. A further local check found a
result-delivery distinction worth preserving: if an operation completed but
stdout failed, it must report RESULT_DELIVERY_UNCERTAIN, never imply NOT_RUN.
That reporting path was corrected and given an injected-failure test after this
static review. Positive re-attestation and full validation are recorded in the
separate completion receipt, not inferred from this document.

Before candidate publication, an additional stateful check tightened the order:
authenticate STARTED against the reviewed COMMIT hash **before** opening any path
named inside STARTED. Full transaction closure already preceded replay, but its
reference dereference also needs that earlier authenticity check. A tampered-path
test now proves the named target and claim are not read. The initial full-validator
and prepare processes at `69046466fddbced273e858cc6d6f0cd8473ff629` were explicitly
interrupted before editing; their logs are retained as interrupted, not PASS.
No candidate bundle, replication output or replication claim had been created.
