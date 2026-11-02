# Prior-tilt candidate review, 2026-10-26

Scope: one additive prior-anchored policy, mean-off control and three-arm runner
on merged main `1f441585fa44191d7806e9e75b71a666cbdb2968`. No prospective cohort
or research outcome was generated to select or debug this candidate. Every
pre-existing tracked file remains unchanged, including sealed plans and raw
provenance references. Existing source-level statistics and transaction/material
authentication are reused; no budget-management framework was added.

## Mechanism and implementation checks

The author checked that log prior, scale16 terminal mean and original-uniform
Gumbel terms have explicit roles. The new policy does not use stored m2 or
visit-dependent noise scaling. Mean-off removes mean use before score addition
while retaining updates. PUCT remains the original binary-return control.

The original generator still creates uniform/normal pairs; only the Gumbel
transform of their original uniforms drives new scores. Its normal values are
not transformed back through a CDF. This incurs redundant normal computation,
openly retained to avoid a material/authentication rewrite during a policy test.
The ideal categorical law is not claimed exact for a finite keyed grid.

The preliminary focused run passed42 tests with zero skips in56.750s. Ruff
passed on the five new Python files. Tests cover a fixed synthetic categorical
fixture, equal-mean prior recovery, unit return odds, many actions/concentrated
prior, no visit rescaling, closed policy identity, PUCT inner-byte equivalence,
all-method replay, actual subprocess replay outside the checkout, forged scores
and material, guard failure retention, source-level reductions/precision gates,
closed authority, no repeated execution/analysis and complete-matrix refusal.
These are implementation tests, not search-performance evidence.

## Claim and authority review

Ryō authorized steps1 through2 of the preceding proposal before a candidate
digest existed. This is delegated candidate selection, not exact-digest consent.
The human proposal/instruction and one-candidate/one-run/one-analysis scope will
be bound to the fixed commit and plan in a separate receipt after qualification.
The executable plan retains authorization=false at this snapshot.

The256 source clusters, four within-source roots and single physical PUCT row
are kept distinct. The only primary is prior-tilt16-minus-PUCT. Mean-off is a
mechanistic diagnostic, not a replacement primary or a general learning claim.
The unchanged precision-first model rule can yield IMPRECISE even for a large
negative difference; filtered deterministic generation does not establish
independence or coverage. Fixed256 is not a precision/power guarantee.

The joint selector change cannot establish which single old mechanism caused
the historical loss. No coefficient sweep, old-data retuning, QMC/semantic
routing, provider, C5/locked evaluation, default promotion or merge is included.

## Remaining gates at this snapshot

The source/claim inspection and tests above are by the same agent, not an
independent reviewer or hosted CI approval. Full repository qualification is
pending on the exact committed candidate. Only a real PASS with no skips and
preserved sources/evidence permits the separately captured one run, followed by
one full generative analysis. A later completion receipt must name that tested
commit; this historical pending snapshot is not rewritten as prior success.
