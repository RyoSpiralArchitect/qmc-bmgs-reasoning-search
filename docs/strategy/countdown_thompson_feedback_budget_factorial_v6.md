# Countdown Thompson feedback × budget factorial v6

Scientific design fixed: 2026-09-04. Base: PR #25 merge
`661025df4f106ceca4c1de73cfc01516cce21d16`.

## Status and question

This is a **design-only development study**, not an execution authorization or
a sealed cohort. No v6 development tasks, calibration witnesses, proposals,
perturbation points, search traces, or outcomes are materialized by this change. Experiment
v6 reuses the unchanged v5 method; it does not introduce a sixth method version.

The prior observation found `48 -> 15 -> 9 -> 4 -> 1` at scale 16: all pairs,
first action divergence, completed suffix, common-prefix best-error improvement,
and new exact success. That post-intervention decomposition motivates a test;
it did not establish that additional budget would help.

The new question is:

> On a fresh source-disjoint development cohort, does doubling the legal-action
> scoring budget increase the exact-success advantage of scale 16 over scale 0?

Scale 16 is fixed from the earlier development selection, not assumed optimal.
The old `STOP_REPAIR_NO_LOCKED_128_RUN` and consumed authorization remain intact.
The old outcomes motivate the question but are not inputs to new task generation,
schedule selection, or outcome-dependent stopping.

## Factors, cohort, and pairing

Exactly 12 new solvable Countdown-D6 tasks, four exploration seeds, two scales,
and two budgets give **192 cells, 48 four-cell blocks, and 12 task clusters**.

| Fixed component | Value |
|---|---|
| Task generator | `generate_solvable_task_suite`, `sha256-counter-mod/v1` |
| Rules | `countdown-d6-positive-int-exact-division/v1` |
| Generation seed / maximum attempts | `26090401` / `10000` |
| Inputs / target ranges | six inputs in `[1,10]`, target in `[100,999]` |
| Task acceptance | existing exhaustive-solvability filter only; generator order |
| Exploration seeds, in order | `8192,8193,8194,8195` |
| Scale order | `0,16` |
| Primary budget order | `256,512` legal-action scores |
| Proposal | unchanged `greedy_rollout_target_error/v1` |
| Method | unchanged dimension-normalized scaled dense Thompson v5, IID only |
| Prior bonus / posterior SD scale | `1.0 / 1.0` |
| Backup | unchanged reverse Welford, discount one, no greedy anchor |
| Cell order | task acceptance order, budget, scale, exploration seed |

Use the existing `TrackAMethodSpec.dimension_normalized_scaled_dense_thompson`
factory, unchanged at the base revision. For absolute terminal error `e`,
`V_s(0)=1`, `V_0(e>0)=0`, and `V_16(e>0)=max(16/(16+e),2^-1074)` with the
existing integer-evidence/binary64 implementation. The
[v5 method-family definition](countdown_thompson_dense_scale_dose_response_v5.md)
remains authoritative; no new reward formula is fitted here.

The future cohort builder must first verify the existing sealed authorities and
exclude both full-task and source-multiset fingerprints of historical-2,
canary-12, reserved locked-128, diagnostic-12, and dense-scale-development-12.
It must also exclude the identities of all public qualification and full-shaped
fixtures, whose manifest must be fixed **before** cohort generation. Accepted
tasks must be unique in both identities. The locked reservation supplies
identities only; it grants no permission to evaluate those tasks.

Solvability calibration is a future cohort-generation operation, not an
experimental method run. Retain the generator/rejection receipt and task
definitions, never solution witnesses, calibration profiles, or hardness-based
selection. If 12 tasks cannot be obtained under the fixed recipe, stop; do not
change the seed, retry with a new cohort, relax exclusions, or extend attempts.

Within every task/seed, all four cells start with empty, separate mutable search
state. Task/state/action-order/source/seed/visit identity must yield identical IID
coordinates. Budget and method configuration must not enter the random stream
key. No persistent cross-cell posterior/proposal cache, budget-adaptive selection,
early-success stopping, provider call, or Sobol development cell is allowed.

