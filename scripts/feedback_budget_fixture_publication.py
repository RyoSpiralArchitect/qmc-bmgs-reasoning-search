"""Durable, exclusive storage for the fixed 192-cell public fixture only.

This wrapper reuses descriptor mechanics, not the old experiment publishers.
An occupied directory is never reclaimed, resumed, overwritten or removed.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import secrets
import stat
from typing import Callable

from qmc_bmgs.experiments import (
    countdown_thompson_regular_file_publication_v2 as mechanics,
)
from qmc_bmgs.substrate.trace import canonical_json, sha256_json, strict_json_loads


DOMAIN = "qmc-bmgs-feedback-budget-nondiagnostic-full-shape/v1"
FIXTURE_ID = "feedback_budget_nondiagnostic_full_shape_192/v1"
CELL_COUNT = 192
MAX_CELL_BYTES = 8 << 20
MAX_CONTROL_BYTES = 8 << 20
MAX_TOTAL_BYTES = 256 << 20
CELL_NAMES = tuple(f"cell-{index:03d}.json" for index in range(CELL_COUNT))
COMPLETE_NAMES = frozenset((*CELL_NAMES, "STARTED.json", "RECEIPT.json", "COMMIT.json"))
ROW_FIELDS = frozenset(
    (
        "schema_version",
        "cell_index",
        "cell_id",
        "cell_key",
        "search_record",
        "deterministic_digest",
    )
)


class PublicationError(ValueError):
    """The fixed public artifact is invalid or incomplete."""


class PublicationUncertain(RuntimeError):
    """Retain the occupied directory; durable completion was not proved."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PublicationError(message)


def canonical(value: dict) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def digested(value: dict) -> dict:
    require("deterministic_digest" not in value, "digest already present")
    return {**value, "deterministic_digest": sha256_json(value)}


def parse(raw: bytes, cap: int = MAX_CONTROL_BYTES) -> dict:
    require(type(raw) is bytes and len(raw) <= cap, "object byte limit exceeded")
    value = strict_json_loads(raw.decode("utf-8"))
    require(
        type(value) is dict and canonical(value) == raw, "canonical object required"
    )
    return value


def valid_digest(value: dict) -> None:
    require(
        value.get("deterministic_digest")
        == sha256_json(
            {key: item for key, item in value.items() if key != "deterministic_digest"}
        ),
        "object digest differs",
    )


def frozen_binding(binding: dict) -> dict:
    require(type(binding) is dict, "binding must be an object")
    binding = parse(canonical(binding))
    require(
        binding.get("schema_version") == DOMAIN + "/binding", "binding domain differs"
    )
    require(binding.get("fixture_id") == FIXTURE_ID, "fixture identity differs")
    require(
        type(binding.get("expected_cell_count")) is int
        and binding["expected_cell_count"] == CELL_COUNT,
        "exactly 192 cells required",
    )
    require(
        binding.get("development_execution_authorized") is False, "public fixture only"
    )
    if "deterministic_digest" in binding:
        valid_digest(binding)
    return binding


def row_bytes(index: int, row: dict) -> bytes:
    require(
        type(index) is int and 0 <= index < CELL_COUNT, "cell index outside schedule"
    )
    require(type(row) is dict and set(row) == ROW_FIELDS, "record fields differ")
    raw = canonical(row)
    frozen = parse(raw, MAX_CELL_BYTES)
    require(frozen["schema_version"] == DOMAIN + "/record", "record domain differs")
    require(
        type(frozen["cell_index"]) is int and frozen["cell_index"] == index,
        "record index differs",
    )
    require(
        type(frozen["cell_key"]) is dict and type(frozen["search_record"]) is dict,
        "record objects differ",
    )
    require(
        frozen["cell_id"] == sha256_json(frozen["cell_key"]),
        "cell identity digest differs",
    )
    valid_digest(frozen)
    return raw


