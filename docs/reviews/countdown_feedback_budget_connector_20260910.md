# Feedback-budget connector: fresh review and qualification (2026-09-10)

## Fresh reviewer output

Review scope: `20eb9a0b83478de192259a991da4010e7db7107c..5a7f551b09343bc60b6a93943a5a0386b8fa6cdd`.
A separate disposable checkout was disk-blinded using fork-review (only its
project-local AGENTS.md was hidden). No parent conversation was passed. This is
best-effort fresh-eye review, not removal of host-injected system context.

One P2; no P1 found:

**Preserve lifecycle status for errors after publication.** The generic CLI
handler classified non-ExecutionFailure run errors as NOT_RUN even after the
one-shot claim and all 192 cells/COMMIT had been written. It also classified the
inherited PublicationUncertain from summary publication as INVALID_ANALYSIS.

Actual entry-path reproductions used temporary synthetic artifacts and mocked
admission/numerical work, not a real cohort:

| Trigger | Pre-fix observation |
| --- | --- |
| Closed stdout after completed run | 192 cells + COMMIT; CLI NOT_RUN, consumed null |
| Repeat the same run | AUTHORIZATION_ALREADY_SPENT |
| Post-write summary revalidation failure | PublicationUncertain exception mislabeled INVALID_ANALYSIS; summary retained |

There was no demonstrated second-run bypass. Independently analyzing a complete
artifact from an uncertain invocation remains an explicit operator disposition:
the analyzer can re-establish closure/replay, but does not know the original
invocation's return status. Do not automatically advance after a nonzero exit.
No extra competing success/failure marker was recommended; ordinary descriptor
cleanup already uses best-effort close.

The reviewer read the connector diff, frozen design and inherited
admission/replay/reduction/provenance/storage paths. All 28 original connector
tests passed (11.269 s). It did not perform source-qualified PUBLIC execution,
new development generation/sealing/execution, full validation or physical crash
testing, and found no additional demonstrated boundary bypass in the reviewed
scope. The review checkout was thawed immediately after completion.

## Stateful annotation and fix

The P2 is actionable: preserved physical state and accurate reported lifecycle
are separate requirements. Commit
`47cb90880b1e437095d3668ac887165d9bc55c03` separates completed-operation
RESULT_DELIVERY_UNCERTAIN from NOT_RUN, preserves inherited PUBLICATION_UNCERTAIN,
and maps uncertain ledger initialization to CONSUMPTION_UNCERTAIN.
Regressions exercise the actual completed-run/closed-stdout path, uncertain
summary publication, candidate publication and ledger setup. The operator-only
uncertain-artifact disposition boundary is now explicit in the connector docs.

31 focused tests passed (8.772 s) in the main checkout. The first full validation
was deliberately interrupted for this fix and is not a passing validation.
The successful pre-fix PUBLIC preparation candidate remains retained locally,
but it was never run and cannot qualify the corrected connector. No failed or
superseded evidence was rewritten.

The same reviewer performed a separately labeled targeted recheck of
`5a7f551..47cb908`: P2 resolved, no new related P1/P2. All 31 connector tests
passed independently (11.634 s), plus four flush-only stdout-failure checks for
run/analyze/verify/prepare. Its temporary project-local freeze was again thawed
immediately. This is a targeted recheck, not a second stateless full review.

## Source-qualified PUBLIC result

Corrected producing implementation:
`47cb90880b1e437095d3668ac887165d9bc55c03`. Separate prepare, run,
analyze and verify processes used fresh private empty cache prefixes, absolute
PYTHONPATH and CPython 3.13.13 / arm64 CPU binary64 with -P -B. Each command
completed successfully. Analysis and saved-summary verification emitted the
same SHA-256 as the retained canonical summary.

- 192 public traces; 96 exact full-event prefix/completion pairs.
- All 192 search-record byte strings equal the preceding qualified public path.
- Completion counts: 87 pairs with 2 → 4 terminals, 9 with 2 → 5.
- 195 closed files, 25,311,612 bytes. The extra connector metadata does not alter
  the search records or logical work budgets.
- PUBLIC fixture: 12 targets, **one** source multiset. Development cells 0,
  scientific decision null, public screen conjunction false.
- A deliberate duplicate PUBLIC invocation returned AUTHORIZATION_ALREADY_SPENT
  before input regeneration/admission/search. No development claim was consumed.

[Tracked summary](../qualifications/countdown_feedback_budget_v6_connector_20260910.summary.json):
787,113 bytes; deterministic digest
`99053827cc66328a0167acbabf00df93ba0db621409474c3940d4e721d0b6799`;
SHA-256 `d99c2606fdc75b25d4f88806fdf9a6c0e32d909e6aa4a818842caf5cdf85c741`.

[Tracked COMMIT](../qualifications/countdown_feedback_budget_v6_connector_20260910.commit.json):
digest `99195bc0523a2595575231f4ccdda8bec559216a140456e0497cbfabeb19e219`;
SHA-256 `8728edeb0961e013c7e6050d97ecaa2dd25eba0cd931815f89bfc4cde25f9e3b`.

Local raw directory:
`artifacts/work/feedback-budget-connector-v6-20260910-r2`.
Its PUBLIC authorization is the sibling
`feedback-budget-connector-v6-20260910-r2.authorization.json`, digest
`e124e314e8b090dcd7fa1f9d3433df405fe8263a601ea8e1a6737ef07df5d914`.
The consumed claim remains under the fixed local ledger. Tracked summaries and
COMMIT hashes are not substitutes for those raw artifacts when replaying.

## Validation and claim ceiling

`python3 -B scripts/validate.py` passed at the corrected producing commit:
**1,016 tests**, unit-suite duration **742.113 s**, no skips; compilation, Ruff,
artifact checks, the five pre-existing ancestry receipts, frozen-design checks,
outside-checkout CLIs, and final historical v5 seal verification also passed.
No hosted CI, cross-host runtime, power-loss recovery or development result is
claimed. The new receipt-bearing descendant is checked separately by the
ancestry guard and its focused tests.

Ignored logs: `artifacts/work/connector-validation-20260910-r2.log` and
`artifacts/work/connector-qualification-20260910-r2.log`.
The interrupted pre-fix validation log and unused pre-fix candidate remain
separate and do not count as qualification.

This closes the connector's PUBLIC qualification, not the new-cohort screen.
The next distinct gates are one fixed cohort seal, independent seal verification,
an exact reviewed execution candidate, and explicit permission for a single
192-cell development run. No locked-128 permission follows from any of these.
