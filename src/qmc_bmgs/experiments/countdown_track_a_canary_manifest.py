#!/usr/bin/env python3
"""Build and verify the outcome-blind Countdown Track A canary seal.

This module intentionally has no search runner.  It freezes task identities,
proposal and method specifications, work budgets, runtime identities, and the
complete 936-cell execution schedule without evaluating a proposal row or
materializing a task-specific perturbation point.
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
from importlib.resources import files as resource_files
from pathlib import Path
from typing import Any, Mapping, Sequence

from qmc_bmgs.benchmarks.countdown import (
    RULESET_ID,
    CountdownTask,
    generate_solvable_task_suite,
)
from qmc_bmgs.substrate.budget import TrackAWorkBudget
from qmc_bmgs.substrate.countdown_search import (
    TrackABudgetProfile,
    TrackAMethodSpec,
    search_runtime_metadata,
)
from qmc_bmgs.substrate.perturbations import perturbation_runtime_metadata
from qmc_bmgs.substrate.proposals import TrackAProposalSpec
from qmc_bmgs.substrate.trace import (
    TraceValidationError,
    canonical_json,
    sha256_json,
    strict_json_loads,
)


BUNDLE_ID = "countdown_track_a_canary_12_seed_26072601/v1"
EXCLUSION_SCHEMA_VERSION = "qmc-bmgs-countdown-track-a-exclusion-set/v1"
TASK_MANIFEST_SCHEMA_VERSION = "qmc-bmgs-countdown-track-a-task-manifest/v1"
PROPOSAL_MANIFEST_SCHEMA_VERSION = (
    "qmc-bmgs-countdown-track-a-proposal-manifest/v1"
)
METHOD_MANIFEST_SCHEMA_VERSION = "qmc-bmgs-countdown-track-a-method-manifest/v1"
BUDGET_MANIFEST_SCHEMA_VERSION = "qmc-bmgs-countdown-track-a-budget-manifest/v1"
PREREGISTRATION_SCHEMA_VERSION = "qmc-bmgs-countdown-track-a-canary-prereg/v1"
SEAL_SCHEMA_VERSION = "qmc-bmgs-countdown-track-a-canary-seal/v1"
CELL_KEY_SCHEMA_VERSION = "qmc-bmgs-countdown-track-a-canary-cell-key/v1"

HISTORICAL_SOURCE_PATH = Path(
    "docs/preregistrations/countdown_calibration_grid_v1.json"
)
HISTORICAL_PACKAGED_RESOURCE = "countdown_calibration_grid_v1.json"
HISTORICAL_SOURCE_SHA256 = (
    "aaa83740d8fea26461bbe9ea64b95f56d9e6064169cbc3adaaa228b07a96b485"
)
HISTORICAL_SOURCE_SCHEMA_VERSION = (
    "qmc-bmgs-countdown-calibration-grid-preregistration/v1"
)
HISTORICAL_TASK_FINGERPRINTS = (
    "a2c80cfde3aaeb372fa8c2628e7f61760370f6184c2ab838368578e4b504ea7d",
    "e1e2fdaf480a626266300f4d9b583e847065458be604d6b9cff2483e4478b5c6",
)

CANARY_COUNT = 12
CANARY_GENERATION_SEED = 26072601
CANARY_EXPLORATION_SEEDS = (7168, 7169, 7170, 7171)
EXPECTED_CELL_COUNT = 936

IMPLEMENTATION_BASE = {
    "merged_revision": "0917d1d7e8e637610883c6ab5901a118a59ca264",
    "pull_request_url": (
        "https://github.com/RyoSpiralArchitect/qmc-bmgs-reasoning-search/pull/3"
    ),
    "repository_url": (
        "https://github.com/RyoSpiralArchitect/qmc-bmgs-reasoning-search"
    ),
}

_FROZEN_RUNTIME_METADATA = {
    "iid": {
        "architecture": "arm64",
        "byteorder": "little",
        "device": "cpu",
        "dtype": "float64",
        "generator_version": "sha256-counter-open-unit-float51/v2",
        "iid_counter_hash": "sha256",
        "iid_open_unit_bits": 51,
        "normal_transform": {
            "clip": 1.1102230246251565e-16,
            "formula": "sqrt(2)*erfinv(2*clip(u)-1)",
            "version": "clipped-torch-erfinv-float64/v1",
        },
        "python_version": "3.13.13",
        "runtime_conformance_digest": (
            "ef329bb698ed0c91c29f76292f30a7d65e7f3802fdf92386cf2c57ade894660f"
        ),
        "source": "iid",
        "torch_git_version": "70d99e998b4955e0049d13a98d77ae1b14db1f45",
        "torch_version": "2.11.0",
    },
    "search": {
        "architecture": "arm64",
        "float_mantissa_bits": 53,
        "libc": ["", ""],
        "python_implementation": "CPython",
        "python_version": "3.13.13",
        "search_schema_version": "qmc-bmgs-track-a-countdown-search/v1",
        "version": "qmc-bmgs-track-a-search-runtime/v1",
    },
    "sobol": {
        "architecture": "arm64",
        "byteorder": "little",
        "device": "cpu",
        "dtype": "float64",
        "generator_version": "torch-sobol-full-sha256-cp-rotation-float51/v2",
        "normal_transform": {
            "clip": 1.1102230246251565e-16,
            "formula": "sqrt(2)*erfinv(2*clip(u)-1)",
            "version": "clipped-torch-erfinv-float64/v1",
        },
        "python_version": "3.13.13",
        "runtime_conformance_digest": (
            "772e3df2cd5c5c72d9e176aa18d22d23f1e3fa9952fd6323cb269eb9888d83c3"
        ),
        "sobol_maxbit": 30,
        "sobol_maxdim": 21201,
        "sobol_randomization": "full-sha256-cranley-patterson-rotation",
        "source": "sobol",
        "torch_git_version": "70d99e998b4955e0049d13a98d77ae1b14db1f45",
        "torch_version": "2.11.0",
    },
}

COMPONENT_FILENAMES = (
    "exclusions.json",
    "tasks.json",
    "proposals.json",
    "methods.json",
    "budgets.json",
    "preregistration.json",
)
SEAL_FILENAME = "seal.json"
BUNDLE_FILENAMES = COMPONENT_FILENAMES + (SEAL_FILENAME,)

_FORBIDDEN_PERSISTED_KEYS = {
    "calibration_profile",
    "calibrations",
    "events",
    "node_digest",
    "normal_digest",
    "normals",
    "point_digest",
    "proposal_row",
    "search_record",
    "solution_witness",
    "uniform_digest",
    "uniforms",
    "witness",
    "witness_digest",
}


class CanaryManifestError(ValueError):
    """Raised when a canary preregistration fails closed validation."""


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return (canonical_json(payload) + "\n").encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _with_digest(core: Mapping[str, Any]) -> dict[str, Any]:
    payload = deepcopy(dict(core))
    payload["deterministic_digest"] = sha256_json(payload)
    return payload


def _assert_no_forbidden_material(payload: Any, *, path: str = "$") -> None:
    if isinstance(payload, dict):
        forbidden = sorted(set(payload) & _FORBIDDEN_PERSISTED_KEYS)
        if forbidden:
            raise CanaryManifestError(
                f"forbidden outcome or material keys at {path}: {forbidden}"
            )
        for key, value in payload.items():
            _assert_no_forbidden_material(value, path=f"{path}.{key}")
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            _assert_no_forbidden_material(value, path=f"{path}[{index}]")


def _strict_source_bytes(raw: bytes) -> dict[str, Any]:
    if _sha256_bytes(raw) != HISTORICAL_SOURCE_SHA256:
        raise CanaryManifestError("historical exclusion source SHA-256 drifted")
    try:
        parsed = strict_json_loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, TraceValidationError) as error:
        raise CanaryManifestError(
            "historical exclusion source is not strict UTF-8 JSON"
        ) from error
    if type(parsed) is not dict:
        raise CanaryManifestError("historical exclusion source must be an object")
    if parsed.get("schema_version") != HISTORICAL_SOURCE_SCHEMA_VERSION:
        raise CanaryManifestError("historical exclusion source schema drifted")
    return parsed


def _strict_source_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise CanaryManifestError("historical exclusion source is not a regular file")
    return _strict_source_bytes(path.read_bytes())


def _packaged_historical_source() -> dict[str, Any]:
    try:
        raw = resource_files("qmc_bmgs.data").joinpath(
            HISTORICAL_PACKAGED_RESOURCE
        ).read_bytes()
    except (FileNotFoundError, ModuleNotFoundError, OSError) as error:
        raise CanaryManifestError(
            "packaged historical exclusion source is unavailable"
        ) from error
    return _strict_source_bytes(raw)


def _historical_tasks(
    repository_root: Path | None,
) -> tuple[CountdownTask, ...]:
    source = (
        _packaged_historical_source()
        if repository_root is None
        else _strict_source_json(repository_root / HISTORICAL_SOURCE_PATH)
    )
    rows = source.get("tasks")
    if type(rows) is not list:
        raise CanaryManifestError("historical exclusion source lacks task rows")
    tasks: list[CountdownTask] = []
    for row in rows:
        if type(row) is not dict:
            raise CanaryManifestError("historical task row must be an object")
        try:
            task = CountdownTask(tuple(row["inputs"]), row["target"])
        except (KeyError, TypeError, ValueError) as error:
            raise CanaryManifestError("historical task row is invalid") from error
        if task.to_dict() != row:
            raise CanaryManifestError("historical task identity is inconsistent")
        tasks.append(task)
    tasks.sort(key=lambda task: task.task_fingerprint)
    if tuple(task.task_fingerprint for task in tasks) != (
        HISTORICAL_TASK_FINGERPRINTS
    ):
        raise CanaryManifestError("historical task identity set drifted")
    if len({task.source_multiset_fingerprint for task in tasks}) != len(tasks):
        raise CanaryManifestError("historical source multisets are not unique")
    return tuple(tasks)


def _exclusion_manifest(repository_root: Path | None) -> dict[str, Any]:
    tasks = _historical_tasks(repository_root)
    return _with_digest(
        {
            "schema_version": EXCLUSION_SCHEMA_VERSION,
            "source": {
                "json_pointer": "/tasks",
                "packaged_resource": (
                    f"qmc_bmgs.data/{HISTORICAL_PACKAGED_RESOURCE}"
                ),
                "path": HISTORICAL_SOURCE_PATH.as_posix(),
                "sha256": HISTORICAL_SOURCE_SHA256,
            },
            "source_multiset_fingerprints": sorted(
                task.source_multiset_fingerprint for task in tasks
            ),
            "task_fingerprints": [task.task_fingerprint for task in tasks],
            "tasks": [task.to_dict() for task in tasks],
        }
    )


def _task_manifest(exclusions: Mapping[str, Any]) -> dict[str, Any]:
    excluded_tasks = tuple(exclusions["task_fingerprints"])
    excluded_sources = tuple(exclusions["source_multiset_fingerprints"])
    suite = generate_solvable_task_suite(
        CANARY_COUNT,
        CANARY_GENERATION_SEED,
        excluded_task_fingerprints=excluded_tasks,
        excluded_source_multiset_fingerprints=excluded_sources,
        excluded_identity_record_digest=exclusions["deterministic_digest"],
    )
    task_rows = [task.to_dict() for task in suite.tasks]
    task_fingerprints = [task.task_fingerprint for task in suite.tasks]
    source_fingerprints = [
        task.source_multiset_fingerprint for task in suite.tasks
    ]
    if len(set(task_fingerprints)) != CANARY_COUNT:
        raise CanaryManifestError("generated canary repeats a full task identity")
    if len(set(source_fingerprints)) != CANARY_COUNT:
        raise CanaryManifestError("generated canary repeats a source multiset")
    if set(task_fingerprints) & set(excluded_tasks):
        raise CanaryManifestError("generated canary overlaps excluded tasks")
    if set(source_fingerprints) & set(excluded_sources):
        raise CanaryManifestError("generated canary overlaps excluded sources")
    return _with_digest(
        {
            "accepted_task_pool_digest": sha256_json(task_rows),
            "bundle_id": BUNDLE_ID,
            "cohort_role": "canary_development",
            "exclusion_manifest_digest": exclusions["deterministic_digest"],
            "generation_call": {
                "count": CANARY_COUNT,
                "function": (
                    "qmc_bmgs.benchmarks.countdown."
                    "generate_solvable_task_suite"
                ),
                "max_attempts": suite.generation_manifest["max_attempts"],
                "seed": CANARY_GENERATION_SEED,
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
            "schema_version": TASK_MANIFEST_SCHEMA_VERSION,
            "task_count": CANARY_COUNT,
            "task_order": "generator_acceptance_order",
            "tasks": task_rows,
        }
    )


def _proposal_manifest() -> dict[str, Any]:
    definitions = (
        (
            "uniform",
            "uniform/v1",
            "proposal_quality_control",
            "all_seven_methods",
        ),
        (
            "heuristic",
            "greedy_rollout_target_error/v1",
            "primary_provider_neutral_proposal",
            "all_seven_methods",
        ),
        (
            "oracle_positive_control",
            "oracle_path_count_positive_control/v1",
            "positive_control_excluded_from_primary_estimands",
            "greedy_only",
        ),
    )
    policies = []
    for label, policy_id, role, execution_scope in definitions:
        spec = TrackAProposalSpec(policy_id)
        policies.append(
            {
                "execution_scope": execution_scope,
                "label": label,
                "role": role,
                "spec": spec.to_dict(),
                "spec_digest": spec.deterministic_digest,
            }
        )
    return _with_digest(
        {
            "bundle_id": BUNDLE_ID,
            "materialization_contract": {
                "full_reachable_dag_snapshot": False,
                "proposal_rows": "lazy_visited_states_only",
                "proposal_rows_persisted_in_preregistration": False,
            },
            "policies": policies,
            "policy_order": [row["label"] for row in policies],
            "primary_policy_id": "greedy_rollout_target_error/v1",
            "schema_version": PROPOSAL_MANIFEST_SCHEMA_VERSION,
        }
    )


def _method_definitions() -> tuple[tuple[str, TrackAMethodSpec], ...]:
    return (
        ("greedy", TrackAMethodSpec.greedy()),
        ("beam_width_2", TrackAMethodSpec.beam_width_two()),
        ("puct_c1", TrackAMethodSpec.puct()),
        ("thompson_frozen_iid", TrackAMethodSpec.frozen_thompson("iid")),
        ("thompson_frozen_sobol", TrackAMethodSpec.frozen_thompson("sobol")),
        ("thompson_candidate_iid", TrackAMethodSpec.candidate_thompson("iid")),
        (
            "thompson_candidate_sobol",
            TrackAMethodSpec.candidate_thompson("sobol"),
        ),
    )


def frozen_track_a_canary_runtime_bindings() -> dict[str, dict[str, Any]]:
    """Return the sealed execution runtime independent of the ambient host."""

    return {
        label: {
            "digest": sha256_json(metadata),
            "metadata": deepcopy(metadata),
        }
        for label, metadata in _FROZEN_RUNTIME_METADATA.items()
    }


def qualify_track_a_canary_runtime() -> dict[str, Any]:
    """Fail closed unless the live runtime matches the sealed execution runtime."""

    expected = frozen_track_a_canary_runtime_bindings()
    observed_metadata = {
        "iid": perturbation_runtime_metadata("iid"),
        "search": search_runtime_metadata(),
        "sobol": perturbation_runtime_metadata("sobol"),
    }
    for label, metadata in observed_metadata.items():
        try:
            observed_bytes = _canonical_bytes(metadata)
        except (TraceValidationError, TypeError, ValueError) as error:
            raise CanaryManifestError(
                f"live {label} runtime metadata is invalid"
            ) from error
        if observed_bytes != _canonical_bytes(expected[label]["metadata"]):
            raise CanaryManifestError(
                f"live {label} runtime does not match the frozen canary runtime"
            )
    return {
        "bundle_id": BUNDLE_ID,
        "runtime_bindings_digest": sha256_json(expected),
        "status": "QUALIFIED",
    }


def _method_manifest() -> dict[str, Any]:
    methods = []
    for label, spec in _method_definitions():
        seeds = list(CANARY_EXPLORATION_SEEDS) if spec.stochastic else [0]
        methods.append(
            {
                "exploration_seeds": seeds,
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
                "iid_and_sobol_are_distinct_streams": True,
                "iid_sobol_common_random_numbers_claimed": False,
                "same_source_same_task_state_seed_visit_is_paired": True,
            },
            "runtime_bindings": frozen_track_a_canary_runtime_bindings(),
            "schema_version": METHOD_MANIFEST_SCHEMA_VERSION,
        }
    )


def _budget_profiles() -> tuple[TrackABudgetProfile, TrackABudgetProfile]:
    score256 = TrackABudgetProfile(
        profile_id="score256",
        primary_axis="legal_action_scores",
        budget=TrackAWorkBudget(
            proposal_state_evaluations=86,
            proposal_action_scores=257,
            legal_action_scores=256,
            generated_perturbation_coordinates=257,
            edge_selections=86,
            transitions=86,
            verifier_calls=18,
        ),
    )
    verifier8 = TrackABudgetProfile(
        profile_id="verifier8",
        primary_axis="verifier_calls",
        budget=TrackAWorkBudget(
            proposal_state_evaluations=41,
            proposal_action_scores=1121,
            legal_action_scores=1121,
            generated_perturbation_coordinates=1121,
            edge_selections=41,
            transitions=41,
            verifier_calls=8,
        ),
    )
    return score256, verifier8


def _budget_manifest() -> dict[str, Any]:
    profiles = [
        {
            "spec": profile.to_dict(),
            "spec_digest": sha256_json(profile.to_dict()),
        }
        for profile in _budget_profiles()
    ]
    return _with_digest(
        {
            "bundle_id": BUNDLE_ID,
            "exact_non_primary_exhaustion_is_invalid": True,
            "profile_order": [row["spec"]["profile_id"] for row in profiles],
            "profiles": profiles,
            "schema_version": BUDGET_MANIFEST_SCHEMA_VERSION,
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
                "score256_max_complete_terminal_verifications": 17,
                "score256_max_selection_steps": 85,
                "strict_guard_slack": 1,
                "verifier8_max_legal_action_scores": 1120,
                "verifier8_max_selection_steps": 40,
                "version": "countdown-d6-structural-upper-bound/v1",
            },
            "telemetry_only": {
                "actual_rss": True,
                "canonical_live_bytes_proxy": True,
                "peak_live_nodes": True,
                "wall_time": True,
            },
        }
    )


@dataclass(frozen=True)
class CanaryCell:
    """One exact preregistered task/proposal/method/budget/seed cell."""

    task_fingerprint: str
    proposal_label: str
    proposal_spec_digest: str
    method_label: str
    method_spec_digest: str
    method_manifest_digest: str
    budget_profile_id: str
    budget_profile_spec_digest: str
    exploration_seed: int
    task_manifest_digest: str

    @property
    def key(self) -> dict[str, Any]:
        return {
            "budget_profile_spec_digest": self.budget_profile_spec_digest,
            "exploration_seed": self.exploration_seed,
            "method_spec_digest": self.method_spec_digest,
            "method_manifest_digest": self.method_manifest_digest,
            "proposal_spec_digest": self.proposal_spec_digest,
            "schema_version": CELL_KEY_SCHEMA_VERSION,
            "task_fingerprint": self.task_fingerprint,
            "task_manifest_digest": self.task_manifest_digest,
        }

    @property
    def cell_id(self) -> str:
        return sha256_json(self.key)

    def to_dict(self) -> dict[str, Any]:
        return {
            "budget_profile_id": self.budget_profile_id,
            "cell_id": self.cell_id,
            "cell_key": self.key,
            "method_label": self.method_label,
            "proposal_label": self.proposal_label,
        }


def _cells_from_components(
    tasks: Mapping[str, Any],
    proposals: Mapping[str, Any],
    methods: Mapping[str, Any],
    budgets: Mapping[str, Any],
) -> tuple[CanaryCell, ...]:
    method_rows = {row["label"]: row for row in methods["methods"]}
    budget_rows = {
        row["spec"]["profile_id"]: row for row in budgets["profiles"]
    }
    full_method_order = list(methods["method_order"])
    cells: list[CanaryCell] = []
    for task in tasks["tasks"]:
        for proposal in proposals["policies"]:
            method_labels = (
                ["greedy"]
                if proposal["execution_scope"] == "greedy_only"
                else full_method_order
            )
            for budget_profile_id in budgets["profile_order"]:
                budget = budget_rows[budget_profile_id]
                for method_label in method_labels:
                    method = method_rows[method_label]
                    selected_source = method["spec"]["selected_source"]
                    seeds = method["exploration_seeds"]
                    if selected_source == "none" and seeds != [0]:
                        raise CanaryManifestError(
                            "deterministic method contains fake seed replication"
                        )
                    if selected_source != "none" and seeds != list(
                        CANARY_EXPLORATION_SEEDS
                    ):
                        raise CanaryManifestError(
                            "stochastic method exploration seeds drifted"
                        )
                    for seed in seeds:
                        cells.append(
                            CanaryCell(
                                task_fingerprint=task["task_fingerprint"],
                                proposal_label=proposal["label"],
                                proposal_spec_digest=proposal["spec_digest"],
                                method_label=method_label,
                                method_spec_digest=method["spec_digest"],
                                method_manifest_digest=methods[
                                    "deterministic_digest"
                                ],
                                budget_profile_id=budget_profile_id,
                                budget_profile_spec_digest=budget["spec_digest"],
                                exploration_seed=seed,
                                task_manifest_digest=tasks[
                                    "deterministic_digest"
                                ],
                            )
                        )
    if len(cells) != EXPECTED_CELL_COUNT:
        raise CanaryManifestError(
            f"canary schedule has {len(cells)} cells, expected {EXPECTED_CELL_COUNT}"
        )
    cell_ids = [cell.cell_id for cell in cells]
    if len(set(cell_ids)) != len(cell_ids):
        raise CanaryManifestError("canary schedule contains duplicate full cell keys")
    return tuple(cells)


def _preregistration_manifest(
    components: Mapping[str, Mapping[str, Any]],
    cells: Sequence[CanaryCell],
) -> dict[str, Any]:
    component_digests = {
        filename: components[filename]["deterministic_digest"]
        for filename in COMPONENT_FILENAMES
        if filename != "preregistration.json"
    }
    schedule = [cell.to_dict() for cell in cells]
    return _with_digest(
        {
            "analysis_freeze": {
                "canary": {
                    "confidence_intervals": False,
                    "performance_promotion_decisions": False,
                    "p_values": False,
                    "purpose": "substrate_and_resource_gate_only",
                    "paired_contrasts": {
                        "contrast_order": [
                            "candidate_minus_frozen_iid",
                            "candidate_minus_frozen_sobol",
                            "equal_source_candidate_minus_frozen",
                            "candidate_sobol_minus_candidate_iid",
                            "candidate_iid_minus_greedy",
                            "candidate_iid_minus_beam",
                            "candidate_iid_minus_puct",
                        ],
                        "definitions": {
                            "candidate_iid_minus_beam": {
                                "left": "thompson_candidate_iid",
                                "right": "beam_width_2",
                            },
                            "candidate_iid_minus_greedy": {
                                "left": "thompson_candidate_iid",
                                "right": "greedy",
                            },
                            "candidate_iid_minus_puct": {
                                "left": "thompson_candidate_iid",
                                "right": "puct_c1",
                            },
                            "candidate_minus_frozen_iid": {
                                "left": "thompson_candidate_iid",
                                "right": "thompson_frozen_iid",
                            },
                            "candidate_minus_frozen_sobol": {
                                "left": "thompson_candidate_sobol",
                                "right": "thompson_frozen_sobol",
                            },
                            "candidate_sobol_minus_candidate_iid": {
                                "left": "thompson_candidate_sobol",
                                "right": "thompson_candidate_iid",
                            },
                            "equal_source_candidate_minus_frozen": {
                                "formula": (
                                    "arithmetic mean of candidate_minus_frozen_iid "
                                    "and candidate_minus_frozen_sobol task deltas"
                                ),
                            },
                        },
                        "output_schema": {
                            "delta_definition": "left_task_score-right_task_score",
                            "fields": [
                                "contrast_id",
                                "proposal_label",
                                "budget_profile_id",
                                "task_delta_vector",
                                "mean_task_delta",
                                "positive_task_count",
                                "zero_task_count",
                                "negative_task_count",
                            ],
                            "proposal_label": "heuristic",
                            "task_delta_vector_length": 12,
                            "task_order": "canary_task_manifest_acceptance_order",
                        },
                        "profile_scope": "each_budget_profile",
                    },
                    "task_metric_schema": {
                        "cross_task_summary": (
                            "equal-weight arithmetic mean of 12 task scores"
                        ),
                        "deterministic_method": (
                            "one binary success_any at seed 0; never replicated"
                        ),
                        "fields": [
                            "task_fingerprint",
                            "proposal_label",
                            "budget_profile_id",
                            "method_label",
                            "ordered_seed_successes",
                            "task_score",
                        ],
                        "stochastic_method": (
                            "arithmetic mean of four ordered binary success_any "
                            "values within task before any cross-task summary"
                        ),
                        "stochastic_seed_order": list(CANARY_EXPLORATION_SEEDS),
                        "unit": "task",
                    },
                    "simple_baseline_pareto_diagnostic": {
                        "candidate_sources": [
                            "thompson_candidate_iid",
                            "thompson_candidate_sobol",
                        ],
                        "baseline_methods": ["greedy", "beam_width_2"],
                        "candidate_task_score": (
                            "arithmetic mean of IID and Sobol candidate task scores"
                        ),
                        "flag_scope": "heuristic_proposal_each_budget_profile",
                        "pareto_definition": (
                            "both baselines have candidate task_score <= baseline "
                            "binary task score on all 12 tasks, and each baseline "
                            "relation has at least one strict task inequality"
                        ),
                        "effect": (
                            "blocks semantic-routing and pruning additions only"
                        ),
                        "does_not_block": [
                            "frozen_candidate_identity",
                            "locked_evaluation_when_all_other_gates_pass",
                        ],
                        "work_counters": "descriptive_not_part_of_pareto_flag",
                    },
                    "summary_schema": {
                        "group_key": [
                            "proposal_label",
                            "budget_profile_id",
                            "method_label",
                        ],
                        "ledger_usage": {
                            "aggregations": ["sum", "arithmetic_mean_per_run"],
                            "axes": [
                                "proposal_state_evaluations",
                                "proposal_action_scores",
                                "legal_action_scores",
                                "generated_perturbation_coordinates",
                                "edge_selections",
                                "transitions",
                                "verifier_calls",
                            ],
                        },
                        "min_non_primary_headroom": (
                            "minimum remaining capacity by non-primary axis over runs"
                        ),
                        "provider_calls": 0,
                        "run_level_mean_fields": [
                            "terminal_count",
                            "exact_terminal_count",
                            "successful_terminal_diversity",
                            "incomplete_trajectory_count",
                        ],
                        "run_level_mean_rule": "arithmetic_mean_over_runs",
                        "run_success_fields": [
                            "successful_run_count",
                            "run_count",
                        ],
                        "storage_proxy_fields": {
                            "peak_live_bytes_proxy": [
                                "maximum",
                                "arithmetic_mean_per_run",
                            ],
                            "peak_live_nodes": [
                                "maximum",
                                "arithmetic_mean_per_run",
                            ],
                        },
                        "task_level_fields": [
                            "task_score_vector",
                            "mean_task_score",
                            "tasks_with_any_success",
                        ],
                        "task_score_vector_length": 12,
                        "task_score_vector_order": (
                            "canary_task_manifest_acceptance_order"
                        ),
                    },
                },
                "locked_evaluation": {
                    "bootstrap_generator": {
                        "draw_count": 10_000,
                        "generator": {
                            "accepted_word_mapping": "word_mod_task_count",
                            "counter_fields": [
                                "generator_version",
                                "cohort_id",
                                "bootstrap_seed",
                                "draw_index",
                                "sample_index_within_draw",
                                "rejection_index",
                            ],
                            "hash": "sha256",
                            "index_word": "first_64_bits_big_endian",
                            "message_encoding": (
                                "ASCII(generator_version|cohort_id|bootstrap_seed|"
                                "draw_index|sample_index_within_draw|rejection_index)"
                            ),
                            "index_origin": "all counters are zero-based",
                            "integer_encoding": (
                                "unsigned base-10 ASCII without leading zeros; zero "
                                "is encoded as 0"
                            ),
                            "rejection_rule": (
                                "accept word < floor(2^64/task_count)*task_count"
                            ),
                            "retry_rule": (
                                "increment rejection_index by one until accepted"
                            ),
                            "sampling": "task_indices_with_replacement",
                            "version": "sha256-counter-rejection-index/v1",
                        },
                        "test_vector": {
                            "accepted_index_for_task_count_128": 44,
                            "acceptance_threshold_exclusive": (
                                "18446744073709551616"
                            ),
                            "digest": (
                                "c03bc295dd75722cd0e83512f4bf14dc2b4968889879c2b4"
                                "579299f67c7dd8c8"
                            ),
                            "first_64_bits_big_endian": 13851879027829469740,
                            "message": (
                                "sha256-counter-rejection-index/v1|"
                                "track_a_locked_128|26072603|0|0|0"
                            ),
                        },
                    },
                    "bootstrap_contracts": {
                        "track_a_locked_128": {
                            "cohort_id": "track_a_locked_128",
                            "nested_seed_reduction": (
                                "per_task_success_fraction_before_resampling"
                            ),
                            "seed": 26072603,
                            "statistic": (
                                "arithmetic mean of the 128 resampled paired task "
                                "differences"
                            ),
                            "task_count": 128,
                            "task_order": (
                                "locked_track_a_task_manifest_acceptance_order"
                            ),
                            "task_weighting": "equal",
                            "unit": "task",
                        },
                        "track_b_provider_16": {
                            "cohort_id": "track_b_provider_16",
                            "nested_seed_reduction": (
                                "per_task_success_fraction_before_resampling"
                            ),
                            "seed": 26072603,
                            "statistic": (
                                "arithmetic mean of the 16 resampled paired task "
                                "differences"
                            ),
                            "task_count": 16,
                            "task_order": (
                                "ascending bytewise SHA256(provider-track-v1|"
                                "task_fingerprint) over the locked Track A cohort"
                            ),
                            "task_weighting": "equal",
                            "unit": "task",
                        },
                    },
                    "decision_comparators": {
                        "calibration_guardrail_lower_bound": {
                            "operator": ">",
                            "value": -0.02,
                        },
                        "candidate_vs_frozen_primary_lower_bound": {
                            "operator": ">",
                            "value": 0.0,
                        },
                        "candidate_vs_frozen_primary_point_margin": {
                            "operator": ">=",
                            "value": 0.03,
                        },
                        "candidate_vs_greedy_or_beam_lower_bound": {
                            "operator": ">",
                            "value": 0.0,
                        },
                        "candidate_vs_greedy_or_beam_point_margin": {
                            "operator": ">=",
                            "value": 0.03,
                        },
                        "candidate_vs_puct_lower_bound": {
                            "operator": ">",
                            "value": -0.02,
                        },
                        "sobol_vs_iid_lower_bound": {
                            "operator": ">",
                            "value": 0.0,
                        },
                        "sobol_vs_iid_point_margin": {
                            "operator": ">=",
                            "value": 0.02,
                        },
                        "track_b_provider_lower_bound": {
                            "operator": ">",
                            "value": -0.02,
                        },
                    },
                    "decision_precision": (
                        "use_unrounded_estimates_and_bounds; round_display_only"
                    ),
                    "endpoint_registry": {
                        "candidate_iid_minus_beam_score256": {
                            "budget_profile_id": "score256",
                            "left": "thompson_candidate_iid",
                            "proposal_label": "heuristic",
                            "right": "beam_width_2",
                        },
                        "candidate_iid_minus_greedy_score256": {
                            "budget_profile_id": "score256",
                            "left": "thompson_candidate_iid",
                            "proposal_label": "heuristic",
                            "right": "greedy",
                        },
                        "candidate_iid_minus_puct_score256": {
                            "budget_profile_id": "score256",
                            "left": "thompson_candidate_iid",
                            "proposal_label": "heuristic",
                            "right": "puct_c1",
                        },
                        "candidate_minus_frozen_iid_score256": {
                            "budget_profile_id": "score256",
                            "left": "thompson_candidate_iid",
                            "proposal_label": "heuristic",
                            "right": "thompson_frozen_iid",
                        },
                        "candidate_minus_frozen_sobol_score256": {
                            "budget_profile_id": "score256",
                            "left": "thompson_candidate_sobol",
                            "proposal_label": "heuristic",
                            "right": "thompson_frozen_sobol",
                        },
                        "candidate_sobol_minus_candidate_iid_score256": {
                            "budget_profile_id": "score256",
                            "left": "thompson_candidate_sobol",
                            "proposal_label": "heuristic",
                            "right": "thompson_candidate_iid",
                        },
                        "equal_source_candidate_minus_frozen_score256": {
                            "components": [
                                "candidate_minus_frozen_iid_score256",
                                "candidate_minus_frozen_sobol_score256",
                            ],
                            "formula": "equal arithmetic mean of component task deltas",
                        },
                        "equal_source_candidate_minus_frozen_verifier8": {
                            "components": [
                                "candidate_minus_frozen_iid_verifier8",
                                "candidate_minus_frozen_sobol_verifier8",
                            ],
                            "formula": "equal arithmetic mean of component task deltas",
                        },
                        "candidate_minus_frozen_iid_verifier8": {
                            "budget_profile_id": "verifier8",
                            "left": "thompson_candidate_iid",
                            "proposal_label": "heuristic",
                            "right": "thompson_frozen_iid",
                        },
                        "candidate_minus_frozen_sobol_verifier8": {
                            "budget_profile_id": "verifier8",
                            "left": "thompson_candidate_sobol",
                            "proposal_label": "heuristic",
                            "right": "thompson_frozen_sobol",
                        },
                        "track_b_candidate_sobol_minus_iid_anthropic": {
                            "budget_profile_id": "score256",
                            "left": "thompson_candidate_sobol",
                            "proposal_label": "provider_snapshot",
                            "provider_stratum": "anthropic",
                            "right": "thompson_candidate_iid",
                            "task_cohort": "track_b_provider_16",
                        },
                        "track_b_candidate_sobol_minus_iid_openai": {
                            "budget_profile_id": "score256",
                            "left": "thompson_candidate_sobol",
                            "proposal_label": "provider_snapshot",
                            "provider_stratum": "openai",
                            "right": "thompson_candidate_iid",
                            "task_cohort": "track_b_provider_16",
                        },
                    },
                    "decision_families": {
                        "calibration_guardrails": {
                            "bootstrap_contract": "track_a_locked_128",
                            "endpoints": [
                                "candidate_minus_frozen_iid_score256",
                                "candidate_minus_frozen_sobol_score256",
                                "equal_source_candidate_minus_frozen_verifier8",
                            ],
                            "lower_bound_comparator": (
                                "calibration_guardrail_lower_bound"
                            ),
                            "family_alpha": 0.05,
                            "multiplicity_method": "bonferroni",
                            "quantile_fraction_key": (
                                "three_way_simultaneous_98_1_3_percent"
                            ),
                            "tails": "two_sided_equal_tail",
                        },
                        "calibration_primary": {
                            "bootstrap_contract": "track_a_locked_128",
                            "endpoints": [
                                "equal_source_candidate_minus_frozen_score256"
                            ],
                            "lower_bound_comparator": (
                                "candidate_vs_frozen_primary_lower_bound"
                            ),
                            "family_alpha": 0.05,
                            "multiplicity_method": "none_single_endpoint",
                            "point_comparator": (
                                "candidate_vs_frozen_primary_point_margin"
                            ),
                            "quantile_fraction_key": (
                                "primary_two_sided_95_percent"
                            ),
                            "tails": "two_sided_equal_tail",
                        },
                        "simple_baselines": {
                            "bootstrap_contract": "track_a_locked_128",
                            "endpoints": [
                                "candidate_iid_minus_greedy_score256",
                                "candidate_iid_minus_beam_score256",
                                "candidate_iid_minus_puct_score256",
                            ],
                            "family_alpha": 0.05,
                            "endpoint_comparators": {
                                "candidate_iid_minus_beam_score256": {
                                    "lower_bound": (
                                        "candidate_vs_greedy_or_beam_lower_bound"
                                    ),
                                    "point": (
                                        "candidate_vs_greedy_or_beam_point_margin"
                                    ),
                                },
                                "candidate_iid_minus_greedy_score256": {
                                    "lower_bound": (
                                        "candidate_vs_greedy_or_beam_lower_bound"
                                    ),
                                    "point": (
                                        "candidate_vs_greedy_or_beam_point_margin"
                                    ),
                                },
                                "candidate_iid_minus_puct_score256": {
                                    "lower_bound": "candidate_vs_puct_lower_bound"
                                },
                            },
                            "multiplicity_method": "bonferroni",
                            "quantile_fraction_key": (
                                "three_way_simultaneous_98_1_3_percent"
                            ),
                            "tails": "two_sided_equal_tail",
                        },
                        "sobol_track_a": {
                            "bootstrap_contract": "track_a_locked_128",
                            "endpoints": [
                                "candidate_sobol_minus_candidate_iid_score256"
                            ],
                            "lower_bound_comparator": "sobol_vs_iid_lower_bound",
                            "family_alpha": 0.05,
                            "multiplicity_method": "none_single_endpoint",
                            "point_comparator": "sobol_vs_iid_point_margin",
                            "quantile_fraction_key": (
                                "primary_two_sided_95_percent"
                            ),
                            "tails": "two_sided_equal_tail",
                        },
                        "sobol_track_b_provider_guardrails": {
                            "bootstrap_contract": "track_b_provider_16",
                            "endpoints": [
                                "track_b_candidate_sobol_minus_iid_anthropic",
                                "track_b_candidate_sobol_minus_iid_openai",
                            ],
                            "lower_bound_comparator": (
                                "track_b_provider_lower_bound"
                            ),
                            "family_alpha": 0.05,
                            "multiplicity_method": "bonferroni",
                            "quantile_fraction_key": (
                                "track_b_two_way_simultaneous_97_5_percent"
                            ),
                            "tails": "two_sided_equal_tail",
                        },
                    },
                    "decision_outputs": {
                        "base_search_competitiveness_decision": {
                            "required_families": ["simple_baselines"]
                        },
                        "calibration_transfer_decision": {
                            "required_families": [
                                "calibration_primary",
                                "calibration_guardrails",
                            ]
                        },
                        "sobol_source_decision": {
                            "required_families": [
                                "sobol_track_a",
                                "sobol_track_b_provider_guardrails",
                            ]
                        },
                    },
                    "paired_vector_schema": {
                        "difference": "left_task_score-right_task_score",
                        "fields": [
                            "task_fingerprint",
                            "left_task_score",
                            "right_task_score",
                            "difference",
                        ],
                        "missing_or_budget_invalid_cell": "fail_entire_gate",
                        "order": "selected bootstrap_contract task_order",
                        "provider_and_proposal_strata": "never_pooled",
                    },
                    "quantiles": {
                        "definition": (
                            "for sorted zero-based x and p=num/den: "
                            "h_num=(n-1)*num; j=h_num//den; g_num=h_num%den; "
                            "q=((den-g_num)*x[j]+g_num*x[j+1])/den"
                        ),
                        "fractions": {
                            "primary_two_sided_95_percent": [
                                {"denominator": 40, "numerator": 1},
                                {"denominator": 40, "numerator": 39},
                            ],
                            "three_way_simultaneous_98_1_3_percent": [
                                {"denominator": 120, "numerator": 1},
                                {"denominator": 120, "numerator": 119},
                            ],
                            "track_b_two_way_simultaneous_97_5_percent": [
                                {"denominator": 80, "numerator": 1},
                                {"denominator": 80, "numerator": 79},
                            ],
                        },
                        "interpolation": "linear",
                        "test_vector": {
                            "expected_quantile": {
                                "denominator": 1,
                                "numerator": 5,
                            },
                            "probability": {
                                "denominator": 6,
                                "numerator": 1,
                            },
                            "sorted_values": [0, 10, 20, 30],
                        },
                        "version": "hyndman-fan-type7-exact-rational/v1",
                    },
                    "task_metric_schema": {
                        "deterministic_method": (
                            "one binary success_any value; never seed-replicated"
                        ),
                        "fields": [
                            "task_fingerprint",
                            "proposal_label",
                            "budget_profile_id",
                            "method_label",
                            "ordered_seed_successes",
                            "task_score",
                        ],
                        "locked_stochastic_seed_order": list(range(4096, 4112)),
                        "stochastic_method": (
                            "arithmetic mean of 16 ordered binary success_any values"
                        ),
                        "unit": "task",
                    },
                },
            },
            "bundle_id": BUNDLE_ID,
            "claim_boundary": (
                "Outcome-blind canary substrate gate only; no method, calibration, "
                "proposal, IID, or Sobol superiority claim is authorized."
            ),
            "component_manifest_digests": component_digests,
            "implementation_base": IMPLEMENTATION_BASE,
            "execution_matrix": {
                "cell_count": EXPECTED_CELL_COUNT,
                "deterministic_seed_policy": [0],
                "matrix_scope": (
                    "reduced_preregistered_matrix_not_full_cartesian"
                ),
                "omitted_cells": "oracle_non_greedy_methods",
                "oracle_positive_control_scope": "greedy_only",
                "primary_proposal_label": "heuristic",
                "schedule_digest": sha256_json(schedule),
                "stochastic_seeds": list(CANARY_EXPLORATION_SEEDS),
                "uniform_and_heuristic_scope": "all_seven_methods",
            },
            "gates": {
                "all_cells_budget_valid": True,
                "all_cells_two_stage_byte_replay": True,
                "all_non_primary_guards_nonbinding": True,
                "coordinate_accounting": {
                    "deterministic_generated_coordinates": 0,
                    "stochastic_coordinates_equal_legal_action_scores": True,
                    "stochastic_point_dimension_sum_equals_coordinates": True,
                    "stochastic_points_and_selections_one_to_one": True,
                },
                "decision_statuses": {
                    "all_hard_gates_and_primary_signal_pass": (
                        "CANARY_ENGINEERING_PASS"
                    ),
                    "hard_gate_failure": "INVALID_CANARY_REPAIR_AND_RERUN",
                    "hard_gate_scope": [
                        "identity",
                        "schedule_coverage",
                        "two_stage_replay",
                        "action_order_and_no_truncation",
                        "budget_and_profile_closure",
                        "coordinate_accounting",
                        "baseline_functionality",
                        "oracle_positive_control",
                        "provider_calls_zero",
                    ],
                    "missing_cells": "never_imputed_or_dropped",
                    "performance_comparisons": "descriptive_only",
                    "primary_adaptive_signal_zero": (
                        "STOP_REPAIR_NO_LOCKED_128_RUN"
                    ),
                },
                "deterministic_baselines_require_terminal_readout": [
                    "greedy",
                    "beam_width_2",
                    "puct_c1",
                ],
                "exact_action_order_no_padding_or_truncation": True,
                "provider_calls": 0,
                "oracle_greedy_positive_control": {
                    "expected_cells": 24,
                    "required_successful_cells": 24,
                },
                "primary_adaptive_signal": {
                    "budget_profile_id": "score256",
                    "method_labels": [
                        "puct_c1",
                        "thompson_frozen_iid",
                        "thompson_frozen_sobol",
                        "thompson_candidate_iid",
                        "thompson_candidate_sobol",
                    ],
                    "minimum_successful_cells": 1,
                    "proposal_label": "heuristic",
                    "positive_control_excluded": True,
                },
                "profile_closure": {
                    "adaptive_method_labels": [
                        "puct_c1",
                        "thompson_frozen_iid",
                        "thompson_frozen_sobol",
                        "thompson_candidate_iid",
                        "thompson_candidate_sobol",
                    ],
                    "completion_method_labels": ["greedy", "beam_width_2"],
                    "completion_methods_may_stop_method_complete": True,
                    "score256_adaptive": {
                        "blocked_axes": ["legal_action_scores"],
                        "stop_reason": "primary_budget_blocked",
                    },
                    "verifier8_adaptive": {
                        "blocked_axes": ["verifier_calls"],
                        "ledger_verifier_calls": 8,
                        "ninth_preflight_has_no_partial_work": True,
                        "stop_reason": "primary_budget_blocked",
                    },
                },
            },
            "materialization_contract": {
                "precomputed_perturbation_bank_bytes": 0,
                "proposal_rows_in_bundle": 0,
                "search_records_in_bundle": 0,
                "task_specific_node_streams_in_bundle": 0,
                "task_specific_perturbation_points_in_bundle": 0,
                "visited_state_materialization": "lazy_at_later_execution_only",
            },
            "schema_version": PREREGISTRATION_SCHEMA_VERSION,
            "sealed_before_search_outcomes": True,
        }
    )


def _seal(component_payloads: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    files = {}
    for filename in COMPONENT_FILENAMES:
        payload = component_payloads[filename]
        raw = _canonical_bytes(payload)
        files[filename] = {
            "byte_count": len(raw),
            "deterministic_digest": payload["deterministic_digest"],
            "sha256": _sha256_bytes(raw),
        }
    return _with_digest(
        {
            "bundle_id": BUNDLE_ID,
            "component_files": files,
            "implementation_base": IMPLEMENTATION_BASE,
            "schema_version": SEAL_SCHEMA_VERSION,
        }
    )


def build_track_a_canary_payloads(
    *, repository_root: Path | None = None
) -> dict[str, dict[str, Any]]:
    """Build all seven sealed payloads without executing any search cell."""

    root = Path(repository_root) if repository_root is not None else None
    exclusions = _exclusion_manifest(root)
    tasks = _task_manifest(exclusions)
    proposals = _proposal_manifest()
    methods = _method_manifest()
    budgets = _budget_manifest()
    components: dict[str, dict[str, Any]] = {
        "exclusions.json": exclusions,
        "tasks.json": tasks,
        "proposals.json": proposals,
        "methods.json": methods,
        "budgets.json": budgets,
    }
    cells = _cells_from_components(tasks, proposals, methods, budgets)
    components["preregistration.json"] = _preregistration_manifest(
        components,
        cells,
    )
    payloads = {**components, SEAL_FILENAME: _seal(components)}
    _assert_no_forbidden_material(payloads)
    return deepcopy(payloads)


def _write_exclusive(path: Path, payload: Mapping[str, Any]) -> None:
    with path.open("xb") as handle:
        handle.write(_canonical_bytes(payload))
        handle.flush()
        os.fsync(handle.fileno())


def _rename_directory_noreplace(source: Path, destination: Path) -> None:
    """Atomically publish one directory while refusing a raced destination.

    POSIX ``rename`` may replace an empty destination directory, so a preceding
    existence check is not a no-overwrite guarantee.  Track A uses each host's
    atomic no-replace rename primitive and fails closed on unsupported systems.
    """

    at_fdcwd = -2 if sys.platform == "darwin" else -100
    old_path = os.fsencode(source)
    new_path = os.fsencode(destination)
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
        result = rename(at_fdcwd, old_path, at_fdcwd, new_path, 0x00000004)
    elif sys.platform.startswith("linux"):
        try:
            rename = libc.renameat2
        except AttributeError as error:
            raise OSError(
                errno.ENOSYS,
                "atomic no-replace directory publication is unsupported",
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
        result = rename(at_fdcwd, old_path, at_fdcwd, new_path, 0x00000001)
    elif sys.platform == "win32":
        os.rename(source, destination)
        return
    else:
        raise OSError(
            errno.ENOSYS,
            "atomic no-replace directory publication is unsupported",
            destination,
        )

    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise FileExistsError(
            error_number,
            "canary bundle destination exists",
            destination,
        )
    raise OSError(error_number, os.strerror(error_number), destination)


def write_track_a_canary_bundle(
    output_dir: Path,
    *,
    repository_root: Path | None = None,
) -> None:
    """Publish a complete bundle through a temporary sibling without overwrite."""

    destination = Path(output_dir)
    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"canary bundle destination exists: {destination}")
    lock = parent / f".{destination.name}.publish-lock"
    try:
        lock.mkdir()
    except FileExistsError as error:
        raise FileExistsError(f"canary bundle publication is locked: {lock}") from error

    temporary: Path | None = None
    try:
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(
                f"canary bundle destination exists: {destination}"
            )
        payloads = build_track_a_canary_payloads(repository_root=repository_root)
        temporary = Path(
            tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=parent)
        )
        for filename in BUNDLE_FILENAMES:
            _write_exclusive(temporary / filename, payloads[filename])
        temporary_fd = os.open(temporary, os.O_RDONLY)
        try:
            os.fsync(temporary_fd)
        finally:
            os.close(temporary_fd)
        _rename_directory_noreplace(temporary, destination)
        temporary = None
        directory_fd = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary is not None:
            shutil.rmtree(temporary, ignore_errors=True)
        try:
            lock.rmdir()
        except FileNotFoundError:
            pass


def _parse_canonical_object(
    raw: bytes,
    *,
    filename: str,
) -> dict[str, Any]:
    try:
        parsed = strict_json_loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, TraceValidationError) as error:
        raise CanaryManifestError(f"invalid strict JSON: {filename}") from error
    if type(parsed) is not dict:
        raise CanaryManifestError(f"bundle JSON is not an object: {filename}")
    if raw != _canonical_bytes(parsed):
        raise CanaryManifestError(f"bundle JSON is not canonical: {filename}")
    return parsed


def _read_canonical_object(path: Path) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise CanaryManifestError(f"bundle entry is not a regular file: {path.name}")
    raw = path.read_bytes()
    return _parse_canonical_object(raw, filename=path.name), raw


def _read_bundle_snapshot(
    directory: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, bytes]]:
    if directory.is_symlink() or not directory.is_dir():
        raise CanaryManifestError("canary bundle path must be a regular directory")
    payloads: dict[str, dict[str, Any]] = {}
    raw_files: dict[str, bytes] = {}
    if sys.platform == "win32":
        entries = {entry.name for entry in directory.iterdir()}
        if entries != set(BUNDLE_FILENAMES):
            raise CanaryManifestError("canary bundle directory closure drifted")
        for filename in BUNDLE_FILENAMES:
            payload, raw = _read_canonical_object(directory / filename)
            payloads[filename] = payload
            raw_files[filename] = raw
        return payloads, raw_files

    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        directory_fd = os.open(directory, directory_flags)
    except OSError as error:
        raise CanaryManifestError(
            "canary bundle path must be a regular directory"
        ) from error
    try:
        if not stat.S_ISDIR(os.fstat(directory_fd).st_mode):
            raise CanaryManifestError(
                "canary bundle path must be a regular directory"
            )
        entries = set(os.listdir(directory_fd))
        if entries != set(BUNDLE_FILENAMES):
            raise CanaryManifestError("canary bundle directory closure drifted")
        for filename in BUNDLE_FILENAMES:
            try:
                file_fd = os.open(
                    filename,
                    os.O_RDONLY | os.O_NOFOLLOW,
                    dir_fd=directory_fd,
                )
            except OSError as error:
                raise CanaryManifestError(
                    f"bundle entry is not a regular file: {filename}"
                ) from error
            try:
                if not stat.S_ISREG(os.fstat(file_fd).st_mode):
                    raise CanaryManifestError(
                        f"bundle entry is not a regular file: {filename}"
                    )
                with os.fdopen(file_fd, "rb", closefd=False) as handle:
                    raw = handle.read()
            finally:
                os.close(file_fd)
            payloads[filename] = _parse_canonical_object(
                raw,
                filename=filename,
            )
            raw_files[filename] = raw
    finally:
        os.close(directory_fd)
    return payloads, raw_files


def _validate_local_digests(
    payloads: Mapping[str, Mapping[str, Any]],
    raw_files: Mapping[str, bytes],
) -> None:
    for filename in COMPONENT_FILENAMES:
        payload = payloads[filename]
        digest = payload.get("deterministic_digest")
        if type(digest) is not str or len(digest) != 64:
            raise CanaryManifestError(f"component digest is invalid: {filename}")
        core = {key: value for key, value in payload.items() if key != "deterministic_digest"}
        if sha256_json(core) != digest:
            raise CanaryManifestError(f"component digest drifted: {filename}")

    seal = payloads[SEAL_FILENAME]
    if set(seal) != {
        "bundle_id",
        "component_files",
        "deterministic_digest",
        "implementation_base",
        "schema_version",
    }:
        raise CanaryManifestError("seal fields drifted")
    if seal["bundle_id"] != BUNDLE_ID or seal["schema_version"] != SEAL_SCHEMA_VERSION:
        raise CanaryManifestError("seal identity drifted")
    if seal["implementation_base"] != IMPLEMENTATION_BASE:
        raise CanaryManifestError("seal implementation base drifted")
    seal_core = {
        key: value for key, value in seal.items() if key != "deterministic_digest"
    }
    if sha256_json(seal_core) != seal["deterministic_digest"]:
        raise CanaryManifestError("seal deterministic digest drifted")
    files = seal["component_files"]
    if type(files) is not dict or set(files) != set(COMPONENT_FILENAMES):
        raise CanaryManifestError("seal component file closure drifted")
    for filename in COMPONENT_FILENAMES:
        metadata = files[filename]
        if type(metadata) is not dict or set(metadata) != {
            "byte_count",
            "deterministic_digest",
            "sha256",
        }:
            raise CanaryManifestError(f"seal metadata drifted: {filename}")
        raw = raw_files[filename]
        if (
            type(metadata["byte_count"]) is not int
            or metadata["byte_count"] != len(raw)
            or metadata["sha256"] != _sha256_bytes(raw)
            or metadata["deterministic_digest"]
            != payloads[filename]["deterministic_digest"]
        ):
            raise CanaryManifestError(f"sealed component bytes drifted: {filename}")


@dataclass(frozen=True)
class VerifiedCanaryBundle:
    """Validated bundle plus its independently reconstructed cell schedule."""

    directory: Path
    _payloads: dict[str, dict[str, Any]]
    _cells: tuple[CanaryCell, ...]

    @property
    def payloads(self) -> dict[str, dict[str, Any]]:
        return deepcopy(self._payloads)

    @property
    def cells(self) -> tuple[CanaryCell, ...]:
        return self._cells

    @property
    def seal_digest(self) -> str:
        return self._payloads[SEAL_FILENAME]["deterministic_digest"]


def verify_track_a_canary_bundle(
    bundle_dir: Path,
    *,
    repository_root: Path | None = None,
) -> VerifiedCanaryBundle:
    """Fail closed unless bytes and semantics match a fresh outcome-blind build."""

    directory = Path(bundle_dir)
    if directory.is_symlink() or not directory.is_dir():
        raise CanaryManifestError("canary bundle path must be a regular directory")
    payloads, raw_files = _read_bundle_snapshot(directory)
    _validate_local_digests(payloads, raw_files)
    _assert_no_forbidden_material(payloads)

    expected = build_track_a_canary_payloads(repository_root=repository_root)
    if any(
        raw_files[filename] != _canonical_bytes(expected[filename])
        for filename in BUNDLE_FILENAMES
    ):
        raise CanaryManifestError(
            "canary bundle bytes differ from independent deterministic regeneration"
        )
    cells = _cells_from_components(
        payloads["tasks.json"],
        payloads["proposals.json"],
        payloads["methods.json"],
        payloads["budgets.json"],
    )
    expected_schedule_digest = sha256_json([cell.to_dict() for cell in cells])
    observed_schedule_digest = payloads["preregistration.json"][
        "execution_matrix"
    ]["schedule_digest"]
    if observed_schedule_digest != expected_schedule_digest:
        raise CanaryManifestError("canary execution schedule digest drifted")
    final_payloads, final_raw_files = _read_bundle_snapshot(directory)
    if final_raw_files != raw_files or final_payloads != payloads:
        raise CanaryManifestError("canary bundle changed during verification")
    return VerifiedCanaryBundle(directory, deepcopy(payloads), cells)


def iter_track_a_canary_cells(
    bundle: VerifiedCanaryBundle,
) -> tuple[CanaryCell, ...]:
    """Return the verified schedule; unverified payload mappings are rejected."""

    if type(bundle) is not VerifiedCanaryBundle:
        raise TypeError("bundle must be exactly VerifiedCanaryBundle")
    return bundle.cells


def _self_test(repository_root: Path | None = None) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="qmc-track-a-canary-") as root:
        output = Path(root) / "bundle"
        write_track_a_canary_bundle(output, repository_root=repository_root)
        verified = verify_track_a_canary_bundle(
            output,
            repository_root=repository_root,
        )
        cells = iter_track_a_canary_cells(verified)
        if len(cells) != EXPECTED_CELL_COUNT:
            raise AssertionError("self-test canary cell count drifted")
        if len({cell.cell_id for cell in cells}) != EXPECTED_CELL_COUNT:
            raise AssertionError("self-test canary cell identities collided")
        deterministic = {
            cell.method_label
            for cell in cells
            if cell.exploration_seed == 0
        }
        if deterministic != {"greedy", "beam_width_2", "puct_c1"}:
            raise AssertionError("self-test deterministic seed policy drifted")
        return {
            "bundle_id": BUNDLE_ID,
            "cell_count": len(cells),
            "claim_boundary": (
                "manifest plumbing only; no canary search outcomes were opened"
            ),
            "seal_digest": verified.seal_digest,
            "status": "PASS",
        }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--create", type=Path, metavar="DIRECTORY")
    modes.add_argument("--qualify-runtime", action="store_true")
    modes.add_argument("--verify", type=Path, metavar="DIRECTORY")
    modes.add_argument("--self-test", action="store_true")
    parser.add_argument("--repository-root", type=Path)
    args = parser.parse_args(argv)

    if args.create is not None:
        write_track_a_canary_bundle(
            args.create,
            repository_root=args.repository_root,
        )
        verified = verify_track_a_canary_bundle(
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
        verified = verify_track_a_canary_bundle(
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
    elif args.self_test:
        result = _self_test(args.repository_root)
    else:
        result = qualify_track_a_canary_runtime()
    print(canonical_json(result))


if __name__ == "__main__":
    main()
