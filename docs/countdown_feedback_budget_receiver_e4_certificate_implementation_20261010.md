# E4 certificate verifier implementation — 2026-10-10

Status: **C1 implemented and locally validated; C2 actual proposal reconstruction
not performed. No certificate issued or execution authority.**

## Delivered

An additive read-only verifier now owns the genuine reconstruction sequence and
its private live evidence capture. Saved E4 PASS records and detached JSON cannot
replace that computation. A second entry point authenticates the fixed reviewed
proposal and repeats the complete computation before whole-certificate equality.
No publisher, candidate, claim consumer, dispatcher, new PUBLIC attempt or
production/consent override was added.

The source closure at `cf8d3f3bdb4d1bdff08669e4f8144fedeb0755d4` is exactly:

- [Executable](../scripts/feedback_budget_receiver_e4_certificate.py)
- [56 boundary tests](../tests/test_feedback_budget_receiver_e4_certificate.py)
- [Acceptance policy and C-T01–C-T16 coverage limits](strategy/countdown_feedback_budget_receiver_e4_certificate.md)

Source digest:
`8b945162299cb7b5759058a75bd200f9822b45c51866d68f49f4e91d04c66041`.
The original E4 source c19db4a, same-HEAD verifier, historical records and the
original study remain unchanged. The certificate schema preserves all 23 old
observation keys through its explicit 16 freshly compared / 7 historical-envelope
partition, both false historical PUBLIC screens and the original sealed-study
generation/input/schedule/seal/output/global-claim identities.

## Evidence levels

| Level | Actual result | Does not establish |
| --- | --- | --- |
| Focused C1 tests | 56 passed in 18.376s, zero skips; synthetic numerical wiring and adversarial comparisons | An actual certifier baseline, PUBLIC replay or original cohort reconstruction |
| Source attestation | Exact three-file source closure and unchanged frozen E4 chain | Current numerical qualification or certificate issuance |
| Genuine metadata-only preflight | 3 historical E4 records, 7 full metadata fields, 23 direct chains / 6 roles, 16 reviewed anchors, 2 PUBLIC archive closures; source/evidence revalidation passed | A live reconstruction capture, proposal, positive screen or execution authority |
| Full repository regression | 1540 tests in 935.858s, zero skips; compile, ruff, artifact/provenance and CLI checks all passed; exit0 | CI, original-study execution, new PUBLIC qualification or search superiority |
| Bounded local review | No unresolved P1 found in C1; all design cases mapped with explicit gaps | Independent-agent, external or human approval |

Completed counters survive later comparison or delivery failures; entered-but-
unfinished counts remain unknown. A short/failed stdout write is distinguished
from completed stdout delivery followed by a stderr failure. No retry/resume or
publication side effect is available. Reading detached bytes is not perpetual
receiver validity. The private capture is an API boundary, not a hostile-host
security claim or an execution capability.

The full validation ran at the frozen implementation HEAD; observed launch was
2026-10-10 08:22:55 UTC and completion 08:41:12 UTC. Its real PUBLIC kernel work
uses synthetic regression bindings, not an actual original-study/C2 operation.
The detailed log and exact hash are retained in the operations receipt.

## Preserved evidence and original study

The pre/post inventories preserve all **380** previously tracked files /
**80139016 bytes**, with full POSIX modes; both 1027-file PUBLIC archives
(2054 files / 272846815 bytes total); the original three-file seal; all three
ledger records; and the four absent original study slots. The proposal, proposed
certificate bundle and three issued-mirror names remain absent and unreserved.

The 2048 retained PUBLIC trace replays in the historical evidence are not 2048
independent sources: each PUBLIC archive uses one source multiset. The original
64 accepted sealed sources, 102 examined attempts and 38 rejections are unchanged
and conditional on exhaustive solvability. No replication-policy cell was run.

## Review and retained failures

The [bounded review](reviews/countdown_feedback_budget_receiver_e4_certificate_implementation_20261010.md)
records both the successful tests and the first rejected run (48 tests, 12 failures,
4 errors). Fixes were confined to the new files: explicit mock Git authority,
absolute CLI source path, keeping static self-test separate from actual cache-
origin attestation, and correcting a missing-digest mutation test that had
reinserted the digest itself. Intermediate 48-test PASS and final 56-test PASS
logs are both retained. Old sources, receipts and tolerances were not changed.

C-T09 future publisher consumption, C-T10 exclusive bundle/partial-publication
handling, and C-T14 post-consumption C4 analysis remain unimplemented. Their
requirements are not represented as passed by these C1 tests.

## Machine-readable records

- [Source receipt](qualifications/countdown_feedback_budget_receiver_e4_certificate_implementation_20261010.source.json)
- [Read-only metadata preflight](qualifications/countdown_feedback_budget_receiver_e4_certificate_implementation_20261010.metadata.json)
- [Preservation inventory](qualifications/countdown_feedback_budget_receiver_e4_certificate_implementation_20261010.inventory.json)
- [Operations, log hashes and validation receipt](qualifications/countdown_feedback_budget_receiver_e4_certificate_implementation_20261010.operations.json)

These are C1 implementation records, not the future proposal or issued certificate.
Detailed logs/helpers remain local under the distinct ignored prefix
`artifacts/work/feedback-budget-receiver-e4-certificate-implementation-20261010.`.
No push, PR, merge, CI or external review was performed.

## Smallest next gate

**C2, with explicit approval:** run the genuine full path at this frozen source
in a fresh process/private empty cache and retain a review-only certificate
proposal plus separate operation evidence. Inspect its exact full bytes before
the separate C3 publisher design/implementation/freeze and certificate-only
publication approval. New coordinator/PUBLIC qualification is C4; original
production remains C5 with a reviewed new candidate and exact-new-digest consent.
The original claim/output are not replaced, widened or silently retried.
