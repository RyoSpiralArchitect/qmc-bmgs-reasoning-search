#!/usr/bin/env python3
"""OpenAI Responses API scorer for canonical Countdown action sets.

The adapter sends only the target, canonical state, ruleset identifier, and
complete legal-action list. GPT-5.6 Sol returns one bounded integer score per
action through strict Structured Outputs. Returned bytes are validated again
locally and retained only as allowlisted replay evidence.

Transport errors propagate. A returned response that is incomplete, refused,
identity-mismatched, or semantically invalid is represented as a recovered
neutral score vector; the development acquisition runner rejects such rows and
fails closed without a free retry.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Mapping, Sequence

from qmc_bmgs.benchmarks.countdown import (
    RULESET_ID,
    CountdownAction,
    CountdownState,
)
from qmc_bmgs.countdown_scoring import (
    ScoreResponseError,
    canonical_actions,
    decode_scores,
    score_output_schema,
)


PROVIDER_NAME = "openai"
API_ENDPOINT = "/v1/responses"
API_VERSION = "responses/v1"
ADAPTER_SCHEMA_VERSION = "qmc-bmgs-openai-countdown-scorer/v1"
OUTPUT_SCHEMA_NAME = "countdown_action_scores"
REASONING_EFFORT = "none"
SYSTEM_INSTRUCTION = (
    "Score every supplied legal Countdown action for progress toward the supplied "
    "target. Return only the requested JSON object and no rationale. Use each "
    "action_id exactly once. Every score must be an integer from 0 through 1000; "
    "higher means more promising."
)


def _canonical_json(payload: Any) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_json(payload: Any) -> str:
    return _sha256_text(_canonical_json(payload))


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _plain_optional_int(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _sdk_version() -> str | None:
    try:
        return importlib.metadata.version("openai")
    except importlib.metadata.PackageNotFoundError:
        return None


@dataclass(frozen=True)
class ScoredCountdownAction:
    action_id: int
    action: CountdownAction
    score: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.to_dict(),
            "action_id": self.action_id,
            "score": self.score,
        }


@dataclass(frozen=True)
class OpenAIScoreResult:
    scored_actions: tuple[ScoredCountdownAction, ...]
    metadata: dict[str, Any]

    @property
    def recovered(self) -> bool:
        return bool(self.metadata["response_validation"]["recovered"])

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "adapter_schema_version": ADAPTER_SCHEMA_VERSION,
            "metadata": self.metadata,
            "scored_actions": [row.to_dict() for row in self.scored_actions],
        }
        _canonical_json(payload)
        return payload


class OpenAICountdownScorer:
    """One-request GPT-5.6 scorer using strict Responses API JSON output."""

    def __init__(
        self,
        client: Any,
        *,
        model: str,
        max_output_tokens: int = 512,
        reasoning_effort: str = REASONING_EFFORT,
    ) -> None:
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must be a non-empty string")
        if type(max_output_tokens) is not int or max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be a positive plain integer")
        if reasoning_effort != REASONING_EFFORT:
            raise ValueError(f"reasoning_effort must be {REASONING_EFFORT!r}")
        responses = getattr(client, "responses", None)
        if responses is None or not callable(getattr(responses, "create", None)):
            raise TypeError("client must expose responses.create")
        self.client = client
        self.model = model.strip()
        self.max_output_tokens = max_output_tokens
        # Shared acquisition code historically names this field max_tokens.
        self.max_tokens = max_output_tokens
        self.reasoning_effort = reasoning_effort

    @classmethod
    def from_environment(
        cls,
        *,
        model: str,
        max_output_tokens: int = 512,
        reasoning_effort: str = REASONING_EFFORT,
        **client_options: Any,
    ) -> OpenAICountdownScorer:
        """Build the SDK lazily and leave credential resolution to the SDK."""

        try:
            from openai import OpenAI
        except ImportError as error:
            raise RuntimeError(
                "OpenAI SDK is not installed; inject a compatible client or "
                "install the optional provider dependency"
            ) from error
        return cls(
            OpenAI(**client_options),
            model=model,
            max_output_tokens=max_output_tokens,
            reasoning_effort=reasoning_effort,
        )

    @staticmethod
    def _canonical_actions(
        state: CountdownState,
        legal_actions: Sequence[CountdownAction],
    ) -> tuple[CountdownAction, ...]:
        return canonical_actions(state, legal_actions)

    @staticmethod
    def _output_schema(action_count: int) -> dict[str, Any]:
        return score_output_schema(action_count)

    @staticmethod
    def _decode_scores(text: str, action_count: int) -> tuple[int, ...]:
        return decode_scores(text, action_count)

    @staticmethod
    def _response_text(response: Any) -> tuple[str, str, tuple[str, ...]]:
        output = _field(response, "output")
        if not isinstance(output, Sequence) or isinstance(output, (str, bytes)):
            raise ScoreResponseError("missing_output_items")
        item_types = tuple(_field(item, "type") for item in output)
        if any(
            not isinstance(item_type, str)
            or item_type not in {"message", "reasoning"}
            for item_type in item_types
        ):
            raise ScoreResponseError("unexpected_output_item")
        messages = [item for item in output if _field(item, "type") == "message"]
        if len(messages) != 1:
            raise ScoreResponseError("expected_one_message")
        message = messages[0]
        if _field(message, "role") != "assistant":
            raise ScoreResponseError("unexpected_message_role")
        if _field(message, "status") != "completed":
            raise ScoreResponseError("incomplete_message")
        content = _field(message, "content")
        if not isinstance(content, Sequence) or isinstance(content, (str, bytes)):
            raise ScoreResponseError("missing_content_blocks")
        refusals = [item for item in content if _field(item, "type") == "refusal"]
        if refusals:
            raise ScoreResponseError("provider_refusal")
        text_blocks = [item for item in content if _field(item, "type") == "output_text"]
        if len(content) != 1 or len(text_blocks) != 1:
            raise ScoreResponseError("expected_one_output_text_block")
        text = _field(text_blocks[0], "text")
        if not isinstance(text, str) or not text.strip():
            raise ScoreResponseError("empty_output_text")
        message_id = _field(message, "id")
        if not isinstance(message_id, str) or not message_id.strip():
            raise ScoreResponseError("missing_message_id")
        return text, message_id, item_types

    @staticmethod
    def _usage_metadata(response: Any) -> dict[str, int | None]:
        usage = _field(response, "usage")
        input_details = _field(usage, "input_tokens_details")
        output_details = _field(usage, "output_tokens_details")
        return {
            "cache_write_tokens": _plain_optional_int(
                _field(input_details, "cache_write_tokens")
            ),
            "cached_tokens": _plain_optional_int(
                _field(input_details, "cached_tokens")
            ),
            "input_tokens": _plain_optional_int(_field(usage, "input_tokens")),
            "output_tokens": _plain_optional_int(_field(usage, "output_tokens")),
            "reasoning_tokens": _plain_optional_int(
                _field(output_details, "reasoning_tokens")
            ),
            "total_tokens": _plain_optional_int(_field(usage, "total_tokens")),
        }

    def score_actions(
        self,
        *,
        target: int,
        state: CountdownState,
        legal_actions: Sequence[CountdownAction],
    ) -> OpenAIScoreResult:
        if type(target) is not int or target <= 0:
            raise ValueError("target must be a positive plain integer")
        actions = self._canonical_actions(state, legal_actions)
        provider_payload = {
            "legal_actions": [
                {"action_id": action_id, **action.to_dict()}
                for action_id, action in enumerate(actions)
            ],
            "ruleset_id": RULESET_ID,
            "state": list(state),
            "target": target,
        }
        schema = self._output_schema(len(actions))
        schema_name = f"{OUTPUT_SCHEMA_NAME}_{len(actions)}"
        request = {
            "input": _canonical_json(provider_payload),
            "instructions": SYSTEM_INSTRUCTION,
            "max_output_tokens": self.max_output_tokens,
            "model": self.model,
            "reasoning": {"effort": self.reasoning_effort},
            "service_tier": "default",
            "store": False,
            "text": {
                "format": {
                    "name": schema_name,
                    "schema": schema,
                    "strict": True,
                    "type": "json_schema",
                },
                "verbosity": "low",
            },
            "truncation": "disabled",
        }

        response = self.client.responses.create(**request)
        response_text: str | None = None
        message_id: str | None = None
        output_item_types: tuple[str, ...] | None = None
        recovery_reason: str | None = None
        response_model = _field(response, "model")
        response_status = _field(response, "status")
        response_id = _field(response, "id")
        service_tier = _field(response, "service_tier")
        try:
            if not isinstance(response_id, str) or not response_id.strip():
                raise ScoreResponseError("missing_response_id")
            if response_model != self.model:
                raise ScoreResponseError("model_identity_mismatch")
            if response_status != "completed":
                raise ScoreResponseError("unexpected_response_status")
            if _field(response, "error") is not None:
                raise ScoreResponseError("response_error")
            if _field(response, "incomplete_details") is not None:
                raise ScoreResponseError("incomplete_response")
            if service_tier != "default":
                raise ScoreResponseError("service_tier_mismatch")
            response_text, message_id, output_item_types = self._response_text(response)
            scores = self._decode_scores(response_text, len(actions))
        except ScoreResponseError as error:
            scores = (0,) * len(actions)
            recovery_reason = error.reason

        scored_actions = tuple(
            ScoredCountdownAction(action_id, action, scores[action_id])
            for action_id, action in enumerate(actions)
        )
        metadata = {
            "action_count": len(actions),
            "api_endpoint": API_ENDPOINT,
            "api_version": API_VERSION,
            "message_id": message_id,
            "model_requested": self.model,
            "model_returned": (
                response_model if isinstance(response_model, str) else None
            ),
            "openai_sdk_version": _sdk_version(),
            "output_item_types": (
                list(output_item_types) if output_item_types is not None else None
            ),
            "output_schema_digest": _sha256_json(schema),
            "provider": PROVIDER_NAME,
            "provider_payload": provider_payload,
            "provider_payload_digest": _sha256_json(provider_payload),
            "request_digest": _sha256_json(request),
            "request_metadata": {
                "max_output_tokens": self.max_output_tokens,
                "output_format": "json_schema",
                "output_schema_name": schema_name,
                "reasoning_effort": self.reasoning_effort,
                "service_tier": "default",
                "store": False,
                "text_verbosity": "low",
                "truncation": "disabled",
            },
            "response_id": response_id if isinstance(response_id, str) else None,
            "response_status": (
                response_status if isinstance(response_status, str) else None
            ),
            "response_text_digest": (
                _sha256_text(response_text) if response_text is not None else None
            ),
            "response_text_for_replay": response_text,
            "response_validation": {
                "recovered": recovery_reason is not None,
                "recovery_policy": (
                    "neutral_all_zero_scores" if recovery_reason is not None else None
                ),
                "recovery_reason": recovery_reason,
                "status": "recovered" if recovery_reason is not None else "valid",
            },
            "service_tier_returned": (
                service_tier if isinstance(service_tier, str) else None
            ),
            "system_instruction_digest": _sha256_text(SYSTEM_INSTRUCTION),
            "tokens": self._usage_metadata(response),
        }
        result = OpenAIScoreResult(scored_actions, metadata)
        result.to_dict()
        return result


class _FakeResponses:
    def __init__(self, responses: Sequence[Any]) -> None:
        self._responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    def create(self, **request: Any) -> Any:
        self.requests.append(request)
        if not self._responses:
            raise AssertionError("fake client has no remaining response")
        return self._responses.pop(0)


class _FakeClient:
    def __init__(self, responses: Sequence[Any]) -> None:
        self.responses = _FakeResponses(responses)
        self.api_key = "fake-secret-that-must-not-appear"


def _fake_response(
    text: str,
    *,
    response_id: str,
    message_id: str,
    model: str = "fake-gpt-5.6-sol",
    status: str = "completed",
    service_tier: str = "default",
) -> Any:
    return SimpleNamespace(
        id=response_id,
        model=model,
        status=status,
        service_tier=service_tier,
        error=None,
        incomplete_details=None,
        output=[
            SimpleNamespace(
                id=message_id,
                type="message",
                role="assistant",
                status="completed",
                content=[SimpleNamespace(type="output_text", text=text)],
            )
        ],
        usage=SimpleNamespace(
            input_tokens=41,
            input_tokens_details=SimpleNamespace(
                cache_write_tokens=0,
                cached_tokens=0,
            ),
            output_tokens=23,
            output_tokens_details=SimpleNamespace(reasoning_tokens=0),
            total_tokens=64,
        ),
    )


def _run_self_test() -> None:
    state = (1, 2)
    actions = (CountdownAction(1, 2, "+"),)
    valid_text = '{"scores":[{"action_id":0,"score":731}]}'
    valid = _fake_response(
        valid_text,
        response_id="resp_valid",
        message_id="msg_valid",
    )
    client = _FakeClient((valid,))
    scorer = OpenAICountdownScorer(client, model="fake-gpt-5.6-sol")
    result = scorer.score_actions(target=3, state=state, legal_actions=actions)
    assert not result.recovered
    assert result.scored_actions[0].score == 731
    assert result.metadata["tokens"] == {
        "cache_write_tokens": 0,
        "cached_tokens": 0,
        "input_tokens": 41,
        "output_tokens": 23,
        "reasoning_tokens": 0,
        "total_tokens": 64,
    }
    request = client.responses.requests[0]
    assert request["model"] == "fake-gpt-5.6-sol"
    assert request["reasoning"] == {"effort": "none"}
    assert request["store"] is False
    assert request["text"]["format"]["strict"] is True
    serialized = _canonical_json(result.to_dict())
    assert "fake-secret-that-must-not-appear" not in serialized
    assert "api_key" not in serialized

    refused = _fake_response(
        valid_text,
        response_id="resp_refused",
        message_id="msg_refused",
    )
    refused.output[0].content = [
        SimpleNamespace(type="refusal", refusal="declined")
    ]
    recovered = OpenAICountdownScorer(
        _FakeClient((refused,)),
        model="fake-gpt-5.6-sol",
    ).score_actions(target=3, state=state, legal_actions=actions)
    assert recovered.recovered
    assert recovered.metadata["response_validation"]["recovery_reason"] == (
        "provider_refusal"
    )
    assert recovered.scored_actions[0].score == 0

    incomplete = _fake_response(
        valid_text,
        response_id="resp_incomplete",
        message_id="msg_incomplete",
        status="incomplete",
    )
    recovered = OpenAICountdownScorer(
        _FakeClient((incomplete,)),
        model="fake-gpt-5.6-sol",
    ).score_actions(target=3, state=state, legal_actions=actions)
    assert recovered.recovered
    assert recovered.metadata["response_validation"]["recovery_reason"] == (
        "unexpected_response_status"
    )

    invalid = _fake_response(
        '{"scores":[{"action_id":0,"score":1001}]}',
        response_id="resp_invalid",
        message_id="msg_invalid",
    )
    recovered = OpenAICountdownScorer(
        _FakeClient((invalid,)),
        model="fake-gpt-5.6-sol",
    ).score_actions(target=3, state=state, legal_actions=actions)
    assert recovered.recovered
    assert recovered.metadata["response_validation"]["recovery_reason"] == (
        "invalid_score_type"
    )

    unexpected = _fake_response(
        valid_text,
        response_id="resp_unexpected",
        message_id="msg_unexpected",
    )
    unexpected.output.insert(0, SimpleNamespace(type="tool_call"))
    recovered = OpenAICountdownScorer(
        _FakeClient((unexpected,)),
        model="fake-gpt-5.6-sol",
    ).score_actions(target=3, state=state, legal_actions=actions)
    assert recovered.recovered
    assert recovered.metadata["response_validation"]["recovery_reason"] == (
        "unexpected_output_item"
    )

    wrong_role = _fake_response(
        valid_text,
        response_id="resp_wrong_role",
        message_id="msg_wrong_role",
    )
    wrong_role.output[0].role = "user"
    recovered = OpenAICountdownScorer(
        _FakeClient((wrong_role,)),
        model="fake-gpt-5.6-sol",
    ).score_actions(target=3, state=state, legal_actions=actions)
    assert recovered.recovered
    assert recovered.metadata["response_validation"]["recovery_reason"] == (
        "unexpected_message_role"
    )
    print("OpenAI Countdown scorer self-test: PASS")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if not args.self_test:
        parser.error("this provider module exposes only --self-test")
    _run_self_test()


if __name__ == "__main__":
    main()
