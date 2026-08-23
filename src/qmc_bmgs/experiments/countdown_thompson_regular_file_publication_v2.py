"""Synthetic-only regular-file publication substrate for the Thompson diagnostic.

This module exercises publication mechanics only.  It cannot open the sealed
diagnostic bundle, execute a diagnostic cell, or authorize a production run.
The production diagnostic runner remains fail-closed until a later integration
binds a separately reviewed authorization and analyzer to this layout.

The v2 ownership event is a successful descriptor-relative
``open(O_CREAT | O_EXCL)`` of a regular file at its final name.  No authority
file is renamed, unlinked, replaced, reclaimed, or adopted from matching bytes.
"""

from __future__ import annotations

import argparse
import errno
import hashlib
import os
import secrets
import stat
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from qmc_bmgs.substrate.trace import (
    TraceValidationError,
    canonical_json,
    sha256_json,
    strict_json_loads,
)


PUBLICATION_BACKEND = "posix_regular_files/v2r2"
ARTIFACT_LAYOUT = "flat_commit_root/v2r2"
FIXTURE_KIND = "nondiagnostic_synthetic_publication_v2r2"
ATTEMPT_SCHEMA_VERSION = "qmc-bmgs-countdown-thompson-synthetic-attempt/v2r2"
PHASE_SCHEMA_VERSION = "qmc-bmgs-countdown-thompson-synthetic-phase/v2r2"
RECORD_SCHEMA_VERSION = "qmc-bmgs-countdown-thompson-synthetic-record/v2r2"
MANIFEST_SCHEMA_VERSION = "qmc-bmgs-countdown-thompson-synthetic-manifest/v2r2"
COMMIT_SCHEMA_VERSION = "qmc-bmgs-countdown-thompson-synthetic-commit/v2r2"

_RESERVED_OUTPUT_PREFIX = ".qmc-bmgs-"
_INTERNAL_NAME_PREFIX = ".qmc-bmgs-v2r2-"
_LEGACY_INTERNAL_NAME_PREFIX = ".qmc-bmgs-v2-"

_MAX_CONTROL_BYTES = 1 << 20
_MAX_RECORDS_BYTES = 16 << 20
_MAX_SYNTHETIC_RECORDS = 10_000
_READ_CHUNK_BYTES = 1 << 16
_OWNER_NONCE_BYTES = 32


class RegularFilePublicationV2Error(RuntimeError):
    """Base error for the synthetic v2 publication substrate."""


class RegularFilePublicationV2NotRunError(RegularFilePublicationV2Error):
    """The outcome boundary was not crossed."""


class RegularFilePublicationV2InvalidError(RegularFilePublicationV2Error):
    """The synthetic outcome boundary was crossed without a commit."""


class RegularFilePublicationV2AmbiguousError(RegularFilePublicationV2Error):
    """An exact durable terminal state could not be proved."""


class _NameConflictError(RegularFilePublicationV2Error):
    """An exclusive final name was already occupied; the entry is foreign."""


class _CreateBeforeOpenError(RegularFilePublicationV2Error):
    """Exclusive creation failed before returning an ownership descriptor."""


class _HookBeforeOpenError(_CreateBeforeOpenError):
    """A private hook failed before the exclusive-open syscall was entered."""


class _CreateAfterOpenError(RegularFilePublicationV2Error):
    """Exclusive creation returned a descriptor but exact closure failed."""

    def __init__(
        self,
        message: str,
        *,
        owned: _OwnedRegularFile,
        cause: BaseException,
    ) -> None:
        super().__init__(message)
        self.owned = owned
        self.__cause__ = cause


class _FixtureOutcomeError(RegularFilePublicationV2Error):
    """A caller-controlled synthetic outcome callback or payload failed."""


class _EventHookError(RegularFilePublicationV2Error):
    """A private test hook raised; it may not impersonate a public status."""


_EventHook = Callable[[str, Mapping[str, Any]], None]
_FixtureAction = Callable[[], Sequence[Mapping[str, Any]]]
_PreOutcomeCheck = Callable[[], None]


def _emit(
    hook: _EventHook | None,
    event: str,
    **context: Any,
) -> None:
    if hook is not None:
        try:
            hook(event, context)
        except BaseException as error:
            raise _EventHookError(f"synthetic event hook failed at {event}") from error


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return (canonical_json(payload) + "\n").encode("utf-8")


