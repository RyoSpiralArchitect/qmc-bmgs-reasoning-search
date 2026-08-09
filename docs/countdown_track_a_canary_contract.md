# Countdown Track A canary preregistration contract

## Scope and claim boundary

This stage seals the inputs and decision rules for a provider-neutral
engineering canary. It does not execute search, materialize a proposal row or
perturbation point, inspect a canary success value, or authorize a performance
claim.

The canary has no inferential or promotion authority. Its later output may
establish that the matrix executed with complete actions, closed budgets, and
two-stage replay. Method superiority, calibration transfer, non-inferiority,
and an IID-versus-Sobol effect remain decisions for the separately locked
128-task evaluation.

## Sealed bundle

The canonical bundle is
`docs/preregistrations/countdown_track_a_canary_v1/`. It contains:

- `exclusions.json`: the two historical development tasks and their tracked
  provenance;
- `tasks.json`: the 12 accepted tasks and the complete generator rejection
  manifest, but no solver witness or calibration profile;
- `proposals.json`: proposal specifications and their experimental roles;
- `methods.json`: seven complete method specifications and exact seed rules;
- `budgets.json`: both hard-limit maps and their structural derivation;
- `preregistration.json`: cell schedule, gates, summaries, and claim language;
- `seal.json`: exact filenames, byte counts, SHA-256 values, component digests,
  and the aggregate deterministic digest.

Every component is canonical finite JSON with its own deterministic digest.
Verification rejects duplicate keys, non-finite constants, noncanonical bytes,
symlinks, directories, missing entries, undeclared entries, byte drift, hash
drift, schema drift, and a regenerated payload that differs from the tracked
bytes. Creation uses a sibling temporary directory and refuses to overwrite an
existing destination.

The version-one aggregate seal digest is
`6d3d6249141bc74e827ca0fcdf860656e5f0885d043607b80b5d9919edc30b78`.
This identifies preregistration bytes only; it is not a search result.

## Task cohort

The task generator call is equivalent to:

```text
generate_solvable_task_suite(
  count=12,
  seed=26072601,
  excluded_task_fingerprints=<two historical tasks>,
  excluded_source_multiset_fingerprints=<the same two source multisets>,
  excluded_identity_record_digest=<sealed exclusions digest>,
)
```

The historical identities come from the tracked
`docs/preregistrations/countdown_calibration_grid_v1.json`; its byte SHA-256 is
sealed before its task rows are used. A byte-identical SHA-bound copy is
packaged as `qmc_bmgs.data/countdown_calibration_grid_v1.json` so an installed
wheel can reproduce the manifest without access to a checkout; repository
verification checks the tracked authority directly. Accepted tasks must be unique by both
full task fingerprint and source-multiset fingerprint. Exhaustive solvability
is the only outcome-conditioned inclusion rule. The generator's in-memory
calibration and witness data are deliberately not serialized.

The accepted task-pool digest is
`d2374929a694882527c82acc6fa763f0a405abb4a06b75c3e48e694000bdeb9c`.
Generation accepts 12 tasks in 16 attempts after four unsolvable rejections.
These are task-selection facts, not search results.

## Proposal and method schedule

The primary fair proposal is `greedy_rollout_target_error/v1`. The
`uniform/v1` full matrix is a proposal-quality control.
`oracle_path_count_positive_control/v1` is an explicitly contaminated positive
control and runs greedy only.

Both fair proposals cross the seven frozen methods:

- greedy;
- layer-synchronous beam width two;
- PUCT with `c_puct=1` and no root noise;
- frozen `(prior_bonus=.1, posterior_sd_scale=1)` Thompson with IID;
- the same frozen configuration with Sobol;
- candidate `(prior_bonus=1, posterior_sd_scale=1)` Thompson with IID;
- the same candidate configuration with Sobol.

Greedy, beam, and PUCT each run once per task, proposal, and budget at seed
zero. They are not copied across stochastic seed labels. Each Thompson method
uses exploration seeds `7168,7169,7170,7171`.

For one task, fair proposal, and budget there are three deterministic cells and
16 stochastic cells. The sealed totals are therefore:

```text
uniform full matrix       = 12 * 2 * 19 = 456
heuristic full matrix     = 12 * 2 * 19 = 456
oracle greedy control     = 12 * 2      =  24
total                                            936
```

