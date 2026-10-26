"""Outcome-independent selector contracts and previously used search fixtures."""

import copy
import math
import os
from pathlib import Path
import random
import subprocess
import sys
import unittest

from qmc_bmgs.benchmarks.countdown import CountdownTask
from qmc_bmgs.substrate import countdown_search as core
from qmc_bmgs.substrate.budget import TRACK_A_WORK_AXES, TrackAWorkBudget
from qmc_bmgs.substrate.proposals import evaluate_track_a_proposal
from qmc_bmgs.substrate.trace import (
    TraceValidationError,
    canonical_trace_bytes,
    sha256_json,
)
from qmc_bmgs_next import prior_tilt as P
from qmc_bmgs_next import search_value as L


TASK = CountdownTask((1, 1, 1, 1, 1, 1), 6)


def profile(scores=64, **guards):
    caps = dict.fromkeys(TRACK_A_WORK_AXES, 100000)
    caps.update(legal_action_scores=scores, **guards)
    return core.TrackABudgetProfile(
        "prior_tilt_fixture", "legal_action_scores", TrackAWorkBudget(**caps)
    )


def rehash(record):
    inner = record["search_record"]
    previous = "0" * 64
    for index, e in enumerate(inner["events"]):
        e["index"], e["previous_event_digest"] = index, previous
        e["event_digest"] = sha256_json(
            {k: v for k, v in e.items() if k != "event_digest"}
        )
        previous = e["event_digest"]
    inner["event_count"] = len(inner["events"])
    inner["final_event_digest"] = previous
    for value in (inner, record):
        value["deterministic_digest"] = sha256_json(
            {k: v for k, v in value.items() if k != "deterministic_digest"}
        )
    return canonical_trace_bytes(record)


class PriorTiltTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = {
            m: P.run_prior_tilt_cell(
                TASK,
                spec=P.PriorTiltSpec(m),
                budget_profile=profile(),
                root_seed=41 if m != "puct" else 0,
            )
            for m in P.METHODS
        }

    def replay(self, payload, method="prior-tilt16", **overrides):
        kwargs = dict(
            task=TASK,
            spec=P.PriorTiltSpec(method),
            budget_profile=profile(),
            root_seed=41 if method != "puct" else 0,
            expected_run_identity_digest=self.results[method].record[
                "run_identity_digest"
            ],
        )
        return P.replay_prior_tilt_cell_bytes(payload, **(kwargs | overrides))

    def test_closed_methods_and_no_free_beta(self):
        self.assertEqual(P.METHODS, ("prior-tilt16", "prior-mean-off", "puct"))
        for bad in ("single16", "adaptive", "gumbel-top-k", True, None):
            with self.assertRaises(ValueError):
                P.PriorTiltSpec(bad)
        with self.assertRaises(TypeError):
            P.PriorTiltSpec("prior-tilt16", beta=3)

    def test_input_types_and_no_duplicate_puct_roots(self):
        for bad in (True, -1, 1.0, "1"):
            with self.assertRaises(ValueError):
                P.run_prior_tilt_cell(
                    TASK,
                    spec=P.PriorTiltSpec(P.METHODS[0]),
                    budget_profile=profile(),
                    root_seed=bad,
                )
        with self.assertRaisesRegex(ValueError, "root_seed=0"):
            P.run_prior_tilt_cell(
                TASK,
                spec=P.PriorTiltSpec("puct"),
                budget_profile=profile(),
                root_seed=41,
            )
        with self.assertRaises(TypeError):
            P.run_prior_tilt_cell(
                TASK, spec="prior-tilt16", budget_profile=profile(), root_seed=41
            )

    def test_gumbel_inverse_cdf_and_open_unit_boundary(self):
        for x in (-3.0, -1.0, 0.0, 1.0, 3.0):
            self.assertAlmostEqual(P.gumbels([math.exp(-math.exp(-x))])[0], x)
        for values in ([], [0.0], [1.0], [True], [1], [float("nan")], [float("inf")]):
            with self.assertRaises(ValueError):
                P.gumbels(values)
        self.assertTrue(
            all(math.isfinite(x) for x in P.gumbels([2.0**-53, 1.0 - 2.0**-53]))
        )

    def test_equal_means_recover_prior_logits_not_probability_scores(self):
        lp = [math.log(x) for x in (0.8, 0.15, 0.05)]
        for constant in (0.0, 0.25, 1.0):
            values = P.scores(lp, [constant] * 3, [0.0] * 3, mean_on=True)
            weights = [math.exp(v) for v in values]
            total = sum(weights)
            for actual, expected in zip(weights, (0.8, 0.15, 0.05)):
                self.assertAlmostEqual(actual / total, expected)
        self.assertEqual(P.scores(lp, [0.5] * 3, [0.0] * 3, mean_on=False), lp)

    def test_unit_return_tilt_odds_and_mean_off(self):
        lp = [math.log(0.5)] * 2
        on = P.scores(lp, [0.0, 1.0], [0.0, 0.0], mean_on=True)
        off = P.scores(lp, [0.0, 1.0], [0.0, 0.0], mean_on=False)
        self.assertAlmostEqual(math.exp(on[1] - on[0]), math.e)
        self.assertEqual(off, lp)
        self.assertEqual(core._argmax(on), 1)
        self.assertEqual(core._argmax(off), 0)

    def test_uniform_and_concentrated_many_action_synthetic_distribution(self):
        # Fixed synthetic selector fixture, not Countdown generation/performance.
        rng = random.Random(42)
        for probabilities in ([0.5, 0.5], [0.8] + [0.2 / 63] * 63):
            lp = [math.log(p) for p in probabilities]
            hits = [0] * len(lp)
            for _ in range(8192):
                uniforms = [(rng.getrandbits(52) + 0.5) / 2**52 for _ in lp]
                value = P.scores(lp, [0.0] * len(lp), P.gumbels(uniforms), mean_on=True)
                hits[core._argmax(value)] += 1
            self.assertLess(abs(hits[0] / 8192 - probabilities[0]), 0.025)

    def test_visit_and_m2_do_not_rescale_selection(self):
        session = P._TiltSession(
            spec=P.PriorTiltSpec(P.METHODS[0]),
            task=TASK,
            proposal=P.PROPOSAL,
            budget_profile=profile(),
            exploration_seed=41,
        )
        node = core._SearchNode.create(
            evaluate_track_a_proposal(TASK, TASK.initial_state, P.PROPOSAL)
        )
        noise = [1.0] * len(node.row.actions)
        before = session._selection_values(node, noise, trajectory_index=0)
        for i, item in enumerate(node.posteriors):
            item.visits, item.m2 = i + 99, 7.0
        self.assertEqual(
            before, session._selection_values(node, noise, trajectory_index=1)
        )

    def test_score_input_boundaries(self):
        for means in ([2.0], [-0.1], [float("nan")], [True], []):
            with self.assertRaises(ValueError):
                P.scores([0.0], means, [0.0], mean_on=True)
        with self.assertRaises(ValueError):
            P.scores([0.0], [0.0], [0.0], mean_on=1)

    def test_all_methods_generative_replay_and_null_winner(self):
        for m, r in self.results.items():
            self.assertEqual(self.replay(r.canonical_bytes, m), r.canonical_bytes)
            self.assertIsNone(r.summary["winner"])
            self.assertIsNone(r.summary["scientific_decision"])

    def test_puct_inner_trace_unchanged(self):
        original = L.run_search_value_cell(
            TASK, spec=L.SearchValueSpec("puct"), budget_profile=profile(), root_seed=0
        )
        self.assertEqual(
            self.results["puct"].record["search_record"],
            original.record["search_record"],
        )

    def test_new_identity_and_declared_transport(self):
        on, off = self.results[P.METHODS[0]], self.results[P.METHODS[1]]
        self.assertNotEqual(
            on.record["run_identity_digest"], off.record["run_identity_digest"]
        )
        for method in P.METHODS[:2]:
            r = self.results[method]
            self.assertEqual(r.record["schema_version"], P.SCHEMA)
            self.assertTrue(
                r.summary["search_summary"]["method"][
                    "normal_material_generated_charged_but_unused"
                ]
            )
            for e in r.record["search_record"]["events"]:
                if e["kind"] == "selection_committed":
                    self.assertEqual(
                        e["payload"]["event_schema_version"], P.EVENT_SCHEMA
                    )
                    self.assertFalse(
                        e["payload"]["selection_semantics"][
                            "normal_material_used_in_selection"
                        ]
                    )

    def test_old_policy_cannot_accept_new_identity(self):
        r = self.results[P.METHODS[0]]
        with self.assertRaises(TraceValidationError):
            core.replay_countdown_track_a_search_bytes(
                canonical_trace_bytes(r.record["search_record"]),
                task=TASK,
                proposal=P.PROPOSAL,
                method=L._single16(),
                budget_profile=profile(),
                exploration_seed=L.branch_seed(41, 0),
                expected_run_identity_digest=sha256_json(
                    r.record["search_record"]["run_identity"]
                ),
            )

    def test_rehashed_score_and_metadata_tampering_rejected(self):
        for field, change in (
            ("selected_value", lambda x: x + 0.5),
            ("event_schema_version", lambda x: "other"),
        ):
            r = copy.deepcopy(self.results[P.METHODS[0]].record)
            p = next(
                e["payload"]
                for e in r["search_record"]["events"]
                if e["kind"] == "selection_committed"
            )
            p[field] = change(p[field])
            with self.assertRaises(TraceValidationError):
                self.replay(rehash(r))

    def test_stored_uniform_tampering_rejected_even_after_rehash(self):
        r = copy.deepcopy(self.results[P.METHODS[0]].record)
        p = next(
            e["payload"]
            for e in r["search_record"]["events"]
            if e["kind"] == "perturbation_draw"
        )
        p["uniforms"][0] = 0.25 if p["uniforms"][0] != 0.25 else 0.75
        p["uniform_digest"] = sha256_json(p["uniforms"])
        p["point_digest"] = sha256_json(
            {k: v for k, v in p.items() if k != "point_digest"}
        )
        with self.assertRaises(TraceValidationError):
            self.replay(rehash(r))

    def test_outer_summary_tampering_rejected(self):
        r = copy.deepcopy(self.results[P.METHODS[0]].record)
        r["summary"]["actual_work"]["transitions"] += 1
        with self.assertRaises(TraceValidationError):
            self.replay(rehash(r))

    def test_guard_failure_retained_and_no_unbounded_search(self):
        r = P.run_prior_tilt_cell(
            TASK,
            spec=P.PriorTiltSpec(P.METHODS[0]),
            budget_profile=profile(transitions=1),
            root_seed=41,
        )
        self.assertFalse(r.summary["search_summary"]["budget_valid"])

    def test_terminal_updates_retained_in_both_stochastic_methods(self):
        for method in P.METHODS[:2]:
            updates = [
                u
                for e in self.results[method].record["search_record"]["events"]
                if e["kind"] == "trajectory_backed_up"
                for u in e["payload"]["updates"]
            ]
            self.assertTrue(updates)
            self.assertTrue(
                all(u["after"]["visits"] == u["before"]["visits"] + 1 for u in updates)
            )
            self.assertTrue(any(u["after"]["mean"] > 0 for u in updates))

    def test_fresh_process_outside_repository_replay(self):
        root = Path(__file__).resolve().parents[1]
        source = """import sys
from qmc_bmgs.substrate.trace import strict_json_loads
from qmc_bmgs.benchmarks.countdown import CountdownTask
from qmc_bmgs.substrate.budget import TrackAWorkBudget
from qmc_bmgs.substrate.countdown_search import TrackABudgetProfile
from qmc_bmgs_next.prior_tilt import PriorTiltSpec,replay_prior_tilt_cell_bytes
raw=sys.stdin.buffer.read(); r=strict_json_loads(raw); i=r['run_identity']
p=TrackABudgetProfile('prior_tilt_fixture','legal_action_scores',TrackAWorkBudget(**i['search_run_identity']['work_limits']))
sys.stdout.buffer.write(replay_prior_tilt_cell_bytes(raw,task=CountdownTask((1,1,1,1,1,1),6),spec=PriorTiltSpec('prior-tilt16'),budget_profile=p,root_seed=41,expected_run_identity_digest=r['run_identity_digest']))
"""
        result = subprocess.run(
            [sys.executable, "-P", "-B", "-c", source],
            cwd="/tmp",
            env=dict(os.environ, PYTHONPATH=str(root / "src")),
            input=self.results[P.METHODS[0]].canonical_bytes,
            capture_output=True,
            check=True,
        )
        self.assertEqual(result.stdout, self.results[P.METHODS[0]].canonical_bytes)


if __name__ == "__main__":
    unittest.main()
