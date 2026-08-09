from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from collections import Counter, defaultdict
from copy import deepcopy
from importlib.resources import files as resource_files
from pathlib import Path
from unittest.mock import patch

from qmc_bmgs.benchmarks.countdown import CountdownTask
from qmc_bmgs.experiments.countdown_track_a_canary_manifest import (
    BUNDLE_FILENAMES,
    EXPECTED_CELL_COUNT,
    IMPLEMENTATION_BASE,
    SUPERSEDED_BUNDLE,
    CanaryManifestError,
    build_track_a_canary_payloads,
    frozen_track_a_canary_runtime_bindings,
    iter_track_a_canary_cells,
    qualify_track_a_canary_runtime,
    verify_track_a_canary_bundle,
    write_track_a_canary_bundle,
)
from qmc_bmgs.experiments import countdown_track_a_canary_manifest as manifest_module
from qmc_bmgs.substrate.budget import TrackAWorkBudget
from qmc_bmgs.substrate.countdown_search import (
    TrackABudgetProfile,
    TrackAMethodSpec,
    run_countdown_track_a_search,
)
from qmc_bmgs.substrate import perturbations as perturbations_module
from qmc_bmgs.substrate.proposals import TrackAProposalSpec
from qmc_bmgs.substrate.trace import canonical_json, sha256_json


