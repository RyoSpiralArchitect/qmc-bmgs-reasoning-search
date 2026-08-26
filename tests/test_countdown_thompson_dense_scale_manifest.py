from __future__ import annotations

import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from qmc_bmgs.experiments import countdown_thompson_dense_scale_manifest as module
from qmc_bmgs.substrate import countdown_search, proposals
from qmc_bmgs.substrate.countdown_search import (
    DENSE_TERMINAL_VALUE_SCALES,
    SCALED_DENSE_TERMINAL_METHOD_SPEC_SCHEMA_VERSION,
    SCALED_RECIPROCAL_ABSOLUTE_ERROR_TERMINAL_VALUE_RULE_ID,
)
from qmc_bmgs.substrate.trace import sha256_json


class DenseScaleManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repository_root = Path(__file__).resolve().parents[1]
        with (
            patch.object(
                countdown_search,
                "run_countdown_track_a_search",
                side_effect=AssertionError("manifest must not execute search"),
            ),
            patch.object(
                proposals,
                "evaluate_track_a_proposal",
                side_effect=AssertionError("manifest must not materialize proposals"),
            ),
        ):
            cls.payload = module.build_countdown_thompson_dense_scale_payload(
                repository_root=cls.repository_root
            )

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix="qmc-dense-scale-manifest-tests-"
        )
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_bundle(self, payload: dict[str, object] | None = None) -> Path:
        destination = self.root / "bundle"
        destination.mkdir()
        (destination / module.BUNDLE_FILENAME).write_bytes(
            module._canonical_bytes(payload or self.payload)
        )
        return destination

    def test_build_is_outcome_blind_and_source_disjoint(self) -> None:
        payload = self.payload
        self.assertEqual(payload["bundle_id"], module.BUNDLE_ID)
        self.assertTrue(payload["sealed_before_development_search_outcomes"])
        self.assertEqual(
            payload["materialization_contract"],
            {
                "persisted_perturbation_point_count": 0,
                "persisted_proposal_row_count": 0,
                "persisted_provider_output_count": 0,
                "persisted_search_record_count": 0,
                "precomputed_perturbation_bank_bytes": 0,
                "provider_calls": 0,
            },
        )
        cohort = payload["cohort"]
        self.assertEqual(cohort["task_count"], 12)
        self.assertEqual(cohort["generation_call"]["seed"], 26082601)
        self.assertEqual(cohort["persisted_solution_witness_count"], 0)
        exclusions = cohort["exclusion_identity"]
        self.assertEqual(
            exclusions["cohort_order"],
            [
                "historical_2",
                "canary_12",
                "locked_128",
                "diagnostic_12",
            ],
        )
        self.assertEqual(exclusions["task_fingerprint_count"], 154)
        self.assertEqual(exclusions["source_multiset_fingerprint_count"], 154)
        task_fingerprints = {row["task_fingerprint"] for row in cohort["tasks"]}
        source_fingerprints = {
            row["source_multiset_fingerprint"] for row in cohort["tasks"]
        }
        self.assertEqual(len(task_fingerprints), 12)
        self.assertEqual(len(source_fingerprints), 12)
        self.assertFalse(task_fingerprints & set(exclusions["task_fingerprints"]))
        self.assertFalse(
            source_fingerprints & set(exclusions["source_multiset_fingerprints"])
        )
        module._assert_no_forbidden_material(payload)

    def test_method_family_changes_only_the_frozen_scale(self) -> None:
        methods = self.payload["methods"]
        self.assertEqual(tuple(methods["scale_order"]), DENSE_TERMINAL_VALUE_SCALES)
        self.assertEqual(len(methods["methods"]), 8)
        reference = copy.deepcopy(methods["methods"][0]["spec"])
        for expected_scale, row in zip(DENSE_TERMINAL_VALUE_SCALES, methods["methods"]):
            self.assertEqual(row["terminal_value_scale"], expected_scale)
            spec = row["spec"]
            self.assertEqual(
                spec["schema_version"],
                SCALED_DENSE_TERMINAL_METHOD_SPEC_SCHEMA_VERSION,
            )
            self.assertEqual(
                spec["terminal_value_rule_id"],
                SCALED_RECIPROCAL_ABSOLUTE_ERROR_TERMINAL_VALUE_RULE_ID,
            )
            self.assertEqual(spec["terminal_value_scale"], expected_scale)
            self.assertEqual(spec["greedy_anchor_trajectory_count"], 0)
            comparison = copy.deepcopy(spec)
            comparison["terminal_value_scale"] = 0
            self.assertEqual(comparison, reference)

    def test_schedule_is_exactly_384_cells_in_frozen_order(self) -> None:
        execution = self.payload["execution_matrix"]
        schedule = execution["schedule"]
        self.assertEqual(execution["cell_count"], 384)
        self.assertEqual(len(schedule), 384)
        self.assertEqual(len({row["cell_id"] for row in schedule}), 384)
        self.assertTrue(
            all(row["cell_id"] == sha256_json(row["cell_key"]) for row in schedule)
        )
        observed = [
            (
                row["cell_key"]["task_fingerprint"],
                row["cell_key"]["terminal_value_scale"],
                row["cell_key"]["exploration_seed"],
            )
            for row in schedule
        ]
        expected = [
            (task["task_fingerprint"], scale, seed)
            for task in self.payload["cohort"]["tasks"]
            for scale in DENSE_TERMINAL_VALUE_SCALES
            for seed in module.EXPLORATION_SEEDS
        ]
        self.assertEqual(observed, expected)

    def test_analysis_cannot_jump_directly_to_locked_128(self) -> None:
        analysis = self.payload["analysis"]
        handoff = analysis["development_handoff"]
        self.assertEqual(handoff["minimum_net_exact_success_gain"], 2)
        self.assertEqual(handoff["minimum_new_exact_successes"], 2)
        self.assertEqual(
            handoff["success_status"],
            "READY_TO_PREREGISTER_SOURCE_DISJOINT_CONFIRMATION",
        )
        self.assertEqual(handoff["failure_status"], "STOP_REPAIR_NO_LOCKED_128_RUN")
        self.assertFalse(analysis["claim_boundary"]["locked_128_authority"])

    def test_normal_bundle_verifies_and_payload_property_is_defensive(self) -> None:
        destination = self._write_bundle()
        with patch.object(
            module,
            "build_countdown_thompson_dense_scale_payload",
            return_value=copy.deepcopy(self.payload),
        ):
            verified = module.verify_countdown_thompson_dense_scale_bundle(
                destination,
                repository_root=self.repository_root,
            )
        self.assertEqual(len(verified.cells), 384)
        copy_payload = verified.payload
        copy_payload["bundle_id"] = "mutated"
        self.assertEqual(verified.payload["bundle_id"], module.BUNDLE_ID)

    def test_canonical_tamper_fails_regeneration(self) -> None:
        tampered = copy.deepcopy(self.payload)
        tampered["claim_boundary"] = "mutated"
        core = {
            key: value
            for key, value in tampered.items()
            if key != "deterministic_digest"
        }
        tampered["deterministic_digest"] = sha256_json(core)
        destination = self._write_bundle(tampered)
        with (
            patch.object(
                module,
                "build_countdown_thompson_dense_scale_payload",
                return_value=copy.deepcopy(self.payload),
            ),
            self.assertRaisesRegex(
                module.DenseScaleManifestError,
                "independent deterministic regeneration",
            ),
        ):
            module.verify_countdown_thompson_dense_scale_bundle(
                destination,
                repository_root=self.repository_root,
            )

    def test_bundle_reader_rejects_extra_symlink_and_hardlink_members(self) -> None:
        extra = self._write_bundle()
        (extra / "extra.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(
            module.DenseScaleManifestError, "directory closure"
        ):
            module._read_bundle_bytes(extra)

        symlink_bundle = self.root / "symlink-bundle"
        symlink_bundle.mkdir()
        target = self.root / "target.json"
        target.write_bytes(module._canonical_bytes(self.payload))
        (symlink_bundle / module.BUNDLE_FILENAME).symlink_to(target)
        with self.assertRaises(module.DenseScaleManifestError):
            module._read_bundle_bytes(symlink_bundle)

        hardlink_bundle = self.root / "hardlink-bundle"
        hardlink_bundle.mkdir()
        os.link(target, hardlink_bundle / module.BUNDLE_FILENAME)
        with self.assertRaisesRegex(module.DenseScaleManifestError, "owned file"):
            module._read_bundle_bytes(hardlink_bundle)

    def test_writer_is_exclusive_without_search_execution(self) -> None:
        destination = self.root / "written"
        with patch.object(
            module,
            "build_countdown_thompson_dense_scale_payload",
            return_value=copy.deepcopy(self.payload),
        ):
            module.write_countdown_thompson_dense_scale_bundle(
                destination,
                repository_root=self.repository_root,
            )
            with self.assertRaises(FileExistsError):
                module.write_countdown_thompson_dense_scale_bundle(
                    destination,
                    repository_root=self.repository_root,
                )
        self.assertEqual(
            set(path.name for path in destination.iterdir()),
            {module.BUNDLE_FILENAME},
        )


if __name__ == "__main__":
    unittest.main()
