"""Source-checkout, one-shot execution for the sealed dense-scale experiment.

Planning is not execution authority.  The full-shaped fixture uses a different
external authorization and never loads a development bundle.  No public mode
selects a scale or emits a scientific decision.
"""

from __future__ import annotations

import argparse
import os
import re
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

from qmc_bmgs.experiments import countdown_thompson_dense_scale_core as core
from qmc_bmgs.experiments import (
    countdown_thompson_dense_scale_publication as publication,
)


CONTRACT_MERGE_REVISION = "3e486c6c196ff6a296e5692555a8e3a885713b18"
AUTHORIZATION_SCHEMA = (
    "qmc-bmgs-countdown-thompson-dense-scale-execution-authorization/v1"
)
FIXTURE_AUTHORIZATION_SCHEMA = (
    "qmc-bmgs-countdown-thompson-dense-scale-nondiagnostic-full-shape-"
    "execution-authorization/v1"
)
AUTHORIZATION_SCOPE = "one_exact_complete_384_cell_dense_scale_development_run"
FIXTURE_AUTHORIZATION_SCOPE = (
    "one_exact_nondiagnostic_dense_scale_full_shape_384_cell_fixture"
)
FIXTURE_BUNDLE_ID = "countdown_thompson_dense_scale_nondiagnostic_full_shape_384/v1"
CLAIM_BOUNDARY = core.CLAIM_BOUNDARY
FIXTURE_CLAIM_BOUNDARY = core.FIXTURE_CLAIM_BOUNDARY
ENVIRONMENT_SCHEMA = (
    "qmc-bmgs-countdown-thompson-dense-scale-publication-environment-requirements/v1"
)
AUTHORIZATION_FIELDS = frozenset(
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
FIXTURE_AUTHORIZATION_FIELDS = AUTHORIZATION_FIELDS | {"fixture_design_digest"}
_BUILD_FIELDS = frozenset(
    "schema_version runner_revision source_files search_build_digest "
    "runtime_import_policy deterministic_digest".split()
)
_MANIFEST_FIELDS = {
    "analysis_manifest_digest": "analysis",
    "budget_manifest_digest": "budget",
    "method_manifest_digest": "methods",
    "proposal_manifest_digest": "proposal",
    "runtime_binding_digest": "runtime_binding",
}


class DenseRunnerError(core.DenseScaleExecutionError):
    """A refusal that has not entered the publisher's attempt state machine."""

    status = "NOT_RUN"
    authorization_consumed = False


class AuthorizationPublicationAmbiguous(DenseRunnerError):
    """A created candidate cannot be proved durable and exact; retain it."""

    status = "PUBLICATION_STATE_AMBIGUOUS"
    authorization_consumed = None


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DenseRunnerError(message)


def _oid(value: object, label: str) -> str:
    _require(
        type(value) is str and re.fullmatch("[0-9a-f]{40}", value) is not None,
        f"{label} must be one full lowercase commit OID",
    )
    return value  # type: ignore[return-value]


def _same(left: object, right: object, label: str) -> None:
    _require(core.canonical_bytes(left) == core.canonical_bytes(right), label)


def _digest_object(value: object, label: str, fields: object = None) -> dict[str, Any]:
    _require(type(value) is dict, f"{label} must be a plain object")
    if fields is not None:
        _require(set(value) == fields, f"{label} fields are not closed")
    observed = value.get("deterministic_digest")
    core.require_sha256(observed, label)
    expected = core.with_digest(
        {key: item for key, item in value.items() if key != "deterministic_digest"}
    )
    _same(value, expected, f"{label} digest does not close")
    return value


def _absolute_path(value: Path | str, *, root: Path | None = None) -> Path:
    raw = os.fspath(value)
    _require(type(raw) is str and bool(raw), "path must be nonempty text")
    _require(
        raw == os.path.normpath(raw), "path must use its exact normalized spelling"
    )
    if not os.path.isabs(raw):
        _require(root is not None, "path must be absolute")
        raw = os.fspath(root / raw)
    _require(raw != "/", "path must name a file, not root")
    try:
        os.fsencode(raw)
    except UnicodeError as error:
        raise DenseRunnerError("path is not filesystem-encodable") from error
    return Path(raw)


def _output_path(value: Path | str, root: Path | None = None) -> Path:
    result = _absolute_path(value)
    _require(result.name.isascii(), "output basename must be ASCII")
    _require(
        not result.name.lower().startswith(".qmc-bmgs-"),
        "output basename is in the reserved namespace",
    )
    if root is not None:
        _require(
            not result.is_relative_to(root), "output must be outside the repository"
        )
    return result


def publication_environment_requirements(binding: dict[str, Any]) -> dict[str, Any]:
    """Requirements to qualify in the separate host/filesystem review."""
    return core.with_digest(
        {
            "schema_version": ENVIRONMENT_SCHEMA,
            "publication_backend": "posix_regular_files/v2r3",
            "artifact_layout": "flat_commit_root/v2r3",
            "binding_scope": "same_host_same_filesystem_identity_epoch",
            "output_parent_binding_digest": binding["deterministic_digest"],
            "required_mechanics": [
                "absolute_normalized_ascii_commit_path/v1",
                "componentwise_o_nofollow_parent_identity/v1",
                "descriptor_relative_o_creat_o_excl_regular_files/v1",
                "regular_file_and_directory_fsync/v1",
                "stable_st_dev_st_ino_within_identity_epoch/v1",
                "superseded_publishers_quiescent/v1",
            ],
            "claim_boundary": (
                "Review must qualify local POSIX mechanics on this host/filesystem "
                "identity epoch; no NFS, SMB, FUSE, reboot, cross-host, mount-namespace, "
                "device/inode ABA, malicious-kernel, or untrusted same-UID guarantee."
            ),
        }
    )


def _manifest_digests(inputs: Any) -> dict[str, str]:
    payload = inputs.payload
    return {
        field: payload[key]["deterministic_digest"]
        for field, key in _MANIFEST_FIELDS.items()
    }


def _validate_build(value: object) -> dict[str, Any]:
    build = _digest_object(value, "runner build", _BUILD_FIELDS)
    _require(
        build["schema_version"] == core.BUILD_SCHEMA_VERSION,
        "runner build schema drifted",
    )
    _oid(build["runner_revision"], "runner revision")
    sources = build["source_files"]
    _require(
        type(sources) is dict and set(sources) == set(core.PROTECTED_SOURCE_PATHS),
        "protected source receipt set is not closed",
    )
    for receipt in sources.values():
        _require(
            type(receipt) is dict and set(receipt) == {"byte_count", "sha256"},
            "source receipt fields are not closed",
        )
        _require(
            type(receipt["byte_count"]) is int
            and 0 <= receipt["byte_count"] <= 8 * 1024 * 1024,
            "source receipt byte count is not a bounded integer",
        )
        core.require_sha256(receipt["sha256"], "source receipt SHA-256")
    expected_search = core.with_digest(
        {path: sources[path] for path in core.SEARCH_SOURCE_PATHS}
    )["deterministic_digest"]
    _require(
        build["search_build_digest"] == expected_search, "search source digest drifted"
    )
    _same(
        build["runtime_import_policy"],
        {
            "bytecode_cache_prefix_empty": True,
            "bytecode_cache_prefix_mode": "0700",
            "bytecode_cache_prefix_owner": "effective_user",
            "bytecode_writes_disabled": True,
            "import_safe_path": True,
            "loader_policy": "exact_source_file_loader_no_cache/v1",
        },
        "source-loading policy drifted",
    )
    return build


def _validate_runtime(value: object) -> dict[str, Any]:
    runtime = _digest_object(
        value,
        "runtime qualification",
        {
            "schema_version",
            "search_runtime",
            "iid_runtime",
            "sobol_runtime",
            "host",
            "provider_calls",
            "deterministic_digest",
        },
    )
    _require(
        runtime["schema_version"] == core.RUNTIME_SCHEMA_VERSION,
        "runtime qualification schema drifted",
    )
    _require(
        type(runtime["provider_calls"]) is int and runtime["provider_calls"] == 0,
        "runtime qualification provider calls must be zero",
    )
    public = core.public_contract()["runtime_binding"]
    _same(
        runtime["search_runtime"],
        public["search_runtime"]["metadata"],
        "sealed search runtime drifted",
    )
    _same(
        runtime["iid_runtime"],
        public["iid_runtime"]["metadata"],
        "sealed IID runtime drifted",
    )
    host = runtime["host"]
    _require(
        type(host) is dict
        and set(host) == {"architecture", "node", "platform", "python_version"},
        "runtime host receipt fields are not closed",
    )
    _require(
        all(type(item) is str and bool(item) for item in host.values()),
        "runtime host receipt values must be nonempty text",
    )
    _require(
        host["architecture"] == "arm64" and host["python_version"] == "3.13.13",
        "runtime host does not match the frozen architecture/Python",
    )
    sobol = runtime["sobol_runtime"]
    iid = runtime["iid_runtime"]
    common = set(iid) - {"iid_counter_hash", "iid_open_unit_bits"}
    _require(
        type(sobol) is dict
        and set(sobol)
        == common
        | {
            "sobol_maxbit",
            "sobol_maxdim",
            "sobol_randomization",
        },
        "Sobol runtime receipt fields are not closed",
    )
    for field in common - {"generator_version", "runtime_conformance_digest", "source"}:
        _same(sobol[field], iid[field], f"Sobol runtime {field} drifted")
    _require(sobol["source"] == "sobol", "qualification source must be Sobol")
    for field in ("generator_version", "sobol_randomization"):
        _require(
            type(sobol[field]) is str and bool(sobol[field]), f"invalid Sobol {field}"
        )
    for field in ("sobol_maxbit", "sobol_maxdim"):
        _require(
            type(sobol[field]) is int and sobol[field] > 0, f"invalid Sobol {field}"
        )
    core.require_sha256(sobol["runtime_conformance_digest"], "Sobol conformance digest")
    return runtime


def validate_authorization(raw: bytes, *, fixture: bool = False) -> dict[str, Any]:
    """Validate closed public authority without opening bundle/output paths.

    Full source/runtime nested receipts are subsequently compared byte-for-byte
    with independently reconstructed receipts by ``load_reviewed_authorization``.
    """
    _require(type(fixture) is bool, "fixture selector must be a plain boolean")
    payload = core.parse_canonical(raw)
    fields = FIXTURE_AUTHORIZATION_FIELDS if fixture else AUTHORIZATION_FIELDS
    _digest_object(payload, "authorization", fields)
    _require(
        payload["schema_version"]
        == (FIXTURE_AUTHORIZATION_SCHEMA if fixture else AUTHORIZATION_SCHEMA),
        "authorization schema/domain mismatch",
    )
    _require(
        payload["authorization_scope"]
        == (FIXTURE_AUTHORIZATION_SCOPE if fixture else AUTHORIZATION_SCOPE),
        "authorization scope/domain mismatch",
    )
    _require(
        payload["claim_boundary"]
        == (FIXTURE_CLAIM_BOUNDARY if fixture else CLAIM_BOUNDARY),
        "authorization claim boundary drifted",
    )
    _require(
        type(payload["cell_count"]) is int and payload["cell_count"] == 384,
        "authorization must close exactly 384 cells",
    )
    _require(
        payload["requires_explicit_digest_confirmation"] is True,
        "explicit digest confirmation is required",
    )
    _require(
        payload["publication_backend"] == "posix_regular_files/v2r3",
        "publication backend drifted",
    )
    _require(
        payload["artifact_layout"] == "flat_commit_root/v2r3", "artifact layout drifted"
    )
    output = _output_path(payload["output_path"])
    _require(
        payload["output_path_digest"] == core.sha256_bytes(os.fsencode(output)),
        "output lexical byte digest drifted",
    )
    binding = publication.freeze_dense_parent_binding(
        output, payload["output_parent_binding"]
    )
    _same(binding, payload["output_parent_binding"], "parent binding bytes drifted")
    _require(
        payload["output_parent_binding_digest"] == binding["deterministic_digest"],
        "parent binding digest drifted",
    )
    _same(
        payload["publication_environment_requirements"],
        publication_environment_requirements(binding),
        "environment requirements drifted",
    )
    qualification = core.anchor_qualification()
    _same(
        payload["anchor_qualification"], qualification, "public qualification drifted"
    )
    _require(
        payload["anchor_qualification_digest"] == qualification["deterministic_digest"],
        "public qualification digest drifted",
    )
    _validate_build(payload["runner_build_attestation"])
    runtime = _validate_runtime(payload["runtime_qualification"])
    _require(
        payload["runtime_qualification_digest"] == runtime["deterministic_digest"],
        "runtime qualification digest drifted",
    )
    core.require_sha256(payload["artifact_id"], "artifact id")
    if fixture:
        expected = core.public_fixture_inputs()
        _require(payload["bundle_id"] == FIXTURE_BUNDLE_ID, "fixture bundle id drifted")
        _require(
            payload["dense_scale_seal_digest"] is None,
            "fixture must not carry a production seal",
        )
        _require(
            payload["preregistration_file_sha256"] is None,
            "fixture must not carry production preregistration bytes",
        )
        _require(
            payload["fixture_design_digest"] == expected.design_digest,
            "fixture design digest drifted",
        )
        _require(
            payload["schedule_digest"] == expected.schedule_digest,
            "fixture schedule digest drifted",
        )
        for field, digest in _manifest_digests(expected).items():
            _require(payload[field] == digest, f"fixture {field} drifted")
    else:
        for field in (
            "bundle_id",
            "dense_scale_seal_digest",
            "preregistration_file_sha256",
            "schedule_digest",
            *_MANIFEST_FIELDS,
        ):
            _require(
                payload[field] == core.FROZEN_AUTHORITY[field],
                f"frozen authority {field} drifted",
            )
    return payload


def _git_regular_blob(root: Path, revision: str, relative: str) -> None:
    listing = core.git_bytes(root, "ls-tree", "-z", revision, "--", relative)
    parts = listing.split(b"\t", 1)
    _require(
        len(parts) == 2 and parts[1] == os.fsencode(relative) + b"\0",
        "authorization must be one exact tracked blob",
    )
    metadata = parts[0].split()
    _require(
        len(metadata) == 3 and metadata[:2] == [b"100644", b"blob"],
        "authorization must be a non-executable regular Git blob",
    )


def _authorization_path(value: Path | str, root: Path, *, fixture: bool) -> Path:
    result = _absolute_path(value, root=root)
    _require(
        result.is_relative_to(root) is not fixture,
        "fixture authorization must be outside Git; production authorization must be inside",
    )
    if not fixture:
        _require(
            not result.is_relative_to(
                root / "docs/preregistrations/countdown_thompson_dense_scale_v5"
            ),
            "authorization candidate must not alter the sealed bundle",
        )
    return result


def _verify_reviewed_bytes(
    *,
    root: Path,
    path: Path,
    raw: bytes,
    payload: dict[str, Any],
    authorization_revision: str,
    fixture: bool,
) -> str:
    runner_revision = _oid(
        payload["runner_build_attestation"]["runner_revision"], "runner revision"
    )
    reviewed = _oid(authorization_revision, "authorization revision")
    head = _oid(core.git_head(root), "execution HEAD")
    core.require_ancestor(root, CONTRACT_MERGE_REVISION, runner_revision)
    if fixture:
        _require(
            reviewed == runner_revision,
            "fixture review revision is exactly the authorized source-review epoch",
        )
        core.require_ancestor(root, reviewed, head)
    else:
        core.require_ancestor(root, runner_revision, reviewed, strict=True)
        core.require_ancestor(root, reviewed, head)
        relative = path.relative_to(root).as_posix()
        delta = core.git_bytes(
            root,
            "diff",
            "--name-status",
            "-z",
            "--no-renames",
            runner_revision,
            reviewed,
            "--",
        )
        _require(
            delta == b"A\0" + os.fsencode(relative) + b"\0",
            "authorization review must add only the single new candidate file",
        )
        for revision in (reviewed, head):
            _git_regular_blob(root, revision, relative)
            _require(
                core.git_bytes(root, "show", f"{revision}:{relative}") == raw,
                "authorization bytes differ from reviewed revision or execution HEAD",
            )
    expected_build = core.source_attestation(root, authorized_revision=runner_revision)
    _same(
        payload["runner_build_attestation"],
        expected_build,
        "reviewed source/build receipt does not match the clean checkout",
    )
    _same(
        payload["runtime_qualification"],
        core.runtime_qualification(),
        "live runtime does not reproduce the reviewed runtime receipt",
    )
    return head


@dataclass(frozen=True)
class ReviewedAuthorization:
    """Stable external authority; embedded artifact copies never replace it."""

    raw: bytes
    snapshot: Any
    path: Path
    repository_root: Path
    authorization_revision: str
    execution_head: str
    fixture: bool

    @property
    def payload(self) -> dict[str, Any]:
        return core.parse_canonical(self.raw)

    def revalidate(self) -> None:
        self.snapshot.revalidate()
        payload = validate_authorization(self.raw, fixture=self.fixture)
        head = _verify_reviewed_bytes(
            root=self.repository_root,
            path=self.path,
            raw=self.raw,
            payload=payload,
            authorization_revision=self.authorization_revision,
            fixture=self.fixture,
        )
        _require(
            head == self.execution_head, "execution HEAD changed during the attempt"
        )
        self.snapshot.revalidate()


def load_reviewed_authorization(
    authorization_file: Path | str,
    *,
    authorization_digest: str,
    authorization_revision: str,
    repository_root: Path,
    output_path: Path | str | None = None,
    fixture: bool = False,
) -> ReviewedAuthorization:
    """Independently load exact external authority, without bundle/output access."""
    core.require_sha256(authorization_digest, "confirmed authorization digest")
    _oid(authorization_revision, "authorization revision")
    root = Path(repository_root).resolve()
    path = _authorization_path(authorization_file, root, fixture=fixture)
    snapshot = core.FileSnapshot.capture(path)
    raw = snapshot.raw
    payload = validate_authorization(raw, fixture=fixture)
    _require(
        payload["deterministic_digest"] == authorization_digest,
        "explicit authorization digest does not match the external file",
    )
    output = _output_path(payload["output_path"], root)
    if output_path is not None:
        _require(
            os.fspath(_output_path(output_path, root)) == os.fspath(output),
            "explicit output path differs from reviewed authority",
        )
    _require(
        not path.is_relative_to(output.parent),
        "external authorization must be outside the output-parent subtree",
    )
    head = _verify_reviewed_bytes(
        root=root,
        path=path,
        raw=raw,
        payload=payload,
        authorization_revision=authorization_revision,
        fixture=fixture,
    )
    snapshot.revalidate()
    return ReviewedAuthorization(
        raw, snapshot, path, root, authorization_revision, head, fixture
    )


def _open_parent(path: Path) -> tuple[int, tuple[tuple[int, int], ...]]:
    """Walk a canonical absolute directory through no-follow descriptors."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    descriptor = os.open("/", flags)
    identities: list[tuple[int, int]] = []
    try:
        observed = os.fstat(descriptor)
        identities.append((observed.st_dev, observed.st_ino))
        for component in path.parts[1:]:
            child = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
            observed = os.fstat(descriptor)
            _require(
                stat.S_ISDIR(observed.st_mode),
                "authorization parent is not a directory",
            )
            identities.append((observed.st_dev, observed.st_ino))
        return descriptor, tuple(identities)
    except BaseException:
        os.close(descriptor)
        raise


def _file_generation(observed: os.stat_result) -> tuple[int, ...]:
    return (
        observed.st_dev,
        observed.st_ino,
        observed.st_mode,
        observed.st_nlink,
        observed.st_uid,
        observed.st_gid,
        observed.st_size,
        observed.st_mtime_ns,
        observed.st_ctime_ns,
    )


def write_authorization_exclusive(path: Path | str, raw: bytes) -> None:
    """Durably create one exact authority file; never adopt, remove, or retry it.

    Any uncertainty after exclusive creation retains the slot and is AMBIGUOUS.
    The caller decides whether these bytes are production or fixture authority.
    """
    destination = _absolute_path(path)
    _require(
        type(raw) is bytes and len(raw) <= 8 * 1024 * 1024,
        "authorization bytes exceed the fixed bound",
    )
    core.parse_canonical(raw)
    parent_fd = file_fd = -1
    created = False
    try:
        parent_fd, chain = _open_parent(destination.parent)
        file_fd = os.open(
            destination.name,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
            dir_fd=parent_fd,
        )
        created = True
        initial = os.fstat(file_fd)
        _require(
            stat.S_ISREG(initial.st_mode)
            and initial.st_size == 0
            and initial.st_nlink == 1
            and initial.st_uid == os.geteuid(),
            "new authorization descriptor has unexpected identity",
        )
        identity = (initial.st_dev, initial.st_ino)
        os.fchmod(file_fd, 0o600)
        offset = 0
        while offset < len(raw):
            written = os.write(file_fd, raw[offset:])
            _require(
                type(written) is int and written > 0,
                "authorization short write made no progress",
            )
            offset += written
        before = _file_generation(os.fstat(file_fd))
        os.fsync(file_fd)
        _require(
            _file_generation(os.fstat(file_fd)) == before,
            "authorization generation changed across file durability",
        )
        os.fsync(parent_fd)
        _require(
            _file_generation(os.fstat(file_fd)) == before,
            "authorization generation changed across parent durability",
        )
        observed = os.stat(destination.name, dir_fd=parent_fd, follow_symlinks=False)
        _require(
            _file_generation(observed) == before
            and (observed.st_dev, observed.st_ino) == identity
            and observed.st_nlink == 1
            and observed.st_uid == os.geteuid()
            and stat.S_IMODE(observed.st_mode) == 0o600,
            "authorization name no longer denotes the exact owned regular file",
        )
        os.lseek(file_fd, 0, os.SEEK_SET)
        chunks: list[bytes] = []
        remaining = len(raw) + 1
        while remaining:
            chunk = os.read(file_fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        _require(b"".join(chunks) == raw, "authorization descriptor bytes changed")
        _require(
            _file_generation(os.fstat(file_fd)) == before,
            "authorization changed during readback",
        )
        observed_fd, observed_chain = _open_parent(destination.parent)
        try:
            _require(
                observed_chain == chain, "authorization lexical parent identity changed"
            )
            _require(
                (os.fstat(parent_fd).st_dev, os.fstat(parent_fd).st_ino) == chain[-1],
                "authorization retained parent identity changed",
            )
        finally:
            os.close(observed_fd)
        _require(
            _file_generation(os.fstat(file_fd)) == before
            and _file_generation(
                os.stat(destination.name, dir_fd=parent_fd, follow_symlinks=False)
            )
            == before,
            "authorization name or descriptor changed at final proof",
        )
    except BaseException as error:
        if created:
            raise AuthorizationPublicationAmbiguous(
                "authorization publication is uncertain; retained file is not usable authority"
            ) from error
        if isinstance(error, DenseRunnerError):
            raise
        raise DenseRunnerError(
            "authorization destination cannot be exclusively created"
        ) from error
    finally:
        close_error = None
        for descriptor in (file_fd, parent_fd):
            if descriptor >= 0:
                try:
                    os.close(descriptor)
                except OSError as error:
                    close_error = error
        if close_error is not None:
            if created:
                raise AuthorizationPublicationAmbiguous(
                    "authorization descriptor closure is uncertain; retain the slot"
                ) from close_error
            raise DenseRunnerError(
                "authorization parent could not be closed"
            ) from close_error


def _authorization_payload(
    inputs: Any,
    output: Path,
    binding: dict[str, Any],
    build: dict[str, Any],
    qualification: dict[str, Any],
    runtime: dict[str, Any],
) -> dict[str, Any]:
    fixture = inputs.fixture
    scope = FIXTURE_AUTHORIZATION_SCOPE if fixture else AUTHORIZATION_SCOPE
    path_digest = core.sha256_bytes(os.fsencode(output))
    artifact_identity = core.with_digest(
        {
            "authorization_scope": scope,
            "bundle_id": inputs.bundle_id,
            "output_path_digest": path_digest,
            "schedule_digest": inputs.schedule_digest,
            "runner_build_digest": build["deterministic_digest"],
        }
    )
    payload = {
        **_manifest_digests(inputs),
        "schema_version": FIXTURE_AUTHORIZATION_SCHEMA
        if fixture
        else AUTHORIZATION_SCHEMA,
        "authorization_scope": scope,
        "claim_boundary": FIXTURE_CLAIM_BOUNDARY if fixture else CLAIM_BOUNDARY,
        "bundle_id": inputs.bundle_id,
        "cell_count": 384,
        "artifact_id": artifact_identity["deterministic_digest"],
        "artifact_layout": "flat_commit_root/v2r3",
        "publication_backend": "posix_regular_files/v2r3",
        "dense_scale_seal_digest": None if fixture else inputs.seal_digest,
        "preregistration_file_sha256": None
        if fixture
        else core.FROZEN_AUTHORITY["preregistration_file_sha256"],
        "schedule_digest": inputs.schedule_digest,
        "output_path": os.fspath(output),
        "output_path_digest": path_digest,
        "output_parent_binding": binding,
        "output_parent_binding_digest": binding["deterministic_digest"],
        "publication_environment_requirements": publication_environment_requirements(
            binding
        ),
        "requires_explicit_digest_confirmation": True,
        "runner_build_attestation": build,
        "anchor_qualification": qualification,
        "anchor_qualification_digest": qualification["deterministic_digest"],
        "runtime_qualification": runtime,
        "runtime_qualification_digest": runtime["deterministic_digest"],
    }
    if fixture:
        payload["fixture_design_digest"] = inputs.design_digest
    result = core.with_digest(payload)
    validate_authorization(core.canonical_bytes(result), fixture=fixture)
    return result


def plan_execution(
    bundle_path: Path | str,
    output_path: Path | str,
    authorization_out: Path | str,
    *,
    repository_root: Path,
) -> dict[str, Any]:
    """Planning only; never called by validation or fixture execution."""
    root = Path(repository_root).resolve()
    output = _output_path(output_path, root)
    destination = _authorization_path(authorization_out, root, fixture=False)
    bundle = _absolute_path(bundle_path, root=root)
    _require(
        not destination.is_relative_to(output.parent),
        "authorization must be outside the output-parent subtree",
    )
    _require(
        not destination.is_relative_to(bundle),
        "candidate must be outside the sealed bundle",
    )
    build = core.source_attestation(root)
    core.require_ancestor(root, CONTRACT_MERGE_REVISION, build["runner_revision"])
    binding = publication.capture_dense_parent_binding(output)
    publication.preflight_dense_parent_binding(output, binding)
    qualification = core.reproduce_anchor_qualification()
    runtime = core.runtime_qualification()
    inputs = core.load_production_inputs(bundle, root)
    payload = _authorization_payload(
        inputs, output, binding, build, qualification, runtime
    )
    inputs.revalidate()
    _same(
        build, core.source_attestation(root), "source changed during planning preflight"
    )
    publication.preflight_dense_parent_binding(output, binding)
    write_authorization_exclusive(destination, core.canonical_bytes(payload))
    return {
        "status": "PREOUTCOME_AUTHORIZATION_CANDIDATE_WRITTEN",
        "authorization_path": os.fspath(destination),
        "authorization_digest": payload["deterministic_digest"],
        "artifact_id": payload["artifact_id"],
        "cell_count": 384,
        "claim_boundary": "Planning only; zero development cells executed.",
    }


def _publication_inputs(authority: ReviewedAuthorization, inputs: Any) -> Any:
    factory = (
        publication.make_dense_fixture_publication_inputs
        if authority.fixture
        else publication.make_dense_publication_inputs
    )
    return factory(
        authorization_raw=authority.raw,
        schedule_raw=core.canonical_bytes(inputs.schedule),
        task_sources_raw=core.canonical_bytes(inputs.task_sources),
        reviewed_authorization_revision=authority.authorization_revision,
        execution_head_revision=authority.execution_head,
    )


def _execute(
    authority: ReviewedAuthorization,
    inputs: Any,
    *,
    _event_hook: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    _require(inputs.fixture is authority.fixture, "execution input domain mismatch")
    if authority.fixture:
        _require(
            authority.authorization_revision == authority.execution_head,
            "fixture execution requires its exact source-review epoch",
        )
    payload = authority.payload
    _require(
        inputs.bundle_id == payload["bundle_id"]
        and inputs.schedule_digest == payload["schedule_digest"],
        "bundle/schedule differs from reviewed authority",
    )
    for field, value in _manifest_digests(inputs).items():
        _require(payload[field] == value, f"execution {field} drifted")
    frozen = _publication_inputs(authority, inputs)

    def recheck() -> None:
        authority.revalidate()
        inputs.revalidate()
        _same(
            core.reproduce_anchor_qualification(),
            payload["anchor_qualification"],
            "public qualification changed at an execution barrier",
        )
        publication.revalidate_dense_parent_binding(
            payload["output_path"], payload["output_parent_binding"]
        )

    def action(context: Any) -> Any:
        binding = context.run_binding
        records = tuple(
            core.build_record(inputs, cell, binding) for cell in inputs.cells
        )
        return publication.DensePublicationBatchV2R3(records=records)

    publisher = (
        publication.publish_dense_scale_fixture_v2r3
        if authority.fixture
        else publication.publish_dense_scale_v2r3
    )
    return publisher(
        payload["output_path"],
        inputs=frozen,
        action=action,
        pre_started_check=recheck,
        pre_commit_check=recheck,
        _event_hook=_event_hook,
    )


def run_execution(
    bundle_path: Path | str,
    output_path: Path | str,
    *,
    authorization_file: Path | str,
    authorization_digest: str,
    authorization_revision: str,
    repository_root: Path,
) -> dict[str, Any]:
    authority = load_reviewed_authorization(
        authorization_file,
        authorization_digest=authorization_digest,
        authorization_revision=authorization_revision,
        repository_root=repository_root,
        output_path=output_path,
    )
    root = Path(repository_root).resolve()
    inputs = core.load_production_inputs(_absolute_path(bundle_path, root=root), root)
    return _execute(authority, inputs)


def run_full_shape_fixture(
    output_path: Path | str,
    authorization_out: Path | str,
    *,
    repository_root: Path,
    _event_hook: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Authorize and run only the public fixture, with external immutable bytes.

    The fixture review revision is the source-review epoch, not a merged Git
    authorization.  This branch cannot manufacture production authority.
    """
    root = Path(repository_root).resolve()
    output = _output_path(output_path, root)
    destination = _authorization_path(authorization_out, root, fixture=True)
    _require(
        not destination.is_relative_to(output.parent),
        "fixture authorization must be outside the output-parent subtree",
    )
    inputs = core.public_fixture_inputs()
    build = core.source_attestation(root)
    core.require_ancestor(root, CONTRACT_MERGE_REVISION, build["runner_revision"])
    binding = publication.capture_dense_parent_binding(output)
    publication.preflight_dense_parent_binding(output, binding)
    qualification = core.reproduce_anchor_qualification()
    runtime = core.runtime_qualification()
    payload = _authorization_payload(
        inputs, output, binding, build, qualification, runtime
    )
    inputs.revalidate()
    _same(
        build, core.source_attestation(root), "source changed during fixture preflight"
    )
    publication.preflight_dense_parent_binding(output, binding)
    write_authorization_exclusive(destination, core.canonical_bytes(payload))
    authority = load_reviewed_authorization(
        destination,
        authorization_digest=payload["deterministic_digest"],
        authorization_revision=build["runner_revision"],
        repository_root=root,
        output_path=output,
        fixture=True,
    )
    result = _execute(authority, inputs, _event_hook=_event_hook)
    return {
        **result,
        "authorization_file": os.fspath(destination),
        "authorization_digest": payload["deterministic_digest"],
        "authorization_revision": build["runner_revision"],
        "claim_boundary": FIXTURE_CLAIM_BOUNDARY,
    }


def self_test() -> dict[str, Any]:
    """Small public-only contract checks; no sealed input or search is opened."""
    _require(
        len(AUTHORIZATION_FIELDS) == 28 and len(FIXTURE_AUTHORIZATION_FIELDS) == 29,
        "authorization field set drifted",
    )
    for fixture in (False, True):
        try:
            validate_authorization(
                core.canonical_bytes(core.with_digest({"schema_version": "foreign"})),
                fixture=fixture,
            )
        except (core.DenseScaleExecutionError, ValueError, TypeError):
            continue
        raise DenseRunnerError("foreign authorization was accepted")
    return {
        "status": "PASS",
        "checks": 3,
        "provider_calls": 0,
        "development_cells_executed": 0,
        "claim_boundary": "Public-only runner self-test, not execution authority.",
    }


class _CanonicalArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise DenseRunnerError(f"invalid arguments: {message}")


def main(argv: Sequence[str] | None = None) -> int:
    execution_dispatched = False
    try:
        parser = _CanonicalArgumentParser(description=__doc__)
        modes = parser.add_mutually_exclusive_group(required=True)
        modes.add_argument("--self-test", action="store_true")
        modes.add_argument("--full-shape-fixture", action="store_true")
        modes.add_argument("--plan")
        modes.add_argument("--run")
        parser.add_argument("--output")
        parser.add_argument("--authorization-out")
        parser.add_argument("--authorization-file")
        parser.add_argument("--authorization-digest")
        parser.add_argument("--authorization-revision")
        parser.add_argument("--repository-root")
        args = parser.parse_args(argv)
        optional = (
            args.output,
            args.authorization_out,
            args.authorization_file,
            args.authorization_digest,
            args.authorization_revision,
            args.repository_root,
        )
        if args.self_test:
            _require(
                not any(value is not None for value in optional),
                "self-test does not accept execution arguments",
            )
            result = self_test()
        else:
            _require(
                args.repository_root is not None and args.output is not None,
                "an explicit repository root and output are required",
            )
            root = Path(args.repository_root)
            if args.plan or args.full_shape_fixture:
                _require(
                    args.authorization_out is not None
                    and args.authorization_file is None
                    and args.authorization_digest is None
                    and args.authorization_revision is None,
                    "planning/fixture require authorization-out only",
                )
                execution_dispatched = args.full_shape_fixture
                result = (
                    plan_execution(
                        args.plan,
                        args.output,
                        args.authorization_out,
                        repository_root=root,
                    )
                    if args.plan
                    else run_full_shape_fixture(
                        args.output, args.authorization_out, repository_root=root
                    )
                )
            else:
                _require(
                    args.authorization_out is None
                    and args.authorization_file is not None
                    and args.authorization_digest is not None
                    and args.authorization_revision is not None,
                    "run requires exact file, digest, and authorization revision",
                )
                execution_dispatched = True
                result = run_execution(
                    args.run,
                    args.output,
                    authorization_file=args.authorization_file,
                    authorization_digest=args.authorization_digest,
                    authorization_revision=args.authorization_revision,
                    repository_root=root,
                )
        sys.stdout.write(core.canonical_bytes(result).decode("utf-8"))
        return 0
    except Exception as error:
        typed = isinstance(error, (DenseRunnerError, publication.DensePublicationError))
        known_refusal = isinstance(error, core.DenseScaleExecutionError)
        if typed:
            status = error.status
            consumed = getattr(error, "authorization_consumed", None)
        elif known_refusal or not execution_dispatched:
            status = "NOT_RUN"
            consumed = False
        else:
            status = "PUBLICATION_STATE_AMBIGUOUS"
            consumed = None
        result = {
            "status": status,
            "error": str(error) if typed or known_refusal else type(error).__name__,
            "authorization_consumed": consumed,
            "retry_permitted": False,
            "claim_boundary": "No scientific decision is emitted by the runner.",
        }
        sys.stdout.write(core.canonical_bytes(result).decode("utf-8"))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
