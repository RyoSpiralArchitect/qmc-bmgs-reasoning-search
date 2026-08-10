from __future__ import annotations

import math
import os
import tempfile
import time
import unittest
from copy import deepcopy
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from qmc_bmgs.benchmarks.countdown import CountdownTask
from qmc_bmgs.experiments import countdown_thompson_diagnostic_analysis as analysis
from qmc_bmgs.experiments import countdown_thompson_diagnostic_runner as runner
from qmc_bmgs.experiments.countdown_thompson_diagnostic_manifest import (
    BUNDLE_ID,
    DiagnosticCell,
)
from qmc_bmgs.substrate.budget import TrackAWorkBudget
from qmc_bmgs.substrate.countdown_search import TrackABudgetProfile, TrackAMethodSpec
from qmc_bmgs.substrate.proposals import TrackAProposalSpec
from qmc_bmgs.substrate.trace import sha256_json


_TASKS = tuple(f"task-{index:02d}" for index in range(12))


@dataclass(frozen=True)
class _FakeBundle:
    payloads: dict[str, object]
    seal_digest: str = "a" * 64


def _bundle_payloads() -> dict[str, object]:
    return {
        "diagnostic_tasks.json": {
            "tasks": [{"task_fingerprint": task, "target": 100} for task in _TASKS]
        },
        "preregistration.json": {"bundle_id": BUNDLE_ID},
    }


def _cell(method: str, task: str, seed: int, proposal: str = "heuristic") -> object:
    return SimpleNamespace(
        budget_profile_id="score256",
        exploration_seed=seed,
        method_label=method,
        proposal_label=proposal,
        task_fingerprint=task,
    )


def _row(
    method: str,
    task: str,
    seed: int,
    *,
    search_record: dict[str, object] | None = None,
    success: bool = False,
    proposal: str = "heuristic",
) -> dict[str, object]:
    return {
        "cell": _cell(method, task, seed, proposal),
        "search_record": search_record or {"events": []},
        "summary": {"success_any": success},
    }


def _validated(records: list[dict[str, object]]) -> analysis._ValidatedRun:
    return analysis._ValidatedRun(
        _FakeBundle(_bundle_payloads()),  # type: ignore[arg-type]
        tuple(records),
        {
            "artifact_id": "synthetic",
            "attempt_id": "attempt",
            "deterministic_digest": "b" * 64,
            "execution_authorization_digest": "c" * 64,
            "reviewed_authorization_revision": "d" * 40,
        },
        "e" * 64,
    )


def _write_synthetic_artifact_members(
    directory: Path,
    marker: bytes,
) -> analysis._ArtifactReceipt:
    directory.mkdir(parents=True, exist_ok=True)
    snapshot = {
        filename: marker + b":" + filename.encode("ascii") + b"\n"
        for filename in analysis.RUN_ARTIFACT_FILENAMES
    }
    for filename, payload in snapshot.items():
        (directory / filename).write_bytes(payload)
    return analysis._artifact_snapshot_receipt(snapshot)


def _proposal_and_selection(
    *,
    digest: str,
    action_count: int,
    action_index: int,
    one_based_rank: int,
    depth: int,
    trajectory: int,
) -> tuple[dict[str, object], dict[str, object]]:
    indices = list(range(action_count))
    remaining = [index for index in indices if index != action_index]
    order = (
        remaining[: one_based_rank - 1]
        + [action_index]
        + remaining[one_based_rank - 1 :]
    )
    prior = [0.0] * action_count
    for position, index in enumerate(order):
        prior[index] = float(action_count - position)
    action_order_digest = f"order-{digest}"
    proposal = {
        "kind": "proposal_materialized",
        "payload": {
            "proposal": {
                "action_order": [{"index": index} for index in indices],
                "action_order_digest": action_order_digest,
                "behavior_digest": digest,
                "prior_logp": prior,
            }
        },
    }
    selection = {
        "kind": "selection_committed",
        "payload": {
            "action_index": action_index,
            "action_order_digest": action_order_digest,
            "depth": depth,
            "point_digest": f"point-{digest}",
            "proposal_behavior_digest": digest,
            "scored_action_indices": indices,
            "trajectory_index": trajectory,
        },
    }
    return proposal, selection


def _mechanism_records() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for method_index, method in enumerate(analysis._STOCHASTIC_METHOD_ORDER):
        for task_index, task in enumerate(_TASKS):
            for seed_index, seed in enumerate(analysis._DIAGNOSTIC_SEEDS):
                selected = (task_index + seed_index) % 4
                root_rank = 20 if method_index == 0 else 1
                trajectory = 1 if method_index == 3 else 0
                root_digest = f"{method}-root-{task_index}-{seed}"
                depth_digest = f"{method}-depth-{task_index}-{seed}"
                root = _proposal_and_selection(
                    digest=root_digest,
                    action_count=32,
                    action_index=selected,
                    one_based_rank=root_rank,
                    depth=0,
                    trajectory=trajectory,
                )
                depth = _proposal_and_selection(
                    digest=depth_digest,
                    action_count=7,
                    action_index=0,
                    one_based_rank=1,
                    depth=4,
                    trajectory=trajectory,
                )
                records.append(
                    _row(
                        method,
                        task,
                        seed,
                        search_record={"events": [*root, *depth]},
                    )
                )
    return records


def _dense_records() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for method in analysis._STOCHASTIC_METHOD_ORDER[2:]:
        for task in _TASKS:
            for seed in analysis._DIAGNOSTIC_SEEDS:
                terminals = []
                for trajectory, final_value in enumerate((100, 102)):
                    terminals.append(
                        {
                            "kind": "terminal_verified",
                            "payload": {
                                "trajectory_index": trajectory,
                                "verification": {
                                    "final_value": final_value,
                                    "success": final_value == 100,
                                    "target": 100,
                                },
                            },
                        }
                    )
                records.append(
                    _row(
                        method,
                        task,
                        seed,
                        search_record={"events": terminals},
                    )
                )
    return records


def _score_vectors(v2_successes: int) -> dict[str, list[Fraction]]:
    vectors = {
        method: [Fraction(0, 1) for _ in _TASKS]
        for method in (
            *analysis._DETERMINISTIC_BASELINES,
            *analysis._STOCHASTIC_METHOD_ORDER,
        )
    }
    for index in range(v2_successes):
        task_index, seed_index = divmod(index, 4)
        vectors["thompson_dimnorm_iid_v2"][task_index] += Fraction(1, 4)
        self_check = seed_index
        if not 0 <= self_check < 4:
            raise AssertionError("synthetic seed allocation drifted")
    return vectors


