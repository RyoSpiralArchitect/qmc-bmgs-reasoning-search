# Receiver v2: production entrypoint implemented, current binding rejected — 2026-10-01

## Outcome

The fixed-candidate execution entrypoint, synthetic boundary tests and bounded
single-agent source review are complete. Full repository validation passed:
**1,340 tests, zero skips**, plus compile, lint, artifact/provenance and CLI checks.

The actual metadata-only preflight **failed closed** because the output-parent
device binding differs from the saved candidate. The operational status is
**NOT_READY_TO_RUN**. No successful preflight or reviewed check exists. No
production run, original claim consumption, production analysis, candidate
regeneration, new cohort or new repository PUBLIC attempt occurred.

This is not a scientific result, a new admission proof or an execution approval.
No push, PR or merge was performed.

## Implementation and review

- Baseline: `667cc144ccb70073be8224a69b778f65107109da`.
- Frozen implementation: `4d419343d6a542a132d2336456000e9c638f1cc3`.
- [Entry point](../scripts/run_feedback_budget_receiver_replication.py),
  [45 boundary tests](../tests/test_feedback_budget_receiver_replication_entrypoint.py),
  [policy](strategy/countdown_feedback_budget_receiver_v2_entrypoint.md), and
  [bounded review](reviews/countdown_feedback_budget_receiver_v2_entrypoint_20261001.md).

The new source closure contains only the entrypoint, its tests and policy. The
existing qualified coordinator's five files and candidate-preparer's three files
remain unchanged. No source changed after the implementation was frozen.

The CLI separates metadata preflight/check, explicitly digest-confirmed run,
exclusive summary analysis/publication, and independent saved-summary replay.
Only the genuine unchanged coordinator can perform admission, consume the
original claim and search the original sealed schedule. Synthetic tests mock
that dispatch; they do not qualify production execution.

Source review corrected three boundaries before freeze: direct calls must also
supply a reviewed revision; analysis must disclose that it writes a summary;
and no post-commit checker exception may downgrade known consumption to unused.
Wrapper source checks at dispatch/progress/return do not extend the coordinator's
atomic transaction or its qualified source closure. A later run must keep source
and HEAD stable, preserve failures/uncertainty and never automatically retry.

## Observed blocker

The fixed candidate remains exactly 159,005 bytes, SHA-256
`7adaeba09ffdc21f21a852ad047b1aa7e0914ec284063a3ce768d410147fbb5b`, digest
`198f4582054184e2e476542afc1621178b3a1fbc6b82bd002b67f99c6684d070`.
The raw and reviewed candidate are byte-identical; neither was regenerated.

All seven components of the recorded output-parent path retain their lexical
paths and inode numbers, but their device number changed:

| Observation | Candidate binding | Current binding |
| --- | --- | --- |
| Device number for every component | 16777231 | 16777234 |
| Output-parent digest | `9a6974f79c4cd05b90a9a9d8b7661deb648a2784d9a4789ef78edb62428c723b` | `a4cd57c3080dae56d29bc22846d93ece45176d2dda15417f542e9971e1801da5` |
| Paths / inode numbers | Same seven-component chain | Same seven-component chain |

The path is `/Users/ryohiga/SpiralReality/qmc-bmgs-reasoning-search/artifacts/work`.
This observation does **not** prove the same physical disk or establish reboot
causality. The existing receiver policy expressly rejects later device or inode
transitions. Reading a uniform correspondence is not permission to accept it.

The wrapper rejected the candidate at its parent check with
`original output parent changed`. It never entered the production coordinator.
It did not repeat the earlier genuine admission reconstruction. The failure
receipt keeps `authorization_consumed: null`; separate point-in-time observation
shows the original claim/output/summary absent. These statements describe
different evidence boundaries and must not be conflated.

## Recorded operations and preservation

| Operation | Started / invocation observed UTC | Completion observed UTC | Result |
| --- | --- | --- | --- |
| Full repository validator | 2026-10-01 11:46:36 | 2026-10-01 12:03:56 | Exit 0; 1,340 tests in 854.023 s; no skips |
| Actual metadata-only preflight | 2026-10-01 11:46:36 | 2026-10-01 11:47:23 | Exit 1; parent binding differs; no dispatch |
| Read-only location/preservation observation | 2026-10-01 11:49:39 | 2026-10-01 11:49:55 | Exit 0; mismatch and preserved bytes recorded |
| Post-validation read-only observation | 2026-10-01 12:05:52 | 2026-10-01 12:06:20 | Exit 0; byte-identical observation |

The final focused set passed 45 tests in 1.991 seconds. Actual preflight and
observation used separate fresh processes/private caches and source-only imports;
the repository validator used a different fresh cache. Times are observations,
not comparative performance measurements.

- [Exact failed-preflight result](qualifications/countdown_feedback_budget_receiver_v2_entrypoint_20261001.preflight-failure.json).
- [Read-only location/preservation observation](qualifications/countdown_feedback_budget_receiver_v2_entrypoint_20261001.location-observation.json).
- [Operation counts, source/file hashes and captured-log references](qualifications/countdown_feedback_budget_receiver_v2_entrypoint_20261001.operations.json).

All **333 pre-existing tracked files / 78,928,252 bytes** were preserved by Git
blob hash and executable mode. The original raw candidate, all three sealed
cohort files and all three prior ledger records retain their exact bytes. The
original production output, v2 summary and fixed replication claim are absent.
The original 64-source / 1,024-cell study, schedule, matched budgets and seeds
are unchanged. There is no successful receipt at the preflight path required by
the entrypoint; a failed preflight cannot be promoted as one.

The post-validation observation reproduced the original observation byte for byte.
This was a read-only preservation check, not a second preflight invocation or a
retry of production execution. The three entrypoint source files also still
match their frozen implementation commit exactly.

## Next decision, not authorization

Stop before production and ask for a separately scoped **current-receiver
re-attestation design/review**. Preserve all old evidence; do not patch its device
numbers or broaden tolerances retrospectively. Any successor must cover all
required location/evidence chains through genuine reconstruction, retain the
original fixed study claim, and keep candidate review and explicit exact-digest
execution approval separate. No replacement candidate or new acceptance policy
is authorized by this report, the tests, or the previous request to continue.

The PUBLIC negative numerical screen remains durable. The original cohort is
conditional on its solvability filter; there is no new algorithmic superiority,
causal/population conclusion or locked-128 evaluation authority.
