#!/usr/bin/env python3
"""Exploratory two-phase action-source experiment for Role-Lock D4.

This is the single-threshold follow-up predeclared by the fixed-verifier
experiment.  All methods receive exactly 700 search-verifier feedback calls.
The candidate method uses Sobol routing and Sobol action perturbations for
requests 1--256, then retains Sobol routing while changing only action
perturbations to IID for requests 257--700.  The switch occurs after request
256 has been backed up and checkpointed; neither tree/value state nor either
node-local uniform stream is reset.

The threshold was selected after inspecting the preceding cohort, so this is
an exploratory mechanism-localization experiment rather than confirmatory
evidence.  It is intentionally one condition, not a threshold sweep.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import statistics
import time
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable, Sequence

import torch

from qmc_bmgs.benchmarks.role_lock import (
    CHANNEL_ABLATION_VARIANTS,
    BenchmarkPolicy,
    CandidateRegistry,
    CoordinateMuxEngine,
    RoleLockLM,
    RoleLockTask,
    RoleLockTokenizer,
    SeedPlan,
    UniformSourcePlan,
    VariantSpec,
    _search_diagnostics,
    benchmark_config,
)
from qmc_bmgs.experiments.fixed_verifier_budget import (
    _bootstrap_mean_interval,
    _exact_mcnemar_p,
    _holm_adjust,
    _wilson_interval,
)
from qmc_bmgs.records import canonical_record_digest


SCHEMA_VERSION = "qmc-bmgs-two-phase/v1"
METHODS = ("sobol_all", "sobol_routing_only", "two_phase_action_256")
POSTERIOR_SD_SCALE = 1.0
VERIFIER_CAP = 700
LM_NODE_CEILING = 1111
EDGE_CEILING = 3500
REACHABLE_PREFIX_BOUND = sum(9**level for level in range(4))
SWITCH_REQUEST = 256
CHECKPOINTS = (64, 128, 256, 512, 700)
FULL_SEED_START = 640
FULL_SEED_COUNT = 64
BOOTSTRAP_SAMPLES = 5_000

SOBOL_ALL_PLAN = UniformSourcePlan("sobol", "sobol", "sobol")
ROUTING_ONLY_PLAN = UniformSourcePlan("sobol", "sobol", "iid")
SOBOL_PLAN_KEY = "sobol/sobol/sobol"
ROUTING_PLAN_KEY = "sobol/sobol/iid"

COUNTER_INTEGER_FIELDS = (
    "logical_lm_node_evals",
    "physical_lm_forwards",
    "full_prefix_tokens",
    "cache_hits",
    "verifier_requests",
    "verifier_evaluations",
    "evaluation_only_calls",
    "edge_selections",
    "coverage_route_selections",
    "global_route_selections",
    "simulations_started",
    "simulations_completed",
    "budget_leaf_backups",
    "prune_checks",
    "prune_batches",
    "arms_pruned",
    "oracle_optimal_arms_pruned",
    "candidate_misses",
    "random_partition_nodes",
)


def _variant_map() -> dict[str, VariantSpec]:
    available = {variant.name: variant for variant in CHANNEL_ABLATION_VARIANTS}
    variants = {
        "sobol_all": available["sobol_all"],
        "sobol_routing_only": available["sobol_routing_only"],
        "two_phase_action_256": VariantSpec(
            "two_phase_action_256",
            "sobol",
            "embedding",
            False,
            SOBOL_ALL_PLAN,
        ),
    }
    if tuple(variants) != METHODS:
        raise AssertionError("two-phase method order must remain stable")
    return variants


def _correct_prefix_length(readout: Sequence[int], target: Sequence[int]) -> int:
    result = 0
    for observed, expected in zip(readout, target):
        if int(observed) != int(expected):
            break
        result += 1
    return result


def _tensor_values(tensor: torch.Tensor) -> list[Any]:
    values = tensor.detach().cpu().tolist()
    return values if isinstance(values, list) else [values]


def _sha256_json(payload: Any) -> str:
    serialized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(serialized.encode()).hexdigest()


def _has_exact_integer_fields(value: Any, fields: Sequence[str]) -> bool:
    return isinstance(value, dict) and all(
        type(value.get(field)) is int for field in fields
    )


def _is_exact_integer_list(value: Any, *, length: int | None = None) -> bool:
    return (
        isinstance(value, list)
        and (length is None or len(value) == length)
        and all(type(item) is int for item in value)
    )


def _json_exact_equal(observed: Any, expected: Any) -> bool:
    """Compare persisted JSON values without Python's int/float/bool coercions."""
    if type(observed) is not type(expected):
        return False
    if isinstance(expected, dict):
        return set(observed) == set(expected) and all(
            _json_exact_equal(observed[key], expected[key]) for key in expected
        )
    if isinstance(expected, list):
        return len(observed) == len(expected) and all(
            _json_exact_equal(left, right) for left, right in zip(observed, expected)
        )
    return observed == expected


def _generator_digest(generator: torch.Generator) -> str:
    state = generator.get_state().detach().cpu().reshape(-1)
    return hashlib.sha256(bytes(state.tolist())).hexdigest()


def _node_value_payload(policy: BenchmarkPolicy) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for state_key, node in sorted(policy.nodes.items()):
        result.append(
            {
                "state": list(state_key),
                "candidate_ids": _tensor_values(node.candidate_ids),
                "prior_logp": _tensor_values(node.prior_logp),
                "cluster_of": _tensor_values(node.cluster_of),
                "cluster_prior_logp": _tensor_values(node.cluster_prior_logp),
                "node_seed": int(node.node_seed),
                "n": _tensor_values(node.n),
                "mean": _tensor_values(node.mean),
                "m2": _tensor_values(node.m2),
                "active": _tensor_values(node.active),
                "cluster_visits": _tensor_values(node.cluster_visits),
                "qmc_draws": int(node.qmc_draws),
                "prune_events": int(node.prune_events),
            }
        )
    return result


def _tree_value_digest(policy: BenchmarkPolicy) -> str:
    """Digest learned/search state while excluding instrumentation-only counts."""
    counters = asdict(policy.counters)
    counters.pop("evaluation_only_calls", None)
    payload = {
        "nodes": _node_value_payload(policy),
        "counters": counters,
        "first_success_verifier_request": policy.first_success_verifier_request,
        "blocked_verifier_calls": policy.blocked_verifier_calls,
        "root_coverage_cluster_counts": dict(
            sorted(policy.root_coverage_cluster_counts.items())
        ),
        "root_action_selection_counts": dict(
            sorted(policy.root_action_selection_counts.items())
        ),
    }
    return _sha256_json(payload)


def _uniform_stream_payload(policy: BenchmarkPolicy) -> list[dict[str, Any]]:
    """Serialize stream positions/states without serializing the selected mask."""
    result: list[dict[str, Any]] = []
    for state_key, node in sorted(policy.nodes.items()):
        engine = getattr(node.qmc_engine, "engine", None)
        if not isinstance(engine, CoordinateMuxEngine):
            continue
        sobol_num_generated = getattr(engine.sobol_engine, "num_generated", None)
        result.append(
            {
                "state": list(state_key),
                "node_seed": int(node.node_seed),
                "dimension": int(engine.dimension),
                "points_drawn": int(engine.points_drawn),
                "sobol_num_generated": (
                    None if sobol_num_generated is None else int(sobol_num_generated)
                ),
                "iid_generator_state_sha256": _generator_digest(
                    engine.iid_engine.generator
                ),
                "selected_sobol_scalar_values": int(
                    engine.selected_sobol_scalar_values
                ),
                "selected_iid_scalar_values": int(engine.selected_iid_scalar_values),
                "source_plan_points": dict(sorted(engine.source_plan_points.items())),
            }
        )
    return result


def _uniform_stream_digest(policy: BenchmarkPolicy) -> str:
    return _sha256_json(_uniform_stream_payload(policy))


def _behavior_state_digest(policy: BenchmarkPolicy) -> str:
    """Digest behaviorally relevant state, including current stream selection."""
    active_sources = policy.active_uniform_sources
    return _sha256_json(
        {
            "tree_value_digest": _tree_value_digest(policy),
            "uniform_stream_digest": _uniform_stream_digest(policy),
            "active_uniform_sources": (
                None if active_sources is None else active_sources.as_dict()
            ),
        }
    )


def _telemetry_census(policy: BenchmarkPolicy, task: RoleLockTask) -> dict[str, Any]:
    depth = task.depth
    vocab_size = len(RoleLockTokenizer.pieces)
    nodes_by_depth = [0] * depth
    on_nodes_by_depth = [0] * depth
    off_nodes_by_depth = [0] * depth
    visits_by_depth = [0] * depth
    on_visits_by_depth = [0] * depth
    off_visits_by_depth = [0] * depth
    oracle_node_visits = [0] * depth
    oracle_action_visits = [0] * depth
    oracle_action_counts: list[dict[str, int]] = [{} for _ in range(depth)]
    token_counts = [0] * vocab_size
    immediate_repeats = 0
    adjacent_probe_repeats = 0
    token_reselections = 0
    probe_reselections = 0

    for state_key, node in policy.nodes.items():
        generated = state_key[len(task.root) :]
        state_depth = len(generated)
        if not 0 <= state_depth < depth:
            raise AssertionError("expanded state lies outside Role-Lock depth")
        on_oracle = generated == task.target[:state_depth]
        node_visits = node.total_visits
        nodes_by_depth[state_depth] += 1
        visits_by_depth[state_depth] += node_visits
        if on_oracle:
            on_nodes_by_depth[state_depth] += 1
            on_visits_by_depth[state_depth] += node_visits
            oracle_node_visits[state_depth] = node_visits
        else:
            off_nodes_by_depth[state_depth] += 1
            off_visits_by_depth[state_depth] += node_visits

        for index, action_id_value in enumerate(node.candidate_ids.tolist()):
            action_id = int(action_id_value)
            count = int(node.n[index].item())
            if not 0 <= action_id < vocab_size:
                raise AssertionError("candidate token lies outside toy vocabulary")
            token_counts[action_id] += count
            if action_id in generated:
                token_reselections += count
                if action_id == 2:
                    probe_reselections += count
            if generated and action_id == int(generated[-1]):
                immediate_repeats += count
                if action_id == 2:
                    adjacent_probe_repeats += count
            if on_oracle:
                oracle_action_counts[state_depth][str(action_id)] = count

        if on_oracle:
            oracle = task.oracle_action(state_key)
            if oracle is None:
                raise AssertionError("nonterminal oracle state lacks oracle action")
            matches = torch.where(node.candidate_ids == int(oracle))[0]
            if len(matches) != 1:
                raise AssertionError("oracle action is not unique in candidates")
            oracle_action_visits[state_depth] = int(node.n[int(matches[0])].item())

    diagnostics = _search_diagnostics(
        policy,
        task,
        include_temporal_source_details=True,
    )
    nonroot_visits = sum(visits_by_depth[1:])
    nonroot_oracle_visits = sum(on_visits_by_depth[1:])
    correct_stage_counts = oracle_action_counts[depth - 1]
    return {
        "nodes_by_depth": nodes_by_depth,
        "on_oracle_prefix_nodes_by_depth": on_nodes_by_depth,
        "off_oracle_prefix_nodes_by_depth": off_nodes_by_depth,
        "visits_by_depth": visits_by_depth,
        "on_oracle_prefix_visits_by_depth": on_visits_by_depth,
        "off_oracle_prefix_visits_by_depth": off_visits_by_depth,
        "oracle_node_visits_by_stage": oracle_node_visits,
        "oracle_action_visits_by_stage": oracle_action_visits,
        "oracle_node_action_counts_by_stage": oracle_action_counts,
        "nonroot_visits": nonroot_visits,
        "nonroot_oracle_prefix_visits": nonroot_oracle_visits,
        "token_selection_counts": token_counts,
        "probe_selection_count": token_counts[2],
        "token_reselection_edge_count": token_reselections,
        "probe_reselection_edge_count": probe_reselections,
        "immediate_repeat_edge_count": immediate_repeats,
        "adjacent_probe_repeat_edge_count": adjacent_probe_repeats,
        "correct_stage_total_visits": oracle_node_visits[depth - 1],
        "correct_stage_eos_trials": int(correct_stage_counts.get("1", 0)),
        "correct_stage_probe_trials": int(correct_stage_counts.get("2", 0)),
        "correct_stage_derive_trials": int(correct_stage_counts.get("3", 0)),
        "uniform_source_usage": diagnostics.get("uniform_source_usage", {}),
        "root_candidate_ids": (
            []
            if policy.nodes.get(task.root) is None
            else [
                int(value) for value in policy.nodes[task.root].candidate_ids.tolist()
            ]
        ),
        "root_action_selection_counts": diagnostics.get(
            "root_action_selection_counts", []
        ),
        "root_coverage_cluster_counts": diagnostics.get(
            "root_coverage_cluster_counts", []
        ),
        "oracle_active_path_expanded": diagnostics["oracle_active_path_expanded"],
    }


def _checkpoint_snapshot(
    policy: BenchmarkPolicy,
    task: RoleLockTask,
    checkpoint: int,
) -> dict[str, Any]:
    behavior_before = _behavior_state_digest(policy)
    readout = policy.best_continuation(task.root, max_new_tokens=task.depth)
    prefix_length = _correct_prefix_length(readout, task.target)
    census = _telemetry_census(policy, task)
    behavior_after = _behavior_state_digest(policy)
    if behavior_after != behavior_before:
        raise AssertionError("passive checkpoint telemetry changed search behavior")
    snapshot = {
        "completed_verifier_requests": int(checkpoint),
        "usage": asdict(policy.counters),
        "readout_token_ids": readout,
        "readout_success": task.is_success(readout),
        "readout_correct_prefix_length": prefix_length,
        "best_observed_success": policy.counters.best_observed_return > 0.0,
        "census": census,
        "tree_value_digest": _tree_value_digest(policy),
        "uniform_stream_digest": _uniform_stream_digest(policy),
        "behavior_state_digest": behavior_after,
        "collector_behavior_digest_before": behavior_before,
        "collector_behavior_digest_after": behavior_after,
        "collector_behavior_unchanged": True,
    }
    snapshot["checkpoint_payload_digest"] = _sha256_json(snapshot)
    return snapshot


