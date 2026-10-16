# E4 certificate-only publisher acceptance policy

Status: **C3 IMPLEMENTATION — ACTUAL ISSUANCE REQUIRES SEPARATE APPROVAL**.

This policy, `scripts/feedback_budget_receiver_e4_publisher.py` and
`tests/test_feedback_budget_receiver_e4_publisher.py` are one separate, complete
three-file source closure. No frozen C1/E4/lower file is modified. The
[C0 design](countdown_feedback_budget_receiver_e4_certificate_design_20261010.md)
and [corrected C1 identity policy](countdown_feedback_budget_receiver_e4_certificate.md)
remain applicable. Implementation/tests do not authorize expensive reconstruction
or issuance. A publisher implementation OID is assigned only after this closure
is committed; do not treat an uncommitted self-test as source qualification.

## Fixed inputs and explicit authority boundary

The certifier is frozen at `23ac0587a1a519cfb85711ffdcc4b28c3ce41a47`, source
digest `4535836b9321da18e703a457356b5ff939cf8393414ddfa6ac845d2ec01f7f70`.
The fixed 226656-byte proposal is authenticated against
`d9809393352e533374eff3df742b7aa5c41e3ccb`, SHA-256
`129c3baa318eebb6eb88a6b124e84d681d1bd7f6b43596bc179908277e887c79`.
The exact proposal-review report, fresh-process verification and operations
records are authenticated at `d3f088c324f59db433dc8e9fc9a4c194d2e17fe1` with
source-owned byte counts and SHA-256 pins, before parsing any historical JSON.
That review was same-agent and same-implementation, not an independent algorithm.

`--self-test` performs static checks only, including outside-checkout imports.
`--issue-certificate-only --implementation-revision <full-OID>` is the sole
effectful mode. Invoke it only after explicit certificate-only approval and
review/validation of that exact immutable publisher closure. The flag is an
explicit scope selection, not evidence that a human authorized it. No supplied
proof, capture, callback, file, output path, candidate, arbitrary review revision,
retry, recovery, resume or execution mode is accepted. The library interface
takes only the full publisher OID and the exact certificate-only scope string.

Every qualified invocation must be a new process using `-P -B`, absolute
`PYTHONPATH` to this checkout's `src` and a private empty cache outside the
checkout. No earlier reconstruction or registered capture may exist in the
process. A failed attempt is not retried, even before creation, in that process.
Occupied target slots block a subsequent process too. Reopening a failed
pre-effect attempt requires a separate human decision, not automatic recovery.

## Genuine reconstruction before any publication effect

The publisher attests its complete closure and unchanged frozen certifier;
pins HEAD and authenticates the fixed historical comparison records. It then
calls the genuine C1 reconstruction exactly once. It does **not** call the
detached `verify_proposal` API and mistake its receipt for a capability.
Only the registered private capture returned by genuine C1 is consumed internally.
All complete certificate bytes, not selected success fields, must equal the
reviewed proposal. Capture HEAD/source and the descriptor-bound output-parent
chain must equal the current operation. C1 owns the full 32-trace baseline,
two separate PUBLIC replays, original cohort reconstruction and final evidence
checks; none can be replaced by saved PASS data or publisher fixtures.

Before and after publication effects, keep checking publisher and C1/lower
source, operation HEAD, clean checkout, fixed proposal/review snapshots, current
receiver/capture evidence/runtime, original unspent study slots, and absent
promoted mirrors. C1's corrected persistent UUID/path/inode identity and actual
operation-local device/inode checks remain unchanged. No post-consumption
analysis or timeless-unused claim is introduced; that remains a C4 boundary.

## One exclusive transaction

The sole raw bundle is
`artifacts/work/feedback-budget-receiver-e4-certificate-20261010-a`.
The only files, in write order, are `certificate.json`, `verification.json`,
`COMMIT.json`. No authorization/candidate or study claim is created. Before
creation, require absence including dangling symlinks. Afterwards, require the
retained no-follow directory identity, private 0700 ownership, exactly the owned
filename prefix, single-link 0600 files, exact descriptor/name/content identity,
and unchanged observed generations between effects. Never adopt a byte-identical
foreign directory or file. Parent directory generation is operation-local, not
a permanent property of the certificate.

