from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from qmc_bmgs.experiments import countdown_thompson_posthoc_mechanism as posthoc
from qmc_bmgs.substrate.trace import canonical_json, sha256_json


def _selection(
    trajectory: int,
    action_index: int,
    *,
    method: str,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "action_index": action_index,
        "child_state": [trajectory, action_index],
        "depth": 0,
        "state": [trajectory, 9],
        "trajectory_index": trajectory,
    }
    if method == posthoc.V4_METHOD:
        payload["selection_semantics"] = {
            "selection_phase": (
                "greedy_anchor" if trajectory == 0 else "posterior_perturbation"
            )
        }
    return {"kind": "selection_committed", "payload": payload}


def _terminal(trajectory: int, error: int) -> dict[str, object]:
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


def _backup(trajectory: int) -> dict[str, object]:
    return {
        "kind": "trajectory_backed_up",
        "payload": {
            "trajectory_index": trajectory,
            "updates": [
                {
                    "after": {"mean": 1.0},
                    "before": {"mean": 0.0},
                    "depth": 0,
                }
            ],
        },
    }


def _record(
    method: str,
    task: str,
    seed: int,
    *,
    first_error: int,
    post_error: int | None,
    post_action: int = 0,
) -> dict[str, object]:
    events: list[dict[str, object]] = [
        _selection(0, 0, method=method),
        _terminal(0, first_error),
        _backup(0),
        _selection(1, post_action, method=method),
    ]
    errors = [first_error]
    if post_error is not None:
        events.extend((_terminal(1, post_error), _backup(1)))
        errors.append(post_error)
        events.append(_selection(2, 0, method=method))
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
        "search_summary": {"success_any": 0 in errors},
    }


def _records() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    index = 0
    for task_index in range(posthoc.EXPECTED_TASK_COUNT):
        task = f"task-{task_index:02d}"
        for seed in posthoc.EXPECTED_SEEDS:
            v3_error = 0 if index == 0 else 5 if index < 16 else 10 if index < 32 else 15
            records.append(
                _record(
                    posthoc.V2_METHOD,
                    task,
                    seed,
                    first_error=10,
                    post_error=10,
                )
            )
            records.append(
                _record(
                    posthoc.V3_METHOD,
                    task,
                    seed,
                    first_error=10,
                    post_error=v3_error,
                    post_action=1 if index < 40 else 0,
                )
            )
            if index < 8:
                anchor_error = 0
                v4_post = 0 if index == 0 else 2
            else:
                anchor_error = 10
                v4_post = (
                    0
                    if index == 8
                    else 5
                    if index < 20
                    else 10
                    if index < 30
                    else 15
                    if index < 40
                    else None
                )
            records.append(
                _record(
                    posthoc.V4_METHOD,
                    task,
                    seed,
                    first_error=anchor_error,
                    post_error=v4_post,
                    post_action=1,
                )
            )
            index += 1
    for task_index in range(posthoc.EXPECTED_TASK_COUNT):
        records.append(
            _record(
                "greedy",
                f"task-{task_index:02d}",
                0,
                first_error=0 if task_index < 2 else 10,
                post_error=None,
            )
        )
    while len(records) < posthoc.EXPECTED_RECORD_COUNT:
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
    summary_core = {"run_manifest_digest": "c" * 64}
    summary_payload = {
        **summary_core,
        "deterministic_digest": sha256_json(summary_core),
    }
    summary = root / "summary.json"
    summary.write_text(canonical_json(summary_payload) + "\n")
    source = {
        "audit_module_sha256": "d" * 64,
        "frozen_design_sha256": "e" * 64,
        "source_revision": "f" * 40,
        "worktree_clean": True,
    }
    verified = SimpleNamespace(
        artifact_commit_digest="b" * 64,
        collective_manifest_digest="1" * 64,
        records=tuple(_records()),
        records_jsonl_bytes=b"synthetic records\n",
        run_manifest_digest="c" * 64,
    )
    return {
        "artifact": artifact,
        "artifact_commit_digest": "b" * 64,
        "authorization": authorization,
        "authorization_digest": authorization_digest,
        "bundle": bundle,
        "repository": repository,
        "source": source,
        "summary": summary,
        "summary_digest": summary_payload["deterministic_digest"],
        "summary_payload": summary_payload,
        "verified": verified,
    }


