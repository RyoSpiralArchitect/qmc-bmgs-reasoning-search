# PR28 fresh review and admission layer — 2026-09-10

## Fresh reviewer output: public path at 143b279

Read-only fresh subagent, no parent conversation, disk-blinded disposable clone;
base `6a375be06c3d1da0fc3618f176264ca473291355`, head
`143b279c61e4962a9b0afaacbdf3c37eff6e34d0`. Default project-local hiding only.
`AGENTS.md` was restored and the clone was clean immediately after completion.
This is best-effort fresh review, not removal of injected host context.

The reviewer's report follows:

> No actionable P1/P2 findings identified in `6a375be…143b279`.
>
> Checked:
>
> - Complete contract, candidate, fixture, cell and run-binding identities; rejection before replay.
> - Full accepted-event prefixes, current-next completion, first-divergence support and outcome-redacted mechanism ordering.
> - Exact factorial arithmetic, all 16 patterns, leave-one-task-out contrasts and conservative screen.
> - Exclusive publication, retained failures, uncertain commits, independent recomputation and late file-closure checks.
> - Tracked qualification canonical bytes/digests, summary–COMMIT linkage and producing-commit ancestry. All 59 source-receipt files match their producing revision and current checkout; all 192 trace hashes match the preceding public qualification.
>
> Validation: **77 tests passed, 60 subtests passed**, using Python 3.13, `-P -B`, checkout-specific `PYTHONPATH`, and disabled pytest cache. This includes fresh public 192-cell search/replay and 96 prefix checks.
>
> Boundaries: I did not run source-qualified CLI operations on the intentionally frozen checkout or inspect ignored raw qualification artifacts. Consequently, this is not an independent re-verification of the saved publication. Production cohort/seal and authorization admission remain explicitly unimplemented, not defects hidden by the public qualification.
>
> No project edits, external writes, provider calls, development generation or further delegation. Review complete; the operator can restore the hidden context now.

## Stateful annotation

No corrective public-path code change was required by that review. Its limits
are retained: code/unit evidence and tracked receipt checks are not independent
verification of the saved raw publication or production admission. The prior
qualification at `117c9a98` remains unchanged.

The operator independently re-verified the old v5 bundle: seal
`49f820692aa4f3551ca5634bdc89efe225fe05d1dc8acb8e814f231f3eea222f`,
384 historical schedule cells. This regenerated the **old** recipe/authority
chain, not the new 26090401 cohort.

The [new layer](../countdown_feedback_budget_development_admission.md) adds
verified identity authorities, outcome-blind cohort sealing/reconstruction and
review-only candidate admission. Production execution authorization and one-shot
consumption remain subsequent work. No fresh development cohort has been
generated, sealed or executed.

## Validation record

The corrected admission executable passed fresh qualification, separate-process
verification and complete repository validation, recorded below. Positive seal
tests use handwritten task rows and a mocked generator/context, not an accepted
development cohort.

During test development, the initial handwritten fixture overlapped two
historical source identities and was correctly rejected. Only the fixture was
corrected. Its temporary path initially used macOS's `/var` alias, correctly
rejected by no-follow storage; the test now uses the canonical temporary path.
Linked-file rejection raised the storage layer's RuntimeError subtype; the
assertion now accepts that failure family. No production guard was weakened.

## Fresh reviewer output: admission increment at 74c7f27

The second fresh read-only subagent reviewed `143b279..74c7f27` in the same
disposable clone with default project-local hiding. Restoration completed
immediately after its return; no user-level memories were hidden. Its report:

> One actionable P2 found; no P1 identified.
>
> [P2] Validate both transaction markers before regenerating the cohort
> (`feedback_budget_development_admission.py`, lines 533–543).
>
> `load_seal()` calls `validate_seal_bytes()` before validating `STARTED.json` or `SEALED.json`. That validator invokes the new recipe through `_cohort()` at line 451. Consequently, an interrupted final publication with a valid preregistration but empty/malformed `SEALED.json` reaches the generator/solver before the loader discovers that the transaction was never validly sealed. Malformed STARTED metadata has the same problem. This leaves transaction-content closure outside the promised reject-before-generation gate.
>
> Reproduction used the existing explicitly synthetic fixture, with source context and new generation mocked:
>
> - Replace `STARTED.json` with canonical `{}`: generator called once, then `KeyError: owner_nonce`.
> - Replace `SEALED.json` with canonical `{}`: generator called once, then `cohort final seal differs`.
>
> Close both markers and their linkage against the parsed preregistration before invoking exact recipe regeneration; add negatives asserting zero generator calls for malformed/partial markers.
>
> Validation: **30 tests and 55 subtests passed**; `git diff --check` passed. No actual new v6 generation, search, provider execution, source-qualified CLI, project edits, hidden context, memory, or prior review reports were used. The absent production execution/authorization-consumption connector is explicitly documented and is not a finding.

