# v7 sealed admission and one-shot connector: review and actual qualification

Date: 2026-09-13 (Asia/Tokyo). Producing implementation:
`91359c9327861210c03ad0bc4e267af240f4ec93`.

Scope: the [new v7 admission/connector](../countdown_feedback_budget_replication_execution.md).
This adds a separately domain-bound 1,024-cell production entry, fixed-study
one-shot consumption, sealed-cohort loading and independent result verification.
Implementation and PUBLIC qualification are not permission for the new 64-source
cohort or its execution. No consumed development study was rerun; v6 evidence,
the existing search implementation and frozen v7 design/contract/PUBLIC identities
remain byte-unchanged.

## Local review and retained development failures

This turn used local operator review and adversarial regression tests, not a
new independent outside/fork reviewer. Do not transfer the earlier PUBLIC-only
path's outside review to this new connector.

The seven new files were first committed in
`256d092494ce0c56eb18f0498624e3f29d0efa48`. Local lifecycle review found that a
stdout failure after successfully verifying an already sealed cohort could
report known generation consumption as false. The correction in `91359c9`
preserves consumed state after successful seal, seal verification or candidate
preparation; self-test remains nonconsuming. A regression reproduces the closed
stdout after successful verification. Uncertain publication is still not
classified as invalid science or permission to regenerate.

Retained development attempts:

- The first admission-focused run had 20 tests, 19 passes and one test error in
  6.719 seconds. The hardlink/symlink fixture was correctly rejected by the POSIX
  publication error class, but the test expected only ValueError. The expectation
  was corrected; no validator was weakened.
- Initial Ruff E731 concerned a test-only assigned lambda; it became a named
  helper. No experiment parameter changed.
- The full validator at `256d092` was deliberately interrupted with exit 130
  to correct the stdout lifecycle issue. It is not a completed validation and
  did not begin a source-qualified connector PUBLIC execution.
- The final focused admission suite passed all 23 tests in 5.655 seconds.
  The connector-focused suite passed all 38 tests in 11.429 seconds.
- The corrected complete validator passed all 1,183 tests in 926.353 seconds,
  with no skips. This is the unittest duration, not total validator wall time.
  Compilation, Ruff, provenance/artifact checks, outside-checkout self-tests and
  final historical v5 seal verification also passed: `repository validation: PASS`,
  exit 0.

The corrected full validator used absolute `src` on `PYTHONPATH`,
`python3 -B scripts/validate.py` and cache prefix
`/private/tmp/qmc-v7-connector-validation-pyc.MnQfxi`.
PUBLIC preparation and the PUBLIC run began while this complete validator was
still running, with the same fixed clean source. No tracked bytes were edited
during these operations. All 61 new tests and all 48 preceding v7 PUBLIC-path
tests also passed within the complete suite.

Boundary tests cover wrong domains and numeric/JSON aliases before generation,
both identity exclusions, exact generator arguments and acceptance order,
three-file seal linkage, immutable snapshots, source-bound qualification,
fixed-study claims across changed output/candidate/cohort names, durable claim
before output/search, partial failures, uncertain COMMIT, closed stdout,
all 1,024 identities before first replay, analyzer order, descriptor preflight
before baseline/admission and the 64 MiB control-file cap. AST equality verifies
that the pure ordered reduction has the preceding qualified v7 algebra, with
only its docstring and domain changed.

## Fixture closure and claim limits

The new connector PUBLIC inputs are exactly the existing 64 target definitions
1 through 64 on [1,2,3,4,5,6]. The component/anchor baseline uses the existing
target 720 on that same source. These are 65 definitions on one input source,
not 64 source-independent performance tasks. Tests verify all 1,024 scientific
run identities equal the preceding PUBLIC path.

Positive sealing/storage unit fixtures deliberately repeat the existing
target-720 definition under explicit identity/generator/context mocks. They
are not a real accepted 64-source cohort; the unmocked positive-looking fixture
is rejected. No additional arithmetic definition or fixture variant was added.
Historical authority checking independently regenerates already sealed identity/
solvability acceptance orders, not consumed search experiments. The new admission
layer never dereferences the returned calibration/witness objects. The eight-group exclusion union is
unchanged at 243 full-task identities and 179 source identities.

## Actual connector PUBLIC operations

Every source-qualified operation used the clean producing commit, absolute
`src` on `PYTHONPATH`, `python3 -P -B`, and a fresh empty owned mode-0700
cache prefix. CPython 3.13.13 / Darwin arm64 / CPU binary64 matched the frozen
runtime. The non-search source/runtime/descriptor preflight also passed before
PUBLIC preparation; the real cohort slot and new ledger were then absent.

The fixed output is the repository-local
`artifacts/work/feedback-budget-replication-connector-v7-20260913-a`.
Its sibling authorization and summary retain that same basename with
`.authorization.json` and `.summary.json` suffixes. These occupied output/
authorization slots must not be reused for execution.

