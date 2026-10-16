"""Identity-only v6 contract tests; no new cohort, solver, search or outcomes."""

from __future__ import annotations

import copy
import importlib.util
from itertools import product
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from qmc_bmgs.benchmarks import countdown
from qmc_bmgs.experiments import countdown_thompson_dense_scale_runner as old_runner
from qmc_bmgs.substrate import countdown_search, proposals, perturbations


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/feedback_budget_development_contract.py"
SPEC = importlib.util.spec_from_file_location("feedback_budget_contract_tested", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def rehash(payload):
    return module.core.with_digest(
        {key: value for key, value in payload.items() if key != "deterministic_digest"}
    )


class DevelopmentContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = module.build_contract()
        cls.identities = module.synthetic_identities()
        cls.candidate = module.build_schedule_candidate(cls.identities)

    def test_build_uses_no_generator_solver_search_proposal_or_point(self):
        with (
            patch.object(
                countdown, "generate_solvable_task_suite", side_effect=AssertionError
            ),
            patch.object(
                countdown_search,
                "run_countdown_track_a_search",
                side_effect=AssertionError,
            ),
            patch.object(
                module.q, "run_countdown_track_a_search", side_effect=AssertionError
            ),
            patch.object(
                proposals, "evaluate_track_a_proposal", side_effect=AssertionError
            ),
            patch.object(
                perturbations,
                "perturbation_runtime_metadata",
                side_effect=AssertionError,
            ),
        ):
            actual = module.self_test()
        self.assertEqual(actual["search_executions"], 0)
        self.assertEqual(actual["new_development_tasks_generated"], 0)
        self.assertFalse(actual["development_execution_authorized"])

    def test_all_six_exclusion_boundaries_and_public_shared_source_survive(self):
        exclusions = self.contract["exclusion_identities"]
        for row, (label, task_count, source_count) in zip(
            exclusions["cohorts"], module.COHORTS
        ):
            self.assertEqual(row["label"], label)
            self.assertEqual(len(row["task_fingerprints"]), task_count)
            self.assertEqual(len(row["source_multiset_fingerprints"]), source_count)
        self.assertEqual(exclusions["task_fingerprint_count"], 179)
        self.assertEqual(exclusions["source_multiset_fingerprint_count"], 167)
        self.assertFalse(exclusions["locked_128_evaluation_authorized"])

    def test_recipe_and_all_unmet_gates_remain_explicit(self):
        recipe = self.contract["generation_recipe"]
        self.assertEqual(
            (recipe["count"], recipe["seed"], recipe["max_attempts"]),
            (12, 26090401, 10000),
        )
        self.assertEqual(
            (recipe["input_count"], recipe["input_min"], recipe["input_max"]),
            (6, 1, 10),
        )
        self.assertEqual((recipe["target_min"], recipe["target_max"]), (100, 999))
        for key in (
            "cohort_generated",
            "cohort_sealed",
            "development_execution_authorized",
            "locked_128_evaluation_authorized",
            "prior_authorization_reusable",
        ):
            self.assertIs(self.contract[key], False)
        qualification = self.contract["qualification_references"]
        for key in (
            "production_runner_qualified",
            "production_analyzer_qualified",
            "production_publication_qualified",
        ):
            self.assertIs(qualification[key], False)

    def test_budget_specs_only_differ_in_primary_budget_and_profile_identity(self):
        low, high = (copy.deepcopy(row["spec"]) for row in self.contract["budgets"])
        self.assertNotEqual(low, high)
        low["profile_id"] = high["profile_id"]
        low["budget"]["legal_action_scores"] = high["budget"]["legal_action_scores"]
        self.assertEqual(low, high)
        self.assertEqual(
            high["budget"],
            dict(zip(module.q.TRACK_A_WORK_AXES, (172, 573, 512, 572, 171, 171, 35))),
        )

    def test_192_cells_are_unique_exactly_ordered_and_bind_all_components(self):
        cells = self.candidate["cells"]
        self.assertEqual(len(cells), 192)
        self.assertEqual(len({cell["cell_id"] for cell in cells}), 192)
        coordinates = list(
            product(range(12), (256, 512), (0, 16), (8192, 8193, 8194, 8195))
        )
        for index, (cell, coordinates) in enumerate(zip(cells, coordinates)):
            key = cell["cell_key"]
            self.assertEqual(cell["cell_index"], index)
            self.assertEqual(
                tuple(key[k] for k in ("task_slot", "budget", "scale", "seed")),
                coordinates,
            )
            self.assertEqual(cell["cell_id"], module.digest(key))
            self.assertEqual(
                key["contract_digest"], self.contract["deterministic_digest"]
            )
            self.assertEqual(
                key["candidate_identity_digest"], module.digest(self.identities)
            )
            self.assertEqual(
                key["task_fingerprint"],
                self.identities[key["task_slot"]]["task_fingerprint"],
            )
            self.assertEqual(
                key["source_multiset_fingerprint"],
                self.identities[key["task_slot"]]["source_multiset_fingerprint"],
            )

    def test_96_budget_pairs_cover_every_cell_once_without_scale_or_seed_crossing(self):
        cells = {cell["cell_id"]: cell["cell_key"] for cell in self.candidate["cells"]}
        used = []
        pairs = self.candidate["budget_prefix_pairs"]
        self.assertEqual(len(pairs), 96)
        for pair in pairs:
            low, high = cells[pair["low_cell_id"]], cells[pair["high_cell_id"]]
            self.assertEqual((low["budget"], high["budget"]), (256, 512))
            for key in (
                "task_slot",
                "task_fingerprint",
                "source_multiset_fingerprint",
                "scale",
                "seed",
            ):
                self.assertEqual(low[key], high[key])
            used.extend((pair["low_cell_id"], pair["high_cell_id"]))
        self.assertEqual(sorted(used), sorted(cells))

    def test_48_four_arm_blocks_match_the_frozen_estimand_arm_order(self):
        cells = {cell["cell_id"]: cell["cell_key"] for cell in self.candidate["cells"]}
        used = []
        self.assertEqual(len(self.candidate["four_cell_blocks"]), 48)
        for block in self.candidate["four_cell_blocks"]:
            for cell_id, (budget, scale) in zip(block["arm_cell_ids"], module.ARMS):
                key = cells[cell_id]
                self.assertEqual(
                    (key["task_slot"], key["seed"]), (block["task_slot"], block["seed"])
                )
                self.assertEqual((key["budget"], key["scale"]), (budget, scale))
                used.append(cell_id)
        self.assertEqual(sorted(used), sorted(cells))

    def test_both_identity_kinds_reject_overlap_in_every_exclusion_cohort(self):
        for row in self.contract["exclusion_identities"]["cohorts"]:
            for singular, plural in (
                ("task_fingerprint", "task_fingerprints"),
                ("source_multiset_fingerprint", "source_multiset_fingerprints"),
            ):
                with self.subTest(cohort=row["label"], field=singular):
                    identities = copy.deepcopy(self.identities)
                    identities[0][singular] = row[plural][0]
                    with self.assertRaisesRegex(
                        module.ContractError, "excluded identity"
                    ):
                        module.build_schedule_candidate(identities)

    def test_duplicate_source_or_full_task_fails_even_with_distinct_other_identity(
        self,
    ):
        for field in ("task_fingerprint", "source_multiset_fingerprint"):
            identities = copy.deepcopy(self.identities)
            identities[1][field] = identities[0][field]
            with self.assertRaisesRegex(module.ContractError, "duplicate candidate"):
                module.build_schedule_candidate(identities)

    def test_shape_reordering_numeric_aliases_and_unknown_identity_material_fail(self):
        variants = [
            self.identities[:-1],
            self.identities + [self.identities[-1]],
            list(reversed(self.identities)),
        ]
        for field, value in (
            ("task_slot", False),
            ("task_slot", 0.0),
            ("task_fingerprint", "a" * 40),
            ("source_multiset_fingerprint", None),
            ("solution_witness", "forbidden"),
            ("search_record", {}),
        ):
            identities = copy.deepcopy(self.identities)
            identities[0][field] = value
            variants.append(identities)
        for identities in variants:
            with self.subTest(identities=identities[:1]), self.assertRaises(ValueError):
                module.build_schedule_candidate(identities)

    def test_identity_change_rekeys_entire_candidate_not_only_one_task(self):
        identities = copy.deepcopy(self.identities)
        identities[-1]["task_fingerprint"] = module.digest("another synthetic task")
        changed = module.build_schedule_candidate(identities)
        self.assertNotEqual(
            changed["candidate_identity_digest"],
            self.candidate["candidate_identity_digest"],
        )
        self.assertFalse(
            {c["cell_id"] for c in changed["cells"]}
            & {c["cell_id"] for c in self.candidate["cells"]}
        )

    def test_rehashed_missing_reordered_tampered_cells_pairs_and_blocks_fail(self):
        for field in ("cells", "budget_prefix_pairs", "four_cell_blocks"):
            for operation in ("drop", "reorder"):
                value = copy.deepcopy(self.candidate)
                if operation == "drop":
                    value[field].pop()
                else:
                    value[field][0], value[field][1] = value[field][1], value[field][0]
                with (
                    self.subTest(field=field, operation=operation),
                    self.assertRaises(ValueError),
                ):
                    module.validate_schedule_candidate(module.canonical(rehash(value)))
        value = copy.deepcopy(self.candidate)
        value["cells"][0]["cell_key"]["budget"] = 257
        value["cells"][0]["cell_id"] = module.digest(value["cells"][0]["cell_key"])
        value["schedule_digest"] = module.digest(value["cells"])
        with self.assertRaisesRegex(module.ContractError, "exact regeneration"):
            module.validate_schedule_candidate(module.canonical(rehash(value)))

    def test_candidate_cannot_self_promote_to_sealed_solvable_or_authorized(self):
        for field in (
            "solvability_verified",
            "generation_order_verified",
            "cohort_sealed",
            "production_cell_keys_materialized",
            "development_execution_authorized",
        ):
            value = copy.deepcopy(self.candidate)
            value[field] = True
            with self.subTest(field=field), self.assertRaises(ValueError):
                module.validate_schedule_candidate(module.canonical(rehash(value)))

    def test_candidate_and_planned_production_domains_are_separate_from_public_and_v5(
        self,
    ):
        schemas = self.contract["planned_production_schemas"]
        self.assertEqual(len(set(schemas.values())), 8)
        self.assertNotIn(
            self.candidate["cells"][0]["cell_key"]["schema_version"], schemas.values()
        )
        with self.assertRaises(ValueError):
            old_runner.validate_authorization(module.canonical(self.contract))
        with self.assertRaises(ValueError):
            old_runner.validate_authorization(
                module.canonical(self.candidate), fixture=True
            )
        public = module.core.parse_canonical((ROOT / module.PUBLIC).read_bytes())
        with self.assertRaises(ValueError):
            module.validate_schedule_candidate(module.canonical(public))

    def test_strict_canonical_json_rejects_duplicate_nonfinite_and_pretty_aliases(self):
        for raw in (
            b'{"a":1,"a":2}\n',
            b'{"x":NaN}\n',
            b'{"x":1e999}\n',
            b"[]\n",
            json.dumps(self.candidate, indent=2).encode(),
        ):
            with self.subTest(raw=raw[:30]), self.assertRaises(ValueError):
                module.validate_schedule_candidate(raw)

    def test_returned_contract_and_candidate_do_not_alias_mutable_inputs(self):
        value = module.build_contract()
        value["generation_recipe"]["seed"] = 0
        self.assertEqual(module.build_contract(), self.contract)
        identities = copy.deepcopy(self.identities)
        candidate = module.build_schedule_candidate(identities)
        identities[0]["task_fingerprint"] = "0" * 64
        self.assertEqual(candidate, self.candidate)

    def test_changed_qualified_component_spec_is_rejected(self):
        class WrongProfile:
            def to_dict(self):
                return {"profile_id": "same label is insufficient"}

        with (
            patch.object(module.q, "profile", return_value=WrongProfile()),
            self.assertRaisesRegex(module.ContractError, "qualified component spec"),
        ):
            module.build_contract()

    def test_every_pinned_file_is_required_and_hash_checked(self):
        with tempfile.TemporaryDirectory(prefix="v6-contract-") as temporary:
            # The macOS /var temporary prefix is an alias. Keep the production
            # reader's no-follow requirement; give this fixture its real path.
            root = Path(temporary).resolve()
            for relative in module.PINNED_FILES:
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, target)
            self.assertEqual(module.build_contract(root), self.contract)
            for relative in module.PINNED_FILES:
                target = root / relative
                original = target.read_bytes()
                target.write_bytes(original + b"\n")
                with (
                    self.subTest(relative=relative),
                    self.assertRaisesRegex(
                        module.ContractError, "pinned input changed"
                    ),
                ):
                    module.build_contract(root)
                target.unlink()
                with self.subTest(missing=relative), self.assertRaises(ValueError):
                    module.build_contract(root)
                target.write_bytes(original)

    def test_all_input_snapshots_are_revalidated_after_contract_construction(self):
        original = module.core.FileSnapshot.revalidate
        observed = []

        def revalidate(snapshot):
            observed.append(snapshot.path)
            original(snapshot)

        with patch.object(
            module.core.FileSnapshot,
            "revalidate",
            autospec=True,
            side_effect=revalidate,
        ):
            self.assertEqual(module.build_contract(), self.contract)
        self.assertEqual(
            observed, [ROOT / relative for relative in module.PINNED_FILES]
        )

        def reject_last(snapshot):
            if snapshot.path == ROOT / module.SUMMARY:
                raise ValueError("late input change")
            original(snapshot)

        with patch.object(
            module.core.FileSnapshot,
            "revalidate",
            autospec=True,
            side_effect=reject_last,
        ):
            with self.assertRaisesRegex(ValueError, "late input change"):
                module.build_contract()

    def test_cli_has_no_generation_execution_or_authorization_path(self):
        for option in (
            "--run",
            "--generate",
            "--seal",
            "--authorize",
            "--task",
            "--seed",
        ):
            result = subprocess.run(
                [sys.executable, "-B", str(SCRIPT), option], capture_output=True
            )
            self.assertEqual(result.returncode, 2)
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--self-test"],
            capture_output=True,
            check=True,
        )
        self.assertEqual(json.loads(result.stdout)["synthetic_cell_count"], 192)


if __name__ == "__main__":
    unittest.main()
