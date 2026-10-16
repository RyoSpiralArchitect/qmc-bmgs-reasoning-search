"""v7 PUBLIC execution/replay kernel; no replication task or authority input.

The future sealed-replication input/authorization loader is deliberately absent.
Neither candidate identities nor an old/public authorization admit a new task.
"""

from __future__ import annotations

import importlib.util
from itertools import product
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = "scripts/feedback_budget_replication_kernel.py"
CONTRACT = "scripts/feedback_budget_replication_contract.py"
FIXTURE = "docs/fixtures/countdown_feedback_budget_v7_public.json"
MODE = "nondiagnostic_replication_full_shape_fixture"
FIXTURE_ID = "feedback_budget_replication_public_1024/v1"


def load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load pinned sibling")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


contract = load("feedback_budget_replication_contract_kernel", CONTRACT)
q, core = contract.q, contract.core
canonical, digest, require = q.canonical, q.sha256_json, q.require
DOMAIN, ARMS = contract.PUBLIC_DOMAIN, contract.ARMS
COORDINATES = tuple(product(range(64), q.BUDGETS, q.SCALES, q.SEEDS))


def fixture_manifest() -> dict:
    """Use exactly the planned PUBLIC bytes; executing them does not change them."""
    return contract.build_public_schedule()


class FixtureInputs:
    """Exact fixed manifest; detached values without reparsing 1024 cells per step."""

    __slots__ = ("_raw", "_cell_raw", "_task_raw", "_header_raw")

    def __init__(self, raw: bytes):
        value = contract.validate_public_schedule(raw)
        object.__setattr__(self, "_raw", raw)
        object.__setattr__(
            self, "_cell_raw", tuple(canonical(c) for c in value["cells"])
        )
        object.__setattr__(
            self, "_task_raw", tuple(canonical(t) for t in value["tasks"])
        )
        object.__setattr__(
            self,
            "_header_raw",
            canonical(
                {
                    f: value[f]
                    for f in (
                        "deterministic_digest",
                        "contract_digest",
                        "schedule_digest",
                    )
                }
            ),
        )

    def __setattr__(self, name, value):
        raise AttributeError("fixed PUBLIC execution inputs are immutable")

    @property
    def manifest(self):
        return core.parse_canonical(self._raw)

    @property
    def header(self):
        return core.parse_canonical(self._header_raw)

    @property
    def cells(self):
        return [core.parse_canonical(raw) for raw in self._cell_raw]

    def arguments(self, cell: dict) -> dict:
        require(
            type(cell) is dict and type(cell.get("cell_index")) is int,
            "plain indexed cell required",
        )
        index = cell["cell_index"]
        require(0 <= index < 1024, "cell outside fixed schedule")
        require(
            canonical(cell) == self._cell_raw[index], "PUBLIC cell identity differs"
        )
        key = core.parse_canonical(self._cell_raw[index])["cell_key"]
        task = core.parse_canonical(self._task_raw[key["task_slot"]])
        return dict(
            task=q.CountdownTask(tuple(task["inputs"]), task["target"]),
            proposal=q.PROPOSAL,
            method=q.method(key["scale"]),
            budget_profile=q.profile(key["budget"]),
            exploration_seed=key["seed"],
        )


def public_inputs() -> FixtureInputs:
    return FixtureInputs(canonical(fixture_manifest()))


def binding(
    inputs: FixtureInputs, source: dict, runtime: dict, qualification: dict
) -> dict:
    require(type(inputs) is FixtureInputs, "fixed PUBLIC inputs required")
    manifest = inputs.header
    return core.with_digest(
        dict(
            schema_version=DOMAIN + "/run-binding",
            execution_mode=MODE,
            experiment_id=FIXTURE_ID,
            expected_cell_count=1024,
            fixture_manifest_digest=manifest["deterministic_digest"],
            contract_digest=manifest["contract_digest"],
            schedule_digest=manifest["schedule_digest"],
            source=source,
            runtime=runtime,
            qualification=qualification,
            replication_execution_authorized=False,
        )
    )


def validate_binding(inputs: FixtureInputs, value: dict) -> None:
    core.require_digest(value)
    require(
        all(type(value.get(k)) is dict for k in ("source", "runtime", "qualification")),
        "binding components required",
    )
    expected = binding(
        inputs, value["source"], value["runtime"], value["qualification"]
    )
    require(canonical(value) == canonical(expected), "fixture run-binding differs")
    # Admission is the runner/analyzer's independent source/runtime qualification,
    # NOT possession of this well-formed storage binding.


