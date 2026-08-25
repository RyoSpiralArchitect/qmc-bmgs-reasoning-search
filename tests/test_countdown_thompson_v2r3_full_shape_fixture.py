from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from qmc_bmgs.experiments import countdown_thompson_diagnostic_analysis as analysis
from qmc_bmgs.experiments import countdown_thompson_diagnostic_runner as runner
from qmc_bmgs.experiments import (
    countdown_thompson_regular_file_publication_v2 as publication,
)
from qmc_bmgs.substrate.trace import sha256_json


def _dummy_build() -> runner._BuildAttestation:
    empty = {"byte_count": 0, "sha256": runner._sha256_bytes(b"")}
    search_receipts = {path: dict(empty) for path in runner._SEARCH_SOURCE_PATHS}
    runner_receipts = {path: dict(empty) for path in runner._RUNNER_SOURCE_PATHS}
    search_core = {
        "host_build": {},
        "numeric_microfixture": {},
        "search_microfixture": {},
        "source_files": search_receipts,
    }
    search_digest = sha256_json(search_core)
    runner_core = {
        "runner_source_files": runner_receipts,
        "search_build_digest": search_digest,
    }
    payload = {
        "authorized_runner_revision": "d" * 40,
        "host_build": {},
        "numeric_microfixture": {},
        "required_ancestry": list(runner.REQUIRED_ANCESTRY),
        "runner_build_digest": sha256_json(runner_core),
        "runner_source_files": runner_receipts,
        "schema_version": runner.BUILD_ATTESTATION_SCHEMA_VERSION,
        "search_build_digest": search_digest,
        "search_microfixture": {},
        "search_source_files": search_receipts,
    }
    return runner._BuildAttestation(payload=payload, current_head="d" * 40)


def _fixture_inputs(
    output: Path,
) -> tuple[
    runner._V2R3ExecutionSnapshot,
    dict[str, object],
    dict[str, object],
]:
    bundle = runner._build_nondiagnostic_full_shape_bundle()
    qualification = {
        "bundle_id": runner._FULL_SHAPE_FIXTURE_BUNDLE_ID,
        "execution_authorized": False,
        "runtime_bindings_digest": sha256_json(
            bundle.payloads["methods.json"]["runtime_bindings"]
        ),
        "status": "NONDIAGNOSTIC_FIXTURE_RUNTIME_QUALIFIED",
    }
    binding = publication.build_synthetic_parent_binding_v2(output)
    layout = publication.RegularFileLayoutV2.from_output_path(output)
    preflight = runner._Preflight(
        bundle=bundle,
        cells=bundle.cells,
        qualification=qualification,
        runtime_qualification_digest=sha256_json(qualification),
        build=_dummy_build(),
        output_path=output,
        publication_backend=runner._REGULAR_FILE_PUBLICATION_BACKEND,
        synthetic_fixture_digest=None,
        artifact_layout=runner._REGULAR_FILE_ARTIFACT_LAYOUT,
        output_path_digest=layout.output_path_digest,
        output_parent_binding=binding,
        publication_environment_requirements=(
            runner._publication_environment_requirements(binding)
        ),
        nondiagnostic_full_shape_fixture_digest=(
            runner._FULL_SHAPE_FIXTURE_DESIGN_DIGEST
        ),
    )
    authorization = runner._full_shape_fixture_authorization_payload(preflight)
    snapshot = runner._snapshot_v2r3_execution_inputs(
        preflight,
        authorization,
        reviewed_authorization_revision="d" * 40,
        execution_mode=runner._FULL_SHAPE_FIXTURE_EXECUTION_MODE,
    )
    return snapshot, authorization, binding


