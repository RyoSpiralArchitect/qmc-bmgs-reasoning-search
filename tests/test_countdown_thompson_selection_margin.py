from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from qmc_bmgs.experiments import countdown_thompson_posthoc_mechanism as posthoc
from qmc_bmgs.experiments import countdown_thompson_selection_margin as margin
from qmc_bmgs.substrate.trace import canonical_json, sha256_json


_ZERO = {"m2": 0.0, "mean": 0.0, "visits": 0}
_ACTION_ORDER_DIGEST = hashlib.sha256(b"action-order").hexdigest()
_PROPOSAL_DIGEST = hashlib.sha256(b"proposal").hexdigest()
_POINT_DIGEST = hashlib.sha256(b"point").hexdigest()


def _selection(
    method: str,
    trajectory: int,
    posterior: list[dict[str, int | float]],
    scores: list[float],
    action_index: int,
) -> dict[str, object]:
    phase = None
    point_digest: str | None = _POINT_DIGEST
    rule = "probability_prior_sqrt_2_ln_action_noise/v1"
    if method == margin.V4_METHOD:
        phase = "greedy_anchor" if trajectory == 0 else "posterior_perturbation"
        rule = "one_greedy_trajectory_then_probability_prior_sqrt_2_ln_action_noise/v1"
        if trajectory == 0:
            point_digest = None
    semantics: dict[str, object] = {
        "action_count": 2,
        "noise_dimension_normalizer": 1.0,
        "selection_rule_id": rule,
    }
    if phase is not None:
        semantics["selection_phase"] = phase
    child_state = [1] if action_index == 0 else [2]
    return {
        "kind": "selection_committed",
        "payload": {
            "action_index": action_index,
            "action_order_digest": _ACTION_ORDER_DIGEST,
            "child_state": child_state,
            "depth": 0,
            "point_digest": point_digest,
            "posterior_before_digest": sha256_json(posterior),
            "proposal_behavior_digest": _PROPOSAL_DIGEST,
            "scored_action_indices": [0, 1],
            "selected_value": scores[action_index],
            "selection_semantics": semantics,
            "selection_values": scores,
            "selection_values_digest": sha256_json(scores),
            "state": [2, 3],
            "trajectory_index": trajectory,
        },
    }


def _terminal(trajectory: int, error: int = 10) -> dict[str, object]:
    return {
        "kind": "terminal_verified",
        "payload": {
            "trajectory_index": trajectory,
            "verification": {
                "final_value": 100 + error,
                "success": error == 0,
                "target": 100,
            },
        },
    }


def _backup(
    trajectory: int,
    action_index: int,
    before: dict[str, int | float],
    after: dict[str, int | float],
) -> dict[str, object]:
    return {
        "kind": "trajectory_backed_up",
        "payload": {
            "trajectory_index": trajectory,
            "updates": [
                {
                    "action_index": action_index,
                    "after": dict(after),
                    "before": dict(before),
                    "state": [2, 3],
                }
            ],
        },
    }


def _record(
    method: str,
    task: str,
    seed: int,
    *,
    dense_flip: bool = False,
) -> dict[str, object]:
    initial = [dict(_ZERO), dict(_ZERO)]
    first_mean = 0.0
    if method == margin.V3_METHOD:
        first_mean = 0.1 if dense_flip else 0.04
    elif method == margin.V4_METHOD:
        first_mean = 0.1
    after_first = {"m2": 0.0, "mean": first_mean, "visits": 1}
    current = [dict(after_first), dict(_ZERO)]
    first_scores = [0.8, 0.2]
    second_scores = [0.45 + first_mean, 0.5]
    second_action = 0 if second_scores[0] >= second_scores[1] else 1
    if second_action == 0:
        after_second = {"m2": 0.0, "mean": first_mean, "visits": 2}
        second_before = after_first
    else:
        after_second = {"m2": 0.0, "mean": first_mean, "visits": 1}
        second_before = _ZERO
    events = [
        _selection(method, 0, initial, first_scores, 0),
        _terminal(0),
        _backup(0, 0, _ZERO, after_first),
        _selection(method, 1, current, second_scores, second_action),
        _terminal(1),
        _backup(1, second_action, second_before, after_second),
    ]
    cell_id = hashlib.sha256(f"{method}:{task}:{seed}".encode()).hexdigest()
    return {
        "cell_id": cell_id,
        "labels": {
            "exploration_seed": seed,
            "method_label": method,
            "proposal_label": "heuristic",
            "task_fingerprint": task,
        },
        "search_record": {"events": events},
        "search_summary": {"success_any": False},
    }


