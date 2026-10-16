#!/usr/bin/env python3
"""Check the fixed v7 replication design and synthetic math; never run a study."""

from __future__ import annotations

import argparse
from collections import Counter
from fractions import Fraction
import hashlib
from itertools import product
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESIGN = "docs/strategy/countdown_thompson_feedback_budget_confirmation_v7.md"
DESIGN_SHA256 = "0a11f4da63063cc48a128e2f9ead676e92a588b31cc8fcbe08e466a46374d0eb"
EXPERIMENT_ID = "feedback_budget_confirmation_64_seed_26091301/v1"
PRODUCTION_DOMAIN = "qmc-bmgs-countdown-thompson-feedback-budget-confirmation/v1"
TASK_COUNT = 64
GENERATION_SEED = 26091301
MAX_ATTEMPTS = 10000
SEEDS = (8192, 8193, 8194, 8195)
SCALES = (0, 16)
BUDGETS = (256, 512)
ARMS = ("Y0_256", "Y16_256", "Y0_512", "Y16_512")
EFFECT_FLOOR = Fraction(1, 24)
RESCUED_TASK_FRACTION = Fraction(1, 6)
PINNED_HISTORY = {
    "docs/strategy/countdown_thompson_feedback_budget_factorial_v6.md": "7b3ebcc7d1b3c3a591b6f3baa574492085bc91c53ee3cccc9fe031d3d70ef01f",
    "docs/preregistrations/countdown_thompson_feedback_budget_v6/preregistration.json": "3d7d68bebcb2708709cf410b9a469c644e900979ca5277636c3f032ae5f89cf8",
    "docs/results/countdown_feedback_budget_v6_development_20260910/COMMIT.json": "3ff307a32b6bd8e7f845164d4e055b7cba8639049e13ca30311404634fa8d0d0",
    "docs/results/countdown_feedback_budget_v6_development_20260910/summary.json": "81149bbcc5f5d7e9a1c54e0192155d9125e58d9bed1163a63ea80a965f98c8dc",
}


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode()


def ratio(numerator: int, denominator: int) -> dict:
    value = Fraction(numerator, denominator)
    return {"numerator": value.numerator, "denominator": value.denominator}