def _write_canonical(path: Path, payload: dict[str, object]) -> bytes:
    raw = (canonical_json(payload) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return raw


class TrackACanaryManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temporary = tempfile.TemporaryDirectory(
            prefix="qmc-track-a-canary-tests-"
        )
        cls.root = Path(cls._temporary.name)
        cls.bundle_path = cls.root / "bundle"
        write_track_a_canary_bundle(cls.bundle_path)
        cls.verified = verify_track_a_canary_bundle(cls.bundle_path)
        cls.payloads = cls.verified.payloads

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temporary.cleanup()

    def test_task_generation_is_source_disjoint_and_persists_no_witness(self) -> None:
        exclusions = self.payloads["exclusions.json"]
        tasks = self.payloads["tasks.json"]
        self.assertEqual(
            exclusions["deterministic_digest"],
            "0646565cee179f622562844e03478a19abd04db768d2e7ca4b638ffdd4942679",
        )
        self.assertEqual(
            tasks["accepted_task_pool_digest"],
            "d2374929a694882527c82acc6fa763f0a405abb4a06b75c3e48e694000bdeb9c",
        )
        self.assertEqual(
            tasks["generation_manifest"]["generation_manifest_digest"],
            "85e517449f21ff2262418be0b1002f12119ce47688a70f14c12b9ea707691e8e",
        )
        self.assertEqual(tasks["task_count"], 12)
        self.assertEqual(tasks["generation_manifest"]["attempt_count"], 16)
        self.assertEqual(
            tasks["generation_manifest"]["rejection_counts"]["unsolvable"],
            4,
        )
        self.assertFalse(tasks["persisted_calibration_profiles"])
        self.assertFalse(tasks["persisted_solution_witnesses"])
        excluded_tasks = set(exclusions["task_fingerprints"])
        excluded_sources = set(exclusions["source_multiset_fingerprints"])
        task_ids = {row["task_fingerprint"] for row in tasks["tasks"]}
        source_ids = {
            row["source_multiset_fingerprint"] for row in tasks["tasks"]
        }
        self.assertEqual(len(task_ids), 12)
        self.assertEqual(len(source_ids), 12)
        self.assertFalse(task_ids & excluded_tasks)
        self.assertFalse(source_ids & excluded_sources)
        rendered = canonical_json(self.payloads)
        for forbidden in (
            '"calibration_profile"',
            '"solution_witness"',
            '"witness_digest"',
            '"uniforms"',
            '"normals"',
            '"point_digest"',
            '"search_record"',
            '"proposal_row"',
        ):
            self.assertNotIn(forbidden, rendered)

    def test_reduced_matrix_has_936_unique_full_spec_digest_keys(self) -> None:
        cells = iter_track_a_canary_cells(self.verified)
        self.assertEqual(len(cells), EXPECTED_CELL_COUNT)
        self.assertEqual(len({cell.cell_id for cell in cells}), EXPECTED_CELL_COUNT)
        required_key_fields = {
            "budget_profile_spec_digest",
            "exploration_seed",
            "method_manifest_digest",
            "method_spec_digest",
            "proposal_spec_digest",
            "schema_version",
            "task_fingerprint",
            "task_manifest_digest",
        }
        for cell in cells:
            self.assertEqual(set(cell.key), required_key_fields)
            self.assertEqual(cell.cell_id, sha256_json(cell.key))
            for field in (
                "budget_profile_spec_digest",
                "method_manifest_digest",
                "method_spec_digest",
                "proposal_spec_digest",
                "task_fingerprint",
                "task_manifest_digest",
            ):
                self.assertRegex(cell.key[field], r"^[0-9a-f]{64}$")

        by_proposal = Counter(cell.proposal_label for cell in cells)
        self.assertEqual(
            by_proposal,
            {
                "uniform": 456,
                "heuristic": 456,
                "oracle_positive_control": 24,
            },
        )
        by_method = Counter(cell.method_label for cell in cells)
        self.assertEqual(by_method["greedy"], 72)
        self.assertEqual(by_method["beam_width_2"], 48)
        self.assertEqual(by_method["puct_c1"], 48)
        for label in (
            "thompson_frozen_iid",
            "thompson_frozen_sobol",
            "thompson_candidate_iid",
            "thompson_candidate_sobol",
        ):
            self.assertEqual(by_method[label], 192)
        oracle_methods = {
            cell.method_label
            for cell in cells
            if cell.proposal_label == "oracle_positive_control"
        }
        self.assertEqual(oracle_methods, {"greedy"})
        matrix = self.payloads["preregistration.json"]["execution_matrix"]
        self.assertEqual(
            matrix["matrix_scope"],
            "reduced_preregistered_matrix_not_full_cartesian",
        )
        self.assertEqual(matrix["omitted_cells"], "oracle_non_greedy_methods")
        contrasts = self.payloads["preregistration.json"]["analysis_freeze"][
            "canary"
        ]["paired_contrasts"]
        self.assertEqual(
            set(contrasts["contrast_order"]),
            set(contrasts["definitions"]),
        )
        self.assertEqual(
            len(contrasts["contrast_order"]),
            len(set(contrasts["contrast_order"])),
        )

    def test_deterministic_methods_are_not_replicated_as_fake_seed_cells(self) -> None:
        cells = iter_track_a_canary_cells(self.verified)
        method_seeds: dict[str, set[int]] = defaultdict(set)
        for cell in cells:
            method_seeds[cell.method_label].add(cell.exploration_seed)
        for label in ("greedy", "beam_width_2", "puct_c1"):
            self.assertEqual(method_seeds[label], {0})
        for label in (
            "thompson_frozen_iid",
            "thompson_frozen_sobol",
            "thompson_candidate_iid",
            "thompson_candidate_sobol",
        ):
            self.assertEqual(method_seeds[label], {7168, 7169, 7170, 7171})

    def test_budget_guards_and_structural_proof_are_exact(self) -> None:
        budgets = self.payloads["budgets.json"]
        profiles = {
            row["spec"]["profile_id"]: row for row in budgets["profiles"]
        }
        self.assertEqual(
            profiles["score256"]["spec"]["budget"],
            {
                "proposal_state_evaluations": 87,
                "proposal_action_scores": 317,
                "legal_action_scores": 256,
                "generated_perturbation_coordinates": 316,
                "edge_selections": 86,
                "transitions": 86,
                "verifier_calls": 18,
            },
        )
        self.assertEqual(
            profiles["verifier8"]["spec"]["budget"],
            {
                "proposal_state_evaluations": 41,
                "proposal_action_scores": 1121,
                "legal_action_scores": 1121,
                "generated_perturbation_coordinates": 1121,
                "edge_selections": 41,
                "transitions": 41,
                "verifier_calls": 8,
            },
        )
        proof = budgets["structural_guard_proof"]
        self.assertEqual(proof["version"], "countdown-d6-atomic-guard-upper-bound/v2")
        self.assertEqual(proof["score256_atomic_next_selection_max_action_count"], 60)
        self.assertEqual(proof["score256_max_selection_steps"], 85)
        self.assertEqual(proof["score256_max_complete_terminal_verifications"], 17)
        self.assertEqual(proof["verifier8_max_legal_action_scores"], 1120)
        self.assertEqual(proof["strict_guard_slack"], 1)

    def test_v2_explicitly_supersedes_the_untouched_v1_seal(self) -> None:
        supersedes = self.payloads["preregistration.json"]["supersedes"]
        self.assertEqual(
            supersedes,
            {
                **SUPERSEDED_BUNDLE,
                "reason": (
                    "The v1 score256 coordinate and proposal guards could "
                    "co-block the same atomic action-vector charge as the "
                    "legal-action primary axis. A source-disjoint non-canary "
                    "D6 fixture reproduced the failure before any sealed "
                    "canary search outcome was opened."
                ),
                "replacement_scope": (
                    "outcome-blind guard correction only; tasks, proposals, "
                    "methods, seeds, analysis rules, and cell count are unchanged"
                ),
            },
        )
        legacy_dir = (
            Path(__file__).resolve().parents[1]
            / "docs/preregistrations/countdown_track_a_canary_v1"
        )
        self.assertEqual(
            {path.name for path in legacy_dir.iterdir()},
            set(BUNDLE_FILENAMES),
        )
        raw = (legacy_dir / "seal.json").read_bytes()
        self.assertEqual(
            hashlib.sha256(raw).hexdigest(),
            SUPERSEDED_BUNDLE["seal_file_sha256"],
        )
        legacy_seal = json.loads(raw)
        self.assertEqual(
            legacy_seal["deterministic_digest"],
            SUPERSEDED_BUNDLE["seal_digest"],
        )
        for filename, receipt in legacy_seal["component_files"].items():
            component_raw = (legacy_dir / filename).read_bytes()
            component = json.loads(component_raw)
            self.assertEqual(len(component_raw), receipt["byte_count"])
            self.assertEqual(hashlib.sha256(component_raw).hexdigest(), receipt["sha256"])
            self.assertEqual(
                component["deterministic_digest"],
                receipt["deterministic_digest"],
            )

    def test_noncanary_fixture_reproduces_v1_coblock_and_v2_primary_stop(
        self,
    ) -> None:
        task = CountdownTask((1, 2, 3, 4, 5, 6), target=720)
        canary_ids = {
            row["task_fingerprint"]
            for row in self.payloads["tasks.json"]["tasks"]
        }
        self.assertNotIn(task.task_fingerprint, canary_ids)
        proposal = TrackAProposalSpec("greedy_rollout_target_error/v1")
        method = TrackAMethodSpec.candidate_thompson("iid")

        legacy = TrackABudgetProfile(
            profile_id="score256-v1-reproducer",
            primary_axis="legal_action_scores",
            budget=TrackAWorkBudget(
                proposal_state_evaluations=86,
                proposal_action_scores=257,
                legal_action_scores=256,
                generated_perturbation_coordinates=257,
                edge_selections=86,
                transitions=86,
                verifier_calls=18,
            ),
        )
        legacy_result = run_countdown_track_a_search(
            task,
            proposal=proposal,
            method=method,
            budget_profile=legacy,
            exploration_seed=7168,
        )
        self.assertFalse(legacy_result.summary["budget_valid"])
        self.assertEqual(
            legacy_result.summary["stop_blocked_axes"],
            ["legal_action_scores", "generated_perturbation_coordinates"],
        )

        score256 = next(
            row["spec"]
            for row in self.payloads["budgets.json"]["profiles"]
            if row["spec"]["profile_id"] == "score256"
        )
        corrected = TrackABudgetProfile(
            profile_id=score256["profile_id"],
            primary_axis=score256["primary_axis"],
            budget=TrackAWorkBudget(**score256["budget"]),
            schema_version=score256["schema_version"],
        )
        corrected_result = run_countdown_track_a_search(
            task,
            proposal=proposal,
            method=method,
            budget_profile=corrected,
            exploration_seed=7168,
        )
        self.assertTrue(corrected_result.summary["budget_valid"])
        self.assertEqual(
            corrected_result.summary["stop_blocked_axes"],
            ["legal_action_scores"],
        )
        self.assertEqual(
            corrected_result.summary["stop_reason"],
            "primary_budget_blocked",
        )

    def test_analysis_and_canary_gates_are_frozen_without_canary_statistics(
        self,
    ) -> None:
        prereg = self.payloads["preregistration.json"]
        canary = prereg["analysis_freeze"]["canary"]
        self.assertFalse(canary["confidence_intervals"])
        self.assertFalse(canary["p_values"])
        self.assertFalse(canary["performance_promotion_decisions"])
        pareto = canary["simple_baseline_pareto_diagnostic"]
        self.assertIn("pareto_definition", pareto)
        self.assertIn("IID and Sobol", pareto["candidate_task_score"])
        self.assertIn("both baselines", pareto["pareto_definition"])
        canary_metric = canary["task_metric_schema"]
        self.assertEqual(
            canary_metric["stochastic_seed_order"],
            [7168, 7169, 7170, 7171],
        )
        self.assertIn("within task", canary_metric["stochastic_method"])
        self.assertIn("12 task", canary_metric["cross_task_summary"])

        locked = prereg["analysis_freeze"]["locked_evaluation"]
        bootstrap = locked["bootstrap_generator"]
        self.assertEqual(bootstrap["draw_count"], 10_000)
        self.assertEqual(
            bootstrap["generator"]["version"],
            "sha256-counter-rejection-index/v1",
        )
        bootstrap_vector = bootstrap["test_vector"]
        digest = hashlib.sha256(
            bootstrap_vector["message"].encode("ascii")
        ).hexdigest()
        self.assertEqual(digest, bootstrap_vector["digest"])
        word = int(digest[:16], 16)
        self.assertEqual(word, bootstrap_vector["first_64_bits_big_endian"])
        self.assertEqual(
            word % 128,
            bootstrap_vector["accepted_index_for_task_count_128"],
        )
        contracts = locked["bootstrap_contracts"]
        self.assertEqual(contracts["track_a_locked_128"]["task_count"], 128)
        self.assertEqual(contracts["track_b_provider_16"]["task_count"], 16)
        self.assertEqual(contracts["track_a_locked_128"]["seed"], 26072603)
        self.assertEqual(contracts["track_b_provider_16"]["seed"], 26072603)
        self.assertEqual(
            locked["quantiles"]["fractions"][
                "three_way_simultaneous_98_1_3_percent"
            ],
            [
                {"denominator": 120, "numerator": 1},
                {"denominator": 120, "numerator": 119},
            ],
        )
        quantile_vector = locked["quantiles"]["test_vector"]
        values = quantile_vector["sorted_values"]
        probability = quantile_vector["probability"]
        h_numerator = (len(values) - 1) * probability["numerator"]
        index, remainder = divmod(h_numerator, probability["denominator"])
        quantile_numerator = (
            (probability["denominator"] - remainder) * values[index]
            + remainder * values[index + 1]
        )
        expected = quantile_vector["expected_quantile"]
        self.assertEqual(
            quantile_numerator * expected["denominator"],
            expected["numerator"] * probability["denominator"],
        )
        self.assertIn("unrounded", locked["decision_precision"])
        for label, comparator in locked["decision_comparators"].items():
            expected = ">=" if "point_margin" in label else ">"
            self.assertEqual(comparator["operator"], expected)
        self.assertEqual(
            locked["task_metric_schema"]["locked_stochastic_seed_order"],
            list(range(4096, 4112)),
        )
        self.assertEqual(
            locked["paired_vector_schema"]["missing_or_budget_invalid_cell"],
            "fail_entire_gate",
        )
        families = locked["decision_families"]
        self.assertEqual(
            families["calibration_guardrails"]["multiplicity_method"],
            "bonferroni",
        )
        self.assertEqual(
            families["sobol_track_b_provider_guardrails"]["bootstrap_contract"],
            "track_b_provider_16",
        )
        self.assertEqual(
            locked["decision_outputs"]["calibration_transfer_decision"][
                "required_families"
            ],
            ["calibration_primary", "calibration_guardrails"],
        )

        gates = prereg["gates"]
        self.assertEqual(
            gates["oracle_greedy_positive_control"],
            {"expected_cells": 24, "required_successful_cells": 24},
        )
        self.assertEqual(
            gates["primary_adaptive_signal"]["method_labels"],
            [
                "puct_c1",
                "thompson_frozen_iid",
                "thompson_frozen_sobol",
                "thompson_candidate_iid",
                "thompson_candidate_sobol",
            ],
        )
        self.assertEqual(
            gates["profile_closure"]["score256_adaptive"]["blocked_axes"],
            ["legal_action_scores"],
        )
        self.assertEqual(
            gates["coordinate_accounting"][
                "deterministic_generated_coordinates"
            ],
            0,
        )

    def test_implementation_and_runtime_provenance_are_bound(self) -> None:
        self.assertEqual(
            self.payloads["preregistration.json"]["implementation_base"],
            IMPLEMENTATION_BASE,
        )
        self.assertEqual(
            self.payloads["seal.json"]["implementation_base"],
            IMPLEMENTATION_BASE,
        )
        runtimes = self.payloads["methods.json"]["runtime_bindings"]
        frozen = frozen_track_a_canary_runtime_bindings()
        self.assertEqual(runtimes, frozen)
        for row in runtimes.values():
            self.assertEqual(row["digest"], sha256_json(row["metadata"]))

        def frozen_perturbation(
            source: str,
            *,
            refresh_conformance: bool = False,
        ) -> dict[str, object]:
            self.assertIs(type(refresh_conformance), bool)
            return deepcopy(frozen[source]["metadata"])

        with (
            patch.object(
                manifest_module,
                "search_runtime_metadata",
                return_value=deepcopy(frozen["search"]["metadata"]),
            ),
            patch.object(
                manifest_module,
                "perturbation_runtime_metadata",
                side_effect=frozen_perturbation,
            ),
        ):
            qualification = qualify_track_a_canary_runtime()
        self.assertEqual(qualification["status"], "RUNTIME_QUALIFIED")
        self.assertFalse(qualification["execution_authorized"])

        changed = deepcopy(frozen["search"]["metadata"])
        changed["python_version"] = "tampered"
        with (
            patch.object(
                manifest_module,
                "search_runtime_metadata",
                return_value=changed,
            ),
            patch.object(
                manifest_module,
                "perturbation_runtime_metadata",
                side_effect=frozen_perturbation,
            ),
            self.assertRaisesRegex(CanaryManifestError, "frozen canary runtime"),
        ):
            qualify_track_a_canary_runtime()

        perturbations_module._runtime_conformance_digest.cache_clear()
        with patch.object(
            perturbations_module,
            "_compute_runtime_conformance_digest",
            return_value="0" * 64,
        ):
            poisoned = manifest_module.perturbation_runtime_metadata("iid")
        self.assertEqual(poisoned["runtime_conformance_digest"], "0" * 64)
        refreshed = manifest_module.perturbation_runtime_metadata(
            "iid",
            refresh_conformance=True,
        )
        subsequent = manifest_module.perturbation_runtime_metadata("iid")
        self.assertEqual(
            subsequent["runtime_conformance_digest"],
            refreshed["runtime_conformance_digest"],
        )
        self.assertNotEqual(refreshed["runtime_conformance_digest"], "0" * 64)

    def test_runtime_qualification_recomputes_perturbation_conformance(self) -> None:
        manifest_module.perturbation_runtime_metadata("iid")
        with (
            patch.object(
                perturbations_module,
                "_iid_uniforms",
                return_value=(0.5,) * 8,
            ),
            self.assertRaisesRegex(CanaryManifestError, "frozen canary runtime"),
        ):
            qualify_track_a_canary_runtime()

        changed_methods = deepcopy(self.payloads["methods.json"])
        changed_runtime = changed_methods["runtime_bindings"]["search"]
        changed_runtime["metadata"]["python_version"] = "tampered"
        changed_runtime["digest"] = sha256_json(changed_runtime["metadata"])
        changed_core = {
            key: value
            for key, value in changed_methods.items()
            if key != "deterministic_digest"
        }
        changed_methods["deterministic_digest"] = sha256_json(changed_core)
        changed_cells = manifest_module._cells_from_components(
            self.payloads["tasks.json"],
            self.payloads["proposals.json"],
            changed_methods,
            self.payloads["budgets.json"],
        )
        original_ids = [cell.cell_id for cell in self.verified.cells]
        changed_ids = [cell.cell_id for cell in changed_cells]
        self.assertEqual(len(original_ids), len(changed_ids))
        self.assertTrue(
            all(original != changed for original, changed in zip(original_ids, changed_ids))
        )

    def test_packaged_historical_source_is_an_exact_sha_bound_mirror(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        authoritative = (
            repository_root / manifest_module.HISTORICAL_SOURCE_PATH
        ).read_bytes()
        packaged = resource_files("qmc_bmgs.data").joinpath(
            manifest_module.HISTORICAL_PACKAGED_RESOURCE
        ).read_bytes()
        self.assertEqual(packaged, authoritative)
        self.assertEqual(
            hashlib.sha256(packaged).hexdigest(),
            manifest_module.HISTORICAL_SOURCE_SHA256,
        )
        source = self.payloads["exclusions.json"]["source"]
        self.assertEqual(
            source["packaged_resource"],
            "qmc_bmgs.data/countdown_calibration_grid_v1.json",
        )

    def test_builder_never_calls_search_proposals_or_task_points(self) -> None:
        with (
            patch(
                "qmc_bmgs.substrate.countdown_search."
                "run_countdown_track_a_search",
                side_effect=AssertionError("search must not run"),
            ),
            patch(
                "qmc_bmgs.substrate.proposals.evaluate_track_a_proposal",
                side_effect=AssertionError("proposal rows must not be evaluated"),
            ),
            patch(
                "qmc_bmgs.substrate.perturbations.generate_perturbation_point",
                side_effect=AssertionError("task points must not materialize"),
            ),
        ):
            payloads = build_track_a_canary_payloads()
        self.assertEqual(
            payloads["preregistration.json"]["materialization_contract"][
                "task_specific_perturbation_points_in_bundle"
            ],
            0,
        )

    def test_publication_is_no_overwrite_and_directory_closed(self) -> None:
        before = {
            path.name: path.read_bytes() for path in self.bundle_path.iterdir()
        }
        with self.assertRaises(FileExistsError):
            write_track_a_canary_bundle(self.bundle_path)
        after = {
            path.name: path.read_bytes() for path in self.bundle_path.iterdir()
        }
        self.assertEqual(before, after)

        copied = self.root / "extra-file"
        shutil.copytree(self.bundle_path, copied)
        (copied / "unexpected.json").write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(CanaryManifestError, "directory closure"):
            verify_track_a_canary_bundle(copied)

        noncanonical = self.root / "noncanonical"
        shutil.copytree(self.bundle_path, noncanonical)
        task_payload = json.loads((noncanonical / "tasks.json").read_text())
        (noncanonical / "tasks.json").write_text(
            json.dumps(task_payload, indent=2) + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(CanaryManifestError, "not canonical"):
            verify_track_a_canary_bundle(noncanonical)

    def test_raced_empty_destination_is_not_replaced(self) -> None:
        destination = self.root / "raced-destination"
        real_publish = manifest_module._rename_directory_noreplace

        def create_raced_destination(source: Path, target: Path) -> None:
            target.mkdir()
            real_publish(source, target)

        with (
            patch.object(
                manifest_module,
                "_rename_directory_noreplace",
                side_effect=create_raced_destination,
            ),
            self.assertRaises(FileExistsError),
        ):
            write_track_a_canary_bundle(destination)
        self.assertTrue(destination.is_dir())
        self.assertEqual(list(destination.iterdir()), [])
        self.assertFalse(
            (destination.parent / f".{destination.name}.publish-lock").exists()
        )

    def test_strict_json_symlink_and_directory_tampering_fail_closed(self) -> None:
        duplicate = self.root / "duplicate-key"
        shutil.copytree(self.bundle_path, duplicate)
        path = duplicate / "tasks.json"
        raw = path.read_text(encoding="utf-8")
        path.write_text(
            raw.replace(
                '"schema_version":',
                '"schema_version":"duplicate","schema_version":',
                1,
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(CanaryManifestError, "invalid strict JSON"):
            verify_track_a_canary_bundle(duplicate)

        nonfinite = self.root / "nonfinite"
        shutil.copytree(self.bundle_path, nonfinite)
        path = nonfinite / "tasks.json"
        raw = path.read_text(encoding="utf-8")
        path.write_text(
            raw.replace('"task_count":12', '"task_count":NaN', 1),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(CanaryManifestError, "invalid strict JSON"):
            verify_track_a_canary_bundle(nonfinite)

        symlinked = self.root / "symlinked"
        shutil.copytree(self.bundle_path, symlinked)
        target = self.root / "symlink-target.json"
        shutil.copyfile(symlinked / "tasks.json", target)
        (symlinked / "tasks.json").unlink()
        (symlinked / "tasks.json").symlink_to(target)
        with self.assertRaisesRegex(CanaryManifestError, "not a regular file"):
            verify_track_a_canary_bundle(symlinked)

        extra_directory = self.root / "extra-directory"
        shutil.copytree(self.bundle_path, extra_directory)
        (extra_directory / "undeclared").mkdir()
        with self.assertRaisesRegex(CanaryManifestError, "directory closure"):
            verify_track_a_canary_bundle(extra_directory)

    def test_self_consistent_semantic_tampering_fails_regeneration(self) -> None:
        copied = self.root / "rehashed-tamper"
        shutil.copytree(self.bundle_path, copied)
        tasks = json.loads((copied / "tasks.json").read_text())
        tasks["cohort_role"] = "tampered"
        task_core = {
            key: value for key, value in tasks.items() if key != "deterministic_digest"
        }
        tasks["deterministic_digest"] = sha256_json(task_core)
        task_raw = _write_canonical(copied / "tasks.json", tasks)

        seal = json.loads((copied / "seal.json").read_text())
        seal["component_files"]["tasks.json"] = {
            "byte_count": len(task_raw),
            "deterministic_digest": tasks["deterministic_digest"],
            "sha256": hashlib.sha256(task_raw).hexdigest(),
        }
        seal_core = {
            key: value for key, value in seal.items() if key != "deterministic_digest"
        }
        seal["deterministic_digest"] = sha256_json(seal_core)
        _write_canonical(copied / "seal.json", seal)
        with self.assertRaisesRegex(
            CanaryManifestError,
            "independent deterministic regeneration",
        ):
            verify_track_a_canary_bundle(copied)

    def test_rehashed_numeric_type_alias_fails_exact_byte_regeneration(self) -> None:
        copied = self.root / "numeric-alias"
        shutil.copytree(self.bundle_path, copied)
        tasks = json.loads((copied / "tasks.json").read_text())
        tasks["task_count"] = 12.0
        task_core = {
            key: value for key, value in tasks.items() if key != "deterministic_digest"
        }
        tasks["deterministic_digest"] = sha256_json(task_core)
        task_raw = _write_canonical(copied / "tasks.json", tasks)

        seal = json.loads((copied / "seal.json").read_text())
        seal["component_files"]["tasks.json"] = {
            "byte_count": len(task_raw),
            "deterministic_digest": tasks["deterministic_digest"],
            "sha256": hashlib.sha256(task_raw).hexdigest(),
        }
        seal_core = {
            key: value for key, value in seal.items() if key != "deterministic_digest"
        }
        seal["deterministic_digest"] = sha256_json(seal_core)
        _write_canonical(copied / "seal.json", seal)
        with self.assertRaisesRegex(
            CanaryManifestError,
            "independent deterministic regeneration",
        ):
            verify_track_a_canary_bundle(copied)

    def test_verification_rechecks_directory_closure_after_regeneration(self) -> None:
        copied = self.root / "verify-race"
        shutil.copytree(self.bundle_path, copied)
        real_build = manifest_module.build_track_a_canary_payloads

        def mutate_after_initial_snapshot(*args: object, **kwargs: object):
            expected = real_build(*args, **kwargs)
            (copied / "unexpected.json").write_text("{}\n", encoding="utf-8")
            return expected

        with (
            patch.object(
                manifest_module,
                "build_track_a_canary_payloads",
                side_effect=mutate_after_initial_snapshot,
            ),
            self.assertRaisesRegex(CanaryManifestError, "directory closure"),
        ):
            verify_track_a_canary_bundle(copied)

    def test_verification_rejects_directory_symlink_swap(self) -> None:
        copied = self.root / "verify-symlink-race"
        moved = self.root / "verify-symlink-target"
        shutil.copytree(self.bundle_path, copied)
        real_build = manifest_module.build_track_a_canary_payloads

        def swap_path_after_initial_snapshot(*args: object, **kwargs: object):
            expected = real_build(*args, **kwargs)
            copied.rename(moved)
            copied.symlink_to(moved, target_is_directory=True)
            return expected

        with (
            patch.object(
                manifest_module,
                "build_track_a_canary_payloads",
                side_effect=swap_path_after_initial_snapshot,
            ),
            self.assertRaisesRegex(CanaryManifestError, "regular directory"),
        ):
            verify_track_a_canary_bundle(copied)

    def test_tracked_bundle_is_exactly_regenerable(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        tracked = repository_root / (
            "docs/preregistrations/countdown_track_a_canary_v2"
        )
        verified = verify_track_a_canary_bundle(
            tracked,
            repository_root=repository_root,
        )
        self.assertEqual(len(verified.cells), EXPECTED_CELL_COUNT)
        self.assertEqual(
            verified.seal_digest,
            "5799c9f17686f064b7c50ee741d79bfbb14a4d61b9048672068a586b258fd437",
        )

    def test_verified_payload_property_is_defensive(self) -> None:
        first = self.verified.payloads
        second = self.verified.payloads
        first["tasks.json"]["task_count"] = 0
        self.assertEqual(second["tasks.json"]["task_count"], 12)
        self.assertEqual(set(second), set(BUNDLE_FILENAMES))


if __name__ == "__main__":
    unittest.main()
