from __future__ import annotations

import copy
import math
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from qmc_bmgs.benchmarks.countdown import CountdownTask
from qmc_bmgs.substrate.budget import TRACK_A_WORK_AXES, TrackAWorkBudget
from qmc_bmgs.substrate.countdown_search import (
    DIMENSION_NORMALIZED_METHOD_SPEC_SCHEMA_VERSION,
    DIMENSION_NORMALIZED_SELECTION_RULE_ID,
    TrackABudgetProfile,
    TrackAMethodSpec,
    _action_dimension_noise_normalizer,
    build_search_run_identity,
    replay_countdown_track_a_search_bytes,
    run_countdown_track_a_search,
)
from qmc_bmgs.substrate.perturbations import LazyNormalSource
from qmc_bmgs.substrate.proposals import TrackAProposalSpec
from qmc_bmgs.substrate.trace import (
    TraceValidationError,
    canonical_trace_bytes,
    sha256_json,
    validate_trace_bytes,
)


TASK = CountdownTask((1, 2, 3, 4, 5, 6), target=720)
HEURISTIC = TrackAProposalSpec("greedy_rollout_target_error/v1")


def _budget(**overrides: int) -> TrackAWorkBudget:
    values = {axis: 20_000 for axis in TRACK_A_WORK_AXES}
    values.update(overrides)
    return TrackAWorkBudget(**values)


def _verifier_profile(calls: int = 2) -> TrackABudgetProfile:
    return TrackABudgetProfile(
        profile_id=f"test_verifier{calls}",
        primary_axis="verifier_calls",
        budget=_budget(verifier_calls=calls),
    )


def _score_profile(scores: int) -> TrackABudgetProfile:
    return TrackABudgetProfile(
        profile_id=f"test_score{scores}",
        primary_axis="legal_action_scores",
        budget=_budget(legal_action_scores=scores),
    )


def _events(record: dict[str, object], kind: str) -> list[dict[str, object]]:
    events = record["events"]
    assert isinstance(events, list)
    return [
        event
        for event in events
        if isinstance(event, dict) and event.get("kind") == kind
    ]


def _rehash_trace(record: dict[str, object]) -> None:
    events = record["events"]
    assert isinstance(events, list)
    previous = "0" * 64
    for index, event in enumerate(events):
        assert isinstance(event, dict)
        event["index"] = index
        event["previous_event_digest"] = previous
        core = {key: value for key, value in event.items() if key != "event_digest"}
        event["event_digest"] = sha256_json(core)
        previous = str(event["event_digest"])
    record["event_count"] = len(events)
    record["final_event_digest"] = previous
    core = {
        key: value for key, value in record.items() if key != "deterministic_digest"
    }
    record["deterministic_digest"] = sha256_json(core)


