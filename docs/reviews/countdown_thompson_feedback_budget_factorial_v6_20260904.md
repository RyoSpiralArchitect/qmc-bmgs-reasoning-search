# Feedback × budget v6: design review and validation

Date: 2026-09-04.

## Fresh reviewer output

A fresh subagent reviewed exact commit
`02f879eef35657d4f2834b6471cbaad81ca242fb` in a disposable clone, without parent
conversation and with project-local context hidden. The clone was thawed
immediately on completion. This is best-effort context separation, not a claim
of complete memory erasure.

> No concrete P1/P2 findings. Frozen design and synthetic checker agree on
> contrasts, denominators, task-LOO screen, guard arithmetic, and conditional
> completion bounds. Design checker, synthetic self-test, and all 23 tests passed.

The reviewer did not validate production prefix/replay, current runtime charging
semantics by execution, public qualification, new cohort identity, or outcomes.
Those remain explicit future gates. No edits, new task generation, proposals,
search, replay, raw access, or provider calls were performed by that review.

## Stateful annotation

No correction was needed after the fresh review. Two separate domain passes
also inspected the primary-only budget change and the finite-cohort estimand.
They motivated common secondary caps and the safeguards against a positive
interaction caused only by disappearance of low-budget harm or one-task gains.
The numerical thresholds are conservative engineering choices, not inferred
significance or power guarantees.

The structural guarantees `T512 >= T256 + 1` and `T512 >= 3` follow from the
maximum 140-score D6 trajectory and common nonbinding guards, **conditional on**
validated unchanged semantics, exact same-scale event prefix and valid complete
runs. They guarantee terminal completions, not distinct witnesses, improved
error or exact correctness. Runtime/event-prefix qualification is still pending.

Only the scientific recipe and synthetic arithmetic are fixed. Ordinal task
slots are not materialized task identities or an exact executable cell seal.
No v6 development cohort, calibration witness, proposal, search trace, outcome,
runner authorization, or production publication destination has been created.
Existing source, preregistrations, results, and consumed authorization remain
unchanged; the original `STOP_REPAIR_NO_LOCKED_128_RUN` is not superseded.


## Validation

Validated code/design commit:
`02f879eef35657d4f2834b6471cbaad81ca242fb`.

- `python3 -B scripts/validate.py`: **PASS**, including all **792 tests**
  (`Ran 792 tests in 481.902s`), compilation, Ruff, artifact checks,
  design-byte and synthetic arithmetic checks, CLI self-tests from outside the
  repository, and existing v5 dense-scale manifest verification.
- The new focused suite contains **23 tests**; the fresh reviewer independently
  passed it with `python3 -P -B -m unittest discover -s tests -p
  test_feedback_budget_design.py`.
- Frozen design SHA-256:
  `7b3ebcc7d1b3c3a591b6f3baa574492085bc91c53ee3cccc9fe031d3d70ef01f`.
- Existing v5 manifest remains **VERIFIED**, with seal
  `49f820692aa4f3551ca5634bdc89efe225fe05d1dc8acb8e814f231f3eea222f`.
- `git diff --quiet 661025df4f106ceca4c1de73cfc01516cce21d16 HEAD -- src
  docs/preregistrations docs/results`: exit 0.
- `git diff --check`: **PASS**.

The full repository suite exercises existing public/synthetic fixtures, including
legacy search and replay checks. It does not execute the newly proposed v6
development study or establish its future production prefix/replay gates.
The later review-note/README-only commit does not change the validated code,
tests, or frozen design.

