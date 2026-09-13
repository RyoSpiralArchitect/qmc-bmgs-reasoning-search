#!/usr/bin/env python3
"""v7 one-shot connector: fixed PUBLIC qualification, then reviewed sealed inputs.

No generator entry point, alternative seeds, retries, resume, or provider route.
A candidate is not authority: replication execution also requires reviewed Git
bytes, a verified connector PUBLIC publication and explicit digest confirmation.
"""

from __future__ import annotations

import argparse
from itertools import product
import os
from pathlib import Path
import re
import sys
import importlib.util


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = "scripts/run_feedback_budget_replication_execution.py"
STORAGE = "scripts/feedback_budget_replication_execution_storage.py"
ADMISSION = "scripts/feedback_budget_replication_admission.py"
BASE = "e5964e0905c5a80260589ab81dafed31353d0c8d"
ANALYSIS = "scripts/feedback_budget_replication_execution_analysis.py"


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


admission = load("feedback_budget_replication_connector_admission", ADMISSION)
storage = load("feedback_budget_replication_connector_storage", STORAGE)
analysis = load("feedback_budget_replication_connector_analysis", ANALYSIS)
public, k, q, core = admission.public, admission.k, admission.q, admission.core
canonical, digest, require = k.canonical, k.digest, k.require
digested = core.with_digest
DOMAIN, PUBLIC, REPLICATION = storage.DOMAIN, storage.PUBLIC, storage.REPLICATION
AUTH_FIELDS = frozenset(
    "schema_version status execution_mode experiment_id input_manifest_digest contract_digest schedule_digest cohort_seal source runtime baseline authorities admission_proof connector_qualification output_path output_parent expected_cell_count candidate_is_execution_authority requires_explicit_digest_confirmation locked_128_evaluation_authorized deterministic_digest".split()
)


def snapshot_file(path):
    return core.FileSnapshot.capture(path, byte_cap=storage.base.MAX_CONTROL_BYTES)


def public_manifest():
    value = k.fixture_manifest()
    cells = []
    for cell in value["cells"]:
        key = {
            **cell["cell_key"],
            "schema_version": DOMAIN + "/cell-key",
            "execution_mode": PUBLIC,
            "experiment_id": storage.PUBLIC_ID,
        }
        cells.append(
            dict(cell_index=cell["cell_index"], cell_id=digest(key), cell_key=key)
        )
    return digested(
        dict(
            schema_version=DOMAIN + "/public-inputs",
            execution_mode=PUBLIC,
            experiment_id=storage.PUBLIC_ID,
            contract_digest=value["contract_digest"],
            tasks=value["tasks"],
            cells=cells,
            schedule_digest=digest(cells),
            cohort_seal=None,
            task_count=64,
            source_multiset_count=1,
            cell_count=1024,
            replication_execution_authorized=False,
        )
    )


class Inputs:
    """Constructed only by the fixed public or independently sealed loader."""

    __slots__ = ("_raw", "_seal", "_cell_raw", "_task_raw")

    def __init__(self, *args):
        raise TypeError("use load_inputs; arbitrary dictionaries are not admission")

    def __setattr__(self, name, value):
        raise AttributeError("execution inputs are immutable")

    @property
    def manifest(self):
        return core.parse_canonical(self._raw)

    @property
    def cells(self):
        return [core.parse_canonical(raw) for raw in self._cell_raw]

    def revalidate(self):
        if self._seal is not None:
            self._seal.revalidate()
        else:
            require(self._raw == canonical(public_manifest()), "public inputs changed")

    def arguments(self, cell):
        require(
            type(cell) is dict and type(cell.get("cell_index")) is int,
            "plain indexed cell required",
        )
        index = cell["cell_index"]
        require(
            0 <= index < 1024 and canonical(cell) == self._cell_raw[index],
            "complete execution cell differs",
        )
        key = cell["cell_key"]
        task = core.parse_canonical(self._task_raw[key["task_slot"]])
        return dict(
            task=q.CountdownTask(tuple(task["inputs"]), task["target"]),
            proposal=q.PROPOSAL,
            method=q.method(key["scale"]),
            budget_profile=q.profile(key["budget"]),
            exploration_seed=key["seed"],
        )


