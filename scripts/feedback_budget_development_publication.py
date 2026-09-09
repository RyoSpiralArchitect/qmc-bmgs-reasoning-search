"""New-domain, one-shot local POSIX publication for development-path qualification.

Only descriptor/immutable-file mechanics are shared with the older public
fixture. Its publisher, inspector, record domains and authority are not reused.
Storage closure alone never establishes replay or execution authorization.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import secrets


ROOT = Path(__file__).resolve().parents[1]
STORAGE = "scripts/feedback_budget_fixture_publication.py"
SPEC = importlib.util.spec_from_file_location(
    "feedback_budget_development_storage", ROOT / STORAGE
)
assert SPEC is not None and SPEC.loader is not None
storage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(storage)
mechanics = storage.mechanics
canonical, parse, digest, sha = (
    storage.canonical,
    storage.parse,
    storage.sha256_json,
    storage.sha,
)
digested, require = storage.digested, storage.require
PublicationError, PublicationUncertain = (
    storage.PublicationError,
    storage.PublicationUncertain,
)
DOMAIN = "qmc-bmgs-countdown-thompson-feedback-budget/v1"
MODE = "nondiagnostic_development_path_fixture"
FIXTURE_ID = "feedback_budget_development_path_public_192/v1"
CELL_NAMES, COMPLETE_NAMES = storage.CELL_NAMES, storage.COMPLETE_NAMES
MAX_CELL_BYTES, MAX_CONTROL_BYTES = storage.MAX_CELL_BYTES, storage.MAX_CONTROL_BYTES
ROW_FIELDS = storage.ROW_FIELDS | {"run_binding_digest"}


def frozen_binding(value: dict) -> dict:
    value = parse(canonical(value))
    storage.valid_digest(value)
    require(
        set(value)
        == {
            "schema_version",
            "execution_mode",
            "experiment_id",
            "expected_cell_count",
            "fixture_manifest_digest",
            "contract_digest",
            "schedule_digest",
            "source",
            "runtime",
            "qualification",
            "development_execution_authorized",
            "deterministic_digest",
        },
        "run-binding fields differ",
    )
    require(
        value["schema_version"] == DOMAIN + "/run-binding"
        and value["execution_mode"] == MODE
        and value["experiment_id"] == FIXTURE_ID,
        "run-binding domain/mode differs",
    )
    require(
        type(value["expected_cell_count"]) is int
        and value["expected_cell_count"] == 192
        and value["development_execution_authorized"] is False,
        "fixture-only 192-cell binding required",
    )
    for field in ("fixture_manifest_digest", "contract_digest", "schedule_digest"):
        mechanics._require_sha256(value[field], field)
    for field in ("source", "runtime", "qualification"):
        require(type(value[field]) is dict, "binding component must be an object")
    return value


def row_bytes(index: int, row: dict, binding: dict) -> bytes:
    require(type(index) is int and 0 <= index < 192, "cell index outside schedule")
    require(type(row) is dict and set(row) == ROW_FIELDS, "record fields differ")
    raw = canonical(row)
    value = parse(raw, MAX_CELL_BYTES)
    storage.valid_digest(value)
    require(value["schema_version"] == DOMAIN + "/record", "record domain differs")
    require(
        type(value["cell_index"]) is int and value["cell_index"] == index,
        "record index differs",
    )
    key = value["cell_key"]
    require(
        type(key) is dict and type(value["search_record"]) is dict,
        "record objects differ",
    )
    require(
        key.get("schema_version") == DOMAIN + "/cell-key"
        and key.get("execution_mode") == MODE
        and key.get("experiment_id") == FIXTURE_ID,
        "cell domain/mode differs",
    )
    require(value["cell_id"] == digest(key), "cell key digest differs")
    require(
        value["run_binding_digest"] == binding["deterministic_digest"],
        "record run-binding differs",
    )
    return raw


def receipt_bytes(receipt: dict, binding: dict) -> bytes:
    raw = canonical(receipt)
    value = parse(raw)
    storage.valid_digest(value)
    require(
        value.get("schema_version") == DOMAIN + "/execution-receipt"
        and value.get("run_binding_digest") == binding["deterministic_digest"]
        and value.get("execution_mode") == MODE
        and value.get("development_execution_authorized") is False,
        "execution receipt domain/binding differs",
    )
    return raw


def commit_value(binding, started_raw, receipt_raw, entries):
    return digested(
        dict(
            schema_version=DOMAIN + "/publication",
            status="DEVELOPMENT_PATH_FIXTURE_COMMITTED",
            execution_mode=MODE,
            experiment_id=FIXTURE_ID,
            expected_cell_count=192,
            run_binding_digest=binding["deterministic_digest"],
            started_sha256=sha(started_raw),
            receipt_sha256=sha(receipt_raw),
            receipt_byte_count=len(receipt_raw),
            cells=entries,
            development_execution_authorized=False,
        )
    )


def publish(output_dir: Path, binding: dict, action, check, _event_hook=None) -> dict:
    mechanics._require_posix_capabilities()
    output = mechanics._snapshot_output_path(output_dir)
    binding = frozen_binding(binding)
    require(callable(action) and callable(check), "callbacks required")
    check()
    parent = storage._create_directory(output)
    owned, entries, total, commit_attempted = [], [], 0, False

    def create(name, raw, cap=MAX_CONTROL_BYTES):
        nonlocal total
        require(
            total + len(raw) <= storage.MAX_TOTAL_BYTES, "artifact byte limit exceeded"
        )
        try:
            item = mechanics._exclusive_create_exact(
                parent, name, raw, max_bytes=cap, hook=_event_hook
            )
        except mechanics._CreateAfterOpenError as error:
            owned.append(error.owned)
            raise
        owned.append(item)
        total += len(raw)

    try:
        started = digested(
            dict(
                schema_version=DOMAIN + "/started",
                status="DEVELOPMENT_PATH_FIXTURE_STARTED",
                binding=binding,
                output_directory=str(output),
                directory_identity_chain=[list(i) for i in parent.component_identities],
                owner_nonce=secrets.token_hex(32),
            )
        )
        started_raw = canonical(started)
        create("STARTED.json", started_raw)
        storage._observe(parent, ("STARTED.json",), owned=owned)
        check()

        def emit(index, row):
            require(
                type(index) is int and index == len(entries), "cell emit order differs"
            )
            raw = row_bytes(index, row, binding)
            name = CELL_NAMES[index]
            create(name, raw, MAX_CELL_BYTES)
            entries.append(
                dict(
                    cell_index=index,
                    filename=name,
                    byte_count=len(raw),
                    sha256=sha(raw),
                )
            )

        receipt_raw = receipt_bytes(action(emit), binding)
        require(len(entries) == 192, "incomplete matrix")
        check()
        create("RECEIPT.json", receipt_raw)
        names = {item.name for item in owned}
        storage._observe(parent, names, owned=owned)
        commit = commit_value(binding, started_raw, receipt_raw, entries)
        check()
        require(
            storage._generation(parent, names)
            == storage._observe(parent, names, owned=owned)[1],
            "precommit closure changed",
        )
        commit_attempted = True
        create("COMMIT.json", canonical(commit))
        storage._observe(parent, COMPLETE_NAMES, owned=owned)
        return commit
    except BaseException as error:
        if commit_attempted or isinstance(
            error, (mechanics.RegularFilePublicationV2Error, PublicationUncertain)
        ):
            raise PublicationUncertain(
                "publication uncertain; retain occupied directory"
            ) from error
        try:
            names = {item.name for item in owned}
            storage._observe(parent, names, owned=owned)
            create(
                "FAILURE.json",
                canonical(
                    digested(
                        dict(
                            schema_version=DOMAIN + "/failure",
                            status="INVALID_ANALYSIS",
                            execution_mode=MODE,
                            error_type=type(error).__name__,
                            run_binding_digest=binding["deterministic_digest"],
                            completed_cell_count=len(entries),
                            development_execution_authorized=False,
                        )
                    )
                ),
            )
            storage._observe(parent, names | {"FAILURE.json"}, owned=owned)
        except BaseException as failure_error:
            raise PublicationUncertain(
                "failure state uncertain; retain occupied directory"
            ) from failure_error
        raise
    finally:
        for item in reversed(owned):
            item.close()
        parent.close()


def inspect(output_dir: Path):
    """Storage closure only. Caller must independently admit and replay all cells."""
    mechanics._require_posix_capabilities()
    output = mechanics._snapshot_output_path(output_dir)
    parent = mechanics._PinnedParent.open(output)
    try:
        raw, generation = storage._observe(parent, COMPLETE_NAMES)
        started = parse(raw["STARTED.json"])
        storage.valid_digest(started)
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
            and started["status"] == "DEVELOPMENT_PATH_FIXTURE_STARTED",
            "started domain differs",
        )
        binding = frozen_binding(started["binding"])
        require(started["output_directory"] == str(output), "output path differs")
        require(
            canonical(started["directory_identity_chain"])
            == canonical([list(i) for i in parent.component_identities]),
            "directory binding differs",
        )
        mechanics._require_sha256(started["owner_nonce"], "owner nonce")
        entries = []
        for index, name in enumerate(CELL_NAMES):
            require(
                row_bytes(index, parse(raw[name], MAX_CELL_BYTES), binding)
                == raw[name],
                "record bytes differ",
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
        expected = commit_value(
            binding, raw["STARTED.json"], raw["RECEIPT.json"], entries
        )
        require(canonical(expected) == raw["COMMIT.json"], "commit closure differs")
        inspection = storage.Inspection(
            output, raw, generation, parent.component_identities
        )
        require(
            storage._generation(parent, COMPLETE_NAMES) == generation,
            "artifact changed during validation",
        )
        return inspection
    finally:
        parent.close()


def publish_summary(path: Path, summary: dict, check):
    require(
        summary.get("schema_version") == DOMAIN + "/analysis"
        and summary.get("execution_mode") == MODE
        and summary.get("scientific_decision") is None
        and summary.get("development_execution_authorized") is False,
        "only nonauthorizing fixture analysis may be saved",
    )
    storage.valid_digest(summary)
    return storage.publish_summary(path, summary, check)