The PUBLIC authorization digest is
`cab7c1467ec796b8f0261bb7375f57af37376dc12033d72141e5a2b2458e0800`.
Its distinct input-manifest digest is
`c07eb38ada5d555d56075047242370c49f4e0dee120d96e1e489c981f00ae7ab`;
its connector-domain schedule digest is
`9ab801c67cacf4cbff99ddd832d471904958cc2842a4508e033fc2bb95d0dabd`.
Changing the enclosing keys does not change a scientific run identity.

| Operation | Fresh cache prefix | Result |
| --- | --- | --- |
| `--prepare-public` | `/private/tmp/qmc-v7-connector-public-prepare-pyc.ZaA7U6` | Non-authorizing candidate saved; exit 0 |
| `--run-public` | `/private/tmp/qmc-v7-connector-public-run-pyc.BMQAqK` | `CONNECTOR_MATRIX_COMMITTED`; exit 0 |
| `--analyze-public` | `/private/tmp/qmc-v7-connector-public-analyze-pyc.fGQtci` | `CONNECTOR_INDEPENDENT_ANALYSIS_PASS`; exit 0 |
| `--verify-public` | `/private/tmp/qmc-v7-connector-public-verify-pyc.JY52j9` | Exact canonical saved-summary equality; exit 0 |

The PUBLIC run returned `CONNECTOR_MATRIX_COMMITTED`, exit 0. All 1,024
scientific records were saved under distinct new-domain cell keys; all 1,024
two-stage replays and 512 complete accepted-event budget-prefix checks passed.
The closed publication has 1,027 files totaling 136,421,856 bytes. Provider calls
and replication cells are zero; scientific decision is null. This is not a
64-source replication result.

After that producer returned exit 0, a deliberately repeated PUBLIC command
was refused with `AUTHORIZATION_ALREADY_SPENT`, consumed=true, exit 1. The
refusal is an expected negative boundary check, not a second experiment or
a failed original execution. It occurs before input regeneration or search.
The committed output and consumed PUBLIC claim remain unchanged.

## Byte equality and retained adverse PUBLIC results

A separate read-only comparison checked the complete scientific record bytes
in all 1,024 old/new PUBLIC cells. All match exactly, while all 1,024 outer
cell identifiers differ as required. After mapping each old outer identifier
to its corresponding new identifier, the full mechanism, terminal-error and
exact-success reductions match, along with stage order and claim-boundary flags.
The ordered trace-hash matrix SHA-256 is
`0f4260b1c4550d9562cbc222590c8220d86a22fe7ee08fc070b8a2597338a63f`.
For this comparison, a scientific record and the ordered hash matrix are encoded
as sorted compact UTF-8 JSON with a final LF. This is a comparison of one fixed
PUBLIC schedule, not an additional independent scientific sample.

The PUBLIC numerical screen remains false. Each arm has denominator 256:

| Budget | Scale 0 exact | Scale 16 exact | Paired rescues / lost exact | Terminal-error wins / ties / losses |
| --- | ---: | ---: | --- | --- |
| 256 | 70 | 74 | 12 / 8 | 23 / 215 / 18 |
| 512 | 128 | 136 | 32 / 24 | 43 / 174 / 39 |

The high-budget net uplift is 8/256; interaction is 4/256. Both numerators are
below the required 11. The 24 high-budget lost exact successes also fail the
no-loss guard. High-budget paired rescues span 25 definitions; this is distinct
from any-seed solved counts of 55 versus 57 definitions. All 64 task rows,
16 patterns, 64 leave-one-out rows at 252 blocks each, error vectors, first hits
and mechanism/support rows remain in the full summary. PUBLIC definitions share
one source; no QMC superiority, causal effect or population inference follows.

## Tracked artifacts and reproducibility anchors

The following are byte-identical copies, checked with byte comparison, not
rewritten or regenerated evidence:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| [PUBLIC candidate](../qualifications/countdown_feedback_budget_v7_connector_public_20260913.authorization.json) | 154928 | `aceba9543b81ad77682073155328231f2977cba27ce3e85938c0473c2d4c79df` |
| [COMMIT](../qualifications/countdown_feedback_budget_v7_connector_public_20260913.commit.json) | 146413 | `7fb43d6576b96ecfae1afbf97cdd63a4cfdb0812f06046355ff47b5c98f8f917` |
| [Independent summary](../qualifications/countdown_feedback_budget_v7_connector_public_20260913.summary.json) | 4019917 | `a12f487cf15c2a58c59cda6f2995127f09148cf01f7f5f3c57bf192b4b156f57` |

