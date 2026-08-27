# Countdown Thompson dense-scale execution contract

## Purpose and current boundary

This document fixes the implementation and operational order for the sealed
Countdown Thompson dense terminal-value scale experiment. The scientific
question, cohort, one-factor matrix, analysis order, and handoff rule remain
authoritative in
[`strategy/countdown_thompson_dense_scale_dose_response_v5.md`](strategy/countdown_thompson_dense_scale_dose_response_v5.md).
This execution contract does not change them.

The sealed preregistration is
`docs/preregistrations/countdown_thompson_dense_scale_v5/preregistration.json`.
It contains 12 source-disjoint development tasks and an exact 384-cell schedule.
At the revision that adds this contract:

- no development proposal row, perturbation point, search record, terminal
  error, or exact-success outcome has been generated or opened;
- no dense-scale runner, analyzer, execution authorization, or production
  output path exists;
- the public eight-trace anchor qualification is implementation evidence only;
  and
- the reserved locked-128 cohort remains unopened and has no execution
  authority.

This contract is therefore a design boundary, not runnable production
authority. The next boundary is a separately reviewed runner/analyzer
implementation. Planning, authorization review, execution, and analysis stay
later and separate.

## Frozen authority

The implementation must reject drift from every value below before it can
produce an authorization candidate:

| Authority | Frozen value |
| --- | --- |
| bundle id | `countdown_thompson_dense_scale_12_seed_26082601/v1` |
| seal digest | `49f820692aa4f3551ca5634bdc89efe225fe05d1dc8acb8e814f231f3eea222f` |
| preregistration file SHA-256 | `bc68216a2f3e4809fd65914cd7a663d9d8f4ff74c3299de5e1ac36a04eecb547` |
| historical implementation base | `2bf4ce85947c39cc05a6f32a19576ea7d6e6790a` |
| preregistration merge revision | `03818e81d27e67488524ed3cb8f7eadcd32becdd` |
| schedule digest | `ea488a273282acecd7e4113ebc123daf4651b0b04f9d4e1f36264b7d4644aebd` |
| method manifest digest | `66195d7888efaf588f4eb050a7c9272a8159b5550e786afe1432f9e5df2beebd` |
| proposal manifest digest | `f9f0d84d7e8ae1cb344efc7d56a9db0adc038929658ef9a81259cf52fe3364f5` |
| budget manifest digest | `c41e5a817c261cd88281c52b8367ecca4f208b8f9e8fed0b6624deb84547e062` |
| runtime binding digest | `bfd7429ab09aa64365efccedec3da99082a93e6c54ab8f2d8b79cb98099504e2` |
| analysis manifest digest | `07303c90974612e9ac20fc285718170385dc9e13de5abb929a2038c2ebf70b02` |
| anchor qualification digest | `2b79d8c052aeef0a39209b41e0de5ff1c09a7b4b69234e7434b39da79bc7ca92` |
| cell count | `384` |
| scale order | `0, 1, 2, 4, 8, 16, 32, 64` |
| exploration-seed order | `7168, 7169, 7170, 7171` |
| provider calls | `0` |

The historical implementation base and PR #20 merge revision are provenance
anchors, not future runner authority. The implementation revision must descend
from the PR #20 merge and the eventual merge of this contract. A future runner
authorization must separately bind the exact reviewed runner revision, the
later authorization revision, and the execution HEAD. Those revisions may not
replace any sealed digest above.

## Domain separation

Dense-scale authority must not be represented as diagnostic, canary, or locked
authority merely to reuse existing code.

- Production objects use new dense-scale schemas and the scope
  `one_exact_complete_384_cell_dense_scale_development_run`.
- The execution mode is `authorized_dense_scale_development`.
- The diagnostic 240-cell and canary 936-cell authorization schemas are always
  rejected by the dense-scale loader before bundle or output access.
- Dense-scale authorization is always rejected by the diagnostic and canary
  production loaders.
- V2 or v3 search traces on a development task are unregistered extra cells and
  invalidate the attempt. V2 and v3 occur only in the public anchor
  qualification.
