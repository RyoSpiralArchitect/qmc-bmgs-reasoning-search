# Countdown Thompson diagnostic execution contract

## Purpose and claim boundary

This document fixes the operational order for the outcome-blind Countdown
Thompson diagnostic. The preregistered cohort, schedule, metrics, and gates
remain authoritative in
[`countdown_thompson_diagnostic_contract.md`](countdown_thompson_diagnostic_contract.md).
This execution contract does not change them.

The sealed bundle is
`docs/preregistrations/countdown_thompson_diagnostic_v1`, with seal digest
`cc633b9ee3ffda6a9115af07f0cc047a1bd8cd7af5e11d07f6ddb0faa4e5f975`.
It contains 12 diagnostic tasks and an exact 240-cell schedule. At the time this
contract was added, no diagnostic search outcome had been opened. The reserved
locked-128 cohort remains unopened and has no execution authority.

This is an engineering diagnostic only. Neither a successful run nor a
successful analysis supplies a confidence interval, p-value, method-superiority
claim, task-transfer claim, general QMC claim, or locked-128 execution
authority. `READY_TO_PREREGISTER_LOCKED_128_EXECUTION` means that a new locked
execution contract may be proposed and reviewed; it is not permission to run
that cohort.

At this revision, only authorization-v2 planning and strict reviewed loading are
closed against the regular-file `v2r3` publication identity. The public `--run`
entry point still refuses before reading authorization, sealed inputs, or output
state because the production v2r3 publisher and analyzer are not integrated.
This implementation revision does not create or commit a real authorization
candidate and opens no diagnostic outcome. Stages 3 and 4 below remain future
review boundaries, not executable instructions.

## Source-checkout authority

The runner and analyzer are source-checkout tools. Their authority comes from a
clean Git checkout, exact source-file bytes, and explicit repository provenance,
not from an installed wheel or console script. No packaged console entrypoint
is provided for either tool.

Every operational invocation must therefore:

1. start in a clean checkout of the reviewed repository revision;
2. use `PYTHONPATH=src python -m ...`; and
3. pass `--repository-root .` explicitly.

The runner protects exactly 15 imported modules: nine search modules and six
runner-side modules. The six runner-side modules are the experiments package
initializer, Track A canary manifest, diagnostic manifest, regular-file v2r3
publication substrate, runner, and analyzer.
The analyzer's current replay closure contains exactly 13 imported modules: the
same nine search modules plus the experiments package initializer, Track A
canary manifest, diagnostic manifest, and analyzer. The historical runner leaf
remains required in the run's attested receipt set even though the analyzer does
not import that leaf for current replay.

The tools pin imported module origins to the checkout. Protected source files
must be regular files whose descriptor-read bytes match both their receipts and
the execution-HEAD Git blobs. POSIX reads use `O_NOFOLLOW` for the final path
component. The runner rechecks its source closure around preflight, and the
analyzer independently checks the historical receipts and its current replay
closure. Missing initializers, symlink substitutions, dirty source, import-origin
drift, receipt drift, or blob mismatches fail closed. Already-loaded Python code
objects remain outside this v1 attestation claim.

## Mandatory outcome-blind order

The following stages are separate review boundaries. Do not combine them into
one unreviewed command sequence.

1. Merge the runner, analyzer, tests, documentation, and validation wiring.
2. Create a clean checkout of that merged revision and run planning only.
3. Review the generated authorization candidate in a separate PR. Merge that PR
   without altering the candidate bytes.
4. From a clean descendant checkout, confirm the exact authorization digest and
   merged authorization revision, then consume the authority in one run attempt.
5. Analyze the committed three-file artifact independently and publish one new
   summary outside the run artifact and sealed bundle.

Planning may inspect and verify the sealed bundle, but it must not execute a
diagnostic search cell. The planning result is an authorization candidate, not
execution authority until its exact bytes have passed separate review and are a
tracked Git blob.

## Stage 1: planning only

After production integration has passed its own exact-head review, choose a new
absolute output commit-file path outside the repository and a new authorization
path inside the repository. The output spelling must already be absolute and
lexically normalized; the basename must be ASCII and must not begin the reserved
`.qmc-bmgs-` prefix. Its parent must already exist as a stable component-wise
no-follow directory path. The output and every v2r3 reserved sidecar name must be
absent, and the parent must contain no superseded v2/v2r2 namespace. Neither the
output nor authorization destination may already exist. From the repository
root, the future planning invocation is:

```bash
PYTHONPATH=src python -m \
  qmc_bmgs.experiments.countdown_thompson_diagnostic_runner \
  --plan docs/preregistrations/countdown_thompson_diagnostic_v1 \
  --output \
    /absolute/outside/repository/countdown_thompson_diagnostic_v1.commit.json \
  --authorization-out \
    docs/preregistrations/countdown_thompson_diagnostic_v1_execution_authorization.json \
  --repository-root .
```

The only successful status is
`PREOUTCOME_AUTHORIZATION_CANDIDATE_WRITTEN`. Its claim boundary is planning
only: no diagnostic outcome was opened. A refusal reports `NOT_RUN` and must not
be reclassified as diagnostic evidence. Invalid or incomplete CLI arguments are
also canonical `NOT_RUN`, rather than an unstructured usage traceback. If the
candidate's parent-directory durability and exact rollback both cannot be
proven, planning reports `PUBLICATION_STATE_AMBIGUOUS`. A file left at that path
is not an authorization candidate, must not be committed or used, and the
storage failure must be resolved before planning again at a new path.

