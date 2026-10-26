#!/usr/bin/env python3
"""Sealed prior-tilt development: one delegated candidate, run and full replay.

Planning never generates tasks. An approval receipt is a binding record, not
proof that a person really consented: the operator must establish that authority
from the human conversation. No resume, overwrite, replacement or retry mode.
"""

from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import resource
import stat
import subprocess
import sys
import time

from qmc_bmgs.benchmarks.countdown import CountdownTask, generate_solvable_task_suite
from qmc_bmgs.substrate.budget import TRACK_A_WORK_AXES, TrackAWorkBudget
from qmc_bmgs.substrate.countdown_search import (
    TrackABudgetProfile,
    search_runtime_metadata,
)
from qmc_bmgs.substrate.perturbations import perturbation_runtime_metadata
from qmc_bmgs.substrate.trace import (
    canonical_trace_bytes,
    sha256_json,
    strict_json_loads,
)
from qmc_bmgs_next.diversity_search import branch_seed
from qmc_bmgs_next.prior_tilt import (
    METHODS,
    PriorTiltSpec,
    run_prior_tilt_cell,
    replay_prior_tilt_cell_bytes,
    _cell_inputs,
)
from qmc_bmgs_next.prior_tilt_study import (
    coordinates,
    event_metrics,
    pair_diagnostics,
    reduce_matrix,
    require,
    same,
)


ROOT = Path(__file__).resolve().parents[1]
STUDY = "prior_tilt_development_20261026_a/v1"
OUTPUT = "artifacts/work/prior-tilt-development-20261026-a"
PLAN = "docs/preregistrations/countdown_search_value_prior_tilt_20261026.plan.json"
DESIGN = "docs/preregistrations/countdown_search_value_development_20261024.design.json"
DESIGN_SHA = "6714e49b050cae72b54f31d5e7f97558efbd43acae749927cdbb677350eabe31"
POLICY = "docs/strategy/countdown_prior_tilt_development_20261026.md"
SCRIPT = "scripts/run_prior_tilt_development.py"
COUNT, SCORES = 256, 512
SEEDS = tuple(range(262144, 262148))
GENERATOR_SEED, MAX_ATTEMPTS = 26102601, 10000
REGISTRY = (
    "docs/preregistrations/countdown_thompson_feedback_budget_v7/preregistration.json"
)
REGISTRY_SHA = "9333ee465f240de2f74094d403ceb43cc4ced6d4fc1b4d3e7ce5a5e6239e85d7"
COHORTS = (
    (
        "docs/qualifications/countdown_search_value_development_20261025.cohort.json",
        "4ebe3752fd0058bf8736b5366c3d95fb52f4ffd1ca3b2557c4b9f9237067521a",
        128,
    ),
    (
        "docs/qualifications/countdown_feedback_portfolio_development_20261020.cohort.json",
        "8bcdf786db8d9f973254d39e404e66fec8f0b0a99073df9bbf4771cb8df38722",
        8,
    ),
    (
        "docs/qualifications/countdown_feedback_diversity_development_20261022.cohort.json",
        "205fadf4eb638e8491cde4cfabe95999ec26bd75ca03b7884ec760b874dac4f0",
        32,
    ),
    (
        "docs/qualifications/countdown_feedback_allocation_recovery_20261024.cohort.json",
        "13d1af8215654c154b078f9fce7e79df5b56658060a8073b186689a2ff18a732",
        256,
    ),
)
APPROVAL_SCHEMA = "prior_tilt_delegated_candidate_approval/v1"
APPROVAL_SCOPE = dict(
    candidate_count=1,
    run_count=1,
    separate_process_analysis_count=1,
    source_count=256,
    cell_count=2304,
    provider_calls=0,
    original_c5=False,
    locked_evaluation=False,
    automatic_retry=False,
    merge=False,
)


