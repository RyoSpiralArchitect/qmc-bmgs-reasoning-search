from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from qmc_bmgs.benchmarks.countdown import CountdownTask
from qmc_bmgs.substrate.budget import (
    TRACK_A_WORK_AXES,
    TrackABudgetExceeded,
    TrackAChargeReceipt,
    TrackAWorkBudget,
    TrackAWorkLedger,
)
from qmc_bmgs.substrate.perturbations import (
    LazyNormalSource,
    TrackARunPoisoned,
    build_perturbation_run_identity,
    generate_perturbation_point,
    perturbation_run_identity_digest,
    replay_perturbation_trace,
)
from qmc_bmgs.substrate.trace import (
    HashChainedTrace,
    TraceValidationError,
    sha256_json,
    validate_trace,
)


ROOT_TASK = CountdownTask((1, 2, 3, 4, 5, 6), target=100)


def _budget(**overrides: int) -> TrackAWorkBudget:
    values = {axis: 10_000 for axis in TRACK_A_WORK_AXES}
    values.update(overrides)
    return TrackAWorkBudget(**values)


def _source(
    budget: TrackAWorkBudget | None = None,
) -> tuple[LazyNormalSource, TrackAWorkLedger, HashChainedTrace]:
    resolved = budget or _budget()
    identity = build_perturbation_run_identity(
        source="sobol",
        exploration_seed=7168,
        tasks=(ROOT_TASK,),
        work_budget=resolved,
        budget_profile="transaction-test",
        method_id="thompson-test",
        configuration_id="prior1-sd1",
    )
    trace = HashChainedTrace(identity)
    return (
        LazyNormalSource(
            source="sobol",
            exploration_seed=7168,
            trace=trace,
            tasks=(ROOT_TASK,),
        ),
        TrackAWorkLedger(resolved),
        trace,
    )


def _commit_one_step(
    source: LazyNormalSource,
    ledger: TrackAWorkLedger,
    trace: HashChainedTrace,
) -> object:
    actions = ROOT_TASK.legal_actions(ROOT_TASK.initial_state)
    plan = source.plan_draw(
        task=ROOT_TASK,
        state=ROOT_TASK.initial_state,
        actions=actions,
    )
    reservation = trace.reserve_event_slots(plan.required_event_slots + 1)
    receipt = ledger.charge_search_step(
        len(actions),
        proposal_cache_miss=True,
        generate_perturbations=True,
    )
    prepared = source.materialize_precharged(
        plan,
        ledger=ledger,
        receipt=receipt,
    )
    events = (
        *prepared.uncharged_events,
        (
            "edge_transition",
            {
                "point_digest": prepared.point["point_digest"],
                "selected_action_index": 0,
            },
        ),
    )
    trace.append_batch(
        events,
        receipt=receipt,
        receipt_event_index=len(events) - 1,
        reservation=reservation,
    )
    return source.commit_prepared(prepared)


class TrackATransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.actions = ROOT_TASK.legal_actions(ROOT_TASK.initial_state)
        self.assertEqual(len(self.actions), 53)

    def test_preflight_and_rejected_combined_charge_are_side_effect_free(self) -> None:
        source, ledger, trace = _source(
            _budget(
                legal_action_scores=52,
                generated_perturbation_coordinates=53,
            )
        )
        plan = source.plan_draw(
            task=ROOT_TASK,
            state=ROOT_TASK.initial_state,
            actions=self.actions,
        )
        reservation = trace.reserve_event_slots(plan.required_event_slots + 1)
        increments = ledger.search_step_increments(
            53,
            proposal_cache_miss=True,
            generate_perturbations=True,
        )
        source_before = copy.deepcopy(source.state_snapshot())
        ledger_before = copy.deepcopy(ledger.snapshot())
        events_before = copy.deepcopy(trace.events)

        self.assertEqual(ledger.preflight(**increments), ("legal_action_scores",))
        self.assertEqual(ledger.snapshot(), ledger_before)
        with self.assertRaises(TrackABudgetExceeded):
            ledger.charge_search_step(
                53,
                proposal_cache_miss=True,
                generate_perturbations=True,
            )
        reservation.cancel()
        source.abort_plan(plan)

        self.assertEqual(source.state_snapshot(), source_before)
        self.assertEqual(ledger.snapshot(), ledger_before)
        self.assertEqual(trace.events, events_before)
        self.assertEqual(trace.reserved_event_slot_count, 0)

    def test_event_capacity_fails_before_combined_charge(self) -> None:
        source, ledger, trace = _source()
        plan = source.plan_draw(
            task=ROOT_TASK,
            state=ROOT_TASK.initial_state,
            actions=self.actions,
        )
        source_before = copy.deepcopy(source.state_snapshot())
        ledger_before = copy.deepcopy(ledger.snapshot())

        with patch(
            "qmc_bmgs.substrate.trace.MAX_TRACE_EVENTS",
            plan.required_event_slots,
        ):
            with self.assertRaisesRegex(TraceValidationError, "capacity"):
                trace.reserve_event_slots(plan.required_event_slots + 1)

        source.abort_plan(plan)
        self.assertEqual(source.state_snapshot(), source_before)
        self.assertEqual(ledger.snapshot(), ledger_before)
        self.assertEqual(trace.event_count, 0)
        self.assertEqual(trace.reserved_event_slot_count, 0)

    def test_plan_generates_no_point_before_combined_receipt(self) -> None:
        source, ledger, trace = _source()
        with patch(
            "qmc_bmgs.substrate.perturbations.generate_perturbation_point",
            wraps=generate_perturbation_point,
        ) as generator:
            plan = source.plan_draw(
                task=ROOT_TASK,
                state=ROOT_TASK.initial_state,
                actions=self.actions,
            )
            generator.assert_not_called()
            reservation = trace.reserve_event_slots(plan.required_event_slots + 1)
            receipt = ledger.charge_search_step(
                53,
                proposal_cache_miss=False,
                generate_perturbations=True,
            )
            prepared = source.materialize_precharged(
                plan,
                ledger=ledger,
                receipt=receipt,
            )
            generator.assert_called_once()

        events = (*prepared.uncharged_events, ("edge_transition", {}))
        trace.append_batch(
            events,
            receipt=receipt,
            receipt_event_index=len(events) - 1,
            reservation=reservation,
        )
        source.commit_prepared(prepared)
        self.assertEqual(source.point_count, 1)

    def test_split_selection_and_coordinate_receipts_poison_search_source(self) -> None:
        source, ledger, trace = _source()
        plan = source.plan_draw(
            task=ROOT_TASK,
            state=ROOT_TASK.initial_state,
            actions=self.actions,
        )
        ledger.charge_selection(53)
        coordinate_receipt = ledger.charge_perturbation_coordinates(53)

        with self.assertRaisesRegex(TrackARunPoisoned, "discard run"):
            source.materialize_precharged(
                plan,
                ledger=ledger,
                receipt=coordinate_receipt,
            )

        self.assertTrue(source.state_snapshot()["poisoned"])
        self.assertEqual(source.point_count, 0)
        self.assertEqual(trace.event_count, 0)
        with self.assertRaisesRegex(TraceValidationError, "poisoned trace"):
            trace.finalize(ledger.snapshot())

    def test_postcharge_generation_failure_poisons_search_source(self) -> None:
        source, ledger, trace = _source()
        plan = source.plan_draw(
            task=ROOT_TASK,
            state=ROOT_TASK.initial_state,
            actions=self.actions,
        )
        receipt = ledger.charge_search_step(
            53,
            proposal_cache_miss=True,
            generate_perturbations=True,
        )
        with patch(
            "qmc_bmgs.substrate.perturbations.generate_perturbation_point",
            side_effect=RuntimeError("injected"),
        ):
            with self.assertRaisesRegex(TrackARunPoisoned, "discard run"):
                source.materialize_precharged(
                    plan,
                    ledger=ledger,
                    receipt=receipt,
                )

        self.assertTrue(source.state_snapshot()["poisoned"])
        self.assertEqual(source.point_count, 0)
        self.assertEqual(trace.event_count, 0)
        with self.assertRaisesRegex(TraceValidationError, "poisoned trace"):
            trace.finalize(ledger.snapshot())

    def test_stale_plan_is_rejected_after_another_plan_commits(self) -> None:
        source, ledger, trace = _source()
        stale = source.plan_draw(
            task=ROOT_TASK,
            state=ROOT_TASK.initial_state,
            actions=self.actions,
        )
        _commit_one_step(source, ledger, trace)

        with self.assertRaisesRegex(ValueError, "stale"):
            source.abort_plan(stale)
        self.assertEqual(source.point_count, 1)
        self.assertFalse(source.state_snapshot()["poisoned"])

    def test_plan_cannot_cross_normal_sources(self) -> None:
        first, _, _ = _source()
        second, _, _ = _source()
        plan = first.plan_draw(
            task=ROOT_TASK,
            state=ROOT_TASK.initial_state,
            actions=self.actions,
        )
        second_before = copy.deepcopy(second.state_snapshot())
        with self.assertRaisesRegex(ValueError, "another normal source"):
            second.abort_plan(plan)
        self.assertEqual(second.state_snapshot(), second_before)

    def test_append_batch_is_atomic_and_receipt_cannot_be_reused(self) -> None:
        _, ledger, trace = _source()
        first_reservation = trace.reserve_event_slots(2)
        receipt = ledger.charge_search_step(
            53,
            proposal_cache_miss=False,
            generate_perturbations=True,
        )
        appended = trace.append_batch(
            (("material", {"value": 1}), ("selection", {"value": 2})),
            receipt=receipt,
            receipt_event_index=1,
            reservation=first_reservation,
        )
        self.assertIsNone(appended[0]["charge"])
        self.assertEqual(appended[1]["charge"]["charge_index"], 0)

        second_reservation = trace.reserve_event_slots(1)
        before = copy.deepcopy(trace.events)
        with self.assertRaisesRegex(TraceValidationError, "not contiguous"):
            trace.append_batch(
                (("receipt_reuse", {}),),
                receipt=receipt,
                receipt_event_index=0,
                reservation=second_reservation,
            )
        self.assertEqual(trace.events, before)
        self.assertEqual(second_reservation.remaining, 1)
        second_reservation.cancel()
        validate_trace(trace.finalize(ledger.snapshot()))

    def test_append_batch_requires_exact_reservation_and_failure_can_poison(
        self,
    ) -> None:
        source, ledger, trace = _source()
        plan = source.plan_draw(
            task=ROOT_TASK,
            state=ROOT_TASK.initial_state,
            actions=self.actions,
        )
        reservation = trace.reserve_event_slots(plan.required_event_slots + 2)
        receipt = ledger.charge_search_step(
            53,
            proposal_cache_miss=False,
            generate_perturbations=True,
        )
        prepared = source.materialize_precharged(
            plan,
            ledger=ledger,
            receipt=receipt,
        )
        events = (*prepared.uncharged_events, ("edge_transition", {}))
        before = copy.deepcopy(trace.events)

        with self.assertRaisesRegex(TraceValidationError, "batch size"):
            trace.append_batch(
                events,
                receipt=receipt,
                receipt_event_index=len(events) - 1,
                reservation=reservation,
            )
        self.assertEqual(trace.events, before)
        self.assertEqual(
            reservation.remaining,
            plan.required_event_slots + 2,
        )

        source.poison_prepared(
            prepared,
            reason_code="accepted_search_batch_failure",
        )
        reservation.cancel()
        self.assertTrue(source.state_snapshot()["poisoned"])
        with self.assertRaisesRegex(TraceValidationError, "poisoned trace"):
            trace.finalize(ledger.snapshot())

    def test_append_batch_rechecks_reentrant_receipt_before_commit(self) -> None:
        _, ledger, trace = _source()
        reservation = trace.reserve_event_slots(1)
        receipt = ledger.charge_search_step(
            53,
            proposal_cache_miss=False,
            generate_perturbations=True,
        )
        original_to_dict = type(receipt).to_dict

        def cancel_during_serialization(value: object) -> dict[str, object]:
            reservation.cancel()
            return original_to_dict(value)  # type: ignore[arg-type]

        before = copy.deepcopy(trace.events)
        with patch.object(type(receipt), "to_dict", cancel_during_serialization):
            with self.assertRaisesRegex(
                TraceValidationError,
                "reservation is not active",
            ):
                trace.append_batch(
                    (("selection", {}),),
                    receipt=receipt,
                    receipt_event_index=0,
                    reservation=reservation,
                )
        self.assertEqual(trace.events, before)
        self.assertEqual(trace.reserved_event_slot_count, 0)

    def test_append_batch_blocks_reentrant_trace_append(self) -> None:
        _, ledger, trace = _source()
        reservation = trace.reserve_event_slots(1)
        receipt = ledger.charge_search_step(
            53,
            proposal_cache_miss=False,
            generate_perturbations=True,
        )
        original_to_dict = type(receipt).to_dict

        def append_during_serialization(value: object) -> dict[str, object]:
            trace.append("reentrant", {})
            return original_to_dict(value)  # type: ignore[arg-type]

        before = copy.deepcopy(trace.events)
        with patch.object(type(receipt), "to_dict", append_during_serialization):
            with self.assertRaisesRegex(
                TraceValidationError,
                "reentrant trace mutation",
            ):
                trace.append_batch(
                    (("selection", {}),),
                    receipt=receipt,
                    receipt_event_index=0,
                    reservation=reservation,
                )
        self.assertEqual(trace.events, before)
        self.assertEqual(reservation.remaining, 1)
        reservation.cancel()

    def test_append_batch_bad_receipt_fails_without_trace_mutation(self) -> None:
        _, _, trace = _source()
        reservation = trace.reserve_event_slots(1)
        invalid = TrackAChargeReceipt(
            charge_index=0,
            increments=(("bogus", 1),),
            usage_after=(("bogus", 1),),
        )
        before = copy.deepcopy(trace.events)
        with self.assertRaisesRegex(TraceValidationError, "axes"):
            trace.append_batch(
                (("selection", {}),),
                receipt=invalid,
                receipt_event_index=0,
                reservation=reservation,
            )
        self.assertEqual(trace.events, before)
        self.assertEqual(reservation.remaining, 1)
        reservation.cancel()

    def test_commit_requires_uncharged_point_and_later_receipt_owner(self) -> None:
        source, ledger, trace = _source()
        plan = source.plan_draw(
            task=ROOT_TASK,
            state=ROOT_TASK.initial_state,
            actions=self.actions,
        )
        reservation = trace.reserve_event_slots(plan.required_event_slots + 1)
        receipt = ledger.charge_search_step(
            53,
            proposal_cache_miss=False,
            generate_perturbations=True,
        )
        prepared = source.materialize_precharged(
            plan,
            ledger=ledger,
            receipt=receipt,
        )
        events = (*prepared.uncharged_events, ("selection", {}))
        point_offset = 1 if prepared.node_materialized else 0
        trace.append_batch(
            events,
            receipt=receipt,
            receipt_event_index=point_offset,
            reservation=reservation,
        )

        with self.assertRaisesRegex(TrackARunPoisoned, "discard run"):
            source.commit_prepared(prepared)
        self.assertTrue(source.state_snapshot()["poisoned"])
        self.assertEqual(source.point_count, 0)

    def test_validated_stored_material_override_commits_uncharged_events(
        self,
    ) -> None:
        source, ledger, trace = _source()
        plan = source.plan_draw(
            task=ROOT_TASK,
            state=ROOT_TASK.initial_state,
            actions=self.actions,
        )
        node, point = generate_perturbation_point(
            task=ROOT_TASK,
            state=ROOT_TASK.initial_state,
            actions=self.actions,
            source="sobol",
            exploration_seed=7168,
            node_visit_index=0,
        )
        validated = source.validate_stored_material_for_replay(
            plan,
            node=node,
            point=point,
        )
        reservation = trace.reserve_event_slots(plan.required_event_slots + 1)
        receipt = ledger.charge_search_step(
            53,
            proposal_cache_miss=False,
            generate_perturbations=True,
        )
        prepared = source.materialize_precharged(
            plan,
            ledger=ledger,
            receipt=receipt,
            stored_material=validated,
        )
        self.assertTrue(prepared.used_stored_material)
        events = (*prepared.uncharged_events, ("edge_transition", {}))
        trace.append_batch(
            events,
            receipt=receipt,
            receipt_event_index=len(events) - 1,
            reservation=reservation,
        )
        source.commit_prepared(prepared)
        self.assertTrue(
            all(event["charge"] is None for event in trace.events[:-1])
        )

    def test_stored_material_tamper_fails_before_charge(self) -> None:
        source, ledger, trace = _source()
        plan = source.plan_draw(
            task=ROOT_TASK,
            state=ROOT_TASK.initial_state,
            actions=self.actions,
        )
        node, point = generate_perturbation_point(
            task=ROOT_TASK,
            state=ROOT_TASK.initial_state,
            actions=self.actions,
            source="sobol",
            exploration_seed=7168,
            node_visit_index=0,
        )
        point["normals"][0] += 1.0
        before_source = copy.deepcopy(source.state_snapshot())
        before_ledger = copy.deepcopy(ledger.snapshot())
        with self.assertRaisesRegex(TraceValidationError, "independent validation"):
            source.validate_stored_material_for_replay(
                plan,
                node=node,
                point=point,
            )
        self.assertEqual(source.state_snapshot(), before_source)
        self.assertEqual(ledger.snapshot(), before_ledger)
        self.assertEqual(trace.event_count, 0)

    def test_base_trace_accepts_none_but_perturbation_identity_rejects_it(self) -> None:
        budget = _budget()
        identity = build_perturbation_run_identity(
            source="iid",
            exploration_seed=0,
            tasks=(ROOT_TASK,),
            work_budget=budget,
            budget_profile="deterministic-test",
            method_id="greedy",
            configuration_id="greedy-v1",
        )
        identity["selected_source"] = "none"
        trace = HashChainedTrace(identity)
        record = trace.finalize(TrackAWorkLedger(budget).snapshot())
        validate_trace(record)
        with self.assertRaisesRegex(ValueError, "source must be"):
            perturbation_run_identity_digest(identity)
        with self.assertRaisesRegex(ValueError, "source must be"):
            replay_perturbation_trace(
                record,
                tasks=(ROOT_TASK,),
                expected_run_identity_digest=sha256_json(identity),
            )


if __name__ == "__main__":
    unittest.main()
