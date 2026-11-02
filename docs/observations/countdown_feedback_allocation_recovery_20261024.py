#!/usr/bin/env python3
"""Read-only stdlib recomputation of COMMIT-bound allocation evidence after explicit recovery.

No engine/reducer import, cohort generation, search, or generative replay.
Print deterministic diagnostics; fixed raw files are never written.
Run from any cwd with Python 3.13: python3 -P -B <this file>.
"""

from __future__ import annotations

from collections import Counter
from fractions import Fraction
import math
import hashlib
from itertools import product
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = "artifacts/work/feedback-allocation-development-20261023-a"
PLAN = (
    "docs/preregistrations/countdown_feedback_allocation_development_20261023.plan.json"
)
DIGEST = "d88244d33e61f83bf878e77e3827ae3633ca6db08adb7f846a64631310f361e9"
HEAD = "35f3b1ba0342406914c0670d2e263d088df513a2"
ARMS = ("single16", "equal16", "weighted16")
SEEDS = tuple(range(65536, 65544))
BUDGETS = (512,)
COUNT = 256
RECOVERY = "artifacts/work/feedback-allocation-analysis-recovery-20261024-a"
RECOVERY_DIGEST = "26ed891bd45ac89577335029b01aec6bfacc38a483a69709a468b0a933fc780b"
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


def rational(x):
    return None if x is None else [x.numerator, x.denominator]


def cluster_readout(blocks, contract):
    # Sum-of-squares identity is independent of the production deviations loop.
    nets = [
        sum(
            int(r["weighted16"]["success_any"]) - int(r["single16"]["success_any"])
            for r in blocks
            if r["task_slot"] == slot
        )
        for slot in range(COUNT)
    ]
    values = [Fraction(n, len(SEEDS)) for n in nets]
    total = sum(values, Fraction())
    mean = total / COUNT
    variance = (sum(x * x for x in values) - total * total / COUNT) / (COUNT - 1)
    interval = half = None
    status, reason = "UNRESOLVED", "insufficient_source_clusters"
    if COUNT >= contract["minimum_clusters_for_interval"]:
        if variance == 0:
            reason = "degenerate_source_variance"
        else:
            half = 2 * math.sqrt(float(variance) / COUNT)
            interval = [float(mean) - half, float(mean) + half]
            if half > contract["target_half_width"]:
                status, reason = "IMPRECISE", "precision_target_not_met"
            elif interval[0] > contract["practical_uplift"]:
                status, reason = (
                    "PROMISING_FOR_FRESH_CONFIRMATION",
                    "model_interval_above_practical_threshold",
                )
            elif interval[1] <= contract["practical_uplift"]:
                status, reason = (
                    "NO_PRACTICAL_UPLIFT_SIGNAL",
                    "model_interval_not_above_practical_threshold",
                )
            else:
                reason = "model_interval_crosses_practical_threshold"
    return dict(
        contract=contract,
        source_count=COUNT,
        fixed_seed_count=len(SEEDS),
        repeated_block_count=len(blocks),
        source_differences=[rational(x) for x in values],
        mean_rational=rational(mean),
        sample_source_variance_rational=rational(variance),
        estimate=float(mean),
        approximate_interval=interval,
        half_width=half,
        precision_target_met=None
        if half is None
        else half <= contract["target_half_width"],
        development_readout=status,
        reason=reason,
        winner=None,
        scientific_decision=None,
    )


def subtract_counts(total, removed):
    return {
        k: (
            {q: total[k][q] - removed[k][q] for q in total[k]}
            if isinstance(total[k], dict)
            else total[k] - removed[k]
        )
        for k in total
    }


