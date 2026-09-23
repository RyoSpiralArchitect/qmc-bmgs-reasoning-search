#!/usr/bin/env python3
"""Prepare and independently review one receiver-v2 replication candidate.

This additive operator has no execution/consumption entry point. The qualified
coordinator and original study remain unchanged. A candidate and its successful
admission review are not permission to search the sealed tasks.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = "scripts/feedback_budget_receiver_candidate.py"
TEST = "tests/test_feedback_budget_receiver_candidate.py"
POLICY = "docs/strategy/countdown_feedback_budget_receiver_v2_candidate.md"
COORDINATOR = "scripts/feedback_budget_receiver_execution.py"
COORDINATOR_REVISION = "c0b048e401d39802c46acd70060ad9af27b0a911"
COORDINATOR_DIGEST = "680caead90bb00f483eafc86ba75e67703b57014457d3834f0e772409a6ac329"
PUBLIC_REVIEW = "ba51b631d6398d0813a36614b3d27821d019162e"
PUBLIC_SUMMARY_DIGEST = (
    "a85537a8b496a4a39be765686eda8d9e26fd9b66df252125a5a8ba1df86e7757"
)
PUBLIC_VERIFICATION = "docs/qualifications/countdown_feedback_budget_receiver_v2_public_20260922.verification.json"
PREPARATION_MIRROR = "docs/qualifications/countdown_feedback_budget_receiver_v2_candidate_20260923.preparation.json"
SPEC = importlib.util.spec_from_file_location(
    "receiver_candidate_coordinator", ROOT / COORDINATOR
)
assert SPEC is not None and SPEC.loader is not None
C = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = C
SPEC.loader.exec_module(C)
B, R, S, core = C.B, C.R, C.S, C.core
canonical, parse, require, digested, sha = (
    C.canonical,
    C.parse,
    C.require,
    C.digested,
    C.sha,
)
DOMAIN = C.DOMAIN + "/candidate-preparation/v1"
SOURCE_FILES = (SCRIPT, TEST, POLICY)
RAW_AUTH = Path(str(B.OUTPUT) + ".receiver-v2.authorization.json")


def attest(revision):
    revision, head = R.oid(revision), core.git_head(ROOT)
    core.require_ancestor(ROOT, PUBLIC_REVIEW, revision)
    core.require_ancestor(ROOT, revision, head)
    require(
        Path(__file__).resolve() == ROOT / SCRIPT, "candidate operator origin differs"
    )
    R.public._origin(C, COORDINATOR)
    files, snapshots = {}, []
    for relative in SOURCE_FILES:
        item = R.snapshot_file(ROOT / relative)
        R.reviewed_file(item, revision)
        files[relative] = dict(byte_count=len(item.raw), sha256=sha(item.raw))
        snapshots.append(item)
    for item in snapshots:
        item.revalidate()
    require(head == core.git_head(ROOT), "candidate operator HEAD changed")
    return digested(
        dict(
            schema_version=DOMAIN + "/source",
            implementation_revision=revision,
            coordinator_revision=COORDINATOR_REVISION,
            coordinator_source_digest=COORDINATOR_DIGEST,
            public_qualification_review_revision=PUBLIC_REVIEW,
            files=files,
        )
    )


def candidate_shape(raw):
    value = parse(raw)
    C.auth_shape(raw, S.REPLICATION, value.get("deterministic_digest"))
    require(
        value["coordinator_source"].get("implementation_revision")
        == COORDINATOR_REVISION
        and value["coordinator_source"].get("deterministic_digest")
        == COORDINATOR_DIGEST,
        "frozen qualified coordinator source required",
    )
    qualifier = value["connector_qualification"]
    require(
        type(qualifier) is dict
        and qualifier.get("summary_digest") == PUBLIC_SUMMARY_DIGEST
        and qualifier.get("source_digest") == COORDINATOR_DIGEST,
        "fixed reviewed PUBLIC qualification required",
    )
    return value


def public_snapshots():
    reviewed = tuple(
        R.snapshot_file(ROOT / relative)
        for relative in (
            C.SUMMARY_MIRROR,
            C.COMMIT_MIRROR,
            PUBLIC_VERIFICATION,
        )
    )
    for item in reviewed:
        R.reviewed_file(item, PUBLIC_REVIEW)
    saved = R.snapshot_file(C.PUBLIC_SUMMARY)
    require(
        saved.raw == reviewed[0].raw, "saved PUBLIC summary differs from reviewed bytes"
    )
    verification = parse(reviewed[2].raw)
    core.require_digest(verification)
    require(
        verification.get("status") == "PUBLIC_SUMMARY_INDEPENDENTLY_VERIFIED"
        and verification.get("summary_digest") == PUBLIC_SUMMARY_DIGEST
        and verification.get("replication_execution_authorized") is False
        and verification.get("scientific_decision") is None,
        "reviewed independent PUBLIC verification required",
    )
    return reviewed + (saved,)


def preparation_receipt(auth, source):
    raw = canonical(auth)
    return digested(
        dict(
            schema_version=DOMAIN + "/preparation",
            status="RECEIVER_V2_CANDIDATE_PREPARED_NOT_AUTHORIZED",
            authorization_path=str(RAW_AUTH),
            promoted_authorization_path=str(C.authorization_for(S.REPLICATION)),
            authorization_digest=auth["deterministic_digest"],
            authorization_byte_count=len(raw),
            authorization_sha256=sha(raw),
            operator_source=source,
            coordinator_source_digest=COORDINATOR_DIGEST,
            public_qualification_review_revision=PUBLIC_REVIEW,
            public_qualification=auth["connector_qualification"],
            input_manifest_digest=auth["input_manifest_digest"],
            fixed_replication_claim_path=str(B.fixed_claim()),
            original_claim_unoccupied=True,
            candidate_is_execution_authority=False,
            production_adapter_executed=False,
            replication_execution_authorized=False,
            replication_search_calls=0,
            locked_128_evaluation_authorized=False,
            claim_boundary="prepared metadata only; reviewed candidate and explicit exact-digest execution confirmation remain separate gates",
        )
    )


def unoccupied_preparation():
    C.unused(S.REPLICATION)
    for path in (
        RAW_AUTH,
        C.authorization_for(S.REPLICATION),
        ROOT / PREPARATION_MIRROR,
    ):
        require(
            not os.path.lexists(path),
            "candidate or preparation slot occupied; no overwrite/adoption",
        )


def prepare(revision, observe=lambda stage: None):
    unoccupied_preparation()
    S.descriptor_preflight()
    source = attest(revision)
    head = core.git_head(ROOT)
    require(
        head == source["implementation_revision"],
        "prepare at frozen operator implementation HEAD",
    )
    snapshots = public_snapshots()
    coordinator_source = C.attest(COORDINATOR_REVISION)
    require(
        coordinator_source["deterministic_digest"] == COORDINATOR_DIGEST,
        "qualified source differs",
    )
    qualifier, qualifier_check = C.qualified_public(
        PUBLIC_REVIEW, coordinator_source, observe
    )
    observe("REVIEWED_RECEIVER_PUBLIC_QUALIFICATION_RECONSTRUCTED")
    base = C.receiver_admit(observe)
    inputs = base.inputs
    manifest = inputs.manifest
    require(
        manifest["execution_mode"] == S.REPLICATION
        and manifest["task_count"] == 64
        and manifest["source_multiset_count"] == 64
        and manifest["cell_count"] == 1024,
        "original sealed 64-source input shape required",
    )
    auth = candidate_shape(
        canonical(
            C.candidate(S.REPLICATION, inputs, base, coordinator_source, qualifier)
        )
    )

    def check():
        C.unused(S.REPLICATION)
        require(
            not os.path.lexists(C.authorization_for(S.REPLICATION)),
            "promoted candidate appeared",
        )
        require(
            not os.path.lexists(ROOT / PREPARATION_MIRROR),
            "preparation mirror appeared",
        )
        require(head == core.git_head(ROOT), "preparation HEAD changed")
        require(
            canonical(attest(revision)) == canonical(source),
            "candidate operator source changed",
        )
        for item in snapshots:
            item.revalidate()
        qualifier_check()
        base.revalidate()
        require(
            canonical(S.parent_binding(B.OUTPUT)) == canonical(auth["output_parent"]),
            "candidate output parent changed",
        )

    unoccupied_preparation()
    S.base._publish_summary(RAW_AUTH, auth, check)
    return preparation_receipt(auth, source)


def verify_candidate(revision, reviewed, observe=lambda stage: None):
    C.unused(S.REPLICATION)
    source = attest(revision)
    reviewed, head = R.oid(reviewed), core.git_head(ROOT)
    core.require_ancestor(ROOT, source["implementation_revision"], reviewed)
    core.require_ancestor(ROOT, reviewed, head)
    raw_snapshot = R.snapshot_file(RAW_AUTH)
    promoted = R.snapshot_file(C.authorization_for(S.REPLICATION))
    preparation = R.snapshot_file(ROOT / PREPARATION_MIRROR)
    for item in (promoted, preparation):
        R.reviewed_file(item, reviewed)
    require(raw_snapshot.raw == promoted.raw, "raw/promoted candidate bytes differ")
    auth = candidate_shape(promoted.raw)
    require(
        preparation.raw == canonical(preparation_receipt(auth, source)),
        "reviewed preparation receipt differs",
    )
    snapshots = public_snapshots()
    # Genuine frozen production admission, not execution or digest approval.
    admitted = C.admit(
        S.REPLICATION,
        promoted.path,
        auth["deterministic_digest"],
        reviewed,
        observe=observe,
    )
    require(
        canonical(admitted.auth) == promoted.raw,
        "independent candidate reconstruction differs",
    )
    admitted.revalidate()
    for item in (raw_snapshot, promoted, preparation) + snapshots:
        item.revalidate()
    require(
        canonical(attest(revision)) == canonical(source),
        "candidate operator source changed",
    )
    require(head == core.git_head(ROOT), "candidate verification HEAD changed")
    C.unused(S.REPLICATION)
    return digested(
        dict(
            schema_version=DOMAIN + "/verification",
            status="RECEIVER_V2_CANDIDATE_INDEPENDENTLY_RECONSTRUCTED_NOT_AUTHORIZED",
            authorization_digest=auth["deterministic_digest"],
            authorization_sha256=sha(promoted.raw),
            preparation_digest=parse(preparation.raw)["deterministic_digest"],
            reviewed_revision=reviewed,
            operator_source=source,
            public_qualification_review_revision=PUBLIC_REVIEW,
            coordinator_source_digest=COORDINATOR_DIGEST,
            production_admission_verified=True,
            production_adapter_executed=False,
            original_claim_unoccupied=True,
            candidate_is_execution_authority=False,
            replication_execution_authorized=False,
            replication_search_calls=0,
            locked_128_evaluation_authorized=False,
            claim_boundary="read-only independent production admission only; no consumption, production run, or exact-digest execution approval",
        )
    )


def self_test():
    require(
        RAW_AUTH != B.ORIGINAL_RAW and RAW_AUTH != C.RAW_AUTH,
        "candidate raw namespaces overlap",
    )
    require(C.output_for(S.REPLICATION) == B.OUTPUT, "fixed production output changed")
    require(
        C.authorization_for(S.REPLICATION) != ROOT / B.CANDIDATE,
        "v1 candidate would be replaced",
    )
    return dict(
        status="CANDIDATE_ONLY_STATIC_SELF_TEST_PASS",
        replication_execution_authorized=False,
        replication_search_calls=0,
        claim_boundary="static identities only; no candidate or execution qualification",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    modes = parser.add_mutually_exclusive_group(required=True)
    for name in ("self-test", "prepare", "verify-candidate"):
        modes.add_argument("--" + name, action="store_true")
    parser.add_argument("--implementation-revision")
    parser.add_argument("--reviewed-revision")
    args = parser.parse_args()
    command = (
        "prepare"
        if args.prepare
        else "verify"
        if args.verify_candidate
        else "self_test"
    )
    required = {
        "self_test": set(),
        "prepare": {"implementation_revision"},
        "verify": {"implementation_revision", "reviewed_revision"},
    }[command]
    supplied = {
        name
        for name in ("implementation_revision", "reviewed_revision")
        if getattr(args, name) is not None
    }
    if supplied != required:
        parser.error("exact mode-specific arguments required; no execution mode exists")
    completed = False

    def observe(stage):
        print(stage, file=sys.stderr, flush=True)

    try:
        if command == "prepare":
            result = prepare(args.implementation_revision, observe)
        elif command == "verify":
            result = verify_candidate(
                args.implementation_revision, args.reviewed_revision, observe
            )
        else:
            result = digested(self_test())
        completed = True
        sys.stdout.buffer.write(canonical(result))
        sys.stdout.buffer.flush()
    except BaseException as error:
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
        status = (
            "RESULT_DELIVERY_UNCERTAIN"
            if completed
            else (
                "CANDIDATE_PUBLICATION_UNCERTAIN"
                if isinstance(error, S.base.PublicationUncertain)
                else "CANDIDATE_PREPARATION_OR_REVIEW_FAILED"
            )
        )
        print(str(error), file=sys.stderr)
        try:
            sys.stdout.buffer.write(
                canonical(
                    digested(
                        dict(
                            status=status,
                            authorization_consumed=None,
                            automatic_retry_allowed=False,
                            replication_execution_authorized=False,
                            replication_search_calls=0,
                            claim_boundary="retain all occupied candidate/claim state; failure is not permission to retry",
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
