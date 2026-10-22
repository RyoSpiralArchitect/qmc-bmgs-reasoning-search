"""Fixed-allocation, isolated diversity channels for Countdown inference.

This is an additive development API, not an E4/C5 execution adapter. Branches
reuse the unchanged Track A engine through its public API. No posterior, cache,
budget remainder or outcome is passed from one branch to another.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qmc_bmgs.benchmarks.countdown import CountdownTask
from qmc_bmgs.substrate.budget import TRACK_A_WORK_AXES, TrackAWorkBudget
from qmc_bmgs.substrate.countdown_search import (
    TrackABudgetProfile,
    TrackAMethodSpec,
    TrackASearchResult,
    build_search_run_identity,
    replay_countdown_track_a_search_bytes,
    run_countdown_track_a_search,
)
from qmc_bmgs.substrate.proposals import TrackAProposalSpec
from qmc_bmgs.substrate.trace import (
    TraceValidationError,
    canonical_trace_bytes,
    sha256_json,
    strict_json_loads,
    validate_trace_bytes,
)


# Reuse the reviewed stream construction and verified readout unchanged.
from qmc_bmgs_next.diversity_search import _reduce_channels, branch_seed

SCHEMA = "qmc-bmgs-feedback-allocation/v1"
ARMS = ("single16", "equal16", "weighted16")
_CHANNELS = {
    "single16": (("primary", 16),),
    "equal16": (("primary", 16), ("secondary", 16)),
    "weighted16": (("primary", 16), ("secondary", 16)),
}
_SEED_INDICES = {"single16": (0,), "equal16": (0, 1), "weighted16": (0, 1)}


_WEIGHTS = {"single16": (1,), "equal16": (1, 1), "weighted16": (3, 1)}


@dataclass(frozen=True)
class AllocationSearchSpec:
    """Three fixed alternatives, not an outcome-adaptive parameter sweep."""

    arm: str

    def __post_init__(self) -> None:
        if type(self.arm) is not str or self.arm not in ARMS:
            raise ValueError(f"arm must be one of {ARMS}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA,
            "arm": self.arm,
            "channels": [
                {"name": name, "scale": scale} for name, scale in _CHANNELS[self.arm]
            ],
            "allocation": "fixed_weights_floor_primary_remainder_to_last/v1",
            "allocation_weights": list(_WEIGHTS[self.arm]),
            "shared_posterior": False,
            "shared_cache": False,
            "reallocate_unspent_work": False,
            "early_stop_on_success": False,
            "seed_policy": "domain_separated_sha256_64bit/v1",
            "channel_seed_indices": list(_SEED_INDICES[self.arm]),
            "statistically_independent_observations": False,
            "readout": "first_exact_else_minimum_verified_error/v1",
        }


@dataclass(frozen=True)
class AllocationSearchResult:
    record: dict[str, Any]

    @property
    def summary(self) -> dict[str, Any]:
        return strict_json_loads(canonical_trace_bytes(self.record["summary"]).decode())

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_trace_bytes(self.record)


def _require_inputs(task, spec, budget_profile, exploration_seed, proposal):
    if type(task) is not CountdownTask or type(spec) is not AllocationSearchSpec:
        raise TypeError("exact task and allocation spec types are required")
    if type(budget_profile) is not TrackABudgetProfile:
        raise TypeError("exact budget profile type is required")
    if budget_profile.primary_axis != "legal_action_scores":
        raise ValueError("allocation comparison requires legal-action-score budgets")
    if type(exploration_seed) is not int or exploration_seed < 0:
        raise ValueError("exploration seed must be a nonnegative plain integer")
    if type(proposal) is not TrackAProposalSpec or proposal.positive_control:
        raise ValueError("provider-free non-oracle proposal required")
    if branch_seed(exploration_seed, 0) == branch_seed(exploration_seed, 1):
        raise ValueError("derived branch seed collision")


def channel_plan(
    spec: AllocationSearchSpec, budget_profile: TrackABudgetProfile
) -> tuple[tuple[str, TrackAMethodSpec, TrackABudgetProfile], ...]:
    """Split *every* work axis before search, retaining indivisible remainders."""
    if type(spec) is not AllocationSearchSpec:
        raise TypeError("exact allocation spec required")
    if type(budget_profile) is not TrackABudgetProfile:
        raise TypeError("exact budget profile required")
    if budget_profile.primary_axis != "legal_action_scores":
        raise ValueError("legal-action-score primary axis required")
    channels = _CHANNELS[spec.arm]
    weights = _WEIGHTS[spec.arm]
    total_weight = sum(weights)
    global_limits = budget_profile.budget.to_dict()
    plans = []
    allocated = {axis: 0 for axis in TRACK_A_WORK_AXES}
    for index, (name, scale) in enumerate(channels):
        limits = {
            axis: (
                limit - allocated[axis]
                if index == len(channels) - 1
                else limit * weights[index] // total_weight
            )
            for axis, limit in global_limits.items()
        }
        if limits["legal_action_scores"] < 1:
            raise ValueError("primary budget cannot allocate one unit to each channel")
        for axis in allocated:
            allocated[axis] += limits[axis]
        # The profile is determined by its limits, not the arm label, so the
        # channel has the same engine identity as a matched standalone run.
        # This deliberately uses the existing feedback-channel profile naming.
        profile = TrackABudgetProfile(
            profile_id="feedback_channel_" + sha256_json(limits),
            primary_axis="legal_action_scores",
            budget=TrackAWorkBudget(**limits),
        )
        plans.append(
            (
                name,
                TrackAMethodSpec.dimension_normalized_scaled_dense_thompson(
                    "iid", scale
                ),
                profile,
            )
        )
    assert all(
        sum(getattr(p.budget, axis) for _, _, p in plans) == global_limits[axis]
        for axis in TRACK_A_WORK_AXES
    )
    return tuple(plans)


def _assemble(task, spec, budget_profile, exploration_seed, proposal, channels):
    record = {
        "schema_version": SCHEMA,
        "task": task.to_dict(),
        "spec": spec.to_dict(),
        "budget_profile": budget_profile.to_dict(),
        "exploration_seed": exploration_seed,
        "proposal": proposal.to_dict(),
        "channels": channels,
        "summary": _reduce_channels(channels, budget_profile),
    }
    record["deterministic_digest"] = sha256_json(record)
    return AllocationSearchResult(record)


def run_allocation_search(
    task: CountdownTask,
    *,
    spec: AllocationSearchSpec,
    budget_profile: TrackABudgetProfile,
    exploration_seed: int,
    proposal: TrackAProposalSpec = TrackAProposalSpec("greedy_rollout_target_error/v1"),
) -> AllocationSearchResult:
    """Run isolated channels sequentially within one preallocated work budget."""
    _require_inputs(task, spec, budget_profile, exploration_seed, proposal)
    channels = []
    for (name, method, profile), seed_index in zip(
        channel_plan(spec, budget_profile), _SEED_INDICES[spec.arm]
    ):
        seed = branch_seed(exploration_seed, seed_index)
        result: TrackASearchResult = run_countdown_track_a_search(
            task,
            proposal=proposal,
            method=method,
            budget_profile=profile,
            exploration_seed=seed,
        )
        channels.append(
            {
                "name": name,
                "exploration_seed": seed,
                "budget_profile": profile.to_dict(),
                "method": method.to_dict(),
                "search_record": result.record,
            }
        )
    return _assemble(task, spec, budget_profile, exploration_seed, proposal, channels)


def replay_allocation_search_bytes(
    raw: bytes,
    *,
    task: CountdownTask,
    spec: AllocationSearchSpec,
    budget_profile: TrackABudgetProfile,
    exploration_seed: int,
    proposal: TrackAProposalSpec = TrackAProposalSpec("greedy_rollout_target_error/v1"),
) -> bytes:
    """Authenticate and generatively replay each branch, then the entire result.

    All inputs come from the caller's reviewed plan, never from an untrusted
    record. A plausible success flag or a self-consistent digest is not enough.
    """
    _require_inputs(task, spec, budget_profile, exploration_seed, proposal)
    parsed = strict_json_loads(raw.decode("utf-8"))
    fields = {
        "schema_version",
        "task",
        "spec",
        "budget_profile",
        "exploration_seed",
        "proposal",
        "channels",
        "summary",
        "deterministic_digest",
    }
    if type(parsed) is not dict or set(parsed) != fields:
        raise TraceValidationError("closed allocation record required")
    if canonical_trace_bytes(parsed) != raw:
        raise TraceValidationError("canonical allocation bytes required")
    core = {k: v for k, v in parsed.items() if k != "deterministic_digest"}
    if sha256_json(core) != parsed["deterministic_digest"]:
        raise TraceValidationError("allocation record digest mismatch")
    expected = {
        "schema_version": SCHEMA,
        "task": task.to_dict(),
        "spec": spec.to_dict(),
        "budget_profile": budget_profile.to_dict(),
        "exploration_seed": exploration_seed,
        "proposal": proposal.to_dict(),
    }
    if canonical_trace_bytes({k: parsed[k] for k in expected}) != canonical_trace_bytes(
        expected
    ):
        raise TraceValidationError("allocation inputs do not match reviewed inputs")
    plan = channel_plan(spec, budget_profile)
    if type(parsed["channels"]) is not list or len(parsed["channels"]) != len(plan):
        raise TraceValidationError("incomplete diversity channel set")
    channels = []
    for given, (name, method, profile), seed_index in zip(
        parsed["channels"], plan, _SEED_INDICES[spec.arm]
    ):
        seed = branch_seed(exploration_seed, seed_index)
        if type(given) is not dict or set(given) != {
            "name",
            "exploration_seed",
            "method",
            "budget_profile",
            "search_record",
        }:
            raise TraceValidationError("closed channel record required")
        header = {
            "name": name,
            "exploration_seed": seed,
            "method": method.to_dict(),
            "budget_profile": profile.to_dict(),
        }
        if canonical_trace_bytes(
            {k: given[k] for k in header}
        ) != canonical_trace_bytes(header):
            raise TraceValidationError("channel identity or allocated budget mismatch")
        trace_raw = canonical_trace_bytes(given["search_record"])
        validate_trace_bytes(trace_raw)
        identity = build_search_run_identity(
            task=task,
            proposal=proposal,
            method=method,
            budget_profile=profile,
            exploration_seed=seed,
        )
        replay_countdown_track_a_search_bytes(
            trace_raw,
            task=task,
            proposal=proposal,
            method=method,
            budget_profile=profile,
            exploration_seed=seed,
            expected_run_identity_digest=sha256_json(identity),
        )
        channels.append({**header, "search_record": given["search_record"]})
    reproduced = _assemble(
        task, spec, budget_profile, exploration_seed, proposal, channels
    )
    if reproduced.canonical_bytes != raw:
        raise TraceValidationError("allocation summary does not match complete replay")
    return raw
