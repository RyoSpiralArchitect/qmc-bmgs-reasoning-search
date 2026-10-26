"""Deterministic pair design and one-attempt boundary fixtures; no fresh cohort."""

from contextlib import ExitStack, contextmanager
import copy
from fractions import Fraction
import importlib.util
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch

from qmc_bmgs.benchmarks.countdown import CountdownTask
from qmc_bmgs.substrate.budget import TRACK_A_WORK_AXES
from qmc_bmgs_next import puct_return_study as S
from qmc_bmgs_next.puct_return import PuctReturnSpec, run_puct_return_cell

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "puct_return_development_tested", ROOT / "scripts/run_puct_return_development.py"
)
D = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(D)


def metric(success=False, missing=False):
    work = dict.fromkeys(TRACK_A_WORK_AXES, 0)
    return dict(
        success=success,
        minimum_terminal_error=None if missing else 0 if success else 3,
        missing_terminal=missing,
        budget_valid=True,
        actual_work=work,
        unspent_work={a: 512 if a == "legal_action_scores" else 100000 for a in work},
        first_exact_work=work if success else None,
        censored_at_work=None if success else work,
        terminal_count=0 if missing else 1,
        revisit_count=0,
        selection_count=0,
        stop_reason="method_complete",
        proposal_work={k: 0 for k in S.PROPOSAL_COUNTERS},
    )


def matrix(count=2):
    return [dict(key=list(k), metrics=metric()) for k in S.coordinates(count)]


