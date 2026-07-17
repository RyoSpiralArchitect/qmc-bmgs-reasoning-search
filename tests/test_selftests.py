from __future__ import annotations

import unittest

from qmc_bmgs.benchmarks.role_lock import _run_self_test as benchmark_self_test
from qmc_bmgs.experiments.channel_ablation import _self_test as channel_self_test
from qmc_bmgs.experiments.d4_noise_sweep import _self_test as d4_self_test
from qmc_bmgs.policy import QMCBMGSConfig
from qmc_bmgs.policy import _run_self_test as policy_self_test
from qmc_bmgs.records import canonical_record_digest


class RepositorySelfTests(unittest.TestCase):
    def test_public_config_import(self) -> None:
        self.assertEqual(QMCBMGSConfig().gamma, 0.99)

    def test_policy_self_test(self) -> None:
        policy_self_test(verbose=False)

    def test_benchmark_self_test(self) -> None:
        benchmark_self_test()

    def test_d4_self_test(self) -> None:
        d4_self_test()

    def test_channel_ablation_self_test(self) -> None:
        channel_self_test()

    def test_record_digest_ignores_wall_time_only(self) -> None:
        first = {"usage": {"wall_time_s": 1.0, "calls": 3}, "value": 4}
        second = {"usage": {"wall_time_s": 9.0, "calls": 3}, "value": 4}
        self.assertEqual(
            canonical_record_digest(first), canonical_record_digest(second)
        )
        second["value"] = 5
        self.assertNotEqual(
            canonical_record_digest(first), canonical_record_digest(second)
        )


if __name__ == "__main__":
    unittest.main()
