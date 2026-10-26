from __future__ import annotations

import copy
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from qmc_bmgs.benchmarks.countdown import CountdownTask
from qmc_bmgs.substrate import countdown_search as core
from qmc_bmgs.substrate.budget import TRACK_A_WORK_AXES, TrackAWorkBudget
from qmc_bmgs.substrate.proposals import evaluate_track_a_proposal
from qmc_bmgs.substrate.trace import (
    TraceValidationError,
    canonical_trace_bytes,
    sha256_json,
    validate_trace_bytes,
)
from qmc_bmgs_next import search_value as S


# Previously used implementation fixture, not a new development cohort.
TASK = CountdownTask((1, 1, 1, 1, 1, 1), 6)


def profile(scores=64, **guards):
    caps = {axis: 100_000 for axis in TRACK_A_WORK_AXES}
    caps.update(legal_action_scores=scores, **guards)
    return core.TrackABudgetProfile(
        "search_value_fixture", "legal_action_scores", TrackAWorkBudget(**caps)
    )


def rehash_inner(record):
    previous = "0" * 64
    for index, event in enumerate(record["events"]):
        event["index"] = index
        event["previous_event_digest"] = previous
        event["event_digest"] = sha256_json(
            {k: v for k, v in event.items() if k != "event_digest"}
        )
        previous = event["event_digest"]
    record["event_count"] = len(record["events"])
    record["final_event_digest"] = previous
    record["deterministic_digest"] = sha256_json(
        {k: v for k, v in record.items() if k != "deterministic_digest"}
    )


def redigest(record):
    record["deterministic_digest"] = sha256_json(
        {k: v for k, v in record.items() if k != "deterministic_digest"}
    )
    return canonical_trace_bytes(record)


def events(result, kind):
    return [e for e in result.record["search_record"]["events"] if e["kind"] == kind]


class SearchValueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = {
            method: S.run_search_value_cell(
                TASK,
                spec=S.SearchValueSpec(method),
                budget_profile=profile(),
                root_seed=41 if S.SearchValueSpec(method).stochastic else 0,
            )
            for method in S.METHODS
        }

    def replay(self, payload, method="selection-mean-off", **overrides):
        kwargs = dict(
            task=TASK,
            spec=S.SearchValueSpec(method),
            budget_profile=profile(),
            root_seed=41 if S.SearchValueSpec(method).stochastic else 0,
            expected_run_identity_digest=self.results[method].record[
                "run_identity_digest"
            ],
        )
        return S.replay_search_value_cell_bytes(payload, **(kwargs | overrides))

    def sessions(self):
        kwargs = dict(
            task=TASK,
            proposal=S.PROPOSAL,
            budget_profile=profile(),
            exploration_seed=41,
        )
        return (
            core._SearchSession(
                method=S.SearchValueSpec("single16").base_method(), **kwargs
            ),
            S._MeanOffSession(**kwargs),
        )

    def test_closed_methods(self):
        for bad in ("adaptive", "weighted16", "mean-off", "PUCT", None, True, []):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                S.SearchValueSpec(bad)
        self.assertEqual(len(S.METHODS), 5)

    def test_bad_inputs_fail_before_search(self):
        with patch.object(core, "run_countdown_track_a_search") as run:
            for bad in (-1, True, 1.0, "0"):
                with self.subTest(bad=bad), self.assertRaises(ValueError):
                    S.run_search_value_cell(
                        TASK,
                        spec=S.SearchValueSpec("single16"),
                        budget_profile=profile(),
                        root_seed=bad,
                    )
            for method in ("greedy", "beam2", "puct"):
                with (
                    self.subTest(method=method),
                    self.assertRaisesRegex(ValueError, "root_seed=0"),
                ):
                    S.run_search_value_cell(
                        TASK,
                        spec=S.SearchValueSpec(method),
                        budget_profile=profile(),
                        root_seed=1,
                    )
            with self.assertRaises(TypeError):
                S.run_search_value_cell(
                    TASK, spec="single16", budget_profile=profile(), root_seed=0
                )
            run.assert_not_called()

    def test_four_controls_have_byte_identical_legacy_inner_records(self):
        for method in ("single16", "greedy", "beam2", "puct"):
            spec = S.SearchValueSpec(method)
            direct = core.run_countdown_track_a_search(
                TASK,
                method=spec.base_method(),
                proposal=S.PROPOSAL,
                budget_profile=profile(),
                exploration_seed=S.branch_seed(41, 0) if spec.stochastic else 0,
            )
            with self.subTest(method=method):
                self.assertEqual(
                    canonical_trace_bytes(self.results[method].record["search_record"]),
                    direct.canonical_bytes,
                )

    def test_all_five_methods_replay_and_have_no_scientific_winner(self):
        for method, result in self.results.items():
            with self.subTest(method=method):
                self.assertEqual(
                    self.replay(result.canonical_bytes, method), result.canonical_bytes
                )
                self.assertIsNone(result.summary["winner"])
                self.assertIsNone(result.summary["scientific_decision"])

    def test_mean_off_identity_and_event_declarations_are_distinct(self):
        off = self.results["selection-mean-off"]
        on = self.results["single16"]
        self.assertNotEqual(
            off.record["run_identity_digest"], on.record["run_identity_digest"]
        )
        inner = off.record["search_record"]
        self.assertEqual(inner["run_identity"]["method_id"], S.MEAN_OFF_SCHEMA)
        self.assertEqual(off.summary["search_summary"]["method"], S._mean_off_payload())
        for event in events(off, "selection_committed"):
            p = event["payload"]
            self.assertEqual(p["method"], S._mean_off_payload())
            self.assertEqual(
                p["selection_semantics"]["selection_mean_coefficient"], 0.0
            )
            self.assertEqual(p["event_schema_version"], S.MEAN_OFF_EVENT)
        with self.assertRaises(TraceValidationError):
            core.replay_countdown_track_a_search_bytes(
                canonical_trace_bytes(inner),
                task=TASK,
                proposal=S.PROPOSAL,
                method=S.SearchValueSpec("single16").base_method(),
                budget_profile=profile(),
                exploration_seed=S.branch_seed(41, 0),
                expected_run_identity_digest=sha256_json(inner["run_identity"]),
            )

    def test_zero_mean_scores_equal_without_mutating_posteriors(self):
        on, off = self.sessions()
        row = evaluate_track_a_proposal(TASK, TASK.initial_state, S.PROPOSAL)
        node = core._SearchNode.create(row)
        for i, item in enumerate(node.posteriors):
            item.visits = i
            item.m2 = i + 0.5
        before = copy.deepcopy(node.to_dict())
        normals = [float(i - 1) for i in range(len(row.actions))]
        self.assertEqual(
            on._selection_values(node, normals, trajectory_index=0),
            off._selection_values(node, normals, trajectory_index=0),
        )
        self.assertEqual(node.to_dict(), before)

    def test_constructed_mean_changes_only_the_on_choice(self):
        on, off = self.sessions()
        row = evaluate_track_a_proposal(TASK, TASK.initial_state, S.PROPOSAL)
        node = core._SearchNode.create(row)
        normals = [0.0] * len(row.actions)
        before = off._selection_values(node, normals, trajectory_index=0)
        alternative = (core._argmax(before) + 1) % len(before)
        node.posteriors[alternative].mean = 100.0
        node.posteriors[alternative].m2 = 5.0
        self.assertEqual(
            off._selection_values(node, normals, trajectory_index=0), before
        )
        self.assertEqual(
            core._argmax(on._selection_values(node, normals, trajectory_index=0)),
            alternative,
        )
        self.assertNotEqual(core._argmax(before), alternative)

    def test_mean_off_keeps_visit_dependent_noise(self):
        _, off = self.sessions()
        node = core._SearchNode.create(
            evaluate_track_a_proposal(TASK, TASK.initial_state, S.PROPOSAL)
        )
        normals = [1.0] * len(node.row.actions)
        before = off._selection_values(node, normals, trajectory_index=1)
        node.posteriors[0].visits = 99
        after = off._selection_values(node, normals, trajectory_index=1)
        self.assertLess(after[0], before[0])
        self.assertEqual(after[1:], before[1:])

    def test_mean_is_omitted_before_rounding_not_subtracted_afterward(self):
        on, off = self.sessions()
        node = core._SearchNode.create(
            evaluate_track_a_proposal(TASK, TASK.initial_state, S.PROPOSAL)
        )
        normals = [0.0] * len(node.row.actions)
        expected = off._selection_values(node, normals, trajectory_index=0)
        for item in node.posteriors:
            item.mean = 1e20
        self.assertEqual(
            off._selection_values(node, normals, trajectory_index=0), expected
        )
        rounded_subtraction = [
            value - item.mean
            for value, item in zip(
                on._selection_values(node, normals, trajectory_index=0), node.posteriors
            )
        ]
        self.assertNotEqual(rounded_subtraction, expected)

    def test_nontrivial_existing_fixture_replays_with_full_diagnostics(self):
        task = CountdownTask((1, 2, 3, 4, 5, 6), 720)
        for method in ("single16", "selection-mean-off"):
            kwargs = dict(
                task=task,
                spec=S.SearchValueSpec(method),
                budget_profile=profile(256),
                root_seed=41,
            )
            result = S.run_search_value_cell(**kwargs)
            with self.subTest(method=method):
                self.assertEqual(
                    S.replay_search_value_cell_bytes(
                        result.canonical_bytes,
                        **kwargs,
                        expected_run_identity_digest=result.record[
                            "run_identity_digest"
                        ],
                    ),
                    result.canonical_bytes,
                )
                self.assertGreater(
                    result.summary["proposal_work"]["materialized_rows"], 1
                )
                self.assertTrue(result.summary["search_summary"]["budget_valid"])

    def test_mean_off_uses_original_backup_functions_and_scale16(self):
        self.assertIs(
            S._MeanOffSession._preview_backup, core._SearchSession._preview_backup
        )
        self.assertIs(
            S._MeanOffSession._commit_backup, core._SearchSession._commit_backup
        )
        backups = events(self.results["selection-mean-off"], "trajectory_backed_up")
        self.assertTrue(backups)
        for event in backups:
            p = event["payload"]
            self.assertEqual(p["terminal_value_scale"], 16)
            self.assertGreater(p["terminal_value"], 0.0)
            for update in p["updates"]:
                before, after = update["before"], update["after"]
                count = before["visits"] + 1
                delta = p["terminal_value"] - before["mean"]
                mean = before["mean"] + delta / count
                self.assertEqual(
                    after,
                    dict(
                        visits=count,
                        mean=mean,
                        m2=before["m2"] + delta * (p["terminal_value"] - mean),
                    ),
                )

    def test_keyed_material_agrees_only_at_shared_coordinates(self):
        def material(result):
            return {
                (e["payload"]["node_digest"], e["payload"]["node_visit_index"]): e[
                    "payload"
                ]
                for e in events(result, "perturbation_draw")
            }

        on, off = (
            material(self.results[m]) for m in ("single16", "selection-mean-off")
        )
        common = on.keys() & off.keys()
        self.assertTrue(common)
        for key in common:
            self.assertEqual(on[key], off[key])
        on_first = [
            e["payload"]["action"]
            for e in events(self.results["single16"], "selection_committed")
            if e["payload"]["trajectory_index"] == 0
        ]
        off_first = [
            e["payload"]["action"]
            for e in events(self.results["selection-mean-off"], "selection_committed")
            if e["payload"]["trajectory_index"] == 0
        ]
        self.assertEqual(on_first, off_first)

    def test_primary_atomic_stop_missingness_and_censoring_are_retained(self):
        for method in S.METHODS:
            spec = S.SearchValueSpec(method)
            r = S.run_search_value_cell(
                TASK,
                spec=spec,
                budget_profile=profile(1),
                root_seed=41 if spec.stochastic else 0,
            )
            with self.subTest(method=method):
                self.assertEqual(
                    r.summary["actual_work"], dict.fromkeys(TRACK_A_WORK_AXES, 0)
                )
                self.assertTrue(r.summary["missing_terminal"])
                self.assertIsNone(r.summary["minimum_terminal_error"])
                self.assertIsNone(r.summary["first_exact_work"])
                self.assertEqual(
                    r.summary["no_exact_observation_censored_at_work"],
                    r.summary["actual_work"],
                )
                self.assertTrue(r.summary["search_summary"]["budget_valid"])

    def test_nonprimary_guard_binding_is_invalid_not_filtered(self):
        result = S.run_search_value_cell(
            TASK,
            spec=S.SearchValueSpec("selection-mean-off"),
            root_seed=41,
            budget_profile=profile(proposal_state_evaluations=0),
        )
        self.assertFalse(result.summary["search_summary"]["budget_valid"])
        self.assertTrue(result.summary["missing_terminal"])
        self.assertEqual(result.summary["actual_work"]["legal_action_scores"], 0)

    def test_deterministic_methods_have_no_random_material_or_duplicate_rows(self):
        for method in ("greedy", "beam2", "puct"):
            r = self.results[method]
            self.assertEqual(r.record["run_identity"]["root_seed"], 0)
            self.assertEqual(
                r.summary["actual_work"]["generated_perturbation_coordinates"], 0
            )
            self.assertFalse(events(r, "perturbation_draw"))
        self.assertEqual(
            self.results["greedy"].summary["search_summary"]["terminal_count"], 1
        )

    def test_all_work_first_exact_and_proposal_miss_counts_close(self):
        for method, r in self.results.items():
            usage = dict.fromkeys(TRACK_A_WORK_AXES, 0)
            first = None
            for e in r.record["search_record"]["events"]:
                if e["charge"]:
                    for a in usage:
                        usage[a] += e["charge"]["delta"][a]
                if (
                    e["kind"] == "terminal_verified"
                    and first is None
                    and e["payload"]["verification"]["success"]
                ):
                    first = dict(usage)
            with self.subTest(method=method):
                self.assertEqual(usage, r.summary["actual_work"])
                self.assertEqual(first, r.summary["first_exact_work"])
                self.assertEqual(
                    {a: usage[a] + r.summary["unspent_work"][a] for a in usage},
                    profile().budget.to_dict(),
                )
                rows = events(r, "proposal_materialized")
                work = r.summary["proposal_work"]
                self.assertEqual(work["materialized_rows"], len(rows))
                self.assertEqual(
                    work["internal_transition_evaluations"],
                    sum(
                        e["payload"]["proposal"]["internal_transition_evaluations"]
                        for e in rows
                    ),
                )
                self.assertGreater(work["completion_legal_action_evaluations"], 0)

    def test_proposal_completion_counter_matches_actual_heuristic_calls(self):
        # Observe the original heuristic on one cached row; the outer legal-action
        # enumeration is not a greedy-completion candidate evaluation.
        observed = []
        original = CountdownTask.legal_actions

        def spy(task, state):
            actions = original(task, state)
            observed.append((len(state), len(actions)))
            return actions

        with patch.object(CountdownTask, "legal_actions", spy):
            row = evaluate_track_a_proposal(TASK, TASK.initial_state, S.PROPOSAL)
        record = {
            "events": [
                {
                    "kind": "proposal_materialized",
                    "payload": {"proposal": row.to_dict()},
                }
            ]
        }
        counts = S._proposal_work(TASK, record)
        self.assertEqual(
            counts["completion_legal_action_evaluations"],
            sum(n for depth, n in observed if depth < len(TASK.initial_state)),
        )
        self.assertEqual(counts["root_action_evaluations"], observed[0][1])

    def test_summary_and_budget_tampering_rejected_even_after_redigest(self):
        for field, value in (
            ("minimum_terminal_error", 999),
            ("missing_terminal", True),
            ("winner", "single16"),
            ("proposal_work", {}),
            ("unspent_work", {}),
        ):
            r = copy.deepcopy(self.results["selection-mean-off"].record)
            r["summary"][field] = value
            with self.subTest(field=field), self.assertRaises(TraceValidationError):
                self.replay(redigest(r))
        with self.assertRaises(TraceValidationError):
            self.replay(
                self.results["selection-mean-off"].canonical_bytes,
                budget_profile=profile(65),
            )

    def test_selection_and_backup_tampering_cannot_be_hidden_by_rehashing(self):
        mutations = (
            (
                "selection_committed",
                lambda p: p["selection_semantics"].update(
                    selection_mean_coefficient=1.0
                ),
            ),
            (
                "selection_committed",
                lambda p: p.update(
                    method=S.SearchValueSpec("single16").base_method().to_dict()
                ),
            ),
            ("selection_committed", lambda p: p.update(selected_value=123.0)),
            ("trajectory_backed_up", lambda p: p.update(terminal_value=0.0)),
            ("perturbation_draw", lambda p: p.update(node_visit_index=999)),
        )
        for kind, mutate in mutations:
            r = copy.deepcopy(self.results["selection-mean-off"].record)
            mutate(
                next(
                    e["payload"]
                    for e in r["search_record"]["events"]
                    if e["kind"] == kind
                )
            )
            rehash_inner(r["search_record"])
            validate_trace_bytes(canonical_trace_bytes(r["search_record"]))
            with self.subTest(kind=kind), self.assertRaises(TraceValidationError):
                self.replay(redigest(r))

    def test_root_identity_method_substitution_and_extra_fields_rejected(self):
        r = self.results["selection-mean-off"]
        with self.assertRaises(TraceValidationError):
            self.replay(r.canonical_bytes, "single16")
        with self.assertRaises(TraceValidationError):
            self.replay(r.canonical_bytes, root_seed=42)
        altered = copy.deepcopy(r.record)
        altered["silently_new_field"] = True
        with self.assertRaises(TraceValidationError):
            self.replay(redigest(altered))

    def test_strict_json_duplicate_nonfinite_and_noncanonical_bytes_rejected(self):
        for payload in (
            b'{"x":0,"x":1}',
            b'{"x":NaN}',
            self.results["selection-mean-off"].canonical_bytes + b" ",
        ):
            with (
                self.subTest(payload=payload[:30]),
                self.assertRaises(TraceValidationError),
            ):
                self.replay(payload)

    def test_replay_uses_validated_stored_normal_material(self):
        original = S.LazyNormalSource.materialize_precharged
        observed = []

        def spy(source, *args, **kwargs):
            self.assertIsNotNone(kwargs.get("stored_material"))
            result = original(source, *args, **kwargs)
            observed.append(result.used_stored_material)
            return result

        with patch.object(S.LazyNormalSource, "materialize_precharged", spy):
            self.replay(self.results["selection-mean-off"].canonical_bytes)
        self.assertTrue(observed)
        self.assertTrue(all(observed))

    def test_fresh_process_replay_from_outside_checkout(self):
        code = """
import sys
from qmc_bmgs.benchmarks.countdown import CountdownTask
from qmc_bmgs.substrate.budget import TRACK_A_WORK_AXES, TrackAWorkBudget
from qmc_bmgs.substrate.countdown_search import TrackABudgetProfile
from qmc_bmgs_next.search_value import SearchValueSpec, replay_search_value_cell_bytes
caps = dict.fromkeys(TRACK_A_WORK_AXES, 100000)
caps['legal_action_scores'] = 64
sys.stdout.buffer.write(replay_search_value_cell_bytes(
    sys.stdin.buffer.read(), task=CountdownTask((1,1,1,1,1,1),6),
    spec=SearchValueSpec('selection-mean-off'), root_seed=41,
    budget_profile=TrackABudgetProfile('search_value_fixture','legal_action_scores',TrackAWorkBudget(**caps)),
    expected_run_identity_digest=sys.argv[1]))
"""
        r = self.results["selection-mean-off"]
        env = {
            **os.environ,
            "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
        }
        child = subprocess.run(
            [sys.executable, "-P", "-B", "-c", code, r.record["run_identity_digest"]],
            input=r.canonical_bytes,
            capture_output=True,
            cwd="/tmp",
            env=env,
            check=True,
        )
        self.assertEqual(child.stdout, r.canonical_bytes)
        self.assertEqual(child.stderr, b"")


if __name__ == "__main__":
    unittest.main()
