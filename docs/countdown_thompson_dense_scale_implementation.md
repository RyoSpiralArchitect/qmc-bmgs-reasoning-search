# Dense-scale runner and independent analyzer

This is the implementation lane for the
[merged execution contract](countdown_thompson_dense_scale_execution_contract.md).
It does not grant planning, development execution, confirmation, or locked-128
authority. Production outcomes and an actual authorization candidate remain
unopened/uncreated during implementation validation.

## Responsibility boundaries

| Module | Responsibility |
| --- | --- |
| `countdown_thompson_dense_scale_core` | Public qualification, immutable inputs, source/runtime receipts, typed v5 cells, exact execution and fresh replay |
| `countdown_thompson_dense_scale_publication` | Separate dense/fixture schemas, durable one-shot lifecycle, exact 384-record closure, independent immutable-byte verification, no-overwrite summary |
| `countdown_thompson_dense_scale_runner` | Closed authorization loading, Git ancestry, planning-only, barrier orchestration, public fixture |
| `countdown_thompson_dense_scale_analysis` | External authorization, all-cell replay, outcome-redacted mechanism stage, errors, successes, preregistered handoff |

The publisher constructs the run manifest from its frozen external authority,
schedule and record bytes. An action cannot supply its own success count,
record count, ordering or manifest hash. Every record binds the publication,
authorization, source and runtime context through its run-binding digest.

The old diagnostic/canary public production loaders and analyzers are not used
as dense-scale authority. Their source files and the six sealed search files
remain unchanged. Low-level regular-file publication mechanics are reused.

## Public-only inputs and source provenance

The new `src/qmc_bmgs/data/countdown_thompson_dense_scale_public_contract_v1.json`
contains only public analysis/method/budget/proposal/runtime manifests and the
public anchor fixture. It contains no development task rows, development
schedule rows, proposal values, perturbation values or search outcomes.
Its exact SHA-256 is
`0d4962c53c9559385c224b68b5713e675c29692c19d1dda20f85726b0fc2de6f`.

The public qualification therefore reproduces eight traces and four sealed
projection receipts without first opening the sealed development bundle.
Raw qualification traces are not persisted. Its receipt digest remains
`2b79d8c052aeef0a39209b41e0de5ff1c09a7b4b69234e7434b39da79bc7ca92`.

Both runner and analyzer use the same exact, conservative protected-file set:
`PROTECTED_SOURCE_PATHS` in
[`countdown_thompson_dense_scale_core.py`](../src/qmc_bmgs/experiments/countdown_thompson_dense_scale_core.py).
That literal tuple includes all package Python source files, all package
initializers and the public contract JSON; it is not populated by discovery at
runtime. Loaded module names must resolve to their exact corresponding source
files, not merely somewhere under the checkout. Every protected file must be
a tracked regular Git blob with descriptor-read bytes equal to the reviewed
revision and current clean HEAD. The six search-source receipts must also
match the frozen preregistration's runtime binding.

Operational invocations require `-P -B` and a newly created, empty, owner-only
bytecode-cache namespace. Source/cache writers must be quiescent from fresh
cache creation and process startup through the final barrier. These receipts
check current Git/source bytes and observable loader/cache policy; they do not
retrospectively measure every loaded code object or detect transient
pre-attestation replacement followed by restoration. That case and arbitrary
code-object mutation are outside the authority model, not detected attacks.
Publication retains the reviewed local POSIX/identity-epoch limits;
it does not claim NFS, SMB, FUSE, reboot, mount-namespace or device/inode ABA
safety.

The final summary barrier also compares directory generations along the whole
lexical output ancestry. Even unrelated sibling creation/deletion in a shared
OS temporary directory can conservatively invalidate publication and trigger
exact summary rollback. Use an output namespace with quiescent ancestors; the
full-shaped integration test therefore uses a disposable sibling of the
checkout, not the shared OS temporary directory. It does not relax the writer's
generation checks or retry a production attempt.

## Exact error summaries

Stage four computes two deterministic views of the already required integer
error vectors, before stage five reads exact success:

- `minimum_terminal_absolute_error_summary`: reduced-rational mean and median
  of all 48 task/seed minimum errors for that scale, with equal cell weight;
- `terminal_absolute_error_summaries`: 48 reduced-rational mean/median pairs in
  the same frozen task/seed order, each using that cell's complete nonempty
  terminal-error vector.

Each rational is stored as integer `numerator` and positive `denominator`.
There is no pooling of terminal observations across cells, outcome-based row
filtering, or floating-point error aggregation. These views supplement the
preregistered raw vectors and counts; they do not change scale selection or the
handoff rule. The frozen analysis manifest and its digest remain unchanged.

