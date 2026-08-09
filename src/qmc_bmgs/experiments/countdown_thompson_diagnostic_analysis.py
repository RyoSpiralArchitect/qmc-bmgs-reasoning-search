"""Fail-closed analysis for the sealed Thompson engineering diagnostic.

The analyzer accepts paths, not caller-created authority objects.  It
independently verifies the outcome-blind bundle, validates the exact run
artifact closure and all 240 cell identities, and performs stage-one plus
stage-two search replay before constructing any outcome-bearing summary.

The output is deliberately engineering-only: exact-rational mechanism metrics,
dense terminal diagnostics, raw task vectors, and a preregistered escalation
status.  It has no confidence interval, p-value, superiority claim, or locked
evaluation authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import secrets
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping, Sequence, TypedDict

from qmc_bmgs.benchmarks.countdown import CountdownTask
from qmc_bmgs.experiments.countdown_thompson_diagnostic_manifest import (
    BUNDLE_ID,
    EXPECTED_CELL_COUNT,
    DiagnosticCell,
    VerifiedDiagnosticBundle,
    iter_countdown_thompson_diagnostic_cells,
    verify_countdown_thompson_diagnostic_bundle,
)
from qmc_bmgs.substrate.budget import TRACK_A_WORK_AXES, TrackAWorkBudget
from qmc_bmgs.substrate.countdown_search import (
    TrackABudgetProfile,
    TrackAMethodSpec,
    replay_countdown_track_a_search_bytes,
)
from qmc_bmgs.substrate.proposals import TrackAProposalSpec
from qmc_bmgs.substrate.trace import (
    TraceValidationError,
    canonical_json,
    canonical_trace_bytes,
    sha256_json,
    strict_json_loads,
)


RUN_MANIFEST_SCHEMA_VERSION = "qmc-bmgs-countdown-thompson-diagnostic-run-manifest/v1"
RUN_RECORD_SCHEMA_VERSION = "qmc-bmgs-countdown-thompson-diagnostic-run-record/v1"
ANALYSIS_SCHEMA_VERSION = "qmc-bmgs-countdown-thompson-diagnostic-result/v1"
ANALYZER_BUILD_SCHEMA_VERSION = (
    "qmc-bmgs-countdown-thompson-diagnostic-analyzer-build/v1"
)
ARTIFACT_COMMIT_SCHEMA_VERSION = (
    "qmc-bmgs-countdown-thompson-diagnostic-artifact-commit/v1"
)
SUMMARY_FILENAME = "summary.json"
RUN_ARTIFACT_FILENAMES = ("commit.json", "manifest.json", "records.jsonl")
ANALYZER_RELATIVE_PATH = Path(
    "src/qmc_bmgs/experiments/countdown_thompson_diagnostic_analysis.py"
)

_SEARCH_SOURCE_PATHS = (
    "src/qmc_bmgs/__init__.py",
    "src/qmc_bmgs/benchmarks/__init__.py",
    "src/qmc_bmgs/benchmarks/countdown.py",
    "src/qmc_bmgs/substrate/__init__.py",
    "src/qmc_bmgs/substrate/budget.py",
    "src/qmc_bmgs/substrate/countdown_search.py",
    "src/qmc_bmgs/substrate/perturbations.py",
    "src/qmc_bmgs/substrate/proposals.py",
    "src/qmc_bmgs/substrate/trace.py",
)
_RUNNER_SOURCE_PATHS = (
    "src/qmc_bmgs/experiments/__init__.py",
    "src/qmc_bmgs/experiments/countdown_track_a_canary_manifest.py",
    "src/qmc_bmgs/experiments/countdown_thompson_diagnostic_manifest.py",
    "src/qmc_bmgs/experiments/countdown_thompson_diagnostic_runner.py",
    ANALYZER_RELATIVE_PATH.as_posix(),
)
_CURRENT_REPLAY_MODULE_PATHS = {
    "qmc_bmgs": _SEARCH_SOURCE_PATHS[0],
    "qmc_bmgs.benchmarks": _SEARCH_SOURCE_PATHS[1],
    "qmc_bmgs.benchmarks.countdown": _SEARCH_SOURCE_PATHS[2],
    "qmc_bmgs.substrate": _SEARCH_SOURCE_PATHS[3],
    "qmc_bmgs.substrate.budget": _SEARCH_SOURCE_PATHS[4],
    "qmc_bmgs.substrate.countdown_search": _SEARCH_SOURCE_PATHS[5],
    "qmc_bmgs.substrate.perturbations": _SEARCH_SOURCE_PATHS[6],
    "qmc_bmgs.substrate.proposals": _SEARCH_SOURCE_PATHS[7],
    "qmc_bmgs.substrate.trace": _SEARCH_SOURCE_PATHS[8],
    "qmc_bmgs.experiments": _RUNNER_SOURCE_PATHS[0],
    "qmc_bmgs.experiments.countdown_track_a_canary_manifest": (_RUNNER_SOURCE_PATHS[1]),
    "qmc_bmgs.experiments.countdown_thompson_diagnostic_manifest": (
        _RUNNER_SOURCE_PATHS[2]
    ),
    __name__: _RUNNER_SOURCE_PATHS[4],
}

_LOWER_HEX = frozenset("0123456789abcdef")
_ADAPTIVE_METHOD_ORDER = (
    "puct_c1",
    "thompson_candidate_iid_v1",
    "thompson_dimnorm_iid_v2",
    "thompson_dense_iid_v3",
    "thompson_greedy_anchor_dense_iid_v4",
)
_ADAPTIVE_METHODS = frozenset(_ADAPTIVE_METHOD_ORDER)
_STOCHASTIC_METHOD_ORDER = (
    "thompson_candidate_iid_v1",
    "thompson_dimnorm_iid_v2",
    "thompson_dense_iid_v3",
    "thompson_greedy_anchor_dense_iid_v4",
)
_CANDIDATE_METHOD_ORDER = _STOCHASTIC_METHOD_ORDER[1:]
_DIAGNOSTIC_SEEDS = (7168, 7169, 7170, 7171)
_DETERMINISTIC_BASELINES = ("greedy", "beam_width_2", "puct_c1")
_DENSE_METHODS = frozenset(_STOCHASTIC_METHOD_ORDER[2:])
_ACTION_COUNT_BINS = (
    ("3_7", 3, 7),
    ("8_15", 8, 15),
    ("16_31", 16, 31),
    ("32_60", 32, 60),
)
_REQUIRED_ANCESTRY = (
    "0917d1d7e8e637610883c6ab5901a118a59ca264",
    "b7eb154d2f3af9112375835c70212b46a59bdab9",
    "2d4960e6f79a12f27ad8dc370b78e89b98958044",
    "9f0f0c9d07d9e7bf66caff5f664792b2160b4ea4",
    "0826aa3480d05453e6900b96aabea5445fa5fce7",
)


class DiagnosticAnalysisError(ValueError):
    """Raised before any summary exists when a run artifact fails closed."""


class DiagnosticAnalysisPublicationAmbiguousError(DiagnosticAnalysisError):
    """Raised when summary durability or exact rollback cannot be proven."""


class RunnerLabels(TypedDict):
    task_fingerprint: str
    proposal_label: str
    method_label: str
    budget_profile_id: str
    exploration_seed: int


class RunnerReplayReceipt(TypedDict):
    stage1_generative: str
    stage2_byte_identical: str
    replayed_sha256: str


class RunnerBudgetEvidence(TypedDict):
    profile_spec: dict[str, Any]
    usage: dict[str, int]
    remaining: dict[str, int]
    primary_axis: str
    primary_headroom: int
    non_primary_headroom: dict[str, int]
    blocked_axes: list[str]
    budget_valid: bool
    stop_reason: str


class RunnerTelemetry(TypedDict):
    role: str
    search_wall_time_ns: int
    replay_wall_time_ns: int


class ThompsonDiagnosticRunnerRecord(TypedDict):
    """Exact analyzer-facing protocol shared with the manifest runner."""

    schema_version: str
    bundle_id: str
    cell_id: str
    cell_key: dict[str, Any]
    labels: RunnerLabels
    diagnostic_seal_digest: str
    method_manifest_digest: str
    runner_build_digest: str
    search_build_digest: str
    runtime_qualification_digest: str
    search_run_identity_digest: str
    search_trace_sha256: str
    search_trace_byte_count: int
    replay: RunnerReplayReceipt
    provider_calls: int
    budget_evidence: RunnerBudgetEvidence
    telemetry: RunnerTelemetry
    search_summary: dict[str, Any]
    search_record: dict[str, Any]
    deterministic_digest: str


_RUN_MANIFEST_FIELDS = {
    "schema_version",
    "bundle_id",
    "artifact_id",
    "attempt_id",
    "attempt_marker_basename",
    "attempt_phase",
    "attempt_started_receipt",
    "attempt_started_receipt_digest",
    "authorized_output_path",
    "diagnostic_seal_digest",
    "method_manifest_digest",
    "runner_build_attestation",
    "runtime_qualification",
    "execution_authorization",
    "execution_authorization_digest",
    "execution_head_revision",
    "reviewed_authorization_revision",
    "cell_count",
    "schedule_cell_ids",
    "records_jsonl_sha256",
    "records_jsonl_byte_count",
    "record_digests",
    "claim_boundary",
    "telemetry",
    "deterministic_digest",
}
_ATTEMPT_STARTED_RECEIPT_FIELDS = {
    "artifact_id",
    "authorization_digest",
    "authorized_output_path",
    "diagnostic_seal_digest",
    "deterministic_digest",
    "execution_head_revision",
    "phase",
    "reviewed_authorization_revision",
    "runner_build_digest",
    "schema_version",
    "search_build_digest",
    "staging_path",
    "status",
}
_ARTIFACT_COMMIT_FIELDS = {
    "artifact_id",
    "attempt_started_receipt_digest",
    "deterministic_digest",
    "execution_authorization_digest",
    "run_manifest_digest",
    "schema_version",
    "status",
}
_RUN_RECORD_FIELDS = set(ThompsonDiagnosticRunnerRecord.__required_keys__)
_LABEL_FIELDS = set(RunnerLabels.__required_keys__)
_REPLAY_FIELDS = set(RunnerReplayReceipt.__required_keys__)
_BUDGET_EVIDENCE_FIELDS = set(RunnerBudgetEvidence.__required_keys__)
_TELEMETRY_FIELDS = set(RunnerTelemetry.__required_keys__)
_AUTHORIZATION_FIELDS = {
    "artifact_id",
    "authorization_scope",
    "bundle_id",
    "cell_count",
    "claim_boundary",
    "deterministic_digest",
    "diagnostic_seal_digest",
    "method_manifest_digest",
    "output_path",
    "requires_explicit_digest_confirmation",
    "runner_build_attestation",
    "runtime_qualification",
    "runtime_qualification_digest",
    "schedule_digest",
    "schema_version",
}
_TELEMETRY_ROLE = "descriptive_only_excluded_from_search_core_identity_and_gates"
_RUN_CLAIM_BOUNDARY = (
    "engineering diagnostic artifact; byte replay applies only to the embedded "
    "search core, telemetry is volatile, and no inferential, superiority, or "
    "locked-evaluation authority is granted"
)


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return (canonical_json(payload) + "\n").encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _stdlib_canonical_json(payload: Any) -> str:
    """Canonical JSON used before any project replay source is trusted."""

    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def _stdlib_sha256_json(payload: Any) -> str:
    return _sha256_bytes(_stdlib_canonical_json(payload).encode("utf-8"))


def _stdlib_strict_json_object(raw: bytes, label: str) -> dict[str, Any]:
    """Strictly parse one canonical object using only the Python stdlib."""

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant: {value}")

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON object key: {key!r}")
            result[key] = value
        return result

    try:
        parsed = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise DiagnosticAnalysisError(f"{label} is not strict UTF-8 JSON") from error
    if type(parsed) is not dict:
        raise DiagnosticAnalysisError(f"{label} must be a JSON object")
    try:
        canonical = (_stdlib_canonical_json(parsed) + "\n").encode("utf-8")
    except (TypeError, ValueError) as error:
        raise DiagnosticAnalysisError(
            f"{label} is not finite canonical JSON"
        ) from error
    if canonical != raw:
        raise DiagnosticAnalysisError(f"{label} bytes are not canonical")
    return parsed


def _is_sha256(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in _LOWER_HEX for character in value)
    )


def _is_git_oid(value: object) -> bool:
    return (
        type(value) is str
        and len(value) in {40, 64}
        and all(character in _LOWER_HEX for character in value)
    )


def _same_json(left: Any, right: Any) -> bool:
    """Compare strict JSON without Python's bool/int equality alias."""

    try:
        return canonical_json(left) == canonical_json(right)
    except (TraceValidationError, TypeError, ValueError):
        return False


