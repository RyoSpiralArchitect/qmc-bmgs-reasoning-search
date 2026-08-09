"""Deterministic, replayable Track A search over Countdown-D6.

This module is deliberately narrower than an experiment runner.  It executes
one task, one proposal policy, one method, and one hard budget profile.  Task
banks, canary manifests, artifact publication, and statistical analysis remain
outside this boundary.
"""

from __future__ import annotations

import math
import platform
import sys
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from qmc_bmgs.benchmarks.countdown import (
    CountdownAction,
    CountdownState,
    CountdownTask,
    CountdownVerification,
)
from qmc_bmgs.substrate.budget import (
    TRACK_A_WORK_AXES,
    TrackABudgetExceeded,
    TrackAWorkBudget,
    TrackAWorkLedger,
)
from qmc_bmgs.substrate.perturbations import (
    LazyNormalSource,
    build_perturbation_run_identity,
    generate_perturbation_point,
)
from qmc_bmgs.substrate.proposals import (
    TrackAProposalRow,
    TrackAProposalSpec,
    evaluate_track_a_proposal,
)
from qmc_bmgs.substrate.trace import (
    RUN_IDENTITY_SCHEMA_VERSION,
    HashChainedTrace,
    TraceValidationError,
    canonical_json,
    canonical_trace_bytes,
    sha256_json,
    validate_trace_bytes,
)


METHOD_SPEC_SCHEMA_VERSION = "qmc-bmgs-track-a-method-spec/v1"
DIMENSION_NORMALIZED_METHOD_SPEC_SCHEMA_VERSION = "qmc-bmgs-track-a-method-spec/v2"
DENSE_TERMINAL_METHOD_SPEC_SCHEMA_VERSION = "qmc-bmgs-track-a-method-spec/v3"
GREEDY_ANCHORED_METHOD_SPEC_SCHEMA_VERSION = "qmc-bmgs-track-a-method-spec/v4"
BUDGET_PROFILE_SCHEMA_VERSION = "qmc-bmgs-track-a-budget-profile/v1"
SEARCH_SCHEMA_VERSION = "qmc-bmgs-track-a-countdown-search/v1"
SEARCH_EVENT_SCHEMA_VERSION = "qmc-bmgs-track-a-search-event/v1"
NO_PERTURBATION_METADATA_VERSION = "qmc-bmgs-no-perturbation-source/v1"
DIMENSION_NORMALIZED_SELECTION_RULE_ID = "probability_prior_sqrt_2_ln_action_noise/v1"
GREEDY_ANCHORED_SELECTION_RULE_ID = (
    "one_greedy_trajectory_then_probability_prior_sqrt_2_ln_action_noise/v1"
)
RECIPROCAL_ABSOLUTE_ERROR_TERMINAL_VALUE_RULE_ID = (
    "reciprocal_absolute_error_binary64_floor/v1"
)
MIN_POSITIVE_BINARY64 = float.fromhex("0x0.0000000000001p-1022")

_METHODS = {"greedy", "beam", "puct", "thompson"}
_SOURCES = {"none", "iid", "sobol"}
_PRIMARY_AXES = {"legal_action_scores", "verifier_calls"}


def _require_nonempty_string(value: object, label: str) -> str:
    if type(value) is not str or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _require_finite_float(
    value: object,
    label: str,
    *,
    minimum: float = 0.0,
    strict: bool = False,
) -> float:
    if type(value) is not float or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite plain float")
    if (strict and value <= minimum) or (not strict and value < minimum):
        relation = "greater than" if strict else "at least"
        raise ValueError(f"{label} must be {relation} {minimum}")
    return value


