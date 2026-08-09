# Countdown Track A engineering canary v2, 12 tasks

## Bottom line

The exact 936-cell canary completed once and passed every integrity, budget,
provenance, and two-stage replay gate.  It produced a useful negative
engineering result for the current Thompson search:

- the deterministic heuristic proposal solved `6/12` tasks with greedy,
  beam width 2, and PUCT under both budget profiles;
- every heuristic Thompson variant solved `0/48` runs under `score256`, for
  `0/192` across the four variants;
- under `verifier8`, candidate IID and candidate Sobol each solved `1/48`, on
  different tasks, while both frozen variants remained `0/48`;
- the equal-source candidate is Pareto-dominated by both greedy and beam on
  the 12-task score vector under both budgets.

The analyzer therefore reports `CANARY_ENGINEERING_PASS` under its frozen
hard-gate plus aggregate-adaptive-signal rule: the signal has six successful
cells because it includes PUCT.  It is not a pass for Thompson, QMC, the
candidate calibration, or search value over greedy.

This canary does not authorize semantic routing or Bayesian pruning.  The
current base-search failure is retained and should be diagnosed first.

## Authority and replay

The run was opened exactly once from clean revision
`3cbea083d8985926ee5b2da2c43ce6a2910d7c60`, after the separate reviewed
authorization PR had merged.

- bundle: `countdown_track_a_canary_12_seed_26072601/v2`
- bundle seal:
  `5799c9f17686f064b7c50ee741d79bfbb14a4d61b9048672068a586b258fd437`
- reviewed authorization digest:
  `27268ffe53596912a4f483dcbd796da288437b839ea18fc89040a08cace1c1e9`
- schedule: 936 unique cells, digest
  `96ceda207ed19220284742a4772191603c24f7e733f3567df856ad60824bbc16`
- run manifest digest:
  `7867ccbe237d42b78ec792eddd714f465a48d520c85405622c64c58aa2048878`
- committed artifact receipt digest:
  `cc48421c6537776930640716ee4256f340c7aa45375d1ae95f5a2045cdaa1210`
- analyzer summary digest:
  `95bc8d59fad1a12040f45f351e41229332ec1c0898d8b7db0c6b00bc6616fcdc`
- analyzer build digest:
  `02c16e10dcd59a769bf7c8698f6e4cfdb03000c205273dfc69dc53c32d41b786`

The committed run directory contains exactly `commit.json`, `manifest.json`,
and 936-line `records.jsonl`.  Their file SHA-256 values are:

| File | SHA-256 |
|---|---|
| `commit.json` | `61aeb5c9bb331e27e1a3f7d56e9ba19add9e619435d17b94773756f610750470` |
| `manifest.json` | `9b4654b57401c50566f63c8dd8f44b254de9c2c3da6271687fdd19339c489521` |
| `records.jsonl` | `c24a8797fe562dc7b748e10e692f7a208bedf945ff453ece3bca6333e1534dfe` |
| analyzer summary JSON | `c7052432e61affc695b5d2992f055f4c4053543bfb33024bc83e7ff0ae5803db` |

The independent analyzer regenerated proposal rows, legal-action order,
perturbation material, and every search result before emitting the summary.
All 936 records had `provider_calls=0`, `budget_valid=true`, and both replay
receipts equal to `PASS`.  The oracle-greedy positive control passed `24/24`.

