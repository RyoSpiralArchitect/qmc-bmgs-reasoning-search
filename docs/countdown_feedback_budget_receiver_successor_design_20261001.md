# Current-receiver re-attestation design and review — 2026-10-01

## Result

The requested design and bounded local review are complete. The proposal preserves
the original 64-source study and all old evidence, but introduces a separately
owned verification path for the current receiver. It is **design only**: no new
production implementation, accepted mapping, certificate, candidate, PUBLIC
attempt or production execution was created. The earlier failed preflight remains
failed; current production status is **NOT_READY_TO_RUN**.

The main architectural finding is that an output-parent-only patch cannot work.
The unchanged coordinator independently checks its old parent, the old PUBLIC
publication locations and the old receiver certificate. Genuine recovery needs
explicit historical reconstruction and new current admission; a successor
execution path would then need its own PUBLIC qualification.

## Design decisions

1. Preserve three separate epochs: original device 16777233, prior receiver
   16777231 and currently observed 16777234. Authenticate the old 33→31 record;
   independently check both old epochs against current descriptors. No universal
   device-number substitution or inferred physical-disk identity.
2. Authenticate and reconstruct both historical PUBLIC archives and the original
   sealed acceptance metadata, without fabricating old admission objects or
   rewriting any historical proof. A saved-byte/hash check is not numerical replay.
3. Give any added verifier/coordinator its own source authority. Historical PUBLIC
   success does not qualify new code; any new full PUBLIC exercise requires its
   own later reviewed scope and exact fixed-attempt approval.
4. Preserve the same original production output/claim, scientific input manifest,
   schedule, budgets, seeds and thresholds. Before execution require absence;
   afterwards verify the exact persisted claim. Do not require permanent absence.

The immediate next proposed slice is **read-only verifier/provenance interfaces
plus synthetic rejection tests**. It should expose no certificate/candidate
publisher, claim consumption or experimental run CLI. Actual reconstruction,
evidence publication, new PUBLIC execution and production consent remain later
gates; none is authorized by this design document.

- [Detailed design and planned T01–T22 matrix](strategy/countdown_feedback_budget_receiver_successor_design_20261001.md).
- [Bounded single-agent design review](reviews/countdown_feedback_budget_receiver_successor_design_20261001.md).
- [Read-only final inventory](qualifications/countdown_feedback_budget_receiver_successor_design_20261001.inventory.json).
- [Validation, source/log hashes and operation counts](qualifications/countdown_feedback_budget_receiver_successor_design_20261001.operations.json).

## Actual evidence inspected

The final read-only inventory authenticated 12 reviewed JSON anchors, 11 recorded
location chains and 6 current directory locations. It closed both retained PUBLIC
archives against their exact reviewed COMMITs:

| Archive | Closed files | Cell files | Total bytes | Numerical replay in this task |
| --- | --- | --- | --- | --- |
| Original v7 PUBLIC | 1,027 | 1,024 | 136,421,856 | No |
| Receiver-v2 PUBLIC | 1,027 | 1,024 | 136,424,959 | No |

The 2,054 files total 272,846,815 bytes. Both authorization/claim linkages, the
v2 fixed fence, all three original sealed-cohort files, the three raw bridge
bundle files and the three prior ledger records matched their reviewed/anchored
bytes. STARTED hashes were authenticated before reference paths were read.
Two inventory passes were used; the second added raw bridge-bundle closure and
final current-directory revalidation. Both are observations, not re-attestations.

E0 has 3 recorded chains and E1 has 8. Their lexical paths and component inode
numbers match the current receiver, with device correspondences 16777233→16777234
and 16777231→16777234 respectively. No correspondence was accepted as authority.
The old bundle's historical directory identity is not recorded in the authenticated
bundle/certificate; it remains unknown, while its current descriptor and exact
file bytes are observable.

Final inventory digest:
`d4dacce39213262f5d79f5025e0f3b3f45856640e2dc65dfb66fbfae7aa38535`.

## Validation and preservation

Baseline and regression-validation revision:
`04114aee55d97b96d437ba49a9b1ef24898e9504`.
All existing production code, source closures, candidates and receipts are
unchanged. Fresh repository validation passed: **1,340 tests, zero skips, 823.850
seconds of test execution**, plus compile, lint, artifact/provenance and CLI
checks. It began at 2026-10-01 12:10:44 UTC and successful completion was observed
at 12:28:08 UTC. These times are operation observations, not performance comparisons.

The captured tool log contains one middle-output omission of 7,542 tokens. The
unittest summary, final `repository validation: PASS` and exit code 0 were retained;
the complete per-test transcript is unavailable in this captured copy. Preserve
that limitation rather than presenting the partial log as complete.

All **341 pre-existing tracked files / 79,008,950 bytes** remain identical by Git
blob hash and executable mode. The original output, v2 production summary, fixed
replication claim and successful v2 entrypoint preflight are absent; all three
prior ledger records remain byte-identical. The operations receipt records the
check and captured logs. This regression validation is not a test of the
unimplemented successor; its T01–T22 cases are specified, not executed.

No numerical PUBLIC replay, original acceptance-order reconstruction, new
receiver admission, experimental search, candidate/certificate issuance, claim
consumption, new cohort, push, PR or merge was performed. Existing negative PUBLIC
results remain durable. There is no new performance/causal/population conclusion
or locked-128 authorization.
