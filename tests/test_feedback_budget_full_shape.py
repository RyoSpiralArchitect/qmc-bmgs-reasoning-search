"""Fixed public 192-cell identities and pre-replay rejection boundaries.

Synthetic envelopes test collective closure without claiming replay evidence.
One actual public search tests that valid hashes cannot replace generative replay.
The separate CLI integration exercises the complete real public fixture.
"""

from __future__ import annotations

import copy
import importlib.util
from itertools import product
from pathlib import Path
import unittest
from unittest.mock import patch

from qmc_bmgs.benchmarks.countdown import CountdownTask
from qmc_bmgs.substrate.trace import (
    TraceValidationError,
    canonical_trace_bytes,
    sha256_json,
    validate_trace_bytes,
)


SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts/run_feedback_budget_full_shape.py"
)
SPEC = importlib.util.spec_from_file_location(
    "feedback_budget_full_shape_tested", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
FULL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FULL)
DOMAIN = "qmc-bmgs-feedback-budget-nondiagnostic-full-shape/v1"
INVALID = (ValueError, TypeError, KeyError, TraceValidationError)


def rehash(value):
    return FULL.q.core.with_digest(
        {key: item for key, item in value.items() if key != "deterministic_digest"}
    )


def rehash_trace(record):
    """Recompute all hash links while retaining the deliberately false claim."""
    previous = "0" * 64
    for event in record["events"]:
        event["previous_event_digest"] = previous
        event["event_digest"] = sha256_json(
            {key: value for key, value in event.items() if key != "event_digest"}
        )
        previous = event["event_digest"]
    record["final_event_digest"] = previous
    return rehash(record)


def envelope(cell):
    """A legal outer identity with intentionally synthetic, unreplayable content."""
    return rehash(
        {
            "schema_version": DOMAIN + "/record",
            **copy.deepcopy(cell),
            "search_record": {
                "run_identity": FULL.q.build_search_run_identity(**FULL.arguments(cell))
            },
        }
    )


class FullShapePublicIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = FULL.fixture_manifest()
        cls.cells = cls.manifest["cells"]

    def test_manifest_is_fixed_public_identity_material_without_search(self):
        with patch.object(
            FULL.q,
            "run_countdown_track_a_search",
            side_effect=AssertionError("manifest must not search"),
        ):
            manifest = FULL.fixture_manifest()
        self.assertEqual(manifest, self.manifest)
        self.assertEqual(FULL.DOMAIN, DOMAIN)
        self.assertNotEqual(FULL.DOMAIN, FULL.q.DOMAIN)
        self.assertEqual(
            manifest["tasks"],
            [
                CountdownTask((1, 2, 3, 4, 5, 6), target).to_dict()
                for target in range(1, 13)
            ],
        )
        self.assertEqual(len(self.cells), 192)
        self.assertEqual(len({cell["cell_id"] for cell in self.cells}), 192)
        self.assertEqual([cell["cell_index"] for cell in self.cells], list(range(192)))
        for cell in self.cells:
            self.assertEqual(cell["cell_id"], sha256_json(cell["cell_key"]))
        self.assertEqual(manifest["schedule_digest"], sha256_json(self.cells))
        self.assertEqual(manifest["cell_count"], 192)
        self.assertEqual(manifest["task_count"], 12)
        self.assertEqual(manifest["budget_prefix_check_count"], 96)
        self.assertIs(manifest["development_execution_authorized"], False)
        FULL.q.core.require_digest(manifest)

    def test_every_coordinate_matches_the_frozen_task_budget_scale_seed_order(self):
        expected = list(
            product(range(12), (256, 512), (0, 16), (8192, 8193, 8194, 8195))
        )
        actual = [
            tuple(
                cell["cell_key"][key]
                for key in ("task_slot", "budget", "scale", "seed")
            )
            for cell in self.cells
        ]
        self.assertEqual(actual, expected)
        for cell, (slot, budget, scale, seed) in zip(self.cells, expected):
            with self.subTest(slot=slot, budget=budget, scale=scale, seed=seed):
                key = cell["cell_key"]
                task = CountdownTask((1, 2, 3, 4, 5, 6), slot + 1)
                self.assertEqual(key["task_fingerprint"], task.task_fingerprint)
                self.assertEqual(
                    key["source_multiset_fingerprint"], task.source_multiset_fingerprint
                )
                args = FULL.arguments(cell)
                self.assertEqual(args["task"], task)
                self.assertEqual(args["budget_profile"], FULL.q.profile(budget))
                self.assertEqual(args["method"], FULL.q.method(scale))
                self.assertEqual(args["proposal"], FULL.q.PROPOSAL)
                self.assertEqual(args["exploration_seed"], seed)
                self.assertEqual(
                    key["budget_spec_digest"],
                    sha256_json(FULL.q.profile(budget).to_dict()),
                )
                self.assertEqual(
                    key["method_spec_digest"],
                    sha256_json(FULL.q.method(scale).to_dict()),
                )
                self.assertEqual(
                    key["proposal_spec_digest"], sha256_json(FULL.q.PROPOSAL.to_dict())
                )

    def test_all_twelve_fixture_tasks_are_already_in_public_exclusion_manifest(self):
        public = FULL.q.public_manifest()
        self.assertEqual(self.manifest["tasks"], public["full_shape_tasks"])
        for task in self.manifest["tasks"]:
            self.assertIn(task["task_fingerprint"], public["exclude_task_fingerprints"])
            self.assertIn(
                task["source_multiset_fingerprint"],
                public["exclude_source_multiset_fingerprints"],
            )

    def test_paired_budgets_change_only_budget_identity_in_search_arguments(self):
        for slot, scale, seed in product(range(12), (0, 16), (8192, 8193, 8194, 8195)):
            selected = [
                FULL.arguments(cell)
                for cell in self.cells
                if all(
                    cell["cell_key"][key] == value
                    for key, value in (
                        ("task_slot", slot),
                        ("scale", scale),
                        ("seed", seed),
                    )
                )
            ]
            self.assertEqual(len(selected), 2)
            low, high = selected
            self.assertEqual(low.pop("budget_profile"), FULL.q.profile(256))
            self.assertEqual(high.pop("budget_profile"), FULL.q.profile(512))
            self.assertEqual(low, high)


class FullShapeCollectiveClosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cells = FULL.fixture_manifest()["cells"]
        cls.rows = [envelope(cell) for cell in cls.cells]

    def rejects_before_replay(self, rows):
        with (
            patch.object(
                FULL.q,
                "replay_countdown_track_a_search_bytes",
                side_effect=AssertionError(
                    "replay before complete identity validation"
                ),
            ) as replay,
            self.assertRaises(INVALID),
        ):
            FULL.analyze_rows(rows)
        replay.assert_not_called()

    def test_all_192_outer_identities_are_accepted_without_claiming_trace_validity(
        self,
    ):
        with patch.object(
            FULL.q,
            "replay_countdown_track_a_search_bytes",
            side_effect=AssertionError("envelope validation must not replay"),
        ) as replay:
            self.assertIsNone(FULL.validate_envelopes(copy.deepcopy(self.rows)))
        replay.assert_not_called()

    def test_missing_extra_duplicate_and_reordered_cells_are_rejected(self):
        variants = {
            "missing": self.rows[:-1],
            "extra": self.rows + self.rows[:1],
            "duplicate": self.rows[:-1] + self.rows[:1],
            "swapped": [self.rows[1], self.rows[0], *self.rows[2:]],
            "tuple": tuple(self.rows),
        }
        for name, rows in variants.items():
            with self.subTest(name=name):
                self.rejects_before_replay(copy.deepcopy(rows))

    def test_24_qualification_rows_cannot_be_presented_as_a_full_fixture(self):
        qualification = [
            {**cell, "search_record": {"synthetic": True}} for cell in FULL.q.schedule()
        ]
        self.assertEqual(len(qualification), 24)
        self.rejects_before_replay(qualification)
        self.rejects_before_replay(qualification * 8)

    def test_hash_valid_row_schema_fields_and_ids_cannot_change_the_schedule(self):
        mutations = (
            ("schema_version", FULL.q.DOMAIN + "/record"),
            ("cell_index", False),
            ("cell_index", 0.0),
            ("cell_id", "0" * 64),
            ("extra", "development authority"),
        )
        for field, value in mutations:
            rows = copy.deepcopy(self.rows)
            rows[0][field] = value
            rows[0] = rehash(rows[0])
            with self.subTest(field=field, value=value):
                self.rejects_before_replay(rows)

    def test_plain_integer_cell_coordinates_cannot_be_numeric_aliases(self):
        mutations = (
            ("task_slot", False),
            ("task_slot", 0.0),
            ("budget", 256.0),
            ("scale", False),
            ("scale", 0.0),
            ("seed", 8192.0),
            ("seed", "8192"),
        )
        for field, value in mutations:
            rows = copy.deepcopy(self.rows)
            rows[0]["cell_key"][field] = value
            rows[0]["cell_id"] = sha256_json(rows[0]["cell_key"])
            rows[0] = rehash(rows[0])
            with self.subTest(field=field, value=value):
                self.rejects_before_replay(rows)

    def test_foreign_and_unplanned_cell_factors_are_rejected_even_when_rehashed(self):
        mutations = (
            ("task_slot", 12),
            ("budget", 128),
            ("scale", 32),
            ("seed", 8196),
            ("task_fingerprint", "0" * 64),
            ("source_multiset_fingerprint", "0" * 64),
            ("budget_spec_digest", "0" * 64),
            ("method_spec_digest", "0" * 64),
            ("proposal_spec_digest", "0" * 64),
            ("legacy", False),
        )
        for field, value in mutations:
            rows = copy.deepcopy(self.rows)
            rows[0]["cell_key"][field] = value
            rows[0]["cell_id"] = sha256_json(rows[0]["cell_key"])
            rows[0] = rehash(rows[0])
            with self.subTest(field=field):
                self.rejects_before_replay(rows)

    def test_invalid_last_identity_is_rejected_before_replaying_the_first_row(self):
        rows = copy.deepcopy(self.rows)
        rows[-1]["search_record"]["run_identity"] = copy.deepcopy(
            rows[0]["search_record"]["run_identity"]
        )
        rows[-1] = rehash(rows[-1])
        self.rejects_before_replay(rows)

    def test_foreign_search_task_cannot_be_smuggled_under_valid_outer_coordinates(self):
        rows = copy.deepcopy(self.rows)
        args = FULL.arguments(self.cells[0])
        args["task"] = CountdownTask((2, 3, 4, 5, 6, 7), 720)
        rows[0]["search_record"]["run_identity"] = FULL.q.build_search_run_identity(
            **args
        )
        rows[0] = rehash(rows[0])
        self.rejects_before_replay(rows)

    def test_missing_and_non_object_search_records_are_rejected_before_replay(self):
        for value in (None, [], True, {"synthetic": True}):
            rows = copy.deepcopy(self.rows)
            rows[-1]["search_record"] = value
            rows[-1] = rehash(rows[-1])
            with self.subTest(value=value):
                self.rejects_before_replay(rows)

    def test_mutation_without_rehash_is_rejected_before_replay(self):
        rows = copy.deepcopy(self.rows)
        rows[-1]["search_record"]["unbound"] = "changed"
        self.rejects_before_replay(rows)


class FullShapeActualReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cells = FULL.fixture_manifest()["cells"]
        cls.real_row = FULL.build_record(cls.cells[0])
        cls.high_row = FULL.build_record(cls.cells[8])

    def test_build_record_binds_one_real_public_search_to_the_exact_cell(self):
        row = self.real_row
        self.assertEqual(
            set(row),
            {
                "schema_version",
                "cell_index",
                "cell_id",
                "cell_key",
                "search_record",
                "deterministic_digest",
            },
        )
        self.assertEqual(row["schema_version"], DOMAIN + "/record")
        self.assertEqual(
            {key: row[key] for key in ("cell_index", "cell_id", "cell_key")},
            self.cells[0],
        )
        FULL.q.core.require_digest(row)
        raw = canonical_trace_bytes(row["search_record"])
        args = FULL.arguments(self.cells[0])
        replayed = FULL.q.replay_countdown_track_a_search_bytes(
            raw,
            **args,
            expected_run_identity_digest=sha256_json(
                FULL.q.build_search_run_identity(**args)
            ),
        )
        self.assertEqual(replayed, raw)
        evidence = FULL.q.validate_budget(row["search_record"], FULL.q.profile(256))
        self.assertEqual(evidence["stop_blocked_axes"], ["legal_action_scores"])
        self.assertIs(evidence["zero_overshoot"], True)
        self.assertIs(evidence["secondary_guards_nonbinding"], True)

    def test_hash_valid_forged_search_summary_fails_real_stage_two_replay(self):
        rows = [envelope(cell) for cell in self.cells]
        rows[0] = copy.deepcopy(self.real_row)
        record = rows[0]["search_record"]
        summary = record["events"][-1]["payload"]["summary"]
        summary["success_any"] = not summary["success_any"]
        rows[0]["search_record"] = rehash_trace(record)
        rows[0] = rehash(rows[0])
        raw = canonical_trace_bytes(rows[0]["search_record"])
        self.assertEqual(validate_trace_bytes(raw), rows[0]["search_record"])
        FULL.validate_envelopes(rows)
        with self.assertRaisesRegex(TraceValidationError, "stage 2.*byte-identical"):
            FULL.analyze_rows(rows)

    def test_one_actual_pair_preserves_exact_events_and_completes_the_next_trajectory(
        self,
    ):
        low = self.real_row["search_record"]
        high = self.high_row["search_record"]
        check = FULL.compare_pair(low, high, self.cells[0])
        self.assertEqual(check["status"], "EXACT_PREFIX_AND_COMPLETION_PASS")
        self.assertEqual(check["task_slot"], 0)
        self.assertEqual(
            check["task_fingerprint"],
            CountdownTask((1, 2, 3, 4, 5, 6), 1).task_fingerprint,
        )
        self.assertEqual(check["low_cell_id"], self.cells[0]["cell_id"])
        self.assertEqual(check["prefix_digest"], sha256_json(low["events"][:-1]))
        self.assertEqual(low["events"][:-1], high["events"][: len(low["events"]) - 1])
        self.assertGreaterEqual(
            check["high_terminal_count"], check["low_terminal_count"] + 1
        )
        self.assertGreaterEqual(check["high_terminal_count"], 3)
        self.assertEqual(
            check["added_terminal_count"],
            check["high_terminal_count"] - check["low_terminal_count"],
        )
        self.assertIs(check["current_next_completed_first"], True)
        self.assertIs(check["exact_success_nondecreasing"], True)
        self.assertIs(check["minimum_error_nonincreasing"], True)

    def test_prefix_comparison_keeps_hash_links_indices_and_complete_event_payloads(
        self,
    ):
        for field, value in (
            ("event_digest", "0" * 64),
            ("previous_event_digest", "1" * 64),
            ("index", 900),
            ("payload", {"discarded_evidence": True}),
        ):
            high = copy.deepcopy(self.high_row["search_record"])
            high["events"][0][field] = value
            with self.subTest(field=field), self.assertRaises(INVALID):
                FULL.compare_pair(self.real_row["search_record"], high, self.cells[0])


if __name__ == "__main__":
    unittest.main()
