#!/usr/bin/env python3
"""Fresh standalone n=128 validation of the fixed two-phase sampler.

The preceding n=64 cohort selected this one validation run.  It is therefore
kept separate from that selection cohort: seeds 704--831 are the only primary
units, the two-phase switch remains fixed after verifier request 256, and all
three methods receive exactly 700 verifier-feedback calls.

Checkpoint 384 supports one bounded, descriptive pre-hit decomposition.  The
decomposition is derived from passive snapshots after search has completed;
it neither changes the search kernel nor participates in the success decision.
"""

from __future__ import annotations

import argparse
import copy
import itertools
import json
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from qmc_bmgs.experiments.fixed_verifier_budget import _bootstrap_mean_interval
from qmc_bmgs.experiments.two_phase_sampler import (
    BOOTSTRAP_SAMPLES,
    EDGE_CEILING,
    LM_NODE_CEILING,
    METHODS,
    SWITCH_REQUEST,
    VERIFIER_CAP,
    _behavior_usage,
    _checkpoint_map,
    _read_jsonl,
    _record_key,
    _sha256_json,
    _validate_records,
    _write_json,
    _write_jsonl,
    run_experiment,
    summarize,
)
from qmc_bmgs.records import canonical_record_digest


SUMMARY_SCHEMA_VERSION = "qmc-bmgs-two-phase-validation-summary/v1"
EXTENSION_SCHEMA_VERSION = "qmc-bmgs-two-phase-validation-extension/v1"
PREHIT_SCHEMA_VERSION = "qmc-bmgs-prehit-decomposition/v1"
COHORT_ID = "role_lock_d4_two_phase_standalone_validation_n128"
COHORT_ROLE = "standalone_validation"
SELECTION_ARTIFACT_ID = "role_lock_d4_20260718_two_phase_n64"
VALIDATION_SEED_START = 704
VALIDATION_SEED_COUNT = 128
VALIDATION_CHECKPOINTS = (64, 128, 256, 384, 512, 700)
DIAGNOSTIC_SEED = 313
PREHIT_WINDOW_START = 257
PREHIT_WINDOW_END = 384
PREHIT_BASELINE_REQUEST = PREHIT_WINDOW_START - 1
PREHIT_REQUEST_COUNT = PREHIT_WINDOW_END - PREHIT_WINDOW_START + 1

METRIC_FIELDS = (
    "edge_selections",
    "nonroot_visits",
    "nonroot_oracle_prefix_visits",
    "correct_stage_total_visits",
    "correct_stage_eos_trials",
)
SUCCESS_TRACE_CONTRIBUTION = {
    "edge_selections": 4,
    "nonroot_visits": 3,
    "nonroot_oracle_prefix_visits": 3,
    "correct_stage_total_visits": 1,
    "correct_stage_eos_trials": 1,
}


@dataclass(frozen=True)
class ValidationCohortSpec:
    cohort_id: str
    role: str
    selection_artifact_id: str
    checkpoints: tuple[int, ...]
    switch_request: int
    verifier_cap: int
    lm_node_ceiling: int
    edge_ceiling: int
    prehit_window_start: int
    prehit_window_end: int


FIXED_SPEC = ValidationCohortSpec(
    cohort_id=COHORT_ID,
    role=COHORT_ROLE,
    selection_artifact_id=SELECTION_ARTIFACT_ID,
    checkpoints=VALIDATION_CHECKPOINTS,
    switch_request=SWITCH_REQUEST,
    verifier_cap=VERIFIER_CAP,
    lm_node_ceiling=LM_NODE_CEILING,
    edge_ceiling=EDGE_CEILING,
    prehit_window_start=PREHIT_WINDOW_START,
    prehit_window_end=PREHIT_WINDOW_END,
)


def _smoke_spec() -> ValidationCohortSpec:
    return ValidationCohortSpec(
        cohort_id="role_lock_d4_two_phase_validation_self_test",
        role="plumbing_self_test",
        selection_artifact_id=SELECTION_ARTIFACT_ID,
        checkpoints=(3, 4, 8, 12),
        switch_request=4,
        verifier_cap=12,
        lm_node_ceiling=128,
        edge_ceiling=256,
        prehit_window_start=5,
        prehit_window_end=8,
    )


def _zero_metrics() -> dict[str, int]:
    return {field: 0 for field in METRIC_FIELDS}


def _metric_math(
    left: dict[str, int],
    right: dict[str, int],
    *,
    operation: str,
) -> dict[str, int]:
    if operation == "add":
        return {field: left[field] + right[field] for field in METRIC_FIELDS}
    if operation == "subtract":
        return {field: left[field] - right[field] for field in METRIC_FIELDS}
    raise ValueError(f"unknown metric operation: {operation}")


def _checkpoint_metrics(record: dict[str, Any], request: int) -> dict[str, int]:
    row = _checkpoint_map(record)[request]
    usage = row["usage"]
    census = row["census"]
    values = {
        "edge_selections": usage["edge_selections"],
        "nonroot_visits": census["nonroot_visits"],
        "nonroot_oracle_prefix_visits": census[
            "nonroot_oracle_prefix_visits"
        ],
        "correct_stage_total_visits": census["correct_stage_total_visits"],
        "correct_stage_eos_trials": census["correct_stage_eos_trials"],
    }
    if any(type(value) is not int for value in values.values()):
        raise TypeError("pre-hit checkpoint metrics must be exact integers")
    return values


def _first_hit_metrics(snapshot: dict[str, Any]) -> dict[str, int]:
    values = {field: snapshot[field] for field in METRIC_FIELDS}
    if any(type(value) is not int for value in values.values()):
        raise TypeError("first-hit metrics must be exact integers")
    return values