def _first_success_snapshot(
    policy: BenchmarkPolicy,
    task: RoleLockTask,
) -> dict[str, Any]:
    behavior_before = _behavior_state_digest(policy)
    census = _telemetry_census(policy, task)
    behavior_after = _behavior_state_digest(policy)
    if behavior_after != behavior_before:
        raise AssertionError("first-hit telemetry changed search behavior")
    snapshot = {
        "completed_verifier_requests": policy.first_success_verifier_request,
        "edge_selections": int(policy.counters.edge_selections),
        "logical_lm_node_evals": int(policy.counters.logical_lm_node_evals),
        "nonroot_visits": int(census["nonroot_visits"]),
        "nonroot_oracle_prefix_visits": int(census["nonroot_oracle_prefix_visits"]),
        "correct_stage_total_visits": int(census["correct_stage_total_visits"]),
        "correct_stage_eos_trials": int(census["correct_stage_eos_trials"]),
        "tree_value_digest": _tree_value_digest(policy),
        "collector_behavior_digest_before": behavior_before,
        "collector_behavior_digest_after": behavior_after,
        "collector_behavior_unchanged": True,
    }
    snapshot["first_success_payload_digest"] = _sha256_json(snapshot)
    return snapshot


def _phase_metrics(
    checkpoint_rows: dict[int, dict[str, Any]],
    *,
    switch_request: int,
    verifier_cap: int,
) -> dict[str, Any]:
    early = checkpoint_rows[switch_request]["census"]
    final = checkpoint_rows[verifier_cap]["census"]
    late_nonroot = int(final["nonroot_visits"]) - int(early["nonroot_visits"])
    late_on = int(final["nonroot_oracle_prefix_visits"]) - int(
        early["nonroot_oracle_prefix_visits"]
    )
    late_eos = int(final["correct_stage_eos_trials"]) - int(
        early["correct_stage_eos_trials"]
    )
    late_edges = sum(final["visits_by_depth"]) - sum(early["visits_by_depth"])
    late_probe = int(final["probe_selection_count"]) - int(
        early["probe_selection_count"]
    )
    late_repeats = int(final["immediate_repeat_edge_count"]) - int(
        early["immediate_repeat_edge_count"]
    )
    late_probe_reselections = int(final["probe_reselection_edge_count"]) - int(
        early["probe_reselection_edge_count"]
    )
    late_nodes_by_depth = [
        int(final["nodes_by_depth"][index]) - int(early["nodes_by_depth"][index])
        for index in range(4)
    ]
    late_oracle_actions_by_stage = [
        int(final["oracle_action_visits_by_stage"][index])
        - int(early["oracle_action_visits_by_stage"][index])
        for index in range(4)
    ]
    late_verifier_requests = verifier_cap - switch_request
    return {
        "late_phase_completed_verifier_requests": late_verifier_requests,
        "late_nonroot_visits": late_nonroot,
        "late_nonroot_oracle_prefix_visits": late_on,
        "late_nonroot_oracle_prefix_visit_share": (
            late_on / late_nonroot if late_nonroot else None
        ),
        "late_correct_stage_eos_trials": late_eos,
        "late_correct_stage_eos_trials_per_verifier_request": (
            late_eos / late_verifier_requests
        ),
        "late_nodes_created_by_depth": late_nodes_by_depth,
        "late_oracle_action_visits_by_stage": late_oracle_actions_by_stage,
        "late_probe_selection_count": late_probe,
        "late_probe_selection_share": late_probe / late_edges if late_edges else None,
        "late_immediate_repeat_edge_count": late_repeats,
        "late_immediate_repeat_edge_share": (
            late_repeats / late_edges if late_edges else None
        ),
        "late_probe_reselection_edge_count": late_probe_reselections,
        "late_probe_reselection_edge_share": (
            late_probe_reselections / late_edges if late_edges else None
        ),
    }


def _run_variant(
    *,
    task: RoleLockTask,
    variant: VariantSpec,
    seeds: SeedPlan,
    registry: CandidateRegistry,
    verifier_cap: int,
    lm_node_ceiling: int,
    edge_ceiling: int,
    checkpoints: Sequence[int],
    switch_request: int,
    telemetry_enabled: bool = True,
) -> dict[str, Any]:
    if min(verifier_cap, lm_node_ceiling, edge_ceiling) < 1:
        raise ValueError("all budget limits must be positive")
    if not 0 < switch_request < verifier_cap:
        raise ValueError("switch_request must lie inside the verifier budget")
    checkpoint_values = tuple(int(value) for value in checkpoints)
    if telemetry_enabled and (
        not checkpoint_values
        or checkpoint_values != tuple(sorted(set(checkpoint_values)))
        or switch_request not in checkpoint_values
        or verifier_cap not in checkpoint_values
    ):
        raise ValueError("telemetry checkpoints must be ordered and include switch/cap")

    tokenizer = RoleLockTokenizer()
    model = RoleLockLM(task, seeds.model_seed)
    config = benchmark_config(task, variant, seeds.exploration_seed)
    policy = BenchmarkPolicy(
        model,
        tokenizer,
        config,
        variant=variant,
        task=task,
        seeds=seeds,
        registry=registry,
        posterior_sd_scale=POSTERIOR_SD_SCALE,
    )
    policy.verifier_budget = int(verifier_cap)
    policy.lm_node_budget = int(lm_node_ceiling)
    policy.edge_budget = int(edge_ceiling)
    policy.stop_reason = "running"

    snapshots: list[dict[str, Any]] = []
    snapshot_by_request: dict[int, dict[str, Any]] = {}
    first_success: dict[str, Any] | None = None
    switch_audit: list[dict[str, Any]] = []
    started = time.perf_counter()

    while True:
        if policy.counters.verifier_requests >= verifier_cap:
            policy.stop_reason = "verifier_budget"
            break
        if policy.counters.logical_lm_node_evals >= lm_node_ceiling:
            policy.stop_reason = "lm_integrity_ceiling"
            break
        if policy.counters.edge_selections >= edge_ceiling:
            policy.stop_reason = "edge_integrity_ceiling"
            break

        previous_first = policy.first_success_verifier_request
        previous_verifier = policy.counters.verifier_requests
        _, reason = policy.search_step_budgeted(task.root)
        if reason == "lm_budget_frontier":
            policy.stop_reason = "lm_integrity_ceiling_frontier"
            break
        if reason == "edge_budget":
            policy.stop_reason = "edge_integrity_ceiling"
            break
        if policy.counters.verifier_requests != previous_verifier + 1:
            raise AssertionError(
                "each Role-Lock simulation must consume one verifier call"
            )

        completed = int(policy.counters.verifier_requests)
        if (
            telemetry_enabled
            and previous_first is None
            and policy.first_success_verifier_request is not None
        ):
            first_success = _first_success_snapshot(policy, task)

        if telemetry_enabled and completed in checkpoint_values:
            snapshot = _checkpoint_snapshot(policy, task, completed)
            snapshots.append(snapshot)
            snapshot_by_request[completed] = snapshot

        if variant.name == "two_phase_action_256" and completed == switch_request:
            tree_before = _tree_value_digest(policy)
            stream_before = _uniform_stream_digest(policy)
            counters_before = asdict(policy.counters)
            policy.set_uniform_sources(
                ROUTING_ONLY_PLAN,
                verifier_request=switch_request,
                reason="predeclared_late_iid_action_phase",
            )
            tree_after = _tree_value_digest(policy)
            stream_after = _uniform_stream_digest(policy)
            counters_after = asdict(policy.counters)
            event = dict(policy.uniform_source_switch_log[-1])
            event.update(
                {
                    "tree_value_digest_before": tree_before,
                    "tree_value_digest_after": tree_after,
                    "tree_value_unchanged": tree_before == tree_after,
                    "uniform_stream_digest_before": stream_before,
                    "uniform_stream_digest_after": stream_after,
                    "uniform_stream_state_unchanged": stream_before == stream_after,
                    "run_counters_unchanged": counters_before == counters_after,
                    "next_simulation_request_number": switch_request + 1,
                }
            )
            switch_audit.append(event)

    wall_time = time.perf_counter() - started
    if telemetry_enabled:
        final_snapshot = snapshot_by_request.get(verifier_cap)
        if final_snapshot is None:
            readout: list[int] = []
        else:
            readout = [int(value) for value in final_snapshot["readout_token_ids"]]
        # The checkpoint collector is passive.  Count the reused cap readout
        # exactly once as the deterministic, outside-budget final evaluation.
        policy.counters.evaluation_only_calls += 1
    else:
        readout = policy.best_continuation(task.root, max_new_tokens=task.depth)
        policy.counters.evaluation_only_calls += 1

    readout_success = task.is_success(readout)
    prefix_length = _correct_prefix_length(readout, task.target)
    counters = asdict(policy.counters)
    lm_used = int(policy.counters.logical_lm_node_evals)
    verifier_used = int(policy.counters.verifier_requests)
    edges_used = int(policy.counters.edge_selections)
    search = _search_diagnostics(
        policy,
        task,
        include_temporal_source_details=True,
    )
    final_behavior_digest = _behavior_state_digest(policy)

    if telemetry_enabled and verifier_cap in snapshot_by_request:
        phase_metrics = _phase_metrics(
            snapshot_by_request,
            switch_request=switch_request,
            verifier_cap=verifier_cap,
        )
    else:
        phase_metrics = None

    initial_plan = (
        SOBOL_ALL_PLAN if variant.name != "sobol_routing_only" else ROUTING_ONLY_PLAN
    )
    final_plan = ROUTING_ONLY_PLAN if variant.name != "sobol_all" else SOBOL_ALL_PLAN
    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "record_type": "two_phase_sampler_run",
        "paired_group_id": (
            f"{task.task_id}:sd{POSTERIOR_SD_SCALE:g}:"
            f"seed{seeds.exploration_seed}:v{verifier_cap}"
        ),
        "experiment": {
            "name": "role_lock_d4_two_phase_action_source",
            "question": (
                "does early Sobol action coverage followed by late IID action "
                "reconcentration improve success and oracle-path behavior"
            ),
            "exploratory_posthoc_threshold": True,
            "threshold_sweep": False,
            "fixed_task": "role_lock_d4",
            "fixed_strata": "aligned_static_token_embedding",
            "fixed_pruning": False,
            "fixed_posterior_sd_scale": POSTERIOR_SD_SCALE,
        },
        "method": {
            "name": variant.name,
            "sampler": (
                "temporal_hybrid"
                if variant.name == "two_phase_action_256"
                else variant.sampler
            ),
            "strata": variant.strata,
            "pruning": variant.pruning,
            "posterior_sd_scale": POSTERIOR_SD_SCALE,
            "sampler_layout": "matched_full_dimension_column_mux/v2_dynamic",
            "initial_uniform_sources": initial_plan.as_dict(),
            "final_uniform_sources": final_plan.as_dict(),
            "phase_schedule": [
                {
                    "request_numbers_inclusive": [1, switch_request],
                    "completed_request_counter_before_phase": 0,
                    "uniform_sources": initial_plan.as_dict(),
                },
                {
                    "request_numbers_inclusive": [switch_request + 1, verifier_cap],
                    "completed_request_counter_before_phase": switch_request,
                    "uniform_sources": final_plan.as_dict(),
                },
            ],
            "readout": "return_mean_then_visits_then_prior",
            "lm_prior_role": "behavior_only",
        },
        "search_config": asdict(config),
        "task": {
            "id": task.task_id,
            "depth": task.depth,
            "target": list(task.target),
            "reward": task.reward,
            "terminal_only": True,
        },
        "seeds": asdict(seeds),
        "budget": {
            "primary": "verifier_requests",
            "limit": verifier_cap,
            "verifier_limit": verifier_cap,
            "lm_node_ceiling": lm_node_ceiling,
            "lm_node_ceiling_kind": "conservative_integrity_guard_not_reachable_saturation",
            "reachable_nonterminal_prefix_bound": REACHABLE_PREFIX_BOUND,
            "edge_ceiling": edge_ceiling,
            "normal_edge_bound": task.depth * verifier_cap,
            "regime": "verifier_primary_with_lm_and_edge_guards",
            "stop_reason": policy.stop_reason,
            "exact_primary_cap_reached": verifier_used == verifier_cap,
            "verifier_overshoot": max(0, verifier_used - verifier_cap),
            "lm_node_overshoot": max(0, lm_used - lm_node_ceiling),
            "edge_overshoot": max(0, edges_used - edge_ceiling),
            "guard_headroom": {
                "lm_nodes": lm_node_ceiling - lm_used,
                "edges": edge_ceiling - edges_used,
            },
        },
        "usage": {
            **counters,
            "first_success_verifier_request": policy.first_success_verifier_request,
            "blocked_verifier_calls": policy.blocked_verifier_calls,
            "wall_time_s": wall_time,
        },
        "outcome": {
            "readout_token_ids": readout,
            "readout_text": tokenizer.decode(readout),
            "readout_success": readout_success,
            "readout_return": task.reward if readout_success else 0.0,
            "readout_correct_prefix_length": prefix_length,
            "readout_failure_stage": None if readout_success else prefix_length,
            "best_observed_success": policy.counters.best_observed_return > 0.0,
            "best_observed_return": policy.counters.best_observed_return,
        },
        "telemetry": {
            "enabled": telemetry_enabled,
            "contract": "passive_checkpoint_census/v1",
            "checkpoint_requests": list(checkpoint_values) if telemetry_enabled else [],
            "checkpoint_readouts_are_search_feedback": False,
            "consumes_rng_draws": False,
            "consumes_model_calls": False,
            "consumes_verifier_calls": False,
            "final_readout_reuses_cap_checkpoint": telemetry_enabled,
            "checkpoints": snapshots,
            "passive_checkpoint_collector_calls": len(snapshots),
            "phase_metrics": phase_metrics,
            "first_success_after_backup_snapshot": first_success,
        },
        "switch_audit": switch_audit,
        "search": {
            **search,
            "prune_log": policy.prune_log,
            "final_tree_value_digest": _tree_value_digest(policy),
            "final_uniform_stream_digest": _uniform_stream_digest(policy),
            "final_behavior_state_digest": final_behavior_digest,
        },
        "randomization": {
            "independent_unit": "exploration_seed",
            "node_stream_seeded_from": "exploration_seed_and_exact_prefix",
            "source_architecture": "matched_full_dimension_column_mux",
            "sobol_scramble": True,
            "iid_seed_transform": "node_seed XOR 0x1D1D1D",
            "both_sources_advanced_every_draw": True,
            "switch_resets_streams": False,
            "common_random_numbers": {
                "across_profiles_for_unchanged_coordinates": True,
                "scope": "same exact prefix, exploration seed, and node draw index",
            },
        },
        "evaluation_scope": {
            "search_verifier_feedback_calls": verifier_used,
            "passive_checkpoint_readouts": int(len(snapshots)),
            "final_outside_budget_readout_evaluations": int(
                policy.counters.evaluation_only_calls
            ),
            "checkpoint_readouts_outside_verifier_budget": True,
            "final_readout_reused_from_checkpoint_700": telemetry_enabled,
            "wall_time_scope": "search_plus_passive_telemetry_instrumentation",
            "wall_time_is_performance_endpoint": False,
        },
    }
    record["deterministic_digest"] = canonical_record_digest(record)
    json.dumps(record, allow_nan=False)
    return record