def load_inputs(mode):
    storage.mode_identity(mode)
    sealed = None
    if mode == PUBLIC:
        value = public_manifest()
    else:
        sealed = admission.load_seal(admission.COHORT_PATH)
        seal = sealed.manifest
        value = digested(
            dict(
                schema_version=DOMAIN + "/sealed-inputs",
                execution_mode=REPLICATION,
                experiment_id=storage.REPLICATION_ID,
                contract_digest=seal["contract"]["deterministic_digest"],
                tasks=seal["cohort"]["tasks"],
                cells=seal["cells"],
                schedule_digest=seal["schedule_digest"],
                cohort_seal=dict(
                    path=str(admission.COHORT_PATH),
                    seal_digest=seal["deterministic_digest"],
                    seal_sha256=q.sha(canonical(seal)),
                    cohort_digest=seal["cohort"]["deterministic_digest"],
                ),
                task_count=64,
                source_multiset_count=64,
                cell_count=1024,
                replication_execution_authorized=False,
            )
        )
    result = object.__new__(Inputs)
    object.__setattr__(result, "_raw", canonical(value))
    object.__setattr__(result, "_seal", sealed)
    object.__setattr__(result, "_cell_raw", tuple(canonical(c) for c in value["cells"]))
    object.__setattr__(result, "_task_raw", tuple(canonical(t) for t in value["tasks"]))
    result.revalidate()
    return result


def oid(value):
    require(
        type(value) is str and re.fullmatch(r"[0-9a-f]{40}", value) is not None,
        "full lowercase commit OID required",
    )
    require(
        core.git_bytes(ROOT, "cat-file", "-t", value) == b"commit\n",
        "commit object required",
    )
    return value


def attest(revision=None):
    source = admission.source_receipt(revision)
    approved = source["admission_revision"]
    core.require_ancestor(ROOT, BASE, approved)
    require(Path(__file__).resolve() == ROOT / SCRIPT, "connector origin differs")
    for module, path in (
        (admission, ADMISSION),
        (storage, STORAGE),
        (analysis, ANALYSIS),
        (storage.base, storage.STORAGE),
    ):
        public._origin(module, path)
    files, snapshots = {}, []
    head = core.git_head(ROOT)
    for path in (SCRIPT, STORAGE, ANALYSIS):
        item = snapshot_file(ROOT / path)
        require(
            item.raw
            == core._regular_git_blob(ROOT, approved, path)
            == core._regular_git_blob(ROOT, head, path),
            "connector source bytes differ",
        )
        files[path] = dict(byte_count=len(item.raw), sha256=q.sha(item.raw))
        snapshots.append(item)
    for item in snapshots:
        item.revalidate()
    require(
        head == core.git_head(ROOT)
        and canonical(admission.source_receipt(approved)) == canonical(source),
        "connector source changed during attestation",
    )
    return digested(
        dict(
            schema_version=DOMAIN + "/source",
            execution_revision=approved,
            admission_source=source,
            connector_files=files,
        )
    )


def environment(revision=None):
    # Admission is qualified inside this NEW connector, not by importing an old
    # 192-cell receipt. Every independent process verifies historical identity
    # orders, the fixed PUBLIC evidence, source/runtime and the 32-trace baseline.
    proof = admission.context(revision)
    source = attest(proof["source"]["admission_revision"])
    result = dict(
        source=source,
        runtime=proof["runtime"],
        baseline=public.qualify_baseline(),
        authorities=proof["authorities"],
        admission_proof=proof,
    )
    check_environment(result)
    return result


def check_environment(env):
    admission.revalidate_context(env["admission_proof"])
    require(
        canonical(attest(env["source"]["execution_revision"]))
        == canonical(env["source"]),
        "connector source changed",
    )
    require(
        canonical(public.runtime_receipt()) == canonical(env["runtime"]),
        "runtime changed",
    )