@dataclass(frozen=True)
class TrackAMethodSpec:
    """A closed, versioned Track A method definition."""

    method: str
    selected_source: str
    c_puct: float | None = None
    prior_bonus: float | None = None
    posterior_sd_scale: float | None = None
    beam_width: int | None = None
    selection_rule_id: str | None = None
    terminal_value_rule_id: str | None = None
    greedy_anchor_trajectory_count: int | None = None
    schema_version: str = METHOD_SPEC_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version not in {
            METHOD_SPEC_SCHEMA_VERSION,
            DIMENSION_NORMALIZED_METHOD_SPEC_SCHEMA_VERSION,
            DENSE_TERMINAL_METHOD_SPEC_SCHEMA_VERSION,
            GREEDY_ANCHORED_METHOD_SPEC_SCHEMA_VERSION,
        }:
            raise ValueError("unsupported Track A method-spec schema")
        if type(self.method) is not str:
            raise ValueError("method must be a plain string")
        if type(self.selected_source) is not str:
            raise ValueError("selected_source must be a plain string")
        if self.method not in _METHODS:
            raise ValueError(f"unsupported Track A method: {self.method!r}")
        if self.selected_source not in _SOURCES:
            raise ValueError("selected_source must be none, iid, or sobol")

        if self.schema_version in {
            DIMENSION_NORMALIZED_METHOD_SPEC_SCHEMA_VERSION,
            DENSE_TERMINAL_METHOD_SPEC_SCHEMA_VERSION,
            GREEDY_ANCHORED_METHOD_SPEC_SCHEMA_VERSION,
        }:
            if self.method != "thompson":
                raise ValueError(
                    "dimension-normalized method-spec v2 requires Thompson"
                )
            if self.selected_source not in {"iid", "sobol"}:
                raise ValueError("Thompson requires an IID or Sobol source")
            _require_finite_float(
                self.prior_bonus,
                "prior_bonus",
                minimum=0.0,
            )
            _require_finite_float(
                self.posterior_sd_scale,
                "posterior_sd_scale",
                minimum=0.0,
                strict=True,
            )
            if type(self.selection_rule_id) is not str:
                raise ValueError("selection_rule_id must be a plain string")
            selection_rule_id = DIMENSION_NORMALIZED_SELECTION_RULE_ID
            terminal_value_rule_id: str | None = None
            greedy_anchor_trajectory_count: int | None = None
            if self.schema_version == DENSE_TERMINAL_METHOD_SPEC_SCHEMA_VERSION:
                if type(self.terminal_value_rule_id) is not str:
                    raise ValueError("terminal_value_rule_id must be a plain string")
                if type(self.greedy_anchor_trajectory_count) is not int:
                    raise ValueError(
                        "greedy_anchor_trajectory_count must be a plain integer"
                    )
                terminal_value_rule_id = (
                    RECIPROCAL_ABSOLUTE_ERROR_TERMINAL_VALUE_RULE_ID
                )
                greedy_anchor_trajectory_count = 0
            elif self.schema_version == GREEDY_ANCHORED_METHOD_SPEC_SCHEMA_VERSION:
                if type(self.terminal_value_rule_id) is not str:
                    raise ValueError("terminal_value_rule_id must be a plain string")
                if type(self.greedy_anchor_trajectory_count) is not int:
                    raise ValueError(
                        "greedy_anchor_trajectory_count must be a plain integer"
                    )
                selection_rule_id = GREEDY_ANCHORED_SELECTION_RULE_ID
                terminal_value_rule_id = (
                    RECIPROCAL_ABSOLUTE_ERROR_TERMINAL_VALUE_RULE_ID
                )
                greedy_anchor_trajectory_count = 1
            expected = (
                self.selected_source,
                None,
                self.prior_bonus,
                self.posterior_sd_scale,
                None,
                selection_rule_id,
                terminal_value_rule_id,
                greedy_anchor_trajectory_count,
            )
        elif self.method == "greedy":
            expected = ("none", None, None, None, None)
        elif self.method == "beam":
            if type(self.beam_width) is not int:
                raise ValueError("beam_width must be the plain integer 2")
            expected = ("none", None, None, None, 2)
        elif self.method == "puct":
            _require_finite_float(
                self.c_puct,
                "c_puct",
                minimum=0.0,
                strict=True,
            )
            expected = ("none", 1.0, None, None, None)
        else:
            if self.selected_source not in {"iid", "sobol"}:
                raise ValueError("Thompson requires an IID or Sobol source")
            _require_finite_float(
                self.prior_bonus,
                "prior_bonus",
                minimum=0.0,
            )
            _require_finite_float(
                self.posterior_sd_scale,
                "posterior_sd_scale",
                minimum=0.0,
                strict=True,
            )
            expected = (
                self.selected_source,
                None,
                self.prior_bonus,
                self.posterior_sd_scale,
                None,
            )

        observed = (
            self.selected_source,
            self.c_puct,
            self.prior_bonus,
            self.posterior_sd_scale,
            self.beam_width,
        )
        if self.schema_version in {
            DIMENSION_NORMALIZED_METHOD_SPEC_SCHEMA_VERSION,
            DENSE_TERMINAL_METHOD_SPEC_SCHEMA_VERSION,
            GREEDY_ANCHORED_METHOD_SPEC_SCHEMA_VERSION,
        }:
            observed = (
                *observed,
                self.selection_rule_id,
                self.terminal_value_rule_id,
                self.greedy_anchor_trajectory_count,
            )
        elif any(
            value is not None
            for value in (
                self.selection_rule_id,
                self.terminal_value_rule_id,
                self.greedy_anchor_trajectory_count,
            )
        ):
            raise ValueError("method-spec v1 does not define v2+ semantics")
        if observed != expected:
            raise ValueError(f"fields do not match {self.method} method semantics")

    @classmethod
    def greedy(cls) -> TrackAMethodSpec:
        return cls(method="greedy", selected_source="none")

    @classmethod
    def beam_width_two(cls) -> TrackAMethodSpec:
        return cls(method="beam", selected_source="none", beam_width=2)

    @classmethod
    def puct(cls) -> TrackAMethodSpec:
        return cls(method="puct", selected_source="none", c_puct=1.0)

    @classmethod
    def thompson(
        cls,
        *,
        source: str,
        prior_bonus: float,
        posterior_sd_scale: float = 1.0,
    ) -> TrackAMethodSpec:
        return cls(
            method="thompson",
            selected_source=source,
            prior_bonus=prior_bonus,
            posterior_sd_scale=posterior_sd_scale,
        )

    @classmethod
    def frozen_thompson(cls, source: str) -> TrackAMethodSpec:
        return cls.thompson(
            source=source,
            prior_bonus=0.1,
            posterior_sd_scale=1.0,
        )

    @classmethod
    def candidate_thompson(cls, source: str) -> TrackAMethodSpec:
        return cls.thompson(
            source=source,
            prior_bonus=1.0,
            posterior_sd_scale=1.0,
        )

    @classmethod
    def dimension_normalized_thompson(cls, source: str) -> TrackAMethodSpec:
        """Return the outcome-free, one-factor Thompson scale repair."""

        return cls(
            method="thompson",
            selected_source=source,
            prior_bonus=1.0,
            posterior_sd_scale=1.0,
            selection_rule_id=DIMENSION_NORMALIZED_SELECTION_RULE_ID,
            schema_version=DIMENSION_NORMALIZED_METHOD_SPEC_SCHEMA_VERSION,
        )

    @classmethod
    def dimension_normalized_dense_thompson(cls, source: str) -> TrackAMethodSpec:
        """Add reciprocal absolute-error terminal feedback to v2 selection."""

        return cls(
            method="thompson",
            selected_source=source,
            prior_bonus=1.0,
            posterior_sd_scale=1.0,
            selection_rule_id=DIMENSION_NORMALIZED_SELECTION_RULE_ID,
            terminal_value_rule_id=(RECIPROCAL_ABSOLUTE_ERROR_TERMINAL_VALUE_RULE_ID),
            greedy_anchor_trajectory_count=0,
            schema_version=DENSE_TERMINAL_METHOD_SPEC_SCHEMA_VERSION,
        )

    @classmethod
    def greedy_anchored_dimension_normalized_dense_thompson(
        cls,
        source: str,
    ) -> TrackAMethodSpec:
        """Run one greedy trajectory before the v3 Thompson policy."""

        return cls(
            method="thompson",
            selected_source=source,
            prior_bonus=1.0,
            posterior_sd_scale=1.0,
            selection_rule_id=GREEDY_ANCHORED_SELECTION_RULE_ID,
            terminal_value_rule_id=(RECIPROCAL_ABSOLUTE_ERROR_TERMINAL_VALUE_RULE_ID),
            greedy_anchor_trajectory_count=1,
            schema_version=GREEDY_ANCHORED_METHOD_SPEC_SCHEMA_VERSION,
        )

    @property
    def method_id(self) -> str:
        if self.schema_version == DIMENSION_NORMALIZED_METHOD_SPEC_SCHEMA_VERSION:
            return "thompson_binary_terminal_dimnorm_noise/v2"
        if self.schema_version == DENSE_TERMINAL_METHOD_SPEC_SCHEMA_VERSION:
            return "thompson_reciprocal_error_terminal_dimnorm_noise/v3"
        if self.schema_version == GREEDY_ANCHORED_METHOD_SPEC_SCHEMA_VERSION:
            return "thompson_greedy_anchor_reciprocal_error_terminal_dimnorm_noise/v4"
        return {
            "greedy": "greedy/v1",
            "beam": "layer_synchronous_beam_width_2/v1",
            "puct": "puct_binary_terminal/v1",
            "thompson": "thompson_binary_terminal/v1",
        }[self.method]

    @property
    def stochastic(self) -> bool:
        return self.method == "thompson"

    @property
    def dimension_normalized(self) -> bool:
        return self.schema_version in {
            DIMENSION_NORMALIZED_METHOD_SPEC_SCHEMA_VERSION,
            DENSE_TERMINAL_METHOD_SPEC_SCHEMA_VERSION,
            GREEDY_ANCHORED_METHOD_SPEC_SCHEMA_VERSION,
        }

    @property
    def dense_terminal_value(self) -> bool:
        return self.schema_version in {
            DENSE_TERMINAL_METHOD_SPEC_SCHEMA_VERSION,
            GREEDY_ANCHORED_METHOD_SPEC_SCHEMA_VERSION,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "beam_width": self.beam_width,
            "c_puct": self.c_puct,
            "method": self.method,
            "method_id": self.method_id,
            "posterior_sd_scale": self.posterior_sd_scale,
            "prior_bonus": self.prior_bonus,
            "schema_version": self.schema_version,
            "selected_source": self.selected_source,
        }
        if self.dimension_normalized:
            payload["selection_rule_id"] = self.selection_rule_id
        if self.dense_terminal_value:
            payload["terminal_value_rule_id"] = self.terminal_value_rule_id
            payload["greedy_anchor_trajectory_count"] = (
                self.greedy_anchor_trajectory_count
            )
        return payload


def _action_dimension_noise_normalizer(action_count: int) -> float:
    """Scale a normal vector so its many-arm maximum stays order one."""

    if type(action_count) is not int or action_count < 1:
        raise ValueError("action_count must be a positive plain integer")
    if action_count == 1:
        return 1.0
    return math.sqrt(2.0 * math.log(action_count))


def _dimension_normalized_selection_semantics(
    method: TrackAMethodSpec,
    *,
    action_count: int,
    trajectory_index: int,
) -> dict[str, Any] | None:
    if type(method) is not TrackAMethodSpec:
        raise TypeError("method must be exactly TrackAMethodSpec")
    if not method.dimension_normalized:
        return None
    if type(trajectory_index) is not int or trajectory_index < 0:
        raise ValueError("trajectory_index must be a non-negative plain integer")
    payload: dict[str, Any] = {
        "action_count": action_count,
        "noise_dimension_normalizer": _action_dimension_noise_normalizer(action_count),
        "selection_rule_id": method.selection_rule_id,
    }
    if method.schema_version == GREEDY_ANCHORED_METHOD_SPEC_SCHEMA_VERSION:
        anchor_count = method.greedy_anchor_trajectory_count
        assert anchor_count == 1
        is_anchor = trajectory_index < anchor_count
        payload["selection_phase"] = (
            "greedy_anchor" if is_anchor else "posterior_perturbation"
        )
        payload["perturbation_point_usage"] = (
            "not_generated" if is_anchor else "selection_input"
        )
    return payload


def _selection_uses_perturbation(
    method: TrackAMethodSpec,
    *,
    trajectory_index: int,
) -> bool:
    """Return whether this selection consumes a source point."""

    if type(method) is not TrackAMethodSpec:
        raise TypeError("method must be exactly TrackAMethodSpec")
    if type(trajectory_index) is not int or trajectory_index < 0:
        raise ValueError("trajectory_index must be a non-negative plain integer")
    if not method.stochastic:
        return False
    if method.schema_version != GREEDY_ANCHORED_METHOD_SPEC_SCHEMA_VERSION:
        return True
    anchor_count = method.greedy_anchor_trajectory_count
    assert anchor_count == 1
    return trajectory_index >= anchor_count


def _dense_terminal_value_evidence(
    verification: CountdownVerification,
) -> dict[str, int | float]:
    """Build exact integer evidence for reciprocal absolute-error feedback."""

    if type(verification) is not CountdownVerification:
        raise TypeError("verification must be exactly CountdownVerification")
    final_value = verification.final_value
    target = verification.target
    if type(final_value) is not int or final_value <= 0:
        raise AssertionError("complete Countdown verification lacks a final value")
    if type(target) is not int or target <= 0:
        raise AssertionError("Countdown verification target drifted")
    if verification.success is not (final_value == target):
        raise AssertionError("Countdown exact-success semantics drifted")
    error = abs(final_value - target)
    numerator = 1
    denominator = 1 + error
    unfloored_value = numerator / denominator
    floor_applied = unfloored_value == 0.0
    return {
        "terminal_absolute_error": error,
        "terminal_value": (MIN_POSITIVE_BINARY64 if floor_applied else unfloored_value),
        "terminal_value_denominator": denominator,
        "terminal_value_floor": MIN_POSITIVE_BINARY64,
        "terminal_value_floor_applied": floor_applied,
        "terminal_value_numerator": numerator,
    }


