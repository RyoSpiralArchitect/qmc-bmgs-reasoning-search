from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from qmc_bmgs.experiments import countdown_thompson_posthoc_mechanism as posthoc
from qmc_bmgs.substrate.trace import canonical_json


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
        "payload": {"trajectory_index": trajectory, "updates": [{"depth": 0}]},
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
    while len(records) < posthoc.EXPECTED_RECORD_COUNT:
        records.append(
            {
                "labels": {
                    "exploration_seed": 0,
                    "method_label": "greedy",
                    "proposal_label": "heuristic",
                    "task_fingerprint": "unused",
                }
            }
        )
    return records


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


if __name__ == "__main__":
    unittest.main()