def _require_plain_nonnegative_int(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise DiagnosticAnalysisError(f"{label} must be a non-negative plain integer")
    return value


def _read_fd_bytes(file_descriptor: int) -> bytes:
    chunks: list[bytes] = []
    while True:
        chunk = os.read(file_descriptor, 1024 * 1024)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def _read_regular_file_nofollow(path: Path, label: str) -> bytes:
    """Read stable regular bytes through one O_NOFOLLOW descriptor."""

    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise DiagnosticAnalysisError(f"{label} validation requires POSIX O_NOFOLLOW")
    candidate = Path(path)
    try:
        descriptor = os.open(candidate, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as error:
        raise DiagnosticAnalysisError(f"{label} must be a regular file") from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise DiagnosticAnalysisError(f"{label} must be a regular file")
        first = _read_fd_bytes(descriptor)
        middle = os.fstat(descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
        second = _read_fd_bytes(descriptor)
        after = os.fstat(descriptor)

        def identity(value: os.stat_result) -> tuple[int, int, int, int, int]:
            return (
                value.st_dev,
                value.st_ino,
                value.st_size,
                value.st_mtime_ns,
                value.st_ctime_ns,
            )

        if (
            identity(before) != identity(middle)
            or identity(middle) != identity(after)
            or len(first) != before.st_size
            or second != first
        ):
            raise DiagnosticAnalysisError(f"{label} changed during descriptor read")
        return first
    finally:
        os.close(descriptor)


def _read_artifact_member_preflight(directory: Path, filename: str) -> bytes:
    """Read one authority member before outcome-bearing records are opened."""

    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise DiagnosticAnalysisError(
            "runner artifact preflight requires POSIX O_NOFOLLOW"
        )
    root = Path(directory)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW
    try:
        directory_fd = os.open(root, flags)
    except OSError as error:
        raise DiagnosticAnalysisError(
            "runner artifact path must be a regular directory"
        ) from error
    try:
        if not stat.S_ISDIR(os.fstat(directory_fd).st_mode):
            raise DiagnosticAnalysisError(
                "runner artifact path must be a regular directory"
            )
        try:
            member_fd = os.open(
                filename,
                os.O_RDONLY | os.O_NOFOLLOW,
                dir_fd=directory_fd,
            )
        except OSError as error:
            raise DiagnosticAnalysisError(
                f"runner artifact authority member is unavailable: {filename}"
            ) from error
        try:
            if not stat.S_ISREG(os.fstat(member_fd).st_mode):
                raise DiagnosticAnalysisError(
                    f"runner artifact authority member is not regular: {filename}"
                )
            return _read_fd_bytes(member_fd)
        finally:
            os.close(member_fd)
    finally:
        os.close(directory_fd)


def _read_artifact_snapshot(directory: Path) -> dict[str, bytes]:
    """Take one descriptor-bound closed artifact snapshot on POSIX hosts."""

    root = Path(directory)
    if os.name == "posix":
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            directory_fd = os.open(root, flags)
        except OSError as error:
            raise DiagnosticAnalysisError(
                "runner artifact path must be a regular directory"
            ) from error
        try:
            names = os.listdir(directory_fd)
            if len(names) != len(set(names)) or set(names) != set(
                RUN_ARTIFACT_FILENAMES
            ):
                raise DiagnosticAnalysisError(
                    "runner artifact directory closure drifted"
                )
            snapshot: dict[str, bytes] = {}
            for filename in RUN_ARTIFACT_FILENAMES:
                file_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                try:
                    file_fd = os.open(filename, file_flags, dir_fd=directory_fd)
                except OSError as error:
                    raise DiagnosticAnalysisError(
                        f"runner artifact member is unavailable: {filename}"
                    ) from error
                try:
                    if not stat.S_ISREG(os.fstat(file_fd).st_mode):
                        raise DiagnosticAnalysisError(
                            f"runner artifact member is not regular: {filename}"
                        )
                    snapshot[filename] = _read_fd_bytes(file_fd)
                finally:
                    os.close(file_fd)
            return snapshot
        finally:
            os.close(directory_fd)

    if root.is_symlink() or not root.is_dir():
        raise DiagnosticAnalysisError(
            "runner artifact path must be a regular directory"
        )
    paths = list(root.iterdir())
    if {path.name for path in paths} != set(RUN_ARTIFACT_FILENAMES):
        raise DiagnosticAnalysisError("runner artifact directory closure drifted")
    snapshot = {}
    for filename in RUN_ARTIFACT_FILENAMES:
        path = root / filename
        if path.is_symlink() or not path.is_file():
            raise DiagnosticAnalysisError(
                f"runner artifact member is not regular: {filename}"
            )
        snapshot[filename] = path.read_bytes()
    return snapshot


def _strict_json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8")
        parsed = strict_json_loads(text)
    except (UnicodeDecodeError, TraceValidationError) as error:
        raise DiagnosticAnalysisError(f"{label} is not strict UTF-8 JSON") from error
    if type(parsed) is not dict:
        raise DiagnosticAnalysisError(f"{label} must be a JSON object")
    if _canonical_bytes(parsed) != raw:
        raise DiagnosticAnalysisError(f"{label} bytes are not canonical")
    return parsed


def _reviewed_authorization(
    path: Path,
    supplied_digest: str,
) -> tuple[dict[str, Any], bytes]:
    raw = _read_regular_file_nofollow(
        Path(path),
        "reviewed authorization path",
    )
    payload = _strict_json_object(raw, "reviewed authorization")
    if not _is_sha256(supplied_digest):
        raise DiagnosticAnalysisError(
            "reviewed authorization digest must be lowercase SHA-256"
        )
    if payload.get("deterministic_digest") != supplied_digest:
        raise DiagnosticAnalysisError("reviewed authorization digest does not match")
    return payload, raw


def _preflight_authorization(
    authorization: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any],
    attestation: Mapping[str, Any],
) -> None:
    """Close reviewed execution authority before opening outcome records."""

    if type(authorization) is not dict or set(authorization) != _AUTHORIZATION_FIELDS:
        raise DiagnosticAnalysisError("execution authorization fields drifted")
    core = {
        key: value
        for key, value in authorization.items()
        if key != "deterministic_digest"
    }
    runtime = authorization["runtime_qualification"]
    output = authorization["output_path"]
    if (
        authorization["schema_version"]
        != "qmc-bmgs-countdown-thompson-diagnostic-execution-authorization/v1"
        or authorization["authorization_scope"]
        != "one_exact_complete_240_cell_diagnostic_run"
        or authorization["claim_boundary"]
        != (
            "execution authority only; this engineering diagnostic grants no "
            "method-superiority or locked-128 execution authority"
        )
        or authorization["deterministic_digest"] != _stdlib_sha256_json(core)
        or authorization["deterministic_digest"]
        != manifest.get("execution_authorization_digest")
        or authorization["bundle_id"] != BUNDLE_ID
        or authorization["bundle_id"] != manifest.get("bundle_id")
        or type(authorization["cell_count"]) is not int
        or authorization["cell_count"] != EXPECTED_CELL_COUNT
        or authorization["requires_explicit_digest_confirmation"] is not True
        or not _same_json(authorization["runner_build_attestation"], attestation)
        or type(runtime) is not dict
        or authorization["runtime_qualification_digest"] != _stdlib_sha256_json(runtime)
        or not _same_json(runtime, manifest.get("runtime_qualification"))
        or authorization["diagnostic_seal_digest"]
        != manifest.get("diagnostic_seal_digest")
        or authorization["method_manifest_digest"]
        != manifest.get("method_manifest_digest")
        or authorization["artifact_id"] != manifest.get("artifact_id")
        or output != manifest.get("authorized_output_path")
        or type(output) is not str
        or not Path(output).is_absolute()
        or Path(output).name != authorization["artifact_id"]
        or not _is_sha256(authorization["diagnostic_seal_digest"])
        or not _is_sha256(authorization["method_manifest_digest"])
        or not _is_sha256(authorization["runtime_qualification_digest"])
        or not _is_sha256(authorization["schedule_digest"])
    ):
        raise DiagnosticAnalysisError("execution authorization preflight drifted")


def _preflight_verified_bundle_authority(
    authorization: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any],
    bundle: VerifiedDiagnosticBundle,
    expected_cells: Sequence[DiagnosticCell],
) -> None:
    """Bind reviewed authority to the verified bundle before records are read."""

    payloads = bundle.payloads
    qualification = manifest.get("runtime_qualification")
    qualification_fields = {
        "bundle_id",
        "execution_authorized",
        "runtime_bindings_digest",
        "status",
    }
    method_digest = payloads["methods.json"]["deterministic_digest"]
    runtime_digest = sha256_json(payloads["methods.json"]["runtime_bindings"])
    matrix = payloads["preregistration.json"]["execution_matrix"]
    expected_ids = [cell.cell_id for cell in expected_cells]
    if (
        len(expected_cells) != EXPECTED_CELL_COUNT
        or len(set(expected_ids)) != EXPECTED_CELL_COUNT
        or type(qualification) is not dict
        or set(qualification) != qualification_fields
        or qualification["bundle_id"] != BUNDLE_ID
        or qualification["execution_authorized"] is not False
        or qualification["runtime_bindings_digest"] != runtime_digest
        or qualification["status"] != "RUNTIME_QUALIFIED"
        or authorization["runtime_qualification_digest"] != sha256_json(qualification)
        or not _same_json(authorization["runtime_qualification"], qualification)
        or bundle.seal_digest != manifest.get("diagnostic_seal_digest")
        or bundle.seal_digest != authorization["diagnostic_seal_digest"]
        or method_digest != manifest.get("method_manifest_digest")
        or method_digest != authorization["method_manifest_digest"]
        or matrix["schedule_digest"] != authorization["schedule_digest"]
        or type(manifest.get("cell_count")) is not int
        or manifest["cell_count"] != EXPECTED_CELL_COUNT
        or not _same_json(manifest.get("schedule_cell_ids"), expected_ids)
    ):
        raise DiagnosticAnalysisError("verified bundle authority preflight drifted")


def _strict_jsonl(raw: bytes) -> tuple[dict[str, Any], ...]:
    if not raw or not raw.endswith(b"\n"):
        raise DiagnosticAnalysisError("records.jsonl must be non-empty canonical JSONL")
    records: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(raw.splitlines(keepends=True), start=1):
        try:
            text = raw_line.decode("utf-8")
            parsed = strict_json_loads(text)
        except (UnicodeDecodeError, TraceValidationError) as error:
            raise DiagnosticAnalysisError(
                f"records.jsonl line {line_number} is not strict JSON"
            ) from error
        if type(parsed) is not dict or _canonical_bytes(parsed) != raw_line:
            raise DiagnosticAnalysisError(
                f"records.jsonl line {line_number} is not a canonical object"
            )
        records.append(parsed)
    return tuple(records)


def _validate_digest_field(payload: Mapping[str, Any], field: str) -> None:
    if not _is_sha256(payload.get(field)):
        raise DiagnosticAnalysisError(f"{field} must be lowercase SHA-256")


def _validate_git_oid_field(payload: Mapping[str, Any], field: str) -> None:
    if not _is_git_oid(payload.get(field)):
        raise DiagnosticAnalysisError(f"{field} must be a lowercase Git object id")


def _validate_receipt_map(
    receipts: object,
    *,
    expected_paths: Sequence[str],
    label: str,
) -> dict[str, dict[str, Any]]:
    if type(receipts) is not dict or set(receipts) != set(expected_paths):
        raise DiagnosticAnalysisError(f"{label} protected path set drifted")
    for relative_path in expected_paths:
        receipt = receipts[relative_path]
        if (
            type(receipt) is not dict
            or set(receipt) != {"byte_count", "sha256"}
            or type(receipt["byte_count"]) is not int
            or receipt["byte_count"] < 0
            or not _is_sha256(receipt["sha256"])
        ):
            raise DiagnosticAnalysisError(f"{label} source receipt is invalid")
    return receipts


def _validate_build_attestation_structure(
    attestation: object,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], str, str]:
    expected_fields = {
        "authorized_runner_revision",
        "host_build",
        "numeric_microfixture",
        "required_ancestry",
        "runner_build_digest",
        "runner_source_files",
        "schema_version",
        "search_build_digest",
        "search_microfixture",
        "search_source_files",
    }
    if type(attestation) is not dict or set(attestation) != expected_fields:
        raise DiagnosticAnalysisError("runner build attestation fields drifted")
    if attestation["schema_version"] != (
        "qmc-bmgs-countdown-thompson-diagnostic-build-attestation/v1"
    ):
        raise DiagnosticAnalysisError("runner build attestation schema drifted")
    _validate_git_oid_field(attestation, "authorized_runner_revision")
    ancestry = attestation["required_ancestry"]
    if (
        type(ancestry) is not list
        or ancestry != list(_REQUIRED_ANCESTRY)
        or any(not _is_git_oid(revision) for revision in ancestry)
    ):
        raise DiagnosticAnalysisError("runner required ancestry drifted")
    search_receipts = _validate_receipt_map(
        attestation["search_source_files"],
        expected_paths=_SEARCH_SOURCE_PATHS,
        label="search",
    )
    runner_receipts = _validate_receipt_map(
        attestation["runner_source_files"],
        expected_paths=_RUNNER_SOURCE_PATHS,
        label="runner",
    )
    runner_build_digest = attestation["runner_build_digest"]
    search_build_digest = attestation["search_build_digest"]
    if not _is_sha256(runner_build_digest) or not _is_sha256(search_build_digest):
        raise DiagnosticAnalysisError("runner/search build attestation is invalid")
    search_core = {
        "host_build": attestation["host_build"],
        "numeric_microfixture": attestation["numeric_microfixture"],
        "search_microfixture": attestation["search_microfixture"],
        "source_files": search_receipts,
    }
    runner_core = {
        "runner_source_files": runner_receipts,
        "search_build_digest": search_build_digest,
    }
    if search_build_digest != _stdlib_sha256_json(
        search_core
    ) or runner_build_digest != _stdlib_sha256_json(runner_core):
        raise DiagnosticAnalysisError("runner/search build attestation digest mismatch")
    return (
        search_receipts,
        runner_receipts,
        runner_build_digest,
        search_build_digest,
    )


