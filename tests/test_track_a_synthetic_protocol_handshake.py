from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from unittest.mock import patch

from qmc_bmgs.benchmarks.countdown import CountdownTask
from qmc_bmgs.experiments import countdown_thompson_diagnostic_analysis as analysis
from qmc_bmgs.experiments import countdown_thompson_diagnostic_runner as runner
from qmc_bmgs.experiments.countdown_thompson_diagnostic_manifest import (
    DiagnosticCell,
)
from qmc_bmgs.substrate.budget import TrackAWorkBudget
from qmc_bmgs.substrate.countdown_search import (
    TrackABudgetProfile,
    TrackAMethodSpec,
)
from qmc_bmgs.substrate.proposals import TrackAProposalSpec
from qmc_bmgs.substrate.trace import sha256_json


@dataclass(frozen=True)
class _SyntheticDiagnosticBundle:
    _payloads: dict[str, object]
    cells: tuple[DiagnosticCell, ...]
    seal_digest: str

    @property
    def payloads(self) -> dict[str, object]:
        return self._payloads


@dataclass(frozen=True)
class _PublishedFixture:
    artifact: Path
    authorization: dict[str, object]
    authorization_path: Path
    authorization_raw: bytes
    authorization_relative_path: str
    bundle_path: Path
    cell: DiagnosticCell
    preflight: runner._Preflight
    published_manifest: dict[str, object]


def _source_receipts(
    repository_root: Path,
    relative_paths: tuple[str, ...],
) -> dict[str, dict[str, object]]:
    receipts: dict[str, dict[str, object]] = {}
    for relative_path in relative_paths:
        raw = (repository_root / relative_path).read_bytes()
        receipts[relative_path] = {
            "byte_count": len(raw),
            "sha256": runner._sha256_bytes(raw),
        }
    return receipts


def _build_attestation(repository_root: Path) -> runner._BuildAttestation:
    search_receipts = _source_receipts(
        repository_root,
        runner._SEARCH_SOURCE_PATHS,
    )
    runner_receipts = _source_receipts(
        repository_root,
        runner._RUNNER_SOURCE_PATHS,
    )
    search_core = {
        "host_build": {"fixture": "synthetic_protocol_handshake"},
        "numeric_microfixture": {"fixture": "not_executed"},
        "search_microfixture": {"fixture": "not_executed"},
        "source_files": search_receipts,
    }
    search_build_digest = sha256_json(search_core)
    runner_core = {
        "runner_source_files": runner_receipts,
        "search_build_digest": search_build_digest,
    }
    payload = {
        "authorized_runner_revision": "1" * 40,
        "host_build": search_core["host_build"],
        "numeric_microfixture": search_core["numeric_microfixture"],
        "required_ancestry": list(runner.REQUIRED_ANCESTRY),
        "runner_build_digest": sha256_json(runner_core),
        "runner_source_files": runner_receipts,
        "schema_version": runner.BUILD_ATTESTATION_SCHEMA_VERSION,
        "search_build_digest": search_build_digest,
        "search_microfixture": search_core["search_microfixture"],
        "search_source_files": search_receipts,
    }
    return runner._BuildAttestation(payload=payload, current_head="3" * 40)


