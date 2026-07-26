#!/usr/bin/env python3
"""Preregistered prior/noise calibration grid on frozen Countdown snapshots.

This is an offline development diagnostic layered on the matched IID/Sobol
Thompson source ablation.  It varies only two scalar calibration parameters:

* proposal-probability bonus: 0.1, 0.5, 1.0
* posterior standard-deviation scale: 0.25, 0.5, 1.0

Every grid cell shares the same fresh node-local perturbation banks.  The
decision rule is frozen in code before reading the grid outcome and selects a
configuration, not a perturbation source.  No provider client, credential, or
network call is used.
"""

from __future__ import annotations

import argparse
import math
import os
import platform
import shutil
import statistics
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import torch

from qmc_bmgs.benchmarks.countdown import (
    CountdownAction,
    CountdownState,
    CountdownTask,
)
from qmc_bmgs.experiments.countdown_anthropic_dev import (
    DEV_TASKS,
    SEARCH_BUDGET,
    THOMPSON_SIMULATIONS,
    ProposalSnapshot,
    SearchContext,
    SearchStopped,
    _NodeStats,
    _canonical_json,
    _sha256_json,
    _state_sort_key,
    _validate_search_record,
)
from qmc_bmgs.experiments.countdown_thompson_source_ablation import (
    FROZEN_SOURCES,
    MAX_ACTIONS,
    METHODS,
    METHOD_SOURCE,
    SOURCE_NAMES,
    BankCursor,
    PerturbationBank,
    _action_digest,
    _argmax,
    _build_bank_record,
    _build_seed_plan,
    _bank_discrepancy_summary,
    _cell_summary,
    _deny_network,
    _expected_source_validation_receipt,
    _file_metadata,
    _file_sha256,
    _fake_snapshot,
    _load_copied_snapshots,
    _method_config as _source_method_config,
    _normal_transform_metadata,
    _path,
    _read_json,
    _read_jsonl,
    _run_diagnostics,
    _selection_margin,
    _snapshot_pairing_gate,
    _source_seed_identity,
    _task_from_dict,
    _top_indices,
    _validate_sources_without_mutation,
    _write_json,
    _write_jsonl,
    run_search as run_source_baseline,
)
from qmc_bmgs.records import canonical_record_digest


RECORD_SCHEMA_VERSION = "qmc-bmgs-countdown-calibration-grid-record/v1"
INTERNAL_SEARCH_SCHEMA_VERSION = (
    "qmc-bmgs-countdown-calibration-grid-internal-search/v1"
)
SUMMARY_SCHEMA_VERSION = "qmc-bmgs-countdown-calibration-grid-summary/v1"
MANIFEST_SCHEMA_VERSION = "qmc-bmgs-countdown-calibration-grid-manifest/v1"
EXPERIMENT_VERSION = "countdown-prior-noise-calibration-grid/v1"
DECISION_RULE_VERSION = "stable-both-source-both-provider/v1"

PRIOR_BONUSES = (0.1, 0.5, 1.0)
POSTERIOR_SD_SCALES = (0.25, 0.5, 1.0)
SEED_START = 2048
SEED_COUNT = 128
EXPLORATION_SEEDS = tuple(range(SEED_START, SEED_START + SEED_COUNT))
BASELINE_PRIOR_BONUS = 0.1
BASELINE_POSTERIOR_SD_SCALE = 1.0
SUCCESS_REGRESSION_TOLERANCE = 1.0 / SEED_COUNT
TOP_RETENTION_REGRESSION_TOLERANCE = 0.02
NORMALIZED_RANK_REGRESSION_TOLERANCE = 0.02
ROOT_ENTROPY_DELTA_MINIMUM = 0.02
UNIQUE_EDGE_DELTA_MINIMUM = 1.0
SOBOL_LOWER_FRACTION_MINIMUM = 0.95
PARENT_V2_SUMMARY_DIGEST = (
    "8e037efcba2cead9c78463ce6f026b517dd4a8c1a194958ad1b8060e4fb749d0"
)
PARENT_V2_MANIFEST_DIGEST = (
    "2f303018e67202824516a7fd84b32dc64492c6167ed6428f29283b23d610cb11"
)
PARENT_V2_BANK_SHA256 = (
    "2a30a8c90c3538cd378a860c02a9e544e8912fafbef81fadea0107e9591166ed"
)
PARENT_V2_RECORDS_SHA256 = (
    "4947f8d7f5e6fd131718680d1c92f767efc5dddac882a7094ff20ba107d160fe"
)
PREREGISTRATION_SCHEMA_VERSION = (
    "qmc-bmgs-countdown-calibration-grid-preregistration/v1"
)
PREREGISTRATION_FILENAME = "countdown_calibration_grid_v1.json"
ROOT = Path(__file__).resolve().parents[3]
PREREGISTRATION_PATH = ROOT / "docs" / "preregistrations" / PREREGISTRATION_FILENAME
DECISION_FREEZE_PATH = (
    ROOT
    / "docs"
    / "preregistrations"
    / "countdown_calibration_decision_freeze_v1.json"
)
DECISION_FREEZE_DIGEST = (
    "15de3ff8386d5839ba5e50c53baa0ef861b515f1d29aa985a67a114a7e02a72d"
)


def _float_label(value: float) -> str:
    return format(value, ".8g").replace(".", "p")


@dataclass(frozen=True)
class CalibrationConfig:
    prior_bonus: float
    posterior_sd_scale: float

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.prior_bonus)
            or self.prior_bonus <= 0.0
            or not math.isfinite(self.posterior_sd_scale)
            or self.posterior_sd_scale <= 0.0
        ):
            raise ValueError("calibration parameters must be finite and positive")

    @property
    def config_id(self) -> str:
        return (
            f"prior_{_float_label(self.prior_bonus)}"
            f"__sd_{_float_label(self.posterior_sd_scale)}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "config_id": self.config_id,
            "posterior_sd_scale": self.posterior_sd_scale,
            "prior_bonus": self.prior_bonus,
        }


GRID_CONFIGS = tuple(
    CalibrationConfig(prior_bonus, posterior_sd_scale)
    for prior_bonus in PRIOR_BONUSES
    for posterior_sd_scale in POSTERIOR_SD_SCALES
)
CONFIG_BY_ID = {config.config_id: config for config in GRID_CONFIGS}
BASELINE_CONFIG = CalibrationConfig(
    BASELINE_PRIOR_BONUS,
    BASELINE_POSTERIOR_SD_SCALE,
)

if len(CONFIG_BY_ID) != len(GRID_CONFIGS):
    raise AssertionError("calibration config identifiers are not unique")
if BASELINE_CONFIG.config_id not in CONFIG_BY_ID:
    raise AssertionError("baseline calibration config is not in the grid")


