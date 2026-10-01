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
