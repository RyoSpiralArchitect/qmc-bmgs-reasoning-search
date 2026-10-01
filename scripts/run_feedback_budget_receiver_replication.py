#!/usr/bin/env python3
"""Reviewed CLI for exactly one already prepared receiver-v2 replication.

Preflight/check are metadata gates, not fresh production admission or consent.
Only --run accepts explicit digest confirmation and delegates consumption/search
to the unchanged qualified coordinator. No candidate, cohort or retry is created.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import importlib.util
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = "scripts/run_feedback_budget_receiver_replication.py"
TEST = "tests/test_feedback_budget_receiver_replication_entrypoint.py"
POLICY = "docs/strategy/countdown_feedback_budget_receiver_v2_entrypoint.md"
CANDIDATE_OPERATOR = "scripts/feedback_budget_receiver_candidate.py"
PREPARER_REVISION = "9d14059362e18a396e4fa865d8a0b3c69fde1eb6"
PREPARER_DIGEST = "cd7497f62f81fe7a5fc1a8b4a0a725bdbaf8b4754aee3d8328d447f8afcf12ee"
CANDIDATE_REVIEW = "119aaf9cef45276c41964b1ec45650534e6df48a"
EVIDENCE_REVIEW = "667cc144ccb70073be8224a69b778f65107109da"
CANDIDATE_DIGEST = "198f4582054184e2e476542afc1621178b3a1fbc6b82bd002b67f99c6684d070"
CANDIDATE_SHA256 = "7adaeba09ffdc21f21a852ad047b1aa7e0914ec284063a3ce768d410147fbb5b"
VERIFICATION = "docs/qualifications/countdown_feedback_budget_receiver_v2_candidate_20260923.verification.json"
VERIFICATION_DIGEST = "68cabef308820b5f2a10cecd97bebbb6aee3ae43c86dd674363b3de51504a367"
PREFLIGHT = "docs/qualifications/countdown_feedback_budget_receiver_v2_entrypoint_20261001.preflight.json"
SOURCE_FILES = (SCRIPT, TEST, POLICY)
SPEC = importlib.util.spec_from_file_location(
    "receiver_replication_candidate", ROOT / CANDIDATE_OPERATOR
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
DOMAIN = C.DOMAIN + "/production-entrypoint/v1"


def oid(value):
    require(
        type(value) is str and re.fullmatch(r"[0-9a-f]{40}", value) is not None,
        "full immutable lowercase revision required",
    )
    return R.oid(value)


def confirm(value):
    require(
        type(value) is str and value == CANDIDATE_DIGEST,
        "explicit confirmation of the exact fixed candidate digest required",
    )


def attest(revision):
    revision, head = oid(revision), core.git_head(ROOT)
    core.require_ancestor(ROOT, EVIDENCE_REVIEW, revision)
    core.require_ancestor(ROOT, revision, head)
    require(Path(__file__).resolve() == ROOT / SCRIPT, "entrypoint origin differs")
    R.public._origin(P, CANDIDATE_OPERATOR)
    files, snapshots = {}, []
    for relative in SOURCE_FILES:
        item = R.snapshot_file(ROOT / relative)
        R.reviewed_file(item, revision)
        files[relative] = dict(byte_count=len(item.raw), sha256=sha(item.raw))
        snapshots.append(item)
    for item in snapshots:
        item.revalidate()
    require(head == core.git_head(ROOT), "entrypoint attestation HEAD changed")
    return digested(
        dict(
            schema_version=DOMAIN + "/source",
            implementation_revision=revision,
            candidate_digest=CANDIDATE_DIGEST,
            candidate_evidence_review_revision=EVIDENCE_REVIEW,
            coordinator_revision=P.COORDINATOR_REVISION,
            coordinator_source_digest=P.COORDINATOR_DIGEST,
            preparer_revision=PREPARER_REVISION,
            preparer_source_digest=PREPARER_DIGEST,
            files=files,
        )
    )


def preflight_receipt(source):
    return digested(
        dict(
            schema_version=DOMAIN + "/preflight",
            status="ENTRYPOINT_PREFLIGHT_PASS_METADATA_ONLY_NOT_AUTHORIZED",
            entrypoint_source=source,
            authorization_path=str(C.authorization_for(S.REPLICATION)),
            authorization_digest=CANDIDATE_DIGEST,
            authorization_sha256=CANDIDATE_SHA256,
            candidate_evidence_review_revision=EVIDENCE_REVIEW,
            prior_candidate_admission_verification_digest=VERIFICATION_DIGEST,
            fixed_replication_claim_path=str(B.fixed_claim()),
            production_output_path=str(B.OUTPUT),
            original_claim_unoccupied_at_preflight=True,
            fresh_production_admission_performed=False,
            production_dispatch_exercised=False,
            production_adapter_executed=False,
            candidate_is_execution_authority=False,
            replication_execution_authorized=False,
            replication_search_calls=0,
            locked_128_evaluation_authorized=False,
            claim_boundary="source and reviewed-metadata preflight only; not fresh admission, production execution, or user digest approval",
        )
    )


@dataclass(frozen=True)
class Context:
    source_raw: bytes
    auth_raw: bytes
    preparer_raw: bytes
    coordinator_raw: bytes
    snapshots: tuple
    head: str
    reviewed: str | None

    @property
    def source(self):
        return parse(self.source_raw)

    @property
    def auth(self):
        return parse(self.auth_raw)

    def revalidate(self, *, full=False):
        for item in self.snapshots:
            item.revalidate()
        require(core.git_head(ROOT) == self.head, "entrypoint HEAD changed")
        require(
            canonical(S.parent_binding(B.OUTPUT))
            == canonical(self.auth["output_parent"]),
            "original output parent changed",
        )
        if full:
            require(
                canonical(attest(self.source["implementation_revision"]))
                == self.source_raw,
                "entrypoint source changed",
            )
            require(
                canonical(P.attest(PREPARER_REVISION)) == self.preparer_raw,
                "candidate operator source changed",
            )
            require(
                canonical(C.attest(P.COORDINATOR_REVISION)) == self.coordinator_raw,
                "qualified coordinator source changed",
            )
            for item in self.snapshots:
                item.revalidate()
            require(core.git_head(ROOT) == self.head, "entrypoint HEAD changed")


def context(revision, reviewed=None):
    source, head = attest(revision), core.git_head(ROOT)
    if reviewed is not None:
        reviewed = oid(reviewed)
        core.require_ancestor(ROOT, source["implementation_revision"], reviewed)
        core.require_ancestor(ROOT, reviewed, head)
    preparer = P.attest(PREPARER_REVISION)
    require(
        preparer["deterministic_digest"] == PREPARER_DIGEST,
        "fixed preparer source required",
    )
    coordinator = C.attest(P.COORDINATOR_REVISION)
    require(
        coordinator["deterministic_digest"] == P.COORDINATOR_DIGEST,
        "fixed coordinator source required",
    )
    snapshots = []
    for receipt, rev in (
        (source, source["implementation_revision"]),
        (preparer, PREPARER_REVISION),
        (coordinator, P.COORDINATOR_REVISION),
    ):
        for relative, metadata in receipt["files"].items():
            item = R.snapshot_file(ROOT / relative)
            R.reviewed_file(item, rev)
            require(
                len(item.raw) == metadata["byte_count"]
                and sha(item.raw) == metadata["sha256"],
                "source receipt bytes differ",
            )
            if reviewed is not None:
                R.reviewed_file(item, reviewed)
            snapshots.append(item)
    raw = R.snapshot_file(P.RAW_AUTH)
    promoted = R.snapshot_file(C.authorization_for(S.REPLICATION))
    preparation = R.snapshot_file(ROOT / P.PREPARATION_MIRROR)
    verification = R.snapshot_file(ROOT / VERIFICATION)
    for item in (promoted, preparation, verification):
        R.reviewed_file(item, EVIDENCE_REVIEW)
        if reviewed is not None:
            R.reviewed_file(item, reviewed)
    require(
        raw.raw == promoted.raw and sha(promoted.raw) == CANDIDATE_SHA256,
        "exact raw/promoted candidate required",
    )
    auth = P.candidate_shape(promoted.raw)
    require(
        auth["deterministic_digest"] == CANDIDATE_DIGEST, "fixed candidate required"
    )
    require(
        canonical(auth["coordinator_source"]) == canonical(coordinator),
        "candidate coordinator source differs",
    )
    require(
        preparation.raw == canonical(P.preparation_receipt(auth, preparer)),
        "original preparation receipt differs",
    )
    verified = parse(verification.raw)
    core.require_digest(verified)
    require(
        verified["deterministic_digest"] == VERIFICATION_DIGEST
        and verified["status"]
        == "RECEIVER_V2_CANDIDATE_INDEPENDENTLY_RECONSTRUCTED_NOT_AUTHORIZED"
        and verified["authorization_digest"] == CANDIDATE_DIGEST
        and verified["authorization_sha256"] == CANDIDATE_SHA256
        and verified["preparation_digest"]
        == parse(preparation.raw)["deterministic_digest"]
        and verified["reviewed_revision"] == CANDIDATE_REVIEW
        and canonical(verified["operator_source"]) == canonical(preparer)
        and verified["production_admission_verified"] is True
        and verified["production_adapter_executed"] is False
        and verified["replication_execution_authorized"] is False,
        "fixed prior candidate admission evidence required",
    )
    snapshots.extend((raw, promoted, preparation, verification))
    snapshots.extend(P.public_snapshots())
    if reviewed is not None:
        preflight = R.snapshot_file(ROOT / PREFLIGHT)
        R.reviewed_file(preflight, reviewed)
        require(
            preflight.raw == canonical(preflight_receipt(source)),
            "reviewed entrypoint preflight differs",
        )
        snapshots.append(preflight)
    value = Context(
        canonical(source),
        promoted.raw,
        canonical(preparer),
        canonical(coordinator),
        tuple(snapshots),
        head,
        reviewed,
    )
    value.revalidate(full=True)
    return value


def preflight(revision):
    C.unused(S.REPLICATION)
    S.descriptor_preflight()
    ctx = context(revision)
    require(
        ctx.head == ctx.source["implementation_revision"],
        "preflight at frozen implementation HEAD",
    )
    C.unused(S.REPLICATION)
    ctx.revalidate()
    return preflight_receipt(ctx.source)


def check_reviewed(revision, reviewed):
    reviewed = oid(reviewed)
    C.unused(S.REPLICATION)
    S.descriptor_preflight()
    ctx = context(revision, reviewed)
    C.unused(S.REPLICATION)
    ctx.revalidate()
    return digested(
        dict(
            schema_version=DOMAIN + "/reviewed-check",
            status="ENTRYPOINT_REVIEWED_CHECK_PASS_METADATA_ONLY_NOT_AUTHORIZED",
            entrypoint_source=ctx.source,
            entrypoint_review_revision=ctx.reviewed,
            preflight_digest=preflight_receipt(ctx.source)["deterministic_digest"],
            authorization_digest=CANDIDATE_DIGEST,
            original_claim_unoccupied=True,
            fresh_production_admission_performed=False,
            production_dispatch_exercised=False,
            production_adapter_executed=False,
            replication_execution_authorized=False,
            replication_search_calls=0,
            locked_128_evaluation_authorized=False,
            claim_boundary="reviewed source and metadata only; genuine admission is repeated by the coordinator only after explicit run confirmation",
        )
    )


def dispatch(command, revision, reviewed, confirmed, observe, state):
    require(
        command in ("run", "analyze", "verify"), "closed production command required"
    )
    if command == "run":
        confirm(confirmed)  # Never derive consent from a candidate or receipt.
        C.unused(S.REPLICATION)
    else:
        require(confirmed is None, "analysis/verification cannot confirm execution")
    reviewed = oid(reviewed)
    S.descriptor_preflight()
    ctx = context(revision, reviewed)
    ctx.revalidate(full=True)

    def progress(stage):
        ctx.revalidate()
        observe(stage)

    if command == "run":
        C.unused(S.REPLICATION)
        state["run_entered"] = True
        value = C.run(
            S.REPLICATION,
            C.authorization_for(S.REPLICATION),
            confirmed,
            ctx.reviewed,
            progress,
        )
        state["run_returned"] = True
    else:
        operation = C.analyze_and_save if command == "analyze" else C.verify
        value = operation(S.REPLICATION, progress)
    ctx.revalidate(full=True)
    core.require_digest(value)
    common = dict(
        schema_version=DOMAIN + "/operation-result",
        entrypoint_source=ctx.source,
        entrypoint_review_revision=ctx.reviewed,
        authorization_digest=CANDIDATE_DIGEST,
        preflight_digest=preflight_receipt(ctx.source)["deterministic_digest"],
        future_execution_authorized=False,
        locked_128_evaluation_authorized=False,
    )
    if command == "run":
        return digested(
            dict(
                **common,
                status="REPLICATION_EXECUTION_COMMITTED",
                output_path=str(B.OUTPUT),
                commit_digest=value["deterministic_digest"],
                authorization_consumed=True,
                production_adapter_executed=True,
                claim_boundary="one confirmed coordinator execution committed; analyze and verify saved evidence separately; no retry or further execution authority",
            )
        )
    require(
        value["authorization_digest"] == CANDIDATE_DIGEST
        and value["execution_mode"] == S.REPLICATION
        and value["production_adapter_executed"] is True,
        "analysis belongs to a different production candidate",
    )
    return digested(
        dict(
            **common,
            status="REPLICATION_SUMMARY_SAVED"
            if command == "analyze"
            else "REPLICATION_SUMMARY_INDEPENDENTLY_VERIFIED",
            summary_path=str(C.REPLICATION_SUMMARY),
            summary_digest=value["deterministic_digest"],
            new_replication_search_calls=0,
            historical_replication_cells_executed=value["replication_cells_executed"],
            source_multiset_count=value["source_multiset_count"],
            scientific_decision=value["scientific_decision"],
            claim_boundary="no new search; replay committed evidence and exclusively save a summary for analyze, read-only saved-summary replay for verify; does not prove historical wrapper usage or authorize another execution",
        )
    )


def self_test():
    require(
        C.output_for(S.REPLICATION) == B.OUTPUT, "original production output changed"
    )
    require(
        C.authorization_for(S.REPLICATION) != ROOT / B.CANDIDATE,
        "v1 candidate would be used",
    )
    return digested(
        dict(
            status="PRODUCTION_ENTRYPOINT_STATIC_SELF_TEST_PASS",
            authorization_digest=CANDIDATE_DIGEST,
            replication_execution_authorized=False,
            replication_search_calls=0,
            claim_boundary="static fixed identities only; no runtime admission or production dispatch",
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    modes = parser.add_mutually_exclusive_group(required=True)
    for mode in ("self-test", "preflight", "check", "run", "analyze", "verify"):
        modes.add_argument("--" + mode, action="store_true")
    for name in ("implementation-revision", "reviewed-revision", "confirm-digest"):
        parser.add_argument("--" + name)
    args = vars(parser.parse_args())
    command = next(
        name
        for name in ("self_test", "preflight", "check", "run", "analyze", "verify")
        if args[name]
    )
    required = {
        "self_test": set(),
        "preflight": {"implementation_revision"},
        "check": {"implementation_revision", "reviewed_revision"},
        "run": {"implementation_revision", "reviewed_revision", "confirm_digest"},
        "analyze": {"implementation_revision", "reviewed_revision"},
        "verify": {"implementation_revision", "reviewed_revision"},
    }[command]
    supplied = {
        name
        for name in ("implementation_revision", "reviewed_revision", "confirm_digest")
        if args[name] is not None
    }
    if supplied != required:
        parser.error(
            "exact mode-specific arguments required; no path, mode, seed or retry overrides"
        )
    completed = False
    state = dict(run_entered=False, run_returned=False)

    def observe(stage):
        print(stage, file=sys.stderr, flush=True)

    try:
        if command == "self_test":
            result = self_test()
        elif command == "preflight":
            result = preflight(args["implementation_revision"])
        elif command == "check":
            result = check_reviewed(
                args["implementation_revision"], args["reviewed_revision"]
            )
        else:
            result = dispatch(
                command,
                args["implementation_revision"],
                args["reviewed_revision"],
                args["confirm_digest"],
                observe,
                state,
            )
        completed = True
        sys.stdout.buffer.write(canonical(result))
        sys.stdout.buffer.flush()
    except BaseException as error:
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
        consumed = True if state["run_returned"] else None
        if completed:
            status = "RESULT_DELIVERY_UNCERTAIN"
        elif state["run_returned"]:
            # A later checker cannot downgrade a known committed run to unspent.
            status = "DISPATCH_RETURNED_REVALIDATION_FAILED"
        elif isinstance(error, S.ExecutionFailure):
            status, consumed = error.status, error.authorization_consumed
        elif isinstance(error, S.base.PublicationUncertain):
            status = "PUBLICATION_UNCERTAIN"
        else:
            status = "ENTRYPOINT_OPERATION_FAILED"
        print(str(error), file=sys.stderr)
        try:
            sys.stdout.buffer.write(
                canonical(
                    digested(
                        dict(
                            status=status,
                            authorization_consumed=consumed,
                            run_dispatch_entered=state["run_entered"],
                            coordinator_run_returned=state["run_returned"],
                            new_replication_search_calls=None
                            if state["run_entered"]
                            else 0,
                            automatic_retry_allowed=False,
                            future_execution_authorized=False,
                            locked_128_evaluation_authorized=False,
                            claim_boundary="retain every occupied claim/output/summary; failed or uncertain delivery is not evidence that execution did not occur",
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
