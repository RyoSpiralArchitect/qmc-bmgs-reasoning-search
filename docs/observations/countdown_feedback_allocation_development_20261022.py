#!/usr/bin/env python3
"""Read-only stdlib recomputation of COMMIT-bound allocation evidence.

No engine/reducer import, cohort generation, search, or generative replay.
Print deterministic diagnostics; fixed raw files are never written.
Run from any cwd with Python 3.13: python3 -P -B <this file>.
"""

from __future__ import annotations

from collections import Counter
import hashlib
from itertools import product
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = "artifacts/work/feedback-allocation-development-20261022-a"
PLAN = "docs/preregistrations/countdown_feedback_allocation_development_20261022.v3.plan.json"
DIGEST = "18f4dd53afd152ef88618e92091e822d56111b6ad04bb67c0aed5755b90da9ed"
HEAD = "04bbe3c5bcf7380fc1b889b4e8a1de5598a19aae"
ARMS = ("single16", "equal16", "weighted16")
SEEDS = tuple(range(65536, 65544))
BUDGETS = (512,)
AXES = (
    "edge_selections",
    "generated_perturbation_coordinates",
    "legal_action_scores",
    "proposal_action_scores",
    "proposal_state_evaluations",
    "transitions",
    "verifier_calls",
)


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def pairs(rows):
    d = {}
    for k, v in rows:
        assert k not in d, k
        d[k] = v
    return d


def load(path):
    p = ROOT / path
    assert p.is_file() and not p.is_symlink(), path
    return json.loads(
        p.read_bytes(),
        object_pairs_hook=pairs,
        parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)),
    )