The cell primary key contains the task fingerprint, proposal-spec digest,
complete method-spec digest, runtime-bound method-manifest digest,
budget-profile digest, and exploration seed. The complete method-spec digest
is mandatory because all four Thompson configurations share one human-readable
method identifier; the method-manifest digest additionally prevents a cell
from being substituted across a Python, Torch, architecture, or generator
runtime boundary.

The tracked bundle is deliberately an exact-runtime execution qualification,
not a claim that every environment admitted by the library's broad package
requirements will regenerate identical bytes. Version one binds CPython
3.13.13, arm64, Torch 2.11.0, and the recorded generator conformance digests.
Before any canary cell is opened, the future runner must pass both a portable
sealed-byte/schema/provenance audit and a separate live exact-runtime
qualification against those bindings. A runtime mismatch is `NOT_RUN`; it is
not converted into a failed search row. The execution environment must be
pinned or containerized before the first outcome is materialized.

```bash
qmc-bmgs-countdown-track-a-canary-manifest --qualify-runtime
```

## Outcome-blind budget guards

The two profiles have separate primary axes:

| profile | proposal states | proposal scores | legal scores | coordinates | edges | transitions | verifiers |
|---|---:|---:|---:|---:|---:|---:|---:|
| `score256` | 86 | 257 | **256** | 257 | 86 | 86 | 18 |
| `verifier8` | 41 | 1121 | 1121 | 1121 | 41 | 41 | **8** |

For a state with `n` values, at least three actions are legal and at most
`4*C(n,2)` are legal. The width-six through width-two maxima are
`60,40,24,12,4`; a complete trajectory therefore uses at most 140 legal-action
scores and exactly five transitions. Eight trajectories use at most 1120
scores and 40 transitions. Under score256, an ordinary method can accept at
most 85 selections and finish at most 17 trajectories. Beam width two
completes within 220 scores and ten retained edges. Every non-primary guard is
the appropriate structural maximum plus one, so a valid cell retains positive
headroom rather than ending at ambiguous exact exhaustion.

## Canary execution gate

The future manifest-driven runner must publish all 936 expected records once
and only once. An integrity or budget failure invalidates the complete canary;
the failed row is not dropped, imputed, or silently counted as zero.

Every record must satisfy all of the following:

- strict finite JSON, sealed external identity, and valid digests;
- the complete canonical legal-action order with no padding or truncation;
- generative proposal/point replay followed by byte-identical search replay;
- zero ledger overshoot and exact event-to-ledger closure;
- `budget_valid=true`, no non-primary blocked axis, and no exhausted
  non-primary guard;
- at least one terminal readout;
- zero perturbation coordinates for deterministic methods, and coordinates
  equal to legal-action scores for Thompson methods.

Adaptive PUCT and Thompson cells must stop on the selected primary axis:
score256 rejects only the next whole legal-action selection, while verifier8
uses exactly eight verifier calls and stops before any ninth-trajectory work.
Greedy and beam may end naturally as `method_complete`.

Oracle-greedy must solve every task under both profiles. A failure is a task,
oracle, transition, verifier, or accounting defect rather than a negative
search result. Under the heuristic score256 stratum, PUCT plus the four
Thompson methods must produce at least one exact success in aggregate; zero
halts the locked run as `STOP_REPAIR_NO_LOCKED_128_RUN`.

## Descriptive canary analysis

The independent transfer unit is the task. A stochastic task score is the
fraction of four nested seeds with any exact success. A deterministic score is
one binary result. Deterministic rows are never expanded to four pseudo-runs.

The canary reports raw 12-task score and paired-delta vectors, counts, means,
ledger usage, minimum guard headroom, replay status, and storage/wall-time
projections. It reports no confidence interval, p-value, multiplicity-adjusted
test, promotion, winner, or non-inferiority label.

Candidate-minus-frozen and source contrasts are averaged within task before
cross-task summaries. IID and Sobol remain distinct matched streams and are
not called common random numbers. A simple-baseline Pareto flag is descriptive:
if the equal-source candidate score is no better than both greedy and beam on
all 12 tasks and each baseline relation is strictly worse on at least one task,
semantic routing and pruning escalation is blocked. The candidate is not
replaced from this canary.

## Authorization boundary

The sealed bundle authorizes only implementation of a runner and analyzer that
consume it fail closed. Canary search may begin only after this bundle and that
runner are merged and a clean-checkout verification passes. A changed task,
scope, method, proposal, runtime, budget, gate, or summary rule requires a new
versioned preregistration before any replacement output is opened.