def _build_fixture_receipt(
    fixture: dict[str, object],
    *,
    recomputed_summary: object | None = None,
    source_side_effect: object | None = None,
    verified: object | None = None,
) -> dict[str, object]:
    summary_payload = fixture["summary_payload"]
    source = fixture["source"]
    with (
        patch.object(
            posthoc,
            "_source_attestation",
            side_effect=source_side_effect,
            return_value=source,
        ),
        patch.object(
            posthoc.analysis,
            "analyze_countdown_thompson_diagnostic_artifact_v2r3",
            return_value=(
                summary_payload
                if recomputed_summary is None
                else recomputed_summary
            ),
        ),
        patch.object(
            posthoc.regular_file_publication,
            "verify_countdown_thompson_diagnostic_v2",
            return_value=fixture["verified"] if verified is None else verified,
        ),
    ):
        return posthoc.build_receipt(
            fixture["artifact"],  # type: ignore[arg-type]
            fixture["bundle"],  # type: ignore[arg-type]
            fixture["authorization"],  # type: ignore[arg-type]
            fixture["authorization_digest"],  # type: ignore[arg-type]
            "2" * 40,
            fixture["summary"],  # type: ignore[arg-type]
            fixture["summary_digest"],  # type: ignore[arg-type]
            fixture["artifact_commit_digest"],  # type: ignore[arg-type]
            repository_root=fixture["repository"],  # type: ignore[arg-type]
        )


