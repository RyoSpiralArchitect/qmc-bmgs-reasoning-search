"""Pure, provider-neutral proposal policies for Countdown Track A.

Proposal evaluation deliberately owns neither a work ledger nor a mutable
cache.  A search session can therefore validate the complete request, accept
one atomic search-step charge, evaluate a cache miss, and commit the returned
immutable row without hidden state in this module.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

from qmc_bmgs.benchmarks.countdown import (
    CountdownAction,
    CountdownState,
    CountdownTask,
)
from qmc_bmgs.substrate.trace import sha256_json


PROPOSAL_SPEC_SCHEMA_VERSION = "qmc-bmgs-track-a-proposal-spec/v1"
PROPOSAL_ROW_SCHEMA_VERSION = "qmc-bmgs-track-a-proposal-row/v1"
TRACK_A_PROPOSAL_POLICY_IDS = (
    "uniform/v1",
    "greedy_rollout_target_error/v1",
    "oracle_path_count_positive_control/v1",
)


def _is_lower_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _action_payload(
    actions: Sequence[CountdownAction],
) -> list[dict[str, Any]]:
    return [action.to_dict() for action in actions]


def _countdown_v1_legal_action_order(
    state: CountdownState,
) -> tuple[CountdownAction, ...]:
    """Reconstruct the exact v1 state-local legal-action order.

    Countdown legality depends only on the current positive-value multiset,
    not on the target or on whether a particular task history reached that
    state.  Proposal rows intentionally do not carry a task object, so their
    constructor uses this versioned structural helper instead of inventing a
    dummy task or claiming reachability.  A change to the task adapter's v1
    action semantics therefore requires a proposal-row schema version bump.
    """

    if len(state) < 2:
        return ()
    value_pairs = {
        (state[left], state[right])
        for left in range(len(state))
        for right in range(left + 1, len(state))
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


def _stable_log_softmax(raw_scores: Sequence[float]) -> tuple[float, ...]:
    """Return a finite deterministic log-softmax without overflow."""

    scores = tuple(raw_scores)
    if not scores:
        raise ValueError("proposal scores cannot be empty")
    if any(type(value) is not float or not math.isfinite(value) for value in scores):
        raise ValueError("proposal raw scores must be finite plain floats")
    maximum = max(scores)
    shifted_sum = math.fsum(math.exp(value - maximum) for value in scores)
    log_normalizer = maximum + math.log(shifted_sum)
    result = tuple(value - log_normalizer for value in scores)
    if any(not math.isfinite(value) for value in result):
        raise ValueError("proposal normalization produced a non-finite value")
    return result


@dataclass(frozen=True)
class TrackAProposalSpec:
    """Versioned identity of one provider-neutral proposal policy."""

    policy_id: str

    def __post_init__(self) -> None:
        if type(self.policy_id) is not str or self.policy_id not in (
            TRACK_A_PROPOSAL_POLICY_IDS
        ):
            raise ValueError(
                f"policy_id must be one of {TRACK_A_PROPOSAL_POLICY_IDS!r}"
            )

    @property
    def positive_control(self) -> bool:
        return self.policy_id == "oracle_path_count_positive_control/v1"

    @property
    def deterministic_digest(self) -> str:
        return sha256_json(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "positive_control": self.positive_control,
            "schema_version": PROPOSAL_SPEC_SCHEMA_VERSION,
        }


@dataclass(frozen=True)
class TrackAProposalRow:
    """Immutable proposal material for one exact task/state/action order."""

    spec: TrackAProposalSpec
    task_fingerprint: str
    state: CountdownState
    actions: tuple[CountdownAction, ...]
    raw_scores: tuple[float, ...]
    prior_logp: tuple[float, ...]
    internal_transition_evaluations: int

    def __post_init__(self) -> None:
        if type(self.spec) is not TrackAProposalSpec:
            raise TypeError("spec must be exactly TrackAProposalSpec")
        if not _is_lower_sha256(self.task_fingerprint):
            raise ValueError("task_fingerprint must be lowercase SHA-256")
        if (
            type(self.state) is not tuple
            or not self.state
            or any(type(value) is not int or value <= 0 for value in self.state)
            or self.state != tuple(sorted(self.state))
        ):
            raise ValueError("state must be a non-empty canonical Countdown state")
        if (
            type(self.actions) is not tuple
            or not self.actions
            or any(type(action) is not CountdownAction for action in self.actions)
        ):
            raise ValueError("actions must be a non-empty canonical action tuple")
        if self.actions != tuple(
            sorted(set(self.actions), key=CountdownAction.sort_key)
        ):
            raise ValueError("actions must be unique and in canonical action order")
        if self.actions != _countdown_v1_legal_action_order(self.state):
            raise ValueError(
                "actions must equal the complete Countdown v1 legal-action order"
            )
        if type(self.raw_scores) is not tuple or len(self.raw_scores) != len(
            self.actions
        ):
            raise ValueError("raw_scores must align with actions")
        if type(self.prior_logp) is not tuple or len(self.prior_logp) != len(
            self.actions
        ):
            raise ValueError("prior_logp must align with actions")
        if any(
            type(value) is not float or not math.isfinite(value)
            for value in self.prior_logp
        ):
            raise ValueError("prior_logp values must be finite plain floats")
        expected_prior = _stable_log_softmax(self.raw_scores)
        if self.prior_logp != expected_prior:
            raise ValueError("prior_logp is not the stable log-softmax of raw_scores")
        if (
            type(self.internal_transition_evaluations) is not int
            or self.internal_transition_evaluations < 0
        ):
            raise ValueError(
                "internal_transition_evaluations must be a non-negative plain integer"
            )

    @property
    def policy_id(self) -> str:
        return self.spec.policy_id

    @property
    def positive_control(self) -> bool:
        return self.spec.positive_control

    @property
    def action_order_digest(self) -> str:
        return sha256_json(_action_payload(self.actions))

    def behavior_core(self) -> dict[str, Any]:
        return {
            "action_order": _action_payload(self.actions),
            "action_order_digest": self.action_order_digest,
            "internal_transition_evaluations": (self.internal_transition_evaluations),
            "policy_spec": self.spec.to_dict(),
            "policy_spec_digest": self.spec.deterministic_digest,
            "prior_logp": list(self.prior_logp),
            "raw_scores": list(self.raw_scores),
            "schema_version": PROPOSAL_ROW_SCHEMA_VERSION,
            "state": list(self.state),
            "task_fingerprint": self.task_fingerprint,
        }

    @property
    def behavior_digest(self) -> str:
        return sha256_json(self.behavior_core())

    @property
    def deterministic_digest(self) -> str:
        return self.behavior_digest

    def to_dict(self) -> dict[str, Any]:
        core = self.behavior_core()
        return {**core, "behavior_digest": self.behavior_digest}


def _closest_result_action_index(
    task: CountdownTask,
    actions: Sequence[CountdownAction],
) -> int:
    """Canonical deterministic one-step policy used inside rollout scoring."""

    return min(
        range(len(actions)),
        key=lambda index: (
            abs(actions[index].evaluate() - task.target),
            index,
        ),
    )


def _greedy_completion_error(
    task: CountdownTask,
    state: CountdownState,
) -> tuple[int, int]:
    """Complete one state greedily and return (target error, transitions)."""

    current = state
    transition_evaluations = 0
    while len(current) > 1:
        actions = task.legal_actions(current)
        if not actions:
            break
        selected = _closest_result_action_index(task, actions)
        current = task.transition(current, actions[selected])
        transition_evaluations += 1
    terminal_error = min(abs(value - task.target) for value in current)
    return terminal_error, transition_evaluations


def _greedy_rollout_scores(
    task: CountdownTask,
    state: CountdownState,
    actions: tuple[CountdownAction, ...],
) -> tuple[tuple[float, ...], int]:
    ranking_keys: list[tuple[int, int, int]] = []
    transition_evaluations = 0
    for canonical_index, action in enumerate(actions):
        child = task.transition(state, action)
        transition_evaluations += 1
        terminal_error, completion_evaluations = _greedy_completion_error(
            task,
            child,
        )
        transition_evaluations += completion_evaluations
        ranking_keys.append(
            (
                terminal_error,
                abs(action.evaluate() - task.target),
                canonical_index,
            )
        )

    ordered_indices = sorted(range(len(actions)), key=ranking_keys.__getitem__)
    ranks = [0] * len(actions)
    for rank, action_index in enumerate(ordered_indices):
        ranks[action_index] = rank
    # Rank logits are finite and yield a controlled geometric falloff after
    # log-softmax.  Canonical index makes every rank deterministic.
    return tuple(-float(rank) for rank in ranks), transition_evaluations


def _oracle_path_count_scores(
    task: CountdownTask,
    state: CountdownState,
    actions: tuple[CountdownAction, ...],
) -> tuple[tuple[float, ...], int]:
    memo: dict[CountdownState, int] = {}
    transition_evaluations = 0

    def count_paths(current: CountdownState) -> int:
        nonlocal transition_evaluations
        cached = memo.get(current)
        if cached is not None:
            return cached
        if len(current) == 1:
            result = int(current[0] == task.target)
            memo[current] = result
            return result
        total = 0
        for action in task.legal_actions(current):
            child = task.transition(current, action)
            transition_evaluations += 1
            total += count_paths(child)
        memo[current] = total
        return total

    path_counts: list[int] = []
    for action in actions:
        child = task.transition(state, action)
        transition_evaluations += 1
        path_counts.append(count_paths(child))
    raw_scores = tuple(float(count) for count in path_counts)
    if any(not math.isfinite(value) for value in raw_scores):
        raise ValueError("oracle solution-path count exceeds finite float range")
    return raw_scores, transition_evaluations


def evaluate_track_a_proposal(
    task: CountdownTask,
    state: CountdownState,
    spec: TrackAProposalSpec,
) -> TrackAProposalRow:
    """Evaluate one pure proposal row without charging or retaining a cache."""

    if type(task) is not CountdownTask:
        raise TypeError("task must be exactly CountdownTask")
    if type(spec) is not TrackAProposalSpec:
        raise TypeError("spec must be exactly TrackAProposalSpec")
    canonical_state = task.canonical_state(state)
    actions = task.legal_actions(canonical_state)
    if not actions:
        raise ValueError("terminal or actionless states have no proposal row")

    if spec.policy_id == "uniform/v1":
        raw_scores = (0.0,) * len(actions)
        transition_evaluations = 0
    elif spec.policy_id == "greedy_rollout_target_error/v1":
        raw_scores, transition_evaluations = _greedy_rollout_scores(
            task,
            canonical_state,
            actions,
        )
    elif spec.policy_id == "oracle_path_count_positive_control/v1":
        raw_scores, transition_evaluations = _oracle_path_count_scores(
            task,
            canonical_state,
            actions,
        )
    else:  # pragma: no cover - TrackAProposalSpec closes this branch.
        raise AssertionError("validated proposal policy is not implemented")

    return TrackAProposalRow(
        spec=spec,
        task_fingerprint=task.task_fingerprint,
        state=canonical_state,
        actions=actions,
        raw_scores=raw_scores,
        prior_logp=_stable_log_softmax(raw_scores),
        internal_transition_evaluations=transition_evaluations,
    )


__all__ = [
    "PROPOSAL_ROW_SCHEMA_VERSION",
    "PROPOSAL_SPEC_SCHEMA_VERSION",
    "TRACK_A_PROPOSAL_POLICY_IDS",
    "TrackAProposalRow",
    "TrackAProposalSpec",
    "evaluate_track_a_proposal",
]
