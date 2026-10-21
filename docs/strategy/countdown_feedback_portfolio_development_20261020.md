# Budget matched feedback portfolios for the next Countdown development comparison

This new development lane addresses the E4 PUBLIC diagnosis: feedback reached
selection, but 32 high-budget gains came with 24 losses, and one seed supplied
the entire net gain of eight. The old false result, its thresholds, raw data,
original C5 study and locked evaluation remain unchanged. PR #28 was already
merged at `db20d23235c277514460b330118a003688f2ba77` on 2026-10-16; its tree
matches the reviewed `786823b` head. No additional review thread was present
when inspected on 2026-10-20; hosted checks and approval were not reported.

The successor adds an opt-in inference API in `qmc_bmgs_next.feedback_search`.
It composes the frozen Track A search through public interfaces, without
altering historical source, monkeypatching its reward function, or redirecting
old execution commands. This first intervention separates *search channels*;
it does not yet add two learned value heads inside one posterior.

## Changes derived from the failure analysis

The old scale-16 reward assigns error one a value of 16/17. Scale one assigns
it 1/2, and every nonexact terminal receives at most 1/2 because Countdown
errors are positive integers. Exact reward remains one. This changes the
strength of approximate-solution feedback while preserving the same proposal,
action enumeration, prior bonus, visit-count noise, reverse backup and IID
perturbation rule. It is a hypothesis about steering, not a proven correction.

The protected portfolio maintains one exact-only search graph and one scale-one
search graph. Each receives half of **every** work-axis cap; any indivisible
remainder goes to the second channel. The graphs, posteriors and proposal caches
are isolated. Both execute even if the first succeeds. Unspent work is not
transferred, cache misses are charged in both branches, and the same exploration
seed is paired across branches rather than described as an independent sample.

This protects the exact-only trajectory at its *allocated half budget*, not the
full-budget baseline's success set. The full-budget comparator remains necessary:
diverting half the work can lose late exact successes or valuable dense search.
Increasing total work to restore those losses would be a different experiment.

The inference readout retains the first verified exact answer across channels;
otherwise it returns the verified terminal with minimum absolute error, with
stable channel/observation tie-breaking. It never reads an exhaustive-solver
witness or spends an uncharged verifier call. With no verified terminal, answer
and minimum error are null, not zero. All four arms use this common readout;
exact-success and minimum-observed-error comparisons therefore do not depend
on which legacy nonexact answer the old engine preferred to display.

## Fixed comparison

| Arm | Feedback and allocation | Total primary cap |
| --- | --- | --- |
| exact | Scale 0, one exact-only channel | B |
| dense16 | Scale 16, unchanged strong-feedback control | B |
| calibrated1 | Scale 1, weaker approximate reward | B |
| protected1 | Scale 0 at B/2 and scale 1 at B/2, isolated graphs | B |

All arms use `greedy_rollout_target_error/v1`, IID dimension-normalized Thompson
selection and legal-action-score budgets B = 256 and 512. Secondary per-axis
caps are 100,000 before channel allocation; binding any secondary guard makes
the run incomplete for comparison. Actual work, including unused remainders,
is reported on every axis. This is neither an LM evaluation nor a QMC versus
IID comparison.

The planned matrix has **eight new source multisets × eight seeds × two budgets
× four arms = 512 cells**, with 640 underlying branch searches and 256
same-arm budget-prefix pairs. Each arm/budget has 64 task-seed blocks, but only
eight source clusters. Maximum total legal-action scores are 196,608.

Generation uses the existing SHA-256 counter generator, seed 26102001, six
inputs in 1–10 and targets in 100–999. Accept the first eight source-unique,
exhaustively solvable tasks outside the authenticated exclusion registry,
within 1,000 attempts. No hardness or search-outcome selection is allowed.
Retain acceptance/rejection identities, never calibration profiles or solution
witnesses. The exclusions include the prior eight-group registry, the original
64-source C5 cohort, the already inspected PUBLIC source, and regression-fixture
sources. Reading those identities grants no right to evaluate those studies.

Exploration seeds are **16384–16391**, selected before new cohort generation or
outcomes. They differ from the inspected E4 seeds. They are development seeds,
not a permanently untouched evaluation set once this matrix is opened.

## Analysis before choosing a next design

Report all arms and every planned cell. Primary paired contrasts at each budget
are calibrated1 minus dense16, protected1 minus calibrated1, protected1 minus
exact, and dense16 minus exact. For each, retain gains, losses and net exact
success, not just rates or an overall rank. Report paired minimum-error
win/tie/loss and explicit missing pairs; do not treat missing terminals as
perfect answers or silently remove them.

Break each contrast down by source and seed, and report leave-one-source-out
and leave-one-seed-out values. Separately replay every branch and require exact
whole-record reproduction, exact budget-prefix decisions/work, and the complete
512-cell matrix before reducing outcomes. The allocated baseline branch must
match a standalone call with the same assigned caps and seed. The test suite
checks this structural property; it does not promise superiority at total B.

No automatic winner, pass threshold, population confidence claim or C5 decision
is defined. Eight sources are a bounded development check, not a replication of
the original study. If there is no consistent gain, preserve that result and
revise the hypothesis under a new plan rather than reopening this attempt.

## Execution and review boundary

The machine-readable plan binds this policy, source bytes, the exclusion
registry, runtime, fixed generation recipe and every factor. Building the plan
does not generate tasks or run search. It is review evidence, not authority.
The current request authorizes implementation and preparation; present the
exact completed plan digest and tested commit for explicit approval before
starting this new matrix. A literal command-line digest is necessary but is
not proof that the human approval occurred.

The new runner owns only `artifacts/work/feedback-portfolio-development-20261020-a`.
Exclusive directory creation is its one-attempt fence. It writes STARTED,
cohort, ordered cells, then COMMIT. A separate analysis invocation regenerates
the cohort and replays all branch traces before writing the summary. Neither
missing COMMIT nor a changed digest allows restart, overwrite, resume or a
replacement cohort. Failures retain partial files and require a new decision.

Original E4 PUBLIC, C5, locked-128, provider calls and the original authorization
ledger are not called by this lane. Its source/runtime/clean-HEAD checks and
exclusive regular-file writes are local research integrity controls, not an
adversarial-host security guarantee. Raw traces stay ignored; reviewed plans,
summaries, hashes and validation receipts belong in Git.
