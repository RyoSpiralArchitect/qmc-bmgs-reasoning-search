"""Read-only post-hoc mechanism audit for the committed Thompson diagnostic.

This module does not execute search.  It revalidates the exact v2r3 diagnostic
and its independently published summary, then reduces already committed trace
events under the frozen exploratory definitions in
``docs/strategy/countdown_thompson_posthoc_mechanism_audit.md``.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping, Sequence

from qmc_bmgs.experiments import countdown_thompson_diagnostic_analysis as analysis
from qmc_bmgs.experiments import (
    countdown_thompson_regular_file_publication_v2 as regular_file_publication,
)
from qmc_bmgs.substrate.trace import canonical_json, sha256_json, strict_json_loads


SCHEMA_VERSION = "qmc-bmgs-countdown-thompson-posthoc-mechanism/v1"
MODULE_RELATIVE_PATH = Path(
    "src/qmc_bmgs/experiments/countdown_thompson_posthoc_mechanism.py"
)
DESIGN_RELATIVE_PATH = Path(
    "docs/strategy/countdown_thompson_posthoc_mechanism_audit.md"
)
V2_METHOD = "thompson_dimnorm_iid_v2"
V3_METHOD = "thompson_dense_iid_v3"
V4_METHOD = "thompson_greedy_anchor_dense_iid_v4"
METHODS = (V2_METHOD, V3_METHOD, V4_METHOD)
EXPECTED_SEEDS = (7168, 7169, 7170, 7171)
EXPECTED_TASK_COUNT = 12
EXPECTED_METHOD_CELL_COUNT = EXPECTED_TASK_COUNT * len(EXPECTED_SEEDS)
EXPECTED_RECORD_COUNT = 240
CLAIM_BOUNDARY = (
    "Exploratory post-hoc engineering observation from one fixed diagnostic. "
    "Integrity PASS is provenance and reduction closure only; it is not a "
    "causal, inferential, method-superiority, retry, or locked-128 authority."
)
HANDOFF_DECISION = "STOP_REPAIR_NO_LOCKED_128_RUN"


class PosthocMechanismAuditError(ValueError):
    """Raised before a receipt is emitted when the audit cannot close."""


@dataclass(frozen=True)
class _Selection:
    trajectory_index: int
    depth: int
    state: tuple[int, ...]
    action_index: int
    child_state: tuple[int, ...]
    prior_feedback_count: int
    selection_phase: str | None

    @property
    def coordinate(self) -> tuple[int, int]:
        return self.trajectory_index, self.depth

    def identity_payload(self) -> list[object]:
        return [
            self.trajectory_index,
            self.depth,
            list(self.state),
            self.action_index,
            list(self.child_state),
        ]


@dataclass(frozen=True)
class _Terminal:
    trajectory_index: int
    absolute_error: int
    success: bool
    prior_feedback_count_at_start: int


@dataclass(frozen=True)
class _Cell:
    cell_id: str
    method_label: str
    task_fingerprint: str
    exploration_seed: int
    selections: tuple[_Selection, ...]
    terminals: tuple[_Terminal, ...]
    backup_count: int
    backup_update_count: int
    success_any: bool

    @property
    def pair_key(self) -> tuple[str, int]:
        return self.task_fingerprint, self.exploration_seed


def _plain_nonnegative_int(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise PosthocMechanismAuditError(f"{label} must be a non-negative plain int")
    return value


def _plain_int_vector(value: object, label: str) -> tuple[int, ...]:
    if type(value) is not list or any(type(item) is not int for item in value):
        raise PosthocMechanismAuditError(f"{label} must be a plain-int list")
    return tuple(value)


def _strict_object(value: object, label: str) -> dict[str, Any]:
    if type(value) is not dict or any(type(key) is not str for key in value):
        raise PosthocMechanismAuditError(f"{label} must be an exact object")
    return value


def _cell_from_record(record: Mapping[str, Any]) -> _Cell:
    if type(record) is not dict:
        raise PosthocMechanismAuditError("run record must be an exact object")
    labels = _strict_object(record.get("labels"), "record labels")
    method = labels.get("method_label")
    task = labels.get("task_fingerprint")
    seed = labels.get("exploration_seed")
    proposal = labels.get("proposal_label")
    cell_id = record.get("cell_id")
    if (
        type(method) is not str
        or method not in METHODS
        or type(task) is not str
        or not task
        or type(seed) is not int
        or seed not in EXPECTED_SEEDS
        or proposal != "heuristic"
        or type(cell_id) is not str
        or len(cell_id) != 64
    ):
        raise PosthocMechanismAuditError("target cell identity drifted")

    search_record = _strict_object(record.get("search_record"), "search record")
    events = search_record.get("events")
    if type(events) is not list:
        raise PosthocMechanismAuditError("search events must be a list")

    feedback_count = 0
    selections: list[_Selection] = []
    raw_terminals: list[tuple[int, int, bool]] = []
    backup_trajectories: list[int] = []
    backup_update_count = 0
    start_feedback: dict[int, int] = {}
    coordinates: set[tuple[int, int]] = set()

    for event_index, raw_event in enumerate(events):
        event = _strict_object(raw_event, f"event {event_index}")
        kind = event.get("kind")
        payload = _strict_object(event.get("payload"), f"event {event_index} payload")
        if kind == "selection_committed":
            trajectory = _plain_nonnegative_int(
                payload.get("trajectory_index"), "selection trajectory_index"
            )
            depth = _plain_nonnegative_int(payload.get("depth"), "selection depth")
            coordinate = (trajectory, depth)
            if coordinate in coordinates:
                raise PosthocMechanismAuditError(
                    "selection coordinate is duplicated within one cell"
                )
            coordinates.add(coordinate)
            if trajectory not in start_feedback:
                start_feedback[trajectory] = feedback_count
            semantics = payload.get("selection_semantics")
            phase: str | None = None
            if semantics is not None:
                semantics = _strict_object(semantics, "selection semantics")
                raw_phase = semantics.get("selection_phase")
                if raw_phase is not None and type(raw_phase) is not str:
                    raise PosthocMechanismAuditError("selection phase type drifted")
                phase = raw_phase
            selections.append(
                _Selection(
                    trajectory_index=trajectory,
                    depth=depth,
                    state=_plain_int_vector(payload.get("state"), "selection state"),
                    action_index=_plain_nonnegative_int(
                        payload.get("action_index"), "selection action_index"
                    ),
                    child_state=_plain_int_vector(
                        payload.get("child_state"), "selection child_state"
                    ),
                    prior_feedback_count=feedback_count,
                    selection_phase=phase,
                )
            )
        elif kind == "terminal_verified":
            trajectory = _plain_nonnegative_int(
                payload.get("trajectory_index"), "terminal trajectory_index"
            )
            verification = _strict_object(
                payload.get("verification"), "terminal verification"
            )
            final_value = verification.get("final_value")
            target = verification.get("target")
            success = verification.get("success")
            if (
                type(final_value) is not int
                or type(target) is not int
                or type(success) is not bool
            ):
                raise PosthocMechanismAuditError("terminal verification types drifted")
            error = abs(final_value - target)
            if success is not (error == 0):
                raise PosthocMechanismAuditError("terminal success/error semantics drifted")
            raw_terminals.append((trajectory, error, success))
        elif kind == "trajectory_backed_up":
            trajectory = _plain_nonnegative_int(
                payload.get("trajectory_index"), "backup trajectory_index"
            )
            updates = payload.get("updates")
            if type(updates) is not list:
                raise PosthocMechanismAuditError("backup updates must be a list")
            backup_trajectories.append(trajectory)
            backup_update_count += len(updates)
            feedback_count += 1

    if not selections or not raw_terminals or not backup_trajectories:
        raise PosthocMechanismAuditError("target cell lacks adaptive trace evidence")
    if tuple(backup_trajectories) != tuple(item[0] for item in raw_terminals):
        raise PosthocMechanismAuditError("terminal/backup trajectory closure drifted")
    if sorted(start_feedback) != list(range(max(start_feedback) + 1)):
        raise PosthocMechanismAuditError("begun trajectory indices are not contiguous")
    if tuple(item[0] for item in raw_terminals) != tuple(range(len(raw_terminals))):
        raise PosthocMechanismAuditError("completed trajectory indices are not contiguous")

    terminals: list[_Terminal] = []
    for trajectory, error, success in raw_terminals:
        if trajectory not in start_feedback:
            raise PosthocMechanismAuditError("terminal trajectory never began")
        terminals.append(
            _Terminal(
                trajectory_index=trajectory,
                absolute_error=error,
                success=success,
                prior_feedback_count_at_start=start_feedback[trajectory],
            )
        )

    summary = _strict_object(record.get("search_summary"), "search summary")
    success_any = summary.get("success_any")
    if type(success_any) is not bool or success_any is not any(
        terminal.success for terminal in terminals
    ):
        raise PosthocMechanismAuditError("search summary success drifted")

    if method == V4_METHOD:
        for selection in selections:
            expected_phase = (
                "greedy_anchor"
                if selection.trajectory_index == 0
                else "posterior_perturbation"
            )
            if selection.selection_phase != expected_phase:
                raise PosthocMechanismAuditError("v4 selection phase drifted")

    return _Cell(
        cell_id=cell_id,
        method_label=method,
        task_fingerprint=task,
        exploration_seed=seed,
        selections=tuple(selections),
        terminals=tuple(terminals),
        backup_count=len(backup_trajectories),
        backup_update_count=backup_update_count,
        success_any=success_any,
    )


def _target_cells(records: Sequence[Mapping[str, Any]]) -> dict[str, tuple[_Cell, ...]]:
    if len(records) != EXPECTED_RECORD_COUNT:
        raise PosthocMechanismAuditError("diagnostic record count drifted")
    selected: dict[str, list[_Cell]] = {method: [] for method in METHODS}
    for record in records:
        labels = _strict_object(record.get("labels"), "record labels")
        method = labels.get("method_label")
        if method in METHODS:
            selected[method].append(_cell_from_record(record))

    result: dict[str, tuple[_Cell, ...]] = {}
    common_keys: set[tuple[str, int]] | None = None
    for method in METHODS:
        cells = sorted(selected[method], key=lambda cell: cell.pair_key)
        if len(cells) != EXPECTED_METHOD_CELL_COUNT:
            raise PosthocMechanismAuditError(f"{method} coverage drifted")
        keys = [cell.pair_key for cell in cells]
        if len(set(keys)) != len(keys):
            raise PosthocMechanismAuditError(f"{method} contains duplicate pairs")
        tasks = {cell.task_fingerprint for cell in cells}
        if len(tasks) != EXPECTED_TASK_COUNT or any(
            {cell.exploration_seed for cell in cells if cell.task_fingerprint == task}
            != set(EXPECTED_SEEDS)
            for task in tasks
        ):
            raise PosthocMechanismAuditError(f"{method} task/seed matrix drifted")
        key_set = set(keys)
        if common_keys is None:
            common_keys = key_set
        elif key_set != common_keys:
            raise PosthocMechanismAuditError("method pair coverage differs")
        result[method] = tuple(cells)
    return result


def _selection_map(
    cell: _Cell, *, feedback_informed: bool | None = None, trajectory: int | None = None
) -> dict[tuple[int, int], _Selection]:
    result: dict[tuple[int, int], _Selection] = {}
    for selection in cell.selections:
        if feedback_informed is not None:
            informed = selection.prior_feedback_count >= 1
            if informed is not feedback_informed:
                continue
        if trajectory is not None and selection.trajectory_index != trajectory:
            continue
        result[selection.coordinate] = selection
    return result


def _first_selection_difference(
    left: _Cell, right: _Cell
) -> tuple[bool, dict[str, int] | None]:
    left_map = _selection_map(left, feedback_informed=True)
    right_map = _selection_map(right, feedback_informed=True)
    for trajectory, depth in sorted(set(left_map) | set(right_map)):
        left_item = left_map.get((trajectory, depth))
        right_item = right_map.get((trajectory, depth))
        if (
            left_item is None
            or right_item is None
            or left_item.identity_payload() != right_item.identity_payload()
        ):
            return True, {"depth": depth, "trajectory_index": trajectory}
    return False, None


def _post_feedback_errors(cell: _Cell) -> list[int]:
    return [
        terminal.absolute_error
        for terminal in cell.terminals
        if terminal.prior_feedback_count_at_start >= 1
    ]


def _comparison(left: int | None, right: int | None) -> str:
    """Classify right relative to left."""

    if left is None or right is None:
        return "not_comparable"
    if right < left:
        return "improved"
    if right > left:
        return "worse"
    return "equal"


def _fraction_payload(value: Fraction) -> dict[str, int]:
    return {"denominator": value.denominator, "numerator": value.numerator}


def _count_payload(values: Sequence[int]) -> dict[str, int]:
    counts = Counter(values)
    return {str(key): counts[key] for key in sorted(counts)}


def _v2_v3_reduction(cells: Mapping[str, Sequence[_Cell]]) -> dict[str, Any]:
    v2 = {cell.pair_key: cell for cell in cells[V2_METHOD]}
    v3 = {cell.pair_key: cell for cell in cells[V3_METHOD]}
    rows: list[dict[str, Any]] = []
    comparison_counts: Counter[str] = Counter()
    exact_counts: Counter[str] = Counter()
    first_trajectory_identical = 0
    divergence_count = 0
    divergence_trajectories: list[int] = []
    divergence_depths: list[int] = []

    for key in sorted(v2):
        left = v2[key]
        right = v3[key]
        left_first = [
            item.identity_payload()
            for item in _selection_map(left, trajectory=0).values()
        ]
        right_first = [
            item.identity_payload()
            for item in _selection_map(right, trajectory=0).values()
        ]
        identical_first = left_first == right_first
        first_trajectory_identical += int(identical_first)
        diverged, first_difference = _first_selection_difference(left, right)
        divergence_count += int(diverged)
        if first_difference is not None:
            divergence_trajectories.append(first_difference["trajectory_index"])
            divergence_depths.append(first_difference["depth"])

        left_errors = _post_feedback_errors(left)
        right_errors = _post_feedback_errors(right)
        left_best = min(left_errors) if left_errors else None
        right_best = min(right_errors) if right_errors else None
        classification = _comparison(left_best, right_best)
        comparison_counts[classification] += 1
        left_exact = left_best == 0
        right_exact = right_best == 0
        exact_classification = (
            "both"
            if left_exact and right_exact
            else "v3_only"
            if right_exact
            else "v2_only"
            if left_exact
            else "neither"
        )
        exact_counts[exact_classification] += 1
        rows.append(
            {
                "exploration_seed": key[1],
                "first_feedback_selection_difference": first_difference,
                "feedback_informed_selection_diverged": diverged,
                "post_first_exact_classification": exact_classification,
                "post_first_v2_best_absolute_error": left_best,
                "post_first_v3_best_absolute_error": right_best,
                "task_fingerprint": key[0],
                "trajectory_0_selection_identity_equal": identical_first,
                "v3_error_classification": classification,
            }
        )

    comparable = sum(
        comparison_counts[label] for label in ("improved", "equal", "worse")
    )
    if divergence_count == 0:
        direction = "NO_OBSERVED_DENSE_DIRECTION"
    elif comparison_counts["improved"] * 2 > comparable:
        direction = "MORE_V3_IMPROVEMENTS_IN_ARTIFACT"
    else:
        direction = "MIXED_OR_NULL_DENSE_DIRECTION"
    return {
        "comparable_pair_count": comparable,
        "dense_direction_label": direction,
        "feedback_informed_selection_divergence_count": divergence_count,
        "first_divergence_depth_distribution": _count_payload(divergence_depths),
        "first_divergence_trajectory_distribution": _count_payload(
            divergence_trajectories
        ),
        "ordered_pair_rows": rows,
        "pair_count": len(rows),
        "post_first_exact_classification_counts": {
            label: exact_counts[label]
            for label in ("both", "v3_only", "v2_only", "neither")
        },
        "trajectory_0_selection_identity_equal_count": first_trajectory_identical,
        "v3_error_classification_counts": {
            label: comparison_counts[label]
            for label in ("improved", "equal", "worse", "not_comparable")
        },
    }


def _v4_reduction(cells: Sequence[_Cell]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    all_counts: Counter[str] = Counter()
    failure_counts: Counter[str] = Counter()
    rescue_count = 0
    anchor_success_count = 0
    post_anchor_exact_after_anchor_success = 0
    for cell in cells:
        anchor = next(
            (terminal for terminal in cell.terminals if terminal.trajectory_index == 0),
            None,
        )
        if anchor is None:
            raise PosthocMechanismAuditError("v4 anchor terminal is missing")
        post_errors = [
            terminal.absolute_error
            for terminal in cell.terminals
            if terminal.trajectory_index > 0
            and terminal.prior_feedback_count_at_start >= 1
        ]
        post_best = min(post_errors) if post_errors else None
        classification = (
            "no_post_anchor_terminal"
            if post_best is None
            else _comparison(anchor.absolute_error, post_best)
        )
        all_counts[classification] += 1
        if anchor.success:
            anchor_success_count += 1
            post_anchor_exact_after_anchor_success += int(post_best == 0)
        else:
            failure_counts[classification] += 1
            rescue_count += int(post_best == 0)
        rows.append(
            {
                "anchor_absolute_error": anchor.absolute_error,
                "anchor_success": anchor.success,
                "cell_id": cell.cell_id,
                "error_classification": classification,
                "exact_rescue": (not anchor.success and post_best == 0),
                "exploration_seed": cell.exploration_seed,
                "post_anchor_best_absolute_error": post_best,
                "task_fingerprint": cell.task_fingerprint,
            }
        )
    labels = ("improved", "equal", "worse", "no_post_anchor_terminal")
    return {
        "all_cell_error_classification_counts": {
            label: all_counts[label] for label in labels
        },
        "anchor_failure_count": len(cells) - anchor_success_count,
        "anchor_failure_error_classification_counts": {
            label: failure_counts[label] for label in labels
        },
        "anchor_success_count": anchor_success_count,
        "cell_count": len(cells),
        "exact_post_anchor_rescue_count": rescue_count,
        "ordered_cell_rows": rows,
        "post_anchor_exact_after_anchor_success_count": (
            post_anchor_exact_after_anchor_success
        ),
    }


def _feedback_exposure(cells: Mapping[str, Sequence[_Cell]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for method in METHODS:
        rows: list[dict[str, Any]] = []
        backup_counts: list[int] = []
        begun_counts: list[int] = []
        completed_counts: list[int] = []
        update_counts: list[int] = []
        start_feedback_counts: list[int] = []
        for cell in cells[method]:
            informed_begun = sorted(
                {
                    selection.trajectory_index
                    for selection in cell.selections
                    if selection.prior_feedback_count >= 1
                }
            )
            informed_completed = [
                terminal.trajectory_index
                for terminal in cell.terminals
                if terminal.prior_feedback_count_at_start >= 1
            ]
            start_counts = [
                min(
                    selection.prior_feedback_count
                    for selection in cell.selections
                    if selection.trajectory_index == trajectory
                )
                for trajectory in informed_begun
            ]
            backup_counts.append(cell.backup_count)
            begun_counts.append(len(informed_begun))
            completed_counts.append(len(informed_completed))
            update_counts.append(cell.backup_update_count)
            start_feedback_counts.extend(start_counts)
            rows.append(
                {
                    "backup_count": cell.backup_count,
                    "backup_update_entry_count": cell.backup_update_count,
                    "exploration_seed": cell.exploration_seed,
                    "feedback_informed_begun_trajectory_count": len(informed_begun),
                    "feedback_informed_completed_trajectory_count": len(
                        informed_completed
                    ),
                    "prior_feedback_counts_at_informed_starts": start_counts,
                    "task_fingerprint": cell.task_fingerprint,
                }
            )
        result[method] = {
            "backup_count_distribution": _count_payload(backup_counts),
            "backup_update_entry_count_distribution": _count_payload(update_counts),
            "cell_count": len(rows),
            "feedback_informed_begun_trajectory_count_distribution": (
                _count_payload(begun_counts)
            ),
            "feedback_informed_completed_trajectory_count_distribution": (
                _count_payload(completed_counts)
            ),
            "ordered_cell_rows": rows,
            "prior_feedback_count_at_informed_start_distribution": _count_payload(
                start_feedback_counts
            ),
        }
    return result


def reduce_verified_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Reduce already verified records under the frozen post-hoc definitions."""

    cells = _target_cells(records)
    paired = _v2_v3_reduction(cells)
    v4 = _v4_reduction(cells[V4_METHOD])
    return {
        "feedback_exposure": _feedback_exposure(cells),
        "interpretation": {
            "dense_direction_label": paired["dense_direction_label"],
            "feedback_exposure_is_descriptive_not_sufficient": True,
            "handoff_decision": HANDOFF_DECISION,
            "low_exposure_vs_feedback_direction_cause_not_identified": True,
        },
        "v2_v3_paired": paired,
        "v4_anchor": v4,
    }