def candidate(inputs, output, env, qualification):
    value = inputs.manifest
    mode = value["execution_mode"]
    require((qualification is None) is (mode == PUBLIC), "qualification mode differs")
    return digested(
        dict(
            schema_version=DOMAIN
            + (
                "/public-authorization-candidate"
                if mode == PUBLIC
                else "/authorization-candidate"
            ),
            status="REVIEW_AND_EXPLICIT_CONFIRMATION_REQUIRED",
            execution_mode=mode,
            experiment_id=storage.mode_identity(mode),
            input_manifest_digest=value["deterministic_digest"],
            contract_digest=value["contract_digest"],
            schedule_digest=value["schedule_digest"],
            cohort_seal=value["cohort_seal"],
            **env,
            connector_qualification=qualification,
            output_path=str(output),
            output_parent=storage.parent_binding(output),
            expected_cell_count=1024,
            candidate_is_execution_authority=False,
            requires_explicit_digest_confirmation=True,
            locked_128_evaluation_authorized=False,
        )
    )


def auth_shape(raw, mode, confirmed):
    value = core.parse_canonical(raw)
    core.require_digest(value)
    storage.mode_identity(mode)
    suffix = (
        "/public-authorization-candidate"
        if mode == PUBLIC
        else "/authorization-candidate"
    )
    require(
        set(value) == AUTH_FIELDS
        and value["schema_version"] == DOMAIN + suffix
        and value["execution_mode"] == mode
        and value["experiment_id"] == storage.mode_identity(mode),
        "authorization domain differs",
    )
    require(
        type(confirmed) is str and confirmed == value["deterministic_digest"],
        "explicit authorization digest differs",
    )
    require(
        value["candidate_is_execution_authority"] is False
        and value["requires_explicit_digest_confirmation"] is True
        and value["locked_128_evaluation_authorized"] is False
        and value["status"] == "REVIEW_AND_EXPLICIT_CONFIRMATION_REQUIRED"
        and type(value["expected_cell_count"]) is int
        and value["expected_cell_count"] == 1024,
        "candidate authority flags differ",
    )
    require(
        all(
            type(value[key]) is dict
            for key in (
                "source",
                "runtime",
                "baseline",
                "authorities",
                "admission_proof",
                "output_parent",
            )
        ),
        "authorization environment objects required",
    )
    return value


def reviewed_file(snapshot, reviewed):
    path = Path(snapshot.path)
    require(path.is_relative_to(ROOT), "reviewed file must be in this checkout")
    relative = str(path.relative_to(ROOT))
    require(
        snapshot.raw
        == core._regular_git_blob(ROOT, reviewed, relative)
        == core._regular_git_blob(ROOT, core.git_head(ROOT), relative),
        "candidate/evidence is not identical reviewed Git bytes",
    )
    snapshot.revalidate()


class Admission:
    def __init__(
        self, inputs, auth, snapshot, env, reviewed, head, qualification_check
    ):
        self.inputs, self.auth, self.snapshot, self.env = inputs, auth, snapshot, env
        self.reviewed, self.head, self.qualification_check = (
            reviewed,
            head,
            qualification_check,
        )

    def revalidate(self):
        self.snapshot.revalidate()
        self.inputs.revalidate()
        if self.auth["execution_mode"] == REPLICATION:
            reviewed_file(self.snapshot, self.reviewed)
        self.qualification_check()
        check_environment(self.env)


def admit(mode, auth_path, confirmed, reviewed, execution_head=None):
    # Reject domain, digest and unreviewed bytes BEFORE any replication regeneration.
    snapshot = snapshot_file(Path(auth_path).absolute())
    auth = auth_shape(snapshot.raw, mode, confirmed)
    output = public._output(auth["output_path"])
    require(str(output) == auth["output_path"], "output alias differs")
    reviewed = oid(reviewed)
    head = oid(execution_head or core.git_head(ROOT))
    core.require_ancestor(ROOT, reviewed, head)
    core.require_ancestor(ROOT, head, core.git_head(ROOT))
    revision = oid(auth["source"]["execution_revision"])
    core.require_ancestor(ROOT, revision, reviewed)
    if mode == REPLICATION:
        reviewed_file(snapshot, reviewed)
    qualification, qualifier_check = None, lambda: None
    if mode == REPLICATION:
        reference = auth["connector_qualification"]
        require(type(reference) is dict, "public connector qualification required")
        qualification, env, qualifier_check = qualified_public(
            reference["summary_path"], reviewed
        )
        require(
            canonical(qualification) == canonical(reference),
            "public qualification differs",
        )
    else:
        require(
            auth["connector_qualification"] is None,
            "public mode cannot borrow authority",
        )
        env = environment(revision)
    # Check all environment/path fields before the positive sealed-input loader.
    for name, value in env.items():
        require(
            canonical(auth[name]) == canonical(value),
            "authorization environment differs",
        )
    require(
        canonical(storage.parent_binding(output)) == canonical(auth["output_parent"]),
        "authorized parent changed",
    )
    inputs = load_inputs(mode)
    require(
        snapshot.raw == canonical(candidate(inputs, output, env, qualification)),
        "independently reconstructed authorization differs",
    )
    result = Admission(inputs, auth, snapshot, env, reviewed, head, qualifier_check)
    result.revalidate()
    return result


