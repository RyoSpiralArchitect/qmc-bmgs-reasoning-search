#!/usr/bin/env python3
"""Read-only E4 certificate proposal reconstruction; no issuance or execution.

Saved records and deterministic projections are comparators, never capabilities.
Actual numerical operations require separate approval and a fresh process.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import importlib.util
from pathlib import Path
import sys
from types import MappingProxyType
from weakref import WeakKeyDictionary


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = "scripts/feedback_budget_receiver_e4_certificate.py"
TEST = "tests/test_feedback_budget_receiver_e4_certificate.py"
POLICY = "docs/strategy/countdown_feedback_budget_receiver_e4_certificate.md"
SOURCE_FILES = (SCRIPT, TEST, POLICY)
DESIGN_REVISION = "0aeb46b039c1d1b46874f7b43c3a655d03b2eff9"
FROZEN_SCRIPT = "scripts/reconstruct_feedback_budget_receiver_e4.py"
FROZEN_REVISION = "c19db4a7994eeb5f33c610cdee3ebc0c72e2a004"
FROZEN_DIGEST = "52deaa2df32b9b03786bd6afeaedb885146a68ddc7de9d0a195f5462275f2456"
HISTORICAL_REVIEW = "3a69f33121be244c21143979be0a04fe71cdac5e"
PROPOSAL = "docs/qualifications/countdown_feedback_budget_receiver_e4_certificate_20261010.proposal.json"
SPEC = importlib.util.spec_from_file_location(
    "certificate_e4_frozen", ROOT / FROZEN_SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
N = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = N
SPEC.loader.exec_module(N)
E, V, C, B, R, S, core = N.E, N.V, N.C, N.B, N.R, N.S, N.core
canonical, parse, require, digested, sha, exact = (
    N.canonical,
    N.parse,
    N.require,
    N.digested,
    N.sha,
    N.exact,
)
DOMAIN = S.DOMAIN + "/receiver-e4-certificate/v1"
STATUS = "ORIGINAL_INPUT_AND_PUBLIC_EVIDENCE_RECONSTRUCTED_NOT_EXECUTION_AUTHORITY"
METHOD = "fresh_process_same_frozen_implementation_full_recomputation"
PINS = MappingProxyType(
    {
        "observation": (
            215556,
            "c4b36d346bfbe641dc292948dc1410d429298fb06b2ee14b0de7a666d08e86c8",
            "d546836a203b3c947dfaa903a49b26b815b07b50a8eebb56f4783c9db855280b",
        ),
        "verification": (
            6006,
            "8d332314e656cbfdd8e6d999a92f3ba43a7c4d35c667e85844199b75fa292dcd",
            "0b0c41275034b94d763b29c58d1d020defacc054036e8e0429444b6f9514d73f",
        ),
        "operations": (
            12603,
            "119458f9b111896666ca8d91b1d82aa844a17423f98e7a53e103a389515320ae",
            "d653610ea2fc852c89303effb4f2e9d94c796c417bc720e53c84902345d679a8",
        ),
    }
)
FRESH_KEYS = (
    "source",
    "prior_public_observation",
    "historical_source_receipts",
    "reviewed_anchors",
    "location_correspondence",
    "public_archive_hash_closures",
    "sealed_metadata",
    "environment",
    "work",
    "public_replays",
    "public_traces_replayed",
    "budget_prefix_comparisons",
    "original_sealed_reconstruction",
    "acceptance_order_reconstructed",
    "original_study_identity",
    "fixed_replication_claim_path",
)
HISTORICAL_KEYS = (
    "schema_version",
    "status",
    "reconstruction_head",
    "original_study_slot_absent_at_completion",
    "claim_ceiling",
    "claim_boundary",
    "deterministic_digest",
)
CERTIFICATE_KEYS = (
    "schema_version",
    "status",
    "case",
    "source",
    "historical_e4",
    "evidence",
    "location_correspondence",
    "environment",
    "reconstruction",
    "study",
    "claim_ceiling",
    "deterministic_digest",
)


def ceiling():
    return dict(
        current_receiver_admitted=False,
        new_coordinator_qualified=False,
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


def closed_source(files):
    require(SOURCE_FILES == (SCRIPT, TEST, POLICY), "certifier source registry differs")
    require(
        type(files) is dict and set(files) == {SCRIPT, TEST, POLICY},
        "exact three-file certifier source closure required",
    )


def attest(revision):
    revision, head = R.oid(revision), core.git_head(ROOT)
    core.require_ancestor(ROOT, DESIGN_REVISION, revision)
    core.require_ancestor(ROOT, revision, head)
    require(
        Path(__file__).resolve() == ROOT / SCRIPT, "certifier source origin differs"
    )
    R.public._origin(N, FROZEN_SCRIPT)
    frozen = N.attest(FROZEN_REVISION)
    require(frozen["deterministic_digest"] == FROZEN_DIGEST, "frozen E4 source differs")
    files, snapshots = {}, []
    for relative in SOURCE_FILES:
        item = R.snapshot_file(ROOT / relative)
        R.reviewed_file(item, revision)
        files[relative] = dict(byte_count=len(item.raw), sha256=sha(item.raw))
        snapshots.append(item)
    closed_source(files)
    for item in snapshots:
        item.revalidate()
    require(core.git_head(ROOT) == head, "HEAD changed during certifier attestation")
    return digested(
        dict(
            schema_version=DOMAIN + "/source",
            implementation_revision=revision,
            design_revision=DESIGN_REVISION,
            files=files,
            frozen_reconstruction=frozen,
        )
    )


def historical_references():
    return {
        label: dict(
            path="docs/qualifications/countdown_feedback_budget_receiver_e4_20261010."
            + label
            + ".json",
            reviewed_revision=HISTORICAL_REVIEW,
            byte_count=pin[0],
            sha256=pin[1],
            deterministic_digest=pin[2],
        )
        for label, pin in PINS.items()
    }


def historical(evidence, frozen):
    """Authenticate all three fixed records before parsing any of them."""
    snapshots = {}
    for label, ref in historical_references().items():
        item = evidence.file(ROOT / ref["path"])
        R.reviewed_file(item, HISTORICAL_REVIEW)
        require(
            len(item.raw) == ref["byte_count"] and sha(item.raw) == ref["sha256"],
            "pinned E4 historical bytes differ: " + label,
        )
        snapshots[label] = item
    values = {}
    for label, item in snapshots.items():
        item.revalidate()
        value = parse(item.raw)
        core.require_digest(value)
        require(
            value["deterministic_digest"] == PINS[label][2], "historical digest differs"
        )
        values[label] = value
    old, verification, operations = (values[label] for label in PINS)
    require(
        type(old) is dict and set(old) == set(FRESH_KEYS + HISTORICAL_KEYS),
        "closed 23-key historical observation required",
    )
    exact(
        {key: old[key] for key in HISTORICAL_KEYS},
        dict(
            schema_version=N.DOMAIN + "/observation",
            status=N.STATUS,
            reconstruction_head=FROZEN_REVISION,
            original_study_slot_absent_at_completion=True,
            claim_ceiling=N.ceiling("FULL_ORIGINAL_RECONSTRUCTION_ONLY"),
            claim_boundary=N.CLAIM_BOUNDARY,
            deterministic_digest=PINS["observation"][2],
        ),
        "historical envelope differs",
    )
    exact(old["source"], frozen, "historical E4 source differs")
    exact(
        verification["implementation_source"],
        frozen,
        "historical verifier source differs",
    )
    exact(verification["work"], old["work"], "historical verifier work differs")
    require(
        verification["reconstruction_head"] == FROZEN_REVISION
        and verification["verification_method"] == METHOD
        and verification["algorithmically_independent_implementation"] is False
        and verification["complete_canonical_observation_byte_identical"] is True
        and operations["implementation_source_digest"] == FROZEN_DIGEST,
        "historical verification method or operations differs",
    )
    ref = {
        key: historical_references()["observation"][key]
        for key in ("byte_count", "sha256", "deterministic_digest")
    }
    exact(
        verification["independently_reconstructed_observation"],
        ref,
        "historical complete-byte comparison differs",
    )
    exact(
        verification["saved_observation"],
        dict(path=str(N.SAVED), **ref),
        "historical comparison target differs",
    )
    evidence.revalidate()
    return old


def _projection(old, source, screens):
    """Pure rejection template, NOT validation, reconstruction, or a live capture."""
    exact(
        screens,
        dict(original_public=False, receiver_v2_public=False),
        "negative historical screens must remain explicit",
    )
    metadata = old["sealed_metadata"]
    return digested(
        dict(
            schema_version=DOMAIN + "/certificate",
            status=STATUS,
            case=dict(
                name="E4",
                device=16777234,
                historical_chain_counts=dict(
                    original_v7=3,
                    receiver_20260921=8,
                    E2_observation=6,
                    E3_observation=6,
                ),
            ),
            source=dict(certifier=source, frozen_reconstruction=old["source"]),
            historical_e4=dict(
                **historical_references(),
                reconstruction_head=FROZEN_REVISION,
                verification_method=METHOD,
                algorithmically_independent_implementation=False,
            ),
            evidence={
                key: old[key]
                for key in (
                    "prior_public_observation",
                    "historical_source_receipts",
                    "reviewed_anchors",
                    "public_archive_hash_closures",
                    "sealed_metadata",
                )
            },
            location_correspondence=old["location_correspondence"],
            environment=old["environment"],
            reconstruction=dict(
                **{
                    key: old[key]
                    for key in (
                        "work",
                        "public_replays",
                        "original_sealed_reconstruction",
                        "public_traces_replayed",
                        "budget_prefix_comparisons",
                        "acceptance_order_reconstructed",
                    )
                },
                historical_screen_conjunction=screens,
            ),
            study=dict(
                experiment_id=S.REPLICATION_ID,
                input_manifest_digest=metadata["input_manifest_digest"],
                schedule_digest=metadata["schedule_digest"],
                seal_digest=metadata["seal_digest"],
                original_generation_reference=old["original_sealed_reconstruction"][
                    "original_generation_reference"
                ],
                output_path=str(B.OUTPUT),
                summary_path=str(C.REPLICATION_SUMMARY),
                fixed_replication_claim_path=old["fixed_replication_claim_path"],
                accepted_source_multisets=64,
                cell_count=1024,
                budget_pair_count=512,
                four_arm_block_count=256,
            ),
            claim_ceiling=ceiling(),
        )
    )


def _compare_certificate(raw, expected):
    value = parse(raw)
    core.require_digest(value)
    require(
        type(value) is dict and set(value) == set(CERTIFICATE_KEYS),
        "closed certificate schema required",
    )
    # Whole canonical equality enforces every inherited nested field AND type;
    # Python equality alone would incorrectly accept True == 1 and 0.0 == 0.
    require(
        canonical(value) == raw == canonical(expected),
        "entire canonical certificate differs",
    )


def _stable(evidence, source, head, locations, inputs=None):
    _guard()
    require(core.git_head(ROOT) == head, "certifier operation HEAD changed")
    exact(attest(source["implementation_revision"]), source, "certifier source changed")
    N.stable_state(evidence, source["frozen_reconstruction"], head, locations, inputs)
    exact(attest(source["implementation_revision"]), source, "certifier source changed")
    require(core.git_head(ROOT) == head, "certifier operation HEAD changed")
    _guard()


def _revalidate(evidence, source, history, environment, head, locations, inputs=None):
    _stable(evidence, source, head, locations, inputs)
    N.revalidate(
        evidence,
        source["frozen_reconstruction"],
        history,
        environment,
        head,
        locations,
        inputs,
    )
    _stable(evidence, source, head, locations, inputs)


@dataclass(frozen=True)
class _State:
    evidence: object
    source: dict
    history: dict
    environment: dict
    head: str
    locations: dict
    inputs: object
    raw: bytes
    work_raw: bytes


class _LiveCapture:
    """No receipt/proof/callback constructor; only completed orchestration registers it."""

    __slots__ = ("__weakref__",)

    def __new__(cls, *args, **kwargs):
        raise TypeError("live capture is only produced by genuine reconstruction")

    def revalidate(self):
        state = _state(self)
        _revalidate(
            state.evidence,
            state.source,
            state.history,
            state.environment,
            state.head,
            state.locations,
            state.inputs,
        )

    @property
    def certificate_raw(self):
        return _state(self).raw


_LIVE = WeakKeyDictionary()
_RECONSTRUCTION_STARTED = False


def _state(capture):
    require(
        type(capture) is _LiveCapture and capture in _LIVE,
        "registered genuine live capture required",
    )
    return _LIVE[capture]


class CertificateFailure(Exception):
    def __init__(self, cause, phase, work):
        super().__init__(str(cause))
        self.cause, self.phase, self.work = cause, phase, parse(canonical(work))


def reconstruct(revision):
    """One ordered genuine computation per process; returns no execution authority."""
    global _RECONSTRUCTION_STARTED
    phase, work = "scope_and_source", N.initial_work()
    try:
        _guard()
        require(
            not _RECONSTRUCTION_STARTED, "fresh process required; no retry or resume"
        )
        _RECONSTRUCTION_STARTED = True
        C.unused(S.REPLICATION)
        head, locations = core.git_head(ROOT), N.current_locations()
        source, evidence = attest(revision), V.Evidence()
        phase = "authenticated_historical_metadata"
        old = historical(evidence, source["frozen_reconstruction"])
        prior, history, cohort, archives, mapping = N.inspect_metadata(
            evidence, source["frozen_reconstruction"], head, locations
        )
        _stable(evidence, source, head, locations)
        phase = "genuine_environment"
        work["baseline_traces_completed"] = None
        N.progress(phase, work)
        environment = R.environment(B.ORIGINAL_SOURCE)
        work["baseline_traces_completed"] = 32
        E.compare_environment(environment, evidence.values[B.ORIGINAL_CANDIDATE])
        exact(environment, prior["environment"], "fresh environment differs from E3")
        exact(environment, old["environment"], "fresh environment differs from E4")
        _revalidate(evidence, source, history, environment, head, locations)
        inputs = R.load_inputs(S.PUBLIC)
        require(type(inputs) is R.Inputs, "genuine PUBLIC loader required")
        replays = []
        for label in N.LABELS:
            phase = label
            _revalidate(evidence, source, history, environment, head, locations, inputs)
            replays.append(
                N.replay_one(label, evidence, inputs, environment, history, work)
            )
            _revalidate(evidence, source, history, environment, head, locations, inputs)
        phase = "original_sealed_cohort_reconstruction"
        _revalidate(evidence, source, history, environment, head, locations, inputs)
        sealed = N.reconstruct_seal(
            evidence, environment, replays[0]["original_generation_reference"], work
        )
        phase = "whole_historical_evidence_comparison"
        fresh = dict(
            source=source["frozen_reconstruction"],
            prior_public_observation=dict(N.PRIOR_REFERENCE),
            historical_source_receipts=history,
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
        )
        require(set(fresh) == set(FRESH_KEYS), "fresh field registry differs")
        for key in FRESH_KEYS:
            exact(fresh[key], old[key], "fresh full evidence differs: " + key)
        # Each complete summary already matched its genuine independently replayed
        # counterpart; the historical boolean is now safe to project, not before.
        screens = {
            label: evidence.values[V.PUBLIC_SPECS[label][2]]["reduction"][
                "exact_success"
            ]["screen_conjunction"]
            for label in N.LABELS
        }
        raw = canonical(_projection(fresh, source, screens))
        phase = "final_source_runtime_evidence_revalidation"
        N.progress(phase, work)
        _revalidate(evidence, source, history, environment, head, locations, inputs)
        state = _State(
            evidence,
            source,
            history,
            environment,
            head,
            locations,
            inputs,
            raw,
            canonical(work),
        )
        capture = object.__new__(_LiveCapture)
        _LIVE[capture] = state
        return capture
    except (Exception, KeyboardInterrupt) as error:
        raise CertificateFailure(error, phase, work) from error


def operation_receipt(capture):
    state = _state(capture)
    capture.revalidate()
    return digested(
        dict(
            schema_version=DOMAIN + "/operation",
            status="PROPOSAL_RECONSTRUCTED_NOT_ISSUED",
            operation_head=state.head,
            implementation_source=state.source,
            certificate=N.reference(state.raw),
            work=parse(state.work_raw),
            original_study_slot_absent_at_completion=True,
            certificate_issued=False,
            claim_ceiling=ceiling(),
        )
    )


def verify_proposal(revision, reviewed_revision):
    """Fixed reviewed proposal only; no external receipt can replace computation."""
    phase, work = "reviewed_proposal_authentication", N.initial_work()
    try:
        _guard()
        revision, reviewed_revision = R.oid(revision), R.oid(reviewed_revision)
        head = core.git_head(ROOT)
        core.require_ancestor(ROOT, revision, reviewed_revision)
        core.require_ancestor(ROOT, reviewed_revision, head)
        source, evidence = attest(revision), V.Evidence()
        old = historical(evidence, source["frozen_reconstruction"])
        saved = evidence.file(ROOT / PROPOSAL)
        R.reviewed_file(saved, reviewed_revision)
        _compare_certificate(
            saved.raw,
            _projection(
                old, source, dict(original_public=False, receiver_v2_public=False)
            ),
        )
        evidence.revalidate()
        require(core.git_head(ROOT) == head, "proposal verification HEAD changed")
        phase = "fresh_complete_reconstruction"
        capture = reconstruct(revision)
        state = _state(capture)
        work = parse(state.work_raw)
        phase = "whole_certificate_byte_comparison"
        require(state.head == head, "proposal reconstruction HEAD changed")
        require(
            capture.certificate_raw == saved.raw,
            "entire reconstructed certificate differs from proposal",
        )
        phase = "final_proposal_and_capture_revalidation"
        evidence.revalidate()
        capture.revalidate()
        saved.revalidate()
        _guard()
        require(core.git_head(ROOT) == head, "proposal verification HEAD changed")
        return digested(
            dict(
                schema_version=DOMAIN + "/verification",
                status="WHOLE_RECONSTRUCTED_PROPOSAL_BYTE_IDENTICAL_NOT_ISSUED",
                operation_head=head,
                implementation_source=state.source,
                reviewed_proposal=dict(
                    path=PROPOSAL,
                    reviewed_revision=reviewed_revision,
                    **N.reference(saved.raw),
                ),
                independently_reconstructed_certificate=N.reference(
                    capture.certificate_raw
                ),
                complete_canonical_certificate_byte_identical=True,
                verification_method=METHOD,
                algorithmically_independent_implementation=False,
                work=work,
                original_study_slot_absent_at_completion=True,
                certificate_issued=False,
                claim_ceiling=ceiling(),
            )
        )
    except CertificateFailure:
        raise
    except (Exception, KeyboardInterrupt) as error:
        raise CertificateFailure(error, phase, work) from error


def failure_receipt(error, work=None, delivery="NOT_ATTEMPTED"):
    cause = error.cause if isinstance(error, CertificateFailure) else error
    return digested(
        dict(
            schema_version=DOMAIN + "/failure",
            status="CERTIFICATE_OPERATION_REJECTED_OR_DELIVERY_UNCERTAIN",
            phase=error.phase
            if isinstance(error, CertificateFailure)
            else "result_delivery",
            reason=str(cause),
            work=error.work if isinstance(error, CertificateFailure) else work,
            result_delivery=delivery,
            authorization_consumed=cause.authorization_consumed
            if isinstance(cause, S.ExecutionFailure)
            else None,
            certificate_issued=False,
            execution_dispatch_entered=False,
            new_effects_attempted=False,
            retain_evidence=True,
            automatic_retry_allowed=False,
            claim_ceiling=ceiling(),
        )
    )


def _guard():
    N._guard()
    for module, name, expected in _DEPENDENCIES:
        require(
            getattr(module, name) is expected,
            "certifier dependency substituted: " + name,
        )


def self_test():
    _guard()
    closed_source({name: {} for name in SOURCE_FILES})
    require(
        len(FRESH_KEYS) == 16
        and len(HISTORICAL_KEYS) == 7
        and len(set(FRESH_KEYS + HISTORICAL_KEYS)) == 23
        and len(set(CERTIFICATE_KEYS)) == 12,
        "closed field partition differs",
    )
    return digested(
        dict(
            schema_version=DOMAIN + "/self-test",
            status="STATIC_SELF_TEST_ONLY",
            work=N.initial_work(),
            certificate_issued=False,
            claim_ceiling=ceiling(),
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--reconstruct", action="store_true")
    mode.add_argument("--verify-proposal", action="store_true")
    parser.add_argument("--implementation-revision")
    parser.add_argument("--reviewed-proposal-revision")
    args = parser.parse_args()
    if args.self_test:
        if (
            args.implementation_revision is not None
            or args.reviewed_proposal_revision is not None
        ):
            parser.error("self-test takes no revisions")
        sys.stdout.buffer.write(canonical(self_test()))
        sys.stdout.buffer.flush()
        return
    if args.implementation_revision is None or (
        args.verify_proposal != (args.reviewed_proposal_revision is not None)
    ):
        parser.error(
            "immutable implementation revision required; proposal review required only for verification"
        )
    work, delivery = None, "NOT_ATTEMPTED"
    try:
        if args.verify_proposal:
            result = verify_proposal(
                args.implementation_revision, args.reviewed_proposal_revision
            )
            work, raw, receipt = result["work"], canonical(result), None
        else:
            capture = reconstruct(args.implementation_revision)
            work = parse(_state(capture).work_raw)
            receipt = operation_receipt(capture)
            raw = capture.certificate_raw
        delivery = "UNKNOWN_PARTIAL_OR_COMPLETE"
        written = sys.stdout.buffer.write(raw)
        require(written == len(raw), "short result write")
        sys.stdout.buffer.flush()
        delivery = "COMPLETE_STDOUT_FLUSH"
        if receipt is not None:
            receipt_raw = canonical(receipt)
            require(
                sys.stderr.buffer.write(receipt_raw) == len(receipt_raw),
                "short operation receipt write",
            )
            sys.stderr.buffer.flush()
    except (Exception, KeyboardInterrupt) as error:
        sys.stderr.buffer.write(canonical(failure_receipt(error, work, delivery)))
        sys.stderr.buffer.flush()
        raise SystemExit(1) from error


_DEPENDENCIES = tuple(
    (module, name, getattr(module, name))
    for module, names in (
        (
            N,
            (
                "_guard",
                "attest",
                "current_locations",
                "inspect_metadata",
                "prior_observation",
                "correspondence",
                "stable_state",
                "revalidate",
                "replay_one",
                "reconstruct_seal",
                "initial_work",
                "reference",
                "progress",
                "ceiling",
            ),
        ),
        (V, ("Evidence",)),
        (
            R,
            (
                "snapshot_file",
                "reviewed_file",
                "oid",
                "environment",
                "load_inputs",
                "Inputs",
            ),
        ),
        (C, ("unused",)),
        (B, ("fixed_claim",)),
        (core, ("git_head", "git_bytes", "require_ancestor", "require_digest")),
        (_LiveCapture, ("revalidate", "certificate_raw")),
        (
            sys.modules[__name__],
            (
                "attest",
                "closed_source",
                "historical",
                "historical_references",
                "_projection",
                "_compare_certificate",
                "_stable",
                "_revalidate",
                "_state",
                "_LiveCapture",
                "_State",
                "reconstruct",
                "operation_receipt",
                "verify_proposal",
                "ceiling",
                "canonical",
                "parse",
                "require",
                "digested",
                "sha",
                "exact",
            ),
        ),
    )
    for name in names
)


if __name__ == "__main__":
    main()