def _terminal_backup_value(
    method: TrackAMethodSpec,
    verification: CountdownVerification,
) -> float:
    if type(method) is not TrackAMethodSpec:
        raise TypeError("method must be exactly TrackAMethodSpec")
    if type(verification) is not CountdownVerification:
        raise TypeError("verification must be exactly CountdownVerification")
    if not method.dense_terminal_value:
        return 1.0 if verification.success else 0.0
    if (
        method.terminal_value_rule_id
        != RECIPROCAL_ABSOLUTE_ERROR_TERMINAL_VALUE_RULE_ID
    ):
        raise AssertionError("dense terminal-value rule drifted")
    return float(_dense_terminal_value_evidence(verification)["terminal_value"])


@dataclass(frozen=True)
class TrackABudgetProfile:
    """One primary stopping axis plus explicit hard guards."""

    profile_id: str
    primary_axis: str
    budget: TrackAWorkBudget
    schema_version: str = BUDGET_PROFILE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_nonempty_string(self.profile_id, "profile_id")
        if self.schema_version != BUDGET_PROFILE_SCHEMA_VERSION:
            raise ValueError("unsupported Track A budget-profile schema")
        if self.primary_axis not in _PRIMARY_AXES:
            raise ValueError(
                "primary_axis must be legal_action_scores or verifier_calls"
            )
        if type(self.budget) is not TrackAWorkBudget:
            raise TypeError("budget must be a TrackAWorkBudget")
        if getattr(self.budget, self.primary_axis) < 1:
            raise ValueError("the primary budget limit must be positive")

    def to_dict(self) -> dict[str, Any]:
        return {
            "budget": self.budget.to_dict(),
            "primary_axis": self.primary_axis,
            "profile_id": self.profile_id,
            "schema_version": self.schema_version,
        }


def _proposal_spec_payload(spec: TrackAProposalSpec) -> dict[str, Any]:
    if type(spec) is not TrackAProposalSpec:
        raise TypeError("proposal must be exactly TrackAProposalSpec")
    return spec.to_dict()


def _search_runtime_metadata() -> dict[str, Any]:
    """Bind deterministic float/search replay to one explicit runtime."""

    return {
        "architecture": platform.machine(),
        "float_mantissa_bits": sys.float_info.mant_dig,
        "libc": list(platform.libc_ver()),
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "search_schema_version": SEARCH_SCHEMA_VERSION,
        "version": "qmc-bmgs-track-a-search-runtime/v1",
    }


def search_runtime_metadata() -> dict[str, Any]:
    """Return the runtime identity payload without starting a search run.

    Preregistration builders need to seal the exact deterministic-float
    runtime before opening outcomes.  This accessor performs no task lookup,
    proposal evaluation, graph mutation, or search execution.
    """

    return _search_runtime_metadata()


def _configuration_payload(
    method: TrackAMethodSpec,
    proposal: TrackAProposalSpec,
    budget_profile: TrackABudgetProfile,
) -> dict[str, Any]:
    return {
        # The generic trace identity carries the human-readable profile id and
        # hard limits, but the primary stopping axis also changes execution
        # semantics.  Bind the complete typed profile here so two profiles
        # cannot share a run identity merely by reusing a label and limits.
        "budget_profile_spec_digest": sha256_json(budget_profile.to_dict()),
        "method": method.to_dict(),
        "proposal": _proposal_spec_payload(proposal),
        "search_runtime_metadata_digest": sha256_json(_search_runtime_metadata()),
        "search_schema_version": SEARCH_SCHEMA_VERSION,
    }


def build_search_run_identity(
    *,
    task: CountdownTask,
    proposal: TrackAProposalSpec,
    method: TrackAMethodSpec,
    budget_profile: TrackABudgetProfile,
    exploration_seed: int,
) -> dict[str, Any]:
    """Build the exact run identity used by both execution and replay."""

    if type(task) is not CountdownTask:
        raise TypeError("task must be exactly CountdownTask")
    if type(method) is not TrackAMethodSpec:
        raise TypeError("method must be exactly TrackAMethodSpec")
    if type(budget_profile) is not TrackABudgetProfile:
        raise TypeError("budget_profile must be exactly TrackABudgetProfile")
    _proposal_spec_payload(proposal)
    if type(exploration_seed) is not int or exploration_seed < 0:
        raise ValueError("exploration_seed must be a non-negative plain integer")
    if not method.stochastic and exploration_seed != 0:
        raise ValueError("deterministic methods require exploration_seed=0")

    configuration_id = sha256_json(
        _configuration_payload(method, proposal, budget_profile)
    )
    if method.stochastic:
        return build_perturbation_run_identity(
            source=method.selected_source,
            exploration_seed=exploration_seed,
            tasks=(task,),
            work_budget=budget_profile.budget,
            budget_profile=budget_profile.profile_id,
            method_id=method.method_id,
            configuration_id=configuration_id,
        )

    task_rows = [task.to_dict()]
    no_source_metadata = {
        **_search_runtime_metadata(),
        "source": "none",
        "version": NO_PERTURBATION_METADATA_VERSION,
    }
    return {
        "budget_profile": budget_profile.profile_id,
        "configuration_id": configuration_id,
        "exploration_seed": 0,
        "generator_metadata_digest": sha256_json(no_source_metadata),
        "method_id": method.method_id,
        "run_identity_schema_version": RUN_IDENTITY_SCHEMA_VERSION,
        "selected_source": "none",
        "task_fingerprints": [task.task_fingerprint],
        "task_manifest_digest": sha256_json(task_rows),
        "work_limits": budget_profile.budget.to_dict(),
    }


def search_run_identity_digest(identity: Mapping[str, Any]) -> str:
    """Digest a strict finite-JSON run identity."""

    if not isinstance(identity, Mapping):
        raise TypeError("identity must be a mapping")
    return sha256_json(dict(identity))


@dataclass
class _Posterior:
    visits: int = 0
    mean: float = 0.0
    m2: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"m2": self.m2, "mean": self.mean, "visits": self.visits}


@dataclass
class _SearchNode:
    row: TrackAProposalRow
    posteriors: list[_Posterior]

    @classmethod
    def create(cls, row: TrackAProposalRow) -> _SearchNode:
        return cls(row=row, posteriors=[_Posterior() for _ in row.actions])

    def to_dict(self) -> dict[str, Any]:
        return {
            "posteriors": [item.to_dict() for item in self.posteriors],
            "proposal": self.row.to_dict(),
            "state": list(self.row.state),
        }


@dataclass(frozen=True)
class _Path:
    states: tuple[CountdownState, ...]
    actions: tuple[CountdownAction, ...] = ()
    edge_path: tuple[tuple[CountdownState, int], ...] = ()
    cumulative_prior_logp: float = 0.0

    @property
    def state(self) -> CountdownState:
        return self.states[-1]

    def extend(
        self,
        *,
        action: CountdownAction,
        action_index: int,
        child: CountdownState,
        prior_logp: float,
    ) -> _Path:
        return _Path(
            states=self.states + (child,),
            actions=self.actions + (action,),
            edge_path=self.edge_path + ((self.state, action_index),),
            cumulative_prior_logp=self.cumulative_prior_logp + prior_logp,
        )


@dataclass(frozen=True)
class _TerminalObservation:
    observation_index: int
    trajectory_index: int
    path: _Path
    verification: CountdownVerification

    @property
    def witness_digest(self) -> str:
        return sha256_json(
            {
                "actions": [action.to_dict() for action in self.path.actions],
                "states": [list(state) for state in self.path.states],
            }
        )


@dataclass(frozen=True)
class TrackASearchResult:
    """Final deterministic search record and compact public summary."""

    record: dict[str, Any]
    summary: dict[str, Any]
    run_identity_digest: str

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_trace_bytes(self.record)


def _argmax(values: Sequence[float]) -> int:
    if not values:
        raise ValueError("cannot select from an empty score vector")
    if any(not math.isfinite(value) for value in values):
        raise ValueError("selection values must be finite")
    return max(range(len(values)), key=lambda index: (values[index], -index))


def _action_trace_key(actions: Sequence[CountdownAction]) -> tuple[Any, ...]:
    return tuple(action.sort_key() for action in actions)


