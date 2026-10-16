# v7 fixed PUBLIC pipeline: review and actual qualification

Date: 2026-09-13 (Asia/Tokyo). Corrected producing implementation:
`ead82d677c4e038d8d2f310b04fe7dc3adb5eb9b`.

Scope: the [PUBLIC-only v7 pipeline](../countdown_feedback_budget_replication_public_pipeline.md),
using the already fixed 1,024-cell schedule. No new replication cohort was
generated, admitted or executed. The search implementation, v6 pipeline,
historical evidence, frozen v7 design/checker/contract and PUBLIC identity file
remain byte-unchanged. Only the new kernel, analysis, publication, runner, tests
and their documentation were implemented here.

## Fresh reviewer output

Full review: `356d090602fbf0392b4052e6793ea0f7fba340dd` to
`dc540e5ae0740130a4168a090b3f2a3774391219`. A separate complete local clone was
used without parent conversation history. Fork-review temporarily hid only
that clone's project-local `AGENTS.md`; the live checkout and user-level files
were untouched. This is best-effort fresh-eye review, not literal context
erasure. The clone was thawed and checked clean immediately after each review.

The outside review, kept separate from operator interpretation:

> One actionable P2: run descriptor preflight before baseline search.
> `run()` called `qualify_baseline()` / `q.run_matrix()` before the publisher
> checked the 1,152-descriptor requirement. With an insufficient limit, the
> 32 baseline traces could run before refusal, contrary to the documented
> no-search preflight. Move the check before baseline qualification and test
> the actual runner boundary.
>
> A mocked limit of 256 reproduced the ordering: baseline call, then descriptor
> preflight, then `PublicationError`. No output was created and no actual
> search was performed by the mock reproduction. Eighteen selected pure
> metadata/arithmetic tests passed. No other actionable P1/P2 was found in
> the reviewed six-file scope. No actual search/replay, source-qualified run,
> full validator or publication writes were performed by the reviewer.

Targeted recheck of `dc540e5..ead82d6`, separately labeled from the full review:

> P2 resolved. The runner checks descriptor limits before source/runtime
> qualification and baseline search; the publisher's check remains.
> A mocked limit of 256 now rejects immediately, with zero admission, runtime,
> baseline, input-construction, publication, search or replay calls and no
> output directory. No remaining or new actionable issue was found in this
> small delta. No actual search/replay, full validator or publication writes
> were performed by this recheck.

## Stateful annotation and validation

The P2 was actionable. `ead82d6` moves the resource check to the runner entrance
and adds a runner-level regression, while retaining the publisher check. No
system limit is raised. Three focused descriptor/summary-bound tests passed
in 0.176 seconds. The targeted reviewer recheck confirms this boundary fix,
not full pipeline qualification; the latter is separately executed below.

Preserved development attempts:

- Initial focused suite: 45 tests in 218.417 seconds, 41 passes and four test
  errors. A test-only replacement had changed literal seed `8192` to `81024`
  in four lookups. These were corrected; production seeds never changed. The
  fixture setup had already executed/replayed the fixed PUBLIC matrix, but
  this failing test attempt is not a qualification receipt.
- The first full validation, at `dc540e5`, was deliberately interrupted to
  apply the P2 fix (exit 130). It is neither a completed nor a passing
  validation. No durable source-qualified PUBLIC invocation had begun.
- The corrected full validation includes **48 passing new-path tests**. These
  cover all-cell identity closure before replay, malformed late cells, exact
  replay and prefixes, outcome-redacted reduction order, exact 64-task screen
  arithmetic, descriptor gating and new-domain publication/failure boundaries.
  Mock storage records establish storage behavior, not numerical validity or
  production admission.

Full validation at the corrected producing commit:

```sh
PYTHONPATH="$PWD/src" \
PYTHONPYCACHEPREFIX=/private/tmp/qmc-v7-pipeline-fixed-validation-pyc.0qp6sM \
python3 -B scripts/validate.py
```