def _read_strict_json_object(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        parsed = strict_json_loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise PosthocMechanismAuditError(f"{label} could not be read exactly") from error
    return _strict_object(parsed, label), raw


def _git(repository: Path, *arguments: str) -> bytes:
    try:
        return subprocess.run(
            ("git", "-C", os.fspath(repository), *arguments),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        raise PosthocMechanismAuditError("git source attestation failed") from error


def _source_attestation(repository: Path) -> dict[str, Any]:
    status = _git(repository, "status", "--porcelain", "--untracked-files=all")
    if status:
        raise PosthocMechanismAuditError("post-hoc audit requires a clean checkout")
    revision = _git(repository, "rev-parse", "HEAD").decode("ascii").strip()
    module_raw = (repository / MODULE_RELATIVE_PATH).read_bytes()
    design_raw = (repository / DESIGN_RELATIVE_PATH).read_bytes()
    if (
        _git(repository, "show", f"HEAD:{MODULE_RELATIVE_PATH.as_posix()}")
        != module_raw
        or _git(repository, "show", f"HEAD:{DESIGN_RELATIVE_PATH.as_posix()}")
        != design_raw
    ):
        raise PosthocMechanismAuditError("post-hoc source differs from exact HEAD")
    return {
        "audit_module_path": MODULE_RELATIVE_PATH.as_posix(),
        "audit_module_sha256": hashlib.sha256(module_raw).hexdigest(),
        "frozen_design_path": DESIGN_RELATIVE_PATH.as_posix(),
        "frozen_design_sha256": hashlib.sha256(design_raw).hexdigest(),
        "source_revision": revision,
        "worktree_clean": True,
    }


def build_receipt(
    artifact_path: Path,
    bundle_dir: Path,
    authorization_path: Path,
    authorization_digest: str,
    authorization_revision: str,
    summary_path: Path,
    summary_digest: str,
    artifact_commit_digest: str,
    *,
    repository_root: Path,
) -> dict[str, Any]:
    """Revalidate fixed inputs and construct one deterministic audit receipt."""

    repository = repository_root.resolve()
    source = _source_attestation(repository)
    try:
        recomputed_summary = (
            analysis.analyze_countdown_thompson_diagnostic_artifact_v2r3(
                artifact_path,
                bundle_dir,
                authorization_path,
                authorization_digest,
                authorization_revision,
                repository_root=repository,
            )
        )
    except analysis.DiagnosticAnalysisError as error:
        raise PosthocMechanismAuditError(
            "v2r3 diagnostic replay and analysis did not close"
        ) from error
    observed_summary, summary_raw = _read_strict_json_object(
        summary_path, "published diagnostic summary"
    )
    summary_core = {
        key: value
        for key, value in observed_summary.items()
        if key != "deterministic_digest"
    }
    if (
        observed_summary.get("deterministic_digest") != summary_digest
        or sha256_json(summary_core) != summary_digest
        or observed_summary != recomputed_summary
    ):
        raise PosthocMechanismAuditError("published summary does not exactly recompute")

    authorization, _ = _read_strict_json_object(
        authorization_path, "execution authorization"
    )
    if authorization.get("deterministic_digest") != authorization_digest:
        raise PosthocMechanismAuditError("execution authorization digest drifted")
    try:
        verified = regular_file_publication.verify_countdown_thompson_diagnostic_v2(
            artifact_path,
            expected_parent_binding=authorization["output_parent_binding"],
            authorization_digest=authorization_digest,
        )
    except (KeyError, regular_file_publication.RegularFilePublicationV2Error) as error:
        raise PosthocMechanismAuditError("committed collective revalidation failed") from error
    records = verified.records
    if (
        verified.artifact_commit_digest != artifact_commit_digest
        or verified.run_manifest_digest != recomputed_summary["run_manifest_digest"]
        or len(records) != EXPECTED_RECORD_COUNT
    ):
        raise PosthocMechanismAuditError("committed collective provenance drifted")

    reductions = reduce_verified_records(records)
    second_source = _source_attestation(repository)
    if second_source != source or summary_path.read_bytes() != summary_raw:
        raise PosthocMechanismAuditError("audit source or summary changed during reduction")
    core: dict[str, Any] = {
        "claim_boundary": CLAIM_BOUNDARY,
        "input_provenance": {
            "artifact_commit_digest": verified.artifact_commit_digest,
            "artifact_path": os.fspath(artifact_path),
            "authorization_digest": authorization_digest,
            "authorization_revision": authorization_revision,
            "collective_manifest_digest": verified.collective_manifest_digest,
            "record_count": len(records),
            "records_jsonl_byte_count": len(verified.records_jsonl_bytes),
            "records_jsonl_sha256": hashlib.sha256(
                verified.records_jsonl_bytes
            ).hexdigest(),
            "run_manifest_digest": verified.run_manifest_digest,
            "summary_deterministic_digest": summary_digest,
            "summary_path": os.fspath(summary_path),
            "summary_raw_byte_count": len(summary_raw),
            "summary_raw_sha256": hashlib.sha256(summary_raw).hexdigest(),
        },
        "integrity_status": "PASS",
        "reductions": reductions,
        "schema_version": SCHEMA_VERSION,
        "source_attestation": source,
    }
    return {**core, "deterministic_digest": sha256_json(core)}


def _write_no_overwrite(path: Path, payload: Mapping[str, Any]) -> None:
    raw = (canonical_json(payload) + "\n").encode("utf-8")
    path = Path(os.path.abspath(os.fspath(path)))
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = -1
    created = False
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags, 0o600)
        created = True
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise PosthocMechanismAuditError("receipt write made no progress")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        parent_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
        if path.read_bytes() != raw:
            raise PosthocMechanismAuditError("published receipt bytes changed")
    except FileExistsError as error:
        raise PosthocMechanismAuditError("receipt output already exists") from error
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        if created:
            try:
                path.unlink()
            except OSError:
                pass
        raise


def _self_test() -> dict[str, object]:
    if _comparison(3, 2) != "improved" or _comparison(2, 3) != "worse":
        raise AssertionError("comparison self-test failed")
    if _comparison(2, 2) != "equal" or _comparison(None, 2) != "not_comparable":
        raise AssertionError("comparison boundary self-test failed")
    if _count_payload([2, 1, 2]) != {"1": 1, "2": 2}:
        raise AssertionError("distribution self-test failed")
    return {
        "claim_boundary": "synthetic helper checks only; no diagnostic opened",
        "status": "PASS",
    }


class _FailClosedParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise PosthocMechanismAuditError(message)


def _parser() -> argparse.ArgumentParser:
    parser = _FailClosedParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--artifact-commit-digest")
    parser.add_argument("--authorization-digest")
    parser.add_argument("--authorization-file", type=Path)
    parser.add_argument("--authorization-revision")
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repository-root", type=Path)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--summary-digest")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        arguments = _parser().parse_args(argv)
        supplied = (
            arguments.artifact,
            arguments.artifact_commit_digest,
            arguments.authorization_digest,
            arguments.authorization_file,
            arguments.authorization_revision,
            arguments.bundle,
            arguments.output,
            arguments.repository_root,
            arguments.summary,
            arguments.summary_digest,
        )
        if arguments.self_test:
            if any(value is not None for value in supplied):
                raise PosthocMechanismAuditError(
                    "--self-test accepts no diagnostic paths or digests"
                )
            result: Mapping[str, Any] = _self_test()
        else:
            if any(value is None for value in supplied):
                raise PosthocMechanismAuditError(
                    "audit mode requires every path, revision, and digest argument"
                )
            receipt = build_receipt(
                arguments.artifact,
                arguments.bundle,
                arguments.authorization_file,
                arguments.authorization_digest,
                arguments.authorization_revision,
                arguments.summary,
                arguments.summary_digest,
                arguments.artifact_commit_digest,
                repository_root=arguments.repository_root,
            )
            _write_no_overwrite(arguments.output, receipt)
            result = {
                "claim_boundary": CLAIM_BOUNDARY,
                "dense_direction_label": receipt["reductions"]["interpretation"][
                    "dense_direction_label"
                ],
                "output_path": os.fspath(arguments.output),
                "receipt_digest": receipt["deterministic_digest"],
                "status": "PASS",
            }
        print(canonical_json(result))
        return 0
    except (OSError, PosthocMechanismAuditError) as error:
        print(
            canonical_json(
                {
                    "claim_boundary": (
                        "INVALID: no post-hoc mechanism receipt was authorized"
                    ),
                    "error": str(error),
                    "status": "INVALID",
                }
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
