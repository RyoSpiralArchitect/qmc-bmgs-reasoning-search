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

## Source-checkout authority

The runner and analyzer are source-checkout tools. Their authority comes from a
clean Git checkout, exact source-file bytes, and explicit repository provenance,
not from an installed wheel or console script. No packaged console entrypoint
is provided for either tool.

Every operational invocation must therefore:

1. start in a clean checkout of the reviewed repository revision;
2. use `PYTHONPATH=src python -m ...`; and
3. pass `--repository-root .` explicitly.

The runner protects exactly 14 imported modules: nine search modules and five
runner-side modules. The five runner-side modules are the experiments package
initializer, Track A canary manifest, diagnostic manifest, runner, and analyzer.
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

Choose a new absolute output directory outside the repository and a new
authorization path inside the repository. Neither destination may already
exist. From the repository root, run:

```bash
PYTHONPATH=src python -m \
  qmc_bmgs.experiments.countdown_thompson_diagnostic_runner \
  --plan docs/preregistrations/countdown_thompson_diagnostic_v1 \
  --output /absolute/outside/repository/countdown_thompson_diagnostic_v1_run \
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

The authorization candidate binds at least the exact output identity, 240-cell
scope, bundle and schedule digests, runtime qualification, runner/search source
receipts, authorized runner revision, and deterministic digest. Reviewers must
check those fields against the clean planning revision. Reviewers must not
inspect or generate search outcomes while reviewing authorization.

## Stage 2: authorization review

Commit only the byte-identical authorization candidate in a separate PR. The
review must establish all of the following before merge:

- the candidate is canonical JSON and its deterministic digest closes;
- the scope is `one_exact_complete_240_cell_diagnostic_run`;
- the sealed bundle, schedule, method manifest, runtime bindings, and output
  path match the preregistration;
- the protected path sets and all source receipts are exact;
- the authorized runner revision is the reviewed implementation revision; and
- the claim boundary grants one diagnostic execution only, with no method
  superiority or locked-128 authority.

Record the full merged authorization commit OID and the 64-character lowercase
authorization digest. The authorization revision must strictly descend from the
authorized runner revision. The later execution HEAD must descend from the
authorization revision, and the authorization bytes at both revisions must be
identical.

## Stage 3: one authorized run attempt

Replace the placeholders below only after authorization review and merge. Use
the same new absolute output path bound into the authorization candidate:

```bash
PYTHONPATH=src python -m \
  qmc_bmgs.experiments.countdown_thompson_diagnostic_runner \
  --run docs/preregistrations/countdown_thompson_diagnostic_v1 \
  --output /absolute/outside/repository/countdown_thompson_diagnostic_v1_run \
  --authorization-file \
    docs/preregistrations/countdown_thompson_diagnostic_v1_execution_authorization.json \
  --authorization-digest <64-character-lowercase-sha256> \
  --authorization-revision <full-merged-authorization-commit-oid> \
  --repository-root .
```

Do not retry an authorization that has a durable attempt marker. Before
`STARTED`, a refusal is `NOT_RUN` and opens no diagnostic search outcome. Once
`STARTED` is durable, any incomplete or failed execution is `INVALID`; the
attempt evidence is retained and the one-shot authority is spent. Operators
must preserve that evidence rather than delete it and rerun. If commit
durability and exact commit-receipt rollback both cannot be proven, the runner
reports `PUBLICATION_STATE_AMBIGUOUS`. This also spends the one-shot authority:
preserve the attempt and output paths, do not analyze the artifact, and do not
retry.

An attempt reservation is durable only after its parent directory is synced.
If that barrier persistently fails, `NOT_RUN` is permitted only after the exact
reservation is atomically moved out of its public name into a retained,
inode-and-byte-verified tombstone, the parent directory barrier completes, and
the public name is re-observed as non-authoritative. `STARTED`, `NOT_RUN`, and
`INVALID` receipts likewise require their containing-directory barrier and an
exact re-observation. An I/O error that prevents either durability or rollback
from being proven is `PUBLICATION_STATE_AMBIGUOUS`, never inferred absence.
Retained tombstones are non-authoritative incident evidence; preserve them and
never treat them as a completed artifact.

A valid completed artifact is one directory containing exactly:

- `commit.json`
- `manifest.json`
- `records.jsonl`

The artifact must close all 240 cell identities in preregistered order, retain
zero provider calls, bind the reviewed authorization and execution HEAD, satisfy
budget closure, and carry two-stage replay evidence. Partial output, an extra or
missing artifact entry, schema drift, replay drift, source drift, or publication
failure is not a valid diagnostic result.

The READY staging directory is renamed from the attempt directory into the
authorized output parent. A completed publication requires durability barriers
for both namespace parents: the source attempt directory after `staging` is
removed and the destination output parent after the artifact and commit receipt
are inserted.

## Stage 4: independent analysis

Choose a new summary path that does not exist and cannot modify the run artifact
or sealed bundle. From the same reviewed source checkout, run:

```bash
PYTHONPATH=src python -m \
  qmc_bmgs.experiments.countdown_thompson_diagnostic_analysis \
  --analyze \
    /absolute/outside/repository/countdown_thompson_diagnostic_v1_run \
  --bundle docs/preregistrations/countdown_thompson_diagnostic_v1 \
  --authorization-file \
    docs/preregistrations/countdown_thompson_diagnostic_v1_execution_authorization.json \
  --authorization-digest <64-character-lowercase-sha256> \
  --output \
    /absolute/outside/repository/countdown_thompson_diagnostic_v1_summary.json \
  --repository-root .
```

The analyzer verifies the bundle, reviewed authorization lineage, exact
three-file artifact closure, all 240 records, provider-call zero, budget
evidence, source attestations, and both replay stages before constructing a
summary. A byte-identical committed artifact may be analyzed from a relocated
copy, but both that copy and the historical `authorized_output_path` remain
protected: the summary path may not modify either artifact, and an existing
historical artifact is pinned by descriptor and inode through publication. It
writes one canonical no-overwrite summary only after every gate passes. Success
reports `PASS`; any CLI, integrity, analysis, or publication
failure with durably proven absence reports canonical `INVALID` and emits no
diagnostic result. If summary durability and exact rollback both cannot be
proven, it reports `PUBLICATION_STATE_AMBIGUOUS`; any file at the requested
destination remains unauthoritative and must not be used as diagnostic
evidence. Summary publication follows the same rule: an exact summary is
accepted only after inode, canonical bytes, stable non-symlink ancestry, and
the parent barrier all close. Rollback atomically moves an exact summary into a
retained quarantine; a moved exact summary that cannot be revoked is ambiguous,
not `INVALID`.

The summary decision is exactly one of:

- `READY_TO_PREREGISTER_LOCKED_128_EXECUTION`
- `STOP_REPAIR_NO_LOCKED_128_RUN`

The first permits only a new preregistration and review step. The second keeps
the locked-128 cohort closed while the mechanism or implementation is repaired.

## Outcome-blind validation surface

These self-tests use only synthetic or non-diagnostic fixtures. They do not open
the sealed diagnostic bundle, task cohort, proposals, search records, or
outcomes:

```bash
PYTHONPATH=src python -m \
  qmc_bmgs.experiments.countdown_thompson_diagnostic_runner --self-test
PYTHONPATH=src python -m \
  qmc_bmgs.experiments.countdown_thompson_diagnostic_analysis --self-test
```

`python scripts/validate.py` invokes both self-tests from outside the repository
with the checkout's absolute `src` directory on `PYTHONPATH`. The repository
validation surface may verify preregistration artifacts, but it executes no
sealed diagnostic search cell and grants no execution authority.