def _validate_attempt_evidence(
    payload: Mapping[str, Any],
    *,
    runner_build_digest: str,
    search_build_digest: str,
) -> None:
    receipt = payload.get("attempt_started_receipt")
    if type(receipt) is not dict or set(receipt) != _ATTEMPT_STARTED_RECEIPT_FIELDS:
        raise DiagnosticAnalysisError("attempt STARTED receipt fields drifted")
    receipt_core = {
        key: value for key, value in receipt.items() if key != "deterministic_digest"
    }
    if (
        not _is_sha256(payload.get("attempt_started_receipt_digest"))
        or receipt["deterministic_digest"] != _stdlib_sha256_json(receipt_core)
        or payload["attempt_started_receipt_digest"] != receipt["deterministic_digest"]
    ):
        raise DiagnosticAnalysisError("attempt STARTED receipt digest does not close")
    authorization_digest = payload.get("execution_authorization_digest")
    artifact_id = payload.get("artifact_id")
    authorized_output = payload.get("authorized_output_path")
    if (
        not _is_sha256(authorization_digest)
        or type(artifact_id) is not str
        or not artifact_id
        or type(authorized_output) is not str
        or not Path(authorized_output).is_absolute()
    ):
        raise DiagnosticAnalysisError(
            "attempt output/authorization identity is invalid"
        )
    expected_marker = f".{artifact_id}.attempt-{authorization_digest}"
    expected_staging = str(Path(authorized_output).parent / expected_marker / "staging")
    if (
        payload.get("attempt_id") != authorization_digest
        or payload.get("attempt_marker_basename") != expected_marker
        or payload.get("attempt_phase") != "READY_TO_COMMIT"
        or receipt["schema_version"]
        != "qmc-bmgs-countdown-thompson-diagnostic-attempt-marker/v1"
        or receipt["phase"] != "STARTED"
        or receipt["status"] != "PENDING"
        or receipt["artifact_id"] != artifact_id
        or receipt["authorization_digest"] != authorization_digest
        or receipt["authorized_output_path"] != authorized_output
        or receipt["diagnostic_seal_digest"] != payload.get("diagnostic_seal_digest")
        or receipt["execution_head_revision"] != payload.get("execution_head_revision")
        or receipt["reviewed_authorization_revision"]
        != payload.get("reviewed_authorization_revision")
        or receipt["runner_build_digest"] != runner_build_digest
        or receipt["search_build_digest"] != search_build_digest
        or receipt["staging_path"] != expected_staging
    ):
        raise DiagnosticAnalysisError("attempt STARTED receipt binding drifted")


def _validate_artifact_commit(
    payload: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> None:
    if type(payload) is not dict or set(payload) != _ARTIFACT_COMMIT_FIELDS:
        raise DiagnosticAnalysisError("artifact commit receipt fields drifted")
    core = {
        key: value for key, value in payload.items() if key != "deterministic_digest"
    }
    if (
        payload.get("schema_version") != ARTIFACT_COMMIT_SCHEMA_VERSION
        or payload.get("status") != "COMMITTED"
        or payload.get("deterministic_digest") != _stdlib_sha256_json(core)
        or payload.get("artifact_id") != manifest.get("artifact_id")
        or payload.get("attempt_started_receipt_digest")
        != manifest.get("attempt_started_receipt_digest")
        or payload.get("execution_authorization_digest")
        != manifest.get("execution_authorization_digest")
        or payload.get("run_manifest_digest") != manifest.get("deterministic_digest")
    ):
        raise DiagnosticAnalysisError("artifact commit receipt does not close")


def _preflight_run_manifest(
    payload: dict[str, Any],
) -> tuple[Mapping[str, Any], str, str]:
    """Validate authority-bearing manifest structure before project replay use."""

    if set(payload) != _RUN_MANIFEST_FIELDS:
        raise DiagnosticAnalysisError("runner manifest fields drifted")
    if payload.get("schema_version") != RUN_MANIFEST_SCHEMA_VERSION:
        raise DiagnosticAnalysisError("runner manifest schema drifted")
    core = {
        key: value for key, value in payload.items() if key != "deterministic_digest"
    }
    if payload.get("deterministic_digest") != _stdlib_sha256_json(core):
        raise DiagnosticAnalysisError("runner manifest deterministic digest mismatch")
    if payload.get("claim_boundary") != _RUN_CLAIM_BOUNDARY:
        raise DiagnosticAnalysisError("runner manifest claim boundary drifted")
    _require_plain_nonnegative_int(payload.get("cell_count"), "runner cell_count")
    _require_plain_nonnegative_int(
        payload.get("records_jsonl_byte_count"),
        "runner records_jsonl_byte_count",
    )
    _validate_digest_field(payload, "execution_authorization_digest")
    _validate_git_oid_field(payload, "execution_head_revision")
    _validate_git_oid_field(payload, "reviewed_authorization_revision")
    attestation = payload.get("runner_build_attestation")
    (
        _search_receipts,
        _runner_receipts,
        runner_build_digest,
        search_build_digest,
    ) = _validate_build_attestation_structure(attestation)
    _validate_attempt_evidence(
        payload,
        runner_build_digest=runner_build_digest,
        search_build_digest=search_build_digest,
    )
    return (
        attestation,
        payload["execution_head_revision"],
        payload["reviewed_authorization_revision"],
    )


def _git_result(
    repository_root: Path, *arguments: str
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *arguments],
        cwd=repository_root,
        check=False,
        capture_output=True,
    )


