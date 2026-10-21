# Fixed continuation allocation at total 512

PR #30 merged at `2fc168157f9d4adc039f6a330d65e0361b31bb15` after its
current diff, clean GitHub merge state, saved qualification and raw evidence
were checked. Its 1,718-test result qualification was at `2e1ed208`, followed
by the records-only `d3b45aaf`. The premerge check passed 30 focused tests and
recomputed the complete saved reductions without new search or replay.
There were no hosted checks, reviews or review threads; local qualification
is not external approval. The merge tree equals `d3b45aaf`.

This implements the separate hypothesis in
[countdown_feedback_diversity_allocation_proposal_20261022.md](countdown_feedback_diversity_allocation_proposal_20261022.md).
That exact file and all historical evidence remain unchanged. The direction
and implementation are approved. The newly frozen exact execution plan still
requires explicit human approval after qualification.

## One factor and three fixed arms

| Arm | Primary stream key 0 | Secondary stream key 1 | Each of the other six caps |
| --- | ---: | ---: | --- |
| single16 | 512 | absent | 100,000 / absent |
| equal16 | 256 | 256 | 50,000 / 50,000 |
| weighted16 | 384 | 128 | 75,000 / 25,000 |

The seven axes are legal_action_scores, generated_perturbation_coordinates,
edge_selections, transitions, proposal_action_scores,
proposal_state_evaluations and verifier_calls. Every arm has the same total
cap on every axis. Integer remainders go to the final branch; all declared
caps divide exactly. The only intended policy change is continuation versus
restart allocation. There is no ratio scan or adaptive scheduling.

Dense feedback scale 16, IID dimension-normalized Thompson method, prior,
learned return, uncertainty proxy, greedy-rollout proposal, routing, pruning,
branch-key construction and verified readout are fixed. The new allocation
API calls the unchanged Track A engine, reuses the prior stream derivation
and readout reducer, and reproduces the prior single16 and diverse16 branch
records exactly at matched limits. Both branches start independently and run
sequentially even after success. Caches, posteriors, work residue and outcomes
are never transferred. Repeated work is charged; readout adds no verification.

## Cohort, seeds and precision aim

Freeze 64 source-unique solvable tasks and eight common root seeds
65536 through 65543 before generation. Generation seed is 26102231, using the
existing SHA-256 counter generator with six inputs in 1–10 and targets in
100–999. Accept the first 64 eligible source multisets within 2,000 attempts.
Eligibility is exhaustive solvability and identity exclusion only. Retain
acceptance order and every rejection identity/reason; do not consume solver
witnesses or hardness as policy inputs, or select sources by search outcomes.

Exclude the authenticated historical identity registry, original study
identities, PUBLIC and regression sources, the eight portfolio sources and
all 32 prior diversity sources. Also exclude every rejected identity from
those two recent development generations. Their bytes are pinned and used
only for identity exclusion. Root seeds and generation seed are fresh; all
arms use the same root-seed table and domain-separated keys. Distinct keys
are not proof of independent statistical observations.

There are **64 source clusters, 512 source-seed blocks, 1,536 cells and 2,560
branch searches**. The separate analyzer replays all branches and checks four
branch-prefix relations per block, or **2,048 prefix pairs**, plus 512
structural blocks. The search-pass legal-action-score ceiling is **786,432**;
each other axis has a ceiling of **153,600,000**. Full replay repeats those
search ceilings, so run plus replay have at most 1,572,864 legal scores.
Generation, validation and analysis overhead are outside these search ledgers
and must not be represented as equal total compute or measured speedup.

The sample-size aim is bounded estimation of source heterogeneity and paired
gains/losses with twice the prior source count, at the same number of cells
and branch searches. It is not powered to confirm a small improvement. The
primary estimand is the mean of each source's mean paired exact-success
difference over the eight fixed seeds. Block net resolution is 1/512; seed
repetitions do not produce 512 independent sources. For differences in [-1,1],
the worst-case nominal sample-standard-error reference is 1/sqrt(63), about
0.126; multiplying by 1.96 gives about 0.247. This is an independent-source
planning reference, not a confidence interval for this fixed deterministic
recipe or a power calculation. Counts and recipe will not expand in response
to results.

## Prespecified analysis and feasibility

The primary practical contrast is weighted16 minus single16. The diagnostic
allocation contrast is weighted16 minus equal16; retain equal16 minus single16
as a reference. For all three retain exact gains, losses and net; minimum-error
wins, ties, losses and missingness; every work axis and unspent work; every
source and seed stratum; and leave-one-source-out / leave-one-seed-out results.
Omission diagnostics are sensitivity analyses, not authorization to omit data.

