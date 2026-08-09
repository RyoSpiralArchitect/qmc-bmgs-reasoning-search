#!/usr/bin/env python3
"""Download-free self-test for the provider-neutral Track A substrate."""

from __future__ import annotations

import argparse
import json
from typing import Sequence

from qmc_bmgs.benchmarks.countdown import CountdownTask
from qmc_bmgs.substrate import (
    TRACK_A_WORK_AXES,
    HashChainedTrace,
    LazyNormalSource,
    TrackAWorkBudget,
    TrackAWorkLedger,
    build_perturbation_run_identity,
    canonical_trace_bytes,
    perturbation_run_identity_digest,
    replay_perturbation_trace_bytes,
)


def _self_test() -> dict[str, object]:
    task = CountdownTask((1, 2, 3, 4, 5, 6), target=100)
    actions = task.legal_actions(task.initial_state)
    if len(actions) != 53:
        raise AssertionError("dynamic-dimension fixture drifted")
    limits = {axis: 128 for axis in TRACK_A_WORK_AXES}
    limits["legal_action_scores"] = 0
    limits["generated_perturbation_coordinates"] = len(actions)
    budget = TrackAWorkBudget(**limits)
    ledger = TrackAWorkLedger(budget)
    run_identity = build_perturbation_run_identity(
        source="sobol",
        exploration_seed=7168,
        tasks=(task,),
        work_budget=budget,
        budget_profile="substrate_self_test",
        method_id="substrate_self_test",
        configuration_id="none",
    )
    trace = HashChainedTrace(run_identity)
    source = LazyNormalSource(
        source="sobol",
        exploration_seed=7168,
        trace=trace,
        tasks=(task,),
    )
    draw = source.draw(
        task=task,
        state=task.initial_state,
        actions=actions,
        ledger=ledger,
    )
    snapshot = ledger.snapshot()
    if snapshot["usage"]["legal_action_scores"] != 0:
        raise AssertionError("perturbation source charged selection scores")
    record = trace.finalize(snapshot)
    payload = canonical_trace_bytes(record)
    replayed = replay_perturbation_trace_bytes(
        payload,
        tasks=(task,),
        expected_run_identity_digest=perturbation_run_identity_digest(
            run_identity
        ),
    )
    if replayed != payload:
        raise AssertionError("Track A substrate replay drifted")
    return {
        "action_count": len(actions),
        "generated_coordinates": len(draw.normals),
        "materialized_nodes": source.materialized_node_count,
        "point_count": source.point_count,
        "legal_action_scores": snapshot["usage"]["legal_action_scores"],
        "status": "PASS",
        "trace_digest": record["deterministic_digest"],
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the download-free 53-action lazy replay test",
    )
    args = parser.parse_args(argv)
    if not args.self_test:
        parser.error("this substrate milestone currently exposes --self-test only")
    print(json.dumps(_self_test(), sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