def reduced(plan, cells):
    blocks = [
        dict(task_slot=t, seed=s, **{a: cells[t, s, 512, a] for a in ARMS})
        for t, s in product(range(COUNT), SEEDS)
    ]
    contrasts = []
    for a, b in plan["analysis"]["comparisons"]:
        total = contrast(blocks, a, b)
        sources = [
            contrast([r for r in blocks if r["task_slot"] == t], a, b)
            for t in range(COUNT)
        ]
        seeds = [contrast([r for r in blocks if r["seed"] == s], a, b) for s in SEEDS]
        contrasts.append(
            dict(
                arm=a,
                baseline=b,
                **total,
                by_source=[dict(task_slot=t, **v) for t, v in enumerate(sources)],
                by_seed=[dict(seed=s, **v) for s, v in zip(SEEDS, seeds)],
                leave_one_source_out=[
                    dict(omitted=t, **subtract_counts(total, v))
                    for t, v in enumerate(sources)
                ],
                leave_one_seed_out=[
                    dict(omitted=s, **subtract_counts(total, v))
                    for s, v in zip(SEEDS, seeds)
                ],
            )
        )
    diagnostics = {}
    for arm in ARMS:
        two = arm != "single16"
        cap = {"single16": 512, "equal16": 256, "weighted16": 384}[arm]
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
            denominator=len(blocks),
            two_branch_denominator=len(blocks) if two else 0,
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
                and r["full_budget_first_exact_work"]["legal_action_scores"] > cap
                for r in rows
            ),
            rows=rows,
        )
    return dict(
        task_count=COUNT,
        source_multiset_count=COUNT,
        seed_count=len(SEEDS),
        cell_count=len(cells),
        by_budget=[
            dict(
                budget=512,
                denominator=len(blocks),
                successes={a: sum(r[a]["success_any"] for r in blocks) for a in ARMS},
                work={
                    a: {
                        axis: sum(r[a]["ledger_usage"][axis] for r in blocks)
                        for axis in AXES
                    }
                    for a in ARMS
                },
                contrasts=contrasts,
                diagnostics=diagnostics,
                primary_source_readout=cluster_readout(
                    blocks, plan["analysis"]["uncertainty"]
                ),
            )
        ],
        winner=None,
        scientific_decision=None,
        claim="exploratory_development_only_not_confirmation",
    )