def _records() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    pair_index = 0
    for task_index in range(margin.EXPECTED_TASK_COUNT):
        task = f"task-{task_index:02d}"
        for seed in margin.EXPECTED_SEEDS:
            records.append(_record(margin.V2_METHOD, task, seed))
            records.append(
                _record(
                    margin.V3_METHOD,
                    task,
                    seed,
                    dense_flip=pair_index < 4,
                )
            )
            records.append(_record(margin.V4_METHOD, task, seed))
            pair_index += 1
    while len(records) < margin.EXPECTED_RECORD_COUNT:
        records.append(
            {
                "labels": {
                    "exploration_seed": 0,
                    "method_label": "beam_width_2",
                    "proposal_label": "heuristic",
                    "task_fingerprint": "unused",
                }
            }
        )
    return records


def _published_posthoc(records: list[dict[str, object]]) -> dict[str, object]:
    reductions = posthoc.reduce_verified_records(records)
    core = {
        "claim_boundary": posthoc.CLAIM_BOUNDARY,
        "input_provenance": {"run_manifest_digest": "c" * 64},
        "integrity_status": "PASS",
        "reductions": reductions,
        "schema_version": posthoc.SCHEMA_VERSION,
        "supplemental_validation": {"status": "PASS"},
    }
    return {**core, "deterministic_digest": sha256_json(core)}


