#!/usr/bin/env python3
"""QMC-BMGS semantic token-search prototype.

This is deliberately one file: candidate construction, semantic clustering,
semantic-stratified QMC Thompson sampling, reverse Bellman backup,
probability-of-optimality diagnostics/pruning, inspection helpers, and an
offline toy demo all live here.

Core interpretation
-------------------
For an exact token prefix ``s``:

1. Build a bounded candidate set from the LM prior (top-p/top-k plus a small
   QMC tail sample).
2. Cluster candidate token embeddings.  A cluster is an exploration stratum;
   only tokens are value-bearing action arms.
3. Use a node-local scrambled Sobol stream for posterior perturbations and a
   controlled amount of semantic-stratified coverage:

       Q_tilde_a = mu_a + sigma_a Phi^-1(u_a) + LM_prior_a
       action = global_argmax(Q_tilde)                    # most visits
       action = cluster_stratified_argmax(Q_tilde, u_c)  # coverage visits

4. Back up a trajectory in reverse order with a Bellman-style target.
5. Report a Sobol estimate of ``P(action is optimal | data)``.  For hard
   pruning, use the safer analytic upper bound ``P(Q_a >= Q_current_best)`` and
   mark only sufficiently visited, sufficiently implausible actions inactive.

Important claim boundary
------------------------
``sigma2`` below is an uncertainty proxy for a non-stationary TD target, not an
exact Bayesian posterior variance.  The probability-of-optimality calculation
is therefore a useful pruning heuristic, not a calibrated theorem.  Replacing
the online moments with an NIG model, bootstrap ensemble, or learned posterior
does not require changing the rest of the search loop.

The state key is the exact token prefix, so this prototype is a tree stored in
a flat dictionary.  It does not claim semantic state merging.  Nodes are never
physically deleted during search; pruning only changes ``active`` masks.

Hugging Face usage
------------------

    policy = QMCBMGSReasoningPolicy(
        model,
        tokenizer,
        config=QMCBMGSConfig(),
        step_reward_fn=my_step_reward,       # optional
        terminal_reward_fn=my_verifier,      # strongly recommended
        leaf_value_fn=my_value_model,         # optional
    )
    policy.run_search(prompt_ids, simulations=128, max_depth=32)
    answer_ids = policy.best_continuation(prompt_ids, max_new_tokens=32)

Run ``python -m qmc_bmgs.policy --self-test`` for a download-free demo.

Prototype trade-off: every newly created prefix is evaluated once in full.
Production code should add a bounded/shared-prefix KV-cache layer rather than
retaining an unbounded KV cache in every node.
"""

from __future__ import annotations

import argparse
import hashlib
import math
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Callable, Iterable, Optional, Sequence

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.quasirandom import SobolEngine


TokenSeq = Sequence[int]
StepRewardFn = Callable[[tuple[int, ...], int, tuple[int, ...], bool], float]
TerminalRewardFn = Callable[[tuple[int, ...]], float]
LeafValueFn = Callable[[tuple[int, ...]], float]


@dataclass
class QMCBMGSConfig:
    """Search knobs with conservative defaults for a prototype."""

    gamma: float = 0.99

    # Candidate construction.  Total candidates are roughly top_k + tail.
    candidate_top_k: int = 48
    candidate_top_p: float = 0.95
    min_candidates: int = 8
    qmc_tail_candidates: int = 8
    force_eos_candidate: bool = True

    # Option 3: semantic partition of candidate-token embedding space.  The
    # clusters stratify exploration only; they do not share learned Q values.
    semantic_clusters: int = 8
    kmeans_iterations: int = 8
    semantic_coverage_probability: float = 0.25
    semantic_uniform_mix: float = 0.50
    eos_singleton_cluster: bool = True

    # LM log-prob is a proposal/selection prior, not the learned return.
    action_prior_strength: float = 0.15

    # Online posterior proxy.
    value_prior_mean: float = 0.0
    value_prior_variance: float = 1.0
    observation_variance: float = 1.0
    uncertainty_floor: float = 1e-4

    # Optional LM-log-prob reward.  Keep zero when using an external verifier.
    lm_logprob_reward_weight: float = 0.0

    # QMC P(optimal) is diagnostic; hard pruning uses a pairwise analytic upper.
    prune_epsilon: float = 0.01
    prune_samples: int = 256
    prune_every_node_visits: int = 4
    min_action_visits_before_prune: int = 3
    min_active_actions: int = 4

    seed: int = 17
    normal_icdf_clip: float = 1e-6

    def __post_init__(self) -> None:
        if not 0.0 <= self.gamma <= 1.0:
            raise ValueError("gamma must be in [0, 1]")
        if self.candidate_top_k < 1:
            raise ValueError("candidate_top_k must be positive")
        if not 0.0 < self.candidate_top_p <= 1.0:
            raise ValueError("candidate_top_p must be in (0, 1]")
        if self.min_candidates < 1:
            raise ValueError("min_candidates must be positive")
        if self.qmc_tail_candidates < 0:
            raise ValueError("qmc_tail_candidates must be non-negative")
        if self.semantic_clusters < 1:
            raise ValueError("semantic_clusters must be positive")
        if not 0.0 <= self.semantic_coverage_probability <= 1.0:
            raise ValueError("semantic_coverage_probability must be in [0, 1]")
        if not 0.0 <= self.semantic_uniform_mix <= 1.0:
            raise ValueError("semantic_uniform_mix must be in [0, 1]")
        if self.value_prior_variance <= 0.0:
            raise ValueError("value_prior_variance must be positive")
        if self.observation_variance <= 0.0:
            raise ValueError("observation_variance must be positive")
        if self.uncertainty_floor <= 0.0:
            raise ValueError("uncertainty_floor must be positive")
        if not 0.0 <= self.prune_epsilon < 1.0:
            raise ValueError("prune_epsilon must be in [0, 1)")
        if self.prune_samples < 2:
            raise ValueError("prune_samples must be at least 2")
        if self.prune_every_node_visits < 1:
            raise ValueError("prune_every_node_visits must be positive")
        if self.min_action_visits_before_prune < 1:
            raise ValueError("min_action_visits_before_prune must be positive")
        if self.min_active_actions < 1:
            raise ValueError("min_active_actions must be positive")
        if not 0.0 < self.normal_icdf_clip < 0.5:
            raise ValueError("normal_icdf_clip must be in (0, 0.5)")