def _expected_preregistration() -> dict[str, Any]:
    return {
        "baseline_config_id": BASELINE_CONFIG.config_id,
        "claim_boundary": (
            "Development calibration on two frozen public tasks. The grid "
            "selects a source-robust configuration, not a winning perturbation "
            "source, and does not establish task transfer or QMC superiority."
        ),
        "decision_rule": {
            "eligibility": {
                "all_eight_cells_exact_success_count_minimum": 1,
                "all_provider_task_qmc_minus_iid_root_entropy_minimum": (
                    ROOT_ENTROPY_DELTA_MINIMUM
                ),
                "all_provider_task_qmc_minus_iid_unique_edges_minimum": (
                    UNIQUE_EDGE_DELTA_MINIMUM
                ),
                "all_task_sobol_lower_discrepancy_fraction_minimum": (
                    SOBOL_LOWER_FRACTION_MINIMUM
                ),
                "mean_normalized_prior_rank_vs_baseline_maximum_regression": (
                    NORMALIZED_RANK_REGRESSION_TOLERANCE
                ),
                "top_set_retention_vs_baseline_maximum_regression": (
                    TOP_RETENTION_REGRESSION_TOLERANCE
                ),
            },
            "no_eligible_status": "NO_STABLE_CALIBRATION_REGION",
            "rank_lexicographic": [
                "maximize_min_cell_exact_success_rate",
                "maximize_min_cell_success_auc",
                "maximize_min_cell_exact_terminal_count_mean",
                "minimize_max_provider_task_abs_qmc_minus_iid_success_delta",
                "maximize_min_provider_task_qmc_minus_iid_root_entropy",
                "minimize_log_distance_from_baseline",
                "minimize_prior_bonus",
                "minimize_posterior_sd_scale",
            ],
            "signed_source_success_delta_is_never_maximized": True,
            "version": DECISION_RULE_VERSION,
        },
        "experiment_version": EXPERIMENT_VERSION,
        "fresh_common_random_number_cohort": {
            "config_provider_and_method_excluded_from_seed_identity": True,
            "count": SEED_COUNT,
            "end_inclusive": EXPLORATION_SEEDS[-1],
            "shared_across_all_grid_cells": True,
            "start": SEED_START,
        },
        "grid": [config.to_dict() for config in GRID_CONFIGS],
        "methods": list(METHODS),
        "parent_v2_regression_oracle": {
            "bank_sha256": PARENT_V2_BANK_SHA256,
            "manifest_digest": PARENT_V2_MANIFEST_DIGEST,
            "records_sha256": PARENT_V2_RECORDS_SHA256,
            "summary_digest": PARENT_V2_SUMMARY_DIGEST,
        },
        "providers": {
            provider: dict(frozen) for provider, frozen in FROZEN_SOURCES.items()
        },
        "schema_version": PREREGISTRATION_SCHEMA_VERSION,
        "search_contract": {
            "gamma": 1.0,
            "no_pruning": True,
            "no_semantic_routing": True,
            "no_shaped_reward": True,
            "posterior_sd_formula": (
                "posterior_sd_scale/sqrt(visits+1)"
            ),
            "prior_component_formula": "prior_bonus*exp(prior_logp)",
            "search_budget": SEARCH_BUDGET.to_dict(),
            "simulations": THOMPSON_SIMULATIONS,
            "terminal_reward": "exact_1_or_0",
        },
        "tasks": [task.to_dict() for task in DEV_TASKS],
        "workload": {
            "paired_iid_qmc_blocks": (
                len(GRID_CONFIGS)
                * len(FROZEN_SOURCES)
                * len(DEV_TASKS)
                * SEED_COUNT
            ),
            "records": (
                len(GRID_CONFIGS)
                * len(FROZEN_SOURCES)
                * len(DEV_TASKS)
                * len(METHODS)
                * SEED_COUNT
            ),
        },
    }


def _load_and_validate_preregistration(path: Path) -> dict[str, Any]:
    observed = _read_json(path)
    expected = _expected_preregistration()
    if _canonical_json(observed) != _canonical_json(expected):
        raise AssertionError("calibration preregistration drifted")
    return observed


def _load_and_validate_decision_freeze(path: Path) -> dict[str, Any]:
    observed = _read_json(path)
    payload = {
        key: value
        for key, value in observed.items()
        if key != "deterministic_digest"
    }
    if (
        observed.get("schema_version")
        != "qmc-bmgs-countdown-calibration-decision-freeze/v1"
        or observed.get("deterministic_digest") != _sha256_json(payload)
        or observed.get("deterministic_digest") != DECISION_FREEZE_DIGEST
        or observed.get("selected_config") != CalibrationConfig(1.0, 1.0).to_dict()
        or observed.get("held_out_gate", {}).get("execution_authorized") is not False
    ):
        raise AssertionError("calibration decision freeze drifted")
    return observed


def _shard_filename(config: CalibrationConfig) -> str:
    return f"search_records_{config.config_id}.jsonl"


