from __future__ import annotations

import math
import unittest
from dataclasses import FrozenInstanceError

from qmc_bmgs.benchmarks.countdown import (
    CountdownAction,
    CountdownState,
    CountdownTask,
)
from qmc_bmgs.substrate.proposals import (
    TRACK_A_PROPOSAL_POLICY_IDS,
    TrackAProposalRow,
    TrackAProposalSpec,
    evaluate_track_a_proposal,
)
from qmc_bmgs.substrate.trace import sha256_json


class AlteredProposalTask(CountdownTask):
    def legal_actions(
        self,
        state: CountdownState,
    ) -> tuple[CountdownAction, ...]:
        return tuple(reversed(super().legal_actions(state)))


class TrackAProposalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.task = CountdownTask((1, 2, 3, 4, 5, 6), target=720)

    def test_policy_ids_are_closed_and_positive_control_is_explicit(self) -> None:
        specs = tuple(
            TrackAProposalSpec(policy_id) for policy_id in (TRACK_A_PROPOSAL_POLICY_IDS)
        )
        self.assertEqual(
            [spec.positive_control for spec in specs],
            [False, False, True],
        )
        self.assertEqual(len({spec.deterministic_digest for spec in specs}), 3)
        with self.assertRaises(ValueError):
            TrackAProposalSpec("unknown/v1")
        with self.assertRaises(ValueError):
            TrackAProposalSpec(True)  # type: ignore[arg-type]

    def test_uniform_row_preserves_canonical_action_order_and_normalizes(self) -> None:
        spec = TrackAProposalSpec("uniform/v1")
        row = evaluate_track_a_proposal(
            self.task,
            tuple(reversed(self.task.initial_state)),
            spec,
        )
        expected_actions = self.task.legal_actions(self.task.initial_state)

        self.assertEqual(row.state, self.task.initial_state)
        self.assertEqual(row.actions, expected_actions)
        self.assertEqual(row.raw_scores, (0.0,) * len(expected_actions))
        self.assertEqual(row.internal_transition_evaluations, 0)
        self.assertAlmostEqual(math.fsum(math.exp(x) for x in row.prior_logp), 1.0)
        self.assertEqual(
            row.action_order_digest,
            sha256_json([action.to_dict() for action in expected_actions]),
        )
        self.assertEqual(row.behavior_digest, row.deterministic_digest)
        self.assertEqual(row.to_dict()["behavior_digest"], row.behavior_digest)
        self.assertFalse(row.positive_control)

    def test_rows_are_immutable_and_reproducible_without_retained_cache(self) -> None:
        spec = TrackAProposalSpec("greedy_rollout_target_error/v1")
        first = evaluate_track_a_proposal(self.task, self.task.initial_state, spec)
        second = evaluate_track_a_proposal(self.task, self.task.initial_state, spec)

        self.assertEqual(first, second)
        self.assertEqual(first.behavior_digest, second.behavior_digest)
        with self.assertRaises(FrozenInstanceError):
            first.raw_scores = ()  # type: ignore[misc]

        uniform = evaluate_track_a_proposal(
            self.task,
            self.task.initial_state,
            TrackAProposalSpec("uniform/v1"),
        )
        self.assertNotEqual(first.behavior_digest, uniform.behavior_digest)

    def test_greedy_rollout_solves_the_720_fixture_and_has_finite_rank_logits(
        self,
    ) -> None:
        spec = TrackAProposalSpec("greedy_rollout_target_error/v1")
        state = self.task.initial_state
        trace: list[CountdownAction] = []

        root = evaluate_track_a_proposal(self.task, state, spec)
        self.assertEqual(
            sorted(root.raw_scores, reverse=True),
            [-float(index) for index in range(len(root.actions))],
        )
        self.assertTrue(all(math.isfinite(value) for value in root.raw_scores))
        self.assertTrue(all(math.isfinite(value) for value in root.prior_logp))
        self.assertEqual(
            root.internal_transition_evaluations,
            len(root.actions) * (len(state) - 1),
        )

        while len(state) > 1:
            row = evaluate_track_a_proposal(self.task, state, spec)
            selected = max(range(len(row.actions)), key=row.raw_scores.__getitem__)
            action = row.actions[selected]
            trace.append(action)
            state = self.task.transition(state, action)

        verification = self.task.verify(trace)
        self.assertTrue(verification.success)
        self.assertEqual(verification.final_value, 720)

    def test_greedy_rollout_frozen_small_fixture_proves_tie_break_order(
        self,
    ) -> None:
        task = CountdownTask((1, 2, 3, 4, 5, 6), target=2)
        row = evaluate_track_a_proposal(
            task,
            (1, 1, 2),
            TrackAProposalSpec("greedy_rollout_target_error/v1"),
        )
        self.assertEqual(
            row.raw_scores,
            (-6.0, -2.0, -3.0, -4.0, -0.0, -5.0, -1.0),
        )
        self.assertEqual(row.internal_transition_evaluations, 14)

        # Frozen independent features for the relevant arms are
        # (terminal error, immediate error, canonical index):
        #   1+1 -> (1, 0, 0), 1+2 -> (0, 1, 1),
        #   2-1 -> (0, 1, 2), 1*2 -> (0, 0, 4).
        # These three comparisons separately prove the precedence order.
        score_by_action = dict(zip(row.actions, row.raw_scores))
        self.assertGreater(
            score_by_action[CountdownAction(1, 2, "+")],
            score_by_action[CountdownAction(1, 1, "+")],
        )
        self.assertGreater(
            score_by_action[CountdownAction(1, 2, "*")],
            score_by_action[CountdownAction(1, 2, "+")],
        )
        self.assertGreater(
            score_by_action[CountdownAction(1, 2, "+")],
            score_by_action[CountdownAction(2, 1, "-")],
        )

    def test_oracle_has_exact_small_path_counts_and_internal_work(self) -> None:
        task = CountdownTask((1, 2, 3, 4, 5, 6), target=3)
        spec = TrackAProposalSpec("oracle_path_count_positive_control/v1")
        row = evaluate_track_a_proposal(task, (1, 1, 1), spec)

        self.assertEqual(
            row.actions,
            (
                CountdownAction(1, 1, "+"),
                CountdownAction(1, 1, "*"),
                CountdownAction(1, 1, "/"),
            ),
        )
        self.assertEqual(row.raw_scores, (1.0, 0.0, 0.0))
        # Three root candidate transitions plus expansion of the two unique
        # two-value children: four actions for (1,2), three for (1,1).
        self.assertEqual(row.internal_transition_evaluations, 3 + 4 + 3)
        self.assertTrue(row.positive_control)
        self.assertAlmostEqual(math.fsum(math.exp(x) for x in row.prior_logp), 1.0)

    def test_task_subclasses_and_terminal_states_are_rejected(self) -> None:
        altered = AlteredProposalTask(self.task.inputs, self.task.target)
        with self.assertRaisesRegex(TypeError, "exactly CountdownTask"):
            evaluate_track_a_proposal(
                altered,
                altered.initial_state,
                TrackAProposalSpec("uniform/v1"),
            )
        with self.assertRaisesRegex(ValueError, "terminal or actionless"):
            evaluate_track_a_proposal(
                self.task,
                (self.task.target,),
                TrackAProposalSpec("uniform/v1"),
            )

    def test_row_constructor_rejects_noncanonical_or_renormalized_material(
        self,
    ) -> None:
        row = evaluate_track_a_proposal(
            self.task,
            self.task.initial_state,
            TrackAProposalSpec("uniform/v1"),
        )
        with self.assertRaisesRegex(ValueError, "stable log-softmax"):
            TrackAProposalRow(
                spec=row.spec,
                task_fingerprint=row.task_fingerprint,
                state=row.state,
                actions=row.actions,
                raw_scores=row.raw_scores,
                prior_logp=tuple(0.0 for _ in row.prior_logp),
                internal_transition_evaluations=0,
            )
        with self.assertRaisesRegex(ValueError, "canonical Countdown state"):
            TrackAProposalRow(
                spec=row.spec,
                task_fingerprint=row.task_fingerprint,
                state=tuple(reversed(row.state)),
                actions=row.actions,
                raw_scores=row.raw_scores,
                prior_logp=row.prior_logp,
                internal_transition_evaluations=0,
            )
        with self.assertRaisesRegex(ValueError, "canonical action order"):
            TrackAProposalRow(
                spec=row.spec,
                task_fingerprint=row.task_fingerprint,
                state=row.state,
                actions=tuple(reversed(row.actions)),
                raw_scores=tuple(reversed(row.raw_scores)),
                prior_logp=tuple(reversed(row.prior_logp)),
                internal_transition_evaluations=0,
            )

    def test_row_constructor_rejects_truncated_and_illegal_action_sets(self) -> None:
        row = evaluate_track_a_proposal(
            self.task,
            self.task.initial_state,
            TrackAProposalSpec("uniform/v1"),
        )

        truncated_actions = row.actions[:-1]
        truncated_raw = (0.0,) * len(truncated_actions)
        truncated_prior = (-math.log(len(truncated_actions)),) * len(truncated_actions)
        with self.assertRaisesRegex(ValueError, "complete Countdown v1"):
            TrackAProposalRow(
                spec=row.spec,
                task_fingerprint=row.task_fingerprint,
                state=row.state,
                actions=truncated_actions,
                raw_scores=truncated_raw,
                prior_logp=truncated_prior,
                internal_transition_evaluations=0,
            )

        illegal = CountdownAction(999, 1000, "+")
        illegal_actions = tuple(
            sorted((*row.actions[:-1], illegal), key=CountdownAction.sort_key)
        )
        illegal_raw = (0.0,) * len(illegal_actions)
        illegal_prior = (-math.log(len(illegal_actions)),) * len(illegal_actions)
        with self.assertRaisesRegex(ValueError, "complete Countdown v1"):
            TrackAProposalRow(
                spec=row.spec,
                task_fingerprint=row.task_fingerprint,
                state=row.state,
                actions=illegal_actions,
                raw_scores=illegal_raw,
                prior_logp=illegal_prior,
                internal_transition_evaluations=0,
            )

    def test_prior_logp_rejects_numeric_aliases_and_nonfinite_values(self) -> None:
        actions = self.task.legal_actions(self.task.initial_state)
        raw_scores = (1000.0,) + (0.0,) * (len(actions) - 1)
        # The stable reference is exactly 0.0 for the first arm and -1000.0
        # for every other arm because exp(-1000) underflows to zero.
        valid_prior = (0.0,) + (-1000.0,) * (len(actions) - 1)

        for replacement in (False, 0, math.nan, math.inf, -math.inf):
            with self.subTest(replacement=replacement):
                invalid = (replacement,) + valid_prior[1:]
                with self.assertRaisesRegex(ValueError, "finite plain floats"):
                    TrackAProposalRow(
                        spec=TrackAProposalSpec("uniform/v1"),
                        task_fingerprint=self.task.task_fingerprint,
                        state=self.task.initial_state,
                        actions=actions,
                        raw_scores=raw_scores,
                        prior_logp=invalid,  # type: ignore[arg-type]
                        internal_transition_evaluations=0,
                    )

        integer_alias = (0.0, -1000) + valid_prior[2:]
        with self.assertRaisesRegex(ValueError, "finite plain floats"):
            TrackAProposalRow(
                spec=TrackAProposalSpec("uniform/v1"),
                task_fingerprint=self.task.task_fingerprint,
                state=self.task.initial_state,
                actions=actions,
                raw_scores=raw_scores,
                prior_logp=integer_alias,  # type: ignore[arg-type]
                internal_transition_evaluations=0,
            )


if __name__ == "__main__":
    unittest.main()
