#!/usr/bin/env python3
"""Fixed-verifier-budget conversion test for Role-Lock D4.

The preceding channel ablation matched logical LM-node evaluations and found
that Sobol routing reached the same node cap with fewer verifier requests and
edge selections.  This experiment reverses the resource constraint: every run
must consume exactly the same 700 verifier requests, while LM nodes and edges
become outcomes.  It asks whether reduced revisitation converts an expensive
verifier budget into more unique search nodes without sacrificing readout
success.

The full design is intentionally fixed:

* Role-Lock D4, posterior SD scale 1.0, pruning disabled;
* ``iid_all``, ``sobol_all``, and ``sobol_routing_only``;
* paired exploration seeds 512--639;
* hard verifier cap 700;
* LM-node ceiling 1111 and edge ceiling 3500 as guards only.

Every full run is invalid unless it stops on the verifier cap exactly.  The
ceilings are not matched budgets and must retain positive headroom.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
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
    RoleLockLM,
    RoleLockTask,
    RoleLockTokenizer,
    SeedPlan,
    VariantSpec,
    _search_diagnostics,
    benchmark_config,
)
from qmc_bmgs.records import canonical_record_digest


SCHEMA_VERSION = "qmc-bmgs-fixed-verifier/v1"
METHODS = ("iid_all", "sobol_all", "sobol_routing_only")
POSTERIOR_SD_SCALE = 1.0
VERIFIER_CAP = 700
LM_NODE_CEILING = 1111
EDGE_CEILING = 3500
REACHABLE_PREFIX_BOUND = sum(9**level for level in range(4))
FULL_SEED_START = 512
FULL_SEED_COUNT = 128
BOOTSTRAP_SAMPLES = 5_000


def _variant_map() -> dict[str, VariantSpec]:
    available = {variant.name: variant for variant in CHANNEL_ABLATION_VARIANTS}
    variants = {name: available[name] for name in METHODS}
    if tuple(variants) != METHODS or len(variants) != 3:
        raise AssertionError("fixed-verifier method order must remain stable")
    return variants


def _correct_prefix_length(readout: Sequence[int], target: Sequence[int]) -> int:
    result = 0
    for observed, expected in zip(readout, target):
        if int(observed) != int(expected):
            break
        result += 1
    return result


def _run_variant(
    *,
    task: RoleLockTask,
    variant: VariantSpec,
    seeds: SeedPlan,
    registry: CandidateRegistry,
    verifier_cap: int,
    lm_node_ceiling: int,
    edge_ceiling: int,
) -> dict[str, Any]:
    if min(verifier_cap, lm_node_ceiling, edge_ceiling) < 1:
        raise ValueError("all budget limits must be positive")
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

    started = time.perf_counter()
    stop_reason = policy.run_to_fixed_verifier_budget(
        task.root,
        verifier_budget=verifier_cap,
        lm_node_ceiling=lm_node_ceiling,
        edge_ceiling=edge_ceiling,
    )
    wall_time = time.perf_counter() - started

    readout = policy.best_continuation(task.root, max_new_tokens=task.depth)
    policy.counters.evaluation_only_calls += 1
    readout_success = task.is_success(readout)
    counters = asdict(policy.counters)
    lm_used = int(policy.counters.logical_lm_node_evals)
    verifier_used = int(policy.counters.verifier_requests)
    edges_used = int(policy.counters.edge_selections)
    prefix_length = _correct_prefix_length(readout, task.target)
    if variant.uniform_sources is None:
        raise AssertionError("fixed-verifier profiles require coordinate sources")

    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "record_type": "fixed_verifier_run",
        "paired_group_id": (
            f"{task.task_id}:sd{POSTERIOR_SD_SCALE:g}:"
            f"seed{seeds.exploration_seed}:v{verifier_cap}"
        ),
        "experiment": {
            "name": "role_lock_d4_fixed_verifier_conversion",
            "question": (
                "does lower revisit work convert a fixed verifier budget into "
                "more unique LM nodes without sacrificing readout success"
            ),
            "fixed_task": "role_lock_d4",
            "fixed_strata": "aligned_static_token_embedding",
            "fixed_pruning": False,
            "fixed_posterior_sd_scale": POSTERIOR_SD_SCALE,
        },
        "method": {
            "name": variant.name,
            "sampler": variant.sampler,
            "strata": variant.strata,
            "pruning": variant.pruning,
            "readout": "return_mean_then_visits_then_prior",
            "lm_prior_role": "behavior_only",
            "runtime_scope": "all profiles pay matched dual-source instrumentation",
            "posterior_sd_scale": POSTERIOR_SD_SCALE,
            "sampler_layout": "matched_full_dimension_column_mux/v1",
            "uniform_sources": variant.uniform_sources.as_dict(),
            "channel_coordinates": {
                "coverage_gate": [0],
                "cluster_quantile": [1],
                "action_perturbation_start": 2,
            },
        },
        "uncertainty_profile": {
            "posterior_sd_scale": POSTERIOR_SD_SCALE,
            "posterior_claim": "nonstationary proxy, not an exact posterior",
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
            "limit": int(verifier_cap),
            "verifier_limit": int(verifier_cap),
            "lm_node_ceiling": int(lm_node_ceiling),
            "lm_node_ceiling_kind": (
                "conservative_integrity_guard_not_reachable_saturation"
            ),
            "reachable_nonterminal_prefix_bound": REACHABLE_PREFIX_BOUND,
            "edge_ceiling": int(edge_ceiling),
            "regime": "verifier_primary_with_lm_and_edge_guards",
            "task_max_unique_prefix_nodes": task.max_unique_prefix_nodes,
            "stop_reason": stop_reason,
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
            "first_success_verifier_request": (policy.first_success_verifier_request),
            "blocked_verifier_calls": policy.blocked_verifier_calls,
            "wall_time_s": wall_time,
        },
        "outcome": {
            "readout_token_ids": readout,
            "readout_text": tokenizer.decode(readout),
            "readout_success": readout_success,
            "readout_return": task.reward if readout_success else 0.0,
            "readout_correct_prefix_length": prefix_length,
            "readout_failure_stage": (None if readout_success else prefix_length),
            "best_observed_success": policy.counters.best_observed_return > 0.0,
            "best_observed_return": policy.counters.best_observed_return,
        },
        "partition": {
            "singletons": list(policy._partition_singletons),
            "target_overlap": 0,
            "mean_mass_l1": None,
            "mean_changed_fraction": None,
        },
        "search": {
            **_search_diagnostics(policy, task),
            "prune_log": policy.prune_log,
        },
        "randomization": {
            "independent_unit": "exploration_seed",
            "node_stream_seeded_from": "exploration_seed_and_exact_prefix",
            "source_architecture": "matched_full_dimension_column_mux",
            "sobol_scramble": True,
            "iid_seed_transform": "node_seed XOR 0x1D1D1D",
            "both_sources_advanced_every_draw": True,
            "common_random_numbers": {
                "across_profiles_for_unchanged_coordinates": True,
                "scope": "same exact prefix, exploration seed, and node draw index",
            },
            "cost_scope": (
                "dual-source generation is matched instrumentation, not a "
                "deployment-time sampler-cost estimate"
            ),
        },
        "evaluation_scope": {
            "search_verifier_feedback_calls": verifier_used,
            "post_search_readout_evaluations": 1,
            "post_search_readout_is_outside_verifier_budget": True,
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
                )
            )
            if progress_every and len(records) % progress_every == 0:
                print(f"completed {len(records)}/{total}", flush=True)
    return records


def _record_key(record: dict[str, Any]) -> tuple[str, int]:
    return (
        str(record["method"]["name"]),
        int(record["seeds"]["exploration_seed"]),
    )


def _validate_records(
    records: Sequence[dict[str, Any]],
    *,
    seed_ids: Sequence[int],
    verifier_cap: int,
    lm_node_ceiling: int,
    edge_ceiling: int,
) -> dict[str, Any]:
    variants = _variant_map()
    expected = set(itertools.product(METHODS, [int(seed) for seed in seed_ids]))
    keys = [_record_key(record) for record in records]
    actual = set(keys)
    duplicate_count = len(keys) - len(actual)
    errors: dict[str, int] = defaultdict(int)
    paired_groups: dict[str, list[tuple[str, int]]] = defaultdict(list)
    fingerprints: dict[int, set[str]] = defaultdict(set)
    all_fingerprints: set[str] = set()
    target = [2, 3, 4, 1]

    for record in records:
        method, seed = _record_key(record)
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
        if (
            method_record.get("uniform_sources") != variant.uniform_sources.as_dict()
            or method_record.get("sampler") != variant.sampler
            or method_record.get("strata") != "embedding"
            or method_record.get("pruning") is not False
            or method_record.get("sampler_layout")
            != "matched_full_dimension_column_mux/v1"
            or float(method_record.get("posterior_sd_scale", -1.0))
            != POSTERIOR_SD_SCALE
        ):
            errors["source_contract"] += 1

        task_record = record["task"]
        outcome = record["outcome"]
        readout = [int(value) for value in outcome["readout_token_ids"]]
        exact_success = readout == target
        correct_prefix = _correct_prefix_length(readout, target)
        if (
            task_record.get("id") != "role_lock_d4"
            or int(task_record.get("depth", -1)) != 4
            or list(task_record.get("target", [])) != target
            or task_record.get("terminal_only") is not True
            or not isinstance(outcome.get("readout_success"), bool)
            or outcome.get("readout_success") != exact_success
            or float(outcome.get("readout_return", -1.0))
            != (5.0 if exact_success else 0.0)
            or int(outcome.get("readout_correct_prefix_length", -1)) != correct_prefix
            or outcome.get("readout_failure_stage")
            != (None if exact_success else correct_prefix)
        ):
            errors["task_and_success_encoding"] += 1

        budget = record["budget"]
        usage = record["usage"]
        verifier_used = int(usage["verifier_requests"])
        lm_used = int(usage["logical_lm_node_evals"])
        edges_used = int(usage["edge_selections"])
        if (
            budget.get("primary") != "verifier_requests"
            or int(budget.get("limit", -1)) != verifier_cap
            or int(budget.get("verifier_limit", -1)) != verifier_cap
            or int(budget.get("lm_node_ceiling", -1)) != lm_node_ceiling
            or budget.get("lm_node_ceiling_kind")
            != "conservative_integrity_guard_not_reachable_saturation"
            or int(budget.get("reachable_nonterminal_prefix_bound", -1))
            != REACHABLE_PREFIX_BOUND
            or int(budget.get("edge_ceiling", -1)) != edge_ceiling
            or budget.get("stop_reason") != "verifier_budget"
            or budget.get("exact_primary_cap_reached") is not True
            or int(budget.get("verifier_overshoot", -1)) != 0
            or int(budget.get("lm_node_overshoot", -1)) != 0
            or int(budget.get("edge_overshoot", -1)) != 0
            or verifier_used != verifier_cap
            or lm_used >= lm_node_ceiling
            or lm_used > REACHABLE_PREFIX_BOUND
            or edges_used >= edge_ceiling
            or edges_used > 4 * verifier_used
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
            or int(record["search"]["nodes_created"]) != lm_used
            or int(usage["budget_leaf_backups"]) != 0
            or int(usage["cache_hits"]) + int(record["search"]["nodes_created"])
            != edges_used
            or not (lm_used <= int(usage["full_prefix_tokens"]) <= 4 * lm_used)
        ):
            errors["usage_accounting"] += 1

        first_verifier = usage.get("first_success_verifier_request")
        first_lm = usage.get("first_success_lm_eval")
        best_success = bool(outcome.get("best_observed_success"))
        valid_first_verifier = first_verifier is None or (
            1 <= int(first_verifier) <= verifier_cap
        )
        valid_first_lm = first_lm is None or 1 <= int(first_lm) <= lm_used
        if (
            not valid_first_verifier
            or not valid_first_lm
            or (first_verifier is None) == best_success
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
        if (
            record.get("search_config") != expected_config
            or record.get("seeds") != expected_seeds
            or record.get("experiment", {}).get("fixed_pruning") is not False
            or float(record.get("experiment", {}).get("fixed_posterior_sd_scale", -1.0))
            != POSTERIOR_SD_SCALE
        ):
            errors["config_propagation"] += 1

        search = record["search"]
        fingerprint = search.get("root_candidate_fingerprint")
        if (
            fingerprint is None
            or int(usage["candidate_misses"]) != 0
            or search.get("oracle_candidate_universe_guaranteed") is not True
        ):
            errors["candidate_contract"] += 1
        else:
            fingerprints[seed].add(str(fingerprint))
            all_fingerprints.add(str(fingerprint))

        source_usage = search.get("uniform_source_usage", {})
        selected_total = int(source_usage.get("total_selected_scalar_values", -1))
        selected_sobol = int(source_usage.get("selected_sobol_scalar_values", -1))
        selected_iid = int(source_usage.get("selected_iid_scalar_values", -1))
        sobol_columns = (
            int(variant.uniform_sources.coverage_gate == "sobol")
            + int(variant.uniform_sources.cluster_quantile == "sobol")
            + 10 * int(variant.uniform_sources.action_perturbation == "sobol")
        )
        if (
            source_usage.get("selection_points") != edges_used
            or source_usage.get("sobol_full_points_generated") != edges_used
            or source_usage.get("iid_full_points_generated") != edges_used
            or source_usage.get("mux_nodes_created") != search.get("nodes_created")
            or selected_total != 12 * edges_used
            or selected_sobol != sobol_columns * edges_used
            or selected_iid != selected_total - selected_sobol
            or int(usage["coverage_route_selections"])
            + int(usage["global_route_selections"])
            != edges_used
        ):
            errors["uniform_draw_accounting"] += 1

        randomization = record.get("randomization", {})
        if (
            randomization.get("source_architecture")
            != "matched_full_dimension_column_mux"
            or randomization.get("both_sources_advanced_every_draw") is not True
            or randomization.get("sobol_scramble") is not True
        ):
            errors["randomization_metadata"] += 1
        evaluation_scope = record.get("evaluation_scope", {})
        if (
            int(evaluation_scope.get("search_verifier_feedback_calls", -1))
            != verifier_used
            or int(evaluation_scope.get("post_search_readout_evaluations", -1)) != 1
            or evaluation_scope.get("post_search_readout_is_outside_verifier_budget")
            is not True
        ):
            errors["evaluation_scope"] += 1

        expected_group = (
            f"role_lock_d4:sd{POSTERIOR_SD_SCALE:g}:seed{seed}:v{verifier_cap}"
        )
        group = str(record.get("paired_group_id"))
        if group != expected_group:
            errors["paired_group"] += 1
        paired_groups[group].append((method, seed))

    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    group_errors = sum(
        len(group_keys) != len(METHODS)
        or {key[0] for key in group_keys} != set(METHODS)
        or len({key[1] for key in group_keys}) != 1
        for group_keys in paired_groups.values()
    )
    if group_errors or len(paired_groups) != len(seed_ids):
        errors["paired_group"] += group_errors + abs(len(paired_groups) - len(seed_ids))
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
        "exact_verifier_caps_and_positive_guard_headroom": (
            errors["budget_contract"] == 0
        ),
        "usage_accounting": errors["usage_accounting"] == 0,
        "first_success_index_valid": errors["first_success"] == 0,
        "pruning_disabled": errors["pruning"] == 0,
        "source_and_config_propagated": errors["source_contract"] == 0
        and errors["config_propagation"] == 0
        and errors["randomization_metadata"] == 0
        and errors["evaluation_scope"] == 0,
        "candidate_manifest_identical": errors["candidate_contract"] == 0,
        "uniform_draw_accounting": errors["uniform_draw_accounting"] == 0,
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
            "paired_groups": len(paired_groups),
            "root_fingerprints": sorted(all_fingerprints),
            "error_counts": dict(errors),
            "minimum_lm_guard_headroom": min(
                (
                    int(record["budget"]["guard_headroom"]["lm_nodes"])
                    for record in records
                ),
                default=0,
            ),
            "minimum_edge_guard_headroom": min(
                (
                    int(record["budget"]["guard_headroom"]["edges"])
                    for record in records
                ),
                default=0,
            ),
        },
    }


def _wilson_interval(successes: int, count: int) -> list[float]:
    if count < 1:
        return [0.0, 0.0]
    z = 1.959963984540054
    p = successes / count
    denominator = 1.0 + z * z / count
    center = (p + z * z / (2.0 * count)) / denominator
    radius = (
        z
        * math.sqrt(p * (1.0 - p) / count + z * z / (4.0 * count * count))
        / denominator
    )
    return [max(0.0, center - radius), min(1.0, center + radius)]


def _bootstrap_mean_interval(values: Sequence[float], seed: int) -> list[float]:
    if not values:
        return [0.0, 0.0]
    if len(values) == 1:
        return [float(values[0]), float(values[0])]
    tensor = torch.tensor(values, dtype=torch.float64)
    generator = torch.Generator().manual_seed(int(seed))
    indices = torch.randint(
        len(tensor),
        (BOOTSTRAP_SAMPLES, len(tensor)),
        generator=generator,
    )
    means = tensor[indices].mean(dim=1).sort().values
    low = float(means[int(0.025 * (BOOTSTRAP_SAMPLES - 1))].item())
    high = float(means[int(0.975 * (BOOTSTRAP_SAMPLES - 1))].item())
    return [low, high]


def _exact_mcnemar_p(candidate_only: int, reference_only: int) -> float:
    discordant = candidate_only + reference_only
    if discordant == 0:
        return 1.0
    tail = min(candidate_only, reference_only)
    probability = sum(math.comb(discordant, k) for k in range(tail + 1))
    return min(1.0, 2.0 * probability / (2**discordant))


def _holm_adjust(rows: list[dict[str, Any]]) -> None:
    order = sorted(range(len(rows)), key=lambda index: rows[index]["mcnemar_p"])
    running = 0.0
    total = len(order)
    for rank, index in enumerate(order):
        adjusted = min(1.0, (total - rank) * rows[index]["mcnemar_p"])
        running = max(running, adjusted)
        rows[index]["holm_adjusted_p"] = running


def _cell_summary(rows: Sequence[dict[str, Any]], verifier_cap: int) -> dict[str, Any]:
    successes = sum(bool(row["outcome"]["readout_success"]) for row in rows)
    observed = sum(bool(row["outcome"]["best_observed_success"]) for row in rows)
    hit_indices = [
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
    usage_fields = (
        "logical_lm_node_evals",
        "full_prefix_tokens",
        "verifier_requests",
        "edge_selections",
    )
    return {
        "replicates": len(rows),
        "readout_success_count": successes,
        "readout_success_rate": successes / len(rows),
        "readout_success_wilson_95": _wilson_interval(successes, len(rows)),
        "best_observed_success_count": observed,
        "best_observed_success_rate": observed / len(rows),
        "first_success_observed_count": len(hit_indices),
        "first_success_censored_count": len(rows) - len(hit_indices),
        "mean_first_success_verifier_request_among_hits": (
            statistics.fmean(hit_indices) if hit_indices else None
        ),
        "mean_restricted_first_success_index": statistics.fmean(restricted_hits),
        "restricted_first_success_definition": (
            "request index for observed hits; verifier_cap + 1 for censored runs"
        ),
        "mean_usage": {
            field: statistics.fmean(float(row["usage"][field]) for row in rows)
            for field in usage_fields
        },
        "mean_nodes_created": statistics.fmean(
            float(row["search"]["nodes_created"]) for row in rows
        ),
        "mean_root_coverage_max_uniform_deviation": statistics.fmean(
            float(row["search"]["root_coverage_max_uniform_deviation"]) for row in rows
        ),
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
    cost_fields = (
        "logical_lm_node_evals",
        "full_prefix_tokens",
        "edge_selections",
    )
    cost_deltas: dict[str, list[float]] = {field: [] for field in cost_fields}

    for block in blocks.values():
        candidate_record = block[candidate]
        reference_record = block[reference]
        candidate_success = int(candidate_record["outcome"]["readout_success"])
        reference_success = int(reference_record["outcome"]["readout_success"])
        success_deltas.append(float(candidate_success - reference_success))
        candidate_only += int(candidate_success == 1 and reference_success == 0)
        reference_only += int(candidate_success == 0 and reference_success == 1)
        both_success += int(candidate_success == 1 and reference_success == 1)
        both_failure += int(candidate_success == 0 and reference_success == 0)
        best_deltas.append(
            float(
                int(candidate_record["outcome"]["best_observed_success"])
                - int(reference_record["outcome"]["best_observed_success"])
            )
        )
        candidate_hit = candidate_record["usage"]["first_success_verifier_request"]
        reference_hit = reference_record["usage"]["first_success_verifier_request"]
        first_hit_deltas.append(
            float(
                (candidate_hit if candidate_hit is not None else verifier_cap + 1)
                - (reference_hit if reference_hit is not None else verifier_cap + 1)
            )
        )
        for field in cost_fields:
            cost_deltas[field].append(
                float(
                    candidate_record["usage"][field] - reference_record["usage"][field]
                )
            )

    return {
        "label": label,
        "role": role,
        "candidate": candidate,
        "reference": reference,
        "paired_blocks": len(success_deltas),
        "mean_success_delta": statistics.fmean(success_deltas),
        "paired_bootstrap_success_95": _bootstrap_mean_interval(
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
        "paired_bootstrap_best_observed_95": _bootstrap_mean_interval(
            best_deltas, bootstrap_seed + 1
        ),
        "mean_restricted_first_success_index_delta": statistics.fmean(first_hit_deltas),
        "paired_bootstrap_restricted_first_success_95": (
            _bootstrap_mean_interval(first_hit_deltas, bootstrap_seed + 2)
        ),
        "mean_resource_delta": {
            field: {
                "mean": statistics.fmean(values),
                "paired_bootstrap_95": _bootstrap_mean_interval(
                    values, bootstrap_seed + 100 + index
                ),
            }
            for index, (field, values) in enumerate(cost_deltas.items())
        },
    }


def _add_simultaneous_primary_intervals(
    comparisons: Sequence[dict[str, Any]],
    blocks: dict[int, dict[str, dict[str, Any]]],
    bootstrap_seed: int,
) -> str:
    """Attach joint seed-block intervals to the two IID-referenced contrasts."""
    labels = ("combined_sobol_vs_iid", "sobol_routing_only_vs_iid")
    by_label = {row["label"]: row for row in comparisons}
    matrix = torch.tensor(
        [
            [
                float(block["sobol_all"]["outcome"]["readout_success"])
                - float(block["iid_all"]["outcome"]["readout_success"]),
                float(block["sobol_routing_only"]["outcome"]["readout_success"])
                - float(block["iid_all"]["outcome"]["readout_success"]),
            ]
            for block in blocks.values()
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
        "paired exploration-seed bootstrap; 95th percentile of maximum "
        "absolute deviation across the two IID-referenced risk differences"
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
    diagnostic_seed: int = 313,
    run_mode: str = "analysis",
) -> dict[str, Any]:
    quality = _validate_records(
        records,
        seed_ids=seed_ids,
        verifier_cap=verifier_cap,
        lm_node_ceiling=lm_node_ceiling,
        edge_ceiling=edge_ceiling,
    )
    if quality["status"] != "PASS":
        raise ValueError(f"invalid fixed-verifier records: {quality['failures']}")

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    blocks: dict[int, dict[str, dict[str, Any]]] = defaultdict(dict)
    for record in records:
        method, seed = _record_key(record)
        grouped[method].append(record)
        blocks[seed][method] = record

    cells = [
        {
            "method": method,
            **_cell_summary(grouped[method], verifier_cap),
        }
        for method in METHODS
    ]
    planned = (
        ("sobol_all", "iid_all", "combined_sobol_vs_iid", "primary"),
        (
            "sobol_routing_only",
            "iid_all",
            "sobol_routing_only_vs_iid",
            "primary",
        ),
        (
            "sobol_all",
            "sobol_routing_only",
            "combined_sobol_vs_routing_only",
            "secondary_mechanism",
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
        comparisons, blocks, diagnostic_seed + 20_000
    )
    primary_combined = comparisons[0]
    primary_routing = comparisons[1]
    seed_set = set(int(seed) for seed in seed_ids)
    prior_overlap = len(seed_set & set(range(FULL_SEED_START)))
    return {
        "schema_version": SCHEMA_VERSION,
        "record_type": "fixed_verifier_summary",
        "design": {
            "run_mode": run_mode,
            "task": "role_lock_d4",
            "methods": list(METHODS),
            "posterior_sd_scale": POSTERIOR_SD_SCALE,
            "verifier_cap": verifier_cap,
            "lm_node_ceiling": lm_node_ceiling,
            "edge_ceiling": edge_ceiling,
            "exploration_seed_ids": [int(seed) for seed in seed_ids],
            "independent_randomization_unit": "exploration_seed",
            "matched_primary_budget": "verifier_requests",
            "primary_contrasts": [
                "sobol_all_minus_iid_all",
                "sobol_routing_only_minus_iid_all",
            ],
            "primary_outcome": "readout_success_at_exact_verifier_cap",
            "engineering_conversion_outcome": "logical_lm_node_evals",
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
                "verifier_cap": verifier_cap,
                "outcome": "readout_success",
                "mean_delta": row["mean_success_delta"],
                "paired_bootstrap_95_simultaneous": row[
                    "paired_bootstrap_success_95_simultaneous"
                ],
                "exact_mcnemar_p": row["mcnemar_p"],
                "holm_adjusted_p_primary_family": row["holm_adjusted_p"],
            }
            for row in (primary_combined, primary_routing)
        ],
        "simultaneous_interval_method": simultaneous_method,
        "engineering_decision": {
            "verifier_cap": verifier_cap,
            "profiles": {
                row["candidate"]: {
                    "success_direction": _interval_direction(
                        row["paired_bootstrap_success_95_simultaneous"]
                    ),
                    "lm_node_conversion_direction": _interval_direction(
                        row["mean_resource_delta"]["logical_lm_node_evals"][
                            "paired_bootstrap_95"
                        ]
                    ),
                }
                for row in (primary_combined, primary_routing)
            },
            "claim_rule": (
                "call resource conversion positive only when the paired LM-node "
                "interval is above zero; do not call success superiority unless "
                "the paired success interval is above zero"
            ),
        },
        "limitations": [
            "This is an oracle-aligned static-token Role-Lock toy task.",
            "The LM and edge ceilings are guards, not matched resource budgets.",
            "Dual-source wall time is instrumentation cost, not deployment cost.",
            "The restricted first-hit metric encodes censored runs as cap + 1.",
            (
                "The matched budget covers 700 search verifier feedback calls; "
                "one deterministic post-search readout evaluation is outside it."
            ),
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
        "# QMC-BMGS fixed-verifier conversion test",
        "",
        "## Outcome",
        "",
        (
            f"Role-Lock D4, SD scale {design['posterior_sd_scale']:g}, exact "
            f"verifier cap {design['verifier_cap']}, paired "
            f"n={len(design['exploration_seed_ids'])}."
        ),
        "",
        "| Method | Readout success | LM nodes | Prefix tokens | Edges | Best hit |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for method in METHODS:
        cell = cells[method]
        lines.append(
            f"| `{method}` | {_percent(cell['readout_success_rate'])} "
            f"({cell['readout_success_count']}/{cell['replicates']}) | "
            f"{cell['mean_usage']['logical_lm_node_evals']:.1f} | "
            f"{cell['mean_usage']['full_prefix_tokens']:.1f} | "
            f"{cell['mean_usage']['edge_selections']:.1f} | "
            f"{_percent(cell['best_observed_success_rate'])} |"
        )
    lines.extend(
        [
            "",
            "## Paired contrasts",
            "",
            (
                "Resource deltas are candidate minus reference. Positive LM-node "
                "delta means more unique search nodes at the same verifier cap."
            ),
            "",
            (
                "| Contrast | Role | Success delta | Simultaneous 95% | "
                "Holm p | LM-node delta | Edge delta |"
            ),
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in summary["planned_pairwise_contrasts"]:
        simultaneous = row.get("paired_bootstrap_success_95_simultaneous")
        interval_text = (
            f"[{_pp(simultaneous[0])}, {_pp(simultaneous[1])}]"
            if simultaneous is not None
            else "nominal only"
        )
        holm = row.get("holm_adjusted_p")
        holm_text = f"{holm:.4g}" if holm is not None else "not in family"
        lines.append(
            f"| `{row['label']}` | {row['role']} | "
            f"{_pp(row['mean_success_delta'])} | "
            f"{interval_text} | {holm_text} | "
            f"{row['mean_resource_delta']['logical_lm_node_evals']['mean']:+.1f} | "
            f"{row['mean_resource_delta']['edge_selections']['mean']:+.1f} |"
        )
    decision = summary["engineering_decision"]
    quality = summary["data_quality"]
    lines.extend(
        [
            "",
            "## Decision boundary",
            "",
            *[
                (
                    f"- `{method}` vs IID: success "
                    f"`{profile['success_direction']}`, LM-node conversion "
                    f"`{profile['lm_node_conversion_direction']}`."
                )
                for method, profile in decision["profiles"].items()
            ],
            "- Success superiority and resource conversion are separate claims.",
            "- No natural-language or general QMC claim follows from this toy.",
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
            "## Reproduce",
            "",
            "```bash",
            "python -m qmc_bmgs.experiments.fixed_verifier_budget",
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


def _self_test() -> None:
    seed_ids = [0, 1]
    verifier_cap = 12
    lm_ceiling = 128
    edge_ceiling = 256
    records = run_experiment(
        seed_ids=seed_ids,
        verifier_cap=verifier_cap,
        lm_node_ceiling=lm_ceiling,
        edge_ceiling=edge_ceiling,
    )
    repeat = run_experiment(
        seed_ids=seed_ids,
        verifier_cap=verifier_cap,
        lm_node_ceiling=lm_ceiling,
        edge_ceiling=edge_ceiling,
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
        run_mode="self_test",
    )
    assert len(records) == 6
    assert summary["data_quality"]["status"] == "PASS"
    assert len(summary["planned_pairwise_contrasts"]) == 3
    assert "fixed-verifier conversion" in render_report(summary)

    cap_one = run_experiment(
        seed_ids=[2],
        verifier_cap=1,
        lm_node_ceiling=16,
        edge_ceiling=16,
    )
    assert all(row["budget"]["stop_reason"] == "verifier_budget" for row in cap_one)
    assert all(row["usage"]["verifier_requests"] == 1 for row in cap_one)
    assert all(row["usage"]["blocked_verifier_calls"] == 0 for row in cap_one)

    task = RoleLockTask(4)
    variant = _variant_map()["iid_all"]
    seeds = SeedPlan(task_seed=4, exploration_seed=3, partition_seed=10_000)
    lm_guard = _run_variant(
        task=task,
        variant=variant,
        seeds=seeds,
        registry=CandidateRegistry(),
        verifier_cap=10,
        lm_node_ceiling=1,
        edge_ceiling=100,
    )
    assert lm_guard["budget"]["stop_reason"] == "lm_integrity_ceiling_frontier"
    edge_guard = _run_variant(
        task=task,
        variant=variant,
        seeds=seeds,
        registry=CandidateRegistry(),
        verifier_cap=10,
        lm_node_ceiling=100,
        edge_ceiling=2,
    )
    assert edge_guard["budget"]["stop_reason"] == "edge_integrity_ceiling"

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
        )
        assert quality["status"] == "FAIL"

    assert_mutation_fails(
        lambda rows: rows[0]["usage"].__setitem__("verifier_requests", 11)
    )
    assert_mutation_fails(
        lambda rows: rows[0]["budget"].__setitem__("stop_reason", "edge_budget")
    )
    assert_mutation_fails(
        lambda rows: rows[0]["usage"].__setitem__("logical_lm_node_evals", 128)
    )
    assert_mutation_fails(
        lambda rows: rows[0]["usage"].__setitem__("edge_selections", 256)
    )
    assert_mutation_fails(
        lambda rows: rows[0]["usage"].__setitem__("first_success_verifier_request", 13)
    )
    assert_mutation_fails(lambda rows: rows[0]["usage"].__setitem__("arms_pruned", 1))
    assert_mutation_fails(
        lambda rows: rows[0]["search"].__setitem__("root_candidate_fingerprint", None)
    )
    assert_mutation_fails(
        lambda rows: rows[0]["outcome"].__setitem__(
            "readout_success", not rows[0]["outcome"]["readout_success"]
        )
    )
    assert_mutation_fails(lambda rows: rows[0]["task"].__setitem__("id", "wrong"))
    assert_mutation_fails(
        lambda rows: rows[0]["search_config"].__setitem__("seed", 999)
    )
    assert_mutation_fails(
        lambda rows: rows[0]["seeds"].__setitem__("candidate_seed", 999)
    )
    assert_mutation_fails(lambda rows: rows[0].__setitem__("paired_group_id", "wrong"))
    assert_mutation_fails(
        lambda rows: rows[0]["method"]["uniform_sources"].__setitem__(
            "coverage_gate",
            "iid" if rows[0]["method"]["name"] != "iid_all" else "sobol",
        )
    )
    json.dumps(summary, allow_nan=False)
    print("fixed verifier self-test: PASS")


def main() -> None:
    base = Path.cwd() / "artifacts" / "work" / "qmc_bmgs_fixed_verifier"
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
    parser.add_argument("--progress-every", type=int, default=64)
    parser.add_argument(
        "--resume-from",
        type=Path,
        action="append",
        default=[],
        help="Reuse digest-valid matching JSONL shards and run only missing cells",
    )
    parser.add_argument(
        "--runs-jsonl", type=Path, default=base.with_name(base.name + "_runs.jsonl")
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=base.with_name(base.name + "_summary.json"),
    )
    parser.add_argument(
        "--report-md", type=Path, default=base.with_name(base.name + "_report.md")
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
    run_mode = "full"
    if args.smoke:
        verifier_cap = 32
        lm_node_ceiling = 256
        edge_ceiling = 512
        seed_start = 0
        seeds_count = 2
        run_mode = "smoke"
    elif args.shard:
        run_mode = "shard"

    if run_mode in {"full", "shard"} and (
        verifier_cap != VERIFIER_CAP
        or lm_node_ceiling != LM_NODE_CEILING
        or edge_ceiling != EDGE_CEILING
    ):
        parser.error("the full/shard verifier and guard limits are fixed")
    if run_mode == "full" and (
        seed_start != FULL_SEED_START or seeds_count != FULL_SEED_COUNT
    ):
        parser.error("the full cohort is fixed to seeds 512--639")
    if run_mode == "shard" and (
        seed_start < FULL_SEED_START
        or seed_start + seeds_count > FULL_SEED_START + FULL_SEED_COUNT
    ):
        parser.error("shards must be subsets of the fixed seeds 512--639")

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
        progress_every=args.progress_every,
        skip_keys=set(reused_keys),
    )
    records = reused_records + new_records
    summary = summarize(
        records,
        seed_ids=seed_ids,
        verifier_cap=verifier_cap,
        lm_node_ceiling=lm_node_ceiling,
        edge_ceiling=edge_ceiling,
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
