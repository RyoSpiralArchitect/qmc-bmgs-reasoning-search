"""Additive, single-cell kernel for the search-value development design.

No cohort, experiment runner, outcome-dependent policy, or execution authority
is provided here. Four controls delegate byte-for-byte to the frozen engine.
The fifth removes only the learned mean from selection, with a distinct trace
identity. Original proposal, budget, backup and perturbation code is unchanged.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from qmc_bmgs.benchmarks.countdown import CountdownTask
from qmc_bmgs.substrate import countdown_search as core
from qmc_bmgs.substrate.budget import TRACK_A_WORK_AXES
from qmc_bmgs.substrate.perturbations import LazyNormalSource
from qmc_bmgs.substrate.proposals import TrackAProposalSpec
from qmc_bmgs.substrate.trace import (
    HashChainedTrace,
    TraceValidationError,
    canonical_trace_bytes,
    sha256_json,
    strict_json_loads,
    validate_trace_bytes,
)
from qmc_bmgs_next.diversity_search import branch_seed


SCHEMA = "countdown_search_value_cell/v1"
MEAN_OFF_SCHEMA = "countdown_selection_mean_off_search/v1"
MEAN_OFF_EVENT = "countdown_selection_mean_off_event/v1"
MEAN_OFF_RULE = "zero_mean_probability_prior_sqrt_2_ln_action_noise/v1"
METHODS = ("single16", "selection-mean-off", "greedy", "beam2", "puct")
PROPOSAL = TrackAProposalSpec("greedy_rollout_target_error/v1")


def _single16() -> core.TrackAMethodSpec:
    return core.TrackAMethodSpec.dimension_normalized_scaled_dense_thompson("iid", 16)


def _mean_off_payload() -> dict[str, Any]:
    return {
        "base_method": _single16().to_dict(),
        "method_id": MEAN_OFF_SCHEMA,
        "schema_version": "countdown_selection_mean_off_method/v1",
        "selection_mean_coefficient": 0.0,
        "selection_rule_id": MEAN_OFF_RULE,
        "terminal_updates": "unchanged_visits_mean_m2",
    }


@dataclass(frozen=True)
class SearchValueSpec:
    method: str

    def __post_init__(self) -> None:
        if type(self.method) is not str or self.method not in METHODS:
            raise ValueError(f"method must be one of {METHODS!r}")

    @property
    def stochastic(self) -> bool:
        return self.method in {"single16", "selection-mean-off"}

    def base_method(self) -> core.TrackAMethodSpec:
        if self.stochastic:
            return _single16()
        return {
            "greedy": core.TrackAMethodSpec.greedy,
            "beam2": core.TrackAMethodSpec.beam_width_two,
            "puct": core.TrackAMethodSpec.puct,
        }[self.method]()

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "search_method": (
                _mean_off_payload()
                if self.method == "selection-mean-off"
                else self.base_method().to_dict()
            ),
            "schema_version": "countdown_search_value_spec/v1",
        }


def _mean_off_identity(**kwargs: Any) -> dict[str, Any]:
    identity = core.build_search_run_identity(method=_single16(), **kwargs)
    identity["configuration_id"] = sha256_json(
        {
            "base_configuration_id": identity["configuration_id"],
            "method": _mean_off_payload(),
            "search_schema_version": MEAN_OFF_SCHEMA,
        }
    )
    identity["method_id"] = MEAN_OFF_SCHEMA
    return identity


def _mean_off_semantics(base: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **base,
        "selection_rule_id": MEAN_OFF_RULE,
        "selection_mean_coefficient": 0.0,
    }


class _MeanOffTrace(HashChainedTrace):
    """Stamp the actual method before hashing/committing selection events.

    This adapter changes metadata only, not charges, choices, reservations or
    transaction ordering. All other event kinds retain their original schemas.
    """

    def append_batch(self, events: Sequence, **kwargs: Any) -> tuple:
        converted = []
        for kind, payload in events:
            if kind == "selection_committed":
                if payload["method"] != _single16().to_dict():
                    raise TraceValidationError("mean-off base method drifted")
                payload = {
                    **payload,
                    "event_schema_version": MEAN_OFF_EVENT,
                    "method": _mean_off_payload(),
                    "selection_semantics": _mean_off_semantics(
                        payload["selection_semantics"]
                    ),
                }
            converted.append((kind, payload))
        return super().append_batch(tuple(converted), **kwargs)


class _MeanOffSession(core._SearchSession):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(method=_single16(), **kwargs)
        # The base constructor performs validation but no search/materialization.
        # Replace the empty writer/source, never relabel an already-produced run.
        if self.trace.events or self.nodes or self.terminals:
            raise AssertionError("base constructor unexpectedly performed search")
        self.run_identity = _mean_off_identity(
            task=self.task,
            proposal=self.proposal,
            budget_profile=self.budget_profile,
            exploration_seed=self.exploration_seed,
        )
        self.trace = _MeanOffTrace(self.run_identity)
        self._final_reservation = self.trace.reserve_event_slots(1)
        self.normal_source = LazyNormalSource(
            source="iid",
            exploration_seed=self.exploration_seed,
            trace=self.trace,
            tasks=(self.task,),
        )

    def _selection_values(
        self, node: Any, normals: Sequence[float] | None, *, trajectory_index: int
    ) -> list[float]:
        if type(trajectory_index) is not int or trajectory_index < 0:
            raise ValueError("trajectory_index must be a non-negative plain integer")
        if normals is None or len(normals) != len(node.row.actions):
            raise AssertionError("mean-off perturbation dimension drifted")
        normalizer = core._action_dimension_noise_normalizer(len(node.row.actions))
        # Keep the original operation order. Subtracting mean from a rounded
        # full score would not be the intervention 0 + prior + perturbation.
        return [
            0.0
            + self.method.prior_bonus * math.exp(logp)
            + self.method.posterior_sd_scale
            / (normalizer * math.sqrt(item.visits + 1.0))
            * normal
            for item, logp, normal in zip(node.posteriors, node.row.prior_logp, normals)
        ]

    def _summary(self) -> dict[str, Any]:
        return {
            **super()._summary(),
            "method": _mean_off_payload(),
            "schema_version": MEAN_OFF_SCHEMA,
        }


def _replay_mean_off(payload: bytes, **kwargs: Any) -> bytes:
    parsed = validate_trace_bytes(payload)
    if parsed["run_identity"] != _mean_off_identity(**kwargs):
        raise TraceValidationError("mean-off replay identity mismatch")
    # Stage 1 authenticates unchanged proposals, keyed normal material, charges
    # and terminal-linked backups. A strictly checked metadata-only projection
    # lets the frozen validator do that work. It does NOT validate selection.
    # Stage 2 below reruns the new policy from empty state and checks all bytes.
    material_view = copy.deepcopy(parsed)
    for event in material_view["events"]:
        if event["kind"] != "selection_committed":
            continue
        p = event["payload"]
        base = core._dimension_normalized_selection_semantics(
            _single16(),
            action_count=len(p["scored_action_indices"]),
            trajectory_index=p["trajectory_index"],
        )
        if (
            p.get("event_schema_version") != MEAN_OFF_EVENT
            or p.get("method") != _mean_off_payload()
            or p.get("selection_semantics") != _mean_off_semantics(base)
        ):
            raise TraceValidationError("mean-off selection metadata drifted")
        p["event_schema_version"] = core.SEARCH_EVENT_SCHEMA_VERSION
        p["method"] = _single16().to_dict()
        p["selection_semantics"] = base
    material = core._validate_stage_one_material(
        material_view,
        task=kwargs["task"],
        proposal=kwargs["proposal"],
        method=_single16(),
    )
    replayed = _MeanOffSession(**kwargs, replay_material=material).run().canonical_bytes
    if replayed != payload:
        raise TraceValidationError("mean-off stage 2 replay was not byte-identical")
    return replayed


def _cell_inputs(
    task: CountdownTask,
    spec: SearchValueSpec,
    budget_profile: core.TrackABudgetProfile,
    root_seed: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if type(spec) is not SearchValueSpec:
        raise TypeError("spec must be exactly SearchValueSpec")
    if type(root_seed) is not int or root_seed < 0:
        raise ValueError("root_seed must be a non-negative plain integer")
    if not spec.stochastic and root_seed != 0:
        raise ValueError(
            "deterministic methods require root_seed=0; no duplicate seeds"
        )
    kwargs = dict(
        task=task,
        proposal=PROPOSAL,
        budget_profile=budget_profile,
        exploration_seed=branch_seed(root_seed, 0) if spec.stochastic else 0,
    )
    inner = (
        _mean_off_identity(**kwargs)
        if spec.method == "selection-mean-off"
        else core.build_search_run_identity(method=spec.base_method(), **kwargs)
    )
    identity = {
        "spec": spec.to_dict(),
        "root_seed": root_seed,
        "search_run_identity": inner,
        "schema_version": SCHEMA,
        "seed_derivation": "feedback-diversity-stream/v1:branch0"
        if spec.stochastic
        else "none",
    }
    return identity, kwargs


def _proposal_work(task: CountdownTask, record: Mapping[str, Any]) -> dict[str, Any]:
    """Reconstruct hidden proposal work, without charging or guiding the search.

    Counts apply to materialized cache misses only, including repetitions across
    cells. This re-enumeration is audit overhead, not live instrumentation or a
    wall-clock performance measurement. Terminal ranking is the frozen v1 rule.
    """
    transition_count = completion_actions = materializations = root_actions = 0
    for event in record["events"]:
        if event["kind"] != "proposal_materialized":
            continue
        row = event["payload"]["proposal"]
        if row["policy_spec"] != PROPOSAL.to_dict():
            raise TraceValidationError("proposal-work audit requires frozen heuristic")
        state = tuple(row["state"])
        actions = task.legal_actions(state)
        if [a.to_dict() for a in actions] != row["action_order"]:
            raise TraceValidationError("proposal-work action order drifted")
        transitions = 0
        for action in actions:
            current = task.transition(state, action)
            transitions += 1
            while len(current) > 1:
                candidates = task.legal_actions(current)
                if not candidates:
                    break
                completion_actions += len(candidates)
                selected = min(
                    range(len(candidates)),
                    key=lambda i: (abs(candidates[i].evaluate() - task.target), i),
                )
                current = task.transition(current, candidates[selected])
                transitions += 1
        if transitions != row["internal_transition_evaluations"]:
            raise TraceValidationError("proposal-work transition count drifted")
        transition_count += transitions
        root_actions += len(actions)
        materializations += 1
    return {
        "schema_version": "greedy_rollout_proposal_work_reconstruction/v1",
        "measurement": "reconstructed_from_materialized_rows_not_live_instrumentation",
        "materialized_rows": materializations,
        "root_action_evaluations": root_actions,
        "completion_legal_action_evaluations": completion_actions,
        "internal_transition_evaluations": transition_count,
        "internal_work_charged_to_seven_axis_ledger": False,
        "root_action_count_duplicates_proposal_action_scores": True,
        "audit_overhead_is_search_work": False,
    }


def _record(
    identity: dict[str, Any],
    result: core.TrackASearchResult,
    task: CountdownTask,
) -> dict[str, Any]:
    usage = {axis: 0 for axis in TRACK_A_WORK_AXES}
    first = None
    errors = []
    for event in result.record["events"]:
        if event["charge"] is not None:
            for axis in usage:
                usage[axis] += event["charge"]["delta"][axis]
        if event["kind"] == "terminal_verified":
            verification = event["payload"]["verification"]
            errors.append(abs(verification["final_value"] - task.target))
            if first is None and verification["success"]:
                first = dict(usage)
    if usage != result.summary["ledger_usage"]:
        raise TraceValidationError("search-value event charges do not close")
    proposal_work = _proposal_work(task, result.record)
    if (
        proposal_work["materialized_rows"] != usage["proposal_state_evaluations"]
        or proposal_work["root_action_evaluations"] != usage["proposal_action_scores"]
    ):
        raise TraceValidationError("proposal-work cache-miss ledger does not close")
    limits = identity["search_run_identity"]["work_limits"]
    record = {
        "schema_version": SCHEMA,
        "run_identity": identity,
        "run_identity_digest": sha256_json(identity),
        "search_record": result.record,
        "summary": {
            "search_summary": result.summary,
            "actual_work": usage,
            "unspent_work": {axis: limits[axis] - usage[axis] for axis in usage},
            "proposal_work": proposal_work,
            "minimum_terminal_error": min(errors) if errors else None,
            "missing_terminal": not errors,
            "first_exact_work": first,
            "no_exact_observation_censored_at_work": dict(usage)
            if first is None
            else None,
            "winner": None,
            "scientific_decision": None,
        },
    }
    return {**record, "deterministic_digest": sha256_json(record)}


@dataclass(frozen=True)
class SearchValueResult:
    record: dict[str, Any]

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_trace_bytes(self.record)

    @property
    def summary(self) -> dict[str, Any]:
        return copy.deepcopy(self.record["summary"])


def run_search_value_cell(
    task: CountdownTask,
    *,
    spec: SearchValueSpec,
    budget_profile: core.TrackABudgetProfile,
    root_seed: int,
) -> SearchValueResult:
    """Execute one isolated cell; callers own separate study authorization."""
    identity, kwargs = _cell_inputs(task, spec, budget_profile, root_seed)
    result = (
        _MeanOffSession(**kwargs).run()
        if spec.method == "selection-mean-off"
        else core.run_countdown_track_a_search(method=spec.base_method(), **kwargs)
    )
    return SearchValueResult(_record(identity, result, task))


def replay_search_value_cell_bytes(
    payload: bytes,
    *,
    task: CountdownTask,
    spec: SearchValueSpec,
    budget_profile: core.TrackABudgetProfile,
    root_seed: int,
    expected_run_identity_digest: str,
) -> bytes:
    """Authenticate material then rerun the declared policy; trust no decisions."""
    identity, kwargs = _cell_inputs(task, spec, budget_profile, root_seed)
    if expected_run_identity_digest != sha256_json(identity):
        raise TraceValidationError("sealed search-value identity mismatch")
    parsed = strict_json_loads(payload)
    if type(parsed) is not dict or parsed.get("run_identity") != identity:
        raise TraceValidationError("search-value replay inputs do not match identity")
    core_record = parsed.get("search_record")
    if type(core_record) is not dict:
        raise TraceValidationError("search-value search_record is not an object")
    core_bytes = canonical_trace_bytes(core_record)
    if spec.method == "selection-mean-off":
        _replay_mean_off(core_bytes, **kwargs)
    else:
        core.replay_countdown_track_a_search_bytes(
            core_bytes,
            method=spec.base_method(),
            expected_run_identity_digest=sha256_json(identity["search_run_identity"]),
            **kwargs,
        )
    result = core.TrackASearchResult(
        record=core_record,
        summary=core_record["events"][-1]["payload"]["summary"],
        run_identity_digest=sha256_json(identity["search_run_identity"]),
    )
    expected = canonical_trace_bytes(_record(identity, result, task))
    if expected != payload:
        raise TraceValidationError("search-value replay was not byte-identical")
    return expected