def now():
    return datetime.now(timezone.utc).isoformat()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def path(name):
    p = Path(name)
    require(
        type(name) is str
        and not p.is_absolute()
        and p.as_posix() == name
        and name != "."
        and ".." not in p.parts,
        "canonical relative path required",
    )
    require(not ROOT.is_symlink(), "checkout root must not be a symlink")
    current = ROOT
    for part in p.parts:
        current /= part
        require(not current.is_symlink(), "symlink path component rejected")
    return current


def read(name):
    fd = os.open(path(name), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as f:
        require(stat.S_ISREG(os.fstat(f.fileno()).st_mode), "regular file required")
        return f.read()


def load(name):
    return strict_json_loads(read(name))


def reference(name):
    data = read(name)
    return dict(
        path=name, byte_count=len(data), sha256=hashlib.sha256(data).hexdigest()
    )


def check(ref, expected_path=None):
    require(
        type(ref) is dict and set(ref) >= {"path", "byte_count", "sha256"},
        "file reference required",
    )
    require(
        type(ref["byte_count"]) is int
        and ref["byte_count"] >= 0
        and type(ref["sha256"]) is str
        and re.fullmatch("[0-9a-f]{64}", ref["sha256"]),
        "typed byte/hash reference required",
    )
    require(
        expected_path is None or ref["path"] == expected_path,
        "fixed reference path mismatch",
    )
    actual = reference(ref["path"])
    require(all(same(actual[k], ref[k]) for k in actual), "file bytes/hash changed")


def digested(core):
    require("deterministic_digest" not in core, "digest already present")
    return {**core, "deterministic_digest": sha256_json(core)}


def checked_record(name, fields=None):
    data, value = read(name), load(name)
    require(
        type(value) is dict and "deterministic_digest" in value,
        "digested object required",
    )
    require(
        fields is None or set(value) == set(fields) | {"deterministic_digest"},
        "closed record fields",
    )
    expected = digested({k: v for k, v in value.items() if k != "deterministic_digest"})
    require(data == canonical_trace_bytes(expected), "canonical bytes/digest mismatch")
    return value


def save_new(name, value):
    raw = canonical_trace_bytes(value)
    fd = os.open(
        path(name), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644
    )
    with os.fdopen(fd, "wb") as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())
    fd = os.open(path(name).parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return reference(name)


def profile():
    caps = dict.fromkeys(TRACK_A_WORK_AXES, 100000)
    caps["legal_action_scores"] = SCORES
    return TrackABudgetProfile(
        "prior_tilt_512_v1", "legal_action_scores", TrackAWorkBudget(**caps)
    )


def tracked_python():
    return sorted(p for p in git("ls-files").decode().splitlines() if p.endswith(".py"))


def exclusions():
    require(
        reference(REGISTRY)["sha256"] == REGISTRY_SHA,
        "historical identity registry drift",
    )
    registry = load(REGISTRY)
    old = registry["admission_context"]["authorities"]["exclusion_identities"]
    tasks, sources = (
        set(old["task_fingerprints"]),
        set(old["source_multiset_fingerprints"]),
    )
    require(
        len(tasks) == 243 and len(sources) == 179, "historical exclusion counts drift"
    )
    refs = [reference(REGISTRY)]

    def add(rows, count):
        require(len(rows) == count, "historical cohort count mismatch")
        for row in rows:
            task = CountdownTask(tuple(row["inputs"]), row["target"])
            require(same(task.to_dict(), row), "historical identity malformed")
            tasks.add(task.task_fingerprint)
            sources.add(task.source_multiset_fingerprint)

    add(registry["cohort"]["tasks"], 64)
    for name, digest, count in COHORTS:
        require(
            reference(name)["sha256"] == digest, "historical development cohort drift"
        )
        add(load(name)["tasks"], count)
        refs.append(reference(name))
    # Conservative, outcome-blind fixture superset: every literal six-element
    # positive 1..10 tuple/list in tracked Python, whether or not executed as a
    # task. This avoids pretending static parsing proves dynamic input coverage.
    fixture_rows, fixture_refs = [], []
    for name in tracked_python():
        fixture_refs.append(reference(name))
        tree = ast.parse(read(name), filename=name)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Tuple, ast.List)) or len(node.elts) != 6:
                continue
            try:
                values = ast.literal_eval(node)
            except (ValueError, TypeError, SyntaxError):
                continue
            if all(type(v) is int and 1 <= v <= 10 for v in values):
                source = CountdownTask(tuple(values), 1).source_multiset_fingerprint
                sources.add(source)
                fixture_rows.append(
                    dict(
                        path=name,
                        line=node.lineno,
                        inputs=list(values),
                        source_multiset_fingerprint=source,
                    )
                )
    return digested(
        dict(
            authority_refs=refs,
            fixture_source_files=fixture_refs,
            literal_fixture_identities=fixture_rows,
            fixture_scope="conservative_literal_superset_plus_authenticated_historical_registry_and_cohorts",
            task_fingerprints=sorted(tasks),
            source_multiset_fingerprints=sorted(sources),
            reserved_use="identity_only_not_outcomes_difficulty_or_witnesses",
        )
    )


