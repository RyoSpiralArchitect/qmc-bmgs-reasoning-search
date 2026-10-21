# Fixed-feedback diversity before allocation

PR #29 was merged at c0a59722f3d23d4703d0b834bfccc68da218d786 after a fresh
read-only review of head 7044af2, no actionable findings, and 25 focused tests
passing. The merge tree matches that reviewed head. The review checked source
references, all 512 raw cells and six publication mirrors without running a new
experiment or full suite. The earlier result-package full validation passed
1,688 tests at 9a568b0; 7044af2 only recorded completion. No hosted CI or GitHub
review approval was present at the merge check. These are distinct evidence.

The previous matrix did not support weaker feedback or the half-budget
exact/calibrated portfolio. Its protected branches repeated their entire action
sequence in 62/64 blocks. Two full-budget exact successes were first found at
331 and 374 scores, beyond the 256-score branch allocation. That observation
motivates separating stream diversity from allocation, not tuning away the
negative result or claiming that independent streams must be better.

## Step 2: a fixed three-arm comparison

| Arm | Branches and stream keys | Total primary cap |
| --- | --- | --- |
| single16 | One dense-scale-16 branch, key 0, full budget | B |
| paired16 | Two isolated dense-scale-16 branches, keys 0 and 0, half each | B |
| diverse16 | Two isolated dense-scale-16 branches, keys 0 and 1, half each | B |

All branches use the unchanged provider-free greedy-rollout proposal and IID
dimension-normalized Thompson method. Scale 16 is a fixed reference, not a claim
of optimality. The prior, approximate reward, uncertainty proxy, routing,
pruning and answer readout do not vary across arms. The single branch starts
from scratch and continues within its full budget; no resume API is added.

Every one of the seven work-axis caps is split equally for the two-branch arms,
with an indivisible remainder assigned to the second branch. Both branches run,
even if the first succeeds. No graph, posterior, proposal cache, budget residue
or outcome is transferred. Repeated work is charged twice. Caps for all other
axes start at 100,000 before splitting. A secondary guard binding invalidates
the comparison cell and stops the attempt with partial evidence retained.

Derive each stream seed from the first 16 hex digits of SHA-256 of canonical
JSON containing domain `feedback-diversity-stream/v1`, the root seed, and branch
index 0 or 1. The key-0 stream is shared across arms, and the derived table is
fixed in the plan with a collision check. Budget and arm labels are not seed
inputs. Distinct keyed pseudorandom streams are not a proof of statistical
independence, and repeated observations do not become independent sources.

Readout is the first verified exact solution in branch/observation order,
otherwise the minimum-error verified terminal; no terminal means null. Readout
uses already charged evidence and adds no verifier call. Parallel wall-clock
speedup is not measured: branches run sequentially and all work is counted.

## Frozen development recipe

Use 32 new source-unique solvable tasks, eight root seeds 32768–32775, primary
budgets 256 and 512, and three arms: **1,536 cells, 2,560 branch searches, 768
same-arm budget-prefix pairs**, maximum 589,824 legal-action scores. There are
256 task-seed blocks per arm/budget but only 32 source clusters. This is a
bounded development comparison, not a power claim or confirmatory sample.

Generation uses the existing SHA-256 counter generator, seed 26102201, six
inputs in 1–10 and targets in 100–999. Accept the first 32 source-unique solvable
tasks outside the authenticated identity exclusions, within 1,000 attempts.
Preserve all acceptance and rejection identities. Do not select by hardness,
search success or observed diversity; do not store solver witnesses or hardness.
In addition to the historical registry, original C5 cohort identities, PUBLIC
source and regression fixtures, exclude all eight accepted source multisets
from the prior portfolio cohort. Its pinned reviewed cohort bytes are used for
identity exclusion only, not to evaluate prior studies.

The new fixed attempt directory is
`artifacts/work/feedback-diversity-development-20261022-a`. Exclusive directory
creation is the one-attempt fence. Partial output, failure, a changed digest or
an absent COMMIT never authorizes retry, overwrite, resume or a new cohort.

## Reduction and structural checks

The primary practical comparison is **diverse16 minus single16**, separately at
both budgets: paired gains, losses, net exact success, minimum-error
win/tie/loss/missing, every work axis, source/seed strata, and leave-one-source
and leave-one-seed-out reductions. Report all cells and retain missingness.

The diverse16-minus-paired16 contrast is diagnostic: both share the same first
half-budget branch, so the diversified union cannot lose an exact success
against duplicate paired branches. Nonloss here is structural, not evidence of
superiority to full-budget continuation. Paired16-minus-single16 captures the
cost of duplicated half-budget work under these fixed policies; it is not an
identified decomposition of all allocation, cache and scheduling mechanisms.

Record per branch: terminal count, first exact discovery work on all axes,
full action-sequence digest, first-trajectory digest, and choice count. For
two-branch arms report common action-prefix length, identical sequence/first
trajectory counts, primary-only and secondary-only successes. Also report lost
full-budget successes and which first occur beyond the half-budget cap. Keep
all row-level diagnostics and unspent work, including no-terminal rows.

The separate analyzer regenerates the cohort and generatively replays every
branch before reconstructing the complete summary. It checks the fixed matrix,
all budget prefixes, byte-identical duplicate paired branches, the shared
primary branch across paired/diverse arms, and the allocated primary branch's
decision/work prefix of the full-budget branch. The latter depends on
secondary caps remaining nonbinding. Both subset success relations must hold.
The analysis fence is exclusive; no partial analysis is adopted or resumed.

## Step 3: interpret before changing allocation

The requested third step is a decision based on this new evidence, not an
automatic second experiment. No allocation ratio, adaptive scheduler, cache
sharing, separate learned value head or extra reward tuning is implemented here.

- If diversified streams produce complementary successes, inspect whether those
  compensate for lost full-budget successes across sources and seeds. Only then
  formulate a separately frozen allocation comparison with unchanged diversity.
- If diversity rises but exact success remains below full continuation, retain
  that tradeoff; consider continuation-oriented allocations rather than claiming
  the restart strategy was successful.
- If differently keyed streams still choose much the same actions, inspect the
  proposal and action-selection mechanisms before adding scheduling complexity.
- Mixed, sparse or missing evidence can leave the decision unresolved. Do not
  silently introduce a winner, population inference or outcome-selected rerun.

Any resulting allocation experiment needs its own predeclared plan, validation
and explicit exact-plan approval. New evidence may justify designing it, not
executing an unreviewed implementation.

## Authority and evidence boundary

Ryō approved proceeding through review, diversity comparison and subsequent
allocation reasoning. Before generating the new cohort, present the completed
implementation commit and exact plan digest for explicit execution approval,
conditional on full repository validation. A literal CLI digest is not evidence
of human approval. The plan binds source/runtime/policy, exclusions and all
factors; plan generation itself is read-only and outcome-blind.

Historical source and result files remain unchanged. This additive API and
runner do not reopen old E4 slots, original C5, locked evaluation or providers.
The comparison is not QMC-versus-IID or an LM evaluation. Raw traces remain
local/ignored; plans, manifests, summaries, review and validation receipts are
published. Local integrity controls do not claim adversarial-host security.
