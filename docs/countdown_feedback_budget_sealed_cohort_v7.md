# Feedback × budget v7: sealed inputs and review-only execution candidate

Date: 2026-09-13 (Asia/Tokyo). Generation/sealing, independent input verification
and exact candidate preparation were explicitly authorized for this turn.
The fixed 64-source cohort has been generated and sealed once. A separate source-qualified process independently reproduced the sealed acceptance order and prepared the exact non-authorizing execution candidate; both operations completed with exit 0.
This is an input-admission result, not a budgeted exploration result or
replication-execution permission. The frozen recipe, search implementation,
source-qualified connector, exclusions and PUBLIC evidence were not changed.

## Fixed realization

- Generator `sha256-counter-mod/v1`; seed 26091301; maximum 10,000 candidates; six inputs in 1..10, target in 100..999.
- Exactly 102 candidates examined; 64 accepted.
  The complete 38-row rejection log retains 27 unsolvable-under-the-fixed-filter
  rejections, 8 excluded source multisets and 3 duplicate source multisets.
  Duplicate full-task and excluded-full-task rejection counts are both zero.
- 64 distinct full-task identities and 64 distinct input multisets. Both
  identity kinds are outside the complete fixed exclusion union: 243 full tasks
  and 179 source multisets across eight groups. This is not a claim that those
  two disjointness checks provide independent evidence.
- 1,024 planned cells: 64 tasks × 4 seeds × 2 scales × 2 budgets. The search seeds
  are 8192 through 8195; scales 0/16; budgets 256/512. There are 512 budget-prefix
  pairs and 256 four-arm blocks, not 256 independent task clusters.
- No hardness/calibration profile, solution witness or new-cohort exploration
  outcome was inspected by the admission layer or persisted in the seal.
  The unchanged exhaustive solvability filter is part of admission; this is
  not an unconditional sample of Countdown tasks.
- No budget-256/512 replication cell was executed. The PUBLIC replays used to
  verify qualification are checks of the existing one-source PUBLIC experiment,
  not new replication samples.

All task definitions below are in generator acceptance order. They were not
reordered or selected using exploration results.

| Slot | Inputs | Target |
| --- | --- | ---: |
| 0 | 3, 4, 4, 6, 7, 9 | 999 |
| 1 | 2, 2, 6, 8, 9, 10 | 518 |
| 2 | 3, 6, 8, 10, 10, 10 | 396 |
| 3 | 1, 2, 4, 7, 8, 10 | 133 |
| 4 | 1, 2, 3, 7, 9, 9 | 304 |
| 5 | 1, 3, 6, 6, 7, 9 | 776 |
| 6 | 3, 4, 6, 6, 7, 10 | 364 |
| 7 | 1, 2, 3, 5, 6, 7 | 375 |
| 8 | 3, 4, 5, 7, 7, 9 | 880 |
| 9 | 2, 3, 6, 6, 9, 9 | 699 |
| 10 | 3, 5, 6, 8, 8, 10 | 269 |
| 11 | 4, 5, 5, 6, 6, 10 | 283 |
| 12 | 3, 4, 4, 7, 8, 8 | 211 |
| 13 | 5, 7, 9, 9, 10, 10 | 176 |
| 14 | 1, 6, 6, 6, 8, 10 | 223 |
| 15 | 2, 4, 5, 6, 10, 10 | 653 |
| 16 | 1, 1, 2, 6, 7, 9 | 350 |
| 17 | 1, 2, 3, 3, 7, 10 | 135 |
| 18 | 3, 5, 5, 6, 7, 8 | 566 |
| 19 | 4, 5, 6, 7, 8, 8 | 644 |
| 20 | 2, 3, 3, 6, 7, 9 | 328 |
| 21 | 1, 6, 6, 8, 8, 10 | 434 |
| 22 | 1, 2, 6, 6, 8, 10 | 105 |
| 23 | 1, 6, 7, 9, 9, 9 | 954 |
| 24 | 1, 6, 7, 8, 9, 10 | 886 |
| 25 | 1, 4, 6, 7, 8, 9 | 580 |
| 26 | 2, 4, 4, 5, 6, 10 | 204 |
| 27 | 3, 4, 7, 9, 10, 10 | 414 |
| 28 | 1, 5, 6, 6, 7, 7 | 185 |
| 29 | 1, 3, 3, 6, 6, 9 | 953 |
| 30 | 1, 2, 5, 7, 7, 10 | 885 |
| 31 | 1, 1, 2, 5, 7, 8 | 650 |
| 32 | 1, 2, 5, 8, 10, 10 | 947 |
| 33 | 6, 7, 8, 8, 8, 9 | 781 |
| 34 | 1, 1, 5, 5, 5, 6 | 274 |
| 35 | 3, 4, 5, 9, 9, 9 | 722 |
| 36 | 2, 3, 3, 5, 5, 8 | 582 |
| 37 | 2, 4, 9, 9, 9, 10 | 668 |
| 38 | 1, 3, 6, 9, 9, 10 | 195 |
| 39 | 1, 2, 2, 3, 5, 6 | 149 |
| 40 | 5, 7, 8, 9, 10, 10 | 766 |
| 41 | 2, 2, 3, 4, 5, 9 | 792 |
| 42 | 4, 5, 5, 6, 8, 8 | 142 |
| 43 | 3, 6, 7, 9, 9, 10 | 578 |
| 44 | 1, 1, 2, 3, 7, 9 | 385 |
| 45 | 2, 3, 4, 7, 9, 9 | 880 |
| 46 | 1, 2, 3, 3, 5, 8 | 338 |
| 47 | 1, 3, 4, 10, 10, 10 | 481 |
| 48 | 3, 3, 3, 7, 9, 9 | 663 |
| 49 | 2, 3, 3, 8, 10, 10 | 250 |
| 50 | 1, 3, 4, 6, 7, 7 | 648 |
| 51 | 2, 3, 3, 6, 6, 9 | 478 |
| 52 | 3, 4, 7, 7, 7, 8 | 230 |
| 53 | 1, 4, 7, 9, 10, 10 | 100 |
| 54 | 1, 3, 6, 8, 9, 10 | 163 |
| 55 | 2, 6, 7, 8, 9, 10 | 511 |
| 56 | 2, 3, 4, 7, 7, 9 | 269 |
| 57 | 1, 1, 3, 4, 7, 9 | 116 |
| 58 | 1, 2, 5, 8, 8, 9 | 570 |
| 59 | 1, 1, 5, 8, 9, 10 | 715 |
| 60 | 4, 4, 8, 8, 9, 9 | 789 |
| 61 | 4, 5, 7, 7, 8, 9 | 977 |
| 62 | 2, 3, 4, 5, 5, 10 | 494 |
| 63 | 3, 3, 5, 5, 9, 10 | 570 |

