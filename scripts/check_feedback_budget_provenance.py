#!/usr/bin/env python3
"""Check public receipt ancestry in a committed Git tree, without running search.

This is a merge/retrieval guard, not source/runtime attestation or trace replay.
Use a complete clone and preserve the producing commits when merging evidence.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
QUALIFICATION_PATHS = (
    ("source", "qualification_revision"),
    ("source", "package_source", "runner_revision"),
)
RECEIPTS = {
    "docs/qualifications/countdown_feedback_budget_v6_public_20260905.json": QUALIFICATION_PATHS,
    "docs/qualifications/countdown_feedback_budget_v6_public_revalidated_20260905.json": QUALIFICATION_PATHS,
    "docs/qualifications/countdown_feedback_budget_v6_full_shape_20260905.summary.json": (
        ("source", "execution_revision"),
        ("source", "public_qualification_source", "qualification_revision"),
        ("source", "public_qualification_source", "package_source", "runner_revision"),
    ),
    "docs/qualifications/countdown_feedback_budget_v6_development_path_20260910.summary.json": (
        ("source", "execution_revision"),
        ("source", "public_qualification_source", "qualification_revision"),
        ("source", "public_qualification_source", "package_source", "runner_revision"),
    ),
    "docs/qualifications/countdown_feedback_budget_v6_admission_20260910.json": (
        ("admission_context", "source", "admission_revision"),
        ("admission_context", "source", "public_path_source", "execution_revision"),
        (
            "admission_context",
            "source",
            "public_path_source",
            "public_qualification_source",
            "qualification_revision",
        ),
        (
            "admission_context",
            "source",
            "public_path_source",
            "public_qualification_source",
            "package_source",
            "runner_revision",
        ),
    ),
    "docs/qualifications/countdown_feedback_budget_v6_connector_20260910.summary.json": (
        ("environment", "source", "execution_revision"),
        ("environment", "source", "admission_source", "admission_revision"),
        (
            "environment",
            "source",
            "admission_source",
            "public_path_source",
            "execution_revision",
        ),
        (
            "environment",
            "source",
            "admission_source",
            "public_path_source",
            "public_qualification_source",
            "qualification_revision",
        ),
        (
            "environment",
            "source",
            "admission_source",
            "public_path_source",
            "public_qualification_source",
            "package_source",
            "runner_revision",
        ),
    ),
}


class ProvenanceError(ValueError):
    """A published producing revision is unavailable or outside the ancestry."""


def git(root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "--no-replace-objects", "-C", str(root), *args],
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise ProvenanceError(f"Git ancestry check failed: {' '.join(args)}")
    return result.stdout


def commit_oid(root: Path, value: object) -> str:
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise ProvenanceError("producing revision must be a full lowercase commit OID")
    if git(root, "cat-file", "-t", value) != b"commit\n":
        raise ProvenanceError("producing revision must identify a commit")
    return value


def revisions(receipt: object, paths: tuple) -> list[str]:
    values = []
    for path in paths:
        value = receipt
        for key in path:
            if type(value) is not dict or key not in value:
                raise ProvenanceError(f"missing revision field: {'.'.join(path)}")
            value = value[key]
        values.append(value)
    if any(value != values[0] for value in values[1:]):
        raise ProvenanceError("nested producing revisions disagree")
    return values


def verify(root: Path, revision: str | None = None) -> dict:
    head = commit_oid(root, revision or git(root, "rev-parse", "HEAD").decode().strip())
    if git(root, "rev-parse", "--is-shallow-repository") != b"false\n":
        raise ProvenanceError("complete Git history required; fetch full history first")
    rows = []
    for relative, paths in RECEIPTS.items():
        entry = git(root, "ls-tree", "-z", head, "--", relative)
        if (
            not entry.startswith(b"100644 blob ")
            or entry.count(b"\x00") != 1
            or not entry.endswith(b"\t" + relative.encode() + b"\x00")
        ):
            raise ProvenanceError(f"missing or non-regular tracked receipt: {relative}")
        try:
            receipt = json.loads(git(root, "show", f"{head}:{relative}"))
        except (ValueError, UnicodeError) as error:
            raise ProvenanceError(f"invalid receipt JSON: {relative}") from error
        producing = commit_oid(root, revisions(receipt, paths)[0])
        try:
            git(root, "merge-base", "--is-ancestor", producing, head)
        except ProvenanceError as error:
            raise ProvenanceError(
                f"{relative}: producing revision {producing} is not an ancestor of "
                f"{head}; preserve history with a merge commit, not squash/rebase"
            ) from error
        rows.append(dict(receipt=relative, producing_revision=producing))
    return dict(
        status="PUBLIC_RECEIPT_ANCESTRY_PASS",
        checked_revision=head,
        receipts=rows,
        trace_replay_performed=False,
        development_execution_authorized=False,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", help="full commit OID; defaults to HEAD")
    args = parser.parse_args()
    print(
        json.dumps(verify(ROOT, args.revision), sort_keys=True, separators=(",", ":"))
    )


if __name__ == "__main__":
    main()