def _with_digest(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    if "deterministic_digest" in result:
        raise RegularFilePublicationV2Error(
            "digest-bearing payload already contains deterministic_digest"
        )
    result["deterministic_digest"] = sha256_json(result)
    return result


def _require_sha256(value: object, label: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise RegularFilePublicationV2NotRunError(
            f"{label} must be lowercase SHA-256"
        )
    return value


def _require_exact_digest(payload: Mapping[str, Any], label: str) -> str:
    digest = payload.get("deterministic_digest")
    if (
        type(digest) is not str
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise RegularFilePublicationV2AmbiguousError(
            f"{label} has no valid deterministic digest"
        )
    core = dict(payload)
    del core["deterministic_digest"]
    if sha256_json(core) != digest:
        raise RegularFilePublicationV2AmbiguousError(
            f"{label} deterministic digest does not close"
        )
    return digest


def _stable_file_signature(observed: os.stat_result) -> tuple[int, ...]:
    return (
        observed.st_dev,
        observed.st_ino,
        observed.st_mode,
        observed.st_uid,
        observed.st_gid,
        observed.st_nlink,
        observed.st_size,
        observed.st_mtime_ns,
        observed.st_ctime_ns,
    )


def _directory_identity(observed: os.stat_result) -> tuple[int, int]:
    return observed.st_dev, observed.st_ino


def _close_best_effort(descriptor: int) -> None:
    if descriptor < 0:
        return
    try:
        os.close(descriptor)
    except BaseException:
        pass


def _require_posix_capabilities() -> None:
    """Fail closed before path access when required descriptor APIs are absent."""

    required_flags = ("O_NOFOLLOW", "O_CLOEXEC", "O_DIRECTORY")
    if os.name != "posix" or any(
        type(getattr(os, name, None)) is not int or getattr(os, name) == 0
        for name in required_flags
    ):
        raise RegularFilePublicationV2NotRunError(
            "regular-file publication v2 requires POSIX no-follow descriptors"
        )
    if not hasattr(os, "pread") or not hasattr(os, "fpathconf"):
        raise RegularFilePublicationV2NotRunError(
            "regular-file publication v2 requires pread and fpathconf"
        )
    supports_dir_fd = getattr(os, "supports_dir_fd", set())
    supports_follow = getattr(os, "supports_follow_symlinks", set())
    if os.open not in supports_dir_fd or os.stat not in supports_dir_fd:
        raise RegularFilePublicationV2NotRunError(
            "regular-file publication v2 requires openat/statat semantics"
        )
    if os.stat not in supports_follow:
        raise RegularFilePublicationV2NotRunError(
            "regular-file publication v2 requires no-follow stat semantics"
        )


def _snapshot_output_path(output_path: Path | str) -> Path:
    try:
        raw = os.fspath(output_path)
    except BaseException as error:
        raise RegularFilePublicationV2NotRunError(
            "output path is not path-like"
        ) from error
    if type(raw) is not str or not raw or "\x00" in raw:
        raise RegularFilePublicationV2NotRunError(
            "output path must be a non-empty text path"
        )
    if not os.path.isabs(raw):
        raise RegularFilePublicationV2NotRunError("output path must be absolute")
    if raw.startswith("//") or raw != os.path.normpath(raw):
        raise RegularFilePublicationV2NotRunError(
            "output path must be lexical, normalized, and name a file"
        )
    candidate = Path(raw)
    if candidate.name in {"", ".", ".."}:
        raise RegularFilePublicationV2NotRunError(
            "output path must be lexical, normalized, and name a file"
        )
    if any(component in {"", ".", ".."} for component in candidate.parts[1:]):
        raise RegularFilePublicationV2NotRunError(
            "output path contains an invalid lexical component"
        )
    if not candidate.name.isascii():
        raise RegularFilePublicationV2NotRunError(
            "output basename must be ASCII for stable namespace alias closure"
        )
    if candidate.name.lower().startswith(_RESERVED_OUTPUT_PREFIX):
        raise RegularFilePublicationV2NotRunError(
            "output basename collides with the reserved protocol namespace"
        )
    return candidate


@dataclass(frozen=True)
class RegularFileLayoutV2:
    """All fixed names participating in one flat publication collective."""

    output_path: Path
    output_path_digest: str
    output_namespace_digest: str
    attempt_name: str
    started_name: str
    ready_name: str
    not_run_name: str
    invalid_name: str
    records_name: str
    manifest_name: str
    commit_name: str

    @classmethod
    def from_output_path(cls, output_path: Path | str) -> RegularFileLayoutV2:
        output = _snapshot_output_path(output_path)
        output_digest = _sha256_bytes(os.fsencode(os.fspath(output)))
        namespace_name = output.name.lower()
        namespace_digest = _sha256_bytes(os.fsencode(namespace_name))
        prefix = f"{_INTERNAL_NAME_PREFIX}{namespace_digest}"
        layout = cls(
            output_path=output,
            output_path_digest=output_digest,
            output_namespace_digest=namespace_digest,
            attempt_name=f"{prefix}.attempt.json",
            started_name=f"{prefix}.started.json",
            ready_name=f"{prefix}.ready-to-commit.json",
            not_run_name=f"{prefix}.not-run.json",
            invalid_name=f"{prefix}.invalid.json",
            records_name=f"{prefix}.records.jsonl",
            manifest_name=f"{prefix}.manifest.json",
            commit_name=output.name,
        )
        names = layout.names
        if len(set(names.values())) != len(names):
            raise RegularFilePublicationV2NotRunError(
                "v2 publication names are not unique"
            )
        return layout

    @property
    def names(self) -> dict[str, str]:
        return {
            "attempt": self.attempt_name,
            "commit": self.commit_name,
            "invalid": self.invalid_name,
            "manifest": self.manifest_name,
            "not_run": self.not_run_name,
            "ready": self.ready_name,
            "records": self.records_name,
            "started": self.started_name,
        }

    @property
    def reserved_names(self) -> tuple[str, ...]:
        return tuple(self.names.values())


def _walk_absolute_directory_nofollow(
    path: Path,
) -> tuple[int, tuple[tuple[int, int], ...]]:
    """Open an absolute directory component-by-component without symlinks."""

    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    descriptor = -1
    identities: list[tuple[int, int]] = []
    try:
        descriptor = os.open(path.anchor, flags)
        root_stat = os.fstat(descriptor)
        if not stat.S_ISDIR(root_stat.st_mode):
            raise RegularFilePublicationV2NotRunError(
                "filesystem root is not a directory"
            )
        identities.append(_directory_identity(root_stat))
        for component in path.parts[1:]:
            next_descriptor = -1
            try:
                next_descriptor = os.open(component, flags, dir_fd=descriptor)
                next_stat = os.fstat(next_descriptor)
                if not stat.S_ISDIR(next_stat.st_mode):
                    raise RegularFilePublicationV2NotRunError(
                        "output parent contains a non-directory component"
                    )
                identities.append(_directory_identity(next_stat))
                _close_best_effort(descriptor)
                descriptor = next_descriptor
                next_descriptor = -1
            finally:
                _close_best_effort(next_descriptor)
        result = descriptor
        descriptor = -1
        return result, tuple(identities)
    except RegularFilePublicationV2NotRunError:
        raise
    except OSError as error:
        raise RegularFilePublicationV2NotRunError(
            "output parent is not a stable no-follow directory path"
        ) from error
    finally:
        _close_best_effort(descriptor)


@dataclass
class _PinnedParent:
    path: Path
    descriptor: int
    component_identities: tuple[tuple[int, int], ...]

    @classmethod
    def open(cls, path: Path) -> _PinnedParent:
        first_fd, first_identities = _walk_absolute_directory_nofollow(path)
        try:
            second_fd, second_identities = _walk_absolute_directory_nofollow(path)
            try:
                if first_identities != second_identities:
                    raise RegularFilePublicationV2NotRunError(
                        "output parent changed while it was pinned"
                    )
            finally:
                _close_best_effort(second_fd)
            return cls(path, first_fd, first_identities)
        except BaseException:
            _close_best_effort(first_fd)
            raise

    def assert_path(self) -> None:
        try:
            opened = os.fstat(self.descriptor)
            if (
                not stat.S_ISDIR(opened.st_mode)
                or _directory_identity(opened) != self.component_identities[-1]
            ):
                raise RegularFilePublicationV2AmbiguousError(
                    "pinned output parent identity changed"
                )
            observed_fd, observed_identities = _walk_absolute_directory_nofollow(
                self.path
            )
        except RegularFilePublicationV2NotRunError as error:
            raise RegularFilePublicationV2AmbiguousError(
                "lexical output parent path is no longer provable"
            ) from error
        try:
            if observed_identities != self.component_identities:
                raise RegularFilePublicationV2AmbiguousError(
                    "lexical output parent path pivoted"
                )
        finally:
            _close_best_effort(observed_fd)

    def fsync(self) -> None:
        try:
            os.fsync(self.descriptor)
        except OSError as error:
            raise RegularFilePublicationV2AmbiguousError(
                "output parent durability barrier failed"
            ) from error

    def close(self) -> None:
        descriptor = self.descriptor
        self.descriptor = -1
        _close_best_effort(descriptor)


@dataclass
class _OwnedRegularFile:
    name: str
    descriptor: int
    expected: bytes
    identity: tuple[int, int] | None = None
    signature: tuple[int, ...] | None = None

    def close(self) -> None:
        descriptor = self.descriptor
        self.descriptor = -1
        _close_best_effort(descriptor)


def _read_exact_pread(descriptor: int, byte_count: int, *, label: str) -> bytes:
    result = bytearray()
    offset = 0
    while offset < byte_count:
        chunk = os.pread(
            descriptor,
            min(_READ_CHUNK_BYTES, byte_count - offset),
            offset,
        )
        if not chunk:
            raise RegularFilePublicationV2AmbiguousError(
                f"{label} became shorter during descriptor read-back"
            )
        result.extend(chunk)
        offset += len(chunk)
    if os.pread(descriptor, 1, byte_count):
        raise RegularFilePublicationV2AmbiguousError(
            f"{label} grew during descriptor read-back"
        )
    return bytes(result)


def _assert_owned_exact(parent: _PinnedParent, owned: _OwnedRegularFile) -> None:
    if owned.identity is None or owned.signature is None or owned.descriptor < 0:
        raise RegularFilePublicationV2AmbiguousError(
            f"{owned.name} has no retained exact ownership proof"
        )
    try:
        before_descriptor = os.fstat(owned.descriptor)
        before_path = os.stat(
            owned.name,
            dir_fd=parent.descriptor,
            follow_symlinks=False,
        )
        signature = _stable_file_signature(before_descriptor)
        if (
            signature != owned.signature
            or _stable_file_signature(before_path) != owned.signature
            or not stat.S_ISREG(before_descriptor.st_mode)
            or before_descriptor.st_nlink != 1
            or _directory_identity(before_descriptor) != owned.identity
            or stat.S_IMODE(before_descriptor.st_mode) != 0o600
            or before_descriptor.st_uid != os.geteuid()
            or not stat.S_ISREG(before_path.st_mode)
            or before_path.st_nlink != 1
            or stat.S_IMODE(before_path.st_mode) != 0o600
            or before_path.st_uid != os.geteuid()
        ):
            raise RegularFilePublicationV2AmbiguousError(
                f"{owned.name} descriptor/name identity changed"
            )
        if _read_exact_pread(
            owned.descriptor,
            len(owned.expected),
            label=owned.name,
        ) != owned.expected:
            raise RegularFilePublicationV2AmbiguousError(
                f"{owned.name} bytes changed"
            )
        after_descriptor = os.fstat(owned.descriptor)
        after_path = os.stat(
            owned.name,
            dir_fd=parent.descriptor,
            follow_symlinks=False,
        )
        if (
            _stable_file_signature(after_descriptor) != owned.signature
            or _stable_file_signature(after_path) != owned.signature
        ):
            raise RegularFilePublicationV2AmbiguousError(
                f"{owned.name} changed during exact read-back"
            )
    except RegularFilePublicationV2AmbiguousError:
        raise
    except OSError as error:
        raise RegularFilePublicationV2AmbiguousError(
            f"{owned.name} exact ownership is unavailable"
        ) from error


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        try:
            written = os.write(descriptor, payload[offset:])
        except InterruptedError:
            continue
        if type(written) is not int or written <= 0:
            raise OSError(errno.EIO, "regular-file write made no progress")
        offset += written


def _try_reconcile_created_file(
    parent: _PinnedParent,
    owned: _OwnedRegularFile,
    *,
    hook: _EventHook | None,
) -> bool:
    """Forward-complete only when exact bytes and both barriers are reproved."""

    if owned.identity is None or owned.descriptor < 0:
        return False
    try:
        opened = os.fstat(owned.descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or _directory_identity(opened) != owned.identity
            or opened.st_size != len(owned.expected)
            or stat.S_IMODE(opened.st_mode) != 0o600
            or opened.st_uid != os.geteuid()
            or _read_exact_pread(
                owned.descriptor,
                len(owned.expected),
                label=owned.name,
            )
            != owned.expected
        ):
            return False
        if (
            owned.signature is not None
            and _stable_file_signature(opened) != owned.signature
        ):
            return False
        to_sync = os.fstat(owned.descriptor)
        if (
            not stat.S_ISREG(to_sync.st_mode)
            or to_sync.st_nlink != 1
            or _directory_identity(to_sync) != owned.identity
            or to_sync.st_size != len(owned.expected)
            or stat.S_IMODE(to_sync.st_mode) != 0o600
            or to_sync.st_uid != os.geteuid()
            or _stable_file_signature(to_sync) != _stable_file_signature(opened)
        ):
            return False
        generation_to_sync = _stable_file_signature(to_sync)
        os.fsync(owned.descriptor)
        durable = os.fstat(owned.descriptor)
        if (
            not stat.S_ISREG(durable.st_mode)
            or durable.st_nlink != 1
            or _directory_identity(durable) != owned.identity
            or durable.st_size != len(owned.expected)
            or stat.S_IMODE(durable.st_mode) != 0o600
            or durable.st_uid != os.geteuid()
            or _stable_file_signature(durable) != generation_to_sync
        ):
            return False
        durable_signature = generation_to_sync
        try:
            _emit(hook, "after_file_fsync", name=owned.name, reconciled=True)
        except _EventHookError:
            # A private observer cannot retract a barrier.  The exact proof
            # below still detects any mutation made before it raised.
            pass
        os.fsync(parent.descriptor)
        try:
            _emit(hook, "after_parent_fsync", name=owned.name, reconciled=True)
        except _EventHookError:
            # Reconciliation authority comes from the retained descriptor and
            # repeated exact proof, never from observer success.
            pass
        final = os.fstat(owned.descriptor)
        if (
            not stat.S_ISREG(final.st_mode)
            or final.st_nlink != 1
            or _directory_identity(final) != owned.identity
            or final.st_size != len(owned.expected)
            or stat.S_IMODE(final.st_mode) != 0o600
            or final.st_uid != os.geteuid()
            or _stable_file_signature(final) != durable_signature
        ):
            return False
        owned.signature = durable_signature
        _assert_owned_exact(parent, owned)
        parent.assert_path()
        return True
    except BaseException:
        return False


def _exclusive_create_exact(
    parent: _PinnedParent,
    name: str,
    payload: bytes,
    *,
    max_bytes: int,
    hook: _EventHook | None,
) -> _OwnedRegularFile:
    """Create one immutable final-name file and retain its authority descriptor."""

    if (
        type(name) is not str
        or not name
        or Path(name).name != name
        or type(payload) is not bytes
        or len(payload) > max_bytes
    ):
        raise _CreateBeforeOpenError("exclusive-create inputs are invalid")
    parent.assert_path()
    try:
        _emit(hook, "before_exclusive_open", name=name, directory_fd=parent.descriptor)
    except _EventHookError as error:
        raise _HookBeforeOpenError(
            f"exclusive create was interrupted before open: {name}"
        ) from error
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        descriptor = os.open(name, flags, 0o600, dir_fd=parent.descriptor)
    except FileExistsError as error:
        raise _NameConflictError(f"reserved name already exists: {name}") from error
    except OSError as error:
        raise _CreateBeforeOpenError(f"exclusive create failed: {name}") from error

    owned = _OwnedRegularFile(name=name, descriptor=descriptor, expected=payload)
    primary_error: BaseException | None = None
    try:
        _emit(
            hook,
            "after_exclusive_open",
            name=name,
            directory_fd=parent.descriptor,
            file_descriptor=descriptor,
        )
        initial = os.fstat(descriptor)
        owned.identity = _directory_identity(initial)
        if (
            not stat.S_ISREG(initial.st_mode)
            or initial.st_nlink != 1
            or initial.st_size != 0
            or initial.st_mode & 0o077
            or initial.st_uid != os.geteuid()
        ):
            raise RegularFilePublicationV2AmbiguousError(
                f"newly created file is not an exclusive private regular file: {name}"
            )
        os.fchmod(descriptor, 0o600)
        private = os.fstat(descriptor)
        if (
            not stat.S_ISREG(private.st_mode)
            or private.st_nlink != 1
            or private.st_size != 0
            or _directory_identity(private) != owned.identity
            or stat.S_IMODE(private.st_mode) != 0o600
            or private.st_uid != os.geteuid()
        ):
            raise RegularFilePublicationV2AmbiguousError(
                f"newly created file permissions are not exactly private: {name}"
            )
        _emit(hook, "after_initial_fstat", name=name, identity=owned.identity)
        _write_all(descriptor, payload)
        to_sync = os.fstat(descriptor)
        if (
            not stat.S_ISREG(to_sync.st_mode)
            or to_sync.st_nlink != 1
            or _directory_identity(to_sync) != owned.identity
            or to_sync.st_size != len(payload)
            or stat.S_IMODE(to_sync.st_mode) != 0o600
            or to_sync.st_uid != os.geteuid()
        ):
            raise RegularFilePublicationV2AmbiguousError(
                f"newly created file lost its private pre-sync identity: {name}"
            )
        generation_to_sync = _stable_file_signature(to_sync)
        os.fsync(descriptor)
        durable = os.fstat(descriptor)
        if (
            not stat.S_ISREG(durable.st_mode)
            or durable.st_nlink != 1
            or _directory_identity(durable) != owned.identity
            or durable.st_size != len(payload)
            or stat.S_IMODE(durable.st_mode) != 0o600
            or durable.st_uid != os.geteuid()
            or _stable_file_signature(durable) != generation_to_sync
        ):
            raise RegularFilePublicationV2AmbiguousError(
                f"newly created file lost its private durable identity: {name}"
            )
        durable_signature = generation_to_sync
        # Once the file barrier has returned and its generation is reproved,
        # reconciliation may retry the parent barrier but may not adopt a later
        # byte-identical generation created by an observer.
        owned.signature = durable_signature
        _emit(hook, "after_file_fsync", name=name, reconciled=False)
        os.fsync(parent.descriptor)
        _emit(hook, "after_parent_fsync", name=name, reconciled=False)
        final = os.fstat(descriptor)
        if (
            not stat.S_ISREG(final.st_mode)
            or final.st_nlink != 1
            or _directory_identity(final) != owned.identity
            or final.st_size != len(payload)
            or stat.S_IMODE(final.st_mode) != 0o600
            or final.st_uid != os.geteuid()
            or _stable_file_signature(final) != durable_signature
        ):
            raise RegularFilePublicationV2AmbiguousError(
                f"newly created file identity changed: {name}"
            )
        owned.signature = durable_signature
        _assert_owned_exact(parent, owned)
        parent.assert_path()
        _emit(hook, "after_file_durable", name=name, identity=owned.identity)
        return owned
    except BaseException as error:
        primary_error = error

    if _try_reconcile_created_file(parent, owned, hook=hook):
        return owned
    raise _CreateAfterOpenError(
        f"exclusive creation became ambiguous after open: {name}",
        owned=owned,
        cause=primary_error,
    )


def _assert_name_absent(parent: _PinnedParent, name: str) -> None:
    try:
        os.stat(name, dir_fd=parent.descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return
    except OSError as error:
        raise RegularFilePublicationV2AmbiguousError(
            f"absence of reserved name is unprovable: {name}"
        ) from error
    raise RegularFilePublicationV2AmbiguousError(
        f"forbidden reserved name exists: {name}"
    )


def _parent_generation(parent: _PinnedParent) -> tuple[int, ...]:
    try:
        observed = os.fstat(parent.descriptor)
    except OSError as error:
        raise RegularFilePublicationV2AmbiguousError(
            "pinned parent generation is unavailable"
        ) from error
    if (
        not stat.S_ISDIR(observed.st_mode)
        or _directory_identity(observed) != parent.component_identities[-1]
    ):
        raise RegularFilePublicationV2AmbiguousError(
            "pinned parent generation changed identity"
        )
    return _stable_file_signature(observed)


def _assert_no_legacy_namespace(parent: _PinnedParent) -> None:
    """Refuse an unqualified transition from the superseded v2 namespace."""

    parent.assert_path()
    before = _parent_generation(parent)
    try:
        entries = os.listdir(parent.descriptor)
    except (OSError, TypeError) as error:
        raise RegularFilePublicationV2AmbiguousError(
            "superseded publication namespace could not be scanned"
        ) from error
    parent.assert_path()
    after = _parent_generation(parent)
    if before != after:
        raise RegularFilePublicationV2AmbiguousError(
            "output parent changed during superseded namespace scan"
        )
    if any(type(name) is not str for name in entries):
        raise RegularFilePublicationV2AmbiguousError(
            "superseded publication namespace returned a non-text entry"
        )
    if any(
        name.lower().startswith(_LEGACY_INTERNAL_NAME_PREFIX) for name in entries
    ):
        raise RegularFilePublicationV2AmbiguousError(
            "superseded v2 publication authority exists in the output parent"
        )


def _reserved_generation(
    parent: _PinnedParent,
    names: Sequence[str],
) -> tuple[tuple[str, tuple[int, ...] | None], ...]:
    captured: list[tuple[str, tuple[int, ...] | None]] = []
    for name in sorted(set(names)):
        try:
            observed = os.stat(
                name,
                dir_fd=parent.descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            signature = None
        except OSError as error:
            raise RegularFilePublicationV2AmbiguousError(
                f"reserved-name generation is unavailable: {name}"
            ) from error
        else:
            signature = _stable_file_signature(observed)
        captured.append((name, signature))
    return tuple(captured)


def _preflight_reserved_names_absent(
    parent: _PinnedParent,
    names: Sequence[str],
) -> None:
    parent.assert_path()
    for name in names:
        try:
            os.stat(name, dir_fd=parent.descriptor, follow_symlinks=False)
        except FileNotFoundError:
            continue
        except OSError as error:
            raise RegularFilePublicationV2NotRunError(
                f"reserved-name preflight is unavailable: {name}"
            ) from error
        raise RegularFilePublicationV2NotRunError(
            f"reserved publication name already exists: {name}"
        )
    parent.assert_path()


def _validate_layout_against_parent(
    parent: _PinnedParent,
    layout: RegularFileLayoutV2,
) -> None:
    try:
        name_max = os.fpathconf(parent.descriptor, "PC_NAME_MAX")
    except (OSError, ValueError) as error:
        raise RegularFilePublicationV2NotRunError(
            "output parent NAME_MAX is unavailable"
        ) from error
    if type(name_max) is not int or name_max <= 0:
        raise RegularFilePublicationV2NotRunError(
            "output parent NAME_MAX is invalid"
        )
    for name in layout.reserved_names:
        if len(os.fsencode(name)) > name_max:
            raise RegularFilePublicationV2NotRunError(
                f"reserved publication name exceeds NAME_MAX: {name}"
            )


def _attempt_payload(
    layout: RegularFileLayoutV2,
    authorization_digest: str,
    owner_nonce: str,
) -> dict[str, Any]:
    return _with_digest(
        {
            "artifact_layout": ARTIFACT_LAYOUT,
            "authorization_digest": authorization_digest,
            "fixture_kind": FIXTURE_KIND,
            "names": layout.names,
            "output_path": os.fspath(layout.output_path),
            "output_path_digest": layout.output_path_digest,
            "owner_nonce": owner_nonce,
            "phase": "PRE_OUTCOME",
            "publication_backend": PUBLICATION_BACKEND,
            "schema_version": ATTEMPT_SCHEMA_VERSION,
            "status": "PENDING",
        }
    )


def _phase_payload(
    attempt: Mapping[str, Any],
    *,
    phase: str,
    status: str,
    previous_receipt_digest: str,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "artifact_layout": ARTIFACT_LAYOUT,
        "attempt_receipt_digest": attempt["deterministic_digest"],
        "authorization_digest": attempt["authorization_digest"],
        "fixture_kind": FIXTURE_KIND,
        "output_path": attempt["output_path"],
        "output_path_digest": attempt["output_path_digest"],
        "owner_nonce": attempt["owner_nonce"],
        "phase": phase,
        "previous_receipt_digest": previous_receipt_digest,
        "publication_backend": PUBLICATION_BACKEND,
        "schema_version": PHASE_SCHEMA_VERSION,
        "status": status,
    }
    if extra is not None:
        overlap = set(payload).intersection(extra)
        if overlap:
            raise RegularFilePublicationV2Error(
                f"phase receipt fields overlap: {sorted(overlap)}"
            )
        payload.update(extra)
    return _with_digest(payload)


def _freeze_synthetic_records(
    records: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], bytes]:
    if type(records) not in {list, tuple} or len(records) > _MAX_SYNTHETIC_RECORDS:
        raise RegularFilePublicationV2Error(
            "synthetic fixture must return a bounded list or tuple of records"
        )
    frozen: list[dict[str, Any]] = []
    encoded: list[bytes] = []
    for index, candidate in enumerate(records):
        if type(candidate) is not dict:
            raise RegularFilePublicationV2Error(
                "synthetic fixture records must be plain JSON objects"
            )
        try:
            payload = strict_json_loads(canonical_json(candidate))
        except (RecursionError, TypeError, ValueError, TraceValidationError) as error:
            raise RegularFilePublicationV2Error(
                "synthetic fixture record is not strict finite JSON"
            ) from error
        wrapped = {
            "fixture_kind": FIXTURE_KIND,
            "payload": payload,
            "record_index": index,
            "schema_version": RECORD_SCHEMA_VERSION,
        }
        frozen.append(wrapped)
        encoded.append(_canonical_bytes(wrapped))
    raw = b"".join(encoded)
    if len(raw) > _MAX_RECORDS_BYTES:
        raise RegularFilePublicationV2Error(
            "synthetic fixture records exceed the bounded byte limit"
        )
    return frozen, raw


def _manifest_payload(
    layout: RegularFileLayoutV2,
    attempt: Mapping[str, Any],
    started: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    records_raw: bytes,
) -> dict[str, Any]:
    return _with_digest(
        {
            "artifact_id": layout.commit_name,
            "artifact_layout": ARTIFACT_LAYOUT,
            "attempt_receipt_digest": attempt["deterministic_digest"],
            "authorization_digest": attempt["authorization_digest"],
            "fixture_kind": FIXTURE_KIND,
            "output_path": os.fspath(layout.output_path),
            "output_path_digest": layout.output_path_digest,
            "owner_nonce": attempt["owner_nonce"],
            "publication_backend": PUBLICATION_BACKEND,
            "records": {
                "byte_count": len(records_raw),
                "filename": layout.records_name,
                "record_count": len(records),
                "schema_version": RECORD_SCHEMA_VERSION,
                "sha256": _sha256_bytes(records_raw),
            },
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "started_receipt_digest": started["deterministic_digest"],
        }
    )


def _commit_payload(
    layout: RegularFileLayoutV2,
    attempt: Mapping[str, Any],
    started: Mapping[str, Any],
    ready: Mapping[str, Any],
    manifest: Mapping[str, Any],
    records_raw: bytes,
) -> dict[str, Any]:
    return _with_digest(
        {
            "artifact_id": layout.commit_name,
            "artifact_layout": ARTIFACT_LAYOUT,
            "attempt_receipt_digest": attempt["deterministic_digest"],
            "authorization_digest": attempt["authorization_digest"],
            "fixture_kind": FIXTURE_KIND,
            "manifest": {
                "deterministic_digest": manifest["deterministic_digest"],
                "filename": layout.manifest_name,
                "sha256": _sha256_bytes(_canonical_bytes(manifest)),
            },
            "output_path": os.fspath(layout.output_path),
            "output_path_digest": layout.output_path_digest,
            "owner_nonce": attempt["owner_nonce"],
            "phase": "COMMITTED",
            "previous_receipt_digest": ready["deterministic_digest"],
            "publication_backend": PUBLICATION_BACKEND,
            "ready_receipt_digest": ready["deterministic_digest"],
            "records": {
                "byte_count": len(records_raw),
                "filename": layout.records_name,
                "sha256": _sha256_bytes(records_raw),
            },
            "schema_version": COMMIT_SCHEMA_VERSION,
            "started_receipt_digest": started["deterministic_digest"],
            "status": "COMMITTED",
        }
    )


@dataclass
class _PublicationSession:
    parent: _PinnedParent
    layout: RegularFileLayoutV2
    hook: _EventHook | None
    owned: list[_OwnedRegularFile] = field(default_factory=list)
    attempt_file: _OwnedRegularFile | None = None
    started_file: _OwnedRegularFile | None = None
    ready_file: _OwnedRegularFile | None = None
    not_run_file: _OwnedRegularFile | None = None
    invalid_file: _OwnedRegularFile | None = None
    records_file: _OwnedRegularFile | None = None
    manifest_file: _OwnedRegularFile | None = None
    commit_file: _OwnedRegularFile | None = None

    def create_authority(
        self,
        name: str,
        payload: Mapping[str, Any],
    ) -> _OwnedRegularFile:
        created = _exclusive_create_exact(
            self.parent,
            name,
            _canonical_bytes(payload),
            max_bytes=_MAX_CONTROL_BYTES,
            hook=self.hook,
        )
        self.owned.append(created)
        return created

    def create_data(self, name: str, payload: bytes) -> _OwnedRegularFile:
        created = _exclusive_create_exact(
            self.parent,
            name,
            payload,
            max_bytes=_MAX_RECORDS_BYTES,
            hook=self.hook,
        )
        self.owned.append(created)
        return created

    def close(self) -> None:
        for owned in reversed(self.owned):
            owned.close()
        self.owned.clear()


def _collective_snapshot(
    session: _PublicationSession,
    *,
    terminal: str,
    required: Sequence[_OwnedRegularFile],
    absent: Sequence[str],
    snapshot_index: int,
) -> tuple[tuple[int, ...], tuple[tuple[str, tuple[int, ...] | None], ...]]:
    try:
        _emit(
            session.hook,
            "before_collective_snapshot",
            terminal=terminal,
            snapshot_index=snapshot_index,
            directory_fd=session.parent.descriptor,
        )
    except _EventHookError:
        terminal_receipt = {
            "NOT_RUN": session.not_run_file,
            "INVALID": session.invalid_file,
            "COMMITTED": session.commit_file,
        }.get(terminal)
        if terminal_receipt is None or terminal_receipt.descriptor < 0:
            raise
    session.parent.assert_path()
    _assert_no_legacy_namespace(session.parent)
    participating_names = tuple(owned.name for owned in required) + tuple(absent)
    before_parent = _parent_generation(session.parent)
    before_reserved = _reserved_generation(session.parent, participating_names)
    for owned in required:
        _assert_owned_exact(session.parent, owned)
    for name in absent:
        _assert_name_absent(session.parent, name)
    session.parent.fsync()
    _assert_no_legacy_namespace(session.parent)
    for owned in required:
        _assert_owned_exact(session.parent, owned)
    for name in absent:
        _assert_name_absent(session.parent, name)
    session.parent.assert_path()
    after_reserved = _reserved_generation(session.parent, participating_names)
    after_parent = _parent_generation(session.parent)
    if before_parent != after_parent or before_reserved != after_reserved:
        raise RegularFilePublicationV2AmbiguousError(
            f"{terminal} collective generation changed during snapshot"
        )
    return before_parent, before_reserved


def _prove_terminal_collective(
    session: _PublicationSession,
    *,
    terminal: str,
    required: Sequence[_OwnedRegularFile],
    absent: Sequence[str],
) -> None:
    generation = None
    for snapshot_index in (1, 2):
        observed_generation = _collective_snapshot(
            session,
            terminal=terminal,
            required=required,
            absent=absent,
            snapshot_index=snapshot_index,
        )
        if generation is not None and observed_generation != generation:
            raise RegularFilePublicationV2AmbiguousError(
                f"{terminal} collective generation changed between snapshots"
            )
        generation = observed_generation


def _reason_code(stage: str, error: BaseException) -> str:
    error_name = type(error).__name__
    if not error_name.isidentifier() or len(error_name) > 128:
        error_name = "BaseException"
    return f"{stage}:{error_name}"


def _publish_not_run(
    session: _PublicationSession,
    attempt: Mapping[str, Any],
    error: BaseException,
) -> None:
    if session.attempt_file is None or session.started_file is not None:
        raise RegularFilePublicationV2AmbiguousError(
            "NOT_RUN is forbidden without exact PRE_OUTCOME-only authority"
        ) from error
    try:
        payload = _phase_payload(
            attempt,
            phase="PRE_OUTCOME",
            status="NOT_RUN",
            previous_receipt_digest=attempt["deterministic_digest"],
            extra={"reason_code": _reason_code("pre_outcome", error)},
        )
    except BaseException as payload_error:
        raise RegularFilePublicationV2AmbiguousError(
            "NOT_RUN receipt could not be constructed"
        ) from payload_error
    try:
        try:
            session.not_run_file = session.create_authority(
                session.layout.not_run_name,
                payload,
            )
        except _CreateAfterOpenError as creation_error:
            creation_error.owned.close()
            raise
        _prove_terminal_collective(
            session,
            terminal="NOT_RUN",
            required=(session.attempt_file, session.not_run_file),
            absent=(
                session.layout.started_name,
                session.layout.ready_name,
                session.layout.invalid_name,
                session.layout.records_name,
                session.layout.manifest_name,
                session.layout.commit_name,
            ),
        )
    except BaseException as terminal_error:
        raise RegularFilePublicationV2AmbiguousError(
            "NOT_RUN terminal closure is ambiguous"
        ) from terminal_error
    raise RegularFilePublicationV2NotRunError(
        "synthetic publication stopped before STARTED"
    ) from error


def _publish_invalid(
    session: _PublicationSession,
    attempt: Mapping[str, Any],
    started: Mapping[str, Any],
    ready: Mapping[str, Any] | None,
    error: BaseException,
    *,
    failure_phase: str,
) -> None:
    if session.attempt_file is None or session.started_file is None:
        raise RegularFilePublicationV2AmbiguousError(
            "INVALID requires exact STARTED authority"
        ) from error
    if session.commit_file is not None:
        raise RegularFilePublicationV2AmbiguousError(
            "INVALID is forbidden after commit ownership"
        ) from error
    if (ready is None) != (session.ready_file is None):
        raise RegularFilePublicationV2AmbiguousError(
            "INVALID READY evidence does not match retained authority"
        ) from error
    previous = (
        ready["deterministic_digest"]
        if ready is not None
        else started["deterministic_digest"]
    )
    try:
        payload = _phase_payload(
            attempt,
            phase=failure_phase,
            status="INVALID",
            previous_receipt_digest=previous,
            extra={"reason_code": _reason_code("post_started", error)},
        )
    except BaseException as payload_error:
        raise RegularFilePublicationV2AmbiguousError(
            "INVALID receipt could not be constructed"
        ) from payload_error
    try:
        _assert_name_absent(session.parent, session.layout.commit_name)
        try:
            session.invalid_file = session.create_authority(
                session.layout.invalid_name,
                payload,
            )
        except _CreateAfterOpenError as creation_error:
            creation_error.owned.close()
            raise
        required: list[_OwnedRegularFile] = [
            session.attempt_file,
            session.started_file,
        ]
        absent = [session.layout.not_run_name, session.layout.commit_name]
        if session.ready_file is None:
            absent.append(session.layout.ready_name)
        else:
            if session.records_file is None or session.manifest_file is None:
                raise RegularFilePublicationV2AmbiguousError(
                    "READY-backed INVALID lacks retained data authority"
                )
            required.extend(
                (
                    session.records_file,
                    session.manifest_file,
                    session.ready_file,
                )
            )
        required.append(session.invalid_file)
        _prove_terminal_collective(
            session,
            terminal="INVALID",
            required=required,
            absent=absent,
        )
    except BaseException as terminal_error:
        raise RegularFilePublicationV2AmbiguousError(
            "INVALID terminal closure is ambiguous"
        ) from terminal_error
    raise RegularFilePublicationV2InvalidError(
        "synthetic publication crossed STARTED without a commit"
    ) from error


def publish_synthetic_fixture_v2(
    output_path: Path | str,
    *,
    authorization_digest: str,
    fixture_action: _FixtureAction,
    _pre_outcome_check: _PreOutcomeCheck | None = None,
    _event_hook: _EventHook | None = None,
) -> dict[str, Any]:
    """Publish one non-diagnostic fixture through the v2 state machine.

    ``fixture_action`` is deliberately invoked only after an exact durable
    STARTED receipt.  It returns synthetic JSON objects; it has no access to a
    diagnostic bundle through this API.
    """

    _require_posix_capabilities()
    layout = RegularFileLayoutV2.from_output_path(output_path)
    authorization = _require_sha256(authorization_digest, "authorization digest")
    if not callable(fixture_action) or (
        _pre_outcome_check is not None and not callable(_pre_outcome_check)
    ) or (
        _event_hook is not None and not callable(_event_hook)
    ):
        raise RegularFilePublicationV2NotRunError(
            "synthetic fixture callbacks must be callable"
        )

    parent = _PinnedParent.open(layout.output_path.parent)
    session = _PublicationSession(parent=parent, layout=layout, hook=_event_hook)
    attempt_payload: dict[str, Any] | None = None
    started_payload: dict[str, Any] | None = None
    ready_payload: dict[str, Any] | None = None
    try:
        try:
            _validate_layout_against_parent(parent, layout)
            _assert_no_legacy_namespace(parent)
            parent.fsync()
            parent.assert_path()
            _assert_no_legacy_namespace(parent)
            _preflight_reserved_names_absent(parent, layout.reserved_names)
        except RegularFilePublicationV2NotRunError:
            raise
        except BaseException as error:
            raise RegularFilePublicationV2NotRunError(
                "publication preflight failed before attempt ownership"
            ) from error

        try:
            owner_nonce = secrets.token_hex(_OWNER_NONCE_BYTES)
            attempt_payload = _attempt_payload(layout, authorization, owner_nonce)
        except BaseException as error:
            raise RegularFilePublicationV2NotRunError(
                "attempt identity could not be constructed before ownership"
            ) from error
        try:
            session.attempt_file = session.create_authority(
                layout.attempt_name,
                attempt_payload,
            )
        except _NameConflictError as error:
            raise RegularFilePublicationV2NotRunError(
                "output-global attempt reservation is already occupied"
            ) from error
        except _CreateBeforeOpenError as error:
            raise RegularFilePublicationV2NotRunError(
                "attempt reservation was not created"
            ) from error
        except _CreateAfterOpenError as error:
            error.owned.close()
            raise RegularFilePublicationV2AmbiguousError(
                "attempt reservation ownership became ambiguous"
            ) from error
        try:
            _emit(_event_hook, "after_attempt", name=layout.attempt_name)
            _emit(_event_hook, "before_started", name=layout.started_name)
            if _pre_outcome_check is not None:
                _pre_outcome_check()
            _assert_owned_exact(parent, session.attempt_file)
            parent.assert_path()
            started_payload = _phase_payload(
                attempt_payload,
                phase="STARTED",
                status="PENDING",
                previous_receipt_digest=attempt_payload["deterministic_digest"],
            )
        except BaseException as error:
            _publish_not_run(session, attempt_payload, error)
        try:
            _assert_no_legacy_namespace(parent)
            session.started_file = session.create_authority(
                layout.started_name,
                started_payload,
            )
        except (_NameConflictError, _CreateAfterOpenError) as error:
            if isinstance(error, _CreateAfterOpenError):
                error.owned.close()
            raise RegularFilePublicationV2AmbiguousError(
                "STARTED authority is ambiguous"
            ) from error
        except _CreateBeforeOpenError as error:
            _publish_not_run(session, attempt_payload, error)
        try:
            _prove_terminal_collective(
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
        except RegularFilePublicationV2AmbiguousError:
            raise
        except BaseException as error:
            _publish_invalid(
                session,
                attempt_payload,
                started_payload,
                None,
                error,
                failure_phase="STARTED",
            )
        try:
            try:
                _emit(_event_hook, "after_started", name=layout.started_name)
            except BaseException as outcome_error:
                raise _FixtureOutcomeError(
                    "synthetic outcome hook failed after STARTED"
                ) from outcome_error
            _assert_no_legacy_namespace(parent)
            try:
                raw_records = fixture_action()
                frozen_records, records_bytes = _freeze_synthetic_records(raw_records)
            except BaseException as outcome_error:
                # Caller-controlled exceptions must not impersonate a substrate
                # ambiguity and bypass the monotonic STARTED -> INVALID boundary.
                raise _FixtureOutcomeError(
                    "synthetic outcome callback or payload failed"
                ) from outcome_error
            try:
                session.records_file = session.create_data(
                    layout.records_name,
                    records_bytes,
                )
            except _CreateAfterOpenError as error:
                error.owned.close()
                raise RegularFilePublicationV2Error(
                    "records publication failed after exclusive open"
                ) from error
            _emit(_event_hook, "after_records", name=layout.records_name)

            manifest_payload = _manifest_payload(
                layout,
                attempt_payload,
                started_payload,
                frozen_records,
                records_bytes,
            )
            try:
                session.manifest_file = session.create_authority(
                    layout.manifest_name,
                    manifest_payload,
                )
            except _CreateAfterOpenError as error:
                error.owned.close()
                raise RegularFilePublicationV2Error(
                    "manifest publication failed after exclusive open"
                ) from error
            _emit(_event_hook, "after_manifest", name=layout.manifest_name)

            ready_candidate = _phase_payload(
                attempt_payload,
                phase="READY_TO_COMMIT",
                status="PENDING",
                previous_receipt_digest=started_payload["deterministic_digest"],
                extra={
                    "manifest_digest": manifest_payload["deterministic_digest"],
                    "manifest_sha256": _sha256_bytes(
                        _canonical_bytes(manifest_payload)
                    ),
                    "records_byte_count": len(records_bytes),
                    "records_sha256": _sha256_bytes(records_bytes),
                },
            )
            try:
                session.ready_file = session.create_authority(
                    layout.ready_name,
                    ready_candidate,
                )
            except (_NameConflictError, _CreateAfterOpenError) as error:
                if isinstance(error, _CreateAfterOpenError):
                    error.owned.close()
                raise RegularFilePublicationV2AmbiguousError(
                    "READY_TO_COMMIT authority is ambiguous"
                ) from error
            ready_payload = ready_candidate
            _emit(_event_hook, "after_ready", name=layout.ready_name)

            _prove_terminal_collective(
                session,
                terminal="PRE_COMMIT",
                required=(
                    session.attempt_file,
                    session.started_file,
                    session.records_file,
                    session.manifest_file,
                    session.ready_file,
                ),
                absent=(
                    layout.not_run_name,
                    layout.invalid_name,
                    layout.commit_name,
                ),
            )
            commit_payload = _commit_payload(
                layout,
                attempt_payload,
                started_payload,
                ready_payload,
                manifest_payload,
                records_bytes,
            )
            _emit(_event_hook, "before_commit", name=layout.commit_name)
            try:
                session.commit_file = session.create_authority(
                    layout.commit_name,
                    commit_payload,
                )
            except _HookBeforeOpenError as error:
                raise RegularFilePublicationV2Error(
                    "commit creation hook failed before exclusive open"
                ) from error
            except (_NameConflictError, _CreateBeforeOpenError) as error:
                raise RegularFilePublicationV2AmbiguousError(
                    "commit name authority is ambiguous"
                ) from error
            except _CreateAfterOpenError as error:
                error.owned.close()
                raise RegularFilePublicationV2AmbiguousError(
                    "commit creation entered an ambiguous state"
                ) from error
            try:
                _emit(_event_hook, "after_commit", name=layout.commit_name)
            except BaseException:
                # The commit descriptor already exists and closed durably.  The
                # only safe direction is forward proof of COMMITTED.
                pass
            _prove_terminal_collective(
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
                "artifact_commit_digest": commit_payload["deterministic_digest"],
                "artifact_layout": ARTIFACT_LAYOUT,
                "artifact_path": os.fspath(layout.output_path),
                "authorization_digest": authorization,
                "fixture_kind": FIXTURE_KIND,
                "run_manifest_digest": manifest_payload["deterministic_digest"],
                "status": "COMMITTED",
            }
        except RegularFilePublicationV2AmbiguousError:
            raise
        except BaseException as error:
            _publish_invalid(
                session,
                attempt_payload,
                started_payload,
                ready_payload,
                error,
                failure_phase=(
                    "READY_TO_COMMIT" if ready_payload is not None else "STARTED"
                ),
            )
    finally:
        session.close()
        parent.close()


def _read_bounded_regular_file_at(
    parent: _PinnedParent,
    name: str,
    *,
    max_bytes: int,
) -> bytes:
    descriptor = -1
    try:
        before = os.stat(name, dir_fd=parent.descriptor, follow_symlinks=False)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size > max_bytes
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_uid != os.geteuid()
        ):
            raise RegularFilePublicationV2AmbiguousError(
                f"{name} is not a bounded single-link regular file"
            )
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
        descriptor = os.open(name, flags, dir_fd=parent.descriptor)
        opened = os.fstat(descriptor)
        signature = _stable_file_signature(opened)
        if signature != _stable_file_signature(before):
            raise RegularFilePublicationV2AmbiguousError(
                f"{name} changed while it was opened"
            )
        raw = _read_exact_pread(descriptor, opened.st_size, label=name)
        after_descriptor = os.fstat(descriptor)
        after_path = os.stat(
            name,
            dir_fd=parent.descriptor,
            follow_symlinks=False,
        )
        if (
            _stable_file_signature(after_descriptor) != signature
            or _stable_file_signature(after_path) != signature
        ):
            raise RegularFilePublicationV2AmbiguousError(
                f"{name} changed during bounded observation"
            )
        return raw
    except RegularFilePublicationV2AmbiguousError:
        raise
    except OSError as error:
        raise RegularFilePublicationV2AmbiguousError(
            f"{name} is not a stable regular file"
        ) from error
    finally:
        _close_best_effort(descriptor)


def _forward_sync_exact_regular_file_at(
    parent: _PinnedParent,
    name: str,
) -> None:
    """Re-establish durability without changing file bytes or namespace."""

    descriptor = -1
    try:
        before = os.stat(name, dir_fd=parent.descriptor, follow_symlinks=False)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_uid != os.geteuid()
        ):
            raise RegularFilePublicationV2AmbiguousError(
                f"{name} is not an exact private regular file for forward sync"
            )
        flags = os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
        descriptor = os.open(name, flags, dir_fd=parent.descriptor)
        opened = os.fstat(descriptor)
        signature = _stable_file_signature(opened)
        if signature != _stable_file_signature(before):
            raise RegularFilePublicationV2AmbiguousError(
                f"{name} changed while it was opened for forward sync"
            )
        os.fsync(descriptor)
        after_descriptor = os.fstat(descriptor)
        after_path = os.stat(
            name,
            dir_fd=parent.descriptor,
            follow_symlinks=False,
        )
        if (
            _stable_file_signature(after_descriptor) != signature
            or _stable_file_signature(after_path) != signature
        ):
            raise RegularFilePublicationV2AmbiguousError(
                f"{name} changed across its forward durability barrier"
            )
    except RegularFilePublicationV2AmbiguousError:
        raise
    except OSError as error:
        raise RegularFilePublicationV2AmbiguousError(
            f"{name} could not be forward-synchronized exactly"
        ) from error
    finally:
        _close_best_effort(descriptor)


def _read_canonical_object_at(
    parent: _PinnedParent,
    name: str,
) -> dict[str, Any]:
    raw = _read_bounded_regular_file_at(parent, name, max_bytes=_MAX_CONTROL_BYTES)
    try:
        parsed = strict_json_loads(raw.decode("utf-8"))
        canonical = _canonical_bytes(parsed) if type(parsed) is dict else None
    except (
        RecursionError,
        TypeError,
        UnicodeDecodeError,
        ValueError,
        TraceValidationError,
    ) as error:
        raise RegularFilePublicationV2AmbiguousError(
            f"{name} is not strict canonical JSON"
        ) from error
    if type(parsed) is not dict or raw != canonical:
        raise RegularFilePublicationV2AmbiguousError(
            f"{name} is not one canonical JSON object"
        )
    _require_exact_digest(parsed, name)
    return parsed


def _name_exists(parent: _PinnedParent, name: str) -> bool:
    try:
        os.stat(name, dir_fd=parent.descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return False
    except OSError as error:
        raise RegularFilePublicationV2AmbiguousError(
            f"reserved name state is unavailable: {name}"
        ) from error
    return True


def _validate_attempt_object(
    attempt: Mapping[str, Any],
    layout: RegularFileLayoutV2,
    expected_authorization_digest: str | None,
) -> None:
    expected_keys = {
        "artifact_layout",
        "authorization_digest",
        "deterministic_digest",
        "fixture_kind",
        "names",
        "output_path",
        "output_path_digest",
        "owner_nonce",
        "phase",
        "publication_backend",
        "schema_version",
        "status",
    }
    if set(attempt) != expected_keys:
        raise RegularFilePublicationV2AmbiguousError(
            "attempt receipt keys do not match v2"
        )
    owner_nonce = attempt.get("owner_nonce")
    authorization = attempt.get("authorization_digest")
    if (
        attempt.get("artifact_layout") != ARTIFACT_LAYOUT
        or attempt.get("publication_backend") != PUBLICATION_BACKEND
        or attempt.get("fixture_kind") != FIXTURE_KIND
        or attempt.get("schema_version") != ATTEMPT_SCHEMA_VERSION
        or attempt.get("phase") != "PRE_OUTCOME"
        or attempt.get("status") != "PENDING"
        or attempt.get("names") != layout.names
        or attempt.get("output_path") != os.fspath(layout.output_path)
        or attempt.get("output_path_digest") != layout.output_path_digest
        or type(owner_nonce) is not str
        or len(owner_nonce) != 2 * _OWNER_NONCE_BYTES
        or any(character not in "0123456789abcdef" for character in owner_nonce)
        or type(authorization) is not str
        or len(authorization) != 64
        or any(character not in "0123456789abcdef" for character in authorization)
        or (
            expected_authorization_digest is not None
            and authorization != expected_authorization_digest
        )
    ):
        raise RegularFilePublicationV2AmbiguousError(
            "attempt receipt identity does not match the requested output"
        )


def _validate_phase_object(
    receipt: Mapping[str, Any],
    attempt: Mapping[str, Any],
    *,
    phase: str,
    status: str,
    previous_receipt_digest: str,
    required_extra_keys: set[str],
) -> None:
    base_keys = {
        "artifact_layout",
        "attempt_receipt_digest",
        "authorization_digest",
        "deterministic_digest",
        "fixture_kind",
        "output_path",
        "output_path_digest",
        "owner_nonce",
        "phase",
        "previous_receipt_digest",
        "publication_backend",
        "schema_version",
        "status",
    }
    if set(receipt) != base_keys | required_extra_keys:
        raise RegularFilePublicationV2AmbiguousError(
            f"{phase} receipt keys do not match v2"
        )
    if (
        receipt.get("artifact_layout") != ARTIFACT_LAYOUT
        or receipt.get("attempt_receipt_digest")
        != attempt.get("deterministic_digest")
        or receipt.get("authorization_digest")
        != attempt.get("authorization_digest")
        or receipt.get("fixture_kind") != FIXTURE_KIND
        or receipt.get("output_path") != attempt.get("output_path")
        or receipt.get("output_path_digest")
        != attempt.get("output_path_digest")
        or receipt.get("owner_nonce") != attempt.get("owner_nonce")
        or receipt.get("phase") != phase
        or receipt.get("previous_receipt_digest") != previous_receipt_digest
        or receipt.get("publication_backend") != PUBLICATION_BACKEND
        or receipt.get("schema_version") != PHASE_SCHEMA_VERSION
        or receipt.get("status") != status
    ):
        raise RegularFilePublicationV2AmbiguousError(
            f"{phase} receipt chain does not close"
        )


def _validate_reason_code(receipt: Mapping[str, Any], prefix: str) -> None:
    reason_code = receipt.get("reason_code")
    expected_prefix = f"{prefix}:"
    if (
        type(reason_code) is not str
        or not reason_code.startswith(expected_prefix)
        or not reason_code[len(expected_prefix) :].isidentifier()
        or len(reason_code) > len(expected_prefix) + 128
    ):
        raise RegularFilePublicationV2AmbiguousError(
            "terminal reason code is not canonical"
        )


def _validate_records_and_manifest(
    parent: _PinnedParent,
    layout: RegularFileLayoutV2,
    attempt: Mapping[str, Any],
    started: Mapping[str, Any],
) -> tuple[bytes, dict[str, Any]]:
    records_raw = _read_bounded_regular_file_at(
        parent,
        layout.records_name,
        max_bytes=_MAX_RECORDS_BYTES,
    )
    records: list[dict[str, Any]] = []
    for index, line in enumerate(records_raw.splitlines(keepends=True)):
        if index >= _MAX_SYNTHETIC_RECORDS:
            raise RegularFilePublicationV2AmbiguousError(
                "records file exceeds the synthetic record-count limit"
            )
        if not line.endswith(b"\n"):
            raise RegularFilePublicationV2AmbiguousError(
                "records file has a truncated final frame"
            )
        try:
            parsed = strict_json_loads(line[:-1].decode("utf-8"))
            canonical = _canonical_bytes(parsed) if type(parsed) is dict else None
        except (
            RecursionError,
            TypeError,
            UnicodeDecodeError,
            ValueError,
            TraceValidationError,
        ) as error:
            raise RegularFilePublicationV2AmbiguousError(
                "records file contains invalid strict JSON"
            ) from error
        if (
            type(parsed) is not dict
            or canonical != line
            or set(parsed)
            != {"fixture_kind", "payload", "record_index", "schema_version"}
            or parsed.get("fixture_kind") != FIXTURE_KIND
            or type(parsed.get("payload")) is not dict
            or type(parsed.get("record_index")) is not int
            or parsed.get("record_index") != index
            or parsed.get("schema_version") != RECORD_SCHEMA_VERSION
        ):
            raise RegularFilePublicationV2AmbiguousError(
                "records file frame identity does not close"
            )
        records.append(parsed)
    manifest = _read_canonical_object_at(parent, layout.manifest_name)
    expected_keys = {
        "artifact_id",
        "artifact_layout",
        "attempt_receipt_digest",
        "authorization_digest",
        "deterministic_digest",
        "fixture_kind",
        "output_path",
        "output_path_digest",
        "owner_nonce",
        "publication_backend",
        "records",
        "schema_version",
        "started_receipt_digest",
    }
    record_info = manifest.get("records")
    if (
        set(manifest) != expected_keys
        or manifest.get("artifact_id") != layout.commit_name
        or manifest.get("artifact_layout") != ARTIFACT_LAYOUT
        or manifest.get("attempt_receipt_digest")
        != attempt.get("deterministic_digest")
        or manifest.get("authorization_digest")
        != attempt.get("authorization_digest")
        or manifest.get("fixture_kind") != FIXTURE_KIND
        or manifest.get("output_path") != os.fspath(layout.output_path)
        or manifest.get("output_path_digest") != layout.output_path_digest
        or manifest.get("owner_nonce") != attempt.get("owner_nonce")
        or manifest.get("publication_backend") != PUBLICATION_BACKEND
        or manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION
        or manifest.get("started_receipt_digest")
        != started.get("deterministic_digest")
        or type(record_info) is not dict
        or type(record_info.get("byte_count")) is not int
        or type(record_info.get("record_count")) is not int
        or record_info
        != {
            "byte_count": len(records_raw),
            "filename": layout.records_name,
            "record_count": len(records),
            "schema_version": RECORD_SCHEMA_VERSION,
            "sha256": _sha256_bytes(records_raw),
        }
    ):
        raise RegularFilePublicationV2AmbiguousError(
            "manifest does not close over the exact records collective"
        )
    return records_raw, manifest


def _inspect_payload_once(
    parent: _PinnedParent,
    layout: RegularFileLayoutV2,
    expected_authorization_digest: str | None,
) -> dict[str, Any]:
    if not _name_exists(parent, layout.attempt_name):
        occupied_without_attempt = [
            name
            for name in layout.reserved_names
            if name != layout.attempt_name and _name_exists(parent, name)
        ]
        if occupied_without_attempt:
            raise RegularFilePublicationV2AmbiguousError(
                "reserved names exist without an exact attempt receipt"
            )
        return {
            "output_path": os.fspath(layout.output_path),
            "status": "UNRESERVED",
        }
    attempt = _read_canonical_object_at(parent, layout.attempt_name)
    _validate_attempt_object(attempt, layout, expected_authorization_digest)
    attempt_digest = attempt["deterministic_digest"]
    has_commit = _name_exists(parent, layout.commit_name)
    has_invalid = _name_exists(parent, layout.invalid_name)
    has_not_run = _name_exists(parent, layout.not_run_name)
    if sum((has_commit, has_invalid, has_not_run)) > 1:
        raise RegularFilePublicationV2AmbiguousError(
            "conflicting terminal receipts exist"
        )

    if has_not_run:
        for forbidden in (
            layout.started_name,
            layout.ready_name,
            layout.invalid_name,
            layout.records_name,
            layout.manifest_name,
            layout.commit_name,
        ):
            _assert_name_absent(parent, forbidden)
        not_run = _read_canonical_object_at(parent, layout.not_run_name)
        _validate_phase_object(
            not_run,
            attempt,
            phase="PRE_OUTCOME",
            status="NOT_RUN",
            previous_receipt_digest=attempt_digest,
            required_extra_keys={"reason_code"},
        )
        _validate_reason_code(not_run, "pre_outcome")
        return {
            "authorization_digest": attempt["authorization_digest"],
            "output_path": os.fspath(layout.output_path),
            "status": "NOT_RUN",
            "terminal_digest": not_run["deterministic_digest"],
        }

    started = _read_canonical_object_at(parent, layout.started_name)
    _validate_phase_object(
        started,
        attempt,
        phase="STARTED",
        status="PENDING",
        previous_receipt_digest=attempt_digest,
        required_extra_keys=set(),
    )
    started_digest = started["deterministic_digest"]

    if has_invalid:
        _assert_name_absent(parent, layout.not_run_name)
        _assert_name_absent(parent, layout.commit_name)
        previous = started_digest
        if _name_exists(parent, layout.ready_name):
            records_raw, manifest = _validate_records_and_manifest(
                parent,
                layout,
                attempt,
                started,
            )
            ready = _read_canonical_object_at(parent, layout.ready_name)
            _validate_phase_object(
                ready,
                attempt,
                phase="READY_TO_COMMIT",
                status="PENDING",
                previous_receipt_digest=started_digest,
                required_extra_keys={
                    "manifest_digest",
                    "manifest_sha256",
                    "records_byte_count",
                    "records_sha256",
                },
            )
            if (
                ready.get("manifest_digest")
                != manifest.get("deterministic_digest")
                or ready.get("manifest_sha256")
                != _sha256_bytes(_canonical_bytes(manifest))
                or type(ready.get("records_byte_count")) is not int
                or ready.get("records_byte_count") != len(records_raw)
                or ready.get("records_sha256") != _sha256_bytes(records_raw)
            ):
                raise RegularFilePublicationV2AmbiguousError(
                    "READY receipt does not close over data sidecars"
                )
            previous = ready["deterministic_digest"]
        invalid = _read_canonical_object_at(parent, layout.invalid_name)
        failure_phase = invalid.get("phase")
        expected_failure_phase = (
            "READY_TO_COMMIT"
            if _name_exists(parent, layout.ready_name)
            else "STARTED"
        )
        if failure_phase != expected_failure_phase:
            raise RegularFilePublicationV2AmbiguousError(
                "INVALID failure phase does not match retained READY evidence"
            )
        _validate_phase_object(
            invalid,
            attempt,
            phase=failure_phase,
            status="INVALID",
            previous_receipt_digest=previous,
            required_extra_keys={"reason_code"},
        )
        _validate_reason_code(invalid, "post_started")
        return {
            "authorization_digest": attempt["authorization_digest"],
            "output_path": os.fspath(layout.output_path),
            "status": "INVALID",
            "terminal_digest": invalid["deterministic_digest"],
        }

    if not has_commit:
        raise RegularFilePublicationV2AmbiguousError(
            "attempt is non-terminal and cannot be recovered or retried"
        )

    _assert_name_absent(parent, layout.not_run_name)
    _assert_name_absent(parent, layout.invalid_name)
    records_raw, manifest = _validate_records_and_manifest(
        parent,
        layout,
        attempt,
        started,
    )
    ready = _read_canonical_object_at(parent, layout.ready_name)
    _validate_phase_object(
        ready,
        attempt,
        phase="READY_TO_COMMIT",
        status="PENDING",
        previous_receipt_digest=started_digest,
        required_extra_keys={
            "manifest_digest",
            "manifest_sha256",
            "records_byte_count",
            "records_sha256",
        },
    )
    if (
        ready.get("manifest_digest") != manifest.get("deterministic_digest")
        or ready.get("manifest_sha256")
        != _sha256_bytes(_canonical_bytes(manifest))
        or type(ready.get("records_byte_count")) is not int
        or ready.get("records_byte_count") != len(records_raw)
        or ready.get("records_sha256") != _sha256_bytes(records_raw)
    ):
        raise RegularFilePublicationV2AmbiguousError(
            "READY receipt does not close over data sidecars"
        )
    commit = _read_canonical_object_at(parent, layout.commit_name)
    expected_commit = _commit_payload(
        layout,
        attempt,
        started,
        ready,
        manifest,
        records_raw,
    )
    if commit != expected_commit:
        raise RegularFilePublicationV2AmbiguousError(
            "commit receipt does not close over the exact collective"
        )
    return {
        "artifact_commit_digest": commit["deterministic_digest"],
        "authorization_digest": attempt["authorization_digest"],
        "output_path": os.fspath(layout.output_path),
        "run_manifest_digest": manifest["deterministic_digest"],
        "status": "COMMITTED",
        "terminal_digest": commit["deterministic_digest"],
    }


def _terminal_forward_sync_names(
    parent: _PinnedParent,
    layout: RegularFileLayoutV2,
    result: Mapping[str, Any],
) -> tuple[str, ...]:
    status = result.get("status")
    if status == "UNRESERVED":
        return ()
    if status == "NOT_RUN":
        return (layout.attempt_name, layout.not_run_name)
    if status == "INVALID":
        names = [layout.attempt_name, layout.started_name]
        if _name_exists(parent, layout.ready_name):
            names.extend(
                (layout.records_name, layout.manifest_name, layout.ready_name)
            )
        names.append(layout.invalid_name)
        return tuple(names)
    if status == "COMMITTED":
        return (
            layout.attempt_name,
            layout.started_name,
            layout.records_name,
            layout.manifest_name,
            layout.ready_name,
            layout.commit_name,
        )
    raise RegularFilePublicationV2AmbiguousError(
        "validated publication has no known terminal durability state"
    )


def _inspect_once(
    parent: _PinnedParent,
    layout: RegularFileLayoutV2,
    expected_authorization_digest: str | None,
) -> tuple[
    dict[str, Any],
    tuple[tuple[int, ...], tuple[tuple[str, tuple[int, ...] | None], ...]],
]:
    parent.assert_path()
    _assert_no_legacy_namespace(parent)
    before_parent = _parent_generation(parent)
    before_reserved = _reserved_generation(parent, layout.reserved_names)
    result = _inspect_payload_once(parent, layout, expected_authorization_digest)
    sync_names = _terminal_forward_sync_names(parent, layout, result)
    for name in sync_names:
        _forward_sync_exact_regular_file_at(parent, name)
    if sync_names:
        parent.fsync()
    _assert_no_legacy_namespace(parent)
    after_reserved = _reserved_generation(parent, layout.reserved_names)
    after_parent = _parent_generation(parent)
    parent.assert_path()
    if before_parent != after_parent or before_reserved != after_reserved:
        raise RegularFilePublicationV2AmbiguousError(
            "terminal collective generation changed during validation"
        )
    return result, (before_parent, before_reserved)


def inspect_synthetic_publication_v2(
    output_path: Path | str,
    *,
    authorization_digest: str | None = None,
) -> dict[str, Any]:
    """Validate and forward-sync one exact terminal synthetic v2 collective."""

    _require_posix_capabilities()
    layout = RegularFileLayoutV2.from_output_path(output_path)
    expected_authorization = (
        None
        if authorization_digest is None
        else _require_sha256(authorization_digest, "authorization digest")
    )
    parent = _PinnedParent.open(layout.output_path.parent)
    try:
        _validate_layout_against_parent(parent, layout)
        first, first_generation = _inspect_once(
            parent,
            layout,
            expected_authorization,
        )
        parent.assert_path()
        second, second_generation = _inspect_once(
            parent,
            layout,
            expected_authorization,
        )
        parent.assert_path()
        if first != second or first_generation != second_generation:
            raise RegularFilePublicationV2AmbiguousError(
                "terminal collective changed between validation snapshots"
            )
        return first
    finally:
        parent.close()


def _run_self_test() -> None:
    authorization = "4" * 64
    with tempfile.TemporaryDirectory(prefix="qmc-bmgs-v2-self-test-") as raw:
        # macOS exposes /var as a symlink to /private/var.  Resolve only the
        # self-test's newly allocated directory so the protocol itself can
        # continue to reject symlink-traversing authority paths.
        output = Path(raw).resolve() / "fixture.commit.json"
        calls = 0

        def fixture() -> list[dict[str, Any]]:
            nonlocal calls
            calls += 1
            return [{"candidate": "alpha", "score": 1}, {"candidate": "beta"}]

        result = publish_synthetic_fixture_v2(
            output,
            authorization_digest=authorization,
            fixture_action=fixture,
        )
        if result["status"] != "COMMITTED" or calls != 1:
            raise AssertionError("synthetic v2 publication did not commit exactly once")
        inspected = inspect_synthetic_publication_v2(
            output,
            authorization_digest=authorization,
        )
        if inspected["status"] != "COMMITTED":
            raise AssertionError("synthetic v2 collective did not verify")
        try:
            publish_synthetic_fixture_v2(
                output,
                authorization_digest="5" * 64,
                fixture_action=fixture,
            )
        except RegularFilePublicationV2NotRunError:
            pass
        else:
            raise AssertionError("output-global reservation was reusable")
        if calls != 1:
            raise AssertionError("losing reservation crossed the outcome boundary")
    print("countdown Thompson regular-file publication v2 self-test: PASS")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run synthetic publication mechanics only",
    )
    args = parser.parse_args(argv)
    if not args.self_test:
        parser.error("only --self-test is available; production remains fail-closed")
    _run_self_test()


if __name__ == "__main__":
    main()
