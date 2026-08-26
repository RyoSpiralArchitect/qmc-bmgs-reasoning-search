"""Read-only selection-margin audit for the fixed Thompson diagnostic.

The audit invokes the existing deterministic verification replay, reconstructs
the recorded node-local posterior state, and computes local score sensitivity
reductions.  It does not run a new outcome-bearing search or infer terminal
performance under an unobserved scale.
"""

from __future__ import annotations

import argparse
import hashlib
import math
import os
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping, Sequence

from qmc_bmgs.experiments import countdown_thompson_posthoc_mechanism as posthoc
from qmc_bmgs.substrate.trace import canonical_json, sha256_json


SCHEMA_VERSION = "qmc-bmgs-countdown-thompson-selection-margin/v1"
MODULE_RELATIVE_PATH = Path(
    "src/qmc_bmgs/experiments/countdown_thompson_selection_margin.py"
)
DESIGN_RELATIVE_PATH = Path(
    "docs/strategy/countdown_thompson_selection_margin_audit.md"
)
CLAIM_BOUNDARY = (
    "Exploratory local score-sensitivity audit of one fixed diagnostic. "
    "Integrity PASS is provenance, replay, reconstruction, pairing, and "
    "reduction closure only; scale boundaries do not predict action quality, "
    "terminal performance, retry success, or locked-128 behavior."
)
HANDOFF_DECISION = posthoc.HANDOFF_DECISION
METHODS = posthoc.METHODS
V2_METHOD = posthoc.V2_METHOD
V3_METHOD = posthoc.V3_METHOD
V4_METHOD = posthoc.V4_METHOD
EXPECTED_RECORD_COUNT = posthoc.EXPECTED_RECORD_COUNT
EXPECTED_METHOD_CELL_COUNT = posthoc.EXPECTED_METHOD_CELL_COUNT
EXPECTED_TASK_COUNT = posthoc.EXPECTED_TASK_COUNT
EXPECTED_SEEDS = posthoc.EXPECTED_SEEDS
FROZEN_ARTIFACT_COMMIT_DIGEST = (
    "ffd5f875f3d560382dd21fddec95b47ad0d4442913d8a5fb7faf104d12f209b9"
)
FROZEN_RUN_MANIFEST_DIGEST = (
    "465f2ec53551eefb2892171aa7ac0815bf3b139d2b0f2f549ba9685c34d9def6"
)
FROZEN_SUMMARY_DIGEST = (
    "46ebdb1eabcaa91220ed8bb10370f70aad0c61d37a2ef6150d09ca29beac0db5"
)
FROZEN_AUTHORIZATION_DIGEST = (
    "88f6639ccc9e949a7633a5cd243099ae28e85c2cceb3bcd7eab7303387474c28"
)
FROZEN_AUTHORIZATION_REVISION = "28cb810dd730cb27a28b8f1d89365dafa12ab980"
FROZEN_POSTHOC_DIGEST = (
    "02a0ecd90f6e695d22f06d77ee74a41210045811913c9e5b2bd793110089c262"
)
FROZEN_POSTHOC_RAW_SHA256 = (
    "07c747aaaef5709c3b215b7c7645d34e8968712c5b273fe29b016510d9ac596c"
)
POSTHOC_FRESH_CROSSCHECK_KEYS = (
    "claim_boundary",
    "input_provenance",
    "integrity_status",
    "reductions",
    "schema_version",
    "supplemental_validation",
)


class SelectionMarginAuditError(ValueError):
    """Raised before receipt publication when the audit cannot close."""


def _require_frozen_input_anchors(
    *,
    artifact_commit_digest: str,
    authorization_digest: str,
    authorization_revision: str,
    summary_digest: str,
    posthoc_digest: str,
    posthoc_raw_sha256: str,
) -> None:
    provided = {
        "artifact_commit_digest": artifact_commit_digest,
        "authorization_digest": authorization_digest,
        "authorization_revision": authorization_revision,
        "posthoc_digest": posthoc_digest,
        "posthoc_raw_sha256": posthoc_raw_sha256,
        "summary_digest": summary_digest,
    }
    expected = {
        "artifact_commit_digest": FROZEN_ARTIFACT_COMMIT_DIGEST,
        "authorization_digest": FROZEN_AUTHORIZATION_DIGEST,
        "authorization_revision": FROZEN_AUTHORIZATION_REVISION,
        "posthoc_digest": FROZEN_POSTHOC_DIGEST,
        "posthoc_raw_sha256": FROZEN_POSTHOC_RAW_SHA256,
        "summary_digest": FROZEN_SUMMARY_DIGEST,
    }
    drifted = sorted(
        name for name, value in provided.items() if value != expected[name]
    )
    if drifted:
        raise SelectionMarginAuditError(
            "caller-supplied frozen input anchors drifted: " + ", ".join(drifted)
        )


@dataclass(frozen=True)
class _Posterior:
    visits: int = 0
    mean: float = 0.0
    m2: float = 0.0

    def to_dict(self) -> dict[str, int | float]:
        return {"m2": self.m2, "mean": self.mean, "visits": self.visits}


@dataclass(frozen=True)
class _Selection:
    event_index: int
    trajectory_index: int
    depth: int
    state: tuple[int, ...]
    child_state: tuple[int, ...]
    action_index: int
    action_count: int
    scored_action_indices: tuple[int, ...]
    selection_values: tuple[float, ...]
    selection_values_digest: str
    selected_value: float
    posterior: tuple[_Posterior, ...]
    posterior_before_digest: str
    action_order_digest: str
    proposal_behavior_digest: str
    point_digest: str | None
    noise_dimension_normalizer: float
    selection_rule_id: str
    selection_phase: str | None
    prior_feedback_count: int

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

    @property
    def posterior_means(self) -> tuple[float, ...]:
        return tuple(item.mean for item in self.posterior)

    @property
    def posterior_visits(self) -> tuple[int, ...]:
        return tuple(item.visits for item in self.posterior)


@dataclass(frozen=True)
class _CellTrace:
    cell_id: str
    method_label: str
    task_fingerprint: str
    exploration_seed: int
    selections: tuple[_Selection, ...]
    feedback_selection_count: int
    backup_count: int

    @property
    def pair_key(self) -> tuple[str, int]:
        return self.task_fingerprint, self.exploration_seed


def _strict_object(value: object, label: str) -> dict[str, Any]:
    if type(value) is not dict or any(type(key) is not str for key in value):
        raise SelectionMarginAuditError(f"{label} must be an exact object")
    return value


