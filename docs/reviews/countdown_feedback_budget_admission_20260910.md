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

Fresh qualification and complete repository validation are pending for the new
admission executable. Positive seal tests use handwritten task rows and a mocked
generator/context, not an accepted development cohort.

During test development, the initial handwritten fixture overlapped two
historical source identities and was correctly rejected. Only the fixture was
corrected. Its temporary path initially used macOS's `/var` alias, correctly
rejected by no-follow storage; the test now uses the canonical temporary path.
Linked-file rejection raised the storage layer's RuntimeError subtype; the
assertion now accepts that failure family. No production guard was weakened.