def seed_exclusions():
    names = sorted(
        p
        for p in git("ls-files", "docs/preregistrations").decode().splitlines()
        if p.endswith(".json") and p != PLAN
    )
    seeds = {0, 1, 2, 3, 4, 7, 9, 11, 41, 42, 43, 101, 202}
    refs = []

    def walk(value):
        if type(value) is dict:
            for k, v in value.items():
                if "seed" in k:
                    if type(v) is int and v >= 0:
                        seeds.add(v)
                    elif type(v) is list:
                        seeds.update(x for x in v if type(x) is int and x >= 0)
                walk(v)
        elif type(value) is list:
            for v in value:
                walk(v)

    for name in names:
        walk(load(name))
        refs.append(reference(name))
    derived = {branch_seed(s, i) for s in seeds for i in (0, 1)}
    current = [branch_seed(s, 0) for s in SEEDS]
    require(
        len(set(current)) == len(SEEDS)
        and not set(SEEDS) & (seeds | derived)
        and not set(current) & (seeds | derived | set(SEEDS)),
        "fixed seed collision; no replacement",
    )
    return dict(
        refs=refs,
        historical_seed_identities=sorted(seeds),
        historical_derived_streams=sorted(derived),
        current_branch0=current,
        scope="authenticated_registered_seed_fields_and_declared_regression_roots",
    )


def source_snapshot():
    paths = set(git("ls-files", "src").decode().splitlines())
    paths.update(
        (
            SCRIPT,
            POLICY,
            DESIGN,
            "tests/test_prior_tilt.py",
            "tests/test_prior_tilt_study.py",
        )
    )
    require(
        "src/qmc_bmgs_next/prior_tilt_study.py" in paths,
        "stage additive source before planning",
    )
    for name, module in list(sys.modules.items()):
        if name in ("qmc_bmgs", "qmc_bmgs_next") or name.startswith(
            ("qmc_bmgs.", "qmc_bmgs_next.")
        ):
            expected = ROOT / "src" / Path(*name.split("."))
            expected = (
                expected / "__init__.py"
                if expected.is_dir()
                else expected.with_suffix(".py")
            )
            file = getattr(module, "__file__", None)
            origin = getattr(getattr(module, "__spec__", None), "origin", None)
            require(
                type(file) is str
                and type(origin) is str
                and Path(file).resolve() == Path(origin).resolve() == expected.resolve()
                and str(expected.relative_to(ROOT)) in paths,
                "unsealed source module origin",
            )
    return [reference(p) for p in sorted(paths)]


