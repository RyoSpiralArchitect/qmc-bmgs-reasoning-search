#!/usr/bin/env python3
"""Fixed E3 retained-PUBLIC replay; no admission, publication or execution API.

Progress is informational JSON on stderr; the final observation is canonical
JSON on stdout. Neither is a certificate or a caller-supplied qualification.
"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import sys
from types import MappingProxyType


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = "scripts/replay_feedback_budget_receiver_e3_public.py"
TEST = "tests/test_feedback_budget_receiver_e3_public_replay.py"
POLICY = "docs/strategy/countdown_feedback_budget_receiver_e3_public_replay.md"
SOURCE_FILES = (SCRIPT, TEST, POLICY)
BASE = "790e26b17d59d31cce42a826054ddab15db8cfff"
ENVIRONMENT_SCRIPT = "scripts/check_feedback_budget_receiver_e3_environment.py"
ENVIRONMENT_REVISION = "85f90035cdfa57f75393500cae72b2aba1e96e96"
ENVIRONMENT_DIGEST = "c1ff9702b58a68eb75cb7514371626c3e599663992f5046c9700fb3c1082f435"
PRIOR = "docs/qualifications/countdown_feedback_budget_receiver_e3_environment_20261008.observation.json"
PRIOR_REFERENCE = MappingProxyType(
    dict(
        path=PRIOR,
        reviewed_revision=BASE,
        byte_count=194443,
        sha256="24f44d2ede0a2a23746e0f61fd5e1fc50be10a37a9deef3a980116b20a9a1344",
        deterministic_digest="032f4d1da89d3f3fb119dfc102e961a2467396bac6d672a69a000422d65b8cb3",
    )
)
SPEC = importlib.util.spec_from_file_location(
    "receiver_e3_replay_environment", ROOT / ENVIRONMENT_SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
E = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = E
SPEC.loader.exec_module(E)
V, C, B, R, S, core = E.V, E.C, E.B, E.R, E.S, E.core
canonical, parse, require, digested, sha, exact = (
    E.canonical,
    E.parse,
    E.require,
    E.digested,
    E.sha,
    E.exact,
)
DOMAIN = S.DOMAIN + "/receiver-e3-public-replay/v1"
LABELS = ("original_public", "receiver_v2_public")
STATUS = "RETAINED_PUBLIC_RECEIPTS_AND_SUMMARIES_REPRODUCED_NOT_ADMITTED"
CLAIM_BOUNDARY = "Fresh E3 environment and two retained PUBLIC numerical reconstructions only. Historical consumption and coordinator qualification flags remain historical. No sealed 64-source acceptance reconstruction, current admission, certificate, candidate, new PUBLIC attempt, new integration qualification, consent or replication execution."


def closed_source(files):
    require(
        SOURCE_FILES == (SCRIPT, TEST, POLICY) and len(SOURCE_FILES) == 3,
        "replay source registry differs",
    )
    require(
        type(files) is dict and set(files) == {SCRIPT, TEST, POLICY},
        "exact replay source closure required",
    )


def attest(revision):
    revision, head = R.oid(revision), core.git_head(ROOT)
    core.require_ancestor(ROOT, BASE, revision)
    core.require_ancestor(ROOT, revision, head)
    require(Path(__file__).resolve() == ROOT / SCRIPT, "replay source origin differs")
    R.public._origin(E, ENVIRONMENT_SCRIPT)
    environment_source = E.attest(ENVIRONMENT_REVISION)
    require(
        environment_source["deterministic_digest"] == ENVIRONMENT_DIGEST,
        "frozen E3 environment source differs",
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
    require(core.git_head(ROOT) == head, "HEAD changed during replay attestation")
    return digested(
        dict(
            schema_version=DOMAIN + "/source",
            implementation_revision=revision,
            base_revision=BASE,
            files=files,
            environment_source=environment_source,
        )
    )


def prior_observation(evidence, source):
    item = evidence.file(ROOT / PRIOR)
    R.reviewed_file(item, BASE)
    require(
        len(item.raw) == PRIOR_REFERENCE["byte_count"]
        and sha(item.raw) == PRIOR_REFERENCE["sha256"],
        "pinned E3 observation bytes differ",
    )
    value = parse(item.raw)  # Exact pinned Git/file bytes before parsing.
    core.require_digest(value)
    require(
        value["deterministic_digest"] == PRIOR_REFERENCE["deterministic_digest"]
        and value["status"] == E.STATUS
        and value["inspection_head"] == ENVIRONMENT_REVISION,
        "pinned E3 observation identity differs",
    )
    exact(value["source"], source["environment_source"], "pinned E3 source differs")
    return value


def inspect_metadata(evidence, source, head, locations):
    prior = prior_observation(evidence, source)
    e2 = E.prior_observation(evidence, source["environment_source"])
    historical = V.historical_sources()
    cohort, archives = E.inspect_metadata(evidence, historical, e2, head)
    mapping = E.correspondence(
        V.recorded_chains(evidence.values),
        e2["location_correspondence"]["current_locations"],
        locations,
    )
    for fresh, key in (
        (historical, "historical_source_receipts"),
        (evidence.anchors, "reviewed_anchors"),
        (cohort, "sealed_metadata"),
        (archives, "public_archive_hash_closures"),
        (mapping, "location_correspondence"),
    ):
        exact(fresh, prior[key], "fresh metadata differs from pinned E3: " + key)
    return prior, historical, cohort, archives, mapping


def stable_state(evidence, source, head, locations, inputs=None):
    _guard()
    E.stable_state(evidence, head, locations)
    exact(attest(source["implementation_revision"]), source, "replay source changed")
    if inputs is not None:
        require(type(inputs) is R.Inputs, "genuine PUBLIC inputs required")
        inputs.revalidate()
    E.stable_state(evidence, head, locations)


def archive_for(evidence, label):
    require(label in LABELS, "fixed retained PUBLIC label required")
    output = V.PUBLIC_SPECS[label][0]
    matches = [item for item in evidence.archives if item.path == output]
    require(
        len(matches) == 1
        and type(matches[0]) is V.ReadOnlyArchive
        and matches[0].names == S.NAMES,
        "unique captured read-only PUBLIC archive required",
    )
    return matches[0]


def historical_authorization(label, inputs, environment, values, historical, binding):
    """Whole nonlocation comparison; no candidate is issued or admitted."""
    require(
        label in LABELS and type(inputs) is R.Inputs, "fixed PUBLIC inputs required"
    )
    output = V.PUBLIC_SPECS[label][0]
    expected = R.candidate(inputs, output, environment, None)
    if label == "receiver_v2_public":
        expected = digested(
            {
                **B.without_digest(expected),
                "schema_version": C.DOMAIN + "/public-authorization-candidate",
                "coordinator_source": historical["coordinator"],
                "receiver_admission": V.historical_receiver_reference(
                    values, historical
                ),
                "attempt_id": C.PUBLIC_ATTEMPT,
            }
        )

    def nonlocation(value):
        return {
            key: val
            for key, val in value.items()
            if key not in ("output_parent", "deterministic_digest")
        }

    exact(
        nonlocation(expected),
        nonlocation(binding["authorization"]),
        "whole historical PUBLIC authorization differs",
    )


def historical_summary(
    label,
    manifest,
    environment,
    binding,
    commit,
    receipt,
    historical,
    receiver_reference,
    fence_raw,
):
    """Explicit whole projections; no saved summary/template is an input."""
    require(label in LABELS, "fixed summary projection required")
    require(manifest["execution_mode"] == S.PUBLIC, "PUBLIC manifest required")
    common = dict(
        execution_mode=S.PUBLIC,
        experiment_id=S.PUBLIC_ID,
        output_path=str(V.PUBLIC_SPECS[label][0]),
        execution_commit_digest=commit["deterministic_digest"],
        execution_receipt_digest=receipt["deterministic_digest"],
        run_binding_digest=binding["deterministic_digest"],
        authorization_digest=binding["authorization"]["deterministic_digest"],
        authorization_consumed=True,
        input_manifest_digest=manifest["deterministic_digest"],
        integrity=receipt["integrity"],
        reduction=receipt["reduction"],
        task_count=64,
        source_multiset_count=1,
        replication_cells_executed=0,
        replication_execution_authorized=False,
        scientific_decision=None,
        locked_128_evaluation_authorized=False,
    )
    if label == "original_public":
        require(
            fence_raw is None and receiver_reference is None,
            "original PUBLIC has no receiver fence/reference",
        )
        return digested(
            dict(
                **common,
                schema_version=S.DOMAIN + "/analysis",
                status="CONNECTOR_INDEPENDENT_ANALYSIS_PASS",
                environment=environment,
                claim_boundary="public single-source connector qualification only; no replication or causal evidence",
            )
        )
    require(
        type(fence_raw) is bytes and receiver_reference is not None,
        "historical v2 fence/reference required",
    )
    return digested(
        dict(
            **common,
            schema_version=C.DOMAIN + "/analysis",
            status="COORDINATOR_INDEPENDENT_ANALYSIS_PASS",
            attempt_id=C.PUBLIC_ATTEMPT,
            coordinator_source=historical["coordinator"],
            receiver_admission=receiver_reference,
            public_attempt_fence_sha256=sha(fence_raw),
            public_cells_executed=1024,
            public_coordinator_qualified=True,
            production_adapter_executed=False,
            claim_boundary="PUBLIC single-source shared-coordinator and PUBLIC-adapter qualification only; not old bridge run, production adapter execution, replication or causal evidence",
        )
    )


def initial_work():
    return dict(
        baseline_traces_completed=0,
        public_archives=[
            dict(
                label=label,
                stage="NOT_STARTED",
                replayed_traces_completed=0,
                budget_prefix_comparisons_completed=0,
                receipt_reproduced=False,
                summary_reproduced=False,
            )
            for label in LABELS
        ],
    )


def progress(stage, work):
    # Internal informational sink only. No caller callback or qualification result.
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


def reference(raw):
    value = parse(raw)
    core.require_digest(value)
    return dict(
        byte_count=len(raw),
        sha256=sha(raw),
        deterministic_digest=value["deterministic_digest"],
    )


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
    )


def ceiling(status="PARTIAL_ENVIRONMENT_AND_RETAINED_PUBLIC_ONLY"):
    return dict(
        reconstruction_status=status,
        acceptance_order_reconstructed=False,
        current_receiver_admitted=False,
        new_coordinator_qualified=False,
        certificate_issued=False,
        candidate_issued=False,
        new_public_attempts=0,
        replication_search_calls=0,
        replication_execution_authorized=False,
        locked_128_evaluation_authorized=False,
        physical_disk_identity_proven=False,
        reboot_causality_proven=False,
    )


class ReplayFailure(Exception):
    def __init__(self, cause, phase, work):
        super().__init__(str(cause))
        self.cause, self.phase, self.work = cause, phase, parse(canonical(work))


def reconstruct(revision):
    """Sole actual operation; saved observations cannot substitute for this path."""
    phase, work = "scope_and_source", initial_work()
    try:
        _guard()
        C.unused(S.REPLICATION)
        head, locations = core.git_head(ROOT), E.current_locations()
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
        E.compare_environment(environment, evidence.values[B.ORIGINAL_CANDIDATE])
        exact(
            environment,
            prior["environment"],
            "fresh environment differs from pinned E3",
        )
        work["baseline_traces_completed"] = 32
        progress("environment_and_32_trace_baseline_reproduced", work)
        E.revalidate(
            evidence,
            source["environment_source"],
            historical,
            environment,
            head,
            locations,
        )
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
        phase = "final_source_runtime_evidence_revalidation"
        progress(phase, work)
        E.revalidate(
            evidence,
            source["environment_source"],
            historical,
            environment,
            head,
            locations,
        )
        stable_state(evidence, source, head, locations, inputs)
        return digested(
            dict(
                schema_version=DOMAIN + "/observation",
                status=STATUS,
                source=source,
                reconstruction_head=head,
                prior_environment_observation=dict(PRIOR_REFERENCE),
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
                original_study_identity=S.REPLICATION_ID,
                fixed_replication_claim_path=str(B.fixed_claim()),
                original_study_slot_absent_at_completion=True,
                claim_ceiling=ceiling(),
                claim_boundary=CLAIM_BOUNDARY,
            )
        )
    except (Exception, KeyboardInterrupt) as error:
        raise ReplayFailure(error, phase, work) from error


def failure_receipt(error, result=None):
    cause = error.cause if isinstance(error, ReplayFailure) else error
    work = (
        error.work
        if isinstance(error, ReplayFailure)
        else result["work"]
        if result is not None
        else None
    )
    return digested(
        dict(
            schema_version=DOMAIN + "/failure",
            status="RETAINED_PUBLIC_REPLAY_REJECTED",
            phase=error.phase
            if isinstance(error, ReplayFailure)
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
    E._guard()
    for module, name, expected in _DEPENDENCIES:
        require(
            getattr(module, name) is expected, "replay dependency substituted: " + name
        )


_DEPENDENCIES = tuple(
    (module, name, getattr(module, name))
    for module, names in (
        (
            E,
            (
                "attest",
                "prior_observation",
                "inspect_metadata",
                "correspondence",
                "current_locations",
                "stable_state",
                "compare_environment",
                "revalidate",
            ),
        ),
        (R, ("load_inputs", "candidate", "reduce_rows", "replay")),
        (R.q, ("replay_countdown_track_a_search_bytes",)),
        (R.analysis, ("reduce_matrix",)),
    )
    for name in names
)


def self_test():
    closed_source({path: {} for path in SOURCE_FILES})
    require(
        tuple(V.PUBLIC_SPECS) == LABELS and E.CURRENT_DEVICE == 16777232,
        "fixed PUBLIC/receiver registry differs",
    )
    return digested(
        dict(
            schema_version=DOMAIN + "/self-test",
            status="STATIC_SELF_TEST_ONLY",
            work=initial_work(),
            claim_ceiling=ceiling("NOT_PERFORMED"),
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--replay", action="store_true")
    parser.add_argument("--implementation-revision")
    args = parser.parse_args()
    if args.self_test:
        if args.implementation_revision is not None:
            parser.error("self-test takes no implementation revision")
        sys.stdout.buffer.write(canonical(self_test()))
        return
    if args.implementation_revision is None:
        parser.error("replay requires a full immutable implementation revision")
    result = None
    try:
        result = reconstruct(args.implementation_revision)
        sys.stdout.buffer.write(canonical(result))
        sys.stdout.buffer.flush()
    except (Exception, KeyboardInterrupt) as error:
        sys.stderr.buffer.write(canonical(failure_receipt(error, result)))
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
