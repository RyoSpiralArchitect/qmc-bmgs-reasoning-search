"""Synthetic operator boundaries; no real candidate, claim or sealed search.

Mocked admission metadata below is deliberately NOT qualification evidence.
The actual candidate must separately pass the unchanged genuine admission path.
"""

from __future__ import annotations

from contextlib import ExitStack
import copy
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
    "receiver_candidate_tested", ROOT / "scripts/feedback_budget_receiver_candidate.py"
)
assert SPEC is not None and SPEC.loader is not None
P = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = P
SPEC.loader.exec_module(P)
C, R, S, B = P.C, P.R, P.S, P.B
REVISION, REVIEWED = "f" * 40, "e" * 40


def rehash(value):
    return P.digested(B.without_digest(value))


def snapshot(path, raw):
    return SimpleNamespace(path=Path(path), raw=raw, revalidate=Mock())


def fixture():
    manifest = R.load_inputs(S.PUBLIC).manifest
    manifest.update(
        execution_mode=S.REPLICATION,
        experiment_id=S.REPLICATION_ID,
        source_multiset_count=64,
        cohort_seal={"fixture": "synthetic"},
    )
    inputs = SimpleNamespace(manifest=rehash(manifest))
    environment = {
        name: {"fixture": name}
        for name in ("source", "runtime", "baseline", "authorities", "admission_proof")
    }
    base = SimpleNamespace(
        inputs=inputs,
        revalidate=Mock(),
        proof=SimpleNamespace(
            environment_raw=P.canonical(environment),
            source_raw=P.canonical({"deterministic_digest": "a" * 64}),
        ),
        snapshots=tuple(
            snapshot(ROOT / name, b"{}\n")
            for name in (B.CANDIDATE, B.CERTIFICATE, B.BUNDLE_COMMIT)
        ),
    )
    source = {
        "implementation_revision": P.COORDINATOR_REVISION,
        "deterministic_digest": P.COORDINATOR_DIGEST,
        "fixture": "synthetic source reference",
    }
    operator = P.digested(
        {
            "schema_version": P.DOMAIN + "/source",
            "implementation_revision": REVISION,
            "coordinator_revision": P.COORDINATOR_REVISION,
            "fixture": "synthetic operator",
        }
    )
    parent = P.digested(
        {
            "schema_version": S.DOMAIN + "/output-parent",
            "path": str(B.OUTPUT.parent),
            "identities": [[1, 2]],
        }
    )
    qualifier = {
        "summary_digest": P.PUBLIC_SUMMARY_DIGEST,
        "source_digest": P.COORDINATOR_DIGEST,
        "summary_path": str(ROOT / C.SUMMARY_MIRROR),
        "fixture": "synthetic qualification",
    }
    with patch.object(S, "parent_binding", return_value=parent):
        auth = C.candidate(S.REPLICATION, inputs, base, source, qualifier)
    raw = P.canonical(auth)
    return SimpleNamespace(
        base=base,
        source=source,
        operator=operator,
        parent=parent,
        qualifier=qualifier,
        auth=auth,
        qualifier_check=Mock(),
        public_items=(snapshot(C.PUBLIC_SUMMARY, b"{}\n"),),
        raw=snapshot(P.RAW_AUTH, raw),
        promoted=snapshot(C.authorization_for(S.REPLICATION), raw),
        preparation=snapshot(
            ROOT / P.PREPARATION_MIRROR,
            P.canonical(P.preparation_receipt(auth, operator)),
        ),
        admitted=SimpleNamespace(auth=auth, revalidate=Mock()),
    )