def _synthetic_preflight(
    repository_root: Path,
    output: Path,
) -> tuple[runner._Preflight, DiagnosticCell]:
    task = CountdownTask((2, 3, 4, 5, 6, 7), target=42)
    if task.task_fingerprint == runner._MICRO_TASK.task_fingerprint:
        raise AssertionError("synthetic task overlaps the runner diagnostic fixture")
    proposal = TrackAProposalSpec("uniform/v1")
    method = TrackAMethodSpec.greedy()
    profile = TrackABudgetProfile(
        profile_id="score256",
        primary_axis="legal_action_scores",
        budget=TrackAWorkBudget(
            proposal_state_evaluations=87,
            proposal_action_scores=317,
            legal_action_scores=256,
            generated_perturbation_coordinates=316,
            edge_selections=86,
            transitions=86,
            verifier_calls=18,
        ),
    )
    method_manifest_digest = "4" * 64
    task_manifest_digest = "5" * 64
    cell = DiagnosticCell(
        task_fingerprint=task.task_fingerprint,
        proposal_label="synthetic_uniform",
        proposal_spec_digest=proposal.deterministic_digest,
        method_label="synthetic_greedy",
        method_spec_digest=sha256_json(method.to_dict()),
        method_manifest_digest=method_manifest_digest,
        budget_profile_id=profile.profile_id,
        budget_profile_spec_digest=sha256_json(profile.to_dict()),
        exploration_seed=0,
        task_manifest_digest=task_manifest_digest,
    )
    schedule_digest = sha256_json([cell.to_dict()])
    payloads: dict[str, object] = {
        "diagnostic_tasks.json": {"tasks": [task.to_dict()]},
        "proposals.json": {
            "policies": [
                {
                    "label": cell.proposal_label,
                    "spec": proposal.to_dict(),
                    "spec_digest": proposal.deterministic_digest,
                }
            ]
        },
        "methods.json": {
            "deterministic_digest": method_manifest_digest,
            "methods": [
                {
                    "label": cell.method_label,
                    "spec": method.to_dict(),
                    "spec_digest": sha256_json(method.to_dict()),
                }
            ],
            "runtime_bindings": {"fixture": "synthetic_protocol_handshake"},
        },
        "budgets.json": {
            "profiles": [
                {
                    "spec": profile.to_dict(),
                    "spec_digest": sha256_json(profile.to_dict()),
                }
            ]
        },
        "preregistration.json": {
            "bundle_id": runner.BUNDLE_ID,
            "execution_matrix": {
                "cell_count": 1,
                "schedule_digest": schedule_digest,
            },
        },
    }
    bundle = _SyntheticDiagnosticBundle(payloads, (cell,), "6" * 64)
    qualification = {
        "bundle_id": runner.BUNDLE_ID,
        "execution_authorized": False,
        "runtime_bindings_digest": sha256_json(
            payloads["methods.json"]["runtime_bindings"]  # type: ignore[index]
        ),
        "status": "RUNTIME_QUALIFIED",
    }
    return (
        runner._Preflight(
            bundle=bundle,
            cells=(cell,),
            qualification=qualification,
            runtime_qualification_digest=sha256_json(qualification),
            build=_build_attestation(repository_root),
            output_path=output.resolve(),
        ),
        cell,
    )


