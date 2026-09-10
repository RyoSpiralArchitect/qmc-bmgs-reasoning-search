# Feedback × budget: cohort and review-candidate admission

This layer follows the [public computational path](countdown_feedback_budget_development_path.md).
It implements outcome-blind cohort sealing, independent seal verification and
an **authorization candidate for review**, not execution authorization. The
frozen v6 design, contract, public executables, old STOP and consumed
authorizations are unchanged. No fresh v6 tasks have been generated here.

## Trust and ordering

`scripts/feedback_budget_development_admission.py` closes these prerequisites:

1. Clean committed checkout, complete producing ancestry, protected loaded
   source/cache origins, exact current/producing bytes and the frozen
   CPython 3.13.13 / arm64 CPU binary64 runtime.
2. Independent verification of the v5 sealed bundle, recursively including its
   diagnostic/canary/locked identity authorities and old generator order. Verified
   identities must equal the original six exclusion groups: **179 full-task /
   167 source-multiset identities**. No historical development outcome is read.
3. Pinned new-domain public summary/COMMIT linkage and producing executable.
   `--qualify` additionally re-verifies the actual saved public 192-cell
   publication, all 96 prefixes and ordered reductions. Raw directory and summary
   snapshots are retained/rechecked around later context checks and receipt
   publication; reading tracked JSON alone is not replay.

Each new receipt independently binds the admission-producing commit. The
unchanged public executable retains its previous producing commit/receipt.

## Cohort seal

Sealing is separate and requires a qualification file plus its exact reviewed
digest. That receipt is independently recomputed before generation. The sole
writable cohort location is the ignored local slot
`artifacts/work/feedback-budget-development-cohort-v6`, so transaction markers
do not dirty the attested source checkout. Tracked promotion is separate.

The sequence is STARTED → fixed generation → preregistration → SEALED. STARTED
is durable before the new generator call; the final seal is last. The existing
generator receives exactly count 12, seed 26090401, max_attempts 10000 and both
verified exclusion unions. The adapter never opens returned calibrations. It
retains acceptance order and the identity/solvability rejection log, not
witnesses, hardness profiles, proposal rows or search outcomes.

The preregistration binds the immutable contract, verified context, cohort and
generation manifest, 192 production-mode keys, 96 pairs and 48 four-arm blocks.
These differ from public-fixture and identity-only candidate keys; they are
materialized identities, **not executable authority**.

Independent verification rejects wrong domains, extra fields, numeric aliases,
altered definitions/identities, either identity exclusion, duplicate sources,
recipe drift and reordered/rekeyed schedules before generation. After closing
source/runtime/authority context, it regenerates the exact recipe and requires
byte-identical acceptance order/full seal reconstruction. Returned inputs are
immutable, with detached accessors and exact directory/file generations.

Storage requires exactly three private single-link regular files, complete
before/after closure and stable no-follow paths. Occupied slots cannot be
resumed, overwritten or adopted. Precommit failures retain STARTED/partial data
and best-effort FAILURE; uncertain final publication retains its directory
without a countermanding failure. This is local POSIX qualification, not remote
storage, reboot/power-loss or hostile same-user protection.

## Review candidate is not permission

`--candidate` verifies a seal and emits a closed `/authorization-candidate` to
stdout. It binds the seal path/bytes/digest, cohort, contract, schedule,
source/runtime context, exact output path and current no-follow parent identity
chain. `validate_candidate` rejects unknown/rehashed fields, changed bindings
and mismatched reviewed digests.

Scope is `REVIEW_ONLY_NOT_EXECUTABLE`. `execution_adapter_qualified` and
`authorization_consumption_implemented` remain false. There is no production run
command, executable authorization loader, permission toggle or consumption
registry. Old 384-cell and existing public adapters reject these new seals.

## Commands and evidence boundary

No-generation checks can run outside the checkout:

```sh
PYTHONPATH="$PWD/src" python3 -P -B scripts/feedback_budget_development_admission.py --self-test
```

For attestation use a clean committed tree, a fresh private empty cache prefix
outside the checkout and a new output filename. Do not edit source concurrently:

```sh
cache=$(mktemp -d "$HOME/.qmc-admission-XXXXXX")
PYTHONPATH="$PWD/src" PYTHONPYCACHEPREFIX="$cache" python3 -P -B scripts/feedback_budget_development_admission.py \
  --qualify \
  --public-run artifacts/work/feedback-budget-development-path-v6-20260910 \
  --public-summary artifacts/work/feedback-budget-development-path-v6-20260910.summary.json \
  --receipt artifacts/work/feedback-budget-admission-v6-YYYYMMDD.json
```

`--verify-qualification FILE --expected-digest DIGEST` recomputes the receipt in
another process with another fresh cache prefix.
`--seal-cohort --qualification FILE --expected-digest DIGEST` is a **separate
generation operation; it has not been invoked**. CLI availability and a passing
preflight do not instruct generation before review/qualification gates close.
`--verify-seal DIRECTORY` repeats that sealed recipe; `--candidate DIRECTORY
--output PATH` emits only a review candidate. There are no task/seed/budget/
method/provider/resume overrides or silently ignored arguments.

Positive seal/storage tests use explicitly mocked source context/generator with
handwritten test tasks, including unsolvable rows. They establish neither actual
generator acceptance nor execution readiness. The live qualification reports
`positive_seal_roundtrip_qualified: false` and zero development generation/run.
Eight domain negatives reject the identity contract/schedule, public fixture/
analysis, v5 preregistration and three old authorizations before generation.

The [dated review/qualification record](reviews/countdown_feedback_budget_admission_20260910.md)
retains the fresh-review P2, corrected ordering, targeted reviewer recheck,
985-test validation and independently verified admission receipt. The interrupted
pre-fix receipt is retained separately and was not promoted.

## Remaining gate

The [execution connector](countdown_feedback_budget_execution.md) now supplies
the one-shot consumption path and its separately recorded PUBLIC/synthetic
qualification. The admission-only candidate described above remains unchanged
and is NOT accepted as executable authority by that connector. Generate/seal the fixed fresh
cohort once, independently verify it, review its exact authorization candidate
and obtain explicit permission before one complete 192-cell development run.
No development signal, causal claim, quality gain or locked-128 authority follows.