## Stateful annotation and correction

The P2 is correct. Transaction markers must close before the generation gate.
The loader now parses the preregistration and validates both canonical markers
and their byte/digest linkage before independent cohort regeneration. Regression
tests cover empty, malformed and `{}` markers plus five rehashed linkage lies,
requiring zero generator calls (and zero context calls for malformed markers).

The in-progress qualification and full validation of `74c7f27` were deliberately
interrupted after this finding, not reported as passes. The qualifier had already
created its summary slot and returned `INVALID_ADMISSION` / `PublicationUncertain`
after interruption during post-publication checks. Its occupied local file
`artifacts/work/feedback-budget-admission-v6-20260910.json` is retained, is not
promoted and is not a qualified receipt. The corrected executable requires a
new named qualification; the existing public experiment/receipt is unchanged.

## Reviewer follow-up: bounded fix verification

This was a targeted follow-up by the same reviewer, not another stateless review.
The clone was frozen/restored again with the same default scope. Report:

> The original P2 is resolved at `1f565588b673d8c16b62ed85a7ee140bbc973082`. `load_seal` now closes both markers and their linkage before calling `validate_seal_bytes()`.
>
> Verified:
>
> - Empty, `{}`, malformed, and rehashed linkage-invalid markers reject with **zero generator calls**.
> - A valid synthetic roundtrip follows: STARTED closure → SEALED closure → preregistration validation → exactly one **mocked** regeneration.
> - **6 targeted tests and 11 subtests passed**; `git diff --check` passed.
>
> No introduced regression found in this bounded patch. No actual v6 generation/search, source-qualified CLI, project edits, hidden context, memory, or delegation.

Stateful annotation: the reproduction and correction agree. The positive path
remains explicitly synthetic; neither review nor the fix authorizes execution.

## Corrected executable qualification and validation

Producing commit: `1f565588b673d8c16b62ed85a7ee140bbc973082`.
No protected admission/public executable changed after this qualification.

- Focused admission tests: **32 PASS** (48.297 seconds).
- Full `python3 -B scripts/validate.py`: **PASS, 985 tests**, no skips; unit-test
  duration **685.513 seconds**, not total script wall time. Compilation, Ruff,
  artifact/ancestry/design checks, all outside-checkout CLIs and old v5 seal
  verification also passed.
- Fresh `--qualify`: **PUBLIC_REPLAY_AND_IDENTITY_ADMISSION_PREFLIGHT_PASS**.
- Separate-process `--verify-qualification` with exact digest: **PASS**, complete
  canonical receipt bytes identical to the first qualification.
- Both processes used fresh private empty cache prefixes outside the repository,
  `-P -B`, and the clean committed producing checkout. Source stayed unchanged
  while they ran. No development generation or authorization was performed.

The accepted local receipt is
`artifacts/work/feedback-budget-admission-v6-20260910-r2.json`; the tracked copy is
[`countdown_feedback_budget_v6_admission_20260910.json`](../qualifications/countdown_feedback_budget_v6_admission_20260910.json).

| Binding | Value |
|---|---|
| Admission receipt digest | `c5f225bb1cc00be31429e888ddf334199e9da24b69fa00b382fca8c014648ce7` |
| Receipt file SHA-256 | `781581e2580f995e604dcd116d5c352e542bae2aaea7ee7d0a156b5b912aec34` |
| Receipt bytes | 64,546 |
| Independently verified public summary | `16788fa259223e5b6c41e931cc7176b3c9acf90345cbbb4f73218d6ab816163e` |
| Public matrix / exact prefixes | 192 / 96 |
| Excluded full-task / source identities | 179 / 167 |
| New development generation / execution | 0 / 0 |

The interrupted, unqualified first receipt remains local with SHA-256
`5d5983441e5c91c76cc5c4c20ffff841abaaf876346089a525d3827df7d9cc06`.
It is not the accepted/tracked qualification above. Interrupted and completed
console logs are retained under `artifacts/work/admission-*-20260910*.log`.

The ancestry guard now covers five receipts, including all nested admission
producing revisions. Receipt-bearing history must retain the actual producing
commits; no squash/rebase merge is acceptable. PR28 remains unmerged.

Claim ceiling: public raw replay, verified historical identity prerequisites,
synthetic positive sealing tests and review-candidate plumbing only. The real
cohort roundtrip is not performed. Production execution admission and one-shot
authorization consumption remain unimplemented; they must be qualified before
fresh cohort sealing and the exact authorization review/permission gate.
