# Countdown Thompson diagnostic: frozen post-hoc mechanism audit

Date frozen: 2026-08-25

## Status and question

This is an explicitly exploratory, post-outcome trace audit. It is not a
preregistration and it cannot reopen the diagnostic, authorize a retry, or
authorize the locked-128 evaluation.

The audit asks two narrower questions of the already committed 240-cell
diagnostic:

1. After the first terminal feedback, where do v2 and v3 actually diverge,
   and is the next completed terminal error better, equal, or worse under v3?
2. When the v4 greedy anchor fails, does any completed post-anchor trajectory
   improve its terminal error or rescue the cell exactly?

It also measures how many posterior updates could affect later begun and
completed trajectories. This distinguishes limited feedback exposure from an
unsupported claim that dense feedback was causally harmful.

## Frozen inputs

- committed artifact:
  `/Users/ryohiga/SpiralReality/countdown_thompson_diagnostic_v1.commit.json`
- artifact commit digest:
  `ffd5f875f3d560382dd21fddec95b47ad0d4442913d8a5fb7faf104d12f209b9`
- run-manifest digest:
  `465f2ec53551eefb2892171aa7ac0815bf3b139d2b0f2f549ba9685c34d9def6`
- independently published summary:
  `/Users/ryohiga/Documents/Codex/2026-07-17/3-qmc-thompson-sampling-qmc-token/countdown_thompson_diagnostic_v1.summary.json`
- summary deterministic digest:
  `46ebdb1eabcaa91220ed8bb10370f70aad0c61d37a2ef6150d09ca29beac0db5`
- execution-authorization digest:
  `88f6639ccc9e949a7633a5cd243099ae28e85c2cceb3bcd7eab7303387474c28`
- reviewed authorization revision:
  `28cb810dd730cb27a28b8f1d89365dafa12ab980`
- authorized runner revision embedded in that authorization:
  `a0111868aae556d6fd7cdbb8c7670c1b11e68f34`

The first draft supplied the nonexistent, mistyped revision
`a0111868d6549597b19cd0e2ac81952974ea9c52` as the reviewed authorization
revision. It was neither the reviewed revision nor the runner revision embedded
in the authorization. The operator observed the first real audit invocation
fail closed in source preflight before any post-hoc reduction was returned.
That invocation history is operator evidence; it is not proven by the canonical
receipt itself.

The audit must first rerun the existing v2r3 analyzer, require exact summary
object equality, and independently reverify the committed collective. It must
fail closed if any digest, source authority, replay, method coverage, task/seed
pairing, or trace shape differs.

## Frozen population and pairing

Only heuristic-proposal cells from these methods are included:

- `thompson_dimnorm_iid_v2`
- `thompson_dense_iid_v3`
- `thompson_greedy_anchor_dense_iid_v4`

Each method must contain exactly the preregistered 12 tasks by four exploration
seeds. v2 and v3 are paired exactly by `(task_fingerprint, exploration_seed)`.
No cell, trajectory, or event may be dropped because of its outcome.

## Frozen event definitions

A selection identity is the exact ordered tuple of:

`(trajectory_index, depth, state, action_index, child_state)`

Only `selection_committed` events contribute selection identities. Method name,
sampled value, posterior digest, and floating-point selection values are not
part of action identity.

For every selection or terminal event, its prior-feedback count is the number
of earlier `trajectory_backed_up` events in the same trace. Therefore:

- a feedback-informed begun trajectory has at least one selection after at
  least one earlier backup;
- a feedback-informed completed trajectory has a terminal whose trajectory had
  begun after at least one earlier backup;
- a post-first terminal is a feedback-informed completed terminal, not merely
  an event with a numerically positive trajectory index.

Terminal absolute error is exactly
`abs(verification.final_value - verification.target)`. Success must equal an
absolute error of zero.

## Frozen v2-v3 paired reductions

For every pair, report:

1. whether trajectory 0 has an identical ordered selection-identity sequence;
2. the first differing feedback-informed selection, with trajectory index and
   depth; a missing selection on either side is a difference;
3. whether any feedback-informed selection differs;
4. the minimum post-first terminal absolute error for each method;
5. v3 versus v2 classification: `improved`, `equal`, `worse`, or
   `not_comparable` when either side has no post-first terminal;
6. post-first exact outcome: both, v3 only, v2 only, or neither.

Aggregate counts retain all 48 ordered pair rows. “v3 only” is descriptive
evidence of a dense-feedback rescue in this artifact; “v2 only” is descriptive
evidence of a regression. Neither is a superiority test.

## Frozen v4 anchor reductions

The anchor is trajectory 0 and must have `selection_phase=greedy_anchor` on
every selection. Every later begun trajectory must have
`selection_phase=posterior_perturbation`.

For every cell, compare anchor terminal absolute error with the minimum
completed post-anchor terminal absolute error and classify it as `improved`,
`equal`, `worse`, or `no_post_anchor_terminal`. Report the classification for
all cells and separately for anchor-failure cells.

An exact rescue requires `anchor_error > 0` and a completed post-anchor error
of zero. A cell already solved by the anchor is never a rescue, even if a later
trajectory also succeeds. Retain all 48 ordered cell rows.

## Frozen feedback-exposure reductions

For v2, v3, and v4, report exact distributions of:

- backup events per cell;
- feedback-informed begun trajectories per cell;
- feedback-informed completed trajectories per cell;
- prior-feedback counts at the start of each feedback-informed trajectory;
- backup update entries per cell.

These reductions describe opportunity, not sufficiency. Even universal low
exposure cannot establish that additional updates would have succeeded.

## Interpretation and claim boundary

The receipt may conclude only one of the following descriptive states:

- `NO_OBSERVED_DENSE_DIRECTION`: v2 and v3 never diverge after feedback;
- `MIXED_OR_NULL_DENSE_DIRECTION`: they diverge, but v3 has no strict majority
  of improved comparable pairs;
- `MORE_V3_IMPROVEMENTS_IN_ARTIFACT`: v3 has a strict majority of improved
  comparable pairs.

This label is not causal and is not a method-ranking claim. Low update exposure
and observed error direction may both be true; the audit must not choose one as
the cause of exact-success failure.

The result remains an engineering observation from the fixed diagnostic. An
integrity `PASS` means only that provenance, replay, coverage, and reductions
closed. It is not positive scientific evidence, retry authority, or
locked-128 execution authority. The handoff decision remains
`STOP_REPAIR_NO_LOCKED_128_RUN` unless a separate future authorization changes
it.

## Post-review v2 receipt amendment

Amendment date: 2026-08-26

The first frozen performance reductions above are unchanged. A fresh read-only
review identified three receipt-presentation gaps, so schema v2 additionally:

- resolves artifact, bundle, authorization, repository, and summary paths to
  canonical existing absolute paths before hashing provenance;
- records V4 anchor versus heuristic-greedy selection and terminal identity as
  a post-review support check;
- records how many V3 backup update entries changed posterior mean.

The latter two values live under `supplemental_validation` with scope
`POST_REVIEW_SUPPORT_CHECKS_NOT_FROZEN_PERFORMANCE_REDUCTIONS`. They were added
after the v1 result was visible and cannot influence the frozen v2/v3 direction
label, V4 rescue classification, or handoff decision.

The analyzer deliberately regenerates each historical search from empty state
and requires byte-identical replay. Therefore “read-only” and “no new run” mean
no new outcome-bearing cohort, retry, provider call, or locked evaluation; they
do not mean that deterministic search replay is skipped.
