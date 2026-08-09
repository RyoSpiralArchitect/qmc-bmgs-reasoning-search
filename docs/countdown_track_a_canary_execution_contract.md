# Countdown Track A canary execution contract

## Purpose and authority boundary

This contract separates implementation, authorization, execution, and
analysis for the provider-neutral Track A engineering canary. The canonical
input is the version-two bundle at
`docs/preregistrations/countdown_track_a_canary_v2/`, whose aggregate seal is:

```text
5799c9f17686f064b7c50ee741d79bfbb14a4d61b9048672068a586b258fd437
```

The bundle contains 12 source-multiset-disjoint tasks and exactly 936 cells.
It has no search outcome. The canary, if validly executed, remains descriptive
development evidence only. It has no inferential, winner-selection,
non-inferiority, promotion, or locked-128 authority.

Runner and analyzer self-tests use only a source-disjoint non-canary fixture.
Passing them establishes plumbing and fail-closed behavior, not search
strength, an IID/Sobol effect, or validity of a canary artifact that has not
been independently analyzed.

## Mandatory outcome-blind order

The following order is part of the authorization boundary. It must not be
collapsed into one pull request or one shell transaction.

1. Review and merge the runner and independent analyzer implementation PR.
2. From a clean checkout of that merged revision, run `--plan` only. This
   repeats the sealed-bundle, exact-runtime, ancestry, source/build, schedule,
   budget-envelope, and non-canary numeric micro-fixture checks. It writes one
   canonical authorization candidate and opens no sealed canary outcome.
3. Put only that authorization candidate and explanatory outcome-blind
   metadata in a separate authorization PR. Review its exact bundle seal,
   schedule digest, 936-cell count, method manifest, runtime qualification,
   runner/search/analyzer source receipts, authorized output identity, and
   deterministic authorization digest. Merge that PR before execution and
   record the authorization PR merge commit as the reviewed authorization
   revision.
4. From the authorized clean revision, supply the reviewed authorization file
   together with its exact lowercase SHA-256 deterministic digest and reviewed
   authorization revision to one `--run` call. The output directory must be
   new, absolute, and outside the repository.
5. Give the finished artifact, the sealed bundle path, and the independently
   supplied reviewed authorization file plus digest to the analyzer. Publish
   the summary outside both the artifact and sealed bundle.

A changed runner, analyzer, search source, task, proposal, method, seed,
budget, runtime binding, schedule, output identity, gate, or summary rule
requires a new outcome-blind authorization candidate. It is never repaired by
editing authorization bytes or an artifact after outcomes exist.

## Planning command

Choose the final, repository-external artifact path before planning. The
authorization candidate must name a repository-internal path intended to
become exactly one tracked file in its separate PR. An absolute path outside
the repository, a symlink path, or an existing destination is rejected. The
run output must remain outside the repository and must not already exist.

```bash
qmc-bmgs-countdown-track-a-canary-runner \
  --plan docs/preregistrations/countdown_track_a_canary_v2 \
  --output /absolute/outside/repo/countdown_track_a_canary_v2_run \
  --authorization-out docs/preregistrations/countdown_track_a_canary_v2_execution_authorization.json \
  --repository-root .
```

Record the printed `authorization_digest` without changing the generated
file. Planning status
`PREOUTCOME_AUTHORIZATION_CANDIDATE_WRITTEN` means only that the candidate was
written after outcome-blind checks. It is not authority to run until the
separate authorization PR is reviewed and merged. At execution, the candidate
must be a tracked file whose working-tree bytes exactly equal its Git blob.

## One authorized execution

After the authorization PR is merged, use the exact path, digest, and merge
commit reviewed in that PR. The merge commit supplied by
`--authorization-revision` must strictly descend from the runner revision
embedded by `--plan`, and the current execution HEAD must descend from that
reviewed revision. The authorization file must be one tracked repository file,
and its bytes must exactly match the Git blob at both the reviewed revision and
the current execution HEAD. The `--output` value must byte-for-byte match the
absolute output identity sealed by `--plan`.

```bash
qmc-bmgs-countdown-track-a-canary-runner \
  --run docs/preregistrations/countdown_track_a_canary_v2 \
  --output /absolute/outside/repo/countdown_track_a_canary_v2_run \
  --authorization-file docs/preregistrations/countdown_track_a_canary_v2_execution_authorization.json \
  --authorization-digest <reviewed-authorization-digest> \
  --authorization-revision <reviewed-authorization-pr-merge-commit> \
  --repository-root .
```

The runner first acquires an output-specific sibling publication lock. Before
opening any sealed task or proposal outcome, it durably publishes a sibling
attempt marker keyed by the output identity and authorization digest, performs
one final source-closure check, creates the marker-owned staging directory,
and durably appends the `STARTED` receipt. Only then may it execute the exact
sealed order. The two-file READY core (`manifest.json` and `records.jsonl`) is
renamed with descriptor-bound atomic no-overwrite publication. Only after that
rename, exact inode/byte checks, and parent-path closure does the runner append
`commit.json`. That third file is the portable COMMITTED authority; a copied
staging directory without it is invalid. Every one of the 936 records must
close against its sealed cell identity, seven-axis budget, method/runtime
identity, and immediate two-stage replay. All
`provider_calls` values are exactly zero: proposals and search are local,
provider-neutral components.

