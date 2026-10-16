#!/usr/bin/env python3
"""Fixed, read-only historical byte/provenance inspection; never admission.

No replay, publication, candidate, consumption, or execution entry point exists.
Pure metadata helpers are comparators, not provenance or proof constructors.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import importlib.util
from pathlib import Path
import re
import sys
from types import MappingProxyType


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = "scripts/inspect_feedback_budget_receiver_successor.py"
TEST = "tests/test_feedback_budget_receiver_successor_inspection.py"
POLICY = "docs/strategy/countdown_feedback_budget_receiver_successor_inspection.md"
SOURCE_FILES = (SCRIPT, TEST, POLICY)
DESIGN_REVISION = "96890dea719b9de5f14f1a1afe7147d4951b16e0"
PREPARER = "scripts/feedback_budget_receiver_candidate.py"
PREPARER_REVISION = "9d14059362e18a396e4fa865d8a0b3c69fde1eb6"
EVIDENCE_REVIEW = "667cc144ccb70073be8224a69b778f65107109da"
SPEC = importlib.util.spec_from_file_location(
    "successor_inspection_preparer", ROOT / PREPARER
)
assert SPEC is not None and SPEC.loader is not None
P = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = P
SPEC.loader.exec_module(P)
C, B, R, S, core = P.C, P.B, P.R, P.S, P.core
canonical, parse, require, digested, sha = (
    P.canonical,
    P.parse,
    P.require,
    P.digested,
    P.sha,
)
DOMAIN = S.DOMAIN + "/receiver-successor-inspection/v1"
STATUS = "READ_ONLY_METADATA_MATCH_NOT_RECONSTRUCTED_OR_AUTHORIZED"
CLAIM_BOUNDARY = "Read-only reviewed-byte, schema and metadata correspondence only. Saved numerical results remain historical. No reconstruction, admission, certificate, candidate, qualification, consent or execution."
CANDIDATE_DIGEST = "198f4582054184e2e476542afc1621178b3a1fbc6b82bd002b67f99c6684d070"
CANDIDATE_SHA = "7adaeba09ffdc21f21a852ad047b1aa7e0914ec284063a3ce768d410147fbb5b"
VERIFICATION = "docs/qualifications/countdown_feedback_budget_receiver_v2_candidate_20260923.verification.json"
EPOCH_DEVICES = MappingProxyType(
    {"original_v7": 16777233, "receiver_20260921": 16777231}
)
CURRENT_DEVICE = 16777234
LOCATIONS = MappingProxyType(
    {
        "original_public": B.PUBLIC_OUTPUT,
        "receiver_v2_public": C.PUBLIC_OUTPUT,
        "cohort": B.M.COHORT_PATH,
        "output_parent": B.OUTPUT.parent,
        "ledger": S.LEDGER,
        "old_bridge_bundle_current_only": B.BUNDLE,
    }
)
# label, epoch, owning path, authenticating Git path, review, JSON pointer, role
REGISTRY = (
    (
        "original_replication_parent",
        "original_v7",
        B.ORIGINAL_CANDIDATE,
        B.ORIGINAL_CANDIDATE,
        B.REVIEWED,
        "/output_parent",
        "output_parent",
    ),
    (
        "original_public_authorization_parent",
        "original_v7",
        str(B.PUBLIC_OUTPUT / "STARTED.json"),
        B.PUBLIC_COMMIT,
        B.REVIEWED,
        "/binding/authorization/output_parent",
        "output_parent",
    ),
    (
        "original_public_started_directory",
        "original_v7",
        str(B.PUBLIC_OUTPUT / "STARTED.json"),
        B.PUBLIC_COMMIT,
        B.REVIEWED,
        "/directory_identities",
        "original_public",
    ),
    (
        "bridge_certificate_public",
        "receiver_20260921",
        B.CERTIFICATE,
        B.CERTIFICATE,
        C.BRIDGE_REVIEWED,
        "/current_locations/public",
        "original_public",
    ),
    (
        "bridge_certificate_cohort",
        "receiver_20260921",
        B.CERTIFICATE,
        B.CERTIFICATE,
        C.BRIDGE_REVIEWED,
        "/current_locations/cohort",
        "cohort",
    ),
    (
        "bridge_certificate_output_parent",
        "receiver_20260921",
        B.CERTIFICATE,
        B.CERTIFICATE,
        C.BRIDGE_REVIEWED,
        "/current_locations/output_parent",
        "output_parent",
    ),
    (
        "bridge_certificate_ledger",
        "receiver_20260921",
        B.CERTIFICATE,
        B.CERTIFICATE,
        C.BRIDGE_REVIEWED,
        "/current_locations/ledger",
        "ledger",
    ),
    (
        "bridge_candidate_parent",
        "receiver_20260921",
        B.CANDIDATE,
        B.CANDIDATE,
        C.BRIDGE_REVIEWED,
        "/output_parent",
        "output_parent",
    ),
    (
        "v2_replication_parent",
        "receiver_20260921",
        C.REPLICATION_AUTH,
        C.REPLICATION_AUTH,
        EVIDENCE_REVIEW,
        "/output_parent",
        "output_parent",
    ),
    (
        "receiver_v2_public_authorization_parent",
        "receiver_20260921",
        str(C.PUBLIC_OUTPUT / "STARTED.json"),
        C.COMMIT_MIRROR,
        P.PUBLIC_REVIEW,
        "/binding/authorization/output_parent",
        "output_parent",
    ),
    (
        "receiver_v2_public_started_directory",
        "receiver_20260921",
        str(C.PUBLIC_OUTPUT / "STARTED.json"),
        C.COMMIT_MIRROR,
        P.PUBLIC_REVIEW,
        "/directory_identities",
        "receiver_v2_public",
    ),
)
ANCHORS = (
    (B.ORIGINAL_CANDIDATE, B.REVIEWED),
    (B.PUBLIC_COMMIT, B.REVIEWED),
    (B.PUBLIC_SUMMARY, B.REVIEWED),
    *((B.SEAL_MIRROR + "/" + n, B.REVIEWED) for n in sorted(B.M.NAMES)),
    (B.CERTIFICATE, C.BRIDGE_REVIEWED),
    (B.CANDIDATE, C.BRIDGE_REVIEWED),
    (B.BUNDLE_COMMIT, C.BRIDGE_REVIEWED),
    (C.PUBLIC_AUTH, P.PUBLIC_REVIEW),
    (C.COMMIT_MIRROR, P.PUBLIC_REVIEW),
    (C.SUMMARY_MIRROR, P.PUBLIC_REVIEW),
    (P.PUBLIC_VERIFICATION, P.PUBLIC_REVIEW),
    (C.REPLICATION_AUTH, EVIDENCE_REVIEW),
    (P.PREPARATION_MIRROR, EVIDENCE_REVIEW),
    (VERIFICATION, EVIDENCE_REVIEW),
)
PUBLIC_SPECS = MappingProxyType(
    {
        "original_public": (
            B.PUBLIC_OUTPUT,
            B.PUBLIC_COMMIT,
            B.PUBLIC_SUMMARY,
            Path(str(B.PUBLIC_OUTPUT) + ".authorization.json"),
            B.ORIGINAL_SOURCE,
        ),
        "receiver_v2_public": (
            C.PUBLIC_OUTPUT,
            C.COMMIT_MIRROR,
            C.SUMMARY_MIRROR,
            ROOT / C.PUBLIC_AUTH,
            "fbd51b18dbefb7908c4637f872ff3a455b2c58bf",
        ),
    }
)


def exact(left, right, reason):
    require(canonical(left) == canonical(right), reason)


def location(value, path, device):
    require(
        type(value) is dict and set(value) == {"path", "identities"},
        "closed location required",
    )
    require(
        type(value["path"]) is str and value["path"] == str(path),
        "fixed lexical path required",
    )
    parts = Path(value["path"]).parts
    require(
        Path(value["path"]).is_absolute()
        and ".." not in parts
        and str(Path(value["path"])) == value["path"],
        "path alias forbidden",
    )
    identities = value["identities"]
    require(
        type(identities) is list and len(identities) == len(parts),
        "complete component chain required",
    )
    for pair in identities:
        require(
            type(pair) is list
            and len(pair) == 2
            and all(type(n) is int and n >= 0 for n in pair),
            "plain integer identity pairs required",
        )
        require(
            pair[0] == device, "exact epoch device required; no automatic rebinding"
        )
    return value


def owner(spec):
    return dict(
        path=spec[2],
        authenticated_by=spec[3],
        reviewed_revision=spec[4],
        json_pointer=spec[5],
    )


def recorded_chains(values):
    """Extract ONLY this registry, after the caller authenticates owning bytes."""
    result = []
    for spec in REGISTRY:
        label, epoch, path, _, _, pointer, role = spec
        value = values[path]
        for field in pointer.lstrip("/").split("/"):
            value = value[field]
        if pointer == "/directory_identities":
            old = dict(path=str(LOCATIONS[role]), identities=value)
        elif pointer.endswith("output_parent") or pointer == "/output_parent":
            # Certificate locations have two fields; candidate parents have four.
            old = {key: value[key] for key in ("path", "identities")}
            if pointer.startswith("/current_locations/"):
                exact(value, old, "certificate location fields differ")
            else:
                exact(
                    value,
                    digested(dict(schema_version=S.DOMAIN + "/output-parent", **old)),
                    "historical parent schema differs",
                )
        else:
            old = value
        result.append(
            dict(label=label, historical_epoch=epoch, owner=owner(spec), historical=old)
        )
    return result


def correspondence(chains, locations):
    """Pure, closed metadata comparator. It grants no provenance or authority."""
    require(
        type(chains) is list and len(chains) == len(REGISTRY),
        "exact eleven recorded chains required",
    )
    require(
        type(locations) is dict and set(locations) == set(LOCATIONS),
        "exact six current roles required",
    )
    current_prefixes, historical_prefixes = {}, {}

    def prefixes(binding, table):
        parts = Path(binding["path"]).parts
        for index, pair in enumerate(binding["identities"]):
            prefix = str(Path(*parts[: index + 1]))
            require(
                prefix not in table or table[prefix] == pair,
                "shared prefix identity differs",
            )
            table[prefix] = pair

    for role, path in LOCATIONS.items():
        prefixes(location(locations[role], path, CURRENT_DEVICE), current_prefixes)
    counts = {epoch: 0 for epoch in EPOCH_DEVICES}
    for record, spec in zip(chains, REGISTRY):
        label, epoch, _, _, _, _, role = spec
        require(
            type(record) is dict
            and set(record) == {"label", "historical_epoch", "owner", "historical"},
            "closed chain record required",
        )
        exact(
            {key: record[key] for key in ("label", "historical_epoch", "owner")},
            dict(label=label, historical_epoch=epoch, owner=owner(spec)),
            "registry order, epoch or owner differs",
        )
        old = location(record["historical"], LOCATIONS[role], EPOCH_DEVICES[epoch])
        now = locations[role]
        require(
            all(
                left[1] == right[1]
                for left, right in zip(old["identities"], now["identities"])
            ),
            "historical inode differs",
        )
        prefixes(old, historical_prefixes.setdefault(epoch, {}))
        counts[epoch] += 1
    return dict(
        policy="fixed_E0_E1_to_E2_same_path_inode_metadata_only/v1",
        epochs={
            epoch: dict(
                historical_device=device,
                observed_device=CURRENT_DEVICE,
                chain_count=counts[epoch],
            )
            for epoch, device in EPOCH_DEVICES.items()
        },
        chains=parse(canonical({"chains": chains}))["chains"],
        current_locations=parse(canonical(locations)),
        metadata_correspondence_matches=True,
        current_receiver_admitted=False,
        physical_disk_identity_proven=False,
        reboot_causality_proven=False,
    )


def current_locations():
    return {
        role: B.directory_binding(path, private=role != "output_parent")
        for role, path in LOCATIONS.items()
    }


def _read_archive(path, names):
    """Only no-follow reads/stat/listdir: deliberately NOT B.Archive/_observe.

    The old _observe performs forward fsync. Do not import its durability effects
    into this inspection. Filesystem-managed access timestamps are not controlled.
    """
    parent = S.mechanics._PinnedParent.open(path)
    try:
        generation = S.base.storage._generation(parent, names)
        raw, total = {}, 0
        for name in sorted(names):
            cap = (
                S.base.MAX_CELL_BYTES
                if name in S.base.CELL_NAMES
                else S.base.MAX_CONTROL_BYTES
            )
            raw[name] = S.mechanics._read_bounded_regular_file_at(
                parent, name, max_bytes=cap
            )
            total += len(raw[name])
            require(total <= S.base.MAX_TOTAL_BYTES, "archive byte limit exceeded")
        require(
            generation == S.base.storage._generation(parent, names),
            "archive generation changed while reading",
        )
        return raw, generation, parent.component_identities
    finally:
        parent.close()


@dataclass(frozen=True)
class ReadOnlyArchive:
    path: Path
    names: frozenset
    raw: object
    generation: tuple
    identities: tuple

    @classmethod
    def capture(cls, path, names):
        require(
            all(
                type(n) is str and Path(n).name == n and n not in ("", ".", "..")
                for n in names
            ),
            "direct archive filenames required",
        )
        path, names = Path(path), frozenset(names)
        raw, generation, identities = _read_archive(path, names)
        return cls(path, names, MappingProxyType(raw), generation, identities)

    def revalidate(self):
        raw, generation, identities = _read_archive(self.path, self.names)
        require(
            raw == dict(self.raw)
            and generation == self.generation
            and identities == self.identities,
            "archive content, generation or identity changed",
        )


def closed_source(files):
    require(
        SOURCE_FILES == (SCRIPT, TEST, POLICY) and len(SOURCE_FILES) == 3,
        "source registry differs",
    )
    require(
        type(files) is dict and set(files) == {SCRIPT, TEST, POLICY},
        "exact successor source closure required",
    )


def attest(revision):
    revision, head = R.oid(revision), core.git_head(ROOT)
    core.require_ancestor(ROOT, DESIGN_REVISION, revision)
    core.require_ancestor(ROOT, revision, head)
    require(
        Path(__file__).resolve() == ROOT / SCRIPT, "successor source origin differs"
    )
    R.public._origin(P, PREPARER)
    files = {}
    for relative in SOURCE_FILES:
        item = R.snapshot_file(ROOT / relative)
        R.reviewed_file(item, revision)
        files[relative] = dict(byte_count=len(item.raw), sha256=sha(item.raw))
    closed_source(files)
    require(core.git_head(ROOT) == head, "HEAD changed during source inspection")
    return digested(
        dict(
            schema_version=DOMAIN + "/source",
            implementation_revision=revision,
            design_revision=DESIGN_REVISION,
            files=files,
        )
    )


def historical_sources():
    """Source-byte checks only; not runtime, baseline or numerical qualification."""
    preparer = P.attest(PREPARER_REVISION)
    coordinator = C.attest(P.COORDINATOR_REVISION)
    original = R.attest(B.ORIGINAL_SOURCE)
    require(
        coordinator["deterministic_digest"] == P.COORDINATOR_DIGEST,
        "historical coordinator source differs",
    )
    require(
        preparer["deterministic_digest"]
        == "cd7497f62f81fe7a5fc1a8b4a0a725bdbaf8b4754aee3d8328d447f8afcf12ee",
        "historical preparer source differs",
    )
    return dict(preparer=preparer, coordinator=coordinator, original=original)


class Evidence:
    """Process-local snapshots, not a detached proof, admission or input adapter."""

    def __init__(self):
        self.snapshots, self.archives, self.anchors, self.values = [], [], {}, {}

    def file(self, path, expected=None):
        item = R.snapshot_file(path)
        if expected is not None:
            require(item.raw == expected, "persisted reviewed bytes differ")
        self.snapshots.append(item)
        return item

    def anchor(self, relative, revision):
        require(
            (relative, revision) in ANCHORS and relative not in self.anchors,
            "fixed unique reviewed anchor required",
        )
        item = self.file(ROOT / relative)
        R.reviewed_file(item, revision)
        value = parse(item.raw)
        core.require_digest(value)
        self.values[relative] = value
        self.anchors[relative] = dict(
            reviewed_revision=revision,
            byte_count=len(item.raw),
            sha256=sha(item.raw),
            deterministic_digest=value["deterministic_digest"],
        )

    def archive(self, path, names):
        item = ReadOnlyArchive.capture(path, names)
        self.archives.append(item)
        return item

    def revalidate(self):
        for item in (*self.snapshots, *self.archives):
            item.revalidate()


def binding_for_mode(binding, mode, output, auth_path):
    binding = S.frozen_binding(binding)
    require(
        binding["execution_mode"] == mode
        and binding["experiment_id"] == S.mode_identity(mode),
        "persisted mode/study differs",
    )
    require(
        binding["authorization"]["output_path"] == str(output)
        and binding["authorization_path"] == str(auth_path),
        "fixed persisted output/authorization differs",
    )
    return binding


def persisted_claim(evidence, binding, mode, output, auth_path):
    """Read an exact existing claim; deliberately no perpetual absence invariant."""
    binding = binding_for_mode(binding, mode, output, auth_path)
    return evidence.file(
        S.claim_path(binding["authorization"]), canonical(binding["claim"])
    )


def authenticated_started(raw, commit, output):
    # This happens before parsing/following STARTED references, even on failure.
    require(
        sha(raw) == commit["started_sha256"],
        "STARTED hash differs before reference access",
    )
    value = parse(raw)
    core.require_digest(
        value,
        {
            "schema_version",
            "binding",
            "output_path",
            "directory_identities",
            "deterministic_digest",
        },
    )
    require(
        value["schema_version"] == S.DOMAIN + "/started"
        and value["output_path"] == str(output),
        "fixed STARTED schema/path differs",
    )
    return value


def historical_receiver_reference(values, sources):
    def ref(path):
        raw = canonical(values[path])
        return dict(path=str(ROOT / path), byte_count=len(raw), sha256=sha(raw))

    return dict(
        authorization=ref(B.CANDIDATE),
        certificate=ref(B.CERTIFICATE),
        bundle_commit=ref(B.BUNDLE_COMMIT),
        authorization_digest=C.BRIDGE_DIGEST,
        reviewed_revision=C.BRIDGE_REVIEWED,
        source_digest=sources["coordinator"]["receiver_source"]["deterministic_digest"],
    )


def public_linkage(label, binding, summary, receipt, commit, values, sources):
    output, _, _, auth_path, revision = PUBLIC_SPECS[label]
    binding_for_mode(binding, S.PUBLIC, output, auth_path)
    require(
        binding["reviewed_revision"] == binding["execution_head_revision"] == revision,
        "historical PUBLIC source/review differs",
    )
    auth = binding["authorization"]
    R.oid(revision)
    if label == "original_public":
        R.auth_shape(canonical(auth), S.PUBLIC, auth["deterministic_digest"])
    else:
        C.auth_shape(canonical(auth), S.PUBLIC, auth["deterministic_digest"])
        exact(auth, values[C.PUBLIC_AUTH], "v2 PUBLIC reviewed authorization differs")
        exact(
            auth["coordinator_source"],
            sources["coordinator"],
            "v2 PUBLIC source differs",
        )
        exact(
            auth["receiver_admission"],
            historical_receiver_reference(values, sources),
            "v2 historical receiver reference differs",
        )
        exact(
            summary["coordinator_source"],
            sources["coordinator"],
            "v2 summary source differs",
        )
        exact(
            summary["receiver_admission"],
            auth["receiver_admission"],
            "v2 summary receiver differs",
        )
    exact(auth["source"], sources["original"], "original source receipt differs")
    for key, expected in {
        "execution_mode": S.PUBLIC,
        "experiment_id": S.PUBLIC_ID,
        "output_path": str(output),
        "execution_commit_digest": commit["deterministic_digest"],
        "execution_receipt_digest": receipt["deterministic_digest"],
        "run_binding_digest": binding["deterministic_digest"],
        "authorization_digest": auth["deterministic_digest"],
        "input_manifest_digest": auth["input_manifest_digest"],
        "authorization_consumed": True,
        "replication_execution_authorized": False,
        "replication_cells_executed": 0,
        "task_count": 64,
        "source_multiset_count": 1,
        "scientific_decision": None,
        "locked_128_evaluation_authorized": False,
    }.items():
        exact(summary[key], expected, "saved PUBLIC summary linkage differs: " + key)


def inspect_public(evidence, label, sources):
    output, commit_path, summary_path, auth_path, _ = PUBLIC_SPECS[label]
    values = evidence.values
    commit, summary = values[commit_path], values[summary_path]
    archive = evidence.archive(output, S.NAMES)
    require(
        archive.raw["COMMIT.json"] == canonical(commit),
        "raw PUBLIC COMMIT differs from reviewed bytes",
    )
    started = authenticated_started(archive.raw["STARTED.json"], commit, output)
    binding = binding_for_mode(started["binding"], S.PUBLIC, output, auth_path)
    receipt = parse(archive.raw["RECEIPT.json"])
    public_linkage(label, binding, summary, receipt, commit, values, sources)
    # Only fixed, authenticated paths are accessed. No claim fsync inspector.
    evidence.file(auth_path, canonical(binding["authorization"]))
    persisted_claim(evidence, binding, S.PUBLIC, output, auth_path)
    evidence.file(Path(str(output) + ".summary.json"), canonical(summary))
    if label == "receiver_v2_public":
        evidence.file(C.RAW_AUTH, canonical(binding["authorization"]))
        expected = C.F._value(
            S,
            C.DOMAIN,
            C.PUBLIC_ATTEMPT,
            binding["authorization"],
            binding["reviewed_revision"],
            binding["execution_head_revision"],
        )
        fence = evidence.file(C.FENCE, canonical(expected))
        require(
            summary["public_attempt_fence_sha256"] == sha(fence.raw),
            "v2 PUBLIC fence/summary differs",
        )
    entries = []
    for index, name in enumerate(S.base.CELL_NAMES):
        raw = archive.raw[name]
        require(
            S.record_bytes(index, S.parse(raw, S.base.MAX_CELL_BYTES), binding) == raw,
            "saved cell schema differs",
        )
        entries.append(
            dict(cell_index=index, filename=name, byte_count=len(raw), sha256=sha(raw))
        )
    require(
        S.receipt_bytes(receipt, binding) == archive.raw["RECEIPT.json"],
        "saved receipt linkage differs",
    )
    exact(
        S.commit_value(
            binding, archive.raw["STARTED.json"], archive.raw["RECEIPT.json"], entries
        ),
        commit,
        "complete PUBLIC transaction closure differs",
    )
    values[str(output / "STARTED.json")] = started
    inventory = [
        dict(filename=name, byte_count=len(raw), sha256=sha(raw))
        for name, raw in sorted(archive.raw.items())
    ]
    return dict(
        label=label,
        closed_file_count=len(inventory),
        cell_count=len(entries),
        total_file_bytes=sum(row["byte_count"] for row in inventory),
        inventory_sha256=sha(canonical(inventory)),
        commit_digest=commit["deterministic_digest"],
        summary_digest=summary["deterministic_digest"],
        numerical_replay_performed=False,
    )


def scientific_projection(
    original, bridge, production, seal, reviewed_seal, original_summary
):
    """Whole saved scientific bytes, including rejection order; no regeneration."""
    exact(seal, reviewed_seal, "complete reviewed seal/scientific projection differs")
    # All original fields except the explicitly versioned envelope stay identical.
    excluded = {
        "schema_version",
        "deterministic_digest",
        "output_parent",
        "connector_qualification",
    }
    for candidate in (bridge, production):
        exact(
            {k: candidate[k] for k in original if k not in excluded},
            {k: v for k, v in original.items() if k not in excluded},
            "original scientific/environment fields differ",
        )
    projection = B.input_projection(seal)
    for key in ("contract_digest", "schedule_digest", "cohort_seal"):
        exact(projection[key], original[key], "original sealed input differs")
    require(
        projection["deterministic_digest"] == original["input_manifest_digest"],
        "sealed input manifest differs",
    )
    reference = dict(
        summary_path=str(ROOT / B.PUBLIC_SUMMARY),
        summary_sha256=sha(canonical(original_summary)),
        summary_digest=original_summary["deterministic_digest"],
        output_path=str(B.PUBLIC_OUTPUT),
        commit_digest=original_summary["execution_commit_digest"],
        source_digest=original["source"]["deterministic_digest"],
    )
    exact(
        seal["generation_qualification"],
        reference,
        "original generation qualification differs",
    )
    return dict(
        seal_digest=seal["deterministic_digest"],
        input_manifest_digest=projection["deterministic_digest"],
        schedule_digest=seal["schedule_digest"],
        task_count=64,
        source_multiset_count=64,
        cell_count=1024,
        acceptance_order_reconstructed=False,
    )


def inspect_metadata(evidence, sources):
    values = evidence.values
    original = R.auth_shape(
        canonical(values[B.ORIGINAL_CANDIDATE]), S.REPLICATION, B.ORIGINAL_DIGEST
    )
    certificate = B.certificate_shape(canonical(values[B.CERTIFICATE]))
    bridge = B.auth_shape(canonical(values[B.CANDIDATE]), C.BRIDGE_DIGEST)
    production = P.candidate_shape(canonical(values[C.REPLICATION_AUTH]))
    require(
        production["deterministic_digest"] == CANDIDATE_DIGEST
        and sha(canonical(production)) == CANDIDATE_SHA,
        "fixed v2 candidate differs",
    )
    exact(
        certificate["source"],
        sources["coordinator"]["receiver_source"],
        "historical certificate source differs",
    )
    exact(
        bridge,
        B.candidate_projection(original, certificate),
        "historical bridge candidate projection differs",
    )
    exact(
        values[B.BUNDLE_COMMIT],
        B.bundle_commit(canonical(certificate), canonical(bridge)),
        "historical bridge COMMIT differs",
    )
    bundle = evidence.archive(B.BUNDLE, B.BUNDLE_NAMES)
    require(
        dict(bundle.raw)
        == {
            "certificate.json": canonical(certificate),
            "authorization.json": canonical(bridge),
            "COMMIT.json": canonical(values[B.BUNDLE_COMMIT]),
        },
        "raw bridge bundle differs from reviewed bytes",
    )
    evidence.file(B.ORIGINAL_RAW, canonical(original))
    evidence.file(P.RAW_AUTH, canonical(production))
    exact(
        production["coordinator_source"],
        sources["coordinator"],
        "production historical source differs",
    )
    exact(
        production["receiver_admission"],
        historical_receiver_reference(values, sources),
        "production historical receiver differs",
    )
    preparation, verification = values[P.PREPARATION_MIRROR], values[VERIFICATION]
    exact(
        preparation,
        P.preparation_receipt(production, sources["preparer"]),
        "historical preparation metadata differs",
    )
    exact(
        verification["operator_source"],
        sources["preparer"],
        "historical admission operator differs",
    )
    require(
        verification["authorization_digest"] == CANDIDATE_DIGEST
        and verification["authorization_sha256"] == CANDIDATE_SHA
        and verification["preparation_digest"] == preparation["deterministic_digest"],
        "historical candidate verification linkage differs",
    )
    saved = values[C.SUMMARY_MIRROR]
    qualifier = dict(
        summary_path=str(ROOT / C.SUMMARY_MIRROR),
        summary_sha256=sha(canonical(saved)),
        summary_digest=saved["deterministic_digest"],
        output_path=str(C.PUBLIC_OUTPUT),
        commit_digest=saved["execution_commit_digest"],
        source_digest=sources["coordinator"]["deterministic_digest"],
    )
    exact(
        production["connector_qualification"],
        qualifier,
        "v2 candidate PUBLIC reference differs",
    )
    public_verification = values[P.PUBLIC_VERIFICATION]
    require(
        public_verification["status"] == "PUBLIC_SUMMARY_INDEPENDENTLY_VERIFIED"
        and public_verification["summary_digest"] == saved["deterministic_digest"]
        and public_verification["replication_execution_authorized"] is False
        and public_verification["scientific_decision"] is None,
        "historical PUBLIC verification differs",
    )
    cohort = evidence.archive(B.M.COHORT_PATH, B.M.NAMES)
    for name in B.M.NAMES:
        require(
            cohort.raw[name] == canonical(values[B.SEAL_MIRROR + "/" + name]),
            "complete sealed bytes differ",
        )
    seal, start = (
        parse(cohort.raw["preregistration.json"]),
        parse(cohort.raw["STARTED.json"]),
    )
    require(
        canonical(
            B.M._started(
                seal["admission_context"],
                start["owner_nonce"],
                seal["generation_qualification"],
            )
        )
        == cohort.raw["STARTED.json"]
        and canonical(B.M._closed(start, seal)) == cohort.raw["SEALED.json"],
        "sealed transaction closure differs",
    )
    return scientific_projection(
        original,
        bridge,
        production,
        seal,
        values[B.SEAL_MIRROR + "/preregistration.json"],
        values[B.PUBLIC_SUMMARY],
    )


def claim_ceiling():
    return dict(
        reconstruction_status="NOT_IMPLEMENTED",
        execution_qualification="NOT_QUALIFIED_FOR_EXECUTION",
        numerical_replay_performed=False,
        environment_requalified=False,
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


def inspection_receipt(source, historical, head, anchors, mapping, archives, cohort):
    return digested(
        dict(
            schema_version=DOMAIN + "/inspection",
            status=STATUS,
            source=source,
            historical_source_receipts=historical,
            inspection_head=head,
            reviewed_anchors=anchors,
            location_correspondence=mapping,
            public_archive_hash_closures=archives,
            sealed_metadata=cohort,
            original_study_identity=S.REPLICATION_ID,
            fixed_replication_claim_path=str(B.fixed_claim()),
            original_study_slot_absent_at_inspection=True,
            claim_ceiling=claim_ceiling(),
            claim_boundary=CLAIM_BOUNDARY,
        )
    )


def inspection_shape(raw):
    """Closed inspection schema only; accepting bytes here is NEVER provenance."""
    value = parse(raw)
    core.require_digest(
        value,
        {
            "schema_version",
            "status",
            "source",
            "historical_source_receipts",
            "inspection_head",
            "reviewed_anchors",
            "location_correspondence",
            "public_archive_hash_closures",
            "sealed_metadata",
            "original_study_identity",
            "fixed_replication_claim_path",
            "original_study_slot_absent_at_inspection",
            "claim_ceiling",
            "claim_boundary",
            "deterministic_digest",
        },
    )
    require(
        value["schema_version"] == DOMAIN + "/inspection" and value["status"] == STATUS,
        "inspection-only schema/status required",
    )
    exact(
        value["claim_ceiling"],
        claim_ceiling(),
        "inspection cannot assert reconstruction or authority",
    )
    require(
        value["original_study_identity"] == S.REPLICATION_ID
        and value["fixed_replication_claim_path"] == str(B.fixed_claim())
        and value["original_study_slot_absent_at_inspection"] is True,
        "fixed pre-consumption inspection required",
    )
    require(
        value["claim_boundary"] == CLAIM_BOUNDARY, "inspection claim boundary differs"
    )
    require(
        type(value["inspection_head"]) is str
        and re.fullmatch(r"[0-9a-f]{40}", value["inspection_head"]) is not None,
        "full inspection HEAD required",
    )
    source = value["source"]
    core.require_digest(
        source,
        {
            "schema_version",
            "implementation_revision",
            "design_revision",
            "files",
            "deterministic_digest",
        },
    )
    require(
        source["schema_version"] == DOMAIN + "/source"
        and source["design_revision"] == DESIGN_REVISION
        and type(source["implementation_revision"]) is str
        and re.fullmatch(r"[0-9a-f]{40}", source["implementation_revision"])
        is not None,
        "successor source schema differs",
    )
    closed_source(source["files"])
    for item in source["files"].values():
        require(
            type(item) is dict
            and set(item) == {"byte_count", "sha256"}
            and type(item["byte_count"]) is int
            and item["byte_count"] > 0,
            "closed source byte reference required",
        )
        core.require_sha256(item["sha256"])
    historical = value["historical_source_receipts"]
    require(
        type(historical) is dict
        and set(historical) == {"preparer", "coordinator", "original"},
        "historical source receipt closure differs",
    )
    for item in historical.values():
        core.require_digest(item)
    require(
        set(value["reviewed_anchors"]) == {p for p, _ in ANCHORS},
        "receipt anchor closure differs",
    )
    for path, revision in ANCHORS:
        anchor = value["reviewed_anchors"][path]
        require(
            type(anchor) is dict
            and set(anchor)
            == {"reviewed_revision", "byte_count", "sha256", "deterministic_digest"}
            and anchor["reviewed_revision"] == revision
            and type(anchor["byte_count"]) is int
            and anchor["byte_count"] > 0,
            "closed anchor reference differs",
        )
        for key in ("sha256", "deterministic_digest"):
            core.require_sha256(anchor[key])
    mapping = value["location_correspondence"]
    exact(
        mapping,
        correspondence(mapping["chains"], mapping["current_locations"]),
        "inspection correspondence fields differ",
    )
    rows = value["public_archive_hash_closures"]
    require(
        type(rows) is list and [r["label"] for r in rows] == list(PUBLIC_SPECS),
        "fixed PUBLIC archive order required",
    )
    for row in rows:
        require(
            set(row)
            == {
                "label",
                "closed_file_count",
                "cell_count",
                "total_file_bytes",
                "inventory_sha256",
                "commit_digest",
                "summary_digest",
                "numerical_replay_performed",
            },
            "closed archive observation required",
        )
        exact(
            [
                row["closed_file_count"],
                row["cell_count"],
                row["numerical_replay_performed"],
            ],
            [1027, 1024, False],
            "hash closure is not replay",
        )
        require(
            type(row["total_file_bytes"]) is int and row["total_file_bytes"] > 0,
            "plain archive byte count required",
        )
        for key in ("inventory_sha256", "commit_digest", "summary_digest"):
            core.require_sha256(row[key])
    sealed = value["sealed_metadata"]
    require(
        type(sealed) is dict
        and set(sealed)
        == {
            "seal_digest",
            "input_manifest_digest",
            "schedule_digest",
            "task_count",
            "source_multiset_count",
            "cell_count",
            "acceptance_order_reconstructed",
        },
        "closed sealed observation required",
    )
    for key in ("seal_digest", "input_manifest_digest", "schedule_digest"):
        core.require_sha256(sealed[key])
    exact(
        [sealed["task_count"], sealed["source_multiset_count"], sealed["cell_count"]],
        [64, 64, 1024],
        "sealed metadata count differs",
    )
    require(
        sealed["acceptance_order_reconstructed"] is False,
        "acceptance reconstruction is not implemented",
    )
    return value


def revalidate(evidence, source, historical, head, locations):
    _guard()
    require(core.git_head(ROOT) == head, "inspection HEAD changed")
    evidence.revalidate()
    exact(current_locations(), locations, "current receiver identity changed")
    exact(attest(source["implementation_revision"]), source, "successor source changed")
    exact(historical_sources(), historical, "historical source changed")
    # The source checks can take time. Re-read the immutable evidence afterwards
    # too, so an archive change during attestation cannot escape the final gate.
    evidence.revalidate()
    exact(current_locations(), locations, "current receiver identity changed")
    require(core.git_head(ROOT) == head, "inspection HEAD changed")
    C.unused(S.REPLICATION)  # D1 inspection only; NOT used for persisted analysis.


def inspect(revision):
    """Sole actual-operation entry: no caller proof, callbacks, paths or adapters."""
    _guard()
    C.unused(S.REPLICATION)
    head = core.git_head(ROOT)
    source = attest(revision)
    historical = historical_sources()
    evidence = Evidence()
    for relative, reviewed in ANCHORS:
        core.require_ancestor(ROOT, reviewed, head)
        evidence.anchor(relative, reviewed)
    require(set(evidence.anchors) == {p for p, _ in ANCHORS}, "anchor closure differs")
    cohort = inspect_metadata(evidence, historical)
    archives = [inspect_public(evidence, label, historical) for label in PUBLIC_SPECS]
    locations = current_locations()
    mapping = correspondence(recorded_chains(evidence.values), locations)
    revalidate(evidence, source, historical, head, locations)
    result = inspection_receipt(
        source, historical, head, evidence.anchors, mapping, archives, cohort
    )
    return inspection_shape(canonical(result))


def failure_receipt(error):
    # Existing external effects cannot be inferred absent from an inspection error.
    consumed = (
        error.authorization_consumed if isinstance(error, S.ExecutionFailure) else None
    )
    return digested(
        dict(
            schema_version=DOMAIN + "/failure",
            status="INSPECTION_REJECTED",
            reason=str(error),
            authorization_consumed=consumed,
            execution_dispatch_entered=False,
            new_effects_attempted=False,
            retain_evidence=True,
            automatic_retry_allowed=False,
            claim_ceiling=claim_ceiling(),
        )
    )


def self_test():
    closed_source({name: {} for name in SOURCE_FILES})
    require(
        len(REGISTRY) == 11 and len(LOCATIONS) == 6 and len(ANCHORS) == 16,
        "closed registry count differs",
    )
    return digested(
        dict(
            schema_version=DOMAIN + "/self-test",
            status="STATIC_SELF_TEST_ONLY",
            claim_ceiling=claim_ceiling(),
        )
    )


def _guard():
    # Detect accidental caller substitution of consumed dependencies. This is not
    # a sandbox against arbitrary code in this interpreter. Actual use is a fresh
    # source-qualified process; no callback/injected-admission interface exists.
    for module, name, expected in _READ_BINDINGS:
        require(
            getattr(module, name) is expected,
            "read-only dependency substituted: " + name,
        )


_READ_BINDINGS = tuple(
    (module, name, getattr(module, name))
    for module, names in (
        (P, ("attest", "candidate_shape", "preparation_receipt")),
        (C, ("attest", "unused", "auth_shape")),
        (
            B,
            (
                "directory_binding",
                "input_projection",
                "certificate_shape",
                "auth_shape",
                "candidate_projection",
                "bundle_commit",
            ),
        ),
        (R, ("oid", "snapshot_file", "reviewed_file", "auth_shape", "attest")),
        (
            S,
            (
                "frozen_binding",
                "record_bytes",
                "receipt_bytes",
                "commit_value",
                "claim_path",
            ),
        ),
    )
    for name in names
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--inspect", action="store_true")
    parser.add_argument("--implementation-revision")
    args = parser.parse_args()
    if args.self_test:
        if args.implementation_revision is not None:
            parser.error("self-test takes no implementation revision")
        result = self_test()
    else:
        if args.implementation_revision is None:
            parser.error("inspection requires a full immutable implementation revision")
        try:
            result = inspect(args.implementation_revision)
            sys.stdout.buffer.write(canonical(result))
            sys.stdout.buffer.flush()
        except (Exception, KeyboardInterrupt) as error:
            sys.stderr.buffer.write(canonical(failure_receipt(error)))
            raise SystemExit(1) from error
        return
    sys.stdout.buffer.write(canonical(result))


if __name__ == "__main__":
    main()
