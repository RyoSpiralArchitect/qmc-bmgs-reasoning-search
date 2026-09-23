# Receiver-v2 candidate operator: bounded local review — 2026-09-23

Scope: additive candidate preparation and independent candidate admission review.
This is a single-agent source review, not a separate-agent or human review.
Separate-process actual reconstruction is recorded only after it completes.

The operator leaves the five qualified coordinator files and all historical
code/evidence unchanged. It has only self-test, prepare, and verify-candidate
commands. No execution mode, digest-confirmation option, caller-selected paths,
new cohort or claim-consumption call is added. A successful verification result
reports production admission separately from production execution.

## Reviewed boundaries

- Fixed PUBLIC review/source anchors precede the preparer implementation.
- The closed candidate schema remains owned by the unchanged coordinator.
- Actual preparation calls genuine PUBLIC qualification and original receiver
  admission; mock inputs exist only in explicitly synthetic tests.
- Raw/promoted candidates and the canonical preparation receipt must agree with
  reviewed Git bytes before genuine sealed-mode admission is invoked.
- The original output, summary and fixed claim must remain unoccupied; a new
  digest cannot create a new study claim. Existing candidates are never replaced.
- Publication is exclusive and rechecks source, evidence, output parent and
  unconsumed state. Occupied/uncertain files are preserved.
- Error receipts do not assert an unused claim; completed-operation delivery
  failures are distinguished from work that did not complete.
- The PUBLIC negative numerical screen and original sealed schedule are unchanged.

No actionable source defect remained in this bounded local review. This statement
does not prove the full repository validation or actual candidate reconstruction;
their operation results must be recorded separately.

## Synthetic validation before source freeze

34 tests passed in 6.131 seconds; Ruff passed. These tests cover forbidden CLI
operations, fixed namespaces, occupied and dangling-symlink slots, source/proof
changes, late claims, genuine-entrypoint dispatch without run/consume/generation,
candidate/preparation byte mismatches, exclusive publication uncertainty and
result-delivery uncertainty.

The first focused run exposed two test-fixture issues, both corrected before
the passing run: a macOS temporary-path alias was not a canonical no-follow
path, and an isolated source-coverage test unintentionally invoked a real
cache-origin preflight without its runtime setup. The publication fixture now
uses its resolved temporary directory; the source-coverage unit test explicitly
mocks and checks the origin boundary. Actual qualification still uses the real
unchanged origin check with a fresh private cache and source-only interpreter.
No real candidate, claim or scientific cell was created by those tests.

Reviewed implementation SHA-256:
`d35a1a84d0721216e98d9f7eeee8f5214af08b54b411547ecd9450f55c1c6f20`.

Reviewed test SHA-256:
`9a20cd58b9884ea566826f3d737a8681b832cd32318adcbea7994b58e3bbdb5e`.

Reviewed policy SHA-256:
`76cdf818464c616637854d83d554630fec2eac373c38403f2f256f54dd4e895e`.

## Actual preparation and candidate metadata review

The operator was frozen at
`9d14059362e18a396e4fa865d8a0b3c69fde1eb6`. The full repository validator
completed successfully: 1,295 tests in 869.792 seconds, zero skips, plus the
repository compilation, lint, artifact and CLI checks. These results do not
substitute for the actual evidence reconstruction below.

Exactly one genuine preparation process ran with a fresh private bytecode cache,
absolute source path and `python3 -P -B`. It began at 2026-09-23 07:26:34 UTC;
successful exit 0 was observed at 08:32:49 UTC. The frozen PUBLIC qualification
and original receiver admission were reconstructed, and exclusive candidate
publication completed both its pre-publication and post-publication checks.

- Candidate status: `RECEIVER_V2_CANDIDATE_PREPARED_NOT_AUTHORIZED`.
- Candidate digest:
  `198f4582054184e2e476542afc1621178b3a1fbc6b82bd002b67f99c6684d070`.
- Candidate bytes: 159,005; SHA-256:
  `7adaeba09ffdc21f21a852ad047b1aa7e0914ec284063a3ce768d410147fbb5b`.
- Preparation receipt digest:
  `f527794d935ad8e3ffb51c17a1e0f97d90b80771bd91ec1f7a12180a2b7d0061`.
- Preparer source digest:
  `cd7497f62f81fe7a5fc1a8b4a0a725bdbaf8b4754aee3d8328d447f8afcf12ee`.

The raw candidate and the exact successful preparation result are promoted
without reserialization. Candidate metadata independently assembled from the
saved v1 candidate and reviewed v2 PUBLIC evidence predicted the same digest,
file hash and byte count. That read-only metadata comparison is corroboration,
not the genuine fresh-process admission check, which remains pending at this
candidate-review commit.

Comparison with the original v1 receiver candidate preserves 18 shared fields,
including the full admission proof, authorities, baseline, cohort seal,
contract, original source/runtime, input manifest, schedule, output binding and
explicit-confirmation requirements. Only the shared schema, connector
qualification and deterministic digest differ. The v1 bridge/certificate fields
are replaced by the qualified coordinator/receiver-admission fields and the
explicit attempt identity. The attempt identity remains the original
`feedback_budget_confirmation_64_seed_26091301/v1`; there is no new study.

All 324 files tracked at the prior PUBLIC evidence commit remain byte- and
executable-mode-identical. The three existing authorization-ledger records are
unchanged. The original production output, replication summary and fixed
replication claim remain absent. The genuine preparation result reports zero
replication search calls, no production adapter execution and no execution
authority. No actionable metadata defect was found in this single-agent review.

Next gate: commit these exact candidate/preparation bytes, then independently
invoke the unchanged genuine production admission in a fresh process. Even a
successful result will not authorize execution or consume the fixed claim.
