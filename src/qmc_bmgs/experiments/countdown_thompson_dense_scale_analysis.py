"""Independent, outcome-ordered analysis of one dense-scale collective.

The public wrappers establish external authority and all-cell replay before
calling the pure reductions. Mechanism helpers receive only frozen allowlisted
selection/backup views, never terminal verification objects or raw records.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable, Sequence

from qmc_bmgs.substrate.trace import canonical_json, sha256_json

SUMMARY_SCHEMA = "qmc-bmgs-countdown-thompson-dense-scale-summary/v1"
FIXTURE_SUMMARY_SCHEMA = (
    "qmc-bmgs-countdown-thompson-dense-scale-nondiagnostic-summary/v1"
)
STAGE_ORDER = (
    "reproduce_nondiagnostic_anchor_qualification_without_development_material",
    "integrity_budget_and_two_stage_replay",
    "common_prefix_mechanism_without_terminal_fields",
    "terminal_error_reductions",
    "exact_success_and_development_handoff",
)
SCALES = (0, 1, 2, 4, 8, 16, 32, 64)
SEEDS = (7168, 7169, 7170, 7171)
READY = "READY_TO_PREREGISTER_SOURCE_DISJOINT_CONFIRMATION"
STOP = "STOP_REPAIR_NO_LOCKED_128_RUN"


class DenseScaleAnalysisError(ValueError):
    """A required authority, integrity, or analysis gate did not close."""


def _object(value: object, label: str) -> dict[str, Any]:
    if type(value) is not dict or any(type(key) is not str for key in value):
        raise DenseScaleAnalysisError(f"{label} must be an exact object")
    return value


def _integer(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise DenseScaleAnalysisError(f"{label} must be a nonnegative plain integer")
    return value


def _integers(value: object, label: str) -> tuple[int, ...]:
    if type(value) is not list or any(type(item) is not int for item in value):
        raise DenseScaleAnalysisError(f"{label} must be a plain integer vector")
    return tuple(value)


def _number(value: object, label: str) -> float:
    if type(value) is not float or not math.isfinite(value):
        raise DenseScaleAnalysisError(f"{label} must be finite binary64")
    return value


def _digest(core: dict[str, Any]) -> dict[str, Any]:
    return {**core, "deterministic_digest": sha256_json(core)}


def _bytes(value: object) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


def exact_integer_summary(values: Sequence[int]) -> dict[str, dict[str, int]]:
    """Exact arithmetic only; callers must separately freeze their estimand."""
    if not values or any(type(value) is not int for value in values):
        raise DenseScaleAnalysisError("required integer vector is empty or invalid")
    ordered = sorted(values)
    count = len(ordered)
    median = (
        Fraction(ordered[count // 2])
        if count % 2
        else Fraction(ordered[count // 2 - 1] + ordered[count // 2], 2)
    )
    mean = Fraction(sum(values), count)
    return {
        name: {"numerator": value.numerator, "denominator": value.denominator}
        for name, value in (("mean", mean), ("median", median))
    }


@dataclass(frozen=True, slots=True)
class BackupExposure:
    trajectory_index: int
    applied_value: float
    edge_order: tuple[tuple[tuple[int, ...], int], ...]


@dataclass(frozen=True, slots=True)
class SelectionSurface:
    trajectory_index: int
    depth: int
    state: tuple[int, ...]
    action_order: tuple[str, ...]
    proposal_behavior_digest: str
    point_digest: str
    selection_rule_id: str
    noise_normalizer: float
    posterior_visits: tuple[int, ...]
    selected_index: int
    scores: tuple[float, ...]
    preceding_backup_count: int

    @property
    def key(self) -> tuple[object, ...]:
        # Exactly the nine predecision fields in the sealed analysis manifest.
        return (
            self.trajectory_index,
            self.depth,
            self.state,
            self.action_order,
            self.proposal_behavior_digest,
            self.point_digest,
            self.selection_rule_id,
            self.noise_normalizer,
            self.posterior_visits,
        )

    @property
    def coordinate(self) -> dict[str, int]:
        return {"trajectory_index": self.trajectory_index, "depth": self.depth}


@dataclass(frozen=True, slots=True)
class MechanismCell:
    cell_id: str
    task_fingerprint: str
    exploration_seed: int
    scale: int
    selections: tuple[SelectionSurface, ...]
    backups: tuple[BackupExposure, ...]


def project_mechanism_cell(cell: Any, trace: dict[str, Any]) -> MechanismCell:
    """Allowlist projection; terminal and summary payloads are never accessed.

    This projection is not a replacement for full replay. Its caller must have
    replay-closed the complete collective first.
    """
    events = _object(trace, "trace").get("events")
    if type(events) is not list:
        raise DenseScaleAnalysisError("trace events must be an exact list")
    orders: dict[tuple[int, ...], tuple[str, ...]] = {}
    behaviors: dict[tuple[int, ...], str] = {}
    visits: dict[tuple[int, ...], list[int]] = {}
    selections: list[SelectionSurface] = []
    backups: list[BackupExposure] = []
    coordinates: set[tuple[int, int]] = set()
    for event in events:
        kind = _object(event, "event").get("kind")
        if kind not in {
            "proposal_materialized",
            "selection_committed",
            "trajectory_backed_up",
        }:
            continue
        payload = _object(event["payload"], "mechanism event payload")
        if kind == "proposal_materialized":
            proposal = _object(payload["proposal"], "proposal")
            state = _integers(proposal["state"], "proposal state")
            action_order = proposal["action_order"]
            if type(action_order) is not list or not action_order or state in orders:
                raise DenseScaleAnalysisError("proposal action-order identity drifted")
            orders[state] = tuple(canonical_json(action) for action in action_order)
            behaviors[state] = proposal["behavior_digest"]
            visits[state] = [0] * len(action_order)
        elif kind == "selection_committed":
            state = _integers(payload["state"], "selection state")
            if state not in orders:
                raise DenseScaleAnalysisError("selection precedes its proposal")
            order = orders[state]
            if (
                payload["action_order_digest"]
                != sha256_json([json.loads(action) for action in order])
                or payload["proposal_behavior_digest"] != behaviors[state]
            ):
                raise DenseScaleAnalysisError("selection proposal binding drifted")
            semantics = _object(payload["selection_semantics"], "selection semantics")
            trajectory = _integer(payload["trajectory_index"], "trajectory")
            depth = _integer(payload["depth"], "depth")
            if (trajectory, depth) in coordinates:
                raise DenseScaleAnalysisError("duplicate selection coordinate")
            coordinates.add((trajectory, depth))
            index = _integer(payload["action_index"], "selected action")
            raw_scores = payload["selection_values"]
            if type(raw_scores) is not list or len(raw_scores) != len(order):
                raise DenseScaleAnalysisError("selection score dimension drifted")
            scores = tuple(_number(value, "selection score") for value in raw_scores)
            if index >= len(order) or canonical_json(payload["action"]) != order[index]:
                raise DenseScaleAnalysisError("selected action identity drifted")
            if index != max(range(len(scores)), key=scores.__getitem__):
                raise DenseScaleAnalysisError("selection is not canonical first argmax")
            selections.append(
                SelectionSurface(
                    trajectory,
                    depth,
                    state,
                    order,
                    behaviors[state],
                    payload["point_digest"],
                    semantics["selection_rule_id"],
                    _number(semantics["noise_dimension_normalizer"], "normalizer"),
                    tuple(visits[state]),
                    index,
                    scores,
                    len(backups),
                )
            )
        else:
            edges: list[tuple[tuple[int, ...], int]] = []
            updates = payload["updates"]
            if type(updates) is not list or not updates:
                raise DenseScaleAnalysisError("backup updates must be nonempty")
            for raw_update in updates:
                update = _object(raw_update, "backup update")
                state = _integers(update["state"], "backup state")
                index = _integer(update["action_index"], "backup edge")
                before = _object(update["before"], "backup before")["visits"]
                after = _object(update["after"], "backup after")["visits"]
                if (
                    state not in visits
                    or index >= len(visits[state])
                    or _integer(before, "before visits") != visits[state][index]
                    or _integer(after, "after visits") != before + 1
                ):
                    raise DenseScaleAnalysisError("backup visit reconstruction failed")
                visits[state][index] = after
                edges.append((state, index))
            backups.append(
                BackupExposure(
                    _integer(payload["trajectory_index"], "backup trajectory"),
                    _number(payload["terminal_value"], "applied backup value"),
                    tuple(edges),
                )
            )
    return MechanismCell(
        cell.cell_id,
        cell.task_fingerprint,
        cell.exploration_seed,
        cell.terminal_value_scale,
        tuple(selections),
        tuple(backups),
    )


def pair_mechanism_cells(left: MechanismCell, right: MechanismCell) -> dict[str, Any]:
    """Compare common-prefix surfaces without any outcome-bearing input."""
    if type(left) is not MechanismCell or type(right) is not MechanismCell:
        raise DenseScaleAnalysisError("mechanism requires exact redacted cell types")
    if (
        left.task_fingerprint != right.task_fingerprint
        or left.exploration_seed != right.exploration_seed
        or left.scale != 0
        or right.scale not in SCALES[1:]
        or any(
            type(item) is not SelectionSurface
            for item in (*left.selections, *right.selections)
        )
        or any(
            type(item) is not BackupExposure for item in (*left.backups, *right.backups)
        )
    ):
        raise DenseScaleAnalysisError("mechanism pair identity drifted")
    common: list[dict[str, Any]] = []
    divergence: dict[str, Any] | None = None
    shared_backups: list[dict[str, Any]] = []
    informed = False
    stop = "trace_end_without_action_divergence"
    stop_coordinate: dict[str, int] | None = None
    for index in range(max(len(left.selections), len(right.selections))):
        if index >= len(left.selections) or index >= len(right.selections):
            present = (
                left.selections if index < len(left.selections) else right.selections
            )[index]
            stop, stop_coordinate = "missing_selection", present.coordinate
            break
        first, second = left.selections[index], right.selections[index]
        if _bytes(first.key) != _bytes(second.key):
            stop, stop_coordinate = "predecision_mismatch", first.coordinate
            break
        before_left = left.backups[: first.preceding_backup_count]
        before_right = right.backups[: second.preceding_backup_count]
        if len(before_left) != len(before_right) or any(
            (a.trajectory_index, a.edge_order) != (b.trajectory_index, b.edge_order)
            for a, b in zip(before_left, before_right)
        ):
            raise DenseScaleAnalysisError("shared-prefix backup identity drifted")
        shared_backups = [
            {
                "trajectory_index": a.trajectory_index,
                "baseline_applied_value": a.applied_value,
                "scaled_applied_value": b.applied_value,
            }
            for a, b in zip(before_left, before_right)
        ]
        surface = {
            **first.coordinate,
            "state": list(first.state),
            "baseline_action": json.loads(first.action_order[first.selected_index]),
            "scaled_action": json.loads(second.action_order[second.selected_index]),
            "baseline_action_index": first.selected_index,
            "scaled_action_index": second.selected_index,
            "baseline_scores": list(first.scores),
            "scaled_scores": list(second.scores),
        }
        common.append(surface)
        if first.selected_index != second.selected_index:
            divergence = surface
            stop, stop_coordinate = "recorded_action_divergence", first.coordinate
            informed = any(
                a.applied_value.hex() != b.applied_value.hex()
                for a, b in zip(before_left, before_right)
            )
            break
    return {
        "task_fingerprint": left.task_fingerprint,
        "exploration_seed": left.exploration_seed,
        "positive_scale": right.scale,
        "baseline_cell_id": left.cell_id,
        "scaled_cell_id": right.cell_id,
        "paired_surface_count": len(common),
        "common_surfaces_digest": sha256_json(common),
        "first_action_divergence": divergence,
        "feedback_informed": informed,
        "shared_prefix_backup_values": shared_backups,
        "stop_reason": stop,
        "stop_coordinate": stop_coordinate,
    }


def _ordered_cells(cells: Sequence[Any]) -> tuple[tuple[str, int], ...]:
    if len(cells) != 384 or len({cell.cell_id for cell in cells}) != 384:
        raise DenseScaleAnalysisError("analysis requires exactly 384 unique cells")
    tasks = tuple(dict.fromkeys(cell.task_fingerprint for cell in cells))
    if len(tasks) != 12:
        raise DenseScaleAnalysisError("analysis requires twelve task identities")
    expected = [
        (task, scale, seed) for task in tasks for scale in SCALES for seed in SEEDS
    ]
    observed = [
        (cell.task_fingerprint, cell.terminal_value_scale, cell.exploration_seed)
        for cell in cells
    ]
    if observed != expected:
        raise DenseScaleAnalysisError(
            "cell order differs from task/scale/seed schedule"
        )
    return tuple((task, seed) for task in tasks for seed in SEEDS)


def _error_cell(trace: dict[str, Any]) -> dict[str, Any]:
    trajectories: list[int] = []
    errors: list[int] = []
    values: list[float] = []
    backup_trajectories: list[int] = []
    for event in trace["events"]:
        if event["kind"] == "terminal_verified":
            payload = event["payload"]
            verification = _object(payload["verification"], "terminal verification")
            final, target = verification["final_value"], verification["target"]
            if type(final) is not int or type(target) is not int:
                raise DenseScaleAnalysisError(
                    "terminal arithmetic is not exact integer"
                )
            if _integer(payload["observation_index"], "observation index") != len(
                errors
            ):
                raise DenseScaleAnalysisError("terminal observation order drifted")
            trajectories.append(
                _integer(payload["trajectory_index"], "terminal trajectory")
            )
            errors.append(abs(final - target))
        elif event["kind"] == "trajectory_backed_up":
            payload = event["payload"]
            backup_trajectories.append(payload["trajectory_index"])
            values.append(_number(payload["terminal_value"], "terminal value"))
    if not errors or trajectories != backup_trajectories:
        raise DenseScaleAnalysisError("required terminal vector is empty or unclosed")
    return {
        "trajectories": trajectories,
        "errors": errors,
        "values": values,
        "minimum_error": min(errors),
    }


def reduce_replay_closed_traces(
    cells: Sequence[Any],
    traces: Sequence[dict[str, Any]],
    *,
    fixture: bool,
    stage_observer: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Pure reduction of an already replay-closed exact collective.

    This API grants no publication authority. Only the independent public
    analyzer wrappers may publish a summary.
    """
    order = _ordered_cells(cells)
    if len(traces) != 384 or type(fixture) is not bool:
        raise DenseScaleAnalysisError("analysis trace count or domain drifted")
    observe = stage_observer or (lambda stage: None)
    observe(STAGE_ORDER[2])
    views = [project_mechanism_cell(cell, trace) for cell, trace in zip(cells, traces)]
    keyed = {
        (view.task_fingerprint, view.exploration_seed, view.scale): view
        for view in views
    }
    pair_rows = [
        pair_mechanism_cells(keyed[task, seed, 0], keyed[task, seed, scale])
        for scale in SCALES[1:]
        for task, seed in order
    ]
    mechanism_by_scale: dict[int, dict[str, Any]] = {}
    for scale in SCALES:
        informed_rows = [
            row
            for row in pair_rows
            if row["positive_scale"] == scale and row["feedback_informed"]
        ]
        coordinates = Counter(
            (
                row["first_action_divergence"]["trajectory_index"],
                row["first_action_divergence"]["depth"],
            )
            for row in informed_rows
        )
        mechanism_by_scale[scale] = {
            "feedback_informed_first_divergence_count": len(informed_rows),
            "first_divergence_coordinate_distribution": [
                {"trajectory_index": trajectory, "depth": depth, "count": count}
                for (trajectory, depth), count in sorted(coordinates.items())
            ],
        }
    mechanism = _digest(
        {
            "pair_count": len(pair_rows),
            "ordered_pair_rows": pair_rows,
            "per_scale": [
                {"scale": scale, **mechanism_by_scale[scale]} for scale in SCALES
            ],
        }
    )
    observe(STAGE_ORDER[3])
    errors = {
        (
            cell.task_fingerprint,
            cell.exploration_seed,
            cell.terminal_value_scale,
        ): _error_cell(trace)
        for cell, trace in zip(cells, traces)
    }
    per_scale: list[dict[str, Any]] = []
    for scale in SCALES:
        rows = [errors[task, seed, scale] for task, seed in order]
        minimum = [row["minimum_error"] for row in rows]
        baseline_minimum = [
            errors[task, seed, 0]["minimum_error"] for task, seed in order
        ]
        per_scale.append(
            {
                "scale": scale,
                **mechanism_by_scale[scale],
                "minimum_terminal_absolute_error_vector": minimum,
                "terminal_absolute_error_vectors": [row["errors"] for row in rows],
                "terminal_value_vectors": [row["values"] for row in rows],
                "paired_minimum_error_win_tie_loss_vs_scale_0": {
                    "wins": sum(a < b for a, b in zip(minimum, baseline_minimum)),
                    "ties": sum(a == b for a, b in zip(minimum, baseline_minimum)),
                    "losses": sum(a > b for a, b in zip(minimum, baseline_minimum)),
                },
            }
        )
    observe(STAGE_ORDER[4])
    baseline_success = [
        any(error == 0 for error in errors[task, seed, 0]["errors"])
        for task, seed in order
    ]
    for scale_row in per_scale:
        scale = scale_row["scale"]
        rows = [errors[task, seed, scale] for task, seed in order]
        success = [any(error == 0 for error in row["errors"]) for row in rows]
        new = sum(
            not base and candidate for base, candidate in zip(baseline_success, success)
        )
        lost = sum(
            base and not candidate for base, candidate in zip(baseline_success, success)
        )
        scale_row.update(
            {
                "success_vector": success,
                "exact_success_count": sum(success),
                "first_hit_trajectory_index_vector": [
                    next(
                        (
                            trajectory
                            for trajectory, error in zip(
                                row["trajectories"], row["errors"]
                            )
                            if error == 0
                        ),
                        None,
                    )
                    for row in rows
                ],
                "paired_new_success_count_vs_scale_0": new,
                "paired_lost_success_count_vs_scale_0": lost,
                "paired_net_success_difference_vs_scale_0": new - lost,
            }
        )
    result: dict[str, Any] = {
        "mechanism": mechanism,
        "per_scale": per_scale,
        "scale_order": list(SCALES),
        "task_seed_order": [
            {"task_fingerprint": task, "exploration_seed": seed} for task, seed in order
        ],
    }
    if not fixture:
        selected = max(
            per_scale[1:], key=lambda row: (row["exact_success_count"], -row["scale"])
        )
        pair_map = {
            (row["task_fingerprint"], row["exploration_seed"]): row
            for row in pair_rows
            if row["positive_scale"] == selected["scale"]
        }
        guard = all(
            pair_map[key]["feedback_informed"]
            and pair_map[key]["first_action_divergence"] is not None
            for key, base, candidate in zip(
                order, baseline_success, selected["success_vector"]
            )
            if not base and candidate
        )
        ready = (
            selected["paired_net_success_difference_vs_scale_0"] >= 2
            and selected["paired_new_success_count_vs_scale_0"] >= 2
            and guard
        )
        result.update(
            {"selected_scale": selected["scale"], "decision": READY if ready else STOP}
        )
    return _digest(result)


