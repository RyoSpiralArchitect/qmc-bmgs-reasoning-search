"""Synthetic wrapper boundaries; mocked dispatch is NOT production evidence.

Saved metadata supplies fixed byte fixtures only. Runtime admission, consumption
and generation are forbidden except for explicit synthetic dispatcher mocks.
"""

from __future__ import annotations

from contextlib import ExitStack
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "receiver_replication_entrypoint_tested",
    ROOT / "scripts/run_feedback_budget_receiver_replication.py",
)
assert SPEC is not None and SPEC.loader is not None
E = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = E
SPEC.loader.exec_module(E)
P, C, R, S, B = E.P, E.C, E.R, E.S, E.B
REVISION, REVIEW = "f" * 40, "e" * 40


def rehash(value):
    return E.digested(B.without_digest(value))


def snapshot(path, raw):
    return SimpleNamespace(path=Path(path), raw=raw, revalidate=Mock())


def fixture():
    auth_raw = C.authorization_for(S.REPLICATION).read_bytes()
    auth = E.parse(auth_raw)
    verified_raw = (ROOT / E.VERIFICATION).read_bytes()
    verified = E.parse(verified_raw)
    preparer, coordinator = verified["operator_source"], auth["coordinator_source"]
    items = {
        ROOT / name: snapshot(ROOT / name, b"synthetic source: " + name.encode())
        for name in E.SOURCE_FILES
    }
    source = E.digested(
        dict(
            implementation_revision=REVISION,
            fixture="synthetic, not source qualification",
            files={
                str(path.relative_to(ROOT)): dict(
                    byte_count=len(item.raw), sha256=E.sha(item.raw)
                )
                for path, item in items.items()
            },
        )
    )
    for receipt in (preparer, coordinator):
        for name in receipt["files"]:
            items[ROOT / name] = snapshot(ROOT / name, (ROOT / name).read_bytes())
    for path, raw in (
        (P.RAW_AUTH, auth_raw),
        (C.authorization_for(S.REPLICATION), auth_raw),
        (ROOT / P.PREPARATION_MIRROR, (ROOT / P.PREPARATION_MIRROR).read_bytes()),
        (ROOT / E.VERIFICATION, verified_raw),
        (ROOT / E.PREFLIGHT, E.canonical(E.preflight_receipt(source))),
    ):
        items[path] = snapshot(path, raw)
    return SimpleNamespace(
        auth=auth,
        source=source,
        preparer=preparer,
        coordinator=coordinator,
        items=items,
        public=(snapshot(ROOT / "synthetic-public", b"{}\n"),),
    )