## Evidence and reproducible boundaries

The [tracked preregistration](preregistrations/countdown_thompson_feedback_budget_v7/preregistration.json),
[STARTED](preregistrations/countdown_thompson_feedback_budget_v7/STARTED.json) and
[SEALED](preregistrations/countdown_thompson_feedback_budget_v7/SEALED.json) are
byte-identical mirrors of the original private fixed local directory
`artifacts/work/feedback-budget-replication-cohort-v7`. The connector only admits
that original location; the Git mirror is for review, not another admission route.

| Original / mirrored file | Bytes | SHA-256 |
| --- | ---: | --- |
| STARTED.json | 77,721 | `fc8896998ead5ac10931335eea307b814c4f2e90e68feb04e954133be86b6387` |
| preregistration.json | 1,451,879 | `9333ee465f240de2f74094d403ceb43cc4ced6d4fc1b4d3e7ce5a5e6239e85d7` |
| SEALED.json | 538 | `4a9ea5abf3597d9e9ad73f4740e2afec3feddfdb350068bf335ac6c82abf301b` |

- Seal digest: `b457706230403b6c2a7ccb1bd6f5ce7ef027bf45fc5fb49995825611ada53479`.
- Cohort digest: `e5f8cd27c1a876c62a2949790d3786f4a6615be7803f3c084b8465ef3688c229`.
- Task-set digest: `0d0a01515a257c8f1085c09276e96cd9fb2c02be6228e46c71ffe28e195a95d5`.
- Schedule digest: `0da39f97a3bd1e6068d33dae9658c7c3656b3a76aa8854e0a4820683b622352b`.
- Generation-manifest digest: `ea3f826eb56a6f5f3594ff98d60c564e6d71238918c886c19134f77dd836f154`.

The exact [connector PUBLIC qualification](qualifications/countdown_feedback_budget_v7_connector_public_20260913.summary.json)
has digest `4511f9bc8ea0c5dacac292ae3d90f6009af8820b5744f46b8b85c1e5a72f57ec`
and file SHA-256 `a12f487cf15c2a58c59cda6f2995127f09148cf01f7f5f3c57bf192b4b156f57`.
Its matching [COMMIT](qualifications/countdown_feedback_budget_v7_connector_public_20260913.commit.json)
has digest `d7bb7ae57e7642c6b1d4aed07a161e48654aac5364b31eb94b51e2ee03c2c14e`.
The independent reconstruction of that PUBLIC publication is a prerequisite,
not replication outcome evidence. Its numerical screen remains false and its
scientific decision remains null.

Historical `new_replication_tasks_generated: 0` and similar fields embedded in
the contract, old identity proof or PUBLIC qualification describe those earlier
operations. They remain unchanged. The new 64-task realization is recorded by
the separate cohort and seal above; those historical fields are neither rewritten
to 64 nor used to deny that this authorized sealing operation occurred.

