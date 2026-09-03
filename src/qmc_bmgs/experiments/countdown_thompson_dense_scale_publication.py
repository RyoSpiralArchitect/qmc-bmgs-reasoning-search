"""Closed dense-scale 384-record domains over unchanged v2r3 mechanics.

This module grants no execution authority.  Its callers independently qualify
the reviewed checkout, runtime and external authorization before entry.  The
only action boundary is an exact durable STARTED collective.  Neither the
diagnostic publisher nor any diagnostic analysis entry point is called here.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from qmc_bmgs.experiments import countdown_thompson_dense_scale_core as core
from qmc_bmgs.experiments import (
    countdown_thompson_regular_file_publication_v2 as mechanics,
)
from qmc_bmgs.substrate.budget import TRACK_A_WORK_AXES
from qmc_bmgs.substrate.trace import (
    canonical_json,
    canonical_trace_bytes,
    sha256_json,
    strict_json_loads,
)


PUBLICATION_BACKEND = mechanics.PUBLICATION_BACKEND
ARTIFACT_LAYOUT = mechanics.ARTIFACT_LAYOUT
EXPECTED_CELL_COUNT = 384
MAX_CONTROL_BYTES = 8 << 20
MAX_RECORDS_BYTES = 256 << 20
MAX_RECORD_BYTES = MAX_RECORDS_BYTES
_SEEDS = (7168, 7169, 7170, 7171)
_SCALES = (0, 1, 2, 4, 8, 16, 32, 64)
_AUTH_FIELDS = frozenset(
    "analysis_manifest_digest anchor_qualification anchor_qualification_digest "
    "artifact_id artifact_layout authorization_scope budget_manifest_digest "
    "bundle_id cell_count claim_boundary dense_scale_seal_digest "
    "deterministic_digest method_manifest_digest output_parent_binding "
    "output_parent_binding_digest output_path output_path_digest "
    "preregistration_file_sha256 proposal_manifest_digest publication_backend "
    "publication_environment_requirements requires_explicit_digest_confirmation "
    "runner_build_attestation runtime_binding_digest runtime_qualification "
    "runtime_qualification_digest schedule_digest schema_version".split()
)
RECORD_FIELDS = frozenset(
    "budget_evidence cell_id cell_key deterministic_digest provider_calls replay "
    "run_binding_digest schema_version search_record search_run_identity_digest "
    "search_trace_byte_count search_trace_sha256 source_multiset_fingerprint".split()
)
RUN_BINDING_FIELDS = frozenset(
    "analysis_manifest_digest anchor_qualification_digest artifact_id artifact_kind "
    "artifact_layout attempt_receipt_digest authorization_schema_version "
    "authorization_scope budget_manifest_digest bundle_id dense_scale_seal_digest "
    "deterministic_digest execution_authorization_digest execution_head_revision "
    "execution_mode fixture_design_digest method_manifest_digest "
    "output_parent_binding_digest output_path output_path_digest owner_nonce "
    "preregistration_file_sha256 proposal_manifest_digest publication_backend "
    "reviewed_authorization_revision runner_build_digest runtime_binding_digest "
    "runtime_qualification_digest schedule_digest schema_version search_build_digest "
    "started_receipt_digest".split()
)
RUN_MANIFEST_FIELDS = frozenset(
    "artifact_kind cell_count claim_boundary deterministic_digest "
    "execution_authorization execution_authorization_digest execution_mode "
    "provider_calls record_digests records_payload_jsonl_byte_count "
    "records_payload_jsonl_sha256 run_binding run_binding_digest schedule_cell_ids "
    "schema_version".split()
)
_BUDGET_FIELDS = frozenset(
    "blocked_axes budget_valid non_primary_headroom primary_axis primary_headroom "
    "profile_spec remaining stop_reason usage".split()
)
_SUMMARY_COMMON_FIELDS = frozenset(
    "schema_version bundle_id execution_mode cell_count analysis_manifest_digest "
    "authorization_digest anchor_qualification_digest run_manifest_digest "
    "stage_order integrity claim_boundary deterministic_digest".split()
)
SUMMARY_FIELDS = _SUMMARY_COMMON_FIELDS | frozenset(
    "mechanism scale_order task_seed_order per_scale selected_scale decision".split()
)
FIXTURE_SUMMARY_FIELDS = _SUMMARY_COMMON_FIELDS | frozenset(
    {"fixture_status", "fixture_reduction_digest"}
)
SUMMARY_SCHEMA_VERSION = "qmc-bmgs-countdown-thompson-dense-scale-summary/v1"
FIXTURE_SUMMARY_SCHEMA_VERSION = (
    "qmc-bmgs-countdown-thompson-dense-scale-nondiagnostic-summary/v1"
)


class DensePublicationError(RuntimeError):
    """Publication refused without a scientific result."""

    status = "NOT_RUN"


class DensePublicationNotRunError(DensePublicationError):
    status = "NOT_RUN"

    def __init__(self, message: str, *, authorization_consumed: bool = False):
        super().__init__(message)
        self.authorization_consumed = authorization_consumed
        self.retry_permitted = False


class DensePublicationInvalidError(DensePublicationError):
    status = "INVALID"
    authorization_consumed = True
    retry_permitted = False


class DensePublicationAmbiguousError(DensePublicationError):
    status = "PUBLICATION_STATE_AMBIGUOUS"
    authorization_consumed = None
    retry_permitted = False


def _canonical(value: Any) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _digested(value: Mapping[str, Any]) -> dict[str, Any]:
    return {**value, "deterministic_digest": sha256_json(value)}


def _sha_value(value: object, label: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise DensePublicationNotRunError(f"{label} must be lowercase SHA-256")
    return value


def _oid(value: object, label: str) -> str:
    if (
        type(value) is not str
        or len(value) != 40
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise DensePublicationNotRunError(f"{label} must be a full Git OID")
    return value


def _parse(raw: bytes, label: str, *, cap: int = MAX_CONTROL_BYTES) -> Any:
    if type(raw) is not bytes or len(raw) > cap:
        raise DensePublicationNotRunError(f"{label} is not bounded exact bytes")
    try:
        value = strict_json_loads(raw.decode("utf-8"))
        if _canonical(value) != raw:
            raise ValueError("noncanonical bytes")
    except (RecursionError, TypeError, UnicodeError, ValueError) as error:
        raise DensePublicationNotRunError(f"{label} is not canonical JSON") from error
    return value


def _require_object(value: object, fields: frozenset[str], label: str) -> dict:
    if type(value) is not dict or set(value) != fields:
        raise DensePublicationNotRunError(f"{label} fields drifted")
    return value


def _require_digest(value: dict, label: str) -> None:
    expected = _sha_value(value.get("deterministic_digest"), label)
    if (
        sha256_json({k: v for k, v in value.items() if k != "deterministic_digest"})
        != expected
    ):
        raise DensePublicationNotRunError(f"{label} digest drifted")


@dataclass(frozen=True)
class _Domain:
    fixture: bool

    @property
    def stem(self) -> str:
        return "qmc-bmgs-countdown-thompson-dense-scale-" + (
            "nondiagnostic-full-shape-" if self.fixture else ""
        )

    def schema(self, kind: str, version: str = "v2r3") -> str:
        return f"{self.stem}{kind}/{version}"

    @property
    def artifact_kind(self) -> str:
        return (
            "countdown_thompson_dense_scale_nondiagnostic_full_shape_run_v2r3"
            if self.fixture
            else "countdown_thompson_dense_scale_run_v2r3"
        )

    @property
    def bundle_id(self) -> str:
        return core.FIXTURE_BUNDLE_ID if self.fixture else core.BUNDLE_ID

    @property
    def execution_mode(self) -> str:
        return core.FIXTURE_EXECUTION_MODE if self.fixture else core.EXECUTION_MODE

    @property
    def authorization_schema(self) -> str:
        return (
            core.FIXTURE_AUTHORIZATION_SCHEMA_VERSION
            if self.fixture
            else core.AUTHORIZATION_SCHEMA_VERSION
        )

    @property
    def authorization_scope(self) -> str:
        return (
            core.FIXTURE_AUTHORIZATION_SCOPE
            if self.fixture
            else core.AUTHORIZATION_SCOPE
        )

    @property
    def record_schema(self) -> str:
        return (
            core.FIXTURE_RECORD_SCHEMA_VERSION
            if self.fixture
            else core.RECORD_SCHEMA_VERSION
        )


@dataclass(frozen=True)
class DensePublicationInputsV2R3:
    """Immutable external authority; constructing this grants no run authority."""

    authorization_raw: bytes = field(repr=False)
    schedule_raw: bytes = field(repr=False)
    task_sources_raw: bytes = field(repr=False)
    reviewed_authorization_revision: str
    execution_head_revision: str
    fixture: bool

    @property
    def authorization(self) -> dict:
        return _parse(self.authorization_raw, "authorization")

    @property
    def schedule(self) -> tuple[dict, ...]:
        return tuple(_parse(self.schedule_raw, "schedule"))

    @property
    def task_sources(self) -> dict:
        return _parse(self.task_sources_raw, "task sources")


def _make_inputs(
    *,
    fixture: bool,
    authorization_raw: bytes,
    schedule_raw: bytes,
    task_sources_raw: bytes,
    reviewed_authorization_revision: str,
    execution_head_revision: str,
) -> DensePublicationInputsV2R3:
    domain = _Domain(fixture)
    authorization = _parse(authorization_raw, "external authorization")
    fields = _AUTH_FIELDS | ({"fixture_design_digest"} if fixture else set())
    _require_object(authorization, frozenset(fields), "external authorization")
    # These checks deliberately precede output/bundle access.
    if (
        authorization["schema_version"] != domain.authorization_schema
        or authorization["authorization_scope"] != domain.authorization_scope
        or authorization["bundle_id"] != domain.bundle_id
        or type(authorization["cell_count"]) is not int
        or authorization["cell_count"] != EXPECTED_CELL_COUNT
        or authorization["publication_backend"] != PUBLICATION_BACKEND
        or authorization["artifact_layout"] != ARTIFACT_LAYOUT
        or authorization["requires_explicit_digest_confirmation"] is not True
        or type(authorization["artifact_id"]) is not str
        or not authorization["artifact_id"]
        or type(authorization["claim_boundary"]) is not str
        or not authorization["claim_boundary"]
    ):
        raise DensePublicationNotRunError("external authorization domain drifted")
    _require_digest(authorization, "authorization")
    for name in (
        "analysis_manifest_digest",
        "anchor_qualification_digest",
        "budget_manifest_digest",
        "method_manifest_digest",
        "output_parent_binding_digest",
        "output_path_digest",
        "proposal_manifest_digest",
        "runtime_binding_digest",
        "runtime_qualification_digest",
        "schedule_digest",
    ):
        _sha_value(authorization[name], name)
    if fixture:
        if (
            authorization["dense_scale_seal_digest"] is not None
            or authorization["preregistration_file_sha256"] is not None
        ):
            raise DensePublicationNotRunError(
                "fixture contains production seal authority"
            )
        _sha_value(authorization["fixture_design_digest"], "fixture design")
        if (
            authorization["fixture_design_digest"] != core.FIXTURE_DESIGN_DIGEST
            or authorization["schedule_digest"] != core.FIXTURE_SCHEDULE_DIGEST
        ):
            raise DensePublicationNotRunError("fixed fixture design/schedule drifted")
    else:
        _sha_value(authorization["dense_scale_seal_digest"], "dense scale seal")
        _sha_value(
            authorization["preregistration_file_sha256"], "preregistration bytes"
        )
        if any(
            _canonical(authorization.get(k)) != _canonical(v)
            for k, v in core.FROZEN_AUTHORITY.items()
        ):
            raise DensePublicationNotRunError("frozen production authority drifted")
    for name in (
        "runner_build_attestation",
        "anchor_qualification",
        "runtime_qualification",
    ):
        if type(authorization[name]) is not dict:
            raise DensePublicationNotRunError(f"{name} must be an object")
        _require_digest(authorization[name], name)
    if (
        authorization["anchor_qualification"]["deterministic_digest"]
        != authorization["anchor_qualification_digest"]
        or authorization["runtime_qualification"]["deterministic_digest"]
        != authorization["runtime_qualification_digest"]
    ):
        raise DensePublicationNotRunError("qualification receipt digest drifted")
    _sha_value(
        authorization["runner_build_attestation"].get("search_build_digest"),
        "search build",
    )
    _oid(reviewed_authorization_revision, "reviewed authorization revision")
    _oid(execution_head_revision, "execution HEAD")
    if fixture and reviewed_authorization_revision != execution_head_revision:
        raise DensePublicationNotRunError("fixture revision must name its source epoch")
    schedule = _parse(schedule_raw, "schedule")
    sources = _parse(task_sources_raw, "task sources")
    if type(schedule) is not list or len(schedule) != EXPECTED_CELL_COUNT:
        raise DensePublicationNotRunError("schedule must contain exactly 384 cells")
    if type(sources) is not dict or len(sources) != 12:
        raise DensePublicationNotRunError(
            "task-source map must contain exactly 12 tasks"
        )
    for task, source in sources.items():
        _sha_value(task, "task fingerprint")
        _sha_value(source, "source multiset fingerprint")
    task_order: list[str] = []
    cell_ids: list[str] = []
    for index, row in enumerate(schedule):
        _require_object(row, frozenset({"cell_id", "cell_key"}), "schedule row")
        key = row["cell_key"]
        if type(key) is not dict or key.get("bundle_id") != domain.bundle_id:
            raise DensePublicationNotRunError("cell key domain drifted")
        if key.get("schema_version") != domain.schema("cell-key", "v1"):
            raise DensePublicationNotRunError("cell key schema drifted")
        if (
            type(key.get("exploration_seed")) is not int
            or key["exploration_seed"] != _SEEDS[index % 4]
            or type(key.get("terminal_value_scale")) is not int
            or key["terminal_value_scale"] != _SCALES[(index // 4) % 8]
            or type(key.get("task_fingerprint")) is not str
            or key.get("task_fingerprint") not in sources
            or row["cell_id"] != sha256_json(key)
        ):
            raise DensePublicationNotRunError("cell key/order drifted")
        if index % 32 == 0:
            task_order.append(key["task_fingerprint"])
        if key["task_fingerprint"] != task_order[-1]:
            raise DensePublicationNotRunError("schedule is not task-major")
        cell_ids.append(row["cell_id"])
    if len(set(task_order)) != 12 or len(set(cell_ids)) != EXPECTED_CELL_COUNT:
        raise DensePublicationNotRunError("schedule duplicates tasks or cells")
    if sha256_json(schedule) != authorization["schedule_digest"]:
        raise DensePublicationNotRunError("schedule does not close over authorization")
    if fixture:
        expected_fixture = core.public_fixture_inputs()
        if schedule_raw != _canonical(
            list(expected_fixture.schedule)
        ) or task_sources_raw != _canonical(expected_fixture.task_sources):
            raise DensePublicationNotRunError(
                "public fixture cells/task sources drifted"
            )
    layout = _layout(authorization["output_path"])
    if layout.output_path_digest != authorization["output_path_digest"]:
        raise DensePublicationNotRunError("authorized lexical output bytes drifted")
    binding = freeze_dense_parent_binding(
        layout.output_path, authorization["output_parent_binding"]
    )
    if binding["deterministic_digest"] != authorization["output_parent_binding_digest"]:
        raise DensePublicationNotRunError("reviewed parent binding digest drifted")
    return DensePublicationInputsV2R3(
        authorization_raw,
        schedule_raw,
        task_sources_raw,
        reviewed_authorization_revision,
        execution_head_revision,
        fixture,
    )


def make_dense_publication_inputs(
    *,
    authorization_raw: bytes,
    schedule_raw: bytes,
    task_sources_raw: bytes,
    reviewed_authorization_revision: str,
    execution_head_revision: str,
) -> DensePublicationInputsV2R3:
    return _make_inputs(
        fixture=False,
        authorization_raw=authorization_raw,
        schedule_raw=schedule_raw,
        task_sources_raw=task_sources_raw,
        reviewed_authorization_revision=reviewed_authorization_revision,
        execution_head_revision=execution_head_revision,
    )


def make_dense_fixture_publication_inputs(
    *,
    authorization_raw: bytes,
    schedule_raw: bytes,
    task_sources_raw: bytes,
    reviewed_authorization_revision: str,
    execution_head_revision: str,
) -> DensePublicationInputsV2R3:
    return _make_inputs(
        fixture=True,
        authorization_raw=authorization_raw,
        schedule_raw=schedule_raw,
        task_sources_raw=task_sources_raw,
        reviewed_authorization_revision=reviewed_authorization_revision,
        execution_head_revision=execution_head_revision,
    )


def _inputs(value: object, fixture: bool) -> DensePublicationInputsV2R3:
    if type(value) is not DensePublicationInputsV2R3 or value.fixture is not fixture:
        raise DensePublicationNotRunError("publication input domain/type drifted")
    return _make_inputs(
        fixture=fixture,
        authorization_raw=value.authorization_raw,
        schedule_raw=value.schedule_raw,
        task_sources_raw=value.task_sources_raw,
        reviewed_authorization_revision=value.reviewed_authorization_revision,
        execution_head_revision=value.execution_head_revision,
    )


def _translate(error: BaseException) -> DensePublicationError:
    if isinstance(error, DensePublicationError):
        return error
    if isinstance(error, mechanics.RegularFilePublicationV2AmbiguousError):
        return DensePublicationAmbiguousError(str(error))
    if isinstance(error, mechanics.RegularFilePublicationV2InvalidError):
        return DensePublicationInvalidError(str(error))
    return DensePublicationNotRunError(str(error))


def _layout(output_path: Path | str) -> mechanics.RegularFileLayoutV2:
    try:
        return mechanics.RegularFileLayoutV2.from_output_path(output_path)
    except mechanics.RegularFilePublicationV2Error as error:
        raise _translate(error) from error


def capture_dense_parent_binding(output_path: Path | str) -> dict:
    try:
        return mechanics.build_synthetic_parent_binding_v2(output_path)
    except mechanics.RegularFilePublicationV2Error as error:
        raise _translate(error) from error


def freeze_dense_parent_binding(
    output_path: Path | str, expected_binding: object
) -> dict:
    try:
        return mechanics.freeze_reviewed_parent_binding_v2(
            output_path, expected_binding
        )
    except mechanics.RegularFilePublicationV2Error as error:
        raise _translate(error) from error


def preflight_dense_parent_binding(
    output_path: Path | str, expected_binding: object
) -> dict:
    try:
        layout = _layout(output_path)
        binding = freeze_dense_parent_binding(output_path, expected_binding)
        parent = mechanics._open_bound_parent(layout.output_path.parent, binding)
        try:
            mechanics._validate_layout_against_parent(parent, layout)
            mechanics._assert_no_legacy_namespace(parent)
            before = (
                mechanics._parent_generation(parent),
                mechanics._reserved_generation(parent, layout.reserved_names),
            )
            for name in layout.reserved_names:
                mechanics._assert_name_absent(parent, name)
            parent.fsync()
            parent.assert_path()
            after = (
                mechanics._parent_generation(parent),
                mechanics._reserved_generation(parent, layout.reserved_names),
            )
            if before != after:
                raise DensePublicationAmbiguousError(
                    "output namespace generation changed"
                )
            return binding
        finally:
            parent.close()
    except mechanics.RegularFilePublicationV2Error as error:
        raise _translate(error) from error


def revalidate_dense_parent_binding(
    output_path: Path | str, expected_binding: object
) -> dict:
    try:
        return mechanics.revalidate_reviewed_parent_binding_v2(
            output_path, expected_binding
        )
    except mechanics.RegularFilePublicationV2Error as error:
        raise _translate(error) from error


@dataclass(frozen=True)
class DensePublicationContextV2R3:
    run_binding_raw: bytes = field(repr=False)

    @property
    def run_binding(self) -> dict:
        return _parse(self.run_binding_raw, "run binding")

    @property
    def run_binding_digest(self) -> str:
        return self.run_binding["deterministic_digest"]


@dataclass(frozen=True)
class DensePublicationBatchV2R3:
    records: object


def _attempt(
    layout: mechanics.RegularFileLayoutV2,
    inputs: DensePublicationInputsV2R3,
    owner_nonce: str,
) -> dict:
    auth = inputs.authorization
    domain = _Domain(inputs.fixture)
    return _digested(
        {
            "artifact_kind": domain.artifact_kind,
            "artifact_layout": ARTIFACT_LAYOUT,
            "authorization_digest": auth["deterministic_digest"],
            "names": layout.names,
            "output_parent_binding": auth["output_parent_binding"],
            "output_parent_binding_digest": auth["output_parent_binding_digest"],
            "output_path": str(layout.output_path),
            "output_path_digest": layout.output_path_digest,
            "owner_nonce": owner_nonce,
            "phase": "PRE_OUTCOME",
            "publication_backend": PUBLICATION_BACKEND,
            "schema_version": domain.schema("attempt"),
            "status": "PENDING",
        }
    )


def _phase(
    domain: _Domain,
    attempt: Mapping[str, Any],
    *,
    phase: str,
    status: str,
    previous_receipt_digest: str,
    extra: Mapping[str, Any] | None = None,
) -> dict:
    value = {
        "artifact_kind": domain.artifact_kind,
        "artifact_layout": ARTIFACT_LAYOUT,
        "attempt_receipt_digest": attempt["deterministic_digest"],
        "authorization_digest": attempt["authorization_digest"],
        "output_parent_binding_digest": attempt["output_parent_binding_digest"],
        "output_path": attempt["output_path"],
        "output_path_digest": attempt["output_path_digest"],
        "owner_nonce": attempt["owner_nonce"],
        "phase": phase,
        "previous_receipt_digest": previous_receipt_digest,
        "publication_backend": PUBLICATION_BACKEND,
        "schema_version": domain.schema("phase"),
        "status": status,
    }
    if extra:
        if set(extra).intersection(value):
            raise DensePublicationInvalidError("phase fields overlap")
        value.update(extra)
    return _digested(value)


def _context(
    inputs: DensePublicationInputsV2R3, attempt: dict, started: dict
) -> DensePublicationContextV2R3:
    auth = inputs.authorization
    domain = _Domain(inputs.fixture)
    fields = (
        "analysis_manifest_digest",
        "anchor_qualification_digest",
        "artifact_id",
        "artifact_layout",
        "authorization_scope",
        "budget_manifest_digest",
        "bundle_id",
        "dense_scale_seal_digest",
        "method_manifest_digest",
        "output_parent_binding_digest",
        "output_path",
        "output_path_digest",
        "preregistration_file_sha256",
        "proposal_manifest_digest",
        "publication_backend",
        "runtime_binding_digest",
        "runtime_qualification_digest",
        "schedule_digest",
    )
    value = {name: auth[name] for name in fields}
    value.update(
        {
            "artifact_kind": domain.artifact_kind,
            "attempt_receipt_digest": attempt["deterministic_digest"],
            "authorization_schema_version": auth["schema_version"],
            "execution_authorization_digest": auth["deterministic_digest"],
            "execution_head_revision": inputs.execution_head_revision,
            "execution_mode": domain.execution_mode,
            "fixture_design_digest": auth.get("fixture_design_digest"),
            "owner_nonce": attempt["owner_nonce"],
            "reviewed_authorization_revision": inputs.reviewed_authorization_revision,
            "runner_build_digest": auth["runner_build_attestation"][
                "deterministic_digest"
            ],
            "schema_version": domain.schema("run-binding", "v1"),
            "search_build_digest": auth["runner_build_attestation"][
                "search_build_digest"
            ],
            "started_receipt_digest": started["deterministic_digest"],
        }
    )
    binding = _digested(value)
    _require_object(binding, RUN_BINDING_FIELDS, "run binding")
    return DensePublicationContextV2R3(_canonical(binding))


def _validate_budget(value: object, cell_key: dict) -> None:
    budget = _require_object(value, _BUDGET_FIELDS, "budget evidence")
    if budget["budget_valid"] is not True or type(budget["stop_reason"]) is not str:
        raise DensePublicationInvalidError("budget evidence is invalid")
    profile = budget["profile_spec"]
    if type(profile) is not dict or sha256_json(profile) != cell_key.get(
        "budget_profile_spec_digest"
    ):
        raise DensePublicationInvalidError("budget profile identity drifted")
    primary = budget["primary_axis"]
    if primary not in TRACK_A_WORK_AXES or primary != profile.get("primary_axis"):
        raise DensePublicationInvalidError("primary budget axis drifted")
    axes = set(TRACK_A_WORK_AXES)
    for name in ("usage", "remaining"):
        mapping = budget[name]
        if (
            type(mapping) is not dict
            or set(mapping) != axes
            or any(type(v) is not int or v < 0 for v in mapping.values())
        ):
            raise DensePublicationInvalidError("work-axis charge snapshot drifted")
    limits = profile.get("budget")
    if type(limits) is not dict or set(limits) != axes:
        raise DensePublicationInvalidError("budget work-axis limits drifted")
    if any(
        type(limits[a]) is not int
        or limits[a] < 0
        or budget["usage"][a] + budget["remaining"][a] != limits[a]
        for a in axes
    ):
        raise DensePublicationInvalidError("budget charges do not close")
    nonprimary = {a: budget["remaining"][a] for a in TRACK_A_WORK_AXES if a != primary}
    if (
        _canonical(budget["non_primary_headroom"]) != _canonical(nonprimary)
        or any(v <= 0 for v in nonprimary.values())
        or type(budget["primary_headroom"]) is not int
        or budget["primary_headroom"] != budget["remaining"][primary]
        or type(budget["blocked_axes"]) is not list
        or budget["blocked_axes"] not in ([], [primary])
    ):
        raise DensePublicationInvalidError("non-primary budget guard bound")


def _freeze_batch(
    batch: object,
    inputs: DensePublicationInputsV2R3,
    context: DensePublicationContextV2R3,
) -> tuple[bytes, bytes, dict]:
    if type(batch) is not DensePublicationBatchV2R3 or type(batch.records) not in (
        list,
        tuple,
    ):
        raise DensePublicationInvalidError("action must return one exact bounded batch")
    candidates = tuple(batch.records[: EXPECTED_CELL_COUNT + 1])
    if len(candidates) != EXPECTED_CELL_COUNT:
        raise DensePublicationInvalidError("action must close exactly 384 records")
    domain = _Domain(inputs.fixture)
    schedule = inputs.schedule
    sources = inputs.task_sources
    frames: list[bytes] = []
    payloads: list[bytes] = []
    digests: list[str] = []
    total = 0
    for index, candidate in enumerate(candidates):
        if type(candidate) is not dict:
            raise DensePublicationInvalidError("record must be a plain object")
        raw = _canonical(candidate)
        record = _parse(raw, "record", cap=MAX_RECORD_BYTES)
        _require_object(record, RECORD_FIELDS, "record")
        _require_digest(record, "record")
        expected = schedule[index]
        if (
            record["schema_version"] != domain.record_schema
            or record["cell_id"] != expected["cell_id"]
            or _canonical(record["cell_key"]) != _canonical(expected["cell_key"])
            or record["run_binding_digest"] != context.run_binding_digest
            or record["source_multiset_fingerprint"]
            != sources[expected["cell_key"]["task_fingerprint"]]
            or type(record["provider_calls"]) is not int
            or record["provider_calls"] != 0
            or type(record["search_record"]) is not dict
        ):
            raise DensePublicationInvalidError(
                "record domain, order or context drifted"
            )
        trace = canonical_trace_bytes(record["search_record"])
        if (
            type(record["search_trace_byte_count"]) is not int
            or record["search_trace_byte_count"] != len(trace)
            or record["search_trace_sha256"] != _sha(trace)
        ):
            raise DensePublicationInvalidError("canonical trace byte closure drifted")
        _sha_value(record["search_run_identity_digest"], "search identity")
        replay = _require_object(
            record["replay"],
            frozenset(
                {"stage1_generative", "stage2_byte_identical", "replayed_sha256"}
            ),
            "replay",
        )
        if replay != {
            "stage1_generative": "PASS",
            "stage2_byte_identical": "PASS",
            "replayed_sha256": _sha(trace),
        }:
            raise DensePublicationInvalidError("two-stage replay receipt drifted")
        _validate_budget(record["budget_evidence"], record["cell_key"])
        frame = _canonical(
            {
                "artifact_kind": domain.artifact_kind,
                "payload": record,
                "record_index": index,
                "schema_version": domain.schema("record-frame"),
            }
        )
        total += len(frame)
        if total > MAX_RECORDS_BYTES:
            raise DensePublicationInvalidError(
                "record frames exceed the bounded byte limit"
            )
        frames.append(frame)
        payloads.append(raw)
        digests.append(record["deterministic_digest"])
    payload_raw = b"".join(payloads)
    auth = inputs.authorization
    manifest = _digested(
        {
            "artifact_kind": domain.artifact_kind,
            "cell_count": EXPECTED_CELL_COUNT,
            "claim_boundary": auth["claim_boundary"],
            "execution_authorization": auth,
            "execution_authorization_digest": auth["deterministic_digest"],
            "execution_mode": domain.execution_mode,
            "provider_calls": 0,
            "record_digests": digests,
            "records_payload_jsonl_byte_count": len(payload_raw),
            "records_payload_jsonl_sha256": _sha(payload_raw),
            "run_binding": context.run_binding,
            "run_binding_digest": context.run_binding_digest,
            "schedule_cell_ids": [row["cell_id"] for row in schedule],
            "schema_version": domain.schema("run-manifest", "v1"),
        }
    )
    _require_object(manifest, RUN_MANIFEST_FIELDS, "run manifest")
    return b"".join(frames), payload_raw, manifest


def _manifest(
    layout: mechanics.RegularFileLayoutV2,
    inputs: DensePublicationInputsV2R3,
    attempt: dict,
    started: dict,
    records: bytes,
    payloads: bytes,
    run_manifest: dict,
) -> dict:
    domain = _Domain(inputs.fixture)
    return _digested(
        {
            "artifact_id": inputs.authorization["artifact_id"],
            "artifact_kind": domain.artifact_kind,
            "artifact_layout": ARTIFACT_LAYOUT,
            "attempt_receipt_digest": attempt["deterministic_digest"],
            "authorization_digest": attempt["authorization_digest"],
            "output_parent_binding_digest": attempt["output_parent_binding_digest"],
            "output_path": str(layout.output_path),
            "output_path_digest": layout.output_path_digest,
            "owner_nonce": attempt["owner_nonce"],
            "publication_backend": PUBLICATION_BACKEND,
            "records": {
                "byte_count": len(records),
                "filename": layout.records_name,
                "payload_byte_count": len(payloads),
                "payload_sha256": _sha(payloads),
                "record_count": EXPECTED_CELL_COUNT,
                "schema_version": domain.schema("record-frame"),
                "sha256": _sha(records),
            },
            "run_manifest": run_manifest,
            "schema_version": domain.schema("collective-manifest"),
            "started_receipt_digest": started["deterministic_digest"],
        }
    )


def _ready(
    domain: _Domain, attempt: dict, started: dict, manifest: dict, records: bytes
) -> dict:
    return _phase(
        domain,
        attempt,
        phase="READY_TO_COMMIT",
        status="PENDING",
        previous_receipt_digest=started["deterministic_digest"],
        extra={
            "manifest_digest": manifest["deterministic_digest"],
            "manifest_sha256": _sha(_canonical(manifest)),
            "records_byte_count": len(records),
            "records_sha256": _sha(records),
        },
    )


def _commit(
    layout: mechanics.RegularFileLayoutV2,
    inputs: DensePublicationInputsV2R3,
    attempt: dict,
    started: dict,
    ready: dict,
    manifest: dict,
    records: bytes,
    payloads: bytes,
) -> dict:
    domain = _Domain(inputs.fixture)
    return _digested(
        {
            "artifact_id": inputs.authorization["artifact_id"],
            "artifact_kind": domain.artifact_kind,
            "artifact_layout": ARTIFACT_LAYOUT,
            "attempt_receipt_digest": attempt["deterministic_digest"],
            "authorization_digest": attempt["authorization_digest"],
            "manifest": {
                "deterministic_digest": manifest["deterministic_digest"],
                "filename": layout.manifest_name,
                "sha256": _sha(_canonical(manifest)),
            },
            "output_path": str(layout.output_path),
            "output_parent_binding_digest": attempt["output_parent_binding_digest"],
            "output_path_digest": layout.output_path_digest,
            "owner_nonce": attempt["owner_nonce"],
            "phase": "COMMITTED",
            "previous_receipt_digest": ready["deterministic_digest"],
            "publication_backend": PUBLICATION_BACKEND,
            "ready_receipt_digest": ready["deterministic_digest"],
            "records": {
                "byte_count": len(records),
                "filename": layout.records_name,
                "payload_byte_count": len(payloads),
                "payload_sha256": _sha(payloads),
                "sha256": _sha(records),
            },
            "run_manifest_digest": manifest["run_manifest"]["deterministic_digest"],
            "schema_version": domain.schema("collective-commit"),
            "started_receipt_digest": started["deterministic_digest"],
            "status": "COMMITTED",
        }
    )


def _create(session: mechanics._PublicationSession, name: str, payload: dict | bytes):
    try:
        return (
            session.create_data(name, payload)
            if type(payload) is bytes
            else session.create_authority(name, payload)
        )
    except mechanics._NameConflictError as error:
        raise DensePublicationAmbiguousError(
            "foreign reserved entry appeared"
        ) from error
    except mechanics._CreateAfterOpenError as error:
        error.owned.close()
        raise DensePublicationAmbiguousError(
            "exclusive file ownership or durability is uncertain"
        ) from error


def _publish(
    output_path: Path | str,
    *,
    inputs: DensePublicationInputsV2R3,
    fixture: bool,
    action: Callable,
    pre_started_check: Callable,
    pre_commit_check: Callable,
    _event_hook: Callable | None,
) -> dict:
    inputs = _inputs(inputs, fixture)
    if not all(callable(x) for x in (action, pre_started_check, pre_commit_check)) or (
        _event_hook is not None and not callable(_event_hook)
    ):
        raise DensePublicationNotRunError("all publication barriers must be callable")
    auth = inputs.authorization
    layout = _layout(output_path)
    if str(layout.output_path) != auth["output_path"]:
        raise DensePublicationNotRunError("output differs from external authorization")
    domain = _Domain(fixture)
    parent = None
    session = None
    attempt = started = ready = None
    try:
        preflight_dense_parent_binding(output_path, auth["output_parent_binding"])
        parent = mechanics._open_bound_parent(
            layout.output_path.parent, auth["output_parent_binding"]
        )
        session = mechanics._PublicationSession(
            parent,
            layout,
            _event_hook,
            max_control_bytes=MAX_CONTROL_BYTES,
            max_records_bytes=MAX_RECORDS_BYTES,
        )
        for name in layout.reserved_names:
            mechanics._assert_name_absent(parent, name)
        attempt = _attempt(layout, inputs, secrets.token_hex(32))
        session.attempt_file = _create(session, layout.attempt_name, attempt)

        def phase_builder(*args, **kwargs):
            return _phase(domain, *args, **kwargs)

        try:
            mechanics._emit(_event_hook, "after_attempt", name=layout.attempt_name)
            mechanics._emit(_event_hook, "before_started", name=layout.started_name)
            pre_started_check()
            mechanics._assert_owned_exact(parent, session.attempt_file)
            parent.assert_path()
            started = _phase(
                domain,
                attempt,
                phase="STARTED",
                status="PENDING",
                previous_receipt_digest=attempt["deterministic_digest"],
            )
            session.started_file = _create(session, layout.started_name, started)
        except (
            DensePublicationAmbiguousError,
            mechanics.RegularFilePublicationV2AmbiguousError,
        ):
            raise
        except BaseException as error:
            try:
                mechanics._publish_not_run(
                    session,
                    attempt,
                    error,
                    phase_payload_builder=phase_builder,
                    terminal_message="dense publication stopped before STARTED; authorization spent",
                )
            except mechanics.RegularFilePublicationV2NotRunError as refusal:
                raise DensePublicationNotRunError(
                    str(refusal), authorization_consumed=True
                ) from refusal
        try:
            mechanics._prove_terminal_collective(
                session,
                terminal="STARTED_BOUNDARY",
                required=(session.attempt_file, session.started_file),
                absent=(
                    layout.ready_name,
                    layout.not_run_name,
                    layout.invalid_name,
                    layout.records_name,
                    layout.manifest_name,
                    layout.commit_name,
                ),
            )
            mechanics._emit(_event_hook, "after_started", name=layout.started_name)
            context = _context(inputs, attempt, started)
            try:
                batch = action(context)
            except BaseException as action_error:
                raise DensePublicationInvalidError(
                    "action failed after durable STARTED"
                ) from action_error
            records, payloads, run_manifest = _freeze_batch(batch, inputs, context)
            session.records_file = _create(session, layout.records_name, records)
            mechanics._emit(_event_hook, "after_records", name=layout.records_name)
            manifest = _manifest(
                layout, inputs, attempt, started, records, payloads, run_manifest
            )
            session.manifest_file = _create(session, layout.manifest_name, manifest)
            mechanics._emit(_event_hook, "after_manifest", name=layout.manifest_name)
            ready_candidate = _ready(domain, attempt, started, manifest, records)
            session.ready_file = _create(session, layout.ready_name, ready_candidate)
            ready = ready_candidate
            mechanics._emit(_event_hook, "after_ready", name=layout.ready_name)
            mechanics._emit(_event_hook, "before_commit", name=layout.commit_name)
            pre_commit_check()
            mechanics._prove_terminal_collective(
                session,
                terminal="PRE_COMMIT",
                required=(
                    session.attempt_file,
                    session.started_file,
                    session.records_file,
                    session.manifest_file,
                    session.ready_file,
                ),
                absent=(layout.not_run_name, layout.invalid_name, layout.commit_name),
            )
            commit = _commit(
                layout, inputs, attempt, started, ready, manifest, records, payloads
            )
            try:
                session.commit_file = _create(session, layout.commit_name, commit)
            except mechanics._CreateBeforeOpenError as error:
                raise DensePublicationAmbiguousError(
                    "commit creation absence is uncertain"
                ) from error
            try:
                mechanics._emit(_event_hook, "after_commit", name=layout.commit_name)
            except BaseException:
                pass
            mechanics._prove_terminal_collective(
                session,
                terminal="COMMITTED",
                required=(
                    session.attempt_file,
                    session.started_file,
                    session.records_file,
                    session.manifest_file,
                    session.ready_file,
                    session.commit_file,
                ),
                absent=(layout.not_run_name, layout.invalid_name),
            )
            return {
                "status": "COMMITTED",
                "artifact_kind": domain.artifact_kind,
                "artifact_path": str(layout.output_path),
                "artifact_layout": ARTIFACT_LAYOUT,
                "authorization_digest": auth["deterministic_digest"],
                "authorization_consumed": True,
                "retry_permitted": False,
                "artifact_commit_digest": commit["deterministic_digest"],
                "collective_manifest_digest": manifest["deterministic_digest"],
                "run_manifest_digest": run_manifest["deterministic_digest"],
                "output_parent_binding_digest": auth["output_parent_binding_digest"],
            }
        except (
            DensePublicationAmbiguousError,
            mechanics.RegularFilePublicationV2AmbiguousError,
        ):
            raise
        except BaseException as error:
            mechanics._publish_invalid(
                session,
                attempt,
                started,
                ready,
                error,
                failure_phase="STARTED" if ready is None else "READY_TO_COMMIT",
                phase_payload_builder=phase_builder,
                terminal_message="dense publication crossed STARTED without a commit",
            )
    except DensePublicationError:
        raise
    except mechanics.RegularFilePublicationV2Error as error:
        raise _translate(error) from error
    except BaseException as error:
        if session is not None and session.attempt_file is not None:
            raise DensePublicationAmbiguousError(
                "publication could not prove a terminal collective"
            ) from error
        raise DensePublicationNotRunError(
            "publication failed before attempt ownership"
        ) from error
    finally:
        if session is not None:
            session.close()
        if parent is not None:
            parent.close()


def publish_dense_scale_v2r3(
    output_path: Path | str,
    *,
    inputs: DensePublicationInputsV2R3,
    action: Callable,
    pre_started_check: Callable,
    pre_commit_check: Callable,
    _event_hook: Callable | None = None,
) -> dict:
    return _publish(
        output_path,
        inputs=inputs,
        fixture=False,
        action=action,
        pre_started_check=pre_started_check,
        pre_commit_check=pre_commit_check,
        _event_hook=_event_hook,
    )


def publish_dense_scale_fixture_v2r3(
    output_path: Path | str,
    *,
    inputs: DensePublicationInputsV2R3,
    action: Callable,
    pre_started_check: Callable,
    pre_commit_check: Callable,
    _event_hook: Callable | None = None,
) -> dict:
    return _publish(
        output_path,
        inputs=inputs,
        fixture=True,
        action=action,
        pre_started_check=pre_started_check,
        pre_commit_check=pre_commit_check,
        _event_hook=_event_hook,
    )


@dataclass(frozen=True)
class VerifiedDensePublicationV2R3:
    output_path: Path
    authorization_digest: str
    output_parent_binding_digest: str
    artifact_commit_digest: str
    collective_manifest_digest: str
    run_manifest_digest: str
    collective_generation: tuple
    _records_raw: bytes = field(repr=False)
    _payload_records_raw: bytes = field(repr=False)
    _manifest_raw: bytes = field(repr=False)
    _commit_raw: bytes = field(repr=False)

    @property
    def authority_generation(self) -> tuple:
        """Raw identities, allowing an unrelated summary in the same parent.

        Each observation still closes the full directory generation twice.
        Between observations only the parent device/inode and every reserved
        raw entry are authority; summary creation legitimately changes parent
        size and timestamps.
        """
        parent, reserved = self.collective_generation
        return (parent[:2], reserved)

    @property
    def records(self) -> tuple[dict, ...]:
        return tuple(
            _parse(raw, "verified record", cap=MAX_RECORD_BYTES)
            for raw in self._payload_records_raw.splitlines(keepends=True)
        )

    @property
    def record_frames(self) -> tuple[dict, ...]:
        return tuple(
            _parse(raw, "verified frame", cap=MAX_RECORD_BYTES)
            for raw in self._records_raw.splitlines(keepends=True)
        )

    @property
    def records_jsonl_bytes(self) -> bytes:
        return self._records_raw

    @property
    def payload_records_jsonl_bytes(self) -> bytes:
        return self._payload_records_raw

    @property
    def collective_manifest(self) -> dict:
        return _parse(self._manifest_raw, "verified collective manifest")

    @property
    def run_manifest(self) -> dict:
        return self.collective_manifest["run_manifest"]

    @property
    def commit_receipt(self) -> dict:
        return _parse(self._commit_raw, "verified commit")


def _inspect_payload(
    parent, layout, inputs
) -> tuple[dict, tuple[tuple[str, bytes], ...]]:
    domain = _Domain(inputs.fixture)
    snapshots: dict[str, bytes] = {}

    def read(name, *, cap=MAX_CONTROL_BYTES):
        raw = mechanics._read_bounded_regular_file_at(parent, name, max_bytes=cap)
        snapshots[name] = raw
        return _parse(raw, name, cap=cap)

    def exact(observed, expected, label):
        if _canonical(observed) != _canonical(expected):
            raise DensePublicationAmbiguousError(
                f"{label} canonical receipt does not close"
            )

    if not mechanics._name_exists(parent, layout.attempt_name):
        for name in layout.reserved_names:
            mechanics._assert_name_absent(parent, name)
        return {
            "status": "UNRESERVED",
            "authorization_consumed": False,
            "retry_permitted": False,
        }, ()
    attempt = read(layout.attempt_name)
    nonce = attempt.get("owner_nonce") if type(attempt) is dict else None
    if not mechanics._is_owner_nonce(nonce):
        raise DensePublicationAmbiguousError("attempt owner nonce is invalid")
    exact(attempt, _attempt(layout, inputs, nonce), "attempt")
    terminals = [
        name
        for name in (layout.not_run_name, layout.invalid_name, layout.commit_name)
        if mechanics._name_exists(parent, name)
    ]
    if len(terminals) != 1:
        raise DensePublicationAmbiguousError(
            "attempt is nonterminal or conflicting; no retry"
        )
    status = {
        layout.not_run_name: "NOT_RUN",
        layout.invalid_name: "INVALID",
        layout.commit_name: "COMMITTED",
    }[terminals[0]]
    if status == "NOT_RUN":
        for name in (
            layout.started_name,
            layout.ready_name,
            layout.invalid_name,
            layout.records_name,
            layout.manifest_name,
            layout.commit_name,
        ):
            mechanics._assert_name_absent(parent, name)
        terminal = read(layout.not_run_name)
        mechanics._validate_reason_code(terminal, "pre_outcome")
        exact(
            terminal,
            _phase(
                domain,
                attempt,
                phase="PRE_OUTCOME",
                status="NOT_RUN",
                previous_receipt_digest=attempt["deterministic_digest"],
                extra={"reason_code": terminal["reason_code"]},
            ),
            "NOT_RUN",
        )
        return {
            "status": status,
            "authorization_consumed": True,
            "retry_permitted": False,
        }, tuple(sorted(snapshots.items()))
    mechanics._assert_name_absent(parent, layout.not_run_name)
    started = read(layout.started_name)
    exact(
        started,
        _phase(
            domain,
            attempt,
            phase="STARTED",
            status="PENDING",
            previous_receipt_digest=attempt["deterministic_digest"],
        ),
        "STARTED",
    )
    ready = None
    records_raw = payloads_raw = b""
    manifest = None
    if status == "COMMITTED" or mechanics._name_exists(parent, layout.ready_name):
        records_raw = mechanics._read_bounded_regular_file_at(
            parent, layout.records_name, max_bytes=MAX_RECORDS_BYTES
        )
        snapshots[layout.records_name] = records_raw
        lines = records_raw.splitlines(keepends=True)
        if len(lines) != EXPECTED_CELL_COUNT:
            raise DensePublicationAmbiguousError("persisted record count is not 384")
        records = []
        for index, raw in enumerate(lines):
            frame = _parse(raw, "record frame", cap=MAX_RECORD_BYTES)
            _require_object(
                frame,
                frozenset(
                    {"artifact_kind", "payload", "record_index", "schema_version"}
                ),
                "record frame",
            )
            if (
                frame["artifact_kind"] != domain.artifact_kind
                or frame["schema_version"] != domain.schema("record-frame")
                or type(frame["record_index"]) is not int
                or frame["record_index"] != index
            ):
                raise DensePublicationAmbiguousError(
                    "persisted record frame domain/order drifted"
                )
            records.append(frame["payload"])
        frozen_raw, payloads_raw, run_manifest = _freeze_batch(
            DensePublicationBatchV2R3(records),
            inputs,
            _context(inputs, attempt, started),
        )
        if frozen_raw != records_raw:
            raise DensePublicationAmbiguousError(
                "persisted record canonical bytes drifted"
            )
        manifest = read(layout.manifest_name)
        exact(
            manifest,
            _manifest(
                layout,
                inputs,
                attempt,
                started,
                records_raw,
                payloads_raw,
                run_manifest,
            ),
            "collective manifest",
        )
        ready = read(layout.ready_name)
        exact(ready, _ready(domain, attempt, started, manifest, records_raw), "READY")
    if status == "INVALID":
        mechanics._assert_name_absent(parent, layout.commit_name)
        if ready is None:
            # Partial regular data is retained as evidence; it is never a result.
            for name in (layout.records_name, layout.manifest_name):
                if mechanics._name_exists(parent, name):
                    snapshots[name] = mechanics._read_bounded_regular_file_at(
                        parent,
                        name,
                        max_bytes=MAX_RECORDS_BYTES
                        if name == layout.records_name
                        else MAX_CONTROL_BYTES,
                    )
        terminal = read(layout.invalid_name)
        mechanics._validate_reason_code(terminal, "post_started")
        exact(
            terminal,
            _phase(
                domain,
                attempt,
                phase="STARTED" if ready is None else "READY_TO_COMMIT",
                status="INVALID",
                previous_receipt_digest=(started if ready is None else ready)[
                    "deterministic_digest"
                ],
                extra={"reason_code": terminal["reason_code"]},
            ),
            "INVALID",
        )
    else:
        mechanics._assert_name_absent(parent, layout.invalid_name)
        commit = read(layout.commit_name)
        exact(
            commit,
            _commit(
                layout,
                inputs,
                attempt,
                started,
                ready,
                manifest,
                records_raw,
                payloads_raw,
            ),
            "COMMITTED",
        )
    return {
        "status": status,
        "authorization_consumed": True,
        "retry_permitted": False,
    }, tuple(sorted(snapshots.items()))


def _observe(output_path, *, inputs, fixture):
    inputs = _inputs(inputs, fixture)
    auth = inputs.authorization
    layout = _layout(output_path)
    if str(layout.output_path) != auth["output_path"]:
        raise DensePublicationNotRunError("observer output differs from authorization")
    parent = None
    try:
        parent = mechanics._open_bound_parent(
            layout.output_path.parent, auth["output_parent_binding"]
        )
        mechanics._validate_layout_against_parent(parent, layout)
        previous = None
        for _ in range(2):
            parent.assert_path()
            mechanics._assert_no_legacy_namespace(parent)
            before = (
                mechanics._parent_generation(parent),
                mechanics._reserved_generation(parent, layout.reserved_names),
            )
            result, snapshots = _inspect_payload(parent, layout, inputs)
            for name, _raw in snapshots:
                mechanics._forward_sync_exact_regular_file_at(parent, name)
            if snapshots:
                parent.fsync()
            parent.assert_path()
            mechanics._assert_no_legacy_namespace(parent)
            after = (
                mechanics._parent_generation(parent),
                mechanics._reserved_generation(parent, layout.reserved_names),
            )
            current = (result, snapshots, before)
            if before != after or (previous is not None and current != previous):
                raise DensePublicationAmbiguousError(
                    "collective generation changed during verification"
                )
            previous = current
        return layout, result, snapshots, before
    except DensePublicationAmbiguousError:
        raise
    except BaseException as error:
        raise DensePublicationAmbiguousError(
            "independent collective verification failed"
        ) from error
    finally:
        if parent is not None:
            parent.close()


def inspect_dense_scale_v2r3(output_path, *, inputs):
    return _observe(output_path, inputs=inputs, fixture=False)[1]


def inspect_dense_scale_fixture_v2r3(output_path, *, inputs):
    return _observe(output_path, inputs=inputs, fixture=True)[1]


def _verify(output_path, *, inputs, fixture) -> VerifiedDensePublicationV2R3:
    layout, result, snapshots, generation = _observe(
        output_path, inputs=inputs, fixture=fixture
    )
    if result["status"] != "COMMITTED":
        raise DensePublicationAmbiguousError(
            "only an exact COMMITTED collective can be analyzed"
        )
    captured = dict(snapshots)
    manifest = _parse(captured[layout.manifest_name], "collective manifest")
    commit = _parse(captured[layout.commit_name], "commit")
    payloads = b"".join(
        _canonical(_parse(raw, "frame", cap=MAX_RECORD_BYTES)["payload"])
        for raw in captured[layout.records_name].splitlines(keepends=True)
    )
    return VerifiedDensePublicationV2R3(
        layout.output_path,
        inputs.authorization["deterministic_digest"],
        inputs.authorization["output_parent_binding_digest"],
        commit["deterministic_digest"],
        manifest["deterministic_digest"],
        manifest["run_manifest"]["deterministic_digest"],
        generation,
        captured[layout.records_name],
        payloads,
        captured[layout.manifest_name],
        captured[layout.commit_name],
    )


def verify_dense_scale_v2r3(output_path, *, inputs) -> VerifiedDensePublicationV2R3:
    return _verify(output_path, inputs=inputs, fixture=False)


def verify_dense_scale_fixture_v2r3(
    output_path, *, inputs
) -> VerifiedDensePublicationV2R3:
    return _verify(output_path, inputs=inputs, fixture=True)


@dataclass(frozen=True)
class DenseExecutionHeadHintV2R3:
    """Untrusted control-file hint, never Git or execution authority.

    An analyzer must verify this revision's ancestry and exact historical
    source receipts before using it in the independent full verifier.
    """

    execution_head_revision: str
    output_path: Path
    authorization_digest: str
    fixture: bool
    manifest_generation: tuple
    _parent_binding_raw: bytes = field(repr=False)
    _manifest_raw: bytes = field(repr=False)

    def revalidate(self) -> None:
        observed = _read_execution_head_hint(
            self.output_path,
            authorization_digest=self.authorization_digest,
            expected_parent_binding=_parse(self._parent_binding_raw, "parent binding"),
            fixture=self.fixture,
        )
        if observed != self:
            raise DensePublicationAmbiguousError(
                "control-manifest hint identity changed"
            )


def _read_execution_head_hint(
    output_path, *, authorization_digest, expected_parent_binding, fixture
) -> DenseExecutionHeadHintV2R3:
    authorization_digest = _sha_value(authorization_digest, "external authorization")
    layout = _layout(output_path)
    binding = freeze_dense_parent_binding(output_path, expected_parent_binding)
    parent = None
    try:
        parent = mechanics._open_bound_parent(layout.output_path.parent, binding)
        parent.assert_path()
        mechanics._assert_no_legacy_namespace(parent)
        before_parent = mechanics._parent_generation(parent)
        before_entry = mechanics._reserved_generation(parent, (layout.manifest_name,))
        raw = mechanics._read_bounded_regular_file_at(
            parent, layout.manifest_name, max_bytes=MAX_CONTROL_BYTES
        )
        manifest = _parse(raw, "untrusted control manifest")
        domain = _Domain(fixture)
        if (
            type(manifest) is not dict
            or manifest.get("schema_version") != domain.schema("collective-manifest")
            or manifest.get("artifact_kind") != domain.artifact_kind
            or manifest.get("authorization_digest") != authorization_digest
            or manifest.get("output_parent_binding_digest")
            != binding["deterministic_digest"]
        ):
            raise DensePublicationAmbiguousError(
                "untrusted control manifest domain drifted"
            )
        run_manifest = manifest.get("run_manifest")
        run_binding = (
            run_manifest.get("run_binding") if type(run_manifest) is dict else None
        )
        if type(run_binding) is not dict:
            raise DensePublicationAmbiguousError("control manifest has no run binding")
        head = _oid(
            run_binding.get("execution_head_revision"), "untrusted execution HEAD"
        )
        after_entry = mechanics._reserved_generation(parent, (layout.manifest_name,))
        after_parent = mechanics._parent_generation(parent)
        parent.assert_path()
        if before_parent != after_parent or before_entry != after_entry:
            raise DensePublicationAmbiguousError("control-manifest generation changed")
        return DenseExecutionHeadHintV2R3(
            head,
            layout.output_path,
            authorization_digest,
            fixture,
            (before_parent[:2], before_entry),
            _canonical(binding),
            raw,
        )
    except DensePublicationAmbiguousError:
        raise
    except BaseException as error:
        raise DensePublicationAmbiguousError(
            "untrusted execution-head hint is unavailable"
        ) from error
    finally:
        if parent is not None:
            parent.close()


def read_dense_scale_execution_head_hint(
    output_path, *, authorization_digest, expected_parent_binding
) -> DenseExecutionHeadHintV2R3:
    return _read_execution_head_hint(
        output_path,
        authorization_digest=authorization_digest,
        expected_parent_binding=expected_parent_binding,
        fixture=False,
    )


def read_dense_scale_fixture_execution_head_hint(
    output_path, *, authorization_digest, expected_parent_binding
) -> DenseExecutionHeadHintV2R3:
    return _read_execution_head_hint(
        output_path,
        authorization_digest=authorization_digest,
        expected_parent_binding=expected_parent_binding,
        fixture=True,
    )


def _publish_summary(
    output_path: Path | str,
    canonical_summary_bytes: bytes,
    *,
    fixture: bool,
    artifact_path: Path | str,
    protected_roots: Sequence[Path],
    pre_publication_check: Callable,
    post_durability_check: Callable,
) -> dict:
    summary = _parse(canonical_summary_bytes, "summary")
    _require_object(
        summary, FIXTURE_SUMMARY_FIELDS if fixture else SUMMARY_FIELDS, "summary"
    )
    _require_digest(summary, "summary")
    domain = _Domain(fixture)
    if (
        summary["schema_version"]
        != (FIXTURE_SUMMARY_SCHEMA_VERSION if fixture else SUMMARY_SCHEMA_VERSION)
        or summary["bundle_id"] != domain.bundle_id
        or summary["execution_mode"] != domain.execution_mode
        or type(summary["cell_count"]) is not int
        or summary["cell_count"] != EXPECTED_CELL_COUNT
    ):
        raise DensePublicationNotRunError("summary domain drifted")
    if not fixture and summary["decision"] not in {
        "READY_TO_PREREGISTER_SOURCE_DISJOINT_CONFIRMATION",
        "STOP_REPAIR_NO_LOCKED_128_RUN",
    }:
        raise DensePublicationNotRunError("summary decision drifted")
    if not callable(pre_publication_check) or not callable(post_durability_check):
        raise DensePublicationNotRunError("summary authority barriers are mandatory")
    destination = _layout(output_path).output_path
    artifact = _layout(artifact_path)
    if (
        destination.parent == artifact.output_path.parent
        and destination.name.lower()
        in {name.lower() for name in artifact.reserved_names}
    ):
        raise DensePublicationNotRunError("summary overlaps the raw reserved namespace")
    # Opaque atomic writer only; no diagnostic bundle/runner/analyzer entry point.
    from qmc_bmgs.experiments import countdown_thompson_diagnostic_analysis as atomic

    pinned = ()
    try:
        if not protected_roots:
            raise DensePublicationNotRunError("summary requires pinned protected roots")
        pinned = atomic._pin_protected_roots(tuple(Path(p) for p in protected_roots))
        if any(
            destination == root.path or destination.is_relative_to(root.path)
            for root in pinned
        ):
            raise DensePublicationNotRunError(
                "summary overlaps protected raw/source/bundle root"
            )
        pre_publication_check()
        atomic._assert_pinned_protected_roots(pinned)

        def revalidate():
            atomic._assert_pinned_protected_roots(pinned)
            post_durability_check()
            atomic._assert_pinned_protected_roots(pinned)

        atomic._atomic_write_no_replace(
            destination,
            canonical_summary_bytes,
            protected_roots=pinned,
            post_durability_check=revalidate,
        )
        return summary
    except atomic.DiagnosticAnalysisPublicationAmbiguousError as error:
        raise DensePublicationAmbiguousError(
            "summary identity/durability is ambiguous"
        ) from error
    except DensePublicationError:
        raise
    except BaseException as error:
        raise DensePublicationInvalidError(
            "summary publication or revalidation failed"
        ) from error
    finally:
        if pinned:
            atomic._close_pinned_protected_roots(pinned)


def publish_dense_scale_summary(
    output_path,
    canonical_summary_bytes,
    *,
    artifact_path,
    protected_roots=(),
    pre_publication_check,
    post_durability_check,
):
    return _publish_summary(
        output_path,
        canonical_summary_bytes,
        fixture=False,
        artifact_path=artifact_path,
        protected_roots=protected_roots,
        pre_publication_check=pre_publication_check,
        post_durability_check=post_durability_check,
    )


def publish_dense_scale_fixture_summary(
    output_path,
    canonical_summary_bytes,
    *,
    artifact_path,
    protected_roots=(),
    pre_publication_check,
    post_durability_check,
):
    return _publish_summary(
        output_path,
        canonical_summary_bytes,
        fixture=True,
        artifact_path=artifact_path,
        protected_roots=protected_roots,
        pre_publication_check=pre_publication_check,
        post_durability_check=post_durability_check,
    )