Result: **1,122 tests passed in 773.005 seconds, no skips**. Compilation, Ruff,
artifact/provenance checks, outside-checkout CLI self-tests and the final
historical v5 seal verification also passed. Final output:
`repository validation: PASS`, exit 0. The duration is the unittest phase,
not total validator wall time. Ruff formatting and `git diff --check` passed.
No hosted CI, cross-host behavior or physical power-loss recovery is claimed.

## Actual source-qualified execution and independent verification

Three separate processes used the clean corrected commit, absolute `src` on
`PYTHONPATH`, `python3 -P -B`, and a fresh empty owned mode-0700 cache prefix for
each process. CPython 3.13.13 / Darwin arm64 / CPU binary64 matched the frozen
runtime requirement. Each process independently requalified source/runtime and
reproduced the same 32 component/anchor baseline traces. Old receipt bytes alone
did not admit execution. The descriptor soft limit was 1,048,575, above 1,152.

Let `OUTPUT` be the absolute repository path to
`artifacts/work/countdown-feedback-budget-v7-public-pipeline-20260913-a`, and
`SUMMARY` its sibling `countdown-feedback-budget-v7-public-pipeline-20260913-a.summary.json`.
These paths are now occupied and must not be reused for execution.

| Operation | Fresh cache prefix | Result |
| --- | --- | --- |
| `--run-public OUTPUT` | `/private/tmp/qmc-v7-public-run-pyc.TwIAMp` | `REPLICATION_PUBLIC_FIXTURE_COMMITTED`, exit 0 |
| `--analyze-public OUTPUT --summary SUMMARY` | `/private/tmp/qmc-v7-public-analyze-pyc.8jqx7B` | `REPLICATION_PUBLIC_FIXTURE_INDEPENDENT_ANALYSIS_PASS`, exit 0 |
| `--verify-public OUTPUT --summary SUMMARY` | `/private/tmp/qmc-v7-public-verify-pyc.tPpoDk` | Same independently recomputed summary digest, exit 0 |

Every operation used `scripts/run_feedback_budget_replication_fixture.py`.
The last two operations reread the saved publication, replayed all cells,
recomputed the ordered reduction and rechecked source/runtime/storage closure.
The final operation required exact canonical-byte equality with the saved
summary. These are independent checks of the same data, not three experiments.

Verified shape and integrity:

- 1,024 cells and 1,024 two-stage replay receipts; provider calls 0.
- 512 full accepted-event budget-prefix/completion checks, all passing.
  Terminal counts were 2 to 4 for 495 pairs, 2 to 5 for 16, and 1 to 4 for one.
  Every unfinished trajectory at the low-budget boundary completed first after
  continuation; each high-budget trace contained at least three terminals.
- 512 cross-scale mechanism pairs and 256 four-arm extension blocks, reduced
  before terminal-error and exact-success statistics.
- 64 task-definition rows, four seeds per definition, 256 cells per arm;
  64 leave-one-definition-out rows with 252 blocks each. All 16 binary success
  patterns are retained, including seven prefix-forbidden zero rows.
- 1,027 closed publication files, 136,245,483 bytes. The commit binds all 1,024
  cell byte hashes and the STARTED/RECEIPT files. Raw cells remain local/ignored.
- `public_pipeline_qualified=true`, `fixture_is_replication_evidence=false`,
  `scientific_decision=null`, replication cells 0; production admission,
  replication authorization and locked-128 authorization all remain false.

The fixed PUBLIC identity file contains 65 definitions on **one source
multiset**: the 64 full-shape targets plus the existing target-720 component
task. The executed full shape uses `[1,2,3,4,5,6]` with targets 1 through 64,
seeds 8192 through 8195, scales 0/16 and budgets 256/512. No additional arithmetic
fixture definition, new source, task generator, cohort seal, provider or arbitrary
override was used for this qualified run.

## Retained PUBLIC outcomes, not performance evidence

The plumbing passed, but the PUBLIC numerical screen **did not pass**. It was
not tuned or reinterpreted as a replication result. These counts are over
target definitions on one shared input source, not 64 independent problems.
The paired contrasts compare scale 16 with scale 0 at the same budget; they are
not losses caused by increasing the budget within one scale.