def _synthetic_git_lookup(
    repository_root: Path,
    *arguments: str,
    synthetic_blobs: dict[str, bytes] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    if arguments == ("rev-parse", "--show-toplevel"):
        return subprocess.CompletedProcess(
            ["git", *arguments],
            0,
            f"{repository_root.resolve()}\n".encode(),
            b"",
        )
    if arguments == ("status", "--porcelain=v1", "--untracked-files=all"):
        return subprocess.CompletedProcess(["git", *arguments], 0, b"", b"")
    if arguments[:2] == ("cat-file", "-t"):
        return subprocess.CompletedProcess(
            ["git", *arguments],
            0,
            b"commit\n",
            b"",
        )
    if arguments[:2] in {("cat-file", "-e"), ("merge-base", "--is-ancestor")}:
        return subprocess.CompletedProcess(["git", *arguments], 0, b"", b"")
    if (
        len(arguments) == 4
        and arguments[:3] == ("ls-files", "--error-unmatch", "--")
        and synthetic_blobs is not None
        and arguments[3] in synthetic_blobs
    ):
        return subprocess.CompletedProcess(
            ["git", *arguments],
            0,
            f"{arguments[3]}\n".encode(),
            b"",
        )
    if (
        len(arguments) == 5
        and arguments[:2] == ("ls-tree", "-z")
        and arguments[3] == "--"
        and synthetic_blobs is not None
        and arguments[4] in synthetic_blobs
    ):
        relative_path = arguments[4]
        return subprocess.CompletedProcess(
            ["git", *arguments],
            0,
            (b"100644 blob " + b"0" * 40 + b"\t" + relative_path.encode() + b"\0"),
            b"",
        )
    if len(arguments) == 2 and arguments[0] == "show":
        _, relative_path = arguments[1].split(":", maxsplit=1)
        if synthetic_blobs is not None and relative_path in synthetic_blobs:
            return subprocess.CompletedProcess(
                ["git", *arguments],
                0,
                synthetic_blobs[relative_path],
                b"",
            )
        source = repository_root.resolve() / relative_path
        if source.is_file():
            return subprocess.CompletedProcess(
                ["git", *arguments],
                0,
                source.read_bytes(),
                b"",
            )
    return subprocess.CompletedProcess(
        ["git", *arguments],
        1,
        b"",
        b"synthetic Git lookup rejected an unexpected command",
    )


def _publish_fixture(
    repository_root: Path,
    root: Path,
) -> _PublishedFixture:
    artifact = root / "synthetic-artifact"
    authorization_path = root / "reviewed-authorization.json"
    authorization_relative_path = (
        "docs/preregistrations/synthetic-diagnostic-protocol-authorization.json"
    )
    bundle_path = root / "sealed-bundle-never-opened"
    preflight, cell = _synthetic_preflight(repository_root, artifact)
    with (
        patch.object(runner, "EXPECTED_CELL_COUNT", 1),
        patch.object(runner, "_recheck_source_closure"),
        patch.object(
            runner,
            "write_countdown_thompson_diagnostic_execution_plan",
            side_effect=AssertionError("planning is forbidden in this fixture"),
        ),
        patch.object(
            runner,
            "run_countdown_thompson_diagnostic",
            side_effect=AssertionError("sealed runner entry point is forbidden"),
        ),
        patch.object(
            runner,
            "_search_microfixture",
            side_effect=AssertionError("diagnostic microfixture is forbidden"),
        ),
    ):
        authorization = runner._authorization_payload(preflight)
        authorization_raw = runner._canonical_bytes(authorization)
        authorization_path.write_bytes(authorization_raw)
        published_manifest = runner._publish_run_artifact(
            preflight,
            authorization,
            reviewed_authorization_revision="7" * 40,
            repository_root=repository_root,
        )
    if bundle_path.exists():
        raise AssertionError("synthetic fixture opened a sealed bundle path")
    return _PublishedFixture(
        artifact=artifact,
        authorization=authorization,
        authorization_path=authorization_path,
        authorization_raw=authorization_raw,
        authorization_relative_path=authorization_relative_path,
        bundle_path=bundle_path,
        cell=cell,
        preflight=preflight,
        published_manifest=published_manifest,
    )


def _analyze_fixture(
    fixture: _PublishedFixture,
    repository_root: Path,
    *,
    authorization_digest: str | None = None,
) -> tuple[analysis._ValidatedRun, int]:
    replay = analysis.replay_countdown_track_a_search_bytes
    with (
        patch.object(analysis, "EXPECTED_CELL_COUNT", 1),
        patch.object(
            analysis,
            "verify_countdown_thompson_diagnostic_bundle",
            return_value=fixture.preflight.bundle,
        ),
        patch.object(
            analysis,
            "iter_countdown_thompson_diagnostic_cells",
            return_value=(fixture.cell,),
        ),
        patch.object(
            analysis,
            "_git_result",
            side_effect=lambda root_path, *arguments: _synthetic_git_lookup(
                root_path,
                *arguments,
                synthetic_blobs={
                    fixture.authorization_relative_path: fixture.authorization_raw,
                },
            ),
        ),
        patch.object(
            analysis,
            "_authorization_repository_location",
            return_value=(
                fixture.authorization_path.resolve(),
                fixture.authorization_relative_path,
            ),
        ),
        patch.object(
            analysis,
            "replay_countdown_track_a_search_bytes",
            wraps=replay,
        ) as replay_mock,
    ):
        validated = analysis._validate_artifact(
            fixture.artifact,
            fixture.bundle_path,
            fixture.authorization_path,
            authorization_digest or str(fixture.authorization["deterministic_digest"]),
            repository_root=repository_root,
        )
    return validated, replay_mock.call_count


def _read_object(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_bytes())
    if type(payload) is not dict:
        raise AssertionError(f"expected JSON object: {path}")
    return payload


def _write_object(path: Path, payload: dict[str, object]) -> None:
    path.write_bytes(runner._canonical_bytes(payload))


def _reseal_manifest_and_commit(
    artifact: Path,
    mutate: Callable[[dict[str, object]], None],
) -> None:
    manifest_path = artifact / "manifest.json"
    manifest = _read_object(manifest_path)
    mutate(manifest)
    manifest["deterministic_digest"] = sha256_json(
        {key: value for key, value in manifest.items() if key != "deterministic_digest"}
    )
    _write_object(manifest_path, manifest)

    commit_path = artifact / "commit.json"
    commit = _read_object(commit_path)
    commit["run_manifest_digest"] = manifest["deterministic_digest"]
    commit["attempt_started_receipt_digest"] = manifest[
        "attempt_started_receipt_digest"
    ]
    commit["deterministic_digest"] = sha256_json(
        {key: value for key, value in commit.items() if key != "deterministic_digest"}
    )
    _write_object(commit_path, commit)


class CountdownThompsonDiagnosticProtocolHandshakeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository_root = Path(__file__).resolve().parents[1]

    def test_diagnostic_runner_artifact_passes_diagnostic_analyzer_replay(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            prefix="qmc-bmgs-synthetic-handshake-"
        ) as temporary:
            fixture = _publish_fixture(self.repository_root, Path(temporary))
            self.assertEqual(
                {path.name for path in fixture.artifact.iterdir()},
                set(runner.ARTIFACT_FILENAMES),
            )
            commit = _read_object(fixture.artifact / "commit.json")
            record = analysis._strict_jsonl(
                (fixture.artifact / "records.jsonl").read_bytes()
            )[0]
            self.assertEqual(commit["status"], "COMMITTED")
            self.assertEqual(
                commit["run_manifest_digest"],
                fixture.published_manifest["deterministic_digest"],
            )
            self.assertEqual(record["replay"]["stage1_generative"], "PASS")
            self.assertEqual(record["replay"]["stage2_byte_identical"], "PASS")

            validated, replay_calls = _analyze_fixture(
                fixture,
                self.repository_root,
            )

            self.assertEqual(replay_calls, 1)
            self.assertEqual(validated.manifest, fixture.published_manifest)
            self.assertEqual(len(validated.records), 1)
            self.assertEqual(validated.records[0]["cell"], fixture.cell)
            self.assertEqual(
                validated.manifest["schema_version"],
                runner.RUN_MANIFEST_SCHEMA_VERSION,
            )
            self.assertEqual(
                commit["schema_version"],
                runner.ARTIFACT_COMMIT_SCHEMA_VERSION,
            )

    def test_reviewed_authorization_tamper_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="qmc-bmgs-synthetic-auth-tamper-"
        ) as temporary:
            fixture = _publish_fixture(self.repository_root, Path(temporary))
            authorization = _read_object(fixture.authorization_path)
            authorization["claim_boundary"] = "tampered synthetic authority"
            authorization["deterministic_digest"] = sha256_json(
                {
                    key: value
                    for key, value in authorization.items()
                    if key != "deterministic_digest"
                }
            )
            _write_object(fixture.authorization_path, authorization)

            with self.assertRaisesRegex(
                analysis.DiagnosticAnalysisError,
                "execution authorization preflight drifted",
            ):
                _analyze_fixture(
                    fixture,
                    self.repository_root,
                    authorization_digest=str(authorization["deterministic_digest"]),
                )

    def test_commit_authority_tamper_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="qmc-bmgs-synthetic-commit-tamper-"
        ) as temporary:
            fixture = _publish_fixture(self.repository_root, Path(temporary))
            commit_path = fixture.artifact / "commit.json"
            commit = _read_object(commit_path)
            commit["status"] = "INVALID"
            commit["deterministic_digest"] = sha256_json(
                {
                    key: value
                    for key, value in commit.items()
                    if key != "deterministic_digest"
                }
            )
            _write_object(commit_path, commit)

            with self.assertRaisesRegex(
                analysis.DiagnosticAnalysisError,
                "artifact commit receipt does not close",
            ):
                _analyze_fixture(fixture, self.repository_root)

    def test_runtime_qualification_tamper_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="qmc-bmgs-synthetic-runtime-tamper-"
        ) as temporary:
            fixture = _publish_fixture(self.repository_root, Path(temporary))

            def mutate(manifest: dict[str, object]) -> None:
                qualification = manifest["runtime_qualification"]
                if type(qualification) is not dict:
                    raise AssertionError("runtime qualification must be an object")
                qualification["status"] = "RUNTIME_DRIFTED"

            _reseal_manifest_and_commit(fixture.artifact, mutate)
            with self.assertRaisesRegex(
                analysis.DiagnosticAnalysisError,
                "execution authorization preflight drifted",
            ):
                _analyze_fixture(fixture, self.repository_root)

    def test_build_receipt_tamper_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="qmc-bmgs-synthetic-build-tamper-"
        ) as temporary:
            fixture = _publish_fixture(self.repository_root, Path(temporary))

            def mutate(manifest: dict[str, object]) -> None:
                attestation = manifest["runner_build_attestation"]
                if type(attestation) is not dict:
                    raise AssertionError("build attestation must be an object")
                search_receipts = attestation["search_source_files"]
                runner_receipts = attestation["runner_source_files"]
                if (
                    type(search_receipts) is not dict
                    or type(runner_receipts) is not dict
                ):
                    raise AssertionError("source receipts must be objects")
                relative = runner._SEARCH_SOURCE_PATHS[0]
                receipt = search_receipts[relative]
                if type(receipt) is not dict:
                    raise AssertionError("source receipt must be an object")
                receipt["sha256"] = "0" * 64
                search_core = {
                    "host_build": attestation["host_build"],
                    "numeric_microfixture": attestation["numeric_microfixture"],
                    "search_microfixture": attestation["search_microfixture"],
                    "source_files": search_receipts,
                }
                attestation["search_build_digest"] = sha256_json(search_core)
                attestation["runner_build_digest"] = sha256_json(
                    {
                        "runner_source_files": runner_receipts,
                        "search_build_digest": attestation["search_build_digest"],
                    }
                )
                started = manifest["attempt_started_receipt"]
                if type(started) is not dict:
                    raise AssertionError("STARTED receipt must be an object")
                started["search_build_digest"] = attestation["search_build_digest"]
                started["runner_build_digest"] = attestation["runner_build_digest"]
                started["deterministic_digest"] = sha256_json(
                    {
                        key: value
                        for key, value in started.items()
                        if key != "deterministic_digest"
                    }
                )
                manifest["attempt_started_receipt_digest"] = started[
                    "deterministic_digest"
                ]

            _reseal_manifest_and_commit(fixture.artifact, mutate)
            with self.assertRaisesRegex(
                analysis.DiagnosticAnalysisError,
                "attested source receipt does not match execution-head bytes",
            ):
                _analyze_fixture(fixture, self.repository_root)


if __name__ == "__main__":
    unittest.main()
