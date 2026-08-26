# Countdown Thompson diagnostic: frozen selection-margin audit

Date frozen: 2026-08-26

## Status and question

This is an explicitly exploratory, post-outcome sensitivity audit of the
already committed 240-cell diagnostic. It is not a preregistration. The
definitions below are frozen before computing aggregate selection-margin or
scale-boundary results.

The audit asks one narrow mechanism question:

> When terminal feedback was already available, how large was the recorded
> winner/runner-up score margin, how much of the decision surface came from the
> current posterior means, and—on v2/v3 common-prefix decisions—how far was the
> observed dense-feedback score displacement from an action boundary?

This audit does not execute a new outcome-bearing cohort, retry a cell, call a
provider, continue an incomplete trajectory, or open locked-128. The existing
analyzer still regenerates every historical search from empty state and
requires byte-identical replay; that deterministic verification replay is part
of the audit.

## Frozen inputs and authority

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
- execution authorization digest:
  `88f6639ccc9e949a7633a5cd243099ae28e85c2cceb3bcd7eab7303387474c28`
- reviewed authorization revision:
  `28cb810dd730cb27a28b8f1d89365dafa12ab980`
- canonical post-hoc mechanism receipt:
  `docs/results/countdown_thompson_diagnostic_v1/posthoc_mechanism_v3.json`
- canonical post-hoc deterministic digest:
  `02a0ecd90f6e695d22f06d77ee74a41210045811913c9e5b2bd793110089c262`
- canonical post-hoc raw SHA-256:
  `07c747aaaef5709c3b215b7c7645d34e8968712c5b273fe29b016510d9ac596c`
- merged base revision:
  `d6391724cae9be59045d7309b7b05f06380b59b1`

The implementation must rerun the existing v2r3 analyzer, require exact
published-summary equality, reverify the committed collective, and require the
published post-hoc v3 frozen reductions and supplemental validation to match a
fresh recomputation. It must fail closed on any digest, source, replay, method
coverage, task/seed pairing, event-shape, or post-hoc cross-check drift.

## Frozen population

The individual selection audit includes only heuristic-proposal cells from:

- `thompson_dimnorm_iid_v2`;
- `thompson_dense_iid_v3`;
- `thompson_greedy_anchor_dense_iid_v4`.

Each method must contain the exact 12-task by four-seed matrix. A selection is
feedback-informed when at least one earlier `trajectory_backed_up` event exists
in the same trace. For v4, every included selection must also have
`selection_phase=posterior_perturbation`; the greedy anchor itself is excluded.
No selection may be filtered by terminal outcome, score margin, posterior
value, or whether its action later diverged.

The paired dense audit matches v2 and v3 exactly by
`(task_fingerprint, exploration_seed)` and uses only feedback-informed
common-prefix decision surfaces defined below.

## Frozen trace reconstruction

For each target cell, process events in their committed order. A node posterior
starts with one exact object per action:

`{"m2": 0.0, "mean": 0.0, "visits": 0}`.

Before every included selection:

1. recover the node by its exact integer `state` tuple;
2. require `scored_action_indices == range(action_count)`;
3. require finite plain-binary64 `selection_values` and exact
   `selected_value` equality;
4. require the recorded action to equal the repository's stable argmax rule,
   maximizing `(score, -action_index)`;
5. require the reconstructed posterior vector digest to equal
   `posterior_before_digest`;
6. retain the exact `mean`, `visits`, and `m2` vector visible at that decision.

At every backup, require each update's `before` object to equal the current
state/action posterior, then apply the exact recorded `after` object. Backup
trajectory indices must remain contiguous and terminal/backup order must close
as in the preceding post-hoc audit.

These checks reconstruct recorded state only. They do not synthesize an
unobserved update or continuation.

## Frozen observed-margin reduction

For each included selection, the winner is its recorded action. The runner-up
is the stable argmax among every other scored action. The observed margin is:

`selection_values[winner] - selection_values[runner_up]`.

The receipt retains an ordered row with method, task fingerprint, seed,
trajectory, depth, state, action count, winner, runner-up, observed margin,
posterior mean vector, nonzero-mean action count, winner mean, and runner-up
mean. It also retains deterministic five-number summaries using sorted index
`floor((n - 1) * p)` for `p in {0, 1/4, 1/2, 3/4, 1}`.

All arithmetic used to locate a scale boundary converts each stored float with
`Fraction.from_float`; therefore the boundary is exact for the committed
binary64 inputs. Human-readable float approximations are supplemental only.

