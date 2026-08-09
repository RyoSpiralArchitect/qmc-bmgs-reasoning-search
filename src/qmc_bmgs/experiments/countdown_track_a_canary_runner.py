#!/usr/bin/env python3
"""Manifest-driven, fail-closed runner for the sealed Track A canary.

Planning performs every outcome-blind preflight and writes a separate,
canonical authorization candidate.  Running recomputes those checks from the
bundle *path*, requires the reviewed authorization bytes and digest, and only
then constructs the first canary task or proposal.  ``--self-test`` uses a
non-canary fixture and never reads the sealed task cohort.
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
import tempfile
import time
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from qmc_bmgs.benchmarks.countdown import CountdownTask
from qmc_bmgs.experiments import countdown_track_a_canary_analysis as analysis
from qmc_bmgs.experiments import countdown_track_a_canary_manifest as manifest
from qmc_bmgs.experiments.countdown_track_a_canary_manifest import (
    BUNDLE_ID,
    EXPECTED_CELL_COUNT,
    CanaryCell,
    qualify_track_a_canary_runtime,
    verify_track_a_canary_bundle,
)
from qmc_bmgs.substrate.budget import TRACK_A_WORK_AXES, TrackAWorkBudget
from qmc_bmgs.substrate.countdown_search import (
    TrackABudgetProfile,
    TrackAMethodSpec,
    replay_countdown_track_a_search_bytes,
    run_countdown_track_a_search,
)
from qmc_bmgs.substrate.proposals import TrackAProposalSpec
from qmc_bmgs.substrate.trace import (
    TraceValidationError,
    canonical_json,
    sha256_json,
    strict_json_loads,
)


RUN_MANIFEST_SCHEMA_VERSION = "qmc-bmgs-countdown-track-a-canary-run-manifest/v1"
RUN_RECORD_SCHEMA_VERSION = "qmc-bmgs-countdown-track-a-canary-run-record/v1"
AUTHORIZATION_SCHEMA_VERSION = (
    "qmc-bmgs-countdown-track-a-canary-execution-authorization/v1"
)
BUILD_ATTESTATION_SCHEMA_VERSION = (
    "qmc-bmgs-countdown-track-a-canary-build-attestation/v1"
)
ATTEMPT_MARKER_SCHEMA_VERSION = "qmc-bmgs-countdown-track-a-canary-attempt-marker/v1"
ARTIFACT_COMMIT_SCHEMA_VERSION = "qmc-bmgs-countdown-track-a-canary-artifact-commit/v1"
ARTIFACT_FILENAMES = ("commit.json", "manifest.json", "records.jsonl")
REQUIRED_ANCESTRY = (
    "0917d1d7e8e637610883c6ab5901a118a59ca264",
    "b7eb154d2f3af9112375835c70212b46a59bdab9",
    "2d4960e6f79a12f27ad8dc370b78e89b98958044",
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
    "src/qmc_bmgs/experiments/countdown_track_a_canary_runner.py",
    "src/qmc_bmgs/experiments/countdown_track_a_canary_analysis.py",
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
    "qmc_bmgs.experiments.countdown_track_a_canary_manifest": (_RUNNER_SOURCE_PATHS[1]),
    __name__: _RUNNER_SOURCE_PATHS[2],
    analysis.__name__: _RUNNER_SOURCE_PATHS[3],
}
_MICRO_TASK = CountdownTask((1, 2, 3, 4, 5, 6), target=720)
_TELEMETRY_ROLE = "descriptive_only_excluded_from_search_core_identity_and_gates"


class CanaryRunnerError(RuntimeError):
    """Raised before publication when runner authority or closure fails."""


class CanaryNotRunError(CanaryRunnerError):
    """A preflight/authorization refusal that opened no canary search outcome."""


class CanaryInvalidRunError(CanaryRunnerError):
    """An authorized attempt that reached STARTED but did not commit."""


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
        raise CanaryRunnerError(f"{label} must be lowercase SHA-256")
    return value


def _require_git_oid(value: object, label: str) -> str:
    """Require a full lowercase Git object ID for SHA-1 or SHA-256 repos."""

    if (
        type(value) is not str
        or len(value) not in {40, 64}
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise CanaryRunnerError(
            f"{label} must be a full lowercase SHA-1 or SHA-256 Git object ID"
        )
    return value


def _strict_canonical_object(path: Path) -> tuple[dict[str, Any], bytes]:
    candidate = Path(path)
    if sys.platform == "win32":
        if candidate.is_symlink() or not candidate.is_file():
            raise CanaryRunnerError(f"not a regular authorization file: {candidate}")
        raw = candidate.read_bytes()
    else:
        try:
            descriptor = os.open(candidate, os.O_RDONLY | os.O_NOFOLLOW)
        except OSError as error:
            raise CanaryRunnerError(
                f"not a regular authorization file: {candidate}"
            ) from error
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise CanaryRunnerError(
                    f"not a regular authorization file: {candidate}"
                )
            with os.fdopen(descriptor, "rb", closefd=False) as handle:
                raw = handle.read()
        finally:
            os.close(descriptor)
    try:
        parsed = strict_json_loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, TraceValidationError) as error:
        raise CanaryRunnerError("authorization is not strict UTF-8 JSON") from error
    if type(parsed) is not dict or raw != _canonical_bytes(parsed):
        raise CanaryRunnerError("authorization is not a canonical JSON object")
    return parsed, raw


def _read_regular_file_nofollow(path: Path, label: str) -> bytes:
    """Read one regular file without following its final path component."""

    candidate = Path(path)
    if sys.platform == "win32":
        if candidate.is_symlink() or not candidate.is_file():
            raise CanaryRunnerError(f"{label} is not a regular file: {candidate}")
        return candidate.read_bytes()
    try:
        descriptor = os.open(candidate, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as error:
        raise CanaryRunnerError(
            f"{label} is not a regular file: {candidate}"
        ) from error
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise CanaryRunnerError(f"{label} is not a regular file: {candidate}")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            return handle.read()
    finally:
        os.close(descriptor)


def _open_stable_directory(path: Path, label: str) -> tuple[int, os.stat_result]:
    """Open one canonical directory and bind its current filesystem identity."""

    if os.name != "posix":
        raise CanaryRunnerError(f"{label} requires POSIX descriptor semantics")
    candidate = Path(path)
    try:
        if candidate.resolve() != candidate:
            raise CanaryRunnerError(f"{label} must not traverse symlinks")
        before = os.stat(candidate, follow_symlinks=False)
        if not stat.S_ISDIR(before.st_mode):
            raise CanaryRunnerError(f"{label} must be a directory")
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(candidate, flags)
        opened = os.fstat(descriptor)
    except OSError as error:
        raise CanaryRunnerError(f"{label} must be a stable directory") from error
    if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
        os.close(descriptor)
        raise CanaryRunnerError(f"{label} changed while it was opened")
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
            raise CanaryRunnerError(f"{label} now traverses a symlink")
        observed = os.stat(path, follow_symlinks=False)
        opened = os.fstat(descriptor)
    except OSError as error:
        raise CanaryRunnerError(f"{label} path identity is unavailable") from error
    identity = (expected.st_dev, expected.st_ino)
    if (observed.st_dev, observed.st_ino) != identity or (
        opened.st_dev,
        opened.st_ino,
    ) != identity:
        raise CanaryRunnerError(f"{label} path identity changed")


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


def _write_canonical_file_noreplace_at(
    directory_fd: int,
    filename: str,
    payload: Mapping[str, Any],
) -> None:
    """Publish one canonical file relative to a pinned directory descriptor."""

    if Path(filename).name != filename or not filename:
        raise CanaryRunnerError("descriptor-relative filename is invalid")
    temporary_name = ""
    file_descriptor = -1
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
            raise CanaryRunnerError("could not allocate receipt staging file")
        with os.fdopen(file_descriptor, "wb") as handle:
            file_descriptor = -1
            handle.write(_canonical_bytes(payload))
            handle.flush()
            os.fsync(handle.fileno())
        os.link(
            temporary_name,
            filename,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
            follow_symlinks=False,
        )
        os.unlink(temporary_name, dir_fd=directory_fd)
        temporary_name = ""
        os.fsync(directory_fd)
    finally:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        if temporary_name:
            try:
                os.unlink(temporary_name, dir_fd=directory_fd)
            except FileNotFoundError:
                pass


def _read_regular_file_at(directory_fd: int, filename: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(filename, flags, dir_fd=directory_fd)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise CanaryRunnerError("attempt receipt is not a regular file")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            return handle.read()
    finally:
        os.close(descriptor)


def _unlink_exact_file_at(
    directory_fd: int,
    filename: str,
    expected: bytes,
) -> bool:
    try:
        if _read_regular_file_at(directory_fd, filename) != expected:
            return False
        os.unlink(filename, dir_fd=directory_fd)
        os.fsync(directory_fd)
        return True
    except (FileNotFoundError, OSError, CanaryRunnerError):
        return False


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
    try:
        output_fd = os.open(output_name, flags, dir_fd=parent_fd)
    except OSError:
        return False
    try:
        observed = os.fstat(output_fd)
        if (observed.st_dev, observed.st_ino) != staging_identity:
            return False
        expected_filenames = {"manifest.json", "records.jsonl"}
        if commit_receipt is not None:
            expected_filenames.add("commit.json")
        if set(os.listdir(output_fd)) != expected_filenames:
            return False
        if _read_regular_file_at(output_fd, "manifest.json") != _canonical_bytes(
            run_manifest
        ):
            return False
        records = _read_regular_file_at(output_fd, "records.jsonl")
        if len(records) != records_byte_count or _sha256_bytes(records) != (
            records_sha256
        ):
            return False
        return commit_receipt is None or _read_regular_file_at(
            output_fd,
            "commit.json",
        ) == _canonical_bytes(commit_receipt)
    except (OSError, CanaryRunnerError):
        return False
    finally:
        os.close(output_fd)


def _write_canonical_file_noreplace(
    destination: Path,
    payload: Mapping[str, Any],
) -> None:
    """Stage, fsync, and atomically publish one authority file."""

    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.tmp-",
        dir=parent,
    )
    temporary: Path | None = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(_canonical_bytes(payload))
            handle.flush()
            os.fsync(handle.fileno())
        manifest._rename_directory_noreplace(temporary, destination)
        temporary = None
        parent_fd = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


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
        raise CanaryRunnerError(f"git {' '.join(arguments)} failed: {message}")
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
        raise CanaryRunnerError(f"git {' '.join(arguments)} failed: {message}")
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
        raise CanaryRunnerError(
            f"required revision {ancestor} is not an ancestor of clean HEAD"
        )


def _require_commit_object(repository_root: Path, revision: str, label: str) -> None:
    if _git(repository_root, "cat-file", "-t", revision) != "commit":
        raise CanaryRunnerError(f"{label} must name an exact Git commit object")


def _require_regular_git_blob(
    repository_root: Path,
    revision: str,
    relative_path: str,
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
        raise CanaryRunnerError("authorization Git tree entry is not unique")
    metadata, observed_path = entries[0].split(b"\t", maxsplit=1)
    fields = metadata.split()
    if (
        observed_path != relative_path.encode("utf-8")
        or len(fields) != 3
        or fields[0] != b"100644"
        or fields[1] != b"blob"
    ):
        raise CanaryRunnerError(
            "authorization Git tree entry must be one non-executable regular blob"
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
        profile_id="track_a_runner_noncanary_microfixture/v1",
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
        raise CanaryRunnerError("non-canary search microfixture replay drifted")
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
            raise CanaryRunnerError(
                f"imported protected module is outside attested source: {module_name}"
            )


def _protected_source_receipts(root: Path, head: str) -> dict[str, dict[str, Any]]:
    receipts: dict[str, dict[str, Any]] = {}
    for relative in (*_SEARCH_SOURCE_PATHS, *_RUNNER_SOURCE_PATHS):
        source = _read_regular_file_nofollow(
            root / relative,
            "attested protected source",
        )
        head_blob = _git_bytes(root, "show", f"{head}:{relative}")
        if source != head_blob:
            raise CanaryRunnerError(
                f"protected source does not exact-match clean HEAD blob: {relative}"
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
        raise CanaryRunnerError(f"authorized {label} protected path set drifted")
    for relative in expected_paths:
        receipt = receipts[relative]
        if (
            type(receipt) is not dict
            or set(receipt) != {"byte_count", "sha256"}
            or type(receipt["byte_count"]) is not int
            or receipt["byte_count"] < 0
        ):
            raise CanaryRunnerError(
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
        raise CanaryRunnerError("authorized runner build attestation fields drifted")
    if attestation["schema_version"] != BUILD_ATTESTATION_SCHEMA_VERSION:
        raise CanaryRunnerError("authorized runner build attestation schema drifted")
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
        raise CanaryRunnerError("authorized runner required ancestry is invalid")
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
        raise CanaryRunnerError("authorized runner/search build digest mismatch")
    return attestation


def _recheck_source_closure(
    repository_root: Path,
    build: _BuildAttestation,
) -> None:
    """Recheck HEAD, cleanliness, import origins, and every protected blob."""

    root = Path(repository_root).resolve()
    head = _require_git_oid(_git(root, "rev-parse", "HEAD"), "git HEAD")
    if head != build.current_head:
        raise CanaryRunnerError("source HEAD changed after build attestation")
    if _git(root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise CanaryRunnerError("source checkout changed after build attestation")
    _validate_protected_import_origins(root)
    observed = _protected_source_receipts(root, head)
    expected = {
        **build.payload["search_source_files"],
        **build.payload["runner_source_files"],
    }
    if observed != expected:
        raise CanaryRunnerError("protected source receipts changed after attestation")


def _attest_clean_source_build(
    repository_root: Path,
    *,
    authorized_runner_revision: str | None,
) -> _BuildAttestation:
    root = Path(repository_root).resolve()
    observed_root = Path(_git(root, "rev-parse", "--show-toplevel")).resolve()
    if observed_root != root:
        raise CanaryRunnerError("repository root does not match git top level")
    if _git(root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise CanaryRunnerError("source checkout is not clean")
    head = _require_git_oid(_git(root, "rev-parse", "HEAD"), "git HEAD")
    approved = (
        head
        if authorized_runner_revision is None
        else _require_git_oid(
            authorized_runner_revision,
            "authorized runner revision",
        )
    )
    for revision in (*REQUIRED_ANCESTRY, approved):
        _require_ancestor(root, revision, head)

    relative_paths = (*_SEARCH_SOURCE_PATHS, *_RUNNER_SOURCE_PATHS)
    tracked = set(_git(root, "ls-files", "--", *relative_paths).splitlines())
    if tracked != set(relative_paths):
        raise CanaryRunnerError("protected runner/search source surface is untracked")
    _validate_protected_import_origins(root)
    receipts = _protected_source_receipts(root, head)
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


def _validate_schedule(bundle: object) -> tuple[CanaryCell, ...]:
    cells = bundle.cells  # type: ignore[attr-defined]
    if len(cells) != EXPECTED_CELL_COUNT:
        raise CanaryRunnerError("verified schedule cell count drifted")
    ids = [cell.cell_id for cell in cells]
    if len(set(ids)) != EXPECTED_CELL_COUNT:
        raise CanaryRunnerError("verified schedule has duplicate cell IDs")
    payloads = bundle.payloads  # type: ignore[attr-defined]
    matrix = payloads["preregistration.json"]["execution_matrix"]
    if matrix["cell_count"] != EXPECTED_CELL_COUNT or matrix[
        "schedule_digest"
    ] != sha256_json([cell.to_dict() for cell in cells]):
        raise CanaryRunnerError("verified schedule coverage digest drifted")
    return cells


def _validate_outcome_blind_budget_guards(payloads: Mapping[str, Any]) -> None:
    """Reject a profile whose non-primary guards can bind valid D6 work.

    These bounds depend only on Countdown-D6 widths and atomic charge
    semantics.  They deliberately run before any sealed task is constructed.
    """

    profiles = {
        row["spec"]["profile_id"]: row["spec"]
        for row in payloads["budgets.json"]["profiles"]
    }
    score = profiles.get("score256")
    verifier = profiles.get("verifier8")
    if type(score) is not dict or type(verifier) is not dict:
        raise CanaryRunnerError("required outcome-blind budget profiles are missing")
    if score.get("primary_axis") != "legal_action_scores":
        raise CanaryRunnerError("score256 primary axis drifted")
    if verifier.get("primary_axis") != "verifier_calls":
        raise CanaryRunnerError("verifier8 primary axis drifted")

    score_limits = score["budget"]
    legal_limit = score_limits["legal_action_scores"]
    max_actions = 60
    min_actions = 3
    edges_per_trajectory = 5
    max_accepted_selections = (legal_limit - 1) // min_actions
    score_minima = {
        # A rejected stochastic selection must be blocked only by the primary
        # axis even when its full atomic vector has width 60.
        "generated_perturbation_coordinates": legal_limit + max_actions,
        # A cache miss may materialize the next full proposal row before the
        # selection refusal; retain one demonstrable unit of guard headroom.
        "proposal_action_scores": legal_limit + max_actions + 1,
        "proposal_state_evaluations": max_accepted_selections + 2,
        "edge_selections": max_accepted_selections + 1,
        "transitions": max_accepted_selections + 1,
        "verifier_calls": max_accepted_selections // edges_per_trajectory + 1,
    }
    for axis, minimum in score_minima.items():
        if type(score_limits.get(axis)) is not int or score_limits[axis] < minimum:
            raise CanaryRunnerError(
                f"score256 {axis} guard is below outcome-blind minimum {minimum}"
            )

    verifier_limits = verifier["budget"]
    verifier_count = verifier_limits["verifier_calls"]
    selection_bound = verifier_count * edges_per_trajectory
    score_bound = verifier_count * 140
    verifier_minima = {
        "proposal_state_evaluations": selection_bound + 1,
        "proposal_action_scores": score_bound + 1,
        "legal_action_scores": score_bound + 1,
        "generated_perturbation_coordinates": score_bound + 1,
        "edge_selections": selection_bound + 1,
        "transitions": selection_bound + 1,
    }
    for axis, minimum in verifier_minima.items():
        if (
            type(verifier_limits.get(axis)) is not int
            or verifier_limits[axis] < minimum
        ):
            raise CanaryRunnerError(
                f"verifier8 {axis} guard is below outcome-blind minimum {minimum}"
            )


@dataclass(frozen=True)
class _Preflight:
    bundle: object
    cells: tuple[CanaryCell, ...]
    qualification: dict[str, Any]
    runtime_qualification_digest: str
    build: _BuildAttestation
    output_path: Path


def _fresh_preflight(
    bundle_path: Path,
    output_path: Path,
    repository_root: Path,
    *,
    authorized_runner_revision: str | None,
) -> _Preflight:
    output = Path(output_path).resolve()
    repository = Path(repository_root).resolve()
    if output == repository or output.is_relative_to(repository):
        raise CanaryRunnerError("run output must lie outside the source repository")
    if output.exists() or output.is_symlink():
        raise CanaryRunnerError(f"output destination already exists: {output}")
    qualification = qualify_track_a_canary_runtime()
    if set(qualification) != {
        "bundle_id",
        "execution_authorized",
        "runtime_bindings_digest",
        "status",
    }:
        raise CanaryRunnerError("fresh runtime qualification fields drifted")
    frozen_runtime_digest = sha256_json(
        manifest.frozen_track_a_canary_runtime_bindings()
    )
    if (
        qualification["bundle_id"] != BUNDLE_ID
        or qualification["status"] != "RUNTIME_QUALIFIED"
        or qualification["execution_authorized"] is not False
        or qualification["runtime_bindings_digest"] != frozen_runtime_digest
    ):
        raise CanaryRunnerError("fresh runtime qualification does not match bundle")
    build = _attest_clean_source_build(
        repository,
        authorized_runner_revision=authorized_runner_revision,
    )
    verified = verify_track_a_canary_bundle(
        Path(bundle_path),
        repository_root=repository,
    )
    cells = _validate_schedule(verified)
    payloads = verified.payloads
    _validate_outcome_blind_budget_guards(payloads)
    expected_runtime_digest = sha256_json(payloads["methods.json"]["runtime_bindings"])
    if qualification["runtime_bindings_digest"] != expected_runtime_digest:
        raise CanaryRunnerError("fresh runtime qualification does not match bundle")
    task_ids = {row["task_fingerprint"] for row in payloads["tasks.json"]["tasks"]}
    if _MICRO_TASK.task_fingerprint in task_ids:
        raise CanaryRunnerError("numeric/search microfixture overlaps canary cohort")
    # The attestation ran its numeric/search microfixtures before bundle
    # verification.  Close the race by checking the same HEAD, clean worktree,
    # import origins, descriptor-read bytes, and HEAD blobs again afterwards.
    _recheck_source_closure(repository, build)
    return _Preflight(
        bundle=verified,
        cells=cells,
        qualification=qualification,
        runtime_qualification_digest=sha256_json(qualification),
        build=build,
        output_path=output,
    )


def _authorization_payload(preflight: _Preflight) -> dict[str, Any]:
    payloads = preflight.bundle.payloads  # type: ignore[attr-defined]
    core = {
        "artifact_id": preflight.output_path.name,
        "authorization_scope": "one_exact_complete_936_cell_canary_run",
        "bundle_id": BUNDLE_ID,
        "canary_seal_digest": preflight.bundle.seal_digest,  # type: ignore[attr-defined]
        "cell_count": EXPECTED_CELL_COUNT,
        "claim_boundary": (
            "execution authority only; canary comparisons remain descriptive"
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
        "schema_version": AUTHORIZATION_SCHEMA_VERSION,
    }
    return _with_digest(core)


def _authorization_repository_location(
    authorization_path: Path,
    repository_root: Path,
) -> tuple[Path, str]:
    root = Path(repository_root).resolve()
    candidate = Path(authorization_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    if candidate.is_symlink():
        raise CanaryRunnerError("authorization path must not traverse symlinks")
    resolved = candidate.resolve()
    if resolved == root or not resolved.is_relative_to(root):
        raise CanaryRunnerError(
            "authorization must be a repository-relative regular file"
        )
    relative = resolved.relative_to(root).as_posix()
    if relative == "." or ".." in Path(relative).parts:
        raise CanaryRunnerError("authorization repository path is invalid")
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
        raise CanaryRunnerError("authorization path resolution drifted")
    tracked = _git(root, "ls-files", "--error-unmatch", "--", relative)
    if tracked.splitlines() != [relative]:
        raise CanaryRunnerError("authorization is not one exact tracked file")
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
        raise CanaryRunnerError(
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
        raise CanaryRunnerError(
            "authorization bytes do not exact-match reviewed revision and HEAD blob"
        )
    return reviewed


def write_track_a_canary_execution_plan(
    bundle_path: Path,
    output_path: Path,
    authorization_path: Path,
    *,
    repository_root: Path,
) -> dict[str, Any]:
    """Write an exclusive pre-outcome authorization candidate."""

    repository = Path(repository_root).resolve()
    authorization, _ = _authorization_repository_location(
        Path(authorization_path),
        repository,
    )
    output = Path(output_path).resolve()
    if authorization == output or authorization.is_relative_to(output):
        raise CanaryRunnerError("authorization file must lie outside output")
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
        "claim_boundary": "planning only; no canary outcome was opened",
        "noncanary_fixture_trace_byte_count": preflight.build.payload[
            "search_microfixture"
        ]["trace_byte_count"],
        "naive_936_trace_bytes_proxy": (
            preflight.build.payload["search_microfixture"]["trace_byte_count"]
            * EXPECTED_CELL_COUNT
        ),
        "status": "PREOUTCOME_AUTHORIZATION_CANDIDATE_WRITTEN",
    }


def _load_and_match_authorization(
    authorization_path: Path,
    supplied_digest: str,
    authorization_revision: str,
    *,
    bundle_path: Path,
    output_path: Path,
    repository_root: Path,
) -> tuple[_Preflight, dict[str, Any]]:
    supplied = _require_sha256(supplied_digest, "authorization digest")
    repository = Path(repository_root).resolve()
    authorization_file, _ = _authorization_repository_location(
        Path(authorization_path),
        repository,
    )
    resolved_authorization = authorization_file.resolve()
    output = Path(output_path).resolve()
    if resolved_authorization == output or resolved_authorization.is_relative_to(
        output
    ):
        raise CanaryRunnerError("authorization file must lie outside output")
    observed, observed_raw = _strict_canonical_object(authorization_file)
    if set(observed) == set() or observed.get("schema_version") != (
        AUTHORIZATION_SCHEMA_VERSION
    ):
        raise CanaryRunnerError("authorization schema is unsupported")
    observed_digest = _require_sha256(
        observed.get("deterministic_digest"),
        "authorization deterministic digest",
    )
    core = {
        key: value for key, value in observed.items() if key != "deterministic_digest"
    }
    if sha256_json(core) != observed_digest or observed_digest != supplied:
        raise CanaryRunnerError("authorization digest does not exact-match")
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
        raise CanaryRunnerError(
            "authorization bytes do not exact-match fresh preflight"
        )
    _, final_raw = _strict_canonical_object(authorization_file)
    if final_raw != observed_raw:
        raise CanaryRunnerError("authorization changed during fresh preflight")
    return preflight, observed


@dataclass(frozen=True)
class _ResolvedComponents:
    tasks: dict[str, CountdownTask]
    proposals: dict[str, TrackAProposalSpec]
    methods: dict[str, TrackAMethodSpec]
    budgets: dict[str, TrackABudgetProfile]


def _resolve_components(payloads: Mapping[str, Any]) -> _ResolvedComponents:
    tasks: dict[str, CountdownTask] = {}
    for row in payloads["tasks.json"]["tasks"]:
        task = CountdownTask(tuple(row["inputs"]), row["target"])
        if task.to_dict() != row:
            raise CanaryRunnerError("sealed task failed typed reconstruction")
        tasks[task.task_fingerprint] = task

    proposals: dict[str, TrackAProposalSpec] = {}
    for row in payloads["proposals.json"]["policies"]:
        spec = TrackAProposalSpec(row["spec"]["policy_id"])
        if (
            spec.to_dict() != row["spec"]
            or spec.deterministic_digest != row["spec_digest"]
        ):
            raise CanaryRunnerError("sealed proposal failed typed reconstruction")
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
            schema_version=source["schema_version"],
        )
        if spec.to_dict() != source or sha256_json(source) != row["spec_digest"]:
            raise CanaryRunnerError("sealed method failed typed reconstruction")
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
            raise CanaryRunnerError("sealed budget failed typed reconstruction")
        budgets[profile.profile_id] = profile
    return _ResolvedComponents(tasks, proposals, methods, budgets)


def _execute_cell(
    cell: CanaryCell,
    *,
    task: CountdownTask,
    proposal: TrackAProposalSpec,
    method: TrackAMethodSpec,
    budget_profile: TrackABudgetProfile,
    canary_seal_digest: str,
    method_manifest_digest: str,
    runtime_qualification_digest: str,
    runner_build_digest: str,
    search_build_digest: str,
) -> dict[str, Any]:
    """Execute and independently replay one already-authorized typed cell."""

    if task.task_fingerprint != cell.task_fingerprint:
        raise CanaryRunnerError("cell task fingerprint does not match typed task")
    if proposal.deterministic_digest != cell.proposal_spec_digest:
        raise CanaryRunnerError("cell proposal digest does not match typed proposal")
    if sha256_json(method.to_dict()) != cell.method_spec_digest:
        raise CanaryRunnerError("cell method digest does not match typed method")
    if sha256_json(budget_profile.to_dict()) != cell.budget_profile_spec_digest:
        raise CanaryRunnerError("cell budget digest does not match typed budget")
    if method_manifest_digest != cell.method_manifest_digest:
        raise CanaryRunnerError("cell method-manifest digest drifted")

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
        raise CanaryRunnerError("monotonic wall-time telemetry moved backwards")
    if replayed != trace_bytes:
        raise CanaryRunnerError("two-stage replay was not byte-identical")
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
        "canary_seal_digest": canary_seal_digest,
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
    except (FileNotFoundError, OSError, CanaryRunnerError):
        return False
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
        os.stat(temporary_name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        pass
    except OSError:
        return False
    else:
        return False
    try:
        destination = os.stat(
            attempt_name,
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
        pinned = os.fstat(pinned_fd)
    except OSError:
        return False
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
        if set(os.listdir(pinned_fd)) != {"pre_outcome.json"}:
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
    except (OSError, CanaryRunnerError):
        return False


def _terminalize_published_attempt_not_run(
    attempt: _Attempt,
    parent_fd: int,
    reason: str,
) -> None:
    """Best-effort terminal receipt for a proven published pre-outcome inode."""

    try:
        _write_attempt_receipt(
            attempt,
            "not_run.json",
            phase="PRE_OUTCOME",
            status="NOT_RUN",
            reason=reason,
        )
        os.fsync(parent_fd)
    except BaseException:
        # The caller still fails closed.  Never touch an unproven path merely to
        # manufacture a terminal receipt after publication validation failed.
        pass


def _cleanup_private_attempt_scratch(
    parent_fd: int,
    temporary_name: str,
    temporary_fd: int,
    pinned_identity: tuple[int, int],
    pre_outcome_receipt: Mapping[str, Any],
) -> None:
    """Best-effort cleanup only when the source entry is still our exact inode."""

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
        names = set(os.listdir(temporary_fd))
        if names == {"pre_outcome.json"}:
            if not _unlink_exact_file_at(
                temporary_fd,
                "pre_outcome.json",
                _canonical_bytes(pre_outcome_receipt),
            ):
                return
        elif names:
            return
        observed = os.stat(
            temporary_name,
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
        pinned = os.fstat(temporary_fd)
        if (observed.st_dev, observed.st_ino) != pinned_identity or (
            pinned.st_dev,
            pinned.st_ino,
        ) != pinned_identity:
            return
        os.rmdir(temporary_name, dir_fd=parent_fd)
        os.fsync(parent_fd)
    except (FileNotFoundError, OSError, CanaryRunnerError):
        # An unproven path is never removed.  A leftover private scratch is
        # preferable to touching a raced or foreign directory entry.
        return


def _transition_attempt_to_started(attempt: _Attempt) -> dict[str, Any]:
    """Publish STARTED and classify an ambiguous publication by exact bytes."""

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
        if _attempt_receipt_matches(attempt, "started.json", expected):
            try:
                _write_attempt_receipt(
                    attempt,
                    "invalid.json",
                    phase="STARTED",
                    status="INVALID",
                    reason=str(error),
                )
            except BaseException:
                pass
            raise CanaryInvalidRunError(str(error)) from error
        try:
            _write_attempt_receipt(
                attempt,
                "not_run.json",
                phase="PRE_OUTCOME",
                status="NOT_RUN",
                reason=str(error),
            )
        except BaseException:
            pass
        raise CanaryNotRunError(str(error)) from error
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
        raise CanaryNotRunError(f"run artifact destination exists: {output}")
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
        "canary_seal_digest": preflight.bundle.seal_digest,  # type: ignore[attr-defined]
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
        raise CanaryNotRunError("could not allocate attempt reservation scratch")
    temporary = parent / temporary_name
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    temporary_fd = os.open(temporary_name, flags, dir_fd=parent_fd)
    attempt = _Attempt(
        directory=temporary,
        directory_fd=temporary_fd,
        directory_name=temporary_name,
        staging_path=temporary / "staging",
        receipt_base={
            **receipt_base,
            "staging_path": str(staging_path),
        },
    )
    temporary_stat = os.fstat(temporary_fd)
    temporary_identity = (temporary_stat.st_dev, temporary_stat.st_ino)
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
                    _terminalize_published_attempt_not_run(
                        attempt,
                        parent_fd,
                        str(error),
                    )
                    raise CanaryNotRunError(
                        "published attempt reservation failed exact validation"
                    ) from error
                if isinstance(error, FileExistsError):
                    raise CanaryNotRunError(
                        "authorization already has a durable attempt marker"
                    ) from error
                raise
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
                _terminalize_published_attempt_not_run(
                    attempt,
                    parent_fd,
                    "attempt reservation publication identity or bytes drifted",
                )
            raise CanaryNotRunError(
                "attempt reservation publication identity or bytes drifted"
            )
        try:
            os.fsync(parent_fd)
        except BaseException as error:
            durable_attempt = _Attempt(
                directory=attempt_directory,
                directory_fd=temporary_fd,
                directory_name=attempt_name,
                staging_path=staging_path,
                receipt_base=receipt_base,
            )
            try:
                _write_attempt_receipt(
                    durable_attempt,
                    "not_run.json",
                    phase="PRE_OUTCOME",
                    status="NOT_RUN",
                    reason=str(error),
                )
            except BaseException:
                # The no-replace marker is already the durable once-only
                # authority even if appending its explanatory receipt fails.
                pass
            raise CanaryNotRunError(
                "attempt reservation parent-directory sync failed"
            ) from error
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
            os.close(temporary_fd)
    return _Attempt(
        directory=attempt_directory,
        directory_fd=temporary_fd,
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
    """Serialize attempts targeting one output while preserving auth markers."""

    output = preflight.output_path
    parent = output.parent
    parent.mkdir(parents=True, exist_ok=True)
    try:
        parent_fd, parent_stat = _open_stable_directory(
            parent,
            "run output parent",
        )
    except CanaryRunnerError as error:
        raise CanaryNotRunError(str(error)) from error
    lock_name = f".{output.name}.publish-lock"
    try:
        try:
            os.mkdir(lock_name, 0o700, dir_fd=parent_fd)
        except FileExistsError as error:
            raise CanaryNotRunError(
                f"run artifact publication is locked: {parent / lock_name}"
            ) from error
        try:
            _assert_directory_path_identity(
                parent,
                parent_fd,
                parent_stat,
                "run output parent",
            )
            try:
                manifest_payload, commit_payload = _publish_run_artifact_locked(
                    preflight,
                    authorization,
                    reviewed_authorization_revision=reviewed_authorization_revision,
                    repository_root=repository_root,
                    parent_fd=parent_fd,
                    parent_stat=parent_stat,
                )
                if _terminal_result:
                    return {
                        "artifact_commit_digest": commit_payload[
                            "deterministic_digest"
                        ],
                        "artifact_id": manifest_payload["artifact_id"],
                        "artifact_path": str(preflight.output_path),
                        "run_manifest_digest": manifest_payload["deterministic_digest"],
                        "status": "COMMITTED",
                    }
                return manifest_payload
            except (CanaryNotRunError, CanaryInvalidRunError):
                raise
            except Exception as error:
                raise CanaryNotRunError(str(error)) from error
        finally:
            try:
                os.rmdir(lock_name, dir_fd=parent_fd)
            except OSError:
                # The durable attempt directory, not this transient mutex, is
                # the execution authority.  Never rewrite outcome state because
                # lock cleanup failed after an otherwise final transition.
                pass
    finally:
        os.close(parent_fd)


def _publish_run_artifact_locked(
    preflight: _Preflight,
    authorization: Mapping[str, Any],
    *,
    reviewed_authorization_revision: str,
    repository_root: Path,
    parent_fd: int,
    parent_stat: os.stat_result,
) -> tuple[dict[str, Any], dict[str, Any]]:
    output = preflight.output_path
    if (
        authorization.get("output_path") != str(output)
        or authorization.get("artifact_id") != output.name
    ):
        raise CanaryRunnerError("authorization output identity drifted")
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
    staging_fd = -1
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
        try:
            _write_attempt_receipt(
                attempt,
                "not_run.json",
                phase="PRE_OUTCOME",
                status="NOT_RUN",
                reason=str(error),
            )
        except BaseException:
            pass
        if staging_fd >= 0:
            os.close(staging_fd)
        os.close(attempt.directory_fd)
        raise CanaryNotRunError(str(error)) from error

    try:
        started_receipt = _transition_attempt_to_started(attempt)
    except BaseException:
        os.close(staging_fd)
        os.close(attempt.directory_fd)
        raise

    try:
        payloads = preflight.bundle.payloads  # type: ignore[attr-defined]
        components = _resolve_components(payloads)
        method_manifest_digest = payloads["methods.json"]["deterministic_digest"]
        build = preflight.build.payload
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
            for cell in preflight.cells:
                record = _execute_cell(
                    cell,
                    task=components.tasks[cell.task_fingerprint],
                    proposal=components.proposals[cell.proposal_label],
                    method=components.methods[cell.method_label],
                    budget_profile=components.budgets[cell.budget_profile_id],
                    canary_seal_digest=preflight.bundle.seal_digest,  # type: ignore[attr-defined]
                    method_manifest_digest=method_manifest_digest,
                    runtime_qualification_digest=(
                        preflight.runtime_qualification_digest
                    ),
                    runner_build_digest=build["runner_build_digest"],
                    search_build_digest=build["search_build_digest"],
                )
                if record.get("cell_id") != cell.cell_id:
                    raise CanaryRunnerError("executed record cell identity drifted")
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
                    raise CanaryRunnerError("executed record telemetry drifted")
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
        expected_ids = [cell.cell_id for cell in preflight.cells]
        if cell_ids != expected_ids or len(set(cell_ids)) != EXPECTED_CELL_COUNT:
            raise CanaryRunnerError(
                "executed record schedule is incomplete or duplicated"
            )
        if len(set(record_digests)) != EXPECTED_CELL_COUNT:
            raise CanaryRunnerError("executed record digests are not unique")
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
                "canary_seal_digest": preflight.bundle.seal_digest,  # type: ignore[attr-defined]
                "cell_count": EXPECTED_CELL_COUNT,
                "claim_boundary": (
                    "descriptive canary artifact; byte replay applies only to the "
                    "embedded search core, telemetry is volatile, and no inferential "
                    "or promotion authority is granted"
                ),
                "execution_authorization_digest": authorization["deterministic_digest"],
                "execution_authorization": deepcopy(dict(authorization)),
                "execution_head_revision": preflight.build.current_head,
                "method_manifest_digest": method_manifest_digest,
                "record_digests": record_digests,
                "records_jsonl_byte_count": records_byte_count,
                "records_jsonl_sha256": records_hasher.hexdigest(),
                "reviewed_authorization_revision": reviewed,
                "runner_build_attestation": build,
                "runtime_qualification": preflight.qualification,
                "schedule_cell_ids": cell_ids,
                "schema_version": RUN_MANIFEST_SCHEMA_VERSION,
                "telemetry": {
                    "replay_wall_time_ns_total": replay_wall_time_ns_total,
                    "role": _TELEMETRY_ROLE,
                    "search_wall_time_ns_total": search_wall_time_ns_total,
                },
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
        _write_attempt_receipt(
            attempt,
            "ready_to_commit.json",
            phase="STARTED",
            status="READY_TO_COMMIT",
            run_manifest_digest=run_manifest["deterministic_digest"],
        )
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
                parent_fd,
                f"{attempt.directory_name}/staging",
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
        if not _published_artifact_matches(
            parent_fd,
            output.name,
            staging_identity,
            run_manifest,
            records_byte_count=records_byte_count,
            records_sha256=records_hasher.hexdigest(),
            commit_receipt=None,
        ):
            raise CanaryRunnerError("published artifact identity or bytes drifted")
        _assert_directory_path_identity(
            output.parent,
            parent_fd,
            parent_stat,
            "run output parent",
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
        output_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        output_flags |= getattr(os, "O_NOFOLLOW", 0)
        output_fd = os.open(output.name, output_flags, dir_fd=parent_fd)
        try:
            _write_canonical_file_noreplace_at(
                output_fd,
                "commit.json",
                commit_receipt,
            )
            os.fsync(output_fd)
        finally:
            os.close(output_fd)
        os.fsync(parent_fd)
        _assert_directory_path_identity(
            output.parent,
            parent_fd,
            parent_stat,
            "run output parent",
        )
        if not _published_artifact_matches(
            parent_fd,
            output.name,
            staging_identity,
            run_manifest,
            records_byte_count=records_byte_count,
            records_sha256=records_hasher.hexdigest(),
            commit_receipt=commit_receipt,
        ):
            raise CanaryRunnerError("published artifact changed before commit return")
        return run_manifest, commit_receipt
    except BaseException as error:
        if (
            "run_manifest" in locals()
            and "staging_identity" in locals()
            and "commit_receipt" in locals()
            and _published_artifact_matches(
                parent_fd,
                output.name,
                staging_identity,
                run_manifest,
                records_byte_count=records_byte_count,
                records_sha256=records_hasher.hexdigest(),
                commit_receipt=commit_receipt,
            )
        ):
            try:
                _assert_directory_path_identity(
                    output.parent,
                    parent_fd,
                    parent_stat,
                    "run output parent",
                )
            except CanaryRunnerError:
                revoked = False
                output_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                output_flags |= getattr(os, "O_NOFOLLOW", 0)
                try:
                    rollback_fd = os.open(
                        output.name,
                        output_flags,
                        dir_fd=parent_fd,
                    )
                except OSError:
                    pass
                else:
                    try:
                        revoked = _unlink_exact_file_at(
                            rollback_fd,
                            "commit.json",
                            _canonical_bytes(commit_receipt),
                        )
                    finally:
                        os.close(rollback_fd)
                if not revoked:
                    # Once an exact artifact-local commit receipt cannot be
                    # revoked, it remains the only non-contradictory authority.
                    return run_manifest, commit_receipt
            else:
                return run_manifest, commit_receipt
        try:
            _write_attempt_receipt(
                attempt,
                "invalid.json",
                phase="STARTED",
                status="INVALID",
                reason=str(error),
            )
        except BaseException:
            pass
        raise CanaryInvalidRunError(str(error)) from error
    finally:
        if staging_fd >= 0:
            os.close(staging_fd)
        os.close(attempt.directory_fd)


def run_track_a_canary(
    bundle_path: Path,
    output_path: Path,
    authorization_path: Path,
    authorization_digest: str,
    authorization_revision: str,
    *,
    repository_root: Path,
) -> dict[str, Any]:
    """Execute exactly the sealed matrix after a fresh path-based preflight."""

    try:
        preflight, authorization = _load_and_match_authorization(
            Path(authorization_path),
            authorization_digest,
            authorization_revision,
            bundle_path=Path(bundle_path),
            output_path=Path(output_path),
            repository_root=Path(repository_root),
        )
    except CanaryInvalidRunError:
        raise
    except Exception as error:
        raise CanaryNotRunError(str(error)) from error
    return _publish_run_artifact(
        preflight,
        authorization,
        reviewed_authorization_revision=authorization_revision,
        repository_root=Path(repository_root),
        _terminal_result=True,
    )


def _self_test() -> dict[str, Any]:
    method_manifest_digest = "1" * 64
    cell = CanaryCell(
        task_fingerprint=_MICRO_TASK.task_fingerprint,
        proposal_label="noncanary_uniform",
        proposal_spec_digest=TrackAProposalSpec("uniform/v1").deterministic_digest,
        method_label="noncanary_greedy",
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
        canary_seal_digest="3" * 64,
        method_manifest_digest=method_manifest_digest,
        runtime_qualification_digest="4" * 64,
        runner_build_digest="5" * 64,
        search_build_digest="6" * 64,
    )
    return {
        "claim_boundary": "non-canary fixture only; no sealed outcome was opened",
        "fixture_task_fingerprint": _MICRO_TASK.task_fingerprint,
        "record_digest": record["deterministic_digest"],
        "replay": record["replay"],
        "status": "PASS",
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--plan", type=Path, metavar="SEALED_BUNDLE")
    modes.add_argument("--run", type=Path, metavar="SEALED_BUNDLE")
    modes.add_argument("--self-test", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--authorization-out", type=Path)
    parser.add_argument("--authorization-file", type=Path)
    parser.add_argument("--authorization-digest")
    parser.add_argument("--authorization-revision")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
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
            )
        ):
            parser.error("--self-test accepts no execution or authorization paths")
        result = _self_test()
    elif args.plan is not None:
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
            result = write_track_a_canary_execution_plan(
                args.plan,
                args.output,
                args.authorization_out,
                repository_root=args.repository_root,
            )
        except (CanaryRunnerError, FileExistsError, OSError, ValueError) as error:
            print(
                canonical_json(
                    {
                        "claim_boundary": (
                            "planning did not complete; no canary search outcome "
                            "was opened"
                        ),
                        "reason": str(error),
                        "status": "NOT_RUN",
                    }
                )
            )
            raise SystemExit(2) from error
    else:
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
            result = run_track_a_canary(
                args.run,
                args.output,
                args.authorization_file,
                args.authorization_digest,
                args.authorization_revision,
                repository_root=args.repository_root,
            )
        except CanaryNotRunError as error:
            print(
                canonical_json(
                    {
                        "claim_boundary": "no canary search outcome was opened",
                        "reason": str(error),
                        "status": "NOT_RUN",
                    }
                )
            )
            raise SystemExit(2) from error
        except CanaryInvalidRunError as error:
            print(
                canonical_json(
                    {
                        "claim_boundary": (
                            "authorized canary execution started but did not "
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