def _segment(
    *,
    request_count: int,
    counts: dict[str, int],
    eligible: bool,
) -> dict[str, Any]:
    if type(request_count) is not int or request_count < 0:
        raise ValueError("segment request count must be a nonnegative integer")
    if any(type(counts[field]) is not int or counts[field] < 0 for field in METRIC_FIELDS):
        raise ValueError("segment metric counts must be nonnegative integers")
    return {
        "request_count": request_count,
        "eligible": eligible,
        "counts": dict(counts),
    }


def _derive_decomposition(
    *,
    baseline: dict[str, int],
    endpoint: dict[str, int],
    first_success_request: int | None,
    first_success_snapshot: dict[str, int] | None,
    window_start: int = PREHIT_WINDOW_START,
    window_end: int = PREHIT_WINDOW_END,
) -> dict[str, Any]:
    """Split requests 257--384 around the first hit, excluding the hit from pre."""
    baseline_request = window_start - 1
    request_count = window_end - window_start + 1
    if window_start < 1 or window_end < window_start:
        raise ValueError("pre-hit window must be a nonempty positive request range")
    fixed_total = _metric_math(endpoint, baseline, operation="subtract")
    if any(value < 0 for value in fixed_total.values()):
        raise ValueError("fixed-window cumulative metrics must be monotone")

    zero = _zero_metrics()
    if first_success_request is not None and first_success_request <= baseline_request:
        position = "before_window"
        pre = _segment(request_count=0, counts=zero, eligible=False)
        hit = _segment(request_count=0, counts=zero, eligible=False)
        post = _segment(
            request_count=request_count,
            counts=fixed_total,
            eligible=False,
        )
    elif (
        first_success_request is not None
        and window_start <= first_success_request <= window_end
    ):
        if first_success_snapshot is None:
            raise ValueError("an in-window first hit requires its post-backup snapshot")
        position = "inside_window"
        through_hit = _metric_math(
            first_success_snapshot,
            baseline,
            operation="subtract",
        )
        pre_counts = _metric_math(
            through_hit,
            SUCCESS_TRACE_CONTRIBUTION,
            operation="subtract",
        )
        post_counts = _metric_math(
            _metric_math(fixed_total, pre_counts, operation="subtract"),
            SUCCESS_TRACE_CONTRIBUTION,
            operation="subtract",
        )
        pre = _segment(
            request_count=first_success_request - window_start,
            counts=pre_counts,
            eligible=True,
        )
        hit = _segment(
            request_count=1,
            counts=SUCCESS_TRACE_CONTRIBUTION,
            eligible=False,
        )
        post = _segment(
            request_count=window_end - first_success_request,
            counts=post_counts,
            eligible=False,
        )
    else:
        position = (
            "after_window" if first_success_request is not None else "not_observed"
        )
        pre = _segment(
            request_count=request_count,
            counts=fixed_total,
            eligible=True,
        )
        hit = _segment(request_count=0, counts=zero, eligible=False)
        post = _segment(request_count=0, counts=zero, eligible=False)

    segment_sum = _zero_metrics()
    for segment in (pre, hit, post):
        segment_sum = _metric_math(
            segment_sum,
            segment["counts"],
            operation="add",
        )
    identity_holds = (
        segment_sum == fixed_total
        and pre["request_count"] + hit["request_count"] + post["request_count"]
        == request_count
    )
    if not identity_holds:
        raise AssertionError("pre-hit segment decomposition does not close")

    payload: dict[str, Any] = {
        "schema_version": PREHIT_SCHEMA_VERSION,
        "derivation": "passive_checkpoint_difference_with_exact_first_hit_trace",
        "fixed_window_request_numbers_inclusive": [
            window_start,
            window_end,
        ],
        "baseline_completed_verifier_requests": baseline_request,
        "endpoint_completed_verifier_requests": window_end,
        "first_success_verifier_request": first_success_request,
        "first_hit_position": position,
        "success_trace_contribution": dict(SUCCESS_TRACE_CONTRIBUTION),
        "segments": {
            "pre_first_hit_exclusive": pre,
            "first_hit_request": hit,
            "post_first_hit": post,
        },
        "fixed_window_total": {
            "request_count": request_count,
            "counts": fixed_total,
        },
        "segment_identity_holds": True,
        "rates_persisted": False,
        "claim_role": "oracle_informed_descriptive_only_not_a_performance_gate",
    }
    payload["payload_digest"] = _sha256_json(payload)
    return payload


def _decomposition_from_record(
    record: dict[str, Any],
    *,
    spec: ValidationCohortSpec,
) -> dict[str, Any]:
    first_request = record["usage"]["first_success_verifier_request"]
    if first_request is not None and type(first_request) is not int:
        raise TypeError("first-success request must be an exact integer or null")
    first_snapshot = record["telemetry"]["first_success_after_backup_snapshot"]
    if first_snapshot is not None:
        if not isinstance(first_snapshot, dict):
            raise TypeError("first-success snapshot must be an object or null")
        if first_snapshot.get("completed_verifier_requests") != first_request:
            raise ValueError("first-success snapshot request does not match usage")
        first_metrics = _first_hit_metrics(first_snapshot)
    else:
        first_metrics = None
    return _derive_decomposition(
        baseline=_checkpoint_metrics(record, spec.prehit_window_start - 1),
        endpoint=_checkpoint_metrics(record, spec.prehit_window_end),
        first_success_request=first_request,
        first_success_snapshot=first_metrics,
        window_start=spec.prehit_window_start,
        window_end=spec.prehit_window_end,
    )


