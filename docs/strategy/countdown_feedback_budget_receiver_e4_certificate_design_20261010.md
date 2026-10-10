# E4 receiver certificate: bounded design — 2026-10-10

Status: **DESIGN_ONLY — NO_CERTIFICATE_ISSUED, NO_EXECUTION_AUTHORITY**.

This is the next design/review gate after [E4 reconstruction](../countdown_feedback_budget_receiver_e4_20261010.md).
It does not implement a certifier, accept a live execution admission, publish a
certificate or candidate, allocate a PUBLIC attempt, or authorize production.
All existing source and evidence remain unchanged.

## Decision and smallest next slice

Create an additive **certificate-only** verifier. Its eventual certificate says
that the original inputs and retained PUBLIC evidence were reconstructed for the
fixed E4 case; it says nothing affirmative about unexecuted replication outcomes.
Do not reuse the old bridge's `prepare`: it publishes an authorization candidate
as well as a certificate and reconstructs under the wrong historical receiver
policy. Do not change that bridge or the E4 reconstruction source.

The immediate next implementation slice is a source-owned read-only certifier
and synthetic adverse-case tests. It may expose self-test and read-only
reconstruction/verification operations; no publisher, candidate, claim consumer
or execution dispatcher. Implementation approval is not approval to perform its
expensive actual reconstruction. Later publication needs a separately reviewed,
source-owned publisher and explicit certificate-only scope.

## Evidence baseline, not a live capability

Design baseline: `3a69f33121be244c21143979be0a04fe71cdac5e`.
The observation, verification and operations files under
`docs/qualifications/countdown_feedback_budget_receiver_e4_20261010.*.json`
are authenticated against this reviewed Git revision **before parsing**.

| Historical E4 record | Bytes | Deterministic digest |
| --- | ---: | --- |
| Observation | 215556 | `d546836a203b3c947dfaa903a49b26b815b07b50a8eebb56f4783c9db855280b` |
| Fresh-process verification | 6006 | `0b0c41275034b94d763b29c58d1d020defacc054036e8e0429444b6f9514d73f` |
| Operations | 12603 | `d653610ea2fc852c89303effb4f2e9d94c796c417bc720e53c84902345d679a8` |

Exact paths, SHA-256 values, original source receipt and current inventory are in
the [design inventory](../qualifications/countdown_feedback_budget_receiver_e4_certificate_design_20261010.inventory.json).
The historical reconstruction HEAD is
`c19db4a7994eeb5f33c610cdee3ebc0c72e2a004`, source digest
`52deaa2df32b9b03786bd6afeaedb885146a68ddc7de9d0a195f5462275f2456`.

A live read-only inventory found the same six E4 chains on device16777234.
The stored 23 direct historical chains remain 3 E0 + 8 E1 + 6 E2 + 6 E3.
Repeated E2/E4 device numbers do not merge the epochs or prove disk continuity.
The inventory verifies retained bytes/locations, not numerical reconstruction or
current receiver admission.

The historical `N.verify_saved` requires its saved observation's exact HEAD.
It correctly rejects treating the later evidence/design HEAD as c19db4a.
Never relax that guard, reset HEAD to impersonate the old run, edit the old
observation, or call this saved result a reusable in-memory proof.

## Three different objects

1. **Historical receipt:** immutable, reviewed evidence of completed work at its
   recorded HEAD. Its successful flags are not authority to skip fresh work.
2. **Live evidence capture:** private, process-local result produced only by the
   new certifier's complete genuine reconstruction. It retains actual evidence
   snapshots, source/runtime bindings and current location identities for
   revalidation. It is not constructible from a caller-supplied receipt, proof,
   callback, device mapping or old `Transport/Proof/Inputs/Admitted` object.
3. **Detached certificate bytes:** a deterministic projection of that verified
   result, reviewed and later independently reconstructed. Reading or hashing
   these bytes is not current admission or execution permission.

