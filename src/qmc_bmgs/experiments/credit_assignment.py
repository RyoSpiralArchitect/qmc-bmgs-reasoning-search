#!/usr/bin/env python3
"""Post-validation credit-assignment diagnostic for Role-Lock D4.

This module deliberately changes one thing: the verifier value returned to the
search.  The sampler is the validated ``sobol_routing_only`` substrate, pruning
stays disabled, and every run receives exactly 700 search-feedback calls.

The immutable terminal-only control is not regenerated or copied into a new
schema.  It is loaded from the promoted standalone-validation raw file after an
exact byte SHA-256 check and full validation of its original 384-row contract.
Production generation writes only the 128 fresh ``prefix_progress`` rows.

Prefix-progress is an oracle positive control, not a deployable verifier:

    feedback(x) = 5 * L(x) / 4

where ``L`` is the longest prefix of ``(PROBE, DERIVE, COMMIT, EOS)`` matched by
the generated tokens.  Exact success remains the complete target and reward 5.
Only the exact return is passed to ``BenchmarkPolicy._observe_verifier_score``;
the progress value is returned separately for Bellman backup.  A compact,
request-complete rational ledger makes all 700 feedback events independently
auditable without relying on floating-point equality.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any, Sequence

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
from qmc_bmgs.experiments.fixed_verifier_budget import (
    _bootstrap_mean_interval,
    _exact_mcnemar_p,
    _wilson_interval,
)
from qmc_bmgs.experiments.two_phase_sampler import (
    _behavior_state_digest,
    _checkpoint_snapshot,
    _first_success_snapshot,
    _read_jsonl,
    _sha256_json,
    _source_usage_valid,
    _tree_value_digest,
    _uniform_stream_digest,
    _validate_census,
    _write_json,
    _write_jsonl,
)
from qmc_bmgs.experiments.two_phase_validation import (
    FIXED_SPEC as CONTROL_SPEC,
    _validate_validation_records,
)
from qmc_bmgs.records import canonical_record_digest


RECORD_SCHEMA_VERSION = "qmc_bmgs_credit_assignment_record_v1"
SUMMARY_SCHEMA_VERSION = "qmc_bmgs_credit_assignment_summary_v1"
REPORT_SCHEMA_VERSION = "qmc_bmgs_credit_assignment_report_v1"
LEDGER_SCHEMA_VERSION = "qmc_bmgs_credit_assignment_feedback_ledger_v1"

COMPARISON_ROLE = "post_validation_mechanism_diagnostic"
CONTROL_METHOD = "terminal_only_control"
CHALLENGER_METHOD = "prefix_progress"
SUBSTRATE_METHOD = "sobol_routing_only"
COHORT_ID = "role_lock_d4_credit_assignment_n128"

TARGET = (2, 3, 4, 1)
EXACT_REWARD = 5
FEEDBACK_DENOMINATOR = 4
POSTERIOR_SD_SCALE = 1.0
VERIFIER_CAP = 700
LM_NODE_CEILING = 1111
EDGE_CEILING = 3500
REACHABLE_PREFIX_BOUND = sum(9**level for level in range(4))
CHECKPOINTS = (64, 128, 256, 384, 512, 700)
FULL_SEED_START = 704
FULL_SEED_COUNT = 128
DIAGNOSTIC_SEED = 313
BOOTSTRAP_SAMPLES = 5_000

CONTROL_ARTIFACT_ID = "role_lock_d4_20260718_two_phase_validation_n128"
CONTROL_RAW_RELATIVE_PATH = Path(
    "artifacts/role_lock/d4/20260718_two_phase_validation_n128/records.jsonl"
)
CONTROL_RAW_SHA256 = "ec035850f61c75ca9a01f2e38f14d59841cbde9b2a046adb852a1d65c512360a"
CONTROL_ROUTING_SUBSET_SHA256 = (
    "6fcd2d613976c965ba9786fbf6f2487c4b75f4310086db5ed8b812760c85d60e"
)
CONTROL_RAW_BYTES = 11_392_058
CONTROL_RAW_RECORDS = 384

LEDGER_COLUMNS = (
    "request",
    "endpoint",
    "generated_token_ids",
    "correct_prefix_length",
    "feedback_numerator",
    "exact_return",
    "logical_lm_node_evals",
    "exact_success",
)
USAGE_INTEGER_FIELDS = (
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
    "blocked_verifier_calls",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _routing_variant() -> VariantSpec:
    variants = {variant.name: variant for variant in CHANNEL_ABLATION_VARIANTS}
    variant = variants[SUBSTRATE_METHOD]
    if (
        variant.uniform_sources is None
        or variant.uniform_sources.coverage_gate != "sobol"
        or variant.uniform_sources.cluster_quantile != "sobol"
        or variant.uniform_sources.action_perturbation != "iid"
        or variant.strata != "embedding"
        or variant.pruning
    ):
        raise AssertionError("routing-only substrate contract drifted")
    return variant


def _correct_prefix_length(
    generated: Sequence[int], target: Sequence[int] = TARGET
) -> int:
    result = 0
    for observed, expected in zip(generated, target):
        if int(observed) != int(expected):
            break
        result += 1
    return result


def _exact_integer(value: Any) -> bool:
    return type(value) is int


def _exact_integer_list(value: Any, *, maximum_length: int | None = None) -> bool:
    return (
        isinstance(value, list)
        and (maximum_length is None or len(value) <= maximum_length)
        and all(_exact_integer(item) for item in value)
    )


def _json_exact_equal(observed: Any, expected: Any) -> bool:
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


class CreditAssignmentPolicy(BenchmarkPolicy):
    """Routing-only policy that separates progress feedback from exact success."""

    def __init__(
        self,
        *args: Any,
        feedback_mode: str = "prefix_progress",
        **kwargs: Any,
    ) -> None:
        if feedback_mode not in ("prefix_progress", "terminal_only_compatibility"):
            raise ValueError("unknown credit-assignment feedback mode")
        self.feedback_mode = feedback_mode
        self.feedback_events: list[list[Any]] = []
        self.best_feedback_numerator = 0
        self.first_positive_feedback_request: int | None = None
        self.first_positive_feedback_lm_eval: int | None = None
        super().__init__(*args, **kwargs)

    def _feedback_verifier(self, tokens: tuple[int, ...], endpoint: str) -> float:
        if endpoint not in ("terminal_eos", "depth_cutoff"):
            raise ValueError("feedback endpoint must be terminal_eos or depth_cutoff")
        if self.counters.verifier_requests >= self.verifier_budget:
            self.blocked_verifier_calls += 1
            return 0.0

        self.counters.verifier_requests += 1
        self.counters.verifier_evaluations += 1
        request = int(self.counters.verifier_requests)
        generated = [int(token) for token in tokens[len(self.task.root) :]]
        prefix_length = _correct_prefix_length(generated, self.task.target)
        exact_return = EXACT_REWARD if tuple(generated) == self.task.target else 0
        exact_success = exact_return == EXACT_REWARD
        progress_numerator = EXACT_REWARD * prefix_length
        feedback_numerator = (
            progress_numerator
            if self.feedback_mode == "prefix_progress"
            else exact_return * FEEDBACK_DENOMINATOR
        )

        # Critical separation: inherited success counters see exact return only.
        super()._observe_verifier_score(float(exact_return))

        if feedback_numerator > self.best_feedback_numerator:
            self.best_feedback_numerator = feedback_numerator
        if feedback_numerator > 0 and self.first_positive_feedback_request is None:
            self.first_positive_feedback_request = request
            self.first_positive_feedback_lm_eval = int(
                self.counters.logical_lm_node_evals
            )
        self.feedback_events.append(
            [
                request,
                endpoint,
                generated,
                prefix_length,
                feedback_numerator,
                exact_return,
                int(self.counters.logical_lm_node_evals),
                exact_success,
            ]
        )
        return feedback_numerator / FEEDBACK_DENOMINATOR

    def _terminal_verifier(self, tokens: tuple[int, ...]) -> float:
        return self._feedback_verifier(tokens, "terminal_eos")

    def _cutoff_verifier(self, tokens: tuple[int, ...]) -> float:
        return self._feedback_verifier(tokens, "depth_cutoff")

    def feedback_ledger(self) -> dict[str, Any]:
        counts = Counter(int(event[3]) for event in self.feedback_events)
        exact_event_count = sum(int(event[7]) for event in self.feedback_events)
        positive_event_count = sum(int(event[4] > 0) for event in self.feedback_events)
        terminal_event_count = sum(
            int(event[1] == "terminal_eos") for event in self.feedback_events
        )
        cumulative_numerator = sum(int(event[4]) for event in self.feedback_events)
        payload: dict[str, Any] = {
            "schema_version": LEDGER_SCHEMA_VERSION,
            "columns": list(LEDGER_COLUMNS),
            "feedback_formula": "5*longest_correct_prefix_length/4",
            "feedback_denominator": FEEDBACK_DENOMINATOR,
            "exact_success_target": list(TARGET),
            "exact_reward": EXACT_REWARD,
            "feedback_mode": self.feedback_mode,
            "event_count": len(self.feedback_events),
            "events": copy.deepcopy(self.feedback_events),
            "event_sequence_sha256": _sha256_json(self.feedback_events),
            "correct_prefix_length_counts": {
                str(length): int(counts.get(length, 0)) for length in range(5)
            },
            "terminal_event_count": terminal_event_count,
            "cutoff_event_count": len(self.feedback_events) - terminal_event_count,
            "positive_feedback_event_count": positive_event_count,
            "exact_success_event_count": exact_event_count,
            "cumulative_feedback_numerator": cumulative_numerator,
            "best_feedback_numerator": int(self.best_feedback_numerator),
            "first_positive_feedback_request": self.first_positive_feedback_request,
            "first_positive_feedback_lm_eval": self.first_positive_feedback_lm_eval,
            "first_exact_success_request": self.first_success_verifier_request,
            "first_exact_success_lm_eval": self.counters.first_success_lm_eval,
            "exact_success_observation_channel": (
                "BenchmarkPolicy._observe_verifier_score(exact_return_only)"
            ),
            "terminal_exact_success_nonintervention": all(
                event[1] == "terminal_eos"
                and event[4] == EXACT_REWARD * FEEDBACK_DENOMINATOR
                and event[5] == EXACT_REWARD
                and event[7] is True
                for event in self.feedback_events
                if event[7] is True
            ),
        }
        payload["ledger_payload_sha256"] = _sha256_json(payload)
        return payload


def _feedback_prefix_summary(
    events: Sequence[list[Any]], completed_requests: int
) -> dict[str, Any]:
    prefix = list(events[:completed_requests])
    positive = [event for event in prefix if int(event[4]) > 0]
    exact = [event for event in prefix if event[7] is True]
    payload: dict[str, Any] = {
        "completed_feedback_requests": int(completed_requests),
        "event_count": len(prefix),
        "event_prefix_sha256": _sha256_json(prefix),
        "cumulative_feedback_numerator": sum(int(event[4]) for event in prefix),
        "positive_feedback_event_count": len(positive),
        "exact_success_event_count": len(exact),
        "best_feedback_numerator": max((int(event[4]) for event in prefix), default=0),
        "first_positive_feedback_request": (
            None if not positive else int(positive[0][0])
        ),
        "first_positive_feedback_lm_eval": (
            None if not positive else int(positive[0][6])
        ),
        "first_exact_success_request": None if not exact else int(exact[0][0]),
        "first_exact_success_lm_eval": None if not exact else int(exact[0][6]),
    }
    payload["prefix_payload_sha256"] = _sha256_json(payload)
    return payload


def _run_prefix_progress(
    *,
    seed: int,
    verifier_cap: int,
    lm_node_ceiling: int,
    edge_ceiling: int,
    checkpoints: Sequence[int],
    registry: CandidateRegistry,
) -> dict[str, Any]:
    checkpoint_values = tuple(int(value) for value in checkpoints)
    if (
        min(verifier_cap, lm_node_ceiling, edge_ceiling) < 1
        or not checkpoint_values
        or checkpoint_values != tuple(sorted(set(checkpoint_values)))
        or checkpoint_values[-1] != verifier_cap
    ):
        raise ValueError("invalid credit-assignment budget/checkpoint contract")
    task = RoleLockTask(4)
    variant = _routing_variant()
    seeds = SeedPlan(
        task_seed=4,
        exploration_seed=int(seed),
        partition_seed=10_000,
    )
    tokenizer = RoleLockTokenizer()
    config = benchmark_config(task, variant, int(seed))
    policy = CreditAssignmentPolicy(
        RoleLockLM(task, seeds.model_seed),
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
    first_success_snapshot: dict[str, Any] | None = None
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
        previous_request = int(policy.counters.verifier_requests)
        previous_first = policy.first_success_verifier_request
        _, reason = policy.search_step_budgeted(task.root)
        if reason == "lm_budget_frontier":
            policy.stop_reason = "lm_integrity_ceiling_frontier"
            break
        if reason == "edge_budget":
            policy.stop_reason = "edge_integrity_ceiling"
            break
        if policy.counters.verifier_requests != previous_request + 1:
            raise AssertionError("each simulation must consume one feedback call")
        completed = int(policy.counters.verifier_requests)
        if previous_first is None and policy.first_success_verifier_request is not None:
            first_success_snapshot = _first_success_snapshot(policy, task)
        if completed in checkpoint_values:
            snapshots.append(_checkpoint_snapshot(policy, task, completed))

    wall_time = time.perf_counter() - started
    if not snapshots or snapshots[-1]["completed_verifier_requests"] != verifier_cap:
        readout: list[int] = []
    else:
        readout = [int(value) for value in snapshots[-1]["readout_token_ids"]]
    policy.counters.evaluation_only_calls += 1
    counters = asdict(policy.counters)
    exact_success = task.is_success(readout)
    correct_prefix = _correct_prefix_length(readout, task.target)
    lm_used = int(policy.counters.logical_lm_node_evals)
    edges_used = int(policy.counters.edge_selections)
    verifier_used = int(policy.counters.verifier_requests)
    source_plan = variant.uniform_sources
    if source_plan is None:
        raise AssertionError("routing-only variant lost its coordinate plan")
    feedback_ledger = policy.feedback_ledger()
    feedback_checkpoint_prefixes = [
        _feedback_prefix_summary(policy.feedback_events, checkpoint)
        for checkpoint in checkpoint_values
    ]

    record: dict[str, Any] = {
        "schema_version": RECORD_SCHEMA_VERSION,
        "record_type": "credit_assignment_prefix_progress_run",
        "paired_group_id": f"role_lock_d4:seed{seed}:v{verifier_cap}",
        "comparison_role": COMPARISON_ROLE,
        "cohort_id": COHORT_ID,
        "experiment": {
            "name": "role_lock_d4_credit_assignment_diagnostic",
            "question": (
                "does oracle prefix-progress feedback improve exact readout success "
                "on the fixed routing-only substrate"
            ),
            "performance_validation": False,
            "oracle_positive_control": True,
            "threshold_sweep": False,
            "control_reused_immutable": True,
            "control_artifact_id": CONTROL_ARTIFACT_ID,
            "control_raw_sha256": CONTROL_RAW_SHA256,
        },
        "method": {
            "name": CHALLENGER_METHOD,
            "substrate": SUBSTRATE_METHOD,
            "sampler": variant.sampler,
            "strata": variant.strata,
            "pruning": False,
            "posterior_sd_scale": POSTERIOR_SD_SCALE,
            "sampler_layout": "matched_full_dimension_column_mux/v2_dynamic",
            "uniform_sources": source_plan.as_dict(),
            "search_feedback": "prefix_progress",
            "feedback_formula": "5*longest_correct_prefix_length/4",
            "success_ledger": "exact_target_only",
            "readout": "return_mean_then_visits_then_prior",
            "lm_prior_role": "behavior_only",
        },
        "search_config": asdict(config),
        "task": {
            "id": task.task_id,
            "depth": task.depth,
            "target": list(task.target),
            "exact_reward": EXACT_REWARD,
            "exact_success_definition": "generated_token_ids_equal_target",
            "feedback_is_terminal_only": False,
        },
        "seeds": asdict(seeds),
        "budget": {
            "primary": "search_feedback_requests",
            "limit": verifier_cap,
            "verifier_limit": verifier_cap,
            "lm_node_ceiling": lm_node_ceiling,
            "lm_node_ceiling_kind": "conservative_integrity_guard",
            "reachable_nonterminal_prefix_bound": REACHABLE_PREFIX_BOUND,
            "edge_ceiling": edge_ceiling,
            "normal_edge_bound": 4 * verifier_cap,
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
            "readout_success": exact_success,
            "readout_exact_return": EXACT_REWARD if exact_success else 0,
            "readout_correct_prefix_length": correct_prefix,
            "readout_failure_stage": None if exact_success else correct_prefix,
            "best_observed_exact_success": (
                policy.counters.best_observed_return == EXACT_REWARD
            ),
            "best_observed_exact_return": int(policy.counters.best_observed_return),
            "best_search_feedback_numerator": policy.best_feedback_numerator,
            "best_search_feedback_denominator": FEEDBACK_DENOMINATOR,
            "first_positive_feedback_request": (policy.first_positive_feedback_request),
            "first_positive_feedback_lm_eval": (policy.first_positive_feedback_lm_eval),
        },
        "feedback_audit": feedback_ledger,
        "telemetry": {
            "enabled": True,
            "contract": "passive_checkpoint_census/v1",
            "checkpoint_requests": list(checkpoint_values),
            "checkpoint_readouts_are_search_feedback": False,
            "consumes_rng_draws": False,
            "consumes_model_calls": False,
            "consumes_feedback_calls": False,
            "final_readout_reuses_cap_checkpoint": True,
            "checkpoints": snapshots,
            "passive_checkpoint_collector_calls": len(snapshots),
            "feedback_checkpoint_prefixes": feedback_checkpoint_prefixes,
            "first_exact_success_after_backup_snapshot": first_success_snapshot,
        },
        "search": {
            **_search_diagnostics(policy, task, include_temporal_source_details=True),
            "prune_log": policy.prune_log,
            "final_tree_value_digest": _tree_value_digest(policy),
            "final_uniform_stream_digest": _uniform_stream_digest(policy),
            "final_behavior_state_digest": _behavior_state_digest(policy),
        },
        "randomization": {
            "independent_unit": "exploration_seed",
            "node_stream_seeded_from": "exploration_seed_and_exact_prefix",
            "source_architecture": "matched_full_dimension_column_mux",
            "sobol_scramble": True,
            "iid_seed_transform": "node_seed XOR 0x1D1D1D",
            "both_sources_advanced_every_draw": True,
            "common_random_numbers_with_control": {
                "unchanged_sampler_coordinates": True,
                "scope": "same exact prefix, exploration seed, and node draw index",
            },
        },
        "evaluation_scope": {
            "search_feedback_calls": verifier_used,
            "passive_checkpoint_readouts": len(snapshots),
            "final_outside_budget_readout_evaluations": 1,
            "checkpoint_readouts_outside_feedback_budget": True,
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
    progress_every: int = 0,
    skip_seeds: set[int] | None = None,
) -> list[dict[str, Any]]:
    normalized = [int(seed) for seed in seed_ids]
    if not normalized or any(seed < 0 for seed in normalized):
        raise ValueError("seed_ids must contain nonnegative integers")
    if len(set(normalized)) != len(normalized):
        raise ValueError("seed_ids must be unique")
    registry = CandidateRegistry()
    skip = skip_seeds or set()
    records: list[dict[str, Any]] = []
    total = len(normalized) - len(skip)
    for seed in normalized:
        if seed in skip:
            continue
        records.append(
            _run_prefix_progress(
                seed=seed,
                verifier_cap=verifier_cap,
                lm_node_ceiling=lm_node_ceiling,
                edge_ceiling=edge_ceiling,
                checkpoints=checkpoints,
                registry=registry,
            )
        )
        if progress_every and len(records) % progress_every == 0:
            print(f"completed {len(records)}/{total}", flush=True)
    return records


def _record_seed(record: dict[str, Any]) -> int:
    seed = record["seeds"]["exploration_seed"]
    if not _exact_integer(seed):
        raise TypeError("record seed must be an exact JSON integer")
    return seed


def _ledger_without_digest(ledger: dict[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(ledger)
    payload.pop("ledger_payload_sha256", None)
    return payload


def _ledger_valid(record: dict[str, Any], verifier_cap: int) -> bool:
    ledger = record.get("feedback_audit")
    if not isinstance(ledger, dict):
        return False
    expected_keys = {
        "schema_version",
        "columns",
        "feedback_formula",
        "feedback_denominator",
        "exact_success_target",
        "exact_reward",
        "feedback_mode",
        "event_count",
        "events",
        "event_sequence_sha256",
        "correct_prefix_length_counts",
        "terminal_event_count",
        "cutoff_event_count",
        "positive_feedback_event_count",
        "exact_success_event_count",
        "cumulative_feedback_numerator",
        "best_feedback_numerator",
        "first_positive_feedback_request",
        "first_positive_feedback_lm_eval",
        "first_exact_success_request",
        "first_exact_success_lm_eval",
        "exact_success_observation_channel",
        "terminal_exact_success_nonintervention",
        "ledger_payload_sha256",
    }
    if set(ledger) != expected_keys:
        return False
    if (
        ledger.get("schema_version") != LEDGER_SCHEMA_VERSION
        or not _json_exact_equal(ledger.get("columns"), list(LEDGER_COLUMNS))
        or ledger.get("feedback_formula") != "5*longest_correct_prefix_length/4"
        or not _json_exact_equal(
            ledger.get("feedback_denominator"), FEEDBACK_DENOMINATOR
        )
        or not _json_exact_equal(ledger.get("exact_success_target"), list(TARGET))
        or not _json_exact_equal(ledger.get("exact_reward"), EXACT_REWARD)
        or ledger.get("feedback_mode") != "prefix_progress"
        or not _json_exact_equal(ledger.get("event_count"), verifier_cap)
        or ledger.get("ledger_payload_sha256")
        != _sha256_json(_ledger_without_digest(ledger))
    ):
        return False
    events = ledger.get("events")
    if not isinstance(events, list) or len(events) != verifier_cap:
        return False
    length_counts = Counter()
    exact_requests: list[int] = []
    exact_lm_evals: list[int] = []
    positive_requests: list[int] = []
    positive_lm_evals: list[int] = []
    terminal_count = 0
    best_numerator = 0
    cumulative_numerator = 0
    previous_lm_eval = 0
    for index, event in enumerate(events, start=1):
        if not isinstance(event, list) or len(event) != len(LEDGER_COLUMNS):
            return False
        (
            request,
            endpoint,
            generated,
            length,
            numerator,
            exact_return,
            lm_eval,
            exact_success,
        ) = event
        if (
            not _json_exact_equal(request, index)
            or endpoint not in ("terminal_eos", "depth_cutoff")
            or not _exact_integer_list(generated, maximum_length=4)
            or not _exact_integer(length)
            or not _exact_integer(numerator)
            or not _exact_integer(exact_return)
            or not _exact_integer(lm_eval)
            or type(exact_success) is not bool
        ):
            return False
        expected_length = _correct_prefix_length(generated)
        expected_exact = EXACT_REWARD if tuple(generated) == TARGET else 0
        if (
            length != expected_length
            or numerator != EXACT_REWARD * expected_length
            or exact_return != expected_exact
            or exact_success is not (expected_exact == EXACT_REWARD)
            or (endpoint == "terminal_eos") != (bool(generated) and generated[-1] == 1)
            or (endpoint == "depth_cutoff" and len(generated) != 4)
            or lm_eval < 1
            or lm_eval < previous_lm_eval
        ):
            return False
        previous_lm_eval = lm_eval
        terminal_count += int(endpoint == "terminal_eos")
        length_counts[length] += 1
        best_numerator = max(best_numerator, numerator)
        cumulative_numerator += numerator
        if numerator > 0:
            positive_requests.append(request)
            positive_lm_evals.append(lm_eval)
        if exact_success:
            exact_requests.append(request)
            exact_lm_evals.append(lm_eval)
            if (
                endpoint != "terminal_eos"
                or numerator != EXACT_REWARD * FEEDBACK_DENOMINATOR
            ):
                return False
    expected_counts = {str(length): int(length_counts[length]) for length in range(5)}
    first_positive = positive_requests[0] if positive_requests else None
    first_positive_lm = positive_lm_evals[0] if positive_lm_evals else None
    first_exact = exact_requests[0] if exact_requests else None
    first_exact_lm = exact_lm_evals[0] if exact_lm_evals else None
    return (
        ledger.get("event_sequence_sha256") == _sha256_json(events)
        and _json_exact_equal(
            ledger.get("correct_prefix_length_counts"), expected_counts
        )
        and _json_exact_equal(ledger.get("terminal_event_count"), terminal_count)
        and _json_exact_equal(
            ledger.get("cutoff_event_count"), verifier_cap - terminal_count
        )
        and _json_exact_equal(
            ledger.get("positive_feedback_event_count"), len(positive_requests)
        )
        and _json_exact_equal(
            ledger.get("exact_success_event_count"), len(exact_requests)
        )
        and _json_exact_equal(
            ledger.get("cumulative_feedback_numerator"), cumulative_numerator
        )
        and _json_exact_equal(ledger.get("best_feedback_numerator"), best_numerator)
        and _json_exact_equal(
            ledger.get("first_positive_feedback_request"), first_positive
        )
        and _json_exact_equal(
            ledger.get("first_positive_feedback_lm_eval"), first_positive_lm
        )
        and _json_exact_equal(ledger.get("first_exact_success_request"), first_exact)
        and _json_exact_equal(ledger.get("first_exact_success_lm_eval"), first_exact_lm)
        and ledger.get("exact_success_observation_channel")
        == "BenchmarkPolicy._observe_verifier_score(exact_return_only)"
        and ledger.get("terminal_exact_success_nonintervention") is True
    )


def _checkpoint_valid(row: dict[str, Any], *, request: int, task: RoleLockTask) -> bool:
    try:
        payload = copy.deepcopy(row)
        observed_digest = payload.pop("checkpoint_payload_digest")
        usage = row["usage"]
        census = row["census"]
        readout = row["readout_token_ids"]
        edges = usage["edge_selections"]
        nodes = usage["logical_lm_node_evals"]
        return (
            observed_digest == _sha256_json(payload)
            and _json_exact_equal(row["completed_verifier_requests"], request)
            and _json_exact_equal(usage["verifier_requests"], request)
            and _exact_integer_list(readout, maximum_length=4)
            and row["readout_success"] is task.is_success(readout)
            and _json_exact_equal(
                row["readout_correct_prefix_length"],
                _correct_prefix_length(readout, task.target),
            )
            and _validate_census(census, nodes_created=nodes, edges=edges)
            and row["collector_behavior_unchanged"] is True
            and row["collector_behavior_digest_before"]
            == row["collector_behavior_digest_after"]
            == row["behavior_state_digest"]
        )
    except (KeyError, TypeError, ValueError):
        return False


def _feedback_checkpoint_prefixes_valid(
    record: dict[str, Any], checkpoint_values: Sequence[int]
) -> bool:
    try:
        events = record["feedback_audit"]["events"]
        observed = record["telemetry"]["feedback_checkpoint_prefixes"]
        snapshots = record["telemetry"]["checkpoints"]
        if not isinstance(observed, list) or len(observed) != len(checkpoint_values):
            return False
        for prefix, snapshot, checkpoint in zip(observed, snapshots, checkpoint_values):
            expected = _feedback_prefix_summary(events, int(checkpoint))
            if not _json_exact_equal(prefix, expected):
                return False
            if (
                prefix["exact_success_event_count"]
                != snapshot["census"]["correct_stage_eos_trials"]
                or prefix["event_count"] != checkpoint
            ):
                return False
            prefix_events = events[:checkpoint]
            if prefix_events and int(prefix_events[-1][6]) > int(
                snapshot["usage"]["logical_lm_node_evals"]
            ):
                return False
        final = observed[-1]
        ledger = record["feedback_audit"]
        return (
            final["event_prefix_sha256"] == ledger["event_sequence_sha256"]
            and final["cumulative_feedback_numerator"]
            == ledger["cumulative_feedback_numerator"]
            and final["positive_feedback_event_count"]
            == ledger["positive_feedback_event_count"]
            and final["exact_success_event_count"]
            == ledger["exact_success_event_count"]
            and final["best_feedback_numerator"] == ledger["best_feedback_numerator"]
            and final["first_positive_feedback_request"]
            == ledger["first_positive_feedback_request"]
            and final["first_positive_feedback_lm_eval"]
            == ledger["first_positive_feedback_lm_eval"]
            and final["first_exact_success_request"]
            == ledger["first_exact_success_request"]
            and final["first_exact_success_lm_eval"]
            == ledger["first_exact_success_lm_eval"]
        )
    except (KeyError, IndexError, TypeError, ValueError):
        return False


def _validate_records_impl(
    records: Sequence[dict[str, Any]],
    *,
    seed_ids: Sequence[int],
    verifier_cap: int,
    lm_node_ceiling: int,
    edge_ceiling: int,
    checkpoints: Sequence[int],
) -> dict[str, Any]:
    expected_seeds = [int(seed) for seed in seed_ids]
    observed_seeds = [_record_seed(record) for record in records]
    errors: dict[str, int] = defaultdict(int)
    task = RoleLockTask(4)
    variant = _routing_variant()
    checkpoint_values = tuple(int(value) for value in checkpoints)
    fingerprints: set[str] = set()

    if len(observed_seeds) != len(set(observed_seeds)):
        errors["duplicate"] += len(observed_seeds) - len(set(observed_seeds))
    if set(observed_seeds) != set(expected_seeds):
        errors["cohort"] += 1
    if observed_seeds != sorted(expected_seeds):
        errors["canonical_order"] += 1

    for record in records:
        seed = _record_seed(record)
        if record.get("schema_version") != RECORD_SCHEMA_VERSION:
            errors["schema"] += 1
        if record.get("deterministic_digest") != canonical_record_digest(record):
            errors["digest"] += 1
        try:
            json.dumps(record, allow_nan=False)
        except (TypeError, ValueError):
            errors["strict_json"] += 1
        if (
            record.get("record_type") != "credit_assignment_prefix_progress_run"
            or record.get("comparison_role") != COMPARISON_ROLE
            or record.get("cohort_id") != COHORT_ID
            or record.get("paired_group_id")
            != f"role_lock_d4:seed{seed}:v{verifier_cap}"
        ):
            errors["identity"] += 1
        method = record.get("method", {})
        expected_sources = variant.uniform_sources
        if (
            method.get("name") != CHALLENGER_METHOD
            or method.get("substrate") != SUBSTRATE_METHOD
            or method.get("pruning") is not False
            or not _json_exact_equal(
                method.get("posterior_sd_scale"), POSTERIOR_SD_SCALE
            )
            or expected_sources is None
            or not _json_exact_equal(
                method.get("uniform_sources"), expected_sources.as_dict()
            )
            or method.get("search_feedback") != "prefix_progress"
            or method.get("success_ledger") != "exact_target_only"
        ):
            errors["method"] += 1
        expected_config = asdict(benchmark_config(task, variant, seed))
        expected_seeds_record = asdict(
            SeedPlan(task_seed=4, exploration_seed=seed, partition_seed=10_000)
        )
        if not _json_exact_equal(
            record.get("search_config"), expected_config
        ) or not _json_exact_equal(record.get("seeds"), expected_seeds_record):
            errors["config"] += 1
        task_record = record.get("task", {})
        if (
            task_record.get("id") != "role_lock_d4"
            or not _json_exact_equal(task_record.get("depth"), 4)
            or not _json_exact_equal(task_record.get("target"), list(TARGET))
            or not _json_exact_equal(task_record.get("exact_reward"), EXACT_REWARD)
            or task_record.get("feedback_is_terminal_only") is not False
        ):
            errors["task"] += 1

        usage = record.get("usage", {})
        if not isinstance(usage, dict) or any(
            not _exact_integer(usage.get(field)) for field in USAGE_INTEGER_FIELDS
        ):
            errors["usage"] += 1
            continue
        verifier_used = usage["verifier_requests"]
        lm_used = usage["logical_lm_node_evals"]
        edges = usage["edge_selections"]
        budget = record.get("budget", {})
        headroom = budget.get("guard_headroom", {})
        if (
            budget.get("primary") != "search_feedback_requests"
            or not _json_exact_equal(budget.get("limit"), verifier_cap)
            or not _json_exact_equal(budget.get("verifier_limit"), verifier_cap)
            or not _json_exact_equal(budget.get("lm_node_ceiling"), lm_node_ceiling)
            or not _json_exact_equal(budget.get("edge_ceiling"), edge_ceiling)
            or budget.get("stop_reason") != "verifier_budget"
            or budget.get("exact_primary_cap_reached") is not True
            or verifier_used != verifier_cap
            or lm_used >= lm_node_ceiling
            or lm_used > REACHABLE_PREFIX_BOUND
            or edges >= edge_ceiling
            or edges > 4 * verifier_cap
            or not _json_exact_equal(
                headroom.get("lm_nodes"), lm_node_ceiling - lm_used
            )
            or not _json_exact_equal(headroom.get("edges"), edge_ceiling - edges)
        ):
            errors["budget"] += 1
        search = record.get("search", {})
        if (
            usage["verifier_evaluations"] != verifier_cap
            or usage["physical_lm_forwards"] != lm_used
            or usage["evaluation_only_calls"] != 1
            or usage["blocked_verifier_calls"] != 0
            or usage["simulations_started"] != verifier_cap
            or usage["simulations_completed"] != verifier_cap
            or usage["budget_leaf_backups"] != 0
            or usage["cache_hits"] + lm_used != edges
            or not lm_used <= usage["full_prefix_tokens"] <= 4 * lm_used
            or usage["coverage_route_selections"] + usage["global_route_selections"]
            != edges
            or usage["prune_checks"] != 0
            or usage["prune_batches"] != 0
            or usage["arms_pruned"] != 0
            or search.get("prune_log") != []
            or search.get("nodes_created") != lm_used
        ):
            errors["usage"] += 1

        outcome = record.get("outcome", {})
        readout = outcome.get("readout_token_ids")
        if not _exact_integer_list(readout, maximum_length=4):
            errors["outcome"] += 1
            readout = []
        exact_success = list(readout) == list(TARGET)
        exact_hit = usage.get("first_success_verifier_request")
        if (
            outcome.get("readout_success") is not exact_success
            or not _json_exact_equal(
                outcome.get("readout_exact_return"),
                EXACT_REWARD if exact_success else 0,
            )
            or not _json_exact_equal(
                outcome.get("readout_correct_prefix_length"),
                _correct_prefix_length(readout),
            )
            or outcome.get("best_observed_exact_success") is not (exact_hit is not None)
            or not _json_exact_equal(
                outcome.get("best_observed_exact_return"),
                EXACT_REWARD if exact_hit is not None else 0,
            )
            or (
                exact_hit is not None
                and not (_exact_integer(exact_hit) and 1 <= exact_hit <= verifier_cap)
            )
        ):
            errors["outcome"] += 1
        if not _ledger_valid(record, verifier_cap):
            errors["feedback_ledger"] += 1
        else:
            ledger = record["feedback_audit"]
            if (
                not _json_exact_equal(ledger["first_exact_success_request"], exact_hit)
                or not _json_exact_equal(
                    ledger["best_feedback_numerator"],
                    outcome.get("best_search_feedback_numerator"),
                )
                or not _json_exact_equal(
                    ledger["first_positive_feedback_request"],
                    outcome.get("first_positive_feedback_request"),
                )
                or not _json_exact_equal(
                    ledger["first_positive_feedback_lm_eval"],
                    outcome.get("first_positive_feedback_lm_eval"),
                )
                or not _json_exact_equal(
                    ledger["first_exact_success_lm_eval"],
                    usage.get("first_success_lm_eval"),
                )
                or not _json_exact_equal(
                    outcome.get("best_search_feedback_denominator"),
                    FEEDBACK_DENOMINATOR,
                )
                or (ledger["events"] and int(ledger["events"][-1][6]) > lm_used)
            ):
                errors["feedback_ledger"] += 1

        telemetry = record.get("telemetry", {})
        rows = telemetry.get("checkpoints", [])
        observed_checkpoint_ids = (
            [row.get("completed_verifier_requests") for row in rows]
            if isinstance(rows, list)
            else []
        )
        if (
            telemetry.get("enabled") is not True
            or not _json_exact_equal(
                telemetry.get("checkpoint_requests"), list(checkpoint_values)
            )
            or observed_checkpoint_ids != list(checkpoint_values)
            or telemetry.get("passive_checkpoint_collector_calls")
            != len(checkpoint_values)
            or any(
                not _checkpoint_valid(row, request=request, task=task)
                for row, request in zip(rows, checkpoint_values)
            )
            or not _feedback_checkpoint_prefixes_valid(record, checkpoint_values)
        ):
            errors["telemetry"] += 1
        source_usage = search.get("uniform_source_usage")
        if not _source_usage_valid(
            source_usage,
            method=SUBSTRATE_METHOD,
            edges=edges,
            nodes=lm_used,
            switch_edges=0,
            expected_reconfigurations=0,
        ):
            errors["source_accounting"] += 1
        fingerprint = search.get("root_candidate_fingerprint")
        if not isinstance(fingerprint, str) or len(fingerprint) != 64:
            errors["candidate"] += 1
        else:
            fingerprints.add(fingerprint)
        if usage["candidate_misses"] != 0:
            errors["candidate"] += 1

    checks = {
        "complete_unique_challenger_cohort": (
            errors["duplicate"] == 0
            and errors["cohort"] == 0
            and errors["canonical_order"] == 0
        ),
        "schema_digest_and_strict_json": all(
            errors[name] == 0 for name in ("schema", "digest", "strict_json")
        ),
        "fixed_identity_method_task_and_config": all(
            errors[name] == 0 for name in ("identity", "method", "task", "config")
        ),
        "exact_budget_and_usage_accounting": all(
            errors[name] == 0 for name in ("budget", "usage")
        ),
        "exact_success_separate_from_progress_feedback": all(
            errors[name] == 0 for name in ("outcome", "feedback_ledger")
        ),
        "passive_checkpoint_and_source_accounting": all(
            errors[name] == 0
            for name in ("telemetry", "source_accounting", "candidate")
        ),
        "candidate_identity_stable": len(fingerprints) == 1,
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "status": "PASS" if not failures else "FAIL",
        "checks": checks,
        "failures": failures,
        "details": {
            "expected_records": len(expected_seeds),
            "observed_records": len(records),
            "duplicate_count": len(observed_seeds) - len(set(observed_seeds)),
            "missing_seeds": sorted(set(expected_seeds) - set(observed_seeds)),
            "unexpected_seeds": sorted(set(observed_seeds) - set(expected_seeds)),
            "error_counts": dict(errors),
            "root_candidate_fingerprints": sorted(fingerprints),
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


def validate_records(
    records: Sequence[dict[str, Any]],
    *,
    seed_ids: Sequence[int],
    verifier_cap: int = VERIFIER_CAP,
    lm_node_ceiling: int = LM_NODE_CEILING,
    edge_ceiling: int = EDGE_CEILING,
    checkpoints: Sequence[int] = CHECKPOINTS,
) -> dict[str, Any]:
    """Return a FAIL object for malformed external records instead of raising."""
    try:
        return _validate_records_impl(
            records,
            seed_ids=seed_ids,
            verifier_cap=verifier_cap,
            lm_node_ceiling=lm_node_ceiling,
            edge_ceiling=edge_ceiling,
            checkpoints=checkpoints,
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
            "details": {"exception": f"{type(exc).__name__}: {exc}"},
        }


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_jsonl_sha256(records: Sequence[dict[str, Any]]) -> str:
    payload = "".join(
        json.dumps(
            record,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
        for record in records
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def load_immutable_control(
    path: Path | None = None,
    *,
    seed_ids: Sequence[int] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    control_path = path or (_repo_root() / CONTROL_RAW_RELATIVE_PATH)
    observed_sha = _file_sha256(control_path)
    if observed_sha != CONTROL_RAW_SHA256:
        raise ValueError(
            "immutable control raw SHA mismatch: "
            f"expected {CONTROL_RAW_SHA256}, observed {observed_sha}"
        )
    manifest_path = control_path.with_name("manifest.json")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_file = manifest["files"]["records.jsonl"]
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise ValueError(f"immutable control manifest is invalid: {exc}") from exc
    if (
        manifest.get("artifact_id") != CONTROL_ARTIFACT_ID
        or not _json_exact_equal(manifest_file.get("bytes"), CONTROL_RAW_BYTES)
        or not _json_exact_equal(manifest_file.get("records"), CONTROL_RAW_RECORDS)
        or manifest_file.get("sha256") != CONTROL_RAW_SHA256
        or control_path.stat().st_size != CONTROL_RAW_BYTES
    ):
        raise ValueError("immutable control manifest/file contract drifted")
    all_records = _read_jsonl(control_path)
    if len(all_records) != CONTROL_RAW_RECORDS:
        raise ValueError("immutable control record count drifted")
    full_seeds = list(range(FULL_SEED_START, FULL_SEED_START + FULL_SEED_COUNT))
    quality = _validate_validation_records(
        all_records,
        seed_ids=full_seeds,
        spec=CONTROL_SPEC,
    )
    if quality["status"] != "PASS":
        raise ValueError(f"immutable control validation failed: {quality['failures']}")
    full_controls = [
        record for record in all_records if record["method"]["name"] == SUBSTRATE_METHOD
    ]
    full_controls.sort(key=lambda record: int(record["seeds"]["exploration_seed"]))
    observed_subset_sha = _canonical_jsonl_sha256(full_controls)
    if (
        len(full_controls) != FULL_SEED_COUNT
        or observed_subset_sha != CONTROL_ROUTING_SUBSET_SHA256
    ):
        raise ValueError("immutable routing-only control subset SHA/count drifted")
    requested = full_seeds if seed_ids is None else [int(seed) for seed in seed_ids]
    if not set(requested).issubset(full_seeds):
        raise ValueError("control requests must be subsets of seeds 704--831")
    controls = [
        record
        for record in full_controls
        if record["seeds"]["exploration_seed"] in set(requested)
    ]
    if [int(record["seeds"]["exploration_seed"]) for record in controls] != sorted(
        requested
    ):
        raise ValueError("immutable control extraction is incomplete")
    provenance = {
        "artifact_id": CONTROL_ARTIFACT_ID,
        "path": str(control_path),
        "expected_sha256": CONTROL_RAW_SHA256,
        "observed_sha256": observed_sha,
        "manifest_artifact_id": manifest["artifact_id"],
        "manifest_expected_bytes": CONTROL_RAW_BYTES,
        "manifest_observed_bytes": control_path.stat().st_size,
        "manifest_expected_records": CONTROL_RAW_RECORDS,
        "source_records_validated": len(all_records),
        "full_routing_subset_records": len(full_controls),
        "expected_routing_subset_sha256": CONTROL_ROUTING_SUBSET_SHA256,
        "observed_routing_subset_sha256": observed_subset_sha,
        "selected_control_records": len(controls),
        "source_data_quality_status": quality["status"],
        "control_method_in_source_schema": SUBSTRATE_METHOD,
        "analysis_label": CONTROL_METHOD,
        "copied_into_challenger_raw": False,
    }
    return controls, provenance


def _cell_summary(
    rows: Sequence[dict[str, Any]], *, verifier_cap: int, challenger: bool
) -> dict[str, Any]:
    successes = sum(bool(row["outcome"]["readout_success"]) for row in rows)
    first_hits = [row["usage"]["first_success_verifier_request"] for row in rows]
    exact_observation_counts = []
    for row in rows:
        if challenger:
            exact_observation_counts.append(
                int(row["feedback_audit"]["exact_success_event_count"])
            )
            continue
        final_checkpoint = next(
            checkpoint
            for checkpoint in row["telemetry"]["checkpoints"]
            if checkpoint["completed_verifier_requests"] == verifier_cap
        )
        exact_observation_counts.append(
            int(final_checkpoint["census"]["correct_stage_eos_trials"])
        )
    restricted = [
        int(value) if value is not None else verifier_cap + 1 for value in first_hits
    ]
    usage_fields = (
        "logical_lm_node_evals",
        "full_prefix_tokens",
        "edge_selections",
    )
    result: dict[str, Any] = {
        "replicates": len(rows),
        "readout_success_count": successes,
        "readout_success_rate": successes / len(rows),
        "readout_success_wilson_95": _wilson_interval(successes, len(rows)),
        "first_exact_success_observed_count": sum(
            value is not None for value in first_hits
        ),
        "exact_success_observation_count_total": sum(exact_observation_counts),
        "mean_exact_success_observations": statistics.fmean(exact_observation_counts),
        "mean_restricted_first_exact_success_request": statistics.fmean(restricted),
        "mean_readout_correct_prefix_length": statistics.fmean(
            int(row["outcome"]["readout_correct_prefix_length"]) for row in rows
        ),
        "restricted_first_success_definition": (
            "exact first-hit request; verifier_cap + 1 for censored runs"
        ),
        "mean_usage": {
            field: statistics.fmean(float(row["usage"][field]) for row in rows)
            for field in usage_fields
        },
    }
    if challenger:
        positive = [row["outcome"]["first_positive_feedback_request"] for row in rows]
        prefix_counts = {
            str(length): sum(
                int(row["feedback_audit"]["correct_prefix_length_counts"][str(length)])
                for row in rows
            )
            for length in range(5)
        }
        result["progress_feedback"] = {
            "oracle_positive_control": True,
            "positive_feedback_observed_count": sum(
                value is not None for value in positive
            ),
            "mean_first_positive_feedback_request_among_observed": (
                statistics.fmean(int(value) for value in positive if value is not None)
                if any(value is not None for value in positive)
                else None
            ),
            "mean_best_feedback": statistics.fmean(
                row["outcome"]["best_search_feedback_numerator"]
                / row["outcome"]["best_search_feedback_denominator"]
                for row in rows
            ),
            "mean_positive_feedback_events": statistics.fmean(
                int(row["feedback_audit"]["positive_feedback_event_count"])
                for row in rows
            ),
            "mean_cumulative_feedback": statistics.fmean(
                row["feedback_audit"]["cumulative_feedback_numerator"]
                / FEEDBACK_DENOMINATOR
                for row in rows
            ),
            "event_correct_prefix_length_counts": prefix_counts,
        }
    return result


def _checkpoint_contrasts(
    controls: Sequence[dict[str, Any]],
    challengers: Sequence[dict[str, Any]],
    checkpoints: Sequence[int],
) -> list[dict[str, Any]]:
    control_by_seed = {_record_seed(row): row for row in controls}
    challenger_by_seed = {_record_seed(row): row for row in challengers}
    result = []
    for index, checkpoint in enumerate(checkpoints):
        deltas = []
        for seed in sorted(challenger_by_seed):
            control_rows = {
                row["completed_verifier_requests"]: row
                for row in control_by_seed[seed]["telemetry"]["checkpoints"]
            }
            challenger_rows = {
                row["completed_verifier_requests"]: row
                for row in challenger_by_seed[seed]["telemetry"]["checkpoints"]
            }
            deltas.append(
                float(
                    int(challenger_rows[checkpoint]["readout_success"])
                    - int(control_rows[checkpoint]["readout_success"])
                )
            )
        result.append(
            {
                "completed_feedback_requests": int(checkpoint),
                "mean_exact_success_delta": statistics.fmean(deltas),
                "paired_bootstrap_95_descriptive": _bootstrap_mean_interval(
                    deltas, DIAGNOSTIC_SEED + 1_000 + index
                ),
            }
        )
    return result


def _paired_contract_quality(
    control_by_seed: dict[int, dict[str, Any]],
    challenger_by_seed: dict[int, dict[str, Any]],
    seed_values: Sequence[int],
) -> dict[str, Any]:
    expected_sources = _routing_variant().uniform_sources
    if expected_sources is None:
        raise AssertionError("routing-only source plan is absent")
    errors: dict[str, int] = defaultdict(int)
    fingerprints: set[str] = set()
    for seed in seed_values:
        control = control_by_seed[seed]
        challenger = challenger_by_seed[seed]
        control_method = control.get("method", {})
        if (
            control_method.get("name") != SUBSTRATE_METHOD
            or not _json_exact_equal(
                control_method.get("initial_uniform_sources"),
                expected_sources.as_dict(),
            )
            or not _json_exact_equal(
                control_method.get("final_uniform_sources"),
                expected_sources.as_dict(),
            )
            or control_method.get("pruning") is not False
            or not _json_exact_equal(
                control_method.get("posterior_sd_scale"), POSTERIOR_SD_SCALE
            )
        ):
            errors["control_method"] += 1
        if not _json_exact_equal(
            control.get("search_config"), challenger.get("search_config")
        ):
            errors["paired_config"] += 1
        if not _json_exact_equal(control.get("seeds"), challenger.get("seeds")):
            errors["paired_seeds"] += 1
        control_fingerprint = control.get("search", {}).get(
            "root_candidate_fingerprint"
        )
        challenger_fingerprint = challenger.get("search", {}).get(
            "root_candidate_fingerprint"
        )
        if (
            type(control_fingerprint) is not str
            or control_fingerprint != challenger_fingerprint
        ):
            errors["paired_candidate_fingerprint"] += 1
        else:
            fingerprints.add(control_fingerprint)
    checks = {
        "control_is_fixed_routing_only": errors["control_method"] == 0,
        "paired_search_config_identical": errors["paired_config"] == 0,
        "paired_seed_plan_identical": errors["paired_seeds"] == 0,
        "paired_root_candidate_fingerprint_identical": (
            errors["paired_candidate_fingerprint"] == 0 and len(fingerprints) == 1
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "status": "PASS" if not failures else "FAIL",
        "checks": checks,
        "failures": failures,
        "details": {
            "paired_blocks": len(seed_values),
            "error_counts": dict(errors),
            "root_candidate_fingerprints": sorted(fingerprints),
        },
    }


def summarize(
    challengers: Sequence[dict[str, Any]],
    controls: Sequence[dict[str, Any]],
    *,
    seed_ids: Sequence[int],
    control_provenance: dict[str, Any],
    verifier_cap: int = VERIFIER_CAP,
    lm_node_ceiling: int = LM_NODE_CEILING,
    edge_ceiling: int = EDGE_CEILING,
    checkpoints: Sequence[int] = CHECKPOINTS,
    diagnostic_seed: int = DIAGNOSTIC_SEED,
    run_mode: str = "credit_assignment_n128",
) -> dict[str, Any]:
    seed_values = [int(seed) for seed in seed_ids]
    ordered = sorted(challengers, key=_record_seed)
    quality = validate_records(
        ordered,
        seed_ids=seed_values,
        verifier_cap=verifier_cap,
        lm_node_ceiling=lm_node_ceiling,
        edge_ceiling=edge_ceiling,
        checkpoints=checkpoints,
    )
    if quality["status"] != "PASS":
        raise ValueError(f"invalid challenger records: {quality['failures']}")
    control_by_seed = {_record_seed(record): record for record in controls}
    challenger_by_seed = {_record_seed(record): record for record in ordered}
    if set(control_by_seed) != set(seed_values) or set(challenger_by_seed) != set(
        seed_values
    ):
        raise ValueError("paired control/challenger seed blocks are incomplete")
    paired_quality = _paired_contract_quality(
        control_by_seed, challenger_by_seed, seed_values
    )
    if paired_quality["status"] != "PASS":
        raise ValueError(
            f"paired contract validation failed: {paired_quality['failures']}"
        )

    success_deltas: list[float] = []
    first_hit_deltas: list[float] = []
    resource_fields = (
        "logical_lm_node_evals",
        "full_prefix_tokens",
        "edge_selections",
    )
    resource_deltas: dict[str, list[float]] = {field: [] for field in resource_fields}
    candidate_only = reference_only = both_success = both_failure = 0
    for seed in seed_values:
        candidate = challenger_by_seed[seed]
        reference = control_by_seed[seed]
        candidate_success = int(candidate["outcome"]["readout_success"])
        reference_success = int(reference["outcome"]["readout_success"])
        success_deltas.append(float(candidate_success - reference_success))
        candidate_only += int(candidate_success == 1 and reference_success == 0)
        reference_only += int(candidate_success == 0 and reference_success == 1)
        both_success += int(candidate_success == reference_success == 1)
        both_failure += int(candidate_success == reference_success == 0)
        candidate_hit = candidate["usage"]["first_success_verifier_request"]
        reference_hit = reference["usage"]["first_success_verifier_request"]
        first_hit_deltas.append(
            float(
                (candidate_hit if candidate_hit is not None else verifier_cap + 1)
                - (reference_hit if reference_hit is not None else verifier_cap + 1)
            )
        )
        for field in resource_fields:
            resource_deltas[field].append(
                float(candidate["usage"][field] - reference["usage"][field])
            )

    mean_delta = statistics.fmean(success_deltas)
    interval = _bootstrap_mean_interval(success_deltas, diagnostic_seed)
    mcnemar = _exact_mcnemar_p(candidate_only, reference_only)
    exact_full_design = (
        run_mode == "credit_assignment_n128"
        and seed_values
        == list(range(FULL_SEED_START, FULL_SEED_START + FULL_SEED_COUNT))
        and verifier_cap == VERIFIER_CAP
        and lm_node_ceiling == LM_NODE_CEILING
        and edge_ceiling == EDGE_CEILING
        and tuple(checkpoints) == CHECKPOINTS
        and diagnostic_seed == DIAGNOSTIC_SEED
        and control_provenance.get("observed_sha256") == CONTROL_RAW_SHA256
    )
    if not exact_full_design:
        decision_status = "not_evaluated"
        action = "complete_the_fixed_n128_mechanism_diagnostic"
    elif mean_delta > 0.0 and interval[0] > 0.0 and mcnemar < 0.05:
        decision_status = "supported_credit_gain"
        action = "freeze_routing_substrate_and_test_contextual_or_chunk_feedback"
    elif mean_delta > 0.0:
        decision_status = "directional_only"
        action = "do_not_claim_gain; retain_as_directional_mechanism_evidence"
    else:
        decision_status = "no_gain"
        action = "stop_additional_sampler_tuning_on_this_toy"

    comparison = {
        "label": "prefix_progress_minus_terminal_only_control",
        "role": COMPARISON_ROLE,
        "candidate": CHALLENGER_METHOD,
        "reference": CONTROL_METHOD,
        "paired_blocks": len(seed_values),
        "endpoint": "exact_readout_success_at_request_700",
        "mean_risk_difference": mean_delta,
        "paired_percentile_bootstrap_95": interval,
        "bootstrap_replicates": BOOTSTRAP_SAMPLES,
        "bootstrap_seed": diagnostic_seed,
        "discordance": {
            "challenger_only": candidate_only,
            "control_only": reference_only,
            "both_success": both_success,
            "both_failure": both_failure,
        },
        "exact_two_sided_mcnemar_p": mcnemar,
        "holm_adjustment": False,
        "mean_restricted_first_exact_success_request_delta": statistics.fmean(
            first_hit_deltas
        ),
        "paired_bootstrap_restricted_first_exact_success_95": (
            _bootstrap_mean_interval(first_hit_deltas, diagnostic_seed + 1)
        ),
        "mean_resource_delta": {
            field: {
                "mean": statistics.fmean(values),
                "paired_bootstrap_95": _bootstrap_mean_interval(
                    values, diagnostic_seed + 100 + index
                ),
            }
            for index, (field, values) in enumerate(resource_deltas.items())
        },
    }
    summary: dict[str, Any] = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "record_type": "credit_assignment_summary",
        "comparison_role": COMPARISON_ROLE,
        "run_mode": run_mode,
        "design": {
            "task": "role_lock_d4",
            "target": list(TARGET),
            "exact_reward": EXACT_REWARD,
            "substrate": SUBSTRATE_METHOD,
            "methods": [CONTROL_METHOD, CHALLENGER_METHOD],
            "challenger_feedback": "5*longest_correct_prefix_length/4",
            "primary_endpoint": "exact_readout_success_at_request_700",
            "verifier_cap": verifier_cap,
            "lm_node_ceiling": lm_node_ceiling,
            "edge_ceiling": edge_ceiling,
            "checkpoints": list(checkpoints),
            "exploration_seed_ids": seed_values,
            "independent_randomization_unit": "exploration_seed",
            "production_raw_contains": [CHALLENGER_METHOD],
            "control_is_referenced_not_copied": True,
            "performance_validation": False,
            "oracle_positive_control": True,
        },
        "control_provenance": control_provenance,
        "data_quality": {
            "status": "PASS",
            "challenger": quality,
            "control_source_status": control_provenance["source_data_quality_status"],
            "paired_seed_blocks_complete": True,
            "paired_contract": paired_quality,
        },
        "cells": {
            CONTROL_METHOD: _cell_summary(
                controls, verifier_cap=verifier_cap, challenger=False
            ),
            CHALLENGER_METHOD: _cell_summary(
                ordered, verifier_cap=verifier_cap, challenger=True
            ),
        },
        "primary_paired_comparison": comparison,
        "checkpoint_exact_success_diagnostics": _checkpoint_contrasts(
            controls, ordered, checkpoints
        ),
        "decision": {
            "status": decision_status,
            "action": action,
            "rule": {
                "supported_credit_gain": (
                    "risk_difference > 0, bootstrap lower > 0, and exact "
                    "two-sided McNemar p < 0.05"
                ),
                "directional_only": "risk_difference > 0 but support rule unmet",
                "no_gain": "risk_difference <= 0",
            },
            "exact_full_design_evaluated": exact_full_design,
        },
        "claim_boundary": [
            "post-validation mechanism diagnostic, not new performance validation",
            "prefix progress is oracle-informed and not a deployable verifier claim",
            "exact success is never inferred from positive dense feedback",
            "results are conditional on Role-Lock D4 aligned static-token strata",
        ],
    }
    summary["summary_payload_sha256"] = _sha256_json(summary)
    json.dumps(summary, allow_nan=False)
    return summary


def render_report(summary: dict[str, Any]) -> str:
    control = summary["cells"][CONTROL_METHOD]
    challenger = summary["cells"][CHALLENGER_METHOD]
    contrast = summary["primary_paired_comparison"]
    decision = summary["decision"]
    low, high = contrast["paired_percentile_bootstrap_95"]
    return "\n".join(
        [
            "# QMC-BMGS credit-assignment diagnostic",
            "",
            f"Report schema: `{REPORT_SCHEMA_VERSION}`.",
            "",
            (
                "Role-Lock D4, routing-only substrate, exact 700 search-feedback "
                f"calls, paired n={contrast['paired_blocks']}."
            ),
            "The terminal-only control is referenced from its immutable promoted raw; "
            "the new raw contains prefix-progress rows only.",
            "",
            "| Condition | Exact successes | Rate |",
            "|---|---:|---:|",
            (
                f"| {CONTROL_METHOD} | {control['readout_success_count']}/"
                f"{control['replicates']} | {control['readout_success_rate']:.1%} |"
            ),
            (
                f"| {CHALLENGER_METHOD} | {challenger['readout_success_count']}/"
                f"{challenger['replicates']} | "
                f"{challenger['readout_success_rate']:.1%} |"
            ),
            "",
            "## Primary paired result",
            "",
            (
                f"Risk difference (prefix-progress minus terminal-only): "
                f"{contrast['mean_risk_difference']:+.1%}; paired percentile "
                f"bootstrap 95% [{low:+.1%}, {high:+.1%}]; exact two-sided "
                f"McNemar p={contrast['exact_two_sided_mcnemar_p']:.6g}."
            ),
            "",
            "## Decision",
            "",
            f"`{decision['status']}` — {decision['action']}.",
            "",
            "Positive prefix feedback is an oracle diagnostic. Exact target success "
            "and dense feedback remain separate ledgers throughout search and analysis.",
            "",
        ]
    )


def _validate_resume_records(
    records: Sequence[dict[str, Any]],
    *,
    requested_seed_ids: Sequence[int],
    verifier_cap: int,
    lm_node_ceiling: int,
    edge_ceiling: int,
    checkpoints: Sequence[int],
) -> list[int]:
    requested = {int(seed) for seed in requested_seed_ids}
    seeds = [_record_seed(record) for record in records]
    if len(seeds) != len(set(seeds)):
        raise ValueError("resume inputs contain duplicate challenger seeds")
    if not set(seeds).issubset(requested):
        raise ValueError("resume inputs contain out-of-design challenger seeds")
    if seeds:
        quality = validate_records(
            records,
            seed_ids=seeds,
            verifier_cap=verifier_cap,
            lm_node_ceiling=lm_node_ceiling,
            edge_ceiling=edge_ceiling,
            checkpoints=checkpoints,
        )
        if quality["status"] != "PASS":
            raise ValueError(f"resume validation failed: {quality['failures']}")
    return seeds


def _terminal_compatibility_run(
    policy: BenchmarkPolicy,
    *,
    task: RoleLockTask,
    verifier_cap: int,
    lm_node_ceiling: int,
    edge_ceiling: int,
    checkpoints: Sequence[int],
) -> dict[str, Any]:
    policy.verifier_budget = verifier_cap
    policy.lm_node_budget = lm_node_ceiling
    policy.edge_budget = edge_ceiling
    policy.stop_reason = "running"
    snapshots: list[dict[str, Any]] = []
    while policy.counters.verifier_requests < verifier_cap:
        _, reason = policy.search_step_budgeted(task.root)
        if reason in ("lm_budget_frontier", "edge_budget"):
            raise AssertionError("terminal compatibility smoke hit a guard")
        completed = int(policy.counters.verifier_requests)
        if completed in checkpoints:
            snapshots.append(_checkpoint_snapshot(policy, task, completed))
    policy.stop_reason = "verifier_budget"
    readout = policy.best_continuation(task.root, max_new_tokens=task.depth)
    policy.counters.evaluation_only_calls += 1
    return {
        "counters": asdict(policy.counters),
        "first_success_verifier_request": policy.first_success_verifier_request,
        "blocked_verifier_calls": policy.blocked_verifier_calls,
        "checkpoints": snapshots,
        "readout_token_ids": readout,
        "tree_value_digest": _tree_value_digest(policy),
        "uniform_stream_digest": _uniform_stream_digest(policy),
        "behavior_state_digest": _behavior_state_digest(policy),
    }


def _assert_terminal_only_nonintervention() -> None:
    task = RoleLockTask(4)
    variant = _routing_variant()
    seeds = SeedPlan(task_seed=4, exploration_seed=23, partition_seed=10_000)
    config = benchmark_config(task, variant, seeds.exploration_seed)
    historical = BenchmarkPolicy(
        RoleLockLM(task),
        RoleLockTokenizer(),
        config,
        variant=variant,
        task=task,
        seeds=seeds,
        registry=CandidateRegistry(),
        posterior_sd_scale=POSTERIOR_SD_SCALE,
    )
    compatibility = CreditAssignmentPolicy(
        RoleLockLM(task),
        RoleLockTokenizer(),
        benchmark_config(task, variant, seeds.exploration_seed),
        variant=variant,
        task=task,
        seeds=seeds,
        registry=CandidateRegistry(),
        posterior_sd_scale=POSTERIOR_SD_SCALE,
        feedback_mode="terminal_only_compatibility",
    )
    kwargs = {
        "task": task,
        "verifier_cap": 24,
        "lm_node_ceiling": 256,
        "edge_ceiling": 512,
        "checkpoints": (6, 12, 18, 24),
    }
    historical_result = _terminal_compatibility_run(historical, **kwargs)
    compatibility_result = _terminal_compatibility_run(compatibility, **kwargs)
    assert compatibility_result == historical_result
    assert len(compatibility.feedback_events) == 24


def _self_test() -> None:
    task = RoleLockTask(4)
    variant = _routing_variant()
    seeds = SeedPlan(task_seed=4, exploration_seed=0, partition_seed=10_000)
    policy = CreditAssignmentPolicy(
        RoleLockLM(task),
        RoleLockTokenizer(),
        benchmark_config(task, variant, 0),
        variant=variant,
        task=task,
        seeds=seeds,
        registry=CandidateRegistry(),
    )
    policy.verifier_budget = 2
    partial_feedback = policy._cutoff_verifier(task.root + (2, 3, 9, 9))
    assert partial_feedback == 2.5
    assert policy.counters.best_observed_return == 0.0
    assert policy.counters.first_success_lm_eval is None
    assert policy.first_success_verifier_request is None
    assert policy.first_positive_feedback_request == 1
    terminal_feedback = policy._terminal_verifier(task.root + task.target)
    assert terminal_feedback == 5.0
    assert policy.counters.best_observed_return == 5.0
    assert policy.first_success_verifier_request == 2
    ledger = policy.feedback_ledger()
    assert ledger["terminal_exact_success_nonintervention"] is True
    assert ledger["exact_success_event_count"] == 1
    assert ledger["events"][1] == [
        2,
        "terminal_eos",
        [2, 3, 4, 1],
        4,
        20,
        5,
        0,
        True,
    ]
    _assert_terminal_only_nonintervention()

    seed_ids = [0, 1]
    verifier_cap = 12
    lm_ceiling = 128
    edge_ceiling = 256
    checkpoints = (3, 6, 9, 12)
    records = run_experiment(
        seed_ids=seed_ids,
        verifier_cap=verifier_cap,
        lm_node_ceiling=lm_ceiling,
        edge_ceiling=edge_ceiling,
        checkpoints=checkpoints,
    )
    repeat = run_experiment(
        seed_ids=seed_ids,
        verifier_cap=verifier_cap,
        lm_node_ceiling=lm_ceiling,
        edge_ceiling=edge_ceiling,
        checkpoints=checkpoints,
    )
    assert [row["deterministic_digest"] for row in records] == [
        row["deterministic_digest"] for row in repeat
    ]
    quality = validate_records(
        records,
        seed_ids=seed_ids,
        verifier_cap=verifier_cap,
        lm_node_ceiling=lm_ceiling,
        edge_ceiling=edge_ceiling,
        checkpoints=checkpoints,
    )
    assert quality["status"] == "PASS", quality

    mutated = copy.deepcopy(records)
    mutated[0]["feedback_audit"]["events"][0][4] += 5
    mutated[0]["feedback_audit"]["ledger_payload_sha256"] = _sha256_json(
        _ledger_without_digest(mutated[0]["feedback_audit"])
    )
    mutated[0]["deterministic_digest"] = canonical_record_digest(mutated[0])
    assert (
        validate_records(
            mutated,
            seed_ids=seed_ids,
            verifier_cap=verifier_cap,
            lm_node_ceiling=lm_ceiling,
            edge_ceiling=edge_ceiling,
            checkpoints=checkpoints,
        )["status"]
        == "FAIL"
    )
    mutated = copy.deepcopy(records)
    mutated[0]["feedback_audit"]["events"].pop()
    mutated[0]["feedback_audit"]["event_count"] -= 1
    mutated[0]["feedback_audit"]["ledger_payload_sha256"] = _sha256_json(
        _ledger_without_digest(mutated[0]["feedback_audit"])
    )
    mutated[0]["deterministic_digest"] = canonical_record_digest(mutated[0])
    assert (
        validate_records(
            mutated,
            seed_ids=seed_ids,
            verifier_cap=verifier_cap,
            lm_node_ceiling=lm_ceiling,
            edge_ceiling=edge_ceiling,
            checkpoints=checkpoints,
        )["status"]
        == "FAIL"
    )
    mutated = copy.deepcopy(records)
    mutated[0]["feedback_audit"]["events"][0][0] = 1.0
    mutated[0]["feedback_audit"]["ledger_payload_sha256"] = _sha256_json(
        _ledger_without_digest(mutated[0]["feedback_audit"])
    )
    mutated[0]["deterministic_digest"] = canonical_record_digest(mutated[0])
    assert (
        validate_records(
            mutated,
            seed_ids=seed_ids,
            verifier_cap=verifier_cap,
            lm_node_ceiling=lm_ceiling,
            edge_ceiling=edge_ceiling,
            checkpoints=checkpoints,
        )["status"]
        == "FAIL"
    )
    try:
        _validate_resume_records(
            records + [copy.deepcopy(records[0])],
            requested_seed_ids=seed_ids,
            verifier_cap=verifier_cap,
            lm_node_ceiling=lm_ceiling,
            edge_ceiling=edge_ceiling,
            checkpoints=checkpoints,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate resume row was accepted")
    json.dumps(records, allow_nan=False)
    print("credit-assignment self-test: PASS")


def main() -> None:
    base = _repo_root() / "artifacts/work/qmc_bmgs_credit_assignment_n128"
    default_runs = base.with_name(base.name + "_prefix_progress_records.jsonl")
    default_summary = base.with_name(base.name + "_summary.json")
    default_report = base.with_name(base.name + "_report.md")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--shard", action="store_true")
    parser.add_argument("--seed-start", type=int, default=FULL_SEED_START)
    parser.add_argument("--seeds", type=int, default=FULL_SEED_COUNT)
    parser.add_argument("--progress-every", type=int, default=16)
    parser.add_argument("--resume-from", type=Path, action="append", default=[])
    parser.add_argument(
        "--control-raw", type=Path, default=_repo_root() / CONTROL_RAW_RELATIVE_PATH
    )
    parser.add_argument("--runs-jsonl", type=Path, default=default_runs)
    parser.add_argument("--summary-json", type=Path, default=default_summary)
    parser.add_argument("--report-md", type=Path, default=default_report)
    args = parser.parse_args()
    if args.self_test:
        _self_test()
        return
    if args.smoke and args.shard:
        parser.error("--smoke and --shard are mutually exclusive")
    if args.seed_start < 0 or args.seeds < 1 or args.progress_every < 0:
        parser.error("seed range must be nonnegative/nonempty and progress nonnegative")

    verifier_cap = VERIFIER_CAP
    lm_node_ceiling = LM_NODE_CEILING
    edge_ceiling = EDGE_CEILING
    checkpoints = CHECKPOINTS
    run_mode = "credit_assignment_n128"
    seed_start = args.seed_start
    seed_count = args.seeds
    if args.smoke:
        verifier_cap = 12
        lm_node_ceiling = 128
        edge_ceiling = 256
        checkpoints = (3, 6, 9, 12)
        run_mode = "smoke"
        seed_start = 0
        seed_count = 2
    elif args.shard:
        run_mode = "credit_assignment_n128_shard"

    fixed_end = FULL_SEED_START + FULL_SEED_COUNT
    if run_mode == "credit_assignment_n128" and (
        seed_start != FULL_SEED_START or seed_count != FULL_SEED_COUNT
    ):
        parser.error("production is fixed to seeds 704--831")
    if run_mode == "credit_assignment_n128_shard" and (
        seed_start < FULL_SEED_START or seed_start + seed_count > fixed_end
    ):
        parser.error("shards must be subsets of seeds 704--831")
    if run_mode == "credit_assignment_n128_shard":
        suffix = f"_s{seed_start}-{seed_start + seed_count - 1}"
        if args.runs_jsonl == default_runs:
            args.runs_jsonl = base.with_name(
                base.name + suffix + "_prefix_progress_records.jsonl"
            )
        if args.summary_json == default_summary:
            args.summary_json = base.with_name(base.name + suffix + "_summary.json")
        if args.report_md == default_report:
            args.report_md = base.with_name(base.name + suffix + "_report.md")

    seed_ids = list(range(seed_start, seed_start + seed_count))
    controls: list[dict[str, Any]] | None = None
    provenance: dict[str, Any] | None = None
    # Production and shard searches are forbidden until the complete promoted
    # control, including all 128 routing-only rows, passes byte/schema/subset
    # preflight. Selection to shard seeds happens only after that full check.
    if run_mode != "smoke":
        try:
            controls, provenance = load_immutable_control(
                args.control_raw, seed_ids=seed_ids
            )
        except (KeyError, OSError, TypeError, ValueError) as exc:
            parser.error(f"immutable control preflight failed: {exc}")
    reused = [record for path in args.resume_from for record in _read_jsonl(path)]
    try:
        reused_seeds = _validate_resume_records(
            reused,
            requested_seed_ids=seed_ids,
            verifier_cap=verifier_cap,
            lm_node_ceiling=lm_node_ceiling,
            edge_ceiling=edge_ceiling,
            checkpoints=checkpoints,
        )
    except (KeyError, TypeError, ValueError) as exc:
        parser.error(str(exc))
    fresh = run_experiment(
        seed_ids=seed_ids,
        verifier_cap=verifier_cap,
        lm_node_ceiling=lm_node_ceiling,
        edge_ceiling=edge_ceiling,
        checkpoints=checkpoints,
        progress_every=args.progress_every,
        skip_seeds=set(reused_seeds),
    )
    records = sorted(reused + fresh, key=_record_seed)
    _write_jsonl(args.runs_jsonl, records)
    reloaded = _read_jsonl(args.runs_jsonl)
    if reloaded != records:
        raise AssertionError("disk-reloaded challenger rows differ from memory")
    quality = validate_records(
        reloaded,
        seed_ids=seed_ids,
        verifier_cap=verifier_cap,
        lm_node_ceiling=lm_node_ceiling,
        edge_ceiling=edge_ceiling,
        checkpoints=checkpoints,
    )
    if quality["status"] != "PASS":
        raise ValueError(f"challenger data quality failed: {quality['failures']}")

    if run_mode == "smoke":
        payload = {
            "schema_version": SUMMARY_SCHEMA_VERSION,
            "record_type": "credit_assignment_smoke_summary",
            "run_mode": run_mode,
            "data_quality": quality,
            "records": len(reloaded),
            "decision": {"status": "not_evaluated"},
        }
        payload["summary_payload_sha256"] = _sha256_json(payload)
        report = "# Credit-assignment smoke\n\nPlumbing and strict-data checks: PASS.\n"
    else:
        if controls is None or provenance is None:
            raise AssertionError("production control preflight result was lost")
        payload = summarize(
            reloaded,
            controls,
            seed_ids=seed_ids,
            control_provenance=provenance,
            verifier_cap=verifier_cap,
            lm_node_ceiling=lm_node_ceiling,
            edge_ceiling=edge_ceiling,
            checkpoints=checkpoints,
            run_mode=run_mode,
        )
        report = render_report(payload)
    _write_json(args.summary_json, payload)
    reloaded_payload = json.loads(args.summary_json.read_text(encoding="utf-8"))
    if not _json_exact_equal(reloaded_payload, payload):
        raise AssertionError("disk-reloaded summary differs from memory")
    args.report_md.parent.mkdir(parents=True, exist_ok=True)
    args.report_md.write_text(report, encoding="utf-8")
    print(
        json.dumps(
            {
                "runs": str(args.runs_jsonl),
                "summary": str(args.summary_json),
                "report": str(args.report_md),
                "records": len(reloaded),
                "data_quality": quality["status"],
                "decision": payload["decision"]["status"],
            },
            indent=2,
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
