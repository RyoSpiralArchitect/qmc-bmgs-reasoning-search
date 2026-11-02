"""Fixed PUCT traversal with either binary or scale16 terminal return.

Only the candidate's backed-up scalar changes. The original PUCT selector,
proposal, canonical ties, visits, arithmetic-mean backup, budget and stopping
rules are reused without modification. Neither method generates random draws.
The baseline delegates directly to the frozen engine, preserving inner bytes.
"""

from dataclasses import dataclass

from qmc_bmgs.substrate import countdown_search as core
from qmc_bmgs.substrate.budget import TRACK_A_WORK_AXES, TrackABudgetExceeded
from qmc_bmgs.substrate.trace import (
    HashChainedTrace,
    TraceValidationError,
    canonical_trace_bytes,
    sha256_json,
    strict_json_loads,
    validate_trace_bytes,
)
from qmc_bmgs_next import search_value as legacy


SCHEMA = "countdown_puct_return_cell/v1"
SEARCH_SCHEMA = "countdown_puct_dense16_search/v1"
EVENT_SCHEMA = "countdown_puct_dense16_selection/v1"
METHODS = ("puct-dense16", "puct")
PROPOSAL = legacy.PROPOSAL


@dataclass(frozen=True)
class PuctReturnSpec:
    method: str

    def __post_init__(self):
        if type(self.method) is not str or self.method not in METHODS:
            raise ValueError(f"method must be one of {METHODS!r}")

    def method_payload(self):
        base = core.TrackAMethodSpec.puct().to_dict()
        if self.method == "puct":
            return base
        return dict(
            schema_version="countdown_puct_dense16_method/v1",
            method_id=SEARCH_SCHEMA,
            selection_rule="unchanged_puct_c1_sqrt_one_plus_total_visits/v1",
            terminal_value_rule_id=core.SCALED_RECIPROCAL_ABSOLUTE_ERROR_TERMINAL_VALUE_RULE_ID,
            terminal_value_scale=16,
            terminal_updates="unchanged_visits_arithmetic_mean_m2",
            base_engine_transport=base,
            selected_source="none",
        )

    def to_dict(self):
        return dict(
            schema_version="countdown_puct_return_spec/v1",
            method=self.method,
            search_method=self.method_payload(),
        )


def _identity(**kwargs):
    identity = core.build_search_run_identity(
        method=core.TrackAMethodSpec.puct(), **kwargs
    )
    identity["configuration_id"] = sha256_json(
        dict(
            base_configuration_id=identity["configuration_id"],
            method=PuctReturnSpec(METHODS[0]).method_payload(),
            search_schema_version=SEARCH_SCHEMA,
        )
    )
    identity["method_id"] = SEARCH_SCHEMA
    return identity


class _DenseTrace(HashChainedTrace):
    def append_batch(self, events, **kwargs):
        converted = []
        for kind, payload in events:
            if kind == "selection_committed":
                if payload["method"] != core.TrackAMethodSpec.puct().to_dict():
                    raise TraceValidationError("PUCT transport drift")
                payload = dict(
                    payload,
                    event_schema_version=EVENT_SCHEMA,
                    method=PuctReturnSpec(METHODS[0]).method_payload(),
                )
            converted.append((kind, payload))
        return super().append_batch(tuple(converted), **kwargs)