def additional(cells, reduction, plan):
    rows = []
    for t, s in product(range(COUNT), SEEDS):
        summaries = {a: cells[t, s, 512, a] for a in ARMS}
        branches = {a: summaries[a]["diversity"]["branches"] for a in ARMS}
        bs = dict(
            primary256=branches["equal16"][0],
            primary384=branches["weighted16"][0],
            primary512=branches["single16"][0],
            secondary128=branches["weighted16"][1],
            secondary256=branches["equal16"][1],
        )
        ok = {k: v["success"] for k, v in bs.items()}
        assert not ok["primary256"] or ok["primary384"]
        assert not ok["primary384"] or ok["primary512"]
        assert not ok["secondary128"] or ok["secondary256"]
        row = dict(
            task_slot=t,
            seed=s,
            branch_success=ok,
            success={a: summaries[a]["success_any"] for a in ARMS},
            first_exact_work={k: v["first_exact_work"] for k, v in bs.items()},
            no_terminal={a: summaries[a]["terminal_count"] == 0 for a in ARMS},
        )
        rows.append(row)
    output = {}
    for a, b in plan["analysis"]["comparisons"]:
        detail = []
        for row in rows:
            gain = row["success"][a] and not row["success"][b]
            loss = row["success"][b] and not row["success"][a]
            if gain or loss:
                detail.append(dict(**row, outcome="gain" if gain else "loss"))
        saved = next(
            x
            for x in reduction["by_budget"][0]["contrasts"]
            if x["arm"] == a and x["baseline"] == b
        )
        source_nets = [v["net"] for v in saved["by_source"]]
        output[a + "_minus_" + b] = dict(
            denominator=2048,
            source_clusters=256,
            discordant_blocks=detail,
            gain_sources=len(
                {r["task_slot"] for r in detail if r["outcome"] == "gain"}
            ),
            loss_sources=len(
                {r["task_slot"] for r in detail if r["outcome"] == "loss"}
            ),
            gain_seeds=len({r["seed"] for r in detail if r["outcome"] == "gain"}),
            loss_seeds=len({r["seed"] for r in detail if r["outcome"] == "loss"}),
            source_net_signs=dict(
                positive=sum(n > 0 for n in source_nets),
                zero=sum(n == 0 for n in source_nets),
                negative=sum(n < 0 for n in source_nets),
            ),
            source_net_histogram=dict(sorted(Counter(map(str, source_nets)).items())),
            loo_source_net_range=[
                min(x["net"] for x in saved["leave_one_source_out"]),
                max(x["net"] for x in saved["leave_one_source_out"]),
            ],
            loo_seed_net_range=[
                min(x["net"] for x in saved["leave_one_seed_out"]),
                max(x["net"] for x in saved["leave_one_seed_out"]),
            ],
        )
    allocation = {}
    for arm, primary, secondary, cap in (
        ("equal16", "primary256", "secondary256", 256),
        ("weighted16", "primary384", "secondary128", 384),
    ):
        gains = [r for r in rows if r["success"][arm] and not r["success"]["single16"]]
        losses = [r for r in rows if not r["success"][arm] and r["success"]["single16"]]
        secondary_only = [
            r
            for r in rows
            if not r["branch_success"][primary] and r["branch_success"][secondary]
        ]
        rescued = [r for r in secondary_only if r["success"]["single16"]]
        assert all(
            r["branch_success"][secondary] and not r["branch_success"][primary]
            for r in gains
        )
        assert all(
            r["first_exact_work"]["primary512"]["legal_action_scores"] > cap
            for r in losses
        )
        patterns = Counter(
            "".join(
                str(int(r["branch_success"][k]))
                for k in ("primary512", primary, secondary)
            )
            for r in rows
        )
        allocation[arm] = dict(
            pattern_key="single_full/allocated_primary/allocated_secondary",
            success_patterns=dict(sorted(patterns.items())),
            full_continuation_extra_successes=sum(
                r["branch_success"]["primary512"] and not r["branch_success"][primary]
                for r in rows
            ),
            secondary_only_successes=len(secondary_only),
            rescued_late_successes=len(rescued),
            pure_additional_successes=len(gains),
            lost_full_continuation_successes=len(losses),
            lost_full_first_scores=sorted(
                r["first_exact_work"]["primary512"]["legal_action_scores"]
                for r in losses
            ),
            gain_secondary_first_scores=sorted(
                r["first_exact_work"][secondary]["legal_action_scores"] for r in gains
            ),
            all_losses_after_allocated_primary_cap=True,
        )
    # The unequal/equal comparison is fully observed, not an unrun counterfactual.
    switch = output["weighted16_minus_equal16"]["discordant_blocks"]
    assert all(
        r["branch_success"]["primary384"]
        and not r["branch_success"]["primary256"]
        and not r["branch_success"]["secondary256"]
        for r in switch
        if r["outcome"] == "gain"
    )
    assert all(
        r["branch_success"]["secondary256"]
        and not r["branch_success"]["secondary128"]
        and not r["branch_success"]["primary384"]
        for r in switch
        if r["outcome"] == "loss"
    )
    limits = plan["budget_profiles"][0]["budget"]
    work = reduction["by_budget"][0]["work"]
    return dict(
        comparisons=output,
        allocations=allocation,
        observed_weighted_equal_tradeoff="All gains are primary256_to384 discoveries; all losses are secondary128_to256 discoveries, with no success in the other observed branch.",
        no_terminal={a: sum(r["no_terminal"][a] for r in rows) for a in ARMS},
        work_limits_per_arm={k: v * 2048 for k, v in limits.items()},
        unspent_per_arm={
            a: {k: limits[k] * 2048 - work[a][k] for k in AXES} for a in ARMS
        },
        first_discovery_cdf=[
            dict(
                scores=cap,
                **{
                    branch: sum(
                        r["first_exact_work"][branch] is not None
                        and r["first_exact_work"][branch]["legal_action_scores"] <= cap
                        for r in rows
                    )
                    for branch in ("primary512", "secondary256")
                },
            )
            for cap in (128, 256, 384, 512)
        ],
        cdf_claim="Observed trace discovery times; not estimates of unrun allocations or a new ratio sweep.",
        block_rows=rows,
    )