def record(inputs: FixtureInputs, cell: dict, run_binding: dict) -> dict:
    validate_binding(inputs, run_binding)
    result = q.run_countdown_track_a_search(**inputs.arguments(cell))
    return core.with_digest(
        dict(
            schema_version=DOMAIN + "/record",
            **cell,
            run_binding_digest=run_binding["deterministic_digest"],
            search_record=result.record,
        )
    )


def validate_envelopes(
    inputs: FixtureInputs, rows: list[dict], run_binding: dict
) -> None:
    validate_binding(inputs, run_binding)
    require(type(rows) is list and len(rows) == 1024, "exactly 1024 records required")
    fields = {
        "schema_version",
        "cell_index",
        "cell_id",
        "cell_key",
        "search_record",
        "run_binding_digest",
        "deterministic_digest",
    }
    for cell, row in zip(inputs.cells, rows):
        require(type(row) is dict and set(row) == fields, "record fields differ")
        core.require_digest(row)
        require(row["schema_version"] == DOMAIN + "/record", "record domain differs")
        require(
            canonical({key: row[key] for key in cell}) == canonical(cell),
            "complete ordered schedule differs",
        )
        require(
            row["run_binding_digest"] == run_binding["deterministic_digest"],
            "record run-binding differs",
        )
        require(type(row["search_record"]) is dict, "search record must be an object")
        require(
            canonical(row["search_record"].get("run_identity"))
            == canonical(q.build_search_run_identity(**inputs.arguments(cell))),
            "search identity differs",
        )


def prefix_pair(low: dict, high: dict) -> dict:
    """Full-event integrity and completion only, before outcome reductions."""
    lo, hi = q.accepted_events(low), q.accepted_events(high)
    require(
        canonical(lo) == canonical(hi[: len(lo)]), "full accepted-event prefix differs"
    )

    def terminals(events):
        return [
            e["payload"]["trajectory_index"]
            for e in events
            if e["kind"] == "terminal_verified"
        ]

    lt, ht, added = terminals(lo), terminals(hi), terminals(hi[len(lo) :])
    require(
        bool(lt) and len(ht) >= len(lt) + 1 and len(ht) >= 3,
        "structural completion guarantee violated",
    )
    require(
        bool(added) and added[0] == len(lt),
        "current-next trajectory did not complete first",
    )
    return dict(
        low_event_count=len(lo),
        high_event_count=len(hi),
        prefix_digest=digest(lo),
        low_terminal_count=len(lt),
        high_terminal_count=len(ht),
        added_terminal_count=len(added),
        added_trajectory_ids=added,
        current_next_trajectory=len(lt),
        current_next_completed_first=True,
        status="EXACT_PREFIX_AND_COMPLETION_PASS",
    )


def replay_matrix(inputs: FixtureInputs, rows: list[dict], run_binding: dict):
    # ALL identities, including cell 1023, close before the first generative replay.
    validate_envelopes(inputs, rows, run_binding)
    records, receipts = {}, []
    for coordinate, cell, row in zip(COORDINATES, inputs.cells, rows):
        args = inputs.arguments(cell)
        identity = digest(q.build_search_run_identity(**args))
        raw = canonical(row["search_record"])
        replayed = q.replay_countdown_track_a_search_bytes(
            raw, **args, expected_run_identity_digest=identity
        )
        require(raw == replayed, "replayed bytes differ")
        trace = q.validate_trace_bytes(replayed)
        evidence = q.validate_budget(trace, args["budget_profile"])
        records[coordinate] = trace
        receipts.append(
            dict(
                cell_index=cell["cell_index"],
                cell_id=cell["cell_id"],
                record_digest=row["deterministic_digest"],
                run_identity_digest=identity,
                trace_sha256=q.sha(raw),
                trace_byte_count=len(raw),
                budget_evidence=evidence,
                replay={"stage1_generative": "PASS", "stage2_byte_identical": "PASS"},
            )
        )
    cells = dict(zip(COORDINATES, inputs.cells))
    pairs = []
    for slot, scale, seed in product(range(64), q.SCALES, q.SEEDS):
        low, high = (slot, 256, scale, seed), (slot, 512, scale, seed)
        pairs.append(
            dict(
                task_slot=slot,
                scale=scale,
                seed=seed,
                low_cell_id=cells[low]["cell_id"],
                high_cell_id=cells[high]["cell_id"],
                **prefix_pair(records[low], records[high]),
            )
        )
    return records, core.with_digest(
        dict(
            schema_version=DOMAIN + "/integrity-analysis",
            cell_count=1024,
            replayed_trace_count=1024,
            budget_prefix_check_count=512,
            cell_receipts=receipts,
            budget_prefix_checks=pairs,
            provider_calls=0,
            status="REPLAY_AND_PREFIX_PASS",
        )
    )
