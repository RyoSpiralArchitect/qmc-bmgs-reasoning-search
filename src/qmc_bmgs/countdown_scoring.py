"""Provider-neutral validation primitives for Countdown action scorers."""

from __future__ import annotations

import json
from typing import Any, Sequence

from qmc_bmgs.benchmarks.countdown import CountdownAction, CountdownState


class ScoreResponseError(ValueError):
    """Stable local validation failure for a provider score response."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def canonical_actions(
    state: CountdownState,
    legal_actions: Sequence[CountdownAction],
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
        action.evaluate()
    return tuple(sorted(actions, key=CountdownAction.sort_key))


def score_output_schema(action_count: int) -> dict[str, Any]:
    if type(action_count) is not int or action_count <= 0:
        raise ValueError("action_count must be a positive plain integer")
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
                # Provider schema subsets differ. Exact cardinality, score
                # range, and one-of-each action identity remain local guards.
                "type": "array",
            }
        },
        "required": ["scores"],
        "type": "object",
    }


def decode_scores(text: str, action_count: int) -> tuple[int, ...]:
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
