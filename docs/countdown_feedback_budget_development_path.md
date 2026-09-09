# Feedback × budget: executable public qualification of the development path

This extends PR28's identity-only compiler with a new-domain computational
kernel and a runnable **public qualification adapter**. It connects fresh
search, two-stage replay, factorial/mechanism reduction, durable one-shot storage,
and a separate-process analyzer. It does not generate or execute the fresh
development cohort. The scientific design, old STOP and consumed authorizations
are unchanged.

## Implemented boundary

| Surface | Implemented here | Not established here |
|---|---|---|
| Inputs | Exact public fixture; fixed candidate contract and exclusions | New development task generation, solvability or seal |
| Kernel | New cell keys, record/run binding, 192-cell replay and 96 prefixes | Production cohort/authorization admission |
| Analysis | Ordered mechanism, errors, exact 2×2 contrasts and fixed screen components | Development decision from this public matrix |
| Publication | New-domain STARTED → 192 cells → RECEIPT → COMMIT; independent analysis | Remote-filesystem or reboot/crash guarantees |

The fixture uses the already excluded inputs `(1,2,3,4,5,6)` and targets `1..12`.
There are twelve task identities but **one source multiset**, not twelve
independent development sources. No generator or exhaustive solver is invoked.
The independently named manifest is
`docs/fixtures/countdown_feedback_budget_v6_development_path.json`. No previous
fixture identity or qualification receipt is rewritten.

## Domains and admission

`feedback_budget_development_kernel.py` implements the computational kernel in
`qmc-bmgs-countdown-thompson-feedback-budget/v1`. Cell keys bind the complete
contract and task-set digests, both task fingerprints, all factors and exact
component specs. The explicit `nondiagnostic_development_path_fixture` mode and
fixture experiment ID are part of every key. These are neither the synthetic
candidate-cell keys nor the older public/384-cell keys.

Every record also binds its execution source/runtime/baseline receipt. The
immutable input object accepts only the canonical, independently reconstructed
public manifest. Rehashed alternate tasks, candidates and old authorizations
are rejected. The future development seal, cohort loader, exact authorization
and one-shot consumption registry are **not implemented**. There is no generic
`--run`, task, seed, cohort, authorization, resume or provider CLI. Well-formed
storage bindings and the pure numerical reducer do not attest their own inputs.

## Independent analysis order

1. Recheck producing-source ancestry and exact bytes, protected imports/cache,
   CPython 3.13.13/arm64 CPU binary64 runtime, and reproduce the prior 32 public
   qualification traces, including legacy guards and unchanged-method anchors.
2. Validate **all 192** outer and search identities before the first replay.
   Independently regenerate and byte-replay every trace; require sole-primary
   budget stopping, zero overshoot and nonbinding common guards.
3. Check all 96 exact accepted-event prefixes. Remove only the final
   `search_finished` event; keep hashes, charges and full payloads. Check added
   completions and the actual current-next trajectory guarantee.
4. Freeze outcome-redacted mechanism rows. Reuse the prior first-divergence
   surface and stop cross-scale decision pairing at the first differing action.
   Retain full preceding backup support, first differing applied backup,
   event-order headroom, divergent-trajectory completion and suffix bins 0/1/2+.
   Keep no-divergence and absent-backup states explicit. Timing projections never
   open terminal verification or summary fields.
5. Reduce complete terminal-error/value vectors, per-budget/per-task W/T/L,
   exact ordinal interaction and observed suffix conversions. Missing terminals
   invalidate analysis. Keep low-divergent and newly-high-divergent pairs
   separate; every continuation is the actual same-scale high-budget history.
6. Open exact-success fields; retain first hit or null, all 48 four-arm blocks,
   all 12 task rows and leave-one-task-out contrasts, and all 16 success-pattern
   rows including seven forbidden zero rows. Compute the frozen numerical and
   differing-backup screen components using exact rational arithmetic.

Mechanism bytes are checked unchanged after outcome reductions. The screen's
conjunction is exposed for testing, but the public wrapper always leaves
`scientific_decision: null`, `development_cells_executed: 0` and authorization
false. Positive synthetic screens likewise cannot emit a scientific decision.
Integrity failures are `INVALID_ANALYSIS`, not a scientific STOP or zero-filled
outcome. There are no p-values, intervals, generalization or causal-mediation
claims.

## Durable closure

`feedback_budget_development_publication.py` shares only the pinned descriptor,
exclusive-file, fsync and snapshot mechanics of the existing public helper,
**not** its old-domain publisher or admission protocol. Storage-only inspection
does not claim replay. The implemented durability boundary is the exercised
local POSIX path/host, not remote storage, power loss or hostile same-user access.

Each publication contains exactly 195 private single-link regular files.
STARTED is durable before the first cell; COMMIT is last, after full replay and
reduction. Occupied outputs/summaries are never overwritten, resumed or adopted.
Known precommit failures retain partial cells and FAILURE. Uncertain commits do
not gain a countermanding failure marker; their occupied directories are kept.
Exact entry sets, bounded bytes, path identities and file/directory generations
are checked before and after analysis and around summary publication. Summaries
must be separate siblings of the input directory.

## Commands

Use a clean committed checkout and a **fresh, private, empty** bytecode-prefix
directory outside the repository for each run/analyzer/verify process. Do not
reuse an occupied output name. From the repository root, for example:

```sh
PYTHONPATH="$PWD/src" python3 -P -B scripts/run_feedback_budget_development_fixture.py --self-test

cache=$(mktemp -d "$HOME/.qmc-devpath-run-XXXXXX")
PYTHONPATH="$PWD/src" PYTHONPYCACHEPREFIX="$cache" python3 -P -B scripts/run_feedback_budget_development_fixture.py \
  --run-public artifacts/work/feedback-budget-development-path-v6-YYYYMMDD

cache=$(mktemp -d "$HOME/.qmc-devpath-analysis-XXXXXX")
PYTHONPATH="$PWD/src" PYTHONPYCACHEPREFIX="$cache" python3 -P -B scripts/run_feedback_budget_development_fixture.py \
  --analyze-public artifacts/work/feedback-budget-development-path-v6-YYYYMMDD \
  --summary artifacts/work/feedback-budget-development-path-v6-YYYYMMDD.summary.json

cache=$(mktemp -d "$HOME/.qmc-devpath-verify-XXXXXX")
PYTHONPATH="$PWD/src" PYTHONPYCACHEPREFIX="$cache" python3 -P -B scripts/run_feedback_budget_development_fixture.py \
  --verify-public artifacts/work/feedback-budget-development-path-v6-YYYYMMDD \
  --summary artifacts/work/feedback-budget-development-path-v6-YYYYMMDD.summary.json
```

The self-test is synthetic/preflight only, with zero search calls. Focused unit
tests also exercise real public search/replay, but their synthetic storage
bindings are not source-qualified execution receipts. Repository validation
invokes the CLI from outside the checkout.

The [2026-09-10 qualification note](reviews/countdown_feedback_budget_development_path_20260910.md)
records the producing commit, independently verified summary, unchanged 192
search traces and exact claim ceiling. It is not an independent code-review approval.

## Next gate

Review this implementation and freshly produced qualification; then implement
and qualify development cohort/seal and authorization admission against the
frozen recipe and historical authorities. Generate/seal the fresh source-disjoint
cohort only after those prerequisite gates close. Review the exact authorization
candidate and obtain explicit permission before a complete development run.
New executable bytes require fresh qualification, not an alias to this receipt.
Preserve producing commits with normal history-preserving merges, never
squash/rebase evidence-bearing history.
