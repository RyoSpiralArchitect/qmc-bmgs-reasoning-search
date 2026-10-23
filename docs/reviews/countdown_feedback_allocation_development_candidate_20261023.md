# Allocation development candidate review

Status: **full repository validation PASS; exact-plan one-run/analysis approval
received**. At this qualification-completion record no new planned cohort,
run or analysis exists. This review is the implementing agent's code/contract
review and regression testing, not an independent reviewer endorsement.

## Fixed scope and evidence

Base: merged PR #30, `2fc168157f9d4adc039f6a330d65e0361b31bb15`.
The old470 tracked files are unchanged. New engine/statistics, one runner,
three test modules, strategy, plan and this review are additive only.

Plan: `docs/preregistrations/countdown_feedback_allocation_development_20261023.plan.json`.
Digest: `d88244d33e61f83bf878e77e3827ae3633ca6db08adb7f846a64631310f361e9`.
It binds 56 source/policy/test references, runtime, 284 excluded source
identities and 347 excluded task identities. Plan generation was outcome-blind
and did not call the task generator or search. Prior cohorts were read for
identity exclusion only; old result bytes and original study slots remain fixed.

The comparison holds total512 and dense16/stream derivation fixed: 512/0,
256/256, 384/128. It specifies 256 source clusters, eight fixed seeds65536–65543,
6,144 cells, 10,240 branch searches and 6,144 branch-prefix comparisons.
These are **planned**, not completed, denominators. Source count is not seed
replication count. All seven caps are conserved, every branch runs, and no
posterior/cache/outcome/unused work is shared. No default is promoted.

## Checks and limitations

- Excluded all-ones and `(2,2,3,4,5,7)` fixtures test primary256→384→512 and
  secondary128→256 decision/work prefixes with roots41/42. No planned source
  was generated for qualification. The old equal-diversity branch bytes match
  the new equal arm on the excluded regression input.
- Tests cover exact and missing readout, all-axis odd-cap conservation,
  secondary-guard invalidity, root/arm/type closure, canonical bytes, forged
  summary/channel/identity rejection, complete replay, exclusive publication,
  STARTED/COMMIT binding, post-analysis changes and refusal of partial retry.
- Independent hand calculations test source rational mean/variance and the
  approximate interval; tests retain negative, imprecise, degenerate and small
  samples. This is a second arithmetic check, not an external statistical audit.
- The sole primary readout is weighted-minus-single at the source level.
  Source SD0.4 yields the 0.05 half-width target at n256; this is a scenario,
  not an estimated SD or a power guarantee. Zero variance yields null interval.
  Fixed seeds, deterministic filtered generation and without-replacement source
  selection limit inference; approximate model coverage is not established.
- The prior six early losses/six early secondary gains are not substituted for
  a 384/128 counterfactual. New equal/weighted whole arms have no subset guarantee.
- Normal data-validation criteria were applied to units, denominators, exact
  moments, precision/readout ordering and unsupported population claims. The
  chosen 2pp practical uplift and 5pp precision target are explicit design choices.

An initial local test retained the old equal-budget expectation64 instead of
the intended weighted96/32 at total128. The test expectation was corrected;
the allocation implementation was not tuned to task outcomes. This was fixture
development, not a failed experiment or reattempt of the planned cohort.

## Qualification and authority

Ruff and 37 focused tests passed before candidate freeze. Full
`scripts/validate.py` ran once at `3221d5f5dd84f70af828ca5671b6bde983d91354`,
2026-10-23T07:18:31.021875Z to 07:36:21.311070Z. Exit0, 1,755 tests in916.792s,
OK/skip0 and final `repository validation: PASS`; postconditions errors empty
and before/after equal. The separate saved-evidence review checked all refs,
479 tracked Git bytes, 5,339 protected files, directory memberships, 56 source
refs and seven absent slots. Receipt:
`docs/qualifications/countdown_feedback_allocation_development_20261023.validation.json`,
4,441 bytes, SHA-256 `e4e3396cab5b426a8f205073ae4ee71c537f3386bcbf3613262b77fe278316ca`;
raw qualification receipt is byte-identical. This subsequent completion-only
commit changes the receipt and this review, not implementation or plan, and did
not rerun the suite. Local PASS does not assert hosted CI or external approval.

Ryō directly answered question item
`["request_user_input_async","call_b163e0dfb3dd4ace9ca24710a29dbc5c",0]`
with `全体検証PASS後の1回実行・解析を承認`. That question named the exact
candidate commit above and plan digest, conditional on full PASS and unchanged
implementation/plan. It covers only this one development attempt, fresh-process
complete analysis and result PR. The separate item1 authorized completion
monitoring. Raw human approval is recorded before execution; the frozen plan's
`execution_authorized:false` remains its candidate-time snapshot. Original C5,
locked evaluation, providers, old E4 reexecution, additional ratios/experiments,
automatic retry/resume and merge remain excluded.