class PosthocMechanismReductionTests(unittest.TestCase):
    def test_fixed_pair_and_anchor_reductions(self) -> None:
        result = posthoc.reduce_verified_records(_records())

        paired = result["v2_v3_paired"]
        self.assertEqual(paired["pair_count"], 48)
        self.assertEqual(paired["trajectory_0_selection_identity_equal_count"], 48)
        self.assertEqual(paired["feedback_informed_selection_divergence_count"], 40)
        self.assertEqual(
            paired["v3_error_classification_counts"],
            {"improved": 16, "equal": 16, "worse": 16, "not_comparable": 0},
        )
        self.assertEqual(
            paired["post_first_exact_classification_counts"],
            {"both": 0, "v3_only": 1, "v2_only": 0, "neither": 47},
        )
        self.assertEqual(
            paired["dense_direction_label"], "MIXED_OR_NULL_DENSE_DIRECTION"
        )

        anchor = result["v4_anchor"]
        self.assertEqual(anchor["anchor_success_count"], 8)
        self.assertEqual(anchor["anchor_failure_count"], 40)
        self.assertEqual(anchor["exact_post_anchor_rescue_count"], 1)
        self.assertEqual(
            anchor["anchor_failure_error_classification_counts"],
            {
                "improved": 12,
                "equal": 10,
                "worse": 10,
                "no_post_anchor_terminal": 8,
            },
        )

        exposure = result["feedback_exposure"]
        self.assertEqual(
            exposure[posthoc.V2_METHOD]["backup_count_distribution"], {"2": 48}
        )
        self.assertEqual(
            exposure[posthoc.V3_METHOD][
                "feedback_informed_completed_trajectory_count_distribution"
            ],
            {"1": 48},
        )
        self.assertEqual(
            exposure[posthoc.V4_METHOD]["backup_count_distribution"],
            {"1": 8, "2": 40},
        )

    def test_reduction_is_deterministic(self) -> None:
        left = posthoc.reduce_verified_records(_records())
        right = posthoc.reduce_verified_records(_records())
        self.assertEqual(canonical_json(left), canonical_json(right))

    def test_missing_feedback_selection_is_a_divergence(self) -> None:
        records = _records()
        v3_rows = [
            record
            for record in records
            if record["labels"]["method_label"] == posthoc.V3_METHOD  # type: ignore[index]
        ]
        v3_rows[40]["search_record"]["events"].pop()  # type: ignore[index]
        paired = posthoc.reduce_verified_records(records)["v2_v3_paired"]
        row = next(
            item
            for item in paired["ordered_pair_rows"]
            if item["task_fingerprint"] == "task-10"
            and item["exploration_seed"] == posthoc.EXPECTED_SEEDS[0]
        )
        self.assertEqual(
            row["first_feedback_selection_difference"],
            {"depth": 0, "trajectory_index": 2},
        )

    def test_missing_post_first_terminal_is_not_comparable(self) -> None:
        records = _records()
        v3_rows = [
            record
            for record in records
            if record["labels"]["method_label"] == posthoc.V3_METHOD  # type: ignore[index]
        ]
        events = v3_rows[40]["search_record"]["events"]  # type: ignore[index]
        del events[-3:]
        paired = posthoc.reduce_verified_records(records)["v2_v3_paired"]
        self.assertEqual(paired["v3_error_classification_counts"]["not_comparable"], 1)

    def test_strict_majority_sets_more_improvements_label(self) -> None:
        records = _records()
        v3_rows = [
            record
            for record in records
            if record["labels"]["method_label"] == posthoc.V3_METHOD  # type: ignore[index]
        ]
        for index, record in enumerate(v3_rows):
            terminal = next(
                event
                for event in record["search_record"]["events"]  # type: ignore[index]
                if event["kind"] == "terminal_verified"
                and event["payload"]["trajectory_index"] == 1  # type: ignore[index]
            )
            terminal["payload"]["verification"]["final_value"] = (  # type: ignore[index]
                105 if index < 25 else 110
            )
            terminal["payload"]["verification"]["success"] = False  # type: ignore[index]
            record["search_summary"]["success_any"] = False  # type: ignore[index]
        paired = posthoc.reduce_verified_records(records)["v2_v3_paired"]
        self.assertEqual(
            paired["dense_direction_label"], "MORE_V3_IMPROVEMENTS_IN_ARTIFACT"
        )

    def test_record_count_drift_fails_closed(self) -> None:
        records = _records()
        with self.assertRaisesRegex(
            posthoc.PosthocMechanismAuditError, "record count drifted"
        ):
            posthoc.reduce_verified_records(records[:-1])

    def test_plain_integer_alias_fails_closed(self) -> None:
        records = _records()
        records[0]["labels"]["exploration_seed"] = True  # type: ignore[index]
        with self.assertRaisesRegex(
            posthoc.PosthocMechanismAuditError, "target cell identity drifted"
        ):
            posthoc.reduce_verified_records(records)

    def test_v4_selection_phase_drift_fails_closed(self) -> None:
        records = _records()
        v4 = next(
            record
            for record in records
            if record["labels"]["method_label"] == posthoc.V4_METHOD  # type: ignore[index]
        )
        selection = v4["search_record"]["events"][0]  # type: ignore[index]
        selection["payload"]["selection_semantics"]["selection_phase"] = (  # type: ignore[index]
            "posterior_perturbation"
        )
        with self.assertRaisesRegex(
            posthoc.PosthocMechanismAuditError, "v4 selection phase drifted"
        ):
            posthoc.reduce_verified_records(records)

    def test_no_overwrite_receipt_publication(self) -> None:
        payload = {"deterministic_digest": "a" * 64, "status": "PASS"}
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw) / "receipt.json"
            posthoc._write_no_overwrite(output, payload)
            self.assertEqual(
                output.read_bytes(), (canonical_json(payload) + "\n").encode()
            )
            with self.assertRaisesRegex(
                posthoc.PosthocMechanismAuditError, "already exists"
            ):
                posthoc._write_no_overwrite(output, payload)

    def test_partial_receipt_write_is_removed(self) -> None:
        payload = {"deterministic_digest": "a" * 64, "status": "PASS"}
        original_write = posthoc.os.write
        calls = 0

        def partial_then_fail(descriptor: int, value: object) -> int:
            nonlocal calls
            calls += 1
            if calls == 1:
                return original_write(descriptor, bytes(value)[:1])  # type: ignore[arg-type]
            raise OSError("synthetic partial-write failure")

        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw) / "receipt.json"
            with (
                patch.object(posthoc.os, "write", side_effect=partial_then_fail),
                self.assertRaisesRegex(OSError, "partial-write failure"),
            ):
                posthoc._write_no_overwrite(output, payload)
            self.assertFalse(output.exists())

    def test_build_receipt_composition_and_resolved_paths(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            fixture = _receipt_fixture(Path(raw))
            receipt = _build_fixture_receipt(fixture)
        self.assertEqual(receipt["schema_version"], posthoc.SCHEMA_VERSION)
        self.assertEqual(receipt["integrity_status"], "PASS")
        provenance = receipt["input_provenance"]
        self.assertEqual(
            provenance["path_identity_semantics"], "resolved_absolute_paths/v1"
        )
        self.assertEqual(
            provenance["artifact_path"],
            str(Path(fixture["artifact"]).resolve()),  # type: ignore[arg-type]
        )
        self.assertEqual(receipt["supplemental_validation"]["status"], "PASS")

    def test_equivalent_path_aliases_produce_the_same_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            fixture = _receipt_fixture(Path(raw))
            direct = _build_fixture_receipt(fixture)
            alias = Path(raw) / "artifact-alias.commit.json"
            alias.symlink_to(fixture["artifact"])
            aliased_fixture = {**fixture, "artifact": alias}
            through_alias = _build_fixture_receipt(aliased_fixture)
        self.assertEqual(canonical_json(direct), canonical_json(through_alias))

    def test_build_receipt_rejects_summary_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            fixture = _receipt_fixture(Path(raw))
            with self.assertRaisesRegex(
                posthoc.PosthocMechanismAuditError,
                "summary does not exactly recompute",
            ):
                _build_fixture_receipt(
                    fixture,
                    recomputed_summary={
                        "deterministic_digest": "9" * 64,
                        "run_manifest_digest": "c" * 64,
                    },
                )

    def test_build_receipt_rejects_collective_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            fixture = _receipt_fixture(Path(raw))
            mismatched = SimpleNamespace(
                **{
                    **vars(fixture["verified"]),
                    "artifact_commit_digest": "9" * 64,
                }
            )
            with self.assertRaisesRegex(
                posthoc.PosthocMechanismAuditError,
                "collective provenance drifted",
            ):
                _build_fixture_receipt(fixture, verified=mismatched)

    def test_build_receipt_rejects_source_drift(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            fixture = _receipt_fixture(Path(raw))
            changed = {**fixture["source"], "source_revision": "9" * 40}  # type: ignore[dict-item]
            with self.assertRaisesRegex(
                posthoc.PosthocMechanismAuditError,
                "changed during reduction",
            ):
                _build_fixture_receipt(
                    fixture,
                    source_side_effect=[fixture["source"], changed],
                )

    def test_build_receipt_rejects_second_read_summary_drift(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            fixture = _receipt_fixture(Path(raw))
            original = posthoc._read_strict_json_object

            def read_then_mutate(path: Path, label: str) -> object:
                parsed, payload = original(path, label)
                if label == "published diagnostic summary":
                    path.write_bytes(payload + b" ")
                return parsed, payload

            with (
                patch.object(
                    posthoc,
                    "_read_strict_json_object",
                    side_effect=read_then_mutate,
                ),
                self.assertRaisesRegex(
                    posthoc.PosthocMechanismAuditError,
                    "changed during reduction",
                ),
            ):
                _build_fixture_receipt(fixture)


if __name__ == "__main__":
    unittest.main()
