from __future__ import annotations

import math
import tempfile
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

    def test_summary_observation_error_is_not_treated_as_absence(self) -> None:
        destination = Path("/tmp/qmc-diagnostic-summary-observation.json")
        with patch.object(
            analysis.os,
            "stat",
            side_effect=PermissionError("summary observation blocked"),
        ):
            with self.assertRaisesRegex(
                analysis.DiagnosticAnalysisPublicationAmbiguousError,
                "could not be observed",
            ):
                analysis._summary_publication_is_exact(
                    destination,
                    17,
                    (1, 2),
                    (3, 4),
                )

        with patch.object(
            analysis.os,
            "stat",
            side_effect=FileNotFoundError,
        ):
            self.assertFalse(
                analysis._summary_publication_is_exact(
                    destination,
                    17,
                    (1, 2),
                    (3, 4),
                )
            )

    def test_summary_observed_absence_requires_parent_sync(self) -> None:
        payload = analysis._canonical_bytes(
            {"schema_version": "synthetic/v1", "status": "PASS"}
        )
        original_fsync = analysis.os.fsync
        original_unlink = analysis._unlink_if_identity
        call_count = 0

        def fail_commit_and_retry(descriptor: int) -> None:
            nonlocal call_count
            call_count += 1
            if call_count in {2, 3}:
                raise OSError("summary parent sync failure")
            original_fsync(descriptor)

        def remove_but_report_no_match(
            directory_fd: int,
            filename: str,
            identity: tuple[int, int],
        ) -> bool:
            if filename == "summary.json":
                analysis.os.unlink(filename, dir_fd=directory_fd)
                return False
            return original_unlink(directory_fd, filename, identity)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "summary.json"
            with (
                patch.object(
                    analysis.os,
                    "fsync",
                    side_effect=fail_commit_and_retry,
                ),
                patch.object(
                    analysis,
                    "_unlink_if_identity",
                    side_effect=remove_but_report_no_match,
                ),
            ):
                with self.assertRaisesRegex(OSError, "summary parent sync failure"):
                    analysis._atomic_write_no_replace(output, payload)
            self.assertEqual(call_count, 4)
            self.assertFalse(output.exists())

    def test_summary_sync_failure_rolls_back_or_reports_ambiguity(self) -> None:
        payload = analysis._canonical_bytes(
            {"schema_version": "synthetic/v1", "status": "PASS"}
        )
        original_fsync = analysis.os.fsync

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "summary.json"
            call_count = 0

            def fail_commit_and_retry(descriptor: int) -> None:
                nonlocal call_count
                call_count += 1
                if call_count in {2, 3}:
                    raise OSError("summary parent sync failure")
                original_fsync(descriptor)

            with patch.object(
                analysis.os,
                "fsync",
                side_effect=fail_commit_and_retry,
            ):
                with self.assertRaisesRegex(OSError, "summary parent sync failure"):
                    analysis._atomic_write_no_replace(output, payload)
            self.assertFalse(output.exists())

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "summary.json"
            call_count = 0
            original_unlink = analysis._unlink_if_identity

            def fail_every_parent_sync(descriptor: int) -> None:
                nonlocal call_count
                call_count += 1
                if call_count >= 2:
                    raise OSError("persistent summary parent sync failure")
                original_fsync(descriptor)

            def refuse_summary_rollback(
                directory_fd: int,
                filename: str,
                identity: tuple[int, int],
            ) -> bool:
                if filename == output.name:
                    raise OSError("summary rollback failure")
                return original_unlink(directory_fd, filename, identity)

            with (
                patch.object(
                    analysis.os,
                    "fsync",
                    side_effect=fail_every_parent_sync,
                ),
                patch.object(
                    analysis,
                    "_unlink_if_identity",
                    side_effect=refuse_summary_rollback,
                ),
            ):
                with self.assertRaisesRegex(
                    analysis.DiagnosticAnalysisPublicationAmbiguousError,
                    "must not be used",
                ):
                    analysis._atomic_write_no_replace(output, payload)
            self.assertEqual(output.read_bytes(), payload)

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
