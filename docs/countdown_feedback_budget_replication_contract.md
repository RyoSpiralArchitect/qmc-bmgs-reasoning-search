# Feedback × budget v7: outcome-blind contract and PUBLIC identities

This implements the contract-construction step of the
[frozen v7 design](strategy/countdown_thompson_feedback_budget_confirmation_v7.md).
It compiles a separately domain-bound contract, a synthetic identity-only
1,024-cell schedule, and a planned PUBLIC schedule. **It does not generate or
seal the new 64-task cohort, execute search, analyze outcomes, qualify a new
pipeline, publish a run, or grant permission.** The v6 implementation and its
consumed development execution remain unchanged.

## Fixed inputs and complete current exclusion union

`scripts/feedback_budget_replication_contract.py` verifies the old pinned
contract inputs, frozen v7 design/checker, v6 seal transaction, reviewed candidate,
result summary/COMMIT linkage, helper file bytes and the
[new PUBLIC identity manifest](fixtures/countdown_feedback_budget_v7_public.json).
It reconstructs all twelve v6 task identities without invoking the generator or
solver. Prior outcomes never select which v6 tasks to exclude. All input
snapshots are revalidated after the new contract or schedule is assembled.

| Exclusion group | Full-task identities | Source-multiset identities |
| --- | ---: | ---: |
| Historical | 2 | 2 |
| Canary | 12 | 12 |
| Locked reservation, identity exclusion only | 128 | 128 |
| Diagnostic | 12 | 12 |
| Dense-scale development | 12 | 12 |
| v6 PUBLIC fixtures | 13 | 1 |
| All v6 feedback-budget development tasks | 12 | 12 |
| v7 planned PUBLIC fixtures | 65 | 1 |
| **Deduplicated union** | **243** | **179** |

The last PUBLIC group intentionally includes all 13 old PUBLIC identities and
their one source. Only that exact overlap is allowed; the eight groups are not
claimed to be mutually disjoint. Adding v7 PUBLIC definitions adds 52 full-task
identities and **no additional source multiset**. Neither 243 fingerprints nor
65 PUBLIC definitions is a count of independent performance tasks.

The full-shape PUBLIC fixture fixes input multiset `[1,2,3,4,5,6]` with targets
`1..64`, plus the unchanged component-qualification task with target `720`.
These definitions are chosen for software shape/identity checks, not selected
for success or solvability. No solver or search was used to choose them.
Every target shares one source, which is entirely excluded from replication.
The identity manifest pins the unchanged 24-cell component schedule and the
eight-anchor qualification digest; those references are not fresh execution
receipts.

This is closure over the **currently defined** fixtures. Every additional
fixture identity or variant actually used by the future pipeline must be
amended into the frozen manifest and exclusion union before any cohort
generation. A planned manifest is not evidence that all future qualification
variants have already been executed or inventoried.

## Identity-only candidate and PUBLIC schedule

The replication recipe remains 64 source-distinct solvable D6 tasks, generation
seed `26091301`, at most 10,000 attempts, unchanged exhaustive solvability and
identity filtering, no hardness selection, generator acceptance order, and no
persisted witnesses. This compiler describes that recipe but never invokes it.
The budgets, search methods, proposal and required runtime specification are
copied exactly from the v6 contract; unchanged specifications are not a claim
that the v7 runner has passed qualification.

`build_schedule_candidate()` accepts exactly 64 ordered rows containing only
`task_slot`, `task_fingerprint`, and `source_multiset_fingerprint`. Both identity
kinds must be unique, well-formed, and outside all exclusions. Numeric aliases,
unknown fields, outcomes and witness fields are rejected. This proves identity
shape and exclusion membership only: the two supplied hashes are not verified
against real task definitions, a solvability result, or generator order.

The candidate deterministically binds 1,024 full cell keys, 512 same-scale
budget-prefix pairs and 256 four-arm blocks. Every key includes both identities,
the whole identity-set digest, contract digest, all factors, and budget/method/
proposal digests. Changing one identity rekeys the whole schedule. Validation
requires exact canonical JSON and full reconstruction, not just a valid digest.

Replication candidate keys, planned PUBLIC keys, and future production keys
are separate schemas within the new confirmation domain. PUBLIC keys also bind
their fixed manifest, fixture identity and non-diagnostic execution mode. The
old 192-cell candidate validator rejects this new candidate, and vice versa;
neither compiler invokes the old connector. No count change or relabeled v6
receipt qualifies the new pipeline.

Every returned object keeps generation, sealing, runtime/source qualification,
runner/analyzer/publication/admission qualification and execution-authority flags
false. Planned protocol names and screen thresholds are metadata, not implemented
production entrypoints or screen decisions. The frozen design remains the
complete decision and integrity specification, including low-budget non-harm,
zero high-budget lost exact successes, task breadth, leave-one-task-out outputs,
and prior differing-backup support for every high-budget rescue.

Helper hashes check current on-disk bytes. They do not attest the executing
interpreter, transitive imports or loaded bytecode; source/runtime qualification
remains an explicit separate gate. Data digests are not signatures or executable
attestations.

## Local checks and qualification plan

With this checkout's `src` on `PYTHONPATH`, these four read-only modes also work
when invoked by absolute path from outside the checkout:

```sh
python3 -P -B scripts/feedback_budget_replication_contract.py --manifest
python3 -P -B scripts/feedback_budget_replication_contract.py --public-identities
python3 -P -B scripts/feedback_budget_replication_contract.py --public-schedule
python3 -P -B scripts/feedback_budget_replication_contract.py --self-test
```

The CLI only writes canonical JSON to stdout. It has no generation, sealing,
execution, authorization, task input, seed override or output-directory mode.
The self-test hashes labelled synthetic strings for 64 identity rows and checks
both synthetic and planned PUBLIC layouts without search/replay/runtime probing.
Its status is `REPLICATION_CONTRACT_SYNTHETIC_PASS_NOT_AUTHORIZED`.

The [dated review/validation note](reviews/countdown_feedback_budget_replication_contract_20260913.md)
records the 31 focused tests, 1,074-test full validation, independent fresh-eye
review, exact metadata digests and unchanged execution/qualification boundaries.

The planned next qualification must independently exercise the unchanged
32 component/anchor traces and the new full-shaped PUBLIC pipeline: all 1,024
cells, two-stage independent replay, ordered outcome-redacted mechanism analysis,
512 accepted-event prefixes, 256 four-arm blocks, sole-primary-budget stopping,
completion bounds, saved-summary verification, strict JSON/identity negatives,
and one-shot admission/consumption/publication failures. Old qualification
receipts are historical inputs, not qualifications transferred to this pipeline.

Only after that implementation, review, actual qualification and complete
fixture-variant closure can separate cohort-generation permission lead to one
verified 64-task seal. Review of an exact execution candidate and explicit
permission for its one complete run follow separately. The old consumed claim,
locked-128 reservation and historical evidence are untouched. Contract tests
alone establish no new search-performance result.
