#!/usr/bin/env python3
"""Independent post-hoc audit of the frozen Countdown calibration grid.

The implementation intentionally does not import the calibration runner.  It
reconstructs coverage, paired source comparisons, and scale-ratio invariants
from the compact JSONL shards alone.  The frozen selected configuration is
checked against an oracle embedded in this source file rather than against the
artifact's own decision rows.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import statistics
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "qmc-bmgs-countdown-calibration-adversarial-audit/v1"
RECORD_SCHEMA_VERSION = "qmc-bmgs-countdown-calibration-grid-record/v1"
MANIFEST_SCHEMA_VERSION = "qmc-bmgs-countdown-calibration-grid-manifest/v1"
IID_METHOD = "matched_iid_thompson_8"
QMC_METHOD = "qmc_thompson_8"
METHODS = (IID_METHOD, QMC_METHOD)
PROVIDERS = ("anthropic", "openai")
SEEDS = tuple(range(2048, 2176))
CONFIGURATIONS = (
    ("prior_0p1__sd_0p25", 0.1, 0.25),
    ("prior_0p1__sd_0p5", 0.1, 0.5),
    ("prior_0p1__sd_1", 0.1, 1.0),
    ("prior_0p5__sd_0p25", 0.5, 0.25),
    ("prior_0p5__sd_0p5", 0.5, 0.5),
    ("prior_0p5__sd_1", 0.5, 1.0),
    ("prior_1__sd_0p25", 1.0, 0.25),
    ("prior_1__sd_0p5", 1.0, 0.5),
    ("prior_1__sd_1", 1.0, 1.0),
)
CONFIG_BY_ID = {
    config_id: {
        "config_id": config_id,
        "posterior_sd_scale": posterior_sd_scale,
        "prior_bonus": prior_bonus,
    }
    for config_id, prior_bonus, posterior_sd_scale in CONFIGURATIONS
}
TASKS = {
    "e1e2fdaf480a626266300f4d9b583e847065458be604d6b9cff2483e4478b5c6": {
        "inputs": [1, 1, 1, 1, 1, 1],
        "max_steps": 5,
        "ruleset_id": "countdown-d6-positive-int-exact-division/v1",
        "target": 6,
        "task_id": "countdown_d6_e1e2fdaf480a6262",
    },
    "a2c80cfde3aaeb372fa8c2628e7f61760370f6184c2ab838368578e4b504ea7d": {
        "inputs": [1, 1, 1, 1, 1, 2],
        "max_steps": 5,
        "ruleset_id": "countdown-d6-positive-int-exact-division/v1",
        "target": 10,
        "task_id": "countdown_d6_a2c80cfde3aaeb37",
    },
}
PROPOSAL_BEHAVIOR_DIGESTS = {
    "anthropic": (
        "9eaee49f6e100d26100b10b0eb8d9f9ba75f74cb0109d2b25634590117682868"
    ),
    "openai": (
        "529b7dd51458cda3a6899a7b0b406dd8880317b413f39fe0fc08786c4eff8862"
    ),
}
CLAIM_BOUNDARY = (
    "Post-hoc compact-record audit of a development grid. Intervals are "
    "reported only within each fixed provider/task stratum across exploration "
    "seeds; pooled provider/task output is descriptive and carries no interval "
    "or p-value. These are not preregistered confirmatory tests. Shared tasks, "
    "matched exploration-seed labels with distinct source streams, and "
    "development-time selection preclude causal, task-transfer, "
    "provider-superiority, or QMC-superiority claims. Compact trajectory "
    "digests cannot prove successful-run pre-hit action-prefix identity."
)

# This oracle is deliberately external to the artifact and its summary.  It
# makes silent replacement of the frozen selected shard observable.
FROZEN_SELECTED_CONFIG_ORACLE: dict[str, Any] = {
    "artifact_manifest_deterministic_digest": (
        "49d8a0465c89584f18b4242d329ffc58482453f8f5f6d5b6af87e91041414270"
    ),
    "config": {
        "config_id": "prior_1__sd_1",
        "posterior_sd_scale": 1.0,
        "prior_bonus": 1.0,
    },
    "record_count": 1024,
    "shard_filename": "search_records_prior_1__sd_1.jsonl",
    "shard_sha256": (
        "53d01ea7d2586b4d0d5430a4035ca28b6467f257517c8d2956775abbe2bd5e5a"
    ),
    "success_counts": {
        "all": 173,
        "anthropic/target_10/matched_iid_thompson_8": 2,
        "anthropic/target_10/qmc_thompson_8": 4,
        "anthropic/target_6/matched_iid_thompson_8": 17,
        "anthropic/target_6/qmc_thompson_8": 16,
        "matched_iid_thompson_8": 95,
        "openai/target_10/matched_iid_thompson_8": 2,
        "openai/target_10/qmc_thompson_8": 4,
        "openai/target_6/matched_iid_thompson_8": 74,
        "openai/target_6/qmc_thompson_8": 54,
        "qmc_thompson_8": 78,
    },
}

PAIRED_METRICS = {
    "exact_success": ("exact_success_any",),
    "exact_terminal_count": ("diagnostics", "exact_terminal_count"),
    "mean_chosen_prior_mass": ("diagnostics", "mean_chosen_prior_mass"),
    "mean_normalized_prior_rank": (
        "diagnostics",
        "mean_normalized_prior_rank",
    ),
    "mean_prior_regret": ("diagnostics", "mean_prior_regret"),
    "noise_overrode_proposal_rate": (
        "diagnostics",
        "noise_overrode_proposal_rate",
    ),
    "positive_posterior_action_count": (
        "diagnostics",
        "positive_posterior_action_count",
    ),
    "positive_posterior_update_count": (
        "diagnostics",
        "positive_posterior_update_count",
    ),
    "root_jsd_from_proposal_prior": (
        "diagnostics",
        "root_jsd_from_proposal_prior",
    ),
    "root_top_set_visit_fraction": (
        "diagnostics",
        "root_top_set_visit_fraction",
    ),
    "root_unique_arms": ("diagnostics", "root_unique_arms"),
    "root_visit_entropy": ("diagnostics", "root_visit_entropy"),
    "success_auc": ("diagnostics", "success_auc"),
    "top_set_retention": ("diagnostics", "top_set_retention"),
    "unique_edge_count": ("diagnostics", "unique_edge_count"),
    "unique_terminal_trace_count": (
        "diagnostics",
        "unique_terminal_trace_count",
    ),
}


class AuditError(ValueError):
    """The compact evidence is structurally invalid or incomplete."""


def _reject_json_constant(value: str) -> None:
    raise AuditError(f"non-finite JSON constant: {value}")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AuditError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _strict_json(text: str) -> Any:
    return json.loads(
        text,
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_json_constant,
    )


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode()).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _record_digest(record: Mapping[str, Any]) -> str:
    payload = json.loads(json.dumps(record))
    payload.pop("deterministic_digest", None)
    payload.get("usage", {}).pop("wall_time_s", None)
    return _sha256_json(payload)


def _path(record: Mapping[str, Any], keys: Sequence[str]) -> Any:
    value: Any = record
    for key in keys:
        if not isinstance(value, Mapping) or key not in value:
            raise AuditError(f"record is missing metric path {'/'.join(keys)}")
        value = value[key]
    return value


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AuditError(f"{label} is not numeric")
    result = float(value)
    if not math.isfinite(result):
        raise AuditError(f"{label} is not finite")
    return result


def _normal_descriptive_interval(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        raise AuditError("cannot summarize an empty paired sample")
    mean = statistics.fmean(values)
    sample_sd = statistics.stdev(values) if len(values) > 1 else 0.0
    standard_error = sample_sd / math.sqrt(len(values))
    radius = 1.959963984540054 * standard_error
    return {
        "mean_qmc_minus_iid": mean,
        "n": len(values),
        "normal_95_interval": [mean - radius, mean + radius],
        "sample_sd": sample_sd,
        "standard_error": standard_error,
    }


def _descriptive_summary(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        raise AuditError("cannot summarize an empty paired sample")
    return {
        "mean_qmc_minus_iid": statistics.fmean(values),
        "n": len(values),
        "sample_sd": statistics.stdev(values) if len(values) > 1 else 0.0,
    }


def _discordance_counts(
    *,
    iid_only: int,
    qmc_only: int,
    both_success: int,
    neither: int,
) -> dict[str, int]:
    return {
        "both_success": both_success,
        "discordant_total": iid_only + qmc_only,
        "iid_only": iid_only,
        "neither": neither,
        "qmc_only": qmc_only,
    }


def _exact_mcnemar(
    *,
    iid_only: int,
    qmc_only: int,
    both_success: int,
    neither: int,
) -> dict[str, Any]:
    counts = (iid_only, qmc_only, both_success, neither)
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in counts
    ):
        raise AuditError("McNemar counts must be non-negative integers")
    discordant = iid_only + qmc_only
    if discordant == 0:
        p_value = 1.0
    else:
        tail = sum(
            math.comb(discordant, index)
            for index in range(min(iid_only, qmc_only) + 1)
        ) / (2**discordant)
        p_value = min(1.0, 2.0 * tail)
    return {
        **_discordance_counts(
            iid_only=iid_only,
            qmc_only=qmc_only,
            both_success=both_success,
            neither=neither,
        ),
        "two_sided_exact_p": p_value,
    }


def _expected_record_keys() -> set[tuple[str, str, int, str]]:
    return {
        (provider, task_fingerprint, seed, method)
        for provider in PROVIDERS
        for task_fingerprint in TASKS
        for seed in SEEDS
        for method in METHODS
    }


def _validate_task(record: Mapping[str, Any]) -> str:
    task = record.get("task")
    if not isinstance(task, Mapping):
        raise AuditError("record task is not an object")
    fingerprint = task.get("task_fingerprint")
    if fingerprint not in TASKS:
        raise AuditError(f"unexpected task fingerprint: {fingerprint!r}")
    expected = TASKS[str(fingerprint)]
    for key, expected_value in expected.items():
        if task.get(key) != expected_value:
            raise AuditError(
                f"task {fingerprint} has unexpected {key}: {task.get(key)!r}"
            )
    return str(fingerprint)


def _validate_success_fields(record: Mapping[str, Any]) -> None:
    terminal_success = record.get("terminal_success")
    if (
        not isinstance(terminal_success, list)
        or len(terminal_success) != 8
        or any(not isinstance(value, bool) for value in terminal_success)
    ):
        raise AuditError("terminal_success must contain eight booleans")
    exact_success = record.get("exact_success_any")
    if not isinstance(exact_success, bool) or exact_success != any(terminal_success):
        raise AuditError("exact_success_any disagrees with terminal_success")
    diagnostics = record.get("diagnostics")
    if not isinstance(diagnostics, Mapping):
        raise AuditError("record diagnostics is not an object")
    cumulative: list[bool] = []
    seen = False
    for success in terminal_success:
        seen = seen or success
        cumulative.append(seen)
    if diagnostics.get("success_by_verifier") != cumulative:
        raise AuditError("success_by_verifier is not cumulative terminal success")
    expected_first = next(
        (index for index, success in enumerate(cumulative, start=1) if success),
        9,
    )
    if diagnostics.get("first_exact_verifier") != expected_first:
        raise AuditError("first_exact_verifier disagrees with terminal success")
    observed_auc = _number(diagnostics.get("success_auc"), "success_auc")
    expected_auc = sum(cumulative) / len(cumulative)
    if not math.isclose(observed_auc, expected_auc, abs_tol=1e-15):
        raise AuditError("success_auc disagrees with cumulative success")


def _validate_record(
    record: Mapping[str, Any],
    *,
    config_id: str,
) -> tuple[str, str, int, str]:
    if record.get("schema_version") != RECORD_SCHEMA_VERSION:
        raise AuditError("unexpected compact record schema")
    if record.get("claim_role") != "offline_calibration_development_only":
        raise AuditError("record has an unexpected claim role")
    if record.get("deterministic_digest") != _record_digest(record):
        raise AuditError("compact record deterministic digest mismatch")
    if record.get("calibration_config") != CONFIG_BY_ID[config_id]:
        raise AuditError(f"record calibration config disagrees with {config_id}")

    provider = record.get("provider")
    if provider not in PROVIDERS:
        raise AuditError(f"unexpected provider: {provider!r}")
    if record.get("proposal_behavior_digest") != PROPOSAL_BEHAVIOR_DIGESTS[provider]:
        raise AuditError(f"proposal behavior digest mismatch for {provider}")
    task_fingerprint = _validate_task(record)
    seed = record.get("seed")
    if isinstance(seed, bool) or seed not in SEEDS:
        raise AuditError(f"unexpected exploration seed: {seed!r}")
    method = record.get("method")
    if method not in METHODS:
        raise AuditError(f"unexpected method: {method!r}")

    method_config = record.get("method_config")
    if not isinstance(method_config, Mapping):
        raise AuditError("method_config is not an object")
    expected_config = CONFIG_BY_ID[config_id]
    if (
        method_config.get("prior_bonus") != expected_config["prior_bonus"]
        or method_config.get("posterior_sd_scale")
        != expected_config["posterior_sd_scale"]
    ):
        raise AuditError("method_config calibration values disagree with shard")
    expected_source = "iid" if method == IID_METHOD else "sobol"
    if method_config.get("selected_perturbation_source") != expected_source:
        raise AuditError("method label disagrees with selected source")
    if not isinstance(record.get("bank_digest"), str):
        raise AuditError("record has no bank digest")
    if not isinstance(record.get("trajectory_digest"), str):
        raise AuditError("record has no trajectory digest")
    _validate_success_fields(record)
    for metric, path in PAIRED_METRICS.items():
        value = _path(record, path)
        if metric == "exact_success":
            if not isinstance(value, bool):
                raise AuditError("exact success metric is not boolean")
        else:
            _number(value, metric)
    return str(provider), task_fingerprint, int(seed), str(method)


def _validate_and_index(
    records_by_config: Mapping[str, Sequence[Mapping[str, Any]]],
) -> tuple[
    dict[
        tuple[str, str, str, int, str],
        Mapping[str, Any],
    ],
    dict[str, Any],
]:
    if set(records_by_config) != set(CONFIG_BY_ID):
        missing = sorted(set(CONFIG_BY_ID) - set(records_by_config))
        extra = sorted(set(records_by_config) - set(CONFIG_BY_ID))
        raise AuditError(f"shard config mismatch: missing={missing}, extra={extra}")
    expected_keys = _expected_record_keys()
    indexed: dict[
        tuple[str, str, str, int, str],
        Mapping[str, Any],
    ] = {}
    per_config: dict[str, int] = {}
    per_method = {method: 0 for method in METHODS}
    per_provider = {provider: 0 for provider in PROVIDERS}
    per_task = {task_fingerprint: 0 for task_fingerprint in TASKS}
    banks: dict[tuple[str, int], set[str]] = {}

    for config_id, _, _ in CONFIGURATIONS:
        shard_keys: set[tuple[str, str, int, str]] = set()
        records = records_by_config[config_id]
        for record in records:
            key = _validate_record(record, config_id=config_id)
            if key in shard_keys:
                raise AuditError(f"duplicate record in {config_id}: {key}")
            shard_keys.add(key)
            provider, task_fingerprint, seed, method = key
            indexed[(config_id, provider, task_fingerprint, seed, method)] = record
            per_method[method] += 1
            per_provider[provider] += 1
            per_task[task_fingerprint] += 1
            banks.setdefault((task_fingerprint, seed), set()).add(
                str(record["bank_digest"])
            )
        if shard_keys != expected_keys:
            missing = sorted(expected_keys - shard_keys)
            extra = sorted(shard_keys - expected_keys)
            raise AuditError(
                f"coverage mismatch in {config_id}: "
                f"missing={missing[:3]}, extra={extra[:3]}"
            )
        per_config[config_id] = len(records)

    bank_mismatches = sum(len(digests) != 1 for digests in banks.values())
    if bank_mismatches:
        raise AuditError(
            f"{bank_mismatches} task/seed blocks changed perturbation bank"
        )
    expected_total = (
        len(CONFIG_BY_ID)
        * len(PROVIDERS)
        * len(TASKS)
        * len(SEEDS)
        * len(METHODS)
    )
    if len(indexed) != expected_total:
        raise AuditError("indexed record count does not close")
    return indexed, {
        "common_bank_task_seed_blocks": len(banks),
        "common_bank_task_seed_mismatches": bank_mismatches,
        "expected_records": expected_total,
        "observed_records": len(indexed),
        "pass": True,
        "records_by_config": per_config,
        "records_by_method": per_method,
        "records_by_provider": per_provider,
        "records_by_task_fingerprint": per_task,
        "seeds": {
            "count": len(SEEDS),
            "end_inclusive": SEEDS[-1],
            "start": SEEDS[0],
        },
    }


def _paired_summary(
    pairs: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
    *,
    sampler_inference: bool,
) -> dict[str, Any]:
    if not pairs:
        raise AuditError("paired summary received no records")
    deltas = {metric: [] for metric in PAIRED_METRICS}
    both = iid_only = qmc_only = neither = 0
    bank_mismatches = 0
    for iid, qmc in pairs:
        if iid["bank_digest"] != qmc["bank_digest"]:
            bank_mismatches += 1
        iid_success = bool(iid["exact_success_any"])
        qmc_success = bool(qmc["exact_success_any"])
        if iid_success and qmc_success:
            both += 1
        elif iid_success:
            iid_only += 1
        elif qmc_success:
            qmc_only += 1
        else:
            neither += 1
        for metric, path in PAIRED_METRICS.items():
            iid_value = float(_path(iid, path))
            qmc_value = float(_path(qmc, path))
            deltas[metric].append(qmc_value - iid_value)
    if bank_mismatches:
        raise AuditError("paired IID/QMC records did not share banks")
    summary = {
        "common_bank_mismatches": bank_mismatches,
        "metric_deltas": {
            metric: (
                _normal_descriptive_interval(values)
                if sampler_inference
                else _descriptive_summary(values)
            )
            for metric, values in sorted(deltas.items())
        },
        "pairs": len(pairs),
        "sampler_inference": {
            "performed": sampler_inference,
            "scope": (
                "fixed_provider_task_across_exploration_seeds"
                if sampler_inference
                else "none_dependent_provider_task_rows_pooled_descriptively"
            ),
        },
    }
    discordance = {
        "iid_only": iid_only,
        "qmc_only": qmc_only,
        "both_success": both,
        "neither": neither,
    }
    if sampler_inference:
        summary["mcnemar_exact_success"] = _exact_mcnemar(**discordance)
    else:
        summary["descriptive_success_discordance"] = _discordance_counts(
            **discordance
        )
    return summary


def _paired_results(
    indexed: Mapping[
        tuple[str, str, str, int, str],
        Mapping[str, Any],
    ],
) -> dict[str, Any]:
    strata: list[dict[str, Any]] = []
    pooled: list[dict[str, Any]] = []
    for config_id, _, _ in CONFIGURATIONS:
        pooled_pairs: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
        for provider in PROVIDERS:
            for task_fingerprint, task in TASKS.items():
                pairs = [
                    (
                        indexed[
                            (
                                config_id,
                                provider,
                                task_fingerprint,
                                seed,
                                IID_METHOD,
                            )
                        ],
                        indexed[
                            (
                                config_id,
                                provider,
                                task_fingerprint,
                                seed,
                                QMC_METHOD,
                            )
                        ],
                    )
                    for seed in SEEDS
                ]
                pooled_pairs.extend(pairs)
                strata.append(
                    {
                        "calibration_config": CONFIG_BY_ID[config_id],
                        "provider": provider,
                        "summary": _paired_summary(
                            pairs,
                            sampler_inference=True,
                        ),
                        "task_fingerprint": task_fingerprint,
                        "target": task["target"],
                    }
                )
        pooled.append(
            {
                "calibration_config": CONFIG_BY_ID[config_id],
                "scope": "two_providers_x_two_tasks_equal_cell_pool",
                "summary": _paired_summary(
                    pooled_pairs,
                    sampler_inference=False,
                ),
            }
        )
    return {
        "delta_direction": "qmc_minus_iid",
        "stratum_interval_method": (
            "mean_plus_or_minus_1.959963984540054_times_paired_sample_se"
        ),
        "pooled_inference": (
            "not_performed_because_provider_task_rows_reuse_task_seed_banks"
        ),
        "pooled_by_config": pooled,
        "strata": strata,
    }


def _kappa(config_id: str) -> Fraction:
    config = CONFIG_BY_ID[config_id]
    return Fraction(str(config["prior_bonus"])) / Fraction(
        str(config["posterior_sd_scale"])
    )


def _equal_kappa_invariants(
    indexed: Mapping[
        tuple[str, str, str, int, str],
        Mapping[str, Any],
    ],
) -> dict[str, Any]:
    by_kappa: dict[Fraction, list[str]] = {}
    for config_id in CONFIG_BY_ID:
        by_kappa.setdefault(_kappa(config_id), []).append(config_id)
    groups: list[dict[str, Any]] = []
    all_pass = True
    comparison_keys = [
        (provider, task_fingerprint, seed, method)
        for provider in PROVIDERS
        for task_fingerprint in TASKS
        for seed in SEEDS
        for method in METHODS
    ]
    for ratio, config_ids in sorted(by_kappa.items()):
        if len(config_ids) < 2:
            continue
        comparisons: list[dict[str, Any]] = []
        for first_id, second_id in itertools.combinations(config_ids, 2):
            first_hit_matches = 0
            success_path_matches = 0
            exact_success_matches = 0
            terminal_vector_matches = 0
            trajectory_matches = 0
            no_hit_pairs = 0
            no_hit_trajectory_matches = 0
            divergent_trajectory_pairs = 0
            divergent_trajectory_hit_pairs = 0
            for provider, task_fingerprint, seed, method in comparison_keys:
                first = indexed[
                    (first_id, provider, task_fingerprint, seed, method)
                ]
                second = indexed[
                    (second_id, provider, task_fingerprint, seed, method)
                ]
                first_success = bool(first["exact_success_any"])
                second_success = bool(second["exact_success_any"])
                exact_success_matches += first_success == second_success
                first_hit_matches += (
                    first["diagnostics"]["first_exact_verifier"]
                    == second["diagnostics"]["first_exact_verifier"]
                )
                success_path_matches += (
                    first["diagnostics"]["success_by_verifier"]
                    == second["diagnostics"]["success_by_verifier"]
                )
                terminal_vector_matches += (
                    first["terminal_success"] == second["terminal_success"]
                )
                same_trajectory = (
                    first["trajectory_digest"] == second["trajectory_digest"]
                )
                trajectory_matches += same_trajectory
                if not first_success and not second_success:
                    no_hit_pairs += 1
                    no_hit_trajectory_matches += same_trajectory
                if not same_trajectory:
                    divergent_trajectory_pairs += 1
                    divergent_trajectory_hit_pairs += (
                        first_success or second_success
                    )
            pair_count = len(comparison_keys)
            invariant_pass = (
                exact_success_matches == pair_count
                and first_hit_matches == pair_count
                and success_path_matches == pair_count
                and no_hit_trajectory_matches == no_hit_pairs
                and divergent_trajectory_pairs
                == divergent_trajectory_hit_pairs
            )
            all_pass = all_pass and invariant_pass
            comparisons.append(
                {
                    "config_ids": [first_id, second_id],
                    "cumulative_success_path_match_count": success_path_matches,
                    "divergent_full_trajectory_count": (
                        divergent_trajectory_pairs
                    ),
                    "divergent_full_trajectory_with_hit_count": (
                        divergent_trajectory_hit_pairs
                    ),
                    "exact_success_match_count": exact_success_matches,
                    "first_exact_verifier_match_count": first_hit_matches,
                    "full_trajectory_digest_match_count": trajectory_matches,
                    "invariant_pass": invariant_pass,
                    "no_hit_full_trajectory_match_count": (
                        no_hit_trajectory_matches
                    ),
                    "no_hit_pair_count": no_hit_pairs,
                    "pair_count": pair_count,
                    "terminal_success_vector_match_count": (
                        terminal_vector_matches
                    ),
                }
            )
        groups.append(
            {
                "comparisons": comparisons,
                "config_ids": config_ids,
                "kappa_prior_over_posterior_sd": (
                    f"{ratio.numerator}/{ratio.denominator}"
                ),
            }
        )
    return {
        "all_invariants_pass": all_pass,
        "groups": groups,
        "tested_invariants": [
            "exact_success_matches_within_equal_kappa",
            "first_exact_verifier_matches_within_equal_kappa",
            "cumulative_success_path_matches_within_equal_kappa",
            "full_trajectory_digest_matches_for_all_no_hit_runs",
            "full_trajectory_divergence_is_confined_to_hit_runs",
        ],
    }


def _success_counts(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    counts = {
        "all": 0,
        IID_METHOD: 0,
        QMC_METHOD: 0,
    }
    for provider in PROVIDERS:
        for target in (6, 10):
            for method in METHODS:
                counts[f"{provider}/target_{target}/{method}"] = 0
    for record in records:
        if not record["exact_success_any"]:
            continue
        provider = str(record["provider"])
        target = int(record["task"]["target"])
        method = str(record["method"])
        counts["all"] += 1
        counts[method] += 1
        counts[f"{provider}/target_{target}/{method}"] += 1
    return dict(sorted(counts.items()))


def _oracle_check(
    *,
    records_by_config: Mapping[str, Sequence[Mapping[str, Any]]],
    artifact_identity: Mapping[str, Any],
) -> dict[str, Any]:
    oracle = FROZEN_SELECTED_CONFIG_ORACLE
    selected_id = str(oracle["config"]["config_id"])
    observed = {
        "artifact_manifest_deterministic_digest": artifact_identity.get(
            "manifest_deterministic_digest"
        ),
        "config": CONFIG_BY_ID[selected_id],
        "record_count": len(records_by_config[selected_id]),
        "shard_filename": artifact_identity["shards"][selected_id]["filename"],
        "shard_sha256": artifact_identity["shards"][selected_id]["sha256"],
        "success_counts": _success_counts(records_by_config[selected_id]),
    }
    mismatches = [
        key
        for key in sorted(oracle)
        if observed.get(key) != oracle.get(key)
    ]
    return {
        "enforced": True,
        "expected": oracle,
        "mismatch_fields": mismatches,
        "observed": observed,
        "pass": not mismatches,
        "source": "module_embedded_external_oracle",
    }


def audit_record_sets(
    records_by_config: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    artifact_identity: Mapping[str, Any],
    enforce_frozen_oracle: bool = True,
) -> dict[str, Any]:
    """Audit already-loaded compact shards without runner aggregation code."""
    indexed, coverage = _validate_and_index(records_by_config)
    oracle = (
        _oracle_check(
            records_by_config=records_by_config,
            artifact_identity=artifact_identity,
        )
        if enforce_frozen_oracle
        else {
            "enforced": False,
            "pass": True,
            "source": "disabled_for_non_frozen_test_fixture",
        }
    )
    equal_kappa = _equal_kappa_invariants(indexed)
    status = (
        "PASS"
        if coverage["pass"]
        and oracle["pass"]
        and equal_kappa["all_invariants_pass"]
        else "FAIL"
    )
    payload = {
        "artifact_identity": artifact_identity,
        "audit_independence": {
            "artifact_decision_rows_read": False,
            "all_manifest_declared_file_bytes_verified": True,
            "artifact_summary_aggregation_read": False,
            "compact_shards_are_primary_evidence": True,
            "runner_module_imported": False,
        },
        "claim_boundary": CLAIM_BOUNDARY,
        "coverage": coverage,
        "equal_kappa_invariants": equal_kappa,
        "frozen_selected_config_oracle": oracle,
        "paired_source_comparison": _paired_results(indexed),
        "schema_version": SCHEMA_VERSION,
        "status": status,
    }
    return {**payload, "deterministic_digest": _sha256_json(payload)}


def _load_artifact(
    artifact_dir: Path,
) -> tuple[
    dict[str, list[Mapping[str, Any]]],
    dict[str, Any],
]:
    if artifact_dir.is_symlink():
        raise AuditError("artifact directory must not be a symlink")
    artifact_dir = artifact_dir.resolve()
    if not artifact_dir.is_dir():
        raise AuditError(f"artifact directory does not exist: {artifact_dir}")
    manifest_path = artifact_dir / "manifest.json"
    if manifest_path.is_symlink():
        raise AuditError("artifact manifest must not be a symlink")
    try:
        manifest = _strict_json(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise AuditError(f"cannot read artifact manifest: {exc}") from exc
    if not isinstance(manifest, Mapping):
        raise AuditError("artifact manifest is not a JSON object")
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise AuditError("unexpected artifact manifest schema")
    manifest_payload = {
        key: value
        for key, value in manifest.items()
        if key != "deterministic_digest"
    }
    if manifest.get("deterministic_digest") != _sha256_json(manifest_payload):
        raise AuditError("manifest deterministic digest mismatch")
    manifest_files = manifest.get("files")
    if not isinstance(manifest_files, Mapping):
        raise AuditError("manifest files is not an object")

    expected_shards = {
        config_id: f"search_records_{config_id}.jsonl"
        for config_id in CONFIG_BY_ID
    }
    expected_file_names = set(expected_shards.values()) | {
        "anthropic_proposal_rows.jsonl",
        "openai_proposal_rows.jsonl",
        "perturbation_banks.jsonl",
        "preregistration.json",
        "summary.json",
    }
    declared_names = set(manifest_files)
    observed_names = {
        path.name for path in artifact_dir.iterdir() if path.name != "manifest.json"
    }
    if declared_names != expected_file_names or observed_names != expected_file_names:
        raise AuditError(
            "artifact file closure does not match frozen grid: "
            f"manifest_missing={sorted(expected_file_names - declared_names)}, "
            f"manifest_extra={sorted(declared_names - expected_file_names)}, "
            f"directory_missing={sorted(expected_file_names - observed_names)}, "
            f"directory_extra={sorted(observed_names - expected_file_names)}"
        )

    parsed_shards: dict[str, list[Mapping[str, Any]]] = {}
    file_identity: dict[str, dict[str, Any]] = {}
    for filename in sorted(expected_file_names):
        path = artifact_dir / filename
        metadata = manifest_files.get(filename)
        if not isinstance(metadata, Mapping):
            raise AuditError(f"manifest has no metadata object for {filename}")
        if path.is_symlink() or not path.is_file():
            raise AuditError(f"artifact entry is not a regular file: {filename}")
        observed_metadata: dict[str, Any] = {
            "bytes": path.stat().st_size,
            "sha256": _sha256_file(path),
        }
        try:
            if path.suffix == ".jsonl":
                records: list[Mapping[str, Any]] = []
                record_count = 0
                with path.open(encoding="utf-8") as handle:
                    for line_number, line in enumerate(handle, start=1):
                        value = _strict_json(line)
                        if not isinstance(value, Mapping):
                            raise AuditError(
                                f"{filename}:{line_number} is not a JSON object"
                            )
                        record_count += 1
                        if filename in expected_shards.values():
                            records.append(value)
                observed_metadata["records"] = record_count
                if filename in expected_shards.values():
                    parsed_shards[filename] = records
            else:
                value = _strict_json(path.read_text(encoding="utf-8"))
                if not isinstance(value, Mapping):
                    raise AuditError(f"{filename} is not a JSON object")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise AuditError(f"cannot read {filename}: {exc}") from exc
        expected_metadata = {
            key: metadata.get(key) for key in observed_metadata
        }
        if observed_metadata != expected_metadata:
            raise AuditError(
                f"manifest metadata mismatch for {filename}: "
                f"observed={observed_metadata}, expected={expected_metadata}"
            )
        file_identity[filename] = observed_metadata

    records_by_config: dict[str, list[Mapping[str, Any]]] = {}
    shard_identity: dict[str, dict[str, Any]] = {}
    for config_id, _, _ in CONFIGURATIONS:
        filename = expected_shards[config_id]
        records = parsed_shards[filename]
        observed_metadata = file_identity[filename]
        records_by_config[config_id] = records
        shard_identity[config_id] = {
            "bytes": observed_metadata["bytes"],
            "filename": filename,
            "records": len(records),
            "sha256": observed_metadata["sha256"],
        }
    return records_by_config, {
        "artifact_locator": artifact_dir.name,
        "file_count": len(file_identity),
        "files": file_identity,
        "manifest_deterministic_digest": manifest["deterministic_digest"],
        "manifest_sha256": _sha256_file(manifest_path),
        "shards": shard_identity,
    }


def audit_artifact(artifact_dir: Path) -> dict[str, Any]:
    """Verify all frozen files, then independently audit compact search shards."""
    records_by_config, artifact_identity = _load_artifact(artifact_dir)
    return audit_record_sets(
        records_by_config,
        artifact_identity=artifact_identity,
        enforce_frozen_oracle=True,
    )


def _write_report(report: Mapping[str, Any], output: Path | None) -> None:
    payload = _canonical_json(report) + "\n"
    if output is None:
        sys.stdout.write(payload)
    else:
        output.write_text(payload)


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifact-dir",
        required=True,
        type=Path,
        help="frozen calibration artifact directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="optional output path outside the artifact; default is stdout",
    )
    args = parser.parse_args(argv)
    if args.output is not None and _is_within(args.output, args.artifact_dir):
        parser.error("--output must not mutate the audited artifact directory")
    try:
        report = audit_artifact(args.artifact_dir)
    except AuditError as exc:
        failure_payload = {
            "artifact_locator": args.artifact_dir.name,
            "claim_boundary": CLAIM_BOUNDARY,
            "error": str(exc),
            "schema_version": SCHEMA_VERSION,
            "status": "INVALID_ARTIFACT",
        }
        report = {
            **failure_payload,
            "deterministic_digest": _sha256_json(failure_payload),
        }
        _write_report(report, args.output)
        return 2
    _write_report(report, args.output)
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
