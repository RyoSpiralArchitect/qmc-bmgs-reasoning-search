"""Read-only recount of committed traces; no search or experiment imports.

Run from any directory with Python 3.13. Raw files must remain at their
manifest paths in this checkout. Writes only JSON to stdout.
"""

from collections import Counter
import hashlib
from itertools import product
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = "artifacts/work/feedback-portfolio-development-20261020-a"
PLAN = (
    "docs/preregistrations/countdown_feedback_portfolio_development_20261020.plan.json"
)
ARMS = ("exact", "dense16", "calibrated1", "protected1")
SEEDS = tuple(range(16384, 16392))
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
COMPARISONS = (
    ("calibrated1", "dense16"),
    ("protected1", "calibrated1"),
    ("protected1", "exact"),
    ("dense16", "exact"),
)


def canonical(value):
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode()


def strict_pairs(pairs):
    result = {}
    for key, value in pairs:
        assert key not in result, key
        result[key] = value
    return result


def read(path):
    p = ROOT / path
    assert p.is_file() and not p.is_symlink(), path
    return p.read_bytes()


def reference(path):
    raw = read(path)
    return dict(path=path, byte_count=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def load(path):
    raw = read(path)
    value = json.loads(raw, object_pairs_hook=strict_pairs)
    assert canonical(value) == raw, path
    if "deterministic_digest" in value:
        core = {k: v for k, v in value.items() if k != "deterministic_digest"}
        # Repository digest excludes the trailing newline used by files.
        assert (
            hashlib.sha256(canonical(core).rstrip(b"\n")).hexdigest()
            == value["deterministic_digest"]
        ), path
    return value


def check(row):
    assert reference(row["path"]) == row, row["path"]


def branch(channel):
    events = channel["search_record"]["events"]
    finish = events[-1]["payload"]["summary"]
    terminals = [
        e["payload"]["verification"] for e in events if e["kind"] == "terminal_verified"
    ]
    assert all(
        v["source_use_exact"] and type(v["final_value"]) is int for v in terminals
    )
    errors = [abs(v["final_value"] - v["target"]) for v in terminals]
    successes = [e == 0 for e in errors]
    assert successes == [v["success"] for v in terminals]
    assert any(successes) == finish["success_any"]
    assert len(terminals) == finish["terminal_count"]
    charged = {axis: 0 for axis in AXES}
    first_exact_work = None
    for event in events:
        charge = event.get("charge")
        if charge:
            for axis in AXES:
                charged[axis] += charge["delta"][axis]
            assert charged == charge["usage_after"]
        if (
            event["kind"] == "terminal_verified"
            and event["payload"]["verification"]["success"]
            and first_exact_work is None
        ):
            first_exact_work = dict(charged)
    assert charged == finish["ledger_usage"]
    choices = [
        {k: e["payload"][k] for k in ("state", "action", "trajectory_index", "depth")}
        for e in events
        if e["kind"] == "selection_committed"
    ]
    prefix = []
    for event in events:
        if event["kind"] == "selection_committed":
            prefix.append(
                {
                    k: event["payload"][k]
                    for k in ("state", "action", "trajectory_index", "depth")
                }
            )
        elif event["kind"] == "terminal_verified":
            break
    return dict(
        success=any(successes),
        minimum_error=min(errors, default=None),
        terminal_count=len(terminals),
        first_exact_work=first_exact_work,
        choices=choices,
        first_trajectory=prefix,
        ledger_usage=finish["ledger_usage"],
        stop_reason=finish["stop_reason"],
        blocked_axes=finish["stop_blocked_axes"],
        attempted_charge=finish["stop_attempted_charge"],
        incomplete_trajectory_count=finish["incomplete_trajectory_count"],
    )


def contrast(data, coordinates, arm, baseline):
    pairs = [(data[(*k, arm)], data[(*k, baseline)]) for k in coordinates]
    gains = sum(a["success"] and not b["success"] for a, b in pairs)
    losses = sum(b["success"] and not a["success"] for a, b in pairs)
    errors = dict(win=0, tie=0, loss=0, missing=0)
    for a, b in pairs:
        x, y = a["minimum_error"], b["minimum_error"]
        category = (
            "missing"
            if x is None or y is None
            else "win"
            if x < y
            else "loss"
            if x > y
            else "tie"
        )
        errors[category] += 1
    return dict(
        denominator=len(pairs),
        gains=gains,
        losses=losses,
        net=gains - losses,
        minimum_error=errors,
    )


def diagnose():
    plan = load(PLAN)
    commit = load(OUTPUT + "/COMMIT.json")
    summary = load(OUTPUT + "/summary.json")
    check(summary["commit"])
    check(summary["analysis_start"])
    check(commit["started"])
    check(commit["cohort"])
    cohort = load(commit["cohort"]["path"])
    assert (
        summary["plan_digest"] == commit["plan_digest"] == plan["deterministic_digest"]
    )
    assert summary["prefix_pairs"] == 256
    assert len(commit["cells"]) == commit["cell_count"] == 512
    data, raw, cell_rows = {}, {}, []
    for index, key in enumerate(product(range(8), SEEDS, BUDGETS, ARMS)):
        row = commit["cells"][index]
        assert row["index"] == index and row["key"] == list(key)
        check(row["file"])
        record = load(row["file"]["path"])
        channels = [branch(c) for c in record["channels"]]
        errors = [
            c["minimum_error"] for c in channels if c["minimum_error"] is not None
        ]
        item = dict(
            success=any(c["success"] for c in channels),
            minimum_error=min(errors, default=None),
            terminal_count=sum(c["terminal_count"] for c in channels),
            ledger_usage={a: sum(c["ledger_usage"][a] for c in channels) for a in AXES},
            channels=channels,
        )
        s = record["summary"]
        assert (
            item["success"],
            item["minimum_error"],
            item["terminal_count"],
            item["ledger_usage"],
        ) == (
            s["success_any"],
            s["minimum_terminal_error"],
            s["terminal_count"],
            s["ledger_usage"],
        )
        assert (
            s["budget_valid"]
            and s["readout_extra_verifier_calls"] == 0
            and s["provider_calls"] == 0
        )
        assert all(s["unspent_work"][a] >= 0 for a in AXES)
        data[key], raw[key] = item, record
        cell_rows.append(
            dict(
                key=list(key),
                success=item["success"],
                minimum_error=item["minimum_error"],
                terminal_count=item["terminal_count"],
                primary_used=item["ledger_usage"]["legal_action_scores"],
                channels=[
                    {
                        k: v
                        for k, v in c.items()
                        if k not in ("choices", "first_trajectory")
                    }
                    for c in channels
                ],
            )
        )

    budgets, reductions = [], []
    for budget in BUDGETS:
        keys = [(slot, seed, budget) for slot, seed in product(range(8), SEEDS)]
        comparisons = []
        for arm, baseline in COMPARISONS:
            comparisons.append(
                dict(
                    arm=arm,
                    baseline=baseline,
                    **contrast(data, keys, arm, baseline),
                    by_source=[
                        dict(
                            task_slot=s,
                            **contrast(
                                data, [k for k in keys if k[0] == s], arm, baseline
                            ),
                        )
                        for s in range(8)
                    ],
                    by_seed=[
                        dict(
                            seed=s,
                            **contrast(
                                data, [k for k in keys if k[1] == s], arm, baseline
                            ),
                        )
                        for s in SEEDS
                    ],
                    leave_one_source_out=[
                        dict(
                            omitted=s,
                            **contrast(
                                data, [k for k in keys if k[0] != s], arm, baseline
                            ),
                        )
                        for s in range(8)
                    ],
                    leave_one_seed_out=[
                        dict(
                            omitted=s,
                            **contrast(
                                data, [k for k in keys if k[1] != s], arm, baseline
                            ),
                        )
                        for s in SEEDS
                    ],
                )
            )
        reduction = dict(
            budget=budget,
            denominator=64,
            successes={a: sum(data[(*k, a)]["success"] for k in keys) for a in ARMS},
            work={
                a: {
                    axis: sum(data[(*k, a)]["ledger_usage"][axis] for k in keys)
                    for axis in AXES
                }
                for a in ARMS
            },
            contrasts=comparisons,
        )
        reductions.append(reduction)
        arm_details = {}
        for arm in ARMS:
            items = [data[(*k, arm)] for k in keys]
            arm_details[arm] = dict(
                no_terminal=sum(x["terminal_count"] == 0 for x in items),
                terminal_count=sum(x["terminal_count"] for x in items),
                unused_primary=64 * budget
                - sum(x["ledger_usage"]["legal_action_scores"] for x in items),
                stop_reasons=dict(
                    Counter(c["stop_reason"] for x in items for c in x["channels"])
                ),
            )
        protected = [data[(*k, "protected1")] for k in keys]
        attribution = Counter()
        equal_choices = equal_first = 0
        for item in protected:
            a, b = item["channels"]
            attribution[
                "both"
                if a["success"] and b["success"]
                else "exact_only"
                if a["success"]
                else "calibrated_only"
                if b["success"]
                else "neither"
            ] += 1
            equal_choices += a["choices"] == b["choices"]
            equal_first += a["first_trajectory"] == b["first_trajectory"]
        paired_choice_equal = {}
        for arm, baseline in (("calibrated1", "exact"), ("dense16", "exact")):
            paired_choice_equal[arm + "_vs_" + baseline] = sum(
                data[(*k, arm)]["channels"][0]["choices"]
                == data[(*k, baseline)]["channels"][0]["choices"]
                for k in keys
            )
        differences = []
        for arm, baseline in COMPARISONS:
            for k in keys:
                a, b = data[(*k, arm)], data[(*k, baseline)]
                if a["success"] != b["success"]:
                    differences.append(
                        dict(
                            task_slot=k[0],
                            seed=k[1],
                            arm=arm,
                            baseline=baseline,
                            outcome="gain" if a["success"] else "loss",
                            arm_error=a["minimum_error"],
                            baseline_error=b["minimum_error"],
                        )
                    )
        budgets.append(
            dict(
                budget=budget,
                denominator=64,
                arms=arm_details,
                protected_success_attribution={
                    k: attribution[k]
                    for k in ("both", "exact_only", "calibrated_only", "neither")
                },
                protected_same_all_choices=equal_choices,
                protected_same_first_trajectory=equal_first,
                single_channel_same_all_choices=paired_choice_equal,
                exact_success_discordances=differences,
            )
        )
    reproduced = dict(
        task_count=8,
        source_multiset_count=8,
        seed_count=8,
        cell_count=512,
        by_budget=reductions,
        winner=None,
        scientific_decision=None,
        claim="exploratory_development_only_not_confirmation",
    )
    assert reproduced == summary["reduction"], (
        "independent terminal-based full reduction mismatch"
    )

    half_matches = {}
    for arm, index in (("exact", 0), ("calibrated1", 1)):
        count = 0
        for slot, seed in product(range(8), SEEDS):
            low = raw[(slot, seed, 256, arm)]["channels"][0]["search_record"]
            half = raw[(slot, seed, 512, "protected1")]["channels"][index][
                "search_record"
            ]

            def projection(r):
                return [
                    (e["kind"], e["payload"], e.get("charge"))
                    for e in r["events"]
                    if e["kind"] != "search_finished"
                ]

            count += projection(low) == projection(half)
        half_matches[arm] = count
    return dict(
        schema_version="feedback-portfolio-posthoc-diagnostics/v1",
        plan=reference(PLAN),
        commit=reference(OUTPUT + "/COMMIT.json"),
        summary=reference(OUTPUT + "/summary.json"),
        cohort=cohort,
        independent_terminal_reduction_matches=True,
        replay_performed=False,
        planned_reduction=reproduced,
        diagnostic_timing="posthoc_after_fixed_run_and_all_cell_replay",
        protected_512_vs_standalone_256_full_event_projection_matches=half_matches,
        by_budget=budgets,
        cells=cell_rows,
        claim="finite_development_observations_not_population_or_mechanism_confirmation",
    )


if __name__ == "__main__":
    print(canonical(diagnose()).decode(), end="")