Report all source mean differences, their mean, positive/tied/negative source
counts and descriptive source-level standard error. The reducer provides no
confidence interval, p-value, winner or scientific decision. Interpret sparse
or conflicting evidence as unresolved; no new default is selected.

Preserve per-branch first exact discovery work, first terminal work, terminal
counts, action/first-trajectory identities, complementary successes and the
full branch diagnostics. Retain full-continuation successes lost by each split
and whether discovery lies beyond that arm's primary cap. A secondary-only
success is a practical gain only if full continuation fails. Report branches
that cannot reach a terminal as missing, never fill their error with zero or
exclude their source. No outcome-based retry or altered allocation is allowed.

Tests use only previously excluded fixture sources and non-study root seed 41.
They exercise first-trajectory feasibility at 128, plus primary prefixes
256→384, 384→512 and 256→512, and secondary prefix 128→256. Fixture feasibility
is not a universal guarantee for all new sources. The actual analysis checks
all applicable decision/work prefixes and branch-subset success claims after
full generative replay. Different union allocations have no nonloss guarantee.
A secondary guard binding stops the attempt with partial evidence retained.

## Frozen authority and one attempt

The fixed output slot is
`artifacts/work/feedback-allocation-development-20261022-a`.
`--plan` is read-only and does not generate a cohort or search. It binds all
current source files, runtime, policy, proposal, exclusions, caps, seeds,
counts and the complete 470-file parent-path inventory at the frozen candidate.
Of the merged parent's files, 469 remain byte-identical. The sole change is
`scripts/validate.py`, which invokes the complete test-discovery wrapper below;
the plan explicitly binds both its original hash and candidate reference.
The preserved source membership and frozen candidate bytes are checked before
and after operations.

The initial unexecuted plan and its failed qualification remain intact. The
current freeze is `countdown_feedback_allocation_development_20261022.v2.plan.json`.
Its scientific design is unchanged. The revision adds qualification portability
and binds 58 source references, including the validator, discovery wrapper and
eight regression tests. Full collection is 1,752 tests: the original 1,718,
26 allocation tests and eight portability tests.

The eight historical modules (328 tests) have fixed paths embedded in saved
receipts. In an isolated checkout set `QMC_BMGS_HISTORICAL_TEST_ROOT` to the
existing canonical checkout named by those receipts. The wrapper first proves
that every mirrored test and source file equals both the candidate and the
immutable PR30 merge tree; only the candidate validator entry point may differ.
It authenticates the original 5,329 protected artifacts and source memberships
against the prior qualification's hash-bound inventory, then repeats those
checks after the tests. The historical modules read that verified mirror;
all other tests run in the isolated candidate. The test identity multiset must
remain identical. Failures, missing artifacts, changed bytes and skips fail
qualification. No receipt path, expected digest, admission assertion or old
test is patched. Fixture tests and static CLI self-tests do not authorize a
fresh cohort, archive reconstruction or study execution. The mirror is not
editable by this workflow and is never an alternate admission root.

Before execution, complete operator review and `python scripts/validate.py`
on the frozen implementation commit. Publish the exact commit, plan digest,
counts and caps in the PR and request explicit human approval for **one run
and one separate-process full analysis**, conditional on that qualification.
The broad direction approval and literal CLI digest are not that approval.

After the actual human decision, preserve its source and direct quote in a
canonical approval receipt at
`artifacts/work/feedback-allocation-authorization-20261022/approval.json`.
The closed receipt binds the plan digest, approved candidate commit and
tracked qualification receipt. The runner requires completed validation with
zero skips and a records-only descendant that preserves every candidate
file. Local receipt checks bind evidence; they do not authenticate a hostile
same-user environment or turn fabricated text into human authorization.

Run and analyze use the same operation commit. Exclusive output-directory
creation prevents a second run; exclusive analysis STARTED prevents a second
analysis. Partial failure is retained. There is no resume, overwrite, automatic
retry or alternate output/seed/cohort argument. The analyzer regenerates the
fixed cohort, authenticates every COMMIT reference and replays every branch,
then rechecks all bytes/memberships before publishing its summary.

Raw evidence stays local/ignored; future manifests, summaries and receipts are
promoted separately without editing prior evidence. Original C5, locked
assessment, E4 reruns, providers, paid APIs, cloud compute, deployment and
merging this next PR remain outside the authorized scope. No new study has
been executed during this implementation and qualification stage.
