# Allocation qualification: isolated checkout blocker

The frozen candidate is `aab59d3b7bd1c09456dcf19c0ad7cf96664145d9` with plan digest
`65004f3fa72438da18aa24296afc70405f40d234f6a2176640235f4f23e8f696`. All 26 new allocation tests passed, including in the captured full
suite. Ruff and compilation passed. Read-only plan regeneration matched all
55 source references and all 470 merged-parent files.

Full repository qualification **failed** in the isolated checkout. From
2026-10-21T23:03:44.587639+00:00 to 2026-10-21T23:18:22.804413+00:00, `scripts/validate.py`
ran 1,565 tests in 874.635 seconds and returned **29 failures, 22 errors,
zero recorded skips, exit 1**. Several legacy class setups failed, so this is
not complete coverage of all collected methods. Later artifact verification
and CLI self-test phases were not reached. There is no repository PASS claim.
The [failure receipt](../qualifications/countdown_feedback_allocation_development_20261022.isolated-validation.json)
is byte-identical to the retained raw process receipt and binds stdout,
stderr, the helper, input inventory and plan. The successful qualification
filename expected by the execution gate remains absent.

## Existing environment dependencies reproduced on unchanged main

The receiver authorization validator compares saved `output_path` directly
with `str(output_for(mode))`; its saved evidence names
`/Users/ryohiga/SpiralReality/qmc-bmgs-reasoning-search`. Relocation therefore
fails with `fixed coordinator attempt differs`, `fixed lexical path required`
and related historical path checks. Fresh clones also omit local historical
`STARTED.json` and `SEALED.json` fixture artifacts. Copying those files alone
would not repair the fixed absolute-path mismatch. Do not rewrite their bytes
or relax the admission checks to turn this run green.

A separate disposable checkout of **unchanged merged PR30** at
`2fc168157f9d4adc039f6a330d65e0361b31bb15` reproduced all **51 identical
failure/error test identities** across the eight affected legacy modules:
149 tests in 21.027 seconds, 29 failures and 22 errors. It contained none of
the allocation implementation. This is evidence of the existing environment
binding; it does not substitute for a passing candidate full suite.
The [diagnosis receipt](../qualifications/countdown_feedback_allocation_development_20261022.portability-diagnosis.json)
binds that reproduction and the failing test identities.

## Preserved state and pending actions

Before/after preservation checks passed with no errors: 477 candidate tracked
files, all 470 merged-parent files, 5,329 protected files, 5,808 inventoried
original files including tracked files, 20 original directory memberships and
six absent original-study/production slots. The new study and new approval
receipt remain absent. The original checkout and its protected evidence were
not edited or moved. The proposal filename and bytes remain exact.

This records-only descendant adds the failed attempt and diagnosis; it does
not change the candidate or plan, rerun the study, claim full qualification,
or turn the existing direction approval into execution consent. No default
is selected. The PR stays draft and is not authorized for merge.

The blocked action is full qualification of the frozen candidate in an
isolated checkout compatible with the historical evidence environment. The
attempt **failed; remediation is pending, not denied by automatic approval**.
The original-path checkout cannot be replaced, edited or moved under the
current isolation and preservation instructions. A canonical-path validation
arrangement or an explicitly reviewed portability remedy is required first.

After full qualification passes, the exact human execution approval still
needed is: **candidate `aab59d3b7bd1c09456dcf19c0ad7cf96664145d9` and plan
`65004f3fa72438da18aa24296afc70405f40d234f6a2176640235f4f23e8f696` for one bounded run and one separate-process complete analysis**.
The [original proposal](../strategy/countdown_feedback_diversity_allocation_proposal_20261022.md)
requires this new exact-plan approval. The requested 64-source, eight-seed,
three-arm comparison remains entirely unexecuted.
