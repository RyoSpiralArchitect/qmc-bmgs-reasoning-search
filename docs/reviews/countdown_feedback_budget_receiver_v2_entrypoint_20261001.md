# Receiver-v2 production entrypoint: bounded local review — 2026-10-01

Scope: an additive fixed-candidate CLI, tests and policy. This is a single-agent
source review, not a separate-agent or human approval. Actual production run,
claim consumption, generation, analysis and saved-summary verification are not
exercised in this implementation task. The real metadata checks are recorded
separately after successful completion.

## Boundaries examined

- Exact immutable candidate digest/hash and the original raw/promoted bytes.
- Frozen preparer/coordinator source closures and prior reviewed admission proof.
- New three-file wrapper source receipt, immutable full revision identities,
  ancestry, reviewed Git bytes, no-follow snapshots and output-parent binding.
- Preflight/check call no genuine admission or production dispatcher, and supply
  neither digest consent nor another qualification result.
- Genuine later dispatch is delegated exactly once to the unchanged coordinator;
  no fake admission, replacement study, custom runner or own consume call exists.
- Run requires unused original claim/output/summary; analysis and verification
  must instead be able to inspect the consumed/committed state.
- Dispatch/progress/return source checks are not an atomic addition to the
  coordinator's transaction. Detection after effects remains possible and must
  preserve consumed/uncertain state without retry.
- Result delivery, generic failures, known coordinator failures and post-return
  validation failures have distinct conservative consumption reporting.
- CLI cannot select PUBLIC, arbitrary paths, different seeds, resume or retry.
- No scientific decision or locked-128 authority follows from plumbing tests.

## Corrections before source freeze

1. Require a full review revision at public function boundaries as well as in
   CLI argument validation; otherwise direct check/dispatch calls could omit the
   reviewed-preflight gate. Regression test covers both functions.
2. Distinguish analysis's exclusive summary publication from verification's
   read-only saved-summary replay in the result boundary.
3. Give a successfully returned coordinator run precedence over later checker
   exceptions: even a later `ExecutionFailure(consumed=False)` cannot downgrade
   known consumption. A specific regression injects this post-return exception.
4. Remove an unused test import reported by the first lint check. No focused
   synthetic test failed; the first 44 passed, then the additional post-commit
   consumption regression brought the final focused set to 45.

## Focused validation

45 synthetic tests passed in 1.991 seconds; Ruff passed. The tests include
candidate and proof substitution, missing/replaced reviewed preflight, full
revision/ancestry checks, source/snapshot/HEAD/parent drift, occupied and dangling
output, explicit confirmation, exactly-once fixed dispatch, analysis boundaries,
unknown consumption, publication/delivery uncertainty and CLI exclusion tests.
An actual static self-test also runs outside the checkout with a fresh private
cache; static identity checking is not production admission or execution.

Saved real metadata supplies byte fixtures only; all runtime admission,
consumption and search entrypoints are forbidden or explicitly mocked in tests.
Synthetic commits/summaries are labelled and are not promoted as real evidence.

No actionable source defect remained in this bounded review. Full repository
validation and fresh-process metadata preflight/check are pending at source
freeze; their results cannot be inferred from the focused tests above.

## Frozen implementation and full validation

Implementation: `4d419343d6a542a132d2336456000e9c638f1cc3`.
No executable, test or policy changed after this freeze. The complete repository
validator exited 0: **1,340 tests, zero skips, 854.023 seconds of test execution**,
plus compilation, lint, artifact/provenance and CLI checks. The validator began
at 2026-10-01 11:46:36 UTC; successful completion was observed at 12:03:56 UTC.
These are invocation/observation timestamps, not performance benchmarks.

## Actual preflight rejection, not an execution failure

Exactly one actual metadata-only preflight used a fresh process and private
cache, absolute `PYTHONPATH`, and `python3 -P -B`. It started at 11:46:36 UTC;
exit 1 was observed at 11:47:23 UTC. Its error was `original output parent
changed`, before production dispatch or any new admission/consumption/search.
The generic failure receipt conservatively reports consumption as unknown;
separate read-only observations establish that the original claim/output/summary
were absent at observation time.

Across all seven output-parent path components, the candidate records device
16777231, while the actual current binding records 16777234. Paths and inode
numbers are identical. This does not establish physical-disk identity or reboot
causality and is not an accepted re-attestation mapping. The underlying existing
bridge policy explicitly rejects later device/inode transitions; the new wrapper
must not relax it.

The exact failure result is saved as a **preflight-failure** artifact. No successful
preflight is promoted to the path required by `--check`/`--run`. No reviewed check,
run, actual production analysis or saved-summary verification was attempted.
No binding was patched, no replacement candidate/certificate was created and
no automatic retry was performed. No remaining source defect was identified;
the operational result remains **NOT_READY_TO_RUN** pending a separately
authorized and reviewed current-receiver re-attestation design.

Read-only observation at the implementation HEAD confirmed all 333 prior tracked
files / 78,928,252 bytes unchanged by blob and executable mode, as well as exact
raw candidate, three sealed-cohort files and three prior ledger records. The
original output, summary and fixed replication claim remained absent. See the
[task report](../countdown_feedback_budget_receiver_v2_entrypoint_20261001.md)
and its linked receipts for the operation boundary and safe next decision.
