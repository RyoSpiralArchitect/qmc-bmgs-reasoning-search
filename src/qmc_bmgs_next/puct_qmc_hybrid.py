"""One anchored binary-PUCT policy, with Sobol or IID bounded bonus variation.

Trajectory zero is fixed c1 PUCT and consumes no exploration material. Later
selections use Q_binary + U_PUCT * (0.5 + original_uniform). Only the uniform
source differs between the two hybrids. This is not posterior sampling,
Gumbel planning, semantic routing, or a guarantee of preserving later PUCT hits.
The existing material backend also generates/stores normals; they are unused
by this selector but their coordinate work and runtime cost are not erased.
"""

from dataclasses import dataclass
import math

from qmc_bmgs.substrate import countdown_search as core
from qmc_bmgs.substrate.perturbations import LazyNormalSource
from qmc_bmgs.substrate.trace import (
    HashChainedTrace,
    TraceValidationError,
    canonical_trace_bytes,
    sha256_json,
    strict_json_loads,
    validate_trace_bytes,
)
from qmc_bmgs_next import search_value as legacy


SCHEMA = "countdown_puct_qmc_hybrid_cell/v1"
SEARCH_SCHEMA = "countdown_puct_bounded_bonus_search/v1"
EVENT_SCHEMA = "countdown_puct_bounded_bonus_selection/v1"
RULE = "binary_puct_c1_first_trajectory_then_bonus_times_half_plus_uniform/v1"
METHODS = ("puct-qmc", "puct-iid", "puct")
PROPOSAL = legacy.PROPOSAL


def scores(log_prior, means, visits, uniforms=None):
    """Fixed c1 and half-width 0.5; None means the unperturbed anchor."""
    if not log_prior or not len(log_prior) == len(means) == len(visits):
        raise ValueError("nonempty matching PUCT components required")
    if any(type(x) is not float or not math.isfinite(x) for x in (*log_prior, *means)):
        raise ValueError("finite plain float prior/means required")
    if any(lp > 0.0 for lp in log_prior) or any(not 0.0 <= m <= 1.0 for m in means):
        raise ValueError("log probabilities and binary-return means required")
    if any(type(n) is not int or n < 0 for n in visits):
        raise ValueError("nonnegative plain visits required")
    if uniforms is not None and (
        len(uniforms) != len(means)
        or any(
            type(u) is not float or not math.isfinite(u) or not 0 < u < 1
            for u in uniforms
        )
    ):
        raise ValueError("matching finite open-unit uniforms required")
    scale = math.sqrt(1.0 + sum(visits))
    bonus = [1.0 * math.exp(lp) * scale / (1.0 + n) for lp, n in zip(log_prior, visits)]
    multipliers = (
        [1.0] * len(means) if uniforms is None else [0.5 + u for u in uniforms]
    )
    return [m + b * w for m, b, w in zip(means, bonus, multipliers)]


@dataclass(frozen=True)
class PuctQmcHybridSpec:
    method: str

    def __post_init__(self):
        if type(self.method) is not str or self.method not in METHODS:
            raise ValueError(f"method must be one of {METHODS!r}")

    @property
    def stochastic(self):
        return self.method != "puct"

    @property
    def source(self):
        return {"puct-qmc": "sobol", "puct-iid": "iid", "puct": "none"}[self.method]

    def transport(self):
        # v1 Thompson is used only for the existing material transaction and
        # binary terminal backup. Its score rule is never used by the hybrid.
        return core.TrackAMethodSpec.frozen_thompson(self.source)

    def method_payload(self):
        if not self.stochastic:
            return core.TrackAMethodSpec.puct().to_dict()
        return dict(
            schema_version="countdown_puct_bounded_bonus_method/v1",
            method_id=SEARCH_SCHEMA,
            selection_rule_id=RULE,
            selected_source=self.source,
            c_puct=1.0,
            multiplier_offset=0.5,
            multiplier_uniform_coefficient=1.0,
            first_fixed_puct_trajectory_count=1,
            anchor_material="not_generated_or_charged",
            terminal_value="exact_success_one_otherwise_zero",
            terminal_updates="unchanged_visits_arithmetic_mean_m2",
            m2_used_in_selection=False,
            base_engine_transport=self.transport().to_dict(),
            normal_material_generated_charged_but_unused=True,
        )

    def to_dict(self):
        return dict(
            schema_version="countdown_puct_qmc_hybrid_spec/v1",
            method=self.method,
            search_method=self.method_payload(),
        )


def _identity(spec, **kwargs):
    identity = core.build_search_run_identity(method=spec.transport(), **kwargs)
    identity["configuration_id"] = sha256_json(
        dict(
            base_configuration_id=identity["configuration_id"],
            method=spec.method_payload(),
            search_schema_version=SEARCH_SCHEMA,
        )
    )
    identity["method_id"] = SEARCH_SCHEMA
    return identity


def _semantics(trajectory_index):
    anchor = trajectory_index == 0
    return dict(
        selection_rule_id=RULE,
        selection_phase="fixed_puct_anchor" if anchor else "bounded_bonus_variation",
        perturbation_point_usage="not_generated" if anchor else "original_uniform",
        multiplier="one" if anchor else "0.5 + original_open_unit_uniform",
        binary_return_mean_unchanged=True,
        normal_material_used_in_selection=False,
        tie_break="lowest_canonical_action_index",
    )


