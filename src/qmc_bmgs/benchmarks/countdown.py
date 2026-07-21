#!/usr/bin/env python3
"""Exact, download-free Countdown-D6 task and calibration substrate.

This module defines a small planning task for later matched search experiments.
It intentionally contains no search policy and makes no performance claim.  Its
job is to freeze four pieces of shared infrastructure:

* a task-adapter boundary with immutable action chunks,
* a task-namespaced cache identity for canonical DAG states,
* an exact multi-axis compute ledger, and
* an exhaustive calibrator that measures the canonical state DAG.

The rules are the positive-integer Countdown rules used in this repository:
all six source numbers must be consumed exactly once; intermediate values must
remain positive integers; subtraction must be positive; division must be exact.

Examples
--------

    python -m qmc_bmgs.benchmarks.countdown --self-test
    python -m qmc_bmgs.benchmarks.countdown \
        --inputs 1,2,3,4,5,6 --target 21
    python -m qmc_bmgs.benchmarks.countdown \
        --generate-candidates 8 --seed 17 --output countdown_pool.json
    python -m qmc_bmgs.benchmarks.countdown \
        --generate-solvable-suite 8 --seed 17 --output countdown_suite.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import threading
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Hashable, Protocol, Sequence, TypeVar, runtime_checkable


SCHEMA_VERSION = "qmc-bmgs-countdown-calibration/v1"
RULESET_ID = "countdown-d6-positive-int-exact-division/v1"
GENERATOR_ID = "sha256-counter-mod/v1"
INPUT_COUNT = 6
ACTION_COUNT = INPUT_COUNT - 1
OPERATORS = ("+", "-", "*", "/")
OPERATOR_ORDER = {operator: index for index, operator in enumerate(OPERATORS)}
OPERATOR_CLUSTERS = {
    "+": "operator:addition",
    "-": "operator:subtraction",
    "*": "operator:multiplication",
    "/": "operator:division",
}
COMPUTE_AXES = (
    "proposal_batch_calls",
    "proposal_state_items",
    "proposal_input_values",
    "proposal_action_scores",
    "selection_action_scores",
    "edge_selections",
    "transitions",
    "verifier_calls",
)

CountdownState = tuple[int, ...]
StateT = TypeVar("StateT", bound=Hashable)
ActionT = TypeVar("ActionT", bound=Hashable)


def _require_plain_int(value: object, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        qualifier = "non-negative" if minimum == 0 else f">= {minimum}"
        raise ValueError(f"{label} must be a plain integer {qualifier}")
    return value


def _canonical_json(payload: Any) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def _pretty_json(payload: Any) -> str:
    return json.dumps(
        payload,
        indent=2,
        sort_keys=True,
        ensure_ascii=True,
        allow_nan=False,
    )


def _sha256_json(payload: Any) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


@runtime_checkable
class TaskAdapter(Protocol[StateT, ActionT]):
    """Minimal planning-task boundary expected by later search harnesses."""

    @property
    def task_id(self) -> str: ...

    @property
    def initial_state(self) -> StateT: ...

    @property
    def max_steps(self) -> int: ...

    def legal_actions(self, state: StateT) -> tuple[ActionT, ...]: ...

    def transition(self, state: StateT, action: ActionT) -> StateT: ...

    def action_cluster(self, action: ActionT) -> str: ...

    def state_key(self, state: StateT) -> Hashable: ...

    def serialize_state(self, state: StateT) -> Any: ...

    def serialize_action(self, action: ActionT) -> Any: ...

    def verify(self, actions: Sequence[ActionT]) -> Any: ...


class CountdownActionError(ValueError):
    """A stable, machine-readable illegal-action failure."""

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class CountdownAction:
    """A value-pair operation; duplicate source copies are resolved on replay."""

    left: int
    right: int
    operator: str

    def __post_init__(self) -> None:
        if type(self.left) is not int or self.left <= 0:
            raise CountdownActionError(
                "non_positive_operand", "left operand must be a positive integer"
            )
        if type(self.right) is not int or self.right <= 0:
            raise CountdownActionError(
                "non_positive_operand", "right operand must be a positive integer"
            )
        if self.operator not in OPERATORS:
            raise CountdownActionError(
                "unknown_operator", f"unsupported operator: {self.operator!r}"
            )
        if self.operator in {"+", "*"} and self.left > self.right:
            original_left = self.left
            object.__setattr__(self, "left", self.right)
            object.__setattr__(self, "right", original_left)

    def evaluate(self) -> int:
        if self.operator == "+":
            return self.left + self.right
        if self.operator == "*":
            return self.left * self.right
        if self.operator == "-":
            result = self.left - self.right
            if result <= 0:
                raise CountdownActionError(
                    "non_positive_subtraction",
                    "subtraction must produce a positive integer",
                )
            return result
        if self.left % self.right != 0:
            raise CountdownActionError(
                "non_integral_division", "division must have zero remainder"
            )
        result = self.left // self.right
        if result <= 0:
            raise CountdownActionError(
                "non_positive_division", "division must produce a positive integer"
            )
        return result

    def sort_key(self) -> tuple[int, int, int]:
        return (OPERATOR_ORDER[self.operator], self.left, self.right)

    def to_dict(self) -> dict[str, Any]:
        return {
            "left": self.left,
            "operator": self.operator,
            "right": self.right,
        }


@dataclass(frozen=True)
class CountdownStateKey:
    """Cache key isolated by ruleset and full task identity."""

    ruleset_id: str
    task_fingerprint: str
    values: CountdownState

    def to_dict(self) -> dict[str, Any]:
        return {
            "ruleset_id": self.ruleset_id,
            "task_fingerprint": self.task_fingerprint,
            "values": list(self.values),
        }


@dataclass(frozen=True)
class ExpressionTerm:
    value: int
    expression: str
    source_indices: tuple[int, ...]

    def sort_key(self) -> tuple[int, tuple[int, ...], str]:
        return (self.value, self.source_indices, self.expression)

    def to_dict(self) -> dict[str, Any]:
        return {
            "expression": self.expression,
            "source_indices": list(self.source_indices),
            "value": self.value,
        }


@dataclass(frozen=True)
class ReplayStep:
    index: int
    state_before: CountdownState
    action: CountdownAction
    state_after: CountdownState
    left_source_indices: tuple[int, ...]
    right_source_indices: tuple[int, ...]
    combined_source_indices: tuple[int, ...]
    result: int
    expression: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.to_dict(),
            "combined_source_indices": list(self.combined_source_indices),
            "expression": self.expression,
            "index": self.index,
            "left_source_indices": list(self.left_source_indices),
            "result": self.result,
            "right_source_indices": list(self.right_source_indices),
            "state_after": list(self.state_after),
            "state_before": list(self.state_before),
        }


@dataclass(frozen=True)
class CountdownVerification:
    success: bool
    reason: str
    failure_step: int | None
    failure_detail: str | None
    action_count_received: int
    action_count_consumed: int
    expected_action_count: int
    target: int
    final_state: CountdownState
    final_value: int | None
    expression: str | None
    final_expression_source_indices: tuple[int, ...]
    all_source_indices: tuple[int, ...]
    source_use_exact: bool
    source_bindings: tuple[tuple[int, int], ...]
    steps: tuple[ReplayStep, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_count_consumed": self.action_count_consumed,
            "action_count_received": self.action_count_received,
            "all_source_indices": list(self.all_source_indices),
            "expected_action_count": self.expected_action_count,
            "expression": self.expression,
            "failure_detail": self.failure_detail,
            "failure_step": self.failure_step,
            "final_expression_source_indices": list(
                self.final_expression_source_indices
            ),
            "final_state": list(self.final_state),
            "final_value": self.final_value,
            "reason": self.reason,
            "source_bindings": [
                {"source_index": index, "value": value}
                for index, value in self.source_bindings
            ],
            "source_use_exact": self.source_use_exact,
            "steps": [step.to_dict() for step in self.steps],
            "success": self.success,
            "target": self.target,
        }


@dataclass(frozen=True)
class CountdownTask:
    """A six-source, five-action exact Countdown task."""

    inputs: tuple[int, ...]
    target: int

    def __post_init__(self) -> None:
        values = tuple(self.inputs)
        if len(values) != INPUT_COUNT:
            raise ValueError(f"Countdown-D6 requires exactly {INPUT_COUNT} inputs")
        if any(type(value) is not int or value <= 0 for value in values):
            raise ValueError("all Countdown inputs must be positive plain integers")
        if type(self.target) is not int or self.target <= 0:
            raise ValueError("Countdown target must be a positive plain integer")
        object.__setattr__(self, "inputs", tuple(sorted(values)))

    @property
    def max_steps(self) -> int:
        return ACTION_COUNT

    @property
    def initial_state(self) -> CountdownState:
        return self.inputs

    @property
    def task_fingerprint(self) -> str:
        return _sha256_json(
            {
                "inputs": list(self.inputs),
                "ruleset_id": RULESET_ID,
                "target": self.target,
            }
        )

    @property
    def source_multiset_fingerprint(self) -> str:
        """Identity used to keep canonical source sets out of both splits."""

        return _sha256_json(
            {
                "inputs": list(self.inputs),
                "ruleset_id": RULESET_ID,
            }
        )

    @property
    def task_id(self) -> str:
        return f"countdown_d6_{self.task_fingerprint[:16]}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "inputs": list(self.inputs),
            "max_steps": self.max_steps,
            "ruleset_id": RULESET_ID,
            "source_multiset_fingerprint": self.source_multiset_fingerprint,
            "target": self.target,
            "task_fingerprint": self.task_fingerprint,
            "task_id": self.task_id,
        }

    @staticmethod
    def canonical_state(values: Sequence[int]) -> CountdownState:
        state = tuple(values)
        if not state:
            raise ValueError("Countdown state cannot be empty")
        if any(type(value) is not int or value <= 0 for value in state):
            raise ValueError("Countdown states contain only positive plain integers")
        return tuple(sorted(state))

    def serialize_state(self, state: CountdownState) -> list[int]:
        return list(self.canonical_state(state))

    @staticmethod
    def serialize_action(action: CountdownAction) -> dict[str, Any]:
        if not isinstance(action, CountdownAction):
            raise TypeError("expected CountdownAction")
        return action.to_dict()

    def state_key(self, state: CountdownState) -> CountdownStateKey:
        return CountdownStateKey(
            ruleset_id=RULESET_ID,
            task_fingerprint=self.task_fingerprint,
            values=self.canonical_state(state),
        )

    @staticmethod
    def action_cluster(action: CountdownAction) -> str:
        if not isinstance(action, CountdownAction):
            raise TypeError("expected CountdownAction")
        return OPERATOR_CLUSTERS[action.operator]

    def legal_actions(self, state: CountdownState) -> tuple[CountdownAction, ...]:
        canonical = self.canonical_state(state)
        if len(canonical) < 2:
            return ()

        # Pair by positions first, then deduplicate value-copy symmetries.  This
        # retains (x, x) only when two copies really exist in the state.
        value_pairs = {
            (canonical[left], canonical[right])
            for left in range(len(canonical))
            for right in range(left + 1, len(canonical))
        }
        actions: set[CountdownAction] = set()
        for low, high in sorted(value_pairs):
            actions.add(CountdownAction(low, high, "+"))
            actions.add(CountdownAction(low, high, "*"))
            if high > low:
                actions.add(CountdownAction(high, low, "-"))
            if high % low == 0:
                actions.add(CountdownAction(high, low, "/"))
        return tuple(sorted(actions, key=CountdownAction.sort_key))

    def transition(
        self, state: CountdownState, action: CountdownAction
    ) -> CountdownState:
        canonical = self.canonical_state(state)
        if len(canonical) < 2:
            raise CountdownActionError(
                "terminal_state", "a one-value terminal state has no outgoing action"
            )
        if not isinstance(action, CountdownAction):
            raise CountdownActionError(
                "invalid_action_type", "transition requires CountdownAction"
            )

        required = Counter((action.left, action.right))
        available = Counter(canonical)
        missing = {
            value: count - available[value]
            for value, count in required.items()
            if available[value] < count
        }
        if missing:
            reason = (
                "operand_multiplicity"
                if action.left == action.right
                else "operand_unavailable"
            )
            raise CountdownActionError(
                reason,
                f"state {canonical!r} does not contain required operands {required!r}",
            )

        result = action.evaluate()
        remainder = list(canonical)
        remainder.remove(action.left)
        remainder.remove(action.right)
        remainder.append(result)
        return self.canonical_state(remainder)

    @staticmethod
    def _term_indices(
        terms: Sequence[ExpressionTerm], action: CountdownAction
    ) -> tuple[int, int]:
        left_candidates = [
            index for index, term in enumerate(terms) if term.value == action.left
        ]
        if action.left == action.right:
            if len(left_candidates) < 2:
                raise CountdownActionError(
                    "operand_multiplicity",
                    "replay needs two distinct equal-valued terms",
                )
            return left_candidates[0], left_candidates[1]
        right_candidates = [
            index for index, term in enumerate(terms) if term.value == action.right
        ]
        if not left_candidates or not right_candidates:
            raise CountdownActionError(
                "operand_unavailable", "replay cannot resolve both operand terms"
            )
        return left_candidates[0], right_candidates[0]

    def _verification_result(
        self,
        *,
        success: bool,
        reason: str,
        failure_step: int | None,
        failure_detail: str | None,
        received: int,
        consumed: int,
        terms: Sequence[ExpressionTerm],
        steps: Sequence[ReplayStep],
    ) -> CountdownVerification:
        ordered_terms = tuple(sorted(terms, key=ExpressionTerm.sort_key))
        final_term = ordered_terms[0] if len(ordered_terms) == 1 else None
        all_sources = tuple(range(INPUT_COUNT))
        final_sources = final_term.source_indices if final_term is not None else ()
        source_use_exact = final_sources == all_sources
        return CountdownVerification(
            success=success,
            reason=reason,
            failure_step=failure_step,
            failure_detail=failure_detail,
            action_count_received=received,
            action_count_consumed=consumed,
            expected_action_count=ACTION_COUNT,
            target=self.target,
            final_state=tuple(sorted(term.value for term in ordered_terms)),
            final_value=final_term.value if final_term is not None else None,
            expression=final_term.expression if final_term is not None else None,
            final_expression_source_indices=final_sources,
            all_source_indices=all_sources,
            source_use_exact=source_use_exact,
            source_bindings=tuple(enumerate(self.inputs)),
            steps=tuple(steps),
        )

    def verify(self, actions: Sequence[CountdownAction]) -> CountdownVerification:
        """Replay an action trace from six independently labelled sources."""

        trace = tuple(actions)
        terms = [
            ExpressionTerm(value, f"x{index}", (index,))
            for index, value in enumerate(self.inputs)
        ]
        terms.sort(key=ExpressionTerm.sort_key)
        steps: list[ReplayStep] = []

        if len(trace) > ACTION_COUNT:
            return self._verification_result(
                success=False,
                reason="action_count_mismatch",
                failure_step=ACTION_COUNT + 1,
                failure_detail=f"received more than {ACTION_COUNT} actions",
                received=len(trace),
                consumed=0,
                terms=terms,
                steps=steps,
            )

        for index, action in enumerate(trace, start=1):
            if not isinstance(action, CountdownAction):
                return self._verification_result(
                    success=False,
                    reason="invalid_action",
                    failure_step=index,
                    failure_detail="trace contains a non-CountdownAction value",
                    received=len(trace),
                    consumed=len(steps),
                    terms=terms,
                    steps=steps,
                )
            state_before = tuple(sorted(term.value for term in terms))
            try:
                expected_state = self.transition(state_before, action)
                left_index, right_index = self._term_indices(terms, action)
                result = action.evaluate()
            except CountdownActionError as error:
                return self._verification_result(
                    success=False,
                    reason="invalid_action",
                    failure_step=index,
                    failure_detail=f"{error.reason}: {error.detail}",
                    received=len(trace),
                    consumed=len(steps),
                    terms=terms,
                    steps=steps,
                )

            left_term = terms[left_index]
            right_term = terms[right_index]
            if set(left_term.source_indices) & set(right_term.source_indices):
                return self._verification_result(
                    success=False,
                    reason="source_reuse",
                    failure_step=index,
                    failure_detail="operand provenance overlaps",
                    received=len(trace),
                    consumed=len(steps),
                    terms=terms,
                    steps=steps,
                )
            combined_sources = tuple(
                sorted(left_term.source_indices + right_term.source_indices)
            )
            expression = (
                f"({left_term.expression}{action.operator}{right_term.expression})"
            )
            combined = ExpressionTerm(result, expression, combined_sources)
            for remove_index in sorted((left_index, right_index), reverse=True):
                del terms[remove_index]
            terms.append(combined)
            terms.sort(key=ExpressionTerm.sort_key)
            state_after = tuple(sorted(term.value for term in terms))
            if state_after != expected_state:
                raise AssertionError(
                    "numeric transition and provenance replay diverged"
                )
            steps.append(
                ReplayStep(
                    index=index,
                    state_before=state_before,
                    action=action,
                    state_after=state_after,
                    left_source_indices=left_term.source_indices,
                    right_source_indices=right_term.source_indices,
                    combined_source_indices=combined_sources,
                    result=result,
                    expression=expression,
                )
            )

        if len(terms) != 1:
            return self._verification_result(
                success=False,
                reason="incomplete_reduction",
                failure_step=None,
                failure_detail=f"{len(terms)} values remain after replay",
                received=len(trace),
                consumed=len(steps),
                terms=terms,
                steps=steps,
            )

        final_term = terms[0]
        all_sources = tuple(range(INPUT_COUNT))
        if final_term.source_indices != all_sources:
            return self._verification_result(
                success=False,
                reason="source_use_mismatch",
                failure_step=None,
                failure_detail="final expression does not use every source exactly once",
                received=len(trace),
                consumed=len(steps),
                terms=terms,
                steps=steps,
            )
        if len(trace) != ACTION_COUNT:
            return self._verification_result(
                success=False,
                reason="action_count_mismatch",
                failure_step=None,
                failure_detail=f"exact solution requires {ACTION_COUNT} actions",
                received=len(trace),
                consumed=len(steps),
                terms=terms,
                steps=steps,
            )
        if final_term.value != self.target:
            return self._verification_result(
                success=False,
                reason="target_mismatch",
                failure_step=None,
                failure_detail=(
                    f"final value {final_term.value} does not equal target {self.target}"
                ),
                received=len(trace),
                consumed=len(steps),
                terms=terms,
                steps=steps,
            )
        return self._verification_result(
            success=True,
            reason="exact_solution",
            failure_step=None,
            failure_detail=None,
            received=len(trace),
            consumed=len(steps),
            terms=terms,
            steps=steps,
        )


@dataclass(frozen=True)
class ComputeBudget:
    """Hard limits for every expensive in-search operation.

    Equal limits do not imply equal compute.  A comparison must match or report
    the actual usage snapshot, including whether each method ran to its cap.
    ``proposal_input_values`` includes every current-state value plus the target
    feature.  The two action-score axes distinguish proposal construction from
    selection-time indexing or rescoring.
    """

    proposal_batch_calls: int
    proposal_state_items: int
    proposal_input_values: int
    proposal_action_scores: int
    selection_action_scores: int
    edge_selections: int
    transitions: int
    verifier_calls: int

    def __post_init__(self) -> None:
        for axis in COMPUTE_AXES:
            _require_plain_int(getattr(self, axis), f"ComputeBudget.{axis}")

    def to_dict(self) -> dict[str, int]:
        return {axis: getattr(self, axis) for axis in COMPUTE_AXES}


class BudgetExceeded(RuntimeError):
    def __init__(
        self, attempted: dict[str, int], blocked_axes: tuple[str, ...]
    ) -> None:
        super().__init__(f"compute budget exhausted on: {', '.join(blocked_axes)}")
        self.attempted = dict(attempted)
        self.blocked_axes = blocked_axes


@dataclass
class ComputeLedger:
    """Thread-safe transactional accounting with no partial budget charge."""

    budget: ComputeBudget
    _usage: dict[str, int] = field(init=False, repr=False)
    _cache_hits: int = field(default=0, init=False, repr=False)
    _cache_misses: int = field(default=0, init=False, repr=False)
    _evaluation_only_calls: int = field(default=0, init=False, repr=False)
    _unique_state_keys: set[Hashable] = field(init=False, repr=False)
    _lock: threading.Lock = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._usage = {axis: 0 for axis in COMPUTE_AXES}
        self._unique_state_keys = set()
        self._lock = threading.Lock()

    @staticmethod
    def _validated_increments(increments: dict[str, int]) -> dict[str, int]:
        unknown = sorted(set(increments) - set(COMPUTE_AXES))
        if unknown:
            raise KeyError(f"unknown compute axes: {unknown}")
        validated = {axis: 0 for axis in COMPUTE_AXES}
        for axis, value in increments.items():
            validated[axis] = _require_plain_int(value, f"charge.{axis}")
        return validated

    def _attempt(self, increments: dict[str, int]) -> tuple[bool, tuple[str, ...]]:
        with self._lock:
            blocked = tuple(
                axis
                for axis in COMPUTE_AXES
                if self._usage[axis] + increments[axis] > getattr(self.budget, axis)
            )
            if blocked:
                # Rejection is side-effect free: no usage, cache, state, or
                # diagnostic field changes.  Callers must charge before RNG,
                # cache, proposal, graph, or value updates.
                return False, blocked
            # Every limit has been checked before any usage counter is changed.
            for axis in COMPUTE_AXES:
                self._usage[axis] += increments[axis]
            return True, ()

    def charge(self, **increments: int) -> None:
        validated = self._validated_increments(increments)
        accepted, blocked = self._attempt(validated)
        if not accepted:
            raise BudgetExceeded(validated, blocked)

    def try_charge(self, **increments: int) -> bool:
        validated = self._validated_increments(increments)
        accepted, _ = self._attempt(validated)
        return accepted

    def can_charge(self, **increments: int) -> bool:
        validated = self._validated_increments(increments)
        with self._lock:
            return all(
                self._usage[axis] + validated[axis] <= getattr(self.budget, axis)
                for axis in COMPUTE_AXES
            )

    def record_cache_lookup(self, state_key: Hashable, *, hit: bool) -> None:
        if type(hit) is not bool:
            raise TypeError("cache hit flag must be bool")
        try:
            hash(state_key)
        except TypeError as error:
            raise TypeError("state_key must be hashable") from error
        with self._lock:
            self._unique_state_keys.add(state_key)
            if hit:
                self._cache_hits += 1
            else:
                self._cache_misses += 1

    def record_state(self, state_key: Hashable) -> None:
        try:
            hash(state_key)
        except TypeError as error:
            raise TypeError("state_key must be hashable") from error
        with self._lock:
            self._unique_state_keys.add(state_key)

    def record_evaluation_only_call(self, *, cache_only: bool) -> None:
        """Record an out-of-search readout that performs no hidden search work."""

        if type(cache_only) is not bool:
            raise TypeError("cache_only flag must be bool")
        if not cache_only:
            raise ValueError(
                "evaluation-only readout may use existing cache only; "
                "proposal and transition work must be charged in search"
            )
        with self._lock:
            self._evaluation_only_calls += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            limits = self.budget.to_dict()
            usage = dict(self._usage)
            remaining = {axis: limits[axis] - usage[axis] for axis in COMPUTE_AXES}
            overshoot_by_axis = {
                axis: max(0, usage[axis] - limits[axis]) for axis in COMPUTE_AXES
            }
            return {
                "cache_hits": self._cache_hits,
                "cache_lookups": self._cache_hits + self._cache_misses,
                "cache_misses": self._cache_misses,
                "evaluation_only_calls": self._evaluation_only_calls,
                "exhausted_axes": [
                    axis for axis in COMPUTE_AXES if remaining[axis] == 0
                ],
                "limits": limits,
                "overshoot": sum(overshoot_by_axis.values()),
                "overshoot_by_axis": overshoot_by_axis,
                "remaining": remaining,
                "unique_states": len(self._unique_state_keys),
                "usage": usage,
            }


@dataclass(frozen=True)
class DagEdge:
    parent: CountdownState
    action: CountdownAction
    child: CountdownState

    def sort_key(self) -> tuple[Any, ...]:
        return (
            -len(self.parent),
            self.parent,
            self.action.sort_key(),
            self.child,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.to_dict(),
            "child": list(self.child),
            "parent": list(self.parent),
        }


@dataclass(frozen=True)
class SolutionWitness:
    """A complete retained trace, never reconstructed from merged parents."""

    actions: tuple[CountdownAction, ...]
    states: tuple[CountdownState, ...]
    verification: CountdownVerification

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "actions": [action.to_dict() for action in self.actions],
            "states": [list(state) for state in self.states],
            "verification": self.verification.to_dict(),
        }
        return {**payload, "witness_digest": _sha256_json(payload)}


@dataclass(frozen=True)
class CountdownCalibration:
    """Oracle calibration output; never pass this object into a search policy."""

    calibration_profile: dict[str, Any]
    solution_witness: SolutionWitness | None

    def to_record(self, *, include_witness: bool = False) -> dict[str, Any]:
        if type(include_witness) is not bool:
            raise TypeError("include_witness must be bool")
        witness_record = (
            self.solution_witness.to_dict()
            if self.solution_witness is not None
            else None
        )
        diagnostics = {
            "solution_witness_digest": (
                witness_record["witness_digest"] if witness_record is not None else None
            )
        }
        if include_witness:
            diagnostics["solution_witness"] = witness_record
        payload = {
            "calibration_profile": self.calibration_profile,
            "diagnostics": diagnostics,
            "record_type": "task_calibration",
            "schema_version": SCHEMA_VERSION,
        }
        return {**payload, "deterministic_digest": _sha256_json(payload)}


def _state_sort_key(state: CountdownState) -> tuple[Any, ...]:
    return (-len(state), state)


def calibrate_task(task: CountdownTask) -> CountdownCalibration:
    """Enumerate the complete canonical DAG and count every action path exactly."""

    states_by_terms: dict[int, set[CountdownState]] = {
        size: set() for size in range(1, INPUT_COUNT + 1)
    }
    states_by_terms[INPUT_COUNT].add(task.initial_state)
    edges_by_parent: dict[CountdownState, tuple[DagEdge, ...]] = {}
    all_edges: list[DagEdge] = []
    distinct_parents: dict[CountdownState, set[CountdownState]] = defaultdict(set)
    incoming_edges: Counter[CountdownState] = Counter()

    # Full root-to-state traces are retained at discovery time.  A merged DAG
    # node never receives a reconstructive parent pointer.
    retained_trace: dict[CountdownState, tuple[CountdownAction, ...]] = {
        task.initial_state: ()
    }

    for term_count in range(INPUT_COUNT, 1, -1):
        for state in sorted(states_by_terms[term_count]):
            state_edges: list[DagEdge] = []
            for action in task.legal_actions(state):
                child = task.transition(state, action)
                if len(child) != term_count - 1:
                    raise AssertionError("Countdown transitions must reduce term count")
                edge = DagEdge(state, action, child)
                state_edges.append(edge)
                all_edges.append(edge)
                distinct_parents[child].add(state)
                incoming_edges[child] += 1
                if child not in retained_trace:
                    retained_trace[child] = retained_trace[state] + (action,)
                states_by_terms[term_count - 1].add(child)
            edges_by_parent[state] = tuple(state_edges)

    path_counts: dict[CountdownState, int] = defaultdict(int)
    path_counts[task.initial_state] = 1
    for term_count in range(INPUT_COUNT, 1, -1):
        for state in sorted(states_by_terms[term_count]):
            parent_paths = path_counts[state]
            for edge in edges_by_parent[state]:
                path_counts[edge.child] += parent_paths

    ordered_states = sorted(
        (state for group in states_by_terms.values() for state in group),
        key=_state_sort_key,
    )
    ordered_edges = sorted(all_edges, key=DagEdge.sort_key)
    topology_payload = {
        "edges": [edge.to_dict() for edge in ordered_edges],
        "inputs": list(task.inputs),
        "ruleset_id": RULESET_ID,
        "states": [list(state) for state in ordered_states],
    }
    state_space_digest = _sha256_json(topology_payload)

    parent_counts = {state: len(parents) for state, parents in distinct_parents.items()}
    transposition_states = [
        state for state, count in parent_counts.items() if count > 1
    ]
    parallel_edge_excess = sum(
        incoming_edges[state] - parent_counts.get(state, 0) for state in incoming_edges
    )
    operator_edge_counts = Counter(edge.action.operator for edge in ordered_edges)
    terminal_states = states_by_terms[1]
    target_state = (task.target,)
    solution_path_count = path_counts.get(target_state, 0)

    solution_reachable_from: dict[CountdownState, bool] = {
        state: state == target_state for state in terminal_states
    }
    for term_count in range(2, INPUT_COUNT + 1):
        for state in sorted(states_by_terms[term_count]):
            solution_reachable_from[state] = any(
                solution_reachable_from[edge.child] for edge in edges_by_parent[state]
            )
    root_edges = edges_by_parent[task.initial_state]
    solution_root_actions = tuple(
        edge.action for edge in root_edges if solution_reachable_from[edge.child]
    )
    root_action_payload = [action.to_dict() for action in solution_root_actions]
    total_action_paths = sum(path_counts[state] for state in terminal_states)
    nonterminal_state_count = sum(
        len(states_by_terms[size]) for size in range(2, INPUT_COUNT + 1)
    )

    metrics: dict[str, Any] = {
        "action_path_count": total_action_paths,
        "branching_factor": {
            "denominator_nonterminal_states": nonterminal_state_count,
            "numerator_legal_edges": len(ordered_edges),
        },
        "edges_by_parent_term_count": {
            str(size): sum(
                len(edges_by_parent[state]) for state in states_by_terms[size]
            )
            for size in range(2, INPUT_COUNT + 1)
        },
        "legal_edge_count": len(ordered_edges),
        "max_distinct_parent_states": max(parent_counts.values(), default=0),
        "max_incoming_edges": max(incoming_edges.values(), default=0),
        "nonterminal_state_count": nonterminal_state_count,
        "operator_edge_counts": {
            operator: operator_edge_counts[operator] for operator in OPERATORS
        },
        "parallel_edge_excess": parallel_edge_excess,
        "reachable_state_count": len(ordered_states),
        "root_action_count": len(root_edges),
        "solution_bearing_root_action_count": len(solution_root_actions),
        "solution_bearing_root_action_digest": _sha256_json(root_action_payload),
        "solution_bearing_root_action_fraction": {
            "denominator_root_actions": len(root_edges),
            "numerator_solution_bearing_actions": len(solution_root_actions),
        },
        "solution_path_density": {
            "denominator_action_paths": total_action_paths,
            "numerator_solution_paths": solution_path_count,
        },
        "solution_path_count": solution_path_count,
        "solution_terminal_reachable": solution_path_count > 0,
        "states_by_term_count": {
            str(size): len(states_by_terms[size]) for size in range(1, INPUT_COUNT + 1)
        },
        "terminal_state_count": len(terminal_states),
        "transposition_parent_excess": sum(
            parent_counts[state] - 1 for state in transposition_states
        ),
        "transposition_state_count": len(transposition_states),
        "tree_unrolled_state_visit_count": sum(path_counts.values()),
    }
    profile_core = {
        "metrics": metrics,
        "state_space_digest": state_space_digest,
        "task": task.to_dict(),
    }
    calibration_profile = {
        **profile_core,
        "profile_digest": _sha256_json(profile_core),
    }

    witness: SolutionWitness | None = None
    if solution_path_count > 0:
        actions = retained_trace[target_state]
        states = [task.initial_state]
        for action in actions:
            states.append(task.transition(states[-1], action))
        verification = task.verify(actions)
        if not verification.success:
            raise AssertionError("retained solution trace failed independent replay")
        if states[-1] != target_state:
            raise AssertionError("retained solution trace ends at wrong state")
        witness = SolutionWitness(actions, tuple(states), verification)

    return CountdownCalibration(calibration_profile, witness)


def _counter_sample(
    *, seed: int, attempt: int, coordinate: int, minimum: int, maximum: int
) -> int:
    payload = f"{GENERATOR_ID}|{seed}|{attempt}|{coordinate}".encode("ascii")
    draw = int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")
    return minimum + draw % (maximum - minimum + 1)


def _candidate_task(seed: int, attempt: int) -> CountdownTask:
    inputs = tuple(
        _counter_sample(
            seed=seed,
            attempt=attempt,
            coordinate=coordinate,
            minimum=1,
            maximum=10,
        )
        for coordinate in range(INPUT_COUNT)
    )
    target = _counter_sample(
        seed=seed,
        attempt=attempt,
        coordinate=INPUT_COUNT,
        minimum=100,
        maximum=999,
    )
    return CountdownTask(inputs, target)


def generate_candidate_tasks(count: int, seed: int) -> tuple[CountdownTask, ...]:
    """Generate an unfiltered diagnostic pool with unique full task identities."""

    _require_plain_int(count, "count", minimum=1)
    _require_plain_int(seed, "seed")
    tasks: list[CountdownTask] = []
    seen: set[str] = set()
    attempt = 0
    while len(tasks) < count:
        task = _candidate_task(seed, attempt)
        if task.task_fingerprint not in seen:
            seen.add(task.task_fingerprint)
            tasks.append(task)
        attempt += 1
    return tuple(tasks)


@dataclass(frozen=True)
class GeneratedTaskSuite:
    """A solvable, source-unique suite plus its already-computed calibrations."""

    tasks: tuple[CountdownTask, ...]
    calibrations: tuple[CountdownCalibration, ...]
    generation_manifest: dict[str, Any]

    def to_calibration_record(self) -> dict[str, Any]:
        return calibrate_pool(
            self.tasks,
            generator=self.generation_manifest,
            calibrations=self.calibrations,
        )


def generate_solvable_task_suite(
    count: int,
    seed: int,
    *,
    excluded_task_fingerprints: Sequence[str] = (),
    excluded_source_multiset_fingerprints: Sequence[str] = (),
    excluded_identity_record_digest: str | None = None,
    max_attempts: int | None = None,
) -> GeneratedTaskSuite:
    """Build a deterministic primary-suite candidate set.

    The exhaustive solver is used only here, before a suite is locked.  Its
    calibration objects and rejection log are never policy inputs.  Accepted
    tasks are solvable and unique by both full task and source multiset.
    """

    _require_plain_int(count, "count", minimum=1)
    _require_plain_int(seed, "seed")
    resolved_max_attempts = max(10_000, count * 200)
    if max_attempts is not None:
        resolved_max_attempts = _require_plain_int(
            max_attempts, "max_attempts", minimum=1
        )

    if isinstance(excluded_task_fingerprints, str) or isinstance(
        excluded_source_multiset_fingerprints, str
    ):
        raise TypeError("excluded fingerprints must be a sequence, not one string")
    if excluded_identity_record_digest is not None and (
        not isinstance(excluded_identity_record_digest, str)
        or not excluded_identity_record_digest
    ):
        raise ValueError("excluded identity record digest must be a non-empty string")
    excluded_tasks = set(excluded_task_fingerprints)
    excluded_sources = set(excluded_source_multiset_fingerprints)
    if any(not isinstance(item, str) or not item for item in excluded_tasks):
        raise ValueError("excluded task fingerprints must be non-empty strings")
    if any(not isinstance(item, str) or not item for item in excluded_sources):
        raise ValueError("excluded source fingerprints must be non-empty strings")

    tasks: list[CountdownTask] = []
    calibrations: list[CountdownCalibration] = []
    attempted_tasks: set[str] = set()
    accepted_sources: set[str] = set()
    rejection_counts: Counter[str] = Counter()
    rejection_log: list[dict[str, Any]] = []

    for attempt in range(resolved_max_attempts):
        task = _candidate_task(seed, attempt)
        reason: str | None = None
        calibration: CountdownCalibration | None = None
        if task.task_fingerprint in attempted_tasks:
            reason = "duplicate_full_task"
        else:
            attempted_tasks.add(task.task_fingerprint)
            if task.task_fingerprint in excluded_tasks:
                reason = "excluded_full_task"
            elif task.source_multiset_fingerprint in excluded_sources:
                reason = "excluded_source_multiset"
            elif task.source_multiset_fingerprint in accepted_sources:
                reason = "duplicate_source_multiset"
            else:
                calibration = calibrate_task(task)
                if not calibration.calibration_profile["metrics"][
                    "solution_terminal_reachable"
                ]:
                    reason = "unsolvable"

        if reason is not None:
            rejection_counts[reason] += 1
            rejection_log.append(
                {
                    "attempt": attempt,
                    "reason": reason,
                    "source_multiset_fingerprint": (task.source_multiset_fingerprint),
                    "task_fingerprint": task.task_fingerprint,
                }
            )
            continue

        if calibration is None:
            raise AssertionError("accepted task is missing exhaustive calibration")
        tasks.append(task)
        calibrations.append(calibration)
        accepted_sources.add(task.source_multiset_fingerprint)
        if len(tasks) == count:
            attempt_count = attempt + 1
            break
    else:
        raise RuntimeError(
            f"could not generate {count} solvable source-unique tasks within "
            f"{resolved_max_attempts} attempts"
        )

    rejection_reasons = (
        "duplicate_full_task",
        "duplicate_source_multiset",
        "excluded_full_task",
        "excluded_source_multiset",
        "unsolvable",
    )
    manifest_core = {
        "accepted_count": len(tasks),
        "accepted_task_pool_digest": _sha256_json([task.to_dict() for task in tasks]),
        "attempt_count": attempt_count,
        "conditioned_on_exhaustive_solvability": True,
        "excluded_identity_record_digest": excluded_identity_record_digest,
        "excluded_source_multiset_fingerprint_count": len(excluded_sources),
        "excluded_source_multiset_fingerprint_digest": _sha256_json(
            sorted(excluded_sources)
        ),
        "excluded_task_fingerprint_count": len(excluded_tasks),
        "excluded_task_fingerprint_digest": _sha256_json(sorted(excluded_tasks)),
        "generator_id": GENERATOR_ID,
        "input_range_inclusive": [1, 10],
        "max_attempts": resolved_max_attempts,
        "rejection_counts": {
            reason: rejection_counts[reason] for reason in rejection_reasons
        },
        "rejection_log": rejection_log,
        "requested_count": count,
        "seed": seed,
        "source_multisets_unique": True,
        "target_range_inclusive": [100, 999],
    }
    manifest = {
        **manifest_core,
        "generation_manifest_digest": _sha256_json(manifest_core),
    }
    return GeneratedTaskSuite(tuple(tasks), tuple(calibrations), manifest)


def calibrate_pool(
    tasks: Sequence[CountdownTask],
    *,
    generator: dict[str, Any] | None = None,
    calibrations: Sequence[CountdownCalibration] | None = None,
) -> dict[str, Any]:
    if not tasks:
        raise ValueError("candidate pool cannot be empty")
    fingerprints = [task.task_fingerprint for task in tasks]
    if len(set(fingerprints)) != len(fingerprints):
        raise ValueError("candidate pool contains duplicate task identities")

    resolved_calibrations = (
        list(calibrations)
        if calibrations is not None
        else [calibrate_task(task) for task in tasks]
    )
    if len(resolved_calibrations) != len(tasks):
        raise ValueError("calibration count must match task count")
    for task, calibration in zip(tasks, resolved_calibrations):
        calibrated_task = calibration.calibration_profile.get("task", {})
        if (
            calibrated_task.get("task_fingerprint") != task.task_fingerprint
            or calibrated_task.get("ruleset_id") != RULESET_ID
        ):
            raise ValueError("calibration identity does not match candidate task")
    profiles = [
        calibration.calibration_profile for calibration in resolved_calibrations
    ]
    witness_digests = [
        {
            "solution_witness_digest": (
                calibration.solution_witness.to_dict()["witness_digest"]
                if calibration.solution_witness is not None
                else None
            ),
            "task_fingerprint": task.task_fingerprint,
            "task_id": task.task_id,
        }
        for task, calibration in zip(tasks, resolved_calibrations)
    ]
    metrics = [profile["metrics"] for profile in profiles]
    solvable = sum(bool(metric["solution_terminal_reachable"]) for metric in metrics)
    aggregate = {
        "candidate_count": len(tasks),
        "solvable_task_count": solvable,
        "total_action_paths": sum(metric["action_path_count"] for metric in metrics),
        "total_legal_edges": sum(metric["legal_edge_count"] for metric in metrics),
        "total_reachable_states": sum(
            metric["reachable_state_count"] for metric in metrics
        ),
        "total_solution_paths": sum(
            metric["solution_path_count"] for metric in metrics
        ),
        "total_transposition_states": sum(
            metric["transposition_state_count"] for metric in metrics
        ),
        "unsolvable_task_count": len(tasks) - solvable,
    }
    pool_core = {
        "aggregate": aggregate,
        "candidate_pool_digest": _sha256_json([task.to_dict() for task in tasks]),
        "generator": generator,
        "task_profiles": profiles,
    }
    pool_profile = {**pool_core, "profile_digest": _sha256_json(pool_core)}
    payload = {
        "calibration_pool_profile": pool_profile,
        "diagnostics": {"solution_witness_digests": witness_digests},
        "record_type": "candidate_pool_calibration",
        "schema_version": SCHEMA_VERSION,
    }
    return {**payload, "deterministic_digest": _sha256_json(payload)}


def assert_disjoint_task_suites(
    calibration_tasks: Sequence[CountdownTask],
    evaluation_tasks: Sequence[CountdownTask],
) -> dict[str, Any]:
    """Enforce full-task and source-multiset isolation for locked splits."""

    if not calibration_tasks or not evaluation_tasks:
        raise ValueError("both task suites must be non-empty")

    def identities(
        tasks: Sequence[CountdownTask], label: str
    ) -> tuple[list[str], list[str]]:
        task_ids = [task.task_fingerprint for task in tasks]
        source_ids = [task.source_multiset_fingerprint for task in tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError(f"{label} suite repeats a full task fingerprint")
        if len(source_ids) != len(set(source_ids)):
            raise ValueError(f"{label} suite repeats a source multiset fingerprint")
        return task_ids, source_ids

    calibration_task_ids, calibration_source_ids = identities(
        calibration_tasks, "calibration"
    )
    evaluation_task_ids, evaluation_source_ids = identities(
        evaluation_tasks, "evaluation"
    )
    if set(calibration_task_ids) & set(evaluation_task_ids):
        raise ValueError("calibration and evaluation suites overlap by full task")
    if set(calibration_source_ids) & set(evaluation_source_ids):
        raise ValueError("calibration and evaluation suites overlap by source multiset")
    payload = {
        "calibration_source_multiset_digest": _sha256_json(
            sorted(calibration_source_ids)
        ),
        "calibration_task_count": len(calibration_tasks),
        "evaluation_source_multiset_digest": _sha256_json(
            sorted(evaluation_source_ids)
        ),
        "evaluation_task_count": len(evaluation_tasks),
        "source_multisets_disjoint": True,
        "task_fingerprints_disjoint": True,
    }
    return {**payload, "split_identity_digest": _sha256_json(payload)}


def _expect_action_error(reason: str, callback: Any) -> None:
    try:
        callback()
    except CountdownActionError as error:
        assert error.reason == reason, (error.reason, reason)
    else:
        raise AssertionError(f"expected CountdownActionError({reason!r})")


def _run_self_test() -> None:
    duplicate_task = CountdownTask((1, 1, 2, 3, 4, 5), 16)
    duplicate_action = CountdownAction(1, 1, "+")
    assert duplicate_action in duplicate_task.legal_actions(
        duplicate_task.initial_state
    )
    assert duplicate_task.transition(
        duplicate_task.initial_state, duplicate_action
    ) == (
        2,
        2,
        3,
        4,
        5,
    )
    _expect_action_error(
        "operand_multiplicity",
        lambda: duplicate_task.transition((1, 2, 3), duplicate_action),
    )
    parallel_actions = duplicate_task.legal_actions((2, 2))
    plus_edge = CountdownAction(2, 2, "+")
    multiply_edge = CountdownAction(2, 2, "*")
    assert plus_edge in parallel_actions and multiply_edge in parallel_actions
    assert duplicate_task.transition((2, 2), plus_edge) == (4,)
    assert duplicate_task.transition((2, 2), multiply_edge) == (4,)
    assert len(parallel_actions) == 3
    assert len({duplicate_task.transition((2, 2), a) for a in parallel_actions}) == 2
    mixed_pair_actions = duplicate_task.legal_actions((2, 4))
    assert len(mixed_pair_actions) == 4
    assert duplicate_task.transition((2, 4), CountdownAction(4, 2, "-")) == (2,)
    assert duplicate_task.transition((2, 4), CountdownAction(4, 2, "/")) == (2,)

    assert CountdownAction(3, 2, "-").evaluate() == 1
    _expect_action_error(
        "non_positive_subtraction", lambda: CountdownAction(2, 3, "-").evaluate()
    )
    assert CountdownAction(6, 3, "/").evaluate() == 2
    _expect_action_error(
        "non_integral_division", lambda: CountdownAction(3, 6, "/").evaluate()
    )
    _expect_action_error("unknown_operator", lambda: CountdownAction(1, 2, "^"))
    _expect_action_error(
        "operand_unavailable",
        lambda: duplicate_task.transition((1, 2, 3), CountdownAction(2, 4, "+")),
    )

    source_task = CountdownTask((1, 1, 1, 1, 1, 1), 6)
    source_trace = (
        CountdownAction(1, 1, "+"),
        CountdownAction(1, 1, "+"),
        CountdownAction(1, 1, "+"),
        CountdownAction(2, 2, "+"),
        CountdownAction(2, 4, "+"),
    )
    source_result = source_task.verify(source_trace)
    assert source_result.success
    assert source_result.source_use_exact
    assert source_result.final_expression_source_indices == tuple(range(INPUT_COUNT))
    assert len(source_result.steps) == ACTION_COUNT
    incomplete = source_task.verify(source_trace[:-1])
    assert not incomplete.success
    assert incomplete.reason == "incomplete_reduction"
    assert not incomplete.source_use_exact

    # Two operation orders merge into one numeric state.  Both complete traces
    # remain independently replayable from the original labelled sources.
    merge_task = CountdownTask((1, 2, 3, 4, 5, 6), 21)
    merge_prefix_a = (
        CountdownAction(1, 2, "+"),
        CountdownAction(3, 4, "+"),
    )
    merge_prefix_b = (
        CountdownAction(3, 4, "+"),
        CountdownAction(1, 2, "+"),
    )
    state_a = merge_task.initial_state
    state_b = merge_task.initial_state
    for action in merge_prefix_a:
        state_a = merge_task.transition(state_a, action)
    for action in merge_prefix_b:
        state_b = merge_task.transition(state_b, action)
    assert state_a == state_b == (3, 5, 6, 7)
    merge_suffix = (
        CountdownAction(3, 5, "+"),
        CountdownAction(6, 7, "+"),
        CountdownAction(8, 13, "+"),
    )
    for prefix in (merge_prefix_a, merge_prefix_b):
        verified = merge_task.verify(prefix + merge_suffix)
        assert verified.success
        assert verified.source_use_exact

    calibration_a = calibrate_task(merge_task)
    calibration_b = calibrate_task(merge_task)
    assert calibration_a.calibration_profile == calibration_b.calibration_profile
    assert (
        calibration_a.calibration_profile["state_space_digest"]
        == calibration_b.calibration_profile["state_space_digest"]
    )
    assert calibration_a.calibration_profile["metrics"]["transposition_state_count"] > 0
    assert (
        calibration_a.calibration_profile["metrics"][
            "solution_bearing_root_action_count"
        ]
        > 0
    )
    assert calibration_a.solution_witness is not None
    assert calibration_a.solution_witness.verification.success
    assert calibration_a.solution_witness.states[0] == merge_task.initial_state
    assert calibration_a.solution_witness.states[-1] == (merge_task.target,)

    unsolvable_task = CountdownTask((1, 1, 1, 1, 1, 1), 999)
    unsolvable = calibrate_task(unsolvable_task)
    assert not unsolvable.calibration_profile["metrics"]["solution_terminal_reachable"]
    assert unsolvable.calibration_profile["metrics"]["solution_path_count"] == 0
    assert unsolvable.solution_witness is None

    # Equal local states must never collide across different target tasks.
    alternate_target = CountdownTask(merge_task.inputs, 20)
    permuted = CountdownTask(tuple(reversed(merge_task.inputs)), merge_task.target)
    assert permuted.task_fingerprint == merge_task.task_fingerprint
    assert (
        permuted.source_multiset_fingerprint == merge_task.source_multiset_fingerprint
    )
    key_a = merge_task.state_key((3, 5, 6, 7))
    key_b = alternate_target.state_key((3, 5, 6, 7))
    assert key_a.values == key_b.values
    assert key_a != key_b
    assert key_a.task_fingerprint != key_b.task_fingerprint
    assert (
        CountdownStateKey("different-rules/v1", key_a.task_fingerprint, key_a.values)
        != key_a
    )

    split_evaluation = CountdownTask((2, 3, 4, 5, 6, 7), 100)
    split_record = assert_disjoint_task_suites((merge_task,), (split_evaluation,))
    assert split_record["source_multisets_disjoint"]
    try:
        assert_disjoint_task_suites((merge_task,), (alternate_target,))
    except ValueError as error:
        assert "source multiset" in str(error)
    else:
        raise AssertionError("source-overlapping suites must be rejected")

    try:
        calibrate_pool((merge_task,), calibrations=(unsolvable,))
    except ValueError as error:
        assert "identity" in str(error)
    else:
        raise AssertionError("mismatched calibration identity must be rejected")

    budget = ComputeBudget(
        proposal_batch_calls=1,
        proposal_state_items=1,
        proposal_input_values=7,
        proposal_action_scores=4,
        selection_action_scores=4,
        edge_selections=3,
        transitions=2,
        verifier_calls=1,
    )
    ledger = ComputeLedger(budget)
    ledger.charge(proposal_batch_calls=1, proposal_action_scores=2)
    snapshot_before = ledger.snapshot()
    assert not ledger.try_charge(proposal_action_scores=3, edge_selections=1)
    assert ledger.snapshot() == snapshot_before
    try:
        ledger.charge(proposal_input_values=8, transitions=1)
    except BudgetExceeded as error:
        assert error.blocked_axes == ("proposal_input_values",)
    else:
        raise AssertionError("oversized atomic charge must fail")
    assert ledger.snapshot() == snapshot_before
    ledger.record_cache_lookup(key_a, hit=False)
    ledger.record_cache_lookup(key_a, hit=True)
    ledger.record_cache_lookup(key_b, hit=False)
    ledger_snapshot = ledger.snapshot()
    assert ledger_snapshot["unique_states"] == 2
    assert ledger_snapshot["cache_hits"] == 1
    assert ledger_snapshot["cache_misses"] == 2
    assert ledger_snapshot["overshoot"] == 0
    for axis in COMPUTE_AXES:
        assert ledger_snapshot["usage"][axis] <= ledger_snapshot["limits"][axis]

    generated_a = generate_candidate_tasks(3, 17)
    generated_b = generate_candidate_tasks(3, 17)
    assert generated_a == generated_b
    assert len({task.task_fingerprint for task in generated_a}) == 3
    suite_a = generate_solvable_task_suite(3, 17)
    suite_b = generate_solvable_task_suite(3, 17)
    assert suite_a.to_calibration_record() == suite_b.to_calibration_record()
    assert all(
        calibration.calibration_profile["metrics"]["solution_terminal_reachable"]
        for calibration in suite_a.calibrations
    )
    assert len({task.source_multiset_fingerprint for task in suite_a.tasks}) == 3
    assert (
        sum(suite_a.generation_manifest["rejection_counts"].values())
        == suite_a.generation_manifest["attempt_count"] - 3
    )
    excluded_suite = generate_solvable_task_suite(
        1,
        17,
        excluded_source_multiset_fingerprints=(
            generated_a[0].source_multiset_fingerprint,
        ),
    )
    assert (
        excluded_suite.generation_manifest["rejection_counts"][
            "excluded_source_multiset"
        ]
        >= 1
    )
    unused_exclusion_suite = generate_solvable_task_suite(
        1,
        17,
        excluded_task_fingerprints=("0" * 64,),
    )
    assert unused_exclusion_suite.tasks == suite_a.tasks[:1]
    assert (
        unused_exclusion_suite.generation_manifest["generation_manifest_digest"]
        != generate_solvable_task_suite(1, 17).generation_manifest[
            "generation_manifest_digest"
        ]
    )
    unsolvable_rejection_suite = generate_solvable_task_suite(1, 2)
    assert (
        unsolvable_rejection_suite.generation_manifest["rejection_counts"]["unsolvable"]
        >= 1
    )
    try:
        generate_solvable_task_suite(1, 2, max_attempts=1)
    except RuntimeError as error:
        assert "within 1 attempts" in str(error)
    else:
        raise AssertionError("suite generation must fail closed at max_attempts")
    pooled_strict = _canonical_json(suite_a.to_calibration_record())
    assert '"solution_witness"' not in pooled_strict
    assert '"actions"' not in pooled_strict
    single_record = calibration_a.to_record()
    assert "solution_witness" not in single_record["diagnostics"]
    debug_record = calibration_a.to_record(include_witness=True)
    assert debug_record["diagnostics"]["solution_witness"]["verification"]["success"]
    strict = _canonical_json(single_record)
    assert json.loads(strict) == single_record
    assert "NaN" not in strict and "Infinity" not in strict
    assert single_record == calibration_b.to_record()

    print("countdown self-test: PASS")
    print(
        "sample:",
        _canonical_json(
            {
                "solution_paths": calibration_a.calibration_profile["metrics"][
                    "solution_path_count"
                ],
                "state_space_digest": calibration_a.calibration_profile[
                    "state_space_digest"
                ],
                "states": calibration_a.calibration_profile["metrics"][
                    "reachable_state_count"
                ],
                "transposition_states": calibration_a.calibration_profile["metrics"][
                    "transposition_state_count"
                ],
            }
        ),
    )


def _parse_inputs(value: str) -> tuple[int, ...]:
    try:
        values = tuple(int(part.strip()) for part in value.split(","))
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "--inputs must contain comma-separated integers"
        ) from error
    if len(values) != INPUT_COUNT or any(item <= 0 for item in values):
        raise argparse.ArgumentTypeError(
            f"--inputs requires exactly {INPUT_COUNT} positive integers"
        )
    return values


def _write_output(payload: dict[str, Any], output: Path | None) -> None:
    rendered = _pretty_json(payload) + "\n"
    if output is None:
        print(rendered, end="")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")


def _load_excluded_suite(
    path: Path,
) -> tuple[tuple[str, ...], tuple[str, ...], str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read exclusion suite: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError("exclusion suite must be a JSON object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("exclusion suite schema version does not match")
    if payload.get("record_type") != "candidate_pool_calibration":
        raise ValueError("exclusion suite must be a candidate pool calibration")
    record_digest = payload.get("deterministic_digest")
    digest_payload = {
        key: value for key, value in payload.items() if key != "deterministic_digest"
    }
    if (
        not isinstance(record_digest, str)
        or _sha256_json(digest_payload) != record_digest
    ):
        raise ValueError("exclusion suite deterministic digest is missing or invalid")
    try:
        profiles = payload["calibration_pool_profile"]["task_profiles"]
    except (KeyError, TypeError) as error:
        raise ValueError("exclusion suite lacks calibrated task profiles") from error
    if not isinstance(profiles, list) or not profiles:
        raise ValueError("exclusion suite task profiles must be a non-empty list")

    task_fingerprints: list[str] = []
    source_fingerprints: list[str] = []
    for profile in profiles:
        try:
            task_record = profile["task"]
            task_fingerprint = task_record["task_fingerprint"]
            source_fingerprint = task_record["source_multiset_fingerprint"]
        except (KeyError, TypeError) as error:
            raise ValueError(
                "exclusion suite contains a malformed task profile"
            ) from error
        if not isinstance(task_fingerprint, str) or not isinstance(
            source_fingerprint, str
        ):
            raise ValueError("exclusion suite fingerprints must be strings")
        try:
            reconstructed = CountdownTask(
                tuple(task_record["inputs"]), task_record["target"]
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("exclusion suite task definition is invalid") from error
        if task_record.get("ruleset_id") != RULESET_ID:
            raise ValueError("exclusion suite ruleset does not match")
        if (
            reconstructed.task_fingerprint != task_fingerprint
            or reconstructed.source_multiset_fingerprint != source_fingerprint
        ):
            raise ValueError("exclusion suite task identity is inconsistent")
        task_fingerprints.append(task_fingerprint)
        source_fingerprints.append(source_fingerprint)
    if len(task_fingerprints) != len(set(task_fingerprints)):
        raise ValueError("exclusion suite repeats a full task fingerprint")
    if len(source_fingerprints) != len(set(source_fingerprints)):
        raise ValueError("exclusion suite repeats a source multiset fingerprint")
    return (
        tuple(sorted(task_fingerprints)),
        tuple(sorted(source_fingerprints)),
        record_digest,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--inputs", type=_parse_inputs)
    parser.add_argument("--target", type=int)
    parser.add_argument("--generate-candidates", type=int, metavar="N")
    parser.add_argument("--generate-solvable-suite", type=int, metavar="N")
    parser.add_argument(
        "--exclude-suite",
        type=Path,
        help="exclude every task/source identity in a prior calibrated suite",
    )
    parser.add_argument(
        "--include-witness",
        action="store_true",
        help="include a full debug witness in single-task output",
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.self_test:
        _run_self_test()
        return

    single_mode = args.inputs is not None or args.target is not None
    generated_mode = args.generate_candidates is not None
    suite_mode = args.generate_solvable_suite is not None
    if sum((single_mode, generated_mode, suite_mode)) > 1:
        parser.error(
            "choose one of --inputs/--target, --generate-candidates, or "
            "--generate-solvable-suite"
        )
    if not any((single_mode, generated_mode, suite_mode)):
        parser.error(
            "provide --inputs and --target, --generate-candidates, or "
            "--generate-solvable-suite"
        )
    if args.seed < 0:
        parser.error("--seed must be non-negative")
    if args.include_witness and not single_mode:
        parser.error("--include-witness is available only in single-task mode")
    if args.exclude_suite is not None and not suite_mode:
        parser.error("--exclude-suite requires --generate-solvable-suite")

    if single_mode:
        if args.inputs is None or args.target is None:
            parser.error("single-task mode requires both --inputs and --target")
        if args.target <= 0:
            parser.error("--target must be positive")
        payload = calibrate_task(CountdownTask(args.inputs, args.target)).to_record(
            include_witness=args.include_witness
        )
    elif generated_mode:
        if args.generate_candidates is None or args.generate_candidates <= 0:
            parser.error("--generate-candidates must be positive")
        tasks = generate_candidate_tasks(args.generate_candidates, args.seed)
        generator = {
            "candidate_count": args.generate_candidates,
            "generator_id": GENERATOR_ID,
            "input_range_inclusive": [1, 10],
            "seed": args.seed,
            "target_range_inclusive": [100, 999],
        }
        payload = calibrate_pool(tasks, generator=generator)
    else:
        if args.generate_solvable_suite is None or args.generate_solvable_suite <= 0:
            parser.error("--generate-solvable-suite must be positive")
        excluded_tasks: tuple[str, ...] = ()
        excluded_sources: tuple[str, ...] = ()
        excluded_record_digest: str | None = None
        if args.exclude_suite is not None:
            try:
                (
                    excluded_tasks,
                    excluded_sources,
                    excluded_record_digest,
                ) = _load_excluded_suite(args.exclude_suite)
            except ValueError as error:
                parser.error(str(error))
        suite = generate_solvable_task_suite(
            args.generate_solvable_suite,
            args.seed,
            excluded_task_fingerprints=excluded_tasks,
            excluded_source_multiset_fingerprints=excluded_sources,
            excluded_identity_record_digest=excluded_record_digest,
        )
        payload = suite.to_calibration_record()
    _write_output(payload, args.output)


if __name__ == "__main__":
    main()