The capture's constructor/interface boundary is a repository API constraint,
not a security claim against a malicious interpreter or host. Guard actual
module origins/callables and source receipts; do not trust a supplied type label.

## Proposed closed certificate schema

Proposed domain:
`qmc-bmgs-countdown-thompson-feedback-budget-confirmation/v1/receiver-e4-certificate/v1/certificate`.

The exact top-level fields are the twelve rows below. All nested structures have
closed key sets, exact domains and plain types; no extension or ignored-field
bag. Existing evidence subobjects inherit their entire frozen E4 schemas and
must equal the authenticated originals after genuine reconstruction.

| Field | Required content |
| --- | --- |
| `schema_version` | The exact proposed domain above |
| `status` | `ORIGINAL_INPUT_AND_PUBLIC_EVIDENCE_RECONSTRUCTED_NOT_EXECUTION_AUTHORITY` |
| `case` | Exactly name `E4`, device 16777234 and the fixed 3/8/6/6 owned-chain registry; no caller-configured receiver |
| `source` | Exactly the certifier's complete new source receipt and unchanged E4 source receipt, chaining all historical sources |
| `historical_e4` | Exactly the three reviewed file references above, original c19db4a reconstruction HEAD and same-implementation/fresh-process method |
| `evidence` | Exactly prior_public_observation, historical_source_receipts, reviewed_anchors, public_archive_hash_closures and sealed_metadata, in full |
| `location_correspondence` | The entire freshly checked E4 direct correspondence and six current chains, not a composed map |
| `environment` | The entire genuine five-field original environment, including the 32-trace baseline |
| `reconstruction` | Exactly work, public_replays, original_sealed_reconstruction, public_traces_replayed, budget_prefix_comparisons, acceptance_order_reconstructed and historical_screen_conjunction |
| `study` | The exact original study, input, schedule, seal, generation reference, output/summary/claim paths and planned denominators described below |
| `claim_ceiling` | The exact non-authorizing false/zero values below; unknown physical identity and reboot cause cannot become positive claims |
| `deterministic_digest` | Existing canonical-content digest convention, not authentication by itself |

`case` uses closed keys `name`, `device`, `historical_chain_counts`; the last
has exactly the four epoch names already owned by E4. `source` has exactly
`certifier` and `frozen_reconstruction`. `historical_e4` has exactly
`observation`, `verification`, `operations`, `reconstruction_head`,
`verification_method`, `algorithmically_independent_implementation`.
Each reviewed file reference has path, reviewed_revision, byte_count, sha256 and
deterministic_digest. Its path/revision is fixed, not a dereference instruction.

`study` has exactly experiment_id, input_manifest_digest, schedule_digest,
seal_digest, original_generation_reference, output_path, summary_path,
fixed_replication_claim_path, accepted_source_multisets, cell_count,
budget_pair_count and four_arm_block_count. These equal the original study:
`feedback_budget_confirmation_64_seed_26091301/v1`, 64/1024/512/256.
The input digest is
`4a969fc46e506d2fc81e0b9a45c841bb8e27f81fb7190ff73abbd72d9fe284b3`;
schedule `0da39f97a3bd1e6068d33dae9658c7c3656b3a76aa8854e0a4820683b622352b`;
seal `b457706230403b6c2a7ccb1bd6f5ce7ef027bf45fc5fb49995825611ada53479`.
The paths remain the original replication output, receiver-v2 summary and
global original study claim; no successor claim or replacement cohort is allowed.

`claim_ceiling` has exactly current_receiver_admitted,
new_coordinator_qualified, candidate_issued, new_public_attempts,
new_cohort_published, replication_policy_search_calls, replication_cells_executed,
replication_execution_authorized, locked_128_evaluation_authorized,
physical_disk_identity_proven and reboot_causality_proven. Booleans are false;
the three counts are plain integer zero. Publication state is **not** a
certificate field: a proposed projection must not claim that publication happened.