def _receipt_bytes(receipt: dict) -> bytes:
    require(type(receipt) is dict, "receipt must be an object")
    raw = canonical(receipt)
    value = parse(raw)
    require(
        value.get("schema_version") == DOMAIN + "/receipt", "receipt domain differs"
    )
    valid_digest(value)
    return raw


def _check_directory(parent) -> None:
    parent.assert_path()
    observed = os.fstat(parent.descriptor)
    require(
        stat.S_ISDIR(observed.st_mode)
        and stat.S_IMODE(observed.st_mode) == 0o700
        and observed.st_uid == os.geteuid(),
        "fixture directory must be private and owned",
    )


def _generation(parent, names) -> tuple:
    _check_directory(parent)
    before = mechanics._parent_generation(parent)
    require(
        set(os.listdir(parent.descriptor)) == set(names),
        "artifact file closure differs",
    )
    entries = mechanics._reserved_generation(parent, tuple(sorted(names)))
    after = mechanics._parent_generation(parent)
    require(before == after, "directory changed while observed")
    parent.assert_path()
    return before, entries


def _observe(parent, names, *, owned=()) -> tuple[dict[str, bytes], tuple]:
    generation = _generation(parent, names)
    for item in owned:
        mechanics._assert_owned_exact(parent, item)
    raw = {}
    total = 0
    for name in sorted(names):
        cap = MAX_CELL_BYTES if name in CELL_NAMES else MAX_CONTROL_BYTES
        raw[name] = mechanics._read_bounded_regular_file_at(parent, name, max_bytes=cap)
        total += len(raw[name])
        require(total <= MAX_TOTAL_BYTES, "artifact byte limit exceeded")
        mechanics._forward_sync_exact_regular_file_at(parent, name)
    parent.fsync()
    require(_generation(parent, names) == generation, "artifact generation changed")
    for item in owned:
        mechanics._assert_owned_exact(parent, item)
    return raw, generation


def _create_directory(output: Path):
    outer = mechanics._PinnedParent.open(output.parent)
    created = False
    inner = None
    try:
        outer.assert_path()
        os.mkdir(output.name, 0o700, dir_fd=outer.descriptor)
        created = True
        outer.fsync()
        observed = os.stat(output.name, dir_fd=outer.descriptor, follow_symlinks=False)
        require(stat.S_ISDIR(observed.st_mode), "new output is not a directory")
        inner = mechanics._PinnedParent.open(output)
        require(
            mechanics._directory_identity(observed)
            == mechanics._directory_identity(os.fstat(inner.descriptor)),
            "new directory identity changed",
        )
        os.fchmod(inner.descriptor, 0o700)
        inner.fsync()
        outer.assert_path()
        _generation(inner, ())
        result, inner = inner, None
        return result
    except BaseException as error:
        if created:
            raise PublicationUncertain(
                "new directory retained after uncertain creation"
            ) from error
        raise
    finally:
        if inner is not None:
            inner.close()
        outer.close()