def _event_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "event_schema_version": SEARCH_EVENT_SCHEMA_VERSION,
        **dict(payload),
    }


class _SearchSession:
    def __init__(
        self,
        *,
        task: CountdownTask,
        proposal: TrackAProposalSpec,
        method: TrackAMethodSpec,
        budget_profile: TrackABudgetProfile,
        exploration_seed: int,
        replay_material: Mapping[tuple[str, int], tuple[dict[str, Any], dict[str, Any]]]
        | None = None,
    ) -> None:
        self.task = task
        self.proposal = proposal
        self.method = method
        self.budget_profile = budget_profile
        self.exploration_seed = exploration_seed
        self.run_identity = build_search_run_identity(
            task=task,
            proposal=proposal,
            method=method,
            budget_profile=budget_profile,
            exploration_seed=exploration_seed,
        )
        self.ledger = TrackAWorkLedger(budget_profile.budget)
        self.trace = HashChainedTrace(self.run_identity)
        self._final_reservation = self.trace.reserve_event_slots(1)
        self.normal_source = (
            LazyNormalSource(
                source=method.selected_source,
                exploration_seed=exploration_seed,
                trace=self.trace,
                tasks=(task,),
            )
            if method.stochastic
            else None
        )
        self.nodes: dict[CountdownState, _SearchNode] = {}
        self.terminals: list[_TerminalObservation] = []
        self.stop_reason: str | None = None
        self.stop_attempted_charge: dict[str, int] | None = None
        self.stop_blocked_axes: tuple[str, ...] = ()
        self.incomplete_trajectory_count = 0
        self._poisoned = False
        self._replay_mode = replay_material is not None
        self._replay_material = dict(replay_material or {})
        self._consumed_replay_material: set[tuple[str, int]] = set()
        if self._replay_material and not method.stochastic:
            raise ValueError("deterministic search cannot receive replay material")

    def _poison(self, reason_code: str, *, prepared: Any | None = None) -> None:
        self._poisoned = True
        if prepared is not None and self.normal_source is not None:
            try:
                self.normal_source.poison_prepared(
                    prepared,
                    reason_code=reason_code,
                )
            except Exception:
                pass
        self.trace.poison(reason_code)

    def _record_budget_stop(
        self,
        attempted: Mapping[str, int],
        blocked_axes: Sequence[str],
    ) -> None:
        blocked = tuple(blocked_axes)
        if not blocked:
            raise AssertionError("budget stop requires at least one blocked axis")
        self.stop_attempted_charge = {
            axis: int(attempted.get(axis, 0)) for axis in TRACK_A_WORK_AXES
        }
        self.stop_blocked_axes = blocked
        non_primary = tuple(
            axis for axis in blocked if axis != self.budget_profile.primary_axis
        )
        self.stop_reason = (
            "guard_budget_blocked" if non_primary else "primary_budget_blocked"
        )

    def _preflight(self, increments: Mapping[str, int]) -> bool:
        blocked = self.ledger.preflight(**dict(increments))
        if blocked:
            self._record_budget_stop(increments, blocked)
            return False
        return True

    def _preflight_trajectory(self) -> bool:
        if self.budget_profile.primary_axis != "verifier_calls":
            return True
        increments = {axis: 0 for axis in TRACK_A_WORK_AXES}
        increments["verifier_calls"] = 1
        return self._preflight(increments)

    def _validate_row(
        self,
        row: TrackAProposalRow,
        state: CountdownState,
        actions: tuple[CountdownAction, ...],
    ) -> None:
        if type(row) is not TrackAProposalRow:
            raise TypeError("proposal evaluator must return exactly TrackAProposalRow")
        if row.state != state:
            raise AssertionError("proposal row state drifted")
        if row.actions != actions:
            raise AssertionError("proposal action order drifted")
        if len(row.prior_logp) != len(actions):
            raise AssertionError("proposal score dimension drifted")
        if any(not math.isfinite(value) for value in row.prior_logp):
            raise AssertionError("proposal contains a non-finite log probability")

    def _row_after_charge(
        self,
        state: CountdownState,
        actions: tuple[CountdownAction, ...],
    ) -> tuple[_SearchNode, bool]:
        existing = self.nodes.get(state)
        if existing is not None:
            if existing.row.actions != actions:
                raise AssertionError("cached proposal action order drifted")
            return existing, False
        row = evaluate_track_a_proposal(self.task, state, self.proposal)
        self._validate_row(row, state, actions)
        return _SearchNode.create(row), True

    def _proposal_event(self, node: _SearchNode) -> tuple[str, Mapping[str, Any]]:
        return (
            "proposal_materialized",
            _event_payload({"proposal": node.row.to_dict()}),
        )

    def _posterior_digest(self, node: _SearchNode) -> str:
        return sha256_json([item.to_dict() for item in node.posteriors])

    def _selection_values(
        self,
        node: _SearchNode,
        normals: Sequence[float] | None,
        *,
        trajectory_index: int,
    ) -> list[float]:
        if self.method.method == "greedy":
            return list(node.row.prior_logp)
        if self.method.method == "puct":
            total = sum(item.visits for item in node.posteriors)
            scale = math.sqrt(1.0 + total)
            assert self.method.c_puct == 1.0
            return [
                item.mean
                + self.method.c_puct * math.exp(logp) * scale / (1.0 + item.visits)
                for item, logp in zip(node.posteriors, node.row.prior_logp)
            ]
        if self.method.method != "thompson":
            raise AssertionError("method does not define an ordinary selection")
        if not _selection_uses_perturbation(
            self.method,
            trajectory_index=trajectory_index,
        ):
            if normals is not None:
                raise AssertionError(
                    "greedy anchor unexpectedly received perturbations"
                )
            return list(node.row.prior_logp)
        if normals is None:
            raise AssertionError("Thompson selection lacks perturbations")
        if len(normals) != len(node.row.actions):
            raise AssertionError("perturbation dimension drifted")
        assert self.method.prior_bonus is not None
        assert self.method.posterior_sd_scale is not None
        noise_dimension_normalizer = 1.0
        if self.method.dimension_normalized:
            noise_dimension_normalizer = _action_dimension_noise_normalizer(
                len(node.row.actions)
            )
        return [
            item.mean
            + self.method.prior_bonus * math.exp(logp)
            + self.method.posterior_sd_scale
            / (noise_dimension_normalizer * math.sqrt(item.visits + 1.0))
            * normal
            for item, logp, normal in zip(
                node.posteriors,
                node.row.prior_logp,
                normals,
            )
        ]

    @staticmethod
    def _prepared_events(prepared: Any) -> tuple[tuple[str, Mapping[str, Any]], ...]:
        events = prepared.uncharged_events
        if not isinstance(events, tuple):
            events = tuple(events)
        return events

    @staticmethod
    def _prepared_normals(prepared: Any) -> tuple[float, ...]:
        if hasattr(prepared, "normals"):
            return tuple(prepared.normals)
        if hasattr(prepared, "draw"):
            return tuple(prepared.draw.normals)
        raise TypeError("prepared perturbation does not expose normal values")

    @staticmethod
    def _prepared_point_digest(prepared: Any) -> str:
        if hasattr(prepared, "point"):
            return str(prepared.point["point_digest"])
        if hasattr(prepared, "draw"):
            return str(prepared.draw.point["point_digest"])
        raise TypeError("prepared perturbation does not expose a point digest")

    @staticmethod
    def _plan_material_event_count(plan: Any) -> int:
        for attribute in (
            "required_event_slots",
            "event_count",
            "material_event_count",
        ):
            if hasattr(plan, attribute):
                value = getattr(plan, attribute)
                if type(value) is int and value in {1, 2}:
                    return value
        if hasattr(plan, "node_materialized"):
            return 2 if bool(plan.node_materialized) else 1
        raise TypeError("perturbation plan does not expose its material event count")

    def _ordinary_step(
        self,
        path: _Path,
        *,
        trajectory_index: int,
    ) -> _Path | None:
        state = path.state
        actions = self.task.legal_actions(state)
        if not actions:
            raise AssertionError("ordinary step received a terminal state")
        miss = state not in self.nodes
        uses_perturbation = _selection_uses_perturbation(
            self.method,
            trajectory_index=trajectory_index,
        )
        increments = TrackAWorkLedger.search_step_increments(
            len(actions),
            proposal_cache_miss=miss,
            generate_perturbations=uses_perturbation,
        )

        plan: Any | None = None
        material_count = 0
        if uses_perturbation:
            if self.normal_source is None:
                raise AssertionError("perturbed selection lacks a normal source")
            plan = self.normal_source.plan_draw(
                task=self.task,
                state=state,
                actions=actions,
            )
            material_count = self._plan_material_event_count(plan)

        try:
            allowed = self._preflight(increments)
        except Exception:
            if plan is not None:
                self.normal_source.abort_plan(plan)
            raise
        if not allowed:
            if plan is not None:
                self.normal_source.abort_plan(plan)
            return None

        replay_key: tuple[str, int] | None = None
        stored_material: Any | None = None
        if plan is not None and self._replay_mode:
            replay_key = (plan.node_digest, plan.node_visit_index)
            if (
                replay_key not in self._replay_material
                or replay_key in self._consumed_replay_material
            ):
                self.normal_source.abort_plan(plan)
                raise TraceValidationError(
                    "stage 2 replay material is missing or already consumed"
                )
            replay_node, replay_point = self._replay_material[replay_key]
            try:
                stored_material = (
                    self.normal_source.validate_stored_material_for_replay(
                        plan,
                        node=replay_node,
                        point=replay_point,
                    )
                )
            except Exception:
                self.normal_source.abort_plan(plan)
                raise

        event_count = int(miss) + material_count + 1
        try:
            reservation = self.trace.reserve_event_slots(event_count)
        except Exception:
            if plan is not None:
                self.normal_source.abort_plan(plan)
            raise
        try:
            receipt = self.ledger.charge_search_step(
                len(actions),
                proposal_cache_miss=miss,
                generate_perturbations=uses_perturbation,
            )
        except TrackABudgetExceeded as error:
            reservation.cancel()
            if plan is not None:
                self.normal_source.abort_plan(plan)
            self._record_budget_stop(increments, error.blocked_axes)
            return None
        except Exception:
            reservation.cancel()
            if plan is not None:
                self.normal_source.abort_plan(plan)
            raise

        prepared: Any | None = None
        try:
            node, created = self._row_after_charge(state, actions)
            if created != miss:
                raise AssertionError("proposal cache status changed within a step")
            material_events: tuple[tuple[str, Mapping[str, Any]], ...] = ()
            normals: tuple[float, ...] | None = None
            point_digest: str | None = None
            if plan is not None:
                prepared = self.normal_source.materialize_precharged(
                    plan,
                    ledger=self.ledger,
                    receipt=receipt,
                    stored_material=stored_material,
                )
                material_events = self._prepared_events(prepared)
                if len(material_events) != material_count:
                    raise AssertionError("planned material event count drifted")
                normals = self._prepared_normals(prepared)
                point_digest = self._prepared_point_digest(prepared)

            values = self._selection_values(
                node,
                normals,
                trajectory_index=trajectory_index,
            )
            action_index = _argmax(values)
            action = actions[action_index]
            child = self.task.transition(state, action)
            extended = path.extend(
                action=action,
                action_index=action_index,
                child=child,
                prior_logp=node.row.prior_logp[action_index],
            )
            selection_fields: dict[str, Any] = {
                "action": action.to_dict(),
                "action_index": action_index,
                "action_order_digest": node.row.action_order_digest,
                "child_state": list(child),
                "cumulative_prior_logp_after": extended.cumulative_prior_logp,
                "cumulative_prior_logp_before": path.cumulative_prior_logp,
                "depth": len(path.actions),
                "method": self.method.to_dict(),
                "point_digest": point_digest,
                "posterior_before_digest": self._posterior_digest(node),
                "proposal_behavior_digest": node.row.behavior_digest,
                "scored_action_indices": list(range(len(actions))),
                "selected_value": values[action_index],
                "selection_values": values,
                "selection_values_digest": sha256_json(values),
                "state": list(state),
                "task_fingerprint": self.task.task_fingerprint,
                "trajectory_index": trajectory_index,
            }
            selection_semantics = _dimension_normalized_selection_semantics(
                self.method,
                action_count=len(actions),
                trajectory_index=trajectory_index,
            )
            if selection_semantics is not None:
                selection_fields["selection_semantics"] = selection_semantics
            selection_payload = _event_payload(selection_fields)
            events: list[tuple[str, Mapping[str, Any]]] = []
            if miss:
                events.append(self._proposal_event(node))
            events.extend(material_events)
            events.append(("selection_committed", selection_payload))
            self.trace.append_batch(
                tuple(events),
                receipt=receipt,
                receipt_event_index=len(events) - 1,
                reservation=reservation,
            )
            if prepared is not None:
                self.normal_source.commit_prepared(prepared)
                if self._replay_mode:
                    if not prepared.used_stored_material or replay_key is None:
                        raise AssertionError(
                            "stage 2 source did not consume validated material"
                        )
                    self._consumed_replay_material.add(replay_key)
            if miss:
                self.nodes[state] = node
            self._observe_storage(active_paths=(extended,))
            return extended
        except Exception:
            self._poison("accepted_search_step_commit_failure", prepared=prepared)
            raise

    def _preview_backup(
        self,
        path: _Path,
        value: float,
    ) -> list[dict[str, Any]]:
        updates: list[dict[str, Any]] = []
        for state, action_index in reversed(path.edge_path):
            node = self.nodes[state]
            current = node.posteriors[action_index]
            count = current.visits + 1
            delta = value - current.mean
            mean = current.mean + delta / count
            m2 = current.m2 + delta * (value - mean)
            updates.append(
                {
                    "action_index": action_index,
                    "after": {"m2": m2, "mean": mean, "visits": count},
                    "before": current.to_dict(),
                    "state": list(state),
                }
            )
        return updates

    def _commit_backup(self, updates: Sequence[Mapping[str, Any]]) -> None:
        for update in updates:
            state = tuple(update["state"])
            action_index = int(update["action_index"])
            after = update["after"]
            posterior = self.nodes[state].posteriors[action_index]
            posterior.visits = int(after["visits"])
            posterior.mean = float(after["mean"])
            posterior.m2 = float(after["m2"])

    def _verify_terminal(
        self,
        path: _Path,
        *,
        trajectory_index: int,
        backup: bool,
    ) -> bool:
        increments = {axis: 0 for axis in TRACK_A_WORK_AXES}
        increments["verifier_calls"] = 1
        if not self._preflight(increments):
            return False
        event_count = 2 if backup else 1
        reservation = self.trace.reserve_event_slots(event_count)
        try:
            receipt = self.ledger.charge(verifier_calls=1)
        except TrackABudgetExceeded as error:
            reservation.cancel()
            self._record_budget_stop(increments, error.blocked_axes)
            return False
        except Exception:
            reservation.cancel()
            raise

        try:
            verification = self.task.verify(path.actions)
            observation_index = len(self.terminals)
            terminal_payload = _event_payload(
                {
                    "actions": [action.to_dict() for action in path.actions],
                    "cumulative_prior_logp": path.cumulative_prior_logp,
                    "observation_index": observation_index,
                    "states": [list(state) for state in path.states],
                    "trajectory_index": trajectory_index,
                    "verification": verification.to_dict(),
                }
            )
            events: list[tuple[str, Mapping[str, Any]]] = [
                ("terminal_verified", terminal_payload)
            ]
            updates: list[dict[str, Any]] = []
            if backup:
                value = _terminal_backup_value(self.method, verification)
                updates = self._preview_backup(path, value)
                backup_payload: dict[str, Any] = {
                    "discount": 1.0,
                    "order": "leaf_to_root",
                    "terminal_value": value,
                    "trajectory_index": trajectory_index,
                    "updates": updates,
                }
                if self.method.dense_terminal_value:
                    backup_payload.update(_dense_terminal_value_evidence(verification))
                    backup_payload["terminal_value_rule_id"] = (
                        self.method.terminal_value_rule_id
                    )
                events.append(
                    (
                        "trajectory_backed_up",
                        _event_payload(backup_payload),
                    )
                )
            self.trace.append_batch(
                tuple(events),
                receipt=receipt,
                receipt_event_index=0,
                reservation=reservation,
            )
            if updates:
                self._commit_backup(updates)
            self.terminals.append(
                _TerminalObservation(
                    observation_index=observation_index,
                    trajectory_index=trajectory_index,
                    path=path,
                    verification=verification,
                )
            )
            self._observe_storage()
            return True
        except Exception:
            self._poison("accepted_terminal_commit_failure")
            raise

    def _run_greedy(self) -> None:
        if not self._preflight_trajectory():
            return
        path = _Path(states=(self.task.initial_state,))
        while len(path.state) > 1:
            extended = self._ordinary_step(path, trajectory_index=0)
            if extended is None:
                self.incomplete_trajectory_count += 1
                return
            path = extended
        if self._verify_terminal(path, trajectory_index=0, backup=False):
            self.stop_reason = "method_complete"

    def _beam_layer_increments(
        self,
        paths: Sequence[_Path],
        action_orders: Sequence[tuple[CountdownAction, ...]],
    ) -> dict[str, int]:
        unique_misses: dict[CountdownState, int] = {}
        for path, actions in zip(paths, action_orders):
            if path.state not in self.nodes:
                unique_misses.setdefault(path.state, len(actions))
        total_actions = sum(len(actions) for actions in action_orders)
        retained = min(2, total_actions)
        return {
            "proposal_state_evaluations": len(unique_misses),
            "proposal_action_scores": sum(unique_misses.values()),
            "legal_action_scores": total_actions,
            "generated_perturbation_coordinates": 0,
            "edge_selections": retained,
            "transitions": retained,
            "verifier_calls": 0,
        }

    def _run_beam(self) -> None:
        if not self._preflight_trajectory():
            return
        beam = [_Path(states=(self.task.initial_state,))]
        layer_index = 0
        while beam and len(beam[0].state) > 1:
            if any(len(path.state) != len(beam[0].state) for path in beam):
                raise AssertionError("beam paths are not layer-synchronous")
            action_orders = [self.task.legal_actions(path.state) for path in beam]
            if any(not actions for actions in action_orders):
                raise AssertionError("nonterminal beam parent has no legal action")
            increments = self._beam_layer_increments(beam, action_orders)
            if not self._preflight(increments):
                self.incomplete_trajectory_count += len(beam)
                return

            missing_states = []
            seen_missing: set[CountdownState] = set()
            for path in beam:
                if path.state not in self.nodes and path.state not in seen_missing:
                    seen_missing.add(path.state)
                    missing_states.append(path.state)
            reservation = self.trace.reserve_event_slots(len(missing_states) + 1)
            try:
                receipt = self.ledger.charge(**increments)
            except TrackABudgetExceeded as error:
                reservation.cancel()
                self._record_budget_stop(increments, error.blocked_axes)
                self.incomplete_trajectory_count += len(beam)
                return
            except Exception:
                reservation.cancel()
                raise

            try:
                staged: dict[CountdownState, _SearchNode] = {}
                for state in missing_states:
                    actions = self.task.legal_actions(state)
                    node, created = self._row_after_charge(state, actions)
                    if not created:
                        raise AssertionError("beam proposal cache changed within layer")
                    staged[state] = node

                candidates: list[tuple[Any, ...]] = []
                scored_parents: list[dict[str, Any]] = []
                for parent_index, (path, actions) in enumerate(
                    zip(beam, action_orders)
                ):
                    node = staged.get(path.state, self.nodes.get(path.state))
                    if node is None:
                        raise AssertionError("beam proposal row is unavailable")
                    scored_parents.append(
                        {
                            "action_order_digest": node.row.action_order_digest,
                            "parent_index": parent_index,
                            "proposal_behavior_digest": node.row.behavior_digest,
                            "scored_action_indices": list(range(len(actions))),
                            "state": list(path.state),
                        }
                    )
                    for action_index, action in enumerate(actions):
                        cumulative = (
                            path.cumulative_prior_logp
                            + node.row.prior_logp[action_index]
                        )
                        action_trace = path.actions + (action,)
                        candidates.append(
                            (
                                -cumulative,
                                _action_trace_key(action_trace),
                                parent_index,
                                action_index,
                                path,
                                node,
                                action,
                                cumulative,
                            )
                        )
                candidates.sort(key=lambda item: item[:4])
                selected = candidates[:2]
                next_beam: list[_Path] = []
                selected_payload: list[dict[str, Any]] = []
                for (
                    _,
                    _,
                    parent_index,
                    action_index,
                    path,
                    node,
                    action,
                    cumulative,
                ) in selected:
                    child = self.task.transition(path.state, action)
                    extended = path.extend(
                        action=action,
                        action_index=action_index,
                        child=child,
                        prior_logp=node.row.prior_logp[action_index],
                    )
                    if extended.cumulative_prior_logp != cumulative:
                        raise AssertionError("beam cumulative priority drifted")
                    next_beam.append(extended)
                    selected_payload.append(
                        {
                            "action": action.to_dict(),
                            "action_index": action_index,
                            "child_state": list(child),
                            "cumulative_prior_logp": cumulative,
                            "parent_index": parent_index,
                            "state": list(path.state),
                            "trace_key": [
                                list(item)
                                for item in _action_trace_key(extended.actions)
                            ],
                        }
                    )
                events: list[tuple[str, Mapping[str, Any]]] = [
                    self._proposal_event(staged[state]) for state in missing_states
                ]
                events.append(
                    (
                        "beam_layer_selection_committed",
                        _event_payload(
                            {
                                "beam_width": 2,
                                "layer_index": layer_index,
                                "scored_parents": scored_parents,
                                "selected": selected_payload,
                            }
                        ),
                    )
                )
                self.trace.append_batch(
                    tuple(events),
                    receipt=receipt,
                    receipt_event_index=len(events) - 1,
                    reservation=reservation,
                )
                self.nodes.update(staged)
                beam = next_beam
                layer_index += 1
                self._observe_storage(active_paths=beam)
            except Exception:
                self._poison("accepted_beam_layer_commit_failure")
                raise

        for trajectory_index, path in enumerate(beam):
            if not self._verify_terminal(
                path,
                trajectory_index=trajectory_index,
                backup=False,
            ):
                return
        self.stop_reason = "method_complete"

    def _run_adaptive(self) -> None:
        trajectory_index = 0
        while self.stop_reason is None:
            if not self._preflight_trajectory():
                return
            path = _Path(states=(self.task.initial_state,))
            while len(path.state) > 1:
                extended = self._ordinary_step(
                    path,
                    trajectory_index=trajectory_index,
                )
                if extended is None:
                    self.incomplete_trajectory_count += 1
                    return
                path = extended
            if not self._verify_terminal(
                path,
                trajectory_index=trajectory_index,
                backup=True,
            ):
                self.incomplete_trajectory_count += 1
                return
            trajectory_index += 1

    def _nodes_payload(self) -> list[dict[str, Any]]:
        return [
            self.nodes[state].to_dict()
            for state in sorted(self.nodes, key=lambda item: (-len(item), item))
        ]

    @staticmethod
    def _path_storage_payload(path: _Path) -> dict[str, Any]:
        return {
            "actions": [action.to_dict() for action in path.actions],
            "cumulative_prior_logp": path.cumulative_prior_logp,
            "edge_path": [
                {"action_index": action_index, "state": list(state)}
                for state, action_index in path.edge_path
            ],
            "states": [list(state) for state in path.states],
        }

    def _observe_storage(self, *, active_paths: Sequence[_Path] = ()) -> None:
        nodes = self._nodes_payload()
        retained = {
            "active_paths": [self._path_storage_payload(path) for path in active_paths],
            "nodes": nodes,
            "normal_source": (
                self.normal_source.state_snapshot()
                if self.normal_source is not None
                else None
            ),
            "terminal_witnesses": [
                {
                    "observation_index": item.observation_index,
                    "path": self._path_storage_payload(item.path),
                    "trajectory_index": item.trajectory_index,
                    "verification": item.verification.to_dict(),
                }
                for item in self.terminals
            ],
            "trace_events": list(self.trace.events),
        }
        self.ledger.observe_live_storage(
            live_nodes=len(nodes),
            live_bytes=len(canonical_json(retained).encode("utf-8")),
        )

    def _readout(self) -> dict[str, Any] | None:
        if not self.terminals:
            return None
        exact = [item for item in self.terminals if item.verification.success]
        if exact:
            selected = min(exact, key=lambda item: item.observation_index)
            reason = "first_exact_terminal"
        else:
            selected = min(
                self.terminals,
                key=lambda item: (
                    -item.path.cumulative_prior_logp,
                    _action_trace_key(item.path.actions),
                    item.observation_index,
                ),
            )
            reason = "highest_prior_verified_terminal"
        return {
            "observation_index": selected.observation_index,
            "reason": reason,
            "success": selected.verification.success,
            "witness_digest": selected.witness_digest,
        }

    def _summary(self) -> dict[str, Any]:
        if self.stop_reason is None:
            raise AssertionError("search ended without a stop reason")
        ledger_snapshot = self.ledger.snapshot()
        exact = [item for item in self.terminals if item.verification.success]
        successful_witnesses = sorted({item.witness_digest for item in exact})
        non_primary_blocked = [
            axis
            for axis in self.stop_blocked_axes
            if axis != self.budget_profile.primary_axis
        ]
        # A guard that lands exactly at zero remaining work did not reject the
        # final operation, but it is not demonstrably nonbinding either.  The
        # canary gate therefore fails conservatively even when the method also
        # completed naturally at that boundary.
        non_primary_exhausted = [
            axis
            for axis in ledger_snapshot["exhausted_axes"]
            if axis != self.budget_profile.primary_axis
        ]
        source_points = (
            self.normal_source.point_count if self.normal_source is not None else 0
        )
        return {
            "budget_profile": self.budget_profile.to_dict(),
            "budget_valid": not non_primary_blocked and not non_primary_exhausted,
            "exact_terminal_count": len(exact),
            "first_exact_observation_index": (
                exact[0].observation_index if exact else None
            ),
            "incomplete_trajectory_count": self.incomplete_trajectory_count,
            "ledger_usage": ledger_snapshot["usage"],
            "live_storage_semantics": (
                "canonical_json_bytes_of_retained_search_state/v1"
            ),
            "live_storage_is_actual_python_heap": False,
            "method": self.method.to_dict(),
            "node_count": len(self.nodes),
            "non_primary_exhausted_axes": non_primary_exhausted,
            "posterior_graph_digest": sha256_json(self._nodes_payload()),
            "proposal": _proposal_spec_payload(self.proposal),
            "readout": self._readout(),
            "run_identity_digest": search_run_identity_digest(self.run_identity),
            "schema_version": SEARCH_SCHEMA_VERSION,
            "selected_source_point_count": source_points,
            "stop_attempted_charge": self.stop_attempted_charge,
            "stop_blocked_axes": list(self.stop_blocked_axes),
            "stop_reason": self.stop_reason,
            "successful_terminal_diversity": len(successful_witnesses),
            "successful_witness_digests": successful_witnesses,
            "success_any": bool(exact),
            "terminal_count": len(self.terminals),
        }

    def run(self) -> TrackASearchResult:
        if self.method.method == "greedy":
            self._run_greedy()
        elif self.method.method == "beam":
            self._run_beam()
        else:
            self._run_adaptive()
        if self._poisoned:
            raise TraceValidationError("poisoned search cannot be finalized")
        if self._replay_mode and self._consumed_replay_material != set(
            self._replay_material
        ):
            raise TraceValidationError(
                "stage 2 replay left validated perturbation material unconsumed"
            )
        summary = self._summary()
        self.trace.append(
            "search_finished",
            _event_payload({"summary": summary}),
            reservation=self._final_reservation,
        )
        record = self.trace.finalize(self.ledger.snapshot())
        return TrackASearchResult(
            record=record,
            summary=summary,
            run_identity_digest=search_run_identity_digest(self.run_identity),
        )