class CountdownThompsonDiagnosticAnalysisTests(unittest.TestCase):
    def test_self_test_opens_no_sealed_authority_or_search(self) -> None:
        with (
            patch.object(
                analysis,
                "verify_countdown_thompson_diagnostic_bundle",
                side_effect=AssertionError("sealed bundle must remain unopened"),
            ),
            patch.object(
                analysis,
                "replay_countdown_track_a_search_bytes",
                side_effect=AssertionError("search replay must remain unopened"),
            ),
        ):
            result = analysis._self_test()
        self.assertEqual(result["status"], "PASS")
        self.assertIn("no sealed bundle", result["claim_boundary"])

    def test_source_attestation_closes_canary_authority_dependency(self) -> None:
        self.assertEqual(len(analysis._SEARCH_SOURCE_PATHS), 9)
        self.assertEqual(len(analysis._RUNNER_SOURCE_PATHS), 5)
        self.assertEqual(len(analysis._CURRENT_REPLAY_MODULE_PATHS), 13)
        self.assertIn(
            "qmc_bmgs.experiments.countdown_track_a_canary_manifest",
            analysis._CURRENT_REPLAY_MODULE_PATHS,
        )
        self.assertEqual(
            set(analysis._RUNNER_SOURCE_PATHS),
            set(runner._RUNNER_SOURCE_PATHS),
        )
        self.assertEqual(analysis._REQUIRED_ANCESTRY, runner.REQUIRED_ANCESTRY)

    def test_build_attestation_requires_the_exact_frozen_ancestry(self) -> None:
        attestation = {
            "authorized_runner_revision": "1" * 40,
            "host_build": {},
            "numeric_microfixture": {},
            "required_ancestry": ["2" * 40],
            "runner_build_digest": "3" * 64,
            "runner_source_files": {},
            "schema_version": (
                "qmc-bmgs-countdown-thompson-diagnostic-build-attestation/v1"
            ),
            "search_build_digest": "4" * 64,
            "search_microfixture": {},
            "search_source_files": {},
        }
        with self.assertRaisesRegex(
            analysis.DiagnosticAnalysisError,
            "required ancestry drifted",
        ):
            analysis._validate_build_attestation_structure(attestation)

    def test_clean_checkout_gate_rejects_dirty_or_unreadable_status(self) -> None:
        root = Path("/tmp/qmc-diagnostic-clean-checkout-fixture")
        with patch.object(
            analysis,
            "_git_result",
            return_value=SimpleNamespace(returncode=0, stdout=b"?? drift.json\n"),
        ):
            with self.assertRaisesRegex(
                analysis.DiagnosticAnalysisError,
                "must be clean",
            ):
                analysis._require_clean_git_checkout(root)

        with patch.object(
            analysis,
            "_git_result",
            return_value=SimpleNamespace(returncode=1, stdout=b""),
        ):
            with self.assertRaisesRegex(
                analysis.DiagnosticAnalysisError,
                "status is unreadable",
            ):
                analysis._require_clean_git_checkout(root)

        with patch.object(
            analysis,
            "_git_result",
            return_value=SimpleNamespace(returncode=0, stdout=b""),
        ):
            analysis._require_clean_git_checkout(root)

    def test_authorization_semantics_close_before_record_access(self) -> None:
        attestation = {"fixture": "already structurally validated"}
        qualification = {"fixture": "runtime-qualified"}
        output = Path("/tmp/qmc-diagnostic-synthetic-artifact")
        seal_digest = "1" * 64
        method_digest = "2" * 64
        schedule_digest = "3" * 64
        runtime_digest = sha256_json(qualification)
        authorization_core = {
            "artifact_id": output.name,
            "authorization_scope": "one_exact_complete_240_cell_diagnostic_run",
            "bundle_id": BUNDLE_ID,
            "cell_count": 240,
            "claim_boundary": (
                "execution authority only; this engineering diagnostic grants no "
                "method-superiority or locked-128 execution authority"
            ),
            "diagnostic_seal_digest": seal_digest,
            "method_manifest_digest": method_digest,
            "output_path": str(output),
            "requires_explicit_digest_confirmation": True,
            "runner_build_attestation": attestation,
            "runtime_qualification": qualification,
            "runtime_qualification_digest": runtime_digest,
            "schedule_digest": schedule_digest,
            "schema_version": (
                "qmc-bmgs-countdown-thompson-diagnostic-execution-authorization/v1"
            ),
        }
        authorization = {
            **authorization_core,
            "deterministic_digest": sha256_json(authorization_core),
        }
        manifest = {
            "artifact_id": output.name,
            "authorized_output_path": str(output),
            "bundle_id": BUNDLE_ID,
            "diagnostic_seal_digest": seal_digest,
            "execution_authorization_digest": authorization["deterministic_digest"],
            "method_manifest_digest": method_digest,
            "runtime_qualification": qualification,
        }
        analysis._preflight_authorization(
            authorization,
            manifest=manifest,
            attestation=attestation,
        )
        tampered_core = {
            **authorization_core,
            "authorization_scope": "two_runs_are_not_authorized",
        }
        tampered = {
            **tampered_core,
            "deterministic_digest": sha256_json(tampered_core),
        }
        tampered_manifest = {
            **manifest,
            "execution_authorization_digest": tampered["deterministic_digest"],
        }
        with self.assertRaisesRegex(
            analysis.DiagnosticAnalysisError,
            "authorization preflight drifted",
        ):
            analysis._preflight_authorization(
                tampered,
                manifest=tampered_manifest,
                attestation=attestation,
            )
        numeric_alias_core = {**authorization_core, "cell_count": 240.0}
        numeric_alias = {
            **numeric_alias_core,
            "deterministic_digest": sha256_json(numeric_alias_core),
        }
        numeric_alias_manifest = {
            **manifest,
            "execution_authorization_digest": numeric_alias["deterministic_digest"],
        }
        with self.assertRaisesRegex(
            analysis.DiagnosticAnalysisError,
            "authorization preflight drifted",
        ):
            analysis._preflight_authorization(
                numeric_alias,
                manifest=numeric_alias_manifest,
                attestation=attestation,
            )

    def test_verified_bundle_semantics_close_before_record_access(self) -> None:
        attestation = {"fixture": "already structurally validated"}
        runtime_bindings = {"iid": {"digest": "1"}, "search": {"digest": "2"}}
        qualification = {
            "bundle_id": BUNDLE_ID,
            "execution_authorized": False,
            "runtime_bindings_digest": sha256_json(runtime_bindings),
            "status": "RUNTIME_QUALIFIED",
        }
        method_digest = "3" * 64
        schedule_digest = "4" * 64
        seal_digest = "5" * 64
        output = Path("/tmp/qmc-diagnostic-bundle-authority-fixture")
        cells = tuple(SimpleNamespace(cell_id=f"{index:064x}") for index in range(240))
        bundle = _FakeBundle(
            {
                "methods.json": {
                    "deterministic_digest": method_digest,
                    "runtime_bindings": runtime_bindings,
                },
                "preregistration.json": {
                    "bundle_id": BUNDLE_ID,
                    "execution_matrix": {"schedule_digest": schedule_digest},
                },
            },
            seal_digest,
        )
        authorization_core = {
            "artifact_id": output.name,
            "authorization_scope": "one_exact_complete_240_cell_diagnostic_run",
            "bundle_id": BUNDLE_ID,
            "cell_count": 240,
            "claim_boundary": (
                "execution authority only; this engineering diagnostic grants no "
                "method-superiority or locked-128 execution authority"
            ),
            "diagnostic_seal_digest": seal_digest,
            "method_manifest_digest": method_digest,
            "output_path": str(output),
            "requires_explicit_digest_confirmation": True,
            "runner_build_attestation": attestation,
            "runtime_qualification": qualification,
            "runtime_qualification_digest": sha256_json(qualification),
            "schedule_digest": schedule_digest,
            "schema_version": (
                "qmc-bmgs-countdown-thompson-diagnostic-execution-authorization/v1"
            ),
        }
        authorization = {
            **authorization_core,
            "deterministic_digest": sha256_json(authorization_core),
        }
        manifest = {
            "artifact_id": output.name,
            "authorized_output_path": str(output),
            "bundle_id": BUNDLE_ID,
            "cell_count": 240,
            "diagnostic_seal_digest": seal_digest,
            "execution_authorization_digest": authorization["deterministic_digest"],
            "method_manifest_digest": method_digest,
            "runtime_qualification": qualification,
            "schedule_cell_ids": [cell.cell_id for cell in cells],
        }
        analysis._preflight_authorization(
            authorization,
            manifest=manifest,
            attestation=attestation,
        )
        analysis._preflight_verified_bundle_authority(
            authorization,
            manifest=manifest,
            bundle=bundle,  # type: ignore[arg-type]
            expected_cells=cells,  # type: ignore[arg-type]
        )

        drifted_qualification = {
            **qualification,
            "execution_authorized": True,
            "runtime_bindings_digest": "6" * 64,
            "status": "RUNTIME_DRIFTED",
        }
        drifted_core = {
            **authorization_core,
            "runtime_qualification": drifted_qualification,
            "runtime_qualification_digest": sha256_json(drifted_qualification),
            "schedule_digest": "7" * 64,
        }
        drifted_authorization = {
            **drifted_core,
            "deterministic_digest": sha256_json(drifted_core),
        }
        drifted_manifest = {
            **manifest,
            "execution_authorization_digest": drifted_authorization[
                "deterministic_digest"
            ],
            "runtime_qualification": drifted_qualification,
        }
        analysis._preflight_authorization(
            drifted_authorization,
            manifest=drifted_manifest,
            attestation=attestation,
        )
        with self.assertRaisesRegex(
            analysis.DiagnosticAnalysisError,
            "verified bundle authority preflight drifted",
        ):
            analysis._preflight_verified_bundle_authority(
                drifted_authorization,
                manifest=drifted_manifest,
                bundle=bundle,  # type: ignore[arg-type]
                expected_cells=cells,  # type: ignore[arg-type]
            )

    def test_selection_rank_uses_descending_prior_and_canonical_tie_break(self) -> None:
        proposal, selection = _proposal_and_selection(
            digest="fixture",
            action_count=7,
            action_index=4,
            one_based_rank=3,
            depth=0,
            trajectory=0,
        )
        material = analysis._proposal_material({"events": [proposal]})
        evidence = analysis._selection_rank(selection["payload"], material)
        self.assertEqual(evidence["one_based_rank"], 3)
        self.assertEqual(evidence["normalized_rank"], Fraction(1, 3))
        tampered = dict(selection["payload"])
        tampered["scored_action_indices"] = list(range(6))
        with self.assertRaisesRegex(analysis.DiagnosticAnalysisError, "closure"):
            analysis._selection_rank(tampered, material)

    def test_mechanism_metrics_use_exact_rationals_and_fixed_bins(self) -> None:
        result = analysis._mechanism_metrics(_validated(_mechanism_records()))
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(
            result["v2_minus_v1_top5_count"], {"numerator": 48, "denominator": 1}
        )
        self.assertTrue(all(result["checks"].values()))
        v2 = result["method_metrics"]["thompson_dimnorm_iid_v2"]
        self.assertEqual(
            v2["mean_normalized_root_rank"], {"numerator": 0, "denominator": 1}
        )
        self.assertEqual(
            v2["mean_root_action_diversity"], {"numerator": 4, "denominator": 1}
        )
        self.assertEqual(v2["tasks_with_multiple_root_actions"], 12)
        self.assertEqual(set(v2["occupied_action_bin_means"]), {"3_7", "32_60"})

    def test_dense_metrics_fix_exact_error_and_fsum_order(self) -> None:
        result = analysis._dense_terminal_metrics(_validated(_dense_records()))
        for method in analysis._STOCHASTIC_METHOD_ORDER[2:]:
            row = result[method]
            self.assertEqual(row["observation_count"], 96)
            self.assertEqual(
                row["mean_terminal_absolute_error"], {"numerator": 1, "denominator": 1}
            )
            self.assertEqual(
                row["median_terminal_absolute_error"],
                {"numerator": 1, "denominator": 1},
            )
            self.assertEqual(row["minimum_terminal_absolute_error"], 0)
            self.assertEqual(
                row["mean_terminal_value"], math.fsum([1.0, 1.0 / 3.0] * 48) / 96
            )

    def test_exact_readiness_boundary_requires_two_of_48_successes(self) -> None:
        rescue = _row(
            "thompson_greedy_anchor_dense_iid_v4",
            _TASKS[0],
            7168,
            search_record={
                "events": [
                    {
                        "kind": "terminal_verified",
                        "payload": {
                            "trajectory_index": 0,
                            "verification": {"success": False},
                        },
                    },
                    {
                        "kind": "terminal_verified",
                        "payload": {
                            "trajectory_index": 1,
                            "verification": {"success": True},
                        },
                    },
                ]
            },
        )
        counts = {
            method: 0
            for method in (
                *analysis._DETERMINISTIC_BASELINES,
                *analysis._STOCHASTIC_METHOD_ORDER,
            )
        }
        passing = analysis._engineering_readiness(
            _validated([rescue]), _score_vectors(2), counts
        )
        self.assertEqual(
            passing["selected_candidate_method"], "thompson_dimnorm_iid_v2"
        )
        self.assertEqual(passing["status"], "READY_TO_PREREGISTER_LOCKED_128_EXECUTION")
        failing = analysis._engineering_readiness(
            _validated([rescue]), _score_vectors(1), counts
        )
        self.assertIsNone(failing["selected_candidate_method"])
        self.assertEqual(failing["status"], "STOP_REPAIR_NO_LOCKED_128_RUN")

    def test_minus_one_of_48_fails_the_minus_one_of_50_puct_guard(self) -> None:
        rescue = _row(
            "thompson_greedy_anchor_dense_iid_v4",
            _TASKS[0],
            7168,
            search_record={
                "events": [
                    {
                        "kind": "terminal_verified",
                        "payload": {
                            "trajectory_index": 0,
                            "verification": {"success": False},
                        },
                    },
                    {
                        "kind": "terminal_verified",
                        "payload": {
                            "trajectory_index": 1,
                            "verification": {"success": True},
                        },
                    },
                ]
            },
        )
        vectors = _score_vectors(47)
        vectors["puct_c1"] = [Fraction(1, 1) for _ in _TASKS]
        vectors["greedy"] = [Fraction(0, 1) for _ in _TASKS]
        vectors["beam_width_2"] = [Fraction(0, 1) for _ in _TASKS]
        counts = {method: 0 for method in vectors}
        result = analysis._engineering_readiness(_validated([rescue]), vectors, counts)
        v2 = result["candidate_evaluations"][0]
        puct = v2["margins"]["candidate_minus_puct_c1"]
        self.assertEqual(puct["mean_task_delta"], {"numerator": -1, "denominator": 48})
        self.assertFalse(puct["passes"])

    def test_typed_replay_inputs_rehydrate_v1_through_v4(self) -> None:
        task = CountdownTask((1, 2, 3, 4, 5, 6), 720)
        methods = (
            ("v1", TrackAMethodSpec.candidate_thompson("iid")),
            ("v2", TrackAMethodSpec.dimension_normalized_thompson("iid")),
            ("v3", TrackAMethodSpec.dimension_normalized_dense_thompson("iid")),
            (
                "v4",
                TrackAMethodSpec.greedy_anchored_dimension_normalized_dense_thompson(
                    "iid"
                ),
            ),
        )
        proposal = TrackAProposalSpec("greedy_rollout_target_error/v1")
        profile = _score256_profile()
        payloads = {
            "diagnostic_tasks.json": {"tasks": [task.to_dict()]},
            "proposals.json": {
                "policies": [{"label": "heuristic", "spec": proposal.to_dict()}]
            },
            "methods.json": {
                "methods": [
                    {"label": label, "spec": method.to_dict()}
                    for label, method in methods
                ]
            },
            "budgets.json": {"profiles": [{"spec": profile.to_dict()}]},
        }
        typed = analysis._typed_replay_inputs(_FakeBundle(payloads))  # type: ignore[arg-type]
        self.assertEqual(set(typed.methods), {"v1", "v2", "v3", "v4"})
        for label, method in methods:
            self.assertEqual(typed.methods[label].to_dict(), method.to_dict())

    def test_runner_record_passes_independent_analyzer_replay(self) -> None:
        task = CountdownTask((1, 2, 3, 4, 5, 6), 720)
        proposal = TrackAProposalSpec("greedy_rollout_target_error/v1")
        method = TrackAMethodSpec.dimension_normalized_thompson("iid")
        profile = _score256_profile()
        method_manifest_digest = "f" * 64
        cell = DiagnosticCell(
            task_fingerprint=task.task_fingerprint,
            task_manifest_digest="1" * 64,
            proposal_label="heuristic",
            proposal_spec_digest=proposal.deterministic_digest,
            method_label="thompson_dimnorm_iid_v2",
            method_spec_digest=sha256_json(method.to_dict()),
            method_manifest_digest=method_manifest_digest,
            budget_profile_id="score256",
            budget_profile_spec_digest=sha256_json(profile.to_dict()),
            exploration_seed=7168,
        )
        record = runner._execute_cell(
            cell,
            task=task,
            proposal=proposal,
            method=method,
            budget_profile=profile,
            diagnostic_seal_digest="2" * 64,
            method_manifest_digest=method_manifest_digest,
            runtime_qualification_digest="3" * 64,
            runner_build_digest="4" * 64,
            search_build_digest="5" * 64,
        )
        replay_inputs = analysis._ReplayInputs(
            {task.task_fingerprint: task},
            {"heuristic": proposal},
            {"thompson_dimnorm_iid_v2": method},
            {"score256": profile},
        )
        validated = analysis._validate_one_record(
            record,
            cell=cell,
            bundle_id=BUNDLE_ID,
            diagnostic_seal_digest="2" * 64,
            method_manifest_digest=method_manifest_digest,
            replay_inputs=replay_inputs,
            runner_build_digest="4" * 64,
            search_build_digest="5" * 64,
            runtime_qualification_digest="3" * 64,
        )
        self.assertEqual(validated["summary"], record["search_summary"])
        self.assertEqual(set(record), analysis._RUN_RECORD_FIELDS)
        aliased = deepcopy(record)
        aliased["search_trace_byte_count"] = float(aliased["search_trace_byte_count"])
        aliased["deterministic_digest"] = sha256_json(
            {
                key: value
                for key, value in aliased.items()
                if key != "deterministic_digest"
            }
        )
        with self.assertRaisesRegex(
            analysis.DiagnosticAnalysisError,
            "trace byte count mismatch",
        ):
            analysis._validate_one_record(
                aliased,
                cell=cell,
                bundle_id=BUNDLE_ID,
                diagnostic_seal_digest="2" * 64,
                method_manifest_digest=method_manifest_digest,
                replay_inputs=replay_inputs,
                runner_build_digest="4" * 64,
                search_build_digest="5" * 64,
                runtime_qualification_digest="3" * 64,
            )

    def test_summary_publication_is_canonical_and_no_overwrite(self) -> None:
        payload = {"schema_version": "synthetic/v1", "status": "PASS"}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "summary.json"
            analysis._atomic_write_no_replace(
                output, analysis._canonical_bytes(payload)
            )
            self.assertEqual(output.read_bytes(), analysis._canonical_bytes(payload))
            with self.assertRaises(FileExistsError):
                analysis._atomic_write_no_replace(
                    output, analysis._canonical_bytes(payload)
                )

    def test_artifact_snapshot_rejects_fifo_without_blocking(self) -> None:
        if not hasattr(os, "mkfifo"):
            self.skipTest("FIFO creation is unavailable")
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "artifact"
            _write_synthetic_artifact_members(artifact, b"fifo-fixture")
            records = artifact / "records.jsonl"
            records.unlink()
            os.mkfifo(records)

            pinned = analysis._pin_protected_roots((artifact,))
            try:
                started = time.monotonic()
                with self.assertRaisesRegex(
                    analysis.DiagnosticAnalysisError,
                    "member is not regular: records.jsonl",
                ):
                    analysis._read_artifact_snapshot_from_descriptor(
                        pinned[0].descriptor,
                        "synthetic artifact",
                    )
                elapsed = time.monotonic() - started
            finally:
                analysis._close_pinned_protected_roots(pinned)
            self.assertLess(elapsed, 1.0)

    def test_artifact_snapshot_rejects_regular_to_fifo_race_without_blocking(
        self,
    ) -> None:
        if not hasattr(os, "mkfifo"):
            self.skipTest("FIFO creation is unavailable")
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "artifact"
            _write_synthetic_artifact_members(artifact, b"fifo-race-fixture")
            records = artifact / "records.jsonl"
            original_stat = analysis.os.stat
            swapped = False

            pinned = analysis._pin_protected_roots((artifact,))

            def swap_after_regular_stat(
                path: object,
                *args: object,
                **kwargs: object,
            ) -> os.stat_result:
                nonlocal swapped
                observed = original_stat(path, *args, **kwargs)
                if (
                    not swapped
                    and path == records.name
                    and kwargs.get("dir_fd") == pinned[0].descriptor
                    and kwargs.get("follow_symlinks") is False
                ):
                    records.unlink()
                    os.mkfifo(records)
                    swapped = True
                return observed

            try:
                started = time.monotonic()
                with (
                    patch.object(
                        analysis.os,
                        "stat",
                        side_effect=swap_after_regular_stat,
                    ),
                    self.assertRaisesRegex(
                        analysis.DiagnosticAnalysisError,
                        "member raced to a non-regular file: records.jsonl",
                    ),
                ):
                    analysis._read_artifact_snapshot_from_descriptor(
                        pinned[0].descriptor,
                        "synthetic artifact",
                    )
                elapsed = time.monotonic() - started
            finally:
                analysis._close_pinned_protected_roots(pinned)
            self.assertTrue(swapped)
            self.assertLess(elapsed, 1.0)

    def test_artifact_closure_rejects_the_first_extra_entry(self) -> None:
        if os.name != "posix":
            self.skipTest("descriptor-bound directory scans require POSIX")

        class Entry:
            def __init__(self, name: str) -> None:
                self.name = name

        class FourEntriesThenBomb:
            def __init__(self) -> None:
                self._names = iter((*analysis.RUN_ARTIFACT_FILENAMES, "unexpected"))
                self.read_count = 0

            def __enter__(self) -> FourEntriesThenBomb:
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def __iter__(self) -> FourEntriesThenBomb:
                return self

            def __next__(self) -> Entry:
                self.read_count += 1
                if self.read_count > 4:
                    raise AssertionError(
                        "closure scan read beyond the first extra entry"
                    )
                return Entry(next(self._names))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            entries = FourEntriesThenBomb()
            try:
                with (
                    patch.object(analysis.os, "scandir", return_value=entries),
                    self.assertRaisesRegex(
                        analysis.DiagnosticAnalysisError,
                        "directory closure drifted",
                    ),
                ):
                    analysis._assert_artifact_directory_closure(
                        directory_fd,
                        "synthetic artifact",
                    )
            finally:
                os.close(directory_fd)
            self.assertEqual(entries.read_count, 4)

    def test_artifact_snapshot_rejects_member_above_v1_byte_cap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "artifact"
            _write_synthetic_artifact_members(artifact, b"oversized-fixture")
            records = artifact / "records.jsonl"
            records_cap = dict(analysis._RUN_ARTIFACT_MEMBER_BYTE_CAPS_V1)[records.name]
            os.truncate(records, records_cap + 1)

            pinned = analysis._pin_protected_roots((artifact,))
            try:
                with self.assertRaisesRegex(
                    analysis.DiagnosticAnalysisError,
                    "exceeds the v1 byte cap",
                ):
                    analysis._read_artifact_snapshot_from_descriptor(
                        pinned[0].descriptor,
                        "synthetic artifact",
                    )
            finally:
                analysis._close_pinned_protected_roots(pinned)

    def test_artifact_snapshot_does_not_chase_a_growing_member(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "artifact"
            _write_synthetic_artifact_members(artifact, b"growing-fixture")
            records = artifact / "records.jsonl"
            records_identity = (records.stat().st_dev, records.stat().st_ino)
            original_read = analysis.os.read
            grew = False

            def grow_after_first_records_read(descriptor: int, size: int) -> bytes:
                nonlocal grew
                payload = original_read(descriptor, size)
                opened = os.fstat(descriptor)
                if (
                    not grew
                    and payload
                    and (opened.st_dev, opened.st_ino) == records_identity
                ):
                    with records.open("ab") as handle:
                        handle.write(b"growth")
                    grew = True
                return payload

            pinned = analysis._pin_protected_roots((artifact,))
            try:
                with (
                    patch.object(
                        analysis.os,
                        "read",
                        side_effect=grow_after_first_records_read,
                    ),
                    self.assertRaisesRegex(
                        analysis.DiagnosticAnalysisError,
                        "grew beyond its declared byte size",
                    ),
                ):
                    analysis._read_artifact_snapshot_from_descriptor(
                        pinned[0].descriptor,
                        "synthetic artifact",
                    )
            finally:
                analysis._close_pinned_protected_roots(pinned)
            self.assertTrue(grew)

    def test_historical_receipt_rejects_expected_size_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "artifact"
            receipt = list(
                _write_synthetic_artifact_members(
                    artifact,
                    b"size-mismatch-fixture",
                )
            )
            filename, byte_count, digest = receipt[-1]
            receipt[-1] = (filename, byte_count + 1, digest)

            pinned = analysis._pin_protected_roots((artifact,))
            try:
                with self.assertRaisesRegex(
                    analysis.DiagnosticAnalysisError,
                    "byte size differs from the validated artifact",
                ):
                    analysis._read_artifact_receipt_from_descriptor(
                        pinned[0].descriptor,
                        "historical committed artifact",
                        tuple(receipt),
                    )
            finally:
                analysis._close_pinned_protected_roots(pinned)

    def test_summary_ancestor_symlink_pivot_cannot_reach_protected_root(
        self,
    ) -> None:
        payload = analysis._canonical_bytes(
            {"schema_version": "synthetic/v1", "status": "PASS"}
        )
        original_open = analysis._open_protected_root_authority

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            protected = root / "protected"
            (protected / "nested").mkdir(parents=True)
            publication_parent = root / "publication-parent"
            (publication_parent / "nested").mkdir(parents=True)
            displaced = root / "displaced-publication-parent"
            output = publication_parent / "nested" / "summary.json"
            pivoted = False

            def revalidate_after_pivot(path: Path, label: str):
                nonlocal pivoted
                if label == "protected root 0 after pinning" and not pivoted:
                    publication_parent.rename(displaced)
                    publication_parent.symlink_to(
                        protected,
                        target_is_directory=True,
                    )
                    pivoted = True
                return original_open(path, label)

            pinned = analysis._pin_protected_roots((protected,))
            try:
                with patch.object(
                    analysis,
                    "_open_protected_root_authority",
                    side_effect=revalidate_after_pivot,
                ):
                    with self.assertRaisesRegex(
                        analysis.DiagnosticAnalysisError,
                        "cannot modify",
                    ):
                        analysis._atomic_write_no_replace(
                            output,
                            payload,
                            protected_roots=pinned,
                        )
            finally:
                analysis._close_pinned_protected_roots(pinned)
            self.assertTrue(pivoted)
            self.assertFalse((protected / "nested" / output.name).exists())
            self.assertFalse((displaced / "nested" / output.name).exists())

    def test_summary_real_parent_move_under_protected_root_precedes_staging(
        self,
    ) -> None:
        payload = analysis._canonical_bytes(
            {"schema_version": "synthetic/v1", "status": "PASS"}
        )
        original_open = analysis._open_stable_directory_with_ancestry

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            protected = root / "protected"
            protected.mkdir()
            publication_parent = root / "publication-parent"
            publication_parent.mkdir()
            relocated = protected / "relocated-publication-parent"
            output = publication_parent / "summary.json"
            parent_was_relocated = False

            def relocate_after_parent_open(path: Path, label: str):
                nonlocal parent_was_relocated
                opened = original_open(path, label)
                if label == "summary parent" and not parent_was_relocated:
                    publication_parent.rename(relocated)
                    publication_parent.mkdir()
                    parent_was_relocated = True
                return opened

            pinned = analysis._pin_protected_roots((protected,))
            try:
                with patch.object(
                    analysis,
                    "_open_stable_directory_with_ancestry",
                    side_effect=relocate_after_parent_open,
                ):
                    with self.assertRaisesRegex(
                        analysis.DiagnosticAnalysisError,
                        "protected",
                    ):
                        analysis._atomic_write_no_replace(
                            output,
                            payload,
                            protected_roots=pinned,
                        )
            finally:
                analysis._close_pinned_protected_roots(pinned)
            self.assertTrue(parent_was_relocated)
            self.assertEqual(list(relocated.iterdir()), [])
            self.assertFalse(output.exists())

    def test_summary_parent_move_under_protected_root_after_fsync_is_ambiguous(
        self,
    ) -> None:
        payload = analysis._canonical_bytes(
            {"schema_version": "synthetic/v1", "status": "PASS"}
        )
        original_fsync = analysis.os.fsync

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            protected = root / "protected"
            protected.mkdir()
            publication_parent = root / "publication-parent"
            publication_parent.mkdir()
            relocated = protected / "relocated-publication-parent"
            output = publication_parent / "summary.json"
            parent_identity = (
                publication_parent.stat().st_dev,
                publication_parent.stat().st_ino,
            )
            parent_was_relocated = False

            def relocate_after_parent_barrier(descriptor: int) -> None:
                nonlocal parent_was_relocated
                opened = analysis.os.fstat(descriptor)
                original_fsync(descriptor)
                if (
                    not parent_was_relocated
                    and (opened.st_dev, opened.st_ino) == parent_identity
                    and output.exists()
                ):
                    publication_parent.rename(relocated)
                    publication_parent.mkdir()
                    parent_was_relocated = True

            pinned = analysis._pin_protected_roots((protected,))
            try:
                with patch.object(
                    analysis.os,
                    "fsync",
                    side_effect=relocate_after_parent_barrier,
                ):
                    with self.assertRaisesRegex(
                        analysis.DiagnosticAnalysisPublicationAmbiguousError,
                        "must not be used",
                    ):
                        analysis._atomic_write_no_replace(
                            output,
                            payload,
                            protected_roots=pinned,
                        )
            finally:
                analysis._close_pinned_protected_roots(pinned)
            self.assertTrue(parent_was_relocated)
            self.assertFalse(output.exists())
            self.assertEqual((relocated / output.name).read_bytes(), payload)

    def test_summary_protected_authority_swap_before_revalidation_is_rejected(
        self,
    ) -> None:
        original_open = analysis._open_protected_root_authority

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            protected = root / "protected"
            (protected / "out").mkdir(parents=True)
            original_protected_identity = (
                protected.stat().st_dev,
                protected.stat().st_ino,
            )
            bundle = root / "bundle"
            bundle.mkdir()
            safe = root / "safe"
            (safe / "out").mkdir(parents=True)
            displaced_safe = root / "displaced-safe"
            output = safe / "out" / "summary.json"
            swapped = False
            protected_revalidation_count = 0

            def swap_before_revalidation(path: Path, label: str):
                nonlocal protected_revalidation_count, swapped
                if label == "protected root 0 after pinning":
                    protected_revalidation_count += 1
                if protected_revalidation_count == 2 and not swapped:
                    safe.rename(displaced_safe)
                    protected.rename(safe)
                    protected.mkdir()
                    swapped = True
                return original_open(path, label)

            with (
                patch.object(
                    analysis,
                    "_open_protected_root_authority",
                    side_effect=swap_before_revalidation,
                ),
                patch.object(
                    analysis,
                    "_validate_artifact",
                    return_value=SimpleNamespace(
                        manifest={"authorized_output_path": str(protected.resolve())}
                    ),
                ) as validate,
                patch.object(
                    analysis,
                    "_build_summary",
                    return_value={
                        "schema_version": "synthetic/v1",
                        "status": "PASS",
                    },
                ),
            ):
                with self.assertRaisesRegex(
                    analysis.DiagnosticAnalysisError,
                    "path identity changed",
                ):
                    analysis.write_countdown_thompson_diagnostic_summary(
                        protected,
                        bundle,
                        root / "authorization.json",
                        "0" * 64,
                        output,
                        repository_root=root,
                    )
            self.assertTrue(swapped)
            validate.assert_called_once()
            self.assertEqual(
                (safe.stat().st_dev, safe.stat().st_ino),
                original_protected_identity,
            )
            self.assertFalse(output.exists())
            self.assertEqual(list((safe / "out").iterdir()), [])

    def test_relocated_copy_cannot_publish_inside_historical_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            historical = root / "historical-artifact"
            historical.mkdir()
            for filename in ("commit.json", "manifest.json", "records.jsonl"):
                (historical / filename).write_bytes(b"synthetic authority\n")
            relocated = root / "relocated-artifact"
            relocated.mkdir()
            bundle = root / "bundle"
            bundle.mkdir()
            output = historical / "summary.json"
            validated = SimpleNamespace(
                manifest={"authorized_output_path": str(historical.resolve())}
            )

            with (
                patch.object(
                    analysis,
                    "_validate_artifact",
                    return_value=validated,
                ) as validate,
                patch.object(
                    analysis,
                    "_build_summary",
                    return_value={
                        "schema_version": "synthetic/v1",
                        "status": "PASS",
                    },
                ),
            ):
                with self.assertRaisesRegex(
                    analysis.DiagnosticAnalysisError,
                    "historical authorized artifact",
                ):
                    analysis.write_countdown_thompson_diagnostic_summary(
                        relocated,
                        bundle,
                        root / "authorization.json",
                        "0" * 64,
                        output,
                        repository_root=root,
                    )
            validate.assert_called_once()
            self.assertEqual(
                {path.name for path in historical.iterdir()},
                {"commit.json", "manifest.json", "records.jsonl"},
            )
            self.assertFalse(output.exists())

    def test_historical_symlink_alias_to_artifact_is_rejected_before_write(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "relocated-artifact"
            artifact.mkdir()
            historical = root / "historical-artifact"
            historical.symlink_to(artifact, target_is_directory=True)
            bundle = root / "bundle"
            bundle.mkdir()
            publication_parent = root / "publication-parent"
            publication_parent.mkdir()
            output = publication_parent / "summary.json"

            with (
                patch.object(
                    analysis,
                    "_validate_artifact",
                    return_value=SimpleNamespace(
                        manifest={"authorized_output_path": str(historical)}
                    ),
                ) as validate,
                patch.object(
                    analysis,
                    "_build_summary",
                    return_value={
                        "schema_version": "synthetic/v1",
                        "status": "PASS",
                    },
                ),
                patch.object(analysis, "_atomic_write_no_replace") as atomic_write,
            ):
                with self.assertRaisesRegex(
                    analysis.DiagnosticAnalysisError,
                    "stable non-symlink directory",
                ):
                    analysis.write_countdown_thompson_diagnostic_summary(
                        artifact,
                        bundle,
                        root / "authorization.json",
                        "0" * 64,
                        output,
                        repository_root=root,
                    )
            validate.assert_called_once()
            atomic_write.assert_not_called()
            self.assertTrue(historical.is_symlink())
            self.assertFalse(output.exists())

    def test_historical_empty_or_foreign_artifact_is_rejected_before_write(
        self,
    ) -> None:
        for case in ("empty", "foreign"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                artifact = root / "relocated-artifact"
                artifact_receipt = _write_synthetic_artifact_members(
                    artifact,
                    b"validated-artifact",
                )
                historical = root / "historical-artifact"
                if case == "empty":
                    historical.mkdir()
                else:
                    _write_synthetic_artifact_members(
                        historical,
                        b"foreign-artifact",
                    )
                bundle = root / "bundle"
                bundle.mkdir()
                publication_parent = root / "publication-parent"
                publication_parent.mkdir()
                output = publication_parent / "summary.json"

                with (
                    patch.object(
                        analysis,
                        "_validate_artifact",
                        return_value=SimpleNamespace(
                            manifest={"authorized_output_path": str(historical)},
                            artifact_receipt=artifact_receipt,
                        ),
                    ) as validate,
                    patch.object(
                        analysis,
                        "_build_summary",
                        return_value={
                            "schema_version": "synthetic/v1",
                            "status": "PASS",
                        },
                    ),
                    patch.object(
                        analysis,
                        "_atomic_write_no_replace",
                    ) as atomic_write,
                ):
                    with self.assertRaisesRegex(
                        analysis.DiagnosticAnalysisError,
                        "historical committed artifact",
                    ):
                        analysis.write_countdown_thompson_diagnostic_summary(
                            artifact,
                            bundle,
                            root / "authorization.json",
                            "0" * 64,
                            output,
                            repository_root=root,
                        )
                validate.assert_called_once()
                atomic_write.assert_not_called()
                self.assertFalse(output.exists())

    def test_byte_identical_relocated_and_historical_artifacts_can_publish(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "relocated-artifact"
            artifact_receipt = _write_synthetic_artifact_members(
                artifact,
                b"identical-artifact",
            )
            historical = root / "historical-artifact"
            historical_receipt = _write_synthetic_artifact_members(
                historical,
                b"identical-artifact",
            )
            self.assertEqual(historical_receipt, artifact_receipt)
            bundle = root / "bundle"
            bundle.mkdir()
            publication_parent = root / "publication-parent"
            publication_parent.mkdir()
            output = publication_parent / "summary.json"
            summary = {
                "schema_version": "synthetic/v1",
                "status": "PASS",
            }

            with (
                patch.object(
                    analysis,
                    "_validate_artifact",
                    return_value=SimpleNamespace(
                        manifest={"authorized_output_path": str(historical)},
                        artifact_receipt=artifact_receipt,
                    ),
                ),
                patch.object(
                    analysis,
                    "_build_summary",
                    return_value=summary,
                ),
                patch.object(analysis, "_atomic_write_no_replace") as atomic_write,
            ):
                observed = analysis.write_countdown_thompson_diagnostic_summary(
                    artifact,
                    bundle,
                    root / "authorization.json",
                    "0" * 64,
                    output,
                    repository_root=root,
                )
            self.assertEqual(observed, summary)
            atomic_write.assert_called_once()
            self.assertFalse(output.exists())

    def test_historical_directory_equal_to_artifact_retains_raw_pin(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "artifact"
            artifact_receipt = _write_synthetic_artifact_members(
                artifact,
                b"same-directory-artifact",
            )
            bundle = root / "bundle"
            bundle.mkdir()
            publication_parent = root / "publication-parent"
            publication_parent.mkdir()
            output = publication_parent / "summary.json"
            summary = {
                "schema_version": "synthetic/v1",
                "status": "PASS",
            }

            def assert_duplicate_pins(
                _path: Path,
                _payload: bytes,
                *,
                protected_roots: tuple[analysis._PinnedProtectedRoot, ...],
            ) -> None:
                self.assertEqual(len(protected_roots), 3)
                artifact_pin, _bundle_pin, historical_pin = protected_roots
                self.assertEqual(artifact_pin.identity, historical_pin.identity)
                self.assertNotEqual(
                    artifact_pin.descriptor,
                    historical_pin.descriptor,
                )
                self.assertEqual(artifact_pin.authority_path, artifact)
                self.assertEqual(historical_pin.authority_path, artifact)
                analysis._assert_pinned_protected_roots(protected_roots)

            with (
                patch.object(
                    analysis,
                    "_validate_artifact",
                    return_value=SimpleNamespace(
                        manifest={"authorized_output_path": str(artifact)},
                        artifact_receipt=artifact_receipt,
                    ),
                ),
                patch.object(
                    analysis,
                    "_build_summary",
                    return_value=summary,
                ),
                patch.object(
                    analysis,
                    "_atomic_write_no_replace",
                    side_effect=assert_duplicate_pins,
                ) as atomic_write,
            ):
                observed = analysis.write_countdown_thompson_diagnostic_summary(
                    artifact,
                    bundle,
                    root / "authorization.json",
                    "0" * 64,
                    output,
                    repository_root=root,
                )
            self.assertEqual(observed, summary)
            atomic_write.assert_called_once()
            self.assertFalse(output.exists())

    def test_absent_historical_path_race_is_rejected_before_publication(self) -> None:
        original_open = analysis._open_protected_root_authority

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "relocated-artifact"
            artifact.mkdir()
            bundle = root / "bundle"
            bundle.mkdir()
            historical = root / "historical-artifact"
            publication_parent = root / "publication-parent"
            publication_parent.mkdir()
            relocated_parent = historical / publication_parent.name
            output = publication_parent / "summary.json"
            raced = False

            def report_absent_then_pivot(
                path: Path,
                label: str,
            ):
                nonlocal raced
                if path == historical and not raced:
                    historical.mkdir()
                    publication_parent.rename(relocated_parent)
                    publication_parent.symlink_to(
                        relocated_parent,
                        target_is_directory=True,
                    )
                    raced = True
                    raise analysis.DiagnosticAnalysisError(
                        "synthetic historical authority open observed absence"
                    )
                return original_open(path, label)

            with (
                patch.object(
                    analysis,
                    "_validate_artifact",
                    return_value=SimpleNamespace(
                        manifest={"authorized_output_path": str(historical)}
                    ),
                ) as validate,
                patch.object(
                    analysis,
                    "_build_summary",
                    return_value={
                        "schema_version": "synthetic/v1",
                        "status": "PASS",
                    },
                ),
                patch.object(
                    analysis,
                    "_open_protected_root_authority",
                    side_effect=report_absent_then_pivot,
                ),
                patch.object(analysis, "_atomic_write_no_replace") as atomic_write,
            ):
                with self.assertRaisesRegex(
                    analysis.DiagnosticAnalysisError,
                    "historical authorized artifact path must exist",
                ):
                    analysis.write_countdown_thompson_diagnostic_summary(
                        artifact,
                        bundle,
                        root / "authorization.json",
                        "0" * 64,
                        output,
                        repository_root=root,
                    )
            validate.assert_called_once()
            atomic_write.assert_not_called()
            self.assertTrue(raced)
            self.assertTrue(publication_parent.is_symlink())
            self.assertEqual(list(relocated_parent.iterdir()), [])
            self.assertFalse(output.exists())

    def test_summary_path_only_protected_authority_is_rejected(self) -> None:
        payload = analysis._canonical_bytes(
            {"schema_version": "synthetic/v1", "status": "PASS"}
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            protected = root / "protected"
            protected.mkdir()
            output = root / "summary.json"
            with self.assertRaisesRegex(
                analysis.DiagnosticAnalysisError,
                "requires pinned protected-root authority",
            ):
                analysis._atomic_write_no_replace(
                    output,
                    payload,
                    protected_roots=(protected,),
                )
            self.assertFalse(output.exists())

    def test_summary_move_after_parent_fsync_is_publication_ambiguous(self) -> None:
        payload = analysis._canonical_bytes(
            {"schema_version": "synthetic/v1", "status": "PASS"}
        )
        original_fsync = analysis.os.fsync

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "summary.json"
            moved = root / "moved-summary.json"
            parent_identity = (root.stat().st_dev, root.stat().st_ino)
            moved_after_barrier = False

            def move_after_parent_barrier(descriptor: int) -> None:
                nonlocal moved_after_barrier
                observed = analysis.os.fstat(descriptor)
                original_fsync(descriptor)
                if (
                    not moved_after_barrier
                    and (observed.st_dev, observed.st_ino) == parent_identity
                    and output.exists()
                ):
                    output.rename(moved)
                    moved_after_barrier = True

            with patch.object(
                analysis.os,
                "fsync",
                side_effect=move_after_parent_barrier,
            ):
                with self.assertRaisesRegex(
                    analysis.DiagnosticAnalysisPublicationAmbiguousError,
                    "must not be used",
                ):
                    analysis._atomic_write_no_replace(output, payload)
            self.assertTrue(moved_after_barrier)
            self.assertFalse(output.exists())
            self.assertEqual(moved.read_bytes(), payload)

    def test_summary_swap_during_final_topology_is_not_reported_pass(self) -> None:
        payload = analysis._canonical_bytes(
            {"schema_version": "synthetic/v1", "status": "PASS"}
        )
        original_exact = analysis._summary_publication_is_exact
        original_topology = analysis._assert_summary_publication_topology

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "summary.json"
            moved = root / "moved-summary.json"
            exact_observations = 0
            swapped = False

            def count_exact(*args: object, **kwargs: object) -> bool:
                nonlocal exact_observations
                result = original_exact(*args, **kwargs)
                if result:
                    exact_observations += 1
                return result

            def swap_after_final_topology(*args: object, **kwargs: object) -> None:
                nonlocal swapped
                original_topology(*args, **kwargs)
                if exact_observations >= 2 and not swapped and output.exists():
                    output.rename(moved)
                    swapped = True

            with (
                patch.object(
                    analysis,
                    "_summary_publication_is_exact",
                    side_effect=count_exact,
                ),
                patch.object(
                    analysis,
                    "_assert_summary_publication_topology",
                    side_effect=swap_after_final_topology,
                ),
            ):
                with self.assertRaisesRegex(
                    analysis.DiagnosticAnalysisPublicationAmbiguousError,
                    "must not be used",
                ):
                    analysis._atomic_write_no_replace(output, payload)
            self.assertTrue(swapped)
            self.assertFalse(output.exists())
            self.assertEqual(moved.read_bytes(), payload)

    def test_summary_recovery_reobserves_exact_after_final_topology(self) -> None:
        payload = analysis._canonical_bytes(
            {"schema_version": "synthetic/v1", "status": "PASS"}
        )
        original_rename = analysis._rename_noreplace_at
        original_topology = analysis._assert_summary_publication_topology

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "summary.json"
            moved = root / "moved-summary.json"
            rename_completed = False
            recovery_topology_checks = 0
            swapped = False

            def rename_then_raise(*args: object) -> None:
                nonlocal rename_completed
                original_rename(*args)
                rename_completed = True
                raise OSError("synthetic post-rename interruption")

            def swap_during_recovery_final_topology(
                *args: object,
                **kwargs: object,
            ) -> None:
                nonlocal recovery_topology_checks, swapped
                original_topology(*args, **kwargs)
                if rename_completed:
                    recovery_topology_checks += 1
                if recovery_topology_checks == 3 and not swapped and output.exists():
                    output.rename(moved)
                    swapped = True

            with (
                patch.object(
                    analysis,
                    "_rename_noreplace_at",
                    side_effect=rename_then_raise,
                ),
                patch.object(
                    analysis,
                    "_assert_summary_publication_topology",
                    side_effect=swap_during_recovery_final_topology,
                ),
            ):
                with self.assertRaisesRegex(
                    analysis.DiagnosticAnalysisPublicationAmbiguousError,
                    "must not be used",
                ):
                    analysis._atomic_write_no_replace(output, payload)
            self.assertTrue(rename_completed)
            self.assertEqual(recovery_topology_checks, 3)
            self.assertTrue(swapped)
            self.assertFalse(output.exists())
            self.assertEqual(moved.read_bytes(), payload)

    def test_summary_move_back_to_staging_after_fsync_is_ambiguous(self) -> None:
        payload = analysis._canonical_bytes(
            {"schema_version": "synthetic/v1", "status": "PASS"}
        )
        original_fsync = analysis.os.fsync
        original_rename = analysis._rename_noreplace_at

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "summary.json"
            parent_identity = (root.stat().st_dev, root.stat().st_ino)
            staging_name = ""
            moved_back_after_barrier = False

            def capture_staging_name(
                directory_fd: int,
                source_name: str,
                destination_name: str,
            ) -> None:
                nonlocal staging_name
                original_rename(directory_fd, source_name, destination_name)
                if destination_name == output.name:
                    staging_name = source_name

            def move_back_after_parent_barrier(descriptor: int) -> None:
                nonlocal moved_back_after_barrier
                observed = analysis.os.fstat(descriptor)
                original_fsync(descriptor)
                if (
                    not moved_back_after_barrier
                    and staging_name
                    and (observed.st_dev, observed.st_ino) == parent_identity
                    and output.exists()
                ):
                    output.rename(root / staging_name)
                    moved_back_after_barrier = True

            with (
                patch.object(
                    analysis,
                    "_rename_noreplace_at",
                    side_effect=capture_staging_name,
                ),
                patch.object(
                    analysis.os,
                    "fsync",
                    side_effect=move_back_after_parent_barrier,
                ),
            ):
                with self.assertRaisesRegex(
                    analysis.DiagnosticAnalysisPublicationAmbiguousError,
                    "must not be used",
                ):
                    analysis._atomic_write_no_replace(output, payload)
            self.assertTrue(moved_back_after_barrier)
            self.assertFalse(output.exists())
            self.assertEqual((root / staging_name).read_bytes(), payload)

    def test_summary_parent_sync_retry_proves_success(self) -> None:
        payload = analysis._canonical_bytes(
            {"schema_version": "synthetic/v1", "status": "PASS"}
        )
        original_fsync = analysis.os.fsync
        call_count = 0

        def fail_first_parent_sync(descriptor: int) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise OSError("transient summary parent sync failure")
            original_fsync(descriptor)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "summary.json"
            with patch.object(
                analysis.os,
                "fsync",
                side_effect=fail_first_parent_sync,
            ):
                analysis._atomic_write_no_replace(output, payload)
            self.assertEqual(output.read_bytes(), payload)

    def test_summary_post_rename_exception_or_interrupt_recovers_success(self) -> None:
        payload = analysis._canonical_bytes(
            {"schema_version": "synthetic/v1", "status": "PASS"}
        )
        original_rename = analysis._rename_noreplace_at
        for exception_type in (OSError, KeyboardInterrupt):
            with self.subTest(exception_type=exception_type.__name__):
                with tempfile.TemporaryDirectory() as directory:
                    output = Path(directory) / "summary.json"

                    def rename_then_raise(*args: object) -> None:
                        original_rename(*args)
                        raise exception_type("synthetic post-rename interruption")

                    with patch.object(
                        analysis,
                        "_rename_noreplace_at",
                        side_effect=rename_then_raise,
                    ):
                        analysis._atomic_write_no_replace(output, payload)
                    self.assertEqual(output.read_bytes(), payload)
                    self.assertEqual(
                        {path.name for path in Path(directory).iterdir()},
                        {output.name},
                    )

    def test_summary_same_inode_corruption_is_never_success(self) -> None:
        payload = analysis._canonical_bytes(
            {"schema_version": "synthetic/v1", "status": "PASS"}
        )
        corrupted = b'{"status":"CORRUPTED"}\n'
        original_rename = analysis._rename_noreplace_at
        renamed_identities: list[tuple[tuple[int, int], tuple[int, int]]] = []

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "summary.json"

            def rename_then_corrupt(
                directory_fd: int,
                source: str,
                destination: str,
            ) -> None:
                source_stat = analysis.os.stat(
                    source,
                    dir_fd=directory_fd,
                    follow_symlinks=False,
                )
                original_rename(directory_fd, source, destination)
                destination_stat = analysis.os.stat(
                    destination,
                    dir_fd=directory_fd,
                    follow_symlinks=False,
                )
                renamed_identities.append(
                    (
                        (source_stat.st_dev, source_stat.st_ino),
                        (destination_stat.st_dev, destination_stat.st_ino),
                    )
                )
                descriptor = analysis.os.open(
                    destination,
                    analysis.os.O_WRONLY | analysis.os.O_TRUNC,
                    dir_fd=directory_fd,
                )
                try:
                    analysis.os.write(descriptor, corrupted)
                    analysis.os.fsync(descriptor)
                finally:
                    analysis.os.close(descriptor)

            with patch.object(
                analysis,
                "_rename_noreplace_at",
                side_effect=rename_then_corrupt,
            ):
                with self.assertRaisesRegex(
                    analysis.DiagnosticAnalysisPublicationAmbiguousError,
                    "must not be used",
                ):
                    analysis._atomic_write_no_replace(output, payload)
            self.assertEqual(renamed_identities[0][0], renamed_identities[0][1])
            self.assertEqual(output.read_bytes(), corrupted)

    def test_summary_observation_error_is_not_treated_as_absence(self) -> None:
        payload = analysis._canonical_bytes(
            {"schema_version": "synthetic/v1", "status": "PASS"}
        )
        original_open = analysis.os.open

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "summary.json"
            destination.write_bytes(payload)
            parent_fd, parent_stat = analysis._open_stable_directory(
                destination.parent,
                "synthetic summary parent",
            )
            published = destination.stat()
            identity = (published.st_dev, published.st_ino)

            def fail_entry_observation(
                path: object,
                *args: object,
                **kwargs: object,
            ) -> int:
                if path == destination.name and kwargs.get("dir_fd") is not None:
                    raise PermissionError("summary observation blocked")
                return original_open(path, *args, **kwargs)

            try:
                with patch.object(
                    analysis.os,
                    "open",
                    side_effect=fail_entry_observation,
                ):
                    with self.assertRaisesRegex(
                        analysis.DiagnosticAnalysisPublicationAmbiguousError,
                        "could not be observed",
                    ):
                        analysis._summary_publication_is_exact(
                            destination,
                            parent_fd,
                            (parent_stat.st_dev, parent_stat.st_ino),
                            identity,
                            payload,
                        )

                def report_entry_absent(
                    path: object,
                    *args: object,
                    **kwargs: object,
                ) -> int:
                    if path == destination.name and kwargs.get("dir_fd") is not None:
                        raise FileNotFoundError
                    return original_open(path, *args, **kwargs)

                with patch.object(
                    analysis.os,
                    "open",
                    side_effect=report_entry_absent,
                ):
                    self.assertFalse(
                        analysis._summary_publication_is_exact(
                            destination,
                            parent_fd,
                            (parent_stat.st_dev, parent_stat.st_ino),
                            identity,
                            payload,
                        )
                    )
            finally:
                analysis.os.close(parent_fd)

    def test_summary_initial_observation_io_failure_is_ambiguous(self) -> None:
        payload = analysis._canonical_bytes(
            {"schema_version": "synthetic/v1", "status": "PASS"}
        )
        original_stat = analysis.os.stat

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "summary.json"

            def fail_destination_stat(
                path: object,
                *args: object,
                **kwargs: object,
            ) -> object:
                if path == output.name and kwargs.get("dir_fd") is not None:
                    raise PermissionError("initial destination observation blocked")
                return original_stat(path, *args, **kwargs)

            with patch.object(
                analysis.os,
                "stat",
                side_effect=fail_destination_stat,
            ):
                with self.assertRaisesRegex(
                    analysis.DiagnosticAnalysisPublicationAmbiguousError,
                    "initial state could not be observed",
                ):
                    analysis._atomic_write_no_replace(output, payload)
            self.assertFalse(output.exists())

    def test_summary_sync_failure_uses_durable_quarantine_rollback(self) -> None:
        payload = analysis._canonical_bytes(
            {"schema_version": "synthetic/v1", "status": "PASS"}
        )
        original_fsync = analysis.os.fsync
        call_count = 0

        def fail_commit_and_retry(descriptor: int) -> None:
            nonlocal call_count
            call_count += 1
            if call_count in {2, 3}:
                raise OSError("summary parent sync failure")
            original_fsync(descriptor)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "summary.json"
            with patch.object(
                analysis.os,
                "fsync",
                side_effect=fail_commit_and_retry,
            ):
                with self.assertRaisesRegex(OSError, "summary parent sync failure"):
                    analysis._atomic_write_no_replace(output, payload)
            self.assertEqual(call_count, 4)
            self.assertFalse(output.exists())
            quarantines = tuple(
                path
                for path in Path(directory).iterdir()
                if path.name.startswith(".summary.json.rollback-")
            )
            self.assertEqual(len(quarantines), 1)
            self.assertEqual(quarantines[0].read_bytes(), payload)

    def test_summary_rollback_sync_failure_reports_ambiguity(self) -> None:
        payload = analysis._canonical_bytes(
            {"schema_version": "synthetic/v1", "status": "PASS"}
        )
        original_fsync = analysis.os.fsync

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "summary.json"
            call_count = 0

            def fail_every_parent_sync(descriptor: int) -> None:
                nonlocal call_count
                call_count += 1
                if call_count >= 2:
                    raise OSError("persistent summary parent sync failure")
                original_fsync(descriptor)

            with patch.object(
                analysis.os,
                "fsync",
                side_effect=fail_every_parent_sync,
            ):
                with self.assertRaisesRegex(
                    analysis.DiagnosticAnalysisPublicationAmbiguousError,
                    "must not be used",
                ):
                    analysis._atomic_write_no_replace(output, payload)
            self.assertFalse(output.exists())
            quarantines = tuple(
                path
                for path in Path(directory).iterdir()
                if path.name.startswith(".summary.json.rollback-")
            )
            self.assertEqual(len(quarantines), 1)
            self.assertEqual(quarantines[0].read_bytes(), payload)

    def test_summary_cleanup_error_does_not_mask_primary_ambiguity(self) -> None:
        payload = analysis._canonical_bytes(
            {"schema_version": "synthetic/v1", "status": "PASS"}
        )
        primary = analysis.DiagnosticAnalysisPublicationAmbiguousError(
            "primary summary observation ambiguity"
        )
        original_close = analysis.os.close

        def close_then_raise(descriptor: int) -> None:
            original_close(descriptor)
            raise RuntimeError("synthetic descriptor cleanup failure")

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "summary.json"
            with (
                patch.object(
                    analysis,
                    "_summary_publication_state",
                    side_effect=primary,
                ),
                patch.object(
                    analysis.os,
                    "close",
                    side_effect=close_then_raise,
                ),
            ):
                with self.assertRaisesRegex(
                    analysis.DiagnosticAnalysisPublicationAmbiguousError,
                    "primary summary observation ambiguity",
                ):
                    analysis._atomic_write_no_replace(output, payload)
            self.assertEqual(output.read_bytes(), payload)

    def test_summary_pre_rename_failure_retains_foreign_staging_replacement(
        self,
    ) -> None:
        payload = analysis._canonical_bytes(
            {"schema_version": "synthetic/v1", "status": "PASS"}
        )
        foreign = b'{"foreign_staging_replacement":true}\n'
        original_unlink = analysis.os.unlink
        retained_names: list[str] = []

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "summary.json"

            def swap_staging_then_fail_rename(
                directory_fd: int,
                source: str,
                destination: str,
            ) -> None:
                del destination
                original_unlink(source, dir_fd=directory_fd)
                descriptor = analysis.os.open(
                    source,
                    analysis.os.O_WRONLY | analysis.os.O_CREAT | analysis.os.O_EXCL,
                    0o600,
                    dir_fd=directory_fd,
                )
                try:
                    analysis.os.write(descriptor, foreign)
                    analysis.os.fsync(descriptor)
                finally:
                    analysis.os.close(descriptor)
                retained_names.append(source)
                raise OSError("synthetic pre-rename failure")

            with (
                patch.object(
                    analysis,
                    "_rename_noreplace_at",
                    side_effect=swap_staging_then_fail_rename,
                ),
                patch.object(
                    analysis.os,
                    "unlink",
                    wraps=original_unlink,
                ) as observed_unlink,
            ):
                with self.assertRaisesRegex(
                    analysis.DiagnosticAnalysisError,
                    "publication is unavailable",
                ):
                    analysis._atomic_write_no_replace(output, payload)
            self.assertEqual(observed_unlink.call_count, 0)
            self.assertFalse(output.exists())
            self.assertEqual(len(retained_names), 1)
            retained = Path(directory) / retained_names[0]
            self.assertEqual(retained.read_bytes(), foreign)

    def test_summary_recovery_never_deletes_foreign_destination(self) -> None:
        payload = analysis._canonical_bytes(
            {"schema_version": "synthetic/v1", "status": "PASS"}
        )
        foreign = b'{"foreign":true}\n'
        original_rename = analysis._rename_noreplace_at

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "summary.json"

            def create_foreign_then_rename(
                directory_fd: int,
                source: str,
                destination: str,
            ) -> None:
                descriptor = analysis.os.open(
                    destination,
                    analysis.os.O_WRONLY | analysis.os.O_CREAT | analysis.os.O_EXCL,
                    0o600,
                    dir_fd=directory_fd,
                )
                try:
                    analysis.os.write(descriptor, foreign)
                    analysis.os.fsync(descriptor)
                finally:
                    analysis.os.close(descriptor)
                original_rename(directory_fd, source, destination)

            with patch.object(
                analysis,
                "_rename_noreplace_at",
                side_effect=create_foreign_then_rename,
            ):
                with self.assertRaises(
                    analysis.DiagnosticAnalysisPublicationAmbiguousError
                ):
                    analysis._atomic_write_no_replace(output, payload)
            self.assertEqual(output.read_bytes(), foreign)

    def test_summary_publication_ambiguity_has_a_distinct_cli_status(self) -> None:
        with (
            patch.object(
                analysis,
                "write_countdown_thompson_diagnostic_summary",
                side_effect=analysis.DiagnosticAnalysisPublicationAmbiguousError(
                    "synthetic publication ambiguity"
                ),
            ),
            patch("builtins.print") as printed,
        ):
            status = analysis.main(
                [
                    "--analyze",
                    "artifact",
                    "--bundle",
                    "bundle",
                    "--authorization-file",
                    "authorization.json",
                    "--authorization-digest",
                    "0" * 64,
                    "--output",
                    "summary.json",
                    "--repository-root",
                    ".",
                ]
            )
        self.assertEqual(status, 3)
        self.assertIn("PUBLICATION_STATE_AMBIGUOUS", printed.call_args.args[0])


def _score256_profile() -> TrackABudgetProfile:
    return TrackABudgetProfile(
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


if __name__ == "__main__":
    unittest.main()
