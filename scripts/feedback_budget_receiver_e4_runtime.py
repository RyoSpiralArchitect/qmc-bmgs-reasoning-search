"""Non-authorizing E4 history capture for the separate execution coordinator.

This layer owns source, issued bytes, current identity and genuine reconstruction.
It never asserts that a study slot is unused or consumed. The coordinator owns
that separate, mode-specific lifecycle; no skip-unused switch is provided.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import os
from pathlib import Path
import stat
import sys
from types import MappingProxyType
from weakref import WeakKeyDictionary


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = "scripts/feedback_budget_receiver_e4_runtime.py"
COORDINATOR = "scripts/feedback_budget_receiver_e4_execution.py"
SOURCE_FILES = (
    SCRIPT,
    COORDINATOR,
    "tests/test_feedback_budget_receiver_e4_runtime.py",
    "tests/test_feedback_budget_receiver_e4_execution.py",
    "docs/strategy/countdown_feedback_budget_receiver_e4_execution.md",
)
PUBLISHER = "scripts/feedback_budget_receiver_e4_publisher.py"
PUBLISHER_REVISION = "abf04523809a440b760886b48d2aa681749825e5"
PUBLISHER_DIGEST = "38a104e89256216c1df8184877ef89e4e457f2c22fb21b5bff0df4d5c757da0c"
ISSUED_REVIEW = "d41a49fb6eafe30005718d27b9fa4b926dce1cce"
PREFIX = (
    "docs/qualifications/countdown_feedback_budget_receiver_e4_certificate_20261010."
)
OPERATIONS = "docs/qualifications/countdown_feedback_budget_receiver_e4_issuance_20261015.operations.json"
PINS = MappingProxyType(
    {
        PREFIX + "certificate.json": (
            226656,
            "129c3baa318eebb6eb88a6b124e84d681d1bd7f6b43596bc179908277e887c79",
        ),
        PREFIX + "verification.json": (
            18494,
            "e9db116a27e40019deb9ba6351d4f6c85312253ebaa3bb19e45f1ba60f5233d5",
        ),
        PREFIX + "commit.json": (
            11561,
            "5452dd5bbc315e1af4d0ab356212516e099c7e70c2563d269cc7640deedcdd32",
        ),
        OPERATIONS: (
            47708,
            "447ed727d89b2339b0958a03caacf8fa68cd298dc4fab8d9109641f68108dbb0",
        ),
    }
)
spec = importlib.util.spec_from_file_location(
    "e4_execution_frozen_publisher", ROOT / PUBLISHER
)
assert spec is not None and spec.loader is not None
P = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = P
spec.loader.exec_module(P)
K, N, V, C, R, S, core = P.K, P.N, P.V, P.C, P.R, P.S, P.core
B, M = K.B, S.mechanics
canonical, parse, require, digested, sha, exact = (
    P.canonical,
    P.parse,
    P.require,
    P.digested,
    P.sha,
    P.exact,
)
DOMAIN = S.DOMAIN + "/receiver-e4-coordinator/v1"


def configuration():
    return dict(
        root=str(ROOT),
        script=SCRIPT,
        coordinator=COORDINATOR,
        source_files=list(SOURCE_FILES),
        publisher=PUBLISHER,
        publisher_revision=PUBLISHER_REVISION,
        publisher_digest=PUBLISHER_DIGEST,
        issued_review=ISSUED_REVIEW,
        pins=dict(PINS),
        prefix=PREFIX,
        operations=OPERATIONS,
        domain=DOMAIN,
        issued_bundle=str(P.BUNDLE),
        issued_names=list(P.NAMES),
    )


_CONFIGURATION_RAW = canonical(configuration())


def attest(revision):
    revision, head = R.oid(revision), core.git_head(ROOT)
    core.require_ancestor(ROOT, ISSUED_REVIEW, revision)
    core.require_ancestor(ROOT, revision, head)
    require(Path(__file__).resolve() == ROOT / SCRIPT, "E4 runtime origin differs")
    R.public._origin(P, PUBLISHER)
    publisher = P.attest(PUBLISHER_REVISION)
    require(
        publisher["deterministic_digest"] == PUBLISHER_DIGEST,
        "frozen publisher differs",
    )
    items = [R.snapshot_file(ROOT / name) for name in SOURCE_FILES]
    require(len(set(SOURCE_FILES)) == 5, "closed five-file coordinator source required")
    files = {}
    for name, item in zip(SOURCE_FILES, items, strict=True):
        R.reviewed_file(item, revision)
        files[name] = dict(byte_count=len(item.raw), sha256=sha(item.raw))
    for item in items:
        item.revalidate()
    require(head == core.git_head(ROOT), "coordinator source HEAD changed")
    return digested(
        dict(
            schema_version=DOMAIN + "/source",
            implementation_revision=revision,
            issued_review_revision=ISSUED_REVIEW,
            publisher_source=publisher,
            files=files,
        )
    )


def clean(head):
    require(core.git_head(ROOT) == head, "E4 coordinator operation HEAD changed")
    require(
        not core.git_bytes(ROOT, "status", "--porcelain", "--untracked-files=all"),
        "E4 coordinator source checkout must remain clean",
    )


def issued(evidence, source, locations):
    """Authenticate all fixed reviewed bytes BEFORE parsing/dereferencing them."""
    items = {}
    for name, (size, checksum) in PINS.items():
        item = evidence.file(ROOT / name)
        R.reviewed_file(item, ISSUED_REVIEW)
        require(
            (len(item.raw), sha(item.raw)) == (size, checksum),
            "issued review pin differs: " + name,
        )
        items[name] = item
    values = {name: parse(item.raw) for name, item in items.items()}
    for name, value in values.items():
        core.require_digest(value)
        require(canonical(value) == items[name].raw, "issued canonical bytes differ")
    certificate, verification, commit = (
        values[PREFIX + suffix]
        for suffix in ("certificate.json", "verification.json", "commit.json")
    )
    operation = values[OPERATIONS]["issuance_operation"]
    exact(
        operation["publisher_source"],
        source["publisher_source"],
        "issued publisher source differs",
    )
    require(
        operation["certificate_issued"] is True
        and operation["execution_dispatch_entered"] is False,
        "certificate-only completed publication required",
    )
    exact(operation["claim_ceiling"], K.ceiling(), "issued authority ceiling differs")
    raw = evidence.archive(P.BUNDLE, P.NAMES)
    expected = {
        name: items[PREFIX + suffix].raw
        for name, suffix in zip(
            P.NAMES,
            ("certificate.json", "verification.json", "commit.json"),
            strict=True,
        )
    }
    require(
        dict(raw.raw) == expected, "raw issued bundle differs from reviewed mirrors"
    )
    for name, field in zip(
        P.NAMES, ("certificate", "verification", "commit"), strict=True
    ):
        item = evidence.file(P.BUNDLE / name, raw.raw[name])
        require(
            stat.S_IMODE(item.generation[2]) == 0o600
            and item.generation[4] == os.geteuid(),
            "issued payload must remain private and owned",
        )
        exact(
            N.reference(raw.raw[name]),
            operation[field],
            "issued payload binding differs",
        )
    exact(
        commit["payloads"],
        {name: N.reference(raw.raw[name]) for name in P.NAMES[:2]},
        "issued COMMIT payload closure differs",
    )
    exact(
        verification["publisher_source"],
        source["publisher_source"],
        "issued verifier source differs",
    )
    exact(
        certificate["receiver_identity"]["persistent_locations"],
        locations["persistent_locations"],
        "issued receiver persistent identity differs",
    )
    parent = M._PinnedParent.open(P.BUNDLE)
    try:
        persistent = locations["persistent_locations"]["output_parent"][
            "components"
        ] + [
            dict(
                volume_uuid=K._volume_uuid(parent.descriptor),
                inode=parent.component_identities[-1][1],
            )
        ]
        exact(
            dict(path=str(P.BUNDLE), persistent_components=persistent),
            {
                key: commit["bundle_location"][key]
                for key in ("path", "persistent_components")
            },
            "issued bundle persistent location differs",
        )
        parent.assert_path()
    finally:
        parent.close()
    old = K.historical(
        evidence, source["publisher_source"]["certifier"]["frozen_reconstruction"]
    )
    K._compare_certificate(
        raw.raw["certificate.json"],
        K._projection(
            old,
            source["publisher_source"]["certifier"],
            dict(original_public=False, receiver_v2_public=False),
        ),
    )
    return old, raw.raw["certificate.json"]


@dataclass
class _HistoryState:
    source: dict
    head: str
    locations: dict
    evidence: object
    old: dict
    prior: dict
    historical: dict
    cohort: dict
    archives: list
    mapping: dict
    certificate_raw: bytes
    work: dict
    environment: object = None
    public_inputs: object = None
    sealed_inputs: object = None
    complete: bool = False
    attempted: bool = False


class History:
    __slots__ = ("__weakref__",)

    def __new__(cls, *args, **kwargs):
        raise TypeError("history is created only by fixed issued evidence capture")

    def revalidate(self):
        state = _state(self)
        guard()
        clean(state.head)
        exact(
            attest(state.source["implementation_revision"]),
            state.source,
            "E4 coordinator source changed",
        )
        state.evidence.revalidate()
        exact(K._capture_locations(), state.locations, "live receiver identity changed")
        exact(V.historical_sources(), state.historical, "historical source changed")
        if state.environment is not None:
            R.check_environment(state.environment)
        if state.public_inputs is not None:
            require(
                type(state.public_inputs) is R.Inputs, "genuine PUBLIC inputs required"
            )
            state.public_inputs.revalidate()
        state.evidence.revalidate()
        exact(
            attest(state.source["implementation_revision"]),
            state.source,
            "source changed during live check",
        )
        exact(
            K._capture_locations(),
            state.locations,
            "receiver changed during live check",
        )
        clean(state.head)
        guard()

    @property
    def source(self):
        return parse(canonical(_state(self).source))

    @property
    def head(self):
        return _state(self).head

    @property
    def environment(self):
        state = _state(self)
        require(state.complete, "complete genuine reconstruction required")
        return parse(canonical(state.environment))

    @property
    def work(self):
        return parse(canonical(_state(self).work))

    @property
    def reference(self):
        return dict(
            reviewed_revision=ISSUED_REVIEW,
            certificate_path=PREFIX + "certificate.json",
            **N.reference(_state(self).certificate_raw),
        )

    def inputs(self, mode):
        S.mode_identity(mode)
        state = _state(self)
        require(state.complete, "complete genuine reconstruction required")
        return state.public_inputs if mode == S.PUBLIC else state.sealed_inputs

    def historical_claims(self):
        state = _state(self)
        result = {
            item.path: item
            for item in state.evidence.snapshots
            if item.path.parent == S.LEDGER
        }
        require(
            len(result) == 3, "exact three original historical ledger rows required"
        )
        return result


_HISTORIES = WeakKeyDictionary()


def _state(history):
    require(
        type(history) is History and history in _HISTORIES,
        "registered non-authorizing history required",
    )
    return _HISTORIES[history]


class SealedInputs:
    """New adapter for genuinely reproduced original bytes; never an old Inputs forgery."""

    __slots__ = ("__weakref__",)

    def __new__(cls, *args, **kwargs):
        raise TypeError("sealed inputs require completed original reconstruction")

    def _value(self):
        require(
            type(self) is SealedInputs and self in _SEALED,
            "registered sealed input adapter required",
        )
        return parse(_SEALED[self])

    @property
    def manifest(self):
        return self._value()

    @property
    def cells(self):
        return self._value()["cells"]

    def arguments(self, cell):
        value = self._value()
        require(
            type(cell) is dict and type(cell.get("cell_index")) is int,
            "plain cell index required",
        )
        index = cell["cell_index"]
        require(0 <= index < 1024, "sealed cell index outside fixed matrix")
        exact(cell, value["cells"][index], "complete sealed cell differs")
        key = cell["cell_key"]
        task = value["tasks"][key["task_slot"]]
        return dict(
            task=R.q.CountdownTask(tuple(task["inputs"]), task["target"]),
            proposal=R.q.PROPOSAL,
            method=R.q.method(key["scale"]),
            budget_profile=R.q.profile(key["budget"]),
            exploration_seed=key["seed"],
        )


_SEALED = WeakKeyDictionary()


def open_history(revision):
    """Read-only metadata, no baseline/replay/generation and no admission."""
    guard()
    head = core.git_head(ROOT)
    clean(head)
    source, locations, evidence = attest(revision), K._capture_locations(), V.Evidence()
    old, raw = issued(evidence, source, locations)
    historical_locations = K._historical_locations(old, locations)
    prior, historical, cohort, archives, mapping = N.inspect_metadata(
        evidence,
        source["publisher_source"]["certifier"]["frozen_reconstruction"],
        head,
        historical_locations,
    )
    value = object.__new__(History)
    _HISTORIES[value] = _HistoryState(
        source,
        head,
        locations,
        evidence,
        old,
        prior,
        historical,
        cohort,
        archives,
        mapping,
        raw,
        N.initial_work(),
    )
    value.revalidate()
    return value


def reconstruct(history):
    """Real full computation, once per capture; no supplied proof or callback."""
    state = _state(history)
    require(not state.attempted, "no reconstruction retry or resume")
    state.attempted = True
    history.revalidate()
    state.work["baseline_traces_completed"] = None
    N.progress("e4_coordinator_genuine_environment", state.work)
    environment = R.environment(B.ORIGINAL_SOURCE)
    state.work["baseline_traces_completed"] = 32
    K.E.compare_environment(environment, state.evidence.values[B.ORIGINAL_CANDIDATE])
    exact(environment, state.prior["environment"], "fresh environment differs from E3")
    exact(environment, state.old["environment"], "fresh environment differs from E4")
    state.environment = environment
    history.revalidate()
    state.public_inputs = R.load_inputs(S.PUBLIC)
    require(type(state.public_inputs) is R.Inputs, "genuine PUBLIC loader required")
    replays = []
    for label in N.LABELS:
        history.revalidate()
        replays.append(
            N.replay_one(
                label,
                state.evidence,
                state.public_inputs,
                environment,
                state.historical,
                state.work,
            )
        )
        history.revalidate()
    sealed = N.reconstruct_seal(
        state.evidence,
        environment,
        replays[0]["original_generation_reference"],
        state.work,
    )
    fresh = dict(
        source=state.source["publisher_source"]["certifier"]["frozen_reconstruction"],
        prior_public_observation=dict(N.PRIOR_REFERENCE),
        historical_source_receipts=state.historical,
        reviewed_anchors=state.evidence.anchors,
        location_correspondence=state.mapping,
        public_archive_hash_closures=state.archives,
        sealed_metadata=state.cohort,
        environment=environment,
        work=state.work,
        public_replays=replays,
        public_traces_replayed=2048,
        budget_prefix_comparisons=1024,
        original_sealed_reconstruction=sealed,
        acceptance_order_reconstructed=True,
        original_study_identity=S.REPLICATION_ID,
        fixed_replication_claim_path=str(B.fixed_claim()),
    )
    require(set(fresh) == set(K.FRESH_KEYS), "whole fresh evidence registry differs")
    for key in K.FRESH_KEYS:
        exact(fresh[key], state.old[key], "fresh full evidence differs: " + key)
    screens = {
        label: state.evidence.values[V.PUBLIC_SPECS[label][2]]["reduction"][
            "exact_success"
        ]["screen_conjunction"]
        for label in N.LABELS
    }
    K._compare_certificate(
        state.certificate_raw,
        K._projection(fresh, state.source["publisher_source"]["certifier"], screens),
    )
    projection = B.input_projection(
        parse(N.cohort_archive(state.evidence).raw["preregistration.json"])
    )
    exact(
        N.reference(canonical(projection)),
        sealed["input_projection"],
        "complete reconstructed input adapter differs",
    )
    history.revalidate()
    adapter = object.__new__(SealedInputs)
    _SEALED[adapter] = canonical(projection)
    state.sealed_inputs, state.complete = adapter, True
    return history


def guard():
    P._guard()
    require(
        canonical(configuration()) == _CONFIGURATION_RAW,
        "E4 runtime fixed configuration changed",
    )
    for module, name, original in _DEPENDENCIES:
        require(
            getattr(module, name) is original,
            "E4 runtime dependency substituted: " + name,
        )


_DEPENDENCIES = tuple(
    (module, name, getattr(module, name))
    for module, names in (
        (
            sys.modules[__name__],
            (
                "configuration",
                "attest",
                "clean",
                "issued",
                "open_history",
                "reconstruct",
                "_state",
                "History",
                "SealedInputs",
            ),
        ),
        (
            History,
            (
                "__new__",
                "revalidate",
                "inputs",
                "historical_claims",
                "source",
                "head",
                "environment",
                "work",
                "reference",
            ),
        ),
        (SealedInputs, ("__new__", "_value", "arguments", "manifest", "cells")),
        (V, ("ReadOnlyArchive", "Evidence", "historical_sources")),
        (V.Evidence, ("file", "archive", "anchor", "revalidate")),
        (V.ReadOnlyArchive, ("revalidate",)),
        (R, ("record", "reduce_rows", "replay")),
    )
    for name in names
)