class SelectionMarginReductionTests(unittest.TestCase):
    def test_boundary_relations_and_tie_semantics(self) -> None:
        open_boundary = margin._boundary_payload(
            [Fraction(1), Fraction(0)],
            [Fraction(0), Fraction(1)],
            expected_observed_action=0,
        )
        self.assertEqual(open_boundary["boundary_relation"], "at_observed_open")
        self.assertFalse(open_boundary["changes_action_at_boundary"])

        closed_boundary = margin._boundary_payload(
            [Fraction(0), Fraction(1)],
            [Fraction(1), Fraction(0)],
            expected_observed_action=0,
        )
        self.assertEqual(
            closed_boundary["boundary_relation"], "at_observed_closed"
        )
        self.assertTrue(closed_boundary["changes_action_at_boundary"])

        after_boundary = margin._boundary_payload(
            [Fraction(1), Fraction(0)],
            [Fraction(0), Fraction(1, 2)],
            expected_observed_action=0,
        )
        self.assertEqual(after_boundary["boundary_relation"], "after_observed")
        self.assertEqual(
            after_boundary["boundary_scale_exact"],
            {"denominator": 1, "numerator": 2},
        )

        no_boundary = margin._boundary_payload(
            [Fraction(1), Fraction(0)],
            [Fraction(1), Fraction(0)],
            expected_observed_action=0,
        )
        self.assertEqual(no_boundary["boundary_relation"], "none")

    def test_fixed_selection_and_pair_reductions(self) -> None:
        records = _records()
        result = margin.reduce_verified_records(
            records, _published_posthoc(records)
        )
        individual = result["individual_method_selection_sensitivity"]
        self.assertEqual(
            individual[margin.V2_METHOD]["feedback_informed_selection_count"],
            48,
        )
        self.assertEqual(
            individual[margin.V2_METHOD]["zero_posterior_mean_selection_count"],
            48,
        )
        self.assertEqual(
            individual[margin.V3_METHOD]["nonzero_posterior_mean_selection_count"],
            48,
        )
        self.assertEqual(
            individual[margin.V3_METHOD][
                "observed_action_changed_from_zero_mean_count"
            ],
            4,
        )
        self.assertEqual(
            individual[margin.V4_METHOD][
                "observed_action_changed_from_zero_mean_count"
            ],
            48,
        )

        paired = result["paired_v2_v3_common_prefix_sensitivity"]
        self.assertEqual(paired["pair_count"], 48)
        self.assertEqual(paired["pairable_surface_count"], 48)
        self.assertEqual(paired["action_flip_count_at_observed_dense_scale"], 4)
        self.assertEqual(
            paired["pair_stop_reason_distribution"],
            {
                "recorded_action_divergence": 4,
                "trace_end_without_action_divergence": 44,
            },
        )
        self.assertEqual(
            paired["first_action_divergence_coordinate_distribution"],
            {"trajectory_1_depth_0": 4},
        )
        self.assertEqual(paired["nonzero_score_displacement_surface_count"], 48)

    def test_reduction_is_deterministic(self) -> None:
        records = _records()
        published = _published_posthoc(records)
        left = margin.reduce_verified_records(records, published)
        right = margin.reduce_verified_records(records, published)
        self.assertEqual(canonical_json(left), canonical_json(right))

    def test_reconstructed_posterior_digest_drift_fails_closed(self) -> None:
        records = _records()
        target = records[0]
        selection = target["search_record"]["events"][3]  # type: ignore[index]
        selection["payload"]["posterior_before_digest"] = "9" * 64  # type: ignore[index]
        with self.assertRaisesRegex(
            margin.SelectionMarginAuditError,
            "reconstructed posterior digest drifted",
        ):
            margin._target_traces(records)

    def test_backup_before_state_drift_fails_closed(self) -> None:
        records = _records()
        target = records[0]
        backup = target["search_record"]["events"][2]  # type: ignore[index]
        backup["payload"]["updates"][0]["before"]["mean"] = 1.0  # type: ignore[index]
        with self.assertRaisesRegex(
            margin.SelectionMarginAuditError, "backup before-state drifted"
        ):
            margin._target_traces(records)

    def test_selected_action_drift_fails_closed(self) -> None:
        records = _records()
        target = records[0]
        selection = target["search_record"]["events"][0]  # type: ignore[index]
        selection["payload"]["action_index"] = 1  # type: ignore[index]
        selection["payload"]["selected_value"] = 0.2  # type: ignore[index]
        with self.assertRaisesRegex(
            margin.SelectionMarginAuditError, "not the stable argmax"
        ):
            margin._target_traces(records)

    def test_posthoc_divergence_crosscheck_fails_closed(self) -> None:
        records = _records()
        published = _published_posthoc(records)
        rows = published["reductions"]["v2_v3_paired"][  # type: ignore[index]
            "ordered_pair_rows"
        ]
        rows[0]["first_feedback_selection_difference"] = None
        rows[0]["feedback_informed_selection_diverged"] = False
        with self.assertRaisesRegex(
            margin.SelectionMarginAuditError,
            "stop differs from published first divergence",
        ):
            margin.reduce_verified_records(records, published)

    def test_v4_anchor_null_point_is_excluded_but_feedback_point_is_required(
        self,
    ) -> None:
        records = _records()
        traces = margin._target_traces(records)
        v4 = traces[margin.V4_METHOD][0]
        self.assertIsNone(v4.selections[0].point_digest)
        self.assertEqual(v4.feedback_selection_count, 1)

        target = next(
            record
            for record in records
            if record["labels"]["method_label"] == margin.V4_METHOD  # type: ignore[index]
        )
        target["search_record"]["events"][3]["payload"]["point_digest"] = None  # type: ignore[index]
        with self.assertRaisesRegex(
            margin.SelectionMarginAuditError, "selection point digest"
        ):
            margin._target_traces(records)