def prepare(mode, output, auth_path, qualification_path=None):
    output, auth_path = public._output(output), public._output(auth_path)
    require(
        output != auth_path
        and not os.path.lexists(output)
        and not os.path.lexists(auth_path),
        "candidate/output slot occupied or overlapping",
    )
    storage.descriptor_preflight()
    if mode == REPLICATION:
        require(
            qualification_path is not None, "verified public connector summary required"
        )
        qualification, env, check_qualifier = qualified_public(qualification_path)
    else:
        require(mode == PUBLIC and qualification_path is None, "prepare mode differs")
        qualification, env, check_qualifier = None, environment(), lambda: None
    inputs = load_inputs(mode)
    value = candidate(inputs, output, env, qualification)

    def check():
        require(not os.path.lexists(output), "output became occupied")
        require(
            canonical(storage.parent_binding(output))
            == canonical(value["output_parent"]),
            "output parent changed",
        )
        inputs.revalidate()
        check_qualifier()
        check_environment(env)

    storage.base._publish_summary(auth_path, value, check)
    return value


def binding(admitted, claim):
    auth = admitted.auth
    return storage.frozen_binding(
        digested(
            dict(
                schema_version=DOMAIN + "/run-binding",
                execution_mode=auth["execution_mode"],
                experiment_id=auth["experiment_id"],
                input_manifest_digest=auth["input_manifest_digest"],
                authorization=auth,
                authorization_path=str(admitted.snapshot.path),
                reviewed_revision=admitted.reviewed,
                execution_head_revision=admitted.head,
                claim=claim,
                replication_execution_authorized=auth["execution_mode"] == REPLICATION,
            )
        )
    )


def record(inputs, cell, run_binding):
    result = q.run_countdown_track_a_search(**inputs.arguments(cell))
    return digested(
        dict(
            schema_version=DOMAIN + "/record",
            **cell,
            run_binding_digest=run_binding["deterministic_digest"],
            search_record=result.record,
        )
    )


def replay(inputs, rows, run_binding):
    require(
        type(rows) is list and len(rows) == 1024, "complete 1024-cell matrix required"
    )
    # ALL envelopes and full scientific identities before even the FIRST replay.
    cells = inputs.cells
    for cell, row in zip(cells, rows):
        storage.record_bytes(cell["cell_index"], row, run_binding)
        require(
            canonical({name: row[name] for name in cell}) == canonical(cell),
            "complete ordered cell schedule differs",
        )
        require(
            canonical(row["search_record"].get("run_identity"))
            == canonical(q.build_search_run_identity(**inputs.arguments(cell))),
            "search identity differs",
        )
    records, receipts = {}, []
    for coordinate, cell, row in zip(k.COORDINATES, cells, rows):
        args = inputs.arguments(cell)
        identity = digest(q.build_search_run_identity(**args))
        raw = canonical(row["search_record"])
        reproduced = q.replay_countdown_track_a_search_bytes(
            raw, **args, expected_run_identity_digest=identity
        )
        require(raw == reproduced, "replayed bytes differ")
        trace = q.validate_trace_bytes(reproduced)
        budget = q.validate_budget(trace, args["budget_profile"])
        records[coordinate] = trace
        receipts.append(
            dict(
                cell_index=cell["cell_index"],
                cell_id=cell["cell_id"],
                record_digest=row["deterministic_digest"],
                run_identity_digest=identity,
                trace_sha256=q.sha(raw),
                trace_byte_count=len(raw),
                budget_evidence=budget,
                replay=dict(stage1_generative="PASS", stage2_byte_identical="PASS"),
            )
        )
    indexed, pairs = dict(zip(k.COORDINATES, cells)), []
    for slot, scale, seed in product(range(64), q.SCALES, q.SEEDS):
        low, high = (slot, 256, scale, seed), (slot, 512, scale, seed)
        pairs.append(
            dict(
                task_slot=slot,
                scale=scale,
                seed=seed,
                low_cell_id=indexed[low]["cell_id"],
                high_cell_id=indexed[high]["cell_id"],
                **k.prefix_pair(records[low], records[high]),
            )
        )
    return records, digested(
        dict(
            schema_version=DOMAIN + "/integrity-analysis",
            cell_count=1024,
            replayed_trace_count=1024,
            budget_prefix_check_count=512,
            cell_receipts=receipts,
            budget_prefix_checks=pairs,
            provider_calls=0,
            status="REPLAY_AND_PREFIX_PASS",
        )
    )


