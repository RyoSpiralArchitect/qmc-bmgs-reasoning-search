"""Connector boundary/fault tests. Mock admission is NOT cohort qualification."""

from __future__ import annotations

import copy
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "feedback_budget_execution_tested",
    ROOT / "scripts/run_feedback_budget_execution.py",
)
assert SPEC is not None and SPEC.loader is not None
R = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(R)
S = R.storage


def rehash(value):
    return R.digested({k: v for k, v in value.items() if k != "deterministic_digest"})


def env():
    return dict(
        source={"execution_revision": "f" * 40},
        runtime={},
        baseline={},
        authorities={},
        admission_proof={},
    )


class Setup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = R.load_inputs(R.PUBLIC)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.output, self.auth_path = self.root / "out", self.root / "auth.json"
        self.auth = R.candidate(self.inputs, self.output, env(), None)
        self.auth_path.write_bytes(R.canonical(self.auth))
        self.snapshot = R.core.FileSnapshot.capture(self.auth_path)
        self.admitted = R.Admission(
            self.inputs,
            self.auth,
            self.snapshot,
            env(),
            "f" * 40,
            "f" * 40,
            lambda: None,
        )
        self.claim = S.claim_value(self.auth, "f" * 40, "f" * 40, "e" * 64)
        self.binding = R.binding(self.admitted, self.claim)
        self.ledger_patch = patch.object(S, "LEDGER", self.root / "ledger")
        self.ledger_patch.start()

    def tearDown(self):
        self.ledger_patch.stop()
        self.temp.cleanup()

    def row(self, index, identity=False):
        cell = self.inputs.cells[index]
        search = (
            {
                "run_identity": R.q.build_search_run_identity(
                    **self.inputs.arguments(cell)
                )
            }
            if identity
            else {"synthetic_only": True}
        )
        return R.digested(
            dict(
                schema_version=S.DOMAIN + "/record",
                **cell,
                run_binding_digest=self.binding["deterministic_digest"],
                search_record=search,
            )
        )

    def receipt(self):
        return R.digested(
            dict(
                schema_version=S.DOMAIN + "/execution-receipt",
                run_binding_digest=self.binding["deterministic_digest"],
                synthetic_only=True,
            )
        )

    def action(self, emit):
        for index in range(192):
            emit(index, self.row(index))
        return self.receipt()


