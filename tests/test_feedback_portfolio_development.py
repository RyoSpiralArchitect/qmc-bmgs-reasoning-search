from __future__ import annotations

from contextlib import ExitStack, contextmanager
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from qmc_bmgs.benchmarks.countdown import CountdownTask


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "portfolio_development_tested",
    ROOT / "scripts/run_feedback_portfolio_development.py",
)
D = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(D)


class PortfolioDevelopmentTests(unittest.TestCase):
    @contextmanager
    def tiny_study(self):
        """Only an all-ones regression fixture; never generate the planned cohort."""
        with tempfile.TemporaryDirectory() as td, ExitStack() as stack:
            for name, value in dict(
                ROOT=Path(td), OUTPUT="tiny", COUNT=1, SEEDS=(41,), BUDGETS=(64, 128)
            ).items():
                stack.enter_context(patch.object(D, name, value))
            plan = dict(
                deterministic_digest="a" * 64,
                analysis=dict(
                    comparisons=[["protected1", "exact"], ["calibrated1", "dense16"]]
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
        self.assertEqual(len(e["task_fingerprints"]), 307)
        self.assertIn(
            CountdownTask((1, 2, 3, 4, 5, 6), 1).source_multiset_fingerprint,
            e["source_multiset_fingerprints"],
        )
        self.assertEqual(e["registry"]["sha256"], D.REGISTRY_SHA)

    def test_plan_is_outcome_blind_and_exactly_sized(self):
        with (
            patch.object(D, "source_snapshot", return_value=[]),
            patch.object(D, "generate_solvable_task_suite") as generate,
            patch.object(D, "run_feedback_search") as run,
        ):
            p = D.build_plan()
        generate.assert_not_called()
        run.assert_not_called()
        self.assertEqual(p["planned_cells"], 512)
        self.assertEqual(p["planned_branch_runs"], 640)
        self.assertEqual(p["planned_budget_prefix_pairs"], 256)
        self.assertEqual(p["maximum_total_legal_action_scores"], 196608)
        self.assertEqual(p["seeds"], list(range(16384, 16392)))
        self.assertFalse(p["execution_authorized"])
        self.assertFalse(p["original_study_C5_authorized"])
        self.assertFalse(p["locked_128_authorized"])

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
            self.assertEqual(commit["cell_count"], 8)
            with self.assertRaises(FileExistsError):
                D.run("a" * 64)
            result = D.analyze("a" * 64)
            self.assertEqual(result["prefix_pairs"], 4)
            self.assertEqual(result["reduction"]["cell_count"], 8)
            self.assertIsNone(result["reduction"]["winner"])
            with self.assertRaisesRegex(ValueError, "analysis already attempted"):
                D.analyze("a" * 64)

    def test_analysis_rejects_rehashed_commit_aliases_paths_and_extra_fields(self):
        def aliases(commit):
            commit["cells"][0]["key"][0] = False

        def count_type(commit):
            commit["cell_count"] = 8.0

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


if __name__ == "__main__":
    unittest.main()
