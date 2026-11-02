# Research status: return to search value, 2026-10-24

## North star and present decision

The goal is reasoning-time search that is strong, computationally useful and
behaviorally interesting under meaningful fixed budgets. QMC, a Bayesian label,
branch diversity and successful replay are not goals in themselves. The
[four gates](engineering_north_star.md#four-gates) separate correctness, search
strength, behavior and systems cost.

The current development series has produced reliable negative evidence about
feedback/portfolio/allocation hypotheses. It has **not** established that the
current single16 search beats simple deterministic baselines. The next focus is
that missing comparison, with a separate diagnostic for the learned selection
mean. Further ratio tuning, adaptive scheduling, provider calls and default
promotion are paused as priorities, not newly authorized operations.

## Evidence map, without pooling cohorts

| Stage | What the evidence supports | What remains unsupported |
| --- | --- | --- |
| D4/channel/credit diagnostics | Coverage and resource changes can be separated from success; schedule/feedback tuning was stopped after adverse fresh results | General QMC superiority, useful semantic reasoning roles, or an LM deployment gain |
| Track A canary, 12 sources | Under heuristic score256, greedy/beam/PUCT each solved 6/12; four then-current Thompson variants totaled 0/192 | Present-day single16 performance: its mechanism and subsequent cohorts differ |
| Portfolio, 8 sources × 8 seeds | At score512, exact/dense16/calibrated1/protected1 solved 3/6/3/1 of 64 blocks; weakened feedback and the protected split were not improvements in that matrix | Scale16 optimality or a source-population effect |
| Diversity, 32 sources × 8 seeds | Distinct streams changed behavior; diverse−single was +2/256 at cap256 and −1/256 at cap512 | Equal splitting as a better default; independent sources multiplied by seed count |
| Allocation, 256 sources × 8 seeds | At cap512, single/equal/weighted solved 212/185/195 of 2,048 blocks; primary weighted−single gained34/lost51 | Current single16 beating greedy/beam/PUCT; 3:1 allocation improvement; any unrun ratio or adaptive policy |

Sources: [north-star chronology](engineering_north_star.md),
[canary](observations/countdown_track_a_canary_v2_20260810.md),
[portfolio](observations/countdown_feedback_portfolio_development_20261020.md),
[diversity](observations/countdown_feedback_diversity_development_20261022.md),
[allocation and recovery](observations/countdown_feedback_allocation_recovery_20261024.md).
The canary's 6/12 and the allocation study's 212/2,048 are different cohorts and
units; comparing those percentages is not an estimate of progress or regression.

The earlier E4 PUBLIC tests used 64 definitions of one source multiset, not 64
independent sources. Their numerical screens and full replay qualify that PUBLIC
connection, not the original C5 or locked evaluation. See the
[E4 observation](observations/countdown_feedback_budget_receiver_e4_public_20261016.md).

## What allocation actually taught us

The sole primary weighted16−single16 result was −17/2,048
(−0.8301 percentage points). The predeclared approximate source-level model
interval was about [−1.8369, +0.1767] percentage points, producing
`NO_PRACTICAL_UPLIFT_SIGNAL` under the fixed practical +2pp and precision rules.
It includes zero. This is not equivalence, proof of no effect, established
population harm, or a reason to replace the primary with weighted−equal +10.
`winner` and `scientific_decision` remain null.

Weighted primary384 solved161 blocks; its secondary128 added34 successes not
found by the full stream. Full continuation found51 more at scores388–511:
`161 + 34 < 161 + 51`. These were discoveries never reached by the truncated
branch, not forgotten answers. Distinct behavior and complementary successes
were real, but insufficient for the tested allocation. Observed future
first-hit times are not a deployable pre-decision scheduling signal.

All 6,144 cells had a verified terminal. Source and seed omissions, minimum
error, every work axis and negative strata remain in the saved results. Distinct
source identities and deterministic solvability filtering do not prove source
independence, model-interval coverage, seed-population generality or causality.

## What is implemented now

The [algorithm map](algorithm.md) separates the original token-prefix prototype
from the current Countdown canonical DAG. In the latter, proposal priors,
terminal-return means, visit-dependent noise and exact answer verification have
different roles. Saved second moments do not enter current action selection;
reverse terminal averaging is not successor-value Bellman bootstrapping. The
latest experiments are provider-free and IID, with no semantic routing/pruning.

The original prototype's uncertainty/TD descriptions remain historical design
context, not proof that the current kernel implements all those mechanisms.
No source code, method parameter, reward, candidate, statistical formula or
experimental artifact is changed by this correction.

## Gates still open

| Gate | Current evidence | Required next evidence |
| --- | --- | --- |
| Correctness | Recorded full replay, saved-event recomputation, explicit budgets and retained failures | Preserve these invariants for any new candidate; test counts are not search-strength outcomes |
| Search strength | Within-family mechanisms and negative allocation results | Current single16 versus fixed simple baselines on the same fresh sources; learned-mean ablation |
| Useful behavior | Different trajectories and complementary solutions are observed | Show that those behaviors improve exact success rather than merely increase diversity |
| Cost | Seven charged axes and internal proposal diagnostics are retained | Distinguish equal score caps from total work; account for proposal-internal scoring and report time/memory without equating them to search work |
| Transfer | Typed-DSL no-retuning gate was reserved in the original contract | A future locked method and fresh transfer design after basic competitiveness; not executed here |

## Fork-review disposition

A parent-chat-free, read-only model review inspected merged main
`70e27cf8352f2285bd0272dcb0008c5cf53edca7`. Project-local instruction files were
temporarily hidden and restored byte-identically. This is a separate model
perspective, not independent human approval or perfectly uncontaminated context.

- Accepted: the current simple-baseline comparison is missing; the research
  entry points lagged the latest series; prototype and current mechanisms need
  separate descriptions.
- Accepted with scope: score-cap comparisons do not establish total-cost
  efficiency. Existing results remain valid for their declared estimands.
- Context retained: integrity engineering was necessary to obtain trustworthy
  results, but is not a substitute for algorithmic strength. The allocation
  sequence answered a bounded question; its negative result is durable evidence.
- Corrected inference: a small or imprecise mean-off difference would not prove
  learning useless. Precision and a predeclared decision rule must govern the
  next interpretation, with unresolved results allowed.

## Provenance and authority

PR #32 was merged as `70e27cf`; its result suite ran on `b01f377` with
1,775 tests, skip0 and PASS. The later `1ffc12d` was a completion-record-only
commit, not another full suite. The original interrupted analysis's
completion/exit/progress and host-restart trigger remain UNKNOWN. The first
recovery qualification's pre-test environment failure remains preserved.

This living status page and the corrected README/algorithm/north-star prose are
not replacements for dated evidence. Existing manifests and receipts retain
their original bytes. Historical references to earlier versions of these living
documents resolve at their recorded Git input revisions, not by rewriting hashes
to fit a later checkout. Do not rerun consumed attempt helpers on this new tree.

This documentation correction and the subsequent experiment-design proposal do
not authorize generation, search, replay of consumed attempts, C5/locked runs,
provider calls, another recovery, or adoption of a new default. Exact execution
authority must be established separately for an implemented, qualified candidate.
