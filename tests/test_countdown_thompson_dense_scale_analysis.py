from __future__ import annotations

import copy
import io
import json
import unittest
from contextlib import redirect_stdout
from dataclasses import FrozenInstanceError, dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from qmc_bmgs.experiments import countdown_thompson_dense_scale_analysis as analysis
from qmc_bmgs.substrate.trace import sha256_json


@dataclass(frozen=True)
class _Cell:
    task_fingerprint: str
    terminal_value_scale: int
    exploration_seed: int

    @property
    def cell_id(self) -> str:
        return sha256_json(
            [self.task_fingerprint, self.terminal_value_scale, self.exploration_seed]
        )


def _cells() -> tuple[_Cell, ...]:
    # Deliberately not fingerprint-sorted: acceptance order is authority.
    tasks = ("z-public", "a-public") + tuple(f"public-{index}" for index in range(10))
    return tuple(
        _Cell(task, scale, seed)
        for task in tasks
        for scale in analysis.SCALES
        for seed in analysis.SEEDS
    )


def _trace(
    scale: int,
    *,
    successful: bool = False,
    backup_equal: bool = False,
    divergent: bool = True,
    terminal_trajectory: int = 1,
) -> dict:
    actions = [{"action": "first"}, {"action": "second"}]
    proposal = {"state": [1, 2], "action_order": actions, "behavior_digest": "p" * 64}
    events = [{"kind": "proposal_materialized", "payload": {"proposal": proposal}}]
    visits = [0, 0]
    for trajectory in (0, terminal_trajectory):
        chosen = int(trajectory != 0 and scale > 0 and divergent)
        scores = [1.0, 2.0] if chosen else [2.0, 1.0]
        events.append(
            {
                "kind": "selection_committed",
                "payload": {
                    "trajectory_index": trajectory,
                    "depth": 0,
                    "state": [1, 2],
                    "action_order_digest": sha256_json(actions),
                    "proposal_behavior_digest": "p" * 64,
                    "point_digest": f"point-{trajectory}",
                    "selection_semantics": {
                        "selection_rule_id": "frozen-rule",
                        "noise_dimension_normalizer": 1.0,
                    },
                    "action_index": chosen,
                    "action": actions[chosen],
                    "selection_values": scores,
                },
            }
        )
        success = successful and trajectory != 0
        error = 0 if success else 8
        value = 1.0 if success else (0.0 if scale == 0 else scale / (scale + error))
        if trajectory == 0 and backup_equal:
            value = 1.0
        events.append(
            {
                "kind": "terminal_verified",
                "payload": {
                    "trajectory_index": trajectory,
                    "observation_index": len(events) // 3,
                    "verification": {
                        "final_value": 20 - error,
                        "target": 20,
                        "success": success,
                    },
                },
            }
        )
        # Explicit observation sequence, independent of trajectory numbering.
        events[-1]["payload"]["observation_index"] = 0 if trajectory == 0 else 1
        before = visits[chosen]
        visits[chosen] += 1
        events.append(
            {
                "kind": "trajectory_backed_up",
                "payload": {
                    "trajectory_index": trajectory,
                    "terminal_value": value,
                    "terminal_absolute_error": error,
                    "updates": [
                        {
                            "state": [1, 2],
                            "action_index": chosen,
                            "before": {"visits": before, "mean": 0.0, "m2": 0.0},
                            "after": {
                                "visits": visits[chosen],
                                "mean": value,
                                "m2": 0.0,
                            },
                        }
                    ],
                },
            }
        )
    events.append(
        {"kind": "search_finished", "payload": {"summary": {"success_any": successful}}}
    )
    return {"events": events}


class _Forbidden:
    def __getitem__(self, key):
        raise AssertionError("terminal field accessed by mechanism")

    def __bool__(self):
        raise AssertionError("terminal value inspected by mechanism")