## Isolate the primary budget; keep the six guards common

Use new profile IDs `feedback_budget_score256_common512_v1` and
`feedback_budget_score512_common512_v1`. Do not silently change legacy `score256`.

| Hard-work axis | B=256 | B=512 |
|---|---:|---:|
| proposal_state_evaluations | 172 | 172 |
| proposal_action_scores | 573 | 573 |
| legal_action_scores | 256 | 512 |
| generated_perturbation_coordinates | 572 | 572 |
| edge_selections | 171 | 171 |
| transitions | 171 | 171 |
| verifier_calls | 35 | 35 |

These guards follow the existing D6 structural proof, not observed new outcomes.
Every nonterminal state has at least three legal actions; at width six there
are at most `4*C(6,2)=60`. A complete trajectory uses five selections. With
`Bmax=512`, accepted selections are at most `floor(512/3)=170`, completed
verifications at most `floor(512/15)=34`, and accepted proposal-action/coordinate
charges at most 512. Allowing the next attempted atomic selection yields:

```text
proposal states = floor(Bmax/3)+2 = 172
proposal scores = Bmax+60+1      = 573
coordinates     = Bmax+60        = 572
edges/transitions = floor(Bmax/3)+1 = 171
verifiers       = floor(Bmax/15)+1  = 35
```

Preflight blocks on `usage + attempted > cap`, not equality. These common
guards keep the next primary-blocked attempt from also blocking a secondary
axis, and keep all accepted nonprimary usage strictly below its cap. The
maximum generic trace size is at most `4*170 + 2*34 + 1 = 749` events, below
the existing 1,000,000-event limit.

All cells must end with `primary_budget_blocked`, exactly
`stop_blocked_axes=[legal_action_scores]`, zero overshoot, and positive accepted
headroom on every other axis. A nonprimary block/exhaustion invalidates the whole
matrix; it is not a row to drop. A rejected attempt is never accepted work.
Logical scores are the matched resource; no wall-time or hardware-efficiency
claim follows merely from a larger logical budget.

## Budget-prefix qualification and integrity

For each fixed task/seed/scale, the small-budget accepted event history must be
an exact prefix of the large-budget history. There are **96 such checks**. Remove
only each trace's final `search_finished` event, then require canonical equality
of every low-budget event to the corresponding high-budget prefix event,
including event indices, hash links, charges, full payloads, semantic digests,
proposal/point material, selections, terminal verification, and backup updates.
Do not strip scores, semantic hashes, or feedback values to force agreement.

Whole records are not equal: run/configuration identity, work limits, final
ledger/storage/summary and final record digest legitimately differ. They must
each pass their own exact identity, canonical trace validation, and two-stage
fresh replay first. Never require cross-scale prefix equality after the first
scale-dependent action divergence.

Under the unchanged code, the budget does not enter selection scores or node
streams, and rejected preflight commits no proposal, point, graph, or event.
This supports the prefix requirement; it is **not yet a measured qualification**.
If exact prefix equality fails, classify integrity failure, retain the evidence,
and stop. Do not broaden the projection after observing outcomes.

There is also a structural completion guarantee, conditional on those valid-run
requirements. If the low-budget prefix used `L<=256`, the high run has
`512-L>=256` legal-action scores remaining there. Any unfinished/current-next
trajectory requires at most `60+40+24+12+4=140` more; verification charges no
legal-action scores. Thus `T512>=T256+1`, and any low-budget divergent trajectory
left unfinished must complete in its actual same-scale high-budget continuation.
A root rejection before the first selection is included: the high run can
complete that newly started trajectory. Also `3*140=420<512`, so `T512>=3`.
Check these inequalities as integrity consequences, not performance outcomes.
They guarantee verified completions, **not** distinct witnesses, exact solutions,
error reduction, feedback utility, or a causal mediation decomposition.

