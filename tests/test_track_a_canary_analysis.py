from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from qmc_bmgs.experiments import countdown_track_a_canary_analysis as analysis
from qmc_bmgs.experiments.countdown_track_a_canary_manifest import CanaryCell
from qmc_bmgs.substrate.budget import TRACK_A_WORK_AXES, TrackAWorkBudget
from qmc_bmgs.substrate.countdown_search import TrackABudgetProfile, TrackAMethodSpec
from qmc_bmgs.substrate.trace import TraceValidationError, canonical_json, sha256_json


_SHA_A = "a" * 64
_SHA_B = "b" * 64
_SHA_C = "c" * 64
_SHA_D = "d" * 64
_SHA_E = "e" * 64
_SHA_F = "f" * 64
_GIT_A = "1" * 40
_GIT_B = "2" * 40
_GIT_C = "3" * 40
_GIT_D = "4" * 40
_GIT_E = "5" * 40
_BUNDLE_ID = "synthetic-track-a-canary/v-test"


def _canonical_bytes(payload: dict[str, object]) -> bytes:
    return (canonical_json(payload) + "\n").encode("utf-8")


def _synthetic_source_bytes() -> dict[str, bytes]:
    return {
        relative: f"synthetic source: {relative}\n".encode("utf-8")
        for relative in (
            *analysis._SEARCH_SOURCE_PATHS,
            *analysis._RUNNER_SOURCE_PATHS,
        )
    }


def _synthetic_attestation(
    source_bytes: dict[str, bytes] | None = None,
) -> dict[str, object]:
    sources = _synthetic_source_bytes() if source_bytes is None else source_bytes
    search_receipts = {
        relative: {
            "byte_count": len(sources[relative]),
            "sha256": analysis._sha256_bytes(sources[relative]),
        }
        for relative in analysis._SEARCH_SOURCE_PATHS
    }
    runner_receipts = {
        relative: {
            "byte_count": len(sources[relative]),
            "sha256": analysis._sha256_bytes(sources[relative]),
        }
        for relative in analysis._RUNNER_SOURCE_PATHS
    }
    search_build_digest = sha256_json(
        {
            "host_build": {},
            "numeric_microfixture": {},
            "search_microfixture": {},
            "source_files": search_receipts,
        }
    )
    runner_build_digest = sha256_json(
        {
            "runner_source_files": runner_receipts,
            "search_build_digest": search_build_digest,
        }
    )
    return {
        "authorized_runner_revision": _GIT_A,
        "host_build": {},
        "numeric_microfixture": {},
        "required_ancestry": [_GIT_B],
        "runner_build_digest": runner_build_digest,
        "runner_source_files": runner_receipts,
        "schema_version": ("qmc-bmgs-countdown-track-a-canary-build-attestation/v1"),
        "search_build_digest": search_build_digest,
        "search_microfixture": {},
        "search_source_files": search_receipts,
    }


class _FakeBundle:
    def __init__(self, payloads: dict[str, object], cells: tuple[CanaryCell, ...]):
        self._payloads = payloads
        self.cells = cells
        self.seal_digest = _SHA_F

    @property
    def payloads(self) -> dict[str, object]:
        return self._payloads


def _cell(task: str, index: int) -> CanaryCell:
    return CanaryCell(
        task_fingerprint=task,
        proposal_label="synthetic_proposal",
        proposal_spec_digest=_SHA_A,
        method_label="synthetic_method",
        method_spec_digest=_SHA_B,
        method_manifest_digest=_SHA_C,
        budget_profile_id="synthetic_budget",
        budget_profile_spec_digest=_SHA_D,
        exploration_seed=index,
        task_manifest_digest=_SHA_E,
    )


