"""Public-fixture qualification; no generated or development-study task data."""

from __future__ import annotations

import copy
import importlib.util
from itertools import product
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from qmc_bmgs.substrate.trace import (
    canonical_trace_bytes,
    sha256_json,
    TraceValidationError,
    validate_trace_bytes,
)


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/qualify_feedback_budget.py"
SPEC = importlib.util.spec_from_file_location(
    "feedback_budget_qualification_tested", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
QUALIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(QUALIFY)

INVALID = (ValueError, TypeError, TraceValidationError)
SEEDS = (8192, 8193, 8194, 8195)
AXES = (
    "proposal_state_evaluations",
    "proposal_action_scores",
    "legal_action_scores",
    "generated_perturbation_coordinates",
    "edge_selections",
    "transitions",
    "verifier_calls",
)


def _summary(record):
    return record["events"][-1]["payload"]["summary"]


def _rehash(record):
    """Make a forged summary structurally canonical without changing its claim."""
    previous = "0" * 64
    for event in record["events"]:
        event["previous_event_digest"] = previous
        event["event_digest"] = sha256_json(
            {key: value for key, value in event.items() if key != "event_digest"}
        )
        previous = event["event_digest"]
    record["final_event_digest"] = previous
    record["deterministic_digest"] = sha256_json(
        {key: value for key, value in record.items() if key != "deterministic_digest"}
    )


class FeedbackBudgetPublicConfigurationTests(unittest.TestCase):
    def test_common_profiles_change_only_legal_action_scores(self):
        expected = (172, 573, 256, 572, 171, 171, 35)
        low = QUALIFY.profile(256)
        high = QUALIFY.profile(512)
        self.assertEqual(tuple(low.budget.to_dict()[axis] for axis in AXES), expected)
        high_caps = high.budget.to_dict()
        self.assertEqual(high_caps.pop("legal_action_scores"), 512)
        low_caps = low.budget.to_dict()
        low_caps.pop("legal_action_scores")
        self.assertEqual(low_caps, high_caps)
        self.assertEqual(low.primary_axis, "legal_action_scores")
        self.assertEqual(high.primary_axis, low.primary_axis)
        self.assertEqual(low.profile_id, "feedback_budget_score256_common512_v1")
        self.assertEqual(high.profile_id, "feedback_budget_score512_common512_v1")

    def test_legacy_profile_remains_distinct_with_its_original_guards(self):
        legacy = QUALIFY.profile(256, legacy=True)
        self.assertEqual(
            tuple(legacy.budget.to_dict()[axis] for axis in AXES),
            (87, 317, 256, 316, 86, 86, 18),
        )
        self.assertNotEqual(legacy.profile_id, QUALIFY.profile(256).profile_id)
        with self.assertRaises(INVALID):
            QUALIFY.profile(512, legacy=True)

    def test_profile_and_method_do_not_accept_numeric_aliases_or_extra_values(self):
        for budget in (True, False, 256.0, "256", 128, 1024, None):
            with self.subTest(budget=budget), self.assertRaises(INVALID):
                QUALIFY.profile(budget)
        for scale in (True, False, 16.0, "16", 1, 32, None):
            with self.subTest(scale=scale), self.assertRaises(INVALID):
                QUALIFY.method(scale)

    def test_method_difference_is_only_frozen_terminal_feedback_scale(self):
        zero = QUALIFY.method(0).to_dict()
        dense = QUALIFY.method(16).to_dict()
        self.assertEqual(zero.pop("terminal_value_scale"), 0)
        self.assertEqual(dense.pop("terminal_value_scale"), 16)
        self.assertEqual(zero, dense)
        self.assertEqual(zero["selected_source"], "iid")
        self.assertEqual(zero["prior_bonus"], 1.0)
        self.assertEqual(zero["posterior_sd_scale"], 1.0)
        self.assertEqual(zero["greedy_anchor_trajectory_count"], 0)

    def test_arguments_pin_public_task_and_reject_unplanned_seeds(self):
        for budget, scale, seed in product((256, 512), (0, 16), SEEDS):
            args = QUALIFY.arguments(budget, scale, seed)
            self.assertEqual(args["task"].inputs, (1, 2, 3, 4, 5, 6))
            self.assertEqual(args["task"].target, 720)
            self.assertEqual(args["exploration_seed"], seed)
            self.assertEqual(args["budget_profile"], QUALIFY.profile(budget))
            self.assertEqual(args["method"], QUALIFY.method(scale))
        for seed in (True, 8192.0, "8192", 8191, 8196, None):
            with self.subTest(seed=seed), self.assertRaises(INVALID):
                QUALIFY.arguments(256, 0, seed)

    def test_manifest_freezes_all_public_source_and_task_exclusions_without_search(
        self,
    ):
        with (
            patch.object(
                QUALIFY,
                "run_countdown_track_a_search",
                side_effect=AssertionError("search"),
            ),
            patch.object(
                QUALIFY.core,
                "reproduce_anchor_qualification",
                side_effect=AssertionError("anchor search"),
            ),
        ):
            manifest = QUALIFY.public_manifest()
        tasks = [manifest["qualification_task"], *manifest["full_shape_tasks"]]
        self.assertEqual(len(tasks), 13)
        self.assertEqual(
            manifest["exclude_task_fingerprints"],
            sorted({task["task_fingerprint"] for task in tasks}),
        )
        self.assertEqual(len(manifest["exclude_task_fingerprints"]), 13)
        self.assertEqual(
            manifest["exclude_source_multiset_fingerprints"],
            sorted({task["source_multiset_fingerprint"] for task in tasks}),
        )
        self.assertEqual(len(manifest["exclude_source_multiset_fingerprints"]), 1)
        self.assertEqual(len(manifest["qualification_schedule"]), 24)
        self.assertEqual(manifest["full_shape_planned_cell_count"], 192)
        self.assertIs(manifest["development_execution_authorized"], False)


class FeedbackBudgetPublicTraceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.receipts = QUALIFY.run_matrix()
        cls.records = {
            (row["budget"], row["scale"], row["seed"], row["legacy"]): row[
                "search_record"
            ]
            for row in cls.rows
        }

    def record(self, budget=256, scale=16, seed=8192, legacy=False):
        return copy.deepcopy(self.records[budget, scale, seed, legacy])

    def test_every_public_cell_has_real_replay_and_sole_primary_stopping(self):
        self.assertEqual(len(self.rows), 24)
        self.assertEqual(len(self.records), 24)
        for row in self.rows:
            coordinates = {
                name: row[name] for name in ("budget", "scale", "seed", "legacy")
            }
            with self.subTest(**coordinates):
                record = row["search_record"]
                receipt = QUALIFY.validate_record(
                    canonical_trace_bytes(record), **coordinates
                )
                self.assertIsInstance(receipt, dict)
                summary = _summary(record)
                self.assertEqual(summary["stop_reason"], "primary_budget_blocked")
                self.assertEqual(summary["stop_blocked_axes"], ["legal_action_scores"])
                self.assertIs(summary["budget_valid"], True)
                self.assertEqual(summary["non_primary_exhausted_axes"], [])

    def test_all_eight_budget_pairs_preserve_every_accepted_event(self):
        for scale, seed in product((0, 16), SEEDS):
            with self.subTest(scale=scale, seed=seed):
                low = self.record(256, scale, seed)
                high = self.record(512, scale, seed)
                receipt = QUALIFY.compare_prefix(
                    canonical_trace_bytes(low),
                    canonical_trace_bytes(high),
                    scale,
                    seed,
                )
                self.assertIsInstance(receipt, dict)
                self.assertEqual(
                    low["events"][:-1], high["events"][: len(low["events"]) - 1]
                )
                self.assertGreaterEqual(
                    _summary(high)["terminal_count"],
                    _summary(low)["terminal_count"] + 1,
                )
                self.assertGreaterEqual(_summary(high)["terminal_count"], 3)
                self.assertNotEqual(low["run_identity"], high["run_identity"])

    def test_guard_relaxation_preserves_all_eight_legacy_accepted_histories(self):
        for scale, seed in product((0, 16), SEEDS):
            with self.subTest(scale=scale, seed=seed):
                legacy = self.record(256, scale, seed, True)
                common = self.record(256, scale, seed)
                QUALIFY.compare_prefix(
                    canonical_trace_bytes(legacy),
                    canonical_trace_bytes(common),
                    scale,
                    seed,
                    legacy=True,
                )
                self.assertEqual(legacy["events"][:-1], common["events"][:-1])

    def test_independent_analyzer_reproduces_complete_public_receipt(self):
        self.assertEqual(
            QUALIFY.analyze_matrix(copy.deepcopy(self.rows)), self.receipts
        )
        self.assertEqual(self.receipts["status"], "PUBLIC_QUALIFICATION_PASS")
        self.assertEqual(self.receipts["two_stage_replayed_trace_count"], 32)
        self.assertEqual(len(self.receipts["budget_prefix_checks"]), 8)
        self.assertEqual(len(self.receipts["legacy_guard_checks"]), 8)
        self.assertEqual(self.receipts["anchor_trace_count"], 8)
        self.assertEqual(self.receipts["development_cells_executed"], 0)
        self.assertIs(self.receipts["development_execution_authorized"], False)
        self.assertIs(self.receipts["full_shape_192_executed"], False)
        self.assertEqual(self.receipts["provider_calls"], 0)

    def test_missing_duplicate_reordered_and_extra_cells_are_rejected(self):
        variants = {
            "missing": self.rows[:-1],
            "extra": self.rows + self.rows[:1],
            "duplicate": self.rows[:-1] + self.rows[:1],
            "reordered": [self.rows[1], self.rows[0], *self.rows[2:]],
        }
        for case, rows in variants.items():
            with (
                self.subTest(case=case),
                patch.object(
                    QUALIFY,
                    "validate_record",
                    side_effect=AssertionError("early replay"),
                ),
                self.assertRaises(INVALID),
            ):
                QUALIFY.analyze_matrix(copy.deepcopy(rows))

    def test_row_identity_aliases_and_extra_fields_fail_before_replay(self):
        mutations = (
            ("budget", 256.0),
            ("scale", False),
            ("seed", "8192"),
            ("legacy", 0),
            ("task", {"inputs": [2, 3, 4, 5, 6, 7], "target": 720}),
        )
        for field, value in mutations:
            rows = copy.deepcopy(self.rows)
            rows[0][field] = value
            with (
                self.subTest(field=field),
                patch.object(
                    QUALIFY,
                    "validate_record",
                    side_effect=AssertionError("early replay"),
                ),
                self.assertRaises(INVALID),
            ):
                QUALIFY.analyze_matrix(rows)

    def test_canonical_bytes_and_expected_identity_are_required(self):
        record = self.record()
        raw = canonical_trace_bytes(record)
        for bad in (raw + b"\n", json.dumps(record, indent=2).encode(), raw[:-1]):
            with self.subTest(length=len(bad)), self.assertRaises(INVALID):
                QUALIFY.validate_record(bad, 256, 16, 8192)
        for budget, scale, seed, legacy in (
            (512, 16, 8192, False),
            (256, 0, 8192, False),
            (256, 16, 8193, False),
            (256, 16, 8192, True),
        ):
            with self.subTest(budget=budget, scale=scale, seed=seed, legacy=legacy):
                with self.assertRaises(INVALID):
                    QUALIFY.validate_record(raw, budget, scale, seed, legacy=legacy)

    def test_changed_accepted_payload_is_rejected_by_actual_validation(self):
        record = self.record()
        record["events"][0]["payload"]["invented_field"] = 1
        with self.assertRaises(INVALID):
            QUALIFY.validate_record(canonical_trace_bytes(record), 256, 16, 8192)

    def test_rehashed_summary_cannot_replace_fresh_stage_two_replay(self):
        record = self.record()
        summary = _summary(record)
        summary["success_any"] = not summary["success_any"]
        _rehash(record)
        raw = canonical_trace_bytes(record)
        self.assertEqual(validate_trace_bytes(raw), record)
        with self.assertRaisesRegex(TraceValidationError, "stage 2.*byte-identical"):
            QUALIFY.validate_record(raw, 256, 16, 8192)

    def test_event_projection_removes_only_one_final_summary(self):
        record = self.record()
        projected = QUALIFY.accepted_events(record)
        self.assertEqual(projected, record["events"][:-1])
        self.assertEqual(projected[0], record["events"][0])
        self.assertTrue(all("event_digest" in event for event in projected))
        self.assertTrue(all("previous_event_digest" in event for event in projected))
        for events in ([], record["events"][:-1], record["events"] * 2):
            bad = copy.deepcopy(record)
            bad["events"] = events
            with self.subTest(length=len(events)), self.assertRaises(INVALID):
                QUALIFY.accepted_events(bad)

    def test_semantic_budget_flags_cannot_hide_secondary_block_or_exhaustion(self):
        cases = (
            ("stop_reason", "method_complete"),
            ("stop_reason", "guard_budget_blocked"),
            ("stop_blocked_axes", []),
            ("stop_blocked_axes", ["legal_action_scores", "transitions"]),
            ("budget_valid", 1),
            ("budget_valid", False),
            ("non_primary_exhausted_axes", ["verifier_calls"]),
        )
        for field, value in cases:
            record = self.record()
            _summary(record)[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(INVALID):
                QUALIFY.validate_budget(record, QUALIFY.profile(256))

    def test_attempted_work_is_recomputed_instead_of_trusting_stop_label(self):
        for axis in AXES:
            record = self.record()
            ledger = record["ledger_snapshot"]
            attempted = _summary(record)["stop_attempted_charge"]
            attempted[axis] = (
                ledger["remaining"][axis]
                if axis == "legal_action_scores"
                else ledger["remaining"][axis] + 1
            )
            with self.subTest(axis=axis), self.assertRaises(INVALID):
                QUALIFY.validate_budget(record, QUALIFY.profile(256))

    def test_zero_headroom_and_primary_overshoot_are_not_valid_stops(self):
        caps = QUALIFY.profile(256).budget.to_dict()
        for axis in AXES:
            record = self.record()
            ledger = record["ledger_snapshot"]
            accepted = caps[axis] + int(axis == "legal_action_scores")
            ledger["usage"][axis] = accepted
            ledger["remaining"][axis] = caps[axis] - accepted
            _summary(record)["ledger_usage"][axis] = accepted
            with self.subTest(axis=axis), self.assertRaises(INVALID):
                QUALIFY.validate_budget(record, QUALIFY.profile(256))

    def test_work_vectors_require_closed_plain_nonnegative_integer_axes(self):
        for field in ("usage", "remaining", "stop_attempted_charge"):
            for defect in ("bool", "negative", "missing", "extra"):
                record = self.record()
                vector = (
                    _summary(record)[field]
                    if field == "stop_attempted_charge"
                    else record["ledger_snapshot"][field]
                )
                if defect == "missing":
                    del vector["transitions"]
                elif defect == "extra":
                    vector["unknown_work"] = 0
                else:
                    vector["transitions"] = True if defect == "bool" else -1
                with (
                    self.subTest(field=field, defect=defect),
                    self.assertRaises(INVALID),
                ):
                    QUALIFY.validate_budget(record, QUALIFY.profile(256))

    def test_terminal_count_must_match_events_and_structural_minimum(self):
        for budget, minimum in ((256, 1), (512, 3)):
            record = self.record(budget)
            summary = _summary(record)
            summary["terminal_count"] += 1
            with (
                self.subTest(budget=budget, defect="count"),
                self.assertRaises(INVALID),
            ):
                QUALIFY.validate_budget(record, QUALIFY.profile(budget))
            record = self.record(budget)
            terminal_indices = [
                index
                for index, event in enumerate(record["events"])
                if event["kind"] == "terminal_verified"
            ]
            remove = set(terminal_indices[minimum - 1 :])
            record["events"] = [
                event
                for index, event in enumerate(record["events"])
                if index not in remove
            ]
            _summary(record)["terminal_count"] = minimum - 1
            with (
                self.subTest(budget=budget, defect="minimum"),
                self.assertRaises(INVALID),
            ):
                QUALIFY.validate_budget(record, QUALIFY.profile(budget))

    def test_prefix_comparison_preserves_hashes_indices_and_full_payload(self):
        for field, value in (
            ("event_digest", "0" * 64),
            ("previous_event_digest", "1" * 64),
            ("index", 900),
            ("payload", {"redacted": True}),
        ):
            low, high = self.record(), self.record(512)
            high["events"][0][field] = value
            with self.subTest(field=field), self.assertRaises(INVALID):
                QUALIFY._compare_validated(low, high, 16, 8192, legacy=False)

    def test_longer_event_history_alone_does_not_prove_extra_completion(self):
        low, high = self.record(), self.record(512)
        boundary = len(low["events"]) - 1
        prefix = high["events"][:boundary]
        continuation = [
            event
            for event in high["events"][boundary:-1]
            if event["kind"] != "terminal_verified"
        ]
        high["events"] = prefix + continuation + high["events"][-1:]
        self.assertGreater(len(high["events"]), len(low["events"]))
        with self.assertRaises(INVALID):
            QUALIFY._compare_validated(low, high, 16, 8192, legacy=False)

    def test_extension_must_complete_the_actual_current_trajectory(self):
        low, high = self.record(), self.record(512)
        boundary = len(low["events"]) - 1
        for event in high["events"][boundary:-1]:
            if event["kind"] == "terminal_verified":
                event["payload"]["trajectory_index"] += 100
        with self.assertRaises(INVALID):
            QUALIFY._compare_validated(low, high, 16, 8192, legacy=False)

    def test_replay_failure_cannot_be_replaced_by_a_pass_receipt(self):
        with (
            patch.object(
                QUALIFY,
                "replay_countdown_track_a_search_bytes",
                side_effect=TraceValidationError(
                    "synthetic independent replay failure"
                ),
            ),
            self.assertRaisesRegex(TraceValidationError, "independent replay failure"),
        ):
            QUALIFY.validate_record(canonical_trace_bytes(self.record()), 256, 16, 8192)
        with (
            patch.object(
                QUALIFY,
                "replay_countdown_track_a_search_bytes",
                return_value=b"different canonical replay bytes",
            ),
            self.assertRaisesRegex(ValueError, "replay bytes differ"),
        ):
            QUALIFY.validate_record(canonical_trace_bytes(self.record()), 256, 16, 8192)


if __name__ == "__main__":
    unittest.main()
