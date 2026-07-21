from __future__ import annotations

import unittest

import torch
from torch.quasirandom import SobolEngine

from qmc_bmgs.benchmarks.countdown import _run_self_test as countdown_self_test
from qmc_bmgs.benchmarks.role_lock import (
    CHANNEL_ABLATION_VARIANTS,
    BenchmarkPolicy,
    CandidateRegistry,
    CoordinateMuxEngine,
    RoleLockLM,
    RoleLockTask,
    RoleLockTokenizer,
    SeedPlan,
    UniformSourcePlan,
    _run_self_test as benchmark_self_test,
    benchmark_config,
)
from qmc_bmgs.experiments.channel_ablation import _self_test as channel_self_test
from qmc_bmgs.experiments.credit_assignment import (
    _self_test as credit_assignment_self_test,
)
from qmc_bmgs.experiments.d4_noise_sweep import _self_test as d4_self_test
from qmc_bmgs.experiments.fixed_verifier_budget import (
    _self_test as fixed_verifier_self_test,
)
from qmc_bmgs.experiments.two_phase_sampler import (
    _self_test as two_phase_self_test,
)
from qmc_bmgs.experiments.two_phase_validation import (
    _self_test as two_phase_validation_self_test,
)
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

    def test_countdown_self_test(self) -> None:
        countdown_self_test()

    def test_d4_self_test(self) -> None:
        d4_self_test()

    def test_channel_ablation_self_test(self) -> None:
        channel_self_test()

    def test_fixed_verifier_self_test(self) -> None:
        fixed_verifier_self_test()

    def test_two_phase_self_test(self) -> None:
        two_phase_self_test()

    def test_two_phase_validation_self_test(self) -> None:
        two_phase_validation_self_test()

    def test_credit_assignment_self_test(self) -> None:
        credit_assignment_self_test()

    def test_mux_source_switch_preserves_both_streams(self) -> None:
        all_sobol = UniformSourcePlan("sobol", "sobol", "sobol")
        routing_only = UniformSourcePlan("sobol", "sobol", "iid")
        engine = CoordinateMuxEngine(
            6,
            17,
            all_sobol,
            SobolEngine(6, scramble=True, seed=31),
        )
        engine.draw(5)
        before = engine.stream_state_digest()
        sobol_engine = engine.sobol_engine
        iid_engine = engine.iid_engine
        engine.set_sources(routing_only)
        self.assertEqual(before, engine.stream_state_digest())
        self.assertEqual(engine.points_drawn, 5)
        self.assertIs(engine.sobol_engine, sobol_engine)
        self.assertIs(engine.iid_engine, iid_engine)

        continued = engine.draw(3)
        reference = CoordinateMuxEngine(
            6,
            17,
            all_sobol,
            SobolEngine(6, scramble=True, seed=31),
        )
        reference.draw(5)
        reference.set_sources(routing_only)
        expected = reference.draw(3)
        self.assertTrue(torch.equal(continued, expected))
        self.assertEqual(engine.selected_sobol_scalar_values, 36)
        self.assertEqual(engine.selected_iid_scalar_values, 12)
        self.assertEqual(
            engine.source_plan_points,
            {"sobol/sobol/sobol": 5, "sobol/sobol/iid": 3},
        )
        self.assertEqual(engine.reconfiguration_count, 1)

    def test_policy_switch_updates_existing_and_future_nodes(self) -> None:
        task = RoleLockTask(4)
        variant = next(
            item for item in CHANNEL_ABLATION_VARIANTS if item.name == "sobol_all"
        )
        seeds = SeedPlan(task_seed=4, exploration_seed=19, partition_seed=10_000)
        policy = BenchmarkPolicy(
            RoleLockLM(task),
            RoleLockTokenizer(),
            benchmark_config(task, variant, seeds.exploration_seed),
            variant=variant,
            task=task,
            seeds=seeds,
            registry=CandidateRegistry(),
        )
        policy.run_to_fixed_verifier_budget(
            task.root,
            verifier_budget=3,
            lm_node_ceiling=64,
            edge_ceiling=128,
        )
        existing = [
            node.qmc_engine.engine  # type: ignore[attr-defined]
            for node in policy.nodes.values()
        ]
        points = [engine.points_drawn for engine in existing]
        values = {
            state: (node.n.clone(), node.mean.clone(), node.m2.clone())
            for state, node in policy.nodes.items()
        }
        routing_only = UniformSourcePlan("sobol", "sobol", "iid")
        policy.set_uniform_sources(
            routing_only,
            verifier_request=3,
            reason="unit_test",
        )
        self.assertEqual([engine.points_drawn for engine in existing], points)
        self.assertTrue(all(engine.sources == routing_only for engine in existing))
        self.assertTrue(all(engine.reconfiguration_count == 1 for engine in existing))
        for state, (n, mean, m2) in values.items():
            self.assertTrue(torch.equal(policy.nodes[state].n, n))
            self.assertTrue(torch.equal(policy.nodes[state].mean, mean))
            self.assertTrue(torch.equal(policy.nodes[state].m2, m2))
        future = policy.get_or_create_node((0, 10, 10, 10))
        future_engine = future.qmc_engine.engine  # type: ignore[attr-defined]
        self.assertEqual(future_engine.sources, routing_only)
        self.assertEqual(future_engine.reconfiguration_count, 0)
        self.assertEqual(len(policy.uniform_source_switch_log), 1)
        self.assertEqual(
            policy.uniform_source_switch_log[0]["completed_verifier_requests"],
            3,
        )

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