## Fixed 384-cell public fixture

The fixture is separate at every public authority boundary:

- bundle: `countdown_thompson_dense_scale_nondiagnostic_full_shape_384/v1`;
- inputs: `(1,2,3,4,5,6)`, targets `1` through `12` in that order;
- scale order: `0,1,2,4,8,16,32,64`;
- seed order: `7168,7169,7170,7171`;
- proposal: the frozen heuristic; methods: IID v5 only; budget: the same
  seven-axis `score256` profile;
- design digest: `2c7b2831a59872560e0310339ea21b7a6cc84ff513eba30f204562b980518d0c`;
- schedule digest: `d68dd802e683ebcf81f3ce78c3fb297e8c1ecf8ed9059ae1cc869d25845d9d1e`.

These inputs and hashes were fixed before executing fixture outcomes. They
exercise the same cell, publication and independent replay paths. Repeated
source multisets within this synthetic fixture are intentional; it is not a
source-disjoint scientific cohort. Its source multiset is the public anchor's,
which is already disjoint from all sealed development sources.

The fixture creates its own external authorization, not the real production
candidate. The fixture authorization's review revision denotes the clean
source-review epoch, not a merged authorization-only Git commit. Production
authority cannot use that interpretation. A fixture summary contains plumbing
evidence and cannot emit either production handoff decision.

From a clean committed checkout, with separate existing output and authority
directories outside the repository:

```bash
PYTHONPYCACHEPREFIX="$(mktemp -d)" PYTHONPATH=src python -P -B -m \
  qmc_bmgs.experiments.countdown_thompson_dense_scale_runner \
  --full-shape-fixture \
  --output /absolute/fixture/raw/dense-fixture.commit.json \
  --authorization-out /absolute/fixture/authority/fixture-authorization.json \
  --repository-root .
```

Use the exact fixture authorization digest and source revision returned by
that run to independently analyze it:

```bash
PYTHONPYCACHEPREFIX="$(mktemp -d)" PYTHONPATH=src python -P -B -m \
  qmc_bmgs.experiments.countdown_thompson_dense_scale_analysis \
  --analyze-full-shape-fixture /absolute/fixture/raw/dense-fixture.commit.json \
  --authorization-file /absolute/fixture/authority/fixture-authorization.json \
  --authorization-digest <64-lowercase-hex-fixture-digest> \
  --authorization-revision <40-lowercase-hex-source-revision> \
  --output /absolute/fixture/dense-fixture.summary.json \
  --repository-root .
```

Neither command accepts a production bundle as a fixture substitute. Files are
not overwritten. A spent `NOT_RUN` attempt cannot retry; storage ambiguity is
not converted into reusable authority.

## Validation and the next review boundary

The runner and analyzer each expose `--self-test` without requiring a bundle,
authorization, repository root or output path. Their self-tests are wired into
`scripts/validate.py`; repository tests separately exercise fixed public cells,
adversarial authority/publication cases and reduction invariants. The sealed
manifest verifier remains a separate read-only check, not a search run.
The validation harness supplies a private temporary namespace to every child
command, so unrelated shared-OS-temp churn does not preempt the deliberately
injected failure in legacy publication tests. Their assertions and source
bytes are unchanged.
The namespace uses a short name under the user's home by default; set
`QMC_BMGS_VALIDATION_TEMP_PARENT` to another short, writable, quiescent parent
outside the checkout if needed. An upfront local Unix-socket probe checks the
longest existing socket-fixture path shape before the expensive tests start.
Unsupported or overlong paths fail explicitly; socket tests are not skipped,
and a shared temporary directory is not silently substituted.

The full-shaped test runs from a clean disposable clone, rejects any sealed
preregistration open or production planning/loading call, then analyzes all
384 committed public cells from a later source-identical Git revision. Summary
publication deliberately shares the raw parent to exercise the authority
barriers across its own directory update.

Two initial public-fixture integration attempts committed the raw collective
but failed final summary publication. A search-free probe isolated generation
changes in the shared OS temporary ancestor. Those attempts were not counted
as passes: the test namespace was isolated, and a deterministic sibling-churn
regression retains fail-closed summary quarantine. A separate regression checks
that raw-authority ambiguity is not downgraded after exact summary rollback.

An implementation fixture or green tests do not authorize `--plan`. First
finish the full-shaped fixture, independently replay it, complete exact-head
fresh adversarial review and merge the implementation. Only then may a
separate authorized planning step create a candidate for an authorization-only
PR. No development execution occurs in this implementation lane.
