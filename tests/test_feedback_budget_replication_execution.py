"""Connector boundary/fault tests. Mock admission is NOT cohort qualification."""

from __future__ import annotations

import copy
import ast
import importlib.util
import io
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
    "feedback_budget_replication_execution_tested",
    ROOT / "scripts/run_feedback_budget_replication_execution.py",
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
        cls.cells = cls.inputs.cells

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
        cell = self.cells[index]
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
                execution_mode=R.PUBLIC,
                synthetic_only=True,
            )
        )

    def action(self, emit):
        for index in range(1024):
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
        self.assertEqual(len({c["cell_id"] for c in inputs.cells}), 1024)
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
            ("cell_index", 1024),
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
                    R.REPLICATION,
                    self.auth_path,
                    value["deterministic_digest"],
                    "f" * 40,
                )
            environment.assert_not_called()
            inputs.assert_not_called()
        with self.assertRaisesRegex(ValueError, "digest"):
            R.auth_shape(R.canonical(self.auth), R.PUBLIC, "0" * 64)

    def test_all_final_identities_close_before_any_replay_or_reduction(self):
        rows = [self.row(i, identity=True) for i in range(1024)]
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
                patch.object(R.analysis, "reduce_matrix") as reduce,
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
                "execution_mode": R.REPLICATION,
                "experiment_id": S.REPLICATION_ID,
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
                R.REPLICATION, self.auth_path, value["deterministic_digest"], "f" * 40
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

    def test_synthetic_replication_projection_only_via_seal_loader(self):
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
            value = R.load_inputs(R.REPLICATION)
        loader.assert_called_once_with(R.admission.COHORT_PATH)
        self.assertEqual(value.manifest["cohort_seal"]["seal_digest"], "b" * 64)
        self.assertFalse(value.manifest["replication_execution_authorized"])

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
                replication_cells_executed=0,
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
        replication = {**self.auth, "execution_mode": R.REPLICATION}
        changed = rehash(
            {
                **replication,
                "output_path": str(self.root / "other"),
                "input_manifest_digest": "1" * 64,
            }
        )
        self.assertEqual(S.claim_path(replication), S.claim_path(changed))
        self.assertNotEqual(
            S.claim_path(self.auth),
            S.claim_path(rehash({**self.auth, "output_path": "other"})),
        )
        self.auth = replication
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

    def test_1027_file_closure_and_claim_linkage(self):
        self.consume()
        result = S.publish(self.output, self.binding, self.action, lambda: None)
        inspection = S.inspect(self.output)
        self.assertEqual(len(list(self.output.iterdir())), 1027)
        self.assertEqual(inspection.commit, result)
        self.assertEqual(inspection.rows, [self.row(i) for i in range(1024)])
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
            {"STARTED.json", "cell-0000.json", "FAILURE.json"},
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
        cell = self.output / "cell-1023.json"
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
            ("replication_execution_authorized", True),
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
    def test_completed_run_stdout_failure_preserves_consumed_lifecycle(self):
        stderr = io.StringIO()
        stdout = SimpleNamespace(
            write=lambda value: (_ for _ in ()).throw(BrokenPipeError("closed stdout")),
            flush=lambda: None,
        )

        def record(inputs, cell, binding):
            return rehash(
                {
                    **self.row(cell["cell_index"]),
                    "run_binding_digest": binding["deterministic_digest"],
                }
            )

        def reduce(inputs, rows, binding):
            return rehash(
                {
                    **self.receipt(),
                    "run_binding_digest": binding["deterministic_digest"],
                }
            )

        argv = [
            R.SCRIPT,
            "--run-public",
            "--authorization",
            str(self.auth_path),
            "--confirm-digest",
            self.auth["deterministic_digest"],
            "--reviewed-revision",
            "f" * 40,
        ]
        with (
            patch.object(sys, "argv", argv),
            patch.object(sys, "stdout", stdout),
            patch.object(sys, "stderr", stderr),
            patch.object(R, "admit", return_value=self.admitted),
            patch.object(self.admitted, "revalidate"),
            patch.object(R.public, "_output", side_effect=lambda x: Path(x)),
            patch.object(R, "record", side_effect=record),
            patch.object(R, "reduce_rows", side_effect=reduce),
        ):
            code = R.main()
        result = R.core.parse_canonical(
            (stderr.getvalue().splitlines()[-1] + "\n").encode()
        )
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "RESULT_DELIVERY_UNCERTAIN")
        self.assertTrue(result["authorization_consumed"])
        self.assertEqual(len(S.inspect(self.output).rows), 1024)
        with (
            patch.object(R, "admit") as admit,
            self.assertRaises(S.ExecutionFailure) as raised,
        ):
            R.run(R.PUBLIC, self.auth_path, self.auth["deterministic_digest"], "f" * 40)
        admit.assert_not_called()
        self.assertEqual(raised.exception.status, "AUTHORIZATION_ALREADY_SPENT")

    def test_uncertain_summary_publication_is_not_invalid_science(self):
        stderr = io.StringIO()
        summary = self.root / "uncertain-summary.json"

        def uncertain(*args):
            calls = []

            def check():
                calls.append(1)
                if len(calls) == 2:
                    raise ValueError("post-write revalidation")

            return S.base._publish_summary(summary, {"synthetic_only": True}, check)

        argv = [
            R.SCRIPT,
            "--analyze-public",
            "--output",
            str(self.output),
            "--summary",
            str(summary),
        ]
        with (
            patch.object(sys, "argv", argv),
            patch.object(sys, "stderr", stderr),
            patch.object(R, "analyze_and_save", side_effect=uncertain),
        ):
            code = R.main()
        result = R.core.parse_canonical(
            (stderr.getvalue().splitlines()[-1] + "\n").encode()
        )
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "PUBLICATION_UNCERTAIN")
        self.assertIsNone(result["scientific_decision"])
        self.assertTrue(summary.exists())

    def test_uncertain_candidate_and_ledger_initialization_keep_uncertainty(self):
        stderr = io.StringIO()
        argv = [
            R.SCRIPT,
            "--prepare-public",
            "--output",
            str(self.output),
            "--authorization",
            str(self.auth_path),
        ]
        with (
            patch.object(sys, "argv", argv),
            patch.object(sys, "stderr", stderr),
            patch.object(
                R,
                "prepare",
                side_effect=S.base.PublicationUncertain("candidate retained"),
            ),
        ):
            self.assertEqual(R.main(), 1)
        result = R.core.parse_canonical(
            (stderr.getvalue().splitlines()[-1] + "\n").encode()
        )
        self.assertEqual(result["status"], "PUBLICATION_UNCERTAIN")
        with (
            patch.object(
                S.base.storage,
                "_create_directory",
                side_effect=S.base.PublicationUncertain("ledger retained"),
            ),
            self.assertRaises(S.ExecutionFailure) as raised,
        ):
            S.consume(self.auth, "f" * 40, "f" * 40, R.core.FileSnapshot)
        self.assertEqual(raised.exception.status, "CONSUMPTION_UNCERTAIN")
        self.assertIsNone(raised.exception.authorization_consumed)

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
                "replication_cells_executed": 0,
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

    def test_synthetic_replication_admission_checks_qualification_and_review(self):
        value = self.inputs.manifest
        value.update(execution_mode=R.REPLICATION, experiment_id=S.REPLICATION_ID)
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
                R.REPLICATION, self.auth_path, auth["deterministic_digest"], "f" * 40
            )
        self.assertEqual(result.auth, auth)
        qualifier.assert_called_once_with(reference["summary_path"], "f" * 40)
        inputs.assert_called_once_with(R.REPLICATION)
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
        for mode in (R.PUBLIC, R.REPLICATION):
            for passed in (False, True):
                stages = []
                with (
                    patch.object(
                        R,
                        "replay",
                        side_effect=lambda *a: (stages.append("replay"), ({}, {}))[1],
                    ),
                    patch.object(
                        R.analysis,
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
                        "SOURCE_DISJOINT_REPLICATION_SCREEN_PASS"
                        if passed
                        else "STOP_REPAIR_REPLICATION_SCREEN_NOT_MET"
                    )
                )
                self.assertEqual(value["scientific_decision"], expected)
                self.assertFalse(value["locked_128_evaluation_authorized"])
        with (
            patch.object(R, "replay", side_effect=ValueError("invalid")),
            patch.object(R.analysis, "reduce_matrix") as reduce,
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


class NewDomainGuards(Setup):
    def test_descriptor_gate_precedes_baseline_admission_consumption_and_search(self):
        with (
            patch.object(S.base.resource, "getrlimit", return_value=(256, 256)),
            patch.object(R, "admit") as admit,
            patch.object(R, "environment") as environment,
            patch.object(S, "consume") as consume,
            patch.object(R, "record") as record,
            self.assertRaisesRegex(ValueError, "1152"),
        ):
            R.run(R.PUBLIC, self.auth_path, self.auth["deterministic_digest"], "f" * 40)
        for call in (admit, environment, consume, record):
            call.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_prepare_descriptor_gate_precedes_environment_or_candidate_creation(self):
        destination = self.root / "unused-candidate.json"
        with (
            patch.object(S.base.resource, "getrlimit", return_value=(256, 256)),
            patch.object(R.public, "_output", side_effect=lambda p: Path(p)),
            patch.object(R, "environment") as environment,
            patch.object(R, "load_inputs") as inputs,
            self.assertRaisesRegex(ValueError, "1152"),
        ):
            R.prepare(R.PUBLIC, self.output, destination)
        environment.assert_not_called()
        inputs.assert_not_called()
        self.assertFalse(destination.exists())

    def test_summary_and_candidate_snapshots_share_the_64MiB_bound(self):
        with patch.object(R.core.FileSnapshot, "capture") as capture:
            R.snapshot_file(self.auth_path)
        capture.assert_called_once_with(self.auth_path, byte_cap=64 << 20)
        self.assertEqual(len(S.base.CELL_NAMES), 1024)
        self.assertEqual(S.base.CELL_NAMES[-1], "cell-1023.json")
        self.assertEqual(S.base.MAX_TOTAL_BYTES, 1 << 30)

    def test_pure_analysis_matches_qualified_v7_algebra_except_domain_and_docstring(
        self,
    ):
        def body(path):
            tree = ast.parse(path.read_text())
            return [
                ast.dump(node)
                for node in tree.body[1:]
                if not (
                    isinstance(node, ast.Assign)
                    and any(
                        isinstance(target, ast.Name) and target.id == "DOMAIN"
                        for target in node.targets
                    )
                )
            ]

        self.assertEqual(
            body(ROOT / "scripts/feedback_budget_replication_analysis.py"),
            body(ROOT / R.ANALYSIS),
        )
        self.assertNotEqual(R.analysis.DOMAIN, R.public.analysis.DOMAIN)

    def test_all_public_scientific_identities_equal_the_previous_1024_path(self):
        previous = R.k.public_inputs()
        for left, right in zip(self.inputs.cells, previous.cells):
            a = R.q.build_search_run_identity(**self.inputs.arguments(left))
            b = R.q.build_search_run_identity(**previous.arguments(right))
            self.assertEqual(R.canonical(a), R.canonical(b))
            self.assertNotEqual(left["cell_id"], right["cell_id"])

    def test_previous_public_and_v6_connector_receipts_are_not_new_qualification(self):
        for path in (
            R.admission.PUBLIC_SUMMARY,
            "docs/qualifications/countdown_feedback_budget_v6_connector_20260910.summary.json",
        ):
            with (
                self.subTest(path=path),
                patch.object(R, "analyze") as analyze,
                self.assertRaises(ValueError),
            ):
                R.qualified_public(ROOT / path)
            analyze.assert_not_called()

    def test_changed_replication_candidate_does_not_replenish_a_spent_study(self):
        value = self.inputs.manifest
        value.update(execution_mode=R.REPLICATION, experiment_id=S.REPLICATION_ID)
        fake = SimpleNamespace(manifest=rehash(value))
        first = R.candidate(fake, self.output, env(), {"synthetic_only": True})
        S.consume(first, "f" * 40, "f" * 40, R.core.FileSnapshot)
        changed = R.candidate(
            fake, self.root / "different-output", env(), {"synthetic_only": True}
        )
        self.auth_path.write_bytes(R.canonical(changed))
        with (
            patch.object(R, "admit") as admit,
            patch.object(R, "qualified_public") as qualifier,
            patch.object(R, "load_inputs") as inputs,
            self.assertRaises(S.ExecutionFailure) as raised,
        ):
            R.run(
                R.REPLICATION, self.auth_path, changed["deterministic_digest"], "f" * 40
            )
        self.assertEqual(raised.exception.status, "AUTHORIZATION_ALREADY_SPENT")
        for call in (admit, qualifier, inputs):
            call.assert_not_called()


class CliTests(unittest.TestCase):
    def test_exact_mode_arguments_and_no_retry_seed_provider_or_abbreviation(self):
        for args in (
            ("--run-replication",),
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