## Frozen current-posterior scale path

For one selection with recorded score `s_a` and reconstructed posterior mean
`mu_a`, define the exact local sensitivity line:

`L_a(lambda) = (F(s_a) - F(mu_a)) + lambda * F(mu_a)`, for `lambda >= 0`,

where `F` is `Fraction.from_float`. Thus `lambda=1` exactly reproduces the
recorded score vector, while `lambda=0` removes only the current posterior-mean
term and holds the recorded prior/noise remainder fixed.

The baseline action is the stable argmax at `lambda=0`. The first positive
decision boundary is the smallest nonnegative `lambda` where an action with a
larger posterior-mean slope ties the baseline action. Report:

- baseline and observed actions;
- whether the recorded mean term changed the action by `lambda=1`;
- the exact boundary fraction, boundary challenger, and whether the stable
  tie-break changes the action at the boundary or only strictly above it;
- boundary relation: `before_observed`, `at_observed_closed`,
  `at_observed_open`, `after_observed`, or `none`;
- scale bin: `zero`, `(0,1]`, `(1,2]`, `(2,4]`, `(4,8]`, `(8,16]`, `>16`,
  or `none`.

This path is a one-node score sensitivity diagnostic. It is not a rerun and
does not assert that an action reached at another scale is better.

## Frozen v2/v3 common-prefix pairing

Within each exact task/seed pair, selection events are compared in event order.
Trajectory 0 must have exact action identity as already established by the
post-hoc receipt. Starting with the first feedback-informed decision, a surface
is pairable only when v2 and v3 have identical:

- trajectory index, depth, state, action count, and scored action indices;
- action-order digest and proposal-behavior digest;
- perturbation point digest;
- noise dimension normalizer and selection-rule identifier;
- reconstructed posterior visit vector.

The selection where the recorded actions first differ is still included when
all pre-decision fields above match. Pairing stops immediately after that
decision. A missing selection or pre-decision mismatch is retained as an
unpairable stop reason rather than silently dropped.

For each pairable surface, retain both score and posterior-mean vectors. Define
the observed dense displacement and its posterior component as:

`d_a = F(score_v3_a) - F(score_v2_a)`

`delta_mu_a = F(mean_v3_a) - F(mean_v2_a)`.

The paired score path is:

`P_a(lambda) = F(score_v2_a) + lambda * d_a`, for `lambda >= 0`.

It exactly reproduces v2 at `lambda=0` and v3 at `lambda=1`. Apply the same
first-boundary and tie-break definitions using the v2 action as baseline.
Report the full float score-delta and posterior-mean-delta vectors, their
digests, nonzero counts, the maximum absolute rounding residual between them,
the boundary, whether v3 changed the action at observed scale, and the exact
stop coordinate for every pair.

The aggregate paired reduction must cross-check its first recorded action
divergences against the canonical post-hoc v3 receipt. It must not read terminal
error or success as part of this reduction.

## Frozen aggregates

For each method, report exact counts and ordered rows for:

- feedback-informed selections;
- zero versus nonzero posterior-mean vectors;
- baseline-action equal versus changed at observed scale;
- boundary relation and scale-bin distributions;
- observed-margin and nonzero posterior-span five-number summaries.

For v2/v3 common-prefix surfaces, report:

- exact pair count and pairable surface count;
- pair stop-reason and first-divergence coordinate distributions;
- zero versus nonzero dense score/posterior displacement;
- observed action-flip count at `lambda=1`;
- boundary relation and scale-bin distributions;
- v2-margin, v3-margin, maximum absolute score displacement, maximum absolute
  posterior displacement, and rounding-residual five-number summaries.

Rows are ordered by method, task fingerprint, seed, trajectory, and depth.
Counts and quantiles include every eligible row; no outcome-based exclusions or
bootstrap/inferential intervals are permitted.

## Interpretation and claim boundary

The receipt may describe whether posterior influence was structurally absent,
below the first local decision boundary, or large enough to change a recorded
action. It may compare the observed v3 displacement with the exact v2-to-v3
common-prefix boundary.

It may not claim:

- that multiplying feedback by a reported scale would improve error or solve a
  task;
- that a boundary challenger is a better action;
- that future states after a hypothetical flip are observed;
- causal sufficiency, method superiority, task transfer, statistical
  significance, retry authority, or locked-128 authority.

An integrity `PASS` means only that provenance, replay, reconstruction,
pairing, and deterministic reductions closed. The handoff decision remains
`STOP_REPAIR_NO_LOCKED_128_RUN`.