@dataclass
class NodeData:
    """Bandit state for one exact prefix; all statistics live on CPU."""

    candidate_ids: torch.Tensor  # [A], long
    prior_logp: torch.Tensor  # [A], float
    cluster_of: torch.Tensor  # [A], long in [0, C)
    cluster_prior_logp: torch.Tensor  # [C], float
    node_seed: int
    qmc_engine: SobolEngine

    n: torch.Tensor  # [A], float64
    mean: torch.Tensor  # [A], float64
    m2: torch.Tensor  # [A], float64
    active: torch.Tensor  # [A], bool

    cluster_visits: torch.Tensor  # [C], float64; routing diagnostic only

    last_p_opt: torch.Tensor  # [A], float64
    last_pairwise_upper: torch.Tensor  # [A], float64
    qmc_draws: int = 0
    prune_events: int = 0

    @property
    def num_actions(self) -> int:
        return int(self.candidate_ids.numel())

    @property
    def num_clusters(self) -> int:
        return int(self.cluster_prior_logp.numel())

    @property
    def total_visits(self) -> int:
        return int(self.n.sum().item())


@dataclass
class Transition:
    state_key: tuple[int, ...]
    action_index: int
    action_id: int
    reward: float
    terminal: bool


@dataclass
class SearchTrace:
    transitions: list[Transition] = field(default_factory=list)
    leaf_value: float = 0.0
    terminated: bool = False

    @property
    def token_ids(self) -> list[int]:
        return [t.action_id for t in self.transitions]


