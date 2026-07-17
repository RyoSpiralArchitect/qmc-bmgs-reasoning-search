#!/usr/bin/env python3
"""Matched uniform-channel ablation for the Role-Lock D4 task.

This experiment localizes the earlier combined IID-versus-Sobol result with a
paired 2x2 design.  Coverage-gate and cluster-quantile coordinates form the
``routing`` factor; posterior action perturbations form the ``action`` factor.

The four profiles are:

    iid_all
    sobol_all
    sobol_routing_only
    sobol_action_only

Every profile advances matched full-dimensional IID and scrambled-Sobol points
on every selection.  A coordinate mux chooses which point supplies routing and
action columns.  The two pure endpoints therefore replay the historical joint
engines, while unchanged hybrid channels receive intentional common random
numbers.  Dual-source wall time is instrumentation cost, not deployment cost.

Examples
--------

    python -m qmc_bmgs.experiments.channel_ablation --self-test
    python -m qmc_bmgs.experiments.channel_ablation --smoke
    python -m qmc_bmgs.experiments.channel_ablation
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import statistics
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable, Sequence

import torch

from qmc_bmgs.benchmarks.role_lock import (
    CHANNEL_ABLATION_VARIANTS,
    CandidateRegistry,
    RoleLockTask,
    SeedPlan,
    VariantSpec,
    benchmark_config,
    run_policy_variant,
)
from qmc_bmgs.records import canonical_record_digest


SCHEMA_VERSION = "qmc-bmgs-channel-ablation/v1"
METHODS = tuple(variant.name for variant in CHANNEL_ABLATION_VARIANTS)
PRIMARY_SCALE = 1.0
PRIMARY_BUDGET = 384
BOOTSTRAP_SAMPLES = 5_000


def _variant_map() -> dict[str, VariantSpec]:
    variants = {variant.name: variant for variant in CHANNEL_ABLATION_VARIANTS}
    if tuple(variants) != METHODS or len(variants) != 4:
        raise AssertionError("channel profile names must be unique and stable")
    return variants


def _decorate_record(record: dict[str, Any]) -> dict[str, Any]:
    record.pop("deterministic_digest", None)
    scale = float(record["method"]["posterior_sd_scale"])
    budget = int(record["budget"]["limit"])
    seed = int(record["seeds"]["exploration_seed"])
    target = [int(value) for value in record["task"]["target"]]
    readout = [int(value) for value in record["outcome"]["readout_token_ids"]]
    correct_prefix_length = 0
    for observed, expected in zip(readout, target):
        if observed != expected:
            break
        correct_prefix_length += 1
    record["schema_version"] = SCHEMA_VERSION
    record["record_type"] = "channel_ablation_run"
    record["experiment"] = {
        "name": "role_lock_d4_uniform_channel_ablation",
        "fixed_task": "role_lock_d4",
        "fixed_strata": "aligned_static_token_embedding",
        "fixed_pruning": False,
        "factorization": {
            "routing": ["coverage_gate", "cluster_quantile"],
            "action": ["action_perturbation"],
        },
    }
    record["uncertainty_profile"] = {
        "posterior_sd_scale": scale,
        "implementation": (
            "multiply the benchmark uncertainty-proxy variance by scale^2; "
            "learned returns and candidates remain fixed"
        ),
        "posterior_claim": "nonstationary proxy, not an exact posterior",
    }
    record["paired_group_id"] = f"role_lock_d4:sd{scale:g}:seed{seed}:b{budget}"
    record["outcome"]["readout_correct_prefix_length"] = correct_prefix_length
    record["outcome"]["readout_failure_stage"] = (
        None if correct_prefix_length == len(target) else correct_prefix_length
    )
    record["deterministic_digest"] = canonical_record_digest(record)
    json.dumps(record, allow_nan=False)
    return record


def run_ablation(
    *,
    sd_scales: Sequence[float],
    budgets: Sequence[int],
    seed_start: int,
    seeds_count: int,
    verifier_budget_multiplier: float = 16.0,
    progress_every: int = 0,
    skip_keys: set[tuple[float, str, int, int]] | None = None,
) -> list[dict[str, Any]]:
    if seed_start < 0 or seeds_count < 1:
        raise ValueError("seed_start must be nonnegative and seeds_count positive")
    if verifier_budget_multiplier != 16.0:
        raise ValueError("the fixed channel-ablation verifier multiplier is 16")
    variants = _variant_map()
    task = RoleLockTask(4)
    registry = CandidateRegistry()
    records: list[dict[str, Any]] = []
    skip = skip_keys or set()
    total = len(sd_scales) * len(budgets) * seeds_count * len(variants) - len(skip)

    for scale, budget, exploration_seed in itertools.product(
        sd_scales,
        budgets,
        range(seed_start, seed_start + seeds_count),
    ):
        for method in METHODS:
            key = (float(scale), method, int(budget), int(exploration_seed))
            if key in skip:
                continue
            variant = variants[method]
            seeds = SeedPlan(
                task_seed=task.depth,
                exploration_seed=exploration_seed,
                partition_seed=10_000,
            )
            config = benchmark_config(task, variant, exploration_seed)
            record = run_policy_variant(
                task,
                variant,
                seeds,
                int(budget),
                registry,
                verifier_budget_multiplier,
                config_override=config,
                posterior_sd_scale=float(scale),
            )
            records.append(_decorate_record(record))
            if progress_every and len(records) % progress_every == 0:
                print(f"completed {len(records)}/{total}", flush=True)
    return records


def _record_key(record: dict[str, Any]) -> tuple[float, str, int, int]:
    return (
        float(record["method"]["posterior_sd_scale"]),
        str(record["method"]["name"]),
        int(record["budget"]["limit"]),
        int(record["seeds"]["exploration_seed"]),
    )


def _validate_records(
    records: Sequence[dict[str, Any]],
    *,
    sd_scales: Sequence[float],
    budgets: Sequence[int],
    seed_ids: Sequence[int],
) -> dict[str, Any]:
    variants = _variant_map()
    expected = set(itertools.product(sd_scales, METHODS, budgets, seed_ids))
    keys = [_record_key(record) for record in records]
    actual = set(keys)
    duplicate_count = len(keys) - len(actual)
    error_counts: dict[str, int] = defaultdict(int)
    fingerprints: dict[tuple[float, int, int], set[str]] = defaultdict(set)
    all_fingerprints: set[str] = set()
    paired_groups: dict[str, list[tuple[float, str, int, int]]] = defaultdict(list)
    target = [2, 3, 4, 1]

    for record in records:
        key = _record_key(record)
        scale, method, budget, seed = key
        variant = variants.get(method)
        if variant is None or variant.uniform_sources is None:
            error_counts["source_contract"] += 1
            continue
        if record.get("schema_version") != SCHEMA_VERSION:
            error_counts["schema"] += 1
        if record.get("deterministic_digest") != canonical_record_digest(record):
            error_counts["digest"] += 1
        method_record = record["method"]
        if (
            method_record.get("uniform_sources") != variant.uniform_sources.as_dict()
            or method_record.get("sampler") != variant.sampler
            or method_record.get("sampler_layout")
            != "matched_full_dimension_column_mux/v1"
            or method_record.get("strata") != "embedding"
        ):
            error_counts["source_contract"] += 1

        task_record = record["task"]
        success_value = record["outcome"].get("readout_success")
        readout = [int(value) for value in record["outcome"]["readout_token_ids"]]
        exact_success = readout == target
        expected_return = 5.0 if exact_success else 0.0
        correct_prefix = 0
        for observed, expected_token in zip(readout, target):
            if observed != expected_token:
                break
            correct_prefix += 1
        if (
            task_record.get("id") != "role_lock_d4"
            or int(task_record.get("depth", -1)) != 4
            or list(task_record.get("target", [])) != target
            or task_record.get("terminal_only") is not True
            or not isinstance(success_value, bool)
            or success_value != exact_success
            or float(record["outcome"]["readout_return"]) != expected_return
            or int(record["outcome"].get("readout_correct_prefix_length", -1))
            != correct_prefix
            or record["outcome"].get("readout_failure_stage")
            != (None if exact_success else correct_prefix)
        ):
            error_counts["task_and_success_encoding"] += 1

        usage_record = record["usage"]
        budget_record = record["budget"]
        lm_used = int(usage_record["logical_lm_node_evals"])
        if (
            lm_used != budget
            or int(usage_record["physical_lm_forwards"]) != lm_used
            or int(budget_record.get("overshoot", -1)) != 0
        ):
            error_counts["lm_budget"] += 1
        if budget_record.get("stop_reason") in {"verifier_budget", "edge_budget"}:
            error_counts["guard_stop"] += 1
        if (
            method_record.get("pruning") is not False
            or int(usage_record["arms_pruned"]) != 0
            or int(usage_record["prune_checks"]) != 0
            or int(usage_record["prune_batches"]) != 0
        ):
            error_counts["pruning"] += 1
        uncertainty = record.get("uncertainty_profile", {})
        expected_config = asdict(benchmark_config(RoleLockTask(4), variant, seed))
        expected_seeds = asdict(
            SeedPlan(
                task_seed=4,
                exploration_seed=seed,
                partition_seed=10_000,
            )
        )
        if (
            float(method_record["posterior_sd_scale"]) != scale
            or float(uncertainty.get("posterior_sd_scale", -1.0)) != scale
            or record["search_config"] != expected_config
            or record["seeds"] != expected_seeds
            or int(budget_record["verifier_limit"]) != 16 * budget
        ):
            error_counts["config_propagation"] += 1
        if (
            int(usage_record["candidate_misses"]) != 0
            or record["search"].get("oracle_candidate_universe_guaranteed") is not True
        ):
            error_counts["candidate_universe"] += 1

        edge_selections = int(usage_record["edge_selections"])
        source_usage = record["search"].get("uniform_source_usage", {})
        selected_total = int(source_usage.get("total_selected_scalar_values", -1))
        selected_sobol = int(source_usage.get("selected_sobol_scalar_values", -1))
        selected_iid = int(source_usage.get("selected_iid_scalar_values", -1))
        sobol_columns = (
            int(variant.uniform_sources.coverage_gate == "sobol")
            + int(variant.uniform_sources.cluster_quantile == "sobol")
            + 10 * int(variant.uniform_sources.action_perturbation == "sobol")
        )
        if (
            source_usage.get("selection_points") != edge_selections
            or source_usage.get("sobol_full_points_generated") != edge_selections
            or source_usage.get("iid_full_points_generated") != edge_selections
            or source_usage.get("mux_nodes_created")
            != record["search"].get("nodes_created")
            or selected_total != 12 * edge_selections
            or selected_sobol != sobol_columns * edge_selections
            or selected_iid != selected_total - selected_sobol
            or int(usage_record["coverage_route_selections"])
            + int(usage_record["global_route_selections"])
            != edge_selections
        ):
            error_counts["uniform_draw_accounting"] += 1

        fingerprint = record["search"].get("root_candidate_fingerprint")
        if fingerprint is None:
            error_counts["candidate_fingerprint"] += 1
        else:
            fingerprints[(scale, budget, seed)].add(str(fingerprint))
            all_fingerprints.add(str(fingerprint))
        expected_group = f"role_lock_d4:sd{scale:g}:seed{seed}:b{budget}"
        group = str(record.get("paired_group_id"))
        if group != expected_group:
            error_counts["paired_group"] += 1
        paired_groups[group].append(key)
        randomization = record.get("randomization", {})
        if (
            randomization.get("source_architecture")
            != "matched_full_dimension_column_mux"
            or randomization.get("both_sources_advanced_every_draw") is not True
            or randomization.get("sobol_scramble") is not True
        ):
            error_counts["randomization_metadata"] += 1
        try:
            json.dumps(record, allow_nan=False)
        except (TypeError, ValueError):
            error_counts["strict_json"] += 1

    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    mismatched_fingerprints = [
        block for block, values in fingerprints.items() if len(values) != 1
    ]
    expected_blocks = len(sd_scales) * len(budgets) * len(seed_ids)
    paired_group_errors = sum(
        len(group_keys) != 4
        or len({key[0] for key in group_keys}) != 1
        or {key[1] for key in group_keys} != set(METHODS)
        for group_keys in paired_groups.values()
    )
    if paired_group_errors or len(paired_groups) != expected_blocks:
        error_counts["paired_group"] += paired_group_errors + abs(
            len(paired_groups) - expected_blocks
        )

    checks = {
        "expected_record_count": len(records) == len(expected),
        "complete_factorial": not missing and not unexpected,
        "unique_composite_keys": duplicate_count == 0,
        "schema_and_strict_json": error_counts["schema"] == 0
        and error_counts["strict_json"] == 0,
        "deterministic_digests": error_counts["digest"] == 0,
        "task_and_success_encoding": error_counts["task_and_success_encoding"] == 0,
        "exact_lm_caps_and_zero_overshoot": error_counts["lm_budget"] == 0,
        "no_verifier_or_edge_guard_stops": error_counts["guard_stop"] == 0,
        "pruning_disabled": error_counts["pruning"] == 0,
        "source_and_config_propagated": error_counts["source_contract"] == 0
        and error_counts["config_propagation"] == 0
        and error_counts["randomization_metadata"] == 0,
        "candidate_universe_complete": error_counts["candidate_universe"] == 0,
        "root_candidate_manifest_identical": (
            error_counts["candidate_fingerprint"] == 0
            and not mismatched_fingerprints
            and len(all_fingerprints) == 1
            and len(fingerprints) == expected_blocks
        ),
        "uniform_draw_accounting": error_counts["uniform_draw_accounting"] == 0,
        "paired_group_identity": error_counts["paired_group"] == 0,
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
            "error_counts": dict(error_counts),
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
    discordant = int(candidate_only + reference_only)
    if discordant == 0:
        return 1.0
    tail = min(int(candidate_only), int(reference_only))
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


def _paired_contrast(
    blocks: dict[int, dict[str, dict[str, Any]]],
    *,
    candidate: str,
    reference: str,
    label: str,
    bootstrap_seed: int,
) -> dict[str, Any]:
    deltas = []
    cost_fields = (
        "logical_lm_node_evals",
        "full_prefix_tokens",
        "verifier_requests",
        "edge_selections",
        "nodes_created",
    )
    cost_deltas: dict[str, list[float]] = {field: [] for field in cost_fields}
    candidate_only = 0
    reference_only = 0
    both_success = 0
    both_failure = 0
    for block in blocks.values():
        candidate_record = block[candidate]
        reference_record = block[reference]
        candidate_success = int(candidate_record["outcome"]["readout_success"])
        reference_success = int(reference_record["outcome"]["readout_success"])
        deltas.append(float(candidate_success - reference_success))
        candidate_only += int(candidate_success == 1 and reference_success == 0)
        reference_only += int(candidate_success == 0 and reference_success == 1)
        both_success += int(candidate_success == 1 and reference_success == 1)
        both_failure += int(candidate_success == 0 and reference_success == 0)
        for field in cost_fields:
            if field == "nodes_created":
                candidate_value = candidate_record["search"][field]
                reference_value = reference_record["search"][field]
            else:
                candidate_value = candidate_record["usage"][field]
                reference_value = reference_record["usage"][field]
            cost_deltas[field].append(float(candidate_value - reference_value))

    return {
        "label": label,
        "candidate": candidate,
        "reference": reference,
        "paired_blocks": len(deltas),
        "mean_success_delta": statistics.fmean(deltas),
        "paired_bootstrap_95": _bootstrap_mean_interval(deltas, bootstrap_seed),
        "discordance": {
            "candidate_only": candidate_only,
            "reference_only": reference_only,
            "both_success": both_success,
            "both_failure": both_failure,
        },
        "mcnemar_p": _exact_mcnemar_p(candidate_only, reference_only),
        "mean_cost_delta": {
            field: {
                "mean": statistics.fmean(values),
                "paired_bootstrap_95": _bootstrap_mean_interval(
                    values, bootstrap_seed + 100 + index
                ),
            }
            for index, (field, values) in enumerate(cost_deltas.items())
        },
    }


def _factorial_effects(
    blocks: dict[int, dict[str, dict[str, Any]]], bootstrap_seed: int
) -> dict[str, Any]:
    effects: dict[str, list[float]] = {
        "routing_main_effect": [],
        "action_main_effect": [],
        "routing_action_interaction": [],
    }
    for block in blocks.values():
        y_ii = float(block["iid_all"]["outcome"]["readout_success"])
        y_ss = float(block["sobol_all"]["outcome"]["readout_success"])
        y_si = float(block["sobol_routing_only"]["outcome"]["readout_success"])
        y_is = float(block["sobol_action_only"]["outcome"]["readout_success"])
        effects["routing_main_effect"].append(0.5 * ((y_ss - y_is) + (y_si - y_ii)))
        effects["action_main_effect"].append(0.5 * ((y_ss - y_si) + (y_is - y_ii)))
        effects["routing_action_interaction"].append(y_ss - y_si - y_is + y_ii)
    names = tuple(effects)
    matrix = torch.tensor(
        [[effects[name][row] for name in names] for row in range(len(blocks))],
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
    result: dict[str, Any] = {}
    bounds = {
        "routing_main_effect": (-1.0, 1.0),
        "action_main_effect": (-1.0, 1.0),
        "routing_action_interaction": (-2.0, 2.0),
    }
    for index, name in enumerate(names):
        nominal = bootstrap_means[:, index].sort().values
        low = float(nominal[int(0.025 * (BOOTSTRAP_SAMPLES - 1))].item())
        high = float(nominal[int(0.975 * (BOOTSTRAP_SAMPLES - 1))].item())
        mean = float(observed[index].item())
        lower_bound, upper_bound = bounds[name]
        result[name] = {
            "mean": mean,
            "paired_bootstrap_95_nominal": [low, high],
            "paired_bootstrap_95_simultaneous": [
                max(lower_bound, mean - critical),
                min(upper_bound, mean + critical),
            ],
        }
    result["simultaneous_interval_method"] = (
        "paired seed-block bootstrap; 95th percentile of the maximum absolute "
        "deviation across routing, action, and interaction"
    )
    return result


def _cell_summary(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    successes = sum(bool(row["outcome"]["readout_success"]) for row in rows)
    best_observed = sum(bool(row["outcome"]["best_observed_success"]) for row in rows)
    first_success_hits = [
        int(row["usage"]["first_success_lm_eval"])
        for row in rows
        if row["usage"]["first_success_lm_eval"] is not None
    ]
    prefix_histogram = {
        str(length): sum(
            int(row["outcome"]["readout_correct_prefix_length"]) == length
            for row in rows
        )
        for length in range(5)
    }
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
        "readout_correct_prefix_length_histogram": prefix_histogram,
        "best_observed_success_rate": best_observed / len(rows),
        "first_success_observed_count": len(first_success_hits),
        "first_success_censored_count": len(rows) - len(first_success_hits),
        "mean_first_success_lm_eval_among_hits": (
            statistics.fmean(first_success_hits) if first_success_hits else None
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
        "mean_root_cluster_visit_entropy": statistics.fmean(
            float(row["search"]["root_cluster_visit_entropy"]) for row in rows
        ),
        "mean_root_action_selection_entropy": statistics.fmean(
            float(row["search"]["root_action_selection_entropy"]) for row in rows
        ),
    }


def _effect_direction(interval: Sequence[float]) -> str:
    if float(interval[0]) > 0.0:
        return "positive"
    if float(interval[1]) < 0.0:
        return "negative"
    return "inconclusive"


def summarize(
    records: Sequence[dict[str, Any]],
    *,
    sd_scales: Sequence[float],
    budgets: Sequence[int],
    seed_ids: Sequence[int],
    diagnostic_seed: int = 313,
    run_mode: str = "analysis",
) -> dict[str, Any]:
    if PRIMARY_SCALE not in {float(value) for value in sd_scales}:
        raise ValueError("the declared primary posterior SD scale 1.0 is required")
    quality = _validate_records(
        records,
        sd_scales=sd_scales,
        budgets=budgets,
        seed_ids=seed_ids,
    )
    if quality["status"] != "PASS":
        raise ValueError(f"invalid channel-ablation records: {quality['failures']}")

    grouped: dict[tuple[float, int, str], list[dict[str, Any]]] = defaultdict(list)
    blocks: dict[tuple[float, int], dict[int, dict[str, dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    for record in records:
        scale, method, budget, seed = _record_key(record)
        grouped[(scale, budget, method)].append(record)
        blocks[(scale, budget)][seed][method] = record

    cells = []
    comparisons = []
    factorial = []
    planned = (
        ("sobol_routing_only", "iid_all", "routing_effect_under_iid_action"),
        ("sobol_all", "sobol_action_only", "routing_effect_under_sobol_action"),
        ("sobol_action_only", "iid_all", "action_effect_under_iid_routing"),
        ("sobol_all", "sobol_routing_only", "action_effect_under_sobol_routing"),
        ("sobol_all", "iid_all", "combined_sobol_effect"),
    )
    for scale in sd_scales:
        for budget in budgets:
            block = blocks[(float(scale), int(budget))]
            for method in METHODS:
                cell = _cell_summary(grouped[(float(scale), int(budget), method)])
                cells.append(
                    {
                        "posterior_sd_scale": float(scale),
                        "lm_budget": int(budget),
                        "method": method,
                        **cell,
                    }
                )
            local_comparisons = [
                {
                    "posterior_sd_scale": float(scale),
                    "lm_budget": int(budget),
                    **_paired_contrast(
                        block,
                        candidate=candidate,
                        reference=reference,
                        label=label,
                        bootstrap_seed=(
                            diagnostic_seed
                            + int(round(float(scale) * 1_000))
                            + int(budget)
                            + index
                        ),
                    ),
                }
                for index, (candidate, reference, label) in enumerate(planned)
            ]
            _holm_adjust(local_comparisons)
            comparisons.extend(local_comparisons)
            factorial.append(
                {
                    "posterior_sd_scale": float(scale),
                    "lm_budget": int(budget),
                    **_factorial_effects(
                        block,
                        diagnostic_seed
                        + int(round(float(scale) * 10_000))
                        + int(budget),
                    ),
                }
            )

    if run_mode == "full" and PRIMARY_BUDGET not in {int(value) for value in budgets}:
        raise ValueError("the fixed full-run primary LM-node budget 384 is required")
    primary_budget = (
        PRIMARY_BUDGET if run_mode == "full" else max(int(value) for value in budgets)
    )
    primary_scale = PRIMARY_SCALE
    primary_factorial = next(
        row
        for row in factorial
        if row["posterior_sd_scale"] == primary_scale
        and row["lm_budget"] == primary_budget
    )
    decision = {
        "scope": "Role-Lock D4 aligned static-token strata only",
        "routing_main_effect": _effect_direction(
            primary_factorial["routing_main_effect"]["paired_bootstrap_95_simultaneous"]
        ),
        "action_main_effect": _effect_direction(
            primary_factorial["action_main_effect"]["paired_bootstrap_95_simultaneous"]
        ),
        "interaction": _effect_direction(
            primary_factorial["routing_action_interaction"][
                "paired_bootstrap_95_simultaneous"
            ]
        ),
        "promotion_rule": (
            "This toy result may select the next engineering benchmark, but no "
            "channel is promoted without matched-compute validation on broader "
            "tasks and an implementation-cost measurement."
        ),
    }
    discovery_overlap = len(set(int(value) for value in seed_ids) & set(range(256)))
    return {
        "schema_version": SCHEMA_VERSION,
        "record_type": "channel_ablation_summary",
        "design": {
            "run_mode": run_mode,
            "task": "role_lock_d4",
            "methods": list(METHODS),
            "posterior_sd_scales": [float(value) for value in sd_scales],
            "lm_budgets": [int(value) for value in budgets],
            "exploration_seed_ids": [int(value) for value in seed_ids],
            "independent_randomization_unit": "exploration_seed",
            "routing_factor": "coverage_gate_plus_cluster_quantile",
            "action_factor": "posterior_action_perturbation",
            "common_random_numbers": "matched full-dimension coordinate sources",
            "matched_primary_budget": "logical_lm_node_evals_only",
            "discovery_seed_overlap": discovery_overlap,
            "cohort_scope": (
                "fresh_from_prior_d4_discovery_cohort"
                if discovery_overlap == 0
                else "overlaps_prior_d4_discovery_cohort"
            ),
            "sensitivity_note": (
                "SD 0.5 was selected from prior D4 engineering results and is "
                "secondary; SD 1.0 is the declared primary localization scale."
            ),
        },
        "data_quality": quality,
        "cells": cells,
        "planned_pairwise_contrasts": comparisons,
        "factorial_effects": factorial,
        "primary_endpoint": {
            "posterior_sd_scale": primary_scale,
            "lm_budget": primary_budget,
            "outcome": "readout_success",
        },
        "decision": decision,
        "limitations": [
            "Routing bundles coverage gate and cluster quantile; their individual effects are not identified.",
            "The mux assigns coordinates from two joint full-dimensional points; channels are not independent streams.",
            "Dual-source wall time is instrumentation cost, not deployment sampler cost.",
            "Only logical LM-node evaluations are exactly matched; verifier, edge, token, and node counts are measured outcomes.",
            "The task uses oracle-aligned static token embeddings and is not natural-language validation.",
            "Uncertainty is a nonstationary TD-target proxy, not an exact Bayesian posterior.",
        ],
    }


def _percent(value: float) -> str:
    return f"{100.0 * float(value):.1f}%"


def _pp(value: float) -> str:
    return f"{100.0 * float(value):+.1f} pp"


def render_report(summary: dict[str, Any]) -> str:
    primary = summary["primary_endpoint"]
    scale = primary["posterior_sd_scale"]
    budget = primary["lm_budget"]
    cells = {
        row["method"]: row
        for row in summary["cells"]
        if row["posterior_sd_scale"] == scale and row["lm_budget"] == budget
    }
    factorial = next(
        row
        for row in summary["factorial_effects"]
        if row["posterior_sd_scale"] == scale and row["lm_budget"] == budget
    )
    primary_comparisons = [
        row
        for row in summary["planned_pairwise_contrasts"]
        if row["posterior_sd_scale"] == scale and row["lm_budget"] == budget
    ]
    run_mode = summary["design"]["run_mode"]
    mode_boundary = (
        "This smoke output validates plumbing only; it is not performance evidence."
        if run_mode in {"smoke", "self_test"}
        else (
            "This fixed full cohort supports toy-task localization only; broader "
            "algorithm promotion still requires external matched-compute evidence."
        )
    )
    lines = [
        "# QMC-BMGS uniform-channel ablation",
        "",
        "## Outcome",
        "",
        (
            f"Primary: Role-Lock D4, posterior SD scale {scale:g}, "
            f"LM-node cap {budget}, paired n={cells['iid_all']['replicates']}."
        ),
        f"Run mode: `{run_mode}`; cohort: `{summary['design']['cohort_scope']}`.",
        "",
        "| Method | Readout success | Best observed | Verifier mean | Edge mean | Root coverage deviation |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for method in METHODS:
        row = cells[method]
        lines.append(
            f"| `{method}` | {_percent(row['readout_success_rate'])} "
            f"({row['readout_success_count']}/{row['replicates']}) | "
            f"{_percent(row['best_observed_success_rate'])} | "
            f"{row['mean_usage']['verifier_requests']:.1f} | "
            f"{row['mean_usage']['edge_selections']:.1f} | "
            f"{row['mean_root_coverage_max_uniform_deviation']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## Factorial localization",
            "",
            "The interval is simultaneous across routing, action, and interaction.",
            "",
            "| Effect | Mean risk difference | Simultaneous paired-bootstrap 95% |",
            "|---|---:|---:|",
        ]
    )
    for key, label in (
        ("routing_main_effect", "Routing Sobol main effect"),
        ("action_main_effect", "Action Sobol main effect"),
        ("routing_action_interaction", "Routing × action interaction"),
    ):
        effect = factorial[key]
        interval = effect["paired_bootstrap_95_simultaneous"]
        lines.append(
            f"| {label} | {_pp(effect['mean'])} | "
            f"[{_pp(interval[0])}, {_pp(interval[1])}] |"
        )
    lines.extend(
        [
            "",
            "## Planned simple contrasts",
            "",
            "McNemar p-values are Holm-adjusted across the five planned contrasts "
            "within this primary cell.",
            "",
            "| Contrast | Success delta | McNemar p | Holm p | Verifier delta | Edge delta |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in primary_comparisons:
        lines.append(
            f"| `{row['label']}` | {_pp(row['mean_success_delta'])} | "
            f"{row['mcnemar_p']:.4g} | {row['holm_adjusted_p']:.4g} | "
            f"{row['mean_cost_delta']['verifier_requests']['mean']:+.1f} | "
            f"{row['mean_cost_delta']['edge_selections']['mean']:+.1f} |"
        )
    lines.extend(
        [
            "",
            "## Sensitivity",
            "",
            "SD 0.5 is a prior-result-selected engineering sensitivity, not a "
            "second confirmatory endpoint.",
            "",
            "| SD scale | Routing | Action | Interaction |",
            "|---:|---:|---:|---:|",
        ]
    )
    for row in summary["factorial_effects"]:
        if row["lm_budget"] != budget:
            continue
        lines.append(
            f"| {row['posterior_sd_scale']:g} | "
            f"{_pp(row['routing_main_effect']['mean'])} | "
            f"{_pp(row['action_main_effect']['mean'])} | "
            f"{_pp(row['routing_action_interaction']['mean'])} |"
        )
    lines.extend(
        [
            "",
            "## Data quality",
            "",
            f"Status: `{summary['data_quality']['status']}`. "
            f"Records: {summary['data_quality']['details']['observed_records']}; "
            f"paired groups: {summary['data_quality']['details']['paired_groups']}.",
            "",
            "## Decision boundary",
            "",
            f"- Routing effect: `{summary['decision']['routing_main_effect']}`",
            f"- Action effect: `{summary['decision']['action_main_effect']}`",
            f"- Interaction: `{summary['decision']['interaction']}`",
            f"- {mode_boundary}",
            "- Gate and cluster quantile remain bundled in the routing factor.",
            "- Only logical LM-node evaluations are exactly matched; other costs "
            "are measured outcomes.",
            "- The result is conditional on the aligned Role-Lock toy task.",
            "",
            "## Reproduce",
            "",
            "```bash",
            "python -m qmc_bmgs.experiments.channel_ablation "
            f"--sd-scales {','.join(str(value) for value in summary['design']['posterior_sd_scales'])} "
            f"--budgets {','.join(str(value) for value in summary['design']['lm_budgets'])} "
            f"--seed-start {min(summary['design']['exploration_seed_ids'])} "
            f"--seeds {len(summary['design']['exploration_seed_ids'])}",
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


def _parse_csv_ints(value: str) -> list[int]:
    values = [int(part.strip()) for part in value.split(",") if part.strip()]
    if (
        not values
        or any(item <= 0 for item in values)
        or len(set(values)) != len(values)
    ):
        raise argparse.ArgumentTypeError(
            "expected unique comma-separated positive ints"
        )
    return values


def _parse_csv_floats(value: str) -> list[float]:
    values = [float(part.strip()) for part in value.split(",") if part.strip()]
    if (
        not values
        or any(not math.isfinite(item) or item <= 0.0 for item in values)
        or len(set(values)) != len(values)
    ):
        raise argparse.ArgumentTypeError(
            "expected unique comma-separated positive finite floats"
        )
    return values


def _self_test() -> None:
    scales = [1.0]
    budgets = [12, 24]
    seed_ids = [0, 1]
    records = run_ablation(
        sd_scales=scales,
        budgets=budgets,
        seed_start=0,
        seeds_count=len(seed_ids),
        verifier_budget_multiplier=16.0,
    )
    repeat = run_ablation(
        sd_scales=scales,
        budgets=budgets,
        seed_start=0,
        seeds_count=len(seed_ids),
        verifier_budget_multiplier=16.0,
    )
    assert [row["deterministic_digest"] for row in records] == [
        row["deterministic_digest"] for row in repeat
    ]
    summary = summarize(
        records,
        sd_scales=scales,
        budgets=budgets,
        seed_ids=seed_ids,
        run_mode="self_test",
    )
    assert len(records) == 16
    assert summary["data_quality"]["status"] == "PASS"
    assert len(summary["planned_pairwise_contrasts"]) == 10
    assert "uniform-channel ablation" in render_report(summary)
    synthetic_blocks = {
        seed: {
            method: {"outcome": {"readout_success": method in {"iid_all", "sobol_all"}}}
            for method in METHODS
        }
        for seed in range(4)
    }
    synthetic_effects = _factorial_effects(synthetic_blocks, bootstrap_seed=7)
    interaction = synthetic_effects["routing_action_interaction"]
    assert interaction["mean"] == 2.0
    assert interaction["paired_bootstrap_95_simultaneous"] == [2.0, 2.0]

    def assert_mutation_fails(mutator: Any) -> None:
        corrupted = json.loads(json.dumps(records))
        mutator(corrupted)
        for row in corrupted:
            row["deterministic_digest"] = canonical_record_digest(row)
        quality = _validate_records(
            corrupted,
            sd_scales=scales,
            budgets=budgets,
            seed_ids=seed_ids,
        )
        assert quality["status"] == "FAIL"

    assert_mutation_fails(
        lambda rows: rows[0]["usage"].__setitem__("logical_lm_node_evals", 1)
    )
    assert_mutation_fails(
        lambda rows: rows[0]["budget"].__setitem__("stop_reason", "edge_budget")
    )
    assert_mutation_fails(lambda rows: rows[0]["usage"].__setitem__("arms_pruned", 1))
    assert_mutation_fails(
        lambda rows: [
            row["search"].__setitem__("root_candidate_fingerprint", None)
            for row in rows
        ]
    )
    assert_mutation_fails(
        lambda rows: rows[0]["outcome"].__setitem__(
            "readout_success", not rows[0]["outcome"]["readout_success"]
        )
    )
    assert_mutation_fails(lambda rows: rows[0]["task"].__setitem__("id", "wrong"))
    assert_mutation_fails(
        lambda rows: rows[0]["search_config"].__setitem__("seed", 99_999)
    )
    for field, value in (
        ("action_prior_strength", 0.9),
        ("semantic_uniform_mix", 0.2),
        ("candidate_top_k", 9),
        ("observation_variance", 3.0),
        ("gamma", 0.5),
    ):
        assert_mutation_fails(
            lambda rows, field=field, value=value: rows[0]["search_config"].__setitem__(
                field, value
            )
        )
    assert_mutation_fails(
        lambda rows: rows[0]["budget"].__setitem__("verifier_limit", 1)
    )
    assert_mutation_fails(
        lambda rows: rows[0]["seeds"].__setitem__("candidate_seed", 999)
    )
    assert_mutation_fails(lambda rows: rows[0].__setitem__("paired_group_id", "wrong"))
    json.dumps(summary, allow_nan=False)
    print("channel ablation self-test: PASS")


def main() -> None:
    base = Path.cwd() / "artifacts" / "work" / "qmc_bmgs_channel_ablation"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--sd-scales", default="0.5,1.0")
    parser.add_argument("--budgets", default="384")
    parser.add_argument("--seed-start", type=int, default=256)
    parser.add_argument("--seeds", type=int, default=256)
    parser.add_argument("--diagnostic-seed", type=int, default=313)
    parser.add_argument("--verifier-budget-multiplier", type=float, default=16.0)
    parser.add_argument("--progress-every", type=int, default=128)
    parser.add_argument(
        "--resume-from",
        type=Path,
        action="append",
        default=[],
        help=(
            "Reuse validated matching records from one or more JSONL shards and "
            "run only missing factorial cells"
        ),
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
    if args.seed_start < 0 or args.seeds < 1:
        parser.error("--seed-start must be nonnegative and --seeds positive")
    if args.verifier_budget_multiplier != 16.0:
        parser.error("--verifier-budget-multiplier is fixed at 16 for this design")
    if args.progress_every < 0:
        parser.error("--progress-every must be nonnegative")

    scales = _parse_csv_floats(args.sd_scales)
    budgets = _parse_csv_ints(args.budgets)
    seeds_count = args.seeds
    if args.smoke:
        scales = [1.0]
        budgets = [64, 128]
        seeds_count = 4
    if PRIMARY_SCALE not in scales:
        parser.error("--sd-scales must include the declared primary scale 1.0")
    if not args.smoke and PRIMARY_BUDGET not in budgets:
        parser.error("--budgets must include the declared full-run primary cap 384")

    seed_ids = list(range(args.seed_start, args.seed_start + seeds_count))
    expected_keys = set(itertools.product(scales, METHODS, budgets, seed_ids))
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

    new_records = run_ablation(
        sd_scales=scales,
        budgets=budgets,
        seed_start=args.seed_start,
        seeds_count=seeds_count,
        verifier_budget_multiplier=args.verifier_budget_multiplier,
        progress_every=args.progress_every,
        skip_keys=set(reused_keys),
    )
    records = reused_records + new_records
    summary = summarize(
        records,
        sd_scales=scales,
        budgets=budgets,
        seed_ids=seed_ids,
        diagnostic_seed=args.diagnostic_seed,
        run_mode="smoke" if args.smoke else "full",
    )
    _write_jsonl(args.runs_jsonl, records)
    reloaded_records = _read_jsonl(args.runs_jsonl)
    reloaded_summary = summarize(
        reloaded_records,
        sd_scales=scales,
        budgets=budgets,
        seed_ids=seed_ids,
        diagnostic_seed=args.diagnostic_seed,
        run_mode="smoke" if args.smoke else "full",
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
