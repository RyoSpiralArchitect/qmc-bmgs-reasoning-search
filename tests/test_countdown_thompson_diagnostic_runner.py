from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

from qmc_bmgs.benchmarks.countdown import CountdownTask
from qmc_bmgs.experiments import countdown_thompson_diagnostic_runner as runner
from qmc_bmgs.experiments.countdown_thompson_diagnostic_manifest import DiagnosticCell
from qmc_bmgs.substrate.budget import TRACK_A_WORK_AXES, TrackAWorkBudget
from qmc_bmgs.substrate.countdown_search import TrackABudgetProfile, TrackAMethodSpec
from qmc_bmgs.substrate.proposals import TrackAProposalSpec
from qmc_bmgs.substrate.trace import canonical_json, canonical_trace_bytes, sha256_json


_AUTHORIZATION_REVISION = "a" * 40


@dataclass(frozen=True)
class _FakeBundle:
    _payloads: dict[str, object]
    cells: tuple[DiagnosticCell, ...]
    seal_digest: str = runner.EXPECTED_SEAL_DIGEST

    @property
    def payloads(self) -> dict[str, object]:
        return self._payloads


def _profile() -> TrackABudgetProfile:
    limits = {axis: 4096 for axis in TRACK_A_WORK_AXES}
    limits["verifier_calls"] = 2
    return TrackABudgetProfile(
        profile_id="runner_test_nondiagnostic/v1",
        primary_axis="verifier_calls",
        budget=TrackAWorkBudget(**limits),
    )


def _fixture() -> tuple[
    CountdownTask,
    TrackAProposalSpec,
    TrackAMethodSpec,
    TrackABudgetProfile,
    DiagnosticCell,
]:
    task = CountdownTask((1, 2, 3, 4, 5, 6), target=720)
    proposal = TrackAProposalSpec("uniform/v1")
    method = TrackAMethodSpec.greedy()
    profile = _profile()
    cell = DiagnosticCell(
        task_fingerprint=task.task_fingerprint,
        proposal_label="nondiagnostic_uniform",
        proposal_spec_digest=proposal.deterministic_digest,
        method_label="nondiagnostic_greedy",
        method_spec_digest=sha256_json(method.to_dict()),
        method_manifest_digest="b" * 64,
        budget_profile_id=profile.profile_id,
        budget_profile_spec_digest=sha256_json(profile.to_dict()),
        exploration_seed=0,
        task_manifest_digest="c" * 64,
    )
    return task, proposal, method, profile, cell


def _payloads() -> tuple[dict[str, object], DiagnosticCell]:
    task, proposal, method, profile, cell = _fixture()
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
            "deterministic_digest": cell.method_manifest_digest,
            "methods": [
                {
                    "label": cell.method_label,
                    "spec": method.to_dict(),
                    "spec_digest": sha256_json(method.to_dict()),
                }
            ],
            "runtime_bindings": {"fixture": True},
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
            "execution_matrix": {
                "cell_count": 1,
                "schedule_digest": sha256_json([cell.to_dict()]),
            }
        },
    }
    return payloads, cell


