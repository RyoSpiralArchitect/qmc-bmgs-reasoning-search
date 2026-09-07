# Feedback × budget v6: full public fixture observation

Date: 2026-09-05. Corrected source:
`112d41b4d729c826377c0619f7953db35c75a063`.

All **192 fixed public cells** were executed, durably stored, independently
reanalyzed in a second source-only process, and the saved summary checked in a
third process. All **96 same-scale budget pairs** preserved their full accepted
event prefix and met the completion requirements.

| Verified terminal count at B256 → B512 | Public task/seed/scale pairs |
|---|---:|
| 2 → 4 | 87 |
| 2 → 5 | 9 |
| Total | 96 |

Every cell stopped on the legal-action-score budget alone, with zero overshoot
and positive headroom on every secondary guard. Every trace passed generative
material validation and byte-identical replay. The added continuation completed
the actual low run's current-next trajectory. Exact-success and minimum-error
prefix consequences held.

The fixture uses the previously fixed inputs `(1,2,3,4,5,6)`, targets 1–12,
budgets 256/512, scales 0/16, and seeds 8192–8195. These twelve public targets
share **one source multiset**. Their completion counts demonstrate the fixture
and resource-extension checks; they are not development-cohort feedback effects,
independent task evidence, or a general 2× performance claim.

## Saved evidence

The committed input directory contains exactly **195 files**: STARTED, 192
immutable cell files, RECEIPT, and COMMIT. Cell files total **24,431,895 bytes**.
The independent summary is saved outside that directory.

- Local ignored input: `artifacts/work/feedback-budget-full-shape-v6-20260905-r2`.
- Local ignored summary: `artifacts/work/feedback-budget-full-shape-v6-20260905-r2.summary.json`.
- [Tracked commit manifest](../qualifications/countdown_feedback_budget_v6_full_shape_20260905.commit.json)
  enumerates all 192 cell hashes and sizes. File SHA-256:
  `16ce27faf77cdeb8c96939428ed5eeb5c1a2f55eeb5b0b4bbfb9da513b679110`.
- Commit deterministic digest:
  `92283ed5f61fa5a431af9520d6d8502febe604da9543d8040dc0b109c803782c`.
- [Tracked independent summary](../qualifications/countdown_feedback_budget_v6_full_shape_20260905.summary.json)
  contains source/runtime receipts and every replay/prefix check. File SHA-256:
  `311701c63f87d04d956214554c38bcae612d5100225113b30b264450f4299011`.
- Summary deterministic digest:
  `620871116058d135567706245d04264ef6d6035e82ad53049c967cada0189026`.
- Integrity receipt deterministic digest:
  `c4adfb8896fbcaacf53bb15e09cbfce1c13b5c565450bfc60d850b670a96ac97`.
- Integrity analysis deterministic digest:
  `e4fd62904e6bbd09eacd981685fb688c35c3fb5795372751f4162a424068c9ae`.
- [Exact fixture manifest](../fixtures/countdown_feedback_budget_v6_full_shape.json)
  file SHA-256:
  `418e264e9b6653f6b387efcf6ba53531bc23c7d629527e24b50eac9cf0835c7c`.

The original 32-trace baseline is reproduced during each full-fixture process.
The corrected 32-trace verifier was also run separately against a fresh
qualification: [refreshed public receipt](../qualifications/countdown_feedback_budget_v6_public_revalidated_20260905.json),
file SHA-256
`cd53c88191c130d1ae457b9664988939eae4ae8047bd9f37d9afed29f594532c`,
deterministic digest
`3ccc94562e01dea7a733e31b7bfa855c28416a3f180d5096b89adf0bedea9d3c`.
Its raw files remain at `artifacts/work/feedback-budget-public-v6-20260905-r2`.
The original historical receipt remains unchanged.

## Review correction and retained earlier run

The full-PR fresh review found a late-directory-entry check missing from the
earlier 32-trace verifier. It was corrected and covered by a regression; re-review
confirmed resolution. See the [review record](../reviews/countdown_feedback_budget_v6_full_shape_20260905.md).

The initial full-shaped public run at `4ef632dcb5f17f66b66590e61168ea15e4aa5a76`
passed its own checks and remains locally retained, rather than being overwritten.
The corrected-source rerun reproduced every cell hash and the complete integrity
receipt exactly. New source/publication/summary receipts bind the corrected code.
The `r2` suffix denotes this public validation rerun, not a new scientific design,
new fixture identity, or outcome-selected cohort.

## Next work

The public fixture's execute/save/analyze/verify path is complete. Production
domains, cohort/seal building, the production runner/analyzer and publication
qualification, and a concrete execution authorization candidate remain.
No new development cohort or provider calls were used. The original
`STOP_REPAIR_NO_LOCKED_128_RUN` and consumed authorization are unchanged.
