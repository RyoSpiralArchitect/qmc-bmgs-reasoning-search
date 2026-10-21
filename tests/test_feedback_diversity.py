from __future__ import annotations

import copy
import hashlib
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
from qmc_bmgs_next import diversity_search as F


TASK = CountdownTask((1, 1, 1, 1, 1, 1), 6)
PROPOSAL = TrackAProposalSpec("greedy_rollout_target_error/v1")


def profile(scores=128, **overrides):
    limits = {axis: 10_000 for axis in TRACK_A_WORK_AXES}
    limits.update(legal_action_scores=scores, **overrides)
    return TrackABudgetProfile(
        "portfolio_test", "legal_action_scores", TrackAWorkBudget(**limits)
    )


def redigest(record):
    result = copy.deepcopy(record)
    result.pop("deterministic_digest")
    result["deterministic_digest"] = sha256_json(result)
    return canonical_trace_bytes(result)


class FeedbackDiversityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kw = dict(
            task=TASK,
            spec=F.DiversitySearchSpec("diverse16"),
            budget_profile=profile(),
            exploration_seed=41,
            proposal=PROPOSAL,
        )
        cls.result = F.run_diversity_search(**cls.kw)

    def test_derived_seed_contract_and_duplicate_control(self):
        values = [F.branch_seed(s, i) for s in range(32768, 32776) for i in (0, 1)]
        self.assertEqual(len(set(values)), 16)
        self.assertEqual(F.branch_seed(41, 0), F.branch_seed(41, 0))
        expected = hashlib.sha256(
            b'{"branch_index":0,"domain":"feedback-diversity-stream/v1","root_seed":41}'
        ).hexdigest()
        self.assertEqual(F.branch_seed(41, 0), int(expected[:16], 16))
        self.assertNotEqual(F.branch_seed(41, 0), F.branch_seed(41, 1))
        for bad in (True, -1, 41.0):
            with self.assertRaises(ValueError):
                F.branch_seed(bad, 0)
        with self.assertRaises(ValueError):
            F.branch_seed(41, True)
        paired = F.run_diversity_search(
            **{**self.kw, "spec": F.DiversitySearchSpec("paired16")}
        )
        self.assertEqual(
            paired.record["channels"][0]["search_record"],
            paired.record["channels"][1]["search_record"],
        )
        self.assertEqual(
            paired.record["channels"][0], self.result.record["channels"][0]
        )
        self.assertTrue(paired.summary["diversity"]["same_action_sequence"])
        self.assertFalse(paired.summary["diversity"]["complementary_success"])
        for axis in TRACK_A_WORK_AXES:
            usage = paired.record["channels"][0]["search_record"]["events"][-1][
                "payload"
            ]["summary"]["ledger_usage"][axis]
            self.assertEqual(paired.summary["ledger_usage"][axis], 2 * usage)

    def test_seed_binding_and_first_exact_diagnostics_are_replayed(self):
        for mutation in (
            lambda r: r["channels"][1].update(exploration_seed=F.branch_seed(41, 0)),
            lambda r: r["summary"]["diversity"]["branches"][0].update(
                first_exact_work={}
            ),
            lambda r: r["summary"]["diversity"].update(common_action_prefix_length=999),
        ):
            r = copy.deepcopy(self.result.record)
            mutation(r)
            with self.assertRaises((TraceValidationError, ValueError)):
                F.replay_diversity_search_bytes(redigest(r), **self.kw)

    def test_seed_collision_rejected_before_run_or_replay(self):
        with (
            patch.object(F, "branch_seed", return_value=1),
            patch.object(F, "run_countdown_track_a_search") as run,
        ):
            with self.assertRaisesRegex(ValueError, "collision"):
                F.run_diversity_search(**self.kw)
            with self.assertRaisesRegex(ValueError, "collision"):
                F.replay_diversity_search_bytes(self.result.canonical_bytes, **self.kw)
            run.assert_not_called()

    def test_first_exact_work_and_choice_diagnostics_match_charged_events(self):
        for channel, diagnostic in zip(
            self.result.record["channels"], self.result.summary["diversity"]["branches"]
        ):
            work = {a: 0 for a in TRACK_A_WORK_AXES}
            first = None
            choices = []
            for event in channel["search_record"]["events"]:
                if event.get("charge"):
                    for axis in work:
                        work[axis] += event["charge"]["delta"][axis]
                if event["kind"] == "terminal_verified" and first is None:
                    if event["payload"]["verification"]["success"]:
                        first = dict(work)
                if event["kind"] == "selection_committed":
                    choices.append(
                        {
                            k: event["payload"][k]
                            for k in ("state", "action", "trajectory_index", "depth")
                        }
                    )
            self.assertEqual(diagnostic["first_exact_work"], first)
            self.assertEqual(diagnostic["choice_count"], len(choices))
            self.assertEqual(diagnostic["choice_sequence_digest"], sha256_json(choices))

    def test_closed_arms_and_noninteger_seeds(self):
        for arm in (True, 1, "unknown", "protected16", None):
            with self.subTest(arm=arm), self.assertRaises(ValueError):
                F.DiversitySearchSpec(arm)
        for seed in (True, 1.0, -1, "41"):
            with self.subTest(seed=seed), self.assertRaises(ValueError):
                F.run_diversity_search(**{**self.kw, "exploration_seed": seed})

    def test_oracle_and_wrong_budget_type_fail_before_search(self):
        with patch.object(F, "run_countdown_track_a_search") as run:
            with self.assertRaises(ValueError):
                F.run_diversity_search(
                    **{
                        **self.kw,
                        "proposal": TrackAProposalSpec(
                            "oracle_path_count_positive_control/v1"
                        ),
                    }
                )
            p = TrackABudgetProfile("verifier", "verifier_calls", profile().budget)
            with self.assertRaises(ValueError):
                F.run_diversity_search(**{**self.kw, "budget_profile": p})
            with self.assertRaises(TypeError):
                F.run_diversity_search(**{**self.kw, "spec": "diverse16"})
            run.assert_not_called()

    def test_split_conserves_all_axes_even_when_odd(self):
        p = profile(257, verifier_calls=19, transitions=999)
        plans = F.channel_plan(F.DiversitySearchSpec("diverse16"), p)
        self.assertEqual([r[2].budget.legal_action_scores for r in plans], [128, 129])
        self.assertEqual([r[2].budget.verifier_calls for r in plans], [9, 10])
        for axis in TRACK_A_WORK_AXES:
            self.assertEqual(
                sum(getattr(r[2].budget, axis) for r in plans), getattr(p.budget, axis)
            )
        with self.assertRaises(ValueError):
            F.channel_plan(F.DiversitySearchSpec("diverse16"), profile(1))

    def test_exact_channel_is_identical_to_its_allocated_baseline(self):
        _, method, p = F.channel_plan(self.kw["spec"], self.kw["budget_profile"])[0]
        baseline = run_countdown_track_a_search(
            TASK,
            method=method,
            budget_profile=p,
            proposal=PROPOSAL,
            exploration_seed=F.branch_seed(41, 0),
        )
        self.assertEqual(
            self.result.record["channels"][0]["search_record"], baseline.record
        )
        self.assertEqual(
            self.result.summary["primary_allocated_budget_success"],
            baseline.summary["success_any"],
        )
        if baseline.summary["success_any"]:
            self.assertTrue(self.result.summary["success_any"])
        self.assertFalse(self.result.summary["protects_full_budget_baseline"])

    def test_single_channel_controls_are_exact_engine_calls(self):
        for arm in ("single16",):
            spec = F.DiversitySearchSpec(arm)
            result = F.run_diversity_search(**{**self.kw, "spec": spec})
            _, method, p = F.channel_plan(spec, self.kw["budget_profile"])[0]
            baseline = run_countdown_track_a_search(
                TASK,
                proposal=PROPOSAL,
                method=method,
                budget_profile=p,
                exploration_seed=F.branch_seed(41, 0),
            )
            self.assertEqual(
                result.record["channels"][0]["search_record"], baseline.record
            )
            self.assertEqual(
                result.summary["success_any"], baseline.summary["success_any"]
            )

    def test_no_cross_branch_budget_cache_or_success_short_circuit(self):
        real = F.run_countdown_track_a_search
        with patch.object(F, "run_countdown_track_a_search", wraps=real) as run:
            result = F.run_diversity_search(**self.kw)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(result.canonical_bytes, self.result.canonical_bytes)
        for i, call in enumerate(run.call_args_list):
            self.assertEqual(
                call.kwargs["budget_profile"].budget.legal_action_scores, 64
            )
            self.assertEqual(call.kwargs["exploration_seed"], F.branch_seed(41, i))
        for axis in TRACK_A_WORK_AXES:
            total = sum(
                row["search_record"]["events"][-1]["payload"]["summary"][
                    "ledger_usage"
                ][axis]
                for row in result.record["channels"]
            )
            self.assertEqual(result.summary["ledger_usage"][axis], total)
            self.assertLessEqual(total, getattr(self.kw["budget_profile"].budget, axis))

    def test_readout_retains_exact_witness_and_adds_no_verifier_work(self):
        # A larger cap on the excluded all-ones fixture exercises successful
        # readout without assuming that every short stochastic run succeeds.
        r = F.run_diversity_search(
            **{**self.kw, "budget_profile": profile(1024)}
        ).summary
        self.assertTrue(r["success_any"])
        self.assertEqual(r["minimum_terminal_error"], 0)
        self.assertEqual(r["readout"]["absolute_error"], 0)
        self.assertTrue(r["readout"]["verification"]["source_use_exact"])
        self.assertEqual(r["readout_extra_verifier_calls"], 0)
        self.assertTrue(
            any(b["first_exact_work"] is not None for b in r["diversity"]["branches"])
        )

    def test_nonexact_readout_uses_verified_minimum_error(self):
        task = CountdownTask((1, 1, 1, 1, 1, 1), 999)
        result = F.run_diversity_search(**{**self.kw, "task": task})
        self.assertFalse(result.summary["success_any"])
        observed = [
            abs(e["payload"]["verification"]["final_value"] - 999)
            for c in result.record["channels"]
            for e in c["search_record"]["events"]
            if e["kind"] == "terminal_verified"
        ]
        self.assertEqual(result.summary["minimum_terminal_error"], min(observed))
        self.assertEqual(result.summary["readout"]["absolute_error"], min(observed))

    def test_missing_terminal_error_is_null_not_zero(self):
        result = F.run_diversity_search(**{**self.kw, "budget_profile": profile(2)})
        self.assertFalse(result.summary["success_any"])
        self.assertEqual(result.summary["terminal_count"], 0)
        self.assertIsNone(result.summary["minimum_terminal_error"])
        self.assertIsNone(result.summary["readout"])

    def test_secondary_guard_failure_remains_visible(self):
        result = F.run_diversity_search(
            **{**self.kw, "budget_profile": profile(verifier_calls=0)}
        )
        self.assertFalse(result.summary["budget_valid"])
        self.assertEqual(result.summary["ledger_usage"]["verifier_calls"], 0)

    def test_generative_replay_and_strict_whole_bytes(self):
        self.assertEqual(
            F.replay_diversity_search_bytes(self.result.canonical_bytes, **self.kw),
            self.result.canonical_bytes,
        )
        with self.assertRaises(TraceValidationError):
            F.replay_diversity_search_bytes(
                self.result.canonical_bytes + b"\n", **self.kw
            )

    def test_forged_summary_even_with_new_digest_rejected(self):
        r = copy.deepcopy(self.result.record)
        r["summary"]["ledger_usage"]["legal_action_scores"] = 0
        with self.assertRaises(TraceValidationError):
            F.replay_diversity_search_bytes(redigest(r), **self.kw)

    def test_missing_channel_and_unknown_fields_rejected(self):
        for mutation in (
            lambda x: x["channels"].pop(),
            lambda x: x.update(extra=True),
            lambda x: x["channels"][0].update(extra=True),
        ):
            r = copy.deepcopy(self.result.record)
            mutation(r)
            with self.assertRaises(TraceValidationError):
                F.replay_diversity_search_bytes(redigest(r), **self.kw)

    def test_identity_aliases_and_channel_swaps_rejected(self):
        for mutation in (
            lambda x: x.update(exploration_seed=41.0),
            lambda x: x["channels"].reverse(),
            lambda x: x["channels"][0]["budget_profile"]["budget"].update(
                legal_action_scores=64.0
            ),
            lambda x: x["channels"][0]["search_record"]["events"][0]["payload"].update(
                extra=True
            ),
        ):
            r = copy.deepcopy(self.result.record)
            mutation(r)
            with self.assertRaises((TraceValidationError, ValueError)):
                F.replay_diversity_search_bytes(redigest(r), **self.kw)


if __name__ == "__main__":
    unittest.main()