def _write_synthetic_artifact(
    directory: Path,
    *,
    cells: tuple[CanaryCell, ...],
    observed_ids: list[str],
) -> _FakeBundle:
    directory.mkdir()
    records = [
        {
            "cell_id": cell_id,
            "deterministic_digest": sha256_json({"index": index}),
            "telemetry": {
                "role": analysis._TELEMETRY_ROLE,
                "search_wall_time_ns": 0,
                "replay_wall_time_ns": 0,
            },
        }
        for index, cell_id in enumerate(observed_ids)
    ]
    records_raw = b"".join(_canonical_bytes(record) for record in records)
    (directory / "records.jsonl").write_bytes(records_raw)
    attestation = _synthetic_attestation()
    search_build_digest = attestation["search_build_digest"]
    runner_build_digest = attestation["runner_build_digest"]
    runtime_qualification = {
        "bundle_id": _BUNDLE_ID,
        "execution_authorized": False,
        "runtime_bindings_digest": sha256_json({}),
        "status": "RUNTIME_QUALIFIED",
    }
    schedule_digest = _SHA_C
    authorization = {
        "authorization_scope": "one_exact_complete_936_cell_canary_run",
        "artifact_id": directory.name,
        "bundle_id": _BUNDLE_ID,
        "canary_seal_digest": _SHA_F,
        "cell_count": len(cells),
        "claim_boundary": (
            "execution authority only; canary comparisons remain descriptive"
        ),
        "method_manifest_digest": _SHA_C,
        "output_path": str(directory.resolve()),
        "requires_explicit_digest_confirmation": True,
        "runner_build_attestation": attestation,
        "runtime_qualification": runtime_qualification,
        "runtime_qualification_digest": sha256_json(runtime_qualification),
        "schedule_digest": schedule_digest,
        "schema_version": (
            "qmc-bmgs-countdown-track-a-canary-execution-authorization/v1"
        ),
    }
    authorization["deterministic_digest"] = sha256_json(authorization)
    attempt_marker_basename = (
        f".{directory.name}.attempt-{authorization['deterministic_digest']}"
    )
    attempt_started_receipt = {
        "artifact_id": directory.name,
        "authorization_digest": authorization["deterministic_digest"],
        "authorized_output_path": str(directory.resolve()),
        "canary_seal_digest": _SHA_F,
        "execution_head_revision": _GIT_E,
        "phase": "STARTED",
        "reviewed_authorization_revision": _GIT_D,
        "runner_build_digest": runner_build_digest,
        "schema_version": ("qmc-bmgs-countdown-track-a-canary-attempt-marker/v1"),
        "search_build_digest": search_build_digest,
        "staging_path": str(
            directory.resolve().parent / attempt_marker_basename / "staging"
        ),
        "status": "PENDING",
    }
    attempt_started_receipt["deterministic_digest"] = sha256_json(
        attempt_started_receipt
    )
    manifest = {
        "schema_version": analysis.RUN_MANIFEST_SCHEMA_VERSION,
        "bundle_id": _BUNDLE_ID,
        "artifact_id": directory.name,
        "attempt_id": authorization["deterministic_digest"],
        "attempt_marker_basename": attempt_marker_basename,
        "attempt_phase": "READY_TO_COMMIT",
        "attempt_started_receipt": attempt_started_receipt,
        "attempt_started_receipt_digest": attempt_started_receipt[
            "deterministic_digest"
        ],
        "authorized_output_path": str(directory.resolve()),
        "canary_seal_digest": _SHA_F,
        "method_manifest_digest": _SHA_C,
        "runner_build_attestation": attestation,
        "runtime_qualification": runtime_qualification,
        "execution_authorization": authorization,
        "execution_authorization_digest": authorization["deterministic_digest"],
        "execution_head_revision": _GIT_E,
        "reviewed_authorization_revision": _GIT_D,
        "cell_count": len(cells),
        "schedule_cell_ids": [cell.cell_id for cell in cells],
        "records_jsonl_sha256": analysis._sha256_bytes(records_raw),
        "records_jsonl_byte_count": len(records_raw),
        "record_digests": [record["deterministic_digest"] for record in records],
        "claim_boundary": analysis._RUN_CLAIM_BOUNDARY,
        "telemetry": {
            "role": analysis._TELEMETRY_ROLE,
            "search_wall_time_ns_total": 0,
            "replay_wall_time_ns_total": 0,
        },
    }
    manifest["deterministic_digest"] = sha256_json(manifest)
    (directory / "manifest.json").write_bytes(_canonical_bytes(manifest))
    commit_receipt = {
        "artifact_id": directory.name,
        "attempt_started_receipt_digest": attempt_started_receipt[
            "deterministic_digest"
        ],
        "execution_authorization_digest": authorization["deterministic_digest"],
        "run_manifest_digest": manifest["deterministic_digest"],
        "schema_version": analysis.ARTIFACT_COMMIT_SCHEMA_VERSION,
        "status": "COMMITTED",
    }
    commit_receipt["deterministic_digest"] = sha256_json(commit_receipt)
    (directory / "commit.json").write_bytes(_canonical_bytes(commit_receipt))
    payloads = {
        "methods.json": {
            "deterministic_digest": _SHA_C,
            "runtime_bindings": {},
        },
        "preregistration.json": {
            "bundle_id": _BUNDLE_ID,
            "execution_matrix": {"schedule_digest": schedule_digest},
        },
    }
    return _FakeBundle(payloads, cells)


def _write_reviewed_authorization(artifact: Path, destination: Path) -> str:
    manifest = analysis._strict_json_object(
        (artifact / "manifest.json").read_bytes(),
        "synthetic manifest",
    )
    authorization = manifest["execution_authorization"]
    destination.write_bytes(_canonical_bytes(authorization))
    return authorization["deterministic_digest"]


def _synthetic_reduction_fixture() -> analysis._ValidatedRun:
    task_order = [_SHA_A, _SHA_B]
    method_order = [
        "greedy",
        "beam_width_2",
        "puct_c1",
        "thompson_frozen_iid",
        "thompson_frozen_sobol",
        "thompson_candidate_iid",
        "thompson_candidate_sobol",
    ]
    success_patterns = {
        "greedy": ((True,), (False,)),
        "beam_width_2": ((True,), (True,)),
        "puct_c1": ((False,), (True,)),
        "thompson_frozen_iid": (
            (True, False, False, False),
            (True, True, False, False),
        ),
        "thompson_frozen_sobol": (
            (True, False, False, False),
            (True, False, False, False),
        ),
        "thompson_candidate_iid": (
            (True, True, False, False),
            (True, True, True, True),
        ),
        "thompson_candidate_sobol": (
            (True, True, True, False),
            (True, True, False, False),
        ),
    }
    payloads = {
        "tasks.json": {"tasks": [{"task_fingerprint": value} for value in task_order]},
        "proposals.json": {
            "policy_order": ["heuristic"],
            "policies": [
                {"label": "heuristic", "execution_scope": "all_seven_methods"}
            ],
        },
        "budgets.json": {"profile_order": ["score256"]},
        "methods.json": {
            "method_order": method_order,
            "methods": [
                {
                    "label": label,
                    "spec": {
                        "selected_source": (
                            "iid"
                            if label.endswith("iid")
                            else "sobol"
                            if label.endswith("sobol")
                            else "none"
                        )
                    },
                }
                for label in method_order
            ],
        },
    }
    records = []
    for task_index, task in enumerate(task_order):
        for method in method_order:
            successes = success_patterns[method][task_index]
            seeds = analysis._CANARY_SEEDS if len(successes) == 4 else (0,)
            for seed, success in zip(seeds, successes, strict=True):
                records.append(
                    {
                        "cell": SimpleNamespace(
                            task_fingerprint=task,
                            proposal_label="heuristic",
                            budget_profile_id="score256",
                            method_label=method,
                            exploration_seed=seed,
                        ),
                        "summary": {"success_any": success},
                    }
                )
    return analysis._ValidatedRun(
        bundle=_FakeBundle(payloads, ()),
        records=tuple(records),
        manifest={},
        analyzer_build_digest=_SHA_F,
    )


