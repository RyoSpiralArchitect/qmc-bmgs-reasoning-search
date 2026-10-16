"""C3 MOCK reconstruction + real temporary-directory fault tests, not issuance."""

from __future__ import annotations

import ast
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
    "e4_publisher_tested", ROOT / "scripts/feedback_budget_receiver_e4_publisher.py"
)
assert SPEC is not None and SPEC.loader is not None
P = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = P
SPEC.loader.exec_module(P)
K, M = P.K, P.M


class MemoryEvidence:
    def __init__(self, files):
        self.files, self.snapshots = files, []
        self.revalidate = Mock()

    def file(self, path):
        item = SimpleNamespace(
            path=path, raw=self.files[str(path.relative_to(ROOT))], revalidate=Mock()
        )
        self.snapshots.append(item)
        return item


class Publisher(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = (ROOT / K.PROPOSAL).read_bytes()
        cls.proposal = P.parse(cls.raw)
        cls.certifier = cls.proposal["source"]["certifier"]
        cls.source = P.digested(
            dict(
                schema_version=P.DOMAIN + "/source",
                implementation_revision="a" * 40,
                proposal_review_revision=P.REVIEW_REVISION,
                files={
                    name: dict(byte_count=0, sha256=P.sha(b""))
                    for name in P.SOURCE_FILES
                },
                certifier=cls.certifier,
            )
        )
        cls.files = {
            path: (ROOT / path).read_bytes()
            for path in (
                *P.PINS,
                *(x["path"] for x in K.historical_references().values()),
            )
        }

    def fixture(self):
        """Only the numerical/source layer is mocked; descriptor storage is real."""
        stack = ExitStack()
        self.addCleanup(stack.close)
        temporary = stack.enter_context(
            tempfile.TemporaryDirectory(prefix="qmc-c3-test-")
        )
        root = Path(temporary).resolve()
        outer, docs = root / "work", root / "docs"
        outer.mkdir(mode=0o700)
        docs.mkdir(mode=0o700)
        bundle = outer / "fixed-certificate"
        stack.enter_context(patch.object(P, "BUNDLE", bundle))
        stack.enter_context(
            patch.object(
                P,
                "MIRRORS",
                tuple(
                    docs / name
                    for name in ("certificate.json", "verification.json", "commit.json")
                ),
            )
        )
        stack.enter_context(patch.object(P, "_STARTED", False))
        stack.enter_context(patch.object(K, "_RECONSTRUCTION_STARTED", False))
        stack.enter_context(patch.object(P, "_guard"))
        stack.enter_context(
            patch.object(P, "attest", return_value=copy.deepcopy(self.source))
        )
        stack.enter_context(patch.object(P.core, "git_head", return_value="b" * 40))
        stack.enter_context(patch.object(P.core, "git_bytes", return_value=b""))
        stack.enter_context(patch.object(P.R, "oid", side_effect=lambda value: value))
        unused = stack.enter_context(patch.object(P.C, "unused"))
        evidence = SimpleNamespace(revalidate=Mock())
        stack.enter_context(patch.object(P.V, "Evidence", return_value=evidence))
        saved = SimpleNamespace(raw=self.raw)
        stack.enter_context(patch.object(P, "_authenticate", return_value=saved))
        parent = M._PinnedParent.open(outer)
        identities = [list(x) for x in parent.component_identities]
        parent.close()
        locations = dict(
            live_locations=dict(
                output_parent=dict(path=str(outer), identities=identities)
            ),
            persistent_locations=dict(
                output_parent=dict(
                    path=str(outer),
                    components=[
                        dict(volume_uuid=K.DATA_VOLUME_UUID, inode=x[1])
                        for x in identities
                    ],
                )
            ),
        )
        capture = object.__new__(K._LiveCapture)
        K._LIVE[capture] = SimpleNamespace(
            raw=self.raw,
            work_raw=P.canonical(self.proposal["reconstruction"]["work"]),
            head="b" * 40,
            source=self.certifier,
            locations=locations,
        )
        stack.callback(lambda: K._LIVE.pop(capture, None))
        # The public fresh-process guard must see no capture BEFORE the mocked
        # reconstruction. Registration occurs only when its mock is called.
        state = K._LIVE.pop(capture)

        def reconstruct(revision):
            self.assertEqual(revision, P.CERTIFIER_REVISION)
            K._LIVE[capture] = state
            return capture

        reconstructed = stack.enter_context(
            patch.object(K, "reconstruct", side_effect=reconstruct)
        )
        revalidate = stack.enter_context(patch.object(K._LiveCapture, "revalidate"))
        stack.enter_context(
            patch.object(K, "_volume_uuid", return_value=K.DATA_VOLUME_UUID)
        )
        stack.enter_context(
            patch.object(
                K,
                "operation_receipt",
                return_value=dict(
                    implementation_source=self.certifier, receiver_identity=locations
                ),
            )
        )
        return SimpleNamespace(
            root=root,
            bundle=bundle,
            outer=outer,
            docs=docs,
            evidence=evidence,
            saved=saved,
            capture=capture,
            state=state,
            reconstructed=reconstructed,
            revalidate=revalidate,
            unused=unused,
        )

    def issue(self):
        return P.issue("a" * 40, scope=P.SCOPE)

    def test_static_self_test_has_no_effect_or_numerics(self):
        with patch.object(K, "reconstruct") as compute:
            with self.assertRaisesRegex(Exception, "substituted"):
                P.self_test()
            compute.assert_not_called()
        result = P.self_test()
        self.assertIs(result["certificate_issued"], False)
        self.assertIs(result["filesystem_effects_attempted"], False)
        self.assertEqual(result["work"], P.N.initial_work())

    def test_exact_three_file_closure(self):
        P.closed_source(dict.fromkeys(P.SOURCE_FILES))
        for value in (
            {},
            [],
            dict.fromkeys(P.SOURCE_FILES[:2]),
            dict.fromkeys((*P.SOURCE_FILES, "extra")),
        ):
            with self.subTest(value=value), self.assertRaises(Exception):
                P.closed_source(value)
        with patch.object(P, "SOURCE_FILES", (P.SCRIPT,)):
            with self.assertRaisesRegex(Exception, "registry"):
                P.closed_source(dict.fromkeys((P.SCRIPT, P.TEST, P.POLICY)))

    def test_attestation_binds_all_files_and_frozen_certifier(self):
        items = [
            SimpleNamespace(raw=name.encode(), revalidate=Mock())
            for name in P.SOURCE_FILES
        ]
        with (
            patch.object(P.core, "git_head", return_value="b" * 40),
            patch.object(P.core, "require_ancestor") as ancestor,
            patch.object(P.R, "oid", side_effect=lambda v: v),
            patch.object(P.R.public, "_origin") as origin,
            patch.object(K, "attest", return_value=self.certifier),
            patch.object(P.R, "snapshot_file", side_effect=items) as snap,
            patch.object(P.R, "reviewed_file") as reviewed,
        ):
            result = P.attest("a" * 40)
        self.assertEqual(result["certifier"], self.certifier)
        self.assertEqual(set(result["files"]), set(P.SOURCE_FILES))
        self.assertEqual(
            [call.args[1:] for call in ancestor.call_args_list],
            [(P.REVIEW_REVISION, "a" * 40), ("a" * 40, "b" * 40)],
        )
        self.assertEqual(
            [call.args for call in snap.call_args_list],
            [(ROOT / p,) for p in P.SOURCE_FILES],
        )
        self.assertEqual(
            [call.args for call in reviewed.call_args_list],
            [(item, "a" * 40) for item in items],
        )
        origin.assert_called_once_with(K, P.CERTIFIER_SCRIPT)
        for item in items:
            item.revalidate.assert_called_once()

    def test_attestation_rejects_certifier_source_drift_before_own_files(self):
        with (
            patch.object(P.core, "git_head", return_value="b" * 40),
            patch.object(P.core, "require_ancestor"),
            patch.object(P.R, "oid", side_effect=lambda v: v),
            patch.object(P.R.public, "_origin"),
            patch.object(
                K,
                "attest",
                return_value=dict(self.certifier, deterministic_digest="0" * 64),
            ),
            patch.object(P.R, "snapshot_file") as snap,
        ):
            with self.assertRaisesRegex(Exception, "frozen certifier"):
                P.attest("a" * 40)
            snap.assert_not_called()

    def test_fixed_proposal_and_review_authenticate_before_parse(self):
        evidence = MemoryEvidence(self.files)
        with patch.object(P.R, "reviewed_file") as reviewed:
            saved = P._authenticate(evidence, self.source)
        self.assertEqual(saved.raw, self.raw)
        self.assertEqual(
            [call.args[1] for call in reviewed.call_args_list[:4]],
            [pin[0] for pin in P.PINS.values()],
        )
        self.assertEqual(
            [str(x.path.relative_to(ROOT)) for x in evidence.snapshots[:4]],
            list(P.PINS),
        )

    def test_each_pinned_file_tamper_stops_before_historical_parse(self):
        for path in P.PINS:
            with (
                self.subTest(path=path),
                patch.object(P.R, "reviewed_file"),
                patch.object(K, "historical") as historical,
            ):
                files = dict(self.files)
                files[path] += b" "
                with self.assertRaisesRegex(Exception, "pinned"):
                    P._authenticate(MemoryEvidence(files), self.source)
                historical.assert_not_called()

    def test_saved_pass_and_callback_cannot_be_public_proof(self):
        for value in ({"status": "PASS"}, self.proposal, lambda: self.raw, object()):
            with (
                self.subTest(value=type(value)),
                self.assertRaises(P.PublicationFailure),
            ):
                P.issue(value, scope=P.SCOPE)
        with self.assertRaises(TypeError):
            P.issue("a" * 40, scope=P.SCOPE, capture=self.proposal)

    def test_wrong_scope_never_reconstructs_or_creates(self):
        f = self.fixture()
        for scope in (None, True, "production", "continue"):
            with self.subTest(scope=scope), self.assertRaises(P.PublicationFailure):
                P.issue("a" * 40, scope=scope)
        self.assertFalse(f.bundle.exists())
        f.reconstructed.assert_not_called()

    def test_prior_reconstruction_or_live_capture_requires_fresh_process(self):
        f = self.fixture()
        with (
            patch.object(K, "_RECONSTRUCTION_STARTED", True),
            self.assertRaisesRegex(P.PublicationFailure, "fresh process"),
        ):
            self.issue()
        self.assertFalse(f.bundle.exists())
        f.reconstructed.assert_not_called()

    def test_mock_complete_transaction_owns_exact_three_files(self):
        f = self.fixture()
        result = self.issue()
        self.assertIs(result["certificate_issued"], True)
        self.assertEqual(set(p.name for p in f.bundle.iterdir()), set(P.NAMES))
        self.assertEqual((f.bundle / "certificate.json").read_bytes(), self.raw)
        verification = P.parse((f.bundle / "verification.json").read_bytes())
        commit = P.parse((f.bundle / "COMMIT.json").read_bytes())
        self.assertEqual(verification["work"], self.proposal["reconstruction"]["work"])
        self.assertEqual(verification["verification_method"], K.METHOD)
        self.assertIs(verification["certificate_issued_at_verification"], False)
        self.assertEqual(
            commit["payloads"],
            {
                name: P.N.reference((f.bundle / name).read_bytes())
                for name in P.NAMES[:2]
            },
        )
        self.assertEqual(commit["publisher_source"], self.source)
        self.assertEqual(commit["certifier_source"], self.certifier)
        self.assertEqual(commit["proposal_review_revision"], P.REVIEW_REVISION)
        self.assertEqual(commit["publication_order"], list(P.NAMES))
        self.assertEqual(commit["bundle_location"]["path"], str(f.bundle))
        self.assertEqual(commit["claim_ceiling"], K.ceiling())
        self.assertNotIn("verification", self.proposal)  # no circular publication field
        self.assertEqual(set(f.docs.iterdir()), set())
        self.assertEqual(f.bundle.stat().st_mode & 0o777, 0o700)
        self.assertTrue(
            all(p.stat().st_mode & 0o777 == 0o600 for p in f.bundle.iterdir())
        )
        self.assertEqual(result["effects"]["final_observation"], "COMPLETE")
        self.assertGreater(f.revalidate.call_count, 20)
        f.reconstructed.assert_called_once_with(P.CERTIFIER_REVISION)
        self.assertGreater(f.unused.call_count, 20)

    def test_foreign_bundle_and_dangling_link_never_adopted(self):
        for kind in ("directory", "dangling", "file"):
            with self.subTest(kind=kind):
                f = self.fixture()
                if kind == "directory":
                    f.bundle.mkdir()
                elif kind == "dangling":
                    f.bundle.symlink_to(f.root / "missing")
                else:
                    f.bundle.write_bytes(b"foreign")
                with self.assertRaises(P.PublicationFailure):
                    self.issue()
                f.reconstructed.assert_not_called()
                self.assertTrue(os.path.lexists(f.bundle))

    def test_each_promoted_mirror_blocks_before_reconstruction(self):
        for index in range(3):
            with self.subTest(index=index):
                f = self.fixture()
                P.MIRRORS[index].symlink_to(f.root / "missing")
                with self.assertRaises(P.PublicationFailure):
                    self.issue()
                self.assertFalse(f.bundle.exists())
                f.reconstructed.assert_not_called()

    def test_complete_byte_comparison_not_selected_fields(self):
        f = self.fixture()
        altered = copy.deepcopy(self.proposal)
        altered["receiver_identity"]["uuid_baseline_date"] = "2099-01-01"
        altered.pop("deterministic_digest")
        f.state.raw = P.canonical(P.digested(altered))
        with self.assertRaisesRegex(P.PublicationFailure, "entire reconstructed"):
            self.issue()
        self.assertFalse(f.bundle.exists())

    def test_reconstruct_returning_detached_bytes_or_unregistered_object_rejects(self):
        for value in (self.raw, self.proposal, object.__new__(K._LiveCapture)):
            f = self.fixture()
            f.reconstructed.side_effect = None
            f.reconstructed.return_value = value
            with (
                self.subTest(value=type(value)),
                self.assertRaisesRegex(P.PublicationFailure, "registered"),
            ):
                self.issue()
            self.assertFalse(f.bundle.exists())

    def test_reconstruction_failure_preserves_known_and_unknown_work(self):
        f = self.fixture()
        work = dict(P.N.initial_work(), baseline_traces_completed=32)
        work["public_archives"][0]["replayed_traces_completed"] = None
        f.reconstructed.side_effect = K.CertificateFailure(
            ValueError("MOCK computation failure"), "original_public", work
        )
        with self.assertRaises(P.PublicationFailure) as caught:
            self.issue()
        self.assertEqual(caught.exception.work, work)
        self.assertFalse(f.bundle.exists())

    def test_post_capture_drift_prevents_first_effect(self):
        f = self.fixture()
        f.revalidate.side_effect = ValueError("MOCK live evidence drift")
        with self.assertRaisesRegex(P.PublicationFailure, "live evidence drift"):
            self.issue()
        self.assertFalse(f.bundle.exists())

    def test_head_drift_prevents_creation(self):
        f = self.fixture()
        original = f.reconstructed.side_effect

        def reconstruct(revision):
            capture = original(revision)
            P.core.git_head.return_value = "c" * 40
            return capture

        f.reconstructed.side_effect = reconstruct
        with self.assertRaisesRegex(P.PublicationFailure, "HEAD changed"):
            self.issue()
        self.assertFalse(f.bundle.exists())

    def test_publisher_source_drift_prevents_creation(self):
        f = self.fixture()
        original = f.reconstructed.side_effect

        def reconstruct(revision):
            capture = original(revision)
            P.attest.return_value = dict(self.source, deterministic_digest="0" * 64)
            return capture

        f.reconstructed.side_effect = reconstruct
        with self.assertRaisesRegex(P.PublicationFailure, "source changed"):
            self.issue()
        self.assertFalse(f.bundle.exists())

    def test_missing_clean_checkout_rejects(self):
        f = self.fixture()
        P.core.git_bytes.return_value = b" M modified\n"
        with self.assertRaisesRegex(P.PublicationFailure, "clean"):
            self.issue()
        f.reconstructed.assert_not_called()
        self.assertFalse(f.bundle.exists())

    def test_source_drift_during_capture_revalidation_stops_same_check(self):
        f = self.fixture()

        def drift():
            P.attest.return_value = dict(self.source, deterministic_digest="0" * 64)

        f.revalidate.side_effect = drift
        with self.assertRaisesRegex(
            P.PublicationFailure, "source changed during live check"
        ):
            self.issue()
        self.assertFalse(f.bundle.exists())

    def test_actual_guard_rejects_storage_and_publisher_substitution(self):
        for module, name in (
            (P, "_commit"),
            (P._Transaction, "create_file"),
            (M, "_write_all"),
            (M, "_read_exact_pread"),
        ):
            with (
                self.subTest(name=name),
                patch.object(module, name, Mock()),
                self.assertRaisesRegex(Exception, "substituted"),
            ):
                P._guard()

    def test_modified_or_hardlinked_payload_rejects_without_cleanup(self):
        for kind in ("mode", "hardlink", "missing", "same_bytes_replaced"):
            with self.subTest(kind=kind):
                f = self.fixture()
                original = P._Transaction.create_file

                def create(tx, name, raw):
                    original(tx, name, raw)
                    if name != "certificate.json":
                        return
                    target = f.bundle / name
                    if kind == "mode":
                        target.chmod(0o644)
                    elif kind == "hardlink":
                        os.link(target, f.root / "external-link")
                    elif kind == "missing":
                        target.rename(f.root / "moved-file")
                    else:
                        target.rename(f.root / "moved-file")
                        target.write_bytes(raw)
                        target.chmod(0o600)

                with (
                    patch.object(P._Transaction, "create_file", create),
                    self.assertRaises(P.PublicationFailure),
                ):
                    self.issue()
                self.assertFalse((f.bundle / "COMMIT.json").exists())
                # Drop this fixture's synthetic capture before the next iteration.
                K._LIVE.pop(f.capture, None)

    def test_commit_partial_write_is_unknown_not_unpublished(self):
        f = self.fixture()
        original = M._write_all

        def write(fd, raw):
            if P.parse(raw)["schema_version"] == P.DOMAIN + "/commit":
                os.write(fd, raw[:13])
                raise OSError("MOCK partial COMMIT")
            original(fd, raw)

        with (
            patch.object(M, "_write_all", side_effect=write),
            self.assertRaises(P.PublicationFailure) as caught,
        ):
            self.issue()
        self.assertEqual((f.bundle / "COMMIT.json").stat().st_size, 13)
        receipt = P.failure_receipt(caught.exception)
        self.assertIsNone(receipt["certificate_issued"])
        self.assertIs(receipt["durable_commit_barriers_completed"], False)

    def test_commit_directory_fsync_uncertainty_retains_all_bytes(self):
        f = self.fixture()
        original = M._PinnedParent.fsync
        calls = []

        def sync(parent):
            if (f.bundle / "COMMIT.json").exists():
                calls.append(parent.path)
                raise OSError("MOCK commit directory barrier")
            original(parent)

        with (
            patch.object(M._PinnedParent, "fsync", sync),
            self.assertRaises(P.PublicationFailure) as caught,
        ):
            self.issue()
        receipt = P.failure_receipt(caught.exception)
        self.assertIsNone(receipt["certificate_issued"])
        self.assertEqual(calls, [f.bundle])
        self.assertEqual(
            caught.exception.effects["files"]["COMMIT.json"]["file_fsync"], "COMPLETE"
        )
        self.assertEqual(
            caught.exception.effects["files"]["COMMIT.json"]["directory_fsync"],
            "UNKNOWN_PARTIAL_OR_COMPLETE",
        )

    def test_closed_generated_commit_and_verification_fields(self):
        f = self.fixture()
        self.issue()
        verification = P.parse((f.bundle / "verification.json").read_bytes())
        commit = P.parse((f.bundle / "COMMIT.json").read_bytes())
        self.assertEqual(
            set(verification),
            set(
                "schema_version status scope operation_head publisher_source certifier_source receiver_identity reviewed_proposal proposal_review_revision proposal_review_records independently_reconstructed_certificate complete_canonical_certificate_byte_identical verification_method algorithmically_independent_implementation work original_study_slot_absent_at_verification certificate_issued_at_verification claim_ceiling deterministic_digest".split()
            ),
        )
        self.assertEqual(
            set(commit),
            set(
                "schema_version status scope operation_head publisher_source certifier_source reviewed_proposal_revision proposal_review_revision bundle_location payloads publication_order claim_ceiling deterministic_digest".split()
            ),
        )
        self.assertEqual(
            set(commit["bundle_location"]),
            {"path", "live_component_identities", "persistent_components"},
        )
        self.assertEqual(
            set(commit["payloads"]), {"certificate.json", "verification.json"}
        )
        for ref in commit["payloads"].values():
            self.assertEqual(set(ref), {"byte_count", "sha256", "deterministic_digest"})

    def test_creation_response_uncertainty_retains_directory(self):
        f = self.fixture()
        original = os.mkdir

        def mkdir(*args, **kwargs):
            original(*args, **kwargs)
            raise OSError("MOCK response lost after mkdir")

        with (
            patch.object(P.os, "mkdir", side_effect=mkdir),
            self.assertRaises(P.PublicationFailure) as caught,
        ):
            self.issue()
        self.assertTrue(f.bundle.is_dir())
        self.assertEqual(
            caught.exception.effects["mkdir"], "UNKNOWN_PARTIAL_OR_COMPLETE"
        )

    def test_creation_fsync_error_stops_without_reconciliation(self):
        f = self.fixture()
        with (
            patch.object(
                M._PinnedParent, "fsync", side_effect=OSError("MOCK fsync error")
            ) as sync,
            self.assertRaises(P.PublicationFailure) as caught,
        ):
            self.issue()
        self.assertEqual(sync.call_count, 1)
        self.assertEqual(list(f.bundle.iterdir()), [])
        self.assertEqual(
            caught.exception.effects["creation_parent_fsync"],
            "UNKNOWN_PARTIAL_OR_COMPLETE",
        )

    def test_short_write_error_preserves_partial_file_and_closes_descriptor(self):
        f = self.fixture()
        descriptors = []

        def write(fd, raw):
            descriptors.append(fd)
            os.write(fd, raw[:7])
            raise OSError("MOCK partial write")

        with (
            patch.object(M, "_write_all", side_effect=write),
            self.assertRaises(P.PublicationFailure) as caught,
        ):
            self.issue()
        self.assertEqual((f.bundle / "certificate.json").read_bytes(), self.raw[:7])
        self.assertFalse((f.bundle / "verification.json").exists())
        self.assertEqual(
            caught.exception.effects["files"]["certificate.json"]["write"],
            "UNKNOWN_PARTIAL_OR_COMPLETE",
        )
        for descriptor in descriptors:
            with self.assertRaises(OSError):
                os.fstat(descriptor)

    def test_file_fsync_error_has_no_retry_and_keeps_full_bytes(self):
        f = self.fixture()
        original = os.fsync
        calls = []

        def fsync(fd):
            if os.fstat(fd).st_mode & 0o170000 == 0o100000:
                calls.append(fd)
                raise OSError("MOCK file fsync error")
            original(fd)

        with (
            patch.object(P.os, "fsync", side_effect=fsync),
            self.assertRaises(P.PublicationFailure) as caught,
        ):
            self.issue()
        self.assertEqual(len(calls), 1)
        self.assertEqual((f.bundle / "certificate.json").read_bytes(), self.raw)
        self.assertEqual(
            caught.exception.effects["files"]["certificate.json"]["file_fsync"],
            "UNKNOWN_PARTIAL_OR_COMPLETE",
        )

    def test_extra_file_after_write_rejects_and_retains_it(self):
        f = self.fixture()
        original = M._write_all

        def write(fd, raw):
            original(fd, raw)
            (f.bundle / "foreign").write_bytes(b"x")

        with (
            patch.object(M, "_write_all", side_effect=write),
            self.assertRaises(P.PublicationFailure),
        ):
            self.issue()
        self.assertTrue((f.bundle / "foreign").exists())
        self.assertFalse((f.bundle / "COMMIT.json").exists())

    def test_bundle_replacement_is_not_adopted(self):
        f = self.fixture()
        original = M._write_all

        def write(fd, raw):
            original(fd, raw)
            f.bundle.rename(f.outer / "retained-original")
            f.bundle.mkdir(mode=0o700)

        with (
            patch.object(M, "_write_all", side_effect=write),
            self.assertRaises(P.PublicationFailure),
        ):
            self.issue()
        self.assertEqual(
            (f.outer / "retained-original" / "certificate.json").read_bytes(), self.raw
        )
        self.assertEqual(list(f.bundle.iterdir()), [])

    def test_committed_prefix_mutation_before_next_file_rejects(self):
        f = self.fixture()
        original = P._Transaction.create_file

        def create(tx, name, raw):
            original(tx, name, raw)
            if name == "certificate.json":
                (f.bundle / name).write_bytes(b"changed")

        with (
            patch.object(P._Transaction, "create_file", create),
            self.assertRaises(P.PublicationFailure),
        ):
            self.issue()
        self.assertFalse((f.bundle / "verification.json").exists())

    def test_final_failure_does_not_claim_complete_bundle_absent(self):
        f = self.fixture()
        original = P._Transaction.check

        def check(tx):
            original(tx)
            if tx.effects["final_observation"] == "UNKNOWN_PARTIAL_OR_COMPLETE":
                raise ValueError("MOCK final evidence drift")

        with (
            patch.object(P._Transaction, "check", check),
            self.assertRaises(P.PublicationFailure) as caught,
        ):
            self.issue()
        receipt = P.failure_receipt(caught.exception)
        self.assertEqual(set(p.name for p in f.bundle.iterdir()), set(P.NAMES))
        self.assertIsNone(receipt["certificate_issued"])
        self.assertIs(receipt["durable_commit_barriers_completed"], True)
        self.assertIs(receipt["automatic_retry_allowed"], False)

    def test_same_process_retry_after_failure_is_forbidden(self):
        f = self.fixture()
        f.reconstructed.side_effect = ValueError("MOCK failure")
        with self.assertRaises(P.PublicationFailure):
            self.issue()
        with self.assertRaisesRegex(P.PublicationFailure, "fresh process"):
            self.issue()
        self.assertEqual(f.reconstructed.call_count, 1)

    def test_same_process_retry_after_success_is_forbidden(self):
        f = self.fixture()
        self.issue()
        with self.assertRaisesRegex(P.PublicationFailure, "fresh process"):
            self.issue()
        self.assertEqual(f.reconstructed.call_count, 1)

    def test_delivery_failure_preserves_issued_state(self):
        f = self.fixture()
        result = self.issue()
        receipt = P.failure_receipt(
            OSError("MOCK stdout failure"), result, "UNKNOWN_PARTIAL_OR_COMPLETE"
        )
        self.assertIs(receipt["certificate_issued"], True)
        self.assertEqual(receipt["completed_operation"], result)
        self.assertTrue((f.bundle / "COMMIT.json").exists())

    def test_cli_static_self_test_outside_checkout(self):
        env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
        result = subprocess.run(
            [sys.executable, "-P", "-B", str(ROOT / P.SCRIPT), "--self-test"],
            cwd="/tmp",
            env=env,
            capture_output=True,
            check=True,
        )
        self.assertEqual(P.parse(result.stdout)["status"], "STATIC_SELF_TEST_ONLY")

    def test_cli_has_no_proof_path_resume_or_execution_override(self):
        for args in (
            ("--issue-certificate-only",),
            ("--self-test", "--implementation-revision", "a" * 40),
            ("--self",),
            ("--self-test", "--output", "/tmp/wrong"),
            ("--self-test", "--resume"),
            ("--self-test", "--execute"),
            ("--self-test", "--reviewed-proposal-revision", P.PROPOSAL_REVISION),
        ):
            with (
                self.subTest(args=args),
                patch.object(sys, "argv", [P.SCRIPT, *args]),
                patch.object(sys, "stderr", io.StringIO()),
                self.assertRaises(SystemExit),
            ):
                P.main()

    def test_cli_short_delivery_keeps_completed_result(self):
        f = self.fixture()
        out, err = SimpleNamespace(buffer=Mock()), SimpleNamespace(buffer=io.BytesIO())
        out.buffer.write.return_value = 1
        with (
            patch.object(
                sys,
                "argv",
                [
                    P.SCRIPT,
                    "--issue-certificate-only",
                    "--implementation-revision",
                    "a" * 40,
                ],
            ),
            patch.object(sys, "stdout", out),
            patch.object(sys, "stderr", err),
            self.assertRaises(SystemExit),
        ):
            P.main()
        result = P.parse(err.buffer.getvalue())
        self.assertIs(result["certificate_issued"], True)
        self.assertEqual(result["result_delivery"], "UNKNOWN_PARTIAL_OR_COMPLETE")
        self.assertTrue((f.bundle / "COMMIT.json").exists())

    def test_source_has_no_execution_bridge_cleanup_or_retry_calls(self):
        tree = ast.parse((ROOT / P.SCRIPT).read_text())
        names = {
            node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, (ast.Name, ast.Attribute))
        }
        self.assertFalse(
            names
            & {
                "unlink",
                "rmdir",
                "rmtree",
                "replace",
                "rename",
                "claim",
                "consume",
                "dispatch",
                "candidate",
                "verify_proposal",
                "_exclusive_create_exact",
                "_try_reconcile_created_file",
            }
        )
        self.assertEqual(
            sum(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "reconstruct"
                for node in ast.walk(tree)
            ),
            1,
        )


if __name__ == "__main__":
    unittest.main()
