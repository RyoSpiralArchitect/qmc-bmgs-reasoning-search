from __future__ import annotations

import copy
import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from qmc_bmgs.benchmarks.countdown import CountdownTask
from qmc_bmgs.experiments import countdown_thompson_dense_scale_manifest as module
from qmc_bmgs.substrate.budget import TrackAWorkBudget
from qmc_bmgs.substrate import countdown_search, proposals
from qmc_bmgs.substrate.countdown_search import (
    DENSE_TERMINAL_VALUE_SCALES,
    SCALED_DENSE_TERMINAL_METHOD_SPEC_SCHEMA_VERSION,
    SCALED_RECIPROCAL_ABSOLUTE_ERROR_TERMINAL_VALUE_RULE_ID,
    TrackABudgetProfile,
    TrackAMethodSpec,
    project_track_a_anchor_equivalence_trace,
    replay_countdown_track_a_search_bytes,
    run_countdown_track_a_search,
)
from qmc_bmgs.substrate.proposals import TrackAProposalSpec
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
        anchors = analysis["anchor_equivalence"]
        qualification = anchors["qualification"]
        self.assertEqual(
            anchors["projection_schema_version"],
            countdown_search.ANCHOR_EQUIVALENCE_PROJECTION_SCHEMA_VERSION,
        )
        self.assertEqual(
            anchors["comparison"], "canonical_projection_exact_equality"
        )
        self.assertIn(
            "all_other_ledger_fields_and_components", anchors["preserved"]
        )
        self.assertIn("stop_events", anchors["preserved"])
        self.assertEqual(anchors["development_matrix_authority_trace_count"], 0)
        self.assertEqual(qualification["development_cell_count"], 0)
        self.assertIs(qualification["development_task_access"], False)
        self.assertEqual(qualification["execution_count"], 8)
        self.assertEqual(qualification["raw_trace_persisted_count"], 0)
        self.assertTrue(qualification["required_before_development_result_open"])
        self.assertIs(
            qualification["v2_or_v3_development_execution_authority"], False
        )
        self.assertEqual(
            {row["spec"]["schema_version"] for row in self.payload["methods"]["methods"]},
            {SCALED_DENSE_TERMINAL_METHOD_SPEC_SCHEMA_VERSION},
        )
        self.assertEqual(
            analysis["integer_reductions"]["even_median"],
            "reduce((sorted[n//2-1]+sorted[n//2])/2)",
        )
        handoff = analysis["development_handoff"]
        self.assertEqual(handoff["minimum_net_exact_success_gain"], 2)
        self.assertEqual(handoff["minimum_new_exact_successes"], 2)
        self.assertEqual(
            handoff["success_status"],
            "READY_TO_PREREGISTER_SOURCE_DISJOINT_CONFIRMATION",
        )
        self.assertEqual(handoff["failure_status"], "STOP_REPAIR_NO_LOCKED_128_RUN")
        self.assertFalse(analysis["claim_boundary"]["locked_128_authority"])

    def test_anchor_qualification_receipt_reproduces_without_development_tasks(
        self,
    ) -> None:
        qualification = self.payload["analysis"]["anchor_equivalence"][
            "qualification"
        ]
        task_row = qualification["fixture_task"]
        task = CountdownTask(tuple(task_row["inputs"]), target=task_row["target"])
        proposal_row = qualification["proposal_spec"]
        proposal = TrackAProposalSpec(proposal_row["policy_id"])
        profile_row = qualification["budget_profile"]
        profile = TrackABudgetProfile(
            profile_id=profile_row["profile_id"],
            primary_axis=profile_row["primary_axis"],
            budget=TrackAWorkBudget(**profile_row["budget"]),
            schema_version=profile_row["schema_version"],
        )
        self.assertEqual(task.to_dict(), task_row)
        self.assertEqual(proposal.to_dict(), proposal_row)
        self.assertEqual(profile.to_dict(), profile_row)
        self.assertNotIn(
            task.task_fingerprint,
            {row["task_fingerprint"] for row in self.payload["cohort"]["tasks"]},
        )

        observed_order: list[str] = []
        execution_count = 0
        for receipt in qualification["receipts"]:
            source = receipt["source"]
            anchor_label = receipt["anchor_label"]
            if anchor_label == "binary_terminal_anchor":
                authority_method = TrackAMethodSpec.dimension_normalized_thompson(
                    source
                )
                scaled_method = (
                    TrackAMethodSpec.dimension_normalized_scaled_dense_thompson(
                        source, 0
                    )
                )
            else:
                self.assertEqual(anchor_label, "reciprocal_error_anchor")
                authority_method = (
                    TrackAMethodSpec.dimension_normalized_dense_thompson(source)
                )
                scaled_method = (
                    TrackAMethodSpec.dimension_normalized_scaled_dense_thompson(
                        source, 1
                    )
                )
            self.assertEqual(
                authority_method.to_dict(), receipt["authority_method_spec"]
            )
            self.assertEqual(scaled_method.to_dict(), receipt["scaled_method_spec"])
            self.assertEqual(
                sha256_json(authority_method.to_dict()),
                receipt["authority_method_spec_digest"],
            )
            self.assertEqual(
                sha256_json(scaled_method.to_dict()),
                receipt["scaled_method_spec_digest"],
            )

            traces = []
            for method, digest_key in (
                (authority_method, "expected_authority_trace_sha256"),
                (scaled_method, "expected_scaled_trace_sha256"),
            ):
                result = run_countdown_track_a_search(
                    task,
                    proposal=proposal,
                    method=method,
                    budget_profile=profile,
                    exploration_seed=qualification["exploration_seed"],
                )
                self.assertEqual(
                    replay_countdown_track_a_search_bytes(
                        result.canonical_bytes,
                        task=task,
                        proposal=proposal,
                        method=method,
                        budget_profile=profile,
                        exploration_seed=qualification["exploration_seed"],
                        expected_run_identity_digest=result.run_identity_digest,
                    ),
                    result.canonical_bytes,
                )
                self.assertEqual(
                    hashlib.sha256(result.canonical_bytes).hexdigest(),
                    receipt[digest_key],
                )
                traces.append(
                    project_track_a_anchor_equivalence_trace(
                        result.canonical_bytes,
                        method=method,
                    )
                )
                execution_count += 1
            self.assertEqual(traces[0], traces[1])
            self.assertEqual(
                sha256_json(traces[0]),
                receipt["expected_common_projection_digest"],
            )
            observed_order.append(f"{source}_{anchor_label}")

        self.assertEqual(observed_order, qualification["receipt_order"])
        self.assertEqual(execution_count, qualification["execution_count"])

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

    def test_bundle_reader_uses_nonblocking_open_for_a_raced_fifo(self) -> None:
        destination = self._write_bundle()
        member = destination / module.BUNDLE_FILENAME
        real_listdir = os.listdir
        real_open = os.open

        def rotate_member(directory_fd: int) -> list[str]:
            names = real_listdir(directory_fd)
            member.unlink()
            os.mkfifo(member)
            return names

        def guarded_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
            if path == module.BUNDLE_FILENAME:
                self.assertTrue(flags & os.O_NONBLOCK)
            return real_open(path, flags, *args, **kwargs)  # type: ignore[arg-type]

        with (
            patch.object(module.os, "listdir", side_effect=rotate_member),
            patch.object(module.os, "open", side_effect=guarded_open),
            self.assertRaises(module.DenseScaleManifestError),
        ):
            module._read_bundle_bytes(destination)

    def test_verifier_rejects_byte_identical_bundle_path_rotation(self) -> None:
        destination = self._write_bundle()
        parked = self.root / "parked"

        def rotate_during_regeneration(**_: object) -> dict[str, object]:
            destination.rename(parked)
            destination.mkdir()
            (destination / module.BUNDLE_FILENAME).write_bytes(
                module._canonical_bytes(self.payload)
            )
            return copy.deepcopy(self.payload)

        with (
            patch.object(
                module,
                "build_countdown_thompson_dense_scale_payload",
                side_effect=rotate_during_regeneration,
            ),
            self.assertRaisesRegex(
                module.DenseScaleManifestError, "changed during verification"
            ),
        ):
            module.verify_countdown_thompson_dense_scale_bundle(
                destination,
                repository_root=self.repository_root,
            )

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

    def test_writer_postcommit_close_error_does_not_reverse_success(self) -> None:
        destination = self.root / "written"
        real_close = os.close
        close_calls: list[int] = []

        def fail_first_close_only(descriptor: int) -> None:
            close_calls.append(descriptor)
            real_close(descriptor)
            if len(close_calls) == 1:
                raise OSError(5, "injected close failure")

        with (
            patch.object(
                module,
                "build_countdown_thompson_dense_scale_payload",
                return_value=copy.deepcopy(self.payload),
            ),
            patch.object(module.os, "close", side_effect=fail_first_close_only),
        ):
            returned = module.write_countdown_thompson_dense_scale_bundle(
                destination,
                repository_root=self.repository_root,
            )
        self.assertEqual(returned, destination)
        self.assertEqual(len(close_calls), 3)
        self.assertEqual(
            set(path.name for path in destination.iterdir()),
            {module.BUNDLE_FILENAME},
        )

    def test_writer_does_not_replace_a_raced_destination(self) -> None:
        destination = self.root / "raced"
        real_rename = module._rename_directory_noreplace_at
        raced_identity: list[tuple[int, int, int]] = []

        def race(
            source_directory_fd: int,
            source_name: str,
            destination_directory_fd: int,
            destination_name: str,
        ) -> None:
            os.mkdir(destination_name, dir_fd=destination_directory_fd)
            raced = os.stat(
                destination_name,
                dir_fd=destination_directory_fd,
                follow_symlinks=False,
            )
            raced_identity.append(module._inode_identity(raced))
            real_rename(
                source_directory_fd,
                source_name,
                destination_directory_fd,
                destination_name,
            )

        with (
            patch.object(
                module,
                "build_countdown_thompson_dense_scale_payload",
                return_value=copy.deepcopy(self.payload),
            ),
            patch.object(module, "_rename_directory_noreplace_at", side_effect=race),
            self.assertRaises(FileExistsError),
        ):
            module.write_countdown_thompson_dense_scale_bundle(
                destination,
                repository_root=self.repository_root,
            )
        self.assertEqual(module._inode_identity(destination.lstat()), raced_identity[0])
        self.assertEqual(set(destination.iterdir()), set())
        self.assertEqual(set(self.root.iterdir()), {destination})

    def test_writer_rejects_staging_rotation_immediately_before_open(self) -> None:
        destination = self.root / "written"
        parked = self.root / "parked-legitimate-staging"
        real_open = os.open
        rotated: list[Path] = []

        def rotate_before_open(
            path: object,
            flags: int,
            *args: object,
            **kwargs: object,
        ) -> int:
            if (
                not rotated
                and type(path) is str
                and path.startswith(f".{destination.name}.tmp-")
                and kwargs.get("dir_fd") is not None
                and flags & getattr(os, "O_DIRECTORY", 0)
            ):
                staging = self.root / path
                staging.rename(parked)
                staging.mkdir(mode=0o700)
                (staging / "attacker-owned.txt").write_text(
                    "attacker",
                    encoding="utf-8",
                )
                rotated.append(staging)
            return real_open(path, flags, *args, **kwargs)  # type: ignore[arg-type]

        with (
            patch.object(
                module,
                "build_countdown_thompson_dense_scale_payload",
                return_value=copy.deepcopy(self.payload),
            ),
            patch.object(module.os, "open", side_effect=rotate_before_open),
            self.assertRaisesRegex(
                module.DenseScaleManifestError,
                "staging directory path changed during open",
            ),
        ):
            module.write_countdown_thompson_dense_scale_bundle(
                destination,
                repository_root=self.repository_root,
            )
        self.assertFalse(destination.exists())
        self.assertEqual(
            (rotated[0] / "attacker-owned.txt").read_text(encoding="utf-8"),
            "attacker",
        )
        self.assertTrue(parked.is_dir())

    def test_writer_rejects_same_inode_bytes_overwritten_before_first_fstat(
        self,
    ) -> None:
        destination = self.root / "written"
        real_write_all = module._write_all

        def overwrite_after_write(file_fd: int, raw: bytes) -> None:
            real_write_all(file_fd, raw)
            staging = next(self.root.glob(f".{destination.name}.tmp-*"))
            malicious = b"X" + raw[1:]
            with (staging / module.BUNDLE_FILENAME).open("r+b") as attacker:
                attacker.write(malicious)
                attacker.flush()
                os.fsync(attacker.fileno())

        with (
            patch.object(
                module,
                "build_countdown_thompson_dense_scale_payload",
                return_value=copy.deepcopy(self.payload),
            ),
            patch.object(module, "_write_all", side_effect=overwrite_after_write),
            self.assertRaisesRegex(
                module.DenseScaleManifestError,
                "staging bundle closure is invalid",
            ),
        ):
            module.write_countdown_thompson_dense_scale_bundle(
                destination,
                repository_root=self.repository_root,
            )
        self.assertFalse(destination.exists())
        self.assertEqual(set(self.root.iterdir()), set())

    def test_writer_rejects_same_inode_overwrite_during_final_lexical_check(
        self,
    ) -> None:
        destination = self.root / "written"
        real_lstat = Path.lstat
        parent_observations = 0

        def overwrite_on_second_parent_lstat(path: Path) -> os.stat_result:
            nonlocal parent_observations
            if path == destination.parent:
                parent_observations += 1
                if parent_observations == 2:
                    attacker_fd = os.open(
                        destination / module.BUNDLE_FILENAME,
                        os.O_RDWR,
                    )
                    try:
                        os.pwrite(attacker_fd, b"X", 0)
                        os.fsync(attacker_fd)
                    finally:
                        os.close(attacker_fd)
            return real_lstat(path)

        with (
            patch.object(
                module,
                "build_countdown_thompson_dense_scale_payload",
                return_value=copy.deepcopy(self.payload),
            ),
            patch.object(
                Path,
                "lstat",
                autospec=True,
                side_effect=overwrite_on_second_parent_lstat,
            ),
            self.assertRaisesRegex(
                module.DenseScaleManifestError,
                "published bundle final member check drifted",
            ),
        ):
            module.write_countdown_thompson_dense_scale_bundle(
                destination,
                repository_root=self.repository_root,
            )
        self.assertEqual(parent_observations, 2)
        self.assertEqual(
            (destination / module.BUNDLE_FILENAME).read_bytes()[:1],
            b"X",
        )

    def test_writer_never_returns_success_for_rotated_staging_bytes(self) -> None:
        destination = self.root / "written"
        parked_name = "parked-legitimate-staging"
        real_rename = module._rename_directory_noreplace_at

        def rotate_then_publish_attacker(
            source_directory_fd: int,
            source_name: str,
            destination_directory_fd: int,
            destination_name: str,
        ) -> None:
            os.rename(
                source_name,
                parked_name,
                src_dir_fd=source_directory_fd,
                dst_dir_fd=source_directory_fd,
            )
            os.mkdir(source_name, mode=0o700, dir_fd=source_directory_fd)
            attacker_directory_fd = os.open(
                source_name,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
                dir_fd=source_directory_fd,
            )
            try:
                attacker_fd = os.open(
                    "attacker-owned.txt",
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=attacker_directory_fd,
                )
                try:
                    os.write(attacker_fd, b"attacker")
                finally:
                    os.close(attacker_fd)
            finally:
                os.close(attacker_directory_fd)
            real_rename(
                source_directory_fd,
                source_name,
                destination_directory_fd,
                destination_name,
            )

        with (
            patch.object(
                module,
                "build_countdown_thompson_dense_scale_payload",
                return_value=copy.deepcopy(self.payload),
            ),
            patch.object(
                module,
                "_rename_directory_noreplace_at",
                side_effect=rotate_then_publish_attacker,
            ),
            self.assertRaisesRegex(
                module.DenseScaleManifestError,
                "published directory identity drifted",
            ),
        ):
            module.write_countdown_thompson_dense_scale_bundle(
                destination,
                repository_root=self.repository_root,
            )
        self.assertEqual(
            (destination / "attacker-owned.txt").read_text(encoding="utf-8"),
            "attacker",
        )
        self.assertEqual(
            set((self.root / parked_name).iterdir()),
            {self.root / parked_name / module.BUNDLE_FILENAME},
        )


if __name__ == "__main__":
    unittest.main()
