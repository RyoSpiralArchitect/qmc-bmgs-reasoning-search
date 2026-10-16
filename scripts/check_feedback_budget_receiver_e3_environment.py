#!/usr/bin/env python3
"""Fixed E3 read-only inspection and genuine environment/baseline reconstruction.

Not receiver admission, PUBLIC replay, certificate issuance or execution.
No caller proof, path, device mapping, callback or consent input is accepted.
"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import sys
from types import MappingProxyType


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = "scripts/check_feedback_budget_receiver_e3_environment.py"
TEST = "tests/test_feedback_budget_receiver_e3_environment.py"
POLICY = "docs/strategy/countdown_feedback_budget_receiver_e3_environment.md"
SOURCE_FILES = (SCRIPT, TEST, POLICY)
BASE = "c18b6a7c96dcb54b18f56404a1802f1753e6cd44"
INSPECTOR = "scripts/inspect_feedback_budget_receiver_successor.py"
INSPECTOR_REVISION = "200b1f8c2dae4214c1917c32a7ff981eaf978fe9"
INSPECTOR_DIGEST = "749cfd1b59a6f16e830918ac82823a2e22a269739ebf0ac9fa4bf649b1557afc"
PRIOR = "docs/qualifications/countdown_feedback_budget_receiver_successor_inspection_20261003.inspection.json"
PRIOR_REFERENCE = MappingProxyType(
    dict(
        path=PRIOR,
        reviewed_revision=BASE,
        byte_count=36006,
        sha256="0c4373e703a57a85d713a3482122f72bb0480d49b1958f952a6cc31d99e2f297",
        deterministic_digest="78e74136b81f0347feef707e30fe23159d2656a8664d3fad363f2b78120ee791",
    )
)
SPEC = importlib.util.spec_from_file_location(
    "receiver_e3_inspection", ROOT / INSPECTOR
)
assert SPEC is not None and SPEC.loader is not None
V = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = V
SPEC.loader.exec_module(V)
C, B, R, S, core = V.C, V.B, V.R, V.S, V.core
canonical, parse, require, digested, sha, exact = (
    V.canonical,
    V.parse,
    V.require,
    V.digested,
    V.sha,
    V.exact,
)
DOMAIN = S.DOMAIN + "/receiver-e3-environment/v1"
CURRENT_DEVICE = 16777232
PRIOR_DEVICE = 16777234
ENV_FIELDS = ("source", "runtime", "baseline", "authorities", "admission_proof")
STATUS = "READ_ONLY_E3_ENVIRONMENT_AND_32_TRACE_BASELINE_REPRODUCED_NOT_ADMITTED"
CLAIM_BOUNDARY = "Fixed E3 metadata correspondence and genuine original environment/32-trace baseline reconstruction only. No PUBLIC trace replay, sealed acceptance reconstruction, current admission, certificate, candidate, new coordinator qualification, consent or execution."


def current_locations():
    locations = V.current_locations()
    require(
        type(locations) is dict and set(locations) == set(V.LOCATIONS),
        "exact six current roles required",
    )
    for role, path in V.LOCATIONS.items():
        V.location(locations[role], path, CURRENT_DEVICE)
    return locations


def correspondence(chains, prior_locations, locations):
    """Pure direct E0/E1/E2 comparator; inputs here have no provenance by shape."""
    require(
        type(chains) is list and len(chains) == len(V.REGISTRY),
        "exact eleven original chains required",
    )
    for value in (prior_locations, locations):
        require(
            type(value) is dict and set(value) == set(V.LOCATIONS),
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
            [p[1] for p in old["identities"]],
            [p[1] for p in locations[role]["identities"]],
            "historical inode differs",
        )

    for role in V.LOCATIONS:
        bind(locations[role], role, "E3", CURRENT_DEVICE)
    counts = {epoch: 0 for epoch in V.EPOCH_DEVICES}
    for row, spec in zip(chains, V.REGISTRY):
        label, epoch, _, _, _, _, role = spec
        require(
            type(row) is dict
            and set(row) == {"label", "historical_epoch", "owner", "historical"},
            "closed original chain required",
        )
        exact(
            {k: row[k] for k in ("label", "historical_epoch", "owner")},
            dict(label=label, historical_epoch=epoch, owner=V.owner(spec)),
            "registry order, epoch or owner differs",
        )
        compare(bind(row["historical"], role, epoch, V.EPOCH_DEVICES[epoch]), role)
        counts[epoch] += 1
    # This history is ONLY from the pinned E2 observation, including the bundle.
    observed = []
    for role in V.LOCATIONS:
        old = bind(prior_locations[role], role, "E2_observation", PRIOR_DEVICE)
        compare(old, role)
        observed.append(
            dict(
                role=role,
                owner=dict(
                    path=PRIOR,
                    reviewed_revision=BASE,
                    json_pointer="/location_correspondence/current_locations/" + role,
                ),
                historical=old,
            )
        )
    return parse(
        canonical(
            dict(
                policy="fixed_direct_E0_E1_E2_to_E3_same_path_inode_metadata_only/v1",
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
                        historical_device=PRIOR_DEVICE,
                        observed_device=CURRENT_DEVICE,
                        chain_count=6,
                    ),
                },
                original_chains=chains,
                prior_observation_chains=observed,
                current_locations=locations,
                metadata_correspondence_matches=True,
                current_receiver_admitted=False,
                physical_disk_identity_proven=False,
                reboot_causality_proven=False,
            )
        )
    )


def closed_source(files):
    require(
        SOURCE_FILES == (SCRIPT, TEST, POLICY) and len(SOURCE_FILES) == 3,
        "E3 source registry differs",
    )
    require(
        type(files) is dict and set(files) == {SCRIPT, TEST, POLICY},
        "exact E3 source closure required",
    )


def attest(revision):
    revision, head = R.oid(revision), core.git_head(ROOT)
    core.require_ancestor(ROOT, BASE, revision)
    core.require_ancestor(ROOT, revision, head)
    require(Path(__file__).resolve() == ROOT / SCRIPT, "E3 source origin differs")
    R.public._origin(V, INSPECTOR)
    old = V.attest(INSPECTOR_REVISION)
    require(
        old["deterministic_digest"] == INSPECTOR_DIGEST,
        "frozen E2 inspector source differs",
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
    require(core.git_head(ROOT) == head, "HEAD changed during E3 source inspection")
    return digested(
        dict(
            schema_version=DOMAIN + "/source",
            implementation_revision=revision,
            case_base_revision=BASE,
            files=files,
            frozen_inspector_source=old,
        )
    )


def prior_observation(evidence, source):
    item = evidence.file(ROOT / PRIOR)
    R.reviewed_file(item, BASE)
    require(
        len(item.raw) == PRIOR_REFERENCE["byte_count"]
        and sha(item.raw) == PRIOR_REFERENCE["sha256"],
        "pinned E2 observation bytes differ",
    )
    # Parse only AFTER exact reviewed bytes and fixed byte reference agree.
    value = V.inspection_shape(item.raw)
    require(
        value["deterministic_digest"] == PRIOR_REFERENCE["deterministic_digest"]
        and value["inspection_head"] == INSPECTOR_REVISION,
        "pinned E2 observation identity differs",
    )
    exact(
        value["source"],
        source["frozen_inspector_source"],
        "E2 observation source differs",
    )
    return value


def inspect_metadata(evidence, historical, prior, head):
    for relative, reviewed in V.ANCHORS:
        core.require_ancestor(ROOT, reviewed, head)
        evidence.anchor(relative, reviewed)
    cohort = V.inspect_metadata(evidence, historical)
    archives = [
        V.inspect_public(evidence, label, historical) for label in V.PUBLIC_SPECS
    ]
    for value, key in (
        (historical, "historical_source_receipts"),
        (evidence.anchors, "reviewed_anchors"),
        (archives, "public_archive_hash_closures"),
        (cohort, "sealed_metadata"),
    ):
        exact(value, prior[key], "fresh historical closure differs from E2: " + key)
    return cohort, archives


def stable_state(evidence, head, locations):
    _guard()
    require(core.git_head(ROOT) == head, "E3 inspection HEAD changed")
    evidence.revalidate()
    exact(current_locations(), locations, "E3 receiver identity changed")
    C.unused(S.REPLICATION)
    require(
        not core.git_bytes(ROOT, "status", "--porcelain", "--untracked-files=all"),
        "E3 source checkout must remain clean",
    )
    require(core.git_head(ROOT) == head, "E3 inspection HEAD changed")


def compare_environment(environment, original):
    require(
        type(environment) is dict and set(environment) == set(ENV_FIELDS),
        "complete five-field original environment required",
    )
    exact(
        environment,
        {key: original[key] for key in ENV_FIELDS},
        "whole genuine environment differs from original candidate",
    )
    exact(
        [
            environment["baseline"]["reproduced_trace_count"],
            environment["baseline"]["status"],
        ],
        [32, "PUBLIC_BASELINE_REPRODUCED"],
        "baseline completion differs",
    )


def revalidate(evidence, source, historical, environment, head, locations):
    stable_state(evidence, head, locations)
    exact(attest(source["implementation_revision"]), source, "E3 source changed")
    exact(V.historical_sources(), historical, "historical source changed")
    R.check_environment(environment)
    # Expensive source/runtime checks are bracketed by immutable-evidence checks.
    stable_state(evidence, head, locations)


def claim_ceiling(reconstruction_status="PARTIAL_ENVIRONMENT_ONLY"):
    return dict(
        reconstruction_status=reconstruction_status,
        execution_qualification="NOT_QUALIFIED_FOR_EXECUTION",
        public_traces_replayed=0,
        acceptance_order_reconstructed=False,
        current_receiver_admitted=False,
        certificate_issued=False,
        candidate_issued=False,
        new_public_attempts=0,
        replication_search_calls=0,
        replication_execution_authorized=False,
        locked_128_evaluation_authorized=False,
        physical_disk_identity_proven=False,
        reboot_causality_proven=False,
    )


class PreflightFailure(Exception):
    def __init__(self, cause, phase, baseline_completed):
        super().__init__(str(cause))
        self.cause, self.phase, self.baseline_completed = (
            cause,
            phase,
            baseline_completed,
        )


def check_environment(revision):
    """Actual entry: authenticated reads first, genuine computation, final checks."""
    phase, completed = "scope_and_source", 0
    try:
        _guard()
        C.unused(S.REPLICATION)
        head = core.git_head(ROOT)
        locations = current_locations()  # Reject another endpoint before numerics.
        source = attest(revision)
        evidence = V.Evidence()
        prior = prior_observation(evidence, source)
        historical = V.historical_sources()
        phase = "historical_metadata"
        cohort, archives = inspect_metadata(evidence, historical, prior, head)
        mapping = correspondence(
            V.recorded_chains(evidence.values),
            prior["location_correspondence"]["current_locations"],
            locations,
        )
        stable_state(evidence, head, locations)
        phase, completed = "genuine_environment", None
        environment = R.environment(B.ORIGINAL_SOURCE)
        compare_environment(environment, evidence.values[B.ORIGINAL_CANDIDATE])
        phase, completed = "final_revalidation", 32
        revalidate(evidence, source, historical, environment, head, locations)
        return digested(
            dict(
                schema_version=DOMAIN + "/observation",
                status=STATUS,
                source=source,
                inspection_head=head,
                prior_observation=dict(PRIOR_REFERENCE),
                historical_source_receipts=historical,
                reviewed_anchors=evidence.anchors,
                location_correspondence=mapping,
                public_archive_hash_closures=archives,
                sealed_metadata=cohort,
                environment=environment,
                environment_reconstructed=True,
                baseline_traces_recomputed=32,
                original_study_identity=S.REPLICATION_ID,
                fixed_replication_claim_path=str(B.fixed_claim()),
                original_study_slot_absent_at_completion=True,
                claim_ceiling=claim_ceiling(),
                claim_boundary=CLAIM_BOUNDARY,
            )
        )
    except (Exception, KeyboardInterrupt) as error:
        raise PreflightFailure(error, phase, completed) from error


def failure_receipt(error, completed_result=None):
    cause = error.cause if isinstance(error, PreflightFailure) else error
    phase = error.phase if isinstance(error, PreflightFailure) else "result_delivery"
    completed = (
        error.baseline_completed
        if isinstance(error, PreflightFailure)
        else 32
        if completed_result is not None
        else None
    )
    return digested(
        dict(
            schema_version=DOMAIN + "/failure",
            status="E3_ENVIRONMENT_CHECK_REJECTED",
            phase=phase,
            reason=str(cause),
            baseline_traces_completed=completed,
            baseline_work_extent_unknown=completed is None,
            authorization_consumed=(
                cause.authorization_consumed
                if isinstance(cause, S.ExecutionFailure)
                else None
            ),
            execution_dispatch_entered=False,
            new_effects_attempted=False,
            retain_evidence=True,
            automatic_retry_allowed=False,
            claim_ceiling=claim_ceiling("FAILED_INCOMPLETE"),
        )
    )


def _guard():
    V._guard()
    for module, name, expected in _DEPENDENCIES:
        require(getattr(module, name) is expected, "E3 dependency substituted: " + name)


_DEPENDENCIES = tuple(
    (module, name, getattr(module, name))
    for module, names in (
        (
            V,
            (
                "attest",
                "inspection_shape",
                "current_locations",
                "location",
                "owner",
                "Evidence",
                "ReadOnlyArchive",
                "historical_sources",
                "inspect_metadata",
                "inspect_public",
                "recorded_chains",
            ),
        ),
        (R, ("environment", "check_environment")),
        (R.public, ("qualify_baseline", "runtime_receipt")),
        (R.public.q, ("run_matrix",)),
    )
    for name in names
)


def self_test():
    closed_source({name: {} for name in SOURCE_FILES})
    require(
        V.CURRENT_DEVICE == PRIOR_DEVICE and CURRENT_DEVICE == 16777232,
        "frozen separate cases differ",
    )
    return digested(
        dict(
            schema_version=DOMAIN + "/self-test",
            status="STATIC_SELF_TEST_ONLY",
            baseline_traces_recomputed=0,
            claim_ceiling=claim_ceiling("NOT_PERFORMED"),
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--check-environment", action="store_true")
    parser.add_argument("--implementation-revision")
    args = parser.parse_args()
    if args.self_test:
        if args.implementation_revision is not None:
            parser.error("self-test takes no implementation revision")
        sys.stdout.buffer.write(canonical(self_test()))
        return
    if args.implementation_revision is None:
        parser.error("check requires a full immutable implementation revision")
    result = None
    try:
        result = check_environment(args.implementation_revision)
        sys.stdout.buffer.write(canonical(result))
        sys.stdout.buffer.flush()
    except (Exception, KeyboardInterrupt) as error:
        sys.stderr.buffer.write(canonical(failure_receipt(error, result)))
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
