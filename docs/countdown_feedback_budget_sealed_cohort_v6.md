# Feedback × budget v6: sealed development cohort

The fixed cohort has been generated once and independently verified by exact
recipe regeneration. This is an input-admission result, **not a search result or
execution authorization**. The frozen design, seed, exclusions, acceptance order,
192-cell schedule and search implementation were not changed.

## Realization

- Seed 26090401; max attempts 10000; six inputs in 1..10, target in 100..999.
- 18 candidates examined; 12 accepted. Rejections: 5 unsolvable under the frozen
  exhaustive solver, 1 previously excluded source multiset; no duplicate
  full-task/source or excluded-full-task rejection.
- 12 distinct tasks and 12 distinct source multisets, with zero overlap against
  the 179 full-task and 167 source-multiset exclusion identities.
- 192 planned cells, 96 budget pairs and 48 four-arm blocks; the 48 blocks are
  not 48 independent tasks.
- No search outcomes, hardness/calibration profiles or solution witnesses were
  inspected by the cohort adapter or persisted into the cohort.
- No development search or development authorization consumption has occurred.

The population is conditional on exhaustive solvability and the fixed identity
exclusions. It is not an unconditional random sample of Countdown tasks.

| Slot (acceptance order) | Inputs | Target |
| --- | --- | --- |
| 0 | 4, 7, 8, 9, 9, 10 | 346 |
| 1 | 4, 4, 6, 8, 9, 10 | 488 |
| 2 | 1, 1, 4, 9, 9, 10 | 416 |
| 3 | 1, 6, 6, 8, 9, 10 | 526 |
| 4 | 1, 3, 3, 5, 5, 8 | 460 |
| 5 | 1, 2, 5, 5, 6, 9 | 400 |
| 6 | 1, 1, 4, 6, 8, 9 | 425 |
| 7 | 1, 3, 6, 6, 8, 9 | 737 |
| 8 | 5, 6, 8, 8, 10, 10 | 164 |
| 9 | 1, 1, 2, 3, 8, 8 | 375 |
| 10 | 2, 3, 3, 4, 4, 5 | 722 |
| 11 | 1, 3, 6, 7, 8, 8 | 241 |

## Evidence

[Tracked three-file mirror](preregistrations/countdown_thompson_feedback_budget_v6/preregistration.json)
is byte-identical to the original private local directory
`artifacts/work/feedback-budget-development-cohort-v6`.
STARTED and SEALED are also mirrored without rewriting. The connector only
admits the original fixed local path; the Git mirror is for review, not a
replacement admission route.

Seal digest:
`e4533c2a3a6eb8425d5773445e835bf81797ea1f507d4fb76c5b18c24d8a7d34`

Canonical preregistration SHA-256 (361,087 bytes):
`3d7d68bebcb2708709cf410b9a469c644e900979ca5277636c3f032ae5f89cf8`

Cohort digest:
`eaac5c6bc4eeefcadf917cc54bfd97d368af7b96a755286010db32be99d488a2`

Task-set digest:
`7ce073d46261a133d9a1deb51da5eb7e064a3a011f48b96ff8b7719e0e797596`

The qualified admission receipt remains the historical
`c5f225bb1cc00be31429e888ddf334199e9da24b69fa00b382fca8c014648ce7`.
Its zero-generation / positive-seal-unqualified fields describe that earlier
preflight and were not rewritten. The new realization and independent
`COHORT_VERIFIED_NOT_AUTHORIZED` result are recorded here separately.
The admission executable is byte-identical to its approved source revision
`1f565588b673d8c16b62ed85a7ee140bbc973082`.
Generation ran with checkout HEAD
`9276606d151c553371fb3b507531c1bd065c45e3`; independent seal verification
ran from `e1b674f668c73474f6ed99df1e68af9f2c497aaf`.
Both used separate fresh private empty cache prefixes, absolute PYTHONPATH,
-P -B, the frozen runtime, and completed with exit 0.

The independently verified [PUBLIC connector qualification](reviews/countdown_feedback_budget_connector_20260910.md)
still has a null scientific decision and one public source multiset. It
qualifies the path, not this cohort's exploration performance.

## Remaining authority gate

Prepare the connector candidate against this exact seal and the tracked PUBLIC
connector summary; promote its unchanged bytes for review. The candidate must
remain `REVIEW_AND_EXPLICIT_CONFIRMATION_REQUIRED`, with
`candidate_is_execution_authority: false`. It is not an instruction to execute.

A separate explicit approval of the exact candidate and reviewed commit is
required before the one complete 192-cell run. Nothing here authorizes a retry,
alternate cohort, provider run or locked-128 evaluation.

## Validation follow-through

The public connector implementation passed 1,016 tests before receipt promotion.
The committed-tree guard subsequently gained a sixth receipt: its pre-commit
real-tree check correctly rejected the then-uncommitted file, and the old
hard-coded test expectation of five receipts was updated to six. All 13
provenance tests then passed (4.815 s), and the six-receipt ancestry guard passed.
These were metadata/test changes; the qualified computation and admission
executables were not modified.

Ignored operation logs are in
`artifacts/work/feedback-budget-cohort-v6-20260910.log`.