def _require_clean_git_checkout(repository_root: Path) -> None:
    result = _git_result(
        repository_root,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    if result.returncode != 0:
        raise DiagnosticAnalysisError("repository checkout status is unreadable")
    if result.stdout != b"":
        raise DiagnosticAnalysisError(
            "repository checkout must be clean before diagnostic analysis"
        )


def _require_git_commit_object(
    repository_root: Path,
    revision: str,
    label: str,
) -> None:
    result = _git_result(repository_root, "cat-file", "-t", revision)
    if result.returncode != 0 or result.stdout != b"commit\n":
        raise DiagnosticAnalysisError(f"{label} must name an exact Git commit object")


def _require_regular_git_tree_entry(
    repository_root: Path,
    revision: str,
    relative_path: str,
) -> None:
    result = _git_result(
        repository_root,
        "ls-tree",
        "-z",
        revision,
        "--",
        relative_path,
    )
    entries = result.stdout.split(b"\0")
    if (
        result.returncode != 0
        or len(entries) != 2
        or entries[1] != b""
        or b"\t" not in entries[0]
    ):
        raise DiagnosticAnalysisError("authorization Git tree entry is not unique")
    metadata, observed_path = entries[0].split(b"\t", maxsplit=1)
    fields = metadata.split()
    if (
        observed_path != relative_path.encode("utf-8")
        or len(fields) != 3
        or fields[0] != b"100644"
        or fields[1] != b"blob"
    ):
        raise DiagnosticAnalysisError(
            "authorization Git tree entry must be one non-executable regular blob"
        )


def _validate_git_provenance(
    repository_root: Path,
    *,
    attestation: Mapping[str, Any],
    execution_head_revision: str,
) -> None:
    (
        search_receipts,
        runner_receipts,
        _runner_build_digest,
        _search_build_digest,
    ) = _validate_build_attestation_structure(attestation)
    root = Path(repository_root).resolve()
    top_level = _git_result(root, "rev-parse", "--show-toplevel")
    if top_level.returncode != 0:
        raise DiagnosticAnalysisError("repository root is not a readable Git checkout")
    try:
        observed_root = Path(top_level.stdout.decode("utf-8").strip()).resolve()
    except UnicodeDecodeError as error:
        raise DiagnosticAnalysisError("Git top-level path is not UTF-8") from error
    if observed_root != root:
        raise DiagnosticAnalysisError("repository root does not match Git top level")
    _require_clean_git_checkout(root)

    authorized = attestation["authorized_runner_revision"]
    ancestors = [authorized, *attestation["required_ancestry"]]
    for revision in [execution_head_revision, *ancestors]:
        exists = _git_result(root, "cat-file", "-e", f"{revision}^{{commit}}")
        if exists.returncode != 0:
            raise DiagnosticAnalysisError(
                "attested execution revision is unavailable in repository history"
            )
    for ancestor in ancestors:
        relation = _git_result(
            root,
            "merge-base",
            "--is-ancestor",
            ancestor,
            execution_head_revision,
        )
        if relation.returncode != 0:
            raise DiagnosticAnalysisError(
                "execution head does not descend from reviewed ancestry"
            )

    for relative_path, receipt in {**search_receipts, **runner_receipts}.items():
        blob = _git_result(
            root,
            "show",
            f"{execution_head_revision}:{relative_path}",
        )
        if (
            blob.returncode != 0
            or len(blob.stdout) != receipt["byte_count"]
            or _sha256_bytes(blob.stdout) != receipt["sha256"]
        ):
            raise DiagnosticAnalysisError(
                "attested source receipt does not match execution-head bytes"
            )


def _validate_current_replay_surface(
    repository_root: Path,
    *,
    attestation: Mapping[str, Any],
    execution_head_revision: str,
) -> str:
    """Bind loaded import origins and current replay files to attested Git blobs.

    The historical runner file remains an exact attested/Git receipt, but it is
    intentionally not imported by this analyzer and is not part of its current
    replay execution surface.
    """

    _validate_git_provenance(
        repository_root,
        attestation=attestation,
        execution_head_revision=execution_head_revision,
    )
    root = Path(repository_root).resolve()
    search_receipts = attestation["search_source_files"]
    runner_receipts = attestation["runner_source_files"]
    analyzer_bytes: bytes | None = None
    analyzer_receipt: Mapping[str, Any] | None = None
    for module_name, relative in _CURRENT_REPLAY_MODULE_PATHS.items():
        loaded = sys.modules.get(module_name)
        loaded_path = getattr(loaded, "__file__", None)
        expected_path = root / relative
        if (
            type(loaded_path) is not str
            or Path(loaded_path).resolve() != expected_path.resolve()
        ):
            raise DiagnosticAnalysisError(
                f"current replay import origin drifted: {module_name}"
            )
        current_bytes = _read_regular_file_nofollow(
            expected_path,
            f"current replay source {relative}",
        )
        receipt = (
            search_receipts[relative]
            if relative in search_receipts
            else runner_receipts[relative]
        )
        blob = _git_result(
            root,
            "show",
            f"{execution_head_revision}:{relative}",
        )
        if (
            len(current_bytes) != receipt["byte_count"]
            or _sha256_bytes(current_bytes) != receipt["sha256"]
            or blob.returncode != 0
            or blob.stdout != current_bytes
        ):
            raise DiagnosticAnalysisError(
                "current replay source, attested receipt, and execution-head "
                f"blob differ: {relative}"
            )
        if relative == ANALYZER_RELATIVE_PATH.as_posix():
            analyzer_bytes = current_bytes
            analyzer_receipt = receipt
    if analyzer_bytes is None or analyzer_receipt is None:
        raise DiagnosticAnalysisError("current analyzer was absent from replay surface")
    build = {
        "byte_count": len(analyzer_bytes),
        "execution_head_revision": execution_head_revision,
        "relative_path": ANALYZER_RELATIVE_PATH.as_posix(),
        "schema_version": ANALYZER_BUILD_SCHEMA_VERSION,
        "sha256": analyzer_receipt["sha256"],
    }
    return _stdlib_sha256_json(build)


def _authorization_repository_location(
    authorization_path: Path,
    repository_root: Path,
) -> tuple[Path, str]:
    root = Path(repository_root).resolve()
    candidate = Path(authorization_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    absolute = Path(os.path.abspath(candidate))
    if absolute == root or not absolute.is_relative_to(root):
        raise DiagnosticAnalysisError(
            "reviewed authorization must be a repository-relative file"
        )
    if absolute.resolve() != absolute:
        raise DiagnosticAnalysisError(
            "reviewed authorization path must not traverse symlinks"
        )
    relative = absolute.relative_to(root).as_posix()
    if relative == "." or ".." in Path(relative).parts:
        raise DiagnosticAnalysisError(
            "reviewed authorization repository path is invalid"
        )
    return absolute, relative


def _validate_reviewed_authorization_provenance(
    repository_root: Path,
    *,
    authorization_path: Path,
    authorization_raw: bytes,
    manifest: Mapping[str, Any],
) -> None:
    """Bind reviewed authority bytes to one tracked blob and revision interval."""

    root = Path(repository_root).resolve()
    absolute, relative = _authorization_repository_location(
        authorization_path,
        root,
    )
    if absolute != Path(os.path.abspath(authorization_path)):
        raise DiagnosticAnalysisError("reviewed authorization path resolution drifted")
    embedded = manifest.get("execution_authorization")
    if (
        type(embedded) is not dict
        or (_stdlib_canonical_json(embedded) + "\n").encode("utf-8")
        != authorization_raw
    ):
        raise DiagnosticAnalysisError(
            "embedded authorization differs from reviewed authorization bytes"
        )
    attestation = manifest["runner_build_attestation"]
    authorized = attestation["authorized_runner_revision"]
    reviewed = manifest["reviewed_authorization_revision"]
    execution_head = manifest["execution_head_revision"]
    for revision, label in (
        (authorized, "authorized runner revision"),
        (reviewed, "reviewed authorization revision"),
        (execution_head, "execution HEAD"),
    ):
        _require_git_commit_object(root, revision, label)
    if reviewed == authorized:
        raise DiagnosticAnalysisError(
            "reviewed authorization revision must strictly descend from "
            "authorized runner revision"
        )
    for ancestor, descendant in (
        (authorized, reviewed),
        (reviewed, execution_head),
    ):
        relation = _git_result(
            root,
            "merge-base",
            "--is-ancestor",
            ancestor,
            descendant,
        )
        if relation.returncode != 0:
            raise DiagnosticAnalysisError(
                "reviewed authorization revision lineage is invalid"
            )
    tracked = _git_result(
        root,
        "ls-files",
        "--error-unmatch",
        "--",
        relative,
    )
    if tracked.returncode != 0 or tracked.stdout != f"{relative}\n".encode("utf-8"):
        raise DiagnosticAnalysisError(
            "reviewed authorization is not one exact tracked file"
        )
    for revision in (reviewed, execution_head):
        _require_regular_git_tree_entry(root, revision, relative)
        blob = _git_result(root, "show", f"{revision}:{relative}")
        if blob.returncode != 0 or blob.stdout != authorization_raw:
            raise DiagnosticAnalysisError(
                "reviewed authorization bytes differ from reviewed/HEAD Git blob"
            )


def _validate_run_manifest(
    payload: dict[str, Any],
    *,
    records_raw: bytes,
    expected_cells: Sequence[DiagnosticCell],
    bundle: VerifiedDiagnosticBundle,
    reviewed_authorization: Mapping[str, Any],
    reviewed_authorization_raw: bytes,
    analyzer_build_digest: str,
) -> tuple[str, str, str, str]:
    if set(payload) != _RUN_MANIFEST_FIELDS:
        raise DiagnosticAnalysisError("runner manifest fields drifted")
    if payload["schema_version"] != RUN_MANIFEST_SCHEMA_VERSION:
        raise DiagnosticAnalysisError("runner manifest schema drifted")
    bundle_payloads = bundle.payloads
    bundle_id = bundle_payloads["preregistration.json"]["bundle_id"]
    if payload["bundle_id"] != bundle_id:
        raise DiagnosticAnalysisError("runner manifest bundle id drifted")
    core = {
        key: value for key, value in payload.items() if key != "deterministic_digest"
    }
    if payload["deterministic_digest"] != sha256_json(core):
        raise DiagnosticAnalysisError("runner manifest deterministic digest mismatch")

    method_manifest_digest = bundle_payloads["methods.json"]["deterministic_digest"]
    if payload["diagnostic_seal_digest"] != bundle.seal_digest:
        raise DiagnosticAnalysisError("runner manifest seal binding drifted")
    if payload["method_manifest_digest"] != method_manifest_digest:
        raise DiagnosticAnalysisError("runner manifest method binding drifted")
    if (
        type(payload["cell_count"]) is not int
        or payload["cell_count"] != EXPECTED_CELL_COUNT
        or payload["cell_count"] != len(expected_cells)
    ):
        raise DiagnosticAnalysisError("runner manifest cell count drifted")
    expected_ids = [cell.cell_id for cell in expected_cells]
    if not _same_json(payload["schedule_cell_ids"], expected_ids):
        raise DiagnosticAnalysisError("runner manifest schedule identity/order drifted")
    if payload["records_jsonl_sha256"] != _sha256_bytes(records_raw):
        raise DiagnosticAnalysisError("records.jsonl SHA-256 mismatch")
    if type(payload["records_jsonl_byte_count"]) is not int or payload[
        "records_jsonl_byte_count"
    ] != len(records_raw):
        raise DiagnosticAnalysisError("records.jsonl byte count mismatch")
    if type(payload["claim_boundary"]) is not str or not payload["claim_boundary"]:
        raise DiagnosticAnalysisError("runner manifest claim boundary is invalid")
    if payload["claim_boundary"] != _RUN_CLAIM_BOUNDARY:
        raise DiagnosticAnalysisError("runner manifest claim boundary drifted")
    manifest_telemetry = payload["telemetry"]
    if (
        type(manifest_telemetry) is not dict
        or set(manifest_telemetry)
        != {
            "role",
            "search_wall_time_ns_total",
            "replay_wall_time_ns_total",
        }
        or manifest_telemetry["role"] != _TELEMETRY_ROLE
    ):
        raise DiagnosticAnalysisError("runner manifest telemetry fields drifted")
    for field in ("search_wall_time_ns_total", "replay_wall_time_ns_total"):
        _require_plain_nonnegative_int(
            manifest_telemetry[field],
            f"runner manifest telemetry.{field}",
        )
    _validate_digest_field(payload, "execution_authorization_digest")
    _validate_git_oid_field(payload, "execution_head_revision")
    _validate_git_oid_field(payload, "reviewed_authorization_revision")

    attestation = payload["runner_build_attestation"]
    (
        _search_receipts,
        _runner_receipts,
        runner_build_digest,
        search_build_digest,
    ) = _validate_build_attestation_structure(attestation)
    _validate_attempt_evidence(
        payload,
        runner_build_digest=runner_build_digest,
        search_build_digest=search_build_digest,
    )
    if not _is_sha256(analyzer_build_digest):
        raise DiagnosticAnalysisError("analyzer build digest is invalid")

    qualification = payload["runtime_qualification"]
    expected_qualification_fields = {
        "bundle_id",
        "execution_authorized",
        "runtime_bindings_digest",
        "status",
    }
    if type(qualification) is not dict or set(qualification) != (
        expected_qualification_fields
    ):
        raise DiagnosticAnalysisError("runtime qualification fields drifted")
    expected_runtime_bindings_digest = sha256_json(
        bundle_payloads["methods.json"]["runtime_bindings"]
    )
    if (
        qualification["bundle_id"] != bundle_id
        or qualification["execution_authorized"] is not False
        or qualification["runtime_bindings_digest"] != expected_runtime_bindings_digest
        or qualification["status"] != "RUNTIME_QUALIFIED"
    ):
        raise DiagnosticAnalysisError("runtime qualification does not match the bundle")
    runtime_qualification_digest = sha256_json(qualification)

    authorization = payload["execution_authorization"]
    if type(authorization) is not dict or set(authorization) != _AUTHORIZATION_FIELDS:
        raise DiagnosticAnalysisError("execution authorization fields drifted")
    if (
        not _same_json(authorization, reviewed_authorization)
        or _canonical_bytes(authorization) != reviewed_authorization_raw
    ):
        raise DiagnosticAnalysisError(
            "embedded authorization differs from reviewed authorization bytes"
        )
    authorization_core = {
        key: value
        for key, value in authorization.items()
        if key != "deterministic_digest"
    }
    if (
        authorization["deterministic_digest"] != sha256_json(authorization_core)
        or authorization["deterministic_digest"]
        != payload["execution_authorization_digest"]
        or authorization["schema_version"]
        != "qmc-bmgs-countdown-thompson-diagnostic-execution-authorization/v1"
        or authorization["authorization_scope"]
        != "one_exact_complete_240_cell_diagnostic_run"
        or authorization["claim_boundary"]
        != (
            "execution authority only; this engineering diagnostic grants no "
            "method-superiority or locked-128 execution authority"
        )
        or authorization["bundle_id"] != bundle_id
        or authorization["diagnostic_seal_digest"] != bundle.seal_digest
        or type(authorization["cell_count"]) is not int
        or authorization["cell_count"] != EXPECTED_CELL_COUNT
        or authorization["method_manifest_digest"] != method_manifest_digest
        or authorization["requires_explicit_digest_confirmation"] is not True
        or authorization["runtime_qualification_digest"] != runtime_qualification_digest
        or not _same_json(authorization["runtime_qualification"], qualification)
        or not _same_json(authorization["runner_build_attestation"], attestation)
        or authorization["schedule_digest"]
        != bundle_payloads["preregistration.json"]["execution_matrix"][
            "schedule_digest"
        ]
        or authorization["artifact_id"] != payload["artifact_id"]
        or authorization["output_path"] != payload["authorized_output_path"]
    ):
        raise DiagnosticAnalysisError("execution authorization does not close")
    authorized_output = authorization["output_path"]
    if (
        type(authorized_output) is not str
        or not Path(authorized_output).is_absolute()
        or type(payload["artifact_id"]) is not str
        or not payload["artifact_id"]
        or Path(authorized_output).name != payload["artifact_id"]
    ):
        raise DiagnosticAnalysisError("authorized output provenance is invalid")
    return (
        runner_build_digest,
        search_build_digest,
        runtime_qualification_digest,
        analyzer_build_digest,
    )


@dataclass(frozen=True)
class _ReplayInputs:
    tasks: dict[str, CountdownTask]
    proposals: dict[str, TrackAProposalSpec]
    methods: dict[str, TrackAMethodSpec]
    budgets: dict[str, TrackABudgetProfile]


def _typed_replay_inputs(bundle: VerifiedDiagnosticBundle) -> _ReplayInputs:
    payloads = bundle.payloads
    tasks: dict[str, CountdownTask] = {}
    for row in payloads["diagnostic_tasks.json"]["tasks"]:
        task = CountdownTask(tuple(row["inputs"]), row["target"])
        if not _same_json(task.to_dict(), row):
            raise DiagnosticAnalysisError("verified task row did not rehydrate exactly")
        tasks[task.task_fingerprint] = task

    proposals: dict[str, TrackAProposalSpec] = {}
    for row in payloads["proposals.json"]["policies"]:
        proposal = TrackAProposalSpec(row["spec"]["policy_id"])
        if not _same_json(proposal.to_dict(), row["spec"]):
            raise DiagnosticAnalysisError("verified proposal did not rehydrate exactly")
        proposals[row["label"]] = proposal

    methods: dict[str, TrackAMethodSpec] = {}
    for row in payloads["methods.json"]["methods"]:
        spec = row["spec"]
        method = TrackAMethodSpec(
            method=spec["method"],
            selected_source=spec["selected_source"],
            c_puct=spec["c_puct"],
            prior_bonus=spec["prior_bonus"],
            posterior_sd_scale=spec["posterior_sd_scale"],
            beam_width=spec["beam_width"],
            selection_rule_id=spec.get("selection_rule_id"),
            terminal_value_rule_id=spec.get("terminal_value_rule_id"),
            greedy_anchor_trajectory_count=spec.get("greedy_anchor_trajectory_count"),
            schema_version=spec["schema_version"],
        )
        if not _same_json(method.to_dict(), spec):
            raise DiagnosticAnalysisError("verified method did not rehydrate exactly")
        methods[row["label"]] = method

    budgets: dict[str, TrackABudgetProfile] = {}
    for row in payloads["budgets.json"]["profiles"]:
        spec = row["spec"]
        budget = TrackAWorkBudget(**spec["budget"])
        profile = TrackABudgetProfile(
            profile_id=spec["profile_id"],
            primary_axis=spec["primary_axis"],
            budget=budget,
            schema_version=spec["schema_version"],
        )
        if not _same_json(profile.to_dict(), spec):
            raise DiagnosticAnalysisError("verified budget did not rehydrate exactly")
        budgets[profile.profile_id] = profile
    return _ReplayInputs(tasks, proposals, methods, budgets)


def _search_summary(search_record: Mapping[str, Any]) -> dict[str, Any]:
    events = search_record.get("events")
    if type(events) is not list or not events:
        raise DiagnosticAnalysisError("search record has no final event")
    final = events[-1]
    if type(final) is not dict or final.get("kind") != "search_finished":
        raise DiagnosticAnalysisError("search record does not end with search_finished")
    payload = final.get("payload")
    if type(payload) is not dict or type(payload.get("summary")) is not dict:
        raise DiagnosticAnalysisError("search_finished summary is invalid")
    return payload["summary"]


def _expected_budget_evidence(
    *,
    profile: TrackABudgetProfile,
    search_record: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    ledger = search_record["ledger_snapshot"]
    remaining = ledger["remaining"]
    return {
        "profile_spec": profile.to_dict(),
        "usage": ledger["usage"],
        "remaining": remaining,
        "primary_axis": profile.primary_axis,
        "primary_headroom": remaining[profile.primary_axis],
        "non_primary_headroom": {
            axis: remaining[axis]
            for axis in TRACK_A_WORK_AXES
            if axis != profile.primary_axis
        },
        "blocked_axes": summary["stop_blocked_axes"],
        "budget_valid": summary["budget_valid"],
        "stop_reason": summary["stop_reason"],
    }


def _validate_profile_and_accounting(
    *,
    cell: DiagnosticCell,
    method: TrackAMethodSpec,
    profile: TrackABudgetProfile,
    search_record: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> None:
    ledger = search_record["ledger_snapshot"]
    usage = ledger["usage"]
    remaining = ledger["remaining"]
    if summary.get("budget_valid") is not True:
        raise DiagnosticAnalysisError(f"cell {cell.cell_id} reports invalid budget")
    if summary.get("non_primary_exhausted_axes") != []:
        raise DiagnosticAnalysisError(
            f"cell {cell.cell_id} exhausted a non-primary guard"
        )
    blocked_axes = summary.get("stop_blocked_axes")
    if type(blocked_axes) is not list:
        raise DiagnosticAnalysisError(f"cell {cell.cell_id} blocked axes are invalid")
    non_primary_blocked = [
        axis for axis in blocked_axes if axis != profile.primary_axis
    ]
    if non_primary_blocked:
        raise DiagnosticAnalysisError(
            f"cell {cell.cell_id} was blocked by a non-primary guard"
        )
    if any(
        type(remaining[axis]) is not int or remaining[axis] <= 0
        for axis in TRACK_A_WORK_AXES
        if axis != profile.primary_axis
    ):
        raise DiagnosticAnalysisError(
            f"cell {cell.cell_id} lacks positive non-primary headroom"
        )
    terminal_count = _require_plain_nonnegative_int(
        summary.get("terminal_count"),
        f"cell {cell.cell_id} terminal_count",
    )
    if terminal_count < 1:
        raise DiagnosticAnalysisError(f"cell {cell.cell_id} has no terminal readout")
    if type(summary.get("success_any")) is not bool:
        raise DiagnosticAnalysisError(f"cell {cell.cell_id} success_any is not boolean")
    for field in (
        "exact_terminal_count",
        "successful_terminal_diversity",
        "incomplete_trajectory_count",
    ):
        _require_plain_nonnegative_int(
            summary.get(field),
            f"cell {cell.cell_id} {field}",
        )

    coordinates = usage["generated_perturbation_coordinates"]
    legal_scores = usage["legal_action_scores"]
    point_count = summary.get("selected_source_point_count")
    selection_events = [
        event["payload"]
        for event in search_record["events"]
        if event["kind"] == "selection_committed"
    ]
    perturbation_events = [
        payload
        for payload in selection_events
        if type(payload.get("point_digest")) is str
    ]
    coordinate_total = sum(
        len(payload["scored_action_indices"]) for payload in perturbation_events
    )
    if method.stochastic:
        if point_count != len(perturbation_events) or coordinates != coordinate_total:
            raise DiagnosticAnalysisError(
                f"cell {cell.cell_id} stochastic coordinate accounting drifted"
            )
        if method.greedy_anchor_trajectory_count == 1:
            anchor_events = [
                payload
                for payload in selection_events
                if payload.get("trajectory_index") == 0
            ]
            if (
                len(anchor_events) != 5
                or any(
                    payload.get("point_digest") is not None for payload in anchor_events
                )
                or any(
                    payload.get("point_digest") is None
                    for payload in selection_events
                    if payload.get("trajectory_index") != 0
                )
                or coordinates >= legal_scores
            ):
                raise DiagnosticAnalysisError(
                    f"cell {cell.cell_id} greedy-anchor coordinate closure drifted"
                )
        elif coordinates != legal_scores or point_count != usage["edge_selections"]:
            raise DiagnosticAnalysisError(
                f"cell {cell.cell_id} ordinary Thompson coordinates drifted"
            )
    elif coordinates != 0 or point_count != 0:
        raise DiagnosticAnalysisError(
            f"cell {cell.cell_id} deterministic coordinates must be zero"
        )

    if method.method == "greedy":
        if terminal_count != 1 or summary.get("stop_reason") != "method_complete":
            raise DiagnosticAnalysisError("greedy completion closure drifted")
    elif method.method == "beam":
        if terminal_count != 2 or summary.get("stop_reason") != "method_complete":
            raise DiagnosticAnalysisError("beam completion closure drifted")
    elif method.method in {"puct", "thompson"}:
        if summary.get("stop_reason") != "primary_budget_blocked" or blocked_axes != [
            profile.primary_axis
        ]:
            raise DiagnosticAnalysisError(
                f"cell {cell.cell_id} adaptive stop closure drifted"
            )
        attempted = summary.get("stop_attempted_charge")
        if type(attempted) is not dict or set(attempted) != set(TRACK_A_WORK_AXES):
            raise DiagnosticAnalysisError("adaptive attempted charge is invalid")
        if attempted[profile.primary_axis] <= remaining[profile.primary_axis]:
            raise DiagnosticAnalysisError(
                "adaptive stop did not reject the next whole primary charge"
            )
        if any(
            attempted[axis] > remaining[axis]
            for axis in TRACK_A_WORK_AXES
            if axis != profile.primary_axis
        ):
            raise DiagnosticAnalysisError(
                "adaptive stop would also bind a non-primary guard"
            )
    if profile.profile_id != "score256":
        raise DiagnosticAnalysisError("diagnostic profile is not score256")


def _validate_one_record(
    record: dict[str, Any],
    *,
    cell: DiagnosticCell,
    bundle_id: str,
    diagnostic_seal_digest: str,
    method_manifest_digest: str,
    replay_inputs: _ReplayInputs,
    runner_build_digest: str,
    search_build_digest: str,
    runtime_qualification_digest: str,
) -> dict[str, Any]:
    if set(record) != _RUN_RECORD_FIELDS:
        raise DiagnosticAnalysisError(f"cell {cell.cell_id} record fields drifted")
    if record["schema_version"] != RUN_RECORD_SCHEMA_VERSION:
        raise DiagnosticAnalysisError("runner record schema drifted")
    core = {
        key: value for key, value in record.items() if key != "deterministic_digest"
    }
    if record["deterministic_digest"] != sha256_json(core):
        raise DiagnosticAnalysisError(f"cell {cell.cell_id} record digest mismatch")
    if record["bundle_id"] != bundle_id or record["cell_id"] != cell.cell_id:
        raise DiagnosticAnalysisError("runner record external identity drifted")
    if not _same_json(record["cell_key"], cell.key):
        raise DiagnosticAnalysisError(f"cell {cell.cell_id} full key drifted")
    expected_labels = {
        "task_fingerprint": cell.task_fingerprint,
        "proposal_label": cell.proposal_label,
        "method_label": cell.method_label,
        "budget_profile_id": cell.budget_profile_id,
        "exploration_seed": cell.exploration_seed,
    }
    if type(record["labels"]) is not dict or set(record["labels"]) != _LABEL_FIELDS:
        raise DiagnosticAnalysisError("runner record labels are invalid")
    if not _same_json(record["labels"], expected_labels):
        raise DiagnosticAnalysisError(f"cell {cell.cell_id} labels drifted")
    bindings = {
        "diagnostic_seal_digest": diagnostic_seal_digest,
        "method_manifest_digest": method_manifest_digest,
        "runner_build_digest": runner_build_digest,
        "search_build_digest": search_build_digest,
        "runtime_qualification_digest": runtime_qualification_digest,
    }
    if any(record[key] != value for key, value in bindings.items()):
        raise DiagnosticAnalysisError(f"cell {cell.cell_id} authority binding drifted")
    if record["provider_calls"] != 0 or type(record["provider_calls"]) is not int:
        raise DiagnosticAnalysisError(f"cell {cell.cell_id} used a provider call")
    telemetry = record["telemetry"]
    if (
        type(telemetry) is not dict
        or set(telemetry) != _TELEMETRY_FIELDS
        or telemetry["role"] != _TELEMETRY_ROLE
    ):
        raise DiagnosticAnalysisError(f"cell {cell.cell_id} telemetry fields drifted")
    for field in ("search_wall_time_ns", "replay_wall_time_ns"):
        _require_plain_nonnegative_int(
            telemetry[field],
            f"cell {cell.cell_id} telemetry.{field}",
        )

    search_record = record["search_record"]
    if type(search_record) is not dict:
        raise DiagnosticAnalysisError("embedded search record must be an object")
    try:
        search_bytes = canonical_trace_bytes(search_record)
    except (TraceValidationError, TypeError, ValueError) as error:
        raise DiagnosticAnalysisError("embedded search record is invalid") from error
    if record["search_trace_sha256"] != _sha256_bytes(search_bytes):
        raise DiagnosticAnalysisError("embedded search trace SHA-256 mismatch")
    if type(record["search_trace_byte_count"]) is not int or record[
        "search_trace_byte_count"
    ] != len(search_bytes):
        raise DiagnosticAnalysisError("embedded search trace byte count mismatch")
    _validate_digest_field(record, "search_run_identity_digest")

    task = replay_inputs.tasks[cell.task_fingerprint]
    proposal = replay_inputs.proposals[cell.proposal_label]
    method = replay_inputs.methods[cell.method_label]
    profile = replay_inputs.budgets[cell.budget_profile_id]
    try:
        replayed = replay_countdown_track_a_search_bytes(
            search_bytes,
            task=task,
            proposal=proposal,
            method=method,
            budget_profile=profile,
            exploration_seed=cell.exploration_seed,
            expected_run_identity_digest=record["search_run_identity_digest"],
        )
    except (TraceValidationError, TypeError, ValueError) as error:
        raise DiagnosticAnalysisError(
            f"cell {cell.cell_id} failed independent two-stage replay"
        ) from error

    replay = record["replay"]
    if type(replay) is not dict or set(replay) != _REPLAY_FIELDS:
        raise DiagnosticAnalysisError("runner replay receipt fields drifted")
    if (
        replay["stage1_generative"] != "PASS"
        or replay["stage2_byte_identical"] != "PASS"
        or replay["replayed_sha256"] != _sha256_bytes(replayed)
        or replayed != search_bytes
    ):
        raise DiagnosticAnalysisError(
            f"cell {cell.cell_id} replay receipt does not close"
        )

    summary = _search_summary(search_record)
    if not _same_json(record["search_summary"], summary):
        raise DiagnosticAnalysisError(
            "runner search summary differs from replayed trace"
        )
    expected_budget = _expected_budget_evidence(
        profile=profile,
        search_record=search_record,
        summary=summary,
    )
    if (
        type(record["budget_evidence"]) is not dict
        or set(record["budget_evidence"]) != _BUDGET_EVIDENCE_FIELDS
        or not _same_json(record["budget_evidence"], expected_budget)
    ):
        raise DiagnosticAnalysisError("runner budget evidence does not close")
    _validate_profile_and_accounting(
        cell=cell,
        method=method,
        profile=profile,
        search_record=search_record,
        summary=summary,
    )
    return {
        "cell": cell,
        "ledger_snapshot": search_record["ledger_snapshot"],
        "search_record": search_record,
        "summary": summary,
        "budget_evidence": expected_budget,
        "telemetry": telemetry,
    }


@dataclass(frozen=True)
class _ValidatedRun:
    bundle: VerifiedDiagnosticBundle
    records: tuple[dict[str, Any], ...]
    manifest: dict[str, Any]
    analyzer_build_digest: str


def _validate_artifact(
    artifact_dir: Path,
    bundle_dir: Path,
    authorization_path: Path,
    authorization_digest: str,
    *,
    repository_root: Path,
) -> _ValidatedRun:
    """Validate every integrity gate before returning outcome-bearing rows."""

    repository = Path(repository_root).resolve()
    preflight_manifest_raw = _read_artifact_member_preflight(
        Path(artifact_dir),
        "manifest.json",
    )
    preflight_manifest = _stdlib_strict_json_object(
        preflight_manifest_raw,
        "manifest.json",
    )
    preflight_commit_raw = _read_artifact_member_preflight(
        Path(artifact_dir),
        "commit.json",
    )
    preflight_commit = _stdlib_strict_json_object(
        preflight_commit_raw,
        "commit.json",
    )
    _validate_artifact_commit(preflight_commit, preflight_manifest)
    attestation, execution_head_revision, _reviewed_revision = _preflight_run_manifest(
        preflight_manifest
    )
    analyzer_build_digest = _validate_current_replay_surface(
        repository,
        attestation=attestation,
        execution_head_revision=execution_head_revision,
    )
    authorization_file, _authorization_relative = _authorization_repository_location(
        Path(authorization_path),
        repository,
    )
    reviewed_authorization, reviewed_authorization_raw = _reviewed_authorization(
        authorization_file,
        authorization_digest,
    )
    _preflight_authorization(
        reviewed_authorization,
        manifest=preflight_manifest,
        attestation=attestation,
    )
    _validate_reviewed_authorization_provenance(
        repository,
        authorization_path=authorization_file,
        authorization_raw=reviewed_authorization_raw,
        manifest=preflight_manifest,
    )
    try:
        bundle = verify_countdown_thompson_diagnostic_bundle(
            Path(bundle_dir),
            repository_root=repository,
        )
        expected_cells = iter_countdown_thompson_diagnostic_cells(bundle)
    except (OSError, TraceValidationError, ValueError) as error:
        raise DiagnosticAnalysisError(
            "diagnostic bundle verification failed"
        ) from error
    if len(expected_cells) != EXPECTED_CELL_COUNT:
        raise DiagnosticAnalysisError("verified diagnostic schedule count drifted")
    _preflight_verified_bundle_authority(
        reviewed_authorization,
        manifest=preflight_manifest,
        bundle=bundle,
        expected_cells=expected_cells,
    )

    first_snapshot = _read_artifact_snapshot(Path(artifact_dir))
    if first_snapshot["manifest.json"] != preflight_manifest_raw:
        raise DiagnosticAnalysisError("runner manifest changed after source preflight")
    if first_snapshot["commit.json"] != preflight_commit_raw:
        raise DiagnosticAnalysisError("artifact commit changed after source preflight")
    manifest = _strict_json_object(first_snapshot["manifest.json"], "manifest.json")
    raw_records = first_snapshot["records.jsonl"]
    records = _strict_jsonl(raw_records)
    if len(records) != EXPECTED_CELL_COUNT:
        raise DiagnosticAnalysisError("runner artifact record count drifted")
    (
        runner_digest,
        search_digest,
        qualification_digest,
        analyzer_build_digest,
    ) = _validate_run_manifest(
        manifest,
        records_raw=raw_records,
        expected_cells=expected_cells,
        bundle=bundle,
        reviewed_authorization=reviewed_authorization,
        reviewed_authorization_raw=reviewed_authorization_raw,
        analyzer_build_digest=analyzer_build_digest,
    )
    record_digests = [record.get("deterministic_digest") for record in records]
    if not _same_json(manifest["record_digests"], record_digests):
        raise DiagnosticAnalysisError("runner manifest record digest sequence drifted")
    observed_ids = [record.get("cell_id") for record in records]
    expected_ids = [cell.cell_id for cell in expected_cells]
    if observed_ids != expected_ids or len(set(observed_ids)) != len(observed_ids):
        raise DiagnosticAnalysisError(
            "runner artifact has missing, duplicate, extra, or reordered cells"
        )

    replay_inputs = _typed_replay_inputs(bundle)
    bundle_payloads = bundle.payloads
    bundle_id = bundle_payloads["preregistration.json"]["bundle_id"]
    method_manifest_digest = bundle_payloads["methods.json"]["deterministic_digest"]
    validated_rows = tuple(
        _validate_one_record(
            record,
            cell=cell,
            bundle_id=bundle_id,
            diagnostic_seal_digest=bundle.seal_digest,
            method_manifest_digest=method_manifest_digest,
            replay_inputs=replay_inputs,
            runner_build_digest=runner_digest,
            search_build_digest=search_digest,
            runtime_qualification_digest=qualification_digest,
        )
        for record, cell in zip(records, expected_cells, strict=True)
    )
    expected_telemetry = {
        "role": _TELEMETRY_ROLE,
        "search_wall_time_ns_total": sum(
            row["telemetry"]["search_wall_time_ns"] for row in validated_rows
        ),
        "replay_wall_time_ns_total": sum(
            row["telemetry"]["replay_wall_time_ns"] for row in validated_rows
        ),
    }
    if not _same_json(manifest["telemetry"], expected_telemetry):
        raise DiagnosticAnalysisError("runner manifest telemetry totals do not close")
    if (
        _read_regular_file_nofollow(
            authorization_file,
            "reviewed authorization path",
        )
        != reviewed_authorization_raw
    ):
        raise DiagnosticAnalysisError("reviewed authorization changed during analysis")
    if (
        _validate_current_replay_surface(
            repository,
            attestation=attestation,
            execution_head_revision=execution_head_revision,
        )
        != analyzer_build_digest
    ):
        raise DiagnosticAnalysisError(
            "current replay source closure changed during analysis"
        )
    if _read_artifact_snapshot(Path(artifact_dir)) != first_snapshot:
        raise DiagnosticAnalysisError("runner artifact changed during verification")
    return _ValidatedRun(
        bundle,
        validated_rows,
        manifest,
        analyzer_build_digest,
    )


def _fraction_payload(value: Fraction) -> dict[str, int]:
    return {"denominator": value.denominator, "numerator": value.numerator}


def _fraction_mean(values: Sequence[Fraction]) -> Fraction:
    if not values:
        raise DiagnosticAnalysisError("cannot aggregate zero observations")
    return sum(values, Fraction(0, 1)) / len(values)


def _fraction_compare(left: Fraction, operator: str, right: Fraction) -> bool:
    if operator == ">=":
        return left >= right
    if operator == "<=":
        return left <= right
    raise DiagnosticAnalysisError(f"unsupported exact comparison: {operator}")


def _task_order(validated: _ValidatedRun) -> tuple[str, ...]:
    return tuple(
        row["task_fingerprint"]
        for row in validated.bundle.payloads["diagnostic_tasks.json"]["tasks"]
    )


def _rows_by_method(
    validated: _ValidatedRun, method_label: str
) -> list[dict[str, Any]]:
    return [
        row
        for row in validated.records
        if row["cell"].proposal_label == "heuristic"
        and row["cell"].method_label == method_label
    ]


def _proposal_material(search_record: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for event in search_record["events"]:
        if event["kind"] != "proposal_materialized":
            continue
        proposal = event["payload"].get("proposal")
        if type(proposal) is not dict:
            raise DiagnosticAnalysisError("proposal material is not an object")
        digest = proposal.get("behavior_digest")
        if type(digest) is not str or digest in result:
            raise DiagnosticAnalysisError(
                "proposal behavior digest is invalid or repeated"
            )
        result[digest] = proposal
    return result


def _selection_rank(
    selection: Mapping[str, Any],
    proposals: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    digest = selection.get("proposal_behavior_digest")
    proposal = proposals.get(digest) if type(digest) is str else None
    if proposal is None:
        raise DiagnosticAnalysisError("selection does not reference proposal material")
    prior = proposal.get("prior_logp")
    action_order = proposal.get("action_order")
    if type(prior) is not list or type(action_order) is not list or not prior:
        raise DiagnosticAnalysisError("proposal rank vectors are invalid")
    if len(prior) != len(action_order):
        raise DiagnosticAnalysisError("proposal rank vector widths differ")
    if any(type(value) is not float or not math.isfinite(value) for value in prior):
        raise DiagnosticAnalysisError(
            "proposal rank vector is not finite float material"
        )
    action_count = len(prior)
    action_index = selection.get("action_index")
    scored = selection.get("scored_action_indices")
    if (
        type(action_index) is not int
        or not 0 <= action_index < action_count
        or scored != list(range(action_count))
        or selection.get("action_order_digest") != proposal.get("action_order_digest")
    ):
        raise DiagnosticAnalysisError("selection rank action closure drifted")
    order = sorted(range(action_count), key=lambda index: (-prior[index], index))
    one_based_rank = order.index(action_index) + 1
    normalized = (
        Fraction(0, 1)
        if action_count == 1
        else Fraction(one_based_rank - 1, action_count - 1)
    )
    return {
        "action_count": action_count,
        "action_identity": [proposal["action_order_digest"], action_index],
        "normalized_rank": normalized,
        "one_based_rank": one_based_rank,
    }


def _action_bin(action_count: int) -> str:
    for label, lower, upper in _ACTION_COUNT_BINS:
        if lower <= action_count <= upper:
            return label
    raise DiagnosticAnalysisError(
        f"action count lies outside sealed bins: {action_count}"
    )


def _mechanism_metrics(validated: _ValidatedRun) -> dict[str, Any]:
    task_order = _task_order(validated)
    method_results: dict[str, dict[str, Any]] = {}
    for method_label in _STOCHASTIC_METHOD_ORDER:
        rows = _rows_by_method(validated, method_label)
        expected_keys = [
            (task, seed) for task in task_order for seed in _DIAGNOSTIC_SEEDS
        ]
        observed_keys = [
            (row["cell"].task_fingerprint, row["cell"].exploration_seed) for row in rows
        ]
        if observed_keys != expected_keys or len(rows) != 48:
            raise DiagnosticAnalysisError(
                f"{method_label} root-rank vector order/coverage drifted"
            )

        root_rows: list[dict[str, Any]] = []
        bin_values: dict[str, list[Fraction]] = {
            label: [] for label, _lower, _upper in _ACTION_COUNT_BINS
        }
        for row in rows:
            search_record = row["search_record"]
            proposals = _proposal_material(search_record)
            perturbation_selections = [
                event["payload"]
                for event in search_record["events"]
                if event["kind"] == "selection_committed"
                and type(event["payload"].get("point_digest")) is str
            ]
            root_selections = [
                payload
                for payload in perturbation_selections
                if payload.get("depth") == 0
            ]
            if not root_selections:
                raise DiagnosticAnalysisError(
                    f"{method_label} is missing its perturbation-selected root event"
                )
            root = root_selections[0]
            expected_trajectory = (
                1 if method_label == _STOCHASTIC_METHOD_ORDER[-1] else 0
            )
            if root.get("trajectory_index") != expected_trajectory:
                raise DiagnosticAnalysisError(
                    f"{method_label} first perturbation root trajectory drifted"
                )
            rank = _selection_rank(root, proposals)
            root_rows.append(
                {
                    "action_count": rank["action_count"],
                    "action_identity": rank["action_identity"],
                    "exploration_seed": row["cell"].exploration_seed,
                    "normalized_rank": _fraction_payload(rank["normalized_rank"]),
                    "one_based_rank": rank["one_based_rank"],
                    "task_fingerprint": row["cell"].task_fingerprint,
                }
            )
            for selection in perturbation_selections:
                evidence = _selection_rank(selection, proposals)
                bin_values[_action_bin(evidence["action_count"])].append(
                    evidence["normalized_rank"]
                )

        root_fractions = [
            Fraction(
                row["normalized_rank"]["numerator"],
                row["normalized_rank"]["denominator"],
            )
            for row in root_rows
        ]
        task_diversities: list[int] = []
        for task in task_order:
            identities = {
                tuple(row["action_identity"])
                for row in root_rows
                if row["task_fingerprint"] == task
            }
            task_diversities.append(len(identities))
        occupied_means = {
            label: _fraction_mean(values)
            for label, values in bin_values.items()
            if values
        }
        if len(occupied_means) < 2:
            raise DiagnosticAnalysisError(
                f"{method_label} occupies fewer than two action-count bins"
            )
        gap = max(occupied_means.values()) - min(occupied_means.values())
        method_results[method_label] = {
            "mean_normalized_root_rank": _fraction_payload(
                _fraction_mean(root_fractions)
            ),
            "mean_root_action_diversity": _fraction_payload(
                Fraction(sum(task_diversities), len(task_diversities))
            ),
            "occupied_action_bin_gap": _fraction_payload(gap),
            "occupied_action_bin_means": {
                label: _fraction_payload(value)
                for label, value in occupied_means.items()
            },
            "root_rank_vector": root_rows,
            "root_top5_retained_count": sum(
                row["one_based_rank"] <= 5 for row in root_rows
            ),
            "task_root_action_diversity_vector": task_diversities,
            "tasks_with_multiple_root_actions": sum(
                value > 1 for value in task_diversities
            ),
        }

    v1 = method_results[_STOCHASTIC_METHOD_ORDER[0]]
    v2 = method_results[_STOCHASTIC_METHOD_ORDER[1]]
    top5_improvement = Fraction(
        v2["root_top5_retained_count"] - v1["root_top5_retained_count"], 1
    )
    rank_improvement = Fraction(
        v1["mean_normalized_root_rank"]["numerator"],
        v1["mean_normalized_root_rank"]["denominator"],
    ) - Fraction(
        v2["mean_normalized_root_rank"]["numerator"],
        v2["mean_normalized_root_rank"]["denominator"],
    )
    diversity = Fraction(
        v2["mean_root_action_diversity"]["numerator"],
        v2["mean_root_action_diversity"]["denominator"],
    )
    gap = Fraction(
        v2["occupied_action_bin_gap"]["numerator"],
        v2["occupied_action_bin_gap"]["denominator"],
    )
    checks = {
        "mean_normalized_root_rank_improvement_at_least_1_10": (
            rank_improvement >= Fraction(1, 10)
        ),
        "mean_root_action_diversity_at_least_3_2": diversity >= Fraction(3, 2),
        "occupied_action_bin_gap_at_most_3_20": gap <= Fraction(3, 20),
        "tasks_with_multiple_root_actions_at_least_6": (
            v2["tasks_with_multiple_root_actions"] >= 6
        ),
        "top5_root_retained_count_improvement_at_least_8": (top5_improvement >= 8),
    }
    return {
        "checks": checks,
        "method_metrics": method_results,
        "status": "PASS" if all(checks.values()) else "MECHANISM_NOT_CONFIRMED",
        "v1_minus_v2_mean_normalized_root_rank": _fraction_payload(rank_improvement),
        "v2_minus_v1_top5_count": _fraction_payload(top5_improvement),
    }


def _dense_terminal_metrics(validated: _ValidatedRun) -> dict[str, Any]:
    task_order = _task_order(validated)
    task_specs = {
        row["task_fingerprint"]: row
        for row in validated.bundle.payloads["diagnostic_tasks.json"]["tasks"]
    }
    result: dict[str, Any] = {}
    for method_label in _STOCHASTIC_METHOD_ORDER[2:]:
        rows = _rows_by_method(validated, method_label)
        expected_keys = [
            (task, seed) for task in task_order for seed in _DIAGNOSTIC_SEEDS
        ]
        if [
            (row["cell"].task_fingerprint, row["cell"].exploration_seed) for row in rows
        ] != expected_keys:
            raise DiagnosticAnalysisError(f"{method_label} dense row order drifted")
        errors: list[int] = []
        values: list[float] = []
        observations: list[dict[str, Any]] = []
        for row in rows:
            task = task_specs[row["cell"].task_fingerprint]
            terminals = [
                event["payload"]
                for event in row["search_record"]["events"]
                if event["kind"] == "terminal_verified"
            ]
            if not terminals:
                raise DiagnosticAnalysisError(
                    f"{method_label} has no terminal evidence"
                )
            for payload in terminals:
                trajectory_index = payload.get("trajectory_index")
                verification = payload.get("verification")
                if type(trajectory_index) is not int or type(verification) is not dict:
                    raise DiagnosticAnalysisError(
                        "dense terminal evidence is malformed"
                    )
                final_value = verification.get("final_value")
                if (
                    type(final_value) is not int
                    or verification.get("target") != task["target"]
                ):
                    raise DiagnosticAnalysisError("dense terminal verification drifted")
                error = abs(final_value - task["target"])
                value = max(float(Fraction(1, 1 + error)), math.ulp(0.0))
                errors.append(error)
                values.append(value)
                observations.append(
                    {
                        "exploration_seed": row["cell"].exploration_seed,
                        "task_fingerprint": row["cell"].task_fingerprint,
                        "terminal_absolute_error": error,
                        "terminal_value": value,
                        "trajectory_index": trajectory_index,
                    }
                )
        if not errors:
            raise DiagnosticAnalysisError("dense terminal aggregate is empty")
        ordered = sorted(errors)
        midpoint = len(ordered) // 2
        median = (
            Fraction(ordered[midpoint], 1)
            if len(ordered) % 2
            else Fraction(ordered[midpoint - 1] + ordered[midpoint], 2)
        )
        result[method_label] = {
            "mean_terminal_absolute_error": _fraction_payload(
                Fraction(sum(errors), len(errors))
            ),
            "mean_terminal_value": math.fsum(values) / len(values),
            "median_terminal_absolute_error": _fraction_payload(median),
            "minimum_terminal_absolute_error": min(errors),
            "observation_count": len(errors),
            "ordered_observations": observations,
            "terminal_absolute_error_vector": errors,
            "terminal_value_vector": values,
        }
    return result


def _success_metrics(
    validated: _ValidatedRun,
) -> tuple[list[dict[str, Any]], dict[str, list[Fraction]], dict[str, int]]:
    task_order = _task_order(validated)
    metrics: list[dict[str, Any]] = []
    vectors: dict[str, list[Fraction]] = {}
    success_counts: dict[str, int] = {}
    for method_label in (*_DETERMINISTIC_BASELINES, *_STOCHASTIC_METHOD_ORDER):
        rows = _rows_by_method(validated, method_label)
        by_task: dict[str, list[dict[str, Any]]] = {task: [] for task in task_order}
        for row in rows:
            by_task[row["cell"].task_fingerprint].append(row)
        vector: list[Fraction] = []
        total = 0
        for task in task_order:
            task_rows = by_task[task]
            expected_seeds = (
                (0,) if method_label in _DETERMINISTIC_BASELINES else _DIAGNOSTIC_SEEDS
            )
            observed_seeds = tuple(row["cell"].exploration_seed for row in task_rows)
            if observed_seeds != expected_seeds:
                raise DiagnosticAnalysisError(
                    f"{method_label} task/seed reduction coverage drifted"
                )
            successes = [row["summary"]["success_any"] for row in task_rows]
            if any(type(value) is not bool for value in successes):
                raise DiagnosticAnalysisError("success vector contains a non-boolean")
            total += sum(successes)
            score = Fraction(sum(successes), len(successes))
            vector.append(score)
            metrics.append(
                {
                    "method_label": method_label,
                    "ordered_seed_successes": successes,
                    "task_fingerprint": task,
                    "task_score": _fraction_payload(score),
                }
            )
        vectors[method_label] = vector
        success_counts[method_label] = total
    return metrics, vectors, success_counts


def _v4_rescue_guard(validated: _ValidatedRun) -> tuple[bool, int]:
    rescue_count = 0
    for row in _rows_by_method(validated, _STOCHASTIC_METHOD_ORDER[-1]):
        terminals = [
            event["payload"]
            for event in row["search_record"]["events"]
            if event["kind"] == "terminal_verified"
        ]
        anchor = next(
            (payload for payload in terminals if payload.get("trajectory_index") == 0),
            None,
        )
        if anchor is None or type(anchor.get("verification")) is not dict:
            raise DiagnosticAnalysisError("v4 anchor terminal is missing")
        if anchor["verification"].get("success") is not False:
            continue
        if any(
            type(payload.get("trajectory_index")) is int
            and payload["trajectory_index"] > 0
            and type(payload.get("verification")) is dict
            and payload["verification"].get("success") is True
            for payload in terminals
        ):
            rescue_count += 1
    return rescue_count >= 1, rescue_count


def _engineering_readiness(
    validated: _ValidatedRun,
    vectors: Mapping[str, Sequence[Fraction]],
    success_counts: Mapping[str, int],
) -> dict[str, Any]:
    evaluations: list[dict[str, Any]] = []
    selected: str | None = None
    v4_guard, rescue_count = _v4_rescue_guard(validated)
    thresholds = {
        "beam_width_2": Fraction(3, 100),
        "greedy": Fraction(3, 100),
        "puct_c1": Fraction(-1, 50),
    }
    for candidate in _CANDIDATE_METHOD_ORDER:
        margins: dict[str, Any] = {}
        passed = True
        for baseline, threshold in thresholds.items():
            task_deltas = [
                left - right
                for left, right in zip(
                    vectors[candidate], vectors[baseline], strict=True
                )
            ]
            margin = _fraction_mean(task_deltas)
            comparison = _fraction_compare(margin, ">=", threshold)
            passed = passed and comparison
            margins[f"candidate_minus_{baseline}"] = {
                "mean_task_delta": _fraction_payload(margin),
                "passes": comparison,
                "task_delta_vector": [
                    _fraction_payload(value) for value in task_deltas
                ],
                "threshold": _fraction_payload(threshold),
            }
        guard_passes = candidate != _CANDIDATE_METHOD_ORDER[-1] or v4_guard
        passed = passed and guard_passes
        evaluations.append(
            {
                "candidate_method_label": candidate,
                "margins": margins,
                "method_specific_guard_passes": guard_passes,
                "passes_all_readiness_requirements": passed,
                "successful_run_count": success_counts[candidate],
            }
        )
        if selected is None and passed:
            selected = candidate
    return {
        "candidate_evaluations": evaluations,
        "selected_candidate_method": selected,
        "status": (
            "READY_TO_PREREGISTER_LOCKED_128_EXECUTION"
            if selected is not None
            else "STOP_REPAIR_NO_LOCKED_128_RUN"
        ),
        "v4_adaptive_rescue": {
            "passes": v4_guard,
            "passing_run_count": rescue_count,
        },
    }


def _method_summaries(
    validated: _ValidatedRun,
    vectors: Mapping[str, Sequence[Fraction]],
    success_counts: Mapping[str, int],
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for method_label in (*_DETERMINISTIC_BASELINES, *_STOCHASTIC_METHOD_ORDER):
        rows = _rows_by_method(validated, method_label)
        ledger_usage: dict[str, Any] = {}
        for axis in TRACK_A_WORK_AXES:
            values = [row["ledger_snapshot"]["usage"][axis] for row in rows]
            ledger_usage[axis] = {
                "arithmetic_mean_per_run": _fraction_payload(
                    Fraction(sum(values), len(values))
                ),
                "sum": sum(values),
            }
        telemetry: dict[str, Any] = {}
        for field in ("search_wall_time_ns", "replay_wall_time_ns"):
            values = [row["telemetry"][field] for row in rows]
            telemetry[field] = {
                "arithmetic_mean_per_run": _fraction_payload(
                    Fraction(sum(values), len(values))
                ),
                "maximum": max(values),
                "sum": sum(values),
            }
        summaries.append(
            {
                "ledger_usage": ledger_usage,
                "mean_task_score": _fraction_payload(
                    _fraction_mean(vectors[method_label])
                ),
                "method_label": method_label,
                "provider_calls": 0,
                "replay_status": "INDEPENDENT_TWO_STAGE_REPLAY_PASS",
                "run_count": len(rows),
                "successful_run_count": success_counts[method_label],
                "task_score_vector": [
                    _fraction_payload(value) for value in vectors[method_label]
                ],
                "telemetry_descriptive_only_excluded_from_gates": telemetry,
            }
        )
    return summaries


def _build_summary(validated: _ValidatedRun) -> dict[str, Any]:
    oracle_rows = [
        row
        for row in validated.records
        if row["cell"].proposal_label == "oracle_positive_control"
        and row["cell"].method_label == "greedy"
    ]
    oracle_successes = sum(row["summary"]["success_any"] for row in oracle_rows)
    if len(oracle_rows) != 12 or oracle_successes != 12:
        raise DiagnosticAnalysisError(
            "oracle positive control failed; diagnostic result is invalid"
        )

    mechanism = _mechanism_metrics(validated)
    dense = _dense_terminal_metrics(validated)
    task_metrics, vectors, success_counts = _success_metrics(validated)
    readiness = _engineering_readiness(validated, vectors, success_counts)
    summary = {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "analyzer_build_digest": validated.analyzer_build_digest,
        "bundle_id": validated.bundle.payloads["preregistration.json"]["bundle_id"],
        "claim_boundary": (
            "Engineering diagnostic only. No confidence interval, p-value, "
            "method-superiority claim, task-transfer claim, or locked-128 "
            "execution authority. Source-file bytes and imports are attested; "
            "already-loaded Python code objects remain outside this v1 claim."
        ),
        "controls": {
            "oracle_greedy_positive_control": {
                "required_successful_cells": 12,
                "status": "PASS",
                "successful_cells": oracle_successes,
            }
        },
        "dense_terminal_metrics": dense,
        "decision_status": readiness["status"],
        "diagnostic_seal_digest": validated.bundle.seal_digest,
        "engineering_readiness": readiness,
        "hard_gate_status": "PASS",
        "mechanism_metrics": mechanism,
        "method_summaries": _method_summaries(validated, vectors, success_counts),
        "reviewed_authorization_revision": validated.manifest[
            "reviewed_authorization_revision"
        ],
        "reviewed_execution_authorization_digest": validated.manifest[
            "execution_authorization_digest"
        ],
        "run_artifact_id": validated.manifest["artifact_id"],
        "run_attempt_id": validated.manifest["attempt_id"],
        "run_manifest_digest": validated.manifest["deterministic_digest"],
        "task_success_metrics": task_metrics,
    }
    summary["deterministic_digest"] = sha256_json(summary)
    return summary


def analyze_countdown_thompson_diagnostic_artifact(
    artifact_dir: Path,
    bundle_dir: Path,
    authorization_path: Path,
    authorization_digest: str,
    *,
    repository_root: Path,
) -> dict[str, Any]:
    """Validate every cell, then emit the preregistered engineering result."""

    validated = _validate_artifact(
        Path(artifact_dir),
        Path(bundle_dir),
        Path(authorization_path),
        authorization_digest,
        repository_root=repository_root,
    )
    return _build_summary(validated)


def _open_stable_directory(path: Path, label: str) -> tuple[int, os.stat_result]:
    try:
        before = os.stat(path, follow_symlinks=False)
        if not stat.S_ISDIR(before.st_mode):
            raise DiagnosticAnalysisError(f"{label} must be a regular directory")
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        directory_fd = os.open(path, flags)
        opened = os.fstat(directory_fd)
    except OSError as error:
        raise DiagnosticAnalysisError(f"{label} must be a stable directory") from error
    if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
        os.close(directory_fd)
        raise DiagnosticAnalysisError(f"{label} changed while it was opened")
    return directory_fd, opened


def _unlink_if_identity(
    directory_fd: int,
    filename: str,
    identity: tuple[int, int],
) -> bool:
    try:
        observed = os.stat(
            filename,
            dir_fd=directory_fd,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return False
    if (observed.st_dev, observed.st_ino) != identity:
        return False
    os.unlink(filename, dir_fd=directory_fd)
    return True


def _summary_publication_is_exact(
    destination: Path,
    parent_fd: int,
    parent_identity: tuple[int, int],
    staged_identity: tuple[int, int],
) -> bool:
    try:
        published = os.stat(
            destination.name,
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
    except OSError:
        return False
    if (published.st_dev, published.st_ino) != staged_identity:
        return False
    current_parent_fd = -1
    try:
        current_parent_fd, current_parent_stat = _open_stable_directory(
            destination.parent,
            "summary parent after publication",
        )
        if (
            current_parent_stat.st_dev,
            current_parent_stat.st_ino,
        ) != parent_identity:
            return False
        current_published = os.stat(
            destination.name,
            dir_fd=current_parent_fd,
            follow_symlinks=False,
        )
        return (current_published.st_dev, current_published.st_ino) == staged_identity
    except (DiagnosticAnalysisError, OSError):
        return False
    finally:
        if current_parent_fd >= 0:
            try:
                os.close(current_parent_fd)
            except OSError:
                pass


def _atomic_write_no_replace(
    path: Path,
    payload: bytes,
    *,
    protected_roots: Sequence[Path] = (),
) -> None:
    if os.name != "posix":
        raise DiagnosticAnalysisError(
            "descriptor-bound no-overwrite publication requires POSIX"
        )
    destination = Path(path)
    if not destination.name:
        raise DiagnosticAnalysisError("summary destination filename is empty")
    destination_resolved = destination.resolve()
    resolved_roots = tuple(Path(root).resolve() for root in protected_roots)
    if any(
        destination_resolved == root or destination_resolved.is_relative_to(root)
        for root in resolved_roots
    ):
        raise DiagnosticAnalysisError(
            "summary destination cannot modify the run artifact or sealed bundle"
        )

    protected_descriptors: list[int] = []
    protected_identities: set[tuple[int, int]] = set()
    parent_fd = -1
    temporary_name = ""
    staged_identity: tuple[int, int] | None = None
    linked = False
    try:
        for index, root in enumerate(resolved_roots):
            root_fd, root_stat = _open_stable_directory(
                root,
                f"protected root {index}",
            )
            protected_descriptors.append(root_fd)
            protected_identities.add((root_stat.st_dev, root_stat.st_ino))
        parent_fd, parent_stat = _open_stable_directory(
            destination.parent,
            "summary parent",
        )
        if (parent_stat.st_dev, parent_stat.st_ino) in protected_identities:
            raise DiagnosticAnalysisError(
                "summary parent aliases the run artifact or sealed bundle"
            )
        try:
            os.stat(
                destination.name,
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError(f"summary destination exists: {destination}")

        file_descriptor = -1
        for _attempt in range(128):
            candidate = f".{destination.name}.{secrets.token_hex(16)}.tmp"
            try:
                file_descriptor = os.open(
                    candidate,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                    dir_fd=parent_fd,
                )
            except FileExistsError:
                continue
            temporary_name = candidate
            break
        if file_descriptor < 0:
            raise DiagnosticAnalysisError(
                "could not allocate exclusive summary staging"
            )
        with os.fdopen(file_descriptor, "wb") as handle:
            staged = os.fstat(handle.fileno())
            staged_identity = (staged.st_dev, staged.st_ino)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(
                temporary_name,
                destination.name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
                follow_symlinks=False,
            )
            linked = True
        except FileExistsError:
            raise
        except OSError as error:
            raise DiagnosticAnalysisError(
                "atomic no-overwrite summary publication is unavailable"
            ) from error
        published = os.stat(
            destination.name,
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
        if (published.st_dev, published.st_ino) != staged_identity:
            raise DiagnosticAnalysisError(
                "published summary inode changed before fsync"
            )
        os.fsync(parent_fd)
        current_parent_fd, current_parent_stat = _open_stable_directory(
            destination.parent,
            "summary parent after publication",
        )
        try:
            if (
                current_parent_stat.st_dev,
                current_parent_stat.st_ino,
            ) != (parent_stat.st_dev, parent_stat.st_ino):
                raise DiagnosticAnalysisError(
                    "summary parent path changed during publication"
                )
            current_published = os.stat(
                destination.name,
                dir_fd=current_parent_fd,
                follow_symlinks=False,
            )
            if (current_published.st_dev, current_published.st_ino) != (
                staged_identity
            ):
                raise DiagnosticAnalysisError(
                    "summary destination path changed during publication"
                )
        finally:
            os.close(current_parent_fd)
    except BaseException as error:
        if linked and staged_identity is not None and parent_fd >= 0:
            try:
                os.fsync(parent_fd)
                if _summary_publication_is_exact(
                    destination,
                    parent_fd,
                    (parent_stat.st_dev, parent_stat.st_ino),
                    staged_identity,
                ):
                    return
            except (DiagnosticAnalysisError, OSError):
                pass

            rollback_durable = False
            try:
                removed = _unlink_if_identity(
                    parent_fd,
                    destination.name,
                    staged_identity,
                )
                if removed:
                    linked = False
                    os.fsync(parent_fd)
                    rollback_durable = True
                else:
                    rollback_durable = not _summary_publication_is_exact(
                        destination,
                        parent_fd,
                        (parent_stat.st_dev, parent_stat.st_ino),
                        staged_identity,
                    )
            except OSError:
                rollback_durable = False
            if not rollback_durable:
                raise DiagnosticAnalysisPublicationAmbiguousError(
                    "summary publication durability and rollback are ambiguous; "
                    "the destination must not be used as diagnostic evidence"
                ) from error
        raise
    finally:
        if temporary_name and staged_identity is not None and parent_fd >= 0:
            try:
                _unlink_if_identity(
                    parent_fd,
                    temporary_name,
                    staged_identity,
                )
            except OSError:
                pass
        if parent_fd >= 0:
            try:
                os.close(parent_fd)
            except OSError:
                pass
        for descriptor in protected_descriptors:
            try:
                os.close(descriptor)
            except OSError:
                pass


def write_countdown_thompson_diagnostic_summary(
    artifact_dir: Path,
    bundle_dir: Path,
    authorization_path: Path,
    authorization_digest: str,
    output_path: Path,
    *,
    repository_root: Path,
) -> dict[str, Any]:
    """Analyze fully, then atomically publish one canonical no-overwrite summary."""

    destination = Path(output_path)
    destination_resolved = destination.resolve()
    protected_roots = (Path(artifact_dir).resolve(), Path(bundle_dir).resolve())
    if any(
        destination_resolved == root or destination_resolved.is_relative_to(root)
        for root in protected_roots
    ):
        raise DiagnosticAnalysisError(
            "summary destination cannot modify the run artifact or sealed bundle"
        )
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"summary destination exists: {destination}")
    summary = analyze_countdown_thompson_diagnostic_artifact(
        artifact_dir,
        bundle_dir,
        authorization_path,
        authorization_digest,
        repository_root=repository_root,
    )
    _atomic_write_no_replace(
        destination,
        _canonical_bytes(summary),
        protected_roots=protected_roots,
    )
    return summary


def _self_test() -> dict[str, Any]:
    """Exercise analyzer plumbing without opening the sealed diagnostic."""

    fixture = {
        "claim_boundary": "synthetic analyzer plumbing only",
        "schema_version": "qmc-bmgs-thompson-diagnostic-analysis-self-test/v1",
        "value": [0, 1, 2],
    }
    canonical = _canonical_bytes(fixture)
    if _strict_json_object(canonical, "self-test fixture") != fixture:
        raise AssertionError("self-test canonical JSON round trip drifted")
    if _strict_jsonl(canonical) != (fixture,):
        raise AssertionError("self-test canonical JSONL round trip drifted")
    with tempfile.TemporaryDirectory(prefix="qmc-track-a-analysis-self-test-") as root:
        output = Path(root) / "summary.json"
        _atomic_write_no_replace(output, canonical)
        if output.read_bytes() != canonical:
            raise AssertionError("self-test atomic publication bytes drifted")
        try:
            _atomic_write_no_replace(output, canonical)
        except FileExistsError:
            pass
        else:
            raise AssertionError("self-test no-overwrite publication did not close")
    return {
        "checks": [
            "strict_canonical_json",
            "strict_canonical_jsonl",
            "descriptor_bound_atomic_no_overwrite",
        ],
        "claim_boundary": (
            "non-diagnostic plumbing only; no sealed bundle, task, proposal, "
            "search record, or outcome was opened"
        ),
        "status": "PASS",
    }


def _invalid_cli_result(reason: str) -> dict[str, Any]:
    return {
        "claim_boundary": "no diagnostic result was emitted",
        "reason": reason,
        "status": "INVALID",
    }


class _FailClosedArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise DiagnosticAnalysisError(message)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _FailClosedArgumentParser(
        description="Fail-closed Thompson diagnostic artifact analyzer",
    )
    parser.add_argument("--analyze", type=Path, metavar="ARTIFACT")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--authorization-file", type=Path)
    parser.add_argument("--authorization-digest")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repository-root", type=Path)
    try:
        arguments = parser.parse_args(argv)
    except DiagnosticAnalysisError as error:
        print(canonical_json(_invalid_cli_result(str(error))))
        return 2

    if int(arguments.analyze is not None) + int(arguments.self_test) != 1:
        print(
            canonical_json(
                _invalid_cli_result("select exactly one of --analyze or --self-test")
            )
        )
        return 2
    try:
        if arguments.self_test:
            supplied_paths = (
                arguments.bundle,
                arguments.authorization_file,
                arguments.authorization_digest,
                arguments.output,
                arguments.repository_root,
            )
            if any(value is not None for value in supplied_paths):
                raise DiagnosticAnalysisError(
                    "--self-test accepts no bundle, authorization, output, or "
                    "repository paths"
                )
            result = _self_test()
        else:
            required = {
                "analyze": arguments.analyze,
                "bundle": arguments.bundle,
                "authorization_file": arguments.authorization_file,
                "authorization_digest": arguments.authorization_digest,
                "output": arguments.output,
                "repository_root": arguments.repository_root,
            }
            missing = [label for label, value in required.items() if value is None]
            if missing:
                raise DiagnosticAnalysisError(
                    f"--analyze is missing required arguments: {', '.join(missing)}"
                )
            summary = write_countdown_thompson_diagnostic_summary(
                arguments.analyze,
                arguments.bundle,
                arguments.authorization_file,
                arguments.authorization_digest,
                arguments.output,
                repository_root=arguments.repository_root,
            )
            result = {
                "analyzer_build_digest": summary["analyzer_build_digest"],
                "claim_boundary": (
                    "diagnostic result emitted only after every integrity gate "
                    "passed; no inferential, superiority, or locked-evaluation "
                    "authority"
                ),
                "output_path": str(arguments.output.resolve()),
                "status": "PASS",
                "summary_digest": summary["deterministic_digest"],
            }
    except DiagnosticAnalysisPublicationAmbiguousError as error:
        print(
            canonical_json(
                {
                    "claim_boundary": (
                        "summary publication durability is unresolved; no file at "
                        "the requested destination is authorized as diagnostic evidence"
                    ),
                    "reason": str(error),
                    "status": "PUBLICATION_STATE_AMBIGUOUS",
                }
            )
        )
        return 3
    except (
        AssertionError,
        DiagnosticAnalysisError,
        FileExistsError,
        OSError,
        ValueError,
    ) as error:
        print(canonical_json(_invalid_cli_result(str(error))))
        return 2
    print(canonical_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