def _receipt_fixture(root: Path) -> dict[str, object]:
    repository = root / "repository"
    bundle = repository / "bundle"
    repository.mkdir()
    bundle.mkdir()
    artifact = root / "artifact.commit.json"
    artifact.write_text("synthetic artifact\n")
    authorization_digest = "a" * 64
    authorization = root / "authorization.json"
    authorization.write_text(
        canonical_json(
            {
                "deterministic_digest": authorization_digest,
                "output_parent_binding": {},
            }
        )
        + "\n"
    )
    summary = root / "summary.json"
    summary.write_text("{}\n")
    records = _records()
    published = _published_posthoc(records)
    posthoc_file = root / "posthoc.json"
    posthoc_raw = (canonical_json(published) + "\n").encode()
    posthoc_file.write_bytes(posthoc_raw)
    source = {
        "audit_module_sha256": "d" * 64,
        "frozen_design_sha256": "e" * 64,
        "source_revision": "f" * 40,
        "worktree_clean": True,
    }
    verified = SimpleNamespace(
        artifact_commit_digest="b" * 64,
        collective_manifest_digest="1" * 64,
        records=tuple(records),
        records_jsonl_bytes=b"synthetic records\n",
        run_manifest_digest="c" * 64,
    )
    fresh_posthoc = {
        key: published[key] for key in margin.POSTHOC_FRESH_CROSSCHECK_KEYS
    }
    return {
        "artifact": artifact,
        "artifact_commit_digest": "b" * 64,
        "authorization": authorization,
        "authorization_digest": authorization_digest,
        "bundle": bundle,
        "fresh_posthoc": fresh_posthoc,
        "posthoc": posthoc_file,
        "posthoc_digest": published["deterministic_digest"],
        "posthoc_raw_sha256": hashlib.sha256(posthoc_raw).hexdigest(),
        "repository": repository,
        "source": source,
        "summary": summary,
        "summary_digest": "2" * 64,
        "verified": verified,
    }


def _build_fixture_receipt(
    fixture: dict[str, object],
    *,
    fresh_posthoc: object | None = None,
    source_side_effect: object | None = None,
) -> dict[str, object]:
    with (
        patch.object(margin, "_require_frozen_input_anchors"),
        patch.object(margin, "FROZEN_RUN_MANIFEST_DIGEST", "c" * 64),
        patch.object(
            margin,
            "_source_attestation",
            side_effect=source_side_effect,
            return_value=fixture["source"],
        ),
        patch.object(
            posthoc,
            "build_receipt",
            return_value=(
                fixture["fresh_posthoc"]
                if fresh_posthoc is None
                else fresh_posthoc
            ),
        ),
        patch.object(
            posthoc.regular_file_publication,
            "verify_countdown_thompson_diagnostic_v2",
            return_value=fixture["verified"],
        ),
    ):
        return margin.build_receipt(
            fixture["artifact"],  # type: ignore[arg-type]
            fixture["bundle"],  # type: ignore[arg-type]
            fixture["authorization"],  # type: ignore[arg-type]
            fixture["authorization_digest"],  # type: ignore[arg-type]
            "3" * 40,
            fixture["summary"],  # type: ignore[arg-type]
            fixture["summary_digest"],  # type: ignore[arg-type]
            fixture["artifact_commit_digest"],  # type: ignore[arg-type]
            fixture["posthoc"],  # type: ignore[arg-type]
            fixture["posthoc_digest"],  # type: ignore[arg-type]
            fixture["posthoc_raw_sha256"],  # type: ignore[arg-type]
            repository_root=fixture["repository"],  # type: ignore[arg-type]
        )