The durable marker is the one-attempt reservation; the sibling lock is only a
transient concurrency mutex. Publication of the marker consumes that exact
authorization for that output, even when the final pre-outcome closure records
`NOT_RUN`. Once an attempt reaches `STARTED`, a failure additionally retains
an append-only `INVALID` receipt and the available execution evidence. Before
publication that evidence is marker-owned staging; after the READY rename it
may instead be an uncommitted two-file directory at the authorized output.
Neither state has `commit.json`, so neither is analyzable. Do not delete that
evidence, rename staging, synthesize the missing commit receipt, or retry the
same authorization. A replacement requires a newly planned and separately
reviewed authorization; a new output identity is recommended so the refused
or failed attempt and its replacement remain unambiguous.

Only the embedded canonical search core is byte-replayed. Wall-clock fields
such as `search_wall_time_ns` and `replay_wall_time_ns` are volatile,
descriptive telemetry. They are excluded from the search-core identity,
budget closure, hard gates, method contrasts, and authorization decision.

## Independent analysis

The analyzer receives authority as paths and bytes, not as a caller-created
verified object. The reviewed authorization is supplied independently instead
of trusting only the copy embedded in the run manifest. It must still be the
same repository-internal tracked file: analysis validates the reviewed
revision lineage recorded by the runner and exact authorization Git blobs at
the reviewed and execution revisions.

```bash
qmc-bmgs-countdown-track-a-canary-analysis \
  --analyze /absolute/outside/repo/countdown_track_a_canary_v2_run \
  --bundle docs/preregistrations/countdown_track_a_canary_v2 \
  --authorization-file docs/preregistrations/countdown_track_a_canary_v2_execution_authorization.json \
  --authorization-digest <reviewed-authorization-digest> \
  --output /absolute/outside/repo/countdown_track_a_canary_v2_summary.json \
  --repository-root .
```

Before opening outcome-bearing records or emitting any descriptive result,
analysis requires the exact three-file closure and verifies that `commit.json`
binds the READY manifest, STARTED receipt, and reviewed authorization. It then
requires exact 936-cell coverage and ordering, canonical JSON/hash closure,
reviewed authorization byte equality, Git/source provenance, zero provider
calls, all budget and oracle gates, and independent stage-one generative plus
stage-two byte-identical replay for every cell. The summary contains raw task
vectors, descriptive contrasts, engineering gate states, and resource
counters only.

The current replay surface binds twelve imported modules: nine search modules
(the `qmc_bmgs`, `benchmarks`, and `substrate` package initializers plus six
search leaves), the `experiments` package initializer, the canary manifest, and
the analyzer. The historical runner leaf remains an attested thirteenth source
but is not imported by the analyzer. For each current module the analyzer
checks the ordinary CPython import origin plus current O_NOFOLLOW-read
regular-file bytes against the execution-head Git blob and attested source
receipt. This is strong source provenance under
ordinary, unmodified CPython import semantics. It is not a cryptographic
attestation of already-loaded code objects, interpreter memory, native code,
or a hostile process that has monkeypatched runtime objects after import.

The committed three-file artifact may be copied or moved after publication for
archival or analysis. The analyzer does not require its current directory to
equal the historical absolute `authorized_output_path`; it verifies the
embedded artifact identity, authorization bytes, file digests, source
receipts, and content closure instead. Copying does not permit modifying any
byte. The reviewed authorization and sealed bundle must still be supplied
separately, and the summary destination must remain outside the copied
artifact and bundle.

## `NOT_RUN`, `INVALID`, and valid descriptive output

- `NOT_RUN` applies only when runner preflight, reviewed-Git authorization, or
  final pre-outcome closure refuses execution before `STARTED`. It is not
  recorded as a failed search cell and must not be converted to a zero score.
  If a durable pre-outcome marker already exists, retain its `NOT_RUN` receipt;
  that exact authorization/output pair remains consumed by the reservation.
- Runner `INVALID` applies after `STARTED` when the 936-cell execution or
  publication fails. The durable `INVALID` receipt and available execution
  evidence remain—either marker-owned staging or an uncommitted two-file READY
  output—the same authorization is consumed permanently, and no partial row
  is dropped, imputed, repaired, or summarized.
- Analyzer `INVALID` also includes invocation/configuration refusal, missing or
  unreviewed external authorization, artifact identity/budget/provider/oracle
  failure, or any replay/analysis closure failure. It emits no descriptive
  summary. This label does not imply that a canary outcome was opened by that
  analyzer invocation.
- A valid descriptive summary exists only after every hard gate and every
  independent replay passes. Even then, it cannot select a winner, promote a
  method, establish non-inferiority, or claim a general IID/Sobol or QMC
  effect.

An interruption that leaves marker-owned staging or a two-file READY directory
does not create a partial valid artifact. Do not publish, rename, complete, or
analyze either state by hand. Preserve the attempt directory, output entry,
and receipts for forensic diagnosis, then generate and review a new
authorization before any replacement run.

## Download-free validation

The two component self-tests do not read the sealed task cohort. Full
repository validation also verifies the outcome-blind sealed manifest bytes,
but none of these commands executes any of the 936 search cells:

```bash
qmc-bmgs-countdown-track-a-canary-runner --self-test
qmc-bmgs-countdown-track-a-canary-analysis --self-test
python3 scripts/validate.py
```

Their claim boundary is mechanism integrity on non-canary fixtures only.