| Budget | Scale 0 exact / 256 | Scale 16 exact / 256 | Paired rescues / lost exact | Terminal-error wins / ties / losses |
| --- | --- | --- | --- | --- |
| 256 | 70 | 74 | 12 / 8 | 23 / 215 / 18 |
| 512 | 128 | 136 | 32 / 24 | 43 / 174 / 39 |

The high-budget net uplift is 8/256 and interaction is 4/256, both below the
required integer numerator 11. There are 24 high-budget lost exact successes,
so the no-loss gate also fails. High-budget rescues span 25 definitions, which
is not the same quantity as 55 versus 57 definitions solved by any seed. All
per-cell vectors, first hits, paired losses, mechanism opportunity bins, task
rows and leave-one-out rows are retained in the full summary. No QMC superiority,
causal effect, population inference or successful replication follows.

## Tracked artifacts and reproducibility anchors

The tracked files are byte-identical copies, not edited or regenerated summaries:

- [COMMIT](../qualifications/countdown_feedback_budget_v7_public_pipeline_20260913.commit.json):
  146,571 bytes; SHA-256
  `7d4594abca5a00a5be25168e807d48b8ade195c6c90c1155829edaae7d40bce9`;
  deterministic digest
  `a436f152709121a2426c483044b0828f587dfa6fedbbb39f7ec19b30b4f4d51f`.
- [Independent summary](../qualifications/countdown_feedback_budget_v7_public_pipeline_20260913.summary.json):
  3,880,757 bytes; SHA-256
  `0c2bef6632aae6410eae5db7423d13482e6775622cfcce355490bbff96105432`;
  deterministic digest
  `a0e48b17aeb6a2bed9075d950848a446685a19da7e4b9bf770f6cd4287ce9978`.

Further raw anchors: RECEIPT SHA-256
`21bc7e120e261895831f9ffd340b463ba8913cffafc920cbb9c0532aa18fcd8f`,
STARTED SHA-256
`68b2248413f5888c0689a2e6e3b540e507340e59528f6f7381da4836437f189e`,
and run-binding digest
`c0315e7606c4c7a4c3534cbec8cdffe74252117be75e1d86b29eba9df64d3ab6`.
The source receipt binds 23 v7 pipeline/fixed-input files in addition to the
unchanged protected search-source closure. The fixed PUBLIC schedule digest
remains `1b1e13515e2036d764c6e05d023b61ed047af1e7f9615799f2a1b18e4a11e91b`.
Replay still requires the local raw publication, not the tracked summary alone.

Ignored console captures share the prefix
`artifacts/work/feedback-budget-v7-public-pipeline-20260913.`:

| Suffix | SHA-256 |
| --- | --- |
| `initial-focused.captured.log` | `4396e140c51f55f71ed9236b3d7f0608f6a32389d7b4812e7beb6b14e2b056ce` |
| `interrupted-validation.captured.log` | `1d2c06061c0ef3e7020e83800ba5c114a6dda7b70d14207a4e73704e2b579c7e` |
| `validation.captured.log` | `da2747549a2b10b9cf6dcb57809265e5da5911569e2bdcc071681a170eab00a8` |
| `operations.captured.log` | `6748053837357ef20f96ff7d8ab79bf98efc9ff9e7ef1a57a4df9cade479a616` |

The successful validator capture is 236,573 bytes and retains the complete
returned output without detected truncation markers; the operations capture
is 3,636 bytes. These are console captures, not scientific traces. The later
changes only promote these artifacts and add documentation; producing source
bytes are not changed or historical evidence rewritten.

## Remaining gate

This completes the fixed PUBLIC execution/replay/analysis/storage path. It does
not implement the new production-domain admission and one-shot consumption
path, qualify its failure handling, close every fixture variant for that later
implementation, authorize cohort generation, seal a 64-source cohort or grant
exact-candidate execution permission. Those remain separate next steps under
the frozen v7 contract. No old consumed study claim was cleared or retried.
