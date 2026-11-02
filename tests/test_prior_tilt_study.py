"""Outcome-blind boundary fixtures; no prospective cohort is generated."""

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
from qmc_bmgs_next import prior_tilt_study as S
from qmc_bmgs_next.prior_tilt import PriorTiltSpec, run_prior_tilt_cell


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "prior_tilt_development_tested", ROOT / "scripts/run_prior_tilt_development.py"
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


def matrix(count=2, seeds=(41, 42)):
    return [dict(key=list(k), metrics=metric()) for k in S.coordinates(count, seeds)]


class BoundaryTests(unittest.TestCase):
    def test_plan_generation_is_outcome_blind_and_seals_all_fixed_conditions(self):
        with (
            patch.object(D, "source_snapshot", return_value=[]),
            patch.object(D, "generate_solvable_task_suite") as generate,
            patch.object(D, "run_prior_tilt_cell") as run,
        ):
            plan = D.build_plan()
        generate.assert_not_called()
        run.assert_not_called()
        self.assertEqual(plan["planned_cells"], 2304)
        self.assertEqual(plan["planned_branch_runs"], 2304)
        self.assertEqual(plan["maximum_primary_work"], 1179648)
        self.assertEqual(
            plan["analysis"]["primary"]["contrast"], "prior-tilt16-minus-puct"
        )
        self.assertFalse(plan["execution_authorized"])
        self.assertEqual(plan["analysis"]["cross_budget_prefix_pairs"], 0)
        self.assertEqual(
            len(plan["coordinates"]), len(set(map(tuple, plan["coordinates"])))
        )
        self.assertEqual(len(plan["seed_exclusions"]["current_branch0"]), 4)
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

    def test_fixed_seed_collision_blocks_without_replacement(self):
        with patch.object(D, "SEEDS", (41, 42)):
            with self.assertRaisesRegex(ValueError, "collision"):
                D.seed_exclusions()

    def test_source_drift_is_rejected_before_cell_execution(self):
        with tempfile.TemporaryDirectory() as td, patch.object(D, "ROOT", Path(td)):
            plan = {
                "source_files": [],
                "exclusions": {"authority_refs": [], "fixture_source_files": []},
                "seed_exclusions": {"refs": []},
            }
            with patch.object(D, "clean_head", return_value="wrong"):
                with self.assertRaisesRegex(ValueError, "HEAD"):
                    D.operation_guard(plan, "expected")

    def test_bad_source_and_seed_types_cannot_alias_coordinates(self):
        for count, seeds in (
            (True, (41,)),
            (1.0, (41,)),
            (1, (True,)),
            (1, (41, 41)),
            (1, ()),
        ):
            with self.assertRaises(ValueError):
                S.coordinates(count, seeds)

    def test_fixed_matrix_is_not_five_times_four_seeds(self):
        keys = S.coordinates(256, (262144, 262145, 262146, 262147))
        self.assertEqual(len(keys), 2304)
        self.assertEqual(sum(k[1] == "puct" for k in keys), 256)
        self.assertEqual(sum(k[1] == "prior-tilt16" for k in keys), 1024)
        self.assertTrue(all(k[2] == 0 for k in keys if k[1] in ("puct",)))

    def test_closed_matrix_rejects_missing_duplicate_alias_extra_and_guard(self):
        good = matrix()
        variants = [good[:-1], good + [good[0]]]
        for field, value in ((0, False), (0, 0.0), (1, "other"), (2, True)):
            rows = copy.deepcopy(good)
            rows[0]["key"][field] = value
            variants.append(rows)
        for edit in (
            lambda r: r[0].update(extra=1),
            lambda r: r[0]["metrics"].update(budget_valid=False),
            lambda r: r[0]["metrics"].update(success=1),
            lambda r: r[0]["metrics"]["actual_work"].update(transitions=-1),
        ):
            rows = copy.deepcopy(good)
            edit(rows)
            variants.append(rows)
        for rows in variants:
            with self.subTest(rows=rows[:1]), self.assertRaises(ValueError):
                S.validate_matrix(rows, 2, (41, 42))
        self.assertEqual(len(S.validate_matrix(good, 2, (41, 42))), 10)

    def test_primary_uses_sources_and_one_puct_row(self):
        rows = matrix()
        for r in rows:
            slot, method, seed = r["key"]
            r["metrics"] = metric(
                (slot == 0 and method == "prior-tilt16" and seed == 41)
                or (slot == 1 and method == "puct")
            )
        result = S.reduce_matrix(rows, 2, (41, 42))
        primary = result["primary"]
        self.assertEqual(primary["mean_rational"], [-1, 4])
        self.assertEqual(primary["sample_source_variance_rational"], [9, 8])
        self.assertEqual(result["methods"]["prior-tilt16"]["denominator"], 4)
        self.assertEqual(result["methods"]["puct"]["denominator"], 2)
        self.assertEqual(primary["source_count"], 2)
        self.assertIsNone(primary["approximate_interval"])
        self.assertIsNone(result["winner"])
        self.assertIsNone(result["scientific_decision"])

    def test_zero_variance_has_no_zero_width_certainty(self):
        out = S.source_moments([Fraction(1)] * 128, primary=True)
        self.assertEqual(out["development_readout"], "UNRESOLVED")
        self.assertIsNone(out["half_width"])
        self.assertIsNone(out["precision_target_met"])

    def test_precision_precedes_promising_and_diagnostic_has_no_gate(self):
        values = [Fraction(1)] * 90 + [Fraction(-1)] * 38
        out = S.source_moments(values, primary=True)
        self.assertEqual(out["development_readout"], "IMPRECISE")
        self.assertGreater(out["estimate"], 0.02)
        self.assertIsNone(
            S.source_moments(values, primary=False)["development_readout"]
        )

    def test_model_readout_boundaries_and_exact_moments(self):
        for base, expected in (
            (Fraction(0), "NO_PRACTICAL_UPLIFT_SIGNAL"),
            (Fraction(1, 2), "PROMISING_FOR_FRESH_CONFIRMATION"),
            (Fraction(1, 50), "UNRESOLVED"),
        ):
            values = [base - Fraction(1, 100)] * 64 + [base + Fraction(1, 100)] * 64
            out = S.source_moments(values, primary=True)
            self.assertEqual(out["development_readout"], expected)
            self.assertEqual(out["mean_rational"], [base.numerator, base.denominator])

    def test_missing_error_and_no_hit_are_retained(self):
        rows = matrix(1, (41,))
        rows[0]["metrics"] = metric(missing=True)
        result = S.reduce_matrix(rows, 1, (41,))
        self.assertEqual(result["contrasts"][0]["minimum_error"]["missing"], 1)
        self.assertEqual(result["methods"]["prior-tilt16"]["missing_terminal"], 1)
        self.assertIsNotNone(result["cells"][0]["metrics"]["censored_at_work"])

    def test_authorization_rejects_mismatched_candidate_plan_scope_or_kind(self):
        valid = dict(
            schema_version=D.APPROVAL_SCHEMA,
            candidate_commit="a" * 40,
            plan_digest="b" * 64,
            authority_kind="delegated_candidate_selection",
            human_proposal="one candidate then three-arm comparison proposal",
            human_answer="approved",
            scope=dict(D.APPROVAL_SCOPE),
        )
        D.validate_approval(valid, "a" * 40, "b" * 64)
        for field, value in (
            ("candidate_commit", "c" * 40),
            ("plan_digest", "d" * 64),
            ("authority_kind", "automation"),
            ("human_answer", ""),
            ("extra", True),
        ):
            bad = copy.deepcopy(valid)
            bad[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                D.validate_approval(bad, "a" * 40, "b" * 64)
        bad = copy.deepcopy(valid)
        bad["scope"]["run_count"] = True
        with self.assertRaises(ValueError):
            D.validate_approval(bad, "a" * 40, "b" * 64)

    def test_invalid_approval_precedes_generation_and_fence(self):
        with tempfile.TemporaryDirectory() as td, patch.object(D, "ROOT", Path(td)):
            with (
                patch.object(D, "preflight", side_effect=ValueError("authority")),
                patch.object(D, "cohort_from_recipe") as generate,
            ):
                with self.assertRaisesRegex(ValueError, "authority"):
                    D.run("x", "y", "z", "q")
                generate.assert_not_called()
                self.assertEqual(list(Path(td).iterdir()), [])

    def test_exclusive_write_and_parent_symlink_rejection(self):
        with tempfile.TemporaryDirectory() as td, patch.object(D, "ROOT", Path(td)):
            D.save_new("a.json", {"a": 1})
            with self.assertRaises(FileExistsError):
                D.save_new("a.json", {"a": 2})
            (Path(td) / "link").symlink_to(Path(td), target_is_directory=True)
            for name in ("../escape", "/tmp/escape", "link/x.json"):
                with self.assertRaises(ValueError):
                    D.save_new(name, {})

    def test_event_metrics_rebuild_terminal_and_charge_evidence(self):
        task = CountdownTask((1, 1, 1, 1, 1, 1), 6)
        record = run_prior_tilt_cell(
            task,
            spec=PriorTiltSpec("prior-tilt16"),
            budget_profile=D.profile(),
            root_seed=41,
        ).record
        metrics = S.event_metrics(record)
        self.assertEqual(
            metrics["success"], record["summary"]["search_summary"]["success_any"]
        )
        for field, value in (
            ("minimum_terminal_error", 999),
            ("first_exact_work", None),
        ):
            bad = copy.deepcopy(record)
            bad["summary"][field] = value
            with self.assertRaises(ValueError):
                S.event_metrics(bad)
        bad = copy.deepcopy(record)
        charge = next(
            e["charge"]
            for e in bad["search_record"]["events"]
            if e["charge"] is not None
        )
        charge["delta"]["transitions"] = True
        with self.assertRaises(ValueError):
            S.event_metrics(bad)

    def test_passive_pair_diagnostics_preserve_nontrivial_history(self):
        task = CountdownTask((1, 2, 3, 4, 5, 6), 720)
        records = [
            run_prior_tilt_cell(
                task, spec=PriorTiltSpec(m), budget_profile=D.profile(), root_seed=41
            ).record
            for m in ("prior-tilt16", "prior-mean-off")
        ]
        result = S.pair_diagnostics(*records)
        self.assertGreater(result["common_material_coordinates"], 0)
        self.assertFalse(result["whole_trajectory_common_random_numbers_claim"])
        self.assertTrue(result["passive_flip_is_not_counterfactual_rollout"])
        bad = copy.deepcopy(records[0])
        e = next(
            e
            for e in bad["search_record"]["events"]
            if e["kind"] == "selection_committed"
        )
        e["payload"]["selection_values"][0] += 1
        with self.assertRaises(ValueError):
            S.pair_diagnostics(bad, records[1])

    def test_cohort_recipe_does_not_access_solver_calibrations(self):
        class FixtureSuite:
            tasks = (CountdownTask((1, 1, 1, 1, 1, 1), 6),)
            generation_manifest = {"attempt_count": 1}

            @property
            def calibrations(self):
                raise AssertionError("witness/hardness must not enter policy")

        plan = dict(
            exclusions=dict(
                task_fingerprints=["t"],
                source_multiset_fingerprints=["s"],
                deterministic_digest="x",
            ),
            generation=dict(count=1, seed=9, max_attempts=10),
            deterministic_digest="p",
        )
        with patch.object(
            D, "generate_solvable_task_suite", return_value=FixtureSuite()
        ) as gen:
            cohort = D.cohort_from_recipe(plan)
        self.assertEqual(
            gen.call_args.kwargs["excluded_source_multiset_fingerprints"], ["s"]
        )
        self.assertEqual(
            set(cohort), {"tasks", "generation", "plan_digest", "deterministic_digest"}
        )

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
                ROOT=root, OUTPUT="work/tiny", COUNT=1, SEEDS=(41,), SCORES=128
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
            self.assertEqual(commit["cell_count"], 3)
            self.assertEqual(len(list(out.iterdir())), 6)
            with self.assertRaises(FileExistsError):
                D.run("a" * 64, "b" * 40, "approval", "qualification")
            with self.assertRaisesRegex(ValueError, "separate process"):
                D.analyze("a" * 64, "b" * 40, "approval", "qualification")
            # Isolated fixture: model the separate analysis process identity.
            # A real subprocess replay test below also exercises this boundary.
            with patch.object(D.os, "getpid", return_value=os.getpid() + 100000):
                result = D.analyze("a" * 64, "b" * 40, "approval", "qualification")
            self.assertEqual(result["replayed_cells"], 3)
            self.assertEqual(result["cross_budget_prefix_pairs"], 0)
            self.assertEqual(result["peak_detailed_cell_records_retained"], 2)
            self.assertEqual(result["reduction"]["methods"]["puct"]["denominator"], 1)
            self.assertEqual(len(list(out.iterdir())), 9)
            with self.assertRaisesRegex(ValueError, "already attempted"):
                D.analyze("a" * 64, "b" * 40, "approval", "qualification")

    def test_guard_failure_keeps_cell_and_fence_without_commit(self):
        with self.tiny() as out:
            record = run_prior_tilt_cell(
                CountdownTask((1, 1, 1, 1, 1, 1), 6),
                spec=PriorTiltSpec("prior-tilt16"),
                budget_profile=D.profile(),
                root_seed=41,
            ).record
            record["summary"]["search_summary"]["budget_valid"] = False
            from qmc_bmgs_next.search_value import SearchValueResult

            with patch.object(
                D, "run_prior_tilt_cell", return_value=SearchValueResult(record)
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
d.ROOT, d.OUTPUT, d.COUNT, d.SEEDS, d.SCORES = Path(sys.argv[2]), 'work/tiny', 1, (41,), 128
cohort = d.digested(dict(tasks=[CountdownTask((1,1,1,1,1,1),6).to_dict()], generation={}, plan_digest='a'*64))
with patch.object(d, 'preflight', return_value=({'deterministic_digest':'a'*64}, 'b'*40, {'approval':{'fixture':True},'qualification':{'fixture':True}})), patch.object(d, 'operation_guard'), patch.object(d, 'cohort_from_recipe', return_value=cohort):
    result = d.analyze('a'*64, 'b'*40, 'approval', 'qualification')
    assert result['replayed_cells'] == 3
    sys.stdout.buffer.write(d.canonical_trace_bytes(result))
"""
            child = subprocess.run(
                [
                    sys.executable,
                    "-P",
                    "-B",
                    "-c",
                    code,
                    str(ROOT / "scripts/run_prior_tilt_development.py"),
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