def run_countdown_track_a_search(
    task: CountdownTask,
    *,
    proposal: TrackAProposalSpec,
    method: TrackAMethodSpec,
    budget_profile: TrackABudgetProfile,
    exploration_seed: int,
) -> TrackASearchResult:
    """Execute one single-threaded Track A search run."""

    session = _SearchSession(
        task=task,
        proposal=proposal,
        method=method,
        budget_profile=budget_profile,
        exploration_seed=exploration_seed,
    )
    return session.run()


def _action_from_payload(payload: Any) -> CountdownAction:
    if type(payload) is not dict or set(payload) != {"left", "operator", "right"}:
        raise TraceValidationError("stage 1 action material fields drifted")
    if type(payload["left"]) is not int or type(payload["right"]) is not int:
        raise TraceValidationError("stage 1 action operands are not plain integers")
    if type(payload["operator"]) is not str:
        raise TraceValidationError("stage 1 action operator is not a plain string")
    try:
        return CountdownAction(
            left=payload["left"],
            operator=payload["operator"],
            right=payload["right"],
        )
    except ValueError as error:
        raise TraceValidationError("stage 1 action material is invalid") from error


def _validate_stage_one_material(
    parsed: Mapping[str, Any],
    *,
    task: CountdownTask,
    proposal: TrackAProposalSpec,
    method: TrackAMethodSpec,
) -> dict[tuple[str, int], tuple[dict[str, Any], dict[str, Any]]]:
    """Independently regenerate proposal and perturbation material."""

    proposal_states: set[CountdownState] = set()
    nodes: dict[str, dict[str, Any]] = {}
    next_visits: dict[str, int] = {}
    point_digests: set[str] = set()
    referenced_point_digests: set[str] = set()
    validated_material: dict[
        tuple[str, int], tuple[dict[str, Any], dict[str, Any]]
    ] = {}
    point_count = 0

    for event in parsed["events"]:
        kind = event["kind"]
        payload = event["payload"]
        if kind == "proposal_materialized":
            if event["charge"] is not None:
                raise TraceValidationError(
                    "stage 1 proposal material must be uncharged"
                )
            if set(payload) != {"event_schema_version", "proposal"}:
                raise TraceValidationError("stage 1 proposal event fields drifted")
            if payload["event_schema_version"] != SEARCH_EVENT_SCHEMA_VERSION:
                raise TraceValidationError(
                    "stage 1 proposal event schema is unsupported"
                )
            stored = payload["proposal"]
            if type(stored) is not dict:
                raise TraceValidationError("stage 1 proposal row is not an object")
            state_payload = stored.get("state")
            if type(state_payload) is not list or any(
                type(value) is not int for value in state_payload
            ):
                raise TraceValidationError("stage 1 proposal state is invalid")
            try:
                state = task.canonical_state(state_payload)
            except ValueError as error:
                raise TraceValidationError(
                    "stage 1 proposal state is invalid"
                ) from error
            if state in proposal_states:
                raise TraceValidationError(
                    "stage 1 proposal state was materialized more than once"
                )
            expected = evaluate_track_a_proposal(task, state, proposal).to_dict()
            if stored != expected:
                raise TraceValidationError(
                    "stage 1 proposal failed independent regeneration"
                )
            proposal_states.add(state)
        elif kind == "node_materialized":
            if not method.stochastic:
                raise TraceValidationError(
                    "stage 1 deterministic search contains perturbation material"
                )
            if event["charge"] is not None:
                raise TraceValidationError("stage 1 node material must be uncharged")
            action_payload = payload.get("action_order")
            state_payload = payload.get("state")
            if type(action_payload) is not list or type(state_payload) is not list:
                raise TraceValidationError("stage 1 node material is malformed")
            actions = tuple(_action_from_payload(item) for item in action_payload)
            expected_node, _ = generate_perturbation_point(
                task=task,
                state=tuple(state_payload),
                actions=actions,
                source=method.selected_source,
                exploration_seed=parsed["run_identity"]["exploration_seed"],
                node_visit_index=0,
            )
            if payload != expected_node:
                raise TraceValidationError(
                    "stage 1 node failed independent regeneration"
                )
            digest = payload["node_digest"]
            if digest in nodes:
                raise TraceValidationError(
                    "stage 1 perturbation node was materialized more than once"
                )
            nodes[digest] = payload
            next_visits[digest] = 0
        elif kind == "perturbation_draw":
            if not method.stochastic:
                raise TraceValidationError(
                    "stage 1 deterministic search contains a perturbation point"
                )
            if event["charge"] is not None:
                raise TraceValidationError("stage 1 point material must be uncharged")
            node_digest = payload.get("node_digest")
            node = nodes.get(node_digest)
            if node is None:
                raise TraceValidationError(
                    "stage 1 perturbation point precedes its node"
                )
            visit_index = next_visits[node_digest]
            if payload.get("node_visit_index") != visit_index:
                raise TraceValidationError(
                    "stage 1 perturbation node-local visit has a gap"
                )
            actions = tuple(_action_from_payload(item) for item in node["action_order"])
            expected_node, expected_point = generate_perturbation_point(
                task=task,
                state=tuple(node["state"]),
                actions=actions,
                source=method.selected_source,
                exploration_seed=parsed["run_identity"]["exploration_seed"],
                node_visit_index=visit_index,
            )
            if node != expected_node or payload != expected_point:
                raise TraceValidationError(
                    "stage 1 point failed independent regeneration"
                )
            point_digest = payload["point_digest"]
            if point_digest in point_digests:
                raise TraceValidationError("stage 1 point digest was reused")
            point_digests.add(point_digest)
            validated_material[(node_digest, visit_index)] = (node, payload)
            point_count += 1
            next_visits[node_digest] = visit_index + 1
        elif kind == "selection_committed":
            if payload.get("event_schema_version") != SEARCH_EVENT_SCHEMA_VERSION:
                raise TraceValidationError(
                    "stage 1 selection event schema is unsupported"
                )
            charge = event["charge"]
            if charge is None:
                raise TraceValidationError("stage 1 selection lacks its receipt")
            scored = payload.get("scored_action_indices")
            if type(scored) is not list or scored != list(range(len(scored))):
                raise TraceValidationError(
                    "stage 1 selection scored-action indices drifted"
                )
            if charge["delta"]["legal_action_scores"] != len(scored):
                raise TraceValidationError(
                    "stage 1 selection-score receipt does not close"
                )
            semantics = payload.get("selection_semantics")
            if method.dimension_normalized:
                trajectory_index = payload.get("trajectory_index")
                if type(trajectory_index) is not int or trajectory_index < 0:
                    raise TraceValidationError(
                        "stage 1 dimension-normalized trajectory index drifted"
                    )
                expected_semantics = _dimension_normalized_selection_semantics(
                    method,
                    action_count=len(scored),
                    trajectory_index=trajectory_index,
                )
                if semantics != expected_semantics:
                    raise TraceValidationError(
                        "stage 1 dimension-normalized selection semantics drifted"
                    )
                if (
                    type(semantics) is not dict
                    or type(semantics.get("action_count")) is not int
                    or type(semantics.get("noise_dimension_normalizer")) is not float
                    or type(semantics.get("selection_rule_id")) is not str
                ):
                    raise TraceValidationError(
                        "stage 1 dimension-normalized selection semantics types drifted"
                    )
                if method.schema_version == GREEDY_ANCHORED_METHOD_SPEC_SCHEMA_VERSION:
                    if (
                        type(semantics.get("selection_phase")) is not str
                        or type(semantics.get("perturbation_point_usage")) is not str
                    ):
                        raise TraceValidationError(
                            "stage 1 greedy-anchor selection semantics types drifted"
                        )
            elif "selection_semantics" in payload:
                raise TraceValidationError(
                    "stage 1 legacy selection contains v2 semantics"
                )
            point_digest = payload.get("point_digest")
            trajectory_index = payload.get("trajectory_index")
            if type(trajectory_index) is not int or trajectory_index < 0:
                raise TraceValidationError("stage 1 selection trajectory index drifted")
            uses_perturbation = _selection_uses_perturbation(
                method,
                trajectory_index=trajectory_index,
            )
            if uses_perturbation:
                if point_digest not in point_digests:
                    raise TraceValidationError(
                        "stage 1 selection references unknown point material"
                    )
                if charge["delta"]["generated_perturbation_coordinates"] != len(scored):
                    raise TraceValidationError(
                        "stage 1 coordinate receipt does not close"
                    )
                if point_digest in referenced_point_digests:
                    raise TraceValidationError(
                        "stage 1 perturbation point was referenced more than once"
                    )
                referenced_point_digests.add(point_digest)
            elif (
                point_digest is not None
                or charge["delta"]["generated_perturbation_coordinates"] != 0
            ):
                raise TraceValidationError(
                    "stage 1 unperturbed selection references random material"
                )
        elif kind == "trajectory_backed_up":
            if event["charge"] is not None:
                raise TraceValidationError("stage 1 backup event must be uncharged")
            terminal_value = payload.get("terminal_value")
            if type(terminal_value) is not float or not math.isfinite(terminal_value):
                raise TraceValidationError(
                    "stage 1 backup terminal value is not a finite plain float"
                )
            if method.dense_terminal_value:
                if (
                    payload.get("terminal_value_rule_id")
                    != RECIPROCAL_ABSOLUTE_ERROR_TERMINAL_VALUE_RULE_ID
                    or type(payload.get("terminal_value_rule_id")) is not str
                ):
                    raise TraceValidationError(
                        "stage 1 dense terminal-value rule drifted"
                    )
                absolute_error = payload.get("terminal_absolute_error")
                numerator = payload.get("terminal_value_numerator")
                denominator = payload.get("terminal_value_denominator")
                floor_value = payload.get("terminal_value_floor")
                floor_applied = payload.get("terminal_value_floor_applied")
                unfloored_value = (
                    numerator / denominator
                    if type(numerator) is int
                    and type(denominator) is int
                    and denominator > 0
                    else None
                )
                if (
                    type(absolute_error) is not int
                    or absolute_error < 0
                    or type(numerator) is not int
                    or numerator != 1
                    or type(denominator) is not int
                    or denominator != 1 + absolute_error
                    or type(floor_value) is not float
                    or floor_value != MIN_POSITIVE_BINARY64
                    or type(floor_applied) is not bool
                    or floor_applied is not (unfloored_value == 0.0)
                    or terminal_value
                    != (floor_value if floor_applied else unfloored_value)
                ):
                    raise TraceValidationError(
                        "stage 1 dense terminal-value evidence drifted"
                    )
                if not 0.0 < terminal_value <= 1.0:
                    raise TraceValidationError(
                        "stage 1 dense terminal value is outside (0, 1]"
                    )
                if (terminal_value == 1.0) is not (absolute_error == 0):
                    raise TraceValidationError(
                        "stage 1 dense exact-success value drifted"
                    )
                if absolute_error > 0 and terminal_value > 0.5:
                    raise TraceValidationError(
                        "stage 1 dense failure value exceeds one half"
                    )
            elif any(
                key in payload
                for key in (
                    "terminal_absolute_error",
                    "terminal_value_denominator",
                    "terminal_value_floor",
                    "terminal_value_floor_applied",
                    "terminal_value_numerator",
                    "terminal_value_rule_id",
                )
            ):
                raise TraceValidationError(
                    "stage 1 binary backup contains dense terminal semantics"
                )
        elif kind == "beam_layer_selection_committed":
            if method.method != "beam":
                raise TraceValidationError(
                    "stage 1 non-beam method contains a beam selection"
                )
            if payload.get("event_schema_version") != SEARCH_EVENT_SCHEMA_VERSION:
                raise TraceValidationError(
                    "stage 1 beam selection event schema is unsupported"
                )
            charge = event["charge"]
            if charge is None:
                raise TraceValidationError("stage 1 beam selection lacks its receipt")
            parents = payload.get("scored_parents")
            selected = payload.get("selected")
            if type(parents) is not list or type(selected) is not list:
                raise TraceValidationError(
                    "stage 1 beam selection payload is malformed"
                )
            score_count = 0
            for parent in parents:
                if type(parent) is not dict:
                    raise TraceValidationError(
                        "stage 1 beam scored parent is malformed"
                    )
                indices = parent.get("scored_action_indices")
                if type(indices) is not list or indices != list(range(len(indices))):
                    raise TraceValidationError(
                        "stage 1 beam scored-action indices drifted"
                    )
                score_count += len(indices)
            delta = charge["delta"]
            if (
                delta["legal_action_scores"] != score_count
                or delta["generated_perturbation_coordinates"] != 0
                or delta["edge_selections"] != len(selected)
                or delta["transitions"] != len(selected)
            ):
                raise TraceValidationError(
                    "stage 1 beam selection receipt does not close"
                )

    if method.stochastic:
        if any(count < 1 for count in next_visits.values()):
            raise TraceValidationError("stage 1 materialized node has no point")
        if point_digests != referenced_point_digests:
            raise TraceValidationError(
                "stage 1 perturbation points and selections are not one-to-one"
            )
    elif nodes or point_count:
        raise TraceValidationError(
            "stage 1 deterministic run retained perturbation material"
        )
    return validated_material


