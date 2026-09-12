# Feedback × budget v7: fixed PUBLIC execution pipeline

This is the PUBLIC-only execution, two-stage replay, ordered analysis and
one-shot storage path for the
[v7 contract](countdown_feedback_budget_replication_contract.md). It accepts only
the already fixed PUBLIC manifest: inputs `[1,2,3,4,5,6]`, targets `1..64`, four
seeds, scales 0/16 and budgets 256/512. Its 1,024 cells share **one input source**;
they are software qualification fixtures, not a 64-source replication study.

No task generator, cohort seal, replication input, authorization candidate,
provider call, optional sample-size extension or resume entrypoint is exposed.
The full PUBLIC schedule bytes/digest are unchanged from contract review. The
component baseline remains the existing target-720 task and eight unchanged
anchors. No additional arithmetic fixture definitions are introduced here.

## Execution and independent verification

`run_feedback_budget_replication_fixture.py` composes three dedicated
modules: a fixed-input kernel, ordered analysis and new-domain publication.
The existing v6 pipeline and search-source bytes remain unchanged; the new
modules do not alter their globals, accept their authorizations or relabel their
receipts. Low-level POSIX descriptor operations and unchanged search primitives
are reused, not their 192-cell publishers or production admission decisions.

Before execution, source qualification requires an exact clean Git checkout,
the original protected search-source closure, the new pipeline/helper files,
and the contract's fixed inputs. Approved source bytes must match both their
recorded commit and the current descendant commit. Loaded helper origins must
be exact source loaders without cached bytecode. Runtime qualification requires
the frozen CPython/Darwin-arm64/CPU-binary64 specification. All 32 baseline
component/anchor traces are independently reproduced and compared to the fixed
historical analysis; the resulting new-domain receipt records that reproduction.
Historical receipts alone do not admit execution.

Execution emits every cell into a fresh private output directory in the fixed
order. Before any generative replay, every outer record and complete underlying
search identity is validated, including cell 1,023. Then every trace undergoes
generative and byte-identical replay, sole-primary-budget stopping checks, and
all 512 full accepted-event budget-prefix/completion checks. Four-arm blocks
remain 256; the mathematical task denominator is 64 and each arm has 256 cells.

Mechanism projection/pairing precedes terminal-error and success reductions.
Outputs retain all 512 cross-scale pairs, all 256 budget-extension blocks,
opportunity bins, complete terminal-error/success vectors, first-hit indices,
all losses, all 64 task rows, all 16 success patterns, and 64 leave-one-task-out
rows with 252 blocks. The engineering screen uses exact effect numerators >=11,
rescue breadth >=11 tasks, low-budget non-harm, zero high-budget lost exact
successes and differing applied-backup support. Any-seed solved-task counts and
paired-rescue task counts are reported separately. A PUBLIC numeric screen
value never becomes a scientific decision or permission.

Analysis runs separately on the complete saved publication. It independently
revalidates source/runtime, reproduces the 32 baseline traces, replays all 1,024
saved cell records and recomputes the ordered reduction. The saved-summary
verifier repeats that independent analysis and requires exact canonical bytes.
The `public_pipeline_qualified` flag belongs only to this PUBLIC summary, not
replication admission or performance evidence. Source/runtime and publication
snapshots are checked again after reduction.

## Storage and operational bounds

The new namespace uses four-digit cell filenames, with durable `STARTED.json`
first and `COMMIT.json` last: 1,027 files for a complete publication. Exclusive
creation, exact path/inode/byte checks and complete directory closure prohibit
overwriting, adopting or resuming an occupied directory. Partial failures retain
their cells and a failure marker when that marker can be written unambiguously.
Uncertain post-commit states are retained without a countermanding failure file.
Separate summaries are also exclusive and revalidate their input publication.

Bounds are 8 MiB per cell, 64 MiB per control/summary object and 1 GiB for the
whole publication. The fixed publisher retains descriptor ownership, so a
preflight requires at least 1,152 descriptor slots before creating output or
running search; it does not silently raise system limits. An unmet bound stops
the run with retained evidence, not a smaller matrix or success-based stopping.

With this checkout's absolute `src` on `PYTHONPATH`, preflight is read-only:

```sh
python3 -P -B scripts/run_feedback_budget_replication_fixture.py --self-test
python3 -P -B scripts/run_feedback_budget_replication_fixture.py --manifest
```

Actual source-qualified operations additionally require a fresh, empty, owned
mode-0700 `PYTHONPYCACHEPREFIX` for **each process**. Output and summary paths must
be unused direct children of `artifacts/work`, without path aliases:

```sh
python3 -P -B scripts/run_feedback_budget_replication_fixture.py --run-public OUTPUT
python3 -P -B scripts/run_feedback_budget_replication_fixture.py --analyze-public OUTPUT --summary SUMMARY
python3 -P -B scripts/run_feedback_budget_replication_fixture.py --verify-public OUTPUT --summary SUMMARY
```

These commands authorize no replication task or later cohort. Full new-domain
production admission/consumption failure qualification, complete fixture-variant
closure, separate cohort-generation permission and exact-candidate run permission
remain later gates, even after this PUBLIC path passes. No old consumed study
claim is reused or cleared.
