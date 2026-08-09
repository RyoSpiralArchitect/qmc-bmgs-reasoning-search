from __future__ import annotations

import subprocess
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

from qmc_bmgs.benchmarks.countdown import CountdownTask
from qmc_bmgs.experiments import countdown_track_a_canary_analysis as analysis
from qmc_bmgs.experiments import countdown_track_a_canary_runner as runner
from qmc_bmgs.experiments.countdown_track_a_canary_manifest import CanaryCell
from qmc_bmgs.substrate.budget import TRACK_A_WORK_AXES, TrackAWorkBudget
from qmc_bmgs.substrate.countdown_search import (
    TrackABudgetProfile,
    TrackAMethodSpec,
)
from qmc_bmgs.substrate.proposals import TrackAProposalSpec
from qmc_bmgs.substrate.trace import sha256_json


@dataclass(frozen=True)
class _SyntheticBundle:
    _payloads: dict[str, object]
    cells: tuple[CanaryCell, ...]
    seal_digest: str

    @property
    def payloads(self) -> dict[str, object]:
        return self._payloads


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
        "host_build": {"fixture": "noncanary_protocol_handshake"},
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
        "required_ancestry": ["2" * 40],
        "runner_build_digest": sha256_json(runner_core),
        "runner_source_files": runner_receipts,
        "schema_version": runner.BUILD_ATTESTATION_SCHEMA_VERSION,
        "search_build_digest": search_build_digest,
        "search_microfixture": search_core["search_microfixture"],
        "search_source_files": search_receipts,
    }
    return runner._BuildAttestation(payload=payload, current_head="3" * 40)