class QMCBMGSReasoningPolicy:
    """Semantic-clustered, QMC-Thompson token tree search."""

    def __init__(
        self,
        model: Any,
        tokenizer: Any,
        config: Optional[QMCBMGSConfig] = None,
        *,
        step_reward_fn: Optional[StepRewardFn] = None,
        terminal_reward_fn: Optional[TerminalRewardFn] = None,
        leaf_value_fn: Optional[LeafValueFn] = None,
    ) -> None:
        self.model = model
        self.tokenizer = tokenizer
        self.config = config or QMCBMGSConfig()
        self.step_reward_fn = step_reward_fn
        self.terminal_reward_fn = terminal_reward_fn
        self.leaf_value_fn = leaf_value_fn

        self.nodes: dict[tuple[int, ...], NodeData] = {}
        # Compatibility with the original sketch, without claiming DAG merging.
        self.graph = self.nodes

        embeddings = self.model.get_input_embeddings()
        if embeddings is None or not hasattr(embeddings, "weight"):
            raise TypeError("model.get_input_embeddings().weight is required")
        self.input_embeddings = embeddings
        self.model_device = embeddings.weight.device
        self.eos_token_id = getattr(tokenizer, "eos_token_id", None)

        if hasattr(self.model, "eval"):
            self.model.eval()

    # ------------------------------------------------------------------
    # Stable QMC utilities
    # ------------------------------------------------------------------

    def _state_seed(self, state_key: tuple[int, ...], salt: int = 0) -> int:
        payload = (
            str(self.config.seed) + ":" + repr(state_key) + ":" + str(salt)
        ).encode()
        digest = hashlib.blake2b(payload, digest_size=8).digest()
        # SobolEngine accepts a signed 32-bit-ish seed across torch versions.
        return int.from_bytes(digest, "little") % (2**31 - 1)

    def _normal_icdf(self, u: torch.Tensor) -> torch.Tensor:
        clip = self.config.normal_icdf_clip
        u = u.to(dtype=torch.float64).clamp(clip, 1.0 - clip)
        # Phi^-1(u) = sqrt(2) * erfinv(2u - 1), no scipy dependency.
        return math.sqrt(2.0) * torch.erfinv(2.0 * u - 1.0)

    def _sobol_normals(self, samples: int, dim: int, seed: int) -> torch.Tensor:
        engine = SobolEngine(dimension=dim, scramble=True, seed=seed)
        return self._normal_icdf(engine.draw(samples))

    # ------------------------------------------------------------------
    # LM evaluation and candidate construction
    # ------------------------------------------------------------------

    @torch.inference_mode()
    def _next_token_logp(self, state_tokens: tuple[int, ...]) -> torch.Tensor:
        if not state_tokens:
            raise ValueError("state_tokens must contain at least one token")
        input_ids = torch.tensor(
            [state_tokens], dtype=torch.long, device=self.model_device
        )
        outputs = self.model(input_ids=input_ids, use_cache=False)
        logits = outputs.logits[0, -1].float()
        return F.log_softmax(logits, dim=-1).detach().cpu()

    def _qmc_tail_ids(
        self,
        probs: torch.Tensor,
        excluded: set[int],
        count: int,
        seed: int,
    ) -> list[int]:
        """Low-discrepancy inverse-CDF samples from residual probability mass."""
        if count <= 0:
            return []

        residual = probs.clone().to(dtype=torch.float64)
        if excluded:
            residual[list(excluded)] = 0.0
        mass = float(residual.sum().item())
        if not math.isfinite(mass) or mass <= 0.0:
            return []
        residual /= mass
        cdf = residual.cumsum(dim=0)

        engine = SobolEngine(dimension=1, scramble=True, seed=seed)
        draws = engine.draw(max(32, count * 8)).squeeze(1).to(dtype=torch.float64)
        sampled = torch.searchsorted(cdf, draws, right=False).clamp_max(len(cdf) - 1)

        result: list[int] = []
        seen = set(excluded)
        for token_id in sampled.tolist():
            token_id = int(token_id)
            if residual[token_id] > 0.0 and token_id not in seen:
                result.append(token_id)
                seen.add(token_id)
                if len(result) == count:
                    return result

        # Duplicated inverse-CDF hits are completed by residual probability rank.
        for token_id in torch.argsort(residual, descending=True).tolist():
            token_id = int(token_id)
            if residual[token_id] <= 0.0:
                break
            if token_id not in seen:
                result.append(token_id)
                seen.add(token_id)
                if len(result) == count:
                    break
        return result

    def _build_candidates(
        self,
        logp: torch.Tensor,
        state_key: tuple[int, ...],
    ) -> tuple[torch.Tensor, torch.Tensor]:
        cfg = self.config
        vocab_size = int(logp.numel())
        top_k = min(cfg.candidate_top_k, vocab_size)
        min_candidates = min(cfg.min_candidates, top_k)

        probs = logp.exp()
        sorted_probs, sorted_ids = torch.sort(probs, descending=True)
        cumulative_before = sorted_probs.cumsum(0) - sorted_probs
        nucleus_mask = cumulative_before < cfg.candidate_top_p
        rank_mask = torch.arange(vocab_size) < top_k
        keep = nucleus_mask & rank_mask
        keep[:min_candidates] = True
        core_ids = [int(x) for x in sorted_ids[keep].tolist()]

        candidate_ids: list[int] = list(dict.fromkeys(core_ids))
        excluded = set(candidate_ids)
        candidate_ids.extend(
            self._qmc_tail_ids(
                probs,
                excluded,
                cfg.qmc_tail_candidates,
                self._state_seed(state_key, salt=11),
            )
        )

        if (
            cfg.force_eos_candidate
            and self.eos_token_id is not None
            and 0 <= int(self.eos_token_id) < vocab_size
            and int(self.eos_token_id) not in candidate_ids
        ):
            candidate_ids.append(int(self.eos_token_id))

        ids = torch.tensor(candidate_ids, dtype=torch.long)
        return ids, logp[ids].to(dtype=torch.float64)

    # ------------------------------------------------------------------
    # Option 3: deterministic spherical k-means over token embeddings
    # ------------------------------------------------------------------

    @torch.inference_mode()
    def _candidate_embeddings(self, candidate_ids: torch.Tensor) -> torch.Tensor:
        ids = candidate_ids.to(self.input_embeddings.weight.device)
        vectors = (
            self.input_embeddings.weight.index_select(0, ids).float().detach().cpu()
        )
        return F.normalize(vectors, p=2, dim=1, eps=1e-12)

    def _semantic_cluster(
        self,
        vectors: torch.Tensor,
        prior_logp: torch.Tensor,
        max_clusters: Optional[int] = None,
    ) -> torch.Tensor:
        """Deterministic farthest-first spherical k-means; returns [A] labels."""
        n = int(vectors.shape[0])
        k = min(max_clusters or self.config.semantic_clusters, n)
        if k == 1:
            return torch.zeros(n, dtype=torch.long)

        # Seed with the highest-prior token, then maximize distance to centers.
        chosen = [int(torch.argmax(prior_logp).item())]
        while len(chosen) < k:
            centers = vectors[torch.tensor(chosen)]
            closest_similarity = (vectors @ centers.T).max(dim=1).values
            closest_similarity[torch.tensor(chosen)] = float("inf")
            chosen.append(int(torch.argmin(closest_similarity).item()))

        centers = vectors[torch.tensor(chosen)].clone()
        labels = torch.zeros(n, dtype=torch.long)
        for _ in range(self.config.kmeans_iterations):
            similarity = vectors @ centers.T
            new_labels = similarity.argmax(dim=1)

            new_centers: list[torch.Tensor] = []
            for cluster_id in range(k):
                members = vectors[new_labels == cluster_id]
                if len(members) == 0:
                    # Revive an empty cluster with the globally least represented point.
                    fit = similarity.max(dim=1).values
                    replacement = vectors[int(torch.argmin(fit).item())]
                    new_centers.append(replacement)
                else:
                    center = members.mean(dim=0)
                    new_centers.append(F.normalize(center, dim=0, eps=1e-12))
            updated = torch.stack(new_centers)
            labels = new_labels
            if torch.allclose(updated, centers, atol=1e-6, rtol=0.0):
                centers = updated
                break
            centers = updated

        # Compress labels in case a final iteration left a cluster empty.
        unique = torch.unique(labels, sorted=True)
        remap = torch.full((k,), -1, dtype=torch.long)
        remap[unique] = torch.arange(len(unique))
        return remap[labels]

    @staticmethod
    def _cluster_log_mass(
        prior_logp: torch.Tensor, labels: torch.Tensor
    ) -> torch.Tensor:
        num_clusters = int(labels.max().item()) + 1
        masses = []
        for cluster_id in range(num_clusters):
            masses.append(torch.logsumexp(prior_logp[labels == cluster_id], dim=0))
        mass = torch.stack(masses)
        return mass - torch.logsumexp(mass, dim=0)

    def get_or_create_node(self, state_tokens: TokenSeq) -> NodeData:
        state_key = tuple(int(x) for x in state_tokens)
        existing = self.nodes.get(state_key)
        if existing is not None:
            return existing

        logp = self._next_token_logp(state_key)
        candidate_ids, prior_logp = self._build_candidates(logp, state_key)
        vectors = self._candidate_embeddings(candidate_ids)
        eos_positions = torch.zeros(len(candidate_ids), dtype=torch.bool)
        if self.eos_token_id is not None:
            eos_positions = candidate_ids == int(self.eos_token_id)
        make_eos_singleton = (
            self.config.eos_singleton_cluster
            and self.config.semantic_clusters >= 2
            and bool(eos_positions.any())
            and bool((~eos_positions).any())
        )
        if make_eos_singleton:
            non_eos_labels = self._semantic_cluster(
                vectors[~eos_positions],
                prior_logp[~eos_positions],
                max_clusters=self.config.semantic_clusters - 1,
            )
            labels = torch.empty(len(candidate_ids), dtype=torch.long)
            labels[~eos_positions] = non_eos_labels
            labels[eos_positions] = int(non_eos_labels.max().item()) + 1
        else:
            labels = self._semantic_cluster(vectors, prior_logp)
        cluster_prior_logp = self._cluster_log_mass(prior_logp, labels)

        num_actions = int(candidate_ids.numel())
        num_clusters = int(cluster_prior_logp.numel())
        prior_mean = self.config.value_prior_mean
        seed = self._state_seed(state_key, salt=23)
        qmc_engine = SobolEngine(
            dimension=2 + num_actions,
            scramble=True,
            seed=seed,
        )
        node = NodeData(
            candidate_ids=candidate_ids,
            prior_logp=prior_logp,
            cluster_of=labels,
            cluster_prior_logp=cluster_prior_logp,
            node_seed=seed,
            qmc_engine=qmc_engine,
            n=torch.zeros(num_actions, dtype=torch.float64),
            mean=torch.full((num_actions,), prior_mean, dtype=torch.float64),
            m2=torch.zeros(num_actions, dtype=torch.float64),
            active=torch.ones(num_actions, dtype=torch.bool),
            cluster_visits=torch.zeros(num_clusters, dtype=torch.float64),
            last_p_opt=torch.full((num_actions,), float("nan"), dtype=torch.float64),
            last_pairwise_upper=torch.full(
                (num_actions,), float("nan"), dtype=torch.float64
            ),
        )
        self.nodes[state_key] = node
        return node

    # ------------------------------------------------------------------
    # Posterior proxy and semantic-stratified QMC Thompson selection
    # ------------------------------------------------------------------

    def _mean_variance(self, n: torch.Tensor, m2: torch.Tensor) -> torch.Tensor:
        cfg = self.config
        n = n.to(dtype=torch.float64)
        empirical = torch.full_like(n, cfg.observation_variance)
        enough = n > 1.0
        # A zero sample variance after two similar targets must not create near-
        # certainty.  observation_variance is also the irreducible noise floor.
        empirical[enough] = (m2[enough] / (n[enough] - 1.0)).clamp_min(
            cfg.observation_variance
        )
        variance = empirical / n.clamp_min(1.0) + cfg.uncertainty_floor
        variance[n == 0.0] = cfg.value_prior_variance
        return variance.clamp_min(cfg.uncertainty_floor)

    @staticmethod
    def _relative_log_prior(logp: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        result = torch.full_like(logp, float("-inf"), dtype=torch.float64)
        if bool(mask.any()):
            selected = logp[mask].to(dtype=torch.float64)
            result[mask] = selected - selected.max()
        return result

    def sample_qmc_action(self, node: NodeData, _k: Optional[int] = None) -> int:
        """Return the token id chosen by semantic-stratified QMC Thompson."""
        action_index = self._sample_qmc_action_index(node)
        return int(node.candidate_ids[action_index].item())

    def _sample_qmc_action_index(self, node: NodeData) -> int:
        if not bool(node.active.any()):
            raise RuntimeError("node has no active actions")

        cfg = self.config
        u = node.qmc_engine.draw(1).squeeze(0)
        node.qmc_draws += 1
        coverage_gate = float(u[0].item())
        cluster_quantile = float(u[1].item())
        z_action = self._normal_icdf(u[2:])

        cluster_active = torch.zeros(node.num_clusters, dtype=torch.bool)
        for cluster_id in range(node.num_clusters):
            cluster_active[cluster_id] = bool(
                node.active[node.cluster_of == cluster_id].any()
            )

        action_var = self._mean_variance(node.n, node.m2)
        action_prior = self._relative_log_prior(node.prior_logp, node.active)
        action_sample = (
            node.mean
            + action_var.sqrt() * z_action
            + cfg.action_prior_strength * action_prior
        )
        action_sample[~node.active] = float("-inf")
        global_choice = int(torch.argmax(action_sample).item())

        if coverage_gate >= cfg.semantic_coverage_probability:
            chosen_cluster = int(node.cluster_of[global_choice].item())
            node.cluster_visits[chosen_cluster] += 1.0
            return global_choice

        # Coverage visits mix a uniform floor with current active LM prior mass.
        # This makes low-mass semantic regions reachable without value sharing.
        cluster_mass = torch.zeros(node.num_clusters, dtype=torch.float64)
        for cluster_id in range(node.num_clusters):
            members = node.active & (node.cluster_of == cluster_id)
            if bool(members.any()):
                cluster_mass[cluster_id] = torch.exp(
                    torch.logsumexp(node.prior_logp[members], dim=0)
                )
        cluster_mass /= cluster_mass.sum().clamp_min(torch.finfo(torch.float64).tiny)
        uniform = cluster_active.to(torch.float64)
        uniform /= uniform.sum().clamp_min(1.0)
        route_probability = (
            cfg.semantic_uniform_mix * uniform
            + (1.0 - cfg.semantic_uniform_mix) * cluster_mass
        )
        cdf = route_probability.cumsum(dim=0)
        chosen_cluster = int(
            torch.searchsorted(
                cdf,
                torch.tensor(cluster_quantile, dtype=torch.float64),
                right=False,
            )
            .clamp_max(node.num_clusters - 1)
            .item()
        )
        eligible = node.active & (node.cluster_of == chosen_cluster)
        if not bool(eligible.any()):
            # Numerical fallback; zero-probability clusters should not be selected.
            chosen_cluster = int(node.cluster_of[global_choice].item())
            eligible = node.active & (node.cluster_of == chosen_cluster)
        restricted = action_sample.clone()
        restricted[~eligible] = float("-inf")
        node.cluster_visits[chosen_cluster] += 1.0
        return int(torch.argmax(restricted).item())

    # ------------------------------------------------------------------
    # Reward, reverse Bellman backup, and non-destructive pruning
    # ------------------------------------------------------------------

    def _step_reward(
        self,
        node: NodeData,
        state_key: tuple[int, ...],
        action_index: int,
        next_state: tuple[int, ...],
        terminal: bool,
    ) -> float:
        action_id = int(node.candidate_ids[action_index].item())
        reward = 0.0
        if self.step_reward_fn is not None:
            reward += float(
                self.step_reward_fn(state_key, action_id, next_state, terminal)
            )
        if self.config.lm_logprob_reward_weight != 0.0:
            reward += self.config.lm_logprob_reward_weight * float(
                node.prior_logp[action_index].item()
            )
        if terminal and self.terminal_reward_fn is not None:
            reward += float(self.terminal_reward_fn(next_state))
        if not math.isfinite(reward):
            raise ValueError(
                f"non-finite reward at state={state_key}, action={action_id}"
            )
        return reward

    @staticmethod
    def _welford_update(
        n: torch.Tensor,
        mean: torch.Tensor,
        m2: torch.Tensor,
        index: int,
        value: float,
    ) -> None:
        old_n = float(n[index].item())
        new_n = old_n + 1.0
        old_mean = float(mean[index].item())
        delta = value - old_mean
        new_mean = old_mean + delta / new_n
        delta2 = value - new_mean
        n[index] = new_n
        mean[index] = new_mean
        m2[index] += delta * delta2

    def _update_action(self, node: NodeData, action_index: int, target: float) -> None:
        self._welford_update(node.n, node.mean, node.m2, action_index, target)

    def _node_value(self, node: NodeData) -> float:
        """Bellman bootstrap value; inactive arms cannot win the maximum."""
        values = node.mean.clone()
        values[~node.active] = float("-inf")
        if not bool(torch.isfinite(values).any()):
            return self.config.value_prior_mean
        return float(torch.max(values).item())

    def _probability_of_optimality(self, node: NodeData) -> torch.Tensor:
        """Diagnostic QMC estimate of P(a = argmax Q); never a hard-prune proof."""
        active_indices = torch.where(node.active)[0]
        result = torch.zeros(node.num_actions, dtype=torch.float64)
        if len(active_indices) == 1:
            result[active_indices[0]] = 1.0
            return result

        means = node.mean[active_indices]
        variances = self._mean_variance(node.n, node.m2)[active_indices]
        z = self._sobol_normals(
            self.config.prune_samples,
            len(active_indices),
            seed=(node.node_seed ^ 0x5F3759DF) % (2**31 - 1),
        )
        samples = means.unsqueeze(0) + variances.sqrt().unsqueeze(0) * z
        winners = samples.argmax(dim=1)
        wins = torch.bincount(winners, minlength=len(active_indices)).to(torch.float64)

        # Jeffreys smoothing prevents a finite QMC batch from claiming exact zero.
        alpha = 0.5
        p = (wins + alpha) / (
            float(self.config.prune_samples) + alpha * len(active_indices)
        )
        result[active_indices] = p
        return result

    def _pairwise_optimality_upper_bound(self, node: NodeData) -> torch.Tensor:
        """Return P(Q_a >= Q_b), where b has the largest active posterior mean.

        If action ``a`` is globally optimal it must beat ``b``.  Under the
        independent Normal proxy this pairwise probability is therefore an
        analytic upper bound on P(a is optimal), safer for hard elimination than
        a zero/low winner count from one finite QMC block.
        """
        active_indices = torch.where(node.active)[0]
        result = torch.zeros(node.num_actions, dtype=torch.float64)
        active_means = node.mean[active_indices]
        best = int(active_indices[int(torch.argmax(active_means).item())].item())
        variance = self._mean_variance(node.n, node.m2)
        denominator = (
            (variance + variance[best])
            .sqrt()
            .clamp_min(math.sqrt(self.config.uncertainty_floor))
        )
        z = (node.mean - node.mean[best]) / denominator
        result = 0.5 * (1.0 + torch.erf(z / math.sqrt(2.0)))
        result[~node.active] = 0.0
        result[best] = 1.0
        return result

    def apply_bayesian_pruning(
        self,
        node: NodeData,
        _state_key: Optional[tuple[int, ...]] = None,
    ) -> list[int]:
        """Deactivate low-P(optimal) arms while preserving statistics and nodes."""
        cfg = self.config
        if node.total_visits % cfg.prune_every_node_visits != 0:
            return []
        if int(node.active.sum().item()) <= cfg.min_active_actions:
            return []

        p_opt = self._probability_of_optimality(node)
        p_upper = self._pairwise_optimality_upper_bound(node)
        node.last_p_opt = p_opt
        node.last_pairwise_upper = p_upper
        node.prune_events += 1

        active_indices = torch.where(node.active)[0]
        best = int(
            active_indices[int(torch.argmax(node.mean[active_indices]).item())].item()
        )
        if node.n[best] < cfg.min_action_visits_before_prune:
            return []

        eligible = (
            node.active
            & (node.n >= cfg.min_action_visits_before_prune)
            & (p_upper < cfg.prune_epsilon)
        )
        eligible[best] = False
        candidates = torch.where(eligible)[0]
        if len(candidates) == 0:
            return []

        # Prune least plausible first and keep a hard minimum alive.
        order = candidates[torch.argsort(p_upper[candidates])]
        capacity = int(node.active.sum().item()) - cfg.min_active_actions
        to_prune = order[: max(0, capacity)]
        node.active[to_prune] = False
        return [int(node.candidate_ids[i].item()) for i in to_prune.tolist()]

    def search_step(self, root_tokens: TokenSeq, max_depth: int = 16) -> SearchTrace:
        """Run one simulation, then update its path from leaf to root."""
        if max_depth < 1:
            raise ValueError("max_depth must be positive")
        current_state = tuple(int(x) for x in root_tokens)
        trace = SearchTrace()

        for _depth in range(max_depth):
            node = self.get_or_create_node(current_state)
            action_index = self._sample_qmc_action_index(node)
            action_id = int(node.candidate_ids[action_index].item())
            next_state = current_state + (action_id,)
            terminal = self.eos_token_id is not None and action_id == int(
                self.eos_token_id
            )
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
                break

        if trace.terminated:
            trace.leaf_value = 0.0  # terminal reward was included on the EOS edge
        elif self.leaf_value_fn is not None:
            trace.leaf_value = float(self.leaf_value_fn(current_state))
        else:
            trace.leaf_value = self.config.value_prior_mean

        next_value = trace.leaf_value
        for transition in reversed(trace.transitions):
            node = self.nodes[transition.state_key]
            target = transition.reward + self.config.gamma * next_value
            self._update_action(node, transition.action_index, target)
            self.apply_bayesian_pruning(node, transition.state_key)
            # The child has just been updated, so its fresh max reaches the parent.
            next_value = self._node_value(node)

        return trace

    def run_search(
        self,
        root_tokens: TokenSeq,
        simulations: int,
        max_depth: int = 16,
    ) -> list[SearchTrace]:
        if simulations < 1:
            raise ValueError("simulations must be positive")
        return [self.search_step(root_tokens, max_depth) for _ in range(simulations)]

    # ------------------------------------------------------------------
    # Readout / inspection
    # ------------------------------------------------------------------

    def _greedy_action_index(self, node: NodeData) -> int:
        cfg = self.config
        # Search readout should not prefer a never-visited optimistic arm over
        # explored evidence.  Fall back to all active arms only before any visit.
        eligible = node.active & (node.n > 0)
        if not bool(eligible.any()):
            eligible = node.active
        prior = self._relative_log_prior(node.prior_logp, eligible)
        # Posterior mean is the decision value; LM prior breaks weak/untested ties.
        score = node.mean + cfg.action_prior_strength * prior
        score[~eligible] = float("-inf")
        return int(torch.argmax(score).item())

    def best_continuation(
        self,
        root_tokens: TokenSeq,
        max_new_tokens: int = 32,
        *,
        include_root: bool = False,
    ) -> list[int]:
        state = tuple(int(x) for x in root_tokens)
        generated: list[int] = []
        for _ in range(max_new_tokens):
            node = self.nodes.get(state)
            if node is None:
                break
            index = self._greedy_action_index(node)
            action_id = int(node.candidate_ids[index].item())
            generated.append(action_id)
            state = state + (action_id,)
            if self.eos_token_id is not None and action_id == int(self.eos_token_id):
                break
        return list(root_tokens) + generated if include_root else generated

    def node_summary(
        self, state_tokens: TokenSeq, active_only: bool = False
    ) -> list[dict[str, Any]]:
        key = tuple(int(x) for x in state_tokens)
        node = self.nodes[key]
        variance = self._mean_variance(node.n, node.m2)
        rows: list[dict[str, Any]] = []
        for i in range(node.num_actions):
            if active_only and not bool(node.active[i]):
                continue
            token_id = int(node.candidate_ids[i].item())
            try:
                token = self.tokenizer.decode([token_id])
            except Exception:
                token = str(token_id)
            p_opt = float(node.last_p_opt[i].item())
            p_upper = float(node.last_pairwise_upper[i].item())
            rows.append(
                {
                    "token_id": token_id,
                    "token": token,
                    "cluster": int(node.cluster_of[i].item()),
                    "active": bool(node.active[i].item()),
                    "visits": int(node.n[i].item()),
                    "mean": float(node.mean[i].item()),
                    "posterior_sd_proxy": math.sqrt(float(variance[i].item())),
                    "lm_logp": float(node.prior_logp[i].item()),
                    "p_opt": None if math.isnan(p_opt) else p_opt,
                    "pairwise_optimality_upper": (
                        None if math.isnan(p_upper) else p_upper
                    ),
                }
            )
        rows.sort(key=lambda row: (row["active"], row["mean"]), reverse=True)
        return rows

    def compact_unreachable_prefixes(self, root_tokens: TokenSeq) -> int:
        """Optional explicit compaction; search itself never physically deletes nodes.

        Exact-prefix states have one structural parent.  A node is retained only if
        every edge from ``root_tokens`` to it still exists and remains active.
        This is deliberately a separate maintenance phase so pruning is reversible
        until the caller chooses to compact.
        """
        root = tuple(int(x) for x in root_tokens)
        removable: list[tuple[int, ...]] = []
        for key in self.nodes:
            if len(key) <= len(root) or key[: len(root)] != root:
                continue
            reachable = True
            for length in range(len(root), len(key)):
                parent_key = key[:length]
                action_id = key[length]
                parent = self.nodes.get(parent_key)
                if parent is None:
                    reachable = False
                    break
                matches = torch.where(parent.candidate_ids == action_id)[0]
                if len(matches) == 0 or not bool(parent.active[int(matches[0])]):
                    reachable = False
                    break
            if not reachable:
                removable.append(key)
        for key in removable:
            del self.nodes[key]
        return len(removable)


# ----------------------------------------------------------------------
# Download-free deterministic toy model and self-test
# ----------------------------------------------------------------------


class _ToyTokenizer:
    pieces = ["<bos>", "<eos>", "A", "B", "C", "D", "x", "y", "?", ".", "+", "-"]
    bos_token_id = 0
    eos_token_id = 1

    def decode(self, ids: Iterable[int], **_: Any) -> str:
        return "".join(self.pieces[int(i)] for i in ids)


class _ToyCausalLM(nn.Module):
    """Tiny bigram-like LM exposing the subset of the HF interface we use."""

    def __init__(self, vocab_size: int = 12, hidden_size: int = 8) -> None:
        super().__init__()
        generator = torch.Generator().manual_seed(7)
        self.embedding = nn.Embedding(vocab_size, hidden_size)
        self.projection = nn.Linear(hidden_size, vocab_size, bias=False)
        with torch.no_grad():
            self.embedding.weight.copy_(
                torch.randn(vocab_size, hidden_size, generator=generator)
            )
            self.projection.weight.copy_(
                0.15 * torch.randn(vocab_size, hidden_size, generator=generator)
            )
            # Make A/B/C a coherent embedding neighborhood for visible clustering.
            base = F.normalize(
                torch.tensor([1.0, 0.8, 0.2, 0.0, 0.0, 0.0, 0.0, 0.0]), dim=0
            )
            self.embedding.weight[2] = base
            self.embedding.weight[3] = F.normalize(base + 0.05, dim=0)
            self.embedding.weight[4] = F.normalize(base - 0.05, dim=0)

    def get_input_embeddings(self) -> nn.Embedding:
        return self.embedding

    def forward(self, input_ids: torch.Tensor, use_cache: bool = False) -> Any:
        del use_cache
        hidden = self.embedding(input_ids)
        logits = self.projection(hidden)
        # A soft but imperfect language prior: A -> B -> eos is plausible.
        last = input_ids[:, -1]
        logits[:, -1, 2] += (last == 0).float() * 1.5
        logits[:, -1, 3] += (last == 2).float() * 1.5
        logits[:, -1, 1] += (last == 3).float() * 1.5
        logits[:, -1, 4] += 0.4  # distractor remains plausible
        return SimpleNamespace(logits=logits)


def _run_self_test(verbose: bool = True) -> None:
    tokenizer = _ToyTokenizer()
    model = _ToyCausalLM()
    root = (tokenizer.bos_token_id,)
    target = (2, 3, tokenizer.eos_token_id)

    def step_reward(
        state: tuple[int, ...],
        action: int,
        _next_state: tuple[int, ...],
        _terminal: bool,
    ) -> float:
        offset = len(state) - len(root)
        if offset < len(target) and action == target[offset]:
            return 0.8
        return -0.15

    def terminal_reward(tokens: tuple[int, ...]) -> float:
        generated = tokens[len(root) :]
        return 2.0 if generated == target else -0.5

    cfg = QMCBMGSConfig(
        gamma=0.95,
        candidate_top_k=8,
        candidate_top_p=0.97,
        min_candidates=6,
        qmc_tail_candidates=3,
        semantic_clusters=3,
        semantic_coverage_probability=0.30,
        semantic_uniform_mix=0.60,
        action_prior_strength=0.08,
        prune_epsilon=0.02,
        prune_samples=128,
        prune_every_node_visits=4,
        min_action_visits_before_prune=2,
        min_active_actions=3,
        seed=123,
    )
    policy = QMCBMGSReasoningPolicy(
        model,
        tokenizer,
        cfg,
        step_reward_fn=step_reward,
        terminal_reward_fn=terminal_reward,
    )
    traces = policy.run_search(root, simulations=96, max_depth=3)
    best = policy.best_continuation(root, max_new_tokens=3)
    root_node = policy.nodes[root]

    assert len(traces) == 96
    assert root_node.num_clusters <= cfg.semantic_clusters
    assert root_node.num_actions <= cfg.candidate_top_k + cfg.qmc_tail_candidates + 1
    assert root_node.total_visits == 96
    assert int(root_node.active.sum()) >= cfg.min_active_actions
    assert best == list(target), (best, target, policy.node_summary(root)[:5])
    assert all(math.isfinite(t.leaf_value) for t in traces)
    assert int(root_node.cluster_visits.sum().item()) == root_node.qmc_draws
    inactive = ~root_node.active
    assert bool(torch.isfinite(root_node.mean[inactive]).all())

    # Node-local scrambled streams are reproducible under the same model/config.
    replay = QMCBMGSReasoningPolicy(
        _ToyCausalLM(),
        tokenizer,
        cfg,
        step_reward_fn=step_reward,
        terminal_reward_fn=terminal_reward,
    )
    replay_traces = replay.run_search(root, simulations=12, max_depth=3)
    assert [t.token_ids for t in replay_traces] == [t.token_ids for t in traces[:12]]

    target_parent = root + target[:-1]
    terminal_node = policy.nodes[target_parent]
    eos_local = int(
        torch.where(terminal_node.candidate_ids == tokenizer.eos_token_id)[0][0]
    )
    assert terminal_node.n[eos_local] > 0, "EOS edge must be backed up"

    if verbose:
        print("self-test: PASS")
        print("nodes:", len(policy.nodes))
        print("best continuation:", tokenizer.decode(best), best)
        print("root candidates:")
        for row in policy.node_summary(root)[:8]:
            print(
                "  ",
                f"{row['token']!r:7}",
                f"cluster={row['cluster']}",
                f"active={row['active']}",
                f"N={row['visits']:3d}",
                f"mean={row['mean']:+.3f}",
                f"sd={row['posterior_sd_proxy']:.3f}",
                f"p_opt={row['p_opt']}",
                f"p_upper={row['pairwise_optimality_upper']}",
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the deterministic toy-model smoke test",
    )
    args = parser.parse_args()
    if args.self_test:
        _run_self_test(verbose=True)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
