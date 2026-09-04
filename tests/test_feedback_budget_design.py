"""Synthetic design arithmetic only: no cohort, search, replay, or raw access."""

from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import redirect_stdout
from fractions import Fraction
import importlib.util
import io
from itertools import product
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_feedback_budget_design.py"
SPEC = importlib.util.spec_from_file_location("feedback_budget_design_tested", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
DESIGN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DESIGN)


def _tasks() -> list[list[tuple[int, int, int, int]]]:
    """Ordinal synthetic blocks, never materialized Countdown task identities."""
    return [[(0, 0, 0, 0) for _ in range(4)] for _ in range(12)]


def _fraction(value: dict[str, int]) -> Fraction:
    return Fraction(value["numerator"], value["denominator"])


class FeedbackBudgetGuardTests(unittest.TestCase):
    def test_completion_bounds_cover_every_low_budget_prefix(self):
        maximum_path_cost = sum(4 * n * (n - 1) // 2 for n in range(2, 7))
        self.assertEqual(maximum_path_cost, 140)
        self.assertLessEqual(maximum_path_cost, min(DESIGN.BUDGETS))
        self.assertLessEqual(3 * maximum_path_cost, max(DESIGN.BUDGETS))
        for accepted_low_usage in range(257):
            self.assertGreaterEqual(512 - accepted_low_usage, maximum_path_cost)

    def test_profiles_differ_only_on_primary_axis(self):
        profiles = DESIGN.guard_profiles()
        common = {
            "proposal_state_evaluations": 172,
            "proposal_action_scores": 573,
            "generated_perturbation_coordinates": 572,
            "edge_selections": 171,
            "transitions": 171,
            "verifier_calls": 35,
        }
        self.assertEqual(set(profiles), {256, 512})
        for budget in (256, 512):
            self.assertEqual(
                profiles[budget], {**common, "legal_action_scores": budget}
            )
            self.assertTrue(all(type(cap) is int for cap in profiles[budget].values()))

    def test_structural_accepted_headroom_and_next_attempt_coverage(self):
        for budget, caps in DESIGN.guard_profiles().items():
            for spent in range(budget + 1):
                selections, terminals = spent // 3, spent // 15
                accepted_bounds = {
                    "proposal_state_evaluations": selections + 1,
                    "proposal_action_scores": spent,
                    "generated_perturbation_coordinates": spent,
                    "edge_selections": selections,
                    "transitions": selections,
                    "verifier_calls": terminals,
                }
                for axis, bound in accepted_bounds.items():
                    self.assertLess(bound, caps[axis], (budget, spent, axis))
                for width in range(3, 61):
                    next_attempt_bounds = {
                        "proposal_state_evaluations": selections + 2,
                        "proposal_action_scores": spent + width + 1,
                        "generated_perturbation_coordinates": spent + width,
                        "edge_selections": selections + 1,
                        "transitions": selections + 1,
                        "verifier_calls": terminals + 1,
                    }
                    for axis, bound in next_attempt_bounds.items():
                        self.assertLessEqual(
                            bound, caps[axis], (budget, spent, width, axis)
                        )

    def test_192_unique_ordinal_slots_and_96_same_scale_budget_pairs(self):
        coordinates = DESIGN.planned_coordinates()
        self.assertEqual(len(coordinates), 192)
        self.assertEqual(len(set(coordinates)), 192)
        self.assertEqual(
            coordinates,
            list(product(range(12), (256, 512), (0, 16), (8192, 8193, 8194, 8195))),
        )
        paired_budgets = defaultdict(list)
        for task, budget, scale, seed in coordinates:
            self.assertTrue(all(type(v) is int for v in (task, budget, scale, seed)))
            paired_budgets[task, scale, seed].append(budget)
        self.assertEqual(len(paired_budgets), 96)
        self.assertTrue(all(values == [256, 512] for values in paired_budgets.values()))


class FeedbackBudgetArithmeticTests(unittest.TestCase):
    def test_all_16_binary_patterns_have_exact_algebraic_contrast(self):
        for bits in product((0, 1), repeat=4):
            with self.subTest(bits=bits):
                self.assertEqual(
                    DESIGN.block_contrast(bits), bits[3] - bits[2] - bits[1] + bits[0]
                )

    def test_nine_monotone_patterns_accepted_and_seven_rejected(self):
        accepted, rejected = [], []
        for bits in product((0, 1), repeat=4):
            tasks = _tasks()
            tasks[0][0] = bits
            expected_valid = bits[0] <= bits[2] and bits[1] <= bits[3]
            with self.subTest(bits=bits):
                self.assertIs(DESIGN.valid_budget_pattern(bits), expected_valid)
                if expected_valid:
                    self.assertEqual(DESIGN.factorial_counts(tasks)["block_count"], 48)
                    accepted.append(bits)
                else:
                    with self.assertRaisesRegex(ValueError, "budget prefix"):
                        DESIGN.factorial_counts(tasks)
                    rejected.append(bits)
        self.assertEqual((len(accepted), len(rejected)), (9, 7))

    def test_pattern_table_retains_all_rows_including_impossible_zero_rows(self):
        tasks = _tasks()
        valid = [p for p in product((0, 1), repeat=4) if p[0] <= p[2] and p[1] <= p[3]]
        for index, bits in enumerate(valid):
            tasks[index // 4][index % 4] = bits
        actual = DESIGN.factorial_counts(tasks)["pattern_counts"]
        expected_counts = Counter("".join(map(str, p)) for rows in tasks for p in rows)
        expected_patterns = ["".join(map(str, p)) for p in product((0, 1), repeat=4)]
        self.assertEqual([row["pattern"] for row in actual], expected_patterns)
        self.assertEqual(
            [row["count"] for row in actual],
            [expected_counts[pattern] for pattern in expected_patterns],
        )
        self.assertEqual(sum(row["count"] for row in actual), 48)
        self.assertEqual(sum(row["count"] == 0 for row in actual), 7)

    def test_exact_task_weighted_fractions_and_44_block_leave_one_out(self):
        tasks = _tasks()
        tasks[0] = [(0, 0, 0, 1)] * 4
        tasks[1][:2] = [(0, 1, 0, 1)] * 2
        tasks[2][0] = (0, 0, 1, 0)
        result = DESIGN.factorial_counts(tasks)
        self.assertEqual(result["arm_success_counts"], [0, 2, 1, 6])
        self.assertEqual(result["low_uplift"], {"numerator": 1, "denominator": 24})
        self.assertEqual(result["high_uplift"], {"numerator": 5, "denominator": 48})
        self.assertEqual(result["interaction"], {"numerator": 1, "denominator": 16})
        self.assertEqual(result["new_success_counts"], [2, 6])
        self.assertEqual(result["lost_success_counts"], [0, 1])
        self.assertEqual((result["task_count"], result["block_count"]), (12, 48))
        for field in ("low_uplift", "high_uplift", "interaction"):
            task_average = (
                sum(_fraction(row[field]) for row in result["task_rows"]) / 12
            )
            self.assertEqual(_fraction(result[field]), task_average)
        self.assertEqual(len(result["leave_one_task_out"]), 12)
        for slot, loo in enumerate(result["leave_one_task_out"]):
            with self.subTest(omitted_task=slot):
                self.assertEqual(loo["omitted_task_slot"], slot)
                self.assertEqual(loo["block_count"], 44)
                retained = [
                    row for row in result["task_rows"] if row["task_slot"] != slot
                ]
                for field in ("interaction", "high_uplift"):
                    numerator = sum(row[field + "_numerator"] for row in retained)
                    self.assertEqual(_fraction(loo[field]), Fraction(numerator, 44))
        self.assertEqual(
            result["leave_one_task_out"][0]["interaction"],
            {"numerator": -1, "denominator": 44},
        )

    def test_positive_interaction_from_disappearing_low_harm_is_not_enough(self):
        tasks = _tasks()
        tasks[0][0] = tasks[1][0] = (1, 0, 1, 1)
        result = DESIGN.factorial_counts(tasks)
        self.assertEqual(_fraction(result["interaction"]), Fraction(2, 48))
        self.assertEqual(_fraction(result["high_uplift"]), 0)
        self.assertTrue(result["numerical_gates"]["interaction_at_least_two"])
        self.assertFalse(result["numerical_gates"]["high_uplift_at_least_two"])
        self.assertFalse(result["numerical_gates"]["low_uplift_nonnegative"])
        self.assertFalse(result["all_numerical_gates_met"])

    def test_low_budget_harm_rejects_an_otherwise_positive_screen(self):
        tasks = _tasks()
        tasks[0][0] = tasks[1][0] = (0, 0, 0, 1)
        tasks[2][0] = (1, 0, 1, 1)
        result = DESIGN.factorial_counts(tasks)
        self.assertEqual(
            [key for key, passed in result["numerical_gates"].items() if not passed],
            ["low_uplift_nonnegative"],
        )
        self.assertFalse(result["all_numerical_gates_met"])

    def test_two_distinct_task_rescues_pass_numerical_screen_only(self):
        tasks = _tasks()
        tasks[0][0] = tasks[1][0] = (0, 0, 0, 1)
        result = DESIGN.factorial_counts(tasks)
        self.assertEqual(_fraction(result["interaction"]), Fraction(1, 24))
        self.assertTrue(all(result["numerical_gates"].values()))
        self.assertTrue(result["all_numerical_gates_met"])
        self.assertFalse(result["production_integrity_assessed"])
        self.assertFalse(result["feedback_guard_assessed"])
        self.assertFalse(result["execution_authorized"])

    def test_two_seed_rescues_in_one_task_fail_breadth_and_leave_one_out(self):
        tasks = _tasks()
        tasks[0][:2] = [(0, 0, 0, 1)] * 2
        result = DESIGN.factorial_counts(tasks)
        self.assertEqual(_fraction(result["interaction"]), Fraction(1, 24))
        self.assertEqual(
            [key for key, passed in result["numerical_gates"].items() if not passed],
            ["high_rescues_on_two_tasks", "leave_one_task_out_strictly_positive"],
        )
        self.assertEqual(_fraction(result["leave_one_task_out"][0]["interaction"]), 0)
        self.assertFalse(result["all_numerical_gates_met"])

    def test_high_budget_lost_success_rejects_otherwise_passing_screen(self):
        tasks = _tasks()
        for slot in (0, 1, 2):
            tasks[slot][0] = (0, 0, 0, 1)
        tasks[3][0] = (0, 0, 1, 0)
        result = DESIGN.factorial_counts(tasks)
        self.assertEqual(result["lost_success_counts"], [0, 1])
        self.assertEqual(_fraction(result["interaction"]), Fraction(1, 24))
        self.assertEqual(
            [key for key, passed in result["numerical_gates"].items() if not passed],
            ["no_high_budget_lost_success"],
        )
        self.assertFalse(result["all_numerical_gates_met"])

    def test_equal_budget_improvement_and_fixed_feedback_advantage_have_zero_interaction(
        self,
    ):
        for bits in ((0, 0, 1, 1), (0, 1, 0, 1)):
            with self.subTest(bits=bits):
                tasks = [[bits] * 4 for _ in range(12)]
                result = DESIGN.factorial_counts(tasks)
                self.assertEqual(_fraction(result["interaction"]), 0)
                self.assertFalse(result["all_numerical_gates_met"])

    def test_error_interaction_can_be_negative_while_both_scales_improve(self):
        self.assertEqual(DESIGN.ordinal_error_contrast((10, 8, 1, 2)), -2)
        self.assertEqual(DESIGN.ordinal_error_contrast((8, 10, 2, 1)), 2)
        self.assertEqual(DESIGN.ordinal_error_contrast((10, 8, 4, 4)), -1)
        self.assertEqual(DESIGN.ordinal_error_contrast((0, 0, 0, 0)), 0)

    def test_error_increase_with_budget_is_rejected(self):
        for errors in ((1, 2, 2, 1), (2, 1, 1, 2)):
            with self.subTest(errors=errors):
                with self.assertRaisesRegex(ValueError, "budget prefix"):
                    DESIGN.ordinal_error_contrast(errors)


class FeedbackBudgetShapeAndBoundaryTests(unittest.TestCase):
    def test_missing_extra_or_wrongly_typed_task_clusters_are_rejected(self):
        for tasks in (
            None,
            {},
            12,
            True,
            "x" * 12,
            _tasks()[:-1],
            _tasks() + [_tasks()[0]],
        ):
            with self.subTest(value_type=type(tasks), value=tasks):
                with self.assertRaisesRegex(ValueError, "12 task clusters"):
                    DESIGN.factorial_counts(tasks)

    def test_missing_extra_or_wrongly_typed_seed_rows_are_rejected(self):
        for rows in (None, {}, True, "0000", [(0, 0, 0, 0)] * 3, [(0, 0, 0, 0)] * 5):
            with self.subTest(rows=rows):
                tasks = _tasks()
                tasks[0] = rows
                with self.assertRaisesRegex(ValueError, "four seeds"):
                    DESIGN.factorial_counts(tasks)

    def test_missing_extra_or_wrongly_typed_four_arm_vectors_are_rejected(self):
        for values in (None, {}, True, "0000", [0] * 3, [0] * 5, iter([0] * 4)):
            with self.subTest(value_type=type(values)):
                tasks = _tasks()
                tasks[0][0] = values
                with self.assertRaisesRegex(ValueError, "four-arm vector"):
                    DESIGN.factorial_counts(tasks)

    def test_binary_values_reject_bools_floats_strings_nulls_and_nonbinary_integers(
        self,
    ):
        class IntegerSubclass(int):
            pass

        for value in (False, True, 0.0, 1.0, "0", None, -1, 2, IntegerSubclass(0)):
            for position in range(4):
                with self.subTest(value=repr(value), position=position):
                    values = [0] * 4
                    values[position] = value
                    tasks = _tasks()
                    tasks[0][0] = values
                    with self.assertRaisesRegex(
                        ValueError, "plain nonnegative integer"
                    ):
                        DESIGN.factorial_counts(tasks)

    def test_error_values_require_plain_nonnegative_integers(self):
        for value in (False, True, 0.0, "0", None, -1):
            with self.subTest(value=repr(value)):
                with self.assertRaisesRegex(ValueError, "plain nonnegative integer"):
                    DESIGN.ordinal_error_contrast([value, 0, 0, 0])

    def test_synthetic_results_never_attest_production_or_feedback_or_authority(self):
        fixtures = [_tasks(), _tasks(), _tasks()]
        fixtures[1][0][0] = fixtures[1][1][0] = (0, 0, 0, 1)
        fixtures[2][0][0] = (0, 0, 1, 0)
        for tasks in fixtures:
            result = DESIGN.factorial_counts(tasks)
            self.assertEqual(
                result["scope"], "synthetic_arithmetic_only_not_integrity_or_authority"
            )
            for field in (
                "production_integrity_assessed",
                "feedback_guard_assessed",
                "execution_authorized",
            ):
                self.assertIs(result[field], False)
            self.assertNotIn("decision", result)
            self.assertNotIn(
                "DEVELOPMENT_SIGNAL_FOR_SEPARATE_CONFIRMATION_DESIGN", str(result)
            )

    def test_self_test_mode_reads_no_design_or_external_data(self):
        output = io.StringIO()
        deny_access = AssertionError(
            "synthetic self-test must not access external material"
        )
        with (
            patch.object(sys, "argv", [str(SCRIPT), "--self-test"]),
            patch("builtins.open", side_effect=deny_access),
            patch.object(Path, "open", side_effect=deny_access),
            patch.object(Path, "read_bytes", side_effect=deny_access),
            patch.object(Path, "read_text", side_effect=deny_access),
            patch("subprocess.Popen", side_effect=deny_access),
            patch("socket.socket", side_effect=deny_access),
            redirect_stdout(output),
        ):
            status = DESIGN.main()
        self.assertEqual(status, 0)
        self.assertEqual(
            json.loads(output.getvalue()),
            {
                "status": "SYNTHETIC_MATH_PASS",
                "new_cohorts_generated": 0,
                "search_executions": 0,
                "provider_calls": 0,
            },
        )


if __name__ == "__main__":
    unittest.main()