def _modules() -> tuple[Any, Any, Any]:
    from qmc_bmgs.experiments import countdown_thompson_dense_scale_core as core
    from qmc_bmgs.experiments import (
        countdown_thompson_dense_scale_publication as publication,
    )
    from qmc_bmgs.experiments import countdown_thompson_dense_scale_runner as runner

    return core, publication, runner


def _publication_inputs(
    core: Any,
    publication: Any,
    inputs: Any,
    reviewed: Any,
    execution_head_revision: str,
) -> Any:
    task_sources = inputs.task_sources
    factory = (
        publication.make_dense_fixture_publication_inputs
        if inputs.fixture
        else publication.make_dense_publication_inputs
    )
    return factory(
        authorization_raw=reviewed.raw,
        schedule_raw=core.canonical_bytes(list(inputs.schedule)),
        task_sources_raw=core.canonical_bytes(task_sources),
        reviewed_authorization_revision=reviewed.authorization_revision,
        execution_head_revision=execution_head_revision,
    )


def _summary(
    inputs: Any,
    reviewed: Any,
    verified: Any,
    qualification: dict[str, Any],
    reduction: dict[str, Any],
) -> dict[str, Any]:
    base = {
        "schema_version": FIXTURE_SUMMARY_SCHEMA if inputs.fixture else SUMMARY_SCHEMA,
        "bundle_id": inputs.bundle_id,
        "execution_mode": (
            "nondiagnostic_dense_scale_full_shape_fixture"
            if inputs.fixture
            else "authorized_dense_scale_development"
        ),
        "cell_count": 384,
        "analysis_manifest_digest": inputs.payload["analysis"]["deterministic_digest"],
        "authorization_digest": reviewed.payload["deterministic_digest"],
        "anchor_qualification_digest": qualification["deterministic_digest"],
        "run_manifest_digest": verified.run_manifest_digest,
        "stage_order": list(STAGE_ORDER),
        "integrity": "PASS",
    }
    if inputs.fixture:
        base.update(
            {
                "fixture_status": "FIXTURE_REPLAY_PASS",
                "fixture_reduction_digest": reduction["deterministic_digest"],
                "claim_boundary": "nondiagnostic plumbing only; no development handoff decision",
            }
        )
    else:
        base.update(
            {
                key: reduction[key]
                for key in (
                    "mechanism",
                    "scale_order",
                    "task_seed_order",
                    "per_scale",
                    "selected_scale",
                    "decision",
                )
            }
        )
        base["claim_boundary"] = (
            "development only; no confirmation, superiority, QMC, or locked-128 authority"
        )
    return _digest(base)


