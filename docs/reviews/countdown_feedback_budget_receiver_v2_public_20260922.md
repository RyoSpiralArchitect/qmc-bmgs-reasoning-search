# Receiver coordinator v2 PUBLIC qualification: design and implementation review

Scope: the additive PUBLIC-only coordinator, its fixed-attempt fence, authentic
receiver admission, and the dormant sealed-mode boundary. No review authorizes
replication, a replacement cohort, a fresh scientific study, or retrying a spent
PUBLIC attempt. Original bridge code and evidence remain unchanged.

## Design review

Independent read-only design and inventory passes identified that the preserved
v1 `run` and `analyze` functions are replication-only. A separate wrapper around
the old connector or a patched admission object would not qualify those functions.
The selected design is an additive successor with its own source receipt, genuine
v1 evidence admission, distinct PUBLIC inputs, and a genuinely shared run/analysis
coordinator. PUBLIC execution qualifies that successor's exercised path, not the
unchanged v1 runner or a production adapter that has not run.

The dormant production adapter is included in the source closure, but there is
no production CLI or production candidate preparation in this task. Future use
requires a new exact reviewed authorization binding this coordinator and its
independently verified PUBLIC evidence. The original production claim is retained.

The ordinary PUBLIC storage claim is keyed by candidate digest. Review therefore
required an additional fixed logical-attempt fence, consumed first, so a changed
candidate cannot revive a failed pre-output attempt. Its entire payload, including
the deterministic correlation nonce, is derivable from the reviewed authorization
and recorded execution identities. Neither fence nor claim is deleted on failure.

## Implementation findings and dispositions

Two actionable P2 findings were reported by a separate read-only code reviewer:

1. An already occupied fixed summary could allow irreversible PUBLIC consumption
   before later summary publication failed. The pre-consumption `unused` check
   now rejects the fixed summary, including dangling symlinks, before admission,
   fence consumption or search.
2. Analysis failures and result-delivery failures could report an authorization
   as unused even though persisted claims were spent. Incomplete analysis or
   verification now reports unknown consumption state; completed analysis or
   verification followed by delivery failure reports consumed state.

Additional operator hardening rejects an occupied candidate-keyed claim before
admission or creating a replacement fence, even if the fixed fence is missing.
The initial authorization snapshot is checked again after full admission.

The reviewer rechecked coordinator SHA-256
`2755b2b25a5a72b88eec9881fa1eaf23c192cfb95badb97e35e86c9529836e7c`
and found no remaining confirmed actionable defect within this bounded scope.
The review checked authentic v1 admission, source/runtime revalidation, unchanged
production namespace, and reusable post-consumption PUBLIC verification without
a replication-claim-absence condition.

## Evidence limits at review time

This record covers design inspection, static code review and isolated mocked
boundary proofs. The new fixed-attempt helper's 16 synthetic tests passed before
integration. Coordinator boundary tests and full repository validation are
recorded separately when complete. No real PUBLIC execution, independent new
summary replay, production search or real claim consumption occurred in these
reviews. Those claims require the subsequent actual-operation receipts.

Before source freeze, all 31 coordinator boundary tests and all 16 fixed-attempt
helper tests passed. These 47 tests remain synthetic control-flow/storage
evidence, not the actual PUBLIC qualification.

## Frozen implementation and PUBLIC candidate review

Implementation: `c0b048e401d39802c46acd70060ad9af27b0a911`.
Full repository validation exited 0 with PASS: 1,261 tests in 918.395 seconds,
no skips; completion observed at 2026-09-22 06:57:37 UTC. PUBLIC preparation
also exited 0, observed at 07:02:57 UTC, after exact historical reconstruction.
These are operator timings, not algorithm-performance measurements.

The separate candidate metadata review verified exact raw/promoted bytes:
158,036 bytes, SHA-256
`3a9ea6e0821873d748c02fddcfaab76d7d172b447b1aee8e3e331cd4fee804da`,
candidate digest
`1ae46982b68ec28659fd8695428ccc8c044928310d4addf5650ecf915d022f48`.
The coordinator source digest is
`680caead90bb00f483eafc86ba75e67703b57014457d3834f0e772409a6ac329`.

The reviewer checked the five new protected files, three unchanged v1 files,
76 historical protected source/artifact entries, original reviewed receipts,
fixed PUBLIC manifest and full schedule, and current output-parent identities.
No actionable mismatch was found. The new PUBLIC fence, candidate claim, output
and summary were absent; the ledger contained only the old PUBLIC claim.
Original production output and claim were also absent.

This is metadata review, not runtime admission or execution. Preparation success
is separately established by its captured exit and receipt; file existence alone
was not counted as completion. The exact promoted candidate must next be committed
and independently admitted by the real PUBLIC run. No production candidate or
production execution is authorized by this record.