def publish(
    output_dir: Path,
    binding: dict,
    action: Callable,
    pre_action_check: Callable,
    pre_commit_check: Callable,
    _event_hook=None,
) -> dict:
    """Execute and retain one exact public matrix; no retry of occupied slots."""
    mechanics._require_posix_capabilities()
    output = mechanics._snapshot_output_path(output_dir)
    binding = frozen_binding(binding)
    require(
        all(callable(fn) for fn in (action, pre_action_check, pre_commit_check)),
        "callbacks required",
    )
    pre_action_check()
    parent = _create_directory(output)
    owned = []
    total = 0
    commit_attempted = False

    def create(name, raw, cap=MAX_CONTROL_BYTES):
        nonlocal total
        require(total + len(raw) <= MAX_TOTAL_BYTES, "artifact byte limit exceeded")
        try:
            item = mechanics._exclusive_create_exact(
                parent, name, raw, max_bytes=cap, hook=_event_hook
            )
        except mechanics._CreateAfterOpenError as error:
            owned.append(error.owned)
            raise
        owned.append(item)
        total += len(raw)
        return item

    try:
        started = digested(
            {
                "schema_version": DOMAIN + "/started",
                "status": "PUBLIC_FULL_SHAPE_STARTED",
                "binding": binding,
                "output_directory": str(output),
                "directory_identity_chain": [
                    list(identity) for identity in parent.component_identities
                ],
                "owner_nonce": secrets.token_hex(32),
            }
        )
        create("STARTED.json", canonical(started))
        _observe(parent, ("STARTED.json",), owned=owned)
        pre_action_check()
        entries = []

        def emit(index, row):
            require(
                type(index) is int and index == len(entries), "cell emit order differs"
            )
            raw = row_bytes(index, row)
            name = CELL_NAMES[index]
            create(name, raw, MAX_CELL_BYTES)
            entries.append(
                {
                    "cell_index": index,
                    "filename": name,
                    "byte_count": len(raw),
                    "sha256": sha(raw),
                }
            )

        receipt_raw = _receipt_bytes(action(emit))
        require(len(entries) == CELL_COUNT, "incomplete public matrix")
        pre_commit_check()
        create("RECEIPT.json", receipt_raw)
        names = {item.name for item in owned}
        _observe(parent, names, owned=owned)
        commit = digested(
            {
                "schema_version": DOMAIN + "/commit",
                "status": "PUBLIC_FULL_SHAPE_COMMITTED",
                "fixture_id": FIXTURE_ID,
                "expected_cell_count": CELL_COUNT,
                "binding_digest": sha256_json(binding),
                "started_sha256": sha(canonical(started)),
                "receipt_sha256": sha(receipt_raw),
                "receipt_byte_count": len(receipt_raw),
                "cells": entries,
                "development_execution_authorized": False,
            }
        )
        pre_commit_check()
        require(
            _generation(parent, names) == _observe(parent, names, owned=owned)[1],
            "precommit closure changed",
        )
        commit_attempted = True
        create("COMMIT.json", canonical(commit))
        _observe(parent, COMPLETE_NAMES, owned=owned)
        return commit
    except BaseException as error:
        ambiguous = isinstance(
            error, (mechanics.RegularFilePublicationV2Error, PublicationUncertain)
        )
        if commit_attempted or ambiguous:
            raise PublicationUncertain(
                "publication uncertain; retain occupied fixture directory"
            ) from error
        try:
            names = {item.name for item in owned}
            _observe(parent, names, owned=owned)
            failure = digested(
                {
                    "schema_version": DOMAIN + "/failure",
                    "status": "INVALID_PUBLIC_FULL_SHAPE",
                    "error_type": type(error).__name__,
                    "binding_digest": sha256_json(binding),
                    "completed_cell_count": sum(name in CELL_NAMES for name in names),
                    "development_execution_authorized": False,
                }
            )
            create("FAILURE.json", canonical(failure))
            _observe(parent, names | {"FAILURE.json"}, owned=owned)
        except BaseException as failure_error:
            raise PublicationUncertain(
                "failure state uncertain; retain occupied fixture directory"
            ) from failure_error
        raise
    finally:
        for item in reversed(owned):
            item.close()
        parent.close()


class Inspection:
    """Detached canonical values plus immutable-byte generation revalidation."""

    def __init__(self, output, raw, generation, identities):
        self._output = output
        self._raw = raw
        self._generation = generation
        self._identities = identities

    @property
    def binding(self):
        return parse(self._raw["STARTED.json"])["binding"]

    @property
    def rows(self):
        return [parse(self._raw[name], MAX_CELL_BYTES) for name in CELL_NAMES]

    @property
    def receipt(self):
        return parse(self._raw["RECEIPT.json"])

    @property
    def commit(self):
        return parse(self._raw["COMMIT.json"])

    def revalidate(self):
        parent = mechanics._PinnedParent.open(self._output)
        try:
            require(
                parent.component_identities == self._identities,
                "artifact path identity changed",
            )
            raw, generation = _observe(parent, COMPLETE_NAMES)
            require(
                raw == self._raw and generation == self._generation,
                "artifact snapshot changed",
            )
        finally:
            parent.close()


