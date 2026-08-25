#!/usr/bin/env python3
"""Fail-closed controls for the sealed Countdown Thompson diagnostic.

Planning can bind a reviewed v2r3 regular-file namespace, but production
execution remains disabled until the production publisher and analyzer are
integrated and reviewed.  The legacy directory publisher is reachable only by
explicit non-diagnostic fixtures.  ``--self-test`` never reads the sealed task
cohort.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import math
import os
import platform
import secrets
import stat
import subprocess
import sys
import time
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, NoReturn, Sequence

from qmc_bmgs.benchmarks.countdown import CountdownTask
from qmc_bmgs.experiments import countdown_thompson_diagnostic_analysis as analysis
from qmc_bmgs.experiments import countdown_thompson_diagnostic_manifest as manifest
from qmc_bmgs.experiments import (
    countdown_track_a_canary_manifest as canary_manifest,
)
from qmc_bmgs.experiments import (
    countdown_thompson_regular_file_publication_v2 as regular_file_publication,
)
from qmc_bmgs.experiments.countdown_thompson_diagnostic_manifest import (
    BUNDLE_ID,
    EXPECTED_CELL_COUNT,
    DiagnosticCell,
    verify_countdown_thompson_diagnostic_bundle,
)
from qmc_bmgs.substrate.budget import TRACK_A_WORK_AXES, TrackAWorkBudget
from qmc_bmgs.substrate.countdown_search import (
    TrackABudgetProfile,
    TrackAMethodSpec,
    replay_countdown_track_a_search_bytes,
    run_countdown_track_a_search,
    search_runtime_metadata,
)
from qmc_bmgs.substrate.perturbations import perturbation_runtime_metadata
from qmc_bmgs.substrate.proposals import TrackAProposalSpec
from qmc_bmgs.substrate.trace import (
    TraceValidationError,
    canonical_json,
    sha256_json,
    strict_json_loads,
)


RUN_MANIFEST_SCHEMA_VERSION = "qmc-bmgs-countdown-thompson-diagnostic-run-manifest/v1"
RUN_RECORD_SCHEMA_VERSION = "qmc-bmgs-countdown-thompson-diagnostic-run-record/v1"
_LEGACY_AUTHORIZATION_SCHEMA_VERSION = (
    "qmc-bmgs-countdown-thompson-diagnostic-execution-authorization/v1"
)
AUTHORIZATION_SCHEMA_VERSION = (
    "qmc-bmgs-countdown-thompson-diagnostic-execution-authorization/v2"
)
PUBLICATION_ENVIRONMENT_REQUIREMENTS_SCHEMA_VERSION = (
    "qmc-bmgs-countdown-thompson-publication-environment-requirements/v1"
)
_AUTHORIZATION_V2_FIELDS = frozenset(
    {
        "artifact_id",
        "artifact_layout",
        "authorization_scope",
        "bundle_id",
        "cell_count",
        "claim_boundary",
        "deterministic_digest",
        "diagnostic_seal_digest",
        "method_manifest_digest",
        "output_parent_binding",
        "output_parent_binding_digest",
        "output_path",
        "output_path_digest",
        "publication_backend",
        "publication_environment_requirements",
        "requires_explicit_digest_confirmation",
        "runner_build_attestation",
        "runtime_qualification",
        "runtime_qualification_digest",
        "schedule_digest",
        "schema_version",
    }
)
BUILD_ATTESTATION_SCHEMA_VERSION = (
    "qmc-bmgs-countdown-thompson-diagnostic-build-attestation/v1"
)
ATTEMPT_MARKER_SCHEMA_VERSION = (
    "qmc-bmgs-countdown-thompson-diagnostic-attempt-marker/v1"
)
ARTIFACT_COMMIT_SCHEMA_VERSION = (
    "qmc-bmgs-countdown-thompson-diagnostic-artifact-commit/v1"
)
ARTIFACT_FILENAMES = ("commit.json", "manifest.json", "records.jsonl")
EXPECTED_SEAL_DIGEST = (
    "cc633b9ee3ffda6a9115af07f0cc047a1bd8cd7af5e11d07f6ddb0faa4e5f975"
)
_DETERMINISTIC_METHOD_LABELS = ("greedy", "beam_width_2", "puct_c1")
_STOCHASTIC_METHOD_LABELS = (
    "thompson_candidate_iid_v1",
    "thompson_dimnorm_iid_v2",
    "thompson_dense_iid_v3",
    "thompson_greedy_anchor_dense_iid_v4",
)
_DIAGNOSTIC_EXPLORATION_SEEDS = (7168, 7169, 7170, 7171)
REQUIRED_ANCESTRY = (
    "0917d1d7e8e637610883c6ab5901a118a59ca264",
    "b7eb154d2f3af9112375835c70212b46a59bdab9",
    "2d4960e6f79a12f27ad8dc370b78e89b98958044",
    "9f0f0c9d07d9e7bf66caff5f664792b2160b4ea4",
    "0826aa3480d05453e6900b96aabea5445fa5fce7",
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
    "src/qmc_bmgs/experiments/countdown_thompson_regular_file_publication_v2.py",
    "src/qmc_bmgs/experiments/countdown_thompson_diagnostic_runner.py",
    "src/qmc_bmgs/experiments/countdown_thompson_diagnostic_analysis.py",
)
_PROTECTED_MODULE_PATHS = {
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
    canary_manifest.__name__: _RUNNER_SOURCE_PATHS[1],
    manifest.__name__: _RUNNER_SOURCE_PATHS[2],
    regular_file_publication.__name__: _RUNNER_SOURCE_PATHS[3],
    __name__: _RUNNER_SOURCE_PATHS[4],
    analysis.__name__: _RUNNER_SOURCE_PATHS[5],
}
_MICRO_TASK = CountdownTask((1, 2, 3, 4, 5, 6), target=720)
_TELEMETRY_ROLE = "descriptive_only_excluded_from_search_core_identity_and_gates"
_REGULAR_FILE_READ_CHUNK_BYTES = 1024 * 1024
_MAX_COMMIT_FILE_BYTES = 1 * 1024 * 1024
_MAX_CONTROL_FILE_BYTES = 8 * 1024 * 1024
_MAX_ATTESTED_FILE_BYTES = 512 * 1024 * 1024
_MAX_RECORDS_FILE_BYTES = 256 * 1024 * 1024
_PUBLICATION_BACKEND_UNAVAILABLE = "atomic_directory_authority_unavailable/v1"
_REGULAR_FILE_PUBLICATION_BACKEND = regular_file_publication.PUBLICATION_BACKEND
_REGULAR_FILE_ARTIFACT_LAYOUT = regular_file_publication.ARTIFACT_LAYOUT
_SYNTHETIC_PUBLICATION_BACKEND = "nondiagnostic_fixture_mkdir_open/v1"
_SYNTHETIC_AUTHORIZATION_SCHEMA_VERSION = (
    "qmc-bmgs-countdown-thompson-nondiagnostic-fixture-authorization/v1"
)
_SYNTHETIC_AUTHORIZATION_SCOPE = "one_nondiagnostic_synthetic_protocol_fixture"
_SYNTHETIC_AUTHORIZATION_CLAIM_BOUNDARY = (
    "synthetic protocol fixture authority only; no diagnostic execution, "
    "inferential, superiority, retry, or locked-evaluation authority is granted"
)
_PUBLICATION_BACKEND_REFUSAL = (
    "diagnostic execution remains fail-closed: portable atomic directory "
    "creation authority is unavailable and the production v2r3 publisher and "
    "analyzer are not integrated; no attempt or outcome was opened"
)
_SYNTHETIC_RUN_CLAIM_BOUNDARY = (
    "non-diagnostic synthetic protocol fixture; byte replay exercises plumbing "
    "only, telemetry is volatile, and no diagnostic, inferential, superiority, "
    "or locked-evaluation authority is granted"
)
_SYNTHETIC_EXPECTED_CELL_COUNT = 1
_SYNTHETIC_MICRO_FIXTURE_CONTENT_DIGEST = (
    "7e64bbfb3443f25dbb0fcbe6fe326711c5df81e9718333013207930d4c0be9a8"
)
_SYNTHETIC_HANDSHAKE_FIXTURE_CONTENT_DIGEST = (
    "ef097f451fe6af90ca7b8d6451c00ce959f8e54521a1fd148da2a25cb1683755"
)
_SYNTHETIC_FIXTURE_CONTENT_DIGESTS = frozenset(
    {
        _SYNTHETIC_MICRO_FIXTURE_CONTENT_DIGEST,
        _SYNTHETIC_HANDSHAKE_FIXTURE_CONTENT_DIGEST,
    }
)


class DiagnosticRunnerError(RuntimeError):
    """Raised before publication when runner authority or closure fails."""


class DiagnosticNotRunError(DiagnosticRunnerError):
    """A preflight/authorization refusal that opened no diagnostic search outcome."""


class DiagnosticInvalidRunError(DiagnosticRunnerError):
    """An authorized attempt that reached STARTED but did not commit."""


class DiagnosticPublicationStateAmbiguousError(DiagnosticRunnerError):
    """Publication durability and exact rollback could not be established."""


class _PublicationLockRetirementAmbiguousError(
    DiagnosticPublicationStateAmbiguousError
):
    """The transient publication lock could not be retired without ambiguity."""


class _ExactPublicationRevokedError(DiagnosticRunnerError):
    """An exact staged publication was durably shown absent after failure."""


def _close_descriptor_best_effort(descriptor: int) -> None:
    """Close one descriptor without replacing an already-decided outcome."""

    if descriptor < 0:
        return
    try:
        os.close(descriptor)
    except BaseException:
        pass


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return (canonical_json(payload) + "\n").encode("utf-8")


def _with_digest(payload: Mapping[str, Any]) -> dict[str, Any]:
    core = deepcopy(dict(payload))
    core["deterministic_digest"] = sha256_json(core)
    return core


def _require_sha256(value: object, label: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise DiagnosticRunnerError(f"{label} must be lowercase SHA-256")
    return value


def _require_git_oid(value: object, label: str) -> str:
    """Require a full lowercase Git object ID for SHA-1 or SHA-256 repos."""

    if (
        type(value) is not str
        or len(value) not in {40, 64}
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise DiagnosticRunnerError(
            f"{label} must be a full lowercase SHA-1 or SHA-256 Git object ID"
        )
    return value


def _strict_canonical_object(path: Path) -> tuple[dict[str, Any], bytes]:
    candidate = Path(path)
    raw = _read_regular_file_nofollow(
        candidate,
        "authorization",
        max_bytes=_MAX_CONTROL_FILE_BYTES,
    )
    try:
        parsed = strict_json_loads(raw.decode("utf-8"))
        canonical = _canonical_bytes(parsed) if type(parsed) is dict else None
    except RecursionError as error:
        raise DiagnosticRunnerError(
            "authorization JSON nesting exceeds the supported depth"
        ) from error
    except (UnicodeDecodeError, TraceValidationError) as error:
        raise DiagnosticRunnerError("authorization is not strict UTF-8 JSON") from error
    if type(parsed) is not dict or raw != canonical:
        raise DiagnosticRunnerError("authorization is not a canonical JSON object")
    return parsed, raw


def _stable_stat_signature(observed: os.stat_result) -> tuple[int, ...]:
    """Return metadata that must remain fixed across one authority observation."""

    return (
        observed.st_dev,
        observed.st_ino,
        observed.st_mode,
        observed.st_nlink,
        observed.st_size,
        observed.st_mtime_ns,
        observed.st_ctime_ns,
    )


def _read_exact_descriptor_bytes(
    descriptor: int,
    byte_count: int,
    *,
    label: str,
) -> bytes:
    """Read exactly a bounded regular-file extent and require immediate EOF."""

    payload = bytearray()
    remaining = byte_count
    try:
        while remaining:
            chunk = os.read(
                descriptor,
                min(remaining, _REGULAR_FILE_READ_CHUNK_BYTES),
            )
            if not chunk:
                raise DiagnosticRunnerError(
                    f"{label} became shorter during observation"
                )
            payload.extend(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise DiagnosticRunnerError(f"{label} grew during observation")
    except BlockingIOError as error:
        raise DiagnosticRunnerError(
            f"{label} did not provide bounded regular-file bytes"
        ) from error
    return bytes(payload)


def _read_regular_file_nofollow(
    path: Path,
    label: str,
    *,
    max_bytes: int = _MAX_ATTESTED_FILE_BYTES,
) -> bytes:
    """Read one stable bounded regular file without following its final name."""

    candidate = Path(path)
    descriptor = -1
    try:
        before = os.stat(candidate, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode) or before.st_size > max_bytes:
            raise DiagnosticRunnerError(
                f"{label} is not a regular file within the bounded size limit: "
                f"{candidate}"
            )
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        flags |= getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(candidate, flags)
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or _stable_stat_signature(
            opened
        ) != _stable_stat_signature(before):
            raise DiagnosticRunnerError(
                f"{label} changed while its regular file was opened: {candidate}"
            )
        raw = _read_exact_descriptor_bytes(
            descriptor,
            opened.st_size,
            label=label,
        )
        after_descriptor = os.fstat(descriptor)
        after_path = os.stat(candidate, follow_symlinks=False)
        signature = _stable_stat_signature(opened)
        if (
            _stable_stat_signature(after_descriptor) != signature
            or _stable_stat_signature(after_path) != signature
        ):
            raise DiagnosticRunnerError(
                f"{label} changed during regular-file observation: {candidate}"
            )
        return raw
    except DiagnosticRunnerError:
        raise
    except OSError as error:
        raise DiagnosticRunnerError(
            f"{label} is not a stable bounded regular file: {candidate}"
        ) from error
    finally:
        _close_descriptor_best_effort(descriptor)


def _open_stable_directory(path: Path, label: str) -> tuple[int, os.stat_result]:
    """Open one canonical directory and bind its current filesystem identity."""

    if os.name != "posix":
        raise DiagnosticRunnerError(f"{label} requires POSIX descriptor semantics")
    candidate = Path(path)
    try:
        if candidate.resolve() != candidate:
            raise DiagnosticRunnerError(f"{label} must not traverse symlinks")
        before = os.stat(candidate, follow_symlinks=False)
        if not stat.S_ISDIR(before.st_mode):
            raise DiagnosticRunnerError(f"{label} must be a directory")
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(candidate, flags)
        opened = os.fstat(descriptor)
    except OSError as error:
        raise DiagnosticRunnerError(f"{label} must be a stable directory") from error
    if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
        _close_descriptor_best_effort(descriptor)
        raise DiagnosticRunnerError(f"{label} changed while it was opened")
    return descriptor, opened


def _assert_directory_path_identity(
    path: Path,
    descriptor: int,
    expected: os.stat_result,
    label: str,
) -> None:
    """Require the lexical path still names the pinned directory descriptor."""

    try:
        if Path(path).resolve() != Path(path):
            raise DiagnosticRunnerError(f"{label} now traverses a symlink")
        observed = os.stat(path, follow_symlinks=False)
        opened = os.fstat(descriptor)
    except OSError as error:
        raise DiagnosticRunnerError(f"{label} path identity is unavailable") from error
    identity = (expected.st_dev, expected.st_ino)
    if (observed.st_dev, observed.st_ino) != identity or (
        opened.st_dev,
        opened.st_ino,
    ) != identity:
        raise DiagnosticRunnerError(f"{label} path identity changed")


_PathGeneration = tuple[tuple[str, tuple[int, ...]], ...]


def _capture_canonical_path_generation(
    path: Path,
    expected_identity: tuple[int, int],
    label: str,
) -> _PathGeneration:
    """Capture non-symlink ancestor generations for one canonical directory."""

    candidate = Path(os.path.abspath(os.fspath(path)))
    try:
        if candidate.resolve() != candidate:
            raise DiagnosticPublicationStateAmbiguousError(
                f"{label} now traverses a symlink"
            )
        current = Path(candidate.anchor)
        captured: list[tuple[str, tuple[int, ...]]] = []
        captured.append((os.fspath(current), _stable_stat_signature(os.lstat(current))))
        for component in candidate.parts[1:]:
            current /= component
            captured.append(
                (os.fspath(current), _stable_stat_signature(os.lstat(current)))
            )
        opened = os.stat(candidate, follow_symlinks=False)
    except DiagnosticPublicationStateAmbiguousError:
        raise
    except (OSError, RuntimeError) as error:
        raise DiagnosticPublicationStateAmbiguousError(
            f"{label} path generation is unavailable"
        ) from error
    if (
        not stat.S_ISDIR(opened.st_mode)
        or (opened.st_dev, opened.st_ino) != expected_identity
    ):
        raise DiagnosticPublicationStateAmbiguousError(f"{label} path identity changed")
    return tuple(captured)


def _rename_noreplace_at(
    source_directory_fd: int,
    source_name: str,
    destination_directory_fd: int,
    destination_name: str,
) -> None:
    """Atomically rename relative to pinned directories without replacement."""

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
            source_directory_fd,
            source,
            destination_directory_fd,
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
            source_directory_fd,
            source,
            destination_directory_fd,
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


@dataclass(frozen=True)
class _PinnedRegularFileObservation:
    descriptor: int
    signature: tuple[int, ...]


def _pin_bounded_regular_file_at(
    directory_fd: int,
    filename: str,
    *,
    expected_size: int,
    max_bytes: int,
    expected_bytes: bytes | None = None,
    expected_sha256: str | None = None,
    expected_identity: tuple[int, int] | None = None,
) -> _PinnedRegularFileObservation | None:
    """Read and retain one exact descriptor-relative regular-file snapshot."""

    if (
        type(expected_size) is not int
        or expected_size < 0
        or expected_size > max_bytes
        or (expected_bytes is not None and len(expected_bytes) != expected_size)
    ):
        return None
    try:
        before = os.stat(filename, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(before.st_mode) or before.st_size != expected_size:
        return None

    descriptor = -1
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        flags |= getattr(os, "O_NONBLOCK", 0)
        try:
            descriptor = os.open(filename, flags, dir_fd=directory_fd)
        except FileNotFoundError:
            return None
        opened = os.fstat(descriptor)
        signature = _stable_stat_signature(opened)
        identity = (opened.st_dev, opened.st_ino)
        if (
            not stat.S_ISREG(opened.st_mode)
            or signature != _stable_stat_signature(before)
            or (expected_identity is not None and identity != expected_identity)
        ):
            return None

        hasher = hashlib.sha256() if expected_sha256 is not None else None
        offset = 0
        matches = True
        remaining = expected_size
        while remaining:
            chunk = os.read(
                descriptor,
                min(remaining, _REGULAR_FILE_READ_CHUNK_BYTES),
            )
            if not chunk:
                return None
            if (
                expected_bytes is not None
                and chunk != expected_bytes[offset : offset + len(chunk)]
            ):
                matches = False
            if hasher is not None:
                hasher.update(chunk)
            offset += len(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            return None

        after_descriptor = os.fstat(descriptor)
        try:
            after_path = os.stat(
                filename,
                dir_fd=directory_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            return None
        if (
            _stable_stat_signature(after_descriptor) != signature
            or _stable_stat_signature(after_path) != signature
        ):
            return None
        if not matches or (
            hasher is not None and hasher.hexdigest() != expected_sha256
        ):
            return None
        pinned = _PinnedRegularFileObservation(
            descriptor=descriptor,
            signature=signature,
        )
        descriptor = -1
        return pinned
    finally:
        _close_descriptor_best_effort(descriptor)


def _bounded_regular_file_identity_at(
    directory_fd: int,
    filename: str,
    *,
    expected_size: int,
    max_bytes: int,
    expected_bytes: bytes | None = None,
    expected_sha256: str | None = None,
    expected_identity: tuple[int, int] | None = None,
) -> tuple[int, int] | None:
    """Stream one exact descriptor-relative regular file without blocking."""

    pinned = _pin_bounded_regular_file_at(
        directory_fd,
        filename,
        expected_size=expected_size,
        max_bytes=max_bytes,
        expected_bytes=expected_bytes,
        expected_sha256=expected_sha256,
        expected_identity=expected_identity,
    )
    if pinned is None:
        return None
    try:
        after_descriptor = os.fstat(pinned.descriptor)
        try:
            after_path = os.stat(
                filename,
                dir_fd=directory_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            return None
        if (
            _stable_stat_signature(after_descriptor) != pinned.signature
            or _stable_stat_signature(after_path) != pinned.signature
        ):
            return None
        return pinned.signature[0], pinned.signature[1]
    finally:
        _close_descriptor_best_effort(pinned.descriptor)


def _exact_regular_file_identity_at(
    directory_fd: int,
    filename: str,
    expected: bytes,
    *,
    expected_identity: tuple[int, int] | None = None,
    label: str,
) -> tuple[int, int] | None:
    """Return the pinned identity of one exact file, absent/different, or raise."""

    try:
        return _bounded_regular_file_identity_at(
            directory_fd,
            filename,
            expected_size=len(expected),
            max_bytes=_MAX_CONTROL_FILE_BYTES,
            expected_bytes=expected,
            expected_identity=expected_identity,
        )
    except OSError as error:
        raise DiagnosticPublicationStateAmbiguousError(
            f"{label} observation failed: {filename}"
        ) from error


def _durably_prove_file_not_exact_at(
    directory_fd: int,
    filename: str,
    expected: bytes,
    *,
    expected_identity: tuple[int, int] | None = None,
    label: str,
) -> bool:
    """Barrier the namespace and confirm an exact authority file is not named."""

    try:
        os.fsync(directory_fd)
    except OSError as error:
        raise DiagnosticPublicationStateAmbiguousError(
            f"{label} absence durability failed: {filename}"
        ) from error
    return (
        _exact_regular_file_identity_at(
            directory_fd,
            filename,
            expected,
            expected_identity=expected_identity,
            label=label,
        )
        is None
    )


def _restore_quarantined_entry_at(
    directory_fd: int,
    tombstone_name: str,
    filename: str,
    *,
    captured_identity: tuple[int, int],
) -> bool:
    """Restore one raced foreign entry without ever deleting it."""

    try:
        _rename_noreplace_at(
            directory_fd,
            tombstone_name,
            directory_fd,
            filename,
        )
    except BaseException:
        pass
    try:
        restored = os.stat(filename, dir_fd=directory_fd, follow_symlinks=False)
        os.stat(tombstone_name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        try:
            restored = os.stat(filename, dir_fd=directory_fd, follow_symlinks=False)
        except OSError:
            return False
        if (restored.st_dev, restored.st_ino) != captured_identity:
            return False
        try:
            os.fsync(directory_fd)
        except OSError:
            return False
        return True
    except OSError:
        return False
    return False


def _quarantine_exact_file_at(
    directory_fd: int,
    filename: str,
    expected: bytes,
    *,
    expected_identity: tuple[int, int] | None,
    label: str,
) -> str | None:
    """Revoke an exact file by atomically renaming it to a retained tombstone."""

    tombstone_name = ""
    rename_error: BaseException | None = None
    for _attempt in range(128):
        candidate = f".{filename}.revoked-{secrets.token_hex(16)}"
        try:
            _rename_noreplace_at(
                directory_fd,
                filename,
                directory_fd,
                candidate,
            )
        except FileExistsError:
            continue
        except BaseException as error:
            tombstone_name = candidate
            rename_error = error
            break
        tombstone_name = candidate
        break
    if not tombstone_name:
        raise DiagnosticPublicationStateAmbiguousError(
            f"could not allocate {label} tombstone"
        )

    captured = _exact_regular_file_identity_at(
        directory_fd,
        tombstone_name,
        expected,
        expected_identity=expected_identity,
        label=f"quarantined {label}",
    )
    if captured is None:
        try:
            foreign = os.stat(
                tombstone_name,
                dir_fd=directory_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            foreign = None
        except OSError as error:
            raise DiagnosticPublicationStateAmbiguousError(
                f"quarantined {label} observation failed"
            ) from error
        if foreign is not None:
            foreign_identity = (foreign.st_dev, foreign.st_ino)
            if not _restore_quarantined_entry_at(
                directory_fd,
                tombstone_name,
                filename,
                captured_identity=foreign_identity,
            ):
                raise DiagnosticPublicationStateAmbiguousError(
                    f"foreign {label} was quarantined and could not be restored"
                ) from rename_error
        if not _durably_prove_file_not_exact_at(
            directory_fd,
            filename,
            expected,
            expected_identity=expected_identity,
            label=label,
        ):
            raise DiagnosticPublicationStateAmbiguousError(
                f"exact {label} remained after quarantine failure"
            ) from rename_error
        return None

    try:
        os.fsync(directory_fd)
    except OSError as error:
        raise DiagnosticPublicationStateAmbiguousError(
            f"{label} tombstone durability failed"
        ) from error
    if (
        _exact_regular_file_identity_at(
            directory_fd,
            tombstone_name,
            expected,
            expected_identity=expected_identity,
            label=f"quarantined {label}",
        )
        is None
    ):
        raise DiagnosticPublicationStateAmbiguousError(
            f"exact {label} tombstone changed after the durability barrier"
        )
    if not _durably_prove_file_not_exact_at(
        directory_fd,
        filename,
        expected,
        expected_identity=expected_identity,
        label=label,
    ):
        raise DiagnosticPublicationStateAmbiguousError(
            f"exact {label} remained named after tombstoning"
        )
    return tombstone_name


def _write_canonical_file_noreplace_at(
    directory_fd: int,
    filename: str,
    payload: Mapping[str, Any],
) -> tuple[int, int]:
    """Publish one canonical file with an exact directory-durability proof."""

    if Path(filename).name != filename or not filename:
        raise DiagnosticRunnerError("descriptor-relative filename is invalid")
    temporary_name = ""
    file_descriptor = -1
    raw = _canonical_bytes(payload)
    staging_identity: tuple[int, int] | None = None
    try:
        for _attempt in range(128):
            candidate = f".{filename}.tmp-{secrets.token_hex(16)}"
            try:
                file_descriptor = os.open(
                    candidate,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                    dir_fd=directory_fd,
                )
            except FileExistsError:
                continue
            temporary_name = candidate
            break
        if file_descriptor < 0:
            raise DiagnosticRunnerError("could not allocate receipt staging file")
        with os.fdopen(file_descriptor, "wb") as handle:
            file_descriptor = -1
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
            staged = os.fstat(handle.fileno())
        staging_identity = (staged.st_dev, staged.st_ino)
        publication_error: BaseException | None = None
        try:
            _rename_noreplace_at(
                directory_fd,
                temporary_name,
                directory_fd,
                filename,
            )
        except BaseException as error:
            publication_error = error
        else:
            temporary_name = ""

        exact_is_named = _published_file_matches(
            directory_fd,
            filename,
            staging_identity,
            raw,
        )
        if exact_is_named:
            temporary_name = ""
            try:
                os.fsync(directory_fd)
                if _published_file_matches(
                    directory_fd,
                    filename,
                    staging_identity,
                    raw,
                ):
                    return staging_identity
            except BaseException as error:
                publication_error = publication_error or error
            try:
                os.fsync(directory_fd)
                if _published_file_matches(
                    directory_fd,
                    filename,
                    staging_identity,
                    raw,
                ):
                    return staging_identity
            except BaseException as error:
                publication_error = publication_error or error
            _quarantine_exact_file_at(
                directory_fd,
                filename,
                raw,
                expected_identity=staging_identity,
                label=filename,
            )
            raise _ExactPublicationRevokedError(
                f"{filename} publication was durably tombstoned"
            ) from publication_error

        if not _durably_prove_file_not_exact_at(
            directory_fd,
            filename,
            raw,
            expected_identity=staging_identity,
            label=filename,
        ):
            raise DiagnosticPublicationStateAmbiguousError(
                f"{filename} publication state changed during absence proof"
            ) from publication_error
        raise _ExactPublicationRevokedError(
            f"{filename} publication did not become durable"
        ) from publication_error
    finally:
        if file_descriptor >= 0:
            _close_descriptor_best_effort(file_descriptor)
        if temporary_name and staging_identity is not None:
            try:
                _quarantine_exact_file_at(
                    directory_fd,
                    temporary_name,
                    raw,
                    expected_identity=staging_identity,
                    label="receipt staging file",
                )
            except BaseException:
                # Never let best-effort scratch cleanup replace the primary
                # publication result, and never unlink a raced foreign entry.
                pass


def _read_regular_file_at(
    directory_fd: int,
    filename: str,
    *,
    max_bytes: int = _MAX_CONTROL_FILE_BYTES,
) -> bytes:
    """Read one stable bounded descriptor-relative control file."""

    before = os.stat(filename, dir_fd=directory_fd, follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode) or before.st_size > max_bytes:
        raise DiagnosticRunnerError("attempt receipt is not a bounded regular file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(filename, flags, dir_fd=directory_fd)
    try:
        opened = os.fstat(descriptor)
        signature = _stable_stat_signature(opened)
        if not stat.S_ISREG(opened.st_mode) or signature != _stable_stat_signature(
            before
        ):
            raise DiagnosticRunnerError(
                "attempt receipt changed while its regular file was opened"
            )
        raw = _read_exact_descriptor_bytes(
            descriptor,
            opened.st_size,
            label="attempt receipt",
        )
        after_descriptor = os.fstat(descriptor)
        after_path = os.stat(
            filename,
            dir_fd=directory_fd,
            follow_symlinks=False,
        )
        if (
            _stable_stat_signature(after_descriptor) != signature
            or _stable_stat_signature(after_path) != signature
        ):
            raise DiagnosticRunnerError(
                "attempt receipt changed during regular-file observation"
            )
        return raw
    finally:
        _close_descriptor_best_effort(descriptor)


def _published_file_matches(
    directory_fd: int,
    filename: str,
    staging_identity: tuple[int, int],
    expected: bytes,
) -> bool:
    """Prove one published file is the exact staged inode and byte payload."""

    try:
        return (
            _bounded_regular_file_identity_at(
                directory_fd,
                filename,
                expected_size=len(expected),
                max_bytes=_MAX_CONTROL_FILE_BYTES,
                expected_bytes=expected,
                expected_identity=staging_identity,
            )
            is not None
        )
    except OSError as error:
        raise DiagnosticPublicationStateAmbiguousError(
            f"published file observation failed: {filename}"
        ) from error


def _directory_has_exact_entries(
    directory_fd: int,
    expected_filenames: set[str],
) -> bool:
    """Check exact directory closure with bounded iteration and early exit."""

    remaining = set(expected_filenames)
    with os.scandir(directory_fd) as entries:
        for entry in entries:
            if entry.name not in remaining:
                return False
            remaining.remove(entry.name)
    return not remaining


def _revoke_published_file_at(
    directory_fd: int,
    filename: str,
    staging_identity: tuple[int, int],
    expected: bytes,
) -> bool:
    """Tombstone one exact published file and durably prove name revocation."""

    identity = _exact_regular_file_identity_at(
        directory_fd,
        filename,
        expected,
        expected_identity=staging_identity,
        label="published file",
    )
    if identity is None:
        return False
    _quarantine_exact_file_at(
        directory_fd,
        filename,
        expected,
        expected_identity=identity,
        label="published file",
    )
    return True


def _published_artifact_matches(
    parent_fd: int,
    output_name: str,
    staging_identity: tuple[int, int],
    run_manifest: Mapping[str, Any],
    *,
    records_byte_count: int,
    records_sha256: str,
    commit_receipt: Mapping[str, Any] | None,
) -> bool:
    """Prove the published entry is the exact READY core or committed artifact."""

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    member_snapshots: dict[str, _PinnedRegularFileObservation] = {}
    try:
        output_fd = os.open(output_name, flags, dir_fd=parent_fd)
    except FileNotFoundError:
        return False
    except OSError as error:
        raise DiagnosticPublicationStateAmbiguousError(
            f"published artifact observation failed: {output_name}"
        ) from error
    try:
        observed = os.fstat(output_fd)
        if (observed.st_dev, observed.st_ino) != staging_identity:
            return False
        directory_signature = _stable_stat_signature(observed)
        expected_filenames = {"manifest.json", "records.jsonl"}
        if commit_receipt is not None:
            expected_filenames.add("commit.json")
        if not _directory_has_exact_entries(output_fd, expected_filenames):
            return False
        manifest_bytes = _canonical_bytes(run_manifest)
        manifest_snapshot = _pin_bounded_regular_file_at(
            output_fd,
            "manifest.json",
            expected_size=len(manifest_bytes),
            max_bytes=_MAX_CONTROL_FILE_BYTES,
            expected_bytes=manifest_bytes,
        )
        if manifest_snapshot is None:
            return False
        member_snapshots["manifest.json"] = manifest_snapshot
        records_snapshot = _pin_bounded_regular_file_at(
            output_fd,
            "records.jsonl",
            expected_size=records_byte_count,
            max_bytes=_MAX_RECORDS_FILE_BYTES,
            expected_sha256=records_sha256,
        )
        if records_snapshot is None:
            return False
        member_snapshots["records.jsonl"] = records_snapshot
        if commit_receipt is not None:
            commit_bytes = _canonical_bytes(commit_receipt)
            commit_snapshot = _pin_bounded_regular_file_at(
                output_fd,
                "commit.json",
                expected_size=len(commit_bytes),
                max_bytes=_MAX_COMMIT_FILE_BYTES,
                expected_bytes=commit_bytes,
            )
            if commit_snapshot is None:
                return False
            member_snapshots["commit.json"] = commit_snapshot
        if not _directory_has_exact_entries(output_fd, expected_filenames):
            return False
        descriptor_signatures = {
            filename: _stable_stat_signature(os.fstat(snapshot.descriptor))
            for filename, snapshot in member_snapshots.items()
        }
        named_signatures = {
            filename: _stable_stat_signature(
                os.stat(
                    filename,
                    dir_fd=output_fd,
                    follow_symlinks=False,
                )
            )
            for filename in expected_filenames
        }
        final_path = os.stat(
            output_name,
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
        return (
            all(
                named_signatures[filename] == snapshot.signature
                and descriptor_signatures[filename] == snapshot.signature
                for filename, snapshot in member_snapshots.items()
            )
            and stat.S_ISDIR(final_path.st_mode)
            and _stable_stat_signature(final_path) == directory_signature
            and (final_path.st_dev, final_path.st_ino) == staging_identity
            and _stable_stat_signature(os.fstat(output_fd)) == directory_signature
        )
    except DiagnosticPublicationStateAmbiguousError:
        raise
    except (FileNotFoundError, DiagnosticRunnerError):
        return False
    except OSError as error:
        raise DiagnosticPublicationStateAmbiguousError(
            f"published artifact observation failed: {output_name}"
        ) from error
    finally:
        for snapshot in member_snapshots.values():
            _close_descriptor_best_effort(snapshot.descriptor)
        _close_descriptor_best_effort(output_fd)


def _published_artifact_content_identity(
    parent_fd: int,
    output_name: str,
    run_manifest: Mapping[str, Any],
    *,
    records_byte_count: int,
    records_sha256: str,
    commit_receipt: Mapping[str, Any],
) -> tuple[int, int] | None:
    """Return the stable public directory identity for exact committed bytes.

    Recovery normally requires the original staging directory identity.  This
    weaker observation is used only to prevent an INVALID transition while a
    byte-identical, analyzer-acceptable three-member artifact remains publicly
    named through a replacement directory inode.
    """

    try:
        observed = os.stat(
            output_name,
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return None
    except OSError as error:
        raise DiagnosticPublicationStateAmbiguousError(
            f"published artifact observation failed: {output_name}"
        ) from error
    if not stat.S_ISDIR(observed.st_mode):
        return None
    identity = observed.st_dev, observed.st_ino
    if not _published_artifact_matches(
        parent_fd,
        output_name,
        identity,
        run_manifest,
        records_byte_count=records_byte_count,
        records_sha256=records_sha256,
        commit_receipt=commit_receipt,
    ):
        return None
    return identity


def _revoke_public_exact_committed_artifact(
    parent_fd: int,
    output_name: str,
    run_manifest: Mapping[str, Any],
    *,
    records_byte_count: int,
    records_sha256: str,
    commit_receipt: Mapping[str, Any],
) -> bool:
    """Tombstone only commit.json from one exact public three-file artifact."""

    public_identity = _published_artifact_content_identity(
        parent_fd,
        output_name,
        run_manifest,
        records_byte_count=records_byte_count,
        records_sha256=records_sha256,
        commit_receipt=commit_receipt,
    )
    if public_identity is None:
        return False
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    output_fd = -1
    try:
        output_fd = os.open(output_name, flags, dir_fd=parent_fd)
        opened = os.fstat(output_fd)
        if (opened.st_dev, opened.st_ino) != public_identity:
            raise DiagnosticPublicationStateAmbiguousError(
                "exact public artifact changed before commit revocation"
            )
        if not _published_artifact_matches(
            parent_fd,
            output_name,
            public_identity,
            run_manifest,
            records_byte_count=records_byte_count,
            records_sha256=records_sha256,
            commit_receipt=commit_receipt,
        ):
            raise DiagnosticPublicationStateAmbiguousError(
                "exact public artifact changed before commit revocation"
            )
        commit_identity = _exact_regular_file_identity_at(
            output_fd,
            "commit.json",
            _canonical_bytes(commit_receipt),
            label="artifact commit",
        )
        if commit_identity is None:
            raise DiagnosticPublicationStateAmbiguousError(
                "exact public artifact commit disappeared before revocation"
            )
        tombstone = _quarantine_exact_file_at(
            output_fd,
            "commit.json",
            _canonical_bytes(commit_receipt),
            expected_identity=commit_identity,
            label="artifact commit",
        )
        if tombstone is None:
            raise DiagnosticPublicationStateAmbiguousError(
                "exact public artifact commit revocation is unproven"
            )
        return True
    except DiagnosticPublicationStateAmbiguousError:
        raise
    except OSError as error:
        raise DiagnosticPublicationStateAmbiguousError(
            "exact public artifact commit revocation failed"
        ) from error
    finally:
        _close_descriptor_best_effort(output_fd)


def _assert_started_output_parent_identity(
    parent: Path,
    parent_fd: int,
    parent_stat: os.stat_result,
) -> None:
    """Keep lexical output-parent drift typed after STARTED."""

    try:
        _assert_directory_path_identity(
            parent,
            parent_fd,
            parent_stat,
            "run output parent",
        )
    except BaseException as error:
        raise DiagnosticPublicationStateAmbiguousError(
            "run output parent identity drifted after STARTED"
        ) from error


def _assert_attempt_entry_identity(
    attempt: _Attempt,
    parent_fd: int,
) -> None:
    """Require the canonical attempt name to retain the reserved directory."""

    named_fd = -1
    try:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        named_fd = os.open(attempt.directory_name, flags, dir_fd=parent_fd)
        named = os.fstat(named_fd)
        pinned = os.fstat(attempt.directory_fd)
        named_after = os.stat(
            attempt.directory_name,
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
    except BaseException as error:
        raise DiagnosticPublicationStateAmbiguousError(
            "attempt reservation canonical identity is unavailable"
        ) from error
    finally:
        _close_descriptor_best_effort(named_fd)
    if (
        not stat.S_ISDIR(named.st_mode)
        or not stat.S_ISDIR(pinned.st_mode)
        or not stat.S_ISDIR(named_after.st_mode)
        or (named.st_dev, named.st_ino) != attempt.directory_identity
        or (pinned.st_dev, pinned.st_ino) != attempt.directory_identity
        or (named_after.st_dev, named_after.st_ino) != attempt.directory_identity
    ):
        raise DiagnosticPublicationStateAmbiguousError(
            "attempt reservation canonical identity drifted after publication"
        )


_MemberGeneration = tuple[tuple[str, tuple[int, ...] | None], ...]
_DirectoryMemberGeneration = tuple[tuple[int, ...], _MemberGeneration]
_NamedDirectoryGeneration = tuple[
    tuple[int, ...] | None,
    _DirectoryMemberGeneration | None,
]
_TerminalCollectiveGeneration = tuple[
    _PathGeneration,
    tuple[int, ...],
    _DirectoryMemberGeneration,
    _NamedDirectoryGeneration,
    _DirectoryMemberGeneration | None,
]


def _optional_entry_signature_at(
    directory_fd: int,
    filename: str,
    label: str,
) -> tuple[int, ...] | None:
    try:
        return _stable_stat_signature(
            os.stat(filename, dir_fd=directory_fd, follow_symlinks=False)
        )
    except FileNotFoundError:
        return None
    except OSError as error:
        raise DiagnosticPublicationStateAmbiguousError(
            f"{label} entry generation is unavailable: {filename}"
        ) from error


def _capture_directory_member_generation(
    directory_fd: int,
    filenames: Sequence[str],
    label: str,
) -> _DirectoryMemberGeneration:
    """Capture one directory plus selected member non-ABA generations."""

    ordered = tuple(sorted(set(filenames)))
    if len(ordered) != len(tuple(filenames)) or any(
        not filename or Path(filename).name != filename for filename in ordered
    ):
        raise DiagnosticRunnerError(f"{label} generation member set is invalid")
    try:
        before_directory = os.fstat(directory_fd)
        if not stat.S_ISDIR(before_directory.st_mode):
            raise DiagnosticPublicationStateAmbiguousError(
                f"{label} is not a directory"
            )
        directory_signature = _stable_stat_signature(before_directory)
        members = tuple(
            (
                filename,
                _optional_entry_signature_at(directory_fd, filename, label),
            )
            for filename in ordered
        )
        after_directory = os.fstat(directory_fd)
        reobserved = tuple(
            (
                filename,
                _optional_entry_signature_at(directory_fd, filename, label),
            )
            for filename in ordered
        )
    except DiagnosticPublicationStateAmbiguousError:
        raise
    except OSError as error:
        raise DiagnosticPublicationStateAmbiguousError(
            f"{label} generation could not be captured"
        ) from error
    if (
        _stable_stat_signature(after_directory) != directory_signature
        or reobserved != members
    ):
        raise DiagnosticPublicationStateAmbiguousError(
            f"{label} changed during generation capture"
        )
    return directory_signature, members


def _capture_attempt_member_generation(
    attempt: _Attempt,
    parent_fd: int,
    filenames: Sequence[str],
) -> _DirectoryMemberGeneration:
    _assert_attempt_entry_identity(attempt, parent_fd)
    generation = _capture_directory_member_generation(
        attempt.directory_fd,
        filenames,
        "terminal attempt",
    )
    _assert_attempt_entry_identity(attempt, parent_fd)
    return generation


def _capture_named_directory_generation(
    parent_fd: int,
    name: str,
    filenames: Sequence[str],
    label: str,
    *,
    expected_identity: tuple[int, int] | None = None,
) -> _NamedDirectoryGeneration:
    """Capture a named entry and selected children when it is a directory."""

    entry_signature = _optional_entry_signature_at(parent_fd, name, label)
    if entry_signature is None:
        if expected_identity is not None:
            raise DiagnosticPublicationStateAmbiguousError(
                f"{label} disappeared during generation capture"
            )
        return None, None
    if not stat.S_ISDIR(entry_signature[2]):
        if expected_identity is not None:
            raise DiagnosticPublicationStateAmbiguousError(
                f"{label} is not the expected directory"
            )
        return entry_signature, None
    descriptor = -1
    try:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(name, flags, dir_fd=parent_fd)
        opened = os.fstat(descriptor)
        opened_signature = _stable_stat_signature(opened)
        if opened_signature != entry_signature:
            raise DiagnosticPublicationStateAmbiguousError(
                f"{label} changed before descriptor acquisition"
            )
        if (
            expected_identity is not None
            and (
                opened.st_dev,
                opened.st_ino,
            )
            != expected_identity
        ):
            raise DiagnosticPublicationStateAmbiguousError(f"{label} identity changed")
        generation = _capture_directory_member_generation(
            descriptor,
            filenames,
            label,
        )
        final_signature = _optional_entry_signature_at(parent_fd, name, label)
        if final_signature != entry_signature:
            raise DiagnosticPublicationStateAmbiguousError(
                f"{label} changed during generation capture"
            )
        return entry_signature, generation
    except DiagnosticPublicationStateAmbiguousError:
        raise
    except OSError as error:
        raise DiagnosticPublicationStateAmbiguousError(
            f"{label} generation could not be captured"
        ) from error
    finally:
        _close_descriptor_best_effort(descriptor)


def _capture_terminal_collective_generation(
    *,
    parent: Path,
    parent_fd: int,
    parent_stat: os.stat_result,
    attempt: _Attempt,
    attempt_filenames: Sequence[str],
    output_name: str,
    output_filenames: Sequence[str],
    output_fd: int = -1,
    expected_output_identity: tuple[int, int] | None = None,
) -> _TerminalCollectiveGeneration:
    """Capture path, attempt, public artifact, and pinned artifact generations."""

    parent_identity = (parent_stat.st_dev, parent_stat.st_ino)
    path_generation = _capture_canonical_path_generation(
        parent,
        parent_identity,
        "run output parent",
    )
    try:
        parent_signature = _stable_stat_signature(os.fstat(parent_fd))
    except OSError as error:
        raise DiagnosticPublicationStateAmbiguousError(
            "terminal authority parent descriptor is unavailable"
        ) from error
    attempt_generation = _capture_attempt_member_generation(
        attempt,
        parent_fd,
        attempt_filenames,
    )
    public_generation = _capture_named_directory_generation(
        parent_fd,
        output_name,
        output_filenames,
        "public run artifact",
        expected_identity=expected_output_identity,
    )
    pinned_generation = (
        _capture_directory_member_generation(
            output_fd,
            output_filenames,
            "pinned run artifact",
        )
        if output_fd >= 0
        else None
    )
    try:
        final_parent_signature = _stable_stat_signature(os.fstat(parent_fd))
    except OSError as error:
        raise DiagnosticPublicationStateAmbiguousError(
            "terminal authority parent descriptor is unavailable"
        ) from error
    final_path_generation = _capture_canonical_path_generation(
        parent,
        parent_identity,
        "run output parent",
    )
    if (
        final_parent_signature != parent_signature
        or final_path_generation != path_generation
    ):
        raise DiagnosticPublicationStateAmbiguousError(
            "terminal authority parent changed during generation capture"
        )
    return (
        path_generation,
        parent_signature,
        attempt_generation,
        public_generation,
        pinned_generation,
    )


def _attempt_success_closure_matches(
    attempt: _Attempt,
    success_receipts: Mapping[str, Mapping[str, Any]],
) -> bool:
    """Prove the exact three-receipt success namespace on the pinned attempt."""

    expected_filenames = {
        "pre_outcome.json",
        "ready_to_commit.json",
        "started.json",
    }
    if set(success_receipts) != expected_filenames:
        raise DiagnosticRunnerError("attempt success receipt set is invalid")
    try:
        before = os.fstat(attempt.directory_fd)
        directory_signature = _stable_stat_signature(before)
        if not _directory_has_exact_entries(
            attempt.directory_fd,
            expected_filenames,
        ):
            return False
        for filename, payload in success_receipts.items():
            if (
                _exact_regular_file_identity_at(
                    attempt.directory_fd,
                    filename,
                    _canonical_bytes(payload),
                    label=f"attempt success receipt {filename}",
                )
                is None
            ):
                return False
        if not _directory_has_exact_entries(
            attempt.directory_fd,
            expected_filenames,
        ):
            return False
        after = os.fstat(attempt.directory_fd)
    except DiagnosticPublicationStateAmbiguousError:
        raise
    except BaseException as error:
        raise DiagnosticPublicationStateAmbiguousError(
            "attempt success closure observation failed"
        ) from error
    return (
        stat.S_ISDIR(before.st_mode)
        and _stable_stat_signature(after) == directory_signature
        and (after.st_dev, after.st_ino) == attempt.directory_identity
    )


def _prove_attempt_terminal_authority(
    *,
    parent: Path,
    parent_fd: int,
    parent_stat: os.stat_result,
    attempt: _Attempt,
    required_receipts: Mapping[str, Mapping[str, Any]] | None = None,
    forbidden_entries: Sequence[str] | None = None,
    success_receipts: Mapping[str, Mapping[str, Any]] | None = None,
) -> bool:
    """Barrier and re-prove parent, reservation name, and optional success closure."""

    tracked_receipts: dict[str, bytes] = {}
    for receipt_set in (required_receipts, success_receipts):
        for filename, payload in (receipt_set or {}).items():
            canonical = _canonical_bytes(payload)
            if filename in tracked_receipts and tracked_receipts[filename] != canonical:
                raise DiagnosticRunnerError(
                    f"terminal attempt receipt expectation conflicts: {filename}"
                )
            tracked_receipts[filename] = canonical
    _assert_started_output_parent_identity(parent, parent_fd, parent_stat)
    _assert_attempt_entry_identity(attempt, parent_fd)
    try:
        os.fsync(attempt.directory_fd)
        terminal_namespace_signature = _stable_stat_signature(
            os.fstat(attempt.directory_fd)
        )
    except BaseException as error:
        raise DiagnosticPublicationStateAmbiguousError(
            "attempt reservation durability is unproven"
        ) from error
    receipt_generation = _capture_attempt_member_generation(
        attempt,
        parent_fd,
        tuple(tracked_receipts),
    )
    if required_receipts is not None:
        try:
            receipt_namespace_signature = _stable_stat_signature(
                os.fstat(attempt.directory_fd)
            )
            for filename, payload in required_receipts.items():
                if (
                    _exact_regular_file_identity_at(
                        attempt.directory_fd,
                        filename,
                        _canonical_bytes(payload),
                        label=f"terminal attempt receipt {filename}",
                    )
                    is None
                ):
                    raise DiagnosticPublicationStateAmbiguousError(
                        f"terminal attempt receipt drifted: {filename}"
                    )
            for filename in forbidden_entries or ():
                if Path(filename).name != filename or not filename:
                    raise DiagnosticRunnerError(
                        "forbidden terminal attempt entry name is invalid"
                    )
                try:
                    os.stat(
                        filename,
                        dir_fd=attempt.directory_fd,
                        follow_symlinks=False,
                    )
                except FileNotFoundError:
                    pass
                except OSError as error:
                    raise DiagnosticPublicationStateAmbiguousError(
                        f"forbidden terminal attempt entry could not be "
                        f"observed: {filename}"
                    ) from error
                else:
                    raise DiagnosticPublicationStateAmbiguousError(
                        f"forbidden terminal attempt entry exists: {filename}"
                    )
            if (
                _stable_stat_signature(os.fstat(attempt.directory_fd))
                != receipt_namespace_signature
            ):
                raise DiagnosticPublicationStateAmbiguousError(
                    "terminal attempt receipt namespace changed during proof"
                )
        except DiagnosticPublicationStateAmbiguousError:
            raise
        except BaseException as error:
            raise DiagnosticPublicationStateAmbiguousError(
                "terminal attempt receipt observation failed"
            ) from error
    success_matches = True
    if success_receipts is not None:
        success_matches = _attempt_success_closure_matches(
            attempt,
            success_receipts,
        )
    _assert_attempt_entry_identity(attempt, parent_fd)
    _assert_started_output_parent_identity(parent, parent_fd, parent_stat)
    try:
        terminal_namespace_after = _stable_stat_signature(
            os.fstat(attempt.directory_fd)
        )
    except BaseException as error:
        raise DiagnosticPublicationStateAmbiguousError(
            "terminal attempt namespace final observation failed"
        ) from error
    if terminal_namespace_after != terminal_namespace_signature:
        raise DiagnosticPublicationStateAmbiguousError(
            "terminal attempt namespace changed during collective proof"
        )
    if (
        _capture_attempt_member_generation(
            attempt,
            parent_fd,
            tuple(tracked_receipts),
        )
        != receipt_generation
    ):
        raise DiagnosticPublicationStateAmbiguousError(
            "terminal attempt receipt generation changed during collective proof"
        )
    return success_matches


def _prove_committed_terminal_collective(
    *,
    parent: Path,
    parent_fd: int,
    parent_stat: os.stat_result,
    attempt: _Attempt,
    success_receipts: Mapping[str, Mapping[str, Any]],
    output_name: str,
    output_fd: int,
    staging_identity: tuple[int, int],
    run_manifest: Mapping[str, Any],
    records_byte_count: int,
    records_sha256: str,
    commit_receipt: Mapping[str, Any],
) -> bool:
    """Prove committed artifact and attempt in one non-ABA generation."""

    artifact_filenames = ("commit.json", "manifest.json", "records.jsonl")
    attempt_filenames = tuple(success_receipts)
    before_generation = _capture_terminal_collective_generation(
        parent=parent,
        parent_fd=parent_fd,
        parent_stat=parent_stat,
        attempt=attempt,
        attempt_filenames=attempt_filenames,
        output_name=output_name,
        output_filenames=artifact_filenames,
        output_fd=output_fd,
        expected_output_identity=staging_identity,
    )
    if not _published_artifact_matches(
        parent_fd,
        output_name,
        staging_identity,
        run_manifest,
        records_byte_count=records_byte_count,
        records_sha256=records_sha256,
        commit_receipt=commit_receipt,
    ):
        return False
    if not _prove_attempt_terminal_authority(
        parent=parent,
        parent_fd=parent_fd,
        parent_stat=parent_stat,
        attempt=attempt,
        success_receipts=success_receipts,
    ):
        return False
    if not _published_artifact_matches(
        parent_fd,
        output_name,
        staging_identity,
        run_manifest,
        records_byte_count=records_byte_count,
        records_sha256=records_sha256,
        commit_receipt=commit_receipt,
    ):
        return False
    after_generation = _capture_terminal_collective_generation(
        parent=parent,
        parent_fd=parent_fd,
        parent_stat=parent_stat,
        attempt=attempt,
        attempt_filenames=attempt_filenames,
        output_name=output_name,
        output_filenames=artifact_filenames,
        output_fd=output_fd,
        expected_output_identity=staging_identity,
    )
    if after_generation != before_generation:
        raise DiagnosticPublicationStateAmbiguousError(
            "committed artifact and attempt changed during collective proof"
        )
    return True


def _prove_invalid_terminal_collective(
    *,
    parent: Path,
    parent_fd: int,
    parent_stat: os.stat_result,
    attempt: _Attempt,
    invalid_receipt: Mapping[str, Any],
    output_name: str,
    output_fd: int,
    run_manifest: Mapping[str, Any],
    records_byte_count: int,
    records_sha256: str,
    commit_receipt: Mapping[str, Any],
) -> None:
    """Prove INVALID receipt and committed-artifact absence collectively."""

    artifact_filenames = ("commit.json", "manifest.json", "records.jsonl")
    attempt_filenames = ("invalid.json",)
    before_generation = _capture_terminal_collective_generation(
        parent=parent,
        parent_fd=parent_fd,
        parent_stat=parent_stat,
        attempt=attempt,
        attempt_filenames=attempt_filenames,
        output_name=output_name,
        output_filenames=artifact_filenames,
        output_fd=output_fd,
    )
    _prove_attempt_terminal_authority(
        parent=parent,
        parent_fd=parent_fd,
        parent_stat=parent_stat,
        attempt=attempt,
        required_receipts={"invalid.json": invalid_receipt},
    )
    if output_fd >= 0 and not _durably_prove_file_not_exact_at(
        output_fd,
        "commit.json",
        _canonical_bytes(commit_receipt),
        label="pinned artifact commit",
    ):
        raise DiagnosticPublicationStateAmbiguousError(
            "pinned artifact commit remained after final reconciliation"
        )
    remaining_public_content = _published_artifact_content_identity(
        parent_fd,
        output_name,
        run_manifest,
        records_byte_count=records_byte_count,
        records_sha256=records_sha256,
        commit_receipt=commit_receipt,
    )
    if remaining_public_content is not None:
        raise DiagnosticPublicationStateAmbiguousError(
            "an exact committed artifact remains public after INVALID"
        )
    _prove_attempt_terminal_authority(
        parent=parent,
        parent_fd=parent_fd,
        parent_stat=parent_stat,
        attempt=attempt,
        required_receipts={"invalid.json": invalid_receipt},
    )
    after_generation = _capture_terminal_collective_generation(
        parent=parent,
        parent_fd=parent_fd,
        parent_stat=parent_stat,
        attempt=attempt,
        attempt_filenames=attempt_filenames,
        output_name=output_name,
        output_filenames=artifact_filenames,
        output_fd=output_fd,
    )
    if after_generation != before_generation:
        raise DiagnosticPublicationStateAmbiguousError(
            "INVALID receipt and artifact absence changed during collective proof"
        )


def _retry_committed_artifact_durability(
    *,
    parent: Path,
    parent_fd: int,
    parent_stat: os.stat_result,
    attempt: _Attempt,
    success_receipts: Mapping[str, Mapping[str, Any]],
    output_name: str,
    staging_identity: tuple[int, int],
    run_manifest: Mapping[str, Any],
    records_byte_count: int,
    records_sha256: str,
    commit_receipt: Mapping[str, Any],
    retire_publication_lock: Callable[[], None] | None = None,
) -> bool:
    """Retry both directory barriers before accepting an exact commit."""

    output_fd = -1
    try:
        if not _prove_attempt_terminal_authority(
            parent=parent,
            parent_fd=parent_fd,
            parent_stat=parent_stat,
            attempt=attempt,
            success_receipts=success_receipts,
        ):
            return False
        try:
            flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            output_fd = os.open(output_name, flags, dir_fd=parent_fd)
            observed = os.fstat(output_fd)
            if (observed.st_dev, observed.st_ino) != staging_identity:
                return False
            os.fsync(output_fd)
            os.fsync(parent_fd)
        except BaseException:
            return False
        _assert_started_output_parent_identity(parent, parent_fd, parent_stat)
        commit_matches = _published_artifact_matches(
            parent_fd,
            output_name,
            staging_identity,
            run_manifest,
            records_byte_count=records_byte_count,
            records_sha256=records_sha256,
            commit_receipt=commit_receipt,
        )
        if not commit_matches:
            return False
        if not _prove_committed_terminal_collective(
            parent=parent,
            parent_fd=parent_fd,
            parent_stat=parent_stat,
            attempt=attempt,
            success_receipts=success_receipts,
            output_name=output_name,
            output_fd=output_fd,
            staging_identity=staging_identity,
            run_manifest=run_manifest,
            records_byte_count=records_byte_count,
            records_sha256=records_sha256,
            commit_receipt=commit_receipt,
        ):
            return False
        if retire_publication_lock is not None:
            retire_publication_lock()
            try:
                if not _prove_committed_terminal_collective(
                    parent=parent,
                    parent_fd=parent_fd,
                    parent_stat=parent_stat,
                    attempt=attempt,
                    success_receipts=success_receipts,
                    output_name=output_name,
                    output_fd=output_fd,
                    staging_identity=staging_identity,
                    run_manifest=run_manifest,
                    records_byte_count=records_byte_count,
                    records_sha256=records_sha256,
                    commit_receipt=commit_receipt,
                ):
                    raise DiagnosticPublicationStateAmbiguousError(
                        "committed artifact or attempt conflicted after recovery "
                        "lock retirement"
                    )
            except _PublicationLockRetirementAmbiguousError:
                raise
            except BaseException as terminal_error:
                raise _PublicationLockRetirementAmbiguousError(
                    "recovered COMMITTED authority is ambiguous after lock "
                    f"retirement: {terminal_error}"
                ) from terminal_error
            return True
        return _prove_committed_terminal_collective(
            parent=parent,
            parent_fd=parent_fd,
            parent_stat=parent_stat,
            attempt=attempt,
            success_receipts=success_receipts,
            output_name=output_name,
            output_fd=output_fd,
            staging_identity=staging_identity,
            run_manifest=run_manifest,
            records_byte_count=records_byte_count,
            records_sha256=records_sha256,
            commit_receipt=commit_receipt,
        )
    finally:
        if output_fd >= 0:
            _close_descriptor_best_effort(output_fd)


def _published_exact_artifact_commit_identity(
    parent_fd: int,
    output_name: str,
    staging_identity: tuple[int, int],
    commit_receipt: Mapping[str, Any],
) -> tuple[int, int] | None:
    """Observe exact commit authority independently of full artifact closure."""

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        output_fd = os.open(output_name, flags, dir_fd=parent_fd)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise DiagnosticPublicationStateAmbiguousError(
            "artifact commit parent observation failed"
        ) from error
    try:
        observed = os.fstat(output_fd)
        if (observed.st_dev, observed.st_ino) != staging_identity:
            return None
        return _exact_regular_file_identity_at(
            output_fd,
            "commit.json",
            _canonical_bytes(commit_receipt),
            label="artifact commit",
        )
    finally:
        _close_descriptor_best_effort(output_fd)


def _pinned_exact_artifact_commit_identity(
    output_fd: int,
    staging_identity: tuple[int, int],
    commit_receipt: Mapping[str, Any],
) -> tuple[int, int] | None:
    """Observe exact commit authority through the retained artifact descriptor."""

    try:
        observed = os.fstat(output_fd)
    except OSError as error:
        raise DiagnosticPublicationStateAmbiguousError(
            "pinned artifact observation failed"
        ) from error
    if (observed.st_dev, observed.st_ino) != staging_identity:
        return None
    return _exact_regular_file_identity_at(
        output_fd,
        "commit.json",
        _canonical_bytes(commit_receipt),
        label="pinned artifact commit",
    )


def _revoke_exact_artifact_commit_at(
    output_fd: int,
    staging_identity: tuple[int, int],
    commit_receipt: Mapping[str, Any],
) -> bool:
    """Tombstone exact commit authority through a pinned artifact descriptor."""

    commit_identity = _pinned_exact_artifact_commit_identity(
        output_fd,
        staging_identity,
        commit_receipt,
    )
    if commit_identity is None:
        return False
    _quarantine_exact_file_at(
        output_fd,
        "commit.json",
        _canonical_bytes(commit_receipt),
        expected_identity=commit_identity,
        label="artifact commit",
    )
    return True


def _revoke_exact_artifact_commit(
    parent_fd: int,
    output_name: str,
    staging_identity: tuple[int, int],
    commit_receipt: Mapping[str, Any],
) -> bool:
    """Durably tombstone commit.json inside the exact artifact inode."""

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        output_fd = os.open(output_name, flags, dir_fd=parent_fd)
    except FileNotFoundError:
        return False
    except OSError as error:
        raise DiagnosticPublicationStateAmbiguousError(
            "artifact commit rollback parent observation failed"
        ) from error
    try:
        return _revoke_exact_artifact_commit_at(
            output_fd,
            staging_identity,
            commit_receipt,
        )
    finally:
        _close_descriptor_best_effort(output_fd)


def _write_canonical_file_noreplace(
    destination: Path,
    payload: Mapping[str, Any],
) -> None:
    """Stage, fsync, and atomically publish one authority file.

    The destination parent must already exist as a stable non-symlink
    directory. This function never creates publication ancestors whose own
    directory entries would require separate durability barriers.

    Once a no-replace rename may have succeeded, success requires a durable
    parent-directory barrier plus the exact staged inode and bytes. A failed
    barrier is retried; persistent failure must durably revoke the candidate or
    report an explicitly ambiguous publication state.
    """

    parent = destination.parent
    parent_fd, parent_stat = _open_stable_directory(
        parent,
        "authorization parent",
    )
    if destination.name != Path(destination.name).name or not destination.name:
        _close_descriptor_best_effort(parent_fd)
        raise DiagnosticRunnerError("authorization filename is invalid")
    raw = _canonical_bytes(payload)
    try:
        _assert_directory_path_identity(
            parent,
            parent_fd,
            parent_stat,
            "authorization parent",
        )
        _assert_directory_path_identity(
            parent,
            parent_fd,
            parent_stat,
            "authorization parent",
        )
        try:
            staging_identity = _write_canonical_file_noreplace_at(
                parent_fd,
                destination.name,
                payload,
            )
        except _ExactPublicationRevokedError as error:
            raise DiagnosticNotRunError(
                "authorization candidate publication was durably revoked"
            ) from error
        except DiagnosticPublicationStateAmbiguousError as error:
            raise DiagnosticPublicationStateAmbiguousError(
                "authorization candidate durability and exact rollback are "
                "both unproven"
            ) from error
        try:
            _assert_directory_path_identity(
                parent,
                parent_fd,
                parent_stat,
                "authorization parent",
            )
        except BaseException as publication_error:
            if _revoke_published_file_at(
                parent_fd,
                destination.name,
                staging_identity,
                raw,
            ):
                raise DiagnosticNotRunError(
                    "authorization candidate publication was durably revoked "
                    "after parent identity drift"
                ) from publication_error
            raise DiagnosticPublicationStateAmbiguousError(
                "authorization candidate durability and exact rollback are "
                "both unproven"
            ) from publication_error
        if not _published_file_matches(
            parent_fd,
            destination.name,
            staging_identity,
            raw,
        ):
            if not _durably_prove_file_not_exact_at(
                parent_fd,
                destination.name,
                raw,
                expected_identity=staging_identity,
                label="authorization candidate",
            ):
                raise DiagnosticPublicationStateAmbiguousError(
                    "authorization candidate reappeared during final proof"
                )
            try:
                _assert_directory_path_identity(
                    parent,
                    parent_fd,
                    parent_stat,
                    "authorization parent",
                )
            except BaseException as error:
                raise DiagnosticPublicationStateAmbiguousError(
                    "authorization candidate final absence was proved only in "
                    "a displaced parent"
                ) from error
            raise DiagnosticNotRunError(
                "authorization candidate was durably absent or different at "
                "final publication proof"
            )
    finally:
        # Closing a pinned descriptor cannot revoke an exact candidate or
        # supersede the already selected typed publication outcome.
        _close_descriptor_best_effort(parent_fd)


def _git(repository_root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise DiagnosticRunnerError(f"git {' '.join(arguments)} failed: {message}")
    return result.stdout.strip()


def _git_bytes(repository_root: Path, *arguments: str) -> bytes:
    result = subprocess.run(
        ["git", *arguments],
        cwd=repository_root,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        if not message:
            message = result.stdout.decode("utf-8", errors="replace").strip()
        raise DiagnosticRunnerError(f"git {' '.join(arguments)} failed: {message}")
    return result.stdout


def _require_ancestor(repository_root: Path, ancestor: str, head: str) -> None:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, head],
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise DiagnosticRunnerError(
            f"required revision {ancestor} is not an ancestor of clean HEAD"
        )


def _require_commit_object(repository_root: Path, revision: str, label: str) -> None:
    if _git(repository_root, "cat-file", "-t", revision) != "commit":
        raise DiagnosticRunnerError(f"{label} must name an exact Git commit object")


def _require_regular_git_blob(
    repository_root: Path,
    revision: str,
    relative_path: str,
    *,
    label: str = "authorization",
) -> None:
    raw = _git_bytes(
        repository_root,
        "ls-tree",
        "-z",
        revision,
        "--",
        relative_path,
    )
    entries = raw.split(b"\0")
    if len(entries) != 2 or entries[1] != b"" or b"\t" not in entries[0]:
        raise DiagnosticRunnerError(f"{label} Git tree entry is not unique")
    metadata, observed_path = entries[0].split(b"\t", maxsplit=1)
    fields = metadata.split()
    if (
        observed_path != relative_path.encode("utf-8")
        or len(fields) != 3
        or fields[0] != b"100644"
        or fields[1] != b"blob"
    ):
        raise DiagnosticRunnerError(
            f"{label} Git tree entry must be one non-executable regular blob"
        )


def _regular_file_receipt(path: Path) -> dict[str, Any]:
    raw = _read_regular_file_nofollow(path, "attested source")
    return {"byte_count": len(raw), "sha256": _sha256_bytes(raw)}


def _host_build_receipt() -> dict[str, Any]:
    executable = Path(sys.executable).resolve()
    math_module = Path(getattr(math, "__file__", "")).resolve()
    return {
        "architecture": platform.machine(),
        "math_module": {
            "path_name": math_module.name,
            **_regular_file_receipt(math_module),
        },
        "operating_system": platform.platform(),
        "python_build": list(platform.python_build()),
        "python_cache_tag": sys.implementation.cache_tag,
        "python_executable": {
            "path_name": executable.name,
            **_regular_file_receipt(executable),
        },
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
    }


def _numeric_microfixture() -> dict[str, Any]:
    values = {
        "exp_neg_three_quarters": math.exp(-0.75).hex(),
        "fsum_cancellation": math.fsum((1e16, 1.0, -1e16)).hex(),
        "hypot_3_4": math.hypot(3.0, 4.0).hex(),
        "log1p_one_eighth": math.log1p(0.125).hex(),
        "sqrt_two": math.sqrt(2.0).hex(),
    }
    return {
        "fixture_id": "python-libm-float-hex/v1",
        "values": values,
        "deterministic_digest": sha256_json(values),
    }


def _micro_budget() -> TrackABudgetProfile:
    limits = {axis: 4096 for axis in TRACK_A_WORK_AXES}
    limits["verifier_calls"] = 2
    return TrackABudgetProfile(
        profile_id="track_a_runner_nondiagnostic_microfixture/v1",
        primary_axis="verifier_calls",
        budget=TrackAWorkBudget(**limits),
    )


def _search_microfixture() -> dict[str, Any]:
    proposal = TrackAProposalSpec("uniform/v1")
    method = TrackAMethodSpec.greedy()
    profile = _micro_budget()
    result = run_countdown_track_a_search(
        _MICRO_TASK,
        proposal=proposal,
        method=method,
        budget_profile=profile,
        exploration_seed=0,
    )
    replayed = replay_countdown_track_a_search_bytes(
        result.canonical_bytes,
        task=_MICRO_TASK,
        proposal=proposal,
        method=method,
        budget_profile=profile,
        exploration_seed=0,
        expected_run_identity_digest=result.run_identity_digest,
    )
    if replayed != result.canonical_bytes:
        raise DiagnosticRunnerError("non-diagnostic search microfixture replay drifted")
    core = {
        "fixture_id": "countdown-d6-uniform-greedy-replay/v1",
        "search_run_identity_digest": result.run_identity_digest,
        "task_fingerprint": _MICRO_TASK.task_fingerprint,
        "trace_byte_count": len(result.canonical_bytes),
        "trace_sha256": _sha256_bytes(result.canonical_bytes),
    }
    return {**core, "deterministic_digest": sha256_json(core)}


@dataclass(frozen=True)
class _BuildAttestation:
    payload: dict[str, Any]
    current_head: str


def _validate_protected_import_origins(root: Path) -> None:
    for module_name, relative in _PROTECTED_MODULE_PATHS.items():
        loaded = sys.modules.get(module_name)
        loaded_path = getattr(loaded, "__file__", None)
        if (
            type(loaded_path) is not str
            or Path(loaded_path).resolve() != (root / relative).resolve()
        ):
            raise DiagnosticRunnerError(
                f"imported protected module is outside attested source: {module_name}"
            )


def _protected_source_receipts(
    root: Path,
    head: str,
    *,
    authorized_runner_revision: str,
) -> dict[str, dict[str, Any]]:
    current = _require_git_oid(head, "git HEAD")
    approved = _require_git_oid(
        authorized_runner_revision,
        "authorized runner revision",
    )
    receipts: dict[str, dict[str, Any]] = {}
    for relative in (*_SEARCH_SOURCE_PATHS, *_RUNNER_SOURCE_PATHS):
        _require_regular_git_blob(
            root,
            current,
            relative,
            label="protected source at clean HEAD",
        )
        source = _read_regular_file_nofollow(
            root / relative,
            "attested protected source",
        )
        head_blob = _git_bytes(root, "show", f"{current}:{relative}")
        if source != head_blob:
            raise DiagnosticRunnerError(
                f"protected source does not exact-match clean HEAD blob: {relative}"
            )
        approved_blob = head_blob
        if approved != current:
            _require_regular_git_blob(
                root,
                approved,
                relative,
                label="protected source at authorized runner revision",
            )
            approved_blob = _git_bytes(root, "show", f"{approved}:{relative}")
        if source != approved_blob:
            raise DiagnosticRunnerError(
                "protected source does not exact-match authorized runner "
                f"revision blob: {relative}"
            )
        receipts[relative] = {
            "byte_count": len(source),
            "sha256": _sha256_bytes(source),
        }
    return receipts


def _validate_authorized_source_receipts(
    receipts: object,
    *,
    expected_paths: Sequence[str],
    label: str,
) -> dict[str, dict[str, Any]]:
    if type(receipts) is not dict or set(receipts) != set(expected_paths):
        raise DiagnosticRunnerError(f"authorized {label} protected path set drifted")
    for relative in expected_paths:
        receipt = receipts[relative]
        if (
            type(receipt) is not dict
            or set(receipt) != {"byte_count", "sha256"}
            or type(receipt["byte_count"]) is not int
            or receipt["byte_count"] < 0
        ):
            raise DiagnosticRunnerError(
                f"authorized {label} source receipt is invalid: {relative}"
            )
        _require_sha256(
            receipt["sha256"],
            f"authorized {label} source receipt digest",
        )
    return receipts


def _validate_authorized_build_attestation_structure(
    attestation: object,
) -> dict[str, Any]:
    """Reject a drifted authorization source closure before sealed preflight."""

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
        raise DiagnosticRunnerError(
            "authorized runner build attestation fields drifted"
        )
    if attestation["schema_version"] != BUILD_ATTESTATION_SCHEMA_VERSION:
        raise DiagnosticRunnerError(
            "authorized runner build attestation schema drifted"
        )
    _require_git_oid(
        attestation["authorized_runner_revision"],
        "authorized runner revision",
    )
    ancestry = attestation["required_ancestry"]
    if (
        type(ancestry) is not list
        or not ancestry
        or any(
            type(revision) is not str
            or len(revision) not in {40, 64}
            or any(character not in "0123456789abcdef" for character in revision)
            for revision in ancestry
        )
        or len(set(ancestry)) != len(ancestry)
    ):
        raise DiagnosticRunnerError("authorized runner required ancestry is invalid")
    search_receipts = _validate_authorized_source_receipts(
        attestation["search_source_files"],
        expected_paths=_SEARCH_SOURCE_PATHS,
        label="search",
    )
    runner_receipts = _validate_authorized_source_receipts(
        attestation["runner_source_files"],
        expected_paths=_RUNNER_SOURCE_PATHS,
        label="runner",
    )
    search_build_digest = _require_sha256(
        attestation["search_build_digest"],
        "authorized search build digest",
    )
    runner_build_digest = _require_sha256(
        attestation["runner_build_digest"],
        "authorized runner build digest",
    )
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
    if (
        sha256_json(search_core) != search_build_digest
        or sha256_json(runner_core) != runner_build_digest
    ):
        raise DiagnosticRunnerError("authorized runner/search build digest mismatch")
    return attestation


def _recheck_source_closure(
    repository_root: Path,
    build: _BuildAttestation,
) -> None:
    """Recheck HEAD, cleanliness, import origins, and every protected blob."""

    root = Path(repository_root).resolve()
    head = _require_git_oid(_git(root, "rev-parse", "HEAD"), "git HEAD")
    if head != build.current_head:
        raise DiagnosticRunnerError("source HEAD changed after build attestation")
    if _git(root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise DiagnosticRunnerError("source checkout changed after build attestation")
    _validate_protected_import_origins(root)
    approved = _require_git_oid(
        build.payload["authorized_runner_revision"],
        "authorized runner revision",
    )
    observed = _protected_source_receipts(
        root,
        head,
        authorized_runner_revision=approved,
    )
    expected = {
        **build.payload["search_source_files"],
        **build.payload["runner_source_files"],
    }
    if observed != expected:
        raise DiagnosticRunnerError(
            "protected source receipts changed after attestation"
        )


def _attest_clean_source_build(
    repository_root: Path,
    *,
    authorized_runner_revision: str | None,
) -> _BuildAttestation:
    root = Path(repository_root).resolve()
    observed_root = Path(_git(root, "rev-parse", "--show-toplevel")).resolve()
    if observed_root != root:
        raise DiagnosticRunnerError("repository root does not match git top level")
    if _git(root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise DiagnosticRunnerError("source checkout is not clean")
    head = _require_git_oid(_git(root, "rev-parse", "HEAD"), "git HEAD")
    approved = (
        head
        if authorized_runner_revision is None
        else _require_git_oid(
            authorized_runner_revision,
            "authorized runner revision",
        )
    )
    _require_commit_object(root, head, "git HEAD")
    _require_commit_object(root, approved, "authorized runner revision")
    for revision in (*REQUIRED_ANCESTRY, approved):
        _require_ancestor(root, revision, head)

    relative_paths = (*_SEARCH_SOURCE_PATHS, *_RUNNER_SOURCE_PATHS)
    tracked = set(_git(root, "ls-files", "--", *relative_paths).splitlines())
    if tracked != set(relative_paths):
        raise DiagnosticRunnerError(
            "protected runner/search source surface is untracked"
        )
    _validate_protected_import_origins(root)
    receipts = _protected_source_receipts(
        root,
        head,
        authorized_runner_revision=approved,
    )
    host = _host_build_receipt()
    numeric = _numeric_microfixture()
    search_micro = _search_microfixture()
    search_core = {
        "host_build": host,
        "numeric_microfixture": numeric,
        "search_microfixture": search_micro,
        "source_files": {path: receipts[path] for path in _SEARCH_SOURCE_PATHS},
    }
    search_build_digest = sha256_json(search_core)
    runner_core = {
        "runner_source_files": {path: receipts[path] for path in _RUNNER_SOURCE_PATHS},
        "search_build_digest": search_build_digest,
    }
    runner_build_digest = sha256_json(runner_core)
    payload = {
        "authorized_runner_revision": approved,
        "host_build": host,
        "numeric_microfixture": numeric,
        "required_ancestry": list(REQUIRED_ANCESTRY),
        "runner_build_digest": runner_build_digest,
        "runner_source_files": runner_core["runner_source_files"],
        "schema_version": BUILD_ATTESTATION_SCHEMA_VERSION,
        "search_build_digest": search_build_digest,
        "search_microfixture": search_micro,
        "search_source_files": search_core["source_files"],
    }
    return _BuildAttestation(payload=payload, current_head=head)


def _validate_schedule(bundle: object) -> tuple[DiagnosticCell, ...]:
    cells = bundle.cells  # type: ignore[attr-defined]
    if len(cells) != EXPECTED_CELL_COUNT:
        raise DiagnosticRunnerError("verified schedule cell count drifted")
    ids = [cell.cell_id for cell in cells]
    if len(set(ids)) != EXPECTED_CELL_COUNT:
        raise DiagnosticRunnerError("verified schedule has duplicate cell IDs")
    payloads = bundle.payloads  # type: ignore[attr-defined]
    matrix = payloads["preregistration.json"]["execution_matrix"]
    if matrix["cell_count"] != EXPECTED_CELL_COUNT or matrix[
        "schedule_digest"
    ] != sha256_json([cell.to_dict() for cell in cells]):
        raise DiagnosticRunnerError("verified schedule coverage digest drifted")
    if {cell.budget_profile_id for cell in cells} != {"score256"}:
        raise DiagnosticRunnerError("verified schedule is not score256-only")
    if len({cell.task_fingerprint for cell in cells}) != 12:
        raise DiagnosticRunnerError("verified schedule task coverage drifted")
    heuristic = [cell for cell in cells if cell.proposal_label == "heuristic"]
    oracle = [
        cell for cell in cells if cell.proposal_label == "oracle_positive_control"
    ]
    if len(heuristic) != 228 or len(oracle) != 12:
        raise DiagnosticRunnerError("verified proposal schedule coverage drifted")
    if any(
        cell.method_label != "greedy" or cell.exploration_seed != 0 for cell in oracle
    ):
        raise DiagnosticRunnerError("oracle schedule must be deterministic greedy")
    for label in _DETERMINISTIC_METHOD_LABELS:
        matching = [cell for cell in heuristic if cell.method_label == label]
        if len(matching) != 12 or {cell.exploration_seed for cell in matching} != {0}:
            raise DiagnosticRunnerError(
                f"deterministic diagnostic schedule drifted: {label}"
            )
    for label in _STOCHASTIC_METHOD_LABELS:
        matching = [cell for cell in heuristic if cell.method_label == label]
        if len(matching) != 48 or {cell.exploration_seed for cell in matching} != set(
            _DIAGNOSTIC_EXPLORATION_SEEDS
        ):
            raise DiagnosticRunnerError(
                f"stochastic diagnostic schedule drifted: {label}"
            )
    expected_methods = set((*_DETERMINISTIC_METHOD_LABELS, *_STOCHASTIC_METHOD_LABELS))
    if {cell.method_label for cell in heuristic} != expected_methods:
        raise DiagnosticRunnerError("verified method schedule coverage drifted")
    return cells


def _frozen_diagnostic_runtime_bindings() -> dict[str, dict[str, Any]]:
    """Return exactly the IID and search bindings frozen in this diagnostic."""

    canary_bindings = canary_manifest.frozen_track_a_canary_runtime_bindings()
    return {label: deepcopy(canary_bindings[label]) for label in ("iid", "search")}


def _qualify_diagnostic_runtime() -> dict[str, Any]:
    """Fail closed unless live IID/search behavior matches the sealed runtime."""

    expected = _frozen_diagnostic_runtime_bindings()
    observed = {
        "iid": perturbation_runtime_metadata("iid", refresh_conformance=True),
        "search": search_runtime_metadata(),
    }
    for label, metadata in observed.items():
        try:
            observed_bytes = _canonical_bytes(metadata)
            expected_bytes = _canonical_bytes(expected[label]["metadata"])
        except (TraceValidationError, TypeError, ValueError) as error:
            raise DiagnosticRunnerError(
                f"live {label} runtime metadata is invalid"
            ) from error
        if observed_bytes != expected_bytes:
            raise DiagnosticRunnerError(
                f"live {label} runtime does not match the frozen diagnostic runtime"
            )
    return {
        "bundle_id": BUNDLE_ID,
        "execution_authorized": False,
        "runtime_bindings_digest": sha256_json(expected),
        "status": "RUNTIME_QUALIFIED",
    }


def _validate_outcome_blind_budget_guards(payloads: Mapping[str, Any]) -> None:
    """Reject any schedule or guard that is not the sole score256 profile."""

    budget_payload = payloads["budgets.json"]
    profiles = budget_payload["profiles"]
    if (
        budget_payload.get("profile_order") != ["score256"]
        or type(profiles) is not list
        or len(profiles) != 1
        or type(profiles[0]) is not dict
    ):
        raise DiagnosticRunnerError("diagnostic must contain only score256")
    score = profiles[0].get("spec")
    if type(score) is not dict or score.get("profile_id") != "score256":
        raise DiagnosticRunnerError("score256 budget profile is missing")
    if score.get("primary_axis") != "legal_action_scores":
        raise DiagnosticRunnerError("score256 primary axis drifted")

    score_limits = score.get("budget")
    if type(score_limits) is not dict:
        raise DiagnosticRunnerError("score256 budget limits are invalid")
    legal_limit = score_limits.get("legal_action_scores")
    if type(legal_limit) is not int or legal_limit != 256:
        raise DiagnosticRunnerError("score256 legal-action limit drifted")
    max_actions = 60
    min_actions = 3
    edges_per_trajectory = 5
    max_accepted_selections = (legal_limit - 1) // min_actions
    score_minima = {
        "generated_perturbation_coordinates": legal_limit + max_actions,
        "proposal_action_scores": legal_limit + max_actions + 1,
        "proposal_state_evaluations": max_accepted_selections + 2,
        "edge_selections": max_accepted_selections + 1,
        "transitions": max_accepted_selections + 1,
        "verifier_calls": max_accepted_selections // edges_per_trajectory + 1,
    }
    for axis, minimum in score_minima.items():
        if type(score_limits.get(axis)) is not int or score_limits[axis] < minimum:
            raise DiagnosticRunnerError(
                f"score256 {axis} guard is below outcome-blind minimum {minimum}"
            )


@dataclass(frozen=True)
class _Preflight:
    bundle: object
    cells: tuple[DiagnosticCell, ...]
    qualification: dict[str, Any]
    runtime_qualification_digest: str
    build: _BuildAttestation
    output_path: Path
    publication_backend: str
    synthetic_fixture_digest: str | None
    artifact_layout: str | None = None
    output_path_digest: str | None = None
    output_parent_binding: dict[str, Any] | None = None
    publication_environment_requirements: dict[str, Any] | None = None
    synthetic_components: _ResolvedComponents | None = None
    synthetic_method_manifest_digest: str | None = None
    synthetic_expected_cell_count: int | None = None


@dataclass(frozen=True)
class _SyntheticFixtureBundleSnapshot:
    """An immutable-byte snapshot of one positively identified test fixture."""

    _payload_bytes: bytes
    cells: tuple[DiagnosticCell, ...]
    seal_digest: str

    @property
    def payloads(self) -> dict[str, Any]:
        parsed = strict_json_loads(self._payload_bytes.decode("utf-8"))
        if type(parsed) is not dict:
            raise DiagnosticRunnerError("synthetic payload snapshot is not an object")
        return parsed


def _snapshot_json_object(value: object, label: str) -> tuple[dict[str, Any], bytes]:
    if type(value) is not dict:
        raise DiagnosticRunnerError(f"{label} is not an exact JSON object")
    raw = _canonical_bytes(value)
    parsed = strict_json_loads(raw.decode("utf-8"))
    if type(parsed) is not dict or _canonical_bytes(parsed) != raw:
        raise DiagnosticRunnerError(f"{label} did not survive canonical snapshotting")
    return parsed, raw


def _snapshot_diagnostic_cell(cell: object) -> DiagnosticCell:
    if type(cell) is not DiagnosticCell:
        raise DiagnosticRunnerError("synthetic schedule contains a non-exact cell")
    observed = cell.to_dict()
    snapshot = DiagnosticCell(
        task_fingerprint=cell.task_fingerprint,
        task_manifest_digest=cell.task_manifest_digest,
        proposal_label=cell.proposal_label,
        proposal_spec_digest=cell.proposal_spec_digest,
        method_label=cell.method_label,
        method_spec_digest=cell.method_spec_digest,
        method_manifest_digest=cell.method_manifest_digest,
        budget_profile_id=cell.budget_profile_id,
        budget_profile_spec_digest=cell.budget_profile_spec_digest,
        exploration_seed=cell.exploration_seed,
    )
    if type(observed) is not dict or snapshot.to_dict() != observed:
        raise DiagnosticRunnerError("synthetic schedule cell snapshot drifted")
    return snapshot


def _snapshot_exact_absolute_path(
    value: object,
    label: str,
    *,
    require_leaf: bool,
) -> Path:
    path_type = type(Path())
    if (
        type(value) is not path_type
        or not value.is_absolute()
        or ".." in value.parts
        or (require_leaf and not value.name)
    ):
        raise DiagnosticRunnerError(f"{label} is not an exact absolute path")
    snapshot = Path(value)
    if type(snapshot) is not path_type or str(snapshot) != str(value):
        raise DiagnosticRunnerError(f"{label} path snapshot drifted")
    return snapshot


def _snapshot_exact_synthetic_preflight(preflight: _Preflight) -> _Preflight:
    """Bind the private publisher to fixed nondiagnostic bytes before I/O."""

    try:
        if (
            type(preflight) is not _Preflight
            or type(preflight.publication_backend) is not str
            or preflight.publication_backend != _SYNTHETIC_PUBLICATION_BACKEND
        ):
            raise DiagnosticNotRunError(_PUBLICATION_BACKEND_REFUSAL)
        output_path = _snapshot_exact_absolute_path(
            preflight.output_path,
            "synthetic output path",
            require_leaf=True,
        )
        cells_value = preflight.cells
        bundle_cells_value = getattr(preflight.bundle, "cells", None)
        if type(cells_value) is not tuple or type(bundle_cells_value) is not tuple:
            raise DiagnosticRunnerError(
                "synthetic schedule must be an exact materialized tuple"
            )
        cells = tuple(_snapshot_diagnostic_cell(cell) for cell in cells_value)
        bundle_cells = tuple(
            _snapshot_diagnostic_cell(cell) for cell in bundle_cells_value
        )
        if len(cells) != _SYNTHETIC_EXPECTED_CELL_COUNT or [
            cell.to_dict() for cell in cells
        ] != [cell.to_dict() for cell in bundle_cells]:
            raise DiagnosticRunnerError(
                "synthetic preflight and bundle schedules do not exact-match"
            )
        payloads, payload_bytes = _snapshot_json_object(
            getattr(preflight.bundle, "payloads", None),
            "synthetic fixture payloads",
        )
        seal_digest = _require_sha256(
            getattr(preflight.bundle, "seal_digest", None),
            "synthetic fixture seal digest",
        )
        qualification, _ = _snapshot_json_object(
            preflight.qualification,
            "synthetic runtime qualification",
        )
        runtime_qualification_digest = _require_sha256(
            preflight.runtime_qualification_digest,
            "synthetic runtime qualification digest",
        )
        fixture_digest = sha256_json(
            {
                "cells": [cell.to_dict() for cell in cells],
                "payloads": payloads,
                "qualification": qualification,
                "runtime_qualification_digest": runtime_qualification_digest,
                "seal_digest": seal_digest,
            }
        )
        if (
            type(preflight.synthetic_fixture_digest) is not str
            or preflight.synthetic_fixture_digest != fixture_digest
            or fixture_digest not in _SYNTHETIC_FIXTURE_CONTENT_DIGESTS
        ):
            raise DiagnosticRunnerError(
                "preflight is not a positively identified synthetic fixture"
            )
        if (
            set(payloads)
            != {
                "budgets.json",
                "diagnostic_tasks.json",
                "methods.json",
                "preregistration.json",
                "proposals.json",
            }
            or set(qualification)
            != {
                "bundle_id",
                "execution_authorized",
                "runtime_bindings_digest",
                "status",
            }
            or qualification["bundle_id"] != BUNDLE_ID
            or qualification["execution_authorized"] is not False
            or qualification["status"] != "RUNTIME_QUALIFIED"
            or sha256_json(qualification) != runtime_qualification_digest
            or qualification["runtime_bindings_digest"]
            != sha256_json(payloads["methods.json"]["runtime_bindings"])
        ):
            raise DiagnosticRunnerError(
                "synthetic fixture runtime qualification drifted"
            )
        components = _resolve_components(payloads)
        method_manifest_digest = _require_sha256(
            payloads["methods.json"]["deterministic_digest"],
            "synthetic method manifest digest",
        )
        for cell in cells:
            _validate_cell_component_bindings(
                cell,
                task=components.tasks[cell.task_fingerprint],
                proposal=components.proposals[cell.proposal_label],
                method=components.methods[cell.method_label],
                budget_profile=components.budgets[cell.budget_profile_id],
                method_manifest_digest=method_manifest_digest,
            )
        if type(preflight.build) is not _BuildAttestation:
            raise DiagnosticRunnerError("synthetic build attestation type drifted")
        build_payload, _ = _snapshot_json_object(
            preflight.build.payload,
            "synthetic build attestation",
        )
        build = _BuildAttestation(
            payload=build_payload,
            current_head=_require_git_oid(
                preflight.build.current_head,
                "synthetic build HEAD",
            ),
        )
        return _Preflight(
            bundle=_SyntheticFixtureBundleSnapshot(
                _payload_bytes=payload_bytes,
                cells=cells,
                seal_digest=seal_digest,
            ),
            cells=cells,
            qualification=qualification,
            runtime_qualification_digest=runtime_qualification_digest,
            build=build,
            output_path=output_path,
            publication_backend=_SYNTHETIC_PUBLICATION_BACKEND,
            synthetic_fixture_digest=fixture_digest,
            synthetic_components=components,
            synthetic_method_manifest_digest=method_manifest_digest,
            synthetic_expected_cell_count=_SYNTHETIC_EXPECTED_CELL_COUNT,
        )
    except DiagnosticNotRunError:
        raise
    except BaseException as error:
        raise DiagnosticNotRunError(_PUBLICATION_BACKEND_REFUSAL) from error


def _regular_file_layout(
    output_path: Path | str,
) -> regular_file_publication.RegularFileLayoutV2:
    try:
        return regular_file_publication.RegularFileLayoutV2.from_output_path(
            output_path
        )
    except regular_file_publication.RegularFilePublicationV2NotRunError as error:
        raise DiagnosticRunnerError(str(error)) from error


def _freeze_reviewed_parent_binding(
    output_path: Path | str,
    expected_parent_binding: object,
) -> dict[str, Any]:
    try:
        return regular_file_publication.freeze_reviewed_parent_binding_v2(
            output_path,
            expected_parent_binding,
        )
    except regular_file_publication.RegularFilePublicationV2NotRunError as error:
        raise DiagnosticRunnerError(str(error)) from error


def _preflight_reviewed_parent_binding(
    output_path: Path | str,
    expected_parent_binding: object,
) -> dict[str, Any]:
    try:
        return regular_file_publication.preflight_reviewed_parent_binding_v2(
            output_path,
            expected_parent_binding,
        )
    except regular_file_publication.RegularFilePublicationV2AmbiguousError as error:
        raise DiagnosticPublicationStateAmbiguousError(str(error)) from error
    except regular_file_publication.RegularFilePublicationV2NotRunError as error:
        raise DiagnosticNotRunError(str(error)) from error


def _capture_planning_parent_binding(
    output_path: Path | str,
) -> dict[str, Any]:
    try:
        return regular_file_publication.build_synthetic_parent_binding_v2(
            output_path
        )
    except regular_file_publication.RegularFilePublicationV2AmbiguousError as error:
        raise DiagnosticPublicationStateAmbiguousError(str(error)) from error
    except regular_file_publication.RegularFilePublicationV2NotRunError as error:
        raise DiagnosticRunnerError(str(error)) from error


def _publication_environment_requirements(
    output_parent_binding: Mapping[str, Any],
) -> dict[str, Any]:
    """Freeze the mechanics that separate review must qualify for this binding."""

    return _with_digest(
        {
            "artifact_layout": _REGULAR_FILE_ARTIFACT_LAYOUT,
            "binding_scope": regular_file_publication.PARENT_BINDING_SCOPE,
            "claim_boundary": (
                "review must qualify these mechanics on the bound local host and "
                "filesystem identity epoch; no NFS, SMB, FUSE, reboot, cross-host, "
                "mount-namespace, device-inode ABA, or malicious-kernel guarantee"
            ),
            "output_parent_binding_digest": output_parent_binding[
                "deterministic_digest"
            ],
            "publication_backend": _REGULAR_FILE_PUBLICATION_BACKEND,
            "required_mechanics": [
                "absolute_normalized_ascii_commit_path/v1",
                "componentwise_o_nofollow_parent_identity/v1",
                "descriptor_relative_o_creat_o_excl_regular_files/v1",
                "regular_file_and_directory_fsync/v1",
                "stable_st_dev_st_ino_within_identity_epoch/v1",
            ],
            "schema_version": (
                PUBLICATION_ENVIRONMENT_REQUIREMENTS_SCHEMA_VERSION
            ),
        }
    )


def _fresh_preflight(
    bundle_path: Path,
    output_path: Path | str,
    repository_root: Path,
    *,
    authorized_runner_revision: str | None,
    expected_output_parent_binding: object | None = None,
) -> _Preflight:
    layout = _regular_file_layout(output_path)
    output = layout.output_path
    lexical_repository = Path(os.path.abspath(os.fspath(repository_root)))
    repository = Path(repository_root).resolve()
    if (
        output == lexical_repository
        or output.is_relative_to(lexical_repository)
        or output == repository
        or output.is_relative_to(repository)
    ):
        raise DiagnosticRunnerError("run output must lie outside the source repository")
    if authorized_runner_revision is None:
        if expected_output_parent_binding is not None:
            raise DiagnosticRunnerError(
                "planning must capture rather than accept a parent binding"
            )
        parent_binding = _capture_planning_parent_binding(output)
    else:
        if expected_output_parent_binding is None:
            raise DiagnosticRunnerError(
                "reviewed authorization must supply its exact parent binding"
            )
        parent_binding = _freeze_reviewed_parent_binding(
            output,
            expected_output_parent_binding,
        )
    parent_binding = _preflight_reviewed_parent_binding(output, parent_binding)
    qualification = _qualify_diagnostic_runtime()
    if set(qualification) != {
        "bundle_id",
        "execution_authorized",
        "runtime_bindings_digest",
        "status",
    }:
        raise DiagnosticRunnerError("fresh runtime qualification fields drifted")
    frozen_runtime_digest = sha256_json(_frozen_diagnostic_runtime_bindings())
    if (
        qualification["bundle_id"] != BUNDLE_ID
        or qualification["status"] != "RUNTIME_QUALIFIED"
        or qualification["execution_authorized"] is not False
        or qualification["runtime_bindings_digest"] != frozen_runtime_digest
    ):
        raise DiagnosticRunnerError("fresh runtime qualification does not match bundle")
    build = _attest_clean_source_build(
        repository,
        authorized_runner_revision=authorized_runner_revision,
    )
    verified = verify_countdown_thompson_diagnostic_bundle(
        Path(bundle_path),
        repository_root=repository,
    )
    if verified.seal_digest != EXPECTED_SEAL_DIGEST:
        raise DiagnosticRunnerError("diagnostic bundle seal digest drifted")
    cells = _validate_schedule(verified)
    payloads = verified.payloads
    _validate_outcome_blind_budget_guards(payloads)
    expected_runtime_digest = sha256_json(payloads["methods.json"]["runtime_bindings"])
    if qualification["runtime_bindings_digest"] != expected_runtime_digest:
        raise DiagnosticRunnerError("fresh runtime qualification does not match bundle")
    task_ids = {
        row["task_fingerprint"] for row in payloads["diagnostic_tasks.json"]["tasks"]
    }
    if _MICRO_TASK.task_fingerprint in task_ids:
        raise DiagnosticRunnerError(
            "numeric/search microfixture overlaps diagnostic cohort"
        )
    # The attestation ran its numeric/search microfixtures before bundle
    # verification.  Close the race by checking the same HEAD, clean worktree,
    # import origins, descriptor-read bytes, and HEAD blobs again afterwards.
    _recheck_source_closure(repository, build)
    # Close parent and namespace drift around all source and sealed-bundle reads.
    parent_binding = _preflight_reviewed_parent_binding(output, parent_binding)
    return _Preflight(
        bundle=verified,
        cells=cells,
        qualification=qualification,
        runtime_qualification_digest=sha256_json(qualification),
        build=build,
        output_path=output,
        publication_backend=_REGULAR_FILE_PUBLICATION_BACKEND,
        synthetic_fixture_digest=None,
        artifact_layout=_REGULAR_FILE_ARTIFACT_LAYOUT,
        output_path_digest=layout.output_path_digest,
        output_parent_binding=parent_binding,
        publication_environment_requirements=(
            _publication_environment_requirements(parent_binding)
        ),
    )


def _authorization_payload_from_preflight(
    preflight: _Preflight,
    *,
    synthetic_fixture: bool,
) -> dict[str, Any]:
    payloads = preflight.bundle.payloads  # type: ignore[attr-defined]
    regular_file_authorization = (
        not synthetic_fixture
        and preflight.publication_backend == _REGULAR_FILE_PUBLICATION_BACKEND
    )
    if (
        not synthetic_fixture
        and not regular_file_authorization
        and preflight.publication_backend != _PUBLICATION_BACKEND_UNAVAILABLE
    ):
        raise DiagnosticRunnerError("production publication backend is unsupported")
    core = {
        "artifact_id": preflight.output_path.name,
        "authorization_scope": (
            _SYNTHETIC_AUTHORIZATION_SCOPE
            if synthetic_fixture
            else "one_exact_complete_240_cell_diagnostic_run"
        ),
        "bundle_id": BUNDLE_ID,
        "diagnostic_seal_digest": preflight.bundle.seal_digest,  # type: ignore[attr-defined]
        "cell_count": len(preflight.cells)
        if synthetic_fixture
        else EXPECTED_CELL_COUNT,
        "claim_boundary": (
            _SYNTHETIC_AUTHORIZATION_CLAIM_BOUNDARY
            if synthetic_fixture
            else (
                "execution authority only; this engineering diagnostic grants no "
                "method-superiority or locked-128 execution authority"
            )
        ),
        "method_manifest_digest": payloads["methods.json"]["deterministic_digest"],
        "output_path": str(preflight.output_path),
        "requires_explicit_digest_confirmation": True,
        "runner_build_attestation": preflight.build.payload,
        "runtime_qualification": preflight.qualification,
        "runtime_qualification_digest": preflight.runtime_qualification_digest,
        "schedule_digest": payloads["preregistration.json"]["execution_matrix"][
            "schedule_digest"
        ],
        "schema_version": (
            _SYNTHETIC_AUTHORIZATION_SCHEMA_VERSION
            if synthetic_fixture
            else (
                AUTHORIZATION_SCHEMA_VERSION
                if regular_file_authorization
                else _LEGACY_AUTHORIZATION_SCHEMA_VERSION
            )
        ),
    }
    if synthetic_fixture:
        core["synthetic_fixture_digest"] = preflight.synthetic_fixture_digest
    elif regular_file_authorization:
        layout = _regular_file_layout(preflight.output_path)
        if (
            preflight.artifact_layout != _REGULAR_FILE_ARTIFACT_LAYOUT
            or preflight.output_path_digest != layout.output_path_digest
            or preflight.output_parent_binding is None
            or preflight.publication_environment_requirements is None
        ):
            raise DiagnosticRunnerError(
                "regular-file authorization preflight is incomplete"
            )
        parent_binding = _freeze_reviewed_parent_binding(
            preflight.output_path,
            preflight.output_parent_binding,
        )
        if _canonical_bytes(parent_binding) != _canonical_bytes(
            preflight.output_parent_binding
        ):
            raise DiagnosticRunnerError(
                "regular-file parent binding is not exact canonical material"
            )
        requirements = _publication_environment_requirements(parent_binding)
        if _canonical_bytes(requirements) != _canonical_bytes(
            preflight.publication_environment_requirements
        ):
            raise DiagnosticRunnerError(
                "publication environment requirements drifted"
            )
        core.update(
            {
                "artifact_layout": _REGULAR_FILE_ARTIFACT_LAYOUT,
                "output_parent_binding": parent_binding,
                "output_parent_binding_digest": parent_binding[
                    "deterministic_digest"
                ],
                "output_path_digest": layout.output_path_digest,
                "publication_backend": _REGULAR_FILE_PUBLICATION_BACKEND,
                "publication_environment_requirements": requirements,
            }
        )
    return _with_digest(core)


def _authorization_payload(preflight: _Preflight) -> dict[str, Any]:
    synthetic_fixture = preflight.publication_backend == _SYNTHETIC_PUBLICATION_BACKEND
    if synthetic_fixture:
        preflight = _snapshot_exact_synthetic_preflight(preflight)
    return _authorization_payload_from_preflight(
        preflight,
        synthetic_fixture=synthetic_fixture,
    )


def _snapshot_exact_synthetic_authorization(
    preflight: _Preflight,
    authorization: object,
) -> dict[str, Any]:
    """Detach and exact-match synthetic authority before output access."""

    try:
        observed, _ = _snapshot_json_object(
            authorization,
            "synthetic execution authorization",
        )
        expected = _authorization_payload_from_preflight(
            preflight,
            synthetic_fixture=True,
        )
        if observed != expected:
            raise DiagnosticRunnerError(
                "synthetic authorization does not exact-match frozen preflight"
            )
        return observed
    except DiagnosticNotRunError:
        raise
    except BaseException as error:
        raise DiagnosticNotRunError(_PUBLICATION_BACKEND_REFUSAL) from error


def _authorization_repository_location(
    authorization_path: Path,
    repository_root: Path,
) -> tuple[Path, str]:
    root = Path(repository_root).resolve()
    candidate = Path(authorization_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    if candidate.is_symlink():
        raise DiagnosticRunnerError("authorization path must not traverse symlinks")
    resolved = candidate.resolve()
    if resolved == root or not resolved.is_relative_to(root):
        raise DiagnosticRunnerError(
            "authorization must be a repository-relative regular file"
        )
    relative = resolved.relative_to(root).as_posix()
    if relative == "." or ".." in Path(relative).parts:
        raise DiagnosticRunnerError("authorization repository path is invalid")
    return resolved, relative


def _validate_reviewed_authorization_blob(
    *,
    repository_root: Path,
    authorization_path: Path,
    authorization_raw: bytes,
    authorized_runner_revision: str,
    reviewed_authorization_revision: str,
) -> str:
    """Bind external review authority to one tracked, unchanged Git blob."""

    root = Path(repository_root).resolve()
    resolved, relative = _authorization_repository_location(
        authorization_path,
        root,
    )
    if resolved != Path(authorization_path).resolve():
        raise DiagnosticRunnerError("authorization path resolution drifted")
    tracked = _git(root, "ls-files", "--error-unmatch", "--", relative)
    if tracked.splitlines() != [relative]:
        raise DiagnosticRunnerError("authorization is not one exact tracked file")
    head = _require_git_oid(_git(root, "rev-parse", "HEAD"), "git HEAD")
    reviewed = _require_git_oid(
        reviewed_authorization_revision,
        "reviewed authorization revision",
    )
    approved = _require_git_oid(
        authorized_runner_revision,
        "authorized runner revision",
    )
    if reviewed == approved:
        raise DiagnosticRunnerError(
            "reviewed authorization revision must strictly descend from "
            "authorized runner revision"
        )
    for revision, label in (
        (approved, "authorized runner revision"),
        (reviewed, "reviewed authorization revision"),
        (head, "execution HEAD"),
    ):
        _require_commit_object(root, revision, label)
    _require_ancestor(root, approved, reviewed)
    _require_ancestor(root, reviewed, head)
    _require_regular_git_blob(root, reviewed, relative)
    _require_regular_git_blob(root, head, relative)
    head_blob = _git_bytes(root, "show", f"{head}:{relative}")
    reviewed_blob = _git_bytes(root, "show", f"{reviewed}:{relative}")
    if head_blob != authorization_raw or reviewed_blob != authorization_raw:
        raise DiagnosticRunnerError(
            "authorization bytes do not exact-match reviewed revision and HEAD blob"
        )
    return reviewed


def write_countdown_thompson_diagnostic_execution_plan(
    bundle_path: Path,
    output_path: Path | str,
    authorization_path: Path,
    *,
    repository_root: Path,
) -> dict[str, Any]:
    """Write an exclusive pre-outcome authorization candidate."""

    output = _regular_file_layout(output_path).output_path
    raw_authorization = Path(authorization_path)
    if raw_authorization == output or raw_authorization.is_relative_to(output):
        raise DiagnosticRunnerError("authorization file must lie outside output")
    repository = Path(repository_root).resolve()
    authorization, _ = _authorization_repository_location(
        raw_authorization,
        repository,
    )
    if authorization == output or authorization.is_relative_to(output):
        raise DiagnosticRunnerError("authorization file must lie outside output")
    if authorization.exists() or authorization.is_symlink():
        raise FileExistsError(f"authorization destination exists: {authorization}")
    preflight = _fresh_preflight(
        Path(bundle_path),
        output,
        repository,
        authorized_runner_revision=None,
    )
    payload = _authorization_payload(preflight)
    _write_canonical_file_noreplace(authorization, payload)
    return {
        "artifact_id": payload["artifact_id"],
        "authorization_digest": payload["deterministic_digest"],
        "authorization_path": str(authorization),
        "cell_count": EXPECTED_CELL_COUNT,
        "claim_boundary": "planning only; no diagnostic outcome was opened",
        "nondiagnostic_fixture_trace_byte_count": preflight.build.payload[
            "search_microfixture"
        ]["trace_byte_count"],
        "naive_240_trace_bytes_proxy": (
            preflight.build.payload["search_microfixture"]["trace_byte_count"]
            * EXPECTED_CELL_COUNT
        ),
        "status": "PREOUTCOME_AUTHORIZATION_CANDIDATE_WRITTEN",
    }


def _reviewed_authorization_parent_binding(
    authorization: Mapping[str, Any],
    output_path: Path | str,
) -> dict[str, Any]:
    """Freeze v2 publication fields before reviewed output access."""

    layout = _regular_file_layout(output_path)
    if (
        type(authorization.get("artifact_id")) is not str
        or authorization.get("artifact_id") != layout.output_path.name
        or type(authorization.get("output_path")) is not str
        or authorization.get("output_path") != os.fspath(layout.output_path)
        or authorization.get("artifact_layout") != _REGULAR_FILE_ARTIFACT_LAYOUT
        or authorization.get("publication_backend")
        != _REGULAR_FILE_PUBLICATION_BACKEND
    ):
        raise DiagnosticRunnerError(
            "authorization publication identity does not match requested output"
        )
    output_path_digest = _require_sha256(
        authorization.get("output_path_digest"),
        "authorization output path digest",
    )
    if output_path_digest != layout.output_path_digest:
        raise DiagnosticRunnerError(
            "authorization output path digest does not exact-match"
        )
    parent_binding = _freeze_reviewed_parent_binding(
        layout.output_path,
        authorization.get("output_parent_binding"),
    )
    if _canonical_bytes(parent_binding) != _canonical_bytes(
        authorization["output_parent_binding"]
    ):
        raise DiagnosticRunnerError(
            "authorization parent binding is not exact canonical material"
        )
    binding_digest = _require_sha256(
        authorization.get("output_parent_binding_digest"),
        "authorization parent binding digest",
    )
    if binding_digest != parent_binding["deterministic_digest"]:
        raise DiagnosticRunnerError(
            "authorization parent binding digest does not exact-match"
        )
    requirements = _publication_environment_requirements(parent_binding)
    observed_requirements = authorization.get(
        "publication_environment_requirements"
    )
    if type(observed_requirements) is not dict or _canonical_bytes(
        observed_requirements
    ) != _canonical_bytes(requirements):
        raise DiagnosticRunnerError(
            "authorization publication environment requirements do not exact-match"
        )
    return parent_binding


def _load_and_match_authorization(
    authorization_path: Path,
    supplied_digest: str,
    authorization_revision: str,
    *,
    bundle_path: Path,
    output_path: Path | str,
    repository_root: Path,
) -> tuple[_Preflight, dict[str, Any]]:
    supplied = _require_sha256(supplied_digest, "authorization digest")
    output = _regular_file_layout(output_path).output_path
    raw_authorization = Path(authorization_path)
    if raw_authorization == output or raw_authorization.is_relative_to(output):
        raise DiagnosticRunnerError("authorization file must lie outside output")
    repository = Path(repository_root).resolve()
    authorization_file, _ = _authorization_repository_location(
        raw_authorization,
        repository,
    )
    resolved_authorization = authorization_file.resolve()
    if resolved_authorization == output or resolved_authorization.is_relative_to(
        output
    ):
        raise DiagnosticRunnerError("authorization file must lie outside output")
    observed, observed_raw = _strict_canonical_object(authorization_file)
    if (
        set(observed) != _AUTHORIZATION_V2_FIELDS
        or observed.get("schema_version") != AUTHORIZATION_SCHEMA_VERSION
    ):
        raise DiagnosticRunnerError("authorization schema is unsupported")
    observed_digest = _require_sha256(
        observed.get("deterministic_digest"),
        "authorization deterministic digest",
    )
    core = {
        key: value for key, value in observed.items() if key != "deterministic_digest"
    }
    if sha256_json(core) != observed_digest or observed_digest != supplied:
        raise DiagnosticRunnerError("authorization digest does not exact-match")
    parent_binding = _reviewed_authorization_parent_binding(observed, output)
    build = _validate_authorized_build_attestation_structure(
        observed.get("runner_build_attestation")
    )
    approved_revision = _require_git_oid(
        build.get("authorized_runner_revision"),
        "authorized runner revision",
    )
    _validate_reviewed_authorization_blob(
        repository_root=repository,
        authorization_path=authorization_file,
        authorization_raw=observed_raw,
        authorized_runner_revision=approved_revision,
        reviewed_authorization_revision=authorization_revision,
    )
    preflight = _fresh_preflight(
        Path(bundle_path),
        output,
        repository,
        authorized_runner_revision=approved_revision,
        expected_output_parent_binding=parent_binding,
    )
    _validate_reviewed_authorization_blob(
        repository_root=repository,
        authorization_path=authorization_file,
        authorization_raw=observed_raw,
        authorized_runner_revision=approved_revision,
        reviewed_authorization_revision=authorization_revision,
    )
    expected = _authorization_payload(preflight)
    if observed_raw != _canonical_bytes(expected):
        raise DiagnosticRunnerError(
            "authorization bytes do not exact-match fresh preflight"
        )
    _, final_raw = _strict_canonical_object(authorization_file)
    if final_raw != observed_raw:
        raise DiagnosticRunnerError("authorization changed during fresh preflight")
    return preflight, observed


@dataclass(frozen=True)
class _ResolvedComponents:
    tasks: dict[str, CountdownTask]
    proposals: dict[str, TrackAProposalSpec]
    methods: dict[str, TrackAMethodSpec]
    budgets: dict[str, TrackABudgetProfile]


def _resolve_components(payloads: Mapping[str, Any]) -> _ResolvedComponents:
    tasks: dict[str, CountdownTask] = {}
    for row in payloads["diagnostic_tasks.json"]["tasks"]:
        task = CountdownTask(tuple(row["inputs"]), row["target"])
        if task.to_dict() != row:
            raise DiagnosticRunnerError("sealed task failed typed reconstruction")
        tasks[task.task_fingerprint] = task

    proposals: dict[str, TrackAProposalSpec] = {}
    for row in payloads["proposals.json"]["policies"]:
        spec = TrackAProposalSpec(row["spec"]["policy_id"])
        if (
            spec.to_dict() != row["spec"]
            or spec.deterministic_digest != row["spec_digest"]
        ):
            raise DiagnosticRunnerError("sealed proposal failed typed reconstruction")
        proposals[row["label"]] = spec

    methods: dict[str, TrackAMethodSpec] = {}
    for row in payloads["methods.json"]["methods"]:
        source = row["spec"]
        spec = TrackAMethodSpec(
            method=source["method"],
            selected_source=source["selected_source"],
            c_puct=source["c_puct"],
            prior_bonus=source["prior_bonus"],
            posterior_sd_scale=source["posterior_sd_scale"],
            beam_width=source["beam_width"],
            selection_rule_id=source.get("selection_rule_id"),
            terminal_value_rule_id=source.get("terminal_value_rule_id"),
            greedy_anchor_trajectory_count=source.get("greedy_anchor_trajectory_count"),
            schema_version=source["schema_version"],
        )
        if spec.to_dict() != source or sha256_json(source) != row["spec_digest"]:
            raise DiagnosticRunnerError("sealed method failed typed reconstruction")
        methods[row["label"]] = spec

    budgets: dict[str, TrackABudgetProfile] = {}
    for row in payloads["budgets.json"]["profiles"]:
        source = row["spec"]
        profile = TrackABudgetProfile(
            profile_id=source["profile_id"],
            primary_axis=source["primary_axis"],
            budget=TrackAWorkBudget(**source["budget"]),
            schema_version=source["schema_version"],
        )
        if profile.to_dict() != source or sha256_json(source) != row["spec_digest"]:
            raise DiagnosticRunnerError("sealed budget failed typed reconstruction")
        budgets[profile.profile_id] = profile
    return _ResolvedComponents(tasks, proposals, methods, budgets)


def _validate_cell_component_bindings(
    cell: DiagnosticCell,
    *,
    task: CountdownTask,
    proposal: TrackAProposalSpec,
    method: TrackAMethodSpec,
    budget_profile: TrackABudgetProfile,
    method_manifest_digest: str,
) -> None:
    if task.task_fingerprint != cell.task_fingerprint:
        raise DiagnosticRunnerError("cell task fingerprint does not match typed task")
    if proposal.deterministic_digest != cell.proposal_spec_digest:
        raise DiagnosticRunnerError(
            "cell proposal digest does not match typed proposal"
        )
    if sha256_json(method.to_dict()) != cell.method_spec_digest:
        raise DiagnosticRunnerError("cell method digest does not match typed method")
    if sha256_json(budget_profile.to_dict()) != cell.budget_profile_spec_digest:
        raise DiagnosticRunnerError("cell budget digest does not match typed budget")
    if method_manifest_digest != cell.method_manifest_digest:
        raise DiagnosticRunnerError("cell method-manifest digest drifted")


def _execute_cell(
    cell: DiagnosticCell,
    *,
    task: CountdownTask,
    proposal: TrackAProposalSpec,
    method: TrackAMethodSpec,
    budget_profile: TrackABudgetProfile,
    diagnostic_seal_digest: str,
    method_manifest_digest: str,
    runtime_qualification_digest: str,
    runner_build_digest: str,
    search_build_digest: str,
) -> dict[str, Any]:
    """Execute and independently replay one already-authorized typed cell."""

    _validate_cell_component_bindings(
        cell,
        task=task,
        proposal=proposal,
        method=method,
        budget_profile=budget_profile,
        method_manifest_digest=method_manifest_digest,
    )
    search_started = time.perf_counter_ns()
    result = run_countdown_track_a_search(
        task,
        proposal=proposal,
        method=method,
        budget_profile=budget_profile,
        exploration_seed=cell.exploration_seed,
    )
    search_wall_time_ns = time.perf_counter_ns() - search_started
    trace_bytes = result.canonical_bytes
    replay_started = time.perf_counter_ns()
    replayed = replay_countdown_track_a_search_bytes(
        trace_bytes,
        task=task,
        proposal=proposal,
        method=method,
        budget_profile=budget_profile,
        exploration_seed=cell.exploration_seed,
        expected_run_identity_digest=result.run_identity_digest,
    )
    replay_wall_time_ns = time.perf_counter_ns() - replay_started
    if search_wall_time_ns < 0 or replay_wall_time_ns < 0:
        raise DiagnosticRunnerError("monotonic wall-time telemetry moved backwards")
    if replayed != trace_bytes:
        raise DiagnosticRunnerError("two-stage replay was not byte-identical")
    ledger = result.record["ledger_snapshot"]
    primary = budget_profile.primary_axis
    non_primary = {
        axis: ledger["remaining"][axis] for axis in TRACK_A_WORK_AXES if axis != primary
    }
    record_core = {
        "budget_evidence": {
            "blocked_axes": result.summary["stop_blocked_axes"],
            "budget_valid": result.summary["budget_valid"],
            "non_primary_headroom": non_primary,
            "primary_axis": primary,
            "primary_headroom": ledger["remaining"][primary],
            "profile_spec": budget_profile.to_dict(),
            "remaining": ledger["remaining"],
            "stop_reason": result.summary["stop_reason"],
            "usage": ledger["usage"],
        },
        "bundle_id": BUNDLE_ID,
        "diagnostic_seal_digest": diagnostic_seal_digest,
        "cell_id": cell.cell_id,
        "cell_key": cell.key,
        "labels": {
            "budget_profile_id": cell.budget_profile_id,
            "exploration_seed": cell.exploration_seed,
            "method_label": cell.method_label,
            "proposal_label": cell.proposal_label,
            "task_fingerprint": cell.task_fingerprint,
        },
        "method_manifest_digest": method_manifest_digest,
        "provider_calls": 0,
        "replay": {
            "replayed_sha256": _sha256_bytes(replayed),
            "stage1_generative": "PASS",
            "stage2_byte_identical": "PASS",
        },
        "runner_build_digest": runner_build_digest,
        "runtime_qualification_digest": runtime_qualification_digest,
        "schema_version": RUN_RECORD_SCHEMA_VERSION,
        "search_build_digest": search_build_digest,
        "search_record": result.record,
        "search_run_identity_digest": result.run_identity_digest,
        "search_summary": result.summary,
        "search_trace_byte_count": len(trace_bytes),
        "search_trace_sha256": _sha256_bytes(trace_bytes),
        "telemetry": {
            "replay_wall_time_ns": replay_wall_time_ns,
            "role": _TELEMETRY_ROLE,
            "search_wall_time_ns": search_wall_time_ns,
        },
    }
    return _with_digest(record_core)


@dataclass(frozen=True)
class _Attempt:
    directory: Path
    directory_fd: int
    directory_identity: tuple[int, int]
    directory_name: str
    staging_path: Path
    receipt_base: dict[str, Any]


def _attempt_receipt(
    attempt: _Attempt,
    *,
    phase: str,
    status: str,
    reason: str | None = None,
    run_manifest_digest: str | None = None,
) -> dict[str, Any]:
    core = {
        **attempt.receipt_base,
        "phase": phase,
        "status": status,
    }
    if reason is not None:
        core["reason"] = reason
    if run_manifest_digest is not None:
        core["run_manifest_digest"] = run_manifest_digest
    return _with_digest(core)


def _write_attempt_receipt(
    attempt: _Attempt,
    filename: str,
    *,
    phase: str,
    status: str,
    reason: str | None = None,
    run_manifest_digest: str | None = None,
) -> dict[str, Any]:
    payload = _attempt_receipt(
        attempt,
        phase=phase,
        status=status,
        reason=reason,
        run_manifest_digest=run_manifest_digest,
    )
    _write_canonical_file_noreplace_at(attempt.directory_fd, filename, payload)
    return payload


def _attempt_receipt_matches(
    attempt: _Attempt,
    filename: str,
    payload: Mapping[str, Any],
) -> bool:
    try:
        observed = _read_regular_file_at(attempt.directory_fd, filename)
    except DiagnosticPublicationStateAmbiguousError:
        raise
    except (FileNotFoundError, DiagnosticRunnerError):
        return False
    except OSError as error:
        raise DiagnosticPublicationStateAmbiguousError(
            f"attempt receipt observation failed: {filename}"
        ) from error
    return observed == _canonical_bytes(payload)


def _published_attempt_entry_is_pinned(
    parent_fd: int,
    attempt_name: str,
    temporary_name: str,
    pinned_fd: int,
    pinned_identity: tuple[int, int],
) -> bool:
    """Prove the destination entry is the renamed private directory inode."""

    try:
        source = os.stat(
            temporary_name,
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        pass
    except OSError as error:
        raise DiagnosticPublicationStateAmbiguousError(
            "attempt reservation source observation failed"
        ) from error
    else:
        if (source.st_dev, source.st_ino) == pinned_identity:
            return False
    try:
        destination = os.stat(
            attempt_name,
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
        pinned = os.fstat(pinned_fd)
    except FileNotFoundError:
        return False
    except OSError as error:
        raise DiagnosticPublicationStateAmbiguousError(
            "attempt reservation destination observation failed"
        ) from error
    if (
        not stat.S_ISDIR(destination.st_mode)
        or not stat.S_ISDIR(pinned.st_mode)
        or (destination.st_dev, destination.st_ino) != pinned_identity
        or (pinned.st_dev, pinned.st_ino) != pinned_identity
    ):
        return False
    return True


def _published_attempt_reservation_matches(
    parent_fd: int,
    attempt_name: str,
    temporary_name: str,
    pinned_fd: int,
    pinned_identity: tuple[int, int],
    pre_outcome_receipt: Mapping[str, Any],
) -> bool:
    """Prove an ambiguous rename published the exact private reservation."""

    if not _published_attempt_entry_is_pinned(
        parent_fd,
        attempt_name,
        temporary_name,
        pinned_fd,
        pinned_identity,
    ):
        return False
    try:
        if not _directory_has_exact_entries(pinned_fd, {"pre_outcome.json"}):
            return False
        if _read_regular_file_at(
            pinned_fd,
            "pre_outcome.json",
        ) != _canonical_bytes(pre_outcome_receipt):
            return False
        return _published_attempt_entry_is_pinned(
            parent_fd,
            attempt_name,
            temporary_name,
            pinned_fd,
            pinned_identity,
        )
    except DiagnosticPublicationStateAmbiguousError:
        raise
    except (FileNotFoundError, DiagnosticRunnerError):
        return False
    except OSError as error:
        raise DiagnosticPublicationStateAmbiguousError(
            "attempt reservation content observation failed"
        ) from error


def _directory_entry_identity_at(
    parent_fd: int,
    name: str,
    *,
    label: str,
) -> tuple[int, int] | None:
    try:
        observed = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise DiagnosticPublicationStateAmbiguousError(
            f"{label} observation failed"
        ) from error
    if not stat.S_ISDIR(observed.st_mode):
        return None
    return observed.st_dev, observed.st_ino


def _entry_identity_at(
    parent_fd: int,
    name: str,
    *,
    label: str,
) -> tuple[int, int] | None:
    """Observe any non-followed directory entry without conflating its type."""

    try:
        observed = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise DiagnosticPublicationStateAmbiguousError(
            f"{label} observation failed"
        ) from error
    return observed.st_dev, observed.st_ino


def _quarantine_exact_directory_at(
    parent_fd: int,
    public_name: str,
    pinned_fd: int,
    pinned_identity: tuple[int, int],
    *,
    label: str,
) -> str | None:
    """Revoke a directory name by retaining the exact inode as a tombstone."""

    tombstone_name = ""
    rename_error: BaseException | None = None
    for _attempt in range(128):
        candidate = f".{public_name}.revoked-{secrets.token_hex(16)}"
        try:
            _rename_noreplace_at(
                parent_fd,
                public_name,
                parent_fd,
                candidate,
            )
        except FileExistsError:
            continue
        except BaseException as error:
            tombstone_name = candidate
            rename_error = error
            break
        tombstone_name = candidate
        break
    if not tombstone_name:
        raise DiagnosticPublicationStateAmbiguousError(
            f"could not allocate {label} tombstone"
        )

    tombstone_identity = _entry_identity_at(
        parent_fd,
        tombstone_name,
        label=f"quarantined {label}",
    )
    try:
        pinned = os.fstat(pinned_fd)
    except OSError as error:
        raise DiagnosticPublicationStateAmbiguousError(
            f"pinned {label} observation failed"
        ) from error
    pinned_now = (pinned.st_dev, pinned.st_ino)
    if tombstone_identity != pinned_identity or pinned_now != pinned_identity:
        if tombstone_identity is not None:
            if not _restore_quarantined_entry_at(
                parent_fd,
                tombstone_name,
                public_name,
                captured_identity=tombstone_identity,
            ):
                raise DiagnosticPublicationStateAmbiguousError(
                    f"foreign {label} was quarantined and could not be restored"
                ) from rename_error
        try:
            os.fsync(parent_fd)
        except OSError as error:
            raise DiagnosticPublicationStateAmbiguousError(
                f"{label} absence durability failed"
            ) from error
        public_identity = _directory_entry_identity_at(
            parent_fd,
            public_name,
            label=label,
        )
        if public_identity == pinned_identity:
            raise DiagnosticPublicationStateAmbiguousError(
                f"exact {label} remained after quarantine failure"
            ) from rename_error
        return None

    try:
        os.fsync(parent_fd)
    except OSError as error:
        raise DiagnosticPublicationStateAmbiguousError(
            f"{label} tombstone durability failed"
        ) from error
    if (
        _directory_entry_identity_at(
            parent_fd,
            tombstone_name,
            label=f"quarantined {label}",
        )
        != pinned_identity
    ):
        raise DiagnosticPublicationStateAmbiguousError(
            f"exact {label} tombstone changed after the durability barrier"
        )
    if (
        _directory_entry_identity_at(
            parent_fd,
            public_name,
            label=label,
        )
        == pinned_identity
    ):
        raise DiagnosticPublicationStateAmbiguousError(
            f"exact {label} remained named after tombstoning"
        )
    return tombstone_name


def _revoke_exact_attempt_reservation(
    parent_fd: int,
    attempt_name: str,
    temporary_name: str,
    pinned_fd: int,
    pinned_identity: tuple[int, int],
    pre_outcome_receipt: Mapping[str, Any],
) -> bool:
    """Durably tombstone one exact pre-outcome reservation."""

    if not _published_attempt_reservation_matches(
        parent_fd,
        attempt_name,
        temporary_name,
        pinned_fd,
        pinned_identity,
        pre_outcome_receipt,
    ):
        return False
    try:
        tombstone_name = _quarantine_exact_directory_at(
            parent_fd,
            attempt_name,
            pinned_fd,
            pinned_identity,
            label="attempt reservation",
        )
        if tombstone_name is None:
            return False
        if not _directory_has_exact_entries(pinned_fd, {"pre_outcome.json"}):
            return False
        if _read_regular_file_at(
            pinned_fd,
            "pre_outcome.json",
        ) != _canonical_bytes(pre_outcome_receipt):
            return False
        if (
            _directory_entry_identity_at(
                parent_fd,
                tombstone_name,
                label="quarantined attempt reservation",
            )
            != pinned_identity
        ):
            return False
        return True
    except DiagnosticPublicationStateAmbiguousError as error:
        raise DiagnosticPublicationStateAmbiguousError(
            "attempt reservation exact rollback failed"
        ) from error
    except (FileNotFoundError, DiagnosticRunnerError):
        return False
    except OSError as error:
        raise DiagnosticPublicationStateAmbiguousError(
            "attempt reservation exact rollback failed"
        ) from error


def _durably_prove_attempt_not_published(
    parent_fd: int,
    attempt_name: str,
    temporary_name: str,
    pinned_fd: int,
    pinned_identity: tuple[int, int],
    pre_outcome_receipt: Mapping[str, Any],
) -> bool:
    """Barrier the parent and prove the pinned reservation is not authoritative."""

    try:
        os.fsync(parent_fd)
    except OSError as error:
        raise DiagnosticPublicationStateAmbiguousError(
            "attempt reservation absence durability failed"
        ) from error
    if _published_attempt_reservation_matches(
        parent_fd,
        attempt_name,
        temporary_name,
        pinned_fd,
        pinned_identity,
        pre_outcome_receipt,
    ):
        return False
    if _published_attempt_entry_is_pinned(
        parent_fd,
        attempt_name,
        temporary_name,
        pinned_fd,
        pinned_identity,
    ):
        raise DiagnosticPublicationStateAmbiguousError(
            "attempt reservation is pinned but its exact content is unproven"
        )
    return True


def _cleanup_private_attempt_scratch(
    parent_fd: int,
    temporary_name: str,
    temporary_fd: int,
    pinned_identity: tuple[int, int],
    pre_outcome_receipt: Mapping[str, Any],
) -> None:
    """Best-effort tombstoning bound to the exact private scratch inode."""

    try:
        observed = os.stat(
            temporary_name,
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
        pinned = os.fstat(temporary_fd)
        if (
            not stat.S_ISDIR(observed.st_mode)
            or (observed.st_dev, observed.st_ino) != pinned_identity
            or (pinned.st_dev, pinned.st_ino) != pinned_identity
        ):
            return
        if not _directory_has_exact_entries(temporary_fd, {"pre_outcome.json"}):
            return
        if _read_regular_file_at(
            temporary_fd,
            "pre_outcome.json",
        ) != _canonical_bytes(pre_outcome_receipt):
            return
        _quarantine_exact_directory_at(
            parent_fd,
            temporary_name,
            temporary_fd,
            pinned_identity,
            label="attempt scratch",
        )
    except BaseException:
        # An unproven path is never removed.  A leftover private scratch is
        # preferable to touching a raced or foreign directory entry. Cleanup
        # cannot supersede the typed result selected by attempt publication.
        return


def _transition_attempt_to_started(attempt: _Attempt) -> dict[str, Any]:
    """Publish STARTED only with exact bytes and directory durability."""

    expected = _attempt_receipt(
        attempt,
        phase="STARTED",
        status="PENDING",
    )
    try:
        _write_attempt_receipt(
            attempt,
            "started.json",
            phase="STARTED",
            status="PENDING",
        )
    except BaseException as error:
        reason = str(error)
        try:
            os.fsync(attempt.directory_fd)
        except BaseException:
            try:
                expected_bytes = _canonical_bytes(expected)
                identity = _exact_regular_file_identity_at(
                    attempt.directory_fd,
                    "started.json",
                    expected_bytes,
                    label="STARTED receipt",
                )
                if identity is not None:
                    _quarantine_exact_file_at(
                        attempt.directory_fd,
                        "started.json",
                        expected_bytes,
                        expected_identity=identity,
                        label="STARTED receipt",
                    )
                elif not _durably_prove_file_not_exact_at(
                    attempt.directory_fd,
                    "started.json",
                    expected_bytes,
                    label="STARTED receipt",
                ):
                    raise DiagnosticPublicationStateAmbiguousError(
                        "STARTED receipt appeared during rollback proof"
                    )
                started_is_durable = False
            except BaseException as rollback_error:
                if isinstance(
                    rollback_error,
                    DiagnosticPublicationStateAmbiguousError,
                ):
                    raise
                raise DiagnosticPublicationStateAmbiguousError(
                    "STARTED receipt durability and exact rollback are unproven"
                ) from rollback_error
        else:
            started_is_durable = _attempt_receipt_matches(
                attempt,
                "started.json",
                expected,
            )

        if started_is_durable:
            try:
                _write_attempt_receipt(
                    attempt,
                    "invalid.json",
                    phase="STARTED",
                    status="INVALID",
                    reason=reason,
                )
            except BaseException as terminal_error:
                raise DiagnosticPublicationStateAmbiguousError(
                    "INVALID receipt durability is unproven after STARTED"
                ) from terminal_error
            raise DiagnosticInvalidRunError(reason) from error
        try:
            _write_attempt_receipt(
                attempt,
                "not_run.json",
                phase="PRE_OUTCOME",
                status="NOT_RUN",
                reason=reason,
            )
        except BaseException as terminal_error:
            raise DiagnosticPublicationStateAmbiguousError(
                "NOT_RUN receipt durability is unproven before STARTED"
            ) from terminal_error
        try:
            os.fsync(attempt.directory_fd)
            started_after_not_run = _attempt_receipt_matches(
                attempt,
                "started.json",
                expected,
            )
        except BaseException as reconciliation_error:
            raise DiagnosticPublicationStateAmbiguousError(
                "STARTED state after NOT_RUN publication is unproven"
            ) from reconciliation_error
        if started_after_not_run:
            try:
                _write_attempt_receipt(
                    attempt,
                    "invalid.json",
                    phase="STARTED",
                    status="INVALID",
                    reason=reason,
                )
            except BaseException as terminal_error:
                raise DiagnosticPublicationStateAmbiguousError(
                    "INVALID receipt durability is unproven after late STARTED"
                ) from terminal_error
            raise DiagnosticInvalidRunError(reason) from error
        raise DiagnosticNotRunError(reason) from error
    return expected


def _reserve_attempt(
    preflight: _Preflight,
    authorization: Mapping[str, Any],
    reviewed_authorization_revision: str,
    *,
    parent_fd: int,
) -> _Attempt:
    """Permanently reserve one authorization before any sealed lookup."""

    output = preflight.output_path
    parent = output.parent
    try:
        os.stat(output.name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        pass
    else:
        raise DiagnosticNotRunError(f"run artifact destination exists: {output}")
    authorization_digest = _require_sha256(
        authorization.get("deterministic_digest"),
        "authorization deterministic digest",
    )
    attempt_name = f".{output.name}.attempt-{authorization_digest}"
    attempt_directory = parent / attempt_name
    staging_path = attempt_directory / "staging"
    receipt_base = {
        "artifact_id": output.name,
        "authorization_digest": authorization_digest,
        "authorized_output_path": str(output),
        "diagnostic_seal_digest": preflight.bundle.seal_digest,  # type: ignore[attr-defined]
        "execution_head_revision": preflight.build.current_head,
        "reviewed_authorization_revision": reviewed_authorization_revision,
        "runner_build_digest": preflight.build.payload["runner_build_digest"],
        "schema_version": ATTEMPT_MARKER_SCHEMA_VERSION,
        "search_build_digest": preflight.build.payload["search_build_digest"],
        "staging_path": str(staging_path),
    }
    temporary_name = ""
    for _attempt in range(128):
        candidate = f".{output.name}.attempt-tmp-{secrets.token_hex(16)}"
        try:
            os.mkdir(candidate, 0o700, dir_fd=parent_fd)
        except FileExistsError:
            continue
        temporary_name = candidate
        break
    if not temporary_name:
        raise DiagnosticNotRunError("could not allocate attempt reservation scratch")
    temporary = parent / temporary_name
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    temporary_fd = os.open(temporary_name, flags, dir_fd=parent_fd)
    temporary_stat = os.fstat(temporary_fd)
    temporary_identity = (temporary_stat.st_dev, temporary_stat.st_ino)
    attempt = _Attempt(
        directory=temporary,
        directory_fd=temporary_fd,
        directory_identity=temporary_identity,
        directory_name=temporary_name,
        staging_path=temporary / "staging",
        receipt_base={
            **receipt_base,
            "staging_path": str(staging_path),
        },
    )
    pre_outcome_receipt = _attempt_receipt(
        attempt,
        phase="PRE_OUTCOME",
        status="PENDING",
    )
    completed = False
    try:
        _write_attempt_receipt(
            attempt,
            "pre_outcome.json",
            phase="PRE_OUTCOME",
            status="PENDING",
        )
        os.fsync(temporary_fd)
        try:
            _rename_noreplace_at(
                parent_fd,
                temporary_name,
                parent_fd,
                attempt_name,
            )
        except BaseException as error:
            if not _published_attempt_reservation_matches(
                parent_fd,
                attempt_name,
                temporary_name,
                temporary_fd,
                temporary_identity,
                pre_outcome_receipt,
            ):
                if _published_attempt_entry_is_pinned(
                    parent_fd,
                    attempt_name,
                    temporary_name,
                    temporary_fd,
                    temporary_identity,
                ):
                    raise DiagnosticPublicationStateAmbiguousError(
                        "published attempt reservation is pinned but its exact "
                        "content cannot be authorized"
                    ) from error
                if not _durably_prove_attempt_not_published(
                    parent_fd,
                    attempt_name,
                    temporary_name,
                    temporary_fd,
                    temporary_identity,
                    pre_outcome_receipt,
                ):
                    raise DiagnosticPublicationStateAmbiguousError(
                        "attempt reservation appeared during absence proof"
                    ) from error
                if isinstance(error, FileExistsError):
                    raise DiagnosticNotRunError(
                        "authorization already has a durable attempt marker"
                    ) from error
                raise DiagnosticNotRunError(str(error)) from error
        if not _published_attempt_reservation_matches(
            parent_fd,
            attempt_name,
            temporary_name,
            temporary_fd,
            temporary_identity,
            pre_outcome_receipt,
        ):
            if _published_attempt_entry_is_pinned(
                parent_fd,
                attempt_name,
                temporary_name,
                temporary_fd,
                temporary_identity,
            ):
                raise DiagnosticPublicationStateAmbiguousError(
                    "published attempt reservation is pinned but its exact "
                    "content cannot be authorized"
                )
            if not _durably_prove_attempt_not_published(
                parent_fd,
                attempt_name,
                temporary_name,
                temporary_fd,
                temporary_identity,
                pre_outcome_receipt,
            ):
                raise DiagnosticPublicationStateAmbiguousError(
                    "attempt reservation appeared during absence proof"
                )
            raise DiagnosticNotRunError(
                "attempt reservation publication identity or bytes drifted"
            )
        try:
            os.fsync(parent_fd)
        except BaseException as error:
            try:
                os.fsync(parent_fd)
                retry_proved_exact = _published_attempt_reservation_matches(
                    parent_fd,
                    attempt_name,
                    temporary_name,
                    temporary_fd,
                    temporary_identity,
                    pre_outcome_receipt,
                )
            except DiagnosticPublicationStateAmbiguousError:
                raise
            except BaseException:
                retry_proved_exact = False
            if not retry_proved_exact:
                exact_is_still_published = _published_attempt_reservation_matches(
                    parent_fd,
                    attempt_name,
                    temporary_name,
                    temporary_fd,
                    temporary_identity,
                    pre_outcome_receipt,
                )
                if exact_is_still_published and _revoke_exact_attempt_reservation(
                    parent_fd,
                    attempt_name,
                    temporary_name,
                    temporary_fd,
                    temporary_identity,
                    pre_outcome_receipt,
                ):
                    raise DiagnosticNotRunError(
                        "attempt reservation was durably revoked after a "
                        "parent-directory sync failure"
                    ) from error
                if not exact_is_still_published and (
                    _durably_prove_attempt_not_published(
                        parent_fd,
                        attempt_name,
                        temporary_name,
                        temporary_fd,
                        temporary_identity,
                        pre_outcome_receipt,
                    )
                ):
                    raise DiagnosticNotRunError(
                        "attempt reservation was durably absent after a "
                        "parent-directory sync failure"
                    ) from error
                raise DiagnosticPublicationStateAmbiguousError(
                    "attempt reservation durability and exact rollback are both "
                    "unproven"
                ) from error
        if not _published_attempt_reservation_matches(
            parent_fd,
            attempt_name,
            temporary_name,
            temporary_fd,
            temporary_identity,
            pre_outcome_receipt,
        ):
            if _published_attempt_entry_is_pinned(
                parent_fd,
                attempt_name,
                temporary_name,
                temporary_fd,
                temporary_identity,
            ):
                raise DiagnosticPublicationStateAmbiguousError(
                    "attempt reservation changed after its durability barrier"
                )
            if _durably_prove_attempt_not_published(
                parent_fd,
                attempt_name,
                temporary_name,
                temporary_fd,
                temporary_identity,
                pre_outcome_receipt,
            ):
                raise DiagnosticPublicationStateAmbiguousError(
                    "attempt reservation was durably lost after publication"
                )
            raise DiagnosticPublicationStateAmbiguousError(
                "attempt reservation appeared during post-barrier proof"
            )
        completed = True
    finally:
        if not completed:
            _cleanup_private_attempt_scratch(
                parent_fd,
                temporary_name,
                temporary_fd,
                temporary_identity,
                pre_outcome_receipt,
            )
            _close_descriptor_best_effort(temporary_fd)
    return _Attempt(
        directory=attempt_directory,
        directory_fd=temporary_fd,
        directory_identity=temporary_identity,
        directory_name=attempt_name,
        staging_path=staging_path,
        receipt_base=receipt_base,
    )


def _publish_run_artifact(
    preflight: _Preflight,
    authorization: Mapping[str, Any],
    *,
    reviewed_authorization_revision: str,
    repository_root: Path,
    _terminal_result: bool = False,
) -> dict[str, Any]:
    """Exercise the legacy directory protocol on non-diagnostic fixtures only.

    Portable POSIX does not provide an atomic mkdir-and-return-fd primitive, so
    this layout cannot prove ownership across the pre-first-stat interval.  A
    real verified diagnostic preflight is therefore refused before any output
    filesystem access.  The remaining implementation exists only to preserve
    synthetic protocol tests while a regular-file artifact layout is designed.
    """

    preflight = _snapshot_exact_synthetic_preflight(preflight)
    authorization = _snapshot_exact_synthetic_authorization(
        preflight,
        authorization,
    )
    try:
        repository_root = _snapshot_exact_absolute_path(
            repository_root,
            "synthetic repository root",
            require_leaf=False,
        )
        reviewed_authorization_revision = _require_git_oid(
            reviewed_authorization_revision,
            "reviewed authorization revision",
        )
        if type(_terminal_result) is not bool:
            raise DiagnosticRunnerError("synthetic terminal-result mode is not boolean")
    except BaseException as error:
        raise DiagnosticNotRunError(_PUBLICATION_BACKEND_REFUSAL) from error

    output = preflight.output_path
    parent = output.parent
    parent_fd = -1
    lock_created = False
    lock_fd = -1
    lock_identity: tuple[int, int] | None = None
    lock_name = f".{output.name}.publish-lock"
    lock_retirement_attempted = False
    lock_retired = False
    publication_entered = False

    def retire_publication_lock() -> None:
        nonlocal lock_retired, lock_retirement_attempted
        if lock_retired:
            return
        if lock_retirement_attempted:
            raise _PublicationLockRetirementAmbiguousError(
                "publication lock retirement was already attempted"
            )
        lock_retirement_attempted = True
        if not lock_created or parent_fd < 0 or lock_fd < 0 or lock_identity is None:
            raise _PublicationLockRetirementAmbiguousError(
                "publication lock retirement authority is unavailable"
            )
        try:
            _quarantine_exact_directory_at(
                parent_fd,
                lock_name,
                lock_fd,
                lock_identity,
                label="publication lock",
            )
        except BaseException as error:
            raise _PublicationLockRetirementAmbiguousError(
                "publication lock retirement and foreign-entry restoration "
                "are ambiguous"
            ) from error
        lock_retired = True

    try:
        parent_fd, parent_stat = _open_stable_directory(
            parent,
            "run output parent",
        )
        try:
            os.mkdir(lock_name, 0o700, dir_fd=parent_fd)
        except FileExistsError as error:
            raise DiagnosticNotRunError(
                f"run artifact publication is locked: {parent / lock_name}"
            ) from error
        lock_created = True
        lock_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        lock_flags |= getattr(os, "O_NOFOLLOW", 0)
        lock_fd = os.open(lock_name, lock_flags, dir_fd=parent_fd)
        lock_stat = os.fstat(lock_fd)
        lock_identity = (lock_stat.st_dev, lock_stat.st_ino)
        _assert_directory_path_identity(
            parent,
            parent_fd,
            parent_stat,
            "run output parent",
        )
        publication_entered = True
        manifest_payload, commit_payload = _publish_run_artifact_locked(
            preflight,
            authorization,
            reviewed_authorization_revision=reviewed_authorization_revision,
            repository_root=repository_root,
            parent_fd=parent_fd,
            parent_stat=parent_stat,
            _retire_publication_lock=retire_publication_lock,
        )
        if _terminal_result:
            return {
                "artifact_commit_digest": commit_payload["deterministic_digest"],
                "artifact_id": manifest_payload["artifact_id"],
                "artifact_path": str(preflight.output_path),
                "run_manifest_digest": manifest_payload["deterministic_digest"],
                "status": "COMMITTED",
            }
        return manifest_payload
    except (
        DiagnosticNotRunError,
        DiagnosticInvalidRunError,
        DiagnosticPublicationStateAmbiguousError,
    ):
        raise
    except BaseException as error:
        if publication_entered:
            raise DiagnosticPublicationStateAmbiguousError(
                "untyped failure at or after the publication call boundary"
            ) from error
        raise DiagnosticNotRunError(str(error)) from error
    finally:
        primary_error = sys.exc_info()[1]
        cleanup_error: BaseException | None = None
        if (
            lock_created
            and parent_fd >= 0
            and lock_fd >= 0
            and lock_identity is not None
            and not lock_retirement_attempted
        ):
            try:
                retire_publication_lock()
            except BaseException as error:
                cleanup_error = error
        _close_descriptor_best_effort(lock_fd)
        _close_descriptor_best_effort(parent_fd)
        if cleanup_error is not None and not isinstance(
            primary_error,
            DiagnosticPublicationStateAmbiguousError,
        ):
            raise cleanup_error


def _publish_run_artifact_locked(
    preflight: _Preflight,
    authorization: Mapping[str, Any],
    *,
    reviewed_authorization_revision: str,
    repository_root: Path,
    parent_fd: int,
    parent_stat: os.stat_result,
    _retire_publication_lock: Callable[[], None] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    output = preflight.output_path
    if (
        type(preflight.bundle) is not _SyntheticFixtureBundleSnapshot
        or type(authorization) is not dict
        or preflight.synthetic_components is None
        or type(preflight.synthetic_method_manifest_digest) is not str
        or preflight.synthetic_expected_cell_count != _SYNTHETIC_EXPECTED_CELL_COUNT
    ):
        raise DiagnosticNotRunError(_PUBLICATION_BACKEND_REFUSAL)
    cells = preflight.cells
    components = preflight.synthetic_components
    method_manifest_digest = preflight.synthetic_method_manifest_digest
    expected_cell_count = preflight.synthetic_expected_cell_count
    seal_digest = preflight.bundle.seal_digest
    build = preflight.build.payload
    qualification = preflight.qualification

    def retire_before_terminal_proof() -> None:
        if _retire_publication_lock is not None:
            _retire_publication_lock()

    if (
        authorization.get("output_path") != str(output)
        or authorization.get("artifact_id") != output.name
    ):
        raise DiagnosticRunnerError("authorization output identity drifted")
    reviewed = _require_git_oid(
        reviewed_authorization_revision,
        "reviewed authorization revision",
    )
    _assert_directory_path_identity(
        output.parent,
        parent_fd,
        parent_stat,
        "run output parent",
    )
    attempt = _reserve_attempt(
        preflight,
        authorization,
        reviewed,
        parent_fd=parent_fd,
    )
    pre_outcome_receipt = _attempt_receipt(
        attempt,
        phase="PRE_OUTCOME",
        status="PENDING",
    )
    expected_started_receipt = _attempt_receipt(
        attempt,
        phase="STARTED",
        status="PENDING",
    )
    staging_fd = -1
    output_fd = -1
    try:
        # This is the final PRE_OUTCOME closure.  No sealed task or proposal has
        # been reconstructed yet, and the immutable reservation already makes
        # reuse of this authorization impossible.
        _recheck_source_closure(Path(repository_root), preflight.build)
        _assert_directory_path_identity(
            output.parent,
            parent_fd,
            parent_stat,
            "run output parent",
        )
        os.mkdir("staging", 0o700, dir_fd=attempt.directory_fd)
        staging_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        staging_flags |= getattr(os, "O_NOFOLLOW", 0)
        staging_fd = os.open(
            "staging",
            staging_flags,
            dir_fd=attempt.directory_fd,
        )
        os.fsync(attempt.directory_fd)
    except BaseException as error:
        reason = str(error)
        try:
            _prove_attempt_terminal_authority(
                parent=output.parent,
                parent_fd=parent_fd,
                parent_stat=parent_stat,
                attempt=attempt,
            )
            not_run_receipt = _write_attempt_receipt(
                attempt,
                "not_run.json",
                phase="PRE_OUTCOME",
                status="NOT_RUN",
                reason=reason,
            )
            os.fsync(attempt.directory_fd)
            started_after_not_run = _attempt_receipt_matches(
                attempt,
                "started.json",
                expected_started_receipt,
            )
        except DiagnosticPublicationStateAmbiguousError:
            _close_descriptor_best_effort(staging_fd)
            _close_descriptor_best_effort(attempt.directory_fd)
            raise
        except BaseException as terminal_error:
            _close_descriptor_best_effort(staging_fd)
            _close_descriptor_best_effort(attempt.directory_fd)
            raise DiagnosticPublicationStateAmbiguousError(
                "NOT_RUN receipt durability is unproven; late STARTED state "
                "could not be reconciled"
            ) from terminal_error
        if started_after_not_run:
            try:
                _prove_attempt_terminal_authority(
                    parent=output.parent,
                    parent_fd=parent_fd,
                    parent_stat=parent_stat,
                    attempt=attempt,
                )
                invalid_receipt = _write_attempt_receipt(
                    attempt,
                    "invalid.json",
                    phase="STARTED",
                    status="INVALID",
                    reason=reason,
                )
                retire_before_terminal_proof()
                _prove_attempt_terminal_authority(
                    parent=output.parent,
                    parent_fd=parent_fd,
                    parent_stat=parent_stat,
                    attempt=attempt,
                    required_receipts={"invalid.json": invalid_receipt},
                )
            except DiagnosticPublicationStateAmbiguousError:
                _close_descriptor_best_effort(staging_fd)
                _close_descriptor_best_effort(attempt.directory_fd)
                raise
            except BaseException as terminal_error:
                _close_descriptor_best_effort(staging_fd)
                _close_descriptor_best_effort(attempt.directory_fd)
                raise DiagnosticPublicationStateAmbiguousError(
                    "INVALID receipt durability is unproven after late STARTED"
                ) from terminal_error
            _close_descriptor_best_effort(staging_fd)
            _close_descriptor_best_effort(attempt.directory_fd)
            raise DiagnosticInvalidRunError(reason) from error
        try:
            retire_before_terminal_proof()
            _prove_attempt_terminal_authority(
                parent=output.parent,
                parent_fd=parent_fd,
                parent_stat=parent_stat,
                attempt=attempt,
                required_receipts={"not_run.json": not_run_receipt},
                forbidden_entries=(
                    "invalid.json",
                    "ready_to_commit.json",
                    "started.json",
                ),
            )
        except DiagnosticPublicationStateAmbiguousError:
            _close_descriptor_best_effort(staging_fd)
            _close_descriptor_best_effort(attempt.directory_fd)
            raise
        _close_descriptor_best_effort(staging_fd)
        _close_descriptor_best_effort(attempt.directory_fd)
        raise DiagnosticNotRunError(reason) from error

    try:
        started_receipt = _transition_attempt_to_started(attempt)
    except DiagnosticInvalidRunError as terminal_error:
        terminal_reason = str(terminal_error)
        try:
            retire_before_terminal_proof()
            _prove_attempt_terminal_authority(
                parent=output.parent,
                parent_fd=parent_fd,
                parent_stat=parent_stat,
                attempt=attempt,
                required_receipts={
                    "invalid.json": _attempt_receipt(
                        attempt,
                        phase="STARTED",
                        status="INVALID",
                        reason=terminal_reason,
                    )
                },
            )
        finally:
            _close_descriptor_best_effort(staging_fd)
            _close_descriptor_best_effort(attempt.directory_fd)
        raise
    except DiagnosticNotRunError as terminal_error:
        terminal_reason = str(terminal_error)
        try:
            retire_before_terminal_proof()
            _prove_attempt_terminal_authority(
                parent=output.parent,
                parent_fd=parent_fd,
                parent_stat=parent_stat,
                attempt=attempt,
                required_receipts={
                    "not_run.json": _attempt_receipt(
                        attempt,
                        phase="PRE_OUTCOME",
                        status="NOT_RUN",
                        reason=terminal_reason,
                    )
                },
                forbidden_entries=(
                    "invalid.json",
                    "ready_to_commit.json",
                    "started.json",
                ),
            )
        finally:
            _close_descriptor_best_effort(staging_fd)
            _close_descriptor_best_effort(attempt.directory_fd)
        raise
    except DiagnosticPublicationStateAmbiguousError:
        _close_descriptor_best_effort(staging_fd)
        _close_descriptor_best_effort(attempt.directory_fd)
        raise
    except BaseException as error:
        reason = str(error)
        try:
            os.fsync(attempt.directory_fd)
            started_is_durable = _attempt_receipt_matches(
                attempt,
                "started.json",
                expected_started_receipt,
            )
        except BaseException as observation_error:
            _close_descriptor_best_effort(staging_fd)
            _close_descriptor_best_effort(attempt.directory_fd)
            raise DiagnosticPublicationStateAmbiguousError(
                "STARTED transition return state is unproven"
            ) from observation_error
        if not started_is_durable:
            _close_descriptor_best_effort(staging_fd)
            _close_descriptor_best_effort(attempt.directory_fd)
            raise DiagnosticPublicationStateAmbiguousError(
                "STARTED transition return state is unproven"
            ) from error
        try:
            _prove_attempt_terminal_authority(
                parent=output.parent,
                parent_fd=parent_fd,
                parent_stat=parent_stat,
                attempt=attempt,
            )
        except DiagnosticPublicationStateAmbiguousError:
            _close_descriptor_best_effort(staging_fd)
            _close_descriptor_best_effort(attempt.directory_fd)
            raise
        try:
            invalid_receipt = _write_attempt_receipt(
                attempt,
                "invalid.json",
                phase="STARTED",
                status="INVALID",
                reason=reason,
            )
        except BaseException as terminal_error:
            _close_descriptor_best_effort(staging_fd)
            _close_descriptor_best_effort(attempt.directory_fd)
            raise DiagnosticPublicationStateAmbiguousError(
                "INVALID receipt durability is unproven after STARTED return"
            ) from terminal_error
        try:
            retire_before_terminal_proof()
            _prove_attempt_terminal_authority(
                parent=output.parent,
                parent_fd=parent_fd,
                parent_stat=parent_stat,
                attempt=attempt,
                required_receipts={"invalid.json": invalid_receipt},
            )
        except DiagnosticPublicationStateAmbiguousError:
            _close_descriptor_best_effort(staging_fd)
            _close_descriptor_best_effort(attempt.directory_fd)
            raise
        _close_descriptor_best_effort(staging_fd)
        _close_descriptor_best_effort(attempt.directory_fd)
        raise DiagnosticInvalidRunError(reason) from error

    try:
        record_digests: list[str] = []
        cell_ids: list[str] = []
        replay_wall_time_ns_total = 0
        search_wall_time_ns_total = 0
        records_hasher = hashlib.sha256()
        records_byte_count = 0
        records_descriptor = os.open(
            "records.jsonl",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=staging_fd,
        )
        with os.fdopen(records_descriptor, "wb") as handle:
            for cell in cells:
                record = _execute_cell(
                    cell,
                    task=components.tasks[cell.task_fingerprint],
                    proposal=components.proposals[cell.proposal_label],
                    method=components.methods[cell.method_label],
                    budget_profile=components.budgets[cell.budget_profile_id],
                    diagnostic_seal_digest=seal_digest,
                    method_manifest_digest=method_manifest_digest,
                    runtime_qualification_digest=(
                        preflight.runtime_qualification_digest
                    ),
                    runner_build_digest=build["runner_build_digest"],
                    search_build_digest=build["search_build_digest"],
                )
                if record.get("cell_id") != cell.cell_id:
                    raise DiagnosticRunnerError("executed record cell identity drifted")
                record_digest = _require_sha256(
                    record.get("deterministic_digest"),
                    "executed record digest",
                )
                telemetry = record.get("telemetry")
                if (
                    type(telemetry) is not dict
                    or telemetry.get("role") != _TELEMETRY_ROLE
                    or type(telemetry.get("search_wall_time_ns")) is not int
                    or telemetry["search_wall_time_ns"] < 0
                    or type(telemetry.get("replay_wall_time_ns")) is not int
                    or telemetry["replay_wall_time_ns"] < 0
                ):
                    raise DiagnosticRunnerError("executed record telemetry drifted")
                search_wall_time_ns_total += telemetry["search_wall_time_ns"]
                replay_wall_time_ns_total += telemetry["replay_wall_time_ns"]
                line = _canonical_bytes(record)
                handle.write(line)
                records_hasher.update(line)
                records_byte_count += len(line)
                record_digests.append(record_digest)
                cell_ids.append(record["cell_id"])
            handle.flush()
            os.fsync(handle.fileno())
        expected_ids = [cell.cell_id for cell in cells]
        if cell_ids != expected_ids or len(set(cell_ids)) != expected_cell_count:
            raise DiagnosticRunnerError(
                "executed record schedule is incomplete or duplicated"
            )
        if len(set(record_digests)) != expected_cell_count:
            raise DiagnosticRunnerError("executed record digests are not unique")
        run_manifest = _with_digest(
            {
                "artifact_id": authorization["artifact_id"],
                "attempt_id": authorization["deterministic_digest"],
                "attempt_marker_basename": attempt.directory.name,
                "attempt_phase": "READY_TO_COMMIT",
                "attempt_started_receipt": started_receipt,
                "attempt_started_receipt_digest": started_receipt[
                    "deterministic_digest"
                ],
                "authorized_output_path": authorization["output_path"],
                "bundle_id": BUNDLE_ID,
                "diagnostic_seal_digest": seal_digest,
                "cell_count": expected_cell_count,
                "claim_boundary": _SYNTHETIC_RUN_CLAIM_BOUNDARY,
                "execution_authorization_digest": authorization["deterministic_digest"],
                "execution_authorization": deepcopy(dict(authorization)),
                "execution_head_revision": preflight.build.current_head,
                "method_manifest_digest": method_manifest_digest,
                "record_digests": record_digests,
                "records_jsonl_byte_count": records_byte_count,
                "records_jsonl_sha256": records_hasher.hexdigest(),
                "reviewed_authorization_revision": reviewed,
                "runner_build_attestation": build,
                "runtime_qualification": qualification,
                "schedule_cell_ids": cell_ids,
                "schema_version": RUN_MANIFEST_SCHEMA_VERSION,
                "telemetry": {
                    "replay_wall_time_ns_total": replay_wall_time_ns_total,
                    "role": _TELEMETRY_ROLE,
                    "search_wall_time_ns_total": search_wall_time_ns_total,
                },
            }
        )
        commit_receipt = _with_digest(
            {
                "artifact_id": authorization["artifact_id"],
                "attempt_started_receipt_digest": started_receipt[
                    "deterministic_digest"
                ],
                "execution_authorization_digest": authorization["deterministic_digest"],
                "run_manifest_digest": run_manifest["deterministic_digest"],
                "schema_version": ARTIFACT_COMMIT_SCHEMA_VERSION,
                "status": "COMMITTED",
            }
        )
        manifest_descriptor = os.open(
            "manifest.json",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=staging_fd,
        )
        with os.fdopen(manifest_descriptor, "wb") as handle:
            handle.write(_canonical_bytes(run_manifest))
            handle.flush()
            os.fsync(handle.fileno())
        os.fsync(staging_fd)
        # Readiness evidence is durable before publication.  A copied staging
        # directory remains non-authoritative until the post-rename artifact
        # commit receipt is present and exact.
        ready_to_commit_receipt = _write_attempt_receipt(
            attempt,
            "ready_to_commit.json",
            phase="STARTED",
            status="READY_TO_COMMIT",
            run_manifest_digest=run_manifest["deterministic_digest"],
        )
        success_receipts = {
            "pre_outcome.json": pre_outcome_receipt,
            "ready_to_commit.json": ready_to_commit_receipt,
            "started.json": started_receipt,
        }
        _assert_directory_path_identity(
            output.parent,
            parent_fd,
            parent_stat,
            "run output parent",
        )
        staged_stat = os.fstat(staging_fd)
        staging_identity = (staged_stat.st_dev, staged_stat.st_ino)
        try:
            _rename_noreplace_at(
                attempt.directory_fd,
                "staging",
                parent_fd,
                output.name,
            )
        except BaseException:
            if not _published_artifact_matches(
                parent_fd,
                output.name,
                staging_identity,
                run_manifest,
                records_byte_count=records_byte_count,
                records_sha256=records_hasher.hexdigest(),
                commit_receipt=None,
            ):
                raise
        # Cross-directory rename durability requires barriers for both the
        # source attempt directory and the destination output parent.  The
        # destination barrier is closed after commit.json is durable below.
        os.fsync(attempt.directory_fd)
        if not _published_artifact_matches(
            parent_fd,
            output.name,
            staging_identity,
            run_manifest,
            records_byte_count=records_byte_count,
            records_sha256=records_hasher.hexdigest(),
            commit_receipt=None,
        ):
            raise DiagnosticRunnerError("published artifact identity or bytes drifted")
        _assert_directory_path_identity(
            output.parent,
            parent_fd,
            parent_stat,
            "run output parent",
        )
        output_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        output_flags |= getattr(os, "O_NOFOLLOW", 0)
        output_fd = os.open(output.name, output_flags, dir_fd=parent_fd)
        opened_output = os.fstat(output_fd)
        if (opened_output.st_dev, opened_output.st_ino) != staging_identity:
            raise DiagnosticRunnerError(
                "published artifact changed before commit publication"
            )
        _write_canonical_file_noreplace_at(
            output_fd,
            "commit.json",
            commit_receipt,
        )
        os.fsync(output_fd)
        os.fsync(parent_fd)
        _assert_directory_path_identity(
            output.parent,
            parent_fd,
            parent_stat,
            "run output parent",
        )
        if not _prove_committed_terminal_collective(
            parent=output.parent,
            parent_fd=parent_fd,
            parent_stat=parent_stat,
            attempt=attempt,
            success_receipts=success_receipts,
            output_name=output.name,
            output_fd=output_fd,
            staging_identity=staging_identity,
            run_manifest=run_manifest,
            records_byte_count=records_byte_count,
            records_sha256=records_hasher.hexdigest(),
            commit_receipt=commit_receipt,
        ):
            raise DiagnosticRunnerError(
                "artifact and attempt did not close before lock retirement"
            )
        retire_before_terminal_proof()
        try:
            if not _prove_committed_terminal_collective(
                parent=output.parent,
                parent_fd=parent_fd,
                parent_stat=parent_stat,
                attempt=attempt,
                success_receipts=success_receipts,
                output_name=output.name,
                output_fd=output_fd,
                staging_identity=staging_identity,
                run_manifest=run_manifest,
                records_byte_count=records_byte_count,
                records_sha256=records_hasher.hexdigest(),
                commit_receipt=commit_receipt,
            ):
                raise DiagnosticPublicationStateAmbiguousError(
                    "committed artifact or attempt conflicted after lock retirement"
                )
        except _PublicationLockRetirementAmbiguousError:
            raise
        except BaseException as terminal_error:
            raise _PublicationLockRetirementAmbiguousError(
                "terminal COMMITTED authority is ambiguous after lock "
                f"retirement: {terminal_error}"
            ) from terminal_error
        return run_manifest, commit_receipt
    except _PublicationLockRetirementAmbiguousError:
        raise
    except BaseException as error:
        reason = str(error)
        pinned_commit_identity = None
        public_commit_identity = None
        commit_observation_error: BaseException | None = None
        if "staging_identity" in locals() and "commit_receipt" in locals():
            if output_fd >= 0:
                try:
                    pinned_commit_identity = _pinned_exact_artifact_commit_identity(
                        output_fd,
                        staging_identity,
                        commit_receipt,
                    )
                except BaseException as observation_error:
                    commit_observation_error = observation_error
            try:
                public_commit_identity = _published_exact_artifact_commit_identity(
                    parent_fd,
                    output.name,
                    staging_identity,
                    commit_receipt,
                )
            except BaseException as observation_error:
                if commit_observation_error is None:
                    commit_observation_error = observation_error
        commit_context_exists = (
            "staging_identity" in locals() and "commit_receipt" in locals()
        )
        commit_identity_observed = (
            pinned_commit_identity is not None or public_commit_identity is not None
        )
        if (
            commit_context_exists
            and not commit_identity_observed
            and commit_observation_error is not None
        ):
            raise DiagnosticPublicationStateAmbiguousError(
                "artifact commit presence and exact rollback are both unproven"
            ) from commit_observation_error
        if commit_context_exists:
            try:
                commit_is_durable = _retry_committed_artifact_durability(
                    parent=output.parent,
                    parent_fd=parent_fd,
                    parent_stat=parent_stat,
                    attempt=attempt,
                    success_receipts=success_receipts,
                    output_name=output.name,
                    staging_identity=staging_identity,
                    run_manifest=run_manifest,
                    records_byte_count=records_byte_count,
                    records_sha256=records_hasher.hexdigest(),
                    commit_receipt=commit_receipt,
                    retire_publication_lock=retire_before_terminal_proof,
                )
            except DiagnosticPublicationStateAmbiguousError:
                raise
            except BaseException:
                commit_is_durable = False
            if commit_is_durable:
                return run_manifest, commit_receipt

        if commit_identity_observed:
            try:
                if pinned_commit_identity is not None:
                    commit_was_revoked = _revoke_exact_artifact_commit_at(
                        output_fd,
                        staging_identity,
                        commit_receipt,
                    )
                else:
                    commit_was_revoked = _revoke_exact_artifact_commit(
                        parent_fd,
                        output.name,
                        staging_identity,
                        commit_receipt,
                    )
            except BaseException as rollback_error:
                raise DiagnosticPublicationStateAmbiguousError(
                    "artifact commit durability and exact rollback are both unproven"
                ) from rollback_error
            if not commit_was_revoked:
                raise DiagnosticPublicationStateAmbiguousError(
                    "artifact commit durability and exact rollback are both unproven"
                ) from error
        elif commit_context_exists:
            # A pair of transient absence observations is not proof that commit
            # authority never became public.  Re-observe after the durability
            # retry before permitting a terminal INVALID receipt.
            try:
                if output_fd >= 0:
                    pinned_commit_identity = _pinned_exact_artifact_commit_identity(
                        output_fd,
                        staging_identity,
                        commit_receipt,
                    )
                public_commit_identity = _published_exact_artifact_commit_identity(
                    parent_fd,
                    output.name,
                    staging_identity,
                    commit_receipt,
                )
            except BaseException as observation_error:
                raise DiagnosticPublicationStateAmbiguousError(
                    "artifact commit absence could not be re-observed"
                ) from observation_error
            if pinned_commit_identity is not None or public_commit_identity is not None:
                commit_identity_observed = True
        _prove_attempt_terminal_authority(
            parent=output.parent,
            parent_fd=parent_fd,
            parent_stat=parent_stat,
            attempt=attempt,
        )
        invalid_receipt = _attempt_receipt(
            attempt,
            phase="STARTED",
            status="INVALID",
            reason=reason,
        )
        try:
            if not _attempt_receipt_matches(
                attempt,
                "invalid.json",
                invalid_receipt,
            ):
                _write_attempt_receipt(
                    attempt,
                    "invalid.json",
                    phase="STARTED",
                    status="INVALID",
                    reason=reason,
                )
        except BaseException as terminal_error:
            raise DiagnosticPublicationStateAmbiguousError(
                "INVALID receipt durability is unproven"
            ) from terminal_error
        _prove_attempt_terminal_authority(
            parent=output.parent,
            parent_fd=parent_fd,
            parent_stat=parent_stat,
            attempt=attempt,
            required_receipts={"invalid.json": invalid_receipt},
        )
        if commit_context_exists:
            try:
                if output_fd >= 0:
                    pinned_commit_identity = _pinned_exact_artifact_commit_identity(
                        output_fd,
                        staging_identity,
                        commit_receipt,
                    )
                    if pinned_commit_identity is not None and (
                        not _revoke_exact_artifact_commit_at(
                            output_fd,
                            staging_identity,
                            commit_receipt,
                        )
                    ):
                        raise DiagnosticPublicationStateAmbiguousError(
                            "pinned artifact commit revocation is unproven"
                        )
                _revoke_public_exact_committed_artifact(
                    parent_fd,
                    output.name,
                    run_manifest,
                    records_byte_count=records_byte_count,
                    records_sha256=records_hasher.hexdigest(),
                    commit_receipt=commit_receipt,
                )
                try:
                    os.fsync(parent_fd)
                except BaseException:
                    # Member revocation is barriered by the artifact directory.
                    # A persistent parent barrier failure retains INVALID only
                    # while the lexical parent still names the pinned directory.
                    _prove_attempt_terminal_authority(
                        parent=output.parent,
                        parent_fd=parent_fd,
                        parent_stat=parent_stat,
                        attempt=attempt,
                        required_receipts={"invalid.json": invalid_receipt},
                    )
            except DiagnosticPublicationStateAmbiguousError:
                raise
            except BaseException as reconciliation_error:
                raise DiagnosticPublicationStateAmbiguousError(
                    "final artifact commit reconciliation failed"
                ) from reconciliation_error
        retire_before_terminal_proof()
        if commit_context_exists:
            try:
                _prove_invalid_terminal_collective(
                    parent=output.parent,
                    parent_fd=parent_fd,
                    parent_stat=parent_stat,
                    attempt=attempt,
                    invalid_receipt=invalid_receipt,
                    output_name=output.name,
                    output_fd=output_fd,
                    run_manifest=run_manifest,
                    records_byte_count=records_byte_count,
                    records_sha256=records_hasher.hexdigest(),
                    commit_receipt=commit_receipt,
                )
            except DiagnosticPublicationStateAmbiguousError:
                raise
            except BaseException as reconciliation_error:
                raise DiagnosticPublicationStateAmbiguousError(
                    "final artifact commit absence is unproven"
                ) from reconciliation_error
        else:
            _prove_attempt_terminal_authority(
                parent=output.parent,
                parent_fd=parent_fd,
                parent_stat=parent_stat,
                attempt=attempt,
                required_receipts={"invalid.json": invalid_receipt},
            )
        raise DiagnosticInvalidRunError(reason) from error
    finally:
        _close_descriptor_best_effort(output_fd)
        _close_descriptor_best_effort(staging_fd)
        _close_descriptor_best_effort(attempt.directory_fd)


def run_countdown_thompson_diagnostic(
    bundle_path: Path,
    output_path: Path | str,
    authorization_path: Path,
    authorization_digest: str,
    authorization_revision: str,
    *,
    repository_root: Path,
) -> dict[str, Any]:
    """Fail closed until creation and ownership share one atomic primitive."""

    raise DiagnosticNotRunError(_PUBLICATION_BACKEND_REFUSAL)


def _self_test() -> dict[str, Any]:
    method_manifest_digest = "1" * 64
    cell = DiagnosticCell(
        task_fingerprint=_MICRO_TASK.task_fingerprint,
        proposal_label="nondiagnostic_uniform",
        proposal_spec_digest=TrackAProposalSpec("uniform/v1").deterministic_digest,
        method_label="nondiagnostic_greedy",
        method_spec_digest=sha256_json(TrackAMethodSpec.greedy().to_dict()),
        method_manifest_digest=method_manifest_digest,
        budget_profile_id=_micro_budget().profile_id,
        budget_profile_spec_digest=sha256_json(_micro_budget().to_dict()),
        exploration_seed=0,
        task_manifest_digest="2" * 64,
    )
    record = _execute_cell(
        cell,
        task=_MICRO_TASK,
        proposal=TrackAProposalSpec("uniform/v1"),
        method=TrackAMethodSpec.greedy(),
        budget_profile=_micro_budget(),
        diagnostic_seal_digest="3" * 64,
        method_manifest_digest=method_manifest_digest,
        runtime_qualification_digest="4" * 64,
        runner_build_digest="5" * 64,
        search_build_digest="6" * 64,
    )
    return {
        "claim_boundary": "non-diagnostic fixture only; no sealed outcome was opened",
        "fixture_task_fingerprint": _MICRO_TASK.task_fingerprint,
        "record_digest": record["deterministic_digest"],
        "replay": record["replay"],
        "status": "PASS",
    }


class _CanonicalArgumentParser(argparse.ArgumentParser):
    """Emit machine-readable refusals without argparse usage prose."""

    def error(self, message: str) -> None:
        print(
            canonical_json(
                {
                    "claim_boundary": (
                        "argument refusal only; no diagnostic search outcome was "
                        "opened; no execution-evidence authority and no retry "
                        "authority are implied"
                    ),
                    "reason": message,
                    "status": "NOT_RUN",
                }
            )
        )
        raise SystemExit(2)


def _raise_publication_state_ambiguous(
    error: DiagnosticPublicationStateAmbiguousError,
) -> NoReturn:
    print(
        canonical_json(
            {
                "claim_boundary": (
                    "publication durability and exact rollback are unresolved; "
                    "no file is authorized as diagnostic evidence and no retry "
                    "authority is implied"
                ),
                "reason": str(error),
                "status": "PUBLICATION_STATE_AMBIGUOUS",
            }
        )
    )
    raise SystemExit(3) from error


def main(argv: Sequence[str] | None = None) -> None:
    parser = _CanonicalArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--plan", type=Path, metavar="SEALED_BUNDLE")
    modes.add_argument("--run", type=Path, metavar="SEALED_BUNDLE")
    modes.add_argument("--self-test", action="store_true")
    # Preserve the exact lexical spelling; v2r3 hashes and reviews these bytes.
    parser.add_argument("--output")
    parser.add_argument("--authorization-out", type=Path)
    parser.add_argument("--authorization-file", type=Path)
    parser.add_argument("--authorization-digest")
    parser.add_argument("--authorization-revision")
    parser.add_argument("--repository-root", type=Path)
    args = parser.parse_args(argv)

    if args.self_test:
        if any(
            value is not None
            for value in (
                args.output,
                args.authorization_out,
                args.authorization_file,
                args.authorization_digest,
                args.authorization_revision,
                args.repository_root,
            )
        ):
            parser.error("--self-test accepts no execution or authorization paths")
        result = _self_test()
    elif args.plan is not None:
        if args.repository_root is None:
            parser.error("--plan requires explicit --repository-root")
        if args.output is None or args.authorization_out is None:
            parser.error("--plan requires --output and --authorization-out")
        if any(
            value is not None
            for value in (
                args.authorization_file,
                args.authorization_digest,
                args.authorization_revision,
            )
        ):
            parser.error("--plan does not accept run authorization inputs")
        try:
            result = write_countdown_thompson_diagnostic_execution_plan(
                args.plan,
                args.output,
                args.authorization_out,
                repository_root=args.repository_root,
            )
        except DiagnosticPublicationStateAmbiguousError as error:
            _raise_publication_state_ambiguous(error)
        except (DiagnosticRunnerError, FileExistsError, OSError, ValueError) as error:
            print(
                canonical_json(
                    {
                        "claim_boundary": (
                            "planning did not complete; no diagnostic search outcome "
                            "was opened"
                        ),
                        "reason": str(error),
                        "status": "NOT_RUN",
                    }
                )
            )
            raise SystemExit(2) from error
    else:
        if args.repository_root is None:
            parser.error("--run requires explicit --repository-root")
        if (
            args.output is None
            or args.authorization_file is None
            or args.authorization_digest is None
            or args.authorization_revision is None
        ):
            parser.error(
                "--run requires --output, --authorization-file, and "
                "--authorization-digest, and --authorization-revision"
            )
        if args.authorization_out is not None:
            parser.error("--run does not accept --authorization-out")
        try:
            result = run_countdown_thompson_diagnostic(
                args.run,
                args.output,
                args.authorization_file,
                args.authorization_digest,
                args.authorization_revision,
                repository_root=args.repository_root,
            )
        except DiagnosticPublicationStateAmbiguousError as error:
            _raise_publication_state_ambiguous(error)
        except DiagnosticNotRunError as error:
            print(
                canonical_json(
                    {
                        "claim_boundary": "no diagnostic search outcome was opened",
                        "reason": str(error),
                        "status": "NOT_RUN",
                    }
                )
            )
            raise SystemExit(2) from error
        except DiagnosticInvalidRunError as error:
            print(
                canonical_json(
                    {
                        "claim_boundary": (
                            "authorized diagnostic execution started but did not "
                            "commit; durable attempt evidence was retained"
                        ),
                        "reason": str(error),
                        "status": "INVALID",
                    }
                )
            )
            raise SystemExit(3) from error
    print(canonical_json(result))


if __name__ == "__main__":
    main()