- A nondiagnostic full-shaped fixture has its own bundle id, schema, scope,
  design digest, tasks, and execution mode. It can never enter the production
  loader or a production analysis decision.

The existing regular-file v2r3 protocol may supply publication mechanics, but
not dense-scale semantics. Reuse must occur through a method-neutral core or a
dense-specific wrapper with closed schemas. Renaming dense fields to legacy
`diagnostic_*` fields is prohibited. Existing diagnostic and canary receipts
must continue to verify byte-identically.

## Source-checkout and runtime authority

The future runner and analyzer are source-checkout tools. Their authority
comes from a clean Git checkout, exact source bytes, explicit import origins,
and recorded Git ancestry, not from an installed wheel or console script.
Every operational invocation must:

1. start in a clean checkout of the reviewed revision;
2. use `PYTHONPATH=src python -m ...`; and
3. pass `--repository-root .` explicitly.

The implementation PR must publish the exact protected source-file sets for
the runner and analyzer. These sets must include every executed package
initializer, search module, manifest module, publication module, runner leaf,
and analyzer leaf. Imported modules must resolve inside the checkout. Every
protected path must be a tracked, non-symlink regular blob whose descriptor-read
bytes match both Git and its attestation receipt.

The runner rechecks its source closure before and after planning preflight,
before durable `STARTED`, and before final commit. The analyzer checks the
historical runner receipts and independently closes its current replay source
set. A missing initializer, dirty checkout, import-origin drift, symlink,
receipt mismatch, Git ancestry mismatch, or already-open timestamp bytecode
cache fails closed.

The live runtime must reproduce the sealed CPython 3.13.13, arm64, CPU,
binary64 IID and search conformance bindings. General package importability is
not runtime qualification. A mismatch is `NOT_RUN` before `STARTED`, or
`INVALID` after it; it is never a failed development cell.

## Mandatory outcome-blind order

The following are separate review boundaries. They must not be collapsed into
one unreviewed command sequence.

1. Merge this design-only execution contract.
2. Implement the runner, analyzer, full-shaped nondiagnostic fixture, tests,
   documentation, and validation wiring without creating an authorization
   candidate or opening a development outcome.
3. Fresh-review and merge that implementation.
4. From a clean checkout of the merged implementation, run planning only and
   write one authorization candidate to a new tracked path.
5. Review the byte-identical authorization candidate in a separate,
   authorization-only PR and merge it without changing its bytes.
6. From a clean descendant checkout on the reviewed host/filesystem identity
   epoch, confirm the exact authorization digest and merged authorization
   revision, then consume that authority in one run attempt.
7. Independently analyze the committed artifact and publish one no-overwrite
   summary outside the raw artifact and sealed preregistration.
8. Preserve the complete result, including a null, adverse, invalid, or
   ambiguous result, before proposing any new experiment.

No stage grants permission for a later stage. In particular, a passing
implementation fixture does not grant planning authority, a planned candidate
does not grant execution authority, and integrity `PASS` does not grant a
scientific or locked-cohort claim.

## Runner/analyzer implementation boundary

The implementation PR must add dedicated public modules named
`countdown_thompson_dense_scale_runner` and
`countdown_thompson_dense_scale_analysis`. It must not create the real
authorization candidate or invoke the production `--run` or `--analyze`
paths.

### Required public surfaces

The runner must expose mutually exclusive `--self-test`,
`--full-shape-fixture`, `--plan`, and `--run` modes. The analyzer must expose
mutually exclusive `--self-test`, `--analyze-full-shape-fixture`, and
`--analyze-v2r3` modes. Production planning, running, and analysis require an
explicit repository root and refuse ambiguous or incomplete CLI combinations
with canonical status objects rather than unstructured tracebacks.

`--self-test` must not open the sealed preregistration, any development task,
or any prior outcome artifact. Repository validation may separately verify
the sealed preregistration bytes, but verification is not search execution.

The full-shaped fixture must exercise the same 384-record execution,
publication, verification, and two-stage replay core using only fixed public
nondiagnostic tasks. It must carry separate authority at every public
boundary. Its terminal values are plumbing evidence only and cannot produce a
dense-scale handoff status.