Require integer counts (reject bool/float aliases), actual booleans, finite
numbers, strict JSON without duplicate keys, exact full OIDs/hashes and canonical
bytes. Preserve the repository's compact sorted ASCII JSON plus final newline;
the deterministic digest excludes its own field and the final newline. Reject
any otherwise self-consistent rehashed alteration of the reviewed target.

## Fresh reconstruction and explicit historical comparison

The new certifier owns its ordered orchestration and live capture. Reuse the
unchanged E4/lower routines for authenticated metadata, genuine environment,
genuine PUBLIC loading/reduction and original cohort reconstruction. Do not
monkeypatch modules, manufacture old admission objects, extract private state
through observer callbacks, or replace a numerical step with a saved PASS.

Before and after expensive stages, revalidate the new source closure as well as
the frozen E4/lower closures, operation HEAD, clean checkout, current chains,
evidence snapshots, genuine runtime and pre-consumption slot state. The new
certifier must enforce its own checks; E4's guards do not cover added code.

The ordered path is the existing E4 contract: authenticate all anchors before
dereference; check all 23 direct chains; reperform the 32-trace baseline; replay
the two PUBLIC archives separately (1024 traces and 512 full-event prefixes
each); reproduce both complete receipts/summaries; use the original v7
generation reference; call the genuine original cohort generator once; compare
all ordered tasks, the complete 102-attempt/64-accepted/38-rejected manifest,
three-file seal and entire 1109241-byte input projection; finally revalidate.
Exhaustive solvability work is real computation, not replication-policy search.

Every old observation key must be assigned to one of two explicit groups:

- Whole freshly compared evidence/science: source, prior_public_observation,
  historical_source_receipts, reviewed_anchors, location_correspondence,
  public_archive_hash_closures, sealed_metadata, environment, work, public_replays,
  public_traces_replayed, budget_prefix_comparisons, original_sealed_reconstruction,
  acceptance_order_reconstructed, original_study_identity and
  fixed_replication_claim_path.
- Immutable historical envelope: schema_version, status, reconstruction_head,
  original_study_slot_absent_at_completion, claim_ceiling, claim_boundary and
  deterministic_digest. Authenticate the entire original bytes and exact expected
  values; keep their meaning at c19db4a, not at the new operation HEAD.

These are a closed partition of all 23 keys (16 + 7); unknown/missing keys reject. Do not
strip arbitrary fields or normalize an old observation into a claimed new run.
Current pre-consumption absence is checked independently and recorded in the new
operation receipt. A historical absence assertion is never a live capability.

The new operation HEAD and time belong in a separate operation/verification
receipt, not in the deterministic certificate. Each operation must bind and keep
its own HEAD unchanged. Later documentation/review commits may be descendants
only when every source/evidence byte and endpoint remains exact. This permits
whole-certificate equality across review commits **without** weakening the old
same-HEAD verifier or deleting any historical provenance.

Both PUBLIC `screen_conjunction=false` results remain explicit, in fixed order,
under `historical_screen_conjunction` keyed by original_public and
receiver_v2_public. Full-summary equality is required before recording them.
Their 64 definitions derive from one source multiset each. Certificate integrity
is not a positive screen, improved search, causality or population inference.

## Source and operation gates

| Gate | Required evidence | Allowed effects |
| --- | --- | --- |
| C0: this design | Bounded local design review and read-only inventory | New design records only |
| C1: read-only certifier | New executable/test/policy closure, review, adverse-case tests and full regression validation | Implementation; no actual computation or publication by approval alone |
| C2: certificate proposal | Separately approved genuine complete reconstruction at frozen source | Stdout/local evidence only; exact proposed bytes for review, no issued certificate |
| C3: exclusive certificate publication | Exact proposal review; separately frozen/tested publisher; explicit certificate-only approval; fresh-process complete reconstruction and whole-certificate equality immediately before publication | One fixed certificate-only bundle; no candidate, search or study claim |
| C4: new coordinator qualification | Separately reviewed execution integration, expressly approved fixed PUBLIC attempt and independent full saved-summary verification | That PUBLIC exercise only |
| C5: original production | New candidate review and explicit exact-new-digest consent | The unchanged original study claim/output only |

