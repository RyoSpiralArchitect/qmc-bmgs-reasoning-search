# Feedback × budget: one-shot execution connector

This layer connects the already qualified computation, cohort admission and
publication mechanisms. It does not change the frozen v6 experiment or old
qualified executables. Code and synthetic fault tests are not development data.

## Gates and scope

1. Qualify this exact committed connector on the fixed public 192-cell matrix.
   It has 12 public targets but **one source multiset**, no new tasks, and a null
   scientific decision. Execution, independent analysis and saved-summary
   verification must run in separate source-qualified processes.
2. Seal the fixed fresh cohort using the separately qualified admission CLI.
   The connector has no generation command. Its development loader only accepts
   that exact three-file seal and independently regenerates its acceptance order.
3. Prepare a candidate binding the seal, full input/schedule identity, verified
   public connector evidence, source/runtime and exact output parent identity.
   Promote the unchanged candidate and public summary into Git and review them.
4. Execute only after explicit confirmation of the candidate digest and a full
   reviewed commit OID. Current Git bytes must equal the reviewed files. The
   source must equal the PUBLIC connector-producing implementation. A code fix
   requires a fresh public qualification, never rewritten historical evidence.

The old admission-only authorization candidate is intentionally NOT executable.
Candidate flags remain `candidate_is_execution_authority: false`; a valid JSON
object, matching hash, clean checkout or unit-test pass does not grant permission.
No command authorizes evaluation of the locked 128 tasks.

## One-shot and failure contract

After admission and before output creation, an exclusive, private, durable claim
is written under `artifacts/work/feedback-budget-v6-authorization-ledger`.
The development claim name is fixed **per study**, not per candidate, cohort or
output. Reissuing a candidate or deleting the output cannot restore permission.
Public fixture claims have separate per-candidate names. A spent claim is checked
before cohort regeneration or public requalification on repeat invocations.

This is receiver-local POSIX crash/race protection, not a remote authorization
service or tamper-proof defense against a user/admin deleting the ledger or
altering executable code. Preserve the ledger and failed artifacts. No automatic
retry, repair, adoption, overwrite, resume, cleanup or alternate cohort is exposed.

An execution writes durable STARTED, 192 ordered cells, RECEIPT, then COMMIT last
(195 files). All identities close before first generative replay; all 192 traces
must be byte-identically reproduced and all 96 full accepted-event prefixes and
completion guarantees pass before mechanism → errors → exact-success reduction.
Analysis independently verifies the candidate, consumed claim, input seal,
source/runtime, complete file closure, replays and receipt, then saves a sibling
summary. Storage alone cannot authenticate a candidate or scientific result.

- `AUTHORIZATION_ALREADY_SPENT`: occupied fixed claim; no new work admitted.
- `CONSUMPTION_UNCERTAIN`: claim durability uncertain; retain namespace, no retry.
- `SPENT_NOT_RUN`: known consumed claim, no admitted search started.
- `INVALID_ANALYSIS`: incomplete/invalid execution or independent analysis; no
  scientific decision. Keep the failed and missing cells; do not impute zeros.
- `PUBLICATION_UNCERTAIN`: publication or post-COMMIT boundary uncertain; retain
  artifacts. No competing failure marker can countermand a possibly durable
  COMMIT. Do not automatically adopt an uncertain invocation as qualification.
- `RESULT_DELIVERY_UNCERTAIN`: the operation completed, but delivery to stdout
  failed. A completed run retains known `authorization_consumed: true`; it is
  never relabeled `NOT_RUN` and must never be repeated.

Independent analysis can validate structurally complete artifacts after a failed
producer invocation. It cannot know that invocation's return status from COMMIT
alone. Disposition of an uncertain invocation is an **operator gate**, not an
automatic recovery feature: record the failure, inspect the retained artifacts,
and explicitly decide whether to reanalyze. Do not chain later qualification
commands after nonzero exit, or call a reanalysis a successful original run.
Neither reanalysis nor a replacement summary restores the fixed study claim.

Only a complete admitted development analysis maps the frozen conjunction to
`DEVELOPMENT_SIGNAL_FOR_SEPARATE_CONFIRMATION_DESIGN` or
`STOP_REPAIR_NO_LOCKED_128_RUN`. Neither is confirmation, causality, population
evidence or permission for another experiment. Denominators remain 12 task
clusters, 48 four-arm task/seed blocks, 96 budget pairs and 192 cells.

## CLI

Use the frozen CPython/arm64 CPU binary64 runtime and a clean committed checkout.
For each source-qualified invocation set `PYTHONPATH` to the absolute `src` path,
use `-P -B`, and set `PYTHONPYCACHEPREFIX` to a newly created private empty directory
outside the checkout. Do not reuse caches. The self-test is identity-only:

```sh
PYTHONPATH="$PWD/src" python3 -P -B scripts/run_feedback_budget_execution.py --self-test
```

The exact command-specific arguments are enforced (no abbreviations):

| Command | Required arguments |
| --- | --- |
| `--prepare-public` | `--output`, `--authorization` |
| `--prepare-development` | `--output`, `--authorization`, `--qualification` |
| `--run-public` / `--run-development` | `--authorization`, `--confirm-digest`, `--reviewed-revision` |
| `--analyze-public` / `--analyze-development` | `--output`, `--summary` |
| `--verify-public` / `--verify-development` | `--output`, `--summary` |

Prepare writes an ignored local candidate, not a reviewed tracked authorization.
Output/candidate creation and saved summaries are direct children of
`artifacts/work`. Development execution reads the promoted candidate at its
reviewed tracked path. `--qualification` names the promoted public connector
summary; verification also needs its original local raw run, public candidate,
claim ledger, and unchanged ancestor implementation. Raw artifacts are local,
hash-bound and ignored; tracked summaries are not portable raw replay evidence.

Implementation and qualification status is recorded separately in the dated
review/validation notes. No example here invokes a development experiment.
