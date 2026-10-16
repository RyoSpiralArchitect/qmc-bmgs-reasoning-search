#!/usr/bin/env python3
"""Fixed E4 PUBLIC qualification and closed shared replication adapter.

Implementation approval is not candidate publication, PUBLIC execution or
production consent. No production CLI, path override, retry or resume exists.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = "scripts/feedback_budget_receiver_e4_execution.py"
RUNTIME = "scripts/feedback_budget_receiver_e4_runtime.py"
spec = importlib.util.spec_from_file_location("e4_coordinator_runtime", ROOT / RUNTIME)
assert spec is not None and spec.loader is not None
G = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = G
spec.loader.exec_module(G)
R, S, B, C, core, F = G.R, G.S, G.B, G.C, G.core, G.C.F
canonical, parse, require, digested, sha, exact = (
    G.canonical,
    G.parse,
    G.require,
    G.digested,
    G.sha,
    G.exact,
)
DOMAIN = G.DOMAIN
PUBLIC_ATTEMPT = "receiver_e4_public_full_path_20261015_a/v1"
PUBLIC_OUTPUT = ROOT / "artifacts/work/feedback-budget-receiver-e4-public-20261015-a"
RAW_AUTH = Path(str(PUBLIC_OUTPUT) + ".authorization.json")
PUBLIC_SUMMARY = Path(str(PUBLIC_OUTPUT) + ".summary.json")
PUBLIC_AUTH = "docs/qualifications/countdown_feedback_budget_receiver_e4_public_20261015.authorization.json"
SUMMARY_MIRROR = "docs/qualifications/countdown_feedback_budget_receiver_e4_public_20261015.summary.json"
COMMIT_MIRROR = "docs/qualifications/countdown_feedback_budget_receiver_e4_public_20261015.commit.json"
REPLICATION_AUTH = (
    "docs/preregistrations/countdown_feedback_budget_receiver_e4.authorization.json"
)
RAW_REPLICATION_AUTH = (
    ROOT / "artifacts/work/feedback-budget-receiver-e4.authorization.json"
)
ORIGINAL_PREFLIGHT = (
    ROOT
    / "docs/qualifications/countdown_feedback_budget_receiver_v2_entrypoint_20261001.preflight.json"
)
FENCE = S.LEDGER / ("receiver-public-" + S.digest([DOMAIN, PUBLIC_ATTEMPT]) + ".json")
AUTH_FIELDS = R.AUTH_FIELDS | {
    "coordinator_source",
    "receiver_certificate",
    "attempt_id",
}
_STARTED = False
_CURRENT = None


def configuration():
    return dict(
        root=str(ROOT),
        script=SCRIPT,
        runtime=RUNTIME,
        domain=DOMAIN,
        public_attempt=PUBLIC_ATTEMPT,
        public_output=str(PUBLIC_OUTPUT),
        raw_auth=str(RAW_AUTH),
        public_summary=str(PUBLIC_SUMMARY),
        public_auth=PUBLIC_AUTH,
        summary_mirror=SUMMARY_MIRROR,
        commit_mirror=COMMIT_MIRROR,
        replication_auth=REPLICATION_AUTH,
        raw_replication_auth=str(RAW_REPLICATION_AUTH),
        original_preflight=str(ORIGINAL_PREFLIGHT),
        fence=str(FENCE),
        ledger=str(S.LEDGER),
        original_output=str(B.OUTPUT),
        original_summary=str(C.REPLICATION_SUMMARY),
        auth_fields=sorted(AUTH_FIELDS),
    )


_CONFIGURATION_RAW = canonical(configuration())


def output_for(mode):
    S.mode_identity(mode)
    return PUBLIC_OUTPUT if mode == S.PUBLIC else B.OUTPUT


def authorization_for(mode):
    S.mode_identity(mode)
    return ROOT / (PUBLIC_AUTH if mode == S.PUBLIC else REPLICATION_AUTH)


def raw_authorization_for(mode):
    S.mode_identity(mode)
    return RAW_AUTH if mode == S.PUBLIC else RAW_REPLICATION_AUTH


def summary_for(mode):
    S.mode_identity(mode)
    return PUBLIC_SUMMARY if mode == S.PUBLIC else C.REPLICATION_SUMMARY


def attempt_for(mode):
    S.mode_identity(mode)
    return PUBLIC_ATTEMPT if mode == S.PUBLIC else S.REPLICATION_ID


def original_unused():
    C.unused(S.REPLICATION)
    require(
        not os.path.lexists(ORIGINAL_PREFLIGHT), "old original entrypoint slot occupied"
    )


def public_unused():
    F.ensure_unused(S, FENCE)
    for path in (PUBLIC_OUTPUT, PUBLIC_SUMMARY):
        require(not os.path.lexists(path), "fixed E4 PUBLIC slot occupied; no retry")


def auth_shape(raw, mode, confirmed):
    S.mode_identity(mode)
    value = parse(raw)
    core.require_digest(value)
    require(canonical(value) == raw, "canonical E4 candidate required")
    suffix = (
        "/public-authorization-candidate"
        if mode == S.PUBLIC
        else "/replication-authorization-candidate"
    )
    require(
        type(value) is dict
        and set(value) == AUTH_FIELDS
        and value["schema_version"] == DOMAIN + suffix,
        "closed E4 candidate required",
    )
    require(
        type(confirmed) is str and confirmed == value["deterministic_digest"],
        "explicit exact candidate digest required",
    )
    exact(
        [
            value["execution_mode"],
            value["experiment_id"],
            value["attempt_id"],
            value["output_path"],
        ],
        [mode, S.mode_identity(mode), attempt_for(mode), str(output_for(mode))],
        "fixed E4 execution identity differs",
    )
    require(
        value["status"] == "REVIEW_AND_EXPLICIT_CONFIRMATION_REQUIRED"
        and value["candidate_is_execution_authority"] is False
        and value["requires_explicit_digest_confirmation"] is True
        and value["locked_128_evaluation_authorized"] is False
        and type(value["expected_cell_count"]) is int
        and value["expected_cell_count"] == 1024,
        "E4 candidate authority or denominator differs",
    )
    require(
        type(value["coordinator_source"]) is dict
        and type(value["receiver_certificate"]) is dict
        and ((value["connector_qualification"] is None) is (mode == S.PUBLIC)),
        "E4 candidate qualification mode differs",
    )
    return value


def candidate(history, mode, qualification=None):
    """Pure envelope from genuine registered reconstruction, never consent."""
    inputs = history.inputs(mode)
    value = R.candidate(inputs, output_for(mode), history.environment, qualification)
    require(inputs.manifest["execution_mode"] == mode, "genuine input mode differs")
    return digested(
        {
            **B.without_digest(value),
            "schema_version": DOMAIN
            + (
                "/public-authorization-candidate"
                if mode == S.PUBLIC
                else "/replication-authorization-candidate"
            ),
            "coordinator_source": history.source,
            "receiver_certificate": history.reference,
            "attempt_id": attempt_for(mode),
        }
    )


def read_authorization(mode, reviewed, source, confirmed=None):
    reviewed = R.oid(reviewed)
    head = core.git_head(ROOT)
    core.require_ancestor(ROOT, source["implementation_revision"], reviewed)
    core.require_ancestor(ROOT, reviewed, head)
    item = R.snapshot_file(authorization_for(mode))
    R.reviewed_file(item, reviewed)  # Authenticate before parsing any references.
    saved = parse(item.raw)
    auth = auth_shape(
        item.raw,
        mode,
        saved["deterministic_digest"] if confirmed is None else confirmed,
    )
    exact(auth["coordinator_source"], source, "reviewed E4 source differs")
    raw = R.snapshot_file(raw_authorization_for(mode))
    require(raw.raw == item.raw, "raw and reviewed candidate bytes differ")
    item.revalidate()
    raw.revalidate()
    return auth, item, raw


def fence_value(auth, reviewed, execution_head):
    return F._value(S, DOMAIN, PUBLIC_ATTEMPT, auth, reviewed, execution_head)


@dataclass(frozen=True)
class _Saved:
    mode: str
    publication: object
    authorization: object
    raw_authorization: object
    claim: object
    fence: object

    @property
    def binding(self):
        return self.publication.binding

    @property
    def auth(self):
        return self.binding["authorization"]

    def check(self):
        self.publication.revalidate()
        R.reviewed_file(self.authorization, self.binding["reviewed_revision"])
        self.raw_authorization.revalidate()
        self.claim.revalidate()
        if self.fence is not None:
            self.fence.revalidate()


def load_saved(mode, source):
    """Fixed committed output and exact persisted ownership, never absence."""
    publication = S.inspect(output_for(mode))
    binding = G.V.binding_for_mode(
        publication.binding, mode, output_for(mode), authorization_for(mode)
    )
    auth, item, raw = read_authorization(mode, binding["reviewed_revision"], source)
    require(
        canonical(auth) == canonical(binding["authorization"]),
        "persisted reviewed authorization differs",
    )
    core.require_ancestor(
        ROOT, binding["reviewed_revision"], R.oid(binding["execution_head_revision"])
    )
    core.require_ancestor(ROOT, binding["execution_head_revision"], core.git_head(ROOT))
    claim = R.snapshot_file(S.claim_path(auth))
    require(claim.raw == canonical(binding["claim"]), "persisted exact claim differs")
    fence = None
    if mode == S.PUBLIC:
        fence = R.snapshot_file(FENCE)
        require(
            fence.raw
            == canonical(
                fence_value(
                    auth,
                    binding["reviewed_revision"],
                    binding["execution_head_revision"],
                )
            ),
            "persisted fixed-attempt fence differs",
        )
    result = _Saved(mode, publication, item, raw, claim, fence)
    result.check()
    return result


def exact_ledger(rows):
    """Permit only specified authenticated rows; no arbitrary future additions."""
    parent = S.mechanics._PinnedParent.open(S.LEDGER)
    try:
        require(
            all(path.parent == S.LEDGER for path in rows),
            "direct fixed ledger children required",
        )
        names = {path.name for path in rows}
        before = S.base.storage._generation(parent, names)
        for path, item in rows.items():
            item.revalidate()
            require(
                item.raw
                == S.mechanics._read_bounded_regular_file_at(
                    parent, path.name, max_bytes=S.base.MAX_CONTROL_BYTES
                ),
                "authenticated ledger row differs",
            )
        require(
            before == S.base.storage._generation(parent, names),
            "ledger changed during observation",
        )
    finally:
        parent.close()


@dataclass
class _Session:
    history: object
    mode: str
    phase: str
    reviewed: object = None
    auth: object = None
    authorization: object = None
    raw_authorization: object = None
    saved: object = None
    public_saved: object = None
    original_saved: object = None
    claim: object = None
    fence: object = None
    qualifier_snapshots: list = field(default_factory=list)
    qualification: object = None
    effects: dict = field(
        default_factory=lambda: dict(
            fixed_attempt_consumed=False,
            authorization_consumed=False,
            publication_committed=False,
            candidate_published=False,
            summary_published=False,
        )
    )

    def check(self):
        guard()
        require(
            self.phase in ("BEFORE", "FENCED", "CLAIMED", "SAVED"),
            "closed E4 lifecycle phase required",
        )
        self.history.revalidate()
        rows = self.history.historical_claims()
        require(
            self.saved is None or self.saved.mode == self.mode,
            "saved operation mode differs",
        )
        require(
            self.public_saved is None or self.public_saved.mode == S.PUBLIC,
            "PUBLIC reference mode differs",
        )
        require(
            self.original_saved is None or self.original_saved.mode == S.REPLICATION,
            "original consumed mode differs",
        )
        for saved in (self.saved, self.public_saved, self.original_saved):
            if saved is not None:
                saved.check()
                rows[saved.claim.path] = saved.claim
                if saved.fence is not None:
                    rows[FENCE] = saved.fence
        if self.authorization is not None:
            R.reviewed_file(self.authorization, self.reviewed)
            self.raw_authorization.revalidate()
            exact(
                S.parent_binding(output_for(self.mode)),
                self.auth["output_parent"],
                "authorized output parent changed",
            )
        for item, reviewed in self.qualifier_snapshots:
            R.reviewed_file(item, reviewed)
        if self.mode == S.PUBLIC:
            if self.original_saved is None:
                original_unused()
            else:
                require(
                    self.phase == "SAVED",
                    "original spent context only allowed for saved PUBLIC analysis",
                )
        elif self.phase == "BEFORE":
            original_unused()
        if self.phase == "BEFORE":
            if self.mode == S.PUBLIC:
                public_unused()
        elif self.phase in ("FENCED", "CLAIMED"):
            require(
                not os.path.lexists(summary_for(self.mode)),
                "summary occupied during run",
            )
            require(
                (self.fence is not None) is (self.mode == S.PUBLIC),
                "exact mode-specific owned fence required",
            )
            if self.fence is not None:
                self.fence.revalidate()
                require(
                    self.fence.raw
                    == canonical(
                        fence_value(self.auth, self.reviewed, self.history.head)
                    ),
                    "owned fence differs",
                )
                rows[FENCE] = self.fence
            if self.phase == "FENCED":
                require(
                    self.mode == S.PUBLIC and self.fence is not None,
                    "fenced PUBLIC state required",
                )
                require(
                    not os.path.lexists(S.claim_path(self.auth))
                    and not os.path.lexists(PUBLIC_OUTPUT),
                    "candidate/output occupied before second consumption",
                )
            else:
                require(self.claim is not None, "owned consumed claim required")
                self.claim.revalidate()
                claimed = parse(self.claim.raw)
                require(
                    self.claim.path == S.claim_path(self.auth)
                    and self.claim.raw
                    == canonical(
                        S.claim_value(
                            self.auth,
                            self.reviewed,
                            self.history.head,
                            claimed["owner_nonce"],
                        )
                    ),
                    "owned claim linkage differs",
                )
                rows[self.claim.path] = self.claim
        if self.phase == "SAVED":
            require(self.saved is not None, "authenticated committed output required")
        require(
            not os.path.lexists(ORIGINAL_PREFLIGHT),
            "old entrypoint slot must remain absent",
        )
        exact_ledger(rows)
        guard()
        G.clean(self.history.head)


def begin():
    global _STARTED
    guard()
    require(not _STARTED, "fresh process required; no retry or resume")
    _STARTED = True


def session(mode, revision, *, reviewed=None, confirmed=None, saved=False):
    global _CURRENT
    S.mode_identity(mode)
    history = G.open_history(revision)
    state = _Session(history, mode, "SAVED" if saved else "BEFORE")
    _CURRENT = state
    if saved:
        state.saved = load_saved(mode, history.source)
        binding = state.saved.binding
        state.reviewed, state.auth = binding["reviewed_revision"], state.saved.auth
        state.authorization, state.raw_authorization = (
            state.saved.authorization,
            state.saved.raw_authorization,
        )
        state.effects.update(
            authorization_consumed=True,
            publication_committed=True,
            fixed_attempt_consumed=mode == S.PUBLIC,
        )
    elif reviewed is not None:
        state.reviewed = R.oid(reviewed)
        state.auth, state.authorization, state.raw_authorization = read_authorization(
            mode, reviewed, history.source, confirmed
        )
        require(
            not os.path.lexists(S.claim_path(state.auth)),
            "candidate claim occupied; no retry",
        )
    if mode == S.REPLICATION:
        state.public_saved = load_saved(S.PUBLIC, history.source)
    elif saved and os.path.lexists(B.fixed_claim()):
        # Public qualification remains usable after ORIGINAL consumption only
        # with a complete, source-bound original run; no skip-unused parameter.
        state.original_saved = load_saved(S.REPLICATION, history.source)
    state.check()
    return state


def run_binding(state, claim):
    auth = state.auth
    return S.frozen_binding(
        digested(
            dict(
                schema_version=S.DOMAIN + "/run-binding",
                execution_mode=state.mode,
                experiment_id=S.mode_identity(state.mode),
                input_manifest_digest=auth["input_manifest_digest"],
                authorization=auth,
                authorization_path=str(authorization_for(state.mode)),
                reviewed_revision=state.reviewed,
                execution_head_revision=state.saved.binding["execution_head_revision"]
                if state.saved
                else state.history.head,
                claim=claim,
                replication_execution_authorized=state.mode == S.REPLICATION,
            )
        )
    )


def analysis_value(history, saved, receipt):
    mode, binding = saved.mode, saved.binding
    auth, public = saved.auth, mode == S.PUBLIC
    return digested(
        dict(
            schema_version=DOMAIN + "/analysis",
            status="E4_COORDINATOR_INDEPENDENT_ANALYSIS_PASS",
            execution_mode=mode,
            experiment_id=S.mode_identity(mode),
            attempt_id=attempt_for(mode),
            output_path=str(output_for(mode)),
            execution_commit_digest=saved.publication.commit["deterministic_digest"],
            execution_receipt_digest=receipt["deterministic_digest"],
            run_binding_digest=binding["deterministic_digest"],
            authorization_digest=auth["deterministic_digest"],
            coordinator_source=history.source,
            receiver_certificate=history.reference,
            input_manifest_digest=history.inputs(mode).manifest["deterministic_digest"],
            public_attempt_fence_sha256=sha(saved.fence.raw) if public else None,
            authorization_consumed=True,
            integrity=receipt["integrity"],
            reduction=receipt["reduction"],
            task_count=64,
            source_multiset_count=1 if public else 64,
            public_cells_executed=1024 if public else 0,
            replication_cells_executed=receipt["replication_cells_executed"],
            replication_execution_authorized=not public,
            public_coordinator_qualified=public,
            production_adapter_executed=not public,
            scientific_decision=receipt["scientific_decision"],
            locked_128_evaluation_authorized=False,
            historical_screen_conjunction=dict(
                original_public=False, receiver_v2_public=False
            ),
            claim_boundary="shared coordinator and PUBLIC adapter only; no production authority or population inference"
            if public
            else "original finite sealed 64-source engineering screen only; no additional execution authority",
        )
    )


def qualification_reference(value):
    return dict(
        summary_path=str(ROOT / SUMMARY_MIRROR),
        summary_sha256=sha(canonical(value)),
        summary_digest=value["deterministic_digest"],
        output_path=str(PUBLIC_OUTPUT),
        commit_digest=value["execution_commit_digest"],
        source_digest=value["coordinator_source"]["deterministic_digest"],
    )


def reviewed_public_summary(state, reviewed, saved):
    items = []
    for path in (SUMMARY_MIRROR, COMMIT_MIRROR):
        item = R.snapshot_file(ROOT / path)
        R.reviewed_file(item, reviewed)
        items.append(item)
        state.qualifier_snapshots.append((item, reviewed))
    require(
        items[1].raw == canonical(saved.publication.commit),
        "reviewed PUBLIC COMMIT differs",
    )
    raw_summary = R.snapshot_file(PUBLIC_SUMMARY)
    require(raw_summary.raw == items[0].raw, "raw PUBLIC summary differs")
    G._state(state.history).evidence.snapshots.append(raw_summary)
    return items[0]


def replay_public_qualification(state):
    saved = state.public_saved
    require(
        saved is not None and state.mode == S.REPLICATION,
        "owned production PUBLIC gate required",
    )
    require(
        canonical(candidate(state.history, S.PUBLIC)) == canonical(saved.auth),
        "reconstructed PUBLIC candidate differs",
    )
    summary = reviewed_public_summary(state, state.reviewed, saved)
    state.check()
    receipt = R.reduce_rows(
        state.history.inputs(S.PUBLIC), saved.publication.rows, saved.binding
    )
    exact(receipt, saved.publication.receipt, "whole PUBLIC receipt did not reproduce")
    value = analysis_value(state.history, saved, receipt)
    require(
        canonical(value) == summary.raw,
        "whole reviewed PUBLIC summary did not reproduce",
    )
    state.check()
    return qualification_reference(value)


def reconstruct_and_admit(state):
    state.check()
    G.reconstruct(state.history)
    state.check()
    if state.mode == S.REPLICATION:
        state.qualification = replay_public_qualification(state)
    expected = candidate(state.history, state.mode, state.qualification)
    if state.auth is not None:
        require(
            canonical(expected) == state.authorization.raw,
            "whole genuinely reconstructed E4 candidate differs",
        )
    if state.saved is not None:
        exact(
            run_binding(state, state.saved.binding["claim"]),
            state.saved.binding,
            "complete admitted run binding differs",
        )
    state.check()
    return expected


def prepare_public(revision):
    begin()
    original_unused()
    public_unused()
    for path in (
        RAW_AUTH,
        ROOT / PUBLIC_AUTH,
        ROOT / SUMMARY_MIRROR,
        ROOT / COMMIT_MIRROR,
    ):
        require(not os.path.lexists(path), "E4 PUBLIC preparation slot occupied")
    S.descriptor_preflight()
    state = session(S.PUBLIC, revision)
    value = reconstruct_and_admit(state)
    state.effects["candidate_published"] = None
    S.base._publish_summary(RAW_AUTH, value, state.check)
    state.effects["candidate_published"] = True
    state.check()
    return operation(
        state,
        "E4_PUBLIC_CANDIDATE_PREPARED_NOT_RUN",
        candidate_digest=value["deterministic_digest"],
        authorization_path=str(RAW_AUTH),
    )


def run(mode, revision, reviewed, confirmed):
    """Shared fixed dispatcher; production additionally needs its future reviewed candidate."""
    begin()
    S.mechanics._require_sha256(confirmed, "explicit candidate digest")
    if mode == S.PUBLIC:
        original_unused()
        public_unused()
    else:
        S.mode_identity(mode)
        original_unused()
    S.descriptor_preflight()
    state = session(mode, revision, reviewed=reviewed, confirmed=confirmed)
    reconstruct_and_admit(state)
    state.check()
    if mode == S.PUBLIC:
        state.effects["fixed_attempt_consumed"] = None
        try:
            _, state.fence = F.consume(
                S,
                FENCE,
                domain=DOMAIN,
                attempt_id=PUBLIC_ATTEMPT,
                authorization=state.auth,
                reviewed=state.reviewed,
                execution_head=state.history.head,
                snapshot_type=core.FileSnapshot,
            )
        except S.ExecutionFailure as error:
            state.effects["fixed_attempt_consumed"] = error.authorization_consumed
            raise
        state.effects["fixed_attempt_consumed"] = True
        state.phase = "FENCED"
        state.check()
    state.effects["authorization_consumed"] = None
    try:
        claim, state.claim = S.consume(
            state.auth, state.reviewed, state.history.head, core.FileSnapshot
        )
    except S.ExecutionFailure as error:
        state.effects["authorization_consumed"] = error.authorization_consumed
        raise
    state.effects["authorization_consumed"] = True
    require(state.claim.raw == canonical(claim), "returned owned claim differs")
    state.phase = "CLAIMED"
    binding = run_binding(state, claim)
    state.check()

    def action(emit):
        inputs, rows = state.history.inputs(mode), []
        for cell in inputs.cells:
            row = R.record(inputs, cell, binding)
            emit(cell["cell_index"], row)
            rows.append(row)
            if len(rows) % 32 == 0:
                G.N.progress(
                    "E4_COORDINATOR_CELLS_" + str(len(rows)), state.history.work
                )
                state.check()
        return R.reduce_rows(inputs, rows, binding)

    state.effects["publication_committed"] = None
    try:
        commit = S.publish(output_for(mode), binding, action, state.check)
    except S.ExecutionFailure as error:
        if error.status in ("SPENT_NOT_RUN", "INVALID_ANALYSIS"):
            state.effects["publication_committed"] = False
        raise
    state.effects["publication_committed"] = True
    state.check()
    return operation(
        state,
        "E4_EXECUTION_COMMITTED",
        commit=commit,
        output_path=str(output_for(mode)),
    )


def _analyze(state):
    reconstruct_and_admit(state)
    saved = state.saved
    receipt = R.reduce_rows(
        state.history.inputs(state.mode), saved.publication.rows, saved.binding
    )
    exact(
        receipt,
        saved.publication.receipt,
        "whole saved execution receipt did not reproduce",
    )
    result = analysis_value(state.history, saved, receipt)
    if state.original_saved is not None:
        # Authenticate the original consumed context as this same coordinator's
        # whole candidate, including the independently replayed PUBLIC reference.
        original = state.original_saved
        summary = reviewed_public_summary(
            state, original.binding["reviewed_revision"], saved
        )
        require(
            summary.raw == canonical(result), "original reviewed PUBLIC summary differs"
        )
        expected = candidate(
            state.history, S.REPLICATION, qualification_reference(result)
        )
        require(
            canonical(expected) == original.authorization.raw,
            "owned original candidate differs after consumption",
        )
    state.check()
    return result


def analyze(mode, revision, *, save=False, verify=False):
    require(
        type(save) is bool and type(verify) is bool and not (save and verify),
        "one fixed analysis action required",
    )
    begin()
    if save:
        require(
            not os.path.lexists(summary_for(mode)), "summary occupied; no replacement"
        )
    state = session(mode, revision, saved=True)
    saved_summary = R.snapshot_file(summary_for(mode)) if verify else None
    if saved_summary is not None:
        G._state(state.history).evidence.snapshots.append(saved_summary)
    value = _analyze(state)
    if verify:
        require(saved_summary.raw == canonical(value), "entire saved summary differs")
        saved_summary.revalidate()
    if save:
        state.effects["summary_published"] = None
        S.base._publish_summary(summary_for(mode), value, state.check)
        state.effects["summary_published"] = True
    state.check()
    return value


def operation(state, status, **extra):
    return digested(
        dict(
            schema_version=DOMAIN + "/operation",
            status=status,
            operation_head=state.history.head,
            coordinator_source=state.history.source,
            receiver_certificate=state.history.reference,
            effects=dict(state.effects),
            work=state.history.work,
            execution_mode=state.mode,
            replication_execution_authorized=state.mode == S.REPLICATION
            and state.effects["authorization_consumed"] is True,
            locked_128_evaluation_authorized=False,
            automatic_retry_allowed=False,
            **extra,
        )
    )


def inspect_metadata(revision):
    begin()
    original_unused()
    public_unused()
    state = session(S.PUBLIC, revision)
    return operation(
        state,
        "E4_METADATA_MATCH_NOT_RECONSTRUCTED_OR_ADMITTED",
        current_receiver_admitted=False,
        new_coordinator_qualified=False,
        numerical_reconstruction_invoked=False,
    )


def failure(error, completed=None, delivery="NOT_ATTEMPTED"):
    state = _CURRENT
    return digested(
        dict(
            schema_version=DOMAIN + "/failure",
            status="E4_OPERATION_REJECTED_OR_DELIVERY_UNCERTAIN",
            reason=str(error),
            effects=dict(state.effects) if state is not None else None,
            work=state.history.work if state is not None else G.N.initial_work(),
            completed_operation=completed,
            result_delivery=delivery,
            retain_all_artifacts=True,
            automatic_retry_allowed=False,
            locked_128_evaluation_authorized=False,
        )
    )


def guard():
    G.guard()
    require(
        canonical(configuration()) == _CONFIGURATION_RAW,
        "E4 coordinator fixed configuration changed",
    )
    require(Path(__file__).resolve() == ROOT / SCRIPT, "E4 coordinator origin differs")
    # Static invariants also run after compileall in the validation suite.
    # The live attestation below this boundary still requires absent caches.
    require(
        type(G.__spec__.loader) is importlib.machinery.SourceFileLoader
        and Path(G.__spec__.origin) == ROOT / RUNTIME
        and Path(G.__file__) == ROOT / RUNTIME,
        "E4 runtime source origin differs",
    )
    for module, name, original in _DEPENDENCIES:
        require(
            getattr(module, name) is original,
            "E4 coordinator callable substituted: " + name,
        )


def self_test():
    guard()
    require(
        FENCE != C.FENCE
        and PUBLIC_OUTPUT != C.PUBLIC_OUTPUT
        and FENCE != B.fixed_claim(),
        "fixed namespaces overlap",
    )
    require(
        output_for(S.REPLICATION) == B.OUTPUT
        and summary_for(S.REPLICATION) == C.REPLICATION_SUMMARY,
        "original study destination changed",
    )
    return digested(
        dict(
            status="E4_COORDINATOR_STATIC_SELF_TEST_ONLY",
            source_files=list(G.SOURCE_FILES),
            genuine_reconstruction_performed=False,
            new_public_attempts=0,
            replication_cells_executed=0,
            replication_execution_authorized=False,
            locked_128_evaluation_authorized=False,
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    modes = parser.add_mutually_exclusive_group(required=True)
    commands = (
        "self-test",
        "inspect",
        "prepare-public",
        "run-public",
        "analyze-public",
        "verify-public",
    )
    for name in commands:
        modes.add_argument("--" + name, action="store_true")
    parser.add_argument("--implementation-revision")
    parser.add_argument("--reviewed-revision")
    parser.add_argument("--confirm-digest")
    args = vars(parser.parse_args())
    command = next(name for name in commands if args[name.replace("-", "_")])
    required = set() if command == "self-test" else {"implementation_revision"}
    if command == "run-public":
        required |= {"reviewed_revision", "confirm_digest"}
    supplied = {
        name
        for name in ("implementation_revision", "reviewed_revision", "confirm_digest")
        if args[name] is not None
    }
    if supplied != required:
        parser.error("exact mode-specific arguments required; no production mode")
    completed, delivery = None, "NOT_ATTEMPTED"
    try:
        revision = args["implementation_revision"]
        if command == "self-test":
            result = self_test()
        elif command == "inspect":
            result = inspect_metadata(revision)
        elif command == "prepare-public":
            result = prepare_public(revision)
        elif command == "run-public":
            result = run(
                S.PUBLIC, revision, args["reviewed_revision"], args["confirm_digest"]
            )
        else:
            result = analyze(
                S.PUBLIC,
                revision,
                save=command == "analyze-public",
                verify=command == "verify-public",
            )
        completed = result
        raw = canonical(result)
        delivery = "UNKNOWN_PARTIAL_OR_COMPLETE"
        require(sys.stdout.buffer.write(raw) == len(raw), "short E4 result write")
        sys.stdout.buffer.flush()
    except (Exception, KeyboardInterrupt) as error:
        raw = canonical(failure(error, completed, delivery))
        sys.stderr.buffer.write(raw)
        sys.stderr.buffer.flush()
        raise SystemExit(1) from error


_DEPENDENCIES = tuple(
    (module, name, getattr(module, name))
    for module, names in (
        (
            sys.modules[__name__],
            (
                "configuration",
                "output_for",
                "authorization_for",
                "raw_authorization_for",
                "summary_for",
                "attempt_for",
                "original_unused",
                "public_unused",
                "auth_shape",
                "candidate",
                "read_authorization",
                "fence_value",
                "load_saved",
                "exact_ledger",
                "begin",
                "session",
                "run_binding",
                "analysis_value",
                "qualification_reference",
                "reviewed_public_summary",
                "replay_public_qualification",
                "reconstruct_and_admit",
                "prepare_public",
                "run",
                "_analyze",
                "analyze",
                "operation",
            ),
        ),
        (_Session, ("check",)),
        (_Saved, ("check",)),
        (
            S,
            (
                "consume",
                "claim_value",
                "claim_path",
                "publish",
                "inspect",
                "frozen_binding",
                "parent_binding",
                "descriptor_preflight",
            ),
        ),
        (F, ("consume", "_value", "ensure_unused")),
        (S.base, ("_publish_summary",)),
    )
    for name in names
)


if __name__ == "__main__":
    main()
