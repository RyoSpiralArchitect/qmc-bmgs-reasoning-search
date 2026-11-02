"""Outcome-independent boundaries and old public fixtures, not new study rows."""

import copy
import math
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from qmc_bmgs.benchmarks.countdown import CountdownTask
from qmc_bmgs.substrate import countdown_search as core
from qmc_bmgs.substrate import perturbations
from qmc_bmgs.substrate.budget import TRACK_A_WORK_AXES, TrackAWorkBudget
from qmc_bmgs.substrate.proposals import evaluate_track_a_proposal
from qmc_bmgs.substrate.trace import (
    TraceValidationError,
    canonical_trace_bytes,
    sha256_json,
)
from qmc_bmgs_next import puct_qmc_unvisited as H
from qmc_bmgs_next import puct_qmc_unvisited_study as S


TASK = CountdownTask((1, 1, 1, 1, 1, 1), 6)


def profile(scores=128, **guards):
    caps = dict.fromkeys(TRACK_A_WORK_AXES, 100000)
    caps.update(legal_action_scores=scores, **guards)
    return core.TrackABudgetProfile(
        "unvisited_fixture", "legal_action_scores", TrackAWorkBudget(**caps)
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


class SelectorBoundaryTests(unittest.TestCase):
    def test_spatial_gate_closed_types_and_no_depth_tuning(self):
        for t in (0, 1, 2, 50):
            for depth in range(5):
                self.assertIs(H.perturbation_active(t, depth), t > 0 and depth == 0)
        for t, depth in ((True, 0), (1, False), (-1, 0), (1, -1), (1.0, 0)):
            with self.assertRaises(ValueError):
                H.perturbation_active(t, depth)
        with self.assertRaises(TypeError):
            H.PuctQmcUnvisitedSpec("puct-qmc", maximum_depth=1)

    def test_deep_scores_are_fixed_puct_even_after_anchor(self):
        s = H._UnvisitedSession(
            spec=H.PuctQmcUnvisitedSpec("puct-qmc"),
            task=TASK,
            proposal=H.PROPOSAL,
            budget_profile=profile(),
            exploration_seed=41,
        )
        state = TASK.transition(
            TASK.initial_state, TASK.legal_actions(TASK.initial_state)[0]
        )
        node = core._SearchNode.create(
            evaluate_track_a_proposal(TASK, state, H.PROPOSAL)
        )
        for i, p in enumerate(node.posteriors):
            p.visits, p.mean, p.m2 = i, 0.25, 5.0
        expected = H.scores(
            node.row.prior_logp,
            [p.mean for p in node.posteriors],
            [p.visits for p in node.posteriors],
        )
        self.assertEqual(s._selection_values(node, None, trajectory_index=9), expected)
        with self.assertRaises(ValueError):
            s._selection_values(node, [0.5] * len(node.posteriors), trajectory_index=9)

    def test_nonroot_transport_restored_on_exception(self):
        s = H._UnvisitedSession(
            spec=H.PuctQmcUnvisitedSpec("puct-iid"),
            task=TASK,
            proposal=H.PROPOSAL,
            budget_profile=profile(),
            exploration_seed=41,
        )
        action = TASK.legal_actions(TASK.initial_state)[0]
        child = TASK.transition(TASK.initial_state, action)
        path = core._Path(states=(TASK.initial_state, child), actions=(action,))
        original = s.method

        def fail(_session, *_args, **_kwargs):
            self.assertEqual(_session.method, core.TrackAMethodSpec.puct())
            raise RuntimeError("deep fixture")

        with patch.object(core._SearchSession, "_ordinary_step", fail):
            with self.assertRaises(RuntimeError):
                s._ordinary_step(path, trajectory_index=3)
        self.assertIs(s.method, original)

    def test_closed_methods_no_sweep_knob(self):
        for bad in (True, "sobol", "adaptive", "thompson", None):
            with self.assertRaises(ValueError):
                H.PuctQmcUnvisitedSpec(bad)
        with self.assertRaises(TypeError):
            H.PuctQmcUnvisitedSpec("puct-qmc", coefficient=0.7)
        self.assertEqual(
            [H.PuctQmcUnvisitedSpec(m).source for m in H.METHODS],
            ["sobol", "iid", "none"],
        )

    def test_reject_bad_components_and_uniform_boundary(self):
        valid = dict(log_prior=[0.0], means=[0.0], visits=[0], uniforms=[0.5])
        for field, values in (
            ("log_prior", [0]),
            ("log_prior", [0.1]),
            ("log_prior", [float("nan")]),
            ("means", [True]),
            ("means", [1.1]),
            ("means", [-0.1]),
            ("visits", [True]),
            ("visits", [-1]),
            ("visits", [0.0]),
            ("uniforms", []),
            ("uniforms", [0.0]),
            ("uniforms", [1.0]),
            ("uniforms", [True]),
            ("uniforms", [float("inf")]),
        ):
            with (
                self.subTest(field=field, values=values),
                self.assertRaises(ValueError),
            ):
                H.scores(**(valid | {field: values}))

    def test_neutral_uniform_exactly_recovers_puct_and_canonical_ties(self):
        lp, means, visits = [math.log(0.5)] * 2, [0.0, 0.0], [0, 0]
        self.assertEqual(
            H.scores(lp, means, visits), H.scores(lp, means, visits, [0.5, 0.5])
        )
        self.assertEqual(core._argmax(H.scores(lp, means, visits, [0.5, 0.5])), 0)
        self.assertEqual(core._argmax(H.scores(lp, means, visits, [0.25, 0.75])), 1)

    def test_only_bonus_is_multiplied_with_bounded_positive_factor(self):
        lp, means, visits = [math.log(0.2), math.log(0.8)], [0.7, 0.1], [0, 17]
        base = H.scores(lp, means, visits)
        u = [2.0**-52, 1.0 - 2.0**-52]
        observed = H.scores(lp, means, visits, u)
        for m, b, x, z, n in zip(means, base, observed, u, visits):
            self.assertAlmostEqual(x, m + (b - m) * (0.5 + z if n == 0 else 1.0))
            self.assertGreaterEqual(x, m + 0.5 * (b - m))
            self.assertLessEqual(x, m + 1.5 * (b - m))

    def test_visits_retained_m2_unused_and_first_anchor_contract(self):
        session = H._UnvisitedSession(
            spec=H.PuctQmcUnvisitedSpec("puct-qmc"),
            task=TASK,
            proposal=H.PROPOSAL,
            budget_profile=profile(),
            exploration_seed=41,
        )
        node = core._SearchNode.create(
            evaluate_track_a_proposal(TASK, TASK.initial_state, H.PROPOSAL)
        )
        n = len(node.posteriors)
        base = session._selection_values(node, None, trajectory_index=0)
        for p in node.posteriors:
            p.m2 = 100.0
        self.assertEqual(
            base, session._selection_values(node, [0.5] * n, trajectory_index=1)
        )
        node.posteriors[0].visits = 7
        self.assertNotEqual(
            base, session._selection_values(node, None, trajectory_index=0)
        )
        for t, material in ((0, [0.5] * n), (1, None), (True, None), (-1, None)):
            with self.assertRaises(ValueError):
                session._selection_values(node, material, trajectory_index=t)

    def test_anchor_transport_restored_on_exception(self):
        s = H._UnvisitedSession(
            spec=H.PuctQmcUnvisitedSpec("puct-iid"),
            task=TASK,
            proposal=H.PROPOSAL,
            budget_profile=profile(),
            exploration_seed=41,
        )
        original = s.method
        with patch.object(
            core._SearchSession, "_ordinary_step", side_effect=RuntimeError("fixture")
        ):
            with self.assertRaises(RuntimeError):
                s._ordinary_step(
                    core._Path(states=(TASK.initial_state,)), trajectory_index=0
                )
        self.assertIs(s.method, original)


class UnvisitedMaskTests(unittest.TestCase):
    def test_only_zero_visit_actions_receive_nonunit_multiplier(self):
        lp = [math.log(0.25)] * 4
        means, visits = [0.0, 0.25, 1.0, 0.0], [0, 2, 1, 0]
        base = H.scores(lp, means, visits)
        got = H.scores(lp, means, visits, [0.1, 0.2, 0.9, 0.8])
        self.assertEqual(got[1:3], base[1:3])
        self.assertAlmostEqual(got[0], base[0] * 0.6)
        self.assertAlmostEqual(got[3], base[3] * 1.3)
        self.assertEqual(got, H.scores(lp, means, visits, [0.1, 0.99, 0.01, 0.8]))

    def test_all_visited_scores_fixed_but_uniform_validation_still_required(self):
        lp, means, visits = [math.log(0.5)] * 2, [0.25, 0.75], [1, 5]
        base = H.scores(lp, means, visits)
        self.assertEqual(H.scores(lp, means, visits, [0.01, 0.99]), base)
        for u in ([0.0, 0.9], [0.1, 1.0], [0.1], [True, 0.5]):
            with self.assertRaises(ValueError):
                H.scores(lp, means, visits, u)

    def test_single_action_zero_to_one_visit_changes_mask_not_q(self):
        self.assertEqual(H.scores([0.0], [0.7], [0], [0.25]), [1.45])
        base = H.scores([0.0], [0.7], [1])
        self.assertEqual(H.scores([0.0], [0.7], [1], [0.25]), base)
        self.assertEqual(H.scores([0.0], [0.7], [1], [0.75]), base)

    def test_no_rank_gap_or_visit_threshold_knob(self):
        for k in ("rank", "gap_threshold", "max_visits", "mask_threshold"):
            with self.assertRaises(TypeError):
                H.PuctQmcUnvisitedSpec("puct-qmc", **{k: 3})
        method = H.PuctQmcUnvisitedSpec("puct-qmc").method_payload()
        self.assertEqual(
            method["action_bonus_mask"], "pre_selection_edge_visits_equal_zero"
        )
        self.assertEqual(method["visited_action_bonus_multiplier"], 1.0)
        self.assertTrue(method["all_visited_root_still_generates_full_point"])

    def test_all_visited_root_transaction_still_draws_charges_and_advances(self):
        for method in H.METHODS[:2]:
            session = H._UnvisitedSession(
                spec=H.PuctQmcUnvisitedSpec(method),
                task=TASK,
                proposal=H.PROPOSAL,
                budget_profile=profile(),
                exploration_seed=41,
            )
            node = core._SearchNode.create(
                evaluate_track_a_proposal(TASK, TASK.initial_state, H.PROPOSAL)
            )
            for posterior in node.posteriors:
                posterior.visits, posterior.mean = 1, 0.25
            session.nodes[TASK.initial_state] = node
            base = H.scores(
                node.row.prior_logp,
                [0.25] * len(node.posteriors),
                [1] * len(node.posteriors),
            )
            with self.assertRaises(ValueError):
                session._selection_values(node, None, trajectory_index=1)
            for trajectory in (1, 2):
                self.assertIsNotNone(
                    session._ordinary_step(
                        core._Path(states=(TASK.initial_state,)),
                        trajectory_index=trajectory,
                    )
                )
            points = [
                e["payload"]
                for e in session.trace.events
                if e["kind"] == "perturbation_draw"
            ]
            selections = [
                e for e in session.trace.events if e["kind"] == "selection_committed"
            ]
            self.assertEqual([p["node_visit_index"] for p in points], [0, 1])
            self.assertEqual(len(selections), 2)
            for point, event in zip(points, selections):
                self.assertEqual(len(point["uniforms"]), len(node.posteriors))
                self.assertEqual(len(point["normals"]), len(node.posteriors))
                self.assertEqual(event["payload"]["selection_values"], base)
                self.assertEqual(
                    event["charge"]["delta"]["generated_perturbation_coordinates"],
                    len(node.posteriors),
                )


class RootTraceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = {
            m: H.run_puct_qmc_unvisited_cell(
                TASK,
                spec=H.PuctQmcUnvisitedSpec(m),
                budget_profile=profile(),
                root_seed=41 if m != "puct" else 0,
            )
            for m in H.METHODS
        }

    def replay(self, payload, method="puct-qmc", **overrides):
        kwargs = dict(
            task=TASK,
            spec=H.PuctQmcUnvisitedSpec(method),
            budget_profile=profile(),
            root_seed=41 if method != "puct" else 0,
            expected_run_identity_digest=self.results[method].record[
                "run_identity_digest"
            ],
        )
        return H.replay_puct_qmc_unvisited_cell_bytes(payload, **(kwargs | overrides))

    def test_root_alias_rejection_and_deterministic_identity(self):
        for bad in (True, -1, 1.0, "1"):
            with self.assertRaises(ValueError):
                H.run_puct_qmc_unvisited_cell(
                    TASK,
                    spec=H.PuctQmcUnvisitedSpec("puct-qmc"),
                    budget_profile=profile(),
                    root_seed=bad,
                )
        with self.assertRaises(ValueError):
            H.run_puct_qmc_unvisited_cell(
                TASK,
                spec=H.PuctQmcUnvisitedSpec("puct"),
                budget_profile=profile(),
                root_seed=41,
            )

    def test_all_methods_replay_and_null_winner(self):
        for method, r in self.results.items():
            self.assertEqual(self.replay(r.canonical_bytes, method), r.canonical_bytes)
            self.assertIsNone(r.summary["winner"])
            self.assertIsNone(r.summary["scientific_decision"])

    def test_baseline_inner_bytes_identical_to_frozen_puct(self):
        fixed = core.run_countdown_track_a_search(
            task=TASK,
            proposal=H.PROPOSAL,
            method=core.TrackAMethodSpec.puct(),
            budget_profile=profile(),
            exploration_seed=0,
        )
        self.assertEqual(
            canonical_trace_bytes(self.results["puct"].record["search_record"]),
            fixed.canonical_bytes,
        )

    def test_fixed_first_trajectory_all_arms_without_draw_or_charge(self):
        anchor = S.anchor_projection(self.results["puct"].record)
        for m in H.METHODS[:2]:
            r = self.results[m].record
            self.assertEqual(S.anchor_projection(r), anchor)
            before_terminal = True
            for e in r["search_record"]["events"]:
                if e["kind"] == "terminal_verified":
                    before_terminal = False
                if before_terminal:
                    self.assertNotIn(
                        e["kind"], ("perturbation_draw", "node_materialized")
                    )
                    if e["charge"]:
                        self.assertEqual(
                            e["charge"]["delta"]["generated_perturbation_coordinates"],
                            0,
                        )
            points = [
                e["payload"]
                for e in r["search_record"]["events"]
                if e["kind"] == "perturbation_draw"
            ]
            self.assertTrue(points)
            self.assertEqual(points[0]["node_visit_index"], 0)

    def test_all_seven_work_charges_and_unused_normals_retained(self):
        for m in H.METHODS:
            record = self.results[m].record
            metrics = S.event_metrics(record)
            self.assertEqual(set(metrics["actual_work"]), set(TRACK_A_WORK_AXES))
            selections = [
                e["payload"]
                for e in record["search_record"]["events"]
                if e["kind"] == "selection_committed"
            ]
            expected = sum(
                len(p["scored_action_indices"])
                for p in selections
                if p["point_digest"] is not None
            )
            self.assertEqual(
                metrics["actual_work"]["generated_perturbation_coordinates"], expected
            )
            for e in record["search_record"]["events"]:
                if e["kind"] == "perturbation_draw":
                    self.assertEqual(
                        len(e["payload"]["uniforms"]), len(e["payload"]["normals"])
                    )
            S.choice_material(record)

    def test_only_root_points_and_contiguous_actual_indexes(self):
        for method in H.METHODS[:2]:
            events = self.results[method].record["search_record"]["events"]
            points = [e["payload"] for e in events if e["kind"] == "perturbation_draw"]
            selections = [
                e["payload"] for e in events if e["kind"] == "selection_committed"
            ]
            active = [
                p for p in selections if p["trajectory_index"] > 0 and p["depth"] == 0
            ]
            self.assertTrue(active)
            self.assertEqual(len(points), len(active))
            self.assertEqual(
                [p["node_visit_index"] for p in points], list(range(len(points)))
            )
            self.assertEqual(len({p["node_digest"] for p in points}), 1)
            for p in selections:
                enabled = p["trajectory_index"] > 0 and p["depth"] == 0
                self.assertEqual(p["point_digest"] is not None, enabled)
                self.assertEqual(
                    p["selection_semantics"],
                    H._semantics(p["trajectory_index"], p["depth"]),
                )
                if enabled:
                    self.assertEqual(p["state"], list(TASK.initial_state))

    def test_no_material_planning_below_root(self):
        original = perturbations.LazyNormalSource.plan_draw
        calls = []

        def observe(source, *, task, state, actions):
            self.assertEqual(state, task.initial_state)
            calls.append(state)
            return original(source, task=task, state=state, actions=actions)

        with patch.object(perturbations.LazyNormalSource, "plan_draw", observe):
            result = H.run_puct_qmc_unvisited_cell(
                TASK,
                spec=H.PuctQmcUnvisitedSpec("puct-qmc"),
                budget_profile=profile(),
                root_seed=41,
            )
        self.assertTrue(calls)
        self.assertEqual(
            result.canonical_bytes, self.results["puct-qmc"].canonical_bytes
        )

    def test_old_all_depth_hybrid_identity_is_not_accepted(self):
        from qmc_bmgs_next import puct_qmc_hybrid as previous

        identity, _ = previous._cell_inputs(
            TASK, previous.PuctQmcHybridSpec("puct-qmc"), profile(), 41
        )
        current = self.results["puct-qmc"].record["run_identity"]
        self.assertNotEqual(identity, current)
        self.assertNotEqual(
            identity["search_run_identity"]["configuration_id"],
            current["search_run_identity"]["configuration_id"],
        )
        with self.assertRaises(TraceValidationError):
            self.replay(
                self.results["puct-qmc"].canonical_bytes,
                expected_run_identity_digest=sha256_json(identity),
            )

    def test_preceding_root_only_identity_is_not_accepted(self):
        from qmc_bmgs_next import puct_qmc_root as previous

        identity, _ = previous._cell_inputs(
            TASK, previous.PuctQmcRootSpec("puct-qmc"), profile(), 41
        )
        current = self.results["puct-qmc"].record["run_identity"]
        self.assertNotEqual(
            identity["search_run_identity"]["configuration_id"],
            current["search_run_identity"]["configuration_id"],
        )
        with self.assertRaises(TraceValidationError):
            self.replay(
                self.results["puct-qmc"].canonical_bytes,
                expected_run_identity_digest=sha256_json(identity),
            )

    def test_saved_history_mask_and_fixed_visited_scores(self):
        for method in H.METHODS:
            choices = S.choice_material(self.results[method].record)
            active = [r for r in choices if r["perturbation_active"]]
            self.assertEqual(bool(active), method != "puct")
            if active:
                self.assertTrue(
                    any(any(n > 0 for n in r["current_visits"]) for r in active)
                )
            for row in choices:
                mask = [
                    row["perturbation_active"] and n == 0 for n in row["current_visits"]
                ]
                self.assertEqual(row["action_bonus_mask"], mask)
                for i, used in enumerate(mask):
                    if not used:
                        self.assertEqual(row["bonus_multipliers"][i], 1.0)
                        self.assertEqual(
                            row["selected_scores"][i],
                            row["current_means"][i] + row["unperturbed_bonus"][i],
                        )

    def test_unused_visited_uniform_is_retained_and_replay_bound(self):
        record = copy.deepcopy(self.results["puct-qmc"].record)
        choices = S.choice_material(record)
        selections = [
            e["payload"]
            for e in record["search_record"]["events"]
            if e["kind"] == "selection_committed"
        ]
        row, selection = next(
            (r, s)
            for r, s in zip(choices, selections)
            if r["perturbation_active"] and any(n > 0 for n in r["current_visits"])
        )
        index = next(i for i, n in enumerate(row["current_visits"]) if n > 0)
        point = next(
            e["payload"]
            for e in record["search_record"]["events"]
            if e["kind"] == "perturbation_draw"
            and e["payload"]["point_digest"] == selection["point_digest"]
        )
        old = point["uniforms"][index]
        point["uniforms"][index] = 1.0 - old if old != 0.5 else 0.25
        with self.assertRaises(TraceValidationError):
            self.replay(rehash(record))

    def test_rehashed_mask_semantics_tamper_rejected(self):
        record = copy.deepcopy(self.results["puct-qmc"].record)
        selection = next(
            e["payload"]
            for e in record["search_record"]["events"]
            if e["kind"] == "selection_committed"
            and e["payload"]["point_digest"] is not None
        )
        selection["selection_semantics"]["action_bonus_mask"] = "all_actions"
        with self.assertRaises(TraceValidationError):
            self.replay(rehash(record))

    def test_rehashed_nonroot_phase_and_depth_tamper_rejected(self):
        for field, value in (("depth", 0), ("point_digest", "f" * 64)):
            record = copy.deepcopy(self.results["puct-qmc"].record)
            p = next(
                e["payload"]
                for e in record["search_record"]["events"]
                if e["kind"] == "selection_committed"
                and e["payload"]["trajectory_index"] > 0
                and e["payload"]["depth"] > 0
            )
            p[field] = value
            with self.assertRaises(TraceValidationError):
                self.replay(rehash(record))

    def test_binary_exact_and_miss_backups_no_near_miss_reward(self):
        for target, expected in ((6, True), (999, False)):
            for m in H.METHODS:
                record = H.run_puct_qmc_unvisited_cell(
                    CountdownTask((1, 1, 1, 1, 1, 1), target),
                    spec=H.PuctQmcUnvisitedSpec(m),
                    budget_profile=profile(),
                    root_seed=41 if m != "puct" else 0,
                ).record
                seen = []
                for e in record["search_record"]["events"]:
                    if e["kind"] == "terminal_verified":
                        value = float(e["payload"]["verification"]["success"])
                    if e["kind"] == "trajectory_backed_up":
                        self.assertEqual(e["payload"]["terminal_value"], value)
                        seen.append(value)
                        self.assertTrue(
                            all(
                                u["after"]["visits"] == u["before"]["visits"] + 1
                                for u in e["payload"]["updates"]
                            )
                        )
                self.assertTrue(seen)
                self.assertEqual(1.0 in seen, expected)

    def test_small_budget_anchor_only_and_guard_failure_retained(self):
        for m in H.METHODS[:2]:
            r = H.run_puct_qmc_unvisited_cell(
                TASK,
                spec=H.PuctQmcUnvisitedSpec(m),
                budget_profile=profile(1),
                root_seed=41,
            )
            self.assertEqual(
                r.summary["actual_work"]["generated_perturbation_coordinates"], 0
            )
            r = H.run_puct_qmc_unvisited_cell(
                TASK,
                spec=H.PuctQmcUnvisitedSpec(m),
                budget_profile=profile(transitions=1),
                root_seed=41,
            )
            self.assertFalse(r.summary["search_summary"]["budget_valid"])

    def test_rehashed_score_metadata_material_and_backup_tampering_rejected(self):
        for kind, field, value in (
            ("selection_committed", "selected_value", 99.0),
            ("selection_committed", "event_schema_version", "wrong"),
            ("perturbation_draw", "uniforms", [0.5]),
            ("trajectory_backed_up", "terminal_value", 0.25),
        ):
            r = copy.deepcopy(self.results["puct-qmc"].record)
            p = next(
                e["payload"] for e in r["search_record"]["events"] if e["kind"] == kind
            )
            p[field] = value
            with self.assertRaises(TraceValidationError):
                self.replay(rehash(r))

    def test_source_seed_and_outer_summary_mismatch_rejected(self):
        r = self.results["puct-qmc"]
        for overrides in (
            dict(spec=H.PuctQmcUnvisitedSpec("puct-iid")),
            dict(root_seed=42),
        ):
            with self.assertRaises(TraceValidationError):
                self.replay(r.canonical_bytes, **overrides)
        bad = copy.deepcopy(r.record)
        bad["summary"]["actual_work"]["transitions"] += 1
        with self.assertRaises(TraceValidationError):
            self.replay(rehash(bad))

    def test_only_selected_source_generates_draws(self):
        for method, forbidden in (
            ("puct-qmc", "_iid_uniforms"),
            ("puct-iid", "_sobol_uniforms"),
        ):
            with patch.object(
                perturbations,
                forbidden,
                side_effect=AssertionError("unselected source"),
            ):
                result = H.run_puct_qmc_unvisited_cell(
                    TASK,
                    spec=H.PuctQmcUnvisitedSpec(method),
                    budget_profile=profile(),
                    root_seed=41,
                )
            self.assertEqual(
                result.canonical_bytes, self.results[method].canonical_bytes
            )

    def test_fresh_process_outside_checkout_replay(self):
        root = Path(__file__).resolve().parents[1]
        source = """import sys
from qmc_bmgs.substrate.trace import strict_json_loads
from qmc_bmgs.benchmarks.countdown import CountdownTask
from qmc_bmgs.substrate.budget import TrackAWorkBudget
from qmc_bmgs.substrate.countdown_search import TrackABudgetProfile
from qmc_bmgs_next.puct_qmc_unvisited import PuctQmcUnvisitedSpec, replay_puct_qmc_unvisited_cell_bytes
raw=sys.stdin.buffer.read(); r=strict_json_loads(raw); i=r['run_identity']
p=TrackABudgetProfile('unvisited_fixture','legal_action_scores',TrackAWorkBudget(**i['search_run_identity']['work_limits']))
sys.stdout.buffer.write(replay_puct_qmc_unvisited_cell_bytes(raw,task=CountdownTask((1,1,1,1,1,1),6),spec=PuctQmcUnvisitedSpec('puct-qmc'),budget_profile=p,root_seed=41,expected_run_identity_digest=r['run_identity_digest']))
"""
        child = subprocess.run(
            [sys.executable, "-P", "-B", "-c", source],
            cwd="/tmp",
            env=dict(os.environ, PYTHONPATH=str(root / "src")),
            input=self.results["puct-qmc"].canonical_bytes,
            capture_output=True,
            check=True,
        )
        self.assertEqual(child.stdout, self.results["puct-qmc"].canonical_bytes)


if __name__ == "__main__":
    unittest.main()
