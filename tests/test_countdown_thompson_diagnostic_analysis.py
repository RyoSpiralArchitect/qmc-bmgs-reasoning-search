from __future__ import annotations

import math
import os
import stat
import tempfile
import time
import unittest
from copy import deepcopy
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
from typing import Callable
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


def _write_synthetic_bundle_members(
    directory: Path,
    marker: bytes = b"synthetic-bundle",
) -> analysis._BundleReceipt:
    directory.mkdir(parents=True, exist_ok=True)
    receipt: list[tuple[str, int, str]] = []
    for filename in analysis.BUNDLE_FILENAMES:
        payload = marker + b":" + filename.encode("ascii") + b"\n"
        (directory / filename).write_bytes(payload)
        receipt.append((filename, len(payload), analysis._sha256_bytes(payload)))
    return tuple(receipt)


def _write_synthetic_committed_attempt(
    historical_artifact: Path,
) -> tuple[dict[str, object], Path, analysis._AttemptStateReceipt]:
    authorization_digest = "a" * 64
    artifact_id = historical_artifact.name
    marker = f".{artifact_id}.attempt-{authorization_digest}"
    attempt = historical_artifact.parent / marker
    staging = attempt / "staging"
    started_core: dict[str, object] = {
        "artifact_id": artifact_id,
        "authorization_digest": authorization_digest,
        "authorized_output_path": str(historical_artifact),
        "diagnostic_seal_digest": "b" * 64,
        "execution_head_revision": "c" * 40,
        "phase": "STARTED",
        "reviewed_authorization_revision": "d" * 40,
        "runner_build_digest": "e" * 64,
        "schema_version": ("qmc-bmgs-countdown-thompson-diagnostic-attempt-marker/v1"),
        "search_build_digest": "f" * 64,
        "staging_path": str(staging),
        "status": "PENDING",
    }
    started = {
        **started_core,
        "deterministic_digest": analysis._stdlib_sha256_json(started_core),
    }
    manifest: dict[str, object] = {
        "artifact_id": artifact_id,
        "attempt_marker_basename": marker,
        "attempt_started_receipt": started,
        "attempt_started_receipt_digest": started["deterministic_digest"],
        "authorized_output_path": str(historical_artifact),
        "deterministic_digest": "1" * 64,
        "execution_authorization_digest": authorization_digest,
    }
    payloads = analysis._expected_committed_attempt_payloads(manifest)
    attempt.mkdir(parents=True, exist_ok=True)
    snapshot: dict[str, bytes] = {}
    for filename in analysis._COMMITTED_ATTEMPT_FILENAMES:
        raw = analysis._canonical_bytes(payloads[filename])
        (attempt / filename).write_bytes(raw)
        snapshot[filename] = raw
    receipt = tuple(
        (filename, len(snapshot[filename]), analysis._sha256_bytes(snapshot[filename]))
        for filename in analysis._COMMITTED_ATTEMPT_FILENAMES
    )
    return manifest, attempt, receipt


def _synthetic_validated_authority(
    historical_artifact: Path,
    artifact_receipt: analysis._ArtifactReceipt = (),
) -> SimpleNamespace:
    manifest, attempt, attempt_receipt = _write_synthetic_committed_attempt(
        historical_artifact
    )
    attempt_authority = analysis._pin_protected_roots((attempt,))[0]
    return SimpleNamespace(
        manifest=manifest,
        artifact_receipt=artifact_receipt,
        historical_attempt_path=attempt,
        attempt_state_receipt=attempt_receipt,
        historical_attempt_authority=attempt_authority,
    )


def _owned_synthetic_validation(
    validated: SimpleNamespace,
) -> Callable[..., SimpleNamespace]:
    enrolled = False

    def validate(*_args: object, **kwargs: object) -> SimpleNamespace:
        nonlocal enrolled
        owner = kwargs.get("attempt_authority_owner")
        if not isinstance(owner, analysis.ExitStack):
            raise AssertionError("synthetic retained attempt requires an owner")
        if enrolled:
            raise AssertionError("synthetic attempt authority was enrolled twice")
        owner.callback(
            analysis._close_pinned_protected_roots,
            (validated.historical_attempt_authority,),
        )
        enrolled = True
        return validated

    return validate


