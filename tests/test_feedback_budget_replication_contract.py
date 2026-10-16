"""v7 identity-only compilation, fixed PUBLIC definitions and admission separation."""

from __future__ import annotations

from contextlib import ExitStack
import copy
import importlib.util
from itertools import product
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/feedback_budget_replication_contract.py"
SPEC = importlib.util.spec_from_file_location("replication_contract_tested", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
C = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(C)


def redigest(value):
    value = copy.deepcopy(value)
    value.pop("deterministic_digest", None)
    return C.core.with_digest(value)


class ReplicationContractTests(unittest.TestCase):
    def setUp(self):
        self.contract = C.build_contract()

    def test_exact_design_recipe_factors_and_new_domain(self):
        value = self.contract
        self.assertEqual(value["schema_version"], C.DOMAIN + "/contract-candidate")
        self.assertNotEqual(C.DOMAIN, C.old.DOMAIN)
        self.assertNotEqual(C.EXPERIMENT_ID, C.old.EXPERIMENT_ID)
        self.assertEqual(value["task_count"], 64)
        self.assertEqual(
            value["generation_recipe"],
            {
                "function": "generate_solvable_task_suite",
                "generator": "sha256-counter-mod/v1",
                "count": 64,
                "seed": 26091301,
                "max_attempts": 10000,
                "input_count": 6,
                "input_min": 1,
                "input_max": 10,
                "target_min": 100,
                "target_max": 999,
                "acceptance": "exhaustive_solvability_and_both_identity_exclusions_only",
                "task_order": "generator_acceptance_order",
                "persist_solution_witnesses": False,
                "hardness_selection_allowed": False,
            },
        )
        self.assertEqual(value["exploration_seeds"], [8192, 8193, 8194, 8195])
        self.assertEqual(value["planned_cell_count"], 1024)
        self.assertEqual(value["planned_budget_prefix_count"], 512)
        self.assertEqual(value["planned_four_cell_block_count"], 256)

    def test_unchanged_qualified_specs_and_runtime_requirement(self):
        old = C.old.build_contract()
        for key in ("budgets", "methods", "proposal", "runtime_requirement"):
            self.assertEqual(C.canonical(self.contract[key]), C.canonical(old[key]))
        profiles = {row["budget"]: row["spec"] for row in self.contract["budgets"]}
        self.assertEqual(profiles[256]["primary_axis"], "legal_action_scores")
        self.assertEqual(self.contract["screen"]["minimum_effect_numerator"], 11)
        self.assertEqual(
            self.contract["screen"]["effect_floor"], {"numerator": 1, "denominator": 24}
        )
        self.assertEqual(self.contract["screen"]["minimum_rescued_tasks"], 11)

    def test_complete_screen_conjunction_is_metadata_not_a_production_decision(self):
        screen = self.contract["screen"]
        self.assertEqual(screen["minimum_low_budget_uplift_numerator"], 0)
        self.assertEqual(screen["maximum_high_budget_lost_exact_successes"], 0)
        self.assertEqual(screen["leave_one_task_out_block_count"], 252)
        self.assertEqual(
            screen["strictly_positive_leave_one_task_out_estimands"],
            ["high_budget_uplift", "interaction"],
        )
        self.assertTrue(
            screen["all_high_budget_rescues_require_prior_differing_applied_backup"]
        )
        self.assertEqual(
            screen["pass_label"], "SOURCE_DISJOINT_REPLICATION_SCREEN_PASS"
        )
        self.assertEqual(
            screen["valid_failure_label"], "STOP_REPAIR_REPLICATION_SCREEN_NOT_MET"
        )
        self.assertEqual(screen["integrity_failure_label"], "INVALID_ANALYSIS")
        self.assertFalse(screen["production_screen_implemented"])

    def test_all_eight_groups_and_exact_overlapping_PUBLIC_union(self):
        exclusions = self.contract["exclusion_identities"]
        groups = exclusions["cohorts"]
        self.assertEqual(
            [
                (
                    row["label"],
                    len(row["task_fingerprints"]),
                    len(row["source_multiset_fingerprints"]),
                )
                for row in groups
            ],
            list(C.COHORTS),
        )
        for field, count in (
            ("task_fingerprints", 243),
            ("source_multiset_fingerprints", 179),
        ):
            union = set().union(*(set(row[field]) for row in groups))
            self.assertEqual(exclusions[field], sorted(union))
            self.assertEqual(len(union), count)
            self.assertEqual(
                set(groups[-2][field]).intersection(
                    set().union(*(set(row[field]) for row in groups[:-2]))
                ),
                set(),
            )
        self.assertEqual(
            exclusions["overlap_with_earlier_groups"]["replication_public_fixtures"],
            {"task_fingerprints": 13, "source_multiset_fingerprints": 1},
        )
        self.assertEqual(
            len(
                set(groups[-1]["task_fingerprints"])
                - set(groups[-3]["task_fingerprints"])
            ),
            52,
        )

    def test_all_v6_tasks_are_excluded_not_just_rescues(self):
        seal = C.core.parse_canonical((ROOT / C.V6).read_bytes())
        groups = self.contract["exclusion_identities"]["cohorts"]
        v6 = groups[-2]
        for field in ("task_fingerprint", "source_multiset_fingerprint"):
            self.assertEqual(
                v6[field + "s"], sorted(row[field] for row in seal["cohort"]["tasks"])
            )
            self.assertEqual(len(v6[field + "s"]), 12)

    def test_seal_markers_and_result_anchors_remain_pinned(self):
        pins = C.pinned_files()
        for path in (
            C.V6,
            C.V6_STARTED,
            C.V6_SEALED,
            C.V6_CANDIDATE,
            C.V6_SUMMARY,
            C.V6_COMMIT,
        ):
            self.assertIn(path, pins)
            self.assertEqual(C.sha((ROOT / path).read_bytes()), pins[path])
        self.assertEqual(
            self.contract["historical_v6_summary_digest"],
            "a9087a60d439d7d8e48d3a26da9028e1f9b230b21853ec8b0f678bb8063918a8",
        )
        self.assertFalse(self.contract["historical_evidence_is_replication_evidence"])

    def test_every_pinned_input_is_required_and_hash_checked(self):
        original = C.core.FileSnapshot.capture
        for path in C.pinned_files():

            def corrupt(candidate, *args, **kwargs):
                if Path(candidate) == ROOT / path:
                    return SimpleNamespace(raw=b"changed\n")
                return original(candidate, *args, **kwargs)

            with (
                self.subTest(path=path),
                patch.object(C.core.FileSnapshot, "capture", side_effect=corrupt),
                self.assertRaisesRegex(ValueError, "fixed input changed"),
            ):
                C.build_contract()

    def test_qualification_plan_does_not_claim_execution_or_transferred_receipts(self):
        plan = self.contract["qualification_plan"]
        self.assertEqual(plan["component_cells_total"], 32)
        self.assertEqual(plan["full_shape_cells"], 1024)
        self.assertEqual(plan["full_shape_budget_prefix_pairs"], 512)
        self.assertFalse(plan["actual_qualification_performed"])
        self.assertFalse(plan["historical_qualification_transfers_to_new_pipeline"])
        self.assertTrue(plan["all_fixture_variants_must_precede_new_cohort_generation"])
        self.assertEqual(len(self.contract["missing_gates"]), 6)
        for key, value in C.not_authority().items():
            self.assertEqual(self.contract[key], value)
        self.assertFalse(self.contract["screen"]["production_screen_implemented"])

    def test_no_generator_solver_search_replay_runtime_probe_or_point_is_called(self):
        import qmc_bmgs.benchmarks.countdown as countdown

        with ExitStack() as stack:
            for module, name in (
                (countdown, "generate_solvable_task_suite"),
                (countdown, "generate_candidate_tasks"),
                (countdown, "calibrate_task"),
                (countdown, "calibrate_pool"),
                (C.q, "run_countdown_track_a_search"),
                (C.q, "replay_countdown_track_a_search_bytes"),
                (C.q, "build_search_run_identity"),
                (C.q, "perturbation_runtime_metadata"),
                (C.core, "reproduce_anchor_qualification"),
                (C.core, "runtime_qualification"),
            ):
                stack.enter_context(
                    patch.object(module, name, side_effect=AssertionError(name))
                )
            C.build_contract()
            C.public_manifest()
            C.build_schedule_candidate(C.synthetic_identities())
            C.build_public_schedule()
            self.assertEqual(C.self_test()["search_executions"], 0)

    def test_contract_results_do_not_alias_each_other(self):
        before = C.canonical(C.build_contract())
        self.contract["exclusion_identities"]["cohorts"].clear()
        self.contract["budgets"][0]["spec"].clear()
        self.contract["qualification_plan"].clear()
        self.assertEqual(C.canonical(C.build_contract()), before)


class ReplicationScheduleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.identities = C.synthetic_identities()
        cls.candidate = C.build_schedule_candidate(cls.identities)

    def test_all_1024_full_keys_are_deterministic_and_bound(self):
        value = self.candidate
        cells = value["cells"]
        self.assertEqual(len(cells), 1024)
        self.assertEqual(len({cell["cell_id"] for cell in cells}), 1024)
        coordinates = list(
            product(range(64), (256, 512), (0, 16), (8192, 8193, 8194, 8195))
        )
        for index, (cell, (task, budget, scale, seed)) in enumerate(
            zip(cells, coordinates)
        ):
            key = cell["cell_key"]
            self.assertEqual(cell["cell_index"], index)
            self.assertEqual(cell["cell_id"], C.digest(key))
            self.assertEqual(
                (key["task_slot"], key["budget"], key["scale"], key["seed"]),
                (task, budget, scale, seed),
            )
            self.assertEqual(key["schema_version"], C.DOMAIN + "/candidate-cell-key")
            self.assertEqual(key["contract_digest"], value["contract_digest"])
            self.assertEqual(
                key["candidate_identity_digest"], value["candidate_identity_digest"]
            )
            self.assertEqual(
                key["task_fingerprint"], self.identities[task]["task_fingerprint"]
            )
        self.assertEqual(
            C.canonical(C.validate_schedule_candidate(C.canonical(value))),
            C.canonical(value),
        )

    def test_all_512_prefix_pairs_and_256_four_arm_blocks_close(self):
        value = self.candidate
        cells = {
            tuple(
                row["cell_key"][key] for key in ("task_slot", "budget", "scale", "seed")
            ): row["cell_id"]
            for row in value["cells"]
        }
        expected_pairs = [
            dict(
                task_slot=t,
                scale=s,
                seed=r,
                low_cell_id=cells[t, 256, s, r],
                high_cell_id=cells[t, 512, s, r],
            )
            for t, s, r in product(range(64), (0, 16), (8192, 8193, 8194, 8195))
        ]
        expected_blocks = [
            dict(
                task_slot=t, seed=r, arm_cell_ids=[cells[t, b, s, r] for b, s in C.ARMS]
            )
            for t, r in product(range(64), (8192, 8193, 8194, 8195))
        ]
        self.assertEqual(value["budget_prefix_pairs"], expected_pairs)
        self.assertEqual(value["four_cell_blocks"], expected_blocks)

    def test_both_identity_kinds_reject_all_eight_exclusion_groups(self):
        contract = C.build_contract()
        for group in contract["exclusion_identities"]["cohorts"]:
            for field in ("task_fingerprint", "source_multiset_fingerprint"):
                ids = copy.deepcopy(self.identities)
                ids[0][field] = group[field + "s"][0]
                with (
                    self.subTest(group=group["label"], field=field),
                    self.assertRaisesRegex(ValueError, "excluded"),
                ):
                    C.build_schedule_candidate(ids)

    def test_duplicate_source_or_task_rejected_with_distinct_other_identity(self):
        for field in ("task_fingerprint", "source_multiset_fingerprint"):
            ids = copy.deepcopy(self.identities)
            ids[1][field] = ids[0][field]
            with self.assertRaisesRegex(ValueError, "duplicate"):
                C.build_schedule_candidate(ids)

    def test_wrong_count_order_fields_type_or_digest_rejected(self):
        malformed = [
            None,
            {},
            self.identities[:12],
            self.identities[:-1],
            self.identities + [self.identities[0]],
        ]
        for key, value in (
            ("task_slot", True),
            ("task_slot", 0.0),
            ("task_slot", 1),
            ("task_fingerprint", "A" * 64),
            ("source_multiset_fingerprint", "x"),
            ("task_fingerprint", 42),
        ):
            ids = copy.deepcopy(self.identities)
            ids[0][key] = value
            malformed.append(ids)
        extra = copy.deepcopy(self.identities)
        extra[0]["success"] = True
        malformed.extend([extra, list(reversed(self.identities))])
        for ids in malformed:
            with self.subTest(kind=type(ids).__name__), self.assertRaises(ValueError):
                C.build_schedule_candidate(ids)

    def test_change_one_identity_rekeys_every_cell(self):
        ids = copy.deepcopy(self.identities)
        ids[0]["task_fingerprint"] = C.digest(["different", 0])
        changed = C.build_schedule_candidate(ids)
        self.assertNotEqual(
            changed["candidate_identity_digest"],
            self.candidate["candidate_identity_digest"],
        )
        self.assertTrue(
            all(
                a["cell_id"] != b["cell_id"]
                for a, b in zip(changed["cells"], self.candidate["cells"])
            )
        )

    def test_rehashed_identity_budget_method_and_pair_tampering_rejected(self):
        mutations = []
        for key, changed in (
            ("schema_version", C.old.DOMAIN + "/schedule-candidate"),
            ("experiment_id", C.old.EXPERIMENT_ID),
            ("cell_count", 192),
            ("cohort_sealed", True),
            ("replication_execution_authorized", True),
            ("production_cell_keys_materialized", True),
            ("unplanned", "field"),
        ):
            value = copy.deepcopy(self.candidate)
            value[key] = changed
            mutations.append(value)
        for collection in ("cells", "budget_prefix_pairs", "four_cell_blocks"):
            value = copy.deepcopy(self.candidate)
            value[collection].reverse()
            mutations.append(value)
            value = copy.deepcopy(self.candidate)
            value[collection].pop()
            mutations.append(value)
        value = copy.deepcopy(self.candidate)
        value["cells"][0]["cell_key"]["budget"] = 512
        value["cells"][0]["cell_id"] = C.digest(value["cells"][0]["cell_key"])
        value["schedule_digest"] = C.digest(value["cells"])
        mutations.append(value)
        value = copy.deepcopy(self.candidate)
        value["cells"][0]["cell_index"] = False
        mutations.append(value)
        for value in mutations:
            with self.subTest(keys=list(value)[:2]), self.assertRaises(ValueError):
                C.validate_schedule_candidate(C.canonical(redigest(value)))

    def test_strict_json_rejects_duplicate_nonfinite_pretty_and_nonobject(self):
        valid = C.canonical(self.candidate)
        wrong = [
            b"[]\n",
            valid.rstrip(b"\n"),
            json.dumps(self.candidate, indent=2).encode(),
            valid.replace(b"{", b'{"extra":NaN,', 1),
            valid.replace(b"{", b'{"extra":1,"extra":2,', 1),
        ]
        for raw in wrong:
            with self.assertRaises(ValueError):
                C.validate_schedule_candidate(raw)

    def test_old_v6_schedule_validator_rejects_v7_without_running_connector(self):
        with self.assertRaises(ValueError):
            C.old.validate_schedule_candidate(C.canonical(self.candidate))
        old_candidate = C.old.build_schedule_candidate(C.old.synthetic_identities())
        with self.assertRaises(ValueError):
            C.validate_schedule_candidate(C.canonical(old_candidate))

    def test_inputs_and_returned_schedules_do_not_alias(self):
        ids = copy.deepcopy(self.identities)
        value = C.build_schedule_candidate(ids)
        before = C.canonical(value)
        ids[0]["task_fingerprint"] = "f" * 64
        self.assertEqual(C.canonical(value), before)
        value["candidate_identities"].clear()
        value["cells"][0]["cell_key"].clear()
        self.assertEqual(
            C.canonical(C.build_schedule_candidate(self.identities)),
            C.canonical(self.candidate),
        )

    def test_all_input_snapshots_revalidate_after_candidate_assembly(self):
        original = C._layout
        original_check = C.core.FileSnapshot.revalidate
        assembled, after = [], []

        def layout(*args, **kwargs):
            result = original(*args, **kwargs)
            assembled.append(True)
            return result

        def checked(snapshot):
            if assembled:
                after.append(Path(snapshot.path).relative_to(ROOT).as_posix())
            return original_check(snapshot)

        with (
            patch.object(C, "_layout", side_effect=layout),
            patch.object(C.core.FileSnapshot, "revalidate", checked),
        ):
            C.build_schedule_candidate(self.identities)
        self.assertEqual(set(after), set(C.pinned_files()))

    def test_post_assembly_input_drift_fails_before_return(self):
        original = C._layout
        original_check = C.core.FileSnapshot.revalidate
        assembled = []

        def layout(*args, **kwargs):
            result = original(*args, **kwargs)
            assembled.append(True)
            return result

        def changed(snapshot):
            if assembled:
                raise ValueError("injected input change after layout")
            return original_check(snapshot)

        with (
            patch.object(C, "_layout", side_effect=layout),
            patch.object(C.core.FileSnapshot, "revalidate", changed),
            self.assertRaisesRegex(ValueError, "after layout"),
        ):
            C.build_schedule_candidate(self.identities)


class ReplicationPublicContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = C.public_manifest()
        cls.schedule = C.build_public_schedule()

    def test_exact_64_target_recipe_and_one_shared_source(self):
        value = self.manifest
        self.assertEqual(
            [t["target"] for t in value["full_shape_tasks"]], list(range(1, 65))
        )
        self.assertTrue(
            all(t["inputs"] == [1, 2, 3, 4, 5, 6] for t in value["full_shape_tasks"])
        )
        self.assertEqual(value["qualification_task"]["target"], 720)
        self.assertEqual(len(value["exclude_task_fingerprints"]), 65)
        self.assertEqual(len(value["exclude_source_multiset_fingerprints"]), 1)
        self.assertFalse(value["fixture_solvability_assessed"])
        self.assertFalse(value["fixture_is_replication_evidence"])
        self.assertFalse(value["fixture_tasks_are_independent_sources"])
        self.assertEqual(C.canonical(value), (ROOT / C.PUBLIC).read_bytes())

    def test_PUBLIC_fixture_schedule_is_complete_but_not_qualified(self):
        value = self.schedule
        self.assertEqual(value["schema_version"], C.PUBLIC_DOMAIN + "/manifest")
        self.assertEqual(value["execution_mode"], C.PUBLIC_MODE)
        self.assertEqual(
            (value["task_count"], value["source_multiset_count"], value["cell_count"]),
            (64, 1, 1024),
        )
        self.assertEqual(len(value["budget_prefix_pairs"]), 512)
        self.assertEqual(len(value["four_cell_blocks"]), 256)
        self.assertFalse(value["actual_qualification_performed"])
        self.assertFalse(value["replication_execution_authorized"])
        self.assertEqual(
            C.canonical(C.validate_public_schedule(C.canonical(value))),
            C.canonical(value),
        )

    def test_PUBLIC_tasks_cannot_become_replication_identities(self):
        with self.assertRaisesRegex(ValueError, "excluded"):
            C.build_schedule_candidate(self.schedule["candidate_identities"])
        with self.assertRaises(ValueError):
            C.validate_schedule_candidate(C.canonical(self.schedule))
        synthetic = C.build_schedule_candidate(C.synthetic_identities())
        with self.assertRaises(ValueError):
            C.validate_public_schedule(C.canonical(synthetic))

    def test_PUBLIC_rehashed_missing_duplicate_or_foreign_rows_fail(self):
        for kind in ("missing", "duplicate", "foreign", "authorize"):
            value = copy.deepcopy(self.schedule)
            if kind == "missing":
                value["cells"].pop()
            elif kind == "duplicate":
                value["cells"][1] = value["cells"][0]
            elif kind == "foreign":
                value["tasks"][0]["inputs"] = [2] * 6
            else:
                value["replication_execution_authorized"] = True
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                C.validate_public_schedule(C.canonical(redigest(value)))

    def test_candidates_cannot_self_promote_by_valid_shape(self):
        for value in (
            C.build_contract(),
            self.manifest,
            self.schedule,
            C.build_schedule_candidate(C.synthetic_identities()),
            C.self_test(),
        ):
            for key, expected in C.not_authority().items():
                self.assertEqual(value[key], expected)
            self.assertNotIn("scientific_decision", value)

    def test_returned_PUBLIC_definitions_do_not_alias(self):
        value = C.public_manifest()
        value["full_shape_tasks"][0]["inputs"].clear()
        value["qualification_task"]["target"] = 1
        self.assertEqual(C.canonical(C.public_manifest()), C.canonical(self.manifest))


class ReplicationContractCLITests(unittest.TestCase):
    def invoke(self, *args, cwd="/tmp"):
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
        return subprocess.run(
            [sys.executable, "-P", "-B", str(SCRIPT), *args],
            cwd=cwd,
            env=env,
            text=True,
            capture_output=True,
        )

    def test_outside_checkout_manifest_and_self_test(self):
        for mode in (
            "--manifest",
            "--self-test",
            "--public-identities",
            "--public-schedule",
        ):
            result = self.invoke(mode)
            self.assertEqual(result.returncode, 0, result.stderr)
            value = C.core.parse_canonical(result.stdout.encode())
            C.core.require_digest(value)
            self.assertFalse(value["replication_execution_authorized"])
            self.assertEqual(value["replication_tasks_generated"], 0)
            self.assertEqual(value["search_executions"], 0)

    def test_unknown_generation_execution_or_authorization_modes_rejected(self):
        for mode in (
            "--run",
            "--run-development",
            "--generate",
            "--seal",
            "--authorization",
        ):
            result = self.invoke(mode)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("REPLICATION_CONTRACT_SYNTHETIC_PASS", result.stdout)

    def test_existing_file_aliases_are_rejected_at_input_boundary(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in C.pinned_files():
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.symlink_to(ROOT / relative)
            with self.assertRaises(ValueError):
                C.build_contract(root)


if __name__ == "__main__":
    unittest.main()