def _cli_arguments(root: Path) -> list[str]:
    return [
        "--artifact",
        str(root / "missing-artifact.json"),
        "--artifact-commit-digest",
        margin.FROZEN_ARTIFACT_COMMIT_DIGEST,
        "--authorization-digest",
        margin.FROZEN_AUTHORIZATION_DIGEST,
        "--authorization-file",
        str(root / "missing-authorization.json"),
        "--authorization-revision",
        margin.FROZEN_AUTHORIZATION_REVISION,
        "--bundle",
        str(root / "missing-bundle"),
        "--output",
        str(root / "output.json"),
        "--posthoc-digest",
        margin.FROZEN_POSTHOC_DIGEST,
        "--posthoc-raw-sha256",
        margin.FROZEN_POSTHOC_RAW_SHA256,
        "--posthoc-receipt",
        str(root / "missing-posthoc.json"),
        "--repository-root",
        str(root),
        "--summary",
        str(root / "missing-summary.json"),
        "--summary-digest",
        margin.FROZEN_SUMMARY_DIGEST,
    ]


class SelectionMarginReceiptTests(unittest.TestCase):
    def test_build_receipt_composes_revalidation_and_reduction(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            fixture = _receipt_fixture(Path(raw))
            receipt = _build_fixture_receipt(fixture)
        self.assertEqual(receipt["schema_version"], margin.SCHEMA_VERSION)
        self.assertEqual(receipt["integrity_status"], "PASS")
        self.assertEqual(receipt["posthoc_revalidation"]["status"], "PASS")
        self.assertEqual(
            receipt["reductions"]["paired_v2_v3_common_prefix_sensitivity"][
                "action_flip_count_at_observed_dense_scale"
            ],
            4,
        )

    def test_build_receipt_rejects_fresh_posthoc_reduction_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            fixture = _receipt_fixture(Path(raw))
            changed = {
                **fixture["fresh_posthoc"],  # type: ignore[dict-item]
                "reductions": {"changed": True},
            }
            with self.assertRaisesRegex(
                margin.SelectionMarginAuditError,
                "published post-hoc reductions does not freshly recompute",
            ):
                _build_fixture_receipt(fixture, fresh_posthoc=changed)

    def test_build_receipt_rejects_fresh_posthoc_authority_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            fixture = _receipt_fixture(Path(raw))
            changed = {
                **fixture["fresh_posthoc"],  # type: ignore[dict-item]
                "claim_boundary": "forged authority boundary",
            }
            with self.assertRaisesRegex(
                margin.SelectionMarginAuditError,
                "published post-hoc claim_boundary does not freshly recompute",
            ):
                _build_fixture_receipt(fixture, fresh_posthoc=changed)

    def test_coherently_rehashed_posthoc_cannot_replace_frozen_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            fixture = _receipt_fixture(Path(raw))
            path = fixture["posthoc"]
            self.assertIsInstance(path, Path)
            payload = json.loads(path.read_text())
            payload["claim_boundary"] = "forged authority boundary"
            core = {
                key: value
                for key, value in payload.items()
                if key != "deterministic_digest"
            }
            tampered_digest = sha256_json(core)
            payload["deterministic_digest"] = tampered_digest
            tampered_raw = (canonical_json(payload) + "\n").encode()
            path.write_bytes(tampered_raw)

            with self.assertRaisesRegex(
                margin.SelectionMarginAuditError,
                "posthoc_digest, posthoc_raw_sha256",
            ):
                margin.build_receipt(
                    fixture["artifact"],  # type: ignore[arg-type]
                    fixture["bundle"],  # type: ignore[arg-type]
                    fixture["authorization"],  # type: ignore[arg-type]
                    margin.FROZEN_AUTHORIZATION_DIGEST,
                    margin.FROZEN_AUTHORIZATION_REVISION,
                    fixture["summary"],  # type: ignore[arg-type]
                    margin.FROZEN_SUMMARY_DIGEST,
                    margin.FROZEN_ARTIFACT_COMMIT_DIGEST,
                    path,
                    tampered_digest,
                    hashlib.sha256(tampered_raw).hexdigest(),
                    repository_root=fixture["repository"],  # type: ignore[arg-type]
                )

    def test_build_receipt_rejects_source_drift(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            fixture = _receipt_fixture(Path(raw))
            changed = {**fixture["source"], "source_revision": "9" * 40}  # type: ignore[dict-item]
            with self.assertRaisesRegex(
                margin.SelectionMarginAuditError,
                "changed during reduction",
            ):
                _build_fixture_receipt(
                    fixture,
                    source_side_effect=[fixture["source"], changed],
                )

    def test_published_posthoc_raw_hash_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            fixture = _receipt_fixture(Path(raw))
            fixture["posthoc_raw_sha256"] = "9" * 64
            with self.assertRaisesRegex(
                margin.SelectionMarginAuditError, "post-hoc receipt drifted"
            ):
                _build_fixture_receipt(fixture)

    def test_runtime_binding_rejects_historical_self_module_origin(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        historical_revision = "7c4b865c4ad40d35f0eff52e6c58634656b8f3f6"
        with tempfile.TemporaryDirectory() as raw:
            historical_path = Path(raw) / margin.MODULE_RELATIVE_PATH.name
            historical_path.write_bytes(
                margin._git(
                    repository,
                    "show",
                    f"{historical_revision}:{margin.MODULE_RELATIVE_PATH.as_posix()}",
                )
            )
            with (
                patch.object(margin, "__file__", str(historical_path)),
                self.assertRaisesRegex(
                    margin.SelectionMarginAuditError,
                    "runtime import origin drifted: "
                    "qmc_bmgs.experiments.countdown_thompson_selection_margin",
                ),
            ):
                margin._runtime_source_receipts(repository, "HEAD")

    def test_runtime_binding_rejects_posthoc_import_origin_drift(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as raw:
            displaced = Path(raw) / posthoc.MODULE_RELATIVE_PATH.name
            displaced.write_bytes(
                (repository / posthoc.MODULE_RELATIVE_PATH).read_bytes()
            )
            with (
                patch.object(posthoc, "__file__", str(displaced)),
                self.assertRaisesRegex(
                    margin.SelectionMarginAuditError,
                    f"runtime import origin drifted: {posthoc.__name__}",
                ),
            ):
                margin._runtime_source_receipts(repository, "HEAD")

    def test_self_test_opens_no_diagnostic(self) -> None:
        with patch.object(margin, "build_receipt") as build:
            self.assertEqual(margin.main(["--self-test"]), 0)
        build.assert_not_called()

    def test_missing_input_is_canonical_invalid_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                status = margin.main(_cli_arguments(Path(raw)))
        payload = json.loads(stderr.getvalue())
        self.assertEqual(status, 2)
        self.assertEqual(payload["status"], "INVALID")
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_occupied_output_is_canonical_invalid_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            stderr = io.StringIO()
            with (
                patch.object(
                    margin,
                    "build_receipt",
                    return_value={"deterministic_digest": "d" * 64},
                ),
                patch.object(
                    posthoc,
                    "_write_no_overwrite",
                    side_effect=posthoc.PosthocMechanismAuditError(
                        "output already exists"
                    ),
                ),
                redirect_stderr(stderr),
            ):
                status = margin.main(_cli_arguments(Path(raw)))
        payload = json.loads(stderr.getvalue())
        self.assertEqual(status, 2)
        self.assertEqual(payload["status"], "INVALID")
        self.assertNotIn("Traceback", stderr.getvalue())


class SelectionMarginPublishedReceiptTests(unittest.TestCase):
    def test_tracked_receipt_is_canonical_and_source_bound(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        path = (
            repository
            / "docs/results/countdown_thompson_diagnostic_v1/selection_margin_v1.json"
        )
        expected_digest = (
            "5457effcf523d9a36d8824e86e17c067c3a3af1d5f1056255c1ff9ba726a406c"
        )
        expected_raw_sha256 = (
            "70504c87e43d42bf786727ddca6822f6f45366c664eff153e99f2a65895d2d97"
        )
        expected_source_revision = "64fda29cac2499bf42e749d721d3c08742bac038"
        expected_module_sha256 = (
            "c5e4a6f96605258d2969410fb19245674d3a5062d1d1b72a34fb5eabedd3a441"
        )
        expected_design_sha256 = (
            "9c92292769b0395c7c818fe4032713b4018ecd319ba4b9d583d98e557c4a5509"
        )

        payload, raw = posthoc._read_strict_json_object(
            path, "tracked selection-margin receipt"
        )
        core = {
            key: value
            for key, value in payload.items()
            if key != "deterministic_digest"
        }
        self.assertEqual(raw, (canonical_json(payload) + "\n").encode())
        self.assertEqual(len(raw), 2_000_231)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), expected_raw_sha256)
        self.assertEqual(payload["deterministic_digest"], expected_digest)
        self.assertEqual(sha256_json(core), expected_digest)
        self.assertEqual(payload["schema_version"], margin.SCHEMA_VERSION)
        self.assertEqual(payload["integrity_status"], "PASS")
        self.assertEqual(payload["handoff_decision"], margin.HANDOFF_DECISION)

        provenance = payload["input_provenance"]
        self.assertEqual(
            provenance["artifact_commit_digest"],
            margin.FROZEN_ARTIFACT_COMMIT_DIGEST,
        )
        self.assertEqual(
            provenance["authorization_digest"],
            margin.FROZEN_AUTHORIZATION_DIGEST,
        )
        self.assertEqual(
            provenance["authorization_revision"],
            margin.FROZEN_AUTHORIZATION_REVISION,
        )
        self.assertEqual(
            provenance["run_manifest_digest"], margin.FROZEN_RUN_MANIFEST_DIGEST
        )
        self.assertEqual(
            provenance["summary_deterministic_digest"],
            margin.FROZEN_SUMMARY_DIGEST,
        )
        self.assertEqual(
            provenance["posthoc_receipt_deterministic_digest"],
            margin.FROZEN_POSTHOC_DIGEST,
        )
        self.assertEqual(
            provenance["posthoc_receipt_raw_sha256"],
            margin.FROZEN_POSTHOC_RAW_SHA256,
        )

        source = payload["source_attestation"]
        self.assertEqual(source["source_revision"], expected_source_revision)
        self.assertEqual(source["audit_module_sha256"], expected_module_sha256)
        self.assertEqual(source["frozen_design_sha256"], expected_design_sha256)
        module_raw = (repository / margin.MODULE_RELATIVE_PATH).read_bytes()
        design_raw = (repository / margin.DESIGN_RELATIVE_PATH).read_bytes()
        self.assertEqual(hashlib.sha256(module_raw).hexdigest(), expected_module_sha256)
        self.assertEqual(hashlib.sha256(design_raw).hexdigest(), expected_design_sha256)
        self.assertEqual(
            margin._git(
                repository,
                "show",
                f"{expected_source_revision}:{margin.MODULE_RELATIVE_PATH.as_posix()}",
            ),
            module_raw,
        )
        self.assertEqual(
            margin._git(
                repository,
                "show",
                f"{expected_source_revision}:{margin.DESIGN_RELATIVE_PATH.as_posix()}",
            ),
            design_raw,
        )

        reductions = payload["reductions"]
        paired = reductions["paired_v2_v3_common_prefix_sensitivity"]
        individual = reductions["individual_method_selection_sensitivity"]
        self.assertEqual(paired["pairable_surface_count"], 370)
        self.assertEqual(paired["nonzero_score_displacement_surface_count"], 94)
        self.assertEqual(paired["action_flip_count_at_observed_dense_scale"], 4)
        self.assertEqual(
            individual[margin.V4_METHOD][
                "observed_action_changed_from_zero_mean_count"
            ],
            128,
        )
        self.assertFalse(reductions["performance_counterfactual_evaluated"])
        self.assertFalse(reductions["terminal_outcomes_used_in_margin_reduction"])


if __name__ == "__main__":
    unittest.main()