def _run_kernel(
    context: SearchContext,
    bank: PerturbationBank,
    *,
    selected_source: str,
    config: CalibrationConfig,
) -> tuple[str, dict[str, Any], dict[CountdownState, _NodeStats], int]:
    stats: dict[CountdownState, _NodeStats] = {}
    cursor = BankCursor(bank, selected_source)
    completed = 0
    positive_posterior_update_count = 0
    try:
        for simulation in range(THOMPSON_SIMULATIONS):
            state = context.task.initial_state
            actions: list[CountdownAction] = []
            states = [state]
            cumulative = 0.0
            path: list[tuple[CountdownState, int]] = []
            depth = 0
            while len(state) > 1:
                row = context.proposal(state)
                node = stats.setdefault(state, _NodeStats.create(len(row.actions)))
                context.charge_selection_and_edge(row)
                draw = cursor.draw(state, len(row.actions))
                probabilities = [math.exp(value) for value in row.prior_logp]
                posterior_sd = [
                    config.posterior_sd_scale / math.sqrt(visits + 1)
                    for visits in node.visits
                ]
                prior_component = [
                    config.prior_bonus * probability
                    for probability in probabilities
                ]
                base_values = [
                    mean + prior
                    for mean, prior in zip(node.means, prior_component)
                ]
                iid_values = [
                    base + sd * noise
                    for base, sd, noise in zip(
                        base_values, posterior_sd, draw["iid_normal"]
                    )
                ]
                sobol_values = [
                    base + sd * noise
                    for base, sd, noise in zip(
                        base_values, posterior_sd, draw["sobol_normal"]
                    )
                ]
                sampled_values = (
                    iid_values if selected_source == "iid" else sobol_values
                )
                action_index = _argmax(sampled_values)
                proposal_top = _top_indices(row.prior_logp)
                base_top = _top_indices(base_values)
                competition_rank = 1 + sum(
                    value > row.prior_logp[action_index]
                    for value in row.prior_logp
                )
                normalized_rank = (
                    (competition_rank - 1) / (len(row.actions) - 1)
                    if len(row.actions) > 1
                    else 0.0
                )
                child = context.transition(
                    state=state,
                    row=row,
                    action_index=action_index,
                    details={
                        "base_top_indices": list(base_top),
                        "base_values": base_values,
                        "calibration_config_id": config.config_id,
                        "chosen_in_proposal_top_set": action_index in proposal_top,
                        "chosen_prior_mass": probabilities[action_index],
                        "chosen_competition_rank": competition_rank,
                        "depth": depth,
                        "iid_choice_index": _argmax(iid_values),
                        "iid_full_vector_digest": draw[
                            "iid_full_vector_digest"
                        ],
                        "local_source_choice_disagreement": (
                            _argmax(iid_values) != _argmax(sobol_values)
                        ),
                        "node_visit_index": draw["node_visit_index"],
                        "noise_overrode_base_top_set": action_index not in base_top,
                        "noise_overrode_proposal_top_set": (
                            action_index not in proposal_top
                        ),
                        "normalized_prior_rank": normalized_rank,
                        "policy": "calibrated_matched_thompson_source",
                        "posterior_means_before": list(node.means),
                        "posterior_sd": posterior_sd,
                        "prior_component": prior_component,
                        "prior_regret": (
                            max(row.prior_logp) - row.prior_logp[action_index]
                        ),
                        "proposal_top_indices": list(proposal_top),
                        "sampled_values": sampled_values,
                        "selected_normal_values": list(draw["selected_normal"]),
                        "selected_source": selected_source,
                        "selected_uniform_values": list(draw["selected_uniform"]),
                        "selection_margin": _selection_margin(
                            sampled_values, action_index
                        ),
                        "simulation": simulation,
                        "sobol_choice_index": _argmax(sobol_values),
                        "sobol_full_vector_digest": draw[
                            "sobol_full_vector_digest"
                        ],
                        "visits_before": list(node.visits),
                    },
                    selection_scores_charged=len(row.actions),
                )
                actions.append(row.actions[action_index])
                states.append(child)
                path.append((state, action_index))
                cumulative += row.prior_logp[action_index]
                state = child
                depth += 1
            success = context.verify_terminal(
                actions=actions,
                states=states,
                cumulative_prior_logp=cumulative,
            )
            value = 1.0 if success else 0.0
            for visited_state, action_index in reversed(path):
                stats[visited_state].update(action_index, value)
                positive_posterior_update_count += int(success)
            completed += 1
    except SearchStopped as error:
        stop_reason = error.reason
    else:
        stop_reason = "completed_simulations"
    stats_payload = {
        _canonical_json(list(state)): {
            "m2": node.m2,
            "means": node.means,
            "visits": node.visits,
        }
        for state, node in sorted(
            stats.items(), key=lambda item: _state_sort_key(item[0])
        )
    }
    return (
        stop_reason,
        {
            "calibration_config": config.to_dict(),
            "completed_simulations": completed,
            "m2_used_for_selection": False,
            "normal_source": cursor.snapshot(),
            "posterior_sd_formula": (
                "posterior_sd_scale*inverse_sqrt_visits_plus_one/v1"
            ),
            "posterior_state_digest": _sha256_json(stats_payload),
        },
        stats,
        positive_posterior_update_count,
    )


def _method_config(
    selected_source: str,
    config: CalibrationConfig,
) -> dict[str, Any]:
    base = _source_method_config(selected_source)
    base["posterior_sd_formula"] = (
        "posterior_sd_scale*inverse_sqrt_visits_plus_one/v1"
    )
    base["posterior_sd_scale"] = config.posterior_sd_scale
    base["prior_bonus"] = config.prior_bonus
    return base


def _compact_diagnostics(diagnostics: Mapping[str, Any]) -> dict[str, Any]:
    wanted = {
        "by_depth",
        "cache_hit_rate",
        "duplicate_terminal_rate",
        "exact_terminal_count",
        "first_exact_verifier",
        "local_source_choice_disagreement_rate",
        "mean_chosen_prior_mass",
        "mean_normalized_prior_rank",
        "mean_prior_regret",
        "noise_overrode_base_rate",
        "noise_overrode_proposal_rate",
        "positive_posterior_action_count",
        "positive_posterior_update_count",
        "root_jsd_from_proposal_prior",
        "root_max_visit_share",
        "root_top_set_visit_fraction",
        "root_unique_arms",
        "root_visit_entropy",
        "simulations_before_first_positive_backup",
        "success_auc",
        "success_by_verifier",
        "top_set_retention",
        "unique_edge_count",
        "unique_terminal_trace_count",
    }
    if not wanted <= set(diagnostics):
        raise AssertionError("grid diagnostics are incomplete")
    return {key: diagnostics[key] for key in sorted(wanted)}


