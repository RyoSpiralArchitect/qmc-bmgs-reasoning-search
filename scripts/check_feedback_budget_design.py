#!/usr/bin/env python3
"""Check a scientific design and synthetic arithmetic, never execute search."""

from __future__ import annotations

import argparse
from collections import Counter
from fractions import Fraction
import hashlib
from itertools import product
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESIGN = "docs/strategy/countdown_thompson_feedback_budget_factorial_v6.md"
DESIGN_SHA256 = "7b3ebcc7d1b3c3a591b6f3baa574492085bc91c53ee3cccc9fe031d3d70ef01f"
TASK_COUNT = 12
GENERATION_SEED = 26090401
SEEDS = (8192, 8193, 8194, 8195)
SCALES = (0, 16)
BUDGETS = (256, 512)
AXES = (
    "proposal_state_evaluations",
    "proposal_action_scores",
    "legal_action_scores",
    "generated_perturbation_coordinates",
    "edge_selections",
    "transitions",
    "verifier_calls",
)
ARMS = ("Y0_256", "Y16_256", "Y0_512", "Y16_512")


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=True
    ).encode()


def ratio(numerator: int, denominator: int) -> dict:
    value = Fraction(numerator, denominator)
    return {"numerator": value.numerator, "denominator": value.denominator}


def guard_profiles() -> dict[int, dict[str, int]]:
    maximum = max(BUDGETS)
    guards = dict(
        zip(
            AXES,
            (
                maximum // 3 + 2,
                maximum + 60 + 1,
                maximum,
                maximum + 60,
                maximum // 3 + 1,
                maximum // 3 + 1,
                maximum // 15 + 1,
            ),
        )
    )
    return {b: {**guards, "legal_action_scores": b} for b in BUDGETS}


def planned_coordinates() -> list[tuple[int, int, int, int]]:
    """Ordinal task slots, NOT materialized task identities or execution cells."""
    return list(product(range(TASK_COUNT), BUDGETS, SCALES, SEEDS))


def _four_plain_ints(values: object, *, binary: bool) -> tuple:
    require(
        type(values) in (tuple, list) and len(values) == 4, "four-arm vector required"
    )
    require(
        all(type(v) is int and v >= 0 and (not binary or v in (0, 1)) for v in values),
        "plain nonnegative integer values required",
    )
    return tuple(values)


def block_contrast(values: object) -> int:
    """Pure algebra; integrity/monotonicity is a separate prerequisite."""
    lo0, lo16, hi0, hi16 = _four_plain_ints(values, binary=True)
    return (hi16 - hi0) - (lo16 - lo0)


def valid_budget_pattern(values: object) -> bool:
    lo0, lo16, hi0, hi16 = _four_plain_ints(values, binary=True)
    return hi0 >= lo0 and hi16 >= lo16


def ordinal_error_contrast(values: object) -> int:
    lo0, lo16, hi0, hi16 = _four_plain_ints(values, binary=False)
    require(hi0 <= lo0 and hi16 <= lo16, "minimum error contradicts budget prefix")

    def sign(value: int) -> int:
        return (value > 0) - (value < 0)

    return sign(hi0 - hi16) - sign(lo0 - lo16)


def factorial_counts(tasks: object) -> dict:
    """Mathematical reducer for synthetic fixtures, NOT a production analyzer.

    This validates shape/types and necessary success monotonicity, not real
    identity, provenance, replay, event-prefix integrity, or feedback support.
    Its output can never itself establish a development decision or authority.
    """
    require(
        type(tasks) in (list, tuple) and len(tasks) == TASK_COUNT,
        "exactly 12 task clusters required",
    )
    task_rows, patterns = [], Counter()
    for slot, rows in enumerate(tasks):
        require(
            type(rows) in (list, tuple) and len(rows) == len(SEEDS),
            "exactly four seeds per task required",
        )
        counts, new, lost = [0] * 4, [0] * 2, [0] * 2
        for values in rows:
            bits = _four_plain_ints(values, binary=True)
            require(valid_budget_pattern(bits), "success contradicts budget prefix")
            patterns["".join(map(str, bits))] += 1
            counts = [a + b for a, b in zip(counts, bits)]
            for budget_slot, offset in enumerate((0, 2)):
                new[budget_slot] += int(bits[offset] == 0 and bits[offset + 1] == 1)
                lost[budget_slot] += int(bits[offset] == 1 and bits[offset + 1] == 0)
        low, high = counts[1] - counts[0], counts[3] - counts[2]
        task_rows.append(
            {
                "task_slot": slot,
                "arm_success_counts": counts,
                "new_success_counts": new,
                "lost_success_counts": lost,
                "low_uplift_numerator": low,
                "high_uplift_numerator": high,
                "interaction_numerator": high - low,
                "low_uplift": ratio(low, 4),
                "high_uplift": ratio(high, 4),
                "interaction": ratio(high - low, 4),
            }
        )
    counts = [sum(row["arm_success_counts"][j] for row in task_rows) for j in range(4)]
    low, high = counts[1] - counts[0], counts[3] - counts[2]
    interaction = high - low
    leave_one_out = [
        {
            "omitted_task_slot": row["task_slot"],
            "block_count": 44,
            "interaction": ratio(interaction - row["interaction_numerator"], 44),
            "high_uplift": ratio(high - row["high_uplift_numerator"], 44),
        }
        for row in task_rows
    ]
    numerical_gates = {
        "interaction_at_least_two": interaction >= 2,
        "high_uplift_at_least_two": high >= 2,
        "low_uplift_nonnegative": low >= 0,
        "no_high_budget_lost_success": sum(
            r["lost_success_counts"][1] for r in task_rows
        )
        == 0,
        "high_rescues_on_two_tasks": sum(
            r["new_success_counts"][1] > 0 for r in task_rows
        )
        >= 2,
        "leave_one_task_out_strictly_positive": all(
            r["interaction"]["numerator"] > 0 and r["high_uplift"]["numerator"] > 0
            for r in leave_one_out
        ),
    }
    return {
        "scope": "synthetic_arithmetic_only_not_integrity_or_authority",
        "block_count": 48,
        "task_count": 12,
        "arm_order": list(ARMS),
        "arm_success_counts": counts,
        "task_rows": task_rows,
        "new_success_counts": [
            sum(r["new_success_counts"][j] for r in task_rows) for j in range(2)
        ],
        "lost_success_counts": [
            sum(r["lost_success_counts"][j] for r in task_rows) for j in range(2)
        ],
        "low_uplift": ratio(low, 48),
        "high_uplift": ratio(high, 48),
        "interaction": ratio(interaction, 48),
        "pattern_counts": [
            {"pattern": "".join(map(str, p)), "count": patterns["".join(map(str, p))]}
            for p in product((0, 1), repeat=4)
        ],
        "leave_one_task_out": leave_one_out,
        "numerical_gates": numerical_gates,
        "all_numerical_gates_met": all(numerical_gates.values()),
        "production_integrity_assessed": False,
        "feedback_guard_assessed": False,
        "execution_authorized": False,
    }