def _admit_historical_execution_head(
    core: Any,
    reviewed: Any,
    hint: Any,
    repository_root: Path,
    *,
    fixture: bool,
) -> str:
    """Admit a control-file hint using independent Git/source authority."""
    historical_head = core.require_git_oid(hint.execution_head_revision)
    if fixture and historical_head != reviewed.authorization_revision:
        raise DenseScaleAnalysisError("fixture execution differs from its source epoch")
    # Only runner revision -> authorization revision is strict, and the external
    # loader closes that edge. Execution may equal the authorization merge HEAD.
    core.require_ancestor(
        repository_root,
        reviewed.authorization_revision,
        historical_head,
    )
    core.require_ancestor(repository_root, historical_head, reviewed.execution_head)
    core.verify_historical_source_receipts(
        repository_root,
        historical_head,
        reviewed.payload["runner_build_attestation"]["source_files"],
    )
    hint.revalidate()
    return historical_head


def _analyze(
    artifact_path: Path,
    *,
    authorization_file: Path,
    authorization_digest: str,
    authorization_revision: str,
    repository_root: Path,
    output_path: Path,
    bundle_path: Path | None,
    fixture: bool,
) -> dict[str, Any]:
    core, publication, runner = _modules()
    # This is intentionally before loading either development bundle or records.
    qualification = core.reproduce_anchor_qualification()
    reviewed = runner.load_reviewed_authorization(
        authorization_file,
        authorization_digest=authorization_digest,
        authorization_revision=authorization_revision,
        repository_root=repository_root,
        output_path=artifact_path,
        fixture=fixture,
    )
    if _bytes(reviewed.payload["anchor_qualification"]) != _bytes(qualification):
        raise DenseScaleAnalysisError("external authorization qualification differs")
    hint_reader = (
        publication.read_dense_scale_fixture_execution_head_hint
        if fixture
        else publication.read_dense_scale_execution_head_hint
    )
    hint = hint_reader(
        artifact_path,
        authorization_digest=reviewed.payload["deterministic_digest"],
        expected_parent_binding=reviewed.payload["output_parent_binding"],
    )
    # The manifest supplies only a candidate revision, never its own authority.
    # Git ancestry and exact historical source blobs independently admit it.
    historical_head = _admit_historical_execution_head(
        core,
        reviewed,
        hint,
        repository_root,
        fixture=fixture,
    )
    inputs = (
        core.public_fixture_inputs()
        if fixture
        else core.load_production_inputs(bundle_path, repository_root)
    )
    if inputs.fixture is not fixture:
        raise DenseScaleAnalysisError("analysis domain differs from input authority")
    if tuple(inputs.payload["analysis"]["analysis_order"]) != STAGE_ORDER:
        raise DenseScaleAnalysisError("sealed analysis order drifted")
    publication_inputs = _publication_inputs(
        core,
        publication,
        inputs,
        reviewed,
        historical_head,
    )
    verifier = (
        publication.verify_dense_scale_fixture_v2r3
        if fixture
        else publication.verify_dense_scale_v2r3
    )
    verified = verifier(artifact_path, inputs=publication_inputs)
    hint.revalidate()
    records = verified.records
    _ordered_cells(inputs.cells)
    if len(records) != 384:
        raise DenseScaleAnalysisError(
            "committed collective does not contain 384 records"
        )
    binding = verified.run_manifest["run_binding"]
    # No projection or reduction is entered until every record has replayed.
    traces = tuple(
        core.verify_record(inputs, cell, row, binding)
        for cell, row in zip(inputs.cells, records)
    )

    def revalidate() -> None:
        reviewed.revalidate()
        inputs.revalidate()
        hint.revalidate()
        core.verify_historical_source_receipts(
            repository_root,
            historical_head,
            reviewed.payload["runner_build_attestation"]["source_files"],
        )
        if not fixture:
            current = core.load_production_inputs(bundle_path, repository_root)
            if _bytes(current.payload) != _bytes(inputs.payload):
                raise DenseScaleAnalysisError("sealed bundle changed during analysis")
        repeated = verifier(artifact_path, inputs=publication_inputs)
        if (
            repeated.authority_generation != verified.authority_generation
            or repeated.records_jsonl_bytes != verified.records_jsonl_bytes
            or _bytes(repeated.run_manifest) != _bytes(verified.run_manifest)
            or _bytes(repeated.commit_receipt) != _bytes(verified.commit_receipt)
        ):
            raise publication.DensePublicationAmbiguousError(
                "collective changed during analysis"
            )
        hint.revalidate()

    # Source, bundle and raw authority must still close after the final replay,
    # before any mechanism, error or success reduction is entered.
    revalidate()
    reduction = reduce_replay_closed_traces(inputs.cells, traces, fixture=fixture)
    summary = _summary(inputs, reviewed, verified, qualification, reduction)

    writer = (
        publication.publish_dense_scale_fixture_summary
        if fixture
        else publication.publish_dense_scale_summary
    )
    protected = (repository_root,) if fixture else (repository_root, bundle_path)
    writer(
        output_path,
        core.canonical_bytes(summary),
        artifact_path=artifact_path,
        protected_roots=protected,
        pre_publication_check=revalidate,
        post_durability_check=revalidate,
    )
    return summary


