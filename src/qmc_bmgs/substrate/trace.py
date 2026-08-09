"""Canonical, hash-chained event traces for Track A search runs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping

from qmc_bmgs.substrate.budget import (
    TRACK_A_LEDGER_SCHEMA_VERSION,
    TRACK_A_WORK_AXES,
    TrackAChargeReceipt,
)


TRACE_SCHEMA_VERSION = "qmc-bmgs-track-a-event-trace/v1"
RUN_IDENTITY_SCHEMA_VERSION = "qmc-bmgs-track-a-run-identity/v1"
GENESIS_DIGEST = "0" * 64
MAX_TRACE_EVENTS = 1_000_000


class TraceValidationError(ValueError):
    """Raised when a persisted deterministic trace fails closed validation."""


def canonical_json(payload: Any) -> str:
    """Serialize deterministic JSON while rejecting non-finite numbers."""

    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def sha256_json(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def strict_json_loads(text: str) -> Any:
    """Load JSON while rejecting duplicate keys and non-finite constants."""

    def reject_constant(value: str) -> None:
        raise TraceValidationError(f"non-finite JSON constant: {value}")

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise TraceValidationError(f"duplicate JSON object key: {key!r}")
            result[key] = value
        return result

    try:
        return json.loads(
            text,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_constant,
        )
    except json.JSONDecodeError as error:
        raise TraceValidationError(f"invalid JSON: {error.msg}") from error


def canonical_trace_bytes(record: Mapping[str, Any]) -> bytes:
    return (canonical_json(record) + "\n").encode("utf-8")


def _frozen_json_value(payload: Any, *, field_name: str) -> Any:
    try:
        return strict_json_loads(canonical_json(payload))
    except (TypeError, ValueError) as error:
        raise TraceValidationError(
            f"{field_name} must be strict finite JSON"
        ) from error


def _require_nonnegative_int(value: Any, field_name: str) -> int:
    if type(value) is not int or value < 0:
        raise TraceValidationError(
            f"{field_name} must be a non-negative plain integer"
        )
    return value


def _validate_usage_mapping(
    payload: Any,
    *,
    axes: tuple[str, ...],
    field_name: str,
) -> dict[str, int]:
    if not isinstance(payload, dict) or set(payload) != set(axes):
        raise TraceValidationError(f"{field_name} axes do not match work limits")
    return {
        axis: _require_nonnegative_int(payload[axis], f"{field_name}.{axis}")
        for axis in axes
    }


def _is_lower_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _validate_base_run_identity(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise TraceValidationError("run_identity must be a JSON object")
    required = {
        "budget_profile",
        "configuration_id",
        "exploration_seed",
        "generator_metadata_digest",
        "method_id",
        "run_identity_schema_version",
        "selected_source",
        "task_fingerprints",
        "task_manifest_digest",
        "work_limits",
    }
    if set(payload) != required:
        raise TraceValidationError("run identity fields drifted")
    for field_name in (
        "budget_profile",
        "configuration_id",
        "method_id",
    ):
        if not isinstance(payload[field_name], str) or not payload[field_name]:
            raise TraceValidationError(f"run identity {field_name} is invalid")
    if payload["run_identity_schema_version"] != RUN_IDENTITY_SCHEMA_VERSION:
        raise TraceValidationError("unsupported run identity schema")
    if payload["selected_source"] not in {"iid", "sobol"}:
        raise TraceValidationError("run identity selected source is invalid")
    _require_nonnegative_int(
        payload["exploration_seed"],
        "run identity exploration_seed",
    )
    fingerprints = payload["task_fingerprints"]
    if (
        not isinstance(fingerprints, list)
        or not fingerprints
        or any(not _is_lower_sha256(item) for item in fingerprints)
        or len(set(fingerprints)) != len(fingerprints)
    ):
        raise TraceValidationError("run identity task fingerprints are invalid")
    if not _is_lower_sha256(payload["task_manifest_digest"]):
        raise TraceValidationError("run identity task manifest digest is invalid")
    if not _is_lower_sha256(payload["generator_metadata_digest"]):
        raise TraceValidationError("run identity generator metadata digest is invalid")
    _validate_usage_mapping(
        payload["work_limits"],
        axes=TRACK_A_WORK_AXES,
        field_name="run_identity.work_limits",
    )
    return payload


@dataclass
class HashChainedTrace:
    """Append-only deterministic core trace.

    Wall time, RSS samples, paths, timestamps, and process identity belong in a
    separate descriptive envelope. They are intentionally excluded here.
    """

    run_identity: Mapping[str, Any]
    _events: list[dict[str, Any]] = field(default_factory=list, init=False)
    _limits: dict[str, int] = field(default_factory=dict, init=False, repr=False)
    _usage: dict[str, int] = field(default_factory=dict, init=False, repr=False)
    _charge_count: int = field(default=0, init=False, repr=False)
    _poison_reason: str | None = field(default=None, init=False, repr=False)
    _run_identity_digest: str = field(default="", init=False, repr=False)

    def __post_init__(self) -> None:
        frozen = _frozen_json_value(self.run_identity, field_name="run_identity")
        frozen = _validate_base_run_identity(frozen)
        limits = frozen.get("work_limits")
        self._limits = _validate_usage_mapping(
            limits,
            axes=TRACK_A_WORK_AXES,
            field_name="run_identity.work_limits",
        )
        self._usage = {axis: 0 for axis in TRACK_A_WORK_AXES}
        self.run_identity = frozen
        self._run_identity_digest = sha256_json(frozen)

    def assert_identity_unchanged(self) -> None:
        if sha256_json(self.run_identity) != self._run_identity_digest:
            raise TraceValidationError("run identity mutated after trace construction")

    @property
    def event_count(self) -> int:
        return len(self._events)

    @property
    def events(self) -> tuple[dict[str, Any], ...]:
        return tuple(_frozen_json_value(self._events, field_name="events"))

    def append(
        self,
        kind: str,
        payload: Mapping[str, Any],
        *,
        receipt: TrackAChargeReceipt | None = None,
    ) -> dict[str, Any]:
        self.assert_identity_unchanged()
        if self._poison_reason is not None:
            raise TraceValidationError("cannot append to a poisoned trace")
        if not isinstance(kind, str) or not kind:
            raise TraceValidationError("event kind must be a non-empty string")
        frozen_payload = _frozen_json_value(payload, field_name="event payload")
        if not isinstance(frozen_payload, dict):
            raise TraceValidationError("event payload must be a JSON object")
        charge: dict[str, Any] | None = None
        next_usage = self._usage
        if receipt is not None:
            if not isinstance(receipt, TrackAChargeReceipt):
                raise TypeError("receipt must be a TrackAChargeReceipt")
            receipt_payload = receipt.to_dict()
            charge_index = _require_nonnegative_int(
                receipt_payload["charge_index"],
                "receipt.charge_index",
            )
            if charge_index != self._charge_count:
                raise TraceValidationError("receipt charge index is not contiguous")
            frozen_delta = _validate_usage_mapping(
                receipt_payload["increments"],
                axes=TRACK_A_WORK_AXES,
                field_name="receipt.increments",
            )
            if not any(frozen_delta.values()):
                raise TraceValidationError("receipt must contain positive work")
            frozen_usage = _validate_usage_mapping(
                receipt_payload["usage_after"],
                axes=TRACK_A_WORK_AXES,
                field_name="receipt.usage_after",
            )
            next_usage = {
                axis: self._usage[axis] + frozen_delta[axis]
                for axis in TRACK_A_WORK_AXES
            }
            if frozen_usage != next_usage:
                raise TraceValidationError("receipt usage does not close")
            if any(
                next_usage[axis] > self._limits[axis]
                for axis in TRACK_A_WORK_AXES
            ):
                raise TraceValidationError("receipt exceeds trace work limits")
            charge = {
                "charge_index": charge_index,
                "delta": frozen_delta,
                "usage_after": frozen_usage,
            }

        previous = (
            self._events[-1]["event_digest"] if self._events else GENESIS_DIGEST
        )
        core = {
            "charge": charge,
            "index": len(self._events),
            "kind": kind,
            "payload": frozen_payload,
            "previous_event_digest": previous,
        }
        event = {**core, "event_digest": sha256_json(core)}
        self._events.append(event)
        if receipt is not None:
            self._usage = next_usage
            self._charge_count += 1
        return _frozen_json_value(event, field_name="event")

    def poison(self, reason_code: str) -> None:
        if not isinstance(reason_code, str) or not reason_code:
            raise ValueError("poison reason code must be a non-empty string")
        self._poison_reason = reason_code

    def finalize(self, ledger_snapshot: Mapping[str, Any]) -> dict[str, Any]:
        self.assert_identity_unchanged()
        if self._poison_reason is not None:
            raise TraceValidationError(
                f"cannot finalize poisoned trace: {self._poison_reason}"
            )
        frozen_ledger = _frozen_json_value(
            ledger_snapshot,
            field_name="ledger_snapshot",
        )
        if not isinstance(frozen_ledger, dict):
            raise TraceValidationError("ledger_snapshot must be a JSON object")
        core = {
            "event_count": len(self._events),
            "events": self._events,
            "final_event_digest": (
                self._events[-1]["event_digest"]
                if self._events
                else GENESIS_DIGEST
            ),
            "ledger_snapshot": frozen_ledger,
            "run_identity": self.run_identity,
            "schema_version": TRACE_SCHEMA_VERSION,
        }
        record = {**core, "deterministic_digest": sha256_json(core)}
        validate_trace(record)
        return _frozen_json_value(record, field_name="trace record")


def validate_trace(record: Mapping[str, Any]) -> dict[str, Any]:
    """Validate hashes and independently reaggregate every accepted charge."""

    if not isinstance(record, Mapping):
        raise TraceValidationError("trace record must be a JSON object")
    parsed = _frozen_json_value(record, field_name="trace record")
    if not isinstance(parsed, dict) or set(parsed) != {
        "deterministic_digest",
        "event_count",
        "events",
        "final_event_digest",
        "ledger_snapshot",
        "run_identity",
        "schema_version",
    }:
        raise TraceValidationError("trace fields drifted")
    if parsed["schema_version"] != TRACE_SCHEMA_VERSION:
        raise TraceValidationError("unsupported trace schema")
    core = {
        key: value for key, value in parsed.items() if key != "deterministic_digest"
    }
    if parsed["deterministic_digest"] != sha256_json(core):
        raise TraceValidationError("trace deterministic digest mismatch")

    events = parsed["events"]
    if not isinstance(events, list):
        raise TraceValidationError("trace events must be an array")
    if len(events) > MAX_TRACE_EVENTS:
        raise TraceValidationError("trace event count exceeds safety bound")
    event_count = _require_nonnegative_int(
        parsed["event_count"],
        "trace.event_count",
    )
    if event_count != len(events):
        raise TraceValidationError("trace event count mismatch")

    ledger = parsed["ledger_snapshot"]
    if not isinstance(ledger, dict):
        raise TraceValidationError("trace ledger snapshot must be an object")
    if set(ledger) != {
        "charge_count",
        "exhausted_axes",
        "limits",
        "live_storage",
        "overshoot",
        "overshoot_by_axis",
        "peak_live_storage",
        "remaining",
        "schema_version",
        "usage",
    }:
        raise TraceValidationError("ledger snapshot fields drifted")
    if ledger["schema_version"] != TRACK_A_LEDGER_SCHEMA_VERSION:
        raise TraceValidationError("unsupported ledger snapshot schema")
    limits = ledger["limits"]
    usage = ledger["usage"]
    axes = TRACK_A_WORK_AXES
    normalized_limits = _validate_usage_mapping(
        limits,
        axes=axes,
        field_name="ledger limits",
    )
    expected_usage = {axis: 0 for axis in axes}
    accepted_charges = 0

    previous = GENESIS_DIGEST
    for expected_index, event in enumerate(events):
        if not isinstance(event, dict) or set(event) != {
            "charge",
            "event_digest",
            "index",
            "kind",
            "payload",
            "previous_event_digest",
        }:
            raise TraceValidationError("trace event fields drifted")
        event_index = _require_nonnegative_int(
            event["index"],
            "trace event index",
        )
        if event_index != expected_index:
            raise TraceValidationError("trace event index/order mismatch")
        if event["previous_event_digest"] != previous:
            raise TraceValidationError("trace hash chain mismatch")
        if not isinstance(event["kind"], str) or not event["kind"]:
            raise TraceValidationError("trace event kind is invalid")
        if not isinstance(event["payload"], dict):
            raise TraceValidationError("trace event payload is not an object")
        event_core = {
            key: value for key, value in event.items() if key != "event_digest"
        }
        if event["event_digest"] != sha256_json(event_core):
            raise TraceValidationError("trace event digest mismatch")

        charge = event["charge"]
        if charge is not None:
            if not isinstance(charge, dict) or set(charge) != {
                "charge_index",
                "delta",
                "usage_after",
            }:
                raise TraceValidationError("trace charge fields drifted")
            charge_index = _require_nonnegative_int(
                charge["charge_index"],
                "event charge index",
            )
            if charge_index != accepted_charges:
                raise TraceValidationError("event charge index is not contiguous")
            delta = _validate_usage_mapping(
                charge["delta"],
                axes=axes,
                field_name="event charge delta",
            )
            if not any(delta.values()):
                raise TraceValidationError("event charge must contain positive work")
            usage_after = _validate_usage_mapping(
                charge["usage_after"],
                axes=axes,
                field_name="event usage after",
            )
            expected_usage = {
                axis: expected_usage[axis] + delta[axis] for axis in axes
            }
            accepted_charges += 1
            if expected_usage != usage_after:
                raise TraceValidationError("event usage receipt does not close")
            if any(
                expected_usage[axis] > normalized_limits[axis] for axis in axes
            ):
                raise TraceValidationError("event usage exceeds a hard limit")
        previous = event["event_digest"]

    expected_final = events[-1]["event_digest"] if events else GENESIS_DIGEST
    if parsed["final_event_digest"] != expected_final:
        raise TraceValidationError("trace final event digest mismatch")
    normalized_usage = _validate_usage_mapping(
        usage,
        axes=axes,
        field_name="ledger usage",
    )
    if normalized_usage != expected_usage:
        raise TraceValidationError("ledger usage does not match event aggregation")
    charge_count = _require_nonnegative_int(
        ledger["charge_count"],
        "ledger charge_count",
    )
    if charge_count != accepted_charges:
        raise TraceValidationError("ledger charge count does not match events")
    expected_remaining = {
        axis: normalized_limits[axis] - normalized_usage[axis] for axis in axes
    }
    normalized_remaining = _validate_usage_mapping(
        ledger["remaining"],
        axes=axes,
        field_name="ledger remaining",
    )
    if normalized_remaining != expected_remaining:
        raise TraceValidationError("ledger remaining work does not close")
    expected_exhausted = [axis for axis in axes if expected_remaining[axis] == 0]
    if ledger["exhausted_axes"] != expected_exhausted:
        raise TraceValidationError("ledger exhausted axes do not close")
    expected_overshoot_by_axis = {axis: 0 for axis in axes}
    normalized_overshoot = _require_nonnegative_int(
        ledger["overshoot"],
        "ledger overshoot",
    )
    normalized_overshoot_by_axis = _validate_usage_mapping(
        ledger["overshoot_by_axis"],
        axes=axes,
        field_name="ledger overshoot_by_axis",
    )
    if (
        normalized_overshoot != 0
        or normalized_overshoot_by_axis != expected_overshoot_by_axis
    ):
        raise TraceValidationError("ledger reports impossible budget overshoot")

    run_identity = _validate_base_run_identity(parsed["run_identity"])
    run_limits = _validate_usage_mapping(
        run_identity.get("work_limits"),
        axes=axes,
        field_name="run_identity.work_limits",
    )
    if run_limits != normalized_limits:
        raise TraceValidationError("run identity work limits do not match ledger")
    live = ledger["live_storage"]
    peak = ledger["peak_live_storage"]
    if (
        not isinstance(live, dict)
        or not isinstance(peak, dict)
        or set(live) != {"bytes", "nodes"}
        or set(peak) != {"bytes", "nodes"}
    ):
        raise TraceValidationError("ledger live-storage fields drifted")
    for field_name in ("bytes", "nodes"):
        current = _require_nonnegative_int(
            live[field_name],
            f"ledger live_storage.{field_name}",
        )
        maximum = _require_nonnegative_int(
            peak[field_name],
            f"ledger peak_live_storage.{field_name}",
        )
        if current > maximum:
            raise TraceValidationError("current live storage exceeds recorded peak")
    return parsed


def validate_trace_bytes(payload: bytes) -> dict[str, Any]:
    """Require strict canonical bytes in addition to semantic trace validity."""

    if not isinstance(payload, bytes):
        raise TypeError("trace payload must be bytes")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise TraceValidationError("trace is not valid UTF-8") from error
    parsed = strict_json_loads(text)
    if not isinstance(parsed, dict):
        raise TraceValidationError("trace root must be an object")
    if canonical_trace_bytes(parsed) != payload:
        raise TraceValidationError("trace bytes are not canonical")
    return validate_trace(parsed)
