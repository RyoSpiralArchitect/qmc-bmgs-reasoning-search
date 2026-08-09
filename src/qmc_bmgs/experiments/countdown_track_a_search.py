#!/usr/bin/env python3
"""Download-free all-method self-test for the Track A search harness."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Sequence

from qmc_bmgs.benchmarks.countdown import CountdownTask
from qmc_bmgs.substrate.budget import TRACK_A_WORK_AXES, TrackAWorkBudget
from qmc_bmgs.substrate.countdown_search import (
    TrackABudgetProfile,
    TrackAMethodSpec,
    replay_countdown_track_a_search_bytes,
    run_countdown_track_a_search,
)
from qmc_bmgs.substrate.proposals import TrackAProposalSpec


SELF_TEST_SEED = 7168
SELF_TEST_GUARD = 1_024
SELF_TEST_VERIFIER_CALLS = 2
CLAIM_BOUNDARY = (
    "download-free integration evidence only; no canary was opened and no "
    "method, calibration, or perturbation source superiority is claimed"
)


@dataclass(frozen=True)
class _Variant:
    label: str
    method: TrackAMethodSpec


def _variants() -> tuple[_Variant, ...]:
    return (
        _Variant("greedy", TrackAMethodSpec.greedy()),
        _Variant("beam_width_2", TrackAMethodSpec.beam_width_two()),
        _Variant("puct", TrackAMethodSpec.puct()),
        _Variant(
            "thompson_frozen_iid",
            TrackAMethodSpec.frozen_thompson("iid"),
        ),
        _Variant(
            "thompson_frozen_sobol",
            TrackAMethodSpec.frozen_thompson("sobol"),
        ),
        _Variant(
            "thompson_candidate_iid",
            TrackAMethodSpec.candidate_thompson("iid"),
        ),
        _Variant(
            "thompson_candidate_sobol",
            TrackAMethodSpec.candidate_thompson("sobol"),
        ),
        _Variant(
            "thompson_dimension_normalized_iid",
            TrackAMethodSpec.dimension_normalized_thompson("iid"),
        ),
        _Variant(
            "thompson_dimension_normalized_sobol",
            TrackAMethodSpec.dimension_normalized_thompson("sobol"),
        ),
        _Variant(
            "thompson_dimension_normalized_dense_iid",
            TrackAMethodSpec.dimension_normalized_dense_thompson("iid"),
        ),
        _Variant(
            "thompson_dimension_normalized_dense_sobol",
            TrackAMethodSpec.dimension_normalized_dense_thompson("sobol"),
        ),
        _Variant(
            "thompson_greedy_anchor_dense_iid",
            (
                TrackAMethodSpec.greedy_anchored_dimension_normalized_dense_thompson(
                    "iid"
                )
            ),
        ),
        _Variant(
            "thompson_greedy_anchor_dense_sobol",
            (
                TrackAMethodSpec.greedy_anchored_dimension_normalized_dense_thompson(
                    "sobol"
                )
            ),
        ),
    )


def _budget_profile() -> TrackABudgetProfile:
    limits = {axis: SELF_TEST_GUARD for axis in TRACK_A_WORK_AXES}
    limits["verifier_calls"] = SELF_TEST_VERIFIER_CALLS
    return TrackABudgetProfile(
        profile_id="track_a_search_self_test_verifier2",
        primary_axis="verifier_calls",
        budget=TrackAWorkBudget(**limits),
    )


def _root_score_count(record: dict[str, object], root_state: list[int]) -> int:
    events = record.get("events")
    if type(events) is not list:
        raise AssertionError("search trace events drifted")
    for event in events:
        if type(event) is not dict:
            continue
        kind = event.get("kind")
        payload = event.get("payload")
        charge = event.get("charge")
        if kind == "selection_committed" and type(payload) is dict:
            if payload.get("state") == root_state:
                scored = payload.get("scored_action_indices")
                if type(scored) is not list:
                    raise AssertionError("root selection score evidence drifted")
                return len(scored)
        if kind == "beam_layer_selection_committed" and type(payload) is dict:
            if payload.get("layer_index") == 0:
                if type(charge) is not dict or type(charge.get("delta")) is not dict:
                    raise AssertionError("root beam charge evidence drifted")
                value = charge["delta"].get("legal_action_scores")
                if type(value) is not int:
                    raise AssertionError("root beam score count drifted")
                return value
    raise AssertionError("search trace does not contain a root selection")


def _anchor_score_count(record: dict[str, object]) -> int:
    events = record.get("events")
    if type(events) is not list:
        raise AssertionError("search trace events drifted")
    total = 0
    for event in events:
        if type(event) is not dict or event.get("kind") != "selection_committed":
            continue
        payload = event.get("payload")
        if type(payload) is not dict or payload.get("trajectory_index") != 0:
            continue
        semantics = payload.get("selection_semantics")
        if type(semantics) is not dict:
            continue
        if semantics.get("selection_phase") != "greedy_anchor":
            continue
        scored = payload.get("scored_action_indices")
        point_digest = payload.get("point_digest")
        charge = event.get("charge")
        if (
            type(scored) is not list
            or point_digest is not None
            or type(charge) is not dict
            or type(charge.get("delta")) is not dict
            or charge["delta"].get("generated_perturbation_coordinates") != 0
        ):
            raise AssertionError("greedy-anchor coordinate evidence drifted")
        total += len(scored)
    return total


def _self_test() -> dict[str, object]:
    task = CountdownTask((1, 2, 3, 4, 5, 6), target=720)
    proposal = TrackAProposalSpec("greedy_rollout_target_error/v1")
    profile = _budget_profile()
    root_actions = task.legal_actions(task.initial_state)
    if len(root_actions) != 53:
        raise AssertionError("53-action self-test fixture drifted")

    rows: list[dict[str, object]] = []
    for variant in _variants():
        seed = SELF_TEST_SEED if variant.method.stochastic else 0
        result = run_countdown_track_a_search(
            task,
            proposal=proposal,
            method=variant.method,
            budget_profile=profile,
            exploration_seed=seed,
        )
        usage = result.summary["ledger_usage"]
        if type(usage) is not dict:
            raise AssertionError("search ledger summary drifted")
        if result.summary["terminal_count"] < 1:
            raise AssertionError(f"{variant.label} did not reach a terminal")
        if result.summary["budget_valid"] is not True:
            raise AssertionError(f"{variant.label} bound a non-primary guard")
        if _root_score_count(result.record, list(task.initial_state)) != 53:
            raise AssertionError(f"{variant.label} truncated the root action set")

        coordinates = usage["generated_perturbation_coordinates"]
        legal_scores = usage["legal_action_scores"]
        if variant.method.greedy_anchor_trajectory_count == 1:
            anchor_scores = _anchor_score_count(result.record)
            if anchor_scores <= 0 or coordinates != legal_scores - anchor_scores:
                raise AssertionError(
                    f"{variant.label} anchor coordinate work did not close"
                )
            coordinate_contract = "coordinates_exclude_greedy_anchor_scores"
        elif variant.method.stochastic:
            if coordinates != legal_scores or coordinates <= 0:
                raise AssertionError(
                    f"{variant.label} perturbation/selection work did not close"
                )
            coordinate_contract = "coordinates_equal_legal_scores"
        else:
            if coordinates != 0:
                raise AssertionError(
                    f"{variant.label} generated deterministic perturbations"
                )
            coordinate_contract = "deterministic_coordinates_zero"

        replayed = replay_countdown_track_a_search_bytes(
            result.canonical_bytes,
            task=task,
            proposal=proposal,
            method=variant.method,
            budget_profile=profile,
            exploration_seed=seed,
            expected_run_identity_digest=result.run_identity_digest,
        )
        if replayed != result.canonical_bytes:
            raise AssertionError(f"{variant.label} two-stage replay drifted")

        rows.append(
            {
                "budget_valid": True,
                "coordinate_contract": coordinate_contract,
                "label": variant.label,
                "method_id": variant.method.method_id,
                "root_action_count": 53,
                "run_identity_digest": result.run_identity_digest,
                "selected_source": variant.method.selected_source,
                "stage1_and_stage2_replay": "PASS",
                "stop_reason": result.summary["stop_reason"],
                "terminal_count": result.summary["terminal_count"],
                "trace_digest": result.record["deterministic_digest"],
            }
        )

    return {
        "claim_boundary": CLAIM_BOUNDARY,
        "fixture": {"inputs": list(task.inputs), "target": task.target},
        "proposal_policy_id": proposal.policy_id,
        "root_action_count": len(root_actions),
        "status": "PASS",
        "variant_count": len(rows),
        "variants": rows,
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run thirteen local methods through two-stage byte replay",
    )
    args = parser.parse_args(argv)
    if not args.self_test:
        parser.error("this milestone exposes --self-test only")
    print(json.dumps(_self_test(), sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