def analyze_dense_scale_artifact(artifact_path: Path, **kwargs: Any) -> dict[str, Any]:
    return _analyze(artifact_path, fixture=False, **kwargs)


def analyze_dense_scale_fixture(artifact_path: Path, **kwargs: Any) -> dict[str, Any]:
    if "bundle_path" in kwargs and kwargs["bundle_path"] is not None:
        raise DenseScaleAnalysisError("fixture analysis cannot receive a sealed bundle")
    kwargs["bundle_path"] = None
    return _analyze(artifact_path, fixture=True, **kwargs)


def _self_test() -> dict[str, Any]:
    if exact_integer_summary((1, 4))["median"] != {"numerator": 5, "denominator": 2}:
        raise DenseScaleAnalysisError("exact integer reduction self-test failed")
    left = MechanismCell("a", "public", 7168, 0, (), ())
    right = MechanismCell("b", "public", 7168, 1, (), ())
    if pair_mechanism_cells(left, right)["first_action_divergence"] is not None:
        raise DenseScaleAnalysisError("null mechanism self-test failed")
    return {
        "status": "PASS",
        "claim_boundary": "pure nondiagnostic analyzer self-test only",
    }


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise DenseScaleAnalysisError(message)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        parser = _Parser(description=__doc__)
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument("--self-test", action="store_true")
        mode.add_argument("--analyze-full-shape-fixture", type=Path)
        mode.add_argument("--analyze-v2r3", type=Path)
        parser.add_argument("--bundle", type=Path)
        parser.add_argument("--authorization-file", type=Path)
        parser.add_argument("--authorization-digest")
        parser.add_argument("--authorization-revision")
        parser.add_argument("--output", type=Path)
        parser.add_argument("--repository-root", type=Path)
        args = parser.parse_args(argv)
        required = (
            args.authorization_file,
            args.authorization_digest,
            args.authorization_revision,
            args.output,
            args.repository_root,
        )
        if args.self_test:
            if any(value is not None for value in (*required, args.bundle)):
                raise DenseScaleAnalysisError("self-test accepts no operational inputs")
            result = _self_test()
        else:
            if any(value is None for value in required):
                raise DenseScaleAnalysisError(
                    "analysis requires explicit authority, output and repository root"
                )
            fixture = args.analyze_full_shape_fixture is not None
            if (fixture and args.bundle is not None) or (
                not fixture and args.bundle is None
            ):
                raise DenseScaleAnalysisError(
                    "only production analysis requires --bundle"
                )
            result = _analyze(
                args.analyze_full_shape_fixture if fixture else args.analyze_v2r3,
                authorization_file=args.authorization_file,
                authorization_digest=args.authorization_digest,
                authorization_revision=args.authorization_revision,
                repository_root=args.repository_root,
                output_path=args.output,
                bundle_path=args.bundle,
                fixture=fixture,
            )
        print(canonical_json(result))
        return 0
    except Exception as error:
        # Exact exception classes, never error text, distinguish ambiguity.
        status = "INVALID_ANALYSIS"
        try:
            from qmc_bmgs.experiments.countdown_thompson_dense_scale_publication import (
                DensePublicationAmbiguousError,
            )

            if isinstance(error, DensePublicationAmbiguousError):
                status = "PUBLICATION_STATE_AMBIGUOUS"
        except ImportError:
            pass
        print(canonical_json({"status": status, "reason": str(error)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