def _mutate_file_preserving_size(path: Path) -> None:
    payload = path.read_bytes()
    if not payload:
        raise AssertionError("synthetic mutation requires non-empty bytes")
    path.write_bytes(bytes((payload[0] ^ 1,)) + payload[1:])


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
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._original_tempdir = tempfile.tempdir
        # Summary publication intentionally rejects raw symlink ancestry.  Use
        # the canonical host temp namespace so macOS /var and /tmp aliases do
        # not turn unrelated synthetic tests into symlink-path tests.
        tempfile.tempdir = os.fspath(Path(tempfile.gettempdir()).resolve())

    @classmethod
    def tearDownClass(cls) -> None:
        tempfile.tempdir = cls._original_tempdir
        super().tearDownClass()

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
        self.assertEqual(len(analysis._RUNNER_SOURCE_PATHS), 6)
        self.assertEqual(len(analysis._CURRENT_REPLAY_MODULE_PATHS), 14)
        self.assertIn(
            "qmc_bmgs.experiments.countdown_track_a_canary_manifest",
            analysis._CURRENT_REPLAY_MODULE_PATHS,
        )
        self.assertIn(
            "qmc_bmgs.experiments.countdown_thompson_regular_file_publication_v2",
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

    def test_reviewed_authorization_rejects_oversize_before_open(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            authorization = Path(directory) / "authorization.json"
            with authorization.open("wb") as handle:
                handle.truncate(analysis._REVIEWED_AUTHORIZATION_BYTE_CAP_V1 + 1)

            with (
                patch.object(
                    analysis.os,
                    "open",
                    side_effect=AssertionError("oversize authorization was opened"),
                ),
                self.assertRaisesRegex(
                    analysis.DiagnosticAnalysisError,
                    "v1 byte cap",
                ),
            ):
                analysis._reviewed_authorization(authorization, "a" * 64)

    def test_reviewed_authorization_rejects_growth_during_bounded_read(
        self,
    ) -> None:
        raw = analysis._canonical_bytes({"deterministic_digest": "a" * 64})
        original_read = analysis.os.read
        with tempfile.TemporaryDirectory() as directory:
            authorization = Path(directory) / "authorization.json"
            authorization.write_bytes(raw)
            grew = False

            def grow_after_first_read(descriptor: int, byte_count: int) -> bytes:
                nonlocal grew
                observed = original_read(descriptor, byte_count)
                if not grew and byte_count > 1:
                    with authorization.open("ab") as handle:
                        handle.write(b"x")
                    grew = True
                return observed

            with (
                patch.object(analysis.os, "read", side_effect=grow_after_first_read),
                self.assertRaisesRegex(
                    analysis.DiagnosticAnalysisError,
                    "grew beyond its declared byte size",
                ),
            ):
                analysis._reviewed_authorization(authorization, "a" * 64)
            self.assertTrue(grew)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX FIFO required")
    def test_reviewed_authorization_rejects_regular_to_fifo_race_without_blocking(
        self,
    ) -> None:
        raw = analysis._canonical_bytes({"deterministic_digest": "a" * 64})
        original_open = analysis.os.open
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            authorization = root / "authorization.json"
            authorization.write_bytes(raw)
            fifo = root / "authorization-fifo"
            os.mkfifo(fifo)

            def open_fifo_after_regular_stat(
                path: object,
                flags: int,
                *args: object,
                **kwargs: object,
            ) -> int:
                if path == authorization:
                    self.assertTrue(flags & os.O_NOFOLLOW)
                    self.assertTrue(flags & os.O_NONBLOCK)
                    return original_open(fifo, flags, *args, **kwargs)
                return original_open(path, flags, *args, **kwargs)

            started = time.monotonic()
            with (
                patch.object(
                    analysis.os,
                    "open",
                    side_effect=open_fifo_after_regular_stat,
                ),
                self.assertRaisesRegex(
                    analysis.DiagnosticAnalysisError,
                    "changed before descriptor acquisition",
                ),
            ):
                analysis._reviewed_authorization(authorization, "a" * 64)
            self.assertLess(time.monotonic() - started, 1.0)

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

    def test_summary_publication_rejects_symlinked_raw_parent(self) -> None:
        payload = analysis._canonical_bytes(
            {"schema_version": "synthetic/v1", "status": "PASS"}
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real_parent = root / "real-parent"
            real_parent.mkdir()
            raw_parent = root / "raw-parent"
            raw_parent.symlink_to(real_parent, target_is_directory=True)
            output = raw_parent / "summary.json"

            with self.assertRaisesRegex(
                analysis.DiagnosticAnalysisError,
                "stable directory",
            ):
                analysis._atomic_write_no_replace(output, payload)
            self.assertFalse((real_parent / output.name).exists())

    def test_summary_ancestor_pivot_cannot_complete_in_another_raw_namespace(
        self,
    ) -> None:
        payload = analysis._canonical_bytes(
            {"schema_version": "synthetic/v1", "status": "PASS"}
        )
        original_open = analysis._open_stable_directory_with_ancestry
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_ancestor = root / "raw-ancestor"
            raw_parent = raw_ancestor / "parent"
            raw_parent.mkdir(parents=True)
            displaced = root / "displaced-ancestor"
            alternate = root / "alternate-ancestor"
            (alternate / "parent").mkdir(parents=True)
            output = raw_parent / "summary.json"
            pivoted = False

            def pivot_after_raw_parent_open(path: Path, label: str):
                nonlocal pivoted
                opened = original_open(path, label)
                if label == "summary parent" and not pivoted:
                    raw_ancestor.rename(displaced)
                    raw_ancestor.symlink_to(alternate, target_is_directory=True)
                    pivoted = True
                return opened

            with (
                patch.object(
                    analysis,
                    "_open_stable_directory_with_ancestry",
                    side_effect=pivot_after_raw_parent_open,
                ),
                self.assertRaises(analysis.DiagnosticAnalysisError),
            ):
                analysis._atomic_write_no_replace(output, payload)
            self.assertTrue(pivoted)
            self.assertFalse((alternate / "parent" / output.name).exists())
            self.assertFalse((displaced / "parent" / output.name).exists())

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

    def test_committed_attempt_namespace_and_member_boundaries_fail_closed(
        self,
    ) -> None:
        cases = (
            ("directory_symlink", "stable non-symlink directory"),
            ("member_symlink", "member is not regular"),
            ("member_fifo", "member is not regular"),
            ("oversize", "v1 byte cap"),
            ("extra_terminal", "directory closure drifted"),
            ("missing_receipt", "directory closure drifted"),
        )
        for case, message in cases:
            if case == "member_fifo" and not hasattr(os, "mkfifo"):
                continue
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                historical = root / "artifact"
                historical.mkdir()
                manifest, attempt, _receipt = _write_synthetic_committed_attempt(
                    historical
                )
                if case == "directory_symlink":
                    displaced = root / "displaced-attempt"
                    attempt.rename(displaced)
                    attempt.symlink_to(displaced, target_is_directory=True)
                elif case == "member_symlink":
                    member = attempt / "started.json"
                    target = root / "foreign-started.json"
                    target.write_bytes(member.read_bytes())
                    member.unlink()
                    member.symlink_to(target)
                elif case == "member_fifo":
                    member = attempt / "started.json"
                    member.unlink()
                    os.mkfifo(member)
                elif case == "oversize":
                    with (attempt / "ready_to_commit.json").open("r+b") as handle:
                        handle.truncate(analysis._ATTEMPT_RECEIPT_BYTE_CAP_V1 + 1)
                elif case == "extra_terminal":
                    (attempt / "invalid.json").write_bytes(b"{}\n")
                else:
                    (attempt / "ready_to_commit.json").unlink()

                started = time.monotonic()
                with self.assertRaisesRegex(
                    analysis.DiagnosticAnalysisError,
                    message,
                ):
                    analysis._read_historical_attempt_state(attempt, manifest)
                if case == "member_fifo":
                    self.assertLess(time.monotonic() - started, 1.0)

    def test_committed_attempt_growth_is_bounded_and_rejected(self) -> None:
        original_read = analysis.os.read
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            historical = root / "artifact"
            historical.mkdir()
            manifest, attempt, _receipt = _write_synthetic_committed_attempt(historical)
            target = attempt / "started.json"
            target_stat = target.stat()
            target_identity = (target_stat.st_dev, target_stat.st_ino)
            grew = False

            def grow_after_target_read(descriptor: int, byte_count: int) -> bytes:
                nonlocal grew
                chunk = original_read(descriptor, byte_count)
                opened = analysis.os.fstat(descriptor)
                if (
                    not grew
                    and chunk
                    and (opened.st_dev, opened.st_ino) == target_identity
                ):
                    with target.open("ab") as handle:
                        handle.write(b"x")
                    grew = True
                return chunk

            with (
                patch.object(
                    analysis.os,
                    "read",
                    side_effect=grow_after_target_read,
                ),
                self.assertRaisesRegex(
                    analysis.DiagnosticAnalysisError,
                    "grew beyond its declared byte size",
                ),
            ):
                analysis._read_historical_attempt_state(attempt, manifest)
            self.assertTrue(grew)

    def test_deeply_nested_attempt_receipt_is_typed_invalid_without_parsing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            historical = root / "artifact"
            historical.mkdir()
            manifest, attempt, _receipt = _write_synthetic_committed_attempt(historical)
            nesting = 10_000
            malicious = (
                b'{"unexpected":' + (b"[" * nesting) + b"0" + (b"]" * nesting) + b"}\n"
            )
            self.assertLess(
                len(malicious),
                analysis._ATTEMPT_RECEIPT_BYTE_CAP_V1,
            )
            (attempt / "pre_outcome.json").write_bytes(malicious)

            with self.assertRaises(
                analysis.DiagnosticAnalysisError,
            ) as raised:
                analysis._read_historical_attempt_state(attempt, manifest)
            self.assertIs(type(raised.exception), analysis.DiagnosticAnalysisError)
            self.assertIn(
                "receipt does not close: pre_outcome.json",
                str(raised.exception),
            )

    def test_committed_attempt_receipts_are_derived_from_embedded_started(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            historical = root / "artifact"
            historical.mkdir()
            manifest, attempt, _receipt = _write_synthetic_committed_attempt(historical)
            ready_path = attempt / "ready_to_commit.json"
            ready = analysis._strict_json_object(
                ready_path.read_bytes(),
                "synthetic ready receipt",
            )
            ready["run_manifest_digest"] = "9" * 64
            ready_core = {
                key: value
                for key, value in ready.items()
                if key != "deterministic_digest"
            }
            ready["deterministic_digest"] = analysis._stdlib_sha256_json(ready_core)
            ready_path.write_bytes(analysis._canonical_bytes(ready))

            with self.assertRaisesRegex(
                analysis.DiagnosticAnalysisError,
                "receipt does not close: ready_to_commit.json",
            ):
                analysis._read_historical_attempt_state(attempt, manifest)

    def test_bundle_receipt_is_bounded_and_requires_exact_closure(self) -> None:
        for case in ("exact", "extra", "oversize"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                bundle = Path(directory) / "bundle"
                expected = _write_synthetic_bundle_members(bundle)
                if case == "extra":
                    (bundle / "foreign.json").write_bytes(b"{}\n")
                elif case == "oversize":
                    with (bundle / analysis.BUNDLE_FILENAMES[0]).open("r+b") as handle:
                        handle.truncate(analysis._BUNDLE_MEMBER_BYTE_CAP_V1 + 1)
                pinned = analysis._pin_protected_roots((bundle,))
                try:
                    if case == "exact":
                        self.assertEqual(
                            analysis._read_bundle_receipt_from_descriptor(
                                pinned[0].descriptor,
                                "synthetic bundle",
                                expected,
                            ),
                            expected,
                        )
                    else:
                        with self.assertRaises(analysis.DiagnosticAnalysisError):
                            analysis._read_bundle_receipt_from_descriptor(
                                pinned[0].descriptor,
                                "synthetic bundle",
                            )
                finally:
                    analysis._close_pinned_protected_roots(pinned)

    def test_public_analyze_rejects_attempt_terminal_injected_during_build(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "artifact"
            artifact_receipt = _write_synthetic_artifact_members(
                artifact,
                b"validated-artifact",
            )
            bundle = root / "bundle"
            _write_synthetic_bundle_members(bundle)
            historical = root / "historical-artifact"
            historical.mkdir()
            validated = _synthetic_validated_authority(
                historical,
                artifact_receipt,
            )
            attempt = validated.historical_attempt_path
            attempt_descriptor = validated.historical_attempt_authority.descriptor
            injected = False

            def build_then_inject(_validated: object) -> dict[str, str]:
                nonlocal injected
                (attempt / "invalid.json").write_bytes(b"{}\n")
                injected = True
                return {"schema_version": "synthetic/v1", "status": "PASS"}

            with (
                patch.object(
                    analysis,
                    "_validate_artifact",
                    side_effect=_owned_synthetic_validation(validated),
                ) as validate,
                patch.object(
                    analysis,
                    "_build_summary",
                    side_effect=build_then_inject,
                ),
                self.assertRaisesRegex(
                    analysis.DiagnosticAnalysisError,
                    "attempt directory closure drifted",
                ),
            ):
                analysis.analyze_countdown_thompson_diagnostic_artifact(
                    artifact,
                    bundle,
                    root / "authorization.json",
                    "0" * 64,
                    repository_root=root,
                )
            self.assertTrue(injected)
            validate.assert_called_once()
            with self.assertRaises(OSError):
                os.fstat(attempt_descriptor)

    def test_public_analyze_rejects_artifact_drift_during_build(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "artifact"
            artifact_receipt = _write_synthetic_artifact_members(
                artifact,
                b"validated-artifact",
            )
            bundle = root / "bundle"
            _write_synthetic_bundle_members(bundle)
            historical = root / "historical-artifact"
            historical.mkdir()
            validated = _synthetic_validated_authority(
                historical,
                artifact_receipt,
            )
            attempt_descriptor = validated.historical_attempt_authority.descriptor
            records = artifact / "records.jsonl"
            drifted = False

            def build_then_drift(_validated: object) -> dict[str, str]:
                nonlocal drifted
                _mutate_file_preserving_size(records)
                drifted = True
                return {"schema_version": "synthetic/v1", "status": "PASS"}

            with (
                patch.object(
                    analysis,
                    "_validate_artifact",
                    side_effect=_owned_synthetic_validation(validated),
                ) as validate,
                patch.object(
                    analysis,
                    "_build_summary",
                    side_effect=build_then_drift,
                ),
                self.assertRaisesRegex(
                    analysis.DiagnosticAnalysisError,
                    "bytes differ from the validated runner artifact",
                ),
            ):
                analysis.analyze_countdown_thompson_diagnostic_artifact(
                    artifact,
                    bundle,
                    root / "authorization.json",
                    "0" * 64,
                    repository_root=root,
                )
            self.assertTrue(drifted)
            validate.assert_called_once()
            with self.assertRaises(OSError):
                os.fstat(attempt_descriptor)

    def test_public_analyze_rechecks_artifact_after_final_attempt_proof(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "artifact"
            artifact_receipt = _write_synthetic_artifact_members(
                artifact,
                b"validated-artifact",
            )
            bundle = root / "bundle"
            _write_synthetic_bundle_members(bundle)
            historical = root / "historical-artifact"
            historical.mkdir()
            validated = _synthetic_validated_authority(
                historical,
                artifact_receipt,
            )
            attempt_descriptor = validated.historical_attempt_authority.descriptor
            original_revalidate = analysis._revalidate_attempt_authority_after_topology
            records = artifact / "records.jsonl"
            drifted = False

            def revalidate_then_drift(*args: object, **kwargs: object) -> None:
                nonlocal drifted
                original_revalidate(*args, **kwargs)
                _mutate_file_preserving_size(records)
                drifted = True

            with (
                patch.object(
                    analysis,
                    "_validate_artifact",
                    side_effect=_owned_synthetic_validation(validated),
                ),
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
                    "_revalidate_attempt_authority_after_topology",
                    side_effect=revalidate_then_drift,
                ),
                self.assertRaisesRegex(
                    analysis.DiagnosticAnalysisError,
                    "authorities changed during collective proof",
                ),
            ):
                analysis.analyze_countdown_thompson_diagnostic_artifact(
                    artifact,
                    bundle,
                    root / "authorization.json",
                    "0" * 64,
                    repository_root=root,
                )
            self.assertTrue(drifted)
            with self.assertRaises(OSError):
                os.fstat(attempt_descriptor)

    def test_public_analyze_rejects_rotating_authority_generations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "artifact"
            artifact_receipt = _write_synthetic_artifact_members(
                artifact,
                b"validated-artifact",
            )
            bundle = root / "bundle"
            _write_synthetic_bundle_members(bundle)
            historical = root / "historical-artifact"
            historical.mkdir()
            validated = _synthetic_validated_authority(
                historical,
                artifact_receipt,
            )
            attempt = validated.historical_attempt_path
            attempt_member = attempt / "ready_to_commit.json"
            artifact_member = artifact / "records.jsonl"
            original_attempt = attempt_member.read_bytes()
            original_artifact = artifact_member.read_bytes()
            original_revalidate = analysis._revalidate_attempt_authority_after_topology

            def build_with_attempt_invalid(_validated: object) -> dict[str, str]:
                _mutate_file_preserving_size(attempt_member)
                return {"schema_version": "synthetic/v1", "status": "PASS"}

            def rotate_during_attempt_proof(
                *args: object,
                **kwargs: object,
            ) -> None:
                _mutate_file_preserving_size(artifact_member)
                _mutate_file_preserving_size(attempt_member)
                original_revalidate(*args, **kwargs)
                _mutate_file_preserving_size(artifact_member)
                _mutate_file_preserving_size(attempt_member)

            with (
                patch.object(
                    analysis,
                    "_validate_artifact",
                    side_effect=_owned_synthetic_validation(validated),
                ),
                patch.object(
                    analysis,
                    "_build_summary",
                    side_effect=build_with_attempt_invalid,
                ),
                patch.object(
                    analysis,
                    "_revalidate_attempt_authority_after_topology",
                    side_effect=rotate_during_attempt_proof,
                ),
                self.assertRaisesRegex(
                    analysis.DiagnosticAnalysisError,
                    "authorities changed during collective proof",
                ),
            ):
                analysis.analyze_countdown_thompson_diagnostic_artifact(
                    artifact,
                    bundle,
                    root / "authorization.json",
                    "0" * 64,
                    repository_root=root,
                )
            self.assertEqual(artifact_member.read_bytes(), original_artifact)
            self.assertNotEqual(attempt_member.read_bytes(), original_attempt)

    def test_public_analyze_rejects_bundle_swap_restored_after_validation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "artifact"
            artifact_receipt = _write_synthetic_artifact_members(
                artifact,
                b"validated-artifact",
            )
            bundle = root / "bundle"
            original_bundle_receipt = _write_synthetic_bundle_members(bundle)
            historical = root / "historical-artifact"
            historical.mkdir()
            validated = _synthetic_validated_authority(
                historical,
                artifact_receipt,
            )
            owned_validation = _owned_synthetic_validation(validated)
            displaced = root / "bundle.original"
            replacement = root / "bundle.replacement"
            swapped = False

            def validate_with_restored_swap(
                *args: object,
                **kwargs: object,
            ) -> object:
                nonlocal swapped
                bundle.rename(displaced)
                _write_synthetic_bundle_members(bundle, b"replacement-bundle")
                bundle.rename(replacement)
                displaced.rename(bundle)
                swapped = True
                return owned_validation(*args, **kwargs)

            with (
                patch.object(
                    analysis,
                    "_validate_artifact",
                    side_effect=validate_with_restored_swap,
                ) as validate,
                patch.object(
                    analysis,
                    "_build_summary",
                    return_value={
                        "schema_version": "synthetic/v1",
                        "status": "PASS",
                    },
                ),
                self.assertRaisesRegex(
                    analysis.DiagnosticAnalysisError,
                    "source authority generation changed after validation: "
                    "diagnostic bundle",
                ),
            ):
                analysis.analyze_countdown_thompson_diagnostic_artifact(
                    artifact,
                    bundle,
                    root / "authorization.json",
                    "0" * 64,
                    repository_root=root,
                )
            self.assertTrue(swapped)
            validate.assert_called_once()
            pinned = analysis._pin_protected_roots((bundle,))
            try:
                self.assertEqual(
                    analysis._read_bundle_receipt_from_descriptor(
                        pinned[0].descriptor,
                        "restored synthetic bundle",
                    ),
                    original_bundle_receipt,
                )
            finally:
                analysis._close_pinned_protected_roots(pinned)
            self.assertTrue(replacement.is_dir())

    def _exercise_final_receipt_pass_replacement(self, target_label: str) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "relocated-artifact"
            artifact_receipt = _write_synthetic_artifact_members(
                artifact,
                b"identical-artifact",
            )
            historical = root / "historical-artifact"
            self.assertEqual(
                _write_synthetic_artifact_members(
                    historical,
                    b"identical-artifact",
                ),
                artifact_receipt,
            )
            bundle = root / "bundle"
            _write_synthetic_bundle_members(bundle)
            publication_parent = root / "publication-parent"
            publication_parent.mkdir()
            output = publication_parent / "summary.json"
            summary = {"schema_version": "synthetic/v1", "status": "PASS"}
            target = historical if target_label.startswith("historical") else artifact
            records = target / "records.jsonl"
            displaced = target / "records.original"
            foreign = b"X" * len(records.read_bytes())
            original_closure = analysis._assert_artifact_directory_closure
            target_closure_count = 0
            replacement_completed = False

            def replace_after_final_closure(
                directory_fd: int,
                label: str,
            ) -> None:
                nonlocal replacement_completed, target_closure_count
                original_closure(directory_fd, label)
                if label == target_label:
                    target_closure_count += 1
                    if target_closure_count == 8:
                        records.rename(displaced)
                        records.write_bytes(foreign)
                        replacement_completed = True

            with (
                patch.object(
                    analysis,
                    "_validate_artifact",
                    side_effect=_owned_synthetic_validation(
                        _synthetic_validated_authority(
                            historical,
                            artifact_receipt,
                        )
                    ),
                ),
                patch.object(analysis, "_build_summary", return_value=summary),
                patch.object(
                    analysis,
                    "_assert_artifact_directory_closure",
                    side_effect=replace_after_final_closure,
                ),
            ):
                with self.assertRaises(analysis.DiagnosticAnalysisError) as raised:
                    analysis.write_countdown_thompson_diagnostic_summary(
                        artifact,
                        bundle,
                        root / "authorization.json",
                        "0" * 64,
                        output,
                        repository_root=root,
                    )
                self.assertIs(type(raised.exception), analysis.DiagnosticAnalysisError)
            self.assertTrue(replacement_completed)
            self.assertEqual(target_closure_count, 8)
            self.assertEqual(records.read_bytes(), foreign)
            self.assertTrue(displaced.is_file())
            self.assertFalse(output.exists())
            quarantines = tuple(
                path
                for path in publication_parent.iterdir()
                if path.name.startswith(".summary.json.rollback-")
            )
            self.assertEqual(len(quarantines), 1)
            self.assertEqual(
                quarantines[0].read_bytes(),
                analysis._canonical_bytes(summary),
            )

    def test_historical_final_receipt_pass_replacement_revokes_summary(self) -> None:
        self._exercise_final_receipt_pass_replacement(
            "historical committed artifact",
        )

    def test_relocated_final_receipt_pass_replacement_revokes_summary(self) -> None:
        self._exercise_final_receipt_pass_replacement(
            "relocated validated artifact",
        )

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
                        "stable directory|cannot modify",
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
                        "protected|path identity changed",
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
            _write_synthetic_bundle_members(bundle)
            safe = root / "safe"
            (safe / "out").mkdir(parents=True)
            displaced_safe = root / "displaced-safe"
            output = safe / "out" / "summary.json"
            swapped = False
            validation_completed = False
            validated = _synthetic_validated_authority(protected.resolve())
            owned_validation = _owned_synthetic_validation(validated)

            def validate_then_mark(*args: object, **kwargs: object) -> object:
                nonlocal validation_completed
                result = owned_validation(*args, **kwargs)
                validation_completed = True
                return result

            def swap_before_revalidation(path: Path, label: str):
                nonlocal swapped
                if (
                    label == "protected root 0 after pinning"
                    and validation_completed
                    and not swapped
                ):
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
                    side_effect=validate_then_mark,
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
            _write_synthetic_bundle_members(bundle)
            output = historical / "summary.json"
            validated = _synthetic_validated_authority(historical.resolve())

            with (
                patch.object(
                    analysis,
                    "_validate_artifact",
                    side_effect=_owned_synthetic_validation(validated),
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
            _write_synthetic_bundle_members(bundle)
            publication_parent = root / "publication-parent"
            publication_parent.mkdir()
            output = publication_parent / "summary.json"
            validated = _synthetic_validated_authority(historical)

            with (
                patch.object(
                    analysis,
                    "_validate_artifact",
                    side_effect=_owned_synthetic_validation(validated),
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
                _write_synthetic_bundle_members(bundle)
                publication_parent = root / "publication-parent"
                publication_parent.mkdir()
                output = publication_parent / "summary.json"

                with (
                    patch.object(
                        analysis,
                        "_validate_artifact",
                        side_effect=_owned_synthetic_validation(
                            _synthetic_validated_authority(
                                historical,
                                artifact_receipt,
                            )
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
            _write_synthetic_bundle_members(bundle)
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
                    side_effect=_owned_synthetic_validation(
                        _synthetic_validated_authority(
                            historical,
                            artifact_receipt,
                        )
                    ),
                ),
                patch.object(
                    analysis,
                    "_build_summary",
                    return_value=summary,
                ),
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
            self.assertEqual(output.read_bytes(), analysis._canonical_bytes(summary))

    def test_source_path_ancestor_summary_parent_is_rejected_before_write(
        self,
    ) -> None:
        for case in ("canonical-sibling", "raw-alias-parent"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                real_parent = root / "real-source-parent"
                artifact = real_parent / "relocated-artifact"
                artifact_receipt = _write_synthetic_artifact_members(
                    artifact,
                    b"identical-artifact",
                )
                historical = root / "historical-parent" / "historical-artifact"
                self.assertEqual(
                    _write_synthetic_artifact_members(
                        historical,
                        b"identical-artifact",
                    ),
                    artifact_receipt,
                )
                bundle = root / "bundle-parent" / "bundle"
                _write_synthetic_bundle_members(bundle)
                if case == "canonical-sibling":
                    artifact_argument = artifact
                    publication_parent = real_parent
                else:
                    publication_parent = root / "raw-alias-parent"
                    publication_parent.mkdir()
                    source_alias = publication_parent / "source-alias"
                    source_alias.symlink_to(real_parent, target_is_directory=True)
                    artifact_argument = source_alias / artifact.name
                output = publication_parent / "summary.json"
                before_entries = tuple(
                    sorted(path.name for path in publication_parent.iterdir())
                )

                with (
                    patch.object(
                        analysis,
                        "_validate_artifact",
                        side_effect=_owned_synthetic_validation(
                            _synthetic_validated_authority(
                                historical,
                                artifact_receipt,
                            )
                        ),
                    ),
                    patch.object(
                        analysis,
                        "_build_summary",
                        return_value={
                            "schema_version": "synthetic/v1",
                            "status": "PASS",
                        },
                    ),
                    self.assertRaisesRegex(
                        analysis.DiagnosticAnalysisError,
                        "summary parent is a protected source-path ancestor",
                    ),
                ):
                    analysis.write_countdown_thompson_diagnostic_summary(
                        artifact_argument,
                        bundle,
                        root / "authorization.json",
                        "0" * 64,
                        output,
                        repository_root=root,
                    )

                self.assertFalse(output.exists())
                self.assertEqual(
                    tuple(sorted(path.name for path in publication_parent.iterdir())),
                    before_entries,
                )

    def test_durable_summary_rejects_bundle_mutation_before_final_check(
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
            self.assertEqual(
                _write_synthetic_artifact_members(
                    historical,
                    b"identical-artifact",
                ),
                artifact_receipt,
            )
            bundle = root / "bundle"
            _write_synthetic_bundle_members(bundle)
            bundle_member = bundle / "analysis.json"
            publication_parent = root / "publication-parent"
            publication_parent.mkdir()
            output = publication_parent / "summary.json"
            mutated = False

            def mutate_before_final_check(
                _path: Path,
                _payload: bytes,
                *,
                protected_roots: tuple[analysis._PinnedProtectedRoot, ...],
                post_durability_check: object,
            ) -> None:
                nonlocal mutated
                self.assertTrue(callable(post_durability_check))
                analysis._assert_pinned_protected_roots(protected_roots)
                _mutate_file_preserving_size(bundle_member)
                mutated = True
                post_durability_check()  # type: ignore[operator]

            with (
                patch.object(
                    analysis,
                    "_validate_artifact",
                    side_effect=_owned_synthetic_validation(
                        _synthetic_validated_authority(
                            historical,
                            artifact_receipt,
                        )
                    ),
                ),
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
                    side_effect=mutate_before_final_check,
                ) as atomic_write,
                self.assertRaisesRegex(
                    analysis.DiagnosticAnalysisError,
                    "source authority generation changed after validation: "
                    "diagnostic bundle",
                ),
            ):
                analysis.write_countdown_thompson_diagnostic_summary(
                    artifact,
                    bundle,
                    root / "authorization.json",
                    "0" * 64,
                    output,
                    repository_root=root,
                )
            self.assertTrue(mutated)
            atomic_write.assert_called_once()
            self.assertFalse(output.exists())

    def test_byte_identical_attempt_directory_replacement_after_validation_is_rejected(
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
            self.assertEqual(
                _write_synthetic_artifact_members(
                    historical,
                    b"identical-artifact",
                ),
                artifact_receipt,
            )
            validated = _synthetic_validated_authority(
                historical,
                artifact_receipt,
            )
            attempt = validated.historical_attempt_path
            displaced = root / "displaced-attempt"
            bundle = root / "bundle"
            _write_synthetic_bundle_members(bundle)
            publication_parent = root / "publication-parent"
            publication_parent.mkdir()
            output = publication_parent / "summary.json"
            replaced = False

            def replace_with_byte_identical_attempt(
                _validated: object,
            ) -> dict[str, str]:
                nonlocal replaced
                attempt.rename(displaced)
                attempt.mkdir()
                for filename in analysis._COMMITTED_ATTEMPT_FILENAMES:
                    (attempt / filename).write_bytes(
                        (displaced / filename).read_bytes()
                    )
                replaced = True
                return {"schema_version": "synthetic/v1", "status": "PASS"}

            with (
                patch.object(
                    analysis,
                    "_validate_artifact",
                    side_effect=_owned_synthetic_validation(validated),
                ),
                patch.object(
                    analysis,
                    "_build_summary",
                    side_effect=replace_with_byte_identical_attempt,
                ),
                patch.object(analysis, "_atomic_write_no_replace") as atomic_write,
            ):
                with self.assertRaisesRegex(
                    analysis.DiagnosticAnalysisError,
                    "path identity changed",
                ):
                    analysis.write_countdown_thompson_diagnostic_summary(
                        artifact,
                        bundle,
                        root / "authorization.json",
                        "0" * 64,
                        output,
                        repository_root=root,
                    )
            self.assertTrue(replaced)
            self.assertEqual(
                tuple(
                    (attempt / name).read_bytes()
                    for name in analysis._COMMITTED_ATTEMPT_FILENAMES
                ),
                tuple(
                    (displaced / name).read_bytes()
                    for name in analysis._COMMITTED_ATTEMPT_FILENAMES
                ),
            )
            atomic_write.assert_not_called()
            self.assertFalse(output.exists())

    def test_final_attempt_read_cannot_hide_byte_identical_raw_path_swap(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            historical = root / "historical-artifact"
            historical.mkdir()
            _manifest, attempt, receipt = _write_synthetic_committed_attempt(historical)
            displaced = root / "displaced-attempt"
            pinned = analysis._pin_protected_roots((attempt,))
            original_read_once = analysis._read_attempt_state_once_from_descriptor
            read_count = 0
            swapped = False

            def swap_after_final_read(
                directory_fd: int,
                label: str,
            ) -> tuple[dict[str, bytes], analysis._AttemptStateReceipt]:
                nonlocal read_count, swapped
                observed = original_read_once(directory_fd, label)
                if directory_fd == pinned[0].descriptor:
                    read_count += 1
                    if read_count == 3:
                        attempt.rename(displaced)
                        attempt.mkdir()
                        for filename in analysis._COMMITTED_ATTEMPT_FILENAMES:
                            (attempt / filename).write_bytes(
                                (displaced / filename).read_bytes()
                            )
                        swapped = True
                return observed

            try:
                with (
                    patch.object(
                        analysis,
                        "_read_attempt_state_once_from_descriptor",
                        side_effect=swap_after_final_read,
                    ),
                    self.assertRaisesRegex(
                        analysis.DiagnosticAnalysisError,
                        "path identity changed",
                    ),
                ):
                    analysis._revalidate_attempt_authority_after_topology(
                        pinned[0],
                        receipt,
                        pinned,
                        "historical committed attempt",
                    )
            finally:
                analysis._close_pinned_protected_roots(pinned)
            self.assertTrue(swapped)
            self.assertEqual(read_count, 3)
            self.assertEqual(
                tuple(
                    (attempt / name).read_bytes()
                    for name in analysis._COMMITTED_ATTEMPT_FILENAMES
                ),
                tuple(
                    (displaced / name).read_bytes()
                    for name in analysis._COMMITTED_ATTEMPT_FILENAMES
                ),
            )

    def test_attempt_terminal_injection_before_publication_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "relocated-artifact"
            artifact_receipt = _write_synthetic_artifact_members(
                artifact,
                b"identical-artifact",
            )
            historical = root / "historical-artifact"
            self.assertEqual(
                _write_synthetic_artifact_members(
                    historical,
                    b"identical-artifact",
                ),
                artifact_receipt,
            )
            validated = _synthetic_validated_authority(
                historical,
                artifact_receipt,
            )
            attempt = validated.historical_attempt_path
            bundle = root / "bundle"
            _write_synthetic_bundle_members(bundle)
            publication_parent = root / "publication-parent"
            publication_parent.mkdir()
            output = publication_parent / "summary.json"
            original_read_attempt = analysis._read_attempt_state_receipt_from_descriptor
            injected = False

            def inject_terminal_before_attempt_receipt(*args: object, **kwargs: object):
                nonlocal injected
                if not injected:
                    (attempt / "invalid.json").write_bytes(b"{}\n")
                    injected = True
                return original_read_attempt(*args, **kwargs)

            with (
                patch.object(
                    analysis,
                    "_validate_artifact",
                    side_effect=_owned_synthetic_validation(validated),
                ),
                patch.object(
                    analysis,
                    "_build_summary",
                    return_value={"schema_version": "synthetic/v1", "status": "PASS"},
                ),
                patch.object(
                    analysis,
                    "_read_attempt_state_receipt_from_descriptor",
                    side_effect=inject_terminal_before_attempt_receipt,
                ),
                patch.object(analysis, "_atomic_write_no_replace") as atomic_write,
            ):
                with self.assertRaisesRegex(
                    analysis.DiagnosticAnalysisError,
                    "attempt directory closure drifted",
                ):
                    analysis.write_countdown_thompson_diagnostic_summary(
                        artifact,
                        bundle,
                        root / "authorization.json",
                        "0" * 64,
                        output,
                        repository_root=root,
                    )
            self.assertTrue(injected)
            atomic_write.assert_not_called()
            self.assertFalse(output.exists())

    def test_post_durability_attempt_injection_after_receipt_read_is_revoked(
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
            self.assertEqual(
                _write_synthetic_artifact_members(
                    historical,
                    b"identical-artifact",
                ),
                artifact_receipt,
            )
            validated = _synthetic_validated_authority(
                historical,
                artifact_receipt,
            )
            attempt = validated.historical_attempt_path
            bundle = root / "bundle"
            _write_synthetic_bundle_members(bundle)
            publication_parent = root / "publication-parent"
            publication_parent.mkdir()
            output = publication_parent / "summary.json"
            summary = {"schema_version": "synthetic/v1", "status": "PASS"}
            original_read_attempt = analysis._read_attempt_state_receipt_from_descriptor
            injected = False

            def inject_after_durable_receipt_read(
                *args: object,
                **kwargs: object,
            ) -> analysis._AttemptStateReceipt:
                nonlocal injected
                receipt = original_read_attempt(*args, **kwargs)
                if output.exists() and not injected:
                    (attempt / "invalid.json").write_bytes(b"{}\n")
                    injected = True
                return receipt

            with (
                patch.object(
                    analysis,
                    "_validate_artifact",
                    side_effect=_owned_synthetic_validation(validated),
                ),
                patch.object(analysis, "_build_summary", return_value=summary),
                patch.object(
                    analysis,
                    "_read_attempt_state_receipt_from_descriptor",
                    side_effect=inject_after_durable_receipt_read,
                ),
                self.assertRaises(analysis.DiagnosticAnalysisError) as raised,
            ):
                analysis.write_countdown_thompson_diagnostic_summary(
                    artifact,
                    bundle,
                    root / "authorization.json",
                    "0" * 64,
                    output,
                    repository_root=root,
                )
            self.assertIs(type(raised.exception), analysis.DiagnosticAnalysisError)
            self.assertIn(
                "mandatory summary post-durability check failed",
                str(raised.exception),
            )
            self.assertTrue(injected)
            self.assertFalse(output.exists())
            quarantines = tuple(
                path
                for path in publication_parent.iterdir()
                if path.name.startswith(".summary.json.rollback-")
            )
            self.assertEqual(len(quarantines), 1)
            self.assertEqual(
                quarantines[0].read_bytes(),
                analysis._canonical_bytes(summary),
            )

    def test_final_summary_proof_is_followed_by_attempt_authority_recheck(
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
            self.assertEqual(
                _write_synthetic_artifact_members(
                    historical,
                    b"identical-artifact",
                ),
                artifact_receipt,
            )
            validated = _synthetic_validated_authority(
                historical,
                artifact_receipt,
            )
            attempt = validated.historical_attempt_path
            bundle = root / "bundle"
            _write_synthetic_bundle_members(bundle)
            publication_parent = root / "publication-parent"
            publication_parent.mkdir()
            output = publication_parent / "summary.json"
            summary = {"schema_version": "synthetic/v1", "status": "PASS"}
            original_summary_exact = analysis._summary_publication_is_exact
            exact_observations = 0
            injected = False

            def inject_after_final_summary_proof(*args: object) -> bool:
                nonlocal exact_observations, injected
                exact = original_summary_exact(*args)
                if output.exists():
                    exact_observations += 1
                    if exact_observations == 3:
                        (attempt / "invalid.json").write_bytes(b"{}\n")
                        injected = True
                return exact

            with (
                patch.object(
                    analysis,
                    "_validate_artifact",
                    side_effect=_owned_synthetic_validation(validated),
                ),
                patch.object(analysis, "_build_summary", return_value=summary),
                patch.object(
                    analysis,
                    "_summary_publication_is_exact",
                    side_effect=inject_after_final_summary_proof,
                ),
                self.assertRaises(analysis.DiagnosticAnalysisError) as raised,
            ):
                analysis.write_countdown_thompson_diagnostic_summary(
                    artifact,
                    bundle,
                    root / "authorization.json",
                    "0" * 64,
                    output,
                    repository_root=root,
                )
            self.assertIs(type(raised.exception), analysis.DiagnosticAnalysisError)
            self.assertTrue(injected)
            self.assertGreaterEqual(exact_observations, 3)
            self.assertFalse(output.exists())

    def test_post_barrier_attempt_terminal_drift_revokes_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "relocated-artifact"
            artifact_receipt = _write_synthetic_artifact_members(
                artifact,
                b"identical-artifact",
            )
            historical = root / "historical-artifact"
            self.assertEqual(
                _write_synthetic_artifact_members(
                    historical,
                    b"identical-artifact",
                ),
                artifact_receipt,
            )
            validated = _synthetic_validated_authority(
                historical,
                artifact_receipt,
            )
            attempt = validated.historical_attempt_path
            bundle = root / "bundle"
            _write_synthetic_bundle_members(bundle)
            publication_parent = root / "publication-parent"
            publication_parent.mkdir()
            parent_identity = (
                publication_parent.stat().st_dev,
                publication_parent.stat().st_ino,
            )
            output = publication_parent / "summary.json"
            summary = {"schema_version": "synthetic/v1", "status": "PASS"}
            summary_bytes = analysis._canonical_bytes(summary)
            original_fsync = analysis.os.fsync
            parent_sync_count = 0
            injected = False

            def inject_terminal_after_summary_barrier(descriptor: int) -> None:
                nonlocal injected, parent_sync_count
                opened = analysis.os.fstat(descriptor)
                original_fsync(descriptor)
                if (opened.st_dev, opened.st_ino) == parent_identity:
                    parent_sync_count += 1
                    if parent_sync_count == 1:
                        (attempt / "invalid.json").write_bytes(b"{}\n")
                        injected = True

            with (
                patch.object(
                    analysis,
                    "_validate_artifact",
                    side_effect=_owned_synthetic_validation(validated),
                ),
                patch.object(analysis, "_build_summary", return_value=summary),
                patch.object(
                    analysis.os,
                    "fsync",
                    side_effect=inject_terminal_after_summary_barrier,
                ),
            ):
                with self.assertRaises(
                    analysis.DiagnosticAnalysisError,
                ) as raised:
                    analysis.write_countdown_thompson_diagnostic_summary(
                        artifact,
                        bundle,
                        root / "authorization.json",
                        "0" * 64,
                        output,
                        repository_root=root,
                    )
            self.assertIs(type(raised.exception), analysis.DiagnosticAnalysisError)
            self.assertIn("directory closure drifted", str(raised.exception))
            self.assertTrue(injected)
            self.assertEqual(parent_sync_count, 2)
            self.assertFalse(output.exists())
            quarantines = tuple(
                path
                for path in publication_parent.iterdir()
                if path.name.startswith(".summary.json.rollback-")
            )
            self.assertEqual(len(quarantines), 1)
            self.assertEqual(quarantines[0].read_bytes(), summary_bytes)

    def test_rotating_source_and_summary_generations_revoke_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "relocated-artifact"
            artifact_receipt = _write_synthetic_artifact_members(
                artifact,
                b"identical-artifact",
            )
            historical = root / "historical-artifact"
            self.assertEqual(
                _write_synthetic_artifact_members(
                    historical,
                    b"identical-artifact",
                ),
                artifact_receipt,
            )
            validated = _synthetic_validated_authority(
                historical,
                artifact_receipt,
            )
            attempt = validated.historical_attempt_path
            attempt_member = attempt / "ready_to_commit.json"
            relocated_member = artifact / "records.jsonl"
            bundle = root / "bundle"
            _write_synthetic_bundle_members(bundle)
            publication_parent = root / "publication-parent"
            publication_parent.mkdir()
            output = publication_parent / "summary.json"
            summary = {"schema_version": "synthetic/v1", "status": "PASS"}
            summary_bytes = analysis._canonical_bytes(summary)
            foreign_summary = bytes((summary_bytes[0] ^ 1,)) + summary_bytes[1:]
            original_summary_exact = analysis._summary_publication_is_exact
            original_revalidate = analysis._revalidate_attempt_authority_after_topology
            attempt_proofs = 0
            attempt_invalidated = False
            rotation_completed = False

            def invalidate_attempt_after_publication(*args: object) -> bool:
                nonlocal attempt_invalidated
                if output.exists() and not attempt_invalidated:
                    _mutate_file_preserving_size(attempt_member)
                    attempt_invalidated = True
                return original_summary_exact(*args)

            def rotate_during_postpublication_attempt(
                *args: object,
                **kwargs: object,
            ) -> None:
                nonlocal attempt_proofs, rotation_completed
                attempt_proofs += 1
                if attempt_proofs != 2:
                    original_revalidate(*args, **kwargs)
                    return
                output.write_bytes(foreign_summary)
                _mutate_file_preserving_size(attempt_member)
                original_revalidate(*args, **kwargs)
                output.write_bytes(summary_bytes)
                _mutate_file_preserving_size(relocated_member)
                rotation_completed = True

            with (
                patch.object(
                    analysis,
                    "_validate_artifact",
                    side_effect=_owned_synthetic_validation(validated),
                ),
                patch.object(analysis, "_build_summary", return_value=summary),
                patch.object(
                    analysis,
                    "_summary_publication_is_exact",
                    side_effect=invalidate_attempt_after_publication,
                ),
                patch.object(
                    analysis,
                    "_revalidate_attempt_authority_after_topology",
                    side_effect=rotate_during_postpublication_attempt,
                ),
                self.assertRaises(analysis.DiagnosticAnalysisError) as raised,
            ):
                analysis.write_countdown_thompson_diagnostic_summary(
                    artifact,
                    bundle,
                    root / "authorization.json",
                    "0" * 64,
                    output,
                    repository_root=root,
                )
            self.assertIs(type(raised.exception), analysis.DiagnosticAnalysisError)
            self.assertTrue(attempt_invalidated)
            self.assertTrue(rotation_completed)
            self.assertEqual(attempt_proofs, 2)
            self.assertFalse(output.exists())
            quarantines = tuple(
                path
                for path in publication_parent.iterdir()
                if path.name.startswith(".summary.json.rollback-")
            )
            self.assertEqual(len(quarantines), 1)
            self.assertEqual(quarantines[0].read_bytes(), summary_bytes)

    def test_source_ancestor_away_and_back_revokes_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            relocated_parent = root / "relocated-parent"
            artifact = relocated_parent / "artifact"
            artifact_receipt = _write_synthetic_artifact_members(
                artifact,
                b"identical-artifact",
            )
            historical = root / "historical-artifact"
            self.assertEqual(
                _write_synthetic_artifact_members(
                    historical,
                    b"identical-artifact",
                ),
                artifact_receipt,
            )
            validated = _synthetic_validated_authority(
                historical,
                artifact_receipt,
            )
            bundle = root / "bundle"
            _write_synthetic_bundle_members(bundle)
            publication_parent = root / "publication-parent"
            publication_parent.mkdir()
            output = publication_parent / "summary.json"
            summary = {"schema_version": "synthetic/v1", "status": "PASS"}
            summary_bytes = analysis._canonical_bytes(summary)
            displaced_parent = root / "relocated-parent-away"
            original_summary_exact = analysis._summary_publication_is_exact
            pivoted = False

            def pivot_source_ancestor_after_publication(*args: object) -> bool:
                nonlocal pivoted
                if output.exists() and not pivoted:
                    relocated_parent.rename(displaced_parent)
                    displaced_parent.rename(relocated_parent)
                    pivoted = True
                return original_summary_exact(*args)

            with (
                patch.object(
                    analysis,
                    "_validate_artifact",
                    side_effect=_owned_synthetic_validation(validated),
                ),
                patch.object(analysis, "_build_summary", return_value=summary),
                patch.object(
                    analysis,
                    "_summary_publication_is_exact",
                    side_effect=pivot_source_ancestor_after_publication,
                ),
                self.assertRaisesRegex(
                    analysis.DiagnosticAnalysisError,
                    "source authority generation changed",
                ),
            ):
                analysis.write_countdown_thompson_diagnostic_summary(
                    artifact,
                    bundle,
                    root / "authorization.json",
                    "0" * 64,
                    output,
                    repository_root=root,
                )
            self.assertTrue(pivoted)
            self.assertFalse(output.exists())
            quarantines = tuple(
                path
                for path in publication_parent.iterdir()
                if path.name.startswith(".summary.json.rollback-")
            )
            self.assertEqual(len(quarantines), 1)
            self.assertEqual(quarantines[0].read_bytes(), summary_bytes)

    def test_final_collective_proof_resyncs_restored_summary_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "relocated-artifact"
            artifact_receipt = _write_synthetic_artifact_members(
                artifact,
                b"identical-artifact",
            )
            historical = root / "historical-artifact"
            self.assertEqual(
                _write_synthetic_artifact_members(
                    historical,
                    b"identical-artifact",
                ),
                artifact_receipt,
            )
            validated = _synthetic_validated_authority(
                historical,
                artifact_receipt,
            )
            bundle = root / "bundle"
            _write_synthetic_bundle_members(bundle)
            publication_parent = root / "publication-parent"
            publication_parent.mkdir()
            output = publication_parent / "summary.json"
            summary = {"schema_version": "synthetic/v1", "status": "PASS"}
            summary_bytes = analysis._canonical_bytes(summary)
            foreign_summary = bytes((summary_bytes[0] ^ 1,)) + summary_bytes[1:]
            original_summary_exact = analysis._summary_publication_is_exact
            original_fsync = analysis.os.fsync
            restored_without_sync = False
            summary_file_sync_count = 0

            def count_summary_file_sync(descriptor: int) -> None:
                nonlocal summary_file_sync_count
                opened = analysis.os.fstat(descriptor)
                if stat.S_ISREG(opened.st_mode):
                    summary_file_sync_count += 1
                original_fsync(descriptor)

            def durably_write_foreign_then_restore(*args: object) -> bool:
                nonlocal restored_without_sync
                if output.exists() and not restored_without_sync:
                    output.write_bytes(foreign_summary)
                    descriptor = analysis.os.open(output, analysis.os.O_RDWR)
                    try:
                        original_fsync(descriptor)
                    finally:
                        analysis.os.close(descriptor)
                    output.write_bytes(summary_bytes)
                    restored_without_sync = True
                return original_summary_exact(*args)

            with (
                patch.object(
                    analysis,
                    "_validate_artifact",
                    side_effect=_owned_synthetic_validation(validated),
                ),
                patch.object(analysis, "_build_summary", return_value=summary),
                patch.object(
                    analysis,
                    "_summary_publication_is_exact",
                    side_effect=durably_write_foreign_then_restore,
                ),
                patch.object(
                    analysis.os,
                    "fsync",
                    side_effect=count_summary_file_sync,
                ),
            ):
                result = analysis.write_countdown_thompson_diagnostic_summary(
                    artifact,
                    bundle,
                    root / "authorization.json",
                    "0" * 64,
                    output,
                    repository_root=root,
                )
            self.assertEqual(result, summary)
            self.assertTrue(restored_without_sync)
            self.assertEqual(summary_file_sync_count, 2)
            self.assertEqual(output.read_bytes(), summary_bytes)

    def _exercise_post_barrier_artifact_receipt_drift(
        self,
        *,
        mutate_historical: bool,
        mutate_relocated: bool,
        fail_rollback_sync: bool = False,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "relocated-artifact"
            artifact_receipt = _write_synthetic_artifact_members(
                artifact,
                b"identical-artifact",
            )
            historical = root / "historical-artifact"
            self.assertEqual(
                _write_synthetic_artifact_members(
                    historical,
                    b"identical-artifact",
                ),
                artifact_receipt,
            )
            bundle = root / "bundle"
            _write_synthetic_bundle_members(bundle)
            publication_parent = root / "publication-parent"
            publication_parent.mkdir()
            parent_identity = (
                publication_parent.stat().st_dev,
                publication_parent.stat().st_ino,
            )
            output = publication_parent / "summary.json"
            summary = {
                "schema_version": "synthetic/v1",
                "status": "PASS",
            }
            summary_bytes = analysis._canonical_bytes(summary)
            original_fsync = analysis.os.fsync
            parent_sync_count = 0
            mutation_completed = False

            def mutate_after_summary_barrier(descriptor: int) -> None:
                nonlocal mutation_completed, parent_sync_count
                opened = analysis.os.fstat(descriptor)
                if (opened.st_dev, opened.st_ino) == parent_identity:
                    parent_sync_count += 1
                    if fail_rollback_sync and parent_sync_count == 2:
                        raise OSError("synthetic rollback parent barrier failure")
                original_fsync(descriptor)
                if (
                    not mutation_completed
                    and parent_sync_count == 1
                    and output.exists()
                ):
                    if mutate_historical:
                        _mutate_file_preserving_size(historical / "records.jsonl")
                    if mutate_relocated:
                        _mutate_file_preserving_size(artifact / "records.jsonl")
                    mutation_completed = True

            with (
                patch.object(
                    analysis,
                    "_validate_artifact",
                    side_effect=_owned_synthetic_validation(
                        _synthetic_validated_authority(
                            historical,
                            artifact_receipt,
                        )
                    ),
                ),
                patch.object(analysis, "_build_summary", return_value=summary),
                patch.object(
                    analysis.os,
                    "fsync",
                    side_effect=mutate_after_summary_barrier,
                ),
            ):
                if fail_rollback_sync:
                    with self.assertRaisesRegex(
                        analysis.DiagnosticAnalysisPublicationAmbiguousError,
                        "must not be used",
                    ):
                        analysis.write_countdown_thompson_diagnostic_summary(
                            artifact,
                            bundle,
                            root / "authorization.json",
                            "0" * 64,
                            output,
                            repository_root=root,
                        )
                else:
                    with self.assertRaises(
                        analysis.DiagnosticAnalysisError,
                    ) as raised:
                        analysis.write_countdown_thompson_diagnostic_summary(
                            artifact,
                            bundle,
                            root / "authorization.json",
                            "0" * 64,
                            output,
                            repository_root=root,
                        )
                    self.assertIs(
                        type(raised.exception), analysis.DiagnosticAnalysisError
                    )
                    self.assertIn("bytes differ", str(raised.exception))
            self.assertTrue(mutation_completed)
            self.assertFalse(output.exists())
            quarantines = tuple(
                path
                for path in publication_parent.iterdir()
                if path.name.startswith(".summary.json.rollback-")
            )
            self.assertEqual(len(quarantines), 1)
            self.assertEqual(quarantines[0].read_bytes(), summary_bytes)
            self.assertEqual(parent_sync_count, 2)

    def test_historical_receipt_drift_after_summary_barrier_revokes_summary(
        self,
    ) -> None:
        self._exercise_post_barrier_artifact_receipt_drift(
            mutate_historical=True,
            mutate_relocated=False,
        )

    def test_relocated_receipt_drift_after_summary_barrier_revokes_summary(
        self,
    ) -> None:
        self._exercise_post_barrier_artifact_receipt_drift(
            mutate_historical=False,
            mutate_relocated=True,
        )

    def test_both_artifact_receipts_drift_after_summary_barrier_revokes_summary(
        self,
    ) -> None:
        self._exercise_post_barrier_artifact_receipt_drift(
            mutate_historical=True,
            mutate_relocated=True,
        )

    def test_post_barrier_receipt_drift_rollback_sync_failure_is_ambiguous(
        self,
    ) -> None:
        self._exercise_post_barrier_artifact_receipt_drift(
            mutate_historical=True,
            mutate_relocated=False,
            fail_rollback_sync=True,
        )

    def test_historical_directory_equal_to_artifact_retains_raw_pin(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "artifact"
            artifact_receipt = _write_synthetic_artifact_members(
                artifact,
                b"same-directory-artifact",
            )
            bundle = root / "bundle"
            _write_synthetic_bundle_members(bundle)
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
                post_durability_check: object,
            ) -> None:
                self.assertEqual(len(protected_roots), 4)
                artifact_pin, _bundle_pin, attempt_pin, historical_pin = protected_roots
                self.assertEqual(artifact_pin.identity, historical_pin.identity)
                self.assertNotEqual(
                    artifact_pin.descriptor,
                    historical_pin.descriptor,
                )
                self.assertEqual(artifact_pin.authority_path, artifact)
                self.assertEqual(historical_pin.authority_path, artifact)
                self.assertEqual(
                    attempt_pin.authority_path.parent,
                    artifact.parent,
                )
                self.assertTrue(callable(post_durability_check))
                analysis._assert_pinned_protected_roots(protected_roots)

            with (
                patch.object(
                    analysis,
                    "_validate_artifact",
                    side_effect=_owned_synthetic_validation(
                        _synthetic_validated_authority(
                            artifact,
                            artifact_receipt,
                        )
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
            _write_synthetic_bundle_members(bundle)
            historical = root / "historical-artifact"
            publication_parent = root / "publication-parent"
            publication_parent.mkdir()
            relocated_parent = historical / publication_parent.name
            output = publication_parent / "summary.json"
            raced = False
            validated = _synthetic_validated_authority(historical)

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
                    side_effect=_owned_synthetic_validation(validated),
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

    def test_summary_entry_stat_open_fifo_race_is_nonblocking(self) -> None:
        if not hasattr(os, "mkfifo") or not hasattr(os, "O_NONBLOCK"):
            self.skipTest("non-blocking FIFO observation is unavailable")
        payload = analysis._canonical_bytes(
            {"schema_version": "synthetic/v1", "status": "PASS"}
        )
        original_open = analysis.os.open
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "summary.json"
            destination.write_bytes(payload)
            opened = destination.stat()
            staged_identity = (opened.st_dev, opened.st_ino)
            parent_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            swapped = False

            def swap_to_fifo_before_open(
                path: object,
                flags: int,
                *args: object,
                **kwargs: object,
            ) -> int:
                nonlocal swapped
                if (
                    path == destination.name
                    and kwargs.get("dir_fd") == parent_fd
                    and not swapped
                ):
                    destination.unlink()
                    os.mkfifo(destination)
                    swapped = True
                    if not flags & os.O_NONBLOCK:
                        raise AssertionError("summary observation omitted O_NONBLOCK")
                return original_open(path, flags, *args, **kwargs)

            try:
                started = time.monotonic()
                with patch.object(
                    analysis.os,
                    "open",
                    side_effect=swap_to_fifo_before_open,
                ):
                    state = analysis._summary_entry_state(
                        parent_fd,
                        destination.name,
                        staged_identity,
                        payload,
                    )
                elapsed = time.monotonic() - started
            finally:
                os.close(parent_fd)
            self.assertTrue(swapped)
            self.assertEqual(state, analysis._SUMMARY_ENTRY_OTHER)
            self.assertLess(elapsed, 1.0)
            self.assertTrue(stat.S_ISFIFO(destination.lstat().st_mode))

    def test_summary_entry_growth_is_bounded_and_not_exact(self) -> None:
        payload = analysis._canonical_bytes(
            {"schema_version": "synthetic/v1", "status": "PASS"}
        )
        original_read = analysis.os.read
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "summary.json"
            destination.write_bytes(payload)
            opened = destination.stat()
            staged_identity = (opened.st_dev, opened.st_ino)
            parent_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            grew = False
            requested_sizes: list[int] = []

            def grow_after_first_read(descriptor: int, size: int) -> bytes:
                nonlocal grew
                current = os.fstat(descriptor)
                if (current.st_dev, current.st_ino) == staged_identity:
                    requested_sizes.append(size)
                    if size > len(payload) + 1:
                        raise AssertionError("summary observation read is unbounded")
                chunk = original_read(descriptor, size)
                if (
                    not grew
                    and chunk
                    and (current.st_dev, current.st_ino) == staged_identity
                ):
                    with destination.open("ab") as handle:
                        handle.write(b"growth" * 1024)
                    grew = True
                return chunk

            try:
                with patch.object(
                    analysis.os,
                    "read",
                    side_effect=grow_after_first_read,
                ):
                    state = analysis._summary_entry_state(
                        parent_fd,
                        destination.name,
                        staged_identity,
                        payload,
                    )
            finally:
                os.close(parent_fd)
            self.assertTrue(grew)
            self.assertTrue(requested_sizes)
            self.assertEqual(state, analysis._SUMMARY_ENTRY_OTHER)

    def test_pinned_summary_inode_growth_is_bounded_and_not_exact(self) -> None:
        payload = analysis._canonical_bytes(
            {"schema_version": "synthetic/v1", "status": "PASS"}
        )
        original_read = analysis.os.read
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "summary.json"
            destination.write_bytes(payload)
            descriptor = os.open(destination, os.O_RDWR | os.O_NOFOLLOW)
            opened = os.fstat(descriptor)
            staged_identity = (opened.st_dev, opened.st_ino)
            grew = False
            requested_sizes: list[int] = []

            def grow_after_first_read(observed_fd: int, size: int) -> bytes:
                nonlocal grew
                current = os.fstat(observed_fd)
                if (current.st_dev, current.st_ino) == staged_identity:
                    requested_sizes.append(size)
                    if size > len(payload) + 1:
                        raise AssertionError("pinned summary read is unbounded")
                chunk = original_read(observed_fd, size)
                if (
                    not grew
                    and chunk
                    and (current.st_dev, current.st_ino) == staged_identity
                ):
                    with destination.open("ab") as handle:
                        handle.write(b"growth" * 1024)
                    grew = True
                return chunk

            try:
                with patch.object(
                    analysis.os,
                    "read",
                    side_effect=grow_after_first_read,
                ):
                    state, link_count = analysis._pinned_summary_inode_state(
                        descriptor,
                        staged_identity,
                        payload,
                    )
            finally:
                os.close(descriptor)
            self.assertTrue(grew)
            self.assertTrue(requested_sizes)
            self.assertEqual(state, analysis._SUMMARY_ENTRY_OTHER)
            self.assertEqual(link_count, 1)

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

    def test_summary_post_durability_baseexceptions_are_typed_invalid(
        self,
    ) -> None:
        payload = analysis._canonical_bytes(
            {"schema_version": "synthetic/v1", "status": "PASS"}
        )
        for exception_type in (KeyboardInterrupt, SystemExit, BaseException):
            with self.subTest(exception_type=exception_type.__name__):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    output = root / "summary.json"
                    check_calls = 0

                    def interrupt_post_durability_check() -> None:
                        nonlocal check_calls
                        check_calls += 1
                        raise exception_type(
                            "synthetic mandatory post-durability interruption"
                        )

                    with self.assertRaises(
                        analysis.DiagnosticAnalysisError,
                    ) as raised:
                        analysis._atomic_write_no_replace(
                            output,
                            payload,
                            post_durability_check=interrupt_post_durability_check,
                        )
                    self.assertIs(
                        type(raised.exception), analysis.DiagnosticAnalysisError
                    )
                    self.assertIn(
                        "mandatory summary post-durability check failed",
                        str(raised.exception),
                    )
                    self.assertIsInstance(raised.exception.__cause__, exception_type)
                    self.assertEqual(check_calls, 1)
                    self.assertFalse(output.exists())
                    quarantines = tuple(
                        path
                        for path in root.iterdir()
                        if path.name.startswith(".summary.json.rollback-")
                    )
                    self.assertEqual(len(quarantines), 1)
                    self.assertEqual(quarantines[0].read_bytes(), payload)

    def test_summary_post_durability_interrupt_with_unproven_rollback_is_ambiguous(
        self,
    ) -> None:
        payload = analysis._canonical_bytes(
            {"schema_version": "synthetic/v1", "status": "PASS"}
        )
        original_fsync = analysis.os.fsync

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "summary.json"
            parent_identity = (root.stat().st_dev, root.stat().st_ino)
            parent_sync_count = 0

            def fail_rollback_parent_barrier(descriptor: int) -> None:
                nonlocal parent_sync_count
                observed = analysis.os.fstat(descriptor)
                if (observed.st_dev, observed.st_ino) == parent_identity:
                    parent_sync_count += 1
                    if parent_sync_count == 2:
                        raise OSError("synthetic rollback durability failure")
                original_fsync(descriptor)

            def interrupt_post_durability_check() -> None:
                raise SystemExit("synthetic mandatory post-durability interruption")

            with patch.object(
                analysis.os,
                "fsync",
                side_effect=fail_rollback_parent_barrier,
            ):
                with self.assertRaises(
                    analysis.DiagnosticAnalysisPublicationAmbiguousError,
                ) as raised:
                    analysis._atomic_write_no_replace(
                        output,
                        payload,
                        post_durability_check=interrupt_post_durability_check,
                    )
            self.assertIs(
                type(raised.exception),
                analysis.DiagnosticAnalysisPublicationAmbiguousError,
            )
            self.assertIn("must not be used", str(raised.exception))
            self.assertEqual(parent_sync_count, 2)
            self.assertFalse(output.exists())
            quarantines = tuple(
                path
                for path in root.iterdir()
                if path.name.startswith(".summary.json.rollback-")
            )
            self.assertEqual(len(quarantines), 1)
            self.assertEqual(quarantines[0].read_bytes(), payload)

    def test_summary_barrier_interrupt_recovery_runs_mandatory_callback(
        self,
    ) -> None:
        payload = analysis._canonical_bytes(
            {"schema_version": "synthetic/v1", "status": "PASS"}
        )
        original_fsync = analysis.os.fsync

        for exception_type in (KeyboardInterrupt, SystemExit):
            with self.subTest(exception_type=exception_type.__name__):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    output = root / "summary.json"
                    parent_identity = (root.stat().st_dev, root.stat().st_ino)
                    parent_sync_count = 0
                    check_calls = 0

                    def interrupt_after_first_parent_barrier(
                        descriptor: int,
                    ) -> None:
                        nonlocal parent_sync_count
                        observed = analysis.os.fstat(descriptor)
                        original_fsync(descriptor)
                        if (observed.st_dev, observed.st_ino) == parent_identity:
                            parent_sync_count += 1
                            if parent_sync_count == 1:
                                raise exception_type(
                                    "synthetic interruption after parent barrier"
                                )

                    def mandatory_post_durability_check() -> None:
                        nonlocal check_calls
                        check_calls += 1

                    with patch.object(
                        analysis.os,
                        "fsync",
                        side_effect=interrupt_after_first_parent_barrier,
                    ):
                        analysis._atomic_write_no_replace(
                            output,
                            payload,
                            post_durability_check=mandatory_post_durability_check,
                        )
                    self.assertGreaterEqual(parent_sync_count, 2)
                    self.assertEqual(check_calls, 1)
                    self.assertEqual(output.read_bytes(), payload)
                    self.assertEqual(
                        {path.name for path in root.iterdir()},
                        {output.name},
                    )

    def test_summary_barrier_recovery_callback_failure_revokes_as_invalid(
        self,
    ) -> None:
        payload = analysis._canonical_bytes(
            {"schema_version": "synthetic/v1", "status": "PASS"}
        )
        original_fsync = analysis.os.fsync

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "summary.json"
            parent_identity = (root.stat().st_dev, root.stat().st_ino)
            parent_sync_count = 0
            check_calls = 0

            def interrupt_after_first_parent_barrier(descriptor: int) -> None:
                nonlocal parent_sync_count
                observed = analysis.os.fstat(descriptor)
                original_fsync(descriptor)
                if (observed.st_dev, observed.st_ino) == parent_identity:
                    parent_sync_count += 1
                    if parent_sync_count == 1:
                        raise KeyboardInterrupt(
                            "synthetic interruption after parent barrier"
                        )

            def interrupt_recovered_post_durability_check() -> None:
                nonlocal check_calls
                check_calls += 1
                raise SystemExit("synthetic recovered post-durability interruption")

            with patch.object(
                analysis.os,
                "fsync",
                side_effect=interrupt_after_first_parent_barrier,
            ):
                with self.assertRaises(
                    analysis.DiagnosticAnalysisError,
                ) as raised:
                    analysis._atomic_write_no_replace(
                        output,
                        payload,
                        post_durability_check=(
                            interrupt_recovered_post_durability_check
                        ),
                    )
            self.assertIs(type(raised.exception), analysis.DiagnosticAnalysisError)
            self.assertIsInstance(raised.exception.__cause__, SystemExit)
            self.assertEqual(check_calls, 1)
            self.assertEqual(parent_sync_count, 3)
            self.assertFalse(output.exists())
            quarantines = tuple(
                path
                for path in root.iterdir()
                if path.name.startswith(".summary.json.rollback-")
            )
            self.assertEqual(len(quarantines), 1)
            self.assertEqual(quarantines[0].read_bytes(), payload)

    def test_callback_same_inode_overwrite_is_never_committed_success(self) -> None:
        payload = analysis._canonical_bytes(
            {"schema_version": "synthetic/v1", "status": "PASS"}
        )
        foreign = payload.replace(b'"PASS"', b'"FAIL"')
        self.assertEqual(len(foreign), len(payload))
        original_rename = analysis._rename_noreplace_at

        for recovery in (False, True):
            with (
                self.subTest(recovery=recovery),
                tempfile.TemporaryDirectory(
                    prefix="qmc-bmgs-summary-callback-overwrite-"
                ) as directory,
            ):
                output = Path(directory) / "summary.json"
                callback_calls = 0
                before_identity: tuple[int, int] | None = None
                after_identity: tuple[int, int] | None = None

                def overwrite_same_inode() -> None:
                    nonlocal callback_calls, before_identity, after_identity
                    callback_calls += 1
                    before = output.stat()
                    before_identity = (before.st_dev, before.st_ino)
                    descriptor = analysis.os.open(
                        output,
                        analysis.os.O_WRONLY | analysis.os.O_NOFOLLOW,
                    )
                    try:
                        written = analysis.os.write(descriptor, foreign)
                        self.assertEqual(written, len(foreign))
                        analysis.os.fsync(descriptor)
                    finally:
                        analysis.os.close(descriptor)
                    after = output.stat()
                    after_identity = (after.st_dev, after.st_ino)

                def rename_then_interrupt(*args: object) -> None:
                    original_rename(*args)
                    raise OSError("synthetic post-rename recovery trigger")

                rename_patch = (
                    patch.object(
                        analysis,
                        "_rename_noreplace_at",
                        side_effect=rename_then_interrupt,
                    )
                    if recovery
                    else patch.object(
                        analysis,
                        "_rename_noreplace_at",
                        wraps=original_rename,
                    )
                )
                with (
                    rename_patch,
                    self.assertRaises(
                        analysis.DiagnosticAnalysisPublicationAmbiguousError,
                    ),
                ):
                    analysis._atomic_write_no_replace(
                        output,
                        payload,
                        post_durability_check=overwrite_same_inode,
                    )
                self.assertEqual(callback_calls, 1)
                self.assertEqual(before_identity, after_identity)
                self.assertEqual(output.read_bytes(), foreign)

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

    def test_summary_rollback_restores_foreign_swap_before_reporting_ambiguity(
        self,
    ) -> None:
        payload = analysis._canonical_bytes(
            {"schema_version": "synthetic/v1", "status": "PASS"}
        )
        foreign = b'{"foreign":true}\n'
        original_rename = analysis._rename_noreplace_at

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "summary.json"
            exact_survivor = root / "moved-exact-summary.json"
            foreign_identity: tuple[int, int] | None = None
            swap_completed = False

            def fail_commit_receipt() -> None:
                raise analysis.DiagnosticAnalysisError(
                    "synthetic post-durability receipt drift"
                )

            def swap_before_rollback_rename(
                directory_fd: int,
                source_name: str,
                destination_name: str,
            ) -> None:
                nonlocal foreign_identity, swap_completed
                if (
                    source_name == output.name
                    and destination_name.startswith(".summary.json.rollback-")
                    and not swap_completed
                ):
                    output.rename(exact_survivor)
                    output.write_bytes(foreign)
                    observed = output.stat()
                    foreign_identity = (observed.st_dev, observed.st_ino)
                    swap_completed = True
                original_rename(directory_fd, source_name, destination_name)

            with patch.object(
                analysis,
                "_rename_noreplace_at",
                side_effect=swap_before_rollback_rename,
            ):
                with self.assertRaisesRegex(
                    analysis.DiagnosticAnalysisPublicationAmbiguousError,
                    "must not be used",
                ):
                    analysis._atomic_write_no_replace(
                        output,
                        payload,
                        post_durability_check=fail_commit_receipt,
                    )
            self.assertTrue(swap_completed)
            self.assertIsNotNone(foreign_identity)
            self.assertEqual(output.read_bytes(), foreign)
            restored = output.stat()
            self.assertEqual(
                (restored.st_dev, restored.st_ino),
                foreign_identity,
            )
            self.assertEqual(exact_survivor.read_bytes(), payload)
            self.assertEqual(
                tuple(
                    path
                    for path in root.iterdir()
                    if path.name.startswith(".summary.json.rollback-")
                ),
                (),
            )

    def test_summary_rollback_restores_foreign_symlink_on_darwin(self) -> None:
        if not hasattr(os, "O_SYMLINK"):
            self.skipTest("Darwin O_SYMLINK is unavailable")
        payload = analysis._canonical_bytes(
            {"schema_version": "synthetic/v1", "status": "PASS"}
        )
        original_rename = analysis._rename_noreplace_at

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "summary.json"
            exact_survivor = root / "moved-exact-summary.json"
            foreign_target = root / "foreign-target.json"
            foreign_target.write_text("foreign\n", encoding="utf-8")
            foreign_identity: tuple[int, int] | None = None
            swap_completed = False

            def fail_commit_receipt() -> None:
                raise analysis.DiagnosticAnalysisError(
                    "synthetic post-durability receipt drift"
                )

            def swap_symlink_before_rollback_rename(
                directory_fd: int,
                source_name: str,
                destination_name: str,
            ) -> None:
                nonlocal foreign_identity, swap_completed
                if (
                    source_name == output.name
                    and destination_name.startswith(".summary.json.rollback-")
                    and not swap_completed
                ):
                    output.rename(exact_survivor)
                    output.symlink_to(foreign_target.name)
                    observed = output.lstat()
                    foreign_identity = (observed.st_dev, observed.st_ino)
                    swap_completed = True
                original_rename(directory_fd, source_name, destination_name)

            with patch.object(
                analysis,
                "_rename_noreplace_at",
                side_effect=swap_symlink_before_rollback_rename,
            ):
                with self.assertRaisesRegex(
                    analysis.DiagnosticAnalysisPublicationAmbiguousError,
                    "must not be used",
                ):
                    analysis._atomic_write_no_replace(
                        output,
                        payload,
                        post_durability_check=fail_commit_receipt,
                    )
            self.assertTrue(swap_completed)
            self.assertIsNotNone(foreign_identity)
            self.assertTrue(output.is_symlink())
            self.assertEqual(os.readlink(output), foreign_target.name)
            restored = output.lstat()
            self.assertEqual(
                (restored.st_dev, restored.st_ino),
                foreign_identity,
            )
            self.assertEqual(exact_survivor.read_bytes(), payload)
            self.assertEqual(
                tuple(
                    path
                    for path in root.iterdir()
                    if path.name.startswith(".summary.json.rollback-")
                ),
                (),
            )

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

    def test_deep_untrusted_json_boundaries_are_typed_invalid(self) -> None:
        nesting = 10_000
        deep_object = (
            b'{"nested":' + (b"[" * nesting) + b"0" + (b"]" * nesting) + b"}\n"
        )
        self.assertLess(len(deep_object), 8 * 1024 * 1024)
        boundaries = (
            (
                "stdlib object",
                lambda: analysis._stdlib_strict_json_object(
                    deep_object,
                    "synthetic deep manifest",
                ),
            ),
            (
                "project object",
                lambda: analysis._strict_json_object(
                    deep_object,
                    "synthetic deep object",
                ),
            ),
            ("project JSONL", lambda: analysis._strict_jsonl(deep_object)),
        )
        for label, boundary in boundaries:
            with (
                self.subTest(boundary=label),
                self.assertRaises(
                    analysis.DiagnosticAnalysisError,
                ) as raised,
            ):
                boundary()
            self.assertIs(type(raised.exception), analysis.DiagnosticAnalysisError)

    def test_deep_manifest_cli_emits_canonical_invalid(self) -> None:
        nesting = 10_000
        deep_manifest = (
            b'{"nested":' + (b"[" * nesting) + b"0" + (b"]" * nesting) + b"}\n"
        )
        self.assertLess(len(deep_manifest), 8 * 1024 * 1024)

        with tempfile.TemporaryDirectory(
            prefix="qmc-bmgs-deep-manifest-cli-"
        ) as directory:
            root = Path(directory)
            artifact = root / "artifact"
            artifact.mkdir()
            (artifact / "manifest.json").write_bytes(deep_manifest)
            bundle = root / "bundle"
            bundle.mkdir()
            output = root / "summary.json"
            with patch("builtins.print") as printed:
                status = analysis.main(
                    [
                        "--analyze",
                        os.fspath(artifact),
                        "--bundle",
                        os.fspath(bundle),
                        "--authorization-file",
                        os.fspath(root / "authorization.json"),
                        "--authorization-digest",
                        "0" * 64,
                        "--output",
                        os.fspath(output),
                        "--repository-root",
                        os.fspath(root),
                    ]
                )
            self.assertEqual(status, 2)
            self.assertFalse(output.exists())
            emitted = analysis.strict_json_loads(printed.call_args.args[0])
            self.assertEqual(emitted["status"], "INVALID")
            self.assertEqual(
                emitted["claim_boundary"],
                "no diagnostic result was emitted",
            )

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

    def test_summary_pass_reports_fixed_lexical_namespace_after_ancestor_pivot(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_parent = root / "raw-parent"
            raw_parent.mkdir()
            displaced = root / "displaced-parent"
            alternate = root / "alternate-parent"
            alternate.mkdir()
            output = raw_parent / "summary.json"

            def publish_then_pivot(*args: object, **kwargs: object) -> dict[str, str]:
                self.assertEqual(args[4], output)
                raw_parent.rename(displaced)
                raw_parent.symlink_to(alternate, target_is_directory=True)
                return {
                    "analyzer_build_digest": "a" * 64,
                    "deterministic_digest": "b" * 64,
                }

            with (
                patch.object(
                    analysis,
                    "write_countdown_thompson_diagnostic_summary",
                    side_effect=publish_then_pivot,
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
                        os.fspath(output),
                        "--repository-root",
                        ".",
                    ]
                )
            self.assertEqual(status, 0)
            reported = analysis.strict_json_loads(printed.call_args.args[0])
            self.assertEqual(reported["status"], "PASS")
            self.assertEqual(reported["output_path"], os.fspath(output))
            self.assertNotEqual(
                reported["output_path"],
                os.fspath(alternate / output.name),
            )


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
