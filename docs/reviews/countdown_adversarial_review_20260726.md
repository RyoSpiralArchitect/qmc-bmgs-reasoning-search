# Countdown search adversarial review

## Scope and review separation

This review covers the path from the generic QMC-BMGS prototype through the
frozen Countdown provider snapshots, matched IID/Sobol source ablation,
prior/noise calibration grid, replay artifact, result interpretation, and
proposed held-out strategy.

A fresh-eye reviewer was run read-only with parent conversation context
withheld and project-local context files temporarily hidden. Those files were
restored before the stateful audit and all implementation work. The fresh
review was then checked against source, raw local artifacts, tests, and the
recorded project history.

## Executive verdict

No P0 defect was found. The frozen two-task calibration artifact remains
numerically coherent:

- the preregistered decision implementation did not change after observation;
- all 9,216 compact records replay byte-for-byte;
- the summary and selected `(prior_bonus=1, posterior_sd_scale=1)` candidate
  recompute;
- the prior matched-source artifact remains unchanged;
- the current two-task workload never exceeds the recorded 14-action bank.

The review nevertheless found material P1 problems in the interpretation and
next strategy. The result is a **gate-passing development candidate**, not a
stable or source-robust winner. The earlier proposed post-positive phase switch
is redundant, the IID/Sobol pairing was mislabeled as CRN, full provenance
replay was weaker than documented, the raw artifact was not durable, and the
selected-only held-out design could not test calibration transfer.

## Fresh reviewer findings

### P1: the proposed phase switch is behaviorally redundant

The proposed policy started with `(prior, SD)=(1,1)` and switched to
`(.5,.5)` after the first positive terminal.

Before the first positive update, all empirical means are zero. Multiplying
both the prior and perturbation terms by `.5` multiplies every action score by
the same positive constant and cannot change the argmax. At the first positive
update, fixed `(.5,.5)` and the proposed switch have identical trajectories,
visit counts, and posterior state. After that point both use the same
coefficients. They are therefore the same policy for a shared stream.

The grid already contains fixed `(.5,.5)`. Running the switch would not add a
new factor or new evidence.

### P1: IID/Sobol blocks are not common-random-number blocks

The v1 schema and human contract used CRN wording. Source is part of seed
identity, however, and IID and Sobol use separate source-specific seeds and
generators.

Random values are genuinely reused across configurations and provider
snapshots *within each source*. IID versus Sobol is a matched dual-stream
comparison, not an IID/Sobol CRN variance-reduction design. Paired differences
remain descriptive and valid, but CRN variance-reduction language is
unsupported.

### P1: replay and storage provenance were weaker than the contract

Artifact creation validated the original Anthropic and OpenAI artifacts on
scratch copies. Standalone `--replay` only checked the receipt already stored
inside the calibration summary; it did not accept or revalidate the original
source directories.

The complete 117 MB calibration artifact and original provider artifacts also
lived under gitignored `artifacts/work/`. A clean clone could inspect tracked
digests but could not reconstruct all search bytes.

### P1: the selected candidate is thin and the held-out contrast was incomplete

The weakest selected cell contains only `2/128` successful seeds.
`(1,1)` and `(.5,.5)` have identical success labels and first-hit times in all
1,024 matched runs. `(1,1)` was selected by the fifth breadth tie-break, not
terminal reward.

OpenAI `->6` has IID `74/128` versus Sobol `54/128`; the eligibility rule has no
hard cap on this source gap. The rule is success-sign-symmetric, but its QMC
entropy requirement is not invariant to exchanging the source labels.

The historical held-out plan allowed only `(1,1)`. It could estimate the source
effect at that operating point but could not estimate calibration transfer
relative to the frozen `(0.1,1)` baseline.

### P1: full-DAG provider snapshots and banks do not scale to a broader suite

The two development tasks contain 64 nonterminal states in total. Broader
Countdown tasks can contain tens of thousands of reachable states and more
than 14 legal actions at a state. Scaling the full provider-snapshot and
persisted full-DAG bank design linearly would require large provider
acquisition and tens of gigabytes of bank text.

The next benchmark needs dynamic action dimension and lazy, visited-state
materialization. A broad provider-neutral benchmark should be separated from a
smaller provider-conditioned experiment.

### P2: fixed 14-dimensional banks did not fail fast

The current workload proves `max_actions=14`, so the frozen artifact is
unaffected. A broader state with more actions could nevertheless be parsed and
drawn from a 14-dimensional bank. Python `zip` then silently ignored trailing
actions before diagnostics failed later.

The review reproduced this with `(1,1,1,1,2,4) -> 8`, whose root has 15 legal
actions and descendants reach 22.

### P2: promised paired intervals were absent