COMMIT digest: `d7bb7ae57e7642c6b1d4aed07a161e48654aac5364b31eb94b51e2ee03c2c14e`.
The independent analyzer and the separate saved-summary verifier returned the
same digest: `4511f9bc8ea0c5dacac292ae3d90f6009af8820b5744f46b8b85c1e5a72f57ec`.
Every independent process requalified the same 32 component/anchor traces;
baseline digest: `0ac349000421b652da51fdab4becedd18b790af35580cc027d470b153d6355bf`.
Source digest: `52ddca4054dc29336fd1701d17723d024807b286ca868553a5e4f5e84178fd06`.
Verified identity-authority digest: `dad2f18c19af77ddc87451d37f4504dd3f3c3dd4fe67f1e1a3ab1400fa81f42f`.
Run-binding digest: `8baf4d5cdf49a071f72401bfe6ade4f370fcf6266cafbe1d81c522ddb8598326`.

Raw STARTED is 157485 bytes, SHA-256
`0559549028b4aeb00aca966f7eec5ba1c7fec8c06e5b56865480bdb590dcc3e3`; raw RECEIPT is 3865645 bytes,
SHA-256 `a736c5ca0938e226238728d7f87e29e94fbe3a97f3f99f10577ce8feb373c32b`.
The raw publication and receiver-local claim remain local/ignored. Replaying or
admitting this qualification still requires those raw files and its original
authorization path, not just the tracked summary. Copying or publishing these
files never grants replication permission.

Ignored console captures share the prefix
`artifacts/work/feedback-budget-v7-connector-20260913.`:

| Suffix | Bytes | SHA-256 |
| --- | ---: | --- |
| `connector-focused.captured.log` | 7178 | `1a90df4906ee4700f79f40b864c7320852313cfd5f1d976a88f19b7407e726a8` |
| `corrected-admission-focused.captured.log` | 4480 | `e0e66d9f86005260c3ebfaddc0139d439eb88660f292f43c01e1ed571973e4c5` |
| `initial-admission-focused.captured.log` | 5567 | `10aab3841dfd51e826ac3ecb6919dab08289ba9730489f84a42f7ba6005b58b8` |
| `interrupted-validation.captured.log` | 15888 | `e1d812d75bcbba760f3971fb8e5c8332e89a244880b01f6dfe07306630d26598` |
| `public-analyze.captured.log` | 328 | `bd84a92aed84858d3424250cfe25e43ae97706b2c92824c567b34e018b3a6c68` |
| `public-comparison.captured.log` | 426 | `6480a31b4c9fc9434de56eacac7cf48dd14ee9955ae91763d61c86e522804eef` |
| `public-prepare.captured.log` | 334 | `c25947f5461b8d45e696a42475e75b1075d088cc5afd6ddb341ba00f6921b849` |
| `public-run.captured.log` | 2525 | `258d7bf154d95554e61f8ef0376b6a9a575c6249b800ede3632f4cef3dc3bb77` |
| `public-spent-denial.captured.log` | 235 | `2d75538acccb45204c1c37de5ea8787c14af2e3bbd1b959a61738c8a88d43324` |
| `public-verify.captured.log` | 328 | `bd84a92aed84858d3424250cfe25e43ae97706b2c92824c567b34e018b3a6c68` |
| `source-runtime-preflight.captured.log` | 2167 | `a3d016999821eb1164aef6cfac6db1f3e215311ce4432b9ae1f667669945b105` |
| `validation.captured.log` | 243062 | `f0dad26a8b751e9720c96a66d0d568473e6f2d6b9a13a4e39a29e59d841fd221` |

The successful validator capture contains an early tool-output truncation
marker and is therefore not a complete per-test transcript. Its final
1,183-test OK, final validator PASS and exit 0 were retained. The interrupted
capture is only the deliberately incomplete attempt. Console captures are not
scientific traces. The actual publication closure and saved summary were
independently verified as described above.

## Remaining explicit authority gates

The new fixed PUBLIC connector has now been implemented and exercised through
consumption, actual 1,024-cell execution, independent analysis/save and independent
saved-summary verification, with the complete currently used fixture inventory
above. This does not qualify an actual positive 64-source seal by unit mocks.

The fixed real cohort slot
`artifacts/work/feedback-budget-replication-cohort-v7` is still absent.
The new ledger contains only its consumed PUBLIC claim; no replication claim,
real replication task, real execution candidate or replication result exists.

The next separate permission is one generation and sealing of the frozen
64-source recipe (seed 26091301; maximum 10,000 candidates), independent seal
verification and preparation of a non-authorizing exact execution candidate.
That candidate then needs review and explicit permission for its one complete
1,024-cell replication run and independent analysis/verification. Generic
readiness, hashes, sealing, merge and the PUBLIC result are not that permission.

No provider, API credential, GPU/furnace workload, locked-128 evaluation,
external push, PR change or merge was used in this turn. No population,
causal, performance-superiority, hosted-CI, cross-host or physical power-loss
certification is claimed. Source-producing files remain unchanged after
qualification; this later record only promotes artifacts and documentation.