def build_plan():
    require(reference(DESIGN)["sha256"] == DESIGN_SHA, "readout template changed")
    design = load(DESIGN)
    keys = coordinates(COUNT, SEEDS)
    require(
        COUNT == 256 and SEEDS == tuple(range(262144, 262148)) and SCORES == 512,
        "fixed design constants changed",
    )
    return digested(
        dict(
            schema_version="prior_tilt_executable_plan/v1",
            study_id=STUDY,
            output=OUTPUT,
            readout_template=reference(DESIGN),
            source_files=source_snapshot(),
            exclusions=exclusions(),
            seed_exclusions=seed_exclusions(),
            runtime=dict(
                search=search_runtime_metadata(),
                perturbation=perturbation_runtime_metadata("iid"),
            ),
            generation=dict(
                count=COUNT,
                seed=GENERATOR_SEED,
                max_attempts=MAX_ATTEMPTS,
                input_count=6,
                input_min=1,
                input_max=10,
                target_min=100,
                target_max=999,
                acceptance="first_source_unique_solvable_identity_excluded_no_outcome_or_hardness_selection",
            ),
            methods=[PriorTiltSpec(m).to_dict() for m in METHODS],
            budget_profile=profile().to_dict(),
            roots=list(SEEDS),
            deterministic_root=0,
            coordinates=[list(k) for k in keys],
            coordinate_digest=sha256_json([list(k) for k in keys]),
            planned_cells=len(keys),
            planned_branch_runs=len(keys),
            maximum_primary_work=len(keys) * SCORES,
            cell_order="source_rotated_groups_stochastic_pair_interleaved_alternating_order/v1",
            analysis=dict(
                primary=dict(
                    design["primary"],
                    contrast="prior-tilt16-minus-puct",
                    n_sources=COUNT,
                    sample_variance_denominator=COUNT - 1,
                    source_difference="mean_four_fixed_roots(prior-tilt16 success) - one_PUCT_success",
                ),
                diagnostic_contrasts=["prior-tilt16-minus-prior-mean-off"],
                cross_budget_prefix_pairs=0,
                replay="all_cells_generative_byte_identical",
                compact_event_reduction=True,
                detailed_pair_cache_limit=2,
                model_assumptions_not_established_by_source_uniqueness=True,
                timing="resource_diagnostics_only_no_speed_or_efficiency_claim",
            ),
            execution_authorized=False,
            requires_conversation_verified_delegated_candidate_binding=True,
            original_c5=False,
            locked_evaluation=False,
            provider_calls=0,
            automatic_retry=False,
            automatic_resume=False,
            winner=None,
            scientific_decision=None,
        )
    )


def clean_head():
    require(
        not git("status", "--porcelain=v1", "--untracked-files=all"),
        "clean committed checkout required",
    )
    return git("rev-parse", "HEAD").decode().strip()


def validate_approval(value, head, digest):
    require(
        type(value) is dict
        and set(value)
        == {
            "schema_version",
            "candidate_commit",
            "plan_digest",
            "authority_kind",
            "human_proposal",
            "human_answer",
            "scope",
        },
        "closed human approval receipt required",
    )
    require(
        value["schema_version"] == APPROVAL_SCHEMA
        and value["candidate_commit"] == head
        and value["plan_digest"] == digest
        and value["authority_kind"] == "delegated_candidate_selection",
        "delegated candidate/plan authority binding required",
    )
    require(
        all(
            type(value[k]) is str and value[k].strip()
            for k in ("human_proposal", "human_answer")
        ),
        "actual proposal and human instruction required",
    )
    require(same(value["scope"], APPROVAL_SCOPE), "closed one-run scope required")


def qualify(name, head):
    q = checked_record(name)
    require(
        q["source_head"] == head
        and type(q["exit_code"]) is int
        and q["exit_code"] == 0
        and q["postflight_pass"] is True
        and q["postconditions_errors"] == []
        and same(q["before"], q["after"]),
        "complete successful qualification required",
    )
    for k in ("inputs", "intent", "start", "helper", "stdout", "stderr"):
        check(q[k])
    records = {k: checked_record(q[k]["path"]) for k in ("inputs", "intent", "start")}
    require(
        all(r["source_head"] == head for r in records.values()),
        "qualification source binding",
    )
    require(
        same(
            records["intent"]["argv"],
            [sys.executable, "-P", "-B", str(ROOT / "scripts/validate.py")],
        ),
        "qualification must run the full repository validator",
    )
    require(
        same(records["inputs"]["helper"], q["helper"])
        and same(records["inputs"]["before"], q["before"])
        and same(records["intent"]["inputs"], q["inputs"])
        and same(records["intent"]["helper"], q["helper"])
        and same(records["start"]["intent"], q["intent"]),
        "qualification reference chain mismatch",
    )
    stdout, stderr = (
        read(q["stdout"]["path"]).decode(),
        read(q["stderr"]["path"]).decode(),
    )
    require(
        stdout.rstrip().endswith("repository validation: PASS")
        and re.search(r"^OK$", stderr, re.M) is not None
        and re.search(r"^Ran [1-9][0-9]* tests in [0-9.]+s$", stderr, re.M) is not None
        and re.search(r"\.\.\. skipped |^OK \(skipped=", stderr, re.M) is None
        and "ruff unavailable: lint check skipped" not in stdout,
        "qualification logs not complete PASS",
    )
    return reference(name)