def _extension_for_record(
    record: dict[str, Any],
    *,
    spec: ValidationCohortSpec,
) -> dict[str, Any]:
    extension: dict[str, Any] = {
        "schema_version": EXTENSION_SCHEMA_VERSION,
        "cohort_id": spec.cohort_id,
        "cohort_role": spec.role,
        "selection_artifact_id": spec.selection_artifact_id,
        "selection_records_in_primary_analysis": False,
        "kernel_modified_for_validation": False,
        "prehit_decomposition": _decomposition_from_record(record, spec=spec),
    }
    extension["extension_payload_digest"] = _sha256_json(extension)
    return extension


def _attach_extensions(
    records: Sequence[dict[str, Any]],
    *,
    spec: ValidationCohortSpec,
) -> list[dict[str, Any]]:
    attached: list[dict[str, Any]] = []
    for source in records:
        record = copy.deepcopy(source)
        record["validation_extension"] = _extension_for_record(record, spec=spec)
        record["deterministic_digest"] = canonical_record_digest(record)
        json.dumps(record, allow_nan=False)
        attached.append(record)
    return attached


def _exact_equal(left: Any, right: Any) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return set(left) == set(right) and all(
            _exact_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _exact_equal(a, b) for a, b in zip(left, right)
        )
    return left == right


def _validate_validation_records_impl(
    records: Sequence[dict[str, Any]],
    *,
    seed_ids: Sequence[int],
    spec: ValidationCohortSpec,
) -> dict[str, Any]:
    base_quality = _validate_records(
        records,
        seed_ids=seed_ids,
        verifier_cap=spec.verifier_cap,
        lm_node_ceiling=spec.lm_node_ceiling,
        edge_ceiling=spec.edge_ceiling,
        checkpoints=spec.checkpoints,
        switch_request=spec.switch_request,
    )
    errors: Counter[str] = Counter()
    expected_keys = set(itertools.product(METHODS, [int(seed) for seed in seed_ids]))
    observed_keys: list[tuple[str, int]] = []

    for record in records:
        observed_keys.append(_record_key(record))
        extension = record.get("validation_extension")
        if not isinstance(extension, dict):
            errors["extension_schema"] += 1
            continue
        digest_payload = dict(extension)
        digest = digest_payload.pop("extension_payload_digest", None)
        if type(digest) is not str or digest != _sha256_json(digest_payload):
            errors["extension_digest"] += 1
        expected_header = {
            "schema_version": EXTENSION_SCHEMA_VERSION,
            "cohort_id": spec.cohort_id,
            "cohort_role": spec.role,
            "selection_artifact_id": spec.selection_artifact_id,
            "selection_records_in_primary_analysis": False,
            "kernel_modified_for_validation": False,
        }
        expected_extension_keys = set(expected_header) | {
            "prehit_decomposition",
            "extension_payload_digest",
        }
        if set(extension) != expected_extension_keys or any(
            not _exact_equal(extension.get(key), value)
            for key, value in expected_header.items()
        ):
            errors["cohort_contract"] += 1
        expected_decomposition = _decomposition_from_record(record, spec=spec)
        if not _exact_equal(
            extension.get("prehit_decomposition"), expected_decomposition
        ):
            errors["prehit_recomputation"] += 1

    observed_set = set(observed_keys)
    duplicate_count = len(observed_keys) - len(observed_set)
    if observed_set != expected_keys or duplicate_count:
        errors["paired_block_contract"] += 1
    if any(type(value) is not int for value in spec.checkpoints) or tuple(
        spec.checkpoints
    ) != tuple(sorted(set(spec.checkpoints))):
        errors["checkpoint_contract"] += 1
    if (
        spec.prehit_window_start - 1 not in spec.checkpoints
        or spec.prehit_window_end not in spec.checkpoints
    ):
        errors["checkpoint_contract"] += 1

    failures = []
    if base_quality["status"] != "PASS":
        failures.append("base_two_phase_contract")
    failures.extend(sorted(errors))
    status = "PASS" if not failures else "FAIL"
    return {
        "status": status,
        "checks": {
            "base_two_phase_contract": base_quality["status"] == "PASS",
            "strict_validation_extension": not errors,
            "selection_cohort_excluded": errors["cohort_contract"] == 0,
            "prehit_recomputed_exactly": errors["prehit_recomputation"] == 0,
            "complete_unique_paired_blocks": errors["paired_block_contract"] == 0,
        },
        "failures": failures,
        "details": {
            "expected_records": len(expected_keys),
            "observed_records": len(records),
            "duplicate_composite_keys": duplicate_count,
            "paired_groups": len(observed_set) // len(METHODS),
            "extension_error_counts": dict(sorted(errors.items())),
            "minimum_lm_guard_headroom": base_quality.get("details", {}).get(
                "minimum_lm_guard_headroom"
            ),
            "minimum_edge_guard_headroom": base_quality.get("details", {}).get(
                "minimum_edge_guard_headroom"
            ),
        },
        "base_contract": base_quality,
    }


