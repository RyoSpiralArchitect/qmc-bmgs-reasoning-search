from __future__ import annotations

from contextlib import ExitStack, contextmanager
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from qmc_bmgs.benchmarks.countdown import CountdownTask


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "portfolio_development_tested",
    ROOT / "scripts/run_feedback_allocation_development.py",
)
D = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(D)


class AllocationDevelopmentTests(unittest.TestCase):
    @contextmanager
    def tiny_study(self):
        """Only an all-ones regression fixture; never generate the planned cohort."""
        with tempfile.TemporaryDirectory() as td, ExitStack() as stack:
            for name, value in dict(
                ROOT=Path(td), OUTPUT="tiny", COUNT=1, SEEDS=(41,), BUDGETS=(512,)
            ).items():
                stack.enter_context(patch.object(D, name, value))
            plan = dict(
                deterministic_digest="a" * 64,
                analysis=dict(
                    comparisons=[["weighted16", "single16"], ["equal16", "single16"]]
                ),
            )
            cohort = D.digested(
                dict(
                    tasks=[CountdownTask((1, 1, 1, 1, 1, 1), 6).to_dict()],
                    generation={},
                    plan_digest="a" * 64,
                )
            )
            stack.enter_context(patch.object(D, "checked_plan", return_value=plan))
            stack.enter_context(patch.object(D, "clean_head", return_value="b" * 40))
            stack.enter_context(patch.object(D, "operation_guard"))
            stack.enter_context(patch.object(D, "historical_guard"))
            stack.enter_context(
                patch.object(D, "require_approval", return_value={"fixture": True})
            )
            stack.enter_context(
                patch.object(D, "cohort_from_recipe", return_value=cohort)
            )
            yield Path(td) / "tiny"

    def replace_digest(self, path, value):
        core = {k: v for k, v in value.items() if k != "deterministic_digest"}
        path.write_bytes(D.canonical_trace_bytes(D.digested(core)))

    def test_registry_excludes_original_study_public_and_locked_identities(self):
        e = D.exclusions()
        self.assertGreaterEqual(len(e["source_multiset_fingerprints"]), 243)
        self.assertGreaterEqual(len(e["task_fingerprints"]), 347)
        self.assertIn(
            CountdownTask((1, 2, 3, 4, 5, 6), 1).source_multiset_fingerprint,
            e["source_multiset_fingerprints"],
        )
        self.assertEqual(e["registry"]["sha256"], D.REGISTRY_SHA)
        prior = D.load(e["prior_development_cohort"]["path"])
        for row in prior["tasks"]:
            self.assertIn(
                row["source_multiset_fingerprint"], e["source_multiset_fingerprints"]
            )

    def test_plan_is_outcome_blind_and_exactly_sized(self):
        with (
            patch.object(D, "source_snapshot", return_value=[]),
            patch.object(D, "generate_solvable_task_suite") as generate,
            patch.object(D, "run_allocation_search") as run,
        ):
            p = D.build_plan()
        generate.assert_not_called()
        run.assert_not_called()
        self.assertEqual(p["planned_cells"], 1536)
        self.assertEqual(p["planned_branch_runs"], 2560)
        self.assertEqual(p["planned_budget_prefix_pairs"], 2048)
        self.assertEqual(p["maximum_total_legal_action_scores"], 786432)
        self.assertEqual(p["seeds"], list(range(65536, 65544)))
        self.assertFalse(p["execution_authorized"])
        self.assertFalse(p["original_study_C5_authorized"])
        self.assertFalse(p["locked_128_authorized"])
        self.assertEqual(
            p["analysis"]["primary"],
            "weighted16_minus_single16_exact_gains_losses_at_512",
        )
        self.assertEqual(
            len({v for r in p["derived_streams"] for v in r["branch_seeds"]}), 16
        )

    def test_wrong_digest_rejected_without_generation_or_output(self):
        with (
            patch.object(
                D, "build_plan", return_value={"deterministic_digest": "a" * 64}
            ),
            patch.object(D, "generate_solvable_task_suite") as generate,
        ):
            with self.assertRaisesRegex(ValueError, "exact reviewed plan"):
                D.run("b" * 64)
        generate.assert_not_called()

    def test_cohort_passes_exclusions_and_never_reads_calibrations(self):
        class Suite:
            tasks = (CountdownTask((1, 1, 1, 1, 1, 1), 6),)
            generation_manifest = {"attempt_count": 1}

            @property
            def calibrations(self):
                raise AssertionError("must not consume witnesses or hardness")

        p = dict(
            exclusions=dict(
                task_fingerprints=["a"],
                source_multiset_fingerprints=["b"],
                deterministic_digest="c",
            ),
            generation=dict(count=1, seed=9, max_attempts=10),
            deterministic_digest="d",
        )
        with patch.object(
            D, "generate_solvable_task_suite", return_value=Suite()
        ) as gen:
            cohort = D.cohort_from_recipe(p)
        self.assertEqual(
            gen.call_args.kwargs["excluded_source_multiset_fingerprints"], ["b"]
        )
        self.assertEqual(
            set(cohort), {"tasks", "generation", "plan_digest", "deterministic_digest"}
        )

    def test_exclusive_publication_rejects_existing_file_and_symlink(self):
        with tempfile.TemporaryDirectory() as td, patch.object(D, "ROOT", Path(td)):
            D.save_new("one.json", {"one": 1})
            with self.assertRaises(FileExistsError):
                D.save_new("one.json", {"one": 2})
            (Path(td) / "link.json").symlink_to(Path(td) / "one.json")
            with self.assertRaises(FileExistsError):
                D.save_new("link.json", {})
            self.assertEqual(D.load("one.json"), {"one": 1})

    def test_paired_reducer_keeps_losses_and_missing_error(self):
        rows = [
            dict(
                a=dict(success_any=True, minimum_terminal_error=0),
                b=dict(success_any=False, minimum_terminal_error=2),
            ),
            dict(
                a=dict(success_any=False, minimum_terminal_error=None),
                b=dict(success_any=True, minimum_terminal_error=0),
            ),
            dict(
                a=dict(success_any=False, minimum_terminal_error=4),
                b=dict(success_any=False, minimum_terminal_error=3),
            ),
        ]
        c = D._contrast(rows, "a", "b")
        self.assertEqual(
            (c["gains"], c["losses"], c["net"], c["denominator"]), (1, 1, 0, 3)
        )
        self.assertEqual(c["minimum_error"], dict(win=1, loss=1, tie=0, missing=1))

    def test_tiny_isolated_lifecycle_replay_and_retry_refusal(self):
        with self.tiny_study():
            commit = D.run("a" * 64)
            self.assertEqual(commit["cell_count"], 3)
            with self.assertRaises(FileExistsError):
                D.run("a" * 64)
            result = D.analyze("a" * 64)
            self.assertEqual(result["prefix_pairs"], 4)
            self.assertEqual(result["reduction"]["cell_count"], 3)
            self.assertIsNone(result["reduction"]["winner"])
            self.assertEqual(result["structural_blocks"], 1)
            for row in result["reduction"]["by_budget"]:
                diagnostics = row["diagnostics"]
                self.assertIsNone(diagnostics["single16"]["same_action_sequence"])
                self.assertEqual(diagnostics["single16"]["two_branch_denominator"], 0)
                self.assertEqual(diagnostics["weighted16"]["two_branch_denominator"], 1)
                self.assertIn("no_terminal_branches", diagnostics["weighted16"])
            with self.assertRaisesRegex(ValueError, "analysis already attempted"):
                D.analyze("a" * 64)

    def test_prefixes_reject_allocation_or_stream_drift(self):
        with self.tiny_study():
            commit = D.run("a" * 64)
            records = {
                tuple(r["key"]): D.load(r["file"]["path"]) for r in commit["cells"]
            }
            self.assertEqual(D.check_prefixes(records), 4)
            self.assertEqual(D.check_structure(records), 1)
            for arm, index in (("weighted16", 0), ("weighted16", 1), ("equal16", 1)):
                changed = copy.deepcopy(records)
                changed[(0, 41, 512, arm)]["channels"][index]["exploration_seed"] += 1
                with self.assertRaisesRegex(ValueError, "seed changed"):
                    D.check_prefixes(changed)

    def test_analysis_rejects_rehashed_commit_aliases_paths_and_extra_fields(self):
        def aliases(commit):
            commit["cells"][0]["key"][0] = False

        def count_type(commit):
            commit["cell_count"] = 3.0

        def foreign_path(commit):
            commit["started"]["path"] = "tiny/cohort.json"

        def unknown(commit):
            commit["extra"] = True

        for change in (aliases, count_type, foreign_path, unknown):
            with self.subTest(change=change.__name__), self.tiny_study() as output:
                commit = D.run("a" * 64)
                change(commit)
                self.replace_digest(output / "COMMIT.json", commit)
                with self.assertRaises(ValueError):
                    D.analyze("a" * 64)
                self.assertFalse((output / "summary.json").exists())

    def test_analysis_rejects_started_binding_even_with_refreshed_hashes(self):
        with self.tiny_study() as output:
            commit = D.run("a" * 64)
            started = D.load("tiny/STARTED.json")
            started["source_head"] = "c" * 40
            self.replace_digest(output / "STARTED.json", started)
            commit["started"] = D.reference("tiny/STARTED.json")
            self.replace_digest(output / "COMMIT.json", commit)
            with self.assertRaisesRegex(ValueError, "STARTED does not bind"):
                D.analyze("a" * 64)
            self.assertFalse((output / "summary.json").exists())

    def test_analysis_rechecks_evidence_after_all_replays(self):
        for mode in ("changed_cell", "added_file"):
            with self.subTest(mode=mode), self.tiny_study() as output:
                D.run("a" * 64)
                reduce = D.reduce_results

                def change_after_replay(plan, records):
                    result = reduce(plan, records)
                    path = output / (
                        "cell-0000.json" if mode == "changed_cell" else "foreign.json"
                    )
                    with path.open("ab") as stream:
                        stream.write(b"\n")
                    return result

                with patch.object(D, "reduce_results", change_after_replay):
                    with self.assertRaisesRegex(ValueError, "changed"):
                        D.analyze("a" * 64)
                self.assertTrue((output / "analysis.STARTED.json").is_file())
                self.assertFalse((output / "summary.json").exists())
                with self.assertRaisesRegex(ValueError, "already attempted"):
                    D.analyze("a" * 64)

    def test_partial_attempt_is_never_adopted(self):
        with tempfile.TemporaryDirectory() as td, ExitStack() as stack:
            for name, value in dict(ROOT=Path(td), OUTPUT="partial").items():
                stack.enter_context(patch.object(D, name, value))
            stack.enter_context(patch.object(D, "checked_plan", return_value={}))
            stack.enter_context(patch.object(D, "clean_head", return_value="b" * 40))
            stack.enter_context(patch.object(D, "operation_guard"))
            stack.enter_context(patch.object(D, "historical_guard"))
            stack.enter_context(
                patch.object(D, "require_approval", return_value={"fixture": True})
            )
            stack.enter_context(
                patch.object(
                    D, "cohort_from_recipe", side_effect=RuntimeError("solver failed")
                )
            )
            with self.assertRaisesRegex(RuntimeError, "solver failed"):
                D.run("a" * 64)
            self.assertTrue((Path(td) / "partial/STARTED.json").is_file())
            self.assertFalse((Path(td) / "partial/COMMIT.json").exists())
            with self.assertRaises(FileExistsError):
                D.run("a" * 64)
            with self.assertRaisesRegex(ValueError, "regular file"):
                D.analyze("a" * 64)

    def test_cluster_denominator_does_not_count_repeated_seeds_as_sources(self):
        blocks = [
            dict(task_slot=s, a=dict(success_any=s == 0), b=dict(success_any=s == 1))
            for s in (0, 1)
            for _ in range(8)
        ]
        with patch.object(D, "COUNT", 2), patch.object(D, "SEEDS", tuple(range(8))):
            result = D.cluster_summary(blocks, "a", "b")
        self.assertEqual(result["source_clusters"], 2)
        self.assertEqual(result["source_mean_differences"], [1, -1])
        self.assertEqual(result["mean"], 0)
        self.assertEqual(result["descriptive_standard_error"], 1)
        self.assertIsNone(result["confidence_interval"])

    def test_recent_accepted_and_rejected_sources_are_all_excluded(self):
        e = D.exclusions()
        for label in ("prior_development_cohort", "prior_diversity_cohort"):
            prior = D.load(e[label]["path"])
            for row in prior["tasks"] + prior["generation"]["rejection_log"]:
                self.assertIn(row["task_fingerprint"], e["task_fingerprints"])
                self.assertIn(
                    row["source_multiset_fingerprint"],
                    e["source_multiset_fingerprints"],
                )

    def test_missing_exact_approval_prevents_generation_and_output(self):
        with (
            tempfile.TemporaryDirectory() as td,
            patch.object(D, "ROOT", Path(td)),
            patch.object(D, "checked_plan", return_value={}),
            patch.object(D, "clean_head", return_value="b" * 40),
            patch.object(D, "operation_guard"),
            patch.object(D, "historical_guard"),
            patch.object(D, "cohort_from_recipe") as generate,
        ):
            with self.assertRaisesRegex(ValueError, "regular file required"):
                D.run("a" * 64)
            generate.assert_not_called()
            self.assertFalse((Path(td) / D.OUTPUT).exists())

    def test_approval_binds_qualified_candidate_and_human_scope(self):
        plan = dict(deterministic_digest="a" * 64)
        ref = dict(path=D.QUALIFICATION_FILE, sha256="c" * 64, byte_count=99)
        approval = dict(
            schema_version="qmc-bmgs-feedback-allocation-approval/v1",
            plan_digest="a" * 64,
            candidate_commit="b" * 40,
            decision="approved",
            scope="one_run_and_one_separate_analysis",
            human_approval=dict(
                source="synthetic_fixture", quote="synthetic fixture only"
            ),
            qualification=ref,
        )
        qualification = dict(
            status="ALLOCATION_CANDIDATE_VALIDATION_PASS",
            tested_commit="b" * 40,
            plan_digest="a" * 64,
            exit_code=0,
            skipped_tests=0,
            repository_validation_pass=True,
        )

        def git(*args):
            return {
                "merge-base": ("b" * 40).encode(),
                "ls-tree": b"file.py",
                "diff": b"",
            }[args[0]]

        with (
            patch.object(D, "load_digest", return_value=approval),
            patch.object(D, "load", return_value=qualification),
            patch.object(D, "reference", return_value=ref),
            patch.object(D, "git", git),
        ):
            self.assertIn("approval", D.require_approval(plan, "d" * 40))
            for field, value in (
                ("decision", "pending"),
                ("plan_digest", "e" * 64),
                ("scope", "direction_only"),
                ("human_approval", {}),
            ):
                changed = {**approval, field: value}
                with (
                    patch.object(D, "load_digest", return_value=changed),
                    self.assertRaises(ValueError),
                ):
                    D.require_approval(plan, "d" * 40)
            with (
                patch.object(
                    D,
                    "load_digest",
                    return_value={
                        **approval,
                        "qualification": {**ref, "byte_count": 99.0},
                    },
                ),
                self.assertRaisesRegex(ValueError, "qualification reference mismatch"),
            ):
                D.require_approval(plan, "d" * 40)
            for field, value in (
                ("exit_code", False),
                ("skipped_tests", 1),
                ("repository_validation_pass", False),
                ("tested_commit", "f" * 40),
            ):
                with (
                    patch.object(
                        D, "load", return_value={**qualification, field: value}
                    ),
                    self.assertRaises(ValueError),
                ):
                    D.require_approval(plan, "d" * 40)
            with (
                patch.object(
                    D,
                    "git",
                    side_effect=lambda *a: b"changed" if a[0] == "diff" else git(*a),
                ),
                self.assertRaisesRegex(ValueError, "candidate bytes changed"),
            ):
                D.require_approval(plan, "d" * 40)

    def test_changed_approval_retains_attempt_without_committing(self):
        with (
            self.tiny_study() as output,
            patch.object(
                D, "require_approval", side_effect=[{"fixture": 1}, {"fixture": 2}]
            ),
        ):
            with self.assertRaisesRegex(ValueError, "authorization changed"):
                D.run("a" * 64)
            self.assertTrue((output / "STARTED.json").exists())
            self.assertFalse((output / "COMMIT.json").exists())

    def test_historical_guard_rejects_changed_parent_file(self):
        with patch.object(
            D, "reference", return_value={"path": "protected", "sha256": "new"}
        ):
            with self.assertRaisesRegex(ValueError, "protected parent bytes changed"):
                D.historical_guard(
                    {"protected_parent_files": [{"path": "protected", "sha256": "old"}]}
                )


if __name__ == "__main__":
    unittest.main()