def operation_guard(plan, head):
    require(clean_head() == head, "operation HEAD changed")
    require(read(PLAN) == canonical_trace_bytes(plan), "sealed plan changed")
    for row in plan["source_files"]:
        check(row)
    for row in (
        plan["exclusions"]["authority_refs"]
        + plan["exclusions"]["fixture_source_files"]
        + plan["seed_exclusions"]["refs"]
    ):
        check(row)


def preflight(digest, head, approval, qualification):
    require(
        type(head) is str and re.fullmatch("[0-9a-f]{40}", head),
        "exact candidate commit required",
    )
    require(clean_head() == head, "operation must use exact candidate commit")
    plan = build_plan()
    require(
        type(digest) is str
        and digest == plan["deterministic_digest"]
        and read(PLAN) == canonical_trace_bytes(plan),
        "exact sealed current plan required",
    )
    value = load(approval)
    validate_approval(value, head, digest)
    q = qualify(qualification, head)
    operation_guard(plan, head)
    return plan, head, dict(approval=reference(approval), qualification=q)


def cohort_from_recipe(plan):
    e, g = plan["exclusions"], plan["generation"]
    suite = generate_solvable_task_suite(
        g["count"],
        g["seed"],
        max_attempts=g["max_attempts"],
        excluded_task_fingerprints=e["task_fingerprints"],
        excluded_source_multiset_fingerprints=e["source_multiset_fingerprints"],
        excluded_identity_record_digest=e["deterministic_digest"],
    )
    # Witnesses/calibrations are intentionally not accessed or persisted.
    return digested(
        dict(
            tasks=[t.to_dict() for t in suite.tasks],
            generation=suite.generation_manifest,
            plan_digest=plan["deterministic_digest"],
        )
    )


def arguments(cohort, key):
    slot, method, seed = key
    row = cohort["tasks"][slot]
    return dict(
        task=CountdownTask(tuple(row["inputs"]), row["target"]),
        spec=PriorTiltSpec(method),
        root_seed=seed,
        budget_profile=profile(),
    )


def members():
    require(path(OUTPUT).is_dir(), "output directory required")
    return {p.name for p in path(OUTPUT).iterdir()}