### Anchor-qualification barrier

Every production environment must reproduce the four sealed receipt rows,
which execute exactly eight public traces:

```text
iid:   v2 versus v5 scale 0; v3 versus v5 scale 1
sobol: v2 versus v5 scale 0; v3 versus v5 scale 1
```

The task is the public `(1,2,3,4,5,6) -> 720` fixture, the exploration seed is
`7168`, and the budget is `dense_scale_anchor_fixture_verifier3`. Each trace
must pass canonical validation and two-stage byte replay before projection.
The exact authority-trace, scaled-trace, and projection digests must equal the
sealed receipts. Raw qualification traces are never persisted.

The barrier appears three times:

1. planning reproduces it and binds the canonical receipt into the candidate;
2. running reproduces it immediately before durable `STARTED`, before any
   development task is executed, and rechecks the same receipt before commit;
3. analysis reproduces it before opening the development bundle or run records.

Qualification mismatch before `STARTED` is `NOT_RUN`. Mismatch after
`STARTED`, or disagreement between planned, run, and independently reproduced
receipts, is `INVALID`. It cannot become a development observation. The
qualification grants no v2/v3 development authority and no auxiliary controls.

### Exact run collective

After durable `STARTED`, the production action executes the sealed schedule in
its exact task, scale, then seed order. Each record closes:

- the exact cell id and complete sealed cell identity;
- task, source-multiset, proposal, method, scale, seed, budget, runtime, bundle,
  schedule, source-build, authorization, and output-parent-binding identities;
- canonical trace bytes and trace SHA-256;
- every work-axis charge and final budget snapshot;
- provider-call count zero; and
- stage-one generative validation plus stage-two fresh byte-identical replay.

The runner emits no per-cell terminal error, exact-success value, scale
aggregate, winner, or handoff decision to stdout. Records remain inside an
uncommitted staging collective until all 384 cells close. Missing, duplicate,
extra, reordered, replay-invalid, budget-invalid, or non-primary-guard-bound
cells invalidate the entire attempt. No partial aggregate is emitted.

There is no outcome-aware retry, task replacement, scale or seed addition,
early stopping, or continuation from a partial collective. A durable attempt
marker consumes the authorization. An interruption or failure after
`STARTED` is terminal and the same authorization is never executed again.
A pre-`STARTED` refusal may reuse the same exact authorization only when the
protocol positively proves that no durable attempt marker or development
outcome exists and every reviewed byte and namespace identity is unchanged.
Observation uncertainty never counts as absence; otherwise a new planning and
review cycle is required.

### Publication substrate

Production uses only `publication_backend=posix_regular_files/v2r3` and
`artifact_layout=flat_commit_root/v2r3`. The output commit file is outside the
repository and outside the sealed preregistration. Planning captures one
canonical root-to-parent `(st_dev, st_ino)` binding; reviewed loading freezes
that stored binding and never regenerates expected identity from a changed live
path.

The parent must already exist. The commit file and every reserved sidecar must
be absent. Fixed names are acquired with descriptor-relative no-follow
`openat(O_EXCL)`, each file and parent durability barrier is proven, and the
commit file is published last. Binding drift, aliasing, mount drift, foreign
entries, rollback uncertainty, or post-publication identity uncertainty is
`PUBLICATION_STATE_AMBIGUOUS`, not `NOT_RUN`, `INVALID`, or success.

The authority is local to the reviewed host, filesystem identity epoch, mount
interpretation, and process namespace. NFS, SMB, FUSE, reboot, cross-host
execution, mount-namespace drift, and device/inode ABA remain outside it.

## Planning only

Planning may verify the sealed preregistration, reproduce the public anchor
qualification, attest the clean implementation, and inspect the future output
namespace. It must execute zero development cells and write no raw run
artifact. Its only successful status is
`PREOUTCOME_AUTHORIZATION_CANDIDATE_WRITTEN`.

The future command shape is fixed as:

```bash
PYTHONPATH=src python -m \
  qmc_bmgs.experiments.countdown_thompson_dense_scale_runner \
  --plan docs/preregistrations/countdown_thompson_dense_scale_v5 \
  --output /absolute/outside/repository/dense-scale-v5.commit.json \
  --authorization-out \
    docs/preregistrations/countdown_thompson_dense_scale_v5_execution_authorization.json \
  --repository-root .
```

This command is documentary until the implementation PR is merged and
reviewed. It must not be invoked from the design-only revision.

## Authorization schema and separate review

The production authorization schema is
`qmc-bmgs-countdown-thompson-dense-scale-execution-authorization/v1`. Its scope
is exactly `one_exact_complete_384_cell_dense_scale_development_run`. The
strict loader accepts exactly these top-level fields and rejects missing or
unknown fields before bundle or output access:

```text
analysis_manifest_digest            anchor_qualification
anchor_qualification_digest         artifact_id
artifact_layout                     authorization_scope
budget_manifest_digest              bundle_id
cell_count                          claim_boundary
dense_scale_seal_digest             deterministic_digest
method_manifest_digest              output_parent_binding
output_parent_binding_digest        output_path
output_path_digest                  preregistration_file_sha256
proposal_manifest_digest            publication_backend
publication_environment_requirements
requires_explicit_digest_confirmation
runner_build_attestation            runtime_binding_digest
runtime_qualification               runtime_qualification_digest
schedule_digest                     schema_version
```

Nested parent-binding, environment-requirements, build-attestation,
qualification, and runtime objects each have their own closed schema and
deterministic digest. Canonical bytes, not Python mapping equality or numeric
coercion, decide identity.

The authorization-only PR contains the single new candidate file and no code,
documentation, sealed-bundle, or output changes. Review must establish:

- every frozen digest and the exact 384-cell scope;
- canonical JSON and complete nested digest closure;
- the exact output path bytes and reviewed parent binding;
- the exact runner revision, protected source receipts, runtime receipt, and
  public anchor-qualification receipt;
- local POSIX publication assumptions on the execution host/filesystem epoch;
- zero v2/v3 development cells and zero provider calls; and
- the claim boundary: one development run only, with no confirmation,
  superiority, QMC, or locked-128 authority.

The merged authorization commit OID and 64-character lowercase authorization
digest must be recorded. The authorization revision strictly descends from
the reviewed runner revision. Execution HEAD strictly descends from the
authorization revision, and the authorization bytes at both revisions are
identical.

## One authorized run attempt

The eventual run command must explicitly provide the sealed preregistration,
absolute output path, reviewed authorization path, exact authorization digest,
full merged authorization revision, and repository root. The loader verifies
all of them before output access. No environment variable, newest-file rule,
branch name, tag, abbreviated OID, or interactive selection may supply
authority.

After separate authorization review, its fixed command shape is:

```bash
PYTHONPATH=src python -m \
  qmc_bmgs.experiments.countdown_thompson_dense_scale_runner \
  --run docs/preregistrations/countdown_thompson_dense_scale_v5 \
  --output /absolute/outside/repository/dense-scale-v5.commit.json \
  --authorization-file \
    docs/preregistrations/countdown_thompson_dense_scale_v5_execution_authorization.json \
  --authorization-digest <64-lowercase-hex> \
  --authorization-revision <40-lowercase-hex-merged-commit> \
  --repository-root .
```

The placeholders must be replaced by the reviewed full values. This command is
not authorized by the design or implementation revisions.

The public status taxonomy remains distinct:

- `NOT_RUN`: no durable `STARTED` and no development cell executed;
- `INVALID`: authority was spent or a cell/outcome existed, but the exact
  collective or a required gate failed;
- `PUBLICATION_STATE_AMBIGUOUS`: storage identity or durability cannot be
  proven; and
- `COMMITTED`: one exact 384-cell collective closed and the commit receipt is
  durable.

`COMMITTED` is not an analysis result. The runner never selects a scale and
never reports readiness.

## Independent analysis and result opening

The analyzer receives the reviewed authorization as an external input; it does
not trust an embedded copy. Before opening development material it reproduces
the public anchor qualification. It then independently verifies authorization
bytes and Git ancestry, historical runner receipts, its current source closure,
the sealed preregistration, the complete v2r3 collective, and all 384 records.
It reconstructs every search and performs stage-one plus fresh stage-two replay
with zero provider calls.