def reduce_rows(inputs, rows, run_binding, observer=None):
    observe = observer or (lambda stage: None)
    observe(analysis.STAGES[1])
    records, integrity = replay(inputs, rows, run_binding)
    observe(analysis.STAGES[2])
    reduced = analysis.reduce_matrix(inputs, records, stage_observer=observe)
    replication = run_binding["execution_mode"] == REPLICATION
    decision = None
    if replication:
        decision = (
            "SOURCE_DISJOINT_REPLICATION_SCREEN_PASS"
            if reduced["exact_success"]["screen_conjunction"]
            else "STOP_REPAIR_REPLICATION_SCREEN_NOT_MET"
        )
    return digested(
        dict(
            schema_version=DOMAIN + "/execution-receipt",
            status="CONNECTOR_INTEGRITY_AND_REDUCTION_PASS",
            execution_mode=run_binding["execution_mode"],
            run_binding_digest=run_binding["deterministic_digest"],
            integrity=integrity,
            reduction=reduced,
            replication_cells_executed=1024 if replication else 0,
            replication_execution_authorized=replication,
            scientific_decision=decision,
            locked_128_evaluation_authorized=False,
        )
    )


def run(mode, auth_path, confirmed, reviewed, progress=None):
    initial = snapshot_file(Path(auth_path).absolute())
    initial_auth = auth_shape(initial.raw, mode, confirmed)
    if os.path.lexists(storage.claim_path(initial_auth)):
        raise storage.ExecutionFailure(
            "AUTHORIZATION_ALREADY_SPENT",
            True,
            "occupied study claim; no input regeneration or retry",
        )
    storage.descriptor_preflight()
    admitted = admit(mode, auth_path, confirmed, reviewed)
    initial.revalidate()
    output = public._output(admitted.auth["output_path"])
    require(not os.path.lexists(output), "output occupied; no retry or adoption")
    admitted.revalidate()
    claim, snapshot = storage.consume(
        admitted.auth, admitted.reviewed, admitted.head, core.FileSnapshot
    )
    try:
        run_binding = binding(admitted, claim)

        def check():
            snapshot.revalidate()
            require(
                canonical(storage.parent_binding(output))
                == canonical(admitted.auth["output_parent"]),
                "authorized parent changed",
            )
            admitted.revalidate()

        def action(emit):
            rows = []
            for cell in admitted.inputs.cells:
                row = record(admitted.inputs, cell, run_binding)
                emit(cell["cell_index"], row)
                rows.append(row)
                if progress is not None:
                    progress(len(rows))
            return reduce_rows(admitted.inputs, rows, run_binding)

        return storage.publish(output, run_binding, action, check)
    except storage.ExecutionFailure:
        raise
    except BaseException as error:
        raise storage.ExecutionFailure(
            "SPENT_NOT_RUN",
            True,
            "authorization consumed; retain claim and publication",
        ) from error


