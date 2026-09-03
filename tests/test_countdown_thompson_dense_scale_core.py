from __future__ import annotations

import importlib.util
import os
import stat
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock

from qmc_bmgs.experiments import countdown_thompson_dense_scale_core as core


def fixture_binding(inputs):
    payload = inputs.payload
    return core.with_digest(
        {
            "bundle_id": inputs.bundle_id,
            "execution_mode": core.FIXTURE_EXECUTION_MODE,
            "schedule_digest": inputs.schedule_digest,
            "dense_scale_seal_digest": None,
            "fixture_design_digest": inputs.design_digest,
            "preregistration_file_sha256": None,
            "analysis_manifest_digest": payload["analysis"]["deterministic_digest"],
            "anchor_qualification_digest": core.FROZEN_AUTHORITY[
                "anchor_qualification_digest"
            ],
            "method_manifest_digest": payload["methods"]["deterministic_digest"],
            "budget_manifest_digest": payload["budget"]["deterministic_digest"],
            "proposal_manifest_digest": payload["proposal"]["deterministic_digest"],
            "runtime_binding_digest": payload["runtime_binding"][
                "deterministic_digest"
            ],
        }
    )


def rehash(payload):
    payload = deepcopy(payload)
    payload.pop("deterministic_digest")
    return core.with_digest(payload)


class DenseScalePublicCoreTests(unittest.TestCase):
    def test_public_contract_contains_no_development_tasks_or_schedule(self):
        public = core.public_contract()
        self.assertEqual(
            set(public),
            {
                "analysis",
                "budget",
                "proposal",
                "methods",
                "runtime_binding",
                "schema_version",
            },
        )
        self.assertEqual(
            core.anchor_qualification()["fixture_task"]["inputs"], [1, 2, 3, 4, 5, 6]
        )
        self.assertEqual(core.anchor_qualification()["fixture_task"]["target"], 720)
        for key in ("analysis", "budget", "proposal"):
            self.assertEqual(
                public[key]["deterministic_digest"],
                core.FROZEN_AUTHORITY[key + "_manifest_digest"],
            )

    def test_public_fixture_design_is_fixed_before_execution(self):
        with (
            mock.patch.object(
                core,
                "run_countdown_track_a_search",
                side_effect=AssertionError("search forbidden"),
            ),
            mock.patch.object(
                core.manifest,
                "verify_countdown_thompson_dense_scale_bundle",
                side_effect=AssertionError("sealed read forbidden"),
            ),
        ):
            inputs = core.public_fixture_inputs()
            self.assertEqual(inputs.design_digest, core.FIXTURE_DESIGN_DIGEST)
            self.assertEqual(inputs.schedule_digest, core.FIXTURE_SCHEDULE_DIGEST)
            self.assertEqual(len(inputs.cells), 384)
            self.assertEqual(len({cell.cell_id for cell in inputs.cells}), 384)
            self.assertEqual(
                [task.target for task in inputs.tasks.values()], list(range(1, 13))
            )
            self.assertTrue(
                all(task.inputs == (1, 2, 3, 4, 5, 6) for task in inputs.tasks.values())
            )
            self.assertTrue(
                all(
                    row["cell_key"]["bundle_id"] == core.FIXTURE_BUNDLE_ID
                    for row in inputs.schedule
                )
            )
            self.assertTrue(
                all(
                    row["cell_key"]["schema_version"].startswith(core.FIXTURE_STEM)
                    for row in inputs.schedule
                )
            )
            expected = [
                (task, scale, seed)
                for task in inputs.tasks
                for scale in core.SCALE_ORDER
                for seed in core.EXPLORATION_SEEDS
            ]
            self.assertEqual(
                [
                    (
                        cell.task_fingerprint,
                        cell.terminal_value_scale,
                        cell.exploration_seed,
                    )
                    for cell in inputs.cells
                ],
                expected,
            )
            inputs.revalidate()

    def test_fixture_properties_are_defensive(self):
        inputs = core.public_fixture_inputs()
        inputs.payload["cohort"]["tasks"].clear()
        inputs.schedule[0]["cell_key"]["exploration_seed"] = 0
        inputs.cells[0].key["terminal_value_scale"] = 128
        self.assertEqual(len(inputs.tasks), 12)
        self.assertEqual(inputs.cells[0].exploration_seed, 7168)
        self.assertEqual(inputs.cells[0].terminal_value_scale, 0)

    def test_eight_anchor_traces_reproduce_without_development_access(self):
        with (
            mock.patch.object(
                core.manifest,
                "verify_countdown_thompson_dense_scale_bundle",
                side_effect=AssertionError("sealed read forbidden"),
            ),
            mock.patch.object(
                core,
                "run_countdown_track_a_search",
                wraps=core.run_countdown_track_a_search,
            ) as run,
            mock.patch.object(
                core,
                "replay_countdown_track_a_search_bytes",
                wraps=core.replay_countdown_track_a_search_bytes,
            ) as replay,
        ):
            receipt = core.reproduce_anchor_qualification()
        self.assertEqual(run.call_count, 8)
        self.assertEqual(replay.call_count, 8)
        self.assertEqual(receipt, core.anchor_qualification())
        self.assertFalse(receipt["development_task_access"])
        self.assertEqual(receipt["development_cell_count"], 0)
        self.assertEqual(receipt["raw_trace_persisted_count"], 0)

    def test_qualification_rejects_trace_and_projection_digest_drift(self):
        for field in (
            "expected_authority_trace_sha256",
            "expected_common_projection_digest",
        ):
            with self.subTest(field=field):
                qualification = core.anchor_qualification()
                qualification["receipts"][0][field] = "f" * 64
                with (
                    mock.patch.object(
                        core, "anchor_qualification", return_value=qualification
                    ),
                    self.assertRaises(core.DenseScaleExecutionError),
                ):
                    core.reproduce_anchor_qualification()

    def test_runtime_requires_exact_sealed_binding(self):
        observed = core.runtime_qualification()
        self.assertEqual(observed["provider_calls"], 0)
        self.assertEqual(observed["search_runtime"]["python_version"], "3.13.13")
        with (
            mock.patch.object(core, "search_runtime_metadata", return_value={}),
            self.assertRaises(core.DenseScaleExecutionError),
        ):
            core.runtime_qualification()

    def test_strict_json_rejects_aliases_and_malformed_roots(self):
        for raw in (b"{}", b"[]\n", b'{"x":1,"x":1}\n', b'{"x":NaN}\n', b"{ }\n"):
            with (
                self.subTest(raw=raw),
                self.assertRaises(core.DenseScaleExecutionError),
            ):
                core.parse_canonical(raw)
        for value in (True, 1, "A" * 64, "a" * 63):
            with self.assertRaises(core.DenseScaleExecutionError):
                core.require_sha256(value)


class DenseScaleCellCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = core.public_fixture_inputs()
        cls.cell = cls.inputs.cells[0]
        cls.binding = fixture_binding(cls.inputs)
        cls.row = core.build_record(cls.inputs, cls.cell, cls.binding)

    def test_public_cell_executes_and_independently_replays(self):
        trace = core.verify_record(self.inputs, self.cell, self.row, self.binding)
        self.assertEqual(
            core.canonical_bytes(trace), core.canonical_bytes(self.row["search_record"])
        )
        self.assertEqual(set(self.row), core.RECORD_FIELDS)
        self.assertEqual(self.row["provider_calls"], 0)
        self.assertTrue(self.row["budget_evidence"]["budget_valid"])
        self.assertTrue(
            all(
                value > 0
                for value in self.row["budget_evidence"][
                    "non_primary_headroom"
                ].values()
            )
        )

    def test_wrong_domain_or_cell_is_rejected_before_search(self):
        binding = deepcopy(self.binding)
        binding["bundle_id"] = core.BUNDLE_ID
        key = self.cell.key
        key["terminal_value_scale"] = 0.0
        wrong_cell = core.DenseExecutionCell(core.canonical_bytes(key))
        with mock.patch.object(
            core,
            "run_countdown_track_a_search",
            side_effect=AssertionError("search forbidden"),
        ):
            for cell, proof in (
                (self.cell, rehash(binding)),
                (wrong_cell, self.binding),
            ):
                with self.assertRaises(core.DenseScaleExecutionError):
                    core.build_record(self.inputs, cell, proof)

    def test_unknown_fields_and_provider_aliases_fail_before_replay(self):
        with mock.patch.object(
            core,
            "replay_countdown_track_a_search_bytes",
            side_effect=AssertionError("replay forbidden"),
        ):
            for field, value in (
                ("unknown", 1),
                ("provider_calls", False),
                ("provider_calls", 1),
                ("schema_version", core.RECORD_SCHEMA_VERSION),
            ):
                row = deepcopy(self.row)
                row[field] = value
                with (
                    self.subTest(field=field, value=value),
                    self.assertRaises(core.DenseScaleExecutionError),
                ):
                    core.verify_record(
                        self.inputs, self.cell, rehash(row), self.binding
                    )

    def test_rehashed_receipt_and_budget_tamper_is_not_replay_evidence(self):
        for field, value in (
            ("search_trace_sha256", "f" * 64),
            ("search_trace_byte_count", True),
            ("source_multiset_fingerprint", "0" * 64),
        ):
            row = deepcopy(self.row)
            row[field] = value
            with (
                self.subTest(field=field),
                self.assertRaises(core.DenseScaleExecutionError),
            ):
                core.verify_record(self.inputs, self.cell, rehash(row), self.binding)
        row = deepcopy(self.row)
        row["budget_evidence"]["non_primary_headroom"]["verifier_calls"] = 0
        with self.assertRaises(core.DenseScaleExecutionError):
            core.verify_record(self.inputs, self.cell, rehash(row), self.binding)

    def test_non_primary_exhaustion_or_blocking_is_invalid(self):
        for mutation in ("remaining", "blocked", "budget_valid"):
            trace = deepcopy(self.row["search_record"])
            summary = trace["events"][-1]["payload"]["summary"]
            if mutation == "remaining":
                trace["ledger_snapshot"]["remaining"]["verifier_calls"] = 0
            elif mutation == "blocked":
                summary["stop_blocked_axes"] = ["verifier_calls"]
            else:
                summary["budget_valid"] = 1
            with (
                self.subTest(mutation=mutation),
                self.assertRaises(core.DenseScaleExecutionError),
            ):
                core._budget_evidence(trace, self.inputs.budget)