After one durable `COMMITTED` run, its fixed command shape is:

```bash
PYTHONPATH=src python -m \
  qmc_bmgs.experiments.countdown_thompson_dense_scale_analysis \
  --analyze-v2r3 \
    /absolute/outside/repository/dense-scale-v5.commit.json \
  --bundle docs/preregistrations/countdown_thompson_dense_scale_v5 \
  --authorization-file \
    docs/preregistrations/countdown_thompson_dense_scale_v5_execution_authorization.json \
  --authorization-digest <64-lowercase-hex> \
  --authorization-revision <40-lowercase-hex-merged-commit> \
  --output /absolute/outside/repository/dense-scale-v5.summary.json \
  --repository-root .
```

Analysis is not authorized before the exact committed collective exists.

The analyzer enforces the sealed five-stage order:

1. reproduce the nondiagnostic anchor qualification without development
   material;
2. integrity, provenance, exact-cell and budget closure, provider-call zero,
   and two-stage replay;
3. common-prefix mechanism reductions through the first action divergence,
   using an outcome-redacted view and making no terminal-error or success
   branch;
4. terminal-error reductions using exact integer vectors and reduced rational
   means and medians;
5. exact-success vectors, paired gains/losses, the preregistered scale
   selection, and the development handoff rule.

Stages three through five begin only after exact closure in stage two.

The mechanism helper must be separately tested to reject access to terminal
success and error fields. Replay may validate the complete trace in the prior
integrity stage, but no outcome-dependent filtering, ordering, retry, or
mechanism choice is permitted.

The summary contains every preregistered per-scale field in fixed task/seed
order, the complete dose response, the selected `s*`, and exactly one terminal
decision:

- `READY_TO_PREREGISTER_SOURCE_DISJOINT_CONFIRMATION`; or
- `STOP_REPAIR_NO_LOCKED_128_RUN`.

The first means only that a new source-disjoint confirmation design may be
proposed and reviewed. It is not confirmation and does not authorize the
locked 128. An integrity, qualification, replay, publication, or analysis
failure emits neither decision.

The summary is published atomically with no overwrite, outside the raw run
artifact and preregistration. The analyzer revalidates authorization, source,
bundle, artifact, and summary identities around the durability barrier. A
summary must never be emitted from partial records or an ambiguous collective.

## Outcome-blind implementation gate

Before an authorization candidate can be planned, the implementation PR must
demonstrate all of the following without opening a development outcome:

- exact self-tests that cannot open the sealed development paths;
- an independently authorized 384-cell nondiagnostic full-shaped run and
  analyzer replay;
- fresh reproduction of all eight public qualification traces and four sealed
  projection receipts;
- production-loader rejection of fixture, diagnostic, canary, and malformed
  authorities before sealed or output access;
- missing, duplicate, extra, reordered, v2/v3-development, budget-invalid,
  provider-call, replay, and source-drift failures closing the whole fixture;
- durable one-shot attempt and regular-file v2r3 race/adversarial tests;
- analyzer enforcement of the fixed five-stage order and terminal-field
  barrier; and
- full repository validation with no provider call and no development result.

The exact implementation HEAD then receives a fresh adversarial review. Any
code or contract change after that review requires another exact-head review
before planning.

## Evidence retention and claim boundary

Raw attempts, committed run files, and summaries remain outside Git. A later
observation PR may commit canonical manifests, hashes, validation receipts,
commands, environment provenance, and compact representative evidence, but not
secrets or raw run bulk. Null, adverse, invalid, and ambiguous outcomes are
retained rather than replaced.

This experiment may report a causal trajectory response to the exact frozen
terminal-value scale intervention on this development cohort, under matched
tasks, IID streams, and budgets. It may not establish general method
superiority, task transfer, statistical significance, QMC benefit, Bayesian
posterior validity, natural-language generalization, or locked-cohort
performance.

Integrity `PASS` means only that authority, provenance, schedule, budget, and
replay closed. It is not a positive scientific result.
