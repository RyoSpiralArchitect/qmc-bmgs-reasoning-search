#!/usr/bin/env python3
"""Matched Role-Lock benchmark harness for :mod:`qmc_bmgs.policy`.

The prototype is intentionally imported unchanged.  This harness isolates one
factor at a time:

    iid_global_no_prune
    sobol_global_no_prune
    iid_embedding_no_prune
    sobol_random_size_matched_no_prune
    sobol_embedding_no_prune
    sobol_misleading_no_prune
    sobol_embedding_prune

Greedy and top-p best-of-N anchors are included separately.  Candidate tail
sampling is disabled so candidate IDs/order are identical across exploration
seeds and methods.  Semantic routing uses a uniform cluster distribution, so
the random null only needs exact cluster-size matching; LM cluster mass is
still measured and reported.

The controlled Role-Lock task is terminal-only.  Correct reasoning moves are
low-prior actions and, in the aligned condition, form singleton embedding
clusters.  A matched random partition and an explicitly misleading partition
separate useful alignment from generic forced diversity.

Primary budget is logical LM prefix evaluations, not simulations.  Full-prefix
token work, physical forwards, verifier calls, edge selections, and wall time
are also recorded.  Every budget checkpoint starts from a fresh policy.

Examples
--------

    python -m qmc_bmgs.benchmarks.role_lock --self-test
    python -m qmc_bmgs.benchmarks.role_lock --smoke
    python -m qmc_bmgs.benchmarks.role_lock --seeds 32 --budgets 32,64,128,256
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable, Optional, Sequence

import torch
import torch.nn as nn

from qmc_bmgs.policy import (
    NodeData,
    QMCBMGSConfig,
    QMCBMGSReasoningPolicy,
    SearchTrace,
    Transition,
)
from qmc_bmgs.records import canonical_record_digest


SCHEMA_VERSION = "qmc-bmgs-bench/v1"
ACTION_IDS = tuple(range(1, 11))  # EOS + nine nonterminal moves
MOVE_IDS = tuple(range(2, 11))
TARGET_MOVES = (2, 3, 4)  # PROBE, DERIVE, COMMIT
NULL_MOVES = (8, 9, 10)


@dataclass(frozen=True)
class VariantSpec:
    name: str
    sampler: str  # iid | sobol
    strata: str  # none | embedding | random_size_matched | misleading
    pruning: bool


POLICY_VARIANTS = (
    VariantSpec("iid_global_no_prune", "iid", "none", False),
    VariantSpec("sobol_global_no_prune", "sobol", "none", False),
    VariantSpec("iid_embedding_no_prune", "iid", "embedding", False),
    VariantSpec(
        "sobol_random_size_matched_no_prune",
        "sobol",
        "random_size_matched",
        False,
    ),
    VariantSpec("sobol_embedding_no_prune", "sobol", "embedding", False),
    VariantSpec("sobol_misleading_no_prune", "sobol", "misleading", False),
    VariantSpec("sobol_embedding_prune", "sobol", "embedding", True),
)


@dataclass(frozen=True)
class SeedPlan:
    model_seed: int = 7
    task_seed: int = 0
    candidate_seed: int = 101
    exploration_seed: int = 0
    partition_seed: int = 0
    diagnostic_seed: int = 313


@dataclass(frozen=True)
class RoleLockTask:
    depth: int
    reward: float = 5.0

    def __post_init__(self) -> None:
        if self.depth not in (2, 3, 4):
            raise ValueError("Role-Lock depth must be 2, 3, or 4")

    @property
    def task_id(self) -> str:
        return f"role_lock_d{self.depth}"

    @property
    def root(self) -> tuple[int, ...]:
        return (0,)

    @property
    def target(self) -> tuple[int, ...]:
        return TARGET_MOVES[: self.depth - 1] + (1,)

    @property
    def target_move_set(self) -> frozenset[int]:
        return frozenset(self.target[:-1])

    @property
    def misleading_singletons(self) -> tuple[int, ...]:
        return NULL_MOVES[: self.depth - 1]

    @property
    def max_unique_prefix_nodes(self) -> int:
        # States are evaluated before each of ``depth`` actions; terminal leaves
        # themselves are scored by the verifier rather than expanded as LM nodes.
        return sum(10**level for level in range(self.depth))

    def score(self, token_ids: Sequence[int]) -> float:
        generated = tuple(int(x) for x in token_ids[len(self.root) :])
        return self.reward if generated == self.target else 0.0

    def is_success(self, generated: Sequence[int]) -> bool:
        return tuple(int(x) for x in generated) == self.target

    def oracle_action(self, state_key: tuple[int, ...]) -> Optional[int]:
        if state_key[: len(self.root)] != self.root:
            return None
        generated = state_key[len(self.root) :]
        if generated != self.target[: len(generated)]:
            return None
        if len(generated) >= len(self.target):
            return None
        return int(self.target[len(generated)])


class RoleLockTokenizer:
    pieces = (
        "<bos>",
        "<eos>",
        "PROBE",
        "DERIVE",
        "COMMIT",
        "LURE0",
        "LURE1",
        "LURE2",
        "NULL0",
        "NULL1",
        "NULL2",
    )
    bos_token_id = 0
    eos_token_id = 1

    def decode(self, ids: Iterable[int], **_: Any) -> str:
        return " ".join(self.pieces[int(i)] for i in ids)


class RoleLockLM(nn.Module):
    """Deterministic LM whose logits and clustering embeddings are separable."""

    def __init__(self, task: RoleLockTask, model_seed: int = 7) -> None:
        super().__init__()
        del model_seed  # reserved in the benchmark seed contract
        self.task = task
        self.embedding = nn.Embedding(len(RoleLockTokenizer.pieces), 5)
        self._initialize_embeddings()

    def _initialize_embeddings(self) -> None:
        # Background contains EOS/lures/nulls.  Each correct reasoning move is
        # an orthogonal singleton up to the selected task depth.
        background = torch.tensor([1.0, 0.0, 0.0, 0.0, 0.0])
        singleton_axes = (
            torch.tensor([0.0, 1.0, 0.0, 0.0, 0.0]),
            torch.tensor([0.0, 0.0, 1.0, 0.0, 0.0]),
            torch.tensor([0.0, 0.0, 0.0, 1.0, 0.0]),
        )
        with torch.no_grad():
            self.embedding.weight.copy_(background.repeat(11, 1))
            self.embedding.weight[0] = torch.tensor([0.0, 0.0, 0.0, 0.0, 1.0])
            for token_id, axis in zip(self.task.target[:-1], singleton_axes):
                self.embedding.weight[token_id] = axis

    def get_input_embeddings(self) -> nn.Embedding:
        return self.embedding

    def _next_logits(self, prefix: tuple[int, ...]) -> torch.Tensor:
        logits = torch.full((11,), -30.0, dtype=torch.float32)
        generated = prefix[1:]
        correct_so_far = generated == self.task.target[: len(generated)]

        if len(generated) >= len(self.task.target):
            logits[1] = 3.0
            logits[2:] = -0.5
            return logits

        if not correct_so_far:
            logits[1] = 3.0
            logits[2:] = -0.5
            return logits

        required = self.task.target[len(generated)]
        if required == 1:
            logits[1] = 3.0
            logits[2:] = -0.5
            return logits

        logits[1] = -0.8
        logits[2:5] = -0.6
        stage = len(generated)
        logits[5:8] = 0.4
        logits[5 + min(stage, 2)] = 2.0
        logits[8:11] = -1.0
        logits[required] = -0.2
        return logits

    def forward(self, input_ids: torch.Tensor, use_cache: bool = False) -> Any:
        del use_cache
        batch, length = input_ids.shape
        logits = torch.empty(batch, length, 11, device=input_ids.device)
        for batch_index in range(batch):
            row = tuple(int(x) for x in input_ids[batch_index].tolist())
            for position in range(length):
                prefix = row[: position + 1]
                logits[batch_index, position] = self._next_logits(prefix).to(
                    input_ids.device
                )
        return SimpleNamespace(logits=logits)


class IIDEngine:
    """SobolEngine-compatible, node-local IID uniform source."""

    def __init__(self, dimension: int, seed: int) -> None:
        self.dimension = int(dimension)
        self.generator = torch.Generator(device="cpu").manual_seed(int(seed))
        self.last_draw: Optional[torch.Tensor] = None

    def draw(self, n: int) -> torch.Tensor:
        result = torch.rand(
            int(n), self.dimension, generator=self.generator, dtype=torch.float32
        )
        self.last_draw = result.detach().clone()
        return result


class RecordingEngine:
    """Record the last point without consuming an additional RNG draw."""

    def __init__(self, engine: Any) -> None:
        self.engine = engine
        self.last_draw: Optional[torch.Tensor] = None

    def draw(self, n: int) -> torch.Tensor:
        result = self.engine.draw(n)
        self.last_draw = result.detach().clone()
        return result


@dataclass
class RunCounters:
    logical_lm_node_evals: int = 0
    physical_lm_forwards: int = 0
    full_prefix_tokens: int = 0
    cache_hits: int = 0
    verifier_requests: int = 0
    verifier_evaluations: int = 0
    evaluation_only_calls: int = 0
    edge_selections: int = 0
    coverage_route_selections: int = 0
    global_route_selections: int = 0
    simulations_started: int = 0
    simulations_completed: int = 0
    budget_leaf_backups: int = 0
    prune_checks: int = 0
    prune_batches: int = 0
    arms_pruned: int = 0
    oracle_optimal_arms_pruned: int = 0
    candidate_misses: int = 0
    first_success_lm_eval: Optional[int] = None
    best_observed_return: float = 0.0
    random_partition_nodes: int = 0
    random_partition_mass_l1_sum: float = 0.0
    random_partition_changed_fraction_sum: float = 0.0


class CandidateRegistry:
    """Assert candidate identity without sharing mutable search state."""

    def __init__(self) -> None:
        self._fingerprints: dict[tuple[str, tuple[int, ...]], str] = {}

    @staticmethod
    def fingerprint(node: NodeData) -> str:
        payload = {
            "ids": [int(x) for x in node.candidate_ids.tolist()],
            "logp": [round(float(x), 12) for x in node.prior_logp.tolist()],
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def assert_or_register(
        self, task_id: str, state_key: tuple[int, ...], node: NodeData
    ) -> str:
        key = (task_id, state_key)
        fingerprint = self.fingerprint(node)
        expected = self._fingerprints.setdefault(key, fingerprint)
        if fingerprint != expected:
            raise AssertionError(
                f"candidate mismatch for task={task_id}, state={state_key}"
            )
        return fingerprint


def _cluster_mass(prior_logp: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
    masses = []
    for cluster_id in torch.unique(labels, sorted=True).tolist():
        masses.append(torch.exp(torch.logsumexp(prior_logp[labels == cluster_id], 0)))
    result = torch.stack(masses).to(torch.float64)
    return result / result.sum().clamp_min(torch.finfo(torch.float64).tiny)


def _canonicalize_labels(
    labels: torch.Tensor, candidate_ids: torch.Tensor
) -> torch.Tensor:
    descriptions = []
    for old in torch.unique(labels, sorted=True).tolist():
        member_ids = candidate_ids[labels == old]
        descriptions.append(
            (-int(len(member_ids)), int(member_ids.min().item()), int(old))
        )
    descriptions.sort()
    remap = {old: new for new, (_, _, old) in enumerate(descriptions)}
    return torch.tensor([remap[int(x)] for x in labels.tolist()], dtype=torch.long)


def _labels_from_singletons(
    candidate_ids: torch.Tensor, singleton_ids: Sequence[int]
) -> torch.Tensor:
    singleton_set = {int(x) for x in singleton_ids}
    labels = torch.zeros(len(candidate_ids), dtype=torch.long)
    for label, token_id in enumerate(sorted(singleton_set), start=1):
        matches = torch.where(candidate_ids == token_id)[0]
        if len(matches) != 1:
            raise AssertionError(f"singleton token {token_id} missing from candidates")
        labels[int(matches[0])] = label
    return _canonicalize_labels(labels, candidate_ids)


class BenchmarkPolicy(QMCBMGSReasoningPolicy):
    def __init__(
        self,
        model: RoleLockLM,
        tokenizer: RoleLockTokenizer,
        config: QMCBMGSConfig,
        *,
        variant: VariantSpec,
        task: RoleLockTask,
        seeds: SeedPlan,
        registry: CandidateRegistry,
        posterior_sd_scale: float = 1.0,
    ) -> None:
        if not math.isfinite(posterior_sd_scale) or posterior_sd_scale <= 0.0:
            raise ValueError("posterior_sd_scale must be finite and positive")
        self.variant = variant
        self.task = task
        self.seeds = seeds
        self.registry = registry
        self.posterior_sd_scale = float(posterior_sd_scale)
        self.counters = RunCounters()
        self.root_coverage_cluster_counts: dict[int, int] = {}
        self.lm_node_budget = 0
        self.verifier_budget = 0
        self.edge_budget = 0
        self.stop_reason = "not_started"
        self.prune_log: list[dict[str, Any]] = []
        self._partition_singletons = self._select_partition_singletons()
        super().__init__(
            model,
            tokenizer,
            config,
            terminal_reward_fn=self._terminal_verifier,
            leaf_value_fn=self._cutoff_verifier,
        )

    def _select_partition_singletons(self) -> tuple[int, ...]:
        count = self.task.depth - 1
        if self.variant.strata == "misleading":
            return self.task.misleading_singletons
        if self.variant.strata != "random_size_matched":
            return ()

        combinations = [
            combo
            for combo in itertools.combinations(MOVE_IDS, count)
            if frozenset(combo) != self.task.target_move_set
        ]
        generator = torch.Generator().manual_seed(self.seeds.partition_seed)
        index = int(
            torch.randint(0, len(combinations), (1,), generator=generator).item()
        )
        return tuple(int(x) for x in combinations[index])

    def _state_seed(self, state_key: tuple[int, ...], salt: int = 0) -> int:
        # Candidate construction and exploration have independent seed families.
        seed = self.seeds.candidate_seed if salt == 11 else self.seeds.exploration_seed
        payload = (str(seed) + ":" + repr(state_key) + ":" + str(salt)).encode()
        digest = hashlib.blake2b(payload, digest_size=8).digest()
        return int.from_bytes(digest, "little") % (2**31 - 1)

    @torch.inference_mode()
    def _next_token_logp(self, state_tokens: tuple[int, ...]) -> torch.Tensor:
        self.counters.logical_lm_node_evals += 1
        self.counters.physical_lm_forwards += 1
        self.counters.full_prefix_tokens += len(state_tokens)
        return super()._next_token_logp(state_tokens)

    def get_or_create_node(self, state_tokens: Sequence[int]) -> NodeData:
        state_key = tuple(int(x) for x in state_tokens)
        existed = state_key in self.nodes
        node = super().get_or_create_node(state_key)
        if existed:
            self.counters.cache_hits += 1
            return node

        embedding_labels = _canonicalize_labels(node.cluster_of, node.candidate_ids)
        node.cluster_of = embedding_labels

        if self.variant.strata == "none":
            node.cluster_of = torch.zeros(node.num_actions, dtype=torch.long)
        elif self.variant.strata in ("random_size_matched", "misleading"):
            target_mass = _cluster_mass(node.prior_logp, embedding_labels)
            replacement = _labels_from_singletons(
                node.candidate_ids, self._partition_singletons
            )
            replacement_mass = _cluster_mass(node.prior_logp, replacement)
            if sorted(torch.bincount(replacement).tolist()) != sorted(
                torch.bincount(embedding_labels).tolist()
            ):
                raise AssertionError(
                    "random/misleading partition changed cluster sizes"
                )
            node.cluster_of = replacement
            if self.variant.strata == "random_size_matched":
                self.counters.random_partition_nodes += 1
                self.counters.random_partition_mass_l1_sum += float(
                    torch.abs(
                        torch.sort(target_mass).values
                        - torch.sort(replacement_mass).values
                    )
                    .sum()
                    .item()
                )
                self.counters.random_partition_changed_fraction_sum += float(
                    (replacement != embedding_labels).to(torch.float64).mean().item()
                )

        node.cluster_of = _canonicalize_labels(node.cluster_of, node.candidate_ids)
        node.cluster_prior_logp = self._cluster_log_mass(
            node.prior_logp, node.cluster_of
        )
        node.cluster_visits = torch.zeros(node.num_clusters, dtype=torch.float64)

        dimension = 2 + node.num_actions
        if self.variant.sampler == "iid":
            engine: Any = IIDEngine(dimension, node.node_seed ^ 0x1D1D1D)
        else:
            engine = node.qmc_engine
        node.qmc_engine = RecordingEngine(engine)  # type: ignore[assignment]
        self.registry.assert_or_register(self.task.task_id, state_key, node)

        oracle = self.task.oracle_action(state_key)
        if oracle is not None and not bool((node.candidate_ids == oracle).any()):
            self.counters.candidate_misses += 1
        return node

    def _terminal_verifier(self, tokens: tuple[int, ...]) -> float:
        if self.counters.verifier_requests >= self.verifier_budget:
            return 0.0
        self.counters.verifier_requests += 1
        self.counters.verifier_evaluations += 1
        score = float(self.task.score(tokens))
        self._observe_verifier_score(score)
        return score

    def _cutoff_verifier(self, tokens: tuple[int, ...]) -> float:
        if self.counters.verifier_requests >= self.verifier_budget:
            return 0.0
        self.counters.verifier_requests += 1
        self.counters.verifier_evaluations += 1
        score = float(self.task.score(tokens))
        self._observe_verifier_score(score)
        return score

    def _observe_verifier_score(self, score: float) -> None:
        if not math.isfinite(score):
            raise ValueError("verifier returned NaN/Inf")
        self.counters.best_observed_return = max(
            self.counters.best_observed_return, score
        )
        if score > 0.0 and self.counters.first_success_lm_eval is None:
            self.counters.first_success_lm_eval = self.counters.logical_lm_node_evals

    def _sample_qmc_action_index(self, node: NodeData) -> int:
        self.counters.edge_selections += 1
        index = super()._sample_qmc_action_index(node)
        engine = node.qmc_engine
        last = getattr(engine, "last_draw", None)
        coverage = False
        if last is not None and self.config.semantic_coverage_probability > 0.0:
            coverage = float(last[0, 0].item()) < float(
                self.config.semantic_coverage_probability
            )
        if coverage:
            self.counters.coverage_route_selections += 1
            if self.nodes.get(self.task.root) is node:
                cluster_id = int(node.cluster_of[index].item())
                self.root_coverage_cluster_counts[cluster_id] = (
                    self.root_coverage_cluster_counts.get(cluster_id, 0) + 1
                )
        else:
            self.counters.global_route_selections += 1
        return index

    def _mean_variance(self, n: torch.Tensor, m2: torch.Tensor) -> torch.Tensor:
        """Scale Thompson/probability noise without changing learned returns."""
        base = super()._mean_variance(n, m2)
        return base * (self.posterior_sd_scale**2)

    def apply_bayesian_pruning(
        self,
        node: NodeData,
        state_key: Optional[tuple[int, ...]] = None,
    ) -> list[int]:
        if not self.variant.pruning:
            return []
        before_checks = node.prune_events
        pruned = super().apply_bayesian_pruning(node, state_key)
        if node.prune_events > before_checks:
            self.counters.prune_checks += 1
        if not pruned:
            return []

        self.counters.prune_batches += 1
        self.counters.arms_pruned += len(pruned)
        oracle = self.task.oracle_action(state_key or ())
        oracle_pruned = oracle is not None and oracle in pruned
        if oracle_pruned:
            self.counters.oracle_optimal_arms_pruned += 1
        self.prune_log.append(
            {
                "state": list(state_key or ()),
                "node_visits": node.total_visits,
                "pruned_token_ids": pruned,
                "oracle_action": oracle,
                "oracle_pruned": oracle_pruned,
            }
        )
        return pruned

    def _greedy_action_index(self, node: NodeData) -> int:
        # LM prior is behavior guidance only in this harness.  Readout maximizes
        # learned return; visits and prior are deterministic tie-breakers.
        eligible = node.active & (node.n > 0)
        if not bool(eligible.any()):
            eligible = node.active
        indices = torch.where(eligible)[0]
        best_mean = node.mean[indices].max()
        indices = indices[torch.isclose(node.mean[indices], best_mean)]
        best_visits = node.n[indices].max()
        indices = indices[node.n[indices] == best_visits]
        if len(indices) == 1:
            return int(indices[0].item())
        return int(indices[torch.argmax(node.prior_logp[indices])].item())

    def search_step_budgeted(
        self, root_tokens: Sequence[int]
    ) -> tuple[SearchTrace, str]:
        """One simulation with an exact new-prefix evaluation budget.

        If the frontier cannot be evaluated, the already selected partial path
        is explicitly backed up with the neutral prior value.  No budget is
        exceeded and no partial trajectory is silently lost.
        """
        self.counters.simulations_started += 1
        current_state = tuple(int(x) for x in root_tokens)
        trace = SearchTrace()
        stop_reason = "depth_cutoff"

        for _depth in range(self.task.depth):
            if (
                current_state not in self.nodes
                and self.counters.logical_lm_node_evals >= self.lm_node_budget
            ):
                stop_reason = "lm_budget_frontier"
                self.counters.budget_leaf_backups += 1
                break
            if self.counters.edge_selections >= self.edge_budget:
                stop_reason = "edge_budget"
                break

            node = self.get_or_create_node(current_state)
            action_index = self._sample_qmc_action_index(node)
            action_id = int(node.candidate_ids[action_index].item())
            next_state = current_state + (action_id,)
            terminal = action_id == int(self.eos_token_id)
            reward = self._step_reward(
                node,
                current_state,
                action_index,
                next_state,
                terminal,
            )
            trace.transitions.append(
                Transition(current_state, action_index, action_id, reward, terminal)
            )
            current_state = next_state
            if terminal:
                trace.terminated = True
                trace.leaf_value = 0.0
                stop_reason = "terminal"
                self.counters.simulations_completed += 1
                break
        else:
            if self.counters.verifier_requests < self.verifier_budget:
                trace.leaf_value = float(self._cutoff_verifier(current_state))
            else:
                trace.leaf_value = 0.0
            if not math.isfinite(trace.leaf_value):
                raise ValueError("leaf verifier returned NaN/Inf")
            self.counters.simulations_completed += 1

        next_value = trace.leaf_value
        for transition in reversed(trace.transitions):
            node = self.nodes[transition.state_key]
            target = transition.reward + self.config.gamma * next_value
            if not math.isfinite(target):
                raise ValueError("non-finite Bellman target")
            self._update_action(node, transition.action_index, target)
            self.apply_bayesian_pruning(node, transition.state_key)
            # This updated node becomes the child value in the next reverse step.
            next_value = self._node_value(node)

        return trace, stop_reason

    def run_to_budget(
        self,
        root_tokens: Sequence[int],
        *,
        lm_node_budget: int,
        verifier_budget: Optional[int] = None,
        edge_budget: Optional[int] = None,
    ) -> str:
        self.lm_node_budget = int(lm_node_budget)
        self.verifier_budget = int(verifier_budget or lm_node_budget)
        self.edge_budget = int(edge_budget or lm_node_budget * self.task.depth * 8)
        self.stop_reason = "running"

        while True:
            if self.counters.logical_lm_node_evals >= self.lm_node_budget:
                self.stop_reason = "lm_budget"
                break
            if self.counters.verifier_requests >= self.verifier_budget:
                self.stop_reason = "verifier_budget"
                break
            if self.counters.edge_selections >= self.edge_budget:
                self.stop_reason = "edge_budget"
                break
            _, reason = self.search_step_budgeted(root_tokens)
            if reason in ("lm_budget_frontier", "edge_budget"):
                self.stop_reason = reason
                break
        return self.stop_reason


def benchmark_config(
    task: RoleLockTask,
    variant: VariantSpec,
    seed: int,
    *,
    value_prior_variance: float = 1.0,
    observation_variance: float = 1.0,
) -> QMCBMGSConfig:
    """Build the matched benchmark config.

    The variance keywords are extension points for sensitivity experiments.
    They remain separate because ``value_prior_variance`` applies to unvisited
    arms while ``observation_variance`` floors the empirical target variance
    after an arm has been visited.
    """
    if not math.isfinite(value_prior_variance) or value_prior_variance <= 0.0:
        raise ValueError("value_prior_variance must be finite and positive")
    if not math.isfinite(observation_variance) or observation_variance <= 0.0:
        raise ValueError("observation_variance must be finite and positive")
    coverage = 0.0 if variant.strata == "none" else 0.70
    return QMCBMGSConfig(
        gamma=1.0,
        candidate_top_k=10,
        candidate_top_p=1.0,
        min_candidates=10,
        qmc_tail_candidates=0,
        force_eos_candidate=True,
        semantic_clusters=task.depth,
        kmeans_iterations=8,
        semantic_coverage_probability=coverage,
        semantic_uniform_mix=1.0,
        eos_singleton_cluster=False,
        action_prior_strength=0.10,
        value_prior_mean=0.0,
        value_prior_variance=float(value_prior_variance),
        observation_variance=float(observation_variance),
        uncertainty_floor=1e-4,
        lm_logprob_reward_weight=0.0,
        prune_epsilon=0.01,
        prune_samples=128,
        prune_every_node_visits=4,
        min_action_visits_before_prune=3,
        min_active_actions=max(2, task.depth),
        seed=seed,
    )


def _candidate_path_available(policy: BenchmarkPolicy, task: RoleLockTask) -> bool:
    state = task.root
    for action in task.target:
        node = policy.nodes.get(state)
        if node is None:
            return False
        matches = torch.where(node.candidate_ids == action)[0]
        if len(matches) != 1:
            return False
        if not bool(node.active[int(matches[0])]):
            return False
        state = state + (action,)
    return True


def _search_diagnostics(policy: BenchmarkPolicy, task: RoleLockTask) -> dict[str, Any]:
    total_arms = sum(node.num_actions for node in policy.nodes.values())
    active_arms = sum(int(node.active.sum().item()) for node in policy.nodes.values())
    cluster_pairs_explored = sum(
        int((node.cluster_visits > 0).sum().item()) for node in policy.nodes.values()
    )
    root = policy.nodes.get(task.root)
    if root is None:
        root_active = 0
        root_cluster_entropy = 0.0
        root_min_cluster_visits = 0
        root_candidate_fingerprint = None
    else:
        root_active = int(root.active.sum().item())
        visits = root.cluster_visits.to(torch.float64)
        if float(visits.sum()) > 0.0:
            probability = visits / visits.sum()
            nonzero = probability > 0
            root_cluster_entropy = float(
                -(probability[nonzero] * probability[nonzero].log()).sum().item()
            )
        else:
            root_cluster_entropy = 0.0
        root_min_cluster_visits = int(visits.min().item())
        root_candidate_fingerprint = CandidateRegistry.fingerprint(root)
    root_coverage_counts = [
        int(policy.root_coverage_cluster_counts.get(cluster_id, 0))
        for cluster_id in range(root.num_clusters if root is not None else 0)
    ]
    root_coverage_total = sum(root_coverage_counts)
    if root_coverage_total and root_coverage_counts:
        uniform_share = 1.0 / len(root_coverage_counts)
        root_coverage_max_uniform_deviation = max(
            abs(count / root_coverage_total - uniform_share)
            for count in root_coverage_counts
        )
    else:
        root_coverage_max_uniform_deviation = 0.0
    return {
        "nodes_created": len(policy.nodes),
        "tree_total_arms": total_arms,
        "tree_active_arms": active_arms,
        "root_active_arms": root_active,
        "state_cluster_pairs_explored": cluster_pairs_explored,
        "root_cluster_visit_entropy": root_cluster_entropy,
        "root_min_cluster_visits": root_min_cluster_visits,
        "root_candidate_fingerprint": root_candidate_fingerprint,
        "root_coverage_cluster_counts": root_coverage_counts,
        "root_coverage_max_uniform_deviation": (
            root_coverage_max_uniform_deviation
        ),
        # All ten non-BOS tokens are forced into every Role-Lock node.  Keep the
        # universe guarantee separate from whether the full path was expanded
        # and remains active by this particular run.
        "oracle_candidate_universe_guaranteed": True,
        "oracle_active_path_expanded": _candidate_path_available(policy, task),
    }


def run_policy_variant(
    task: RoleLockTask,
    variant: VariantSpec,
    seeds: SeedPlan,
    budget: int,
    registry: CandidateRegistry,
    verifier_budget_multiplier: float = 8.0,
    *,
    config_override: Optional[QMCBMGSConfig] = None,
    posterior_sd_scale: float = 1.0,
) -> dict[str, Any]:
    tokenizer = RoleLockTokenizer()
    model = RoleLockLM(task, seeds.model_seed)
    config = config_override or benchmark_config(
        task, variant, seeds.exploration_seed
    )
    if int(config.seed) != int(seeds.exploration_seed):
        raise ValueError(
            "config.seed must equal seeds.exploration_seed so the randomization "
            "replicate is auditable"
        )
    policy = BenchmarkPolicy(
        model,
        tokenizer,
        config,
        variant=variant,
        task=task,
        seeds=seeds,
        registry=registry,
        posterior_sd_scale=posterior_sd_scale,
    )

    verifier_limit = max(
        int(budget), int(math.ceil(budget * verifier_budget_multiplier))
    )
    edge_limit = max(
        budget * task.depth * 8,
        verifier_limit * task.depth * 2,
    )
    started = time.perf_counter()
    stop_reason = policy.run_to_budget(
        task.root,
        lm_node_budget=budget,
        verifier_budget=verifier_limit,
        edge_budget=edge_limit,
    )
    wall = time.perf_counter() - started

    readout = policy.best_continuation(task.root, max_new_tokens=task.depth)
    policy.counters.evaluation_only_calls += 1
    readout_return = task.reward if task.is_success(readout) else 0.0
    counters = asdict(policy.counters)
    random_nodes = max(1, policy.counters.random_partition_nodes)
    partition = {
        "singletons": list(policy._partition_singletons),
        "target_overlap": len(
            set(policy._partition_singletons) & set(task.target_move_set)
        ),
        "mean_mass_l1": (
            policy.counters.random_partition_mass_l1_sum / random_nodes
            if policy.counters.random_partition_nodes
            else None
        ),
        "mean_changed_fraction": (
            policy.counters.random_partition_changed_fraction_sum / random_nodes
            if policy.counters.random_partition_nodes
            else None
        ),
    }
    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "record_type": "run_snapshot",
        "paired_group_id": (
            f"{task.task_id}:seed{seeds.exploration_seed}:"
            f"partition{seeds.partition_seed}:b{budget}"
        ),
        "method": {
            "name": variant.name,
            "sampler": variant.sampler,
            "strata": variant.strata,
            "pruning": variant.pruning,
            "readout": "return_mean_then_visits_then_prior",
            "lm_prior_role": "behavior_only",
            "runtime_scope": "all policy variants pay base embedding clustering",
            "posterior_sd_scale": float(posterior_sd_scale),
        },
        "search_config": asdict(config),
        "task": {
            "id": task.task_id,
            "depth": task.depth,
            "target": list(task.target),
            "reward": task.reward,
            "terminal_only": True,
        },
        "seeds": asdict(seeds),
        "budget": {
            "primary": "logical_lm_node_evals",
            "limit": int(budget),
            "verifier_limit": verifier_limit,
            "regime": "lm_primary_with_verifier_guard",
            "task_max_unique_prefix_nodes": task.max_unique_prefix_nodes,
            "stop_reason": stop_reason,
            "overshoot": max(0, policy.counters.logical_lm_node_evals - int(budget)),
        },
        "usage": {
            **counters,
            "wall_time_s": wall,
        },
        "outcome": {
            "readout_token_ids": readout,
            "readout_text": tokenizer.decode(readout),
            "readout_success": task.is_success(readout),
            "readout_return": readout_return,
            "best_observed_success": policy.counters.best_observed_return > 0.0,
            "best_observed_return": policy.counters.best_observed_return,
        },
        "partition": partition,
        "search": {
            **_search_diagnostics(policy, task),
            "prune_log": policy.prune_log,
        },
    }
    record["deterministic_digest"] = canonical_record_digest(record)
    json.dumps(record, allow_nan=False)
    return record


def _sample_top_p(
    logits: torch.Tensor,
    top_p: float,
    generator: torch.Generator,
) -> int:
    probs = torch.softmax(logits.to(torch.float64), dim=-1)
    sorted_probs, sorted_ids = torch.sort(probs, descending=True)
    cumulative_before = sorted_probs.cumsum(0) - sorted_probs
    keep = cumulative_before < top_p
    kept_probs = sorted_probs[keep]
    kept_ids = sorted_ids[keep]
    kept_probs /= kept_probs.sum()
    local = int(torch.multinomial(kept_probs, 1, generator=generator).item())
    return int(kept_ids[local].item())


def run_prior_anchor(
    task: RoleLockTask,
    method: str,
    seeds: SeedPlan,
    budget: int,
    top_p: float = 0.95,
) -> dict[str, Any]:
    if method not in ("greedy_prior", "top_p_best_of_n"):
        raise ValueError(method)
    tokenizer = RoleLockTokenizer()
    model = RoleLockLM(task, seeds.model_seed)
    generator = torch.Generator().manual_seed(seeds.exploration_seed)
    calls = tokens = verifier = completed = 0
    best_sequence: list[int] = []
    best_return = -math.inf
    first_success: Optional[int] = None
    started = time.perf_counter()

    max_rollouts = 1 if method == "greedy_prior" else max(1, budget)
    for _ in range(max_rollouts):
        if calls >= budget:
            break
        state = list(task.root)
        generated: list[int] = []
        for _depth in range(task.depth):
            if calls >= budget:
                break
            input_ids = torch.tensor([state], dtype=torch.long)
            logits = model(input_ids=input_ids, use_cache=False).logits[0, -1]
            calls += 1
            tokens += len(state)
            if method == "greedy_prior":
                action = int(torch.argmax(logits).item())
            else:
                action = _sample_top_p(logits, top_p, generator)
            generated.append(action)
            state.append(action)
            if action == tokenizer.eos_token_id:
                break
        if not generated:
            break
        verifier += 1
        completed += 1
        score = task.reward if task.is_success(generated) else 0.0
        if score > best_return:
            best_return = score
            best_sequence = list(generated)
        if score > 0.0 and first_success is None:
            first_success = calls
        if method == "greedy_prior":
            break

    wall = time.perf_counter() - started
    if best_return == -math.inf:
        best_return = 0.0
    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "record_type": "run_snapshot",
        "paired_group_id": (
            f"{task.task_id}:seed{seeds.exploration_seed}:"
            f"partition{seeds.partition_seed}:b{budget}"
        ),
        "method": {
            "name": method,
            "sampler": "argmax" if method == "greedy_prior" else "categorical",
            "strata": "none",
            "pruning": False,
            "readout": "single" if method == "greedy_prior" else "best_observed",
            "lm_prior_role": "objective",
            "runtime_scope": "prior-only anchor",
        },
        "task": {
            "id": task.task_id,
            "depth": task.depth,
            "target": list(task.target),
            "reward": task.reward,
            "terminal_only": True,
        },
        "seeds": asdict(seeds),
        "budget": {
            "primary": "logical_lm_node_evals",
            "limit": int(budget),
            "verifier_limit": int(budget),
            "regime": "lm_primary_prior_anchor",
            "task_max_unique_prefix_nodes": task.max_unique_prefix_nodes,
            "stop_reason": "single_rollout"
            if method == "greedy_prior"
            else "lm_budget",
            "overshoot": max(0, calls - budget),
        },
        "usage": {
            "logical_lm_node_evals": calls,
            "physical_lm_forwards": calls,
            "full_prefix_tokens": tokens,
            "cache_hits": 0,
            "verifier_requests": verifier,
            "verifier_evaluations": verifier,
            "evaluation_only_calls": 1,
            "edge_selections": calls,
            "coverage_route_selections": 0,
            "global_route_selections": calls,
            "simulations_started": completed,
            "simulations_completed": completed,
            "budget_leaf_backups": 0,
            "prune_checks": 0,
            "prune_batches": 0,
            "arms_pruned": 0,
            "oracle_optimal_arms_pruned": 0,
            "candidate_misses": 0,
            "first_success_lm_eval": first_success,
            "best_observed_return": best_return,
            "random_partition_nodes": 0,
            "random_partition_mass_l1_sum": 0.0,
            "random_partition_changed_fraction_sum": 0.0,
            "wall_time_s": wall,
        },
        "outcome": {
            "readout_token_ids": best_sequence,
            "readout_text": tokenizer.decode(best_sequence),
            "readout_success": task.is_success(best_sequence),
            "readout_return": best_return,
            "best_observed_success": best_return > 0.0,
            "best_observed_return": best_return,
        },
        "partition": {
            "singletons": [],
            "target_overlap": 0,
            "mean_mass_l1": None,
            "mean_changed_fraction": None,
        },
        "search": {
            "nodes_created": calls,
            "tree_total_arms": 0,
            "tree_active_arms": 0,
            "root_active_arms": 0,
            "state_cluster_pairs_explored": 0,
            "root_cluster_visit_entropy": 0.0,
            "root_min_cluster_visits": 0,
            "oracle_candidate_universe_guaranteed": True,
            "oracle_active_path_expanded": task.is_success(best_sequence),
            "prune_log": [],
        },
    }
    record["deterministic_digest"] = canonical_record_digest(record)
    json.dumps(record, allow_nan=False)
    return record


def _bootstrap_mean_interval(
    values: Sequence[float], *, seed: int, samples: int = 2000
) -> tuple[float, float]:
    if not values:
        return (0.0, 0.0)
    if len(values) == 1:
        return (float(values[0]), float(values[0]))
    tensor = torch.tensor(values, dtype=torch.float64)
    generator = torch.Generator().manual_seed(seed)
    indices = torch.randint(0, len(values), (samples, len(values)), generator=generator)
    means = tensor[indices].mean(dim=1).sort().values
    low = float(means[int(0.025 * (samples - 1))].item())
    high = float(means[int(0.975 * (samples - 1))].item())
    return low, high


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
    for record in records:
        key = (
            record["task"]["id"],
            record["method"]["name"],
            int(record["budget"]["limit"]),
        )
        groups.setdefault(key, []).append(record)

    cells = []
    for (task_id, method, budget), rows in sorted(groups.items()):
        rows_by_seed: dict[int, list[dict[str, Any]]] = {}
        for row in rows:
            rows_by_seed.setdefault(int(row["seeds"]["exploration_seed"]), []).append(
                row
            )
        successes = [
            statistics.mean(
                float(row["outcome"]["readout_success"]) for row in seed_rows
            )
            for seed_rows in rows_by_seed.values()
        ]
        observed = [
            statistics.mean(
                float(row["outcome"]["best_observed_success"]) for row in seed_rows
            )
            for seed_rows in rows_by_seed.values()
        ]
        calls = [float(row["usage"]["logical_lm_node_evals"]) for row in rows]
        prefix_tokens = [float(row["usage"]["full_prefix_tokens"]) for row in rows]
        verifier = [float(row["usage"]["verifier_requests"]) for row in rows]
        first_hits = [
            row["usage"]["first_success_lm_eval"]
            for row in rows
            if row["usage"]["first_success_lm_eval"] is not None
        ]
        interval_seed = int.from_bytes(
            hashlib.blake2b(
                f"cell:{task_id}:{method}:{budget}".encode(), digest_size=8
            ).digest(),
            "little",
        ) % (2**31 - 1)
        success_low, success_high = _bootstrap_mean_interval(
            successes, seed=interval_seed
        )
        cells.append(
            {
                "task_id": task_id,
                "method": method,
                "budget": budget,
                "run_records": len(rows),
                "exploration_seed_replicates": len(rows_by_seed),
                "readout_success_rate": statistics.mean(successes),
                "readout_success_seed_bootstrap_95": [success_low, success_high],
                "readout_success_seed_sd": (
                    statistics.pstdev(successes) if len(successes) > 1 else 0.0
                ),
                "best_observed_success_rate": statistics.mean(observed),
                "mean_lm_node_evals": statistics.mean(calls),
                "mean_full_prefix_tokens": statistics.mean(prefix_tokens),
                "mean_verifier_requests": statistics.mean(verifier),
                "mean_first_success_lm_eval": (
                    statistics.mean(first_hits) if first_hits else None
                ),
                "oracle_prune_errors": sum(
                    int(row["usage"]["oracle_optimal_arms_pruned"]) for row in rows
                ),
                "mean_random_target_overlap": statistics.mean(
                    float(row["partition"]["target_overlap"]) for row in rows
                ),
            }
        )

    aucs = []
    by_curve: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for cell in cells:
        by_curve.setdefault((cell["task_id"], cell["method"]), []).append(cell)
    for (task_id, method), curve in sorted(by_curve.items()):
        curve.sort(key=lambda x: x["budget"])
        if len(curve) == 1:
            auc = curve[0]["readout_success_rate"]
        else:
            area = 0.0
            for left, right in zip(curve, curve[1:]):
                width = right["budget"] - left["budget"]
                area += (
                    width
                    * (left["readout_success_rate"] + right["readout_success_rate"])
                    / 2.0
                )
            span = curve[-1]["budget"] - curve[0]["budget"]
            auc = area / span if span else curve[-1]["readout_success_rate"]
        aucs.append({"task_id": task_id, "method": method, "success_budget_auc": auc})

    # Paired deltas use exploration seed as the replicate.  Multiple random
    # partitions for the same search seed are averaged before differencing.
    reference_name = "sobol_global_no_prune"
    replicate_values: dict[tuple[str, int, str, int], list[float]] = {}
    for row in records:
        key = (
            row["task"]["id"],
            int(row["budget"]["limit"]),
            row["method"]["name"],
            int(row["seeds"]["exploration_seed"]),
        )
        replicate_values.setdefault(key, []).append(
            float(row["outcome"]["readout_success"])
        )
    collapsed = {key: statistics.mean(value) for key, value in replicate_values.items()}

    paired = []
    methods = sorted({row["method"]["name"] for row in records})
    task_budgets = sorted(
        {(row["task"]["id"], int(row["budget"]["limit"])) for row in records}
    )
    for task_id, budget in task_budgets:
        reference = {
            seed: value
            for (task, cell_budget, method, seed), value in collapsed.items()
            if task == task_id and cell_budget == budget and method == reference_name
        }
        if not reference:
            continue
        for method in methods:
            values = {
                seed: value
                for (
                    task,
                    cell_budget,
                    candidate_method,
                    seed,
                ), value in collapsed.items()
                if task == task_id
                and cell_budget == budget
                and candidate_method == method
            }
            common = sorted(set(reference) & set(values))
            if not common:
                continue
            deltas = [values[seed] - reference[seed] for seed in common]
            bootstrap_seed = int.from_bytes(
                hashlib.blake2b(
                    f"{task_id}:{budget}:{method}".encode(), digest_size=8
                ).digest(),
                "little",
            ) % (2**31 - 1)
            low, high = _bootstrap_mean_interval(deltas, seed=bootstrap_seed)
            paired.append(
                {
                    "task_id": task_id,
                    "budget": budget,
                    "method": method,
                    "reference": reference_name,
                    "paired_seeds": len(common),
                    "mean_success_delta": statistics.mean(deltas),
                    "bootstrap_95": [low, high],
                }
            )

    return {
        "schema_version": SCHEMA_VERSION,
        "record_type": "summary",
        "records": len(records),
        "cells": cells,
        "curves": aucs,
        "paired_deltas": paired,
    }


def run_benchmark(
    *,
    depths: Sequence[int],
    seeds_count: int,
    budgets: Sequence[int],
    include_anchors: bool = True,
    random_partition_replicates: int = 1,
    verifier_budget_multiplier: float = 8.0,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    registry = CandidateRegistry()
    for depth in depths:
        task = RoleLockTask(int(depth))
        for budget in budgets:
            for seed in range(seeds_count):
                seeds = SeedPlan(
                    exploration_seed=seed,
                    partition_seed=10_000,
                    task_seed=depth,
                )
                if include_anchors:
                    records.append(
                        run_prior_anchor(task, "greedy_prior", seeds, int(budget))
                    )
                    records.append(
                        run_prior_anchor(task, "top_p_best_of_n", seeds, int(budget))
                    )
                for variant in POLICY_VARIANTS:
                    partition_seeds = (
                        range(10_000, 10_000 + random_partition_replicates)
                        if variant.strata == "random_size_matched"
                        else (10_000,)
                    )
                    for partition_seed in partition_seeds:
                        variant_seeds = SeedPlan(
                            model_seed=seeds.model_seed,
                            task_seed=seeds.task_seed,
                            candidate_seed=seeds.candidate_seed,
                            exploration_seed=seeds.exploration_seed,
                            partition_seed=int(partition_seed),
                            diagnostic_seed=seeds.diagnostic_seed,
                        )
                        records.append(
                            run_policy_variant(
                                task,
                                variant,
                                variant_seeds,
                                int(budget),
                                registry,
                                verifier_budget_multiplier,
                            )
                        )
    return records


def _write_jsonl(path: Path, records: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _run_self_test() -> None:
    task = RoleLockTask(3)
    registry = CandidateRegistry()
    seeds = SeedPlan(exploration_seed=5, partition_seed=1005, task_seed=3)

    sobol = next(v for v in POLICY_VARIANTS if v.name == "sobol_embedding_no_prune")
    first = run_policy_variant(task, sobol, seeds, 32, registry)
    second = run_policy_variant(task, sobol, seeds, 32, registry)
    assert first["deterministic_digest"] == second["deterministic_digest"]
    assert first["budget"]["overshoot"] == 0
    assert first["usage"]["logical_lm_node_evals"] <= 32
    assert (
        first["usage"]["physical_lm_forwards"]
        == first["usage"]["logical_lm_node_evals"]
    )
    assert (
        first["usage"]["full_prefix_tokens"] >= first["usage"]["logical_lm_node_evals"]
    )
    assert first["usage"]["verifier_requests"] <= first["budget"]["verifier_limit"]
    assert first["search"]["oracle_candidate_universe_guaranteed"] is True

    random_variant = next(
        v for v in POLICY_VARIANTS if v.name == "sobol_random_size_matched_no_prune"
    )
    random_record = run_policy_variant(task, random_variant, seeds, 32, registry)
    assert len(random_record["partition"]["singletons"]) == task.depth - 1
    assert random_record["partition"]["mean_changed_fraction"] is not None
    assert random_record["partition"]["mean_changed_fraction"] > 0.0

    no_strata = next(v for v in POLICY_VARIANTS if v.name == "sobol_global_no_prune")
    no_strata_record = run_policy_variant(task, no_strata, seeds, 16, registry)
    assert no_strata_record["usage"]["coverage_route_selections"] == 0
    assert no_strata_record["usage"]["prune_checks"] == 0

    prune_variant = next(
        v for v in POLICY_VARIANTS if v.name == "sobol_embedding_prune"
    )
    prune_record = run_policy_variant(
        RoleLockTask(2), prune_variant, seeds, 128, registry
    )
    assert prune_record["usage"]["prune_batches"] > 0
    assert prune_record["usage"]["arms_pruned"] > 0
    assert prune_record["usage"]["oracle_optimal_arms_pruned"] == 0

    policy = BenchmarkPolicy(
        RoleLockLM(task),
        RoleLockTokenizer(),
        benchmark_config(task, sobol, seeds.exploration_seed),
        variant=sobol,
        task=task,
        seeds=seeds,
        registry=registry,
    )
    try:
        policy._observe_verifier_score(float("nan"))
    except ValueError:
        pass
    else:
        raise AssertionError("NaN verifier result must be rejected")

    anchor = run_prior_anchor(task, "greedy_prior", seeds, 32)
    assert not anchor["outcome"]["readout_success"]
    assert anchor["usage"]["logical_lm_node_evals"] <= task.depth

    summary = summarize([first, random_record, no_strata_record, anchor])
    json.dumps(summary, allow_nan=False)
    print("benchmark self-test: PASS")
    print(
        "sample:",
        {
            "method": first["method"]["name"],
            "lm_evals": first["usage"]["logical_lm_node_evals"],
            "prefix_tokens": first["usage"]["full_prefix_tokens"],
            "verifier_calls": first["usage"]["verifier_requests"],
            "success": first["outcome"]["readout_success"],
        },
    )


def _parse_csv_ints(value: str) -> list[int]:
    result = [int(part.strip()) for part in value.split(",") if part.strip()]
    if not result or any(item <= 0 for item in result):
        raise argparse.ArgumentTypeError("expected comma-separated positive integers")
    return result


def main() -> None:
    output_dir = Path.cwd() / "artifacts" / "work"
    default_runs = output_dir / "qmc_bmgs_benchmark_runs.jsonl"
    default_summary = output_dir / "qmc_bmgs_benchmark_summary.json"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--depths", default="3,4")
    parser.add_argument("--seeds", type=int, default=32)
    parser.add_argument("--budgets", default="32,64,128,256")
    parser.add_argument("--runs-jsonl", type=Path, default=default_runs)
    parser.add_argument("--summary-json", type=Path, default=default_summary)
    parser.add_argument("--no-anchors", action="store_true")
    parser.add_argument("--random-partition-replicates", type=int, default=4)
    parser.add_argument("--verifier-budget-multiplier", type=float, default=8.0)
    args = parser.parse_args()

    if args.self_test:
        _run_self_test()
        return

    if args.seeds < 1:
        parser.error("--seeds must be positive")
    if args.random_partition_replicates < 1:
        parser.error("--random-partition-replicates must be positive")
    if args.verifier_budget_multiplier < 1.0:
        parser.error("--verifier-budget-multiplier must be at least 1.0")

    depths = _parse_csv_ints(args.depths)
    budgets = _parse_csv_ints(args.budgets)
    seeds_count = args.seeds
    if args.smoke:
        depths = [3]
        budgets = [24, 48, 96]
        seeds_count = 4
        args.random_partition_replicates = 2
        args.verifier_budget_multiplier = 4.0

    records = run_benchmark(
        depths=depths,
        seeds_count=seeds_count,
        budgets=budgets,
        include_anchors=not args.no_anchors,
        random_partition_replicates=args.random_partition_replicates,
        verifier_budget_multiplier=args.verifier_budget_multiplier,
    )
    summary = summarize(records)
    _write_jsonl(args.runs_jsonl, records)
    _write_json(args.summary_json, summary)
    print(
        json.dumps(
            {
                "runs": len(records),
                "runs_jsonl": str(args.runs_jsonl),
                "summary_json": str(args.summary_json),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
