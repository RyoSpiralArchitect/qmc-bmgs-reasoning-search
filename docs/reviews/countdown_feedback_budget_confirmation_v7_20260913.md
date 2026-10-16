# Countdown feedback × budget v7: design review (2026-09-13)

Scope: `aabf9ef55829ca2723d3c3504ff71c0a49059ad2..bc092279353dacffdbbdf74ce5639e3f353d45fd`.
The scientific recipe is [v7 source-disjoint replication](../strategy/countdown_thompson_feedback_budget_confirmation_v7.md),
SHA-256 `0a11f4da63063cc48a128e2f9ead676e92a588b31cc8fcbe08e466a46374d0eb`.

A fresh read-only reviewer used a separate complete clone without parent
conversation. Only its project-local AGENTS.md was hidden; user-level memories
were not hidden and host-injected context cannot literally be removed. The
hidden file was restored immediately after review, and the clone was clean.

## Fresh reviewer output

No actionable P1/P2 findings.

Reviewed exact HEAD bc092279353dacffdbbdf74ce5639e3f353d45fd against aabf9ef55829ca2723d3c3504ff71c0a49059ad2; the delta contains only the four specified files.

Bounded checks confirmed:

- Exact thresholds are correct: effect numerators ≥11/256 and rescue breadth ≥11/64. Four seeds remain within each task cluster.
- All 16 factorial patterns are accounted for; seven prefix-inconsistent patterns are rejected.
- The screen separately handles interaction, high-budget uplift, low-budget harm, concentrated rescues and high-budget losses.
- LOO calculations remove all four seeds and use 252 blocks. Their positivity is correctly identified as implied by the effect floor, not independent evidence.
- Paired rescues remain distinct from any-seed solved-task counts.
- Historical v6 bytes and unchanged-method boundaries are preserved. New-domain qualification, exclusions, sealing and explicit one-shot permission remain future gates.
- The checker produces synthetic/design statuses only, with no experimental-input or execution interface.

Validation: all 27 focused synthetic tests passed; the default checker and self-test both passed. No material checker/test inconsistency found.

Limits: this was a read-only design/arithmetic review. I did not run full validation, generation, solvers, replay, providers or inspect private artifacts. It establishes no study outcome, pipeline qualification or execution authority. The parent has been notified to restore the hidden files.

## Stateful operator annotation

No material design/checker correction was required by this review. For exact
units, the two effect **numerators** must each be at least 11, with denominator
256; the task-breadth **count** must be at least 11, with denominator 64. The
rational recipe floors remain `1/24` and `1/6`, not the displayed rounded
percentages or an absolute two-cell/two-task rule.

The parent separately checked all 52 relative links in the README/design,
unchanged historical source and evidence bytes, and all six PUBLIC receipt
ancestries at the reviewed descendant. The checker reads byte anchors only; it
does not itself establish those source/provenance properties or a complete new
fixture/exclusion closure.

Both mathematical redundancies remain explicit: the effect floors imply
strictly positive leave-one-task-out values under valid bounded task contrasts,
and the task-breadth requirement plus no lost high-budget successes implies the
high-budget net-count floor. These are transparent engineering gates, not
independent significance tests.

## Parent validation and remaining gate

The parent ran the unchanged full repository validator on the original checkout
at `bc092279353dacffdbbdf74ce5639e3f353d45fd`, with a fresh private bytecode-cache
namespace:

```sh
PYTHONPYCACHEPREFIX=<fresh-private-cache> python3 -B scripts/validate.py
```

Exit 0: **1,043 tests passed, no skips**, unit-suite time 530.044 s. Compilation,
Ruff, historic artifact checks, all six receipt ancestries, the frozen v6 design
checker, outside-checkout CLIs and historical v5 seal verification also passed;
the final line was `repository validation: PASS`. The new v7 checker/default
CLI and its 27 focused tests passed independently and again within the full
test discovery. This validation is parent work, not a claim by the fresh reviewer.

The complete local command/output record is retained under ignored
`artifacts/work/feedback-budget-v7-design-validation-20260913.log`. No new v7
cohort, experimental search, provider call, locked-128 evaluation, external
publication or merge was performed. Existing PUBLIC test fixtures are software
validation, not additional experimental observations.

The next missing gate is a separately domain-bound outcome-blind contract and
full-shaped qualification plan, closing all historical, v6-development and new
PUBLIC fixture exclusions before any cohort-generation permission. This review
does not authorize generation, execution, publication or reuse of the consumed
v6 claim.