Before new development outcomes are opened, a separately reviewed implementation
must qualify both new profiles on the public fixture `(1,2,3,4,5,6) -> 720`,
using scales 0/16 and all four new exploration seeds: 16 new-profile traces.
Eight legacy-score256 traces (two scales × four seeds) additionally establish
that loosening only guards at B=256 leaves the accepted event sequence unchanged.
The legacy low-budget traces are public-fixture-only, never extra development
cells. Reproduce the existing eight public v5 binary/reciprocal anchor traces
as a separate unchanged-method gate. Every qualification trace requires its own
two-stage replay. No qualification traces or digests are claimed in this PR.

The subsequent implementation must also pass an independently named, nondiagnostic
192-cell full-shaped fixture, negative identity/budget/prefix tests, source/runtime
closure, no-overwrite one-shot publication, and an independent analyzer. Fix the
public fixture identity manifest before cohort generation. Production schemas,
cell keys, budget digests, run/analyzer domains, and authorization must be new;
the existing 384-cell runner and authorization must reject this experiment.

Freeze exact source/runtime receipts in that later implementation and cohort
seal. Retain the prior CPython 3.13.13, arm64 CPU binary64 numerical contract and
unchanged IID/search conformance; a runtime change requires a reviewed design
amendment and qualification, not an alias to the old receipt.

## Main estimand: paired exact-success interaction

Let `Y[i,r,s,b]` be 1 iff a valid complete cell contains a verified exact terminal,
otherwise 0. Valid budget stopping without success is zero; missing, corrupt or
replay-invalid material is not zero and invalidates closure.

For each of 12 tasks, average its four seeds first; weight tasks equally:

```text
D[i,b] = sum_r(Y[i,r,16,b] - Y[i,r,0,b]) / 4
I[i]   = D[i,512] - D[i,256]
Delta[b] = sum_i D[i,b] / 12
I        = sum_i I[i] / 12
         = sum_i,r(Y16,512 - Y0,512 - Y16,256 + Y0,256) / 48
```

Report exact reduced fractions, optionally with labelled percentage-point
rendering. The estimand describes this finite cohort; 48 task/seed blocks are
not 48 independent tasks. No p-value, confidence interval, bootstrap, significance,
power, or population-generalization claim is authorized by this design.

Publish all four 48-denominator arm success counts, both `Delta[b]`, `I`, all
12 task rows, each budget's paired new/lost/net successes, and the complete
16-pattern table in arm order `(Y0,256,Y16,256,Y0,512,Y16,512)`. Prefix integrity
implies each scale's success is nondecreasing with budget; seven of the 16 binary
patterns must have zero counts. Retain those zero rows. A forbidden pattern
is an integrity contradiction, never an ignorable outlier.

Positive interaction alone is not evidence of a useful high-budget method: it
can come from low-budget harm disappearing. The two budget-specific uplifts
and all four arm counts remain mandatory.

## Secondaries and mechanism order

After all 192 records close, analysis order is: qualification/provenance/replay
and 96 prefix checks; common-prefix mechanism; terminal-error reductions; exact
success and the fixed screen. Mechanism pairing accesses an outcome-redacted
view until its rows are fixed; integrity replay may validate full records.

At each budget, pair scale 16 with scale 0 over all 48 task/seed blocks. Reuse
the fixed first-divergence surface and explicit event-order opportunity rules
from PR #25: full preceding backup support, first differing applied backup,
step-charge headroom, divergence-trajectory completion, suffix-completion bins
0/1/2+, and separate no-divergence/absent-backup states. Stop cross-scale decision
pairing immediately after including the first differing action.

Keep exact success, minimum verified terminal absolute error, and shaped terminal
value separate. Retain full terminal vectors, first hit or null, per-budget
error W/T/L, and all 12 task summaries. The D6 maximum first trajectory cost is
140 legal-action scores; with nonbinding guards B=256 must complete at least one
terminal. A missing verified terminal is therefore `INVALID_ANALYSIS`, not an
invented error or a finite-only reduction. Prefix integrity also implies
`E[s,512] <= E[s,256]` for minimum error.

One fixed secondary is the ordinal error interaction:

```text
I_error = sum_i,r(sign(E0,512-E16,512)-sign(E0,256-E16,256)) / 48
```

For budget extension, report how many new completed terminals occur after the
low-budget accepted-event prefix, separately by scale. If the low-budget run
already diverged across scales, explicitly track whether its unfinished
divergent trajectory completes in the observed high-budget continuation. These
are actual matched-budget prefixes, not fabricated continuations. Do not pool
newly diverging high-budget pairs with previously diverged low-budget pairs.
Neither these counts nor conditional suffix-conversion rates are causal mediator
estimates. Primary results always retain all 48 four-cell blocks.

## Fixed conservative development screen

The numerical screen is deliberately an engineering choice, not a significance
threshold. It reuses a two-cell effect floor and adds breadth/stability checks
so a single-task rescue cannot alone advance the amplification hypothesis.
All of the following must hold:

1. Full integrity, source/runtime, sole-primary-budget, 192-cell and 96-prefix
   closure, with zero provider calls.
2. Interaction numerator at least 2: `I >= 2/48`.
3. High-budget feedback uplift at least 2: `Delta[512] >= 2/48`.
4. No low-budget net harm: `Delta[256] >= 0`.
5. No lost exact successes at B=512; high-budget new exact successes span at
   least two distinct tasks.
6. Removing any one task leaves both interaction and high-budget uplift strictly
   positive. Publish all 12 leave-one-task-out contrasts, denominator 44,
   regardless of whether the screen passes. These are sensitivity summaries,
   not resampling intervals or significance tests.
7. Every high-budget new-success pair first diverges only after a differing
   scale-dependent backup on the common prefix, using the fixed mechanism rule.

Only their conjunction yields
`DEVELOPMENT_SIGNAL_FOR_SEPARATE_CONFIRMATION_DESIGN`. This means only that a
new source-disjoint confirmation design may be proposed, not that any run is
authorized. Otherwise, a valid completed matrix yields
`STOP_REPAIR_NO_LOCKED_128_RUN` with all null/adverse/mixed evidence retained.
An integrity failure emits `INVALID_ANALYSIS`, not either scientific decision.
Do not short-circuit matrix execution based on accumulating outcomes.

Interpretation is not reduced to the screen alone:

- Both methods improve equally with budget: more-budget benefit, no amplification.
- `I>0`, `Delta[512]<=0`: interaction without a useful high-budget advantage.
- `Delta[512]>0`, `I<=0`: a feedback advantage may exist, but amplification is unsupported.
- More completed suffixes without exact/error gains: more realized opportunity only.
- Error gain without exact gain: near-miss development evidence only.
- Concentrated gains or lost successes: mixed result, no automatic advancement.

## Next gates, not current authority

The standard-library checker `scripts/check_feedback_budget_design.py` pins
these design bytes and checks the ordinal 192-slot layout, common guard
arithmetic, binary contrast identities, and a synthetic numerical screen.
Its task slots are not full task identities, and its synthetic reducers are
not production analyzers: they attest neither provenance, replay, prefix events,
nor feedback support. They cannot emit a production readiness decision.

```sh
python3 -P -B scripts/check_feedback_budget_design.py
python3 -P -B scripts/check_feedback_budget_design.py --self-test
```

The first command returns `DESIGN_CHECKS_PASS_NOT_EXECUTABLE`; the second uses
only synthetic arithmetic and does not open the design or any experiment data.

This PR fixes the scientific recipe and mechanical contrast/guard checks only.
Next: review this design; implement and qualify the new outcome-blind manifest,
fixture, runner/analyzer and domains; generate and seal the excluded cohort and
exact task-keyed schedule; review an exact authorization candidate; then obtain
permission for one complete run and independent analysis. No experiment may
reuse PR #23's consumed authorization or amend PR #24's STOP decision.

No claim of linear intelligence growth, general method superiority, optimal
scale, QMC benefit, natural-language transfer, confirmation, or locked-128
performance follows from either design validation or a positive development screen.