def analyze(mode, output):
    publication = storage.inspect(public._output(output))
    b = publication.binding
    require(b["execution_mode"] == mode, "analysis mode differs")
    admitted = admit(
        mode,
        b["authorization_path"],
        b["authorization"]["deterministic_digest"],
        b["reviewed_revision"],
        b["execution_head_revision"],
    )
    claim = storage.inspect_claim(b, core.FileSnapshot)
    require(
        canonical(binding(admitted, b["claim"])) == canonical(b),
        "admitted binding differs",
    )

    def check():
        publication.revalidate()
        claim.revalidate()
        admitted.revalidate()

    check()
    receipt = reduce_rows(admitted.inputs, publication.rows, b)
    require(
        canonical(receipt) == canonical(publication.receipt),
        "independent receipt differs",
    )
    check()
    value = digested(
        dict(
            schema_version=DOMAIN + "/analysis",
            status="CONNECTOR_INDEPENDENT_ANALYSIS_PASS",
            execution_mode=mode,
            experiment_id=storage.mode_identity(mode),
            output_path=str(public._output(output)),
            execution_commit_digest=publication.commit["deterministic_digest"],
            execution_receipt_digest=receipt["deterministic_digest"],
            run_binding_digest=b["deterministic_digest"],
            authorization_digest=admitted.auth["deterministic_digest"],
            authorization_consumed=True,
            input_manifest_digest=admitted.inputs.manifest["deterministic_digest"],
            environment=admitted.env,
            integrity=receipt["integrity"],
            reduction=receipt["reduction"],
            task_count=64,
            source_multiset_count=1 if mode == PUBLIC else 64,
            replication_cells_executed=receipt["replication_cells_executed"],
            replication_execution_authorized=mode == REPLICATION,
            scientific_decision=receipt["scientific_decision"],
            locked_128_evaluation_authorized=False,
            claim_boundary=(
                "public single-source connector qualification only; no replication or causal evidence"
                if mode == PUBLIC
                else "64 source-distinct task clusters; finite-cohort replication engineering screen only; no population inference, causal or further execution authority"
            ),
        )
    )
    return value, check


def analyze_and_save(mode, output, summary_path):
    summary_path = public._output(summary_path)
    require(not os.path.lexists(summary_path), "summary occupied")
    value, check = analyze(mode, output)
    storage.base._publish_summary(summary_path, value, check)
    return value


def verify(mode, output, summary_path):
    snapshot = snapshot_file(Path(summary_path).absolute())
    saved = core.parse_canonical(snapshot.raw)
    core.require_digest(saved)
    require(
        saved.get("schema_version") == DOMAIN + "/analysis"
        and saved.get("execution_mode") == mode,
        "summary domain differs",
    )
    value, check = analyze(mode, output)
    require(
        canonical(value) == snapshot.raw,
        "saved summary is not independently reproduced",
    )
    snapshot.revalidate()
    check()
    return value


def qualified_public(summary_path, reviewed=None):
    snapshot = snapshot_file(Path(summary_path).absolute())
    saved = core.parse_canonical(snapshot.raw)
    core.require_digest(saved)
    require(
        saved.get("schema_version") == DOMAIN + "/analysis"
        and saved.get("execution_mode") == PUBLIC
        and saved.get("scientific_decision") is None
        and saved.get("replication_cells_executed") == 0,
        "only a connector PUBLIC summary may qualify replication",
    )
    if reviewed is not None:
        reviewed_file(snapshot, reviewed)
    fresh, check_analysis = analyze(PUBLIC, saved["output_path"])
    require(
        canonical(fresh) == snapshot.raw,
        "public connector qualification did not reproduce",
    )

    def check():
        snapshot.revalidate()
        if reviewed is not None:
            reviewed_file(snapshot, reviewed)
        check_analysis()

    check()
    reference = dict(
        summary_path=str(snapshot.path),
        summary_sha256=q.sha(snapshot.raw),
        summary_digest=fresh["deterministic_digest"],
        output_path=fresh["output_path"],
        commit_digest=fresh["execution_commit_digest"],
        source_digest=fresh["environment"]["source"]["deterministic_digest"],
    )
    return reference, fresh["environment"], check