The v2 authorization candidate binds the exact raw output path and its byte
digest, `publication_backend=posix_regular_files/v2r3`,
`artifact_layout=flat_commit_root/v2r3`, the complete canonical root-to-parent
`(st_dev, st_ino)` binding and nested digest, the exact mechanics that separate
review must qualify for that host/filesystem identity epoch, 240-cell scope,
bundle and schedule digests, runtime qualification, runner/search source
receipts, authorized runner revision, and its top-level deterministic digest.
Planning captures the parent binding once and then revalidates that exact object
around source and sealed-bundle reads. Reviewed loading parses and freezes the
stored binding before output access and never regenerates an expected binding
from the live path. Reviewers must check those fields against the clean planning
revision without inspecting or generating search outcomes.

### Authorization v2 frozen surface

The top-level schema is
`qmc-bmgs-countdown-thompson-diagnostic-execution-authorization/v2`. It accepts
exactly these fields and rejects missing or unknown fields before Git review or
output access:

```text
artifact_id                         artifact_layout
authorization_scope                 bundle_id
cell_count                          claim_boundary
deterministic_digest                diagnostic_seal_digest
method_manifest_digest              output_parent_binding
output_parent_binding_digest        output_path
output_path_digest                  publication_backend
publication_environment_requirements
requires_explicit_digest_confirmation
runner_build_attestation            runtime_qualification
runtime_qualification_digest        schedule_digest
schema_version
```

`output_parent_binding` is the exact canonical
`qmc-bmgs-posix-output-parent-binding/v1` object defined by the v2r3 publication
contract. `publication_environment_requirements` is an independently
digest-closed
`qmc-bmgs-countdown-thompson-publication-environment-requirements/v1` object
binding the backend, layout, parent-binding digest, required local POSIX
mechanics, scope, and exclusions. The top-level digest closes both nested
objects. Canonical-byte comparison, not Python mapping or numeric equality,
decides identity.

## Stage 2: authorization review

Commit only the byte-identical authorization candidate in a separate PR. The
review must establish all of the following before merge:

- the candidate is canonical JSON and its deterministic digest closes;
- the scope is `one_exact_complete_240_cell_diagnostic_run`;
- the sealed bundle, schedule, method manifest, runtime bindings, and output
  path match the preregistration;
- the backend and layout are exactly `posix_regular_files/v2r3` and
  `flat_commit_root/v2r3`;
- the output path digest closes over its exact filesystem-encoded lexical bytes;
- the complete parent binding and its digest close, and review occurs on the
  same host, filesystem identity epoch, and mount interpretation;
- the stated local POSIX `openat(O_EXCL)`, no-follow identity, regular-file and
  directory `fsync`, and ASCII alias assumptions are qualified; NFS, SMB, FUSE,
  reboot, cross-host, mount-namespace drift, and device/inode ABA remain outside
  authority;
- the protected path sets and all source receipts exact-match non-executable
  regular blobs at both the authorized runner revision and execution HEAD;
- the authorized runner revision is the reviewed implementation revision; and
- the claim boundary grants one diagnostic execution only, with no method
  superiority or locked-128 authority.

Record the full merged authorization commit OID and the 64-character lowercase
authorization digest. The authorization revision must strictly descend from the
authorized runner revision. The later execution HEAD must descend from the
authorization revision, and the authorization bytes at both revisions must be
identical.

## Stage 3: one authorized run attempt — not enabled

There is no authorized production command at this revision. `--run` returns
canonical `NOT_RUN` before loading authorization, sealed bundle, or output state.
A later integration must replace the legacy directory publisher with a
production v2r3 runner, bind every phase receipt and the final commit file to the
authorization's exact parent-binding bytes, preserve the one-shot
NOT_RUN/INVALID/AMBIGUOUS rules, add a nondiagnostic full-shaped fixture, and
pass a fresh exact-head authority review. Only that reviewed revision may freeze
the one-attempt command.

## Stage 4: independent analysis — not enabled

The current analyzer validates only the legacy v1 three-file directory artifact;
it is not compatible with the v2r3 flat commit-root layout or authorization v2.
Do not invoke it on a future v2r3 diagnostic artifact. A later integration must
add a production v2r3 analyzer, exact collective/authorization/source replay
closure, bounded regular-file reads, and no-overwrite summary publication before
any 240-cell outcome is opened. The eventual decision remains exactly one of
`READY_TO_PREREGISTER_LOCKED_128_EXECUTION` and
`STOP_REPAIR_NO_LOCKED_128_RUN`; the first grants only authority to propose and
review a new locked execution contract.

## Outcome-blind validation surface

These self-tests use only synthetic or non-diagnostic fixtures. They do not open
the sealed diagnostic bundle, task cohort, proposals, search records, or
outcomes:

```bash
PYTHONPATH=src python -m \
  qmc_bmgs.experiments.countdown_thompson_diagnostic_runner --self-test
PYTHONPATH=src python -m \
  qmc_bmgs.experiments.countdown_thompson_diagnostic_analysis --self-test
PYTHONPATH=src python -m \
  qmc_bmgs.experiments.countdown_thompson_regular_file_publication_v2 --self-test
```

`python scripts/validate.py` invokes both self-tests from outside the repository
with the checkout's absolute `src` directory on `PYTHONPATH`. The repository
validation surface may verify preregistration artifacts, but it executes no
sealed diagnostic search cell and grants no execution authority.