def reference(path):
    raw = (ROOT / path).read_bytes()
    return dict(path=path, byte_count=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def checked(row):
    actual = reference(row["path"])
    assert all(actual[k] == row[k] for k in actual), row["path"]
    return load(row["path"])


def digested(path):
    value = load(path)
    assert (
        digest({k: v for k, v in value.items() if k != "deterministic_digest"})
        == value["deterministic_digest"]
    )
    assert canonical(value) + b"\n" == (ROOT / path).read_bytes()
    return value


def branch(channel):
    trace = channel["search_record"]
    usage = dict.fromkeys(AXES, 0)
    terminals, choices, first_choices, projection = [], [], [], []
    first_exact = first_terminal = None
    for event in trace["events"]:
        charge = event.get("charge")
        if charge is not None:
            assert set(charge["delta"]) == set(AXES)
            for axis in AXES:
                n = charge["delta"][axis]
                assert type(n) is int and n >= 0
                usage[axis] += n
            assert usage == charge["usage_after"]
        if event["kind"] != "search_finished":
            projection.append(digest([event["kind"], event["payload"], charge]))
        if event["kind"] == "selection_committed":
            choice = {
                k: event["payload"][k]
                for k in ("state", "action", "trajectory_index", "depth")
            }
            choices.append(choice)
            if not terminals:
                first_choices.append(choice)
        if event["kind"] == "terminal_verified":
            if not terminals:
                first_terminal = dict(usage)
            payload = event["payload"]
            v = payload["verification"]
            assert type(v["success"]) is bool and type(v["final_value"]) is int
            assert v["source_use_exact"] is True
            assert v["success"] == (v["final_value"] == v["target"])
            if v["success"] and first_exact is None:
                first_exact = dict(usage)
            terminals.append(payload)
    finish = trace["events"][-1]["payload"]["summary"]
    assert trace["events"][-1]["kind"] == "search_finished"
    assert usage == finish["ledger_usage"] and finish["budget_valid"] is True
    success = any(p["verification"]["success"] for p in terminals)
    assert (
        success == finish["success_any"] and len(terminals) == finish["terminal_count"]
    )
    diagnostics = dict(
        name=channel["name"],
        exploration_seed=channel["exploration_seed"],
        success=success,
        terminal_count=len(terminals),
        first_exact_work=first_exact,
        choice_count=len(choices),
        choice_sequence_digest=digest(choices),
        first_trajectory_digest=digest(first_choices),
    )
    return dict(
        usage=usage,
        first_terminal=first_terminal,
        terminals=terminals,
        choices=choices,
        first_choices=first_choices,
        projection=projection,
        diagnostics=diagnostics,
        trace_digest=digest(trace),
        channel_digest=digest(channel),
    )


def cell_metrics(cell):
    channels = [branch(ch) for ch in cell["channels"]]
    usage = {a: sum(ch["usage"][a] for ch in channels) for a in AXES}
    terminals = []
    for i, ch in enumerate(channels):
        for p in ch["terminals"]:
            v = p["verification"]
            terminals.append(
                dict(
                    channel_index=i,
                    channel_name=cell["channels"][i]["name"],
                    observation_index=p["observation_index"],
                    success=v["success"],
                    absolute_error=abs(v["final_value"] - v["target"]),
                    verification=v,
                    actions=p["actions"],
                )
            )
    exact = [t for t in terminals if t["success"]]
    readout = (
        exact[0]
        if exact
        else min(
            terminals,
            default=None,
            key=lambda t: (
                t["absolute_error"],
                t["channel_index"],
                t["observation_index"],
            ),
        )
    )
    two = len(channels) == 2
    prefix = None
    if two:
        prefix = 0
        for a, b in zip(channels[0]["choices"], channels[1]["choices"]):
            if a != b:
                break
            prefix += 1
    diversity = dict(
        branches=[ch["diagnostics"] for ch in channels],
        same_action_sequence=(channels[0]["choices"] == channels[1]["choices"])
        if two
        else None,
        same_first_trajectory=(
            channels[0]["first_choices"] == channels[1]["first_choices"]
        )
        if two
        else None,
        common_action_prefix_length=prefix,
        complementary_success=(
            channels[0]["diagnostics"]["success"]
            != channels[1]["diagnostics"]["success"]
        )
        if two
        else None,
    )
    limits = cell["budget_profile"]["budget"]
    assert all(usage[a] <= limits[a] for a in AXES)
    summary = dict(
        success_any=bool(exact),
        minimum_terminal_error=min(
            (t["absolute_error"] for t in terminals), default=None
        ),
        terminal_count=len(terminals),
        exact_terminal_count=len(exact),
        readout=readout,
        readout_extra_verifier_calls=0,
        ledger_usage=usage,
        unspent_work={a: limits[a] - usage[a] for a in AXES},
        budget_valid=True,
        primary_allocated_budget_success=channels[0]["diagnostics"]["success"],
        diversity=diversity,
        protects_full_budget_baseline=False,
        provider_calls=0,
    )
    assert canonical(summary) == canonical(cell["summary"])
    compact = [
        {k: ch[k] for k in ("projection", "trace_digest", "channel_digest")}
        for ch in channels
    ]
    return summary, compact, [ch["first_terminal"] for ch in channels]


def contrast(blocks, a, b):
    gains = losses = 0
    error = dict(win=0, tie=0, loss=0, missing=0)
    for r in blocks:
        x, y = r[a], r[b]
        gains += int(x["success_any"] and not y["success_any"])
        losses += int(y["success_any"] and not x["success_any"])
        u, v = x["minimum_terminal_error"], y["minimum_terminal_error"]
        label = (
            "missing"
            if u is None or v is None
            else "win"
            if u < v
            else "loss"
            if u > v
            else "tie"
        )
        error[label] += 1
    return dict(
        denominator=len(blocks),
        gains=gains,
        losses=losses,
        net=gains - losses,
        minimum_error=error,
    )


def reduce_budget(budget, cells, comparisons, first_terminals):
    blocks = [
        dict(task_slot=t, seed=s, **{a: cells[t, s, budget, a] for a in ARMS})
        for t, s in product(range(64), SEEDS)
    ]
    contrasts = []
    for a, b in comparisons:
        contrasts.append(
            dict(
                arm=a,
                baseline=b,
                **contrast(blocks, a, b),
                source_cluster_summary=clusters(blocks, a, b),
                by_source=[
                    dict(
                        task_slot=t,
                        **contrast([r for r in blocks if r["task_slot"] == t], a, b),
                    )
                    for t in range(64)
                ],
                by_seed=[
                    dict(
                        seed=s, **contrast([r for r in blocks if r["seed"] == s], a, b)
                    )
                    for s in SEEDS
                ],
                leave_one_source_out=[
                    dict(
                        omitted=t,
                        **contrast([r for r in blocks if r["task_slot"] != t], a, b),
                    )
                    for t in range(64)
                ],
                leave_one_seed_out=[
                    dict(
                        omitted=s,
                        **contrast([r for r in blocks if r["seed"] != s], a, b),
                    )
                    for s in SEEDS
                ],
            )
        )
    diagnostics = {}
    for arm in ARMS:
        two = arm != "single16"
        rows = [
            dict(
                task_slot=r["task_slot"],
                seed=r["seed"],
                **r[arm]["diversity"],
                primary_cap={"single16": 512, "equal16": 256, "weighted16": 384}[arm],
                first_terminal_work=first_terminals[
                    r["task_slot"], r["seed"], budget, arm
                ],
                loses_full_budget_success=r["single16"]["success_any"]
                and not r[arm]["success_any"],
                full_budget_first_exact_work=r["single16"]["diversity"]["branches"][0][
                    "first_exact_work"
                ],
                unspent_work=r[arm]["unspent_work"],
            )
            for r in blocks
        ]
        diagnostics[arm] = dict(
            denominator=512,
            no_terminal_branches=sum(
                b["terminal_count"] == 0 for r in rows for b in r["branches"]
            ),
            two_branch_denominator=512 if two else 0,
            same_action_sequence=sum(r["same_action_sequence"] is True for r in rows)
            if two
            else None,
            same_first_trajectory=sum(r["same_first_trajectory"] is True for r in rows)
            if two
            else None,
            complementary_success=sum(r["complementary_success"] is True for r in rows)
            if two
            else None,
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
                > {"single16": 512, "equal16": 256, "weighted16": 384}[arm]
                for r in rows
            ),
            rows=rows,
        )
    return dict(
        budget=budget,
        denominator=512,
        successes={a: sum(r[a]["success_any"] for r in blocks) for a in ARMS},
        work={
            a: {axis: sum(r[a]["ledger_usage"][axis] for r in blocks) for axis in AXES}
            for a in ARMS
        },
        unspent_work={
            a: {axis: sum(r[a]["unspent_work"][axis] for r in blocks) for axis in AXES}
            for a in ARMS
        },
        contrasts=contrasts,
        diagnostics=diagnostics,
    )


