"""Boundaries of the public source-level export (not search performance tests)."""

import importlib.util
from fractions import Fraction
from pathlib import Path
import unittest


def load_verifier():
    path = Path(__file__).resolve().parents[1] / "scripts/verify_puct_qmc_results.py"
    spec = importlib.util.spec_from_file_location("public_puct_results", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PublicOutcomes(unittest.TestCase):
    def test_one_deterministic_control_per_source(self):
        check = load_verifier()
        base = ["1"] * 9
        row = ["0", "1", "1", "0", "0", "0", "0", "0", "0"]
        totals, gl, mean, variance, _, _ = check.summarize([row] + [base] * 511)
        self.assertEqual(totals, [2046, 2044, 511])
        self.assertEqual(gl, [2, 0])
        self.assertEqual(mean, Fraction(1, 1024))
        self.assertEqual(variance, Fraction(1, 2048))

    def test_null_variance_not_evidence(self):
        self.assertEqual(load_verifier().summarize([["1"] * 9] * 512)[-1], "UNRESOLVED")

    def test_no_missing_or_extra_outcomes(self):
        check = load_verifier()
        for bad in (["0"] * 8, ["0"] * 10, ["0"] * 8 + [""], ["0"] * 8 + ["2"]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                check.summarize([bad] + [["0"] * 9] * 511)

    def test_missing_source(self):
        with self.assertRaises(ValueError):
            load_verifier().summarize([["0"] * 9] * 511)
