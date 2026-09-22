#!/usr/bin/env python3
"""Additive receiver coordinator: fixed PUBLIC qualification, not replication.

The unchanged v1 bridge authenticates historical evidence. This successor owns
its admission objects and shared run/analysis coordinator. Its CLI exposes only
the one fixed PUBLIC attempt; the closed sealed-input adapter is not executed
or authorized by that qualification. No original receipt or code is rewritten.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import importlib.util
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = "scripts/feedback_budget_receiver_execution.py"
TEST = "tests/test_feedback_budget_receiver_execution.py"
HELPER = "scripts/feedback_budget_receiver_attempt.py"
HELPER_TEST = "tests/test_feedback_budget_receiver_attempt.py"
POLICY = "docs/strategy/countdown_feedback_budget_receiver_v2_public.md"
BRIDGE = "scripts/feedback_budget_replication_reattest.py"
BRIDGE_REVISION = "951d273ccf4072b8e0557970cc71095951b843b7"
BRIDGE_REVIEWED = "bf83efbaa94af3dc9b6863a19202acffa815ad74"
BRIDGE_DIGEST = "fa6947915c170158fcce4ef524988771648fddfe03e442648a9faf1dd9cf08b6"
SPEC = importlib.util.spec_from_file_location(
    "receiver_coordinator_bridge", ROOT / BRIDGE
)
assert SPEC is not None and SPEC.loader is not None
B = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = B
SPEC.loader.exec_module(B)
R, S, core = B.R, B.S, B.core
F = R.load("receiver_coordinator_attempt", HELPER)
canonical, parse, require = B.canonical, B.parse, B.require
digested, digest, sha = B.digested, B.digest, B.sha
DOMAIN = B.DOMAIN + "/coordinator/v2"
PUBLIC_ATTEMPT = "receiver_public_full_path_20260922_a/v1"
PUBLIC_OUTPUT = ROOT / "artifacts/work/feedback-budget-v7-receiver-public-20260922-a"
RAW_AUTH = Path(str(PUBLIC_OUTPUT) + ".authorization.json")
PUBLIC_SUMMARY = Path(str(PUBLIC_OUTPUT) + ".summary.json")
PUBLIC_AUTH = "docs/qualifications/countdown_feedback_budget_receiver_v2_public_20260922.authorization.json"
SUMMARY_MIRROR = "docs/qualifications/countdown_feedback_budget_receiver_v2_public_20260922.summary.json"
COMMIT_MIRROR = "docs/qualifications/countdown_feedback_budget_receiver_v2_public_20260922.commit.json"
REPLICATION_AUTH = (
    "docs/preregistrations/countdown_feedback_budget_receiver_v2.authorization.json"
)
REPLICATION_SUMMARY = Path(str(B.OUTPUT) + ".receiver-v2.summary.json")
FENCE = S.LEDGER / ("receiver-public-" + digest([DOMAIN, PUBLIC_ATTEMPT]) + ".json")
SOURCE_FILES = (SCRIPT, HELPER, TEST, HELPER_TEST, POLICY)
AUTH_FIELDS = R.AUTH_FIELDS | {"coordinator_source", "receiver_admission", "attempt_id"}


def output_for(mode):
    S.mode_identity(mode)
    return PUBLIC_OUTPUT if mode == S.PUBLIC else B.OUTPUT


def authorization_for(mode):
    S.mode_identity(mode)
    return ROOT / (PUBLIC_AUTH if mode == S.PUBLIC else REPLICATION_AUTH)


def summary_for(mode):
    S.mode_identity(mode)
    return PUBLIC_SUMMARY if mode == S.PUBLIC else REPLICATION_SUMMARY


def attempt_for(mode):
    S.mode_identity(mode)
    return PUBLIC_ATTEMPT if mode == S.PUBLIC else S.REPLICATION_ID


def unused(mode):
    if mode == S.PUBLIC:
        F.ensure_unused(S, FENCE)
        require(not os.path.lexists(PUBLIC_OUTPUT), "fixed PUBLIC output occupied")
    else:
        S.mode_identity(mode)
        B.unused()
    require(
        not os.path.lexists(summary_for(mode)),
        "fixed coordinator summary occupied before execution",
    )


def attest(revision):
    revision, head = R.oid(revision), core.git_head(ROOT)
    core.require_ancestor(ROOT, BRIDGE_REVIEWED, revision)
    core.require_ancestor(ROOT, revision, head)
    require(Path(__file__).resolve() == ROOT / SCRIPT, "coordinator origin differs")
    R.public._origin(B, BRIDGE)
    R.public._origin(F, HELPER)
    receiver = B.attest(BRIDGE_REVISION)
    files, snapshots = {}, []
    for relative in SOURCE_FILES:
        item = R.snapshot_file(ROOT / relative)
        R.reviewed_file(item, revision)
        files[relative] = dict(byte_count=len(item.raw), sha256=sha(item.raw))
        snapshots.append(item)
    for item in snapshots:
        item.revalidate()
    require(head == core.git_head(ROOT), "coordinator source HEAD changed")
    return digested(
        dict(
            schema_version=DOMAIN + "/source",
            implementation_revision=revision,
            receiver_source=receiver,
            files=files,
        )
    )


def receiver_admit(observe):
    # Genuine historical admission; no fabricated v1 Admission/Inputs objects.
    return B.admit(
        ROOT / B.CANDIDATE,
        ROOT / B.CERTIFICATE,
        BRIDGE_DIGEST,
        BRIDGE_REVIEWED,
        observe=observe,
    )


def receiver_reference(base):
    return dict(
        authorization=B.file_reference(base.snapshots[0]),
        certificate=B.file_reference(base.snapshots[1]),
        bundle_commit=B.file_reference(base.snapshots[2]),
        authorization_digest=BRIDGE_DIGEST,
        reviewed_revision=BRIDGE_REVIEWED,
        source_digest=parse(base.proof.source_raw)["deterministic_digest"],
    )


def candidate(mode, inputs, base, source, qualification=None):
    value = R.candidate(
        inputs,
        output_for(mode),
        parse(base.proof.environment_raw),
        qualification,
    )
    require(inputs.manifest["execution_mode"] == mode, "input mode differs")
    return digested(
        {
            **B.without_digest(value),
            "schema_version": DOMAIN
            + (
                "/public-authorization-candidate"
                if mode == S.PUBLIC
                else "/replication-authorization-candidate"
            ),
            "coordinator_source": source,
            "receiver_admission": receiver_reference(base),
            "attempt_id": attempt_for(mode),
        }
    )


def auth_shape(raw, mode, confirmed):
    S.mode_identity(mode)
    value = parse(raw)
    core.require_digest(value)
    suffix = (
        "/public-authorization-candidate"
        if mode == S.PUBLIC
        else "/replication-authorization-candidate"
    )
    require(
        set(value) == AUTH_FIELDS and value["schema_version"] == DOMAIN + suffix,
        "closed coordinator candidate domain required",
    )
    require(
        type(confirmed) is str and confirmed == value["deterministic_digest"],
        "explicit coordinator candidate digest differs",
    )
    require(
        value["execution_mode"] == mode
        and value["experiment_id"] == S.mode_identity(mode)
        and value["attempt_id"] == attempt_for(mode)
        and value["output_path"] == str(output_for(mode)),
        "fixed coordinator attempt differs",
    )
    require(
        value["status"] == "REVIEW_AND_EXPLICIT_CONFIRMATION_REQUIRED"
        and value["candidate_is_execution_authority"] is False
        and value["requires_explicit_digest_confirmation"] is True
        and value["locked_128_evaluation_authorized"] is False
        and type(value["expected_cell_count"]) is int
        and value["expected_cell_count"] == 1024,
        "coordinator authority flags differ",
    )
    require(
        type(value["coordinator_source"]) is dict
        and type(value["receiver_admission"]) is dict
        and ((value["connector_qualification"] is None) is (mode == S.PUBLIC)),
        "coordinator source or qualification mode differs",
    )
    return value


@dataclass(frozen=True)
class Admitted:
    base: object
    snapshot: object
    inputs: object
    source_raw: bytes
    reviewed: str
    head: str
    qualifier_check: object

    @property
    def auth(self):
        return parse(self.snapshot.raw)

    def revalidate(self):
        R.reviewed_file(self.snapshot, self.reviewed)
        self.base.revalidate()
        if self.auth["execution_mode"] == S.PUBLIC:
            self.inputs.revalidate()
        self.qualifier_check()
        require(
            canonical(attest(parse(self.source_raw)["implementation_revision"]))
            == self.source_raw,
            "coordinator source changed",
        )


def admit(
    mode,
    auth_path,
    confirmed,
    reviewed,
    *,
    execution_head=None,
    observe=lambda stage: None,
):
    require(
        Path(auth_path) == authorization_for(mode), "fixed promoted candidate required"
    )
    snapshot = R.snapshot_file(auth_path)
    auth = auth_shape(snapshot.raw, mode, confirmed)
    reviewed, head = R.oid(reviewed), R.oid(execution_head or core.git_head(ROOT))
    revision = R.oid(auth["coordinator_source"]["implementation_revision"])
    core.require_ancestor(ROOT, revision, reviewed)
    core.require_ancestor(ROOT, reviewed, head)
    core.require_ancestor(ROOT, head, core.git_head(ROOT))
    R.reviewed_file(snapshot, reviewed)
    source = attest(revision)
    require(
        canonical(source) == canonical(auth["coordinator_source"]),
        "reviewed coordinator source differs",
    )
    require(
        canonical(S.parent_binding(output_for(mode)))
        == canonical(auth["output_parent"]),
        "coordinator output parent changed",
    )
    qualifier, qualifier_check = None, lambda: None
    if mode == S.REPLICATION:
        # Closed dormant adapter: no old candidate grants this successor authority.
        # Authenticate the new PUBLIC proof before entering sealed-input admission.
        qualifier, qualifier_check = qualified_public(reviewed, source, observe)
        require(
            canonical(qualifier) == canonical(auth["connector_qualification"]),
            "coordinator PUBLIC qualification differs",
        )
    base = receiver_admit(observe)
    inputs = R.load_inputs(S.PUBLIC) if mode == S.PUBLIC else base.inputs
    require(
        snapshot.raw == canonical(candidate(mode, inputs, base, source, qualifier)),
        "independently reconstructed coordinator candidate differs",
    )
    result = Admitted(
        base, snapshot, inputs, canonical(source), reviewed, head, qualifier_check
    )
    result.revalidate()
    return result


def prepare_public(revision, observe=lambda stage: None):
    unused(S.PUBLIC)
    B.unused()  # This operation is scoped before any production attempt.
    require(
        not os.path.lexists(RAW_AUTH), "PUBLIC candidate slot occupied; no replacement"
    )
    require(
        not os.path.lexists(ROOT / PUBLIC_AUTH),
        "promoted PUBLIC candidate already exists",
    )
    S.descriptor_preflight()
    source = attest(revision)
    base = receiver_admit(observe)
    inputs = R.load_inputs(S.PUBLIC)
    value = candidate(S.PUBLIC, inputs, base, source)

    def check():
        unused(S.PUBLIC)
        B.unused()
        inputs.revalidate()
        base.revalidate()
        require(
            canonical(attest(revision)) == canonical(source),
            "PUBLIC preparation source changed",
        )
        require(
            canonical(S.parent_binding(PUBLIC_OUTPUT))
            == canonical(value["output_parent"]),
            "PUBLIC preparation parent changed",
        )

    S.base._publish_summary(RAW_AUTH, value, check)
    return value


def run_binding(admitted, claim):
    auth = admitted.auth
    return S.frozen_binding(
        digested(
            dict(
                schema_version=S.DOMAIN + "/run-binding",
                execution_mode=auth["execution_mode"],
                experiment_id=auth["experiment_id"],
                input_manifest_digest=auth["input_manifest_digest"],
                authorization=auth,
                authorization_path=str(admitted.snapshot.path),
                reviewed_revision=admitted.reviewed,
                execution_head_revision=admitted.head,
                claim=claim,
                replication_execution_authorized=auth["execution_mode"]
                == S.REPLICATION,
            )
        )
    )


def fence_arguments(auth, reviewed, head):
    return dict(
        domain=DOMAIN,
        attempt_id=PUBLIC_ATTEMPT,
        authorization=auth,
        reviewed=reviewed,
        execution_head=head,
        snapshot_type=core.FileSnapshot,
    )


def run(mode, auth_path, confirmed, reviewed, observe=lambda stage: None):
    """One shared coordinator; PUBLIC and sealed admission remain distinct."""
    unused(mode)
    require(
        Path(auth_path) == authorization_for(mode), "fixed promoted candidate required"
    )
    initial = R.snapshot_file(auth_path)
    initial_auth = auth_shape(initial.raw, mode, confirmed)
    if os.path.lexists(S.claim_path(initial_auth)):
        raise S.ExecutionFailure(
            "AUTHORIZATION_ALREADY_SPENT",
            True,
            "occupied candidate claim; no admission, replacement fence or retry",
        )
    S.descriptor_preflight()
    admitted = admit(mode, auth_path, confirmed, reviewed, observe=observe)
    initial.revalidate()
    unused(mode)
    admitted.revalidate()
    output = output_for(mode)
    fence = None
    if mode == S.PUBLIC:
        # Irreversible fixed-attempt fence precedes digest-keyed storage claim.
        _, fence = F.consume(
            S, FENCE, **fence_arguments(admitted.auth, admitted.reviewed, admitted.head)
        )
    try:
        claim, snapshot = S.consume(
            admitted.auth, admitted.reviewed, admitted.head, core.FileSnapshot
        )
        binding = run_binding(admitted, claim)

        def check():
            if fence is not None:
                fence.revalidate()
            snapshot.revalidate()
            require(
                canonical(S.parent_binding(output))
                == canonical(admitted.auth["output_parent"]),
                "authorized coordinator parent changed",
            )
            admitted.revalidate()

        def action(emit):
            rows = []
            for cell in admitted.inputs.cells:
                row = R.record(admitted.inputs, cell, binding)
                emit(cell["cell_index"], row)
                rows.append(row)
                if len(rows) % 32 == 0:
                    observe("COORDINATOR_CELLS_" + str(len(rows)))
            return R.reduce_rows(admitted.inputs, rows, binding, observer=observe)

        return S.publish(output, binding, action, check)
    except S.ExecutionFailure as error:
        if fence is not None and error.authorization_consumed is False:
            raise S.ExecutionFailure(
                "SPENT_NOT_RUN",
                True,
                "fixed PUBLIC attempt spent; retain both claim namespaces",
            ) from error
        raise
    except BaseException as error:
        # After entry to consume, a failed/uncertain claim is never replenished.
        raise S.ExecutionFailure(
            "SPENT_NOT_RUN",
            True,
            "coordinator attempt consumed; retain claims and publication",
        ) from error


def analyze(mode, observe=lambda stage: None):
    publication = S.inspect(output_for(mode))
    binding = publication.binding
    require(binding["execution_mode"] == mode, "coordinator analysis mode differs")
    auth = auth_shape(
        canonical(binding["authorization"]),
        mode,
        binding["authorization"]["deterministic_digest"],
    )
    # Persisted claims BEFORE expensive reconstruction; no absence test here.
    claim = S.inspect_claim(binding, core.FileSnapshot)
    fence = (
        F.inspect(
            S,
            FENCE,
            **fence_arguments(
                auth, binding["reviewed_revision"], binding["execution_head_revision"]
            ),
        )
        if mode == S.PUBLIC
        else None
    )
    admitted = admit(
        mode,
        binding["authorization_path"],
        auth["deterministic_digest"],
        binding["reviewed_revision"],
        execution_head=binding["execution_head_revision"],
        observe=observe,
    )
    require(
        canonical(run_binding(admitted, binding["claim"])) == canonical(binding),
        "coordinator admitted binding differs",
    )

    def check():
        publication.revalidate()
        claim.revalidate()
        if fence is not None:
            fence.revalidate()
        admitted.revalidate()

    check()
    receipt = R.reduce_rows(
        admitted.inputs, publication.rows, binding, observer=observe
    )
    require(
        canonical(receipt) == canonical(publication.receipt),
        "coordinator independent receipt differs",
    )
    check()
    public = mode == S.PUBLIC
    value = digested(
        dict(
            schema_version=DOMAIN + "/analysis",
            status="COORDINATOR_INDEPENDENT_ANALYSIS_PASS",
            execution_mode=mode,
            experiment_id=S.mode_identity(mode),
            attempt_id=attempt_for(mode),
            output_path=str(output_for(mode)),
            execution_commit_digest=publication.commit["deterministic_digest"],
            execution_receipt_digest=receipt["deterministic_digest"],
            run_binding_digest=binding["deterministic_digest"],
            authorization_digest=auth["deterministic_digest"],
            coordinator_source=parse(admitted.source_raw),
            receiver_admission=auth["receiver_admission"],
            input_manifest_digest=admitted.inputs.manifest["deterministic_digest"],
            public_attempt_fence_sha256=sha(fence.raw) if fence is not None else None,
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
            claim_boundary=(
                "PUBLIC single-source shared-coordinator and PUBLIC-adapter qualification only; not old bridge run, production adapter execution, replication or causal evidence"
                if public
                else "finite sealed 64-source engineering screen only; no population inference, causal or further execution authority"
            ),
        )
    )
    return value, check


def analyze_and_save(mode, observe=lambda stage: None):
    path = summary_for(mode)
    require(not os.path.lexists(path), "coordinator summary occupied; no overwrite")
    value, check = analyze(mode, observe)
    S.base._publish_summary(path, value, check)
    return value


def verify(mode, observe=lambda stage: None):
    snapshot = R.snapshot_file(summary_for(mode))
    saved = parse(snapshot.raw)
    core.require_digest(saved)
    require(
        saved.get("schema_version") == DOMAIN + "/analysis"
        and saved.get("execution_mode") == mode,
        "saved coordinator summary domain differs",
    )
    value, check = analyze(mode, observe)
    require(
        canonical(value) == snapshot.raw, "saved coordinator summary did not reproduce"
    )
    snapshot.revalidate()
    check()
    return value


def qualified_public(reviewed, expected_source, observe):
    """Closed future sealed-mode gate; PUBLIC evidence never authorizes itself."""
    summary_snapshot = R.snapshot_file(ROOT / SUMMARY_MIRROR)
    commit_snapshot = R.snapshot_file(ROOT / COMMIT_MIRROR)
    for item in (summary_snapshot, commit_snapshot):
        R.reviewed_file(item, reviewed)
    publication = S.inspect(PUBLIC_OUTPUT)
    require(
        canonical(publication.commit) == commit_snapshot.raw,
        "reviewed PUBLIC COMMIT differs",
    )
    value, check = analyze(S.PUBLIC, observe)
    require(
        canonical(value) == summary_snapshot.raw, "reviewed PUBLIC analysis differs"
    )
    require(
        canonical(value["coordinator_source"]) == canonical(expected_source)
        and value["public_coordinator_qualified"] is True
        and value["replication_execution_authorized"] is False
        and value["replication_cells_executed"] == 0
        and value["scientific_decision"] is None,
        "PUBLIC qualification source or authority differs",
    )

    def revalidate():
        for item in (summary_snapshot, commit_snapshot):
            R.reviewed_file(item, reviewed)
        publication.revalidate()
        check()

    revalidate()
    return dict(
        summary_path=str(summary_snapshot.path),
        summary_sha256=sha(summary_snapshot.raw),
        summary_digest=value["deterministic_digest"],
        output_path=str(PUBLIC_OUTPUT),
        commit_digest=value["execution_commit_digest"],
        source_digest=expected_source["deterministic_digest"],
    ), revalidate


def self_test():
    require(
        authorization_for(S.PUBLIC) != authorization_for(S.REPLICATION),
        "candidate namespaces overlap",
    )
    require(output_for(S.REPLICATION) == B.OUTPUT, "fixed production output changed")
    require(FENCE != B.fixed_claim(), "attempt fence overlaps production")
    return dict(
        status="COORDINATOR_STATIC_SELF_TEST_PASS",
        attempt_id=PUBLIC_ATTEMPT,
        replication_execution_authorized=False,
        replication_search_calls=0,
        claim_boundary="static checks only; not execution qualification",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    modes = parser.add_mutually_exclusive_group(required=True)
    for mode in (
        "self-test",
        "prepare-public",
        "run-public",
        "analyze-public",
        "verify-public",
    ):
        modes.add_argument("--" + mode, action="store_true")
    parser.add_argument("--implementation-revision")
    parser.add_argument("--authorization")
    parser.add_argument("--confirm-digest")
    parser.add_argument("--reviewed-revision")
    args = vars(parser.parse_args())
    command = next(
        name
        for name in (
            "self_test",
            "prepare_public",
            "run_public",
            "analyze_public",
            "verify_public",
        )
        if args[name]
    )
    required = {
        "self_test": set(),
        "prepare_public": {"implementation_revision"},
        "run_public": {"authorization", "confirm_digest", "reviewed_revision"},
        "analyze_public": set(),
        "verify_public": set(),
    }[command]
    supplied = {
        name
        for name in (
            "implementation_revision",
            "authorization",
            "confirm_digest",
            "reviewed_revision",
        )
        if args[name] is not None
    }
    if supplied != required:
        parser.error("exact mode-specific arguments required")
    completed = False

    def observe(stage):
        print(stage, file=sys.stderr, flush=True)

    try:
        if command == "self_test":
            result = self_test()
        elif command == "prepare_public":
            value = prepare_public(args["implementation_revision"], observe)
            result = dict(
                status="PUBLIC_CANDIDATE_PREPARED_NOT_RUN",
                authorization_path=str(RAW_AUTH),
                authorization_digest=value["deterministic_digest"],
            )
        elif command == "run_public":
            B.unused()
            value = run(
                S.PUBLIC,
                args["authorization"],
                args["confirm_digest"],
                args["reviewed_revision"],
                observe,
            )
            result = dict(
                status="PUBLIC_EXECUTION_COMMITTED",
                output_path=str(PUBLIC_OUTPUT),
                commit_digest=value["deterministic_digest"],
            )
        else:
            value = (
                analyze_and_save(S.PUBLIC, observe)
                if command == "analyze_public"
                else verify(S.PUBLIC, observe)
            )
            result = dict(
                status="PUBLIC_SUMMARY_SAVED"
                if command == "analyze_public"
                else "PUBLIC_SUMMARY_INDEPENDENTLY_VERIFIED",
                summary_path=str(PUBLIC_SUMMARY),
                summary_digest=value["deterministic_digest"],
                public_cells_executed=value["public_cells_executed"],
                replayed_trace_count=value["integrity"]["replayed_trace_count"],
                budget_prefix_check_count=value["integrity"][
                    "budget_prefix_check_count"
                ],
                source_multiset_count=value["source_multiset_count"],
                scientific_decision=value["scientific_decision"],
            )
        completed = True
        result.update(
            replication_execution_authorized=False, replication_search_calls=0
        )
        sys.stdout.buffer.write(canonical(digested(result)))
        sys.stdout.buffer.flush()
    except BaseException as error:
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
        if completed:
            status = "RESULT_DELIVERY_UNCERTAIN"
            consumed = command in ("run_public", "analyze_public", "verify_public")
        elif isinstance(error, S.ExecutionFailure):
            status, consumed = error.status, error.authorization_consumed
        elif isinstance(error, S.base.PublicationUncertain):
            status, consumed = "PUBLICATION_UNCERTAIN", None
        else:
            status = "NOT_RUN_OR_ANALYSIS_FAILED"
            consumed = None if command in ("analyze_public", "verify_public") else False
        print(str(error), file=sys.stderr)
        try:
            sys.stdout.buffer.write(
                canonical(
                    digested(
                        dict(
                            status=status,
                            authorization_consumed=consumed,
                            replication_execution_authorized=False,
                            automatic_retry_allowed=False,
                        )
                    )
                )
            )
            sys.stdout.buffer.flush()
        except (OSError, ValueError):
            pass
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