class IdentityTests(Setup):
    def test_fixed_public_domain_no_new_generation_or_search(self):
        with (
            patch.object(R.admission, "load_seal", side_effect=AssertionError("seal")),
            patch.object(
                R.q,
                "run_countdown_track_a_search",
                side_effect=AssertionError("search"),
            ),
        ):
            inputs = R.load_inputs(R.PUBLIC)
            inputs.revalidate()
        self.assertEqual(inputs.manifest["tasks"], R.k.fixture_manifest()["tasks"])
        self.assertEqual(inputs.manifest["source_multiset_count"], 1)
        self.assertEqual(len({c["cell_id"] for c in inputs.cells}), 192)
        self.assertNotEqual(
            inputs.cells[0]["cell_id"], R.k.public_inputs().cells[0]["cell_id"]
        )
        with self.assertRaises(TypeError):
            R.Inputs(R.canonical(inputs.manifest))
        with self.assertRaises(AttributeError):
            inputs._raw = b"{}\n"

    def test_accessors_are_detached_and_numeric_aliases_rejected(self):
        value = self.inputs.manifest
        value["tasks"][0]["target"] = 999
        self.assertEqual(self.inputs.arguments(self.inputs.cells[0])["task"].target, 1)
        for field, value in (
            ("cell_index", True),
            ("cell_index", 192),
            ("cell_id", "e" * 64),
        ):
            cell = self.inputs.cells[0]
            cell[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.inputs.arguments(cell)

    def test_wrong_domains_flags_digest_reject_before_environment_or_seal(self):
        values = [R.k.fixture_manifest(), R.k.contract.build_contract(), self.auth]
        for field, value in (
            ("schema_version", R.k.DOMAIN + "/authorization-candidate"),
            ("candidate_is_execution_authority", True),
            ("expected_cell_count", True),
            ("extra", False),
        ):
            values.append(rehash({**self.auth, field: value}))
        for value in values:
            self.auth_path.write_bytes(R.canonical(value))
            with (
                self.subTest(value=value.get("schema_version")),
                patch.object(R, "environment") as environment,
                patch.object(R, "load_inputs") as inputs,
                self.assertRaises(ValueError),
            ):
                R.admit(
                    R.DEVELOPMENT,
                    self.auth_path,
                    value["deterministic_digest"],
                    "f" * 40,
                )
            environment.assert_not_called()
            inputs.assert_not_called()
        with self.assertRaisesRegex(ValueError, "digest"):
            R.auth_shape(R.canonical(self.auth), R.PUBLIC, "0" * 64)

    def test_all_final_identities_close_before_any_replay_or_reduction(self):
        rows = [self.row(i, identity=True) for i in range(192)]
        variants = [rows[:-1], rows + [rows[0]], rows[:-1] + [rows[0]]]
        for mutate in (
            lambda row: row.update(cell_index=True),
            lambda row: row.update(run_binding_digest="0" * 64),
            lambda row: row["search_record"]["run_identity"].update(exploration_seed=3),
        ):
            value = copy.deepcopy(rows)
            mutate(value[-1])
            value[-1] = rehash(value[-1])
            variants.append(value)
        for value in variants:
            with (
                self.subTest(length=len(value)),
                patch.object(R.q, "replay_countdown_track_a_search_bytes") as replay,
                patch.object(R.public.analysis, "reduce_matrix") as reduce,
                self.assertRaises(ValueError),
            ):
                R.reduce_rows(self.inputs, value, self.binding)
            replay.assert_not_called()
            reduce.assert_not_called()

    def test_reviewed_git_bytes_checked_before_qualifier_or_generator(self):
        value = rehash(
            {
                **self.auth,
                "schema_version": R.DOMAIN + "/authorization-candidate",
                "execution_mode": R.DEVELOPMENT,
                "experiment_id": S.DEVELOPMENT_ID,
            }
        )
        self.auth_path.write_bytes(R.canonical(value))
        with (
            patch.object(R.public, "_output", side_effect=lambda x: Path(x)),
            patch.object(R, "oid", side_effect=lambda x: x),
            patch.object(R.core, "require_ancestor"),
            patch.object(R, "reviewed_file", side_effect=ValueError("unreviewed")),
            patch.object(R, "qualified_public") as qualifier,
            patch.object(R, "load_inputs") as inputs,
            self.assertRaisesRegex(ValueError, "unreviewed"),
        ):
            R.admit(
                R.DEVELOPMENT, self.auth_path, value["deterministic_digest"], "f" * 40
            )
        qualifier.assert_not_called()
        inputs.assert_not_called()

    def test_valid_public_admission_reconstructs_environment_and_output(self):
        with (
            patch.object(R.public, "_output", side_effect=lambda x: Path(x)),
            patch.object(R, "oid", side_effect=lambda x: x),
            patch.object(R.core, "require_ancestor"),
            patch.object(R, "environment", return_value=env()),
            patch.object(R, "check_environment"),
        ):
            result = R.admit(
                R.PUBLIC, self.auth_path, self.auth["deterministic_digest"], "f" * 40
            )
        self.assertEqual(result.auth, self.auth)

    def test_environment_and_parent_tamper_rejected_before_input_loader(self):
        for field in ("source", "runtime", "baseline", "output_parent"):
            value = copy.deepcopy(self.auth)
            value[field]["tampered"] = True
            value = rehash(value)
            self.auth_path.write_bytes(R.canonical(value))
            with (
                self.subTest(field=field),
                patch.object(R.public, "_output", side_effect=lambda x: Path(x)),
                patch.object(R, "oid", side_effect=lambda x: x),
                patch.object(R.core, "require_ancestor"),
                patch.object(R, "environment", return_value=env()),
                patch.object(R, "load_inputs") as inputs,
                self.assertRaises(ValueError),
            ):
                R.admit(
                    R.PUBLIC, self.auth_path, value["deterministic_digest"], "f" * 40
                )
            inputs.assert_not_called()

    def test_synthetic_development_projection_only_via_seal_loader(self):
        source = self.inputs.manifest
        seal = dict(
            contract={"deterministic_digest": source["contract_digest"]},
            cohort=dict(tasks=source["tasks"], deterministic_digest="a" * 64),
            cells=source["cells"],
            schedule_digest=source["schedule_digest"],
            deterministic_digest="b" * 64,
        )
        fake = SimpleNamespace(manifest=seal, revalidate=lambda: None)
        with patch.object(R.admission, "load_seal", return_value=fake) as loader:
            value = R.load_inputs(R.DEVELOPMENT)
        loader.assert_called_once_with(R.admission.COHORT_PATH)
        self.assertEqual(value.manifest["cohort_seal"]["seal_digest"], "b" * 64)
        self.assertFalse(value.manifest["development_execution_authorized"])

    def test_public_qualification_cannot_be_digest_only_or_other_domain(self):
        self.auth_path.write_bytes(R.canonical(self.auth))
        with patch.object(R, "analyze") as analyze, self.assertRaises(ValueError):
            R.qualified_public(self.auth_path)
        analyze.assert_not_called()
        saved = R.digested(
            dict(
                schema_version=R.DOMAIN + "/analysis",
                execution_mode=R.PUBLIC,
                scientific_decision=None,
                development_cells_executed=0,
                output_path=str(self.output),
            )
        )
        self.auth_path.write_bytes(R.canonical(saved))
        with (
            patch.object(
                R, "analyze", return_value=({**saved, "extra": 1}, lambda: None)
            ) as analyze,
            self.assertRaisesRegex(ValueError, "reproduce"),
        ):
            R.qualified_public(self.auth_path)
        analyze.assert_called_once_with(R.PUBLIC, str(self.output))


class StorageTests(Setup):
    def consume(self):
        claim, snapshot = S.consume(self.auth, "f" * 40, "f" * 40, R.core.FileSnapshot)
        self.binding = R.binding(self.admitted, claim)
        return claim, snapshot

    def test_claim_durable_before_output_and_reconsume_rejected(self):
        claim, snapshot = self.consume()
        self.assertFalse(self.output.exists())
        self.assertEqual(snapshot.raw, R.canonical(claim))
        S.inspect_claim(self.binding, R.core.FileSnapshot).revalidate()
        with self.assertRaises(S.ExecutionFailure) as raised:
            self.consume()
        self.assertEqual(raised.exception.status, "AUTHORIZATION_ALREADY_SPENT")
        self.assertEqual(snapshot.raw, snapshot.path.read_bytes())

    def test_fixed_study_slot_ignores_candidate_output_and_cohort_changes(self):
        development = {**self.auth, "execution_mode": R.DEVELOPMENT}
        changed = rehash(
            {
                **development,
                "output_path": str(self.root / "other"),
                "input_manifest_digest": "1" * 64,
            }
        )
        self.assertEqual(S.claim_path(development), S.claim_path(changed))
        self.assertNotEqual(
            S.claim_path(self.auth),
            S.claim_path(rehash({**self.auth, "output_path": "other"})),
        )
        self.auth = development
        S.consume(self.auth, "f" * 40, "f" * 40, R.core.FileSnapshot)
        self.auth = changed
        with self.assertRaisesRegex(S.ExecutionFailure, "occupied"):
            self.consume()

    def test_existing_nonfile_claim_is_spent_not_replaced(self):
        S.LEDGER.mkdir(mode=0o700)
        path = S.claim_path(self.auth)
        path.mkdir()
        with self.assertRaises(S.ExecutionFailure) as raised:
            self.consume()
        self.assertEqual(raised.exception.status, "AUTHORIZATION_ALREADY_SPENT")
        self.assertTrue(path.is_dir())

    def test_claim_fsync_failure_is_uncertain_and_retained(self):
        S.LEDGER.mkdir(mode=0o700)
        with (
            patch.object(
                S.mechanics._PinnedParent, "fsync", side_effect=OSError("fsync")
            ),
            self.assertRaises(S.ExecutionFailure) as raised,
        ):
            self.consume()
        self.assertEqual(raised.exception.status, "CONSUMPTION_UNCERTAIN")
        self.assertIsNone(raised.exception.authorization_consumed)
        self.assertTrue(S.claim_path(self.auth).exists())
        with self.assertRaisesRegex(S.ExecutionFailure, "occupied"):
            self.consume()

    def test_195_file_closure_and_claim_linkage(self):
        self.consume()
        result = S.publish(self.output, self.binding, self.action, lambda: None)
        inspection = S.inspect(self.output)
        self.assertEqual(len(list(self.output.iterdir())), 195)
        self.assertEqual(inspection.commit, result)
        self.assertEqual(inspection.rows, [self.row(i) for i in range(192)])
        self.assertEqual(inspection.receipt, self.receipt())
        inspection.revalidate()

    def test_start_failure_is_spent_without_search(self):
        self.consume()
        with self.assertRaises(S.ExecutionFailure) as raised:
            S.publish(
                self.output,
                self.binding,
                lambda emit: self.fail("search"),
                lambda: (_ for _ in ()).throw(ValueError("preflight")),
            )
        self.assertEqual(raised.exception.status, "SPENT_NOT_RUN")
        self.assertFalse(self.output.exists())
        with self.assertRaisesRegex(S.ExecutionFailure, "occupied"):
            self.consume()

    def test_partial_failure_retains_claim_cells_failure_and_never_commits(self):
        self.consume()

        def action(emit):
            emit(0, self.row(0))
            raise ValueError("search interrupted")

        with self.assertRaises(S.ExecutionFailure) as raised:
            S.publish(self.output, self.binding, action, lambda: None)
        self.assertEqual(raised.exception.status, "INVALID_ANALYSIS")
        self.assertEqual(
            {p.name for p in self.output.iterdir()},
            {"STARTED.json", "cell-000.json", "FAILURE.json"},
        )
        with self.assertRaises(ValueError):
            S.inspect(self.output)
        with self.assertRaisesRegex(S.ExecutionFailure, "occupied"):
            self.consume()

    def test_post_commit_failure_uncertain_no_countermand(self):
        self.consume()

        def check():
            if (self.output / "COMMIT.json").exists():
                raise ValueError("late change")

        with self.assertRaises(S.ExecutionFailure) as raised:
            S.publish(self.output, self.binding, self.action, check)
        self.assertEqual(raised.exception.status, "PUBLICATION_UNCERTAIN")
        self.assertTrue((self.output / "COMMIT.json").exists())
        self.assertFalse((self.output / "FAILURE.json").exists())

    def test_missing_extra_tampered_and_relinked_publication_reject(self):
        self.consume()
        S.publish(self.output, self.binding, self.action, lambda: None)
        cell = self.output / "cell-191.json"
        raw = cell.read_bytes()
        for mutation in (
            lambda: cell.write_bytes(b"{}\n"),
            lambda: cell.unlink(),
            lambda: (self.output / "extra").write_bytes(b"x"),
        ):
            mutation()
            with self.assertRaises((OSError, ValueError)):
                S.inspect(self.output)
            cell.write_bytes(raw)
            cell.chmod(0o600)
            (self.output / "extra").unlink(missing_ok=True)

    def test_binding_cannot_promote_or_change_claim(self):
        for field, value in (
            ("development_execution_authorized", True),
            ("input_manifest_digest", "0" * 64),
            ("reviewed_revision", "0" * 40),
            ("extra", False),
        ):
            with self.subTest(field=field), self.assertRaises(ValueError):
                S.frozen_binding(rehash({**self.binding, field: value}))

    def test_claim_tampering_rejected(self):
        self.consume()
        path = S.claim_path(self.auth)
        path.write_bytes(
            R.canonical(rehash({**self.binding["claim"], "owner_nonce": "0" * 64}))
        )
        with self.assertRaisesRegex(ValueError, "claim"):
            S.inspect_claim(self.binding, R.core.FileSnapshot)


class AdapterTests(Setup):
    def test_spent_claim_rejects_before_admission_regeneration_or_search(self):
        S.consume(self.auth, "f" * 40, "f" * 40, R.core.FileSnapshot)
        with (
            patch.object(R, "admit") as admit,
            patch.object(R, "record") as record,
            self.assertRaises(S.ExecutionFailure) as raised,
        ):
            R.run(R.PUBLIC, self.auth_path, self.auth["deterministic_digest"], "f" * 40)
        self.assertEqual(raised.exception.status, "AUTHORIZATION_ALREADY_SPENT")
        admit.assert_not_called()
        record.assert_not_called()

    def test_synthetic_independent_analyzer_roundtrip_not_scientific_evidence(self):
        claim, _ = S.consume(self.auth, "f" * 40, "f" * 40, R.core.FileSnapshot)
        self.binding = R.binding(self.admitted, claim)
        receipt = rehash(
            {
                **self.receipt(),
                "integrity": {"synthetic_only": True},
                "reduction": {"synthetic_only": True},
                "development_cells_executed": 0,
                "scientific_decision": None,
            }
        )

        def action(emit):
            self.action(emit)
            return receipt

        S.publish(self.output, self.binding, action, lambda: None)
        summary = self.root / "summary.json"
        with (
            patch.object(R.public, "_output", side_effect=lambda x: Path(x)),
            patch.object(R, "admit", return_value=self.admitted),
            patch.object(self.admitted, "revalidate"),
            patch.object(R, "reduce_rows", return_value=receipt) as reduce,
        ):
            first = R.analyze_and_save(R.PUBLIC, self.output, summary)
            second = R.verify(R.PUBLIC, self.output, summary)
        self.assertEqual(first, second)
        self.assertEqual(reduce.call_count, 2)
        self.assertIsNone(first["scientific_decision"])
        self.assertTrue(first["authorization_consumed"])
        self.assertEqual(first["output_path"], str(self.output))

    def test_synthetic_development_admission_checks_qualification_and_review(self):
        value = self.inputs.manifest
        value.update(execution_mode=R.DEVELOPMENT, experiment_id=S.DEVELOPMENT_ID)
        value = rehash(value)
        fake = SimpleNamespace(manifest=value, revalidate=lambda: None)
        reference = dict(
            summary_path=str(self.root / "public-summary.json"), synthetic_only=True
        )
        auth = R.candidate(fake, self.output, env(), reference)
        self.auth_path.write_bytes(R.canonical(auth))
        with (
            patch.object(R.public, "_output", side_effect=lambda x: Path(x)),
            patch.object(R, "oid", side_effect=lambda x: x),
            patch.object(R.core, "require_ancestor"),
            patch.object(
                R, "qualified_public", return_value=(reference, env(), lambda: None)
            ) as qualifier,
            patch.object(R, "reviewed_file") as reviewed,
            patch.object(R, "load_inputs", return_value=fake) as inputs,
            patch.object(R, "check_environment"),
        ):
            result = R.admit(
                R.DEVELOPMENT, self.auth_path, auth["deterministic_digest"], "f" * 40
            )
        self.assertEqual(result.auth, auth)
        qualifier.assert_called_once_with(reference["summary_path"], "f" * 40)
        inputs.assert_called_once_with(R.DEVELOPMENT)
        self.assertGreaterEqual(reviewed.call_count, 2)

    def test_run_consumes_before_search_and_claim_survives_failure(self):
        def search(*args):
            self.assertTrue(S.claim_path(self.auth).exists())
            self.assertTrue((self.output / "STARTED.json").exists())
            raise ValueError("stop synthetic search")

        with (
            patch.object(R, "admit", return_value=self.admitted),
            patch.object(self.admitted, "revalidate"),
            patch.object(R.public, "_output", side_effect=lambda x: Path(x)),
            patch.object(R, "record", side_effect=search),
            self.assertRaises(S.ExecutionFailure),
        ):
            R.run(R.PUBLIC, self.auth_path, self.auth["deterministic_digest"], "f" * 40)
        self.assertTrue(S.claim_path(self.auth).exists())

    def test_no_claim_or_search_after_failed_admission(self):
        with (
            patch.object(R, "admit", side_effect=ValueError("unadmitted")),
            patch.object(S, "consume") as consume,
            patch.object(R, "record") as record,
            self.assertRaises(ValueError),
        ):
            R.run(R.PUBLIC, self.auth_path, self.auth["deterministic_digest"], "f" * 40)
        consume.assert_not_called()
        record.assert_not_called()

    def test_decision_only_after_integrity_and_ordered_reduction(self):
        for mode in (R.PUBLIC, R.DEVELOPMENT):
            for passed in (False, True):
                stages = []
                with (
                    patch.object(
                        R,
                        "replay",
                        side_effect=lambda *a: (stages.append("replay"), ({}, {}))[1],
                    ),
                    patch.object(
                        R.public.analysis,
                        "reduce_matrix",
                        side_effect=lambda *a, **kw: (
                            stages.append("reduce"),
                            {"exact_success": {"screen_conjunction": passed}},
                        )[1],
                    ),
                ):
                    value = R.reduce_rows(
                        self.inputs, [], {**self.binding, "execution_mode": mode}
                    )
                self.assertEqual(stages, ["replay", "reduce"])
                expected = (
                    None
                    if mode == R.PUBLIC
                    else (
                        "DEVELOPMENT_SIGNAL_FOR_SEPARATE_CONFIRMATION_DESIGN"
                        if passed
                        else "STOP_REPAIR_NO_LOCKED_128_RUN"
                    )
                )
                self.assertEqual(value["scientific_decision"], expected)
                self.assertFalse(value["locked_128_evaluation_authorized"])
        with (
            patch.object(R, "replay", side_effect=ValueError("invalid")),
            patch.object(R.public.analysis, "reduce_matrix") as reduce,
            self.assertRaises(ValueError),
        ):
            R.reduce_rows(self.inputs, [], self.binding)
        reduce.assert_not_called()

    def test_analyzer_checks_storage_then_admission_then_claim_before_replay(self):
        self.binding = R.binding(
            self.admitted,
            S.consume(self.auth, "f" * 40, "f" * 40, R.core.FileSnapshot)[0],
        )
        S.publish(self.output, self.binding, self.action, lambda: None)
        S.claim_path(self.auth).unlink()
        with (
            patch.object(R.public, "_output", side_effect=lambda x: Path(x)),
            patch.object(R, "admit", return_value=self.admitted),
            patch.object(R, "reduce_rows") as replay,
            self.assertRaises(ValueError),
        ):
            R.analyze(R.PUBLIC, self.output)
        replay.assert_not_called()


class CliTests(unittest.TestCase):
    def test_exact_mode_arguments_and_no_retry_seed_provider_or_abbreviation(self):
        for args in (
            ("--run-development",),
            ("--self-test", "--output", "x"),
            ("--self-t",),
            ("--self-test", "--seed", "26090402"),
            ("--self-test", "--resume"),
            ("--self-test", "--provider", "openai"),
        ):
            result = subprocess.run(
                [sys.executable, "-P", "-B", str(ROOT / R.SCRIPT), *args],
                cwd="/tmp",
                env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
                capture_output=True,
            )
            self.assertEqual(result.returncode, 2, result.stderr)


if __name__ == "__main__":
    unittest.main()