C3's independent reconstruction uses the same frozen certifier in a new process
and private empty cache; it is not an algorithmically independent implementation.
Its verifier receipt references the complete certificate bytes, exact source,
reviewed proposal revision, actual HEAD, completed work and authority ceiling.
It must not be included inside the certificate it verifies (a circular hash).
If verification is performed earlier, publication still needs a genuine live
capture and final revalidation; a detached verification receipt is no substitute.

C2's exact stdout may be retained as the distinctly named review-only
`docs/qualifications/countdown_feedback_budget_receiver_e4_certificate_20261010.proposal.json`.
Its review commit is the fixed comparator for C3, not an issued certificate.
Do not pre-populate the issued bundle or its promoted mirrors to obtain a review
revision. The read-only verifier accepts that one fixed reviewed proposal, not a
caller-chosen JSON file. No proposal bytes/digest or review revision is allocated
by this design.

Proposed C1 closure: `scripts/feedback_budget_receiver_e4_certificate.py`,
`tests/test_feedback_budget_receiver_e4_certificate.py`,
`docs/strategy/countdown_feedback_budget_receiver_e4_certificate.md`.
This design document is not that acceptance policy. Freeze all three together
and chain the unchanged E4 source at c19db4a. No implementation OID/source digest
exists for these proposed files yet.

The later publisher has a separate complete executable/test/policy closure and
chains the certifier source. Its own changes cannot be hidden under the certifier
digest. Adding the publisher does not require modifying the certificate's
certifier receipt: publisher source and operation HEAD are bound in publication
records. No callable/source mutation during a qualified operation is allowed.

## Proposed publication transaction — not implemented

One proposed fixed bundle:
`artifacts/work/feedback-budget-receiver-e4-certificate-20261010-a`.
It has exactly `certificate.json`, `verification.json`, `COMMIT.json`.
There is **no authorization.json**, candidate, execution binding or consume call.
The suffix names this reviewed proposal, not an assertion of publication date.

Proposed promoted mirrors are
`docs/qualifications/countdown_feedback_budget_receiver_e4_certificate_20261010.{certificate,verification,commit}.json`.
The inventory confirms all proposed names absent; none is created or reserved.
No PUBLIC attempt identity/namespace or production candidate is assigned here.

Before the first filesystem effect, require absence using lexists semantics, exact
reviewed certificate bytes/digest, fixed paths, current source/runtime/evidence,
original unspent production slots and live reconstruction. Authenticate the
proposal before dereferencing its references. The publisher accepts no caller
proof, path, mapping, certificate generator or qualification callback.

Bundle absence is a pre-creation gate only. Afterwards require the exact owned
directory identity and exact completed filename prefix; do not require the
already created bundle to remain absent or adopt a foreign matching directory.
The publisher writes only the ignored raw bundle. Promoted mirrors are later
verbatim documentation of a verified bundle, not writes during its frozen-HEAD
transaction; mirror delivery failure cannot undo or reopen raw publication.

Use the existing reviewed descriptor-bound exclusive storage primitives, with
new certificate-specific ownership/transaction checks, not old bridge.prepare
or execution storage dispatch. Preserve every created file on failure; close
descriptors, do not clean up. Write certificate then verification, fsync each,
then COMMIT last and fsync the directory under the qualified storage contract.
COMMIT binds the exact two payload hashes/sizes/digests, full publisher source,
certifier source, proposal review revision, operation HEAD, fixed publication
scope and owned bundle location chain. It does not hash itself. Its schema and
owning-source closure must be fixed and adversarially tested before C3 approval.