class DenseMechanismTests(unittest.TestCase):
    def test_projection_accepts_one_replayed_public_nondiagnostic_trace(self):
        from qmc_bmgs.experiments import countdown_thompson_dense_scale_core as core
        from qmc_bmgs.substrate.countdown_search import (
            replay_countdown_track_a_search_bytes,
            run_countdown_track_a_search,
        )

        inputs = core.public_fixture_inputs()
        cell = inputs.cells[0]
        arguments = {
            "task": inputs.tasks[cell.task_fingerprint],
            "proposal": inputs.proposal,
            "method": inputs.methods[cell.method_label],
            "budget_profile": inputs.budget,
            "exploration_seed": cell.exploration_seed,
        }
        result = run_countdown_track_a_search(**arguments)
        self.assertEqual(
            replay_countdown_track_a_search_bytes(
                result.canonical_bytes,
                **arguments,
                expected_run_identity_digest=result.run_identity_digest,
            ),
            result.canonical_bytes,
        )
        view = analysis.project_mechanism_cell(cell, result.record)
        self.assertEqual(view.cell_id, cell.cell_id)
        self.assertTrue(view.selections)

    def pair(self, *, backup_equal=False):
        left = analysis.project_mechanism_cell(
            _Cell("public", 0, 7168), _trace(0, backup_equal=backup_equal)
        )
        right = analysis.project_mechanism_cell(
            _Cell("public", 1, 7168), _trace(1, backup_equal=backup_equal)
        )
        return left, right

    def test_projection_never_reads_terminal_fields_or_summary(self):
        original = _trace(1)
        poisoned = copy.deepcopy(original)
        for event in poisoned["events"]:
            if event["kind"] in {"terminal_verified", "search_finished"}:
                event["payload"] = _Forbidden()
            elif event["kind"] == "trajectory_backed_up":
                event["payload"]["terminal_absolute_error"] = _Forbidden()
                event["payload"]["success"] = _Forbidden()
        cell = _Cell("public", 1, 7168)
        projected = analysis.project_mechanism_cell(cell, poisoned)
        self.assertEqual(projected, analysis.project_mechanism_cell(cell, original))
        with self.assertRaises((AttributeError, FrozenInstanceError)):
            projected.scale = 4
        self.assertFalse(hasattr(projected, "__dict__"))
        with self.assertRaises(analysis.DenseScaleAnalysisError):
            analysis.pair_mechanism_cells({"terminal_absolute_error": 0}, projected)

    def test_feedback_requires_different_prior_applied_values(self):
        left, right = self.pair()
        result = analysis.pair_mechanism_cells(left, right)
        self.assertTrue(result["feedback_informed"])
        self.assertEqual(result["paired_surface_count"], 2)
        self.assertEqual(result["first_action_divergence"]["trajectory_index"], 1)
        left, right = self.pair(backup_equal=True)
        self.assertFalse(
            analysis.pair_mechanism_cells(left, right)["feedback_informed"]
        )

    def test_first_trajectory_divergence_has_no_feedback(self):
        left, right = self.pair()
        first = replace(right.selections[0], selected_index=1, scores=(1.0, 2.0))
        right = replace(right, selections=(first,) + right.selections[1:])
        result = analysis.pair_mechanism_cells(left, right)
        self.assertEqual(result["paired_surface_count"], 1)
        self.assertEqual(result["shared_prefix_backup_values"], [])
        self.assertFalse(result["feedback_informed"])

    def test_divergence_stops_before_later_rejoin(self):
        left, right = self.pair()
        left = replace(left, selections=left.selections + (left.selections[0],))
        right = replace(right, selections=right.selections + (right.selections[0],))
        self.assertEqual(
            analysis.pair_mechanism_cells(left, right)["paired_surface_count"], 2
        )

    def test_predecision_mismatch_does_not_skip_to_later_surface(self):
        left, right = self.pair()
        changed = replace(right.selections[0], point_digest="different")
        right = replace(right, selections=(changed,) + right.selections[1:])
        result = analysis.pair_mechanism_cells(left, right)
        self.assertEqual(result["stop_reason"], "predecision_mismatch")
        self.assertEqual(result["paired_surface_count"], 0)
        self.assertIsNone(result["first_action_divergence"])

    def test_changed_scores_without_changed_action_are_not_divergence(self):
        left, right = self.pair()
        changed = replace(right.selections[1], selected_index=0, scores=(3.0, 1.0))
        right = replace(right, selections=(right.selections[0], changed))
        self.assertIsNone(
            analysis.pair_mechanism_cells(left, right)["first_action_divergence"]
        )

    def test_missing_or_empty_selection_is_not_fabricated_divergence(self):
        left, right = self.pair()
        result = analysis.pair_mechanism_cells(left, replace(right, selections=()))
        self.assertEqual(result["stop_reason"], "missing_selection")
        self.assertIsNone(result["first_action_divergence"])

    def test_duplicate_coordinate_and_bad_backup_visit_rejected(self):
        trace = _trace(0)
        trace["events"].insert(2, copy.deepcopy(trace["events"][1]))
        with self.assertRaisesRegex(analysis.DenseScaleAnalysisError, "duplicate"):
            analysis.project_mechanism_cell(_Cell("public", 0, 7168), trace)
        trace = _trace(0)
        trace["events"][3]["payload"]["updates"][0]["after"]["visits"] = 99
        with self.assertRaisesRegex(analysis.DenseScaleAnalysisError, "visit"):
            analysis.project_mechanism_cell(_Cell("public", 0, 7168), trace)


