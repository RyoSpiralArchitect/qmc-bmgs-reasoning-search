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
import ctypes
import errno
import hashlib
import json
import math
import os
import secrets
import stat
import subprocess
import sys
import tempfile
from contextlib import ExitStack
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, TypedDict

from qmc_bmgs.benchmarks.countdown import CountdownTask
from qmc_bmgs.experiments.countdown_thompson_diagnostic_manifest import (
    BUNDLE_FILENAMES,
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
_ArtifactReceipt = tuple[tuple[str, int, str], ...]
_BundleReceipt = tuple[tuple[str, int, str], ...]
_COMMITTED_ATTEMPT_FILENAMES = (
    "pre_outcome.json",
    "started.json",
    "ready_to_commit.json",
)
_AttemptStateReceipt = tuple[tuple[str, int, str], ...]
_RUN_ARTIFACT_MEMBER_BYTE_CAPS_V1 = (
    ("commit.json", 1 * 1024 * 1024),
    ("manifest.json", 8 * 1024 * 1024),
    ("records.jsonl", 256 * 1024 * 1024),
)
_ARTIFACT_READ_CHUNK_BYTES = 1024 * 1024
_ATTEMPT_RECEIPT_BYTE_CAP_V1 = 8 * 1024 * 1024
_BUNDLE_MEMBER_BYTE_CAP_V1 = 8 * 1024 * 1024
# The runner accepts reviewed authorization as a control file under the same
# 8 MiB ceiling.  Keep that v1 compatibility boundary explicit here so an
# unreviewed oversized file is rejected before provenance inspection.
_REVIEWED_AUTHORIZATION_BYTE_CAP_V1 = 8 * 1024 * 1024
_REGULAR_FILE_READ_CHUNK_BYTES = 1024 * 1024
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
_AUTHORIZATION_SCHEMA_VERSION = (
    "qmc-bmgs-countdown-thompson-diagnostic-execution-authorization/v1"
)
_AUTHORIZATION_SCOPE = "one_exact_complete_240_cell_diagnostic_run"
_AUTHORIZATION_CLAIM_BOUNDARY = (
    "execution authority only; this engineering diagnostic grants no "
    "method-superiority or locked-128 execution authority"
)
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
    except (
        RecursionError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
    ) as error:
        raise DiagnosticAnalysisError(f"{label} is not strict UTF-8 JSON") from error
    if type(parsed) is not dict:
        raise DiagnosticAnalysisError(f"{label} must be a JSON object")
    try:
        canonical = (_stdlib_canonical_json(parsed) + "\n").encode("utf-8")
    except (RecursionError, TypeError, ValueError) as error:
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
    except (RecursionError, TraceValidationError, TypeError, ValueError):
        return False


def _require_plain_nonnegative_int(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise DiagnosticAnalysisError(f"{label} must be a non-negative plain integer")
    return value


def _close_descriptor_best_effort(descriptor: int) -> None:
    """Close cleanup without superseding a selected integrity result."""

    if descriptor < 0:
        return
    try:
        os.close(descriptor)
    except BaseException:
        pass


def _regular_file_stable_state(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _read_exact_regular_file_extent(
    file_descriptor: int,
    byte_count: int,
    label: str,
) -> bytes:
    """Read one already-capped extent and require immediate EOF."""

    payload = bytearray()
    remaining = byte_count
    try:
        while remaining:
            chunk = os.read(
                file_descriptor,
                min(remaining, _REGULAR_FILE_READ_CHUNK_BYTES),
            )
            if not chunk:
                raise DiagnosticAnalysisError(
                    f"{label} ended before its declared byte size"
                )
            payload.extend(chunk)
            remaining -= len(chunk)
        if os.read(file_descriptor, 1):
            raise DiagnosticAnalysisError(f"{label} grew beyond its declared byte size")
    except BlockingIOError as error:
        raise DiagnosticAnalysisError(
            f"{label} did not provide bounded regular-file bytes"
        ) from error
    return bytes(payload)


def _read_regular_file_nofollow(
    path: Path,
    label: str,
    *,
    max_bytes: int | None = None,
) -> bytes:
    """Read one stable regular-file extent through a nonblocking descriptor."""

    if (
        os.name != "posix"
        or not hasattr(os, "O_NOFOLLOW")
        or not hasattr(os, "O_NONBLOCK")
    ):
        raise DiagnosticAnalysisError(
            f"{label} validation requires POSIX O_NOFOLLOW and O_NONBLOCK"
        )
    candidate = Path(path)
    descriptor = -1
    try:
        before = os.stat(candidate, follow_symlinks=False)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size < 0
            or (max_bytes is not None and before.st_size > max_bytes)
        ):
            boundary = (
                f" within the v1 byte cap of {max_bytes}"
                if max_bytes is not None
                else ""
            )
            raise DiagnosticAnalysisError(f"{label} must be a regular file{boundary}")
        descriptor = os.open(
            candidate,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
        )
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or _regular_file_stable_state(
            opened
        ) != _regular_file_stable_state(before):
            raise DiagnosticAnalysisError(
                f"{label} changed before descriptor acquisition"
            )
        raw = _read_exact_regular_file_extent(
            descriptor,
            opened.st_size,
            label,
        )
        after_descriptor = os.fstat(descriptor)
        after_name = os.stat(candidate, follow_symlinks=False)
        expected_state = _regular_file_stable_state(opened)
        if (
            _regular_file_stable_state(after_descriptor) != expected_state
            or _regular_file_stable_state(after_name) != expected_state
        ):
            raise DiagnosticAnalysisError(f"{label} changed during bounded read")
        return raw
    except DiagnosticAnalysisError:
        raise
    except OSError as error:
        raise DiagnosticAnalysisError(
            f"{label} must be a stable bounded regular file"
        ) from error
    finally:
        _close_descriptor_best_effort(descriptor)


def _artifact_member_byte_cap(filename: str) -> int:
    for expected_filename, byte_cap in _RUN_ARTIFACT_MEMBER_BYTE_CAPS_V1:
        if filename == expected_filename:
            return byte_cap
    raise DiagnosticAnalysisError(f"unknown runner artifact member: {filename}")


def _validate_artifact_member_size(
    filename: str,
    value: object,
    label: str,
) -> int:
    if type(value) is not int or value < 0:
        raise DiagnosticAnalysisError(
            f"{label} member byte size is not a plain non-negative integer: {filename}"
        )
    byte_cap = _artifact_member_byte_cap(filename)
    if value > byte_cap:
        raise DiagnosticAnalysisError(
            f"{label} member exceeds the v1 byte cap of {byte_cap}: {filename}"
        )
    return value


def _artifact_member_stable_state(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _read_bounded_artifact_member_from_descriptor(
    directory_fd: int,
    filename: str,
    label: str,
    *,
    expected_size: int | None,
    capture_bytes: bool,
) -> tuple[bytes | None, tuple[str, int, str]]:
    """Read one regular member without blocking or chasing a growing EOF."""

    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_NONBLOCK"):
        raise DiagnosticAnalysisError(
            f"{label} validation requires O_NOFOLLOW and O_NONBLOCK"
        )
    try:
        observed = os.stat(
            filename,
            dir_fd=directory_fd,
            follow_symlinks=False,
        )
    except OSError as error:
        raise DiagnosticAnalysisError(
            f"{label} member could not be observed: {filename}"
        ) from error
    if not stat.S_ISREG(observed.st_mode):
        raise DiagnosticAnalysisError(f"{label} member is not regular: {filename}")
    observed_size = _validate_artifact_member_size(
        filename,
        observed.st_size,
        label,
    )
    if expected_size is not None:
        expected_size = _validate_artifact_member_size(
            filename,
            expected_size,
            label,
        )
        if observed_size != expected_size:
            raise DiagnosticAnalysisError(
                f"{label} member byte size differs from the validated artifact: "
                f"{filename}"
            )

    file_fd = -1
    try:
        file_fd = os.open(
            filename,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=directory_fd,
        )
        opened = os.fstat(file_fd)
        if not stat.S_ISREG(opened.st_mode):
            raise DiagnosticAnalysisError(
                f"{label} member raced to a non-regular file: {filename}"
            )
        opened_size = _validate_artifact_member_size(
            filename,
            opened.st_size,
            label,
        )

        if (opened.st_dev, opened.st_ino) != (
            observed.st_dev,
            observed.st_ino,
        ) or opened_size != observed_size:
            raise DiagnosticAnalysisError(
                f"{label} member changed before descriptor acquisition: {filename}"
            )

        remaining = opened_size
        hasher = hashlib.sha256()
        chunks: list[bytes] | None = [] if capture_bytes else None
        while remaining:
            chunk = os.read(
                file_fd,
                min(remaining, _ARTIFACT_READ_CHUNK_BYTES),
            )
            if not chunk:
                raise DiagnosticAnalysisError(
                    f"{label} member ended before its declared byte size: {filename}"
                )
            remaining -= len(chunk)
            hasher.update(chunk)
            if chunks is not None:
                chunks.append(chunk)
        if os.read(file_fd, 1):
            raise DiagnosticAnalysisError(
                f"{label} member grew beyond its declared byte size: {filename}"
            )
        after = os.fstat(file_fd)
        if _artifact_member_stable_state(after) != _artifact_member_stable_state(
            opened
        ):
            raise DiagnosticAnalysisError(
                f"{label} member changed during bounded read: {filename}"
            )
        payload = b"".join(chunks) if chunks is not None else None
        return payload, (filename, opened_size, hasher.hexdigest())
    except DiagnosticAnalysisError:
        raise
    except OSError as error:
        raise DiagnosticAnalysisError(
            f"{label} member is unavailable: {filename}"
        ) from error
    finally:
        _close_descriptor_best_effort(file_fd)


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
        payload, _receipt = _read_bounded_artifact_member_from_descriptor(
            directory_fd,
            filename,
            "runner artifact authority",
            expected_size=None,
            capture_bytes=True,
        )
        if payload is None:
            raise AssertionError("captured authority member bytes are unavailable")
        return payload
    finally:
        _close_descriptor_best_effort(directory_fd)


def _assert_artifact_directory_closure(directory_fd: int, label: str) -> None:
    expected = set(RUN_ARTIFACT_FILENAMES)
    names: set[str] = set()
    try:
        if not stat.S_ISDIR(os.fstat(directory_fd).st_mode):
            raise DiagnosticAnalysisError(f"{label} must be a regular directory")
        with os.scandir(directory_fd) as entries:
            for entry in entries:
                name = entry.name
                if name not in expected or name in names:
                    raise DiagnosticAnalysisError(f"{label} directory closure drifted")
                names.add(name)
    except DiagnosticAnalysisError:
        raise
    except OSError as error:
        raise DiagnosticAnalysisError(f"{label} could not be observed") from error
    if names != expected:
        raise DiagnosticAnalysisError(f"{label} directory closure drifted")


def _read_artifact_snapshot_from_descriptor(
    directory_fd: int,
    label: str,
) -> dict[str, bytes]:
    """Take one capped exact closed artifact snapshot through a pinned root fd."""

    _assert_artifact_directory_closure(directory_fd, label)
    snapshot: dict[str, bytes] = {}
    for filename in RUN_ARTIFACT_FILENAMES:
        payload, _receipt = _read_bounded_artifact_member_from_descriptor(
            directory_fd,
            filename,
            label,
            expected_size=None,
            capture_bytes=True,
        )
        if payload is None:
            raise AssertionError("captured artifact member bytes are unavailable")
        snapshot[filename] = payload
    _assert_artifact_directory_closure(directory_fd, label)
    return snapshot


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
            return _read_artifact_snapshot_from_descriptor(
                directory_fd,
                "runner artifact",
            )
        finally:
            _close_descriptor_best_effort(directory_fd)

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
        try:
            before = path.lstat()
        except OSError as error:
            raise DiagnosticAnalysisError(
                f"runner artifact member is unavailable: {filename}"
            ) from error
        if not stat.S_ISREG(before.st_mode):
            raise DiagnosticAnalysisError(
                f"runner artifact member is not regular: {filename}"
            )
        byte_count = _validate_artifact_member_size(
            filename,
            before.st_size,
            "runner artifact",
        )
        try:
            with path.open("rb") as handle:
                opened = os.fstat(handle.fileno())
                if (
                    not stat.S_ISREG(opened.st_mode)
                    or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
                    or opened.st_size != byte_count
                ):
                    raise DiagnosticAnalysisError(
                        f"runner artifact member changed before bounded read: {filename}"
                    )
                payload = handle.read(byte_count)
                if len(payload) != byte_count or handle.read(1):
                    raise DiagnosticAnalysisError(
                        f"runner artifact member changed during bounded read: {filename}"
                    )
                after = os.fstat(handle.fileno())
                if (
                    after.st_size != opened.st_size
                    or after.st_mtime_ns != opened.st_mtime_ns
                    or after.st_ctime_ns != opened.st_ctime_ns
                ):
                    raise DiagnosticAnalysisError(
                        f"runner artifact member changed during bounded read: {filename}"
                    )
        except DiagnosticAnalysisError:
            raise
        except OSError as error:
            raise DiagnosticAnalysisError(
                f"runner artifact member is unavailable: {filename}"
            ) from error
        snapshot[filename] = payload
    return snapshot


def _artifact_snapshot_receipt(
    snapshot: Mapping[str, bytes],
) -> _ArtifactReceipt:
    """Reduce an exact artifact snapshot to one immutable byte receipt."""

    if set(snapshot) != set(RUN_ARTIFACT_FILENAMES):
        raise DiagnosticAnalysisError("runner artifact receipt closure is invalid")
    receipt: list[tuple[str, int, str]] = []
    for filename in RUN_ARTIFACT_FILENAMES:
        payload = snapshot[filename]
        if type(payload) is not bytes:
            raise DiagnosticAnalysisError(
                f"runner artifact receipt member is not bytes: {filename}"
            )
        byte_count = _validate_artifact_member_size(
            filename,
            len(payload),
            "runner artifact receipt",
        )
        receipt.append((filename, byte_count, _sha256_bytes(payload)))
    return tuple(receipt)


def _validated_artifact_receipt(
    value: object,
    label: str,
) -> _ArtifactReceipt:
    if type(value) is not tuple or len(value) != len(RUN_ARTIFACT_FILENAMES):
        raise DiagnosticAnalysisError(f"{label} byte receipt is unavailable")
    receipt: list[tuple[str, int, str]] = []
    for expected_filename, member in zip(
        RUN_ARTIFACT_FILENAMES,
        value,
        strict=True,
    ):
        if type(member) is not tuple or len(member) != 3:
            raise DiagnosticAnalysisError(f"{label} byte receipt is invalid")
        filename, byte_count, digest = member
        if filename != expected_filename or not _is_sha256(digest):
            raise DiagnosticAnalysisError(f"{label} byte receipt is invalid")
        receipt.append(
            (
                filename,
                _validate_artifact_member_size(filename, byte_count, label),
                digest,
            )
        )
    return tuple(receipt)


def _read_artifact_receipt_from_descriptor(
    directory_fd: int,
    label: str,
    expected_receipt: _ArtifactReceipt,
) -> _ArtifactReceipt:
    """Stream a stable byte receipt through an already pinned artifact root."""

    if (
        os.name != "posix"
        or not hasattr(os, "O_NOFOLLOW")
        or not hasattr(os, "O_NONBLOCK")
    ):
        raise DiagnosticAnalysisError(
            f"{label} validation requires POSIX descriptor-bound reads"
        )
    expected = _validated_artifact_receipt(expected_receipt, label)

    def read_once() -> _ArtifactReceipt:
        _assert_artifact_directory_closure(directory_fd, label)
        pinned_members: list[tuple[str, int, os.stat_result]] = []
        try:
            for filename, expected_size, _digest in expected:
                try:
                    named_before = os.stat(
                        filename,
                        dir_fd=directory_fd,
                        follow_symlinks=False,
                    )
                except OSError as error:
                    raise DiagnosticAnalysisError(
                        f"{label} member could not be observed: {filename}"
                    ) from error
                if not stat.S_ISREG(named_before.st_mode):
                    raise DiagnosticAnalysisError(
                        f"{label} member is not regular: {filename}"
                    )
                named_size = _validate_artifact_member_size(
                    filename,
                    named_before.st_size,
                    label,
                )
                if named_size != expected_size:
                    raise DiagnosticAnalysisError(
                        f"{label} member byte size differs from the validated "
                        f"artifact: {filename}"
                    )

                member_fd = -1
                try:
                    member_fd = os.open(
                        filename,
                        os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                        dir_fd=directory_fd,
                    )
                    opened = os.fstat(member_fd)
                    if not stat.S_ISREG(opened.st_mode):
                        raise DiagnosticAnalysisError(
                            f"{label} member raced to a non-regular file: {filename}"
                        )
                    opened_size = _validate_artifact_member_size(
                        filename,
                        opened.st_size,
                        label,
                    )
                    if (opened.st_dev, opened.st_ino) != (
                        named_before.st_dev,
                        named_before.st_ino,
                    ) or opened_size != expected_size:
                        raise DiagnosticAnalysisError(
                            f"{label} member changed before descriptor acquisition: "
                            f"{filename}"
                        )
                    pinned_members.append((filename, member_fd, opened))
                    member_fd = -1
                finally:
                    _close_descriptor_best_effort(member_fd)

            observed: list[tuple[str, int, str]] = []
            for filename, member_fd, opened in pinned_members:
                os.lseek(member_fd, 0, os.SEEK_SET)
                remaining = opened.st_size
                hasher = hashlib.sha256()
                while remaining:
                    chunk = os.read(
                        member_fd,
                        min(remaining, _ARTIFACT_READ_CHUNK_BYTES),
                    )
                    if not chunk:
                        raise DiagnosticAnalysisError(
                            f"{label} member ended before its declared byte size: "
                            f"{filename}"
                        )
                    remaining -= len(chunk)
                    hasher.update(chunk)
                if os.read(member_fd, 1):
                    raise DiagnosticAnalysisError(
                        f"{label} member grew beyond its declared byte size: {filename}"
                    )
                after_read = os.fstat(member_fd)
                if _artifact_member_stable_state(
                    after_read
                ) != _artifact_member_stable_state(opened):
                    raise DiagnosticAnalysisError(
                        f"{label} member changed during bounded read: {filename}"
                    )
                observed.append((filename, opened.st_size, hasher.hexdigest()))

            _assert_artifact_directory_closure(directory_fd, label)
            descriptor_states = tuple(
                os.fstat(member_fd) for _filename, member_fd, _opened in pinned_members
            )
            try:
                named_states = tuple(
                    os.stat(
                        filename,
                        dir_fd=directory_fd,
                        follow_symlinks=False,
                    )
                    for filename, _member_fd, _opened in pinned_members
                )
            except OSError as error:
                raise DiagnosticAnalysisError(
                    f"{label} member names could not be reobserved"
                ) from error
            for (
                (filename, _member_fd, opened),
                descriptor_state,
                named_state,
            ) in zip(
                pinned_members,
                descriptor_states,
                named_states,
                strict=True,
            ):
                expected_state = _artifact_member_stable_state(opened)
                if _artifact_member_stable_state(descriptor_state) != expected_state:
                    raise DiagnosticAnalysisError(
                        f"{label} member changed after bounded receipt: {filename}"
                    )
                if (
                    not stat.S_ISREG(named_state.st_mode)
                    or _artifact_member_stable_state(named_state) != expected_state
                ):
                    raise DiagnosticAnalysisError(
                        f"{label} member name changed after bounded receipt: {filename}"
                    )
            return tuple(observed)
        except DiagnosticAnalysisError:
            raise
        except OSError as error:
            raise DiagnosticAnalysisError(
                f"{label} bounded receipt could not be completed"
            ) from error
        finally:
            for _filename, member_fd, _opened in pinned_members:
                _close_descriptor_best_effort(member_fd)

    first = read_once()
    if first != expected:
        raise DiagnosticAnalysisError(
            f"{label} bytes differ from the validated runner artifact"
        )
    if read_once() != first:
        raise DiagnosticAnalysisError(f"{label} changed during descriptor snapshot")
    return first


def _validate_bundle_member_size(
    filename: str,
    value: object,
    label: str,
) -> int:
    """Apply a bundle-only bound without changing runner artifact caps."""

    if filename not in BUNDLE_FILENAMES:
        raise DiagnosticAnalysisError(f"unknown diagnostic bundle member: {filename}")
    if type(value) is not int or value < 0 or value > _BUNDLE_MEMBER_BYTE_CAP_V1:
        raise DiagnosticAnalysisError(
            f"{label} member must be a plain non-negative size within the v1 "
            f"byte cap of {_BUNDLE_MEMBER_BYTE_CAP_V1}: {filename}"
        )
    return value


def _assert_bundle_directory_closure(directory_fd: int, label: str) -> None:
    expected = set(BUNDLE_FILENAMES)
    names: set[str] = set()
    try:
        if not stat.S_ISDIR(os.fstat(directory_fd).st_mode):
            raise DiagnosticAnalysisError(f"{label} must be a regular directory")
        with os.scandir(directory_fd) as entries:
            for entry in entries:
                name = entry.name
                if name not in expected or name in names:
                    raise DiagnosticAnalysisError(f"{label} directory closure drifted")
                names.add(name)
    except DiagnosticAnalysisError:
        raise
    except OSError as error:
        raise DiagnosticAnalysisError(f"{label} could not be observed") from error
    if names != expected:
        raise DiagnosticAnalysisError(f"{label} directory closure drifted")


def _validated_bundle_receipt(
    value: object,
    label: str,
) -> _BundleReceipt:
    if type(value) is not tuple or len(value) != len(BUNDLE_FILENAMES):
        raise DiagnosticAnalysisError(f"{label} byte receipt is unavailable")
    receipt: list[tuple[str, int, str]] = []
    for expected_filename, member in zip(BUNDLE_FILENAMES, value, strict=True):
        if type(member) is not tuple or len(member) != 3:
            raise DiagnosticAnalysisError(f"{label} byte receipt is invalid")
        filename, byte_count, digest = member
        if filename != expected_filename or not _is_sha256(digest):
            raise DiagnosticAnalysisError(f"{label} byte receipt is invalid")
        receipt.append(
            (
                filename,
                _validate_bundle_member_size(filename, byte_count, label),
                digest,
            )
        )
    return tuple(receipt)


def _read_bundle_receipt_once_from_descriptor(
    directory_fd: int,
    label: str,
) -> _BundleReceipt:
    """Stream one exact, bounded bundle closure through its pinned root fd."""

    if (
        os.name != "posix"
        or not hasattr(os, "O_NOFOLLOW")
        or not hasattr(os, "O_NONBLOCK")
    ):
        raise DiagnosticAnalysisError(
            f"{label} validation requires POSIX descriptor-bound reads"
        )
    pinned_members: list[tuple[str, int, os.stat_result]] = []
    try:
        before_directory = os.fstat(directory_fd)
        if not stat.S_ISDIR(before_directory.st_mode):
            raise DiagnosticAnalysisError(f"{label} must be a regular directory")
        directory_generation = _artifact_member_stable_state(before_directory)
        _assert_bundle_directory_closure(directory_fd, label)
        for filename in BUNDLE_FILENAMES:
            try:
                named_before = os.stat(
                    filename,
                    dir_fd=directory_fd,
                    follow_symlinks=False,
                )
            except OSError as error:
                raise DiagnosticAnalysisError(
                    f"{label} member could not be observed: {filename}"
                ) from error
            if not stat.S_ISREG(named_before.st_mode):
                raise DiagnosticAnalysisError(
                    f"{label} member is not regular: {filename}"
                )
            named_size = _validate_bundle_member_size(
                filename,
                named_before.st_size,
                label,
            )
            member_fd = -1
            try:
                member_fd = os.open(
                    filename,
                    os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                    dir_fd=directory_fd,
                )
                opened = os.fstat(member_fd)
                opened_size = _validate_bundle_member_size(
                    filename,
                    opened.st_size,
                    label,
                )
                if (
                    not stat.S_ISREG(opened.st_mode)
                    or _artifact_member_stable_state(opened)
                    != _artifact_member_stable_state(named_before)
                    or opened_size != named_size
                ):
                    raise DiagnosticAnalysisError(
                        f"{label} member changed before descriptor acquisition: "
                        f"{filename}"
                    )
                pinned_members.append((filename, member_fd, opened))
                member_fd = -1
            finally:
                _close_descriptor_best_effort(member_fd)

        observed: list[tuple[str, int, str]] = []
        for filename, member_fd, opened in pinned_members:
            os.lseek(member_fd, 0, os.SEEK_SET)
            remaining = opened.st_size
            hasher = hashlib.sha256()
            while remaining:
                chunk = os.read(
                    member_fd,
                    min(remaining, _ARTIFACT_READ_CHUNK_BYTES),
                )
                if not chunk:
                    raise DiagnosticAnalysisError(
                        f"{label} member ended before its declared byte size: "
                        f"{filename}"
                    )
                remaining -= len(chunk)
                hasher.update(chunk)
            if os.read(member_fd, 1):
                raise DiagnosticAnalysisError(
                    f"{label} member grew beyond its declared byte size: {filename}"
                )
            if _artifact_member_stable_state(
                os.fstat(member_fd)
            ) != _artifact_member_stable_state(opened):
                raise DiagnosticAnalysisError(
                    f"{label} member changed during bounded read: {filename}"
                )
            observed.append((filename, opened.st_size, hasher.hexdigest()))

        _assert_bundle_directory_closure(directory_fd, label)
        for filename, member_fd, opened in pinned_members:
            try:
                named_after = os.stat(
                    filename,
                    dir_fd=directory_fd,
                    follow_symlinks=False,
                )
            except OSError as error:
                raise DiagnosticAnalysisError(
                    f"{label} member name could not be reobserved: {filename}"
                ) from error
            expected_state = _artifact_member_stable_state(opened)
            if (
                _artifact_member_stable_state(os.fstat(member_fd)) != expected_state
                or not stat.S_ISREG(named_after.st_mode)
                or _artifact_member_stable_state(named_after) != expected_state
            ):
                raise DiagnosticAnalysisError(
                    f"{label} member name changed after bounded receipt: {filename}"
                )
        if (
            _artifact_member_stable_state(os.fstat(directory_fd))
            != directory_generation
        ):
            raise DiagnosticAnalysisError(
                f"{label} directory changed during bounded receipt"
            )
        return tuple(observed)
    except DiagnosticAnalysisError:
        raise
    except OSError as error:
        raise DiagnosticAnalysisError(
            f"{label} bounded receipt could not be completed"
        ) from error
    finally:
        for _filename, member_fd, _opened in pinned_members:
            _close_descriptor_best_effort(member_fd)


def _read_bundle_receipt_from_descriptor(
    directory_fd: int,
    label: str,
    expected_receipt: _BundleReceipt | None = None,
) -> _BundleReceipt:
    """Require two identical exact bundle receipts, optionally against a baseline."""

    expected = (
        _validated_bundle_receipt(expected_receipt, label)
        if expected_receipt is not None
        else None
    )
    first = _read_bundle_receipt_once_from_descriptor(directory_fd, label)
    if expected is not None and first != expected:
        raise DiagnosticAnalysisError(
            f"{label} bytes differ from the pre-validation bundle"
        )
    second = _read_bundle_receipt_once_from_descriptor(directory_fd, label)
    if second != first:
        raise DiagnosticAnalysisError(f"{label} changed during descriptor snapshot")
    return first


def _strict_json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8")
        parsed = strict_json_loads(text)
    except (RecursionError, UnicodeDecodeError, TraceValidationError) as error:
        raise DiagnosticAnalysisError(f"{label} is not strict UTF-8 JSON") from error
    if type(parsed) is not dict:
        raise DiagnosticAnalysisError(f"{label} must be a JSON object")
    try:
        canonical = _canonical_bytes(parsed)
    except (RecursionError, TraceValidationError, TypeError, ValueError) as error:
        raise DiagnosticAnalysisError(
            f"{label} is not finite canonical JSON"
        ) from error
    if canonical != raw:
        raise DiagnosticAnalysisError(f"{label} bytes are not canonical")
    return parsed


def _validate_attempt_member_size(
    filename: str,
    value: object,
    label: str,
) -> int:
    if filename not in _COMMITTED_ATTEMPT_FILENAMES:
        raise DiagnosticAnalysisError(f"{label} has an unknown member: {filename}")
    if type(value) is not int or value < 0:
        raise DiagnosticAnalysisError(
            f"{label} member byte size is not a plain non-negative integer: {filename}"
        )
    if value > _ATTEMPT_RECEIPT_BYTE_CAP_V1:
        raise DiagnosticAnalysisError(
            f"{label} member exceeds the v1 byte cap of "
            f"{_ATTEMPT_RECEIPT_BYTE_CAP_V1}: {filename}"
        )
    return value


def _assert_committed_attempt_directory_closure(
    directory_fd: int,
    label: str,
) -> None:
    expected = set(_COMMITTED_ATTEMPT_FILENAMES)
    names: set[str] = set()
    try:
        opened = os.fstat(directory_fd)
        if not stat.S_ISDIR(opened.st_mode):
            raise DiagnosticAnalysisError(f"{label} must be a regular directory")
        with os.scandir(directory_fd) as entries:
            for entry in entries:
                name = entry.name
                if name not in expected or name in names:
                    raise DiagnosticAnalysisError(f"{label} directory closure drifted")
                names.add(name)
    except DiagnosticAnalysisError:
        raise
    except OSError as error:
        raise DiagnosticAnalysisError(f"{label} could not be observed") from error
    if names != expected:
        raise DiagnosticAnalysisError(f"{label} directory closure drifted")


def _read_attempt_state_once_from_descriptor(
    directory_fd: int,
    label: str,
) -> tuple[dict[str, bytes], _AttemptStateReceipt]:
    """Read one collective, bounded attempt-state snapshot from pinned fds."""

    if (
        os.name != "posix"
        or not hasattr(os, "O_NOFOLLOW")
        or not hasattr(os, "O_NONBLOCK")
    ):
        raise DiagnosticAnalysisError(
            f"{label} validation requires POSIX descriptor-bound reads"
        )
    _assert_committed_attempt_directory_closure(directory_fd, label)
    pinned_members: list[tuple[str, int, os.stat_result]] = []
    try:
        for filename in _COMMITTED_ATTEMPT_FILENAMES:
            try:
                named_before = os.stat(
                    filename,
                    dir_fd=directory_fd,
                    follow_symlinks=False,
                )
            except OSError as error:
                raise DiagnosticAnalysisError(
                    f"{label} member could not be observed: {filename}"
                ) from error
            if not stat.S_ISREG(named_before.st_mode):
                raise DiagnosticAnalysisError(
                    f"{label} member is not regular: {filename}"
                )
            _validate_attempt_member_size(filename, named_before.st_size, label)
            member_fd = -1
            try:
                member_fd = os.open(
                    filename,
                    os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                    dir_fd=directory_fd,
                )
                opened = os.fstat(member_fd)
                if not stat.S_ISREG(opened.st_mode):
                    raise DiagnosticAnalysisError(
                        f"{label} member raced to a non-regular file: {filename}"
                    )
                _validate_attempt_member_size(filename, opened.st_size, label)
                if _artifact_member_stable_state(
                    opened
                ) != _artifact_member_stable_state(named_before):
                    raise DiagnosticAnalysisError(
                        f"{label} member changed before descriptor acquisition: "
                        f"{filename}"
                    )
                pinned_members.append((filename, member_fd, opened))
                member_fd = -1
            finally:
                _close_descriptor_best_effort(member_fd)

        snapshot: dict[str, bytes] = {}
        receipt: list[tuple[str, int, str]] = []
        for filename, member_fd, opened in pinned_members:
            os.lseek(member_fd, 0, os.SEEK_SET)
            remaining = opened.st_size
            payload = bytearray()
            while remaining:
                chunk = os.read(
                    member_fd,
                    min(remaining, _ARTIFACT_READ_CHUNK_BYTES),
                )
                if not chunk:
                    raise DiagnosticAnalysisError(
                        f"{label} member ended before its declared byte size: "
                        f"{filename}"
                    )
                payload.extend(chunk)
                remaining -= len(chunk)
            if os.read(member_fd, 1):
                raise DiagnosticAnalysisError(
                    f"{label} member grew beyond its declared byte size: {filename}"
                )
            after_read = os.fstat(member_fd)
            if _artifact_member_stable_state(
                after_read
            ) != _artifact_member_stable_state(opened):
                raise DiagnosticAnalysisError(
                    f"{label} member changed during bounded read: {filename}"
                )
            raw = bytes(payload)
            snapshot[filename] = raw
            receipt.append((filename, opened.st_size, _sha256_bytes(raw)))

        _assert_committed_attempt_directory_closure(directory_fd, label)
        for filename, member_fd, opened in pinned_members:
            try:
                named_after = os.stat(
                    filename,
                    dir_fd=directory_fd,
                    follow_symlinks=False,
                )
            except OSError as error:
                raise DiagnosticAnalysisError(
                    f"{label} member name could not be reobserved: {filename}"
                ) from error
            expected_state = _artifact_member_stable_state(opened)
            if _artifact_member_stable_state(os.fstat(member_fd)) != expected_state:
                raise DiagnosticAnalysisError(
                    f"{label} member changed after bounded read: {filename}"
                )
            if (
                not stat.S_ISREG(named_after.st_mode)
                or _artifact_member_stable_state(named_after) != expected_state
            ):
                raise DiagnosticAnalysisError(
                    f"{label} member name changed after bounded read: {filename}"
                )
        return snapshot, tuple(receipt)
    except DiagnosticAnalysisError:
        raise
    except OSError as error:
        raise DiagnosticAnalysisError(
            f"{label} bounded receipt could not be completed"
        ) from error
    finally:
        for _filename, member_fd, _opened in pinned_members:
            _close_descriptor_best_effort(member_fd)


def _validated_attempt_state_receipt(
    value: object,
    label: str,
) -> _AttemptStateReceipt:
    if type(value) is not tuple or len(value) != len(_COMMITTED_ATTEMPT_FILENAMES):
        raise DiagnosticAnalysisError(f"{label} byte receipt is unavailable")
    receipt: list[tuple[str, int, str]] = []
    for expected_filename, member in zip(
        _COMMITTED_ATTEMPT_FILENAMES,
        value,
        strict=True,
    ):
        if type(member) is not tuple or len(member) != 3:
            raise DiagnosticAnalysisError(f"{label} byte receipt is invalid")
        filename, byte_count, digest = member
        if filename != expected_filename or not _is_sha256(digest):
            raise DiagnosticAnalysisError(f"{label} byte receipt is invalid")
        receipt.append(
            (
                filename,
                _validate_attempt_member_size(filename, byte_count, label),
                digest,
            )
        )
    return tuple(receipt)


def _read_attempt_state_receipt_from_descriptor(
    directory_fd: int,
    label: str,
    expected_receipt: _AttemptStateReceipt,
) -> _AttemptStateReceipt:
    expected = _validated_attempt_state_receipt(expected_receipt, label)
    _first_snapshot, first = _read_attempt_state_once_from_descriptor(
        directory_fd,
        label,
    )
    if first != expected:
        raise DiagnosticAnalysisError(
            f"{label} bytes differ from the validated committed attempt"
        )
    _second_snapshot, second = _read_attempt_state_once_from_descriptor(
        directory_fd,
        label,
    )
    if second != first:
        raise DiagnosticAnalysisError(f"{label} changed during descriptor snapshot")
    return first


def _revalidate_attempt_authority_after_topology(
    attempt_authority: _PinnedProtectedRoot,
    expected_receipt: _AttemptStateReceipt,
    protected_roots: Sequence[_PinnedProtectedRoot],
    label: str,
) -> _AttemptStateReceipt:
    """End an authority proof with one direct namespace-and-byte observation."""

    expected = _validated_attempt_state_receipt(expected_receipt, label)
    _assert_pinned_protected_roots(protected_roots)
    _read_attempt_state_receipt_from_descriptor(
        attempt_authority.descriptor,
        label,
        expected,
    )
    _assert_pinned_protected_roots(protected_roots)
    _final_snapshot, final_receipt = _read_attempt_state_once_from_descriptor(
        attempt_authority.descriptor,
        label,
    )
    if final_receipt != expected:
        raise DiagnosticAnalysisError(
            f"{label} bytes differ from the validated committed attempt"
        )
    _assert_pinned_protected_roots(protected_roots)
    return final_receipt


def _historical_attempt_path(manifest: Mapping[str, Any]) -> Path:
    authorized_output = manifest.get("authorized_output_path")
    artifact_id = manifest.get("artifact_id")
    authorization_digest = manifest.get("execution_authorization_digest")
    marker = manifest.get("attempt_marker_basename")
    if (
        type(authorized_output) is not str
        or not Path(authorized_output).is_absolute()
        or type(artifact_id) is not str
        or not artifact_id
        or Path(authorized_output).name != artifact_id
        or not _is_sha256(authorization_digest)
        or type(marker) is not str
    ):
        raise DiagnosticAnalysisError(
            "historical committed attempt path binding is invalid"
        )
    expected_marker = f".{artifact_id}.attempt-{authorization_digest}"
    marker_path = Path(marker)
    if (
        marker != expected_marker
        or marker in {"", ".", ".."}
        or marker_path.is_absolute()
        or marker_path.name != marker
        or marker_path.parts != (marker,)
    ):
        raise DiagnosticAnalysisError(
            "historical committed attempt marker is not one exact safe basename"
        )
    return Path(
        os.path.abspath(
            os.fspath(Path(authorized_output).parent / marker),
        )
    )


def _expected_committed_attempt_payloads(
    manifest: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    started = manifest.get("attempt_started_receipt")
    if type(started) is not dict or set(started) != _ATTEMPT_STARTED_RECEIPT_FIELDS:
        raise DiagnosticAnalysisError("embedded attempt STARTED receipt is invalid")
    started_core = {
        key: value for key, value in started.items() if key != "deterministic_digest"
    }
    if started.get("deterministic_digest") != _stdlib_sha256_json(started_core):
        raise DiagnosticAnalysisError(
            "embedded attempt STARTED receipt digest does not close"
        )
    common = {
        key: value
        for key, value in started.items()
        if key not in {"deterministic_digest", "phase", "status"}
    }
    pre_outcome_core = {
        **common,
        "phase": "PRE_OUTCOME",
        "status": "PENDING",
    }
    ready_core = {
        **common,
        "phase": "STARTED",
        "run_manifest_digest": manifest.get("deterministic_digest"),
        "status": "READY_TO_COMMIT",
    }
    return {
        "pre_outcome.json": {
            **pre_outcome_core,
            "deterministic_digest": _stdlib_sha256_json(pre_outcome_core),
        },
        "started.json": dict(started),
        "ready_to_commit.json": {
            **ready_core,
            "deterministic_digest": _stdlib_sha256_json(ready_core),
        },
    }


def _validate_historical_attempt_state_from_descriptor(
    directory_fd: int,
    manifest: Mapping[str, Any],
) -> _AttemptStateReceipt:
    first_snapshot, first_receipt = _read_attempt_state_once_from_descriptor(
        directory_fd,
        "historical committed attempt",
    )
    expected_payloads = _expected_committed_attempt_payloads(manifest)
    for filename in _COMMITTED_ATTEMPT_FILENAMES:
        expected_raw = (
            _stdlib_canonical_json(expected_payloads[filename]) + "\n"
        ).encode("utf-8")
        if first_snapshot[filename] != expected_raw:
            raise DiagnosticAnalysisError(
                f"historical committed attempt receipt does not close: {filename}"
            )
    second_snapshot, second_receipt = _read_attempt_state_once_from_descriptor(
        directory_fd,
        "historical committed attempt",
    )
    if second_snapshot != first_snapshot or second_receipt != first_receipt:
        raise DiagnosticAnalysisError(
            "historical committed attempt changed during validation"
        )
    return _validated_attempt_state_receipt(
        first_receipt,
        "historical committed attempt",
    )


def _read_historical_attempt_state(
    path: Path,
    manifest: Mapping[str, Any],
) -> _AttemptStateReceipt:
    expected_path = _historical_attempt_path(manifest)
    candidate = Path(os.path.abspath(os.fspath(path)))
    if candidate != expected_path:
        raise DiagnosticAnalysisError(
            "historical committed attempt path differs from the manifest"
        )
    try:
        pinned = _pin_protected_roots((candidate,))
    except DiagnosticAnalysisError as error:
        raise DiagnosticAnalysisError(
            "historical committed attempt must exist as a stable non-symlink directory"
        ) from error
    try:
        _assert_pinned_protected_roots(pinned)
        receipt = _validate_historical_attempt_state_from_descriptor(
            pinned[0].descriptor,
            manifest,
        )
        _assert_pinned_protected_roots(pinned)
        return receipt
    finally:
        _close_pinned_protected_roots(pinned)


def _reviewed_authorization(
    path: Path,
    supplied_digest: str,
) -> tuple[dict[str, Any], bytes]:
    raw = _read_regular_file_nofollow(
        Path(path),
        "reviewed authorization path",
        max_bytes=_REVIEWED_AUTHORIZATION_BYTE_CAP_V1,
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
        authorization["schema_version"] != _AUTHORIZATION_SCHEMA_VERSION
        or authorization["authorization_scope"] != _AUTHORIZATION_SCOPE
        or authorization["claim_boundary"] != _AUTHORIZATION_CLAIM_BOUNDARY
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
        except (RecursionError, UnicodeDecodeError, TraceValidationError) as error:
            raise DiagnosticAnalysisError(
                f"records.jsonl line {line_number} is not strict JSON"
            ) from error
        if type(parsed) is not dict:
            raise DiagnosticAnalysisError(
                f"records.jsonl line {line_number} is not a canonical object"
            )
        try:
            canonical = _canonical_bytes(parsed)
        except (
            RecursionError,
            TraceValidationError,
            TypeError,
            ValueError,
        ) as error:
            raise DiagnosticAnalysisError(
                f"records.jsonl line {line_number} is not a canonical object"
            ) from error
        if canonical != raw_line:
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
        or authorization["schema_version"] != _AUTHORIZATION_SCHEMA_VERSION
        or authorization["authorization_scope"] != _AUTHORIZATION_SCOPE
        or authorization["claim_boundary"] != _AUTHORIZATION_CLAIM_BOUNDARY
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
    artifact_receipt: _ArtifactReceipt = ()
    historical_attempt_path: Path | None = None
    attempt_state_receipt: _AttemptStateReceipt = ()
    historical_attempt_authority: _PinnedProtectedRoot | None = None


def _validate_artifact(
    artifact_dir: Path,
    bundle_dir: Path,
    authorization_path: Path,
    authorization_digest: str,
    *,
    repository_root: Path,
    attempt_authority_owner: ExitStack | None = None,
) -> _ValidatedRun:
    local_authority_cleanup = ExitStack()
    authority_cleanup = (
        attempt_authority_owner
        if attempt_authority_owner is not None
        else local_authority_cleanup
    )
    try:
        return _validate_artifact_unmanaged(
            artifact_dir,
            bundle_dir,
            authorization_path,
            authorization_digest,
            repository_root=repository_root,
            retain_historical_attempt_authority=(attempt_authority_owner is not None),
            authority_cleanup=authority_cleanup,
        )
    finally:
        local_authority_cleanup.close()


def _validate_artifact_unmanaged(
    artifact_dir: Path,
    bundle_dir: Path,
    authorization_path: Path,
    authorization_digest: str,
    *,
    repository_root: Path,
    retain_historical_attempt_authority: bool,
    authority_cleanup: ExitStack,
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
    historical_attempt_path = _historical_attempt_path(preflight_manifest)
    try:
        historical_attempt_roots = _pin_protected_roots((historical_attempt_path,))
    except DiagnosticAnalysisError as error:
        raise DiagnosticAnalysisError(
            "historical committed attempt must exist as a stable non-symlink directory"
        ) from error
    authority_cleanup.callback(
        _close_pinned_protected_roots,
        historical_attempt_roots,
    )
    _assert_pinned_protected_roots(historical_attempt_roots)
    attempt_state_receipt = _validate_historical_attempt_state_from_descriptor(
        historical_attempt_roots[0].descriptor,
        preflight_manifest,
    )
    _assert_pinned_protected_roots(historical_attempt_roots)
    try:
        bundle = verify_countdown_thompson_diagnostic_bundle(
            Path(bundle_dir),
            repository_root=repository,
        )
        expected_cells = iter_countdown_thompson_diagnostic_cells(bundle)
    except (OSError, RecursionError, TraceValidationError, ValueError) as error:
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
            max_bytes=_REVIEWED_AUTHORIZATION_BYTE_CAP_V1,
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
    _revalidate_attempt_authority_after_topology(
        historical_attempt_roots[0],
        attempt_state_receipt,
        historical_attempt_roots,
        "historical committed attempt",
    )
    retained_authority = (
        historical_attempt_roots[0] if retain_historical_attempt_authority else None
    )
    validated = _ValidatedRun(
        bundle,
        validated_rows,
        manifest,
        analyzer_build_digest,
        _artifact_snapshot_receipt(first_snapshot),
        historical_attempt_path,
        attempt_state_receipt,
        retained_authority,
    )
    return validated


def _validated_historical_attempt_authority(
    validated: _ValidatedRun,
) -> tuple[_PinnedProtectedRoot, _AttemptStateReceipt]:
    attempt_authority = getattr(
        validated,
        "historical_attempt_authority",
        None,
    )
    if type(attempt_authority) is not _PinnedProtectedRoot:
        raise DiagnosticAnalysisError(
            "validated historical committed attempt authority is unavailable"
        )
    attempt_path_value = getattr(validated, "historical_attempt_path", None)
    expected_attempt_path = _historical_attempt_path(validated.manifest)
    if (
        not isinstance(attempt_path_value, Path)
        or Path(os.path.abspath(os.fspath(attempt_path_value))) != expected_attempt_path
        or attempt_authority.authority_path != expected_attempt_path
    ):
        raise DiagnosticAnalysisError(
            "validated historical committed attempt path is unavailable"
        )
    receipt = _validated_attempt_state_receipt(
        getattr(validated, "attempt_state_receipt", ()),
        "validated historical committed attempt",
    )
    return attempt_authority, receipt


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

    with ExitStack() as authority_cleanup:
        source_roots = _pin_protected_roots(
            (Path(artifact_dir), Path(bundle_dir)),
        )
        authority_cleanup.callback(
            _close_pinned_protected_roots,
            source_roots,
        )
        artifact_authority, bundle_authority = source_roots
        bundle_receipt, bundle_validation_generation = (
            _capture_bundle_validation_baseline(
                bundle_authority,
                source_roots,
            )
        )
        _assert_pinned_protected_roots(source_roots)
        validated = _validate_artifact(
            Path(artifact_dir),
            Path(bundle_dir),
            Path(authorization_path),
            authorization_digest,
            repository_root=repository_root,
            attempt_authority_owner=authority_cleanup,
        )
        _assert_pinned_protected_roots(source_roots)
        validated_artifact_receipt = _validated_artifact_receipt(
            getattr(validated, "artifact_receipt", ()),
            "validated runner artifact",
        )
        attempt_authority, attempt_receipt = _validated_historical_attempt_authority(
            validated
        )
        summary = _build_summary(validated)
        protected_roots = (*source_roots, attempt_authority)
        authority_specs = (
            (
                artifact_authority,
                RUN_ARTIFACT_FILENAMES,
                "validated runner artifact",
            ),
            (
                bundle_authority,
                BUNDLE_FILENAMES,
                "verified diagnostic bundle",
            ),
            (
                attempt_authority,
                _COMMITTED_ATTEMPT_FILENAMES,
                "historical committed attempt",
            ),
        )
        before_generation = _capture_pinned_authority_generation(
            authority_specs,
            protected_roots,
        )
        if before_generation[1] != bundle_validation_generation:
            raise DiagnosticAnalysisError(
                "source authority generation changed after validation: "
                "diagnostic bundle"
            )
        _read_artifact_receipt_from_descriptor(
            artifact_authority.descriptor,
            "validated runner artifact",
            validated_artifact_receipt,
        )
        _read_bundle_receipt_from_descriptor(
            bundle_authority.descriptor,
            "verified diagnostic bundle",
            bundle_receipt,
        )
        _revalidate_attempt_authority_after_topology(
            attempt_authority,
            attempt_receipt,
            protected_roots,
            "historical committed attempt",
        )
        after_generation = _capture_pinned_authority_generation(
            authority_specs,
            protected_roots,
        )
        if after_generation != before_generation:
            raise DiagnosticAnalysisError(
                "artifact, bundle, and attempt authorities changed during "
                "collective proof"
            )
        if after_generation[1] != bundle_validation_generation:
            raise DiagnosticAnalysisError(
                "source authority generation changed after validation: "
                "diagnostic bundle"
            )
        _assert_pinned_protected_roots(protected_roots)
        return summary


def _open_stable_directory_with_ancestry(
    path: Path,
    label: str,
) -> tuple[int, os.stat_result, frozenset[tuple[int, int]]]:
    """Open every absolute path component with O_NOFOLLOW from the root fd."""

    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise DiagnosticAnalysisError(
            f"{label} requires POSIX descriptor-bound path traversal"
        )
    absolute = Path(os.path.abspath(os.fspath(path)))
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW
    directory_fd = -1
    try:
        directory_fd = os.open(absolute.anchor, flags)
        opened = os.fstat(directory_fd)
        if not stat.S_ISDIR(opened.st_mode):
            raise DiagnosticAnalysisError(f"{label} must be a regular directory")
        ancestry = {(opened.st_dev, opened.st_ino)}
        for component in absolute.parts[1:]:
            next_fd = -1
            try:
                next_fd = os.open(component, flags, dir_fd=directory_fd)
                next_opened = os.fstat(next_fd)
                if not stat.S_ISDIR(next_opened.st_mode):
                    raise DiagnosticAnalysisError(
                        f"{label} must be a regular directory"
                    )
            except BaseException:
                if next_fd >= 0:
                    try:
                        os.close(next_fd)
                    except BaseException:
                        pass
                raise
            try:
                os.close(directory_fd)
            except BaseException:
                pass
            directory_fd = next_fd
            opened = next_opened
            ancestry.add((opened.st_dev, opened.st_ino))
        return directory_fd, opened, frozenset(ancestry)
    except DiagnosticAnalysisError:
        if directory_fd >= 0:
            try:
                os.close(directory_fd)
            except BaseException:
                pass
        raise
    except OSError as error:
        if directory_fd >= 0:
            try:
                os.close(directory_fd)
            except BaseException:
                pass
        raise DiagnosticAnalysisError(f"{label} must be a stable directory") from error
    except BaseException:
        if directory_fd >= 0:
            try:
                os.close(directory_fd)
            except BaseException:
                pass
        raise


def _open_stable_directory(path: Path, label: str) -> tuple[int, os.stat_result]:
    directory_fd, opened, _ancestry = _open_stable_directory_with_ancestry(
        Path(path),
        label,
    )
    return directory_fd, opened


def _assert_raw_directory_identity(
    path: Path,
    expected_identity: tuple[int, int],
    label: str,
) -> None:
    """Prove one lexical raw directory name still reaches its pinned inode."""

    descriptor = -1
    try:
        descriptor, opened = _open_stable_directory(path, label)
        if (opened.st_dev, opened.st_ino) != expected_identity:
            raise DiagnosticAnalysisError(f"{label} path identity changed")
    finally:
        _close_descriptor_best_effort(descriptor)


@dataclass(frozen=True)
class _PinnedProtectedRoot:
    authority_path: Path
    path: Path
    descriptor: int
    identity: tuple[int, int]


def _open_protected_root_authority(
    path: Path,
    label: str,
) -> tuple[int, os.stat_result]:
    """Atomically acquire one directory inode from an unresolved absolute path."""

    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise DiagnosticAnalysisError(
            f"{label} requires POSIX descriptor-bound path traversal"
        )
    absolute = Path(os.path.abspath(os.fspath(path)))
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW
    descriptor = -1
    try:
        descriptor = os.open(absolute, flags)
        opened = os.fstat(descriptor)
        if not stat.S_ISDIR(opened.st_mode):
            raise DiagnosticAnalysisError(f"{label} must be a regular directory")
        return descriptor, opened
    except DiagnosticAnalysisError:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except BaseException:
                pass
        raise
    except OSError as error:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except BaseException:
                pass
        raise DiagnosticAnalysisError(f"{label} must be a stable directory") from error
    except BaseException:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except BaseException:
                pass
        raise


def _pin_protected_roots(
    protected_roots: Sequence[Path],
) -> tuple[_PinnedProtectedRoot, ...]:
    """Acquire protected-root authority before validation or destination lookup."""

    pinned: list[_PinnedProtectedRoot] = []
    try:
        for index, raw_root in enumerate(protected_roots):
            # Do not resolve first: this single open is the authority acquisition.
            # A separate resolve/open pair would admit an inode swap.  Ancestor
            # aliases such as macOS /var remain usable; O_NOFOLLOW closes the final
            # component. Retain the raw name for revalidation and the canonical
            # path for containment checks.
            root = Path(os.path.abspath(os.fspath(raw_root)))
            root_fd = -1
            try:
                root_fd, root_stat = _open_protected_root_authority(
                    root,
                    f"protected root {index} authority",
                )
                root_identity = (root_stat.st_dev, root_stat.st_ino)
                canonical = root.resolve()
                canonical_fd = -1
                try:
                    canonical_fd, canonical_stat = _open_protected_root_authority(
                        canonical,
                        f"protected root {index} authority resolution",
                    )
                    if (canonical_stat.st_dev, canonical_stat.st_ino) != root_identity:
                        raise DiagnosticAnalysisError(
                            f"protected root {index} changed during authority acquisition"
                        )
                finally:
                    if canonical_fd >= 0:
                        try:
                            os.close(canonical_fd)
                        except BaseException:
                            pass
                pinned.append(
                    _PinnedProtectedRoot(
                        authority_path=root,
                        path=canonical,
                        descriptor=root_fd,
                        identity=root_identity,
                    )
                )
                root_fd = -1
            finally:
                if root_fd >= 0:
                    try:
                        os.close(root_fd)
                    except BaseException:
                        pass
        return tuple(pinned)
    except BaseException:
        for protected in pinned:
            try:
                os.close(protected.descriptor)
            except BaseException:
                pass
        raise


def _close_pinned_protected_roots(
    protected_roots: Sequence[_PinnedProtectedRoot],
) -> None:
    for protected in protected_roots:
        try:
            os.close(protected.descriptor)
        except BaseException:
            pass


def _assert_pinned_protected_roots(
    protected_roots: Sequence[_PinnedProtectedRoot],
) -> None:
    """Prove each raw protected name still names its pinned authority inode."""

    for index, protected in enumerate(protected_roots):
        if type(protected) is not _PinnedProtectedRoot:
            raise DiagnosticAnalysisError(
                "summary publication requires pinned protected-root authority"
            )
        pinned = os.fstat(protected.descriptor)
        pinned_identity = (pinned.st_dev, pinned.st_ino)
        if not stat.S_ISDIR(pinned.st_mode) or pinned_identity != protected.identity:
            raise DiagnosticAnalysisError(
                f"protected root {index} pinned identity changed"
            )
        current_fd = -1
        try:
            current_fd, current = _open_protected_root_authority(
                protected.authority_path,
                f"protected root {index} after pinning",
            )
            if (current.st_dev, current.st_ino) != protected.identity:
                raise DiagnosticAnalysisError(
                    f"protected root {index} path identity changed"
                )
        finally:
            if current_fd >= 0:
                try:
                    os.close(current_fd)
                except BaseException:
                    pass


_PathGeneration = tuple[tuple[str, tuple[int, ...]], ...]
_AuthorityDirectoryGeneration = tuple[
    _PathGeneration,
    _PathGeneration,
    tuple[int, ...],
    tuple[tuple[str, tuple[int, ...]], ...],
]
_AuthorityGeneration = tuple[_AuthorityDirectoryGeneration, ...]


def _directory_stable_state(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _capture_raw_path_generation(
    path: Path,
    expected_identity: tuple[int, int],
    label: str,
) -> _PathGeneration:
    """Capture every lexical path component plus the final target identity."""

    absolute = Path(os.path.abspath(os.fspath(path)))
    current = Path(absolute.anchor)
    captured: list[tuple[str, tuple[int, ...]]] = []
    descriptor = -1
    try:
        captured.append(
            (
                os.fspath(current),
                _directory_stable_state(os.lstat(current)),
            )
        )
        for component in absolute.parts[1:]:
            current /= component
            captured.append(
                (
                    os.fspath(current),
                    _directory_stable_state(os.lstat(current)),
                )
            )
        descriptor, opened = _open_protected_root_authority(
            absolute,
            label,
        )
        if (opened.st_dev, opened.st_ino) != expected_identity:
            raise DiagnosticAnalysisError(f"{label} path identity changed")
        return tuple(captured)
    except DiagnosticAnalysisError:
        raise
    except OSError as error:
        raise DiagnosticAnalysisError(f"{label} path generation changed") from error
    finally:
        _close_descriptor_best_effort(descriptor)


_ProtectedPathGeneration = tuple[_PathGeneration, _PathGeneration]


def _capture_protected_path_generations(
    protected_roots: Sequence[_PinnedProtectedRoot],
) -> tuple[_ProtectedPathGeneration, ...]:
    """Capture raw and canonical namespace generations for every source root."""

    return tuple(
        (
            _capture_raw_path_generation(
                protected.authority_path,
                protected.identity,
                f"protected root {index} raw authority",
            ),
            _capture_raw_path_generation(
                protected.path,
                protected.identity,
                f"protected root {index} canonical authority",
            ),
        )
        for index, protected in enumerate(protected_roots)
    )


def _path_generation_identities(
    generations: Sequence[_ProtectedPathGeneration],
) -> frozenset[tuple[int, int]]:
    """Return every inode identity named by raw and canonical source paths."""

    return frozenset(
        (state[0], state[1])
        for raw_generation, canonical_generation in generations
        for generation in (raw_generation, canonical_generation)
        for _path, state in generation
    )


def _capture_pinned_authority_generation(
    authorities: Sequence[tuple[_PinnedProtectedRoot, tuple[str, ...], str]],
    protected_roots: Sequence[_PinnedProtectedRoot],
) -> _AuthorityGeneration:
    """Capture one non-ABA namespace/member generation for each authority.

    The receipt readers prove expected bytes. This companion token binds
    those proofs across independently mutable directories: under the existing
    POSIX stable-state assumption, an in-place write, replacement, or link
    change advances at least one mtime/ctime-bearing generation component.
    """

    _assert_pinned_protected_roots(protected_roots)
    captured: list[_AuthorityDirectoryGeneration] = []
    try:
        for authority, filenames, label in authorities:
            raw_path_generation = _capture_raw_path_generation(
                authority.authority_path,
                authority.identity,
                f"{label} raw authority",
            )
            canonical_path_generation = _capture_raw_path_generation(
                authority.path,
                authority.identity,
                f"{label} canonical authority",
            )
            before_directory = os.fstat(authority.descriptor)
            if not stat.S_ISDIR(before_directory.st_mode):
                raise DiagnosticAnalysisError(f"{label} must be a regular directory")
            expected_names = set(filenames)
            with os.scandir(authority.descriptor) as entries:
                observed_names = tuple(entry.name for entry in entries)
            if (
                len(observed_names) != len(expected_names)
                or set(observed_names) != expected_names
            ):
                raise DiagnosticAnalysisError(f"{label} directory closure drifted")

            member_states: list[tuple[str, tuple[int, ...]]] = []
            for filename in filenames:
                observed = os.stat(
                    filename,
                    dir_fd=authority.descriptor,
                    follow_symlinks=False,
                )
                if not stat.S_ISREG(observed.st_mode):
                    raise DiagnosticAnalysisError(
                        f"{label} member is not regular: {filename}"
                    )
                member_states.append(
                    (filename, _artifact_member_stable_state(observed))
                )

            after_directory = os.fstat(authority.descriptor)
            directory_generation = _directory_stable_state(before_directory)
            if _directory_stable_state(after_directory) != directory_generation:
                raise DiagnosticAnalysisError(
                    f"{label} directory changed during generation capture"
                )
            for filename, expected_state in member_states:
                reobserved = os.stat(
                    filename,
                    dir_fd=authority.descriptor,
                    follow_symlinks=False,
                )
                if (
                    not stat.S_ISREG(reobserved.st_mode)
                    or _artifact_member_stable_state(reobserved) != expected_state
                ):
                    raise DiagnosticAnalysisError(
                        f"{label} member changed during generation capture: {filename}"
                    )
            if (
                _capture_raw_path_generation(
                    authority.authority_path,
                    authority.identity,
                    f"{label} raw authority",
                )
                != raw_path_generation
                or _capture_raw_path_generation(
                    authority.path,
                    authority.identity,
                    f"{label} canonical authority",
                )
                != canonical_path_generation
            ):
                raise DiagnosticAnalysisError(
                    f"{label} path changed during generation capture"
                )
            captured.append(
                (
                    raw_path_generation,
                    canonical_path_generation,
                    directory_generation,
                    tuple(member_states),
                )
            )
    except DiagnosticAnalysisError:
        raise
    except OSError as error:
        raise DiagnosticAnalysisError(
            "authority generation could not be captured"
        ) from error
    _assert_pinned_protected_roots(protected_roots)
    return tuple(captured)


def _capture_bundle_validation_baseline(
    bundle_authority: _PinnedProtectedRoot,
    protected_roots: Sequence[_PinnedProtectedRoot],
) -> tuple[_BundleReceipt, _AuthorityDirectoryGeneration]:
    """Bind exact bundle bytes to one raw/canonical pre-validation generation."""

    bundle_specs = (
        (
            bundle_authority,
            BUNDLE_FILENAMES,
            "verified diagnostic bundle",
        ),
    )
    before_generation = _capture_pinned_authority_generation(
        bundle_specs,
        protected_roots,
    )
    receipt = _read_bundle_receipt_from_descriptor(
        bundle_authority.descriptor,
        "verified diagnostic bundle",
    )
    after_generation = _capture_pinned_authority_generation(
        bundle_specs,
        protected_roots,
    )
    if after_generation != before_generation:
        raise DiagnosticAnalysisError(
            "diagnostic bundle changed during pre-validation collective proof"
        )
    return receipt, after_generation[0]


def _directory_ancestry_from_fd(
    directory_fd: int,
    label: str,
) -> frozenset[tuple[int, int]]:
    """Walk the directory's current real parents through descriptor-relative .. ."""

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW
    current_fd = -1
    try:
        current_fd = os.dup(directory_fd)
        ancestry: set[tuple[int, int]] = set()
        for _depth in range(4096):
            current = os.fstat(current_fd)
            if not stat.S_ISDIR(current.st_mode):
                raise DiagnosticAnalysisError(f"{label} is not a directory")
            current_identity = (current.st_dev, current.st_ino)
            if current_identity in ancestry:
                raise DiagnosticAnalysisError(f"{label} ancestry contains a cycle")
            ancestry.add(current_identity)
            parent_fd = os.open("..", flags, dir_fd=current_fd)
            try:
                parent = os.fstat(parent_fd)
                if not stat.S_ISDIR(parent.st_mode):
                    raise DiagnosticAnalysisError(f"{label} parent is not a directory")
                parent_identity = (parent.st_dev, parent.st_ino)
                if parent_identity == current_identity:
                    try:
                        os.close(parent_fd)
                    except BaseException:
                        pass
                    return frozenset(ancestry)
            except BaseException:
                try:
                    os.close(parent_fd)
                except BaseException:
                    pass
                raise
            try:
                os.close(current_fd)
            except BaseException:
                pass
            current_fd = parent_fd
        raise DiagnosticAnalysisError(f"{label} ancestry exceeds the safety bound")
    except DiagnosticAnalysisError:
        raise
    except OSError as error:
        raise DiagnosticAnalysisError(f"{label} ancestry is unavailable") from error
    finally:
        if current_fd >= 0:
            try:
                os.close(current_fd)
            except BaseException:
                pass


def _assert_summary_publication_topology(
    parent_fd: int,
    protected_roots: Sequence[_PinnedProtectedRoot],
    *,
    publication_may_exist: bool,
) -> None:
    """Bind the parent's current real ancestry to still-pinned protected roots."""

    if not protected_roots:
        return
    try:
        parent = os.fstat(parent_fd)
        if not stat.S_ISDIR(parent.st_mode):
            raise DiagnosticAnalysisError("summary parent is not a directory")
        parent_identity = (parent.st_dev, parent.st_ino)
        protected_identities = {protected.identity for protected in protected_roots}
        ancestry_before = _directory_ancestry_from_fd(parent_fd, "summary parent")
        if protected_identities.intersection(ancestry_before):
            raise DiagnosticAnalysisError(
                "summary parent real ancestry intersects a protected root"
            )
        protected_paths_before = _capture_protected_path_generations(protected_roots)
        if parent_identity in _path_generation_identities(protected_paths_before):
            raise DiagnosticAnalysisError(
                "summary parent is a protected source-path ancestor"
            )
        _assert_pinned_protected_roots(protected_roots)
        ancestry_after = _directory_ancestry_from_fd(parent_fd, "summary parent")
        protected_paths_after = _capture_protected_path_generations(protected_roots)
        if ancestry_after != ancestry_before:
            raise DiagnosticAnalysisError(
                "summary parent real ancestry changed during topology proof"
            )
        if protected_paths_after != protected_paths_before:
            raise DiagnosticAnalysisError(
                "protected source paths changed during topology proof"
            )
        if protected_identities.intersection(ancestry_after):
            raise DiagnosticAnalysisError(
                "summary parent real ancestry intersects a protected root"
            )
        if parent_identity in _path_generation_identities(protected_paths_after):
            raise DiagnosticAnalysisError(
                "summary parent is a protected source-path ancestor"
            )
    except DiagnosticAnalysisPublicationAmbiguousError:
        raise
    except BaseException as error:
        if publication_may_exist:
            raise DiagnosticAnalysisPublicationAmbiguousError(
                "summary publication topology is ambiguous; the destination "
                "must not be used as diagnostic evidence"
            ) from error
        if isinstance(error, DiagnosticAnalysisError):
            raise
        raise DiagnosticAnalysisError(
            "summary publication topology could not be proven"
        ) from error


_SUMMARY_ENTRY_ABSENT = "ABSENT"
_SUMMARY_ENTRY_EXACT = "EXACT"
_SUMMARY_ENTRY_OTHER = "OTHER"


def _summary_inode_stable_state(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _read_exact_bounded_summary_payload(
    descriptor: int,
    expected_size: int,
) -> tuple[bytes, bool]:
    """Read at most expected_size plus one EOF-probe byte."""

    remaining = expected_size
    chunks: list[bytes] = []
    while remaining:
        chunk = os.read(descriptor, remaining)
        if not chunk:
            break
        remaining -= len(chunk)
        chunks.append(chunk)
    extra = bool(os.read(descriptor, 1))
    return b"".join(chunks), extra


def _summary_entry_state(
    directory_fd: int,
    filename: str,
    staged_identity: tuple[int, int],
    expected_payload: bytes,
) -> str:
    """Observe one entry by descriptor, including its exact expected bytes."""

    try:
        named_before = os.stat(
            filename,
            dir_fd=directory_fd,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return _SUMMARY_ENTRY_ABSENT
    except OSError as error:
        raise DiagnosticAnalysisPublicationAmbiguousError(
            f"summary entry could not be observed: {filename}"
        ) from error
    if (
        not stat.S_ISREG(named_before.st_mode)
        or (named_before.st_dev, named_before.st_ino) != staged_identity
        or named_before.st_size != len(expected_payload)
    ):
        return _SUMMARY_ENTRY_OTHER

    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    try:
        descriptor = os.open(filename, flags, dir_fd=directory_fd)
    except FileNotFoundError:
        return _SUMMARY_ENTRY_ABSENT
    except OSError as error:
        raise DiagnosticAnalysisPublicationAmbiguousError(
            f"summary entry could not be observed: {filename}"
        ) from error
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or (opened.st_dev, opened.st_ino) != staged_identity
            or opened.st_size != len(expected_payload)
            or _summary_inode_stable_state(opened)
            != _summary_inode_stable_state(named_before)
        ):
            return _SUMMARY_ENTRY_OTHER
        os.lseek(descriptor, 0, os.SEEK_SET)
        observed_payload, has_extra = _read_exact_bounded_summary_payload(
            descriptor,
            len(expected_payload),
        )
        after = os.fstat(descriptor)
        try:
            named_after = os.stat(
                filename,
                dir_fd=directory_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            return _SUMMARY_ENTRY_OTHER
        except OSError as error:
            raise DiagnosticAnalysisPublicationAmbiguousError(
                f"summary entry could not be reobserved: {filename}"
            ) from error
        if (
            not stat.S_ISREG(after.st_mode)
            or (after.st_dev, after.st_ino) != staged_identity
            or after.st_size != len(expected_payload)
            or _summary_inode_stable_state(after) != _summary_inode_stable_state(opened)
            or _summary_inode_stable_state(named_after)
            != _summary_inode_stable_state(opened)
            or has_extra
            or observed_payload != expected_payload
        ):
            return _SUMMARY_ENTRY_OTHER
        return _SUMMARY_ENTRY_EXACT
    except OSError as error:
        raise DiagnosticAnalysisPublicationAmbiguousError(
            f"summary entry could not be read: {filename}"
        ) from error
    finally:
        try:
            os.close(descriptor)
        except BaseException:
            pass


def _pinned_summary_inode_state(
    descriptor: int,
    staged_identity: tuple[int, int],
    expected_payload: bytes,
) -> tuple[str, int]:
    """Observe whether the staged inode still has an exact named link."""

    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or (before.st_dev, before.st_ino) != staged_identity
            or before.st_size != len(expected_payload)
        ):
            return _SUMMARY_ENTRY_OTHER, before.st_nlink
        expected_state = _summary_inode_stable_state(before)
        for _pass in range(2):
            os.lseek(descriptor, 0, os.SEEK_SET)
            observed_payload, has_extra = _read_exact_bounded_summary_payload(
                descriptor,
                len(expected_payload),
            )
            after = os.fstat(descriptor)
            if (
                _summary_inode_stable_state(after) != expected_state
                or observed_payload != expected_payload
                or has_extra
            ):
                return _SUMMARY_ENTRY_OTHER, after.st_nlink
    except BaseException as error:
        raise DiagnosticAnalysisPublicationAmbiguousError(
            "pinned summary inode could not be observed"
        ) from error
    if after.st_nlink == 0:
        return _SUMMARY_ENTRY_ABSENT, 0
    return _SUMMARY_ENTRY_EXACT, after.st_nlink


def _summary_publication_state(
    destination: Path,
    parent_fd: int,
    parent_identity: tuple[int, int],
    staged_identity: tuple[int, int],
    expected_payload: bytes,
) -> str:
    """Observe the requested path twice through the pinned and current parent."""

    pinned_state = _summary_entry_state(
        parent_fd,
        destination.name,
        staged_identity,
        expected_payload,
    )
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
            return _SUMMARY_ENTRY_OTHER
        current_state = _summary_entry_state(
            current_parent_fd,
            destination.name,
            staged_identity,
            expected_payload,
        )
        if current_state != pinned_state:
            return _SUMMARY_ENTRY_OTHER
        return current_state
    except DiagnosticAnalysisPublicationAmbiguousError:
        raise
    except DiagnosticAnalysisError as error:
        if isinstance(error.__cause__, OSError):
            raise DiagnosticAnalysisPublicationAmbiguousError(
                "summary parent could not be observed"
            ) from error
        return _SUMMARY_ENTRY_OTHER
    finally:
        if current_parent_fd >= 0:
            try:
                os.close(current_parent_fd)
            except BaseException:
                pass


def _summary_publication_is_exact(
    destination: Path,
    parent_fd: int,
    parent_identity: tuple[int, int],
    staged_identity: tuple[int, int],
    expected_payload: bytes,
) -> bool:
    return (
        _summary_publication_state(
            destination,
            parent_fd,
            parent_identity,
            staged_identity,
            expected_payload,
        )
        == _SUMMARY_ENTRY_EXACT
    )


def _rename_noreplace_at(
    directory_fd: int,
    source_name: str,
    destination_name: str,
) -> None:
    """Atomically rename within one pinned directory without replacement."""

    libc = ctypes.CDLL(None, use_errno=True)
    source = os.fsencode(source_name)
    destination = os.fsencode(destination_name)
    if sys.platform == "darwin":
        rename = libc.renameatx_np
        rename.argtypes = (
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        )
        rename.restype = ctypes.c_int
        result = rename(
            directory_fd,
            source,
            directory_fd,
            destination,
            0x00000004,
        )
    elif sys.platform.startswith("linux"):
        try:
            rename = libc.renameat2
        except AttributeError as error:
            raise OSError(
                errno.ENOSYS,
                "descriptor-bound atomic no-replace rename is unsupported",
                destination_name,
            ) from error
        rename.argtypes = (
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        )
        rename.restype = ctypes.c_int
        result = rename(
            directory_fd,
            source,
            directory_fd,
            destination,
            0x00000001,
        )
    else:
        raise OSError(
            errno.ENOSYS,
            "descriptor-bound atomic no-replace rename is unsupported",
            destination_name,
        )
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise FileExistsError(
            error_number,
            "destination exists",
            destination_name,
        )
    raise OSError(error_number, os.strerror(error_number), destination_name)


def _restore_foreign_summary_from_quarantine(
    destination: Path,
    parent_fd: int,
    parent_identity: tuple[int, int],
    protected_roots: Sequence[_PinnedProtectedRoot],
    quarantine_name: str,
    foreign_identity: tuple[int, int],
) -> None:
    """Restore the exact foreign inode moved by a raced rollback rename."""

    foreign_fd = -1
    current_parent_fd = -1
    try:
        if hasattr(os, "O_PATH"):
            capture_flags = os.O_PATH | os.O_NOFOLLOW | os.O_NONBLOCK
        elif hasattr(os, "O_SYMLINK"):
            # Darwin's O_SYMLINK opens the link inode itself. Combining it with
            # O_NOFOLLOW raises ELOOP, so the two platform contracts are kept
            # deliberately separate.
            capture_flags = os.O_SYMLINK | os.O_NONBLOCK
        else:
            capture_flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        foreign_fd = os.open(
            quarantine_name,
            capture_flags,
            dir_fd=parent_fd,
        )
        captured = os.fstat(foreign_fd)
        if (captured.st_dev, captured.st_ino) != foreign_identity:
            raise DiagnosticAnalysisPublicationAmbiguousError(
                "foreign summary replacement changed before restoration"
            )
        try:
            _rename_noreplace_at(
                parent_fd,
                quarantine_name,
                destination.name,
            )
        except BaseException as error:
            raise DiagnosticAnalysisPublicationAmbiguousError(
                "foreign summary replacement could not be restored without overwrite"
            ) from error
        os.fsync(parent_fd)
        _assert_summary_publication_topology(
            parent_fd,
            protected_roots,
            publication_may_exist=True,
        )
        retained = os.fstat(foreign_fd)
        pinned_destination = os.stat(
            destination.name,
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
        try:
            os.stat(
                quarantine_name,
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            pass
        else:
            raise DiagnosticAnalysisPublicationAmbiguousError(
                "foreign summary quarantine survived restoration"
            )
        current_parent_fd, current_parent = _open_stable_directory(
            destination.parent,
            "summary parent after foreign restoration",
        )
        if (current_parent.st_dev, current_parent.st_ino) != parent_identity:
            raise DiagnosticAnalysisPublicationAmbiguousError(
                "summary parent changed during foreign restoration"
            )
        current_destination = os.stat(
            destination.name,
            dir_fd=current_parent_fd,
            follow_symlinks=False,
        )
        observed_identities = {
            (retained.st_dev, retained.st_ino),
            (pinned_destination.st_dev, pinned_destination.st_ino),
            (current_destination.st_dev, current_destination.st_ino),
        }
        if observed_identities != {foreign_identity}:
            raise DiagnosticAnalysisPublicationAmbiguousError(
                "foreign summary replacement identity changed during restoration"
            )
    except DiagnosticAnalysisPublicationAmbiguousError:
        raise
    except BaseException as error:
        raise DiagnosticAnalysisPublicationAmbiguousError(
            "foreign summary replacement restoration is ambiguous"
        ) from error
    finally:
        _close_descriptor_best_effort(current_parent_fd)
        _close_descriptor_best_effort(foreign_fd)


def _durably_revoke_exact_summary(
    destination: Path,
    parent_fd: int,
    parent_identity: tuple[int, int],
    protected_roots: Sequence[_PinnedProtectedRoot],
    staged_fd: int,
    staged_identity: tuple[int, int],
    expected_payload: bytes,
) -> bool:
    """Move an exact summary to a retained quarantine and prove rollback."""

    _assert_summary_publication_topology(
        parent_fd,
        protected_roots,
        publication_may_exist=True,
    )
    state = _summary_publication_state(
        destination,
        parent_fd,
        parent_identity,
        staged_identity,
        expected_payload,
    )
    if state == _SUMMARY_ENTRY_ABSENT:
        os.fsync(parent_fd)
        _assert_summary_publication_topology(
            parent_fd,
            protected_roots,
            publication_may_exist=True,
        )
        return False
    if state != _SUMMARY_ENTRY_EXACT:
        return False

    for _attempt in range(128):
        quarantine_name = f".{destination.name}.rollback-{secrets.token_hex(16)}"
        try:
            _rename_noreplace_at(
                parent_fd,
                destination.name,
                quarantine_name,
            )
        except FileExistsError:
            continue
        except FileNotFoundError:
            os.fsync(parent_fd)
            _assert_summary_publication_topology(
                parent_fd,
                protected_roots,
                publication_may_exist=True,
            )
            return False
        os.fsync(parent_fd)
        _assert_summary_publication_topology(
            parent_fd,
            protected_roots,
            publication_may_exist=True,
        )
        try:
            quarantined_entry = os.stat(
                quarantine_name,
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
        except OSError as error:
            raise DiagnosticAnalysisPublicationAmbiguousError(
                "summary rollback quarantine could not be observed"
            ) from error
        quarantine_identity = (
            quarantined_entry.st_dev,
            quarantined_entry.st_ino,
        )
        if quarantine_identity != staged_identity:
            _restore_foreign_summary_from_quarantine(
                destination,
                parent_fd,
                parent_identity,
                protected_roots,
                quarantine_name,
                quarantine_identity,
            )
            return False
        destination_absent = (
            _summary_publication_state(
                destination,
                parent_fd,
                parent_identity,
                staged_identity,
                expected_payload,
            )
            == _SUMMARY_ENTRY_ABSENT
        )
        quarantine_exact = (
            _summary_publication_state(
                destination.with_name(quarantine_name),
                parent_fd,
                parent_identity,
                staged_identity,
                expected_payload,
            )
            == _SUMMARY_ENTRY_EXACT
        )
        pinned_state, pinned_link_count = _pinned_summary_inode_state(
            staged_fd,
            staged_identity,
            expected_payload,
        )
        _assert_summary_publication_topology(
            parent_fd,
            protected_roots,
            publication_may_exist=True,
        )
        return (
            destination_absent
            and quarantine_exact
            and pinned_state == _SUMMARY_ENTRY_EXACT
            and pinned_link_count == 1
        )
    return False


def _recover_summary_publication(
    destination: Path,
    parent_fd: int,
    parent_identity: tuple[int, int],
    protected_roots: Sequence[_PinnedProtectedRoot],
    staging_name: str,
    staged_fd: int,
    staged_identity: tuple[int, int],
    expected_payload: bytes,
    publication_observed_exact: bool,
    parent_barrier_completed: bool,
    primary_error: BaseException,
) -> bool:
    """Return True for a durable exact commit and False for durable rollback."""

    _assert_summary_publication_topology(
        parent_fd,
        protected_roots,
        publication_may_exist=True,
    )
    if isinstance(primary_error, DiagnosticAnalysisPublicationAmbiguousError):
        raise primary_error
    try:
        os.fsync(parent_fd)
        _assert_summary_publication_topology(
            parent_fd,
            protected_roots,
            publication_may_exist=True,
        )
        state = _summary_publication_state(
            destination,
            parent_fd,
            parent_identity,
            staged_identity,
            expected_payload,
        )
    except DiagnosticAnalysisPublicationAmbiguousError:
        raise
    except BaseException:
        state = _SUMMARY_ENTRY_OTHER
    else:
        if state == _SUMMARY_ENTRY_EXACT:
            _assert_summary_publication_topology(
                parent_fd,
                protected_roots,
                publication_may_exist=True,
            )
            if (
                _summary_publication_state(
                    destination,
                    parent_fd,
                    parent_identity,
                    staged_identity,
                    expected_payload,
                )
                != _SUMMARY_ENTRY_EXACT
            ):
                raise DiagnosticAnalysisPublicationAmbiguousError(
                    "summary publication durability and rollback are ambiguous; "
                    "the destination must not be used as diagnostic evidence"
                ) from primary_error
            return True
        if state == _SUMMARY_ENTRY_ABSENT:
            staging_state = _summary_entry_state(
                parent_fd,
                staging_name,
                staged_identity,
                expected_payload,
            )
            pinned_state, pinned_link_count = _pinned_summary_inode_state(
                staged_fd,
                staged_identity,
                expected_payload,
            )
            if (
                publication_observed_exact or parent_barrier_completed
            ) and pinned_link_count > 0:
                raise DiagnosticAnalysisPublicationAmbiguousError(
                    "summary publication durability and rollback are ambiguous; "
                    "the destination must not be used as diagnostic evidence"
                ) from primary_error
            if (
                staging_state == _SUMMARY_ENTRY_EXACT
                and pinned_state == _SUMMARY_ENTRY_EXACT
                and pinned_link_count == 1
            ):
                return False
            if (
                staging_state != _SUMMARY_ENTRY_EXACT
                and pinned_state != _SUMMARY_ENTRY_EXACT
            ):
                return False
            raise DiagnosticAnalysisPublicationAmbiguousError(
                "summary publication durability and rollback are ambiguous; "
                "the destination must not be used as diagnostic evidence"
            ) from primary_error

    try:
        if _durably_revoke_exact_summary(
            destination,
            parent_fd,
            parent_identity,
            protected_roots,
            staged_fd,
            staged_identity,
            expected_payload,
        ):
            return False
    except DiagnosticAnalysisPublicationAmbiguousError:
        raise
    except BaseException:
        raise DiagnosticAnalysisPublicationAmbiguousError(
            "summary publication durability and rollback are ambiguous; "
            "the destination must not be used as diagnostic evidence"
        ) from primary_error
    raise DiagnosticAnalysisPublicationAmbiguousError(
        "summary publication durability and rollback are ambiguous; "
        "the destination must not be used as diagnostic evidence"
    ) from primary_error


def _atomic_write_no_replace(
    path: Path,
    payload: bytes,
    *,
    protected_roots: Sequence[_PinnedProtectedRoot] = (),
    post_durability_check: Callable[[], None] | None = None,
) -> None:
    if os.name != "posix":
        raise DiagnosticAnalysisError(
            "descriptor-bound no-overwrite publication requires POSIX"
        )
    requested_destination = Path(os.path.abspath(os.fspath(path)))
    if not requested_destination.name:
        raise DiagnosticAnalysisError("summary destination filename is empty")
    _strict_json_object(payload, "summary publication payload")
    destination = requested_destination
    pinned_protected_roots = tuple(protected_roots)
    parent_fd = -1
    parent_identity: tuple[int, int] | None = None
    file_descriptor = -1
    staging_name = ""
    staged_identity: tuple[int, int] | None = None
    rename_attempted = False
    publication_observed_exact = False
    parent_barrier_completed = False
    post_durability_check_failed = False
    post_durability_check_completed = post_durability_check is None

    def raise_after_failed_post_durability_check(
        check_error: BaseException,
    ) -> None:
        """Revoke an exact summary, then report one typed INVALID failure."""

        if (
            staged_identity is None
            or parent_identity is None
            or parent_fd < 0
            or file_descriptor < 0
        ):
            raise DiagnosticAnalysisPublicationAmbiguousError(
                "summary publication durability and rollback are ambiguous; "
                "the destination must not be used as diagnostic evidence"
            ) from check_error
        try:
            revoked = _durably_revoke_exact_summary(
                destination,
                parent_fd,
                parent_identity,
                pinned_protected_roots,
                file_descriptor,
                staged_identity,
                payload,
            )
        except DiagnosticAnalysisPublicationAmbiguousError:
            raise
        except BaseException:
            raise DiagnosticAnalysisPublicationAmbiguousError(
                "summary publication durability and rollback are ambiguous; "
                "the destination must not be used as diagnostic evidence"
            ) from check_error
        if revoked:
            raise DiagnosticAnalysisError(
                "mandatory summary post-durability check failed after exact "
                f"durable rollback: {type(check_error).__name__}: {check_error}"
            ) from check_error
        raise DiagnosticAnalysisPublicationAmbiguousError(
            "summary publication durability and rollback are ambiguous; "
            "the destination must not be used as diagnostic evidence"
        ) from check_error

    def run_mandatory_post_durability_check() -> None:
        nonlocal post_durability_check_completed, post_durability_check_failed

        if post_durability_check is None:
            post_durability_check_completed = True
            return
        try:
            post_durability_check()
        except BaseException:
            post_durability_check_failed = True
            raise
        post_durability_check_completed = True

    def observe_exact_summary_generation() -> tuple[
        _PathGeneration,
        tuple[int, ...],
        tuple[int, ...],
    ]:
        """Bind one exact payload proof to parent and inode generations."""

        if (
            staged_identity is None
            or parent_identity is None
            or parent_fd < 0
            or file_descriptor < 0
        ):
            raise DiagnosticAnalysisPublicationAmbiguousError(
                "summary publication durability and rollback are ambiguous; "
                "the destination must not be used as diagnostic evidence"
            )
        parent_before = os.fstat(parent_fd)
        inode_before = os.fstat(file_descriptor)
        parent_path_generation = _capture_raw_path_generation(
            destination.parent,
            parent_identity,
            "summary parent authority",
        )
        parent_generation = _directory_stable_state(parent_before)
        inode_generation = _summary_inode_stable_state(inode_before)
        _assert_raw_directory_identity(
            destination.parent,
            parent_identity,
            "summary parent during mandatory post-durability check",
        )
        if not _summary_publication_is_exact(
            destination,
            parent_fd,
            parent_identity,
            staged_identity,
            payload,
        ):
            raise DiagnosticAnalysisError(
                "summary destination changed during mandatory post-durability proof"
            )
        inode_after = os.fstat(file_descriptor)
        parent_after = os.fstat(parent_fd)
        if (
            _summary_inode_stable_state(inode_after) != inode_generation
            or _directory_stable_state(parent_after) != parent_generation
        ):
            raise DiagnosticAnalysisError(
                "summary destination generation changed during mandatory proof"
            )
        if (
            _capture_raw_path_generation(
                destination.parent,
                parent_identity,
                "summary parent authority",
            )
            != parent_path_generation
        ):
            raise DiagnosticAnalysisError(
                "summary parent path changed during mandatory proof"
            )
        _assert_raw_directory_identity(
            destination.parent,
            parent_identity,
            "summary parent after mandatory post-durability check",
        )
        return parent_path_generation, parent_generation, inode_generation

    def complete_mandatory_commit_check() -> None:
        nonlocal post_durability_check_failed

        try:
            # S0 is captured by the caller before publication. D0 is captured
            # here after the directory durability barrier, then the mandatory
            # callback rechecks S0 and the final observations recheck D0. With
            # non-ABA mtime/ctime generations, S0-D0-S1-D1 contains a real
            # interval in which source authorities and destination are exact.
            pre_sync_generation = observe_exact_summary_generation()
            os.fsync(file_descriptor)
            durable_generation = observe_exact_summary_generation()
            if durable_generation != pre_sync_generation:
                raise DiagnosticAnalysisError(
                    "summary destination changed during final file durability barrier"
                )
            run_mandatory_post_durability_check()
            for _observation in range(2):
                if observe_exact_summary_generation() != durable_generation:
                    raise DiagnosticAnalysisError(
                        "summary destination generation changed after mandatory "
                        "post-durability check"
                    )
        except BaseException:
            post_durability_check_failed = True
            raise

    try:
        # These descriptors were acquired before validation.  Revalidate their
        # names before touching any attacker-pivotable destination path.
        _assert_pinned_protected_roots(pinned_protected_roots)
        # Keep the lexical absolute namespace supplied by the caller.  Opening
        # its raw parent component-by-component rejects every symlink component
        # instead of resolving an alias and silently publishing elsewhere.
        destination = requested_destination
        parent_fd, parent_stat, _parent_ancestry = _open_stable_directory_with_ancestry(
            destination.parent,
            "summary parent",
        )
        parent_identity = (parent_stat.st_dev, parent_stat.st_ino)
        # Re-open the lexical name after authority acquisition.  This closes an
        # ancestor pivot performed immediately after the component walk before
        # even a staging inode can be allocated.
        _assert_raw_directory_identity(
            destination.parent,
            parent_identity,
            "summary parent after authority acquisition",
        )
        _assert_summary_publication_topology(
            parent_fd,
            pinned_protected_roots,
            publication_may_exist=False,
        )
        try:
            os.stat(
                destination.name,
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            pass
        except OSError as error:
            raise DiagnosticAnalysisPublicationAmbiguousError(
                "summary destination initial state could not be observed"
            ) from error
        else:
            raise FileExistsError(f"summary destination exists: {destination}")

        _assert_summary_publication_topology(
            parent_fd,
            pinned_protected_roots,
            publication_may_exist=False,
        )
        for _attempt in range(128):
            candidate = f".{destination.name}.staging-{secrets.token_hex(16)}.retained"
            try:
                file_descriptor = os.open(
                    candidate,
                    os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_NONBLOCK,
                    0o600,
                    dir_fd=parent_fd,
                )
            except FileExistsError:
                continue
            staging_name = candidate
            break
        if file_descriptor < 0:
            raise DiagnosticAnalysisError(
                "could not allocate exclusive summary staging"
            )
        with os.fdopen(file_descriptor, "wb", closefd=False) as handle:
            staged = os.fstat(handle.fileno())
            staged_identity = (staged.st_dev, staged.st_ino)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        _assert_summary_publication_topology(
            parent_fd,
            pinned_protected_roots,
            publication_may_exist=False,
        )
        # A successful no-replace rename consumes the staging name. If the
        # rename does not happen, leave staging untouched rather than deleting
        # a possibly replaced name.
        _assert_summary_publication_topology(
            parent_fd,
            pinned_protected_roots,
            publication_may_exist=False,
        )
        rename_attempted = True
        try:
            _rename_noreplace_at(
                parent_fd,
                staging_name,
                destination.name,
            )
        except FileExistsError:
            raise
        except OSError as error:
            raise DiagnosticAnalysisError(
                "atomic no-overwrite summary publication is unavailable"
            ) from error
        if not _summary_publication_is_exact(
            destination,
            parent_fd,
            parent_identity,
            staged_identity,
            payload,
        ):
            raise DiagnosticAnalysisError(
                "published summary inode or payload changed before fsync"
            )
        publication_observed_exact = True
        _assert_summary_publication_topology(
            parent_fd,
            pinned_protected_roots,
            publication_may_exist=True,
        )
        os.fsync(parent_fd)
        parent_barrier_completed = True
        _assert_summary_publication_topology(
            parent_fd,
            pinned_protected_roots,
            publication_may_exist=True,
        )
        if not _summary_publication_is_exact(
            destination,
            parent_fd,
            parent_identity,
            staged_identity,
            payload,
        ):
            raise DiagnosticAnalysisError(
                "summary destination path or payload changed during publication"
            )
        _assert_summary_publication_topology(
            parent_fd,
            pinned_protected_roots,
            publication_may_exist=True,
        )
        if not _summary_publication_is_exact(
            destination,
            parent_fd,
            parent_identity,
            staged_identity,
            payload,
        ):
            raise DiagnosticAnalysisError(
                "summary destination changed during final topology proof"
            )
        complete_mandatory_commit_check()
        if not post_durability_check_completed:
            raise DiagnosticAnalysisPublicationAmbiguousError(
                "summary publication durability and rollback are ambiguous; "
                "the destination must not be used as diagnostic evidence"
            )
        return
    except BaseException as error:
        if (
            rename_attempted
            and staged_identity is not None
            and parent_fd >= 0
            and parent_identity is not None
        ):
            if post_durability_check_failed:
                raise_after_failed_post_durability_check(error)
            committed = _recover_summary_publication(
                destination,
                parent_fd,
                parent_identity,
                pinned_protected_roots,
                staging_name,
                file_descriptor,
                staged_identity,
                payload,
                publication_observed_exact,
                parent_barrier_completed,
                error,
            )
            if committed:
                try:
                    complete_mandatory_commit_check()
                except BaseException as recovery_error:
                    raise_after_failed_post_durability_check(recovery_error)
                if not post_durability_check_completed:
                    raise DiagnosticAnalysisPublicationAmbiguousError(
                        "summary publication durability and rollback are "
                        "ambiguous; the destination must not be used as "
                        "diagnostic evidence"
                    ) from error
                return
        raise
    finally:
        if file_descriptor >= 0:
            try:
                os.close(file_descriptor)
            except BaseException:
                pass
        if parent_fd >= 0:
            try:
                os.close(parent_fd)
            except BaseException:
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

    destination = Path(os.path.abspath(os.fspath(output_path)))
    with ExitStack() as authority_cleanup:
        protected_roots = _pin_protected_roots(
            (Path(artifact_dir), Path(bundle_dir)),
        )
        authority_cleanup.callback(
            _close_pinned_protected_roots,
            protected_roots,
        )
        artifact_authority, bundle_authority = protected_roots
        bundle_receipt, bundle_validation_generation = (
            _capture_bundle_validation_baseline(
                bundle_authority,
                protected_roots,
            )
        )
        _assert_pinned_protected_roots(protected_roots)
        validated = _validate_artifact(
            Path(artifact_dir),
            Path(bundle_dir),
            Path(authorization_path),
            authorization_digest,
            repository_root=repository_root,
            attempt_authority_owner=authority_cleanup,
        )
        _assert_pinned_protected_roots(protected_roots)
        attempt_authority, validated_attempt_receipt = (
            _validated_historical_attempt_authority(validated)
        )
        protected_roots = (*protected_roots, attempt_authority)
        _assert_pinned_protected_roots(protected_roots)
        summary = _build_summary(validated)
        historical_value = validated.manifest.get("authorized_output_path")
        if (
            type(historical_value) is not str
            or not Path(historical_value).is_absolute()
        ):
            raise DiagnosticAnalysisError(
                "validated historical artifact path is invalid"
            )
        historical_authorized_path = Path(historical_value)
        try:
            historical_roots = _pin_protected_roots(
                (historical_authorized_path,),
            )
        except DiagnosticAnalysisError as error:
            raise DiagnosticAnalysisError(
                "historical authorized artifact path must exist as a stable "
                "non-symlink directory for summary publication"
            ) from error
        authority_cleanup.callback(
            _close_pinned_protected_roots,
            historical_roots,
        )
        protected_roots = (*protected_roots, *historical_roots)
        historical_canonical = historical_roots[0].path
        if destination == historical_canonical or destination.is_relative_to(
            historical_canonical
        ):
            raise DiagnosticAnalysisError(
                "summary destination cannot modify the historical authorized artifact"
            )
        _assert_pinned_protected_roots(protected_roots)
        _assert_pinned_protected_roots(protected_roots)
        if any(
            destination == root.path or destination.is_relative_to(root.path)
            for root in protected_roots
        ):
            raise DiagnosticAnalysisError(
                "summary destination cannot modify a protected artifact or bundle"
            )
        validated_receipt = _validated_artifact_receipt(
            getattr(validated, "artifact_receipt", ()),
            "validated runner artifact",
        )
        authority_specs = (
            (
                historical_roots[0],
                RUN_ARTIFACT_FILENAMES,
                "historical committed artifact",
            ),
            (
                artifact_authority,
                RUN_ARTIFACT_FILENAMES,
                "relocated validated artifact",
            ),
            (
                bundle_authority,
                BUNDLE_FILENAMES,
                "verified diagnostic bundle",
            ),
            (
                attempt_authority,
                _COMMITTED_ATTEMPT_FILENAMES,
                "historical committed attempt",
            ),
        )
        source_generation: _AuthorityGeneration | None = None

        def revalidate_authority_receipts() -> None:
            nonlocal source_generation

            before_generation = _capture_pinned_authority_generation(
                authority_specs,
                protected_roots,
            )
            if before_generation[2] != bundle_validation_generation:
                raise DiagnosticAnalysisError(
                    "source authority generation changed after validation: "
                    "diagnostic bundle"
                )
            _assert_pinned_protected_roots(protected_roots)
            _read_artifact_receipt_from_descriptor(
                historical_roots[0].descriptor,
                "historical committed artifact",
                validated_receipt,
            )
            _read_artifact_receipt_from_descriptor(
                artifact_authority.descriptor,
                "relocated validated artifact",
                validated_receipt,
            )
            _read_bundle_receipt_from_descriptor(
                bundle_authority.descriptor,
                "verified diagnostic bundle",
                bundle_receipt,
            )
            _revalidate_attempt_authority_after_topology(
                attempt_authority,
                validated_attempt_receipt,
                protected_roots,
                "historical committed attempt",
            )
            after_generation = _capture_pinned_authority_generation(
                authority_specs,
                protected_roots,
            )
            if after_generation != before_generation:
                raise DiagnosticAnalysisError(
                    "summary source authorities changed during collective proof"
                )
            if after_generation[2] != bundle_validation_generation:
                raise DiagnosticAnalysisError(
                    "source authority generation changed after validation: "
                    "diagnostic bundle"
                )
            if source_generation is not None and after_generation != source_generation:
                raise DiagnosticAnalysisError(
                    "summary source authority generation changed after validation"
                )
            source_generation = after_generation

        revalidate_authority_receipts()
        _assert_pinned_protected_roots(protected_roots)
        _atomic_write_no_replace(
            destination,
            _canonical_bytes(summary),
            protected_roots=protected_roots,
            post_durability_check=revalidate_authority_receipts,
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
        # The self-test owns this temporary path, so hand the publisher its
        # canonical spelling even on hosts where /tmp or /var is a symlink.
        output = Path(root).resolve() / "summary.json"
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
            requested_output = Path(os.path.abspath(os.fspath(arguments.output)))
            summary = write_countdown_thompson_diagnostic_summary(
                arguments.analyze,
                arguments.bundle,
                arguments.authorization_file,
                arguments.authorization_digest,
                requested_output,
                repository_root=arguments.repository_root,
            )
            result = {
                "analyzer_build_digest": summary["analyzer_build_digest"],
                "claim_boundary": (
                    "diagnostic result emitted only after every integrity gate "
                    "passed; no inferential, superiority, or locked-evaluation "
                    "authority"
                ),
                "output_path": str(requested_output),
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
        RecursionError,
        ValueError,
    ) as error:
        print(canonical_json(_invalid_cli_result(str(error))))
        return 2
    print(canonical_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