class TrackASearchTests(unittest.TestCase):
    def test_method_specs_are_closed_and_deterministic_seed_is_not_replicated(
        self,
    ) -> None:
        self.assertEqual(TrackAMethodSpec.greedy().selected_source, "none")
        self.assertEqual(TrackAMethodSpec.beam_width_two().beam_width, 2)
        self.assertEqual(TrackAMethodSpec.puct().c_puct, 1.0)
        self.assertEqual(
            TrackAMethodSpec.frozen_thompson("iid").prior_bonus,
            0.1,
        )
        self.assertEqual(
            TrackAMethodSpec.candidate_thompson("sobol").prior_bonus,
            1.0,
        )
        self.assertEqual(
            TrackAMethodSpec.candidate_thompson("iid").to_dict(),
            {
                "beam_width": None,
                "c_puct": None,
                "method": "thompson",
                "method_id": "thompson_binary_terminal/v1",
                "posterior_sd_scale": 1.0,
                "prior_bonus": 1.0,
                "schema_version": "qmc-bmgs-track-a-method-spec/v1",
                "selected_source": "iid",
            },
        )
        dimension_normalized = TrackAMethodSpec.dimension_normalized_thompson("sobol")
        self.assertEqual(
            dimension_normalized.to_dict(),
            {
                "beam_width": None,
                "c_puct": None,
                "method": "thompson",
                "method_id": "thompson_binary_terminal_dimnorm_noise/v2",
                "posterior_sd_scale": 1.0,
                "prior_bonus": 1.0,
                "schema_version": DIMENSION_NORMALIZED_METHOD_SPEC_SCHEMA_VERSION,
                "selected_source": "sobol",
                "selection_rule_id": DIMENSION_NORMALIZED_SELECTION_RULE_ID,
            },
        )

        with self.assertRaisesRegex(ValueError, "exploration_seed=0"):
            build_search_run_identity(
                task=TASK,
                proposal=HEURISTIC,
                method=TrackAMethodSpec.puct(),
                budget_profile=_verifier_profile(1),
                exploration_seed=1,
            )
        with self.assertRaisesRegex(ValueError, "fields do not match"):
            TrackAMethodSpec(
                method="beam",
                selected_source="none",
                beam_width=3,
            )
        with self.assertRaisesRegex(ValueError, "plain integer"):
            TrackAMethodSpec(
                method="beam",
                selected_source="none",
                beam_width=2.0,  # type: ignore[arg-type]
            )
        with self.assertRaisesRegex(ValueError, "plain float"):
            TrackAMethodSpec(
                method="puct",
                selected_source="none",
                c_puct=1,  # type: ignore[arg-type]
            )
        with self.assertRaisesRegex(ValueError, "IID or Sobol"):
            TrackAMethodSpec(
                method="thompson",
                selected_source="none",
                prior_bonus=1.0,
                posterior_sd_scale=1.0,
            )
        with self.assertRaisesRegex(ValueError, "does not define"):
            TrackAMethodSpec(
                method="thompson",
                selected_source="iid",
                prior_bonus=1.0,
                posterior_sd_scale=1.0,
                selection_rule_id=DIMENSION_NORMALIZED_SELECTION_RULE_ID,
            )
        with self.assertRaisesRegex(ValueError, "fields do not match"):
            TrackAMethodSpec(
                method="thompson",
                selected_source="iid",
                prior_bonus=1.0,
                posterior_sd_scale=1.0,
                selection_rule_id="wrong/v1",
                schema_version=DIMENSION_NORMALIZED_METHOD_SPEC_SCHEMA_VERSION,
            )

    def test_budget_profile_requires_one_supported_positive_primary_axis(self) -> None:
        with self.assertRaisesRegex(ValueError, "primary_axis"):
            TrackABudgetProfile("bad", "transitions", _budget())
        with self.assertRaisesRegex(ValueError, "positive"):
            TrackABudgetProfile(
                "zero",
                "verifier_calls",
                _budget(verifier_calls=0),
            )

    def test_run_identity_binds_primary_axis_even_when_label_and_limits_match(
        self,
    ) -> None:
        budget = _budget()
        score_profile = TrackABudgetProfile(
            "same_label",
            "legal_action_scores",
            budget,
        )
        verifier_profile = TrackABudgetProfile(
            "same_label",
            "verifier_calls",
            budget,
        )
        common = {
            "task": TASK,
            "proposal": HEURISTIC,
            "method": TrackAMethodSpec.puct(),
            "exploration_seed": 0,
        }
        score_identity = build_search_run_identity(
            budget_profile=score_profile,
            **common,
        )
        verifier_identity = build_search_run_identity(
            budget_profile=verifier_profile,
            **common,
        )
        self.assertNotEqual(score_identity, verifier_identity)
        self.assertNotEqual(
            sha256_json(score_identity),
            sha256_json(verifier_identity),
        )

    def test_exactly_exhausted_non_primary_guard_invalidates_the_cell(self) -> None:
        profile = TrackABudgetProfile(
            "exact_edge_guard",
            "verifier_calls",
            _budget(verifier_calls=1, edge_selections=5, transitions=5),
        )
        result = run_countdown_track_a_search(
            TASK,
            proposal=HEURISTIC,
            method=TrackAMethodSpec.greedy(),
            budget_profile=profile,
            exploration_seed=0,
        )

        self.assertEqual(result.summary["stop_reason"], "method_complete")
        self.assertFalse(result.summary["budget_valid"])
        self.assertEqual(
            result.summary["non_primary_exhausted_axes"],
            ["edge_selections", "transitions"],
        )

    def test_greedy_uses_no_random_coordinates_and_replays(self) -> None:
        profile = _verifier_profile(2)
        result = run_countdown_track_a_search(
            TASK,
            proposal=HEURISTIC,
            method=TrackAMethodSpec.greedy(),
            budget_profile=profile,
            exploration_seed=0,
        )

        self.assertEqual(result.summary["stop_reason"], "method_complete")
        self.assertEqual(result.summary["terminal_count"], 1)
        self.assertTrue(result.summary["success_any"])
        usage = result.summary["ledger_usage"]
        self.assertEqual(usage["generated_perturbation_coordinates"], 0)
        self.assertEqual(usage["edge_selections"], 5)
        self.assertEqual(usage["transitions"], 5)
        self.assertEqual(usage["verifier_calls"], 1)
        self.assertEqual(result.record["run_identity"]["selected_source"], "none")
        self.assertEqual(result.record["run_identity"]["exploration_seed"], 0)
        self.assertFalse(_events(result.record, "perturbation_draw"))

        self.assertEqual(
            replay_countdown_track_a_search_bytes(
                result.canonical_bytes,
                task=TASK,
                proposal=HEURISTIC,
                method=TrackAMethodSpec.greedy(),
                budget_profile=profile,
                exploration_seed=0,
                expected_run_identity_digest=result.run_identity_digest,
            ),
            result.canonical_bytes,
        )

    def test_beam_is_layer_synchronous_width_two_with_combined_layer_receipts(
        self,
    ) -> None:
        result = run_countdown_track_a_search(
            TASK,
            proposal=HEURISTIC,
            method=TrackAMethodSpec.beam_width_two(),
            budget_profile=_verifier_profile(2),
            exploration_seed=0,
        )

        layers = _events(result.record, "beam_layer_selection_committed")
        self.assertEqual(len(layers), TASK.max_steps)
        root = layers[0]
        root_payload = root["payload"]
        root_charge = root["charge"]
        assert isinstance(root_payload, dict)
        assert isinstance(root_charge, dict)
        self.assertEqual(root_payload["beam_width"], 2)
        self.assertEqual(len(root_payload["selected"]), 2)
        self.assertEqual(
            root_charge["delta"],
            {
                "proposal_state_evaluations": 1,
                "proposal_action_scores": 53,
                "legal_action_scores": 53,
                "generated_perturbation_coordinates": 0,
                "edge_selections": 2,
                "transitions": 2,
                "verifier_calls": 0,
            },
        )
        self.assertEqual(result.summary["terminal_count"], 2)
        self.assertEqual(result.summary["exact_terminal_count"], 2)
        self.assertEqual(result.summary["stop_reason"], "method_complete")
        terminals = _events(result.record, "terminal_verified")
        self.assertEqual(len(terminals), 2)
        for terminal in terminals:
            verification = terminal["payload"]["verification"]
            self.assertEqual(verification["action_count_consumed"], 5)
            self.assertTrue(verification["source_use_exact"])

    def test_puct_continues_after_exact_hit_and_reverse_backups_close(self) -> None:
        profile = _verifier_profile(2)
        result = run_countdown_track_a_search(
            TASK,
            proposal=HEURISTIC,
            method=TrackAMethodSpec.puct(),
            budget_profile=profile,
            exploration_seed=0,
        )

        self.assertTrue(result.summary["success_any"])
        self.assertEqual(result.summary["first_exact_observation_index"], 0)
        self.assertEqual(result.summary["terminal_count"], 2)
        self.assertEqual(result.summary["exact_terminal_count"], 2)
        self.assertEqual(result.summary["stop_reason"], "primary_budget_blocked")
        self.assertEqual(result.summary["stop_blocked_axes"], ["verifier_calls"])
        backups = _events(result.record, "trajectory_backed_up")
        self.assertEqual(len(backups), 2)
        for backup in backups:
            payload = backup["payload"]
            self.assertEqual(payload["order"], "leaf_to_root")
            self.assertEqual(payload["discount"], 1.0)
            self.assertEqual(len(payload["updates"]), 5)
            self.assertIsNone(backup["charge"])
        usage = result.summary["ledger_usage"]
        self.assertLess(usage["proposal_state_evaluations"], usage["edge_selections"])

    def test_thompson_source_pairing_and_combined_step_accounting(self) -> None:
        profile = _verifier_profile(1)
        results = {}
        for source in ("iid", "sobol"):
            for label, method in (
                ("frozen", TrackAMethodSpec.frozen_thompson(source)),
                ("candidate", TrackAMethodSpec.candidate_thompson(source)),
            ):
                result = run_countdown_track_a_search(
                    TASK,
                    proposal=HEURISTIC,
                    method=method,
                    budget_profile=profile,
                    exploration_seed=7168,
                )
                results[(source, label)] = result
                usage = result.summary["ledger_usage"]
                self.assertEqual(
                    usage["generated_perturbation_coordinates"],
                    usage["legal_action_scores"],
                )
                for selection in _events(result.record, "selection_committed"):
                    delta = selection["charge"]["delta"]
                    count = len(selection["payload"]["scored_action_indices"])
                    self.assertEqual(delta["legal_action_scores"], count)
                    self.assertEqual(delta["generated_perturbation_coordinates"], count)
                    self.assertEqual(delta["edge_selections"], 1)
                    self.assertEqual(delta["transitions"], 1)
                for material in _events(result.record, "perturbation_draw"):
                    self.assertIsNone(material["charge"])
                self.assertEqual(
                    replay_countdown_track_a_search_bytes(
                        result.canonical_bytes,
                        task=TASK,
                        proposal=HEURISTIC,
                        method=method,
                        budget_profile=profile,
                        exploration_seed=7168,
                        expected_run_identity_digest=result.run_identity_digest,
                    ),
                    result.canonical_bytes,
                )

        def first_point(result: object) -> dict[str, object]:
            record = result.record  # type: ignore[attr-defined]
            return _events(record, "perturbation_draw")[0]["payload"]

        self.assertEqual(
            first_point(results[("iid", "frozen")]),
            first_point(results[("iid", "candidate")]),
        )
        self.assertEqual(
            first_point(results[("sobol", "frozen")]),
            first_point(results[("sobol", "candidate")]),
        )
        self.assertNotEqual(
            first_point(results[("iid", "frozen")])["uniforms"],
            first_point(results[("sobol", "frozen")])["uniforms"],
        )
        self.assertEqual(
            len(first_point(results[("iid", "frozen")])["uniforms"]),
            53,
        )

    def test_dimension_normalized_thompson_is_one_factor_and_replays(self) -> None:
        self.assertEqual(_action_dimension_noise_normalizer(1), 1.0)
        for action_count in (2, 27, 55):
            self.assertEqual(
                _action_dimension_noise_normalizer(action_count),
                math.sqrt(2.0 * math.log(action_count)),
            )
        with self.assertRaisesRegex(ValueError, "positive plain integer"):
            _action_dimension_noise_normalizer(True)
        with self.assertRaisesRegex(ValueError, "positive plain integer"):
            _action_dimension_noise_normalizer(0)

        profile = _verifier_profile(1)
        for source in ("iid", "sobol"):
            legacy_method = TrackAMethodSpec.candidate_thompson(source)
            v2_method = TrackAMethodSpec.dimension_normalized_thompson(source)
            legacy = run_countdown_track_a_search(
                TASK,
                proposal=HEURISTIC,
                method=legacy_method,
                budget_profile=profile,
                exploration_seed=7168,
            )
            v2 = run_countdown_track_a_search(
                TASK,
                proposal=HEURISTIC,
                method=v2_method,
                budget_profile=profile,
                exploration_seed=7168,
            )

            legacy_point = _events(legacy.record, "perturbation_draw")[0]["payload"]
            v2_point = _events(v2.record, "perturbation_draw")[0]["payload"]
            self.assertEqual(legacy_point, v2_point)
            self.assertNotEqual(
                legacy.run_identity_digest,
                v2.run_identity_digest,
            )

            legacy_selection = _events(legacy.record, "selection_committed")[0][
                "payload"
            ]
            v2_selection = _events(v2.record, "selection_committed")[0]["payload"]
            self.assertNotIn("selection_semantics", legacy_selection)
            semantics = v2_selection["selection_semantics"]
            self.assertEqual(
                semantics,
                {
                    "action_count": 53,
                    "noise_dimension_normalizer": math.sqrt(2.0 * math.log(53)),
                    "selection_rule_id": DIMENSION_NORMALIZED_SELECTION_RULE_ID,
                },
            )

            proposal = _events(v2.record, "proposal_materialized")[0]["payload"]
            prior_logp = proposal["proposal"]["prior_logp"]
            normals = v2_point["normals"]
            expected_values = [
                math.exp(logp)
                + 1.0
                / (_action_dimension_noise_normalizer(len(prior_logp)) * math.sqrt(1.0))
                * normal
                for logp, normal in zip(prior_logp, normals)
            ]
            self.assertEqual(v2_selection["selection_values"], expected_values)
            self.assertEqual(
                v2_selection["action_index"],
                max(range(len(expected_values)), key=expected_values.__getitem__),
            )
            self.assertEqual(
                replay_countdown_track_a_search_bytes(
                    v2.canonical_bytes,
                    task=TASK,
                    proposal=HEURISTIC,
                    method=v2_method,
                    budget_profile=profile,
                    exploration_seed=7168,
                    expected_run_identity_digest=v2.run_identity_digest,
                ),
                v2.canonical_bytes,
            )

    def test_dimension_normalized_selection_semantics_tampering_fails_stage_one(
        self,
    ) -> None:
        profile = _verifier_profile(1)
        method = TrackAMethodSpec.dimension_normalized_thompson("iid")
        result = run_countdown_track_a_search(
            TASK,
            proposal=HEURISTIC,
            method=method,
            budget_profile=profile,
            exploration_seed=7168,
        )
        for field, value in (
            ("action_count", 52),
            ("action_count", 53.0),
            ("noise_dimension_normalizer", 1.0),
            ("noise_dimension_normalizer", True),
            ("selection_rule_id", "wrong/v1"),
        ):
            with self.subTest(field=field, value=value):
                tampered = copy.deepcopy(result.record)
                selection = _events(tampered, "selection_committed")[0]
                selection["payload"]["selection_semantics"][field] = value
                _rehash_trace(tampered)
                tampered_bytes = canonical_trace_bytes(tampered)
                validate_trace_bytes(tampered_bytes)
                with self.assertRaisesRegex(
                    TraceValidationError,
                    "dimension-normalized selection semantics",
                ):
                    replay_countdown_track_a_search_bytes(
                        tampered_bytes,
                        task=TASK,
                        proposal=HEURISTIC,
                        method=method,
                        budget_profile=profile,
                        exploration_seed=7168,
                        expected_run_identity_digest=result.run_identity_digest,
                    )

    def test_dimension_normalized_uniform_prior_is_a_common_constant(self) -> None:
        profile = _verifier_profile(1)
        method = TrackAMethodSpec.dimension_normalized_thompson("iid")
        result = run_countdown_track_a_search(
            TASK,
            proposal=TrackAProposalSpec("uniform/v1"),
            method=method,
            budget_profile=profile,
            exploration_seed=7168,
        )
        proposal = _events(result.record, "proposal_materialized")[0]["payload"][
            "proposal"
        ]
        point = _events(result.record, "perturbation_draw")[0]["payload"]
        selection = _events(result.record, "selection_committed")[0]["payload"]
        action_count = len(proposal["prior_logp"])
        normalizer = _action_dimension_noise_normalizer(action_count)
        self.assertEqual(len(set(proposal["prior_logp"])), 1)
        expected = [
            math.exp(logp) + 1.0 / (normalizer * math.sqrt(1.0)) * normal
            for logp, normal in zip(proposal["prior_logp"], point["normals"])
        ]
        self.assertEqual(selection["selection_values"], expected)
        self.assertEqual(selection["action_index"], 1)

    def test_score_stop_preflights_whole_dynamic_action_vector(self) -> None:
        result = run_countdown_track_a_search(
            TASK,
            proposal=HEURISTIC,
            method=TrackAMethodSpec.puct(),
            budget_profile=_score_profile(53),
            exploration_seed=0,
        )

        self.assertEqual(result.summary["stop_reason"], "primary_budget_blocked")
        self.assertEqual(result.summary["stop_blocked_axes"], ["legal_action_scores"])
        self.assertEqual(result.summary["ledger_usage"]["legal_action_scores"], 53)
        self.assertEqual(result.summary["ledger_usage"]["edge_selections"], 1)
        self.assertEqual(result.summary["terminal_count"], 0)
        self.assertEqual(result.summary["node_count"], 1)
        self.assertEqual(result.summary["incomplete_trajectory_count"], 1)
        attempted = result.summary["stop_attempted_charge"]
        self.assertGreater(attempted["legal_action_scores"], 0)
        self.assertFalse(_events(result.record, "terminal_verified"))

    def test_rejected_root_thompson_step_consumes_no_point_or_partial_event(
        self,
    ) -> None:
        result = run_countdown_track_a_search(
            TASK,
            proposal=HEURISTIC,
            method=TrackAMethodSpec.frozen_thompson("sobol"),
            budget_profile=_score_profile(52),
            exploration_seed=7168,
        )

        usage = result.summary["ledger_usage"]
        self.assertEqual(usage["legal_action_scores"], 0)
        self.assertEqual(usage["generated_perturbation_coordinates"], 0)
        self.assertEqual(usage["edge_selections"], 0)
        self.assertEqual(result.summary["node_count"], 0)
        self.assertEqual(result.summary["selected_source_point_count"], 0)
        self.assertEqual(
            [event["kind"] for event in result.record["events"]],
            ["search_finished"],
        )

    def test_rehashed_selection_tampering_fails_fresh_search_replay(self) -> None:
        profile = _verifier_profile(1)
        method = TrackAMethodSpec.puct()
        result = run_countdown_track_a_search(
            TASK,
            proposal=HEURISTIC,
            method=method,
            budget_profile=profile,
            exploration_seed=0,
        )
        tampered = copy.deepcopy(result.record)
        selection = _events(tampered, "selection_committed")[0]
        payload = selection["payload"]
        payload["action_index"] = (payload["action_index"] + 1) % 53
        _rehash_trace(tampered)
        tampered_bytes = canonical_trace_bytes(tampered)
        validate_trace_bytes(tampered_bytes)

        with self.assertRaisesRegex(TraceValidationError, "byte-identical"):
            replay_countdown_track_a_search_bytes(
                tampered_bytes,
                task=TASK,
                proposal=HEURISTIC,
                method=method,
                budget_profile=profile,
                exploration_seed=0,
                expected_run_identity_digest=result.run_identity_digest,
            )

    def test_stage_one_rejects_rehashed_point_and_reference_tampering(self) -> None:
        profile = _verifier_profile(2)
        method = TrackAMethodSpec.frozen_thompson("sobol")
        result = run_countdown_track_a_search(
            TASK,
            proposal=HEURISTIC,
            method=method,
            budget_profile=profile,
            exploration_seed=7168,
        )

        point_tamper = copy.deepcopy(result.record)
        point_event = _events(point_tamper, "perturbation_draw")[0]
        point = point_event["payload"]
        point["uniforms"][0] = point["uniforms"][0] / 2.0
        point["uniform_digest"] = sha256_json(point["uniforms"])
        point_core = {
            key: value for key, value in point.items() if key != "point_digest"
        }
        point["point_digest"] = sha256_json(point_core)
        selection = _events(point_tamper, "selection_committed")[0]
        selection["payload"]["point_digest"] = point["point_digest"]
        _rehash_trace(point_tamper)
        point_bytes = canonical_trace_bytes(point_tamper)
        validate_trace_bytes(point_bytes)
        with self.assertRaisesRegex(TraceValidationError, "stage 1 point"):
            replay_countdown_track_a_search_bytes(
                point_bytes,
                task=TASK,
                proposal=HEURISTIC,
                method=method,
                budget_profile=profile,
                exploration_seed=7168,
                expected_run_identity_digest=result.run_identity_digest,
            )

        duplicate_reference = copy.deepcopy(result.record)
        points = _events(duplicate_reference, "perturbation_draw")
        selections = _events(duplicate_reference, "selection_committed")
        self.assertGreaterEqual(len(points), 2)
        selections[1]["payload"]["point_digest"] = points[0]["payload"]["point_digest"]
        _rehash_trace(duplicate_reference)
        duplicate_bytes = canonical_trace_bytes(duplicate_reference)
        validate_trace_bytes(duplicate_bytes)
        with self.assertRaisesRegex(TraceValidationError, "referenced more than once"):
            replay_countdown_track_a_search_bytes(
                duplicate_bytes,
                task=TASK,
                proposal=HEURISTIC,
                method=method,
                budget_profile=profile,
                exploration_seed=7168,
                expected_run_identity_digest=result.run_identity_digest,
            )

        removed_point = copy.deepcopy(result.record)
        events = removed_point["events"]
        first_point_index = next(
            index
            for index, event in enumerate(events)
            if event["kind"] == "perturbation_draw"
        )
        del events[first_point_index]
        _rehash_trace(removed_point)
        removed_bytes = canonical_trace_bytes(removed_point)
        validate_trace_bytes(removed_bytes)
        with self.assertRaisesRegex(
            TraceValidationError,
            "unknown point|visit has a gap",
        ):
            replay_countdown_track_a_search_bytes(
                removed_bytes,
                task=TASK,
                proposal=HEURISTIC,
                method=method,
                budget_profile=profile,
                exploration_seed=7168,
                expected_run_identity_digest=result.run_identity_digest,
            )

    def test_verifier8_preflight_prevents_a_ninth_trajectory_or_source_draw(
        self,
    ) -> None:
        profile = _verifier_profile(8)
        method = TrackAMethodSpec.frozen_thompson("iid")
        original_initial_state = CountdownTask.initial_state.fget
        original_plan_draw = LazyNormalSource.plan_draw
        initial_state_calls = 0
        plan_calls = 0

        def guarded_initial_state(task: CountdownTask) -> tuple[int, ...]:
            nonlocal initial_state_calls
            initial_state_calls += 1
            if initial_state_calls > 8:
                raise AssertionError("ninth trajectory inspected initial_state")
            assert original_initial_state is not None
            return original_initial_state(task)

        def guarded_plan_draw(source: LazyNormalSource, **kwargs: object) -> object:
            nonlocal plan_calls
            plan_calls += 1
            if plan_calls > 8 * TASK.max_steps:
                raise AssertionError("ninth trajectory touched perturbation source")
            return original_plan_draw(source, **kwargs)

        with (
            patch.object(
                CountdownTask,
                "initial_state",
                new=property(guarded_initial_state),
            ),
            patch.object(LazyNormalSource, "plan_draw", new=guarded_plan_draw),
        ):
            result = run_countdown_track_a_search(
                TASK,
                proposal=HEURISTIC,
                method=method,
                budget_profile=profile,
                exploration_seed=7168,
            )

        self.assertEqual(result.summary["terminal_count"], 8)
        self.assertEqual(initial_state_calls, 8)
        self.assertEqual(plan_calls, 8 * TASK.max_steps)
        self.assertEqual(result.summary["stop_blocked_axes"], ["verifier_calls"])

    def test_search_digest_is_independent_of_python_hash_seed(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        code = """
from qmc_bmgs.benchmarks.countdown import CountdownTask
from qmc_bmgs.substrate.budget import TRACK_A_WORK_AXES, TrackAWorkBudget
from qmc_bmgs.substrate.countdown_search import (
    TrackABudgetProfile, TrackAMethodSpec, run_countdown_track_a_search,
)
from qmc_bmgs.substrate.proposals import TrackAProposalSpec
values = {axis: 20000 for axis in TRACK_A_WORK_AXES}
values[\"verifier_calls\"] = 1
results = [
    run_countdown_track_a_search(
        CountdownTask((1, 2, 3, 4, 5, 6), 720),
        proposal=TrackAProposalSpec(\"greedy_rollout_target_error/v1\"),
        method=method,
        budget_profile=TrackABudgetProfile(
            \"hash_seed_test\", \"verifier_calls\", TrackAWorkBudget(**values)
        ),
        exploration_seed=seed,
    )
    for method, seed in (
        (TrackAMethodSpec.puct(), 0),
        (TrackAMethodSpec.dimension_normalized_thompson(\"iid\"), 7168),
    )
]
print(\"|\".join(result.record[\"deterministic_digest\"] for result in results))
"""
        digests = []
        for seed in ("0", "1", "777"):
            environment = dict(os.environ)
            environment["PYTHONHASHSEED"] = seed
            environment["PYTHONPATH"] = str(repository / "src")
            digests.append(
                subprocess.check_output(
                    [sys.executable, "-c", code],
                    cwd=repository,
                    env=environment,
                    text=True,
                ).strip()
            )
        self.assertEqual(len(set(digests)), 1)


if __name__ == "__main__":
    unittest.main()