Reuse frozen descriptor walkers, pinned parents, owned-file assertions and bounded
write primitives. The older `_exclusive_create_exact` includes reconciliation
after errors, so this publisher deliberately owns its small non-reconciling
O_EXCL path using those lower primitives. No hooks or numerical callbacks are
accepted. Normal short-write completion is not a retry of a failed publication;
write/barrier errors stop without re-fsync, rewrite or adoption. A restrictive
umask that fails exact 0700/0600 requirements fails closed, with entries retained.

After mkdir, sync the parent and new directory. Write each payload exclusively,
sync its file and the bundle directory, and read back exact retained ownership.
Write COMMIT last; perform an additional terminal directory barrier and final
live/owned observation. Preserve every created entry on **any** failure. Close
descriptors only: never unlink, rename, overwrite, resume, pick an alternate
suffix or automatically republish. These are qualified POSIX/no-follow/host
assumptions, not protection against a malicious interpreter, privileged host,
hardware lying about fsync, or an atomic source-to-filesystem transaction.

## Closed generated records and uncertainty

All records use compact sorted ASCII canonical JSON with one final newline,
strict duplicate/nonfinite rejection and the existing content-digest convention.
Certificate bytes are the unchanged C1 proposal; publication state is not added.

The `/verification` record has exactly schema_version, status, scope,
operation_head, publisher_source, certifier_source, receiver_identity,
reviewed_proposal, proposal_review_revision, proposal_review_records,
independently_reconstructed_certificate,
complete_canonical_certificate_byte_identical, verification_method,
algorithmically_independent_implementation, work,
original_study_slot_absent_at_verification, certificate_issued_at_verification,
claim_ceiling, deterministic_digest. It records whole-byte equality immediately
before issuance, not that a future write succeeded. Same frozen implementation
in a fresh process is not algorithmic independence.

The `/commit` record has exactly schema_version, status, scope, operation_head,
publisher_source, certifier_source, reviewed_proposal_revision,
proposal_review_revision, bundle_location, payloads, publication_order,
claim_ceiling, deterministic_digest. Payloads has exactly the two preceding
filenames, each with byte_count/sha256/deterministic_digest. The owned bundle
location records its fixed path, actual live component identities and persistent
UUID/inode components including the newly owned directory. COMMIT does not hash
itself; neither certificate nor verification references this future COMMIT.
Every authority ceiling remains C1's eleven false/plain-zero values.

Effect counters distinguish NOT_ATTEMPTED, UNKNOWN_PARTIAL_OR_COMPLETE and
COMPLETE for mkdir, barriers, each exclusive open/write, and final observation.
Unfinished genuine work remains unknown while completed work is retained.
Once COMMIT creation has been entered, failure reports issuance as unknown,
not false, and separately reports completed durability barriers. A later
validation/delivery failure never makes a complete bundle absent or reusable.
After a successful transaction, failed/short stdout delivery retains issued=true
and the complete operation record. If even stderr delivery fails, the process
outcome is uncertain: retain the namespace and do not retry.

The publisher never writes the three promoted documentation mirrors. Later
verbatim promotion is separate from the frozen-HEAD transaction and must not
trigger raw republishing if delivery fails. No later inspect/admit/execute API is
added by this slice. New coordinator/PUBLIC qualification (C4), new candidate
review and exact-new-digest production consent (C5) remain unimplemented here.

## Test scope

C-T09 is covered by rejection of caller-supplied receipts/callbacks, unregistered
captures, stale reconstruction state and detached bytes; one ordered genuine
helper call is checked through explicit MOCK reconstruction only. C-T10 uses
real isolated temporary directories for exclusive creation, exact prefix,
foreign/dangling paths, mirror occupancy, generation/content/ownership drift,
partial writes, fsync/response/delivery failures, retained complete-but-uncertain
bundles, descriptor cleanup, and same-process retry rejection. C-T03/06/07/08/12
also cover pinned reviews, full source/HEAD checks, whole-byte equality and live
drift. C-T11/13/15/16 preserve certificate-only scope, acyclic records, original
proposal bytes and false authority. C-T14 is intentionally still a later C4 gate.
Static AST checks supplement runtime tests; they are not security proofs.

No temporary-directory test issues the fixed real certificate or repeats the
original numerical experiment. Test success is implementation/mechanics evidence,
not issuance, positive PUBLIC screening, search improvement or production readiness.
