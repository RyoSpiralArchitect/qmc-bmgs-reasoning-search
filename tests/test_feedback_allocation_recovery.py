from __future__ import annotations

from contextlib import ExitStack, contextmanager
import copy
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "allocation_recovery_tested",
    ROOT / "scripts/recover_feedback_allocation_analysis.py",
)
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)
D = M.D


class AllocationRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Excluded source, non-study roots and small caps; never planned inputs.
        task = D.CountdownTask((1, 1, 1, 1, 1, 1), 6)
        cls.task = task
        cls.eager = {
            (0, seed, 128, arm): D.run_allocation_search(
                task=task,
                spec=D.AllocationSearchSpec(arm),
                budget_profile=D.profile(128),
                exploration_seed=seed,
            ).record
            for seed in (41, 42)
            for arm in D.ARMS
        }

    @contextmanager
    def fixture(self):
        with tempfile.TemporaryDirectory() as td, ExitStack() as stack:
            root = Path(td)
            for module, items in (
                (
                    M,
                    dict(
                        ROOT=root,
                        OUTPUT="recovery",
                        E="execution",
                        R="review",
                        ANCHORS={},
                        SOURCE_PATHS=(),
                    ),
                ),
                (
                    D,
                    dict(
                        ROOT=root,
                        OUTPUT="fixture",
                        COUNT=1,
                        SEEDS=(41, 42),
                        BUDGETS=(128,),
                    ),
                ),
            ):
                for key, value in items.items():
                    stack.enter_context(patch.object(module, key, value))
            for directory in ("fixture", "review", "execution"):
                (root / directory).mkdir()
            plan = dict(
                deterministic_digest=M.PLAN_DIGEST,
                planned_branch_runs=10,
                planned_branch_prefix_pairs=6,
                planned_structural_blocks=2,
                analysis=dict(
                    comparisons=[
                        ["weighted16", "single16"],
                        ["equal16", "single16"],
                        ["weighted16", "equal16"],
                    ]
                ),
            )
            cohort = D.digested(
                dict(
                    tasks=[self.task.to_dict()],
                    generation={},
                    plan_digest=M.PLAN_DIGEST,
                )
            )
            started = D.save_new(
                "fixture/STARTED.json",
                D.digested(
                    dict(
                        study_id=D.STUDY, plan_digest=M.PLAN_DIGEST, source_head=M.BASE
                    )
                ),
            )
            cohort_ref = D.save_new("fixture/cohort.json", cohort)
            cells = [
                dict(
                    index=i,
                    key=list(key),
                    file=D.save_new(f"fixture/cell-{i:04d}.json", self.eager[key]),
                )
                for i, key in enumerate(D.coordinates())
            ]
            commit = D.digested(
                dict(
                    study_id=D.STUDY,
                    plan_digest=M.PLAN_DIGEST,
                    source_head=M.BASE,
                    started=started,
                    cohort=cohort_ref,
                    cells=cells,
                    cell_count=6,
                    status="COMPLETE_NOT_YET_INDEPENDENTLY_ANALYZED",
                )
            )
            commit_ref = D.save_new("fixture/COMMIT.json", commit)
            D.save_new(
                "fixture/analysis.STARTED.json",
                D.digested(
                    dict(
                        source_head=M.BASE, plan_digest=M.PLAN_DIGEST, commit=commit_ref
                    )
                ),
            )
            D.save_new("review/analysis.interruption.json", dict(complete=False))
            manifest = D.digested(
                dict(
                    original_head=M.BASE,
                    output="recovery",
                    recovery_source=[],
                    frozen=[M.ref(p) for p in M.names("fixture")],
                    membership={"fixture": M.names("fixture")},
                    absent=["fixture/summary.json"],
                )
            )
            D.save_new("manifest.json", manifest)
            D.save_new(
                "approval.json",
                dict(
                    candidate_commit=M.BASE,
                    recovery_digest=manifest["deterministic_digest"],
                    scope="one_full_saved_data_recovery_analysis_no_experiment",
                    authorization_mode="delegated_candidate_selection",
                    human_message="そうね、候補決めるー＞全権実行->分析&ドキュメンテーション改善まで回してみよう🐈‍⬛🐈🐈🌀",
                ),
            )
            (root / "stdout").write_text("repository validation: PASS\n")
            (root / "stderr").write_text("Ran 3 tests in 1s\n\nOK\n")
            D.save_new(
                "qualification.json",
                dict(
                    source_head=M.BASE,
                    exit_code=0,
                    postflight_pass=True,
                    postconditions_errors=[],
                    before={},
                    after={},
                    **{
                        k: M.ref("stdout" if k != "stderr" else "stderr")
                        for k in (
                            "helper",
                            "inputs",
                            "intent",
                            "start",
                            "stdout",
                            "stderr",
                        )
                    },
                ),
            )
            stack.enter_context(patch.object(D, "checked_plan", return_value=plan))
            stack.enter_context(patch.object(D, "clean_head", return_value=M.BASE))
            stack.enter_context(patch.object(D, "operation_guard"))
            stack.enter_context(
                patch.object(D, "cohort_from_recipe", return_value=cohort)
            )
            yield root, plan, commit, manifest

    def recover(self, manifest):
        return M.recover(
            "manifest.json",
            manifest["deterministic_digest"],
            M.BASE,
            "approval.json",
            "qualification.json",
        )

    def test_complete_replay_and_reduction_equal_eager(self):
        with self.fixture() as (_, plan, commit, _):
            progress = []
            result = M.execute_analysis(
                plan, commit, lambda *x: progress.append(x), lambda: None
            )
            self.assertEqual(result["reduction"], D.reduce_results(plan, self.eager))
            self.assertEqual(result["prefix_pairs"], D.check_prefixes(self.eager))
            self.assertEqual(result["structural_blocks"], D.check_structure(self.eager))
            self.assertEqual(result["replayed_branches"], 10)
            self.assertEqual(result["peak_cached_detailed_cells"], 3)
            self.assertIn(("replay", 6), progress)
            self.assertIsNone(result["reduction"]["winner"])

    def test_cache_evicts_entire_previous_block(self):
        with self.fixture() as (_, _, c, _):
            records = M.BoundedRecords(c["cells"])
            for key in D.coordinates():
                self.assertEqual(records[key], self.eager[key])
                self.assertTrue(all(k[:3] == key[:3] for k in records.cache))
                self.assertLessEqual(len(records.cache), 3)
            self.assertEqual(len(records), 6)
            self.assertEqual(len(records.cache), 3)
            with self.assertRaises(KeyError):
                records[(99, 41, 128, "single16")]

    def test_large_synthetic_mapping_cache_bound(self):
        cells = [
            dict(key=[i, 1, 128, arm], file={}) for i in range(1000) for arm in D.ARMS
        ]
        records = M.BoundedRecords(cells)
        with patch.object(records, "raw", return_value=b'{"summary":{}}'):
            for key in records:
                records[key]
            self.assertEqual(records.peak_cached_cells, 3)
            self.assertEqual(len(records.cache), 3)

    def test_duplicate_mapping_keys_refused(self):
        with self.fixture() as (_, _, c, _):
            with self.assertRaisesRegex(ValueError, "duplicate"):
                M.BoundedRecords(c["cells"] + c["cells"][:1])

    def test_cached_file_tamper_is_not_hidden(self):
        with self.fixture() as (root, _, c, _):
            r = M.BoundedRecords(c["cells"])
            key = D.coordinates()[0]
            r[key]
            with (root / c["cells"][0]["file"]["path"]).open("ab") as stream:
                stream.write(b"\n")
            with self.assertRaisesRegex(ValueError, "bytes changed"):
                r[key]

    def test_missing_file_refused(self):
        with self.fixture() as (root, _, c, _):
            (root / c["cells"][0]["file"]["path"]).unlink()
            with self.assertRaises(FileNotFoundError):
                M.BoundedRecords(c["cells"])[D.coordinates()[0]]

    def test_symlink_file_and_parent_refused(self):
        with self.fixture() as (root, _, c, _):
            target = root / c["cells"][0]["file"]["path"]
            for name, destination, read_name in (
                ("alias", target, "alias"),
                ("parent", root / "fixture", "parent/cell-0000.json"),
            ):
                (root / name).symlink_to(destination)
                with self.assertRaisesRegex(ValueError, "symlink"):
                    M.read(read_name)

    def test_noncanonical_and_escaping_paths_refused(self):
        for name in ("../outside", "/tmp/outside", "a/../b", "./a", "a//b", "."):
            with self.subTest(name=name), self.assertRaises(ValueError):
                M.safe_path(name)

    def test_old_absolute_slots_normalize_only_inside_repository(self):
        with self.fixture() as (root, _, _, _):
            self.assertEqual(
                M.historical_slot(str(root / "missing.json")), "missing.json"
            )
            with self.assertRaises(ValueError):
                M.historical_slot("/foreign/missing.json")

    def test_coordinate_bool_alias_and_duplicates_refused(self):
        for change in (
            lambda c: c["cells"][0]["key"].__setitem__(0, False),
            lambda c: c["cells"].__setitem__(1, c["cells"][0]),
            lambda c: c.__setitem__("cell_count", 6.0),
        ):
            with self.fixture() as (root, _, c, _):
                changed = copy.deepcopy(c)
                change(changed)
                changed.pop("deterministic_digest")
                (root / "fixture/COMMIT.json").write_bytes(
                    D.canonical_trace_bytes(D.digested(changed))
                )
                with self.assertRaises(ValueError):
                    M.checked_commit()

    def test_wrong_operation_binding_refused(self):
        for field in ("plan_digest", "source_head", "study_id", "status"):
            with self.fixture() as (root, _, c, _):
                changed = {k: v for k, v in c.items() if k != "deterministic_digest"}
                changed[field] = "foreign"
                (root / "fixture/COMMIT.json").write_bytes(
                    D.canonical_trace_bytes(D.digested(changed))
                )
                with self.assertRaisesRegex(ValueError, "binding"):
                    M.checked_commit()

    def test_old_fence_required_and_original_analyzer_still_refuses(self):
        with self.fixture() as (root, _, _, _):
            with self.assertRaisesRegex(ValueError, "analysis already attempted"):
                D.analyze(M.PLAN_DIGEST)
            (root / "fixture/analysis.STARTED.json").unlink()
            with self.assertRaises(FileNotFoundError):
                M.checked_commit()

    def test_membership_and_absence_fail_closed(self):
        with self.fixture() as (root, _, _, manifest):
            M.check_manifest(manifest)
            (root / "fixture/foreign").touch()
            with self.assertRaisesRegex(ValueError, "membership"):
                M.check_manifest(manifest)

    def test_wrong_digest_does_not_create_recovery_slot(self):
        with self.fixture() as (root, _, _, _):
            with self.assertRaisesRegex(ValueError, "exact recovery digest"):
                M.recover(
                    "manifest.json",
                    "wrong",
                    M.BASE,
                    "approval.json",
                    "qualification.json",
                )
            self.assertFalse((root / "recovery").exists())

    def test_unqualified_candidate_refused(self):
        with self.fixture() as (root, _, _, manifest):
            q = M.load("qualification.json")
            q["exit_code"] = 1
            (root / "qualification.json").write_bytes(D.canonical_trace_bytes(q))
            with self.assertRaisesRegex(ValueError, "not qualified"):
                self.recover(manifest)
            self.assertFalse((root / "recovery").exists())

    def test_wrong_approval_refused(self):
        with self.fixture() as (root, _, _, manifest):
            a = M.load("approval.json")
            a["candidate_commit"] = "foreign"
            (root / "approval.json").write_bytes(D.canonical_trace_bytes(a))
            with self.assertRaisesRegex(ValueError, "authorization"):
                self.recover(manifest)
            self.assertFalse((root / "recovery").exists())

    def test_skipped_test_name_is_not_a_skip_but_actual_skip_is_refused(self):
        for line, accepted in (
            ("test_not_silently_skipped ... ok", True),
            ("test_one ... skipped 'unsupported'", False),
        ):
            with self.fixture() as (root, _, _, manifest):
                (root / "stderr").write_text(line + "\nRan 3 tests in 1s\n\nOK\n")
                q = M.load("qualification.json")
                q["stderr"] = M.ref("stderr")
                (root / "qualification.json").write_bytes(D.canonical_trace_bytes(q))
                if accepted:
                    self.recover(manifest)
                else:
                    with self.assertRaisesRegex(ValueError, "OK/skip0"):
                        self.recover(manifest)
                    self.assertFalse((root / "recovery").exists())

    def test_success_preserves_original_and_rejects_second_attempt(self):
        with self.fixture() as (root, _, _, manifest):
            original = {p: M.read(p) for p in M.names("fixture")}
            result = self.recover(manifest)
            self.assertEqual(
                result["status"], "ALL_CELLS_REPLAYED_RECOVERY_ANALYSIS_COMPLETE"
            )
            self.assertTrue(result["postflight_pass"])
            self.assertEqual(result["before"], result["after"])
            self.assertEqual(original, {p: M.read(p) for p in M.names("fixture")})
            self.assertFalse((root / "fixture/summary.json").exists())
            self.assertEqual(
                M.read("recovery/summary.json"), D.canonical_trace_bytes(result)
            )
            with self.assertRaises(FileExistsError):
                self.recover(manifest)

    def test_exception_keeps_failed_attempt_and_original(self):
        with self.fixture() as (root, _, _, manifest):
            before = {
                p: hashlib.sha256(M.read(p)).hexdigest() for p in M.names("fixture")
            }
            with patch.object(
                D,
                "replay_allocation_search_bytes",
                side_effect=RuntimeError("interrupted"),
            ):
                with self.assertRaisesRegex(RuntimeError, "interrupted"):
                    self.recover(manifest)
            self.assertTrue((root / "recovery/FAILED.json").exists())
            self.assertFalse((root / "recovery/summary.json").exists())
            self.assertEqual(
                before,
                {p: hashlib.sha256(M.read(p)).hexdigest() for p in M.names("fixture")},
            )
            with self.assertRaises(FileExistsError):
                self.recover(manifest)

    def test_postflight_change_never_publishes_summary(self):
        with self.fixture() as (root, _, _, manifest):
            reduce = D.reduce_results

            def mutate(plan, records):
                value = reduce(plan, records)
                (root / "fixture/foreign").touch()
                return value

            with patch.object(D, "reduce_results", mutate):
                with self.assertRaisesRegex(ValueError, "membership"):
                    self.recover(manifest)
            self.assertFalse((root / "recovery/summary.json").exists())
            self.assertTrue((root / "recovery/FAILED.json").exists())


if __name__ == "__main__":
    unittest.main()
