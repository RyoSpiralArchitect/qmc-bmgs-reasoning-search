#!/usr/bin/env python3
"""Provider-backed Countdown development runner with offline replay.

This is a plumbing canary, not an effectiveness benchmark.  It serially acquires
an immutable Anthropic heuristic-score snapshot for two tiny public development
tasks, then runs four local search methods against exactly the same bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import heapq
import importlib.metadata
import json
import math
import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping, Protocol, Sequence

from qmc_bmgs.anthropic_countdown import (
    ADAPTER_SCHEMA_VERSION,
    API_ENDPOINT,
    API_VERSION,
    SYSTEM_INSTRUCTION,
    AnthropicCountdownScorer,
    AnthropicScoreResult,
)
from qmc_bmgs.benchmarks.countdown import (
    COMPUTE_AXES,
    RULESET_ID,
    BudgetExceeded,
    ComputeBudget,
    ComputeLedger,
    CountdownAction,
    CountdownState,
    CountdownTask,
)
from qmc_bmgs.records import canonical_record_digest


RECORD_SCHEMA_VERSION = "qmc-bmgs-countdown-anthropic-dev-record/v1"
PROPOSAL_SCHEMA_VERSION = "qmc-bmgs-countdown-proposal-row/v1"
SUMMARY_SCHEMA_VERSION = "qmc-bmgs-countdown-anthropic-dev-summary/v1"
MANIFEST_SCHEMA_VERSION = "qmc-bmgs-countdown-anthropic-dev-manifest/v1"
NORMALIZATION_VERSION = "integer-score-softmax-div100/v1"
RNG_VERSION = "sha256-counter-box-muller/v1"
PINNED_MODEL = "claude-haiku-4-5-20251001"
PINNED_SDK_VERSION = "0.116.0"
MAX_OUTPUT_TOKENS = 512
MAX_INPUT_TOKENS_PER_REQUEST = 4096
PHYSICAL_REQUEST_CAP = 64
PHYSICAL_COST_CAP_USD = 0.50
TOP_P = 0.95
ROLLOUTS = 8
THOMPSON_SIMULATIONS = 8
BEST_FIRST_TERMINALS = 8
THOMPSON_PRIOR_BONUS = 0.1
DEV_SEEDS = (0, 1)
FAKE_SECRET = "fake-provider-secret-must-never-appear"

PRICE_SOURCE = "https://platform.claude.com/docs/en/about-claude/pricing"
PRICE_RETRIEVED_DATE = "2026-07-22"
PRICE_PER_MTOK = {
    "base_input": 1.0,
    "cache_creation_input": 1.25,
    "cache_read_input": 0.10,
    "output": 5.0,
}

SEARCH_BUDGET = ComputeBudget(
    proposal_batch_calls=64,
    proposal_state_items=64,
    proposal_input_values=448,
    proposal_action_scores=256,
    selection_action_scores=512,
    edge_selections=128,
    transitions=128,
    verifier_calls=8,
)

DEV_TASKS = (
    CountdownTask((1, 1, 1, 1, 1, 1), 6),
    CountdownTask((1, 1, 1, 1, 1, 2), 10),
)


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
        sort_keys=True,
        indent=2,
        ensure_ascii=True,
        allow_nan=False,
    )


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_json(payload: Any) -> str:
    return _sha256_bytes(_canonical_json(payload).encode("utf-8"))


def _strict_json_text(text: str) -> Any:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant: {value}")

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON object key: {key!r}")
            result[key] = value
        return result

    return json.loads(
        text,
        object_pairs_hook=reject_duplicate_keys,
        parse_constant=reject_constant,
    )


def _strict_json_file(path: Path) -> Any:
    return _strict_json_text(path.read_text(encoding="utf-8"))


def _action_from_dict(payload: Mapping[str, Any]) -> CountdownAction:
    if set(payload) != {"left", "operator", "right"}:
        raise ValueError("invalid serialized Countdown action")
    return CountdownAction(payload["left"], payload["right"], payload["operator"])


def _trace_sort_key(actions: Sequence[CountdownAction]) -> tuple[Any, ...]:
    return tuple(action.sort_key() for action in actions)


def _state_sort_key(state: CountdownState) -> tuple[Any, ...]:
    return (-len(state), state)


def _normalization(raw_scores: Sequence[int]) -> tuple[float, ...]:
    if not raw_scores:
        raise ValueError("cannot normalize an empty score vector")
    if any(type(score) is not int or not 0 <= score <= 1000 for score in raw_scores):
        raise ValueError("raw provider scores must be integers in [0, 1000]")
    scaled = [score / 100.0 for score in raw_scores]
    maximum = max(scaled)
    log_denominator = maximum + math.log(
        sum(math.exp(value - maximum) for value in scaled)
    )
    result = tuple(value - log_denominator for value in scaled)
    if any(not math.isfinite(value) for value in result):
        raise AssertionError("normalization produced a non-finite value")
    return result


def _nonterminal_states(task: CountdownTask) -> tuple[CountdownState, ...]:
    seen = {task.initial_state}
    frontier = [task.initial_state]
    while frontier:
        state = frontier.pop()
        if len(state) == 1:
            continue
        for action in task.legal_actions(state):
            child = task.transition(state, action)
            if child not in seen:
                seen.add(child)
                frontier.append(child)
    return tuple(
        sorted((state for state in seen if len(state) > 1), key=_state_sort_key)
    )


def _provider_payload(
    task: CountdownTask,
    state: CountdownState,
    actions: Sequence[CountdownAction],
) -> dict[str, Any]:
    return {
        "legal_actions": [
            {"action_id": action_id, **action.to_dict()}
            for action_id, action in enumerate(actions)
        ],
        "ruleset_id": RULESET_ID,
        "state": list(state),
        "target": task.target,
    }


class ActionScorer(Protocol):
    model: str
    max_tokens: int

    def score_actions(
        self,
        *,
        target: int,
        state: CountdownState,
        legal_actions: Sequence[CountdownAction],
    ) -> AnthropicScoreResult: ...


@dataclass(frozen=True)
class ProposalRow:
    task_fingerprint: str
    state: CountdownState
    actions: tuple[CountdownAction, ...]
    raw_scores: tuple[int, ...]
    prior_logp: tuple[float, ...]
    provider_result: dict[str, Any]

    def behavior_core(self) -> dict[str, Any]:
        return {
            "actions": [action.to_dict() for action in self.actions],
            "normalization_version": NORMALIZATION_VERSION,
            "prior_logp": list(self.prior_logp),
            "raw_scores": list(self.raw_scores),
            "state": list(self.state),
            "task_fingerprint": self.task_fingerprint,
        }

    @property
    def behavior_digest(self) -> str:
        return _sha256_json(self.behavior_core())

    def to_record(self) -> dict[str, Any]:
        payload = {
            "behavior": self.behavior_core(),
            "behavior_digest": self.behavior_digest,
            "provider_result": self.provider_result,
            "schema_version": PROPOSAL_SCHEMA_VERSION,
        }
        return {**payload, "deterministic_digest": _sha256_json(payload)}

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> ProposalRow:
        if record.get("schema_version") != PROPOSAL_SCHEMA_VERSION:
            raise ValueError("unsupported proposal-row schema")
        payload = {
            key: value for key, value in record.items() if key != "deterministic_digest"
        }
        if record.get("deterministic_digest") != _sha256_json(payload):
            raise ValueError("proposal-row digest mismatch")
        behavior = record["behavior"]
        actions = tuple(_action_from_dict(item) for item in behavior["actions"])
        row = cls(
            task_fingerprint=behavior["task_fingerprint"],
            state=tuple(behavior["state"]),
            actions=actions,
            raw_scores=tuple(behavior["raw_scores"]),
            prior_logp=tuple(behavior["prior_logp"]),
            provider_result=dict(record["provider_result"]),
        )
        if behavior.get("normalization_version") != NORMALIZATION_VERSION:
            raise ValueError("proposal normalization version mismatch")
        if row.prior_logp != _normalization(row.raw_scores):
            raise ValueError("stored proposal normalization mismatch")
        if record.get("behavior_digest") != row.behavior_digest:
            raise ValueError("proposal behavior digest mismatch")
        return row


@dataclass(frozen=True)
class ProposalSnapshot:
    rows: tuple[ProposalRow, ...]
    _index: dict[tuple[str, CountdownState], ProposalRow] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        index: dict[tuple[str, CountdownState], ProposalRow] = {}
        for row in self.rows:
            key = (row.task_fingerprint, row.state)
            if key in index:
                raise ValueError("proposal snapshot contains duplicate state identity")
            index[key] = row
        object.__setattr__(self, "_index", index)

    @property
    def behavior_digest(self) -> str:
        return _sha256_json([row.behavior_digest for row in self.rows])

    @property
    def acquisition_digest(self) -> str:
        return _sha256_json(
            [row.to_record()["deterministic_digest"] for row in self.rows]
        )

    def get(self, task: CountdownTask, state: CountdownState) -> ProposalRow:
        try:
            return self._index[(task.task_fingerprint, state)]
        except KeyError as error:
            raise KeyError(f"proposal snapshot misses state {state!r}") from error


@dataclass(frozen=True)
class PhysicalProviderBudget:
    max_requests: int = PHYSICAL_REQUEST_CAP
    max_input_tokens_per_request: int = MAX_INPUT_TOKENS_PER_REQUEST
    max_output_tokens_per_request: int = MAX_OUTPUT_TOKENS
    max_cost_usd: float = PHYSICAL_COST_CAP_USD

    def __post_init__(self) -> None:
        for name in (
            "max_requests",
            "max_input_tokens_per_request",
            "max_output_tokens_per_request",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a non-negative plain integer")
        if (
            type(self.max_cost_usd) not in {int, float}
            or isinstance(self.max_cost_usd, bool)
            or not math.isfinite(float(self.max_cost_usd))
            or self.max_cost_usd < 0
        ):
            raise ValueError("max_cost_usd must be finite and non-negative")

    @property
    def reserve_per_request_usd(self) -> float:
        return (
            self.max_input_tokens_per_request * PRICE_PER_MTOK["base_input"]
            + self.max_output_tokens_per_request * PRICE_PER_MTOK["output"]
        ) / 1_000_000

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_cost_usd": self.max_cost_usd,
            "max_input_tokens_per_request": self.max_input_tokens_per_request,
            "max_output_tokens_per_request": self.max_output_tokens_per_request,
            "max_requests": self.max_requests,
            "reserve_per_request_usd": self.reserve_per_request_usd,
        }


@dataclass
class PhysicalProviderLedger:
    budget: PhysicalProviderBudget
    attempts: int = 0
    responses_returned: int = 0
    successes: int = 0
    failures: int = 0
    reserved_cost_usd: float = 0.0
    actual_cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    latency_ms: float = 0.0
    failure_types: list[str] = field(default_factory=list)

    def reserve(self) -> int:
        next_attempts = self.attempts + 1
        next_reserved = self.reserved_cost_usd + self.budget.reserve_per_request_usd
        if next_attempts > self.budget.max_requests:
            raise RuntimeError("physical provider request cap exhausted")
        if next_reserved > self.budget.max_cost_usd + 1e-12:
            raise RuntimeError("physical provider USD cap exhausted")
        self.attempts = next_attempts
        self.reserved_cost_usd = next_reserved
        return next_attempts

    def record_failure(self, error: BaseException, latency_ms: float) -> None:
        self.failures += 1
        self.latency_ms += latency_ms
        self.failure_types.append(type(error).__name__)

    def record_success(self, result: AnthropicScoreResult, latency_ms: float) -> None:
        self.responses_returned += 1
        self.latency_ms += latency_ms
        tokens = result.metadata["tokens"]
        if tokens.get("input_tokens") is None or tokens.get("output_tokens") is None:
            raise ValueError("provider base input/output token usage is required")
        values = {
            "input_tokens": tokens["input_tokens"],
            "output_tokens": tokens["output_tokens"],
            "cache_creation_input_tokens": (
                0
                if tokens.get("cache_creation_input_tokens") is None
                else tokens["cache_creation_input_tokens"]
            ),
            "cache_read_input_tokens": (
                0
                if tokens.get("cache_read_input_tokens") is None
                else tokens["cache_read_input_tokens"]
            ),
        }
        if any(type(value) is not int or value < 0 for value in values.values()):
            raise ValueError("provider usage contains invalid token counts")
        for name, value in values.items():
            setattr(self, name, getattr(self, name) + value)
        self.actual_cost_usd += (
            values["input_tokens"] * PRICE_PER_MTOK["base_input"]
            + values["output_tokens"] * PRICE_PER_MTOK["output"]
            + values["cache_creation_input_tokens"]
            * PRICE_PER_MTOK["cache_creation_input"]
            + values["cache_read_input_tokens"] * PRICE_PER_MTOK["cache_read_input"]
        ) / 1_000_000
        if values["input_tokens"] > self.budget.max_input_tokens_per_request:
            raise RuntimeError(
                "provider input usage exceeded reserved per-request bound"
            )
        if values["output_tokens"] > self.budget.max_output_tokens_per_request:
            raise RuntimeError(
                "provider output usage exceeded reserved per-request bound"
            )
        if (
            values["cache_creation_input_tokens"] != 0
            or values["cache_read_input_tokens"] != 0
        ):
            raise RuntimeError("unexpected prompt-cache usage was not reserved")
        self.successes += 1

    def record_settlement_failure(self, error: BaseException) -> None:
        self.failures += 1
        self.failure_types.append(type(error).__name__)

    def snapshot(self) -> dict[str, Any]:
        payload = {
            "actual_cost_usd": self.actual_cost_usd,
            "attempts": self.attempts,
            "budget": self.budget.to_dict(),
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
            "failures": self.failures,
            "failure_types": list(self.failure_types),
            "input_tokens": self.input_tokens,
            "latency_ms": self.latency_ms,
            "output_tokens": self.output_tokens,
            "price_per_mtok": dict(PRICE_PER_MTOK),
            "price_retrieved_date": PRICE_RETRIEVED_DATE,
            "price_source": PRICE_SOURCE,
            "responses_returned": self.responses_returned,
            "reserved_cost_usd": self.reserved_cost_usd,
            "successes": self.successes,
        }
        return {**payload, "ledger_digest": _sha256_json(payload)}


class AcquisitionFailure(RuntimeError):
    def __init__(
        self,
        *,
        reason: str,
        task: CountdownTask,
        state: CountdownState,
        ledger: Mapping[str, Any],
        cause_type: str,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.task_fingerprint = task.task_fingerprint
        self.state = state
        self.ledger = dict(ledger)
        self.cause_type = cause_type

    def to_record(self) -> dict[str, Any]:
        payload = {
            "cause_type": self.cause_type,
            "physical_provider_usage": self.ledger,
            "reason": self.reason,
            "schema_version": "qmc-bmgs-countdown-acquisition-failure/v1",
            "state": list(self.state),
            "status": "FAILED_CLOSED",
            "task_fingerprint": self.task_fingerprint,
        }
        return {**payload, "deterministic_digest": _sha256_json(payload)}


def _append_journal_record(path: Path | None, payload: Mapping[str, Any]) -> None:
    if path is None:
        return
    record = dict(payload)
    if "deterministic_digest" not in record:
        record["deterministic_digest"] = _sha256_json(record)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(_canonical_json(record) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _journal_file_evidence(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    payload = path.read_bytes()
    return {
        "bytes": len(payload),
        "records": sum(bool(line) for line in payload.splitlines()),
        "sha256": _sha256_bytes(payload),
    }


def _write_acquisition_checkpoint(
    path: Path | None,
    *,
    status: str,
    ledger: PhysicalProviderLedger,
    attempt_journal_path: Path | None,
    proposal_journal_path: Path | None,
) -> None:
    if path is None:
        return
    payload = {
        "attempt_journal": _journal_file_evidence(attempt_journal_path),
        "physical_provider_usage": ledger.snapshot(),
        "proposal_journal": _journal_file_evidence(proposal_journal_path),
        "schema_version": "qmc-bmgs-countdown-acquisition-checkpoint/v1",
        "status": status,
    }
    _write_json(path, {**payload, "deterministic_digest": _sha256_json(payload)})


def acquire_snapshot(
    scorer: ActionScorer,
    *,
    physical_budget: PhysicalProviderBudget | None = None,
    attempt_journal_path: Path | None = None,
    proposal_journal_path: Path | None = None,
    checkpoint_path: Path | None = None,
) -> tuple[ProposalSnapshot, dict[str, Any]]:
    budget = physical_budget or PhysicalProviderBudget()
    if scorer.model != PINNED_MODEL and not scorer.model.startswith("fake-"):
        raise ValueError("live acquisition requires the pinned model ID")
    if scorer.max_tokens != budget.max_output_tokens_per_request:
        raise ValueError("provider max_tokens must match the physical reservation")
    plan = tuple(
        (task, state, task.legal_actions(state))
        for task in DEV_TASKS
        for state in _nonterminal_states(task)
    )
    if len(plan) != PHYSICAL_REQUEST_CAP:
        raise AssertionError("development fixture proposal coverage drifted")
    if len(plan) > budget.max_requests or (
        len(plan) * budget.reserve_per_request_usd > budget.max_cost_usd + 1e-12
    ):
        raise ValueError(
            "physical provider budget cannot cover the frozen request plan"
        )
    ledger = PhysicalProviderLedger(budget)
    rows: list[ProposalRow] = []
    _write_acquisition_checkpoint(
        checkpoint_path,
        status="IN_PROGRESS",
        ledger=ledger,
        attempt_journal_path=attempt_journal_path,
        proposal_journal_path=proposal_journal_path,
    )
    for task, state, actions in plan:
        planned_payload = _provider_payload(task, state, actions)
        attempt = ledger.reserve()
        _append_journal_record(
            attempt_journal_path,
            {
                "attempt": attempt,
                "event": "REQUEST_RESERVED",
                "physical_provider_usage": ledger.snapshot(),
                "planned_provider_payload": planned_payload,
                "schema_version": "qmc-bmgs-provider-attempt-event/v1",
                "state": list(state),
                "task_fingerprint": task.task_fingerprint,
            },
        )
        _write_acquisition_checkpoint(
            checkpoint_path,
            status="IN_PROGRESS",
            ledger=ledger,
            attempt_journal_path=attempt_journal_path,
            proposal_journal_path=proposal_journal_path,
        )
        started = time.perf_counter()
        try:
            result = scorer.score_actions(
                target=task.target,
                state=state,
                legal_actions=actions,
            )
        except BaseException as error:
            latency_ms = (time.perf_counter() - started) * 1000
            ledger.record_failure(error, latency_ms)
            _append_journal_record(
                attempt_journal_path,
                {
                    "attempt": attempt,
                    "cause_type": type(error).__name__,
                    "event": "TRANSPORT_FAILURE",
                    "physical_provider_usage": ledger.snapshot(),
                    "schema_version": "qmc-bmgs-provider-attempt-event/v1",
                    "state": list(state),
                    "task_fingerprint": task.task_fingerprint,
                },
            )
            _write_acquisition_checkpoint(
                checkpoint_path,
                status="FAILED",
                ledger=ledger,
                attempt_journal_path=attempt_journal_path,
                proposal_journal_path=proposal_journal_path,
            )
            raise AcquisitionFailure(
                reason="provider_transport_or_sdk_error",
                task=task,
                state=state,
                ledger=ledger.snapshot(),
                cause_type=type(error).__name__,
            ) from error
        latency_ms = (time.perf_counter() - started) * 1000
        try:
            ledger.record_success(result, latency_ms)
        except BaseException as error:
            ledger.record_settlement_failure(error)
            _append_journal_record(
                attempt_journal_path,
                {
                    "attempt": attempt,
                    "cause_type": type(error).__name__,
                    "event": "RESPONSE_REJECTED",
                    "latency_ms": latency_ms,
                    "physical_provider_usage": ledger.snapshot(),
                    "provider_result": result.to_dict(),
                    "schema_version": "qmc-bmgs-provider-attempt-event/v1",
                    "state": list(state),
                    "task_fingerprint": task.task_fingerprint,
                },
            )
            _write_acquisition_checkpoint(
                checkpoint_path,
                status="FAILED",
                ledger=ledger,
                attempt_journal_path=attempt_journal_path,
                proposal_journal_path=proposal_journal_path,
            )
            raise AcquisitionFailure(
                reason="provider_usage_settlement_error",
                task=task,
                state=state,
                ledger=ledger.snapshot(),
                cause_type=type(error).__name__,
            ) from error
        _append_journal_record(
            attempt_journal_path,
            {
                "attempt": attempt,
                "event": "RESPONSE_RECEIVED",
                "latency_ms": latency_ms,
                "physical_provider_usage": ledger.snapshot(),
                "provider_result": result.to_dict(),
                "schema_version": "qmc-bmgs-provider-attempt-event/v1",
                "state": list(state),
                "task_fingerprint": task.task_fingerprint,
            },
        )

        def validation_failure(reason: str, cause_type: str) -> AcquisitionFailure:
            _append_journal_record(
                attempt_journal_path,
                {
                    "attempt": attempt,
                    "cause_type": cause_type,
                    "event": "VALIDATION_REJECTED",
                    "physical_provider_usage": ledger.snapshot(),
                    "reason": reason,
                    "schema_version": "qmc-bmgs-provider-attempt-event/v1",
                    "state": list(state),
                    "task_fingerprint": task.task_fingerprint,
                },
            )
            _write_acquisition_checkpoint(
                checkpoint_path,
                status="FAILED",
                ledger=ledger,
                attempt_journal_path=attempt_journal_path,
                proposal_journal_path=proposal_journal_path,
            )
            return AcquisitionFailure(
                reason=reason,
                task=task,
                state=state,
                ledger=ledger.snapshot(),
                cause_type=cause_type,
            )

        if result.recovered:
            raise validation_failure(
                "provider_response_failed_strict_validation",
                str(result.metadata["response_validation"]["recovery_reason"]),
            )
        if result.metadata["model_returned"] != scorer.model:
            raise validation_failure(
                "provider_model_identity_mismatch", "ModelIdentityMismatch"
            )
        provider_payload = result.metadata["provider_payload"]
        if set(provider_payload) != {
            "legal_actions",
            "ruleset_id",
            "state",
            "target",
        }:
            raise validation_failure(
                "provider_payload_allowlist_violation",
                "PayloadAllowlistViolation",
            )
        if provider_payload != planned_payload:
            raise validation_failure(
                "provider_payload_identity_mismatch", "PayloadIdentityMismatch"
            )
        scored_actions = tuple(item.action for item in result.scored_actions)
        if scored_actions != actions:
            raise validation_failure(
                "provider_action_identity_mismatch", "ActionIdentityMismatch"
            )
        raw_scores = tuple(item.score for item in result.scored_actions)
        row = ProposalRow(
            task_fingerprint=task.task_fingerprint,
            state=state,
            actions=actions,
            raw_scores=raw_scores,
            prior_logp=_normalization(raw_scores),
            provider_result=result.to_dict(),
        )
        rows.append(row)
        _append_journal_record(proposal_journal_path, row.to_record())
        _write_acquisition_checkpoint(
            checkpoint_path,
            status="IN_PROGRESS",
            ledger=ledger,
            attempt_journal_path=attempt_journal_path,
            proposal_journal_path=proposal_journal_path,
        )
    expected_rows = len(plan)
    if len(rows) != expected_rows:
        raise AssertionError("development fixture proposal coverage drifted")
    if ledger.attempts != expected_rows or ledger.successes != expected_rows:
        raise AssertionError("physical acquisition ledger did not close")
    _write_acquisition_checkpoint(
        checkpoint_path,
        status="COMPLETE",
        ledger=ledger,
        attempt_journal_path=attempt_journal_path,
        proposal_journal_path=proposal_journal_path,
    )
    return ProposalSnapshot(tuple(rows)), ledger.snapshot()


class _FakeMessages:
    def __init__(self) -> None:
        self.api_key = FAKE_SECRET
        self.calls = 0

    def create(self, **request: Any) -> Any:
        self.calls += 1
        payload = _strict_json_text(request["messages"][0]["content"])
        state = tuple(payload["state"])
        target = payload["target"]
        scores: list[dict[str, int]] = []
        for item in reversed(payload["legal_actions"]):
            action = CountdownAction(item["left"], item["right"], item["operator"])
            result = action.evaluate()
            remainder = list(state)
            remainder.remove(action.left)
            remainder.remove(action.right)
            remainder.append(result)
            distance = min(abs(value - target) for value in remainder)
            score = max(0, 1000 - min(1000, distance * 40))
            if result == target:
                score = 1000
            scores.append({"action_id": item["action_id"], "score": score})
        text = _canonical_json({"scores": scores})
        request_digest = _sha256_json(request)
        return SimpleNamespace(
            id=f"fake_{self.calls:03d}_{request_digest[:12]}",
            model=request["model"],
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text=text)],
            usage=SimpleNamespace(
                input_tokens=max(1, len(request["messages"][0]["content"]) // 4),
                output_tokens=max(1, len(text) // 4),
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0,
            ),
        )


class _FakeClient:
    def __init__(self) -> None:
        self.messages = _FakeMessages()
        self.api_key = FAKE_SECRET


class _FailingScorer:
    model = "fake-failure"
    max_tokens = MAX_OUTPUT_TOKENS

    def score_actions(
        self,
        *,
        target: int,
        state: CountdownState,
        legal_actions: Sequence[CountdownAction],
    ) -> AnthropicScoreResult:
        del target, state, legal_actions
        raise RuntimeError("synthetic_transport_failure")


class _FailAfterNScorer:
    model = "fake-haiku"
    max_tokens = MAX_OUTPUT_TOKENS

    def __init__(self, successful_calls: int) -> None:
        self.successful_calls = successful_calls
        self.calls = 0
        self.delegate = AnthropicCountdownScorer(
            _FakeClient(),
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=0.0,
        )

    def score_actions(
        self,
        *,
        target: int,
        state: CountdownState,
        legal_actions: Sequence[CountdownAction],
    ) -> AnthropicScoreResult:
        if self.calls >= self.successful_calls:
            raise RuntimeError("synthetic_failure_after_successes")
        self.calls += 1
        return self.delegate.score_actions(
            target=target,
            state=state,
            legal_actions=legal_actions,
        )


class _OverBoundUsageScorer(_FailAfterNScorer):
    def __init__(self) -> None:
        super().__init__(successful_calls=PHYSICAL_REQUEST_CAP)

    def score_actions(
        self,
        *,
        target: int,
        state: CountdownState,
        legal_actions: Sequence[CountdownAction],
    ) -> AnthropicScoreResult:
        result = super().score_actions(
            target=target,
            state=state,
            legal_actions=legal_actions,
        )
        result.metadata["tokens"]["input_tokens"] = MAX_INPUT_TOKENS_PER_REQUEST + 1
        return result


class CounterRNG:
    def __init__(self, *, seed: int, stream: str) -> None:
        if type(seed) is not int or seed < 0:
            raise ValueError("seed must be a non-negative plain integer")
        self.seed = seed
        self.stream = stream
        self.counter = 0

    def uniform(self) -> float:
        payload = f"{RNG_VERSION}|{self.seed}|{self.stream}|{self.counter}".encode()
        self.counter += 1
        integer = int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")
        return (integer + 0.5) / (1 << 64)

    def normal(self) -> float:
        first = max(self.uniform(), 1e-15)
        second = self.uniform()
        return math.sqrt(-2.0 * math.log(first)) * math.cos(2.0 * math.pi * second)


@dataclass
class _NodeStats:
    visits: list[int]
    means: list[float]
    m2: list[float]

    @classmethod
    def create(cls, action_count: int) -> _NodeStats:
        return cls([0] * action_count, [0.0] * action_count, [0.0] * action_count)

    def update(self, action_index: int, value: float) -> None:
        self.visits[action_index] += 1
        count = self.visits[action_index]
        delta = value - self.means[action_index]
        self.means[action_index] += delta / count
        self.m2[action_index] += delta * (value - self.means[action_index])


class SearchStopped(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class SearchContext:
    task: CountdownTask
    snapshot: ProposalSnapshot
    method: str
    seed: int
    ledger: ComputeLedger = field(init=False)
    rng: CounterRNG = field(init=False)
    local_cache: dict[CountdownState, ProposalRow] = field(default_factory=dict)
    proposal_events: list[dict[str, Any]] = field(default_factory=list)
    selection_events: list[dict[str, Any]] = field(default_factory=list)
    terminals: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.ledger = ComputeLedger(SEARCH_BUDGET)
        self.rng = CounterRNG(seed=self.seed, stream=self.method)

    def proposal(self, state: CountdownState) -> ProposalRow:
        state = self.task.canonical_state(state)
        state_key = self.task.state_key(state)
        if state in self.local_cache:
            self.ledger.record_cache_lookup(state_key, hit=True)
            self.proposal_events.append(
                {
                    "action_scores": 0,
                    "batch_calls": 0,
                    "event": "proposal_lookup",
                    "hit": True,
                    "input_values": 0,
                    "state": list(state),
                    "state_items": 0,
                }
            )
            return self.local_cache[state]
        expected_actions = self.task.legal_actions(state)
        row = self.snapshot.get(self.task, state)
        if row.actions != expected_actions:
            raise AssertionError("snapshot action set drifted from task adapter")
        try:
            self.ledger.charge(
                proposal_batch_calls=1,
                proposal_state_items=1,
                proposal_input_values=len(state) + 1,
                proposal_action_scores=len(expected_actions),
            )
        except BudgetExceeded as error:
            raise SearchStopped(
                f"proposal_budget:{','.join(error.blocked_axes)}"
            ) from error
        self.local_cache[state] = row
        self.ledger.record_cache_lookup(state_key, hit=False)
        self.proposal_events.append(
            {
                "action_scores": len(expected_actions),
                "batch_calls": 1,
                "event": "proposal_lookup",
                "hit": False,
                "input_values": len(state) + 1,
                "state": list(state),
                "state_items": 1,
            }
        )
        return row

    def charge_selection_and_edge(self, row: ProposalRow) -> None:
        try:
            self.ledger.charge(
                selection_action_scores=len(row.actions),
                edge_selections=1,
                transitions=1,
            )
        except BudgetExceeded as error:
            raise SearchStopped(
                f"edge_budget:{','.join(error.blocked_axes)}"
            ) from error

    def charge_frontier_expansion(self, row: ProposalRow) -> None:
        try:
            self.ledger.charge(selection_action_scores=len(row.actions))
        except BudgetExceeded as error:
            raise SearchStopped(
                f"selection_budget:{','.join(error.blocked_axes)}"
            ) from error
        self.selection_events.append(
            {
                "event": "frontier_expand",
                "selection_action_scores": len(row.actions),
                "state": list(row.state),
            }
        )

    def charge_frontier_edge(self) -> None:
        try:
            self.ledger.charge(edge_selections=1, transitions=1)
        except BudgetExceeded as error:
            raise SearchStopped(
                f"edge_budget:{','.join(error.blocked_axes)}"
            ) from error

    def transition(
        self,
        *,
        state: CountdownState,
        row: ProposalRow,
        action_index: int,
        details: Mapping[str, Any],
        selection_scores_charged: int,
    ) -> CountdownState:
        action = row.actions[action_index]
        child = self.task.transition(state, action)
        self.selection_events.append(
            {
                "action": action.to_dict(),
                "action_index": action_index,
                "child": list(child),
                "details": dict(details),
                "event": "edge_transition",
                "prior_logp": row.prior_logp[action_index],
                "selection_action_scores": selection_scores_charged,
                "state": list(state),
            }
        )
        return child

    def verify_terminal(
        self,
        *,
        actions: Sequence[CountdownAction],
        states: Sequence[CountdownState],
        cumulative_prior_logp: float,
    ) -> bool:
        try:
            self.ledger.charge(verifier_calls=1)
        except BudgetExceeded as error:
            raise SearchStopped(
                f"verifier_budget:{','.join(error.blocked_axes)}"
            ) from error
        verification = self.task.verify(actions)
        terminal = {
            "actions": [action.to_dict() for action in actions],
            "cumulative_prior_logp": cumulative_prior_logp,
            "observation_index": len(self.terminals),
            "states": [list(state) for state in states],
            "verification": {
                "final_value": verification.final_value,
                "reason": verification.reason,
                "source_use_exact": verification.source_use_exact,
                "success": verification.success,
            },
        }
        self.terminals.append(terminal)
        return verification.success

    def readout(self) -> dict[str, Any] | None:
        self.ledger.record_evaluation_only_call(cache_only=True)
        if not self.terminals:
            return None
        exact = [row for row in self.terminals if row["verification"]["success"]]
        if exact:
            selected = min(exact, key=lambda row: row["observation_index"])
            reason = "first_exact_terminal"
        else:
            selected = min(
                self.terminals,
                key=lambda row: (
                    -row["cumulative_prior_logp"],
                    _trace_sort_key(
                        tuple(_action_from_dict(item) for item in row["actions"])
                    ),
                ),
            )
            reason = "highest_prior_verified_terminal"
        return {
            "observation_index": selected["observation_index"],
            "reason": reason,
            "success": selected["verification"]["success"],
        }


def _select_greedy(row: ProposalRow) -> int:
    return max(range(len(row.actions)), key=lambda index: row.prior_logp[index])


def _top_p_indices(row: ProposalRow) -> tuple[int, ...]:
    ordered = sorted(
        range(len(row.actions)),
        key=lambda index: (
            -math.exp(row.prior_logp[index]),
            row.actions[index].sort_key(),
        ),
    )
    selected: list[int] = []
    cumulative = 0.0
    for index in ordered:
        selected.append(index)
        cumulative += math.exp(row.prior_logp[index])
        if cumulative >= TOP_P:
            break
    return tuple(selected)


def _sample_nucleus(row: ProposalRow, nucleus: Sequence[int], draw: float) -> int:
    total = sum(math.exp(row.prior_logp[index]) for index in nucleus)
    threshold = draw * total
    cumulative = 0.0
    for index in nucleus:
        cumulative += math.exp(row.prior_logp[index])
        if threshold <= cumulative:
            return index
    return nucleus[-1]


def _run_greedy(context: SearchContext) -> tuple[str, dict[str, Any]]:
    state = context.task.initial_state
    actions: list[CountdownAction] = []
    states = [state]
    cumulative = 0.0
    try:
        while len(state) > 1:
            row = context.proposal(state)
            context.charge_selection_and_edge(row)
            action_index = _select_greedy(row)
            child = context.transition(
                state=state,
                row=row,
                action_index=action_index,
                details={"policy": "max_prior"},
                selection_scores_charged=len(row.actions),
            )
            actions.append(row.actions[action_index])
            states.append(child)
            cumulative += row.prior_logp[action_index]
            state = child
        context.verify_terminal(
            actions=actions,
            states=states,
            cumulative_prior_logp=cumulative,
        )
    except SearchStopped as error:
        return error.reason, {}
    return "completed_anchor", {}


def _run_top_p(context: SearchContext) -> tuple[str, dict[str, Any]]:
    completed = 0
    try:
        for rollout in range(ROLLOUTS):
            state = context.task.initial_state
            actions: list[CountdownAction] = []
            states = [state]
            cumulative = 0.0
            while len(state) > 1:
                row = context.proposal(state)
                nucleus = _top_p_indices(row)
                context.charge_selection_and_edge(row)
                draw = context.rng.uniform()
                action_index = _sample_nucleus(row, nucleus, draw)
                child = context.transition(
                    state=state,
                    row=row,
                    action_index=action_index,
                    details={
                        "draw": draw,
                        "nucleus_action_indices": list(nucleus),
                        "policy": "top_p",
                        "rollout": rollout,
                        "top_p": TOP_P,
                    },
                    selection_scores_charged=len(row.actions),
                )
                actions.append(row.actions[action_index])
                states.append(child)
                cumulative += row.prior_logp[action_index]
                state = child
            context.verify_terminal(
                actions=actions,
                states=states,
                cumulative_prior_logp=cumulative,
            )
            completed += 1
    except SearchStopped as error:
        return error.reason, {"completed_rollouts": completed}
    return "completed_rollouts", {"completed_rollouts": completed}


def _run_thompson(context: SearchContext) -> tuple[str, dict[str, Any]]:
    stats: dict[CountdownState, _NodeStats] = {}
    completed = 0
    try:
        for simulation in range(THOMPSON_SIMULATIONS):
            state = context.task.initial_state
            actions: list[CountdownAction] = []
            states = [state]
            cumulative = 0.0
            path: list[tuple[CountdownState, int]] = []
            while len(state) > 1:
                row = context.proposal(state)
                node = stats.setdefault(state, _NodeStats.create(len(row.actions)))
                context.charge_selection_and_edge(row)
                samples: list[float] = []
                for index in range(len(row.actions)):
                    posterior_sd = 1.0 / math.sqrt(node.visits[index] + 1)
                    samples.append(
                        node.means[index]
                        + THOMPSON_PRIOR_BONUS * math.exp(row.prior_logp[index])
                        + posterior_sd * context.rng.normal()
                    )
                action_index = max(
                    range(len(samples)), key=lambda index: samples[index]
                )
                child = context.transition(
                    state=state,
                    row=row,
                    action_index=action_index,
                    details={
                        "policy": "iid_thompson",
                        "sampled_indices": samples,
                        "simulation": simulation,
                        "visits_before": list(node.visits),
                    },
                    selection_scores_charged=len(row.actions),
                )
                actions.append(row.actions[action_index])
                states.append(child)
                path.append((state, action_index))
                cumulative += row.prior_logp[action_index]
                state = child
            success = context.verify_terminal(
                actions=actions,
                states=states,
                cumulative_prior_logp=cumulative,
            )
            value = 1.0 if success else 0.0
            for visited_state, action_index in reversed(path):
                stats[visited_state].update(action_index, value)
            completed += 1
    except SearchStopped as error:
        stop_reason = error.reason
    else:
        stop_reason = "completed_simulations"
    stats_payload = {
        _canonical_json(list(state)): {
            "m2": node.m2,
            "means": node.means,
            "visits": node.visits,
        }
        for state, node in sorted(
            stats.items(), key=lambda item: _state_sort_key(item[0])
        )
    }
    return stop_reason, {
        "completed_simulations": completed,
        "posterior_state_digest": _sha256_json(stats_payload),
    }


@dataclass(frozen=True)
class _FrontierItem:
    cumulative_prior_logp: float
    parent_state: CountdownState
    action_index: int
    actions: tuple[CountdownAction, ...]
    states: tuple[CountdownState, ...]
    trace_key: tuple[Any, ...]


def _run_best_first(context: SearchContext) -> tuple[str, dict[str, Any]]:
    frontier: list[tuple[Any, ...]] = []
    push_counter = 0
    expanded: set[CountdownState] = set()

    def expand(
        state: CountdownState,
        actions: tuple[CountdownAction, ...],
        states: tuple[CountdownState, ...],
        cumulative: float,
    ) -> None:
        nonlocal push_counter
        row = context.proposal(state)
        context.charge_frontier_expansion(row)
        expanded.add(state)
        for action_index, action in enumerate(row.actions):
            next_actions = actions + (action,)
            next_score = cumulative + row.prior_logp[action_index]
            item = _FrontierItem(
                cumulative_prior_logp=next_score,
                parent_state=state,
                action_index=action_index,
                actions=next_actions,
                states=states,
                trace_key=_trace_sort_key(next_actions),
            )
            heapq.heappush(
                frontier,
                (-next_score, item.trace_key, push_counter, item),
            )
            push_counter += 1

    completed = 0
    duplicate_state_edges = 0
    try:
        expand(context.task.initial_state, (), (context.task.initial_state,), 0.0)
        while frontier and completed < BEST_FIRST_TERMINALS:
            _, _, _, item = heapq.heappop(frontier)
            context.charge_frontier_edge()
            row = context.snapshot.get(context.task, item.parent_state)
            child = context.transition(
                state=item.parent_state,
                row=row,
                action_index=item.action_index,
                details={
                    "frontier_size_after_pop": len(frontier),
                    "policy": "best_first",
                },
                selection_scores_charged=0,
            )
            next_states = item.states + (child,)
            if len(child) == 1:
                context.verify_terminal(
                    actions=item.actions,
                    states=next_states,
                    cumulative_prior_logp=item.cumulative_prior_logp,
                )
                completed += 1
            elif child in expanded:
                duplicate_state_edges += 1
            else:
                expand(
                    child,
                    item.actions,
                    next_states,
                    item.cumulative_prior_logp,
                )
    except SearchStopped as error:
        stop_reason = error.reason
    else:
        stop_reason = (
            "completed_terminals"
            if completed == BEST_FIRST_TERMINALS
            else "frontier_empty"
        )
    return stop_reason, {
        "completed_terminals": completed,
        "duplicate_state_edges": duplicate_state_edges,
        "expanded_state_count": len(expanded),
    }


def _method_config(method: str) -> dict[str, Any]:
    common = {
        "exact_terminal_reward": "1_or_0",
        "pruning": False,
        "shaped_reward": False,
    }
    if method == "greedy":
        return {**common, "role": "low_cost_anchor", "traces": 1}
    if method == "top_p_best_of_8":
        return {**common, "rollouts": ROLLOUTS, "top_p": TOP_P}
    if method == "iid_thompson_8":
        return {
            **common,
            "gamma": 1.0,
            "observation_variance_floor": 1.0,
            "prior_bonus": THOMPSON_PRIOR_BONUS,
            "simulations": THOMPSON_SIMULATIONS,
        }
    if method == "best_first_8":
        return {
            **common,
            "priority": "cumulative_prior_logp",
            "terminal_cap": BEST_FIRST_TERMINALS,
        }
    raise ValueError(f"unknown method: {method}")


def run_search(
    task: CountdownTask,
    snapshot: ProposalSnapshot,
    *,
    method: str,
    seed: int,
) -> dict[str, Any]:
    context = SearchContext(task, snapshot, method, seed)
    if method == "greedy":
        stop_reason, method_state = _run_greedy(context)
    elif method == "top_p_best_of_8":
        stop_reason, method_state = _run_top_p(context)
    elif method == "iid_thompson_8":
        stop_reason, method_state = _run_thompson(context)
    elif method == "best_first_8":
        stop_reason, method_state = _run_best_first(context)
    else:
        raise ValueError(f"unknown method: {method}")
    readout = context.readout()
    payload = {
        "budget": SEARCH_BUDGET.to_dict(),
        "claim_role": "provider_and_search_plumbing_only",
        "exact_success_any": any(
            terminal["verification"]["success"] for terminal in context.terminals
        ),
        "method": method,
        "method_config": _method_config(method),
        "method_state": method_state,
        "proposal_behavior_digest": snapshot.behavior_digest,
        "proposal_events": context.proposal_events,
        "readout": readout,
        "rng": {
            "draw_count": context.rng.counter,
            "seed": seed,
            "version": RNG_VERSION,
        },
        "schema_version": RECORD_SCHEMA_VERSION,
        "seed": seed,
        "selection_events": context.selection_events,
        "stop_reason": stop_reason,
        "task": task.to_dict(),
        "terminals": context.terminals,
        "usage": context.ledger.snapshot(),
    }
    return {**payload, "deterministic_digest": canonical_record_digest(payload)}


def run_all_searches(snapshot: ProposalSnapshot) -> tuple[dict[str, Any], ...]:
    records: list[dict[str, Any]] = []
    for task in DEV_TASKS:
        records.append(run_search(task, snapshot, method="greedy", seed=0))
        records.append(run_search(task, snapshot, method="best_first_8", seed=0))
        for seed in DEV_SEEDS:
            records.append(
                run_search(task, snapshot, method="top_p_best_of_8", seed=seed)
            )
            records.append(
                run_search(task, snapshot, method="iid_thompson_8", seed=seed)
            )
    return tuple(records)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(_pretty_json(payload) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _write_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.write_text(
        "".join(_canonical_json(record) + "\n" for record in records),
        encoding="utf-8",
    )


def _read_jsonl(path: Path) -> tuple[dict[str, Any], ...]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line:
            continue
        record = _strict_json_text(line)
        if not isinstance(record, dict):
            raise ValueError(f"non-object JSONL record at {path}:{line_number}")
        records.append(record)
    return tuple(records)


def _file_metadata(path: Path, *, records: int | None = None) -> dict[str, Any]:
    payload = path.read_bytes()
    result: dict[str, Any] = {
        "bytes": len(payload),
        "sha256": _sha256_bytes(payload),
    }
    if records is not None:
        result["records"] = records
    return result


def _ensure_empty_output_dir(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    if any(output_dir.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output_dir}")
    probe = output_dir / ".qmc_bmgs_write_probe"
    with probe.open("x", encoding="utf-8") as handle:
        handle.write("writeable\n")
        handle.flush()
        os.fsync(handle.fileno())
    probe.unlink()


def _summary(
    snapshot: ProposalSnapshot,
    physical_usage: Mapping[str, Any],
    search_records: Sequence[Mapping[str, Any]],
    *,
    provider_mode: str,
) -> dict[str, Any]:
    method_rows: dict[str, list[Mapping[str, Any]]] = {}
    for record in search_records:
        method_rows.setdefault(record["method"], []).append(record)
    aggregate = {
        method: {
            "exact_success_rows": sum(bool(row["exact_success_any"]) for row in rows),
            "rows": len(rows),
            "total_verifier_calls": sum(
                row["usage"]["usage"]["verifier_calls"] for row in rows
            ),
        }
        for method, rows in sorted(method_rows.items())
    }
    payload = {
        "claim_boundary": {
            "effectiveness_comparison": False,
            "matched_compute_superiority": False,
            "provider_and_replay_plumbing": True,
            "qmc_included": False,
        },
        "data_quality": {"status": "PENDING_VALIDATION"},
        "dev_fixture": {
            "nonterminal_state_count": len(snapshot.rows),
            "task_count": len(DEV_TASKS),
            "tasks": [task.to_dict() for task in DEV_TASKS],
        },
        "method_aggregate_descriptive_only": aggregate,
        "physical_provider_usage": dict(physical_usage),
        "proposal_acquisition_digest": snapshot.acquisition_digest,
        "proposal_behavior_digest": snapshot.behavior_digest,
        "provider": {
            "adapter_schema_version": ADAPTER_SCHEMA_VERSION,
            "api_endpoint": API_ENDPOINT,
            "api_version": API_VERSION,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "model": PINNED_MODEL if provider_mode == "live" else "fake-haiku",
            "mode": provider_mode,
            "normalization_version": NORMALIZATION_VERSION,
            "sdk_version_required": PINNED_SDK_VERSION,
            "system_instruction_digest": _sha256_bytes(
                SYSTEM_INSTRUCTION.encode("utf-8")
            ),
        },
        "record_count": len(search_records),
        "schema_version": SUMMARY_SCHEMA_VERSION,
    }
    return {**payload, "deterministic_digest": _sha256_json(payload)}


def write_artifact(
    output_dir: Path,
    snapshot: ProposalSnapshot,
    physical_usage: Mapping[str, Any],
    search_records: Sequence[Mapping[str, Any]],
    *,
    provider_mode: str,
) -> None:
    proposal_path = output_dir / "proposal_rows.jsonl"
    records_path = output_dir / "search_records.jsonl"
    summary_path = output_dir / "summary.json"
    manifest_path = output_dir / "manifest.json"
    attempts_path = output_dir / "provider_attempts.jsonl"
    checkpoint_path = output_dir / "acquisition_checkpoint.json"
    proposal_records = [row.to_record() for row in snapshot.rows]
    _write_jsonl(proposal_path, proposal_records)
    _write_jsonl(records_path, search_records)
    summary = _summary(
        snapshot,
        physical_usage,
        search_records,
        provider_mode=provider_mode,
    )
    _write_json(summary_path, summary)
    manifest = {
        "artifact_role": "scratch_provider_plumbing_not_promoted_evidence",
        "files": {
            "acquisition_checkpoint.json": _file_metadata(checkpoint_path),
            "proposal_rows.jsonl": _file_metadata(
                proposal_path, records=len(proposal_records)
            ),
            "provider_attempts.jsonl": _file_metadata(
                attempts_path, records=len(_read_jsonl(attempts_path))
            ),
            "search_records.jsonl": _file_metadata(
                records_path, records=len(search_records)
            ),
            "summary.json": _file_metadata(summary_path),
        },
        "provider_mode": provider_mode,
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "status": "COMPLETE",
    }
    _write_json(manifest_path, manifest)


def _write_failure_manifest(output_dir: Path, *, provider_mode: str) -> None:
    files: dict[str, dict[str, Any]] = {}
    for filename in (
        "acquisition_checkpoint.json",
        "acquisition_failure.json",
        "proposal_rows.jsonl",
        "provider_attempts.jsonl",
    ):
        path = output_dir / filename
        if path.exists():
            records = len(_read_jsonl(path)) if path.suffix == ".jsonl" else None
            files[filename] = _file_metadata(path, records=records)
    _write_json(
        output_dir / "manifest.json",
        {
            "artifact_role": "scratch_provider_plumbing_not_promoted_evidence",
            "files": files,
            "provider_mode": provider_mode,
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "status": "FAILED_CLOSED",
        },
    )


def load_snapshot(path: Path) -> ProposalSnapshot:
    records = _read_jsonl(path)
    rows = tuple(ProposalRow.from_record(record) for record in records)
    return ProposalSnapshot(rows)


def _validate_physical_ledger(
    ledger: Mapping[str, Any], *, require_complete: bool
) -> None:
    payload = {key: value for key, value in ledger.items() if key != "ledger_digest"}
    if ledger.get("ledger_digest") != _sha256_json(payload):
        raise AssertionError("physical provider ledger digest mismatch")
    if ledger["budget"] != PhysicalProviderBudget().to_dict():
        raise AssertionError("physical provider budget identity mismatch")
    if (
        ledger["price_per_mtok"] != PRICE_PER_MTOK
        or ledger["price_retrieved_date"] != PRICE_RETRIEVED_DATE
        or ledger["price_source"] != PRICE_SOURCE
    ):
        raise AssertionError("physical provider price identity mismatch")
    integer_fields = (
        "attempts",
        "responses_returned",
        "successes",
        "failures",
        "input_tokens",
        "output_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
    )
    if any(
        type(ledger[name]) is not int or ledger[name] < 0 for name in integer_fields
    ):
        raise AssertionError("physical provider ledger contains invalid counters")
    if (
        ledger["responses_returned"] > ledger["attempts"]
        or ledger["successes"] > ledger["responses_returned"]
        or ledger["successes"] + ledger["failures"] > ledger["attempts"]
        or not math.isfinite(ledger["latency_ms"])
        or ledger["latency_ms"] < 0
        or not isinstance(ledger["failure_types"], list)
    ):
        raise AssertionError("physical provider ledger lifecycle is inconsistent")
    expected_reserved = ledger["attempts"] * ledger["budget"]["reserve_per_request_usd"]
    expected_actual = (
        ledger["input_tokens"] * PRICE_PER_MTOK["base_input"]
        + ledger["output_tokens"] * PRICE_PER_MTOK["output"]
        + ledger["cache_creation_input_tokens"] * PRICE_PER_MTOK["cache_creation_input"]
        + ledger["cache_read_input_tokens"] * PRICE_PER_MTOK["cache_read_input"]
    ) / 1_000_000
    if not math.isclose(
        ledger["reserved_cost_usd"],
        expected_reserved,
        rel_tol=0.0,
        abs_tol=1e-12,
    ) or not math.isclose(
        ledger["actual_cost_usd"],
        expected_actual,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise AssertionError("physical provider cost formula does not close")
    if (
        ledger["reserved_cost_usd"] > ledger["budget"]["max_cost_usd"] + 1e-12
        or ledger["actual_cost_usd"] > ledger["reserved_cost_usd"] + 1e-12
    ):
        raise AssertionError("physical provider cost exceeded its reservation")
    if require_complete and (
        ledger["attempts"] != PHYSICAL_REQUEST_CAP
        or ledger["responses_returned"] != PHYSICAL_REQUEST_CAP
        or ledger["successes"] != PHYSICAL_REQUEST_CAP
        or ledger["failures"] != 0
        or ledger["failure_types"]
        or ledger["cache_creation_input_tokens"] != 0
        or ledger["cache_read_input_tokens"] != 0
    ):
        raise AssertionError("physical provider budget did not close")


def _validate_acquisition_journals(
    artifact_dir: Path,
    snapshot: ProposalSnapshot,
    physical_usage: Mapping[str, Any],
) -> None:
    attempts_path = artifact_dir / "provider_attempts.jsonl"
    proposal_path = artifact_dir / "proposal_rows.jsonl"
    events = _read_jsonl(attempts_path)
    if len(events) != PHYSICAL_REQUEST_CAP * 2:
        raise AssertionError("provider attempt journal has incomplete coverage")
    task_by_fingerprint = {task.task_fingerprint: task for task in DEV_TASKS}
    for offset, row in enumerate(snapshot.rows):
        request_event = events[offset * 2]
        response_event = events[offset * 2 + 1]
        for event in (request_event, response_event):
            digest_payload = {
                key: value
                for key, value in event.items()
                if key != "deterministic_digest"
            }
            if event.get("deterministic_digest") != _sha256_json(digest_payload):
                raise AssertionError("provider attempt event digest mismatch")
            if (
                event.get("schema_version") != "qmc-bmgs-provider-attempt-event/v1"
                or event.get("attempt") != offset + 1
                or event.get("task_fingerprint") != row.task_fingerprint
                or event.get("state") != list(row.state)
            ):
                raise AssertionError("provider attempt event identity mismatch")
            _validate_physical_ledger(
                event["physical_provider_usage"], require_complete=False
            )
        task = task_by_fingerprint[row.task_fingerprint]
        if (
            request_event.get("event") != "REQUEST_RESERVED"
            or request_event.get("planned_provider_payload")
            != _provider_payload(task, row.state, row.actions)
            or request_event["physical_provider_usage"]["attempts"] != offset + 1
            or request_event["physical_provider_usage"]["responses_returned"] != offset
        ):
            raise AssertionError("provider request reservation journal mismatch")
        if (
            response_event.get("event") != "RESPONSE_RECEIVED"
            or response_event.get("provider_result") != row.provider_result
            or response_event["physical_provider_usage"]["attempts"] != offset + 1
            or response_event["physical_provider_usage"]["responses_returned"]
            != offset + 1
            or response_event["physical_provider_usage"]["successes"] != offset + 1
            or type(response_event.get("latency_ms")) not in {int, float}
            or not math.isfinite(response_event["latency_ms"])
            or response_event["latency_ms"] < 0
        ):
            raise AssertionError("provider response journal mismatch")
    if events[-1]["physical_provider_usage"] != physical_usage:
        raise AssertionError("provider journal final ledger mismatch")

    checkpoint = _strict_json_file(artifact_dir / "acquisition_checkpoint.json")
    checkpoint_payload = {
        key: value for key, value in checkpoint.items() if key != "deterministic_digest"
    }
    if (
        checkpoint.get("deterministic_digest") != _sha256_json(checkpoint_payload)
        or checkpoint.get("status") != "COMPLETE"
        or checkpoint.get("physical_provider_usage") != physical_usage
        or checkpoint.get("attempt_journal") != _journal_file_evidence(attempts_path)
        or checkpoint.get("proposal_journal") != _journal_file_evidence(proposal_path)
    ):
        raise AssertionError("acquisition checkpoint does not close")


def _validate_search_record(
    record: Mapping[str, Any], snapshot: ProposalSnapshot
) -> None:
    if record.get("schema_version") != RECORD_SCHEMA_VERSION:
        raise AssertionError("unsupported search-record schema")
    if record.get("deterministic_digest") != canonical_record_digest(dict(record)):
        raise AssertionError("search-record digest mismatch")
    task_payload = record["task"]
    task = CountdownTask(tuple(task_payload["inputs"]), task_payload["target"])
    if task_payload != task.to_dict():
        raise AssertionError("search-record task identity mismatch")
    if record["proposal_behavior_digest"] != snapshot.behavior_digest:
        raise AssertionError("search-record proposal snapshot mismatch")
    if record["budget"] != SEARCH_BUDGET.to_dict():
        raise AssertionError("search-record budget identity mismatch")
    usage = record["usage"]
    if usage["overshoot"] != 0 or usage["limits"] != SEARCH_BUDGET.to_dict():
        raise AssertionError("search budget integrity failure")
    if any(usage["usage"][axis] > usage["limits"][axis] for axis in COMPUTE_AXES):
        raise AssertionError("search usage exceeded a hard guard")

    cached_states: set[CountdownState] = set()
    proposal_usage = {
        "proposal_action_scores": 0,
        "proposal_batch_calls": 0,
        "proposal_input_values": 0,
        "proposal_state_items": 0,
    }
    cache_hits = 0
    cache_misses = 0
    for event in record["proposal_events"]:
        if (
            set(event)
            != {
                "action_scores",
                "batch_calls",
                "event",
                "hit",
                "input_values",
                "state",
                "state_items",
            }
            or event["event"] != "proposal_lookup"
        ):
            raise AssertionError("invalid proposal lookup event")
        state = task.canonical_state(event["state"])
        if list(state) != event["state"] or len(state) <= 1:
            raise AssertionError("proposal event state is not canonical nonterminal")
        row = snapshot.get(task, state)
        expected_hit = state in cached_states
        if event["hit"] is not expected_hit:
            raise AssertionError("proposal cache hit/miss sequence is inconsistent")
        if expected_hit:
            expected_charge = {
                "action_scores": 0,
                "batch_calls": 0,
                "input_values": 0,
                "state_items": 0,
            }
            cache_hits += 1
        else:
            expected_charge = {
                "action_scores": len(row.actions),
                "batch_calls": 1,
                "input_values": len(state) + 1,
                "state_items": 1,
            }
            cached_states.add(state)
            cache_misses += 1
        if any(event[name] != value for name, value in expected_charge.items()):
            raise AssertionError(
                "proposal event charge does not match lookup semantics"
            )
        for name, value in expected_charge.items():
            proposal_usage[f"proposal_{name}"] += value

    transition_events = [
        event
        for event in record["selection_events"]
        if event["event"] == "edge_transition"
    ]
    selection_charges = 0
    for event in record["selection_events"]:
        event_type = event.get("event")
        if event_type not in {"edge_transition", "frontier_expand"}:
            raise AssertionError("unknown selection event")
        state = task.canonical_state(event["state"])
        row = snapshot.get(task, state)
        expected_selection_charge = (
            len(row.actions)
            if event_type == "frontier_expand" or record["method"] != "best_first_8"
            else 0
        )
        if event["selection_action_scores"] != expected_selection_charge:
            raise AssertionError("selection event score charge is inconsistent")
        selection_charges += event["selection_action_scores"]
        if event_type == "frontier_expand":
            if set(event) != {
                "event",
                "selection_action_scores",
                "state",
            }:
                raise AssertionError("invalid frontier expansion event")
            continue
        action_index = event["action_index"]
        if type(action_index) is not int or not 0 <= action_index < len(row.actions):
            raise AssertionError("transition action index is invalid")
        action = row.actions[action_index]
        if (
            event["action"] != action.to_dict()
            or event["child"] != list(task.transition(state, action))
            or not math.isclose(
                event["prior_logp"],
                row.prior_logp[action_index],
                rel_tol=0.0,
                abs_tol=1e-12,
            )
        ):
            raise AssertionError("transition event does not replay")

    expected_usage = {
        **proposal_usage,
        "selection_action_scores": selection_charges,
        "edge_selections": len(transition_events),
        "transitions": len(transition_events),
        "verifier_calls": len(record["terminals"]),
    }
    if usage["usage"] != expected_usage:
        raise AssertionError("search usage does not close against events")
    if (
        usage["cache_hits"] != cache_hits
        or usage["cache_misses"] != cache_misses
        or usage["cache_lookups"] != cache_hits + cache_misses
        or usage["unique_states"] != len(cached_states)
    ):
        raise AssertionError("proposal cache ledger does not close")
    if usage["evaluation_only_calls"] != 1:
        raise AssertionError("readout must be recorded exactly once")
    expected_remaining = {
        axis: SEARCH_BUDGET.to_dict()[axis] - expected_usage[axis]
        for axis in COMPUTE_AXES
    }
    if (
        usage["remaining"] != expected_remaining
        or usage["overshoot_by_axis"] != {axis: 0 for axis in COMPUTE_AXES}
        or usage["exhausted_axes"]
        != [axis for axis in COMPUTE_AXES if expected_remaining[axis] == 0]
    ):
        raise AssertionError("search ledger derived fields are inconsistent")

    observed_success = False
    for observation_index, terminal in enumerate(record["terminals"]):
        if terminal["observation_index"] != observation_index:
            raise AssertionError("terminal observation indices are not contiguous")
        actions = tuple(_action_from_dict(item) for item in terminal["actions"])
        verification = task.verify(actions)
        stored = terminal["verification"]
        if (
            stored["success"] != verification.success
            or stored["reason"] != verification.reason
            or stored["final_value"] != verification.final_value
            or stored["source_use_exact"] != verification.source_use_exact
        ):
            raise AssertionError("terminal exact replay mismatch")
        state = task.initial_state
        states = [state]
        cumulative_prior_logp = 0.0
        for action in actions:
            row = snapshot.get(task, state)
            try:
                action_index = row.actions.index(action)
            except ValueError as error:
                raise AssertionError(
                    "terminal action missing from proposal row"
                ) from error
            cumulative_prior_logp += row.prior_logp[action_index]
            state = task.transition(state, action)
            states.append(state)
        if terminal["states"] != [list(item) for item in states]:
            raise AssertionError("terminal state trace mismatch")
        if not math.isclose(
            terminal["cumulative_prior_logp"],
            cumulative_prior_logp,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise AssertionError("terminal cumulative prior does not replay")
        observed_success = observed_success or verification.success
    if bool(record["exact_success_any"]) != observed_success:
        raise AssertionError("record exact-success flag mismatch")
    readout = record["readout"]
    if readout is None:
        if record["terminals"]:
            raise AssertionError("readout missing despite observed terminals")
    else:
        exact = [
            terminal
            for terminal in record["terminals"]
            if terminal["verification"]["success"]
        ]
        if exact:
            selected = min(exact, key=lambda item: item["observation_index"])
            reason = "first_exact_terminal"
        else:
            selected = min(
                record["terminals"],
                key=lambda item: (
                    -item["cumulative_prior_logp"],
                    _trace_sort_key(
                        tuple(_action_from_dict(action) for action in item["actions"])
                    ),
                ),
            )
            reason = "highest_prior_verified_terminal"
        expected_readout = {
            "observation_index": selected["observation_index"],
            "reason": reason,
            "success": selected["verification"]["success"],
        }
        if readout != expected_readout:
            raise AssertionError("readout selection rule does not replay")


def validate_artifact(
    artifact_dir: Path,
    *,
    require_replay_match: bool = True,
) -> dict[str, Any]:
    manifest = _strict_json_file(artifact_dir / "manifest.json")
    expected_manifest_files = {
        "acquisition_checkpoint.json",
        "proposal_rows.jsonl",
        "provider_attempts.jsonl",
        "search_records.jsonl",
        "summary.json",
    }
    if (
        manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION
        or manifest.get("status") != "COMPLETE"
        or set(manifest.get("files", {})) != expected_manifest_files
    ):
        raise AssertionError("artifact manifest schema mismatch")
    for filename, expected in manifest["files"].items():
        path = artifact_dir / filename
        observed = _file_metadata(
            path,
            records=(len(_read_jsonl(path)) if path.suffix == ".jsonl" else None),
        )
        if observed != expected:
            raise AssertionError(f"artifact byte manifest mismatch: {filename}")
    summary_path = artifact_dir / "summary.json"
    summary = _strict_json_file(summary_path)
    if manifest.get("provider_mode") != summary["provider"]["mode"]:
        raise AssertionError("manifest provider mode mismatch")
    expected_model = summary["provider"]["model"]
    snapshot = load_snapshot(artifact_dir / "proposal_rows.jsonl")
    expected_states = {
        (task.task_fingerprint, state)
        for task in DEV_TASKS
        for state in _nonterminal_states(task)
    }
    if set(snapshot._index) != expected_states or len(snapshot.rows) != 64:
        raise AssertionError("proposal snapshot is not complete for the dev fixture")
    response_ids: set[str] = set()
    provider_usage_totals = {
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "input_tokens": 0,
        "output_tokens": 0,
    }
    for task in DEV_TASKS:
        for state in _nonterminal_states(task):
            row = snapshot.get(task, state)
            if row.actions != task.legal_actions(state):
                raise AssertionError("proposal legal actions drifted")
            provider = row.provider_result
            if provider.get("adapter_schema_version") != ADAPTER_SCHEMA_VERSION:
                raise AssertionError("provider adapter schema mismatch")
            metadata = provider["metadata"]
            payload = metadata["provider_payload"]
            if set(payload) != {"legal_actions", "ruleset_id", "state", "target"}:
                raise AssertionError("artifact provider payload exceeds allowlist")
            expected_payload = _provider_payload(task, state, task.legal_actions(state))
            if payload != expected_payload:
                raise AssertionError("artifact provider payload identity mismatch")
            response_text = metadata["response_text_for_replay"]
            decoded = AnthropicCountdownScorer._decode_scores(
                response_text, len(row.actions)
            )
            if decoded != row.raw_scores:
                raise AssertionError("raw provider response does not replay to scores")
            if metadata["provider_payload_digest"] != _sha256_json(payload) or metadata[
                "response_text_digest"
            ] != _sha256_bytes(response_text.encode("utf-8")):
                raise AssertionError(
                    "provider request/response content digest mismatch"
                )
            if (
                metadata["api_endpoint"] != API_ENDPOINT
                or metadata["api_version"] != API_VERSION
                or metadata["model_requested"] != expected_model
                or metadata["model_returned"] != expected_model
                or metadata["stop_reason"] != "end_turn"
                or metadata["response_validation"]["status"] != "valid"
                or metadata["system_instruction_digest"]
                != _sha256_bytes(SYSTEM_INSTRUCTION.encode("utf-8"))
            ):
                raise AssertionError("provider identity or strict-validation drift")
            response_id = metadata.get("response_id")
            if (
                not isinstance(response_id, str)
                or not response_id.strip()
                or response_id in response_ids
            ):
                raise AssertionError("provider response ID is missing or duplicated")
            response_ids.add(response_id)
            if (
                summary["provider"]["mode"] == "live"
                and metadata.get("anthropic_sdk_version") != PINNED_SDK_VERSION
            ):
                raise AssertionError("live provider SDK identity mismatch")
            tokens = metadata.get("tokens")
            if not isinstance(tokens, dict) or set(tokens) != set(
                provider_usage_totals
            ):
                raise AssertionError("provider usage metadata shape mismatch")
            if any(type(value) is not int or value < 0 for value in tokens.values()):
                raise AssertionError("provider usage metadata is incomplete")
            if (
                tokens["cache_creation_input_tokens"] != 0
                or tokens["cache_read_input_tokens"] != 0
                or tokens["input_tokens"] > MAX_INPUT_TOKENS_PER_REQUEST
                or tokens["output_tokens"] > MAX_OUTPUT_TOKENS
            ):
                raise AssertionError("provider usage exceeds per-request reservation")
            for name, value in tokens.items():
                provider_usage_totals[name] += value
            schema = AnthropicCountdownScorer._output_schema(len(row.actions))
            expected_request = {
                "max_tokens": MAX_OUTPUT_TOKENS,
                "messages": [{"content": _canonical_json(payload), "role": "user"}],
                "model": expected_model,
                "output_config": {"format": {"schema": schema, "type": "json_schema"}},
                "service_tier": "standard_only",
                "system": SYSTEM_INSTRUCTION,
                "temperature": 0.0,
            }
            if metadata["output_schema_digest"] != _sha256_json(schema) or metadata[
                "request_digest"
            ] != _sha256_json(expected_request):
                raise AssertionError("provider cache/request identity mismatch")
            scored_records = provider["scored_actions"]
            if [item["action"] for item in scored_records] != [
                action.to_dict() for action in row.actions
            ] or [item["score"] for item in scored_records] != list(row.raw_scores):
                raise AssertionError("provider parsed-score evidence mismatch")
            forbidden = ("solution_witness", "calibration_profile", "task_fingerprint")
            serialized_payload = _canonical_json(payload)
            if any(name in serialized_payload for name in forbidden):
                raise AssertionError("provider request leaked forbidden oracle fields")
    records = _read_jsonl(artifact_dir / "search_records.jsonl")
    if len(records) != 12:
        raise AssertionError("unexpected development search-record count")
    for record in records:
        _validate_search_record(record, snapshot)
    if require_replay_match:
        replayed = run_all_searches(snapshot)
        original_bytes = (artifact_dir / "search_records.jsonl").read_bytes()
        replayed_bytes = "".join(
            _canonical_json(record) + "\n" for record in replayed
        ).encode("utf-8")
        if replayed_bytes != original_bytes:
            raise AssertionError("network-free search replay is not byte-identical")
    summary_payload = {
        key: value for key, value in summary.items() if key != "deterministic_digest"
    }
    if summary.get("deterministic_digest") != _sha256_json(summary_payload):
        raise AssertionError("summary digest mismatch")
    if (
        summary["proposal_behavior_digest"] != snapshot.behavior_digest
        or summary["proposal_acquisition_digest"] != snapshot.acquisition_digest
    ):
        raise AssertionError("summary proposal digest mismatch")
    physical = summary["physical_provider_usage"]
    _validate_physical_ledger(physical, require_complete=True)
    if any(physical[name] != value for name, value in provider_usage_totals.items()):
        raise AssertionError("physical token ledger does not match provider rows")
    _validate_acquisition_journals(artifact_dir, snapshot, physical)
    summary["data_quality"] = {
        "artifact_bytes_verified": True,
        "network_free_replay_verified": require_replay_match,
        "proposal_rows_verified": len(snapshot.rows),
        "search_records_verified": len(records),
        "status": "PASS",
    }
    summary_payload = {
        key: value for key, value in summary.items() if key != "deterministic_digest"
    }
    summary["deterministic_digest"] = _sha256_json(summary_payload)
    _write_json(summary_path, summary)
    manifest["files"]["summary.json"] = _file_metadata(summary_path)
    _write_json(artifact_dir / "manifest.json", manifest)
    return summary


def _run_pipeline(
    scorer: ActionScorer,
    output_dir: Path,
    *,
    provider_mode: str,
) -> dict[str, Any]:
    _ensure_empty_output_dir(output_dir)
    attempts_path = output_dir / "provider_attempts.jsonl"
    proposals_path = output_dir / "proposal_rows.jsonl"
    checkpoint_path = output_dir / "acquisition_checkpoint.json"
    try:
        snapshot, physical_usage = acquire_snapshot(
            scorer,
            attempt_journal_path=attempts_path,
            proposal_journal_path=proposals_path,
            checkpoint_path=checkpoint_path,
        )
    except AcquisitionFailure as error:
        _write_json(output_dir / "acquisition_failure.json", error.to_record())
        _write_failure_manifest(output_dir, provider_mode=provider_mode)
        raise
    search_records = run_all_searches(snapshot)
    write_artifact(
        output_dir,
        snapshot,
        physical_usage,
        search_records,
        provider_mode=provider_mode,
    )
    return validate_artifact(output_dir)


def _run_self_test() -> None:
    fake = _FakeClient()
    scorer = AnthropicCountdownScorer(
        fake,
        model="fake-haiku",
        max_tokens=MAX_OUTPUT_TOKENS,
        temperature=0.0,
    )
    with tempfile.TemporaryDirectory(prefix="qmc_bmgs_anthropic_dev_") as directory:
        output_dir = Path(directory) / "artifact"
        summary = _run_pipeline(scorer, output_dir, provider_mode="fake")
        assert summary["data_quality"]["status"] == "PASS"
        assert summary["dev_fixture"]["nonterminal_state_count"] == 64
        assert summary["record_count"] == 12
        assert fake.messages.calls == 64
        artifact_bytes = b"".join(
            path.read_bytes() for path in sorted(output_dir.iterdir()) if path.is_file()
        )
        assert FAKE_SECRET.encode() not in artifact_bytes
        assert b"api_key" not in artifact_bytes
        validate_artifact(output_dir)

        def mutation_copy(name: str) -> Path:
            destination = Path(directory) / f"mutation_{name}"
            shutil.copytree(output_dir, destination)
            return destination

        def refresh_manifest(artifact_dir: Path, filename: str) -> None:
            manifest = _strict_json_file(artifact_dir / "manifest.json")
            path = artifact_dir / filename
            records = len(_read_jsonl(path)) if path.suffix == ".jsonl" else None
            manifest["files"][filename] = _file_metadata(path, records=records)
            _write_json(artifact_dir / "manifest.json", manifest)

        def expect_semantic_rejection(artifact_dir: Path, label: str) -> None:
            try:
                validate_artifact(artifact_dir, require_replay_match=False)
            except (AssertionError, KeyError, TypeError, ValueError):
                return
            raise AssertionError(f"semantic artifact mutation was accepted: {label}")

        missing_row_dir = mutation_copy("missing_row")
        missing_rows = list(_read_jsonl(missing_row_dir / "proposal_rows.jsonl"))
        _write_jsonl(missing_row_dir / "proposal_rows.jsonl", missing_rows[:-1])
        refresh_manifest(missing_row_dir, "proposal_rows.jsonl")
        expect_semantic_rejection(missing_row_dir, "missing proposal row")

        payload_dir = mutation_copy("provider_payload")
        payload_rows = list(_read_jsonl(payload_dir / "proposal_rows.jsonl"))
        payload_record = payload_rows[0]
        metadata = payload_record["provider_result"]["metadata"]
        metadata["provider_payload"]["target"] += 1
        metadata["provider_payload_digest"] = _sha256_json(metadata["provider_payload"])
        schema = AnthropicCountdownScorer._output_schema(
            len(payload_record["behavior"]["actions"])
        )
        mutated_request = {
            "max_tokens": MAX_OUTPUT_TOKENS,
            "messages": [
                {
                    "content": _canonical_json(metadata["provider_payload"]),
                    "role": "user",
                }
            ],
            "model": "fake-haiku",
            "output_config": {"format": {"schema": schema, "type": "json_schema"}},
            "service_tier": "standard_only",
            "system": SYSTEM_INSTRUCTION,
            "temperature": 0.0,
        }
        metadata["request_digest"] = _sha256_json(mutated_request)
        proposal_payload = {
            key: value
            for key, value in payload_record.items()
            if key != "deterministic_digest"
        }
        payload_record["deterministic_digest"] = _sha256_json(proposal_payload)
        _write_jsonl(payload_dir / "proposal_rows.jsonl", payload_rows)
        refresh_manifest(payload_dir, "proposal_rows.jsonl")
        expect_semantic_rejection(payload_dir, "provider payload identity")

        usage_dir = mutation_copy("missing_usage")
        usage_rows = list(_read_jsonl(usage_dir / "proposal_rows.jsonl"))
        usage_record = usage_rows[0]
        usage_record["provider_result"]["metadata"]["tokens"]["input_tokens"] = None
        usage_payload = {
            key: value
            for key, value in usage_record.items()
            if key != "deterministic_digest"
        }
        usage_record["deterministic_digest"] = _sha256_json(usage_payload)
        _write_jsonl(usage_dir / "proposal_rows.jsonl", usage_rows)
        refresh_manifest(usage_dir, "proposal_rows.jsonl")
        expect_semantic_rejection(usage_dir, "missing provider usage")

        ledger_dir = mutation_copy("search_ledger")
        ledger_records = list(_read_jsonl(ledger_dir / "search_records.jsonl"))
        ledger_records[0]["usage"]["usage"]["proposal_batch_calls"] += 1
        ledger_records[0]["deterministic_digest"] = canonical_record_digest(
            ledger_records[0]
        )
        _write_jsonl(ledger_dir / "search_records.jsonl", ledger_records)
        refresh_manifest(ledger_dir, "search_records.jsonl")
        expect_semantic_rejection(ledger_dir, "search ledger closure")

        readout_dir = mutation_copy("readout")
        readout_records = list(_read_jsonl(readout_dir / "search_records.jsonl"))
        readout_record = next(row for row in readout_records if row["readout"])
        readout_record["readout"]["reason"] = "mutated_rule"
        readout_record["deterministic_digest"] = canonical_record_digest(readout_record)
        _write_jsonl(readout_dir / "search_records.jsonl", readout_records)
        refresh_manifest(readout_dir, "search_records.jsonl")
        expect_semantic_rejection(readout_dir, "readout selection rule")

        records_path = output_dir / "search_records.jsonl"
        original_records = records_path.read_bytes()
        records_path.write_bytes(original_records + b" ")
        try:
            validate_artifact(output_dir)
        except (AssertionError, ValueError):
            pass
        else:
            raise AssertionError("artifact byte corruption must be rejected")
        records_path.write_bytes(original_records)

        failure_dir = Path(directory) / "failure"
        try:
            _run_pipeline(_FailingScorer(), failure_dir, provider_mode="fake")
        except AcquisitionFailure as error:
            assert error.reason == "provider_transport_or_sdk_error"
        else:
            raise AssertionError("provider transport failure must abort acquisition")
        failure_record = _strict_json_file(failure_dir / "acquisition_failure.json")
        assert failure_record["status"] == "FAILED_CLOSED"
        assert failure_record["physical_provider_usage"]["attempts"] == 1
        assert failure_record["physical_provider_usage"]["failures"] == 1
        assert FAKE_SECRET not in _canonical_json(failure_record)
        assert _strict_json_file(failure_dir / "manifest.json")["status"] == (
            "FAILED_CLOSED"
        )
        assert (
            _strict_json_file(failure_dir / "acquisition_checkpoint.json")["status"]
            == "FAILED"
        )
        assert len(_read_jsonl(failure_dir / "provider_attempts.jsonl")) == 2

        partial_dir = Path(directory) / "partial_failure"
        try:
            _run_pipeline(
                _FailAfterNScorer(successful_calls=3),
                partial_dir,
                provider_mode="fake",
            )
        except AcquisitionFailure:
            pass
        else:
            raise AssertionError("failure-after-N scorer must abort acquisition")
        partial_snapshot = load_snapshot(partial_dir / "proposal_rows.jsonl")
        assert len(partial_snapshot.rows) == 3
        assert len(_read_jsonl(partial_dir / "provider_attempts.jsonl")) == 8
        partial_checkpoint = _strict_json_file(
            partial_dir / "acquisition_checkpoint.json"
        )
        assert partial_checkpoint["status"] == "FAILED"
        assert partial_checkpoint["proposal_journal"]["records"] == 3

        settlement_dir = Path(directory) / "settlement_failure"
        try:
            _run_pipeline(
                _OverBoundUsageScorer(),
                settlement_dir,
                provider_mode="fake",
            )
        except AcquisitionFailure as error:
            assert error.reason == "provider_usage_settlement_error"
        else:
            raise AssertionError("over-bound provider usage must fail closed")
        settlement = _strict_json_file(settlement_dir / "acquisition_failure.json")[
            "physical_provider_usage"
        ]
        assert settlement["attempts"] == 1
        assert settlement["responses_returned"] == 1
        assert settlement["successes"] == 0
        assert settlement["failures"] == 1
        assert settlement["input_tokens"] == MAX_INPUT_TOKENS_PER_REQUEST + 1
        assert settlement["actual_cost_usd"] > 0.0

        zero_budget = PhysicalProviderLedger(
            PhysicalProviderBudget(max_requests=0, max_cost_usd=0.0)
        )
        before = zero_budget.snapshot()
        try:
            zero_budget.reserve()
        except RuntimeError:
            pass
        else:
            raise AssertionError("physical reservation must fail before mutation")
        assert zero_budget.snapshot() == before
    print("countdown Anthropic dev self-test: PASS")


def _sdk_version() -> str | None:
    try:
        return importlib.metadata.version("anthropic")
    except importlib.metadata.PackageNotFoundError:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--self-test", action="store_true")
    modes.add_argument("--run-fake-dev", action="store_true")
    modes.add_argument("--run-live-dev", action="store_true")
    modes.add_argument("--replay", type=Path, metavar="ARTIFACT_DIR")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    if args.self_test:
        if args.output_dir is not None:
            parser.error("--self-test does not accept --output-dir")
        _run_self_test()
        return
    if args.replay is not None:
        if args.output_dir is not None:
            parser.error("--replay does not accept --output-dir")
        summary = validate_artifact(args.replay)
        print(
            "countdown Anthropic dev replay: PASS",
            _canonical_json(summary["data_quality"]),
        )
        return
    if args.output_dir is None:
        parser.error("provider runs require --output-dir")

    if args.run_fake_dev:
        scorer = AnthropicCountdownScorer(
            _FakeClient(),
            model="fake-haiku",
            max_tokens=MAX_OUTPUT_TOKENS,
            temperature=0.0,
        )
        provider_mode = "fake"
    else:
        observed_sdk = _sdk_version()
        if observed_sdk != PINNED_SDK_VERSION:
            parser.error(
                f"Anthropic SDK must be exactly {PINNED_SDK_VERSION}; "
                f"observed {observed_sdk!r}"
            )
        if not os.environ.get("ANTHROPIC_API_KEY"):
            parser.error("ANTHROPIC_API_KEY is not set in the process environment")
        if os.environ.get("ANTHROPIC_LOG"):
            parser.error("ANTHROPIC_LOG must be unset for secret-safe live acquisition")
        scorer = AnthropicCountdownScorer.from_environment(
            model=PINNED_MODEL,
            max_tokens=MAX_OUTPUT_TOKENS,
            temperature=0.0,
            max_retries=0,
            timeout=30.0,
        )
        provider_mode = "live"
    try:
        summary = _run_pipeline(scorer, args.output_dir, provider_mode=provider_mode)
    except AcquisitionFailure as error:
        print(
            "countdown Anthropic dev run: FAILED_CLOSED",
            _canonical_json(
                {
                    "attempts": error.ledger["attempts"],
                    "cause_type": error.cause_type,
                    "failure_artifact_dir": str(args.output_dir),
                    "reason": error.reason,
                }
            ),
        )
        raise SystemExit(1) from None
    print(
        "countdown Anthropic dev run: PASS",
        _canonical_json(
            {
                "actual_cost_usd": summary["physical_provider_usage"][
                    "actual_cost_usd"
                ],
                "artifact_dir": str(args.output_dir),
                "provider_mode": provider_mode,
                "proposal_rows": summary["dev_fixture"]["nonterminal_state_count"],
                "search_records": summary["record_count"],
            }
        ),
    )


if __name__ == "__main__":
    main()