def extras(budget, cells, arm):
    rows = []
    for slot, seed in product(range(64), SEEDS):
        single = cells[slot, seed, budget, "single16"]
        diverse = cells[slot, seed, budget, arm]
        primary, secondary = diverse["diversity"]["branches"]
        single_ok, primary_ok, secondary_ok = (
            single["success_any"],
            primary["success"],
            secondary["success"],
        )
        full_first = single["diversity"]["branches"][0]["first_exact_work"]
        rows.append(
            dict(
                task_slot=slot,
                seed=seed,
                single=single_ok,
                primary=primary_ok,
                secondary=secondary_ok,
                allocation=diverse["success_any"],
                gain=diverse["success_any"] and not single_ok,
                loss=single_ok and not diverse["success_any"],
                rescued_late_success=single_ok and not primary_ok and secondary_ok,
                single_first_scores=None
                if full_first is None
                else full_first["legal_action_scores"],
                secondary_first_scores=None
                if secondary["first_exact_work"] is None
                else secondary["first_exact_work"]["legal_action_scores"],
            )
        )
        assert not primary_ok or single_ok
    counts = Counter(
        ("1" if r["single"] else "0")
        + ("1" if r["primary"] else "0")
        + ("1" if r["secondary"] else "0")
        for r in rows
    )
    source = []
    seed_rows = []
    for field, values, output in (
        ("task_slot", range(64), source),
        ("seed", SEEDS, seed_rows),
    ):
        for v in values:
            rs = [r for r in rows if r[field] == v]
            output.append(
                {
                    field: v,
                    "gains": sum(r["gain"] for r in rs),
                    "losses": sum(r["loss"] for r in rs),
                    "net": sum(int(r["gain"]) - int(r["loss"]) for r in rs),
                }
            )
    return dict(
        budget=budget,
        denominator=512,
        arm=arm,
        pattern_key="single_full/primary_allocated/secondary_allocated",
        success_patterns={
            k: counts[k]
            for k in ("000", "001", "010", "011", "100", "101", "110", "111")
        },
        practical_gain_sources=len({r["task_slot"] for r in rows if r["gain"]}),
        practical_loss_sources=len({r["task_slot"] for r in rows if r["loss"]}),
        practical_gain_seeds=len({r["seed"] for r in rows if r["gain"]}),
        practical_loss_seeds=len({r["seed"] for r in rows if r["loss"]}),
        full_continuation_extra_successes=sum(
            r["single"] and not r["primary"] for r in rows
        ),
        rescued_late_successes=sum(r["rescued_late_success"] for r in rows),
        lost_single_first_scores=sorted(
            r["single_first_scores"] for r in rows if r["loss"]
        ),
        gained_secondary_first_scores=sorted(
            r["secondary_first_scores"] for r in rows if r["gain"]
        ),
        by_source=source,
        by_seed=seed_rows,
        no_terminal={
            a: sum(
                cells[t, s, budget, a]["terminal_count"] == 0
                for t, s in product(range(64), SEEDS)
            )
            for a in ARMS
        },
        observed_first_discovery_cdf=[
            dict(
                scores=cap,
                full=sum(
                    r["single_first_scores"] is not None
                    and r["single_first_scores"] <= cap
                    for r in rows
                ),
                secondary=sum(
                    r["secondary_first_scores"] is not None
                    and r["secondary_first_scores"] <= cap
                    for r in rows
                ),
            )
            for cap in sorted({budget // 4, budget // 2, 3 * budget // 4, budget})
        ],
        cdf_claim="Descriptive first-hit counts at the fixed 128/256/384/512 boundaries; no counterfactual or wall-clock claim.",
        rows=rows,
    )


def clusters(blocks, arm, baseline):
    values = [
        sum(
            int(r[arm]["success_any"]) - int(r[baseline]["success_any"])
            for r in blocks
            if r["task_slot"] == slot
        )
        / len(SEEDS)
        for slot in range(64)
    ]
    mean = sum(values) / len(values)
    return dict(
        source_clusters=64,
        repeated_seeds=8,
        source_mean_differences=values,
        mean=mean,
        positive_sources=sum(v > 0 for v in values),
        tied_sources=sum(v == 0 for v in values),
        negative_sources=sum(v < 0 for v in values),
        descriptive_standard_error=math.sqrt(
            sum((v - mean) ** 2 for v in values) / (64 * 63)
        ),
        confidence_interval=None,
        interpretation="fixed_recipe_development_sample_not_population_confirmation",
    )


def main():
    plan = digested(PLAN)
    assert plan["deterministic_digest"] == DIGEST
    commit = digested(OUTPUT + "/COMMIT.json")
    summary = digested(OUTPUT + "/summary.json")
    assert commit["plan_digest"] == summary["plan_digest"] == DIGEST
    assert commit["source_head"] == HEAD
    assert commit["cell_count"] == 1536 and len(commit["cells"]) == 1536
    assert commit["status"] == "COMPLETE_NOT_YET_INDEPENDENTLY_ANALYZED"
    assert summary["status"] == "ALL_CELLS_REPLAYED_DEVELOPMENT_ANALYSIS_COMPLETE"
    assert summary["commit"] == reference(OUTPUT + "/COMMIT.json")
    cohort = checked(commit["cohort"])
    started = checked(commit["started"])
    checked(summary["analysis_start"])
    assert started["source_head"] == HEAD and started["plan_digest"] == DIGEST
    authorization = checked(started["authorization"]["approval"])
    qualification = checked(started["authorization"]["qualification"])
    assert (
        authorization["plan_digest"] == DIGEST
        and authorization["decision"] == "approved"
    )
    assert qualification["tested_commit"] == authorization["candidate_commit"]
    assert (
        qualification["repository_validation_pass"] is True
        and qualification["skipped_tests"] == 0
    )
    assert cohort["plan_digest"] == DIGEST and len(cohort["tasks"]) == 64
    assert len({t["source_multiset_fingerprint"] for t in cohort["tasks"]}) == 64
    assert len({t["task_fingerprint"] for t in cohort["tasks"]}) == 64
    assert not {t["source_multiset_fingerprint"] for t in cohort["tasks"]} & set(
        plan["exclusions"]["source_multiset_fingerprints"]
    )
    assert not {t["task_fingerprint"] for t in cohort["tasks"]} & set(
        plan["exclusions"]["task_fingerprints"]
    )
    cells, projections, first_terminals = {}, {}, {}
    branch_count = 0
    for index, key in enumerate(product(range(64), SEEDS, BUDGETS, ARMS)):
        row = commit["cells"][index]
        assert type(row["index"]) is int and row["index"] == index
        assert canonical(row["key"]) == canonical(list(key))
        assert row["file"]["path"] == f"{OUTPUT}/cell-{index:04d}.json"
        cell = checked(row["file"])
        assert cell["task"] == cohort["tasks"][key[0]]
        assert (
            cell["exploration_seed"] == key[1]
            and cell["spec"] == plan["arms"][ARMS.index(key[3])]
        )
        assert cell["budget_profile"]["budget"] == {
            axis: 512 if axis == "legal_action_scores" else 100000 for axis in AXES
        }
        weights = {"single16": (4,), "equal16": (2, 2), "weighted16": (3, 1)}[key[3]]
        assert len(cell["channels"]) == len(weights)
        for channel, weight in zip(cell["channels"], weights):
            assert channel["budget_profile"]["budget"] == {
                axis: value * weight // 4
                for axis, value in cell["budget_profile"]["budget"].items()
            }
        cells[key], projections[key], first_terminals[key] = cell_metrics(cell)
        branch_count += len(cell["channels"])
    prefixes = blocks = 0
    for slot, seed in product(range(64), SEEDS):
        single, equal, weighted = [projections[slot, seed, 512, arm] for arm in ARMS]
        for low, high in (
            (equal[0], weighted[0]),
            (weighted[0], single[0]),
            (equal[0], single[0]),
            (weighted[1], equal[1]),
        ):
            assert low["projection"] == high["projection"][: len(low["projection"])]
            prefixes += 1
        for arm in ARMS:
            branches = cells[slot, seed, 512, arm]["diversity"]["branches"]
            assert (
                not branches[0]["success"] or cells[slot, seed, 512, arm]["success_any"]
            )
        blocks += 1
    assert branch_count == 2560 and prefixes == summary["prefix_pairs"] == 2048
    assert blocks == summary["structural_blocks"] == 512
    reduction = dict(
        task_count=64,
        source_multiset_count=64,
        seed_count=8,
        cell_count=1536,
        by_budget=[
            reduce_budget(512, cells, plan["analysis"]["comparisons"], first_terminals)
        ],
        winner=None,
        scientific_decision=None,
        claim="exploratory_development_only_not_confirmation",
    )
    assert canonical(reduction) == canonical(summary["reduction"])
    for row in commit["cells"]:
        assert reference(row["file"]["path"]) == row["file"]
    assert {p.name for p in (ROOT / OUTPUT).iterdir()} == {
        "STARTED.json",
        "cohort.json",
        "COMMIT.json",
        "analysis.STARTED.json",
        "summary.json",
    } | {f"cell-{i:04d}.json" for i in range(1536)}
    result = dict(
        status="ALL_PLANNED_REDUCTIONS_RECOMPUTED_FROM_SAVED_EVENTS",
        plan=reference(PLAN),
        commit=reference(OUTPUT + "/COMMIT.json"),
        summary=reference(OUTPUT + "/summary.json"),
        source=reference(str(Path(__file__).relative_to(ROOT))),
        raw_cells=1536,
        branches=branch_count,
        prefix_pairs=prefixes,
        structural_blocks=blocks,
        reduction=reduction,
        allocation_diagnostics=[
            extras(512, cells, arm) for arm in ("equal16", "weighted16")
        ],
        generation=cohort["generation"],
        independent_reduction_implementation=True,
        independent_reviewer=False,
        generative_replay=False,
        additional_experiment=False,
        limitations=[
            "64 source clusters, not 512 independent observations",
            "Matched caps are not equal actual work",
            "Descriptive fixed-recipe evidence, not population confirmation or an optimal allocation",
        ],
    )
    result["deterministic_digest"] = digest(result)
    sys.stdout.buffer.write(canonical(result) + b"\n")


if __name__ == "__main__":
    main()