class TrackACanaryAnalysisTests(unittest.TestCase):
    def test_git_oid_validation_is_distinct_from_sha256_data_digests(self) -> None:
        self.assertTrue(analysis._is_git_oid(_GIT_A))
        self.assertTrue(analysis._is_git_oid(_SHA_A))
        self.assertFalse(analysis._is_git_oid("1" * 39))
        self.assertFalse(analysis._is_git_oid("G" * 40))
        self.assertTrue(analysis._is_sha256(_SHA_A))
        self.assertFalse(analysis._is_sha256(_GIT_A))

    def test_runner_claim_boundary_handshake_matches_current_schema(self) -> None:
        self.assertEqual(
            analysis._RUN_CLAIM_BOUNDARY,
            "descriptive canary artifact; byte replay applies only to the "
            "embedded search core, telemetry is volatile, and no inferential "
            "or promotion authority is granted",
        )

    def test_runner_manifest_attempt_evidence_handshake_is_exact(self) -> None:
        cells = (_cell(_SHA_A, 0),)
        with tempfile.TemporaryDirectory(prefix="synthetic-attempt-handshake-") as root:
            artifact = Path(root).resolve() / "artifact"
            _write_synthetic_artifact(
                artifact,
                cells=cells,
                observed_ids=[cells[0].cell_id],
            )
            manifest = analysis._stdlib_strict_json_object(
                (artifact / "manifest.json").read_bytes(),
                "synthetic manifest",
            )
            analysis._preflight_run_manifest(manifest)
            changed = analysis.strict_json_loads(canonical_json(manifest))
            changed["attempt_started_receipt"]["status"] = "PASS"
            changed["attempt_started_receipt"]["deterministic_digest"] = sha256_json(
                {
                    key: value
                    for key, value in changed["attempt_started_receipt"].items()
                    if key != "deterministic_digest"
                }
            )
            changed["attempt_started_receipt_digest"] = changed[
                "attempt_started_receipt"
            ]["deterministic_digest"]
            changed["deterministic_digest"] = sha256_json(
                {
                    key: value
                    for key, value in changed.items()
                    if key != "deterministic_digest"
                }
            )
            with self.assertRaisesRegex(
                analysis.CanaryAnalysisError,
                "binding drifted",
            ):
                analysis._preflight_run_manifest(changed)

    def test_strict_jsonl_rejects_noncanonical_duplicate_and_nonfinite(self) -> None:
        self.assertEqual(
            analysis._strict_jsonl(b'{"a":1}\n'),
            ({"a": 1},),
        )
        for raw in (
            b'{"a": 1}\n',
            b'{"a":1,"a":2}\n',
            b'{"a":NaN}\n',
            b'{"a":1}',
        ):
            with self.subTest(raw=raw):
                with self.assertRaises(analysis.CanaryAnalysisError):
                    analysis._strict_jsonl(raw)

    def test_exact_schedule_rejects_duplicate_before_record_validation(self) -> None:
        cells = (_cell(_SHA_A, 0), _cell(_SHA_B, 1))
        with tempfile.TemporaryDirectory(prefix="synthetic-canary-analysis-") as root:
            root_path = Path(root).resolve()
            artifact = root_path / "artifact"
            bundle = _write_synthetic_artifact(
                artifact,
                cells=cells,
                observed_ids=[cells[0].cell_id, cells[0].cell_id],
            )
            authorization = root_path / "authorization.json"
            authorization_digest = _write_reviewed_authorization(
                artifact,
                authorization,
            )
            with (
                patch.object(analysis, "EXPECTED_CELL_COUNT", 2),
                patch.object(
                    analysis,
                    "verify_track_a_canary_bundle",
                    return_value=bundle,
                ),
                patch.object(
                    analysis,
                    "iter_track_a_canary_cells",
                    return_value=cells,
                ),
                patch.object(analysis, "_typed_replay_inputs", return_value=None),
                patch.object(
                    analysis,
                    "_validate_current_replay_surface",
                    return_value=_SHA_F,
                ),
                patch.object(
                    analysis,
                    "_validate_reviewed_authorization_provenance",
                ),
                patch.object(analysis, "_validate_one_record") as validate_record,
            ):
                with self.assertRaisesRegex(
                    analysis.CanaryAnalysisError,
                    "missing, duplicate, extra, or reordered",
                ):
                    analysis._validate_artifact(
                        artifact,
                        root_path / "bundle",
                        authorization,
                        authorization_digest,
                        repository_root=root_path,
                    )
            validate_record.assert_not_called()

    def test_current_surface_gate_precedes_bundle_and_record_open(self) -> None:
        cells = (_cell(_SHA_A, 0), _cell(_SHA_B, 1))
        with tempfile.TemporaryDirectory(prefix="synthetic-canary-order-") as root:
            root_path = Path(root).resolve()
            artifact = root_path / "artifact"
            _write_synthetic_artifact(
                artifact,
                cells=cells,
                observed_ids=[cell.cell_id for cell in cells],
            )
            with (
                patch.object(
                    analysis,
                    "_validate_current_replay_surface",
                    side_effect=analysis.CanaryAnalysisError(
                        "synthetic current surface refusal"
                    ),
                ) as current_gate,
                patch.object(
                    analysis,
                    "verify_track_a_canary_bundle",
                ) as verify_bundle,
                patch.object(
                    analysis,
                    "_read_artifact_snapshot",
                ) as read_outcome_snapshot,
            ):
                with self.assertRaisesRegex(
                    analysis.CanaryAnalysisError,
                    "current surface refusal",
                ):
                    analysis._validate_artifact(
                        artifact,
                        root_path / "bundle",
                        root_path / "authorization.json",
                        _SHA_A,
                        repository_root=root_path,
                    )
            current_gate.assert_called_once()
            verify_bundle.assert_not_called()
            read_outcome_snapshot.assert_not_called()

    def test_ready_staging_without_commit_is_rejected_before_records(self) -> None:
        cells = (_cell(_SHA_A, 0),)
        with tempfile.TemporaryDirectory(prefix="synthetic-ready-staging-") as root:
            artifact = Path(root).resolve() / "artifact"
            _write_synthetic_artifact(
                artifact,
                cells=cells,
                observed_ids=[cells[0].cell_id],
            )
            (artifact / "commit.json").unlink()
            with (
                patch.object(
                    analysis,
                    "_validate_current_replay_surface",
                    side_effect=AssertionError("source gate must not be reached"),
                ),
                patch.object(
                    analysis,
                    "_read_artifact_snapshot",
                    side_effect=AssertionError("records must not be opened"),
                ),
            ):
                with self.assertRaisesRegex(
                    analysis.CanaryAnalysisError,
                    "authority member is unavailable: commit.json",
                ):
                    analysis._validate_artifact(
                        artifact,
                        Path(root) / "bundle",
                        Path(root) / "authorization.json",
                        _SHA_A,
                        repository_root=Path(root),
                    )

    def test_reviewed_authorization_uses_nofollow_descriptor(self) -> None:
        with tempfile.TemporaryDirectory(prefix="synthetic-auth-nofollow-") as root:
            root_path = Path(root).resolve()
            target = root_path / "target.json"
            authorization = {"fixture": "synthetic-only"}
            authorization["deterministic_digest"] = sha256_json(authorization)
            target.write_bytes(_canonical_bytes(authorization))
            link = root_path / "authorization.json"
            link.symlink_to(target)
            with self.assertRaisesRegex(
                analysis.CanaryAnalysisError,
                "regular file",
            ):
                analysis._reviewed_authorization(
                    link,
                    authorization["deterministic_digest"],
                )

    def test_reviewed_authorization_revision_and_tracked_blob_close(self) -> None:
        cells = (_cell(_SHA_A, 0), _cell(_SHA_B, 1))
        with tempfile.TemporaryDirectory(prefix="synthetic-auth-git-") as root:
            root_path = Path(root).resolve()
            artifact = root_path / "artifact"
            _write_synthetic_artifact(
                artifact,
                cells=cells,
                observed_ids=[cell.cell_id for cell in cells],
            )
            manifest = analysis._strict_json_object(
                (artifact / "manifest.json").read_bytes(),
                "synthetic manifest",
            )
            authorization_path = root_path / "authorization.json"
            authorization_raw = _canonical_bytes(manifest["execution_authorization"])
            authorization_path.write_bytes(authorization_raw)
            relative = authorization_path.relative_to(root_path).as_posix()
            observed_relations: list[tuple[str, str]] = []

            def fake_git(_root: Path, *arguments: str) -> SimpleNamespace:
                if arguments[0] == "cat-file":
                    return SimpleNamespace(returncode=0, stdout=b"commit\n")
                if arguments[0] == "merge-base":
                    observed_relations.append((arguments[2], arguments[3]))
                    return SimpleNamespace(returncode=0, stdout=b"")
                if arguments[0] == "ls-files":
                    return SimpleNamespace(
                        returncode=0,
                        stdout=f"{relative}\n".encode("utf-8"),
                    )
                if arguments[0] == "ls-tree":
                    return SimpleNamespace(
                        returncode=0,
                        stdout=(
                            b"100644 blob "
                            + b"0" * 40
                            + b"\t"
                            + relative.encode("utf-8")
                            + b"\0"
                        ),
                    )
                if arguments[0] == "show":
                    return SimpleNamespace(returncode=0, stdout=authorization_raw)
                raise AssertionError(arguments)

            with patch.object(analysis, "_git_result", side_effect=fake_git):
                analysis._validate_reviewed_authorization_provenance(
                    root_path,
                    authorization_path=authorization_path,
                    authorization_raw=authorization_raw,
                    manifest=manifest,
                )
            self.assertEqual(
                observed_relations,
                [(_GIT_A, _GIT_D), (_GIT_D, _GIT_E)],
            )

            equal_revision = dict(manifest)
            equal_revision["reviewed_authorization_revision"] = _GIT_A
            with (
                patch.object(analysis, "_git_result", side_effect=fake_git),
                self.assertRaisesRegex(
                    analysis.CanaryAnalysisError,
                    "strictly descend",
                ),
            ):
                analysis._validate_reviewed_authorization_provenance(
                    root_path,
                    authorization_path=authorization_path,
                    authorization_raw=authorization_raw,
                    manifest=equal_revision,
                )

    def test_reviewed_git_authority_rejects_tag_and_symlink_tree_entry(self) -> None:
        with patch.object(
            analysis,
            "_git_result",
            return_value=SimpleNamespace(returncode=0, stdout=b"tag\n"),
        ):
            with self.assertRaisesRegex(
                analysis.CanaryAnalysisError,
                "exact Git commit object",
            ):
                analysis._require_git_commit_object(
                    Path("."),
                    _GIT_D,
                    "reviewed authorization revision",
                )

        relative = "docs/preregistrations/reviewed-auth.json"
        symlink_entry = (
            b"120000 blob " + b"0" * 40 + b"\t" + relative.encode("utf-8") + b"\0"
        )
        with patch.object(
            analysis,
            "_git_result",
            return_value=SimpleNamespace(returncode=0, stdout=symlink_entry),
        ):
            with self.assertRaisesRegex(
                analysis.CanaryAnalysisError,
                "regular blob",
            ):
                analysis._require_regular_git_tree_entry(
                    Path("."),
                    _GIT_D,
                    relative,
                )

    def test_invalid_artifact_never_creates_summary_file(self) -> None:
        cells = (_cell(_SHA_A, 0), _cell(_SHA_B, 1))
        with tempfile.TemporaryDirectory(prefix="synthetic-canary-analysis-") as root:
            root_path = Path(root).resolve()
            artifact = root_path / "artifact"
            output = root_path / "summary.json"
            bundle = _write_synthetic_artifact(
                artifact,
                cells=cells,
                observed_ids=[cells[0].cell_id, cells[0].cell_id],
            )
            authorization = root_path / "authorization.json"
            authorization_digest = _write_reviewed_authorization(
                artifact,
                authorization,
            )
            with (
                patch.object(analysis, "EXPECTED_CELL_COUNT", 2),
                patch.object(
                    analysis,
                    "verify_track_a_canary_bundle",
                    return_value=bundle,
                ),
                patch.object(
                    analysis,
                    "iter_track_a_canary_cells",
                    return_value=cells,
                ),
                patch.object(
                    analysis,
                    "_validate_current_replay_surface",
                    return_value=_SHA_F,
                ),
                patch.object(
                    analysis,
                    "_validate_reviewed_authorization_provenance",
                ),
            ):
                with self.assertRaises(analysis.CanaryAnalysisError):
                    analysis.write_track_a_canary_summary(
                        artifact,
                        root_path / "bundle",
                        authorization,
                        authorization_digest,
                        output,
                        repository_root=root_path,
                    )
            self.assertFalse(output.exists())

    def test_task_reduction_uses_nested_seeds_before_task_contrasts(self) -> None:
        validated = _synthetic_reduction_fixture()
        task_metrics, vectors = analysis._task_metrics(validated)
        self.assertEqual(len(task_metrics), 14)
        self.assertEqual(
            vectors[("heuristic", "score256", "thompson_candidate_iid")],
            [0.5, 1.0],
        )
        self.assertEqual(
            vectors[("heuristic", "score256", "greedy")],
            [1.0, 0.0],
        )
        contrasts = {
            row["contrast_id"]: row
            for row in analysis._contrasts(vectors, ["score256"])
        }
        self.assertEqual(
            contrasts["candidate_minus_frozen_iid"]["task_delta_vector"],
            [0.25, 0.5],
        )
        self.assertEqual(
            contrasts["candidate_minus_frozen_sobol"]["task_delta_vector"],
            [0.5, 0.25],
        )
        self.assertEqual(
            contrasts["equal_source_candidate_minus_frozen"]["task_delta_vector"],
            [0.375, 0.375],
        )
        self.assertEqual(
            contrasts["candidate_iid_minus_greedy"]["task_delta_vector"],
            [-0.5, 1.0],
        )

    def test_pareto_flag_requires_both_baselines_and_strict_inequality(self) -> None:
        validated = _synthetic_reduction_fixture()
        _, vectors = analysis._task_metrics(validated)
        status = analysis._pareto_statuses(vectors, ["score256"])[0]
        self.assertFalse(status["simple_baseline_pareto_dominated"])
        dominated = dict(vectors)
        dominated[("heuristic", "score256", "thompson_candidate_iid")] = [
            0.0,
            0.0,
        ]
        dominated[("heuristic", "score256", "thompson_candidate_sobol")] = [
            0.0,
            0.0,
        ]
        dominated[("heuristic", "score256", "greedy")] = [1.0, 1.0]
        dominated[("heuristic", "score256", "beam_width_2")] = [1.0, 1.0]
        status = analysis._pareto_statuses(dominated, ["score256"])[0]
        self.assertTrue(status["simple_baseline_pareto_dominated"])
        self.assertFalse(status["locked_evaluation_blocked_by_this_flag"])

    def test_puct_is_coordinate_free_but_uses_adaptive_stop_closure(self) -> None:
        budget = TrackAWorkBudget(
            proposal_state_evaluations=86,
            proposal_action_scores=257,
            legal_action_scores=256,
            generated_perturbation_coordinates=257,
            edge_selections=86,
            transitions=86,
            verifier_calls=18,
        )
        profile = TrackABudgetProfile("score256", "legal_action_scores", budget)
        usage = {axis: 1 for axis in TRACK_A_WORK_AXES}
        usage.update(
            {
                "legal_action_scores": 254,
                "generated_perturbation_coordinates": 0,
                "edge_selections": 2,
                "transitions": 2,
                "verifier_calls": 1,
            }
        )
        remaining = {
            axis: budget.to_dict()[axis] - usage[axis] for axis in TRACK_A_WORK_AXES
        }
        search_record = {"ledger_snapshot": {"usage": usage, "remaining": remaining}}
        summary = {
            "budget_valid": True,
            "non_primary_exhausted_axes": [],
            "stop_blocked_axes": ["legal_action_scores"],
            "terminal_count": 1,
            "exact_terminal_count": 0,
            "successful_terminal_diversity": 0,
            "incomplete_trajectory_count": 0,
            "success_any": False,
            "selected_source_point_count": 0,
            "stop_reason": "primary_budget_blocked",
            "stop_attempted_charge": {
                axis: 3 if axis == "legal_action_scores" else 0
                for axis in TRACK_A_WORK_AXES
            },
        }
        analysis._validate_profile_and_accounting(
            cell=_cell(_SHA_A, 0),
            method=TrackAMethodSpec.puct(),
            profile=profile,
            search_record=search_record,
            summary=summary,
        )
        usage["generated_perturbation_coordinates"] = 1
        with self.assertRaisesRegex(
            analysis.CanaryAnalysisError,
            "deterministic coordinates",
        ):
            analysis._validate_profile_and_accounting(
                cell=_cell(_SHA_A, 0),
                method=TrackAMethodSpec.puct(),
                profile=profile,
                search_record=search_record,
                summary=summary,
            )
        usage["generated_perturbation_coordinates"] = 0
        summary["stop_blocked_axes"] = [
            "legal_action_scores",
            "generated_perturbation_coordinates",
        ]
        with self.assertRaisesRegex(
            analysis.CanaryAnalysisError,
            "non-primary guard",
        ):
            analysis._validate_profile_and_accounting(
                cell=_cell(_SHA_A, 0),
                method=TrackAMethodSpec.puct(),
                profile=profile,
                search_record=search_record,
                summary=summary,
            )

    def test_record_requires_independent_replay_and_zero_provider_calls(self) -> None:
        cell = _cell(_SHA_A, 0)
        replay_inputs = SimpleNamespace(
            tasks={_SHA_A: object()},
            proposals={"synthetic_proposal": object()},
            methods={"synthetic_method": object()},
            budgets={"synthetic_budget": object()},
        )
        trace_bytes = b"{}\n"
        record = {
            "schema_version": analysis.RUN_RECORD_SCHEMA_VERSION,
            "bundle_id": _BUNDLE_ID,
            "cell_id": cell.cell_id,
            "cell_key": cell.key,
            "labels": {
                "task_fingerprint": cell.task_fingerprint,
                "proposal_label": cell.proposal_label,
                "method_label": cell.method_label,
                "budget_profile_id": cell.budget_profile_id,
                "exploration_seed": cell.exploration_seed,
            },
            "canary_seal_digest": _SHA_F,
            "method_manifest_digest": _SHA_C,
            "runner_build_digest": _SHA_A,
            "search_build_digest": _SHA_B,
            "runtime_qualification_digest": _SHA_D,
            "search_run_identity_digest": _SHA_E,
            "search_trace_sha256": analysis._sha256_bytes(trace_bytes),
            "search_trace_byte_count": len(trace_bytes),
            "replay": {
                "stage1_generative": "PASS",
                "stage2_byte_identical": "PASS",
                "replayed_sha256": analysis._sha256_bytes(trace_bytes),
            },
            "provider_calls": 0,
            "budget_evidence": {},
            "telemetry": {
                "role": analysis._TELEMETRY_ROLE,
                "search_wall_time_ns": 0,
                "replay_wall_time_ns": 0,
            },
            "search_summary": {},
            "search_record": {},
        }
        record["deterministic_digest"] = sha256_json(record)
        with (
            patch.object(
                analysis,
                "canonical_trace_bytes",
                return_value=trace_bytes,
            ),
            patch.object(
                analysis,
                "replay_countdown_track_a_search_bytes",
                side_effect=TraceValidationError("synthetic replay failure"),
            ) as replay,
        ):
            with self.assertRaisesRegex(
                analysis.CanaryAnalysisError,
                "failed independent two-stage replay",
            ):
                analysis._validate_one_record(
                    record,
                    cell=cell,
                    bundle_id=_BUNDLE_ID,
                    canary_seal_digest=_SHA_F,
                    method_manifest_digest=_SHA_C,
                    replay_inputs=replay_inputs,
                    runner_build_digest=_SHA_A,
                    search_build_digest=_SHA_B,
                    runtime_qualification_digest=_SHA_D,
                )
        replay.assert_called_once()

        record["provider_calls"] = 1
        record["deterministic_digest"] = sha256_json(
            {
                key: value
                for key, value in record.items()
                if key != "deterministic_digest"
            }
        )
        with patch.object(
            analysis,
            "canonical_trace_bytes",
            side_effect=AssertionError("provider gate must precede trace parsing"),
        ):
            with self.assertRaisesRegex(
                analysis.CanaryAnalysisError,
                "used a provider call",
            ):
                analysis._validate_one_record(
                    record,
                    cell=cell,
                    bundle_id=_BUNDLE_ID,
                    canary_seal_digest=_SHA_F,
                    method_manifest_digest=_SHA_C,
                    replay_inputs=replay_inputs,
                    runner_build_digest=_SHA_A,
                    search_build_digest=_SHA_B,
                    runtime_qualification_digest=_SHA_D,
                )

    def test_atomic_summary_publication_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory(prefix="synthetic-summary-") as root:
            destination = Path(root) / "summary.json"
            payload = b'{"fixture":"synthetic-only"}\n'
            analysis._atomic_write_no_replace(destination, payload)
            self.assertEqual(destination.read_bytes(), payload)
            with self.assertRaises(FileExistsError):
                analysis._atomic_write_no_replace(destination, payload)

    def test_summary_publication_refuses_protected_artifact_closures(self) -> None:
        with tempfile.TemporaryDirectory(prefix="synthetic-summary-") as root:
            root_path = Path(root)
            artifact = root_path / "artifact"
            bundle = root_path / "bundle"
            artifact.mkdir()
            bundle.mkdir()
            for output in (artifact / "summary.json", bundle / "summary.json"):
                with self.subTest(output=output):
                    with self.assertRaisesRegex(
                        analysis.CanaryAnalysisError,
                        "cannot modify",
                    ):
                        analysis.write_track_a_canary_summary(
                            artifact,
                            bundle,
                            root_path / "authorization.json",
                            _SHA_A,
                            output,
                            repository_root=root_path,
                        )
                    self.assertFalse(output.exists())

    def test_post_link_fsync_failure_rolls_back_summary(self) -> None:
        with tempfile.TemporaryDirectory(prefix="synthetic-summary-") as root:
            destination = Path(root) / "summary.json"
            call_count = 0

            def flaky_fsync(_file_descriptor: int) -> None:
                nonlocal call_count
                call_count += 1
                if call_count == 2:
                    raise OSError("synthetic directory fsync failure")

            with patch.object(analysis.os, "fsync", side_effect=flaky_fsync):
                with self.assertRaisesRegex(OSError, "synthetic directory"):
                    analysis._atomic_write_no_replace(
                        destination,
                        b'{"fixture":"synthetic-only"}\n',
                    )
            self.assertFalse(destination.exists())

    def test_summary_parent_swap_never_reports_publication_success(self) -> None:
        with tempfile.TemporaryDirectory(prefix="synthetic-summary-") as root:
            root_path = Path(root)
            parent = root_path / "summary-parent"
            displaced = root_path / "displaced-parent"
            parent.mkdir()
            destination = parent / "summary.json"
            original_link = analysis.os.link
            swapped = False

            def swap_parent_then_link(*args: object, **kwargs: object) -> None:
                nonlocal swapped
                if not swapped:
                    parent.rename(displaced)
                    parent.mkdir()
                    swapped = True
                original_link(*args, **kwargs)

            with patch.object(
                analysis.os,
                "link",
                side_effect=swap_parent_then_link,
            ):
                with self.assertRaisesRegex(
                    analysis.CanaryAnalysisError,
                    "summary parent path changed",
                ):
                    analysis._atomic_write_no_replace(
                        destination,
                        b'{"fixture":"synthetic-only"}\n',
                    )
            self.assertFalse(destination.exists())
            self.assertFalse((displaced / destination.name).exists())

    def test_rollback_never_deletes_concurrently_substituted_destination(self) -> None:
        with tempfile.TemporaryDirectory(prefix="synthetic-summary-") as root:
            destination = Path(root) / "summary.json"
            replacement = b"concurrent replacement"
            call_count = 0

            def substitute_then_fail(_file_descriptor: int) -> None:
                nonlocal call_count
                call_count += 1
                if call_count == 2:
                    destination.unlink()
                    destination.write_bytes(replacement)
                    raise OSError("synthetic directory fsync failure")

            with patch.object(
                analysis.os,
                "fsync",
                side_effect=substitute_then_fail,
            ):
                with self.assertRaisesRegex(OSError, "synthetic directory"):
                    analysis._atomic_write_no_replace(
                        destination,
                        b'{"fixture":"synthetic-only"}\n',
                    )
            self.assertEqual(destination.read_bytes(), replacement)

    def test_parent_swap_to_protected_inode_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="synthetic-summary-") as root:
            root_path = Path(root)
            parent = root_path / "parent"
            protected = root_path / "artifact"
            displaced = root_path / "displaced"
            parent.mkdir()
            protected.mkdir()
            original_open = analysis._open_stable_directory
            swapped = False

            def swap_before_parent_open(
                path: Path,
                label: str,
            ) -> tuple[int, object]:
                nonlocal swapped
                if label == "summary parent" and not swapped:
                    parent.rename(displaced)
                    protected.rename(parent)
                    swapped = True
                return original_open(path, label)

            try:
                with patch.object(
                    analysis,
                    "_open_stable_directory",
                    side_effect=swap_before_parent_open,
                ):
                    with self.assertRaisesRegex(
                        analysis.CanaryAnalysisError,
                        "aliases",
                    ):
                        analysis._atomic_write_no_replace(
                            parent / "summary.json",
                            b'{"fixture":"synthetic-only"}\n',
                            protected_roots=(protected,),
                        )
            finally:
                if swapped:
                    parent.rename(protected)
                    displaced.rename(parent)
            self.assertFalse((parent / "summary.json").exists())

    def test_git_provenance_binds_head_ancestry_and_source_receipts(self) -> None:
        sources = _synthetic_source_bytes()
        attestation = _synthetic_attestation(sources)
        with tempfile.TemporaryDirectory(prefix="synthetic-git-provenance-") as root:
            root_path = Path(root).resolve()

            def fake_git(_root: Path, *arguments: str) -> SimpleNamespace:
                if arguments == ("rev-parse", "--show-toplevel"):
                    return SimpleNamespace(
                        returncode=0,
                        stdout=f"{root_path}\n".encode("utf-8"),
                    )
                if arguments[0] in {"cat-file", "merge-base"}:
                    return SimpleNamespace(returncode=0, stdout=b"")
                if arguments[0] == "show":
                    relative = arguments[1].split(":", 1)[1]
                    return SimpleNamespace(returncode=0, stdout=sources[relative])
                raise AssertionError(arguments)

            with patch.object(analysis, "_git_result", side_effect=fake_git):
                analysis._validate_git_provenance(
                    root_path,
                    attestation=attestation,
                    execution_head_revision=_GIT_C,
                )

            def missing_head(_root: Path, *arguments: str) -> SimpleNamespace:
                if arguments == ("rev-parse", "--show-toplevel"):
                    return SimpleNamespace(
                        returncode=0,
                        stdout=f"{root_path}\n".encode("utf-8"),
                    )
                return SimpleNamespace(returncode=1, stdout=b"")

            with patch.object(analysis, "_git_result", side_effect=missing_head):
                with self.assertRaisesRegex(
                    analysis.CanaryAnalysisError,
                    "unavailable",
                ):
                    analysis._validate_git_provenance(
                        root_path,
                        attestation=attestation,
                        execution_head_revision=_GIT_C,
                    )

    def test_receipt_sets_reject_missing_and_extra_protected_paths(self) -> None:
        attestation = _synthetic_attestation()
        for field in ("search_source_files", "runner_source_files"):
            for mutation in ("missing", "extra"):
                with self.subTest(field=field, mutation=mutation):
                    changed = analysis.strict_json_loads(canonical_json(attestation))
                    if mutation == "missing":
                        changed[field].pop(next(iter(changed[field])))
                    else:
                        changed[field]["src/synthetic_extra.py"] = {
                            "byte_count": 0,
                            "sha256": analysis._sha256_bytes(b""),
                        }
                    with self.assertRaisesRegex(
                        analysis.CanaryAnalysisError,
                        "protected path set",
                    ):
                        analysis._validate_build_attestation_structure(changed)

    def test_current_replay_surface_binds_imports_files_receipts_and_git(self) -> None:
        with tempfile.TemporaryDirectory(prefix="synthetic-analyzer-build-") as root:
            root_path = Path(root).resolve()
            sources = _synthetic_source_bytes()
            attestation = _synthetic_attestation(sources)
            for relative in analysis._CURRENT_REPLAY_MODULE_PATHS.values():
                source_path = root_path / relative
                source_path.parent.mkdir(parents=True, exist_ok=True)
                source_path.write_bytes(sources[relative])
            loaded_modules = {
                module_name: SimpleNamespace(__file__=str(root_path / relative))
                for module_name, relative in (
                    analysis._CURRENT_REPLAY_MODULE_PATHS.items()
                )
            }

            def fake_git(_root: Path, *arguments: str) -> SimpleNamespace:
                if arguments == ("rev-parse", "--show-toplevel"):
                    return SimpleNamespace(
                        returncode=0,
                        stdout=f"{root_path}\n".encode("utf-8"),
                    )
                if arguments[0] in {"cat-file", "merge-base"}:
                    return SimpleNamespace(returncode=0, stdout=b"")
                if arguments[0] == "show":
                    relative = arguments[1].split(":", 1)[1]
                    return SimpleNamespace(returncode=0, stdout=sources[relative])
                raise AssertionError(arguments)

            with (
                patch.dict(analysis.sys.modules, loaded_modules),
                patch.object(analysis, "_git_result", side_effect=fake_git),
            ):
                observed = analysis._validate_current_replay_surface(
                    root_path,
                    attestation=attestation,
                    execution_head_revision=_GIT_C,
                )
            analyzer_relative = analysis.ANALYZER_RELATIVE_PATH.as_posix()
            analyzer_receipt = attestation["runner_source_files"][analyzer_relative]
            expected = analysis._stdlib_sha256_json(
                {
                    "byte_count": len(sources[analyzer_relative]),
                    "execution_head_revision": _GIT_C,
                    "relative_path": analyzer_relative,
                    "schema_version": analysis.ANALYZER_BUILD_SCHEMA_VERSION,
                    "sha256": analyzer_receipt["sha256"],
                }
            )
            self.assertEqual(observed, expected)

            wrong_modules = dict(loaded_modules)
            first_module = next(iter(analysis._CURRENT_REPLAY_MODULE_PATHS))
            wrong_modules[first_module] = SimpleNamespace(
                __file__=str(root_path / "outside.py")
            )
            with (
                patch.dict(analysis.sys.modules, wrong_modules),
                patch.object(analysis, "_git_result", side_effect=fake_git),
                self.assertRaisesRegex(
                    analysis.CanaryAnalysisError,
                    "import origin drifted",
                ),
            ):
                analysis._validate_current_replay_surface(
                    root_path,
                    attestation=attestation,
                    execution_head_revision=_GIT_C,
                )

            tampered_relative = analysis._SEARCH_SOURCE_PATHS[0]
            (root_path / tampered_relative).write_bytes(b"tampered source\n")
            with (
                patch.dict(analysis.sys.modules, loaded_modules),
                patch.object(analysis, "_git_result", side_effect=fake_git),
            ):
                with self.assertRaisesRegex(
                    analysis.CanaryAnalysisError,
                    "differ",
                ):
                    analysis._validate_current_replay_surface(
                        root_path,
                        attestation=attestation,
                        execution_head_revision=_GIT_C,
                    )

    def test_self_test_and_cli_do_not_open_sealed_inputs(self) -> None:
        with (
            patch.object(
                analysis,
                "verify_track_a_canary_bundle",
                side_effect=AssertionError("sealed bundle must not be opened"),
            ),
            patch.object(
                analysis,
                "replay_countdown_track_a_search_bytes",
                side_effect=AssertionError("search replay must not run"),
            ),
        ):
            result = analysis._self_test()
            self.assertEqual(result["status"], "PASS")
            self.assertIn("no sealed bundle", result["claim_boundary"])
            with patch("builtins.print") as emit:
                self.assertEqual(analysis.main(["--self-test"]), 0)
            rendered = emit.call_args.args[0]
            parsed = analysis.strict_json_loads(rendered)
            self.assertEqual(parsed["status"], "PASS")
            self.assertIn("no sealed bundle", parsed["claim_boundary"])
            with patch("builtins.print") as emit:
                self.assertEqual(
                    analysis.main(["--self-test", "--bundle", "/forbidden"]),
                    2,
                )
            rejected = analysis.strict_json_loads(emit.call_args.args[0])
            self.assertEqual(rejected["status"], "INVALID")
            self.assertIn("accepts no", rejected["reason"])

    def test_cli_analysis_error_is_canonical_invalid_exit_two(self) -> None:
        with patch("builtins.print") as emit:
            self.assertEqual(
                analysis.main(["--analyze", "/synthetic/artifact"]),
                2,
            )
        rendered = emit.call_args.args[0]
        self.assertEqual(rendered, canonical_json(analysis.strict_json_loads(rendered)))
        parsed = analysis.strict_json_loads(rendered)
        self.assertEqual(parsed["status"], "INVALID")
        self.assertIn("missing required arguments", parsed["reason"])


if __name__ == "__main__":
    unittest.main()
