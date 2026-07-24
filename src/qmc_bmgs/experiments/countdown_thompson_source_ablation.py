#!/usr/bin/env python3
"""Offline matched IID-versus-Sobol Thompson comparison for Countdown.

The two frozen provider proposal snapshots are treated as immutable inputs.
This module introduces a *new* matched Thompson pair because the historical
``iid_thompson_8`` record uses a global SHA-counter Box--Muller stream.  Both
conditions here instead read the same precomputed node-local perturbation bank,
use the same clipped inverse-normal transform, and differ only in whether the
selected coordinates came from IID uniforms or randomized Sobol uniforms.

No provider client, credential, or network call is used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import shutil
import socket
import statistics
import tempfile
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import torch
from torch.quasirandom import SobolEngine

from qmc_bmgs.benchmarks.countdown import (
    CountdownAction,
    CountdownState,
    CountdownTask,
)
from qmc_bmgs.experiments.countdown_anthropic_dev import (
    DEV_TASKS,
    SEARCH_BUDGET,
    THOMPSON_PRIOR_BONUS,
    THOMPSON_SIMULATIONS,
    ProposalRow,
    ProposalSnapshot,
    SearchContext,
    SearchStopped,
    _NodeStats,
    _canonical_json,
    _nonterminal_states,
    _normalization,
    _sha256_json,
    _state_sort_key,
    _validate_search_record,
    load_snapshot,
    validate_artifact as validate_anthropic_artifact,
)
from qmc_bmgs.experiments.countdown_openai_dev import (
    validate_artifact as validate_openai_artifact,
)
from qmc_bmgs.records import canonical_record_digest


RECORD_SCHEMA_VERSION = "qmc-bmgs-countdown-thompson-source-record/v1"
BANK_SCHEMA_VERSION = "qmc-bmgs-countdown-perturbation-bank/v1"
SUMMARY_SCHEMA_VERSION = "qmc-bmgs-countdown-thompson-source-summary/v1"
MANIFEST_SCHEMA_VERSION = "qmc-bmgs-countdown-thompson-source-manifest/v1"
SEED_PLAN_VERSION = "sha256-uint32-linear-probe/v1"
NORMAL_TRANSFORM_VERSION = "clipped-torch-erfinv-float64/v1"
EXPERIMENT_VERSION = "countdown-matched-thompson-source/v1"

METHODS = ("matched_iid_thompson_8", "qmc_thompson_8")
METHOD_SOURCE = {
    "matched_iid_thompson_8": "iid",
    "qmc_thompson_8": "sobol",
}
SOURCE_NAMES = ("iid", "sobol")
SEED_START = 1024
SEED_COUNT = 128
EXPLORATION_SEEDS = tuple(range(SEED_START, SEED_START + SEED_COUNT))
MAX_ACTIONS = 14
ICDF_CLIP = 2.0**-53
NO_HIT_SENTINEL = THOMPSON_SIMULATIONS + 1

FROZEN_SOURCES = {
    "anthropic": {
        "behavior_digest": (
            "9eaee49f6e100d26100b10b0eb8d9f9ba75f74cb0109d2b25634590117682868"
        ),
        "manifest_sha256": (
            "843b2437000818e225315029e3e9f08cb7325c765406e8505a34fa6dd46c7005"
        ),
        "proposal_sha256": (
            "cbeba18fb46c7b5a9fdc7317dd29e82bd13ceeb286ee7aaaf47574e2ef55ae46"
        ),
        "summary_digest": (
            "2a8974326d436bcc53ebb47c73232d99784046d44a16ba9b1f906a1447bae379"
        ),
    },
    "openai": {
        "behavior_digest": (
            "529b7dd51458cda3a6899a7b0b406dd8880317b413f39fe0fc08786c4eff8862"
        ),
        "manifest_sha256": (
            "f69f1a04065a93da495c97a191f38fe7d4a67a603ed58dfbe3930f1adedc8e51"
        ),
        "proposal_sha256": (
            "57a9e5a1a07340739f88288ee4b12af0d8550e2683667de447c2febcbc131e13"
        ),
        "summary_digest": (
            "11a3ed0b4313ea7b73a2d6987d9400c13081c918ec5a1982822c5241ed12e73d"
        ),
    },
}


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _file_metadata(path: Path, *, records: int | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "bytes": path.stat().st_size,
        "sha256": _file_sha256(path),
    }
    if records is not None:
        result["records"] = records
    return result


def _strict_json_text(text: str) -> Any:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant: {value}")

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key!r}")
            result[key] = value
        return result

    return json.loads(
        text,
        object_pairs_hook=reject_duplicate_keys,
        parse_constant=reject_constant,
    )


def _read_json(path: Path) -> dict[str, Any]:
    payload = _strict_json_text(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return payload


def _read_jsonl(path: Path) -> tuple[dict[str, Any], ...]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line:
            continue
        record = _strict_json_text(line)
        if not isinstance(record, dict):
            raise ValueError(f"{path.name}:{line_number} is not a JSON object")
        records.append(record)
    return tuple(records)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                payload,
                sort_keys=True,
                indent=2,
                ensure_ascii=True,
                allow_nan=False,
            )
            + "\n"
        )
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> int:
    temporary = path.with_name(f".{path.name}.tmp")
    count = 0
    with temporary.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(_canonical_json(record) + "\n")
            count += 1
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    return count


def _action_digest(actions: Sequence[CountdownAction]) -> str:
    return _sha256_json([action.to_dict() for action in actions])


def _task_from_dict(payload: Mapping[str, Any]) -> CountdownTask:
    task = CountdownTask(tuple(payload["inputs"]), payload["target"])
    if task.to_dict() != payload:
        raise ValueError("serialized task is not canonical")
    return task


def _source_seed_identity(
    *,
    task: CountdownTask,
    state: CountdownState,
    exploration_seed: int,
    action_digest: str,
    source: str,
) -> dict[str, Any]:
    return {
        "action_digest": action_digest,
        "exploration_seed": exploration_seed,
        "seed_plan_version": SEED_PLAN_VERSION,
        "source": source,
        "state": list(state),
        "task_fingerprint": task.task_fingerprint,
    }


def _build_seed_plan(
    tasks: Sequence[CountdownTask],
    exploration_seeds: Sequence[int],
) -> tuple[dict[str, int], dict[str, Any]]:
    identities: list[dict[str, Any]] = []
    for task in tasks:
        for state in _nonterminal_states(task):
            actions = task.legal_actions(state)
            action_digest = _action_digest(actions)
            for exploration_seed in exploration_seeds:
                for source in SOURCE_NAMES:
                    identities.append(
                        _source_seed_identity(
                            task=task,
                            state=state,
                            exploration_seed=exploration_seed,
                            action_digest=action_digest,
                            source=source,
                        )
                    )
    identities.sort(key=_canonical_json)
    result: dict[str, int] = {}
    used: dict[int, str] = {}
    collision_resolutions = 0
    max_probe = 0
    for identity in identities:
        identity_digest = _sha256_json(identity)
        candidate = int(identity_digest[:8], 16)
        probe = 0
        while candidate in used and used[candidate] != identity_digest:
            probe += 1
            candidate = (candidate + 1) % (2**32)
        used[candidate] = identity_digest
        result[identity_digest] = candidate
        if probe:
            collision_resolutions += 1
            max_probe = max(max_probe, probe)
    evidence = {
        "collision_resolutions": collision_resolutions,
        "entries": len(result),
        "max_probe": max_probe,
        "seed_map_digest": _sha256_json(
            sorted((identity_digest, seed) for identity_digest, seed in result.items())
        ),
        "version": SEED_PLAN_VERSION,
    }
    return result, evidence


def _inverse_normal(uniforms: torch.Tensor) -> torch.Tensor:
    if uniforms.dtype != torch.float64 or uniforms.device.type != "cpu":
        raise ValueError("normal transform requires CPU float64 uniforms")
    clipped = uniforms.clamp(min=ICDF_CLIP, max=1.0 - ICDF_CLIP)
    return math.sqrt(2.0) * torch.erfinv(2.0 * clipped - 1.0)


def _matrix_to_lists(matrix: torch.Tensor) -> list[list[float]]:
    return [[float(value) for value in row] for row in matrix.tolist()]


def _matrix_from_payload(
    payload: Any,
    *,
    rows: int,
    columns: int,
    name: str,
) -> torch.Tensor:
    if (
        not isinstance(payload, list)
        or len(payload) != rows
        or any(not isinstance(row, list) or len(row) != columns for row in payload)
    ):
        raise ValueError(f"{name} has the wrong matrix shape")
    tensor = torch.tensor(payload, dtype=torch.float64, device="cpu")
    if tensor.shape != (rows, columns) or not torch.isfinite(tensor).all():
        raise ValueError(f"{name} contains invalid values")
    return tensor


@dataclass(frozen=True)
class BankState:
    state: CountdownState
    action_count: int
    action_digest: str
    iid_seed: int
    sobol_seed: int
    iid_uniforms: tuple[tuple[float, ...], ...]
    iid_normals: tuple[tuple[float, ...], ...]
    sobol_uniforms: tuple[tuple[float, ...], ...]
    sobol_normals: tuple[tuple[float, ...], ...]


@dataclass(frozen=True)
class PerturbationBank:
    task: CountdownTask
    exploration_seed: int
    max_actions: int
    states: tuple[BankState, ...]
    deterministic_digest: str
    _index: dict[CountdownState, BankState]

    @classmethod
    def from_record(
        cls,
        record: Mapping[str, Any],
        *,
        verify_transform: bool,
    ) -> PerturbationBank:
        if record.get("schema_version") != BANK_SCHEMA_VERSION:
            raise ValueError("unsupported perturbation-bank schema")
        payload = {
            key: value for key, value in record.items() if key != "deterministic_digest"
        }
        if record.get("deterministic_digest") != _sha256_json(payload):
            raise ValueError("perturbation-bank digest mismatch")
        if set(payload) != {
            "exploration_seed",
            "max_actions",
            "normal_transform",
            "schema_version",
            "states",
            "task",
        }:
            raise ValueError("perturbation-bank fields drifted")
        task = _task_from_dict(payload["task"])
        exploration_seed = payload["exploration_seed"]
        max_actions = payload["max_actions"]
        if (
            type(exploration_seed) is not int
            or exploration_seed < 0
            or max_actions != MAX_ACTIONS
            or payload["normal_transform"] != _normal_transform_metadata()
        ):
            raise ValueError("perturbation-bank configuration mismatch")
        expected_states = _nonterminal_states(task)
        if not isinstance(payload["states"], list):
            raise ValueError("perturbation-bank states must be an array")
        parsed: list[BankState] = []
        index: dict[CountdownState, BankState] = {}
        for item in payload["states"]:
            if not isinstance(item, dict) or set(item) != {
                "action_count",
                "action_digest",
                "iid_normals",
                "iid_seed",
                "iid_uniforms",
                "sobol_normals",
                "sobol_seed",
                "sobol_uniforms",
                "state",
                "state_digest",
            }:
                raise ValueError("invalid perturbation-bank state row")
            state = task.canonical_state(item["state"])
            actions = task.legal_actions(state)
            action_count = len(actions)
            if (
                list(state) != item["state"]
                or state in index
                or item["action_count"] != action_count
                or item["action_digest"] != _action_digest(actions)
                or type(item["iid_seed"]) is not int
                or not 0 <= item["iid_seed"] < 2**32
                or type(item["sobol_seed"]) is not int
                or not 0 <= item["sobol_seed"] < 2**32
            ):
                raise ValueError("perturbation-bank state identity mismatch")
            state_core = {
                key: value for key, value in item.items() if key != "state_digest"
            }
            if item["state_digest"] != _sha256_json(state_core):
                raise ValueError("perturbation-bank state digest mismatch")
            tensors: dict[str, torch.Tensor] = {}
            for source in SOURCE_NAMES:
                uniforms = _matrix_from_payload(
                    item[f"{source}_uniforms"],
                    rows=THOMPSON_SIMULATIONS,
                    columns=max_actions,
                    name=f"{source}_uniforms",
                )
                normals = _matrix_from_payload(
                    item[f"{source}_normals"],
                    rows=THOMPSON_SIMULATIONS,
                    columns=max_actions,
                    name=f"{source}_normals",
                )
                if bool(((uniforms < 0.0) | (uniforms >= 1.0)).any()):
                    raise ValueError("perturbation-bank uniform escaped [0, 1)")
                if verify_transform and not torch.equal(
                    _inverse_normal(uniforms), normals
                ):
                    raise ValueError("stored inverse-normal transform mismatch")
                tensors[f"{source}_uniforms"] = uniforms
                tensors[f"{source}_normals"] = normals
            parsed_state = BankState(
                state=state,
                action_count=action_count,
                action_digest=item["action_digest"],
                iid_seed=item["iid_seed"],
                sobol_seed=item["sobol_seed"],
                iid_uniforms=tuple(
                    tuple(float(value) for value in row)
                    for row in tensors["iid_uniforms"].tolist()
                ),
                iid_normals=tuple(
                    tuple(float(value) for value in row)
                    for row in tensors["iid_normals"].tolist()
                ),
                sobol_uniforms=tuple(
                    tuple(float(value) for value in row)
                    for row in tensors["sobol_uniforms"].tolist()
                ),
                sobol_normals=tuple(
                    tuple(float(value) for value in row)
                    for row in tensors["sobol_normals"].tolist()
                ),
            )
            parsed.append(parsed_state)
            index[state] = parsed_state
        if tuple(item.state for item in parsed) != expected_states:
            raise ValueError("perturbation-bank state coverage/order mismatch")
        return cls(
            task=task,
            exploration_seed=exploration_seed,
            max_actions=max_actions,
            states=tuple(parsed),
            deterministic_digest=record["deterministic_digest"],
            _index=index,
        )

    def state(self, state: CountdownState) -> BankState:
        try:
            return self._index[state]
        except KeyError as error:
            raise KeyError(f"perturbation bank misses state {state!r}") from error


def _normal_transform_metadata() -> dict[str, Any]:
    return {
        "clip": ICDF_CLIP,
        "device": "cpu",
        "dtype": "float64",
        "formula": "sqrt(2)*erfinv(2*clip(u)-1)",
        "version": NORMAL_TRANSFORM_VERSION,
    }


def _build_bank_record(
    task: CountdownTask,
    exploration_seed: int,
    seed_plan: Mapping[str, int],
) -> dict[str, Any]:
    state_records: list[dict[str, Any]] = []
    for state in _nonterminal_states(task):
        actions = task.legal_actions(state)
        action_digest = _action_digest(actions)
        source_seeds: dict[str, int] = {}
        for source in SOURCE_NAMES:
            identity = _source_seed_identity(
                task=task,
                state=state,
                exploration_seed=exploration_seed,
                action_digest=action_digest,
                source=source,
            )
            source_seeds[source] = seed_plan[_sha256_json(identity)]
        iid_generator = torch.Generator(device="cpu").manual_seed(source_seeds["iid"])
        iid_uniforms = torch.rand(
            (THOMPSON_SIMULATIONS, MAX_ACTIONS),
            generator=iid_generator,
            dtype=torch.float64,
            device="cpu",
        )
        sobol_uniforms = SobolEngine(
            dimension=MAX_ACTIONS,
            scramble=True,
            seed=source_seeds["sobol"],
        ).draw_base2(int(math.log2(THOMPSON_SIMULATIONS)), dtype=torch.float64)
        state_core = {
            "action_count": len(actions),
            "action_digest": action_digest,
            "iid_normals": _matrix_to_lists(_inverse_normal(iid_uniforms)),
            "iid_seed": source_seeds["iid"],
            "iid_uniforms": _matrix_to_lists(iid_uniforms),
            "sobol_normals": _matrix_to_lists(_inverse_normal(sobol_uniforms)),
            "sobol_seed": source_seeds["sobol"],
            "sobol_uniforms": _matrix_to_lists(sobol_uniforms),
            "state": list(state),
        }
        state_records.append(
            {**state_core, "state_digest": _sha256_json(state_core)}
        )
    payload = {
        "exploration_seed": exploration_seed,
        "max_actions": MAX_ACTIONS,
        "normal_transform": _normal_transform_metadata(),
        "schema_version": BANK_SCHEMA_VERSION,
        "states": state_records,
        "task": task.to_dict(),
    }
    return {**payload, "deterministic_digest": _sha256_json(payload)}


def _vector_digest(values: Sequence[float]) -> str:
    return _sha256_json(list(values))


class BankCursor:
    def __init__(self, bank: PerturbationBank, selected_source: str) -> None:
        if selected_source not in SOURCE_NAMES:
            raise ValueError("unknown perturbation source")
        self.bank = bank
        self.selected_source = selected_source
        self.visits: dict[CountdownState, int] = defaultdict(int)
        self.point_reads = 0
        self.used_coordinates = 0

    def draw(self, state: CountdownState, action_count: int) -> dict[str, Any]:
        bank_state = self.bank.state(state)
        if action_count != bank_state.action_count:
            raise AssertionError("bank/action count mismatch")
        visit_index = self.visits[state]
        if visit_index >= THOMPSON_SIMULATIONS:
            raise AssertionError("node visit exceeds frozen bank depth")
        self.visits[state] += 1
        self.point_reads += 1
        self.used_coordinates += action_count
        iid_uniform = bank_state.iid_uniforms[visit_index]
        iid_normal = bank_state.iid_normals[visit_index]
        sobol_uniform = bank_state.sobol_uniforms[visit_index]
        sobol_normal = bank_state.sobol_normals[visit_index]
        selected_uniform = (
            iid_uniform if self.selected_source == "iid" else sobol_uniform
        )
        selected_normal = (
            iid_normal if self.selected_source == "iid" else sobol_normal
        )
        return {
            "iid_full_vector_digest": _vector_digest(iid_normal),
            "iid_normal": iid_normal[:action_count],
            "node_visit_index": visit_index,
            "selected_normal": selected_normal[:action_count],
            "selected_uniform": selected_uniform[:action_count],
            "sobol_full_vector_digest": _vector_digest(sobol_normal),
            "sobol_normal": sobol_normal[:action_count],
        }

    def snapshot(self) -> dict[str, Any]:
        full_coordinates = self.point_reads * self.bank.max_actions
        return {
            "bank_digest": self.bank.deterministic_digest,
            "dual_source_instrumentation": True,
            "full_coordinates_read_per_source": full_coordinates,
            "full_points_read_per_source": self.point_reads,
            "max_actions": self.bank.max_actions,
            "node_streams_read": len(self.visits),
            "padded_coordinates_per_source": full_coordinates
            - self.used_coordinates,
            "selected_source": self.selected_source,
            "used_action_coordinates": self.used_coordinates,
        }


def _argmax(values: Sequence[float]) -> int:
    return max(range(len(values)), key=lambda index: values[index])


def _top_indices(values: Sequence[float]) -> tuple[int, ...]:
    maximum = max(values)
    return tuple(index for index, value in enumerate(values) if value == maximum)


def _selection_margin(values: Sequence[float], selected: int) -> float:
    competitors = [value for index, value in enumerate(values) if index != selected]
    return values[selected] - max(competitors) if competitors else math.inf


def _run_kernel(
    context: SearchContext,
    bank: PerturbationBank,
    selected_source: str,
) -> tuple[str, dict[str, Any], dict[CountdownState, _NodeStats], int]:
    stats: dict[CountdownState, _NodeStats] = {}
    cursor = BankCursor(bank, selected_source)
    completed = 0
    positive_posterior_update_count = 0
    try:
        for simulation in range(THOMPSON_SIMULATIONS):
            state = context.task.initial_state
            actions: list[CountdownAction] = []
            states = [state]
            cumulative = 0.0
            path: list[tuple[CountdownState, int]] = []
            depth = 0
            while len(state) > 1:
                row = context.proposal(state)
                node = stats.setdefault(state, _NodeStats.create(len(row.actions)))
                context.charge_selection_and_edge(row)
                draw = cursor.draw(state, len(row.actions))
                probabilities = [math.exp(value) for value in row.prior_logp]
                posterior_sd = [
                    1.0 / math.sqrt(visits + 1) for visits in node.visits
                ]
                prior_component = [
                    THOMPSON_PRIOR_BONUS * probability
                    for probability in probabilities
                ]
                base_values = [
                    mean + prior
                    for mean, prior in zip(node.means, prior_component)
                ]
                iid_values = [
                    base + sd * noise
                    for base, sd, noise in zip(
                        base_values, posterior_sd, draw["iid_normal"]
                    )
                ]
                sobol_values = [
                    base + sd * noise
                    for base, sd, noise in zip(
                        base_values, posterior_sd, draw["sobol_normal"]
                    )
                ]
                sampled_values = (
                    iid_values if selected_source == "iid" else sobol_values
                )
                action_index = _argmax(sampled_values)
                proposal_top = _top_indices(row.prior_logp)
                base_top = _top_indices(base_values)
                dense_rank = 1 + sum(
                    value > row.prior_logp[action_index]
                    for value in row.prior_logp
                )
                normalized_rank = (
                    (dense_rank - 1) / (len(row.actions) - 1)
                    if len(row.actions) > 1
                    else 0.0
                )
                child = context.transition(
                    state=state,
                    row=row,
                    action_index=action_index,
                    details={
                        "base_top_indices": list(base_top),
                        "base_values": base_values,
                        "chosen_in_proposal_top_set": action_index in proposal_top,
                        "chosen_prior_mass": probabilities[action_index],
                        "chosen_competition_rank": dense_rank,
                        "depth": depth,
                        "iid_choice_index": _argmax(iid_values),
                        "iid_full_vector_digest": draw[
                            "iid_full_vector_digest"
                        ],
                        "local_source_choice_disagreement": (
                            _argmax(iid_values) != _argmax(sobol_values)
                        ),
                        "node_visit_index": draw["node_visit_index"],
                        "noise_overrode_base_top_set": action_index not in base_top,
                        "noise_overrode_proposal_top_set": (
                            action_index not in proposal_top
                        ),
                        "normalized_prior_rank": normalized_rank,
                        "policy": "matched_thompson_source",
                        "posterior_means_before": list(node.means),
                        "posterior_sd": posterior_sd,
                        "prior_component": prior_component,
                        "prior_regret": (
                            max(row.prior_logp) - row.prior_logp[action_index]
                        ),
                        "proposal_top_indices": list(proposal_top),
                        "sampled_values": sampled_values,
                        "selected_normal_values": list(draw["selected_normal"]),
                        "selected_source": selected_source,
                        "selected_uniform_values": list(draw["selected_uniform"]),
                        "selection_margin": _selection_margin(
                            sampled_values, action_index
                        ),
                        "simulation": simulation,
                        "sobol_choice_index": _argmax(sobol_values),
                        "sobol_full_vector_digest": draw[
                            "sobol_full_vector_digest"
                        ],
                        "visits_before": list(node.visits),
                    },
                    selection_scores_charged=len(row.actions),
                )
                actions.append(row.actions[action_index])
                states.append(child)
                path.append((state, action_index))
                cumulative += row.prior_logp[action_index]
                state = child
                depth += 1
            success = context.verify_terminal(
                actions=actions,
                states=states,
                cumulative_prior_logp=cumulative,
            )
            value = 1.0 if success else 0.0
            for visited_state, action_index in reversed(path):
                stats[visited_state].update(action_index, value)
                positive_posterior_update_count += int(success)
            completed += 1
    except SearchStopped as error:
        stop_reason = error.reason
    else:
        stop_reason = "completed_simulations"
    stats_payload = {
        _canonical_json(list(state)): {
            "m2": node.m2,
            "means": node.means,
            "visits": node.visits,
        }
        for state, node in sorted(
            stats.items(), key=lambda item: _state_sort_key(item[0])
        )
    }
    return (
        stop_reason,
        {
            "completed_simulations": completed,
            "m2_used_for_selection": False,
            "normal_source": cursor.snapshot(),
            "posterior_sd_formula": "inverse_sqrt_visits_plus_one/v1",
            "posterior_state_digest": _sha256_json(stats_payload),
        },
        stats,
        positive_posterior_update_count,
    )


def _normalized_entropy(counts: Sequence[int]) -> float:
    total = sum(counts)
    if total <= 0 or len(counts) <= 1:
        return 0.0
    probabilities = [count / total for count in counts if count]
    return -sum(value * math.log(value) for value in probabilities) / math.log(
        len(counts)
    )


def _normalized_jsd(first: Sequence[float], second: Sequence[float]) -> float:
    midpoint = [(left + right) / 2.0 for left, right in zip(first, second)]

    def kl(left: Sequence[float], right: Sequence[float]) -> float:
        return sum(
            value * math.log(value / reference)
            for value, reference in zip(left, right)
            if value > 0.0
        )

    value = (kl(first, midpoint) + kl(second, midpoint)) / (2.0 * math.log(2.0))
    return min(1.0, max(0.0, value))


def _star_discrepancy(values: Sequence[float]) -> float:
    ordered = sorted(values)
    count = len(ordered)
    return max(
        max((index + 1) / count - value, value - index / count)
        for index, value in enumerate(ordered)
    )


def _root_discrepancy(
    bank: PerturbationBank,
    source: str,
) -> dict[str, float]:
    root = bank.state(bank.task.initial_state)
    matrix = root.iid_uniforms if source == "iid" else root.sobol_uniforms
    values = [
        _star_discrepancy([row[index] for row in matrix])
        for index in range(root.action_count)
    ]
    return {
        "coordinate_max": max(values),
        "coordinate_mean": statistics.fmean(values),
    }


def _run_diagnostics(
    context: SearchContext,
    stats: Mapping[CountdownState, _NodeStats],
    bank: PerturbationBank,
    positive_posterior_update_count: int,
) -> dict[str, Any]:
    transitions = [
        event
        for event in context.selection_events
        if event["event"] == "edge_transition"
    ]
    details = [event["details"] for event in transitions]
    exact_indices = [
        terminal["observation_index"] + 1
        for terminal in context.terminals
        if terminal["verification"]["success"]
    ]
    first_exact = min(exact_indices) if exact_indices else NO_HIT_SENTINEL
    success_by_verifier = [
        any(index <= verifier for index in exact_indices)
        for verifier in range(1, THOMPSON_SIMULATIONS + 1)
    ]
    root_events = [
        event
        for event in transitions
        if tuple(event["state"]) == context.task.initial_state
    ]
    root_row = context.snapshot.get(context.task, context.task.initial_state)
    root_histogram = [0] * len(root_row.actions)
    for event in root_events:
        root_histogram[event["action_index"]] += 1
    root_prior = [math.exp(value) for value in root_row.prior_logp]
    root_visits = [count / len(root_events) for count in root_histogram]
    root_top = set(_top_indices(root_row.prior_logp))
    terminal_keys = [
        _canonical_json(terminal["actions"]) for terminal in context.terminals
    ]
    edge_keys = [
        (_canonical_json(event["state"]), event["action_index"])
        for event in transitions
    ]

    by_depth: dict[str, dict[str, float | int]] = {}
    for depth in range(len(context.task.initial_state) - 1):
        selected = [item for item in details if item["depth"] == depth]
        by_depth[str(depth)] = {
            "count": len(selected),
            "mean_normalized_prior_rank": statistics.fmean(
                item["normalized_prior_rank"] for item in selected
            ),
            "mean_prior_regret": statistics.fmean(
                item["prior_regret"] for item in selected
            ),
            "top_set_retention": statistics.fmean(
                item["chosen_in_proposal_top_set"] for item in selected
            ),
        }
    usage = context.ledger.snapshot()
    positive_actions = sum(
        mean > 0.0 for node in stats.values() for mean in node.means
    )
    root_stats = stats[context.task.initial_state]
    all_node_visits = sum(sum(node.visits) for node in stats.values())
    return {
        "all_node_visit_sum": all_node_visits,
        "by_depth": by_depth,
        "cache_hit_rate": (
            usage["cache_hits"] / usage["cache_lookups"]
            if usage["cache_lookups"]
            else 0.0
        ),
        "duplicate_terminal_rate": 1.0
        - len(set(terminal_keys)) / len(terminal_keys),
        "exact_terminal_count": len(exact_indices),
        "first_exact_verifier": first_exact,
        "local_source_choice_disagreement_rate": statistics.fmean(
            item["local_source_choice_disagreement"] for item in details
        ),
        "mean_chosen_prior_mass": statistics.fmean(
            item["chosen_prior_mass"] for item in details
        ),
        "mean_normalized_prior_rank": statistics.fmean(
            item["normalized_prior_rank"] for item in details
        ),
        "mean_prior_regret": statistics.fmean(
            item["prior_regret"] for item in details
        ),
        "noise_overrode_base_rate": statistics.fmean(
            item["noise_overrode_base_top_set"] for item in details
        ),
        "noise_overrode_proposal_rate": statistics.fmean(
            item["noise_overrode_proposal_top_set"] for item in details
        ),
        "final_root_posterior": {
            "means": list(root_stats.means),
            "visits": list(root_stats.visits),
        },
        "positive_posterior_update_count": positive_posterior_update_count,
        "positive_posterior_action_count": positive_actions,
        "posterior_update_count": all_node_visits,
        "root_iid_star_discrepancy": _root_discrepancy(bank, "iid"),
        "root_jsd_from_proposal_prior": _normalized_jsd(root_visits, root_prior),
        "root_max_visit_share": max(root_visits),
        "root_sobol_star_discrepancy": _root_discrepancy(bank, "sobol"),
        "root_top_set_visit_fraction": sum(
            root_histogram[index] for index in root_top
        )
        / len(root_events),
        "root_unique_arms": sum(count > 0 for count in root_histogram),
        "root_visit_entropy": _normalized_entropy(root_histogram),
        "root_visit_histogram": root_histogram,
        "simulations_before_first_positive_backup": (
            first_exact - 1 if exact_indices else THOMPSON_SIMULATIONS
        ),
        "success_auc": statistics.fmean(success_by_verifier),
        "success_by_verifier": success_by_verifier,
        "top_set_retention": statistics.fmean(
            item["chosen_in_proposal_top_set"] for item in details
        ),
        "unique_edge_count": len(set(edge_keys)),
        "unique_terminal_trace_count": len(set(terminal_keys)),
    }


def _method_config(selected_source: str) -> dict[str, Any]:
    return {
        "dual_source_instrumentation": True,
        "gamma": 1.0,
        "m2_used_for_selection": False,
        "max_actions": MAX_ACTIONS,
        "normal_transform": _normal_transform_metadata(),
        "posterior_sd_formula": "inverse_sqrt_visits_plus_one/v1",
        "prior_bonus": THOMPSON_PRIOR_BONUS,
        "prior_component_formula": "prior_bonus*exp(prior_logp)",
        "pruning": False,
        "selected_perturbation_source": selected_source,
        "semantic_routing": False,
        "shaped_reward": False,
        "simulations": THOMPSON_SIMULATIONS,
        "terminal_reward": "exact_1_or_0",
    }


def run_search(
    *,
    provider: str,
    task: CountdownTask,
    snapshot: ProposalSnapshot,
    bank: PerturbationBank,
    method: str,
    expected_behavior_digest: str | None = None,
) -> dict[str, Any]:
    if provider not in FROZEN_SOURCES:
        raise ValueError("unknown frozen provider label")
    if method not in METHODS:
        raise ValueError("unknown matched Thompson method")
    expected_digest = (
        FROZEN_SOURCES[provider]["behavior_digest"]
        if expected_behavior_digest is None
        else expected_behavior_digest
    )
    if task != bank.task or snapshot.behavior_digest != expected_digest:
        raise ValueError("search input identity mismatch")
    selected_source = METHOD_SOURCE[method]
    context = SearchContext(task, snapshot, method, bank.exploration_seed)
    stop_reason, method_state, stats, positive_posterior_update_count = _run_kernel(
        context, bank, selected_source
    )
    readout = context.readout()
    diagnostics = _run_diagnostics(
        context, stats, bank, positive_posterior_update_count
    )
    payload = {
        "bank_digest": bank.deterministic_digest,
        "budget": SEARCH_BUDGET.to_dict(),
        "claim_role": "offline_conditional_dev_robustness_only",
        "diagnostics": diagnostics,
        "exact_success_any": any(
            terminal["verification"]["success"] for terminal in context.terminals
        ),
        "method": method,
        "method_config": _method_config(selected_source),
        "method_state": method_state,
        "proposal_behavior_digest": snapshot.behavior_digest,
        "proposal_events": context.proposal_events,
        "provider": provider,
        "readout": readout,
        "rng": {
            "bank_digest": bank.deterministic_digest,
            "exploration_seed": bank.exploration_seed,
            "selected_source": selected_source,
            "version": EXPERIMENT_VERSION,
        },
        "schema_version": RECORD_SCHEMA_VERSION,
        "seed": bank.exploration_seed,
        "selection_events": context.selection_events,
        "stop_reason": stop_reason,
        "task": task.to_dict(),
        "terminals": context.terminals,
        "usage": context.ledger.snapshot(),
    }
    return {**payload, "deterministic_digest": canonical_record_digest(payload)}


def _mean(values: Sequence[float]) -> float:
    return statistics.fmean(values)


def _variance(values: Sequence[float]) -> float:
    return statistics.variance(values) if len(values) > 1 else 0.0


def _quantile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return (1.0 - weight) * ordered[lower] + weight * ordered[upper]


def _median_absolute_deviation(values: Sequence[float]) -> float:
    median = statistics.median(values)
    return statistics.median(abs(value - median) for value in values)


def _wilson(successes: int, total: int) -> list[float]:
    z = 1.959963984540054
    p = successes / total
    denominator = 1.0 + z * z / total
    center = (p + z * z / (2.0 * total)) / denominator
    radius = (
        z
        * math.sqrt(p * (1.0 - p) / total + z * z / (4.0 * total * total))
        / denominator
    )
    return [max(0.0, center - radius), min(1.0, center + radius)]


def _exact_mcnemar_p(qmc_only: int, iid_only: int) -> float:
    discordant = qmc_only + iid_only
    if discordant == 0:
        return 1.0
    tail = min(qmc_only, iid_only)
    probability = sum(math.comb(discordant, index) for index in range(tail + 1))
    return min(1.0, 2.0 * probability / (2**discordant))


def _conditional_mean_interval(values: Sequence[float]) -> list[float]:
    mean = _mean(values)
    if len(values) < 2:
        return [mean, mean]
    radius = 1.959963984540054 * math.sqrt(_variance(values) / len(values))
    return [mean - radius, mean + radius]


METRIC_PATHS = {
    "cache_hits": ("usage", "cache_hits"),
    "cache_misses": ("usage", "cache_misses"),
    "cache_hit_rate": ("diagnostics", "cache_hit_rate"),
    "duplicate_terminal_rate": ("diagnostics", "duplicate_terminal_rate"),
    "exact_success": ("exact_success_any",),
    "exact_terminal_count": ("diagnostics", "exact_terminal_count"),
    "first_exact_verifier": ("diagnostics", "first_exact_verifier"),
    "local_source_choice_disagreement_rate": (
        "diagnostics",
        "local_source_choice_disagreement_rate",
    ),
    "mean_chosen_prior_mass": ("diagnostics", "mean_chosen_prior_mass"),
    "mean_normalized_prior_rank": (
        "diagnostics",
        "mean_normalized_prior_rank",
    ),
    "mean_prior_regret": ("diagnostics", "mean_prior_regret"),
    "noise_overrode_base_rate": ("diagnostics", "noise_overrode_base_rate"),
    "noise_overrode_proposal_rate": (
        "diagnostics",
        "noise_overrode_proposal_rate",
    ),
    "positive_posterior_update_count": (
        "diagnostics",
        "positive_posterior_update_count",
    ),
    "positive_posterior_action_count": (
        "diagnostics",
        "positive_posterior_action_count",
    ),
    "proposal_action_scores": ("usage", "usage", "proposal_action_scores"),
    "proposal_batch_calls": ("usage", "usage", "proposal_batch_calls"),
    "proposal_input_values": ("usage", "usage", "proposal_input_values"),
    "proposal_state_items": ("usage", "usage", "proposal_state_items"),
    "root_jsd_from_proposal_prior": (
        "diagnostics",
        "root_jsd_from_proposal_prior",
    ),
    "root_max_visit_share": ("diagnostics", "root_max_visit_share"),
    "root_top_set_visit_fraction": (
        "diagnostics",
        "root_top_set_visit_fraction",
    ),
    "root_unique_arms": ("diagnostics", "root_unique_arms"),
    "root_visit_entropy": ("diagnostics", "root_visit_entropy"),
    "selection_action_scores": ("usage", "usage", "selection_action_scores"),
    "success_auc": ("diagnostics", "success_auc"),
    "top_set_retention": ("diagnostics", "top_set_retention"),
    "unique_edge_count": ("diagnostics", "unique_edge_count"),
    "unique_states": ("usage", "unique_states"),
    "unique_terminal_trace_count": (
        "diagnostics",
        "unique_terminal_trace_count",
    ),
}

METRIC_DIRECTIONS = {
    "cache_hits": "descriptive",
    "cache_misses": "descriptive",
    "cache_hit_rate": "descriptive",
    "duplicate_terminal_rate": "descriptive",
    "exact_success": "higher_is_better",
    "exact_terminal_count": "higher_is_better",
    "first_exact_verifier": "lower_is_better",
    "local_source_choice_disagreement_rate": "descriptive",
    "mean_chosen_prior_mass": "higher_preserves_proposal",
    "mean_normalized_prior_rank": "lower_preserves_proposal",
    "mean_prior_regret": "lower_preserves_proposal",
    "noise_overrode_base_rate": "lower_preserves_proposal",
    "noise_overrode_proposal_rate": "lower_preserves_proposal",
    "positive_posterior_update_count": "higher_is_better",
    "positive_posterior_action_count": "higher_is_better",
    "proposal_action_scores": "lower_compute",
    "proposal_batch_calls": "lower_compute",
    "proposal_input_values": "lower_compute",
    "proposal_state_items": "lower_compute",
    "root_jsd_from_proposal_prior": "descriptive",
    "root_max_visit_share": "descriptive",
    "root_top_set_visit_fraction": "higher_preserves_proposal",
    "root_unique_arms": "higher_is_broader",
    "root_visit_entropy": "higher_is_broader",
    "selection_action_scores": "lower_compute",
    "success_auc": "higher_is_better",
    "top_set_retention": "higher_preserves_proposal",
    "unique_edge_count": "higher_is_broader",
    "unique_states": "higher_is_broader",
    "unique_terminal_trace_count": "higher_is_broader",
}

DEPTH_METRICS = (
    "mean_normalized_prior_rank",
    "mean_prior_regret",
    "top_set_retention",
)


def _path(record: Mapping[str, Any], path: Sequence[str]) -> Any:
    value: Any = record
    for key in path:
        value = value[key]
    return value


def _cell_summary(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    success_count = sum(bool(record["exact_success_any"]) for record in records)
    metrics: dict[str, Any] = {}
    for name, path in METRIC_PATHS.items():
        values = [float(_path(record, path)) for record in records]
        metrics[name] = {
            "direction": METRIC_DIRECTIONS[name],
            "mean": _mean(values),
            "median": statistics.median(values),
            "median_absolute_deviation": _median_absolute_deviation(values),
            "p05": _quantile(values, 0.05),
            "p95": _quantile(values, 0.95),
            "seed_variance": _variance(values),
        }
    by_depth: dict[str, Any] = {}
    for depth in range(len(DEV_TASKS[0].initial_state) - 1):
        by_depth[str(depth)] = {}
        for name in DEPTH_METRICS:
            values = [
                float(record["diagnostics"]["by_depth"][str(depth)][name])
                for record in records
            ]
            by_depth[str(depth)][name] = {
                "direction": METRIC_DIRECTIONS[name],
                "mean": _mean(values),
                "median": statistics.median(values),
                "median_absolute_deviation": _median_absolute_deviation(values),
                "seed_variance": _variance(values),
            }
    return {
        "by_depth": by_depth,
        "records": len(records),
        "success_count": success_count,
        "success_rate": success_count / len(records),
        "success_rate_wilson95_conditional": _wilson(success_count, len(records)),
        "metrics": metrics,
    }


def _pair_summary(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    by_seed: dict[int, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for record in records:
        if record["method"] in by_seed[record["seed"]]:
            raise AssertionError("duplicate method record in paired seed block")
        by_seed[record["seed"]][record["method"]] = record
    if any(set(pair) != set(METHODS) for pair in by_seed.values()):
        raise AssertionError("paired method block is incomplete")
    both = qmc_only = iid_only = neither = 0
    deltas: dict[str, list[float]] = {name: [] for name in METRIC_PATHS}
    depth_deltas: dict[str, dict[str, list[float]]] = {
        str(depth): {name: [] for name in DEPTH_METRICS}
        for depth in range(len(DEV_TASKS[0].initial_state) - 1)
    }
    shared_events = 0
    shared_root_events = 0
    vector_digest_mismatches = 0
    for pair in by_seed.values():
        iid = pair["matched_iid_thompson_8"]
        qmc = pair["qmc_thompson_8"]
        iid_success = bool(iid["exact_success_any"])
        qmc_success = bool(qmc["exact_success_any"])
        if iid_success and qmc_success:
            both += 1
        elif qmc_success:
            qmc_only += 1
        elif iid_success:
            iid_only += 1
        else:
            neither += 1
        for name, path in METRIC_PATHS.items():
            deltas[name].append(float(_path(qmc, path)) - float(_path(iid, path)))
        for depth, metric_values in depth_deltas.items():
            for name, values in metric_values.items():
                values.append(
                    float(qmc["diagnostics"]["by_depth"][depth][name])
                    - float(iid["diagnostics"]["by_depth"][depth][name])
                )
        event_maps: list[dict[tuple[Any, ...], Mapping[str, Any]]] = []
        for record in (iid, qmc):
            mapping: dict[tuple[Any, ...], Mapping[str, Any]] = {}
            for event in record["selection_events"]:
                if event["event"] != "edge_transition":
                    continue
                details = event["details"]
                key = (
                    tuple(event["state"]),
                    details["node_visit_index"],
                )
                mapping[key] = details
            event_maps.append(mapping)
        common = set(event_maps[0]) & set(event_maps[1])
        shared_events += len(common)
        root_common = {
            key
            for key in common
            if key[0] == tuple(iid["task"]["inputs"])
        }
        if len(root_common) != THOMPSON_SIMULATIONS:
            raise AssertionError("paired methods do not share all eight root points")
        shared_root_events += len(root_common)
        for key in common:
            for source in SOURCE_NAMES:
                digest_key = f"{source}_full_vector_digest"
                vector_digest_mismatches += int(
                    event_maps[0][key][digest_key]
                    != event_maps[1][key][digest_key]
                )
    paired_metrics = {
        name: {
            "conditional_normal_interval95": _conditional_mean_interval(values),
            "direction": METRIC_DIRECTIONS[name],
            "mean_improvement": (
                _mean(values)
                if METRIC_DIRECTIONS[name] == "higher_is_better"
                else (
                    -_mean(values)
                    if METRIC_DIRECTIONS[name] == "lower_is_better"
                    else None
                )
            ),
            "mean_qmc_minus_iid": _mean(values),
            "median_absolute_deviation": _median_absolute_deviation(values),
            "median_qmc_minus_iid": statistics.median(values),
            "p05_qmc_minus_iid": _quantile(values, 0.05),
            "p95_qmc_minus_iid": _quantile(values, 0.95),
            "seed_variance_of_delta": _variance(values),
        }
        for name, values in deltas.items()
    }
    paired_by_depth = {
        depth: {
            name: {
                "conditional_normal_interval95": _conditional_mean_interval(values),
                "direction": METRIC_DIRECTIONS[name],
                "mean_qmc_minus_iid": _mean(values),
                "median_qmc_minus_iid": statistics.median(values),
                "seed_variance_of_delta": _variance(values),
            }
            for name, values in metric_values.items()
        }
        for depth, metric_values in depth_deltas.items()
    }
    return {
        "discordance": {
            "both_success": both,
            "iid_only": iid_only,
            "neither": neither,
            "qmc_only": qmc_only,
        },
        "exact_mcnemar_p_conditional": _exact_mcnemar_p(qmc_only, iid_only),
        "paired_blocks": len(by_seed),
        "paired_by_depth": paired_by_depth,
        "paired_metrics": paired_metrics,
        "shared_root_state_visit_events": shared_root_events,
        "shared_state_visit_events": shared_events,
        "vector_digest_mismatches": vector_digest_mismatches,
    }


def _equal_task_macro(
    cells: Mapping[str, Any],
    pairs: Mapping[str, Any],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for provider in FROZEN_SOURCES:
        provider_cells: dict[str, Any] = {}
        for method in METHODS:
            task_cells = [
                cells[provider][task.task_fingerprint][method] for task in DEV_TASKS
            ]
            provider_cells[method] = {
                "success_rate": _mean(
                    [task_cell["success_rate"] for task_cell in task_cells]
                ),
                "metrics": {
                    name: {
                        "direction": METRIC_DIRECTIONS[name],
                        "mean": _mean(
                            [
                                task_cell["metrics"][name]["mean"]
                                for task_cell in task_cells
                            ]
                        ),
                    }
                    for name in METRIC_PATHS
                },
            }
        task_pairs = [
            pairs[provider][task.task_fingerprint] for task in DEV_TASKS
        ]
        provider_pairs = {
            name: {
                "direction": METRIC_DIRECTIONS[name],
                "mean_improvement": (
                    _mean(
                        [
                            task_pair["paired_metrics"][name]["mean_improvement"]
                            for task_pair in task_pairs
                        ]
                    )
                    if METRIC_DIRECTIONS[name]
                    in {"higher_is_better", "lower_is_better"}
                    else None
                ),
                "mean_qmc_minus_iid": _mean(
                    [
                        task_pair["paired_metrics"][name]["mean_qmc_minus_iid"]
                        for task_pair in task_pairs
                    ]
                ),
            }
            for name in METRIC_PATHS
        }
        result[provider] = {
            "cells": provider_cells,
            "paired_metrics": provider_pairs,
        }
    return result


def _snapshot_pairing_gate(
    snapshots: Mapping[str, ProposalSnapshot],
) -> dict[str, Any]:
    first = snapshots["anthropic"]
    second = snapshots["openai"]
    first_index = {
        (row.task_fingerprint, row.state): row for row in first.rows
    }
    second_index = {
        (row.task_fingerprint, row.state): row for row in second.rows
    }
    if set(first_index) != set(second_index):
        raise AssertionError("frozen snapshot state identities differ")
    action_count = 0
    input_values = 0
    action_order_equal = 0
    for key in sorted(first_index, key=lambda item: (item[0], _state_sort_key(item[1]))):
        left = first_index[key]
        right = second_index[key]
        if left.actions != right.actions:
            raise AssertionError("frozen snapshot action order differs")
        action_order_equal += 1
        action_count += len(left.actions)
        input_values += len(left.state) + 1
    maximum = max(len(row.actions) for row in first.rows)
    result = {
        "action_order_equal_states": action_order_equal,
        "actions": action_count,
        "input_values": input_values,
        "max_actions": maximum,
        "states": len(first.rows),
        "tasks": len({row.task_fingerprint for row in first.rows}),
    }
    if result != {
        "action_order_equal_states": 64,
        "actions": 352,
        "input_values": 259,
        "max_actions": MAX_ACTIONS,
        "states": 64,
        "tasks": 2,
    }:
        raise AssertionError("frozen snapshot comparison workload drifted")
    return result


def _bank_discrepancy_summary(
    banks: Sequence[PerturbationBank],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for task in DEV_TASKS:
        task_banks = [bank for bank in banks if bank.task == task]
        source_result: dict[str, Any] = {}
        for source in SOURCE_NAMES:
            mean_values = [
                _root_discrepancy(bank, source)["coordinate_mean"]
                for bank in task_banks
            ]
            max_values = [
                _root_discrepancy(bank, source)["coordinate_max"]
                for bank in task_banks
            ]
            source_result[source] = {
                "coordinate_max_mean_over_seeds": _mean(max_values),
                "coordinate_mean_mean_over_seeds": _mean(mean_values),
                "coordinate_mean_seed_variance": _variance(mean_values),
            }
        iid_by_seed = {
            bank.exploration_seed: _root_discrepancy(bank, "iid")[
                "coordinate_mean"
            ]
            for bank in task_banks
        }
        sobol_by_seed = {
            bank.exploration_seed: _root_discrepancy(bank, "sobol")[
                "coordinate_mean"
            ]
            for bank in task_banks
        }
        deltas = [
            sobol_by_seed[seed] - iid_by_seed[seed] for seed in sorted(iid_by_seed)
        ]
        source_result["comparison"] = {
            "fraction_sobol_lower": statistics.fmean(value < 0.0 for value in deltas),
            "mean_sobol_minus_iid": _mean(deltas),
            "seed_variance_of_delta": _variance(deltas),
        }
        result[task.task_fingerprint] = source_result
    return result


def _aggregate(
    *,
    records: Sequence[Mapping[str, Any]],
    banks: Sequence[PerturbationBank],
    snapshots: Mapping[str, ProposalSnapshot],
    seed_plan_evidence: Mapping[str, Any],
    source_validation: Mapping[str, Any],
    runtime_metadata: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    expected_records = (
        len(FROZEN_SOURCES) * len(DEV_TASKS) * len(EXPLORATION_SEEDS) * len(METHODS)
    )
    if len(records) != expected_records:
        raise AssertionError("matched experiment record count drifted")
    cells: dict[str, Any] = {}
    pairs: dict[str, Any] = {}
    for provider in FROZEN_SOURCES:
        cells[provider] = {}
        pairs[provider] = {}
        for task in DEV_TASKS:
            task_records = [
                record
                for record in records
                if record["provider"] == provider
                and record["task"]["task_fingerprint"] == task.task_fingerprint
            ]
            cells[provider][task.task_fingerprint] = {
                method: _cell_summary(
                    [record for record in task_records if record["method"] == method]
                )
                for method in METHODS
            }
            pairs[provider][task.task_fingerprint] = _pair_summary(task_records)
    pairing = _snapshot_pairing_gate(snapshots)
    pairing.update(
        {
            "bank_records": len(banks),
            "credentials_present": False,
            "estimated_provider_cost_usd": 0.0,
            "expected_records": expected_records,
            "network_or_provider_calls": 0,
            "paired_blocks": expected_records // len(METHODS),
            "per_run_fixed_compute": {
                "edge_selections": 40,
                "full_coordinates_read_per_source": 560,
                "full_points_read_per_source": 40,
                "posterior_updates": 40,
                "root_visits": 8,
                "transitions": 40,
                "verifier_calls": 8,
            },
            "seeds": len(EXPLORATION_SEEDS),
        }
    )
    runtime = (
        {
            "python_version": platform.python_version(),
            "torch_version": str(torch.__version__),
        }
        if runtime_metadata is None
        else dict(runtime_metadata)
    )
    if set(runtime) != {"python_version", "torch_version"}:
        raise ValueError("runtime metadata fields drifted")
    payload = {
        "artifact_role": "offline_source_ablation_development_evidence",
        "cells": cells,
        "claim_boundary": (
            "Conditional randomization robustness on two public development tasks; "
            "not task-generalization or QMC-superiority evidence."
        ),
        "equal_task_macro": _equal_task_macro(cells, pairs),
        "experiment_config": {
            "experiment_version": EXPERIMENT_VERSION,
            "methods": list(METHODS),
            "normal_transform": _normal_transform_metadata(),
            "search_budget": SEARCH_BUDGET.to_dict(),
            "seed_count": SEED_COUNT,
            "seed_start": SEED_START,
            "thompson": _method_config("SOURCE_FACTOR"),
            **runtime,
        },
        "estimand_scope": {
            "alpha_decision": False,
            "delta_definition": "qmc_minus_iid",
            "interval_scope": "seed_randomization_within_fixed_task",
            "provider_superiority": False,
            "qmc_superiority": False,
            "task_generalization": False,
        },
        "manipulation_check": {
            "root_star_discrepancy": _bank_discrepancy_summary(banks),
        },
        "metric_directions": METRIC_DIRECTIONS,
        "pairing_gate": pairing,
        "paired_results": pairs,
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "seed_plan": dict(seed_plan_evidence),
        "source_validation": dict(source_validation),
        "sources": {
            provider: {
                **FROZEN_SOURCES[provider],
                "copied_snapshot_behavior_digest": snapshots[
                    provider
                ].behavior_digest,
            }
            for provider in FROZEN_SOURCES
        },
        "tasks": {
            task.task_fingerprint: task.to_dict() for task in DEV_TASKS
        },
    }
    return {**payload, "deterministic_digest": _sha256_json(payload)}


def _validate_run_record(
    record: Mapping[str, Any],
    snapshot: ProposalSnapshot,
    bank: PerturbationBank,
) -> None:
    _validate_search_record(
        record,
        snapshot,
        record_schema_version=RECORD_SCHEMA_VERSION,
    )
    method = record["method"]
    if (
        method not in METHODS
        or record["provider"] not in FROZEN_SOURCES
        or record["bank_digest"] != bank.deterministic_digest
        or record["seed"] != bank.exploration_seed
        or record["method_config"] != _method_config(METHOD_SOURCE[method])
        or record["stop_reason"] != "completed_simulations"
        or record["method_state"]["completed_simulations"] != THOMPSON_SIMULATIONS
        or record["method_state"]["posterior_sd_formula"]
        != "inverse_sqrt_visits_plus_one/v1"
        or record["method_state"]["m2_used_for_selection"] is not False
    ):
        raise AssertionError("matched Thompson record identity/config mismatch")
    usage = record["usage"]
    expected_edges = THOMPSON_SIMULATIONS * (len(bank.task.initial_state) - 1)
    if (
        len(record["terminals"]) != THOMPSON_SIMULATIONS
        or usage["usage"]["verifier_calls"] != THOMPSON_SIMULATIONS
        or usage["usage"]["edge_selections"] != expected_edges
        or usage["usage"]["transitions"] != expected_edges
        or usage["evaluation_only_calls"] != 1
        or usage["overshoot"] != 0
        or usage["exhausted_axes"] != ["verifier_calls"]
        or record["diagnostics"]["all_node_visit_sum"] != expected_edges
        or record["diagnostics"]["posterior_update_count"] != expected_edges
        or sum(record["diagnostics"]["root_visit_histogram"])
        != THOMPSON_SIMULATIONS
    ):
        raise AssertionError("matched Thompson per-run budget did not close")
    source = record["method_state"]["normal_source"]
    if (
        source["bank_digest"] != bank.deterministic_digest
        or source["selected_source"] != METHOD_SOURCE[method]
        or source["full_points_read_per_source"] != expected_edges
        or source["full_coordinates_read_per_source"] != expected_edges * MAX_ACTIONS
        or source["used_action_coordinates"]
        != usage["usage"]["selection_action_scores"]
        or source["padded_coordinates_per_source"]
        != expected_edges * MAX_ACTIONS
        - usage["usage"]["selection_action_scores"]
    ):
        raise AssertionError("dual perturbation-source accounting mismatch")
    for event in record["selection_events"]:
        details = event["details"]
        if (
            details["policy"] != "matched_thompson_source"
            or details["selected_source"] != METHOD_SOURCE[method]
            or details["sampled_values"][event["action_index"]]
            != max(details["sampled_values"])
            or not 0 <= details["node_visit_index"] < THOMPSON_SIMULATIONS
            or len(details["sampled_values"])
            != event["selection_action_scores"]
        ):
            raise AssertionError("matched Thompson selection diagnostics mismatch")


def _load_copied_snapshots(
    artifact_dir: Path,
) -> dict[str, ProposalSnapshot]:
    snapshots = {
        provider: load_snapshot(artifact_dir / f"{provider}_proposal_rows.jsonl")
        for provider in FROZEN_SOURCES
    }
    for provider, snapshot in snapshots.items():
        path = artifact_dir / f"{provider}_proposal_rows.jsonl"
        frozen = FROZEN_SOURCES[provider]
        if (
            snapshot.behavior_digest != frozen["behavior_digest"]
            or _file_sha256(path) != frozen["proposal_sha256"]
        ):
            raise AssertionError(f"{provider} frozen proposal identity mismatch")
    _snapshot_pairing_gate(snapshots)
    return snapshots


def _expected_source_validation_receipt() -> dict[str, Any]:
    return {
        "mode": "offline_validator_on_scratch_copy",
        "network_guard": "socket_and_create_connection_denied",
        "providers": {
            provider: {
                "frozen_manifest_sha256": frozen["manifest_sha256"],
                "frozen_summary_digest": frozen["summary_digest"],
                "validator_returned_summary_digest": frozen["summary_digest"],
            }
            for provider, frozen in FROZEN_SOURCES.items()
        },
    }


@contextmanager
def _deny_network() -> Iterable[None]:
    original_socket = socket.socket
    original_create_connection = socket.create_connection

    def denied(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise RuntimeError("network access is forbidden in offline ablation")

    socket.socket = denied  # type: ignore[assignment]
    socket.create_connection = denied
    try:
        yield
    finally:
        socket.socket = original_socket
        socket.create_connection = original_create_connection


def _validate_sources_without_mutation(
    source_dirs: Mapping[str, Path],
) -> dict[str, Any]:
    validators = {
        "anthropic": validate_anthropic_artifact,
        "openai": validate_openai_artifact,
    }
    receipt = _expected_source_validation_receipt()
    with tempfile.TemporaryDirectory(prefix="countdown_source_validation_") as root:
        validation_root = Path(root)
        for provider, source_dir in source_dirs.items():
            frozen = FROZEN_SOURCES[provider]
            if (
                _file_sha256(source_dir / "manifest.json")
                != frozen["manifest_sha256"]
                or _read_json(source_dir / "summary.json").get(
                    "deterministic_digest"
                )
                != frozen["summary_digest"]
            ):
                raise AssertionError(f"{provider} frozen source receipt drifted")
            copied = validation_root / provider
            shutil.copytree(source_dir, copied)
            result = validators[provider](copied)
            if result["deterministic_digest"] != frozen["summary_digest"]:
                raise AssertionError(
                    f"{provider} copied source failed deterministic validation"
                )
    return receipt


def validate_artifact(
    artifact_dir: Path,
    *,
    require_replay_match: bool = True,
    verify_bank_transform: bool = False,
) -> dict[str, Any]:
    manifest = _read_json(artifact_dir / "manifest.json")
    manifest_payload = {
        key: value for key, value in manifest.items() if key != "deterministic_digest"
    }
    expected_files = {
        "anthropic_proposal_rows.jsonl",
        "openai_proposal_rows.jsonl",
        "perturbation_banks.jsonl",
        "search_records.jsonl",
        "summary.json",
    }
    if (
        manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION
        or manifest.get("status") != "COMPLETE"
        or set(manifest.get("files", {})) != expected_files
        or manifest.get("deterministic_digest") != _sha256_json(manifest_payload)
    ):
        raise AssertionError("matched ablation manifest schema mismatch")
    for filename, expected in manifest["files"].items():
        path = artifact_dir / filename
        observed = _file_metadata(
            path,
            records=len(_read_jsonl(path)) if path.suffix == ".jsonl" else None,
        )
        if observed != expected:
            raise AssertionError(f"matched ablation byte manifest mismatch: {filename}")
    snapshots = _load_copied_snapshots(artifact_dir)
    bank_records = _read_jsonl(artifact_dir / "perturbation_banks.jsonl")
    banks = tuple(
        PerturbationBank.from_record(
            record,
            verify_transform=verify_bank_transform,
        )
        for record in bank_records
    )
    bank_index = {
        (bank.task.task_fingerprint, bank.exploration_seed): bank for bank in banks
    }
    expected_bank_key_sequence = [
        (task.task_fingerprint, seed)
        for task in DEV_TASKS
        for seed in EXPLORATION_SEEDS
    ]
    observed_bank_key_sequence = [
        (bank.task.task_fingerprint, bank.exploration_seed) for bank in banks
    ]
    if (
        observed_bank_key_sequence != expected_bank_key_sequence
        or len(bank_index) != len(banks)
    ):
        raise AssertionError("perturbation-bank fixture coverage mismatch")
    seed_plan, seed_plan_evidence = _build_seed_plan(DEV_TASKS, EXPLORATION_SEEDS)
    for bank in banks:
        for bank_state in bank.states:
            actions = bank.task.legal_actions(bank_state.state)
            for source in SOURCE_NAMES:
                identity = _source_seed_identity(
                    task=bank.task,
                    state=bank_state.state,
                    exploration_seed=bank.exploration_seed,
                    action_digest=_action_digest(actions),
                    source=source,
                )
                expected_seed = seed_plan[_sha256_json(identity)]
                if getattr(bank_state, f"{source}_seed") != expected_seed:
                    raise AssertionError("perturbation-bank seed plan mismatch")
    records = _read_jsonl(artifact_dir / "search_records.jsonl")
    record_keys = [
        (
            record["provider"],
            record["task"]["task_fingerprint"],
            record["seed"],
            record["method"],
        )
        for record in records
    ]
    expected_record_key_sequence = [
        (provider, task.task_fingerprint, seed, method)
        for provider in FROZEN_SOURCES
        for task in DEV_TASKS
        for seed in EXPLORATION_SEEDS
        for method in METHODS
    ]
    if record_keys != expected_record_key_sequence:
        raise AssertionError("matched experiment record pairing/order is incomplete")
    replay_records: list[dict[str, Any]] = []
    for record in records:
        task = _task_from_dict(record["task"])
        bank = bank_index[(task.task_fingerprint, record["seed"])]
        snapshot = snapshots[record["provider"]]
        _validate_run_record(record, snapshot, bank)
        if require_replay_match:
            replay = run_search(
                provider=record["provider"],
                task=task,
                snapshot=snapshot,
                bank=bank,
                method=record["method"],
            )
            if _canonical_json(replay) != _canonical_json(record):
                raise AssertionError("matched Thompson search replay mismatch")
            replay_records.append(replay)
    if require_replay_match:
        replay_bytes = "".join(
            _canonical_json(record) + "\n" for record in replay_records
        ).encode("utf-8")
        if replay_bytes != (artifact_dir / "search_records.jsonl").read_bytes():
            raise AssertionError("matched Thompson replay bytes differ")
    summary = _read_json(artifact_dir / "summary.json")
    if summary.get("schema_version") != SUMMARY_SCHEMA_VERSION:
        raise AssertionError("matched ablation summary schema mismatch")
    summary_payload = {
        key: value for key, value in summary.items() if key != "deterministic_digest"
    }
    if summary.get("deterministic_digest") != _sha256_json(summary_payload):
        raise AssertionError("matched ablation summary digest mismatch")
    runtime_metadata = {
        "python_version": summary["experiment_config"]["python_version"],
        "torch_version": summary["experiment_config"]["torch_version"],
    }
    if summary["source_validation"] != _expected_source_validation_receipt():
        raise AssertionError("source validation receipt is not frozen")
    recomputed_summary = _aggregate(
        records=records,
        banks=banks,
        snapshots=snapshots,
        seed_plan_evidence=seed_plan_evidence,
        source_validation=summary["source_validation"],
        runtime_metadata=runtime_metadata,
    )
    if _canonical_json(recomputed_summary) != _canonical_json(summary):
        raise AssertionError("matched ablation summary does not recompute")
    if any(
        pair["vector_digest_mismatches"] != 0
        for provider in summary["paired_results"].values()
        for pair in provider.values()
    ):
        raise AssertionError("paired latent perturbation vectors drifted")
    return summary


def _run_experiment_offline(
    *,
    anthropic_dir: Path,
    openai_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError("output directory must not already exist")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    source_dirs = {
        "anthropic": anthropic_dir,
        "openai": openai_dir,
    }
    source_validation = _validate_sources_without_mutation(source_dirs)
    source_paths = {
        "anthropic": anthropic_dir / "proposal_rows.jsonl",
        "openai": openai_dir / "proposal_rows.jsonl",
    }
    for provider, path in source_paths.items():
        if _file_sha256(path) != FROZEN_SOURCES[provider]["proposal_sha256"]:
            raise AssertionError(f"{provider} source proposal bytes drifted")

    temporary = Path(
        tempfile.mkdtemp(prefix="countdown_thompson_ablation_", dir=output_dir.parent)
    )
    try:
        for provider, source in source_paths.items():
            shutil.copyfile(
                source,
                temporary / f"{provider}_proposal_rows.jsonl",
            )
        snapshots = _load_copied_snapshots(temporary)
        seed_plan, seed_plan_evidence = _build_seed_plan(
            DEV_TASKS, EXPLORATION_SEEDS
        )
        bank_records = [
            _build_bank_record(task, seed, seed_plan)
            for task in DEV_TASKS
            for seed in EXPLORATION_SEEDS
        ]
        _write_jsonl(temporary / "perturbation_banks.jsonl", bank_records)
        banks = tuple(
            PerturbationBank.from_record(record, verify_transform=True)
            for record in bank_records
        )
        bank_index = {
            (bank.task.task_fingerprint, bank.exploration_seed): bank
            for bank in banks
        }
        records = [
            run_search(
                provider=provider,
                task=task,
                snapshot=snapshots[provider],
                bank=bank_index[(task.task_fingerprint, seed)],
                method=method,
            )
            for provider in FROZEN_SOURCES
            for task in DEV_TASKS
            for seed in EXPLORATION_SEEDS
            for method in METHODS
        ]
        _write_jsonl(temporary / "search_records.jsonl", records)
        summary = _aggregate(
            records=records,
            banks=banks,
            snapshots=snapshots,
            seed_plan_evidence=seed_plan_evidence,
            source_validation=source_validation,
        )
        _write_json(temporary / "summary.json", summary)
        files = {}
        for filename in (
            "anthropic_proposal_rows.jsonl",
            "openai_proposal_rows.jsonl",
            "perturbation_banks.jsonl",
            "search_records.jsonl",
            "summary.json",
        ):
            path = temporary / filename
            files[filename] = _file_metadata(
                path,
                records=len(_read_jsonl(path)) if path.suffix == ".jsonl" else None,
            )
        manifest_payload = {
            "artifact_role": "offline_source_ablation_development_evidence",
            "files": files,
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "status": "COMPLETE",
        }
        _write_json(
            temporary / "manifest.json",
            {
                **manifest_payload,
                "deterministic_digest": _sha256_json(manifest_payload),
            },
        )
        validated_summary = validate_artifact(
            temporary,
            require_replay_match=True,
            verify_bank_transform=True,
        )
        os.replace(temporary, output_dir)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return validated_summary


def run_experiment(
    *,
    anthropic_dir: Path,
    openai_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    if any(os.environ.get(name) for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")):
        raise RuntimeError(
            "offline ablation requires ANTHROPIC_API_KEY and OPENAI_API_KEY unset"
        )
    with _deny_network():
        return _run_experiment_offline(
            anthropic_dir=anthropic_dir,
            openai_dir=openai_dir,
            output_dir=output_dir,
        )


def _fake_snapshot(score_offset: int) -> ProposalSnapshot:
    rows: list[ProposalRow] = []
    for task in DEV_TASKS:
        for state in _nonterminal_states(task):
            actions = task.legal_actions(state)
            scores = tuple(
                int(
                    max(
                        0,
                        min(
                            1000,
                            700
                            - abs(action.evaluate() - task.target) * 20
                            + score_offset
                            + index,
                        ),
                    )
                )
                for index, action in enumerate(actions)
            )
            rows.append(
                ProposalRow(
                    task_fingerprint=task.task_fingerprint,
                    state=state,
                    actions=actions,
                    raw_scores=scores,
                    prior_logp=_normalization(scores),
                    provider_result={"fake": True},
                )
            )
    return ProposalSnapshot(tuple(rows))


def _run_self_test() -> None:
    first = _fake_snapshot(0)
    second = _fake_snapshot(1)
    if first.behavior_digest == second.behavior_digest:
        raise AssertionError("fake snapshots should differ")
    seeds = (7, 8)
    seed_plan, evidence = _build_seed_plan(DEV_TASKS, seeds)
    if evidence["entries"] != len(DEV_TASKS) * 2 * 64:
        raise AssertionError("self-test seed plan coverage mismatch")
    records: list[dict[str, Any]] = []
    for task in DEV_TASKS:
        bank_record = _build_bank_record(task, seeds[0], seed_plan)
        bank = PerturbationBank.from_record(bank_record, verify_transform=True)
        for method in METHODS:
            context_snapshot = first
            provider = "anthropic"
            record = run_search(
                provider=provider,
                task=task,
                snapshot=context_snapshot,
                bank=bank,
                method=method,
                expected_behavior_digest=context_snapshot.behavior_digest,
            )
            replay = run_search(
                provider=provider,
                task=task,
                snapshot=context_snapshot,
                bank=bank,
                method=method,
                expected_behavior_digest=context_snapshot.behavior_digest,
            )
            if record != replay:
                raise AssertionError("self-test matched search is not reproducible")
            if (
                record["usage"]["usage"]["transitions"] != 40
                or record["usage"]["usage"]["verifier_calls"] != 8
                or record["method_state"]["normal_source"][
                    "full_coordinates_read_per_source"
                ]
                != 560
            ):
                raise AssertionError("self-test matched budget did not close")
            _validate_run_record(record, context_snapshot, bank)
            records.append(record)
    if records[0]["deterministic_digest"] == records[1]["deterministic_digest"]:
        raise AssertionError("IID and QMC records should have distinct identities")
    for task in DEV_TASKS:
        task_records = [
            record
            for record in records
            if record["task"]["task_fingerprint"] == task.task_fingerprint
        ]
        pair = _pair_summary(task_records)
        if (
            pair["paired_blocks"] != 1
            or pair["shared_root_state_visit_events"] != THOMPSON_SIMULATIONS
            or pair["vector_digest_mismatches"] != 0
        ):
            raise AssertionError("self-test pair summary did not close")
        try:
            _pair_summary(task_records + [task_records[0]])
        except AssertionError:
            pass
        else:
            raise AssertionError("duplicate pair record was accepted")
    tampered = _build_bank_record(DEV_TASKS[0], seeds[0], seed_plan)
    tampered["states"][0]["iid_uniforms"][0][0] = 0.25
    try:
        PerturbationBank.from_record(tampered, verify_transform=True)
    except ValueError:
        pass
    else:
        raise AssertionError("tampered perturbation bank was accepted")


def _print_summary(summary: Mapping[str, Any]) -> None:
    print(
        _canonical_json(
            {
                "artifact_role": summary["artifact_role"],
                "deterministic_digest": summary["deterministic_digest"],
                "pairing_gate": summary["pairing_gate"],
                "paired_results": summary["paired_results"],
            }
        )
    )


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--replay", type=Path)
    mode.add_argument("--self-test", action="store_true")
    parser.add_argument("--anthropic-dir", type=Path)
    parser.add_argument("--openai-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)

    if args.self_test:
        _run_self_test()
        print("countdown Thompson source ablation self-test: PASS")
        return
    if args.replay is not None:
        if any(
            os.environ.get(name) for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")
        ):
            raise RuntimeError("offline replay requires provider credentials unset")
        with _deny_network():
            summary = validate_artifact(args.replay, require_replay_match=True)
        _print_summary(summary)
        return
    if (
        not args.run
        or args.anthropic_dir is None
        or args.openai_dir is None
        or args.output_dir is None
    ):
        parser.error(
            "--run requires --anthropic-dir, --openai-dir, and --output-dir"
        )
    summary = run_experiment(
        anthropic_dir=args.anthropic_dir,
        openai_dir=args.openai_dir,
        output_dir=args.output_dir,
    )
    _print_summary(summary)


if __name__ == "__main__":
    main()