class DenseReductionTests(unittest.TestCase):
    def setUp(self):
        self.cells = _cells()

    def reduce(self, *, successes=(), equal_backup=(), fixture=False):
        traces = [
            _trace(
                cell.terminal_value_scale,
                successful=(
                    cell.terminal_value_scale,
                    cell.task_fingerprint,
                    cell.exploration_seed,
                )
                in successes,
                backup_equal=(
                    cell.terminal_value_scale,
                    cell.task_fingerprint,
                    cell.exploration_seed,
                )
                in equal_backup,
            )
            for cell in self.cells
        ]
        return analysis.reduce_replay_closed_traces(self.cells, traces, fixture=fixture)

    def test_every_sealed_field_and_acceptance_order(self):
        result = self.reduce()
        self.assertEqual(result["task_seed_order"][0]["task_fingerprint"], "z-public")
        self.assertEqual(result["task_seed_order"][4]["task_fingerprint"], "a-public")
        self.assertEqual(result["mechanism"]["pair_count"], 336)
        required = {
            "success_vector",
            "exact_success_count",
            "first_hit_trajectory_index_vector",
            "minimum_terminal_absolute_error_vector",
            "terminal_absolute_error_vectors",
            "terminal_value_vectors",
            "paired_new_success_count_vs_scale_0",
            "paired_lost_success_count_vs_scale_0",
            "paired_net_success_difference_vs_scale_0",
            "paired_minimum_error_win_tie_loss_vs_scale_0",
            "feedback_informed_first_divergence_count",
            "first_divergence_coordinate_distribution",
            "scale",
        }
        for row in result["per_scale"]:
            self.assertEqual(set(row), required)
            self.assertEqual(len(row["success_vector"]), 48)
            self.assertEqual(
                sum(
                    entry["count"]
                    for entry in row["first_divergence_coordinate_distribution"]
                ),
                row["feedback_informed_first_divergence_count"],
            )
        base = result["per_scale"][0]
        self.assertEqual(
            base["paired_minimum_error_win_tie_loss_vs_scale_0"],
            {"wins": 0, "ties": 48, "losses": 0},
        )
        self.assertEqual(base["first_divergence_coordinate_distribution"], [])
        self.assertEqual(result["selected_scale"], 1)
        self.assertEqual(result["decision"], analysis.STOP)

    def test_ready_and_lower_scale_tie_break(self):
        successes = {
            (scale, "z-public", seed) for scale in (1, 2) for seed in (7168, 7169)
        }
        result = self.reduce(successes=successes)
        self.assertEqual(result["selected_scale"], 1)
        self.assertEqual(result["decision"], analysis.READY)
        self.assertEqual(result["per_scale"][1]["exact_success_count"], 2)

    def test_every_new_success_guard_and_no_fallback(self):
        successes = {(1, "z-public", seed) for seed in (7168, 7169, 7170)}
        successes |= {(2, "z-public", seed) for seed in (7168, 7169)}
        # Baseline and scale one receive identical applied prior values for
        # exactly one new-success pair: the winning scale must fail its guard.
        equal = {(0, "z-public", 7170), (1, "z-public", 7170)}
        result = self.reduce(successes=successes, equal_backup=equal)
        self.assertEqual(result["selected_scale"], 1)
        self.assertEqual(result["decision"], analysis.STOP)

    def test_net_gain_counts_lost_successes(self):
        successes = {
            (0, "a-public", 7168),
            (1, "z-public", 7168),
            (1, "z-public", 7169),
        }
        result = self.reduce(successes=successes)
        row = result["per_scale"][1]
        self.assertEqual(row["paired_new_success_count_vs_scale_0"], 2)
        self.assertEqual(row["paired_lost_success_count_vs_scale_0"], 1)
        self.assertEqual(row["paired_net_success_difference_vs_scale_0"], 1)
        self.assertEqual(result["decision"], analysis.STOP)

    def test_fixture_never_gets_handoff_or_selected_scale(self):
        result = self.reduce(fixture=True)
        self.assertNotIn("decision", result)
        self.assertNotIn("selected_scale", result)

    def test_reduction_stage_order(self):
        observed = []
        traces = [_trace(cell.terminal_value_scale) for cell in self.cells]
        analysis.reduce_replay_closed_traces(
            self.cells, traces, fixture=True, stage_observer=observed.append
        )
        self.assertEqual(observed, list(analysis.STAGE_ORDER[2:]))

    def test_first_hit_is_trajectory_not_observation_index(self):
        traces = [
            _trace(cell.terminal_value_scale, successful=True, terminal_trajectory=7)
            for cell in self.cells
        ]
        result = analysis.reduce_replay_closed_traces(self.cells, traces, fixture=True)
        self.assertEqual(
            result["per_scale"][0]["first_hit_trajectory_index_vector"], [7] * 48
        )

    def test_missing_duplicate_extra_reordered_and_empty_terminal_fail(self):
        traces = [_trace(cell.terminal_value_scale) for cell in self.cells]
        bad_orders = (
            self.cells[:-1],
            self.cells + self.cells[:1],
            self.cells[:-1] + self.cells[:1],
            (self.cells[1], self.cells[0]) + self.cells[2:],
        )
        for cells in bad_orders:
            with (
                self.subTest(count=len(cells)),
                self.assertRaises(analysis.DenseScaleAnalysisError),
            ):
                analysis.reduce_replay_closed_traces(cells, traces, fixture=True)
        traces[0] = {"events": []}
        with self.assertRaisesRegex(analysis.DenseScaleAnalysisError, "empty"):
            analysis.reduce_replay_closed_traces(self.cells, traces, fixture=True)

    def test_exact_rational_even_odd_large_and_empty(self):
        self.assertEqual(
            analysis.exact_integer_summary([1, 4])["median"],
            {"numerator": 5, "denominator": 2},
        )
        self.assertEqual(
            analysis.exact_integer_summary([7, 2, 3])["median"],
            {"numerator": 3, "denominator": 1},
        )
        self.assertEqual(
            analysis.exact_integer_summary([10**400, 10**400 + 1])["mean"],
            {"numerator": 2 * 10**400 + 1, "denominator": 2},
        )
        for values in ([], [True], [1.0]):
            with self.assertRaises(analysis.DenseScaleAnalysisError):
                analysis.exact_integer_summary(values)


