# Fixed-feedback allocation: continuation versus a second stream

## Status and question

Candidate implementation and preregistration only. Ryō approved building this
next comparison after PR #30; no new cohort generation or experiment is
authorized until the exact candidate commit and plan digest receive a separate
explicit approval, conditional on full repository validation. A CLI digest is
not proof of human approval. No automatic retry, extension or ratio sweep.

PR #30 merged at `2fc168157f9d4adc039f6a330d65e0361b31bb15`.
Its result remains mixed and its evidence files are unchanged. At total 512,
equal diverse streams gained 11 and lost 12 exact successes versus a full
single stream (256 repeated blocks, 32 source clusters). All 12 losses first
solved after 256 scores in the single stream. Six solved by 384; six of the
11 additional successes appeared within 128 scores in the second stream.
These observations motivate a candidate, not a counterfactual performance
estimate for 384/128. See the frozen
[allocation proposal](countdown_feedback_diversity_allocation_proposal_20261022.md).

Question: with the same feedback, proposal, stream keys and total work caps,
does retaining more first-stream continuation improve the development outcome?

## Three fixed arms, one total budget

| Arm | Key 0 primary | Key 1 secondary | Primary contrast role |
| --- | ---: | ---: | --- |
| single16 | 512 | absent | Full-continuation baseline |
| equal16 | 256 | 256 | Equal-diversity diagnostic reference |
| weighted16 | 384 | 128 | Candidate; sole primary comparison versus single16 |

All use the unchanged Track A engine, IID dimension-normalized dense Thompson
scale 16, and provider-free greedy-rollout target-error proposal. Prior, reward,
uncertainty proxy, routing, pruning and answer readout are held fixed. This is
not QMC-versus-IID and not an LM evaluation. Scale 16 is not claimed optimal.

Allocation applies to **all seven work axes** before either branch starts.
For equal16 the first cap is floor(total/2); for weighted16 it is floor(3total/4).
The secondary receives the exact remainder. Other total caps are each 100,000,
so their weighted caps are 75,000/25,000. No cap is created or discarded.
A secondary guard binding invalidates the cell and stops the attempt while
retaining partial evidence. Unspent work is reported, never transferred.

Both branches run even after success. Each has isolated graph, posterior,
cache and budget; all repeated work is charged. No resumption or adaptive
scheduler is introduced. Branches execute sequentially, not as a speed test.
The inherited SHA-256 `feedback-diversity-stream/v1` derivation maps each root
and index 0/1 to a 64-bit seed, independent of arm and budget. The same stream
key is used across arms. Distinct streams are not independent sampling units.
Readout chooses the first verified exact solution in branch/observation order,
else the minimum-error verified terminal, else null, with no extra verifier.

## Frozen fresh development recipe

- 256 new source-unique solvable tasks; eight fixed roots 65536–65543.
- One total budget 512; three arms: 6,144 cells, 10,240 branch searches.
- 2,048 repeated task-seed blocks per arm, **256 source clusters**, not 2,048
  independent sources. Maximum combined primary work is 3,145,728 scores.
- Generator seed 26102301, maximum 10,000 attempts. The existing six-input
  1–10 / target100–999 recipe accepts the first source-unique solvable tasks
  outside authenticated exclusions; no selection by search outcome or hardness.
- Exclude the historical identity registry, original study identities, PUBLIC
  source, regression fixtures, prior eight portfolio sources and prior 32
  diversity sources. The two prior cohort files are read for identity only.
  Keep all generation acceptance/rejection identities; solver witnesses and
  hardness do not enter the search or saved task cohort.
- Fresh roots differ from the prior portfolio16384–16391 and diversity32768–32775
  blocks. Root keys and their derived table are frozen before generation.
- Fixed new slot: `artifacts/work/feedback-allocation-development-20261023-a`.
  Exclusive mkdir is the attempt fence; failure, missing COMMIT or changed
  digest never licenses overwrite, adoption, retry, resume or replacement.

## Estimand, precision and development readout

The sole primary estimand is the average source-level paired exact-success
difference **weighted16 minus single16**, conditional on these eight fixed seeds,
the accepted generation recipe and exclusions. For source s,
`D_s = sum_seed(success_weighted - success_single) / 8`. The point estimate is
`mean_s(D_s)`; sample variance uses the 256 source values with denominator255.
Exact rational moments are saved. The seed repetitions do not multiply n.

