"""Durable fixed PUBLIC attempt fences, not admission or execution authority.

The reviewed caller owns the fixed domain, attempt identity and path. A fence
must be consumed before the ordinary candidate-keyed PUBLIC claim. Changing a
candidate digest cannot reopen its occupied fence; uncertainty never unlinks it.
"""

from __future__ import annotations

import os
from pathlib import Path
import re


FIELDS = frozenset(
    "schema_version attempt_id execution_mode authorization_digest output_path "
    "reviewed_revision execution_head_revision irreversible owner_nonce "
    "deterministic_digest".split()
)


def _path(S, path):
    path = Path(path)
    S.require(
        path.is_absolute()
        and path.parent == S.LEDGER
        and re.fullmatch(r"receiver-public-[0-9a-f]{64}\.json", path.name) is not None,
        "fixed PUBLIC attempt path must be a direct ledger child",
    )
    return path


def ensure_unused(S, path):
    """Every occupied name, including a dangling symlink, is irrevocably spent."""
    path = _path(S, path)
    if os.path.lexists(path):
        raise S.ExecutionFailure(
            "AUTHORIZATION_ALREADY_SPENT",
            True,
            "occupied fixed PUBLIC attempt; no candidate replacement or retry",
        )


def _value(S, domain, attempt_id, authorization, reviewed, execution_head):
    S.require(
        type(domain) is str
        and bool(domain)
        and type(attempt_id) is str
        and bool(attempt_id),
        "fixed PUBLIC attempt domain and identity required",
    )
    S.require(
        type(authorization) is dict
        and authorization.get("execution_mode") == S.PUBLIC
        and authorization.get("replication_execution_authorized", False) is False,
        "PUBLIC authorization required; replication attempt fences are forbidden",
    )
    authorization = S.parse(S.canonical(authorization))
    S.base.storage.valid_digest(authorization)
    S.mechanics._require_sha256(authorization["deterministic_digest"], "authorization")
    for value in (reviewed, execution_head):
        S.require(
            type(value) is str and re.fullmatch(r"[0-9a-f]{40}", value) is not None,
            "PUBLIC attempt requires full lowercase revision OIDs",
        )
    output = authorization.get("output_path")
    S.require(
        type(output) is str
        and Path(output).is_absolute()
        and str(Path(output)) == output
        and ".." not in Path(output).parts,
        "PUBLIC attempt output must be an absolute unaliased path",
    )
    # Deterministic integrity/correlation label, not a secret capability. Actual
    # concurrency ownership comes from exclusive creation and its held descriptor.
    nonce = S.digest(
        [
            domain + "/public-attempt-nonce",
            attempt_id,
            authorization["deterministic_digest"],
            reviewed,
            execution_head,
        ]
    )
    return S.digested(
        dict(
            schema_version=domain + "/public-attempt-consumption",
            attempt_id=attempt_id,
            execution_mode=S.PUBLIC,
            authorization_digest=authorization["deterministic_digest"],
            output_path=output,
            reviewed_revision=reviewed,
            execution_head_revision=execution_head,
            irreversible=True,
            owner_nonce=nonce,
        )
    )


def consume(
    S,
    path,
    *,
    domain,
    attempt_id,
    authorization,
    reviewed,
    execution_head,
    snapshot_type,
):
    """Consume this fixed fence before S.consume; retain every uncertain name."""
    path = _path(S, path)
    ensure_unused(S, path)
    value = _value(S, domain, attempt_id, authorization, reviewed, execution_head)
    S.require(
        path
        == S.LEDGER / ("receiver-public-" + S.digest([domain, attempt_id]) + ".json"),
        "fixed PUBLIC attempt path differs from domain and identity",
    )
    raw = S.canonical(value)
    S.mechanics._require_posix_capabilities()
    try:
        if not os.path.lexists(S.LEDGER):
            created = S.base.storage._create_directory(S.LEDGER)
            created.close()
        parent = S.mechanics._PinnedParent.open(S.LEDGER)
    except S.base.PublicationUncertain as error:
        raise S.ExecutionFailure(
            "CONSUMPTION_UNCERTAIN",
            None,
            "attempt ledger creation uncertain; retain it",
        ) from error
    owned = None
    attempted = False
    try:
        S.base.storage._check_directory(parent)
        ensure_unused(S, path)
        attempted = True
        try:
            owned = S.mechanics._exclusive_create_exact(
                parent, path.name, raw, max_bytes=S.base.MAX_CONTROL_BYTES, hook=None
            )
        except S.mechanics._CreateAfterOpenError as error:
            owned = error.owned
            raise
        S.mechanics._assert_owned_exact(parent, owned)
        parent.fsync()
        S.base.storage._check_directory(parent)
        snapshot = snapshot_type.capture(path)
        S.require(
            snapshot.raw
            == raw
            == S.mechanics._read_bounded_regular_file_at(
                parent, path.name, max_bytes=S.base.MAX_CONTROL_BYTES
            ),
            "fixed PUBLIC attempt bytes differ",
        )
        S.mechanics._assert_owned_exact(parent, owned)
        snapshot.revalidate()
        return value, snapshot
    except S.ExecutionFailure:
        raise
    except S.mechanics._NameConflictError as error:
        raise S.ExecutionFailure(
            "AUTHORIZATION_ALREADY_SPENT", True, "fixed PUBLIC attempt raced; no retry"
        ) from error
    except BaseException as error:
        raise S.ExecutionFailure(
            "CONSUMPTION_UNCERTAIN" if attempted else "NOT_RUN",
            None if attempted else False,
            "retain fixed PUBLIC attempt namespace; no retry",
        ) from error
    finally:
        if owned is not None:
            owned.close()
        parent.close()


def inspect(
    S,
    path,
    *,
    domain,
    attempt_id,
    authorization,
    reviewed,
    execution_head,
    snapshot_type,
):
    """Independently derive and inspect the entire exact fixed-attempt payload."""
    path = _path(S, path)
    # Reject wrong modes/references before opening any claimed fence.
    expected = _value(S, domain, attempt_id, authorization, reviewed, execution_head)
    S.require(
        path
        == S.LEDGER / ("receiver-public-" + S.digest([domain, attempt_id]) + ".json"),
        "fixed PUBLIC attempt path differs from domain and identity",
    )
    parent = S.mechanics._PinnedParent.open(S.LEDGER)
    try:
        S.base.storage._check_directory(parent)
        raw = S.mechanics._read_bounded_regular_file_at(
            parent, path.name, max_bytes=S.base.MAX_CONTROL_BYTES
        )
        value = S.parse(raw)
        S.base.storage.valid_digest(value)
        S.require(set(value) == FIELDS, "closed fixed PUBLIC attempt required")
        S.require(
            raw == S.canonical(expected), "fixed PUBLIC attempt references differ"
        )
        snapshot = snapshot_type.capture(path)
        S.require(snapshot.raw == raw, "fixed PUBLIC attempt snapshot differs")
        S.mechanics._forward_sync_exact_regular_file_at(parent, path.name)
        parent.fsync()
        S.base.storage._check_directory(parent)
        snapshot.revalidate()
        S.require(
            raw
            == S.mechanics._read_bounded_regular_file_at(
                parent, path.name, max_bytes=S.base.MAX_CONTROL_BYTES
            ),
            "fixed PUBLIC attempt changed during inspection",
        )
        return snapshot
    finally:
        parent.close()