class _HybridTrace(HashChainedTrace):
    def __init__(self, identity, spec):
        super().__init__(identity)
        self.spec = spec

    def append_batch(self, events, **kwargs):
        converted = []
        for kind, payload in events:
            if kind == "selection_committed":
                anchor = payload["trajectory_index"] == 0
                expected = (
                    core.TrackAMethodSpec.puct() if anchor else self.spec.transport()
                )
                if payload["method"] != expected.to_dict():
                    raise TraceValidationError("hybrid transaction transport drift")
                payload = dict(
                    payload,
                    event_schema_version=EVENT_SCHEMA,
                    method=self.spec.method_payload(),
                    selection_semantics=_semantics(payload["trajectory_index"]),
                )
            converted.append((kind, payload))
        return super().append_batch(tuple(converted), **kwargs)


class _HybridSession(core._SearchSession):
    def __init__(self, *, spec, **kwargs):
        if type(spec) is not PuctQmcHybridSpec or not spec.stochastic:
            raise ValueError("stochastic hybrid spec required")
        self.spec = spec
        super().__init__(method=spec.transport(), **kwargs)
        if self.trace.events or self.nodes or self.terminals:
            raise AssertionError("base constructor performed search")
        self.run_identity = _identity(
            spec,
            task=self.task,
            proposal=self.proposal,
            budget_profile=self.budget_profile,
            exploration_seed=self.exploration_seed,
        )
        self.trace = _HybridTrace(self.run_identity, spec)
        self._final_reservation = self.trace.reserve_event_slots(1)
        self.normal_source = LazyNormalSource(
            source=spec.source,
            exploration_seed=self.exploration_seed,
            trace=self.trace,
            tasks=(self.task,),
        )

    def _ordinary_step(self, path, *, trajectory_index):
        # Local, exception-safe transport switch: reuse the identical transaction
        # without planning/drawing/charging a point during trajectory zero. No
        # module/global monkeypatch, and binary backup remains v1 in both phases.
        saved = self.method
        if trajectory_index == 0:
            self.method = core.TrackAMethodSpec.puct()
        try:
            return super()._ordinary_step(path, trajectory_index=trajectory_index)
        finally:
            self.method = saved

    @staticmethod
    def _prepared_normals(prepared):
        # The inherited hook name is historical. Use original uniforms directly.
        return prepared.uniforms

    def _selection_values(self, node, normals, *, trajectory_index):
        if type(trajectory_index) is not int or trajectory_index < 0:
            raise ValueError("nonnegative plain trajectory index required")
        if (trajectory_index == 0) != (normals is None):
            raise ValueError("anchor/no-material and later/material phases required")
        return scores(
            node.row.prior_logp,
            [p.mean for p in node.posteriors],
            [p.visits for p in node.posteriors],
            normals,
        )

    def _summary(self):
        return dict(
            super()._summary(),
            method=self.spec.method_payload(),
            schema_version=SEARCH_SCHEMA,
        )


def _cell_inputs(task, spec, budget_profile, root_seed):
    if type(spec) is not PuctQmcHybridSpec:
        raise TypeError("spec must be exactly PuctQmcHybridSpec")
    if type(root_seed) is not int or root_seed < 0:
        raise ValueError("nonnegative plain root_seed required")
    if not spec.stochastic and root_seed != 0:
        raise ValueError("deterministic PUCT requires root_seed=0")
    kwargs = dict(
        task=task,
        proposal=PROPOSAL,
        budget_profile=budget_profile,
        exploration_seed=legacy.branch_seed(root_seed, 0) if spec.stochastic else 0,
    )
    inner = (
        _identity(spec, **kwargs)
        if spec.stochastic
        else core.build_search_run_identity(
            method=core.TrackAMethodSpec.puct(), **kwargs
        )
    )
    return dict(
        spec=spec.to_dict(),
        root_seed=root_seed,
        search_run_identity=inner,
        schema_version=SCHEMA,
        seed_derivation="feedback-diversity-stream/v1:branch0"
        if spec.stochastic
        else "none",
    ), kwargs


def _record(identity, result, task):
    record = legacy._record(identity, result, task)
    record["schema_version"] = SCHEMA
    record.pop("deterministic_digest")
    return dict(record, deterministic_digest=sha256_json(record))


def run_puct_qmc_hybrid_cell(task, *, spec, budget_profile, root_seed):
    identity, kwargs = _cell_inputs(task, spec, budget_profile, root_seed)
    result = (
        _HybridSession(spec=spec, **kwargs).run()
        if spec.stochastic
        else core.run_countdown_track_a_search(
            method=core.TrackAMethodSpec.puct(), **kwargs
        )
    )
    return legacy.SearchValueResult(_record(identity, result, task))


def replay_puct_qmc_hybrid_cell_bytes(
    payload, *, task, spec, budget_profile, root_seed, expected_run_identity_digest
):
    identity, kwargs = _cell_inputs(task, spec, budget_profile, root_seed)
    if expected_run_identity_digest != sha256_json(identity):
        raise TraceValidationError("sealed hybrid identity mismatch")
    parsed = strict_json_loads(payload)
    if type(parsed) is not dict or parsed.get("run_identity") != identity:
        raise TraceValidationError("hybrid inputs mismatch")
    inner = parsed.get("search_record")
    if type(inner) is not dict:
        raise TraceValidationError("inner trace required")
    raw = canonical_trace_bytes(inner)
    if validate_trace_bytes(raw)["run_identity"] != identity["search_run_identity"]:
        raise TraceValidationError("inner identity mismatch")
    # Regenerate from empty state, including every proposal and selected-source
    # point. Do not accept rehashed stored scores/material as proof of execution.
    result = (
        _HybridSession(spec=spec, **kwargs).run()
        if spec.stochastic
        else core.run_countdown_track_a_search(
            method=core.TrackAMethodSpec.puct(), **kwargs
        )
    )
    if result.canonical_bytes != raw:
        raise TraceValidationError("hybrid generative replay not byte-identical")
    expected = canonical_trace_bytes(_record(identity, result, task))
    if expected != payload:
        raise TraceValidationError("hybrid outer replay not byte-identical")
    return expected