Report an explicitly **model-based approximate 95% interval**
`mean(D) ± 2 * sample_sd(D) / sqrt(n_sources)`. The multiplier2 is a transparent
rounded approximation, not an exact t quantile or distribution-free coverage
guarantee. It assumes exchangeable, sufficiently independent accepted source
clusters and an adequate normal approximation for the mean. The deterministic
counter recipe, solvability filtering and source sampling without replacement
do not establish these assumptions or calibration; distinct source hashes alone
do not establish independence. No seed-population, natural-task-population or
causal generalization follows. The interval is not a probability that the fixed
parameter lies in the displayed range.

The prespecified practical uplift is **+0.02 absolute success rate** and the
precision target is **half-width <=0.05**. These are research design choices,
not facts inferred from prior results or a guarantee of useful power. Choosing
256 source clusters gives half-width0.025/0.05/0.075 for source SD0.2/0.4/0.6,
respectively. Thus even n256 may miss precision; it is not a design guaranteed
to detect two percentage points. Do not add sources after inspecting results.

Apply this order to the sole primary comparison:

1. Fewer than64 clusters or zero source variance: interval/precision are null;
   `UNRESOLVED`. No degenerate zero-width certainty, even for uniform success.
2. Half-width >0.05: `IMPRECISE`, regardless of the point estimate.
3. Lower bound >0.02: `PROMISING_FOR_FRESH_CONFIRMATION` only.
4. Upper bound <=0.02: `NO_PRACTICAL_UPLIFT_SIGNAL` under this model/design,
   not equivalence or proof of absence across tasks.
5. Otherwise `UNRESOLVED`.

Every status retains `winner: null` and `scientific_decision: null`. No default
promotion or confirmation is authorized. The equal16 comparisons, minimum
error and all subgroups remain descriptive; none may replace the primary
comparison post hoc. Source/seed leave-one-out ranges are sensitivity summaries,
not confidence intervals. Missing terminals remain null in error reductions.

Method references: [NIST mean confidence limits](https://www.itl.nist.gov/div898/handbook/eda/section3/eda352.htm)
for the mean/standard-error form and coverage interpretation;
[NIST sample-size design](https://www.itl.nist.gov/div898/handbook/prc/section2/prc222.htm)
for dependence on variability, precision and power assumptions. Neither source
validates this generator or supplies the chosen 2pp/5pp research thresholds.

## Integrity and complete analysis

The analyzer runs in a fresh process/runtime, regenerates the fixed cohort and
generatively replays all 10,240 branches with byte-identical cell reconstruction.
The complete 6,144-cell coordinate/hash matrix must match the committed operation.
It verifies three branch decision/work prefixes per block (6,144 total):
primary256→384, primary384→512, and secondary128→256. Each corresponding
branch-success subset relation is mechanical. There is **no whole-arm subset
guarantee** between equal16 and weighted16, since one branch grows and one shrinks.
Header/seed/allocation checks cover 2,048 structural blocks.

Persist all arms, gains/losses/net, minimum-error win/tie/loss/missing, all seven
work axes, unspent work, by-source/by-seed and both leave-one-out reductions,
action/first-trajectory overlap, complementary/primary-only/secondary-only
successes, and first-exact work. Lost single-stream successes are compared to
the actual primary allocation (384 for weighted, 256 for equal), not a hardcoded
half-budget threshold. Do not select only favorable sources or successful rows.

The analyzer has its own exclusive start fence. Every input ref and directory
membership is rechecked after replay; no partial analysis may be adopted.
Raw remains ignored with matching tracked plan/manifests/summary and receipts.
Source/runtime/policy/test refs bind the plan. Plan creation is read-only and
outcome-blind; it neither generates tasks nor calls search. All old470 tracked
files and existing raw evidence remain unchanged.

Before requesting execution: excluded-fixture prefix/guard and tamper tests,
hand-computed source-statistics tests, review, committed candidate and full
repository validation. Full-suite input commit and later record-only completion
commit remain distinct. Human execution approval must cite the exact candidate
and plan digest. Original C5, locked evaluation, providers, old E4 runs, new
ratios, extra experiments and merge are outside this candidate's authority.
