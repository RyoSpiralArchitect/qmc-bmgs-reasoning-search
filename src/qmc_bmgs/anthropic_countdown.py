#!/usr/bin/env python3
"""Anthropic-backed action scorer for canonical Countdown states.

The adapter deliberately receives no original sources, witness, search trace,
value estimate, or task fingerprint.  A provider request contains only the
current target, canonical state, and complete legal-action list.  Responses use
Anthropic's JSON-schema output format and are validated again locally.

Transport errors are not disguised as model scores.  A syntactically or
semantically invalid provider response is recovered deterministically as a
neutral all-zero score vector, with the recovery reason recorded in metadata.

The Anthropic dependency is optional at import time.  Callers may inject any
client exposing ``client.messages.create``; ``from_environment`` imports the
installed SDK lazily and lets the SDK resolve credentials without recording
them here.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Mapping, Sequence

from qmc_bmgs.benchmarks.countdown import (
    RULESET_ID,
    CountdownAction,
    CountdownState,
)


PROVIDER_NAME = "anthropic"
API_ENDPOINT = "/v1/messages"
API_VERSION = "2023-06-01"
ADAPTER_SCHEMA_VERSION = "qmc-bmgs-anthropic-countdown-scorer/v1"
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
        return importlib.metadata.version("anthropic")
    except importlib.metadata.PackageNotFoundError:
        return None


class ScoreResponseError(ValueError):
    """Stable local validation failure for provider output."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


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
class AnthropicScoreResult:
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
        # Strict serialization is part of the provider boundary contract.
        _canonical_json(payload)
        return payload


