#!/usr/bin/env python3
"""Additive, one-attempt recovery of saved allocation data; never runs a study.

The original runner, source, plan, raw data and interrupted attempt stay fixed.
--manifest is read-only. Recovery requires a separately qualified candidate and
an explicit human-authorization record. CLI arguments are not human approval.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from datetime import datetime, timezone
import hashlib
import importlib.util
import os
from pathlib import Path
import re
import resource
import stat
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "frozen_allocation_recovery_dependency",
    ROOT / "scripts/run_feedback_allocation_development.py",
)
D = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(D)
BASE = "35f3b1ba0342406914c0670d2e263d088df513a2"
PLAN_DIGEST = "d88244d33e61f83bf878e77e3827ae3633ca6db08adb7f846a64631310f361e9"
E = "artifacts/work/feedback-allocation-development-execution-20261023"
Q = "artifacts/work/feedback-allocation-development-qualification-20261023"
R = "artifacts/work/feedback-allocation-review-20261023"
DIAG = "artifacts/work/feedback-allocation-recovery-diagnosis-20261023"
OUTPUT = "artifacts/work/feedback-allocation-analysis-recovery-20261024-a"
SOURCE_PATHS = (
    "scripts/recover_feedback_allocation_analysis.py",
    "tests/test_feedback_allocation_recovery.py",
    "docs/strategy/countdown_feedback_allocation_recovery_20261024.md",
)
ANCHORS = {
    E
    + "/inventory.json": "4fd107a1e12761d8034aa8402a956b1881dec188ad097378951980f179284ce8",
    E
    + "/run.process.json": "58d032533f88d6a65a11a37c31aa43d7e0cc59ffaf2b50eed219bed7e6a4d850",
    D.OUTPUT
    + "/COMMIT.json": "6e16a5f52cce793fb372830f5f69a31b49d8d2478f128d2af7d4f7996c905d5e",
    R
    + "/analysis.interruption.json": "b38ee197932db6ab9f848ac54f56ac9a2efc5ed4a489dbd3b97f798923f1ce79",
    DIAG
    + "/diagnosis.json": "bfa10ba539be2fad5b49d72eb986d8665b7b62fe7f6dab368cf87862894515f6",
}


def now():
    return datetime.now(timezone.utc).isoformat()


def safe_path(name):
    path = Path(name)
    D.require(
        type(name) is str
        and not path.is_absolute()
        and path.as_posix() == name
        and ".." not in path.parts
        and name != ".",
        "canonical relative path required",
    )
    current = ROOT
    D.require(not current.is_symlink(), "root symlink refused")
    for part in path.parts:
        current /= part
        D.require(not current.is_symlink(), "symlink component refused")
    return current


def read(name):
    path = safe_path(name)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        D.require(
            stat.S_ISREG(os.fstat(stream.fileno()).st_mode), "regular file required"
        )
        return stream.read()


def ref(name):
    raw = read(name)
    return dict(path=name, byte_count=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def check(row):
    actual = ref(row["path"])
    D.require(
        set(row) <= {"path", "byte_count", "sha256", "mode"}
        and type(row["byte_count"]) is int
        and all(actual[k] == row[k] for k in actual),
        "reference mismatch: " + row["path"],
    )
    if "mode" in row:
        D.require(
            stat.S_IMODE(safe_path(row["path"]).stat().st_mode) == row["mode"],
            "file mode changed",
        )


def load(name):
    return D.strict_json_loads(read(name).decode())


def canonical_digest(name):
    raw = read(name)
    value = D.strict_json_loads(raw.decode())
    D.require(type(value) is dict and "deterministic_digest" in value, "digest missing")
    core = {k: v for k, v in value.items() if k != "deterministic_digest"}
    D.require(
        raw == D.canonical_trace_bytes(D.digested(core)), "canonical digest mismatch"
    )
    return value


def names(directory):
    path = safe_path(directory)
    D.require(path.is_dir(), "directory required")
    return sorted(str(p.relative_to(ROOT)) for p in path.iterdir())


def historical_slot(name):
    """Old inventories include two absolute paths; normalize only inside ROOT."""
    path = Path(name)
    relative = str(path.relative_to(ROOT)) if path.is_absolute() else name
    safe_path(relative)
    return relative


def check_manifest(manifest):
    D.require(
        manifest["original_head"] == BASE and manifest["output"] == OUTPUT,
        "recovery target changed",
    )
    for path, sha in ANCHORS.items():
        D.require(ref(path)["sha256"] == sha, "historical anchor changed")
    D.checked_plan(PLAN_DIGEST)
    D.require(
        [ref(p) for p in SOURCE_PATHS] == manifest["recovery_source"],
        "recovery source changed",
    )
    for row in manifest["frozen"]:
        check(row)
    for path, expected in manifest["membership"].items():
        D.require(names(path) == expected, "directory membership changed: " + path)
    for path in manifest["absent"]:
        D.require(not os.path.lexists(safe_path(path)), "absent slot changed: " + path)
    return dict(
        frozen_files=len(manifest["frozen"]),
        directories=len(manifest["membership"]),
        absent=len(manifest["absent"]),
    )


def build_manifest():
    """Inventory and binding only: no generation, replay or result reduction."""
    D.require(not os.path.lexists(safe_path(OUTPUT)), "recovery already attempted")
    plan = D.checked_plan(PLAN_DIGEST)
    inv = load(E + "/inventory.json")
    interruption = load(R + "/analysis.interruption.json")
    run = load(E + "/run.process.json")
    D.require(
        run["exit_code"] == 0
        and run["postflight_pass"] is True
        and run["postconditions_errors"] == []
        and run["before"] == run["after"],
        "original run not verified",
    )
    D.require(
        interruption["analysis_completion_verified"] is False
        and interruption["analysis_exit_code"] is None,
        "interruption changed",
    )
    rows = inv["tracked"] + inv["protected"] + inv["qualification"]
    frozen = {}
    for row in rows:
        check(row)
        frozen[row["path"]] = ref(row["path"])
    membership = dict(inv["membership"])
    for directory in (E, Q, R, DIAG, D.OUTPUT):
        membership[directory] = names(directory)
        for path in membership[directory]:
            frozen[path] = ref(path)
    manifest = D.digested(
        dict(
            schema="allocation-analysis-recovery/v1",
            original_head=BASE,
            plan=ref(D.PLAN_FILE),
            plan_digest=PLAN_DIGEST,
            output=OUTPUT,
            recovery_source=[ref(p) for p in SOURCE_PATHS],
            frozen=[frozen[p] for p in sorted(frozen)],
            membership=membership,
            absent=sorted(
                set(
                    [historical_slot(p) for p in inv["absent_original_slots"]]
                    + [E + "/analyze.process.json", D.OUTPUT + "/summary.json"]
                )
            ),
            cells=plan["planned_cells"],
            branches=plan["planned_branch_runs"],
            detailed_cache_cell_limit=3,
            original_attempt_completion="UNKNOWN",
            reboot_trigger="UNKNOWN",
            experiment_rerun=False,
            resume=False,
            automatic_retry=False,
            authorization="external_delegated_selection_record_and_qualified_commit_required",
        )
    )
    check_manifest(manifest)
    checked_commit()
    return manifest


def checked_commit():
    c = canonical_digest(D.OUTPUT + "/COMMIT.json")
    D.require(
        set(c)
        == {
            "study_id",
            "plan_digest",
            "source_head",
            "started",
            "cohort",
            "cells",
            "cell_count",
            "status",
            "deterministic_digest",
        },
        "closed COMMIT fields required",
    )
    D.require(
        c["source_head"] == BASE
        and c["plan_digest"] == PLAN_DIGEST
        and c["study_id"] == D.STUDY
        and c["status"] == "COMPLETE_NOT_YET_INDEPENDENTLY_ANALYZED",
        "original operation binding mismatch",
    )
    keys = D.coordinates()
    D.require(
        type(c["cell_count"]) is int
        and c["cell_count"] == len(keys)
        and type(c["cells"]) is list
        and len(c["cells"]) == len(keys),
        "incomplete COMMIT",
    )
    for index, (key, row) in enumerate(zip(keys, c["cells"])):
        D.require(
            type(row) is dict
            and set(row) == {"index", "key", "file"}
            and type(row["index"]) is int
            and row["index"] == index
            and D.canonical_trace_bytes(row["key"])
            == D.canonical_trace_bytes(list(key))
            and row["file"]["path"] == f"{D.OUTPUT}/cell-{index:04d}.json",
            "cell coordinate/path mismatch",
        )
        check(row["file"])
    for key, filename in (("started", "STARTED.json"), ("cohort", "cohort.json")):
        D.require(
            c[key]["path"] == D.OUTPUT + "/" + filename,
            "COMMIT reference path mismatch",
        )
        check(c[key])
    started = canonical_digest(c["started"]["path"])
    D.require(
        started["plan_digest"] == PLAN_DIGEST
        and started["source_head"] == BASE
        and started["study_id"] == D.STUDY,
        "STARTED binding mismatch",
    )
    fence = canonical_digest(D.OUTPUT + "/analysis.STARTED.json")
    D.require(
        fence["plan_digest"] == PLAN_DIGEST
        and fence["source_head"] == BASE
        and fence["commit"] == ref(D.OUTPUT + "/COMMIT.json"),
        "interrupted analysis fence binding mismatch",
    )
    expected = {r["file"]["path"] for r in c["cells"]} | {
        D.OUTPUT + "/" + f
        for f in ("STARTED.json", "COMMIT.json", "cohort.json", "analysis.STARTED.json")
    }
    D.require(set(names(D.OUTPUT)) == expected, "original output membership mismatch")
    return c


class BoundedRecords(Mapping):
    """Re-read authenticated files; retain detailed objects for one block only.

    Callers must not retain detailed values from old blocks. Frozen reducers
    retain only compact summaries; prefix checks hold at most one 3-cell block.
    """

    def __init__(self, cells):
        self.refs = {tuple(r["key"]): r["file"] for r in cells}
        D.require(len(self.refs) == len(cells), "duplicate coordinates")
        self.cache = {}
        self.block = None
        self.peak_cached_cells = 0

    def __iter__(self):
        return iter(self.refs)

    def __len__(self):
        return len(self.refs)

    def raw(self, key):
        row = self.refs[key]
        raw = read(row["path"])
        D.require(
            len(raw) == row["byte_count"]
            and hashlib.sha256(raw).hexdigest() == row["sha256"],
            "cell bytes changed",
        )
        return raw

    def __getitem__(self, key):
        if key not in self.refs:
            raise KeyError(key)
        if key[:3] != self.block:
            self.cache.clear()
            self.block = key[:3]
        # Authenticate even cached reads, so a changed file cannot hide in cache.
        raw = self.raw(key)
        if key not in self.cache:
            self.cache[key] = D.strict_json_loads(raw.decode())
            self.peak_cached_cells = max(self.peak_cached_cells, len(self.cache))
            D.require(len(self.cache) <= 3, "detailed cache bound exceeded")
        return self.cache[key]


def execute_analysis(plan, commit, progress, guard):
    """Full replay from cell zero; never adopts progress of an earlier attempt."""
    cohort = load(commit["cohort"]["path"])
    progress("cohort_start", 0)
    D.require(
        D.canonical_trace_bytes(cohort)
        == D.canonical_trace_bytes(D.cohort_from_recipe(plan)),
        "cohort regeneration mismatch",
    )
    records = BoundedRecords(commit["cells"])
    branches = 0
    work = {axis: 0 for axis in D.TRACK_A_WORK_AXES}
    for i, key in enumerate(D.coordinates()):
        guard()
        raw = records.raw(key)
        D.replay_allocation_search_bytes(raw, **D.arguments(cohort, key))
        cell = records[key]
        D.require(cell["summary"]["budget_valid"] is True, "secondary guard bound")
        branches += len(cell["channels"])
        for axis in work:
            work[axis] += cell["summary"]["ledger_usage"][axis]
        del cell, raw
        if (i + 1) % 24 == 0 or i + 1 == len(records):
            progress("replay", i + 1)
    progress("prefixes", len(records))
    prefixes = D.check_prefixes(records)
    structure = D.check_structure(records)
    progress("reduction", len(records))
    reduction = D.reduce_results(plan, records)
    D.require(
        branches == plan["planned_branch_runs"]
        and prefixes == plan["planned_branch_prefix_pairs"]
        and structure == plan["planned_structural_blocks"],
        "incomplete replay",
    )
    return dict(
        prefix_pairs=prefixes,
        structural_blocks=structure,
        replayed_cells=len(records),
        replayed_branches=branches,
        work=work,
        reduction=reduction,
        peak_cached_detailed_cells=records.peak_cached_cells,
    )


def save(name, value):
    safe_path(name)
    return D.save_new(name, D.digested(value))


def recover(manifest_path, digest, candidate, approval_path, qualification_path):
    manifest = canonical_digest(manifest_path)
    D.require(
        manifest["deterministic_digest"] == digest, "exact recovery digest required"
    )
    D.require(D.clean_head() == candidate, "qualified clean candidate HEAD required")
    approval, qualification = load(approval_path), load(qualification_path)
    D.require(
        approval["candidate_commit"] == candidate
        and approval["recovery_digest"] == digest
        and approval["scope"] == "one_full_saved_data_recovery_analysis_no_experiment"
        and approval["authorization_mode"] == "delegated_candidate_selection"
        and approval["human_message"]
        == "そうね、候補決めるー＞全権実行->分析&ドキュメンテーション改善まで回してみよう🐈‍⬛🐈🐈🌀",
        "recovery authorization binding mismatch",
    )
    D.require(
        qualification["source_head"] == candidate
        and type(qualification["exit_code"]) is int
        and qualification["exit_code"] == 0
        and qualification["postflight_pass"] is True
        and qualification["postconditions_errors"] == []
        and qualification["before"] == qualification["after"],
        "candidate not qualified",
    )
    for key in ("helper", "inputs", "intent", "start", "stdout", "stderr"):
        check(qualification[key])
    D.require(
        read(qualification["stdout"]["path"])
        .decode()
        .rstrip()
        .endswith("repository validation: PASS"),
        "whole validation PASS missing",
    )
    stderr = read(qualification["stderr"]["path"]).decode()
    D.require(
        "\nOK\n" in stderr
        and re.search(r"\.\.\. skipped |^OK \(skipped=", stderr, re.MULTILINE) is None,
        "unittest OK/skip0 missing",
    )
    before = check_manifest(manifest)
    commit = checked_commit()
    plan = D.checked_plan(PLAN_DIGEST)
    bindings = [ref(p) for p in (manifest_path, approval_path, qualification_path)]
    output = safe_path(OUTPUT)
    output.mkdir()  # Never reuse even an empty or interrupted directory.
    start = save(
        OUTPUT + "/STARTED.json",
        dict(
            started_at_utc=now(),
            pid=os.getpid(),
            candidate_commit=candidate,
            recovery_digest=digest,
            original_operation_head=BASE,
            bindings=bindings,
            previous_analysis_completion="UNKNOWN",
            continuation="fresh_full_replay_not_resume",
        ),
    )
    clock = time.monotonic()
    with (output / "progress.jsonl").open("xb") as stream:

        def progress(stage, completed):
            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            row = dict(
                stage=stage,
                completed_cells=completed,
                planned_cells=len(D.coordinates()),
                at_utc=now(),
                elapsed_seconds=time.monotonic() - clock,
                peak_rss_bytes=rss if sys.platform == "darwin" else rss * 1024,
                accounting="process_diagnostic_not_scientific_work",
            )
            stream.write(D.canonical_trace_bytes(row))
            stream.flush()
            os.fsync(stream.fileno())

        def guard():
            D.require(D.clean_head() == candidate, "candidate changed")
            D.require(
                [ref(p) for p in SOURCE_PATHS] == manifest["recovery_source"],
                "recovery source changed",
            )
            D.operation_guard(plan, candidate)

        try:
            result = execute_analysis(plan, commit, progress, guard)
            guard()
            after = check_manifest(manifest)
            for row in bindings + [start]:
                check(row)
            D.require(before == after, "postflight invariant changed")
            progress("complete", result["replayed_cells"])
            D.require(
                set(p.name for p in output.iterdir())
                == {"STARTED.json", "progress.jsonl"},
                "foreign recovery output",
            )
            summary = D.digested(
                dict(
                    status="ALL_CELLS_REPLAYED_RECOVERY_ANALYSIS_COMPLETE",
                    plan_digest=PLAN_DIGEST,
                    recovery_digest=digest,
                    candidate_commit=candidate,
                    original_operation_head=BASE,
                    commit=ref(D.OUTPUT + "/COMMIT.json"),
                    analysis_start=start,
                    interruption=ref(R + "/analysis.interruption.json"),
                    before=before,
                    after=after,
                    postflight_pass=True,
                    **result,
                )
            )
            D.save_new(OUTPUT + "/summary.json", summary)
            return summary
        except BaseException as error:
            save(
                OUTPUT + "/FAILED.json",
                dict(
                    at_utc=now(),
                    error=repr(error),
                    completed=False,
                    automatic_retry=False,
                    original_inputs_must_be_preserved=True,
                ),
            )
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--manifest", action="store_true")
    modes.add_argument("--recover-manifest")
    parser.add_argument("--confirm-recovery-digest")
    parser.add_argument("--candidate-commit")
    parser.add_argument("--approval")
    parser.add_argument("--qualification")
    args = parser.parse_args()
    if args.manifest:
        D.require(
            not any(
                (
                    args.confirm_recovery_digest,
                    args.candidate_commit,
                    args.approval,
                    args.qualification,
                )
            ),
            "manifest is read-only and does not accept authority",
        )
        value = build_manifest()
    else:
        D.require(
            all(
                (
                    args.confirm_recovery_digest,
                    args.candidate_commit,
                    args.approval,
                    args.qualification,
                )
            ),
            "explicit recovery candidate, digest and evidence required",
        )
        value = recover(
            args.recover_manifest,
            args.confirm_recovery_digest,
            args.candidate_commit,
            args.approval,
            args.qualification,
        )
    sys.stdout.buffer.write(D.canonical_trace_bytes(value))


if __name__ == "__main__":
    main()
