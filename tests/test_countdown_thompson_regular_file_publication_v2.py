from __future__ import annotations

import json
import errno
import multiprocessing
import os
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from qmc_bmgs.experiments import (
    countdown_thompson_regular_file_publication_v2 as publication,
)


AUTHORIZATION_A = "a" * 64
AUTHORIZATION_B = "b" * 64


def _race_worker(
    output: str,
    authorization: str,
    gate: multiprocessing.synchronize.Event,
    results: multiprocessing.queues.Queue,
) -> None:
    gate.wait()
    try:
        publication.publish_synthetic_fixture_v2(
            output,
            authorization_digest=authorization,
            fixture_action=lambda: [{"authorization": authorization}],
        )
    except publication.RegularFilePublicationV2NotRunError:
        results.put("NOT_RUN")
    except BaseException as error:
        results.put(type(error).__name__)
    else:
        results.put("COMMITTED")


class RegularFilePublicationV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix="qmc-bmgs-v2-test-",
            dir="/private/tmp" if Path("/private/tmp").is_dir() else None,
        )
        self.root = Path(self.temporary.name).resolve()
        self.output = self.root / "artifact.commit.json"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _publish(
        self,
        *,
        output: Path | None = None,
        authorization: str = AUTHORIZATION_A,
        fixture_action=None,
        pre_outcome_check=None,
        event_hook=None,
    ) -> dict[str, object]:
        action = fixture_action or (lambda: [{"candidate": "alpha", "score": 1}])
        return publication.publish_synthetic_fixture_v2(
            output or self.output,
            authorization_digest=authorization,
            fixture_action=action,
            _pre_outcome_check=pre_outcome_check,
            _event_hook=event_hook,
        )

    def _install_forged_committed_collective(
        self,
        output: Path,
        record_frames: list[dict[str, object]],
        *,
        manifest_record_overrides: dict[str, object] | None = None,
        ready_overrides: dict[str, object] | None = None,
    ) -> None:
        layout = publication.RegularFileLayoutV2.from_output_path(output)
        attempt = publication._attempt_payload(
            layout,
            AUTHORIZATION_A,
            "1" * (2 * publication._OWNER_NONCE_BYTES),
        )
        started = publication._phase_payload(
            attempt,
            phase="STARTED",
            status="PENDING",
            previous_receipt_digest=attempt["deterministic_digest"],
        )
        records_raw = b"".join(
            publication._canonical_bytes(frame) for frame in record_frames
        )
        manifest = publication._manifest_payload(
            layout,
            attempt,
            started,
            record_frames,
            records_raw,
        )
        if manifest_record_overrides is not None:
            manifest_core = dict(manifest)
            del manifest_core["deterministic_digest"]
            manifest_records = dict(manifest_core["records"])
            manifest_records.update(manifest_record_overrides)
            manifest_core["records"] = manifest_records
            manifest = publication._with_digest(manifest_core)
        ready_extra = {
            "manifest_digest": manifest["deterministic_digest"],
            "manifest_sha256": publication._sha256_bytes(
                publication._canonical_bytes(manifest)
            ),
            "records_byte_count": len(records_raw),
            "records_sha256": publication._sha256_bytes(records_raw),
        }
        if ready_overrides is not None:
            ready_extra.update(ready_overrides)
        ready = publication._phase_payload(
            attempt,
            phase="READY_TO_COMMIT",
            status="PENDING",
            previous_receipt_digest=started["deterministic_digest"],
            extra=ready_extra,
        )
        commit = publication._commit_payload(
            layout,
            attempt,
            started,
            ready,
            manifest,
            records_raw,
        )
        payloads = {
            layout.attempt_name: publication._canonical_bytes(attempt),
            layout.started_name: publication._canonical_bytes(started),
            layout.records_name: records_raw,
            layout.manifest_name: publication._canonical_bytes(manifest),
            layout.ready_name: publication._canonical_bytes(ready),
            layout.commit_name: publication._canonical_bytes(commit),
        }
        for name, payload in payloads.items():
            path = output.parent / name
            path.write_bytes(payload)
            path.chmod(0o600)

    def _flip_first_byte_and_fsync(self, path: Path) -> None:
        descriptor = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
        try:
            original = os.pread(descriptor, 1, 0)
            self.assertEqual(len(original), 1)
            self.assertEqual(
                os.pwrite(descriptor, bytes([original[0] ^ 1]), 0),
                1,
            )
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def test_happy_path_is_flat_commit_last_and_verifies(self) -> None:
        durable_order: list[str] = []

        def hook(event: str, context: publication.Mapping[str, object]) -> None:
            if event == "after_file_durable":
                durable_order.append(str(context["name"]))

        result = self._publish(event_hook=hook)
        layout = publication.RegularFileLayoutV2.from_output_path(self.output)
        self.assertEqual(result["status"], "COMMITTED")
        self.assertEqual(durable_order[-1], layout.commit_name)
        self.assertTrue(self.output.is_file())
        self.assertFalse(self.output.is_dir())
        self.assertEqual(
            set(path.name for path in self.root.iterdir()),
            {
                layout.attempt_name,
                layout.started_name,
                layout.records_name,
                layout.manifest_name,
                layout.ready_name,
                layout.commit_name,
            },
        )
        commit = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(commit["phase"], "COMMITTED")
        self.assertEqual(commit["status"], "COMMITTED")
        inspected = publication.inspect_synthetic_publication_v2(
            self.output,
            authorization_digest=AUTHORIZATION_A,
        )
        self.assertEqual(inspected["status"], "COMMITTED")
        self.assertEqual(
            inspected["artifact_commit_digest"],
            result["artifact_commit_digest"],
        )

    def test_restrictive_umask_still_publishes_exact_0600_collective(self) -> None:
        previous_umask = os.umask(0o777)
        try:
            result = self._publish()
        finally:
            os.umask(previous_umask)

        self.assertEqual(result["status"], "COMMITTED")
        self.assertEqual(
            publication.inspect_synthetic_publication_v2(self.output)["status"],
            "COMMITTED",
        )
        self.assertTrue(list(self.root.iterdir()))
        for path in self.root.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_output_global_reservation_blocks_new_authorization_before_action(self) -> None:
        self._publish()
        before = {
            path.name: (os.lstat(path).st_ino, path.read_bytes())
            for path in self.root.iterdir()
        }
        calls = 0

        def losing_action() -> list[dict[str, object]]:
            nonlocal calls
            calls += 1
            return []

        with self.assertRaises(publication.RegularFilePublicationV2NotRunError):
            self._publish(
                authorization=AUTHORIZATION_B,
                fixture_action=losing_action,
            )
        after = {
            path.name: (os.lstat(path).st_ino, path.read_bytes())
            for path in self.root.iterdir()
        }
        self.assertEqual(calls, 0)
        self.assertEqual(after, before)

    def test_preexisting_output_is_preserved_before_attempt_or_action(self) -> None:
        self.output.write_bytes(b"foreign-output")
        calls = 0

        def action() -> list[dict[str, object]]:
            nonlocal calls
            calls += 1
            return []

        with self.assertRaises(publication.RegularFilePublicationV2NotRunError):
            self._publish(fixture_action=action)
        self.assertEqual(calls, 0)
        self.assertEqual(self.output.read_bytes(), b"foreign-output")
        self.assertEqual(set(self.root.iterdir()), {self.output})
        with self.assertRaises(publication.RegularFilePublicationV2AmbiguousError):
            publication.inspect_synthetic_publication_v2(self.output)

    def test_pre_outcome_failure_publishes_exact_not_run(self) -> None:
        calls = 0

        def action() -> list[dict[str, object]]:
            nonlocal calls
            calls += 1
            return []

        def precheck() -> None:
            raise ValueError("synthetic precheck failure")

        with self.assertRaises(publication.RegularFilePublicationV2NotRunError):
            self._publish(fixture_action=action, pre_outcome_check=precheck)
        self.assertEqual(calls, 0)
        inspected = publication.inspect_synthetic_publication_v2(
            self.output,
            authorization_digest=AUTHORIZATION_A,
        )
        self.assertEqual(inspected["status"], "NOT_RUN")
        layout = publication.RegularFileLayoutV2.from_output_path(self.output)
        self.assertFalse((self.root / layout.started_name).exists())
        self.assertFalse(self.output.exists())

    def test_entropy_failure_before_attempt_leaves_no_evidence_or_outcome(self) -> None:
        calls = 0

        def action() -> list[dict[str, object]]:
            nonlocal calls
            calls += 1
            return []

        with mock.patch.object(
            publication.secrets,
            "token_hex",
            side_effect=OSError(errno.EIO, "synthetic entropy failure"),
        ):
            with self.assertRaises(publication.RegularFilePublicationV2NotRunError):
                self._publish(fixture_action=action)
        self.assertEqual(calls, 0)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_started_payload_failure_terminalizes_not_run(self) -> None:
        original_phase_payload = publication._phase_payload
        calls = 0

        def action() -> list[dict[str, object]]:
            nonlocal calls
            calls += 1
            return []

        def fail_started_payload(attempt, *, phase, status, previous_receipt_digest, extra=None):
            if phase == "STARTED" and status == "PENDING":
                raise ValueError("synthetic STARTED payload failure")
            return original_phase_payload(
                attempt,
                phase=phase,
                status=status,
                previous_receipt_digest=previous_receipt_digest,
                extra=extra,
            )

        with mock.patch.object(
            publication,
            "_phase_payload",
            side_effect=fail_started_payload,
        ):
            with self.assertRaises(publication.RegularFilePublicationV2NotRunError):
                self._publish(fixture_action=action)
        self.assertEqual(calls, 0)
        self.assertEqual(
            publication.inspect_synthetic_publication_v2(self.output)["status"],
            "NOT_RUN",
        )

    def test_post_started_failure_publishes_exact_invalid(self) -> None:
        def action() -> list[dict[str, object]]:
            raise RuntimeError("synthetic execution failure")

        with self.assertRaises(publication.RegularFilePublicationV2InvalidError):
            self._publish(fixture_action=action)
        inspected = publication.inspect_synthetic_publication_v2(
            self.output,
            authorization_digest=AUTHORIZATION_A,
        )
        self.assertEqual(inspected["status"], "INVALID")
        self.assertFalse(self.output.exists())

    def test_fixture_cannot_impersonate_substrate_ambiguity_after_started(self) -> None:
        def action() -> list[dict[str, object]]:
            raise publication.RegularFilePublicationV2AmbiguousError(
                "caller-controlled exception"
            )

        with self.assertRaises(publication.RegularFilePublicationV2InvalidError):
            self._publish(fixture_action=action)
        self.assertEqual(
            publication.inspect_synthetic_publication_v2(self.output)["status"],
            "INVALID",
        )

    def test_event_hook_cannot_impersonate_ambiguity_at_started_boundary(self) -> None:
        def hook(event: str, context: publication.Mapping[str, object]) -> None:
            if (
                event == "before_collective_snapshot"
                and context["terminal"] == "STARTED_BOUNDARY"
            ):
                raise publication.RegularFilePublicationV2AmbiguousError(
                    "caller-controlled hook exception"
                )

        with self.assertRaises(publication.RegularFilePublicationV2InvalidError):
            self._publish(event_hook=hook)
        self.assertEqual(
            publication.inspect_synthetic_publication_v2(self.output)["status"],
            "INVALID",
        )

    def test_precommit_hook_failure_still_terminalizes_invalid(self) -> None:
        def hook(event: str, context: publication.Mapping[str, object]) -> None:
            if (
                event == "before_collective_snapshot"
                and context["terminal"] == "PRE_COMMIT"
            ):
                raise publication.RegularFilePublicationV2AmbiguousError(
                    "caller-controlled precommit observer failure"
                )

        with self.assertRaises(publication.RegularFilePublicationV2InvalidError):
            self._publish(event_hook=hook)
        self.assertFalse(self.output.exists())
        self.assertEqual(
            publication.inspect_synthetic_publication_v2(self.output)["status"],
            "INVALID",
        )

    def test_not_run_terminal_hook_failure_preserves_exact_not_run(self) -> None:
        hook_calls = 0

        def hook(event: str, context: publication.Mapping[str, object]) -> None:
            nonlocal hook_calls
            if event == "before_collective_snapshot" and context["terminal"] == "NOT_RUN":
                hook_calls += 1
                raise publication.RegularFilePublicationV2AmbiguousError(
                    "non-authoritative observer failure"
                )

        with self.assertRaises(publication.RegularFilePublicationV2NotRunError):
            self._publish(
                pre_outcome_check=lambda: (_ for _ in ()).throw(ValueError("stop")),
                event_hook=hook,
            )
        self.assertEqual(hook_calls, 2)
        self.assertEqual(
            publication.inspect_synthetic_publication_v2(self.output)["status"],
            "NOT_RUN",
        )

    def test_invalid_terminal_hook_failure_preserves_exact_invalid(self) -> None:
        hook_calls = 0

        def hook(event: str, context: publication.Mapping[str, object]) -> None:
            nonlocal hook_calls
            if event == "before_collective_snapshot" and context["terminal"] == "INVALID":
                hook_calls += 1
                raise publication.RegularFilePublicationV2AmbiguousError(
                    "non-authoritative observer failure"
                )

        with self.assertRaises(publication.RegularFilePublicationV2InvalidError):
            self._publish(
                fixture_action=lambda: (_ for _ in ()).throw(RuntimeError("stop")),
                event_hook=hook,
            )
        self.assertEqual(hook_calls, 2)
        self.assertEqual(
            publication.inspect_synthetic_publication_v2(self.output)["status"],
            "INVALID",
        )

    def test_committed_terminal_hook_failure_preserves_exact_commit(self) -> None:
        hook_calls = 0

        def hook(event: str, context: publication.Mapping[str, object]) -> None:
            nonlocal hook_calls
            if (
                event == "before_collective_snapshot"
                and context["terminal"] == "COMMITTED"
            ):
                hook_calls += 1
                raise publication.RegularFilePublicationV2AmbiguousError(
                    "non-authoritative observer failure"
                )

        result = self._publish(event_hook=hook)
        self.assertEqual(result["status"], "COMMITTED")
        self.assertEqual(hook_calls, 2)
        self.assertEqual(
            publication.inspect_synthetic_publication_v2(self.output)["status"],
            "COMMITTED",
        )

    def test_every_reserved_name_refuses_foreign_entry_types_without_mutation(self) -> None:
        layout = publication.RegularFileLayoutV2.from_output_path(self.output)
        foreign_types = ("regular", "directory", "symlink", "fifo")
        for index, name in enumerate(layout.reserved_names):
            for kind in foreign_types:
                with self.subTest(name=name, kind=kind):
                    case_root = self.root / f"case-{index}-{kind}"
                    case_root.mkdir()
                    case_output = case_root / layout.commit_name
                    case_layout = publication.RegularFileLayoutV2.from_output_path(
                        case_output
                    )
                    case_name = case_layout.reserved_names[index]
                    foreign = case_root / case_name
                    if kind == "regular":
                        foreign.write_bytes(b"foreign")
                    elif kind == "directory":
                        foreign.mkdir()
                    elif kind == "symlink":
                        foreign.symlink_to("missing-target")
                    else:
                        os.mkfifo(foreign)
                    before = os.lstat(foreign)
                    parent = publication._PinnedParent.open(case_root)
                    try:
                        with self.assertRaises(publication._NameConflictError):
                            publication._exclusive_create_exact(
                                parent,
                                case_name,
                                b"owned",
                                max_bytes=64,
                                hook=None,
                            )
                    finally:
                        parent.close()
                    after = os.lstat(foreign)
                    self.assertEqual((after.st_dev, after.st_ino), (before.st_dev, before.st_ino))
                    if kind == "regular":
                        self.assertEqual(foreign.read_bytes(), b"foreign")

    def test_foreign_unix_socket_is_preserved(self) -> None:
        name = "foreign.sock"
        foreign = self.root / name
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(os.fspath(foreign))
        before = os.lstat(foreign)
        parent = publication._PinnedParent.open(self.root)
        try:
            with self.assertRaises(publication._NameConflictError):
                publication._exclusive_create_exact(
                    parent,
                    name,
                    b"owned",
                    max_bytes=64,
                    hook=None,
                )
        finally:
            parent.close()
            server.close()
        after = os.lstat(foreign)
        self.assertTrue(stat.S_ISSOCK(after.st_mode))
        self.assertEqual((after.st_dev, after.st_ino), (before.st_dev, before.st_ino))

    def test_creation_uses_exact_required_exclusive_flags(self) -> None:
        original_open = os.open
        observed: list[int] = []

        def recording_open(path, flags, mode=0o777, *, dir_fd=None):
            if flags & os.O_CREAT:
                observed.append(flags)
            if dir_fd is None:
                return original_open(path, flags, mode)
            return original_open(path, flags, mode, dir_fd=dir_fd)

        with (
            mock.patch.object(publication.os, "open", side_effect=recording_open),
            mock.patch.object(
                publication,
                "_require_posix_capabilities",
                return_value=None,
            ),
        ):
            self._publish()
        required = os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
        self.assertTrue(observed)
        self.assertTrue(all(flags & required == required for flags in observed))

    def test_post_initial_fstat_permission_widening_is_never_adopted(self) -> None:
        layout = publication.RegularFileLayoutV2.from_output_path(self.output)
        attempt_descriptor = -1
        calls = 0

        def action() -> list[dict[str, object]]:
            nonlocal calls
            calls += 1
            return []

        def hook(event: str, context: publication.Mapping[str, object]) -> None:
            nonlocal attempt_descriptor
            if (
                event == "after_exclusive_open"
                and context["name"] == layout.attempt_name
            ):
                attempt_descriptor = int(context["file_descriptor"])
            if event == "after_initial_fstat" and context["name"] == layout.attempt_name:
                os.fchmod(attempt_descriptor, 0o644)

        with self.assertRaises(publication.RegularFilePublicationV2AmbiguousError):
            self._publish(fixture_action=action, event_hook=hook)
        self.assertEqual(calls, 0)
        self.assertEqual(
            stat.S_IMODE((self.root / layout.attempt_name).stat().st_mode),
            0o644,
        )
        with self.assertRaises(publication.RegularFilePublicationV2AmbiguousError):
            publication.inspect_synthetic_publication_v2(self.output)

    def test_post_file_fsync_same_bytes_generation_is_never_adopted(self) -> None:
        layout = publication.RegularFileLayoutV2.from_output_path(self.output)
        attempt_descriptor = -1
        mutations = 0
        calls = 0

        def action() -> list[dict[str, object]]:
            nonlocal calls
            calls += 1
            return []

        def hook(event: str, context: publication.Mapping[str, object]) -> None:
            nonlocal attempt_descriptor, mutations
            if (
                event == "after_exclusive_open"
                and context["name"] == layout.attempt_name
            ):
                attempt_descriptor = int(context["file_descriptor"])
            if event == "after_file_fsync" and context["name"] == layout.attempt_name:
                size = os.fstat(attempt_descriptor).st_size
                raw = os.pread(attempt_descriptor, size, 0)
                os.ftruncate(attempt_descriptor, 0)
                os.lseek(attempt_descriptor, 0, os.SEEK_SET)
                self.assertEqual(os.write(attempt_descriptor, raw), len(raw))
                mutations += 1

        with self.assertRaises(publication.RegularFilePublicationV2AmbiguousError):
            self._publish(fixture_action=action, event_hook=hook)
        self.assertGreaterEqual(mutations, 2)
        self.assertEqual(calls, 0)

    def test_mutation_before_fsync_returns_is_never_adopted_as_durable(self) -> None:
        layout = publication.RegularFileLayoutV2.from_output_path(self.output)
        original_fsync = publication.os.fsync
        attempt_descriptor = -1
        mutations = 0
        calls = 0

        def action() -> list[dict[str, object]]:
            nonlocal calls
            calls += 1
            return []

        def hook(event: str, context: publication.Mapping[str, object]) -> None:
            nonlocal attempt_descriptor
            if (
                event == "after_exclusive_open"
                and context["name"] == layout.attempt_name
            ):
                attempt_descriptor = int(context["file_descriptor"])

        def mutating_fsync(descriptor: int) -> None:
            nonlocal mutations
            original_fsync(descriptor)
            if descriptor == attempt_descriptor:
                size = os.fstat(descriptor).st_size
                raw = os.pread(descriptor, size, 0)
                os.ftruncate(descriptor, 0)
                os.lseek(descriptor, 0, os.SEEK_SET)
                self.assertEqual(os.write(descriptor, raw), len(raw))
                mutations += 1

        with mock.patch.object(
            publication.os,
            "fsync",
            side_effect=mutating_fsync,
        ):
            with self.assertRaises(publication.RegularFilePublicationV2AmbiguousError):
                self._publish(fixture_action=action, event_hook=hook)
        self.assertGreaterEqual(mutations, 2)
        self.assertEqual(calls, 0)

    def test_post_open_pre_fstat_substitution_is_ambiguous_and_foreign_survives(self) -> None:
        layout = publication.RegularFileLayoutV2.from_output_path(self.output)
        calls = 0
        substituted = False

        def action() -> list[dict[str, object]]:
            nonlocal calls
            calls += 1
            return []

        def hook(event: str, context: publication.Mapping[str, object]) -> None:
            nonlocal substituted
            if (
                event == "after_exclusive_open"
                and context["name"] == layout.attempt_name
                and not substituted
            ):
                substituted = True
                directory_fd = int(context["directory_fd"])
                os.unlink(layout.attempt_name, dir_fd=directory_fd)
                descriptor = os.open(
                    layout.attempt_name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=directory_fd,
                )
                try:
                    os.write(descriptor, b"foreign")
                    os.fsync(descriptor)
                    os.fsync(directory_fd)
                finally:
                    os.close(descriptor)

        with self.assertRaises(publication.RegularFilePublicationV2AmbiguousError):
            self._publish(fixture_action=action, event_hook=hook)
        self.assertTrue(substituted)
        self.assertEqual(calls, 0)
        self.assertEqual((self.root / layout.attempt_name).read_bytes(), b"foreign")

    def test_protocol_never_calls_rename_replace_or_unlink(self) -> None:
        with (
            mock.patch.object(
                publication.os,
                "rename",
                side_effect=AssertionError("rename forbidden"),
            ),
            mock.patch.object(
                publication.os,
                "replace",
                side_effect=AssertionError("replace forbidden"),
            ),
            mock.patch.object(
                publication.os,
                "unlink",
                side_effect=AssertionError("unlink forbidden"),
            ),
        ):
            result = self._publish()
        self.assertEqual(result["status"], "COMMITTED")

    def test_short_writes_are_completed_exactly(self) -> None:
        original_write = os.write

        def short_write(descriptor: int, payload: bytes) -> int:
            return original_write(descriptor, payload[: max(1, min(7, len(payload)))])

        with mock.patch.object(publication.os, "write", side_effect=short_write):
            result = self._publish()
        self.assertEqual(result["status"], "COMMITTED")
        self.assertEqual(
            publication.inspect_synthetic_publication_v2(self.output)["status"],
            "COMMITTED",
        )

    def test_interrupted_writes_are_retried(self) -> None:
        original_write = os.write
        interrupted = False

        def interrupt_once(descriptor: int, payload: bytes) -> int:
            nonlocal interrupted
            if not interrupted:
                interrupted = True
                raise InterruptedError(errno.EINTR, "synthetic interrupt")
            return original_write(descriptor, payload)

        with mock.patch.object(publication.os, "write", side_effect=interrupt_once):
            result = self._publish()
        self.assertTrue(interrupted)
        self.assertEqual(result["status"], "COMMITTED")

    def test_attempt_file_fsync_failure_is_ambiguous_before_outcome(self) -> None:
        layout = publication.RegularFileLayoutV2.from_output_path(self.output)
        original_fsync = os.fsync
        target_descriptor = -1
        calls = 0

        def action() -> list[dict[str, object]]:
            nonlocal calls
            calls += 1
            return []

        def hook(event: str, context: publication.Mapping[str, object]) -> None:
            nonlocal target_descriptor
            if event == "after_exclusive_open" and context["name"] == layout.attempt_name:
                target_descriptor = int(context["file_descriptor"])

        def failing_fsync(descriptor: int) -> None:
            if descriptor == target_descriptor:
                raise OSError(errno.EIO, "synthetic attempt fsync failure")
            original_fsync(descriptor)

        with mock.patch.object(publication.os, "fsync", side_effect=failing_fsync):
            with self.assertRaises(publication.RegularFilePublicationV2AmbiguousError):
                self._publish(fixture_action=action, event_hook=hook)
        self.assertEqual(calls, 0)
        self.assertFalse((self.root / layout.not_run_name).exists())

    def test_pre_attempt_parent_fsync_failure_is_not_run_without_evidence(self) -> None:
        original_fsync = os.fsync
        failed = False
        calls = 0

        def action() -> list[dict[str, object]]:
            nonlocal calls
            calls += 1
            return []

        def fail_first(descriptor: int) -> None:
            nonlocal failed
            if not failed:
                failed = True
                raise OSError(errno.EIO, "synthetic pre-attempt parent fsync failure")
            original_fsync(descriptor)

        with mock.patch.object(publication.os, "fsync", side_effect=fail_first):
            with self.assertRaises(publication.RegularFilePublicationV2NotRunError):
                self._publish(fixture_action=action)
        self.assertTrue(failed)
        self.assertEqual(calls, 0)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_records_enospc_after_partial_write_becomes_invalid(self) -> None:
        layout = publication.RegularFileLayoutV2.from_output_path(self.output)
        original_write = os.write
        target_descriptor = -1
        target_writes = 0

        def hook(event: str, context: publication.Mapping[str, object]) -> None:
            nonlocal target_descriptor
            if event == "after_exclusive_open":
                target_descriptor = (
                    int(context["file_descriptor"])
                    if context["name"] == layout.records_name
                    else -1
                )

        def failing_write(descriptor: int, payload: bytes) -> int:
            nonlocal target_writes
            if descriptor != target_descriptor:
                return original_write(descriptor, payload)
            target_writes += 1
            if target_writes == 1:
                return original_write(descriptor, payload[:3])
            raise OSError(errno.ENOSPC, "synthetic records ENOSPC")

        with mock.patch.object(publication.os, "write", side_effect=failing_write):
            with self.assertRaises(publication.RegularFilePublicationV2InvalidError):
                self._publish(event_hook=hook)
        self.assertGreaterEqual(target_writes, 2)
        self.assertEqual(
            publication.inspect_synthetic_publication_v2(self.output)["status"],
            "INVALID",
        )

    def test_one_shot_commit_file_fsync_failure_forward_completes_commit(self) -> None:
        layout = publication.RegularFileLayoutV2.from_output_path(self.output)
        original_fsync = os.fsync
        target_descriptor = -1
        failed = False

        def hook(event: str, context: publication.Mapping[str, object]) -> None:
            nonlocal target_descriptor
            if event == "after_exclusive_open" and context["name"] == layout.commit_name:
                target_descriptor = int(context["file_descriptor"])

        def fail_once(descriptor: int) -> None:
            nonlocal failed
            if descriptor == target_descriptor and not failed:
                failed = True
                raise OSError(errno.EIO, "synthetic one-shot commit fsync failure")
            original_fsync(descriptor)

        with mock.patch.object(publication.os, "fsync", side_effect=fail_once):
            result = self._publish(event_hook=hook)
        self.assertTrue(failed)
        self.assertEqual(result["status"], "COMMITTED")

    def test_persistent_commit_file_fsync_failure_never_becomes_invalid(self) -> None:
        layout = publication.RegularFileLayoutV2.from_output_path(self.output)
        original_fsync = os.fsync
        target_descriptor = -1

        def hook(event: str, context: publication.Mapping[str, object]) -> None:
            nonlocal target_descriptor
            if event == "after_exclusive_open" and context["name"] == layout.commit_name:
                target_descriptor = int(context["file_descriptor"])

        def fail_commit(descriptor: int) -> None:
            if descriptor == target_descriptor:
                raise OSError(errno.EIO, "synthetic persistent commit fsync failure")
            original_fsync(descriptor)

        with mock.patch.object(publication.os, "fsync", side_effect=fail_commit):
            with self.assertRaises(publication.RegularFilePublicationV2AmbiguousError):
                self._publish(event_hook=hook)
        self.assertTrue(self.output.exists())
        self.assertFalse((self.root / layout.invalid_name).exists())

    def test_one_shot_commit_parent_fsync_failure_forward_completes_commit(self) -> None:
        layout = publication.RegularFileLayoutV2.from_output_path(self.output)
        original_fsync = os.fsync
        parent_descriptor = -1
        commit_opened = False
        failed = False

        def hook(event: str, context: publication.Mapping[str, object]) -> None:
            nonlocal parent_descriptor, commit_opened
            if event == "after_exclusive_open" and context["name"] == layout.commit_name:
                parent_descriptor = int(context["directory_fd"])
                commit_opened = True

        def fail_once(descriptor: int) -> None:
            nonlocal failed
            if commit_opened and descriptor == parent_descriptor and not failed:
                failed = True
                raise OSError(errno.EIO, "synthetic one-shot parent fsync failure")
            original_fsync(descriptor)

        with mock.patch.object(publication.os, "fsync", side_effect=fail_once):
            result = self._publish(event_hook=hook)
        self.assertTrue(failed)
        self.assertEqual(result["status"], "COMMITTED")

    def test_persistent_commit_parent_fsync_failure_is_ambiguous(self) -> None:
        layout = publication.RegularFileLayoutV2.from_output_path(self.output)
        original_fsync = os.fsync
        parent_descriptor = -1
        commit_opened = False

        def hook(event: str, context: publication.Mapping[str, object]) -> None:
            nonlocal parent_descriptor, commit_opened
            if event == "after_exclusive_open" and context["name"] == layout.commit_name:
                parent_descriptor = int(context["directory_fd"])
                commit_opened = True

        def fail_parent(descriptor: int) -> None:
            if commit_opened and descriptor == parent_descriptor:
                raise OSError(errno.EIO, "synthetic persistent parent fsync failure")
            original_fsync(descriptor)

        with mock.patch.object(publication.os, "fsync", side_effect=fail_parent):
            with self.assertRaises(publication.RegularFilePublicationV2AmbiguousError):
                self._publish(event_hook=hook)
        self.assertTrue(self.output.exists())
        self.assertFalse((self.root / layout.invalid_name).exists())

    def test_each_file_barrier_orders_file_fsync_before_parent_fsync(self) -> None:
        events: list[tuple[str, str]] = []

        def hook(event: str, context: publication.Mapping[str, object]) -> None:
            if event in {"after_file_fsync", "after_parent_fsync"} and not context.get(
                "reconciled"
            ):
                events.append((str(context["name"]), event))

        self._publish(event_hook=hook)
        layout = publication.RegularFileLayoutV2.from_output_path(self.output)
        expected_names = {
            layout.attempt_name,
            layout.started_name,
            layout.records_name,
            layout.manifest_name,
            layout.ready_name,
            layout.commit_name,
        }
        for name in expected_names:
            sequence = [event for observed_name, event in events if observed_name == name]
            self.assertEqual(sequence, ["after_file_fsync", "after_parent_fsync"])

    def test_started_open_then_failure_never_becomes_not_run(self) -> None:
        layout = publication.RegularFileLayoutV2.from_output_path(self.output)
        calls = 0

        def action() -> list[dict[str, object]]:
            nonlocal calls
            calls += 1
            return []

        def hook(event: str, context: publication.Mapping[str, object]) -> None:
            if event == "after_exclusive_open" and context["name"] == layout.started_name:
                raise OSError("fault after STARTED open")

        with self.assertRaises(publication.RegularFilePublicationV2AmbiguousError):
            self._publish(fixture_action=action, event_hook=hook)
        self.assertEqual(calls, 0)
        self.assertFalse((self.root / layout.not_run_name).exists())

    def test_foreign_records_conflict_becomes_invalid_and_is_preserved(self) -> None:
        layout = publication.RegularFileLayoutV2.from_output_path(self.output)
        injected = False

        def hook(event: str, context: publication.Mapping[str, object]) -> None:
            nonlocal injected
            if (
                event == "before_exclusive_open"
                and context["name"] == layout.records_name
                and not injected
            ):
                injected = True
                descriptor = os.open(
                    layout.records_name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=int(context["directory_fd"]),
                )
                try:
                    os.write(descriptor, b"foreign-records")
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)

        with self.assertRaises(publication.RegularFilePublicationV2InvalidError):
            self._publish(event_hook=hook)
        self.assertTrue(injected)
        self.assertEqual(
            (self.root / layout.records_name).read_bytes(),
            b"foreign-records",
        )
        self.assertEqual(
            publication.inspect_synthetic_publication_v2(self.output)["status"],
            "INVALID",
        )

    def test_foreign_ready_conflict_is_ambiguous_and_preserved(self) -> None:
        layout = publication.RegularFileLayoutV2.from_output_path(self.output)

        def hook(event: str, context: publication.Mapping[str, object]) -> None:
            if event == "before_exclusive_open" and context["name"] == layout.ready_name:
                descriptor = os.open(
                    layout.ready_name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=int(context["directory_fd"]),
                )
                try:
                    os.write(descriptor, b"foreign-ready")
                finally:
                    os.close(descriptor)

        with self.assertRaises(publication.RegularFilePublicationV2AmbiguousError):
            self._publish(event_hook=hook)
        self.assertEqual((self.root / layout.ready_name).read_bytes(), b"foreign-ready")
        self.assertFalse((self.root / layout.invalid_name).exists())

    def test_ready_preopen_failure_becomes_inspectable_invalid(self) -> None:
        layout = publication.RegularFileLayoutV2.from_output_path(self.output)

        def hook(event: str, context: publication.Mapping[str, object]) -> None:
            if event == "before_exclusive_open" and context["name"] == layout.ready_name:
                raise OSError(errno.ENOSPC, "synthetic READY pre-open failure")

        with self.assertRaises(publication.RegularFilePublicationV2InvalidError):
            self._publish(event_hook=hook)
        self.assertFalse((self.root / layout.ready_name).exists())
        self.assertEqual(
            publication.inspect_synthetic_publication_v2(self.output)["status"],
            "INVALID",
        )

    def test_commit_preopen_hook_failure_becomes_inspectable_invalid(self) -> None:
        layout = publication.RegularFileLayoutV2.from_output_path(self.output)

        def hook(event: str, context: publication.Mapping[str, object]) -> None:
            if event == "before_exclusive_open" and context["name"] == layout.commit_name:
                raise publication.RegularFilePublicationV2AmbiguousError(
                    "caller-controlled ambiguity"
                )

        with self.assertRaises(publication.RegularFilePublicationV2InvalidError):
            self._publish(event_hook=hook)
        self.assertFalse(self.output.exists())
        self.assertEqual(
            publication.inspect_synthetic_publication_v2(self.output)["status"],
            "INVALID",
        )

    def test_foreign_commit_collision_never_downgrades_to_invalid(self) -> None:
        layout = publication.RegularFileLayoutV2.from_output_path(self.output)

        def hook(event: str, context: publication.Mapping[str, object]) -> None:
            if event == "before_exclusive_open" and context["name"] == layout.commit_name:
                descriptor = os.open(
                    layout.commit_name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=int(context["directory_fd"]),
                )
                try:
                    os.write(descriptor, b"foreign-commit")
                finally:
                    os.close(descriptor)

        with self.assertRaises(publication.RegularFilePublicationV2AmbiguousError):
            self._publish(event_hook=hook)
        self.assertEqual(self.output.read_bytes(), b"foreign-commit")
        self.assertFalse((self.root / layout.invalid_name).exists())

    def test_not_run_terminal_mutate_then_raise_is_ambiguous(self) -> None:
        layout = publication.RegularFileLayoutV2.from_output_path(self.output)
        mutated = False

        def hook(event: str, context: publication.Mapping[str, object]) -> None:
            nonlocal mutated
            if (
                event == "before_collective_snapshot"
                and context["terminal"] == "NOT_RUN"
                and context["snapshot_index"] == 1
            ):
                mutated = True
                self._flip_first_byte_and_fsync(self.root / layout.not_run_name)
                raise publication.RegularFilePublicationV2AmbiguousError(
                    "mutation plus observer failure"
                )

        with self.assertRaises(publication.RegularFilePublicationV2AmbiguousError):
            self._publish(
                pre_outcome_check=lambda: (_ for _ in ()).throw(ValueError("stop")),
                event_hook=hook,
            )
        self.assertTrue(mutated)
        self.assertFalse((self.root / layout.started_name).exists())
        with self.assertRaises(publication.RegularFilePublicationV2AmbiguousError):
            publication.inspect_synthetic_publication_v2(self.output)

    def test_invalid_terminal_mutate_then_raise_is_ambiguous(self) -> None:
        layout = publication.RegularFileLayoutV2.from_output_path(self.output)
        mutated = False

        def hook(event: str, context: publication.Mapping[str, object]) -> None:
            nonlocal mutated
            if (
                event == "before_collective_snapshot"
                and context["terminal"] == "INVALID"
                and context["snapshot_index"] == 1
            ):
                mutated = True
                self._flip_first_byte_and_fsync(self.root / layout.invalid_name)
                raise publication.RegularFilePublicationV2AmbiguousError(
                    "mutation plus observer failure"
                )

        with self.assertRaises(publication.RegularFilePublicationV2AmbiguousError):
            self._publish(
                fixture_action=lambda: (_ for _ in ()).throw(RuntimeError("stop")),
                event_hook=hook,
            )
        self.assertTrue(mutated)
        self.assertFalse(self.output.exists())
        with self.assertRaises(publication.RegularFilePublicationV2AmbiguousError):
            publication.inspect_synthetic_publication_v2(self.output)

    def test_committed_terminal_mutate_then_raise_is_ambiguous(self) -> None:
        layout = publication.RegularFileLayoutV2.from_output_path(self.output)
        mutated = False

        def hook(event: str, context: publication.Mapping[str, object]) -> None:
            nonlocal mutated
            if (
                event == "before_collective_snapshot"
                and context["terminal"] == "COMMITTED"
                and context["snapshot_index"] == 1
            ):
                mutated = True
                self._flip_first_byte_and_fsync(self.output)
                raise publication.RegularFilePublicationV2AmbiguousError(
                    "mutation plus observer failure"
                )

        with self.assertRaises(publication.RegularFilePublicationV2AmbiguousError):
            self._publish(event_hook=hook)
        self.assertTrue(mutated)
        self.assertFalse((self.root / layout.invalid_name).exists())
        with self.assertRaises(publication.RegularFilePublicationV2AmbiguousError):
            publication.inspect_synthetic_publication_v2(self.output)

    def test_committed_invalid_injection_is_ambiguous(self) -> None:
        layout = publication.RegularFileLayoutV2.from_output_path(self.output)
        injected = False

        def hook(event: str, context: publication.Mapping[str, object]) -> None:
            nonlocal injected
            if (
                event == "before_collective_snapshot"
                and context["terminal"] == "COMMITTED"
                and context["snapshot_index"] == 1
                and not injected
            ):
                injected = True
                descriptor = os.open(
                    layout.invalid_name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=int(context["directory_fd"]),
                )
                try:
                    os.write(descriptor, b"foreign-invalid")
                finally:
                    os.close(descriptor)

        with self.assertRaises(publication.RegularFilePublicationV2AmbiguousError):
            self._publish(event_hook=hook)
        self.assertTrue(self.output.exists())
        self.assertEqual((self.root / layout.invalid_name).read_bytes(), b"foreign-invalid")
        with self.assertRaises(publication.RegularFilePublicationV2AmbiguousError):
            publication.inspect_synthetic_publication_v2(self.output)

    def test_not_run_started_injection_is_ambiguous(self) -> None:
        layout = publication.RegularFileLayoutV2.from_output_path(self.output)
        injected = False

        def hook(event: str, context: publication.Mapping[str, object]) -> None:
            nonlocal injected
            if (
                event == "before_collective_snapshot"
                and context["terminal"] == "NOT_RUN"
                and not injected
            ):
                injected = True
                descriptor = os.open(
                    layout.started_name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=int(context["directory_fd"]),
                )
                try:
                    os.write(descriptor, b"foreign-started")
                finally:
                    os.close(descriptor)

        with self.assertRaises(publication.RegularFilePublicationV2AmbiguousError):
            self._publish(
                pre_outcome_check=lambda: (_ for _ in ()).throw(ValueError("stop")),
                event_hook=hook,
            )
        self.assertEqual((self.root / layout.started_name).read_bytes(), b"foreign-started")
        with self.assertRaises(publication.RegularFilePublicationV2AmbiguousError):
            publication.inspect_synthetic_publication_v2(self.output)

    def test_hardlink_added_before_started_prevents_outcome(self) -> None:
        layout = publication.RegularFileLayoutV2.from_output_path(self.output)
        calls = 0

        def action() -> list[dict[str, object]]:
            nonlocal calls
            calls += 1
            return []

        # after_attempt intentionally exposes no dirfd, so bind the test's
        # adversary through the absolute parent while the protocol stays dirfd-only.
        def absolute_hook(event: str, context: publication.Mapping[str, object]) -> None:
            if event == "after_attempt":
                os.link(self.root / layout.attempt_name, self.root / "foreign-hardlink")

        with self.assertRaises(publication.RegularFilePublicationV2AmbiguousError):
            self._publish(fixture_action=action, event_hook=absolute_hook)
        self.assertEqual(calls, 0)
        self.assertTrue((self.root / "foreign-hardlink").exists())

    def test_hardlink_create_remove_aba_is_detected_before_outcome(self) -> None:
        layout = publication.RegularFileLayoutV2.from_output_path(self.output)
        calls = 0

        def action() -> list[dict[str, object]]:
            nonlocal calls
            calls += 1
            return []

        def hook(event: str, context: publication.Mapping[str, object]) -> None:
            if event == "after_attempt":
                alias = self.root / "temporary-hardlink"
                os.link(self.root / layout.attempt_name, alias)
                os.unlink(alias)

        with self.assertRaises(publication.RegularFilePublicationV2AmbiguousError):
            self._publish(fixture_action=action, event_hook=hook)
        self.assertEqual(calls, 0)

    def test_bounded_reader_refuses_fifo_and_oversized_regular_file(self) -> None:
        parent = publication._PinnedParent.open(self.root)
        try:
            fifo_name = "foreign.fifo"
            os.mkfifo(self.root / fifo_name)
            with self.assertRaises(publication.RegularFilePublicationV2AmbiguousError):
                publication._read_bounded_regular_file_at(
                    parent,
                    fifo_name,
                    max_bytes=64,
                )
            oversized_name = "oversized.bin"
            (self.root / oversized_name).write_bytes(b"x" * 65)
            with self.assertRaises(publication.RegularFilePublicationV2AmbiguousError):
                publication._read_bounded_regular_file_at(
                    parent,
                    oversized_name,
                    max_bytes=64,
                )
        finally:
            parent.close()

    def test_inspector_rejects_more_records_than_publisher_can_emit(self) -> None:
        frames = [
            {
                "fixture_kind": publication.FIXTURE_KIND,
                "payload": {},
                "record_index": index,
                "schema_version": publication.RECORD_SCHEMA_VERSION,
            }
            for index in range(publication._MAX_SYNTHETIC_RECORDS + 1)
        ]
        self._install_forged_committed_collective(self.output, frames)
        layout = publication.RegularFileLayoutV2.from_output_path(self.output)
        self.assertLessEqual(
            (self.root / layout.records_name).stat().st_size,
            publication._MAX_RECORDS_BYTES,
        )
        with self.assertRaises(publication.RegularFilePublicationV2AmbiguousError):
            publication.inspect_synthetic_publication_v2(self.output)

    def test_inspector_rejects_records_outside_exact_producer_schema(self) -> None:
        cases = {
            "list-payload": {"payload": [], "record_index": 0},
            "boolean-index": {"payload": {}, "record_index": False},
            "float-index": {"payload": {}, "record_index": 0.0},
        }
        for label, variant in cases.items():
            with self.subTest(label=label):
                case_root = self.root / label
                case_root.mkdir()
                output = case_root / "artifact.commit.json"
                frame = {
                    "fixture_kind": publication.FIXTURE_KIND,
                    "payload": variant["payload"],
                    "record_index": variant["record_index"],
                    "schema_version": publication.RECORD_SCHEMA_VERSION,
                }
                self._install_forged_committed_collective(output, [frame])
                with self.assertRaises(
                    publication.RegularFilePublicationV2AmbiguousError
                ):
                    publication.inspect_synthetic_publication_v2(output)

    def test_inspector_rejects_non_integer_record_metadata(self) -> None:
        frame = {
            "fixture_kind": publication.FIXTURE_KIND,
            "payload": {},
            "record_index": 0,
            "schema_version": publication.RECORD_SCHEMA_VERSION,
        }
        byte_count = len(publication._canonical_bytes(frame))
        cases = {
            "manifest-byte-count-float": {
                "manifest_record_overrides": {"byte_count": float(byte_count)}
            },
            "manifest-record-count-float": {
                "manifest_record_overrides": {"record_count": 1.0}
            },
            "manifest-record-count-bool": {
                "manifest_record_overrides": {"record_count": True}
            },
            "ready-byte-count-float": {
                "ready_overrides": {"records_byte_count": float(byte_count)}
            },
        }
        for label, overrides in cases.items():
            with self.subTest(label=label):
                case_root = self.root / label
                case_root.mkdir()
                output = case_root / "artifact.commit.json"
                self._install_forged_committed_collective(
                    output,
                    [frame],
                    **overrides,
                )
                with self.assertRaises(
                    publication.RegularFilePublicationV2AmbiguousError
                ):
                    publication.inspect_synthetic_publication_v2(output)

    def test_same_inode_overwrite_during_commit_proof_is_ambiguous(self) -> None:
        layout = publication.RegularFileLayoutV2.from_output_path(self.output)
        mutated = False

        def hook(event: str, context: publication.Mapping[str, object]) -> None:
            nonlocal mutated
            if (
                event == "before_collective_snapshot"
                and context["terminal"] == "COMMITTED"
                and not mutated
            ):
                mutated = True
                path = self.root / layout.records_name
                raw = path.read_bytes()
                replacement = bytes([raw[0] ^ 1]) + raw[1:]
                descriptor = os.open(path, os.O_WRONLY | os.O_NOFOLLOW)
                try:
                    os.write(descriptor, replacement)
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)

        with self.assertRaises(publication.RegularFilePublicationV2AmbiguousError):
            self._publish(event_hook=hook)
        self.assertTrue(mutated)
        self.assertTrue(self.output.exists())
        with self.assertRaises(publication.RegularFilePublicationV2AmbiguousError):
            publication.inspect_synthetic_publication_v2(self.output)

    def test_ready_backed_invalid_reproves_records_and_manifest(self) -> None:
        layout = publication.RegularFileLayoutV2.from_output_path(self.output)
        mutated = False

        def hook(event: str, context: publication.Mapping[str, object]) -> None:
            nonlocal mutated
            if event == "before_commit" and not mutated:
                mutated = True
                path = self.root / layout.records_name
                raw = path.read_bytes()
                descriptor = os.open(path, os.O_WRONLY | os.O_NOFOLLOW)
                try:
                    os.write(descriptor, bytes([raw[0] ^ 1]) + raw[1:])
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
                raise RuntimeError("synthetic post-READY failure")

        with self.assertRaises(publication.RegularFilePublicationV2AmbiguousError):
            self._publish(event_hook=hook)
        self.assertTrue(mutated)
        self.assertFalse(self.output.exists())

    def test_byte_identical_commit_name_replacement_is_detected_in_process(self) -> None:
        replaced = False

        def hook(event: str, context: publication.Mapping[str, object]) -> None:
            nonlocal replaced
            if event == "after_commit" and not replaced:
                replaced = True
                raw = self.output.read_bytes()
                os.unlink(self.output)
                descriptor = os.open(
                    self.output,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                )
                try:
                    os.write(descriptor, raw)
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)

        with self.assertRaises(publication.RegularFilePublicationV2AmbiguousError):
            self._publish(event_hook=hook)
        self.assertTrue(replaced)
        self.assertFalse(
            (
                self.root
                / publication.RegularFileLayoutV2.from_output_path(
                    self.output
                ).invalid_name
            ).exists()
        )

    def test_inspector_rejects_byte_identical_generation_between_snapshots(self) -> None:
        self._publish()
        layout = publication.RegularFileLayoutV2.from_output_path(self.output)
        original_inspect_once = publication._inspect_once
        calls = 0

        def replacing_inspect_once(parent, observed_layout, authorization):
            nonlocal calls
            result = original_inspect_once(parent, observed_layout, authorization)
            calls += 1
            if calls == 1:
                path = self.root / layout.attempt_name
                raw = path.read_bytes()
                os.unlink(path)
                descriptor = os.open(
                    path,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                )
                try:
                    os.write(descriptor, raw)
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            return result

        with mock.patch.object(
            publication,
            "_inspect_once",
            side_effect=replacing_inspect_once,
        ):
            with self.assertRaises(publication.RegularFilePublicationV2AmbiguousError):
                publication.inspect_synthetic_publication_v2(self.output)
        self.assertEqual(calls, 2)

    def test_parent_path_pivot_after_attempt_is_ambiguous_before_outcome(self) -> None:
        calls = 0
        original_parent = self.root
        moved_parent = self.root.with_name(f"{self.root.name}-moved")

        def action() -> list[dict[str, object]]:
            nonlocal calls
            calls += 1
            return []

        def hook(event: str, context: publication.Mapping[str, object]) -> None:
            if event == "after_attempt":
                os.rename(original_parent, moved_parent)
                original_parent.mkdir()

        try:
            with self.assertRaises(publication.RegularFilePublicationV2AmbiguousError):
                self._publish(fixture_action=action, event_hook=hook)
            self.assertEqual(calls, 0)
        finally:
            # Restore the TemporaryDirectory's owning path for normal cleanup.
            if original_parent.exists():
                original_parent.rmdir()
            if moved_parent.exists():
                os.rename(moved_parent, original_parent)

    def test_symlinked_parent_is_refused_before_action(self) -> None:
        real_parent = self.root / "real"
        real_parent.mkdir()
        linked_parent = self.root / "linked"
        linked_parent.symlink_to(real_parent, target_is_directory=True)
        calls = 0

        def action() -> list[dict[str, object]]:
            nonlocal calls
            calls += 1
            return []

        with self.assertRaises(publication.RegularFilePublicationV2NotRunError):
            self._publish(
                output=linked_parent / "artifact",
                fixture_action=action,
            )
        self.assertEqual(calls, 0)
        self.assertEqual(list(real_parent.iterdir()), [])

    def test_directory_walk_closes_child_descriptor_when_fstat_fails(self) -> None:
        child = self.root / "child"
        child.mkdir()
        original_open = publication.os.open
        original_fstat = publication.os.fstat
        child_descriptors: list[int] = []

        def tracking_open(path, flags, mode=0o777, *, dir_fd=None):
            if dir_fd is None:
                descriptor = original_open(path, flags, mode)
            else:
                descriptor = original_open(path, flags, mode, dir_fd=dir_fd)
            if path == child.name:
                child_descriptors.append(descriptor)
            return descriptor

        def failing_fstat(descriptor):
            if descriptor in child_descriptors:
                raise OSError(errno.EIO, "synthetic child fstat failure")
            return original_fstat(descriptor)

        with (
            mock.patch.object(publication.os, "open", side_effect=tracking_open),
            mock.patch.object(publication.os, "fstat", side_effect=failing_fstat),
        ):
            with self.assertRaises(publication.RegularFilePublicationV2NotRunError):
                publication._walk_absolute_directory_nofollow(child)

        self.assertEqual(len(child_descriptors), 1)
        with self.assertRaises(OSError) as observed:
            os.fstat(child_descriptors[0])
        self.assertEqual(observed.exception.errno, errno.EBADF)

    def test_missing_required_flag_refuses_before_path_access(self) -> None:
        calls = 0

        def action() -> list[dict[str, object]]:
            nonlocal calls
            calls += 1
            return []

        with mock.patch.object(publication.os, "O_NOFOLLOW", 0):
            with self.assertRaises(publication.RegularFilePublicationV2NotRunError):
                self._publish(fixture_action=action)
        self.assertEqual(calls, 0)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_crash_after_started_spends_authorization_without_reexecution(self) -> None:
        code = """
import os
import sys
from qmc_bmgs.experiments.countdown_thompson_regular_file_publication_v2 import publish_synthetic_fixture_v2

def hook(event, context):
    if event == 'after_started':
        os._exit(17)

publish_synthetic_fixture_v2(
    sys.argv[1],
    authorization_digest='a' * 64,
    fixture_action=lambda: [{'must_not': 'return'}],
    _event_hook=hook,
)
"""
        environment = os.environ.copy()
        environment["PYTHONPATH"] = os.fspath(
            Path(__file__).resolve().parents[1] / "src"
        )
        completed = subprocess.run(
            [sys.executable, "-c", code, os.fspath(self.output)],
            env=environment,
            check=False,
        )
        self.assertEqual(completed.returncode, 17)
        with self.assertRaises(publication.RegularFilePublicationV2AmbiguousError):
            publication.inspect_synthetic_publication_v2(self.output)
        calls = 0

        def action() -> list[dict[str, object]]:
            nonlocal calls
            calls += 1
            return []

        with self.assertRaises(publication.RegularFilePublicationV2NotRunError):
            self._publish(
                authorization=AUTHORIZATION_B,
                fixture_action=action,
            )
        self.assertEqual(calls, 0)

    @unittest.skipUnless(os.name == "posix", "requires POSIX fork semantics")
    def test_two_processes_have_one_reservation_winner(self) -> None:
        context = multiprocessing.get_context("fork")
        gate = context.Event()
        results = context.Queue()
        processes = [
            context.Process(
                target=_race_worker,
                args=(os.fspath(self.output), authorization, gate, results),
            )
            for authorization in (AUTHORIZATION_A, AUTHORIZATION_B)
        ]
        for process in processes:
            process.start()
        gate.set()
        for process in processes:
            process.join(15)
            self.assertFalse(process.is_alive())
            self.assertEqual(process.exitcode, 0)
        statuses = sorted(results.get(timeout=2) for _ in processes)
        self.assertEqual(statuses, ["COMMITTED", "NOT_RUN"])
        self.assertEqual(
            publication.inspect_synthetic_publication_v2(self.output)["status"],
            "COMMITTED",
        )


if __name__ == "__main__":
    unittest.main()