Revalidate before and after each effect and the final owned-directory observation.
An occupied name (including a symlink), extra/missing file, changed generation,
partial write, fsync error, source/HEAD drift or uncertain response stops the
operation with exact completed/unknown effects retained. A fully written bundle
does not become “not published” because delivery or later validation failed.
No overwrite, unlink, adoption, resume, retry, alternate suffix or automatic
republishing is allowed. Metadata-only later inspection may report observed
state but cannot rerun the publication or mint permission.

## Lifetime and the original consumed-state boundary

Immutable facts: certificate bytes, source receipts, reviewed anchor bytes,
evidence archive generations, current identity chains and three old ledger rows.
Mutable lifecycle: absence before a permitted effect, then the exact owned
persisted claim after consumption. Parent mtimes or perpetual absence of all
future ledger additions are not timeless certificate properties.

C1/C3 are deliberately pre-consumption only. E4's `stable_state/revalidate`
calls `C.unused(S.REPLICATION)`; therefore neither that function nor a wrapper
around it can serve as post-consumption analysis. This design does **not**
implement that future analysis path or remove the existing absence gate.
C4 must separately own mode-specific live revalidation: absence before
consumption, exact authenticated owned claim/output binding afterwards, while
preserving the original three ledger bytes and permitting only approved new
claim/fence names. No “skip unused” boolean or caller-selected relaxed mode.

A certificate is stable historical evidence, not eternal receiver validity.
Any later device/inode/source/evidence drift rejects live use and requires a
separately reviewed case. Current checks cannot prove disk identity or reboot
cause, and cannot make source changes atomic with filesystem effects.

## Planned adverse cases — not implemented or passed

| ID | Case | Required outcome |
| --- | --- | --- |
| C-T01 | Old E4 PASS or self-consistent certificate supplied without fresh computation | No live capture, certification or publication |
| C-T02 | Same numeric E2/E4 device, missing owner, transitive mapping, changed chain | Reject exact direct-registry or endpoint mismatch |
| C-T03 | Wrong historical review/HEAD, rehashed JSON, redirected reference | Authenticate pinned bytes before parse/dereference; reject |
| C-T04 | Missing/extra key; bool/float count alias; duplicate JSON key; non-finite number | Closed-schema/type/canonical rejection |
| C-T05 | Skipped baseline/archive/cohort; copied summary; altered rejection order or generation reference | Full genuine work and whole-byte comparisons required |
| C-T06 | Added certifier/publisher file omitted from source, origin/callable or HEAD changes mid-work | Reject and preserve completed work/effects |
| C-T07 | Fresh-process comparison changes an otherwise unused certificate field | Entire canonical equality fails; no field-subset verification |
| C-T08 | Review commit changes only documentation vs changes protected source/evidence | Exact source/evidence plus ancestry allow the former; reject the latter; old verify_saved unchanged |
| C-T09 | Snapshot-only or forged old proof/callback offered to publisher | Reject interface; no effect reached |
| C-T10 | Expected owned bundle creation vs foreign/dangling path, extra file, write/fsync/delivery failure | Switch from pre-creation absence to exact owned prefix; retain occupied/partial/unknown state; no cleanup or retry |
| C-T11 | Certificate projection claims issued/qualified/authorized or includes a candidate | Reject; publication state separate and no candidate in bundle |
| C-T12 | Detached verification receipt used after live source/receiver drift | Reject before effect despite earlier PASS |
| C-T13 | Certificate includes the hash of its own later verification receipt | Reject circular provenance construction |
| C-T14 | Historical unused flag used forever, or broad skip-unused used after consumption | Reject; separately owned exact persisted-binding path required at C4 |
| C-T15 | Historical negative screen erased or original reference/input/schedule changed | Reject; no repaired result or new scientific identity |
| C-T16 | General “continue”, certificate-only approval or PUBLIC approval used for production | No dispatch; exact future candidate digest consent still required |

Regression tests of unchanged code cannot pass these new, unimplemented cases.
The next implementation review must map every applicable case to concrete tests
and distinguish fixture checks from genuine reconstruction and publication.
