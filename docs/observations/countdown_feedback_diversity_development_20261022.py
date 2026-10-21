#!/usr/bin/env python3
"""Read-only stdlib recomputation of COMMIT-bound diversity evidence.

No engine/reducer import, cohort generation, search, or generative replay.
Print deterministic diagnostics; fixed raw files are never written.
Run from any cwd with Python 3.13: python3 -P -B <this file>.
"""

from __future__ import annotations

from collections import Counter
import hashlib
from itertools import product
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = "artifacts/work/feedback-diversity-development-20261022-a"
PLAN = (
    "docs/preregistrations/countdown_feedback_diversity_development_20261022.plan.json"
)
DIGEST = "b9277ed5f4d537276dd612861bde6bb3bb322f53afae50b8456713839fefc4a4"
HEAD = "cbc8abc40907097757a39bcd1b29f3aec6562f77"
ARMS = ("single16", "paired16", "diverse16")
SEEDS = tuple(range(32768, 32776))
BUDGETS = (256, 512)
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
    first_exact = None
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
    return summary, compact


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


def reduce_budget(budget, cells, comparisons):
    blocks = [
        dict(task_slot=t, seed=s, **{a: cells[t, s, budget, a] for a in ARMS})
        for t, s in product(range(32), SEEDS)
    ]
    contrasts = []
    for a, b in comparisons:
        contrasts.append(
            dict(
                arm=a,
                baseline=b,
                **contrast(blocks, a, b),
                by_source=[
                    dict(
                        task_slot=t,
                        **contrast([r for r in blocks if r["task_slot"] == t], a, b),
                    )
                    for t in range(32)
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
                    for t in range(32)
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
            denominator=256,
            two_branch_denominator=256 if two else 0,
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
            lost_success_beyond_half_budget=sum(
                r["loses_full_budget_success"]
                and r["full_budget_first_exact_work"]["legal_action_scores"]
                > budget // 2
                for r in rows
            ),
            rows=rows,
        )
    return dict(
        budget=budget,
        denominator=256,
        successes={a: sum(r[a]["success_any"] for r in blocks) for a in ARMS},
        work={
            a: {axis: sum(r[a]["ledger_usage"][axis] for r in blocks) for axis in AXES}
            for a in ARMS
        },
        contrasts=contrasts,
        diagnostics=diagnostics,
    )


def extras(budget, cells):
    rows = []
    for slot, seed in product(range(32), SEEDS):
        single, paired, diverse = [cells[slot, seed, budget, a] for a in ARMS]
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
                diverse=diverse["success_any"],
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
        assert paired["success_any"] == primary_ok
    counts = Counter(
        ("1" if r["single"] else "0")
        + ("1" if r["primary"] else "0")
        + ("1" if r["secondary"] else "0")
        for r in rows
    )
    source = []
    seed_rows = []
    for field, values, output in (
        ("task_slot", range(32), source),
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
        denominator=256,
        pattern_key="single_full/primary_half/secondary_half",
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
                for t, s in product(range(32), SEEDS)
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
        cdf_claim="Descriptive discovery times in observed traces, not an unrun allocation result.",
        rows=rows,
    )


def main():
    plan = digested(PLAN)
    assert plan["deterministic_digest"] == DIGEST
    commit = digested(OUTPUT + "/COMMIT.json")
    summary = digested(OUTPUT + "/summary.json")
    assert commit["plan_digest"] == summary["plan_digest"] == DIGEST
    assert commit["source_head"] == HEAD
    assert commit["cell_count"] == 1536 and len(commit["cells"]) == 1536
    assert summary["status"] == "ALL_CELLS_REPLAYED_DEVELOPMENT_ANALYSIS_COMPLETE"
    assert summary["commit"] == reference(OUTPUT + "/COMMIT.json")
    cohort = checked(commit["cohort"])
    checked(commit["started"])
    checked(summary["analysis_start"])
    assert cohort["plan_digest"] == DIGEST and len(cohort["tasks"]) == 32
    assert len({t["source_multiset_fingerprint"] for t in cohort["tasks"]}) == 32
    assert not {t["source_multiset_fingerprint"] for t in cohort["tasks"]} & set(
        plan["exclusions"]["source_multiset_fingerprints"]
    )
    assert not {t["task_fingerprint"] for t in cohort["tasks"]} & set(
        plan["exclusions"]["task_fingerprints"]
    )
    cells, projections = {}, {}
    branch_count = 0
    for index, key in enumerate(product(range(32), SEEDS, BUDGETS, ARMS)):
        row = commit["cells"][index]
        assert type(row["index"]) is int and row["index"] == index
        assert canonical(row["key"]) == canonical(list(key))
        assert row["file"]["path"] == f"{OUTPUT}/cell-{index:04d}.json"
        cell = checked(row["file"])
        assert cell["task"] == cohort["tasks"][key[0]]
        assert cell["exploration_seed"] == key[1] and cell["spec"]["arm"] == key[3]
        assert cell["budget_profile"]["budget"]["legal_action_scores"] == key[2]
        assert len(cell["channels"]) == (1 if key[3] == "single16" else 2)
        cells[key], projections[key] = cell_metrics(cell)
        branch_count += len(cell["channels"])
    prefixes = blocks = 0
    for t, s, a in product(range(32), SEEDS, ARMS):
        low, high = [projections[t, s, b, a] for b in BUDGETS]
        for lo, hi in zip(low, high):
            assert lo["projection"] == hi["projection"][: len(lo["projection"])]
        prefixes += 1
    for t, s, b in product(range(32), SEEDS, BUDGETS):
        single, paired, diverse = [projections[t, s, b, a] for a in ARMS]
        assert paired[0]["trace_digest"] == paired[1]["trace_digest"]
        assert paired[0]["channel_digest"] == diverse[0]["channel_digest"]
        assert (
            paired[0]["projection"]
            == single[0]["projection"][: len(paired[0]["projection"])]
        )
        assert (
            not cells[t, s, b, "paired16"]["success_any"]
            or cells[t, s, b, "single16"]["success_any"]
        )
        assert (
            not cells[t, s, b, "paired16"]["success_any"]
            or cells[t, s, b, "diverse16"]["success_any"]
        )
        blocks += 1
    assert branch_count == 2560 and prefixes == summary["prefix_pairs"] == 768
    assert blocks == summary["structural_blocks"] == 512
    reduction = dict(
        task_count=32,
        source_multiset_count=32,
        seed_count=8,
        cell_count=1536,
        by_budget=[
            reduce_budget(b, cells, plan["analysis"]["comparisons"]) for b in BUDGETS
        ],
        winner=None,
        scientific_decision=None,
        claim="exploratory_development_only_not_confirmation",
    )
    assert canonical(reduction) == canonical(summary["reduction"])
    # Finish by reauthenticating the controlling data after recomputation.
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
        allocation_diagnostics=[extras(b, cells) for b in BUDGETS],
        generation=cohort["generation"],
        independent_implementation=True,
        independent_reviewer=False,
        generative_replay=False,
        additional_experiment=False,
        limitations=[
            "32 source clusters, not 256 independent sources per budget",
            "Secondary-only success is not always a gain against full continuation",
            "Unequal allocations were not run or estimated here",
        ],
    )
    result["deterministic_digest"] = digest(result)
    sys.stdout.buffer.write(canonical(result) + b"\n")


if __name__ == "__main__":
    main()
