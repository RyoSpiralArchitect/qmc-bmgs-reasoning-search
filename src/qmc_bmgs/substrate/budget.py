"""Atomic work accounting for the provider-neutral Track A benchmark.

The legacy Countdown experiments retain their frozen ``ComputeLedger`` schema.
This module defines the smaller, explicit accounting contract used by new
Track A search methods.  Every expensive operation must be charged before it
generates randomness, mutates a search graph, or performs a transition.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


TRACK_A_LEDGER_SCHEMA_VERSION = "qmc-bmgs-track-a-work-ledger/v1"
TRACK_A_WORK_AXES = (
    "proposal_state_evaluations",
    "proposal_action_scores",
    "legal_action_scores",
    "generated_perturbation_coordinates",
    "edge_selections",
    "transitions",
    "verifier_calls",
)


def _require_plain_nonnegative_int(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a non-negative plain integer")
    return value


def _require_plain_positive_int(value: object, label: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{label} must be a positive plain integer")
    return value


@dataclass(frozen=True)
class TrackAWorkBudget:
    """Hard integer limits for every Track A work axis."""

    proposal_state_evaluations: int
    proposal_action_scores: int
    legal_action_scores: int
    generated_perturbation_coordinates: int
    edge_selections: int
    transitions: int
    verifier_calls: int

    def __post_init__(self) -> None:
        for axis in TRACK_A_WORK_AXES:
            _require_plain_nonnegative_int(
                getattr(self, axis),
                f"TrackAWorkBudget.{axis}",
            )

    def to_dict(self) -> dict[str, int]:
        return {axis: getattr(self, axis) for axis in TRACK_A_WORK_AXES}


@dataclass(frozen=True)
class TrackAChargeReceipt:
    """Immutable-by-convention evidence for one accepted atomic charge."""

    charge_index: int
    increments: tuple[tuple[str, int], ...]
    usage_after: tuple[tuple[str, int], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "charge_index": self.charge_index,
            "increments": dict(self.increments),
            "usage_after": dict(self.usage_after),
        }


class TrackABudgetExceeded(RuntimeError):
    """Raised when an atomic charge would exceed one or more hard limits."""

    def __init__(
        self,
        attempted: dict[str, int],
        blocked_axes: tuple[str, ...],
    ) -> None:
        super().__init__(f"Track A work budget exhausted on: {', '.join(blocked_axes)}")
        self.attempted = dict(attempted)
        self.blocked_axes = blocked_axes


@dataclass
class TrackAWorkLedger:
    """Thread-safe Track A accounting with all-or-nothing multi-axis charges."""

    budget: TrackAWorkBudget
    _usage: dict[str, int] = field(init=False, repr=False)
    _charge_count: int = field(default=0, init=False, repr=False)
    _live_nodes: int = field(default=0, init=False, repr=False)
    _live_bytes: int = field(default=0, init=False, repr=False)
    _peak_live_nodes: int = field(default=0, init=False, repr=False)
    _peak_live_bytes: int = field(default=0, init=False, repr=False)
    _lock: threading.Lock = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.budget, TrackAWorkBudget):
            raise TypeError("budget must be a TrackAWorkBudget")
        self._usage = {axis: 0 for axis in TRACK_A_WORK_AXES}
        self._lock = threading.Lock()

    @staticmethod
    def _validated_increments(increments: dict[str, int]) -> dict[str, int]:
        if not increments:
            raise ValueError("charge requires at least one work axis")
        unknown = sorted(set(increments) - set(TRACK_A_WORK_AXES))
        if unknown:
            raise KeyError(f"unknown Track A work axes: {unknown}")
        validated = {axis: 0 for axis in TRACK_A_WORK_AXES}
        for axis, value in increments.items():
            validated[axis] = _require_plain_nonnegative_int(
                value,
                f"charge.{axis}",
            )
        if not any(validated.values()):
            raise ValueError("charge must contain positive work")
        return validated

    def preflight(self, **increments: int) -> tuple[str, ...]:
        """Return every axis that would block one charge, without mutation.

        The validation and axis order are exactly the same as :meth:`charge`.
        A caller may use this to derive a deterministic stop reason, but the
        subsequent charge remains authoritative.  Track A runs are
        single-threaded, so no cross-thread reservation semantics are implied.
        """

        validated = self._validated_increments(increments)
        limits = self.budget.to_dict()
        with self._lock:
            return tuple(
                axis
                for axis in TRACK_A_WORK_AXES
                if self._usage[axis] + validated[axis] > limits[axis]
            )

    @staticmethod
    def search_step_increments(
        action_count: int,
        *,
        proposal_cache_miss: bool,
        generate_perturbations: bool,
    ) -> dict[str, int]:
        """Build the one-receipt work vector for a complete search step."""

        count = _require_plain_positive_int(action_count, "action_count")
        if type(proposal_cache_miss) is not bool:
            raise TypeError("proposal_cache_miss must be bool")
        if type(generate_perturbations) is not bool:
            raise TypeError("generate_perturbations must be bool")
        return {
            "proposal_state_evaluations": int(proposal_cache_miss),
            "proposal_action_scores": count if proposal_cache_miss else 0,
            "legal_action_scores": count,
            "generated_perturbation_coordinates": (
                count if generate_perturbations else 0
            ),
            "edge_selections": 1,
            "transitions": 1,
            "verifier_calls": 0,
        }

    def charge(self, **increments: int) -> TrackAChargeReceipt:
        """Atomically charge work or raise without changing any ledger field."""

        validated = self._validated_increments(increments)
        limits = self.budget.to_dict()
        with self._lock:
            blocked_axes = tuple(
                axis
                for axis in TRACK_A_WORK_AXES
                if self._usage[axis] + validated[axis] > limits[axis]
            )
            if blocked_axes:
                raise TrackABudgetExceeded(validated, blocked_axes)

            for axis in TRACK_A_WORK_AXES:
                self._usage[axis] += validated[axis]
            self._charge_count += 1
            return TrackAChargeReceipt(
                charge_index=self._charge_count - 1,
                increments=tuple(
                    (axis, validated[axis]) for axis in TRACK_A_WORK_AXES
                ),
                usage_after=tuple(
                    (axis, self._usage[axis]) for axis in TRACK_A_WORK_AXES
                ),
            )

    def charge_search_step(
        self,
        action_count: int,
        *,
        proposal_cache_miss: bool,
        generate_perturbations: bool,
    ) -> TrackAChargeReceipt:
        """Atomically authorize one scored edge selection and transition.

        A proposal miss, every legal-action score, the optional one-coordinate
        perturbation per action, the selected edge, and its transition share a
        single receipt.  Rejection therefore cannot leave a half-authorized
        Thompson selection.
        """

        return self.charge(
            **self.search_step_increments(
                action_count,
                proposal_cache_miss=proposal_cache_miss,
                generate_perturbations=generate_perturbations,
            )
        )

    def charge_selection(self, scored_action_count: int) -> TrackAChargeReceipt:
        """Charge scoring every legal action at one selection point."""

        count = _require_plain_positive_int(
            scored_action_count,
            "scored_action_count",
        )
        return self.charge(legal_action_scores=count)

    def charge_perturbation_coordinates(
        self,
        coordinate_count: int,
    ) -> TrackAChargeReceipt:
        """Charge exactly one generated perturbation coordinate per action."""

        count = _require_plain_positive_int(
            coordinate_count,
            "coordinate_count",
        )
        return self.charge(generated_perturbation_coordinates=count)

    def observe_live_storage(self, *, live_nodes: int, live_bytes: int) -> None:
        """Record current and peak live storage without treating it as budget."""

        nodes = _require_plain_nonnegative_int(live_nodes, "live_nodes")
        bytes_ = _require_plain_nonnegative_int(live_bytes, "live_bytes")
        with self._lock:
            self._live_nodes = nodes
            self._live_bytes = bytes_
            self._peak_live_nodes = max(self._peak_live_nodes, nodes)
            self._peak_live_bytes = max(self._peak_live_bytes, bytes_)

    def snapshot(self) -> dict[str, Any]:
        """Return the complete deterministic accounting state."""

        with self._lock:
            limits = self.budget.to_dict()
            usage = dict(self._usage)
            remaining = {
                axis: limits[axis] - usage[axis] for axis in TRACK_A_WORK_AXES
            }
            overshoot_by_axis = {
                axis: max(0, usage[axis] - limits[axis])
                for axis in TRACK_A_WORK_AXES
            }
            return {
                "charge_count": self._charge_count,
                "exhausted_axes": [
                    axis for axis in TRACK_A_WORK_AXES if remaining[axis] == 0
                ],
                "limits": limits,
                "live_storage": {
                    "bytes": self._live_bytes,
                    "nodes": self._live_nodes,
                },
                "overshoot": sum(overshoot_by_axis.values()),
                "overshoot_by_axis": overshoot_by_axis,
                "peak_live_storage": {
                    "bytes": self._peak_live_bytes,
                    "nodes": self._peak_live_nodes,
                },
                "remaining": remaining,
                "schema_version": TRACK_A_LEDGER_SCHEMA_VERSION,
                "usage": usage,
            }
