import copy
from fractions import Fraction
import math
import unittest

from qmc_bmgs_next.allocation_statistics import source_readout, uncertainty_contract


def blocks(differences, seeds=tuple(range(8))):
    result = []
    for source, difference in enumerate(differences):
        for index, seed in enumerate(seeds):
            result.append(
                dict(
                    task_slot=source,
                    seed=seed,
                    weighted16={"success_any": difference > 0 and index < difference},
                    single16={"success_any": difference < 0 and index < -difference},
                )
            )
    return result


class AllocationStatisticsTests(unittest.TestCase):
    def readout(self, values):
        return source_readout(blocks(values), len(values), tuple(range(8)))

    def test_exact_source_moments_not_seed_pseudoreplication(self):
        r = self.readout([0, 2] * 128)
        self.assertEqual(r["mean_rational"], [1, 8])
        # 128 at zero and 128 at 1/4: sum squared deviations = 4.
        self.assertEqual(r["sample_source_variance_rational"], [4, 255])
        half = 2 * math.sqrt(float(Fraction(4, 255)) / 256)
        self.assertAlmostEqual(r["half_width"], half)
        self.assertEqual(r["repeated_block_count"], 2048)
        self.assertEqual(r["source_count"], 256)
        self.assertEqual(r["development_readout"], "PROMISING_FOR_FRESH_CONFIRMATION")
        self.assertIsNone(r["winner"])
        self.assertIsNone(r["scientific_decision"])

    def test_negative_null_and_imprecision_are_retained(self):
        negative = self.readout([0, -2] * 128)
        self.assertEqual(negative["development_readout"], "NO_PRACTICAL_UPLIFT_SIGNAL")
        imprecise = self.readout([-8, 8] * 128)
        self.assertEqual(imprecise["development_readout"], "IMPRECISE")
        self.assertFalse(imprecise["precision_target_met"])
        # Near the practical threshold with nonzero variance remains unresolved.
        r = self.readout([1] * 40 + [0] * 216)
        self.assertEqual(r["development_readout"], "UNRESOLVED")

    def test_degenerate_and_small_sample_never_claim_certainty(self):
        for values in ([0] * 256, [8] * 256, [-8] * 256, [0, 2], [0]):
            r = self.readout(values)
            self.assertIsNone(r["approximate_interval"])
            self.assertIsNone(r["half_width"])
            self.assertIsNone(r["precision_target_met"])
            self.assertEqual(r["development_readout"], "UNRESOLVED")

    def test_matrix_types_missing_duplicate_foreign_rejected(self):
        rows = blocks([0, 2])
        for mutate in (
            lambda r: r.pop(),
            lambda r: r.append(copy.deepcopy(r[0])),
            lambda r: r[0].update(task_slot=False),
            lambda r: r[0].update(seed=99),
            lambda r: r[0]["weighted16"].update(success_any=1),
        ):
            changed = copy.deepcopy(rows)
            mutate(changed)
            with self.assertRaises(ValueError):
                source_readout(changed, 2, tuple(range(8)))
        for seeds in ([], [0, 0], [False], [1.0]):
            with self.assertRaises(ValueError):
                source_readout(rows, 2, seeds)

    def test_precision_scenarios_and_contract_are_fixed(self):
        c = uncertainty_contract()
        self.assertEqual(c["source_count"], 256)
        for scenario in c["precision_scenarios"]:
            self.assertEqual(
                2 * scenario["source_sd"] / 16, scenario["half_width_at_256_sources"]
            )
        self.assertFalse(c["sequential_extension"])
        self.assertFalse(c["default_promotion"])


if __name__ == "__main__":
    unittest.main()
