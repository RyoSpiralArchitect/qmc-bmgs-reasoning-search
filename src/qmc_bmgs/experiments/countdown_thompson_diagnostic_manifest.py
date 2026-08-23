#!/usr/bin/env python3
"""Seal an outcome-blind Countdown Thompson diagnostic preregistration.

The bundle created here reserves the future locked 128-task Track A cohort and
then constructs a source-disjoint 12-task engineering diagnostic.  It freezes
the exact task identities, method/proposal/budget specifications, analysis
rules, and 240-cell schedule.  It deliberately has no search runner and never
evaluates a proposal row or materializes a perturbation point.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import os
import shutil
import stat
import sys
import tempfile
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from qmc_bmgs.benchmarks.countdown import (
    RULESET_ID,
    CountdownTask,
    generate_solvable_task_suite,
)
from qmc_bmgs.experiments import countdown_track_a_canary_manifest as canary
from qmc_bmgs.substrate.budget import TrackAWorkBudget
from qmc_bmgs.substrate.countdown_search import (
    TrackABudgetProfile,
    TrackAMethodSpec,
)
from qmc_bmgs.substrate.proposals import TrackAProposalSpec
from qmc_bmgs.substrate.trace import (
    TraceValidationError,
    canonical_json,
    sha256_json,
    strict_json_loads,
)


BUNDLE_ID = "countdown_thompson_diagnostic_12_seed_26081001/v1"
LOCKED_RESERVATION_ID = "countdown_track_a_locked_128_seed_26072602/v1"
CANARY_BUNDLE_ID = "countdown_track_a_canary_12_seed_26072601/v2"
CANARY_BUNDLE_PATH = Path("docs/preregistrations/countdown_track_a_canary_v2")
CANARY_SEAL_DIGEST = "5799c9f17686f064b7c50ee741d79bfbb14a4d61b9048672068a586b258fd437"

LOCKED_TASK_COUNT = 128
LOCKED_GENERATION_SEED = 26072602
DIAGNOSTIC_TASK_COUNT = 12
DIAGNOSTIC_GENERATION_SEED = 26081001
DIAGNOSTIC_EXPLORATION_SEEDS = (7168, 7169, 7170, 7171)
EXPECTED_CELL_COUNT = 240

IMPLEMENTATION_BASE = {
    "merged_revision": "9f0f0c9d07d9e7bf66caff5f664792b2160b4ea4",
    "pull_request_url": (
        "https://github.com/RyoSpiralArchitect/qmc-bmgs-reasoning-search/pull/10"
    ),
    "repository_url": (
        "https://github.com/RyoSpiralArchitect/qmc-bmgs-reasoning-search"
    ),
}

AUTHORITY_SCHEMA_VERSION = "qmc-bmgs-countdown-thompson-diagnostic-authorities/v1"
LOCKED_SCHEMA_VERSION = "qmc-bmgs-countdown-track-a-locked-reservation/v1"
DIAGNOSTIC_TASK_SCHEMA_VERSION = "qmc-bmgs-countdown-thompson-diagnostic-tasks/v1"
PROPOSAL_SCHEMA_VERSION = "qmc-bmgs-countdown-thompson-diagnostic-proposals/v1"
METHOD_SCHEMA_VERSION = "qmc-bmgs-countdown-thompson-diagnostic-methods/v1"
BUDGET_SCHEMA_VERSION = "qmc-bmgs-countdown-thompson-diagnostic-budgets/v1"
ANALYSIS_SCHEMA_VERSION = "qmc-bmgs-countdown-thompson-diagnostic-analysis/v1"
PREREGISTRATION_SCHEMA_VERSION = (
    "qmc-bmgs-countdown-thompson-diagnostic-preregistration/v1"
)
SEAL_SCHEMA_VERSION = "qmc-bmgs-countdown-thompson-diagnostic-seal/v1"
CELL_KEY_SCHEMA_VERSION = "qmc-bmgs-countdown-thompson-diagnostic-cell-key/v1"
EXCLUSION_IDENTITY_SCHEMA_VERSION = (
    "qmc-bmgs-countdown-source-disjoint-exclusion-identity/v1"
)

COMPONENT_FILENAMES = (
    "authorities.json",
    "locked_reservation.json",
    "diagnostic_tasks.json",
    "proposals.json",
    "methods.json",
    "budgets.json",
    "analysis.json",
    "preregistration.json",
)
SEAL_FILENAME = "seal.json"
BUNDLE_FILENAMES = COMPONENT_FILENAMES + (SEAL_FILENAME,)
_BUNDLE_MEMBER_BYTE_CAP_V1 = 8 * 1024 * 1024
_BUNDLE_READ_CHUNK_BYTES = 1024 * 1024

_COMPONENT_TOP_LEVEL_FIELDS = {
    "analysis.json": {
        "analysis_order",
        "bundle_id",
        "claim_boundary",
        "dense_terminal_metrics",
        "deterministic_digest",
        "engineering_readiness",
        "integrity_gates",
        "mechanism_metrics",
        "mechanism_result_schema",
        "mechanism_thresholds",
        "oracle_positive_control",
        "schema_version",
    },
    "authorities.json": {
        "authority_order",
        "bundle_id",
        "canary_authority",
        "deterministic_digest",
        "historical_authority",
        "identity_contract",
        "ruleset_id",
        "schema_version",
    },
    "budgets.json": {
        "bundle_id",
        "deterministic_digest",
        "exact_non_primary_exhaustion_is_invalid",
        "profile_order",
        "profiles",
        "schema_version",
        "structural_guard_proof",
    },
    "diagnostic_tasks.json": {
        "accepted_task_pool_digest",
        "bundle_id",
        "cohort_role",
        "deterministic_digest",
        "exclusion_identity",
        "generation_call",
        "generation_manifest",
        "identity_contract",
        "persisted_calibration_profiles",
        "persisted_solution_witnesses",
        "ruleset_id",
        "schema_version",
        "task_count",
        "task_order",
        "tasks",
    },
    "locked_reservation.json": {
        "accepted_task_pool_digest",
        "bundle_id",
        "cohort_role",
        "deterministic_digest",
        "exclusion_identity",
        "generation_call",
        "generation_manifest",
        "identity_contract",
        "persisted_calibration_profiles",
        "persisted_solution_witnesses",
        "ruleset_id",
        "schema_version",
        "task_count",
        "task_order",
        "tasks",
    },
    "methods.json": {
        "bundle_id",
        "deterministic_digest",
        "method_order",
        "methods",
        "pairing_contract",
        "runtime_authority",
        "runtime_bindings",
        "schema_version",
    },
    "preregistration.json": {
        "bundle_id",
        "claim_boundary",
        "component_manifest_digests",
        "deterministic_digest",
        "execution_matrix",
        "implementation_base",
        "materialization_contract",
        "schema_version",
        "sealed_before_diagnostic_search_outcomes",
    },
    "proposals.json": {
        "bundle_id",
        "deterministic_digest",
        "materialization_contract",
        "policies",
        "policy_order",
        "primary_policy_id",
        "schema_version",
    },
    "seal.json": {
        "bundle_id",
        "component_files",
        "deterministic_digest",
        "implementation_base",
        "schema_version",
    },
}

_FORBIDDEN_PERSISTED_KEYS = {
    "calibration_profile",
    "calibrations",
    "events",
    "node_digest",
    "normal_digest",
    "normals",
    "point_digest",
    "proposal_row",
    "proposal_rows",
    "provider_outputs",
    "search_outcomes",
    "search_record",
    "search_records",
    "solution_witness",
    "solution_witness_digest",
    "task_specific_perturbation_points",
    "uniform_digest",
    "uniforms",
    "witness",
    "witness_digest",
}


class DiagnosticManifestError(ValueError):
    """Raised when the outcome-blind diagnostic seal fails closed."""


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return (canonical_json(payload) + "\n").encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _with_digest(core: Mapping[str, Any]) -> dict[str, Any]:
    payload = deepcopy(dict(core))
    payload["deterministic_digest"] = sha256_json(payload)
    return payload


def _compare_rational(
    numerator: int,
    denominator: int,
    operator: str,
    threshold: Mapping[str, Any],
) -> bool:
    """Compare exact fractions using integer cross multiplication only."""

    if type(numerator) is not int or type(denominator) is not int or denominator < 1:
        raise ValueError(
            "observed rational must use plain integers and denominator > 0"
        )
    if type(threshold) is not dict or set(threshold) != {
        "denominator",
        "numerator",
    }:
        raise ValueError("threshold must be an exact rational object")
    threshold_numerator = threshold["numerator"]
    threshold_denominator = threshold["denominator"]
    if (
        type(threshold_numerator) is not int
        or type(threshold_denominator) is not int
        or threshold_denominator < 1
    ):
        raise ValueError("threshold rational fields must be plain integers")
    left = numerator * threshold_denominator
    right = threshold_numerator * denominator
    if operator == ">=":
        return left >= right
    if operator == "<=":
        return left <= right
    raise ValueError("operator must be >= or <=")


def _assert_no_forbidden_material(payload: Any, *, path: str = "$") -> None:
    pending: list[tuple[Any, str]] = [(payload, path)]
    while pending:
        current, current_path = pending.pop()
        if type(current) is dict:
            forbidden = sorted(set(current) & _FORBIDDEN_PERSISTED_KEYS)
            if forbidden:
                raise DiagnosticManifestError(
                    f"forbidden outcome or material keys at {current_path}: {forbidden}"
                )
            pending.extend(
                (value, f"{current_path}.{key}")
                for key, value in reversed(tuple(current.items()))
            )
        elif type(current) is list:
            pending.extend(
                (current[index], f"{current_path}[{index}]")
                for index in range(len(current) - 1, -1, -1)
            )


def _validate_component_schemas(
    payloads: Mapping[str, Mapping[str, Any]],
) -> None:
    """Reject result smuggling and schema drift independently of regeneration."""

    if set(payloads) != set(BUNDLE_FILENAMES):
        raise DiagnosticManifestError("bundle payload closure drifted")
    for filename in BUNDLE_FILENAMES:
        payload = payloads[filename]
        if (
            type(payload) is not dict
            or set(payload) != _COMPONENT_TOP_LEVEL_FIELDS[filename]
        ):
            raise DiagnosticManifestError(
                f"component top-level schema drifted: {filename}"
            )
    for filename in ("locked_reservation.json", "diagnostic_tasks.json"):
        payload = payloads[filename]
        if type(payload["tasks"]) is not list:
            raise DiagnosticManifestError(f"task rows are invalid: {filename}")
        for row in payload["tasks"]:
            _task_from_row(row, label=filename)
    proposals = payloads["proposals.json"]["policies"]
    if type(proposals) is not list or any(
        type(row) is not dict
        or set(row) != {"execution_scope", "label", "role", "spec", "spec_digest"}
        for row in proposals
    ):
        raise DiagnosticManifestError("proposal-row schema drifted")
    methods = payloads["methods.json"]["methods"]
    if type(methods) is not list or any(
        type(row) is not dict
        or set(row)
        != {
            "exploration_seeds",
            "label",
            "replication",
            "spec",
            "spec_digest",
        }
        for row in methods
    ):
        raise DiagnosticManifestError("method-row schema drifted")
    profiles = payloads["budgets.json"]["profiles"]
    if type(profiles) is not list or any(
        type(row) is not dict or set(row) != {"spec", "spec_digest"} for row in profiles
    ):
        raise DiagnosticManifestError("budget-row schema drifted")
    schedule = payloads["preregistration.json"]["execution_matrix"].get("schedule")
    if type(schedule) is not list or any(
        type(row) is not dict or set(row) != {"cell_id", "cell_key"} for row in schedule
    ):
        raise DiagnosticManifestError("schedule-row schema drifted")


def _repository_root(repository_root: Path | None) -> Path:
    root = (
        Path(__file__).resolve().parents[3]
        if repository_root is None
        else Path(repository_root).resolve()
    )
    if root.is_symlink() or not root.is_dir():
        raise DiagnosticManifestError("repository root must be a regular directory")
    return root


def _task_from_row(row: Any, *, label: str) -> CountdownTask:
    if type(row) is not dict:
        raise DiagnosticManifestError(f"{label} task row must be an object")
    try:
        task = CountdownTask(tuple(row["inputs"]), row["target"])
    except (KeyError, TypeError, ValueError) as error:
        raise DiagnosticManifestError(f"{label} task row is invalid") from error
    if task.to_dict() != row:
        raise DiagnosticManifestError(f"{label} task row identity drifted")
    return task


def _validate_identity_sets(
    cohorts: Sequence[tuple[str, Sequence[CountdownTask]]],
) -> None:
    seen_tasks: set[str] = set()
    seen_sources: set[str] = set()
    for label, tasks in cohorts:
        for task in tasks:
            if task.task_fingerprint in seen_tasks:
                raise DiagnosticManifestError(
                    f"full task identity overlaps at cohort {label}"
                )
            if task.source_multiset_fingerprint in seen_sources:
                raise DiagnosticManifestError(
                    f"source multiset identity overlaps at cohort {label}"
                )
            seen_tasks.add(task.task_fingerprint)
            seen_sources.add(task.source_multiset_fingerprint)


def _identity_record(
    cohorts: Sequence[tuple[str, Sequence[CountdownTask]]],
    *,
    authority_digests: Mapping[str, str],
) -> dict[str, Any]:
    _validate_identity_sets(cohorts)
    task_fingerprints = sorted(
        task.task_fingerprint for _, tasks in cohorts for task in tasks
    )
    source_fingerprints = sorted(
        task.source_multiset_fingerprint for _, tasks in cohorts for task in tasks
    )
    return _with_digest(
        {
            "authority_digests": deepcopy(dict(authority_digests)),
            "cohort_order": [label for label, _ in cohorts],
            "cohorts": [
                {
                    "label": label,
                    "source_multiset_fingerprints": sorted(
                        task.source_multiset_fingerprint for task in tasks
                    ),
                    "task_count": len(tasks),
                    "task_fingerprints": sorted(
                        task.task_fingerprint for task in tasks
                    ),
                }
                for label, tasks in cohorts
            ],
            "schema_version": EXCLUSION_IDENTITY_SCHEMA_VERSION,
            "source_multiset_fingerprint_count": len(source_fingerprints),
            "source_multiset_fingerprint_digest": sha256_json(source_fingerprints),
            "source_multiset_fingerprints": source_fingerprints,
            "task_fingerprint_count": len(task_fingerprints),
            "task_fingerprint_digest": sha256_json(task_fingerprints),
            "task_fingerprints": task_fingerprints,
        }
    )


def _verified_canary(root: Path) -> canary.VerifiedCanaryBundle:
    bundle = canary.verify_track_a_canary_bundle(
        root / CANARY_BUNDLE_PATH,
        repository_root=root,
    )
    payloads = bundle.payloads
    if payloads["tasks.json"].get("bundle_id") != CANARY_BUNDLE_ID:
        raise DiagnosticManifestError("canary bundle identity drifted")
    if bundle.seal_digest != CANARY_SEAL_DIGEST:
        raise DiagnosticManifestError("canary seal authority drifted")
    return bundle


def _authority_manifest(
    root: Path,
) -> tuple[
    dict[str, Any],
    tuple[CountdownTask, ...],
    tuple[CountdownTask, ...],
    dict[str, dict[str, Any]],
]:
    bundle = _verified_canary(root)
    payloads = bundle.payloads
    historical = tuple(
        _task_from_row(row, label="historical")
        for row in payloads["exclusions.json"]["tasks"]
    )
    canary_tasks = tuple(
        _task_from_row(row, label="canary") for row in payloads["tasks.json"]["tasks"]
    )
    if len(historical) != 2 or len(canary_tasks) != 12:
        raise DiagnosticManifestError("historical/canary authority count drifted")
    _validate_identity_sets((("historical_2", historical), ("canary_12", canary_tasks)))
    canary_seal = payloads["seal.json"]
    component_receipts = {
        filename: deepcopy(canary_seal["component_files"][filename])
        for filename in (
            "exclusions.json",
            "tasks.json",
            "proposals.json",
            "methods.json",
            "budgets.json",
        )
    }
    authority = _with_digest(
        {
            "authority_order": ["historical_2", "canary_12"],
            "bundle_id": BUNDLE_ID,
            "canary_authority": {
                "bundle_id": CANARY_BUNDLE_ID,
                "bundle_path": CANARY_BUNDLE_PATH.as_posix(),
                "component_receipts": component_receipts,
                "seal_digest": bundle.seal_digest,
                "tasks": [task.to_dict() for task in canary_tasks],
            },
            "historical_authority": {
                "source": deepcopy(payloads["exclusions.json"]["source"]),
                "source_component_digest": payloads["exclusions.json"][
                    "deterministic_digest"
                ],
                "tasks": [task.to_dict() for task in historical],
            },
            "identity_contract": {
                "full_task_count": 14,
                "full_tasks_unique_and_disjoint": True,
                "source_multiset_count": 14,
                "source_multisets_unique_and_disjoint": True,
            },
            "ruleset_id": RULESET_ID,
            "schema_version": AUTHORITY_SCHEMA_VERSION,
        }
    )
    return authority, historical, canary_tasks, payloads


def _task_cohort_payload(
    *,
    bundle_id: str,
    cohort_role: str,
    count: int,
    seed: int,
    exclusions: Mapping[str, Any],
    schema_version: str,
) -> tuple[dict[str, Any], tuple[CountdownTask, ...]]:
    suite = generate_solvable_task_suite(
        count,
        seed,
        excluded_task_fingerprints=tuple(exclusions["task_fingerprints"]),
        excluded_source_multiset_fingerprints=tuple(
            exclusions["source_multiset_fingerprints"]
        ),
        excluded_identity_record_digest=exclusions["deterministic_digest"],
    )
    tasks = suite.tasks
    rows = [task.to_dict() for task in tasks]
    if len(tasks) != count:
        raise DiagnosticManifestError(f"{cohort_role} task count drifted")
    if len({task.task_fingerprint for task in tasks}) != count:
        raise DiagnosticManifestError(f"{cohort_role} repeats a full task")
    if len({task.source_multiset_fingerprint for task in tasks}) != count:
        raise DiagnosticManifestError(f"{cohort_role} repeats a source multiset")
    if set(exclusions["task_fingerprints"]) & {task.task_fingerprint for task in tasks}:
        raise DiagnosticManifestError(f"{cohort_role} overlaps excluded tasks")
    if set(exclusions["source_multiset_fingerprints"]) & {
        task.source_multiset_fingerprint for task in tasks
    }:
        raise DiagnosticManifestError(f"{cohort_role} overlaps excluded sources")
    payload = _with_digest(
        {
            "accepted_task_pool_digest": sha256_json(rows),
            "bundle_id": bundle_id,
            "cohort_role": cohort_role,
            "exclusion_identity": deepcopy(dict(exclusions)),
            "generation_call": {
                "count": count,
                "function": (
                    "qmc_bmgs.benchmarks.countdown.generate_solvable_task_suite"
                ),
                "max_attempts": suite.generation_manifest["max_attempts"],
                "seed": seed,
            },
            "generation_manifest": suite.generation_manifest,
            "identity_contract": {
                "full_tasks_disjoint_from_exclusions": True,
                "full_tasks_unique": True,
                "source_multisets_disjoint_from_exclusions": True,
                "source_multisets_unique": True,
            },
            "persisted_calibration_profiles": False,
            "persisted_solution_witnesses": False,
            "ruleset_id": RULESET_ID,
            "schema_version": schema_version,
            "task_count": count,
            "task_order": "generator_acceptance_order",
            "tasks": rows,
        }
    )
    return payload, tasks


def _proposal_manifest(
    canary_payloads: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    policies = []
    definitions = (
        (
            "heuristic",
            "greedy_rollout_target_error/v1",
            "primary_provider_neutral_proposal",
            "all_seven_methods",
        ),
        (
            "oracle_positive_control",
            "oracle_path_count_positive_control/v1",
            "positive_control_excluded_from_primary_readiness",
            "greedy_only",
        ),
    )
    for label, policy_id, role, scope in definitions:
        spec = TrackAProposalSpec(policy_id)
        policies.append(
            {
                "execution_scope": scope,
                "label": label,
                "role": role,
                "spec": spec.to_dict(),
                "spec_digest": spec.deterministic_digest,
            }
        )
    payload = _with_digest(
        {
            "bundle_id": BUNDLE_ID,
            "materialization_contract": {
                "proposal_rows_persisted_in_preregistration": False,
                "proposal_row_materialization": (
                    "lazy_visited_states_only_at_later_execution"
                ),
            },
            "policies": policies,
            "policy_order": [row["label"] for row in policies],
            "primary_policy_id": "greedy_rollout_target_error/v1",
            "schema_version": PROPOSAL_SCHEMA_VERSION,
        }
    )
    canary_rows = {
        row["label"]: row for row in canary_payloads["proposals.json"]["policies"]
    }
    for row in payload["policies"]:
        authority = canary_rows.get(row["label"])
        if authority is None or (
            authority["spec"] != row["spec"]
            or authority["spec_digest"] != row["spec_digest"]
        ):
            raise DiagnosticManifestError(
                f"proposal spec differs from canary authority: {row['label']}"
            )
    return payload


def _method_definitions() -> tuple[tuple[str, TrackAMethodSpec], ...]:
    return (
        ("greedy", TrackAMethodSpec.greedy()),
        ("beam_width_2", TrackAMethodSpec.beam_width_two()),
        ("puct_c1", TrackAMethodSpec.puct()),
        (
            "thompson_candidate_iid_v1",
            TrackAMethodSpec.candidate_thompson("iid"),
        ),
        (
            "thompson_dimnorm_iid_v2",
            TrackAMethodSpec.dimension_normalized_thompson("iid"),
        ),
        (
            "thompson_dense_iid_v3",
            TrackAMethodSpec.dimension_normalized_dense_thompson("iid"),
        ),
        (
            "thompson_greedy_anchor_dense_iid_v4",
            TrackAMethodSpec.greedy_anchored_dimension_normalized_dense_thompson("iid"),
        ),
    )


def _method_manifest(
    canary_payloads: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    runtime = canary_payloads["methods.json"]["runtime_bindings"]
    if type(runtime) is not dict or not {"search", "iid"} <= set(runtime):
        raise DiagnosticManifestError("canary runtime authority is incomplete")
    methods = []
    for label, spec in _method_definitions():
        methods.append(
            {
                "exploration_seeds": (
                    list(DIAGNOSTIC_EXPLORATION_SEEDS) if spec.stochastic else [0]
                ),
                "label": label,
                "replication": (
                    "four_nested_task_seeds"
                    if spec.stochastic
                    else "one_deterministic_run_no_fake_seed_replication"
                ),
                "spec": spec.to_dict(),
                "spec_digest": sha256_json(spec.to_dict()),
            }
        )
    return _with_digest(
        {
            "bundle_id": BUNDLE_ID,
            "method_order": [row["label"] for row in methods],
            "methods": methods,
            "pairing_contract": {
                "configuration_excluded_from_node_stream_identity": True,
                "iid_only_diagnostic": True,
                "same_task_state_seed_visit_uses_same_iid_coordinates": True,
                "sobol_comparison_closed_until_base_search_is_competitive": True,
                "v4_anchor_consumes_no_perturbation_point": True,
                "v4_first_perturbation_visit_index": 0,
            },
            "runtime_authority": {
                "canary_method_manifest_digest": canary_payloads["methods.json"][
                    "deterministic_digest"
                ],
                "canary_seal_digest": CANARY_SEAL_DIGEST,
            },
            "runtime_bindings": {
                "iid": deepcopy(runtime["iid"]),
                "search": deepcopy(runtime["search"]),
            },
            "schema_version": METHOD_SCHEMA_VERSION,
        }
    )


def _budget_profile() -> TrackABudgetProfile:
    return TrackABudgetProfile(
        profile_id="score256",
        primary_axis="legal_action_scores",
        budget=TrackAWorkBudget(
            proposal_state_evaluations=87,
            proposal_action_scores=317,
            legal_action_scores=256,
            generated_perturbation_coordinates=316,
            edge_selections=86,
            transitions=86,
            verifier_calls=18,
        ),
    )


def _budget_manifest(
    canary_payloads: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    profile = _budget_profile()
    spec = profile.to_dict()
    payload = _with_digest(
        {
            "bundle_id": BUNDLE_ID,
            "exact_non_primary_exhaustion_is_invalid": True,
            "profile_order": ["score256"],
            "profiles": [{"spec": spec, "spec_digest": sha256_json(spec)}],
            "schema_version": BUDGET_SCHEMA_VERSION,
            "structural_guard_proof": {
                "countdown_actions_per_trajectory_upper_bound": 140,
                "countdown_edges_per_trajectory": 5,
                "max_legal_actions_by_remaining_value_count": {
                    "2": 4,
                    "3": 12,
                    "4": 24,
                    "5": 40,
                    "6": 60,
                },
                "minimum_legal_actions_per_nonterminal_state": 3,
                "score256_atomic_next_selection_max_action_count": 60,
                "score256_generated_coordinate_guard": 316,
                "score256_max_complete_terminal_verifications": 17,
                "score256_max_selection_steps": 85,
                "score256_proposal_action_guard": 317,
                "score256_proposal_state_guard": 87,
                "version": "countdown-d6-atomic-guard-upper-bound/v2",
            },
        }
    )
    canary_score256 = next(
        (
            row
            for row in canary_payloads["budgets.json"]["profiles"]
            if row["spec"]["profile_id"] == "score256"
        ),
        None,
    )
    if canary_score256 is None or canary_score256 != payload["profiles"][0]:
        raise DiagnosticManifestError("score256 differs from canary authority")
    return payload


@dataclass(frozen=True)
class DiagnosticCell:
    """One exact task/proposal/method/budget/seed diagnostic cell."""

    task_fingerprint: str
    task_manifest_digest: str
    proposal_label: str
    proposal_spec_digest: str
    method_label: str
    method_spec_digest: str
    method_manifest_digest: str
    budget_profile_id: str
    budget_profile_spec_digest: str
    exploration_seed: int

    @property
    def key(self) -> dict[str, Any]:
        return {
            "budget_profile_id": self.budget_profile_id,
            "budget_profile_spec_digest": self.budget_profile_spec_digest,
            "bundle_id": BUNDLE_ID,
            "exploration_seed": self.exploration_seed,
            "method_label": self.method_label,
            "method_manifest_digest": self.method_manifest_digest,
            "method_spec_digest": self.method_spec_digest,
            "proposal_label": self.proposal_label,
            "proposal_spec_digest": self.proposal_spec_digest,
            "schema_version": CELL_KEY_SCHEMA_VERSION,
            "task_fingerprint": self.task_fingerprint,
            "task_manifest_digest": self.task_manifest_digest,
        }

    @property
    def cell_id(self) -> str:
        return sha256_json(self.key)

    def to_dict(self) -> dict[str, Any]:
        return {"cell_id": self.cell_id, "cell_key": self.key}


def _cells_from_components(
    tasks: Mapping[str, Any],
    proposals: Mapping[str, Any],
    methods: Mapping[str, Any],
    budgets: Mapping[str, Any],
) -> tuple[DiagnosticCell, ...]:
    method_rows = {row["label"]: row for row in methods["methods"]}
    budget = budgets["profiles"][0]
    cells: list[DiagnosticCell] = []
    for task in tasks["tasks"]:
        for proposal in proposals["policies"]:
            method_labels = (
                ["greedy"]
                if proposal["execution_scope"] == "greedy_only"
                else list(methods["method_order"])
            )
            for method_label in method_labels:
                method = method_rows[method_label]
                selected_source = method["spec"]["selected_source"]
                expected_seeds = (
                    [0]
                    if selected_source == "none"
                    else list(DIAGNOSTIC_EXPLORATION_SEEDS)
                )
                if method["exploration_seeds"] != expected_seeds:
                    raise DiagnosticManifestError(
                        f"method seed policy drifted: {method_label}"
                    )
                for seed in expected_seeds:
                    cells.append(
                        DiagnosticCell(
                            task_fingerprint=task["task_fingerprint"],
                            task_manifest_digest=tasks["deterministic_digest"],
                            proposal_label=proposal["label"],
                            proposal_spec_digest=proposal["spec_digest"],
                            method_label=method_label,
                            method_spec_digest=method["spec_digest"],
                            method_manifest_digest=methods["deterministic_digest"],
                            budget_profile_id=budget["spec"]["profile_id"],
                            budget_profile_spec_digest=budget["spec_digest"],
                            exploration_seed=seed,
                        )
                    )
    if len(cells) != EXPECTED_CELL_COUNT:
        raise DiagnosticManifestError(
            f"diagnostic schedule has {len(cells)} cells, expected "
            f"{EXPECTED_CELL_COUNT}"
        )
    if len({cell.cell_id for cell in cells}) != len(cells):
        raise DiagnosticManifestError("diagnostic schedule contains duplicates")
    return tuple(cells)


def _analysis_manifest() -> dict[str, Any]:
    return _with_digest(
        {
            "analysis_order": [
                "integrity_and_two_stage_replay",
                "mechanism_metrics_without_terminal_or_success_fields",
                "dense_terminal_error_metrics",
                "exact_success_and_engineering_readiness",
            ],
            "bundle_id": BUNDLE_ID,
            "claim_boundary": {
                "analysis_order_is_interpretive_not_blinding": True,
                "confidence_intervals": False,
                "engineering_escalation_gate_not_performance_claim": True,
                "method_superiority_claim": False,
                "multiplicity_inference": False,
                "p_values": False,
                "task_transfer_claim": False,
            },
            "dense_terminal_metrics": {
                "cell_order": (
                    "diagnostic task acceptance order, then exploration seed "
                    "order 7168,7169,7170,7171"
                ),
                "fields": [
                    "terminal_absolute_error_vector",
                    "terminal_value_vector",
                    "mean_terminal_absolute_error",
                    "median_terminal_absolute_error",
                    "minimum_terminal_absolute_error",
                    "mean_terminal_value",
                ],
                "method_labels": [
                    "thompson_dense_iid_v3",
                    "thompson_greedy_anchor_dense_iid_v4",
                ],
                "terminal_absolute_error": "abs(final_value-target)",
                "terminal_absolute_error_mean": (
                    "exact rational sum(error)/observation_count, reduced and "
                    "serialized as plain-integer {numerator,denominator}"
                ),
                "terminal_absolute_error_median": (
                    "sort integer errors; odd uses center integer, even uses the "
                    "exact rational mean of the two center integers; reduce and "
                    "serialize as plain-integer {numerator,denominator}"
                ),
                "terminal_value": ("max(1/(1+terminal_absolute_error),2^-1074)"),
                "terminal_value_mean": (
                    "math.fsum over cell_order and within-cell trajectory order, "
                    "divided by observation_count"
                ),
            },
            "engineering_readiness": {
                "candidate_method_order": [
                    "thompson_dimnorm_iid_v2",
                    "thompson_dense_iid_v3",
                    "thompson_greedy_anchor_dense_iid_v4",
                ],
                "decision_rule": (
                    "first method in candidate_method_order satisfying every "
                    "paired task-level margin and its method-specific guard"
                ),
                "invalid_or_missing_rule": (
                    "any missing, duplicate, extra, replay-invalid, or budget-invalid "
                    "cell invalidates the entire diagnostic before task scores"
                ),
                "failure_status": "STOP_REPAIR_NO_LOCKED_128_RUN",
                "margins": {
                    "candidate_minus_beam_width_2": {
                        "minimum_48_cell_success_count_difference": 2,
                        "operator": ">=",
                        "smallest_passing_lattice_delta": {
                            "denominator": 24,
                            "numerator": 1,
                        },
                        "threshold": {"denominator": 100, "numerator": 3},
                    },
                    "candidate_minus_greedy": {
                        "minimum_48_cell_success_count_difference": 2,
                        "operator": ">=",
                        "smallest_passing_lattice_delta": {
                            "denominator": 24,
                            "numerator": 1,
                        },
                        "threshold": {"denominator": 100, "numerator": 3},
                    },
                    "candidate_minus_puct_c1": {
                        "minimum_48_cell_success_count_difference": 0,
                        "operator": ">=",
                        "smallest_passing_lattice_delta": {
                            "denominator": 1,
                            "numerator": 0,
                        },
                        "threshold": {"denominator": 50, "numerator": -1},
                    },
                },
                "paired_delta": (
                    "for each task compute candidate task_score minus baseline "
                    "task_score, then take the equal-weight arithmetic mean of the "
                    "12 ordered task deltas"
                ),
                "success_status": ("READY_TO_PREREGISTER_LOCKED_128_EXECUTION"),
                "task_score": {
                    "deterministic": "one binary success_any at seed 0",
                    "stochastic": (
                        "arithmetic mean of ordered seed successes 7168..7171"
                    ),
                    "cross_task": "equal-weight arithmetic mean over 12 tasks",
                    "unit": "task",
                },
                "task_score_lattice": {
                    "cross_task_delta_denominator": 48,
                    "exact_comparison": (
                        "compare reduced integer fractions by cross multiplication; "
                        "do not round decimal displays"
                    ),
                    "source": "12 tasks times 4 stochastic seeds",
                },
                "v4_additional_guard": (
                    "at least one run has an unsuccessful greedy-anchor terminal "
                    "followed by a later exact-success terminal"
                ),
            },
            "integrity_gates": {
                "budget_valid": True,
                "exact_cell_set": True,
                "no_missing_duplicate_or_extra_cells": True,
                "no_non_primary_guard_binding_or_exhaustion": True,
                "no_padding_or_action_truncation": True,
                "provider_calls": 0,
                "two_stage_byte_replay": True,
            },
            "mechanism_metrics": {
                "action_count_bins": [
                    {"inclusive": [3, 7], "label": "3_7"},
                    {"inclusive": [8, 15], "label": "8_15"},
                    {"inclusive": [16, 31], "label": "16_31"},
                    {"inclusive": [32, 60], "label": "32_60"},
                ],
                "normalized_proposal_rank": (
                    "0 when action_count=1, otherwise "
                    "(one_based_proposal_rank-1)/(action_count-1)"
                ),
                "rational_aggregation": (
                    "represent every normalized rank, event mean, task-diversity "
                    "mean, improvement, and occupied-bin gap as a reduced "
                    "plain-integer {numerator,denominator}; compare thresholds by "
                    "integer cross multiplication without binary64 rounding"
                ),
                "proposal_rank_order": (
                    "descending finite prior_logp, then canonical legal-action "
                    "index ascending as the exact tie-break"
                ),
                "rank_vector_closure": (
                    "proposal row action order and scored indices must equal the "
                    "full canonical legal-action order without padding or truncation"
                ),
                "occupied_bin_gap": (
                    "max minus min of equal-event-weight mean normalized proposal "
                    "rank over bins containing at least one perturbation selection"
                ),
                "occupied_bin_minimum_count": 2,
                "occupied_bin_underflow": (
                    "fewer than two occupied bins fails the mechanism gate"
                ),
                "root_action_diversity": (
                    "per task, number of unique first perturbation-selected root "
                    "action identities across ordered seeds 7168..7171; action "
                    "identity is (action_order_digest,canonical_action_index)"
                ),
                "root_rank_event": (
                    "first perturbation-selected root action in each stochastic "
                    "cell; v4 excludes the no-RNG anchor and uses trajectory 1"
                ),
                "root_rank_event_missing": "invalidates the entire diagnostic",
                "root_rank_pair_key": "(task_fingerprint,exploration_seed)",
                "root_rank_vector_order": (
                    "diagnostic task acceptance order, then exploration seeds "
                    "7168,7169,7170,7171"
                ),
                "root_rank_vector_size_per_stochastic_method": 48,
                "top5_root_retained": "one_based_proposal_rank <= 5",
                "zero_observation_aggregate": (
                    "invalidates the entire diagnostic before metric emission"
                ),
            },
            "mechanism_result_schema": {
                "integer_fields": [
                    "root_top5_retained_count",
                    "tasks_with_multiple_root_actions",
                ],
                "rational_fields": [
                    "mean_normalized_root_rank",
                    "mean_root_action_diversity",
                    "occupied_action_bin_gap",
                    "v2_minus_v1_top5_count",
                    "v1_minus_v2_mean_normalized_root_rank",
                ],
                "rational_representation": {
                    "denominator": "positive plain integer",
                    "numerator": "plain integer",
                    "reduction": "greatest-common-divisor reduced; denominator positive",
                },
                "vector_order": (
                    "diagnostic task acceptance order, then seed order 7168..7171"
                ),
            },
            "mechanism_thresholds": {
                "v2_mean_normalized_root_rank_improvement_over_v1": {
                    "formula": "v1_mean-v2_mean",
                    "operator": ">=",
                    "threshold": {"denominator": 10, "numerator": 1},
                },
                "v2_mean_root_action_diversity_minimum": {
                    "operator": ">=",
                    "threshold": {"denominator": 2, "numerator": 3},
                },
                "v2_occupied_action_bin_gap_maximum": {
                    "operator": "<=",
                    "threshold": {"denominator": 20, "numerator": 3},
                },
                "v2_tasks_with_multiple_root_actions_minimum": {
                    "operator": ">=",
                    "threshold": {"denominator": 1, "numerator": 6},
                },
                "v2_top5_root_retained_count_improvement_over_v1": {
                    "formula": "v2_count-v1_count",
                    "operator": ">=",
                    "threshold": {"denominator": 1, "numerator": 8},
                },
            },
            "oracle_positive_control": {
                "expected_successful_cells": 12,
                "method_label": "greedy",
                "proposal_label": "oracle_positive_control",
                "role": "integrity_control_excluded_from_readiness",
            },
            "schema_version": ANALYSIS_SCHEMA_VERSION,
        }
    )


def _preregistration_manifest(
    components: Mapping[str, Mapping[str, Any]],
    cells: Sequence[DiagnosticCell],
) -> dict[str, Any]:
    schedule = [cell.to_dict() for cell in cells]
    component_digests = {
        filename: components[filename]["deterministic_digest"]
        for filename in COMPONENT_FILENAMES
        if filename != "preregistration.json"
    }
    return _with_digest(
        {
            "bundle_id": BUNDLE_ID,
            "claim_boundary": (
                "Outcome-blind engineering diagnostic preregistration only; "
                "no search outcome, proposal row, perturbation point, provider "
                "call, method superiority, or task-transfer claim is authorized."
            ),
            "component_manifest_digests": component_digests,
            "execution_matrix": {
                "budget_profiles": ["score256"],
                "cell_count": EXPECTED_CELL_COUNT,
                "deterministic_seed_policy": [0],
                "diagnostic_task_count": DIAGNOSTIC_TASK_COUNT,
                "heuristic_deterministic_cell_count": 36,
                "heuristic_stochastic_cell_count": 192,
                "matrix_scope": "reduced_preregistered_iid_diagnostic",
                "oracle_greedy_cell_count": 12,
                "schedule": schedule,
                "schedule_digest": sha256_json(schedule),
                "stochastic_seeds": list(DIAGNOSTIC_EXPLORATION_SEEDS),
            },
            "implementation_base": IMPLEMENTATION_BASE,
            "materialization_contract": {
                "precomputed_perturbation_bank_bytes": 0,
                "proposal_rows_in_bundle": 0,
                "provider_calls": 0,
                "search_records_in_bundle": 0,
                "task_specific_perturbation_points_in_bundle": 0,
            },
            "schema_version": PREREGISTRATION_SCHEMA_VERSION,
            "sealed_before_diagnostic_search_outcomes": True,
        }
    )


def _seal(component_payloads: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    receipts = {}
    for filename in COMPONENT_FILENAMES:
        payload = component_payloads[filename]
        raw = _canonical_bytes(payload)
        receipts[filename] = {
            "byte_count": len(raw),
            "deterministic_digest": payload["deterministic_digest"],
            "sha256": _sha256_bytes(raw),
        }
    return _with_digest(
        {
            "bundle_id": BUNDLE_ID,
            "component_files": receipts,
            "implementation_base": IMPLEMENTATION_BASE,
            "schema_version": SEAL_SCHEMA_VERSION,
        }
    )


def build_countdown_thompson_diagnostic_payloads(
    *, repository_root: Path | None = None
) -> dict[str, dict[str, Any]]:
    """Build all nine payloads without running any diagnostic search cell."""

    root = _repository_root(repository_root)
    authorities, historical, canary_tasks, canary_payloads = _authority_manifest(root)
    locked_exclusions = _identity_record(
        (("historical_2", historical), ("canary_12", canary_tasks)),
        authority_digests={"authorities.json": authorities["deterministic_digest"]},
    )
    locked, locked_tasks = _task_cohort_payload(
        bundle_id=LOCKED_RESERVATION_ID,
        cohort_role="locked_evaluation_reserved_not_executed",
        count=LOCKED_TASK_COUNT,
        seed=LOCKED_GENERATION_SEED,
        exclusions=locked_exclusions,
        schema_version=LOCKED_SCHEMA_VERSION,
    )
    diagnostic_exclusions = _identity_record(
        (
            ("historical_2", historical),
            ("canary_12", canary_tasks),
            ("locked_128", locked_tasks),
        ),
        authority_digests={
            "authorities.json": authorities["deterministic_digest"],
            "locked_reservation.json": locked["deterministic_digest"],
        },
    )
    diagnostic_tasks, diagnostic_task_objects = _task_cohort_payload(
        bundle_id=BUNDLE_ID,
        cohort_role="engineering_diagnostic_pre_locked_evaluation",
        count=DIAGNOSTIC_TASK_COUNT,
        seed=DIAGNOSTIC_GENERATION_SEED,
        exclusions=diagnostic_exclusions,
        schema_version=DIAGNOSTIC_TASK_SCHEMA_VERSION,
    )
    _validate_identity_sets(
        (
            ("historical_2", historical),
            ("canary_12", canary_tasks),
            ("locked_128", locked_tasks),
            ("diagnostic_12", diagnostic_task_objects),
        )
    )
    proposals = _proposal_manifest(canary_payloads)
    methods = _method_manifest(canary_payloads)
    budgets = _budget_manifest(canary_payloads)
    analysis = _analysis_manifest()
    components: dict[str, dict[str, Any]] = {
        "authorities.json": authorities,
        "locked_reservation.json": locked,
        "diagnostic_tasks.json": diagnostic_tasks,
        "proposals.json": proposals,
        "methods.json": methods,
        "budgets.json": budgets,
        "analysis.json": analysis,
    }
    cells = _cells_from_components(
        diagnostic_tasks,
        proposals,
        methods,
        budgets,
    )
    components["preregistration.json"] = _preregistration_manifest(
        components,
        cells,
    )
    payloads = {**components, SEAL_FILENAME: _seal(components)}
    _validate_component_schemas(payloads)
    _assert_no_forbidden_material(payloads)
    return deepcopy(payloads)


def _parse_canonical_object(raw: bytes, *, filename: str) -> dict[str, Any]:
    try:
        parsed = strict_json_loads(raw.decode("utf-8"))
    except (RecursionError, UnicodeDecodeError, TraceValidationError) as error:
        raise DiagnosticManifestError(f"invalid strict JSON: {filename}") from error
    if type(parsed) is not dict:
        raise DiagnosticManifestError(f"bundle JSON is not an object: {filename}")
    try:
        canonical = _canonical_bytes(parsed)
    except (RecursionError, TraceValidationError, TypeError, ValueError) as error:
        raise DiagnosticManifestError(f"invalid strict JSON: {filename}") from error
    if raw != canonical:
        raise DiagnosticManifestError(f"bundle JSON is not canonical: {filename}")
    return parsed


def _bundle_entry_stable_state(observed: os.stat_result) -> tuple[int, ...]:
    return (
        observed.st_dev,
        observed.st_ino,
        observed.st_mode,
        observed.st_nlink,
        observed.st_size,
        observed.st_mtime_ns,
        observed.st_ctime_ns,
    )


def _assert_exact_bundle_directory_closure(directory_fd: int) -> None:
    expected = set(BUNDLE_FILENAMES)
    observed: set[str] = set()
    try:
        with os.scandir(directory_fd) as entries:
            for entry in entries:
                if entry.name not in expected or entry.name in observed:
                    raise DiagnosticManifestError("bundle directory closure drifted")
                observed.add(entry.name)
    except DiagnosticManifestError:
        raise
    except OSError as error:
        raise DiagnosticManifestError(
            "bundle directory closure could not be observed"
        ) from error
    if observed != expected:
        raise DiagnosticManifestError("bundle directory closure drifted")


_BundleDirectoryGeneration = tuple[
    tuple[int, ...],
    tuple[tuple[str, tuple[int, ...]], ...],
]


def _capture_bundle_directory_generation(
    directory_fd: int,
) -> _BundleDirectoryGeneration:
    """Capture one stable collective generation for all nine bundle members."""

    try:
        directory_before = os.fstat(directory_fd)
        if not stat.S_ISDIR(directory_before.st_mode):
            raise DiagnosticManifestError("bundle path must be a regular directory")
        directory_state = _bundle_entry_stable_state(directory_before)
        _assert_exact_bundle_directory_closure(directory_fd)
        member_states: list[tuple[str, tuple[int, ...]]] = []
        for filename in BUNDLE_FILENAMES:
            observed = os.stat(
                filename,
                dir_fd=directory_fd,
                follow_symlinks=False,
            )
            if not stat.S_ISREG(observed.st_mode):
                raise DiagnosticManifestError(
                    f"bundle entry is not a regular file: {filename}"
                )
            if observed.st_size < 0 or observed.st_size > _BUNDLE_MEMBER_BYTE_CAP_V1:
                raise DiagnosticManifestError(
                    "bundle entry exceeds the v1 byte cap of "
                    f"{_BUNDLE_MEMBER_BYTE_CAP_V1}: {filename}"
                )
            member_states.append((filename, _bundle_entry_stable_state(observed)))
        directory_after = os.fstat(directory_fd)
        reobserved_states = tuple(
            (
                filename,
                _bundle_entry_stable_state(
                    os.stat(
                        filename,
                        dir_fd=directory_fd,
                        follow_symlinks=False,
                    )
                ),
            )
            for filename in BUNDLE_FILENAMES
        )
    except DiagnosticManifestError:
        raise
    except OSError as error:
        raise DiagnosticManifestError(
            "bundle collective generation could not be captured"
        ) from error
    if _bundle_entry_stable_state(
        directory_after
    ) != directory_state or reobserved_states != tuple(member_states):
        raise DiagnosticManifestError(
            "bundle changed during collective generation capture"
        )
    return directory_state, tuple(member_states)


def _open_stable_bundle_directory(
    directory: Path,
) -> tuple[int, tuple[int, ...]]:
    descriptor = -1
    try:
        named_before = os.stat(directory, follow_symlinks=False)
        if not stat.S_ISDIR(named_before.st_mode):
            raise DiagnosticManifestError("bundle path must be a regular directory")
        descriptor = os.open(
            directory,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
        )
        opened = os.fstat(descriptor)
        named_after = os.stat(directory, follow_symlinks=False)
        expected_state = _bundle_entry_stable_state(opened)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or _bundle_entry_stable_state(named_before) != expected_state
            or _bundle_entry_stable_state(named_after) != expected_state
        ):
            raise DiagnosticManifestError(
                "bundle path changed during descriptor acquisition"
            )
        return descriptor, expected_state
    except DiagnosticManifestError:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise
    except OSError as error:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise DiagnosticManifestError(
            "bundle path must be a stable regular directory"
        ) from error


def _assert_stable_bundle_directory_path(
    directory: Path,
    directory_fd: int,
    expected_state: tuple[int, ...],
) -> None:
    try:
        opened = os.fstat(directory_fd)
        named = os.stat(directory, follow_symlinks=False)
    except OSError as error:
        raise DiagnosticManifestError(
            "bundle path identity could not be reobserved"
        ) from error
    if (
        not stat.S_ISDIR(opened.st_mode)
        or not stat.S_ISDIR(named.st_mode)
        or _bundle_entry_stable_state(opened) != expected_state
        or _bundle_entry_stable_state(named) != expected_state
    ):
        raise DiagnosticManifestError("bundle path identity changed")


def _read_bounded_bundle_member_at(
    directory_fd: int,
    filename: str,
) -> bytes:
    file_fd = -1
    try:
        named_before = os.stat(
            filename,
            dir_fd=directory_fd,
            follow_symlinks=False,
        )
        if not stat.S_ISREG(named_before.st_mode):
            raise DiagnosticManifestError(
                f"bundle entry is not a regular file: {filename}"
            )
        if (
            named_before.st_size < 0
            or named_before.st_size > _BUNDLE_MEMBER_BYTE_CAP_V1
        ):
            raise DiagnosticManifestError(
                "bundle entry exceeds the v1 byte cap of "
                f"{_BUNDLE_MEMBER_BYTE_CAP_V1}: {filename}"
            )
        file_fd = os.open(
            filename,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=directory_fd,
        )
        opened = os.fstat(file_fd)
        expected_state = _bundle_entry_stable_state(opened)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_size < 0
            or opened.st_size > _BUNDLE_MEMBER_BYTE_CAP_V1
            or _bundle_entry_stable_state(named_before) != expected_state
        ):
            raise DiagnosticManifestError(
                f"bundle entry changed before descriptor acquisition: {filename}"
            )
        remaining = opened.st_size
        raw = bytearray()
        while remaining:
            chunk = os.read(
                file_fd,
                min(remaining, _BUNDLE_READ_CHUNK_BYTES),
            )
            if not chunk:
                raise DiagnosticManifestError(
                    f"bundle entry ended before its declared byte size: {filename}"
                )
            raw.extend(chunk)
            remaining -= len(chunk)
        if os.read(file_fd, 1):
            raise DiagnosticManifestError(
                f"bundle entry grew beyond its declared byte size: {filename}"
            )
        descriptor_after = os.fstat(file_fd)
        named_after = os.stat(
            filename,
            dir_fd=directory_fd,
            follow_symlinks=False,
        )
        if (
            _bundle_entry_stable_state(descriptor_after) != expected_state
            or _bundle_entry_stable_state(named_after) != expected_state
        ):
            raise DiagnosticManifestError(
                f"bundle entry changed during bounded read: {filename}"
            )
        return bytes(raw)
    except DiagnosticManifestError:
        raise
    except OSError as error:
        raise DiagnosticManifestError(
            f"bundle entry is not a stable bounded regular file: {filename}"
        ) from error
    finally:
        if file_fd >= 0:
            try:
                os.close(file_fd)
            except OSError:
                pass


def _read_bundle_snapshot_from_descriptor(
    directory_fd: int,
) -> tuple[dict[str, dict[str, Any]], dict[str, bytes]]:
    before_generation = _capture_bundle_directory_generation(directory_fd)
    payloads: dict[str, dict[str, Any]] = {}
    raw_files: dict[str, bytes] = {}
    for filename in BUNDLE_FILENAMES:
        raw = _read_bounded_bundle_member_at(directory_fd, filename)
        payloads[filename] = _parse_canonical_object(raw, filename=filename)
        raw_files[filename] = raw
    after_generation = _capture_bundle_directory_generation(directory_fd)
    if after_generation != before_generation:
        raise DiagnosticManifestError(
            "bundle member generation changed during snapshot"
        )
    return payloads, raw_files


def _require_descriptor_bound_bundle_platform() -> None:
    required_flags = ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK")
    if os.name != "posix" or any(not hasattr(os, flag) for flag in required_flags):
        raise DiagnosticManifestError(
            "descriptor-bound bundle verification is unavailable on this platform"
        )


def _read_bundle_snapshot(
    directory: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, bytes]]:
    _require_descriptor_bound_bundle_platform()
    candidate = Path(directory)
    directory_fd = -1
    try:
        directory_fd, directory_state = _open_stable_bundle_directory(candidate)
        snapshot = _read_bundle_snapshot_from_descriptor(directory_fd)
        _assert_stable_bundle_directory_path(
            candidate,
            directory_fd,
            directory_state,
        )
        return snapshot
    finally:
        if directory_fd >= 0:
            try:
                os.close(directory_fd)
            except OSError:
                pass


def _validate_local_digests(
    payloads: Mapping[str, Mapping[str, Any]],
    raw_files: Mapping[str, bytes],
) -> None:
    for filename in COMPONENT_FILENAMES:
        payload = payloads[filename]
        digest = payload.get("deterministic_digest")
        if type(digest) is not str or len(digest) != 64:
            raise DiagnosticManifestError(f"invalid component digest: {filename}")
        core = {
            key: value
            for key, value in payload.items()
            if key != "deterministic_digest"
        }
        if sha256_json(core) != digest:
            raise DiagnosticManifestError(f"component digest drifted: {filename}")
    seal = payloads[SEAL_FILENAME]
    if set(seal) != {
        "bundle_id",
        "component_files",
        "deterministic_digest",
        "implementation_base",
        "schema_version",
    }:
        raise DiagnosticManifestError("seal fields drifted")
    if (
        seal["bundle_id"] != BUNDLE_ID
        or seal["schema_version"] != SEAL_SCHEMA_VERSION
        or seal["implementation_base"] != IMPLEMENTATION_BASE
    ):
        raise DiagnosticManifestError("seal identity drifted")
    seal_core = {
        key: value for key, value in seal.items() if key != "deterministic_digest"
    }
    if sha256_json(seal_core) != seal["deterministic_digest"]:
        raise DiagnosticManifestError("seal digest drifted")
    receipts = seal["component_files"]
    if type(receipts) is not dict or set(receipts) != set(COMPONENT_FILENAMES):
        raise DiagnosticManifestError("seal component closure drifted")
    for filename in COMPONENT_FILENAMES:
        receipt = receipts[filename]
        if type(receipt) is not dict or set(receipt) != {
            "byte_count",
            "deterministic_digest",
            "sha256",
        }:
            raise DiagnosticManifestError(f"seal receipt drifted: {filename}")
        raw = raw_files[filename]
        if (
            type(receipt["byte_count"]) is not int
            or receipt["byte_count"] != len(raw)
            or receipt["sha256"] != _sha256_bytes(raw)
            or receipt["deterministic_digest"]
            != payloads[filename]["deterministic_digest"]
        ):
            raise DiagnosticManifestError(f"sealed bytes drifted: {filename}")


@dataclass(frozen=True)
class VerifiedDiagnosticBundle:
    """A verified bundle and independently reconstructed cell schedule."""

    directory: Path
    _payloads: dict[str, dict[str, Any]]
    _cells: tuple[DiagnosticCell, ...]

    @property
    def payloads(self) -> dict[str, dict[str, Any]]:
        return deepcopy(self._payloads)

    @property
    def cells(self) -> tuple[DiagnosticCell, ...]:
        return self._cells

    @property
    def seal_digest(self) -> str:
        return self._payloads[SEAL_FILENAME]["deterministic_digest"]


def verify_countdown_thompson_diagnostic_bundle(
    bundle_dir: Path,
    *,
    repository_root: Path | None = None,
) -> VerifiedDiagnosticBundle:
    """Verify bytes, authorities, regeneration, schedule, and directory closure."""

    _require_descriptor_bound_bundle_platform()
    directory = Path(bundle_dir)
    directory_fd = -1
    directory_state: tuple[int, ...] | None = None
    try:
        directory_fd, directory_state = _open_stable_bundle_directory(directory)
        payloads, raw_files = _read_bundle_snapshot_from_descriptor(directory_fd)
        _validate_component_schemas(payloads)
        _validate_local_digests(payloads, raw_files)
        _assert_no_forbidden_material(payloads)
        expected = build_countdown_thompson_diagnostic_payloads(
            repository_root=repository_root
        )
        for filename in BUNDLE_FILENAMES:
            if raw_files[filename] != _canonical_bytes(expected[filename]):
                raise DiagnosticManifestError(
                    "bundle bytes differ from independent deterministic regeneration: "
                    f"{filename}"
                )
        cells = _cells_from_components(
            payloads["diagnostic_tasks.json"],
            payloads["proposals.json"],
            payloads["methods.json"],
            payloads["budgets.json"],
        )
        schedule = [cell.to_dict() for cell in cells]
        matrix = payloads["preregistration.json"]["execution_matrix"]
        if matrix["schedule"] != schedule:
            raise DiagnosticManifestError("diagnostic schedule rows drifted")
        if matrix["schedule_digest"] != sha256_json(schedule):
            raise DiagnosticManifestError("diagnostic schedule digest drifted")
        final_payloads, final_raw_files = _read_bundle_snapshot_from_descriptor(
            directory_fd
        )
        if directory_state is None:
            raise DiagnosticManifestError(
                "bundle directory authority was not established"
            )
        _assert_stable_bundle_directory_path(
            directory,
            directory_fd,
            directory_state,
        )
        if final_payloads != payloads or final_raw_files != raw_files:
            raise DiagnosticManifestError("bundle changed during verification")
        return VerifiedDiagnosticBundle(directory, deepcopy(payloads), cells)
    finally:
        if directory_fd >= 0:
            try:
                os.close(directory_fd)
            except OSError:
                pass


def iter_countdown_thompson_diagnostic_cells(
    bundle: VerifiedDiagnosticBundle,
) -> tuple[DiagnosticCell, ...]:
    if type(bundle) is not VerifiedDiagnosticBundle:
        raise TypeError("bundle must be exactly VerifiedDiagnosticBundle")
    return bundle.cells


def _write_exclusive(path: Path, payload: Mapping[str, Any]) -> None:
    with path.open("xb") as handle:
        handle.write(_canonical_bytes(payload))
        handle.flush()
        os.fsync(handle.fileno())


def _rename_directory_noreplace(source: Path, destination: Path) -> None:
    """Atomically publish a directory while refusing an existing destination."""

    at_fdcwd = -2 if sys.platform == "darwin" else -100
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        rename = libc.renameatx_np
        rename.argtypes = (
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        )
        rename.restype = ctypes.c_int
        result = rename(
            at_fdcwd,
            os.fsencode(source),
            at_fdcwd,
            os.fsencode(destination),
            0x00000004,
        )
    elif sys.platform.startswith("linux"):
        try:
            rename = libc.renameat2
        except AttributeError as error:
            raise OSError(
                errno.ENOSYS,
                "atomic no-replace publication is unsupported",
                destination,
            ) from error
        rename.argtypes = (
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        )
        rename.restype = ctypes.c_int
        result = rename(
            at_fdcwd,
            os.fsencode(source),
            at_fdcwd,
            os.fsencode(destination),
            0x00000001,
        )
    elif sys.platform == "win32":
        os.rename(source, destination)
        return
    else:
        raise OSError(
            errno.ENOSYS,
            "atomic no-replace publication is unsupported",
            destination,
        )
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise FileExistsError(
            error_number,
            "diagnostic bundle destination exists",
            destination,
        )
    raise OSError(error_number, os.strerror(error_number), destination)


def write_countdown_thompson_diagnostic_bundle(
    output_dir: Path,
    *,
    repository_root: Path | None = None,
) -> None:
    """Atomically publish a complete bundle without overwriting a destination."""

    destination = Path(output_dir)
    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    if parent.is_symlink() or not parent.is_dir():
        raise DiagnosticManifestError("bundle parent must be a regular directory")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"diagnostic bundle destination exists: {destination}")
    lock = parent / f".{destination.name}.publish-lock"
    try:
        lock.mkdir()
    except FileExistsError as error:
        raise FileExistsError(
            f"diagnostic bundle publication is locked: {lock}"
        ) from error
    temporary: Path | None = None
    try:
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(
                f"diagnostic bundle destination exists: {destination}"
            )
        payloads = build_countdown_thompson_diagnostic_payloads(
            repository_root=repository_root
        )
        temporary = Path(
            tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=parent)
        )
        for filename in BUNDLE_FILENAMES:
            _write_exclusive(temporary / filename, payloads[filename])
        directory_fd = os.open(temporary, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        _rename_directory_noreplace(temporary, destination)
        temporary = None
        parent_fd = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        if temporary is not None:
            shutil.rmtree(temporary, ignore_errors=True)
        try:
            lock.rmdir()
        except FileNotFoundError:
            pass


def _self_test(repository_root: Path | None) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(
        prefix="qmc-thompson-diagnostic-prereg-"
    ) as temporary_root:
        output = Path(temporary_root) / "bundle"
        write_countdown_thompson_diagnostic_bundle(
            output,
            repository_root=repository_root,
        )
        verified = verify_countdown_thompson_diagnostic_bundle(
            output,
            repository_root=repository_root,
        )
        return {
            "bundle_id": BUNDLE_ID,
            "cell_count": len(verified.cells),
            "claim_boundary": (
                "manifest plumbing only; no diagnostic search outcome was opened"
            ),
            "seal_digest": verified.seal_digest,
            "status": "PASS",
        }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--create", type=Path, metavar="DIRECTORY")
    modes.add_argument("--verify", type=Path, metavar="DIRECTORY")
    modes.add_argument("--self-test", action="store_true")
    parser.add_argument(
        "--repository-root",
        type=Path,
        required=True,
        help="source checkout containing the tracked canary-v2 authority",
    )
    args = parser.parse_args(argv)
    if args.create is not None:
        write_countdown_thompson_diagnostic_bundle(
            args.create,
            repository_root=args.repository_root,
        )
        verified = verify_countdown_thompson_diagnostic_bundle(
            args.create,
            repository_root=args.repository_root,
        )
        result = {
            "bundle_id": BUNDLE_ID,
            "cell_count": len(verified.cells),
            "path": str(args.create),
            "seal_digest": verified.seal_digest,
            "status": "CREATED_AND_VERIFIED",
        }
    elif args.verify is not None:
        verified = verify_countdown_thompson_diagnostic_bundle(
            args.verify,
            repository_root=args.repository_root,
        )
        result = {
            "bundle_id": BUNDLE_ID,
            "cell_count": len(verified.cells),
            "path": str(args.verify),
            "seal_digest": verified.seal_digest,
            "status": "VERIFIED",
        }
    else:
        result = _self_test(args.repository_root)
    print(canonical_json(result))


if __name__ == "__main__":
    main()