def run_experiment(
    *,
    seed_ids: Sequence[int],
    verifier_cap: int = VERIFIER_CAP,
    lm_node_ceiling: int = LM_NODE_CEILING,
    edge_ceiling: int = EDGE_CEILING,
    checkpoints: Sequence[int] = CHECKPOINTS,
    switch_request: int = SWITCH_REQUEST,
    progress_every: int = 0,
    skip_keys: set[tuple[str, int]] | None = None,
) -> list[dict[str, Any]]:
    if not seed_ids or any(int(seed) < 0 for seed in seed_ids):
        raise ValueError("seed_ids must contain nonnegative integers")
    if len({int(seed) for seed in seed_ids}) != len(seed_ids):
        raise ValueError("seed_ids must be unique")
    variants = _variant_map()
    task = RoleLockTask(4)
    registry = CandidateRegistry()
    records: list[dict[str, Any]] = []
    skip = skip_keys or set()
    total = len(seed_ids) * len(METHODS) - len(skip)
    for seed in seed_ids:
        for method in METHODS:
            key = (method, int(seed))
            if key in skip:
                continue
            seeds = SeedPlan(
                task_seed=task.depth,
                exploration_seed=int(seed),
                partition_seed=10_000,
            )
            records.append(
                _run_variant(
                    task=task,
                    variant=variants[method],
                    seeds=seeds,
                    registry=registry,
                    verifier_cap=verifier_cap,
                    lm_node_ceiling=lm_node_ceiling,
                    edge_ceiling=edge_ceiling,
                    checkpoints=checkpoints,
                    switch_request=switch_request,
                )
            )
            if progress_every and len(records) % progress_every == 0:
                print(f"completed {len(records)}/{total}", flush=True)
    return records


def _record_key(record: dict[str, Any]) -> tuple[str, int]:
    method = record["method"]["name"]
    seed = record["seeds"]["exploration_seed"]
    if type(method) is not str or type(seed) is not int:
        raise TypeError("record keys require an exact string method and integer seed")
    return method, seed


def _checkpoint_map(record: dict[str, Any]) -> dict[int, dict[str, Any]]:
    rows = record["telemetry"]["checkpoints"]
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise TypeError("checkpoint rows must be objects")
    if any(type(row.get("completed_verifier_requests")) is not int for row in rows):
        raise TypeError("checkpoint request counters must be exact integers")
    return {row["completed_verifier_requests"]: row for row in rows}


def _validate_census(
    census: dict[str, Any],
    *,
    nodes_created: int,
    edges: int,
) -> bool:
    def exact_int_list(value: Any) -> list[int]:
        if not isinstance(value, list) or any(type(item) is not int for item in value):
            raise TypeError("expected a JSON integer list")
        return value

    scalar_fields = (
        "nonroot_visits",
        "nonroot_oracle_prefix_visits",
        "probe_selection_count",
        "token_reselection_edge_count",
        "probe_reselection_edge_count",
        "immediate_repeat_edge_count",
        "adjacent_probe_repeat_edge_count",
        "correct_stage_total_visits",
        "correct_stage_eos_trials",
        "correct_stage_probe_trials",
        "correct_stage_derive_trials",
    )
    if not _has_exact_integer_fields(census, scalar_fields):
        return False
    try:
        nodes = exact_int_list(census["nodes_by_depth"])
        on_nodes = exact_int_list(census["on_oracle_prefix_nodes_by_depth"])
        off_nodes = exact_int_list(census["off_oracle_prefix_nodes_by_depth"])
        visits = exact_int_list(census["visits_by_depth"])
        on_visits = exact_int_list(census["on_oracle_prefix_visits_by_depth"])
        off_visits = exact_int_list(census["off_oracle_prefix_visits_by_depth"])
        oracle_node = exact_int_list(census["oracle_node_visits_by_stage"])
        oracle_action = exact_int_list(census["oracle_action_visits_by_stage"])
        action_counts = census["oracle_node_action_counts_by_stage"]
        token_counts = exact_int_list(census["token_selection_counts"])
        root_candidate_ids = exact_int_list(census["root_candidate_ids"])
        root_action_counts = exact_int_list(census["root_action_selection_counts"])
        root_coverage_counts = exact_int_list(census["root_coverage_cluster_counts"])
    except (KeyError, TypeError, ValueError):
        return False
    if not all(
        len(values) == 4
        for values in (
            nodes,
            on_nodes,
            off_nodes,
            visits,
            on_visits,
            off_visits,
            oracle_node,
            oracle_action,
        )
    ):
        return False
    if len(action_counts) != 4 or len(token_counts) != len(RoleLockTokenizer.pieces):
        return False
    if any(
        value < 0
        for values in (
            nodes,
            on_nodes,
            off_nodes,
            visits,
            on_visits,
            off_visits,
            oracle_node,
            oracle_action,
            token_counts,
        )
        for value in values
    ):
        return False
    if (
        sum(nodes) != nodes_created
        or sum(visits) != edges
        or sum(token_counts) != edges
    ):
        return False
    if any(nodes[index] != on_nodes[index] + off_nodes[index] for index in range(4)):
        return False
    if any(visits[index] != on_visits[index] + off_visits[index] for index in range(4)):
        return False
    if any(on_nodes[index] not in (0, 1) for index in range(4)):
        return False
    if any(oracle_node[index] != on_visits[index] for index in range(4)):
        return False
    if any(oracle_action[index] > oracle_node[index] for index in range(4)):
        return False
    if any(
        not isinstance(stage, dict)
        or any(
            type(key) is not str or type(value) is not int
            for key, value in stage.items()
        )
        for stage in action_counts
    ):
        return False
    normalized_counts = [dict(stage) for stage in action_counts]
    if any(
        sum(stage.values()) != oracle_node[index]
        for index, stage in enumerate(normalized_counts)
    ):
        return False
    expected_oracle = (2, 3, 4, 1)
    if any(
        oracle_action[index]
        != normalized_counts[index].get(str(expected_oracle[index]), 0)
        for index in range(4)
    ):
        return False
    if census["nonroot_visits"] != sum(visits[1:]):
        return False
    if census["nonroot_oracle_prefix_visits"] != sum(on_visits[1:]):
        return False
    if census["probe_selection_count"] != token_counts[2]:
        return False
    if census["correct_stage_total_visits"] != oracle_node[3]:
        return False
    if census["correct_stage_eos_trials"] != normalized_counts[3].get("1", 0):
        return False
    if census["correct_stage_probe_trials"] != normalized_counts[3].get("2", 0):
        return False
    if census["correct_stage_derive_trials"] != normalized_counts[3].get("3", 0):
        return False
    reselections = census["token_reselection_edge_count"]
    probe_reselections = census["probe_reselection_edge_count"]
    immediate = census["immediate_repeat_edge_count"]
    adjacent_probe = census["adjacent_probe_repeat_edge_count"]
    if not (
        0 <= adjacent_probe <= probe_reselections <= reselections <= edges
        and adjacent_probe <= immediate <= reselections
        and probe_reselections <= token_counts[2]
    ):
        return False
    if (
        sorted(root_candidate_ids) != list(range(1, 11))
        or len(root_action_counts) != len(root_candidate_ids)
        or any(value < 0 for value in root_action_counts)
        or sum(root_action_counts) != visits[0]
        or len(root_coverage_counts) != 4
        or any(value < 0 for value in root_coverage_counts)
        or sum(root_coverage_counts) > visits[0]
        or not isinstance(census.get("oracle_active_path_expanded"), bool)
    ):
        return False
    return True


def _expected_source_accounting(
    method: str,
    *,
    edges: int,
    switch_edges: int,
) -> tuple[int, int, dict[str, int]]:
    if method == "sobol_all":
        return 12 * edges, 0, {SOBOL_PLAN_KEY: edges}
    if method == "sobol_routing_only":
        return 2 * edges, 10 * edges, {ROUTING_PLAN_KEY: edges}
    late_edges = edges - switch_edges
    plans = {SOBOL_PLAN_KEY: switch_edges, ROUTING_PLAN_KEY: late_edges}
    return (
        12 * switch_edges + 2 * late_edges,
        10 * late_edges,
        {key: value for key, value in plans.items() if value != 0},
    )


def _source_usage_valid(
    usage: Any,
    *,
    method: str,
    edges: int,
    nodes: int,
    switch_edges: int,
    expected_reconfigurations: int,
) -> bool:
    integer_fields = (
        "mux_nodes_created",
        "selection_points",
        "sobol_full_points_generated",
        "iid_full_points_generated",
        "selected_sobol_scalar_values",
        "selected_iid_scalar_values",
        "total_selected_scalar_values",
        "mux_reconfigurations",
    )
    if not _has_exact_integer_fields(usage, integer_fields):
        return False
    raw_plans = usage.get("selection_points_by_source_plan")
    if not isinstance(raw_plans, dict) or any(
        type(key) is not str or type(value) is not int
        for key, value in raw_plans.items()
    ):
        return False
    expected_sobol, expected_iid, expected_plans = _expected_source_accounting(
        method,
        edges=edges,
        switch_edges=switch_edges,
    )
    observed_plans = {key: value for key, value in raw_plans.items() if value != 0}
    return (
        usage["mux_nodes_created"] == nodes
        and usage["selection_points"] == edges
        and usage["sobol_full_points_generated"] == edges
        and usage["iid_full_points_generated"] == edges
        and usage["selected_sobol_scalar_values"] == expected_sobol
        and usage["selected_iid_scalar_values"] == expected_iid
        and usage["total_selected_scalar_values"] == 12 * edges
        and observed_plans == expected_plans
        and usage["mux_reconfigurations"] == expected_reconfigurations
        and usage.get("both_sources_advanced_every_draw") is True
    )