## Operations and source qualification

Generation/sealing and separate `--prepare-replication` ran at clean checkout
HEAD `c4448c05d6bc498fce562d6fe95012f35a86b56c`. The qualified producing source
remains `91359c9327861210c03ad0bc4e267af240f4ec93`; its protected source,
test and fixed-input bytes were unchanged, and the runtime receipts matched.

Both operations used CPython 3.13.13 / Darwin arm64 / CPU binary64, absolute
repository `PYTHONPATH`, `-P -B`, and their own fresh private empty bytecode-cache
prefixes. Generation/sealing used
`/private/tmp/qmc-v7-cohort-seal-pyc.U8bjPP`;
independent candidate preparation used
`/private/tmp/qmc-v7-cohort-candidate-pyc.loOYIC`.
The seal completed by 03:23:13 UTC (started 03:00:20 UTC), exit 0.
Independent candidate preparation ran from 03:24:22 UTC and completed by
04:07:41 UTC, exit 0. These are observed operation times, not search-performance
benchmarks. Its compact terminal receipt reports zero replication cells executed
and a null scientific decision.

The sealer's unchanged CLI ran once as a child of a minimal stdlib stdout-capture
wrapper. The wrapper verified that the full successful CLI stdout exactly
equaled durable preregistration bytes before printing a compact receipt. This
avoided terminal truncation of the 1.45 MB seal; it did not change the producer,
inputs or one-shot transaction. The fixed generation slot is now occupied and
must not be regenerated, adopted, overwritten or resumed.

The separate prepare operation reanalyzed the exact saved PUBLIC experiment and
loaded the original three-file seal. Its normal loader independently regenerated
the complete fixed 64-task acceptance order and rejection manifest, then
revalidated the detached seal before publishing the non-authorizing candidate.
This is the independent seal verification. No extra standalone
`--verify-seal` invocation or extra independent sample is claimed.

## Exact candidate and local review

The [exact candidate](preregistrations/countdown_thompson_feedback_budget_v7_execution_authorization_candidate.json)
was copied byte-for-byte from its original ignored local candidate file.
The three-file seal and this candidate were committed first, yielding the full
reviewed artifact revision `b57b16ee107eddf07aa94bcf7b20763577aab3a8`.

- Candidate digest: `27c579f553e44ba3d307d74a5d5b9fa26b9e613150488ecab48e280e518d610f`.
- Candidate SHA-256 (155,877 bytes): `4a062a1bd56b254954f0a1cce8510e35d298293500a690b5b0573bbd2b8e39df`.
- Sealed-input manifest digest: `4a969fc46e506d2fc81e0b9a45c841bb8e27f81fb7190ff73abbd72d9fe284b3`.
- Exact output: `artifacts/work/feedback-budget-replication-v7-20260913-a`.
- Candidate preparation did not consume the fixed replication study claim.

The candidate binds the complete sealed-input, contract and schedule digests,
the exact PUBLIC summary/COMMIT, qualified source/runtime and the output path
plus pinned parent component identities. Its status is
`REVIEW_AND_EXPLICIT_CONFIRMATION_REQUIRED`,
`candidate_is_execution_authority: false`,
`requires_explicit_digest_confirmation: true`, and
`locked_128_evaluation_authorized: false`. These bytes were not edited to
grant permission.

The separate fresh-cache local structural/source/Git review passed at that exact
artifact revision, exit 0. Its [saved review receipt](reviews/countdown_feedback_budget_v7_candidate_20260913.json)
has digest `5d47f3eda53adc0c54ce8cff3efe327098f0e4ef0cea89461d675ebff5490866`
and SHA-256 `4609bc6851ef068be580eb6e1e5674a2c63ec704be7f0fb893689f0227800d44`
(6,436 bytes). Its fresh private cache was
`/private/tmp/qmc-v7-cohort-structural-review-pyc.VZBUUo`.

It checked exact candidate and qualifier Git blobs at the full reviewed OID;
current qualified source/runtime equality; original no-follow three-file closure
and unchanged mirrors; both task identities and the eight-group exclusion union;
closed transaction and 1,024-cell/512-pair/256-block reconstruction; exact pure
candidate reconstruction; and the unchanged output-parent identity.
Every saved check is true; no actionable mismatch was found in that scope.

This local structural review is distinct from the source-qualified independent
prepare operation. It reconstructs identity, metadata, transaction, schedule
and candidate bytes without calling the generator, search, full admission or
authorization consumption. It is not an external/fresh-agent review and does
not claim a second full PUBLIC replay or seal regeneration.

## Validation

