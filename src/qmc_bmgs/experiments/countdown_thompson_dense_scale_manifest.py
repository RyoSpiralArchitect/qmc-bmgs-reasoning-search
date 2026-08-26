#!/usr/bin/env python3
"""Seal the source-disjoint Countdown dense-scale development matrix.

This module verifies the preceding diagnostic preregistration, constructs a
new task cohort disjoint in both full-task and source-multiset identity, and
freezes the exact 384-cell v5 schedule.  It deliberately has no search runner
and never materializes a proposal row, perturbation point, or search outcome.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import os
import secrets
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
from qmc_bmgs.experiments import countdown_thompson_diagnostic_manifest as diagnostic
from qmc_bmgs.substrate.budget import TRACK_A_WORK_AXES, TrackAWorkBudget
from qmc_bmgs.substrate.countdown_search import (
    ANCHOR_EQUIVALENCE_PROJECTION_SCHEMA_VERSION,
    DENSE_TERMINAL_VALUE_SCALES,
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


BUNDLE_ID = "countdown_thompson_dense_scale_12_seed_26082601/v1"
BUNDLE_SCHEMA_VERSION = "qmc-bmgs-countdown-thompson-dense-scale-preregistration/v1"
COHORT_SCHEMA_VERSION = "qmc-bmgs-countdown-thompson-dense-scale-tasks/v1"
EXCLUSION_SCHEMA_VERSION = "qmc-bmgs-countdown-source-disjoint-exclusion-identity/v2"
METHODS_SCHEMA_VERSION = "qmc-bmgs-countdown-thompson-dense-scale-methods/v1"
CELL_KEY_SCHEMA_VERSION = "qmc-bmgs-countdown-thompson-dense-scale-cell-key/v1"
ANALYSIS_SCHEMA_VERSION = "qmc-bmgs-countdown-thompson-dense-scale-analysis/v1"
EXECUTION_SCHEMA_VERSION = "qmc-bmgs-countdown-thompson-dense-scale-execution/v1"

DIAGNOSTIC_BUNDLE_ID = "countdown_thompson_diagnostic_12_seed_26081001/v1"
DIAGNOSTIC_BUNDLE_PATH = Path("docs/preregistrations/countdown_thompson_diagnostic_v1")
DIAGNOSTIC_SEAL_DIGEST = (
    "cc633b9ee3ffda6a9115af07f0cc047a1bd8cd7af5e11d07f6ddb0faa4e5f975"
)
FROZEN_DESIGN_PATH = Path(
    "docs/strategy/countdown_thompson_dense_scale_dose_response_v5.md"
)
FROZEN_DESIGN_REVISION = "c1eef797b8bc5dcdbb311473d94974afa4ce1797"
FROZEN_DESIGN_SHA256 = (
    "67f6ed541c0ef5e2409a05f9d044eb257ab0ee3b76baa3e6f2df809a06f86002"
)
IMPLEMENTATION_BASE = {
    "merged_revision": "2bf4ce85947c39cc05a6f32a19576ea7d6e6790a",
    "pull_request_url": (
        "https://github.com/RyoSpiralArchitect/qmc-bmgs-reasoning-search/pull/19"
    ),
    "repository_url": (
        "https://github.com/RyoSpiralArchitect/qmc-bmgs-reasoning-search"
    ),
}

TASK_COUNT = 12
GENERATION_SEED = 26082601
EXPLORATION_SEEDS = (7168, 7169, 7170, 7171)
SCALE_ORDER = DENSE_TERMINAL_VALUE_SCALES
EXPECTED_CELL_COUNT = TASK_COUNT * len(SCALE_ORDER) * len(EXPLORATION_SEEDS)
BUNDLE_FILENAME = "preregistration.json"
_BUNDLE_BYTE_CAP = 8 * 1024 * 1024
_READ_CHUNK_BYTES = 1024 * 1024

_SOURCE_BINDING_PATHS = (
    Path("src/qmc_bmgs/benchmarks/countdown.py"),
    Path("src/qmc_bmgs/substrate/budget.py"),
    Path("src/qmc_bmgs/substrate/countdown_search.py"),
    Path("src/qmc_bmgs/substrate/perturbations.py"),
    Path("src/qmc_bmgs/substrate/proposals.py"),
    Path("src/qmc_bmgs/substrate/trace.py"),
)

_TOP_LEVEL_FIELDS = {
    "analysis",
    "authority",
    "budget",
    "bundle_id",
    "claim_boundary",
    "cohort",
    "deterministic_digest",
    "execution_matrix",
    "frozen_design",
    "implementation_base",
    "materialization_contract",
    "methods",
    "proposal",
    "runtime_binding",
    "schema_version",
    "sealed_before_development_search_outcomes",
}

_FORBIDDEN_PERSISTED_KEYS = {
    "calibration_profile",
    "events",
    "normals",
    "perturbation_point",
    "perturbation_points",
    "proposal_row",
    "proposal_rows",
    "provider_output",
    "provider_outputs",
    "search_outcome",
    "search_outcomes",
    "search_record",
    "search_records",
    "solution_witness",
    "terminal_outcome",
    "terminal_outcomes",
    "uniforms",
    "witness",
}


class DenseScaleManifestError(ValueError):
    """Raised when the outcome-blind v5 preregistration fails closed."""


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return (canonical_json(payload) + "\n").encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _with_digest(core: Mapping[str, Any]) -> dict[str, Any]:
    payload = deepcopy(dict(core))
    payload["deterministic_digest"] = sha256_json(payload)
    return payload


def _read_stable_regular_file(path: Path, *, label: str) -> bytes:
    try:
        before = path.lstat()
    except OSError as error:
        raise DenseScaleManifestError(f"{label} is unavailable") from error
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise DenseScaleManifestError(f"{label} must be a regular file")
    try:
        raw = path.read_bytes()
        after = path.lstat()
    except OSError as error:
        raise DenseScaleManifestError(f"{label} could not be read") from error
    if (
        _directory_state(before) != _directory_state(after)
        or len(raw) != before.st_size
    ):
        raise DenseScaleManifestError(f"{label} changed during read")
    return raw


def _repository_root(repository_root: Path | None) -> Path:
    root = (
        Path(__file__).resolve().parents[3]
        if repository_root is None
        else Path(repository_root).resolve()
    )
    if root.is_symlink() or not root.is_dir():
        raise DenseScaleManifestError("repository root must be a regular directory")
    return root


def _task_from_row(row: Any, *, label: str) -> CountdownTask:
    if type(row) is not dict:
        raise DenseScaleManifestError(f"{label} task row must be an object")
    try:
        task = CountdownTask(tuple(row["inputs"]), row["target"])
    except (KeyError, TypeError, ValueError) as error:
        raise DenseScaleManifestError(f"{label} task row is invalid") from error
    if task.to_dict() != row:
        raise DenseScaleManifestError(f"{label} task row identity drifted")
    return task


def _validate_identity_sets(
    cohorts: Sequence[tuple[str, Sequence[CountdownTask]]],
) -> None:
    seen_tasks: set[str] = set()
    seen_sources: set[str] = set()
    for label, tasks in cohorts:
        for task in tasks:
            if task.task_fingerprint in seen_tasks:
                raise DenseScaleManifestError(
                    f"full task identity overlaps at cohort {label}"
                )
            if task.source_multiset_fingerprint in seen_sources:
                raise DenseScaleManifestError(
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
            "schema_version": EXCLUSION_SCHEMA_VERSION,
            "source_multiset_fingerprint_count": len(source_fingerprints),
            "source_multiset_fingerprint_digest": sha256_json(source_fingerprints),
            "source_multiset_fingerprints": source_fingerprints,
            "task_fingerprint_count": len(task_fingerprints),
            "task_fingerprint_digest": sha256_json(task_fingerprints),
            "task_fingerprints": task_fingerprints,
        }
    )


def _verified_authority(
    root: Path,
) -> tuple[
    dict[str, Any],
    tuple[tuple[str, tuple[CountdownTask, ...]], ...],
    dict[str, dict[str, Any]],
]:
    verified = diagnostic.verify_countdown_thompson_diagnostic_bundle(
        root / DIAGNOSTIC_BUNDLE_PATH,
        repository_root=root,
    )
    payloads = verified.payloads
    if (
        verified.seal_digest != DIAGNOSTIC_SEAL_DIGEST
        or payloads["seal.json"]["bundle_id"] != DIAGNOSTIC_BUNDLE_ID
    ):
        raise DenseScaleManifestError("diagnostic authority seal drifted")

    authorities = payloads["authorities.json"]
    cohort_rows = (
        ("historical_2", authorities["historical_authority"]["tasks"]),
        ("canary_12", authorities["canary_authority"]["tasks"]),
        ("locked_128", payloads["locked_reservation.json"]["tasks"]),
        ("diagnostic_12", payloads["diagnostic_tasks.json"]["tasks"]),
    )
    cohorts = tuple(
        (
            label,
            tuple(_task_from_row(row, label=label) for row in rows),
        )
        for label, rows in cohort_rows
    )
    _validate_identity_sets(cohorts)
    component_digests = {
        filename: payloads[filename]["deterministic_digest"]
        for filename in diagnostic.BUNDLE_FILENAMES
    }
    authority = _with_digest(
        {
            "component_digests": component_digests,
            "diagnostic_bundle_id": DIAGNOSTIC_BUNDLE_ID,
            "diagnostic_bundle_path": DIAGNOSTIC_BUNDLE_PATH.as_posix(),
            "diagnostic_seal_digest": DIAGNOSTIC_SEAL_DIGEST,
            "excluded_cohort_order": [label for label, _ in cohorts],
            "role": "verified_identity_exclusion_authority_only",
        }
    )
    return authority, cohorts, payloads


def _cohort_manifest(
    authority: Mapping[str, Any],
    prior_cohorts: Sequence[tuple[str, Sequence[CountdownTask]]],
) -> tuple[dict[str, Any], tuple[CountdownTask, ...]]:
    exclusions = _identity_record(
        prior_cohorts,
        authority_digests={
            "dense_scale_authority": authority["deterministic_digest"],
        },
    )
    suite = generate_solvable_task_suite(
        TASK_COUNT,
        GENERATION_SEED,
        excluded_task_fingerprints=tuple(exclusions["task_fingerprints"]),
        excluded_source_multiset_fingerprints=tuple(
            exclusions["source_multiset_fingerprints"]
        ),
        excluded_identity_record_digest=exclusions["deterministic_digest"],
    )
    tasks = suite.tasks
    rows = [task.to_dict() for task in tasks]
    if len(tasks) != TASK_COUNT:
        raise DenseScaleManifestError("development task count drifted")
    _validate_identity_sets((*prior_cohorts, ("dense_scale_development_12", tasks)))
    if len({task.task_fingerprint for task in tasks}) != TASK_COUNT:
        raise DenseScaleManifestError("development cohort repeats a full task")
    if len({task.source_multiset_fingerprint for task in tasks}) != TASK_COUNT:
        raise DenseScaleManifestError("development cohort repeats a source multiset")
    cohort = _with_digest(
        {
            "accepted_task_pool_digest": sha256_json(rows),
            "cohort_role": "source_disjoint_scale_development_not_locked_evaluation",
            "exclusion_identity": exclusions,
            "generation_call": {
                "count": TASK_COUNT,
                "function": (
                    "qmc_bmgs.benchmarks.countdown.generate_solvable_task_suite"
                ),
                "max_attempts": suite.generation_manifest["max_attempts"],
                "seed": GENERATION_SEED,
            },
            "generation_manifest": suite.generation_manifest,
            "identity_contract": {
                "full_tasks_disjoint_from_all_four_prior_cohorts": True,
                "full_tasks_unique": True,
                "source_multisets_disjoint_from_all_four_prior_cohorts": True,
                "source_multisets_unique": True,
            },
            "persisted_calibration_profile_count": 0,
            "persisted_solution_witness_count": 0,
            "ruleset_id": RULESET_ID,
            "schema_version": COHORT_SCHEMA_VERSION,
            "task_count": TASK_COUNT,
            "task_order": "generator_acceptance_order",
            "tasks": rows,
        }
    )
    return cohort, tasks


def _proposal_manifest(
    authority_payloads: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    spec = TrackAProposalSpec("greedy_rollout_target_error/v1")
    spec_payload = spec.to_dict()
    spec_digest = spec.deterministic_digest
    authority_rows = [
        row
        for row in authority_payloads["proposals.json"]["policies"]
        if row["label"] == "heuristic"
    ]
    if len(authority_rows) != 1:
        raise DenseScaleManifestError("heuristic proposal authority is not unique")
    authority_row = authority_rows[0]
    if (
        authority_row["spec"] != spec_payload
        or authority_row["spec_digest"] != spec_digest
    ):
        raise DenseScaleManifestError("heuristic proposal authority drifted")
    return _with_digest(
        {
            "label": "heuristic",
            "materialization": "lazy_visited_states_only_at_later_execution",
            "provider_calls": 0,
            "spec": spec_payload,
            "spec_digest": spec_digest,
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
    authority_payloads: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    profile = _budget_profile()
    spec = profile.to_dict()
    spec_digest = sha256_json(spec)
    authority_rows = [
        row
        for row in authority_payloads["budgets.json"]["profiles"]
        if row["spec"]["profile_id"] == "score256"
    ]
    if len(authority_rows) != 1:
        raise DenseScaleManifestError("score256 budget authority is not unique")
    authority_row = authority_rows[0]
    if authority_row != {"spec": spec, "spec_digest": spec_digest}:
        raise DenseScaleManifestError("score256 budget authority drifted")
    return _with_digest(
        {
            "exact_non_primary_exhaustion_is_invalid": True,
            "profile": {"spec": spec, "spec_digest": spec_digest},
            "structural_guard_authority_digest": authority_payloads["budgets.json"][
                "deterministic_digest"
            ],
        }
    )


def _methods_manifest() -> dict[str, Any]:
    rows = []
    for scale in SCALE_ORDER:
        spec = TrackAMethodSpec.dimension_normalized_scaled_dense_thompson("iid", scale)
        spec_payload = spec.to_dict()
        rows.append(
            {
                "exploration_seeds": list(EXPLORATION_SEEDS),
                "label": f"thompson_scaled_dense_iid_s{scale}_v5",
                "spec": spec_payload,
                "spec_digest": sha256_json(spec_payload),
                "terminal_value_scale": scale,
            }
        )
    return _with_digest(
        {
            "anchor_contract": {
                "development_v2_or_v3_cell_count": 0,
                "qualification_scope": "nondiagnostic_public_fixture_only",
                "scale_0": "existing_v2_binary_terminal_behavior",
                "scale_1": "existing_v3_reciprocal_error_terminal_behavior",
            },
            "method_order": [row["label"] for row in rows],
            "methods": rows,
            "pairing_contract": {
                "configuration_excluded_from_node_stream_identity": True,
                "iid_only": True,
                "no_greedy_anchor": True,
                "same_task_state_seed_visit_uses_same_iid_coordinates": True,
                "single_changed_factor": "terminal_value_scale",
            },
            "scale_order": list(SCALE_ORDER),
            "schema_version": METHODS_SCHEMA_VERSION,
        }
    )


def _source_binding(
    root: Path,
    authority_payloads: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    rows = []
    for relative_path in _SOURCE_BINDING_PATHS:
        raw = _read_stable_regular_file(
            root / relative_path,
            label=f"runtime source {relative_path.as_posix()}",
        )
        rows.append(
            {
                "byte_count": len(raw),
                "path": relative_path.as_posix(),
                "sha256": _sha256_bytes(raw),
            }
        )
    iid_metadata = perturbation_runtime_metadata("iid")
    search_metadata = search_runtime_metadata()
    runtime_authority = authority_payloads["methods.json"]["runtime_bindings"]
    observed_runtime = {
        "iid": {
            "digest": sha256_json(iid_metadata),
            "metadata": iid_metadata,
        },
        "search": {
            "digest": sha256_json(search_metadata),
            "metadata": search_metadata,
        },
    }
    if observed_runtime != {
        "iid": runtime_authority["iid"],
        "search": runtime_authority["search"],
    }:
        raise DenseScaleManifestError("diagnostic runtime authority drifted")
    return _with_digest(
        {
            "diagnostic_runtime_binding_digest": sha256_json(runtime_authority),
            "iid_runtime": observed_runtime["iid"],
            "search_runtime": observed_runtime["search"],
            "source_files": rows,
        }
    )


@dataclass(frozen=True)
class DenseScaleCell:
    """One exact task/scale/seed cell in the frozen development matrix."""

    task_fingerprint: str
    task_manifest_digest: str
    method_label: str
    method_spec_digest: str
    method_manifest_digest: str
    terminal_value_scale: int
    proposal_spec_digest: str
    budget_profile_spec_digest: str
    exploration_seed: int

    @property
    def key(self) -> dict[str, Any]:
        return {
            "budget_profile_id": "score256",
            "budget_profile_spec_digest": self.budget_profile_spec_digest,
            "bundle_id": BUNDLE_ID,
            "exploration_seed": self.exploration_seed,
            "method_label": self.method_label,
            "method_manifest_digest": self.method_manifest_digest,
            "method_spec_digest": self.method_spec_digest,
            "proposal_label": "heuristic",
            "proposal_spec_digest": self.proposal_spec_digest,
            "schema_version": CELL_KEY_SCHEMA_VERSION,
            "task_fingerprint": self.task_fingerprint,
            "task_manifest_digest": self.task_manifest_digest,
            "terminal_value_scale": self.terminal_value_scale,
        }

    @property
    def cell_id(self) -> str:
        return sha256_json(self.key)

    def to_dict(self) -> dict[str, Any]:
        return {"cell_id": self.cell_id, "cell_key": self.key}


def _cells_from_components(
    cohort: Mapping[str, Any],
    proposal: Mapping[str, Any],
    methods: Mapping[str, Any],
    budget: Mapping[str, Any],
) -> tuple[DenseScaleCell, ...]:
    method_rows = {row["label"]: row for row in methods["methods"]}
    cells: list[DenseScaleCell] = []
    for task in cohort["tasks"]:
        for method_label in methods["method_order"]:
            method = method_rows[method_label]
            scale = method["terminal_value_scale"]
            for seed in EXPLORATION_SEEDS:
                cells.append(
                    DenseScaleCell(
                        task_fingerprint=task["task_fingerprint"],
                        task_manifest_digest=cohort["deterministic_digest"],
                        method_label=method_label,
                        method_spec_digest=method["spec_digest"],
                        method_manifest_digest=methods["deterministic_digest"],
                        terminal_value_scale=scale,
                        proposal_spec_digest=proposal["spec_digest"],
                        budget_profile_spec_digest=budget["profile"]["spec_digest"],
                        exploration_seed=seed,
                    )
                )
    if len(cells) != EXPECTED_CELL_COUNT:
        raise DenseScaleManifestError(
            f"dense-scale schedule has {len(cells)} cells, expected "
            f"{EXPECTED_CELL_COUNT}"
        )
    if len({cell.cell_id for cell in cells}) != EXPECTED_CELL_COUNT:
        raise DenseScaleManifestError("dense-scale schedule contains duplicates")
    return tuple(cells)


def _anchor_qualification_manifest() -> dict[str, Any]:
    task = CountdownTask((1, 2, 3, 4, 5, 6), target=720)
    proposal = TrackAProposalSpec("greedy_rollout_target_error/v1")
    budget_limits = {axis: 20_000 for axis in TRACK_A_WORK_AXES}
    budget_limits["verifier_calls"] = 3
    profile = TrackABudgetProfile(
        profile_id="dense_scale_anchor_fixture_verifier3",
        primary_axis="verifier_calls",
        budget=TrackAWorkBudget(**budget_limits),
    )
    expected_digests = {
        ("iid", "binary_terminal_anchor"): (
            "1a712c7b766dc5e6aa138edb718432636fac838f75e7ca1e4274fd17a4bca9e4",
            "0d0dc2eb4c52697e78bcb744a48c3a407cac4dc3025b0b9f393e08144efc320b",
            "18534a6eb89bb0a23cf0c6de104f7d1ed810eb4c5a662377fb4957d3690ba8ff",
        ),
        ("iid", "reciprocal_error_anchor"): (
            "036ab50644b600cacf8488f74210c9e9725db441b8e8a3b78e90561eb2445763",
            "0657acaf773f995a5c624bb18ad7f45cc0b8349edfd037222b04d50a657fcf22",
            "f0628fdeda9f93f41ed6ad60f4718738b6cfad3f0ea967c6f4b3391a2d757310",
        ),
        ("sobol", "binary_terminal_anchor"): (
            "651d1c5a6dd5395dbb54768eeea3c9a8f2e6d6a1f60e399301120dc59f93531f",
            "2058e56a97de725c61b78efc338c75c868386fe6fd1e6879a0d5cf32c2f81b0f",
            "75c80b1a60ec85328ee9a88259c81da13ac81ea3ea8719a5e5049754350a482c",
        ),
        ("sobol", "reciprocal_error_anchor"): (
            "6be047dad38bfbee09e42ca2c07e88df75e1f493efdecc171b1a26a4f7852d31",
            "e1136f466718b762cbd50549bbecb8fd9c14553361d54461ee8883739ba6596c",
            "5cbccc2eb19780909b3942ec509ad61424f12d401fff03df071909600a742b4b",
        ),
    }
    receipts: list[dict[str, Any]] = []
    for source in ("iid", "sobol"):
        pairs = (
            (
                "binary_terminal_anchor",
                TrackAMethodSpec.dimension_normalized_thompson(source),
                TrackAMethodSpec.dimension_normalized_scaled_dense_thompson(
                    source, 0
                ),
            ),
            (
                "reciprocal_error_anchor",
                TrackAMethodSpec.dimension_normalized_dense_thompson(source),
                TrackAMethodSpec.dimension_normalized_scaled_dense_thompson(
                    source, 1
                ),
            ),
        )
        for anchor_label, authority_method, scaled_method in pairs:
            authority_digest, scaled_digest, projection_digest = expected_digests[
                (source, anchor_label)
            ]
            receipts.append(
                {
                    "anchor_label": anchor_label,
                    "authority_method_spec": authority_method.to_dict(),
                    "authority_method_spec_digest": sha256_json(
                        authority_method.to_dict()
                    ),
                    "expected_authority_trace_sha256": authority_digest,
                    "expected_common_projection_digest": projection_digest,
                    "expected_scaled_trace_sha256": scaled_digest,
                    "scaled_method_spec": scaled_method.to_dict(),
                    "scaled_method_spec_digest": sha256_json(
                        scaled_method.to_dict()
                    ),
                    "source": source,
                }
            )
    return _with_digest(
        {
            "budget_profile": profile.to_dict(),
            "development_cell_count": 0,
            "development_task_access": False,
            "execution_count": 8,
            "exploration_seed": 7168,
            "fixture_task": task.to_dict(),
            "projection_schema_version": (
                ANCHOR_EQUIVALENCE_PROJECTION_SCHEMA_VERSION
            ),
            "proposal_spec": proposal.to_dict(),
            "raw_trace_persisted_count": 0,
            "receipt_order": [
                "iid_binary_terminal_anchor",
                "iid_reciprocal_error_anchor",
                "sobol_binary_terminal_anchor",
                "sobol_reciprocal_error_anchor",
            ],
            "receipts": receipts,
            "required_before_development_result_open": True,
            "scope": "nondiagnostic_public_fixture_only",
            "v2_or_v3_development_execution_authority": False,
        }
    )


def _analysis_manifest() -> dict[str, Any]:
    return _with_digest(
        {
            "analysis_order": [
                "reproduce_nondiagnostic_anchor_qualification_without_development_material",
                "integrity_budget_and_two_stage_replay",
                "common_prefix_mechanism_without_terminal_fields",
                "terminal_error_reductions",
                "exact_success_and_development_handoff",
            ],
            "anchor_equivalence": {
                "backup_fields_removed": [
                    "terminal_absolute_error",
                    "terminal_value_denominator",
                    "terminal_value_floor",
                    "terminal_value_floor_applied",
                    "terminal_value_numerator",
                    "terminal_value_rule_id",
                    "terminal_value_scale",
                ],
                "comparison": "canonical_projection_exact_equality",
                "development_matrix_authority_trace_count": 0,
                "failure_timing": "before_terminal_error_or_success_read",
                "pairs": [
                    {
                        "anchor_label": "binary_terminal_anchor",
                        "authority_schema": "qmc-bmgs-track-a-method-spec/v2",
                        "scaled_terminal_value_scale": 0,
                    },
                    {
                        "anchor_label": "reciprocal_error_anchor",
                        "authority_schema": "qmc-bmgs-track-a-method-spec/v3",
                        "scaled_terminal_value_scale": 1,
                    },
                ],
                "precondition": (
                    "both traces pass canonical validation and two-stage byte "
                    "replay under their own sealed method"
                ),
                "qualification": _anchor_qualification_manifest(),
                "preserved": [
                    "all_other_run_identity_fields",
                    "event_count",
                    "event_index_kind_charge_and_all_other_payload_fields",
                    "proposal_node_and_point_material",
                    "terminal_value_and_posterior_updates",
                    "stop_events",
                    "all_other_ledger_fields_and_components",
                    "trace_schema_version",
                ],
                "projection_schema_version": (
                    ANCHOR_EQUIVALENCE_PROJECTION_SCHEMA_VERSION
                ),
                "replay_closed_storage_bytes_replaced_as_schema_overhead": [
                    "ledger_snapshot.live_storage.bytes",
                    "ledger_snapshot.peak_live_storage.bytes",
                ],
                "run_identity_replaced_fields": [
                    "configuration_id",
                    "method_id",
                ],
                "selection_method_field_replaced_after_exact_spec_check": True,
                "scope": "nondiagnostic_implementation_qualification_only",
                "top_level_removed_fields": [
                    "deterministic_digest",
                    "final_event_digest",
                ],
                "event_removed_fields": [
                    "event_digest",
                    "previous_event_digest",
                ],
                "finished_summary_fields_replaced_after_exact_identity_check": [
                    "method",
                    "run_identity_digest",
                ],
            },
            "claim_boundary": {
                "confidence_intervals": False,
                "development_not_confirmation": True,
                "locked_128_authority": False,
                "method_superiority_claim": False,
                "p_values": False,
                "qmc_comparison": False,
                "task_transfer_claim": False,
            },
            "development_handoff": {
                "candidate_scale_order": list(SCALE_ORDER[1:]),
                "failure_status": "STOP_REPAIR_NO_LOCKED_128_RUN",
                "minimum_new_exact_successes": 2,
                "minimum_net_exact_success_gain": 2,
                "new_success_divergence_guard": (
                    "each new-success pair first diverges only after at least one "
                    "scale-dependent terminal backup on the common prefix"
                ),
                "scale_selection": (
                    "maximize exact-success count across 48 task-seed cells; "
                    "break ties by lower scale"
                ),
                "success_status": ("READY_TO_PREREGISTER_SOURCE_DISJOINT_CONFIRMATION"),
            },
            "integrity_gates": {
                "budget_valid": True,
                "exact_384_cell_set": True,
                "no_missing_duplicate_or_extra_cells": True,
                "no_non_primary_guard_binding_or_exhaustion": True,
                "provider_calls": 0,
                "two_stage_byte_replay": True,
            },
            "integer_reductions": {
                "arithmetic": "exact_reduced_rational",
                "empty_required_vector": "INVALID_ANALYSIS",
                "even_median": (
                    "reduce((sorted[n//2-1]+sorted[n//2])/2)"
                ),
                "odd_median": "sorted[n//2]",
            },
            "mechanism_pairing": {
                "baseline_scale": 0,
                "include_first_action_divergence_then_stop": True,
                "outcome_fields_read": False,
                "pair_key": "(task_fingerprint,exploration_seed,positive_scale)",
                "predecision_equal_fields": [
                    "trajectory_index",
                    "depth",
                    "state",
                    "canonical_action_order",
                    "proposal_behavior_digest",
                    "perturbation_point_digest",
                    "selection_rule_id",
                    "noise_dimension_normalizer",
                    "posterior_visit_vector",
                ],
            },
            "reported_scale_fields": [
                "success_vector",
                "exact_success_count",
                "first_hit_trajectory_index_vector",
                "minimum_terminal_absolute_error_vector",
                "terminal_absolute_error_vectors",
                "terminal_value_vectors",
                "paired_new_success_count_vs_scale_0",
                "paired_lost_success_count_vs_scale_0",
                "paired_net_success_difference_vs_scale_0",
                "paired_minimum_error_win_tie_loss_vs_scale_0",
                "feedback_informed_first_divergence_count",
                "first_divergence_coordinate_distribution",
            ],
            "schema_version": ANALYSIS_SCHEMA_VERSION,
        }
    )


def _execution_manifest(cells: Sequence[DenseScaleCell]) -> dict[str, Any]:
    schedule = [cell.to_dict() for cell in cells]
    return _with_digest(
        {
            "all_or_nothing": True,
            "cell_count": EXPECTED_CELL_COUNT,
            "development_task_count": TASK_COUNT,
            "exploration_seeds": list(EXPLORATION_SEEDS),
            "outcome_aware_retry": False,
            "scale_count": len(SCALE_ORDER),
            "scale_order": list(SCALE_ORDER),
            "schedule": schedule,
            "schedule_digest": sha256_json(schedule),
            "schedule_order": "task_acceptance_then_scale_then_seed",
            "schema_version": EXECUTION_SCHEMA_VERSION,
        }
    )


def _assert_no_forbidden_material(payload: Any, *, path: str = "$") -> None:
    pending: list[tuple[Any, str]] = [(payload, path)]
    while pending:
        current, current_path = pending.pop()
        if type(current) is dict:
            forbidden = sorted(set(current) & _FORBIDDEN_PERSISTED_KEYS)
            if forbidden:
                raise DenseScaleManifestError(
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


def build_countdown_thompson_dense_scale_payload(
    *, repository_root: Path | None = None
) -> dict[str, Any]:
    """Build the sealed v5 matrix without executing any search cell."""

    root = _repository_root(repository_root)
    design_raw = _read_stable_regular_file(
        root / FROZEN_DESIGN_PATH,
        label="frozen design",
    )
    if _sha256_bytes(design_raw) != FROZEN_DESIGN_SHA256:
        raise DenseScaleManifestError("frozen design bytes drifted")
    authority, prior_cohorts, authority_payloads = _verified_authority(root)
    cohort, _ = _cohort_manifest(authority, prior_cohorts)
    proposal = _proposal_manifest(authority_payloads)
    budget = _budget_manifest(authority_payloads)
    methods = _methods_manifest()
    runtime_binding = _source_binding(root, authority_payloads)
    cells = _cells_from_components(cohort, proposal, methods, budget)
    analysis = _analysis_manifest()
    execution = _execution_manifest(cells)
    payload = _with_digest(
        {
            "analysis": analysis,
            "authority": authority,
            "budget": budget,
            "bundle_id": BUNDLE_ID,
            "claim_boundary": (
                "Outcome-blind source-disjoint development preregistration only; "
                "no search outcome, retry, QMC claim, method-superiority claim, "
                "or locked-128 authority is present."
            ),
            "cohort": cohort,
            "execution_matrix": execution,
            "frozen_design": {
                "path": FROZEN_DESIGN_PATH.as_posix(),
                "revision": FROZEN_DESIGN_REVISION,
                "sha256": FROZEN_DESIGN_SHA256,
            },
            "implementation_base": IMPLEMENTATION_BASE,
            "materialization_contract": {
                "persisted_perturbation_point_count": 0,
                "persisted_proposal_row_count": 0,
                "persisted_provider_output_count": 0,
                "persisted_search_record_count": 0,
                "precomputed_perturbation_bank_bytes": 0,
                "provider_calls": 0,
            },
            "methods": methods,
            "proposal": proposal,
            "runtime_binding": runtime_binding,
            "schema_version": BUNDLE_SCHEMA_VERSION,
            "sealed_before_development_search_outcomes": True,
        }
    )
    if set(payload) != _TOP_LEVEL_FIELDS:
        raise DenseScaleManifestError("top-level preregistration schema drifted")
    _assert_no_forbidden_material(payload)
    return payload


def _parse_canonical_payload(raw: bytes) -> dict[str, Any]:
    try:
        parsed = strict_json_loads(raw.decode("utf-8"))
    except (RecursionError, UnicodeDecodeError, TraceValidationError) as error:
        raise DenseScaleManifestError("invalid strict preregistration JSON") from error
    if type(parsed) is not dict or set(parsed) != _TOP_LEVEL_FIELDS:
        raise DenseScaleManifestError("preregistration top-level schema drifted")
    if raw != _canonical_bytes(parsed):
        raise DenseScaleManifestError("preregistration bytes are not canonical")
    core = {
        key: value for key, value in parsed.items() if key != "deterministic_digest"
    }
    if parsed["deterministic_digest"] != sha256_json(core):
        raise DenseScaleManifestError("preregistration deterministic digest drifted")
    _assert_no_forbidden_material(parsed)
    return parsed


def _directory_state(observed: os.stat_result) -> tuple[int, ...]:
    return (
        observed.st_dev,
        observed.st_ino,
        observed.st_mode,
        observed.st_nlink,
        observed.st_uid,
        observed.st_gid,
        observed.st_size,
        observed.st_mtime_ns,
        observed.st_ctime_ns,
    )


def _inode_identity(observed: os.stat_result) -> tuple[int, int, int]:
    return (
        observed.st_dev,
        observed.st_ino,
        stat.S_IFMT(observed.st_mode),
    )


def _entry_state(
    directory_fd: int,
    name: str,
) -> os.stat_result | None:
    try:
        return os.stat(
            name,
            dir_fd=directory_fd,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return None


@dataclass(frozen=True)
class _BundleSnapshot:
    raw: bytes
    directory_state: tuple[int, ...]
    member_state: tuple[int, ...]


def _read_bundle_snapshot(bundle_dir: Path) -> _BundleSnapshot:
    directory = Path(bundle_dir)
    try:
        path_state = directory.lstat()
    except OSError as error:
        raise DenseScaleManifestError("bundle directory is unavailable") from error
    if stat.S_ISLNK(path_state.st_mode) or not stat.S_ISDIR(path_state.st_mode):
        raise DenseScaleManifestError("bundle path must be a real directory")
    directory_fd = -1
    file_fd = -1
    try:
        flags = (
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
        )
        directory_fd = os.open(directory, flags)
        opened_directory = os.fstat(directory_fd)
        directory_generation = _directory_state(opened_directory)
        if set(os.listdir(directory_fd)) != {BUNDLE_FILENAME}:
            raise DenseScaleManifestError("bundle directory closure drifted")
        file_fd = os.open(
            BUNDLE_FILENAME,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0),
            dir_fd=directory_fd,
        )
        opened = os.fstat(file_fd)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or opened.st_uid != os.geteuid()
            or opened.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
            or opened.st_size > _BUNDLE_BYTE_CAP
        ):
            raise DenseScaleManifestError("bundle member is not a bounded owned file")
        remaining = opened.st_size
        chunks: list[bytes] = []
        while remaining:
            chunk = os.read(file_fd, min(remaining, _READ_CHUNK_BYTES))
            if not chunk:
                raise DenseScaleManifestError("bundle member truncated during read")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(file_fd, 1):
            raise DenseScaleManifestError("bundle member grew during read")
        if _directory_state(os.fstat(file_fd)) != _directory_state(opened):
            raise DenseScaleManifestError("bundle member changed during read")
        path_member = os.stat(
            BUNDLE_FILENAME,
            dir_fd=directory_fd,
            follow_symlinks=False,
        )
        if _directory_state(path_member) != _directory_state(opened):
            raise DenseScaleManifestError("bundle member path rotated during read")
        if _directory_state(os.fstat(directory_fd)) != directory_generation:
            raise DenseScaleManifestError("bundle directory changed during read")
        final_path_state = directory.lstat()
        if _directory_state(final_path_state) != _directory_state(opened_directory):
            raise DenseScaleManifestError("bundle directory path rotated during read")
        return _BundleSnapshot(
            raw=b"".join(chunks),
            directory_state=_directory_state(opened_directory),
            member_state=_directory_state(opened),
        )
    except OSError as error:
        raise DenseScaleManifestError("bundle descriptor read failed") from error
    finally:
        if file_fd >= 0:
            os.close(file_fd)
        if directory_fd >= 0:
            os.close(directory_fd)


def _read_bundle_bytes(bundle_dir: Path) -> bytes:
    return _read_bundle_snapshot(bundle_dir).raw


@dataclass(frozen=True)
class VerifiedDenseScaleBundle:
    """A verified preregistration and reconstructed frozen schedule."""

    directory: Path
    _payload: dict[str, Any]
    _cells: tuple[DenseScaleCell, ...]

    @property
    def payload(self) -> dict[str, Any]:
        return deepcopy(self._payload)

    @property
    def cells(self) -> tuple[DenseScaleCell, ...]:
        return self._cells

    @property
    def seal_digest(self) -> str:
        return self._payload["deterministic_digest"]


def verify_countdown_thompson_dense_scale_bundle(
    bundle_dir: Path,
    *,
    repository_root: Path | None = None,
) -> VerifiedDenseScaleBundle:
    """Verify canonical bytes, authorities, regeneration, and schedule closure."""

    initial_snapshot = _read_bundle_snapshot(bundle_dir)
    raw = initial_snapshot.raw
    payload = _parse_canonical_payload(raw)
    expected = build_countdown_thompson_dense_scale_payload(
        repository_root=repository_root
    )
    if raw != _canonical_bytes(expected):
        raise DenseScaleManifestError(
            "preregistration differs from independent deterministic regeneration"
        )
    cells = _cells_from_components(
        payload["cohort"],
        payload["proposal"],
        payload["methods"],
        payload["budget"],
    )
    schedule = [cell.to_dict() for cell in cells]
    execution = payload["execution_matrix"]
    if execution["schedule"] != schedule or execution["schedule_digest"] != sha256_json(
        schedule
    ):
        raise DenseScaleManifestError("dense-scale schedule rows drifted")
    final_snapshot = _read_bundle_snapshot(bundle_dir)
    if final_snapshot != initial_snapshot:
        raise DenseScaleManifestError("bundle changed during verification")
    return VerifiedDenseScaleBundle(Path(bundle_dir), deepcopy(payload), cells)


def iter_countdown_thompson_dense_scale_cells(
    bundle: VerifiedDenseScaleBundle,
) -> tuple[DenseScaleCell, ...]:
    if type(bundle) is not VerifiedDenseScaleBundle:
        raise TypeError("bundle must be exactly VerifiedDenseScaleBundle")
    return bundle.cells


def _rename_directory_noreplace_at(
    source_directory_fd: int,
    source_name: str,
    destination_directory_fd: int,
    destination_name: str,
) -> None:
    """Atomically rename one directory entry without replacing another."""

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
            source_directory_fd,
            os.fsencode(source_name),
            destination_directory_fd,
            os.fsencode(destination_name),
            0x00000004,
        )
    elif sys.platform.startswith("linux"):
        try:
            rename = libc.renameat2
        except AttributeError as error:
            raise OSError(
                errno.ENOSYS,
                "atomic no-replace publication is unsupported",
                destination_name,
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
            source_directory_fd,
            os.fsencode(source_name),
            destination_directory_fd,
            os.fsencode(destination_name),
            0x00000001,
        )
    else:
        raise OSError(
            errno.ENOSYS,
            "atomic no-replace publication is unsupported",
            destination_name,
        )
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise FileExistsError(
            error_number,
            "dense-scale bundle destination exists",
            destination_name,
        )
    raise OSError(error_number, os.strerror(error_number), destination_name)


def _rename_directory_noreplace(source: Path, destination: Path) -> None:
    """Path wrapper retained for direct no-replace qualification tests."""

    at_fdcwd = -2 if sys.platform == "darwin" else -100
    _rename_directory_noreplace_at(
        at_fdcwd,
        os.fspath(source),
        at_fdcwd,
        os.fspath(destination),
    )


def _make_staging_directory(parent_fd: int, target_name: str) -> tuple[str, os.stat_result]:
    for _ in range(128):
        name = f".{target_name}.tmp-{secrets.token_hex(12)}"
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent_fd)
        except FileExistsError:
            continue
        observed = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if (
            not stat.S_ISDIR(observed.st_mode)
            or observed.st_uid != os.geteuid()
            or stat.S_IMODE(observed.st_mode) != 0o700
        ):
            raise DenseScaleManifestError("staging directory identity is invalid")
        return name, observed
    raise DenseScaleManifestError("could not allocate a unique staging directory")


def _write_all(file_fd: int, raw: bytes) -> None:
    remaining = memoryview(raw)
    while remaining:
        written = os.write(file_fd, remaining)
        if written <= 0:
            raise OSError(errno.EIO, "short write while sealing preregistration")
        remaining = remaining[written:]


def _read_exact_at(file_fd: int, byte_count: int) -> bytes:
    chunks: list[bytes] = []
    offset = 0
    while offset < byte_count:
        chunk = os.pread(
            file_fd,
            min(byte_count - offset, _READ_CHUNK_BYTES),
            offset,
        )
        if not chunk:
            raise DenseScaleManifestError("staging bundle truncated during readback")
        chunks.append(chunk)
        offset += len(chunk)
    if os.pread(file_fd, 1, byte_count):
        raise DenseScaleManifestError("staging bundle grew during readback")
    return b"".join(chunks)


def _require_pinned_member_bytes(
    *,
    directory_fd: int,
    member_fd: int,
    expected_raw: bytes,
    error_message: str,
) -> os.stat_result:
    before = os.fstat(member_fd)
    readback = _read_exact_at(member_fd, len(expected_raw))
    after = os.fstat(member_fd)
    path_state = _entry_state(directory_fd, BUNDLE_FILENAME)
    if (
        path_state is None
        or readback != expected_raw
        or _directory_state(before) != _directory_state(after)
        or _directory_state(path_state) != _directory_state(after)
        or not stat.S_ISREG(after.st_mode)
        or after.st_nlink != 1
        or after.st_uid != os.geteuid()
        or stat.S_IMODE(after.st_mode) != 0o644
        or after.st_size != len(expected_raw)
    ):
        raise DenseScaleManifestError(error_message)
    return after


def _cleanup_pinned_staging_directory(
    *,
    parent_fd: int,
    staging_fd: int,
    staging_name: str,
    staging_identity: tuple[int, int, int],
    member_state: os.stat_result | None,
) -> None:
    """Best-effort cleanup only while the original directory entry is pinned."""

    current = _entry_state(parent_fd, staging_name)
    if current is None or _inode_identity(current) != staging_identity:
        return
    try:
        names = set(os.listdir(staging_fd))
        if member_state is not None and names == {BUNDLE_FILENAME}:
            current_member = _entry_state(staging_fd, BUNDLE_FILENAME)
            if (
                current_member is not None
                and _directory_state(current_member) == _directory_state(member_state)
            ):
                os.unlink(BUNDLE_FILENAME, dir_fd=staging_fd)
                os.fsync(staging_fd)
        elif names:
            return
        current = _entry_state(parent_fd, staging_name)
        if current is not None and _inode_identity(current) == staging_identity:
            os.rmdir(staging_name, dir_fd=parent_fd)
            os.fsync(parent_fd)
    except OSError:
        return


def _close_descriptors_best_effort(*descriptors: int) -> None:
    for descriptor in descriptors:
        if descriptor < 0:
            continue
        try:
            os.close(descriptor)
        except OSError:
            continue


def write_countdown_thompson_dense_scale_bundle(
    destination: Path,
    *,
    repository_root: Path | None = None,
) -> Path:
    """Create one closed preregistration directory without overwriting.

    Publication is relative to one pinned parent descriptor.  The staging
    directory and its only member remain open through the atomic no-replace
    rename.  Before descriptor cleanup, a final collective observation checks
    the canonical bytes, pinned identities, and descriptor-relative plus
    lexical target binding.  As with any path-returning API, this observation
    does not freeze same-credential mutations made after an object's final
    check.
    """

    target = Path(destination)
    parent = target.parent
    if target.name in {"", ".", ".."}:
        raise DenseScaleManifestError("bundle destination name is invalid")
    try:
        parent_path_state = parent.lstat()
    except OSError as error:
        raise DenseScaleManifestError("bundle parent is unavailable") from error
    if stat.S_ISLNK(parent_path_state.st_mode) or not stat.S_ISDIR(
        parent_path_state.st_mode
    ):
        raise DenseScaleManifestError("bundle parent must be a real directory")

    parent_fd = -1
    staging_fd = -1
    member_fd = -1
    staging_name: str | None = None
    staging_identity: tuple[int, int, int] | None = None
    member_state: os.stat_result | None = None
    published = False
    try:
        parent_fd = os.open(
            parent,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0),
        )
        opened_parent = os.fstat(parent_fd)
        if _inode_identity(opened_parent) != _inode_identity(parent_path_state):
            raise DenseScaleManifestError("bundle parent path changed during open")
        if _entry_state(parent_fd, target.name) is not None:
            raise FileExistsError(target)

        payload = build_countdown_thompson_dense_scale_payload(
            repository_root=repository_root
        )
        raw = _canonical_bytes(payload)
        staging_name, staging_path_state = _make_staging_directory(
            parent_fd,
            target.name,
        )
        staging_identity = _inode_identity(staging_path_state)
        staging_fd = os.open(
            staging_name,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0),
            dir_fd=parent_fd,
        )
        opened_staging = os.fstat(staging_fd)
        if _inode_identity(opened_staging) != staging_identity:
            raise DenseScaleManifestError("staging directory path changed during open")

        member_fd = os.open(
            BUNDLE_FILENAME,
            os.O_RDWR
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0),
            0o600,
            dir_fd=staging_fd,
        )
        _write_all(member_fd, raw)
        os.fchmod(member_fd, 0o644)
        os.fsync(member_fd)
        member_state = os.fstat(member_fd)
        member_state = _require_pinned_member_bytes(
            directory_fd=staging_fd,
            member_fd=member_fd,
            expected_raw=raw,
            error_message="staging bundle closure is invalid",
        )
        if set(os.listdir(staging_fd)) != {BUNDLE_FILENAME}:
            raise DenseScaleManifestError("staging bundle closure is invalid")
        os.fsync(staging_fd)

        source_state = _entry_state(parent_fd, staging_name)
        if source_state is None or _inode_identity(source_state) != staging_identity:
            raise DenseScaleManifestError("staging directory path changed before publish")
        if _entry_state(parent_fd, target.name) is not None:
            raise FileExistsError(target)
        _rename_directory_noreplace_at(
            parent_fd,
            staging_name,
            parent_fd,
            target.name,
        )
        published = True

        target_state = _entry_state(parent_fd, target.name)
        if target_state is None or _inode_identity(target_state) != staging_identity:
            raise DenseScaleManifestError("published directory identity drifted")
        if _entry_state(parent_fd, staging_name) is not None:
            raise DenseScaleManifestError("staging name survived publication")
        if set(os.listdir(staging_fd)) != {BUNDLE_FILENAME}:
            raise DenseScaleManifestError("published bundle closure drifted")
        published_member = _require_pinned_member_bytes(
            directory_fd=staging_fd,
            member_fd=member_fd,
            expected_raw=raw,
            error_message="published bundle member identity drifted",
        )
        if member_state is None or (
            _directory_state(published_member) != _directory_state(member_state)
            or _inode_identity(os.fstat(staging_fd)) != staging_identity
        ):
            raise DenseScaleManifestError("published bundle member identity drifted")
        os.fsync(staging_fd)
        os.fsync(parent_fd)

        final_member = _require_pinned_member_bytes(
            directory_fd=staging_fd,
            member_fd=member_fd,
            expected_raw=raw,
            error_message="published bundle final member check drifted",
        )
        if member_state is None or _directory_state(final_member) != _directory_state(
            member_state
        ):
            raise DenseScaleManifestError("published bundle final member check drifted")
        final_target_state = _entry_state(parent_fd, target.name)
        final_parent_path_state = parent.lstat()
        final_target_path_state = target.lstat()
        if (
            final_target_state is None
            or _inode_identity(final_target_state) != staging_identity
            or _inode_identity(final_parent_path_state) != _inode_identity(opened_parent)
            or _inode_identity(final_target_path_state) != staging_identity
            or _entry_state(parent_fd, staging_name) is not None
            or set(os.listdir(staging_fd)) != {BUNDLE_FILENAME}
        ):
            raise DenseScaleManifestError(
                "published bundle final target binding drifted"
            )
        final_path_member = _entry_state(staging_fd, BUNDLE_FILENAME)
        if (
            final_path_member is None
            or _directory_state(final_path_member) != _directory_state(final_member)
            or _directory_state(os.fstat(member_fd)) != _directory_state(final_member)
            or _inode_identity(os.fstat(staging_fd)) != staging_identity
        ):
            raise DenseScaleManifestError("published bundle final member check drifted")
        return target
    except FileExistsError:
        raise
    except DenseScaleManifestError:
        raise
    except OSError as error:
        raise DenseScaleManifestError("bundle descriptor publication failed") from error
    finally:
        try:
            if (
                not published
                and parent_fd >= 0
                and staging_fd >= 0
                and staging_name is not None
                and staging_identity is not None
            ):
                _cleanup_pinned_staging_directory(
                    parent_fd=parent_fd,
                    staging_fd=staging_fd,
                    staging_name=staging_name,
                    staging_identity=staging_identity,
                    member_state=member_state,
                )
        finally:
            _close_descriptors_best_effort(member_fd, staging_fd, parent_fd)


def _self_test(repository_root: Path | None) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="qmc-dense-scale-prereg-") as root:
        destination = Path(root) / "bundle"
        write_countdown_thompson_dense_scale_bundle(
            destination,
            repository_root=repository_root,
        )
        verified = verify_countdown_thompson_dense_scale_bundle(
            destination,
            repository_root=repository_root,
        )
        return {
            "bundle_id": BUNDLE_ID,
            "cell_count": len(verified.cells),
            "claim_boundary": (
                "manifest plumbing only; no development search outcome was opened"
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
        help="source checkout containing the tracked diagnostic authority",
    )
    args = parser.parse_args(argv)
    if args.create is not None:
        write_countdown_thompson_dense_scale_bundle(
            args.create,
            repository_root=args.repository_root,
        )
        verified = verify_countdown_thompson_dense_scale_bundle(
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
        verified = verify_countdown_thompson_dense_scale_bundle(
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
