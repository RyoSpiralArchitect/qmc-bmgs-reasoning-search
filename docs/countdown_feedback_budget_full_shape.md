# Feedback × budget: complete 192-cell public fixture

This extends the [32-trace qualification](countdown_feedback_budget_public_qualification.md)
through execution, durable storage, and independent analysis of the full fixture
shape. The [original public identity manifest](fixtures/countdown_feedback_budget_v6_public.json)
remains unchanged: inputs `(1,2,3,4,5,6)`, targets 1–12, budgets 256/512, scales
0/16, and seeds 8192–8195. The
[exact 192-cell manifest](fixtures/countdown_feedback_budget_v6_full_shape.json)
binds every task, factor, component digest, cell key, and execution order.

## Execution and analysis

`run_feedback_budget_full_shape.py` reconstructs the fixed tasks without any
cohort generation or solvability/hardness selection. It first reproduces all 32
public qualification traces and requires their complete analysis to match the
previous tracked receipt. Every full-shape cell starts from empty search state.
The unchanged search package and the existing common guard profiles are used.

Before replay, the analyzer validates all 192 record identities, including the
last one, against the fixed ordered schedule. It then performs fresh generative
and byte-identical replay on each trace, checks sole-primary stopping and guard
accounting, and verifies all 96 same-scale B256/B512 event prefixes. Each prefix
retains all event payloads, indices, charges, and hash links. It also checks
`T256 >= 1`, `T512 >= 3`, `T512 >= T256 + 1`, actual current-next trajectory
completion, and monotone exact-success/minimum-error consequences.

The runner performs those integrity checks before committing. A separate
`--analyze` process rereads every saved cell and reconstructs the complete
receipt, then publishes an independent summary outside the closed input
directory. `--verify` repeats that analysis and compares all saved summary
bytes. These summaries describe fixture integrity; `scientific_decision` is
always null and `development_execution_authorized` is always false.

## Storage and failure handling

The fixture uses a dedicated domain,
`qmc-bmgs-feedback-budget-nondiagnostic-full-shape/v1`. Its storage wrapper uses
the existing low-level descriptor and file-sync primitives. It does not use
the old 240/384-cell publishers or their authorization objects.

Publication creates a new private directory, then durably records `STARTED.json`
before the first cell. Each `cell-000.json` through `cell-191.json` is exclusively
created and synchronized immediately. `RECEIPT.json` follows the complete
matrix checks; `COMMIT.json` is written last after source/runtime and file-set
revalidation. A committed artifact contains exactly 195 files.

Partial failure retains the occupied directory and completed cells. A known
precommit failure records `FAILURE.json`; uncertain publication, especially
after a commit attempt, reports uncertainty without a contradictory failure
marker. Existing directories, cells, and summaries are never overwritten,
resumed, or adopted. Independent inspection checks canonical bytes, schema,
ordered hashes, single-link regular files, directory/file generations, and
the complete path identity before and after analysis.

The durability claim covers the exercised local POSIX filesystem and current
host/path identity. It does not qualify remote filesystems, reboot recovery,
malicious same-user mutation, or a future production runner.

## Reproduction

Use a clean committed checkout with CPython 3.13.13, arm64 CPU float64,
Torch 2.11.0, and the unchanged search/IID conformance. Each command needs `-P -B`,
the checkout's `src` on `PYTHONPATH`, and a new empty mode-0700
`PYTHONPYCACHEPREFIX` outside the checkout. The wrapper and both imported sibling
scripts are checked against their exact Git bytes and source import origins.

```sh
python3 -P -B scripts/run_feedback_budget_full_shape.py --manifest
python3 -P -B scripts/run_feedback_budget_full_shape.py --run artifacts/work/feedback-budget-full-shape-v6
python3 -P -B scripts/run_feedback_budget_full_shape.py --analyze artifacts/work/feedback-budget-full-shape-v6 --summary artifacts/work/feedback-budget-full-shape-v6.summary.json
python3 -P -B scripts/run_feedback_budget_full_shape.py --verify artifacts/work/feedback-budget-full-shape-v6 --summary artifacts/work/feedback-budget-full-shape-v6.summary.json
```

Both output paths must be new direct children of the existing `artifacts/work`
directory. The summary is separate from the 195-file committed input directory.
Raw cell files stay local and ignored; the tracked manifest/summary binds their
hashes and counts.

## Scope after this gate

The twelve public targets share one source multiset and are intentionally
nondiagnostic. They are not a fresh development cohort, and their 96 prefix
checks do not substitute for the later development study's 96 checks. This PR
qualifies the full fixture shape and its own public storage/analysis path.
Production-domain schemas, outcome-blind cohort/seal builder, production
runner/analyzer and publication qualification, and a concrete execution
authorization candidate remain the next work. The prior STOP and consumed
authorization remain unchanged.
