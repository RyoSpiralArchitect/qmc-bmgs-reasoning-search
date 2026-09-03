"""Public-only runner checks; never plan or execute a production candidate."""

from __future__ import annotations

import copy
import io
import os
import stat
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from qmc_bmgs.experiments import countdown_thompson_dense_scale_core as core
from qmc_bmgs.experiments import (
    countdown_thompson_dense_scale_publication as publication,
)
from qmc_bmgs.experiments import countdown_thompson_dense_scale_runner as runner


RUNNER_REVISION = "a" * 40
AUTHORIZATION_REVISION = "b" * 40
HEAD_REVISION = "c" * 40


def redigest(value: dict) -> dict:
    return core.with_digest(
        {key: item for key, item in value.items() if key != "deterministic_digest"}
    )


def build_receipt() -> dict:
    receipts = {
        path: {"byte_count": 1, "sha256": "a" * 64}
        for path in core.PROTECTED_SOURCE_PATHS
    }
    return core.with_digest(
        {
            "schema_version": core.BUILD_SCHEMA_VERSION,
            "runner_revision": RUNNER_REVISION,
            "source_files": receipts,
            "search_build_digest": core.with_digest(
                {path: receipts[path] for path in core.SEARCH_SOURCE_PATHS}
            )["deterministic_digest"],
            "runtime_import_policy": {
                "bytecode_cache_prefix_empty": True,
                "bytecode_cache_prefix_mode": "0700",
                "bytecode_cache_prefix_owner": "effective_user",
                "bytecode_writes_disabled": True,
                "import_safe_path": True,
                "loader_policy": "exact_source_file_loader_no_cache/v1",
            },
        }
    )


def runtime_receipt() -> dict:
    public = core.public_contract()["runtime_binding"]
    iid = public["iid_runtime"]["metadata"]
    sobol = {
        key: value
        for key, value in iid.items()
        if key not in {"iid_counter_hash", "iid_open_unit_bits"}
    }
    sobol.update(
        source="sobol",
        generator_version="public-test-sobol/v1",
        sobol_maxbit=30,
        sobol_maxdim=21201,
        sobol_randomization="full-sha256-cranley-patterson-rotation",
    )
    return core.with_digest(
        {
            "schema_version": core.RUNTIME_SCHEMA_VERSION,
            "search_runtime": public["search_runtime"]["metadata"],
            "iid_runtime": iid,
            "sobol_runtime": sobol,
            "host": {
                "architecture": "arm64",
                "node": "public-unit-fixture",
                "platform": "public-unit-fixture",
                "python_version": "3.13.13",
            },
            "provider_calls": 0,
        }
    )


class DenseRunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.repository = self.root / "repo"
        self.output_parent = self.root / "run"
        self.authority_parent = self.root / "authority"
        for path in (self.repository, self.output_parent, self.authority_parent):
            path.mkdir()
        self.output = self.output_parent / "public-fixture.commit.json"
        self.authority_path = self.authority_parent / "fixture.authorization.json"
        self.inputs = core.public_fixture_inputs()
        self.build = build_receipt()
        self.runtime = runtime_receipt()
        self.qualification = core.anchor_qualification()
        self.binding = publication.capture_dense_parent_binding(self.output)
        self.payload = runner._authorization_payload(
            self.inputs,
            self.output,
            self.binding,
            self.build,
            self.qualification,
            self.runtime,
        )
        self.raw = core.canonical_bytes(self.payload)

    def safe_loader(self, **changes):
        arguments = {
            "authorization_digest": self.payload["deterministic_digest"],
            "authorization_revision": RUNNER_REVISION,
            "repository_root": self.repository,
            "fixture": True,
        }
        arguments.update(changes)
        return runner.load_reviewed_authorization(self.authority_path, **arguments)

    def fixture_source_mocks(self, stack: ExitStack) -> None:
        stack.enter_context(
            patch.object(core, "git_head", return_value=RUNNER_REVISION)
        )
        stack.enter_context(patch.object(core, "require_ancestor"))
        stack.enter_context(
            patch.object(core, "source_attestation", return_value=self.build)
        )
        stack.enter_context(
            patch.object(core, "runtime_qualification", return_value=self.runtime)
        )

    def test_exact_fixture_fields_and_roundtrip(self) -> None:
        self.assertEqual(len(runner.AUTHORIZATION_FIELDS), 28)
        self.assertEqual(len(runner.FIXTURE_AUTHORIZATION_FIELDS), 29)
        self.assertEqual(set(self.payload), runner.FIXTURE_AUTHORIZATION_FIELDS)
        self.assertEqual(
            runner.validate_authorization(self.raw, fixture=True), self.payload
        )
        self.assertIsNone(self.payload["dense_scale_seal_digest"])
        self.assertIsNone(self.payload["preregistration_file_sha256"])

    def test_production_rejects_fixture_before_any_bundle_or_output_access(
        self,
    ) -> None:
        with ExitStack() as stack:
            bundle = stack.enter_context(
                patch.object(
                    core,
                    "load_production_inputs",
                    side_effect=AssertionError("sealed access"),
                )
            )
            search = stack.enter_context(
                patch.object(
                    core,
                    "build_record",
                    side_effect=AssertionError("development search"),
                )
            )
            output = stack.enter_context(
                patch.object(
                    publication,
                    "preflight_dense_parent_binding",
                    side_effect=AssertionError("output access"),
                )
            )
            with self.assertRaises(core.DenseScaleExecutionError):
                runner.validate_authorization(self.raw)
            bundle.assert_not_called()
            search.assert_not_called()
            output.assert_not_called()

    def test_closed_nested_receipts_reject_canonical_tampering(self) -> None:
        mutations = [
            lambda row: row.update(extra="foreign"),
            lambda row: row.update(cell_count=True),
            lambda row: row.update(requires_explicit_digest_confirmation=1),
            lambda row: row.update(fixture_design_digest="f" * 64),
            lambda row: row.update(dense_scale_seal_digest="f" * 64),
            lambda row: row.update(preregistration_file_sha256="f" * 64),
            lambda row: row["publication_environment_requirements"].update(
                extra="foreign"
            ),
            lambda row: row["output_parent_binding"]["component_identities"][0].update(
                st_dev=True
            ),
            lambda row: row["anchor_qualification"].update(extra="foreign"),
            lambda row: row["runner_build_attestation"].update(extra="foreign"),
            lambda row: row["runner_build_attestation"]["source_files"].pop(
                core.PROTECTED_SOURCE_PATHS[0]
            ),
            lambda row: row["runner_build_attestation"]["runtime_import_policy"].update(
                import_safe_path=1
            ),
            lambda row: row["runtime_qualification"]["host"].update(extra="foreign"),
            lambda row: row["runtime_qualification"]["sobol_runtime"].update(
                extra="foreign"
            ),
            lambda row: row["runtime_qualification"].update(provider_calls=False),
        ]
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index):
                row = copy.deepcopy(self.payload)
                mutation(row)
                for field in ("runner_build_attestation", "runtime_qualification"):
                    row[field] = redigest(row[field])
                row["runtime_qualification_digest"] = row["runtime_qualification"][
                    "deterministic_digest"
                ]
                with self.assertRaises(
                    (core.DenseScaleExecutionError, publication.DensePublicationError)
                ):
                    runner.validate_authorization(
                        core.canonical_bytes(redigest(row)), fixture=True
                    )

    def test_wrong_domains_and_noncanonical_bytes_are_refused(self) -> None:
        for schema in (
            runner.AUTHORIZATION_SCHEMA,
            "qmc-bmgs-countdown-thompson-diagnostic-execution-authorization/v2",
            "qmc-bmgs-countdown-track-a-canary-execution-authorization/v2",
        ):
            row = redigest({**self.payload, "schema_version": schema})
            with (
                self.subTest(schema=schema),
                self.assertRaises(core.DenseScaleExecutionError),
            ):
                runner.validate_authorization(core.canonical_bytes(row), fixture=True)
        with self.assertRaises(core.DenseScaleExecutionError):
            runner.validate_authorization(self.raw + b"\n", fixture=True)

    def test_external_fixture_authority_is_independently_snapshotted(self) -> None:
        runner.write_authorization_exclusive(self.authority_path, self.raw)
        with ExitStack() as stack:
            self.fixture_source_mocks(stack)
            observed = self.safe_loader()
            self.assertEqual(observed.raw, self.raw)
            observed.payload["bundle_id"] = "mutated caller copy"
            self.assertEqual(observed.payload["bundle_id"], self.inputs.bundle_id)
            observed.revalidate()
            with self.authority_path.open("ab") as handle:
                handle.write(b" ")
            with self.assertRaises(core.DenseScaleExecutionError):
                observed.revalidate()

    def test_fixture_revision_is_source_epoch_not_merged_authority(self) -> None:
        runner.write_authorization_exclusive(self.authority_path, self.raw)
        with ExitStack() as stack:
            self.fixture_source_mocks(stack)
            with self.assertRaisesRegex(
                core.DenseScaleExecutionError, "source-review epoch"
            ):
                self.safe_loader(authorization_revision=AUTHORIZATION_REVISION)
            with self.assertRaises(core.DenseScaleExecutionError):
                self.safe_loader(authorization_digest="f" * 64)

    def test_fixture_authority_can_be_analyzed_but_not_rerun_on_descendant(
        self,
    ) -> None:
        runner.write_authorization_exclusive(self.authority_path, self.raw)
        with ExitStack() as stack:
            self.fixture_source_mocks(stack)
            stack.enter_context(
                patch.object(core, "git_head", return_value=HEAD_REVISION)
            )
            authority = self.safe_loader()
            self.assertEqual(authority.execution_head, HEAD_REVISION)
            authority.revalidate()
            with patch.object(
                publication, "publish_dense_scale_fixture_v2r3"
            ) as publisher:
                with self.assertRaisesRegex(
                    core.DenseScaleExecutionError, "exact source-review epoch"
                ):
                    runner._execute(authority, self.inputs)
                publisher.assert_not_called()

    def test_fixture_authority_cannot_be_in_repository_or_output_parent(self) -> None:
        for destination in (
            self.repository / "candidate.json",
            self.output_parent / "candidate.json",
        ):
            runner.write_authorization_exclusive(destination, self.raw)
            with (
                self.subTest(destination=destination),
                self.assertRaises(core.DenseScaleExecutionError),
            ):
                runner.load_reviewed_authorization(
                    destination,
                    authorization_digest=self.payload["deterministic_digest"],
                    authorization_revision=RUNNER_REVISION,
                    repository_root=self.repository,
                    fixture=True,
                )

    def test_runtime_and_source_receipt_drift_are_refused_before_bundle_reads(
        self,
    ) -> None:
        runner.write_authorization_exclusive(self.authority_path, self.raw)
        with ExitStack() as stack:
            self.fixture_source_mocks(stack)
            bundle = stack.enter_context(
                patch.object(
                    core,
                    "load_production_inputs",
                    side_effect=AssertionError("sealed access"),
                )
            )
            with (
                patch.object(core, "source_attestation", return_value={}),
                self.assertRaises(core.DenseScaleExecutionError),
            ):
                self.safe_loader()
            with (
                patch.object(core, "runtime_qualification", return_value={}),
                self.assertRaises(core.DenseScaleExecutionError),
            ):
                self.safe_loader()
            bundle.assert_not_called()

    def test_authorization_only_git_delta_and_exact_blobs(self) -> None:
        path = self.repository / "candidate.json"
        raw = b"{}\n"  # inert mock bytes, not a production candidate
        payload = {
            "runner_build_attestation": self.build,
            "runtime_qualification": self.runtime,
        }

        def git_bytes(root, *args):
            if args[0] == "diff":
                return b"A\0candidate.json\0"
            if args[0] == "ls-tree":
                return b"100644 blob " + b"d" * 40 + b"\tcandidate.json\0"
            if args[0] == "show":
                return raw
            raise AssertionError(args)

        with ExitStack() as stack:
            self.fixture_source_mocks(stack)
            stack.enter_context(
                patch.object(core, "git_head", return_value=AUTHORIZATION_REVISION)
            )
            stack.enter_context(patch.object(core, "git_bytes", side_effect=git_bytes))
            result = runner._verify_reviewed_bytes(
                root=self.repository,
                path=path,
                raw=raw,
                payload=payload,
                authorization_revision=AUTHORIZATION_REVISION,
                fixture=False,
            )
            self.assertEqual(result, AUTHORIZATION_REVISION)
            for bad_delta in (
                b"M\0candidate.json\0",
                b"A\0candidate.json\0M\0README.md\0",
                b"",
            ):

                def wrong_delta(root, *args, delta=bad_delta):
                    return delta if args[0] == "diff" else git_bytes(root, *args)

                with (
                    self.subTest(delta=bad_delta),
                    patch.object(core, "git_bytes", side_effect=wrong_delta),
                    self.assertRaises(core.DenseScaleExecutionError),
                ):
                    runner._verify_reviewed_bytes(
                        root=self.repository,
                        path=path,
                        raw=raw,
                        payload=payload,
                        authorization_revision=AUTHORIZATION_REVISION,
                        fixture=False,
                    )

    def test_exclusive_writer_roundtrip_mode_and_no_overwrite(self) -> None:
        runner.write_authorization_exclusive(self.authority_path, self.raw)
        self.assertEqual(self.authority_path.read_bytes(), self.raw)
        self.assertEqual(self.authority_path.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(runner.DenseRunnerError):
            runner.write_authorization_exclusive(self.authority_path, self.raw)
        self.assertEqual(self.authority_path.read_bytes(), self.raw)

    def test_exclusive_writer_handles_short_writes(self) -> None:
        real_write = os.write
        with patch.object(
            runner.os, "write", side_effect=lambda fd, raw: real_write(fd, raw[:7])
        ):
            runner.write_authorization_exclusive(self.authority_path, self.raw)
        self.assertEqual(self.authority_path.read_bytes(), self.raw)

    def test_exclusive_writer_preserves_uncertain_file(self) -> None:
        with patch.object(
            runner.os, "fsync", side_effect=OSError("injected durability failure")
        ):
            with self.assertRaises(runner.AuthorizationPublicationAmbiguous):
                runner.write_authorization_exclusive(self.authority_path, self.raw)
        self.assertTrue(self.authority_path.exists())
        with self.assertRaises(runner.DenseRunnerError):
            runner.write_authorization_exclusive(self.authority_path, self.raw)

    def test_exclusive_writer_close_failure_stays_ambiguous(self) -> None:
        real_close = os.close

        def close(descriptor):
            regular = stat.S_ISREG(os.fstat(descriptor).st_mode)
            real_close(descriptor)
            if regular:
                raise OSError("injected regular-file close failure")

        with patch.object(runner.os, "close", side_effect=close):
            with self.assertRaises(runner.AuthorizationPublicationAmbiguous):
                runner.write_authorization_exclusive(self.authority_path, self.raw)
        self.assertEqual(self.authority_path.read_bytes(), self.raw)

    def test_exclusive_writer_same_inode_mutation_across_barrier_is_ambiguous(
        self,
    ) -> None:
        real_fsync = os.fsync

        def fsync(descriptor):
            real_fsync(descriptor)
            if stat.S_ISDIR(os.fstat(descriptor).st_mode):
                with self.authority_path.open("ab") as handle:
                    handle.write(b" ")

        with patch.object(runner.os, "fsync", side_effect=fsync):
            with self.assertRaises(runner.AuthorizationPublicationAmbiguous):
                runner.write_authorization_exclusive(self.authority_path, self.raw)
        self.assertTrue(self.authority_path.exists())

    def test_exclusive_writer_refuses_symlink_parent_and_file(self) -> None:
        link = self.root / "alias"
        link.symlink_to(self.authority_parent, target_is_directory=True)
        with self.assertRaises(runner.DenseRunnerError):
            runner.write_authorization_exclusive(link / "candidate.json", self.raw)
        self.assertFalse((self.authority_parent / "candidate.json").exists())
        self.authority_path.symlink_to(self.root / "absent-target")
        with self.assertRaises(runner.DenseRunnerError):
            runner.write_authorization_exclusive(self.authority_path, self.raw)
        self.assertTrue(self.authority_path.is_symlink())

    def test_exclusive_writer_race_has_one_winner(self) -> None:
        def invoke():
            try:
                runner.write_authorization_exclusive(self.authority_path, self.raw)
                return "written"
            except runner.DenseRunnerError:
                return "refused"

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(lambda _: invoke(), range(2)))
        self.assertEqual(sorted(statuses), ["refused", "written"])
        self.assertEqual(self.authority_path.read_bytes(), self.raw)

    def test_self_test_and_malformed_cli_never_enter_production(self) -> None:
        bad_arguments = [
            [],
            ["--run", "sealed"],
            ["--plan", "sealed"],
            ["--self-test", "--output", "/tmp/not-used"],
            ["--self-test", "--run", "sealed"],
            ["--unknown"],
        ]
        with ExitStack() as stack:
            sealed = stack.enter_context(
                patch.object(
                    core,
                    "load_production_inputs",
                    side_effect=AssertionError("sealed access"),
                )
            )
            search = stack.enter_context(
                patch.object(
                    core, "build_record", side_effect=AssertionError("search access")
                )
            )
            stack.enter_context(
                patch.object(
                    runner, "plan_execution", side_effect=AssertionError("planning")
                )
            )
            stack.enter_context(
                patch.object(
                    runner,
                    "run_execution",
                    side_effect=AssertionError("production run"),
                )
            )
            self.assertEqual(runner.self_test()["status"], "PASS")
            for arguments in bad_arguments:
                output = io.StringIO()
                with self.subTest(arguments=arguments), redirect_stdout(output):
                    self.assertEqual(runner.main(arguments), 2)
                self.assertEqual(
                    core.parse_canonical(output.getvalue().encode())["status"],
                    "NOT_RUN",
                )
            sealed.assert_not_called()
            search.assert_not_called()

    def test_candidate_path_cannot_modify_sealed_bundle(self) -> None:
        with patch.object(
            core, "source_attestation", side_effect=AssertionError("preflight")
        ) as source:
            with self.assertRaisesRegex(core.DenseScaleExecutionError, "sealed bundle"):
                runner.plan_execution(
                    "docs/preregistrations/countdown_thompson_dense_scale_v5",
                    self.output,
                    "docs/preregistrations/countdown_thompson_dense_scale_v5/authorization.json",
                    repository_root=self.repository,
                )
            source.assert_not_called()

    def test_unexpected_execution_exception_is_canonical_and_not_outcome_text(
        self,
    ) -> None:
        output = io.StringIO()
        with (
            patch.object(
                runner,
                "run_full_shape_fixture",
                side_effect=RuntimeError("terminal outcome must not leak"),
            ),
            redirect_stdout(output),
        ):
            code = runner.main(
                [
                    "--full-shape-fixture",
                    "--output",
                    str(self.output),
                    "--authorization-out",
                    str(self.authority_path),
                    "--repository-root",
                    str(self.repository),
                ]
            )
        result = core.parse_canonical(output.getvalue().encode())
        self.assertEqual(code, 2)
        self.assertEqual(result["status"], "PUBLICATION_STATE_AMBIGUOUS")
        self.assertEqual(result["error"], "RuntimeError")
        self.assertIsNone(result["authorization_consumed"])
        self.assertFalse(result["retry_permitted"])

    def test_shared_action_orders_exact_384_records_between_barriers(self) -> None:
        observed: list[str] = []
        authority = SimpleNamespace(
            fixture=True,
            payload=self.payload,
            raw=self.raw,
            authorization_revision=RUNNER_REVISION,
            execution_head=RUNNER_REVISION,
            revalidate=lambda: observed.append("authority"),
        )
        context = SimpleNamespace(run_binding={"deterministic_digest": "f" * 64})

        def publisher(
            output, *, inputs, action, pre_started_check, pre_commit_check, _event_hook
        ):
            observed.append("reserved")
            pre_started_check()
            observed.append("started")
            batch = action(context)
            self.assertEqual(len(batch.records), 384)
            self.assertEqual(
                tuple(row["cell_id"] for row in batch.records),
                tuple(cell.cell_id for cell in self.inputs.cells),
            )
            observed.append("records")
            pre_commit_check()
            observed.append("committed")
            return {"status": "COMMITTED"}

        def record(inputs, cell, binding):
            self.assertIn("started", observed)
            self.assertNotIn("committed", observed)
            return {"cell_id": cell.cell_id}

        with ExitStack() as stack:
            stack.enter_context(
                patch.object(runner, "_publication_inputs", return_value=object())
            )
            stack.enter_context(
                patch.object(
                    publication,
                    "publish_dense_scale_fixture_v2r3",
                    side_effect=publisher,
                )
            )
            stack.enter_context(
                patch.object(publication, "revalidate_dense_parent_binding")
            )
            stack.enter_context(
                patch.object(
                    core,
                    "reproduce_anchor_qualification",
                    side_effect=lambda: (
                        observed.append("qualification") or self.qualification
                    ),
                )
            )
            records = stack.enter_context(
                patch.object(core, "build_record", side_effect=record)
            )
            result = runner._execute(authority, self.inputs)
        self.assertEqual(result["status"], "COMMITTED")
        self.assertEqual(records.call_count, 384)
        self.assertEqual(
            observed,
            [
                "reserved",
                "authority",
                "qualification",
                "started",
                "records",
                "authority",
                "qualification",
                "committed",
            ],
        )

    def test_qualification_failure_after_attempt_is_spent_not_run(self) -> None:
        authority = SimpleNamespace(
            fixture=True,
            payload=self.payload,
            raw=self.raw,
            authorization_revision=RUNNER_REVISION,
            execution_head=RUNNER_REVISION,
            revalidate=Mock(),
        )
        with (
            patch.object(
                core,
                "reproduce_anchor_qualification",
                side_effect=core.DenseScaleExecutionError("public qualifier mismatch"),
            ),
            patch.object(core, "build_record") as record,
        ):
            with self.assertRaises(publication.DensePublicationNotRunError) as captured:
                runner._execute(authority, self.inputs)
            self.assertTrue(captured.exception.authorization_consumed)
            record.assert_not_called()
            with self.assertRaises(publication.DensePublicationAmbiguousError):
                runner._execute(authority, self.inputs)
            record.assert_not_called()


if __name__ == "__main__":
    unittest.main()