def inspect(output_dir: Path) -> Inspection:
    """Validate storage closure only; caller independently recomputes search."""
    mechanics._require_posix_capabilities()
    output = mechanics._snapshot_output_path(output_dir)
    parent = mechanics._PinnedParent.open(output)
    try:
        raw, generation = _observe(parent, COMPLETE_NAMES)
        started = parse(raw["STARTED.json"])
        valid_digest(started)
        require(
            set(started)
            == {
                "schema_version",
                "status",
                "binding",
                "output_directory",
                "directory_identity_chain",
                "owner_nonce",
                "deterministic_digest",
            },
            "started fields differ",
        )
        require(
            started["schema_version"] == DOMAIN + "/started"
            and started["status"] == "PUBLIC_FULL_SHAPE_STARTED",
            "started domain differs",
        )
        binding = frozen_binding(started["binding"])
        require(
            started["output_directory"] == str(output), "artifact output path differs"
        )
        require(
            canonical_json(started["directory_identity_chain"])
            == canonical_json(
                [list(identity) for identity in parent.component_identities]
            ),
            "artifact directory binding differs",
        )
        mechanics._require_sha256(started["owner_nonce"], "owner nonce")
        entries = []
        for index, name in enumerate(CELL_NAMES):
            require(
                row_bytes(index, parse(raw[name], MAX_CELL_BYTES)) == raw[name],
                "record bytes differ",
            )
            entries.append(
                {
                    "cell_index": index,
                    "filename": name,
                    "byte_count": len(raw[name]),
                    "sha256": sha(raw[name]),
                }
            )
        _receipt_bytes(parse(raw["RECEIPT.json"]))
        expected = digested(
            {
                "schema_version": DOMAIN + "/commit",
                "status": "PUBLIC_FULL_SHAPE_COMMITTED",
                "fixture_id": FIXTURE_ID,
                "expected_cell_count": CELL_COUNT,
                "binding_digest": sha256_json(binding),
                "started_sha256": sha(raw["STARTED.json"]),
                "receipt_sha256": sha(raw["RECEIPT.json"]),
                "receipt_byte_count": len(raw["RECEIPT.json"]),
                "cells": entries,
                "development_execution_authorized": False,
            }
        )
        require(canonical(expected) == raw["COMMIT.json"], "commit closure differs")
        result = Inspection(output, raw, generation, parent.component_identities)
        require(
            _generation(parent, COMPLETE_NAMES) == generation,
            "artifact changed during validation",
        )
        return result
    finally:
        parent.close()


def publish_summary(path: Path, payload: dict, pre_publish_check: Callable) -> dict:
    """Publish one exclusive summary outside the input artifact directory."""
    mechanics._require_posix_capabilities()
    path = mechanics._snapshot_output_path(path)
    require(
        type(payload) is dict and callable(pre_publish_check),
        "summary object and callback required",
    )
    raw = canonical(payload)
    parse(raw)
    parent = mechanics._PinnedParent.open(path.parent)
    owned = None
    attempted = False
    try:
        pre_publish_check()
        attempted = True
        try:
            owned = mechanics._exclusive_create_exact(
                parent, path.name, raw, max_bytes=MAX_CONTROL_BYTES, hook=None
            )
        except mechanics._CreateAfterOpenError as error:
            owned = error.owned
            raise
        pre_publish_check()
        mechanics._assert_owned_exact(parent, owned)
        parent.fsync()
        parent.assert_path()
        return {"path": str(path), "sha256": sha(raw), "byte_count": len(raw)}
    except mechanics._NameConflictError:
        raise
    except BaseException as error:
        if attempted:
            raise PublicationUncertain(
                "summary publication uncertain; retain occupied file"
            ) from error
        raise
    finally:
        if owned is not None:
            owned.close()
        parent.close()