def minimum_integer_count(denominator: int, floor: Fraction) -> int:
    require(type(denominator) is int and denominator > 0, "positive plain denominator")
    require(type(floor) is Fraction and 0 < floor <= 1, "positive fractional floor")
    return -(-(denominator * floor.numerator) // floor.denominator)


def boundaries() -> dict:
    return {
        "new_tasks_generated": 0,
        "search_executions": 0,
        "provider_calls": 0,
        "task_identities_materialized": False,
        "complete_exclusion_manifest_verified": False,
        "source_runtime_qualified": False,
        "production_integrity_assessed": False,
        "feedback_support_assessed": False,
        "execution_authorized": False,
        "locked_128_evaluation_authorized": False,
    }


def guard_profiles() -> dict:
    common = {
        "proposal_state_evaluations": 172,
        "proposal_action_scores": 573,
        "generated_perturbation_coordinates": 572,
        "edge_selections": 171,
        "transitions": 171,
        "verifier_calls": 35,
    }
    return {b: {**common, "legal_action_scores": b} for b in BUDGETS}


def planned_coordinates() -> list[tuple[int, int, int, int]]:
    """Ordinal slots only: no task identities, generation or runnable schedule."""
    return list(product(range(TASK_COUNT), BUDGETS, SCALES, SEEDS))


def _bits(values: object) -> tuple:
    require(
        type(values) in (list, tuple) and len(values) == 4, "four-arm vector required"
    )
    require(
        all(type(value) is int and value in (0, 1) for value in values),
        "plain binary integer values required",
    )
    return tuple(values)


def valid_budget_pattern(values: object) -> bool:
    lo0, lo16, hi0, hi16 = _bits(values)
    return hi0 >= lo0 and hi16 >= lo16


def block_contrast(values: object) -> int:
    lo0, lo16, hi0, hi16 = _bits(values)
    return hi16 - hi0 - lo16 + lo0


def synthetic_counts(tasks: object) -> dict:
    """Reduce synthetic binary arrays, never certify experimental evidence.

    Only shape, plain-int types, necessary budget monotonicity and arithmetic
    are checked. There is no input-file CLI, task-key, source, trace replay,
    event-prefix or mechanism validator and no production decision field.
    """
    require(
        type(tasks) in (list, tuple) and len(tasks) == TASK_COUNT,
        "exactly 64 task clusters required",
    )
    task_rows, patterns = [], Counter()
    for slot, rows in enumerate(tasks):
        require(
            type(rows) in (list, tuple) and len(rows) == len(SEEDS),
            "exactly four seeds per task required",
        )
        counts, new, lost = [0] * 4, [0] * 2, [0] * 2
        for values in rows:
            bits = _bits(values)
            require(valid_budget_pattern(bits), "success contradicts budget prefix")
            patterns["".join(map(str, bits))] += 1
            counts = [count + value for count, value in zip(counts, bits)]
            for j, offset in enumerate((0, 2)):
                new[j] += int(bits[offset] == 0 and bits[offset + 1] == 1)
                lost[j] += int(bits[offset] == 1 and bits[offset + 1] == 0)
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
                "low_uplift": ratio(low, len(SEEDS)),
                "high_uplift": ratio(high, len(SEEDS)),
                "interaction": ratio(high - low, len(SEEDS)),
            }
        )
    blocks = TASK_COUNT * len(SEEDS)
    counts = [sum(row["arm_success_counts"][j] for row in task_rows) for j in range(4)]
    new = [sum(row["new_success_counts"][j] for row in task_rows) for j in range(2)]
    lost = [sum(row["lost_success_counts"][j] for row in task_rows) for j in range(2)]
    low, high = counts[1] - counts[0], counts[3] - counts[2]
    interaction = high - low
    rescued_tasks = sum(row["new_success_counts"][1] > 0 for row in task_rows)
    effect_minimum = minimum_integer_count(blocks, EFFECT_FLOOR)
    task_minimum = minimum_integer_count(TASK_COUNT, RESCUED_TASK_FRACTION)
    loo_blocks = blocks - len(SEEDS)
    leave_one_out = [
        {
            "omitted_task_slot": row["task_slot"],
            "block_count": loo_blocks,
            "high_uplift": ratio(high - row["high_uplift_numerator"], loo_blocks),
            "interaction": ratio(
                interaction - row["interaction_numerator"], loo_blocks
            ),
        }
        for row in task_rows
    ]
    gates = {
        "interaction_meets_fixed_fraction": interaction >= effect_minimum,
        "high_uplift_meets_fixed_fraction": high >= effect_minimum,
        "low_uplift_nonnegative": low >= 0,
        "no_high_budget_lost_success": lost[1] == 0,
        "rescued_task_fraction_met": rescued_tasks >= task_minimum,
        "leave_one_task_out_strictly_positive": all(
            row["interaction"]["numerator"] > 0 and row["high_uplift"]["numerator"] > 0
            for row in leave_one_out
        ),
    }
    return {
        "scope": "synthetic_replication_arithmetic_only_not_integrity_or_authority",
        "task_count": TASK_COUNT,
        "block_count": blocks,
        "arm_order": list(ARMS),
        "arm_success_counts": counts,
        "any_seed_solved_task_counts": [
            sum(row["arm_success_counts"][j] > 0 for row in task_rows) for j in range(4)
        ],
        "new_success_counts": new,
        "lost_success_counts": lost,
        "high_budget_rescued_task_count": rescued_tasks,
        "low_uplift": ratio(low, blocks),
        "high_uplift": ratio(high, blocks),
        "interaction": ratio(interaction, blocks),
        "task_rows": task_rows,
        "pattern_counts": [
            {"pattern": "".join(map(str, p)), "count": patterns["".join(map(str, p))]}
            for p in product((0, 1), repeat=4)
        ],
        "leave_one_task_out": leave_one_out,
        "effect_floor": ratio(EFFECT_FLOOR.numerator, EFFECT_FLOOR.denominator),
        "minimum_effect_numerator": effect_minimum,
        "rescued_task_fraction": ratio(
            RESCUED_TASK_FRACTION.numerator, RESCUED_TASK_FRACTION.denominator
        ),
        "minimum_rescued_tasks": task_minimum,
        "numerical_gates": gates,
        "synthetic_numerical_gates_met": all(gates.values()),
        **boundaries(),
    }


