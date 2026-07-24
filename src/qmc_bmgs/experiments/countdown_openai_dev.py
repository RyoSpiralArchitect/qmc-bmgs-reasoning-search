#!/usr/bin/env python3
"""GPT-5.6-backed Countdown development runner with offline replay.

This is a provider-plumbing canary, not an effectiveness benchmark. It acquires
one immutable GPT-5.6 Sol action-score snapshot for the same two tiny public
development tasks as the Anthropic canary, then reuses the same local search
implementation and exact verifier against those frozen bytes.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import math
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping, Sequence

from qmc_bmgs.benchmarks.countdown import CountdownAction, CountdownState
# The historical Anthropic runner currently owns the provider-neutral snapshot,
# local-search, verifier, and replay primitives. Importing them preserves exact
# search semantics while OpenAI acquisition/accounting stays provider-specific.
from qmc_bmgs.experiments.countdown_anthropic_dev import (
    DEV_TASKS,
    NORMALIZATION_VERSION,
    AcquisitionFailure,
    ProposalSnapshot,
    _canonical_json,
    _ensure_empty_output_dir,
    _file_metadata,
    _journal_file_evidence,
    _nonterminal_states,
    _provider_payload,
    _read_jsonl,
    _sha256_bytes,
    _sha256_json,
    _strict_json_file,
    _strict_json_text,
    _validate_search_record,
    _write_json,
    _write_jsonl,
    acquire_snapshot,
    load_snapshot,
    run_all_searches,
)
from qmc_bmgs.openai_countdown import (
    ADAPTER_SCHEMA_VERSION,
    API_ENDPOINT,
    API_VERSION,
    OUTPUT_SCHEMA_NAME,
    REASONING_EFFORT,
    SYSTEM_INSTRUCTION,
    OpenAICountdownScorer,
    OpenAIScoreResult,
)


RECORD_SCHEMA_VERSION = "qmc-bmgs-countdown-openai-dev-record/v1"
SUMMARY_SCHEMA_VERSION = "qmc-bmgs-countdown-openai-dev-summary/v1"
MANIFEST_SCHEMA_VERSION = "qmc-bmgs-countdown-openai-dev-manifest/v1"
PINNED_MODEL = "gpt-5.6-sol"
PINNED_SDK_VERSION = "2.45.0"
MAX_OUTPUT_TOKENS = 512
MAX_INPUT_TOKENS_PER_REQUEST = 4096
PHYSICAL_REQUEST_CAP = 64
PHYSICAL_COST_CAP_USD = 3.00
FAKE_MODEL = "fake-gpt-5.6-sol"
FAKE_SECRET = "fake-openai-secret-must-never-appear"

PRICE_SOURCE = "https://developers.openai.com/api/docs/models/gpt-5.6-sol"
PRICE_RETRIEVED_DATE = "2026-07-24"
PRICE_PER_MTOK = {
    "base_input": 5.0,
    "cache_write_input": 6.25,
    "cached_input": 0.50,
    "output": 30.0,
}


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
        # Any input token may be an implicit cache write at 1.25x base price.
        return (
            self.max_input_tokens_per_request
            * PRICE_PER_MTOK["cache_write_input"]
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
    cached_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0
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

    def record_success(self, result: OpenAIScoreResult, latency_ms: float) -> None:
        self.responses_returned += 1
        self.latency_ms += latency_ms
        tokens = result.metadata["tokens"]
        values = {
            name: tokens.get(name)
            for name in (
                "input_tokens",
                "output_tokens",
                "cached_tokens",
                "cache_write_tokens",
                "reasoning_tokens",
                "total_tokens",
            )
        }
        if any(type(value) is not int or value < 0 for value in values.values()):
            raise ValueError("provider usage contains missing or invalid token counts")
        typed = {name: int(value) for name, value in values.items()}
        uncached = (
            typed["input_tokens"]
            - typed["cached_tokens"]
            - typed["cache_write_tokens"]
        )
        if (
            uncached < 0
            or typed["reasoning_tokens"] > typed["output_tokens"]
            or typed["total_tokens"]
            != typed["input_tokens"] + typed["output_tokens"]
        ):
            raise ValueError("provider token usage details are inconsistent")
        for name, value in typed.items():
            setattr(self, name, getattr(self, name) + value)
        self.actual_cost_usd += (
            uncached * PRICE_PER_MTOK["base_input"]
            + typed["cached_tokens"] * PRICE_PER_MTOK["cached_input"]
            + typed["cache_write_tokens"] * PRICE_PER_MTOK["cache_write_input"]
            + typed["output_tokens"] * PRICE_PER_MTOK["output"]
        ) / 1_000_000
        if typed["input_tokens"] > self.budget.max_input_tokens_per_request:
            raise RuntimeError(
                "provider input usage exceeded reserved per-request bound"
            )
        if typed["output_tokens"] > self.budget.max_output_tokens_per_request:
            raise RuntimeError(
                "provider output usage exceeded reserved per-request bound"
            )
        self.successes += 1

    def record_settlement_failure(self, error: BaseException) -> None:
        self.failures += 1
        self.failure_types.append(type(error).__name__)

    def snapshot(self) -> dict[str, Any]:
        payload = {
            "actual_cost_usd": self.actual_cost_usd,
            "attempts": self.attempts,
            "budget": self.budget.to_dict(),
            "cache_write_tokens": self.cache_write_tokens,
            "cached_tokens": self.cached_tokens,
            "failures": self.failures,
            "failure_types": list(self.failure_types),
            "input_tokens": self.input_tokens,
            "latency_ms": self.latency_ms,
            "output_tokens": self.output_tokens,
            "price_per_mtok": dict(PRICE_PER_MTOK),
            "price_retrieved_date": PRICE_RETRIEVED_DATE,
            "price_source": PRICE_SOURCE,
            "reasoning_tokens": self.reasoning_tokens,
            "responses_returned": self.responses_returned,
            "reserved_cost_usd": self.reserved_cost_usd,
            "successes": self.successes,
            "total_tokens": self.total_tokens,
        }
        return {**payload, "ledger_digest": _sha256_json(payload)}


class _FakeResponses:
    def __init__(self) -> None:
        self.api_key = FAKE_SECRET
        self.calls = 0

    def create(self, **request: Any) -> Any:
        self.calls += 1
        payload = _strict_json_text(request["input"])
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
        input_tokens = max(1, len(request["input"]) // 4)
        output_tokens = max(1, len(text) // 4)
        return SimpleNamespace(
            id=f"fake_resp_{self.calls:03d}_{request_digest[:12]}",
            model=request["model"],
            status="completed",
            service_tier="default",
            error=None,
            incomplete_details=None,
            output=[
                SimpleNamespace(
                    id=f"fake_msg_{self.calls:03d}_{request_digest[:12]}",
                    type="message",
                    role="assistant",
                    status="completed",
                    content=[SimpleNamespace(type="output_text", text=text)],
                )
            ],
            usage=SimpleNamespace(
                input_tokens=input_tokens,
                input_tokens_details=SimpleNamespace(
                    cache_write_tokens=0,
                    cached_tokens=0,
                ),
                output_tokens=output_tokens,
                output_tokens_details=SimpleNamespace(reasoning_tokens=0),
                total_tokens=input_tokens + output_tokens,
            ),
        )


class _FakeClient:
    def __init__(self) -> None:
        self.responses = _FakeResponses()
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
    ) -> OpenAIScoreResult:
        del target, state, legal_actions
        raise RuntimeError("synthetic_transport_failure")


class _RecoveredScorer:
    model = FAKE_MODEL
    max_tokens = MAX_OUTPUT_TOKENS

    def __init__(self) -> None:
        self.delegate = OpenAICountdownScorer(_FakeClient(), model=self.model)

    def score_actions(
        self,
        *,
        target: int,
        state: CountdownState,
        legal_actions: Sequence[CountdownAction],
    ) -> OpenAIScoreResult:
        result = self.delegate.score_actions(
            target=target,
            state=state,
            legal_actions=legal_actions,
        )
        result.metadata["response_validation"] = {
            "recovered": True,
            "recovery_policy": "neutral_all_zero_scores",
            "recovery_reason": "synthetic_invalid_response",
            "status": "recovered",
        }
        return result


class _OverBoundUsageScorer:
    model = FAKE_MODEL
    max_tokens = MAX_OUTPUT_TOKENS

    def __init__(self) -> None:
        self.delegate = OpenAICountdownScorer(_FakeClient(), model=self.model)

    def score_actions(
        self,
        *,
        target: int,
        state: CountdownState,
        legal_actions: Sequence[CountdownAction],
    ) -> OpenAIScoreResult:
        result = self.delegate.score_actions(
            target=target,
            state=state,
            legal_actions=legal_actions,
        )
        tokens = result.metadata["tokens"]
        tokens["input_tokens"] = MAX_INPUT_TOKENS_PER_REQUEST + 1
        tokens["total_tokens"] = tokens["input_tokens"] + tokens["output_tokens"]
        return result


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
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "model": PINNED_MODEL if provider_mode == "live" else FAKE_MODEL,
            "mode": provider_mode,
            "normalization_version": NORMALIZATION_VERSION,
            "reasoning_effort": REASONING_EFFORT,
            "sdk_version_required": PINNED_SDK_VERSION,
            "store": False,
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
    attempts_path = output_dir / "provider_attempts.jsonl"
    checkpoint_path = output_dir / "acquisition_checkpoint.json"
    proposal_records = [row.to_record() for row in snapshot.rows]
    _write_jsonl(proposal_path, proposal_records)
    _write_jsonl(records_path, search_records)
    _write_json(
        summary_path,
        _summary(
            snapshot,
            physical_usage,
            search_records,
            provider_mode=provider_mode,
        ),
    )
    _write_json(
        output_dir / "manifest.json",
        {
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
        },
    )


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


def _expected_actual_cost(ledger: Mapping[str, Any]) -> float:
    uncached = (
        ledger["input_tokens"]
        - ledger["cached_tokens"]
        - ledger["cache_write_tokens"]
    )
    if uncached < 0:
        raise AssertionError("physical provider cached token details exceed input")
    return (
        uncached * PRICE_PER_MTOK["base_input"]
        + ledger["cached_tokens"] * PRICE_PER_MTOK["cached_input"]
        + ledger["cache_write_tokens"] * PRICE_PER_MTOK["cache_write_input"]
        + ledger["output_tokens"] * PRICE_PER_MTOK["output"]
    ) / 1_000_000


def _validate_physical_ledger(
    ledger: Mapping[str, Any],
    *,
    require_complete: bool,
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
        "cached_tokens",
        "cache_write_tokens",
        "reasoning_tokens",
        "total_tokens",
    )
    if any(
        type(ledger[name]) is not int or ledger[name] < 0 for name in integer_fields
    ):
        raise AssertionError("physical provider ledger contains invalid counters")
    if (
        ledger["responses_returned"] > ledger["attempts"]
        or ledger["successes"] > ledger["responses_returned"]
        or ledger["successes"] + ledger["failures"] > ledger["attempts"]
        or ledger["reasoning_tokens"] > ledger["output_tokens"]
        or ledger["total_tokens"]
        != ledger["input_tokens"] + ledger["output_tokens"]
        or not math.isfinite(ledger["latency_ms"])
        or ledger["latency_ms"] < 0
        or not isinstance(ledger["failure_types"], list)
    ):
        raise AssertionError("physical provider ledger lifecycle is inconsistent")
    expected_reserved = ledger["attempts"] * ledger["budget"][
        "reserve_per_request_usd"
    ]
    if not math.isclose(
        ledger["reserved_cost_usd"],
        expected_reserved,
        rel_tol=0.0,
        abs_tol=1e-12,
    ) or not math.isclose(
        ledger["actual_cost_usd"],
        _expected_actual_cost(ledger),
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
                event.get("schema_version")
                != "qmc-bmgs-provider-attempt-event/v1"
                or event.get("attempt") != offset + 1
                or event.get("task_fingerprint") != row.task_fingerprint
                or event.get("state") != list(row.state)
            ):
                raise AssertionError("provider attempt event identity mismatch")
            _validate_physical_ledger(
                event["physical_provider_usage"],
                require_complete=False,
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
        or checkpoint.get("proposal_journal")
        != _journal_file_evidence(proposal_path)
    ):
        raise AssertionError("acquisition checkpoint does not close")


def _expected_request(
    payload: Mapping[str, Any],
    action_count: int,
    model: str,
) -> dict[str, Any]:
    schema = OpenAICountdownScorer._output_schema(action_count)
    return {
        "input": _canonical_json(payload),
        "instructions": SYSTEM_INSTRUCTION,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "model": model,
        "reasoning": {"effort": REASONING_EFFORT},
        "service_tier": "default",
        "store": False,
        "text": {
            "format": {
                "name": f"{OUTPUT_SCHEMA_NAME}_{action_count}",
                "schema": schema,
                "strict": True,
                "type": "json_schema",
            },
            "verbosity": "low",
        },
        "truncation": "disabled",
    }


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
    if (
        summary.get("schema_version") != SUMMARY_SCHEMA_VERSION
        or manifest.get("provider_mode") != summary["provider"]["mode"]
    ):
        raise AssertionError("summary/provider mode schema mismatch")
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
    message_ids: set[str] = set()
    usage_totals = {
        "cache_write_tokens": 0,
        "cached_tokens": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "total_tokens": 0,
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
            expected_payload = _provider_payload(task, state, row.actions)
            if payload != expected_payload:
                raise AssertionError("artifact provider payload identity mismatch")
            response_text = metadata["response_text_for_replay"]
            decoded = OpenAICountdownScorer._decode_scores(
                response_text,
                len(row.actions),
            )
            if decoded != row.raw_scores:
                raise AssertionError("raw provider response does not replay to scores")
            if (
                metadata["provider_payload_digest"] != _sha256_json(payload)
                or metadata["response_text_digest"]
                != _sha256_bytes(response_text.encode("utf-8"))
            ):
                raise AssertionError(
                    "provider request/response content digest mismatch"
                )
            if (
                metadata["api_endpoint"] != API_ENDPOINT
                or metadata["api_version"] != API_VERSION
                or metadata["model_requested"] != expected_model
                or metadata["model_returned"] != expected_model
                or metadata["response_status"] != "completed"
                or metadata["service_tier_returned"] != "default"
                or metadata["response_validation"]["status"] != "valid"
                or not isinstance(metadata.get("output_item_types"), list)
                or metadata["output_item_types"].count("message") != 1
                or any(
                    item_type not in {"message", "reasoning"}
                    for item_type in metadata["output_item_types"]
                )
                or metadata["system_instruction_digest"]
                != _sha256_bytes(SYSTEM_INSTRUCTION.encode("utf-8"))
            ):
                raise AssertionError("provider identity or strict-validation drift")
            response_id = metadata.get("response_id")
            message_id = metadata.get("message_id")
            if (
                not isinstance(response_id, str)
                or not response_id.strip()
                or response_id in response_ids
                or not isinstance(message_id, str)
                or not message_id.strip()
                or message_id in message_ids
            ):
                raise AssertionError("provider response/message ID is invalid")
            response_ids.add(response_id)
            message_ids.add(message_id)
            if (
                summary["provider"]["mode"] == "live"
                and metadata.get("openai_sdk_version") != PINNED_SDK_VERSION
            ):
                raise AssertionError("live provider SDK identity mismatch")
            tokens = metadata.get("tokens")
            if not isinstance(tokens, dict) or set(tokens) != set(usage_totals):
                raise AssertionError("provider usage metadata shape mismatch")
            if any(type(value) is not int or value < 0 for value in tokens.values()):
                raise AssertionError("provider usage metadata is incomplete")
            if (
                tokens["input_tokens"] > MAX_INPUT_TOKENS_PER_REQUEST
                or tokens["output_tokens"] > MAX_OUTPUT_TOKENS
                or tokens["reasoning_tokens"] > tokens["output_tokens"]
                or tokens["total_tokens"]
                != tokens["input_tokens"] + tokens["output_tokens"]
                or tokens["cached_tokens"] + tokens["cache_write_tokens"]
                > tokens["input_tokens"]
            ):
                raise AssertionError("provider usage exceeds reservation or consistency")
            for name, value in tokens.items():
                usage_totals[name] += value
            schema = OpenAICountdownScorer._output_schema(len(row.actions))
            if (
                metadata["output_schema_digest"] != _sha256_json(schema)
                or metadata["request_digest"]
                != _sha256_json(
                    _expected_request(payload, len(row.actions), expected_model)
                )
            ):
                raise AssertionError("provider request/schema identity mismatch")
            scored_records = provider["scored_actions"]
            if [item["action"] for item in scored_records] != [
                action.to_dict() for action in row.actions
            ] or [item["score"] for item in scored_records] != list(row.raw_scores):
                raise AssertionError("provider parsed-score evidence mismatch")
            forbidden = (
                "solution_witness",
                "calibration_profile",
                "task_fingerprint",
            )
            serialized_payload = _canonical_json(payload)
            if any(name in serialized_payload for name in forbidden):
                raise AssertionError("provider request leaked forbidden oracle fields")

    records = _read_jsonl(artifact_dir / "search_records.jsonl")
    if len(records) != 12:
        raise AssertionError("unexpected development search-record count")
    for record in records:
        _validate_search_record(
            record,
            snapshot,
            record_schema_version=RECORD_SCHEMA_VERSION,
        )
    if require_replay_match:
        replayed = run_all_searches(
            snapshot,
            record_schema_version=RECORD_SCHEMA_VERSION,
        )
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
    if any(physical[name] != value for name, value in usage_totals.items()):
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
    scorer: Any,
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
            physical_budget=PhysicalProviderBudget(),
            attempt_journal_path=attempts_path,
            proposal_journal_path=proposals_path,
            checkpoint_path=checkpoint_path,
            pinned_model=PINNED_MODEL,
            expected_request_count=PHYSICAL_REQUEST_CAP,
            ledger_factory=PhysicalProviderLedger,
        )
    except AcquisitionFailure as error:
        _write_json(output_dir / "acquisition_failure.json", error.to_record())
        _write_failure_manifest(output_dir, provider_mode=provider_mode)
        raise
    search_records = run_all_searches(
        snapshot,
        record_schema_version=RECORD_SCHEMA_VERSION,
    )
    write_artifact(
        output_dir,
        snapshot,
        physical_usage,
        search_records,
        provider_mode=provider_mode,
    )
    return validate_artifact(output_dir)


def _refresh_manifest(artifact_dir: Path, filename: str) -> None:
    manifest = _strict_json_file(artifact_dir / "manifest.json")
    path = artifact_dir / filename
    records = len(_read_jsonl(path)) if path.suffix == ".jsonl" else None
    manifest["files"][filename] = _file_metadata(path, records=records)
    _write_json(artifact_dir / "manifest.json", manifest)


def _run_self_test() -> None:
    fake = _FakeClient()
    scorer = OpenAICountdownScorer(
        fake,
        model=FAKE_MODEL,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        reasoning_effort=REASONING_EFFORT,
    )
    with tempfile.TemporaryDirectory(prefix="qmc_bmgs_openai_dev_") as directory:
        output_dir = Path(directory) / "artifact"
        summary = _run_pipeline(scorer, output_dir, provider_mode="fake")
        assert summary["data_quality"]["status"] == "PASS"
        assert summary["dev_fixture"]["nonterminal_state_count"] == 64
        assert summary["record_count"] == 12
        assert fake.responses.calls == 64
        artifact_bytes = b"".join(
            path.read_bytes() for path in sorted(output_dir.iterdir()) if path.is_file()
        )
        assert FAKE_SECRET.encode() not in artifact_bytes
        assert b"api_key" not in artifact_bytes
        validate_artifact(output_dir)

        mutation_dir = Path(directory) / "mutation_missing_row"
        shutil.copytree(output_dir, mutation_dir)
        rows = list(_read_jsonl(mutation_dir / "proposal_rows.jsonl"))
        _write_jsonl(mutation_dir / "proposal_rows.jsonl", rows[:-1])
        _refresh_manifest(mutation_dir, "proposal_rows.jsonl")
        try:
            validate_artifact(mutation_dir, require_replay_match=False)
        except (AssertionError, KeyError, TypeError, ValueError):
            pass
        else:
            raise AssertionError("missing proposal row mutation was accepted")

        failure_dir = Path(directory) / "failure"
        try:
            _run_pipeline(_FailingScorer(), failure_dir, provider_mode="fake")
        except AcquisitionFailure as error:
            assert error.reason == "provider_transport_or_sdk_error"
        else:
            raise AssertionError("transport failure must abort acquisition")

        recovered_dir = Path(directory) / "recovered"
        try:
            _run_pipeline(_RecoveredScorer(), recovered_dir, provider_mode="fake")
        except AcquisitionFailure as error:
            assert error.reason == "provider_response_failed_strict_validation"
        else:
            raise AssertionError("recovered provider row must abort acquisition")

        settlement_dir = Path(directory) / "settlement"
        try:
            _run_pipeline(
                _OverBoundUsageScorer(),
                settlement_dir,
                provider_mode="fake",
            )
        except AcquisitionFailure as error:
            assert error.reason == "provider_usage_settlement_error"
        else:
            raise AssertionError("over-bound usage must fail closed")
        settlement = _strict_json_file(
            settlement_dir / "acquisition_failure.json"
        )["physical_provider_usage"]
        assert settlement["attempts"] == 1
        assert settlement["responses_returned"] == 1
        assert settlement["successes"] == 0
        assert settlement["failures"] == 1
        assert settlement["input_tokens"] == MAX_INPUT_TOKENS_PER_REQUEST + 1
        assert settlement["actual_cost_usd"] > 0.0

        before = PhysicalProviderLedger(
            PhysicalProviderBudget(max_requests=0, max_cost_usd=0.0)
        ).snapshot()
        zero = PhysicalProviderLedger(
            PhysicalProviderBudget(max_requests=0, max_cost_usd=0.0)
        )
        try:
            zero.reserve()
        except RuntimeError:
            pass
        else:
            raise AssertionError("physical reservation must fail before mutation")
        assert zero.snapshot() == before
    print("countdown OpenAI GPT-5.6 dev self-test: PASS")


def _sdk_version() -> str | None:
    try:
        return importlib.metadata.version("openai")
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
            "countdown OpenAI GPT-5.6 dev replay: PASS",
            _canonical_json(summary["data_quality"]),
        )
        return
    if args.output_dir is None:
        parser.error("provider runs require --output-dir")

    if args.run_fake_dev:
        scorer = OpenAICountdownScorer(
            _FakeClient(),
            model=FAKE_MODEL,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            reasoning_effort=REASONING_EFFORT,
        )
        provider_mode = "fake"
    else:
        observed_sdk = _sdk_version()
        if observed_sdk != PINNED_SDK_VERSION:
            parser.error(
                f"OpenAI SDK must be exactly {PINNED_SDK_VERSION}; "
                f"observed {observed_sdk!r}"
            )
        if not os.environ.get("OPENAI_API_KEY"):
            parser.error("OPENAI_API_KEY is not set in the process environment")
        if os.environ.get("OPENAI_LOG"):
            parser.error("OPENAI_LOG must be unset for secret-safe live acquisition")
        if os.environ.get("OPENAI_BASE_URL"):
            parser.error("OPENAI_BASE_URL must be unset for provider identity")
        if os.environ.get("OPENAI_CUSTOM_HEADERS"):
            parser.error("OPENAI_CUSTOM_HEADERS must be unset for audited requests")
        if os.environ.get("OPENAI_ORG_ID"):
            parser.error("OPENAI_ORG_ID must be unset for audited request identity")
        if os.environ.get("OPENAI_PROJECT_ID"):
            parser.error("OPENAI_PROJECT_ID must be unset for audited request identity")
        scorer = OpenAICountdownScorer.from_environment(
            model=PINNED_MODEL,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            reasoning_effort=REASONING_EFFORT,
            base_url="https://api.openai.com/v1",
            max_retries=0,
            timeout=30.0,
        )
        provider_mode = "live"
    try:
        summary = _run_pipeline(scorer, args.output_dir, provider_mode=provider_mode)
    except AcquisitionFailure as error:
        print(
            "countdown OpenAI GPT-5.6 dev run: FAILED_CLOSED",
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
        "countdown OpenAI GPT-5.6 dev run: PASS",
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
