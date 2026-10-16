# Receiver v2: original production candidate and admission review — 2026-09-23

## Result and boundary

The fixed v2 production candidate was prepared, reviewed locally, committed,
and independently reconstructed by the genuine frozen production admission
path in a fresh process. Both actual operations exited successfully.
This verifies **production admission**, not production adapter execution.

The original sealed study remains unexecuted and unauthorized: zero replication
search calls, no production output, and the original fixed claim remains
unoccupied. No new cohort or PUBLIC attempt was created. No execution entry
point, exact-digest execution confirmation, push, PR or merge was part of this
task.

“Independent” here means a fresh process and actual reconstruction using the
unchanged coordinator. It does not mean an independent implementation, separate
agent, external reviewer or human approval. The code and metadata reviews in
this task were bounded single-agent reviews.

## Frozen candidate and source identities

- Prior PUBLIC evidence / baseline:
  `ba51b631d6398d0813a36614b3d27821d019162e`.
- Candidate operator implementation:
  `9d14059362e18a396e4fa865d8a0b3c69fde1eb6`.
- Candidate/preparation review and verification HEAD:
  `119aaf9cef45276c41964b1ec45650534e6df48a`.
- Unchanged qualified coordinator:
  `c0b048e401d39802c46acd70060ad9af27b0a911`;
  source digest
  `680caead90bb00f483eafc86ba75e67703b57014457d3834f0e772409a6ac329`.
- Exact reviewed PUBLIC summary digest:
  `a85537a8b496a4a39be765686eda8d9e26fd9b66df252125a5a8ba1df86e7757`.
- Separate three-file preparer source digest:
  `cd7497f62f81fe7a5fc1a8b4a0a725bdbaf8b4754aee3d8328d447f8afcf12ee`.

[Prepared candidate](preregistrations/countdown_feedback_budget_receiver_v2.authorization.json):

`198f4582054184e2e476542afc1621178b3a1fbc6b82bd002b67f99c6684d070`

The file is exactly 159,005 bytes, SHA-256
`7adaeba09ffdc21f21a852ad047b1aa7e0914ec284063a3ce768d410147fbb5b`.
Its reviewed bytes equal the original raw candidate; it was not regenerated
for verification.

The three-file preparer closure covers the new operator, its tests and
[candidate policy](strategy/countdown_feedback_budget_receiver_v2_candidate.md).
It does not replace or extend the coordinator's qualified five-file closure.

## Same original study, not a replacement attempt

The logical identity remains
`feedback_budget_confirmation_64_seed_26091301/v1`: the original 64-source,
1,024-cell sealed schedule, budgets and seeds, with the original output and
fixed replication claim.

- Input manifest:
  `4a969fc46e506d2fc81e0b9a45c841bb8e27f81fb7190ff73abbd72d9fe284b3`.
- Schedule:
  `0da39f97a3bd1e6068d33dae9658c7c3656b3a76aa8854e0a4820683b622352b`.
- Production output remains
  `artifacts/work/feedback-budget-replication-v7-20260913-a`.
- Fixed claim remains
  `artifacts/work/feedback-budget-v7-authorization-ledger/replication-548114440db6e0fa49226e28d519fbe1c0f113d5edfe76f282e7ebc29c0bfc3c.json`.

Compared with the original v1 candidate, 18 shared fields are identical,
including the full original admission proof, authorities, baseline, source,
runtime, cohort seal, schedule and output binding. The changed shared fields
are the schema, connector qualification and digest. The v1 bridge/certificate
fields are replaced by the qualified coordinator/receiver-admission fields and
the explicit original attempt identity.

The candidate was also independently predicted from saved metadata; its byte
count, full file hash and digest matched. That comparison is corroboration,
not a substitute for the genuine runtime admission check below.

## Validation and actual operations

Full repository validation against the frozen implementation passed:
**1,295 tests, zero skips, 869.792 seconds of test execution**, plus the repository
compile, lint, artifact and CLI checks. The 34 new focused tests passed in
6.131 seconds; these are synthetic boundary tests, not scientific execution.

The [local review record](reviews/countdown_feedback_budget_receiver_v2_candidate_20260923.md)
documents the bounded review, two corrected test-fixture issues, and the
separate actual-operation evidence. No actionable source or metadata defect
remained in that review.

Each actual candidate operation used a fresh process, fresh private cache,
absolute source path and `python3 -P -B`. There was exactly one preparation and
one fresh-process candidate verification invocation; neither called the
production run/consume path. Existing PUBLIC traces and original cohort
acceptance metadata were reconstructed as verification computations.

| Operation | Started (UTC) | Completion observed (UTC) | Exit / result |
| --- | --- | --- | --- |
| Repository validation | 2026-09-23 07:26:34 | 2026-09-23 07:44:23 | 0 / PASS |
| Candidate preparation | 2026-09-23 07:26:34 | 2026-09-23 08:32:49 | 0 / prepared, not authorized |
| Fresh-process production admission | 2026-09-23 08:34:37 | 2026-09-23 09:40:57 | 0 / independently reconstructed, not authorized |

Completion times are observation times, not benchmark measurements. Intermediate
stage messages may announce stage entry; successful final receipts establish
completion.

- [Exact preparation result](qualifications/countdown_feedback_budget_receiver_v2_candidate_20260923.preparation.json):
  digest `f527794d935ad8e3ffb51c17a1e0f97d90b80771bd91ec1f7a12180a2b7d0061`.
- [Exact verification result](qualifications/countdown_feedback_budget_receiver_v2_candidate_20260923.verification.json):
  digest `68cabef308820b5f2a10cecd97bebbb6aee3ae43c86dd674363b3de51504a367`.
- [Operator observations, artifact identities and captured-log hashes](qualifications/countdown_feedback_budget_receiver_v2_candidate_20260923.operations.json).

The verifier checked reviewed candidate/preparation bytes, reconstructed the
reviewed PUBLIC qualification and original receiver admission through genuine
entry points, compared the entire candidate, and rechecked source, evidence
and unused production state. Reading the candidate digest for this integrity
comparison was not the user's execution confirmation.

## Preservation and final packaging check

The read-only post-verification packaging check passed at 2026-09-23 09:41:24 UTC.
All **324 pre-existing tracked files / 78,689,314 bytes** remain identical to
the baseline by Git blob hash and executable mode. Both source closures match
their implementation commits. The raw PUBLIC summary/COMMIT match their
reviewed mirrors, and the exact original sealed payload still matches its
candidate-bound digest and hash.

The three prior authorization-ledger records are unchanged. Original production
output, receiver-v2 replication summary and fixed replication claim are absent.
The raw candidate and both final CLI results are promoted byte-identically.
Captured logs and the read-only packaging-check source/output remain local and
ignored; their identities are retained in the operator observations.

## Scientific ceiling and next separate gate

The previous PUBLIC screen remains **false**, and its scientific decision
remains `null`. This task provides no new performance, causal, population or
QMC-superiority result. The sealed 64-source cohort remains conditional on its
existing solvability filter, not an unconditional population sample.

The production admission path has now actually been exercised. The production
generation/publication adapter has **not** been executed, and admission success
does not establish successful production execution.

Stop here. A later run needs a separately reviewed execution entry point,
explicit user confirmation of the exact candidate digest above, and fresh
checks of the unchanged source/evidence, output binding and unspent original
claim. Do not replace the candidate, create another cohort, change the fixed
claim/output, tune the screen or infer permission from this successful review.