Before artifact promotion, the complete repository validator passed at
`c4448c05d6bc498fce562d6fe95012f35a86b56c`: all 1,183 tests in 862.798 seconds,
no skips, plus compilation, Ruff, artifact/provenance checks and outside-checkout
self-tests; final status `repository validation: PASS`, exit 0.
Its separate fresh cache was
`/private/tmp/qmc-v7-cohort-validation-pyc.yO49we`.

At the reviewed artifact revision above, focused packaging checks also passed:
byte-for-byte promotion comparisons, the local structural/source/Git review,
repository artifact verification, the six-receipt provenance guard, Ruff and
whitespace checks. `src/`, `scripts/` and `tests/` remained byte-identical to
the qualified implementation revision. The provenance guard covers its six
historical receipts; the separate local candidate review closes the new v7
candidate and connector qualification. Neither is presented as a fresh
replication-outcome analysis.

After writing the note, final document/byte packaging checks also passed:
all 64 input-table rows matched the sealed acceptance order, all seven referenced
file hashes and all six reviewed Git blobs matched, 68 local documentation links resolved,
qualified source/tests were unchanged, and the replication output and study
claim remained absent. The compact result is preserved in
`artifacts/work/feedback-budget-v7-cohort-20260913.document-packaging.captured.log`.

This is not a claim that the entire 1,183-test suite was rerun after documentation
or byte-identical artifact promotion. No qualified source or test was changed.

Operation captures and the local review helper remain ignored under
`artifacts/work/`; the matching review receipt is separately tracked. The logs
preserve full returned output, not all raw experiment data:

- `artifacts/work/feedback-budget-v7-cohort-20260913.validation.captured.log`: 248,032 bytes,
  SHA-256 `57d5af31f56284bab35c950601bed59ed6b055ec4bb3237d744094453b67cffa`.
- `artifacts/work/feedback-budget-v7-cohort-20260913.seal.captured.log`: 315 bytes,
  SHA-256 `91f39a9b9add638c705544bc6e6bd6404cff6b9bf9ab5b67974b2a4859bb9aeb`.
- `artifacts/work/feedback-budget-v7-cohort-20260913.candidate.captured.log`: 316 bytes,
  SHA-256 `1579de66d288ff7687185e5c2d86aaf7e9f00d3536fddcd14d39dc59765893de`.
- `artifacts/work/feedback-budget-v7-cohort-20260913.structural-review.captured.log`: 6,436 bytes,
  SHA-256 `4609bc6851ef068be580eb6e1e5674a2c63ec704be7f0fb893689f0227800d44`.
- `artifacts/work/feedback-budget-v7-cohort-20260913.packaging.captured.log`: 2,489 bytes,
  SHA-256 `7ce0b2a577bd6ad5a37e002d6d9420f9dabc2fd099bc4b22fd02961fd2dea99a`.
- `artifacts/work/feedback-budget-v7-cohort-candidate-structural-review.py`: 9,543 bytes,
  SHA-256 `6be60932c790324ee44d7c0f811830156a808a836eae8ce13e5e2ce32c86a324`.
- `docs/reviews/countdown_feedback_budget_v7_candidate_20260913.json`: 6,436 bytes,
  SHA-256 `4609bc6851ef068be580eb6e1e5674a2c63ec704be7f0fb893689f0227800d44`.

The packaging log retains a non-experimental orchestration error: the first
read-only artifact verifier returned PASS text, but the outer wrapper failed
while storing an absent optional session identifier. The read-only verifier
was then repeated and its exit 0 was recorded. No sealing, candidate preparation,
PUBLIC qualification, admission or experiment was retried for that wrapper error.

## Next authority gate

At the local review snapshot, the exact replication output directory was absent.
The fixed study claim was also absent:
`artifacts/work/feedback-budget-v7-authorization-ledger/replication-548114440db6e0fa49226e28d519fbe1c0f113d5edfe76f282e7ebc29c0bfc3c.json`.
The ledger still contained only the existing PUBLIC claim
`public-cab7c1467ec796b8f0261bb7375f57af37376dc12033d72141e5a2b2458e0800.json`.
No replication-execution permission was received or consumed in this turn,
and no replication search cell was executed.

Only a new explicit confirmation of this exact candidate digest, tied to the
full reviewed commit above, may authorize its one complete 1,024-cell run,
followed by independent analysis and saved-summary verification. That operation
must revalidate the actual original artifacts and current source at consumption.
The structural review is not a shortcut around those gates.

The unchanged [frozen decision rule](strategy/countdown_thompson_feedback_budget_confirmation_v7.md)
remains a bounded fixed-cohort replication screen, not a population-significance
test, proof of causal mechanism, QMC superiority or broad intelligence gain.
Preserve all task-level losses, stop reasons, fixed denominators and negative
screens. There is no authority for retries, an alternate seed/cohort, provider
calls, GPU work, locked-128 evaluation, publication, push, PR or merge.