def _validate_validation_records(
    records: Sequence[dict[str, Any]],
    *,
    seed_ids: Sequence[int],
    spec: ValidationCohortSpec,
) -> dict[str, Any]:
    try:
        return _validate_validation_records_impl(
            records,
            seed_ids=seed_ids,
            spec=spec,
        )
    except (
        AttributeError,
        KeyError,
        IndexError,
        TypeError,
        ValueError,
        OverflowError,
        AssertionError,
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


def _prehit_metrics(record: dict[str, Any]) -> dict[str, float | None]:
    segment = record["validation_extension"]["prehit_decomposition"]["segments"][
        "pre_first_hit_exclusive"
    ]
    requests = int(segment["request_count"])
    counts = segment["counts"]
    nonroot = int(counts["nonroot_visits"])
    if not segment["eligible"]:
        return {
            "edge_selections_per_request": None,
            "nonroot_oracle_prefix_visits_per_request": None,
            "correct_stage_total_visits_per_request": None,
            "correct_stage_eos_trials_per_request": None,
            "nonroot_oracle_prefix_visit_share": None,
        }
    return {
        "edge_selections_per_request": (
            int(counts["edge_selections"]) / requests if requests else None
        ),
        "nonroot_oracle_prefix_visits_per_request": (
            int(counts["nonroot_oracle_prefix_visits"]) / requests
            if requests
            else None
        ),
        "correct_stage_total_visits_per_request": (
            int(counts["correct_stage_total_visits"]) / requests
            if requests
            else None
        ),
        "correct_stage_eos_trials_per_request": (
            int(counts["correct_stage_eos_trials"]) / requests
            if requests
            else None
        ),
        "nonroot_oracle_prefix_visit_share": (
            int(counts["nonroot_oracle_prefix_visits"]) / nonroot
            if nonroot
            else None
        ),
    }


def _prehit_cell(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    positions = Counter(
        row["validation_extension"]["prehit_decomposition"]["first_hit_position"]
        for row in rows
    )
    segments = [
        row["validation_extension"]["prehit_decomposition"]["segments"][
            "pre_first_hit_exclusive"
        ]
        for row in rows
    ]
    eligible = [segment for segment in segments if segment["eligible"]]
    metrics = [_prehit_metrics(row) for row in rows]
    metric_summary: dict[str, Any] = {}
    for field in metrics[0]:
        values = [float(row[field]) for row in metrics if row[field] is not None]
        metric_summary[field] = {
            "defined_runs": len(values),
            "mean": statistics.fmean(values) if values else None,
        }
    return {
        "replicates": len(rows),
        "first_hit_position_counts": dict(sorted(positions.items())),
        "eligible_pre_hit_runs": len(eligible),
        "positive_exposure_runs": sum(
            int(segment["request_count"] > 0) for segment in eligible
        ),
        "total_eligible_pre_hit_requests": sum(
            int(segment["request_count"]) for segment in eligible
        ),
        "mean_metrics": metric_summary,
    }


def _prehit_contrast(
    blocks: dict[int, dict[str, dict[str, Any]]],
    *,
    candidate: str,
    reference: str,
    label: str,
    bootstrap_seed: int,
) -> dict[str, Any]:
    metric_fields = tuple(_prehit_metrics(next(iter(blocks.values()))[candidate]))
    deltas: dict[str, list[float]] = {field: [] for field in metric_fields}
    eligible_pairs = 0
    for seed in sorted(blocks):
        candidate_row = blocks[seed][candidate]
        reference_row = blocks[seed][reference]
        candidate_segment = candidate_row["validation_extension"][
            "prehit_decomposition"
        ]["segments"]["pre_first_hit_exclusive"]
        reference_segment = reference_row["validation_extension"][
            "prehit_decomposition"
        ]["segments"]["pre_first_hit_exclusive"]
        if not candidate_segment["eligible"] or not reference_segment["eligible"]:
            continue
        eligible_pairs += 1
        candidate_metrics = _prehit_metrics(candidate_row)
        reference_metrics = _prehit_metrics(reference_row)
        for field in metric_fields:
            left = candidate_metrics[field]
            right = reference_metrics[field]
            if left is not None and right is not None:
                deltas[field].append(float(left) - float(right))

    metric_results: dict[str, Any] = {}
    for index, (field, values) in enumerate(deltas.items()):
        metric_results[field] = {
            "defined_pairs": len(values),
            "mean_delta": statistics.fmean(values) if values else None,
            "median_delta": statistics.median(values) if values else None,
            "paired_bootstrap_95_nominal": (
                _bootstrap_mean_interval(values, bootstrap_seed + index)
                if values
                else None
            ),
            "positive_pairs": sum(value > 0.0 for value in values),
            "negative_pairs": sum(value < 0.0 for value in values),
            "ties": sum(value == 0.0 for value in values),
        }
    return {
        "label": label,
        "candidate": candidate,
        "reference": reference,
        "eligible_paired_blocks": eligible_pairs,
        "metric_deltas": metric_results,
    }


def _canonical_records(
    records: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    order = {method: index for index, method in enumerate(METHODS)}
    return sorted(
        records,
        key=lambda row: (
            int(row["seeds"]["exploration_seed"]),
            order[str(row["method"]["name"])],
        ),
    )


def summarize_validation(
    records: Sequence[dict[str, Any]],
    *,
    seed_ids: Sequence[int],
    spec: ValidationCohortSpec,
    diagnostic_seed: int = DIAGNOSTIC_SEED,
    run_mode: str = "validation_n128",
) -> dict[str, Any]:
    ordered = _canonical_records(records)
    quality = _validate_validation_records(ordered, seed_ids=seed_ids, spec=spec)
    if quality["status"] != "PASS":
        raise ValueError(f"invalid validation records: {quality['failures']}")
    base = summarize(
        ordered,
        seed_ids=seed_ids,
        verifier_cap=spec.verifier_cap,
        lm_node_ceiling=spec.lm_node_ceiling,
        edge_ceiling=spec.edge_ceiling,
        checkpoints=spec.checkpoints,
        switch_request=spec.switch_request,
        diagnostic_seed=diagnostic_seed,
        run_mode=run_mode,
    )
    comparisons = {
        row["label"]: row for row in base["planned_pairwise_contrasts"]
    }
    primary = [
        comparisons["two_phase_vs_routing_only"],
        comparisons["two_phase_vs_sobol_all"],
    ]
    point_deltas = [float(row["mean_success_delta"]) for row in primary]
    lower_bounds = [
        float(row["paired_bootstrap_success_95_simultaneous"][0]) for row in primary
    ]
    exact_full_design = (
        run_mode == "validation_n128"
        and [int(seed) for seed in seed_ids]
        == list(
            range(
                VALIDATION_SEED_START,
                VALIDATION_SEED_START + VALIDATION_SEED_COUNT,
            )
        )
        and spec == FIXED_SPEC
        and diagnostic_seed == DIAGNOSTIC_SEED
    )
    if not exact_full_design:
        status = "not_evaluated"
        action = "complete_the_exact_fresh_n128_validation"
        reason = "the standalone decision is reserved for the fixed complete cohort"
    elif all(lower > 0.0 for lower in lower_bounds):
        status = "supported_positive_validation"
        action = "freeze_the_sampler_and_begin_bounded_task_transfer"
        reason = "both co-primary simultaneous lower bounds are above zero"
    elif all(delta > 0.0 for delta in point_deltas):
        status = "directional_replication"
        action = "freeze_the_sampler_and_begin_bounded_task_transfer"
        reason = (
            "both co-primary point deltas are positive, but uncertainty still includes zero"
        )
    else:
        status = "direction_not_replicated"
        action = "stop_threshold_tuning_and_run_credit_assignment_ablation"
        reason = "at least one co-primary success point delta is nonpositive"

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    blocks: dict[int, dict[str, dict[str, Any]]] = defaultdict(dict)
    for record in ordered:
        method, seed = _record_key(record)
        grouped[method].append(record)
        blocks[seed][method] = record
    prehit = {
        "role": "oracle_informed_descriptive_only_not_a_performance_gate",
        "conditioning_warning": (
            "eligibility and exposure depend on the post-treatment first-success time; "
            "these are not causal contrasts"
        ),
        "fixed_window_request_numbers_inclusive": [
            spec.prehit_window_start,
            spec.prehit_window_end,
        ],
        "first_hit_request_excluded_from_pre_hit_segment": True,
        "cells": [
            {"method": method, **_prehit_cell(grouped[method])}
            for method in METHODS
        ],
        "paired_contrasts": [
            _prehit_contrast(
                blocks,
                candidate="two_phase_action_256",
                reference="sobol_routing_only",
                label="two_phase_vs_routing_only",
                bootstrap_seed=diagnostic_seed + 30_000,
            ),
            _prehit_contrast(
                blocks,
                candidate="two_phase_action_256",
                reference="sobol_all",
                label="two_phase_vs_sobol_all",
                bootstrap_seed=diagnostic_seed + 40_000,
            ),
        ],
    }

    base["schema_version"] = SUMMARY_SCHEMA_VERSION
    base["record_type"] = "two_phase_standalone_validation_summary"
    base["data_quality"] = quality
    base["design"].update(
        {
            "run_mode": run_mode,
            "cohort_id": spec.cohort_id,
            "cohort_role": spec.role,
            "selection_artifact_id": spec.selection_artifact_id,
            "selection_records_in_primary_analysis": False,
            "selection_cohort_size": 64,
            "validation_cohort_size": len(seed_ids),
            "cohort_pooling": False,
            "fresh_seed_range_inclusive": [min(seed_ids), max(seed_ids)],
            "fixed_validation_decision_evaluable": exact_full_design,
            "bootstrap_samples": BOOTSTRAP_SAMPLES,
            "selection_seed_range_inclusive": [640, 703],
            "selection_validation_seed_overlap": 0,
        }
    )
    for legacy_field in (
        "engineering_gate_evaluable",
        "prior_experiment_seed_overlap",
        "cohort_scope",
    ):
        base["design"].pop(legacy_field, None)
    base.pop("engineering_decision", None)
    base["validation_decision"] = {
        "status": status,
        "action": action,
        "reason": reason,
        "co_primary_point_deltas": {
            row["label"]: row["mean_success_delta"] for row in primary
        },
        "co_primary_simultaneous_95": {
            row["label"]: row["paired_bootstrap_success_95_simultaneous"]
            for row in primary
        },
        "predeclared_rule": {
            "supported_positive_validation": (
                "both co-primary simultaneous lower bounds are strictly positive"
            ),
            "directional_replication": (
                "both co-primary point deltas are strictly positive but the joint "
                "interval condition is not met"
            ),
            "direction_not_replicated": (
                "either co-primary point delta is nonpositive"
            ),
            "data_quality_failure": "do not interpret; repair and rerun the same seeds",
        },
        "threshold_tuning_after_this_cohort": False,
    }
    base["pre_hit_fixed_window_descriptive"] = prehit
    base["limitations"] = [
        "The switch threshold was selected from the preceding n=64 cohort.",
        "The n=64 selection cohort is not pooled into this primary analysis.",
        "This is an oracle-aligned static-token Role-Lock toy task.",
        "Pre-hit telemetry is oracle-informed, outcome-conditioned, and descriptive.",
        "Equal verifier calls are not equal total compute or deployment wall time.",
        "Uncertainty remains a nonstationary proxy, not an exact posterior.",
    ]
    return base


def _percent(value: float) -> str:
    return f"{100.0 * value:.1f}%"


def _percentage_points(value: float) -> str:
    return f"{100.0 * value:+.1f} pp"


def _optional_decimal(value: float | None) -> str:
    return "not defined" if value is None else f"{value:.4f}"


def render_validation_report(summary: dict[str, Any]) -> str:
    design = summary["design"]
    cells = {row["method"]: row for row in summary["cells"]}
    comparisons = {
        row["label"]: row for row in summary["planned_pairwise_contrasts"]
    }
    prehit_cells = {
        row["method"]: row
        for row in summary["pre_hit_fixed_window_descriptive"]["cells"]
    }
    exact_full = bool(design["fixed_validation_decision_evaluable"])
    title_suffix = "fresh n=128" if exact_full else f"provisional {design['run_mode']}"
    lines = [
        f"# Two-phase action-source standalone validation: {title_suffix}",
        "",
        "## Outcome",
        "",
        (
            f"Role-Lock D4, exact verifier cap {design['verifier_cap']}, paired "
            f"seeds {design['fresh_seed_range_inclusive'][0]}--"
            f"{design['fresh_seed_range_inclusive'][1]}. The preceding n=64 "
            "selection cohort is not pooled."
        ),
        "",
        "| Method | Readout success | LM nodes | Edges |",
        "|---|---:|---:|---:|",
    ]
    for method in METHODS:
        cell = cells[method]
        lines.append(
            f"| `{method}` | {_percent(cell['readout_success_rate'])} "
            f"({cell['readout_success_count']}/{cell['replicates']}) | "
            f"{cell['mean_usage']['logical_lm_node_evals']:.1f} | "
            f"{cell['mean_usage']['edge_selections']:.1f} |"
        )
    lines.extend(
        [
            "",
            "## Co-primary paired contrasts",
            "",
            "| Contrast | Success delta | Simultaneous 95% | McNemar p | Holm p |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for label in ("two_phase_vs_routing_only", "two_phase_vs_sobol_all"):
        row = comparisons[label]
        interval = row["paired_bootstrap_success_95_simultaneous"]
        lines.append(
            f"| `{label}` | {_percentage_points(row['mean_success_delta'])} | "
            f"[{_percentage_points(interval[0])}, "
            f"{_percentage_points(interval[1])}] | {row['mcnemar_p']:.4g} | "
            f"{row['holm_adjusted_p']:.4g} |"
        )
    decision = summary["validation_decision"]
    lines.extend(
        [
            "",
            "## Engineering decision",
            "",
            f"- Status: `{decision['status']}`.",
            f"- Action: `{decision['action']}`.",
            f"- Reason: {decision['reason']}.",
            (
                "- This closes threshold tuning for this toy task."
                if exact_full
                else "- Provisional output cannot trigger or close the validation decision."
            ),
            "",
            "## Fixed-window pre-hit telemetry (descriptive)",
            "",
            "| Method | Eligible runs | Requests | On-path / nonroot | EOS / request |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for method in METHODS:
        cell = prehit_cells[method]
        metrics = cell["mean_metrics"]
        on_path = metrics["nonroot_oracle_prefix_visit_share"]["mean"]
        eos = metrics["correct_stage_eos_trials_per_request"]["mean"]
        lines.append(
            f"| `{method}` | {cell['eligible_pre_hit_runs']} | "
            f"{cell['total_eligible_pre_hit_requests']} | "
            f"{_optional_decimal(on_path)} | {_optional_decimal(eos)} |"
        )
    quality = summary["data_quality"]
    lines.extend(
        [
            "",
            "The first-hit request itself is excluded. Eligibility depends on when "
            "success occurred, so these values explain behavior but do not estimate "
            "a causal effect or enter the decision rule.",
            "",
            "## Data quality",
            "",
            (
                f"Status: `{quality['status']}`. Records: "
                f"{quality['details']['observed_records']}; paired groups: "
                f"{quality['details']['paired_groups']}."
            ),
            "",
            "## Claim boundary",
            "",
            "This test bears only on direction within the fixed Role-Lock D4 toy. "
            "It is not evidence of transfer to natural-language reasoning.",
            "",
            "## Reproduce",
            "",
            "```bash",
            "python -m qmc_bmgs.experiments.two_phase_validation",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _rehash_extension_and_record(record: dict[str, Any]) -> None:
    extension = record["validation_extension"]
    payload = dict(extension)
    payload.pop("extension_payload_digest", None)
    extension["extension_payload_digest"] = _sha256_json(payload)
    record["deterministic_digest"] = canonical_record_digest(record)


def _self_test() -> None:
    spec = _smoke_spec()
    seed_ids = [0, 1]
    raw = run_experiment(
        seed_ids=seed_ids,
        verifier_cap=spec.verifier_cap,
        lm_node_ceiling=spec.lm_node_ceiling,
        edge_ceiling=spec.edge_ceiling,
        checkpoints=spec.checkpoints,
        switch_request=spec.switch_request,
    )
    records = _attach_extensions(raw, spec=spec)
    repeat = _attach_extensions(
        run_experiment(
            seed_ids=seed_ids,
            verifier_cap=spec.verifier_cap,
            lm_node_ceiling=spec.lm_node_ceiling,
            edge_ceiling=spec.edge_ceiling,
            checkpoints=spec.checkpoints,
            switch_request=spec.switch_request,
        ),
        spec=spec,
    )
    assert [row["deterministic_digest"] for row in records] == [
        row["deterministic_digest"] for row in repeat
    ]
    quality = _validate_validation_records(records, seed_ids=seed_ids, spec=spec)
    assert quality["status"] == "PASS"
    summary = summarize_validation(
        records,
        seed_ids=seed_ids,
        spec=spec,
        run_mode="self_test",
    )
    reversed_summary = summarize_validation(
        list(reversed(records)),
        seed_ids=seed_ids,
        spec=spec,
        run_mode="self_test",
    )
    assert summary == reversed_summary
    assert summary["validation_decision"]["status"] == "not_evaluated"

    baseline = _zero_metrics()
    endpoint = {
        "edge_selections": 500,
        "nonroot_visits": 380,
        "nonroot_oracle_prefix_visits": 250,
        "correct_stage_total_visits": 60,
        "correct_stage_eos_trials": 10,
    }
    before = _derive_decomposition(
        baseline=baseline,
        endpoint=endpoint,
        first_success_request=100,
        first_success_snapshot=None,
    )
    assert before["first_hit_position"] == "before_window"
    assert not before["segments"]["pre_first_hit_exclusive"]["eligible"]
    pre_counts = {
        "edge_selections": 170,
        "nonroot_visits": 125,
        "nonroot_oracle_prefix_visits": 80,
        "correct_stage_total_visits": 20,
        "correct_stage_eos_trials": 3,
    }
    through_hit = _metric_math(pre_counts, SUCCESS_TRACE_CONTRIBUTION, operation="add")
    inside = _derive_decomposition(
        baseline=baseline,
        endpoint=endpoint,
        first_success_request=300,
        first_success_snapshot=through_hit,
    )
    assert inside["first_hit_position"] == "inside_window"
    assert inside["segments"]["pre_first_hit_exclusive"]["request_count"] == 43
    assert inside["segments"]["pre_first_hit_exclusive"]["counts"] == pre_counts
    at_start = _derive_decomposition(
        baseline=baseline,
        endpoint=endpoint,
        first_success_request=257,
        first_success_snapshot=SUCCESS_TRACE_CONTRIBUTION,
    )
    assert at_start["segments"]["pre_first_hit_exclusive"]["request_count"] == 0
    after = _derive_decomposition(
        baseline=baseline,
        endpoint=endpoint,
        first_success_request=500,
        first_success_snapshot=None,
    )
    missing = _derive_decomposition(
        baseline=baseline,
        endpoint=endpoint,
        first_success_request=None,
        first_success_snapshot=None,
    )
    assert after["first_hit_position"] == "after_window"
    assert missing["first_hit_position"] == "not_observed"

    without_extra = run_experiment(
        seed_ids=[0],
        verifier_cap=spec.verifier_cap,
        lm_node_ceiling=spec.lm_node_ceiling,
        edge_ceiling=spec.edge_ceiling,
        checkpoints=(3, 4, 12),
        switch_request=spec.switch_request,
    )
    by_key = {_record_key(row): row for row in records}
    for old in without_extra:
        new = by_key[_record_key(old)]
        assert old["outcome"] == new["outcome"]
        assert _behavior_usage(old) == _behavior_usage(new)
        assert old["search"]["final_behavior_state_digest"] == new["search"][
            "final_behavior_state_digest"
        ]
        old_cp = _checkpoint_map(old)
        new_cp = _checkpoint_map(new)
        for request in (3, 4, 12):
            assert old_cp[request]["behavior_state_digest"] == new_cp[request][
                "behavior_state_digest"
            ]

    def assert_mutation_fails(mutator: Any) -> None:
        mutated = copy.deepcopy(records)
        mutator(mutated)
        _rehash_extension_and_record(mutated[0])
        result = _validate_validation_records(mutated, seed_ids=seed_ids, spec=spec)
        assert result["status"] == "FAIL"

    assert_mutation_fails(
        lambda rows: rows[0]["validation_extension"].__setitem__(
            "cohort_id", "selection_cohort"
        )
    )
    assert_mutation_fails(
        lambda rows: rows[0]["validation_extension"].__setitem__(
            "unexpected_but_rehashed", True
        )
    )
    assert_mutation_fails(
        lambda rows: rows[0]["validation_extension"]["prehit_decomposition"][
            "success_trace_contribution"
        ].__setitem__("edge_selections", 5)
    )
    assert_mutation_fails(
        lambda rows: rows[0]["validation_extension"]["prehit_decomposition"][
            "segments"
        ]["pre_first_hit_exclusive"].__setitem__("request_count", 999)
    )
    assert_mutation_fails(
        lambda rows: rows[0]["telemetry"]["checkpoints"].pop(2)
    )
    assert_mutation_fails(
        lambda rows: rows[0]["telemetry"]["checkpoints"][2].__setitem__(
            "completed_verifier_requests", 8.0
        )
    )
    missing_extension = copy.deepcopy(records)
    missing_extension[0].pop("validation_extension")
    missing_extension[0]["deterministic_digest"] = canonical_record_digest(
        missing_extension[0]
    )
    assert (
        _validate_validation_records(
            missing_extension,
            seed_ids=seed_ids,
            spec=spec,
        )["status"]
        == "FAIL"
    )
    try:
        _validate_resume_records(
            records + [copy.deepcopy(records[0])],
            requested_seed_ids=seed_ids,
            spec=spec,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate resume block was accepted")
    try:
        _validate_resume_records(
            records[:2],
            requested_seed_ids=seed_ids,
            spec=spec,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("incomplete resume block was accepted")
    try:
        _validate_resume_records(
            records,
            requested_seed_ids=[704, 705],
            spec=spec,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("out-of-design selection-cohort resume was accepted")
    json.dumps(summary, allow_nan=False)
    print("two-phase standalone validation self-test: PASS")


def _validate_resume_records(
    records: Sequence[dict[str, Any]],
    *,
    requested_seed_ids: Sequence[int],
    spec: ValidationCohortSpec,
) -> list[tuple[str, int]]:
    requested = set(itertools.product(METHODS, [int(seed) for seed in requested_seed_ids]))
    keys = [_record_key(record) for record in records]
    if len(keys) != len(set(keys)):
        raise ValueError("resume inputs contain duplicate composite keys")
    unexpected = sorted(set(keys) - requested)
    if unexpected:
        raise ValueError(f"resume inputs contain out-of-design cells: {unexpected[:5]}")
    methods_by_seed: dict[int, set[str]] = defaultdict(set)
    for method, seed in keys:
        methods_by_seed[seed].add(method)
    incomplete = [
        seed for seed, methods in sorted(methods_by_seed.items()) if methods != set(METHODS)
    ]
    if incomplete:
        raise ValueError(f"resume inputs contain incomplete paired blocks: {incomplete[:5]}")
    resume_seeds = sorted(methods_by_seed)
    if resume_seeds:
        quality = _validate_validation_records(
            records,
            seed_ids=resume_seeds,
            spec=spec,
        )
        if quality["status"] != "PASS":
            raise ValueError(f"resume input validation failed: {quality['failures']}")
    return keys


def main() -> None:
    base = Path.cwd() / "artifacts" / "work" / "qmc_bmgs_two_phase_validation_n128"
    default_runs = base.with_name(base.name + "_runs.jsonl")
    default_summary = base.with_name(base.name + "_summary.json")
    default_report = base.with_name(base.name + "_report.md")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--shard", action="store_true")
    parser.add_argument("--seed-start", type=int, default=VALIDATION_SEED_START)
    parser.add_argument("--seeds", type=int, default=VALIDATION_SEED_COUNT)
    parser.add_argument("--progress-every", type=int, default=32)
    parser.add_argument(
        "--resume-from",
        type=Path,
        action="append",
        default=[],
        help="Reuse fully validated matching JSONL shards before running missing cells",
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
    if args.seed_start < 0 or args.seeds < 1:
        parser.error("--seed-start must be nonnegative and --seeds positive")
    if args.progress_every < 0:
        parser.error("--progress-every must be nonnegative")

    spec = FIXED_SPEC
    run_mode = "validation_n128"
    seed_start = args.seed_start
    seed_count = args.seeds
    if args.smoke:
        spec = _smoke_spec()
        run_mode = "smoke"
        seed_start = 0
        seed_count = 2
    elif args.shard:
        run_mode = "validation_n128_shard"

    fixed_end = VALIDATION_SEED_START + VALIDATION_SEED_COUNT
    if run_mode == "validation_n128" and (
        seed_start != VALIDATION_SEED_START or seed_count != VALIDATION_SEED_COUNT
    ):
        parser.error("the standalone validation is fixed to seeds 704--831")
    if run_mode == "validation_n128_shard" and (
        seed_start < VALIDATION_SEED_START or seed_start + seed_count > fixed_end
    ):
        parser.error("validation shards must be subsets of fixed seeds 704--831")
    if run_mode == "validation_n128_shard":
        suffix = f"_s{seed_start}-{seed_start + seed_count - 1}"
        if args.runs_jsonl == default_runs:
            args.runs_jsonl = base.with_name(base.name + suffix + "_runs.jsonl")
        if args.summary_json == default_summary:
            args.summary_json = base.with_name(base.name + suffix + "_summary.json")
        if args.report_md == default_report:
            args.report_md = base.with_name(base.name + suffix + "_report.md")

    seed_ids = list(range(seed_start, seed_start + seed_count))
    reused = [record for path in args.resume_from for record in _read_jsonl(path)]
    try:
        reused_keys = _validate_resume_records(
            reused,
            requested_seed_ids=seed_ids,
            spec=spec,
        )
    except (KeyError, TypeError, ValueError) as exc:
        parser.error(str(exc))

    fresh = run_experiment(
        seed_ids=seed_ids,
        verifier_cap=spec.verifier_cap,
        lm_node_ceiling=spec.lm_node_ceiling,
        edge_ceiling=spec.edge_ceiling,
        checkpoints=spec.checkpoints,
        switch_request=spec.switch_request,
        progress_every=args.progress_every,
        skip_keys=set(reused_keys),
    )
    records = _canonical_records(reused + _attach_extensions(fresh, spec=spec))
    # Persist the deterministic raw rows before analysis so an analysis-layer
    # failure cannot discard a long fixed-cohort search run.
    _write_jsonl(args.runs_jsonl, records)
    reloaded = _read_jsonl(args.runs_jsonl)
    if records != reloaded:
        raise AssertionError("disk-reloaded records differ from in-memory records")
    reloaded_summary = summarize_validation(
        reloaded,
        seed_ids=seed_ids,
        spec=spec,
        run_mode=run_mode,
    )
    _write_json(args.summary_json, reloaded_summary)
    args.report_md.parent.mkdir(parents=True, exist_ok=True)
    args.report_md.write_text(
        render_validation_report(reloaded_summary),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "records": len(records),
                "data_quality": reloaded_summary["data_quality"]["status"],
                "disk_revalidation": "PASS",
                "decision": reloaded_summary["validation_decision"]["status"],
                "runs_jsonl": str(args.runs_jsonl),
                "summary_json": str(args.summary_json),
                "report_md": str(args.report_md),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
