# E4 certificate verifier: bounded local implementation review — 2026-10-10

Scope: C1 read-only verifier, its tests/policy, immutable lower E4 source, and
read-only metadata/source preflight. This is a bounded same-agent review, not
independent-agent, external or human approval. The full validation result is
recorded in the final task report and operations receipt, not inferred here.

## Verdict and scope

No unresolved P1 finding found in this bounded C1 review. Local regression
validation completed successfully; the implementation is ready for the separate C2
decision: an actual full reconstruction producing a review-only proposal.
No issued certificate, publisher, new coordinator qualification, production
candidate or production authority exists. C2 approval has not been inferred
from C1 implementation approval.

Source freeze: `cf8d3f3bdb4d1bdff08669e4f8144fedeb0755d4`.
Source digest: `8b945162299cb7b5759058a75bd200f9822b45c51866d68f49f4e91d04c66041`.
The exact closure consists of the new executable, its 56-test file and its
acceptance policy. It chains unchanged E4 source at c19db4a and design at 0aeb46b.
All original 380 tracked files remain protected, including their full POSIX modes.

## Reviewed boundaries

| Risk | Concrete implementation / evidence | Remaining limit |
| --- | --- | --- |
| Saved PASS replaces computation | Historical files are pinned against reviewed Git and fixed byte hashes before parsing; the pure projection never registers a capture. The owned reconstruction calls genuine environment, both separate PUBLIC replays, and original cohort reconstruction before registering. | Numerical dispatch is MOCK-tested in C1; an actual C2 run is still required. |
| Detached JSON becomes a live proof | Private capture has no public constructor; exact registered type required; internal state retains actual snapshots, source/runtime/HEAD/locations and genuine PUBLIC Inputs. Operation receipt revalidates it. | An API boundary, not protection against a malicious interpreter/host; not an execution capability. |
| New code hidden under old source digest | Three new complete files have their own source receipt; old E4 digest remains exact. Own callable guards and phase checks surround the frozen helpers. | Future publisher needs a separate closure, not a claim under this one. |
| HEAD normalization or forgotten fields | Old 23-key observation is exactly partitioned into 16 fresh whole comparisons and 7 pinned historical envelope keys. c19db4a is retained. Certificate excludes current operation HEAD; detached operation receipt includes it. | Descendant review commits permitted only with unchanged protected bytes/identity. Old same-HEAD verifier unchanged. |
| Rehashed/type-alias/unused-field edits accepted | Strict parser plus full canonical equality closes the entire nested projection, including count types. Tests inject an extension into every nested object; missing/extra fields, duplicates, nonfinite values and bool/float count aliases reject. Fresh recomputation is followed by a second whole-byte comparison. | Digest equality alone is never evidence of computation. |
| Scientific or authority inflation | Complete original identities/denominators and both false historical PUBLIC screens are projected. Eleven false/zero claim ceilings; no publication-state field in certificate. | 2048 retained traces do not become 2048 independent sources; certificate integrity is not a positive screen or search improvement. |
| Failure loses completed work | 32 baseline traces retained after genuine environment returns; lower replay/cohort work records are retained through later comparisons/revalidation/delivery failures; unknown incomplete counters stay unknown. Short write/flush failures are distinct from completed stdout delivery. | stderr itself can fail; a successful receipt is never invented when delivery fails. Retain the process failure and any partial output, no automatic retry. |
| Perpetual absence or hidden consumption | The new operator calls no publisher, candidate, claim consumer or dispatcher. Frozen original-unused checks remain before live capture use. | C1 is pre-consumption. Separate C4 post-consumption persisted-binding logic remains unimplemented. |

Source attestation and genuine metadata-only preflight passed at the frozen
implementation HEAD. The preflight authenticated 3 historical E4 records, compared
7 complete metadata fields, 23 direct historical chains / 6 current location
roles, 16 reviewed anchors and 2 PUBLIC archive closures. It did **not** call the
baseline, replay or cohort generator, enter the reconstruction attempt, create a
live capture, generate a proposal or issue a certificate.

## Retained iteration failures

First focused run: 48 tests, 12 failures and 4 errors. Four distinct causes:

1. Mock OIDs reached real Git existence checks; test wiring now explicitly mocks
   those checks while separate invalid-OID/ancestor tests retain their boundary.
2. Outside-checkout CLI tests inherited relative PYTHONPATH; their environment now
   supplies the absolute source path, as the frozen runtime requires.
3. The draft static guard unnecessarily performed the source/cache-origin
   attestation, so static self-test needed an attestation cache. Source/cache
   origin authentication remains in every actual attestation; static callable
   checks no longer claim or require runtime qualification.
4. The missing-digest negative test accidentally reinserted that digest via its
   rehash helper. The test now genuinely omits it; the parser was not weakened.

Second run: 48 tests passed. Eight further boundary tests were added, including
source-generation drift, review-descendant stability, original slot occupation,
fresh whole-certificate mismatch after a valid template, HEAD/ancestor failures,
known consumption-state retention and short/failed stdout delivery. Final focused
run: 56 tests passed in 18.376s, zero skips. All three logs are retained.

The acceptance policy maps all C-T01–C-T16 requirements to current test coverage
and explicit gaps. C-T09 publisher consumption, C-T10 exclusive bundle/partial
publication, and C-T14 post-consumption analysis are **not implemented/tested** by
this C1 slice. Local tests and source metadata checks do not close those gates.

## Next gate

After C1 regression validation and explicit C2 approval, perform exactly the
genuine complete reconstruction at this frozen source in a new private-cache
process. Retain stdout only as the fixed review-only proposal plus separate
operation evidence. Review those exact bytes before designing/freezing the C3
publisher. Certificate publication, new PUBLIC qualification and exact-new-digest
production consent stay separate; no push/PR/merge is included in this work.

## Completed regression evidence

Local full validation passed: **1540 tests in 935.858s, zero skips**, plus
compile, ruff, artifact/provenance and CLI checks; exit0, final repository
validation PASS. Observed launch 2026-10-10 08:22:55 UTC and completion
2026-10-10 08:41:12 UTC. This includes real PUBLIC kernel work under synthetic
regression bindings, not actual C2 reconstruction or production. Logs and
preservation receipts are linked from the
[task report](../countdown_feedback_budget_receiver_e4_certificate_implementation_20261010.md).