def _plain_nonnegative_int(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise SelectionMarginAuditError(f"{label} must be a non-negative plain int")
    return value


def _plain_float(value: object, label: str) -> float:
    if type(value) is not float or not math.isfinite(value):
        raise SelectionMarginAuditError(f"{label} must be a finite plain float")
    return value


def _plain_float_vector(value: object, label: str) -> tuple[float, ...]:
    if type(value) is not list:
        raise SelectionMarginAuditError(f"{label} must be a float list")
    return tuple(_plain_float(item, f"{label} entry") for item in value)


def _plain_int_vector(value: object, label: str) -> tuple[int, ...]:
    if type(value) is not list or any(type(item) is not int for item in value):
        raise SelectionMarginAuditError(f"{label} must be a plain-int list")
    return tuple(value)


def _digest_string(value: object, label: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise SelectionMarginAuditError(f"{label} must be a lowercase SHA-256")
    return value


def _posterior_from_payload(value: object, label: str) -> _Posterior:
    payload = _strict_object(value, label)
    if set(payload) != {"m2", "mean", "visits"}:
        raise SelectionMarginAuditError(f"{label} keys drifted")
    visits = _plain_nonnegative_int(payload.get("visits"), f"{label} visits")
    mean = _plain_float(payload.get("mean"), f"{label} mean")
    m2 = _plain_float(payload.get("m2"), f"{label} m2")
    return _Posterior(visits=visits, mean=mean, m2=m2)


def _stable_argmax(values: Sequence[float]) -> int:
    if not values or any(type(value) is not float or not math.isfinite(value) for value in values):
        raise SelectionMarginAuditError("score vector must contain finite plain floats")
    return max(range(len(values)), key=lambda index: (values[index], -index))


def _stable_fraction_argmax(values: Sequence[Fraction]) -> int:
    if not values:
        raise SelectionMarginAuditError("exact score vector is empty")
    return max(range(len(values)), key=lambda index: (values[index], -index))


def _runner_up(values: Sequence[float], winner: int) -> int:
    if len(values) < 2 or winner not in range(len(values)):
        raise SelectionMarginAuditError("selection lacks a valid runner-up")
    return max(
        (index for index in range(len(values)) if index != winner),
        key=lambda index: (values[index], -index),
    )


def _selection_from_event(
    event_index: int,
    payload: Mapping[str, Any],
    nodes: dict[tuple[int, ...], list[_Posterior]],
    feedback_count: int,
    method_label: str,
) -> _Selection:
    trajectory = _plain_nonnegative_int(
        payload.get("trajectory_index"), "selection trajectory_index"
    )
    depth = _plain_nonnegative_int(payload.get("depth"), "selection depth")
    state = _plain_int_vector(payload.get("state"), "selection state")
    child_state = _plain_int_vector(
        payload.get("child_state"), "selection child_state"
    )
    scores = _plain_float_vector(
        payload.get("selection_values"), "selection values"
    )
    if len(scores) < 2:
        raise SelectionMarginAuditError("selection requires at least two actions")
    action_count = len(scores)
    scored = _plain_int_vector(
        payload.get("scored_action_indices"), "scored action indices"
    )
    if scored != tuple(range(action_count)):
        raise SelectionMarginAuditError("scored action coverage drifted")
    action_index = _plain_nonnegative_int(
        payload.get("action_index"), "selection action_index"
    )
    if action_index >= action_count or action_index != _stable_argmax(scores):
        raise SelectionMarginAuditError("recorded selection is not the stable argmax")
    selected_value = _plain_float(
        payload.get("selected_value"), "selected value"
    )
    if selected_value != scores[action_index]:
        raise SelectionMarginAuditError("selected value differs from score vector")
    score_digest = _digest_string(
        payload.get("selection_values_digest"), "selection values digest"
    )
    if score_digest != sha256_json(list(scores)):
        raise SelectionMarginAuditError("selection values digest drifted")

    posterior = nodes.setdefault(
        state, [_Posterior() for _ in range(action_count)]
    )
    if len(posterior) != action_count:
        raise SelectionMarginAuditError("node action dimension drifted")
    posterior_digest = _digest_string(
        payload.get("posterior_before_digest"), "posterior-before digest"
    )
    if posterior_digest != sha256_json([item.to_dict() for item in posterior]):
        raise SelectionMarginAuditError("reconstructed posterior digest drifted")

    semantics = _strict_object(
        payload.get("selection_semantics"), "selection semantics"
    )
    semantic_action_count = _plain_nonnegative_int(
        semantics.get("action_count"), "semantic action count"
    )
    if semantic_action_count != action_count:
        raise SelectionMarginAuditError("semantic action count drifted")
    normalizer = _plain_float(
        semantics.get("noise_dimension_normalizer"), "noise dimension normalizer"
    )
    selection_rule_id = semantics.get("selection_rule_id")
    if type(selection_rule_id) is not str or not selection_rule_id:
        raise SelectionMarginAuditError("selection rule id drifted")
    phase = semantics.get("selection_phase")
    if phase is not None and type(phase) is not str:
        raise SelectionMarginAuditError("selection phase type drifted")
    if method_label == V4_METHOD:
        expected_phase = "greedy_anchor" if trajectory == 0 else "posterior_perturbation"
        if phase != expected_phase:
            raise SelectionMarginAuditError("v4 selection phase drifted")
    elif phase is not None:
        raise SelectionMarginAuditError("v2/v3 unexpectedly records a selection phase")

    raw_point_digest = payload.get("point_digest")
    if method_label == V4_METHOD and phase == "greedy_anchor":
        if raw_point_digest is not None:
            raise SelectionMarginAuditError("greedy anchor unexpectedly used a point")
        point_digest: str | None = None
    else:
        point_digest = _digest_string(raw_point_digest, "selection point digest")
    action_order_digest = _digest_string(
        payload.get("action_order_digest"), "action-order digest"
    )
    proposal_behavior_digest = _digest_string(
        payload.get("proposal_behavior_digest"), "proposal-behavior digest"
    )
    return _Selection(
        event_index=event_index,
        trajectory_index=trajectory,
        depth=depth,
        state=state,
        child_state=child_state,
        action_index=action_index,
        action_count=action_count,
        scored_action_indices=scored,
        selection_values=scores,
        selection_values_digest=score_digest,
        selected_value=selected_value,
        posterior=tuple(posterior),
        posterior_before_digest=posterior_digest,
        action_order_digest=action_order_digest,
        proposal_behavior_digest=proposal_behavior_digest,
        point_digest=point_digest,
        noise_dimension_normalizer=normalizer,
        selection_rule_id=selection_rule_id,
        selection_phase=phase,
        prior_feedback_count=feedback_count,
    )


def _trace_from_record(record: Mapping[str, Any]) -> _CellTrace:
    if type(record) is not dict:
        raise SelectionMarginAuditError("run record must be an exact object")
    labels = _strict_object(record.get("labels"), "record labels")
    method = labels.get("method_label")
    task = labels.get("task_fingerprint")
    seed = labels.get("exploration_seed")
    proposal = labels.get("proposal_label")
    cell_id = record.get("cell_id")
    if (
        method not in METHODS
        or type(task) is not str
        or not task
        or type(seed) is not int
        or seed not in EXPECTED_SEEDS
        or proposal != "heuristic"
        or type(cell_id) is not str
        or len(cell_id) != 64
    ):
        raise SelectionMarginAuditError("target cell identity drifted")

    search_record = _strict_object(record.get("search_record"), "search record")
    events = search_record.get("events")
    if type(events) is not list:
        raise SelectionMarginAuditError("search events must be a list")
    nodes: dict[tuple[int, ...], list[_Posterior]] = {}
    selections: list[_Selection] = []
    coordinates: set[tuple[int, int]] = set()
    terminal_trajectories: list[int] = []
    backup_trajectories: list[int] = []
    feedback_count = 0

    for event_index, raw_event in enumerate(events):
        event = _strict_object(raw_event, f"event {event_index}")
        payload = _strict_object(
            event.get("payload"), f"event {event_index} payload"
        )
        kind = event.get("kind")
        if kind == "selection_committed":
            selection = _selection_from_event(
                event_index, payload, nodes, feedback_count, method
            )
            if selection.coordinate in coordinates:
                raise SelectionMarginAuditError("selection coordinate is duplicated")
            coordinates.add(selection.coordinate)
            selections.append(selection)
        elif kind == "terminal_verified":
            trajectory = _plain_nonnegative_int(
                payload.get("trajectory_index"), "terminal trajectory_index"
            )
            terminal_trajectories.append(trajectory)
        elif kind == "trajectory_backed_up":
            trajectory = _plain_nonnegative_int(
                payload.get("trajectory_index"), "backup trajectory_index"
            )
            if (
                len(terminal_trajectories) != len(backup_trajectories) + 1
                or terminal_trajectories[-1] != trajectory
            ):
                raise SelectionMarginAuditError("terminal/backup event order drifted")
            updates = payload.get("updates")
            if type(updates) is not list or not updates:
                raise SelectionMarginAuditError("backup updates must be a nonempty list")
            for update_index, raw_update in enumerate(updates):
                update = _strict_object(
                    raw_update, f"backup update {update_index}"
                )
                state = _plain_int_vector(update.get("state"), "backup update state")
                action_index = _plain_nonnegative_int(
                    update.get("action_index"), "backup update action index"
                )
                if state not in nodes or action_index >= len(nodes[state]):
                    raise SelectionMarginAuditError("backup update targets an unknown edge")
                before = _posterior_from_payload(
                    update.get("before"), "backup update before"
                )
                after = _posterior_from_payload(
                    update.get("after"), "backup update after"
                )
                if before != nodes[state][action_index]:
                    raise SelectionMarginAuditError("backup before-state drifted")
                if after.visits != before.visits + 1:
                    raise SelectionMarginAuditError("backup visit increment drifted")
                nodes[state][action_index] = after
            backup_trajectories.append(trajectory)
            feedback_count += 1

    if not selections or not backup_trajectories:
        raise SelectionMarginAuditError("target cell lacks adaptive trace evidence")
    if terminal_trajectories != backup_trajectories:
        raise SelectionMarginAuditError("terminal/backup closure drifted")
    if backup_trajectories != list(range(len(backup_trajectories))):
        raise SelectionMarginAuditError("backup trajectory indices are not contiguous")
    feedback_selections = [
        selection for selection in selections if selection.prior_feedback_count >= 1
    ]
    if not feedback_selections:
        raise SelectionMarginAuditError("target cell has no feedback-informed selection")
    if method == V4_METHOD and any(
        selection.selection_phase != "posterior_perturbation"
        for selection in feedback_selections
    ):
        raise SelectionMarginAuditError("v4 feedback selection is not posterior phase")
    return _CellTrace(
        cell_id=cell_id,
        method_label=method,
        task_fingerprint=task,
        exploration_seed=seed,
        selections=tuple(selections),
        feedback_selection_count=len(feedback_selections),
        backup_count=len(backup_trajectories),
    )


def _target_traces(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, tuple[_CellTrace, ...]]:
    if len(records) != EXPECTED_RECORD_COUNT:
        raise SelectionMarginAuditError("diagnostic record count drifted")
    selected: dict[str, list[_CellTrace]] = {method: [] for method in METHODS}
    for record in records:
        labels = _strict_object(record.get("labels"), "record labels")
        method = labels.get("method_label")
        if method in METHODS:
            selected[method].append(_trace_from_record(record))

    result: dict[str, tuple[_CellTrace, ...]] = {}
    common_keys: set[tuple[str, int]] | None = None
    for method in METHODS:
        cells = sorted(selected[method], key=lambda cell: cell.pair_key)
        if len(cells) != EXPECTED_METHOD_CELL_COUNT:
            raise SelectionMarginAuditError(f"{method} coverage drifted")
        keys = [cell.pair_key for cell in cells]
        if len(set(keys)) != len(keys):
            raise SelectionMarginAuditError(f"{method} contains duplicate pairs")
        tasks = {cell.task_fingerprint for cell in cells}
        if len(tasks) != EXPECTED_TASK_COUNT or any(
            {
                cell.exploration_seed
                for cell in cells
                if cell.task_fingerprint == task
            }
            != set(EXPECTED_SEEDS)
            for task in tasks
        ):
            raise SelectionMarginAuditError(f"{method} task/seed matrix drifted")
        key_set = set(keys)
        if common_keys is None:
            common_keys = key_set
        elif key_set != common_keys:
            raise SelectionMarginAuditError("method pair coverage differs")
        result[method] = tuple(cells)
    return result


def _fraction_payload(value: Fraction) -> dict[str, int]:
    return {"denominator": value.denominator, "numerator": value.numerator}


def _finite_fraction_approximation(value: Fraction) -> float | None:
    try:
        approximation = float(value)
    except OverflowError:
        return None
    return approximation if math.isfinite(approximation) else None


def _scale_bin(value: Fraction | None) -> str:
    if value is None:
        return "none"
    if value == 0:
        return "zero"
    for upper, label in (
        (Fraction(1), "(0,1]"),
        (Fraction(2), "(1,2]"),
        (Fraction(4), "(2,4]"),
        (Fraction(8), "(4,8]"),
        (Fraction(16), "(8,16]"),
    ):
        if value <= upper:
            return label
    return ">16"


def _boundary_payload(
    intercepts: Sequence[Fraction],
    slopes: Sequence[Fraction],
    *,
    expected_observed_action: int,
) -> dict[str, Any]:
    if len(intercepts) < 2 or len(intercepts) != len(slopes):
        raise SelectionMarginAuditError("boundary vectors have invalid dimensions")
    baseline = _stable_fraction_argmax(intercepts)
    observed_values = [
        intercept + slope for intercept, slope in zip(intercepts, slopes)
    ]
    observed = _stable_fraction_argmax(observed_values)
    if observed != expected_observed_action:
        raise SelectionMarginAuditError("exact scale path misses the recorded action")

    candidates: list[tuple[Fraction, int]] = []
    for action_index in range(len(intercepts)):
        if action_index == baseline or slopes[action_index] <= slopes[baseline]:
            continue
        numerator = intercepts[baseline] - intercepts[action_index]
        if numerator < 0:
            raise SelectionMarginAuditError("baseline is not maximal at zero scale")
        boundary = numerator / (slopes[action_index] - slopes[baseline])
        if boundary >= 0:
            candidates.append((boundary, action_index))

    if not candidates:
        return {
            "baseline_action_index": baseline,
            "boundary_action_at_tie": None,
            "boundary_challenger_action_index": None,
            "boundary_relation": "none",
            "boundary_scale_approx": None,
            "boundary_scale_exact": None,
            "boundary_scale_bin": "none",
            "changes_action_at_boundary": False,
            "observed_action_changed": observed != baseline,
            "observed_action_index": observed,
        }

    boundary = min(item[0] for item in candidates)
    at_boundary = [
        intercept + boundary * slope
        for intercept, slope in zip(intercepts, slopes)
    ]
    tie_action = _stable_fraction_argmax(at_boundary)
    top_value = at_boundary[tie_action]
    tied = [
        index for index, value in enumerate(at_boundary) if value == top_value
    ]
    challenger = max(tied, key=lambda index: (slopes[index], -index))
    if challenger == baseline:
        raise SelectionMarginAuditError("boundary lacks a right-side challenger")
    changes_at_boundary = tie_action != baseline
    if boundary < 1:
        relation = "before_observed"
    elif boundary > 1:
        relation = "after_observed"
    elif changes_at_boundary:
        relation = "at_observed_closed"
    else:
        relation = "at_observed_open"
    if (observed != baseline) is not (
        relation in {"before_observed", "at_observed_closed"}
    ):
        raise SelectionMarginAuditError("boundary relation contradicts observed action")
    return {
        "baseline_action_index": baseline,
        "boundary_action_at_tie": tie_action,
        "boundary_challenger_action_index": challenger,
        "boundary_relation": relation,
        "boundary_scale_approx": _finite_fraction_approximation(boundary),
        "boundary_scale_exact": _fraction_payload(boundary),
        "boundary_scale_bin": _scale_bin(boundary),
        "changes_action_at_boundary": changes_at_boundary,
        "observed_action_changed": observed != baseline,
        "observed_action_index": observed,
    }


def _five_number(values: Sequence[float]) -> dict[str, Any]:
    if any(type(value) is not float or not math.isfinite(value) for value in values):
        raise SelectionMarginAuditError("five-number input must be finite floats")
    if not values:
        return {
            "count": 0,
            "index_rule": "floor((n-1)*p)",
            "maximum": None,
            "median": None,
            "minimum": None,
            "q1": None,
            "q3": None,
        }
    ordered = sorted(values)

    def select(numerator: int, denominator: int) -> float:
        index = ((len(ordered) - 1) * numerator) // denominator
        return ordered[index]

    return {
        "count": len(ordered),
        "index_rule": "floor((n-1)*p)",
        "maximum": ordered[-1],
        "median": select(1, 2),
        "minimum": ordered[0],
        "q1": select(1, 4),
        "q3": select(3, 4),
    }


def _count_payload(values: Sequence[str]) -> dict[str, int]:
    counts = Counter(values)
    return {key: counts[key] for key in sorted(counts)}


def _coordinate_distribution(
    values: Sequence[tuple[int, int]],
) -> dict[str, int]:
    return _count_payload(
        [f"trajectory_{trajectory}_depth_{depth}" for trajectory, depth in values]
    )


def _individual_selection_row(
    cell: _CellTrace, selection: _Selection
) -> dict[str, Any]:
    scores = selection.selection_values
    means = selection.posterior_means
    winner = selection.action_index
    runner = _runner_up(scores, winner)
    exact_scores = [Fraction.from_float(value) for value in scores]
    exact_means = [Fraction.from_float(value) for value in means]
    margin_exact = exact_scores[winner] - exact_scores[runner]
    if margin_exact < 0:
        raise SelectionMarginAuditError("observed winner margin is negative")
    boundary = _boundary_payload(
        [score - mean for score, mean in zip(exact_scores, exact_means)],
        exact_means,
        expected_observed_action=winner,
    )
    nonzero_mean_count = sum(value != 0 for value in exact_means)
    span = max(means) - min(means)
    if not math.isfinite(span) or span < 0.0:
        raise SelectionMarginAuditError("posterior mean span is invalid")
    return {
        "action_count": selection.action_count,
        "depth": selection.depth,
        "exploration_seed": cell.exploration_seed,
        "method_label": cell.method_label,
        "nonzero_posterior_mean_action_count": nonzero_mean_count,
        "observed_action_index": winner,
        "observed_margin": scores[winner] - scores[runner],
        "observed_margin_exact": _fraction_payload(margin_exact),
        "point_digest": selection.point_digest,
        "posterior_mean_digest": sha256_json(list(means)),
        "posterior_mean_span": span,
        "posterior_mean_vector": list(means),
        "posterior_scale": boundary,
        "runner_up_action_index": runner,
        "runner_up_posterior_mean": means[runner],
        "selection_values_digest": selection.selection_values_digest,
        "state": list(selection.state),
        "task_fingerprint": cell.task_fingerprint,
        "trajectory_index": selection.trajectory_index,
        "winner_posterior_mean": means[winner],
    }


def _individual_reduction(
    traces: Mapping[str, Sequence[_CellTrace]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for method in METHODS:
        rows: list[dict[str, Any]] = []
        for cell in traces[method]:
            for selection in cell.selections:
                if selection.prior_feedback_count < 1:
                    continue
                if method == V4_METHOD and selection.selection_phase != "posterior_perturbation":
                    raise SelectionMarginAuditError("v4 feedback selection phase drifted")
                rows.append(_individual_selection_row(cell, selection))
        rows.sort(
            key=lambda row: (
                row["task_fingerprint"],
                row["exploration_seed"],
                row["trajectory_index"],
                row["depth"],
            )
        )
        if sum(cell.feedback_selection_count for cell in traces[method]) != len(rows):
            raise SelectionMarginAuditError("feedback selection coverage drifted")
        margins = [row["observed_margin"] for row in rows]
        spans = [
            row["posterior_mean_span"]
            for row in rows
            if row["posterior_mean_span"] > 0.0
        ]
        result[method] = {
            "boundary_relation_distribution": _count_payload(
                [row["posterior_scale"]["boundary_relation"] for row in rows]
            ),
            "boundary_scale_bin_distribution": _count_payload(
                [row["posterior_scale"]["boundary_scale_bin"] for row in rows]
            ),
            "cell_count": len(traces[method]),
            "feedback_informed_selection_count": len(rows),
            "nonzero_posterior_mean_selection_count": sum(
                row["nonzero_posterior_mean_action_count"] > 0 for row in rows
            ),
            "observed_action_changed_from_zero_mean_count": sum(
                row["posterior_scale"]["observed_action_changed"] for row in rows
            ),
            "observed_margin_five_number": _five_number(margins),
            "ordered_selection_rows": rows,
            "positive_posterior_mean_span_five_number": _five_number(spans),
            "zero_posterior_mean_selection_count": sum(
                row["nonzero_posterior_mean_action_count"] == 0 for row in rows
            ),
        }
    return result


def _predecision_identity(selection: _Selection) -> tuple[object, ...]:
    return (
        selection.trajectory_index,
        selection.depth,
        selection.state,
        selection.action_count,
        selection.scored_action_indices,
        selection.action_order_digest,
        selection.proposal_behavior_digest,
        selection.point_digest,
        selection.noise_dimension_normalizer,
        selection.selection_rule_id,
        selection.posterior_visits,
        selection.prior_feedback_count,
    )


def _pair_surface_row(
    left_cell: _CellTrace,
    left: _Selection,
    right: _Selection,
) -> dict[str, Any]:
    if _predecision_identity(left) != _predecision_identity(right):
        raise SelectionMarginAuditError("pair surface predecision identity drifted")
    left_scores = left.selection_values
    right_scores = right.selection_values
    left_means = left.posterior_means
    right_means = right.posterior_means
    left_exact = [Fraction.from_float(value) for value in left_scores]
    right_exact = [Fraction.from_float(value) for value in right_scores]
    left_mean_exact = [Fraction.from_float(value) for value in left_means]
    right_mean_exact = [Fraction.from_float(value) for value in right_means]
    score_delta_exact = [
        right_value - left_value
        for left_value, right_value in zip(left_exact, right_exact)
    ]
    mean_delta_exact = [
        right_value - left_value
        for left_value, right_value in zip(left_mean_exact, right_mean_exact)
    ]
    score_delta = [
        right_value - left_value
        for left_value, right_value in zip(left_scores, right_scores)
    ]
    mean_delta = [
        right_value - left_value
        for left_value, right_value in zip(left_means, right_means)
    ]
    residuals = [
        abs(score_delta_value - mean_delta_value)
        for score_delta_value, mean_delta_value in zip(
            score_delta_exact, mean_delta_exact
        )
    ]
    max_residual = max(residuals)
    left_runner = _runner_up(left_scores, left.action_index)
    right_runner = _runner_up(right_scores, right.action_index)
    dense_boundary = _boundary_payload(
        left_exact,
        score_delta_exact,
        expected_observed_action=right.action_index,
    )
    if dense_boundary["baseline_action_index"] != left.action_index:
        raise SelectionMarginAuditError("paired scale path misses the v2 action")
    return {
        "action_count": left.action_count,
        "action_changed_at_observed_dense_scale": (
            left.action_index != right.action_index
        ),
        "dense_score_scale": dense_boundary,
        "depth": left.depth,
        "exploration_seed": left_cell.exploration_seed,
        "maximum_absolute_posterior_mean_delta": max(
            abs(value) for value in mean_delta
        ),
        "maximum_absolute_rounding_residual": _finite_fraction_approximation(
            max_residual
        ),
        "maximum_absolute_rounding_residual_exact": _fraction_payload(max_residual),
        "maximum_absolute_score_delta": max(abs(value) for value in score_delta),
        "nonzero_posterior_mean_delta_action_count": sum(
            value != 0 for value in mean_delta_exact
        ),
        "nonzero_score_delta_action_count": sum(
            value != 0 for value in score_delta_exact
        ),
        "posterior_mean_delta_digest": sha256_json(mean_delta),
        "posterior_mean_delta_vector": mean_delta,
        "score_delta_digest": sha256_json(score_delta),
        "score_delta_vector": score_delta,
        "state": list(left.state),
        "task_fingerprint": left_cell.task_fingerprint,
        "trajectory_index": left.trajectory_index,
        "v2_action_index": left.action_index,
        "v2_margin": left_scores[left.action_index] - left_scores[left_runner],
        "v2_selection_values_digest": left.selection_values_digest,
        "v3_action_index": right.action_index,
        "v3_margin": right_scores[right.action_index] - right_scores[right_runner],
        "v3_selection_values_digest": right.selection_values_digest,
    }


def _published_pair_rows(
    published_posthoc: Mapping[str, Any],
) -> dict[tuple[str, int], Mapping[str, Any]]:
    reductions = _strict_object(
        published_posthoc.get("reductions"), "published post-hoc reductions"
    )
    paired = _strict_object(reductions.get("v2_v3_paired"), "published v2/v3")
    rows = paired.get("ordered_pair_rows")
    if type(rows) is not list or len(rows) != EXPECTED_METHOD_CELL_COUNT:
        raise SelectionMarginAuditError("published post-hoc pair coverage drifted")
    result: dict[tuple[str, int], Mapping[str, Any]] = {}
    for raw_row in rows:
        row = _strict_object(raw_row, "published post-hoc pair row")
        task = row.get("task_fingerprint")
        seed = row.get("exploration_seed")
        if type(task) is not str or type(seed) is not int:
            raise SelectionMarginAuditError("published post-hoc pair key drifted")
        key = (task, seed)
        if key in result:
            raise SelectionMarginAuditError("published post-hoc pair is duplicated")
        result[key] = row
    return result


def _posthoc_difference_coordinate(
    row: Mapping[str, Any],
) -> tuple[int, int] | None:
    diverged = row.get("feedback_informed_selection_diverged")
    if type(diverged) is not bool:
        raise SelectionMarginAuditError("published divergence flag drifted")
    raw = row.get("first_feedback_selection_difference")
    if raw is None:
        if diverged:
            raise SelectionMarginAuditError("published divergence coordinate is missing")
        return None
    coordinate = _strict_object(raw, "published divergence coordinate")
    trajectory = _plain_nonnegative_int(
        coordinate.get("trajectory_index"), "published divergence trajectory"
    )
    depth = _plain_nonnegative_int(
        coordinate.get("depth"), "published divergence depth"
    )
    if not diverged:
        raise SelectionMarginAuditError("published coordinate lacks divergence flag")
    return trajectory, depth


def _pair_one(
    left: _CellTrace,
    right: _CellTrace,
    published_row: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if left.pair_key != right.pair_key:
        raise SelectionMarginAuditError("v2/v3 pair key drifted")
    surfaces: list[dict[str, Any]] = []
    stop_reason = "trace_end_without_action_divergence"
    stop_coordinate: tuple[int, int] | None = None
    action_divergence_coordinate: tuple[int, int] | None = None
    left_selections = left.selections
    right_selections = right.selections
    limit = max(len(left_selections), len(right_selections))

    for index in range(limit):
        if index >= len(left_selections) or index >= len(right_selections):
            present = (
                left_selections[index]
                if index < len(left_selections)
                else right_selections[index]
            )
            if present.prior_feedback_count < 1:
                raise SelectionMarginAuditError("trajectory 0 selection coverage differs")
            stop_reason = "missing_selection"
            stop_coordinate = present.coordinate
            break
        left_selection = left_selections[index]
        right_selection = right_selections[index]
        if left_selection.prior_feedback_count < 1 or right_selection.prior_feedback_count < 1:
            if (
                left_selection.prior_feedback_count != 0
                or right_selection.prior_feedback_count != 0
                or left_selection.identity_payload()
                != right_selection.identity_payload()
            ):
                raise SelectionMarginAuditError("trajectory 0 identity drifted")
            continue
        if _predecision_identity(left_selection) != _predecision_identity(
            right_selection
        ):
            stop_reason = "predecision_mismatch"
            stop_coordinate = min(
                left_selection.coordinate, right_selection.coordinate
            )
            break
        surfaces.append(_pair_surface_row(left, left_selection, right_selection))
        if left_selection.action_index != right_selection.action_index:
            stop_reason = "recorded_action_divergence"
            stop_coordinate = left_selection.coordinate
            action_divergence_coordinate = left_selection.coordinate
            break
        if left_selection.child_state != right_selection.child_state:
            raise SelectionMarginAuditError("equal actions produced different child states")

    expected_coordinate = _posthoc_difference_coordinate(published_row)
    if stop_coordinate != expected_coordinate:
        raise SelectionMarginAuditError(
            "selection-margin stop differs from published first divergence"
        )
    if expected_coordinate is None and stop_reason != "trace_end_without_action_divergence":
        raise SelectionMarginAuditError("pair stopped without a published divergence")
    if not surfaces:
        raise SelectionMarginAuditError("v2/v3 pair has no common feedback surface")
    return surfaces, {
        "exploration_seed": left.exploration_seed,
        "first_action_divergence": (
            None
            if action_divergence_coordinate is None
            else {
                "depth": action_divergence_coordinate[1],
                "trajectory_index": action_divergence_coordinate[0],
            }
        ),
        "first_posthoc_difference": (
            None
            if expected_coordinate is None
            else {
                "depth": expected_coordinate[1],
                "trajectory_index": expected_coordinate[0],
            }
        ),
        "pairable_surface_count": len(surfaces),
        "stop_coordinate": (
            None
            if stop_coordinate is None
            else {
                "depth": stop_coordinate[1],
                "trajectory_index": stop_coordinate[0],
            }
        ),
        "stop_reason": stop_reason,
        "task_fingerprint": left.task_fingerprint,
    }


def _paired_reduction(
    traces: Mapping[str, Sequence[_CellTrace]],
    published_posthoc: Mapping[str, Any],
) -> dict[str, Any]:
    left_by_key = {cell.pair_key: cell for cell in traces[V2_METHOD]}
    right_by_key = {cell.pair_key: cell for cell in traces[V3_METHOD]}
    published_by_key = _published_pair_rows(published_posthoc)
    if set(left_by_key) != set(right_by_key) or set(left_by_key) != set(
        published_by_key
    ):
        raise SelectionMarginAuditError("v2/v3/post-hoc pair keys differ")

    surfaces: list[dict[str, Any]] = []
    pairs: list[dict[str, Any]] = []
    for key in sorted(left_by_key):
        pair_surfaces, pair_row = _pair_one(
            left_by_key[key], right_by_key[key], published_by_key[key]
        )
        surfaces.extend(pair_surfaces)
        pairs.append(pair_row)
    surfaces.sort(
        key=lambda row: (
            row["task_fingerprint"],
            row["exploration_seed"],
            row["trajectory_index"],
            row["depth"],
        )
    )
    first_divergences = [
        (
            row["first_action_divergence"]["trajectory_index"],
            row["first_action_divergence"]["depth"],
        )
        for row in pairs
        if row["first_action_divergence"] is not None
    ]
    first_posthoc_differences = [
        (
            row["first_posthoc_difference"]["trajectory_index"],
            row["first_posthoc_difference"]["depth"],
        )
        for row in pairs
        if row["first_posthoc_difference"] is not None
    ]
    margins_v2 = [row["v2_margin"] for row in surfaces]
    margins_v3 = [row["v3_margin"] for row in surfaces]
    max_score_delta = [row["maximum_absolute_score_delta"] for row in surfaces]
    max_mean_delta = [
        row["maximum_absolute_posterior_mean_delta"] for row in surfaces
    ]
    max_residual = [
        row["maximum_absolute_rounding_residual"] for row in surfaces
    ]
    if any(value is None for value in max_residual):
        raise SelectionMarginAuditError("rounding residual approximation overflowed")
    return {
        "action_flip_count_at_observed_dense_scale": sum(
            row["action_changed_at_observed_dense_scale"] for row in surfaces
        ),
        "boundary_relation_distribution": _count_payload(
            [row["dense_score_scale"]["boundary_relation"] for row in surfaces]
        ),
        "boundary_scale_bin_distribution": _count_payload(
            [row["dense_score_scale"]["boundary_scale_bin"] for row in surfaces]
        ),
        "first_action_divergence_coordinate_distribution": (
            _coordinate_distribution(first_divergences)
        ),
        "first_posthoc_difference_coordinate_distribution": (
            _coordinate_distribution(first_posthoc_differences)
        ),
        "maximum_absolute_posterior_mean_delta_five_number": _five_number(
            max_mean_delta
        ),
        "maximum_absolute_rounding_residual_five_number": _five_number(
            max_residual  # type: ignore[arg-type]
        ),
        "maximum_absolute_score_delta_five_number": _five_number(max_score_delta),
        "nonzero_posterior_displacement_surface_count": sum(
            row["nonzero_posterior_mean_delta_action_count"] > 0 for row in surfaces
        ),
        "nonzero_score_displacement_surface_count": sum(
            row["nonzero_score_delta_action_count"] > 0 for row in surfaces
        ),
        "ordered_pair_rows": pairs,
        "ordered_surface_rows": surfaces,
        "pair_count": len(pairs),
        "pair_stop_reason_distribution": _count_payload(
            [row["stop_reason"] for row in pairs]
        ),
        "pairable_surface_count": len(surfaces),
        "posthoc_first_divergence_crosscheck": "PASS",
        "v2_margin_five_number": _five_number(margins_v2),
        "v3_margin_five_number": _five_number(margins_v3),
        "zero_posterior_displacement_surface_count": sum(
            row["nonzero_posterior_mean_delta_action_count"] == 0 for row in surfaces
        ),
        "zero_score_displacement_surface_count": sum(
            row["nonzero_score_delta_action_count"] == 0 for row in surfaces
        ),
    }


def reduce_verified_records(
    records: Sequence[Mapping[str, Any]],
    published_posthoc: Mapping[str, Any],
) -> dict[str, Any]:
    """Reduce verified fixed traces under the frozen margin definitions."""

    traces = _target_traces(records)
    individual = _individual_reduction(traces)
    paired = _paired_reduction(traces, published_posthoc)
    return {
        "handoff_decision": HANDOFF_DECISION,
        "individual_method_selection_sensitivity": individual,
        "paired_v2_v3_common_prefix_sensitivity": paired,
        "performance_counterfactual_evaluated": False,
        "terminal_outcomes_used_in_margin_reduction": False,
    }


def _git(repository: Path, *arguments: str) -> bytes:
    try:
        return subprocess.run(
            ("git", "-C", os.fspath(repository), *arguments),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        raise SelectionMarginAuditError("git source attestation failed") from error


def _source_attestation(repository: Path) -> dict[str, Any]:
    status = _git(repository, "status", "--porcelain", "--untracked-files=all")
    if status:
        raise SelectionMarginAuditError("selection-margin audit requires a clean checkout")
    revision = _git(repository, "rev-parse", "HEAD").decode("ascii").strip()
    module_path = repository / MODULE_RELATIVE_PATH
    design_path = repository / DESIGN_RELATIVE_PATH
    try:
        module_raw = module_path.read_bytes()
        design_raw = design_path.read_bytes()
    except OSError as error:
        raise SelectionMarginAuditError("audit source could not be read") from error
    if (
        _git(repository, "show", f"HEAD:{MODULE_RELATIVE_PATH.as_posix()}")
        != module_raw
        or _git(repository, "show", f"HEAD:{DESIGN_RELATIVE_PATH.as_posix()}")
        != design_raw
    ):
        raise SelectionMarginAuditError("selection-margin source differs from exact HEAD")
    return {
        "audit_module_path": MODULE_RELATIVE_PATH.as_posix(),
        "audit_module_sha256": hashlib.sha256(module_raw).hexdigest(),
        "frozen_design_path": DESIGN_RELATIVE_PATH.as_posix(),
        "frozen_design_sha256": hashlib.sha256(design_raw).hexdigest(),
        "source_revision": revision,
        "worktree_clean": True,
    }


def _read_frozen_posthoc(
    path: Path,
    expected_digest: str,
    expected_raw_sha256: str,
) -> tuple[dict[str, Any], bytes]:
    payload, raw = posthoc._read_strict_json_object(path, "published post-hoc receipt")
    core = {
        key: value for key, value in payload.items() if key != "deterministic_digest"
    }
    if (
        payload.get("schema_version") != posthoc.SCHEMA_VERSION
        or payload.get("integrity_status") != "PASS"
        or payload.get("deterministic_digest") != expected_digest
        or sha256_json(core) != expected_digest
        or hashlib.sha256(raw).hexdigest() != expected_raw_sha256
    ):
        raise SelectionMarginAuditError("published post-hoc receipt drifted")
    return payload, raw


def build_receipt(
    artifact_path: Path,
    bundle_dir: Path,
    authorization_path: Path,
    authorization_digest: str,
    authorization_revision: str,
    summary_path: Path,
    summary_digest: str,
    artifact_commit_digest: str,
    posthoc_receipt_path: Path,
    posthoc_digest: str,
    posthoc_raw_sha256: str,
    *,
    repository_root: Path,
) -> dict[str, Any]:
    """Revalidate the fixed diagnostic and build one margin-audit receipt."""

    _require_frozen_input_anchors(
        artifact_commit_digest=artifact_commit_digest,
        authorization_digest=authorization_digest,
        authorization_revision=authorization_revision,
        summary_digest=summary_digest,
        posthoc_digest=posthoc_digest,
        posthoc_raw_sha256=posthoc_raw_sha256,
    )
    repository = posthoc._resolved_existing_path(
        repository_root, "repository root", directory=True
    )
    artifact = posthoc._resolved_existing_path(
        artifact_path, "artifact", directory=False
    )
    bundle = posthoc._resolved_existing_path(bundle_dir, "bundle", directory=True)
    authorization_file = posthoc._resolved_existing_path(
        authorization_path, "execution authorization", directory=False
    )
    summary_file = posthoc._resolved_existing_path(
        summary_path, "published diagnostic summary", directory=False
    )
    posthoc_file = posthoc._resolved_existing_path(
        posthoc_receipt_path, "published post-hoc receipt", directory=False
    )
    source = _source_attestation(repository)
    published_posthoc, published_posthoc_raw = _read_frozen_posthoc(
        posthoc_file, posthoc_digest, posthoc_raw_sha256
    )
    summary_raw = summary_file.read_bytes()
    authorization_raw = authorization_file.read_bytes()
    artifact_raw = artifact.read_bytes()

    try:
        fresh_posthoc = posthoc.build_receipt(
            artifact,
            bundle,
            authorization_file,
            authorization_digest,
            authorization_revision,
            summary_file,
            summary_digest,
            artifact_commit_digest,
            repository_root=repository,
        )
    except posthoc.PosthocMechanismAuditError as error:
        raise SelectionMarginAuditError(
            "post-hoc replay and reduction did not freshly close"
        ) from error
    for key in POSTHOC_FRESH_CROSSCHECK_KEYS:
        if fresh_posthoc.get(key) != published_posthoc.get(key):
            raise SelectionMarginAuditError(
                f"published post-hoc {key} does not freshly recompute"
            )
    if (
        fresh_posthoc.get("integrity_status") != "PASS"
        or fresh_posthoc.get("schema_version") != posthoc.SCHEMA_VERSION
    ):
        raise SelectionMarginAuditError("fresh post-hoc integrity metadata drifted")

    authorization, _ = posthoc._read_strict_json_object(
        authorization_file, "execution authorization"
    )
    if authorization.get("deterministic_digest") != authorization_digest:
        raise SelectionMarginAuditError("execution authorization digest drifted")
    try:
        verified = (
            posthoc.regular_file_publication.verify_countdown_thompson_diagnostic_v2(
                artifact,
                expected_parent_binding=authorization["output_parent_binding"],
                authorization_digest=authorization_digest,
            )
        )
    except (
        KeyError,
        posthoc.regular_file_publication.RegularFilePublicationV2Error,
    ) as error:
        raise SelectionMarginAuditError(
            "committed collective revalidation failed"
        ) from error
    if (
        verified.artifact_commit_digest != artifact_commit_digest
        or verified.run_manifest_digest != FROZEN_RUN_MANIFEST_DIGEST
        or verified.run_manifest_digest
        != fresh_posthoc["input_provenance"]["run_manifest_digest"]
        or len(verified.records) != EXPECTED_RECORD_COUNT
    ):
        raise SelectionMarginAuditError("committed collective provenance drifted")

    reductions = reduce_verified_records(verified.records, published_posthoc)
    second_source = _source_attestation(repository)
    if (
        second_source != source
        or artifact.read_bytes() != artifact_raw
        or summary_file.read_bytes() != summary_raw
        or authorization_file.read_bytes() != authorization_raw
        or posthoc_file.read_bytes() != published_posthoc_raw
    ):
        raise SelectionMarginAuditError(
            "audit source or frozen input changed during reduction"
        )

    core: dict[str, Any] = {
        "claim_boundary": CLAIM_BOUNDARY,
        "handoff_decision": HANDOFF_DECISION,
        "input_provenance": {
            "artifact_commit_digest": verified.artifact_commit_digest,
            "artifact_path": os.fspath(artifact),
            "artifact_raw_sha256": hashlib.sha256(artifact_raw).hexdigest(),
            "authorization_digest": authorization_digest,
            "authorization_path": os.fspath(authorization_file),
            "authorization_revision": authorization_revision,
            "bundle_path": os.fspath(bundle),
            "collective_manifest_digest": verified.collective_manifest_digest,
            "path_identity_semantics": (
                "filesystem_entry_spelling_absolute_paths/v1"
            ),
            "posthoc_receipt_deterministic_digest": posthoc_digest,
            "posthoc_receipt_path": os.fspath(posthoc_file),
            "posthoc_receipt_raw_sha256": posthoc_raw_sha256,
            "record_count": len(verified.records),
            "records_jsonl_byte_count": len(verified.records_jsonl_bytes),
            "records_jsonl_sha256": hashlib.sha256(
                verified.records_jsonl_bytes
            ).hexdigest(),
            "repository_path": os.fspath(repository),
            "run_manifest_digest": verified.run_manifest_digest,
            "summary_deterministic_digest": summary_digest,
            "summary_path": os.fspath(summary_file),
            "summary_raw_sha256": hashlib.sha256(summary_raw).hexdigest(),
        },
        "integrity_status": "PASS",
        "posthoc_revalidation": {
            "fresh_reduction_digest": sha256_json(fresh_posthoc["reductions"]),
            "fresh_supplemental_digest": sha256_json(
                fresh_posthoc["supplemental_validation"]
            ),
            "published_values_exactly_recomputed": True,
            "status": "PASS",
        },
        "reductions": reductions,
        "schema_version": SCHEMA_VERSION,
        "source_attestation": source,
    }
    return {**core, "deterministic_digest": sha256_json(core)}


def _self_test() -> dict[str, object]:
    boundary = _boundary_payload(
        [Fraction(1), Fraction(0)],
        [Fraction(0), Fraction(2)],
        expected_observed_action=1,
    )
    if (
        boundary["boundary_scale_exact"]
        != {"denominator": 2, "numerator": 1}
        or boundary["boundary_relation"] != "before_observed"
        or not boundary["observed_action_changed"]
    ):
        raise AssertionError("boundary self-test failed")
    if _five_number([4.0, 1.0, 3.0, 2.0]) != {
        "count": 4,
        "index_rule": "floor((n-1)*p)",
        "maximum": 4.0,
        "median": 2.0,
        "minimum": 1.0,
        "q1": 1.0,
        "q3": 3.0,
    }:
        raise AssertionError("five-number self-test failed")
    return {
        "claim_boundary": "synthetic helper checks only; no diagnostic opened",
        "status": "PASS",
    }


class _FailClosedParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise SelectionMarginAuditError(message)


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
    parser.add_argument("--posthoc-digest")
    parser.add_argument("--posthoc-raw-sha256")
    parser.add_argument("--posthoc-receipt", type=Path)
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
            arguments.posthoc_digest,
            arguments.posthoc_raw_sha256,
            arguments.posthoc_receipt,
            arguments.repository_root,
            arguments.summary,
            arguments.summary_digest,
        )
        if arguments.self_test:
            if any(value is not None for value in supplied):
                raise SelectionMarginAuditError(
                    "--self-test accepts no diagnostic paths or digests"
                )
            result: Mapping[str, Any] = _self_test()
        else:
            if any(value is None for value in supplied):
                raise SelectionMarginAuditError(
                    "audit mode requires every path and digest argument"
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
                arguments.posthoc_receipt,
                arguments.posthoc_digest,
                arguments.posthoc_raw_sha256,
                repository_root=arguments.repository_root,
            )
            posthoc._write_no_overwrite(arguments.output, receipt)
            result = {
                "claim_boundary": CLAIM_BOUNDARY,
                "output_path": os.fspath(arguments.output),
                "receipt_digest": receipt["deterministic_digest"],
                "status": "PASS",
            }
        print(canonical_json(result))
        return 0
    except (
        OSError,
        SelectionMarginAuditError,
        posthoc.PosthocMechanismAuditError,
    ) as error:
        print(
            canonical_json(
                {
                    "claim_boundary": (
                        "INVALID: no selection-margin receipt was authorized"
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
