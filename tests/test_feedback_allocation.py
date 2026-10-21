from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from qmc_bmgs.benchmarks.countdown import CountdownTask
from qmc_bmgs.substrate.budget import TRACK_A_WORK_AXES, TrackAWorkBudget
from qmc_bmgs.substrate.countdown_search import (
    TrackABudgetProfile,
    run_countdown_track_a_search,
)
from qmc_bmgs.substrate.proposals import TrackAProposalSpec
from qmc_bmgs.substrate.trace import (
    TraceValidationError,
    canonical_trace_bytes,
    sha256_json,
)
from qmc_bmgs_next import allocation_search as A
from qmc_bmgs_next import diversity_search as D

TASK = CountdownTask((1, 1, 1, 1, 1, 1), 6)


def profile(scores=512, **overrides):
    limits = {axis: 100_000 for axis in TRACK_A_WORK_AXES}
    limits.update(legal_action_scores=scores, **overrides)
    return TrackABudgetProfile(
        "allocation_test", "legal_action_scores", TrackAWorkBudget(**limits)
    )


def redigest(record):
    record = copy.deepcopy(record)
    record.pop("deterministic_digest")
    record["deterministic_digest"] = sha256_json(record)
    return canonical_trace_bytes(record)


def events(channel):
    return [
        (e["kind"], e["payload"], e.get("charge"))
        for e in channel["search_record"]["events"]
        if e["kind"] != "search_finished"
    ]


class AllocationSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kw = dict(task=TASK, budget_profile=profile(), exploration_seed=41)
        cls.results = {
            arm: A.run_allocation_search(**cls.kw, spec=A.AllocationSearchSpec(arm))
            for arm in A.ARMS
        }

    def test_three_fixed_allocations_conserve_seven_axes_and_remainders(self):
        expected = {"single16": [512], "equal16": [256, 256], "weighted16": [384, 128]}
        for arm, caps in expected.items():
            plans = A.channel_plan(A.AllocationSearchSpec(arm), profile())
            self.assertEqual([p.budget.legal_action_scores for _, _, p in plans], caps)
            if arm == "weighted16":
                self.assertEqual(
                    [p.budget.verifier_calls for _, _, p in plans], [75000, 25000]
                )
            odd = profile(513, transitions=100003, verifier_calls=7)
            plans = A.channel_plan(A.AllocationSearchSpec(arm), odd)
            for axis in TRACK_A_WORK_AXES:
                self.assertEqual(
                    sum(getattr(p.budget, axis) for _, _, p in plans),
                    getattr(odd.budget, axis),
                )
        plans = A.channel_plan(A.AllocationSearchSpec("weighted16"), odd)
        self.assertEqual(
            [p.budget.legal_action_scores for _, _, p in plans], [384, 129]
        )

    def test_reference_arms_are_identical_to_reviewed_engine_branches(self):
        for arm, prior in (("single16", "single16"), ("equal16", "diverse16")):
            old = D.run_diversity_search(**self.kw, spec=D.DiversitySearchSpec(prior))
            self.assertEqual(
                self.results[arm].record["channels"], old.record["channels"]
            )
            self.assertEqual(self.results[arm].summary, old.summary)
        for i, (name, method, p) in enumerate(
            A.channel_plan(A.AllocationSearchSpec("weighted16"), profile())
        ):
            result = run_countdown_track_a_search(
                TASK,
                method=method,
                budget_profile=p,
                exploration_seed=D.branch_seed(41, i),
                proposal=TrackAProposalSpec("greedy_rollout_target_error/v1"),
            )
            self.assertEqual(
                self.results["weighted16"].record["channels"][i]["search_record"],
                result.record,
            )

    def test_new_primary_and_secondary_boundaries_are_decision_work_prefixes(self):
        single, equal, weighted = (self.results[a].record["channels"] for a in A.ARMS)
        for lo, hi in (
            (equal[0], weighted[0]),
            (weighted[0], single[0]),
            (equal[0], single[0]),
            (weighted[1], equal[1]),
        ):
            self.assertEqual(lo["exploration_seed"], hi["exploration_seed"])
            a, b = events(lo), events(hi)
            self.assertEqual(a, b[: len(a)])

    def test_smallest_branch_completes_first_trajectory_on_excluded_fixtures(self):
        # Feasibility on known excluded sources, not a universal performance claim.
        for inputs, target in (
            ((1, 1, 1, 1, 1, 1), 6),
            ((1, 2, 3, 4, 5, 6), 100),
            ((2, 2, 3, 4, 5, 7), 100),
        ):
            result = A.run_allocation_search(
                task=CountdownTask(inputs, target),
                budget_profile=profile(),
                exploration_seed=41,
                spec=A.AllocationSearchSpec("weighted16"),
            )
            for channel in result.record["channels"]:
                self.assertGreater(
                    channel["search_record"]["events"][-1]["payload"]["summary"][
                        "terminal_count"
                    ],
                    0,
                )

    def test_both_branches_execute_without_transfer_or_success_shortcut(self):
        # Larger cap on the excluded fixture checks success does not stop branch 2.
        with patch.object(
            A, "run_countdown_track_a_search", wraps=run_countdown_track_a_search
        ) as run:
            result = A.run_allocation_search(
                **{**self.kw, "budget_profile": profile(2048)},
                spec=A.AllocationSearchSpec("weighted16"),
            )
        self.assertTrue(result.summary["success_any"])
        self.assertEqual(run.call_count, 2)
        self.assertEqual(
            [
                c.kwargs["budget_profile"].budget.legal_action_scores
                for c in run.call_args_list
            ],
            [1536, 512],
        )
        for axis in TRACK_A_WORK_AXES:
            spent = sum(
                c["search_record"]["events"][-1]["payload"]["summary"]["ledger_usage"][
                    axis
                ]
                for c in result.record["channels"]
            )
            self.assertEqual(result.summary["ledger_usage"][axis], spent)
            self.assertEqual(
                spent + result.summary["unspent_work"][axis],
                getattr(profile(2048).budget, axis),
            )
        self.assertEqual(result.summary["readout_extra_verifier_calls"], 0)

    def test_missingness_and_secondary_guard_are_not_hidden(self):
        for p, terminal, valid in (
            (profile(4), 0, True),
            (profile(verifier_calls=0), 0, False),
        ):
            result = A.run_allocation_search(
                **{**self.kw, "budget_profile": p},
                spec=A.AllocationSearchSpec("weighted16"),
            )
            self.assertEqual(result.summary["terminal_count"], terminal)
            self.assertIsNone(result.summary["minimum_terminal_error"])
            self.assertEqual(result.summary["budget_valid"], valid)

    def test_replay_binds_allocations_inputs_and_complete_charged_evidence(self):
        spec = A.AllocationSearchSpec("weighted16")
        raw = self.results["weighted16"].canonical_bytes
        self.assertEqual(
            A.replay_allocation_search_bytes(raw, **self.kw, spec=spec), raw
        )
        changes = [
            lambda r: r["channels"].reverse(),
            lambda r: r["channels"][0]["budget_profile"]["budget"].update(
                legal_action_scores=384.0
            ),
            lambda r: r["summary"]["ledger_usage"].update(legal_action_scores=0),
            lambda r: r["spec"].update(allocation_weights=[1, 1]),
            lambda r: r["channels"][1].update(exploration_seed=D.branch_seed(41, 0)),
            lambda r: r.update(extra=True),
        ]
        for change in changes:
            record = copy.deepcopy(self.results["weighted16"].record)
            change(record)
            with self.assertRaises((TraceValidationError, ValueError)):
                A.replay_allocation_search_bytes(redigest(record), **self.kw, spec=spec)
        with self.assertRaises(TraceValidationError):
            A.replay_allocation_search_bytes(raw + b"\n", **self.kw, spec=spec)

    def test_closed_inputs_and_collisions_fail_before_search(self):
        for arm in ("paired16", "diverse16", "adaptive", None, 1, True):
            with self.assertRaises(ValueError):
                A.AllocationSearchSpec(arm)
        with patch.object(A, "run_countdown_track_a_search") as run:
            for seed in (True, -1, 41.0):
                with self.assertRaises(ValueError):
                    A.run_allocation_search(
                        **{**self.kw, "exploration_seed": seed},
                        spec=A.AllocationSearchSpec("weighted16"),
                    )
            with patch.object(A, "branch_seed", return_value=1):
                with self.assertRaisesRegex(ValueError, "collision"):
                    A.run_allocation_search(
                        **self.kw, spec=A.AllocationSearchSpec("weighted16")
                    )
            with self.assertRaises(ValueError):
                A.run_allocation_search(
                    **self.kw,
                    spec=A.AllocationSearchSpec("weighted16"),
                    proposal=TrackAProposalSpec(
                        "oracle_path_count_positive_control/v1"
                    ),
                )
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