def run_grid_record(
    *,
    provider: str,
    task: CountdownTask,
    snapshot: ProposalSnapshot,
    bank: PerturbationBank,
    method: str,
    config: CalibrationConfig,
    expected_behavior_digest: str | None = None,
) -> dict[str, Any]:
    if provider not in FROZEN_SOURCES:
        raise ValueError("unknown frozen provider label")
    if method not in METHODS:
        raise ValueError("unknown matched Thompson method")
    expected_digest = (
        FROZEN_SOURCES[provider]["behavior_digest"]
        if expected_behavior_digest is None
        else expected_behavior_digest
    )
    if task != bank.task or snapshot.behavior_digest != expected_digest:
        raise ValueError("grid search input identity mismatch")
    selected_source = METHOD_SOURCE[method]
    context = SearchContext(
        task,
        snapshot,
        f"grid:{config.config_id}:{method}",
        bank.exploration_seed,
    )
    stop_reason, method_state, stats, positive_updates = _run_kernel(
        context,
        bank,
        selected_source=selected_source,
        config=config,
    )
    readout = context.readout()
    diagnostics = _run_diagnostics(context, stats, bank, positive_updates)
    full_payload = {
        "bank_digest": bank.deterministic_digest,
        "budget": SEARCH_BUDGET.to_dict(),
        "claim_role": "offline_calibration_development_only",
        "diagnostics": diagnostics,
        "exact_success_any": any(
            terminal["verification"]["success"] for terminal in context.terminals
        ),
        "method": method,
        "method_config": _method_config(selected_source, config),
        "method_state": method_state,
        "proposal_behavior_digest": snapshot.behavior_digest,
        "proposal_events": context.proposal_events,
        "provider": provider,
        "readout": readout,
        "rng": {
            "bank_digest": bank.deterministic_digest,
            "exploration_seed": bank.exploration_seed,
            "selected_source": selected_source,
            "version": EXPERIMENT_VERSION,
        },
        "schema_version": INTERNAL_SEARCH_SCHEMA_VERSION,
        "seed": bank.exploration_seed,
        "selection_events": context.selection_events,
        "stop_reason": stop_reason,
        "task": task.to_dict(),
        "terminals": context.terminals,
        "usage": context.ledger.snapshot(),
    }
    full_record = {
        **full_payload,
        "deterministic_digest": canonical_record_digest(full_payload),
    }
    _validate_search_record(
        full_record,
        snapshot,
        record_schema_version=INTERNAL_SEARCH_SCHEMA_VERSION,
    )
    event_core = {
        "proposal_events": context.proposal_events,
        "selection_events": context.selection_events,
        "terminals": context.terminals,
    }
    trajectory = [
        {
            "action_index": event["action_index"],
            "state": event["state"],
        }
        for event in context.selection_events
        if event["event"] == "edge_transition"
    ]
    terminal_success = [
        bool(terminal["verification"]["success"]) for terminal in context.terminals
    ]
    compact_payload = {
        "bank_digest": bank.deterministic_digest,
        "calibration_config": config.to_dict(),
        "claim_role": "offline_calibration_development_only",
        "diagnostics": _compact_diagnostics(diagnostics),
        "event_core_digest": _sha256_json(event_core),
        "exact_success_any": bool(full_record["exact_success_any"]),
        "full_search_record_digest": full_record["deterministic_digest"],
        "method": method,
        "method_config": _method_config(selected_source, config),
        "method_state": method_state,
        "proposal_behavior_digest": snapshot.behavior_digest,
        "provider": provider,
        "readout": readout,
        "schema_version": RECORD_SCHEMA_VERSION,
        "seed": bank.exploration_seed,
        "stop_reason": stop_reason,
        "task": task.to_dict(),
        "terminal_success": terminal_success,
        "trajectory_digest": _sha256_json(trajectory),
        "usage": context.ledger.snapshot(),
    }
    return {
        **compact_payload,
        "deterministic_digest": canonical_record_digest(compact_payload),
    }


