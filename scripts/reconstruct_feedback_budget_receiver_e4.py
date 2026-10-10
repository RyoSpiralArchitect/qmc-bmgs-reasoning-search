#!/usr/bin/env python3
"""Fixed E4 original-study reconstruction; never admission or execution.

Fresh-process verification repeats the entire numerical path. Saved observations
are comparison targets only, not proofs, resume tokens or execution authority.
"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import sys
from types import MappingProxyType


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = "scripts/reconstruct_feedback_budget_receiver_e4.py"
TEST = "tests/test_feedback_budget_receiver_e4.py"
POLICY = "docs/strategy/countdown_feedback_budget_receiver_e4.md"
SOURCE_FILES = (SCRIPT, TEST, POLICY)
BASE = "64180f80d6712afd15793ab17fca5ae0ac883240"
PREVIOUS_SCRIPT = "scripts/replay_feedback_budget_receiver_e3_public.py"
PREVIOUS_REVISION = "575fee9a235779ac982ab13be2f10577474a6c84"
PREVIOUS_DIGEST = "b04934e1fb1d9e69bd78135ceded8f305bac38615e56fc6f838699e41b424aff"
PRIOR = "docs/qualifications/countdown_feedback_budget_receiver_e3_public_replay_20261008.observation.json"
PRIOR_REFERENCE = MappingProxyType(
    dict(
        path=PRIOR,
        reviewed_revision=BASE,
        byte_count=197823,
        sha256="924e1118ca0861d336b5266a2b809f0fb784ae31a446a3ab08d879e7a13f7fb3",
        deterministic_digest="c2ad3d97bd1e2ee30dcf255c2b5a1ca10faf0b533256862994ad484492564c3c",
    )
)
SAVED = ROOT / "artifacts/work/feedback-budget-receiver-e4-20261010.observation.json"
SPEC = importlib.util.spec_from_file_location(
    "receiver_e4_previous_replay", ROOT / PREVIOUS_SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
P = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = P
SPEC.loader.exec_module(P)
E, V, C, B, R, S, core = P.E, P.V, P.C, P.B, P.R, P.S, P.core
M = B.M
canonical, parse, require, digested, sha, exact = (
    P.canonical,
    P.parse,
    P.require,
    P.digested,
    P.sha,
    P.exact,
)
archive_for = P.archive_for
historical_authorization = P.historical_authorization
historical_summary = P.historical_summary
reference = P.reference
DOMAIN = S.DOMAIN + "/receiver-e4-reconstruction/v1"
CURRENT_DEVICE = 16777234
LABELS = ("original_public", "receiver_v2_public")
STATUS = "ORIGINAL_STUDY_FULLY_RECONSTRUCTED_NOT_ADMITTED"
CLAIM_BOUNDARY = "Fixed E4 environment, two retained PUBLIC reconstructions and original sealed 64-source generation/acceptance/rejection reconstruction only. Historical qualification remains historical. No current receiver admission, certificate, candidate, new PUBLIC exercise, new integration qualification, consent, replication-policy search or production execution."


def closed_source(files):
    require(
        SOURCE_FILES == (SCRIPT, TEST, POLICY) and len(SOURCE_FILES) == 3,
        "E4 source registry differs",
    )
    require(
        type(files) is dict and set(files) == {SCRIPT, TEST, POLICY},
        "exact E4 source closure required",
    )


def attest(revision):
    revision, head = R.oid(revision), core.git_head(ROOT)
    core.require_ancestor(ROOT, BASE, revision)
    core.require_ancestor(ROOT, revision, head)
    require(Path(__file__).resolve() == ROOT / SCRIPT, "E4 source origin differs")
    R.public._origin(P, PREVIOUS_SCRIPT)
    previous = P.attest(PREVIOUS_REVISION)
    require(
        previous["deterministic_digest"] == PREVIOUS_DIGEST,
        "frozen E3 replay source differs",
    )
    files, snapshots = {}, []
    for relative in SOURCE_FILES:
        item = R.snapshot_file(ROOT / relative)
        R.reviewed_file(item, revision)
        files[relative] = dict(byte_count=len(item.raw), sha256=sha(item.raw))
        snapshots.append(item)
    closed_source(files)
    for item in snapshots:
        item.revalidate()
    require(core.git_head(ROOT) == head, "HEAD changed during E4 attestation")
    return digested(
        dict(
            schema_version=DOMAIN + "/source",
            implementation_revision=revision,
            case_base_revision=BASE,
            files=files,
            previous_replay_source=previous,
        )
    )


def prior_observation(evidence, source):
    item = evidence.file(ROOT / PRIOR)
    R.reviewed_file(item, BASE)
    require(
        len(item.raw) == PRIOR_REFERENCE["byte_count"]
        and sha(item.raw) == PRIOR_REFERENCE["sha256"],
        "pinned E3 PUBLIC observation bytes differ",
    )
    value = parse(item.raw)
    core.require_digest(value)
    require(
        value["deterministic_digest"] == PRIOR_REFERENCE["deterministic_digest"]
        and value["status"] == P.STATUS
        and value["reconstruction_head"] == PREVIOUS_REVISION,
        "pinned E3 PUBLIC observation identity differs",
    )
    exact(value["source"], source["previous_replay_source"], "pinned E3 source differs")
    return value


def current_locations():
    locations = V.current_locations()
    require(
        type(locations) is dict and set(locations) == set(V.LOCATIONS),
        "exact six current roles required",
    )
    for role, path in V.LOCATIONS.items():
        V.location(locations[role], path, CURRENT_DEVICE)
    return locations


def correspondence(chains, e2_locations, e3_locations, locations):
    """Pure direct comparator; repeated device numbers do not identify an epoch."""
    require(
        type(chains) is list and len(chains) == len(V.REGISTRY),
        "exact eleven original chains required",
    )
    for values in (e2_locations, e3_locations, locations):
        require(
            type(values) is dict and set(values) == set(V.LOCATIONS),
            "exact six location roles required",
        )
    prefixes = {}

    def bind(value, role, epoch, device):
        value = V.location(value, V.LOCATIONS[role], device)
        table = prefixes.setdefault(epoch, {})
        parts = Path(value["path"]).parts
        for index, pair in enumerate(value["identities"]):
            prefix = str(Path(*parts[: index + 1]))
            require(
                prefix not in table or table[prefix] == pair,
                "shared prefix identity differs",
            )
            table[prefix] = pair
        return value

    def compare(old, role):
        exact(
            [pair[1] for pair in old["identities"]],
            [pair[1] for pair in locations[role]["identities"]],
            "historical inode differs",
        )

    for role in V.LOCATIONS:
        bind(locations[role], role, "E4", CURRENT_DEVICE)
    counts = {epoch: 0 for epoch in V.EPOCH_DEVICES}
    for row, spec in zip(chains, V.REGISTRY):
        label, epoch, _, _, _, _, role = spec
        require(
            type(row) is dict
            and set(row) == {"label", "historical_epoch", "owner", "historical"},
            "closed original chain required",
        )
        exact(
            {key: row[key] for key in ("label", "historical_epoch", "owner")},
            dict(label=label, historical_epoch=epoch, owner=V.owner(spec)),
            "registry order, epoch or owner differs",
        )
        compare(bind(row["historical"], role, epoch, V.EPOCH_DEVICES[epoch]), role)
        counts[epoch] += 1
    observed = []
    for epoch, prior_locations, device, owner_path, reviewed in (
        ("E2_observation", e2_locations, E.PRIOR_DEVICE, E.PRIOR, E.BASE),
        ("E3_observation", e3_locations, E.CURRENT_DEVICE, PRIOR, BASE),
    ):
        for role in V.LOCATIONS:
            old = bind(prior_locations[role], role, epoch, device)
            compare(old, role)
            observed.append(
                dict(
                    historical_epoch=epoch,
                    role=role,
                    owner=dict(
                        path=owner_path,
                        reviewed_revision=reviewed,
                        json_pointer="/location_correspondence/current_locations/"
                        + role,
                    ),
                    historical=old,
                )
            )
    return parse(
        canonical(
            dict(
                policy="fixed_direct_E0_E1_E2_E3_to_E4_same_path_inode_metadata_only/v1",
                current_epoch="E4",
                epochs={
                    **{
                        epoch: dict(
                            historical_device=device,
                            observed_device=CURRENT_DEVICE,
                            chain_count=counts[epoch],
                        )
                        for epoch, device in V.EPOCH_DEVICES.items()
                    },
                    "E2_observation": dict(
                        historical_device=E.PRIOR_DEVICE,
                        observed_device=CURRENT_DEVICE,
                        chain_count=6,
                    ),
                    "E3_observation": dict(
                        historical_device=E.CURRENT_DEVICE,
                        observed_device=CURRENT_DEVICE,
                        chain_count=6,
                    ),
                },
                original_chains=chains,
                prior_observation_chains=observed,
                current_locations=locations,
                metadata_correspondence_matches=True,
                repeated_device_number_is_epoch_identity=False,
                current_receiver_admitted=False,
                physical_disk_identity_proven=False,
                reboot_causality_proven=False,
            )
        )
    )


def inspect_metadata(evidence, source, head, locations):
    prior = prior_observation(evidence, source)
    previous = source["previous_replay_source"]
    e3_environment = P.prior_observation(evidence, previous)
    e2 = E.prior_observation(evidence, previous["environment_source"])
    historical = V.historical_sources()
    cohort, archives = E.inspect_metadata(evidence, historical, e2, head)
    for old in (e3_environment, prior):
        for fresh, key in (
            (historical, "historical_source_receipts"),
            (evidence.anchors, "reviewed_anchors"),
            (cohort, "sealed_metadata"),
            (archives, "public_archive_hash_closures"),
        ):
            exact(fresh, old[key], "fresh closure differs from pinned E3: " + key)
    exact(
        prior["environment"],
        e3_environment["environment"],
        "pinned E3 environments differ",
    )
    exact(
        prior["location_correspondence"],
        e3_environment["location_correspondence"],
        "pinned E3 location histories differ",
    )
    mapping = correspondence(
        V.recorded_chains(evidence.values),
        e2["location_correspondence"]["current_locations"],
        prior["location_correspondence"]["current_locations"],
        locations,
    )
    return prior, historical, cohort, archives, mapping


def stable_state(evidence, source, head, locations, inputs=None):
    _guard()
    require(core.git_head(ROOT) == head, "E4 reconstruction HEAD changed")
    evidence.revalidate()
    exact(current_locations(), locations, "E4 receiver identity changed")
    C.unused(S.REPLICATION)
    require(
        not core.git_bytes(ROOT, "status", "--porcelain", "--untracked-files=all"),
        "E4 source checkout must remain clean",
    )
    exact(attest(source["implementation_revision"]), source, "E4 source changed")
    if inputs is not None:
        require(type(inputs) is R.Inputs, "genuine PUBLIC inputs required")
        inputs.revalidate()
    evidence.revalidate()
    exact(current_locations(), locations, "E4 receiver identity changed")
    C.unused(S.REPLICATION)
    require(core.git_head(ROOT) == head, "E4 reconstruction HEAD changed")


def revalidate(evidence, source, historical, environment, head, locations, inputs=None):
    stable_state(evidence, source, head, locations, inputs)
    exact(V.historical_sources(), historical, "historical source changed")
    R.check_environment(environment)
    stable_state(evidence, source, head, locations, inputs)


def initial_work():
    return dict(
        **P.initial_work(),
        sealed_cohort=dict(
            stage="NOT_STARTED",
            accepted_sources_completed=0,
            examined_attempts_completed=0,
            rejected_attempts_completed=0,
            cohort_reproduced=False,
            complete_seal_reproduced=False,
            complete_input_projection_reproduced=False,
        ),
    )


def progress(stage, work):
    sys.stderr.buffer.write(
        canonical(
            dict(
                schema_version=DOMAIN + "/progress",
                status="INFORMATIONAL_NOT_A_RESULT",
                stage=stage,
                work=work,
            )
        )
    )
    sys.stderr.buffer.flush()


def generation_reference(summary):
    """Pure projection of an original summary; not a qualification function."""
    require(
        summary["schema_version"] == S.DOMAIN + "/analysis"
        and summary["status"] == "CONNECTOR_INDEPENDENT_ANALYSIS_PASS"
        and summary["output_path"] == str(B.PUBLIC_OUTPUT),
        "original v7 PUBLIC summary required",
    )
    result = dict(
        summary_path=str(ROOT / B.PUBLIC_SUMMARY),
        summary_sha256=sha(canonical(summary)),
        summary_digest=summary["deterministic_digest"],
        output_path=summary["output_path"],
        commit_digest=summary["execution_commit_digest"],
        source_digest=summary["environment"]["source"]["deterministic_digest"],
    )
    M.generation_reference_shape(result)
    return result


def replay_one(label, evidence, inputs, environment, historical, work):
    require(
        label in LABELS and type(inputs) is R.Inputs,
        "genuine fixed PUBLIC inputs required",
    )
    inputs.revalidate()
    output, commit_path, summary_path, _, _ = V.PUBLIC_SPECS[label]
    archive = archive_for(evidence, label)
    archive.revalidate()
    binding = evidence.values[str(output / "STARTED.json")]["binding"]
    historical_authorization(
        label, inputs, environment, evidence.values, historical, binding
    )
    row = next(item for item in work["public_archives"] if item["label"] == label)
    require(row["stage"] == "NOT_STARTED", "no automatic replay retry or deduplication")
    rows = [
        S.parse(archive.raw[name], S.base.MAX_CELL_BYTES) for name in S.base.CELL_NAMES
    ]
    stages = []

    def observe(stage):
        require(
            len(stages) < len(R.analysis.STAGES) - 1
            and stage == R.analysis.STAGES[len(stages) + 1],
            "numerical stage order differs",
        )
        stages.append(stage)
        row["stage"] = stage
        if stage == R.analysis.STAGES[2]:
            # Frozen R.reduce_rows emits this only AFTER R.replay's full success.
            row["replayed_traces_completed"] = 1024
            row["budget_prefix_comparisons_completed"] = 512
        progress(label + ":" + stage, work)

    row.update(
        stage="ENTERING_REPLAY",
        replayed_traces_completed=None,
        budget_prefix_comparisons_completed=None,
    )
    receipt = R.reduce_rows(inputs, rows, binding, observer=observe)
    exact(
        stages,
        list(R.analysis.STAGES[1:]),
        "complete numerical stage sequence required",
    )
    exact(
        [
            receipt["execution_mode"],
            receipt["integrity"]["replayed_trace_count"],
            receipt["integrity"]["budget_prefix_check_count"],
            receipt["replication_cells_executed"],
            receipt["replication_execution_authorized"],
            receipt["scientific_decision"],
        ],
        [S.PUBLIC, 1024, 512, 0, False, None],
        "PUBLIC numerical completion differs",
    )
    fresh_receipt = canonical(receipt)
    require(
        fresh_receipt == archive.raw["RECEIPT.json"],
        "complete retained PUBLIC receipt did not reproduce",
    )
    row.update(stage="RECEIPT_REPRODUCED", receipt_reproduced=True)
    receiver_reference, fence_raw = None, None
    if label == "receiver_v2_public":
        receiver_reference = V.historical_receiver_reference(
            evidence.values, historical
        )
        fences = [item for item in evidence.snapshots if item.path == C.FENCE]
        require(len(fences) == 1, "unique authenticated v2 fence required")
        fences[0].revalidate()
        fence_raw = fences[0].raw
    summary = historical_summary(
        label,
        inputs.manifest,
        environment,
        binding,
        evidence.values[commit_path],
        receipt,
        historical,
        receiver_reference,
        fence_raw,
    )
    fresh_summary = canonical(summary)
    require(
        fresh_summary == canonical(evidence.values[summary_path]),
        "complete historical PUBLIC summary did not reproduce",
    )
    row.update(stage="SUMMARY_REPRODUCED", summary_reproduced=True)
    inputs.revalidate()
    archive.revalidate()
    progress(label + ":complete_historical_summary_reproduced", work)
    return dict(
        label=label,
        output_path=str(output),
        input_manifest_digest=inputs.manifest["deterministic_digest"],
        replayed_trace_count=1024,
        budget_prefix_check_count=512,
        complete_receipt_reproduced=True,
        complete_summary_reproduced=True,
        receipt=reference(fresh_receipt),
        summary={"path": summary_path, **reference(fresh_summary)},
        task_count=64,
        source_multiset_count=1,
        current_receiver_admitted=False,
        new_coordinator_qualified=False,
        historical_metadata_only=True,
        original_generation_reference=generation_reference(summary)
        if label == "original_public"
        else None,
    )


def cohort_archive(evidence):
    matches = [item for item in evidence.archives if item.path == M.COHORT_PATH]
    require(
        len(matches) == 1
        and type(matches[0]) is V.ReadOnlyArchive
        and matches[0].names == M.NAMES,
        "unique captured read-only original cohort required",
    )
    return matches[0]


def reconstruct_seal(evidence, environment, original_reference, work):
    """Recompute the original recipe; no old Transport, Proof or sealed loader."""
    row = work["sealed_cohort"]
    require(row["stage"] == "NOT_STARTED", "no automatic cohort reconstruction retry")
    archive = cohort_archive(evidence)
    archive.revalidate()
    raw = archive.raw["preregistration.json"]
    value, contract = parse(raw), M.contract.build_contract()
    exact(value["contract"], contract, "original sealed contract differs")
    exact(
        value["admission_context"],
        environment["admission_proof"],
        "original generation admission differs",
    )
    M.generation_reference_shape(original_reference)
    exact(
        value["generation_qualification"],
        original_reference,
        "original generation qualifier must remain original v7 PUBLIC",
    )
    M._cohort_shape(value["cohort"], contract, environment["authorities"])
    require(
        canonical(
            M._seal(
                value["cohort"],
                contract,
                environment["admission_proof"],
                original_reference,
            )
        )
        == raw,
        "closed original sealed metadata differs",
    )
    projection = B.input_projection(value)
    original = evidence.values[B.ORIGINAL_CANDIDATE]
    for key in ("contract_digest", "schedule_digest", "cohort_seal"):
        exact(projection[key], original[key], "original input projection differs")
    require(
        projection["deterministic_digest"] == original["input_manifest_digest"],
        "original input digest differs",
    )
    archive.revalidate()
    M.revalidate_context(environment["admission_proof"])
    row.update(
        stage="ENTERING_ORIGINAL_COHORT_RECONSTRUCTION",
        accepted_sources_completed=None,
        examined_attempts_completed=None,
        rejected_attempts_completed=None,
    )
    progress(row["stage"], work)
    reproduced = M._cohort(contract, environment["authorities"])
    # A returned cohort has passed the frozen _cohort_shape. Counts describe
    # completed computation even if comparison or later revalidation fails.
    manifest = reproduced["generation_manifest"]
    row.update(
        stage="COHORT_COMPUTATION_COMPLETED",
        accepted_sources_completed=len(reproduced["tasks"]),
        examined_attempts_completed=manifest["attempt_count"],
        rejected_attempts_completed=len(manifest["rejection_log"]),
    )
    exact(
        reproduced,
        value["cohort"],
        "original acceptance/rejection order did not reproduce",
    )
    row["cohort_reproduced"] = True
    fresh = M._seal(
        reproduced, contract, environment["admission_proof"], original_reference
    )
    require(canonical(fresh) == raw, "complete original sealed bytes did not reproduce")
    started = M._started(
        environment["admission_proof"],
        parse(archive.raw["STARTED.json"])["owner_nonce"],
        original_reference,
    )
    require(
        canonical(started) == archive.raw["STARTED.json"]
        and canonical(M._closed(started, fresh)) == archive.raw["SEALED.json"],
        "complete original seal transaction differs",
    )
    row.update(stage="COMPLETE_SEAL_REPRODUCED", complete_seal_reproduced=True)
    fresh_inputs = B.input_projection(fresh)
    exact(fresh_inputs, projection, "complete original input projection differs")
    row.update(
        stage="COMPLETE_ORIGINAL_INPUT_REPRODUCED",
        complete_input_projection_reproduced=True,
    )
    archive.revalidate()
    M.revalidate_context(environment["admission_proof"])
    progress(row["stage"], work)
    return dict(
        original_generation_reference=original_reference,
        generation_manifest=manifest,
        complete_cohort_reproduced=True,
        complete_three_file_seal_reproduced=True,
        complete_input_projection_reproduced=True,
        sealed_files={name: reference(archive.raw[name]) for name in sorted(M.NAMES)},
        cohort=reference(canonical(reproduced)),
        input_projection=reference(canonical(fresh_inputs)),
        schedule_digest=fresh["schedule_digest"],
        task_count=len(reproduced["tasks"]),
        source_multiset_count=fresh_inputs["source_multiset_count"],
        cell_count=len(fresh_inputs["cells"]),
        accepted_sources=manifest["accepted_count"],
        examined_attempts=manifest["attempt_count"],
        rejected_attempts=len(manifest["rejection_log"]),
        cohort_conditioned_on_exhaustive_solvability=True,
        persisted_calibration_profile_count=reproduced[
            "persisted_calibration_profile_count"
        ],
        persisted_solution_witness_count=reproduced["persisted_solution_witness_count"],
        replication_policy_search_calls=0,
        new_cohort_published=False,
        current_receiver_admitted=False,
    )


def ceiling(status="NOT_PERFORMED"):
    return dict(
        reconstruction_status=status,
        current_receiver_admitted=False,
        new_coordinator_qualified=False,
        certificate_issued=False,
        candidate_issued=False,
        new_public_attempts=0,
        new_cohort_published=False,
        replication_policy_search_calls=0,
        replication_cells_executed=0,
        replication_execution_authorized=False,
        locked_128_evaluation_authorized=False,
        physical_disk_identity_proven=False,
        reboot_causality_proven=False,
    )


class ReconstructionFailure(Exception):
    def __init__(self, cause, phase, work):
        super().__init__(str(cause))
        self.cause, self.phase, self.work = cause, phase, parse(canonical(work))


def reconstruct(revision):
    phase, work = "scope_and_source", initial_work()
    try:
        _guard()
        C.unused(S.REPLICATION)
        head, locations = core.git_head(ROOT), current_locations()
        progress(phase, work)
        source, evidence = attest(revision), V.Evidence()
        phase = "authenticated_historical_metadata"
        prior, historical, cohort, archives, mapping = inspect_metadata(
            evidence, source, head, locations
        )
        stable_state(evidence, source, head, locations)
        phase = "genuine_environment"
        work["baseline_traces_completed"] = None
        progress(phase, work)
        environment = R.environment(B.ORIGINAL_SOURCE)
        # The genuine lower environment returns only after its baseline passes.
        # Keep that completed work if a later historical comparison rejects.
        work["baseline_traces_completed"] = 32
        E.compare_environment(environment, evidence.values[B.ORIGINAL_CANDIDATE])
        exact(
            environment,
            prior["environment"],
            "fresh environment differs from pinned E3",
        )
        progress("environment_and_32_trace_baseline_reproduced", work)
        revalidate(evidence, source, historical, environment, head, locations)
        inputs = R.load_inputs(S.PUBLIC)
        require(type(inputs) is R.Inputs, "genuine PUBLIC loader required")
        replays = []
        for label in LABELS:
            phase = label
            stable_state(evidence, source, head, locations, inputs)
            replays.append(
                replay_one(label, evidence, inputs, environment, historical, work)
            )
            stable_state(evidence, source, head, locations, inputs)
        phase = "original_sealed_cohort_reconstruction"
        revalidate(evidence, source, historical, environment, head, locations, inputs)
        sealed = reconstruct_seal(
            evidence, environment, replays[0]["original_generation_reference"], work
        )
        phase = "final_source_runtime_evidence_revalidation"
        progress(phase, work)
        revalidate(evidence, source, historical, environment, head, locations, inputs)
        return digested(
            dict(
                schema_version=DOMAIN + "/observation",
                status=STATUS,
                source=source,
                reconstruction_head=head,
                prior_public_observation=dict(PRIOR_REFERENCE),
                historical_source_receipts=historical,
                reviewed_anchors=evidence.anchors,
                location_correspondence=mapping,
                public_archive_hash_closures=archives,
                sealed_metadata=cohort,
                environment=environment,
                work=work,
                public_replays=replays,
                public_traces_replayed=2048,
                budget_prefix_comparisons=1024,
                original_sealed_reconstruction=sealed,
                acceptance_order_reconstructed=True,
                original_study_identity=S.REPLICATION_ID,
                fixed_replication_claim_path=str(B.fixed_claim()),
                original_study_slot_absent_at_completion=True,
                claim_ceiling=ceiling("FULL_ORIGINAL_RECONSTRUCTION_ONLY"),
                claim_boundary=CLAIM_BOUNDARY,
            )
        )
    except (Exception, KeyboardInterrupt) as error:
        raise ReconstructionFailure(error, phase, work) from error


def verify_saved(revision):
    """Fixed comparison target; recompute EVERYTHING before whole-byte equality."""
    phase, result = "saved_comparator_authentication", None
    try:
        _guard()
        head = core.git_head(ROOT)
        saved = R.snapshot_file(SAVED)
        expected = parse(saved.raw)
        core.require_digest(expected)
        require(
            expected["schema_version"] == DOMAIN + "/observation"
            and expected["status"] == STATUS
            and expected["reconstruction_head"] == head,
            "same-head completed E4 comparator required",
        )
        exact(expected["source"], attest(revision), "saved comparator source differs")
        saved.revalidate()
        phase = "fresh_independent_process_reconstruction"
        result = reconstruct(revision)
        phase = "whole_result_byte_comparison"
        require(
            canonical(result) == saved.raw,
            "entire fresh reconstruction differs from saved observation",
        )
        saved.revalidate()
        _guard()
        exact(attest(revision), result["source"], "verification source changed")
        exact(
            current_locations(),
            result["location_correspondence"]["current_locations"],
            "verification receiver identity changed",
        )
        C.unused(S.REPLICATION)
        require(
            core.git_head(ROOT) == head
            and not core.git_bytes(
                ROOT, "status", "--porcelain", "--untracked-files=all"
            ),
            "verification source checkout changed",
        )
        return digested(
            dict(
                schema_version=DOMAIN + "/verification",
                status="FRESH_PROCESS_WHOLE_RESULT_BYTE_IDENTICAL_NOT_ADMITTED",
                implementation_source=result["source"],
                reconstruction_head=head,
                saved_observation=dict(path=str(SAVED), **reference(saved.raw)),
                independently_reconstructed_observation=reference(canonical(result)),
                complete_canonical_observation_byte_identical=True,
                verification_method="fresh_process_same_frozen_implementation_full_recomputation",
                algorithmically_independent_implementation=False,
                work=result["work"],
                claim_ceiling=ceiling("FULL_ORIGINAL_RECONSTRUCTION_ONLY"),
                claim_boundary=CLAIM_BOUNDARY,
            )
        )
    except ReconstructionFailure:
        raise
    except (Exception, KeyboardInterrupt) as error:
        raise ReconstructionFailure(
            error, phase, initial_work() if result is None else result["work"]
        ) from error


def failure_receipt(error, result=None):
    cause = error.cause if isinstance(error, ReconstructionFailure) else error
    work = (
        error.work
        if isinstance(error, ReconstructionFailure)
        else result["work"]
        if result is not None
        else None
    )
    return digested(
        dict(
            schema_version=DOMAIN + "/failure",
            status="E4_RECONSTRUCTION_OR_VERIFICATION_REJECTED",
            phase=error.phase
            if isinstance(error, ReconstructionFailure)
            else "result_delivery",
            reason=str(cause),
            work=work,
            authorization_consumed=cause.authorization_consumed
            if isinstance(cause, S.ExecutionFailure)
            else None,
            execution_dispatch_entered=False,
            new_effects_attempted=False,
            retain_evidence=True,
            automatic_retry_allowed=False,
            claim_ceiling=ceiling("FAILED_INCOMPLETE"),
        )
    )


def _guard():
    P._guard()
    for module, name, expected in _DEPENDENCIES:
        require(getattr(module, name) is expected, "E4 dependency substituted: " + name)


_DEPENDENCIES = tuple(
    (module, name, getattr(module, name))
    for module, names in (
        (
            P,
            (
                "attest",
                "prior_observation",
                "archive_for",
                "historical_authorization",
                "historical_summary",
                "reference",
                "initial_work",
            ),
        ),
        (E, ("prior_observation", "inspect_metadata", "compare_environment")),
        (V, ("current_locations", "location", "historical_sources", "recorded_chains")),
        (
            M,
            (
                "_cohort",
                "_cohort_shape",
                "_seal",
                "_started",
                "_closed",
                "revalidate_context",
                "generation_reference_shape",
            ),
        ),
        (M.contract, ("build_contract",)),
        (M.historical, ("generate_solvable_task_suite",)),
        (B, ("input_projection",)),
    )
    for name in names
)


def self_test():
    closed_source({name: {} for name in SOURCE_FILES})
    require(
        tuple(V.PUBLIC_SPECS) == LABELS
        and E.CURRENT_DEVICE == 16777232
        and E.PRIOR_DEVICE == CURRENT_DEVICE == 16777234,
        "frozen separate epoch registry differs",
    )
    return digested(
        dict(
            schema_version=DOMAIN + "/self-test",
            status="STATIC_SELF_TEST_ONLY",
            work=initial_work(),
            claim_ceiling=ceiling(),
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--reconstruct", action="store_true")
    mode.add_argument("--verify-saved", action="store_true")
    parser.add_argument("--implementation-revision")
    args = parser.parse_args()
    if args.self_test:
        if args.implementation_revision is not None:
            parser.error("self-test takes no implementation revision")
        sys.stdout.buffer.write(canonical(self_test()))
        return
    if args.implementation_revision is None:
        parser.error(
            "reconstruction/verification requires a full immutable implementation revision"
        )
    result = None
    try:
        result = (
            verify_saved(args.implementation_revision)
            if args.verify_saved
            else reconstruct(args.implementation_revision)
        )
        sys.stdout.buffer.write(canonical(result))
        sys.stdout.buffer.flush()
    except (Exception, KeyboardInterrupt) as error:
        sys.stderr.buffer.write(canonical(failure_receipt(error, result)))
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