class EntrypointBoundaries(unittest.TestCase):
    def patches(self, f, *, head=REVIEW):
        stack = ExitStack()
        self.addCleanup(stack.close)
        for target, name, options in (
            (E, "attest", {"return_value": f.source}),
            (P, "attest", {"return_value": f.preparer}),
            (C, "attest", {"return_value": f.coordinator}),
            (E.core, "git_head", {"return_value": head}),
            (E.core, "require_ancestor", {}),
            (R, "oid", {"side_effect": lambda value: value}),
            (R, "snapshot_file", {"side_effect": lambda path: f.items[Path(path)]}),
            (R, "reviewed_file", {}),
            (P, "public_snapshots", {"return_value": f.public}),
            (S, "parent_binding", {"return_value": f.auth["output_parent"]}),
            (S, "descriptor_preflight", {}),
            (C, "unused", {}),
            (C, "admit", {"side_effect": AssertionError("no real admission")}),
            (
                C,
                "qualified_public",
                {"side_effect": AssertionError("no new qualification")},
            ),
            (
                C,
                "receiver_admit",
                {"side_effect": AssertionError("no sealed admission")},
            ),
            (S, "consume", {"side_effect": AssertionError("must not consume")}),
            (R, "record", {"side_effect": AssertionError("must not search")}),
            (C, "run", {"side_effect": AssertionError("must not run")}),
            (
                C,
                "analyze_and_save",
                {"side_effect": AssertionError("must not analyze")},
            ),
            (C, "verify", {"side_effect": AssertionError("must not verify")}),
        ):
            stack.enter_context(patch.object(target, name, **options))

    def no_effects(self):
        for operation in (
            C.admit,
            C.qualified_public,
            C.receiver_admit,
            S.consume,
            R.record,
            C.run,
            C.analyze_and_save,
            C.verify,
        ):
            operation.assert_not_called()

    def invoke(self, mode="run", confirmed=E.CANDIDATE_DIGEST, state=None):
        if state is None:
            state = dict(run_entered=False, run_returned=False)
        return E.dispatch(mode, REVISION, REVIEW, confirmed, Mock(), state)

    def cli(self, arguments, *, sink=None, expect_failure=False):
        sink = sink or io.BytesIO()
        with (
            patch.object(sys, "argv", [E.SCRIPT, *arguments]),
            patch.object(sys, "stdout", SimpleNamespace(buffer=sink)),
            patch.object(sys, "stderr", io.StringIO()),
        ):
            if expect_failure:
                with self.assertRaises(SystemExit) as raised:
                    E.main()
                self.assertNotEqual(raised.exception.code, 0)
            else:
                E.main()
        return sink.getvalue()

    def run_args(self):
        return [
            "--run",
            "--implementation-revision",
            REVISION,
            "--reviewed-revision",
            REVIEW,
            "--confirm-digest",
            E.CANDIDATE_DIGEST,
        ]

    def allow_mock_run(self):
        C.run.side_effect = None
        C.run.return_value = E.digested(
            dict(fixture="synthetic commit; never a real run")
        )

    def summary(self, **changes):
        return E.digested(
            dict(
                authorization_digest=E.CANDIDATE_DIGEST,
                execution_mode=S.REPLICATION,
                production_adapter_executed=True,
                replication_cells_executed=1024,
                source_multiset_count=64,
                scientific_decision="SYNTHETIC_ONLY",
                **changes,
            )
        )

    def test_exact_identity_and_static_self_test_no_authority(self):
        self.assertEqual(E.SOURCE_FILES, (E.SCRIPT, E.TEST, E.POLICY))
        self.assertEqual(C.output_for(S.REPLICATION), B.OUTPUT)
        self.assertNotEqual(C.authorization_for(S.REPLICATION), ROOT / B.CANDIDATE)
        result = E.self_test()
        self.assertFalse(result["replication_execution_authorized"])
        self.assertEqual(result["replication_search_calls"], 0)

    def test_confirmation_requires_literal_exact_digest(self):
        E.confirm(E.CANDIDATE_DIGEST)
        for value in (
            None,
            True,
            1,
            "",
            E.CANDIDATE_DIGEST.upper(),
            E.CANDIDATE_DIGEST[:16],
            " " + E.CANDIDATE_DIGEST,
            "0" * 64,
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                E.confirm(value)

    def test_revision_rejects_alias_short_upper_or_non_string(self):
        for value in (None, True, "HEAD", "main", "f" * 7, "F" * 40, "f" * 41):
            with (
                self.subTest(value=value),
                patch.object(R, "oid") as resolve,
                self.assertRaises(ValueError),
            ):
                E.oid(value)
            resolve.assert_not_called()

    def test_context_authenticates_exact_metadata_without_runtime_effects(self):
        f = fixture()
        self.patches(f)
        ctx = E.context(REVISION, REVIEW)
        self.assertEqual(ctx.auth, f.auth)
        self.assertEqual(ctx.reviewed, REVIEW)
        for name in E.SOURCE_FILES:
            R.reviewed_file.assert_any_call(f.items[ROOT / name], REVISION)
            R.reviewed_file.assert_any_call(f.items[ROOT / name], REVIEW)
        R.reviewed_file.assert_any_call(f.items[ROOT / E.PREFLIGHT], REVIEW)
        self.no_effects()

    def test_preflight_metadata_only_at_frozen_head(self):
        f = fixture()
        self.patches(f, head=REVISION)
        result = E.preflight(REVISION)
        self.assertEqual(result, E.preflight_receipt(f.source))
        self.assertFalse(result["fresh_production_admission_performed"])
        self.assertFalse(result["production_dispatch_exercised"])
        self.assertFalse(result["replication_execution_authorized"])
        self.assertEqual(result["replication_search_calls"], 0)
        self.assertEqual(C.unused.call_count, 2)
        self.no_effects()

    def test_preflight_rejects_later_head(self):
        self.patches(fixture())
        with self.assertRaisesRegex(ValueError, "implementation HEAD"):
            E.preflight(REVISION)
        self.no_effects()

    def test_reviewed_check_is_not_consent_or_fresh_admission(self):
        self.patches(fixture())
        result = E.check_reviewed(REVISION, REVIEW)
        self.assertEqual(result["entrypoint_review_revision"], REVIEW)
        self.assertFalse(result["replication_execution_authorized"])
        self.assertFalse(result["fresh_production_admission_performed"])
        self.no_effects()

    def test_check_and_dispatch_require_review_even_when_called_directly(self):
        self.patches(fixture())
        with self.assertRaises(ValueError):
            E.check_reviewed(REVISION, None)
        with self.assertRaises(ValueError):
            E.dispatch("run", REVISION, None, E.CANDIDATE_DIGEST, Mock(), {})
        E.attest.assert_not_called()
        self.no_effects()

    def test_occupied_claim_stops_before_metadata_and_dispatch(self):
        self.patches(fixture())
        C.unused.side_effect = S.ExecutionFailure(
            "AUTHORIZATION_ALREADY_SPENT", True, "occupied"
        )
        for operation in (
            lambda: E.preflight(REVISION),
            lambda: E.check_reviewed(REVISION, REVIEW),
            self.invoke,
        ):
            with self.assertRaises(S.ExecutionFailure):
                operation()
        E.attest.assert_not_called()
        self.no_effects()

    def test_dangling_original_output_is_occupied(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "output"
            path.symlink_to(Path(directory) / "missing")
            with (
                patch.object(B, "OUTPUT", path),
                patch.object(E, "context") as ctx,
                self.assertRaises(ValueError),
            ):
                E.preflight(REVISION)
            ctx.assert_not_called()
            self.assertTrue(path.is_symlink())

    def test_raw_promoted_candidate_mismatch_rejected(self):
        f = fixture()
        self.patches(f)
        f.items[P.RAW_AUTH].raw += b" "
        with self.assertRaisesRegex(ValueError, "raw/promoted"):
            E.context(REVISION, REVIEW)
        self.no_effects()

    def test_both_candidates_replaced_rejected_by_pinned_hash(self):
        f = fixture()
        self.patches(f)
        for path in (P.RAW_AUTH, C.authorization_for(S.REPLICATION)):
            f.items[path].raw += b" "
        with self.assertRaisesRegex(ValueError, "raw/promoted"):
            E.context(REVISION, REVIEW)

    def test_wrong_candidate_digest_rejected(self):
        self.patches(fixture())
        with (
            patch.object(E, "CANDIDATE_DIGEST", "0" * 64),
            self.assertRaisesRegex(ValueError, "fixed candidate"),
        ):
            E.context(REVISION, REVIEW)

    def test_wrong_preparer_or_coordinator_source_rejected(self):
        f = fixture()
        self.patches(f)
        for attestor, original, label in (
            (P.attest, f.preparer, "preparer"),
            (C.attest, f.coordinator, "coordinator"),
        ):
            with self.subTest(label=label):
                attestor.return_value = {**original, "deterministic_digest": "0" * 64}
                with self.assertRaisesRegex(ValueError, label):
                    E.context(REVISION, REVIEW)
                attestor.return_value = original

    def test_source_receipt_byte_count_and_hash_enforced(self):
        f = fixture()
        self.patches(f)
        for name in (E.SCRIPT, P.SCRIPT, C.SCRIPT):
            item = f.items[ROOT / name]
            old = item.raw
            with self.subTest(name=name):
                item.raw = old + b" "
                with self.assertRaisesRegex(ValueError, "source receipt bytes"):
                    E.context(REVISION, REVIEW)
                item.raw = old

    def test_preparation_receipt_must_match_exact_original_bytes(self):
        f = fixture()
        self.patches(f)
        f.items[ROOT / P.PREPARATION_MIRROR].raw += b" "
        with self.assertRaisesRegex(ValueError, "preparation receipt"):
            E.context(REVISION, REVIEW)

    def test_verification_must_be_exact_prior_admission_evidence(self):
        f = fixture()
        self.patches(f)
        item = f.items[ROOT / E.VERIFICATION]
        original = E.parse(item.raw)
        for key, value in (
            ("production_admission_verified", False),
            ("production_adapter_executed", True),
            ("replication_execution_authorized", True),
            ("reviewed_revision", REVISION),
            ("authorization_digest", "0" * 64),
            ("preparation_digest", "0" * 64),
        ):
            with self.subTest(key=key):
                item.raw = E.canonical(rehash({**original, key: value}))
                with self.assertRaisesRegex(ValueError, "prior candidate admission"):
                    E.context(REVISION, REVIEW)

    def test_unreviewed_files_rejected(self):
        self.patches(fixture())
        R.reviewed_file.side_effect = ValueError("not reviewed")
        with self.assertRaisesRegex(ValueError, "not reviewed"):
            E.context(REVISION, REVIEW)
        self.no_effects()

    def test_source_revision_ancestry_checked(self):
        self.patches(fixture())
        E.context(REVISION, REVIEW)
        E.core.require_ancestor.assert_any_call(ROOT, REVISION, REVIEW)
        E.core.require_ancestor.assert_any_call(ROOT, REVIEW, REVIEW)

    def test_missing_or_replaced_reviewed_preflight_rejected(self):
        f = fixture()
        self.patches(f)
        item = f.items.pop(ROOT / E.PREFLIGHT)
        with self.assertRaises(KeyError):
            E.context(REVISION, REVIEW)
        f.items[item.path] = item
        item.raw += b" "
        with self.assertRaisesRegex(ValueError, "preflight differs"):
            E.context(REVISION, REVIEW)

    def test_public_evidence_failure_stops_before_dispatch(self):
        self.patches(fixture())
        P.public_snapshots.side_effect = ValueError("PUBLIC bytes changed")
        with self.assertRaisesRegex(ValueError, "PUBLIC bytes"):
            self.invoke()
        self.no_effects()

    def test_context_snapshot_change_rejected(self):
        f = fixture()
        self.patches(f)
        f.items[P.RAW_AUTH].revalidate.side_effect = ValueError("snapshot changed")
        with self.assertRaisesRegex(ValueError, "snapshot changed"):
            E.context(REVISION, REVIEW)

    def test_context_revalidation_rejects_changed_parent(self):
        self.patches(fixture())
        ctx = E.context(REVISION, REVIEW)
        S.parent_binding.return_value = {"different": True}
        with self.assertRaisesRegex(ValueError, "output parent"):
            ctx.revalidate()

    def test_context_revalidation_rejects_head_drift(self):
        self.patches(fixture())
        ctx = E.context(REVISION, REVIEW)
        E.core.git_head.return_value = REVISION
        with self.assertRaisesRegex(ValueError, "HEAD changed"):
            ctx.revalidate()

    def test_context_full_revalidation_rejects_each_source_drift(self):
        f = fixture()
        self.patches(f)
        ctx = E.context(REVISION, REVIEW)
        for attestor, original, label in (
            (E.attest, f.source, "entrypoint"),
            (P.attest, f.preparer, "candidate operator"),
            (C.attest, f.coordinator, "coordinator"),
        ):
            with self.subTest(label=label):
                attestor.return_value = {**original, "drift": True}
                with self.assertRaisesRegex(ValueError, label):
                    ctx.revalidate(full=True)
                attestor.return_value = original

    def test_invalid_confirmation_stops_before_context(self):
        self.patches(fixture())
        with self.assertRaises(ValueError):
            self.invoke(confirmed=None)
        E.attest.assert_not_called()
        C.unused.assert_not_called()
        self.no_effects()

    def test_run_delegates_once_to_unchanged_fixed_coordinator(self):
        self.patches(fixture())
        self.allow_mock_run()
        state = dict(run_entered=False, run_returned=False)
        result = self.invoke(state=state)
        self.assertEqual(C.run.call_count, 1)
        mode, path, confirmed, reviewed, observer = C.run.call_args.args
        self.assertEqual(
            (mode, path, confirmed, reviewed),
            (
                S.REPLICATION,
                C.authorization_for(S.REPLICATION),
                E.CANDIDATE_DIGEST,
                REVIEW,
            ),
        )
        self.assertTrue(callable(observer))
        self.assertEqual(state, dict(run_entered=True, run_returned=True))
        self.assertTrue(result["authorization_consumed"])
        self.assertFalse(result["future_execution_authorized"])
        self.assertFalse(result["locked_128_evaluation_authorized"])
        self.assertEqual(
            result["commit_digest"], C.run.return_value["deterministic_digest"]
        )
        S.consume.assert_not_called()
        R.record.assert_not_called()
        C.admit.assert_not_called()

    def test_progress_revalidates_before_external_observer(self):
        f = fixture()
        self.patches(f)
        observe = Mock()

        def run(mode, path, confirmed, reviewed, progress):
            f.items[P.RAW_AUTH].revalidate.side_effect = ValueError("progress drift")
            progress("synthetic stage")

        C.run.side_effect = run
        with self.assertRaisesRegex(ValueError, "progress drift"):
            E.dispatch("run", REVISION, REVIEW, E.CANDIDATE_DIGEST, observe, {})
        observe.assert_not_called()
        self.assertEqual(C.run.call_count, 1)

    def test_post_run_drift_is_consumed_not_retryable(self):
        f = fixture()
        self.patches(f)

        def run(*args):
            f.items[P.RAW_AUTH].revalidate.side_effect = ValueError(
                "after commit drift"
            )
            return E.digested(dict(fixture="synthetic commit"))

        C.run.side_effect = run
        result = E.parse(self.cli(self.run_args(), expect_failure=True))
        self.assertEqual(result["status"], "DISPATCH_RETURNED_REVALIDATION_FAILED")
        self.assertTrue(result["authorization_consumed"])
        self.assertTrue(result["coordinator_run_returned"])
        self.assertFalse(result["automatic_retry_allowed"])
        self.assertEqual(C.run.call_count, 1)

    def test_closed_dispatch_rejects_public_and_retry(self):
        self.patches(fixture())
        for mode in ("public", "retry", "resume", "prepare", None):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.invoke(mode=mode)
        self.no_effects()

    def test_post_commit_exception_cannot_downgrade_consumption(self):
        f = fixture()
        self.patches(f)

        def run(*args):
            f.items[P.RAW_AUTH].revalidate.side_effect = S.ExecutionFailure(
                "SYNTHETIC_CHECKER_UNSPENT", False, "post-commit checker failure"
            )
            return E.digested(dict(fixture="synthetic commit"))

        C.run.side_effect = run
        result = E.parse(self.cli(self.run_args(), expect_failure=True))
        self.assertEqual(result["status"], "DISPATCH_RETURNED_REVALIDATION_FAILED")
        self.assertTrue(result["authorization_consumed"])
        self.assertFalse(result["automatic_retry_allowed"])
        C.run.assert_called_once()

    def test_analyze_and_verify_delegate_without_search_or_unused_gate(self):
        self.patches(fixture())
        for mode, operation in (("analyze", C.analyze_and_save), ("verify", C.verify)):
            with self.subTest(mode=mode):
                operation.side_effect = None
                operation.return_value = self.summary()
                result = self.invoke(mode=mode, confirmed=None)
                operation.assert_called_once_with(S.REPLICATION, unittest.mock.ANY)
                self.assertEqual(result["new_replication_search_calls"], 0)
                self.assertEqual(result["historical_replication_cells_executed"], 1024)
                self.assertEqual(result["source_multiset_count"], 64)
                self.assertEqual(result["scientific_decision"], "SYNTHETIC_ONLY")
                self.assertFalse(result["future_execution_authorized"])
        C.unused.assert_not_called()
        C.run.assert_not_called()
        S.consume.assert_not_called()
        R.record.assert_not_called()

    def test_analysis_rejects_confirmation(self):
        self.patches(fixture())
        for mode in ("analyze", "verify"):
            with (
                self.subTest(mode=mode),
                self.assertRaisesRegex(ValueError, "cannot confirm"),
            ):
                self.invoke(mode=mode)
        self.no_effects()

    def test_analysis_rejects_other_candidate_mode_or_nonproduction_summary(self):
        self.patches(fixture())
        C.verify.side_effect = None
        for key, value in (
            ("authorization_digest", "0" * 64),
            ("execution_mode", S.PUBLIC),
            ("production_adapter_executed", False),
        ):
            with self.subTest(key=key):
                C.verify.return_value = rehash({**self.summary(), key: value})
                with self.assertRaisesRegex(
                    ValueError, "different production candidate"
                ):
                    self.invoke(mode="verify", confirmed=None)

    def test_tampered_coordinator_result_digest_rejected(self):
        self.patches(fixture())
        self.allow_mock_run()
        C.run.return_value["deterministic_digest"] = "0" * 64
        with self.assertRaises(ValueError):
            self.invoke()

    def test_execution_failure_preserves_core_consumption_status(self):
        self.patches(fixture())
        for consumed in (False, True):
            with self.subTest(consumed=consumed):
                C.run.side_effect = S.ExecutionFailure(
                    "SYNTHETIC_CORE_FAILURE", consumed, "fixture"
                )
                result = E.parse(self.cli(self.run_args(), expect_failure=True))
                self.assertEqual(result["status"], "SYNTHETIC_CORE_FAILURE")
                self.assertIs(result["authorization_consumed"], consumed)
                self.assertFalse(result["automatic_retry_allowed"])
        self.assertEqual(C.run.call_count, 2)

    def test_generic_dispatch_failure_is_unknown_not_false(self):
        self.patches(fixture())
        C.run.side_effect = OSError("fixture failure")
        result = E.parse(self.cli(self.run_args(), expect_failure=True))
        self.assertIsNone(result["authorization_consumed"])
        self.assertIsNone(result["new_replication_search_calls"])
        self.assertFalse(result["automatic_retry_allowed"])
        C.run.assert_called_once()

    def test_pre_dispatch_failure_does_not_assert_claim_unspent(self):
        self.patches(fixture())
        E.attest.side_effect = ValueError("source mismatch")
        result = E.parse(self.cli(self.run_args(), expect_failure=True))
        self.assertIsNone(result["authorization_consumed"])
        self.assertEqual(result["new_replication_search_calls"], 0)
        self.assertFalse(result["run_dispatch_entered"])
        self.no_effects()

    def test_publication_uncertainty_retains_unknown_consumption(self):
        self.patches(fixture())
        C.run.side_effect = S.base.PublicationUncertain("synthetic publication")
        result = E.parse(self.cli(self.run_args(), expect_failure=True))
        self.assertEqual(result["status"], "PUBLICATION_UNCERTAIN")
        self.assertIsNone(result["authorization_consumed"])
        self.assertFalse(result["automatic_retry_allowed"])

    def test_analysis_failure_does_not_assert_unconsumed(self):
        self.patches(fixture())
        C.verify.side_effect = ValueError("synthetic verification error")
        result = E.parse(
            self.cli(
                [
                    "--verify",
                    "--implementation-revision",
                    REVISION,
                    "--reviewed-revision",
                    REVIEW,
                ],
                expect_failure=True,
            )
        )
        self.assertIsNone(result["authorization_consumed"])
        self.assertEqual(result["new_replication_search_calls"], 0)
        C.run.assert_not_called()

    def test_delivery_failure_after_mock_commit_preserves_consumed(self):
        self.patches(fixture())
        self.allow_mock_run()

        class Sink(io.BytesIO):
            first = True

            def write(self, raw):
                if self.first:
                    self.first = False
                    raise OSError("synthetic stdout failure")
                return super().write(raw)

        result = E.parse(self.cli(self.run_args(), sink=Sink(), expect_failure=True))
        self.assertEqual(result["status"], "RESULT_DELIVERY_UNCERTAIN")
        self.assertTrue(result["authorization_consumed"])
        self.assertFalse(result["automatic_retry_allowed"])
        C.run.assert_called_once()

    def test_cli_rejects_missing_extra_abbreviated_or_override_arguments(self):
        self.patches(fixture())
        for args in (
            [],
            ["--run"],
            ["--pre"],
            ["--self-test", "--run"],
            ["--self-test", "--confirm-digest", E.CANDIDATE_DIGEST],
            [
                "--preflight",
                "--implementation-revision",
                REVISION,
                "--reviewed-revision",
                REVIEW,
            ],
            [
                "--verify",
                "--implementation-revision",
                REVISION,
                "--reviewed-revision",
                REVIEW,
                "--confirm-digest",
                E.CANDIDATE_DIGEST,
            ],
            [*self.run_args(), "--output", "/tmp/retry"],
            [*self.run_args(), "--mode", "public"],
            [*self.run_args(), "--seed", "1"],
        ):
            with self.subTest(args=args):
                self.cli(args, expect_failure=True)
        E.attest.assert_not_called()
        self.no_effects()

    def test_attest_covers_all_three_reviewed_files_and_frozen_dependencies(self):
        f = fixture()
        with (
            patch.object(R, "oid", side_effect=lambda x: x),
            patch.object(E.core, "git_head", return_value=REVISION),
            patch.object(E.core, "require_ancestor") as ancestor,
            patch.object(R.public, "_origin") as origin,
            patch.object(
                R, "snapshot_file", side_effect=lambda path: f.items[Path(path)]
            ),
            patch.object(R, "reviewed_file") as reviewed,
        ):
            result = E.attest(REVISION)
        self.assertEqual(set(result["files"]), set(E.SOURCE_FILES))
        self.assertEqual(result["candidate_digest"], E.CANDIDATE_DIGEST)
        ancestor.assert_any_call(ROOT, E.EVIDENCE_REVIEW, REVISION)
        ancestor.assert_any_call(ROOT, REVISION, REVISION)
        origin.assert_called_once_with(P, E.CANDIDATE_OPERATOR)
        self.assertEqual(reviewed.call_count, 3)
        for name in E.SOURCE_FILES:
            self.assertEqual(
                result["files"][name]["sha256"], E.sha(f.items[ROOT / name].raw)
            )
            f.items[ROOT / name].revalidate.assert_called_once()

    def test_attest_rejects_head_change(self):
        f = fixture()
        with (
            patch.object(R, "oid", side_effect=lambda x: x),
            patch.object(E.core, "git_head", side_effect=[REVISION, REVIEW]),
            patch.object(E.core, "require_ancestor"),
            patch.object(R.public, "_origin"),
            patch.object(
                R, "snapshot_file", side_effect=lambda path: f.items[Path(path)]
            ),
            patch.object(R, "reviewed_file"),
            self.assertRaisesRegex(ValueError, "HEAD changed"),
        ):
            E.attest(REVISION)

    def test_static_cli_from_outside_checkout_has_no_runtime_effects(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "cache"
            cache.mkdir(mode=0o700)
            env = {
                **os.environ,
                "PYTHONPATH": str(ROOT / "src"),
                "PYTHONPYCACHEPREFIX": str(cache),
            }
            result = subprocess.run(
                [sys.executable, "-P", "-B", str(ROOT / E.SCRIPT), "--self-test"],
                cwd=directory,
                env=env,
                capture_output=True,
                check=True,
            )
        receipt = E.parse(result.stdout)
        self.assertEqual(
            receipt["status"], "PRODUCTION_ENTRYPOINT_STATIC_SELF_TEST_PASS"
        )
        self.assertFalse(receipt["replication_execution_authorized"])
        self.assertEqual(receipt["replication_search_calls"], 0)


if __name__ == "__main__":
    unittest.main()