def main():
    plan = digested(PLAN)
    assert plan["deterministic_digest"] == DIGEST
    commit = digested(OUTPUT + "/COMMIT.json")
    summary = digested(RECOVERY + "/summary.json")
    assert commit["plan_digest"] == summary["plan_digest"] == DIGEST
    assert (
        commit["source_head"] == HEAD
        and commit["cell_count"] == len(commit["cells"]) == 6144
    )
    assert summary["status"] == "ALL_CELLS_REPLAYED_RECOVERY_ANALYSIS_COMPLETE"
    assert summary["recovery_digest"] == RECOVERY_DIGEST
    assert summary["commit"] == reference(OUTPUT + "/COMMIT.json")
    cohort = checked(commit["cohort"])
    checked(commit["started"])
    checked(summary["analysis_start"])
    assert len(cohort["tasks"]) == COUNT
    assert len({t["source_multiset_fingerprint"] for t in cohort["tasks"]}) == COUNT
    assert not {t["source_multiset_fingerprint"] for t in cohort["tasks"]} & set(
        plan["exclusions"]["source_multiset_fingerprints"]
    )
    assert not {t["task_fingerprint"] for t in cohort["tasks"]} & set(
        plan["exclusions"]["task_fingerprints"]
    )
    cells = {}
    branch_count = prefixes = blocks = 0
    for t, s in product(range(COUNT), SEEDS):
        projections = {}
        for a in ARMS:
            key = (t, s, 512, a)
            index = len(cells)
            row = commit["cells"][index]
            assert type(row["index"]) is int and row["index"] == index
            assert canonical(row["key"]) == canonical(list(key))
            assert row["file"]["path"] == f"{OUTPUT}/cell-{index:04d}.json"
            cell = checked(row["file"])
            assert cell["task"] == cohort["tasks"][t]
            assert cell["exploration_seed"] == s and cell["spec"]["arm"] == a
            assert (
                cell["budget_profile"]["budget"] == plan["budget_profiles"][0]["budget"]
            )
            assert len(cell["channels"]) == (1 if a == "single16" else 2)
            fraction = {"single16": (1, 1), "equal16": (1, 2), "weighted16": (3, 4)}[a]
            assert cell["spec"]["primary_fraction"] == list(fraction)
            assert (
                cell["spec"]["reallocate_unspent_work"] is False
                and cell["spec"]["early_stop_on_success"] is False
            )
            assert (
                cell["spec"]["shared_cache"] is False
                and cell["spec"]["shared_posterior"] is False
            )
            for j, ch in enumerate(cell["channels"]):
                cap = {
                    k: v * fraction[0] // fraction[1]
                    for k, v in cell["budget_profile"]["budget"].items()
                }
                if j:
                    cap = {
                        k: v - cap[k]
                        for k, v in cell["budget_profile"]["budget"].items()
                    }
                assert ch["budget_profile"]["budget"] == cap
            cells[key], projections[a] = cell_metrics(cell)
            branch_count += len(cell["channels"])
        for lo, hi in (
            (projections["equal16"][0], projections["weighted16"][0]),
            (projections["weighted16"][0], projections["single16"][0]),
            (projections["weighted16"][1], projections["equal16"][1]),
        ):
            assert lo["projection"] == hi["projection"][: len(lo["projection"])]
            prefixes += 1
        blocks += 1
    assert (branch_count, prefixes, blocks) == (10240, 6144, 2048)
    reduction = reduced(plan, cells)
    assert canonical(reduction) == canonical(summary["reduction"])
    assert summary["work"] == {
        axis: sum(reduction["by_budget"][0]["work"][a][axis] for a in ARMS)
        for axis in AXES
    }
    extra = additional(cells, reduction, plan)
    for row in commit["cells"]:
        assert reference(row["file"]["path"]) == row["file"]
    assert {p.name for p in (ROOT / OUTPUT).iterdir()} == {
        "STARTED.json",
        "cohort.json",
        "COMMIT.json",
        "analysis.STARTED.json",
    } | {f"cell-{i:04d}.json" for i in range(6144)}
    assert not (ROOT / OUTPUT / "summary.json").exists()
    result = dict(
        status="ALL_PLANNED_REDUCTIONS_RECOMPUTED_FROM_SAVED_EVENTS",
        plan=reference(PLAN),
        commit=reference(OUTPUT + "/COMMIT.json"),
        summary=reference(RECOVERY + "/summary.json"),
        source=reference(str(Path(__file__).relative_to(ROOT))),
        event_checker_origin=reference(
            "docs/observations/countdown_feedback_diversity_development_20261022.py"
        ),
        raw_cells=6144,
        branches=branch_count,
        branch_prefix_pairs=prefixes,
        structural_blocks=blocks,
        reduction=reduction,
        allocation_diagnostics=extra,
        generation=cohort["generation"],
        independent_implementation=True,
        independent_reviewer=False,
        generative_replay=False,
        additional_experiment=False,
        limitations=[
            "256 source clusters, not 2048 independent sources",
            "The interval is model-based conditional on fixed seeds and filtered deterministic generation",
            "Negative primary preserved; secondary results do not select a winner",
            "Original interrupted analysis completion and reboot trigger remain UNKNOWN",
        ],
    )
    result["deterministic_digest"] = digest(result)
    sys.stdout.buffer.write(canonical(result) + b"\n")


if __name__ == "__main__":
    main()
