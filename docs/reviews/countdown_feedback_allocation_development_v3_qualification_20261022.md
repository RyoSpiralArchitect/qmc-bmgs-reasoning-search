# Allocation v3 qualification completion

Full repository validation passed at candidate `4795f91686de2715696e689d52661976d8d57ad2`, with frozen
v3 plan digest `18f4dd53afd152ef88618e92091e822d56111b6ad04bb67c0aed5755b90da9ed`. The run began at 2026-10-21T23:47:45.418769+00:00 and
completed at 2026-10-22T00:05:53.515664+00:00. It reported **1,752 tests in
925.935 seconds, zero failures, errors or skips**, exit 0, then completed
artifact verification and every required self-test with
`repository validation: PASS`. Ruff and compilation also passed.

The [qualification receipt](../qualifications/countdown_feedback_allocation_development_20261022.validation.json)
is an exact byte copy of the retained process receipt. It binds the source
commit, v3 plan, raw logs, capture helper and complete before/after inventory.
The original failed full qualification and unchanged-main reproduction remain
unchanged. The separate v2 capture stopped on a macOS temporary-path assertion
before starting its validation child; that failure and v2 plan also remain.
The v3 launcher uses the resolved private temporary path, and the discovery
wrapper explicitly restores the former unittest import surface under `-P`.
The first v3 suite lost its terminal transport after 505 successful test markers;
its process disappeared without a completion receipt. That incomplete attempt
and a post-interruption preservation check are retained. The successful capture
ran the same immutable candidate in one durable local process; it was not a
resume or a study retry.

Complete collection is reconciled: 1,718 original tests + 26 allocation tests
and eight portability tests = 1,752. The old 1,565 execution count omitted 179
methods after failed class setups. All 328 tests in the eight path-bound
historical modules now ran on their authenticated read-only canonical mirror;
the other 1,424 ran in the isolated candidate checkout. Their unchanged source
and test bytes were checked against both this candidate and the immutable
PR30 merge tree. No old test, receipt, path assertion or admission was patched.

All captured preservation invariants match before and after; postflight errors
are empty. These cover 486 candidate tracked files, all 470 merged-parent paths
at the frozen candidate, 469 byte-identical merged files plus the explicitly
declared validator entry-point change, 5,329 protected historical files,
5,808 inventoried original files, 20 original directory memberships and six
absent historical study/production slots. Earlier failed capture files remain
unchanged. The original checkout was never edited, moved or replaced. Its
historical validator remains byte-identical to the merge tree. All 58 v3 source
references match the committed candidate.

This subsequent commit adds only this completion note, its receipt and the
retained interruption receipt. The complete suite was run on the candidate above, not again on the records-only
descendant. Local qualification and operator review do not assert hosted CI
or independent reviewer approval. The mirror option requires that existing
canonical evidence; it does not make historical admission relocatable.

The scientific design is unchanged across the unexecuted freezes: 64 fresh
source clusters, eight shared seeds, dense scale 16, arms 512/0, 256/256 and
384/128, 1,536 cells, 2,560 branch searches, 512 source-seed blocks and 2,048
branch-prefix pairs. Per cell, legal scores total 512 and each other work axis
totals 100,000. Search-pass ceilings are 786,432 legal scores and 153,600,000
on each other axis; separate replay repeats those ceilings. Actual work,
paired gains/losses, missingness and source-level heterogeneity remain required.
No new cohort has been generated or allocation study run; no default is chosen.

## Pending exact execution approval

The [original allocation proposal](../strategy/countdown_feedback_diversity_allocation_proposal_20261022.md)
requires: "Review and validate the new implementation, freeze its exact plan
digest and commit, then request new explicit human authorization for one
run/analysis." The implementation and qualification are complete. The remaining
decision is **approve candidate `4795f91686de2715696e689d52661976d8d57ad2` and v3 plan `18f4dd53afd152ef88618e92091e822d56111b6ad04bb67c0aed5755b90da9ed` for one
bounded run and one separate-process complete analysis**. This approval is
pending; it was neither denied nor inferred from direction approval.

The runner accepts a records-only descendant that preserves every candidate
byte and binds this qualification receipt. Do not create the human approval
receipt without the actual decision. New cohort generation and study execution
remain closed; the fixed output and approval slots remain absent. PR #31 is
not authorized for merge. PR #30 alone was merged at
`2fc168157f9d4adc039f6a330d65e0361b31bb15`.
