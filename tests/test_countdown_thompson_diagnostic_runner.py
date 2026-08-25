from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack
from dataclasses import dataclass, replace
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
        bundle=_FakeBundle(payloads, (cell,), seal_digest="e" * 64),
        cells=(cell,),
        qualification=qualification,
        runtime_qualification_digest=sha256_json(qualification),
        build=_build_attestation(),
        output_path=output.resolve(),
        publication_backend=runner._SYNTHETIC_PUBLICATION_BACKEND,
        synthetic_fixture_digest=runner._SYNTHETIC_MICRO_FIXTURE_CONTENT_DIGEST,
    )


def _production_preflight(output: Path) -> runner._Preflight:
    fixture = _preflight(output)
    layout = runner._regular_file_layout(output.resolve())
    parent_binding = runner.regular_file_publication.build_synthetic_parent_binding_v2(
        layout.output_path
    )
    return replace(
        fixture,
        bundle=_FakeBundle(
            fixture.bundle.payloads,  # type: ignore[attr-defined]
            fixture.cells,
            seal_digest=runner.EXPECTED_SEAL_DIGEST,
        ),
        publication_backend=runner._REGULAR_FILE_PUBLICATION_BACKEND,
        synthetic_fixture_digest=None,
        artifact_layout=runner._REGULAR_FILE_ARTIFACT_LAYOUT,
        output_path_digest=layout.output_path_digest,
        output_parent_binding=parent_binding,
        publication_environment_requirements=(
            runner._publication_environment_requirements(parent_binding)
        ),
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

    def test_deep_authorization_json_is_typed_runner_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            authorization = Path(temporary) / "authorization.json"
            depth = 10_000
            authorization.write_bytes(
                b'{"nested":' + (b"[" * depth) + b"0" + (b"]" * depth) + b"}\n"
            )
            with self.assertRaisesRegex(
                runner.DiagnosticRunnerError,
                "authorization JSON nesting exceeds the supported depth",
            ) as raised:
                runner._strict_canonical_object(authorization)
            self.assertIs(type(raised.exception), runner.DiagnosticRunnerError)

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
        self.assertEqual(len(payload["protected"]), 15)

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
            output = Path(temporary).resolve() / "output"
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
            output = root.resolve() / "artifact"
            authorization_path = root / "authorization.json"
            preflight = _production_preflight(output)
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
            self.assertEqual(parsed["schema_version"], runner.AUTHORIZATION_SCHEMA_VERSION)
            self.assertEqual(
                parsed["publication_backend"],
                runner._REGULAR_FILE_PUBLICATION_BACKEND,
            )
            self.assertEqual(
                parsed["artifact_layout"], runner._REGULAR_FILE_ARTIFACT_LAYOUT
            )
            self.assertEqual(
                parsed["output_path_digest"], preflight.output_path_digest
            )
            self.assertEqual(
                parsed["output_parent_binding"], preflight.output_parent_binding
            )
            self.assertEqual(
                parsed["output_parent_binding_digest"],
                preflight.output_parent_binding["deterministic_digest"],  # type: ignore[index]
            )
            with (
                patch.object(
                    runner, "_fresh_preflight", return_value=preflight
                ) as fresh_preflight,
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
            self.assertEqual(
                runner._canonical_bytes(
                    fresh_preflight.call_args.kwargs[
                        "expected_output_parent_binding"
                    ]
                ),
                runner._canonical_bytes(parsed["output_parent_binding"]),
            )

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

    def test_malformed_v2_binding_stops_before_git_parent_or_sealed_preflight(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            output = root / "artifact"
            authorization_path = root / "authorization.json"
            payload = runner._authorization_payload(_production_preflight(output))
            binding = json.loads(json.dumps(payload["output_parent_binding"]))
            binding["component_identities"][-1]["st_dev"] = True
            binding_core = dict(binding)
            binding_core.pop("deterministic_digest")
            binding["deterministic_digest"] = sha256_json(binding_core)
            payload["output_parent_binding"] = binding
            payload["output_parent_binding_digest"] = binding[
                "deterministic_digest"
            ]
            requirements = payload["publication_environment_requirements"]
            self.assertIsInstance(requirements, dict)
            requirements["output_parent_binding_digest"] = binding[
                "deterministic_digest"
            ]
            requirements_core = dict(requirements)
            requirements_core.pop("deterministic_digest")
            requirements["deterministic_digest"] = sha256_json(requirements_core)
            payload_core = dict(payload)
            payload_core.pop("deterministic_digest")
            payload["deterministic_digest"] = sha256_json(payload_core)
            authorization_path.write_bytes(runner._canonical_bytes(payload))

            with (
                patch.object(
                    runner.regular_file_publication,
                    "_open_bound_parent",
                    side_effect=AssertionError("malformed binding must not open parent"),
                ) as parent_open,
                patch.object(
                    runner,
                    "_validate_reviewed_authorization_blob",
                    side_effect=AssertionError("Git gate must not be reached"),
                ) as review_gate,
                patch.object(
                    runner,
                    "_fresh_preflight",
                    side_effect=AssertionError("sealed preflight must not start"),
                ) as fresh_preflight,
                patch.object(
                    runner,
                    "run_countdown_track_a_search",
                    side_effect=AssertionError("diagnostic search must not run"),
                ) as search,
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticRunnerError,
                    "plain identities",
                ):
                    runner._load_and_match_authorization(
                        authorization_path,
                        payload["deterministic_digest"],
                        _AUTHORIZATION_REVISION,
                        bundle_path=root / "sealed-bundle",
                        output_path=output,
                        repository_root=root,
                    )
            parent_open.assert_not_called()
            review_gate.assert_not_called()
            fresh_preflight.assert_not_called()
            search.assert_not_called()

    def test_v2_publication_identity_drift_stops_before_git_and_preflight(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            output = root / "artifact"
            authorization_path = root / "authorization.json"
            baseline = runner._authorization_payload(_production_preflight(output))
            cases = (
                ("unexpected_field", True, "schema is unsupported"),
                ("artifact_id", "other", "publication identity"),
                ("publication_backend", "foreign/v1", "publication identity"),
                ("artifact_layout", "foreign/v1", "publication identity"),
                ("output_path", f"{output}.other", "publication identity"),
                ("output_path_digest", "0" * 64, "path digest"),
                ("output_parent_binding_digest", "0" * 64, "binding digest"),
            )
            with (
                patch.object(
                    runner,
                    "_validate_reviewed_authorization_blob",
                    side_effect=AssertionError("Git gate must not be reached"),
                ) as review_gate,
                patch.object(
                    runner,
                    "_fresh_preflight",
                    side_effect=AssertionError("sealed preflight must not start"),
                ) as fresh_preflight,
            ):
                for field, value, reason in cases:
                    with self.subTest(field=field):
                        payload = json.loads(json.dumps(baseline))
                        payload[field] = value
                        core = dict(payload)
                        core.pop("deterministic_digest")
                        payload["deterministic_digest"] = sha256_json(core)
                        authorization_path.write_bytes(
                            runner._canonical_bytes(payload)
                        )
                        with self.assertRaisesRegex(
                            runner.DiagnosticRunnerError,
                            reason,
                        ):
                            runner._load_and_match_authorization(
                                authorization_path,
                                payload["deterministic_digest"],
                                _AUTHORIZATION_REVISION,
                                bundle_path=root / "sealed-bundle",
                                output_path=output,
                                repository_root=root,
                            )
            review_gate.assert_not_called()
            fresh_preflight.assert_not_called()

    def test_reviewed_loader_uses_authorized_binding_without_recapture(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            repository = root / "repository"
            repository.mkdir()
            output_parent = root / "output-parent"
            output_parent.mkdir()
            output = output_parent / "artifact.commit.json"
            authorization_path = repository / "authorization.json"
            planned = _production_preflight(output)
            payload = runner._authorization_payload(planned)
            authorization_path.write_bytes(runner._canonical_bytes(payload))
            fresh_payloads = json.loads(json.dumps(planned.bundle.payloads))  # type: ignore[attr-defined]
            fresh_payloads["diagnostic_tasks.json"] = {"tasks": []}
            fresh_bundle = _FakeBundle(
                fresh_payloads,
                planned.cells,
                seal_digest=runner.EXPECTED_SEAL_DIGEST,
            )

            with (
                patch.object(
                    runner.regular_file_publication,
                    "build_synthetic_parent_binding_v2",
                    side_effect=AssertionError("reviewed loader must not recapture"),
                ) as recapture,
                patch.object(
                    runner,
                    "_validate_reviewed_authorization_blob",
                    return_value=_AUTHORIZATION_REVISION,
                ),
                patch.object(
                    runner,
                    "_qualify_diagnostic_runtime",
                    return_value=planned.qualification,
                ),
                patch.object(
                    runner,
                    "_frozen_diagnostic_runtime_bindings",
                    return_value={"fixture": True},
                ),
                patch.object(
                    runner,
                    "_attest_clean_source_build",
                    return_value=planned.build,
                ),
                patch.object(
                    runner,
                    "verify_countdown_thompson_diagnostic_bundle",
                    return_value=fresh_bundle,
                ),
                patch.object(
                    runner,
                    "_validate_schedule",
                    return_value=planned.cells,
                ),
                patch.object(runner, "_validate_outcome_blind_budget_guards"),
                patch.object(runner, "_recheck_source_closure"),
                patch.object(
                    runner,
                    "run_countdown_track_a_search",
                    side_effect=AssertionError("diagnostic search must not run"),
                ) as search,
            ):
                fresh, observed = runner._load_and_match_authorization(
                    authorization_path,
                    payload["deterministic_digest"],
                    _AUTHORIZATION_REVISION,
                    bundle_path=root / "sealed-bundle",
                    output_path=output,
                    repository_root=repository,
                )
            recapture.assert_not_called()
            search.assert_not_called()
            self.assertEqual(observed, payload)
            self.assertEqual(
                runner._canonical_bytes(fresh.output_parent_binding),
                runner._canonical_bytes(payload["output_parent_binding"]),
            )

    def test_reviewed_loader_treats_replaced_parent_as_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            repository = root / "repository"
            repository.mkdir()
            output_parent = root / "output-parent"
            output_parent.mkdir()
            output = output_parent / "artifact.commit.json"
            authorization_path = repository / "authorization.json"
            payload = runner._authorization_payload(_production_preflight(output))
            authorization_path.write_bytes(runner._canonical_bytes(payload))
            displaced_parent = root / "displaced-output-parent"
            output_parent.rename(displaced_parent)
            output_parent.mkdir()

            with (
                patch.object(
                    runner.regular_file_publication,
                    "build_synthetic_parent_binding_v2",
                    side_effect=AssertionError("reviewed loader must not recapture"),
                ) as recapture,
                patch.object(
                    runner,
                    "_validate_reviewed_authorization_blob",
                    return_value=_AUTHORIZATION_REVISION,
                ) as review_gate,
                patch.object(
                    runner,
                    "_qualify_diagnostic_runtime",
                    side_effect=AssertionError("sealed preflight must not start"),
                ) as qualify,
                patch.object(
                    runner,
                    "run_countdown_track_a_search",
                    side_effect=AssertionError("diagnostic search must not run"),
                ) as search,
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticPublicationStateAmbiguousError,
                    "reviewed binding",
                ):
                    runner._load_and_match_authorization(
                        authorization_path,
                        payload["deterministic_digest"],
                        _AUTHORIZATION_REVISION,
                        bundle_path=root / "sealed-bundle",
                        output_path=output,
                        repository_root=repository,
                    )
            recapture.assert_not_called()
            review_gate.assert_called_once()
            qualify.assert_not_called()
            search.assert_not_called()

    def test_missing_authorization_parent_is_not_created_or_published(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root.resolve() / "artifact"
            missing_ancestor = root / "missing"
            authorization_path = missing_ancestor / "reviews" / "authorization.json"
            preflight = _production_preflight(output)
            with (
                patch.object(runner, "_fresh_preflight", return_value=preflight),
                patch.object(
                    runner,
                    "_write_canonical_file_noreplace_at",
                    side_effect=AssertionError(
                        "authorization candidate must not be staged"
                    ),
                ) as publish_candidate,
                patch.object(
                    runner,
                    "run_countdown_track_a_search",
                    side_effect=AssertionError("diagnostic search must not run"),
                ) as search,
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticRunnerError,
                    "authorization parent must be a stable directory",
                ):
                    runner.write_countdown_thompson_diagnostic_execution_plan(
                        root / "bundle",
                        output,
                        authorization_path,
                        repository_root=root,
                    )
            self.assertFalse(missing_ancestor.exists())
            self.assertFalse(authorization_path.exists())
            self.assertEqual(list(root.iterdir()), [])
            publish_candidate.assert_not_called()
            search.assert_not_called()

    def test_authorization_parent_sync_failure_returns_exact_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root.resolve() / "artifact"
            authorization_path = root / "authorization.json"
            preflight = _production_preflight(output)
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

    def test_persistent_authorization_sync_failure_durably_revokes_candidate(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root.resolve() / "artifact"
            authorization_path = root / "authorization.json"
            preflight = _production_preflight(output)
            original_fsync = runner.os.fsync
            call_count = 0

            def fail_initial_and_retry_sync(descriptor: int) -> None:
                nonlocal call_count
                call_count += 1
                if call_count in {2, 3}:
                    raise OSError("persistent authorization parent sync failure")
                original_fsync(descriptor)

            with (
                patch.object(runner, "_fresh_preflight", return_value=preflight),
                patch.object(
                    runner.os,
                    "fsync",
                    side_effect=fail_initial_and_retry_sync,
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticNotRunError,
                    "durably revoked",
                ):
                    runner.write_countdown_thompson_diagnostic_execution_plan(
                        root / "bundle",
                        output,
                        authorization_path,
                        repository_root=root,
                    )
            self.assertFalse(authorization_path.exists())

    def test_authorization_rollback_sync_failure_is_publication_ambiguous(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root.resolve() / "artifact"
            authorization_path = root / "authorization.json"
            preflight = _production_preflight(output)
            original_fsync = runner.os.fsync
            call_count = 0

            def fail_publication_and_rollback_sync(descriptor: int) -> None:
                nonlocal call_count
                call_count += 1
                if call_count >= 2:
                    raise OSError("authorization rollback sync failure")
                original_fsync(descriptor)

            with (
                patch.object(runner, "_fresh_preflight", return_value=preflight),
                patch.object(
                    runner.os,
                    "fsync",
                    side_effect=fail_publication_and_rollback_sync,
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticPublicationStateAmbiguousError,
                    "durability and exact rollback",
                ):
                    runner.write_countdown_thompson_diagnostic_execution_plan(
                        root / "bundle",
                        output,
                        authorization_path,
                        repository_root=root,
                    )
            self.assertFalse(authorization_path.exists())

    def test_authorization_parent_drift_revokes_candidate_before_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root.resolve() / "artifact"
            authorization_path = root / "authorization.json"
            preflight = _production_preflight(output)
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
                    runner.DiagnosticNotRunError,
                    "durably revoked",
                ):
                    runner.write_countdown_thompson_diagnostic_execution_plan(
                        root / "bundle",
                        output,
                        authorization_path,
                        repository_root=root,
                    )
            self.assertFalse(authorization_path.exists())

    def test_final_authorization_drift_needs_a_fresh_durability_proof(self) -> None:
        for barrier_fails in (False, True):
            with (
                self.subTest(barrier_fails=barrier_fails),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                output = root.resolve() / "artifact"
                authorization_path = root / "authorization.json"
                stolen = root / "stolen-authorization.json"
                foreign = root / "foreign-authorization.json"
                foreign.write_bytes(b"foreign\n")
                preflight = _production_preflight(output)
                original_assert = runner._assert_directory_path_identity
                original_fsync = runner.os.fsync
                root_identity = (root.stat().st_dev, root.stat().st_ino)
                assertion_count = 0
                swapped = False

                def swap_after_durable_publication(*args: object) -> None:
                    nonlocal assertion_count, swapped
                    assertion_count += 1
                    if assertion_count == 3:
                        authorization_path.rename(stolen)
                        foreign.rename(authorization_path)
                        swapped = True
                    original_assert(*args)

                def maybe_fail_final_barrier(descriptor: int) -> None:
                    observed = runner.os.fstat(descriptor)
                    if (
                        barrier_fails
                        and swapped
                        and (observed.st_dev, observed.st_ino) == root_identity
                    ):
                        raise OSError("final authorization barrier unavailable")
                    original_fsync(descriptor)

                expected_error = (
                    runner.DiagnosticPublicationStateAmbiguousError
                    if barrier_fails
                    else runner.DiagnosticNotRunError
                )
                with (
                    patch.object(runner, "_fresh_preflight", return_value=preflight),
                    patch.object(
                        runner,
                        "_assert_directory_path_identity",
                        side_effect=swap_after_durable_publication,
                    ),
                    patch.object(
                        runner.os,
                        "fsync",
                        side_effect=maybe_fail_final_barrier,
                    ),
                ):
                    with self.assertRaises(expected_error):
                        runner.write_countdown_thompson_diagnostic_execution_plan(
                            root / "bundle",
                            output,
                            authorization_path,
                            repository_root=root,
                        )
                self.assertTrue(swapped)
                self.assertEqual(authorization_path.read_bytes(), b"foreign\n")
                self.assertTrue(stolen.is_file())

    def test_authorization_missing_initializer_receipt_stops_before_preflight(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root.resolve() / "artifact"
            authorization_path = root / "authorization.json"
            payload = runner._authorization_payload(_production_preflight(output))
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
            output = root.resolve() / "artifact"
            authorization_path = root / "authorization.json"
            preflight = _production_preflight(output)
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

    def test_public_run_fails_closed_before_inputs_without_atomic_backend(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            authorization = root / "authorization.json"
            authorization.write_bytes(runner._canonical_bytes({"invalid": True}))
            with (
                patch.object(
                    runner,
                    "_load_and_match_authorization",
                    side_effect=AssertionError("inputs must not be opened"),
                ),
                patch.object(
                    runner,
                    "_publish_run_artifact",
                    side_effect=AssertionError("execution must not start"),
                ),
                patch.object(
                    runner,
                    "run_countdown_track_a_search",
                    side_effect=AssertionError("diagnostic search must not run"),
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticNotRunError,
                    "portable atomic directory creation authority is unavailable",
                ):
                    runner.run_countdown_thompson_diagnostic(
                        root / "bundle",
                        root / "output",
                        authorization,
                        "0" * 64,
                        _AUTHORIZATION_REVISION,
                        repository_root=root,
                    )

    def test_real_backend_preflight_cannot_enter_fixture_publisher(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            preflight = replace(
                _preflight(root / "artifact"),
                publication_backend=runner._PUBLICATION_BACKEND_UNAVAILABLE,
            )
            authorization = runner._authorization_payload(preflight)
            with (
                patch.object(
                    runner,
                    "_open_stable_directory",
                    side_effect=AssertionError("output parent must not be opened"),
                ),
                patch.object(
                    runner,
                    "_publish_run_artifact_locked",
                    side_effect=AssertionError("publisher body must not run"),
                ),
                patch.object(
                    runner,
                    "run_countdown_track_a_search",
                    side_effect=AssertionError("diagnostic search must not run"),
                ),
                self.assertRaisesRegex(
                    runner.DiagnosticNotRunError,
                    "portable atomic directory creation authority is unavailable",
                ),
            ):
                runner._publish_run_artifact(
                    preflight,
                    authorization,
                    reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                    repository_root=root,
                )

    def test_retagged_diagnostic_shape_cannot_enter_fixture_publisher(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = _preflight(root / "artifact")
            authorization = runner._authorization_payload(fixture)
            preflight = replace(
                fixture,
                bundle=_FakeBundle(
                    fixture.bundle.payloads,  # type: ignore[attr-defined]
                    fixture.cells,
                    seal_digest=runner.EXPECTED_SEAL_DIGEST,
                ),
                publication_backend=runner._SYNTHETIC_PUBLICATION_BACKEND,
            )
            with (
                patch.object(
                    runner,
                    "_open_stable_directory",
                    side_effect=AssertionError("output parent must not be opened"),
                ),
                patch.object(
                    runner,
                    "_publish_run_artifact_locked",
                    side_effect=AssertionError("publisher body must not run"),
                ),
                patch.object(
                    runner,
                    "run_countdown_track_a_search",
                    side_effect=AssertionError("diagnostic search must not run"),
                ),
                self.assertRaisesRegex(
                    runner.DiagnosticNotRunError,
                    "portable atomic directory creation authority is unavailable",
                ),
            ):
                runner._publish_run_artifact(
                    preflight,
                    authorization,
                    reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                    repository_root=root,
                )

    def test_unknown_synthetic_content_cannot_enter_fixture_publisher(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = _preflight(root / "artifact")
            unexpected_cell = replace(fixture.cells[0], exploration_seed=1)
            unexpected_payloads = json.loads(
                json.dumps(fixture.bundle.payloads)  # type: ignore[attr-defined]
            )
            unexpected_payloads["preregistration.json"]["execution_matrix"][
                "schedule_digest"
            ] = sha256_json([unexpected_cell.to_dict()])
            unexpected_bundle = _FakeBundle(
                unexpected_payloads,
                (unexpected_cell,),
                seal_digest="e" * 64,
            )
            unexpected_digest = sha256_json(
                {
                    "cells": [unexpected_cell.to_dict()],
                    "payloads": unexpected_bundle.payloads,
                    "qualification": fixture.qualification,
                    "runtime_qualification_digest": (
                        fixture.runtime_qualification_digest
                    ),
                    "seal_digest": unexpected_bundle.seal_digest,
                }
            )
            preflight = replace(
                fixture,
                bundle=unexpected_bundle,
                cells=(unexpected_cell,),
                synthetic_fixture_digest=unexpected_digest,
            )
            authorization = runner._authorization_payload_from_preflight(
                preflight,
                synthetic_fixture=True,
            )
            self.assertNotIn(
                unexpected_digest,
                runner._SYNTHETIC_FIXTURE_CONTENT_DIGESTS,
            )
            self.assertEqual(
                authorization["synthetic_fixture_digest"],
                unexpected_digest,
            )
            with (
                patch.object(runner, "EXPECTED_CELL_COUNT", 1),
                patch.object(runner, "EXPECTED_SEAL_DIGEST", "f" * 64),
                patch.object(
                    runner,
                    "_open_stable_directory",
                    side_effect=AssertionError("output parent must not be opened"),
                ) as open_directory,
                patch.object(
                    runner,
                    "run_countdown_track_a_search",
                    side_effect=AssertionError("diagnostic search must not run"),
                ) as search,
                self.assertRaisesRegex(
                    runner.DiagnosticNotRunError,
                    "portable atomic directory creation authority is unavailable",
                ) as raised,
            ):
                runner._publish_run_artifact(
                    preflight,
                    authorization,
                    reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                    repository_root=root,
                )
            self.assertIs(
                type(raised.exception.__cause__), runner.DiagnosticRunnerError
            )
            self.assertIn(
                "not a positively identified synthetic fixture",
                str(raised.exception.__cause__),
            )
            open_directory.assert_not_called()
            search.assert_not_called()

    def test_adversarial_cell_iterable_cannot_enter_fixture_publisher(self) -> None:
        class _Cells:
            def __init__(self, cells: tuple[DiagnosticCell, ...]) -> None:
                self.cells = cells
                self.iterations = 0

            def __len__(self) -> int:
                return 1

            def __iter__(self):  # type: ignore[no-untyped-def]
                self.iterations += 1
                return iter(self.cells)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = _preflight(root / "artifact")
            authorization = runner._authorization_payload(fixture)
            cells = _Cells(fixture.cells)
            preflight = replace(fixture, cells=cells)  # type: ignore[arg-type]
            with (
                patch.object(
                    runner,
                    "_open_stable_directory",
                    side_effect=AssertionError("output parent must not be opened"),
                ),
                patch.object(
                    runner,
                    "run_countdown_track_a_search",
                    side_effect=AssertionError("diagnostic search must not run"),
                ),
                self.assertRaisesRegex(
                    runner.DiagnosticNotRunError,
                    "portable atomic directory creation authority is unavailable",
                ),
            ):
                runner._publish_run_artifact(
                    preflight,
                    authorization,
                    reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                    repository_root=root,
                )
            self.assertEqual(cells.iterations, 0)

    def test_stateful_authorization_mapping_is_refused_before_output(self) -> None:
        class _Authorization(dict[str, object]):
            pass

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            preflight = _preflight(root / "artifact")
            authorization = _Authorization(runner._authorization_payload(preflight))
            with (
                patch.object(
                    runner,
                    "_open_stable_directory",
                    side_effect=AssertionError("output parent must not be opened"),
                ),
                patch.object(
                    runner,
                    "run_countdown_track_a_search",
                    side_effect=AssertionError("diagnostic search must not run"),
                ),
                self.assertRaisesRegex(
                    runner.DiagnosticNotRunError,
                    "portable atomic directory creation authority is unavailable",
                ),
            ):
                runner._publish_run_artifact(
                    preflight,
                    authorization,
                    reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                    repository_root=root,
                )

    def test_split_output_path_is_refused_before_output_or_execution(self) -> None:
        class _SplitPath:
            def __init__(self, claimed: Path, actual_parent: Path) -> None:
                self.claimed = claimed
                self.actual_parent = actual_parent

            @property
            def name(self) -> str:
                return self.claimed.name

            @property
            def parent(self) -> Path:
                return self.actual_parent

            def __str__(self) -> str:
                return str(self.claimed)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = _preflight(root / "claimed" / "artifact")
            authorization = runner._authorization_payload(fixture)
            split = _SplitPath(fixture.output_path, root / "actual")
            preflight = replace(fixture, output_path=split)  # type: ignore[arg-type]
            with (
                patch.object(
                    runner,
                    "_open_stable_directory",
                    side_effect=AssertionError("output parent must not be opened"),
                ),
                patch.object(
                    runner,
                    "_execute_cell",
                    side_effect=AssertionError("synthetic cell must not execute"),
                ),
                self.assertRaisesRegex(
                    runner.DiagnosticNotRunError,
                    "portable atomic directory creation authority is unavailable",
                ),
            ):
                runner._publish_run_artifact(
                    preflight,
                    authorization,
                    reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                    repository_root=root,
                    _terminal_result=True,
                )
            self.assertFalse((root / "claimed" / "artifact").exists())
            self.assertFalse((root / "actual" / "artifact").exists())

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

    def test_plan_rejects_noncanonical_output_spelling_before_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            repository = root / "repository"
            repository.mkdir()
            candidates = (
                "relative/artifact.commit.json",
                f"{root}/nested/../artifact.commit.json",
                f"{root}/成果.commit.json",
            )
            with patch.object(
                runner,
                "_fresh_preflight",
                side_effect=AssertionError("invalid lexical path must fail first"),
            ) as fresh_preflight:
                for index, output in enumerate(candidates):
                    with self.subTest(output=output):
                        authorization = repository / f"authorization-{index}.json"
                        with self.assertRaises(runner.DiagnosticRunnerError):
                            runner.write_countdown_thompson_diagnostic_execution_plan(
                                root / "sealed-bundle",
                                output,
                                authorization,
                                repository_root=repository,
                            )
                        self.assertFalse(authorization.exists())
            fresh_preflight.assert_not_called()

    def test_plan_candidate_must_be_written_inside_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
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

    def test_preflight_does_not_resolve_through_output_parent_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            repository = root / "repository"
            repository.mkdir()
            actual_parent = root / "actual-parent"
            actual_parent.mkdir()
            alias_parent = root / "alias-parent"
            alias_parent.symlink_to(actual_parent, target_is_directory=True)
            with (
                patch.object(
                    runner,
                    "_qualify_diagnostic_runtime",
                    side_effect=AssertionError("sealed preflight must not start"),
                ) as qualify,
                patch.object(
                    runner,
                    "run_countdown_track_a_search",
                    side_effect=AssertionError("diagnostic search must not run"),
                ) as search,
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticRunnerError,
                    "stable no-follow directory path",
                ):
                    runner._fresh_preflight(
                        root / "sealed-bundle",
                        alias_parent / "artifact.commit.json",
                        repository,
                        authorized_runner_revision=None,
                    )
            qualify.assert_not_called()
            search.assert_not_called()

    def test_fresh_preflight_rechecks_source_after_microfixture_and_bundle(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
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

    def test_publication_observation_io_errors_never_collapse_to_false(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate = root / "candidate.json"
            candidate.write_bytes(b"candidate\n")
            artifact = root / "artifact"
            artifact.mkdir()
            attempt_path = root / "attempt"
            attempt_path.mkdir()
            receipt = {"status": "PENDING"}
            (attempt_path / "pre_outcome.json").write_bytes(
                runner._canonical_bytes(receipt)
            )
            parent_fd = runner.os.open(root, runner.os.O_RDONLY)
            attempt_fd = runner.os.open(attempt_path, runner.os.O_RDONLY)
            try:
                candidate_stat = candidate.stat()
                candidate_identity = (
                    candidate_stat.st_dev,
                    candidate_stat.st_ino,
                )
                artifact_stat = artifact.stat()
                artifact_identity = (artifact_stat.st_dev, artifact_stat.st_ino)
                attempt_stat = attempt_path.stat()
                attempt_identity = (attempt_stat.st_dev, attempt_stat.st_ino)
                attempt = runner._Attempt(
                    directory=attempt_path,
                    directory_fd=attempt_fd,
                    directory_identity=attempt_identity,
                    directory_name="attempt",
                    staging_path=attempt_path / "staging",
                    receipt_base={},
                )

                with patch.object(
                    runner.os,
                    "open",
                    side_effect=OSError("candidate observation unavailable"),
                ):
                    with self.assertRaisesRegex(
                        runner.DiagnosticPublicationStateAmbiguousError,
                        "published file observation failed",
                    ):
                        runner._published_file_matches(
                            parent_fd,
                            candidate.name,
                            candidate_identity,
                            candidate.read_bytes(),
                        )

                with patch.object(
                    runner.os,
                    "scandir",
                    side_effect=OSError("artifact observation unavailable"),
                ):
                    with self.assertRaisesRegex(
                        runner.DiagnosticPublicationStateAmbiguousError,
                        "published artifact observation failed",
                    ):
                        runner._published_artifact_matches(
                            parent_fd,
                            artifact.name,
                            artifact_identity,
                            {},
                            records_byte_count=0,
                            records_sha256=runner._sha256_bytes(b""),
                            commit_receipt=None,
                        )

                with patch.object(
                    runner.os,
                    "stat",
                    side_effect=OSError("attempt entry observation unavailable"),
                ):
                    with self.assertRaisesRegex(
                        runner.DiagnosticPublicationStateAmbiguousError,
                        "attempt reservation source observation failed",
                    ):
                        runner._published_attempt_entry_is_pinned(
                            parent_fd,
                            attempt_path.name,
                            "missing-temporary-attempt",
                            attempt_fd,
                            attempt_identity,
                        )

                with patch.object(
                    runner.os,
                    "scandir",
                    side_effect=OSError("attempt content observation unavailable"),
                ):
                    with self.assertRaisesRegex(
                        runner.DiagnosticPublicationStateAmbiguousError,
                        "attempt reservation content observation failed",
                    ):
                        runner._published_attempt_reservation_matches(
                            parent_fd,
                            attempt_path.name,
                            "missing-temporary-attempt",
                            attempt_fd,
                            attempt_identity,
                            receipt,
                        )

                with patch.object(
                    runner,
                    "_read_regular_file_at",
                    side_effect=OSError("attempt receipt observation unavailable"),
                ):
                    with self.assertRaisesRegex(
                        runner.DiagnosticPublicationStateAmbiguousError,
                        "attempt receipt observation failed",
                    ):
                        runner._attempt_receipt_matches(
                            attempt,
                            "started.json",
                            receipt,
                        )
            finally:
                runner.os.close(attempt_fd)
                runner.os.close(parent_fd)

    def test_terminal_receipt_generation_spans_final_name_proof(self) -> None:
        terminal_cases = {
            "COMMITTED": {
                "receipts": {
                    "pre_outcome.json": {"phase": "PRE_OUTCOME", "status": "PENDING"},
                    "ready_to_commit.json": {
                        "phase": "STARTED",
                        "status": "PENDING",
                    },
                    "started.json": {"phase": "STARTED", "status": "PENDING"},
                },
                "target": "ready_to_commit.json",
                "success": True,
            },
            "NOT_RUN": {
                "receipts": {
                    "not_run.json": {"phase": "PRE_OUTCOME", "status": "NOT_RUN"}
                },
                "target": "not_run.json",
                "success": False,
            },
            "INVALID": {
                "receipts": {"invalid.json": {"phase": "STARTED", "status": "INVALID"}},
                "target": "invalid.json",
                "success": False,
            },
        }
        for terminal_status, case in terminal_cases.items():
            with (
                self.subTest(terminal_status=terminal_status),
                tempfile.TemporaryDirectory() as temporary,
            ):
                parent = Path(temporary).resolve()
                attempt_path = parent / "attempt"
                attempt_path.mkdir()
                receipts = case["receipts"]
                assert isinstance(receipts, dict)
                for filename, payload in receipts.items():
                    (attempt_path / filename).write_bytes(
                        runner._canonical_bytes(payload)
                    )
                parent_fd = runner.os.open(parent, runner.os.O_RDONLY)
                attempt_fd = runner.os.open(attempt_path, runner.os.O_RDONLY)
                attempt_stat = attempt_path.stat()
                attempt = runner._Attempt(
                    directory=attempt_path,
                    directory_fd=attempt_fd,
                    directory_identity=(attempt_stat.st_dev, attempt_stat.st_ino),
                    directory_name=attempt_path.name,
                    staging_path=attempt_path / "staging",
                    receipt_base={},
                )
                target = attempt_path / str(case["target"])
                target_before = target.stat()
                original_capture = runner._capture_attempt_member_generation
                capture_calls = 0

                def mutate_before_final_generation(
                    observed_attempt: runner._Attempt,
                    observed_parent_fd: int,
                    filenames: tuple[str, ...],
                ) -> runner._DirectoryMemberGeneration:
                    nonlocal capture_calls
                    capture_calls += 1
                    if capture_calls == 2:
                        original = target.read_bytes()
                        replacement = bytes([original[0] ^ 1]) + original[1:]
                        descriptor = runner.os.open(target, runner.os.O_WRONLY)
                        try:
                            runner.os.pwrite(descriptor, replacement, 0)
                            runner.os.fsync(descriptor)
                        finally:
                            runner.os.close(descriptor)
                    return original_capture(
                        observed_attempt,
                        observed_parent_fd,
                        filenames,
                    )

                try:
                    proof_kwargs: dict[str, object] = {}
                    if case["success"]:
                        proof_kwargs["success_receipts"] = receipts
                    else:
                        proof_kwargs["required_receipts"] = receipts
                    with (
                        patch.object(
                            runner,
                            "_capture_attempt_member_generation",
                            side_effect=mutate_before_final_generation,
                        ),
                        self.assertRaisesRegex(
                            runner.DiagnosticPublicationStateAmbiguousError,
                            "terminal attempt receipt generation changed",
                        ),
                    ):
                        runner._prove_attempt_terminal_authority(
                            parent=parent,
                            parent_fd=parent_fd,
                            parent_stat=parent.stat(),
                            attempt=attempt,
                            **proof_kwargs,
                        )
                    target_after = target.stat()
                    self.assertEqual(target_after.st_ino, target_before.st_ino)
                    self.assertEqual(target_after.st_size, target_before.st_size)
                finally:
                    runner._close_descriptor_best_effort(attempt_fd)
                    runner._close_descriptor_best_effort(parent_fd)

    def test_committed_collective_rejects_alternating_exact_authorities(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary).resolve()
            attempt_path = parent / "attempt"
            artifact = parent / "artifact"
            attempt_path.mkdir()
            artifact.mkdir()
            success_receipts = {
                "pre_outcome.json": {"phase": "PRE_OUTCOME", "status": "PENDING"},
                "ready_to_commit.json": {
                    "phase": "STARTED",
                    "status": "PENDING",
                },
                "started.json": {"phase": "STARTED", "status": "PENDING"},
            }
            for filename, payload in success_receipts.items():
                (attempt_path / filename).write_bytes(runner._canonical_bytes(payload))
            run_manifest = {"fixture": "collective-commit"}
            records_bytes = b'{"fixture":"collective-commit"}\n'
            commit_receipt = {"status": "COMMITTED"}
            manifest = artifact / "manifest.json"
            records = artifact / "records.jsonl"
            commit = artifact / "commit.json"
            manifest_exact = runner._canonical_bytes(run_manifest)
            manifest_corrupt = bytes([manifest_exact[0] ^ 1]) + manifest_exact[1:]
            manifest.write_bytes(manifest_exact)
            records.write_bytes(records_bytes)
            commit.write_bytes(runner._canonical_bytes(commit_receipt))
            started = attempt_path / "started.json"
            started_exact = started.read_bytes()
            started_corrupt = bytes([started_exact[0] ^ 1]) + started_exact[1:]
            started.write_bytes(started_corrupt)

            def overwrite_same_extent(path: Path, payload: bytes) -> None:
                self.assertEqual(path.stat().st_size, len(payload))
                descriptor = runner.os.open(path, runner.os.O_WRONLY)
                try:
                    runner.os.pwrite(descriptor, payload, 0)
                    runner.os.fsync(descriptor)
                finally:
                    runner.os.close(descriptor)

            parent_fd = runner.os.open(parent, runner.os.O_RDONLY)
            attempt_fd = runner.os.open(attempt_path, runner.os.O_RDONLY)
            output_fd = runner.os.open(artifact, runner.os.O_RDONLY)
            parent_stat = parent.stat()
            attempt_stat = attempt_path.stat()
            artifact_stat = artifact.stat()
            attempt = runner._Attempt(
                directory=attempt_path,
                directory_fd=attempt_fd,
                directory_identity=(attempt_stat.st_dev, attempt_stat.st_ino),
                directory_name=attempt_path.name,
                staging_path=attempt_path / "staging",
                receipt_base={},
            )
            original_artifact_proof = runner._published_artifact_matches
            original_attempt_proof = runner._prove_attempt_terminal_authority
            artifact_proofs = 0
            attempt_proofs = 0

            def rotate_after_artifact_proof(
                *args: object,
                **kwargs: object,
            ) -> bool:
                nonlocal artifact_proofs
                matches = original_artifact_proof(*args, **kwargs)
                artifact_proofs += 1
                if artifact_proofs == 1:
                    self.assertTrue(matches)
                    overwrite_same_extent(manifest, manifest_corrupt)
                    overwrite_same_extent(started, started_exact)
                return matches

            def rotate_after_attempt_proof(
                **kwargs: object,
            ) -> bool:
                nonlocal attempt_proofs
                matches = original_attempt_proof(**kwargs)
                attempt_proofs += 1
                if attempt_proofs == 1:
                    self.assertTrue(matches)
                    overwrite_same_extent(started, started_corrupt)
                    overwrite_same_extent(manifest, manifest_exact)
                return matches

            try:
                with (
                    patch.object(
                        runner,
                        "_published_artifact_matches",
                        side_effect=rotate_after_artifact_proof,
                    ),
                    patch.object(
                        runner,
                        "_prove_attempt_terminal_authority",
                        side_effect=rotate_after_attempt_proof,
                    ),
                    self.assertRaisesRegex(
                        runner.DiagnosticPublicationStateAmbiguousError,
                        "committed artifact and attempt changed",
                    ),
                ):
                    runner._prove_committed_terminal_collective(
                        parent=parent,
                        parent_fd=parent_fd,
                        parent_stat=parent_stat,
                        attempt=attempt,
                        success_receipts=success_receipts,
                        output_name=artifact.name,
                        output_fd=output_fd,
                        staging_identity=(artifact_stat.st_dev, artifact_stat.st_ino),
                        run_manifest=run_manifest,
                        records_byte_count=len(records_bytes),
                        records_sha256=runner._sha256_bytes(records_bytes),
                        commit_receipt=commit_receipt,
                    )
                self.assertEqual(artifact_proofs, 2)
                self.assertEqual(attempt_proofs, 1)
                self.assertEqual(manifest.read_bytes(), manifest_exact)
                self.assertEqual(started.read_bytes(), started_corrupt)
            finally:
                runner._close_descriptor_best_effort(output_fd)
                runner._close_descriptor_best_effort(attempt_fd)
                runner._close_descriptor_best_effort(parent_fd)

    def test_invalid_collective_rejects_alternating_receipt_and_absence(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary).resolve()
            attempt_path = parent / "attempt"
            artifact = parent / "artifact"
            attempt_path.mkdir()
            artifact.mkdir()
            invalid_receipt = {"phase": "STARTED", "status": "INVALID"}
            invalid = attempt_path / "invalid.json"
            invalid_exact = runner._canonical_bytes(invalid_receipt)
            invalid_corrupt = bytes([invalid_exact[0] ^ 1]) + invalid_exact[1:]
            invalid.write_bytes(invalid_exact)
            run_manifest = {"fixture": "collective-invalid"}
            records_bytes = b'{"fixture":"collective-invalid"}\n'
            commit_receipt = {"status": "COMMITTED"}
            (artifact / "manifest.json").write_bytes(
                runner._canonical_bytes(run_manifest)
            )
            (artifact / "records.jsonl").write_bytes(records_bytes)
            commit = artifact / "commit.json"
            commit_bytes = runner._canonical_bytes(commit_receipt)
            commit.write_bytes(commit_bytes)

            def overwrite_same_extent(path: Path, payload: bytes) -> None:
                self.assertEqual(path.stat().st_size, len(payload))
                descriptor = runner.os.open(path, runner.os.O_WRONLY)
                try:
                    runner.os.pwrite(descriptor, payload, 0)
                    runner.os.fsync(descriptor)
                finally:
                    runner.os.close(descriptor)

            def create_durable(path: Path, payload: bytes, directory_fd: int) -> None:
                path.write_bytes(payload)
                descriptor = runner.os.open(path, runner.os.O_RDONLY)
                try:
                    runner.os.fsync(descriptor)
                finally:
                    runner.os.close(descriptor)
                runner.os.fsync(directory_fd)

            parent_fd = runner.os.open(parent, runner.os.O_RDONLY)
            attempt_fd = runner.os.open(attempt_path, runner.os.O_RDONLY)
            output_fd = runner.os.open(artifact, runner.os.O_RDONLY)
            parent_stat = parent.stat()
            attempt_stat = attempt_path.stat()
            attempt = runner._Attempt(
                directory=attempt_path,
                directory_fd=attempt_fd,
                directory_identity=(attempt_stat.st_dev, attempt_stat.st_ino),
                directory_name=attempt_path.name,
                staging_path=attempt_path / "staging",
                receipt_base={},
            )
            original_attempt_proof = runner._prove_attempt_terminal_authority
            original_content_identity = runner._published_artifact_content_identity
            attempt_proofs = 0
            absence_proofs = 0

            def rotate_after_invalid_proof(**kwargs: object) -> bool:
                nonlocal attempt_proofs
                result = original_attempt_proof(**kwargs)
                attempt_proofs += 1
                if attempt_proofs == 1:
                    overwrite_same_extent(invalid, invalid_corrupt)
                    commit.unlink()
                    runner.os.fsync(output_fd)
                return result

            def rotate_after_absence_proof(
                *args: object,
                **kwargs: object,
            ) -> tuple[int, int] | None:
                nonlocal absence_proofs
                identity = original_content_identity(*args, **kwargs)
                absence_proofs += 1
                if absence_proofs == 1:
                    self.assertIsNone(identity)
                    create_durable(commit, commit_bytes, output_fd)
                    overwrite_same_extent(invalid, invalid_exact)
                return identity

            try:
                with (
                    patch.object(
                        runner,
                        "_prove_attempt_terminal_authority",
                        side_effect=rotate_after_invalid_proof,
                    ),
                    patch.object(
                        runner,
                        "_published_artifact_content_identity",
                        side_effect=rotate_after_absence_proof,
                    ),
                    self.assertRaisesRegex(
                        runner.DiagnosticPublicationStateAmbiguousError,
                        "INVALID receipt and artifact absence changed",
                    ),
                ):
                    runner._prove_invalid_terminal_collective(
                        parent=parent,
                        parent_fd=parent_fd,
                        parent_stat=parent_stat,
                        attempt=attempt,
                        invalid_receipt=invalid_receipt,
                        output_name=artifact.name,
                        output_fd=output_fd,
                        run_manifest=run_manifest,
                        records_byte_count=len(records_bytes),
                        records_sha256=runner._sha256_bytes(records_bytes),
                        commit_receipt=commit_receipt,
                    )
                self.assertEqual(attempt_proofs, 2)
                self.assertEqual(absence_proofs, 1)
                self.assertEqual(invalid.read_bytes(), invalid_exact)
                self.assertEqual(commit.read_bytes(), commit_bytes)
            finally:
                runner._close_descriptor_best_effort(output_fd)
                runner._close_descriptor_best_effort(attempt_fd)
                runner._close_descriptor_best_effort(parent_fd)

    @unittest.skipUnless(hasattr(runner.os, "mkfifo"), "POSIX FIFO required")
    def test_bounded_readers_reject_fifo_and_stat_open_fifo_race(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fifo = root / "blocked-reader"
            runner.os.mkfifo(fifo)
            with (
                patch.object(
                    runner.os,
                    "open",
                    side_effect=AssertionError("direct FIFO must fail before open"),
                ),
                self.assertRaisesRegex(
                    runner.DiagnosticRunnerError,
                    "not a regular file",
                ),
            ):
                runner._read_regular_file_nofollow(fifo, "synthetic FIFO")

            candidate = root / "candidate.json"
            candidate.write_bytes(b"candidate\n")
            parent_fd = runner.os.open(root, runner.os.O_RDONLY)
            original_open = runner.os.open

            def swap_regular_for_fifo(
                path: object,
                flags: int,
                *args: object,
                **kwargs: object,
            ) -> int:
                if path == candidate.name:
                    self.assertTrue(flags & getattr(runner.os, "O_NONBLOCK", 0))
                    return original_open(fifo.name, flags, *args, **kwargs)
                return original_open(path, flags, *args, **kwargs)

            try:
                with (
                    patch.object(
                        runner.os,
                        "open",
                        side_effect=swap_regular_for_fifo,
                    ),
                    self.assertRaisesRegex(
                        runner.DiagnosticRunnerError,
                        "changed while its regular file was opened",
                    ),
                ):
                    runner._read_regular_file_at(parent_fd, candidate.name)
            finally:
                runner.os.close(parent_fd)

    def test_bounded_reader_rejects_growth_and_explicit_oversize(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate = root / "candidate.json"
            candidate.write_bytes(b"candidate\n")
            parent_fd = runner.os.open(root, runner.os.O_RDONLY)
            original_read = runner.os.read
            grew = False

            def grow_after_first_read(descriptor: int, byte_count: int) -> bytes:
                nonlocal grew
                chunk = original_read(descriptor, byte_count)
                if not grew:
                    with candidate.open("ab") as handle:
                        handle.write(b"growth")
                    grew = True
                return chunk

            try:
                with (
                    patch.object(
                        runner.os,
                        "read",
                        side_effect=grow_after_first_read,
                    ),
                    self.assertRaisesRegex(
                        runner.DiagnosticRunnerError,
                        "grew during observation",
                    ),
                ):
                    runner._read_regular_file_at(parent_fd, candidate.name)
                with self.assertRaisesRegex(
                    runner.DiagnosticRunnerError,
                    "bounded regular file",
                ):
                    runner._read_regular_file_at(
                        parent_fd,
                        candidate.name,
                        max_bytes=4,
                    )
            finally:
                runner.os.close(parent_fd)

    def test_directory_closure_exits_and_closes_on_first_foreign_entry(
        self,
    ) -> None:
        class _Entry:
            name = "foreign"

        class _UnboundedScandir:
            def __init__(self) -> None:
                self.closed = False
                self.next_calls = 0

            def __enter__(self) -> _UnboundedScandir:
                return self

            def __exit__(self, *args: object) -> None:
                self.closed = True

            def __iter__(self) -> _UnboundedScandir:
                return self

            def __next__(self) -> _Entry:
                self.next_calls += 1
                if self.next_calls > 4:
                    raise AssertionError("directory closure exhausted unbounded input")
                return _Entry()

        entries = _UnboundedScandir()
        with patch.object(runner.os, "scandir", return_value=entries):
            self.assertFalse(
                runner._directory_has_exact_entries(
                    123,
                    {"manifest.json", "records.jsonl"},
                )
            )
        self.assertEqual(entries.next_calls, 1)
        self.assertTrue(entries.closed)

    def test_artifact_records_observer_streams_and_rejects_growth_or_cap(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "artifact"
            artifact.mkdir()
            manifest_payload: dict[str, object] = {}
            (artifact / "manifest.json").write_bytes(
                runner._canonical_bytes(manifest_payload)
            )
            records = artifact / "records.jsonl"
            records_bytes = b'{"fixture":true}\n'
            records.write_bytes(records_bytes)
            parent_fd = runner.os.open(root, runner.os.O_RDONLY)
            artifact_stat = artifact.stat()
            artifact_identity = (artifact_stat.st_dev, artifact_stat.st_ino)
            digest = runner._sha256_bytes(records_bytes)
            try:
                self.assertTrue(
                    runner._published_artifact_matches(
                        parent_fd,
                        artifact.name,
                        artifact_identity,
                        manifest_payload,
                        records_byte_count=len(records_bytes),
                        records_sha256=digest,
                        commit_receipt=None,
                    )
                )
                with patch.object(runner, "_MAX_RECORDS_FILE_BYTES", 4):
                    self.assertFalse(
                        runner._published_artifact_matches(
                            parent_fd,
                            artifact.name,
                            artifact_identity,
                            manifest_payload,
                            records_byte_count=len(records_bytes),
                            records_sha256=digest,
                            commit_receipt=None,
                        )
                    )

                original_read = runner.os.read
                records_identity = (records.stat().st_dev, records.stat().st_ino)
                grew = False

                def grow_records_after_first_read(
                    descriptor: int,
                    byte_count: int,
                ) -> bytes:
                    nonlocal grew
                    chunk = original_read(descriptor, byte_count)
                    observed = runner.os.fstat(descriptor)
                    if (
                        not grew
                        and (
                            observed.st_dev,
                            observed.st_ino,
                        )
                        == records_identity
                    ):
                        with records.open("ab") as handle:
                            handle.write(b"growth")
                        grew = True
                    return chunk

                with patch.object(
                    runner.os,
                    "read",
                    side_effect=grow_records_after_first_read,
                ):
                    self.assertFalse(
                        runner._published_artifact_matches(
                            parent_fd,
                            artifact.name,
                            artifact_identity,
                            manifest_payload,
                            records_byte_count=len(records_bytes),
                            records_sha256=digest,
                            commit_receipt=None,
                        )
                    )
                self.assertTrue(grew)
            finally:
                runner.os.close(parent_fd)

    def test_artifact_collective_snapshot_rejects_final_closure_manifest_race(
        self,
    ) -> None:
        for race in ("mutation", "replacement"):
            with self.subTest(race=race), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                artifact = root / "artifact"
                artifact.mkdir()
                manifest_payload: dict[str, object] = {}
                manifest = artifact / "manifest.json"
                manifest.write_bytes(runner._canonical_bytes(manifest_payload))
                records_bytes = b'{"fixture":true}\n'
                (artifact / "records.jsonl").write_bytes(records_bytes)
                parent_fd = runner.os.open(root, runner.os.O_RDONLY)
                artifact_stat = artifact.stat()
                artifact_identity = (artifact_stat.st_dev, artifact_stat.st_ino)
                original_closure = runner._directory_has_exact_entries
                closure_calls = 0

                def race_after_final_closure(
                    directory_fd: int,
                    expected_filenames: set[str],
                ) -> bool:
                    nonlocal closure_calls
                    exact = original_closure(directory_fd, expected_filenames)
                    closure_calls += 1
                    if closure_calls == 2:
                        if race == "mutation":
                            manifest.write_bytes(b"[]\n")
                        else:
                            replacement = artifact / ".manifest-replacement"
                            replacement.write_bytes(manifest.read_bytes())
                            replacement.replace(manifest)
                    return exact

                try:
                    with patch.object(
                        runner,
                        "_directory_has_exact_entries",
                        side_effect=race_after_final_closure,
                    ):
                        self.assertFalse(
                            runner._published_artifact_matches(
                                parent_fd,
                                artifact.name,
                                artifact_identity,
                                manifest_payload,
                                records_byte_count=len(records_bytes),
                                records_sha256=runner._sha256_bytes(records_bytes),
                                commit_receipt=None,
                            )
                        )
                    self.assertEqual(closure_calls, 2)
                finally:
                    runner.os.close(parent_fd)

    def test_authorization_mismatch_requires_a_parent_durability_barrier(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            destination = root / "authorization.json"
            destination.write_bytes(b"foreign\n")
            root_identity = (root.stat().st_dev, root.stat().st_ino)
            original_fsync = runner.os.fsync

            def fail_parent_barrier(descriptor: int) -> None:
                observed = runner.os.fstat(descriptor)
                if (observed.st_dev, observed.st_ino) == root_identity:
                    raise OSError("authorization absence barrier unavailable")
                original_fsync(descriptor)

            with patch.object(
                runner.os,
                "fsync",
                side_effect=fail_parent_barrier,
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticPublicationStateAmbiguousError,
                    "durability and exact rollback",
                ):
                    runner._write_canonical_file_noreplace(
                        destination,
                        {"status": "candidate"},
                    )
            self.assertEqual(destination.read_bytes(), b"foreign\n")

    def test_foreign_file_swap_is_restored_and_never_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            authority = root / "authority.json"
            foreign = root / "foreign.json"
            stolen = root / "stolen-authority.json"
            expected = b"exact-authority\n"
            authority.write_bytes(expected)
            foreign.write_bytes(b"foreign-replacement\n")
            authority_stat = authority.stat()
            authority_identity = (authority_stat.st_dev, authority_stat.st_ino)
            directory_fd = runner.os.open(root, runner.os.O_RDONLY)
            original_rename = runner._rename_noreplace_at
            swapped = False

            def swap_before_quarantine(
                source_directory_fd: int,
                source_name: str,
                destination_directory_fd: int,
                destination_name: str,
            ) -> None:
                nonlocal swapped
                if source_name == authority.name and not swapped:
                    swapped = True
                    authority.rename(stolen)
                    foreign.rename(authority)
                original_rename(
                    source_directory_fd,
                    source_name,
                    destination_directory_fd,
                    destination_name,
                )

            try:
                with patch.object(
                    runner,
                    "_rename_noreplace_at",
                    side_effect=swap_before_quarantine,
                ):
                    tombstone = runner._quarantine_exact_file_at(
                        directory_fd,
                        authority.name,
                        expected,
                        expected_identity=authority_identity,
                        label="authorization",
                    )
            finally:
                runner.os.close(directory_fd)
            self.assertTrue(swapped)
            self.assertIsNone(tombstone)
            self.assertEqual(authority.read_bytes(), b"foreign-replacement\n")
            self.assertEqual(stolen.read_bytes(), expected)
            self.assertFalse(any(".revoked-" in path.name for path in root.iterdir()))

    def test_foreign_directory_swap_is_restored_and_never_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            authority = root / "attempt"
            foreign = root / "foreign-attempt"
            stolen = root / "stolen-attempt"
            authority.mkdir()
            (authority / "exact.txt").write_text("exact", encoding="utf-8")
            foreign.mkdir()
            (foreign / "foreign.txt").write_text("foreign", encoding="utf-8")
            parent_fd = runner.os.open(root, runner.os.O_RDONLY)
            authority_fd = runner.os.open(authority, runner.os.O_RDONLY)
            authority_stat = authority.stat()
            authority_identity = (authority_stat.st_dev, authority_stat.st_ino)
            original_rename = runner._rename_noreplace_at
            swapped = False

            def swap_before_quarantine(
                source_directory_fd: int,
                source_name: str,
                destination_directory_fd: int,
                destination_name: str,
            ) -> None:
                nonlocal swapped
                if source_name == authority.name and not swapped:
                    swapped = True
                    authority.rename(stolen)
                    foreign.rename(authority)
                original_rename(
                    source_directory_fd,
                    source_name,
                    destination_directory_fd,
                    destination_name,
                )

            try:
                with patch.object(
                    runner,
                    "_rename_noreplace_at",
                    side_effect=swap_before_quarantine,
                ):
                    tombstone = runner._quarantine_exact_directory_at(
                        parent_fd,
                        authority.name,
                        authority_fd,
                        authority_identity,
                        label="attempt reservation",
                    )
            finally:
                runner.os.close(authority_fd)
                runner.os.close(parent_fd)
            self.assertTrue(swapped)
            self.assertIsNone(tombstone)
            self.assertEqual(
                (authority / "foreign.txt").read_text(encoding="utf-8"),
                "foreign",
            )
            self.assertEqual(
                (stolen / "exact.txt").read_text(encoding="utf-8"),
                "exact",
            )

    def test_foreign_nondirectory_swap_is_restored_from_directory_tombstone(
        self,
    ) -> None:
        for foreign_kind in ("file", "symlink", "fifo"):
            with (
                self.subTest(foreign_kind=foreign_kind),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                authority = root / "attempt"
                foreign = root / "foreign-entry"
                stolen = root / "stolen-attempt"
                authority.mkdir()
                (authority / "exact.txt").write_text("exact", encoding="utf-8")
                if foreign_kind == "file":
                    foreign.write_text("foreign", encoding="utf-8")
                elif foreign_kind == "symlink":
                    foreign.symlink_to("foreign-target")
                else:
                    runner.os.mkfifo(foreign)
                foreign_stat = foreign.lstat()
                foreign_identity = (foreign_stat.st_dev, foreign_stat.st_ino)
                parent_fd = runner.os.open(root, runner.os.O_RDONLY)
                authority_fd = runner.os.open(authority, runner.os.O_RDONLY)
                authority_stat = authority.stat()
                authority_identity = (
                    authority_stat.st_dev,
                    authority_stat.st_ino,
                )
                original_rename = runner._rename_noreplace_at
                swapped = False

                def swap_before_quarantine(
                    source_directory_fd: int,
                    source_name: str,
                    destination_directory_fd: int,
                    destination_name: str,
                ) -> None:
                    nonlocal swapped
                    if source_name == authority.name and not swapped:
                        swapped = True
                        authority.rename(stolen)
                        foreign.rename(authority)
                    original_rename(
                        source_directory_fd,
                        source_name,
                        destination_directory_fd,
                        destination_name,
                    )

                try:
                    with patch.object(
                        runner,
                        "_rename_noreplace_at",
                        side_effect=swap_before_quarantine,
                    ):
                        tombstone = runner._quarantine_exact_directory_at(
                            parent_fd,
                            authority.name,
                            authority_fd,
                            authority_identity,
                            label="attempt reservation",
                        )
                finally:
                    runner.os.close(authority_fd)
                    runner.os.close(parent_fd)

                restored = authority.lstat()
                self.assertTrue(swapped)
                self.assertIsNone(tombstone)
                self.assertEqual(
                    (restored.st_dev, restored.st_ino),
                    foreign_identity,
                )
                if foreign_kind == "file":
                    self.assertEqual(
                        authority.read_text(encoding="utf-8"),
                        "foreign",
                    )
                elif foreign_kind == "symlink":
                    self.assertTrue(authority.is_symlink())
                    self.assertEqual(runner.os.readlink(authority), "foreign-target")
                else:
                    self.assertTrue(runner.stat.S_ISFIFO(restored.st_mode))
                self.assertTrue((stolen / "exact.txt").is_file())
                self.assertFalse(
                    any(".revoked-" in path.name for path in root.iterdir())
                )

    def test_foreign_staging_swap_is_not_deleted_by_finally_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory_fd = runner.os.open(root, runner.os.O_RDONLY)
            original_rename = runner._rename_noreplace_at
            staged_name = ""
            stolen = root / "stolen-staging.json"
            foreign = b"foreign-staging\n"

            def replace_staging_then_fail(
                source_directory_fd: int,
                source_name: str,
                destination_directory_fd: int,
                destination_name: str,
            ) -> None:
                nonlocal staged_name
                if destination_name == "receipt.json":
                    staged_name = source_name
                    (root / source_name).rename(stolen)
                    (root / source_name).write_bytes(foreign)
                    raise OSError("synthetic staging substitution")
                original_rename(
                    source_directory_fd,
                    source_name,
                    destination_directory_fd,
                    destination_name,
                )

            try:
                with patch.object(
                    runner,
                    "_rename_noreplace_at",
                    side_effect=replace_staging_then_fail,
                ):
                    with self.assertRaises(runner._ExactPublicationRevokedError):
                        runner._write_canonical_file_noreplace_at(
                            directory_fd,
                            "receipt.json",
                            {"status": "PENDING"},
                        )
            finally:
                runner.os.close(directory_fd)
            self.assertTrue(staged_name)
            self.assertEqual((root / staged_name).read_bytes(), foreign)
            self.assertEqual(
                stolen.read_bytes(),
                runner._canonical_bytes({"status": "PENDING"}),
            )
            self.assertFalse((root / "receipt.json").exists())

    def test_atomic_artifact_publication_on_nondiagnostic_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            with (
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
                patch.object(runner, "_recheck_source_closure"),
            ):
                with self.assertRaises(runner.DiagnosticNotRunError):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=(_AUTHORIZATION_REVISION),
                        repository_root=Path(temporary),
                    )

    def test_fixture_bundle_properties_are_read_once_before_output(self) -> None:
        class _OneReadBundle:
            def __init__(self, source: _FakeBundle) -> None:
                self._source = source
                self.reads = {"cells": 0, "payloads": 0, "seal_digest": 0}

            @property
            def cells(self) -> tuple[DiagnosticCell, ...]:
                self.reads["cells"] += 1
                if self.reads["cells"] != 1:
                    raise AssertionError("bundle cells were reread")
                return self._source.cells

            @property
            def payloads(self) -> dict[str, object]:
                self.reads["payloads"] += 1
                if self.reads["payloads"] != 1:
                    raise AssertionError("bundle payloads were reread")
                return self._source.payloads

            @property
            def seal_digest(self) -> str:
                self.reads["seal_digest"] += 1
                if self.reads["seal_digest"] != 1:
                    raise AssertionError("bundle seal was reread")
                return self._source.seal_digest

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "artifact"
            fixture = _preflight(output)
            authorization = runner._authorization_payload(fixture)
            bundle = _OneReadBundle(fixture.bundle)  # type: ignore[arg-type]
            preflight = replace(fixture, bundle=bundle)
            with patch.object(runner, "_recheck_source_closure"):
                manifest = runner._publish_run_artifact(
                    preflight,
                    authorization,
                    reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                    repository_root=Path(temporary),
                )
            self.assertEqual(manifest["cell_count"], 1)
            self.assertEqual(
                bundle.reads,
                {"cells": 1, "payloads": 1, "seal_digest": 1},
            )

    def test_fixture_and_authorization_alias_mutation_cannot_reach_execution(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            frozen_authorization = json.loads(json.dumps(authorization))
            original_open = runner._open_stable_directory
            mutated = False

            def mutate_after_snapshot(path: Path, label: str):  # type: ignore[no-untyped-def]
                nonlocal mutated
                if not mutated:
                    mutated = True
                    tasks = preflight.bundle._payloads["diagnostic_tasks.json"][  # type: ignore[attr-defined,index]
                        "tasks"
                    ]
                    tasks[0]["target"] = -1
                    authorization["artifact_id"] = "mutated-after-snapshot"
                return original_open(path, label)

            with (
                patch.object(runner, "_recheck_source_closure"),
                patch.object(
                    runner,
                    "_open_stable_directory",
                    side_effect=mutate_after_snapshot,
                ),
            ):
                manifest = runner._publish_run_artifact(
                    preflight,
                    authorization,
                    reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                    repository_root=Path(temporary),
                )
            self.assertTrue(mutated)
            self.assertEqual(manifest["execution_authorization"], frozen_authorization)
            lines = (output / "records.jsonl").read_bytes().splitlines()
            self.assertEqual(len(lines), 1)
            self.assertEqual(
                json.loads(lines[0])["cell_id"], preflight.cells[0].cell_id
            )

    def test_artifact_rename_syncs_both_source_and_destination_parents(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            original_rename = runner._rename_noreplace_at
            original_fsync = runner.os.fsync
            rename_complete = False
            source_fd = -1
            destination_fd = -1
            synced_after_rename: list[int] = []

            def record_artifact_rename(
                source_directory_fd: int,
                source_name: str,
                destination_directory_fd: int,
                destination_name: str,
            ) -> None:
                nonlocal destination_fd, rename_complete, source_fd
                if destination_name == output.name:
                    source_fd = source_directory_fd
                    destination_fd = destination_directory_fd
                    self.assertEqual(source_name, "staging")
                original_rename(
                    source_directory_fd,
                    source_name,
                    destination_directory_fd,
                    destination_name,
                )
                if destination_name == output.name:
                    rename_complete = True

            def record_sync(descriptor: int) -> None:
                if rename_complete:
                    synced_after_rename.append(descriptor)
                original_fsync(descriptor)

            with (
                patch.object(runner, "_recheck_source_closure"),
                patch.object(
                    runner,
                    "_rename_noreplace_at",
                    side_effect=record_artifact_rename,
                ),
                patch.object(runner.os, "fsync", side_effect=record_sync),
            ):
                runner._publish_run_artifact(
                    preflight,
                    authorization,
                    reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                    repository_root=root,
                )
            self.assertGreaterEqual(source_fd, 0)
            self.assertGreaterEqual(destination_fd, 0)
            self.assertNotEqual(source_fd, destination_fd)
            self.assertIn(source_fd, synced_after_rename)
            self.assertIn(destination_fd, synced_after_rename)

    def test_post_rename_source_barrier_failure_is_invalid_not_not_run(
        self,
    ) -> None:
        """A failed source-directory barrier spends the durable STARTED attempt."""

        for failure in (OSError, KeyboardInterrupt, SystemExit):
            with (
                self.subTest(failure=failure.__name__),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                output = root / "artifact"
                preflight = _preflight(output)
                authorization = runner._authorization_payload(preflight)
                original_rename = runner._rename_noreplace_at
                original_fsync = runner.os.fsync
                rename_complete = False
                source_fd = -1
                injected = False

                def record_artifact_rename(
                    source_directory_fd: int,
                    source_name: str,
                    destination_directory_fd: int,
                    destination_name: str,
                ) -> None:
                    nonlocal rename_complete, source_fd
                    original_rename(
                        source_directory_fd,
                        source_name,
                        destination_directory_fd,
                        destination_name,
                    )
                    if destination_name == output.name:
                        self.assertEqual(source_name, "staging")
                        source_fd = source_directory_fd
                        rename_complete = True

                def fail_only_post_rename_source_barrier(descriptor: int) -> None:
                    nonlocal injected
                    if rename_complete and descriptor == source_fd and not injected:
                        injected = True
                        raise failure("synthetic post-rename source barrier failure")
                    original_fsync(descriptor)

                with (
                    patch.object(runner, "_recheck_source_closure"),
                    patch.object(
                        runner,
                        "_rename_noreplace_at",
                        side_effect=record_artifact_rename,
                    ),
                    patch.object(
                        runner.os,
                        "fsync",
                        side_effect=fail_only_post_rename_source_barrier,
                    ),
                ):
                    with self.assertRaisesRegex(
                        runner.DiagnosticInvalidRunError,
                        "synthetic post-rename source barrier failure",
                    ):
                        runner._publish_run_artifact(
                            preflight,
                            authorization,
                            reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                            repository_root=root,
                        )

                self.assertTrue(rename_complete)
                self.assertGreaterEqual(source_fd, 0)
                self.assertTrue(injected)
                self.assertFalse((output / "commit.json").exists())
                attempt = root / (
                    f".artifact.attempt-{authorization['deterministic_digest']}"
                )
                self.assertTrue((attempt / "started.json").is_file())
                self.assertTrue((attempt / "invalid.json").is_file())
                self.assertFalse((attempt / "not_run.json").exists())

    def test_started_failure_retains_invalid_marker_and_staging(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            with (
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

    def test_post_started_close_baseexceptions_do_not_mask_typed_status(
        self,
    ) -> None:
        for cleanup_error in (KeyboardInterrupt, SystemExit):
            for terminal_receipt_fails in (False, True):
                with (
                    self.subTest(
                        cleanup_error=cleanup_error.__name__,
                        terminal_receipt_fails=terminal_receipt_fails,
                    ),
                    tempfile.TemporaryDirectory() as temporary,
                ):
                    root = Path(temporary)
                    output = root / "artifact"
                    preflight = _preflight(output)
                    authorization = runner._authorization_payload(preflight)
                    original_close = runner.os.close
                    original_open = runner.os.open
                    original_write = runner._write_attempt_receipt
                    close_armed = False
                    attempt_fd = -1
                    staging_fd = -1
                    failed_closes: list[int] = []

                    def capture_staging_open(
                        path: object,
                        *args: object,
                        **kwargs: object,
                    ) -> int:
                        nonlocal staging_fd
                        descriptor = original_open(path, *args, **kwargs)
                        if path == "staging":
                            staging_fd = descriptor
                        return descriptor

                    def terminate_started_attempt(
                        *args: object,
                        **kwargs: object,
                    ):
                        nonlocal attempt_fd, close_armed
                        attempt = args[0]
                        filename = args[1]
                        assert isinstance(attempt, runner._Attempt)
                        assert isinstance(filename, str)
                        if filename == "invalid.json":
                            attempt_fd = attempt.directory_fd
                            if terminal_receipt_fails:
                                close_armed = True
                                raise OSError("primary INVALID receipt failure")
                        payload = original_write(*args, **kwargs)
                        if filename == "invalid.json":
                            close_armed = True
                        return payload

                    def fail_close_after_success(descriptor: int) -> None:
                        original_close(descriptor)
                        if close_armed:
                            failed_closes.append(descriptor)
                            raise cleanup_error("synthetic cleanup close failure")

                    expected_error = (
                        runner.DiagnosticPublicationStateAmbiguousError
                        if terminal_receipt_fails
                        else runner.DiagnosticInvalidRunError
                    )
                    expected_message = (
                        "INVALID receipt durability is unproven"
                        if terminal_receipt_fails
                        else "primary post-STARTED failure"
                    )
                    with (
                        patch.object(runner, "_recheck_source_closure"),
                        patch.object(
                            runner.os,
                            "open",
                            side_effect=capture_staging_open,
                        ),
                        patch.object(
                            runner,
                            "_execute_cell",
                            side_effect=runner.DiagnosticRunnerError(
                                "primary post-STARTED failure"
                            ),
                        ),
                        patch.object(
                            runner,
                            "_write_attempt_receipt",
                            side_effect=terminate_started_attempt,
                        ),
                        patch.object(
                            runner.os,
                            "close",
                            side_effect=fail_close_after_success,
                        ),
                    ):
                        with self.assertRaisesRegex(expected_error, expected_message):
                            runner._publish_run_artifact(
                                preflight,
                                authorization,
                                reviewed_authorization_revision=(
                                    _AUTHORIZATION_REVISION
                                ),
                                repository_root=root,
                            )
                    self.assertGreaterEqual(staging_fd, 0)
                    self.assertGreaterEqual(attempt_fd, 0)
                    self.assertIn(staging_fd, failed_closes)
                    self.assertIn(attempt_fd, failed_closes)
                    self.assertGreaterEqual(len(failed_closes), 4)

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

    def test_commit_recovery_close_baseexceptions_do_not_relabel_started(self) -> None:
        for cleanup_error in (KeyboardInterrupt, SystemExit):
            with (
                self.subTest(cleanup_error=cleanup_error.__name__),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                output = root / "artifact"
                preflight = _preflight(output)
                authorization = runner._authorization_payload(preflight)
                original_write = runner._write_canonical_file_noreplace_at
                original_close = runner.os.close
                close_armed = False
                failed_closes: list[int] = []

                def commit_then_interrupt(
                    directory_fd: int,
                    filename: str,
                    payload: dict[str, object],
                ) -> None:
                    nonlocal close_armed
                    original_write(directory_fd, filename, payload)
                    if filename == "commit.json":
                        close_armed = True
                        raise OSError("post-commit publication interruption")

                def fail_close_after_success(descriptor: int) -> None:
                    original_close(descriptor)
                    if close_armed:
                        failed_closes.append(descriptor)
                        raise cleanup_error("synthetic recovery close failure")

                with (
                    patch.object(runner, "_recheck_source_closure"),
                    patch.object(
                        runner,
                        "_write_canonical_file_noreplace_at",
                        side_effect=commit_then_interrupt,
                    ),
                    patch.object(
                        runner.os,
                        "close",
                        side_effect=fail_close_after_success,
                    ),
                ):
                    manifest = runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                        repository_root=root,
                    )
                self.assertEqual(manifest["attempt_phase"], "READY_TO_COMMIT")
                self.assertTrue((output / "commit.json").is_file())
                self.assertGreaterEqual(len(failed_closes), 1)

    def test_commit_recovery_baseexceptions_never_relabel_ready_attempt_not_run(
        self,
    ) -> None:
        for recovery_stage in (
            "pinned_observation",
            "public_observation",
            "durability_retry",
            "commit_revoke",
        ):
            for interruption in (KeyboardInterrupt, SystemExit):
                with (
                    self.subTest(
                        recovery_stage=recovery_stage,
                        interruption=interruption.__name__,
                    ),
                    tempfile.TemporaryDirectory() as temporary,
                ):
                    root = Path(temporary)
                    output = root / "artifact"
                    preflight = _preflight(output)
                    authorization = runner._authorization_payload(preflight)
                    original_write = runner._write_canonical_file_noreplace_at

                    def commit_then_interrupt(
                        directory_fd: int,
                        filename: str,
                        payload: dict[str, object],
                    ) -> tuple[int, int]:
                        identity = original_write(directory_fd, filename, payload)
                        if filename == "commit.json":
                            raise OSError("post-commit publication interruption")
                        return identity

                    injected = interruption(f"synthetic {recovery_stage} interruption")
                    expected_error: type[BaseException]
                    if recovery_stage == "durability_retry":
                        expected_error = runner.DiagnosticInvalidRunError
                    else:
                        expected_error = runner.DiagnosticPublicationStateAmbiguousError

                    with ExitStack() as stack:
                        stack.enter_context(
                            patch.object(runner, "_recheck_source_closure")
                        )
                        stack.enter_context(
                            patch.object(
                                runner,
                                "_write_canonical_file_noreplace_at",
                                side_effect=commit_then_interrupt,
                            )
                        )
                        if recovery_stage == "pinned_observation":
                            stack.enter_context(
                                patch.object(
                                    runner,
                                    "_pinned_exact_artifact_commit_identity",
                                    side_effect=injected,
                                )
                            )
                            stack.enter_context(
                                patch.object(
                                    runner,
                                    "_published_exact_artifact_commit_identity",
                                    return_value=None,
                                )
                            )
                        elif recovery_stage == "public_observation":
                            stack.enter_context(
                                patch.object(
                                    runner,
                                    "_pinned_exact_artifact_commit_identity",
                                    return_value=None,
                                )
                            )
                            stack.enter_context(
                                patch.object(
                                    runner,
                                    "_published_exact_artifact_commit_identity",
                                    side_effect=injected,
                                )
                            )
                        elif recovery_stage == "durability_retry":
                            stack.enter_context(
                                patch.object(
                                    runner,
                                    "_retry_committed_artifact_durability",
                                    side_effect=injected,
                                )
                            )
                        else:
                            stack.enter_context(
                                patch.object(
                                    runner,
                                    "_retry_committed_artifact_durability",
                                    return_value=False,
                                )
                            )
                            stack.enter_context(
                                patch.object(
                                    runner,
                                    "_revoke_exact_artifact_commit_at",
                                    side_effect=injected,
                                )
                            )
                        with self.assertRaises(expected_error):
                            runner._publish_run_artifact(
                                preflight,
                                authorization,
                                reviewed_authorization_revision=(
                                    _AUTHORIZATION_REVISION
                                ),
                                repository_root=root,
                            )

                    attempt = root / (
                        f".artifact.attempt-{authorization['deterministic_digest']}"
                    )
                    self.assertTrue((attempt / "started.json").is_file())
                    self.assertTrue((attempt / "ready_to_commit.json").is_file())
                    self.assertFalse((attempt / "not_run.json").exists())
                    if recovery_stage == "durability_retry":
                        self.assertTrue((attempt / "invalid.json").is_file())
                        self.assertFalse((output / "commit.json").exists())
                        self.assertTrue(
                            any(
                                path.name.startswith(".commit.json.revoked-")
                                for path in output.iterdir()
                            )
                        )
                    else:
                        self.assertFalse((attempt / "invalid.json").exists())
                        self.assertTrue((output / "commit.json").is_file())

    def test_interrupt_after_started_transition_return_is_durably_invalid(
        self,
    ) -> None:
        for interruption in (KeyboardInterrupt, SystemExit):
            with (
                self.subTest(interruption=interruption.__name__),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                output = root / "artifact"
                preflight = _preflight(output)
                authorization = runner._authorization_payload(preflight)
                original_transition = runner._transition_attempt_to_started

                def transition_then_interrupt(
                    attempt: runner._Attempt,
                ) -> dict[str, object]:
                    original_transition(attempt)
                    raise interruption("synthetic STARTED return interruption")

                with (
                    patch.object(runner, "_recheck_source_closure"),
                    patch.object(
                        runner,
                        "_transition_attempt_to_started",
                        side_effect=transition_then_interrupt,
                    ),
                ):
                    with self.assertRaisesRegex(
                        runner.DiagnosticInvalidRunError,
                        "synthetic STARTED return interruption",
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
                self.assertTrue((attempt / "started.json").is_file())
                self.assertTrue((attempt / "invalid.json").is_file())
                self.assertFalse((attempt / "not_run.json").exists())
                self.assertFalse(output.exists())

    def test_interrupt_after_locked_publication_return_is_never_not_run(
        self,
    ) -> None:
        for interruption in (KeyboardInterrupt, SystemExit):
            with (
                self.subTest(interruption=interruption.__name__),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                output = root / "artifact"
                preflight = _preflight(output)
                authorization = runner._authorization_payload(preflight)
                original_publish_locked = runner._publish_run_artifact_locked

                def publish_then_interrupt(*args: object, **kwargs: object):
                    original_publish_locked(*args, **kwargs)
                    raise interruption("synthetic publication return interruption")

                with (
                    patch.object(runner, "_recheck_source_closure"),
                    patch.object(
                        runner,
                        "_publish_run_artifact_locked",
                        side_effect=publish_then_interrupt,
                    ),
                ):
                    with self.assertRaisesRegex(
                        runner.DiagnosticPublicationStateAmbiguousError,
                        "publication call boundary",
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
                self.assertTrue((attempt / "started.json").is_file())
                self.assertTrue((attempt / "ready_to_commit.json").is_file())
                self.assertFalse((attempt / "invalid.json").exists())
                self.assertFalse((attempt / "not_run.json").exists())
                self.assertEqual(
                    {path.name for path in output.iterdir()},
                    set(runner.ARTIFACT_FILENAMES),
                )

    def test_transient_double_none_commit_observation_recovers_committed(
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
            ) -> tuple[int, int]:
                identity = original_write(directory_fd, filename, payload)
                if filename == "commit.json":
                    raise OSError("synthetic post-commit observation window")
                return identity

            with (
                patch.object(runner, "_recheck_source_closure"),
                patch.object(
                    runner,
                    "_write_canonical_file_noreplace_at",
                    side_effect=commit_then_interrupt,
                ),
                patch.object(
                    runner,
                    "_pinned_exact_artifact_commit_identity",
                    return_value=None,
                ),
                patch.object(
                    runner,
                    "_published_exact_artifact_commit_identity",
                    return_value=None,
                ),
            ):
                manifest = runner._publish_run_artifact(
                    preflight,
                    authorization,
                    reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                    repository_root=root,
                )

            attempt = root / manifest["attempt_marker_basename"]
            self.assertEqual(manifest["attempt_phase"], "READY_TO_COMMIT")
            self.assertTrue((output / "commit.json").is_file())
            self.assertFalse((attempt / "invalid.json").exists())
            self.assertFalse((attempt / "not_run.json").exists())

    def test_byte_identical_public_directory_replacement_is_revoked_before_invalid(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            stolen = root / "stolen-original-artifact"
            replacement = root / "replacement-artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            original_write = runner._write_canonical_file_noreplace_at

            def commit_then_replace_directory(
                directory_fd: int,
                filename: str,
                payload: dict[str, object],
            ) -> tuple[int, int]:
                identity = original_write(directory_fd, filename, payload)
                if filename == "commit.json":
                    replacement.mkdir()
                    for member in runner.ARTIFACT_FILENAMES:
                        (replacement / member).write_bytes(
                            (output / member).read_bytes()
                        )
                    output.rename(stolen)
                    replacement.rename(output)
                    raise OSError("synthetic byte-identical directory replacement")
                return identity

            with (
                patch.object(runner, "_recheck_source_closure"),
                patch.object(
                    runner,
                    "_write_canonical_file_noreplace_at",
                    side_effect=commit_then_replace_directory,
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticInvalidRunError,
                    "synthetic byte-identical directory replacement",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                        repository_root=root,
                    )

            attempt = root / (
                f".artifact.attempt-{authorization['deterministic_digest']}"
            )
            self.assertNotEqual(
                (output.stat().st_dev, output.stat().st_ino),
                (stolen.stat().st_dev, stolen.stat().st_ino),
            )
            for artifact in (output, stolen):
                self.assertFalse((artifact / "commit.json").exists())
                revoked = [
                    path
                    for path in artifact.iterdir()
                    if path.name.startswith(".commit.json.revoked-")
                ]
                self.assertEqual(len(revoked), 1)
                self.assertEqual(
                    json.loads(revoked[0].read_bytes())["status"],
                    "COMMITTED",
                )
            self.assertEqual(
                (output / "manifest.json").read_bytes(),
                (stolen / "manifest.json").read_bytes(),
            )
            self.assertEqual(
                (output / "records.jsonl").read_bytes(),
                (stolen / "records.jsonl").read_bytes(),
            )
            self.assertTrue((attempt / "invalid.json").exists())
            self.assertFalse((attempt / "not_run.json").exists())

    def test_post_started_output_parent_replacement_is_publication_ambiguous(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            container = Path(temporary)
            authorized_parent = container / "authorized"
            replacement_parent = container / "replacement"
            displaced_parent = container / "displaced"
            authorized_parent.mkdir()
            replacement_parent.mkdir()
            output = authorized_parent / "artifact"
            replacement_output = replacement_parent / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            original_write = runner._write_canonical_file_noreplace_at
            parent_replaced = False

            def commit_then_replace_parent(
                directory_fd: int,
                filename: str,
                payload: dict[str, object],
            ) -> tuple[int, int]:
                nonlocal parent_replaced
                identity = original_write(directory_fd, filename, payload)
                if filename == "commit.json":
                    replacement_output.mkdir()
                    for member in runner.ARTIFACT_FILENAMES:
                        (replacement_output / member).write_bytes(
                            (output / member).read_bytes()
                        )
                    authorized_parent.rename(displaced_parent)
                    replacement_parent.rename(authorized_parent)
                    parent_replaced = True
                    raise OSError("synthetic output parent replacement")
                return identity

            with (
                patch.object(runner, "_recheck_source_closure"),
                patch.object(
                    runner,
                    "_write_canonical_file_noreplace_at",
                    side_effect=commit_then_replace_parent,
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticPublicationStateAmbiguousError,
                    "output parent identity drifted after STARTED",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                        repository_root=container,
                    )

            attempt = displaced_parent / (
                f".artifact.attempt-{authorization['deterministic_digest']}"
            )
            self.assertTrue(parent_replaced)
            self.assertTrue((attempt / "started.json").is_file())
            self.assertTrue((attempt / "ready_to_commit.json").is_file())
            self.assertFalse((attempt / "invalid.json").exists())
            self.assertFalse((attempt / "not_run.json").exists())
            for committed in (output, displaced_parent / "artifact"):
                self.assertEqual(
                    {path.name for path in committed.iterdir()},
                    set(runner.ARTIFACT_FILENAMES),
                )
                self.assertEqual(
                    json.loads((committed / "commit.json").read_bytes())["status"],
                    "COMMITTED",
                )

    def test_parent_swap_after_final_success_observation_is_ambiguous(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            container = Path(temporary)
            authorized_parent = container / "authorized"
            replacement_parent = container / "replacement"
            displaced_parent = container / "displaced"
            authorized_parent.mkdir()
            replacement_parent.mkdir()
            (replacement_parent / "foreign.txt").write_text(
                "preserve me",
                encoding="utf-8",
            )
            output = authorized_parent / "artifact"
            replacement_output = replacement_parent / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            original_matches = runner._published_artifact_matches
            parent_swapped = False

            def swap_parent_after_final_match(
                *args: object,
                **kwargs: object,
            ) -> bool:
                nonlocal parent_swapped
                matches = original_matches(*args, **kwargs)
                if (
                    matches
                    and kwargs.get("commit_receipt") is not None
                    and not parent_swapped
                ):
                    replacement_output.mkdir()
                    for member in runner.ARTIFACT_FILENAMES:
                        (replacement_output / member).write_bytes(
                            (output / member).read_bytes()
                        )
                    authorized_parent.rename(displaced_parent)
                    replacement_parent.rename(authorized_parent)
                    parent_swapped = True
                return matches

            with (
                patch.object(runner, "_recheck_source_closure"),
                patch.object(
                    runner,
                    "_published_artifact_matches",
                    side_effect=swap_parent_after_final_match,
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticPublicationStateAmbiguousError,
                    "output parent identity drifted after STARTED",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                        repository_root=container,
                    )

            attempt = displaced_parent / (
                f".artifact.attempt-{authorization['deterministic_digest']}"
            )
            self.assertTrue(parent_swapped)
            self.assertFalse((attempt / "invalid.json").exists())
            self.assertFalse((attempt / "not_run.json").exists())
            self.assertEqual(
                (authorized_parent / "foreign.txt").read_text(encoding="utf-8"),
                "preserve me",
            )
            for committed in (output, displaced_parent / "artifact"):
                self.assertEqual(
                    {path.name for path in committed.iterdir()},
                    set(runner.ARTIFACT_FILENAMES),
                )

    def test_parent_swap_after_recovery_commit_observation_is_ambiguous(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            container = Path(temporary)
            authorized_parent = container / "authorized"
            replacement_parent = container / "replacement"
            displaced_parent = container / "displaced"
            authorized_parent.mkdir()
            replacement_parent.mkdir()
            (replacement_parent / "foreign.txt").write_text(
                "preserve me",
                encoding="utf-8",
            )
            output = authorized_parent / "artifact"
            replacement_output = replacement_parent / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            original_file_write = runner._write_canonical_file_noreplace_at
            original_matches = runner._published_artifact_matches
            commit_interrupted = False
            parent_swapped = False

            def interrupt_after_commit(
                directory_fd: int,
                filename: str,
                payload: dict[str, object],
            ) -> tuple[int, int]:
                nonlocal commit_interrupted
                identity = original_file_write(directory_fd, filename, payload)
                if filename == "commit.json" and not commit_interrupted:
                    commit_interrupted = True
                    raise OSError("synthetic post-commit recovery")
                return identity

            def swap_parent_after_recovery_match(
                *args: object,
                **kwargs: object,
            ) -> bool:
                nonlocal parent_swapped
                matches = original_matches(*args, **kwargs)
                if (
                    commit_interrupted
                    and matches
                    and kwargs.get("commit_receipt") is not None
                    and not parent_swapped
                ):
                    replacement_output.mkdir()
                    for member in runner.ARTIFACT_FILENAMES:
                        (replacement_output / member).write_bytes(
                            (output / member).read_bytes()
                        )
                    authorized_parent.rename(displaced_parent)
                    replacement_parent.rename(authorized_parent)
                    parent_swapped = True
                return matches

            with (
                patch.object(runner, "_recheck_source_closure"),
                patch.object(
                    runner,
                    "_write_canonical_file_noreplace_at",
                    side_effect=interrupt_after_commit,
                ),
                patch.object(
                    runner,
                    "_published_artifact_matches",
                    side_effect=swap_parent_after_recovery_match,
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticPublicationStateAmbiguousError,
                    "run output parent path identity changed",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                        repository_root=container,
                    )

            attempt = displaced_parent / (
                f".artifact.attempt-{authorization['deterministic_digest']}"
            )
            self.assertTrue(commit_interrupted)
            self.assertTrue(parent_swapped)
            self.assertFalse((attempt / "invalid.json").exists())
            self.assertFalse((attempt / "not_run.json").exists())
            self.assertEqual(
                (authorized_parent / "foreign.txt").read_text(encoding="utf-8"),
                "preserve me",
            )
            for committed in (output, displaced_parent / "artifact"):
                self.assertEqual(
                    {path.name for path in committed.iterdir()},
                    set(runner.ARTIFACT_FILENAMES),
                )

    def test_recovered_commit_requires_attempt_source_directory_barrier(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            original_attempt_write = runner._write_attempt_receipt
            original_file_write = runner._write_canonical_file_noreplace_at
            original_fsync = runner.os.fsync
            attempt_fd = -1
            commit_interrupted = False
            source_barrier_failed = False

            def capture_attempt(
                attempt: runner._Attempt,
                filename: str,
                **kwargs: object,
            ) -> dict[str, object]:
                nonlocal attempt_fd
                receipt = original_attempt_write(attempt, filename, **kwargs)
                if filename == "ready_to_commit.json":
                    attempt_fd = attempt.directory_fd
                return receipt

            def interrupt_after_commit(
                directory_fd: int,
                filename: str,
                payload: dict[str, object],
            ) -> tuple[int, int]:
                nonlocal commit_interrupted
                identity = original_file_write(directory_fd, filename, payload)
                if filename == "commit.json" and not commit_interrupted:
                    commit_interrupted = True
                    raise OSError("synthetic post-commit recovery")
                return identity

            def fail_recovery_source_barrier(descriptor: int) -> None:
                nonlocal source_barrier_failed
                if (
                    commit_interrupted
                    and descriptor == attempt_fd
                    and not source_barrier_failed
                ):
                    source_barrier_failed = True
                    raise OSError("synthetic recovery source barrier failure")
                original_fsync(descriptor)

            with (
                patch.object(runner, "_recheck_source_closure"),
                patch.object(
                    runner,
                    "_write_attempt_receipt",
                    side_effect=capture_attempt,
                ),
                patch.object(
                    runner,
                    "_write_canonical_file_noreplace_at",
                    side_effect=interrupt_after_commit,
                ),
                patch.object(
                    runner.os,
                    "fsync",
                    side_effect=fail_recovery_source_barrier,
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticPublicationStateAmbiguousError,
                    "attempt reservation durability is unproven",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                        repository_root=root,
                    )

            attempt = root / (
                f".artifact.attempt-{authorization['deterministic_digest']}"
            )
            self.assertGreaterEqual(attempt_fd, 0)
            self.assertTrue(commit_interrupted)
            self.assertTrue(source_barrier_failed)
            self.assertTrue((output / "commit.json").is_file())
            self.assertFalse((attempt / "invalid.json").exists())
            self.assertFalse((attempt / "not_run.json").exists())

    def test_normal_commit_conflicting_invalid_receipt_is_never_committed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            original_attempt_write = runner._write_attempt_receipt
            original_matches = runner._published_artifact_matches
            captured_attempt: runner._Attempt | None = None
            invalid_injected = False

            def capture_attempt(
                attempt: runner._Attempt,
                filename: str,
                **kwargs: object,
            ) -> dict[str, object]:
                nonlocal captured_attempt
                receipt = original_attempt_write(attempt, filename, **kwargs)
                if filename == "ready_to_commit.json":
                    captured_attempt = attempt
                return receipt

            def inject_invalid_after_commit_match(
                *args: object,
                **kwargs: object,
            ) -> bool:
                nonlocal invalid_injected
                matches = original_matches(*args, **kwargs)
                if (
                    matches
                    and kwargs.get("commit_receipt") is not None
                    and not invalid_injected
                ):
                    if captured_attempt is None:
                        raise AssertionError("attempt was not captured")
                    original_attempt_write(
                        captured_attempt,
                        "invalid.json",
                        phase="STARTED",
                        status="INVALID",
                        reason="synthetic normal terminal conflict",
                    )
                    invalid_injected = True
                return matches

            with (
                patch.object(runner, "_recheck_source_closure"),
                patch.object(
                    runner,
                    "_write_attempt_receipt",
                    side_effect=capture_attempt,
                ),
                patch.object(
                    runner,
                    "_published_artifact_matches",
                    side_effect=inject_invalid_after_commit_match,
                ),
            ):
                with self.assertRaises(runner.DiagnosticPublicationStateAmbiguousError):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                        repository_root=root,
                    )

            attempt = root / (
                f".artifact.attempt-{authorization['deterministic_digest']}"
            )
            self.assertTrue(invalid_injected)
            self.assertTrue((attempt / "invalid.json").is_file())
            self.assertFalse((output / "commit.json").exists())
            self.assertTrue(
                any(
                    path.name.startswith(".commit.json.revoked-")
                    for path in output.iterdir()
                )
            )

    def test_recovery_reason_terminal_conflict_revokes_commit(self) -> None:
        for terminal_filename in ("invalid.json", "not_run.json"):
            with (
                self.subTest(terminal_filename=terminal_filename),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                output = root / "artifact"
                preflight = _preflight(output)
                authorization = runner._authorization_payload(preflight)
                original_attempt_write = runner._write_attempt_receipt
                original_file_write = runner._write_canonical_file_noreplace_at
                captured_attempt: runner._Attempt | None = None

                class TerminalWritingError(OSError):
                    def __init__(self) -> None:
                        super().__init__("synthetic post-commit terminal conflict")
                        self.str_calls = 0

                    def __str__(self) -> str:
                        self.str_calls += 1
                        if self.str_calls == 1:
                            if captured_attempt is None:
                                raise AssertionError("attempt was not captured")
                            if terminal_filename == "invalid.json":
                                original_attempt_write(
                                    captured_attempt,
                                    terminal_filename,
                                    phase="STARTED",
                                    status="INVALID",
                                    reason=("synthetic post-commit terminal conflict"),
                                )
                            else:
                                original_attempt_write(
                                    captured_attempt,
                                    terminal_filename,
                                    phase="PRE_OUTCOME",
                                    status="NOT_RUN",
                                    reason=("synthetic post-commit terminal conflict"),
                                )
                        return "synthetic post-commit terminal conflict"

                injected_error = TerminalWritingError()
                commit_interrupted = False

                def capture_attempt(
                    attempt: runner._Attempt,
                    filename: str,
                    **kwargs: object,
                ) -> dict[str, object]:
                    nonlocal captured_attempt
                    receipt = original_attempt_write(attempt, filename, **kwargs)
                    if filename == "ready_to_commit.json":
                        captured_attempt = attempt
                    return receipt

                def commit_then_raise(
                    directory_fd: int,
                    filename: str,
                    payload: dict[str, object],
                ) -> tuple[int, int]:
                    nonlocal commit_interrupted
                    identity = original_file_write(directory_fd, filename, payload)
                    if filename == "commit.json" and not commit_interrupted:
                        commit_interrupted = True
                        raise injected_error
                    return identity

                with (
                    patch.object(runner, "_recheck_source_closure"),
                    patch.object(
                        runner,
                        "_write_attempt_receipt",
                        side_effect=capture_attempt,
                    ),
                    patch.object(
                        runner,
                        "_write_canonical_file_noreplace_at",
                        side_effect=commit_then_raise,
                    ),
                ):
                    with self.assertRaisesRegex(
                        runner.DiagnosticInvalidRunError,
                        "synthetic post-commit terminal conflict",
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
                self.assertTrue(commit_interrupted)
                self.assertEqual(injected_error.str_calls, 1)
                self.assertTrue((attempt / terminal_filename).is_file())
                self.assertTrue((attempt / "invalid.json").is_file())
                self.assertFalse((output / "commit.json").exists())
                self.assertTrue(
                    any(
                        path.name.startswith(".commit.json.revoked-")
                        for path in output.iterdir()
                    )
                )

    def test_commit_published_by_invalid_hook_is_reconciled_and_revoked(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            original_file_write = runner._write_canonical_file_noreplace_at
            original_attempt_write = runner._write_attempt_receipt
            commit_write_failed = False
            late_commit_published = False

            def fail_initial_commit_write(
                directory_fd: int,
                filename: str,
                payload: dict[str, object],
            ) -> tuple[int, int]:
                nonlocal commit_write_failed
                if filename == "commit.json" and not commit_write_failed:
                    commit_write_failed = True
                    raise OSError("synthetic initial commit publication failure")
                return original_file_write(directory_fd, filename, payload)

            def publish_commit_after_invalid(
                attempt: runner._Attempt,
                filename: str,
                **kwargs: object,
            ) -> dict[str, object]:
                nonlocal late_commit_published
                receipt = original_attempt_write(attempt, filename, **kwargs)
                if filename == "invalid.json" and not late_commit_published:
                    manifest_payload = json.loads(
                        (output / "manifest.json").read_bytes()
                    )
                    started_payload = json.loads(
                        (attempt.directory / "started.json").read_bytes()
                    )
                    commit_payload = runner._with_digest(
                        {
                            "artifact_id": authorization["artifact_id"],
                            "attempt_started_receipt_digest": started_payload[
                                "deterministic_digest"
                            ],
                            "execution_authorization_digest": authorization[
                                "deterministic_digest"
                            ],
                            "run_manifest_digest": manifest_payload[
                                "deterministic_digest"
                            ],
                            "schema_version": runner.ARTIFACT_COMMIT_SCHEMA_VERSION,
                            "status": "COMMITTED",
                        }
                    )
                    flags = runner.os.O_RDONLY | getattr(
                        runner.os,
                        "O_DIRECTORY",
                        0,
                    )
                    flags |= getattr(runner.os, "O_NOFOLLOW", 0)
                    output_fd = runner.os.open(output, flags)
                    try:
                        original_file_write(
                            output_fd,
                            "commit.json",
                            commit_payload,
                        )
                    finally:
                        runner.os.close(output_fd)
                    late_commit_published = True
                return receipt

            with (
                patch.object(runner, "_recheck_source_closure"),
                patch.object(
                    runner,
                    "_write_canonical_file_noreplace_at",
                    side_effect=fail_initial_commit_write,
                ),
                patch.object(
                    runner,
                    "_write_attempt_receipt",
                    side_effect=publish_commit_after_invalid,
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticInvalidRunError,
                    "synthetic initial commit publication failure",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                        repository_root=root,
                    )

            attempt = root / (
                f".artifact.attempt-{authorization['deterministic_digest']}"
            )
            self.assertTrue(commit_write_failed)
            self.assertTrue(late_commit_published)
            self.assertTrue((attempt / "invalid.json").is_file())
            self.assertFalse((attempt / "not_run.json").exists())
            self.assertFalse((output / "commit.json").exists())
            self.assertTrue((output / "manifest.json").is_file())
            self.assertTrue((output / "records.jsonl").is_file())
            revoked = [
                path
                for path in output.iterdir()
                if path.name.startswith(".commit.json.revoked-")
            ]
            self.assertEqual(len(revoked), 1)
            self.assertEqual(json.loads(revoked[0].read_bytes())["status"], "COMMITTED")
            self.assertNotEqual(
                {path.name for path in output.iterdir()},
                set(runner.ARTIFACT_FILENAMES),
            )

    def test_post_rename_failure_has_commit_context_before_invalid_hook(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            foreign = root / "foreign.txt"
            foreign.write_text("preserve me", encoding="utf-8")
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            original_rename = runner._rename_noreplace_at
            original_fsync = runner.os.fsync
            original_file_write = runner._write_canonical_file_noreplace_at
            original_attempt_write = runner._write_attempt_receipt
            source_fd = -1
            rename_complete = False
            source_barrier_failed = False
            late_commit_published = False

            def record_artifact_rename(
                source_directory_fd: int,
                source_name: str,
                destination_directory_fd: int,
                destination_name: str,
            ) -> None:
                nonlocal rename_complete, source_fd
                original_rename(
                    source_directory_fd,
                    source_name,
                    destination_directory_fd,
                    destination_name,
                )
                if destination_name == output.name:
                    self.assertEqual(source_name, "staging")
                    source_fd = source_directory_fd
                    rename_complete = True

            def fail_first_post_rename_source_barrier(descriptor: int) -> None:
                nonlocal source_barrier_failed
                if (
                    rename_complete
                    and descriptor == source_fd
                    and not source_barrier_failed
                ):
                    source_barrier_failed = True
                    raise OSError("synthetic post-rename commit-context failure")
                original_fsync(descriptor)

            def publish_commit_after_invalid(
                attempt: runner._Attempt,
                filename: str,
                **kwargs: object,
            ) -> dict[str, object]:
                nonlocal late_commit_published
                receipt = original_attempt_write(attempt, filename, **kwargs)
                if filename == "invalid.json" and not late_commit_published:
                    manifest_payload = json.loads(
                        (output / "manifest.json").read_bytes()
                    )
                    started_payload = json.loads(
                        (attempt.directory / "started.json").read_bytes()
                    )
                    commit_payload = runner._with_digest(
                        {
                            "artifact_id": authorization["artifact_id"],
                            "attempt_started_receipt_digest": started_payload[
                                "deterministic_digest"
                            ],
                            "execution_authorization_digest": authorization[
                                "deterministic_digest"
                            ],
                            "run_manifest_digest": manifest_payload[
                                "deterministic_digest"
                            ],
                            "schema_version": runner.ARTIFACT_COMMIT_SCHEMA_VERSION,
                            "status": "COMMITTED",
                        }
                    )
                    flags = runner.os.O_RDONLY | getattr(
                        runner.os,
                        "O_DIRECTORY",
                        0,
                    )
                    flags |= getattr(runner.os, "O_NOFOLLOW", 0)
                    output_fd = runner.os.open(output, flags)
                    try:
                        original_file_write(
                            output_fd,
                            "commit.json",
                            commit_payload,
                        )
                    finally:
                        runner.os.close(output_fd)
                    late_commit_published = True
                return receipt

            with (
                patch.object(runner, "_recheck_source_closure"),
                patch.object(
                    runner,
                    "_rename_noreplace_at",
                    side_effect=record_artifact_rename,
                ),
                patch.object(
                    runner.os,
                    "fsync",
                    side_effect=fail_first_post_rename_source_barrier,
                ),
                patch.object(
                    runner,
                    "_write_attempt_receipt",
                    side_effect=publish_commit_after_invalid,
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticInvalidRunError,
                    "synthetic post-rename commit-context failure",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                        repository_root=root,
                    )

            attempt = root / (
                f".artifact.attempt-{authorization['deterministic_digest']}"
            )
            self.assertTrue(rename_complete)
            self.assertTrue(source_barrier_failed)
            self.assertTrue(late_commit_published)
            self.assertTrue((attempt / "invalid.json").is_file())
            self.assertFalse((attempt / "not_run.json").exists())
            self.assertFalse((output / "commit.json").exists())
            revoked = [
                path
                for path in output.iterdir()
                if path.name.startswith(".commit.json.revoked-")
            ]
            self.assertEqual(len(revoked), 1)
            self.assertEqual(json.loads(revoked[0].read_bytes())["status"], "COMMITTED")
            self.assertEqual(foreign.read_text(encoding="utf-8"), "preserve me")
            self.assertNotEqual(
                {path.name for path in output.iterdir()},
                set(runner.ARTIFACT_FILENAMES),
            )

    def test_parent_swap_after_final_recovery_absence_is_ambiguous(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            container = Path(temporary)
            authorized_parent = container / "authorized"
            replacement_parent = container / "replacement"
            displaced_parent = container / "displaced"
            authorized_parent.mkdir()
            replacement_parent.mkdir()
            replacement_output = replacement_parent / "artifact"
            replacement_output.mkdir()
            (replacement_output / "foreign.txt").write_text(
                "preserve me",
                encoding="utf-8",
            )
            output = authorized_parent / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            original_file_write = runner._write_canonical_file_noreplace_at
            original_content_identity = runner._published_artifact_content_identity
            commit_write_failed = False
            invalid_absence_observations = 0
            parent_swapped = False

            def fail_initial_commit_write(
                directory_fd: int,
                filename: str,
                payload: dict[str, object],
            ) -> tuple[int, int]:
                nonlocal commit_write_failed
                if filename == "commit.json" and not commit_write_failed:
                    commit_write_failed = True
                    raise OSError("synthetic commit publication failure")
                return original_file_write(directory_fd, filename, payload)

            def swap_parent_after_final_absence(
                *args: object,
                **kwargs: object,
            ) -> tuple[int, int] | None:
                nonlocal invalid_absence_observations, parent_swapped
                identity = original_content_identity(*args, **kwargs)
                attempt = authorized_parent / (
                    f".artifact.attempt-{authorization['deterministic_digest']}"
                )
                if identity is None and (attempt / "invalid.json").is_file():
                    invalid_absence_observations += 1
                    if invalid_absence_observations == 2 and not parent_swapped:
                        authorized_parent.rename(displaced_parent)
                        replacement_parent.rename(authorized_parent)
                        parent_swapped = True
                return identity

            with (
                patch.object(runner, "_recheck_source_closure"),
                patch.object(
                    runner,
                    "_write_canonical_file_noreplace_at",
                    side_effect=fail_initial_commit_write,
                ),
                patch.object(
                    runner,
                    "_published_artifact_content_identity",
                    side_effect=swap_parent_after_final_absence,
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticPublicationStateAmbiguousError,
                    "output parent identity drifted after STARTED",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                        repository_root=container,
                    )

            attempt = displaced_parent / (
                f".artifact.attempt-{authorization['deterministic_digest']}"
            )
            self.assertTrue(commit_write_failed)
            self.assertEqual(invalid_absence_observations, 2)
            self.assertTrue(parent_swapped)
            self.assertTrue((attempt / "invalid.json").is_file())
            self.assertFalse((attempt / "not_run.json").exists())
            self.assertEqual(
                (output / "foreign.txt").read_text(encoding="utf-8"),
                "preserve me",
            )
            self.assertFalse((displaced_parent / "artifact" / "commit.json").exists())

    def test_persistent_artifact_parent_sync_failure_revokes_commit_but_lock_is_ambiguous(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            original_write = runner._write_canonical_file_noreplace_at
            original_fsync = runner.os.fsync
            root_stat = root.stat()
            root_identity = (root_stat.st_dev, root_stat.st_ino)
            commit_written = False

            def arm_after_commit(
                directory_fd: int,
                filename: str,
                payload: dict[str, object],
            ) -> None:
                nonlocal commit_written
                original_write(directory_fd, filename, payload)
                if filename == "commit.json":
                    commit_written = True

            def fail_parent_sync(descriptor: int) -> None:
                observed = runner.os.fstat(descriptor)
                if (
                    commit_written
                    and (
                        observed.st_dev,
                        observed.st_ino,
                    )
                    == root_identity
                ):
                    raise OSError("persistent artifact parent sync failure")
                original_fsync(descriptor)

            with (
                patch.object(runner, "_recheck_source_closure"),
                patch.object(
                    runner,
                    "_write_canonical_file_noreplace_at",
                    side_effect=arm_after_commit,
                ),
                patch.object(runner.os, "fsync", side_effect=fail_parent_sync),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticPublicationStateAmbiguousError,
                    "publication lock retirement",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                        repository_root=root,
                    )
            self.assertFalse((output / "commit.json").exists())
            revoked_commits = [
                path
                for path in output.iterdir()
                if path.name.startswith(".commit.json.revoked-")
            ]
            self.assertEqual(len(revoked_commits), 1)
            self.assertEqual(
                json.loads(revoked_commits[0].read_bytes())["status"],
                "COMMITTED",
            )
            attempt = root / (
                f".artifact.attempt-{authorization['deterministic_digest']}"
            )
            self.assertTrue((attempt / "invalid.json").is_file())
            self.assertFalse((root / ".artifact.publish-lock").exists())

    def test_artifact_commit_rollback_sync_failure_is_publication_ambiguous(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            original_write = runner._write_canonical_file_noreplace_at
            original_fsync = runner.os.fsync
            root_stat = root.stat()
            root_identity = (root_stat.st_dev, root_stat.st_ino)
            commit_written = False

            def arm_after_commit(
                directory_fd: int,
                filename: str,
                payload: dict[str, object],
            ) -> None:
                nonlocal commit_written
                original_write(directory_fd, filename, payload)
                if filename == "commit.json":
                    commit_written = True

            def fail_publication_directory_sync(descriptor: int) -> None:
                if not commit_written:
                    original_fsync(descriptor)
                    return
                observed = runner.os.fstat(descriptor)
                observed_identity = (observed.st_dev, observed.st_ino)
                output_stat = output.stat()
                output_identity = (output_stat.st_dev, output_stat.st_ino)
                if commit_written and observed_identity in {
                    root_identity,
                    output_identity,
                }:
                    raise OSError("artifact commit rollback sync failure")
                original_fsync(descriptor)

            with (
                patch.object(runner, "_recheck_source_closure"),
                patch.object(
                    runner,
                    "_write_canonical_file_noreplace_at",
                    side_effect=arm_after_commit,
                ),
                patch.object(
                    runner.os,
                    "fsync",
                    side_effect=fail_publication_directory_sync,
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticPublicationStateAmbiguousError,
                    "durability and exact rollback",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                        repository_root=root,
                    )
            self.assertFalse((output / "commit.json").exists())
            self.assertEqual(
                len(
                    [
                        path
                        for path in output.iterdir()
                        if path.name.startswith(".commit.json.revoked-")
                    ]
                ),
                1,
            )
            attempt = root / (
                f".artifact.attempt-{authorization['deterministic_digest']}"
            )
            self.assertFalse((attempt / "invalid.json").exists())
            self.assertFalse((root / ".artifact.publish-lock").exists())

    def test_exact_commit_with_extra_file_is_revoked_before_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            original_write = runner._write_canonical_file_noreplace_at

            def add_extra_after_commit(
                directory_fd: int,
                filename: str,
                payload: dict[str, object],
            ) -> tuple[int, int]:
                identity = original_write(directory_fd, filename, payload)
                if filename == "commit.json":
                    (output / "extra.bin").write_bytes(b"closure drift")
                    raise OSError("synthetic post-commit closure drift")
                return identity

            with (
                patch.object(runner, "_recheck_source_closure"),
                patch.object(
                    runner,
                    "_write_canonical_file_noreplace_at",
                    side_effect=add_extra_after_commit,
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticInvalidRunError,
                    "synthetic post-commit closure drift",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                        repository_root=root,
                    )
            self.assertFalse((output / "commit.json").exists())
            self.assertTrue((output / "extra.bin").is_file())
            revoked = [
                path
                for path in output.iterdir()
                if path.name.startswith(".commit.json.revoked-")
            ]
            self.assertEqual(len(revoked), 1)
            self.assertEqual(json.loads(revoked[0].read_bytes())["status"], "COMMITTED")
            attempt = root / (
                f".artifact.attempt-{authorization['deterministic_digest']}"
            )
            self.assertTrue((attempt / "invalid.json").is_file())

    @unittest.skipUnless(hasattr(runner.os, "mkfifo"), "POSIX FIFO required")
    def test_post_started_fifo_substitution_is_invalid_without_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            original_rename = runner._rename_noreplace_at

            def replace_manifest_with_fifo(
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
                    (output / "manifest.json").unlink()
                    runner.os.mkfifo(output / "manifest.json")

            with (
                patch.object(runner, "_recheck_source_closure"),
                patch.object(
                    runner,
                    "_rename_noreplace_at",
                    side_effect=replace_manifest_with_fifo,
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticInvalidRunError,
                    "published artifact identity or bytes drifted",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                        repository_root=root,
                    )
            attempt = root / (
                f".artifact.attempt-{authorization['deterministic_digest']}"
            )
            self.assertTrue((attempt / "started.json").is_file())
            self.assertTrue((attempt / "invalid.json").is_file())
            self.assertFalse((attempt / "not_run.json").exists())
            self.assertTrue((output / "manifest.json").is_fifo())

    def test_post_started_final_closure_member_replacement_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            original_closure = runner._directory_has_exact_entries
            artifact_closure_calls = 0

            def replace_after_final_artifact_closure(
                directory_fd: int,
                expected_filenames: set[str],
            ) -> bool:
                nonlocal artifact_closure_calls
                exact = original_closure(directory_fd, expected_filenames)
                if expected_filenames == {"manifest.json", "records.jsonl"}:
                    artifact_closure_calls += 1
                    if artifact_closure_calls == 2:
                        manifest = output / "manifest.json"
                        replacement = output / ".manifest-replacement"
                        replacement.write_bytes(manifest.read_bytes())
                        replacement.replace(manifest)
                return exact

            with (
                patch.object(runner, "_recheck_source_closure"),
                patch.object(
                    runner,
                    "_directory_has_exact_entries",
                    side_effect=replace_after_final_artifact_closure,
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticInvalidRunError,
                    "published artifact identity or bytes drifted",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                        repository_root=root,
                    )
            self.assertEqual(artifact_closure_calls, 2)
            attempt = root / (
                f".artifact.attempt-{authorization['deterministic_digest']}"
            )
            self.assertTrue((attempt / "started.json").is_file())
            self.assertTrue((attempt / "invalid.json").is_file())
            self.assertFalse((attempt / "not_run.json").exists())

    def test_post_started_unbounded_directory_entries_exit_as_invalid(self) -> None:
        class _Entry:
            name = "foreign"

        class _UnboundedScandir:
            def __init__(self) -> None:
                self.closed = False
                self.next_calls = 0

            def __enter__(self) -> _UnboundedScandir:
                return self

            def __exit__(self, *args: object) -> None:
                self.closed = True

            def __iter__(self) -> _UnboundedScandir:
                return self

            def __next__(self) -> _Entry:
                self.next_calls += 1
                if self.next_calls > 4:
                    raise AssertionError("artifact closure exhausted entries")
                return _Entry()

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            original_rename = runner._rename_noreplace_at
            original_scandir = runner.os.scandir
            artifact_identity: tuple[int, int] | None = None
            synthetic_entries: list[_UnboundedScandir] = []

            def capture_artifact_identity(
                source_directory_fd: int,
                source_name: str,
                destination_directory_fd: int,
                destination_name: str,
            ) -> None:
                nonlocal artifact_identity
                original_rename(
                    source_directory_fd,
                    source_name,
                    destination_directory_fd,
                    destination_name,
                )
                if destination_name == output.name:
                    observed = output.stat()
                    artifact_identity = (observed.st_dev, observed.st_ino)

            def bounded_artifact_scandir(path: object = "."):
                if type(path) is int and artifact_identity is not None:
                    observed = runner.os.fstat(path)
                    if (observed.st_dev, observed.st_ino) == artifact_identity:
                        entries = _UnboundedScandir()
                        synthetic_entries.append(entries)
                        return entries
                return original_scandir(path)

            with (
                patch.object(runner, "_recheck_source_closure"),
                patch.object(
                    runner,
                    "_rename_noreplace_at",
                    side_effect=capture_artifact_identity,
                ),
                patch.object(
                    runner.os,
                    "scandir",
                    side_effect=bounded_artifact_scandir,
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticInvalidRunError,
                    "published artifact identity or bytes drifted",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                        repository_root=root,
                    )
            self.assertGreaterEqual(len(synthetic_entries), 1)
            self.assertTrue(
                all(entries.next_calls == 1 for entries in synthetic_entries)
            )
            self.assertTrue(all(entries.closed for entries in synthetic_entries))
            attempt = root / (
                f".artifact.attempt-{authorization['deterministic_digest']}"
            )
            self.assertTrue((attempt / "started.json").is_file())
            self.assertTrue((attempt / "invalid.json").is_file())
            self.assertFalse((attempt / "not_run.json").exists())

    def test_moved_committed_artifact_is_revoked_through_pinned_fd(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            stolen = root / "stolen-committed-artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            original_write = runner._write_canonical_file_noreplace_at
            original_fsync = runner.os.fsync
            root_identity = (root.stat().st_dev, root.stat().st_ino)
            commit_written = False
            swapped = False

            def arm_after_commit(
                directory_fd: int,
                filename: str,
                payload: dict[str, object],
            ) -> tuple[int, int]:
                nonlocal commit_written
                identity = original_write(directory_fd, filename, payload)
                if filename == "commit.json":
                    commit_written = True
                return identity

            def swap_after_commit_parent_barrier(descriptor: int) -> None:
                nonlocal swapped
                observed = runner.os.fstat(descriptor)
                identity = (observed.st_dev, observed.st_ino)
                original_fsync(descriptor)
                if commit_written and not swapped and identity == root_identity:
                    output.rename(stolen)
                    output.mkdir()
                    (output / "foreign.txt").write_text(
                        "foreign",
                        encoding="utf-8",
                    )
                    swapped = True

            with (
                patch.object(runner, "_recheck_source_closure"),
                patch.object(
                    runner,
                    "_write_canonical_file_noreplace_at",
                    side_effect=arm_after_commit,
                ),
                patch.object(
                    runner.os,
                    "fsync",
                    side_effect=swap_after_commit_parent_barrier,
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticInvalidRunError,
                    "public run artifact identity changed",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                        repository_root=root,
                    )
            self.assertTrue(swapped)
            self.assertEqual(
                (output / "foreign.txt").read_text(encoding="utf-8"),
                "foreign",
            )
            self.assertFalse((stolen / "commit.json").exists())
            revoked = [
                path
                for path in stolen.iterdir()
                if path.name.startswith(".commit.json.revoked-")
            ]
            self.assertEqual(len(revoked), 1)
            self.assertEqual(json.loads(revoked[0].read_bytes())["status"], "COMMITTED")
            attempt = root / (
                f".artifact.attempt-{authorization['deterministic_digest']}"
            )
            self.assertTrue((attempt / "invalid.json").is_file())

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
                runner.os.rename(
                    source_name,
                    stolen.name,
                    src_dir_fd=source_directory_fd,
                    dst_dir_fd=destination_directory_fd,
                )
                output.mkdir()
                (output / "foreign.txt").write_text("foreign", encoding="utf-8")
                raise OSError("synthetic final rename ambiguity")

            with (
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

    def test_started_failure_reason_is_frozen_before_terminal_reconciliation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            original_write = runner._write_attempt_receipt

            class StateMutatingError(OSError):
                def __init__(self) -> None:
                    super().__init__("synthetic STARTED write failure")
                    self.attempt: runner._Attempt | None = None
                    self.str_calls = 0

                def __str__(self) -> str:
                    self.str_calls += 1
                    if self.str_calls == 2:
                        if self.attempt is None:
                            raise AssertionError("attempt was not captured")
                        original_write(
                            self.attempt,
                            "started.json",
                            phase="STARTED",
                            status="PENDING",
                        )
                    return "synthetic STARTED write failure"

            injected_error = StateMutatingError()
            started_write_failed = False

            def fail_initial_started(
                attempt: runner._Attempt,
                filename: str,
                **kwargs: object,
            ) -> dict[str, object]:
                nonlocal started_write_failed
                if filename == "started.json" and not started_write_failed:
                    started_write_failed = True
                    injected_error.attempt = attempt
                    raise injected_error
                return original_write(attempt, filename, **kwargs)

            with (
                patch.object(runner, "_recheck_source_closure"),
                patch.object(
                    runner,
                    "_write_attempt_receipt",
                    side_effect=fail_initial_started,
                ),
                patch.object(
                    runner,
                    "_execute_cell",
                    side_effect=AssertionError("synthetic cell must not execute"),
                ) as execute_cell,
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticNotRunError,
                    "synthetic STARTED write failure",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                        repository_root=root,
                    )

            attempt = root / (
                f".artifact.attempt-{authorization['deterministic_digest']}"
            )
            self.assertTrue(started_write_failed)
            self.assertEqual(injected_error.str_calls, 1)
            self.assertTrue((attempt / "not_run.json").is_file())
            self.assertFalse((attempt / "started.json").exists())
            self.assertFalse((attempt / "invalid.json").exists())
            execute_cell.assert_not_called()
            with (
                patch.object(runner, "_recheck_source_closure"),
                patch.object(
                    runner,
                    "_execute_cell",
                    side_effect=AssertionError("spent attempt must not retry"),
                ) as retry_execute_cell,
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticNotRunError,
                    "durable attempt marker",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                        repository_root=root,
                    )
            retry_execute_cell.assert_not_called()

    def test_started_appearing_during_not_run_write_reconciles_to_invalid(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            original_write = runner._write_attempt_receipt
            started_write_failed = False
            late_started_written = False

            def inject_late_started(
                attempt: runner._Attempt,
                filename: str,
                **kwargs: object,
            ) -> dict[str, object]:
                nonlocal late_started_written, started_write_failed
                if filename == "started.json" and not started_write_failed:
                    started_write_failed = True
                    raise OSError("synthetic initial STARTED write failure")
                if filename == "not_run.json" and not late_started_written:
                    original_write(
                        attempt,
                        "started.json",
                        phase="STARTED",
                        status="PENDING",
                    )
                    late_started_written = True
                return original_write(attempt, filename, **kwargs)

            with (
                patch.object(runner, "_recheck_source_closure"),
                patch.object(
                    runner,
                    "_write_attempt_receipt",
                    side_effect=inject_late_started,
                ),
                patch.object(
                    runner,
                    "_execute_cell",
                    side_effect=AssertionError("synthetic cell must not execute"),
                ) as execute_cell,
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticInvalidRunError,
                    "synthetic initial STARTED write failure",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                        repository_root=root,
                    )

            attempt = root / (
                f".artifact.attempt-{authorization['deterministic_digest']}"
            )
            self.assertTrue(started_write_failed)
            self.assertTrue(late_started_written)
            self.assertTrue((attempt / "started.json").is_file())
            self.assertTrue((attempt / "not_run.json").is_file())
            self.assertTrue((attempt / "invalid.json").is_file())
            execute_cell.assert_not_called()
            with (
                patch.object(runner, "_recheck_source_closure"),
                patch.object(
                    runner,
                    "_execute_cell",
                    side_effect=AssertionError("spent attempt must not retry"),
                ) as retry_execute_cell,
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticNotRunError,
                    "durable attempt marker",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                        repository_root=root,
                    )
            retry_execute_cell.assert_not_called()

    def test_pre_outcome_not_run_reconciles_late_started_to_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            original_write = runner._write_attempt_receipt
            late_started_written = False

            def fail_pre_outcome_closure(*args: object, **kwargs: object) -> None:
                raise OSError("synthetic PRE_OUTCOME closure failure")

            def write_started_during_not_run(
                attempt: runner._Attempt,
                filename: str,
                **kwargs: object,
            ) -> dict[str, object]:
                nonlocal late_started_written
                receipt = original_write(attempt, filename, **kwargs)
                if filename == "not_run.json" and not late_started_written:
                    original_write(
                        attempt,
                        "started.json",
                        phase="STARTED",
                        status="PENDING",
                    )
                    late_started_written = True
                return receipt

            with (
                patch.object(
                    runner,
                    "_recheck_source_closure",
                    side_effect=fail_pre_outcome_closure,
                ),
                patch.object(
                    runner,
                    "_write_attempt_receipt",
                    side_effect=write_started_during_not_run,
                ),
                patch.object(
                    runner,
                    "_execute_cell",
                    side_effect=AssertionError("synthetic cell must not execute"),
                ) as execute_cell,
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticInvalidRunError,
                    "synthetic PRE_OUTCOME closure failure",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                        repository_root=root,
                    )

            attempt = root / (
                f".artifact.attempt-{authorization['deterministic_digest']}"
            )
            self.assertTrue(late_started_written)
            self.assertEqual(
                {path.name for path in attempt.iterdir()},
                {
                    "invalid.json",
                    "not_run.json",
                    "pre_outcome.json",
                    "started.json",
                },
            )
            execute_cell.assert_not_called()

    def test_attempt_rename_during_started_work_is_publication_ambiguous(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            attempt_name = f".artifact.attempt-{authorization['deterministic_digest']}"
            attempt = root / attempt_name
            displaced_attempt = root / "displaced-attempt"
            moved = False

            def move_attempt_then_fail(*args: object, **kwargs: object):
                nonlocal moved
                attempt.rename(displaced_attempt)
                moved = True
                raise OSError("synthetic attempt canonical-name loss")

            with (
                patch.object(runner, "_recheck_source_closure"),
                patch.object(
                    runner,
                    "_execute_cell",
                    side_effect=move_attempt_then_fail,
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticPublicationStateAmbiguousError,
                    "attempt reservation canonical identity",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                        repository_root=root,
                    )

            self.assertTrue(moved)
            self.assertFalse(attempt.exists())
            self.assertTrue((displaced_attempt / "started.json").is_file())
            self.assertFalse((displaced_attempt / "invalid.json").exists())
            self.assertFalse((displaced_attempt / "not_run.json").exists())
            self.assertFalse(output.exists())

    def test_parent_replacement_mid_pre_outcome_is_publication_ambiguous(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            container = Path(temporary)
            authorized_parent = container / "authorized"
            replacement_parent = container / "replacement"
            displaced_parent = container / "displaced"
            authorized_parent.mkdir()
            replacement_parent.mkdir()
            (replacement_parent / "foreign.txt").write_text(
                "preserve me",
                encoding="utf-8",
            )
            output = authorized_parent / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            parent_replaced = False

            def replace_parent_then_fail(*args: object, **kwargs: object) -> None:
                nonlocal parent_replaced
                authorized_parent.rename(displaced_parent)
                replacement_parent.rename(authorized_parent)
                parent_replaced = True
                raise OSError("synthetic PRE_OUTCOME parent replacement")

            with (
                patch.object(
                    runner,
                    "_recheck_source_closure",
                    side_effect=replace_parent_then_fail,
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticPublicationStateAmbiguousError,
                    "output parent identity drifted after STARTED",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                        repository_root=container,
                    )

            attempt = displaced_parent / (
                f".artifact.attempt-{authorization['deterministic_digest']}"
            )
            self.assertTrue(parent_replaced)
            self.assertEqual(
                (authorized_parent / "foreign.txt").read_text(encoding="utf-8"),
                "preserve me",
            )
            self.assertTrue((attempt / "pre_outcome.json").is_file())
            self.assertFalse((attempt / "not_run.json").exists())
            self.assertFalse((attempt / "invalid.json").exists())

    def test_terminal_receipt_replacement_prevents_typed_terminal_status(
        self,
    ) -> None:
        for terminal_filename in ("not_run.json", "invalid.json"):
            with (
                self.subTest(terminal_filename=terminal_filename),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                output = root / "artifact"
                preflight = _preflight(output)
                authorization = runner._authorization_payload(preflight)
                original_write = runner._write_attempt_receipt
                terminal_replaced = False

                def replace_terminal_receipt(
                    attempt: runner._Attempt,
                    filename: str,
                    **kwargs: object,
                ) -> dict[str, object]:
                    nonlocal terminal_replaced
                    receipt = original_write(attempt, filename, **kwargs)
                    if filename == terminal_filename and not terminal_replaced:
                        terminal_path = attempt.directory / filename
                        terminal_path.rename(attempt.directory / f".{filename}.stolen")
                        terminal_path.write_bytes(b"foreign terminal receipt\n")
                        terminal_replaced = True
                    return receipt

                with ExitStack() as stack:
                    stack.enter_context(
                        patch.object(
                            runner,
                            "_write_attempt_receipt",
                            side_effect=replace_terminal_receipt,
                        )
                    )
                    if terminal_filename == "not_run.json":
                        stack.enter_context(
                            patch.object(
                                runner,
                                "_recheck_source_closure",
                                side_effect=OSError(
                                    "synthetic PRE_OUTCOME terminal failure"
                                ),
                            )
                        )
                    else:
                        stack.enter_context(
                            patch.object(runner, "_recheck_source_closure")
                        )
                        stack.enter_context(
                            patch.object(
                                runner,
                                "_execute_cell",
                                side_effect=OSError(
                                    "synthetic STARTED terminal failure"
                                ),
                            )
                        )
                    with self.assertRaisesRegex(
                        runner.DiagnosticPublicationStateAmbiguousError,
                        "terminal attempt receipt drifted",
                    ):
                        runner._publish_run_artifact(
                            preflight,
                            authorization,
                            reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                            repository_root=root,
                        )

                attempt = root / (
                    f".artifact.attempt-{authorization['deterministic_digest']}"
                )
                self.assertTrue(terminal_replaced)
                self.assertEqual(
                    (attempt / terminal_filename).read_bytes(),
                    b"foreign terminal receipt\n",
                )
                self.assertTrue((attempt / f".{terminal_filename}.stolen").is_file())

    def test_parent_drift_after_typed_started_transition_is_ambiguous(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            container = Path(temporary)
            authorized_parent = container / "authorized"
            replacement_parent = container / "replacement"
            displaced_parent = container / "displaced"
            authorized_parent.mkdir()
            replacement_parent.mkdir()
            output = authorized_parent / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            original_transition = runner._transition_attempt_to_started

            def terminal_then_replace_parent(
                attempt: runner._Attempt,
            ) -> dict[str, object]:
                original_transition(attempt)
                runner._write_attempt_receipt(
                    attempt,
                    "invalid.json",
                    phase="STARTED",
                    status="INVALID",
                    reason="synthetic typed transition failure",
                )
                authorized_parent.rename(displaced_parent)
                replacement_parent.rename(authorized_parent)
                raise runner.DiagnosticInvalidRunError(
                    "synthetic typed transition failure"
                )

            with (
                patch.object(runner, "_recheck_source_closure"),
                patch.object(
                    runner,
                    "_transition_attempt_to_started",
                    side_effect=terminal_then_replace_parent,
                ),
                patch.object(
                    runner,
                    "_execute_cell",
                    side_effect=AssertionError("synthetic cell must not execute"),
                ) as execute_cell,
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticPublicationStateAmbiguousError,
                    "output parent identity drifted after STARTED",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                        repository_root=container,
                    )

            attempt = displaced_parent / (
                f".artifact.attempt-{authorization['deterministic_digest']}"
            )
            self.assertTrue((attempt / "started.json").is_file())
            self.assertTrue((attempt / "invalid.json").is_file())
            self.assertFalse((attempt / "not_run.json").exists())
            execute_cell.assert_not_called()

    def test_started_receipt_observation_failure_is_publication_ambiguous(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            original_write = runner._write_attempt_receipt
            original_read = runner._read_regular_file_at
            started_written = False

            def publish_started_then_interrupt(*args: object, **kwargs: object):
                nonlocal started_written
                payload = original_write(*args, **kwargs)
                if args[1] == "started.json":
                    started_written = True
                    raise OSError("synthetic STARTED publication interruption")
                return payload

            def fail_started_observation(
                directory_fd: int,
                filename: str,
            ) -> bytes:
                if started_written and filename == "started.json":
                    raise OSError("synthetic STARTED observation failure")
                return original_read(directory_fd, filename)

            with (
                patch.object(runner, "_recheck_source_closure"),
                patch.object(
                    runner,
                    "_write_attempt_receipt",
                    side_effect=publish_started_then_interrupt,
                ),
                patch.object(
                    runner,
                    "_read_regular_file_at",
                    side_effect=fail_started_observation,
                ),
                patch.object(
                    runner,
                    "_execute_cell",
                    side_effect=AssertionError("search must not start"),
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticPublicationStateAmbiguousError,
                    "attempt receipt observation failed",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                        repository_root=root,
                    )
            attempt = root / (
                f".artifact.attempt-{authorization['deterministic_digest']}"
            )
            self.assertEqual(
                {path.name for path in attempt.iterdir()},
                {"pre_outcome.json", "staging", "started.json"},
            )
            self.assertFalse((attempt / "invalid.json").exists())
            self.assertFalse((attempt / "not_run.json").exists())

    def test_terminal_receipts_require_directory_fsync_durability(self) -> None:
        for target in ("started.json", "not_run.json", "invalid.json"):
            with (
                self.subTest(target=target),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                output = root / "artifact"
                preflight = _preflight(output)
                authorization = runner._authorization_payload(preflight)
                original_rename = runner._rename_noreplace_at
                original_fsync = runner.os.fsync
                armed_identity: tuple[int, int] | None = None

                def arm_target_receipt(
                    source_directory_fd: int,
                    source_name: str,
                    destination_directory_fd: int,
                    destination_name: str,
                ) -> None:
                    nonlocal armed_identity
                    original_rename(
                        source_directory_fd,
                        source_name,
                        destination_directory_fd,
                        destination_name,
                    )
                    if destination_name == target:
                        observed = runner.os.fstat(destination_directory_fd)
                        armed_identity = (observed.st_dev, observed.st_ino)

                def fail_target_directory_barrier(descriptor: int) -> None:
                    observed = runner.os.fstat(descriptor)
                    if armed_identity == (observed.st_dev, observed.st_ino):
                        raise OSError(f"persistent {target} directory sync failure")
                    original_fsync(descriptor)

                recheck = (
                    runner.DiagnosticRunnerError("source raced")
                    if target == "not_run.json"
                    else None
                )
                execute = (
                    runner.DiagnosticRunnerError("fixture failure")
                    if target == "invalid.json"
                    else None
                )
                with (
                    patch.object(
                        runner,
                        "_recheck_source_closure",
                        side_effect=recheck,
                    ),
                    patch.object(
                        runner,
                        "_execute_cell",
                        side_effect=execute,
                    ),
                    patch.object(
                        runner,
                        "_rename_noreplace_at",
                        side_effect=arm_target_receipt,
                    ),
                    patch.object(
                        runner.os,
                        "fsync",
                        side_effect=fail_target_directory_barrier,
                    ),
                ):
                    with self.assertRaises(
                        runner.DiagnosticPublicationStateAmbiguousError
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
                self.assertFalse((attempt / target).exists())
                self.assertTrue(
                    any(
                        path.name.startswith(f".{target}.revoked-")
                        for path in attempt.iterdir()
                    )
                )
                if target == "started.json":
                    self.assertFalse((attempt / "not_run.json").exists())
                    self.assertFalse((attempt / "invalid.json").exists())
                elif target == "not_run.json":
                    self.assertFalse((attempt / "invalid.json").exists())
                else:
                    self.assertTrue((attempt / "started.json").is_file())

    def test_pre_outcome_closure_failure_is_not_run_and_never_executes_cell(
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
                    "_execute_cell",
                    side_effect=AssertionError("synthetic cell must not execute"),
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

    def test_pre_outcome_close_failures_do_not_mask_terminal_status(self) -> None:
        for terminal_receipt_fails in (False, True):
            with (
                self.subTest(terminal_receipt_fails=terminal_receipt_fails),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                output = root / "artifact"
                preflight = _preflight(output)
                authorization = runner._authorization_payload(preflight)
                original_close = runner.os.close
                original_fsync = runner.os.fsync
                original_open = runner.os.open
                original_write = runner._write_attempt_receipt
                close_armed = False
                pre_outcome_failed = False
                attempt_fd = -1
                staging_fd = -1
                failed_closes: list[int] = []

                def capture_staging_open(
                    path: object,
                    *args: object,
                    **kwargs: object,
                ) -> int:
                    nonlocal staging_fd
                    descriptor = original_open(path, *args, **kwargs)
                    if path == "staging":
                        staging_fd = descriptor
                    return descriptor

                def fail_after_staging_open(descriptor: int) -> None:
                    nonlocal pre_outcome_failed
                    if not pre_outcome_failed:
                        try:
                            entries = set(runner.os.listdir(descriptor))
                        except OSError:
                            entries = set()
                        if "staging" in entries:
                            pre_outcome_failed = True
                            raise runner.DiagnosticRunnerError(
                                "primary PRE_OUTCOME failure"
                            )
                    original_fsync(descriptor)

                def terminate_attempt(*args: object, **kwargs: object):
                    nonlocal attempt_fd, close_armed
                    attempt = args[0]
                    filename = args[1]
                    assert isinstance(attempt, runner._Attempt)
                    assert isinstance(filename, str)
                    attempt_fd = attempt.directory_fd
                    if filename == "not_run.json" and terminal_receipt_fails:
                        close_armed = True
                        raise OSError("primary terminal receipt failure")
                    payload = original_write(*args, **kwargs)
                    if filename == "not_run.json":
                        close_armed = True
                    return payload

                def fail_close_after_success(descriptor: int) -> None:
                    original_close(descriptor)
                    if close_armed:
                        failed_closes.append(descriptor)
                        raise OSError("synthetic cleanup close failure")

                expected_error = (
                    runner.DiagnosticPublicationStateAmbiguousError
                    if terminal_receipt_fails
                    else runner.DiagnosticNotRunError
                )
                expected_message = (
                    "NOT_RUN receipt durability is unproven"
                    if terminal_receipt_fails
                    else "primary PRE_OUTCOME failure"
                )
                with (
                    patch.object(runner, "_recheck_source_closure"),
                    patch.object(
                        runner.os,
                        "open",
                        side_effect=capture_staging_open,
                    ),
                    patch.object(
                        runner.os,
                        "fsync",
                        side_effect=fail_after_staging_open,
                    ),
                    patch.object(
                        runner,
                        "_write_attempt_receipt",
                        side_effect=terminate_attempt,
                    ),
                    patch.object(
                        runner.os,
                        "close",
                        side_effect=fail_close_after_success,
                    ),
                ):
                    with self.assertRaisesRegex(expected_error, expected_message):
                        runner._publish_run_artifact(
                            preflight,
                            authorization,
                            reviewed_authorization_revision=(_AUTHORIZATION_REVISION),
                            repository_root=root,
                        )
                self.assertGreaterEqual(staging_fd, 0)
                self.assertGreaterEqual(attempt_fd, 0)
                self.assertIn(staging_fd, failed_closes)
                self.assertIn(attempt_fd, failed_closes)

    def test_started_transition_close_failures_do_not_mask_typed_status(
        self,
    ) -> None:
        for expected_error in (
            runner.DiagnosticPublicationStateAmbiguousError,
            runner.DiagnosticInvalidRunError,
            runner.DiagnosticNotRunError,
        ):
            with (
                self.subTest(expected_error=expected_error.__name__),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                output = root / "artifact"
                preflight = _preflight(output)
                authorization = runner._authorization_payload(preflight)
                original_close = runner.os.close
                original_open = runner.os.open
                close_armed = False
                attempt_fd = -1
                staging_fd = -1
                failed_closes: list[int] = []

                def capture_staging_open(
                    path: object,
                    *args: object,
                    **kwargs: object,
                ) -> int:
                    nonlocal staging_fd
                    descriptor = original_open(path, *args, **kwargs)
                    if path == "staging":
                        staging_fd = descriptor
                    return descriptor

                def fail_transition(attempt: runner._Attempt) -> dict[str, object]:
                    nonlocal attempt_fd, close_armed
                    attempt_fd = attempt.directory_fd
                    if expected_error is runner.DiagnosticInvalidRunError:
                        runner._write_attempt_receipt(
                            attempt,
                            "invalid.json",
                            phase="STARTED",
                            status="INVALID",
                            reason="primary STARTED transition status",
                        )
                    elif expected_error is runner.DiagnosticNotRunError:
                        runner._write_attempt_receipt(
                            attempt,
                            "not_run.json",
                            phase="PRE_OUTCOME",
                            status="NOT_RUN",
                            reason="primary STARTED transition status",
                        )
                    close_armed = True
                    raise expected_error("primary STARTED transition status")

                def fail_close_after_success(descriptor: int) -> None:
                    original_close(descriptor)
                    if close_armed:
                        failed_closes.append(descriptor)
                        raise OSError("synthetic cleanup close failure")

                with (
                    patch.object(runner, "_recheck_source_closure"),
                    patch.object(
                        runner.os,
                        "open",
                        side_effect=capture_staging_open,
                    ),
                    patch.object(
                        runner,
                        "_transition_attempt_to_started",
                        side_effect=fail_transition,
                    ),
                    patch.object(
                        runner.os,
                        "close",
                        side_effect=fail_close_after_success,
                    ),
                ):
                    with self.assertRaisesRegex(
                        expected_error,
                        "primary STARTED transition status",
                    ):
                        runner._publish_run_artifact(
                            preflight,
                            authorization,
                            reviewed_authorization_revision=(_AUTHORIZATION_REVISION),
                            repository_root=root,
                        )
                self.assertGreaterEqual(staging_fd, 0)
                self.assertGreaterEqual(attempt_fd, 0)
                self.assertIn(staging_fd, failed_closes)
                self.assertIn(attempt_fd, failed_closes)

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

    def test_post_attempt_rename_validation_failure_is_publication_ambiguous(
        self,
    ) -> None:
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
                    "_execute_cell",
                    side_effect=AssertionError("synthetic cell must not execute"),
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticPublicationStateAmbiguousError,
                    "pinned but its exact content",
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
                {"pre_outcome.json"},
            )
            self.assertFalse(output.exists())

    def test_foreign_attempt_marker_needs_parent_durability_before_not_run(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            attempt_name = f".artifact.attempt-{authorization['deterministic_digest']}"
            foreign_attempt = root / attempt_name
            foreign_attempt.mkdir()
            (foreign_attempt / "foreign.txt").write_text(
                "foreign",
                encoding="utf-8",
            )
            root_identity = (root.stat().st_dev, root.stat().st_ino)
            original_fsync = runner.os.fsync

            def fail_parent_barrier(descriptor: int) -> None:
                observed = runner.os.fstat(descriptor)
                if (observed.st_dev, observed.st_ino) == root_identity:
                    raise OSError("attempt absence barrier unavailable")
                original_fsync(descriptor)

            with (
                patch.object(runner, "_recheck_source_closure"),
                patch.object(
                    runner.os,
                    "fsync",
                    side_effect=fail_parent_barrier,
                ),
                patch.object(
                    runner,
                    "_execute_cell",
                    side_effect=AssertionError("search must not start"),
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticPublicationStateAmbiguousError,
                    "absence durability",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                        repository_root=root,
                    )
            self.assertEqual(
                (foreign_attempt / "foreign.txt").read_text(encoding="utf-8"),
                "foreign",
            )
            self.assertFalse(output.exists())

    def test_attempt_parent_sync_transient_failure_retries_and_commits(self) -> None:
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
                patch.object(runner, "_recheck_source_closure"),
                patch.object(runner.os, "fsync", side_effect=fail_after_attempt_rename),
            ):
                manifest = runner._publish_run_artifact(
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
                {"pre_outcome.json", "ready_to_commit.json", "started.json"},
            )
            self.assertEqual(manifest["attempt_phase"], "READY_TO_COMMIT")
            self.assertTrue((output / "commit.json").is_file())
            self.assertFalse((root / ".artifact.publish-lock").exists())

    def test_post_barrier_attempt_swap_is_publication_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            attempt_name = f".artifact.attempt-{authorization['deterministic_digest']}"
            attempt = root / attempt_name
            stolen = root / "stolen-exact-attempt"
            foreign = root / "foreign-attempt"
            foreign.mkdir()
            (foreign / "foreign.txt").write_text("foreign", encoding="utf-8")
            root_identity = (root.stat().st_dev, root.stat().st_ino)
            original_fsync = runner.os.fsync
            swapped = False

            def swap_at_parent_barrier(descriptor: int) -> None:
                nonlocal swapped
                observed = runner.os.fstat(descriptor)
                if (
                    not swapped
                    and (observed.st_dev, observed.st_ino) == root_identity
                    and attempt.is_dir()
                ):
                    swapped = True
                    attempt.rename(stolen)
                    foreign.rename(attempt)
                original_fsync(descriptor)

            with (
                patch.object(runner, "_recheck_source_closure"),
                patch.object(
                    runner.os,
                    "fsync",
                    side_effect=swap_at_parent_barrier,
                ),
                patch.object(
                    runner,
                    "_execute_cell",
                    side_effect=AssertionError("search must not start"),
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticPublicationStateAmbiguousError,
                    "durably lost after publication",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                        repository_root=root,
                    )
            self.assertTrue(swapped)
            self.assertEqual(
                (attempt / "foreign.txt").read_text(encoding="utf-8"),
                "foreign",
            )
            self.assertTrue((stolen / "pre_outcome.json").is_file())
            self.assertFalse(output.exists())

    def test_persistent_attempt_parent_sync_failure_durably_revokes_reservation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            original_fsync = runner.os.fsync
            call_count = 0

            def fail_initial_and_retry_parent_sync(descriptor: int) -> None:
                nonlocal call_count
                call_count += 1
                if call_count in {4, 5}:
                    raise OSError("persistent attempt parent sync failure")
                original_fsync(descriptor)

            with (
                patch.object(runner, "_recheck_source_closure"),
                patch.object(
                    runner.os,
                    "fsync",
                    side_effect=fail_initial_and_retry_parent_sync,
                ),
                patch.object(
                    runner,
                    "_execute_cell",
                    side_effect=AssertionError("synthetic cell must not execute"),
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticNotRunError,
                    "durably revoked",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                        repository_root=root,
                    )
            attempt = root / (
                f".artifact.attempt-{authorization['deterministic_digest']}"
            )
            self.assertFalse(attempt.exists())
            self.assertFalse(output.exists())
            self.assertFalse((root / ".artifact.publish-lock").exists())

    def test_attempt_reservation_rollback_sync_failure_is_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            original_fsync = runner.os.fsync
            call_count = 0

            def fail_publication_and_child_rollback_sync(descriptor: int) -> None:
                nonlocal call_count
                call_count += 1
                if call_count in {4, 5, 6}:
                    raise OSError("attempt rollback sync failure")
                original_fsync(descriptor)

            with (
                patch.object(runner, "_recheck_source_closure"),
                patch.object(
                    runner.os,
                    "fsync",
                    side_effect=fail_publication_and_child_rollback_sync,
                ),
                patch.object(
                    runner,
                    "_execute_cell",
                    side_effect=AssertionError("synthetic cell must not execute"),
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticPublicationStateAmbiguousError,
                    "exact rollback failed",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                        repository_root=root,
                    )
            attempt = root / (
                f".artifact.attempt-{authorization['deterministic_digest']}"
            )
            self.assertFalse(attempt.exists())
            revoked_attempts = [
                path
                for path in root.iterdir()
                if path.name.startswith(f".{attempt.name}.revoked-")
            ]
            self.assertEqual(len(revoked_attempts), 1)
            self.assertTrue((revoked_attempts[0] / "pre_outcome.json").is_file())
            self.assertFalse((root / ".artifact.publish-lock").exists())

    def test_attempt_reservation_rollback_observation_failure_is_ambiguous(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            original_fsync = runner.os.fsync
            original_closure = runner._directory_has_exact_entries
            fsync_count = 0
            closure_count = 0

            def fail_parent_sync(descriptor: int) -> None:
                nonlocal fsync_count
                fsync_count += 1
                if fsync_count in {4, 5}:
                    raise OSError("persistent attempt parent sync failure")
                original_fsync(descriptor)

            def fail_rollback_observation(
                descriptor: int,
                expected: set[str],
            ) -> bool:
                nonlocal closure_count
                closure_count += 1
                if closure_count == 2:
                    raise OSError("attempt rollback observation failure")
                return original_closure(descriptor, expected)

            with (
                patch.object(runner, "_recheck_source_closure"),
                patch.object(runner.os, "fsync", side_effect=fail_parent_sync),
                patch.object(
                    runner,
                    "_directory_has_exact_entries",
                    side_effect=fail_rollback_observation,
                ),
                patch.object(
                    runner,
                    "_execute_cell",
                    side_effect=AssertionError("synthetic cell must not execute"),
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticPublicationStateAmbiguousError,
                    "content observation failed",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                        repository_root=root,
                    )
            attempt = root / (
                f".artifact.attempt-{authorization['deterministic_digest']}"
            )
            self.assertTrue((attempt / "pre_outcome.json").is_file())
            self.assertFalse((root / ".artifact.publish-lock").exists())

    def test_attempt_scratch_cleanup_interrupt_preserves_primary_ambiguity(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            primary = runner.DiagnosticPublicationStateAmbiguousError(
                "primary attempt reservation ambiguity"
            )
            original_stat = runner.os.stat

            def interrupt_private_scratch(
                path: object,
                *args: object,
                **kwargs: object,
            ):
                if isinstance(path, str) and ".attempt-tmp-" in path:
                    raise KeyboardInterrupt("synthetic scratch cleanup interruption")
                return original_stat(path, *args, **kwargs)

            with (
                patch.object(runner, "_recheck_source_closure"),
                patch.object(
                    runner,
                    "_published_attempt_reservation_matches",
                    side_effect=primary,
                ),
                patch.object(
                    runner.os,
                    "stat",
                    side_effect=interrupt_private_scratch,
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticPublicationStateAmbiguousError,
                    "primary attempt reservation ambiguity",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                        repository_root=root,
                    )
            self.assertFalse(output.exists())

    def test_missing_output_parent_is_not_created_or_started(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            missing_ancestor = root / "missing"
            output = missing_ancestor / "runs" / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            with (
                patch.object(
                    runner,
                    "_publish_run_artifact_locked",
                    side_effect=AssertionError("attempt must not start"),
                ) as publish_locked,
                patch.object(
                    runner,
                    "_execute_cell",
                    side_effect=AssertionError("diagnostic task must not run"),
                ) as execute_cell,
                patch.object(
                    runner,
                    "run_countdown_track_a_search",
                    side_effect=AssertionError("diagnostic search must not run"),
                ) as search,
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticNotRunError,
                    "run output parent must be a stable directory",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                        repository_root=root,
                    )
            self.assertFalse(missing_ancestor.exists())
            self.assertFalse(output.exists())
            self.assertEqual(list(root.iterdir()), [])
            publish_locked.assert_not_called()
            execute_cell.assert_not_called()
            search.assert_not_called()

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

    def test_lock_retirement_precedes_all_terminal_attempt_proofs(self) -> None:
        for terminal_status in ("COMMITTED", "NOT_RUN", "INVALID"):
            with (
                self.subTest(terminal_status=terminal_status),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                output = root / "artifact"
                preflight = _preflight(output)
                authorization = runner._authorization_payload(preflight)
                attempt_name = (
                    f".artifact.attempt-{authorization['deterministic_digest']}"
                )
                displaced_name = f"{attempt_name}.displaced"
                original_quarantine = runner._quarantine_exact_directory_at
                original_execute = runner._execute_cell
                displaced = False

                def recheck_source(*_args: object, **_kwargs: object) -> None:
                    if terminal_status == "NOT_RUN":
                        raise OSError("synthetic PRE_OUTCOME failure")

                def execute_cell(*args: object, **kwargs: object):
                    if terminal_status == "INVALID":
                        raise OSError("synthetic STARTED failure")
                    return original_execute(*args, **kwargs)

                def retire_then_displace(
                    *args: object,
                    **kwargs: object,
                ) -> str | None:
                    nonlocal displaced
                    tombstone = original_quarantine(*args, **kwargs)
                    if kwargs.get("label") == "publication lock":
                        parent_fd = args[0]
                        runner.os.rename(
                            attempt_name,
                            displaced_name,
                            src_dir_fd=parent_fd,
                            dst_dir_fd=parent_fd,
                        )
                        runner.os.fsync(parent_fd)
                        displaced = True
                    return tombstone

                with (
                    patch.object(
                        runner,
                        "_recheck_source_closure",
                        side_effect=recheck_source,
                    ),
                    patch.object(
                        runner,
                        "_execute_cell",
                        side_effect=execute_cell,
                    ),
                    patch.object(
                        runner,
                        "_quarantine_exact_directory_at",
                        side_effect=retire_then_displace,
                    ),
                    self.assertRaisesRegex(
                        runner.DiagnosticPublicationStateAmbiguousError,
                        "attempt reservation canonical identity",
                    ),
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                        repository_root=root,
                        _terminal_result=True,
                    )
                self.assertTrue(displaced)
                self.assertFalse((root / attempt_name).exists())
                self.assertTrue((root / displaced_name).is_dir())

    def test_not_run_rejects_started_injected_during_lock_retirement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            original_quarantine = runner._quarantine_exact_directory_at
            original_attempt_write = runner._write_attempt_receipt
            captured_attempt: runner._Attempt | None = None
            started_injected = False

            def capture_not_run(
                attempt: runner._Attempt,
                filename: str,
                **kwargs: object,
            ) -> dict[str, object]:
                nonlocal captured_attempt
                receipt = original_attempt_write(attempt, filename, **kwargs)
                if filename == "not_run.json":
                    captured_attempt = attempt
                return receipt

            def retire_then_start(
                *args: object,
                **kwargs: object,
            ) -> str | None:
                nonlocal started_injected
                tombstone = original_quarantine(*args, **kwargs)
                if kwargs.get("label") == "publication lock":
                    if captured_attempt is None:
                        raise AssertionError("NOT_RUN attempt was not captured")
                    original_attempt_write(
                        captured_attempt,
                        "started.json",
                        phase="STARTED",
                        status="PENDING",
                    )
                    runner.os.fsync(captured_attempt.directory_fd)
                    started_injected = True
                return tombstone

            with (
                patch.object(
                    runner,
                    "_recheck_source_closure",
                    side_effect=OSError("synthetic PRE_OUTCOME failure"),
                ),
                patch.object(
                    runner,
                    "_write_attempt_receipt",
                    side_effect=capture_not_run,
                ),
                patch.object(
                    runner,
                    "_quarantine_exact_directory_at",
                    side_effect=retire_then_start,
                ),
                self.assertRaisesRegex(
                    runner.DiagnosticPublicationStateAmbiguousError,
                    "forbidden terminal attempt entry exists: started.json",
                ),
            ):
                runner._publish_run_artifact(
                    preflight,
                    authorization,
                    reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                    repository_root=root,
                )
            self.assertTrue(started_injected)

    def test_commit_rejects_invalid_injected_during_lock_retirement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            original_quarantine = runner._quarantine_exact_directory_at
            original_attempt_write = runner._write_attempt_receipt
            captured_attempt: runner._Attempt | None = None
            invalid_injected = False

            def capture_ready(
                attempt: runner._Attempt,
                filename: str,
                **kwargs: object,
            ) -> dict[str, object]:
                nonlocal captured_attempt
                receipt = original_attempt_write(attempt, filename, **kwargs)
                if filename == "ready_to_commit.json":
                    captured_attempt = attempt
                return receipt

            def retire_then_invalidate(
                *args: object,
                **kwargs: object,
            ) -> str | None:
                nonlocal invalid_injected
                tombstone = original_quarantine(*args, **kwargs)
                if kwargs.get("label") == "publication lock":
                    if captured_attempt is None:
                        raise AssertionError("COMMITTED attempt was not captured")
                    original_attempt_write(
                        captured_attempt,
                        "invalid.json",
                        phase="STARTED",
                        status="INVALID",
                        reason="synthetic post-lock terminal conflict",
                    )
                    runner.os.fsync(captured_attempt.directory_fd)
                    invalid_injected = True
                return tombstone

            with (
                patch.object(runner, "_recheck_source_closure"),
                patch.object(
                    runner,
                    "_write_attempt_receipt",
                    side_effect=capture_ready,
                ),
                patch.object(
                    runner,
                    "_quarantine_exact_directory_at",
                    side_effect=retire_then_invalidate,
                ),
                self.assertRaisesRegex(
                    runner.DiagnosticPublicationStateAmbiguousError,
                    "committed artifact or attempt conflicted after lock retirement",
                ),
            ):
                runner._publish_run_artifact(
                    preflight,
                    authorization,
                    reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                    repository_root=root,
                    _terminal_result=True,
                )
            self.assertTrue(invalid_injected)
            self.assertTrue((output / "commit.json").is_file())

    def test_terminal_namespace_signature_spans_final_name_proof(self) -> None:
        for terminal_status in ("COMMITTED", "NOT_RUN"):
            with (
                self.subTest(terminal_status=terminal_status),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                output = root / "artifact"
                preflight = _preflight(output)
                authorization = runner._authorization_payload(preflight)
                original_quarantine = runner._quarantine_exact_directory_at
                original_assert_identity = runner._assert_attempt_entry_identity
                original_attempt_write = runner._write_attempt_receipt
                lock_retired = False
                identity_calls_after_retirement = 0
                receipt_injected = False

                def observe_retirement(
                    *args: object,
                    **kwargs: object,
                ) -> str | None:
                    nonlocal lock_retired
                    tombstone = original_quarantine(*args, **kwargs)
                    if kwargs.get("label") == "publication lock":
                        lock_retired = True
                    return tombstone

                def inject_during_final_identity(
                    attempt: runner._Attempt,
                    parent_fd: int,
                ) -> None:
                    nonlocal identity_calls_after_retirement, receipt_injected
                    if lock_retired:
                        identity_calls_after_retirement += 1
                        if (
                            identity_calls_after_retirement == 2
                            and not receipt_injected
                        ):
                            if terminal_status == "COMMITTED":
                                original_attempt_write(
                                    attempt,
                                    "invalid.json",
                                    phase="STARTED",
                                    status="INVALID",
                                    reason="synthetic final-name conflict",
                                )
                            else:
                                original_attempt_write(
                                    attempt,
                                    "started.json",
                                    phase="STARTED",
                                    status="PENDING",
                                )
                            runner.os.fsync(attempt.directory_fd)
                            receipt_injected = True
                    original_assert_identity(attempt, parent_fd)

                recheck_effect = (
                    OSError("synthetic PRE_OUTCOME failure")
                    if terminal_status == "NOT_RUN"
                    else None
                )
                with (
                    patch.object(
                        runner,
                        "_recheck_source_closure",
                        side_effect=recheck_effect,
                    ),
                    patch.object(
                        runner,
                        "_quarantine_exact_directory_at",
                        side_effect=observe_retirement,
                    ),
                    patch.object(
                        runner,
                        "_assert_attempt_entry_identity",
                        side_effect=inject_during_final_identity,
                    ),
                    self.assertRaisesRegex(
                        runner.DiagnosticPublicationStateAmbiguousError,
                        (
                            "terminal COMMITTED authority is ambiguous"
                            "|forbidden terminal attempt entry exists: started.json"
                        ),
                    ),
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                        repository_root=root,
                        _terminal_result=True,
                    )
                self.assertTrue(receipt_injected)

    def test_lock_retirement_ambiguity_supersedes_terminal_success(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)

            with (
                patch.object(runner, "_recheck_source_closure"),
                patch.object(
                    runner,
                    "_quarantine_exact_directory_at",
                    side_effect=runner.DiagnosticPublicationStateAmbiguousError(
                        "foreign publication lock could not be restored"
                    ),
                ),
                self.assertRaisesRegex(
                    runner.DiagnosticPublicationStateAmbiguousError,
                    "foreign-entry restoration are ambiguous",
                ),
            ):
                runner._publish_run_artifact(
                    preflight,
                    authorization,
                    reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                    repository_root=root,
                    _terminal_result=True,
                )
            self.assertTrue((root / ".artifact.publish-lock").is_dir())

    def test_attempt_name_is_reobserved_after_final_canonical_open(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            attempt_name = f".artifact.attempt-{authorization['deterministic_digest']}"
            displaced_name = f"{attempt_name}.post-open-displaced"
            original_quarantine = runner._quarantine_exact_directory_at
            original_open = runner.os.open
            lock_retired = False
            displaced = False

            def observe_retirement(
                *args: object,
                **kwargs: object,
            ) -> str | None:
                nonlocal lock_retired
                tombstone = original_quarantine(*args, **kwargs)
                if kwargs.get("label") == "publication lock":
                    lock_retired = True
                return tombstone

            def open_then_displace(
                path: object,
                flags: int,
                mode: int = 0o777,
                *,
                dir_fd: int | None = None,
            ) -> int:
                nonlocal displaced
                descriptor = original_open(path, flags, mode, dir_fd=dir_fd)
                if (
                    lock_retired
                    and not displaced
                    and path == attempt_name
                    and dir_fd is not None
                ):
                    runner.os.rename(
                        attempt_name,
                        displaced_name,
                        src_dir_fd=dir_fd,
                        dst_dir_fd=dir_fd,
                    )
                    runner.os.fsync(dir_fd)
                    displaced = True
                return descriptor

            with (
                patch.object(runner, "_recheck_source_closure"),
                patch.object(
                    runner,
                    "_quarantine_exact_directory_at",
                    side_effect=observe_retirement,
                ),
                patch.object(runner.os, "open", side_effect=open_then_displace),
                self.assertRaisesRegex(
                    runner.DiagnosticPublicationStateAmbiguousError,
                    "attempt reservation canonical identity is unavailable",
                ),
            ):
                runner._publish_run_artifact(
                    preflight,
                    authorization,
                    reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                    repository_root=root,
                    _terminal_result=True,
                )
            self.assertTrue(displaced)
            self.assertFalse((root / attempt_name).exists())
            self.assertTrue((root / displaced_name).is_dir())

    def test_lock_cleanup_restores_a_foreign_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            lock = root / ".artifact.publish-lock"
            stolen_lock = root / "stolen-lock"
            foreign_lock = root / "foreign-lock"
            foreign_lock.mkdir()
            (foreign_lock / "foreign.txt").write_text("foreign", encoding="utf-8")

            def substitute_lock(*args: object, **kwargs: object):
                lock.rename(stolen_lock)
                foreign_lock.rename(lock)
                return (
                    {"artifact_id": "artifact", "status": "fixture"},
                    {"deterministic_digest": "0" * 64},
                )

            with patch.object(
                runner,
                "_publish_run_artifact_locked",
                side_effect=substitute_lock,
            ):
                observed = runner._publish_run_artifact(
                    preflight,
                    authorization,
                    reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                    repository_root=root,
                )
            self.assertEqual(observed["status"], "fixture")
            self.assertEqual(
                (lock / "foreign.txt").read_text(encoding="utf-8"),
                "foreign",
            )
            self.assertTrue(stolen_lock.is_dir())

    def test_lock_cleanup_failure_does_not_mask_primary_ambiguity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "artifact"
            preflight = _preflight(output)
            authorization = runner._authorization_payload(preflight)
            with (
                patch.object(
                    runner,
                    "_publish_run_artifact_locked",
                    side_effect=(
                        runner.DiagnosticPublicationStateAmbiguousError(
                            "primary publication ambiguity"
                        )
                    ),
                ),
                patch.object(
                    runner,
                    "_quarantine_exact_directory_at",
                    side_effect=OSError("secondary lock cleanup failure"),
                ),
            ):
                with self.assertRaisesRegex(
                    runner.DiagnosticPublicationStateAmbiguousError,
                    "primary publication ambiguity",
                ):
                    runner._publish_run_artifact(
                        preflight,
                        authorization,
                        reviewed_authorization_revision=_AUTHORIZATION_REVISION,
                        repository_root=root,
                    )

    def test_cli_keeps_plan_self_test_and_run_authority_separate(self) -> None:
        def assert_canonical_refusal(
            arguments: list[str],
            reason_fragment: str,
        ) -> None:
            with (
                patch("builtins.print") as printed,
                patch("sys.stderr") as stderr,
            ):
                with self.assertRaises(SystemExit) as stopped:
                    runner.main(arguments)
            stderr.write.assert_not_called()
            self.assertEqual(stopped.exception.code, 2)
            raw = printed.call_args.args[0]
            refusal = json.loads(raw)
            self.assertEqual(raw, runner.canonical_json(refusal))
            self.assertEqual(refusal["status"], "NOT_RUN")
            self.assertIn(reason_fragment, refusal["reason"])
            self.assertIn("no execution-evidence authority", refusal["claim_boundary"])
            self.assertIn("no retry authority", refusal["claim_boundary"])

        assert_canonical_refusal([], "one of the arguments")
        assert_canonical_refusal(
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
            ],
            "--run requires",
        )
        assert_canonical_refusal(
            ["--self-test", "--output", "artifact"],
            "--self-test accepts no execution",
        )
        assert_canonical_refusal(
            ["--self-test", "--repository-root", "."],
            "--self-test accepts no execution",
        )
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
            assert_canonical_refusal(
                [
                    "--plan",
                    "bundle",
                    "--output",
                    "artifact",
                    "--authorization-out",
                    "authorization.json",
                ],
                "--plan requires explicit --repository-root",
            )
        with patch.object(
            runner,
            "run_countdown_thompson_diagnostic",
            side_effect=AssertionError("execution must require an explicit root"),
        ):
            assert_canonical_refusal(
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
                ],
                "--run requires explicit --repository-root",
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
        self.assertIs(type(planned.call_args.args[1]), str)
        self.assertEqual(planned.call_args.args[1], "artifact")
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
        self.assertIs(type(executed.call_args.args[1]), str)
        self.assertEqual(executed.call_args.args[1], "artifact")

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

        ambiguity_cases = (
            (
                "write_countdown_thompson_diagnostic_execution_plan",
                [
                    "--plan",
                    "bundle",
                    "--output",
                    "artifact",
                    "--authorization-out",
                    "authorization.json",
                    "--repository-root",
                    ".",
                ],
            ),
            (
                "run_countdown_thompson_diagnostic",
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
                ],
            ),
        )
        for target, arguments in ambiguity_cases:
            with self.subTest(ambiguous_target=target):
                with (
                    patch.object(
                        runner,
                        target,
                        side_effect=(
                            runner.DiagnosticPublicationStateAmbiguousError(
                                "synthetic publication ambiguity"
                            )
                        ),
                    ),
                    patch("builtins.print") as printed,
                ):
                    with self.assertRaises(SystemExit) as stopped:
                        runner.main(arguments)
                self.assertEqual(stopped.exception.code, 3)
                raw = printed.call_args.args[0]
                ambiguous = json.loads(raw)
                self.assertEqual(raw, runner.canonical_json(ambiguous))
                self.assertEqual(
                    ambiguous["status"],
                    "PUBLICATION_STATE_AMBIGUOUS",
                )
                self.assertIn("no file is authorized", ambiguous["claim_boundary"])
                self.assertIn("no retry authority", ambiguous["claim_boundary"])

    def test_build_attestation_binds_all_runner_sources_and_import_origins(
        self,
    ) -> None:
        repository = Path(runner.__file__).resolve().parents[3]
        expected_runner_sources = (
            "src/qmc_bmgs/experiments/__init__.py",
            "src/qmc_bmgs/experiments/countdown_track_a_canary_manifest.py",
            "src/qmc_bmgs/experiments/countdown_thompson_diagnostic_manifest.py",
            "src/qmc_bmgs/experiments/countdown_thompson_regular_file_publication_v2.py",
            "src/qmc_bmgs/experiments/countdown_thompson_diagnostic_runner.py",
            "src/qmc_bmgs/experiments/countdown_thompson_diagnostic_analysis.py",
        )
        self.assertEqual(runner._RUNNER_SOURCE_PATHS, expected_runner_sources)
        self.assertEqual(
            {
                "qmc_bmgs.experiments": expected_runner_sources[0],
                runner.canary_manifest.__name__: expected_runner_sources[1],
                runner.manifest.__name__: expected_runner_sources[2],
                runner.regular_file_publication.__name__: expected_runner_sources[3],
                runner.__name__: expected_runner_sources[4],
                runner.analysis.__name__: expected_runner_sources[5],
            },
            {
                module: runner._PROTECTED_MODULE_PATHS[module]
                for module in (
                    "qmc_bmgs.experiments",
                    runner.canary_manifest.__name__,
                    runner.manifest.__name__,
                    runner.regular_file_publication.__name__,
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
                        Path(temporary).resolve() / "artifact",
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
