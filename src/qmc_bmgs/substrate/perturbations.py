"""Dynamic, visited-state-only IID and Sobol perturbations for Track A."""

from __future__ import annotations

import math
import platform
import sys
from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Mapping, Sequence

import torch
from torch.quasirandom import SobolEngine

from qmc_bmgs.benchmarks.countdown import (
    RULESET_ID,
    CountdownAction,
    CountdownActionError,
    CountdownState,
    CountdownTask,
)
from qmc_bmgs.substrate.budget import (
    TRACK_A_WORK_AXES,
    TrackAChargeReceipt,
    TrackAWorkBudget,
    TrackAWorkLedger,
)
from qmc_bmgs.substrate.trace import (
    HashChainedTrace,
    RUN_IDENTITY_SCHEMA_VERSION,
    TraceValidationError,
    canonical_trace_bytes,
    sha256_json,
    validate_trace,
    validate_trace_bytes,
)


SOURCE_NAMES = ("iid", "sobol")
NODE_SCHEMA_VERSION = "qmc-bmgs-track-a-node-materialization/v1"
POINT_SCHEMA_VERSION = "qmc-bmgs-track-a-perturbation-point/v1"
STREAM_IDENTITY_VERSION = "qmc-bmgs-track-a-stream-identity/v1"
POINT_IDENTITY_VERSION = "qmc-bmgs-track-a-point-identity/v1"
IID_GENERATOR_VERSION = "sha256-counter-open-unit-float51/v2"
SOBOL_GENERATOR_VERSION = "torch-sobol-full-sha256-cp-rotation-float51/v2"
NORMAL_TRANSFORM_VERSION = "clipped-torch-erfinv-float64/v1"
NORMAL_ICDF_CLIP = 2.0**-53
MAX_GENERIC_ACTION_DIMENSION = 1_000_000
MAX_GENERIC_NODE_VISIT_INDEX = 2**63 - 1


class TrackARunPoisoned(RuntimeError):
    """Raised after accepted work cannot be committed to a complete trace."""


