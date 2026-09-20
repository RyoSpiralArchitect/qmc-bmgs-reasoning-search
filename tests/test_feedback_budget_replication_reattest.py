"""Receiver boundary tests. Synthetic transport/mocked admission is NOT qualification.

Only existing PUBLIC definitions or original sealed metadata are used. No new
cohort, replication search, provider call or consumed real-study claim occurs.
"""

from __future__ import annotations

import ast
import copy
from dataclasses import FrozenInstanceError
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
    "replication_reattest_tested",
    ROOT / "scripts/feedback_budget_replication_reattest.py",
)
assert SPEC is not None and SPEC.loader is not None
B = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = B
SPEC.loader.exec_module(B)
R, S = B.R, B.S


def rehash(value):
    return B.digested(B.without_digest(value))


def private_file(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    path.chmod(0o600)


class MappingTests(unittest.TestCase):
    def chains(self):
        def one(path, inodes):
            return (
                {"path": path, "identities": [[19, inode] for inode in inodes]},
                {"path": path, "identities": [[17, inode] for inode in inodes]},
            )

        return [
            ("replication", *one("/a/b", [2, 3, 4])),
            ("public_parent", *one("/a/b", [2, 3, 4])),
            ("public", *one("/a/b/c", [2, 3, 4, 5])),
        ]

    def test_exact_uniform_mapping_is_not_physical_causality(self):
        value = B.mapping(self.chains())
        self.assertEqual(
            (value["historical_device"], value["current_device"]), (19, 17)
        )
        self.assertIs(value["physical_disk_identity_proven"], False)
        self.assertIs(value["reboot_causality_proven"], False)

    def test_closed_components_aliases_and_consistency(self):
        mutations = (
            lambda c: c.pop(),
            lambda c: c[0][1]["identities"].pop(),
            lambda c: c[0][2]["identities"].pop(),
            lambda c: c[0][2]["identities"][0].__setitem__(1, 99),
            lambda c: c[0][2]["identities"][0].__setitem__(0, 18),
            lambda c: c[0][2]["identities"][0].__setitem__(0, True),
            lambda c: c[0][1]["identities"][0].__setitem__(1, True),
            lambda c: c[0][1]["identities"][0].append(0),
            lambda c: c[0][2].__setitem__("path", "/a/x"),
            lambda c: (
                c[0][1].__setitem__("path", "/a/../b"),
                c[0][2].__setitem__("path", "/a/../b"),
            ),
            lambda c: (
                c[0][1]["identities"][1].__setitem__(1, 100),
                c[0][2]["identities"][1].__setitem__(1, 100),
            ),
        )
        for mutate in mutations:
            value = self.chains()
            mutate(value)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                B.mapping(value)

    def test_no_implicit_noop_mapping(self):
        chains = self.chains()
        for _, before, after in chains:
            after["identities"] = copy.deepcopy(before["identities"])
        with self.assertRaisesRegex(ValueError, "transition"):
            B.mapping(chains)


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.archive = self.root / "archive"
        self.archive.mkdir(mode=0o700)
        self.file = self.archive / "STARTED.json"
        private_file(self.file, b"{}\n")
        self.names = {"STARTED.json"}

    def tearDown(self):
        self.temp.cleanup()

    def test_private_regular_closed_archive_and_readonly_bytes(self):
        value = B.Archive(self.archive, self.names)
        value.revalidate()
        with self.assertRaises(TypeError):
            value.raw["STARTED.json"] = b"other"

    def test_extra_missing_hardlink_symlink_and_public_directory(self):
        def check():
            with self.assertRaises(
                (ValueError, OSError, S.mechanics.RegularFilePublicationV2Error)
            ):
                B.Archive(self.archive, self.names)

        extra = self.archive / "extra"
        private_file(extra, b"extra")
        check()
        extra.unlink()
        self.file.unlink()
        check()
        target = self.root / "target"
        private_file(target, b"{}\n")
        self.file.symlink_to(target)
        check()
        self.file.unlink()
        os.link(target, self.file)
        check()
        self.file.unlink()
        private_file(self.file, b"{}\n")
        self.archive.chmod(0o755)
        check()

    def test_rebinding_and_byte_changes_after_capture_reject(self):
        value = B.Archive(self.archive, self.names)
        private_file(self.file, b'{"changed":true}\n')
        with self.assertRaises(ValueError):
            value.revalidate()
        value = B.Archive(self.archive, self.names)
        old = self.root / "old"
        self.archive.rename(old)
        self.archive.mkdir(mode=0o700)
        private_file(self.file, b'{"changed":true}\n')
        with self.assertRaisesRegex(ValueError, "identity"):
            value.revalidate()

    def test_identity_binding_allows_expected_children_but_not_remount(self):
        value = B.directory_binding(self.archive, private=True)
        private_file(self.archive / "claim.json", b"{}\n")
        self.assertEqual(value, B.directory_binding(self.archive, private=True))
        changed = copy.deepcopy(value)
        changed["identities"][-1][0] += 1
        self.assertNotEqual(B.canonical(value), B.canonical(changed))

    def test_symlink_ancestor_and_foreign_owner_reject(self):
        alias = self.root / "alias"
        alias.symlink_to(self.archive, target_is_directory=True)
        with self.assertRaises(
            (ValueError, OSError, S.mechanics.RegularFilePublicationV2Error)
        ):
            B.Archive(alias, self.names)
        with (
            patch.object(S.base.storage.os, "geteuid", return_value=os.geteuid() + 1),
            self.assertRaises(ValueError),
        ):
            B.Archive(self.archive, self.names)

    def test_file_modes_and_byte_caps_are_not_relaxed(self):
        self.file.chmod(0o644)
        with self.assertRaises(S.mechanics.RegularFilePublicationV2Error):
            B.Archive(self.archive, self.names)
        self.file.chmod(0o600)
        with (
            patch.object(S.base, "MAX_CONTROL_BYTES", 2),
            self.assertRaises(S.mechanics.RegularFilePublicationV2Error),
        ):
            B.Archive(self.archive, self.names)
        with patch.object(S.base, "MAX_TOTAL_BYTES", 2), self.assertRaises(ValueError):
            B.Archive(self.archive, self.names)


class InputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seal = B.parse((ROOT / B.SEAL_MIRROR / "preregistration.json").read_bytes())
        cls.original = B.parse((ROOT / B.ORIGINAL_CANDIDATE).read_bytes())

    def test_projection_matches_original_candidate_without_generation(self):
        with (
            patch.object(B.M, "_cohort", side_effect=AssertionError("generation")),
            patch.object(
                B.q,
                "run_countdown_track_a_search",
                side_effect=AssertionError("search"),
            ),
        ):
            value = B.input_projection(self.seal)
        self.assertEqual(
            value["deterministic_digest"], self.original["input_manifest_digest"]
        )
        self.assertEqual(value["schedule_digest"], self.original["schedule_digest"])
        self.assertEqual(value["cohort_seal"], self.original["cohort_seal"])

    def test_detached_values_frozen_storage_and_complete_cells(self):
        inputs = B.VerifiedInputs(B.canonical(B.input_projection(self.seal)))
        original_target = inputs.arguments(inputs.cells[0])["task"].target
        detached = inputs.manifest
        detached["tasks"][0]["target"] += 1
        self.assertEqual(
            inputs.arguments(inputs.cells[0])["task"].target, original_target
        )
        with self.assertRaises(FrozenInstanceError):
            inputs.raw = b"{}\n"
        for key, value in (
            ("cell_index", True),
            ("cell_index", -1),
            ("cell_index", 1024),
            ("cell_id", "e" * 64),
            ("extra", 1),
        ):
            cell = {**inputs.cells[0], key: value}
            with self.subTest(key=key), self.assertRaises(ValueError):
                inputs.arguments(cell)

    def test_cli_static_checks_from_outside_checkout(self):
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
        result = subprocess.run(
            [sys.executable, "-P", "-B", str(ROOT / B.SCRIPT), "--self-test"],
            cwd="/tmp",
            env=env,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertFalse(B.parse(result.stdout)["replication_execution_authorized"])

    def test_cli_rejects_extras_and_abbreviations(self):
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
        for args in (
            ("--self-test", "--summary", "unused"),
            ("--run-replication",),
            ("--pre",),
        ):
            with self.subTest(args=args):
                result = subprocess.run(
                    [sys.executable, "-P", "-B", str(ROOT / B.SCRIPT), *args],
                    cwd="/tmp",
                    env=env,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 2)

    def test_no_old_admission_construction_or_qualifier_substitution(self):
        tree = ast.parse((ROOT / B.SCRIPT).read_text())
        forbidden = {
            "R.admit",
            "R.Admission",
            "R.Inputs",
            "M.load_seal",
            "M.SealedInputs",
            "M.verify_generation_reference",
            "R.qualified_public",
            "M.validate_seal_bytes",
        }
        calls = {
            ast.unparse(node.func)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
        }
        self.assertFalse(calls & forbidden)
        assignments = [
            ast.unparse(node)
            for node in ast.walk(tree)
            if isinstance(node, (ast.Assign, ast.AugAssign))
        ]
        self.assertFalse(
            any(text.startswith(("R.", "M.", "S.")) for text in assignments)
        )

    def test_completed_operation_stdout_failure_never_becomes_not_run(self):
        stdout = Mock()
        stdout.write.side_effect = BrokenPipeError("injected closed output")
        cases = (
            (
                ["--prepare", "--implementation-revision", "f" * 40],
                "prepare",
                {"deterministic_digest": "a" * 64, "receiver_certificate": {}},
                False,
            ),
            (
                [
                    "--run-replication",
                    "--authorization",
                    "unused",
                    "--certificate",
                    "unused",
                    "--confirm-digest",
                    "a" * 64,
                    "--reviewed-revision",
                    "f" * 40,
                ],
                "run",
                {"status": "CONNECTOR_MATRIX_COMMITTED"},
                True,
            ),
        )
        for args, method, result, consumed in cases:
            stderr = io.StringIO()
            with (
                self.subTest(method=method),
                patch.object(sys, "argv", [B.SCRIPT, *args]),
                patch.object(sys, "stdout", stdout),
                patch.object(sys, "stderr", stderr),
                patch.object(B, method, return_value=result),
            ):
                self.assertEqual(B.main(), 1)
            failure = B.parse(stderr.getvalue().encode())
            self.assertEqual(failure["status"], "RESULT_DELIVERY_UNCERTAIN")
            self.assertTrue(failure["operation_completed"])
            self.assertIs(failure["authorization_consumed"], consumed)


class TransportFixture(unittest.TestCase):
    """Closed 1,024-envelope fixture, explicitly NOT a numerical PUBLIC run."""

    @classmethod
    def setUpClass(cls):
        cls.real_original = B.parse((ROOT / B.ORIGINAL_CANDIDATE).read_bytes())
        cls.seal_raw = {
            name: (ROOT / B.SEAL_MIRROR / name).read_bytes() for name in B.M.NAMES
        }
        cls.public_inputs = R.load_inputs(S.PUBLIC)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.output, self.public_output = (
            self.root / "replication",
            self.root / "public",
        )
        self.cohort, self.ledger = self.root / "cohort", self.root / "ledger"
        for path in (self.public_output, self.cohort, self.ledger):
            path.mkdir(mode=0o700)
        self.patches = [
            patch.object(B, "ROOT", self.root),
            patch.object(B, "OUTPUT", self.output),
            patch.object(B, "PUBLIC_OUTPUT", self.public_output),
            patch.object(S, "LEDGER", self.ledger),
            patch.object(B.M, "COHORT_PATH", self.cohort),
            patch.object(B, "ORIGINAL_RAW", self.root / "original.json"),
            patch.object(
                R, "reviewed_file", side_effect=lambda item, revision: item.revalidate()
            ),
        ]
        for item in self.patches:
            item.start()
        env = {
            key: self.real_original[key]
            for key in (
                "source",
                "runtime",
                "baseline",
                "authorities",
                "admission_proof",
            )
        }

        def historic(parent):
            value = copy.deepcopy(parent)
            for identity in value["identities"]:
                identity[0] += 100
            return rehash(value)

        public_auth = R.candidate(self.public_inputs, self.public_output, env, None)
        public_auth = rehash(
            {**public_auth, "output_parent": historic(public_auth["output_parent"])}
        )
        auth_path = self.root / "public-auth.json"
        private_file(auth_path, B.canonical(public_auth))
        self.claim = S.claim_value(
            public_auth, B.ORIGINAL_SOURCE, B.ORIGINAL_SOURCE, "e" * 64
        )
        private_file(S.claim_path(public_auth), B.canonical(self.claim))
        self.binding = S.frozen_binding(
            B.digested(
                dict(
                    schema_version=S.DOMAIN + "/run-binding",
                    execution_mode=S.PUBLIC,
                    experiment_id=S.PUBLIC_ID,
                    input_manifest_digest=self.public_inputs.manifest[
                        "deterministic_digest"
                    ],
                    authorization=public_auth,
                    authorization_path=str(auth_path),
                    reviewed_revision=B.ORIGINAL_SOURCE,
                    execution_head_revision=B.ORIGINAL_SOURCE,
                    claim=self.claim,
                    replication_execution_authorized=False,
                )
            )
        )
        identities = B.directory_binding(self.public_output)["identities"]
        for identity in identities:
            identity[0] += 100
        started = B.digested(
            dict(
                schema_version=S.DOMAIN + "/started",
                binding=self.binding,
                output_path=str(self.public_output),
                directory_identities=identities,
            )
        )
        started_raw = B.canonical(started)
        private_file(self.public_output / "STARTED.json", started_raw)
        receipt_raw = B.canonical(
            B.digested(
                dict(
                    schema_version=S.DOMAIN + "/execution-receipt",
                    execution_mode=S.PUBLIC,
                    run_binding_digest=self.binding["deterministic_digest"],
                    fixture_only_not_qualified=True,
                )
            )
        )
        private_file(self.public_output / "RECEIPT.json", receipt_raw)
        entries = []
        for cell, name in zip(self.public_inputs.cells, S.base.CELL_NAMES):
            raw = B.canonical(
                B.digested(
                    dict(
                        schema_version=S.DOMAIN + "/record",
                        **cell,
                        run_binding_digest=self.binding["deterministic_digest"],
                        search_record={"fixture_only_not_qualified": True},
                    )
                )
            )
            private_file(self.public_output / name, raw)
            entries.append(
                dict(
                    cell_index=cell["cell_index"],
                    filename=name,
                    byte_count=len(raw),
                    sha256=B.sha(raw),
                )
            )
        commit = S.commit_value(self.binding, started_raw, receipt_raw, entries)
        private_file(self.public_output / "COMMIT.json", B.canonical(commit))
        private_file(self.root / B.PUBLIC_COMMIT, B.canonical(commit))
        summary = B.digested(
            dict(
                output_path=str(self.public_output),
                execution_commit_digest=commit["deterministic_digest"],
                environment=env,
            )
        )
        private_file(self.root / B.PUBLIC_SUMMARY, B.canonical(summary))
        original = rehash(
            {
                **self.real_original,
                "output_path": str(self.output),
                "output_parent": historic(S.parent_binding(self.output)),
            }
        )
        self.original = original
        item = patch.object(B, "ORIGINAL_DIGEST", original["deterministic_digest"])
        item.start()
        self.patches.append(item)
        for path in (self.root / B.ORIGINAL_CANDIDATE, B.ORIGINAL_RAW):
            private_file(path, B.canonical(original))
        for name, raw in self.seal_raw.items():
            private_file(self.cohort / name, raw)
            private_file(self.root / B.SEAL_MIRROR / name, raw)

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def test_complete_content_import_is_not_replay_or_generation(self):
        with (
            patch.object(R, "environment") as environment,
            patch.object(R, "reduce_rows") as replay,
            patch.object(B.M, "_cohort") as generator,
        ):
            value = B.inspect_transport()
            value.revalidate()
        environment.assert_not_called()
        replay.assert_not_called()
        generator.assert_not_called()
        self.assertEqual(len(value.public.raw), 1027)

    def test_changed_final_cell_rejects_before_environment(self):
        path = self.public_output / S.base.CELL_NAMES[-1]
        row = B.parse(path.read_bytes())
        private_file(
            path, B.canonical(rehash({**row, "search_record": {"changed": True}}))
        )
        with (
            patch.object(R, "environment") as environment,
            patch.object(R, "reduce_rows") as replay,
            self.assertRaisesRegex(ValueError, "closure"),
        ):
            B.reconstruct("f" * 40)
        environment.assert_not_called()
        replay.assert_not_called()

    def test_changed_started_reference_is_not_dereferenced_before_anchor(self):
        path = self.public_output / "STARTED.json"
        started = B.parse(path.read_bytes())
        forbidden = self.root / "must-not-read.json"
        started["binding"] = rehash(
            {**started["binding"], "authorization_path": str(forbidden)}
        )
        private_file(path, B.canonical(rehash(started)))
        capture = R.snapshot_file

        def guarded_snapshot(path):
            self.assertNotEqual(Path(path), forbidden)
            return capture(path)

        with (
            patch.object(R, "snapshot_file", side_effect=guarded_snapshot),
            patch.object(S, "inspect_claim") as claim,
            patch.object(R, "environment") as environment,
            self.assertRaisesRegex(ValueError, "STARTED hash.*before reference"),
        ):
            B.inspect_transport()
        claim.assert_not_called()
        environment.assert_not_called()

    def test_immutable_source_seal_and_current_identity_changes_reject(self):
        value = B.inspect_transport()
        old = self.cohort / "SEALED.json"
        private_file(old, old.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            value.revalidate()

    def test_spent_before_preparation_candidate_verification_or_run(self):
        private_file(B.fixed_claim(), b"uncertain retained claim")
        with (
            patch.object(B, "reconstruct") as reconstruction,
            patch.object(B, "admit") as admission,
        ):
            for action in (
                lambda: B.prepare("f" * 40),
                lambda: B.verify_candidate("invalid", "invalid", "0" * 64, "f" * 40),
                lambda: B.run("invalid", "invalid", "0" * 64, "f" * 40),
            ):
                with self.assertRaises(S.ExecutionFailure) as caught:
                    action()
                self.assertEqual(caught.exception.status, "AUTHORIZATION_ALREADY_SPENT")
            reconstruction.assert_not_called()
            admission.assert_not_called()

    def test_certificate_difference_rejects_before_qualification_and_generator(self):
        transport = B.inspect_transport()
        source = {"implementation_revision": "f" * 40}
        certificate = B.certificate_projection(transport, source)
        for mutate in (
            lambda c: c["current_locations"]["ledger"]["identities"][-1].__setitem__(
                1, 99
            ),
            lambda c: c["public_verification"].__setitem__(
                "original_traces_replayed", True
            ),
            lambda c: c["source"].__setitem__("implementation_revision", "e" * 40),
            lambda c: c["public_verification"]["reference"].__setitem__(
                "summary_digest", "0" * 64
            ),
        ):
            value = copy.deepcopy(certificate)
            mutate(value)
            with (
                patch.object(B, "inspect_transport", return_value=transport),
                patch.object(B, "attest", return_value=source),
                patch.object(R, "environment") as environment,
                patch.object(B.M, "_cohort") as generator,
                self.assertRaisesRegex(ValueError, "before qualification"),
            ):
                B.reconstruct("f" * 40, expected=B.canonical(rehash(value)))
            environment.assert_not_called()
            generator.assert_not_called()

    def test_new_candidate_preserves_science_and_old_runner_rejects_it(self):
        transport = B.inspect_transport()
        cert = B.certificate_projection(
            transport, {"implementation_revision": "f" * 40}
        )
        value = B.candidate_projection(transport.original, cert)
        B.auth_shape(B.canonical(value), value["deterministic_digest"])
        for key in self.original:
            if key not in ("schema_version", "output_parent", "deterministic_digest"):
                self.assertEqual(
                    B.canonical(value[key]), B.canonical(self.original[key]), key
                )
        with self.assertRaisesRegex(ValueError, "domain"):
            R.auth_shape(
                B.canonical(value), S.REPLICATION, value["deterministic_digest"]
            )
        self.assertEqual(S.claim_path(value), B.fixed_claim())
        for changed in (True, "replacement", "0" * 64):
            self.assertEqual(
                S.claim_path({**value, "deterministic_digest": changed}),
                B.fixed_claim(),
            )

    def test_candidate_flags_extra_fields_and_wrong_confirmation_reject(self):
        transport = B.inspect_transport()
        cert = B.certificate_projection(
            transport, {"implementation_revision": "f" * 40}
        )
        auth = B.candidate_projection(transport.original, cert)
        for field, value in (
            ("schema_version", S.DOMAIN + "/authorization-candidate"),
            ("candidate_is_execution_authority", True),
            ("expected_cell_count", True),
            ("execution_mode", S.PUBLIC),
            ("output_path", str(self.root / "retry")),
            ("extra", False),
        ):
            changed = rehash({**auth, field: value})
            with self.subTest(field=field), self.assertRaises(ValueError):
                B.auth_shape(B.canonical(changed), changed["deterministic_digest"])
        with self.assertRaisesRegex(ValueError, "digest"):
            B.auth_shape(B.canonical(auth), "0" * 64)

    def test_admit_does_not_accept_arbitrary_objects_or_aliases(self):
        with patch.object(B, "reconstruct") as reconstruction:
            for first, second in (
                (SimpleNamespace(), SimpleNamespace()),
                (self.root / "alias.json", self.root / B.CERTIFICATE),
            ):
                with self.assertRaises((TypeError, ValueError)):
                    B.admit(first, second, "0" * 64, "f" * 40)
            reconstruction.assert_not_called()

    def test_parent_children_may_change_but_archive_may_not(self):
        transport = B.inspect_transport()
        cert_before = B.certificate_projection(transport, {})
        private_file(B.fixed_claim(), b"expected consumption fixture")
        self.output.mkdir(mode=0o700)
        transport.revalidate()
        self.assertEqual(
            B.canonical(cert_before),
            B.canonical(B.certificate_projection(transport, {})),
        )

    def test_old_claim_or_public_authorization_changes_reject(self):
        path = S.claim_path(self.binding["authorization"])
        private_file(path, B.canonical(rehash({**self.claim, "owner_nonce": "0" * 64})))
        with self.assertRaisesRegex(ValueError, "claim"):
            B.inspect_transport()

    def promoted_fixture(self):
        transport = B.inspect_transport()
        certificate = B.certificate_projection(
            transport, {"implementation_revision": "f" * 40}
        )
        auth = B.candidate_projection(transport.original, certificate)
        auth_path, cert_path = self.root / B.CANDIDATE, self.root / B.CERTIFICATE
        private_file(auth_path, B.canonical(auth))
        private_file(cert_path, B.canonical(certificate))
        private_file(
            self.root / B.BUNDLE_COMMIT,
            B.canonical(B.bundle_commit(B.canonical(certificate), B.canonical(auth))),
        )
        return transport, certificate, auth, auth_path, cert_path

    def test_unreviewed_bytes_reject_before_any_reconstruction(self):
        _, _, auth, auth_path, cert_path = self.promoted_fixture()
        with (
            patch.object(R, "oid", side_effect=lambda x: x),
            patch.object(B.core, "git_head", return_value="f" * 40),
            patch.object(B.core, "require_ancestor"),
            patch.object(R, "reviewed_file", side_effect=ValueError("not reviewed")),
            patch.object(B, "reconstruct") as reconstruct,
            self.assertRaisesRegex(ValueError, "not reviewed"),
        ):
            B.admit(auth_path, cert_path, auth["deterministic_digest"], "f" * 40)
        reconstruct.assert_not_called()

    def test_bundle_or_candidate_reference_tamper_rejects_before_reconstruction(self):
        _, certificate, auth, auth_path, cert_path = self.promoted_fixture()
        for field, value in (
            ("input_manifest_digest", "0" * 64),
            ("receiver_certificate", {"path": "wrong"}),
        ):
            changed = rehash({**auth, field: value})
            private_file(auth_path, B.canonical(changed))
            private_file(
                self.root / B.BUNDLE_COMMIT,
                B.canonical(
                    B.bundle_commit(B.canonical(certificate), B.canonical(changed))
                ),
            )
            with (
                patch.object(R, "oid", side_effect=lambda x: x),
                patch.object(B.core, "git_head", return_value="f" * 40),
                patch.object(B.core, "require_ancestor"),
                patch.object(B, "reconstruct") as reconstruct,
                self.assertRaisesRegex(ValueError, "before qualification"),
            ):
                B.admit(auth_path, cert_path, changed["deterministic_digest"], "f" * 40)
            reconstruct.assert_not_called()

    def test_run_consumes_fixed_claim_before_action_and_retains_failure(self):
        _, _, auth, auth_path, cert_path = self.promoted_fixture()
        admitted = SimpleNamespace(
            auth=auth,
            reviewed="f" * 40,
            head="f" * 40,
            snapshots=(SimpleNamespace(path=auth_path),),
            inputs=SimpleNamespace(cells=[{"cell_index": 0}]),
            revalidate=Mock(),
        )
        checkpoints = []

        def publisher(output, binding, action, check):
            self.assertTrue(B.fixed_claim().exists())
            checkpoints.append("claimed")
            check()
            return action(lambda index, row: None)

        def stopped_record(inputs, cell, binding):
            self.assertEqual(checkpoints, ["claimed"])
            raise RuntimeError("injected stop before any actual search")

        with (
            patch.object(B, "admit", return_value=admitted),
            patch.object(S, "publish", side_effect=publisher),
            patch.object(R, "record", side_effect=stopped_record),
            self.assertRaises(S.ExecutionFailure) as caught,
        ):
            B.run(auth_path, cert_path, auth["deterministic_digest"], "f" * 40)
        self.assertEqual(caught.exception.status, "SPENT_NOT_RUN")
        self.assertTrue(caught.exception.authorization_consumed)
        self.assertTrue(B.fixed_claim().is_file())
        with (
            patch.object(B, "admit") as admission,
            self.assertRaises(S.ExecutionFailure),
        ):
            B.run(auth_path, cert_path, auth["deterministic_digest"], "f" * 40)
        admission.assert_not_called()

    def test_post_consumption_analysis_uses_exact_claim_not_absence(self):
        _, certificate, auth, auth_path, _ = self.promoted_fixture()
        admitted = SimpleNamespace(
            auth=auth,
            reviewed="f" * 40,
            head="f" * 40,
            snapshots=(SimpleNamespace(path=auth_path),),
            inputs=SimpleNamespace(
                manifest={"deterministic_digest": auth["input_manifest_digest"]}
            ),
            proof=SimpleNamespace(
                source_raw=B.canonical(certificate["source"]), environment_raw=b"{}\n"
            ),
            revalidate=Mock(),
        )
        claim, _ = S.consume(
            auth, admitted.reviewed, admitted.head, B.core.FileSnapshot
        )
        binding = B.run_binding(admitted, claim)
        receipt = B.digested(
            dict(
                integrity={},
                reduction={},
                replication_cells_executed=1024,
                scientific_decision="STOP_REPAIR_REPLICATION_SCREEN_NOT_MET",
            )
        )
        publication = SimpleNamespace(
            binding=binding,
            rows=[],
            receipt=receipt,
            commit={"deterministic_digest": "a" * 64},
            revalidate=Mock(),
        )
        with (
            patch.object(S, "inspect", return_value=publication),
            patch.object(B, "admit", return_value=admitted),
            patch.object(R, "reduce_rows", return_value=receipt),
            patch.object(
                B,
                "unused",
                side_effect=AssertionError("analysis must not require absence"),
            ),
        ):
            summary, check = B.analyze()
            check()
        self.assertTrue(summary["authorization_consumed"])
        self.assertEqual(summary["scientific_decision"], receipt["scientific_decision"])
        private_file(
            B.fixed_claim(), B.canonical(rehash({**claim, "owner_nonce": "0" * 64}))
        )
        with (
            patch.object(S, "inspect", return_value=publication),
            patch.object(B, "admit") as admission,
            self.assertRaisesRegex(ValueError, "claim"),
        ):
            B.analyze()
        admission.assert_not_called()

    def test_complete_original_summary_including_negative_decision_is_compared(self):
        transport = B.inspect_transport()
        env = {
            key: self.original[key]
            for key in (
                "source",
                "runtime",
                "baseline",
                "authorities",
                "admission_proof",
            )
        }
        receipt = {
            "deterministic_digest": "e" * 64,
            "integrity": {"cell_count": 1024},
            "reduction": {"exact_success": {"screen_conjunction": False}},
        }
        value = B.original_summary(transport, self.public_inputs, env, receipt)
        self.assertIsNone(value["scientific_decision"])
        self.assertEqual(value["replication_cells_executed"], 0)
        self.assertFalse(value["replication_execution_authorized"])
        self.assertFalse(value["reduction"]["exact_success"]["screen_conjunction"])
