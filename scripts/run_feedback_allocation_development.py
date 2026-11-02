#!/usr/bin/env python3
"""One new development recipe, separate from frozen E4 and original-study slots.

--plan is read-only and outcome-blind. --run requires an externally reviewed
plan digest and an unused fixed output directory. --analyze is a separate
all-cell generative replay; it never resumes a partial run.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from itertools import product
import os
from pathlib import Path
import subprocess
import sys

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
from qmc_bmgs_next.allocation_search import (
    ARMS,
    branch_seed,
    channel_plan,
    AllocationSearchSpec,
    replay_allocation_search_bytes,
    run_allocation_search,
)
from qmc_bmgs_next.allocation_statistics import source_readout, uncertainty_contract


ROOT = Path(__file__).resolve().parents[1]
STUDY = "feedback_allocation_development_20261023_a/v1"
OUTPUT = "artifacts/work/feedback-allocation-development-20261023-a"
PLAN_FILE = (
    "docs/preregistrations/countdown_feedback_allocation_development_20261023.plan.json"
)
POLICY = "docs/strategy/countdown_feedback_allocation_development_20261023.md"
SCRIPT = "scripts/run_feedback_allocation_development.py"
REGISTRY = (
    "docs/preregistrations/countdown_thompson_feedback_budget_v7/preregistration.json"
)
REGISTRY_SHA = "9333ee465f240de2f74094d403ceb43cc4ced6d4fc1b4d3e7ce5a5e6239e85d7"
COUNT = 256
SEEDS = tuple(range(65536, 65544))
BUDGETS = (512,)
GENERATION_SEED = 26102301
MAX_ATTEMPTS = 10000


def require(ok, message):
    if not ok:
        raise ValueError(message)


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def read(path):
    path = ROOT / path
    require(path.is_file() and not path.is_symlink(), f"regular file required: {path}")
    return path.read_bytes()


def load(path):
    return strict_json_loads(read(path).decode())


def load_digest(path, fields):
    raw = read(path)
    value = strict_json_loads(raw.decode())
    require(
        type(value) is dict and set(value) == set(fields),
        "closed record fields required",
    )
    require(canonical_trace_bytes(value) == raw, "canonical record bytes required")
    expected = digested({k: v for k, v in value.items() if k != "deterministic_digest"})
    require(
        canonical_trace_bytes(value) == canonical_trace_bytes(expected),
        "record digest mismatch",
    )
    return value


def reference(path):
    raw = read(path)
    return dict(
        path=str(path), byte_count=len(raw), sha256=hashlib.sha256(raw).hexdigest()
    )


def digested(payload):
    require("deterministic_digest" not in payload, "digest already present")
    return {**payload, "deterministic_digest": sha256_json(payload)}


def save_new(path, payload):
    """Exclusive, fsynced new evidence; failures retain all partial names."""
    path = ROOT / path
    raw = canonical_trace_bytes(payload)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return reference(path.relative_to(ROOT))


def profile(scores):
    require(type(scores) is int and scores > 0, "positive plain score budget")
    limits = {axis: 100_000 for axis in TRACK_A_WORK_AXES}
    limits["legal_action_scores"] = scores
    return TrackABudgetProfile(
        f"allocation_total_{scores}", "legal_action_scores", TrackAWorkBudget(**limits)
    )


def exclusions():
    """Authenticate one identity registry; do not replay or inspect study results."""
    require(
        hashlib.sha256(read(REGISTRY)).hexdigest() == REGISTRY_SHA,
        "historical identity registry changed",
    )
    registry = load(REGISTRY)
    old = registry["admission_context"]["authorities"]["exclusion_identities"]
    tasks, sources = (
        set(old["task_fingerprints"]),
        set(old["source_multiset_fingerprints"]),
    )
    require(
        len(tasks) == 243 and len(sources) == 179, "historical exclusion counts changed"
    )
    rows = registry["cohort"]["tasks"]
    require(len(rows) == 64, "original study identity count changed")
    for row in rows:
        task = CountdownTask(tuple(row["inputs"]), row["target"])
        require(task.to_dict() == row, "original study identity is malformed")
        tasks.add(task.task_fingerprint)
        sources.add(task.source_multiset_fingerprint)
    # The repeatedly inspected PUBLIC source and local regression fixtures are
    # excluded even if another historical group already contains them.
    for inputs in ((1, 2, 3, 4, 5, 6), (1, 1, 1, 1, 1, 1), (2, 2, 3, 4, 5, 7)):
        sources.add(CountdownTask(inputs, 1).source_multiset_fingerprint)
    prior_path = "docs/qualifications/countdown_feedback_portfolio_development_20261020.cohort.json"
    prior = load(prior_path)
    require(
        reference(prior_path)["sha256"]
        == "8bcdf786db8d9f973254d39e404e66fec8f0b0a99073df9bbf4771cb8df38722",
        "prior development cohort identity bytes changed",
    )
    require(len(prior["tasks"]) == 8, "prior development identity count changed")
    for row in prior["tasks"]:
        task = CountdownTask(tuple(row["inputs"]), row["target"])
        require(task.to_dict() == row, "prior development identity malformed")
        tasks.add(task.task_fingerprint)
        sources.add(task.source_multiset_fingerprint)
    diversity_path = "docs/qualifications/countdown_feedback_diversity_development_20261022.cohort.json"
    require(
        reference(diversity_path)["sha256"]
        == "205fadf4eb638e8491cde4cfabe95999ec26bd75ca03b7884ec760b874dac4f0",
        "prior diversity cohort identity bytes changed",
    )
    diversity = load(diversity_path)
    require(len(diversity["tasks"]) == 32, "prior diversity identity count changed")
    for row in diversity["tasks"]:
        task = CountdownTask(tuple(row["inputs"]), row["target"])
        require(task.to_dict() == row, "prior diversity identity malformed")
        tasks.add(task.task_fingerprint)
        sources.add(task.source_multiset_fingerprint)
    return digested(
        dict(
            prior_development_cohort=reference(prior_path),
            prior_diversity_cohort=reference(diversity_path),
            task_fingerprints=sorted(tasks),
            source_multiset_fingerprints=sorted(sources),
            registry=reference(REGISTRY),
            use="identity_exclusion_only_no_original_study_execution",
        )
    )


def source_snapshot():
    paths = set(git("ls-files", "src").decode().splitlines())
    paths.update(
        (
            SCRIPT,
            POLICY,
            "tests/test_feedback_allocation.py",
            "tests/test_feedback_allocation_development.py",
            "tests/test_feedback_allocation_statistics.py",
        )
    )
    require(
        "src/qmc_bmgs_next/allocation_search.py" in paths,
        "stage the additive source before planning",
    )
    for name, module in list(sys.modules.items()):
        if name in {"qmc_bmgs", "qmc_bmgs_next"} or name.startswith(
            ("qmc_bmgs.", "qmc_bmgs_next.")
        ):
            file = getattr(module, "__file__", None)
            origin = getattr(getattr(module, "__spec__", None), "origin", None)
            require(
                type(file) is str and type(origin) is str,
                "source module origin missing",
            )
            expected = ROOT / "src" / Path(*name.split("."))
            expected = (
                expected / "__init__.py"
                if expected.is_dir()
                else expected.with_suffix(".py")
            )
            require(
                Path(file).resolve() == Path(origin).resolve() == expected.resolve(),
                "loaded source origin differs",
            )
            require(
                str(expected.relative_to(ROOT)) in paths,
                "undeclared source module loaded",
            )
    return [reference(path) for path in sorted(paths)]


def build_plan():
    streams = [
        dict(root_seed=s, branch_seeds=[branch_seed(s, i) for i in (0, 1)])
        for s in SEEDS
    ]
    require(
        len({v for row in streams for v in row["branch_seeds"]}) == 2 * len(SEEDS),
        "predeclared derived seed collision",
    )
    return digested(
        dict(
            schema_version="qmc-bmgs-feedback-allocation-development-plan/v1",
            study_id=STUDY,
            output=OUTPUT,
            generation=dict(
                count=COUNT,
                seed=GENERATION_SEED,
                max_attempts=MAX_ATTEMPTS,
                acceptance="existing_exhaustive_solvability_and_identity_exclusion_only",
                outcome_selection=False,
                persist_witnesses=False,
                persist_hardness=False,
            ),
            exclusions=exclusions(),
            task_count=COUNT,
            source_multiset_count=COUNT,
            seeds=list(SEEDS),
            derived_streams=streams,
            budgets=list(BUDGETS),
            arms=[AllocationSearchSpec(a).to_dict() for a in ARMS],
            budget_profiles=[profile(b).to_dict() for b in BUDGETS],
            planned_cells=COUNT * len(SEEDS) * len(BUDGETS) * len(ARMS),
            planned_branch_runs=COUNT * len(SEEDS) * len(BUDGETS) * 5,
            planned_branch_prefix_pairs=COUNT * len(SEEDS) * len(BUDGETS) * 3,
            planned_structural_blocks=COUNT * len(SEEDS) * len(BUDGETS),
            maximum_total_legal_action_scores=COUNT
            * len(SEEDS)
            * sum(BUDGETS)
            * len(ARMS),
            source_files=source_snapshot(),
            runtime=dict(
                search=search_runtime_metadata(),
                perturbation=perturbation_runtime_metadata("iid"),
            ),
            analysis=dict(
                primary="weighted16_minus_single16_source_mean_exact_success_at_512",
                uncertainty=uncertainty_contract(),
                diagnostic_contrast="weighted16_minus_equal16_and_equal16_minus_single16",
                comparisons=[
                    [a, b]
                    for a, b in (
                        ("weighted16", "equal16"),
                        ("weighted16", "single16"),
                        ("equal16", "single16"),
                    )
                ],
                secondary=[
                    "minimum_error_win_tie_loss_missing",
                    "all_work_axes",
                    "by_source",
                    "by_seed",
                    "leave_one_source_out",
                    "leave_one_seed_out",
                    "branch_overlap_and_complementary_success",
                    "first_exact_work_and_lost_late_success",
                ],
                automatic_winner=False,
                population_claim=False,
            ),
            execution_authorized=False,
            requires_explicit_plan_digest_approval=True,
            original_study_C5_authorized=False,
            locked_128_authorized=False,
            provider_calls=0,
        )
    )


def checked_plan(expected_digest):
    expected = build_plan()
    require(
        type(expected_digest) is str
        and expected_digest == expected["deterministic_digest"],
        "exact reviewed plan digest required",
    )
    require(
        read(PLAN_FILE) == canonical_trace_bytes(expected),
        "tracked plan does not match current source/runtime",
    )
    return expected


def clean_head():
    require(
        not git("status", "--porcelain", "--untracked-files=all"),
        "clean committed checkout required",
    )
    return git("rev-parse", "HEAD").decode().strip()


def operation_guard(plan, head):
    require(clean_head() == head, "operation HEAD changed")
    require(
        [reference(r["path"]) for r in plan["source_files"]] == plan["source_files"],
        "source bytes changed",
    )
    require(read(PLAN_FILE) == canonical_trace_bytes(plan), "reviewed plan changed")


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
    # Do not access suite.calibrations. Only inputs and acceptance/rejection
    # identities survive; witnesses and hardness never enter a search policy.
    return digested(
        dict(
            tasks=[t.to_dict() for t in suite.tasks],
            generation=suite.generation_manifest,
            plan_digest=plan["deterministic_digest"],
        )
    )


def coordinates():
    return tuple(product(range(COUNT), SEEDS, BUDGETS, ARMS))


def arguments(cohort, key):
    slot, seed, budget, arm = key
    row = cohort["tasks"][slot]
    return dict(
        task=CountdownTask(tuple(row["inputs"]), row["target"]),
        spec=AllocationSearchSpec(arm),
        budget_profile=profile(budget),
        exploration_seed=seed,
    )


def run(expected_digest):
    plan = checked_plan(expected_digest)
    head = clean_head()
    operation_guard(plan, head)
    output = ROOT / OUTPUT
    # mkdir itself is the one-attempt fence. Neither a digest change nor an
    # absent COMMIT permits reuse. No overwrite/resume/retry CLI exists.
    output.mkdir()
    parent_fd = os.open(output.parent, os.O_RDONLY)
    try:
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)
    started = save_new(
        output.relative_to(ROOT) / "STARTED.json",
        digested(
            dict(
                study_id=STUDY,
                plan_digest=expected_digest,
                source_head=head,
                started_at_utc=datetime.now(timezone.utc).isoformat(),
                approval_basis="external_human_plan_approval_required_literal_argument_is_not_proof",
            )
        ),
    )
    cohort = cohort_from_recipe(plan)
    cohort_ref = save_new(output.relative_to(ROOT) / "cohort.json", cohort)
    cells = []
    for index, key in enumerate(coordinates()):
        operation_guard(plan, head)
        result = run_allocation_search(**arguments(cohort, key))
        require(
            result.summary["budget_valid"], "secondary guard bound; retain partial run"
        )
        ref = save_new(
            output.relative_to(ROOT) / f"cell-{index:04d}.json", result.record
        )
        cells.append(dict(index=index, key=list(key), file=ref))
        print(
            canonical_trace_bytes(
                dict(completed_cells=index + 1, planned_cells=len(coordinates()))
            ).decode(),
            file=sys.stderr,
            end="",
            flush=True,
        )
    operation_guard(plan, head)
    commit = digested(
        dict(
            study_id=STUDY,
            plan_digest=expected_digest,
            source_head=head,
            started=started,
            cohort=cohort_ref,
            cells=cells,
            cell_count=len(cells),
            status="COMPLETE_NOT_YET_INDEPENDENTLY_ANALYZED",
        )
    )
    save_new(output.relative_to(ROOT) / "COMMIT.json", commit)
    return commit


def _contrast(rows, arm, baseline):
    pairs = [(r[arm], r[baseline]) for r in rows]
    gains = sum(int(a["success_any"] and not b["success_any"]) for a, b in pairs)
    losses = sum(int(b["success_any"] and not a["success_any"]) for a, b in pairs)
    errors = dict(win=0, tie=0, loss=0, missing=0)
    for a, b in pairs:
        x, y = a["minimum_terminal_error"], b["minimum_terminal_error"]
        key = (
            "missing"
            if x is None or y is None
            else "win"
            if x < y
            else "loss"
            if x > y
            else "tie"
        )
        errors[key] += 1
    return dict(
        denominator=len(pairs),
        gains=gains,
        losses=losses,
        net=gains - losses,
        minimum_error=errors,
    )


def reduce_results(plan, records):
    require(set(records) == set(coordinates()), "complete unique fixed matrix required")
    by_budget = []
    for budget in BUDGETS:
        blocks = [
            dict(
                task_slot=slot,
                seed=seed,
                **{a: records[(slot, seed, budget, a)]["summary"] for a in ARMS},
            )
            for slot, seed in product(range(COUNT), SEEDS)
        ]
        contrasts = []
        for arm, baseline in plan["analysis"]["comparisons"]:
            contrasts.append(
                dict(
                    arm=arm,
                    baseline=baseline,
                    **_contrast(blocks, arm, baseline),
                    by_source=[
                        dict(
                            task_slot=s,
                            **_contrast(
                                [r for r in blocks if r["task_slot"] == s],
                                arm,
                                baseline,
                            ),
                        )
                        for s in range(COUNT)
                    ],
                    by_seed=[
                        dict(
                            seed=s,
                            **_contrast(
                                [r for r in blocks if r["seed"] == s], arm, baseline
                            ),
                        )
                        for s in SEEDS
                    ],
                    leave_one_source_out=[
                        dict(
                            omitted=s,
                            **_contrast(
                                [r for r in blocks if r["task_slot"] != s],
                                arm,
                                baseline,
                            ),
                        )
                        for s in range(COUNT)
                    ],
                    leave_one_seed_out=[
                        dict(
                            omitted=s,
                            **_contrast(
                                [r for r in blocks if r["seed"] != s], arm, baseline
                            ),
                        )
                        for s in SEEDS
                    ],
                )
            )
        by_budget.append(
            dict(
                budget=budget,
                denominator=len(blocks),
                successes={
                    a: sum(int(r[a]["success_any"]) for r in blocks) for a in ARMS
                },
                work={
                    a: {
                        axis: sum(r[a]["ledger_usage"][axis] for r in blocks)
                        for axis in TRACK_A_WORK_AXES
                    }
                    for a in ARMS
                },
                contrasts=contrasts,
                primary_source_readout=source_readout(blocks, COUNT, SEEDS),
                diagnostics=diversity_diagnostics(records, budget),
            )
        )
    return dict(
        task_count=COUNT,
        source_multiset_count=COUNT,
        seed_count=len(SEEDS),
        cell_count=len(records),
        by_budget=by_budget,
        winner=None,
        scientific_decision=None,
        claim="exploratory_development_only_not_confirmation",
    )


def diversity_diagnostics(records, budget):
    result = {}
    for arm in ARMS:
        two_branches = arm != "single16"
        rows = []
        for slot, seed in product(range(COUNT), SEEDS):
            summary = records[(slot, seed, budget, arm)]["summary"]
            baseline = records[(slot, seed, budget, "single16")]["summary"]
            rows.append(
                dict(
                    task_slot=slot,
                    seed=seed,
                    **summary["diversity"],
                    loses_full_budget_success=(
                        baseline["success_any"] and not summary["success_any"]
                    ),
                    full_budget_first_exact_work=baseline["diversity"]["branches"][0][
                        "first_exact_work"
                    ],
                    unspent_work=summary["unspent_work"],
                )
            )
        result[arm] = dict(
            denominator=len(rows),
            two_branch_denominator=len(rows) if two_branches else 0,
            same_action_sequence=(
                sum(r["same_action_sequence"] is True for r in rows)
                if two_branches
                else None
            ),
            same_first_trajectory=(
                sum(r["same_first_trajectory"] is True for r in rows)
                if two_branches
                else None
            ),
            complementary_success=(
                sum(r["complementary_success"] is True for r in rows)
                if two_branches
                else None
            ),
            primary_only_success=sum(
                len(r["branches"]) == 2
                and r["branches"][0]["success"]
                and not r["branches"][1]["success"]
                for r in rows
            ),
            secondary_only_success=sum(
                len(r["branches"]) == 2
                and r["branches"][1]["success"]
                and not r["branches"][0]["success"]
                for r in rows
            ),
            loses_full_budget_success=sum(r["loses_full_budget_success"] for r in rows),
            lost_success_beyond_primary_allocation=sum(
                r["loses_full_budget_success"]
                and r["full_budget_first_exact_work"]["legal_action_scores"]
                > (
                    budget
                    if arm == "single16"
                    else budget // 2
                    if arm == "equal16"
                    else budget * 3 // 4
                )
                for r in rows
            ),
            rows=rows,
        )
    return result


def _event_projection(record):
    # Trace identities include budget limits; compare work/decisions rather
    # than hash-chain links. The engine uses task/state/visit keyed randomness.
    return [
        (e["kind"], e["payload"], e.get("charge"))
        for e in record["events"]
        if e["kind"] != "search_finished"
    ]


def check_prefixes(records):
    count = 0
    for slot, seed, budget in product(range(COUNT), SEEDS, BUDGETS):
        single, equal, weighted = [records[(slot, seed, budget, a)] for a in ARMS]
        for a, b in (
            (equal["channels"][0], weighted["channels"][0]),
            (weighted["channels"][0], single["channels"][0]),
            (weighted["channels"][1], equal["channels"][1]),
        ):
            lo, hi = (
                _event_projection(a["search_record"]),
                _event_projection(b["search_record"]),
            )
            require(lo == hi[: len(lo)], "budget prefix decision/work mismatch")
            require(
                not a["search_record"]["events"][-1]["payload"]["summary"][
                    "success_any"
                ]
                or b["search_record"]["events"][-1]["payload"]["summary"][
                    "success_any"
                ],
                "success lost within branch budget prefix",
            )
            count += 1
    return count


def check_structure(records):
    checked = 0
    for slot, seed, budget in product(range(COUNT), SEEDS, BUDGETS):
        for arm in ARMS:
            record = records[(slot, seed, budget, arm)]
            expected = AllocationSearchSpec(arm).to_dict()
            require(record["spec"] == expected, "allocation spec mismatch")
            channels = channel_plan(AllocationSearchSpec(arm), profile(budget))
            require(len(record["channels"]) == len(channels), "channel count mismatch")
            for index, (given, (name, method, allocated)) in enumerate(
                zip(record["channels"], channels)
            ):
                require(
                    canonical_trace_bytes(
                        {
                            k: given[k]
                            for k in (
                                "name",
                                "method",
                                "budget_profile",
                                "exploration_seed",
                            )
                        }
                    )
                    == canonical_trace_bytes(
                        dict(
                            name=name,
                            method=method.to_dict(),
                            budget_profile=allocated.to_dict(),
                            exploration_seed=branch_seed(seed, index),
                        )
                    ),
                    "channel allocation/stream mismatch",
                )
            limits = record["summary"]["ledger_usage"]
            require(
                all(
                    limits[axis] <= getattr(profile(budget).budget, axis)
                    for axis in TRACK_A_WORK_AXES
                ),
                "global work cap exceeded",
            )
        # Branch prefix nonloss is mechanical; there is deliberately no
        # whole-arm nonloss assertion between equal and weighted allocation.
        checked += 1
    return checked


def analyze(expected_digest):
    plan = checked_plan(expected_digest)
    head = clean_head()
    output = ROOT / OUTPUT
    require(
        output.is_dir() and not output.is_symlink(), "regular output directory required"
    )
    require(
        not os.path.lexists(output / "analysis.STARTED.json"),
        "analysis already attempted; no automatic retry",
    )
    commit = load_digest(
        OUTPUT + "/COMMIT.json",
        {
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
    )
    commit_ref = reference(OUTPUT + "/COMMIT.json")
    require(
        commit["plan_digest"] == expected_digest and commit["study_id"] == STUDY,
        "COMMIT study mismatch",
    )
    require(commit["source_head"] == head, "analysis must use the operation commit")
    require(
        commit["status"] == "COMPLETE_NOT_YET_INDEPENDENTLY_ANALYZED",
        "COMMIT status mismatch",
    )
    expected_names = {"STARTED.json", "cohort.json", "COMMIT.json"} | {
        f"cell-{i:04d}.json" for i in range(len(coordinates()))
    }
    require(
        {p.name for p in output.iterdir()} == expected_names,
        "partial/foreign output membership",
    )
    require(
        type(commit["cell_count"]) is int
        and commit["cell_count"] == len(coordinates())
        and type(commit["cells"]) is list
        and len(commit["cells"]) == len(coordinates()),
        "incomplete COMMIT",
    )
    for key in ("started", "cohort"):
        expected_path = OUTPUT + (
            "/STARTED.json" if key == "started" else "/cohort.json"
        )
        require(
            type(commit[key]) is dict and commit[key].get("path") == expected_path,
            "fixed COMMIT reference path mismatch",
        )
        require(
            canonical_trace_bytes(reference(expected_path))
            == canonical_trace_bytes(commit[key]),
            "COMMIT reference mismatch",
        )
    started = load_digest(
        OUTPUT + "/STARTED.json",
        {
            "study_id",
            "plan_digest",
            "source_head",
            "started_at_utc",
            "approval_basis",
            "deterministic_digest",
        },
    )
    require(
        started["study_id"] == STUDY
        and started["plan_digest"] == expected_digest
        and started["source_head"] == head,
        "STARTED does not bind the committed operation",
    )
    operation_guard(plan, head)
    analysis_start_ref = save_new(
        OUTPUT + "/analysis.STARTED.json",
        digested(
            dict(
                plan_digest=expected_digest,
                commit=commit_ref,
                source_head=head,
            )
        ),
    )
    cohort = load(OUTPUT + "/cohort.json")
    require(
        canonical_trace_bytes(cohort)
        == canonical_trace_bytes(cohort_from_recipe(plan)),
        "cohort regeneration mismatch",
    )
    records = {}
    for index, key in enumerate(coordinates()):
        operation_guard(plan, head)
        row = commit["cells"][index]
        expected_path = f"{OUTPUT}/cell-{index:04d}.json"
        require(
            type(row) is dict
            and set(row) == {"index", "key", "file"}
            and type(row["index"]) is int
            and row["index"] == index
            and canonical_trace_bytes(row["key"]) == canonical_trace_bytes(list(key))
            and row["file"]["path"] == expected_path,
            "cell coordinate/path mismatch",
        )
        require(
            canonical_trace_bytes(reference(expected_path))
            == canonical_trace_bytes(row["file"]),
            "cell byte hash mismatch",
        )
        raw = read(expected_path)
        replay_allocation_search_bytes(raw, **arguments(cohort, key))
        records[key] = strict_json_loads(raw.decode())
        require(records[key]["summary"]["budget_valid"], "secondary guard bound")
    prefixes = check_prefixes(records)
    structure = check_structure(records)
    result = digested(
        dict(
            status="ALL_CELLS_REPLAYED_DEVELOPMENT_ANALYSIS_COMPLETE",
            plan_digest=expected_digest,
            commit=commit_ref,
            analysis_start=analysis_start_ref,
            prefix_pairs=prefixes,
            structural_blocks=structure,
            reduction=reduce_results(plan, records),
        )
    )
    operation_guard(plan, head)
    require(
        {p.name for p in output.iterdir()}
        == expected_names | {"analysis.STARTED.json"},
        "analysis output membership changed",
    )
    for ref in (
        commit_ref,
        analysis_start_ref,
        commit["started"],
        commit["cohort"],
        *(r["file"] for r in commit["cells"]),
    ):
        require(reference(ref["path"]) == ref, "evidence changed during analysis")
    save_new(OUTPUT + "/summary.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--analyze", action="store_true")
    parser.add_argument("--confirm-plan-digest")
    args = parser.parse_args()
    if args.plan:
        require(args.confirm_plan_digest is None, "plan mode does not accept approval")
        result = build_plan()
    else:
        require(
            args.confirm_plan_digest is not None, "explicit plan digest is required"
        )
        result = (run if args.run else analyze)(args.confirm_plan_digest)
    sys.stdout.buffer.write(canonical_trace_bytes(result))


if __name__ == "__main__":
    main()