def run(digest, head, approval, qualification):
    plan, head, authority = preflight(digest, head, approval, qualification)
    output = path(OUTPUT)
    require(output.parent.is_dir(), "existing regular work parent required")
    output.mkdir()  # Exclusive one-attempt fence; failure never removes it.
    started = save_new(
        OUTPUT + "/STARTED.json",
        digested(
            dict(
                study_id=STUDY,
                plan_digest=digest,
                candidate_commit=head,
                authority=authority,
                started_at_utc=now(),
                process_id=os.getpid(),
            )
        ),
    )
    cohort = cohort_from_recipe(plan)
    cohort_ref = save_new(OUTPUT + "/cohort.json", cohort)
    cells = []
    keys = coordinates(COUNT, SEEDS)
    for index, key in enumerate(keys):
        operation_guard(plan, head)
        started_clock = time.monotonic()
        result = run_prior_tilt_cell(**arguments(cohort, key))
        # Persist even an invalid result, then fail closed; no favorable-row subset.
        ref = save_new(OUTPUT + f"/cell-{index:04d}.json", result.record)
        require(
            result.summary["search_summary"]["budget_valid"] is True,
            "non-primary guard bound; INCOMPLETE_OR_INVALID; keep partial evidence",
        )
        cells.append(dict(index=index, key=list(key), file=ref))
        print(
            canonical_trace_bytes(
                dict(
                    completed_cells=index + 1,
                    planned_cells=len(keys),
                    elapsed_seconds=time.monotonic() - started_clock,
                    maxrss_native=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                    timing_is_not_scientific_work=True,
                )
            ).decode(),
            file=sys.stderr,
            end="",
            flush=True,
        )
        del result
    operation_guard(plan, head)
    for ref in (started, cohort_ref, *(r["file"] for r in cells)):
        check(ref)
    require(
        members()
        == {"STARTED.json", "cohort.json"}
        | {f"cell-{i:04d}.json" for i in range(len(keys))},
        "run membership changed",
    )
    commit = digested(
        dict(
            study_id=STUDY,
            plan_digest=digest,
            candidate_commit=head,
            authority=authority,
            started=started,
            cohort=cohort_ref,
            cells=cells,
            cell_count=len(keys),
            status="COMPLETE_NOT_YET_INDEPENDENTLY_ANALYZED",
        )
    )
    save_new(OUTPUT + "/COMMIT.json", commit)
    return commit


def committed_inputs(digest, head, authority):
    commit = checked_record(
        OUTPUT + "/COMMIT.json",
        {
            "study_id",
            "plan_digest",
            "candidate_commit",
            "authority",
            "started",
            "cohort",
            "cells",
            "cell_count",
            "status",
        },
    )
    keys = coordinates(COUNT, SEEDS)
    require(
        commit["study_id"] == STUDY
        and commit["plan_digest"] == digest
        and commit["candidate_commit"] == head
        and same(commit["authority"], authority)
        and commit["status"] == "COMPLETE_NOT_YET_INDEPENDENTLY_ANALYZED",
        "COMMIT binding mismatch",
    )
    require(
        type(commit["cell_count"]) is int
        and commit["cell_count"] == len(keys)
        and type(commit["cells"]) is list
        and len(commit["cells"]) == len(keys),
        "incomplete COMMIT",
    )
    check(commit["started"], OUTPUT + "/STARTED.json")
    check(commit["cohort"], OUTPUT + "/cohort.json")
    started = checked_record(
        OUTPUT + "/STARTED.json",
        {
            "study_id",
            "plan_digest",
            "candidate_commit",
            "authority",
            "started_at_utc",
            "process_id",
        },
    )
    require(
        started["study_id"] == STUDY
        and started["plan_digest"] == digest
        and started["candidate_commit"] == head
        and same(started["authority"], authority),
        "STARTED binding mismatch",
    )
    require(
        type(started["process_id"]) is int and started["process_id"] != os.getpid(),
        "analysis must use a separate process from run",
    )
    for i, (key, row) in enumerate(zip(keys, commit["cells"])):
        expected = dict(
            index=i, key=list(key), file=reference(OUTPUT + f"/cell-{i:04d}.json")
        )
        require(same(row, expected), "cell coordinate/order/hash mismatch")
    expected_names = {"STARTED.json", "cohort.json", "COMMIT.json"} | {
        f"cell-{i:04d}.json" for i in range(len(keys))
    }
    require(members() == expected_names, "partial/foreign output membership")
    return commit, expected_names