class _DenseSession(core._SearchSession):
    def __init__(self, **kwargs):
        super().__init__(method=core.TrackAMethodSpec.puct(), **kwargs)
        if self.trace.events or self.nodes or self.terminals or self.normal_source:
            raise AssertionError("base constructor performed search or created RNG")
        self.run_identity = _identity(
            task=self.task,
            proposal=self.proposal,
            budget_profile=self.budget_profile,
            exploration_seed=self.exploration_seed,
        )
        self.trace = _DenseTrace(self.run_identity)
        self._final_reservation = self.trace.reserve_event_slots(1)

    def _verify_terminal(self, path, *, trajectory_index, backup):
        # Same transaction as the frozen engine: reserve, charge, verify once,
        # preview, atomically append, then commit updates and retain the terminal.
        # A local adapter avoids changing historical core method identities.
        increments = {axis: 0 for axis in TRACK_A_WORK_AXES}
        increments["verifier_calls"] = 1
        if not self._preflight(increments):
            return False
        reservation = self.trace.reserve_event_slots(2 if backup else 1)
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
            index = len(self.terminals)
            terminal = core._event_payload(
                dict(
                    actions=[action.to_dict() for action in path.actions],
                    cumulative_prior_logp=path.cumulative_prior_logp,
                    observation_index=index,
                    states=[list(state) for state in path.states],
                    trajectory_index=trajectory_index,
                    verification=verification.to_dict(),
                )
            )
            events = [("terminal_verified", terminal)]
            updates = []
            if backup:
                evidence = core._scaled_dense_terminal_value_evidence(verification, 16)
                updates = self._preview_backup(path, evidence["terminal_value"])
                events.append(
                    (
                        "trajectory_backed_up",
                        core._event_payload(
                            dict(
                                discount=1.0,
                                order="leaf_to_root",
                                trajectory_index=trajectory_index,
                                updates=updates,
                                terminal_value_rule_id=core.SCALED_RECIPROCAL_ABSOLUTE_ERROR_TERMINAL_VALUE_RULE_ID,
                                **evidence,
                            )
                        ),
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
                core._TerminalObservation(
                    observation_index=index,
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

    def _summary(self):
        return dict(
            super()._summary(),
            method=PuctReturnSpec(METHODS[0]).method_payload(),
            schema_version=SEARCH_SCHEMA,
        )


def _cell_inputs(task, spec, budget_profile, root_seed):
    if type(spec) is not PuctReturnSpec:
        raise TypeError("spec must be exactly PuctReturnSpec")
    if type(root_seed) is not int or root_seed != 0:
        raise ValueError("deterministic methods require plain root_seed=0")
    kwargs = dict(
        task=task, proposal=PROPOSAL, budget_profile=budget_profile, exploration_seed=0
    )
    inner = (
        _identity(**kwargs)
        if spec.method == METHODS[0]
        else core.build_search_run_identity(
            method=core.TrackAMethodSpec.puct(), **kwargs
        )
    )
    return dict(
        spec=spec.to_dict(),
        root_seed=0,
        search_run_identity=inner,
        schema_version=SCHEMA,
        seed_derivation="none",
    ), kwargs


def _record(identity, result, task):
    record = legacy._record(identity, result, task)
    record["schema_version"] = SCHEMA
    record.pop("deterministic_digest")
    return dict(record, deterministic_digest=sha256_json(record))


def run_puct_return_cell(task, *, spec, budget_profile, root_seed=0):
    identity, kwargs = _cell_inputs(task, spec, budget_profile, root_seed)
    result = (
        _DenseSession(**kwargs).run()
        if spec.method == METHODS[0]
        else core.run_countdown_track_a_search(
            method=core.TrackAMethodSpec.puct(), **kwargs
        )
    )
    return legacy.SearchValueResult(_record(identity, result, task))


def replay_puct_return_cell_bytes(
    payload, *, task, spec, budget_profile, root_seed, expected_run_identity_digest
):
    identity, kwargs = _cell_inputs(task, spec, budget_profile, root_seed)
    if expected_run_identity_digest != sha256_json(identity):
        raise TraceValidationError("sealed PUCT-return identity mismatch")
    parsed = strict_json_loads(payload)
    if type(parsed) is not dict or parsed.get("run_identity") != identity:
        raise TraceValidationError("PUCT-return inputs mismatch")
    inner = parsed.get("search_record")
    if type(inner) is not dict:
        raise TraceValidationError("inner trace required")
    raw = canonical_trace_bytes(inner)
    checked = validate_trace_bytes(raw)
    if checked["run_identity"] != identity["search_run_identity"]:
        raise TraceValidationError("inner identity mismatch")
    if spec.method == METHODS[0]:
        # No random/external material is consumed. Regenerate proposals, every
        # choice, verification, dense backup and ledger from the supplied task.
        result = _DenseSession(**kwargs).run()
        if result.canonical_bytes != raw:
            raise TraceValidationError(
                "dense PUCT generative replay not byte-identical"
            )
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
        raise TraceValidationError("PUCT-return outer replay not byte-identical")
    return expected
