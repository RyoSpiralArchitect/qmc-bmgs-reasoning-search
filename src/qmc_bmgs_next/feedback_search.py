"""Budget-matched, isolated feedback channels for Countdown inference.

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


SCHEMA = "qmc-bmgs-feedback-portfolio/v1"
ARMS = ("exact", "dense16", "calibrated1", "protected1")
_CHANNELS = {
    "exact": (("exact", 0),),
    "dense16": (("dense", 16),),
    "calibrated1": (("calibrated", 1),),
    "protected1": (("exact", 0), ("calibrated", 1)),
}


@dataclass(frozen=True)
class FeedbackSearchSpec:
    """Four fixed alternatives, not an outcome-adaptive parameter sweep."""

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
            "allocation": "equal_axis_caps_remainder_to_last/v1",
            "shared_posterior": False,
            "shared_cache": False,
            "reallocate_unspent_work": False,
            "early_stop_on_success": False,
            "seed_policy": "same_seed_paired_not_independent/v1",
            "readout": "first_exact_else_minimum_verified_error/v1",
        }


@dataclass(frozen=True)
class FeedbackSearchResult:
    record: dict[str, Any]

    @property
    def summary(self) -> dict[str, Any]:
        return strict_json_loads(canonical_trace_bytes(self.record["summary"]).decode())

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_trace_bytes(self.record)


def _require_inputs(task, spec, budget_profile, exploration_seed, proposal):
    if type(task) is not CountdownTask or type(spec) is not FeedbackSearchSpec:
        raise TypeError("exact task and feedback spec types are required")
    if type(budget_profile) is not TrackABudgetProfile:
        raise TypeError("exact budget profile type is required")
    if budget_profile.primary_axis != "legal_action_scores":
        raise ValueError("feedback portfolio requires legal-action-score budgets")
    if type(exploration_seed) is not int or exploration_seed < 0:
        raise ValueError("exploration seed must be a nonnegative plain integer")
    if type(proposal) is not TrackAProposalSpec or proposal.positive_control:
        raise ValueError("provider-free non-oracle proposal required")


def channel_plan(
    spec: FeedbackSearchSpec, budget_profile: TrackABudgetProfile
) -> tuple[tuple[str, TrackAMethodSpec, TrackABudgetProfile], ...]:
    """Split *every* work axis before search, retaining indivisible remainders."""
    if type(spec) is not FeedbackSearchSpec:
        raise TypeError("exact feedback spec required")
    if type(budget_profile) is not TrackABudgetProfile:
        raise TypeError("exact budget profile required")
    if budget_profile.primary_axis != "legal_action_scores":
        raise ValueError("legal-action-score primary axis required")
    channels = _CHANNELS[spec.arm]
    count = len(channels)
    if budget_profile.budget.legal_action_scores < count:
        raise ValueError("primary budget cannot allocate one unit to each channel")
    global_limits = budget_profile.budget.to_dict()
    plans = []
    for index, (name, scale) in enumerate(channels):
        limits = {
            axis: limit // count + (limit % count if index == count - 1 else 0)
            for axis, limit in global_limits.items()
        }
        # The profile is determined by its limits, not the arm label, so the
        # exact channel has the same engine identity as a matched half-budget
        # standalone exact run. All channel limits are also in the outer record.
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


def _reduce_channels(channels: list[dict], global_profile: TrackABudgetProfile):
    usage = {axis: 0 for axis in TRACK_A_WORK_AXES}
    terminals = []
    valid = True
    terminal_count = 0
    protected_success = None
    for index, channel in enumerate(channels):
        record = channel["search_record"]
        summary = record["events"][-1]["payload"]["summary"]
        for axis in usage:
            usage[axis] += summary["ledger_usage"][axis]
        valid = valid and summary["budget_valid"]
        terminal_count += summary["terminal_count"]
        if len(channels) == 2 and index == 0:
            protected_success = summary["success_any"]
        for event in record["events"]:
            if event["kind"] != "terminal_verified":
                continue
            p = event["payload"]
            v = p["verification"]
            if type(v["final_value"]) is not int or not v["source_use_exact"]:
                raise TraceValidationError("incomplete terminal cannot be read out")
            terminals.append(
                {
                    "channel_index": index,
                    "channel_name": channel["name"],
                    "observation_index": p["observation_index"],
                    "success": v["success"],
                    "absolute_error": abs(v["final_value"] - v["target"]),
                    "verification": v,
                    "actions": p["actions"],
                }
            )
    limits = global_profile.budget.to_dict()
    if any(usage[axis] > limits[axis] for axis in usage):
        raise TraceValidationError("combined work exceeds the shared budget")
    exact = [row for row in terminals if row["success"]]
    readout = (
        exact[0]
        if exact
        else min(
            terminals,
            key=lambda row: (
                row["absolute_error"],
                row["channel_index"],
                row["observation_index"],
            ),
            default=None,
        )
    )
    # No new verifier call is used for answer selection: these witnesses have
    # already been charged and verified within the underlying search.
    return {
        "success_any": bool(exact),
        "minimum_terminal_error": (
            min(row["absolute_error"] for row in terminals) if terminals else None
        ),
        "terminal_count": terminal_count,
        "exact_terminal_count": len(exact),
        "readout": readout,
        "readout_extra_verifier_calls": 0,
        "ledger_usage": usage,
        "unspent_work": {axis: limits[axis] - usage[axis] for axis in usage},
        "budget_valid": valid,
        "protected_allocated_budget_success": protected_success,
        "protects_full_budget_baseline": False,
        "provider_calls": 0,
    }


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
    return FeedbackSearchResult(record)


def run_feedback_search(
    task: CountdownTask,
    *,
    spec: FeedbackSearchSpec,
    budget_profile: TrackABudgetProfile,
    exploration_seed: int,
    proposal: TrackAProposalSpec = TrackAProposalSpec("greedy_rollout_target_error/v1"),
) -> FeedbackSearchResult:
    """Run isolated channels sequentially within one preallocated work budget."""
    _require_inputs(task, spec, budget_profile, exploration_seed, proposal)
    channels = []
    for name, method, profile in channel_plan(spec, budget_profile):
        result: TrackASearchResult = run_countdown_track_a_search(
            task,
            proposal=proposal,
            method=method,
            budget_profile=profile,
            exploration_seed=exploration_seed,
        )
        channels.append(
            {
                "name": name,
                "budget_profile": profile.to_dict(),
                "method": method.to_dict(),
                "search_record": result.record,
            }
        )
    return _assemble(task, spec, budget_profile, exploration_seed, proposal, channels)


def replay_feedback_search_bytes(
    raw: bytes,
    *,
    task: CountdownTask,
    spec: FeedbackSearchSpec,
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
        raise TraceValidationError("closed feedback record required")
    if canonical_trace_bytes(parsed) != raw:
        raise TraceValidationError("canonical feedback bytes required")
    core = {k: v for k, v in parsed.items() if k != "deterministic_digest"}
    if sha256_json(core) != parsed["deterministic_digest"]:
        raise TraceValidationError("feedback record digest mismatch")
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
        raise TraceValidationError("feedback inputs do not match reviewed inputs")
    plan = channel_plan(spec, budget_profile)
    if type(parsed["channels"]) is not list or len(parsed["channels"]) != len(plan):
        raise TraceValidationError("incomplete feedback channel set")
    channels = []
    for given, (name, method, profile) in zip(parsed["channels"], plan):
        if type(given) is not dict or set(given) != {
            "name",
            "method",
            "budget_profile",
            "search_record",
        }:
            raise TraceValidationError("closed channel record required")
        header = {
            "name": name,
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
            exploration_seed=exploration_seed,
        )
        replay_countdown_track_a_search_bytes(
            trace_raw,
            task=task,
            proposal=proposal,
            method=method,
            budget_profile=profile,
            exploration_seed=exploration_seed,
            expected_run_identity_digest=sha256_json(identity),
        )
        channels.append({**header, "search_record": given["search_record"]})
    reproduced = _assemble(
        task, spec, budget_profile, exploration_seed, proposal, channels
    )
    if reproduced.canonical_bytes != raw:
        raise TraceValidationError("feedback summary does not match complete replay")
    return raw
