# Receiver v2: prepare and review the original replication candidate

This operation prepares metadata and independently exercises admission only.
It does not run the sealed study, consume a claim, approve a digest, prepare a
replacement cohort, or create a production execution CLI. It changes none of
the previously qualified coordinator, numerical, storage or PUBLIC evidence.

## Frozen dependencies and additive operator

- Coordinator: `c0b048e401d39802c46acd70060ad9af27b0a911`, source digest
  `680caead90bb00f483eafc86ba75e67703b57014457d3834f0e772409a6ac329`.
- PUBLIC evidence review: `ba51b631d6398d0813a36614b3d27821d019162e`.
- Exact PUBLIC summary digest:
  `a85537a8b496a4a39be765686eda8d9e26fd9b66df252125a5a8ba1df86e7757`.

`scripts/feedback_budget_receiver_candidate.py` has its own source receipt
covering itself, `tests/test_feedback_budget_receiver_candidate.py`, and this
policy. Its receipt is preparer provenance, not a replacement for the qualified
coordinator's five-file source receipt or an extension of execution authority.
The closed candidate schema is owned by the unchanged coordinator.

Commit this operator first. Prepare only at that frozen implementation HEAD in
a clean checkout with a fresh owned mode-0700 cache, absolute `PYTHONPATH` to
`src`, and `python3 -P -B`. Preserve source and artifacts throughout each operation.
Run the repository validator after code changes. Synthetic boundary tests and
actual independent admission are separate evidence classes.

## Fixed candidate; original study and claim retained

Raw candidate:
`artifacts/work/feedback-budget-replication-v7-20260913-a.receiver-v2.authorization.json`.

Reviewed candidate:
`docs/preregistrations/countdown_feedback_budget_receiver_v2.authorization.json`.

Reviewed preparation receipt:
`docs/qualifications/countdown_feedback_budget_receiver_v2_candidate_20260923.preparation.json`.

The output remains `artifacts/work/feedback-budget-replication-v7-20260913-a`,
with the original fixed replication claim. There is no v2 replacement claim or
output slot. Preserve all v1 candidates/certificates, the spent PUBLIC claims and
fixed PUBLIC fence, and the original sealed 64-source, 1,024-cell schedule.

Reject any occupied raw candidate, promoted candidate, preparation mirror,
production output, production summary or fixed replication claim before preparing.
No caller-selected paths, seeds, study identities, mode switches or retry slots
exist. Exclusive publication retains an occupied or uncertain candidate on
failure; never overwrite, delete, adopt or regenerate it automatically. Failed
or uncertain output delivery is not evidence that publication did not occur.

## Prepare, promote, independently reconstruct

Preparation authenticates the reviewed PUBLIC summary/COMMIT and independent
verification result, checks the local saved summary matches, and invokes the
real frozen `qualified_public` path. It separately invokes genuine receiver
admission for the original sealed inputs, then uses the unchanged coordinator
candidate constructor. No fabricated admission/inputs, patched callback or
replacement reference is accepted in an actual operation.

Preparation writes only the fixed new candidate. Promote its exact bytes and
the successful canonical preparation result, then commit their review. A fresh
process checks those reviewed bytes, the original raw candidate and operator
source, and invokes the real frozen `admit(REPLICATION, ...)` path. It reconstructs
the PUBLIC qualification and original receiver admission and compares the complete
candidate, without invoking run, consume, record generation or sealed-task search.
The PUBLIC verification path replays existing PUBLIC traces; this is not a new
PUBLIC attempt or a sealed-study execution.

The CLI exposes only static self-test, preparation, and candidate verification.
Verification reads the candidate's digest for integrity checking; this is **not**
the user's explicit execution confirmation. The result remains
`candidate_is_execution_authority = false`,
`replication_execution_authorized = false`, `replication_search_calls = 0`, and
`locked_128_evaluation_authorized = false`.

Record the exact preparer implementation/review commits, candidate digest and
file hash, preparation/verification results and captured log hashes. Check that
the original production output/claim remain absent before and after. A successful
review proves authentic production **admission**, not production execution.
Do not relabel static/synthetic checks as independent actual admission.

## Remaining execution gate and scientific ceiling

Stop after candidate review. Any later run needs explicit user confirmation of
this exact digest and a separately reviewed execution entry point which calls
the unchanged qualified coordinator. Existing approvals and this successful
preparation do not supply that authority. No push, PR or merge is part of this
candidate preparation task.

The PUBLIC negative numerical screen is preserved. Neither the new candidate,
source attestation nor admission verification supplies new scientific evidence,
algorithm superiority, population inference or causal identification. The sealed
cohort is conditional on its existing solvability filter, not a fresh population
sample. Do not select new tasks, tune thresholds or spend the fixed study merely
to obtain a favorable result.
