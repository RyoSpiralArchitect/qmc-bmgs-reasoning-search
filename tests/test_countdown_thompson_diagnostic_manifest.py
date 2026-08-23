from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import time
import unittest
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from qmc_bmgs.benchmarks.countdown import CountdownTask, GeneratedTaskSuite
from qmc_bmgs.experiments import countdown_thompson_diagnostic_manifest as module
from qmc_bmgs.experiments.countdown_track_a_canary_manifest import (
    verify_track_a_canary_bundle,
)
from qmc_bmgs.substrate.trace import canonical_json, sha256_json


def _task_rows(payload: dict[str, object]) -> tuple[CountdownTask, ...]:
    return tuple(
        CountdownTask(tuple(row["inputs"]), row["target"]) for row in payload["tasks"]
    )


class CountdownThompsonDiagnosticManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temporary = tempfile.TemporaryDirectory(
            prefix="qmc-thompson-diagnostic-manifest-tests-"
        )
        cls.root = Path(cls._temporary.name)
        cls.repository_root = Path(__file__).resolve().parents[1]
        cls.payloads = module.build_countdown_thompson_diagnostic_payloads(
            repository_root=cls.repository_root
        )
        cls.tracked_bundle = (
            cls.repository_root
            / "docs/preregistrations/countdown_thompson_diagnostic_v1"
        )
        cls.bundle = cls.root / "bundle"
        with patch.object(
            module,
            "build_countdown_thompson_diagnostic_payloads",
            return_value=deepcopy(cls.payloads),
        ):
            module.write_countdown_thompson_diagnostic_bundle(
                cls.bundle,
                repository_root=cls.repository_root,
            )
            cls.verified = module.verify_countdown_thompson_diagnostic_bundle(
                cls.bundle,
                repository_root=cls.repository_root,
            )

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temporary.cleanup()

    def test_locked_and_diagnostic_cohorts_are_doubly_disjoint(self) -> None:
        authorities = self.payloads["authorities.json"]
        locked = self.payloads["locked_reservation.json"]
        diagnostic = self.payloads["diagnostic_tasks.json"]
        self.assertEqual(locked["task_count"], 128)
        self.assertEqual(diagnostic["task_count"], 12)
        self.assertEqual(locked["generation_call"]["seed"], 26072602)
        self.assertEqual(diagnostic["generation_call"]["seed"], 26081001)
        self.assertEqual(locked["generation_manifest"]["attempt_count"], 173)
        self.assertEqual(diagnostic["generation_manifest"]["attempt_count"], 16)
        self.assertEqual(
            locked["deterministic_digest"],
            "770e827281e39192a28029af1b5dd8eda4140103db5ee00254e4397465eb4d44",
        )
        self.assertEqual(
            diagnostic["deterministic_digest"],
            "c9c1d2be2504b1bb72331a183287b783bffb623a14b4b54ef0c0f2f548275aea",
        )

        cohorts = [
            authorities["historical_authority"]["tasks"],
            authorities["canary_authority"]["tasks"],
            locked["tasks"],
            diagnostic["tasks"],
        ]
        self.assertEqual([len(rows) for rows in cohorts], [2, 12, 128, 12])
        task_ids = [row["task_fingerprint"] for rows in cohorts for row in rows]
        source_ids = [
            row["source_multiset_fingerprint"] for rows in cohorts for row in rows
        ]
        self.assertEqual(len(task_ids), 154)
        self.assertEqual(len(set(task_ids)), 154)
        self.assertEqual(len(set(source_ids)), 154)
        self.assertEqual(locked["exclusion_identity"]["task_fingerprint_count"], 14)
        self.assertEqual(
            diagnostic["exclusion_identity"]["task_fingerprint_count"], 142
        )
        self.assertEqual(
            set(authorities["canary_authority"]["component_receipts"]),
            {
                "budgets.json",
                "exclusions.json",
                "methods.json",
                "proposals.json",
                "tasks.json",
            },
        )

    def test_tracked_bundle_is_exactly_one_fresh_build(self) -> None:
        self.assertEqual(
            {path.name for path in self.tracked_bundle.iterdir()},
            set(module.BUNDLE_FILENAMES),
        )
        for filename in module.BUNDLE_FILENAMES:
            self.assertEqual(
                (self.tracked_bundle / filename).read_bytes(),
                (canonical_json(self.payloads[filename]) + "\n").encode(),
            )
        self.assertEqual(
            self.verified.seal_digest,
            "cc633b9ee3ffda6a9115af07f0cc047a1bd8cd7af5e11d07f6ddb0faa4e5f975",
        )

    def test_no_solution_or_search_material_is_persisted(self) -> None:
        rendered = canonical_json(self.payloads)
        for forbidden in sorted(module._FORBIDDEN_PERSISTED_KEYS):
            self.assertNotIn(f'"{forbidden}"', rendered)
        for filename in ("locked_reservation.json", "diagnostic_tasks.json"):
            payload = self.payloads[filename]
            self.assertFalse(payload["persisted_calibration_profiles"])
            self.assertFalse(payload["persisted_solution_witnesses"])
            for row in payload["tasks"]:
                task = CountdownTask(tuple(row["inputs"]), row["target"])
                self.assertEqual(row, task.to_dict())
            self.assertEqual(
                set(payload["generation_manifest"]),
                {
                    "accepted_count",
                    "accepted_task_pool_digest",
                    "attempt_count",
                    "conditioned_on_exhaustive_solvability",
                    "excluded_identity_record_digest",
                    "excluded_source_multiset_fingerprint_count",
                    "excluded_source_multiset_fingerprint_digest",
                    "excluded_task_fingerprint_count",
                    "excluded_task_fingerprint_digest",
                    "generation_manifest_digest",
                    "generator_id",
                    "input_range_inclusive",
                    "max_attempts",
                    "rejection_counts",
                    "rejection_log",
                    "requested_count",
                    "seed",
                    "source_multisets_unique",
                    "target_range_inclusive",
                },
            )

    def test_component_allowlists_reject_unlisted_result_containers(self) -> None:
        for key in (
            "final_value",
            "provider_output",
            "search_outcome",
            "success_any",
            "terminal_records",
        ):
            tampered = deepcopy(self.payloads)
            tampered["analysis.json"][key] = []
            with self.subTest(key=key):
                with self.assertRaises(module.DiagnosticManifestError):
                    module._validate_component_schemas(tampered)

    def test_schedule_has_exact_240_ragged_cells_and_no_fake_seeds(self) -> None:
        cells = module.iter_countdown_thompson_diagnostic_cells(self.verified)
        self.assertEqual(len(cells), 240)
        self.assertEqual(len({cell.cell_id for cell in cells}), 240)
        self.assertTrue(all(cell.cell_id == sha256_json(cell.key) for cell in cells))
        by_proposal = Counter(cell.proposal_label for cell in cells)
        self.assertEqual(by_proposal, {"heuristic": 228, "oracle_positive_control": 12})
        by_method = Counter(cell.method_label for cell in cells)
        self.assertEqual(by_method["greedy"], 24)
        self.assertEqual(by_method["beam_width_2"], 12)
        self.assertEqual(by_method["puct_c1"], 12)
        for label in (
            "thompson_candidate_iid_v1",
            "thompson_dimnorm_iid_v2",
            "thompson_dense_iid_v3",
            "thompson_greedy_anchor_dense_iid_v4",
        ):
            self.assertEqual(by_method[label], 48)
        method_seeds: dict[str, set[int]] = defaultdict(set)
        for cell in cells:
            method_seeds[cell.method_label].add(cell.exploration_seed)
        for label in ("greedy", "beam_width_2", "puct_c1"):
            self.assertEqual(method_seeds[label], {0})
        for label in by_method.keys() - {"greedy", "beam_width_2", "puct_c1"}:
            self.assertEqual(method_seeds[label], {7168, 7169, 7170, 7171})
        oracle_methods = {
            cell.method_label
            for cell in cells
            if cell.proposal_label == "oracle_positive_control"
        }
        self.assertEqual(oracle_methods, {"greedy"})

    def test_method_versions_runtime_and_budget_are_exact(self) -> None:
        methods = self.payloads["methods.json"]
        observed = {
            row["label"]: row["spec"]["method_id"] for row in methods["methods"]
        }
        self.assertEqual(
            observed,
            {
                "beam_width_2": "layer_synchronous_beam_width_2/v1",
                "greedy": "greedy/v1",
                "puct_c1": "puct_binary_terminal/v1",
                "thompson_candidate_iid_v1": "thompson_binary_terminal/v1",
                "thompson_dimnorm_iid_v2": (
                    "thompson_binary_terminal_dimnorm_noise/v2"
                ),
                "thompson_dense_iid_v3": (
                    "thompson_reciprocal_error_terminal_dimnorm_noise/v3"
                ),
                "thompson_greedy_anchor_dense_iid_v4": (
                    "thompson_greedy_anchor_reciprocal_error_terminal_dimnorm_noise/v4"
                ),
            },
        )
        self.assertEqual(set(methods["runtime_bindings"]), {"iid", "search"})
        self.assertTrue(methods["pairing_contract"]["iid_only_diagnostic"])
        self.assertTrue(
            methods["pairing_contract"][
                "sobol_comparison_closed_until_base_search_is_competitive"
            ]
        )
        budget = self.payloads["budgets.json"]["profiles"][0]["spec"]
        self.assertEqual(
            budget,
            {
                "budget": {
                    "edge_selections": 86,
                    "generated_perturbation_coordinates": 316,
                    "legal_action_scores": 256,
                    "proposal_action_scores": 317,
                    "proposal_state_evaluations": 87,
                    "transitions": 86,
                    "verifier_calls": 18,
                },
                "primary_axis": "legal_action_scores",
                "profile_id": "score256",
                "schema_version": "qmc-bmgs-track-a-budget-profile/v1",
            },
        )

    def test_analysis_is_task_paired_descriptive_and_exactly_ordered(self) -> None:
        analysis = self.payloads["analysis.json"]
        self.assertTrue(
            analysis["claim_boundary"]["analysis_order_is_interpretive_not_blinding"]
        )
        self.assertFalse(analysis["claim_boundary"]["p_values"])
        self.assertFalse(analysis["claim_boundary"]["confidence_intervals"])
        metrics = analysis["mechanism_metrics"]
        self.assertEqual(metrics["root_rank_vector_size_per_stochastic_method"], 48)
        self.assertEqual(
            metrics["root_rank_pair_key"], "(task_fingerprint,exploration_seed)"
        )
        readiness = analysis["engineering_readiness"]
        self.assertEqual(
            readiness["margins"]["candidate_minus_greedy"],
            {
                "minimum_48_cell_success_count_difference": 2,
                "operator": ">=",
                "smallest_passing_lattice_delta": {
                    "denominator": 24,
                    "numerator": 1,
                },
                "threshold": {"denominator": 100, "numerator": 3},
            },
        )
        self.assertEqual(
            readiness["margins"]["candidate_minus_puct_c1"],
            {
                "minimum_48_cell_success_count_difference": 0,
                "operator": ">=",
                "smallest_passing_lattice_delta": {
                    "denominator": 1,
                    "numerator": 0,
                },
                "threshold": {"denominator": 50, "numerator": -1},
            },
        )
        self.assertEqual(readiness["failure_status"], "STOP_REPAIR_NO_LOCKED_128_RUN")

    def test_exact_rational_boundaries_match_the_sealed_lattice(self) -> None:
        plus_three = {"denominator": 100, "numerator": 3}
        minus_two = {"denominator": 50, "numerator": -1}
        self.assertFalse(module._compare_rational(1, 48, ">=", plus_three))
        self.assertTrue(module._compare_rational(2, 48, ">=", plus_three))
        self.assertFalse(module._compare_rational(-1, 48, ">=", minus_two))
        self.assertTrue(module._compare_rational(0, 48, ">=", minus_two))
        self.assertFalse(
            module._compare_rational(
                9,
                100,
                ">=",
                {"denominator": 10, "numerator": 1},
            )
        )
        self.assertTrue(
            module._compare_rational(
                1,
                10,
                ">=",
                {"denominator": 10, "numerator": 1},
            )
        )
        self.assertTrue(
            module._compare_rational(
                3,
                20,
                "<=",
                {"denominator": 20, "numerator": 3},
            )
        )
        self.assertFalse(
            module._compare_rational(
                4,
                20,
                "<=",
                {"denominator": 20, "numerator": 3},
            )
        )

    def test_build_path_does_not_touch_search_proposals_or_points(self) -> None:
        authorities = self.payloads["authorities.json"]
        historical = tuple(
            CountdownTask(tuple(row["inputs"]), row["target"])
            for row in authorities["historical_authority"]["tasks"]
        )
        canary_tasks = tuple(
            CountdownTask(tuple(row["inputs"]), row["target"])
            for row in authorities["canary_authority"]["tasks"]
        )
        canary_bundle = verify_track_a_canary_bundle(
            self.repository_root / module.CANARY_BUNDLE_PATH,
            repository_root=self.repository_root,
        )
        authority_result = (
            deepcopy(authorities),
            historical,
            canary_tasks,
            canary_bundle.payloads,
        )
        suites = iter(
            (
                GeneratedTaskSuite(
                    _task_rows(self.payloads["locked_reservation.json"]),
                    (),
                    deepcopy(
                        self.payloads["locked_reservation.json"]["generation_manifest"]
                    ),
                ),
                GeneratedTaskSuite(
                    _task_rows(self.payloads["diagnostic_tasks.json"]),
                    (),
                    deepcopy(
                        self.payloads["diagnostic_tasks.json"]["generation_manifest"]
                    ),
                ),
            )
        )
        bomb = AssertionError("outcome/material API was touched")
        with (
            patch.object(module, "_authority_manifest", return_value=authority_result),
            patch.object(
                module,
                "generate_solvable_task_suite",
                side_effect=lambda *args, **kwargs: next(suites),
            ),
            patch(
                "qmc_bmgs.substrate.countdown_search.run_countdown_track_a_search",
                side_effect=bomb,
            ),
            patch(
                "qmc_bmgs.substrate.proposals.evaluate_track_a_proposal",
                side_effect=bomb,
            ),
            patch(
                "qmc_bmgs.substrate.perturbations.LazyNormalSource.draw",
                side_effect=bomb,
            ),
        ):
            rebuilt = module.build_countdown_thompson_diagnostic_payloads(
                repository_root=self.repository_root
            )
        self.assertEqual(rebuilt, self.payloads)

    def test_verifier_rejects_noncanonical_extra_and_symlink_entries(self) -> None:
        noncanonical = self.root / "noncanonical"
        shutil.copytree(self.bundle, noncanonical)
        path = noncanonical / "analysis.json"
        path.write_bytes(b" " + path.read_bytes())
        with self.assertRaises(module.DiagnosticManifestError):
            module.verify_countdown_thompson_diagnostic_bundle(
                noncanonical,
                repository_root=self.repository_root,
            )

        extra = self.root / "extra"
        shutil.copytree(self.bundle, extra)
        (extra / "unexpected.json").write_text("{}\n", encoding="utf-8")
        with self.assertRaises(module.DiagnosticManifestError):
            module.verify_countdown_thompson_diagnostic_bundle(
                extra,
                repository_root=self.repository_root,
            )

        linked = self.root / "linked"
        shutil.copytree(self.bundle, linked)
        target = linked / "analysis-target.json"
        (linked / "analysis.json").rename(target)
        (linked / "analysis.json").symlink_to(target.name)
        with self.assertRaises(module.DiagnosticManifestError):
            module.verify_countdown_thompson_diagnostic_bundle(
                linked,
                repository_root=self.repository_root,
            )

    def test_strict_parser_rejects_duplicate_keys_nan_and_wrong_root(self) -> None:
        for raw in (b'{"a":1,"a":2}\n', b'{"a":NaN}\n'):
            with self.assertRaises(module.DiagnosticManifestError):
                module._parse_canonical_object(raw, filename="invalid.json")
        with self.assertRaises(module.DiagnosticManifestError):
            module.build_countdown_thompson_diagnostic_payloads(
                repository_root=self.root / "not-a-repository"
            )

    def test_strict_parser_types_deep_recursion_as_manifest_invalid(self) -> None:
        nesting = 10_000
        raw = b'{"nested":' + (b"[" * nesting) + b"0" + (b"]" * nesting) + b"}\n"
        with self.assertRaises(module.DiagnosticManifestError) as raised:
            module._parse_canonical_object(raw, filename="deep.json")
        self.assertIs(type(raised.exception), module.DiagnosticManifestError)

    def test_public_verifier_types_deep_parseable_bundle_as_manifest_invalid(
        self,
    ) -> None:
        deep_bundle = self.root / "deep-parseable-bundle"
        payloads = deepcopy(self.payloads)
        nested: object = 0
        for _ in range(1_050):
            nested = [nested]
        analysis_payload = payloads["analysis.json"]
        analysis_payload["claim_boundary"] = nested
        analysis_core = {
            key: value
            for key, value in analysis_payload.items()
            if key != "deterministic_digest"
        }
        analysis_payload["deterministic_digest"] = sha256_json(analysis_core)

        preregistration = payloads["preregistration.json"]
        preregistration["component_manifest_digests"]["analysis.json"] = (
            analysis_payload["deterministic_digest"]
        )
        preregistration_core = {
            key: value
            for key, value in preregistration.items()
            if key != "deterministic_digest"
        }
        preregistration["deterministic_digest"] = sha256_json(preregistration_core)
        payloads[module.SEAL_FILENAME] = module._seal(
            {filename: payloads[filename] for filename in module.COMPONENT_FILENAMES}
        )

        deep_bundle.mkdir()
        for filename in module.BUNDLE_FILENAMES:
            (deep_bundle / filename).write_bytes(
                module._canonical_bytes(payloads[filename])
            )
        self.assertIs(
            type(
                module._parse_canonical_object(
                    (deep_bundle / "analysis.json").read_bytes(),
                    filename="analysis.json",
                )
            ),
            dict,
        )

        with (
            patch.object(
                module,
                "build_countdown_thompson_diagnostic_payloads",
                return_value=deepcopy(self.payloads),
            ),
            self.assertRaises(module.DiagnosticManifestError) as raised,
        ):
            module.verify_countdown_thompson_diagnostic_bundle(
                deep_bundle,
                repository_root=self.repository_root,
            )
        self.assertIs(type(raised.exception), module.DiagnosticManifestError)

    def test_verifier_rejects_directory_change_during_verification(self) -> None:
        changed = self.root / "changed-during-verify"
        shutil.copytree(self.bundle, changed)
        original = module._read_bundle_snapshot_from_descriptor
        calls = 0

        def read_then_change(
            directory_fd: int,
        ) -> tuple[dict[str, dict[str, object]], dict[str, bytes]]:
            nonlocal calls
            result = original(directory_fd)
            calls += 1
            if calls == 1:
                path = changed / "analysis.json"
                path.write_bytes(b" " + path.read_bytes())
            return result

        with (
            patch.object(
                module,
                "build_countdown_thompson_diagnostic_payloads",
                return_value=deepcopy(self.payloads),
            ),
            patch.object(
                module,
                "_read_bundle_snapshot_from_descriptor",
                side_effect=read_then_change,
            ),
        ):
            with self.assertRaises(module.DiagnosticManifestError):
                module.verify_countdown_thompson_diagnostic_bundle(
                    changed,
                    repository_root=self.repository_root,
                )

    @unittest.skipUnless(
        os.name == "posix" and hasattr(os, "mkfifo"),
        "POSIX FIFO semantics required",
    )
    def test_snapshot_rejects_regular_to_fifo_race_without_blocking(self) -> None:
        raced = self.root / "regular-to-fifo-race"
        shutil.copytree(self.bundle, raced)
        target = raced / module.BUNDLE_FILENAMES[0]
        original_open = module.os.open
        swapped = False

        def swap_before_member_open(
            path: object,
            flags: int,
            *args: object,
            **kwargs: object,
        ) -> int:
            nonlocal swapped
            if path == target.name and kwargs.get("dir_fd") is not None and not swapped:
                self.assertTrue(flags & os.O_NONBLOCK)
                target.unlink()
                os.mkfifo(target)
                swapped = True
            return original_open(path, flags, *args, **kwargs)

        started = time.monotonic()
        with (
            patch.object(module.os, "open", side_effect=swap_before_member_open),
            self.assertRaisesRegex(
                module.DiagnosticManifestError,
                "changed before descriptor acquisition",
            ),
        ):
            module._read_bundle_snapshot(raced)
        self.assertTrue(swapped)
        self.assertLess(time.monotonic() - started, 1.0)

    def test_snapshot_rejects_oversize_member_before_open(self) -> None:
        oversized = self.root / "oversized-member"
        shutil.copytree(self.bundle, oversized)
        target = oversized / module.BUNDLE_FILENAMES[0]
        with target.open("wb") as handle:
            handle.truncate(module._BUNDLE_MEMBER_BYTE_CAP_V1 + 1)
        original_open = module.os.open
        member_opened = False

        def observe_member_open(
            path: object,
            flags: int,
            *args: object,
            **kwargs: object,
        ) -> int:
            nonlocal member_opened
            if path == target.name and kwargs.get("dir_fd") is not None:
                member_opened = True
            return original_open(path, flags, *args, **kwargs)

        with (
            patch.object(module.os, "open", side_effect=observe_member_open),
            self.assertRaisesRegex(
                module.DiagnosticManifestError,
                "exceeds the v1 byte cap",
            ),
        ):
            module._read_bundle_snapshot(oversized)
        self.assertFalse(member_opened)

    def test_snapshot_rejects_rotating_member_generations(self) -> None:
        rotating = self.root / "rotating-member-generations"
        shutil.copytree(self.bundle, rotating)
        early = rotating / module.BUNDLE_FILENAMES[0]
        late = rotating / "analysis.json"
        early_exact = early.read_bytes()
        late_exact = late.read_bytes()
        early_foreign = bytes([early_exact[0] ^ 1]) + early_exact[1:]
        late_foreign = bytes([late_exact[0] ^ 1]) + late_exact[1:]
        self.assertEqual(len(early_foreign), len(early_exact))
        self.assertEqual(len(late_foreign), len(late_exact))
        late.write_bytes(late_foreign)
        original_read = module._read_bounded_bundle_member_at
        rotated = False

        def rotate_before_late_read(
            directory_fd: int,
            filename: str,
        ) -> bytes:
            nonlocal rotated
            if filename == late.name and not rotated:
                early.write_bytes(early_foreign)
                late.write_bytes(late_exact)
                rotated = True
            return original_read(directory_fd, filename)

        with (
            patch.object(
                module,
                "_read_bounded_bundle_member_at",
                side_effect=rotate_before_late_read,
            ),
            self.assertRaisesRegex(
                module.DiagnosticManifestError,
                "bundle member generation changed during snapshot",
            ),
        ):
            module._read_bundle_snapshot(rotating)
        self.assertTrue(rotated)
        self.assertEqual(early.read_bytes(), early_foreign)
        self.assertEqual(late.read_bytes(), late_exact)

    def test_verifier_fails_closed_without_descriptor_bound_platform(self) -> None:
        with (
            patch.object(module.os, "name", "nt"),
            self.assertRaisesRegex(
                module.DiagnosticManifestError,
                "descriptor-bound bundle verification is unavailable",
            ) as raised,
        ):
            module.verify_countdown_thompson_diagnostic_bundle(
                self.bundle,
                repository_root=self.repository_root,
            )
        self.assertIs(type(raised.exception), module.DiagnosticManifestError)

    def test_verifier_rejects_rehashed_semantic_tamper(self) -> None:
        tampered = self.root / "tampered"
        shutil.copytree(self.bundle, tampered)
        payloads = deepcopy(self.payloads)
        methods = payloads["methods.json"]
        methods["methods"][0]["label"] = "renamed_greedy"
        core = {k: v for k, v in methods.items() if k != "deterministic_digest"}
        methods["deterministic_digest"] = sha256_json(core)
        raw = (canonical_json(methods) + "\n").encode()
        (tampered / "methods.json").write_bytes(raw)
        seal = payloads["seal.json"]
        seal["component_files"]["methods.json"] = {
            "byte_count": len(raw),
            "deterministic_digest": methods["deterministic_digest"],
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
        seal_core = {k: v for k, v in seal.items() if k != "deterministic_digest"}
        seal["deterministic_digest"] = sha256_json(seal_core)
        (tampered / "seal.json").write_text(
            canonical_json(seal) + "\n", encoding="utf-8"
        )
        with patch.object(
            module,
            "build_countdown_thompson_diagnostic_payloads",
            return_value=deepcopy(self.payloads),
        ):
            with self.assertRaises(module.DiagnosticManifestError):
                module.verify_countdown_thompson_diagnostic_bundle(
                    tampered,
                    repository_root=self.repository_root,
                )

    def test_write_is_no_overwrite_and_verified_payload_is_defensive(self) -> None:
        with patch.object(
            module,
            "build_countdown_thompson_diagnostic_payloads",
            return_value=deepcopy(self.payloads),
        ):
            with self.assertRaises(FileExistsError):
                module.write_countdown_thompson_diagnostic_bundle(
                    self.bundle,
                    repository_root=self.repository_root,
                )
        copy = self.verified.payloads
        copy["analysis.json"]["bundle_id"] = "mutated"
        self.assertEqual(
            self.verified.payloads["analysis.json"]["bundle_id"], module.BUNDLE_ID
        )

    def test_publication_refuses_a_raced_destination(self) -> None:
        destination = self.root / "raced-destination"
        original = module._rename_directory_noreplace

        def create_destination_then_rename(source: Path, target: Path) -> None:
            target.mkdir()
            original(source, target)

        with (
            patch.object(
                module,
                "build_countdown_thompson_diagnostic_payloads",
                return_value=deepcopy(self.payloads),
            ),
            patch.object(
                module,
                "_rename_directory_noreplace",
                side_effect=create_destination_then_rename,
            ),
        ):
            with self.assertRaises(FileExistsError):
                module.write_countdown_thompson_diagnostic_bundle(
                    destination,
                    repository_root=self.repository_root,
                )
        self.assertTrue(destination.is_dir())
        self.assertEqual(list(destination.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