class BoundaryTests(unittest.TestCase):
    def test_plan_is_outcome_blind_fixed_pair_and_no_run_permission(self):
        with (
            patch.object(D, "source_snapshot", return_value=[]),
            patch.object(D, "generate_solvable_task_suite") as gen,
            patch.object(D, "run_puct_return_cell") as run,
        ):
            plan = D.build_plan()
        gen.assert_not_called()
        run.assert_not_called()
        self.assertEqual(plan["planned_cells"], 1024)
        self.assertEqual(plan["maximum_primary_work"], 524288)
        self.assertEqual(plan["roots"], [0])
        self.assertEqual(
            plan["analysis"]["primary"]["contrast"], "puct-dense16-minus-puct"
        )
        self.assertEqual(plan["analysis"]["diagnostic_contrasts"], [])
        self.assertFalse(plan["execution_authorized"])
        self.assertTrue(plan["requires_conversation_verified_exact_candidate_approval"])
        self.assertIsNone(plan["runtime"]["perturbation"])
        self.assertEqual(len(set(map(tuple, plan["coordinates"]))), 1024)
        for name, _, count in D.COHORTS:
            cohort = D.load(name)
            self.assertEqual(len(cohort["tasks"]), count)
            self.assertTrue(
                all(
                    t["source_multiset_fingerprint"]
                    in plan["exclusions"]["source_multiset_fingerprints"]
                    for t in cohort["tasks"]
                )
            )

    def test_generator_collision_blocks_but_zero_is_not_a_random_seed(self):
        with patch.object(D, "GENERATOR_SEED", 26102601):
            with self.assertRaisesRegex(ValueError, "collision"):
                D.seed_exclusions()
        self.assertEqual(D.seed_exclusions()["deterministic_root"], 0)

    def test_count_and_roots_cannot_alias_or_replicate(self):
        for count, seeds in (
            (True, (0,)),
            (1.0, (0,)),
            (1, (False,)),
            (1, (0, 0)),
            (1, ()),
            (1, (41,)),
        ):
            with self.assertRaises(ValueError):
                S.coordinates(count, seeds)
        keys = S.coordinates(512)
        self.assertEqual(len(keys), 1024)
        self.assertEqual(sum(k[1] == "puct" for k in keys), 512)
        self.assertTrue(all(k[2] == 0 for k in keys))

    def test_complete_matrix_and_plain_type_validation(self):
        good = matrix()
        variants = [good[:-1], good + [good[0]]]
        for field, value in ((0, False), (0, 0.0), (1, "unknown"), (2, False)):
            rows = copy.deepcopy(good)
            rows[0]["key"][field] = value
            variants.append(rows)
        for field, value in (
            ("budget_valid", False),
            ("success", 1),
            ("minimum_terminal_error", -1),
        ):
            rows = copy.deepcopy(good)
            rows[0]["metrics"][field] = value
            variants.append(rows)
        for rows in variants:
            with self.assertRaises(ValueError):
                S.validate_matrix(rows, 2, (0,))
        self.assertEqual(len(S.validate_matrix(good, 2, (0,))), 4)

    def test_primary_has_one_physical_pair_per_source_and_exact_moments(self):
        rows = matrix()
        for row in rows:
            slot, method, _ = row["key"]
            row["metrics"] = metric(slot == 0 and method == "puct-dense16")
        out = S.reduce_matrix(rows, 2)
        self.assertEqual(out["primary"]["mean_rational"], [1, 2])
        self.assertEqual(out["primary"]["sample_source_variance_rational"], [1, 2])
        self.assertEqual(out["contrasts"][0]["paired_description_count"], 2)
        self.assertEqual(out["methods"]["puct"]["denominator"], 2)
        self.assertEqual(out["stochastic_roots"], [])
        self.assertIsNone(out["primary"]["approximate_interval"])
        self.assertIsNone(out["winner"])

    def test_zero_variance_and_precision_first_are_retained(self):
        out = S.source_moments([Fraction(1)] * 512, primary=True)
        self.assertEqual(out["development_readout"], "UNRESOLVED")
        self.assertIsNone(out["half_width"])
        out = S.source_moments([Fraction(1)] * 256 + [Fraction(-1)] * 256, primary=True)
        self.assertEqual(out["development_readout"], "IMPRECISE")

    def test_missing_and_no_hit_censoring_retained(self):
        rows = matrix(1)
        rows[0]["metrics"] = metric(missing=True)
        out = S.reduce_matrix(rows, 1)
        self.assertEqual(out["contrasts"][0]["minimum_error"]["missing"], 1)
        self.assertIsNotNone(out["cells"][0]["metrics"]["censored_at_work"])

    def test_implementation_consent_or_old_study_approval_is_not_run_authority(self):
        valid = dict(
            schema_version=D.APPROVAL_SCHEMA,
            candidate_commit="a" * 40,
            plan_digest="b" * 64,
            authority_kind="exact_candidate_human_approval",
            human_question="fixture",
            human_answer="fixture",
            scope=dict(D.APPROVAL_SCOPE),
        )
        D.validate_approval(valid, "a" * 40, "b" * 64)
        for field, value in (
            ("candidate_commit", "c" * 40),
            ("plan_digest", "d" * 64),
            ("authority_kind", "delegated_candidate_selection"),
            ("human_answer", ""),
            ("extra", True),
        ):
            bad = copy.deepcopy(valid)
            bad[field] = value
            with self.assertRaises(ValueError):
                D.validate_approval(bad, "a" * 40, "b" * 64)
        bad = copy.deepcopy(valid)
        bad["scope"]["run_count"] = True
        with self.assertRaises(ValueError):
            D.validate_approval(bad, "a" * 40, "b" * 64)

    def test_missing_authority_precedes_generation_or_output_fence(self):
        with (
            tempfile.TemporaryDirectory() as td,
            patch.object(D, "ROOT", Path(td)),
            patch.object(D, "preflight", side_effect=ValueError("authority")),
            patch.object(D, "cohort_from_recipe") as gen,
        ):
            with self.assertRaisesRegex(ValueError, "authority"):
                D.run("x", "y", "z", "q")
            gen.assert_not_called()
            self.assertEqual(list(Path(td).iterdir()), [])

    def test_exclusive_and_no_symlink_writes(self):
        with tempfile.TemporaryDirectory() as td, patch.object(D, "ROOT", Path(td)):
            D.save_new("a.json", {})
            with self.assertRaises(FileExistsError):
                D.save_new("a.json", {})
            (Path(td) / "link").symlink_to(Path(td), target_is_directory=True)
            for name in ("../escape", "/tmp/escape", "link/x.json"):
                with self.assertRaises(ValueError):
                    D.save_new(name, {})

    def test_pair_scores_before_first_exact_and_forgery(self):
        task = CountdownTask((1, 2, 3, 4, 5, 6), 720)
        records = [
            run_puct_return_cell(
                task, spec=PuctReturnSpec(m), budget_profile=D.profile()
            ).record
            for m in ("puct-dense16", "puct")
        ]
        pair = S.pair_diagnostics(*records)
        self.assertTrue(pair["same_first_trajectory"])
        self.assertTrue(pair["binary_pre_first_exact_all_means_zero"])
        self.assertEqual(pair["pre_first_exact_passive_mean_off_choice_flips"][1], 0)
        self.assertFalse(pair["stochastic_pairing_applicable"])
        bad = copy.deepcopy(records[0])
        next(
            e
            for e in bad["search_record"]["events"]
            if e["kind"] == "selection_committed"
        )["payload"]["selection_values"][0] += 1
        with self.assertRaises(ValueError):
            S.pair_diagnostics(bad, records[1])
        bad = copy.deepcopy(records[0])
        bad["summary"]["minimum_terminal_error"] = 999
        with self.assertRaises(ValueError):
            S.event_metrics(bad)

    def test_qualification_rejects_failed_empty_skipped_or_foreign_logs(self):
        with tempfile.TemporaryDirectory() as td, patch.object(D, "ROOT", Path(td)):
            refs = {}
            refs["helper"] = D.save_new(
                "helper.json", D.digested(dict(source_head="a" * 40))
            )
            refs["inputs"] = D.save_new(
                "inputs.json",
                D.digested(
                    dict(
                        source_head="a" * 40, helper=refs["helper"], before={"ok": True}
                    )
                ),
            )
            refs["intent"] = D.save_new(
                "intent.json",
                D.digested(
                    dict(
                        source_head="a" * 40,
                        inputs=refs["inputs"],
                        helper=refs["helper"],
                        argv=[
                            sys.executable,
                            "-P",
                            "-B",
                            str(D.ROOT / "scripts/validate.py"),
                        ],
                    )
                ),
            )
            refs["start"] = D.save_new(
                "start.json",
                D.digested(dict(source_head="a" * 40, intent=refs["intent"])),
            )
            (Path(td) / "stdout.log").write_text("repository validation: PASS\n")
            (Path(td) / "stderr.log").write_text("Ran 10 tests in 1.0s\n\nOK\n")
            refs.update(
                stdout=D.reference("stdout.log"), stderr=D.reference("stderr.log")
            )
            q = dict(
                source_head="a" * 40,
                exit_code=0,
                postflight_pass=True,
                postconditions_errors=[],
                before={"ok": True},
                after={"ok": True},
                **refs,
            )

            def writeq(value):
                (Path(td) / "process.json").write_bytes(
                    D.canonical_trace_bytes(D.digested(value))
                )

            writeq(q)
            D.qualify("process.json", "a" * 40)
            for k, v in (
                ("exit_code", False),
                ("exit_code", 1),
                ("postflight_pass", False),
                ("postconditions_errors", ["drift"]),
                ("after", {"ok": 1}),
            ):
                writeq(q | {k: v})
                with self.assertRaises(ValueError):
                    D.qualify("process.json", "a" * 40)
            for text in (
                "",
                "Ran 0 tests in 1.0s\nOK\n",
                "Ran 10 tests in 1.0s\nOK (skipped=1)\n",
            ):
                (Path(td) / "stderr.log").write_text(text)
                writeq(q | {"stderr": D.reference("stderr.log")})
                with self.assertRaises(ValueError):
                    D.qualify("process.json", "a" * 40)