def analyze(digest, head, approval, qualification):
    plan, head, authority = preflight(digest, head, approval, qualification)
    require(
        not os.path.lexists(path(OUTPUT + "/analysis.STARTED.json")),
        "analysis already attempted; no retry",
    )
    commit, expected_names = committed_inputs(digest, head, authority)
    commit_ref = reference(OUTPUT + "/COMMIT.json")
    start = save_new(
        OUTPUT + "/analysis.STARTED.json",
        digested(
            dict(
                candidate_commit=head,
                plan_digest=digest,
                commit=commit_ref,
                authority=authority,
                started_at_utc=now(),
                process_id=os.getpid(),
            )
        ),
    )
    cohort = checked_record(
        OUTPUT + "/cohort.json", {"tasks", "generation", "plan_digest"}
    )
    require(same(cohort, cohort_from_recipe(plan)), "cohort regeneration mismatch")
    rows, pair_rows, pending = [], [], {}
    progress_name = OUTPUT + "/analysis.progress.jsonl"
    with path(progress_name).open("xb") as progress:
        for i, entry in enumerate(commit["cells"]):
            operation_guard(plan, head)
            key = tuple(entry["key"])
            raw = read(entry["file"]["path"])
            kwargs = arguments(cohort, key)
            identity, _ = _cell_inputs(**kwargs)
            replay_prior_tilt_cell_bytes(
                raw, **kwargs, expected_run_identity_digest=sha256_json(identity)
            )
            record = strict_json_loads(raw)
            rows.append(dict(key=list(key), metrics=event_metrics(record)))
            if key[1] in METHODS[:2]:
                pending[key[1]] = record
                if len(pending) == 2:
                    pair_rows.append(
                        dict(
                            source_slot=key[0],
                            root_seed=key[2],
                            **pair_diagnostics(
                                pending["prior-tilt16"], pending["prior-mean-off"]
                            ),
                        )
                    )
                    pending.clear()
            require(len(pending) <= 1, "pair cache boundary drift")
            del raw, record
            progress.write(
                canonical_trace_bytes(
                    dict(
                        completed_cells=i + 1,
                        planned_cells=len(commit["cells"]),
                        maxrss_native=resource.getrusage(
                            resource.RUSAGE_SELF
                        ).ru_maxrss,
                    )
                )
            )
            progress.flush()
        os.fsync(progress.fileno())
    require(
        not pending and len(pair_rows) == COUNT * len(SEEDS),
        "incomplete stochastic pair diagnostics",
    )
    result = digested(
        dict(
            status="ALL_CELLS_REPLAYED_PRIOR_TILT_ANALYSIS_COMPLETE",
            candidate_commit=head,
            plan_digest=digest,
            commit=commit_ref,
            analysis_start=start,
            progress=reference(progress_name),
            replayed_cells=len(rows),
            cross_budget_prefix_pairs=0,
            peak_detailed_cell_records_retained=2,
            cache_limit_is_not_total_memory_bound=True,
            reduction=reduce_matrix(rows, COUNT, SEEDS, SCORES),
            paired_choice_diagnostics=pair_rows,
            winner=None,
            scientific_decision=None,
        )
    )
    operation_guard(plan, head)
    for ref in (
        commit_ref,
        start,
        commit["started"],
        commit["cohort"],
        *(r["file"] for r in commit["cells"]),
    ):
        check(ref)
    require(
        members()
        == expected_names | {"analysis.STARTED.json", "analysis.progress.jsonl"},
        "analysis output membership changed",
    )
    save_new(OUTPUT + "/summary.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--plan", action="store_true")
    modes.add_argument("--run", action="store_true")
    modes.add_argument("--analyze", action="store_true")
    parser.add_argument("--confirm-plan-digest")
    parser.add_argument("--candidate-commit")
    parser.add_argument("--approval")
    parser.add_argument("--qualification")
    args = parser.parse_args()
    if args.plan:
        require(
            all(
                v is None
                for v in (
                    args.confirm_plan_digest,
                    args.candidate_commit,
                    args.approval,
                    args.qualification,
                )
            ),
            "plan mode is not approval",
        )
        result = build_plan()
    else:
        require(
            all(
                type(v) is str and v
                for v in (
                    args.confirm_plan_digest,
                    args.candidate_commit,
                    args.approval,
                    args.qualification,
                )
            ),
            "all authority inputs required",
        )
        result = (run if args.run else analyze)(
            args.confirm_plan_digest,
            args.candidate_commit,
            args.approval,
            args.qualification,
        )
    sys.stdout.buffer.write(canonical_trace_bytes(result))


if __name__ == "__main__":
    main()