def _fixture(
    repository_root: Path,
    output: Path,
) -> tuple[runner._Preflight, CanaryCell]:
    task = CountdownTask((1, 2, 3, 4, 5, 6), target=720)
    proposal = TrackAProposalSpec("uniform/v1")
    method = TrackAMethodSpec.greedy()
    limits = {axis: 4096 for axis in TRACK_A_WORK_AXES}
    limits["verifier_calls"] = 2
    profile = TrackABudgetProfile(
        profile_id="protocol_handshake_noncanary/v1",
        primary_axis="verifier_calls",
        budget=TrackAWorkBudget(**limits),
    )
    method_manifest_digest = "4" * 64
    task_manifest_digest = "5" * 64
    cell = CanaryCell(
        task_fingerprint=task.task_fingerprint,
        proposal_label="noncanary_uniform",
        proposal_spec_digest=proposal.deterministic_digest,
        method_label="noncanary_greedy",
        method_spec_digest=sha256_json(method.to_dict()),
        method_manifest_digest=method_manifest_digest,
        budget_profile_id=profile.profile_id,
        budget_profile_spec_digest=sha256_json(profile.to_dict()),
        exploration_seed=0,
        task_manifest_digest=task_manifest_digest,
    )
    schedule_digest = sha256_json([cell.to_dict()])
    payloads: dict[str, object] = {
        "tasks.json": {"tasks": [task.to_dict()]},
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
            "runtime_bindings": {"fixture": "noncanary_protocol_handshake"},
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
    bundle = _SyntheticBundle(payloads, (cell,), "6" * 64)
    qualification = {
        "bundle_id": runner.BUNDLE_ID,
        "execution_authorized": False,
        "runtime_bindings_digest": sha256_json(
            payloads["methods.json"]["runtime_bindings"]  # type: ignore[index]
        ),
        "status": "RUNTIME_QUALIFIED",
    }
    preflight = runner._Preflight(
        bundle=bundle,
        cells=(cell,),
        qualification=qualification,
        runtime_qualification_digest=sha256_json(qualification),
        build=_build_attestation(repository_root),
        output_path=output.resolve(),
    )
    return preflight, cell


def _synthetic_git_lookup(
    repository_root: Path,
    *arguments: str,
    synthetic_blobs: dict[str, bytes] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    if arguments == ("rev-parse", "--show-toplevel"):
        return subprocess.CompletedProcess(
            ["git", *arguments],
            0,
            f"{repository_root.resolve()}\n".encode("utf-8"),
            b"",
        )
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
            f"{arguments[3]}\n".encode("utf-8"),
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
            (
                b"100644 blob "
                + b"0" * 40
                + b"\t"
                + relative_path.encode("utf-8")
                + b"\0"
            ),
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


class TrackACanaryProtocolIntegrationTests(unittest.TestCase):
    def test_runner_artifact_passes_independent_analyzer_replay(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(
            prefix="qmc-bmgs-noncanary-protocol-"
        ) as temporary:
            root = Path(temporary)
            artifact = root / "artifact"
            authorization_path = root / "reviewed-authorization.json"
            authorization_relative_path = (
                "docs/preregistrations/synthetic-reviewed-authorization.json"
            )
            reviewed_authorization_revision = "7" * 40
            bundle_path = root / "synthetic-bundle-not-read"
            preflight, cell = _fixture(repository_root, artifact)

            with (
                patch.object(runner, "EXPECTED_CELL_COUNT", 1),
                patch.object(runner, "_recheck_source_closure"),
            ):
                authorization = runner._authorization_payload(preflight)
                authorization_raw = runner._canonical_bytes(authorization)
                authorization_path.write_bytes(authorization_raw)
                published = runner._publish_run_artifact(
                    preflight,
                    authorization,
                    reviewed_authorization_revision=(reviewed_authorization_revision),
                    repository_root=repository_root,
                )

            analyzer_bytes = (
                repository_root / analysis.ANALYZER_RELATIVE_PATH
            ).read_bytes()
            expected_analyzer_build_digest = sha256_json(
                {
                    "byte_count": len(analyzer_bytes),
                    "execution_head_revision": preflight.build.current_head,
                    "relative_path": analysis.ANALYZER_RELATIVE_PATH.as_posix(),
                    "schema_version": analysis.ANALYZER_BUILD_SCHEMA_VERSION,
                    "sha256": analysis._sha256_bytes(analyzer_bytes),
                }
            )
            with (
                patch.object(analysis, "EXPECTED_CELL_COUNT", 1),
                patch.object(
                    analysis,
                    "verify_track_a_canary_bundle",
                    return_value=preflight.bundle,
                ) as verify_bundle,
                patch.object(
                    analysis,
                    "iter_track_a_canary_cells",
                    return_value=(cell,),
                ) as iter_cells,
                patch.object(
                    analysis,
                    "_git_result",
                    side_effect=lambda root_path, *arguments: _synthetic_git_lookup(
                        root_path,
                        *arguments,
                        synthetic_blobs={
                            authorization_relative_path: authorization_raw,
                        },
                    ),
                ),
                patch.object(
                    analysis,
                    "_authorization_repository_location",
                    return_value=(
                        authorization_path.resolve(),
                        authorization_relative_path,
                    ),
                ),
            ):
                validated = analysis._validate_artifact(
                    artifact,
                    bundle_path,
                    authorization_path,
                    authorization["deterministic_digest"],
                    repository_root=repository_root,
                )

            verify_bundle.assert_called_once_with(
                bundle_path,
                repository_root=repository_root,
            )
            iter_cells.assert_called_once_with(preflight.bundle)
            self.assertEqual(
                validated.analyzer_build_digest,
                expected_analyzer_build_digest,
            )
            self.assertEqual(validated.manifest, published)
            self.assertEqual(len(validated.records), 1)
            record = validated.records[0]
            self.assertEqual(record["cell"], cell)
            self.assertEqual(record["summary"], published_record_summary(artifact))
            self.assertEqual(
                published["execution_authorization"],
                authorization,
            )
            self.assertEqual(
                published["runner_build_attestation"]["runner_build_digest"],
                preflight.build.payload["runner_build_digest"],
            )
            self.assertEqual(
                published["runner_build_attestation"]["search_build_digest"],
                preflight.build.payload["search_build_digest"],
            )
            self.assertIn(
                analysis.ANALYZER_RELATIVE_PATH.as_posix(),
                published["runner_build_attestation"]["runner_source_files"],
            )


def published_record_summary(artifact: Path) -> dict[str, object]:
    record = analysis._strict_jsonl((artifact / "records.jsonl").read_bytes())[0]
    return record["search_summary"]


if __name__ == "__main__":
    unittest.main()