def _validate_records_impl(
    records: Sequence[dict[str, Any]],
    *,
    seed_ids: Sequence[int],
    verifier_cap: int,
    lm_node_ceiling: int,
    edge_ceiling: int,
    checkpoints: Sequence[int],
    switch_request: int,
) -> dict[str, Any]:
    variants = _variant_map()
    checkpoint_values = tuple(int(value) for value in checkpoints)
    expected = set(itertools.product(METHODS, [int(seed) for seed in seed_ids]))
    keys = [_record_key(record) for record in records]
    actual = set(keys)
    duplicate_count = len(keys) - len(actual)
    errors: dict[str, int] = defaultdict(int)
    groups: dict[str, list[tuple[str, int]]] = defaultdict(list)
    fingerprints: dict[int, set[str]] = defaultdict(set)
    all_fingerprints: set[str] = set()
    records_by_seed: dict[int, dict[str, dict[str, Any]]] = defaultdict(dict)
    target = [2, 3, 4, 1]

    for record in records:
        try:
            method, seed = _record_key(record)
        except (KeyError, TypeError, ValueError):
            errors["schema"] += 1
            continue
        records_by_seed[seed][method] = record
        variant = variants.get(method)
        if variant is None or variant.uniform_sources is None:
            errors["source_contract"] += 1
            continue
        if record.get("schema_version") != SCHEMA_VERSION:
            errors["schema"] += 1
        if record.get("deterministic_digest") != canonical_record_digest(record):
            errors["digest"] += 1
        try:
            json.dumps(record, allow_nan=False)
        except (TypeError, ValueError):
            errors["strict_json"] += 1

        method_record = record["method"]
        initial = (
            SOBOL_ALL_PLAN if method != "sobol_routing_only" else ROUTING_ONLY_PLAN
        )
        final = SOBOL_ALL_PLAN if method == "sobol_all" else ROUTING_ONLY_PLAN
        expected_sampler = (
            "temporal_hybrid" if method == "two_phase_action_256" else variant.sampler
        )
        schedule = method_record.get("phase_schedule", [])
        expected_schedule = [
            {
                "request_numbers_inclusive": [1, switch_request],
                "completed_request_counter_before_phase": 0,
                "uniform_sources": initial.as_dict(),
            },
            {
                "request_numbers_inclusive": [switch_request + 1, verifier_cap],
                "completed_request_counter_before_phase": switch_request,
                "uniform_sources": final.as_dict(),
            },
        ]
        if (
            method_record.get("name") != method
            or method_record.get("sampler") != expected_sampler
            or method_record.get("strata") != "embedding"
            or method_record.get("pruning") is not False
            or not _json_exact_equal(
                method_record.get("posterior_sd_scale"), POSTERIOR_SD_SCALE
            )
            or method_record.get("sampler_layout")
            != "matched_full_dimension_column_mux/v2_dynamic"
            or not _json_exact_equal(
                method_record.get("initial_uniform_sources"), initial.as_dict()
            )
            or not _json_exact_equal(
                method_record.get("final_uniform_sources"), final.as_dict()
            )
            or not _json_exact_equal(schedule, expected_schedule)
        ):
            errors["source_contract"] += 1

        task_record = record["task"]
        outcome = record["outcome"]
        raw_readout = outcome["readout_token_ids"]
        readout_valid = _is_exact_integer_list(raw_readout) and len(raw_readout) <= 4
        readout = raw_readout if readout_valid else []
        exact_success = readout == target
        correct_prefix = _correct_prefix_length(readout, target)
        if (
            task_record.get("id") != "role_lock_d4"
            or type(task_record.get("depth")) is not int
            or task_record.get("depth") != 4
            or not _json_exact_equal(task_record.get("target"), target)
            or not _json_exact_equal(task_record.get("reward"), 5.0)
            or task_record.get("terminal_only") is not True
            or not readout_valid
            or outcome.get("readout_success") is not exact_success
            or not _json_exact_equal(
                outcome.get("readout_return"), 5.0 if exact_success else 0.0
            )
            or type(outcome.get("readout_correct_prefix_length")) is not int
            or outcome.get("readout_correct_prefix_length") != correct_prefix
            or (
                outcome.get("readout_failure_stage") is not None
                and type(outcome.get("readout_failure_stage")) is not int
            )
            or outcome.get("readout_failure_stage")
            != (None if exact_success else correct_prefix)
            or type(outcome.get("best_observed_success")) is not bool
        ):
            errors["task_and_success_encoding"] += 1

        budget = record["budget"]
        usage = record["usage"]
        required_usage_integers = COUNTER_INTEGER_FIELDS + ("blocked_verifier_calls",)
        if not _has_exact_integer_fields(usage, required_usage_integers):
            errors["usage_accounting"] += 1
        budget_integer_fields = (
            "limit",
            "verifier_limit",
            "lm_node_ceiling",
            "reachable_nonterminal_prefix_bound",
            "edge_ceiling",
            "normal_edge_bound",
            "verifier_overshoot",
            "lm_node_overshoot",
            "edge_overshoot",
        )
        headroom = budget.get("guard_headroom")
        if not _has_exact_integer_fields(
            budget, budget_integer_fields
        ) or not _has_exact_integer_fields(headroom, ("lm_nodes", "edges")):
            errors["budget_contract"] += 1
        if type(record.get("search", {}).get("nodes_created")) is not int:
            errors["usage_accounting"] += 1
        verifier_used = int(usage["verifier_requests"])
        lm_used = int(usage["logical_lm_node_evals"])
        edges_used = int(usage["edge_selections"])
        if (
            budget.get("primary") != "verifier_requests"
            or int(budget.get("limit", -1)) != verifier_cap
            or int(budget.get("verifier_limit", -1)) != verifier_cap
            or int(budget.get("lm_node_ceiling", -1)) != lm_node_ceiling
            or int(budget.get("edge_ceiling", -1)) != edge_ceiling
            or int(budget.get("reachable_nonterminal_prefix_bound", -1))
            != REACHABLE_PREFIX_BOUND
            or int(budget.get("normal_edge_bound", -1)) != 4 * verifier_cap
            or budget.get("stop_reason") != "verifier_budget"
            or budget.get("exact_primary_cap_reached") is not True
            or verifier_used != verifier_cap
            or lm_used >= lm_node_ceiling
            or lm_used > REACHABLE_PREFIX_BOUND
            or edges_used >= edge_ceiling
            or edges_used > 4 * verifier_used
            or int(budget.get("verifier_overshoot", -1)) != 0
            or int(budget.get("lm_node_overshoot", -1)) != 0
            or int(budget.get("edge_overshoot", -1)) != 0
            or int(budget["guard_headroom"]["lm_nodes"]) != lm_node_ceiling - lm_used
            or int(budget["guard_headroom"]["edges"]) != edge_ceiling - edges_used
        ):
            errors["budget_contract"] += 1
        if (
            int(usage["verifier_evaluations"]) != verifier_used
            or int(usage["physical_lm_forwards"]) != lm_used
            or int(usage["evaluation_only_calls"]) != 1
            or int(usage["blocked_verifier_calls"]) != 0
            or int(usage["simulations_started"]) != verifier_used
            or int(usage["simulations_completed"]) != verifier_used
            or int(usage["budget_leaf_backups"]) != 0
            or int(record["search"]["nodes_created"]) != lm_used
            or int(usage["cache_hits"]) + lm_used != edges_used
            or not lm_used <= int(usage["full_prefix_tokens"]) <= 4 * lm_used
            or int(usage["coverage_route_selections"])
            + int(usage["global_route_selections"])
            != edges_used
        ):
            errors["usage_accounting"] += 1

        first_request = usage.get("first_success_verifier_request")
        first_lm = usage.get("first_success_lm_eval")
        best_success = outcome.get("best_observed_success") is True
        if (
            (first_request is not None and type(first_request) is not int)
            or (first_lm is not None and type(first_lm) is not int)
            or (first_request is not None and not 1 <= first_request <= verifier_cap)
            or (first_lm is not None and not 1 <= first_lm <= lm_used)
            or (first_request is None) == best_success
            or (first_lm is None) == best_success
        ):
            errors["first_success"] += 1

        if (
            int(usage["arms_pruned"]) != 0
            or int(usage["prune_checks"]) != 0
            or int(usage["prune_batches"]) != 0
            or record["search"].get("prune_log") != []
        ):
            errors["pruning"] += 1

        expected_config = asdict(benchmark_config(RoleLockTask(4), variant, seed))
        expected_seeds = asdict(
            SeedPlan(task_seed=4, exploration_seed=seed, partition_seed=10_000)
        )
        experiment = record.get("experiment", {})
        if (
            not _json_exact_equal(record.get("search_config"), expected_config)
            or not _json_exact_equal(record.get("seeds"), expected_seeds)
            or experiment.get("exploratory_posthoc_threshold") is not True
            or experiment.get("threshold_sweep") is not False
            or experiment.get("fixed_task") != "role_lock_d4"
            or experiment.get("fixed_strata") != "aligned_static_token_embedding"
            or experiment.get("fixed_pruning") is not False
            or not _json_exact_equal(
                experiment.get("fixed_posterior_sd_scale"), POSTERIOR_SD_SCALE
            )
        ):
            errors["config_propagation"] += 1

        fingerprint = record["search"].get("root_candidate_fingerprint")
        if (
            type(fingerprint) is not str
            or len(fingerprint) != 64
            or any(character not in "0123456789abcdef" for character in fingerprint)
            or int(usage["candidate_misses"]) != 0
            or record["search"].get("oracle_candidate_universe_guaranteed") is not True
        ):
            errors["candidate_contract"] += 1
        else:
            fingerprints[seed].add(str(fingerprint))
            all_fingerprints.add(str(fingerprint))

        telemetry = record["telemetry"]
        checkpoint_rows = telemetry.get("checkpoints", [])
        checkpoint_rows_valid = (
            isinstance(checkpoint_rows, list)
            and all(isinstance(row, dict) for row in checkpoint_rows)
            and all(
                type(row.get("completed_verifier_requests")) is int
                for row in checkpoint_rows
            )
        )
        observed_checkpoint_ids = (
            [row["completed_verifier_requests"] for row in checkpoint_rows]
            if checkpoint_rows_valid
            else []
        )
        if (
            telemetry.get("enabled") is not True
            or telemetry.get("contract") != "passive_checkpoint_census/v1"
            or not _json_exact_equal(
                telemetry.get("checkpoint_requests"), list(checkpoint_values)
            )
            or observed_checkpoint_ids != list(checkpoint_values)
            or telemetry.get("checkpoint_readouts_are_search_feedback") is not False
            or telemetry.get("consumes_rng_draws") is not False
            or telemetry.get("consumes_model_calls") is not False
            or telemetry.get("consumes_verifier_calls") is not False
            or telemetry.get("final_readout_reuses_cap_checkpoint") is not True
            or type(telemetry.get("passive_checkpoint_collector_calls")) is not int
            or telemetry.get("passive_checkpoint_collector_calls")
            != len(checkpoint_values)
            or not checkpoint_rows_valid
        ):
            errors["telemetry_contract"] += 1
            checkpoint_map: dict[int, dict[str, Any]] = {}
        else:
            checkpoint_map = _checkpoint_map(record)

        previous_nodes = previous_edges = previous_lm = -1
        previous_census: dict[str, Any] | None = None
        for checkpoint in checkpoint_values:
            row = checkpoint_map.get(checkpoint)
            if row is None:
                errors["checkpoint_accounting"] += 1
                continue
            cp_usage = row["usage"]
            cp_nodes = int(cp_usage["logical_lm_node_evals"])
            cp_edges = int(cp_usage["edge_selections"])
            cp_lm = int(cp_usage["logical_lm_node_evals"])
            checkpoint_payload = dict(row)
            checkpoint_digest = checkpoint_payload.pop(
                "checkpoint_payload_digest", None
            )
            cp_readout = row.get("readout_token_ids", [])
            cp_readout_valid = (
                isinstance(cp_readout, list)
                and len(cp_readout) <= 4
                and all(type(value) is int for value in cp_readout)
            )
            cp_success = cp_readout == target if cp_readout_valid else False
            cp_prefix = (
                _correct_prefix_length(cp_readout, target) if cp_readout_valid else -1
            )
            expected_active_plan = (
                ROUTING_ONLY_PLAN
                if method == "sobol_routing_only"
                or (method == "two_phase_action_256" and checkpoint > switch_request)
                else SOBOL_ALL_PLAN
            )
            expected_behavior_digest = _sha256_json(
                {
                    "tree_value_digest": row.get("tree_value_digest"),
                    "uniform_stream_digest": row.get("uniform_stream_digest"),
                    "active_uniform_sources": expected_active_plan.as_dict(),
                }
            )
            cumulative_fields = (
                "nodes_by_depth",
                "on_oracle_prefix_nodes_by_depth",
                "off_oracle_prefix_nodes_by_depth",
                "visits_by_depth",
                "on_oracle_prefix_visits_by_depth",
                "off_oracle_prefix_visits_by_depth",
                "oracle_node_visits_by_stage",
                "oracle_action_visits_by_stage",
                "token_selection_counts",
                "root_action_selection_counts",
                "root_coverage_cluster_counts",
            )
            cumulative = previous_census is None or all(
                len(row["census"][field]) == len(previous_census[field])
                and all(
                    int(current) >= int(previous)
                    for current, previous in zip(
                        row["census"][field], previous_census[field]
                    )
                )
                for field in cumulative_fields
            )
            if (
                any(
                    type(cp_usage.get(field)) is not int
                    for field in required_usage_integers
                    if field != "blocked_verifier_calls"
                )
                or (
                    cp_usage.get("first_success_lm_eval") is not None
                    and type(cp_usage.get("first_success_lm_eval")) is not int
                )
                or int(cp_usage["verifier_requests"]) != checkpoint
                or int(cp_usage["evaluation_only_calls"]) != 0
                or cp_nodes < previous_nodes
                or cp_edges < previous_edges
                or cp_lm < previous_lm
                or not _validate_census(
                    row["census"], nodes_created=cp_nodes, edges=cp_edges
                )
                or type(row.get("best_observed_success")) is not bool
                or row["best_observed_success"]
                is not (row["census"]["correct_stage_eos_trials"] > 0)
                or not cp_readout_valid
                or row.get("readout_success") is not cp_success
                or type(row.get("readout_correct_prefix_length")) is not int
                or row.get("readout_correct_prefix_length") != cp_prefix
                or checkpoint_digest != _sha256_json(checkpoint_payload)
                or row.get("behavior_state_digest") != expected_behavior_digest
                or row.get("collector_behavior_digest_before")
                != expected_behavior_digest
                or row.get("collector_behavior_digest_after")
                != expected_behavior_digest
                or row.get("collector_behavior_unchanged") is not True
                or not cumulative
            ):
                errors["checkpoint_accounting"] += 1
            previous_nodes, previous_edges, previous_lm = cp_nodes, cp_edges, cp_lm
            previous_census = row["census"]

        if checkpoint_map:
            final_cp = checkpoint_map[verifier_cap]
            if (
                final_cp["readout_token_ids"] != readout
                or final_cp["readout_success"] != exact_success
                or final_cp["tree_value_digest"]
                != record["search"]["final_tree_value_digest"]
                or final_cp["uniform_stream_digest"]
                != record["search"]["final_uniform_stream_digest"]
                or final_cp["behavior_state_digest"]
                != record["search"]["final_behavior_state_digest"]
                or int(final_cp["usage"]["edge_selections"]) != edges_used
                or int(final_cp["usage"]["logical_lm_node_evals"]) != lm_used
                or int(final_cp["usage"]["evaluation_only_calls"]) != 0
                or int(usage["evaluation_only_calls"]) != 1
                or bool(outcome["best_observed_success"])
                != (int(final_cp["census"]["correct_stage_eos_trials"]) > 0)
            ):
                errors["checkpoint_final_match"] += 1

            switch_edges = int(
                checkpoint_map[switch_request]["usage"]["edge_selections"]
            )
            switch_nodes = int(
                checkpoint_map[switch_request]["usage"]["logical_lm_node_evals"]
            )
            for checkpoint in checkpoint_values:
                cp = checkpoint_map[checkpoint]
                cp_edges = int(cp["usage"]["edge_selections"])
                cp_nodes = int(cp["usage"]["logical_lm_node_evals"])
                cp_switch_edges = (
                    min(cp_edges, switch_edges)
                    if method == "two_phase_action_256"
                    else 0
                )
                expected_reconfigs = (
                    switch_nodes
                    if method == "two_phase_action_256" and checkpoint > switch_request
                    else 0
                )
                # The checkpoint at 256 is deliberately captured before switching.
                if not _source_usage_valid(
                    cp["census"]["uniform_source_usage"],
                    method=method,
                    edges=cp_edges,
                    nodes=cp_nodes,
                    switch_edges=cp_switch_edges,
                    expected_reconfigurations=expected_reconfigs,
                ):
                    errors["checkpoint_source_accounting"] += 1
        else:
            switch_edges = -1
            switch_nodes = -1

        switches = record.get("switch_audit", [])
        if method == "two_phase_action_256":
            if len(switches) != 1:
                errors["switch_contract"] += 1
                switch_event = {}
            else:
                switch_event = switches[0]
            switch_integer_fields = (
                "completed_verifier_requests",
                "next_simulation_request_number",
                "existing_nodes_reconfigured",
                "tree_nodes_preserved",
                "selection_points_before",
                "selection_points_after",
            )
            if (
                not _has_exact_integer_fields(switch_event, switch_integer_fields)
                or switch_event.get("completed_verifier_requests") != switch_request
                or switch_event.get("next_simulation_request_number")
                != switch_request + 1
                or switch_event.get("from") != SOBOL_ALL_PLAN.as_dict()
                or switch_event.get("to") != ROUTING_ONLY_PLAN.as_dict()
                or switch_event.get("reason") != "predeclared_late_iid_action_phase"
                or switch_event.get("existing_nodes_reconfigured") != switch_nodes
                or switch_event.get("tree_nodes_preserved") != switch_nodes
                or switch_event.get("selection_points_before") != switch_edges
                or switch_event.get("selection_points_after") != switch_edges
                or switch_event.get("stream_points_unchanged") is not True
                or switch_event.get("stream_state_unchanged") is not True
                or switch_event.get("stream_state_digest_before")
                != switch_event.get("stream_state_digest_after")
                or switch_event.get("tree_value_unchanged") is not True
                or switch_event.get("uniform_stream_state_unchanged") is not True
                or switch_event.get("run_counters_unchanged") is not True
                or switch_event.get("tree_value_digest_before")
                != switch_event.get("tree_value_digest_after")
                or switch_event.get("tree_value_digest_before")
                != checkpoint_map.get(switch_request, {}).get("tree_value_digest")
                or switch_event.get("uniform_stream_digest_before")
                != switch_event.get("uniform_stream_digest_after")
                or switch_event.get("uniform_stream_digest_before")
                != checkpoint_map.get(switch_request, {}).get("uniform_stream_digest")
            ):
                errors["switch_contract"] += 1
            expected_reconfigs = switch_nodes
        else:
            if switches:
                errors["switch_contract"] += 1
            expected_reconfigs = 0

        source_usage = record["search"].get("uniform_source_usage", {})
        if not _source_usage_valid(
            source_usage,
            method=method,
            edges=edges_used,
            nodes=lm_used,
            switch_edges=(switch_edges if method == "two_phase_action_256" else 0),
            expected_reconfigurations=expected_reconfigs,
        ):
            errors["uniform_draw_accounting"] += 1

        phase = telemetry.get("phase_metrics")
        if checkpoint_map and phase is not None:
            recomputed = _phase_metrics(
                checkpoint_map,
                switch_request=switch_request,
                verifier_cap=verifier_cap,
            )
            phase_integer_fields = (
                "late_phase_completed_verifier_requests",
                "late_nonroot_visits",
                "late_nonroot_oracle_prefix_visits",
                "late_correct_stage_eos_trials",
                "late_probe_selection_count",
                "late_immediate_repeat_edge_count",
                "late_probe_reselection_edge_count",
            )
            phase_types_valid = (
                _has_exact_integer_fields(phase, phase_integer_fields)
                and _is_exact_integer_list(
                    phase.get("late_nodes_created_by_depth"), length=4
                )
                and _is_exact_integer_list(
                    phase.get("late_oracle_action_visits_by_stage"), length=4
                )
            )
            if (
                not phase_types_valid
                or not _json_exact_equal(phase, recomputed)
                or phase["late_nonroot_visits"] <= 0
                or phase["late_nonroot_oracle_prefix_visit_share"] is None
            ):
                errors["phase_metrics"] += 1
        else:
            errors["phase_metrics"] += 1

        first_snapshot = telemetry.get("first_success_after_backup_snapshot")
        if first_request is None:
            if first_snapshot is not None:
                errors["first_success_snapshot"] += 1
        elif not isinstance(first_snapshot, dict):
            errors["first_success_snapshot"] += 1
        else:
            first_payload = dict(first_snapshot)
            first_payload_digest = first_payload.pop(
                "first_success_payload_digest", None
            )
            first_integer_fields = (
                "completed_verifier_requests",
                "edge_selections",
                "logical_lm_node_evals",
                "nonroot_visits",
                "nonroot_oracle_prefix_visits",
                "correct_stage_total_visits",
                "correct_stage_eos_trials",
            )
            exact_first_integers = all(
                type(first_snapshot.get(field)) is int for field in first_integer_fields
            )
            first_edges = int(first_snapshot.get("edge_selections", -1))
            first_nonroot = int(first_snapshot.get("nonroot_visits", -1))
            first_on = int(first_snapshot.get("nonroot_oracle_prefix_visits", -1))
            first_stage = int(first_snapshot.get("correct_stage_total_visits", -1))
            first_eos = int(first_snapshot.get("correct_stage_eos_trials", -1))
            final_census = checkpoint_map[verifier_cap]["census"]
            if (
                not exact_first_integers
                or int(first_snapshot.get("completed_verifier_requests", -1))
                != int(first_request)
                or not 0 <= first_on <= first_nonroot <= first_edges <= edges_used
                or not 1 == first_eos <= first_stage <= first_edges
                or not 0
                <= int(first_snapshot.get("logical_lm_node_evals", -1))
                <= lm_used
                or int(final_census["nonroot_visits"]) < first_nonroot
                or int(final_census["nonroot_oracle_prefix_visits"]) < first_on
                or int(final_census["correct_stage_total_visits"]) < first_stage
                or int(final_census["correct_stage_eos_trials"]) < first_eos
                or first_payload_digest != _sha256_json(first_payload)
                or first_snapshot.get("collector_behavior_unchanged") is not True
                or first_snapshot.get("collector_behavior_digest_before")
                != first_snapshot.get("collector_behavior_digest_after")
            ):
                errors["first_success_snapshot"] += 1

        if any(
            row.get("collector_behavior_unchanged") is not True
            or row.get("collector_behavior_digest_before")
            != row.get("collector_behavior_digest_after")
            for row in checkpoint_rows
        ):
            errors["telemetry_contract"] += 1

        randomization = record.get("randomization", {})
        evaluation_scope = record.get("evaluation_scope", {})
        evaluation_integer_fields = (
            "search_verifier_feedback_calls",
            "passive_checkpoint_readouts",
            "final_outside_budget_readout_evaluations",
        )
        if (
            randomization.get("independent_unit") != "exploration_seed"
            or randomization.get("node_stream_seeded_from")
            != "exploration_seed_and_exact_prefix"
            or randomization.get("source_architecture")
            != "matched_full_dimension_column_mux"
            or randomization.get("both_sources_advanced_every_draw") is not True
            or randomization.get("switch_resets_streams") is not False
            or randomization.get("sobol_scramble") is not True
            or randomization.get("iid_seed_transform") != "node_seed XOR 0x1D1D1D"
            or randomization.get("common_random_numbers", {}).get(
                "across_profiles_for_unchanged_coordinates"
            )
            is not True
            or randomization.get("common_random_numbers", {}).get("scope")
            != "same exact prefix, exploration seed, and node draw index"
            or not _has_exact_integer_fields(
                evaluation_scope, evaluation_integer_fields
            )
            or evaluation_scope.get("search_verifier_feedback_calls") != verifier_used
            or evaluation_scope.get("passive_checkpoint_readouts")
            != len(checkpoint_values)
            or evaluation_scope.get("final_outside_budget_readout_evaluations") != 1
            or evaluation_scope.get("checkpoint_readouts_outside_verifier_budget")
            is not True
            or evaluation_scope.get("final_readout_reused_from_checkpoint_700")
            is not True
            or evaluation_scope.get("wall_time_scope")
            != "search_plus_passive_telemetry_instrumentation"
            or evaluation_scope.get("wall_time_is_performance_endpoint") is not False
        ):
            errors["randomization_and_evaluation_scope"] += 1

        expected_group = (
            f"role_lock_d4:sd{POSTERIOR_SD_SCALE:g}:seed{seed}:v{verifier_cap}"
        )
        group = str(record.get("paired_group_id"))
        if group != expected_group:
            errors["paired_group"] += 1
        groups[group].append((method, seed))

    # Phase-one identity is a strong implementation-level falsification check.
    for seed in seed_ids:
        block = records_by_seed.get(int(seed), {})
        if set(block) != set(METHODS):
            continue
        sobol_cp = _checkpoint_map(block["sobol_all"])
        two_phase_cp = _checkpoint_map(block["two_phase_action_256"])
        if set(sobol_cp) != set(checkpoint_values) or set(two_phase_cp) != set(
            checkpoint_values
        ):
            errors["phase_one_behavior_identity"] += 1
            continue
        for checkpoint in checkpoint_values:
            if checkpoint > switch_request:
                continue
            if (
                sobol_cp[checkpoint]["behavior_state_digest"]
                != two_phase_cp[checkpoint]["behavior_state_digest"]
            ):
                errors["phase_one_behavior_identity"] += 1

    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    group_errors = sum(
        len(values) != len(METHODS)
        or {value[0] for value in values} != set(METHODS)
        or len({value[1] for value in values}) != 1
        for values in groups.values()
    )
    if group_errors or len(groups) != len(seed_ids):
        errors["paired_group"] += group_errors + abs(len(groups) - len(seed_ids))
    fingerprint_errors = sum(len(values) != 1 for values in fingerprints.values())
    if (
        fingerprint_errors
        or len(fingerprints) != len(seed_ids)
        or len(all_fingerprints) != 1
    ):
        errors["candidate_contract"] += fingerprint_errors + 1

    checks = {
        "expected_record_count": len(records) == len(expected),
        "complete_method_by_seed_grid": not missing and not unexpected,
        "unique_composite_keys": duplicate_count == 0,
        "schema_and_strict_json": errors["schema"] == 0 and errors["strict_json"] == 0,
        "deterministic_digests": errors["digest"] == 0,
        "task_and_success_encoding": errors["task_and_success_encoding"] == 0,
        "exact_verifier_caps_and_positive_guard_headroom": errors["budget_contract"]
        == 0,
        "usage_accounting": errors["usage_accounting"] == 0,
        "first_success_and_snapshot": errors["first_success"] == 0
        and errors["first_success_snapshot"] == 0,
        "pruning_disabled": errors["pruning"] == 0,
        "source_and_config_propagated": errors["source_contract"] == 0
        and errors["config_propagation"] == 0,
        "candidate_manifest_identical": errors["candidate_contract"] == 0,
        "telemetry_contract_and_accounting": errors["telemetry_contract"] == 0
        and errors["checkpoint_accounting"] == 0
        and errors["checkpoint_final_match"] == 0
        and errors["phase_metrics"] == 0,
        "phase_one_behavior_identity": errors["phase_one_behavior_identity"] == 0,
        "switch_preserves_tree_and_streams": errors["switch_contract"] == 0,
        "uniform_draw_accounting": errors["uniform_draw_accounting"] == 0
        and errors["checkpoint_source_accounting"] == 0,
        "randomization_and_evaluation_scope": errors[
            "randomization_and_evaluation_scope"
        ]
        == 0,
        "paired_group_identity": errors["paired_group"] == 0,
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "status": "PASS" if not failures else "FAIL",
        "checks": checks,
        "failures": failures,
        "details": {
            "expected_records": len(expected),
            "observed_records": len(records),
            "duplicate_count": duplicate_count,
            "missing_count": len(missing),
            "unexpected_count": len(unexpected),
            "paired_groups": len(groups),
            "root_fingerprints": sorted(all_fingerprints),
            "error_counts": dict(errors),
            "minimum_lm_guard_headroom": min(
                (int(row["budget"]["guard_headroom"]["lm_nodes"]) for row in records),
                default=0,
            ),
            "minimum_edge_guard_headroom": min(
                (int(row["budget"]["guard_headroom"]["edges"]) for row in records),
                default=0,
            ),
        },
    }


