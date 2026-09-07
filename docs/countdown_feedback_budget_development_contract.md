# Feedback × budget: development contract and schedule compiler

This is the first development-specific implementation layer after PR27's public
qualification. It builds a reproducible contract candidate and compiles
identity-only schedule candidates. **It does not generate or seal the new
cohort, run search, analyze outcomes, publish a run, or grant authorization.**

The [frozen scientific design](strategy/countdown_thompson_feedback_budget_factorial_v6.md)
is unchanged. The existing STOP and consumed authorization remain unchanged.

## Fixed inputs and identity exclusions

`scripts/feedback_budget_development_contract.py` reads six hash-pinned files:
the frozen v6 design, historical v5 preregistration, public fixture identities,
corrected 32-trace receipt, and public 192-cell commit and summary. It checks
canonical JSON/digests, the public commit/summary linkage, the current component
factories against the qualified budget/method specs, and each input snapshot
again after building the contract.

It retains all six identity boundaries separately:

| Boundary | Full-task identities | Source-multiset identities |
|---|---:|---:|
| Historical | 2 | 2 |
| Canary | 12 | 12 |
| Locked reservation, identities only | 128 | 128 |
| Diagnostic | 12 | 12 |
| Dense-scale development | 12 | 12 |
| Public feedback-budget fixtures | 13 | 1 |
| **Union** | **179** | **167** |

The 13 public tasks intentionally share one input multiset. This is not treated
as thirteen independent source groups. No historical outcomes or locked task
definitions are opened by this compiler. The historical preregistration is a
pinned identity input, not reused execution authority. This step does not
substitute for the future cohort builder's complete authority verification.

The fixed recipe remains 12 solvable D6 tasks, seed `26090401`, maximum 10000
attempts, six inputs in `[1,10]`, targets in `[100,999]`, generator acceptance
order, exhaustive-solvability/identity filtering only, and no stored witnesses
or hardness selection. The recipe is described but never invoked here.

## Candidate compiler

`build_schedule_candidate()` accepts exactly 12 ordered rows containing only
`task_slot`, full-task fingerprint, and source-multiset fingerprint. It rejects
duplicates, either identity kind overlapping any exclusion boundary, numeric
aliases, reordered slots, malformed hashes, and unknown fields such as outcomes
or solution witnesses. These are identity references, not verified task rows.

It deterministically constructs:

- 192 unique candidate cells in task → budget → scale → seed order;
- 96 same-task/scale/seed B256/B512 pairs, covering every cell once;
- 48 four-cell blocks in the frozen arm order `(Y0,256,Y16,256,Y0,512,Y16,512)`.

Every candidate cell key binds the complete contract and identity-set digests,
both task identities, all factor coordinates, and budget/method/proposal spec
digests. Changing even one candidate identity rekeys the entire schedule.
The canonical candidate validator independently regenerates the complete object;
rehashing reordered, omitted, or altered cells/pairs/blocks does not make them
valid. Returning a candidate copies inputs rather than retaining mutable aliases.

All candidate keys use a dedicated `candidate-cell-key` schema. They are not
the planned production `cell-key` schema and cannot be relabeled as a sealed
cohort or executable schedule. Solvability, generator order, cohort sealing,
production cell keys, and execution authorization stay explicitly false.

The contract reserves a new development domain,
`qmc-bmgs-countdown-thompson-feedback-budget/v1`, and distinct future
preregistration/cohort/record/run-binding/authorization/publication/analysis
schemas. Those reserved names are not implemented production protocols. Public
receipts and the old 384-cell authorization are not accepted as this candidate;
the old authorization validator also rejects the new contract/candidate objects.

## Run the checks

With the repository's `src` on `PYTHONPATH`:

```sh
python3 -P -B scripts/feedback_budget_development_contract.py --manifest
python3 -P -B scripts/feedback_budget_development_contract.py --self-test
```

The self-test reads the pinned inventory and hashes labelled synthetic strings
for the twelve task/source identities. It constructs no new Countdown inputs,
targets, solutions, or outcomes. The CLI has no task input, generation seed
override, generation, sealing, execution, or authorization option. It writes
only to stdout. Repository validation exercises it from outside the checkout.

On 2026-09-07 the contract digest was
`555018a2734587d417c71c7523f4420c3eec4a1ac47aa2d4fa4870f5feac4dce`,
and the synthetic schedule-candidate digest was
`35761709902de870b3f78e76bb0651bea99dcaaef3cc754e66b24d6e3cbbbe98`.
These bind the candidate data, not an attested producing executable or a study.

## Remaining gate

Implement and qualify the production runner/analyzer and their one-shot
publication path, with full source/runtime closure and a separate public
fixture. Then generate and seal the fresh excluded cohort, review an exact
execution authorization candidate, and obtain permission for one complete run.
No v6 development result, causal claim, method-quality improvement, or locked-128
authority follows from these contract/compiler tests.
