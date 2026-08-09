from __future__ import annotations

import copy
import json
import unittest
from unittest.mock import patch

import torch
from torch.quasirandom import SobolEngine

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
    SOBOL_GENERATOR_VERSION,
    TrackARunPoisoned,
    _open_unit_hash,
    _open_unit_from_digest,
    _sobol_uniforms,
    build_perturbation_run_identity,
    generate_perturbation_point,
    perturbation_run_identity_digest,
    replay_perturbation_trace_bytes,
)
from qmc_bmgs.substrate.trace import (
    HashChainedTrace,
    TraceValidationError,
    canonical_trace_bytes,
    sha256_json,
    validate_trace,
    validate_trace_bytes,
)


ROOT_TASK = CountdownTask((1, 2, 3, 4, 5, 6), target=100)


def _budget(**overrides: int) -> TrackAWorkBudget:
    values = {axis: 10_000 for axis in TRACK_A_WORK_AXES}
    values.update(overrides)
    return TrackAWorkBudget(**values)


def _source(
    *,
    source: str = "sobol",
    seed: int = 7168,
    budget: TrackAWorkBudget | None = None,
    task: CountdownTask = ROOT_TASK,
    method_id: str = "test_method",
    configuration_id: str = "test_configuration",
) -> tuple[LazyNormalSource, TrackAWorkLedger, HashChainedTrace]:
    resolved = budget or _budget()
    run_identity = build_perturbation_run_identity(
        source=source,
        exploration_seed=seed,
        tasks=(task,),
        work_budget=resolved,
        budget_profile="test",
        method_id=method_id,
        configuration_id=configuration_id,
    )
    trace = HashChainedTrace(run_identity)
    return (
        LazyNormalSource(
            source=source,
            exploration_seed=seed,
            trace=trace,
            tasks=(task,),
        ),
        TrackAWorkLedger(resolved),
        trace,
    )


def _rehash_trace(record: dict[str, object]) -> None:
    events = record["events"]
    assert isinstance(events, list)
    previous = "0" * 64
    for index, event in enumerate(events):
        assert isinstance(event, dict)
        event["index"] = index
        event["previous_event_digest"] = previous
        core = {key: value for key, value in event.items() if key != "event_digest"}
        event["event_digest"] = sha256_json(core)
        previous = event["event_digest"]
    record["event_count"] = len(events)
    record["final_event_digest"] = previous
    core = {
        key: value for key, value in record.items() if key != "deterministic_digest"
    }
    record["deterministic_digest"] = sha256_json(core)


def _rehash_trace_preserving_counter_fields(record: dict[str, object]) -> None:
    events = record["events"]
    assert isinstance(events, list)
    previous = "0" * 64
    for event in events:
        assert isinstance(event, dict)
        event["previous_event_digest"] = previous
        core = {key: value for key, value in event.items() if key != "event_digest"}
        event["event_digest"] = sha256_json(core)
        previous = event["event_digest"]
    record["final_event_digest"] = previous
    core = {
        key: value for key, value in record.items() if key != "deterministic_digest"
    }
    record["deterministic_digest"] = sha256_json(core)


class TrackAPerturbationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.task = ROOT_TASK
        self.actions = self.task.legal_actions(self.task.initial_state)
        self.assertEqual(len(self.actions), 53)

    def test_dynamic_53_action_draw_has_no_padding_and_replays(self) -> None:
        source, ledger, trace = _source(
            budget=_budget(
                legal_action_scores=53,
                generated_perturbation_coordinates=53,
            )
        )
        draw = source.draw(
            task=self.task,
            state=self.task.initial_state,
            actions=self.actions,
            ledger=ledger,
        )

        self.assertEqual(len(draw.uniforms), 53)
        self.assertEqual(len(draw.normals), 53)
        self.assertEqual(draw.node["action_count"], 53)
        self.assertTrue(draw.node_materialized)
        self.assertEqual(source.materialized_node_count, 1)
        self.assertEqual(source.point_count, 1)
        usage = ledger.snapshot()["usage"]
        self.assertEqual(usage["legal_action_scores"], 53)
        self.assertEqual(usage["generated_perturbation_coordinates"], 53)

        record = trace.finalize(ledger.snapshot())
        payload = canonical_trace_bytes(record)
        self.assertEqual(
            replay_perturbation_trace_bytes(
                payload,
                tasks=(self.task,),
                expected_run_identity_digest=perturbation_run_identity_digest(
                    trace.run_identity
                ),
            ),
            payload,
        )

    def test_rejected_charge_consumes_no_node_point_event_or_rng_position(self) -> None:
        source, ledger, trace = _source(
            budget=_budget(
                legal_action_scores=52,
                generated_perturbation_coordinates=53,
            )
        )
        source_before = copy.deepcopy(source.state_snapshot())
        ledger_before = copy.deepcopy(ledger.snapshot())

        with self.assertRaises(TrackABudgetExceeded):
            source.draw(
                task=self.task,
                state=self.task.initial_state,
                actions=self.actions,
                ledger=ledger,
            )

        self.assertEqual(source.state_snapshot(), source_before)
        self.assertEqual(ledger.snapshot(), ledger_before)
        self.assertEqual(trace.event_count, 0)

        _, after_rejection = generate_perturbation_point(
            task=self.task,
            state=self.task.initial_state,
            actions=self.actions,
            source="sobol",
            exploration_seed=7168,
            node_visit_index=0,
        )
        clean_source, clean_ledger, _ = _source()
        clean = clean_source.draw(
            task=self.task,
            state=self.task.initial_state,
            actions=self.actions,
            ledger=clean_ledger,
        )
        self.assertEqual(after_rejection, clean.point)

    def test_random_access_matches_sequence_despite_state_interleaving(self) -> None:
        source, ledger, _ = _source()
        first = source.draw(
            task=self.task,
            state=self.task.initial_state,
            actions=self.actions,
            ledger=ledger,
        )
        child = self.task.transition(self.task.initial_state, self.actions[0])
        child_actions = self.task.legal_actions(child)
        source.draw(
            task=self.task,
            state=child,
            actions=child_actions,
            ledger=ledger,
        )
        second = source.draw(
            task=self.task,
            state=self.task.initial_state,
            actions=self.actions,
            ledger=ledger,
        )

        _, expected_first = generate_perturbation_point(
            task=self.task,
            state=self.task.initial_state,
            actions=self.actions,
            source="sobol",
            exploration_seed=7168,
            node_visit_index=0,
        )
        _, expected_second = generate_perturbation_point(
            task=self.task,
            state=self.task.initial_state,
            actions=self.actions,
            source="sobol",
            exploration_seed=7168,
            node_visit_index=1,
        )
        self.assertEqual(first.point, expected_first)
        self.assertEqual(second.point, expected_second)
        self.assertEqual(source.materialized_node_count, 2)

    def test_stream_identity_excludes_method_config_and_budget_profile(self) -> None:
        first, first_ledger, _ = _source(
            budget=_budget(legal_action_scores=53),
            method_id="candidate_thompson",
            configuration_id="prior1_sd1",
        )
        second, second_ledger, _ = _source(
            budget=_budget(legal_action_scores=999),
            method_id="baseline_thompson",
            configuration_id="prior0.1_sd1",
        )
        first_draw = first.draw(
            task=self.task,
            state=self.task.initial_state,
            actions=self.actions,
            ledger=first_ledger,
        )
        second_draw = second.draw(
            task=self.task,
            state=self.task.initial_state,
            actions=self.actions,
            ledger=second_ledger,
        )
        self.assertEqual(first_draw.node, second_draw.node)
        self.assertEqual(first_draw.point, second_draw.point)

    def test_iid_and_sobol_are_distinct_selected_source_streams(self) -> None:
        iid, iid_ledger, iid_trace = _source(source="iid")
        sobol, sobol_ledger, sobol_trace = _source(source="sobol")
        iid_draw = iid.draw(
            task=self.task,
            state=self.task.initial_state,
            actions=self.actions,
            ledger=iid_ledger,
        )
        sobol_draw = sobol.draw(
            task=self.task,
            state=self.task.initial_state,
            actions=self.actions,
            ledger=sobol_ledger,
        )

        self.assertNotEqual(iid_draw.uniforms, sobol_draw.uniforms)
        self.assertNotEqual(iid_draw.node["stream_identity_digest"], sobol_draw.node["stream_identity_digest"])
        self.assertEqual(iid_trace.event_count, 2)
        self.assertEqual(sobol_trace.event_count, 2)

    def test_full_identity_rotation_separates_low_32_bit_seed_aliases(self) -> None:
        _, first = generate_perturbation_point(
            task=self.task,
            state=self.task.initial_state,
            actions=self.actions,
            source="sobol",
            exploration_seed=1,
            node_visit_index=0,
        )
        _, second = generate_perturbation_point(
            task=self.task,
            state=self.task.initial_state,
            actions=self.actions,
            source="sobol",
            exploration_seed=2**32 + 1,
            node_visit_index=0,
        )
        self.assertNotEqual(first["uniforms"], second["uniforms"])

    def test_open_unit_boundaries_and_persistent_sobol_equivalence(self) -> None:
        lower = _open_unit_from_digest(b"\x00" * 8)
        upper = _open_unit_from_digest(b"\xff" * 8)
        self.assertGreater(lower, 0.0)
        self.assertLess(upper, 1.0)
        self.assertLess(lower, upper)

        node, _ = generate_perturbation_point(
            task=self.task,
            state=self.task.initial_state,
            actions=self.actions,
            source="sobol",
            exploration_seed=7168,
            node_visit_index=0,
        )
        stream_digest = node["stream_identity_digest"]
        shifts = tuple(
            _open_unit_hash(
                {
                    "coordinate": coordinate,
                    "generator_version": SOBOL_GENERATOR_VERSION,
                    "purpose": "cranley_patterson_rotation",
                    "stream_identity_digest": stream_digest,
                }
            )
            for coordinate in range(len(self.actions))
        )
        persistent = SobolEngine(
            dimension=len(self.actions),
            scramble=False,
        ).draw(32, dtype=torch.float64)
        for visit_index, row in enumerate(persistent.tolist()):
            expected = tuple(
                (float(value) + shift) % 1.0
                for value, shift in zip(row, shifts)
            )
            self.assertEqual(
                _sobol_uniforms(stream_digest, visit_index, len(self.actions)),
                expected,
            )
            self.assertTrue(all(0.0 < value < 1.0 for value in expected))

    def test_action_reorder_and_terminal_state_fail_before_charge(self) -> None:
        source, ledger, trace = _source()
        source_before = source.state_snapshot()
        ledger_before = ledger.snapshot()
        with self.assertRaisesRegex(ValueError, "action order"):
            source.draw(
                task=self.task,
                state=self.task.initial_state,
                actions=tuple(reversed(self.actions)),
                ledger=ledger,
            )
        with self.assertRaisesRegex(ValueError, "actionless"):
            source.draw(
                task=self.task,
                state=(1,),
                actions=(),
                ledger=ledger,
            )
        self.assertEqual(source.state_snapshot(), source_before)
        self.assertEqual(ledger.snapshot(), ledger_before)
        self.assertEqual(trace.event_count, 0)

    def test_run_identity_and_ledger_are_bound_before_charge(self) -> None:
        source, ledger, trace = _source()
        mismatched_ledger = TrackAWorkLedger(
            _budget(legal_action_scores=9_999)
        )
        before_source = source.state_snapshot()
        before_ledger = mismatched_ledger.snapshot()
        with self.assertRaisesRegex(ValueError, "sealed run identity"):
            source.draw(
                task=self.task,
                state=self.task.initial_state,
                actions=self.actions,
                ledger=mismatched_ledger,
            )
        self.assertEqual(source.state_snapshot(), before_source)
        self.assertEqual(mismatched_ledger.snapshot(), before_ledger)

        source.draw(
            task=self.task,
            state=self.task.initial_state,
            actions=self.actions,
            ledger=ledger,
        )
        replacement = TrackAWorkLedger(ledger.budget)
        replacement_before = replacement.snapshot()
        with self.assertRaisesRegex(ValueError, "another ledger"):
            source.draw(
                task=self.task,
                state=self.task.initial_state,
                actions=self.actions,
                ledger=replacement,
            )
        self.assertEqual(replacement.snapshot(), replacement_before)
        self.assertEqual(trace.event_count, 2)

    def test_source_and_seed_drift_fail_before_charge(self) -> None:
        source, ledger, trace = _source()
        with self.assertRaises(AttributeError):
            source.source = "iid"  # type: ignore[misc]
        with self.assertRaises(AttributeError):
            source.exploration_seed = 9  # type: ignore[misc]

        source._source = "iid"
        before = ledger.snapshot()
        with self.assertRaisesRegex(TraceValidationError, "drifted"):
            source.draw(
                task=self.task,
                state=self.task.initial_state,
                actions=self.actions,
                ledger=ledger,
            )
        self.assertEqual(ledger.snapshot(), before)
        self.assertEqual(trace.event_count, 0)

        second, second_ledger, second_trace = _source()
        identity_copy = second.run_identity
        identity_copy["selected_source"] = "iid"
        self.assertEqual(second.run_identity["selected_source"], "sobol")
        second_trace.run_identity["selected_source"] = "iid"
        second_before = second_ledger.snapshot()
        with self.assertRaisesRegex(TraceValidationError, "mutated"):
            second.draw(
                task=self.task,
                state=self.task.initial_state,
                actions=self.actions,
                ledger=second_ledger,
            )
        self.assertEqual(second_ledger.snapshot(), second_before)

    def test_external_run_identity_digest_rejects_valid_run_substitution(self) -> None:
        source, ledger, trace = _source()
        source.draw(
            task=self.task,
            state=self.task.initial_state,
            actions=self.actions,
            ledger=ledger,
        )
        payload = canonical_trace_bytes(trace.finalize(ledger.snapshot()))
        substituted_identity = build_perturbation_run_identity(
            source="sobol",
            exploration_seed=7169,
            tasks=(self.task,),
            work_budget=ledger.budget,
            budget_profile="test",
            method_id="test_method",
            configuration_id="test_configuration",
        )
        with self.assertRaisesRegex(TraceValidationError, "sealed run identity"):
            replay_perturbation_trace_bytes(
                payload,
                tasks=(self.task,),
                expected_run_identity_digest=perturbation_run_identity_digest(
                    substituted_identity
                ),
            )

        iid_identity = build_perturbation_run_identity(
            source="iid",
            exploration_seed=7168,
            tasks=(self.task,),
            work_budget=ledger.budget,
            budget_profile="test",
            method_id="test_method",
            configuration_id="test_configuration",
        )
        with self.assertRaisesRegex(TraceValidationError, "source"):
            LazyNormalSource(
                source="sobol",
                exploration_seed=7168,
                trace=HashChainedTrace(iid_identity),
                tasks=(self.task,),
            )

    def test_post_charge_failure_poisons_run_and_cannot_be_finalized(self) -> None:
        source, ledger, trace = _source()
        with patch(
            "qmc_bmgs.substrate.perturbations.generate_perturbation_point",
            side_effect=RuntimeError("injected generation failure"),
        ):
            with self.assertRaisesRegex(TrackARunPoisoned, "discard run"):
                source.draw(
                    task=self.task,
                    state=self.task.initial_state,
                    actions=self.actions,
                    ledger=ledger,
                )
        self.assertTrue(source.state_snapshot()["poisoned"])
        self.assertEqual(source.materialized_node_count, 0)
        self.assertEqual(source.point_count, 0)
        self.assertEqual(trace.event_count, 0)
        usage_after_failure = copy.deepcopy(ledger.snapshot())

        with self.assertRaisesRegex(TrackARunPoisoned, "poisoned"):
            source.draw(
                task=self.task,
                state=self.task.initial_state,
                actions=self.actions,
                ledger=ledger,
            )
        self.assertEqual(ledger.snapshot(), usage_after_failure)
        with self.assertRaisesRegex(TraceValidationError, "poisoned trace"):
            trace.finalize(ledger.snapshot())

    def test_failure_between_node_and_point_events_poison_run(self) -> None:
        source, ledger, trace = _source()
        original_append = trace.append

        def fail_point(kind: str, *args: object, **kwargs: object) -> object:
            if kind == "perturbation_draw":
                raise RuntimeError("injected point append failure")
            return original_append(kind, *args, **kwargs)  # type: ignore[arg-type]

        with patch.object(trace, "append", side_effect=fail_point):
            with self.assertRaisesRegex(TrackARunPoisoned, "discard run"):
                source.draw(
                    task=self.task,
                    state=self.task.initial_state,
                    actions=self.actions,
                    ledger=ledger,
                )
        self.assertTrue(source.state_snapshot()["poisoned"])
        self.assertEqual(source.materialized_node_count, 0)
        self.assertEqual(source.point_count, 0)
        self.assertEqual(trace.event_count, 1)
        with self.assertRaisesRegex(TraceValidationError, "poisoned trace"):
            trace.finalize(ledger.snapshot())

    def test_trace_rejects_invalid_receipt_before_append(self) -> None:
        _, _, trace = _source()
        invalid = TrackAChargeReceipt(
            charge_index=0,
            increments=(("bogus_axis", 1),),
            usage_after=(("bogus_axis", 1),),
        )
        with self.assertRaisesRegex(TraceValidationError, "axes"):
            trace.append("invalid", {}, receipt=invalid)
        self.assertEqual(trace.event_count, 0)

        with self.assertRaisesRegex(TraceValidationError, "fields drifted"):
            HashChainedTrace({"work_limits": _budget().to_dict()})

    def test_generative_replay_rejects_self_consistent_vector_tamper(self) -> None:
        source, ledger, trace = _source()
        source.draw(
            task=self.task,
            state=self.task.initial_state,
            actions=self.actions,
            ledger=ledger,
        )
        record = trace.finalize(ledger.snapshot())
        tampered = copy.deepcopy(record)
        events = tampered["events"]
        self.assertIsInstance(events, list)
        point_event = events[1]
        self.assertIsInstance(point_event, dict)
        point = point_event["payload"]
        self.assertIsInstance(point, dict)
        uniforms = point["uniforms"]
        self.assertIsInstance(uniforms, list)
        uniforms[0] = (uniforms[0] + 0.125) % 1.0
        point["uniform_digest"] = sha256_json(uniforms)
        point_core = {
            key: value for key, value in point.items() if key != "point_digest"
        }
        point["point_digest"] = sha256_json(point_core)
        _rehash_trace(tampered)

        validate_trace(tampered)
        with self.assertRaisesRegex(TraceValidationError, "generative replay"):
            replay_perturbation_trace_bytes(
                canonical_trace_bytes(tampered),
                tasks=(self.task,),
                expected_run_identity_digest=perturbation_run_identity_digest(
                    trace.run_identity
                ),
            )

    def test_replay_rejects_node_integer_type_aliases(self) -> None:
        source, ledger, trace = _source()
        source.draw(
            task=self.task,
            state=self.task.initial_state,
            actions=self.actions,
            ledger=ledger,
        )
        record = trace.finalize(ledger.snapshot())
        mutations = (
            ("action_count_float", "action_count", 53.0),
            ("action_count_bool", "action_count", True),
            ("sobol_maxbit_float", "sobol_maxbit", float(SobolEngine.MAXBIT)),
            ("sobol_maxdim_bool", "sobol_maxdim", True),
        )

        for mutation, field_name, value in mutations:
            tampered = copy.deepcopy(record)
            node = tampered["events"][0]["payload"]
            if field_name == "action_count":
                node[field_name] = value
            else:
                node["generator_metadata"][field_name] = value
            _rehash_trace(tampered)

            with self.subTest(mutation=mutation):
                with self.assertRaisesRegex(
                    TraceValidationError,
                    "plain integer",
                ):
                    replay_perturbation_trace_bytes(
                        canonical_trace_bytes(tampered),
                        tasks=(self.task,),
                        expected_run_identity_digest=(
                            perturbation_run_identity_digest(trace.run_identity)
                        ),
                    )

    def test_trace_rejects_reorder_ledger_tamper_and_noncanonical_json(self) -> None:
        source, ledger, trace = _source()
        source.draw(
            task=self.task,
            state=self.task.initial_state,
            actions=self.actions,
            ledger=ledger,
        )
        record = trace.finalize(ledger.snapshot())

        reordered = copy.deepcopy(record)
        events = reordered["events"]
        self.assertIsInstance(events, list)
        events.reverse()
        with self.assertRaises(TraceValidationError):
            validate_trace(reordered)

        ledger_tamper = copy.deepcopy(record)
        ledger_snapshot = ledger_tamper["ledger_snapshot"]
        self.assertIsInstance(ledger_snapshot, dict)
        usage = ledger_snapshot["usage"]
        self.assertIsInstance(usage, dict)
        usage["legal_action_scores"] += 1
        _rehash_trace(ledger_tamper)
        with self.assertRaisesRegex(TraceValidationError, "event aggregation"):
            validate_trace(ledger_tamper)

        pretty = json.dumps(record, indent=2).encode("utf-8")
        with self.assertRaisesRegex(TraceValidationError, "not canonical"):
            validate_trace_bytes(pretty)
        duplicate = b'{"schema_version":1,"schema_version":1}\n'
        with self.assertRaisesRegex(TraceValidationError, "duplicate"):
            validate_trace_bytes(duplicate)

    def test_trace_rejects_bool_and_float_counter_aliases(self) -> None:
        source, ledger, trace = _source()
        source.draw(
            task=self.task,
            state=self.task.initial_state,
            actions=self.actions,
            ledger=ledger,
        )
        record = trace.finalize(ledger.snapshot())
        mutations = (
            ("event_count", 2.0),
            ("ledger_charge_count", True),
            ("ledger_overshoot", False),
            ("event_index", False),
            ("remaining", 9_947.0),
        )
        for mutation, value in mutations:
            tampered = copy.deepcopy(record)
            if mutation == "event_count":
                tampered["event_count"] = value
            elif mutation == "ledger_charge_count":
                tampered["ledger_snapshot"]["charge_count"] = value
            elif mutation == "ledger_overshoot":
                tampered["ledger_snapshot"]["overshoot"] = value
            elif mutation == "event_index":
                tampered["events"][0]["index"] = value
            else:
                tampered["ledger_snapshot"]["remaining"][
                    "legal_action_scores"
                ] = value
            _rehash_trace_preserving_counter_fields(tampered)
            with self.subTest(mutation=mutation):
                with self.assertRaisesRegex(
                    TraceValidationError,
                    "plain integer",
                ):
                    validate_trace(tampered)

    def test_replay_rejects_recomputed_charge_on_materialization_event(self) -> None:
        source, ledger, trace = _source()
        source.draw(
            task=self.task,
            state=self.task.initial_state,
            actions=self.actions,
            ledger=ledger,
        )
        record = trace.finalize(ledger.snapshot())

        zero_charge = copy.deepcopy(record)
        zero_events = zero_charge["events"]
        self.assertIsInstance(zero_events, list)
        zero_events[0]["charge"] = {
            "charge_index": 0,
            "delta": {axis: 0 for axis in TRACK_A_WORK_AXES},
            "usage_after": {axis: 0 for axis in TRACK_A_WORK_AXES},
        }
        _rehash_trace(zero_charge)
        with self.assertRaisesRegex(TraceValidationError, "positive work"):
            validate_trace(zero_charge)

        semantic_tamper = copy.deepcopy(record)
        events = semantic_tamper["events"]
        self.assertIsInstance(events, list)
        verifier_delta = {axis: 0 for axis in TRACK_A_WORK_AXES}
        verifier_delta["verifier_calls"] = 1
        events[0]["charge"] = {
            "charge_index": 0,
            "delta": verifier_delta,
            "usage_after": dict(verifier_delta),
        }
        point_charge = events[1]["charge"]
        self.assertIsInstance(point_charge, dict)
        point_charge["charge_index"] = 1
        point_usage = point_charge["usage_after"]
        self.assertIsInstance(point_usage, dict)
        point_usage["verifier_calls"] = 1
        ledger_snapshot = semantic_tamper["ledger_snapshot"]
        self.assertIsInstance(ledger_snapshot, dict)
        ledger_snapshot["charge_count"] += 1
        ledger_usage = ledger_snapshot["usage"]
        ledger_remaining = ledger_snapshot["remaining"]
        self.assertIsInstance(ledger_usage, dict)
        self.assertIsInstance(ledger_remaining, dict)
        ledger_usage["verifier_calls"] = 1
        ledger_remaining["verifier_calls"] -= 1
        _rehash_trace(semantic_tamper)

        validate_trace(semantic_tamper)
        with self.assertRaisesRegex(TraceValidationError, "cannot carry work"):
            replay_perturbation_trace_bytes(
                canonical_trace_bytes(semantic_tamper),
                tasks=(self.task,),
                expected_run_identity_digest=perturbation_run_identity_digest(
                    trace.run_identity
                ),
            )


if __name__ == "__main__":
    unittest.main()
