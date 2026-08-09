"""Fail-closed descriptive analysis for a sealed Track A canary run.

The analyzer accepts paths, not caller-created authority objects.  It
independently verifies the outcome-blind bundle, validates the exact run
artifact closure and all 936 cell identities, and performs stage-one plus
stage-two search replay before constructing any performance summary.

The output is deliberately development-only: raw task vectors, descriptive
contrasts, engineering gate statuses, and resource counters.  It has no
confidence intervals, p-values, winner, non-inferiority, or promotion result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence, TypedDict

from qmc_bmgs.benchmarks.countdown import CountdownTask
from qmc_bmgs.experiments.countdown_track_a_canary_manifest import (
    EXPECTED_CELL_COUNT,
    CanaryCell,
    VerifiedCanaryBundle,
    iter_track_a_canary_cells,
    verify_track_a_canary_bundle,
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


RUN_MANIFEST_SCHEMA_VERSION = "qmc-bmgs-countdown-track-a-canary-run-manifest/v1"
RUN_RECORD_SCHEMA_VERSION = "qmc-bmgs-countdown-track-a-canary-run-record/v1"
ANALYSIS_SCHEMA_VERSION = "qmc-bmgs-countdown-track-a-canary-analysis/v1"
ANALYZER_BUILD_SCHEMA_VERSION = "qmc-bmgs-countdown-track-a-canary-analyzer-build/v1"
ARTIFACT_COMMIT_SCHEMA_VERSION = "qmc-bmgs-countdown-track-a-canary-artifact-commit/v1"
SUMMARY_FILENAME = "summary.json"
RUN_ARTIFACT_FILENAMES = ("commit.json", "manifest.json", "records.jsonl")
ANALYZER_RELATIVE_PATH = Path(
    "src/qmc_bmgs/experiments/countdown_track_a_canary_analysis.py"
)

_SEARCH_SOURCE_PATHS = (
    "src/qmc_bmgs/benchmarks/countdown.py",
    "src/qmc_bmgs/substrate/budget.py",
    "src/qmc_bmgs/substrate/countdown_search.py",
    "src/qmc_bmgs/substrate/perturbations.py",
    "src/qmc_bmgs/substrate/proposals.py",
    "src/qmc_bmgs/substrate/trace.py",
)
_RUNNER_SOURCE_PATHS = (
    "src/qmc_bmgs/experiments/countdown_track_a_canary_manifest.py",
    "src/qmc_bmgs/experiments/countdown_track_a_canary_runner.py",
    ANALYZER_RELATIVE_PATH.as_posix(),
)
_CURRENT_REPLAY_MODULE_PATHS = {
    "qmc_bmgs.benchmarks.countdown": _SEARCH_SOURCE_PATHS[0],
    "qmc_bmgs.substrate.budget": _SEARCH_SOURCE_PATHS[1],
    "qmc_bmgs.substrate.countdown_search": _SEARCH_SOURCE_PATHS[2],
    "qmc_bmgs.substrate.perturbations": _SEARCH_SOURCE_PATHS[3],
    "qmc_bmgs.substrate.proposals": _SEARCH_SOURCE_PATHS[4],
    "qmc_bmgs.substrate.trace": _SEARCH_SOURCE_PATHS[5],
    "qmc_bmgs.experiments.countdown_track_a_canary_manifest": (_RUNNER_SOURCE_PATHS[0]),
    __name__: _RUNNER_SOURCE_PATHS[2],
}

_LOWER_HEX = frozenset("0123456789abcdef")
_ADAPTIVE_METHOD_ORDER = (
    "puct_c1",
    "thompson_frozen_iid",
    "thompson_frozen_sobol",
    "thompson_candidate_iid",
    "thompson_candidate_sobol",
)
_ADAPTIVE_METHODS = frozenset(_ADAPTIVE_METHOD_ORDER)
_CANARY_SEEDS = (7168, 7169, 7170, 7171)
_CONTRAST_ORDER = (
    "candidate_minus_frozen_iid",
    "candidate_minus_frozen_sobol",
    "equal_source_candidate_minus_frozen",
    "candidate_sobol_minus_candidate_iid",
    "candidate_iid_minus_greedy",
    "candidate_iid_minus_beam",
    "candidate_iid_minus_puct",
)
_PAIRWISE_CONTRASTS = {
    "candidate_minus_frozen_iid": (
        "thompson_candidate_iid",
        "thompson_frozen_iid",
    ),
    "candidate_minus_frozen_sobol": (
        "thompson_candidate_sobol",
        "thompson_frozen_sobol",
    ),
    "candidate_sobol_minus_candidate_iid": (
        "thompson_candidate_sobol",
        "thompson_candidate_iid",
    ),
    "candidate_iid_minus_greedy": ("thompson_candidate_iid", "greedy"),
    "candidate_iid_minus_beam": (
        "thompson_candidate_iid",
        "beam_width_2",
    ),
    "candidate_iid_minus_puct": ("thompson_candidate_iid", "puct_c1"),
}


class CanaryAnalysisError(ValueError):
    """Raised before any summary exists when a run artifact fails closed."""


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


class TrackACanaryRunnerRecord(TypedDict):
    """Exact analyzer-facing protocol shared with the manifest runner."""

    schema_version: str
    bundle_id: str
    cell_id: str
    cell_key: dict[str, Any]
    labels: RunnerLabels
    canary_seal_digest: str
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
    "canary_seal_digest",
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
    "canary_seal_digest",
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
_RUN_RECORD_FIELDS = set(TrackACanaryRunnerRecord.__required_keys__)
_LABEL_FIELDS = set(RunnerLabels.__required_keys__)
_REPLAY_FIELDS = set(RunnerReplayReceipt.__required_keys__)
_BUDGET_EVIDENCE_FIELDS = set(RunnerBudgetEvidence.__required_keys__)
_TELEMETRY_FIELDS = set(RunnerTelemetry.__required_keys__)
_TELEMETRY_ROLE = "descriptive_only_excluded_from_search_core_identity_and_gates"
_RUN_CLAIM_BOUNDARY = (
    "descriptive canary artifact; byte replay applies only to the embedded "
    "search core, telemetry is volatile, and no inferential or promotion "
    "authority is granted"
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
        raise CanaryAnalysisError(f"{label} is not strict UTF-8 JSON") from error
    if type(parsed) is not dict:
        raise CanaryAnalysisError(f"{label} must be a JSON object")
    try:
        canonical = (_stdlib_canonical_json(parsed) + "\n").encode("utf-8")
    except (TypeError, ValueError) as error:
        raise CanaryAnalysisError(f"{label} is not finite canonical JSON") from error
    if canonical != raw:
        raise CanaryAnalysisError(f"{label} bytes are not canonical")
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
        raise CanaryAnalysisError(f"{label} must be a non-negative plain integer")
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
        raise CanaryAnalysisError(f"{label} validation requires POSIX O_NOFOLLOW")
    candidate = Path(path)
    try:
        descriptor = os.open(candidate, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as error:
        raise CanaryAnalysisError(f"{label} must be a regular file") from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise CanaryAnalysisError(f"{label} must be a regular file")
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
            raise CanaryAnalysisError(f"{label} changed during descriptor read")
        return first
    finally:
        os.close(descriptor)


def _read_artifact_member_preflight(directory: Path, filename: str) -> bytes:
    """Read one authority member before outcome-bearing records are opened."""

    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise CanaryAnalysisError("runner artifact preflight requires POSIX O_NOFOLLOW")
    root = Path(directory)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW
    try:
        directory_fd = os.open(root, flags)
    except OSError as error:
        raise CanaryAnalysisError(
            "runner artifact path must be a regular directory"
        ) from error
    try:
        if not stat.S_ISDIR(os.fstat(directory_fd).st_mode):
            raise CanaryAnalysisError(
                "runner artifact path must be a regular directory"
            )
        try:
            member_fd = os.open(
                filename,
                os.O_RDONLY | os.O_NOFOLLOW,
                dir_fd=directory_fd,
            )
        except OSError as error:
            raise CanaryAnalysisError(
                f"runner artifact authority member is unavailable: {filename}"
            ) from error
        try:
            if not stat.S_ISREG(os.fstat(member_fd).st_mode):
                raise CanaryAnalysisError(
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
            raise CanaryAnalysisError(
                "runner artifact path must be a regular directory"
            ) from error
        try:
            names = os.listdir(directory_fd)
            if len(names) != len(set(names)) or set(names) != set(
                RUN_ARTIFACT_FILENAMES
            ):
                raise CanaryAnalysisError("runner artifact directory closure drifted")
            snapshot: dict[str, bytes] = {}
            for filename in RUN_ARTIFACT_FILENAMES:
                file_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                try:
                    file_fd = os.open(filename, file_flags, dir_fd=directory_fd)
                except OSError as error:
                    raise CanaryAnalysisError(
                        f"runner artifact member is unavailable: {filename}"
                    ) from error
                try:
                    if not stat.S_ISREG(os.fstat(file_fd).st_mode):
                        raise CanaryAnalysisError(
                            f"runner artifact member is not regular: {filename}"
                        )
                    snapshot[filename] = _read_fd_bytes(file_fd)
                finally:
                    os.close(file_fd)
            return snapshot
        finally:
            os.close(directory_fd)

    if root.is_symlink() or not root.is_dir():
        raise CanaryAnalysisError("runner artifact path must be a regular directory")
    paths = list(root.iterdir())
    if {path.name for path in paths} != set(RUN_ARTIFACT_FILENAMES):
        raise CanaryAnalysisError("runner artifact directory closure drifted")
    snapshot = {}
    for filename in RUN_ARTIFACT_FILENAMES:
        path = root / filename
        if path.is_symlink() or not path.is_file():
            raise CanaryAnalysisError(
                f"runner artifact member is not regular: {filename}"
            )
        snapshot[filename] = path.read_bytes()
    return snapshot


def _strict_json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8")
        parsed = strict_json_loads(text)
    except (UnicodeDecodeError, TraceValidationError) as error:
        raise CanaryAnalysisError(f"{label} is not strict UTF-8 JSON") from error
    if type(parsed) is not dict:
        raise CanaryAnalysisError(f"{label} must be a JSON object")
    if _canonical_bytes(parsed) != raw:
        raise CanaryAnalysisError(f"{label} bytes are not canonical")
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
        raise CanaryAnalysisError(
            "reviewed authorization digest must be lowercase SHA-256"
        )
    if payload.get("deterministic_digest") != supplied_digest:
        raise CanaryAnalysisError("reviewed authorization digest does not match")
    return payload, raw


def _strict_jsonl(raw: bytes) -> tuple[dict[str, Any], ...]:
    if not raw or not raw.endswith(b"\n"):
        raise CanaryAnalysisError("records.jsonl must be non-empty canonical JSONL")
    records: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(raw.splitlines(keepends=True), start=1):
        try:
            text = raw_line.decode("utf-8")
            parsed = strict_json_loads(text)
        except (UnicodeDecodeError, TraceValidationError) as error:
            raise CanaryAnalysisError(
                f"records.jsonl line {line_number} is not strict JSON"
            ) from error
        if type(parsed) is not dict or _canonical_bytes(parsed) != raw_line:
            raise CanaryAnalysisError(
                f"records.jsonl line {line_number} is not a canonical object"
            )
        records.append(parsed)
    return tuple(records)


def _validate_digest_field(payload: Mapping[str, Any], field: str) -> None:
    if not _is_sha256(payload.get(field)):
        raise CanaryAnalysisError(f"{field} must be lowercase SHA-256")


def _validate_git_oid_field(payload: Mapping[str, Any], field: str) -> None:
    if not _is_git_oid(payload.get(field)):
        raise CanaryAnalysisError(f"{field} must be a lowercase Git object id")


def _validate_receipt_map(
    receipts: object,
    *,
    expected_paths: Sequence[str],
    label: str,
) -> dict[str, dict[str, Any]]:
    if type(receipts) is not dict or set(receipts) != set(expected_paths):
        raise CanaryAnalysisError(f"{label} protected path set drifted")
    for relative_path in expected_paths:
        receipt = receipts[relative_path]
        if (
            type(receipt) is not dict
            or set(receipt) != {"byte_count", "sha256"}
            or type(receipt["byte_count"]) is not int
            or receipt["byte_count"] < 0
            or not _is_sha256(receipt["sha256"])
        ):
            raise CanaryAnalysisError(f"{label} source receipt is invalid")
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
        raise CanaryAnalysisError("runner build attestation fields drifted")
    if attestation["schema_version"] != (
        "qmc-bmgs-countdown-track-a-canary-build-attestation/v1"
    ):
        raise CanaryAnalysisError("runner build attestation schema drifted")
    _validate_git_oid_field(attestation, "authorized_runner_revision")
    ancestry = attestation["required_ancestry"]
    if (
        type(ancestry) is not list
        or not ancestry
        or any(not _is_git_oid(revision) for revision in ancestry)
        or len(set(ancestry)) != len(ancestry)
    ):
        raise CanaryAnalysisError("runner required ancestry is invalid")
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
        raise CanaryAnalysisError("runner/search build attestation is invalid")
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
        raise CanaryAnalysisError("runner/search build attestation digest mismatch")
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
        raise CanaryAnalysisError("attempt STARTED receipt fields drifted")
    receipt_core = {
        key: value for key, value in receipt.items() if key != "deterministic_digest"
    }
    if (
        not _is_sha256(payload.get("attempt_started_receipt_digest"))
        or receipt["deterministic_digest"] != _stdlib_sha256_json(receipt_core)
        or payload["attempt_started_receipt_digest"] != receipt["deterministic_digest"]
    ):
        raise CanaryAnalysisError("attempt STARTED receipt digest does not close")
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
        raise CanaryAnalysisError("attempt output/authorization identity is invalid")
    expected_marker = f".{artifact_id}.attempt-{authorization_digest}"
    expected_staging = str(Path(authorized_output).parent / expected_marker / "staging")
    if (
        payload.get("attempt_id") != authorization_digest
        or payload.get("attempt_marker_basename") != expected_marker
        or payload.get("attempt_phase") != "READY_TO_COMMIT"
        or receipt["schema_version"]
        != "qmc-bmgs-countdown-track-a-canary-attempt-marker/v1"
        or receipt["phase"] != "STARTED"
        or receipt["status"] != "PENDING"
        or receipt["artifact_id"] != artifact_id
        or receipt["authorization_digest"] != authorization_digest
        or receipt["authorized_output_path"] != authorized_output
        or receipt["canary_seal_digest"] != payload.get("canary_seal_digest")
        or receipt["execution_head_revision"] != payload.get("execution_head_revision")
        or receipt["reviewed_authorization_revision"]
        != payload.get("reviewed_authorization_revision")
        or receipt["runner_build_digest"] != runner_build_digest
        or receipt["search_build_digest"] != search_build_digest
        or receipt["staging_path"] != expected_staging
    ):
        raise CanaryAnalysisError("attempt STARTED receipt binding drifted")


def _validate_artifact_commit(
    payload: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> None:
    if type(payload) is not dict or set(payload) != _ARTIFACT_COMMIT_FIELDS:
        raise CanaryAnalysisError("artifact commit receipt fields drifted")
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
        raise CanaryAnalysisError("artifact commit receipt does not close")


def _preflight_run_manifest(
    payload: dict[str, Any],
) -> tuple[Mapping[str, Any], str, str]:
    """Validate authority-bearing manifest structure before project replay use."""

    if set(payload) != _RUN_MANIFEST_FIELDS:
        raise CanaryAnalysisError("runner manifest fields drifted")
    if payload.get("schema_version") != RUN_MANIFEST_SCHEMA_VERSION:
        raise CanaryAnalysisError("runner manifest schema drifted")
    core = {
        key: value for key, value in payload.items() if key != "deterministic_digest"
    }
    if payload.get("deterministic_digest") != _stdlib_sha256_json(core):
        raise CanaryAnalysisError("runner manifest deterministic digest mismatch")
    if payload.get("claim_boundary") != _RUN_CLAIM_BOUNDARY:
        raise CanaryAnalysisError("runner manifest claim boundary drifted")
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


def _require_git_commit_object(
    repository_root: Path,
    revision: str,
    label: str,
) -> None:
    result = _git_result(repository_root, "cat-file", "-t", revision)
    if result.returncode != 0 or result.stdout != b"commit\n":
        raise CanaryAnalysisError(f"{label} must name an exact Git commit object")


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
        raise CanaryAnalysisError("authorization Git tree entry is not unique")
    metadata, observed_path = entries[0].split(b"\t", maxsplit=1)
    fields = metadata.split()
    if (
        observed_path != relative_path.encode("utf-8")
        or len(fields) != 3
        or fields[0] != b"100644"
        or fields[1] != b"blob"
    ):
        raise CanaryAnalysisError(
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
        raise CanaryAnalysisError("repository root is not a readable Git checkout")
    try:
        observed_root = Path(top_level.stdout.decode("utf-8").strip()).resolve()
    except UnicodeDecodeError as error:
        raise CanaryAnalysisError("Git top-level path is not UTF-8") from error
    if observed_root != root:
        raise CanaryAnalysisError("repository root does not match Git top level")

    authorized = attestation["authorized_runner_revision"]
    ancestors = [authorized, *attestation["required_ancestry"]]
    for revision in [execution_head_revision, *ancestors]:
        exists = _git_result(root, "cat-file", "-e", f"{revision}^{{commit}}")
        if exists.returncode != 0:
            raise CanaryAnalysisError(
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
            raise CanaryAnalysisError(
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
            raise CanaryAnalysisError(
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
            raise CanaryAnalysisError(
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
            raise CanaryAnalysisError(
                "current replay source, attested receipt, and execution-head "
                f"blob differ: {relative}"
            )
        if relative == ANALYZER_RELATIVE_PATH.as_posix():
            analyzer_bytes = current_bytes
            analyzer_receipt = receipt
    if analyzer_bytes is None or analyzer_receipt is None:
        raise CanaryAnalysisError("current analyzer was absent from replay surface")
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
        raise CanaryAnalysisError(
            "reviewed authorization must be a repository-relative file"
        )
    if absolute.resolve() != absolute:
        raise CanaryAnalysisError(
            "reviewed authorization path must not traverse symlinks"
        )
    relative = absolute.relative_to(root).as_posix()
    if relative == "." or ".." in Path(relative).parts:
        raise CanaryAnalysisError("reviewed authorization repository path is invalid")
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
        raise CanaryAnalysisError("reviewed authorization path resolution drifted")
    embedded = manifest.get("execution_authorization")
    if (
        type(embedded) is not dict
        or (_stdlib_canonical_json(embedded) + "\n").encode("utf-8")
        != authorization_raw
    ):
        raise CanaryAnalysisError(
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
        raise CanaryAnalysisError(
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
            raise CanaryAnalysisError(
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
        raise CanaryAnalysisError(
            "reviewed authorization is not one exact tracked file"
        )
    for revision in (reviewed, execution_head):
        _require_regular_git_tree_entry(root, revision, relative)
        blob = _git_result(root, "show", f"{revision}:{relative}")
        if blob.returncode != 0 or blob.stdout != authorization_raw:
            raise CanaryAnalysisError(
                "reviewed authorization bytes differ from reviewed/HEAD Git blob"
            )


def _validate_run_manifest(
    payload: dict[str, Any],
    *,
    records_raw: bytes,
    expected_cells: Sequence[CanaryCell],
    bundle: VerifiedCanaryBundle,
    reviewed_authorization: Mapping[str, Any],
    reviewed_authorization_raw: bytes,
    analyzer_build_digest: str,
) -> tuple[str, str, str, str]:
    if set(payload) != _RUN_MANIFEST_FIELDS:
        raise CanaryAnalysisError("runner manifest fields drifted")
    if payload["schema_version"] != RUN_MANIFEST_SCHEMA_VERSION:
        raise CanaryAnalysisError("runner manifest schema drifted")
    bundle_payloads = bundle.payloads
    bundle_id = bundle_payloads["preregistration.json"]["bundle_id"]
    if payload["bundle_id"] != bundle_id:
        raise CanaryAnalysisError("runner manifest bundle id drifted")
    core = {
        key: value for key, value in payload.items() if key != "deterministic_digest"
    }
    if payload["deterministic_digest"] != sha256_json(core):
        raise CanaryAnalysisError("runner manifest deterministic digest mismatch")

    method_manifest_digest = bundle_payloads["methods.json"]["deterministic_digest"]
    if payload["canary_seal_digest"] != bundle.seal_digest:
        raise CanaryAnalysisError("runner manifest seal binding drifted")
    if payload["method_manifest_digest"] != method_manifest_digest:
        raise CanaryAnalysisError("runner manifest method binding drifted")
    if payload["cell_count"] != EXPECTED_CELL_COUNT or payload["cell_count"] != len(
        expected_cells
    ):
        raise CanaryAnalysisError("runner manifest cell count drifted")
    expected_ids = [cell.cell_id for cell in expected_cells]
    if not _same_json(payload["schedule_cell_ids"], expected_ids):
        raise CanaryAnalysisError("runner manifest schedule identity/order drifted")
    if payload["records_jsonl_sha256"] != _sha256_bytes(records_raw):
        raise CanaryAnalysisError("records.jsonl SHA-256 mismatch")
    if payload["records_jsonl_byte_count"] != len(records_raw):
        raise CanaryAnalysisError("records.jsonl byte count mismatch")
    if type(payload["claim_boundary"]) is not str or not payload["claim_boundary"]:
        raise CanaryAnalysisError("runner manifest claim boundary is invalid")
    if payload["claim_boundary"] != _RUN_CLAIM_BOUNDARY:
        raise CanaryAnalysisError("runner manifest claim boundary drifted")
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
        raise CanaryAnalysisError("runner manifest telemetry fields drifted")
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
        raise CanaryAnalysisError("analyzer build digest is invalid")

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
        raise CanaryAnalysisError("runtime qualification fields drifted")
    expected_runtime_bindings_digest = sha256_json(
        bundle_payloads["methods.json"]["runtime_bindings"]
    )
    if (
        qualification["bundle_id"] != bundle_id
        or qualification["execution_authorized"] is not False
        or qualification["runtime_bindings_digest"] != expected_runtime_bindings_digest
        or qualification["status"] != "RUNTIME_QUALIFIED"
    ):
        raise CanaryAnalysisError("runtime qualification does not match the bundle")
    runtime_qualification_digest = sha256_json(qualification)

    authorization = payload["execution_authorization"]
    expected_authorization_fields = {
        "authorization_scope",
        "artifact_id",
        "bundle_id",
        "canary_seal_digest",
        "cell_count",
        "claim_boundary",
        "deterministic_digest",
        "method_manifest_digest",
        "output_path",
        "requires_explicit_digest_confirmation",
        "runner_build_attestation",
        "runtime_qualification",
        "runtime_qualification_digest",
        "schedule_digest",
        "schema_version",
    }
    if type(authorization) is not dict or set(authorization) != (
        expected_authorization_fields
    ):
        raise CanaryAnalysisError("execution authorization fields drifted")
    if (
        not _same_json(authorization, reviewed_authorization)
        or _canonical_bytes(authorization) != reviewed_authorization_raw
    ):
        raise CanaryAnalysisError(
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
        != "qmc-bmgs-countdown-track-a-canary-execution-authorization/v1"
        or authorization["authorization_scope"]
        != "one_exact_complete_936_cell_canary_run"
        or authorization["claim_boundary"]
        != "execution authority only; canary comparisons remain descriptive"
        or authorization["bundle_id"] != bundle_id
        or authorization["canary_seal_digest"] != bundle.seal_digest
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
        raise CanaryAnalysisError("execution authorization does not close")
    authorized_output = authorization["output_path"]
    if (
        type(authorized_output) is not str
        or not Path(authorized_output).is_absolute()
        or type(payload["artifact_id"]) is not str
        or not payload["artifact_id"]
        or Path(authorized_output).name != payload["artifact_id"]
    ):
        raise CanaryAnalysisError("authorized output provenance is invalid")
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


def _typed_replay_inputs(bundle: VerifiedCanaryBundle) -> _ReplayInputs:
    payloads = bundle.payloads
    tasks: dict[str, CountdownTask] = {}
    for row in payloads["tasks.json"]["tasks"]:
        task = CountdownTask(tuple(row["inputs"]), row["target"])
        if not _same_json(task.to_dict(), row):
            raise CanaryAnalysisError("verified task row did not rehydrate exactly")
        tasks[task.task_fingerprint] = task

    proposals: dict[str, TrackAProposalSpec] = {}
    for row in payloads["proposals.json"]["policies"]:
        proposal = TrackAProposalSpec(row["spec"]["policy_id"])
        if not _same_json(proposal.to_dict(), row["spec"]):
            raise CanaryAnalysisError("verified proposal did not rehydrate exactly")
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
            schema_version=spec["schema_version"],
        )
        if not _same_json(method.to_dict(), spec):
            raise CanaryAnalysisError("verified method did not rehydrate exactly")
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
            raise CanaryAnalysisError("verified budget did not rehydrate exactly")
        budgets[profile.profile_id] = profile
    return _ReplayInputs(tasks, proposals, methods, budgets)


def _search_summary(search_record: Mapping[str, Any]) -> dict[str, Any]:
    events = search_record.get("events")
    if type(events) is not list or not events:
        raise CanaryAnalysisError("search record has no final event")
    final = events[-1]
    if type(final) is not dict or final.get("kind") != "search_finished":
        raise CanaryAnalysisError("search record does not end with search_finished")
    payload = final.get("payload")
    if type(payload) is not dict or type(payload.get("summary")) is not dict:
        raise CanaryAnalysisError("search_finished summary is invalid")
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
    cell: CanaryCell,
    method: TrackAMethodSpec,
    profile: TrackABudgetProfile,
    search_record: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> None:
    ledger = search_record["ledger_snapshot"]
    usage = ledger["usage"]
    remaining = ledger["remaining"]
    if summary.get("budget_valid") is not True:
        raise CanaryAnalysisError(f"cell {cell.cell_id} reports invalid budget")
    if summary.get("non_primary_exhausted_axes") != []:
        raise CanaryAnalysisError(f"cell {cell.cell_id} exhausted a non-primary guard")
    blocked_axes = summary.get("stop_blocked_axes")
    if type(blocked_axes) is not list:
        raise CanaryAnalysisError(f"cell {cell.cell_id} blocked axes are invalid")
    non_primary_blocked = [
        axis for axis in blocked_axes if axis != profile.primary_axis
    ]
    if non_primary_blocked:
        raise CanaryAnalysisError(
            f"cell {cell.cell_id} was blocked by a non-primary guard"
        )
    if any(
        type(remaining[axis]) is not int or remaining[axis] <= 0
        for axis in TRACK_A_WORK_AXES
        if axis != profile.primary_axis
    ):
        raise CanaryAnalysisError(
            f"cell {cell.cell_id} lacks positive non-primary headroom"
        )
    terminal_count = _require_plain_nonnegative_int(
        summary.get("terminal_count"),
        f"cell {cell.cell_id} terminal_count",
    )
    if terminal_count < 1:
        raise CanaryAnalysisError(f"cell {cell.cell_id} has no terminal readout")
    if type(summary.get("success_any")) is not bool:
        raise CanaryAnalysisError(f"cell {cell.cell_id} success_any is not boolean")
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
    if method.stochastic:
        if coordinates != legal_scores or point_count != usage["edge_selections"]:
            raise CanaryAnalysisError(
                f"cell {cell.cell_id} stochastic coordinate accounting drifted"
            )
    elif coordinates != 0 or point_count != 0:
        raise CanaryAnalysisError(
            f"cell {cell.cell_id} deterministic coordinates must be zero"
        )

    if method.method == "greedy":
        if terminal_count != 1 or summary.get("stop_reason") != "method_complete":
            raise CanaryAnalysisError("greedy completion closure drifted")
    elif method.method == "beam":
        if terminal_count != 2 or summary.get("stop_reason") != "method_complete":
            raise CanaryAnalysisError("beam completion closure drifted")
    elif method.method in {"puct", "thompson"}:
        if summary.get("stop_reason") != "primary_budget_blocked" or blocked_axes != [
            profile.primary_axis
        ]:
            raise CanaryAnalysisError(
                f"cell {cell.cell_id} adaptive stop closure drifted"
            )
        attempted = summary.get("stop_attempted_charge")
        if type(attempted) is not dict or set(attempted) != set(TRACK_A_WORK_AXES):
            raise CanaryAnalysisError("adaptive attempted charge is invalid")
        if attempted[profile.primary_axis] <= remaining[profile.primary_axis]:
            raise CanaryAnalysisError(
                "adaptive stop did not reject the next whole primary charge"
            )
        if any(
            attempted[axis] > remaining[axis]
            for axis in TRACK_A_WORK_AXES
            if axis != profile.primary_axis
        ):
            raise CanaryAnalysisError(
                "adaptive stop would also bind a non-primary guard"
            )
        if profile.profile_id == "verifier8" and (
            usage["verifier_calls"] != 8 or terminal_count != 8
        ):
            raise CanaryAnalysisError("verifier8 adaptive closure drifted")


def _validate_one_record(
    record: dict[str, Any],
    *,
    cell: CanaryCell,
    bundle_id: str,
    canary_seal_digest: str,
    method_manifest_digest: str,
    replay_inputs: _ReplayInputs,
    runner_build_digest: str,
    search_build_digest: str,
    runtime_qualification_digest: str,
) -> dict[str, Any]:
    if set(record) != _RUN_RECORD_FIELDS:
        raise CanaryAnalysisError(f"cell {cell.cell_id} record fields drifted")
    if record["schema_version"] != RUN_RECORD_SCHEMA_VERSION:
        raise CanaryAnalysisError("runner record schema drifted")
    core = {
        key: value for key, value in record.items() if key != "deterministic_digest"
    }
    if record["deterministic_digest"] != sha256_json(core):
        raise CanaryAnalysisError(f"cell {cell.cell_id} record digest mismatch")
    if record["bundle_id"] != bundle_id or record["cell_id"] != cell.cell_id:
        raise CanaryAnalysisError("runner record external identity drifted")
    if not _same_json(record["cell_key"], cell.key):
        raise CanaryAnalysisError(f"cell {cell.cell_id} full key drifted")
    expected_labels = {
        "task_fingerprint": cell.task_fingerprint,
        "proposal_label": cell.proposal_label,
        "method_label": cell.method_label,
        "budget_profile_id": cell.budget_profile_id,
        "exploration_seed": cell.exploration_seed,
    }
    if type(record["labels"]) is not dict or set(record["labels"]) != _LABEL_FIELDS:
        raise CanaryAnalysisError("runner record labels are invalid")
    if not _same_json(record["labels"], expected_labels):
        raise CanaryAnalysisError(f"cell {cell.cell_id} labels drifted")
    bindings = {
        "canary_seal_digest": canary_seal_digest,
        "method_manifest_digest": method_manifest_digest,
        "runner_build_digest": runner_build_digest,
        "search_build_digest": search_build_digest,
        "runtime_qualification_digest": runtime_qualification_digest,
    }
    if any(record[key] != value for key, value in bindings.items()):
        raise CanaryAnalysisError(f"cell {cell.cell_id} authority binding drifted")
    if record["provider_calls"] != 0 or type(record["provider_calls"]) is not int:
        raise CanaryAnalysisError(f"cell {cell.cell_id} used a provider call")
    telemetry = record["telemetry"]
    if (
        type(telemetry) is not dict
        or set(telemetry) != _TELEMETRY_FIELDS
        or telemetry["role"] != _TELEMETRY_ROLE
    ):
        raise CanaryAnalysisError(f"cell {cell.cell_id} telemetry fields drifted")
    for field in ("search_wall_time_ns", "replay_wall_time_ns"):
        _require_plain_nonnegative_int(
            telemetry[field],
            f"cell {cell.cell_id} telemetry.{field}",
        )

    search_record = record["search_record"]
    if type(search_record) is not dict:
        raise CanaryAnalysisError("embedded search record must be an object")
    try:
        search_bytes = canonical_trace_bytes(search_record)
    except (TraceValidationError, TypeError, ValueError) as error:
        raise CanaryAnalysisError("embedded search record is invalid") from error
    if record["search_trace_sha256"] != _sha256_bytes(search_bytes):
        raise CanaryAnalysisError("embedded search trace SHA-256 mismatch")
    if record["search_trace_byte_count"] != len(search_bytes):
        raise CanaryAnalysisError("embedded search trace byte count mismatch")
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
        raise CanaryAnalysisError(
            f"cell {cell.cell_id} failed independent two-stage replay"
        ) from error

    replay = record["replay"]
    if type(replay) is not dict or set(replay) != _REPLAY_FIELDS:
        raise CanaryAnalysisError("runner replay receipt fields drifted")
    if (
        replay["stage1_generative"] != "PASS"
        or replay["stage2_byte_identical"] != "PASS"
        or replay["replayed_sha256"] != _sha256_bytes(replayed)
        or replayed != search_bytes
    ):
        raise CanaryAnalysisError(f"cell {cell.cell_id} replay receipt does not close")

    summary = _search_summary(search_record)
    if not _same_json(record["search_summary"], summary):
        raise CanaryAnalysisError("runner search summary differs from replayed trace")
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
        raise CanaryAnalysisError("runner budget evidence does not close")
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
        "summary": summary,
        "budget_evidence": expected_budget,
        "telemetry": telemetry,
    }


@dataclass(frozen=True)
class _ValidatedRun:
    bundle: VerifiedCanaryBundle
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
    _validate_reviewed_authorization_provenance(
        repository,
        authorization_path=authorization_file,
        authorization_raw=reviewed_authorization_raw,
        manifest=preflight_manifest,
    )
    try:
        bundle = verify_track_a_canary_bundle(
            Path(bundle_dir),
            repository_root=repository,
        )
        expected_cells = iter_track_a_canary_cells(bundle)
    except (OSError, TraceValidationError, ValueError) as error:
        raise CanaryAnalysisError("canary bundle verification failed") from error
    if len(expected_cells) != EXPECTED_CELL_COUNT:
        raise CanaryAnalysisError("verified canary schedule count drifted")

    first_snapshot = _read_artifact_snapshot(Path(artifact_dir))
    if first_snapshot["manifest.json"] != preflight_manifest_raw:
        raise CanaryAnalysisError("runner manifest changed after source preflight")
    if first_snapshot["commit.json"] != preflight_commit_raw:
        raise CanaryAnalysisError("artifact commit changed after source preflight")
    manifest = _strict_json_object(first_snapshot["manifest.json"], "manifest.json")
    raw_records = first_snapshot["records.jsonl"]
    records = _strict_jsonl(raw_records)
    if len(records) != EXPECTED_CELL_COUNT:
        raise CanaryAnalysisError("runner artifact record count drifted")
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
        raise CanaryAnalysisError("runner manifest record digest sequence drifted")
    observed_ids = [record.get("cell_id") for record in records]
    expected_ids = [cell.cell_id for cell in expected_cells]
    if observed_ids != expected_ids or len(set(observed_ids)) != len(observed_ids):
        raise CanaryAnalysisError(
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
            canary_seal_digest=bundle.seal_digest,
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
        raise CanaryAnalysisError("runner manifest telemetry totals do not close")
    if (
        _read_regular_file_nofollow(
            authorization_file,
            "reviewed authorization path",
        )
        != reviewed_authorization_raw
    ):
        raise CanaryAnalysisError("reviewed authorization changed during analysis")
    if (
        _validate_current_replay_surface(
            repository,
            attestation=attestation,
            execution_head_revision=execution_head_revision,
        )
        != analyzer_build_digest
    ):
        raise CanaryAnalysisError(
            "current replay source closure changed during analysis"
        )
    if _read_artifact_snapshot(Path(artifact_dir)) != first_snapshot:
        raise CanaryAnalysisError("runner artifact changed during verification")
    return _ValidatedRun(
        bundle,
        validated_rows,
        manifest,
        analyzer_build_digest,
    )


def _mean(values: Sequence[int | float]) -> float:
    if not values:
        raise CanaryAnalysisError("cannot summarize an empty value sequence")
    return sum(values) / len(values)


def _task_metrics(
    validated: _ValidatedRun,
) -> tuple[list[dict[str, Any]], dict[tuple[str, str, str], list[float]]]:
    payloads = validated.bundle.payloads
    task_order = [row["task_fingerprint"] for row in payloads["tasks.json"]["tasks"]]
    proposal_order = list(payloads["proposals.json"]["policy_order"])
    budget_order = list(payloads["budgets.json"]["profile_order"])
    method_order = list(payloads["methods.json"]["method_order"])
    method_specs = {row["label"]: row for row in payloads["methods.json"]["methods"]}
    rows_by_key: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for row in validated.records:
        cell = row["cell"]
        key = (
            cell.task_fingerprint,
            cell.proposal_label,
            cell.budget_profile_id,
            cell.method_label,
        )
        rows_by_key.setdefault(key, []).append(row)

    metrics: list[dict[str, Any]] = []
    vectors: dict[tuple[str, str, str], list[float]] = {}
    for proposal in proposal_order:
        execution_scope = next(
            row["execution_scope"]
            for row in payloads["proposals.json"]["policies"]
            if row["label"] == proposal
        )
        labels = ["greedy"] if execution_scope == "greedy_only" else method_order
        for budget in budget_order:
            for method_label in labels:
                stochastic = (
                    method_specs[method_label]["spec"]["selected_source"] != "none"
                )
                expected_seeds = _CANARY_SEEDS if stochastic else (0,)
                vector: list[float] = []
                for task in task_order:
                    cell_rows = rows_by_key.get(
                        (task, proposal, budget, method_label), []
                    )
                    seeds = tuple(row["cell"].exploration_seed for row in cell_rows)
                    if seeds != expected_seeds:
                        raise CanaryAnalysisError(
                            "nested seed order/coverage drifted before task reduction"
                        )
                    successes = [row["summary"]["success_any"] for row in cell_rows]
                    score = _mean([int(value) for value in successes])
                    vector.append(score)
                    metrics.append(
                        {
                            "task_fingerprint": task,
                            "proposal_label": proposal,
                            "budget_profile_id": budget,
                            "method_label": method_label,
                            "ordered_seed_successes": successes,
                            "task_score": score,
                        }
                    )
                vectors[(proposal, budget, method_label)] = vector
    return metrics, vectors


def _method_summaries(
    validated: _ValidatedRun,
    vectors: Mapping[tuple[str, str, str], Sequence[float]],
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for key, vector in vectors.items():
        proposal, budget, method = key
        rows = [
            row
            for row in validated.records
            if (
                row["cell"].proposal_label,
                row["cell"].budget_profile_id,
                row["cell"].method_label,
            )
            == key
        ]
        primary_axis = next(row["budget_evidence"]["primary_axis"] for row in rows)
        ledger_usage = {}
        for axis in TRACK_A_WORK_AXES:
            values = [row["ledger_snapshot"]["usage"][axis] for row in rows]
            ledger_usage[axis] = {
                "sum": sum(values),
                "arithmetic_mean_per_run": _mean(values),
            }
        non_primary_headroom = {
            axis: min(row["ledger_snapshot"]["remaining"][axis] for row in rows)
            for axis in TRACK_A_WORK_AXES
            if axis != primary_axis
        }
        peak_nodes = [
            row["ledger_snapshot"]["peak_live_storage"]["nodes"] for row in rows
        ]
        peak_bytes = [
            row["ledger_snapshot"]["peak_live_storage"]["bytes"] for row in rows
        ]
        run_level_means = {
            field: _mean([row["summary"][field] for row in rows])
            for field in (
                "terminal_count",
                "exact_terminal_count",
                "successful_terminal_diversity",
                "incomplete_trajectory_count",
            )
        }
        telemetry = {}
        for field in ("search_wall_time_ns", "replay_wall_time_ns"):
            values = [row["telemetry"][field] for row in rows]
            telemetry[field] = {
                "sum": sum(values),
                "arithmetic_mean_per_run": _mean(values),
                "maximum": max(values),
            }
        summaries.append(
            {
                "proposal_label": proposal,
                "budget_profile_id": budget,
                "method_label": method,
                "task_score_vector": list(vector),
                "mean_task_score": _mean(vector),
                "tasks_with_any_success": sum(value > 0 for value in vector),
                "successful_run_count": sum(
                    row["summary"]["success_any"] for row in rows
                ),
                "run_count": len(rows),
                "run_level_means": run_level_means,
                "ledger_usage": ledger_usage,
                "minimum_non_primary_headroom": non_primary_headroom,
                "storage_proxy": {
                    "peak_live_nodes": {
                        "maximum": max(peak_nodes),
                        "arithmetic_mean_per_run": _mean(peak_nodes),
                    },
                    "peak_live_bytes_proxy": {
                        "maximum": max(peak_bytes),
                        "arithmetic_mean_per_run": _mean(peak_bytes),
                    },
                },
                "provider_calls": 0,
                "replay_status": "INDEPENDENT_TWO_STAGE_REPLAY_PASS",
                "telemetry_descriptive_only_excluded_from_gates": telemetry,
            }
        )
    return summaries


def _contrasts(
    vectors: Mapping[tuple[str, str, str], Sequence[float]],
    budget_order: Sequence[str],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for budget in budget_order:
        computed: dict[str, list[float]] = {}
        for contrast_id in _CONTRAST_ORDER:
            if contrast_id == "equal_source_candidate_minus_frozen":
                iid = computed["candidate_minus_frozen_iid"]
                sobol = computed["candidate_minus_frozen_sobol"]
                deltas = [
                    (left + right) / 2.0 for left, right in zip(iid, sobol, strict=True)
                ]
            else:
                left_method, right_method = _PAIRWISE_CONTRASTS[contrast_id]
                left = vectors[("heuristic", budget, left_method)]
                right = vectors[("heuristic", budget, right_method)]
                deltas = [
                    left_value - right_value
                    for left_value, right_value in zip(left, right, strict=True)
                ]
            computed[contrast_id] = deltas
            result.append(
                {
                    "contrast_id": contrast_id,
                    "proposal_label": "heuristic",
                    "budget_profile_id": budget,
                    "task_delta_vector": deltas,
                    "mean_task_delta": _mean(deltas),
                    "positive_task_count": sum(value > 0 for value in deltas),
                    "zero_task_count": sum(value == 0 for value in deltas),
                    "negative_task_count": sum(value < 0 for value in deltas),
                }
            )
    return result


def _pareto_statuses(
    vectors: Mapping[tuple[str, str, str], Sequence[float]],
    budget_order: Sequence[str],
) -> list[dict[str, Any]]:
    statuses: list[dict[str, Any]] = []
    for budget in budget_order:
        candidate_iid = vectors[("heuristic", budget, "thompson_candidate_iid")]
        candidate_sobol = vectors[("heuristic", budget, "thompson_candidate_sobol")]
        candidate = [
            (iid + sobol) / 2.0
            for iid, sobol in zip(candidate_iid, candidate_sobol, strict=True)
        ]
        relations = []
        for method in ("greedy", "beam_width_2"):
            baseline = vectors[("heuristic", budget, method)]
            relations.append(
                all(
                    left <= right
                    for left, right in zip(candidate, baseline, strict=True)
                )
                and any(
                    left < right
                    for left, right in zip(candidate, baseline, strict=True)
                )
            )
        dominated = all(relations)
        statuses.append(
            {
                "proposal_label": "heuristic",
                "budget_profile_id": budget,
                "simple_baseline_pareto_dominated": dominated,
                "status": (
                    "BLOCK_SEMANTIC_ROUTING_AND_PRUNING_ESCALATION"
                    if dominated
                    else "NO_PARETO_BLOCK"
                ),
                "locked_evaluation_blocked_by_this_flag": False,
                "candidate_replacement_authorized": False,
            }
        )
    return statuses


def _build_summary(validated: _ValidatedRun) -> dict[str, Any]:
    oracle_rows = [
        row
        for row in validated.records
        if row["cell"].proposal_label == "oracle_positive_control"
    ]
    oracle_successes = sum(row["summary"]["success_any"] for row in oracle_rows)
    if len(oracle_rows) != 24 or oracle_successes != 24:
        raise CanaryAnalysisError(
            "oracle positive control failed; no performance summary is valid"
        )

    task_metrics, vectors = _task_metrics(validated)
    budget_order = validated.bundle.payloads["budgets.json"]["profile_order"]

    signal_rows = [
        row
        for row in validated.records
        if row["cell"].proposal_label == "heuristic"
        and row["cell"].budget_profile_id == "score256"
        and row["cell"].method_label in _ADAPTIVE_METHODS
    ]
    signal_successes = sum(row["summary"]["success_any"] for row in signal_rows)
    signal_status = "PASS" if signal_successes >= 1 else "STOP_REPAIR_NO_LOCKED_128_RUN"
    decision_status = (
        "CANARY_ENGINEERING_PASS"
        if signal_successes >= 1
        else "STOP_REPAIR_NO_LOCKED_128_RUN"
    )
    summary = {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "bundle_id": validated.bundle.payloads["preregistration.json"]["bundle_id"],
        "canary_seal_digest": validated.bundle.seal_digest,
        "analyzer_build_digest": validated.analyzer_build_digest,
        "run_artifact_id": validated.manifest["artifact_id"],
        "run_attempt_id": validated.manifest["attempt_id"],
        "run_manifest_digest": validated.manifest["deterministic_digest"],
        "reviewed_authorization_revision": validated.manifest[
            "reviewed_authorization_revision"
        ],
        "reviewed_execution_authorization_digest": validated.manifest[
            "execution_authorization_digest"
        ],
        "claim_boundary": (
            "Development-only descriptive engineering canary; no confidence "
            "interval, p-value, winner, non-inferiority, or promotion authority. "
            "Source-file bytes and import origins are attested; already-loaded "
            "Python code objects are outside this v1 attestation claim."
        ),
        "hard_gate_status": "PASS",
        "decision_status": decision_status,
        "controls": {
            "oracle_greedy_positive_control": {
                "status": "PASS",
                "successful_cells": oracle_successes,
                "required_successful_cells": 24,
            },
            "uniform_proposal_quality_control": {
                "status": "DESCRIPTIVE_ONLY_NO_THRESHOLD",
            },
        },
        "primary_adaptive_signal": {
            "status": signal_status,
            "successful_cells": signal_successes,
            "minimum_successful_cells": 1,
            "proposal_label": "heuristic",
            "budget_profile_id": "score256",
            "method_labels": list(_ADAPTIVE_METHOD_ORDER),
        },
        "task_metrics": task_metrics,
        "method_summaries": _method_summaries(validated, vectors),
        "descriptive_paired_contrasts": _contrasts(vectors, budget_order),
        "simple_baseline_pareto_diagnostics": _pareto_statuses(
            vectors,
            budget_order,
        ),
    }
    summary["deterministic_digest"] = sha256_json(summary)
    return summary


def analyze_track_a_canary_artifact(
    artifact_dir: Path,
    bundle_dir: Path,
    authorization_path: Path,
    authorization_digest: str,
    *,
    repository_root: Path,
) -> dict[str, Any]:
    """Validate paths and return a descriptive summary only after all gates pass."""

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
            raise CanaryAnalysisError(f"{label} must be a regular directory")
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        directory_fd = os.open(path, flags)
        opened = os.fstat(directory_fd)
    except OSError as error:
        raise CanaryAnalysisError(f"{label} must be a stable directory") from error
    if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
        os.close(directory_fd)
        raise CanaryAnalysisError(f"{label} changed while it was opened")
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


def _atomic_write_no_replace(
    path: Path,
    payload: bytes,
    *,
    protected_roots: Sequence[Path] = (),
) -> None:
    if os.name != "posix":
        raise CanaryAnalysisError(
            "descriptor-bound no-overwrite publication requires POSIX"
        )
    destination = Path(path)
    if not destination.name:
        raise CanaryAnalysisError("summary destination filename is empty")
    destination_resolved = destination.resolve()
    resolved_roots = tuple(Path(root).resolve() for root in protected_roots)
    if any(
        destination_resolved == root or destination_resolved.is_relative_to(root)
        for root in resolved_roots
    ):
        raise CanaryAnalysisError(
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
            raise CanaryAnalysisError(
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
            raise CanaryAnalysisError("could not allocate exclusive summary staging")
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
            raise CanaryAnalysisError(
                "atomic no-overwrite summary publication is unavailable"
            ) from error
        published = os.stat(
            destination.name,
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
        if (published.st_dev, published.st_ino) != staged_identity:
            raise CanaryAnalysisError("published summary inode changed before fsync")
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
                raise CanaryAnalysisError(
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
                raise CanaryAnalysisError(
                    "summary destination path changed during publication"
                )
        finally:
            os.close(current_parent_fd)
    except BaseException:
        if linked and staged_identity is not None and parent_fd >= 0:
            try:
                if _unlink_if_identity(
                    parent_fd,
                    destination.name,
                    staged_identity,
                ):
                    os.fsync(parent_fd)
            except OSError:
                pass
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


def write_track_a_canary_summary(
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
        raise CanaryAnalysisError(
            "summary destination cannot modify the run artifact or sealed bundle"
        )
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"summary destination exists: {destination}")
    summary = analyze_track_a_canary_artifact(
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
    """Exercise non-canary analyzer plumbing without opening a sealed bundle."""

    fixture = {
        "claim_boundary": "synthetic analyzer plumbing only",
        "schema_version": "qmc-bmgs-canary-analysis-self-test/v1",
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
            "non-canary plumbing only; no sealed bundle, task, proposal, search "
            "record, or outcome was opened"
        ),
        "status": "PASS",
    }


def _invalid_cli_result(reason: str) -> dict[str, Any]:
    return {
        "claim_boundary": "no canary performance summary was emitted",
        "reason": reason,
        "status": "INVALID",
    }


class _FailClosedArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CanaryAnalysisError(message)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _FailClosedArgumentParser(
        description="Fail-closed Track A canary artifact analyzer",
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
    except CanaryAnalysisError as error:
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
                raise CanaryAnalysisError(
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
                raise CanaryAnalysisError(
                    f"--analyze is missing required arguments: {', '.join(missing)}"
                )
            summary = write_track_a_canary_summary(
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
                    "descriptive summary emitted only after every canary integrity "
                    "gate passed; no inferential or promotion authority"
                ),
                "output_path": str(arguments.output.resolve()),
                "status": "PASS",
                "summary_digest": summary["deterministic_digest"],
            }
    except (
        AssertionError,
        CanaryAnalysisError,
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
