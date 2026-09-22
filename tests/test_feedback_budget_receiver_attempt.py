"""Synthetic fixed-attempt mechanics; no real ledger, search or qualification."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from qmc_bmgs.experiments.countdown_thompson_dense_scale_core import FileSnapshot


ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


A = load("receiver_attempt_tested", "scripts/feedback_budget_receiver_attempt.py")
S = load(
    "receiver_attempt_storage_tested",
    "scripts/feedback_budget_replication_execution_storage.py",
)


def rehash(value):
    return S.digested({k: v for k, v in value.items() if k != "deterministic_digest"})


class AttemptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.patch = patch.object(S, "LEDGER", self.root / "ledger")
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.auth = S.digested(
            dict(execution_mode=S.PUBLIC, output_path=str(self.root / "out"))
        )
        self.args = dict(
            domain="synthetic-receiver/v1",
            attempt_id="fixed-public-fixture/v1",
            authorization=self.auth,
            reviewed="a" * 40,
            execution_head="b" * 40,
            snapshot_type=FileSnapshot,
        )
        self.path = S.LEDGER / (
            "receiver-public-"
            + S.digest([self.args["domain"], self.args["attempt_id"]])
            + ".json"
        )

    def consume(self, **changes):
        return A.consume(S, self.path, **{**self.args, **changes})

    def inspect(self, **changes):
        return A.inspect(S, self.path, **{**self.args, **changes})

    def test_consumed_before_secondary_claim_and_output(self):
        A.ensure_unused(S, self.path)
        value, snapshot = self.consume()
        self.assertEqual(set(value), A.FIELDS)
        self.assertEqual(snapshot.raw, S.canonical(value))
        self.assertEqual(self.inspect().raw, snapshot.raw)
        self.assertFalse(S.claim_path(self.auth).exists())
        self.assertFalse((self.root / "out").exists())
        self.assertEqual(S.LEDGER.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertTrue(value["irreversible"])
        self.assertEqual(
            value["owner_nonce"],
            S.digest(
                [
                    self.args["domain"] + "/public-attempt-nonce",
                    self.args["attempt_id"],
                    self.auth["deterministic_digest"],
                    self.args["reviewed"],
                    self.args["execution_head"],
                ]
            ),
        )
        with self.assertRaises(S.ExecutionFailure) as caught:
            self.consume()
        self.assertEqual(caught.exception.status, "AUTHORIZATION_ALREADY_SPENT")
        self.assertIs(caught.exception.authorization_consumed, True)

    def test_changed_candidate_source_and_revisions_cannot_reopen_attempt(self):
        _, snapshot = self.consume()
        changed = rehash({**self.auth, "source": "replacement"})
        self.assertNotEqual(S.claim_path(changed), S.claim_path(self.auth))
        with self.assertRaises(S.ExecutionFailure) as caught:
            self.consume(authorization=changed, reviewed="c" * 40)
        self.assertEqual(caught.exception.status, "AUTHORIZATION_ALREADY_SPENT")
        self.assertEqual(self.path.read_bytes(), snapshot.raw)

    def test_secondary_failure_preserves_attempt_and_blocks_later_auth(self):
        _, snapshot = self.consume()
        with patch.object(S, "consume", side_effect=OSError("secondary failure")):
            with self.assertRaises(OSError):
                S.consume(self.auth, "a" * 40, "b" * 40, FileSnapshot)
        self.assertEqual(self.path.read_bytes(), snapshot.raw)
        with self.assertRaises(S.ExecutionFailure):
            self.consume(authorization=rehash({**self.auth, "source": "new"}))

    def test_occupied_nonfiles_and_dangling_symlinks_are_spent(self):
        S.LEDGER.mkdir(mode=0o700)
        for name in ("directory", "symlink", "file"):
            with self.subTest(kind=name):
                path = S.LEDGER / ("receiver-public-" + S.digest([name]) + ".json")
                if name == "directory":
                    path.mkdir(mode=0o700)
                elif name == "symlink":
                    path.symlink_to(self.root / "absent")
                else:
                    path.write_bytes(b"partial")
                with self.assertRaises(S.ExecutionFailure) as caught:
                    A.ensure_unused(S, path)
                self.assertEqual(caught.exception.status, "AUTHORIZATION_ALREADY_SPENT")
                with self.assertRaises(S.ExecutionFailure):
                    A.consume(S, path, **self.args)
                self.assertTrue(os.path.lexists(path))

    def test_wrong_modes_or_invalid_refs_reject_before_ledger_creation(self):
        for changes in (
            {"authorization": rehash({**self.auth, "execution_mode": S.REPLICATION})},
            {
                "authorization": rehash(
                    {**self.auth, "replication_execution_authorized": True}
                )
            },
            {"authorization": {**self.auth, "deterministic_digest": "0" * 64}},
            {"authorization": rehash({**self.auth, "output_path": "relative"})},
            {"authorization": rehash({**self.auth, "output_path": "/a/../b"})},
            {"reviewed": True},
            {"execution_head": "f" * 39},
            {"domain": ""},
            {"attempt_id": False},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.consume(**changes)
            self.assertFalse(S.LEDGER.exists())

    def test_nonledger_and_reserved_claim_paths_reject_without_writes(self):
        for path in (
            self.root / self.path.name,
            S.LEDGER / "nested" / self.path.name,
            S.LEDGER / "replication-study.json",
            S.claim_path(self.auth),
            S.LEDGER / "receiver-public-.json",
            S.LEDGER / ("receiver-public-" + "f" * 64 + ".json"),
            Path("receiver-public-relative.json"),
        ):
            with self.subTest(path=path), self.assertRaises(ValueError):
                A.consume(S, path, **self.args)
        self.assertFalse(S.LEDGER.exists())

    def test_private_owned_ledger_required(self):
        S.LEDGER.mkdir(mode=0o755)
        S.LEDGER.chmod(0o755)
        with self.assertRaises(S.ExecutionFailure) as caught:
            self.consume()
        self.assertEqual(caught.exception.status, "NOT_RUN")
        self.assertIs(caught.exception.authorization_consumed, False)
        self.assertFalse(self.path.exists())

    def test_ledger_symlink_is_not_followed(self):
        target = self.root / "target"
        target.mkdir(mode=0o700)
        S.LEDGER.symlink_to(target, target_is_directory=True)
        with self.assertRaises(S.mechanics.RegularFilePublicationV2Error):
            self.consume()
        self.assertEqual(list(target.iterdir()), [])

    def test_exclusive_race_is_spent_and_foreign_bytes_retained(self):
        S.LEDGER.mkdir(mode=0o700)

        def raced(*args, **kwargs):
            self.path.write_bytes(b"foreign")
            raise S.mechanics._NameConflictError("raced")

        with patch.object(S.mechanics, "_exclusive_create_exact", side_effect=raced):
            with self.assertRaises(S.ExecutionFailure) as caught:
                self.consume()
        self.assertEqual(caught.exception.status, "AUTHORIZATION_ALREADY_SPENT")
        self.assertEqual(self.path.read_bytes(), b"foreign")

    def test_fsync_uncertainty_retains_fence(self):
        S.LEDGER.mkdir(mode=0o700)
        with patch.object(
            S.mechanics._PinnedParent, "fsync", side_effect=OSError("fsync")
        ):
            with self.assertRaises(S.ExecutionFailure) as caught:
                self.consume()
        self.assertEqual(caught.exception.status, "CONSUMPTION_UNCERTAIN")
        self.assertIsNone(caught.exception.authorization_consumed)
        self.assertTrue(self.path.is_file())
        with self.assertRaises(S.ExecutionFailure):
            self.consume()

    def test_ledger_creation_uncertainty_is_not_not_run(self):
        def uncertain(path):
            path.mkdir(mode=0o700)
            raise S.base.PublicationUncertain("creation uncertain")

        with patch.object(S.base.storage, "_create_directory", side_effect=uncertain):
            with self.assertRaises(S.ExecutionFailure) as caught:
                self.consume()
        self.assertEqual(caught.exception.status, "CONSUMPTION_UNCERTAIN")
        self.assertIsNone(caught.exception.authorization_consumed)
        self.assertTrue(S.LEDGER.is_dir())

    def test_failure_after_open_closes_descriptor_and_retains_file(self):
        S.LEDGER.mkdir(mode=0o700)
        create = S.mechanics._exclusive_create_exact
        captured = []

        def interrupted(*args, **kwargs):
            owned = create(*args, **kwargs)
            captured.append(owned.descriptor)
            raise S.mechanics._CreateAfterOpenError(
                "interrupted", owned=owned, cause=KeyboardInterrupt()
            )

        with patch.object(
            S.mechanics, "_exclusive_create_exact", side_effect=interrupted
        ):
            with self.assertRaises(S.ExecutionFailure) as caught:
                self.consume()
        self.assertEqual(caught.exception.status, "CONSUMPTION_UNCERTAIN")
        self.assertTrue(self.path.is_file())
        with self.assertRaises(OSError):
            os.fstat(captured[0])

    def test_inspection_references_and_closed_payload_are_exact(self):
        value, snapshot = self.consume()
        for changes in (
            {"domain": "different/v1"},
            {"attempt_id": "other/v1"},
            {"authorization": rehash({**self.auth, "source": "different"})},
            {"reviewed": "c" * 40},
            {"execution_head": "d" * 40},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.inspect(**changes)
        for changes in (
            {"extra": False},
            {"irreversible": 1},
            {"execution_mode": S.REPLICATION},
            {"owner_nonce": "not-a-sha"},
            {"owner_nonce": "0" * 64},
            {"output_path": str(self.root / "other")},
        ):
            self.path.write_bytes(S.canonical(rehash({**value, **changes})))
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.inspect()
        self.path.write_bytes(snapshot.raw)
        self.assertEqual(self.inspect().raw, snapshot.raw)

    def test_inspection_rejects_noncanonical_and_bad_digest_bytes(self):
        value, snapshot = self.consume()
        for raw in (
            snapshot.raw + b"\n",
            b"{}\n",
            S.canonical({**value, "deterministic_digest": "0" * 64}),
        ):
            self.path.write_bytes(raw)
            with self.subTest(raw_length=len(raw)), self.assertRaises(ValueError):
                self.inspect()

    def test_snapshot_failure_after_durable_write_remains_uncertain(self):
        with patch.object(FileSnapshot, "capture", side_effect=OSError("capture")):
            with self.assertRaises(S.ExecutionFailure) as caught:
                self.consume()
        self.assertEqual(caught.exception.status, "CONSUMPTION_UNCERTAIN")
        self.assertIsNone(caught.exception.authorization_consumed)
        self.assertTrue(self.path.is_file())
        with self.assertRaises(S.ExecutionFailure):
            self.consume()

    def test_inspection_rejects_hardlinks_permissions_and_symlinks(self):
        _, snapshot = self.consume()
        alias = self.root / "alias.json"
        os.link(self.path, alias)
        with self.assertRaises(S.mechanics.RegularFilePublicationV2Error):
            self.inspect()
        alias.unlink()
        self.path.chmod(0o644)
        with self.assertRaises(S.mechanics.RegularFilePublicationV2Error):
            self.inspect()
        self.path.chmod(0o600)
        self.path.rename(alias)
        self.path.symlink_to(alias)
        with self.assertRaises(S.mechanics.RegularFilePublicationV2Error):
            self.inspect()
        self.assertEqual(alias.read_bytes(), snapshot.raw)


if __name__ == "__main__":
    unittest.main()