def self_test() -> dict:
    profiles = guard_profiles()
    maximum_trajectory_cost = sum((60, 40, 24, 12, 4))
    require(BUDGETS[0] >= maximum_trajectory_cost, "first terminal structural bound")
    require(
        BUDGETS[1] - BUDGETS[0] >= maximum_trajectory_cost,
        "at least one extra completion must fit after any low prefix",
    )
    require(
        BUDGETS[1] >= 3 * maximum_trajectory_cost,
        "three complete trajectories must fit high primary budget",
    )
    require(
        len(planned_coordinates()) == len(set(planned_coordinates())) == 192,
        "planned ordinal layout",
    )
    for axis in AXES:
        require(
            axis == "legal_action_scores" or profiles[256][axis] == profiles[512][axis],
            "common guards differ",
        )
    for budget in BUDGETS:
        cap = profiles[budget]
        for spent in range(budget + 1):
            steps = spent // 3
            require(
                steps < cap["edge_selections"] and spent // 15 < cap["verifier_calls"],
                "accepted guard exhaustion possible under structural bound",
            )
            for attempted in range(3, 61):
                require(
                    spent + attempted <= cap["generated_perturbation_coordinates"]
                    and spent + attempted <= cap["proposal_action_scores"]
                    and steps + 1 <= cap["edge_selections"]
                    and steps + 2 <= cap["proposal_state_evaluations"],
                    "secondary co-block possible under structural bound",
                )
    require(
        sum(valid_budget_pattern(p) for p in product((0, 1), repeat=4)) == 9,
        "budget-monotone pattern count",
    )
    tasks = [[(0, 0, 0, 0)] * 4 for _ in range(12)]
    tasks[0][0] = tasks[1][0] = (0, 0, 0, 1)
    result = factorial_counts(tasks)
    require(
        result["interaction"] == ratio(2, 48) and result["all_numerical_gates_met"],
        "two-task synthetic positive control",
    )
    require(
        not result["execution_authorized"]
        and not result["production_integrity_assessed"],
        "synthetic arithmetic must not authorize or attest production",
    )
    return {
        "status": "SYNTHETIC_MATH_PASS",
        "new_cohorts_generated": 0,
        "search_executions": 0,
        "provider_calls": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="pure arithmetic; no design file access",
    )
    args = parser.parse_args()
    try:
        result = self_test()
        if not args.self_test:
            path = ROOT / DESIGN
            require(
                not path.is_symlink() and path.is_file(),
                "design must be a regular file",
            )
            require(
                hashlib.sha256(path.read_bytes()).hexdigest() == DESIGN_SHA256,
                "fixed design bytes changed",
            )
            result = {
                "status": "DESIGN_CHECKS_PASS_NOT_EXECUTABLE",
                "design_sha256": DESIGN_SHA256,
                "task_count": TASK_COUNT,
                "generation_seed": GENERATION_SEED,
                "exploration_seeds": list(SEEDS),
                "scales": list(SCALES),
                "guard_profiles": guard_profiles(),
                "planned_cell_count": len(planned_coordinates()),
                "planned_prefix_checks": 96,
                "task_identities_materialized": False,
                "execution_authorized": False,
                "numerical_checks": result,
            }
        print(canonical(result).decode())
        return 0
    except (ValueError, OSError) as error:
        print(canonical({"status": "INVALID_DESIGN", "reason": str(error)}).decode())
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