PAIRED_METRIC_PATHS = {
    "exact_success": ("exact_success_any",),
    "exact_terminal_count": ("diagnostics", "exact_terminal_count"),
    "mean_normalized_prior_rank": (
        "diagnostics",
        "mean_normalized_prior_rank",
    ),
    "mean_prior_regret": ("diagnostics", "mean_prior_regret"),
    "noise_overrode_proposal_rate": (
        "diagnostics",
        "noise_overrode_proposal_rate",
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


def _mean(values: Sequence[float]) -> float:
    return statistics.fmean(values)


def _variance(values: Sequence[float]) -> float:
    return statistics.variance(values) if len(values) > 1 else 0.0


def _compact_pair_summary(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    by_seed: dict[int, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for record in records:
        seed = int(record["seed"])
        method = str(record["method"])
        if method in by_seed[seed]:
            raise AssertionError("duplicate method in calibration pair")
        by_seed[seed][method] = record
    if any(set(pair) != set(METHODS) for pair in by_seed.values()):
        raise AssertionError("calibration source pair is incomplete")

    both = iid_only = qmc_only = neither = 0
    deltas: dict[str, list[float]] = {
        metric: [] for metric in PAIRED_METRIC_PATHS
    }
    for pair in by_seed.values():
        iid = pair["matched_iid_thompson_8"]
        qmc = pair["qmc_thompson_8"]
        if iid["bank_digest"] != qmc["bank_digest"]:
            raise AssertionError("paired methods did not share a bank")
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
        for metric, path in PAIRED_METRIC_PATHS.items():
            deltas[metric].append(
                float(_path(qmc, path)) - float(_path(iid, path))
            )
    return {
        "common_random_number_bank_mismatches": 0,
        "discordance": {
            "both_success": both,
            "iid_only": iid_only,
            "neither": neither,
            "qmc_only": qmc_only,
        },
        "paired_blocks": len(by_seed),
        "paired_metrics": {
            metric: {
                "mean_qmc_minus_iid": _mean(values),
                "seed_variance_of_delta": _variance(values),
            }
            for metric, values in deltas.items()
        },
    }


def _cell(
    cells: Mapping[str, Any],
    config_id: str,
    provider: str,
    task_fingerprint: str,
    method: str,
) -> Mapping[str, Any]:
    return cells[config_id][provider][task_fingerprint][method]


def _pair(
    pairs: Mapping[str, Any],
    config_id: str,
    provider: str,
    task_fingerprint: str,
) -> Mapping[str, Any]:
    return pairs[config_id][provider][task_fingerprint]


def _decision_rows(
    *,
    cells: Mapping[str, Any],
    pairs: Mapping[str, Any],
    discrepancy: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    baseline_id = BASELINE_CONFIG.config_id
    for config in GRID_CONFIGS:
        config_id = config.config_id
        all_cells = [
            _cell(cells, config_id, provider, task.task_fingerprint, method)
            for provider in FROZEN_SOURCES
            for task in DEV_TASKS
            for method in METHODS
        ]
        provider_task_pairs = [
            _pair(pairs, config_id, provider, task.task_fingerprint)
            for provider in FROZEN_SOURCES
            for task in DEV_TASKS
        ]
        success_entry = all(cell["success_count"] >= 1 for cell in all_cells)
        discrepancy_pass = all(
            discrepancy[task.task_fingerprint]["comparison"][
                "fraction_sobol_lower"
            ]
            >= SOBOL_LOWER_FRACTION_MINIMUM
            for task in DEV_TASKS
        )
        entropy_deltas = [
            pair["paired_metrics"]["root_visit_entropy"][
                "mean_qmc_minus_iid"
            ]
            for pair in provider_task_pairs
        ]
        edge_deltas = [
            pair["paired_metrics"]["unique_edge_count"]["mean_qmc_minus_iid"]
            for pair in provider_task_pairs
        ]
        mechanism_pass = (
            discrepancy_pass
            and min(entropy_deltas) >= ROOT_ENTROPY_DELTA_MINIMUM
            and min(edge_deltas) >= UNIQUE_EDGE_DELTA_MINIMUM
        )
        retention_margins: list[float] = []
        rank_margins: list[float] = []
        for provider in FROZEN_SOURCES:
            for task in DEV_TASKS:
                for method in METHODS:
                    current = _cell(
                        cells,
                        config_id,
                        provider,
                        task.task_fingerprint,
                        method,
                    )
                    baseline = _cell(
                        cells,
                        baseline_id,
                        provider,
                        task.task_fingerprint,
                        method,
                    )
                    retention_margins.append(
                        current["metrics"]["top_set_retention"]["mean"]
                        - baseline["metrics"]["top_set_retention"]["mean"]
                    )
                    rank_margins.append(
                        current["metrics"]["mean_normalized_prior_rank"]["mean"]
                        - baseline["metrics"]["mean_normalized_prior_rank"]["mean"]
                    )
        proposal_pass = (
            min(retention_margins) >= -TOP_RETENTION_REGRESSION_TOLERANCE
            and max(rank_margins) <= NORMALIZED_RANK_REGRESSION_TOLERANCE
        )
        min_success_rate = min(cell["success_rate"] for cell in all_cells)
        min_success_auc = min(
            cell["metrics"]["success_auc"]["mean"] for cell in all_cells
        )
        min_terminal_count = min(
            cell["metrics"]["exact_terminal_count"]["mean"]
            for cell in all_cells
        )
        success_source_deltas = [
            pair["paired_metrics"]["exact_success"]["mean_qmc_minus_iid"]
            for pair in provider_task_pairs
        ]
        max_abs_source_delta = max(abs(value) for value in success_source_deltas)
        log_distance = abs(
            math.log(config.prior_bonus / BASELINE_CONFIG.prior_bonus)
        ) + abs(
            math.log(
                config.posterior_sd_scale
                / BASELINE_CONFIG.posterior_sd_scale
            )
        )
        eligible = success_entry and mechanism_pass and proposal_pass
        rank_key = [
            -min_success_rate,
            -min_success_auc,
            -min_terminal_count,
            max_abs_source_delta,
            -min(entropy_deltas),
            log_distance,
            config.prior_bonus,
            config.posterior_sd_scale,
        ]
        rows.append(
            {
                "calibration_config": config.to_dict(),
                "eligible": eligible,
                "eligibility": {
                    "mechanism_pass": mechanism_pass,
                    "proposal_preservation_pass": proposal_pass,
                    "terminal_feedback_entry_pass": success_entry,
                },
                "guardrail_observations": {
                    "max_normalized_rank_regression": max(rank_margins),
                    "min_qmc_minus_iid_root_entropy": min(entropy_deltas),
                    "min_qmc_minus_iid_unique_edges": min(edge_deltas),
                    "min_top_set_retention_delta": min(retention_margins),
                    "sobol_lower_discrepancy_pass": discrepancy_pass,
                },
                "rank_observations": {
                    "log_distance_from_baseline": log_distance,
                    "max_abs_qmc_minus_iid_success_delta": (
                        max_abs_source_delta
                    ),
                    "min_cell_exact_success_rate": min_success_rate,
                    "min_cell_exact_terminal_count_mean": min_terminal_count,
                    "min_cell_success_auc": min_success_auc,
                },
                "selection_sort_key_ascending": rank_key,
            }
        )
    eligible_rows = [row for row in rows if row["eligible"]]
    eligible_rows.sort(key=lambda row: row["selection_sort_key_ascending"])
    if eligible_rows:
        selected = eligible_rows[0]["calibration_config"]
        status = "CALIBRATION_CANDIDATE_FROZEN"
    else:
        selected = None
        status = "NO_STABLE_CALIBRATION_REGION"
    return rows, {
        "decision_rule_version": DECISION_RULE_VERSION,
        "eligible_config_count": len(eligible_rows),
        "selected_config": selected,
        "signed_source_success_delta_was_optimized": False,
        "status": status,
    }


def _aggregate(
    *,
    records: Sequence[Mapping[str, Any]],
    banks: Sequence[PerturbationBank],
    snapshots: Mapping[str, ProposalSnapshot],
    seed_plan_evidence: Mapping[str, Any],
    source_validation: Mapping[str, Any],
    preregistration: Mapping[str, Any],
    runtime_metadata: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    expected_records = (
        len(GRID_CONFIGS)
        * len(FROZEN_SOURCES)
        * len(DEV_TASKS)
        * len(EXPLORATION_SEEDS)
        * len(METHODS)
    )
    if len(records) != expected_records:
        raise AssertionError("calibration grid record count drifted")
    cells: dict[str, Any] = {}
    pairs: dict[str, Any] = {}
    for config in GRID_CONFIGS:
        cells[config.config_id] = {}
        pairs[config.config_id] = {}
        config_records = [
            record
            for record in records
            if record["calibration_config"]["config_id"] == config.config_id
        ]
        for provider in FROZEN_SOURCES:
            cells[config.config_id][provider] = {}
            pairs[config.config_id][provider] = {}
            for task in DEV_TASKS:
                task_records = [
                    record
                    for record in config_records
                    if record["provider"] == provider
                    and record["task"]["task_fingerprint"]
                    == task.task_fingerprint
                ]
                cells[config.config_id][provider][task.task_fingerprint] = {
                    method: _cell_summary(
                        [
                            record
                            for record in task_records
                            if record["method"] == method
                        ]
                    )
                    for method in METHODS
                }
                pairs[config.config_id][provider][task.task_fingerprint] = (
                    _compact_pair_summary(task_records)
                )
    discrepancy = _bank_discrepancy_summary(banks)
    decision_rows, decision = _decision_rows(
        cells=cells,
        pairs=pairs,
        discrepancy=discrepancy,
    )
    pairing_gate = _snapshot_pairing_gate(snapshots)
    pairing_gate.update(
        {
            "all_grid_cells_share_one_bank_cohort": True,
            "bank_records": len(banks),
            "credentials_present": False,
            "expected_records": expected_records,
            "missing_or_duplicate_records": 0,
            "network_or_provider_calls": 0,
            "paired_blocks": expected_records // len(METHODS),
            "per_run_fixed_compute": {
                "edge_selections": 40,
                "full_coordinates_read_per_source": 560,
                "full_points_read_per_source": 40,
                "posterior_updates": 40,
                "transitions": 40,
                "verifier_calls": 8,
            },
        }
    )
    runtime = (
        {
            "python_version": platform.python_version(),
            "torch_version": str(torch.__version__),
        }
        if runtime_metadata is None
        else dict(runtime_metadata)
    )
    if set(runtime) != {"python_version", "torch_version"}:
        raise ValueError("runtime metadata fields drifted")
    payload = {
        "artifact_role": "offline_calibration_development_evidence",
        "cells": cells,
        "claim_boundary": preregistration["claim_boundary"],
        "decision": decision,
        "decision_rows": decision_rows,
        "experiment_config": {
            "configs": [config.to_dict() for config in GRID_CONFIGS],
            "experiment_version": EXPERIMENT_VERSION,
            "methods": list(METHODS),
            "normal_transform": _normal_transform_metadata(),
            "preregistration_digest": _sha256_json(preregistration),
            "search_budget": SEARCH_BUDGET.to_dict(),
            "seed_count": SEED_COUNT,
            "seed_start": SEED_START,
            **runtime,
        },
        "estimand_scope": {
            "common_random_number_blocks": True,
            "provider_superiority": False,
            "qmc_superiority": False,
            "task_generalization": False,
        },
        "manipulation_check": {
            "root_star_discrepancy": discrepancy,
        },
        "paired_results": pairs,
        "pairing_gate": pairing_gate,
        "preregistration": dict(preregistration),
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "seed_plan": dict(seed_plan_evidence),
        "source_validation": dict(source_validation),
        "sources": {
            provider: {
                **FROZEN_SOURCES[provider],
                "copied_snapshot_behavior_digest": snapshots[
                    provider
                ].behavior_digest,
            }
            for provider in FROZEN_SOURCES
        },
        "tasks": {
            task.task_fingerprint: task.to_dict() for task in DEV_TASKS
        },
    }
    return {**payload, "deterministic_digest": _sha256_json(payload)}


def _validate_compact_record(
    record: Mapping[str, Any],
    snapshot: ProposalSnapshot,
    bank: PerturbationBank,
    config: CalibrationConfig,
) -> None:
    payload = {
        key: value
        for key, value in record.items()
        if key != "deterministic_digest"
    }
    method = record.get("method")
    source = METHOD_SOURCE.get(str(method))
    if (
        record.get("schema_version") != RECORD_SCHEMA_VERSION
        or record.get("deterministic_digest")
        != canonical_record_digest(payload)
        or record.get("calibration_config") != config.to_dict()
        or record.get("provider") not in FROZEN_SOURCES
        or method not in METHODS
        or record.get("proposal_behavior_digest") != snapshot.behavior_digest
        or record.get("bank_digest") != bank.deterministic_digest
        or record.get("seed") != bank.exploration_seed
        or record.get("task") != bank.task.to_dict()
        or record.get("method_config") != _method_config(str(source), config)
        or record.get("stop_reason") != "completed_simulations"
    ):
        raise AssertionError("calibration compact record identity drifted")
    method_state = record["method_state"]
    if (
        method_state["calibration_config"] != config.to_dict()
        or method_state["completed_simulations"] != THOMPSON_SIMULATIONS
        or method_state["m2_used_for_selection"] is not False
        or method_state["posterior_sd_formula"]
        != "posterior_sd_scale*inverse_sqrt_visits_plus_one/v1"
    ):
        raise AssertionError("calibration method state drifted")
    usage = record["usage"]
    expected_edges = THOMPSON_SIMULATIONS * (
        len(bank.task.initial_state) - 1
    )
    if (
        usage["usage"]["verifier_calls"] != THOMPSON_SIMULATIONS
        or usage["usage"]["edge_selections"] != expected_edges
        or usage["usage"]["transitions"] != expected_edges
        or usage["evaluation_only_calls"] != 1
        or usage["overshoot"] != 0
        or usage["exhausted_axes"] != ["verifier_calls"]
        or len(record["terminal_success"]) != THOMPSON_SIMULATIONS
        or len(record["diagnostics"]["success_by_verifier"])
        != THOMPSON_SIMULATIONS
        or record["diagnostics"]["exact_terminal_count"]
        != sum(record["terminal_success"])
        or bool(record["exact_success_any"])
        != any(record["terminal_success"])
    ):
        raise AssertionError("calibration per-run budget or reward did not close")
    normal_source = method_state["normal_source"]
    if (
        normal_source["bank_digest"] != bank.deterministic_digest
        or normal_source["selected_source"] != source
        or normal_source["full_points_read_per_source"] != expected_edges
        or normal_source["full_coordinates_read_per_source"]
        != expected_edges * MAX_ACTIONS
        or normal_source["used_action_coordinates"]
        != usage["usage"]["selection_action_scores"]
        or normal_source["padded_coordinates_per_source"]
        != expected_edges * MAX_ACTIONS
        - usage["usage"]["selection_action_scores"]
        or record["diagnostics"]["positive_posterior_update_count"]
        > expected_edges
    ):
        raise AssertionError("calibration perturbation accounting drifted")


def _expected_record_keys(config: CalibrationConfig) -> list[tuple[Any, ...]]:
    return [
        (
            provider,
            task.task_fingerprint,
            seed,
            method,
            config.config_id,
        )
        for provider in FROZEN_SOURCES
        for task in DEV_TASKS
        for seed in EXPLORATION_SEEDS
        for method in METHODS
    ]


def validate_artifact(
    artifact_dir: Path,
    *,
    require_replay_match: bool = True,
    verify_bank_transform: bool = False,
) -> dict[str, Any]:
    manifest = _read_json(artifact_dir / "manifest.json")
    manifest_payload = {
        key: value
        for key, value in manifest.items()
        if key != "deterministic_digest"
    }
    expected_files = {
        "anthropic_proposal_rows.jsonl",
        "openai_proposal_rows.jsonl",
        "perturbation_banks.jsonl",
        "preregistration.json",
        "summary.json",
        *(_shard_filename(config) for config in GRID_CONFIGS),
    }
    if (
        manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION
        or manifest.get("status") != "COMPLETE"
        or set(manifest.get("files", {})) != expected_files
        or manifest.get("deterministic_digest")
        != _sha256_json(manifest_payload)
    ):
        raise AssertionError("calibration artifact manifest drifted")
    for filename, expected in manifest["files"].items():
        path = artifact_dir / filename
        observed = _file_metadata(
            path,
            records=len(_read_jsonl(path)) if path.suffix == ".jsonl" else None,
        )
        if observed != expected:
            raise AssertionError(
                f"calibration byte manifest mismatch: {filename}"
            )

    preregistration = _load_and_validate_preregistration(
        artifact_dir / "preregistration.json"
    )
    snapshots = _load_copied_snapshots(artifact_dir)
    bank_records = _read_jsonl(artifact_dir / "perturbation_banks.jsonl")
    banks = tuple(
        PerturbationBank.from_record(
            record,
            verify_transform=verify_bank_transform,
        )
        for record in bank_records
    )
    bank_index = {
        (bank.task.task_fingerprint, bank.exploration_seed): bank
        for bank in banks
    }
    expected_bank_keys = [
        (task.task_fingerprint, seed)
        for task in DEV_TASKS
        for seed in EXPLORATION_SEEDS
    ]
    observed_bank_keys = [
        (bank.task.task_fingerprint, bank.exploration_seed) for bank in banks
    ]
    if observed_bank_keys != expected_bank_keys or len(bank_index) != len(banks):
        raise AssertionError("calibration perturbation bank coverage drifted")
    seed_plan, seed_plan_evidence = _build_seed_plan(
        DEV_TASKS, EXPLORATION_SEEDS
    )
    for bank in banks:
        for state in bank.states:
            actions = bank.task.legal_actions(state.state)
            for source_name in SOURCE_NAMES:
                identity = _source_seed_identity(
                    task=bank.task,
                    state=state.state,
                    exploration_seed=bank.exploration_seed,
                    action_digest=_action_digest(actions),
                    source=source_name,
                )
                expected_seed = seed_plan[_sha256_json(identity)]
                if getattr(state, f"{source_name}_seed") != expected_seed:
                    raise AssertionError("calibration bank seed plan drifted")

    all_records: list[dict[str, Any]] = []
    for config in GRID_CONFIGS:
        shard_path = artifact_dir / _shard_filename(config)
        records = _read_jsonl(shard_path)
        observed_keys = [
            (
                record["provider"],
                record["task"]["task_fingerprint"],
                record["seed"],
                record["method"],
                record["calibration_config"]["config_id"],
            )
            for record in records
        ]
        if observed_keys != _expected_record_keys(config):
            raise AssertionError(
                f"calibration shard pairing/order drifted: {config.config_id}"
            )
        replay_records: list[dict[str, Any]] = []
        for record in records:
            task = _task_from_dict(record["task"])
            bank = bank_index[(task.task_fingerprint, record["seed"])]
            snapshot = snapshots[record["provider"]]
            _validate_compact_record(record, snapshot, bank, config)
            if require_replay_match:
                replay = run_grid_record(
                    provider=record["provider"],
                    task=task,
                    snapshot=snapshot,
                    bank=bank,
                    method=record["method"],
                    config=config,
                )
                if _canonical_json(replay) != _canonical_json(record):
                    raise AssertionError(
                        f"calibration replay mismatch: {config.config_id}"
                    )
                replay_records.append(replay)
        if require_replay_match:
            replay_bytes = "".join(
                _canonical_json(record) + "\n" for record in replay_records
            ).encode("utf-8")
            if replay_bytes != shard_path.read_bytes():
                raise AssertionError(
                    f"calibration replay bytes differ: {config.config_id}"
                )
        all_records.extend(records)

    summary = _read_json(artifact_dir / "summary.json")
    summary_payload = {
        key: value
        for key, value in summary.items()
        if key != "deterministic_digest"
    }
    if (
        summary.get("schema_version") != SUMMARY_SCHEMA_VERSION
        or summary.get("deterministic_digest") != _sha256_json(summary_payload)
        or summary.get("source_validation")
        != _expected_source_validation_receipt()
    ):
        raise AssertionError("calibration summary identity drifted")
    runtime_metadata = {
        "python_version": summary["experiment_config"]["python_version"],
        "torch_version": summary["experiment_config"]["torch_version"],
    }
    recomputed = _aggregate(
        records=all_records,
        banks=banks,
        snapshots=snapshots,
        seed_plan_evidence=seed_plan_evidence,
        source_validation=summary["source_validation"],
        preregistration=preregistration,
        runtime_metadata=runtime_metadata,
    )
    if _canonical_json(recomputed) != _canonical_json(summary):
        raise AssertionError("calibration summary did not recompute")
    return summary


def _run_experiment_offline(
    *,
    anthropic_dir: Path,
    openai_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError("output directory must not already exist")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    preregistration = _load_and_validate_preregistration(PREREGISTRATION_PATH)
    source_dirs = {
        "anthropic": anthropic_dir,
        "openai": openai_dir,
    }
    source_validation = _validate_sources_without_mutation(source_dirs)
    source_paths = {
        provider: source_dirs[provider] / "proposal_rows.jsonl"
        for provider in FROZEN_SOURCES
    }
    for provider, path in source_paths.items():
        if _file_sha256(path) != FROZEN_SOURCES[provider]["proposal_sha256"]:
            raise AssertionError(f"{provider} frozen proposal bytes drifted")

    temporary = Path(
        tempfile.mkdtemp(
            prefix="countdown_calibration_grid_",
            dir=output_dir.parent,
        )
    )
    try:
        for provider, source in source_paths.items():
            shutil.copyfile(
                source,
                temporary / f"{provider}_proposal_rows.jsonl",
            )
        _write_json(temporary / "preregistration.json", preregistration)
        snapshots = _load_copied_snapshots(temporary)
        seed_plan, seed_plan_evidence = _build_seed_plan(
            DEV_TASKS, EXPLORATION_SEEDS
        )
        bank_records = [
            _build_bank_record(task, seed, seed_plan)
            for task in DEV_TASKS
            for seed in EXPLORATION_SEEDS
        ]
        _write_jsonl(temporary / "perturbation_banks.jsonl", bank_records)
        banks = tuple(
            PerturbationBank.from_record(record, verify_transform=True)
            for record in bank_records
        )
        bank_index = {
            (bank.task.task_fingerprint, bank.exploration_seed): bank
            for bank in banks
        }
        all_records: list[dict[str, Any]] = []
        for config in GRID_CONFIGS:
            records = [
                run_grid_record(
                    provider=provider,
                    task=task,
                    snapshot=snapshots[provider],
                    bank=bank_index[(task.task_fingerprint, seed)],
                    method=method,
                    config=config,
                )
                for provider in FROZEN_SOURCES
                for task in DEV_TASKS
                for seed in EXPLORATION_SEEDS
                for method in METHODS
            ]
            _write_jsonl(
                temporary / _shard_filename(config),
                records,
            )
            all_records.extend(records)
        summary = _aggregate(
            records=all_records,
            banks=banks,
            snapshots=snapshots,
            seed_plan_evidence=seed_plan_evidence,
            source_validation=source_validation,
            preregistration=preregistration,
        )
        _write_json(temporary / "summary.json", summary)
        filenames = [
            "anthropic_proposal_rows.jsonl",
            "openai_proposal_rows.jsonl",
            "perturbation_banks.jsonl",
            "preregistration.json",
            "summary.json",
            *(_shard_filename(config) for config in GRID_CONFIGS),
        ]
        files = {
            filename: _file_metadata(
                temporary / filename,
                records=(
                    len(_read_jsonl(temporary / filename))
                    if filename.endswith(".jsonl")
                    else None
                ),
            )
            for filename in filenames
        }
        manifest_payload = {
            "artifact_role": "offline_calibration_development_evidence",
            "files": files,
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "status": "COMPLETE",
        }
        _write_json(
            temporary / "manifest.json",
            {
                **manifest_payload,
                "deterministic_digest": _sha256_json(manifest_payload),
            },
        )
        validated = validate_artifact(
            temporary,
            require_replay_match=True,
            verify_bank_transform=True,
        )
        os.replace(temporary, output_dir)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return validated


def run_experiment(
    *,
    anthropic_dir: Path,
    openai_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    if any(
        os.environ.get(name)
        for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")
    ):
        raise RuntimeError(
            "offline calibration requires provider credentials unset"
        )
    with _deny_network():
        return _run_experiment_offline(
            anthropic_dir=anthropic_dir,
            openai_dir=openai_dir,
            output_dir=output_dir,
        )


def _run_self_test() -> None:
    preregistration = _load_and_validate_preregistration(PREREGISTRATION_PATH)
    decision_freeze = _load_and_validate_decision_freeze(DECISION_FREEZE_PATH)
    if preregistration["workload"]["records"] != 9216:
        raise AssertionError("calibration preregistered workload drifted")
    if decision_freeze["status"] != (
        "CALIBRATION_CONFIG_FROZEN_HELD_OUT_INPUTS_PENDING"
    ):
        raise AssertionError("calibration held-out gate drifted")
    snapshot = _fake_snapshot(0)
    task = DEV_TASKS[0]
    seed = 31
    seed_plan, _ = _build_seed_plan(DEV_TASKS, (seed,))
    bank = PerturbationBank.from_record(
        _build_bank_record(task, seed, seed_plan),
        verify_transform=True,
    )
    for method in METHODS:
        grid = run_grid_record(
            provider="anthropic",
            task=task,
            snapshot=snapshot,
            bank=bank,
            method=method,
            config=BASELINE_CONFIG,
            expected_behavior_digest=snapshot.behavior_digest,
        )
        replay = run_grid_record(
            provider="anthropic",
            task=task,
            snapshot=snapshot,
            bank=bank,
            method=method,
            config=BASELINE_CONFIG,
            expected_behavior_digest=snapshot.behavior_digest,
        )
        if grid != replay:
            raise AssertionError("calibration grid record is not reproducible")
        _validate_compact_record(grid, snapshot, bank, BASELINE_CONFIG)
        source = run_source_baseline(
            provider="anthropic",
            task=task,
            snapshot=snapshot,
            bank=bank,
            method=method,
            expected_behavior_digest=snapshot.behavior_digest,
        )
        source_trajectory = [
            {
                "action_index": event["action_index"],
                "state": event["state"],
            }
            for event in source["selection_events"]
            if event["event"] == "edge_transition"
        ]
        source_success = [
            bool(terminal["verification"]["success"])
            for terminal in source["terminals"]
        ]
        if (
            grid["trajectory_digest"] != _sha256_json(source_trajectory)
            or grid["terminal_success"] != source_success
            or grid["usage"] != source["usage"]
            or grid["method_state"]["posterior_state_digest"]
            != source["method_state"]["posterior_state_digest"]
        ):
            raise AssertionError(
                "baseline calibration kernel diverged from source v2 kernel"
            )
    alternate = run_grid_record(
        provider="anthropic",
        task=task,
        snapshot=snapshot,
        bank=bank,
        method=METHODS[0],
        config=CalibrationConfig(1.0, 0.25),
        expected_behavior_digest=snapshot.behavior_digest,
    )
    baseline = run_grid_record(
        provider="anthropic",
        task=task,
        snapshot=snapshot,
        bank=bank,
        method=METHODS[0],
        config=BASELINE_CONFIG,
        expected_behavior_digest=snapshot.behavior_digest,
    )
    if alternate["deterministic_digest"] == baseline["deterministic_digest"]:
        raise AssertionError("calibration config was absent from record identity")


def _print_summary(
    summary: Mapping[str, Any],
    *,
    replay_provenance: Mapping[str, Any] | None = None,
) -> None:
    payload = {
        "decision": summary["decision"],
        "deterministic_digest": summary["deterministic_digest"],
        "pairing_gate": summary["pairing_gate"],
    }
    if replay_provenance is not None:
        payload["replay_provenance"] = dict(replay_provenance)
    print(_canonical_json(payload))


def _replay_with_source_revalidation(
    *,
    artifact_dir: Path,
    anthropic_dir: Path,
    openai_dir: Path,
) -> dict[str, Any]:
    source_dirs = {
        "anthropic": anthropic_dir,
        "openai": openai_dir,
    }
    with _deny_network():
        fresh_receipt = _validate_sources_without_mutation(source_dirs)
        summary = validate_artifact(
            artifact_dir,
            require_replay_match=True,
        )
        if fresh_receipt != summary["source_validation"]:
            raise AssertionError(
                "fresh source validation receipt does not match "
                "the calibration artifact"
            )
    return summary


def _replay_search_bytes_only(artifact_dir: Path) -> dict[str, Any]:
    with _deny_network():
        return validate_artifact(
            artifact_dir,
            require_replay_match=True,
        )


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--replay", type=Path)
    mode.add_argument("--replay-search-only", type=Path)
    mode.add_argument("--self-test", action="store_true")
    parser.add_argument("--anthropic-dir", type=Path)
    parser.add_argument("--openai-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)

    if args.self_test:
        _run_self_test()
        print("countdown calibration grid self-test: PASS")
        return
    if args.replay is not None:
        if args.anthropic_dir is None or args.openai_dir is None:
            parser.error(
                "--replay requires --anthropic-dir and --openai-dir "
                "for fresh source-artifact revalidation"
            )
        if any(
            os.environ.get(name)
            for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")
        ):
            raise RuntimeError(
                "offline replay requires provider credentials unset"
            )
        summary = _replay_with_source_revalidation(
            artifact_dir=args.replay,
            anthropic_dir=args.anthropic_dir,
            openai_dir=args.openai_dir,
        )
        _print_summary(
            summary,
            replay_provenance={
                "mode": "search_bytes_and_fresh_source_artifacts",
                "original_source_artifacts_revalidated": True,
            },
        )
        return
    if args.replay_search_only is not None:
        if args.anthropic_dir is not None or args.openai_dir is not None:
            parser.error(
                "--replay-search-only does not accept source directories; "
                "use --replay to revalidate original source artifacts"
            )
        if any(
            os.environ.get(name)
            for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")
        ):
            raise RuntimeError(
                "offline replay requires provider credentials unset"
            )
        summary = _replay_search_bytes_only(args.replay_search_only)
        _print_summary(
            summary,
            replay_provenance={
                "mode": "self_contained_search_bytes_only",
                "original_source_artifacts_revalidated": False,
            },
        )
        return
    if (
        not args.run
        or args.anthropic_dir is None
        or args.openai_dir is None
        or args.output_dir is None
    ):
        parser.error(
            "--run requires --anthropic-dir, --openai-dir, and --output-dir"
        )
    summary = run_experiment(
        anthropic_dir=args.anthropic_dir,
        openai_dir=args.openai_dir,
        output_dir=args.output_dir,
    )
    _print_summary(summary)


if __name__ == "__main__":
    main()
