from __future__ import annotations

import copy
import math
import unittest
from unittest.mock import patch

import torch

from qmc_bmgs.benchmarks.countdown import CountdownTask
from qmc_bmgs.experiments.countdown_anthropic_dev import DEV_TASKS
from qmc_bmgs.experiments.countdown_thompson_source_ablation import (
    MAX_ACTIONS,
    BankCursor,
    PerturbationBank,
    _build_bank_record,
    _build_seed_plan,
    _sha256_json,
)
from qmc_bmgs.policy import (
    QMCBMGSConfig,
    QMCBMGSReasoningPolicy,
    _ToyCausalLM,
    _ToyTokenizer,
)


def _valid_bank_record() -> dict[str, object]:
    task = DEV_TASKS[0]
    seed_plan, _ = _build_seed_plan((task,), (7,))
    return _build_bank_record(task, 7, seed_plan)


def _refresh_bank_digests(record: dict[str, object], row_index: int) -> None:
    states = record["states"]
    assert isinstance(states, list)
    row = states[row_index]
    assert isinstance(row, dict)
    state_core = {key: value for key, value in row.items() if key != "state_digest"}
    row["state_digest"] = _sha256_json(state_core)
    payload = {
        key: value for key, value in record.items() if key != "deterministic_digest"
    }
    record["deterministic_digest"] = _sha256_json(payload)


class HardeningGuardTests(unittest.TestCase):
    numeric_config_fields = (
        "gamma",
        "candidate_top_k",
        "candidate_top_p",
        "min_candidates",
        "qmc_tail_candidates",
        "semantic_clusters",
        "kmeans_iterations",
        "semantic_coverage_probability",
        "semantic_uniform_mix",
        "action_prior_strength",
        "value_prior_mean",
        "value_prior_variance",
        "observation_variance",
        "uncertainty_floor",
        "lm_logprob_reward_weight",
        "prune_epsilon",
        "prune_samples",
        "prune_every_node_visits",
        "min_action_visits_before_prune",
        "min_active_actions",
        "seed",
        "normal_icdf_clip",
    )

    def test_bank_build_rejects_reproduced_task_above_dimension(self) -> None:
        task = CountdownTask((1, 2, 3, 4, 5, 6), target=100)
        self.assertEqual(len(task.legal_actions(task.initial_state)), 53)

        with patch(
            "qmc_bmgs.experiments.countdown_thompson_source_ablation."
            "_nonterminal_states",
            return_value=(task.initial_state,),
        ):
            with self.assertRaisesRegex(
                ValueError,
                r"action_count 53 exceeds perturbation-bank dimension 14",
            ):
                _build_bank_record(task, exploration_seed=7, seed_plan={})

    def test_bank_parse_rejects_action_count_above_dimension(self) -> None:
        record = copy.deepcopy(_valid_bank_record())
        states = record["states"]
        self.assertIsInstance(states, list)
        row = states[0]
        self.assertIsInstance(row, dict)
        row["action_count"] = MAX_ACTIONS + 1
        _refresh_bank_digests(record, 0)

        with self.assertRaisesRegex(
            ValueError,
            r"action_count 15 exceeds perturbation-bank dimension 14",
        ):
            PerturbationBank.from_record(record, verify_transform=True)

    def test_bank_draw_rejects_mismatch_before_consumption(self) -> None:
        bank = PerturbationBank.from_record(
            _valid_bank_record(),
            verify_transform=True,
        )
        bank_state = bank.states[0]
        requested = (
            bank_state.action_count + 1
            if bank_state.action_count < bank.max_actions
            else bank_state.action_count - 1
        )
        cursor = BankCursor(bank, "sobol")

        with self.assertRaisesRegex(
            ValueError,
            "does not match stored action_count",
        ):
            cursor.draw(bank_state.state, requested)

        self.assertEqual(cursor.point_reads, 0)
        self.assertEqual(cursor.used_coordinates, 0)
        self.assertEqual(cursor.visits, {})

    def test_bank_draw_rejects_overflow_before_consumption(self) -> None:
        bank = PerturbationBank.from_record(
            _valid_bank_record(),
            verify_transform=True,
        )
        cursor = BankCursor(bank, "iid")

        with self.assertRaisesRegex(
            ValueError,
            r"action_count 15 exceeds perturbation-bank dimension 14",
        ):
            cursor.draw(bank.states[0].state, MAX_ACTIONS + 1)

        self.assertEqual(cursor.point_reads, 0)
        self.assertEqual(cursor.used_coordinates, 0)
        self.assertEqual(cursor.visits, {})

    def test_config_rejects_nan_in_every_numeric_field(self) -> None:
        for field_name in self.numeric_config_fields:
            with self.subTest(field_name=field_name):
                with self.assertRaisesRegex(ValueError, field_name):
                    QMCBMGSConfig(**{field_name: math.nan})

    def test_config_rejects_infinite_numeric_values(self) -> None:
        for value in (math.inf, -math.inf):
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    ValueError,
                    "action_prior_strength",
                ):
                    QMCBMGSConfig(action_prior_strength=value)

    def test_config_rejects_non_integer_discrete_fields(self) -> None:
        for field_name in (
            "candidate_top_k",
            "min_candidates",
            "qmc_tail_candidates",
            "semantic_clusters",
            "kmeans_iterations",
            "prune_samples",
            "prune_every_node_visits",
            "min_action_visits_before_prune",
            "min_active_actions",
            "seed",
        ):
            with self.subTest(field_name=field_name):
                with self.assertRaisesRegex(ValueError, field_name):
                    QMCBMGSConfig(**{field_name: 1.5})
        with self.assertRaisesRegex(ValueError, "kmeans_iterations"):
            QMCBMGSConfig(kmeans_iterations=0)

    def test_non_finite_leaf_is_rejected_before_posterior_mutation(self) -> None:
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value):
                tokenizer = _ToyTokenizer()
                tokenizer.eos_token_id = None
                policy = QMCBMGSReasoningPolicy(
                    _ToyCausalLM(),
                    tokenizer,
                    QMCBMGSConfig(seed=31),
                    leaf_value_fn=lambda _state, value=value: value,
                )

                with self.assertRaisesRegex(
                    ValueError,
                    "non-finite leaf value",
                ):
                    policy.search_step(
                        (tokenizer.bos_token_id,),
                        max_depth=1,
                    )

                self.assertTrue(policy.nodes)
                for node in policy.nodes.values():
                    self.assertEqual(float(node.n.sum().item()), 0.0)
                    self.assertTrue(
                        torch.equal(node.mean, torch.zeros_like(node.mean))
                    )
                    self.assertTrue(
                        torch.equal(node.m2, torch.zeros_like(node.m2))
                    )


if __name__ == "__main__":
    unittest.main()