class CountdownThompsonV2R3FullShapeFixtureTests(unittest.TestCase):
    def test_v2r3_summary_writer_requires_post_durability_revalidation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="qmc-v2r3-summary-") as raw:
            root = Path(raw).resolve()
            artifact_parent = root / "artifact-parent"
            summary_parent = root / "summary-parent"
            artifact_parent.mkdir()
            summary_parent.mkdir()
            artifact = artifact_parent / "diagnostic.commit.json"
            destination = summary_parent / "summary.json"
            summary = {
                "analyzer_build_digest": "a" * 64,
                "deterministic_digest": "b" * 64,
            }
            publications = 0

            def publish(
                path: Path,
                payload: bytes,
                *,
                protected_roots: object = (),
                post_durability_check=None,
            ) -> None:
                nonlocal publications
                del protected_roots
                self.assertEqual(path, destination)
                self.assertEqual(payload, analysis._canonical_bytes(summary))
                self.assertIsNotNone(post_durability_check)
                post_durability_check()
                publications += 1

            with (
                patch.object(
                    analysis,
                    "analyze_countdown_thompson_diagnostic_artifact_v2r3",
                    return_value=summary,
                ) as analyze,
                patch.object(
                    analysis,
                    "_atomic_write_no_replace",
                    side_effect=publish,
                ),
            ):
                observed = analysis.write_countdown_thompson_diagnostic_summary_v2r3(
                    artifact,
                    root / "bundle",
                    root / "authorization.json",
                    "c" * 64,
                    "d" * 40,
                    destination,
                    repository_root=Path(__file__).resolve().parents[1],
                )
            self.assertEqual(observed, summary)
            self.assertEqual(publications, 1)
            self.assertEqual(analyze.call_count, 2)

    def test_production_wire_closes_not_run_before_action(self) -> None:
        with tempfile.TemporaryDirectory(prefix="qmc-v2r3-not-run-") as raw:
            output = Path(raw).resolve() / "diagnostic.commit.json"
            binding = publication.build_synthetic_parent_binding_v2(output)
            calls = 0

            def action(
                context: publication.DiagnosticPublicationContextV2,
            ) -> publication.DiagnosticPublicationBatchV2:
                nonlocal calls
                calls += 1
                raise AssertionError(context)

            def refuse() -> None:
                raise RuntimeError("pre-outcome refusal")

            with self.assertRaises(publication.RegularFilePublicationV2NotRunError):
                publication.publish_countdown_thompson_diagnostic_v2(
                    output,
                    authorization_digest="a" * 64,
                    expected_parent_binding=binding,
                    diagnostic_action=action,
                    _pre_outcome_check=refuse,
                )
            inspected = publication.inspect_countdown_thompson_diagnostic_v2(
                output,
                expected_parent_binding=binding,
                authorization_digest="a" * 64,
            )
            self.assertEqual(inspected["status"], "NOT_RUN")
            self.assertEqual(calls, 0)

    def test_production_wire_closes_invalid_after_started(self) -> None:
        with tempfile.TemporaryDirectory(prefix="qmc-v2r3-invalid-") as raw:
            output = Path(raw).resolve() / "diagnostic.commit.json"
            binding = publication.build_synthetic_parent_binding_v2(output)
            with self.assertRaises(publication.RegularFilePublicationV2InvalidError):
                publication.publish_countdown_thompson_diagnostic_v2(
                    output,
                    authorization_digest="b" * 64,
                    expected_parent_binding=binding,
                    diagnostic_action=lambda context: (
                        publication.DiagnosticPublicationBatchV2(
                            records=[],
                            run_manifest={
                                "context": context.artifact_id,
                            },
                        )
                    ),
                )
            inspected = publication.inspect_countdown_thompson_diagnostic_v2(
                output,
                expected_parent_binding=binding,
                authorization_digest="b" * 64,
            )
            self.assertEqual(inspected["status"], "INVALID")

    def test_fixture_authority_is_rejected_by_production_loader(self) -> None:
        with tempfile.TemporaryDirectory(prefix="qmc-v2r3-auth-shape-") as raw:
            root = Path(raw).resolve()
            output = root / "fixture.commit.json"
            _, authorization, _ = _fixture_inputs(output)
            authorization_path = root / "fixture-authorization.json"
            authorization_raw = runner._canonical_bytes(authorization)
            with (
                patch.object(
                    runner,
                    "_authorization_repository_location",
                    return_value=(authorization_path, "fixture-authorization.json"),
                ),
                patch.object(
                    runner,
                    "_strict_canonical_object",
                    return_value=(authorization, authorization_raw),
                ),
                patch.object(
                    runner,
                    "_fresh_preflight",
                    side_effect=AssertionError("sealed preflight must not run"),
                ),
                self.assertRaisesRegex(
                    runner.DiagnosticRunnerError,
                    "authorization schema is unsupported",
                ),
            ):
                runner._load_and_match_authorization(
                    authorization_path,
                    authorization["deterministic_digest"],
                    "d" * 40,
                    bundle_path=root / "sealed-bundle-must-not-open",
                    output_path=output,
                    repository_root=root,
                )

    def test_shared_wire_executes_and_independently_replays_all_240_cells(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="qmc-v2r3-full-shape-") as raw:
            root = Path(raw).resolve()
            output = root / "fixture.commit.json"
            snapshot, authorization, binding = _fixture_inputs(output)
            with patch.object(
                runner,
                "verify_countdown_thompson_diagnostic_bundle",
                side_effect=AssertionError("sealed diagnostic bundle must not open"),
            ):
                published = runner._publish_v2r3_execution(
                    snapshot,
                    pre_outcome_check=lambda: None,
                    post_execution_check=lambda: None,
                )
            verified = publication.verify_countdown_thompson_diagnostic_v2(
                output,
                expected_parent_binding=binding,
                authorization_digest=authorization["deterministic_digest"],
            )
            independent_bundle = analysis._full_shape_fixture_analysis_bundle(
                authorization["method_manifest_digest"]
            )
            self.assertEqual(
                [cell.to_dict() for cell in independent_bundle.cells],
                [cell.to_dict() for cell in snapshot.cells],
            )

            def git_result(
                repository_root: Path,
                *arguments: str,
            ) -> subprocess.CompletedProcess[bytes]:
                if arguments == ("rev-parse", "HEAD"):
                    return subprocess.CompletedProcess(
                        ["git", *arguments],
                        0,
                        ("d" * 40 + "\n").encode("utf-8"),
                        b"",
                    )
                raise AssertionError(f"unexpected Git lookup: {arguments}")

            with (
                patch.object(
                    analysis,
                    "_validate_v2r3_source_provenance",
                    return_value="a" * 64,
                ),
                patch.object(analysis, "_git_result", side_effect=git_result),
            ):
                result = analysis.analyze_countdown_thompson_nondiagnostic_full_shape_fixture_v2r3(
                    output,
                    authorization,
                    repository_root=Path(__file__).resolve().parents[1],
                )
            self.assertEqual(published["status"], "COMMITTED")
            self.assertEqual(len(verified.records), 240)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(
                result["replay_status"],
                "INDEPENDENT_240_CELL_TWO_STAGE_REPLAY_PASS",
            )
            mutable = verified.records[0]
            mutable["cell_id"] = "mutated"
            self.assertNotEqual(verified.records[0]["cell_id"], "mutated")


if __name__ == "__main__":
    unittest.main()