class DenseScaleSnapshotTests(unittest.TestCase):
    def test_snapshot_rejects_symlink_hardlink_and_rotation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = root / "input.json"
            path.write_bytes(b"{}\n")
            snapshot = core.FileSnapshot.capture(path)
            snapshot.revalidate()
            linked = root / "linked.json"
            linked.symlink_to(path)
            with self.assertRaises(core.DenseScaleExecutionError):
                core.FileSnapshot.capture(linked)
            linked.unlink()
            os.link(path, linked)
            with self.assertRaises(core.DenseScaleExecutionError):
                core.FileSnapshot.capture(path)
            linked.unlink()
            replacement = root / "replacement.json"
            replacement.write_bytes(snapshot.raw)
            os.replace(replacement, path)
            with self.assertRaises(core.DenseScaleExecutionError):
                snapshot.revalidate()

    def test_oversized_file_rejected_before_open_and_fifo_is_not_opened(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = root / "large"
            path.write_bytes(b"abcd")
            with self.assertRaises(core.DenseScaleExecutionError):
                core.FileSnapshot.capture(path, byte_cap=3)
            fifo = root / "fifo"
            os.mkfifo(fifo)
            with self.assertRaises(core.DenseScaleExecutionError):
                core.FileSnapshot.capture(fifo)

    def test_descriptor_close_failure_does_not_report_snapshot_success(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "input"
            path.write_bytes(b"x")
            real_close = os.close

            def close(fd):
                real_close(fd)
                raise OSError("injected close failure")

            with (
                mock.patch.object(core.os, "close", side_effect=close),
                self.assertRaises(core.DenseScaleExecutionError),
            ):
                core.FileSnapshot.capture(path)

    def test_source_startup_requires_empty_owned_private_cache(self):
        with self.assertRaises(core.DenseScaleExecutionError):
            core.runtime_import_policy()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve()
            os.chmod(path, 0o700)
            flags = mock.Mock(safe_path=True)
            with (
                mock.patch.object(sys, "flags", flags),
                mock.patch.object(sys, "dont_write_bytecode", True),
                mock.patch.object(sys, "pycache_prefix", str(path)),
            ):
                policy, observed = core.runtime_import_policy()
                self.assertEqual(observed, path)
                self.assertTrue(policy["bytecode_writes_disabled"])
                (path / "stale.pyc").write_bytes(importlib.util.MAGIC_NUMBER)
                with self.assertRaises(core.DenseScaleExecutionError):
                    core.runtime_import_policy()
                (path / "stale.pyc").unlink()
                os.chmod(path, 0o755)
                with self.assertRaises(core.DenseScaleExecutionError):
                    core.runtime_import_policy()
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o755)


if __name__ == "__main__":
    unittest.main()