The human contract listed paired conditional intervals, while the compact
calibration summary stored paired means and seed variance only. Post-hoc
reconstruction for the selected configuration gave descriptive normal
intervals for QMC-minus-IID success:

| Snapshot | Task | Delta | Descriptive 95% interval |
|---|---:|---:|---:|
| Anthropic | `->6` | -0.78pp | -9.06 to +7.50pp |
| Anthropic | `->10` | +1.56pp | -2.19 to +5.32pp |
| OpenAI | `->6` | -15.63pp | -27.42 to -3.83pp |
| OpenAI | `->10` | +1.56pp | -2.19 to +5.32pp |

These are fixed-task sampler intervals, not task-generalization intervals or a
multiplicity-corrected promotion test.

### Other P2 findings

- Generic QMC-BMGS accepted non-finite numeric configuration and `NaN` leaf
  values, allowing posterior contamination. The Countdown grid uses a separate
  finite binary kernel and was unaffected.
- The promoted-artifact verifier rejected non-finite JSON but not duplicate
  object keys or undeclared extra files.
- The manipulation check uses coordinate-wise one-dimensional discrepancy.
  It shows that the Sobol source changed marginal discrepancy and breadth, not
  that low discrepancy alone caused the breadth change.
- Proposal temperature differs sharply by provider/task. One scalar
  `prior_bonus` is not the same effective prior strength across provider
  snapshots.

## Stateful annotation

### Confirmed and actioned

| Finding | Stateful verdict | Resolution |
|---|---|---|
| phase-switch redundancy | mathematically exact | experiment removed from strategy |
| CRN label | correct schema/wording error | v1 retained as history; explicit erratum and matched dual-stream wording added |
| source replay gap | correct | full replay now revalidates both original artifacts; search-only replay is explicit |
| ignored raw artifact | correct | full-provenance archive promoted as a durable release asset |
| selected-only held-out | correct estimand gap | new plan includes selected and frozen baseline |
| 14-D overflow | concrete latent bug | fail-fast guards and regression tests added |
| missing paired intervals | correct | independent post-hoc audit added without rewriting the frozen summary |
| non-finite generic values | concrete latent bug | finite configuration and leaf-value guards added |
| strict JSON gaps | correct | duplicate keys, undeclared entries, and symlinks now fail |

### Valid caveats, not current artifact defects

- The “posterior” is an empirical Bernoulli mean with visit-count uncertainty,
  not a conjugate Bayesian posterior. Existing algorithm docs already call it
  an uncertainty proxy.
- Actual legal-action scoring differs after trajectories diverge even though
  verifier, edge, transition, update, and padded-bank axes are fixed.
- A task-blocked bootstrap over only two development tasks is a useful stress
  test but not a stable estimate of selection probability. It reinforces
  caution; it does not replace a held-out task suite.

### Independent artifact and compact-record audit

A second implementation that imports neither the grid runner nor its aggregate
and decision code verified the artifact closure and reconstructed the nine
search shards directly:

- coverage: `9,216/9,216`, with no duplicate or missing record;
- all 14 manifest-declared artifact files: byte, hash, strict-JSON, and entry
  closure pass;
- selected pooled success delta, QMC minus IID: `-3.32pp` descriptively
  (`IID-only=60`, `QMC-only=43`);
- pooled interval and p-value: deliberately not computed because provider rows
  reuse each task/seed bank;
- fixed provider/task stratum intervals and exact paired diagnostics: computed
  separately over the 128 exploration seeds;
- equal-kappa first-hit and cumulative-success invariants: pass;
- no-hit full-trajectory invariants: pass;
- canonical audit digest:
  `0fe86974fa06103240262b41d339cb30cb8266c03ebbc4dcb141b2e1c2353f81`.

This audit is post-hoc. The 512 pooled rows are neither independent sampler
blocks nor task-transfer units, so only their raw mean and discordance counts
are reported. It is a corruption and interpretation check, not a new promotion
test.

### Context-explained non-findings

- There was no post-outcome modification of the frozen eligibility or ranking
  rule.
- The exact two-task calibration artifact is not affected by the 14-action
  limit because its pairing gate proves the bound.
- The QMC coverage claim remains bounded: Sobol changed discrepancy and
  exploration breadth, while reward conversion remains unconfirmed.

## Corrected project-level claim

The strongest supported statement is:

> On two frozen development tasks, the matched Sobol source reduced root
> coordinate discrepancy and broadened search. Prior/noise calibration found a
> preregistered gate-passing operating point that entered terminal feedback
> under both sources, but did not establish stable task transfer or consistent
> QMC reward improvement.

The next experiment must measure calibration transfer and source effect
separately, against simple search baselines, over independently sealed tasks.
