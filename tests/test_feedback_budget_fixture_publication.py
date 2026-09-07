"""Small synthetic rows exercise the exact public192 storage protocol."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts/feedback_budget_fixture_publication.py"
)
SPEC = importlib.util.spec_from_file_location(
    "feedback_budget_fixture_publication_tested", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
PUB = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PUB)


def binding():
    return PUB.digested(
        {
            "schema_version": PUB.DOMAIN + "/binding",
            "fixture_id": PUB.FIXTURE_ID,
            "expected_cell_count": 192,
            "development_execution_authorized": False,
            "schedule_digest": "a" * 64,
        }
    )


def row(index):
    key = {"synthetic_index": index}
    return PUB.digested(
        {
            "schema_version": PUB.DOMAIN + "/record",
            "cell_index": index,
            "cell_id": PUB.sha256_json(key),
            "cell_key": key,
            "search_record": {"synthetic": True},
        }
    )


def receipt():
    return PUB.digested(
        {"schema_version": PUB.DOMAIN + "/receipt", "synthetic_only": True}
    )


def action(emit):
    for index in range(192):
        emit(index, row(index))
    return receipt()


def noop():
    return None


class PublicFixturePublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        # The POSIX walker deliberately rejects macOS /var aliases.
        self.root = Path(self.temporary.name).resolve()
        self.output = self.root / "public192"

    def tearDown(self):
        self.temporary.cleanup()

    def publish(self, selected_action=action, **kwargs):
        return PUB.publish(
            self.output, binding(), selected_action, noop, noop, **kwargs
        )

    def test_exact_matrix_commits_and_independently_inspects(self):
        events = []

        def hook(event, details):
            if event == "after_file_durable":
                events.append(details["name"])

        result = self.publish(_event_hook=hook)
        self.assertEqual(result["status"], "PUBLIC_FULL_SHAPE_COMMITTED")
        self.assertEqual(events[0], "STARTED.json")
        self.assertEqual(events[-1], "COMMIT.json")
        self.assertEqual(len(events), 195)
        observed = PUB.inspect(self.output)
        self.assertEqual(observed.rows, [row(index) for index in range(192)])
        self.assertEqual(observed.binding, binding())
        self.assertEqual(observed.receipt, receipt())
        self.assertEqual(observed.commit, result)
        observed.revalidate()
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o700)
        for path in self.output.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_start_is_durable_before_action_and_checks_bracket_search(self):
        events = []

        def before():
            events.append("pre-action")

        def final():
            events.append("pre-commit")

        def checked(emit):
            events.append("action")
            self.assertTrue((self.output / "STARTED.json").is_file())
            self.assertFalse((self.output / "COMMIT.json").exists())
            return action(emit)

        PUB.publish(self.output, binding(), checked, before, final)
        self.assertEqual(
            events, ["pre-action", "pre-action", "action", "pre-commit", "pre-commit"]
        )

    def test_existing_directory_never_runs_or_adopts_matching_publication(self):
        self.publish()
        before = {path.name: path.read_bytes() for path in self.output.iterdir()}
        with self.assertRaises(FileExistsError):
            self.publish(lambda emit: self.fail("occupied slot executed"))
        self.assertEqual(
            before, {path.name: path.read_bytes() for path in self.output.iterdir()}
        )

    def test_empty_existing_directory_is_also_occupied(self):
        self.output.mkdir()
        with self.assertRaises(FileExistsError):
            self.publish(lambda emit: self.fail("empty slot adopted"))

    def test_bad_binding_never_creates_output(self):
        for field, value in (
            ("schema_version", "old384"),
            ("fixture_id", "other"),
            ("expected_cell_count", 384),
            ("expected_cell_count", True),
            ("development_execution_authorized", True),
        ):
            bad = binding()
            bad[field] = value
            bad.pop("deterministic_digest")
            bad = PUB.digested(bad)
            with (
                self.subTest(field=field, value=value),
                self.assertRaises(PUB.PublicationError),
            ):
                PUB.publish(self.output, bad, action, noop, noop)
            self.assertFalse(self.output.exists())

    def test_wrong_binding_digest_is_rejected(self):
        bad = binding()
        bad["schedule_digest"] = "b" * 64
        with self.assertRaises(PUB.PublicationError):
            PUB.publish(self.output, bad, action, noop, noop)
        self.assertFalse(self.output.exists())

    def test_failure_preserves_durable_partial_rows_and_forbids_resume(self):
        def partial(emit):
            emit(0, row(0))
            emit(1, row(1))
            raise ValueError("synthetic interruption")

        with self.assertRaisesRegex(ValueError, "synthetic interruption"):
            self.publish(partial)
        self.assertEqual(
            set(path.name for path in self.output.iterdir()),
            {"STARTED.json", "cell-000.json", "cell-001.json", "FAILURE.json"},
        )
        failure = PUB.parse((self.output / "FAILURE.json").read_bytes())
        self.assertEqual(failure["completed_cell_count"], 2)
        with self.assertRaises(PUB.PublicationError):
            PUB.inspect(self.output)
        with self.assertRaises(FileExistsError):
            self.publish()

    def test_incomplete_matrix_cannot_commit(self):
        def short(emit):
            emit(0, row(0))
            return receipt()

        with self.assertRaisesRegex(PUB.PublicationError, "incomplete"):
            self.publish(short)
        self.assertFalse((self.output / "COMMIT.json").exists())

    def test_out_of_order_emit_preserves_previous_cell(self):
        def wrong_order(emit):
            emit(0, row(0))
            emit(2, row(2))

        with self.assertRaisesRegex(PUB.PublicationError, "order"):
            self.publish(wrong_order)
        self.assertTrue((self.output / "cell-000.json").is_file())
        self.assertFalse((self.output / "cell-002.json").exists())

    def test_record_identity_types_domain_fields_and_digest_are_checked(self):
        mutations = (
            lambda value: value.update(cell_index=True),
            lambda value: value.update(schema_version="old384/record"),
            lambda value: value.update(cell_id="b" * 64),
            lambda value: value.update(unexpected=True),
            lambda value: value.update(search_record=[]),
        )
        for mutate in mutations:
            candidate = row(1)
            mutate(candidate)
            candidate.pop("deterministic_digest")
            candidate = PUB.digested(candidate)
            with self.assertRaises(PUB.PublicationError):
                PUB.row_bytes(1, candidate)
        candidate = row(0)
        candidate["search_record"]["modified"] = True
        with self.assertRaises(PUB.PublicationError):
            PUB.row_bytes(0, candidate)

    def test_pre_action_failure_creates_nothing(self):
        def fail():
            raise ValueError("source drift")

        with self.assertRaisesRegex(ValueError, "source drift"):
            PUB.publish(self.output, binding(), action, fail, noop)
        self.assertFalse(self.output.exists())

    def test_pre_commit_failure_retains_all_rows_without_commit(self):
        def fail():
            raise ValueError("runtime drift")

        with self.assertRaisesRegex(ValueError, "runtime drift"):
            PUB.publish(self.output, binding(), action, noop, fail)
        self.assertEqual(
            sum(path.name in PUB.CELL_NAMES for path in self.output.iterdir()), 192
        )
        self.assertTrue((self.output / "FAILURE.json").is_file())
        self.assertFalse((self.output / "COMMIT.json").exists())

    def test_symlink_parent_is_rejected_before_action(self):
        alias = self.root / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(PUB.mechanics.RegularFilePublicationV2Error):
            PUB.publish(
                alias / "fixture",
                binding(),
                lambda emit: self.fail("symlink ran"),
                noop,
                noop,
            )

    def test_extra_file_or_conflicting_failure_invalidates_committed_input(self):
        self.publish()
        (self.output / "FAILURE.json").write_bytes(b"{}\n")
        with self.assertRaisesRegex(PUB.PublicationError, "closure"):
            PUB.inspect(self.output)

    def test_hardlinked_or_symlinked_cell_is_rejected(self):
        self.publish()
        cell = self.output / "cell-000.json"
        os.link(cell, self.root / "hardlink")
        with self.assertRaises(PUB.mechanics.RegularFilePublicationV2Error):
            PUB.inspect(self.output)

    def test_snapshot_detects_same_bytes_replaced_inode(self):
        self.publish()
        observed = PUB.inspect(self.output)
        path = self.output / "cell-000.json"
        replacement = self.root / "replacement"
        replacement.write_bytes(path.read_bytes())
        replacement.chmod(0o600)
        replacement.replace(path)
        with self.assertRaises(PUB.PublicationError):
            observed.revalidate()

    def test_inspection_values_are_detached_from_frozen_snapshot(self):
        self.publish()
        observed = PUB.inspect(self.output)
        observed.binding["fixture_id"] = "mutated"
        observed.rows[0]["search_record"].clear()
        observed.receipt["synthetic_only"] = False
        observed.commit.clear()
        self.assertEqual(observed.binding, binding())
        self.assertEqual(observed.rows[0], row(0))
        observed.revalidate()

    def test_modified_commit_and_noncanonical_record_fail(self):
        self.publish()
        commit = self.output / "COMMIT.json"
        value = PUB.parse(commit.read_bytes())
        value["cells"][0]["sha256"] = "c" * 64
        value.pop("deterministic_digest")
        commit.write_bytes(PUB.canonical(PUB.digested(value)))
        with self.assertRaisesRegex(PUB.PublicationError, "commit closure"):
            PUB.inspect(self.output)

    def test_commit_failure_is_uncertain_and_no_failure_receipt_is_added(self):
        original = PUB.mechanics._exclusive_create_exact

        def create(parent, name, payload, **kwargs):
            if name == "COMMIT.json":
                raise OSError("commit storage failure")
            return original(parent, name, payload, **kwargs)

        with (
            patch.object(PUB.mechanics, "_exclusive_create_exact", side_effect=create),
            self.assertRaises(PUB.PublicationUncertain),
        ):
            self.publish()
        self.assertFalse((self.output / "FAILURE.json").exists())
        self.assertTrue((self.output / "RECEIPT.json").exists())

    def test_summary_is_exclusive_and_revalidates_input(self):
        self.publish()
        observed = PUB.inspect(self.output)
        output = self.root / "summary.json"
        result = PUB.publish_summary(output, {"synthetic": True}, observed.revalidate)
        self.assertEqual(result["sha256"], PUB.sha(output.read_bytes()))
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(PUB.mechanics._NameConflictError):
            PUB.publish_summary(output, {"synthetic": True}, observed.revalidate)

    def test_summary_retained_when_post_publication_validation_fails(self):
        calls = []

        def check():
            calls.append(True)
            if len(calls) == 2:
                raise ValueError("input drift")

        output = self.root / "summary.json"
        with self.assertRaises(PUB.PublicationUncertain):
            PUB.publish_summary(output, {"synthetic": True}, check)
        self.assertTrue(output.is_file())


if __name__ == "__main__":
    unittest.main()
