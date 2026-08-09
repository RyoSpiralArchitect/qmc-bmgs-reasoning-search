from __future__ import annotations

import copy
import unittest

from qmc_bmgs.substrate.budget import (
    TRACK_A_WORK_AXES,
    TrackABudgetExceeded,
    TrackAWorkBudget,
    TrackAWorkLedger,
)


def _budget(**overrides: int) -> TrackAWorkBudget:
    values = {axis: 100 for axis in TRACK_A_WORK_AXES}
    values.update(overrides)
    return TrackAWorkBudget(**values)


class TrackAWorkBudgetTests(unittest.TestCase):
    def test_budget_rejects_bool_non_integer_and_negative_limits(self) -> None:
        for value in (True, 1.5, -1):
            with self.subTest(value=value):
                values = {axis: 1 for axis in TRACK_A_WORK_AXES}
                values["legal_action_scores"] = value  # type: ignore[assignment]
                with self.assertRaisesRegex(ValueError, "legal_action_scores"):
                    TrackAWorkBudget(**values)

    def test_successful_atomic_charge_and_full_snapshot(self) -> None:
        ledger = TrackAWorkLedger(_budget())
        receipt = ledger.charge(
            proposal_state_evaluations=1,
            proposal_action_scores=53,
        )
        ledger.observe_live_storage(live_nodes=8, live_bytes=4096)
        ledger.observe_live_storage(live_nodes=3, live_bytes=1024)

        snapshot = ledger.snapshot()
        self.assertEqual(receipt.charge_index, 0)
        self.assertEqual(dict(receipt.increments)["proposal_action_scores"], 53)
        self.assertEqual(snapshot["charge_count"], 1)
        self.assertEqual(snapshot["usage"]["proposal_state_evaluations"], 1)
        self.assertEqual(snapshot["usage"]["proposal_action_scores"], 53)
        self.assertEqual(snapshot["live_storage"], {"bytes": 1024, "nodes": 3})
        self.assertEqual(
            snapshot["peak_live_storage"],
            {"bytes": 4096, "nodes": 8},
        )
        self.assertEqual(snapshot["overshoot"], 0)
        self.assertEqual(set(snapshot["limits"]), set(TRACK_A_WORK_AXES))
        self.assertEqual(set(snapshot["usage"]), set(TRACK_A_WORK_AXES))
        self.assertEqual(set(snapshot["remaining"]), set(TRACK_A_WORK_AXES))

    def test_failed_multi_axis_charge_changes_no_snapshot_field(self) -> None:
        ledger = TrackAWorkLedger(
            _budget(legal_action_scores=5, transitions=1)
        )
        ledger.charge(legal_action_scores=2)
        ledger.observe_live_storage(live_nodes=4, live_bytes=2048)
        before = copy.deepcopy(ledger.snapshot())

        with self.assertRaises(TrackABudgetExceeded) as caught:
            ledger.charge(
                legal_action_scores=4,
                edge_selections=1,
                transitions=2,
            )

        self.assertEqual(
            caught.exception.blocked_axes,
            ("legal_action_scores", "transitions"),
        )
        self.assertEqual(ledger.snapshot(), before)

    def test_selection_helpers_charge_closed_work_bundles(self) -> None:
        ledger = TrackAWorkLedger(_budget())
        first = ledger.charge_selection(7)
        second = ledger.charge_perturbed_selection(53)
        usage = ledger.snapshot()["usage"]

        self.assertEqual(first.charge_index, 0)
        self.assertEqual(second.charge_index, 1)
        self.assertEqual(usage["legal_action_scores"], 60)
        self.assertEqual(usage["generated_perturbation_coordinates"], 53)
        self.assertEqual(usage["edge_selections"], 0)
        self.assertEqual(usage["transitions"], 0)

    def test_perturbed_selection_fails_atomically_before_coordinate_charge(self) -> None:
        ledger = TrackAWorkLedger(
            _budget(
                legal_action_scores=52,
                generated_perturbation_coordinates=100,
            )
        )
        before = ledger.snapshot()

        with self.assertRaises(TrackABudgetExceeded) as caught:
            ledger.charge_perturbed_selection(53)

        self.assertEqual(caught.exception.blocked_axes, ("legal_action_scores",))
        self.assertEqual(ledger.snapshot(), before)

    def test_charge_validation_is_side_effect_free(self) -> None:
        invalid_calls = (
            lambda ledger: ledger.charge(unknown_axis=1),
            lambda ledger: ledger.charge(legal_action_scores=True),
            lambda ledger: ledger.charge(legal_action_scores=1.5),
            lambda ledger: ledger.charge(legal_action_scores=-1),
            lambda ledger: ledger.charge(),
            lambda ledger: ledger.charge(legal_action_scores=0),
            lambda ledger: ledger.charge_selection(0),
            lambda ledger: ledger.charge_perturbed_selection(False),
        )
        for invalid_call in invalid_calls:
            ledger = TrackAWorkLedger(_budget())
            before = ledger.snapshot()
            with self.subTest(call=invalid_call):
                with self.assertRaises((KeyError, ValueError)):
                    invalid_call(ledger)
                self.assertEqual(ledger.snapshot(), before)

    def test_storage_validation_is_side_effect_free(self) -> None:
        ledger = TrackAWorkLedger(_budget())
        ledger.observe_live_storage(live_nodes=2, live_bytes=200)
        before = ledger.snapshot()

        for kwargs in (
            {"live_nodes": True, "live_bytes": 200},
            {"live_nodes": 2.5, "live_bytes": 200},
            {"live_nodes": 2, "live_bytes": -1},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    ledger.observe_live_storage(**kwargs)  # type: ignore[arg-type]
                self.assertEqual(ledger.snapshot(), before)

    def test_exact_limit_closes_without_overshoot(self) -> None:
        ledger = TrackAWorkLedger(
            _budget(
                legal_action_scores=53,
                generated_perturbation_coordinates=53,
            )
        )
        ledger.charge_perturbed_selection(53)
        snapshot = ledger.snapshot()

        for axis in (
            "legal_action_scores",
            "generated_perturbation_coordinates",
        ):
            self.assertIn(axis, snapshot["exhausted_axes"])
            self.assertEqual(snapshot["remaining"][axis], 0)
        self.assertEqual(snapshot["overshoot"], 0)


if __name__ == "__main__":
    unittest.main()