class OperatorBoundaries(unittest.TestCase):
    def preparation_patches(self, f):
        stack = ExitStack()
        self.addCleanup(stack.close)
        for target, name, options in (
            (C, "unused", {}),
            (S, "descriptor_preflight", {}),
            (P.os.path, "lexists", {"return_value": False}),
            (P, "attest", {"return_value": f.operator}),
            (P.core, "git_head", {"return_value": REVISION}),
            (P, "public_snapshots", {"return_value": f.public_items}),
            (C, "attest", {"return_value": f.source}),
            (C, "qualified_public", {"return_value": (f.qualifier, f.qualifier_check)}),
            (C, "receiver_admit", {"return_value": f.base}),
            (S, "parent_binding", {"return_value": f.parent}),
            (S, "consume", {"side_effect": AssertionError("must not consume")}),
            (C, "run", {"side_effect": AssertionError("must not run")}),
            (R, "record", {"side_effect": AssertionError("must not generate")}),
        ):
            stack.enter_context(patch.object(target, name, **options))

        def publish(path, value, check):
            self.assertEqual(path, P.RAW_AUTH)
            self.assertEqual(P.canonical(value), f.raw.raw)
            check()
            check()

        stack.enter_context(
            patch.object(S.base, "_publish_summary", side_effect=publish)
        )

    def verification_patches(self, f):
        stack = ExitStack()
        self.addCleanup(stack.close)
        snapshots = {item.path: item for item in (f.raw, f.promoted, f.preparation)}
        for target, name, options in (
            (C, "unused", {}),
            (P, "attest", {"return_value": f.operator}),
            (P.core, "git_head", {"return_value": REVIEWED}),
            (R, "oid", {"side_effect": lambda x: x}),
            (P.core, "require_ancestor", {}),
            (R, "reviewed_file", {}),
            (R, "snapshot_file", {"side_effect": lambda path: snapshots[Path(path)]}),
            (P, "public_snapshots", {"return_value": f.public_items}),
            (C, "admit", {"return_value": f.admitted}),
            (S, "consume", {"side_effect": AssertionError("must not consume")}),
            (C, "run", {"side_effect": AssertionError("must not run")}),
            (R, "record", {"side_effect": AssertionError("must not generate")}),
        ):
            stack.enter_context(patch.object(target, name, **options))

    def test_fixed_candidate_does_not_replace_old_candidate_or_study(self):
        self.assertEqual(
            P.RAW_AUTH, Path(str(B.OUTPUT) + ".receiver-v2.authorization.json")
        )
        self.assertNotEqual(P.RAW_AUTH, B.ORIGINAL_RAW)
        self.assertNotEqual(C.authorization_for(S.REPLICATION), ROOT / B.CANDIDATE)
        self.assertEqual(C.output_for(S.REPLICATION), B.OUTPUT)
        self.assertFalse(P.self_test()["replication_execution_authorized"])

    def test_candidate_rejects_changed_source_public_proof_or_authority(self):
        f = fixture()
        variants = []
        for key, value in (
            ("candidate_is_execution_authority", True),
            ("expected_cell_count", True),
            ("expected_cell_count", 16),
            ("output_path", str(B.OUTPUT) + "-retry"),
            ("execution_mode", S.PUBLIC),
        ):
            variants.append({**f.auth, key: value})
        altered = copy.deepcopy(f.auth)
        altered["coordinator_source"]["implementation_revision"] = REVISION
        variants.append(altered)
        altered = copy.deepcopy(f.auth)
        altered["connector_qualification"]["summary_digest"] = "0" * 64
        variants.append(altered)
        for value in variants:
            with self.subTest(value=value), self.assertRaises(ValueError):
                P.candidate_shape(P.canonical(rehash(value)))

    def test_preparation_uses_genuine_entrypoints_without_consumption(self):
        f = fixture()
        self.preparation_patches(f)
        result = P.prepare(REVISION)
        self.assertEqual(P.canonical(result), f.preparation.raw)
        C.qualified_public.assert_called_once_with(
            P.PUBLIC_REVIEW, f.source, unittest.mock.ANY
        )
        C.receiver_admit.assert_called_once()
        self.assertEqual(f.qualifier_check.call_count, 2)
        self.assertEqual(f.base.revalidate.call_count, 2)
        self.assertFalse(result["candidate_is_execution_authority"])
        self.assertFalse(result["replication_execution_authorized"])
        self.assertEqual(result["replication_search_calls"], 0)
        S.consume.assert_not_called()
        C.run.assert_not_called()
        R.record.assert_not_called()

    def test_occupied_preparation_slots_reject_before_attestation(self):
        f = fixture()
        self.preparation_patches(f)
        for path in (
            P.RAW_AUTH,
            C.authorization_for(S.REPLICATION),
            ROOT / P.PREPARATION_MIRROR,
        ):
            with self.subTest(path=path):
                P.os.path.lexists.side_effect = lambda observed, occupied=path: (
                    Path(observed) == occupied
                )
                with self.assertRaisesRegex(ValueError, "occupied"):
                    P.prepare(REVISION)
        P.attest.assert_not_called()
        C.qualified_public.assert_not_called()

    def test_dangling_candidate_symlink_is_occupied(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidate.json"
            path.symlink_to(Path(directory) / "missing")
            with (
                patch.object(P, "RAW_AUTH", path),
                patch.object(C, "unused"),
                self.assertRaisesRegex(ValueError, "occupied"),
            ):
                P.unoccupied_preparation()
            self.assertTrue(path.is_symlink())

    def test_spent_original_claim_stops_before_source_or_qualification(self):
        f = fixture()
        self.preparation_patches(f)
        C.unused.side_effect = S.ExecutionFailure(
            "AUTHORIZATION_ALREADY_SPENT", True, "spent"
        )
        with self.assertRaises(S.ExecutionFailure):
            P.prepare(REVISION)
        P.attest.assert_not_called()
        S.base._publish_summary.assert_not_called()

    def test_prepare_requires_frozen_implementation_head(self):
        f = fixture()
        self.preparation_patches(f)
        P.core.git_head.return_value = REVIEWED
        with self.assertRaisesRegex(ValueError, "implementation HEAD"):
            P.prepare(REVISION)
        C.qualified_public.assert_not_called()

    def test_bad_saved_public_summary_stops_before_qualification(self):
        f = fixture()
        self.preparation_patches(f)
        P.public_snapshots.side_effect = ValueError("saved PUBLIC differs")
        with self.assertRaisesRegex(ValueError, "saved PUBLIC"):
            P.prepare(REVISION)
        C.qualified_public.assert_not_called()
        S.base._publish_summary.assert_not_called()

    def test_changed_qualified_source_stops_before_qualification(self):
        f = fixture()
        self.preparation_patches(f)
        C.attest.return_value = {**f.source, "deterministic_digest": "0" * 64}
        with self.assertRaisesRegex(ValueError, "qualified source"):
            P.prepare(REVISION)
        C.qualified_public.assert_not_called()

    def test_public_qualification_failure_stops_before_sealed_admission(self):
        f = fixture()
        self.preparation_patches(f)
        C.qualified_public.side_effect = ValueError("PUBLIC mismatch")
        with self.assertRaisesRegex(ValueError, "PUBLIC mismatch"):
            P.prepare(REVISION)
        C.receiver_admit.assert_not_called()
        S.base._publish_summary.assert_not_called()

    def test_wrong_source_denominator_rejected_before_publication(self):
        f = fixture()
        f.base.inputs.manifest["source_multiset_count"] = 1
        self.preparation_patches(f)
        with self.assertRaisesRegex(ValueError, "64-source"):
            P.prepare(REVISION)
        S.base._publish_summary.assert_not_called()

    def test_publication_revalidates_qualified_evidence(self):
        f = fixture()
        self.preparation_patches(f)
        f.qualifier_check.side_effect = ValueError("PUBLIC changed at publication")
        with self.assertRaisesRegex(ValueError, "PUBLIC changed"):
            P.prepare(REVISION)
        S.consume.assert_not_called()

    def test_publication_revalidates_output_parent(self):
        f = fixture()
        self.preparation_patches(f)
        S.parent_binding.side_effect = [f.parent, {"different": True}]
        with self.assertRaisesRegex(ValueError, "parent changed"):
            P.prepare(REVISION)

    def test_publication_rejects_operator_source_change(self):
        f = fixture()
        self.preparation_patches(f)
        P.attest.side_effect = [f.operator, {"different": True}]
        with self.assertRaisesRegex(ValueError, "operator source changed"):
            P.prepare(REVISION)
        S.consume.assert_not_called()

    def test_late_claim_rejects_before_candidate_publication(self):
        f = fixture()
        self.preparation_patches(f)
        C.unused.side_effect = [
            None,
            S.ExecutionFailure("AUTHORIZATION_ALREADY_SPENT", True, "late claim"),
        ]
        with self.assertRaises(S.ExecutionFailure):
            P.prepare(REVISION)
        S.base._publish_summary.assert_not_called()

    def test_candidate_mirror_appearing_at_publication_rejects(self):
        f = fixture()
        self.preparation_patches(f)

        def publish(path, value, check):
            P.os.path.lexists.side_effect = lambda observed: (
                Path(observed) == C.authorization_for(S.REPLICATION)
            )
            check()

        S.base._publish_summary.side_effect = publish
        with self.assertRaisesRegex(ValueError, "promoted candidate appeared"):
            P.prepare(REVISION)
        S.consume.assert_not_called()

    def test_real_exclusive_publication_retains_uncertain_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "candidate.json"
            value = P.digested({"synthetic": True})
            check = Mock(side_effect=[None, ValueError("post-publication fault")])
            with self.assertRaises(S.base.PublicationUncertain):
                S.base._publish_summary(path, value, check)
            self.assertEqual(path.read_bytes(), P.canonical(value))
            with self.assertRaises(S.mechanics._NameConflictError):
                S.base._publish_summary(path, value, lambda: None)
            self.assertEqual(path.read_bytes(), P.canonical(value))

    def test_review_uses_frozen_production_admission_but_never_run(self):
        f = fixture()
        self.verification_patches(f)
        result = P.verify_candidate(REVISION, REVIEWED)
        C.admit.assert_called_once_with(
            S.REPLICATION,
            f.promoted.path,
            f.auth["deterministic_digest"],
            REVIEWED,
            observe=unittest.mock.ANY,
        )
        self.assertTrue(result["production_admission_verified"])
        self.assertFalse(result["production_adapter_executed"])
        self.assertFalse(result["replication_execution_authorized"])
        self.assertFalse(result["candidate_is_execution_authority"])
        self.assertEqual(result["replication_search_calls"], 0)
        self.assertEqual(C.unused.call_count, 2)
        for item in (f.raw, f.promoted, f.preparation) + f.public_items:
            item.revalidate.assert_called_once()
        S.consume.assert_not_called()
        C.run.assert_not_called()
        R.record.assert_not_called()

    def test_review_rejects_raw_mirror_difference_before_admission(self):
        f = fixture()
        self.verification_patches(f)
        f.raw.raw = b"{}\n"
        with self.assertRaisesRegex(ValueError, "raw/promoted"):
            P.verify_candidate(REVISION, REVIEWED)
        C.admit.assert_not_called()

    def test_review_rejects_preparation_receipt_difference_before_admission(self):
        f = fixture()
        self.verification_patches(f)
        f.preparation.raw = b"{}\n"
        with self.assertRaisesRegex(ValueError, "preparation receipt"):
            P.verify_candidate(REVISION, REVIEWED)
        C.admit.assert_not_called()

    def test_review_rejects_unreviewed_promoted_bytes_before_admission(self):
        f = fixture()
        self.verification_patches(f)
        R.reviewed_file.side_effect = ValueError("not reviewed")
        with self.assertRaisesRegex(ValueError, "not reviewed"):
            P.verify_candidate(REVISION, REVIEWED)
        C.admit.assert_not_called()

    def test_review_propagates_real_admission_failure(self):
        f = fixture()
        self.verification_patches(f)
        C.admit.side_effect = ValueError("authentic admission failed")
        with self.assertRaisesRegex(ValueError, "authentic admission"):
            P.verify_candidate(REVISION, REVIEWED)
        S.consume.assert_not_called()

    def test_review_rejects_different_independent_candidate(self):
        f = fixture()
        self.verification_patches(f)
        f.admitted.auth = {"different": True}
        with self.assertRaisesRegex(ValueError, "reconstruction differs"):
            P.verify_candidate(REVISION, REVIEWED)

    def test_review_rechecks_original_claim_after_admission(self):
        f = fixture()
        self.verification_patches(f)
        C.unused.side_effect = [
            None,
            S.ExecutionFailure("AUTHORIZATION_ALREADY_SPENT", True, "late claim"),
        ]
        with self.assertRaises(S.ExecutionFailure):
            P.verify_candidate(REVISION, REVIEWED)

    def test_review_rejects_operator_source_change(self):
        f = fixture()
        self.verification_patches(f)
        P.attest.side_effect = [f.operator, {"different": True}]
        with self.assertRaisesRegex(ValueError, "operator source changed"):
            P.verify_candidate(REVISION, REVIEWED)

    def test_source_attestation_covers_exact_three_new_files(self):
        items = {
            ROOT / relative: snapshot(ROOT / relative, relative.encode())
            for relative in P.SOURCE_FILES
        }
        with (
            patch.object(R, "oid", return_value=REVISION),
            patch.object(P.core, "git_head", return_value=REVISION),
            patch.object(P.core, "require_ancestor"),
            patch.object(R.public, "_origin") as origin,
            patch.object(R, "reviewed_file") as reviewed,
            patch.object(R, "snapshot_file", side_effect=lambda path: items[path]),
        ):
            value = P.attest(REVISION)
        self.assertEqual(set(value["files"]), set(P.SOURCE_FILES))
        origin.assert_called_once_with(C, P.COORDINATOR)
        self.assertEqual(reviewed.call_count, 3)
        for item in items.values():
            item.revalidate.assert_called_once()

    def test_saved_public_bytes_must_match_reviewed_summary(self):
        summary = snapshot(ROOT / C.SUMMARY_MIRROR, b"{}\n")
        commit = snapshot(ROOT / C.COMMIT_MIRROR, b"{}\n")
        verification = snapshot(ROOT / P.PUBLIC_VERIFICATION, b"{}\n")
        saved = snapshot(C.PUBLIC_SUMMARY, b'{"different":true}\n')
        with (
            patch.object(
                R, "snapshot_file", side_effect=[summary, commit, verification, saved]
            ),
            patch.object(R, "reviewed_file"),
            self.assertRaisesRegex(ValueError, "saved PUBLIC"),
        ):
            P.public_snapshots()

    def test_public_verification_status_and_authority_are_checked(self):
        valid = {
            "status": "PUBLIC_SUMMARY_INDEPENDENTLY_VERIFIED",
            "summary_digest": P.PUBLIC_SUMMARY_DIGEST,
            "replication_execution_authorized": False,
            "scientific_decision": None,
        }
        for change in (
            {},
            {"status": "NOT_RUN"},
            {"replication_execution_authorized": True},
            {"summary_digest": "0" * 64},
        ):
            value = P.digested({**valid, **change})
            items = [
                snapshot(ROOT / C.SUMMARY_MIRROR, b"{}\n"),
                snapshot(ROOT / C.COMMIT_MIRROR, b"{}\n"),
                snapshot(ROOT / P.PUBLIC_VERIFICATION, P.canonical(value)),
                snapshot(C.PUBLIC_SUMMARY, b"{}\n"),
            ]
            with (
                patch.object(R, "snapshot_file", side_effect=items),
                patch.object(R, "reviewed_file"),
            ):
                if change:
                    with self.assertRaisesRegex(ValueError, "independent PUBLIC"):
                        P.public_snapshots()
                else:
                    self.assertEqual(len(P.public_snapshots()), 4)


class CliBoundaries(unittest.TestCase):
    def test_no_execution_confirmation_or_path_override_cli(self):
        for arguments in (
            ("--run",),
            ("--prepare", "--confirm-digest", "a" * 64),
            ("--prepare", "--output", "/tmp/elsewhere"),
            ("--prepare",),
            ("--self-test", "--implementation-revision", REVISION),
            ("--verify-candidate", "--implementation-revision", REVISION),
        ):
            with (
                self.subTest(arguments=arguments),
                patch.object(sys, "argv", [P.SCRIPT, *arguments]),
                patch.object(P, "prepare") as prepare,
                patch.object(P, "verify_candidate") as verify,
                patch.object(sys, "stderr", io.StringIO()),
                self.assertRaises(SystemExit) as error,
            ):
                P.main()
            self.assertEqual(error.exception.code, 2)
            prepare.assert_not_called()
            verify.assert_not_called()

    def test_failure_never_claims_unused_authorization(self):
        output = SimpleNamespace(buffer=io.BytesIO())
        with (
            patch.object(
                sys,
                "argv",
                [P.SCRIPT, "--prepare", "--implementation-revision", REVISION],
            ),
            patch.object(P, "prepare", side_effect=ValueError("failure")),
            patch.object(sys, "stdout", output),
            patch.object(sys, "stderr", io.StringIO()),
            self.assertRaises(SystemExit),
        ):
            P.main()
        value = P.parse(output.buffer.getvalue())
        self.assertIsNone(value["authorization_consumed"])
        self.assertFalse(value["automatic_retry_allowed"])
        self.assertFalse(value["replication_execution_authorized"])

    def test_completed_result_delivery_failure_is_uncertain_not_unrun(self):
        class Sink:
            def __init__(self):
                self.calls = 0
                self.output = b""

            def write(self, raw):
                self.calls += 1
                if self.calls == 1:
                    raise OSError("delivery failed")
                self.output += raw

            def flush(self):
                pass

        sink = Sink()
        with (
            patch.object(
                sys,
                "argv",
                [P.SCRIPT, "--prepare", "--implementation-revision", REVISION],
            ),
            patch.object(P, "prepare", return_value=P.digested({"prepared": True})),
            patch.object(sys, "stdout", SimpleNamespace(buffer=sink)),
            patch.object(sys, "stderr", io.StringIO()),
            self.assertRaises(SystemExit),
        ):
            P.main()
        value = P.parse(sink.output)
        self.assertEqual(value["status"], "RESULT_DELIVERY_UNCERTAIN")
        self.assertFalse(value["automatic_retry_allowed"])

    def test_publication_uncertainty_is_preserved_by_cli(self):
        output = SimpleNamespace(buffer=io.BytesIO())
        with (
            patch.object(
                sys,
                "argv",
                [P.SCRIPT, "--prepare", "--implementation-revision", REVISION],
            ),
            patch.object(
                P,
                "prepare",
                side_effect=S.base.PublicationUncertain("retain candidate"),
            ),
            patch.object(sys, "stdout", output),
            patch.object(sys, "stderr", io.StringIO()),
            self.assertRaises(SystemExit),
        ):
            P.main()
        value = P.parse(output.buffer.getvalue())
        self.assertEqual(value["status"], "CANDIDATE_PUBLICATION_UNCERTAIN")
        self.assertIsNone(value["authorization_consumed"])
        self.assertFalse(value["automatic_retry_allowed"])

    def test_verify_cli_is_review_not_execution_confirmation(self):
        output = SimpleNamespace(buffer=io.BytesIO())
        result = P.digested(
            {"status": "synthetic review", "replication_execution_authorized": False}
        )
        with (
            patch.object(
                sys,
                "argv",
                [
                    P.SCRIPT,
                    "--verify-candidate",
                    "--implementation-revision",
                    REVISION,
                    "--reviewed-revision",
                    REVIEWED,
                ],
            ),
            patch.object(P, "verify_candidate", return_value=result) as verify,
            patch.object(P, "prepare") as prepare,
            patch.object(sys, "stdout", output),
        ):
            P.main()
        verify.assert_called_once_with(REVISION, REVIEWED, unittest.mock.ANY)
        prepare.assert_not_called()
        self.assertEqual(output.buffer.getvalue(), P.canonical(result))

    def test_static_cli_from_outside_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {
                **os.environ,
                "PYTHONPATH": str(ROOT / "src"),
                "PYTHONPYCACHEPREFIX": str(Path(directory) / "cache"),
            }
            result = subprocess.run(
                [sys.executable, "-P", "-B", str(ROOT / P.SCRIPT), "--self-test"],
                cwd=directory,
                env=env,
                capture_output=True,
                check=True,
            )
        self.assertEqual(
            P.parse(result.stdout)["status"], "CANDIDATE_ONLY_STATIC_SELF_TEST_PASS"
        )


if __name__ == "__main__":
    unittest.main()