def self_test():
    inputs = load_inputs(PUBLIC)
    require(
        len(inputs.cells) == 1024 and len({c["cell_id"] for c in inputs.cells}) == 1024,
        "public identity matrix differs",
    )
    for cell in inputs.cells:
        inputs.arguments(cell)
    try:
        auth_shape(canonical(k.fixture_manifest()), REPLICATION, "0" * 64)
    except (ValueError, KeyError):
        pass
    else:
        raise ValueError("public manifest accepted as replication authority")
    return dict(
        status="CONNECTOR_IDENTITY_SELF_TEST_PASS",
        public_cells=1024,
        replication_tasks_generated=0,
        search_calls=0,
        authorization_consumed=False,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_mutually_exclusive_group(required=True)
    for command in (
        "self-test",
        "manifest",
        "prepare-public",
        "prepare-replication",
        "run-public",
        "run-replication",
        "analyze-public",
        "analyze-replication",
        "verify-public",
        "verify-replication",
    ):
        commands.add_argument("--" + command, action="store_true")
    for name in (
        "output",
        "authorization",
        "confirm-digest",
        "reviewed-revision",
        "summary",
        "qualification",
    ):
        parser.add_argument("--" + name)
    args = vars(parser.parse_args())
    command = next(c for c, v in args.items() if v is True)
    allowed = {
        "self_test": set(),
        "manifest": set(),
        "prepare_public": {"output", "authorization"},
        "prepare_replication": {"output", "authorization", "qualification"},
        "run_public": {"authorization", "confirm_digest", "reviewed_revision"},
        "run_replication": {"authorization", "confirm_digest", "reviewed_revision"},
        "analyze_public": {"output", "summary"},
        "analyze_replication": {"output", "summary"},
        "verify_public": {"output", "summary"},
        "verify_replication": {"output", "summary"},
    }[command]
    actual = {
        name
        for name in (
            "output",
            "authorization",
            "confirm_digest",
            "reviewed_revision",
            "summary",
            "qualification",
        )
        if args[name] is not None
    }
    if actual != allowed:
        parser.error("exact mode-specific argument set required")
    mode = REPLICATION if command.endswith("replication") else PUBLIC
    completed = False
    try:
        if command == "self_test":
            result = self_test()
        elif command == "manifest":
            result = public_manifest()
        elif command.startswith("prepare_"):
            result = prepare(
                mode, args["output"], args["authorization"], args["qualification"]
            )
        elif command.startswith("run_"):
            result = run(
                mode,
                args["authorization"],
                args["confirm_digest"],
                args["reviewed_revision"],
                progress=lambda count: (
                    print(
                        canonical(
                            dict(
                                status="CONNECTOR_CELL_PROGRESS",
                                completed=count,
                                expected=1024,
                            )
                        )
                        .decode()
                        .strip(),
                        file=sys.stderr,
                        flush=True,
                    )
                    if count % 32 == 0
                    else None
                ),
            )
        elif command.startswith("analyze_"):
            result = analyze_and_save(mode, args["output"], args["summary"])
        else:
            result = verify(mode, args["output"], args["summary"])
        completed = True
        visible = (
            result
            if command in ("manifest", "self_test")
            else dict(
                status=result["status"],
                deterministic_digest=result["deterministic_digest"],
                execution_mode=mode,
                expected_cell_count=1024,
                replication_cells_executed=result.get(
                    "replication_cells_executed",
                    1024 if command == "run_replication" else 0,
                ),
                scientific_decision=result.get("scientific_decision"),
                candidate_is_execution_authority=False,
            )
        )
        print(canonical(visible).decode(), end="", flush=True)
        return 0
    except BaseException as error:
        if completed:
            # The operation already returned success. A closed stdout cannot
            # countermand its durable claim/publication or imply NOT_RUN.
            status = "RESULT_DELIVERY_UNCERTAIN"
            consumed = command.startswith(("run_", "analyze_", "verify_"))
        elif isinstance(error, storage.ExecutionFailure):
            status, consumed = error.status, error.authorization_consumed
        elif isinstance(error, storage.base.PublicationUncertain):
            status = "PUBLICATION_UNCERTAIN"
            consumed = True if command.startswith("analyze_") else None
        else:
            status = (
                "INVALID_ANALYSIS"
                if command.startswith(("analyze_", "verify_"))
                else "NOT_RUN"
            )
            consumed = None
        result = dict(
            status=status,
            error_type=type(error).__name__,
            reason=str(error),
            scientific_decision=None,
            authorization_consumed=consumed,
            locked_128_evaluation_authorized=False,
        )
        print(canonical(result).decode(), end="", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