def _build_attestation(revision: str = "d" * 40) -> runner._BuildAttestation:
    empty_receipt = {
        "byte_count": 0,
        "sha256": runner._sha256_bytes(b""),
    }
    search_receipts = {
        relative: dict(empty_receipt) for relative in runner._SEARCH_SOURCE_PATHS
    }
    runner_receipts = {
        relative: dict(empty_receipt) for relative in runner._RUNNER_SOURCE_PATHS
    }
    search_core = {
        "host_build": {},
        "numeric_microfixture": {},
        "search_microfixture": {"trace_byte_count": 123},
        "source_files": search_receipts,
    }
    search_build_digest = sha256_json(search_core)
    runner_core = {
        "runner_source_files": runner_receipts,
        "search_build_digest": search_build_digest,
    }
    payload = {
        "authorized_runner_revision": revision,
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
    return runner._BuildAttestation(payload=payload, current_head=revision)


def _preflight(output: Path) -> runner._Preflight:
    payloads, cell = _payloads()
    qualification = {
        "bundle_id": runner.BUNDLE_ID,
        "execution_authorized": False,
        "runtime_bindings_digest": sha256_json({"fixture": True}),
        "status": "RUNTIME_QUALIFIED",
    }
    return runner._Preflight(
        bundle=_FakeBundle(payloads, (cell,)),
        cells=(cell,),
        qualification=qualification,
        runtime_qualification_digest=sha256_json(qualification),
        build=_build_attestation(),
        output_path=output.resolve(),
    )


class CountdownThompsonDiagnosticRunnerTests(unittest.TestCase):
    def test_self_test_uses_only_nondiagnostic_fixture(self) -> None:
        with (
            patch.object(
                runner,
                "verify_countdown_thompson_diagnostic_bundle",
                side_effect=AssertionError("sealed bundle must not be read"),
            ),
            patch.object(
                runner,
                "_qualify_diagnostic_runtime",
                side_effect=AssertionError("diagnostic qualifier must not run"),
            ),
        ):
            result = runner._self_test()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["replay"]["stage1_generative"], "PASS")
        self.assertIn("no sealed outcome", result["claim_boundary"])

    def test_verified_bundle_binds_exact_240_cell_runner_schedule(self) -> None:
        repository = Path(runner.__file__).resolve().parents[3]
        bundle_path = (
            repository / "docs/preregistrations/countdown_thompson_diagnostic_v1"
        )
        with patch.object(
            runner,
            "run_countdown_track_a_search",
            side_effect=AssertionError("diagnostic search must not run"),
        ) as search:
            payloads, raw_files = runner.manifest._read_bundle_snapshot(bundle_path)
            runner.manifest._validate_component_schemas(payloads)
            runner.manifest._validate_local_digests(payloads, raw_files)
            bundle_cells = runner.manifest._cells_from_components(
                payloads["diagnostic_tasks.json"],
                payloads["proposals.json"],
                payloads["methods.json"],
                payloads["budgets.json"],
            )
            bundle = runner.manifest.VerifiedDiagnosticBundle(
                bundle_path,
                payloads,
                bundle_cells,
            )
            cells = runner._validate_schedule(bundle)
            components = runner._resolve_components(bundle.payloads)
        search.assert_not_called()
        self.assertEqual(bundle.seal_digest, runner.EXPECTED_SEAL_DIGEST)
        self.assertEqual(len(cells), 240)
        self.assertEqual(len({cell.cell_id for cell in cells}), 240)
        self.assertEqual({cell.budget_profile_id for cell in cells}, {"score256"})
        self.assertEqual(len(components.tasks), 12)
        self.assertEqual(
            set(components.methods),
            {
                "greedy",
                "beam_width_2",
                "puct_c1",
                "thompson_candidate_iid_v1",
                "thompson_dimnorm_iid_v2",
                "thompson_dense_iid_v3",
                "thompson_greedy_anchor_dense_iid_v4",
            },
        )
        heuristic = [cell for cell in cells if cell.proposal_label == "heuristic"]
        oracle = [
            cell for cell in cells if cell.proposal_label == "oracle_positive_control"
        ]
        deterministic = [
            cell
            for cell in heuristic
            if cell.method_label in {"greedy", "beam_width_2", "puct_c1"}
        ]
        stochastic = [cell for cell in heuristic if cell not in deterministic]
        self.assertEqual(len(deterministic), 36)
        self.assertEqual({cell.exploration_seed for cell in deterministic}, {0})
        self.assertEqual(len(stochastic), 192)
        self.assertEqual(
            {cell.exploration_seed for cell in stochastic},
            {7168, 7169, 7170, 7171},
        )
        self.assertEqual(len(oracle), 12)
        self.assertEqual({cell.method_label for cell in oracle}, {"greedy"})
        self.assertEqual({cell.exploration_seed for cell in oracle}, {0})

    def test_runtime_binding_is_iid_and_search_only(self) -> None:
        frozen = runner._frozen_diagnostic_runtime_bindings()
        self.assertEqual(set(frozen), {"iid", "search"})
        self.assertNotIn("sobol", frozen)
        for binding in frozen.values():
            self.assertEqual(
                binding["digest"],
                sha256_json(binding["metadata"]),
            )

    def test_fresh_runner_import_surface_is_exactly_attested(self) -> None:
        repository = Path(runner.__file__).resolve().parents[3]
        script = """
import json
import sys
from qmc_bmgs.experiments import countdown_thompson_diagnostic_runner as runner
loaded = sorted(
    name
    for name in sys.modules
    if name == "qmc_bmgs" or name.startswith("qmc_bmgs.")
)
print(json.dumps({"loaded": loaded, "protected": sorted(runner._PROTECTED_MODULE_PATHS)}))
"""
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["loaded"], payload["protected"])
        self.assertEqual(len(payload["protected"]), 14)

    def test_single_cell_embeds_replayable_search_and_all_bindings(self) -> None:
        task, proposal, method, profile, cell = _fixture()
        record = runner._execute_cell(
            cell,
            task=task,
            proposal=proposal,
            method=method,
            budget_profile=profile,
            diagnostic_seal_digest="a" * 64,
            method_manifest_digest=cell.method_manifest_digest,
            runtime_qualification_digest="d" * 64,
            runner_build_digest="e" * 64,
            search_build_digest="f" * 64,
        )
        self.assertEqual(record["schema_version"], runner.RUN_RECORD_SCHEMA_VERSION)
        self.assertEqual(record["cell_id"], cell.cell_id)
        self.assertEqual(record["cell_key"], cell.key)
        self.assertEqual(record["diagnostic_seal_digest"], "a" * 64)
        self.assertEqual(record["method_manifest_digest"], "b" * 64)
        self.assertEqual(record["runner_build_digest"], "e" * 64)
        self.assertEqual(record["search_build_digest"], "f" * 64)
        trace_bytes = canonical_trace_bytes(record["search_record"])
        self.assertEqual(record["search_trace_byte_count"], len(trace_bytes))
        self.assertEqual(
            record["search_trace_sha256"], runner._sha256_bytes(trace_bytes)
        )
        self.assertEqual(
            record["replay"]["replayed_sha256"], record["search_trace_sha256"]
        )
        self.assertEqual(record["provider_calls"], 0)
        self.assertEqual(record["telemetry"]["role"], runner._TELEMETRY_ROLE)
        self.assertGreaterEqual(record["telemetry"]["search_wall_time_ns"], 0)
        self.assertGreaterEqual(record["telemetry"]["replay_wall_time_ns"], 0)
        self.assertEqual(
            record["budget_evidence"]["usage"],
            record["search_record"]["ledger_snapshot"]["usage"],
        )
        core = {
            key: value for key, value in record.items() if key != "deterministic_digest"
        }
        self.assertEqual(record["deterministic_digest"], sha256_json(core))

    def test_cell_identity_mismatch_fails_before_search(self) -> None:
        task, proposal, method, profile, cell = _fixture()
        changed = DiagnosticCell(
            **{
                **cell.__dict__,
                "proposal_spec_digest": "0" * 64,
            }
        )
        with patch.object(
            runner,
            "run_countdown_track_a_search",
            side_effect=AssertionError("search must not start"),
        ):
            with self.assertRaisesRegex(
                runner.DiagnosticRunnerError, "proposal digest"
            ):
                runner._execute_cell(
                    changed,
                    task=task,
                    proposal=proposal,
                    method=method,
                    budget_profile=profile,
                    diagnostic_seal_digest="a" * 64,
                    method_manifest_digest=cell.method_manifest_digest,
                    runtime_qualification_digest="d" * 64,
                    runner_build_digest="e" * 64,
                    search_build_digest="f" * 64,
                )

    def test_fresh_runtime_digest_mismatch_stops_before_build_fixture(self) -> None:
        drifted = {
            "bundle_id": runner.BUNDLE_ID,
            "execution_authorized": False,
            "runtime_bindings_digest": "0" * 64,
            "status": "RUNTIME_QUALIFIED",
        }
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / "repository"
            output = Path(temporary) / "output"
            with (
                patch.object(
                    runner,
                    "verify_countdown_thompson_diagnostic_bundle",
                    side_effect=AssertionError("bundle must not be opened"),
                ),
                patch.object(
                    runner,
                    "_qualify_diagnostic_runtime",
                    return_value=drifted,
                ),
                patch.object(
                    runner,
                    "_attest_clean_source_build",
                    side_effect=AssertionError("build fixture must not run"),
                ),
                patch.object(
                    runner,
                    "run_countdown_track_a_search",
                    side_effect=AssertionError("diagnostic search must not run"),
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticRunnerError,
                    "qualification does not match",
                ):
                    runner._fresh_preflight(
                        Path(temporary) / "bundle",
                        output,
                        repository,
                        authorized_runner_revision=None,
                    )

    def test_authorization_is_separate_canonical_reviewed_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            authorization_path = root / "authorization.json"
            preflight = _preflight(output)
            with patch.object(runner, "_fresh_preflight", return_value=preflight):
                receipt = runner.write_countdown_thompson_diagnostic_execution_plan(
                    root / "bundle",
                    output,
                    authorization_path,
                    repository_root=root,
                )
            raw = authorization_path.read_bytes()
            parsed = json.loads(raw)
            self.assertEqual(raw, (canonical_json(parsed) + "\n").encode())
            self.assertEqual(
                receipt["authorization_digest"], parsed["deterministic_digest"]
            )
            with (
                patch.object(runner, "_fresh_preflight", return_value=preflight),
                patch.object(
                    runner,
                    "_validate_reviewed_authorization_blob",
                    return_value=_AUTHORIZATION_REVISION,
                ),
            ):
                observed_preflight, observed = runner._load_and_match_authorization(
                    authorization_path,
                    parsed["deterministic_digest"],
                    _AUTHORIZATION_REVISION,
                    bundle_path=root / "bundle",
                    output_path=output,
                    repository_root=root,
                )
            self.assertIs(observed_preflight, preflight)
            self.assertEqual(observed, parsed)

            with patch.object(
                runner,
                "_fresh_preflight",
                side_effect=AssertionError("preflight must not run"),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticRunnerError,
                    "digest does not exact-match",
                ):
                    runner._load_and_match_authorization(
                        authorization_path,
                        "0" * 64,
                        _AUTHORIZATION_REVISION,
                        bundle_path=root / "bundle",
                        output_path=output,
                        repository_root=root,
                    )

    def test_authorization_parent_sync_failure_returns_exact_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            authorization_path = root / "authorization.json"
            preflight = _preflight(output)
            original_fsync = runner.os.fsync
            call_count = 0

            def fail_after_authorization_rename(descriptor: int) -> None:
                nonlocal call_count
                call_count += 1
                if call_count == 2:
                    raise OSError("authorization parent sync failure")
                original_fsync(descriptor)

            with (
                patch.object(runner, "_fresh_preflight", return_value=preflight),
                patch.object(
                    runner.os,
                    "fsync",
                    side_effect=fail_after_authorization_rename,
                ),
            ):
                receipt = runner.write_countdown_thompson_diagnostic_execution_plan(
                    root / "bundle",
                    output,
                    authorization_path,
                    repository_root=root,
                )
            raw = authorization_path.read_bytes()
            parsed = json.loads(raw)
            self.assertEqual(raw, runner._canonical_bytes(parsed))
            self.assertEqual(
                receipt["authorization_digest"],
                parsed["deterministic_digest"],
            )
            self.assertEqual(
                receipt["status"],
                "PREOUTCOME_AUTHORIZATION_CANDIDATE_WRITTEN",
            )
            self.assertFalse(
                any(
                    path.name.startswith(".authorization.json.tmp-")
                    for path in root.iterdir()
                )
            )

    def test_authorization_parent_drift_revokes_candidate_before_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            authorization_path = root / "authorization.json"
            preflight = _preflight(output)
            original_assert = runner._assert_directory_path_identity
            call_count = 0

            def drift_after_authorization_rename(*args: object) -> None:
                nonlocal call_count
                call_count += 1
                if call_count >= 3:
                    raise runner.DiagnosticRunnerError(
                        "authorization parent path identity changed"
                    )
                original_assert(*args)

            with (
                patch.object(runner, "_fresh_preflight", return_value=preflight),
                patch.object(
                    runner,
                    "_assert_directory_path_identity",
                    side_effect=drift_after_authorization_rename,
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticRunnerError,
                    "authorization parent path identity changed",
                ):
                    runner.write_countdown_thompson_diagnostic_execution_plan(
                        root / "bundle",
                        output,
                        authorization_path,
                        repository_root=root,
                    )
            self.assertFalse(authorization_path.exists())

    def test_authorization_missing_initializer_receipt_stops_before_preflight(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            authorization_path = root / "authorization.json"
            payload = runner._authorization_payload(_preflight(output))
            build = payload["runner_build_attestation"]
            self.assertIsInstance(build, dict)
            build["search_source_files"].pop("src/qmc_bmgs/__init__.py")
            payload["deterministic_digest"] = sha256_json(
                {
                    key: value
                    for key, value in payload.items()
                    if key != "deterministic_digest"
                }
            )
            authorization_path.write_bytes(runner._canonical_bytes(payload))
            with (
                patch.object(
                    runner,
                    "_fresh_preflight",
                    side_effect=AssertionError(
                        "sealed bundle preflight must not start"
                    ),
                ) as fresh_preflight,
                patch.object(
                    runner,
                    "_validate_reviewed_authorization_blob",
                    side_effect=AssertionError("Git review gate must not be reached"),
                ) as review_gate,
                patch.object(
                    runner,
                    "run_countdown_track_a_search",
                    side_effect=AssertionError("diagnostic search must not run"),
                ) as search,
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticRunnerError,
                    "authorized search protected path set drifted",
                ):
                    runner._load_and_match_authorization(
                        authorization_path,
                        payload["deterministic_digest"],
                        _AUTHORIZATION_REVISION,
                        bundle_path=root / "sealed-bundle",
                        output_path=output,
                        repository_root=root,
                    )
            fresh_preflight.assert_not_called()
            review_gate.assert_not_called()
            search.assert_not_called()

    def test_authorization_symlink_and_preflight_swap_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            authorization_path = root / "authorization.json"
            preflight = _preflight(output)
            payload = runner._authorization_payload(preflight)
            authorization_path.write_bytes(runner._canonical_bytes(payload))
            symlink = root / "authorization-link.json"
            symlink.symlink_to(authorization_path)
            with self.assertRaisesRegex(
                runner.DiagnosticRunnerError,
                "must not traverse symlinks",
            ):
                runner._load_and_match_authorization(
                    symlink,
                    payload["deterministic_digest"],
                    _AUTHORIZATION_REVISION,
                    bundle_path=root / "bundle",
                    output_path=output,
                    repository_root=root,
                )

            def swap_authorization(
                *args: object, **kwargs: object
            ) -> runner._Preflight:
                changed = json.loads(json.dumps(payload))
                changed["claim_boundary"] = "changed after initial read"
                core = {
                    key: value
                    for key, value in changed.items()
                    if key != "deterministic_digest"
                }
                changed["deterministic_digest"] = sha256_json(core)
                authorization_path.write_bytes(runner._canonical_bytes(changed))
                return preflight

            with (
                patch.object(
                    runner,
                    "_fresh_preflight",
                    side_effect=swap_authorization,
                ),
                patch.object(
                    runner,
                    "_validate_reviewed_authorization_blob",
                    return_value=_AUTHORIZATION_REVISION,
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticRunnerError,
                    "changed during fresh preflight",
                ):
                    runner._load_and_match_authorization(
                        authorization_path,
                        payload["deterministic_digest"],
                        _AUTHORIZATION_REVISION,
                        bundle_path=root / "bundle",
                        output_path=output,
                        repository_root=root,
                    )

    def test_reviewed_authorization_requires_tracked_exact_blob_and_strict_review(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            authorization = root / "reviews" / "authorization.json"
            authorization.parent.mkdir()
            raw = runner._canonical_bytes({"reviewed": True})
            authorization.write_bytes(raw)
            approved = "a" * 40
            reviewed = "b" * 40
            head = "c" * 40
            ancestry: list[tuple[str, str]] = []

            def git(*args: object) -> str:
                arguments = args[1:]
                if arguments[:1] == ("ls-files",):
                    return "reviews/authorization.json"
                if arguments == ("rev-parse", "HEAD"):
                    return head
                raise AssertionError(arguments)

            def ancestor(root_path: Path, old: str, new: str) -> None:
                ancestry.append((old, new))

            with (
                patch.object(runner, "_git", side_effect=git),
                patch.object(runner, "_git_bytes", return_value=raw),
                patch.object(runner, "_require_ancestor", side_effect=ancestor),
                patch.object(runner, "_require_commit_object"),
                patch.object(runner, "_require_regular_git_blob"),
            ):
                observed = runner._validate_reviewed_authorization_blob(
                    repository_root=root,
                    authorization_path=authorization,
                    authorization_raw=raw,
                    authorized_runner_revision=approved,
                    reviewed_authorization_revision=reviewed,
                )
            self.assertEqual(observed, reviewed)
            self.assertEqual(ancestry, [(approved, reviewed), (reviewed, head)])

            with (
                patch.object(runner, "_git", side_effect=git),
                patch.object(
                    runner,
                    "_require_ancestor",
                    side_effect=AssertionError("same-HEAD plan must fail first"),
                ),
                patch.object(runner, "_require_commit_object"),
                patch.object(runner, "_require_regular_git_blob"),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticRunnerError,
                    "strictly descend",
                ):
                    runner._validate_reviewed_authorization_blob(
                        repository_root=root,
                        authorization_path=authorization,
                        authorization_raw=raw,
                        authorized_runner_revision=reviewed,
                        reviewed_authorization_revision=reviewed,
                    )

            with (
                patch.object(runner, "_git", side_effect=git),
                patch.object(
                    runner,
                    "_git_bytes",
                    side_effect=(raw, b"changed"),
                ),
                patch.object(runner, "_require_ancestor"),
                patch.object(runner, "_require_commit_object"),
                patch.object(runner, "_require_regular_git_blob"),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticRunnerError,
                    "reviewed revision and HEAD blob",
                ):
                    runner._validate_reviewed_authorization_blob(
                        repository_root=root,
                        authorization_path=authorization,
                        authorization_raw=raw,
                        authorized_runner_revision=approved,
                        reviewed_authorization_revision=reviewed,
                    )

    def test_reviewed_authorization_rejects_symlink_blob_and_tag_object(self) -> None:
        def git(root: Path, *arguments: str) -> str:
            result = subprocess.run(
                ["git", *arguments],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            return result.stdout.strip()

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(
                ["git", "config", "user.email", "synthetic@example.invalid"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Synthetic Review"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "commit", "--allow-empty", "-qm", "base"],
                cwd=root,
                check=True,
            )
            approved = git(root, "rev-parse", "HEAD")
            authorization = root / "reviewed-auth.json"
            raw = runner._canonical_bytes({"reviewed": True})
            authorization.symlink_to(raw.decode("utf-8"))
            subprocess.run(
                ["git", "add", "reviewed-auth.json"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "commit", "-qm", "reviewed symlink"],
                cwd=root,
                check=True,
            )
            reviewed_symlink = git(root, "rev-parse", "HEAD")
            authorization.unlink()
            authorization.write_bytes(raw)
            subprocess.run(
                ["git", "add", "reviewed-auth.json"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "commit", "-qm", "regular head"],
                cwd=root,
                check=True,
            )
            with self.assertRaisesRegex(
                runner.DiagnosticRunnerError,
                "regular blob",
            ):
                runner._validate_reviewed_authorization_blob(
                    repository_root=root,
                    authorization_path=authorization,
                    authorization_raw=raw,
                    authorized_runner_revision=approved,
                    reviewed_authorization_revision=reviewed_symlink,
                )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(
                ["git", "config", "user.email", "synthetic@example.invalid"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Synthetic Review"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "commit", "--allow-empty", "-qm", "base"],
                cwd=root,
                check=True,
            )
            approved = git(root, "rev-parse", "HEAD")
            authorization = root / "reviewed-auth.json"
            raw = runner._canonical_bytes({"reviewed": True})
            authorization.write_bytes(raw)
            subprocess.run(
                ["git", "add", "reviewed-auth.json"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "commit", "-qm", "reviewed regular"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "tag", "-am", "reviewed", "reviewed-tag"],
                cwd=root,
                check=True,
            )
            reviewed_tag = git(root, "rev-parse", "reviewed-tag")
            (root / "after.txt").write_text("after\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", "after.txt"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "commit", "-qm", "execution head"],
                cwd=root,
                check=True,
            )
            with self.assertRaisesRegex(
                runner.DiagnosticRunnerError,
                "exact Git commit object",
            ):
                runner._validate_reviewed_authorization_blob(
                    repository_root=root,
                    authorization_path=authorization,
                    authorization_raw=raw,
                    authorized_runner_revision=approved,
                    reviewed_authorization_revision=reviewed_tag,
                )

    def test_public_run_reports_preflight_refusal_as_not_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            authorization = root / "authorization.json"
            authorization.write_bytes(runner._canonical_bytes({"invalid": True}))
            with patch.object(
                runner,
                "_publish_run_artifact",
                side_effect=AssertionError("execution must not start"),
            ):
                with self.assertRaises(runner.DiagnosticNotRunError):
                    runner.run_countdown_thompson_diagnostic(
                        root / "bundle",
                        root / "output",
                        authorization,
                        "0" * 64,
                        _AUTHORIZATION_REVISION,
                        repository_root=root,
                    )

            with (
                patch.object(
                    runner,
                    "_load_and_match_authorization",
                    side_effect=OSError("pre-outcome filesystem failure"),
                ),
                patch.object(
                    runner,
                    "_publish_run_artifact",
                    side_effect=AssertionError("execution must not start"),
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticNotRunError,
                    "pre-outcome filesystem failure",
                ):
                    runner.run_countdown_thompson_diagnostic(
                        root / "bundle",
                        root / "output",
                        authorization,
                        "0" * 64,
                        _AUTHORIZATION_REVISION,
                        repository_root=root,
                    )

    def test_authorization_must_lie_outside_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            with self.assertRaisesRegex(runner.DiagnosticRunnerError, "outside output"):
                runner.write_countdown_thompson_diagnostic_execution_plan(
                    root / "bundle",
                    output,
                    output / "authorization.json",
                    repository_root=root,
                )

    def test_plan_candidate_must_be_written_inside_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "repository"
            repository.mkdir()
            with patch.object(
                runner,
                "_fresh_preflight",
                side_effect=AssertionError("invalid authority path must fail first"),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticRunnerError,
                    "repository-relative regular file",
                ):
                    runner.write_countdown_thompson_diagnostic_execution_plan(
                        root / "bundle",
                        root / "output",
                        root / "outside-authorization.json",
                        repository_root=repository,
                    )

    def test_preflight_requires_artifact_outside_source_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            with patch.object(
                runner,
                "_qualify_diagnostic_runtime",
                side_effect=AssertionError("qualifier must not run"),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticRunnerError,
                    "outside the source repository",
                ):
                    runner._fresh_preflight(
                        repository / "bundle",
                        repository / "artifacts" / "run",
                        repository,
                        authorized_runner_revision=None,
                    )

    def test_fresh_preflight_rechecks_source_after_microfixture_and_bundle(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "repository"
            output = root / "output"
            runtime_bindings = runner._frozen_diagnostic_runtime_bindings()
            qualification = {
                "bundle_id": runner.BUNDLE_ID,
                "execution_authorized": False,
                "runtime_bindings_digest": sha256_json(runtime_bindings),
                "status": "RUNTIME_QUALIFIED",
            }
            bundle = _FakeBundle(
                {
                    "budgets.json": {"profiles": []},
                    "methods.json": {"runtime_bindings": runtime_bindings},
                    "diagnostic_tasks.json": {"tasks": []},
                },
                (),
            )
            events: list[str] = []

            def attest(*args: object, **kwargs: object) -> runner._BuildAttestation:
                events.append("microfixture")
                return _build_attestation()

            def verify(*args: object, **kwargs: object) -> _FakeBundle:
                events.append("bundle")
                return bundle

            def recheck(*args: object, **kwargs: object) -> None:
                events.append("recheck")

            with (
                patch.object(
                    runner,
                    "_qualify_diagnostic_runtime",
                    return_value=qualification,
                ),
                patch.object(
                    runner,
                    "_attest_clean_source_build",
                    side_effect=attest,
                ),
                patch.object(
                    runner,
                    "verify_countdown_thompson_diagnostic_bundle",
                    side_effect=verify,
                ),
                patch.object(runner, "_validate_schedule", return_value=()),
                patch.object(runner, "_validate_outcome_blind_budget_guards"),
                patch.object(
                    runner,
                    "_recheck_source_closure",
                    side_effect=recheck,
                ),
            ):
                runner._fresh_preflight(
                    root / "bundle",
                    output,
                    repository,
                    authorized_runner_revision=None,
                )
            self.assertEqual(events, ["microfixture", "bundle", "recheck"])

    def test_score256_atomic_stochastic_guard_regression_is_rejected(self) -> None:
        invalid_score = {
            "profile_id": "score256",
            "primary_axis": "legal_action_scores",
            "budget": {
                "proposal_state_evaluations": 86,
                "proposal_action_scores": 257,
                "legal_action_scores": 256,
                "generated_perturbation_coordinates": 257,
                "edge_selections": 86,
                "transitions": 86,
                "verifier_calls": 18,
            },
        }
        payloads = {
            "budgets.json": {
                "profile_order": ["score256"],
                "profiles": [{"spec": invalid_score}],
            }
        }
        with self.assertRaisesRegex(
            runner.DiagnosticRunnerError,
            "generated_perturbation_coordinates.*316",
        ):
            runner._validate_outcome_blind_budget_guards(payloads)

        valid_score = {
            **invalid_score,
            "budget": {
                **invalid_score["budget"],
                "proposal_state_evaluations": 87,
                "proposal_action_scores": 317,
                "generated_perturbation_coordinates": 316,
            },
        }
        runner._validate_outcome_blind_budget_guards(
            {
                "budgets.json": {
                    "profile_order": ["score256"],
                    "profiles": [{"spec": valid_score}],
                }
            }
        )

    def test_atomic_artifact_publication_on_nondiagnostic_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            with (
                patch.object(runner, "EXPECTED_CELL_COUNT", 1),
                patch.object(runner, "_recheck_source_closure"),
            ):
                manifest = runner._publish_run_artifact(
                    preflight,
                    authorization,
                    reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                    repository_root=Path(temporary),
                )
            self.assertEqual(
                set(path.name for path in output.iterdir()),
                set(runner.ARTIFACT_FILENAMES),
            )
            self.assertEqual(
                manifest["schema_version"], runner.RUN_MANIFEST_SCHEMA_VERSION
            )
            self.assertEqual(manifest["cell_count"], 1)
            self.assertEqual(manifest["artifact_id"], output.name)
            self.assertEqual(manifest["authorized_output_path"], str(output.resolve()))
            self.assertEqual(
                manifest["execution_authorization"],
                authorization,
            )
            self.assertEqual(
                manifest["reviewed_authorization_revision"],
                _AUTHORIZATION_REVISION,
            )
            self.assertEqual(manifest["attempt_phase"], "READY_TO_COMMIT")
            self.assertEqual(
                manifest["attempt_started_receipt_digest"],
                manifest["attempt_started_receipt"]["deterministic_digest"],
            )
            self.assertEqual(
                manifest["runner_build_attestation"]["runner_build_digest"],
                preflight.build.payload["runner_build_digest"],
            )
            self.assertEqual(
                manifest["runner_build_attestation"]["search_build_digest"],
                preflight.build.payload["search_build_digest"],
            )
            lines = (output / "records.jsonl").read_bytes().splitlines()
            self.assertEqual(len(lines), 1)
            record = json.loads(lines[0])
            self.assertEqual(record["cell_id"], preflight.cells[0].cell_id)
            self.assertEqual(
                manifest["record_digests"], [record["deterministic_digest"]]
            )
            self.assertEqual(
                manifest["telemetry"]["search_wall_time_ns_total"],
                record["telemetry"]["search_wall_time_ns"],
            )
            self.assertEqual(
                manifest["telemetry"]["replay_wall_time_ns_total"],
                record["telemetry"]["replay_wall_time_ns"],
            )
            attempt = Path(temporary) / manifest["attempt_marker_basename"]
            self.assertEqual(
                {path.name for path in attempt.iterdir()},
                {"pre_outcome.json", "ready_to_commit.json", "started.json"},
            )
            self.assertFalse((Path(temporary) / ".artifact.publish-lock").exists())
            with (
                patch.object(runner, "EXPECTED_CELL_COUNT", 1),
                patch.object(runner, "_recheck_source_closure"),
            ):
                with self.assertRaises(runner.DiagnosticNotRunError):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=(_AUTHORIZATION_REVISION),
                        repository_root=Path(temporary),
                    )

    def test_started_failure_retains_invalid_marker_and_staging(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            with (
                patch.object(runner, "EXPECTED_CELL_COUNT", 1),
                patch.object(runner, "_recheck_source_closure"),
                patch.object(
                    runner,
                    "_execute_cell",
                    side_effect=runner.DiagnosticRunnerError("fixture failure"),
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticInvalidRunError,
                    "fixture failure",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=(_AUTHORIZATION_REVISION),
                        repository_root=root,
                    )
            self.assertFalse(output.exists())
            self.assertFalse((root / ".artifact.publish-lock").exists())
            attempt = root / (
                f".artifact.attempt-{authorization['deterministic_digest']}"
            )
            self.assertTrue((attempt / "staging").is_dir())
            self.assertEqual(
                {path.name for path in attempt.iterdir()},
                {"invalid.json", "pre_outcome.json", "staging", "started.json"},
            )
            invalid_raw = (attempt / "invalid.json").read_bytes()
            invalid = json.loads(invalid_raw)
            self.assertEqual(invalid_raw, runner._canonical_bytes(invalid))
            invalid_core = {
                key: value
                for key, value in invalid.items()
                if key != "deterministic_digest"
            }
            self.assertEqual(
                invalid["deterministic_digest"],
                sha256_json(invalid_core),
            )
            self.assertEqual(invalid["phase"], "STARTED")
            self.assertEqual(invalid["status"], "INVALID")
            with (
                patch.object(runner, "EXPECTED_CELL_COUNT", 1),
                patch.object(runner, "_recheck_source_closure"),
                patch.object(
                    runner,
                    "_execute_cell",
                    side_effect=AssertionError("same auth must not retry"),
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticNotRunError,
                    "durable attempt marker",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=(_AUTHORIZATION_REVISION),
                        repository_root=root,
                    )

    def test_post_rename_fsync_failure_cannot_relabel_artifact_invalid(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            original_write = runner._write_canonical_file_noreplace_at

            def commit_then_interrupt(
                directory_fd: int,
                filename: str,
                payload: dict[str, object],
            ) -> None:
                original_write(directory_fd, filename, payload)
                if filename == "commit.json":
                    raise OSError("post-commit publication interruption")

            with (
                patch.object(runner, "EXPECTED_CELL_COUNT", 1),
                patch.object(runner, "_recheck_source_closure"),
                patch.object(
                    runner,
                    "_write_canonical_file_noreplace_at",
                    side_effect=commit_then_interrupt,
                ),
            ):
                manifest = runner._publish_run_artifact(
                    preflight,
                    authorization,
                    reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                    repository_root=root,
                )
            self.assertTrue(output.is_dir())
            attempt = root / manifest["attempt_marker_basename"]
            self.assertTrue((attempt / "ready_to_commit.json").is_file())
            self.assertFalse((attempt / "invalid.json").exists())
            self.assertFalse((root / ".artifact.publish-lock").exists())

    def test_exception_after_successful_rename_keeps_committed_authority(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            original_rename = runner._rename_noreplace_at

            def rename_then_interrupt(
                source_directory_fd: int,
                source_name: str,
                destination_directory_fd: int,
                destination_name: str,
            ) -> None:
                original_rename(
                    source_directory_fd,
                    source_name,
                    destination_directory_fd,
                    destination_name,
                )
                if destination_name == output.name:
                    raise OSError("interrupted after successful rename")

            with (
                patch.object(runner, "EXPECTED_CELL_COUNT", 1),
                patch.object(runner, "_recheck_source_closure"),
                patch.object(
                    runner,
                    "_rename_noreplace_at",
                    side_effect=rename_then_interrupt,
                ),
            ):
                manifest = runner._publish_run_artifact(
                    preflight,
                    authorization,
                    reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                    repository_root=root,
                )
            self.assertTrue(output.is_dir())
            attempt = root / manifest["attempt_marker_basename"]
            self.assertTrue((attempt / "ready_to_commit.json").is_file())
            self.assertFalse((attempt / "invalid.json").exists())

    def test_foreign_output_substitution_never_commits(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            stolen = root / "stolen-staging"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            original_rename = runner._rename_noreplace_at

            def substitute_final_output(
                source_directory_fd: int,
                source_name: str,
                destination_directory_fd: int,
                destination_name: str,
            ) -> None:
                if destination_name != output.name:
                    original_rename(
                        source_directory_fd,
                        source_name,
                        destination_directory_fd,
                        destination_name,
                    )
                    return
                (root / source_name).rename(stolen)
                output.mkdir()
                (output / "foreign.txt").write_text("foreign", encoding="utf-8")
                raise OSError("synthetic final rename ambiguity")

            with (
                patch.object(runner, "EXPECTED_CELL_COUNT", 1),
                patch.object(runner, "_recheck_source_closure"),
                patch.object(
                    runner,
                    "_rename_noreplace_at",
                    side_effect=substitute_final_output,
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticInvalidRunError,
                    "synthetic final rename ambiguity",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=(_AUTHORIZATION_REVISION),
                        repository_root=root,
                    )
            self.assertEqual(
                {path.name for path in output.iterdir()},
                {"foreign.txt"},
            )
            self.assertEqual(
                {path.name for path in stolen.iterdir()},
                {"manifest.json", "records.jsonl"},
            )

    def test_output_parent_symlink_swap_is_not_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            authorized_parent = root / "authorized"
            redirected_parent = root / "redirected"
            displaced_parent = root / "displaced"
            authorized_parent.mkdir()
            redirected_parent.mkdir()
            output = authorized_parent / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            authorized_parent.rename(displaced_parent)
            authorized_parent.symlink_to(redirected_parent, target_is_directory=True)
            with (
                patch.object(runner, "EXPECTED_CELL_COUNT", 1),
                patch.object(runner, "_recheck_source_closure"),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticNotRunError,
                    "must not traverse symlinks",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=(_AUTHORIZATION_REVISION),
                        repository_root=root,
                    )
            self.assertEqual(list(redirected_parent.iterdir()), [])
            self.assertEqual(list(displaced_parent.iterdir()), [])

    def test_started_receipt_ambiguity_is_invalid_not_not_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            original_write = runner._write_attempt_receipt

            def publish_started_then_interrupt(*args: object, **kwargs: object):
                payload = original_write(*args, **kwargs)
                if args[1] == "started.json":
                    raise KeyboardInterrupt("synthetic STARTED ambiguity")
                return payload

            with (
                patch.object(runner, "EXPECTED_CELL_COUNT", 1),
                patch.object(runner, "_recheck_source_closure"),
                patch.object(
                    runner,
                    "_write_attempt_receipt",
                    side_effect=publish_started_then_interrupt,
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticInvalidRunError,
                    "synthetic STARTED ambiguity",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=(_AUTHORIZATION_REVISION),
                        repository_root=root,
                    )
            attempt = root / (
                f".artifact.attempt-{authorization['deterministic_digest']}"
            )
            self.assertEqual(
                {path.name for path in attempt.iterdir()},
                {"invalid.json", "pre_outcome.json", "staging", "started.json"},
            )
            self.assertFalse((attempt / "not_run.json").exists())

    def test_pre_outcome_closure_failure_is_not_run_and_never_resolves_task(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            with (
                patch.object(
                    runner,
                    "_recheck_source_closure",
                    side_effect=runner.DiagnosticRunnerError("source raced"),
                ),
                patch.object(
                    runner,
                    "_resolve_components",
                    side_effect=AssertionError("sealed task must not be resolved"),
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticNotRunError,
                    "source raced",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=(_AUTHORIZATION_REVISION),
                        repository_root=root,
                    )
            attempt = root / (
                f".artifact.attempt-{authorization['deterministic_digest']}"
            )
            self.assertEqual(
                {path.name for path in attempt.iterdir()},
                {"not_run.json", "pre_outcome.json"},
            )
            receipt_raw = (attempt / "not_run.json").read_bytes()
            receipt = json.loads(receipt_raw)
            self.assertEqual(receipt_raw, runner._canonical_bytes(receipt))
            self.assertEqual(receipt["phase"], "PRE_OUTCOME")
            self.assertEqual(receipt["status"], "NOT_RUN")
            self.assertFalse(output.exists())
            self.assertFalse((root / ".artifact.publish-lock").exists())

    def test_attempt_rename_then_raise_continues_terminal_lifecycle(self) -> None:
        for error_type in (OSError, FileExistsError):
            with self.subTest(error_type=error_type.__name__):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    output = root / "artifact"
                    preflight = _preflight(output)
                    authorization = runner._authorization_payload(preflight)
                    attempt_name = (
                        f".artifact.attempt-{authorization['deterministic_digest']}"
                    )
                    original_rename = runner._rename_noreplace_at
                    ambiguity_count = 0

                    def rename_attempt_then_raise(
                        source_directory_fd: int,
                        source_name: str,
                        destination_directory_fd: int,
                        destination_name: str,
                    ) -> None:
                        nonlocal ambiguity_count
                        original_rename(
                            source_directory_fd,
                            source_name,
                            destination_directory_fd,
                            destination_name,
                        )
                        if destination_name == attempt_name:
                            ambiguity_count += 1
                            raise error_type("synthetic attempt rename ambiguity")

                    with (
                        patch.object(runner, "EXPECTED_CELL_COUNT", 1),
                        patch.object(runner, "_recheck_source_closure"),
                        patch.object(
                            runner,
                            "_rename_noreplace_at",
                            side_effect=rename_attempt_then_raise,
                        ),
                    ):
                        manifest = runner._publish_run_artifact(
                            preflight,
                            authorization,
                            reviewed_authorization_revision=(_AUTHORIZATION_REVISION),
                            repository_root=root,
                        )
                    self.assertEqual(ambiguity_count, 1)
                    self.assertEqual(manifest["attempt_marker_basename"], attempt_name)
                    self.assertEqual(manifest["attempt_phase"], "READY_TO_COMMIT")
                    self.assertEqual(
                        {path.name for path in (root / attempt_name).iterdir()},
                        {
                            "pre_outcome.json",
                            "ready_to_commit.json",
                            "started.json",
                        },
                    )
                    self.assertFalse((root / attempt_name / "not_run.json").exists())
                    self.assertFalse((root / attempt_name / "invalid.json").exists())
                    self.assertEqual(
                        {path.name for path in output.iterdir()},
                        set(runner.ARTIFACT_FILENAMES),
                    )
                    self.assertEqual(
                        json.loads((output / "commit.json").read_bytes())["status"],
                        "COMMITTED",
                    )
                    self.assertFalse(
                        any(
                            path.name.startswith(".artifact.attempt-tmp-")
                            for path in root.iterdir()
                        )
                    )

    def test_post_attempt_rename_validation_failure_is_durable_not_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            attempt_name = f".artifact.attempt-{authorization['deterministic_digest']}"
            with (
                patch.object(
                    runner,
                    "_published_attempt_reservation_matches",
                    return_value=False,
                ),
                patch.object(
                    runner,
                    "_resolve_components",
                    side_effect=AssertionError("sealed task must not be resolved"),
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticNotRunError,
                    "publication identity or bytes drifted",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                        repository_root=root,
                    )
            attempt = root / attempt_name
            self.assertEqual(
                {path.name for path in attempt.iterdir()},
                {"not_run.json", "pre_outcome.json"},
            )
            receipt_raw = (attempt / "not_run.json").read_bytes()
            receipt = json.loads(receipt_raw)
            self.assertEqual(receipt_raw, runner._canonical_bytes(receipt))
            self.assertEqual(receipt["phase"], "PRE_OUTCOME")
            self.assertEqual(receipt["status"], "NOT_RUN")
            self.assertFalse(output.exists())

    def test_attempt_parent_sync_failure_is_durable_not_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            original_fsync = runner.os.fsync
            call_count = 0

            def fail_after_attempt_rename(descriptor: int) -> None:
                nonlocal call_count
                call_count += 1
                if call_count == 4:
                    raise OSError("attempt parent sync failure")
                original_fsync(descriptor)

            with (
                patch.object(runner, "EXPECTED_CELL_COUNT", 1),
                patch.object(runner, "_recheck_source_closure"),
                patch.object(runner.os, "fsync", side_effect=fail_after_attempt_rename),
                patch.object(
                    runner,
                    "_resolve_components",
                    side_effect=AssertionError("sealed task must not be resolved"),
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticNotRunError,
                    "attempt reservation parent-directory sync failed",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=(_AUTHORIZATION_REVISION),
                        repository_root=root,
                    )
            attempt = root / (
                f".artifact.attempt-{authorization['deterministic_digest']}"
            )
            self.assertEqual(
                {path.name for path in attempt.iterdir()},
                {"not_run.json", "pre_outcome.json"},
            )
            self.assertFalse(output.exists())
            self.assertFalse((root / ".artifact.publish-lock").exists())

    def test_output_parent_creation_failure_is_canonical_not_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "missing" / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            with (
                patch.object(
                    Path,
                    "mkdir",
                    side_effect=OSError("output parent creation failure"),
                ),
                patch.object(
                    runner,
                    "_open_stable_directory",
                    side_effect=AssertionError("parent must not be opened"),
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticNotRunError,
                    "output parent creation failure",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                        repository_root=root,
                    )

    def test_output_lock_creation_failure_is_canonical_not_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            original_mkdir = runner.os.mkdir

            def fail_lock(
                path: object,
                mode: int = 0o777,
                *,
                dir_fd: int | None = None,
            ) -> None:
                if path == ".artifact.publish-lock" and dir_fd is not None:
                    raise OSError("output lock creation failure")
                original_mkdir(path, mode, dir_fd=dir_fd)

            with (
                patch.object(runner.os, "mkdir", side_effect=fail_lock),
                patch.object(
                    runner,
                    "_publish_run_artifact_locked",
                    side_effect=AssertionError("attempt must not start"),
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticNotRunError,
                    "output lock creation failure",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                        repository_root=root,
                    )
            self.assertFalse((root / ".artifact.publish-lock").exists())

    def test_initial_output_parent_identity_failure_is_canonical_not_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            with (
                patch.object(
                    runner,
                    "_assert_directory_path_identity",
                    side_effect=runner.DiagnosticRunnerError(
                        "output parent identity failure"
                    ),
                ),
                patch.object(
                    runner,
                    "_publish_run_artifact_locked",
                    side_effect=AssertionError("attempt must not start"),
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticNotRunError,
                    "output parent identity failure",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                        repository_root=root,
                    )
            self.assertFalse((root / ".artifact.publish-lock").exists())

    def test_output_lock_serializes_different_authorization_digests(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            (root / ".artifact.publish-lock").mkdir()
            with patch.object(
                runner,
                "_reserve_attempt",
                side_effect=AssertionError("concurrent attempt must not reserve"),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticNotRunError,
                    "publication is locked",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=(_AUTHORIZATION_REVISION),
                        repository_root=root,
                    )

    def test_cli_keeps_plan_self_test_and_run_authority_separate(self) -> None:
        with self.assertRaises(SystemExit):
            runner.main(
                [
                    "--run",
                    "bundle",
                    "--output",
                    "artifact",
                    "--authorization-file",
                    "authorization.json",
                    "--authorization-digest",
                    "0" * 64,
                    "--repository-root",
                    ".",
                ]
            )
        with self.assertRaises(SystemExit):
            runner.main(["--self-test", "--output", "artifact"])
        with self.assertRaises(SystemExit):
            runner.main(["--self-test", "--repository-root", "."])
        with (
            patch.object(runner, "_self_test", return_value={"status": "PASS"}),
            patch("builtins.print") as printed,
        ):
            runner.main(["--self-test"])
        self.assertEqual(json.loads(printed.call_args.args[0])["status"], "PASS")
        with patch.object(
            runner,
            "write_countdown_thompson_diagnostic_execution_plan",
            side_effect=AssertionError("planning must require an explicit root"),
        ):
            with self.assertRaises(SystemExit):
                runner.main(
                    [
                        "--plan",
                        "bundle",
                        "--output",
                        "artifact",
                        "--authorization-out",
                        "authorization.json",
                    ]
                )
        with patch.object(
            runner,
            "run_countdown_thompson_diagnostic",
            side_effect=AssertionError("execution must require an explicit root"),
        ):
            with self.assertRaises(SystemExit):
                runner.main(
                    [
                        "--run",
                        "bundle",
                        "--output",
                        "artifact",
                        "--authorization-file",
                        "authorization.json",
                        "--authorization-digest",
                        "0" * 64,
                        "--authorization-revision",
                        _AUTHORIZATION_REVISION,
                    ]
                )
        with patch.object(
            runner,
            "write_countdown_thompson_diagnostic_execution_plan",
            return_value={"status": "PLANNED"},
        ) as planned:
            runner.main(
                [
                    "--plan",
                    "bundle",
                    "--output",
                    "artifact",
                    "--authorization-out",
                    "authorization.json",
                    "--repository-root",
                    ".",
                ]
            )
        planned.assert_called_once()
        self.assertEqual(planned.call_args.kwargs["repository_root"], Path("."))

        with (
            patch.object(
                runner,
                "write_countdown_thompson_diagnostic_execution_plan",
                side_effect=FileExistsError("authorization destination exists"),
            ),
            patch("builtins.print") as printed,
        ):
            with self.assertRaises(SystemExit) as stopped:
                runner.main(
                    [
                        "--plan",
                        "bundle",
                        "--output",
                        "artifact",
                        "--authorization-out",
                        "authorization.json",
                        "--repository-root",
                        ".",
                    ]
                )
        self.assertEqual(stopped.exception.code, 2)
        refused_raw = printed.call_args.args[0]
        refused = json.loads(refused_raw)
        self.assertEqual(refused_raw, runner.canonical_json(refused))
        self.assertEqual(refused["status"], "NOT_RUN")
        self.assertIn("planning did not complete", refused["claim_boundary"])
        self.assertEqual(refused["reason"], "authorization destination exists")

        with patch.object(
            runner,
            "run_countdown_thompson_diagnostic",
            return_value={"status": "COMMITTED"},
        ) as executed:
            runner.main(
                [
                    "--run",
                    "bundle",
                    "--output",
                    "artifact",
                    "--authorization-file",
                    "authorization.json",
                    "--authorization-digest",
                    "0" * 64,
                    "--authorization-revision",
                    _AUTHORIZATION_REVISION,
                    "--repository-root",
                    ".",
                ]
            )
        self.assertEqual(
            executed.call_args.args[4],
            _AUTHORIZATION_REVISION,
        )

        with (
            patch.object(
                runner,
                "run_countdown_thompson_diagnostic",
                side_effect=runner.DiagnosticInvalidRunError("fixture invalid"),
            ),
            patch("builtins.print") as printed,
        ):
            with self.assertRaises(SystemExit) as stopped:
                runner.main(
                    [
                        "--run",
                        "bundle",
                        "--output",
                        "artifact",
                        "--authorization-file",
                        "authorization.json",
                        "--authorization-digest",
                        "0" * 64,
                        "--authorization-revision",
                        _AUTHORIZATION_REVISION,
                        "--repository-root",
                        ".",
                    ]
                )
        self.assertEqual(stopped.exception.code, 3)
        invalid = json.loads(printed.call_args.args[0])
        self.assertEqual(invalid["status"], "INVALID")
        self.assertIn("durable attempt evidence", invalid["claim_boundary"])

    def test_build_attestation_binds_all_runner_sources_and_import_origins(
        self,
    ) -> None:
        repository = Path(runner.__file__).resolve().parents[3]
        expected_runner_sources = (
            "src/qmc_bmgs/experiments/__init__.py",
            "src/qmc_bmgs/experiments/countdown_track_a_canary_manifest.py",
            "src/qmc_bmgs/experiments/countdown_thompson_diagnostic_manifest.py",
            "src/qmc_bmgs/experiments/countdown_thompson_diagnostic_runner.py",
            "src/qmc_bmgs/experiments/countdown_thompson_diagnostic_analysis.py",
        )
        self.assertEqual(runner._RUNNER_SOURCE_PATHS, expected_runner_sources)
        self.assertEqual(
            {
                "qmc_bmgs.experiments": expected_runner_sources[0],
                runner.canary_manifest.__name__: expected_runner_sources[1],
                runner.manifest.__name__: expected_runner_sources[2],
                runner.__name__: expected_runner_sources[3],
                runner.analysis.__name__: expected_runner_sources[4],
            },
            {
                module: runner._PROTECTED_MODULE_PATHS[module]
                for module in (
                    "qmc_bmgs.experiments",
                    runner.canary_manifest.__name__,
                    runner.manifest.__name__,
                    runner.__name__,
                    runner.analysis.__name__,
                )
            },
        )

        original_git = runner._git

        def clean_tracked_git(root: Path, *arguments: str) -> str:
            if arguments == ("status", "--porcelain=v1", "--untracked-files=all"):
                return ""
            if arguments[:1] == ("ls-files",):
                return "\n".join(
                    (*runner._SEARCH_SOURCE_PATHS, *runner._RUNNER_SOURCE_PATHS)
                )
            return original_git(root, *arguments)

        def local_head_blob(root: Path, *arguments: str) -> bytes:
            self.assertEqual(arguments[0], "show")
            relative = arguments[1].split(":", 1)[1]
            return (root / relative).read_bytes()

        with (
            patch.object(runner, "_git", side_effect=clean_tracked_git),
            patch.object(runner, "_git_bytes", side_effect=local_head_blob),
            patch.object(runner, "_host_build_receipt", return_value={}),
            patch.object(runner, "_numeric_microfixture", return_value={}),
            patch.object(runner, "_search_microfixture", return_value={}),
        ):
            attestation = runner._attest_clean_source_build(
                repository,
                authorized_runner_revision=None,
            )
            self.assertEqual(
                set(attestation.payload["runner_source_files"]),
                set(expected_runner_sources),
            )
            self.assertTrue(
                {
                    "src/qmc_bmgs/__init__.py",
                    "src/qmc_bmgs/benchmarks/__init__.py",
                    "src/qmc_bmgs/substrate/__init__.py",
                }.issubset(attestation.payload["search_source_files"])
            )
            self.assertEqual(
                attestation.current_head,
                original_git(repository, "rev-parse", "HEAD"),
            )

            with patch.object(
                runner.analysis,
                "__file__",
                str(repository / "outside-attested-source.py"),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticRunnerError,
                    "imported protected module is outside attested source",
                ):
                    runner._attest_clean_source_build(
                        repository,
                        authorized_runner_revision=None,
                    )

    def test_attested_source_read_rejects_symlink_and_head_blob_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.py"
            source.write_bytes(b"source\n")
            symlink = root / "source-link.py"
            symlink.symlink_to(source)
            with self.assertRaisesRegex(
                runner.DiagnosticRunnerError,
                "not a regular file",
            ):
                runner._regular_file_receipt(symlink)

        repository = Path(runner.__file__).resolve().parents[3]
        head = runner._git(repository, "rev-parse", "HEAD")
        with patch.object(runner, "_git_bytes", return_value=b"drifted"):
            with self.assertRaisesRegex(
                runner.DiagnosticRunnerError,
                "does not exact-match clean HEAD blob",
            ):
                runner._protected_source_receipts(repository, head)

    def test_initializer_byte_drift_stops_before_sealed_bundle_and_search(self) -> None:
        repository = Path(runner.__file__).resolve().parents[3]
        initializer = "src/qmc_bmgs/__init__.py"
        original_git = runner._git
        original_read = runner._read_regular_file_nofollow

        def clean_tracked_git(root: Path, *arguments: str) -> str:
            if arguments == ("status", "--porcelain=v1", "--untracked-files=all"):
                return ""
            if arguments[:1] == ("ls-files",):
                return "\n".join(
                    (*runner._SEARCH_SOURCE_PATHS, *runner._RUNNER_SOURCE_PATHS)
                )
            return original_git(root, *arguments)

        def drift_initializer(path: Path, label: str) -> bytes:
            if Path(path).resolve() == (repository / initializer).resolve():
                return b"synthetic initializer drift\n"
            return original_read(path, label)

        def current_worktree_blob(root: Path, *arguments: str) -> bytes:
            self.assertEqual(arguments[0], "show")
            relative = arguments[1].split(":", 1)[1]
            return original_read(root / relative, "synthetic HEAD blob")

        with tempfile.TemporaryDirectory() as temporary:
            with (
                patch.object(runner, "_git", side_effect=clean_tracked_git),
                patch.object(
                    runner,
                    "_read_regular_file_nofollow",
                    side_effect=drift_initializer,
                ),
                patch.object(
                    runner,
                    "_git_bytes",
                    side_effect=current_worktree_blob,
                ),
                patch.object(
                    runner,
                    "verify_countdown_thompson_diagnostic_bundle",
                    side_effect=AssertionError("sealed bundle must not be opened"),
                ) as verify_bundle,
                patch.object(
                    runner,
                    "_search_microfixture",
                    side_effect=AssertionError("search fixture must not run"),
                ) as search_fixture,
                patch.object(
                    runner,
                    "run_countdown_track_a_search",
                    side_effect=AssertionError("diagnostic search must not run"),
                ) as diagnostic_search,
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticRunnerError,
                    "does not exact-match clean HEAD blob.*__init__",
                ):
                    runner._fresh_preflight(
                        repository / "sealed-bundle",
                        Path(temporary) / "artifact",
                        repository,
                        authorized_runner_revision=None,
                    )
            verify_bundle.assert_not_called()
            search_fixture.assert_not_called()
            diagnostic_search.assert_not_called()

    def test_git_oid_validation_is_distinct_from_data_sha256(self) -> None:
        self.assertEqual(runner._require_git_oid("a" * 40, "revision"), "a" * 40)
        self.assertEqual(runner._require_git_oid("b" * 64, "revision"), "b" * 64)
        with self.assertRaisesRegex(runner.DiagnosticRunnerError, "Git object ID"):
            runner._require_git_oid("c" * 39, "revision")
        with self.assertRaisesRegex(runner.DiagnosticRunnerError, "Git object ID"):
            runner._require_git_oid("D" * 40, "revision")
        with self.assertRaisesRegex(runner.DiagnosticRunnerError, "lowercase SHA-256"):
            runner._require_sha256("e" * 40, "artifact digest")

    def test_required_history_anchors_are_explicit(self) -> None:
        self.assertEqual(
            runner.REQUIRED_ANCESTRY,
            (
                "0917d1d7e8e637610883c6ab5901a118a59ca264",
                "b7eb154d2f3af9112375835c70212b46a59bdab9",
                "2d4960e6f79a12f27ad8dc370b78e89b98958044",
                "9f0f0c9d07d9e7bf66caff5f664792b2160b4ea4",
                "0826aa3480d05453e6900b96aabea5445fa5fce7",
            ),
        )


if __name__ == "__main__":
    unittest.main()