def _require_nonnegative_int(value: Any, field_name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{field_name} must be a non-negative plain integer")
    return value


def _require_source(source: Any) -> str:
    if source not in SOURCE_NAMES or not isinstance(source, str):
        raise ValueError(f"source must be one of {SOURCE_NAMES!r}")
    return source


def _action_from_dict(payload: Mapping[str, Any]) -> CountdownAction:
    if not isinstance(payload, Mapping) or set(payload) != {
        "left",
        "operator",
        "right",
    }:
        raise TraceValidationError("invalid serialized Countdown action")
    try:
        return CountdownAction(
            payload["left"],
            payload["right"],
            payload["operator"],
        )
    except (TypeError, ValueError, CountdownActionError) as error:
        raise TraceValidationError("invalid serialized Countdown action") from error


def _action_payload(actions: Sequence[CountdownAction]) -> list[dict[str, Any]]:
    return [action.to_dict() for action in actions]


@lru_cache(maxsize=len(SOURCE_NAMES))
def _runtime_conformance_digest(source: str) -> str:
    resolved_source = _require_source(source)
    uniforms = torch.tensor(
        (0.125, 0.25, 0.5, 0.75, 0.875),
        dtype=torch.float64,
        device="cpu",
    )
    normals = math.sqrt(2.0) * torch.erfinv(2.0 * uniforms - 1.0)
    payload: dict[str, Any] = {"inverse_normal": normals.tolist()}
    if resolved_source == "iid":
        payload["iid"] = list(_iid_uniforms("0" * 64, 8))
    else:
        payload["sobol"] = SobolEngine(dimension=3, scramble=False).draw(
            8,
            dtype=torch.float64,
        ).tolist()
    return sha256_json(payload)


def _runtime_metadata(source: str) -> dict[str, Any]:
    resolved_source = _require_source(source)
    generator = (
        IID_GENERATOR_VERSION
        if resolved_source == "iid"
        else SOBOL_GENERATOR_VERSION
    )
    metadata = {
        "architecture": platform.machine(),
        "byteorder": sys.byteorder,
        "device": "cpu",
        "dtype": "float64",
        "generator_version": generator,
        "normal_transform": {
            "clip": NORMAL_ICDF_CLIP,
            "formula": "sqrt(2)*erfinv(2*clip(u)-1)",
            "version": NORMAL_TRANSFORM_VERSION,
        },
        "python_version": platform.python_version(),
        "runtime_conformance_digest": _runtime_conformance_digest(
            resolved_source
        ),
        "source": resolved_source,
        "torch_git_version": getattr(torch.version, "git_version", None),
        "torch_version": torch.__version__,
    }
    if resolved_source == "iid":
        metadata.update(
            {
                "iid_counter_hash": "sha256",
                "iid_open_unit_bits": 51,
            }
        )
    else:
        metadata.update(
            {
                "sobol_maxbit": SobolEngine.MAXBIT,
                "sobol_maxdim": SobolEngine.MAXDIM,
                "sobol_randomization": "full-sha256-cranley-patterson-rotation",
            }
        )
    return metadata


def _validate_node_materialization_schema(payload: Mapping[str, Any]) -> None:
    """Reject JSON type aliases before Python's value equality can hide them."""

    action_count = payload["action_count"]
    if type(action_count) is not int or action_count < 1:
        raise TraceValidationError(
            "node action_count must be a positive plain integer"
        )
    action_order = payload["action_order"]
    if not isinstance(action_order, list) or len(action_order) != action_count:
        raise TraceValidationError("node action order does not match action_count")

    metadata = payload["generator_metadata"]
    common_metadata_fields = {
        "architecture",
        "byteorder",
        "device",
        "dtype",
        "generator_version",
        "normal_transform",
        "python_version",
        "runtime_conformance_digest",
        "source",
        "torch_git_version",
        "torch_version",
    }
    source = payload["source"]
    if source not in SOURCE_NAMES or not isinstance(source, str):
        raise TraceValidationError("node source is invalid")
    source_metadata_fields = (
        {"iid_counter_hash", "iid_open_unit_bits"}
        if source == "iid"
        else {"sobol_maxbit", "sobol_maxdim", "sobol_randomization"}
    )
    metadata_fields = common_metadata_fields | source_metadata_fields
    if not isinstance(metadata, dict) or set(metadata) != metadata_fields:
        raise TraceValidationError("node generator metadata fields drifted")
    for field_name in (
        "architecture",
        "byteorder",
        "device",
        "dtype",
        "generator_version",
        "python_version",
        "source",
        "torch_version",
    ):
        if not isinstance(metadata[field_name], str):
            raise TraceValidationError(
                f"node generator metadata {field_name} is invalid"
            )
    if metadata["source"] != source:
        raise TraceValidationError("node generator metadata source drifted")
    git_version = metadata["torch_git_version"]
    if git_version is not None and not isinstance(git_version, str):
        raise TraceValidationError(
            "node generator metadata torch_git_version is invalid"
        )
    conformance_digest = metadata["runtime_conformance_digest"]
    if (
        not isinstance(conformance_digest, str)
        or len(conformance_digest) != 64
        or any(
            character not in "0123456789abcdef"
            for character in conformance_digest
        )
    ):
        raise TraceValidationError(
            "node generator metadata runtime_conformance_digest is invalid"
        )
    integer_fields = (
        ("iid_open_unit_bits",)
        if source == "iid"
        else ("sobol_maxbit", "sobol_maxdim")
    )
    for field_name in integer_fields:
        value = metadata[field_name]
        if type(value) is not int or value < 1:
            raise TraceValidationError(
                f"node generator metadata {field_name} must be a positive plain integer"
            )
    if source == "iid":
        if metadata["iid_counter_hash"] != "sha256":
            raise TraceValidationError("node IID counter hash is invalid")
    elif not isinstance(metadata["sobol_randomization"], str):
        raise TraceValidationError("node Sobol randomization metadata is invalid")

    normal_transform = metadata["normal_transform"]
    if (
        not isinstance(normal_transform, dict)
        or set(normal_transform) != {"clip", "formula", "version"}
        or type(normal_transform["clip"]) is not float
        or not math.isfinite(normal_transform["clip"])
        or not isinstance(normal_transform["formula"], str)
        or not isinstance(normal_transform["version"], str)
    ):
        raise TraceValidationError("node normal-transform metadata is invalid")


def build_perturbation_run_identity(
    *,
    source: str,
    exploration_seed: int,
    tasks: Sequence[CountdownTask],
    work_budget: TrackAWorkBudget,
    budget_profile: str,
    method_id: str,
    configuration_id: str,
) -> dict[str, Any]:
    """Build the typed identity that an external manifest must seal."""

    resolved_source = _require_source(source)
    resolved_seed = _require_nonnegative_int(exploration_seed, "exploration_seed")
    if not isinstance(work_budget, TrackAWorkBudget):
        raise TypeError("work_budget must be a TrackAWorkBudget")
    labels = {
        "budget_profile": budget_profile,
        "configuration_id": configuration_id,
        "method_id": method_id,
    }
    for field_name, value in labels.items():
        if not isinstance(value, str) or not value:
            raise ValueError(f"{field_name} must be a non-empty string")
    task_rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for task in tasks:
        if type(task) is not CountdownTask:
            raise TypeError("tasks must contain only CountdownTask values")
        if task.task_fingerprint in seen:
            raise ValueError("run identity contains a duplicate task")
        seen.add(task.task_fingerprint)
        task_rows.append(task.to_dict())
    if not task_rows:
        raise ValueError("run identity requires at least one task")
    metadata = _runtime_metadata(resolved_source)
    return {
        **labels,
        "exploration_seed": resolved_seed,
        "generator_metadata_digest": sha256_json(metadata),
        "run_identity_schema_version": RUN_IDENTITY_SCHEMA_VERSION,
        "selected_source": resolved_source,
        "task_fingerprints": [row["task_fingerprint"] for row in task_rows],
        "task_manifest_digest": sha256_json(task_rows),
        "work_limits": work_budget.to_dict(),
    }


def _validate_run_identity(identity: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(identity, Mapping) or set(identity) != {
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
    }:
        raise TraceValidationError("Track A run identity fields drifted")
    if identity["run_identity_schema_version"] != RUN_IDENTITY_SCHEMA_VERSION:
        raise TraceValidationError("unsupported Track A run identity schema")
    for field_name in ("budget_profile", "configuration_id", "method_id"):
        if not isinstance(identity[field_name], str) or not identity[field_name]:
            raise TraceValidationError(f"run identity {field_name} is invalid")
    source = _require_source(identity["selected_source"])
    seed = _require_nonnegative_int(identity["exploration_seed"], "exploration_seed")
    fingerprints = identity["task_fingerprints"]
    if (
        not isinstance(fingerprints, list)
        or not fingerprints
        or any(not isinstance(item, str) or not item for item in fingerprints)
        or len(set(fingerprints)) != len(fingerprints)
    ):
        raise TraceValidationError("run identity task fingerprints are invalid")
    for field_name in ("generator_metadata_digest", "task_manifest_digest"):
        value = identity[field_name]
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise TraceValidationError(f"run identity {field_name} is invalid")
    limits = identity["work_limits"]
    if not isinstance(limits, dict) or set(limits) != set(TRACK_A_WORK_AXES):
        raise TraceValidationError("run identity work limits are invalid")
    normalized_limits = {
        axis: _require_nonnegative_int(limits[axis], f"work_limits.{axis}")
        for axis in TRACK_A_WORK_AXES
    }
    return {
        **dict(identity),
        "exploration_seed": seed,
        "selected_source": source,
        "work_limits": normalized_limits,
    }


def perturbation_run_identity_digest(identity: Mapping[str, Any]) -> str:
    """Digest a fully validated run identity for external sealing."""

    return sha256_json(_validate_run_identity(identity))


def _validate_request(
    *,
    task: CountdownTask,
    state: CountdownState,
    actions: Sequence[CountdownAction],
    source: str,
    exploration_seed: int,
    node_visit_index: int,
) -> tuple[CountdownState, tuple[CountdownAction, ...]]:
    if type(task) is not CountdownTask:
        raise TypeError("task must be a CountdownTask")
    resolved_source = _require_source(source)
    _require_nonnegative_int(exploration_seed, "exploration_seed")
    visit = _require_nonnegative_int(node_visit_index, "node_visit_index")
    if visit > MAX_GENERIC_NODE_VISIT_INDEX:
        raise ValueError("node_visit_index exceeds the generic safety bound")
    canonical_state = task.canonical_state(state)
    action_order = tuple(actions)
    if any(not isinstance(action, CountdownAction) for action in action_order):
        raise TypeError("actions must contain only CountdownAction values")
    expected_actions = task.legal_actions(canonical_state)
    if not expected_actions:
        raise ValueError("terminal or actionless states have no perturbation stream")
    if action_order != expected_actions:
        raise ValueError("action order drifted from the task adapter")
    if len(action_order) > MAX_GENERIC_ACTION_DIMENSION:
        raise ValueError("action dimension exceeds the generic safety bound")
    if resolved_source == "sobol":
        if visit >= 2**SobolEngine.MAXBIT:
            raise ValueError("node_visit_index exceeds the versioned Sobol depth")
        if len(action_order) > SobolEngine.MAXDIM:
            raise ValueError("action dimension exceeds the versioned Sobol maximum")
    return canonical_state, action_order


def _stream_identity(
    *,
    task: CountdownTask,
    state: CountdownState,
    action_order: Sequence[CountdownAction],
    source: str,
    exploration_seed: int,
) -> dict[str, Any]:
    actions = _action_payload(action_order)
    metadata = _runtime_metadata(source)
    return {
        "action_count": len(action_order),
        "action_order_digest": sha256_json(actions),
        "exploration_seed": exploration_seed,
        "generator_metadata_digest": sha256_json(metadata),
        "ruleset_id": RULESET_ID,
        "source": source,
        "state": list(state),
        "stream_identity_version": STREAM_IDENTITY_VERSION,
        "task_fingerprint": task.task_fingerprint,
    }


def _point_identity(stream_identity_digest: str, node_visit_index: int) -> dict[str, Any]:
    return {
        "node_visit_index": node_visit_index,
        "point_identity_version": POINT_IDENTITY_VERSION,
        "stream_identity_digest": stream_identity_digest,
    }


def _open_unit_from_digest(digest: bytes) -> float:
    if not isinstance(digest, bytes) or len(digest) < 8:
        raise ValueError("uniform digest material must contain at least eight bytes")
    # A 51-bit midpoint has denominator 2**52 and an odd numerator. Both
    # endpoints remain at least one binary64 ulp away from 0 and 1.
    mantissa = int.from_bytes(digest[:8], "big") >> 13
    value = (mantissa + 0.5) / 2**51
    if not 0.0 < value < 1.0:
        raise AssertionError("open-unit mapping reached an endpoint")
    return value


def _open_unit_hash(payload: Mapping[str, Any]) -> float:
    return _open_unit_from_digest(bytes.fromhex(sha256_json(payload)))


def _iid_uniforms(
    point_identity_digest: str,
    action_count: int,
) -> tuple[float, ...]:
    return tuple(
        _open_unit_hash(
            {
                "coordinate": coordinate,
                "generator_version": IID_GENERATOR_VERSION,
                "point_identity_digest": point_identity_digest,
            }
        )
        for coordinate in range(action_count)
    )


def _sobol_uniforms(
    stream_identity_digest: str,
    node_visit_index: int,
    action_count: int,
) -> tuple[float, ...]:
    # PyTorch scramble seeds collide modulo 2**32.  Track A therefore uses one
    # fixed, unscrambled Sobol sequence plus a full-identity keyed
    # Cranley-Patterson rotation.  Visits take successive points from the same
    # node-local sequence; they are never individually reseeded.
    engine = SobolEngine(dimension=action_count, scramble=False)
    if node_visit_index:
        engine.fast_forward(node_visit_index)
    base = engine.draw(1, dtype=torch.float64)[0].tolist()
    shifts = (
        _open_unit_hash(
            {
                "coordinate": coordinate,
                "generator_version": SOBOL_GENERATOR_VERSION,
                "purpose": "cranley_patterson_rotation",
                "stream_identity_digest": stream_identity_digest,
            }
        )
        for coordinate in range(action_count)
    )
    rotated = tuple(
        (float(value) + shift) % 1.0 for value, shift in zip(base, shifts)
    )
    if any(not 0.0 < value < 1.0 for value in rotated):
        raise AssertionError("Cranley-Patterson rotation reached an endpoint")
    return rotated


def _inverse_normal(uniforms: Sequence[float]) -> tuple[float, ...]:
    values = torch.tensor(tuple(uniforms), dtype=torch.float64, device="cpu")
    clipped = values.clamp(NORMAL_ICDF_CLIP, 1.0 - NORMAL_ICDF_CLIP)
    normals = math.sqrt(2.0) * torch.erfinv(2.0 * clipped - 1.0)
    if not bool(torch.isfinite(normals).all()):
        raise AssertionError("inverse-normal transform produced non-finite values")
    return tuple(float(value) for value in normals.tolist())


def _node_record(
    *,
    task: CountdownTask,
    state: CountdownState,
    action_order: Sequence[CountdownAction],
    source: str,
    exploration_seed: int,
) -> dict[str, Any]:
    actions = _action_payload(action_order)
    identity = _stream_identity(
        task=task,
        state=state,
        action_order=action_order,
        source=source,
        exploration_seed=exploration_seed,
    )
    core = {
        "action_count": len(action_order),
        "action_order": actions,
        "action_order_digest": sha256_json(actions),
        "exploration_seed": exploration_seed,
        "generator_metadata": _runtime_metadata(source),
        "schema_version": NODE_SCHEMA_VERSION,
        "source": source,
        "state": list(state),
        "stream_identity_digest": sha256_json(identity),
        "task_fingerprint": task.task_fingerprint,
    }
    return {**core, "node_digest": sha256_json(core)}


def generate_perturbation_point(
    *,
    task: CountdownTask,
    state: CountdownState,
    actions: Sequence[CountdownAction],
    source: str,
    exploration_seed: int,
    node_visit_index: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Random-access deterministic generation used by live runs and replay."""

    canonical_state, action_order = _validate_request(
        task=task,
        state=state,
        actions=actions,
        source=source,
        exploration_seed=exploration_seed,
        node_visit_index=node_visit_index,
    )
    node = _node_record(
        task=task,
        state=canonical_state,
        action_order=action_order,
        source=source,
        exploration_seed=exploration_seed,
    )
    identity = _point_identity(node["stream_identity_digest"], node_visit_index)
    identity_digest = sha256_json(identity)
    uniforms = (
        _iid_uniforms(identity_digest, len(action_order))
        if source == "iid"
        else _sobol_uniforms(
            node["stream_identity_digest"],
            node_visit_index,
            len(action_order),
        )
    )
    normals = _inverse_normal(uniforms)
    core = {
        "node_digest": node["node_digest"],
        "node_visit_index": node_visit_index,
        "normal_digest": sha256_json(list(normals)),
        "normals": list(normals),
        "point_identity_digest": identity_digest,
        "schema_version": POINT_SCHEMA_VERSION,
        "uniform_digest": sha256_json(list(uniforms)),
        "uniforms": list(uniforms),
    }
    point = {**core, "point_digest": sha256_json(core)}
    return node, point


@dataclass(frozen=True)
class PerturbationDraw:
    """One selected-source vector and its coordinate-generation receipt."""

    node: dict[str, Any]
    point: dict[str, Any]
    receipt: TrackAChargeReceipt
    node_materialized: bool

    @property
    def uniforms(self) -> tuple[float, ...]:
        return tuple(self.point["uniforms"])

    @property
    def normals(self) -> tuple[float, ...]:
        return tuple(self.point["normals"])

    @property
    def node_visit_index(self) -> int:
        return int(self.point["node_visit_index"])


class LazyNormalSource:
    """Materialize only selected-source points at actually visited states."""

    def __init__(
        self,
        *,
        source: str,
        exploration_seed: int,
        trace: HashChainedTrace,
        tasks: Sequence[CountdownTask],
    ) -> None:
        self._source = _require_source(source)
        self._exploration_seed = _require_nonnegative_int(
            exploration_seed,
            "exploration_seed",
        )
        if not isinstance(trace, HashChainedTrace):
            raise TypeError("trace must be a HashChainedTrace")
        run_identity = _validate_run_identity(trace.run_identity)
        if run_identity["selected_source"] != self._source:
            raise TraceValidationError("trace source does not match normal source")
        if run_identity["exploration_seed"] != self._exploration_seed:
            raise TraceValidationError("trace seed does not match normal source")
        expected_metadata_digest = sha256_json(_runtime_metadata(self._source))
        if run_identity["generator_metadata_digest"] != expected_metadata_digest:
            raise TraceValidationError("trace runtime metadata does not match runtime")
        task_index = _task_index(tasks)
        task_rows = [task.to_dict() for task in tasks]
        if run_identity["task_fingerprints"] != [
            row["task_fingerprint"] for row in task_rows
        ] or run_identity["task_manifest_digest"] != sha256_json(task_rows):
            raise TraceValidationError("trace task manifest does not match tasks")
        self.trace = trace
        self._run_identity = deepcopy(run_identity)
        self._task_index = task_index
        self._nodes: dict[str, dict[str, Any]] = {}
        self._next_visit: dict[str, int] = {}
        self._bound_ledger: TrackAWorkLedger | None = None
        self._poisoned = False

    @property
    def source(self) -> str:
        return self._source

    @property
    def exploration_seed(self) -> int:
        return self._exploration_seed

    @property
    def run_identity(self) -> dict[str, Any]:
        return deepcopy(self._run_identity)

    @property
    def materialized_node_count(self) -> int:
        return len(self._nodes)

    @property
    def point_count(self) -> int:
        return sum(self._next_visit.values())

    def state_snapshot(self) -> dict[str, Any]:
        return {
            "materialized_node_digests": sorted(self._nodes),
            "next_visit": dict(sorted(self._next_visit.items())),
            "point_count": self.point_count,
            "poisoned": self._poisoned,
            "trace_event_count": self.trace.event_count,
        }

    def draw(
        self,
        *,
        task: CountdownTask,
        state: CountdownState,
        actions: Sequence[CountdownAction],
        ledger: TrackAWorkLedger,
    ) -> PerturbationDraw:
        if self._poisoned:
            raise TrackARunPoisoned("normal source is poisoned after a partial failure")
        self.trace.assert_identity_unchanged()
        if not isinstance(ledger, TrackAWorkLedger):
            raise TypeError("ledger must be a TrackAWorkLedger")
        if type(task) is not CountdownTask:
            raise TypeError("task must be a CountdownTask")
        if (
            self._source != self._run_identity["selected_source"]
            or self._exploration_seed != self._run_identity["exploration_seed"]
        ):
            raise TraceValidationError("normal source drifted from sealed run identity")
        if ledger.budget.to_dict() != self._run_identity["work_limits"]:
            raise ValueError("ledger limits do not match the sealed run identity")
        if self._bound_ledger is not None and ledger is not self._bound_ledger:
            raise ValueError("normal source is already bound to another ledger")
        if self._task_index.get(task.task_fingerprint) != task:
            raise ValueError("task is not sealed in the run identity")

        # Validate and derive every fallible identity/dimension field before the
        # atomic charge. A rejected charge therefore cannot consume a point or
        # create a node/event.
        canonical_state, action_order = _validate_request(
            task=task,
            state=state,
            actions=actions,
            source=self._source,
            exploration_seed=self._exploration_seed,
            node_visit_index=0,
        )
        candidate_node = _node_record(
            task=task,
            state=canonical_state,
            action_order=action_order,
            source=self._source,
            exploration_seed=self._exploration_seed,
        )
        node_digest = candidate_node["node_digest"]
        visit_index = self._next_visit.get(node_digest, 0)
        _validate_request(
            task=task,
            state=canonical_state,
            actions=action_order,
            source=self._source,
            exploration_seed=self._exploration_seed,
            node_visit_index=visit_index,
        )
        materialized = node_digest not in self._nodes
        reservation = self.trace.reserve_event_slots(2 if materialized else 1)
        try:
            receipt = ledger.charge_perturbation_coordinates(len(action_order))
        except Exception:
            reservation.cancel()
            raise

        try:
            node, point = generate_perturbation_point(
                task=task,
                state=canonical_state,
                actions=action_order,
                source=self._source,
                exploration_seed=self._exploration_seed,
                node_visit_index=visit_index,
            )
            if node != candidate_node:
                raise AssertionError("node materialization drifted within one draw")

            if materialized:
                self.trace.append(
                    "node_materialized",
                    node,
                    reservation=reservation,
                )
            self.trace.append(
                "perturbation_draw",
                point,
                receipt=receipt,
                reservation=reservation,
            )
            if materialized:
                self._nodes[node_digest] = node
            self._next_visit[node_digest] = visit_index + 1
            self._bound_ledger = ledger
            return PerturbationDraw(
                deepcopy(node),
                deepcopy(point),
                receipt,
                materialized,
            )
        except Exception as error:
            if reservation.remaining:
                reservation.cancel()
            self._poisoned = True
            self.trace.poison("accepted_perturbation_commit_failure")
            raise TrackARunPoisoned(
                "accepted perturbation charge could not be committed; discard run"
            ) from error


def _task_index(tasks: Sequence[CountdownTask]) -> dict[str, CountdownTask]:
    index: dict[str, CountdownTask] = {}
    for task in tasks:
        if type(task) is not CountdownTask:
            raise TypeError("replay tasks must contain only CountdownTask values")
        if task.task_fingerprint in index:
            raise TraceValidationError("replay task registry contains duplicates")
        index[task.task_fingerprint] = task
    if not index:
        raise TraceValidationError("replay task registry cannot be empty")
    return index


def replay_perturbation_trace(
    record: Mapping[str, Any],
    *,
    tasks: Sequence[CountdownTask],
    expected_run_identity_digest: str,
) -> bytes:
    """Regenerate every selected point independently from sealed identities."""

    parsed = validate_trace(record)
    task_index = _task_index(tasks)
    if (
        not isinstance(expected_run_identity_digest, str)
        or len(expected_run_identity_digest) != 64
        or any(
            character not in "0123456789abcdef"
            for character in expected_run_identity_digest
        )
    ):
        raise ValueError("expected_run_identity_digest must be lowercase SHA-256")
    run_identity = _validate_run_identity(parsed["run_identity"])
    if sha256_json(run_identity) != expected_run_identity_digest:
        raise TraceValidationError("sealed run identity digest mismatch")
    task_rows = [task.to_dict() for task in tasks]
    if run_identity["task_fingerprints"] != [
        row["task_fingerprint"] for row in task_rows
    ] or run_identity["task_manifest_digest"] != sha256_json(task_rows):
        raise TraceValidationError("replay tasks do not match the sealed run identity")
    if run_identity["generator_metadata_digest"] != sha256_json(
        _runtime_metadata(run_identity["selected_source"])
    ):
        raise TraceValidationError("sealed runtime metadata does not match runtime")
    nodes: dict[str, dict[str, Any]] = {}
    next_visits: dict[str, int] = {}

    for event in parsed["events"]:
        kind = event["kind"]
        payload = event["payload"]
        if kind == "node_materialized":
            if event["charge"] is not None:
                raise TraceValidationError("node materialization cannot carry work")
            if set(payload) != {
                "action_count",
                "action_order",
                "action_order_digest",
                "exploration_seed",
                "generator_metadata",
                "node_digest",
                "schema_version",
                "source",
                "state",
                "stream_identity_digest",
                "task_fingerprint",
            }:
                raise TraceValidationError("node materialization fields drifted")
            if payload["schema_version"] != NODE_SCHEMA_VERSION:
                raise TraceValidationError("unsupported node materialization schema")
            _validate_node_materialization_schema(payload)
            task = task_index.get(payload["task_fingerprint"])
            if task is None:
                raise TraceValidationError("trace references an unknown task")
            if (
                payload["source"] != run_identity["selected_source"]
                or payload["exploration_seed"] != run_identity["exploration_seed"]
                or payload["task_fingerprint"]
                not in run_identity["task_fingerprints"]
            ):
                raise TraceValidationError("node does not match sealed run identity")
            actions = tuple(_action_from_dict(item) for item in payload["action_order"])
            expected_node, _ = generate_perturbation_point(
                task=task,
                state=tuple(payload["state"]),
                actions=actions,
                source=payload["source"],
                exploration_seed=payload["exploration_seed"],
                node_visit_index=0,
            )
            if payload != expected_node:
                raise TraceValidationError(
                    "node materialization failed generative replay"
                )
            digest = payload["node_digest"]
            if digest in nodes:
                raise TraceValidationError("node materialized more than once")
            nodes[digest] = payload
            next_visits[digest] = 0
        elif kind == "perturbation_draw":
            if set(payload) != {
                "node_digest",
                "node_visit_index",
                "normal_digest",
                "normals",
                "point_digest",
                "point_identity_digest",
                "schema_version",
                "uniform_digest",
                "uniforms",
            }:
                raise TraceValidationError("perturbation point fields drifted")
            if payload["schema_version"] != POINT_SCHEMA_VERSION:
                raise TraceValidationError("unsupported perturbation point schema")
            node = nodes.get(payload["node_digest"])
            if node is None:
                raise TraceValidationError("point precedes its node materialization")
            visit_index = payload["node_visit_index"]
            if visit_index != next_visits[payload["node_digest"]]:
                raise TraceValidationError("node-local visit index has a gap")
            task = task_index[node["task_fingerprint"]]
            actions = tuple(_action_from_dict(item) for item in node["action_order"])
            expected_node, expected_point = generate_perturbation_point(
                task=task,
                state=tuple(node["state"]),
                actions=actions,
                source=node["source"],
                exploration_seed=node["exploration_seed"],
                node_visit_index=visit_index,
            )
            if node != expected_node or payload != expected_point:
                raise TraceValidationError(
                    "perturbation point failed generative replay"
                )
            expected_delta = {axis: 0 for axis in TRACK_A_WORK_AXES}
            expected_delta["generated_perturbation_coordinates"] = node[
                "action_count"
            ]
            charge = event["charge"]
            if charge is None or charge["delta"] != expected_delta:
                raise TraceValidationError("perturbation charge does not close")
            next_visits[payload["node_digest"]] = visit_index + 1
        else:
            raise TraceValidationError(
                f"unsupported event kind in perturbation-only replay: {kind}"
            )

    if any(count < 1 for count in next_visits.values()):
        raise TraceValidationError("materialized node has no selected point")
    return canonical_trace_bytes(parsed)


def replay_perturbation_trace_bytes(
    payload: bytes,
    *,
    tasks: Sequence[CountdownTask],
    expected_run_identity_digest: str,
) -> bytes:
    parsed = validate_trace_bytes(payload)
    replayed = replay_perturbation_trace(
        parsed,
        tasks=tasks,
        expected_run_identity_digest=expected_run_identity_digest,
    )
    if replayed != payload:
        raise TraceValidationError("generative replay was not byte-identical")
    return replayed
