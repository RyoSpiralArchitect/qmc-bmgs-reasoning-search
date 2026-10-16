# v7 replication contract: fresh review and validation

Date: 2026-09-13 (Asia/Tokyo). Implementation reviewed:
`37bd8294f6058dd3b675ed7b936433dd93b64113`, against
`692b9a8b62731697f953973c81f3ead6849b9353`.

Scope: [non-authorizing v7 contract/compiler](../countdown_feedback_budget_replication_contract.md),
fixed PUBLIC identity definitions, tests and README. The frozen v7 scientific
design, existing search implementation, v6 pipeline and historical evidence
bytes are unchanged. This is not an execution candidate or qualification receipt.

## Fresh reviewer output

The reviewer received a complete local clone of the reviewed commit, no parent
conversation history, and a read-only brief. The clone's project-local
`AGENTS.md` was temporarily hidden; user-level files and the operator checkout
were not hidden or changed. This is best-effort fresh-eye review, not a claim
of literal context erasure. The hidden file was restored immediately on review
completion, and the clone's working tree was verified clean.

Reviewer output, preserved separately from operator interpretation:

> No actionable P1/P2 findings for HEAD
> `37bd8294f6058dd3b675ed7b936433dd93b64113` against base
> `692b9a8b62731697f953973c81f3ead6849b9353`.
>
> Reviewed all five changed files, the frozen v7 design/checker, historical v6
> contract, and supporting canonical-JSON/file-snapshot boundaries.
>
> Validated:
>
> - 30 focused read-only tests passed, including all four CLI modes, exact
>   reconstruction, input drift, mutation isolation, and v6/v7 rejection.
> - Independently rejected every excluded identity: 243 full-task fingerprints
>   and 179 source fingerprints.
> - Independently checked both complete 1,024-cell coordinate sets, their
>   combined 1,024 prefix pairs, and 512 four-arm blocks.
> - Confirmed all twelve v6 tasks are excluded; PUBLIC overlap is intentionally
>   exactly 13 task identities and one source.
> - Documentation and returned metadata distinguish fixture definitions,
>   synthetic schedules, historical receipts, actual qualification, and permission.
>
> Limitations: no full validator, generation, solving, search, replay, runtime
> qualification, provider/network calls, or file mutations. The filesystem-alias
> test that creates temporary files was not run; that boundary was inspected
> statically. Missing production and authorization gates are explicitly deferred
> design work, not implementation defects.

## Operator annotation

The review is consistent with the implemented scope. The operator also ran the
filesystem-alias test, bringing the focused suite to **31 passing tests**. The
reviewer's combined 1,024 pairs and 512 blocks belong to **two planned layouts**:
each layout has 1,024 cells, 512 pairs and 256 blocks. These are not two executed
studies. Likewise, 422 rejected identity values means 243 task hashes plus 179
source hashes, not 422 independent problems.

All twelve v6 development tasks remain excluded without outcome-dependent
selection. The old PUBLIC fixture group is intentionally contained in the new
65-definition PUBLIC group; their single common input source is excluded as a
whole. Source/runtime attestation, new-domain runner/analyzer/publication/admission,
actual full-pipeline qualification and closure over every fixture variant used
remain unmet. New cohort generation and exact-candidate run permission are
separate later gates. No old consumed authorization or locked reservation was
opened for new execution.

An initial focused run had 29 passes and one test error: the new no-operation
test referred to nonexistent `calibrate_countdown_task`. It was corrected to
patch the actual `calibrate_task` entrypoint and also cover the candidate
generator and pool calibration. A subsequent complete-screen metadata test
raised the focused total to 31. No failing scientific result was removed.

## Validation evidence

The operator's final focused command:

```sh
PYTHONPATH="$PWD/src" python3 -B -m unittest discover -s tests \
  -p test_feedback_budget_replication_contract.py -v
```

Result: **31 tests passed in 11.936 seconds**. Ruff format/check and
`git diff --check` also passed. All four CLI modes are covered from outside the
checkout using absolute script/PYTHONPATH locations. The metadata self-test
reported `REPLICATION_CONTRACT_SYNTHETIC_PASS_NOT_AUTHORIZED`.

Full repository validation used the same implementation revision, CPython
3.13.13 on Darwin arm64, this checkout's absolute `src` path, and a newly created
private bytecode-cache directory:

```sh
PYTHONPATH="$PWD/src" \
PYTHONPYCACHEPREFIX=/private/tmp/qmc-v7-contract-pyc.OOyfpT \
python3 -B scripts/validate.py
```

Result: **1,074 tests passed in 523.180 seconds, no skips**; all subsequent
artifact/provenance checks, outside-checkout CLI self-tests and the saved v5 seal
verification completed. Final output was `repository validation: PASS`, exit 0.
The 523.180 seconds describes the unittest phase, not total validator wall time.
The existing validator also exercises legacy software fixtures; it does not
qualify the unimplemented v7 production pipeline or run its new cohort.

A local, ignored console capture is retained at
`artifacts/work/feedback-budget-v7-contract-validation-20260913.captured.log`:
193,621 bytes, SHA-256
`f57f2b01313bb1cd87ce0ecd81b3bfcd4dda4d73fe3f94c0155de5fde5d4af2e`.
One tool-output chunk was truncated during capture, so this is **not a complete
raw log**; it retains the test summary and final validator status. It is neither
an experimental trace nor a qualification receipt. The later changes are this
review/validation note and a documentation link, not producing code changes.

## Reproducibility anchors

| Item | SHA-256 or deterministic digest |
| --- | --- |
| Compiler file SHA-256 | `5d1e69411916745856c7c49d22731d695882f1873fd884cb66540e0c37bd2704` |
| Focused tests file SHA-256 | `77ddcb4d02d90eb4d9b9c341636d5fb555a274f052989efdbffeef2964ae250c` |
| PUBLIC identity file SHA-256 | `38082634240650f3fbaf77875585419003fecfd310eaed3548346fa616782495` |
| PUBLIC identity digest | `18b94986944bce23ef6a867fd5b136dea18502116ac10e71286b69f3f64d3cb3` |
| Contract canonical-byte SHA-256 | `b144d7f963a2166a649e707edb9730075259f6df0cd01ef3ac3f806c47d20129` |
| Contract digest | `eba85e2dabfbe2ff52ffcc6e0ba9ec85b2d03ad8e718b98645d509bfa6e3a0a6` |
| Synthetic candidate digest | `ad4a6a3a1f948ceaeea06beacfed8477783eb8fc363a0cd9703590849137b95f` |
| Planned PUBLIC schedule digest | `1b1e13515e2036d764c6e05d023b61ed047af1e7f9615799f2a1b18e4a11e91b` |
| Metadata self-test digest | `8debdb18936492e1d47933747ebc503290cd4779f539945cf669786e62ee992b` |

The contract reads 17 fixed input files and emits 71,144 canonical bytes. These
digests bind metadata, not a source-qualified executable, a solvable cohort or
an authorized study. The PUBLIC identity file contains 65 definitions on one
source; its 64 full-shape definitions describe a software fixture, not 64
independent performance observations.
