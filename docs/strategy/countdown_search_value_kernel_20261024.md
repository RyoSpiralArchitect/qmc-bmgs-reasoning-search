# Search-value kernel: implementation boundary, 2026-10-24

Status: **single-cell implementation and fixture tests; not an executable study
candidate, generated cohort, execution authorization, or performance result.**

This implements the first gate of the [merged research design](countdown_search_value_development_20261024.md).
That earlier design remains a dated snapshot. The research question remains:
does current single16 beat the fixed PUCT comparator under the stated score
ceiling, and separately does using learned terminal-return means help? No new
branch allocation, adaptive scheduler, QMC intervention or LM is added.

## What is implemented

`src/qmc_bmgs_next/search_value.py` provides a closed five-method, one-cell API:
single16, selection-mean-off, greedy, beam2 and puct. Every call creates isolated
search state. The proposal is fixed to `greedy_rollout_target_error/v1`; all
seven limits come from an explicit typed budget profile. The future study's
512-score profile is not silently installed as a new default.

The four existing methods call the original engine without changing its inner
trace bytes. Stochastic roots use the existing `feedback-diversity-stream/v1`
branch0 derivation; deterministic methods require root0 and produce no random
material. The outer cell identity binds the declared method, root, derived
stream and complete original search identity. Cohort identity, attempt identity
and inter-cell scheduling belong to a later sealed runner, not this API.

### Selection-mean-off is not learning-off

The new policy changes only selection from `mean + prior + perturbation` to
`0 + prior + perturbation`. It does not compute a rounded full score and subtract
the mean afterward. Dense return scale16, mean/m2/visit updates, visit-dependent
noise, proposals, legal-action order, tie breaking, terminal verification,
readout and atomic seven-axis accounting reuse the original implementation.

It has its own method, configuration, selection-event and summary identities.
The frozen engine's private session is extended locally, without modifying or
monkey-patching historical source files. Before any search event is generated,
the empty writer/source is replaced with the new identity. A writer adapter
stamps the actual control metadata **before** transaction hashing; it never
changes chosen actions, numerical values, charges or reservation ordering.
Consequently trace-storage byte counts need not equal the baseline's metadata
sizes; they are not Python heap usage or evidence of faster/slower search.

The adapter depends on private frozen internals. A future engine change requires
requalification of these integration boundaries. Existing source-byte seals
and the explicit equivalence/tamper fixtures are safeguards, not an API stability
promise.

### Two-stage replay

First, validate the stored hash chain and declared new identity. Authenticate
the new selection metadata, then use a metadata-only view to let the original
stage-one checker regenerate proposals/keyed normal material and validate
terminal-linked backups and charges. That view does **not** validate decisions.

Second, rerun the new policy from empty state with only that authenticated normal
material. Stored choices, selection values and terminal results never guide the
rerun. Require byte-identical inner records and rebuild the entire outer
summary/identity. The old single16 replay rejects the new trace identity.

Only shared task/state/local-visit/action-order/stream coordinates have equal
normal material. Divergent full trajectories are not called common random
numbers. Equal update *rules* do not imply equal realized visits or costs.

## Additional work visibility, without changing the ledger

The outer record retains all seven actual/unspent counters, the original budget
validity, minimum terminal error, missingness, first-exact work and no-hit
censoring at observed stopping work. Missing terminals keep error/first-hit
null, not fabricated failures with zero error. Non-primary guard binding remains
invalid and is not silently filtered.

A passive audit reconstructs the fixed greedy proposal's internal completion
action evaluations from each materialized proposal row, and checks its internal
transition total against the existing row. Cache hits are not charged again;
cache misses in separate cells are counted separately. The root-action count
duplicates the existing proposal-action ledger axis. The internal completion
counts are additional diagnostics, not new budget charges or a total-compute
equivalence claim. The reconstruction itself costs CPU but is audit overhead,
not search work. This is **not live instrumentation** or a wall-clock speed
measurement. A fixture observes calls in the original heuristic to check the
reconstruction's counting convention.

## Qualification and next unmet gates

The 23 focused tests pass, including all-five-method replay, four-control
byte equality, zero-mean score equality, a constructed nonzero-mean choice
difference, unchanged backups and visit-dependent noise, material-coordinate
agreement, missingness/guard failures, tamper rejection and fresh-process replay
from outside the checkout. These are synthetic implementation checks, not a new
development experiment or independent reviewer approval. Full repository
qualification is recorded separately; focused PASS alone is not full PASS.

Still required before a study can run:

1. Version and review the study runner, precise one-primary reduction and
   complete-matrix rejection rules, without redefining the merged design.
2. Authenticate all historical/fixture/reserved source and seed exclusions;
   seal implementation/runtime, method order, budgets, source manifest,
   candidate and one-attempt identity. Generate no new cohort yet.
3. Qualify and review that exact executable candidate, then obtain separate
   authority for its one run and full separate-process replay.

The intended matrix remains128 sources × (4 single16 + 4 mean-off + 1 greedy +
1 beam2 + 1 PUCT) =1,408 cells. The sole primary remains **single16 minus PUCT**;
the mean-off contrast is diagnostic. No winner/default, architecture expansion,
new ratio, C5/locked evaluation or provider execution follows from these tests.
