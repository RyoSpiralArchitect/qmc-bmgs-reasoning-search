"""v7 design arithmetic and boundaries; no cohort, solver, replay or provider."""

from __future__ import annotations

from collections import defaultdict
from contextlib import redirect_stdout
from fractions import Fraction
import importlib.util
import io
from itertools import product
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts/check_feedback_budget_confirmation_design.py"
)
SPEC = importlib.util.spec_from_file_location("replication_design_tested", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
D = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(D)


def tasks():
    return [[(0, 0, 0, 0) for _ in range(4)] for _ in range(64)]


def positives(count=11):
    value = tasks()
    for i in range(count):
        value[i][0] = (0, 0, 0, 1)
    return value


def as_fraction(value):
    return Fraction(value["numerator"], value["denominator"])


class ReplicationDesignMathTests(unittest.TestCase):
    def test_1024_unique_ordinal_coordinates_and_512_prefix_pairs(self):
        coordinates = D.planned_coordinates()
        self.assertEqual(
            coordinates,
            list(product(range(64), (256, 512), (0, 16), (8192, 8193, 8194, 8195))),
        )
        self.assertEqual(len(coordinates), len(set(coordinates)))
        self.assertEqual(len(coordinates), 1024)
        pairs = defaultdict(list)
        for slot, budget, scale, seed in coordinates:
            pairs[slot, scale, seed].append(budget)
        self.assertEqual(len(pairs), 512)
        self.assertTrue(all(row == [256, 512] for row in pairs.values()))
        self.assertEqual(sum(row[1] for row in coordinates), 393216)

    def test_same_factors_and_guards_not_new_method(self):
        self.assertEqual(D.SEEDS, (8192, 8193, 8194, 8195))
        self.assertEqual(D.SCALES, (0, 16))
        self.assertEqual(D.GENERATION_SEED, 26091301)
        self.assertEqual(D.MAX_ATTEMPTS, 10000)
        self.assertEqual(
            D.guard_profiles()[256],
            {
                "proposal_state_evaluations": 172,
                "proposal_action_scores": 573,
                "legal_action_scores": 256,
                "generated_perturbation_coordinates": 572,
                "edge_selections": 171,
                "transitions": 171,
                "verifier_calls": 35,
            },
        )
        self.assertEqual(
            D.guard_profiles()[256] | {"legal_action_scores": 512},
            D.guard_profiles()[512],
        )

    def test_fractional_floors_preserved_not_two_cell_or_rounded_rules(self):
        self.assertEqual(D.EFFECT_FLOOR, Fraction(2, 48))
        self.assertEqual(D.RESCUED_TASK_FRACTION, Fraction(2, 12))
        for denominator in range(1, 301):
            for floor in (D.EFFECT_FLOOR, D.RESCUED_TASK_FRACTION):
                count = D.minimum_integer_count(denominator, floor)
                self.assertLess(Fraction(count - 1, denominator), floor)
                self.assertGreaterEqual(Fraction(count, denominator), floor)
        self.assertEqual(D.minimum_integer_count(256, D.EFFECT_FLOOR), 11)
        self.assertEqual(D.minimum_integer_count(64, D.RESCUED_TASK_FRACTION), 11)
        self.assertNotEqual(Fraction(11, 256), Fraction(1, 24))

    def test_invalid_threshold_inputs_rejected(self):
        for denominator in (True, False, 0, -1, 256.0, "256"):
            with self.subTest(denominator=denominator), self.assertRaises(ValueError):
                D.minimum_integer_count(denominator, Fraction(1, 24))
        for floor in (
            0,
            1,
            True,
            0.0417,
            "1/24",
            Fraction(0),
            Fraction(-1),
            Fraction(2),
        ):
            with self.subTest(floor=floor), self.assertRaises(ValueError):
                D.minimum_integer_count(256, floor)

    def test_all_16_patterns_and_seven_rejections(self):
        permitted = 0
        for bits in product((0, 1), repeat=4):
            expected = bits[2] >= bits[0] and bits[3] >= bits[1]
            self.assertEqual(D.valid_budget_pattern(bits), expected)
            self.assertEqual(
                D.block_contrast(bits), bits[3] - bits[2] - bits[1] + bits[0]
            )
            value = tasks()
            value[0][0] = bits
            if expected:
                permitted += 1
                result = D.synthetic_counts(value)
                self.assertLessEqual(abs(D.block_contrast(bits)), 1)
                self.assertEqual(
                    sum(row["count"] for row in result["pattern_counts"]), 256
                )
            else:
                with self.assertRaisesRegex(ValueError, "budget prefix"):
                    D.synthetic_counts(value)
        self.assertEqual(permitted, 9)

    def test_pattern_table_keeps_all_zero_rows(self):
        rows = D.synthetic_counts(tasks())["pattern_counts"]
        self.assertEqual(
            [row["pattern"] for row in rows],
            ["".join(map(str, p)) for p in product((0, 1), repeat=4)],
        )
        self.assertEqual([row["count"] for row in rows], [256] + [0] * 15)

    def test_eleven_distinct_rescue_tasks_is_minimum_numerical_positive(self):
        result = D.synthetic_counts(positives())
        self.assertTrue(result["synthetic_numerical_gates_met"])
        self.assertEqual(result["arm_success_counts"], [0, 0, 0, 11])
        self.assertEqual(result["high_budget_rescued_task_count"], 11)
        self.assertEqual(as_fraction(result["interaction"]), Fraction(11, 256))
        self.assertEqual(as_fraction(result["high_uplift"]), Fraction(11, 256))
        self.assertEqual(result["lost_success_counts"], [0, 0])

    def test_ten_rescues_and_old_two_rescue_screen_fail(self):
        for count in (0, 2, 10):
            with self.subTest(count=count):
                result = D.synthetic_counts(positives(count))
                self.assertFalse(result["synthetic_numerical_gates_met"])
                self.assertFalse(
                    result["numerical_gates"]["interaction_meets_fixed_fraction"]
                )
                self.assertFalse(result["numerical_gates"]["rescued_task_fraction_met"])

    def test_large_gain_concentrated_on_three_tasks_fails_breadth(self):
        value = tasks()
        for i in range(3):
            value[i] = [(0, 0, 0, 1)] * 4
        result = D.synthetic_counts(value)
        self.assertTrue(result["numerical_gates"]["interaction_meets_fixed_fraction"])
        self.assertEqual(result["high_budget_rescued_task_count"], 3)
        self.assertFalse(result["synthetic_numerical_gates_met"])

    def test_high_uplift_without_interaction_does_not_pass(self):
        value = tasks()
        for i in range(11):
            value[i][0] = (0, 1, 0, 1)
        result = D.synthetic_counts(value)
        self.assertEqual(as_fraction(result["interaction"]), 0)
        self.assertTrue(result["numerical_gates"]["high_uplift_meets_fixed_fraction"])
        self.assertFalse(result["synthetic_numerical_gates_met"])

    def test_low_budget_harm_disappearing_does_not_pass(self):
        value = tasks()
        for i in range(11):
            value[i][0] = (1, 0, 1, 1)
        result = D.synthetic_counts(value)
        self.assertEqual(as_fraction(result["interaction"]), Fraction(11, 256))
        self.assertEqual(as_fraction(result["high_uplift"]), 0)
        self.assertFalse(result["numerical_gates"]["low_uplift_nonnegative"])
        self.assertFalse(result["synthetic_numerical_gates_met"])

    def test_one_high_budget_loss_blocks_even_broad_positive_net(self):
        value = positives(12)
        value[63][0] = (0, 0, 1, 0)
        result = D.synthetic_counts(value)
        self.assertEqual(as_fraction(result["high_uplift"]), Fraction(11, 256))
        self.assertEqual(result["lost_success_counts"], [0, 1])
        self.assertFalse(result["synthetic_numerical_gates_met"])

    def test_both_methods_improve_equally_is_not_feedback_replication(self):
        value = tasks()
        for i in range(64):
            value[i][0] = (0, 0, 1, 1)
        result = D.synthetic_counts(value)
        self.assertEqual(result["arm_success_counts"], [0, 0, 64, 64])
        self.assertEqual(as_fraction(result["interaction"]), 0)
        self.assertFalse(result["synthetic_numerical_gates_met"])

    def test_all_64_leave_one_out_rows_use_252_blocks(self):
        rows = D.synthetic_counts(positives())["leave_one_task_out"]
        self.assertEqual([row["omitted_task_slot"] for row in rows], list(range(64)))
        for i, row in enumerate(rows):
            self.assertEqual(row["block_count"], 252)
            expected = Fraction(10 if i < 11 else 11, 252)
            self.assertEqual(as_fraction(row["interaction"]), expected)
            self.assertEqual(as_fraction(row["high_uplift"]), expected)

    def test_leave_one_out_at_effect_floor_is_not_independent_support(self):
        # Prefix-valid per-seed interaction/high-uplift are bounded by one.
        for bits in product((0, 1), repeat=4):
            if D.valid_budget_pattern(bits):
                self.assertLessEqual(4 * D.block_contrast(bits), 4)
                self.assertLessEqual(4 * (bits[3] - bits[2]), 4)
        self.assertGreater(11 - 4, 0)

    def test_rescued_pairs_distinguished_from_any_seed_solved_tasks(self):
        value = positives()
        value[0][1] = (0, 0, 1, 1)
        result = D.synthetic_counts(value)
        self.assertEqual(result["new_success_counts"], [0, 11])
        self.assertEqual(result["high_budget_rescued_task_count"], 11)
        self.assertEqual(result["any_seed_solved_task_counts"], [0, 0, 1, 11])
        self.assertEqual(result["arm_success_counts"], [0, 0, 1, 12])

    def test_wrong_task_and_seed_shape_rejected(self):
        for value in (None, {}, [], tasks()[:12], tasks()[:-1], tasks() + [tasks()[0]]):
            with (
                self.subTest(value_type=type(value).__name__),
                self.assertRaises(ValueError),
            ):
                D.synthetic_counts(value)
        for row in (None, {}, [], [(0, 0, 0, 0)] * 3, [(0, 0, 0, 0)] * 5):
            value = tasks()
            value[0] = row
            with self.assertRaises(ValueError):
                D.synthetic_counts(value)

    def test_nonbinary_boolean_missing_or_wrong_vector_rejected(self):
        for wrong in (
            None,
            {},
            [],
            [0, 0, 0],
            [0] * 5,
            [True, 0, 0, 0],
            [0, 0, False, 0],
            [0.0, 0, 0, 0],
            ["0", 0, 0, 0],
            [-1, 0, 0, 0],
            [0, 0, 0, 2],
        ):
            value = tasks()
            value[0][0] = wrong
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                D.synthetic_counts(value)

    def test_tuple_arrays_supported_without_mutation(self):
        value = tuple(tuple(row) for row in positives())
        before = D.canonical(value)
        self.assertTrue(D.synthetic_counts(value)["synthetic_numerical_gates_met"])
        self.assertEqual(D.canonical(value), before)

    def test_no_synthetic_input_can_become_a_production_decision(self):
        for value in (tasks(), positives(), positives(64)):
            result = D.synthetic_counts(value)
            for key, expected in D.boundaries().items():
                self.assertEqual(result[key], expected)
            self.assertNotIn("decision", result)
            self.assertNotIn(
                "SOURCE_DISJOINT_REPLICATION_SCREEN_PASS", D.canonical(result).decode()
            )
            self.assertNotIn(
                "STOP_REPAIR_REPLICATION_SCREEN_NOT_MET", D.canonical(result).decode()
            )


class ReplicationDesignInterfaceTests(unittest.TestCase):
    def test_design_and_history_byte_anchors(self):
        result = D.checked_files(D.ROOT)
        self.assertEqual(len(result), 5)
        self.assertEqual(result[D.DESIGN], D.DESIGN_SHA256)
        self.assertEqual(len(D.DESIGN_SHA256), 64)

    def test_missing_changed_or_symlink_design_rejected(self):
        with (
            patch.object(Path, "is_file", return_value=False),
            self.assertRaises(ValueError),
        ):
            D.checked_files(D.ROOT)
        with (
            patch.object(Path, "is_symlink", return_value=True),
            self.assertRaises(ValueError),
        ):
            D.checked_files(D.ROOT)
        with (
            patch.object(Path, "read_bytes", return_value=b"different"),
            self.assertRaises(ValueError),
        ):
            D.checked_files(D.ROOT)

    def test_self_test_has_no_data_file_io(self):
        with patch.object(
            Path, "read_bytes", side_effect=AssertionError("data-file IO")
        ):
            result = D.self_test()
        self.assertEqual(result["status"], "SYNTHETIC_REPLICATION_MATH_PASS")
        self.assertFalse(result["execution_authorized"])

    def test_main_explicitly_nonexecuting(self):
        stream = io.StringIO()
        with patch.object(sys, "argv", [str(SCRIPT)]), redirect_stdout(stream):
            status = D.main()
        self.assertEqual(status, 0)
        result = json.loads(stream.getvalue())
        self.assertEqual(
            result["status"], "REPLICATION_DESIGN_CHECKS_PASS_NOT_EXECUTABLE"
        )
        self.assertEqual(result["planned_cell_count"], 1024)
        self.assertEqual(result["planned_prefix_pairs"], 512)
        self.assertEqual(result["minimum_rescued_tasks"], 11)
        self.assertFalse(result["complete_exclusion_manifest_verified"])
        self.assertFalse(result["production_integrity_assessed"])

    def test_invalid_file_returns_failure_not_success(self):
        stream = io.StringIO()
        with (
            patch.object(sys, "argv", [str(SCRIPT)]),
            redirect_stdout(stream),
            patch.object(D, "checked_files", side_effect=ValueError("changed anchor")),
        ):
            status = D.main()
        self.assertEqual(status, 2)
        self.assertEqual(json.loads(stream.getvalue())["status"], "INVALID_DESIGN")

    def test_no_experiment_input_or_execution_cli(self):
        for option in (
            "--input",
            "--run",
            "--run-development",
            "--authorization",
            "--seed",
        ):
            with (
                patch.object(sys, "argv", [str(SCRIPT), option]),
                patch("sys.stderr", io.StringIO()),
                self.assertRaises(SystemExit) as error,
            ):
                D.main()
            self.assertEqual(error.exception.code, 2)

    def test_outside_checkout_cli(self):
        for arguments in ([], ["--self-test"]):
            result = subprocess.run(
                [sys.executable, "-P", "-B", str(SCRIPT), *arguments],
                cwd="/tmp",
                text=True,
                capture_output=True,
                check=True,
            )
            output = json.loads(result.stdout)
            self.assertFalse(output["execution_authorized"])
            self.assertEqual(output["new_tasks_generated"], 0)


if __name__ == "__main__":
    unittest.main()