class LifecycleTests(unittest.TestCase):
    @contextmanager
    def tiny(self):
        with tempfile.TemporaryDirectory() as td, ExitStack() as stack:
            root = Path(td)
            (root / "work").mkdir()
            for name, value in dict(
                ROOT=root, OUTPUT="work/tiny", COUNT=1, SEEDS=(0,), SCORES=128
            ).items():
                stack.enter_context(patch.object(D, name, value))
            plan = dict(deterministic_digest="a" * 64)
            cohort = D.digested(
                dict(
                    tasks=[CountdownTask((1, 1, 1, 1, 1, 1), 6).to_dict()],
                    generation={},
                    plan_digest="a" * 64,
                )
            )
            authority = dict(
                approval={"fixture": True}, qualification={"fixture": True}
            )
            stack.enter_context(
                patch.object(D, "preflight", return_value=(plan, "b" * 40, authority))
            )
            stack.enter_context(patch.object(D, "operation_guard"))
            stack.enter_context(
                patch.object(D, "cohort_from_recipe", return_value=cohort)
            )
            yield root / "work/tiny"

    def test_all_cell_replay_streams_and_refuses_repeat(self):
        with self.tiny() as out:
            commit = D.run("a" * 64, "b" * 40, "approval", "qualification")
            self.assertEqual(commit["cell_count"], 2)
            self.assertEqual(len(list(out.iterdir())), 5)
            with self.assertRaises(FileExistsError):
                D.run("a" * 64, "b" * 40, "approval", "qualification")
            with self.assertRaisesRegex(ValueError, "separate process"):
                D.analyze("a" * 64, "b" * 40, "approval", "qualification")
            # Isolated fixture: model the separate analysis process identity.
            # A real subprocess replay test below also exercises this boundary.
            with patch.object(D.os, "getpid", return_value=os.getpid() + 100000):
                result = D.analyze("a" * 64, "b" * 40, "approval", "qualification")
            self.assertEqual(result["replayed_cells"], 2)
            self.assertEqual(result["cross_budget_prefix_pairs"], 0)
            self.assertEqual(result["peak_detailed_cell_records_retained"], 2)
            self.assertEqual(result["reduction"]["methods"]["puct"]["denominator"], 1)
            self.assertEqual(len(list(out.iterdir())), 8)
            with self.assertRaisesRegex(ValueError, "already attempted"):
                D.analyze("a" * 64, "b" * 40, "approval", "qualification")

    def test_guard_failure_keeps_cell_and_fence_without_commit(self):
        with self.tiny() as out:
            record = run_puct_return_cell(
                CountdownTask((1, 1, 1, 1, 1, 1), 6),
                spec=PuctReturnSpec("puct-dense16"),
                budget_profile=D.profile(),
                root_seed=0,
            ).record
            record["summary"]["search_summary"]["budget_valid"] = False
            from qmc_bmgs_next.search_value import SearchValueResult

            with patch.object(
                D, "run_puct_return_cell", return_value=SearchValueResult(record)
            ):
                with self.assertRaisesRegex(ValueError, "INCOMPLETE_OR_INVALID"):
                    D.run("a" * 64, "b" * 40, "approval", "qualification")
            self.assertTrue((out / "cell-0000.json").exists())
            self.assertTrue((out / "STARTED.json").exists())
            self.assertFalse((out / "COMMIT.json").exists())

    def test_generation_failure_keeps_attempt_fence(self):
        with (
            self.tiny() as out,
            patch.object(
                D, "cohort_from_recipe", side_effect=ValueError("insufficient")
            ),
        ):
            with self.assertRaisesRegex(ValueError, "insufficient"):
                D.run("a" * 64, "b" * 40, "approval", "qualification")
            self.assertTrue((out / "STARTED.json").exists())
            self.assertFalse((out / "cohort.json").exists())
            with self.assertRaises(FileExistsError):
                D.run("a" * 64, "b" * 40, "approval", "qualification")

    def test_rehashed_commit_alias_missing_and_foreign_reference_fail(self):
        changes = [
            lambda c: c["cells"][0]["key"].__setitem__(0, False),
            lambda c: c["cells"].pop(),
            lambda c: c["cells"][0]["file"].update(path="work/tiny/cohort.json"),
            lambda c: c.update(extra=1),
            lambda c: c.update(cell_count=True),
        ]
        for change in changes:
            with self.subTest(change=change), self.tiny() as out:
                commit = D.run("a" * 64, "b" * 40, "approval", "qualification")
                change(commit)
                core = {k: v for k, v in commit.items() if k != "deterministic_digest"}
                (out / "COMMIT.json").write_bytes(
                    D.canonical_trace_bytes(D.digested(core))
                )
                with self.assertRaises(ValueError):
                    D.analyze("a" * 64, "b" * 40, "approval", "qualification")
                self.assertFalse((out / "summary.json").exists())

    def test_actual_separate_process_analysis_fixture(self):
        with self.tiny() as out:
            D.run("a" * 64, "b" * 40, "approval", "qualification")
            code = """
import importlib.util, sys
from pathlib import Path
from unittest.mock import patch
from qmc_bmgs.benchmarks.countdown import CountdownTask
spec = importlib.util.spec_from_file_location('tested_child', sys.argv[1])
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)
d.ROOT, d.OUTPUT, d.COUNT, d.SEEDS, d.SCORES = Path(sys.argv[2]), 'work/tiny', 1, (0,), 128
cohort = d.digested(dict(tasks=[CountdownTask((1,1,1,1,1,1),6).to_dict()], generation={}, plan_digest='a'*64))
with patch.object(d, 'preflight', return_value=({'deterministic_digest':'a'*64}, 'b'*40, {'approval':{'fixture':True},'qualification':{'fixture':True}})), patch.object(d, 'operation_guard'), patch.object(d, 'cohort_from_recipe', return_value=cohort):
    result = d.analyze('a'*64, 'b'*40, 'approval', 'qualification')
    assert result['replayed_cells'] == 2
    sys.stdout.buffer.write(d.canonical_trace_bytes(result))
"""
            child = subprocess.run(
                [
                    sys.executable,
                    "-P",
                    "-B",
                    "-c",
                    code,
                    str(ROOT / "scripts/run_puct_return_development.py"),
                    str(out.parent.parent),
                ],
                cwd="/tmp",
                env=dict(os.environ, PYTHONPATH=str(ROOT / "src")),
                check=True,
                capture_output=True,
            )
            self.assertEqual(child.stdout, (out / "summary.json").read_bytes())

    def test_saved_decision_tamper_even_with_refreshed_outer_hash_is_rejected(self):
        with self.tiny() as out:
            commit = D.run("a" * 64, "b" * 40, "approval", "qualification")
            name = commit["cells"][0]["file"]["path"]
            cell = D.load(name)
            cell["summary"]["minimum_terminal_error"] = 999
            (D.ROOT / name).write_bytes(
                D.canonical_trace_bytes(
                    D.digested(
                        {k: v for k, v in cell.items() if k != "deterministic_digest"}
                    )
                )
            )
            commit["cells"][0]["file"] = D.reference(name)
            (out / "COMMIT.json").write_bytes(
                D.canonical_trace_bytes(
                    D.digested(
                        {k: v for k, v in commit.items() if k != "deterministic_digest"}
                    )
                )
            )
            with (
                patch.object(D.os, "getpid", return_value=os.getpid() + 100000),
                self.assertRaises(ValueError),
            ):
                D.analyze("a" * 64, "b" * 40, "approval", "qualification")
            self.assertTrue((out / "analysis.STARTED.json").exists())
            self.assertFalse((out / "summary.json").exists())


if __name__ == "__main__":
    unittest.main()
