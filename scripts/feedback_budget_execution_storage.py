"""One-shot authorization claims and closed connector publications.

Only POSIX descriptor mechanics are shared with earlier fixtures. Neither this
storage module nor a well-formed binding authenticates an execution candidate.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import secrets


ROOT = Path(__file__).resolve().parents[1]
STORAGE = "scripts/feedback_budget_fixture_publication.py"
SPEC = importlib.util.spec_from_file_location(
    "feedback_budget_connector_storage_base", ROOT / STORAGE
)
assert SPEC is not None and SPEC.loader is not None
base = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(base)
mechanics = base.mechanics
canonical, parse, digest, sha, require = (
    base.canonical,
    base.parse,
    base.sha256_json,
    base.sha,
    base.require,
)
digested = base.digested
DOMAIN = "qmc-bmgs-countdown-thompson-feedback-budget/v1/connector"
PUBLIC = "nondiagnostic_execution_connector_fixture"
DEVELOPMENT = "sealed_development_cohort"
PUBLIC_ID = "feedback_budget_execution_connector_public_192/v1"
DEVELOPMENT_ID = "feedback_budget_development_12_seed_26090401/v1"
LEDGER = ROOT / "artifacts/work/feedback-budget-v6-authorization-ledger"
NAMES = base.COMPLETE_NAMES
BINDING_FIELDS = frozenset(
    "schema_version execution_mode experiment_id input_manifest_digest authorization authorization_path reviewed_revision execution_head_revision claim development_execution_authorized deterministic_digest".split()
)


class ExecutionFailure(RuntimeError):
    def __init__(self, status, consumed, reason):
        super().__init__(reason)
        self.status, self.authorization_consumed = status, consumed


def mode_identity(mode):
    require(
        type(mode) is str and mode in (PUBLIC, DEVELOPMENT),
        "connector execution mode differs",
    )
    return PUBLIC_ID if mode == PUBLIC else DEVELOPMENT_ID


def parent_binding(output):
    parent = mechanics._PinnedParent.open(output.parent)
    try:
        parent.assert_path()
        return digested(
            dict(
                schema_version=DOMAIN + "/output-parent",
                path=str(output.parent),
                identities=[list(x) for x in parent.component_identities],
            )
        )
    finally:
        parent.close()


def claim_path(authorization):
    mode = authorization["execution_mode"]
    identity = mode_identity(mode)
    # Development is consumed once per fixed study, not once per filename or
    # candidate digest. A newly minted authorization cannot revive the study.
    key = (
        authorization["deterministic_digest"]
        if mode == PUBLIC
        else digest([DOMAIN, identity])
    )
    return LEDGER / (("public-" if mode == PUBLIC else "development-") + key + ".json")


def claim_value(authorization, reviewed, execution_head, nonce):
    mechanics._require_sha256(nonce, "claim nonce")
    return digested(
        dict(
            schema_version=DOMAIN + "/consumption",
            execution_mode=authorization["execution_mode"],
            experiment_id=mode_identity(authorization["execution_mode"]),
            authorization_digest=authorization["deterministic_digest"],
            input_manifest_digest=authorization["input_manifest_digest"],
            output_path=authorization["output_path"],
            output_parent=authorization["output_parent"],
            reviewed_revision=reviewed,
            execution_head_revision=execution_head,
            owner_nonce=nonce,
            irreversible=True,
        )
    )


def consume(authorization, reviewed, execution_head, snapshot_type):
    """Durable exclusive claim BEFORE output creation; every occupied slot stays."""
    mechanics._require_posix_capabilities()
    try:
        if not os.path.lexists(LEDGER):
            created = base._create_directory(LEDGER)
            created.close()
        parent = mechanics._PinnedParent.open(LEDGER)
    except base.PublicationUncertain as error:
        raise ExecutionFailure(
            "CONSUMPTION_UNCERTAIN", None, "ledger creation uncertain; retain namespace"
        ) from error
    owned = None
    attempted = False
    try:
        base._check_directory(parent)
        path = claim_path(authorization)
        if os.path.lexists(path):
            raise ExecutionFailure(
                "AUTHORIZATION_ALREADY_SPENT",
                True,
                "occupied consumption slot; no retry or adoption",
            )
        value = claim_value(
            authorization, reviewed, execution_head, secrets.token_hex(32)
        )
        attempted = True
        try:
            owned = mechanics._exclusive_create_exact(
                parent,
                path.name,
                canonical(value),
                max_bytes=base.MAX_CONTROL_BYTES,
                hook=None,
            )
        except mechanics._CreateAfterOpenError as error:
            owned = error.owned
            raise
        mechanics._assert_owned_exact(parent, owned)
        parent.fsync()
        base._check_directory(parent)
        snapshot = snapshot_type.capture(path)
        require(snapshot.raw == canonical(value), "consumption claim bytes differ")
        return value, snapshot
    except ExecutionFailure:
        raise
    except mechanics._NameConflictError as error:
        raise ExecutionFailure(
            "AUTHORIZATION_ALREADY_SPENT", True, "consumption name raced; no retry"
        ) from error
    except BaseException as error:
        raise ExecutionFailure(
            "CONSUMPTION_UNCERTAIN" if attempted else "NOT_RUN",
            None if attempted else False,
            "retain consumption namespace; no retry",
        ) from error
    finally:
        if owned is not None:
            owned.close()
        parent.close()


def frozen_binding(value):
    value = parse(canonical(value))
    base.valid_digest(value)
    require(set(value) == BINDING_FIELDS, "connector binding fields differ")
    mode = value["execution_mode"]
    require(
        value["schema_version"] == DOMAIN + "/run-binding"
        and value["experiment_id"] == mode_identity(mode),
        "connector binding domain differs",
    )
    require(
        value["development_execution_authorized"] is (mode == DEVELOPMENT),
        "execution authority flag differs",
    )
    mechanics._require_sha256(value["input_manifest_digest"], "input digest")
    require(
        type(value["authorization"]) is dict and type(value["claim"]) is dict,
        "authorization and claim objects required",
    )
    require(
        canonical(
            claim_value(
                value["authorization"],
                value["reviewed_revision"],
                value["execution_head_revision"],
                value["claim"]["owner_nonce"],
            )
        )
        == canonical(value["claim"]),
        "claim linkage differs",
    )
    require(
        value["authorization"]["execution_mode"] == mode
        and value["authorization"]["input_manifest_digest"]
        == value["input_manifest_digest"],
        "authorization input/mode differs",
    )
    return value


def inspect_claim(binding, snapshot_type):
    binding = frozen_binding(binding)
    parent = mechanics._PinnedParent.open(LEDGER)
    try:
        base._check_directory(parent)
        snapshot = snapshot_type.capture(claim_path(binding["authorization"]))
        require(
            snapshot.raw
            == canonical(binding["claim"])
            == mechanics._read_bounded_regular_file_at(
                parent, snapshot.path.name, max_bytes=base.MAX_CONTROL_BYTES
            ),
            "persisted consumption claim differs",
        )
        mechanics._forward_sync_exact_regular_file_at(parent, snapshot.path.name)
        parent.fsync()
        base._check_directory(parent)
        snapshot.revalidate()
        return snapshot
    finally:
        parent.close()


def record_bytes(index, value, binding):
    raw = canonical(value)
    value = parse(raw, base.MAX_CELL_BYTES)
    base.valid_digest(value)
    require(
        set(value) == base.ROW_FIELDS | {"run_binding_digest"},
        "connector record fields differ",
    )
    require(
        type(index) is int
        and 0 <= index < 192
        and type(value["cell_index"]) is int
        and value["cell_index"] == index,
        "record index differs",
    )
    require(
        value["schema_version"] == DOMAIN + "/record"
        and value["run_binding_digest"] == binding["deterministic_digest"],
        "record run-binding differs",
    )
    key = value["cell_key"]
    require(
        type(key) is dict
        and type(value["search_record"]) is dict
        and value["cell_id"] == digest(key),
        "record key/content differs",
    )
    require(
        key["execution_mode"] == binding["execution_mode"]
        and key["experiment_id"] == binding["experiment_id"],
        "record mode differs",
    )
    return raw


def receipt_bytes(value, binding):
    raw = canonical(value)
    value = parse(raw)
    base.valid_digest(value)
    require(
        value.get("schema_version") == DOMAIN + "/execution-receipt"
        and value.get("run_binding_digest") == binding["deterministic_digest"],
        "connector receipt linkage differs",
    )
    return raw


def commit_value(binding, started_raw, receipt_raw, entries):
    return digested(
        dict(
            schema_version=DOMAIN + "/publication",
            status="CONNECTOR_MATRIX_COMMITTED",
            execution_mode=binding["execution_mode"],
            run_binding_digest=binding["deterministic_digest"],
            started_sha256=sha(started_raw),
            receipt_sha256=sha(receipt_raw),
            receipt_byte_count=len(receipt_raw),
            cells=entries,
        )
    )


def publish(output, binding, action, check):
    """An independently admitted/consumed binding is required by the caller."""
    binding = frozen_binding(binding)
    parent = None
    owned, entries, total, commit_attempted = [], [], 0, False
    started_durable = False

    def create(name, raw, cap=base.MAX_CONTROL_BYTES):
        nonlocal total
        require(
            total + len(raw) <= base.MAX_TOTAL_BYTES, "publication byte limit exceeded"
        )
        try:
            item = mechanics._exclusive_create_exact(
                parent, name, raw, max_bytes=cap, hook=None
            )
        except mechanics._CreateAfterOpenError as error:
            owned.append(error.owned)
            raise
        owned.append(item)
        total += len(raw)

    try:
        check()
        parent = base._create_directory(output)
        started_raw = canonical(
            digested(
                dict(
                    schema_version=DOMAIN + "/started",
                    binding=binding,
                    output_path=str(output),
                    directory_identities=[list(x) for x in parent.component_identities],
                )
            )
        )
        create("STARTED.json", started_raw)
        base._observe(parent, ("STARTED.json",), owned=owned)
        started_durable = True
        check()

        def emit(index, row):
            require(
                type(index) is int and index == len(entries),
                "cell emission order differs",
            )
            raw = record_bytes(index, row, binding)
            name = base.CELL_NAMES[index]
            create(name, raw, base.MAX_CELL_BYTES)
            entries.append(
                dict(
                    cell_index=index,
                    filename=name,
                    byte_count=len(raw),
                    sha256=sha(raw),
                )
            )

        receipt_raw = receipt_bytes(action(emit), binding)
        require(len(entries) == 192, "incomplete connector matrix")
        check()
        create("RECEIPT.json", receipt_raw)
        names = {x.name for x in owned}
        base._observe(parent, names, owned=owned)
        check()
        base._observe(parent, names, owned=owned)
        commit = commit_value(binding, started_raw, receipt_raw, entries)
        commit_attempted = True
        create("COMMIT.json", canonical(commit))
        base._observe(parent, NAMES, owned=owned)
        check()
        base._observe(parent, NAMES, owned=owned)
        return commit
    except BaseException as error:
        if commit_attempted or isinstance(
            error, (base.PublicationUncertain, mechanics.RegularFilePublicationV2Error)
        ):
            raise ExecutionFailure(
                "PUBLICATION_UNCERTAIN",
                True,
                "retain consumed claim and occupied publication",
            ) from error
        if parent is not None:
            try:
                create(
                    "FAILURE.json",
                    canonical(
                        digested(
                            dict(
                                schema_version=DOMAIN + "/failure",
                                run_binding_digest=binding["deterministic_digest"],
                                cell_count=len(entries),
                                error_type=type(error).__name__,
                                scientific_decision=None,
                            )
                        )
                    ),
                )
            except BaseException:
                raise ExecutionFailure(
                    "PUBLICATION_UNCERTAIN",
                    True,
                    "failure marker uncertain; retain consumed claim",
                ) from error
        raise ExecutionFailure(
            "INVALID_ANALYSIS" if started_durable else "SPENT_NOT_RUN", True, str(error)
        ) from error
    finally:
        for item in reversed(owned):
            item.close()
        if parent is not None:
            parent.close()


def inspect(output):
    """Content closure only, before source admission or replay; no claim of either."""
    parent = mechanics._PinnedParent.open(output)
    try:
        raw, generation = base._observe(parent, NAMES)
        started = parse(raw["STARTED.json"])
        base.valid_digest(started)
        require(
            set(started)
            == {
                "schema_version",
                "binding",
                "output_path",
                "directory_identities",
                "deterministic_digest",
            }
            and started["schema_version"] == DOMAIN + "/started",
            "STARTED content differs",
        )
        binding = frozen_binding(started["binding"])
        require(
            started["output_path"] == str(output)
            and canonical(started["directory_identities"])
            == canonical([list(x) for x in parent.component_identities]),
            "publication location differs",
        )
        require(
            binding["authorization"]["output_path"] == str(output),
            "authorized output differs",
        )
        entries = []
        for index, name in enumerate(base.CELL_NAMES):
            require(
                record_bytes(index, parse(raw[name], base.MAX_CELL_BYTES), binding)
                == raw[name],
                "stored record differs",
            )
            entries.append(
                dict(
                    cell_index=index,
                    filename=name,
                    byte_count=len(raw[name]),
                    sha256=sha(raw[name]),
                )
            )
        receipt_bytes(parse(raw["RECEIPT.json"]), binding)
        require(
            canonical(
                commit_value(binding, raw["STARTED.json"], raw["RECEIPT.json"], entries)
            )
            == raw["COMMIT.json"],
            "COMMIT closure differs",
        )
        result = base.Inspection(output, raw, generation, parent.component_identities)
        require(
            base._generation(parent, NAMES) == generation,
            "publication changed during inspection",
        )
        return result
    finally:
        parent.close()