The release asset
[`countdown_track_a_canary_v2_full_provenance.tar.gz`](https://github.com/RyoSpiralArchitect/qmc-bmgs-reasoning-search/releases/download/countdown-track-a-canary-v2/countdown_track_a_canary_v2_full_provenance.tar.gz)
contains the sealed seven-file bundle, reviewed authorization, committed run,
and analyzer summary.  Its SHA-256 is
`2b065248506d21f8fca5f5c6c15225a04f88fc7dc1d09544d023f330cffdc1ef`.
The extracted bundle and run reproduced the same summary digest using the
Git-tracked byte-identical authorization.

## Descriptive result

The task is the reduction unit.  A stochastic task score is the fraction of
four nested seeds with any exact solution; deterministic methods contribute
one binary value.

### Heuristic proposal

| Budget | Method | Successful runs | Tasks with success | Mean task score |
|---|---|---:|---:|---:|
| `score256` | greedy | `6/12` | 6 | 0.5000 |
| `score256` | beam width 2 | `6/12` | 6 | 0.5000 |
| `score256` | PUCT c=1 | `6/12` | 6 | 0.5000 |
| `score256` | frozen IID | `0/48` | 0 | 0.0000 |
| `score256` | frozen Sobol | `0/48` | 0 | 0.0000 |
| `score256` | candidate IID | `0/48` | 0 | 0.0000 |
| `score256` | candidate Sobol | `0/48` | 0 | 0.0000 |
| `verifier8` | greedy | `6/12` | 6 | 0.5000 |
| `verifier8` | beam width 2 | `6/12` | 6 | 0.5000 |
| `verifier8` | PUCT c=1 | `6/12` | 6 | 0.5000 |
| `verifier8` | frozen IID | `0/48` | 0 | 0.0000 |
| `verifier8` | frozen Sobol | `0/48` | 0 | 0.0000 |
| `verifier8` | candidate IID | `1/48` | 1 | 0.0208 |
| `verifier8` | candidate Sobol | `1/48` | 1 | 0.0208 |

Greedy, beam, and PUCT solved the same six tasks.  PUCT did not add a solved
task beyond the greedy proposal in this canary.  Under `score256`, candidate
minus frozen and candidate Sobol minus candidate IID are identically zero on
all 12 tasks.  Under `verifier8`, candidate minus frozen is `+2.08pp` for each
source, supported by one positive task per source; candidate Sobol minus IID
has mean zero because the two isolated successes occur on different tasks.
These are descriptive values, not intervals or promotion tests.

The uniform-proposal control was `0` for every method and budget.  This
confirms that the six deterministic successes came from proposal quality, not
from a proposal-neutral search improvement.

## Post-hoc mechanism diagnosis

This section was not a preregistered endpoint.  It reads the independently
validated selection events to explain the engineering failure and has no
promotion authority.

The implemented Thompson index is

```text
posterior_mean
+ prior_bonus * exp(proposal_logp)
+ posterior_sd_scale / sqrt(visits + 1) * Normal(0, 1)
```

Across these tasks the root has 27--55 legal actions, with mean 38.  The
largest of that many unit-normal perturbations is commonly much larger than
the candidate prior bonus, whose maximum contribution is about `0.63`.  The
observed root choices match that scale mismatch:

| Budget/method | Root draws | Mean proposal rank | Top-1 | Top-5 | Mean selected prior mass |
|---|---:|---:|---:|---:|---:|
| `score256` PUCT | 35 | 1.14 | `30/35` | `35/35` | 0.5750 |
| `score256` candidate IID | 142 | 16.92 | `16/142` | `34/142` | 0.0813 |
| `score256` candidate Sobol | 143 | 17.12 | `16/143` | `30/143` | 0.0813 |
| `verifier8` PUCT | 96 | 1.13 | `84/96` | `96/96` | 0.5822 |
| `verifier8` candidate IID | 384 | 17.64 | `34/384` | `80/384` | 0.0676 |
| `verifier8` candidate Sobol | 384 | 18.10 | `33/384` | `72/384` | 0.0663 |

The candidate does explore more distinct root actions: about `2.9` per run
under `score256` and `7.6--8.0` under `verifier8`, versus `1.4--1.5` for PUCT.
That breadth did not convert to exact reward.

Within each `score256` Thompson variant, every completed task-namespaced path
was unique: frozen IID `99/99`, frozen Sobol `99/99`, candidate IID `100/100`,
and candidate Sobol `99/99`.  Pooling across method labels leaves 292 unique
task-and-action paths among 397 trajectories; the 105 duplicate extras are
mostly the matched frozen/candidate paths.  In contrast, PUCT produced 26
completed trajectories but only 13 task-namespaced unique paths, and selected
the heuristic root rank 1 on `25/26` of them.  The candidate and frozen
configuration still chose the same first root action in about 90% of matched
same-source runs, so increasing the probability-mass prior bonus from `0.1`
to `1.0` usually did not change the initial perturbation argmax.

The fixed-score profile buys only about two completed trajectories per
adaptive run because every selection scores the complete legal-action vector.
Mean verified terminals were `2.17` for PUCT and `2.06--2.08` for Thompson.
The fixed-verifier profile buys eight trajectories, but candidate Thompson
retains about 32 live nodes per run while receiving only sparse binary terminal
feedback.  Failed actions back up zero, equal to the unvisited mean; most nodes
are not revisited enough for the posterior to overcome the initial
extreme-value noise.

Across the four `score256` Thompson variants, about 89% of node-local streams
received exactly one perturbation point, with a maximum of four visits in this
slice.  Consequently the node-local Sobol sequence was usually not long enough
for low-discrepancy coverage across visits to become an effective search
mechanism.

This supports, but does not prove, two concrete failure hypotheses:

1. the probability-mass prior and unit-normal perturbation are not calibrated
   across dynamic action dimensions; and
2. full-action scoring plus binary terminal feedback allocates too little
   revisitation for Thompson learning.

Nothing here isolates an IID-versus-Sobol effect.  Both sources show the same
base-search failure, so source comparison is downstream of repairing the
selection scale and feedback density.

## Engineering decision

1. Retain the canary as a valid negative result for the current Thompson
   design.  Do not reinterpret `CANARY_ENGINEERING_PASS` as candidate success.
2. Do not add semantic clustering, routing, or Bayesian pruning yet.  The
   preregistered Pareto gate blocks that escalation under both budgets.
   The frozen analyzer explicitly sets
   `locked_evaluation_blocked_by_this_flag=false`; pausing locked-128 below is
   a post-outcome engineering decision, not that formal Pareto gate.
3. Do not claim QMC benefit or harm from this result.  Reward conversion was
   too sparse for the source contrast to answer that question.
4. Before spending the substantially larger locked-128 budget, run a new
   source-disjoint development diagnostic that changes one base-search factor
   at a time:
   proposal-scale representation, action-dimension normalization, candidate
   narrowing/progressive widening, or shaped failure feedback.
5. Start with an outcome-free counterfactual selection audit over stored
   proposal rows and perturbation vectors.  Freeze the transform from a target
   proposal-rank-retention range, not from exact-success labels.  Then test the
   chosen transform on a new development cohort that excludes the canary and
   reserved locked-evaluation identities.
6. A minimal first run is 204 `score256` cells on 12 new tasks: PUCT once per
   task, plus four IID seeds for current candidate, scale-calibrated candidate,
   scale-calibrated candidate with bounded failure value, and that method with
   one greedy-first safety trajectory.  Record proposal-rank retention,
   terminal prior, best terminal error, node visit distribution, and exact
   success before looking at any winner label.
7. Keep IID as the first base-search diagnostic source.  Reintroduce the
   matched IID/Sobol comparison only after the base method is competitive with
   greedy, beam, and PUCT at the same work budget.  If only the greedy-first
   variant improves, attribute the gain to the anchor until Thompson adds
   independent value.

Skipping the present locked-128 run means no formal promotion or rejection is
claimed for the frozen candidate.  That is intentional: the project objective
is an effective search algorithm, and the canary already exposed a cheaper,
actionable base-search defect.

## Claim boundary

This is a 12-task development canary with four nested stochastic seeds.  It
contains no confidence interval, p-value, winner, non-inferiority result, or
task-transfer claim.  It is not evidence for natural-language reasoning,
provider superiority, or general QMC superiority.  Its positive claim is
limited to valid execution/replay and a concrete engineering failure signal
for the frozen Countdown search implementation.