class DenseAnalysisBoundaryTests(unittest.TestCase):
    def test_self_test_and_bad_cli_never_load_execution_modules(self):
        with patch.object(
            analysis, "_modules", side_effect=AssertionError("operational import")
        ):
            for args, status in (
                (["--self-test"], "PASS"),
                ([], "INVALID_ANALYSIS"),
                (["--self-test", "--bundle", "/sealed"], "INVALID_ANALYSIS"),
                (["--analyze-v2r3", "/raw"], "INVALID_ANALYSIS"),
            ):
                output = io.StringIO()
                with redirect_stdout(output):
                    analysis.main(args)
                self.assertEqual(json.loads(output.getvalue())["status"], status)

    def test_all_records_close_before_mechanism_and_no_reduce_on_failure(self):
        cells = _cells()
        traces = [_trace(cell.terminal_value_scale) for cell in cells]
        qualification = {"deterministic_digest": "q" * 64}
        events = []
        payload = {
            "analysis": {
                "analysis_order": list(analysis.STAGE_ORDER),
                "deterministic_digest": "m" * 64,
            }
        }
        inputs = SimpleNamespace(
            cells=cells,
            fixture=True,
            bundle_id="fixture",
            payload=payload,
            revalidate=lambda: None,
        )
        reviewed = SimpleNamespace(
            raw=b"authority",
            payload={
                "anchor_qualification": qualification,
                "deterministic_digest": "a" * 64,
                "output_parent_binding": {},
                "runner_build_attestation": {"source_files": {}},
            },
            revalidate=lambda: events.append("authority_recheck"),
            authorization_revision="b" * 40,
            execution_head="c" * 40,
        )
        verified = SimpleNamespace(
            records=tuple(range(384)),
            run_manifest={"run_binding": {}},
            run_manifest_digest="r" * 64,
            collective_generation=(1,),
            authority_generation=(1,),
            records_jsonl_bytes=b"records",
            commit_receipt={},
        )

        def qualify():
            events.append("qualification")
            return qualification

        def load(*args, **kwargs):
            events.append("external_authority")
            return reviewed

        def verify(inputs, cell, row, binding):
            events.append(f"replay:{row}")
            return traces[row]

        def writer(path, raw, **kwargs):
            kwargs["pre_publication_check"]()
            kwargs["post_durability_check"]()
            events.append("summary")

        core = SimpleNamespace(
            reproduce_anchor_qualification=qualify,
            public_fixture_inputs=lambda: inputs,
            verify_record=verify,
            canonical_bytes=analysis._bytes,
            require_git_oid=lambda revision: revision,
            require_ancestor=lambda *a, **k: None,
            verify_historical_source_receipts=lambda *a: events.append(
                "historical_source"
            ),
        )
        hint = SimpleNamespace(
            execution_head_revision="b" * 40,
            revalidate=lambda: events.append("hint_recheck"),
        )
        pub = SimpleNamespace(
            read_dense_scale_fixture_execution_head_hint=lambda *a, **k: hint,
            verify_dense_scale_fixture_v2r3=lambda *a, **k: verified,
            publish_dense_scale_fixture_summary=writer,
        )
        runner = SimpleNamespace(load_reviewed_authorization=load)
        original = analysis.project_mechanism_cell

        def project(*args):
            self.assertIn("replay:383", events)
            events.append("mechanism")
            return original(*args)

        args = dict(
            authorization_file=Path("/fixture-authority"),
            authorization_digest="a" * 64,
            authorization_revision="b" * 40,
            repository_root=Path("/repo"),
            output_path=Path("/summary"),
        )
        with (
            patch.object(analysis, "_modules", return_value=(core, pub, runner)),
            patch.object(analysis, "_publication_inputs", return_value=object()),
            patch.object(analysis, "project_mechanism_cell", side_effect=project),
        ):
            result = analysis.analyze_dense_scale_fixture(Path("/fixture"), **args)
            self.assertEqual(events[:2], ["qualification", "external_authority"])
            self.assertEqual(result["fixture_status"], "FIXTURE_REPLAY_PASS")
            self.assertNotIn("decision", result)
            self.assertNotIn("selected_scale", result)
            self.assertNotIn("per_scale", result)
            events.clear()
            hint.execution_head_revision = "d" * 40
            with self.assertRaisesRegex(
                analysis.DenseScaleAnalysisError, "source epoch"
            ):
                analysis.analyze_dense_scale_fixture(Path("/fixture"), **args)
            self.assertFalse(any(event.startswith("replay:") for event in events))
            hint.execution_head_revision = "b" * 40
            events.clear()

            def fail_last(inputs, cell, row, binding):
                events.append(f"replay:{row}")
                if row == 383:
                    raise ValueError("replay failed")
                return traces[row]

            core.verify_record = fail_last
            with self.assertRaisesRegex(ValueError, "replay failed"):
                analysis.analyze_dense_scale_fixture(Path("/fixture"), **args)
            self.assertNotIn("mechanism", events)
            self.assertNotIn("summary", events)
            self.assertIn("replay:383", events)


if __name__ == "__main__":
    unittest.main()
