# Feedback × budget v6: public qualification observation

Date: 2026-09-05. Scope: one fixed public Countdown-D6 problem,
`(1,2,3,4,5,6) -> 720`.

The budget-extension and legacy-guard qualification passed, and a separate
source-only process independently verified the saved evidence. All 32 traces
passed generative material validation and byte-identical replay: 16 new-profile,
eight legacy-score256, and eight existing v5 anchor traces.

For every one of the eight scale/seed budget pairs (scales 0/16, seeds
8192–8195), B256 completed **2** verified terminals and B512 completed **4**.
All eight low accepted histories exactly matched the corresponding high
history's prefix, retaining every event field and hash. The first added
terminal completed trajectory index 2, the low run's current-next trajectory.
All eight legacy/new B256 comparisons had exactly equal accepted histories.
All 24 budgeted traces stopped on the primary score budget alone, with no
overshoot and positive secondary headroom.

These measurements qualify the intended resource intervention on this public
problem. They do not measure feedback benefit on the future development cohort.
Additional completions do not imply distinct solutions, improved error, or
increased exact success. The eight public prefix checks are separate from the
future study's 96 checks.

## Evidence

- Qualified code revision:
  `d63980cf715788d0e8062afb9ceb58bb6fef1dc0`.
- [Complete public receipt](../qualifications/countdown_feedback_budget_v6_public_20260905.json),
  file SHA-256:
  `ee8cb216499f678c05c836d77443196c853cbc5dfb184c73448745e07e6dfa53`.
- Receipt deterministic digest:
  `a5a29a329520c35c6b05e902d0ee9b39b3577af46d8fb5b0492455791b5edd76`.
- Retained raw records: 24 canonical JSONL rows, 2,897,417 bytes,
  SHA-256 `25c8d8e11f12c5bcbfabb8f0b285e4972fa75204ff9c89f700a3a7cfb480a139`.
- Local ignored evidence directory:
  `artifacts/work/feedback-budget-public-v6-20260905`.
- Public fixture identity manifest digest:
  `fa7c57c057a5e2d68ca167de8e95dfdd859780720215f8c8feeecf76e952ce9a`.
- Exact search/IID runtime reproduced: CPython 3.13.13, arm64 CPU float64,
  Torch 2.11.0. The complete source and runtime receipts are included.
- Independent `--verify` reproduced the same receipt digest in a new process.

The eight old anchor raw traces are regenerated during both qualification and
verification; their expected trace/projection digests and replay receipts remain
in the tracked public receipt. The 24 budgeted raw traces stay local and ignored.
See [the implementation and reproduction guide](../countdown_feedback_budget_public_qualification.md).

## Remaining gate

The twelve planned public full-shape fixture identities and their source
exclusion are fixed. Their 192-cell run, new production manifest/runner/analyzer,
publication qualification, fresh cohort seal, and execution authorization remain
future work. No v6 development cells or provider calls were executed, and no
development execution permission is granted. The prior
`STOP_REPAIR_NO_LOCKED_128_RUN` and consumed authorization remain unchanged.
