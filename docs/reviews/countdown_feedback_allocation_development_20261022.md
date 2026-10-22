# Allocation implementation review before execution

This operator review covers the additive allocation API, fixed development
runner, analysis, approval binding and fixture tests. It is not an independent
reviewer or hosted CI approval. PR #30 was merged at
`2fc168157f9d4adc039f6a330d65e0361b31bb15`; the complete 470-file parent is
preserved, including the exact allocation-proposal filename and contents.

The full-continuation and equal-split branch records and summaries match the
previous API under identical inputs. Weighted allocation calls the same engine
at 384 and 128 with the same stream-key function and dense scale 16. Every
axis conserves its cap, both streams run after success, repeated work is
charged, and no residue is transferred. The old API and engine are untouched.

Fixture tests cover all four applicable branch-prefix relations, explicit
first-trajectory feasibility at the 128 boundary, isolated engine equivalence,
verified readout, missing terminals, secondary guard failures, strict replay,
closed inputs, seed collisions and work conservation. First-trajectory tests
use three previously excluded source multisets and non-study seed 41; they do
not establish new-cohort performance or universal feasibility.

Runner tests use only excluded all-ones fixtures or synthetic records. They
cover exclusion of prior accepted and rejected identities, outcome-blind plan
construction, complete cells, per-source statistics, paired losses, missingness,
replay tampering, altered STARTED and COMMIT bindings, membership changes,
partial-attempt preservation and retry refusal. New exact-plan human approval
and zero-skip qualification must be recorded before generation/output creation;
direction-only approval, changed candidates, missing evidence and numeric
aliases are rejected. Receipt binding is local integrity, not proof against
fabrication by a hostile same-user process.

The initial 20 scoped tests passed, followed by all 26 scoped tests passing in
37.310 seconds with zero skips. A subsequent qualification-reference numeric
alias hardening is covered by a focused gate test and the required full suite.
These are fixture checks, not execution of the new 64-source cohort.

The plan fixes 64 sources, eight common seeds, one total budget 512 and three
allocations: 1,536 cells, 2,560 branch searches and 2,048 branch-prefix pairs.
The sample-size/precision rationale, source-level estimand, descriptive standard
error, no-population-claim limitation and no-extension rule are preregistered.
Both favorable and unfavorable paired results remain; no default is selected.

At this implementation snapshot full repository qualification is pending.
A later additive qualification receipt must name the exact tested commit,
plan digest, captured logs, test/skip counts and protected-byte checks. The
plan's execution_authorized:false remains a historical design field; future
human approval is a separate receipt, not a silent edit to this plan.

No new study generation, allocation experiment, additional prior-study replay,
provider call, cloud compute or next-PR merge occurred in this stage. The next
required human decision is one run and one separate complete analysis of the
exact frozen commit/plan after full qualification passes.