def replay_countdown_track_a_search_bytes(
    payload: bytes,
    *,
    task: CountdownTask,
    proposal: TrackAProposalSpec,
    method: TrackAMethodSpec,
    budget_profile: TrackABudgetProfile,
    exploration_seed: int,
    expected_run_identity_digest: str,
) -> bytes:
    """Regenerate a search from empty state and require identical core bytes.

    Stage 1 regenerates proposal and perturbation material from sealed
    identities. Stage 2 supplies only those validated stored node/point values
    through the replay-source boundary; stored selections, transitions,
    verifier results, backups, and stop payloads never guide the rerun.
    """

    parsed = validate_trace_bytes(payload)
    if (
        not isinstance(expected_run_identity_digest, str)
        or len(expected_run_identity_digest) != 64
        or any(
            character not in "0123456789abcdef"
            for character in expected_run_identity_digest
        )
    ):
        raise ValueError("expected_run_identity_digest must be lowercase SHA-256")
    if sha256_json(parsed["run_identity"]) != expected_run_identity_digest:
        raise TraceValidationError("sealed search run identity digest mismatch")

    expected_identity = build_search_run_identity(
        task=task,
        proposal=proposal,
        method=method,
        budget_profile=budget_profile,
        exploration_seed=exploration_seed,
    )
    if expected_identity != parsed["run_identity"]:
        raise TraceValidationError("search replay inputs do not match run identity")
    validated_material = _validate_stage_one_material(
        parsed,
        task=task,
        proposal=proposal,
        method=method,
    )
    replayed = (
        _SearchSession(
            task=task,
            proposal=proposal,
            method=method,
            budget_profile=budget_profile,
            exploration_seed=exploration_seed,
            replay_material=validated_material,
        )
        .run()
        .canonical_bytes
    )
    if replayed != payload:
        raise TraceValidationError("stage 2 search replay was not byte-identical")
    return replayed
