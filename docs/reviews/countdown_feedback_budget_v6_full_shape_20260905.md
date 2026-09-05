# PR27 full public shape: fresh review and validation

Date: 2026-09-05.

## Fresh reviewer output

The reviewer examined the complete PR against PR26 merge
`6a7b2a411444c610c5947bf9f3c85af38fd3787e`, at initial full-shape commit
`4ef632dcb5f17f66b66590e61168ea15e4aa5a76`.

> One P2 finding: the 32-trace qualification verifier checked directory closure
> only before analysis. Adding a late `failure.json/` entry during analysis
> could still return PASS. Revalidate the exact entry set before returning.
> No additional findings in the 192-cell runner/publication path.

The initial review passed all 106 targeted tests, regenerated both fixture
manifests, and reproduced the frozen 32-trace analysis baseline.

After correction at `112d41b4d729c826377c0619f7953db35c75a063`:

> The P2 is fixed. The final exact-entry check follows source/runtime
> revalidation, and the regression rejects the entry added during analysis.
> All 20 focused evidence tests passed. No remaining P1/P2 findings in the
> correction.

Each review used the same isolated disposable clone with no parent conversation
and project-local context hidden. The files were thawed immediately after each
completed review. This is best-effort context separation, not complete memory
erasure.

## Stateful annotation

The finding concerned final file-set closure, not a requirement for the older
32-trace publisher to provide full transaction semantics. The correction was
appropriate and is covered by a concrete late-directory-addition regression.

The operator repeated the official source-only 32-trace qualification and
verification, then ran, saved, independently analyzed, and verified the 192-cell
fixture using the corrected source. The 192 cell hashes and integrity receipt
matched the initial full-shape run exactly. Source/publication/summary identities
were refreshed and the earlier local evidence retained. No search behavior or
scientific recipe was changed.

The latest [observation](../observations/countdown_feedback_budget_v6_full_shape_20260905.md)
contains the corrected-source evidence. The original 32-trace receipt remains
a historical, hash-pinned baseline; the corrected verifier has its own fresh
receipt. Source attestation deliberately does not accept changed executable
bytes as an alias to an old producing revision.

This validates the complete public fixture and its storage/analysis path.
Production domains, cohort generation/sealing, production analysis and
publication qualification, and execution authorization remain subsequent work.

## Final validation

At corrected code commit `112d41b4d729c826377c0619f7953db35c75a063`:

- `python3 -B scripts/validate.py`: **PASS**, including **876 tests**
  (`Ran 876 tests in 425.117s`), compilation, Ruff, artifact verification,
  frozen-design checking, outside-checkout CLI self-tests, and the existing
  v5 seal verification.
- This PR adds **84 tests**: 25 qualification trace/configuration tests,
  20 qualification evidence tests, 18 full-shape core tests, and
  21 durable-publication tests.
- Corrected-source 32-trace `--qualify` and independent `--verify`: **PASS**.
- 192-cell `--run`: **PUBLIC_FULL_SHAPE_COMMITTED**.
- Independent `--analyze`, then separate saved-summary `--verify`:
  **PUBLIC_FULL_SHAPE_INDEPENDENT_ANALYSIS_PASS**, summary digest
  `620871116058d135567706245d04264ef6d6035e82ad53049c967cada0189026`.
- Exactly 192 stored cells and 96 complete budget-prefix checks; 195 committed
  input files. All 192 cell hashes match the earlier public run.
- Tracked commit, summary and refreshed qualification files match their local
  source bytes exactly.
- `git diff --check`: **PASS**. Existing package source, preregistrations,
  results and frozen v6 scientific design are unchanged from the PR base.

Later changes only publish documentation and evidence. The full validation
suite exercises existing public/synthetic fixtures as well as the new tests;
no v6 development cohort or provider call was executed.
