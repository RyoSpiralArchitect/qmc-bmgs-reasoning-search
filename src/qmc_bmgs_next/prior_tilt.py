"""One fixed prior-anchored return tilt, its mean-off control and frozen PUCT.

With ideal independent continuous uniforms, argmax(log p + mean + Gumbel)
samples p*exp(mean)/Z. Equal means recover p; no action-count or visit-dependent
noise rescaling is applied. Finite keyed uniforms/float arithmetic approximate
that identity, not a calibrated Bayesian posterior or a performance guarantee.

Reuse the frozen engine's transaction, proposals, terminal updates and material
authentication. Its stored normal draws remain generated/charged but unused:
the selected-action scores use Gumbels directly from their original uniforms.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from typing import Any, Sequence

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


SCHEMA = "countdown_prior_tilt_cell/v1"
SEARCH_SCHEMA = "countdown_prior_tilt_search/v1"
EVENT_SCHEMA = "countdown_prior_tilt_selection_event/v1"
RULE = "log_prior_plus_unit_terminal_mean_plus_unit_gumbel/v1"
METHODS = ("prior-tilt16", "prior-mean-off", "puct")
PROPOSAL = legacy.PROPOSAL


def gumbels(uniforms: Sequence[float]) -> tuple[float, ...]:
    if not uniforms or any(
        type(u) is not float or not math.isfinite(u) or not 0.0 < u < 1.0
        for u in uniforms
    ):
        raise ValueError("nonempty finite open-unit float uniforms required")
    return tuple(-math.log(-math.log(u)) for u in uniforms)


def scores(log_prior, means, noise, *, mean_on: bool):
    """Fixed unit coefficients; no tunable beta, variance, visits or temperature."""
    if type(mean_on) is not bool:
        raise ValueError("plain mean_on boolean required")
    if not log_prior or not len(log_prior) == len(means) == len(noise):
        raise ValueError("nonempty matching score dimensions required")
    if any(
        type(x) is not float or not math.isfinite(x)
        for vector in (log_prior, means, noise)
        for x in vector
    ):
        raise ValueError("finite float score components required")
    if any(not 0.0 <= m <= 1.0 for m in means):
        raise ValueError("scale16 mean must be bounded in [0,1]")
    return [
        lp + (m if mean_on else 0.0) + g for lp, m, g in zip(log_prior, means, noise)
    ]


@dataclass(frozen=True)
class PriorTiltSpec:
    method: str

    def __post_init__(self):
        if type(self.method) is not str or self.method not in METHODS:
            raise ValueError(f"method must be one of {METHODS!r}")

    @property
    def stochastic(self):
        return self.method != "puct"

    def method_payload(self):
        if not self.stochastic:
            return core.TrackAMethodSpec.puct().to_dict()
        return dict(
            schema_version="countdown_prior_tilt_method/v1",
            method_id=SEARCH_SCHEMA,
            method=self.method,
            selection_rule_id=RULE,
            selection_mean_coefficient=1.0 if self.method == METHODS[0] else 0.0,
            prior_logit_coefficient=1.0,
            gumbel_scale=1.0,
            terminal_value_scale=16,
            terminal_updates="unchanged_visits_mean_m2",
            visits_and_m2_used_in_selection=False,
            base_engine_transport=legacy._single16().to_dict(),
            normal_material_generated_charged_but_unused=True,
        )

    def to_dict(self):
        return dict(
            schema_version="countdown_prior_tilt_spec/v1",
            method=self.method,
            search_method=self.method_payload(),
        )


def _identity(spec, **kwargs):
    identity = core.build_search_run_identity(method=legacy._single16(), **kwargs)
    identity["configuration_id"] = sha256_json(
        dict(
            base_configuration_id=identity["configuration_id"],
            method=spec.method_payload(),
            search_schema_version=SEARCH_SCHEMA,
        )
    )
    identity["method_id"] = SEARCH_SCHEMA
    return identity


def _semantics(spec, count):
    return dict(
        selection_rule_id=RULE,
        action_count=count,
        selection_mean_coefficient=1.0 if spec.method == METHODS[0] else 0.0,
        prior_representation="log_probability",
        perturbation_transform="-log(-log(original_open_unit_uniform))",
        perturbation_scale=1.0,
        perturbation_visit_or_dimension_scaling=False,
        tie_break="lowest_canonical_action_index",
        normal_material_used_in_selection=False,
    )


class _TiltTrace(HashChainedTrace):
    def __init__(self, identity, spec):
        super().__init__(identity)
        self.spec = spec

    def append_batch(self, events: Sequence, **kwargs: Any):
        converted = []
        for kind, payload in events:
            if kind == "selection_committed":
                if payload["method"] != legacy._single16().to_dict():
                    raise TraceValidationError("prior-tilt transport drift")
                payload = {
                    **payload,
                    "event_schema_version": EVENT_SCHEMA,
                    "method": self.spec.method_payload(),
                    "selection_semantics": _semantics(
                        self.spec, len(payload["scored_action_indices"])
                    ),
                }
            converted.append((kind, payload))
        return super().append_batch(tuple(converted), **kwargs)


class _TiltSession(core._SearchSession):
    def __init__(self, *, spec, **kwargs):
        if type(spec) is not PriorTiltSpec or not spec.stochastic:
            raise ValueError("stochastic prior-tilt spec required")
        self.spec = spec
        super().__init__(method=legacy._single16(), **kwargs)
        if self.trace.events or self.nodes or self.terminals:
            raise AssertionError("base constructor performed search")
        self.run_identity = _identity(
            spec,
            task=self.task,
            proposal=self.proposal,
            budget_profile=self.budget_profile,
            exploration_seed=self.exploration_seed,
        )
        self.trace = _TiltTrace(self.run_identity, spec)
        self._final_reservation = self.trace.reserve_event_slots(1)
        self.normal_source = LazyNormalSource(
            source="iid",
            exploration_seed=self.exploration_seed,
            trace=self.trace,
            tasks=(self.task,),
        )

    @staticmethod
    def _prepared_normals(prepared):
        # Narrow frozen-engine hook: the legacy argument is named normals, but
        # this policy receives Gumbels computed from ORIGINAL uniforms, never
        # reconstructed/clipped through a normal CDF. Stored material is unchanged.
        return gumbels(prepared.uniforms)

    def _selection_values(self, node, normals, *, trajectory_index):
        if type(trajectory_index) is not int or trajectory_index < 0:
            raise ValueError("nonnegative plain trajectory index required")
        if normals is None:
            raise ValueError("Gumbel selection material required")
        return scores(
            node.row.prior_logp,
            [p.mean for p in node.posteriors],
            normals,
            mean_on=self.spec.method == METHODS[0],
        )

    def _summary(self):
        return {
            **super()._summary(),
            "method": self.spec.method_payload(),
            "schema_version": SEARCH_SCHEMA,
        }


def _replay_tilt(payload, *, spec, **kwargs):
    parsed = validate_trace_bytes(payload)
    if parsed["run_identity"] != _identity(spec, **kwargs):
        raise TraceValidationError("prior-tilt replay identity mismatch")
    material_view = copy.deepcopy(parsed)
    for e in material_view["events"]:
        if e["kind"] != "selection_committed":
            continue
        p = e["payload"]
        count = len(p["scored_action_indices"])
        if (
            p.get("event_schema_version") != EVENT_SCHEMA
            or p.get("method") != spec.method_payload()
            or p.get("selection_semantics") != _semantics(spec, count)
        ):
            raise TraceValidationError("prior-tilt selection metadata drift")
        p["event_schema_version"] = core.SEARCH_EVENT_SCHEMA_VERSION
        p["method"] = legacy._single16().to_dict()
        p["selection_semantics"] = core._dimension_normalized_selection_semantics(
            legacy._single16(),
            action_count=count,
            trajectory_index=p["trajectory_index"],
        )
    # Stage one checks only unchanged proposals/keyed uniform+normal material,
    # charges and terminal-linked backups. It does not approve the new scores.
    material = core._validate_stage_one_material(
        material_view,
        task=kwargs["task"],
        proposal=kwargs["proposal"],
        method=legacy._single16(),
    )
    result = _TiltSession(spec=spec, **kwargs, replay_material=material).run()
    if result.canonical_bytes != payload:
        raise TraceValidationError("prior-tilt generative replay not byte-identical")


def _cell_inputs(task, spec, budget_profile, root_seed):
    if type(spec) is not PriorTiltSpec:
        raise TypeError("spec must be exactly PriorTiltSpec")
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
    identity = dict(
        spec=spec.to_dict(),
        root_seed=root_seed,
        search_run_identity=inner,
        schema_version=SCHEMA,
        seed_derivation="feedback-diversity-stream/v1:branch0"
        if spec.stochastic
        else "none",
    )
    return identity, kwargs


def _record(identity, result, task):
    record = legacy._record(identity, result, task)
    record["schema_version"] = SCHEMA
    record.pop("deterministic_digest")
    return {**record, "deterministic_digest": sha256_json(record)}


def run_prior_tilt_cell(task, *, spec, budget_profile, root_seed):
    identity, kwargs = _cell_inputs(task, spec, budget_profile, root_seed)
    result = (
        _TiltSession(spec=spec, **kwargs).run()
        if spec.stochastic
        else (
            core.run_countdown_track_a_search(
                method=core.TrackAMethodSpec.puct(), **kwargs
            )
        )
    )
    return legacy.SearchValueResult(_record(identity, result, task))


def replay_prior_tilt_cell_bytes(
    payload, *, task, spec, budget_profile, root_seed, expected_run_identity_digest
):
    identity, kwargs = _cell_inputs(task, spec, budget_profile, root_seed)
    if expected_run_identity_digest != sha256_json(identity):
        raise TraceValidationError("sealed prior-tilt identity mismatch")
    parsed = strict_json_loads(payload)
    if type(parsed) is not dict or parsed.get("run_identity") != identity:
        raise TraceValidationError("prior-tilt inputs mismatch")
    inner = parsed.get("search_record")
    if type(inner) is not dict:
        raise TraceValidationError("inner trace required")
    raw = canonical_trace_bytes(inner)
    if spec.stochastic:
        _replay_tilt(raw, spec=spec, **kwargs)
    else:
        core.replay_countdown_track_a_search_bytes(
            raw,
            method=core.TrackAMethodSpec.puct(),
            expected_run_identity_digest=sha256_json(identity["search_run_identity"]),
            **kwargs,
        )
    result = core.TrackASearchResult(
        record=inner,
        summary=inner["events"][-1]["payload"]["summary"],
        run_identity_digest=sha256_json(identity["search_run_identity"]),
    )
    expected = canonical_trace_bytes(_record(identity, result, task))
    if expected != payload:
        raise TraceValidationError("prior-tilt outer replay not byte-identical")
    return expected
