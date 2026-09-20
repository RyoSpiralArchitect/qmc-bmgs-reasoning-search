#!/usr/bin/env python3
"""Explicit v7 receiver re-attestation; never relax or rewrite old admission.

One historical candidate, cohort, PUBLIC archive and replication claim. This
module adds its own source authority and immutable certificate. It shares only
unchanged numerical functions and durable publication mechanics with the old
connector; an arbitrary object or structurally valid binding is not admission.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import importlib.util
import os
from pathlib import Path
import sys
from types import MappingProxyType


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = "scripts/feedback_budget_replication_reattest.py"
TEST = "tests/test_feedback_budget_replication_reattest.py"
POLICY = "docs/strategy/countdown_feedback_budget_v7_reattestation.md"
RUNNER = "scripts/run_feedback_budget_replication_execution.py"
SPEC = importlib.util.spec_from_file_location(
    "replication_reattest_original", ROOT / RUNNER
)
assert SPEC is not None and SPEC.loader is not None
R = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = R
SPEC.loader.exec_module(R)
S, M, q, core = R.storage, R.admission, R.q, R.core
canonical, require, digested, digest = R.canonical, R.require, R.digested, R.digest
parse, sha = core.parse_canonical, q.sha
DOMAIN = S.DOMAIN + "/receiver-reattestation/v1"
REVIEWED = "b57b16ee107eddf07aa94bcf7b20763577aab3a8"
ORIGINAL_SOURCE = "91359c9327861210c03ad0bc4e267af240f4ec93"
ORIGINAL_DIGEST = "27c579f553e44ba3d307d74a5d5b9fa26b9e613150488ecab48e280e518d610f"
ORIGINAL_CANDIDATE = "docs/preregistrations/countdown_thompson_feedback_budget_v7_execution_authorization_candidate.json"
ORIGINAL_RAW = (
    ROOT / "artifacts/work/feedback-budget-replication-v7-20260913-a.authorization.json"
)
OUTPUT = ROOT / "artifacts/work/feedback-budget-replication-v7-20260913-a"
PUBLIC_OUTPUT = (
    ROOT / "artifacts/work/feedback-budget-replication-connector-v7-20260913-a"
)
PUBLIC_SUMMARY = "docs/qualifications/countdown_feedback_budget_v7_connector_public_20260913.summary.json"
PUBLIC_COMMIT = "docs/qualifications/countdown_feedback_budget_v7_connector_public_20260913.commit.json"
SEAL_MIRROR = "docs/preregistrations/countdown_thompson_feedback_budget_v7"
CERTIFICATE = "docs/qualifications/countdown_feedback_budget_v7_reattest_20260921.certificate.json"
CANDIDATE = "docs/preregistrations/countdown_feedback_budget_v7_reattest_20260921.authorization.json"
BUNDLE_COMMIT = (
    "docs/qualifications/countdown_feedback_budget_v7_reattest_20260921.commit.json"
)
BUNDLE = ROOT / "artifacts/work/feedback-budget-v7-reattest-20260921-a"
BUNDLE_NAMES = frozenset(("certificate.json", "authorization.json", "COMMIT.json"))
AUTH_FIELDS = R.AUTH_FIELDS | {"receiver_certificate", "bridge_source"}
CERT_FIELDS = frozenset(
    "schema_version status historical_review_revision original_candidate_digest "
    "anchors location_correspondence current_locations source public_verification "
    "sealed_input_verification fixed_claim_path replication_search_calls "
    "replication_execution_authorized candidate_is_execution_authority "
    "locked_128_evaluation_authorized claim_boundary deterministic_digest".split()
)


def without_digest(value):
    return {
        name: item for name, item in value.items() if name != "deterministic_digest"
    }


def file_reference(snapshot):
    return dict(
        path=str(snapshot.path), byte_count=len(snapshot.raw), sha256=sha(snapshot.raw)
    )


def fixed_claim():
    return S.claim_path({"execution_mode": S.REPLICATION})


def unused():
    # No caller-supplied candidate, output or digest can select another claim.
    if os.path.lexists(fixed_claim()):
        raise S.ExecutionFailure(
            "AUTHORIZATION_ALREADY_SPENT",
            True,
            "occupied fixed study claim; no requalification or retry",
        )
    require(not os.path.lexists(OUTPUT), "fixed output occupied; no retry or adoption")


def directory_binding(path, *, private=False):
    path = Path(path)
    require(
        path.is_absolute() and path == path.absolute(),
        "absolute canonical directory required",
    )
    parent = S.mechanics._PinnedParent.open(path)
    try:
        if private:
            S.base.storage._check_directory(parent)
        parent.assert_path()
        return dict(
            path=str(path), identities=[list(x) for x in parent.component_identities]
        )
    finally:
        parent.close()


def mapping(chains):
    """Exact lexical paths/inodes and one global, nonidentity device mapping.

    Callers supply authenticated historical bindings and freshly pinned current
    bindings. This pure restriction is not, by itself, provenance or admission.
    """
    require(
        type(chains) is list and len(chains) == 3,
        "three historical binding chains required",
    )
    transitions, prefixes = set(), {}
    records = []
    for label, old, current in chains:
        require(type(old) is dict and type(current) is dict, "binding objects required")
        path = old.get("path")
        require(
            type(path) is str and path == current.get("path"), "historical path differs"
        )
        parts = Path(path).parts
        require(
            Path(path).is_absolute() and str(Path(path)) == path and ".." not in parts,
            "historical path alias differs",
        )
        before, after = old.get("identities"), current.get("identities")
        require(
            type(before) is list
            and type(after) is list
            and len(before) == len(after) == len(parts),
            "all path component identities required",
        )
        for index, (left, right) in enumerate(zip(before, after)):
            require(
                all(
                    type(x) is list
                    and len(x) == 2
                    and all(type(n) is int and n >= 0 for n in x)
                    for x in (left, right)
                ),
                "plain device/inode pairs required",
            )
            require(left[1] == right[1], "historical inode differs")
            transitions.add((left[0], right[0]))
            prefix = str(Path(*parts[: index + 1]))
            pair = (tuple(left), tuple(right))
            require(
                prefix not in prefixes or prefixes[prefix] == pair,
                "shared prefix mapping differs",
            )
            prefixes[prefix] = pair
        records.append(dict(label=label, historical=old, current=current))
    require(len(transitions) == 1, "one uniform device transition required")
    old_device, current_device = next(iter(transitions))
    require(
        old_device != current_device,
        "this bridge requires an explicit device transition",
    )
    return dict(
        policy="same_lexical_paths_and_inodes_one_device_correspondence/v1",
        historical_device=old_device,
        current_device=current_device,
        chains=records,
        physical_disk_identity_proven=False,
        reboot_causality_proven=False,
    )


def current_locations():
    return {
        "public": directory_binding(PUBLIC_OUTPUT, private=True),
        "cohort": directory_binding(M.COHORT_PATH, private=True),
        "output_parent": directory_binding(OUTPUT.parent),
        "ledger": directory_binding(S.LEDGER, private=True),
    }


class Archive:
    """Closed bytes plus process-local no-follow location/generation checks."""

    def __init__(self, path, names):
        self.path, self.names = Path(path), frozenset(names)
        parent = S.mechanics._PinnedParent.open(self.path)
        try:
            raw, self.generation = S.base._observe(parent, self.names)
            self.identities = parent.component_identities
            self.raw = MappingProxyType(raw)
        finally:
            parent.close()

    def revalidate(self):
        parent = S.mechanics._PinnedParent.open(self.path)
        try:
            require(
                parent.component_identities == self.identities,
                "archive identity changed",
            )
            raw, generation = S.base._observe(parent, self.names)
            require(
                raw == dict(self.raw) and generation == self.generation,
                "archive content/generation changed",
            )
        finally:
            parent.close()


@dataclass(frozen=True)
class Transport:
    snapshots: tuple
    public: Archive
    cohort: Archive
    locations_raw: bytes
    correspondence_raw: bytes
    anchors_raw: bytes
    original_raw: bytes

    @property
    def original(self):
        return parse(self.original_raw)

    @property
    def binding(self):
        return parse(self.public.raw["STARTED.json"])["binding"]

    def revalidate(self):
        require(
            canonical(current_locations()) == self.locations_raw,
            "current receiver locations changed",
        )
        for item in self.snapshots:
            item.revalidate()
        self.public.revalidate()
        self.cohort.revalidate()


def inspect_transport():
    """Content closure before any environment qualification, replay or generator."""
    snapshots, anchors = [], {}

    def anchored(relative):
        item = R.snapshot_file(ROOT / relative)
        R.reviewed_file(item, REVIEWED)
        snapshots.append(item)
        anchors[relative] = file_reference(item)
        return item

    old_snapshot = anchored(ORIGINAL_CANDIDATE)
    original = R.auth_shape(old_snapshot.raw, S.REPLICATION, ORIGINAL_DIGEST)
    require(
        original["output_path"] == str(OUTPUT)
        and original["source"]["execution_revision"] == ORIGINAL_SOURCE,
        "original fixed candidate differs",
    )
    duplicate = R.snapshot_file(ORIGINAL_RAW)
    require(duplicate.raw == old_snapshot.raw, "original raw candidate differs")
    snapshots.append(duplicate)
    summary_snapshot, commit_snapshot = (
        anchored(PUBLIC_SUMMARY),
        anchored(PUBLIC_COMMIT),
    )
    public = Archive(PUBLIC_OUTPUT, S.NAMES)
    require(
        public.raw["COMMIT.json"] == commit_snapshot.raw,
        "historical PUBLIC COMMIT differs",
    )
    anchored_commit = parse(commit_snapshot.raw)
    core.require_digest(anchored_commit)
    # Authenticate STARTED before following its authorization path or claim.
    # The complete cell/receipt transaction is still closed separately below.
    require(
        sha(public.raw["STARTED.json"]) == anchored_commit["started_sha256"],
        "historical PUBLIC STARTED hash differs before reference access",
    )
    started = parse(public.raw["STARTED.json"])
    core.require_digest(started)
    require(
        set(started)
        == {
            "schema_version",
            "binding",
            "output_path",
            "directory_identities",
            "deterministic_digest",
        }
        and started["schema_version"] == S.DOMAIN + "/started"
        and started["output_path"] == str(PUBLIC_OUTPUT),
        "historical PUBLIC STARTED differs",
    )
    binding = S.frozen_binding(started["binding"])
    old_auth = binding["authorization"]
    require(
        binding["execution_mode"] == S.PUBLIC
        and old_auth["output_path"] == str(PUBLIC_OUTPUT),
        "historical PUBLIC binding differs",
    )
    auth_snapshot = R.snapshot_file(Path(binding["authorization_path"]))
    require(
        auth_snapshot.raw == canonical(old_auth),
        "historical PUBLIC authorization differs",
    )
    R.auth_shape(auth_snapshot.raw, S.PUBLIC, old_auth["deterministic_digest"])
    snapshots.extend((auth_snapshot, S.inspect_claim(binding, core.FileSnapshot)))
    # Anchored COMMIT hashes STARTED, which binds both the old authorization and
    # claim. The raw control bytes are not independently trusted merely by path.
    entries = []
    for index, name in enumerate(S.base.CELL_NAMES):
        raw = public.raw[name]
        require(
            S.record_bytes(index, S.parse(raw, S.base.MAX_CELL_BYTES), binding) == raw,
            "historical PUBLIC record differs",
        )
        entries.append(
            dict(cell_index=index, filename=name, byte_count=len(raw), sha256=sha(raw))
        )
    S.receipt_bytes(parse(public.raw["RECEIPT.json"]), binding)
    require(
        canonical(
            S.commit_value(
                binding, public.raw["STARTED.json"], public.raw["RECEIPT.json"], entries
            )
        )
        == commit_snapshot.raw,
        "historical PUBLIC transaction closure differs",
    )
    cohort = Archive(M.COHORT_PATH, M.NAMES)
    for name in sorted(M.NAMES):
        require(
            cohort.raw[name] == anchored(SEAL_MIRROR + "/" + name).raw,
            "original seal/mirror bytes differ",
        )
    seal, start = (
        parse(cohort.raw["preregistration.json"]),
        parse(cohort.raw["STARTED.json"]),
    )
    core.require_digest(seal)
    require(
        canonical(
            M._started(
                seal["admission_context"],
                start["owner_nonce"],
                seal["generation_qualification"],
            )
        )
        == cohort.raw["STARTED.json"]
        and canonical(M._closed(start, seal)) == cohort.raw["SEALED.json"],
        "original cohort transaction closure differs",
    )
    locations = current_locations()

    def projection(value):
        return {key: value[key] for key in ("path", "identities")}

    correspondence = mapping(
        [
            (
                "original_replication_parent",
                projection(original["output_parent"]),
                locations["output_parent"],
            ),
            (
                "original_public_parent",
                projection(old_auth["output_parent"]),
                directory_binding(PUBLIC_OUTPUT.parent),
            ),
            (
                "original_public_directory",
                dict(
                    path=str(PUBLIC_OUTPUT), identities=started["directory_identities"]
                ),
                locations["public"],
            ),
        ]
    )
    # Verify canonical parent schemas/digests as well as their path projection.
    for auth in (original, old_auth):
        parent = auth["output_parent"]
        require(
            canonical(parent)
            == canonical(
                digested(
                    dict(
                        schema_version=S.DOMAIN + "/output-parent", **projection(parent)
                    )
                )
            ),
            "historical output parent fields differ",
        )
    saved = parse(summary_snapshot.raw)
    core.require_digest(saved)
    require(
        saved["output_path"] == str(PUBLIC_OUTPUT)
        and saved["execution_commit_digest"]
        == parse(commit_snapshot.raw)["deterministic_digest"],
        "historical summary linkage differs",
    )
    result = Transport(
        tuple(snapshots),
        public,
        cohort,
        canonical(locations),
        canonical(correspondence),
        canonical(anchors),
        old_snapshot.raw,
    )
    result.revalidate()
    return result


def attest(revision):
    revision, head = R.oid(revision), core.git_head(ROOT)
    core.require_ancestor(ROOT, REVIEWED, revision)
    core.require_ancestor(ROOT, revision, head)
    require(Path(__file__).resolve() == ROOT / SCRIPT, "bridge origin differs")
    R.public._origin(R, RUNNER)
    original = R.attest(ORIGINAL_SOURCE)
    files, snapshots = {}, []
    for relative in (SCRIPT, TEST, POLICY):
        item = R.snapshot_file(ROOT / relative)
        R.reviewed_file(item, revision)
        files[relative] = dict(byte_count=len(item.raw), sha256=sha(item.raw))
        snapshots.append(item)
    for item in snapshots:
        item.revalidate()
    require(head == core.git_head(ROOT), "bridge source HEAD changed")
    return digested(
        dict(
            schema_version=DOMAIN + "/source",
            implementation_revision=revision,
            original_qualified_revision=ORIGINAL_SOURCE,
            original_source_digest=original["deterministic_digest"],
            files=files,
        )
    )


def original_reference(transport):
    saved = parse(
        next(
            item.raw
            for item in transport.snapshots
            if item.path == ROOT / PUBLIC_SUMMARY
        )
    )
    return dict(
        summary_path=str(ROOT / PUBLIC_SUMMARY),
        summary_sha256=sha(canonical(saved)),
        summary_digest=saved["deterministic_digest"],
        output_path=str(PUBLIC_OUTPUT),
        commit_digest=saved["execution_commit_digest"],
        source_digest=saved["environment"]["source"]["deterministic_digest"],
    )


def original_summary(transport, inputs, env, receipt):
    """Pure original-domain reconstruction; never a rewritten historical file."""
    b = transport.binding
    return digested(
        dict(
            schema_version=S.DOMAIN + "/analysis",
            status="CONNECTOR_INDEPENDENT_ANALYSIS_PASS",
            execution_mode=S.PUBLIC,
            experiment_id=S.PUBLIC_ID,
            output_path=str(PUBLIC_OUTPUT),
            execution_commit_digest=parse(transport.public.raw["COMMIT.json"])[
                "deterministic_digest"
            ],
            execution_receipt_digest=receipt["deterministic_digest"],
            run_binding_digest=b["deterministic_digest"],
            authorization_digest=b["authorization"]["deterministic_digest"],
            authorization_consumed=True,
            input_manifest_digest=inputs.manifest["deterministic_digest"],
            environment=env,
            integrity=receipt["integrity"],
            reduction=receipt["reduction"],
            task_count=64,
            source_multiset_count=1,
            replication_cells_executed=0,
            replication_execution_authorized=False,
            scientific_decision=None,
            locked_128_evaluation_authorized=False,
            claim_boundary="public single-source connector qualification only; no replication or causal evidence",
        )
    )


def verify_original_public(transport, env, observe):
    b, auth = transport.binding, transport.binding["authorization"]
    reviewed, head = R.oid(b["reviewed_revision"]), R.oid(b["execution_head_revision"])
    core.require_ancestor(ROOT, ORIGINAL_SOURCE, reviewed)
    core.require_ancestor(ROOT, reviewed, head)
    core.require_ancestor(ROOT, head, REVIEWED)
    inputs = R.load_inputs(S.PUBLIC)
    # Both exact historical parent bindings were authenticated and mapped above.
    # Compare all other candidate bytes; do NOT create an old admission object.
    current = R.candidate(inputs, PUBLIC_OUTPUT, env, None)

    def nonlocation(value):
        return {
            key: item
            for key, item in value.items()
            if key not in ("output_parent", "deterministic_digest")
        }

    require(
        canonical(nonlocation(current)) == canonical(nonlocation(auth)),
        "original PUBLIC candidate environment differs",
    )
    transport.revalidate()
    observe("ORIGINAL_PUBLIC_REPLAY_1024_AND_PREFIX_512")
    rows = [
        S.parse(transport.public.raw[name], S.base.MAX_CELL_BYTES)
        for name in S.base.CELL_NAMES
    ]
    receipt = R.reduce_rows(inputs, rows, b)
    require(
        canonical(receipt) == transport.public.raw["RECEIPT.json"],
        "original PUBLIC receipt did not reproduce",
    )
    summary = original_summary(transport, inputs, env, receipt)
    saved_raw = next(
        item.raw for item in transport.snapshots if item.path == ROOT / PUBLIC_SUMMARY
    )
    require(
        canonical(summary) == saved_raw,
        "complete original PUBLIC summary did not reproduce",
    )
    reference = original_reference(transport)
    require(
        canonical(reference)
        == canonical(transport.original["connector_qualification"]),
        "original candidate PUBLIC reference differs",
    )
    R.check_environment(env)
    transport.revalidate()
    return reference


def input_projection(seal):
    return digested(
        dict(
            schema_version=S.DOMAIN + "/sealed-inputs",
            execution_mode=S.REPLICATION,
            experiment_id=S.REPLICATION_ID,
            contract_digest=seal["contract"]["deterministic_digest"],
            tasks=seal["cohort"]["tasks"],
            cells=seal["cells"],
            schedule_digest=seal["schedule_digest"],
            cohort_seal=dict(
                path=str(M.COHORT_PATH),
                seal_digest=seal["deterministic_digest"],
                seal_sha256=sha(canonical(seal)),
                cohort_digest=seal["cohort"]["deterministic_digest"],
            ),
            task_count=64,
            source_multiset_count=64,
            cell_count=1024,
            replication_execution_authorized=False,
        )
    )


def verify_original_seal(transport, env, reference, observe):
    raw = transport.cohort.raw["preregistration.json"]
    value, contract = parse(raw), M.contract.build_contract()
    require(
        canonical(value["contract"]) == canonical(contract),
        "original sealed contract differs",
    )
    require(
        canonical(value["admission_context"]) == canonical(env["admission_proof"]),
        "original generation admission differs",
    )
    M.generation_reference_shape(reference)
    require(
        canonical(reference) == canonical(value["generation_qualification"]),
        "original generation qualification differs",
    )
    M._cohort_shape(value["cohort"], contract, env["authorities"])
    require(
        canonical(M._seal(value["cohort"], contract, env["admission_proof"], reference))
        == raw,
        "closed original sealed metadata differs",
    )
    projection = input_projection(value)
    old = transport.original
    for key in ("contract_digest", "schedule_digest", "cohort_seal"):
        require(
            canonical(projection[key]) == canonical(old[key]),
            "original input projection differs",
        )
    require(
        projection["deterministic_digest"] == old["input_manifest_digest"],
        "original input digest differs",
    )
    transport.revalidate()
    M.revalidate_context(env["admission_proof"])
    observe("ORIGINAL_64_TASK_ACCEPTANCE_ORDER_VERIFICATION_NO_SEARCH")
    reproduced = M._cohort(contract, env["authorities"])
    require(
        canonical(M._seal(reproduced, contract, env["admission_proof"], reference))
        == raw,
        "original cohort acceptance order did not reproduce",
    )
    transport.revalidate()
    M.revalidate_context(env["admission_proof"])
    return projection


def certificate_projection(transport, source):
    """Deterministic expected metadata, NOT evidence that verification ran."""
    seal = parse(transport.cohort.raw["preregistration.json"])
    receipt = parse(transport.public.raw["RECEIPT.json"])
    return digested(
        dict(
            schema_version=DOMAIN + "/certificate",
            status="ORIGINAL_EVIDENCE_REATTESTED_NOT_EXECUTION_AUTHORITY",
            historical_review_revision=REVIEWED,
            original_candidate_digest=ORIGINAL_DIGEST,
            anchors=parse(transport.anchors_raw),
            location_correspondence=parse(transport.correspondence_raw),
            current_locations=parse(transport.locations_raw),
            source=source,
            public_verification=dict(
                reference=original_reference(transport),
                receipt_digest=receipt["deterministic_digest"],
                full_summary_byte_identical=True,
                original_baseline_traces_requalified=32,
                original_traces_replayed=1024,
                original_budget_prefixes_verified=512,
                new_execution_orchestration_run=False,
                scientific_decision=None,
            ),
            sealed_input_verification=dict(
                seal_digest=seal["deterministic_digest"],
                cohort_digest=seal["cohort"]["deterministic_digest"],
                task_set_digest=seal["cohort"]["task_set_digest"],
                schedule_digest=seal["schedule_digest"],
                input_manifest_digest=input_projection(seal)["deterministic_digest"],
                original_tasks_verified=64,
                replacement_tasks_generated=0,
                calibration_or_witness_objects_accessed=0,
            ),
            fixed_claim_path=str(fixed_claim()),
            replication_search_calls=0,
            replication_execution_authorized=False,
            candidate_is_execution_authority=False,
            locked_128_evaluation_authorized=False,
            claim_boundary="explicit current-receiver correspondence and exact original evidence reconstruction only; not physical-disk/reboot proof, new orchestration qualification, replication or causal evidence",
        )
    )


def certificate_shape(raw):
    value = parse(raw)
    core.require_digest(value)
    require(
        set(value) == CERT_FIELDS
        and value["schema_version"] == DOMAIN + "/certificate",
        "closed receiver certificate required",
    )
    require(
        value["historical_review_revision"] == REVIEWED
        and value["original_candidate_digest"] == ORIGINAL_DIGEST
        and value["fixed_claim_path"] == str(fixed_claim()),
        "certificate historical scope differs",
    )
    require(
        value["replication_execution_authorized"] is False
        and value["candidate_is_execution_authority"] is False
        and value["locked_128_evaluation_authorized"] is False
        and type(value["replication_search_calls"]) is int
        and value["replication_search_calls"] == 0,
        "certificate authority flags differ",
    )
    return value


@dataclass(frozen=True)
class Proof:
    transport: Transport
    source_raw: bytes
    environment_raw: bytes
    inputs_raw: bytes
    certificate_raw: bytes

    def revalidate(self):
        self.transport.revalidate()
        source = parse(self.source_raw)
        require(
            canonical(attest(source["implementation_revision"])) == self.source_raw,
            "bridge source changed",
        )
        R.check_environment(parse(self.environment_raw))


def reconstruct(revision, *, expected=None, observe=lambda stage: None):
    transport = inspect_transport()
    observe("HISTORICAL_CONTENT_AND_CURRENT_LOCATIONS_CLOSED")
    source = attest(revision)
    certificate = certificate_projection(transport, source)
    if expected is not None:
        certificate_shape(expected)
        require(
            canonical(certificate) == expected,
            "reviewed certificate differs before qualification",
        )
    # No certificate or seal callback is accepted as proof. Only this complete
    # ordered execution returns Proof. The template above is just a comparator.
    observe("ORIGINAL_SOURCE_RUNTIME_AUTHORITIES_AND_BASELINE")
    env = R.environment(ORIGINAL_SOURCE)
    for key, value in env.items():
        require(
            canonical(value) == canonical(transport.original[key]),
            "original environment did not reproduce",
        )
    reference = verify_original_public(transport, env, observe)
    projection = verify_original_seal(transport, env, reference, observe)
    result = Proof(
        transport,
        canonical(source),
        canonical(env),
        canonical(projection),
        canonical(certificate),
    )
    result.revalidate()
    observe("EXACT_ORIGINAL_EVIDENCE_REATTESTED")
    return result


def candidate_projection(original, certificate):
    current_parent = digested(
        dict(
            schema_version=S.DOMAIN + "/output-parent",
            **certificate["current_locations"]["output_parent"],
        )
    )
    return digested(
        {
            **without_digest(original),
            "schema_version": DOMAIN + "/authorization-candidate",
            "output_parent": current_parent,
            "receiver_certificate": dict(
                path=str(ROOT / CERTIFICATE),
                byte_count=len(canonical(certificate)),
                sha256=sha(canonical(certificate)),
                deterministic_digest=certificate["deterministic_digest"],
            ),
            "bridge_source": certificate["source"],
        }
    )


def auth_shape(raw, confirmed):
    value = parse(raw)
    core.require_digest(value)
    require(
        set(value) == AUTH_FIELDS
        and value["schema_version"] == DOMAIN + "/authorization-candidate",
        "new receiver candidate domain required",
    )
    require(
        type(confirmed) is str and value["deterministic_digest"] == confirmed,
        "explicit receiver candidate digest differs",
    )
    require(
        value["execution_mode"] == S.REPLICATION
        and value["experiment_id"] == S.REPLICATION_ID
        and value["output_path"] == str(OUTPUT),
        "fixed replication study differs",
    )
    require(
        value["candidate_is_execution_authority"] is False
        and value["requires_explicit_digest_confirmation"] is True
        and value["locked_128_evaluation_authorized"] is False
        and value["status"] == "REVIEW_AND_EXPLICIT_CONFIRMATION_REQUIRED"
        and type(value["expected_cell_count"]) is int
        and value["expected_cell_count"] == 1024,
        "receiver candidate authority flags differ",
    )
    require(
        type(value["receiver_certificate"]) is dict
        and type(value["bridge_source"]) is dict,
        "receiver certificate/source required",
    )
    return value


def bundle_commit(certificate_raw, authorization_raw):
    return digested(
        dict(
            schema_version=DOMAIN + "/candidate-publication",
            status="CANDIDATE_PUBLISHED_NOT_AUTHORIZED",
            files={
                "certificate.json": dict(
                    byte_count=len(certificate_raw), sha256=sha(certificate_raw)
                ),
                "authorization.json": dict(
                    byte_count=len(authorization_raw), sha256=sha(authorization_raw)
                ),
            },
            replication_execution_authorized=False,
        )
    )


def prepare(revision, observe=lambda stage: None):
    unused()
    require(
        not os.path.lexists(BUNDLE),
        "candidate bundle occupied; no overwrite or adoption",
    )
    S.descriptor_preflight()
    proof = reconstruct(revision, observe=observe)
    certificate = certificate_shape(proof.certificate_raw)
    auth = candidate_projection(proof.transport.original, certificate)
    raws = {
        "certificate.json": proof.certificate_raw,
        "authorization.json": canonical(auth),
    }
    raws["COMMIT.json"] = canonical(
        bundle_commit(raws["certificate.json"], raws["authorization.json"])
    )
    unused()
    proof.revalidate()
    parent, owned = None, []
    try:
        parent = S.base.storage._create_directory(BUNDLE)
        for name in ("certificate.json", "authorization.json", "COMMIT.json"):
            unused()
            proof.revalidate()
            try:
                item = S.mechanics._exclusive_create_exact(
                    parent,
                    name,
                    raws[name],
                    max_bytes=S.base.MAX_CONTROL_BYTES,
                    hook=None,
                )
            except S.mechanics._CreateAfterOpenError as error:
                owned.append(error.owned)
                raise
            owned.append(item)
            S.base._observe(parent, {x.name for x in owned}, owned=owned)
        final, _ = S.base._observe(parent, BUNDLE_NAMES, owned=owned)
        require(final == raws, "candidate bundle bytes differ")
        unused()
        proof.revalidate()
        return auth
    finally:
        for item in reversed(owned):
            item.close()
        if parent is not None:
            parent.close()


@dataclass(frozen=True)
class VerifiedInputs:
    """Internal detached inputs, not a public admission capability."""

    raw: bytes
    _cells: tuple = field(init=False, repr=False)
    _tasks: tuple = field(init=False, repr=False)

    def __post_init__(self):
        value = parse(self.raw)
        object.__setattr__(
            self, "_cells", tuple(canonical(cell) for cell in value["cells"])
        )
        object.__setattr__(
            self, "_tasks", tuple(canonical(task) for task in value["tasks"])
        )

    @property
    def manifest(self):
        return parse(self.raw)

    @property
    def cells(self):
        return [parse(raw) for raw in self._cells]

    def arguments(self, cell):
        require(
            type(cell) is dict and type(cell.get("cell_index")) is int,
            "plain indexed cell required",
        )
        index = cell["cell_index"]
        require(
            0 <= index < 1024 and canonical(cell) == self._cells[index],
            "complete immutable cell differs",
        )
        key = cell["cell_key"]
        row = parse(self._tasks[key["task_slot"]])
        return dict(
            task=q.CountdownTask(tuple(row["inputs"]), row["target"]),
            proposal=q.PROPOSAL,
            method=q.method(key["scale"]),
            budget_profile=q.profile(key["budget"]),
            exploration_seed=key["seed"],
        )


@dataclass(frozen=True)
class Admitted:
    proof: Proof
    snapshots: tuple
    reviewed: str
    head: str

    @property
    def auth(self):
        return parse(self.snapshots[0].raw)

    @property
    def inputs(self):
        return VerifiedInputs(self.proof.inputs_raw)

    def revalidate(self):
        for item in self.snapshots:
            R.reviewed_file(item, self.reviewed)
        self.proof.revalidate()


def admit(
    auth_path,
    cert_path,
    confirmed,
    reviewed,
    *,
    execution_head=None,
    observe=lambda stage: None,
):
    """Paths + exact reviewed bytes only. No caller-supplied admission object."""
    require(
        Path(auth_path) == ROOT / CANDIDATE and Path(cert_path) == ROOT / CERTIFICATE,
        "fixed promoted candidate/certificate paths required",
    )
    snapshot, cert_snapshot = R.snapshot_file(auth_path), R.snapshot_file(cert_path)
    auth_shape(snapshot.raw, confirmed)
    cert = certificate_shape(cert_snapshot.raw)
    reviewed, head = R.oid(reviewed), R.oid(execution_head or core.git_head(ROOT))
    revision = R.oid(cert["source"]["implementation_revision"])
    core.require_ancestor(ROOT, revision, reviewed)
    core.require_ancestor(ROOT, reviewed, head)
    core.require_ancestor(ROOT, head, core.git_head(ROOT))
    commit_snapshot = R.snapshot_file(ROOT / BUNDLE_COMMIT)
    for item in (snapshot, cert_snapshot, commit_snapshot):
        R.reviewed_file(item, reviewed)
    require(
        commit_snapshot.raw
        == canonical(bundle_commit(cert_snapshot.raw, snapshot.raw)),
        "reviewed candidate bundle closure differs",
    )
    original = R.snapshot_file(ROOT / ORIGINAL_CANDIDATE)
    R.reviewed_file(original, REVIEWED)
    require(
        snapshot.raw == canonical(candidate_projection(parse(original.raw), cert)),
        "candidate/certificate projection differs before qualification",
    )
    proof = reconstruct(revision, expected=cert_snapshot.raw, observe=observe)
    require(
        snapshot.raw
        == canonical(
            candidate_projection(proof.transport.original, parse(proof.certificate_raw))
        ),
        "independently reconstructed receiver candidate differs",
    )
    result = Admitted(
        proof, (snapshot, cert_snapshot, commit_snapshot, original), reviewed, head
    )
    result.revalidate()
    return result


def verify_candidate(
    auth_path, cert_path, confirmed, reviewed, observe=lambda stage: None
):
    unused()
    admitted = admit(auth_path, cert_path, confirmed, reviewed, observe=observe)
    unused()
    admitted.revalidate()
    return digested(
        dict(
            schema_version=DOMAIN + "/candidate-verification",
            status="RECEIVER_CANDIDATE_INDEPENDENTLY_RECONSTRUCTED_NOT_AUTHORIZED",
            authorization_digest=admitted.auth["deterministic_digest"],
            certificate_digest=parse(admitted.proof.certificate_raw)[
                "deterministic_digest"
            ],
            reviewed_revision=reviewed,
            source=parse(admitted.proof.source_raw),
            replication_search_calls=0,
            replication_execution_authorized=False,
            original_claim_unoccupied=True,
            new_execution_orchestration_run=False,
        )
    )


def run_binding(admitted, claim):
    auth = admitted.auth
    return S.frozen_binding(
        digested(
            dict(
                schema_version=S.DOMAIN + "/run-binding",
                execution_mode=S.REPLICATION,
                experiment_id=S.REPLICATION_ID,
                input_manifest_digest=auth["input_manifest_digest"],
                authorization=auth,
                authorization_path=str(admitted.snapshots[0].path),
                reviewed_revision=admitted.reviewed,
                execution_head_revision=admitted.head,
                claim=claim,
                replication_execution_authorized=True,
            )
        )
    )


def run(auth_path, cert_path, confirmed, reviewed, observe=lambda stage: None):
    unused()
    S.descriptor_preflight()
    admitted = admit(auth_path, cert_path, confirmed, reviewed, observe=observe)
    unused()
    admitted.revalidate()
    claim, snapshot = S.consume(
        admitted.auth, admitted.reviewed, admitted.head, core.FileSnapshot
    )
    try:
        binding = run_binding(admitted, claim)
        inputs = admitted.inputs

        def check():
            snapshot.revalidate()
            require(
                canonical(S.parent_binding(OUTPUT))
                == canonical(admitted.auth["output_parent"]),
                "authorized receiver parent changed",
            )
            admitted.revalidate()

        def action(emit):
            rows = []
            for cell in inputs.cells:
                row = R.record(inputs, cell, binding)
                emit(cell["cell_index"], row)
                rows.append(row)
                if len(rows) % 32 == 0:
                    observe("REPLICATION_CELLS_" + str(len(rows)))
            return R.reduce_rows(inputs, rows, binding)

        return S.publish(OUTPUT, binding, action, check)
    except S.ExecutionFailure:
        raise
    except BaseException as error:
        raise S.ExecutionFailure(
            "SPENT_NOT_RUN", True, "claim consumed; retain claim and any publication"
        ) from error


def analyze(observe=lambda stage: None):
    publication = S.inspect(OUTPUT)
    b = publication.binding
    require(b["execution_mode"] == S.REPLICATION, "receiver analysis mode differs")
    auth_shape(
        canonical(b["authorization"]), b["authorization"]["deterministic_digest"]
    )
    # Analysis requires the exact spent claim, not absence. Check it before any
    # expensive historical reconstruction; never use analysis to revive a slot.
    claim = S.inspect_claim(b, core.FileSnapshot)
    admitted = admit(
        b["authorization_path"],
        b["authorization"]["receiver_certificate"]["path"],
        b["authorization"]["deterministic_digest"],
        b["reviewed_revision"],
        execution_head=b["execution_head_revision"],
        observe=observe,
    )
    require(
        canonical(run_binding(admitted, b["claim"])) == canonical(b),
        "receiver admitted binding differs",
    )

    def check():
        publication.revalidate()
        claim.revalidate()
        admitted.revalidate()

    check()
    receipt = R.reduce_rows(admitted.inputs, publication.rows, b)
    require(
        canonical(receipt) == canonical(publication.receipt),
        "receiver independent receipt differs",
    )
    check()
    value = digested(
        dict(
            schema_version=DOMAIN + "/analysis",
            status="RECEIVER_EXECUTION_INDEPENDENT_ANALYSIS_PASS",
            execution_mode=S.REPLICATION,
            experiment_id=S.REPLICATION_ID,
            output_path=str(OUTPUT),
            execution_commit_digest=publication.commit["deterministic_digest"],
            execution_receipt_digest=receipt["deterministic_digest"],
            run_binding_digest=b["deterministic_digest"],
            authorization_digest=admitted.auth["deterministic_digest"],
            receiver_certificate=admitted.auth["receiver_certificate"],
            bridge_source=parse(admitted.proof.source_raw),
            original_environment=parse(admitted.proof.environment_raw),
            input_manifest_digest=admitted.inputs.manifest["deterministic_digest"],
            authorization_consumed=True,
            integrity=receipt["integrity"],
            reduction=receipt["reduction"],
            task_count=64,
            source_multiset_count=64,
            replication_cells_executed=receipt["replication_cells_executed"],
            replication_execution_authorized=True,
            scientific_decision=receipt["scientific_decision"],
            locked_128_evaluation_authorized=False,
            claim_boundary="64 source-distinct task clusters; finite-cohort replication engineering screen only; no population inference, causal or further execution authority",
        )
    )
    return value, check


def analyze_and_save(summary_path, observe=lambda stage: None):
    summary_path = R.public._output(summary_path)
    require(not os.path.lexists(summary_path), "receiver summary occupied")
    value, check = analyze(observe)
    S.base._publish_summary(summary_path, value, check)
    return value


def verify(summary_path, observe=lambda stage: None):
    snapshot = R.snapshot_file(R.public._output(summary_path))
    saved = parse(snapshot.raw)
    core.require_digest(saved)
    require(
        saved.get("schema_version") == DOMAIN + "/analysis",
        "receiver summary domain differs",
    )
    value, check = analyze(observe)
    require(
        canonical(value) == snapshot.raw, "saved receiver summary did not reproduce"
    )
    snapshot.revalidate()
    check()
    return value


def self_test():
    require(
        fixed_claim()
        == S.LEDGER / ("replication-" + digest([S.DOMAIN, S.REPLICATION_ID]) + ".json"),
        "fixed claim namespace changed",
    )
    require(
        AUTH_FIELDS != R.AUTH_FIELDS and len(S.NAMES) == 1027, "bridge closure differs"
    )
    return dict(
        status="RECEIVER_STATIC_SELF_TEST_PASS",
        replication_search_calls=0,
        replication_execution_authorized=False,
        claim_boundary="static schema/namespace checks only; not source qualification, re-attestation, orchestration or replication",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_mutually_exclusive_group(required=True)
    for command in (
        "self-test",
        "inventory",
        "prepare",
        "verify-candidate",
        "run-replication",
        "analyze-replication",
        "verify-replication",
    ):
        commands.add_argument("--" + command, action="store_true")
    options = (
        "implementation-revision",
        "authorization",
        "certificate",
        "confirm-digest",
        "reviewed-revision",
        "summary",
    )
    for option in options:
        parser.add_argument("--" + option)
    args = vars(parser.parse_args())
    command = next(name for name, value in args.items() if value is True)
    entry = {"authorization", "certificate", "confirm_digest", "reviewed_revision"}
    allowed = {
        "self_test": set(),
        "inventory": set(),
        "prepare": {"implementation_revision"},
        "verify_candidate": entry,
        "run_replication": entry,
        "analyze_replication": {"summary"},
        "verify_replication": {"summary"},
    }[command]
    actual = {
        name.replace("-", "_")
        for name in options
        if args[name.replace("-", "_")] is not None
    }
    if actual != allowed:
        parser.error("exact mode-specific arguments required")

    def observe(stage):
        print(canonical(dict(stage=stage)).decode(), end="", flush=True)

    completed = False
    try:
        if command == "self_test":
            result = self_test()
        elif command == "inventory":
            unused()
            transport = inspect_transport()
            result = dict(
                status="HISTORICAL_CONTENT_ONLY_CLOSED_NOT_REPLAYED",
                anchors=parse(transport.anchors_raw),
                locations=parse(transport.locations_raw),
                correspondence=parse(transport.correspondence_raw),
                replication_search_calls=0,
                replication_execution_authorized=False,
            )
        elif command == "prepare":
            auth = prepare(args["implementation_revision"], observe)
            result = dict(
                status="RECEIVER_CANDIDATE_PREPARED_NOT_AUTHORIZED",
                authorization_digest=auth["deterministic_digest"],
                certificate=auth["receiver_certificate"],
                bundle_path=str(BUNDLE),
                replication_search_calls=0,
                replication_execution_authorized=False,
            )
        elif command in ("verify_candidate", "run_replication"):
            function = verify_candidate if command == "verify_candidate" else run
            result = function(
                args["authorization"],
                args["certificate"],
                args["confirm_digest"],
                args["reviewed_revision"],
                observe,
            )
        elif command == "analyze_replication":
            result = analyze_and_save(args["summary"], observe)
        else:
            result = verify(args["summary"], observe)
        completed = True
        print(canonical(result).decode(), end="", flush=True)
        return 0
    except BaseException as error:
        # Do not infer non-consumption after a racing/uncertain ledger operation.
        if completed:
            status = "RESULT_DELIVERY_UNCERTAIN"
            consumed = command in (
                "run_replication",
                "analyze_replication",
                "verify_replication",
            )
        elif isinstance(error, S.ExecutionFailure):
            status, consumed = error.status, error.authorization_consumed
        elif isinstance(error, S.base.PublicationUncertain):
            status, consumed = "PUBLICATION_UNCERTAIN", None
        else:
            status = "RECEIVER_VERIFICATION_FAILED"
            consumed = True if os.path.lexists(fixed_claim()) else None
        print(
            canonical(
                dict(
                    status=status,
                    error_type=type(error).__name__,
                    error=str(error),
                    operation_completed=completed,
                    authorization_consumed=consumed,
                    scientific_decision=None,
                    locked_128_evaluation_authorized=False,
                )
            ).decode(),
            end="",
            file=sys.stderr,
            flush=True,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