def _validate_records(
    records: Sequence[dict[str, Any]],
    *,
    seed_ids: Sequence[int],
    verifier_cap: int,
    lm_node_ceiling: int,
    edge_ceiling: int,
    checkpoints: Sequence[int],
    switch_request: int,
) -> dict[str, Any]:
    """Return FAIL, rather than raising, for malformed external record shapes."""
    try:
        return _validate_records_impl(
            records,
            seed_ids=seed_ids,
            verifier_cap=verifier_cap,
            lm_node_ceiling=lm_node_ceiling,
            edge_ceiling=edge_ceiling,
            checkpoints=checkpoints,
            switch_request=switch_request,
        )
    except (
        AttributeError,
        KeyError,
        IndexError,
        TypeError,
        ValueError,
        OverflowError,
    ) as exc:
        return {
            "status": "FAIL",
            "checks": {"validator_completed_without_schema_exception": False},
            "failures": ["validator_completed_without_schema_exception"],
            "details": {
                "expected_records": len(seed_ids) * len(METHODS),
                "observed_records": len(records),
                "schema_exception_type": type(exc).__name__,
                "schema_exception": str(exc),
            },
        }


def _mean_or_none(values: Sequence[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _cell_summary(
    rows: Sequence[dict[str, Any]],
    *,
    checkpoints: Sequence[int],
    verifier_cap: int,
) -> dict[str, Any]:
    successes = sum(bool(row["outcome"]["readout_success"]) for row in rows)
    best_hits = sum(bool(row["outcome"]["best_observed_success"]) for row in rows)
    first_hits = [
        int(row["usage"]["first_success_verifier_request"])
        for row in rows
        if row["usage"]["first_success_verifier_request"] is not None
    ]
    restricted_hits = [
        (
            int(row["usage"]["first_success_verifier_request"])
            if row["usage"]["first_success_verifier_request"] is not None
            else verifier_cap + 1
        )
        for row in rows
    ]
    checkpoint_curve = []
    for checkpoint in checkpoints:
        checkpoint_rows = [_checkpoint_map(row)[int(checkpoint)] for row in rows]
        checkpoint_curve.append(
            {
                "completed_verifier_requests": int(checkpoint),
                "readout_success_count": sum(
                    bool(row["readout_success"]) for row in checkpoint_rows
                ),
                "readout_success_rate": statistics.fmean(
                    float(row["readout_success"]) for row in checkpoint_rows
                ),
                "best_observed_success_count": sum(
                    bool(row["best_observed_success"]) for row in checkpoint_rows
                ),
                "mean_nodes_created": statistics.fmean(
                    float(row["usage"]["logical_lm_node_evals"])
                    for row in checkpoint_rows
                ),
                "mean_edges": statistics.fmean(
                    float(row["usage"]["edge_selections"]) for row in checkpoint_rows
                ),
                "mean_nonroot_oracle_prefix_visit_share": statistics.fmean(
                    (
                        float(row["census"]["nonroot_oracle_prefix_visits"])
                        / float(row["census"]["nonroot_visits"])
                        if int(row["census"]["nonroot_visits"])
                        else 0.0
                    )
                    for row in checkpoint_rows
                ),
                "mean_correct_stage_eos_trials": statistics.fmean(
                    float(row["census"]["correct_stage_eos_trials"])
                    for row in checkpoint_rows
                ),
            }
        )

    phase_fields = (
        "late_nonroot_oracle_prefix_visit_share",
        "late_correct_stage_eos_trials_per_verifier_request",
        "late_nonroot_oracle_prefix_visits",
        "late_correct_stage_eos_trials",
        "late_probe_selection_share",
        "late_immediate_repeat_edge_share",
        "late_probe_reselection_edge_share",
    )
    final_censuses = [_checkpoint_map(row)[verifier_cap]["census"] for row in rows]

    def mean_vector(field: str, source: Sequence[dict[str, Any]]) -> list[float]:
        return [
            statistics.fmean(float(row[field][index]) for row in source)
            for index in range(4)
        ]

    phase_rows = [row["telemetry"]["phase_metrics"] for row in rows]
    root_coverage_deviations: list[float] = []
    for census in final_censuses:
        counts = [int(value) for value in census["root_coverage_cluster_counts"]]
        total = sum(counts)
        root_coverage_deviations.append(
            max(abs(count / total - 0.25) for count in counts) if total else 0.0
        )
    after_hit_shares: list[float] = []
    after_hit_eos_rates: list[float] = []
    for row in rows:
        first = row["telemetry"]["first_success_after_backup_snapshot"]
        if first is None:
            continue
        final = _checkpoint_map(row)[verifier_cap]["census"]
        late_nonroot = int(final["nonroot_visits"]) - int(first["nonroot_visits"])
        late_on = int(final["nonroot_oracle_prefix_visits"]) - int(
            first["nonroot_oracle_prefix_visits"]
        )
        remaining = verifier_cap - int(first["completed_verifier_requests"])
        if late_nonroot > 0:
            after_hit_shares.append(late_on / late_nonroot)
        if remaining > 0:
            after_hit_eos_rates.append(
                (
                    int(final["correct_stage_eos_trials"])
                    - int(first["correct_stage_eos_trials"])
                )
                / remaining
            )

    return {
        "replicates": len(rows),
        "readout_success_count": successes,
        "readout_success_rate": successes / len(rows),
        "readout_success_wilson_95": _wilson_interval(successes, len(rows)),
        "best_observed_success_count": best_hits,
        "best_observed_success_rate": best_hits / len(rows),
        "first_success_observed_count": len(first_hits),
        "first_success_censored_count": len(rows) - len(first_hits),
        "mean_first_success_verifier_request_among_hits": _mean_or_none(first_hits),
        "mean_restricted_first_success_index": statistics.fmean(restricted_hits),
        "mean_usage": {
            field: statistics.fmean(float(row["usage"][field]) for row in rows)
            for field in (
                "logical_lm_node_evals",
                "full_prefix_tokens",
                "verifier_requests",
                "edge_selections",
            )
        },
        "mean_late_phase_metrics": {
            field: statistics.fmean(
                float(row["telemetry"]["phase_metrics"][field]) for row in rows
            )
            for field in phase_fields
        },
        "mean_final_telemetry": {
            "nodes_by_depth": mean_vector("nodes_by_depth", final_censuses),
            "on_oracle_prefix_nodes_by_depth": mean_vector(
                "on_oracle_prefix_nodes_by_depth", final_censuses
            ),
            "off_oracle_prefix_nodes_by_depth": mean_vector(
                "off_oracle_prefix_nodes_by_depth", final_censuses
            ),
            "oracle_action_visits_by_stage": mean_vector(
                "oracle_action_visits_by_stage", final_censuses
            ),
            "mean_probe_selection_count": statistics.fmean(
                float(row["probe_selection_count"]) for row in final_censuses
            ),
            "mean_token_reselection_edge_count": statistics.fmean(
                float(row["token_reselection_edge_count"]) for row in final_censuses
            ),
            "mean_immediate_repeat_edge_count": statistics.fmean(
                float(row["immediate_repeat_edge_count"]) for row in final_censuses
            ),
            "mean_root_coverage_max_uniform_deviation": statistics.fmean(
                root_coverage_deviations
            ),
        },
        "mean_late_depth_telemetry": {
            "nodes_created_by_depth": mean_vector(
                "late_nodes_created_by_depth", phase_rows
            ),
            "oracle_action_visits_by_stage": mean_vector(
                "late_oracle_action_visits_by_stage", phase_rows
            ),
        },
        "checkpoint_curve_descriptive": checkpoint_curve,
        "after_first_hit_descriptive": {
            "conditioning_warning": (
                "conditioned on a post-treatment success event; not a causal contrast"
            ),
            "runs_with_hit": len(first_hits),
            "runs_with_remaining_nonroot_visits": len(after_hit_shares),
            "runs_with_remaining_verifier_requests": len(after_hit_eos_rates),
            "mean_nonroot_oracle_prefix_visit_share": _mean_or_none(after_hit_shares),
            "mean_correct_stage_eos_trials_per_remaining_request": _mean_or_none(
                after_hit_eos_rates
            ),
        },
        "minimum_lm_guard_headroom": min(
            int(row["budget"]["guard_headroom"]["lm_nodes"]) for row in rows
        ),
        "minimum_edge_guard_headroom": min(
            int(row["budget"]["guard_headroom"]["edges"]) for row in rows
        ),
    }


def _paired_contrast(
    blocks: dict[int, dict[str, dict[str, Any]]],
    *,
    candidate: str,
    reference: str,
    label: str,
    role: str,
    verifier_cap: int,
    bootstrap_seed: int,
) -> dict[str, Any]:
    success_deltas: list[float] = []
    best_deltas: list[float] = []
    first_hit_deltas: list[float] = []
    candidate_only = reference_only = both_success = both_failure = 0
    resource_fields = (
        "logical_lm_node_evals",
        "full_prefix_tokens",
        "edge_selections",
    )
    resource_deltas: dict[str, list[float]] = {field: [] for field in resource_fields}
    mechanism_fields = (
        "late_nonroot_oracle_prefix_visit_share",
        "late_correct_stage_eos_trials_per_verifier_request",
        "late_nonroot_oracle_prefix_visits",
        "late_correct_stage_eos_trials",
        "late_probe_selection_share",
        "late_immediate_repeat_edge_share",
        "late_probe_reselection_edge_share",
    )
    mechanism_deltas: dict[str, list[float]] = {field: [] for field in mechanism_fields}
    checkpoint_success_deltas: dict[int, list[float]] = defaultdict(list)

    for seed in sorted(blocks):
        block = blocks[seed]
        candidate_row = block[candidate]
        reference_row = block[reference]
        candidate_success = int(candidate_row["outcome"]["readout_success"])
        reference_success = int(reference_row["outcome"]["readout_success"])
        success_deltas.append(float(candidate_success - reference_success))
        candidate_only += int(candidate_success == 1 and reference_success == 0)
        reference_only += int(candidate_success == 0 and reference_success == 1)
        both_success += int(candidate_success == 1 and reference_success == 1)
        both_failure += int(candidate_success == 0 and reference_success == 0)
        best_deltas.append(
            float(
                int(candidate_row["outcome"]["best_observed_success"])
                - int(reference_row["outcome"]["best_observed_success"])
            )
        )
        candidate_hit = candidate_row["usage"]["first_success_verifier_request"]
        reference_hit = reference_row["usage"]["first_success_verifier_request"]
        first_hit_deltas.append(
            float(
                (candidate_hit if candidate_hit is not None else verifier_cap + 1)
                - (reference_hit if reference_hit is not None else verifier_cap + 1)
            )
        )
        for field in resource_fields:
            resource_deltas[field].append(
                float(candidate_row["usage"][field] - reference_row["usage"][field])
            )
        for field in mechanism_fields:
            mechanism_deltas[field].append(
                float(
                    candidate_row["telemetry"]["phase_metrics"][field]
                    - reference_row["telemetry"]["phase_metrics"][field]
                )
            )
        candidate_cp = _checkpoint_map(candidate_row)
        reference_cp = _checkpoint_map(reference_row)
        for checkpoint in candidate_cp:
            checkpoint_success_deltas[checkpoint].append(
                float(
                    int(candidate_cp[checkpoint]["readout_success"])
                    - int(reference_cp[checkpoint]["readout_success"])
                )
            )

    return {
        "label": label,
        "role": role,
        "candidate": candidate,
        "reference": reference,
        "paired_blocks": len(success_deltas),
        "mean_success_delta": statistics.fmean(success_deltas),
        "paired_bootstrap_success_95_nominal": _bootstrap_mean_interval(
            success_deltas, bootstrap_seed
        ),
        "discordance": {
            "candidate_only": candidate_only,
            "reference_only": reference_only,
            "both_success": both_success,
            "both_failure": both_failure,
        },
        "mcnemar_p": _exact_mcnemar_p(candidate_only, reference_only),
        "mean_best_observed_success_delta": statistics.fmean(best_deltas),
        "mean_restricted_first_success_index_delta": statistics.fmean(first_hit_deltas),
        "paired_bootstrap_restricted_first_success_95": _bootstrap_mean_interval(
            first_hit_deltas, bootstrap_seed + 1
        ),
        "mean_resource_delta": {
            field: {
                "mean": statistics.fmean(values),
                "paired_bootstrap_95": _bootstrap_mean_interval(
                    values, bootstrap_seed + 100 + index
                ),
            }
            for index, (field, values) in enumerate(resource_deltas.items())
        },
        "mechanism_deltas_descriptive": {
            field: {
                "mean": statistics.fmean(values),
                "paired_bootstrap_95_nominal": _bootstrap_mean_interval(
                    values, bootstrap_seed + 200 + index
                ),
            }
            for index, (field, values) in enumerate(mechanism_deltas.items())
        },
        "checkpoint_success_deltas_descriptive": [
            {
                "completed_verifier_requests": checkpoint,
                "mean_delta": statistics.fmean(values),
            }
            for checkpoint, values in sorted(checkpoint_success_deltas.items())
        ],
    }


def _add_simultaneous_primary_intervals(
    comparisons: Sequence[dict[str, Any]],
    blocks: dict[int, dict[str, dict[str, Any]]],
    bootstrap_seed: int,
) -> str:
    labels = (
        "two_phase_vs_routing_only",
        "two_phase_vs_sobol_all",
    )
    by_label = {row["label"]: row for row in comparisons}
    matrix = torch.tensor(
        [
            [
                float(block["two_phase_action_256"]["outcome"]["readout_success"])
                - float(block["sobol_routing_only"]["outcome"]["readout_success"]),
                float(block["two_phase_action_256"]["outcome"]["readout_success"])
                - float(block["sobol_all"]["outcome"]["readout_success"]),
            ]
            for _, block in sorted(blocks.items())
        ],
        dtype=torch.float64,
    )
    observed = matrix.mean(dim=0)
    generator = torch.Generator().manual_seed(int(bootstrap_seed))
    indices = torch.randint(
        len(matrix),
        (BOOTSTRAP_SAMPLES, len(matrix)),
        generator=generator,
    )
    bootstrap_means = matrix[indices].mean(dim=1)
    max_deviation = torch.max(torch.abs(bootstrap_means - observed), dim=1).values
    critical = float(
        max_deviation.sort().values[int(0.95 * (BOOTSTRAP_SAMPLES - 1))].item()
    )
    for index, label in enumerate(labels):
        mean = float(observed[index].item())
        by_label[label]["paired_bootstrap_success_95_simultaneous"] = [
            max(-1.0, mean - critical),
            min(1.0, mean + critical),
        ]
    return (
        "paired exploration-seed bootstrap; 95th percentile of maximum absolute "
        "deviation across the two candidate-vs-control risk differences"
    )


def _interval_direction(interval: Sequence[float]) -> str:
    if float(interval[0]) > 0.0:
        return "positive"
    if float(interval[1]) < 0.0:
        return "negative"
    return "inconclusive"


def summarize(
    records: Sequence[dict[str, Any]],
    *,
    seed_ids: Sequence[int],
    verifier_cap: int,
    lm_node_ceiling: int,
    edge_ceiling: int,
    checkpoints: Sequence[int],
    switch_request: int,
    diagnostic_seed: int = 313,
    run_mode: str = "analysis",
) -> dict[str, Any]:
    quality = _validate_records(
        records,
        seed_ids=seed_ids,
        verifier_cap=verifier_cap,
        lm_node_ceiling=lm_node_ceiling,
        edge_ceiling=edge_ceiling,
        checkpoints=checkpoints,
        switch_request=switch_request,
    )
    if quality["status"] != "PASS":
        raise ValueError(f"invalid two-phase records: {quality['failures']}")

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    blocks: dict[int, dict[str, dict[str, Any]]] = defaultdict(dict)
    for record in records:
        method, seed = _record_key(record)
        grouped[method].append(record)
        blocks[seed][method] = record

    cells = [
        {
            "method": method,
            **_cell_summary(
                grouped[method],
                checkpoints=checkpoints,
                verifier_cap=verifier_cap,
            ),
        }
        for method in METHODS
    ]
    planned = (
        (
            "two_phase_action_256",
            "sobol_routing_only",
            "two_phase_vs_routing_only",
            "primary_engineering_substrate",
        ),
        (
            "two_phase_action_256",
            "sobol_all",
            "two_phase_vs_sobol_all",
            "primary_switch_effect",
        ),
        (
            "sobol_all",
            "sobol_routing_only",
            "sobol_all_vs_routing_only",
            "secondary_descriptive_control",
        ),
    )
    comparisons = [
        _paired_contrast(
            blocks,
            candidate=candidate,
            reference=reference,
            label=label,
            role=role,
            verifier_cap=verifier_cap,
            bootstrap_seed=diagnostic_seed + index * 1_000,
        )
        for index, (candidate, reference, label, role) in enumerate(planned)
    ]
    _holm_adjust(comparisons[:2])
    comparisons[2]["holm_adjusted_p"] = None
    simultaneous_method = _add_simultaneous_primary_intervals(
        comparisons,
        blocks,
        diagnostic_seed + 20_000,
    )
    routing_comparison = comparisons[0]
    routing_interval = routing_comparison["paired_bootstrap_success_95_simultaneous"]
    mechanism = routing_comparison["mechanism_deltas_descriptive"]
    on_path_delta = float(mechanism["late_nonroot_oracle_prefix_visit_share"]["mean"])
    eos_delta = float(
        mechanism["late_correct_stage_eos_trials_per_verifier_request"]["mean"]
    )
    mechanism_improved = on_path_delta > 0.0 and eos_delta > 0.0
    success_delta = float(routing_comparison["mean_success_delta"])
    full_gate_design = (
        run_mode == "full"
        and [int(seed) for seed in seed_ids]
        == list(range(FULL_SEED_START, FULL_SEED_START + FULL_SEED_COUNT))
        and verifier_cap == VERIFIER_CAP
        and lm_node_ceiling == LM_NODE_CEILING
        and edge_ceiling == EDGE_CEILING
        and tuple(int(value) for value in checkpoints) == CHECKPOINTS
        and switch_request == SWITCH_REQUEST
        and diagnostic_seed == 313
    )
    if not full_gate_design:
        gate_action = "not_evaluated_until_exact_full_cohort"
        gate_reason = "engineering gate is reserved for the fixed fresh n=64 design"
    elif not mechanism_improved:
        gate_action = "stop_threshold_tuning_and_run_credit_assignment_ablation"
        gate_reason = "late on-path and EOS mechanism endpoints did not both improve"
    elif float(routing_interval[1]) < 0.0:
        gate_action = "stop_threshold_tuning_and_run_credit_assignment_ablation"
        gate_reason = "success interval was wholly negative despite telemetry"
    elif success_delta > 0.0:
        gate_action = "authorize_one_fresh_standalone_n128_validation"
        gate_reason = (
            "paired success point estimate and both mechanism endpoints improved"
        )
    else:
        gate_action = "at_most_one_predeclared_fresh_n128_validation"
        gate_reason = "mechanism improved while success remained inconclusive"

    seed_set = set(int(seed) for seed in seed_ids)
    prior_overlap = len(seed_set & set(range(FULL_SEED_START)))
    return {
        "schema_version": SCHEMA_VERSION,
        "record_type": "two_phase_sampler_summary",
        "design": {
            "run_mode": run_mode,
            "task": "role_lock_d4",
            "methods": list(METHODS),
            "posterior_sd_scale": POSTERIOR_SD_SCALE,
            "verifier_cap": verifier_cap,
            "lm_node_ceiling": lm_node_ceiling,
            "edge_ceiling": edge_ceiling,
            "switch_after_completed_verifier_request": switch_request,
            "phase_one_request_numbers": [1, switch_request],
            "phase_two_request_numbers": [switch_request + 1, verifier_cap],
            "checkpoint_requests": [int(value) for value in checkpoints],
            "exploration_seed_ids": [int(seed) for seed in seed_ids],
            "independent_randomization_unit": "exploration_seed",
            "matched_primary_budget": "verifier_requests",
            "primary_outcome": "readout_success_at_exact_verifier_cap",
            "primary_contrasts": [
                "two_phase_action_256_minus_sobol_routing_only",
                "two_phase_action_256_minus_sobol_all",
            ],
            "threshold_selection": "posthoc_from_preceding_fixed_verifier_curve",
            "threshold_sweep": False,
            "diagnostic_bootstrap_seed": int(diagnostic_seed),
            "engineering_gate_evaluable": full_gate_design,
            "prior_experiment_seed_overlap": prior_overlap,
            "cohort_scope": (
                "fresh_from_all_prior_role_lock_cohorts"
                if prior_overlap == 0
                else "overlaps_prior_role_lock_cohorts"
            ),
        },
        "data_quality": quality,
        "cells": cells,
        "planned_pairwise_contrasts": comparisons,
        "primary_endpoints": [
            {
                "candidate": row["candidate"],
                "reference": row["reference"],
                "mean_delta": row["mean_success_delta"],
                "paired_bootstrap_95_simultaneous": row[
                    "paired_bootstrap_success_95_simultaneous"
                ],
                "exact_mcnemar_p": row["mcnemar_p"],
                "holm_adjusted_p_primary_family": row["holm_adjusted_p"],
            }
            for row in comparisons[:2]
        ],
        "simultaneous_interval_method": simultaneous_method,
        "engineering_decision": {
            "comparison": "two_phase_action_256_minus_sobol_routing_only",
            "success_point_delta": success_delta,
            "success_interval_direction": _interval_direction(routing_interval),
            "mechanism_gate": {
                "definition": "both paired late-phase point deltas must be strictly positive",
                "late_nonroot_oracle_prefix_visit_share_delta": on_path_delta,
                "late_correct_stage_eos_rate_delta": eos_delta,
                "observed_point_condition": mechanism_improved,
                "passed": mechanism_improved if full_gate_design else None,
            },
            "action": gate_action,
            "reason": gate_reason,
            "followup_if_authorized": {
                "fresh_seed_ids": list(range(704, 832)),
                "replicates": 128,
                "standalone_primary_analysis": True,
                "pool_selection_cohort_for_primary": False,
            },
            "claim_rule": (
                "the n=64 gate authorizes validation but does not establish superiority; "
                "success superiority requires a simultaneous interval wholly above zero"
            ),
        },
        "limitations": [
            "The switch threshold was selected after inspecting a prior cohort.",
            "This is an oracle-aligned static-token Role-Lock toy task.",
            "Checkpoint and mechanism telemetry are descriptive and oracle-informed.",
            "Equal verifier calls are not equal total compute or deployment wall time.",
            "After-first-hit summaries condition on a post-treatment event.",
            "Uncertainty remains a nonstationary proxy, not an exact posterior.",
        ],
    }


def _percent(value: float) -> str:
    return f"{100.0 * value:.1f}%"


def _pp(value: float) -> str:
    return f"{100.0 * value:+.1f} pp"


def render_report(summary: dict[str, Any]) -> str:
    design = summary["design"]
    cells = {row["method"]: row for row in summary["cells"]}
    lines = [
        "# QMC-BMGS two-phase action-source experiment",
        "",
        "## Outcome",
        "",
        (
            f"Role-Lock D4, exact verifier cap {design['verifier_cap']}, switch after "
            f"request {design['switch_after_completed_verifier_request']}, paired "
            f"n={len(design['exploration_seed_ids'])}."
        ),
        "",
        "| Method | Readout success | LM nodes | Edges | Late on-path share | Late EOS / request |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for method in METHODS:
        cell = cells[method]
        late = cell["mean_late_phase_metrics"]
        lines.append(
            f"| `{method}` | {_percent(cell['readout_success_rate'])} "
            f"({cell['readout_success_count']}/{cell['replicates']}) | "
            f"{cell['mean_usage']['logical_lm_node_evals']:.1f} | "
            f"{cell['mean_usage']['edge_selections']:.1f} | "
            f"{late['late_nonroot_oracle_prefix_visit_share']:.4f} | "
            f"{late['late_correct_stage_eos_trials_per_verifier_request']:.4f} |"
        )
    lines.extend(
        [
            "",
            "## Behavioral telemetry",
            "",
            (
                "| Method | Final nodes d0/d1/d2/d3 | Late d3 nodes | "
                "Late oracle actions d0/d1/d2/d3 | "
                "Late PROBE share | Late immediate-repeat share | "
                "Late PROBE-reselection share | Root coverage deviation |"
            ),
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for method in METHODS:
        cell = cells[method]
        final = cell["mean_final_telemetry"]
        late = cell["mean_late_phase_metrics"]
        late_depth = cell["mean_late_depth_telemetry"]
        nodes_text = "/".join(f"{value:.1f}" for value in final["nodes_by_depth"])
        oracle_text = "/".join(
            f"{value:.1f}" for value in late_depth["oracle_action_visits_by_stage"]
        )
        lines.append(
            f"| `{method}` | {nodes_text} | "
            f"{late_depth['nodes_created_by_depth'][3]:.1f} | "
            f"{oracle_text} | "
            f"{late['late_probe_selection_share']:.4f} | "
            f"{late['late_immediate_repeat_edge_share']:.4f} | "
            f"{late['late_probe_reselection_edge_share']:.4f} | "
            f"{final['mean_root_coverage_max_uniform_deviation']:.4f} |"
        )
    lines.extend(
        [
            "",
            "## Paired contrasts",
            "",
            "| Contrast | Role | Success delta | Simultaneous 95% | Holm p | On-path delta | EOS-rate delta |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in summary["planned_pairwise_contrasts"]:
        interval = row.get("paired_bootstrap_success_95_simultaneous")
        interval_text = (
            f"[{_pp(interval[0])}, {_pp(interval[1])}]"
            if interval is not None
            else "nominal only"
        )
        holm = row.get("holm_adjusted_p")
        holm_text = f"{holm:.4g}" if holm is not None else "not in family"
        mechanism = row["mechanism_deltas_descriptive"]
        lines.append(
            f"| `{row['label']}` | {row['role']} | {_pp(row['mean_success_delta'])} | "
            f"{interval_text} | {holm_text} | "
            f"{mechanism['late_nonroot_oracle_prefix_visit_share']['mean']:+.4f} | "
            f"{mechanism['late_correct_stage_eos_trials_per_verifier_request']['mean']:+.4f} |"
        )
    decision = summary["engineering_decision"]
    quality = summary["data_quality"]
    mechanism_gate_display = (
        "not evaluated"
        if decision["mechanism_gate"]["passed"] is None
        else str(decision["mechanism_gate"]["passed"])
    )
    gate_scope_line = (
        "- This exploratory full-cohort gate authorizes validation; it does not "
        "declare a winner."
        if design["engineering_gate_evaluable"]
        else "- Provisional shard/smoke summaries cannot trigger the engineering gate."
    )
    lines.extend(
        [
            "",
            "## Engineering gate",
            "",
            f"- Mechanism gate: `{mechanism_gate_display}`.",
            f"- Action: `{decision['action']}`.",
            f"- Reason: {decision['reason']}.",
            gate_scope_line,
            "",
            "## Data quality",
            "",
            (
                f"Status: `{quality['status']}`. Records: "
                f"{quality['details']['observed_records']}; paired groups: "
                f"{quality['details']['paired_groups']}."
            ),
            (
                "Minimum guard headroom: LM nodes "
                f"{quality['details']['minimum_lm_guard_headroom']}, edges "
                f"{quality['details']['minimum_edge_guard_headroom']}."
            ),
            "",
            "## Claim boundary",
            "",
            (
                "The threshold was selected from a previous cohort. Telemetry is "
                "oracle-informed and descriptive; equal verifier calls are not equal total compute."
            ),
            "",
            "## Reproduce",
            "",
            "```bash",
            "python -m qmc_bmgs.experiments.two_phase_sampler",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _behavior_usage(record: dict[str, Any]) -> dict[str, Any]:
    result = dict(record["usage"])
    result.pop("wall_time_s", None)
    result.pop("evaluation_only_calls", None)
    return result


def _self_test() -> None:
    seed_ids = [0, 1]
    verifier_cap = 12
    lm_ceiling = 128
    edge_ceiling = 256
    checkpoints = (3, 4, 8, 12)
    switch_request = 4
    records = run_experiment(
        seed_ids=seed_ids,
        verifier_cap=verifier_cap,
        lm_node_ceiling=lm_ceiling,
        edge_ceiling=edge_ceiling,
        checkpoints=checkpoints,
        switch_request=switch_request,
    )
    repeat = run_experiment(
        seed_ids=seed_ids,
        verifier_cap=verifier_cap,
        lm_node_ceiling=lm_ceiling,
        edge_ceiling=edge_ceiling,
        checkpoints=checkpoints,
        switch_request=switch_request,
    )
    assert [row["deterministic_digest"] for row in records] == [
        row["deterministic_digest"] for row in repeat
    ]
    summary = summarize(
        records,
        seed_ids=seed_ids,
        verifier_cap=verifier_cap,
        lm_node_ceiling=lm_ceiling,
        edge_ceiling=edge_ceiling,
        checkpoints=checkpoints,
        switch_request=switch_request,
        run_mode="self_test",
    )
    assert len(records) == 6
    assert summary["data_quality"]["status"] == "PASS"
    assert len(summary["planned_pairwise_contrasts"]) == 3
    assert "two-phase action-source" in render_report(summary)

    # Passive telemetry must leave the final behavior exactly unchanged.
    task = RoleLockTask(4)
    variant = _variant_map()["two_phase_action_256"]
    seeds = SeedPlan(task_seed=4, exploration_seed=7, partition_seed=10_000)
    with_telemetry = _run_variant(
        task=task,
        variant=variant,
        seeds=seeds,
        registry=CandidateRegistry(),
        verifier_cap=verifier_cap,
        lm_node_ceiling=lm_ceiling,
        edge_ceiling=edge_ceiling,
        checkpoints=checkpoints,
        switch_request=switch_request,
        telemetry_enabled=True,
    )
    without_telemetry = _run_variant(
        task=task,
        variant=variant,
        seeds=seeds,
        registry=CandidateRegistry(),
        verifier_cap=verifier_cap,
        lm_node_ceiling=lm_ceiling,
        edge_ceiling=edge_ceiling,
        checkpoints=(),
        switch_request=switch_request,
        telemetry_enabled=False,
    )
    assert (
        with_telemetry["search"]["final_tree_value_digest"]
        == without_telemetry["search"]["final_tree_value_digest"]
    )
    assert (
        with_telemetry["search"]["final_uniform_stream_digest"]
        == without_telemetry["search"]["final_uniform_stream_digest"]
    )
    assert (
        with_telemetry["search"]["final_behavior_state_digest"]
        == without_telemetry["search"]["final_behavior_state_digest"]
    )
    assert with_telemetry["outcome"] == without_telemetry["outcome"]
    assert _behavior_usage(with_telemetry) == _behavior_usage(without_telemetry)
    assert (
        with_telemetry["search"]["uniform_source_usage"]
        == without_telemetry["search"]["uniform_source_usage"]
    )
    assert without_telemetry["telemetry"]["checkpoints"] == []
    assert without_telemetry["telemetry"]["first_success_after_backup_snapshot"] is None

    def assert_mutation_fails(mutator: Any) -> None:
        corrupted = json.loads(json.dumps(records))
        mutator(corrupted)
        for row in corrupted:
            row["deterministic_digest"] = canonical_record_digest(row)
        quality = _validate_records(
            corrupted,
            seed_ids=seed_ids,
            verifier_cap=verifier_cap,
            lm_node_ceiling=lm_ceiling,
            edge_ceiling=edge_ceiling,
            checkpoints=checkpoints,
            switch_request=switch_request,
        )
        assert quality["status"] == "FAIL"

    def rehash_checkpoint(checkpoint: dict[str, Any]) -> None:
        payload = dict(checkpoint)
        payload.pop("checkpoint_payload_digest", None)
        checkpoint["checkpoint_payload_digest"] = _sha256_json(payload)

    def corrupt_intermediate_readout(rows: list[dict[str, Any]]) -> None:
        checkpoint = rows[0]["telemetry"]["checkpoints"][0]
        checkpoint["readout_success"] = not checkpoint["readout_success"]
        rehash_checkpoint(checkpoint)

    def corrupt_first_success(rows: list[dict[str, Any]]) -> None:
        snapshot = next(
            row["telemetry"]["first_success_after_backup_snapshot"]
            for row in rows
            if row["telemetry"]["first_success_after_backup_snapshot"] is not None
        )
        snapshot["nonroot_visits"] = 999
        payload = dict(snapshot)
        payload.pop("first_success_payload_digest", None)
        snapshot["first_success_payload_digest"] = _sha256_json(payload)

    def corrupt_checkpoint_counter_type(rows: list[dict[str, Any]]) -> None:
        checkpoint = rows[0]["telemetry"]["checkpoints"][0]
        checkpoint["completed_verifier_requests"] = (
            float(checkpoint["completed_verifier_requests"]) + 0.9
        )
        rehash_checkpoint(checkpoint)

    def corrupt_census_scalar_type(rows: list[dict[str, Any]]) -> None:
        checkpoint = rows[0]["telemetry"]["checkpoints"][0]
        census = checkpoint["census"]
        census["nonroot_visits"] = float(census["nonroot_visits"]) + 0.9
        rehash_checkpoint(checkpoint)

    assert_mutation_fails(
        lambda rows: rows[0]["usage"].__setitem__("verifier_requests", 11)
    )
    assert_mutation_fails(lambda rows: rows.append(json.loads(json.dumps(rows[0]))))
    assert_mutation_fails(lambda rows: rows[0]["telemetry"]["checkpoints"].pop(0))
    assert_mutation_fails(corrupt_intermediate_readout)
    assert_mutation_fails(
        lambda rows: rows[0]["telemetry"]["checkpoints"][0]["census"][
            "nodes_by_depth"
        ].__setitem__(0, 99)
    )
    assert_mutation_fails(
        lambda rows: rows[0]["telemetry"]["checkpoints"][0].__setitem__(
            "collector_behavior_unchanged", False
        )
    )
    assert_mutation_fails(
        lambda rows: rows[2]["telemetry"]["checkpoints"][0].__setitem__(
            "behavior_state_digest", "wrong"
        )
    )
    assert_mutation_fails(
        lambda rows: rows[2]["switch_audit"][0].__setitem__(
            "completed_verifier_requests", 5
        )
    )
    assert_mutation_fails(
        lambda rows: rows[2]["switch_audit"][0].__setitem__(
            "uniform_stream_digest_after", "rewound"
        )
    )
    assert_mutation_fails(
        lambda rows: rows[2]["switch_audit"][0].__setitem__(
            "stream_state_unchanged", False
        )
    )
    assert_mutation_fails(
        lambda rows: rows[2]["method"]["phase_schedule"][1].__setitem__(
            "completed_request_counter_before_phase", 999
        )
    )
    assert_mutation_fails(
        lambda rows: rows[2]["search"]["uniform_source_usage"][
            "selection_points_by_source_plan"
        ].__setitem__(ROUTING_PLAN_KEY, 0)
    )
    assert_mutation_fails(
        lambda rows: rows[2]["telemetry"]["phase_metrics"].__setitem__(
            "late_correct_stage_eos_trials", 999
        )
    )
    assert_mutation_fails(corrupt_first_success)
    assert_mutation_fails(
        lambda rows: rows[0]["usage"].__setitem__("verifier_requests", 12.9)
    )
    assert_mutation_fails(lambda rows: rows[0]["budget"].__setitem__("limit", 12.9))
    assert_mutation_fails(corrupt_checkpoint_counter_type)
    assert_mutation_fails(corrupt_census_scalar_type)
    assert_mutation_fails(
        lambda rows: rows[0]["telemetry"]["checkpoint_requests"].__setitem__(
            0, float(rows[0]["telemetry"]["checkpoint_requests"][0])
        )
    )
    assert_mutation_fails(
        lambda rows: rows[0]["search"]["uniform_source_usage"].__setitem__(
            "selected_sobol_scalar_values",
            float(
                rows[0]["search"]["uniform_source_usage"][
                    "selected_sobol_scalar_values"
                ]
            )
            + 0.9,
        )
    )
    assert_mutation_fails(
        lambda rows: rows[0]["search"].__setitem__("uniform_source_usage", None)
    )
    assert_mutation_fails(
        lambda rows: rows[0]["search"].__setitem__("root_candidate_fingerprint", 123)
    )
    assert_mutation_fails(lambda rows: rows[0]["task"].__setitem__("reward", 5))
    assert_mutation_fails(
        lambda rows: rows[0]["experiment"].__setitem__("fixed_pruning", 1)
    )
    assert_mutation_fails(
        lambda rows: rows[0]["randomization"].__setitem__("sobol_scramble", 1)
    )
    assert_mutation_fails(lambda rows: rows[0].pop("task"))
    assert_mutation_fails(
        lambda rows: rows[0]["outcome"].__setitem__(
            "readout_success", not rows[0]["outcome"]["readout_success"]
        )
    )
    assert_mutation_fails(
        lambda rows: rows[0]["search"].__setitem__("root_candidate_fingerprint", None)
    )
    assert_mutation_fails(
        lambda rows: rows[0]["search_config"].__setitem__("seed", 999)
    )
    assert_mutation_fails(
        lambda rows: rows[0]["seeds"].__setitem__("candidate_seed", 999)
    )
    assert_mutation_fails(lambda rows: rows[0].__setitem__("paired_group_id", "wrong"))
    json.dumps(summary, allow_nan=False)
    print("two-phase sampler self-test: PASS")


def main() -> None:
    base = Path.cwd() / "artifacts" / "work" / "qmc_bmgs_two_phase"
    default_runs = base.with_name(base.name + "_runs.jsonl")
    default_summary = base.with_name(base.name + "_summary.json")
    default_report = base.with_name(base.name + "_report.md")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--shard", action="store_true")
    parser.add_argument("--verifier-cap", type=int, default=VERIFIER_CAP)
    parser.add_argument("--lm-node-ceiling", type=int, default=LM_NODE_CEILING)
    parser.add_argument("--edge-ceiling", type=int, default=EDGE_CEILING)
    parser.add_argument("--seed-start", type=int, default=FULL_SEED_START)
    parser.add_argument("--seeds", type=int, default=FULL_SEED_COUNT)
    parser.add_argument("--diagnostic-seed", type=int, default=313)
    parser.add_argument("--progress-every", type=int, default=32)
    parser.add_argument(
        "--resume-from",
        type=Path,
        action="append",
        default=[],
        help="Reuse digest-valid matching JSONL shards and run only missing cells",
    )
    parser.add_argument(
        "--runs-jsonl",
        type=Path,
        default=default_runs,
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=default_summary,
    )
    parser.add_argument(
        "--report-md",
        type=Path,
        default=default_report,
    )
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        return
    if args.smoke and args.shard:
        parser.error("--smoke and --shard are mutually exclusive")
    if min(args.verifier_cap, args.lm_node_ceiling, args.edge_ceiling) < 1:
        parser.error("budget limits must be positive")
    if args.seed_start < 0 or args.seeds < 1:
        parser.error("--seed-start must be nonnegative and --seeds positive")
    if args.progress_every < 0:
        parser.error("--progress-every must be nonnegative")

    verifier_cap = args.verifier_cap
    lm_node_ceiling = args.lm_node_ceiling
    edge_ceiling = args.edge_ceiling
    seed_start = args.seed_start
    seeds_count = args.seeds
    checkpoints = CHECKPOINTS
    switch_request = SWITCH_REQUEST
    run_mode = "full"
    if args.smoke:
        verifier_cap = 12
        lm_node_ceiling = 128
        edge_ceiling = 256
        seed_start = 0
        seeds_count = 2
        checkpoints = (3, 4, 8, 12)
        switch_request = 4
        run_mode = "smoke"
    elif args.shard:
        run_mode = "shard"

    if run_mode in {"full", "shard"} and (
        verifier_cap != VERIFIER_CAP
        or lm_node_ceiling != LM_NODE_CEILING
        or edge_ceiling != EDGE_CEILING
    ):
        parser.error("the full/shard verifier and guard limits are fixed")
    if run_mode in {"full", "shard"} and args.diagnostic_seed != 313:
        parser.error("the full/shard diagnostic bootstrap seed is fixed to 313")
    if run_mode == "full" and (
        seed_start != FULL_SEED_START or seeds_count != FULL_SEED_COUNT
    ):
        parser.error("the full cohort is fixed to seeds 640--703")
    if run_mode == "shard" and (
        seed_start < FULL_SEED_START
        or seed_start + seeds_count > FULL_SEED_START + FULL_SEED_COUNT
    ):
        parser.error("shards must be subsets of the fixed seeds 640--703")
    if run_mode == "shard":
        shard_suffix = f"_s{seed_start}-{seed_start + seeds_count - 1}"
        if args.runs_jsonl == default_runs:
            args.runs_jsonl = base.with_name(base.name + shard_suffix + "_runs.jsonl")
        if args.summary_json == default_summary:
            args.summary_json = base.with_name(
                base.name + shard_suffix + "_summary.json"
            )
        if args.report_md == default_report:
            args.report_md = base.with_name(base.name + shard_suffix + "_report.md")

    seed_ids = list(range(seed_start, seed_start + seeds_count))
    expected_keys = set(itertools.product(METHODS, seed_ids))
    reused_records = [
        record for path in args.resume_from for record in _read_jsonl(path)
    ]
    reused_keys = [_record_key(record) for record in reused_records]
    if len(reused_keys) != len(set(reused_keys)):
        parser.error("--resume-from inputs contain duplicate composite keys")
    unexpected = sorted(set(reused_keys) - expected_keys)
    if unexpected:
        parser.error(f"--resume-from contains out-of-design cells: {unexpected[:5]}")
    for record in reused_records:
        if record.get("schema_version") != SCHEMA_VERSION:
            parser.error("--resume-from contains an incompatible schema")
        if record.get("deterministic_digest") != canonical_record_digest(record):
            parser.error("--resume-from contains a deterministic digest mismatch")

    new_records = run_experiment(
        seed_ids=seed_ids,
        verifier_cap=verifier_cap,
        lm_node_ceiling=lm_node_ceiling,
        edge_ceiling=edge_ceiling,
        checkpoints=checkpoints,
        switch_request=switch_request,
        progress_every=args.progress_every,
        skip_keys=set(reused_keys),
    )
    records = reused_records + new_records
    method_order = {method: index for index, method in enumerate(METHODS)}
    records.sort(
        key=lambda row: (
            int(row["seeds"]["exploration_seed"]),
            method_order[str(row["method"]["name"])],
        )
    )
    summary = summarize(
        records,
        seed_ids=seed_ids,
        verifier_cap=verifier_cap,
        lm_node_ceiling=lm_node_ceiling,
        edge_ceiling=edge_ceiling,
        checkpoints=checkpoints,
        switch_request=switch_request,
        diagnostic_seed=args.diagnostic_seed,
        run_mode=run_mode,
    )
    _write_jsonl(args.runs_jsonl, records)
    reloaded_records = _read_jsonl(args.runs_jsonl)
    reloaded_summary = summarize(
        reloaded_records,
        seed_ids=seed_ids,
        verifier_cap=verifier_cap,
        lm_node_ceiling=lm_node_ceiling,
        edge_ceiling=edge_ceiling,
        checkpoints=checkpoints,
        switch_request=switch_request,
        diagnostic_seed=args.diagnostic_seed,
        run_mode=run_mode,
    )
    if reloaded_summary != summary:
        raise AssertionError("disk-reloaded summary differs from in-memory summary")
    _write_json(args.summary_json, reloaded_summary)
    args.report_md.parent.mkdir(parents=True, exist_ok=True)
    args.report_md.write_text(render_report(reloaded_summary), encoding="utf-8")
    print(
        json.dumps(
            {
                "records": len(records),
                "data_quality": reloaded_summary["data_quality"]["status"],
                "disk_revalidation": "PASS",
                "runs_jsonl": str(args.runs_jsonl),
                "summary_json": str(args.summary_json),
                "report_md": str(args.report_md),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
