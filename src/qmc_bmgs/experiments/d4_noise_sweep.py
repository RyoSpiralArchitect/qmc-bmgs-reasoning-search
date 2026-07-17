#!/usr/bin/env python3
"""D4 matched IID-versus-randomized-Sobol uncertainty sweep.

This is a focused follow-up to :mod:`qmc_bmgs.benchmarks.role_lock`.  It fixes the
Role-Lock D4 task, aligned embedding strata, candidate construction, learned
return, LM behavior prior, and pruning-off policy.  The only policy factors are
the posterior-standard-deviation multiplier and the uniform engine used by the
Thompson/coverage sampler.

An ``exploration_seed`` is the independent randomization unit: one family of
node-local scrambled Sobol streams or its IID peer.  Budgets, nodes, actions,
and nested scramble-count diagnostics are not treated as independent samples.

Default experiment
------------------

    2 samplers x 3 SD scales x 4 LM caps x 64 paired seeds = 1,536 runs

    python -m qmc_bmgs.experiments.d4_noise_sweep
    python -m qmc_bmgs.experiments.d4_noise_sweep --self-test
    python -m qmc_bmgs.experiments.d4_noise_sweep --smoke

The primary endpoint is predeclared as readout success at SD scale 1.0 and the
largest LM cap.  Other cells are sensitivity analyses.  Binary success spread
is not used as evidence of QMC variance reduction; empirical run-to-run spread
is evaluated on per-seed success-budget AUC instead.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import torch

from qmc_bmgs.benchmarks.role_lock import (
    POLICY_VARIANTS,
    CandidateRegistry,
    RoleLockTask,
    SeedPlan,
    VariantSpec,
    benchmark_config,
    run_policy_variant,
)
from qmc_bmgs.records import canonical_record_digest


SCHEMA_VERSION = "qmc-bmgs-d4-noise-sweep/v1"
SAMPLERS = ("iid", "sobol")
DEFAULT_SD_SCALES = (0.5, 1.0, 2.0)
DEFAULT_BUDGETS = (64, 128, 256, 384)
DEFAULT_STABILITY_COUNTS = (8, 16, 32, 64)
PRIMARY_SD_SCALE = 1.0
BOOTSTRAP_SAMPLES = 10_000
SUBSET_SAMPLES = 2_000


@dataclass(frozen=True)
class NoiseProfile:
    profile_id: str
    posterior_sd_scale: float

    @classmethod
    def from_scale(cls, scale: float) -> "NoiseProfile":
        if not math.isfinite(scale) or scale <= 0.0:
            raise ValueError("posterior SD scales must be finite and positive")
        label = format(float(scale), ".8g").replace(".", "p")
        return cls(f"sd_{label}", float(scale))


def _variant_map() -> dict[str, VariantSpec]:
    wanted = {
        "iid": "iid_embedding_no_prune",
        "sobol": "sobol_embedding_no_prune",
    }
    result = {
        sampler: next(v for v in POLICY_VARIANTS if v.name == name)
        for sampler, name in wanted.items()
    }
    for sampler, variant in result.items():
        if variant.sampler != sampler or variant.strata != "embedding":
            raise AssertionError("D4 sampler variant is not aligned embedding")
        if variant.pruning:
            raise AssertionError("D4 sweep must keep pruning disabled")
    return result


def _stable_seed(label: str) -> int:
    return int.from_bytes(
        hashlib.blake2b(label.encode(), digest_size=8).digest(), "little"
    ) % (2**31 - 1)


def _quantile(values: Sequence[float], probability: float) -> float:
    if not values:
        raise ValueError("cannot take a quantile of an empty sequence")
    tensor = torch.tensor(values, dtype=torch.float64).sort().values
    position = probability * (len(tensor) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return float(tensor[lower].item())
    weight = position - lower
    return float(((1.0 - weight) * tensor[lower] + weight * tensor[upper]).item())


def _bootstrap_mean_interval(
    values: Sequence[float], *, seed: int, samples: int = BOOTSTRAP_SAMPLES
) -> tuple[float, float]:
    if not values:
        raise ValueError("bootstrap values cannot be empty")
    if len(values) == 1:
        return float(values[0]), float(values[0])
    tensor = torch.tensor(values, dtype=torch.float64)
    generator = torch.Generator().manual_seed(int(seed))
    indices = torch.randint(0, len(tensor), (samples, len(tensor)), generator=generator)
    means = tensor[indices].mean(dim=1).sort().values
    return (
        float(means[int(0.025 * (samples - 1))].item()),
        float(means[int(0.975 * (samples - 1))].item()),
    )


def _wilson_interval(successes: int, total: int) -> tuple[float, float]:
    if total <= 0:
        raise ValueError("Wilson interval requires a positive total")
    z = 1.959963984540054
    p = successes / total
    denominator = 1.0 + z * z / total
    center = (p + z * z / (2.0 * total)) / denominator
    radius = (
        z
        * math.sqrt(p * (1.0 - p) / total + z * z / (4.0 * total * total))
        / denominator
    )
    return max(0.0, center - radius), min(1.0, center + radius)


def _exact_mcnemar_p(sobol_only: int, iid_only: int) -> float:
    discordant = int(sobol_only + iid_only)
    if discordant == 0:
        return 1.0
    tail = min(int(sobol_only), int(iid_only))
    probability = sum(math.comb(discordant, k) for k in range(tail + 1)) / (
        2**discordant
    )
    return min(1.0, 2.0 * probability)


def _holm_adjust(p_values: Sequence[float]) -> list[float]:
    count = len(p_values)
    order = sorted(range(count), key=lambda index: p_values[index])
    adjusted = [1.0] * count
    running = 0.0
    for rank, index in enumerate(order):
        candidate = min(1.0, (count - rank) * float(p_values[index]))
        running = max(running, candidate)
        adjusted[index] = running
    return adjusted


def _sample_variance(values: Sequence[float]) -> float:
    return statistics.variance(values) if len(values) > 1 else 0.0


def _log_variance_ratio_analysis(
    sobol_values: Sequence[float],
    iid_values: Sequence[float],
    *,
    seed: int,
) -> dict[str, Any]:
    if len(sobol_values) != len(iid_values) or len(sobol_values) < 2:
        raise ValueError("variance analysis requires matched vectors of length >= 2")
    sobol = torch.tensor(sobol_values, dtype=torch.float64)
    iid = torch.tensor(iid_values, dtype=torch.float64)
    epsilon = 1e-12
    sobol_variance = float(torch.var(sobol, unbiased=True).item())
    iid_variance = float(torch.var(iid, unbiased=True).item())
    log_ratio = math.log(max(sobol_variance, epsilon) / max(iid_variance, epsilon))

    generator = torch.Generator().manual_seed(seed)
    indices = torch.randint(
        0,
        len(sobol),
        (BOOTSTRAP_SAMPLES, len(sobol)),
        generator=generator,
    )
    sobol_boot = torch.var(sobol[indices], dim=1, unbiased=True).clamp_min(epsilon)
    iid_boot = torch.var(iid[indices], dim=1, unbiased=True).clamp_min(epsilon)
    boot = torch.log(sobol_boot / iid_boot).sort().values
    bootstrap_95 = [
        float(boot[int(0.025 * (BOOTSTRAP_SAMPLES - 1))].item()),
        float(boot[int(0.975 * (BOOTSTRAP_SAMPLES - 1))].item()),
    ]

    return {
        "sobol_sample_variance": sobol_variance,
        "iid_sample_variance": iid_variance,
        "variance_ratio_sobol_over_iid": (
            sobol_variance / iid_variance if iid_variance > 0.0 else None
        ),
        "log_variance_ratio": log_ratio,
        "log_variance_ratio_bootstrap_95": bootstrap_95,
        "zero_variance_regularization": epsilon,
        "inference_boundary": (
            "paired seed-block bootstrap is descriptive for empirical spread; "
            "no label-swap variance test is used because method means and "
            "distributions may differ"
        ),
    }


def _enrich_record(
    record: dict[str, Any],
    *,
    profile: NoiseProfile,
    max_budget: int,
) -> dict[str, Any]:
    sampler = str(record["method"]["sampler"])
    seed = int(record["seeds"]["exploration_seed"])
    budget = int(record["budget"]["limit"])
    record["schema_version"] = SCHEMA_VERSION
    record["experiment"] = {
        "name": "role_lock_d4_iid_vs_scrambled_sobol_noise_sweep",
        "fixed_task": "role_lock_d4",
        "fixed_strata": "aligned_static_token_embedding",
        "fixed_pruning": False,
        "primary_endpoint": {
            "posterior_sd_scale": PRIMARY_SD_SCALE,
            "budget": int(max_budget),
            "metric": "readout_success",
            "estimand": "P(Sobol success) - P(IID success)",
        },
    }
    record["uncertainty_profile"] = {
        **asdict(profile),
        "implementation": (
            "multiply the benchmark uncertainty-proxy variance by scale^2; "
            "learned means, rewards, action prior, candidates, and routing "
            "probabilities remain fixed"
        ),
        "posterior_claim": "nonstationary uncertainty proxy, not exact posterior",
    }
    record["randomization"] = {
        "independent_unit": "exploration_seed",
        "replicate_id": seed,
        "engine": (
            "torch_node_local_scrambled_sobol"
            if sampler == "sobol"
            else "torch_node_local_iid_uniform"
        ),
        "scramble_enabled": sampler == "sobol",
        "node_stream_seeded_from": "exploration_seed_and_exact_prefix",
        "common_random_numbers": False,
        "engine_consumers": [
            "semantic_coverage_gate",
            "cluster_quantile",
            "action_posterior_perturbations",
        ],
    }
    record["paired_group_id"] = (
        f"role_lock_d4:{profile.profile_id}:seed{seed}:b{budget}"
    )
    record["deterministic_digest"] = canonical_record_digest(record)
    json.dumps(record, allow_nan=False)
    return record


def run_sweep(
    *,
    sd_scales: Sequence[float],
    budgets: Sequence[int],
    seed_start: int,
    seeds_count: int,
    verifier_budget_multiplier: float,
    progress_every: int = 64,
    existing_records: Sequence[dict[str, Any]] = (),
) -> list[dict[str, Any]]:
    task = RoleLockTask(4)
    variants = _variant_map()
    profiles = [NoiseProfile.from_scale(value) for value in sd_scales]
    records: list[dict[str, Any]] = [dict(record) for record in existing_records]
    registry = CandidateRegistry()
    total = len(profiles) * len(budgets) * seeds_count * len(SAMPLERS)
    existing_keys = {_record_key(record) for record in records}
    if len(existing_keys) != len(records):
        raise ValueError("existing_records contains duplicate sweep keys")
    if len(records) > total:
        raise ValueError("existing_records exceeds the requested factorial")

    for profile in profiles:
        for budget in budgets:
            for seed in range(seed_start, seed_start + seeds_count):
                seeds = SeedPlan(
                    exploration_seed=seed,
                    partition_seed=10_000,
                    task_seed=4,
                )
                for sampler in SAMPLERS:
                    key = (
                        profile.posterior_sd_scale,
                        sampler,
                        int(budget),
                        seed,
                    )
                    if key in existing_keys:
                        continue
                    variant = variants[sampler]
                    config = benchmark_config(task, variant, seed)
                    record = run_policy_variant(
                        task,
                        variant,
                        seeds,
                        int(budget),
                        registry,
                        verifier_budget_multiplier,
                        config_override=config,
                        posterior_sd_scale=profile.posterior_sd_scale,
                    )
                    records.append(
                        _enrich_record(
                            record,
                            profile=profile,
                            max_budget=max(int(value) for value in budgets),
                        )
                    )
                    existing_keys.add(key)
                    if progress_every > 0 and (
                        len(records) % progress_every == 0 or len(records) == total
                    ):
                        print(
                            json.dumps(
                                {
                                    "progress": len(records),
                                    "total": total,
                                    "sd_scale": profile.posterior_sd_scale,
                                    "budget": int(budget),
                                    "seed": seed,
                                }
                            ),
                            flush=True,
                        )
    return records


def _record_key(record: dict[str, Any]) -> tuple[float, str, int, int]:
    return (
        float(record["uncertainty_profile"]["posterior_sd_scale"]),
        str(record["method"]["sampler"]),
        int(record["budget"]["limit"]),
        int(record["seeds"]["exploration_seed"]),
    )


def validate_records(
    records: Sequence[dict[str, Any]],
    *,
    sd_scales: Sequence[float],
    budgets: Sequence[int],
    seed_ids: Sequence[int],
) -> dict[str, Any]:
    expected_keys = {
        (float(scale), sampler, int(budget), int(seed))
        for scale in sd_scales
        for sampler in SAMPLERS
        for budget in budgets
        for seed in seed_ids
    }
    keys = [_record_key(record) for record in records]
    duplicate_count = len(keys) - len(set(keys))
    actual_keys = set(keys)
    target = [2, 3, 4, 1]

    digest_errors = 0
    success_encoding_errors = 0
    budget_errors = 0
    guard_stops = 0
    prune_errors = 0
    config_errors = 0
    candidate_misses = 0
    root_fingerprints: set[str] = set()
    for record in records:
        if record.get("deterministic_digest") != canonical_record_digest(record):
            digest_errors += 1
        success = bool(record["outcome"]["readout_success"])
        exact = list(record["outcome"]["readout_token_ids"]) == target
        expected_return = 5.0 if success else 0.0
        if success != exact or float(record["outcome"]["readout_return"]) != expected_return:
            success_encoding_errors += 1
        limit = int(record["budget"]["limit"])
        used = int(record["usage"]["logical_lm_node_evals"])
        if used != limit or int(record["budget"]["overshoot"]) != 0:
            budget_errors += 1
        if record["budget"]["stop_reason"] in ("verifier_budget", "edge_budget"):
            guard_stops += 1
        if (
            bool(record["method"]["pruning"])
            or int(record["usage"]["arms_pruned"]) != 0
            or int(record["usage"]["prune_checks"]) != 0
        ):
            prune_errors += 1
        scale = float(record["uncertainty_profile"]["posterior_sd_scale"])
        if (
            float(record["method"]["posterior_sd_scale"]) != scale
            or int(record["search_config"]["seed"])
            != int(record["seeds"]["exploration_seed"])
            or record["method"]["strata"] != "embedding"
        ):
            config_errors += 1
        candidate_misses += int(record["usage"]["candidate_misses"])
        fingerprint = record["search"].get("root_candidate_fingerprint")
        if fingerprint is not None:
            root_fingerprints.add(str(fingerprint))
        json.dumps(record, allow_nan=False)

    prefix_consistency_errors = 0
    multi_budget_groups = 0
    grouped: dict[tuple[float, str, int], list[dict[str, Any]]] = {}
    for record in records:
        scale, sampler, _budget, seed = _record_key(record)
        grouped.setdefault((scale, sampler, seed), []).append(record)
    for rows in grouped.values():
        rows.sort(key=lambda row: int(row["budget"]["limit"]))
        if len(rows) < 2:
            continue
        multi_budget_groups += 1
        observed = [bool(row["outcome"]["best_observed_success"]) for row in rows]
        if any(left and not right for left, right in zip(observed, observed[1:])):
            prefix_consistency_errors += 1
        first_hits = [
            int(row["usage"]["first_success_lm_eval"])
            for row in rows
            if row["usage"]["first_success_lm_eval"] is not None
        ]
        if len(set(first_hits)) > 1:
            prefix_consistency_errors += 1

    checks = {
        "expected_record_count": len(records) == len(expected_keys),
        "complete_factorial": actual_keys == expected_keys,
        "unique_composite_keys": duplicate_count == 0,
        "deterministic_digests": digest_errors == 0,
        "strict_success_encoding": success_encoding_errors == 0,
        "exact_lm_caps_and_zero_overshoot": budget_errors == 0,
        "no_verifier_or_edge_guard_stops": guard_stops == 0,
        "pruning_disabled": prune_errors == 0,
        "noise_and_seed_config_propagated": config_errors == 0,
        "candidate_universe_complete": candidate_misses == 0,
        "root_candidate_manifest_identical": len(root_fingerprints) == 1,
    }
    if multi_budget_groups > 0:
        checks["fresh_budget_observation_consistency"] = (
            prefix_consistency_errors == 0
        )
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "status": "PASS" if not failures else "FAIL",
        "checks": checks,
        "failures": failures,
        "details": {
            "expected_records": len(expected_keys),
            "actual_records": len(records),
            "duplicate_count": duplicate_count,
            "missing_cells": len(expected_keys - actual_keys),
            "unexpected_cells": len(actual_keys - expected_keys),
            "digest_errors": digest_errors,
            "success_encoding_errors": success_encoding_errors,
            "budget_errors": budget_errors,
            "guard_stops": guard_stops,
            "prune_errors": prune_errors,
            "config_errors": config_errors,
            "candidate_misses": candidate_misses,
            "distinct_root_candidate_fingerprints": len(root_fingerprints),
            "multi_budget_observation_groups_checked": multi_budget_groups,
            "prefix_consistency_errors": prefix_consistency_errors,
        },
    }


def _cell_summary(records: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[float, str, int], list[dict[str, Any]]] = {}
    for record in records:
        scale, sampler, budget, _seed = _record_key(record)
        groups.setdefault((scale, sampler, budget), []).append(record)

    cells: list[dict[str, Any]] = []
    for (scale, sampler, budget), rows in sorted(groups.items()):
        rows.sort(key=lambda row: int(row["seeds"]["exploration_seed"]))
        success_count = sum(bool(row["outcome"]["readout_success"]) for row in rows)
        observed_count = sum(
            bool(row["outcome"]["best_observed_success"]) for row in rows
        )
        low, high = _wilson_interval(success_count, len(rows))
        censored_hits = [
            int(row["usage"]["first_success_lm_eval"])
            if row["usage"]["first_success_lm_eval"] is not None
            else budget + 1
            for row in rows
        ]
        cells.append(
            {
                "posterior_sd_scale": scale,
                "sampler": sampler,
                "budget": budget,
                "paired_replicates": len(rows),
                "readout_success_count": success_count,
                "readout_success_rate": success_count / len(rows),
                "readout_success_wilson_95": [low, high],
                "best_observed_success_count": observed_count,
                "best_observed_success_rate": observed_count / len(rows),
                "mean_censored_first_success_lm_eval": statistics.fmean(
                    censored_hits
                ),
                "mean_verifier_requests": statistics.fmean(
                    float(row["usage"]["verifier_requests"]) for row in rows
                ),
                "mean_edge_selections": statistics.fmean(
                    float(row["usage"]["edge_selections"]) for row in rows
                ),
                "mean_full_prefix_tokens": statistics.fmean(
                    float(row["usage"]["full_prefix_tokens"]) for row in rows
                ),
                "mean_root_coverage_max_uniform_deviation": statistics.fmean(
                    float(row["search"]["root_coverage_max_uniform_deviation"])
                    for row in rows
                ),
                "stop_reasons": {
                    reason: sum(row["budget"]["stop_reason"] == reason for row in rows)
                    for reason in sorted({row["budget"]["stop_reason"] for row in rows})
                },
            }
        )
    return cells


def _paired_comparisons(records: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    by_cell: dict[tuple[float, int, int], dict[str, dict[str, Any]]] = {}
    for record in records:
        scale, sampler, budget, seed = _record_key(record)
        by_cell.setdefault((scale, budget, seed), {})[sampler] = record

    conditions = sorted({(key[0], key[1]) for key in by_cell})
    comparisons: list[dict[str, Any]] = []
    for scale, budget in conditions:
        seed_rows = [
            (seed, samplers)
            for (cell_scale, cell_budget, seed), samplers in by_cell.items()
            if cell_scale == scale and cell_budget == budget
        ]
        seed_rows.sort()
        if any(set(samplers) != set(SAMPLERS) for _seed, samplers in seed_rows):
            raise AssertionError("paired comparison has a missing sampler")
        pairs = [
            (
                int(samplers["sobol"]["outcome"]["readout_success"]),
                int(samplers["iid"]["outcome"]["readout_success"]),
            )
            for _seed, samplers in seed_rows
        ]
        n11 = sum(sobol == 1 and iid == 1 for sobol, iid in pairs)
        n10 = sum(sobol == 1 and iid == 0 for sobol, iid in pairs)
        n01 = sum(sobol == 0 and iid == 1 for sobol, iid in pairs)
        n00 = sum(sobol == 0 and iid == 0 for sobol, iid in pairs)
        differences = [float(sobol - iid) for sobol, iid in pairs]
        low, high = _bootstrap_mean_interval(
            differences, seed=_stable_seed(f"paired:{scale}:{budget}")
        )

        def mean_cost_delta(field: str) -> float:
            return statistics.fmean(
                float(samplers["sobol"]["usage"][field])
                - float(samplers["iid"]["usage"][field])
                for _seed, samplers in seed_rows
            )

        comparisons.append(
            {
                "posterior_sd_scale": scale,
                "budget": budget,
                "paired_replicates": len(pairs),
                "discordance": {
                    "both_success_n11": n11,
                    "sobol_only_n10": n10,
                    "iid_only_n01": n01,
                    "neither_n00": n00,
                },
                "success_delta_sobol_minus_iid": statistics.fmean(differences),
                "paired_seed_bootstrap_95": [low, high],
                "exact_two_sided_mcnemar_p": _exact_mcnemar_p(n10, n01),
                "mean_cost_delta_sobol_minus_iid": {
                    "logical_lm_node_evals": mean_cost_delta(
                        "logical_lm_node_evals"
                    ),
                    "verifier_requests": mean_cost_delta("verifier_requests"),
                    "edge_selections": mean_cost_delta("edge_selections"),
                    "full_prefix_tokens": mean_cost_delta("full_prefix_tokens"),
                },
            }
        )

    all_adjusted = _holm_adjust(
        [float(row["exact_two_sided_mcnemar_p"]) for row in comparisons]
    )
    for row, adjusted in zip(comparisons, all_adjusted):
        row["holm_adjusted_p_all_sensitivity_cells"] = adjusted

    max_budget = max(int(row["budget"]) for row in comparisons)
    max_budget_rows = [row for row in comparisons if int(row["budget"]) == max_budget]
    max_adjusted = _holm_adjust(
        [float(row["exact_two_sided_mcnemar_p"]) for row in max_budget_rows]
    )
    for row, adjusted in zip(max_budget_rows, max_adjusted):
        row["holm_adjusted_p_max_budget_noise_family"] = adjusted
    return comparisons


def _success_budget_auc(
    successes_by_budget: dict[int, float], budgets: Sequence[int]
) -> float:
    ordered = sorted(int(value) for value in budgets)
    points = [(0, 0.0)] + [
        (budget, float(successes_by_budget[budget])) for budget in ordered
    ]
    area = 0.0
    for (left_budget, left_value), (right_budget, right_value) in zip(
        points, points[1:]
    ):
        area += (right_budget - left_budget) * (left_value + right_value) / 2.0
    return area / ordered[-1]


def _curve_stability(
    records: Sequence[dict[str, Any]], budgets: Sequence[int]
) -> list[dict[str, Any]]:
    lookup = {_record_key(record): record for record in records}
    scales = sorted({key[0] for key in lookup})
    seeds = sorted({key[3] for key in lookup})
    results: list[dict[str, Any]] = []

    for scale in scales:
        auc_by_sampler: dict[str, list[float]] = {sampler: [] for sampler in SAMPLERS}
        nonmonotone: dict[str, int] = {sampler: 0 for sampler in SAMPLERS}
        for sampler in SAMPLERS:
            for seed in seeds:
                curve = {
                    int(budget): float(
                        lookup[(scale, sampler, int(budget), seed)]["outcome"][
                            "readout_success"
                        ]
                    )
                    for budget in budgets
                }
                ordered_values = [curve[int(budget)] for budget in sorted(budgets)]
                if any(
                    left > right
                    for left, right in zip(ordered_values, ordered_values[1:])
                ):
                    nonmonotone[sampler] += 1
                auc_by_sampler[sampler].append(_success_budget_auc(curve, budgets))

        differences = [
            sobol - iid
            for sobol, iid in zip(auc_by_sampler["sobol"], auc_by_sampler["iid"])
        ]
        mean_low, mean_high = _bootstrap_mean_interval(
            differences, seed=_stable_seed(f"auc-mean:{scale}")
        )
        variance = _log_variance_ratio_analysis(
            auc_by_sampler["sobol"],
            auc_by_sampler["iid"],
            seed=_stable_seed(f"auc-variance:{scale}"),
        )
        results.append(
            {
                "posterior_sd_scale": scale,
                "metric": "per_seed_readout_success_budget_auc_over_0_to_max_cap",
                "paired_replicates": len(seeds),
                "sobol_mean_auc": statistics.fmean(auc_by_sampler["sobol"]),
                "iid_mean_auc": statistics.fmean(auc_by_sampler["iid"]),
                "mean_auc_delta_sobol_minus_iid": statistics.fmean(differences),
                "paired_mean_auc_delta_bootstrap_95": [mean_low, mean_high],
                "sobol_auc_sd": statistics.stdev(auc_by_sampler["sobol"]),
                "iid_auc_sd": statistics.stdev(auc_by_sampler["iid"]),
                "nonmonotone_readout_seed_count": nonmonotone,
                **variance,
            }
        )

    for row in results:
        interval = row["log_variance_ratio_bootstrap_95"]
        mean_interval = row["paired_mean_auc_delta_bootstrap_95"]
        row["joint_lower_spread_nonworse_mean_candidate"] = bool(
            interval[1] < 0.0 and mean_interval[0] >= 0.0
        )
    return results


def _sign(value: float, tolerance: float = 1e-12) -> int:
    if value > tolerance:
        return 1
    if value < -tolerance:
        return -1
    return 0


def _scramble_count_stability(
    records: Sequence[dict[str, Any]],
    *,
    stability_counts: Sequence[int],
    diagnostic_seed: int,
) -> list[dict[str, Any]]:
    max_budget = max(int(record["budget"]["limit"]) for record in records)
    scales = sorted(
        {
            float(record["uncertainty_profile"]["posterior_sd_scale"])
            for record in records
        }
    )
    lookup = {_record_key(record): record for record in records}
    all_seeds = sorted({int(record["seeds"]["exploration_seed"]) for record in records})
    counts = sorted({int(value) for value in stability_counts if value <= len(all_seeds)})
    if not counts or counts[-1] != len(all_seeds):
        counts.append(len(all_seeds))

    output: list[dict[str, Any]] = []
    for scale in scales:
        differences_by_seed = {
            seed: float(
                bool(lookup[(scale, "sobol", max_budget, seed)]["outcome"]["readout_success"])
            )
            - float(
                bool(lookup[(scale, "iid", max_budget, seed)]["outcome"]["readout_success"])
            )
            for seed in all_seeds
        }
        full_delta = statistics.fmean(differences_by_seed.values())
        order_generator = torch.Generator().manual_seed(
            _stable_seed(f"order:{diagnostic_seed}:{scale}")
        )
        permutation = torch.randperm(len(all_seeds), generator=order_generator).tolist()
        ordered_seeds = [all_seeds[index] for index in permutation]
        order_digest = hashlib.sha256(
            json.dumps(ordered_seeds, separators=(",", ":")).encode()
        ).hexdigest()

        for count in counts:
            cumulative = [differences_by_seed[seed] for seed in ordered_seeds[:count]]
            cumulative_delta = statistics.fmean(cumulative)
            cumulative_low, cumulative_high = _bootstrap_mean_interval(
                cumulative,
                seed=_stable_seed(f"cumulative:{diagnostic_seed}:{scale}:{count}"),
                samples=5_000,
            )

            subset_deltas: list[float] = []
            approximate_widths: list[float] = []
            subset_iterations = 1 if count == len(all_seeds) else SUBSET_SAMPLES
            subset_generator = torch.Generator().manual_seed(
                _stable_seed(f"subsets:{diagnostic_seed}:{scale}:{count}")
            )
            full_vector = [differences_by_seed[seed] for seed in all_seeds]
            for _ in range(subset_iterations):
                if count == len(all_seeds):
                    subset = full_vector
                else:
                    indices = torch.randperm(
                        len(full_vector), generator=subset_generator
                    )[:count].tolist()
                    subset = [full_vector[index] for index in indices]
                subset_deltas.append(statistics.fmean(subset))
                approximate_widths.append(
                    2.0
                    * 1.959963984540054
                    * (statistics.stdev(subset) if len(subset) > 1 else 0.0)
                    / math.sqrt(len(subset))
                )

            absolute_errors = [abs(value - full_delta) for value in subset_deltas]
            full_sign = _sign(full_delta)
            sign_disagreement_rate = statistics.fmean(
                float(_sign(value) != full_sign) for value in subset_deltas
            )
            median_absolute_error = statistics.median(absolute_errors)
            cumulative_half_width = (cumulative_high - cumulative_low) / 2.0
            discordant_pairs_observed = sum(value != 0.0 for value in cumulative)
            output.append(
                {
                    "posterior_sd_scale": scale,
                    "budget": max_budget,
                    "n_randomization_replicates": count,
                    "nested_order_seed": diagnostic_seed,
                    "nested_order_digest": order_digest,
                    "nested_cumulative_delta": cumulative_delta,
                    "nested_cumulative_bootstrap_95": [
                        cumulative_low,
                        cumulative_high,
                    ],
                    "full_replicate_delta_reference": full_delta,
                    "subset_resamples": subset_iterations,
                    "subset_delta_median": statistics.median(subset_deltas),
                    "subset_delta_p05_p95": [
                        _quantile(subset_deltas, 0.05),
                        _quantile(subset_deltas, 0.95),
                    ],
                    "subset_median_absolute_error_vs_full": median_absolute_error,
                    "subset_sign_disagreement_rate_vs_full": (
                        sign_disagreement_rate
                    ),
                    "subset_median_normal_approx_95_width": statistics.median(
                        approximate_widths
                    ),
                    "engineering_stability_rule": {
                        "ci_half_width_at_most_10pp": cumulative_half_width <= 0.10,
                        "subset_median_absolute_error_at_most_5pp": (
                            median_absolute_error <= 0.05
                        ),
                        "at_least_one_discordant_pair": (
                            discordant_pairs_observed > 0
                        ),
                        "adequate": (
                            cumulative_half_width <= 0.10
                            and median_absolute_error <= 0.05
                            and discordant_pairs_observed > 0
                        ),
                        "degenerate_bootstrap_guard": (
                            "all-zero paired differences cannot pass because the "
                            "ordinary bootstrap would otherwise have zero width"
                        ),
                    },
                    "interpretation": (
                        "finite-sample diagnostic; nested counts are correlated "
                        "and do not constitute independent tests"
                    ),
                }
            )
    return output


def summarize(
    records: Sequence[dict[str, Any]],
    *,
    sd_scales: Sequence[float],
    budgets: Sequence[int],
    seed_ids: Sequence[int],
    stability_counts: Sequence[int],
    diagnostic_seed: int,
    precision_extension_initial_replicates: int | None = None,
) -> dict[str, Any]:
    quality = validate_records(
        records,
        sd_scales=sd_scales,
        budgets=budgets,
        seed_ids=seed_ids,
    )
    cells = _cell_summary(records)
    paired = _paired_comparisons(records)
    curves = _curve_stability(records, budgets)
    convergence = _scramble_count_stability(
        records,
        stability_counts=stability_counts,
        diagnostic_seed=diagnostic_seed,
    )
    max_budget = max(int(value) for value in budgets)
    primary = next(
        row
        for row in paired
        if math.isclose(float(row["posterior_sd_scale"]), PRIMARY_SD_SCALE)
        and int(row["budget"]) == max_budget
    )
    primary_low, primary_high = primary["paired_seed_bootstrap_95"]
    primary_p = float(primary["exact_two_sided_mcnemar_p"])
    if primary_low > 0.0 and primary_p < 0.05:
        mean_effect = "sobol_positive"
    elif primary_high < 0.0 and primary_p < 0.05:
        mean_effect = "iid_positive"
    else:
        mean_effect = "inconclusive"

    primary_convergence = next(
        row
        for row in convergence
        if math.isclose(float(row["posterior_sd_scale"]), PRIMARY_SD_SCALE)
        and int(row["n_randomization_replicates"]) == len(seed_ids)
    )
    default_curve = next(
        row
        for row in curves
        if math.isclose(float(row["posterior_sd_scale"]), PRIMARY_SD_SCALE)
    )
    design: dict[str, Any] = {
        "task": "role_lock_d4",
        "target": [2, 3, 4, 1],
        "samplers": list(SAMPLERS),
        "posterior_sd_scales": [float(value) for value in sd_scales],
        "lm_node_eval_budgets": [int(value) for value in budgets],
        "exploration_seed_ids": [int(value) for value in seed_ids],
        "independent_randomization_unit": "exploration_seed",
        "records_expected": (
            len(SAMPLERS) * len(sd_scales) * len(budgets) * len(seed_ids)
        ),
        "primary_endpoint": {
            "posterior_sd_scale": PRIMARY_SD_SCALE,
            "budget": max_budget,
            "metric": "readout_success",
            "estimand": "P(Sobol success) - P(IID success)",
        },
        "sensitivity_multiplicity": (
            "McNemar p-values Holm-adjusted across all cells and, "
            "separately, across max-budget noise profiles"
        ),
    }
    if precision_extension_initial_replicates is not None:
        initial_replicates = int(precision_extension_initial_replicates)
        checkpoint_counts = [initial_replicates]
        while checkpoint_counts[-1] < len(seed_ids):
            checkpoint_counts.append(
                min(len(seed_ids), checkpoint_counts[-1] * 2)
            )
        record_lookup = {_record_key(record): record for record in records}
        ordered_seeds = sorted(int(seed) for seed in seed_ids)
        checkpoints: list[dict[str, Any]] = []
        for count in checkpoint_counts:
            selected_seeds = ordered_seeds[:count]
            pairs = [
                (
                    int(
                        record_lookup[
                            (PRIMARY_SD_SCALE, "sobol", max_budget, seed)
                        ]["outcome"]["readout_success"]
                    ),
                    int(
                        record_lookup[
                            (PRIMARY_SD_SCALE, "iid", max_budget, seed)
                        ]["outcome"]["readout_success"]
                    ),
                )
                for seed in selected_seeds
            ]
            sobol_only = sum(sobol == 1 and iid == 0 for sobol, iid in pairs)
            iid_only = sum(sobol == 0 and iid == 1 for sobol, iid in pairs)
            differences = [float(sobol - iid) for sobol, iid in pairs]
            checkpoint_low, checkpoint_high = _bootstrap_mean_interval(
                differences,
                seed=_stable_seed(f"extension-checkpoint:{count}"),
            )
            checkpoints.append(
                {
                    "paired_replicates": count,
                    "seed_ids": [selected_seeds[0], selected_seeds[-1]],
                    "iid_success_count": sum(iid for _sobol, iid in pairs),
                    "sobol_success_count": sum(sobol for sobol, _iid in pairs),
                    "success_delta_sobol_minus_iid": statistics.fmean(
                        differences
                    ),
                    "paired_seed_bootstrap_95": [
                        checkpoint_low,
                        checkpoint_high,
                    ],
                    "sobol_only": sobol_only,
                    "iid_only": iid_only,
                    "exact_two_sided_mcnemar_p": _exact_mcnemar_p(
                        sobol_only, iid_only
                    ),
                }
            )
        design["precision_extension"] = {
            "initial_paired_replicates": int(
                precision_extension_initial_replicates
            ),
            "final_paired_replicates": len(seed_ids),
            "additional_paired_replicates": (
                len(seed_ids) - int(precision_extension_initial_replicates)
            ),
            "trigger": (
                "predeclared engineering precision rule failed at the initial "
                "replicate count"
            ),
            "sequential_inference_boundary": (
                "nominal final p-value and CI are not anytime-valid; the initial "
                "64-replicate endpoint was already directionally significant"
            ),
            "checkpoint_order": "ascending exploration_seed execution blocks",
            "actual_extension_checkpoints": checkpoints,
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "record_type": "validated_summary",
        "design": design,
        "data_quality": quality,
        "cells": cells,
        "paired_comparisons": paired,
        "primary_endpoint": primary,
        "curve_stability": curves,
        "scramble_count_stability": convergence,
        "decision": {
            "primary_mean_effect": mean_effect,
            "primary_full_replicates_engineering_adequate": bool(
                primary_convergence["engineering_stability_rule"]["adequate"]
            ),
            "default_noise_joint_lower_spread_candidate": bool(
                default_curve["joint_lower_spread_nonworse_mean_candidate"]
            ),
            "claim_scope": (
                "conditional randomized-scramble behavior on oracle-aligned "
                "Role-Lock D4; not natural-language reasoning or general QMC theory"
            ),
        },
    }


def _percent(value: float) -> str:
    return f"{100.0 * value:.1f}%"


def render_report(summary: dict[str, Any]) -> str:
    primary = summary["primary_endpoint"]
    scale = float(primary["posterior_sd_scale"])
    budget = int(primary["budget"])
    cells = {
        (
            float(row["posterior_sd_scale"]),
            str(row["sampler"]),
            int(row["budget"]),
        ): row
        for row in summary["cells"]
    }
    iid_primary = cells[(scale, "iid", budget)]
    sobol_primary = cells[(scale, "sobol", budget)]
    low, high = primary["paired_seed_bootstrap_95"]
    decision = summary["decision"]["primary_mean_effect"]
    if decision == "sobol_positive":
        headline = "Primaryではrandomized Sobol優位を支持した。"
    elif decision == "iid_positive":
        headline = "PrimaryではIID優位を支持し、Sobol優位は否定された。"
    else:
        headline = "PrimaryではIIDとrandomized Sobolの平均性能差は未確定だった。"

    precision_extension = summary["design"].get("precision_extension")
    ci_label = "nominal 95%" if precision_extension is not None else "95%"
    title = (
        "# QMC-BMGS D4 Primary precision extension"
        if precision_extension is not None
        else "# QMC-BMGS D4 posterior-noise sweep"
    )
    lines = [
        title,
        "",
        "## 結論",
        "",
        headline,
        (
            f"事前固定した SD scale={scale:g}, LM cap={budget} のreadout成功率は、"
            f"IID {_percent(iid_primary['readout_success_rate'])} "
            f"({iid_primary['readout_success_count']}/{iid_primary['paired_replicates']}), "
            f"Sobol {_percent(sobol_primary['readout_success_rate'])} "
            f"({sobol_primary['readout_success_count']}/{sobol_primary['paired_replicates']})。"
        ),
        (
            "paired delta (Sobol - IID) は "
            f"{_percent(primary['success_delta_sobol_minus_iid'])}, "
            f"{ci_label} bootstrap CI [{_percent(low)}, {_percent(high)}], "
            f"exact McNemar p={primary['exact_two_sided_mcnemar_p']:.4g}。"
        ),
        "",
        "これはoracle-aligned static-token embeddingを使ったRole-Lock D4上の"
        "条件付き結果であり、自然言語reasoningや一般的なQMC優位の証明ではない。",
        "",
        "## 実験契約",
        "",
        "- Task: `PROBE -> DERIVE -> COMMIT -> EOS`（terminal-only reward +5）",
        "- Fixed: aligned embedding strata、候補10、LM prior、reward、pruning off",
        "- Factor: IID / node-local `scramble=True` Sobol（coverage gate、cluster "
        "quantile、action perturbationをまとめて置換）",
        "- Posterior SD scales: "
        + ", ".join(f"{value:g}" for value in summary["design"]["posterior_sd_scales"]),
        "- LM caps: "
        + ", ".join(str(value) for value in summary["design"]["lm_node_eval_budgets"]),
        f"- Independent paired randomization replicates: {len(summary['design']['exploration_seed_ids'])}",
        f"- Total runs: {summary['design']['records_expected']}",
        "",
        "SD scaleはlearned meanを変えず、uncertainty proxyの標準偏差だけを倍率変更する。"
        "このproxyは非定常TD targetに対する探索量で、厳密なBayesian posteriorではない。",
        "",
        "## 全successセル",
        "",
        "| SD scale | LM cap | IID | Sobol | Delta | Paired 95% CI | "
        f"Holm p (all {len(summary['paired_comparisons'])}) |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    if precision_extension is not None:
        insertion = lines.index("## 全successセル")
        provenance_lines = [
            "## Precision-extension provenance",
            "",
            (
                f"初期n={precision_extension['initial_paired_replicates']}で"
                "事前precision ruleを満たさなかったため、Primaryセルだけ"
                f"n={precision_extension['final_paired_replicates']}へ延長した。"
                "これは効果方向ではなくCI幅で発火したsequential extension。"
            ),
            "nominalな最終p値/CIはanytime-validではない。ただし初期64-replicate "
            "PrimaryでもIID方向は既に有意で、延長は効果量精度を上げるために行った。",
            "",
            "| Actual checkpoint n | IID success | Sobol success | Delta | Nominal 95% CI | McNemar p |",
            "|---:|---:|---:|---:|---:|---:|",
        ]
        for checkpoint in precision_extension["actual_extension_checkpoints"]:
            checkpoint_low, checkpoint_high = checkpoint[
                "paired_seed_bootstrap_95"
            ]
            provenance_lines.append(
                "| "
                f"{checkpoint['paired_replicates']} | "
                f"{checkpoint['iid_success_count']} | "
                f"{checkpoint['sobol_success_count']} | "
                f"{_percent(checkpoint['success_delta_sobol_minus_iid'])} | "
                f"[{_percent(checkpoint_low)}, {_percent(checkpoint_high)}] | "
                f"{checkpoint['exact_two_sided_mcnemar_p']:.4g} |"
            )
        provenance_lines.extend(
            [
                "",
                "このcheckpoint表は実際のseed追加順。後段のstability表は"
                "diagnostic seedで固定shuffleしたnested subsetで、別の診断である。",
                "",
            ]
        )
        lines[insertion:insertion] = provenance_lines
    for row in summary["paired_comparisons"]:
        row_scale = float(row["posterior_sd_scale"])
        row_budget = int(row["budget"])
        iid = cells[(row_scale, "iid", row_budget)]
        sobol = cells[(row_scale, "sobol", row_budget)]
        row_low, row_high = row["paired_seed_bootstrap_95"]
        lines.append(
            "| "
            f"{row_scale:g} | {row_budget} | "
            f"{_percent(iid['readout_success_rate'])} | "
            f"{_percent(sobol['readout_success_rate'])} | "
            f"{_percent(row['success_delta_sobol_minus_iid'])} | "
            f"[{_percent(row_low)}, {_percent(row_high)}] | "
            f"{row['holm_adjusted_p_all_sensitivity_cells']:.4g} |"
        )

    if len(summary["paired_comparisons"]) > 1:
        comparison_note = (
            "低budgetセルは同じseedのnested sensitivityで、独立した"
            f"{len(summary['paired_comparisons'])}実験ではない。"
            "表のHolm値は探索的な多重比較を保守的に可視化するためのもの。"
        )
    else:
        comparison_note = (
            "この表は事前Primaryの1セルだけで、多重なsensitivity検定ではない。"
        )
    full_replicates = len(summary["design"]["exploration_seed_ids"])
    if summary["decision"]["primary_full_replicates_engineering_adequate"]:
        stability_result = (
            f"n={full_replicates}で事前engineering precision ruleを満たした。"
        )
    else:
        stability_result = (
            f"n={full_replicates}でも満たさない場合は「差なし」ではなく"
            "scramble不足と読む。"
        )
    lines.extend(
        [
            "",
            comparison_note,
            "",
            "## Scramble replicate数の安定性（最大LM cap）",
            "",
            "| SD scale | n | Nested delta | Nested 95% CI | Subset median abs error | Sign disagreement (tie含む) | Adequate? |",
            "|---:|---:|---:|---:|---:|---:|:---:|",
        ]
    )
    for row in summary["scramble_count_stability"]:
        row_low, row_high = row["nested_cumulative_bootstrap_95"]
        adequate = "yes" if row["engineering_stability_rule"]["adequate"] else "no"
        lines.append(
            "| "
            f"{row['posterior_sd_scale']:g} | "
            f"{row['n_randomization_replicates']} | "
            f"{_percent(row['nested_cumulative_delta'])} | "
            f"[{_percent(row_low)}, {_percent(row_high)}] | "
            f"{_percent(row['subset_median_absolute_error_vs_full'])} | "
            f"{_percent(row['subset_sign_disagreement_rate_vs_full'])} | {adequate} |"
        )
    lines.extend(
        [
            "",
            "`Adequate`は、nested paired-delta CI half-width <=10pp かつ"
            "random-subset median absolute error <=5pp、かつdiscordant pairを"
            "1件以上観測、という事前engineering rule。" + stability_result,
        ]
    )
    if len(summary["design"]["lm_node_eval_budgets"]) > 1:
        lines.extend(
            [
                "",
                "## Success-budget AUCの平均とrun間spread",
                "",
                "| SD scale | IID mean AUC | Sobol mean AUC | Delta (95% CI) | Variance ratio S/I | log-ratio 95% CI | Joint candidate? |",
                "|---:|---:|---:|---:|---:|---:|:---:|",
            ]
        )
        for row in summary["curve_stability"]:
            ratio = row["variance_ratio_sobol_over_iid"]
            ratio_text = "NA" if ratio is None else f"{ratio:.3f}"
            var_low, var_high = row["log_variance_ratio_bootstrap_95"]
            mean_low, mean_high = row["paired_mean_auc_delta_bootstrap_95"]
            support = (
                "yes"
                if row["joint_lower_spread_nonworse_mean_candidate"]
                else "no"
            )
            lines.append(
                "| "
                f"{row['posterior_sd_scale']:g} | "
                f"{row['iid_mean_auc']:.3f} | {row['sobol_mean_auc']:.3f} | "
                f"{row['mean_auc_delta_sobol_minus_iid']:+.3f} "
                f"([{mean_low:+.3f}, {mean_high:+.3f}]) | {ratio_text} | "
                f"[{var_low:+.3f}, {var_high:+.3f}] | "
                f"{support} |"
            )
        lines.extend(
            [
                "",
                "binary successのSDはp(1-p)に従うため、分散低下の根拠には使っていない。"
                "AUCのspreadも一般的RQMC定理ではなく、このadaptive search上の経験的"
                "run-to-run stabilityである。`Joint candidate`はlog variance-ratio CIが"
                "0未満かつAUC mean-delta CIが0以上のときだけ立てる探索的フラグで、"
                "分散検定による支持判定ではない。readout curveの非単調seed数もJSONへ保存した。",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "Success-budget AUC spreadは省略した。LM capが1点だけの場合、AUCは"
                "binary successの定数倍にすぎず、独立な分散指標にならない。",
            ]
        )
    lines.extend(["", "## Computeとデータ品質", ""])
    cost = primary["mean_cost_delta_sobol_minus_iid"]
    lines.extend(
        [
            f"Primaryの平均cost delta (Sobol - IID): verifier {cost['verifier_requests']:+.2f}, "
            f"edge selections {cost['edge_selections']:+.2f}, "
            f"full-prefix tokens {cost['full_prefix_tokens']:+.2f}。"
            "LM node capが同じでも、これらの二次費用は同一とは限らない。",
            "",
            f"Validation: **{summary['data_quality']['status']}**",
            "",
        ]
    )
    for name, passed in summary["data_quality"]["checks"].items():
        lines.append(f"- {'PASS' if passed else 'FAIL'}: `{name}`")
    if summary["decision"]["primary_full_replicates_engineering_adequate"]:
        precision_line = (
            f"- Primaryのn={full_replicates}は事前precision ruleを満たした。"
            "このendpointのscramble追加は不要。"
        )
    else:
        precision_line = (
            f"- Primaryのn={full_replicates}は事前precision ruleを満たさない。"
            "差なしとは読まず、必要ならPrimaryセルだけ128/256へ延長する。"
        )
    lines.extend(
        [
            "",
            "## Claim boundary / 次の判断",
            "",
            "- Primary CIが0を跨ぐなら、IIDとSobolが同等とは言わず未確定とする。",
            precision_line,
            "- ここで良い結果が出ても、static token embeddingがreasoning roleを捉える"
            "とは限らない。contextual/chunk action embeddingは次の独立段階。",
            "- QMCの効果とsemantic strataの効果は混ぜない。後者のpositive controlはD3で"
            "扱い済みで、このD4はaligned strataに条件付けている。",
            "- sampler差はnode-local uniform engine全体の置換であり、posterior "
            "perturbation単独のQMC効果ではない。",
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
    if not values or any(item <= 0 for item in values) or len(set(values)) != len(values):
        raise argparse.ArgumentTypeError("expected unique comma-separated positive ints")
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
    records = run_sweep(
        sd_scales=scales,
        budgets=budgets,
        seed_start=0,
        seeds_count=2,
        verifier_budget_multiplier=16.0,
        progress_every=0,
    )
    repeat = run_sweep(
        sd_scales=scales,
        budgets=budgets,
        seed_start=0,
        seeds_count=2,
        verifier_budget_multiplier=16.0,
        progress_every=0,
    )
    assert [row["deterministic_digest"] for row in records] == [
        row["deterministic_digest"] for row in repeat
    ]
    summary = summarize(
        records,
        sd_scales=scales,
        budgets=budgets,
        seed_ids=[0, 1],
        stability_counts=[1, 2],
        diagnostic_seed=313,
    )
    assert summary["data_quality"]["status"] == "PASS"
    assert len(records) == 8
    assert summary["primary_endpoint"]["posterior_sd_scale"] == 1.0
    assert "QMC-BMGS D4" in render_report(summary)
    json.dumps(summary, allow_nan=False)
    print("d4 noise sweep self-test: PASS")


def main() -> None:
    base = Path.cwd() / "artifacts" / "work" / "qmc_bmgs_d4_noise_sweep"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--sd-scales", default="0.5,1.0,2.0")
    parser.add_argument("--budgets", default="64,128,256,384")
    parser.add_argument("--seed-start", type=int, default=0)
    parser.add_argument("--seeds", type=int, default=64)
    parser.add_argument("--stability-counts", default="8,16,32,64")
    parser.add_argument("--diagnostic-seed", type=int, default=313)
    parser.add_argument("--verifier-budget-multiplier", type=float, default=16.0)
    parser.add_argument("--progress-every", type=int, default=64)
    parser.add_argument(
        "--resume-from",
        type=Path,
        help=(
            "Reuse matching validated records from an existing JSONL and run "
            "only missing factorial cells"
        ),
    )
    parser.add_argument(
        "--precision-extension-initial-replicates",
        type=int,
        help=(
            "Annotate a single-cell run as the precision-triggered extension "
            "of an earlier paired-replicate count"
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
    if args.seed_start < 0 or args.seeds <= 0:
        parser.error("--seed-start must be nonnegative and --seeds positive")
    if args.verifier_budget_multiplier < 1.0:
        parser.error("--verifier-budget-multiplier must be at least 1")
    if args.progress_every < 0:
        parser.error("--progress-every must be nonnegative")

    scales = _parse_csv_floats(args.sd_scales)
    budgets = _parse_csv_ints(args.budgets)
    stability_counts = _parse_csv_ints(args.stability_counts)
    seed_count = args.seeds
    if args.smoke:
        scales = [0.5, 1.0, 2.0]
        budgets = [32, 64]
        seed_count = 4
        stability_counts = [2, 4]

    if not any(math.isclose(value, PRIMARY_SD_SCALE) for value in scales):
        parser.error("--sd-scales must include the predeclared primary scale 1.0")
    if args.precision_extension_initial_replicates is not None:
        initial = args.precision_extension_initial_replicates
        if initial <= 0 or initial >= seed_count:
            parser.error(
                "--precision-extension-initial-replicates must be positive and "
                "smaller than --seeds"
            )
        if len(scales) != 1 or len(budgets) != 1:
            parser.error("precision-extension annotation requires one scale and cap")
    seed_ids = list(range(args.seed_start, args.seed_start + seed_count))
    expected_keys = {
        (float(scale), sampler, int(budget), int(seed))
        for scale in scales
        for sampler in SAMPLERS
        for budget in budgets
        for seed in seed_ids
    }
    existing_records: list[dict[str, Any]] = []
    if args.resume_from is not None:
        loaded = _read_jsonl(args.resume_from)
        existing_records = [
            record for record in loaded if _record_key(record) in expected_keys
        ]
        if len({_record_key(record) for record in existing_records}) != len(
            existing_records
        ):
            parser.error("--resume-from contains duplicate matching records")
        print(
            json.dumps(
                {
                    "resume_source": str(args.resume_from),
                    "matching_records_reused": len(existing_records),
                    "source_records_ignored": len(loaded) - len(existing_records),
                }
            ),
            flush=True,
        )
    records = run_sweep(
        sd_scales=scales,
        budgets=budgets,
        seed_start=args.seed_start,
        seeds_count=seed_count,
        verifier_budget_multiplier=args.verifier_budget_multiplier,
        progress_every=args.progress_every,
        existing_records=existing_records,
    )
    summary = summarize(
        records,
        sd_scales=scales,
        budgets=budgets,
        seed_ids=seed_ids,
        stability_counts=stability_counts,
        diagnostic_seed=args.diagnostic_seed,
        precision_extension_initial_replicates=(
            args.precision_extension_initial_replicates
        ),
    )
    if summary["data_quality"]["status"] != "PASS":
        raise RuntimeError(
            "D4 data-quality validation failed: "
            + ", ".join(summary["data_quality"]["failures"])
        )

    _write_jsonl(args.runs_jsonl, records)
    _write_json(args.summary_json, summary)
    args.report_md.parent.mkdir(parents=True, exist_ok=True)
    args.report_md.write_text(render_report(summary), encoding="utf-8")

    # Reload the durable JSONL and independently rebuild the deterministic
    # summary.  This catches serialization loss and accidental NaN coercion.
    reloaded = _read_jsonl(args.runs_jsonl)
    rebuilt = summarize(
        reloaded,
        sd_scales=scales,
        budgets=budgets,
        seed_ids=seed_ids,
        stability_counts=stability_counts,
        diagnostic_seed=args.diagnostic_seed,
        precision_extension_initial_replicates=(
            args.precision_extension_initial_replicates
        ),
    )
    if rebuilt != summary:
        raise AssertionError("summary recomputation from durable JSONL diverged")

    print(
        json.dumps(
            {
                "runs": len(records),
                "validation": summary["data_quality"]["status"],
                "primary": summary["primary_endpoint"],
                "runs_jsonl": str(args.runs_jsonl),
                "summary_json": str(args.summary_json),
                "report_md": str(args.report_md),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
