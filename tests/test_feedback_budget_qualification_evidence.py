"""Public qualification file and CLI boundaries with synthetic retained records.

Actual trace/replay semantics are exercised in test_feedback_budget_qualification.
These tests isolate publication and verification, without a clean-Git requirement.
"""

from __future__ import annotations

from contextlib import ExitStack, redirect_stderr
import copy
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/qualify_feedback_budget.py"
SPEC = importlib.util.spec_from_file_location("feedback_budget_evidence_tested", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
QUALIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(QUALIFY)

INVALID = (ValueError, TypeError, KeyError, OSError)


def rehash(value):
    return QUALIFY.core.with_digest(
        {key: item for key, item in value.items() if key != "deterministic_digest"}
    )


class PublicEvidenceBoundaries(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.temp = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.root = Path(self.temp).resolve()
        (self.root / "artifacts/work").mkdir(parents=True)
        self.output = self.root / "artifacts/work/public-qualification"
        self.stack.enter_context(patch.object(QUALIFY, "ROOT", self.root))
        self.source = QUALIFY.core.with_digest(
            {
                "schema_version": QUALIFY.DOMAIN + "/source",
                "qualification_revision": "a" * 40,
                "package_source": {"fixture": "synthetic source receipt"},
                "qualification_files": {"fixture": "synthetic Git binding"},
            }
        )
        self.runtime = QUALIFY.core.with_digest(
            {"fixture": "synthetic runtime receipt", "provider_calls": 0}
        )
        self.attest = self.stack.enter_context(
            patch.object(QUALIFY, "attest", return_value=self.source)
        )
        self.runtime_check = self.stack.enter_context(
            patch.object(QUALIFY, "runtime_receipt", return_value=self.runtime)
        )
        self.rows = [
            {**cell, "search_record": {"synthetic_public_record": index}}
            for index, cell in enumerate(QUALIFY.schedule())
        ]
        self.analysis = QUALIFY.core.with_digest(
            {
                "schema_version": QUALIFY.DOMAIN + "/analysis",
                "status": "PUBLIC_QUALIFICATION_PASS",
                "fixture": "synthetic analysis; not a replay assertion",
            }
        )

    def fake_run(self, on_record=None):
        for row in self.rows:
            if on_record is not None:
                on_record(copy.deepcopy(row))
        return copy.deepcopy(self.rows), copy.deepcopy(self.analysis)

    def create_evidence(self):
        with patch.object(QUALIFY, "run_matrix", side_effect=self.fake_run):
            return QUALIFY.qualify(self.output)

    def receipt(self):
        return QUALIFY.core.parse_canonical((self.output / "receipt.json").read_bytes())

    def replace_receipt(self, value):
        (self.output / "receipt.json").write_bytes(QUALIFY.canonical(rehash(value)))

    def test_qualification_retains_every_public_row_with_exact_file_binding(self):
        receipt = self.create_evidence()
        raw = (self.output / "records.jsonl").read_bytes()
        self.assertEqual(raw, b"".join(QUALIFY.canonical(row) for row in self.rows))
        self.assertEqual(receipt["records_byte_count"], len(raw))
        self.assertEqual(receipt["records_sha256"], QUALIFY.sha(raw))
        self.assertEqual(receipt["raw_trace_persisted_count"], 24)
        self.assertIs(receipt["development_execution_authorized"], False)
        self.assertEqual(
            {path.name for path in self.output.iterdir()},
            {"records.jsonl", "receipt.json"},
        )

    def test_partial_failure_retains_rows_and_never_writes_pass_receipt(self):
        def fail_after_three(on_record=None):
            for row in self.rows[:3]:
                on_record(row)
            raise QUALIFY.QualificationError("synthetic replay failure")

        with (
            patch.object(QUALIFY, "run_matrix", side_effect=fail_after_three),
            self.assertRaisesRegex(QUALIFY.QualificationError, "synthetic replay"),
        ):
            QUALIFY.qualify(self.output)
        self.assertEqual(
            (self.output / "records.jsonl").read_bytes(),
            b"".join(QUALIFY.canonical(row) for row in self.rows[:3]),
        )
        failure = QUALIFY.core.parse_canonical(
            (self.output / "failure.json").read_bytes()
        )
        self.assertEqual(failure["status"], "INVALID_PUBLIC_QUALIFICATION")
        self.assertEqual(failure["error_type"], "QualificationError")
        self.assertIs(failure["development_execution_authorized"], False)
        self.assertFalse((self.output / "receipt.json").exists())
        with self.assertRaises(INVALID):
            QUALIFY.verify(self.output)

    def test_existing_destination_is_refused_before_search_and_preserved(self):
        self.output.mkdir()
        marker = self.output / "existing.txt"
        marker.write_bytes(b"existing user evidence\n")
        with (
            patch.object(QUALIFY, "run_matrix") as run,
            self.assertRaises(INVALID),
        ):
            QUALIFY.qualify(self.output)
        run.assert_not_called()
        self.assertEqual(marker.read_bytes(), b"existing user evidence\n")
        self.assertEqual(list(self.output.iterdir()), [marker])

    def test_output_outside_fixed_parent_is_refused_before_search(self):
        for output in (self.root / "other", self.root / "artifacts/work/deeper/output"):
            with self.subTest(output=output):
                with (
                    patch.object(QUALIFY, "run_matrix") as run,
                    self.assertRaises(INVALID),
                ):
                    QUALIFY.qualify(output)
                run.assert_not_called()
                self.assertFalse(output.exists())

    def test_symlink_destination_does_not_write_into_target(self):
        target = self.root / "untouched"
        target.mkdir()
        self.output.symlink_to(target, target_is_directory=True)
        with (
            patch.object(QUALIFY, "run_matrix") as run,
            self.assertRaises(INVALID),
        ):
            QUALIFY.qualify(self.output)
        run.assert_not_called()
        self.assertEqual(list(target.iterdir()), [])

    def test_source_failure_precedes_destination_creation_and_search(self):
        self.attest.side_effect = QUALIFY.QualificationError("source bytes changed")
        with (
            patch.object(QUALIFY, "run_matrix") as run,
            self.assertRaisesRegex(QUALIFY.QualificationError, "source bytes"),
        ):
            QUALIFY.qualify(self.output)
        run.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_source_change_after_execution_retains_failed_evidence(self):
        changed = copy.deepcopy(self.source)
        changed["qualification_revision"] = "b" * 40
        self.attest.side_effect = [self.source, rehash(changed)]
        with (
            patch.object(QUALIFY, "run_matrix", side_effect=self.fake_run),
            self.assertRaisesRegex(QUALIFY.QualificationError, "source or runtime"),
        ):
            QUALIFY.qualify(self.output)
        self.assertTrue((self.output / "records.jsonl").is_file())
        self.assertTrue((self.output / "failure.json").is_file())
        self.assertFalse((self.output / "receipt.json").exists())

    def test_runtime_change_after_execution_retains_failed_evidence(self):
        changed = copy.deepcopy(self.runtime)
        changed["fixture"] = "changed runtime behavior"
        self.runtime_check.side_effect = [self.runtime, rehash(changed)]
        with (
            patch.object(QUALIFY, "run_matrix", side_effect=self.fake_run),
            self.assertRaisesRegex(QUALIFY.QualificationError, "source or runtime"),
        ):
            QUALIFY.qualify(self.output)
        self.assertTrue((self.output / "records.jsonl").is_file())
        self.assertTrue((self.output / "failure.json").is_file())
        self.assertFalse((self.output / "receipt.json").exists())

    def test_verify_recomputes_receipt_from_retained_rows(self):
        expected = self.create_evidence()
        with patch.object(
            QUALIFY, "analyze_matrix", return_value=self.analysis
        ) as analyze:
            verified = QUALIFY.verify(self.output)
        self.assertEqual(verified, expected)
        analyze.assert_called_once_with(self.rows)
        self.attest.assert_called_with(self.root, self.source["qualification_revision"])

    def test_rehashed_receipt_mutations_fail_full_recomputation(self):
        original = self.create_evidence()
        mutations = (
            ("status", "SOME_OTHER_PASS"),
            ("records_file", "other.jsonl"),
            ("raw_trace_persisted_count", 23),
            ("anchor_raw_trace_persisted_count", 8),
            ("development_execution_authorized", True),
            ("extra_authority", "run development"),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                changed = copy.deepcopy(original)
                changed[field] = value
                self.replace_receipt(changed)
                with (
                    patch.object(QUALIFY, "analyze_matrix", return_value=self.analysis),
                    self.assertRaises(INVALID),
                ):
                    QUALIFY.verify(self.output)

    def test_rehashed_analysis_claim_is_not_independent_evidence(self):
        receipt = self.create_evidence()
        receipt["analysis"]["status"] = "MADE_UP_QUALIFICATION_PASS"
        receipt["analysis"] = rehash(receipt["analysis"])
        self.replace_receipt(receipt)
        with (
            patch.object(QUALIFY, "analyze_matrix", return_value=self.analysis),
            self.assertRaisesRegex(QUALIFY.QualificationError, "recomputed public"),
        ):
            QUALIFY.verify(self.output)

    def test_rehashed_source_receipt_fails_before_analysis(self):
        receipt = self.create_evidence()
        receipt["source"]["package_source"]["fixture"] = "foreign source bytes"
        receipt["source"] = rehash(receipt["source"])
        self.replace_receipt(receipt)
        with (
            patch.object(QUALIFY, "analyze_matrix") as analyze,
            self.assertRaisesRegex(QUALIFY.QualificationError, "source receipt"),
        ):
            QUALIFY.verify(self.output)
        analyze.assert_not_called()

    def test_rehashed_runtime_receipt_fails_before_analysis(self):
        receipt = self.create_evidence()
        receipt["runtime"]["fixture"] = "unqualified numerical runtime"
        receipt["runtime"] = rehash(receipt["runtime"])
        self.replace_receipt(receipt)
        with (
            patch.object(QUALIFY, "analyze_matrix") as analyze,
            self.assertRaisesRegex(QUALIFY.QualificationError, "runtime receipt"),
        ):
            QUALIFY.verify(self.output)
        analyze.assert_not_called()

    def test_changed_record_bytes_fail_before_analysis(self):
        self.create_evidence()
        path = self.output / "records.jsonl"
        path.write_bytes(path.read_bytes() + QUALIFY.canonical({"extra": "row"}))
        with (
            patch.object(QUALIFY, "analyze_matrix") as analyze,
            self.assertRaisesRegex(QUALIFY.QualificationError, "raw records digest"),
        ):
            QUALIFY.verify(self.output)
        analyze.assert_not_called()

    def test_evidence_mutation_during_analysis_fails_snapshot_revalidation(self):
        self.create_evidence()

        def mutate_during_analysis(rows):
            self.assertEqual(rows, self.rows)
            path = self.output / "records.jsonl"
            path.write_bytes(path.read_bytes() + b"\n")
            return self.analysis

        with (
            patch.object(QUALIFY, "analyze_matrix", side_effect=mutate_during_analysis),
            self.assertRaises(INVALID),
        ):
            QUALIFY.verify(self.output)

    def test_foreign_receipt_domain_fails_before_source_or_analysis(self):
        receipt = self.create_evidence()
        receipt["schema_version"] = "foreign-development-run/v1"
        self.replace_receipt(receipt)
        self.attest.reset_mock()
        with (
            patch.object(QUALIFY, "analyze_matrix") as analyze,
            self.assertRaisesRegex(QUALIFY.QualificationError, "public receipt domain"),
        ):
            QUALIFY.verify(self.output)
        self.attest.assert_not_called()
        analyze.assert_not_called()

    def test_failure_or_extra_file_invalidates_evidence_closure_before_analysis(self):
        self.create_evidence()
        for name in ("failure.json", "unclaimed-record.jsonl"):
            with self.subTest(name=name):
                path = self.output / name
                path.write_bytes(b"{}\n")
                with (
                    patch.object(QUALIFY, "analyze_matrix") as analyze,
                    self.assertRaisesRegex(QUALIFY.QualificationError, "file closure"),
                ):
                    QUALIFY.verify(self.output)
                analyze.assert_not_called()
                path.unlink()

    def test_symlinked_evidence_file_is_not_read_as_valid_evidence(self):
        self.create_evidence()
        original = self.output / "records.jsonl"
        other = self.root / "copied-records.jsonl"
        other.write_bytes(original.read_bytes())
        original.unlink()
        original.symlink_to(other)
        with (
            patch.object(QUALIFY, "analyze_matrix") as analyze,
            self.assertRaises(INVALID),
        ):
            QUALIFY.verify(self.output)
        analyze.assert_not_called()


class PublicQualificationCliBoundary(unittest.TestCase):
    def test_cli_has_no_task_seed_budget_or_provider_input_controls(self):
        for extra in (
            ("--task", "foreign-task.json"),
            ("--seed", "42"),
            ("--budget", "1024"),
            ("--scale", "32"),
            ("--cohort", "development.json"),
            ("--authorization", "old-authorization.json"),
            ("--model", "remote-provider"),
        ):
            with self.subTest(extra=extra):
                with (
                    patch.object(sys, "argv", [str(SCRIPT), "--manifest", *extra]),
                    patch.object(QUALIFY, "public_manifest") as manifest,
                    patch.object(QUALIFY, "qualify") as qualify,
                    patch.object(QUALIFY, "verify") as verify,
                    redirect_stderr(io.StringIO()),
                    self.assertRaises(SystemExit) as stopped,
                ):
                    QUALIFY.main()
                self.assertEqual(stopped.exception.code, 2)
                manifest.assert_not_called()
                qualify.assert_not_called()
                verify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