def self_test() -> dict:
    layout = planned_coordinates()
    require(len(layout) == len(set(layout)) == 1024, "ordinal matrix shape")
    require(minimum_integer_count(256, EFFECT_FLOOR) == 11, "effect threshold")
    require(minimum_integer_count(64, RESCUED_TASK_FRACTION) == 11, "breadth threshold")
    require(
        Fraction(10, 256) < EFFECT_FLOOR <= Fraction(11, 256), "exact effect ceiling"
    )
    require(
        Fraction(10, 64) < RESCUED_TASK_FRACTION <= Fraction(11, 64), "breadth ceiling"
    )
    require(
        sum(valid_budget_pattern(p) for p in product((0, 1), repeat=4)) == 9,
        "nine permitted binary patterns",
    )
    require(
        all(
            abs(block_contrast(p)) <= 1
            for p in product((0, 1), repeat=4)
            if valid_budget_pattern(p)
        ),
        "bounded prefix-valid interaction",
    )
    # Numeric positive control needs eleven different ordinal task slots.
    tasks = [[(0, 0, 0, 0) for _ in SEEDS] for _ in range(TASK_COUNT)]
    for i in range(11):
        tasks[i][0] = (0, 0, 0, 1)
    positive = synthetic_counts(tasks)
    require(positive["synthetic_numerical_gates_met"], "eleven-task synthetic control")
    require(positive["interaction"] == ratio(11, 256), "positive exact fraction")
    tasks[10][0] = (0, 0, 0, 0)
    require(
        not synthetic_counts(tasks)["synthetic_numerical_gates_met"],
        "ten-task near miss must not pass",
    )
    profiles = guard_profiles()
    require(
        profiles[256] | {"legal_action_scores": 512} == profiles[512],
        "only the primary guard changes",
    )
    require(sum(cell[1] for cell in layout) == 393216, "configured primary-cap sum")
    return {"status": "SYNTHETIC_REPLICATION_MATH_PASS", **boundaries()}


def checked_files(root: Path) -> dict:
    """Byte anchors only, not Git ancestry, raw-evidence or runtime attestation."""
    expected = {DESIGN: DESIGN_SHA256, **PINNED_HISTORY}
    for relative, expected_hash in expected.items():
        path = root / relative
        require(
            not path.is_symlink() and path.is_file(),
            f"regular file required: {relative}",
        )
        require(
            hashlib.sha256(path.read_bytes()).hexdigest() == expected_hash,
            f"fixed design/evidence bytes changed: {relative}",
        )
    return dict(expected)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--self-test", action="store_true", help="synthetic math; no data-file IO"
    )
    args = parser.parse_args()
    try:
        numerical = self_test()
        result = numerical
        if not args.self_test:
            result = {
                "status": "REPLICATION_DESIGN_CHECKS_PASS_NOT_EXECUTABLE",
                "experiment_id": EXPERIMENT_ID,
                "future_production_domain": PRODUCTION_DOMAIN,
                "pinned_file_sha256": checked_files(ROOT),
                "task_count": TASK_COUNT,
                "generation_seed": GENERATION_SEED,
                "maximum_generation_attempts": MAX_ATTEMPTS,
                "exploration_seeds": list(SEEDS),
                "scales": list(SCALES),
                "guard_profiles": guard_profiles(),
                "planned_cell_count": len(planned_coordinates()),
                "planned_four_arm_blocks": 256,
                "planned_prefix_pairs": 512,
                "configured_primary_cap_sum": 393216,
                "effect_floor": ratio(1, 24),
                "minimum_effect_numerator": 11,
                "rescued_task_fraction": ratio(1, 6),
                "minimum_rescued_tasks": 11,
                "leave_one_task_out_block_count": 252,
                "numerical_checks": numerical,
                **boundaries(),
            }
        print(canonical(result).decode())
        return 0
    except (ValueError, OSError) as error:
        print(canonical({"status": "INVALID_DESIGN", "reason": str(error)}).decode())
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