class AnthropicCountdownScorer:
    """One-request strict-JSON scorer for a legal Countdown action set."""

    def __init__(
        self,
        client: Any,
        *,
        model: str,
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> None:
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must be a non-empty string")
        if type(max_tokens) is not int or max_tokens <= 0:
            raise ValueError("max_tokens must be a positive plain integer")
        if type(temperature) not in {int, float} or isinstance(temperature, bool):
            raise ValueError("temperature must be a finite number")
        if not math.isfinite(float(temperature)) or not 0.0 <= temperature <= 1.0:
            raise ValueError("temperature must be finite and in [0, 1]")
        messages = getattr(client, "messages", None)
        if messages is None or not callable(getattr(messages, "create", None)):
            raise TypeError("client must expose messages.create")
        self.client = client
        self.model = model.strip()
        self.max_tokens = max_tokens
        self.temperature = float(temperature)

    @classmethod
    def from_environment(
        cls,
        *,
        model: str,
        max_tokens: int = 512,
        temperature: float = 0.0,
        **client_options: Any,
    ) -> AnthropicCountdownScorer:
        """Build the SDK client lazily; credentials are never copied to metadata."""

        try:
            from anthropic import Anthropic
        except ImportError as error:
            raise RuntimeError(
                "Anthropic SDK is not installed; inject a compatible client or "
                "install the optional provider dependency"
            ) from error
        client = Anthropic(**client_options)
        return cls(
            client,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    @staticmethod
    def _canonical_actions(
        state: CountdownState, legal_actions: Sequence[CountdownAction]
    ) -> tuple[CountdownAction, ...]:
        canonical_state = tuple(state)
        if not canonical_state:
            raise ValueError("state cannot be empty")
        if any(type(value) is not int or value <= 0 for value in canonical_state):
            raise ValueError("state must contain positive plain integers")
        if tuple(sorted(canonical_state)) != canonical_state:
            raise ValueError("state must be a canonical sorted multiset")
        actions = tuple(legal_actions)
        if not actions:
            raise ValueError("legal_actions cannot be empty")
        if any(not isinstance(action, CountdownAction) for action in actions):
            raise TypeError("legal_actions must contain CountdownAction values")
        if len(actions) != len(set(actions)):
            raise ValueError("legal_actions cannot contain duplicate labels")

        available: dict[int, int] = {}
        for value in canonical_state:
            available[value] = available.get(value, 0) + 1
        for action in actions:
            required = {action.left: 1, action.right: 1}
            if action.left == action.right:
                required[action.left] = 2
            if any(
                available.get(value, 0) < count for value, count in required.items()
            ):
                raise ValueError("legal action references unavailable operands")
            # Enforce positive subtraction and exact division before transmission.
            action.evaluate()
        return tuple(sorted(actions, key=CountdownAction.sort_key))

    @staticmethod
    def _output_schema(action_count: int) -> dict[str, Any]:
        action_ids = list(range(action_count))
        return {
            "additionalProperties": False,
            "properties": {
                "scores": {
                    "items": {
                        "additionalProperties": False,
                        "properties": {
                            "action_id": {
                                "enum": action_ids,
                                "type": "integer",
                            },
                            "score": {
                                "description": (
                                    "Integer promise score from 0 through 1000, "
                                    "validated locally after decoding."
                                ),
                                "type": "integer",
                            },
                        },
                        "required": ["action_id", "score"],
                        "type": "object",
                    },
                    # The raw-schema subset omits array cardinality
                    # constraints. Exact cardinality, score range, and the
                    # one-of-each action_id invariant are enforced again by
                    # ``_decode_scores`` before a response can be used.
                    "type": "array",
                }
            },
            "required": ["scores"],
            "type": "object",
        }

    @staticmethod
    def _response_text(response: Any) -> str:
        content = _field(response, "content")
        if not isinstance(content, Sequence) or isinstance(content, (str, bytes)):
            raise ScoreResponseError("missing_content_blocks")
        if len(content) != 1 or _field(content[0], "type") != "text":
            raise ScoreResponseError("expected_one_text_block")
        text = _field(content[0], "text")
        if not isinstance(text, str):
            raise ScoreResponseError("expected_one_text_block")
        if not text.strip():
            raise ScoreResponseError("empty_text_block")
        return text

    @staticmethod
    def _decode_scores(text: str, action_count: int) -> tuple[int, ...]:
        def reject_constant(_: str) -> None:
            raise ScoreResponseError("non_finite_json_constant")

        def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, value in pairs:
                if key in result:
                    raise ScoreResponseError("duplicate_json_key")
                result[key] = value
            return result

        try:
            payload = json.loads(
                text,
                object_pairs_hook=reject_duplicate_keys,
                parse_constant=reject_constant,
            )
        except ScoreResponseError:
            raise
        except (json.JSONDecodeError, TypeError) as error:
            raise ScoreResponseError("invalid_json") from error
        if not isinstance(payload, dict) or set(payload) != {"scores"}:
            raise ScoreResponseError("invalid_top_level_shape")
        rows = payload["scores"]
        if not isinstance(rows, list) or len(rows) != action_count:
            raise ScoreResponseError("wrong_score_count")

        scores_by_id: dict[int, int] = {}
        for row in rows:
            if not isinstance(row, dict) or set(row) != {"action_id", "score"}:
                raise ScoreResponseError("invalid_score_row_shape")
            action_id = row["action_id"]
            score = row["score"]
            if type(action_id) is not int or not 0 <= action_id < action_count:
                raise ScoreResponseError("invalid_action_id")
            if action_id in scores_by_id:
                raise ScoreResponseError("duplicate_action_id")
            if type(score) is not int or not 0 <= score <= 1000:
                raise ScoreResponseError("invalid_score_type")
            scores_by_id[action_id] = score
        if set(scores_by_id) != set(range(action_count)):
            raise ScoreResponseError("incomplete_action_ids")
        return tuple(scores_by_id[action_id] for action_id in range(action_count))

    @staticmethod
    def _usage_metadata(response: Any) -> dict[str, int | None]:
        usage = _field(response, "usage")
        return {
            "cache_creation_input_tokens": _plain_optional_int(
                _field(usage, "cache_creation_input_tokens")
            ),
            "cache_read_input_tokens": _plain_optional_int(
                _field(usage, "cache_read_input_tokens")
            ),
            "input_tokens": _plain_optional_int(_field(usage, "input_tokens")),
            "output_tokens": _plain_optional_int(_field(usage, "output_tokens")),
        }

    def score_actions(
        self,
        *,
        target: int,
        state: CountdownState,
        legal_actions: Sequence[CountdownAction],
    ) -> AnthropicScoreResult:
        if type(target) is not int or target <= 0:
            raise ValueError("target must be a positive plain integer")
        actions = self._canonical_actions(state, legal_actions)
        action_records = [
            {"action_id": action_id, **action.to_dict()}
            for action_id, action in enumerate(actions)
        ]
        provider_payload = {
            "legal_actions": action_records,
            "ruleset_id": RULESET_ID,
            "state": list(state),
            "target": target,
        }
        schema = self._output_schema(len(actions))
        request = {
            "max_tokens": self.max_tokens,
            "messages": [
                {
                    "content": _canonical_json(provider_payload),
                    "role": "user",
                }
            ],
            "model": self.model,
            "output_config": {
                "format": {
                    "schema": schema,
                    "type": "json_schema",
                }
            },
            "service_tier": "standard_only",
            "system": SYSTEM_INSTRUCTION,
            "temperature": self.temperature,
        }

        # Any transport/provider exception propagates.  Only returned content is
        # eligible for deterministic local recovery.
        response = self.client.messages.create(**request)
        response_text: str | None = None
        recovery_reason: str | None = None
        response_model = _field(response, "model")
        stop_reason = _field(response, "stop_reason")
        response_id = _field(response, "id")
        try:
            response_text = self._response_text(response)
            if not isinstance(response_id, str) or not response_id.strip():
                raise ScoreResponseError("missing_response_id")
            if response_model != self.model:
                raise ScoreResponseError("model_identity_mismatch")
            if stop_reason != "end_turn":
                raise ScoreResponseError("unexpected_stop_reason")
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
            "anthropic_sdk_version": _sdk_version(),
            "model_requested": self.model,
            "model_returned": response_model
            if isinstance(response_model, str)
            else None,
            "output_schema_digest": _sha256_json(schema),
            "provider": PROVIDER_NAME,
            "provider_payload": provider_payload,
            "provider_payload_digest": _sha256_json(provider_payload),
            "request_digest": _sha256_json(request),
            "request_metadata": {
                "max_tokens": self.max_tokens,
                "output_format": "json_schema",
                "service_tier": "standard_only",
                "temperature": self.temperature,
                "user_message_count": 1,
            },
            "response_id": response_id if isinstance(response_id, str) else None,
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
            "stop_reason": stop_reason if isinstance(stop_reason, str) else None,
            "system_instruction_digest": _sha256_text(SYSTEM_INSTRUCTION),
            "tokens": self._usage_metadata(response),
        }
        result = AnthropicScoreResult(scored_actions, metadata)
        result.to_dict()
        return result


class _FakeMessages:
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
        self.messages = _FakeMessages(responses)
        # The adapter must never inspect or serialize this attribute.
        self.api_key = "fake-secret-that-must-not-appear"


def _fake_response(
    text: str, *, response_id: str, model: str = "fake-request-model"
) -> Any:
    return SimpleNamespace(
        id=response_id,
        model=model,
        stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(
            input_tokens=37,
            output_tokens=19,
            cache_creation_input_tokens=3,
            cache_read_input_tokens=5,
        ),
    )


def _run_self_test() -> None:
    actions = (
        CountdownAction(2, 4, "+"),
        CountdownAction(2, 4, "*"),
        CountdownAction(4, 2, "-"),
        CountdownAction(4, 2, "/"),
    )
    valid_text = _canonical_json(
        {
            "scores": [
                {"action_id": 3, "score": 25},
                {"action_id": 1, "score": 1000},
                {"action_id": 0, "score": 125},
                {"action_id": 2, "score": 0},
            ]
        }
    )
    invalid_text = _canonical_json(
        {
            "scores": [
                {"action_id": 0, "score": 1},
                {"action_id": 0, "score": 2},
                {"action_id": 2, "score": 3},
                {"action_id": 3, "score": 4},
            ]
        }
    )
    duplicate_key_text = (
        '{"scores":[],"scores":'
        + _canonical_json(json.loads(valid_text)["scores"])
        + "}"
    )
    extra_block_response = _fake_response(valid_text, response_id="msg_extra_block")
    extra_block_response.content.append(SimpleNamespace(type="tool_use", id="tool_1"))
    missing_id_response = _fake_response(valid_text, response_id="msg_placeholder")
    missing_id_response.id = None
    fake = _FakeClient(
        [
            _fake_response(valid_text, response_id="msg_valid"),
            _fake_response(invalid_text, response_id="msg_invalid"),
            _fake_response(valid_text, response_id="msg_repeat"),
            _fake_response(duplicate_key_text, response_id="msg_duplicate_key"),
            extra_block_response,
            missing_id_response,
        ]
    )
    scorer = AnthropicCountdownScorer(fake, model="fake-request-model")
    first = scorer.score_actions(target=24, state=(2, 4), legal_actions=actions)
    assert not first.recovered
    assert [row.score for row in first.scored_actions] == [125, 1000, 0, 25]
    assert first.metadata["tokens"] == {
        "cache_creation_input_tokens": 3,
        "cache_read_input_tokens": 5,
        "input_tokens": 37,
        "output_tokens": 19,
    }

    request = fake.messages.requests[0]
    user_payload = json.loads(request["messages"][0]["content"])
    assert set(user_payload) == {
        "legal_actions",
        "ruleset_id",
        "state",
        "target",
    }
    assert set(user_payload["legal_actions"][0]) == {
        "action_id",
        "left",
        "operator",
        "right",
    }
    assert request["output_config"]["format"]["type"] == "json_schema"
    serialized_schema = _canonical_json(request["output_config"]["format"]["schema"])
    assert all(
        keyword not in serialized_schema
        for keyword in ('"minimum"', '"maximum"', '"minItems"', '"maxItems"')
    )
    assert request["service_tier"] == "standard_only"
    assert request["temperature"] == 0.0

    recovered = scorer.score_actions(target=24, state=(2, 4), legal_actions=actions)
    assert recovered.recovered
    assert recovered.metadata["response_validation"]["recovery_reason"] == (
        "duplicate_action_id"
    )
    assert all(row.score == 0 for row in recovered.scored_actions)

    repeated = scorer.score_actions(target=24, state=(2, 4), legal_actions=actions)
    assert repeated.metadata["request_digest"] == first.metadata["request_digest"]
    duplicate_key = scorer.score_actions(target=24, state=(2, 4), legal_actions=actions)
    assert duplicate_key.metadata["response_validation"]["recovery_reason"] == (
        "duplicate_json_key"
    )
    extra_block = scorer.score_actions(target=24, state=(2, 4), legal_actions=actions)
    assert extra_block.metadata["response_validation"]["recovery_reason"] == (
        "expected_one_text_block"
    )
    missing_id = scorer.score_actions(target=24, state=(2, 4), legal_actions=actions)
    assert missing_id.metadata["response_validation"]["recovery_reason"] == (
        "missing_response_id"
    )
    try:
        scorer._decode_scores('{"scores":[]}', len(actions))
    except ScoreResponseError as error:
        assert error.reason == "wrong_score_count"
    else:
        raise AssertionError("local decoder must enforce exact response cardinality")
    serialized = _canonical_json(
        {
            "first": first.to_dict(),
            "recovered": recovered.to_dict(),
            "repeated": repeated.to_dict(),
            "strict_failures": [
                duplicate_key.to_dict(),
                extra_block.to_dict(),
                missing_id.to_dict(),
            ],
        }
    )
    assert "fake-secret-that-must-not-appear" not in serialized
    assert "api_key" not in serialized
    assert "NaN" not in serialized and "Infinity" not in serialized

    try:
        scorer.score_actions(
            target=24,
            state=(2, 4),
            legal_actions=(CountdownAction(2, 3, "+"),),
        )
    except ValueError as error:
        assert "unavailable operands" in str(error)
    else:
        raise AssertionError("non-legal action must be rejected before provider call")
    assert len(fake.messages.requests) == 6
    print("anthropic countdown scorer self-test: PASS")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if not args.self_test:
        parser.error("this provider module exposes only --self-test")
    _run_self_test()


if __name__ == "__main__":
    main()
