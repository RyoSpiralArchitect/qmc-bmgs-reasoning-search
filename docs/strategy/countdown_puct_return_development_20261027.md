# PUCT return isolation: implementation and registration, 2026-10-27

Status: candidate implementation and outcome-blind plan only. No fresh cohort,
development run or scientific analysis is authorized by this document.

## Research question and current authority

The north star remains useful search strength, not satisfying an accounting
framework or defending a named algorithm. PR37's fixed prior-tilt result is
negative against PUCT: -129/1024, model interval [-0.165115389583868,
-0.086837735416132], NO_PRACTICAL_UPLIFT_SIGNAL. Its mean-use diagnostic is
also negative (-16/1024), without establishing a general failure of learning.
Different historical cohorts cannot identify a paired improvement over PR36.
Those results, failures, source files and original PUCT remain unchanged.

Ryō answered 「うん！！🙂‍↕️🌀」 to the specific proposal:
「PR #37のmerge → この単一候補の実装・登録まで進めてよい？
実験は候補と計画を固定してから、別途確認します。」
PR37 was merged without rewriting history at
`0b0381bfc861673a8555c4a6169c24c4f239e91c` (reviewed head `750d75f`).
This authorizes this implementation, registration and software qualification,
not a run, a future digest, a retry or automatic merge of the new candidate.
Execution requires later conversation-verified exact candidate/plan permission
and successful full qualification. No experiment approval receipt is created now.

## One factor, two deterministic arms

Both methods use the existing selection rule exactly, including its `1+N`
finite-visit convention and binary64 operation order:

```
score(s,a) = Q(s,a) + 1.0 * p(s,a) * sqrt(1 + sum_b N(s,b)) / (1 + N(s,a))
```

| Arm | Scalar backed up at a verified terminal |
| --- | --- |
| puct (unchanged control) | 1 for exact success, otherwise 0 |
| puct-dense16 (one candidate) | 16 / (16 + absolute terminal error), exact = 1 |

The prior is the existing deterministic greedy-rollout error heuristic, not an
LM prior. Proposal computation, canonical ties, zero initialization, visit and
arithmetic-mean/m2 updates, DAG sharing, full-budget stopping and terminal
verification are unchanged. There is no root noise, random material, beta/scale
sweep, extra heuristic, novelty reward, maximum backup or budget redistribution.
Scale16 is the pre-existing dense return, not selected using this new cohort.
This one-factor intervention tests this particular dense target within fixed
PUCT; it cannot identify all return learning or its general optimality.

### Why another binary mean-off study arm is unnecessary

In the current implementation all means initialize to zero. Every binary return
is zero before the first verified exact terminal; the arithmetic mean stays
zero while visits still update. Consequently removing the Q term preserves
the entire pre-first-exact traversal and first-hit work under identical inputs
and budgets. Once a positive Q can affect selection, success_any is already true.
The control's first-hit advantage therefore does not demonstrate Q-value learning.
This is a source-level property plus small contract fixtures, not a new result
on the prospective cohort and not a claim that visits or the prior do no work.
Post-first-exact action sequences, diversity and costs need not be equivalent.

The dense target can change Q before exact success, so the primary can test
whether near-miss experience helps first-solution discovery. It might instead
overconcentrate traversal. Passive decompositions will not be called causal
counterfactual rollouts. No performance improvement is presumed.

## Implementation and evidence boundary

The additive `puct_return.py` adapter inherits the original selector, ordinary
step, traversal and mean-update functions. Binary PUCT delegates directly to the
old engine and must keep identical inner bytes. The dense adapter repeats the
small terminal transaction with only the scalar/evidence changed: reserve,
charge one verification, verify once, preview, append atomically, then commit.
Failed accepted commits poison the session; a guard rejection verifies nothing.
Historical engine code is neither edited nor monkey-patched. The adapter uses
private frozen internals, so a future engine change requires requalification.

Distinct method/configuration/event/summary identities are stamped before
hashing. Since neither arm consumes random/external material, dense replay
regenerates all proposals, choices, terminal verification and backups from empty
state and compares every inner byte, then reconstructs the complete outer record.
The old control uses its existing replay. Rehashing forged values cannot make
them pass generative replay. Metadata storage sizes need not match across arms
and do not measure Python heap or wall-clock efficiency.

## Registered future matrix, not permission to execute

Use the first 512 eligible solvable source-multiset-unique Countdown sources:
six inputs 1..10, target 100..999, generator26102701, maximum10,000 attempts.
Exclude the authenticated historical registry and all published development
cohorts including PR37's256 sources, plus the tracked-Python literal fixture
superset. Exclusions use identities, never difficulty, success or witnesses.
Static extraction does not prove discovery of arbitrary dynamic fixtures.

Each source contributes exactly one physical run of each deterministic arm:
512 sources x 2 arms =1,024 cells. Root0 is a nonrandom identity, not a sampled
seed or a repetition. Alternate arm order by source slot; no shared search state.
The fixed512-source design uses more source pairs without stochastic root
replication, still fewer physical cells than PR37. It does not guarantee power
or a 0.05 half-width. No sample-size extension is triggered by results.

Each cell retains the512 legal-action-score cap and six separate100,000 guards,
maximum524,288 primary scores. All seven actual/unspent axes and proposal-internal
work remain visible. Equal legal-score caps do not imply equal total compute.
A binding non-primary guard invalidates the attempt; partial evidence is retained.

Sole primary: source-paired `puct-dense16-minus-puct` exact-success difference.
Use all512 pairs, exact rational mean/sample variance (denominator511), and the
unchanged `mean +/- 2*source_sd/sqrt(n)` approximate model interval. Preserve the
precision-first order: incomplete/invalid; n<64 or zero variance => null interval
UNRESOLVED; half-width>0.05 => IMPRECISE; lower>+0.02 =>
PROMISING_FOR_FRESH_CONFIRMATION; upper<=+0.02 => NO_PRACTICAL_UPLIFT_SIGNAL;
otherwise UNRESOLVED. Uniqueness and deterministic solvability filtering do not
establish independence, population representativeness or interval coverage.
No secondary contrast replaces the primary; winner/scientific_decision stay null.

Keep per-source gains/losses, minimum errors and missingness, first-hit work or
right-censoring, terminal/revisit/proposal counts, first divergence and saved
Q/prior/visit decomposition. Leave-one-source-out is sensitivity, not a confidence
interval. With one deterministic row per arm, root-omission analysis is inapplicable.

The plan seals source/runtime/exclusions/order and generates no source. A later
approved run uses an exclusive output fence, and a separate process regenerates
the cohort and all1,024 cells byte-identically before reduction. It retains at
most two outer detailed cell records, not a claim of bounded total RSS. There is
one budget, hence zero cross-budget prefix pairs. No automatic retry/resume,
provider/C5/locked evaluation, default promotion or QMC/transfer run is included.

## Remaining gates

Focused fixture checks and same-agent source review are not performance evidence,
full repository qualification, independent review or execution permission.
Freeze the candidate and executable plan, complete full `scripts/validate.py`,
then present that exact commit/digest and one-run/one-analysis scope to Ryō.
The experiment output slot must remain absent until that later approval.
