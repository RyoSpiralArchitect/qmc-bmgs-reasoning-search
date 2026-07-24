#!/usr/bin/env python3
"""Compare two validated Countdown provider snapshots without network access."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from pathlib import Path
from typing import Any, Mapping, Sequence

from qmc_bmgs.experiments.countdown_anthropic_dev import (
    validate_artifact as validate_anthropic_artifact,
)
from qmc_bmgs.experiments.countdown_openai_dev import (
    validate_artifact as validate_openai_artifact,
)


def _read_jsonl(path: Path) -> tuple[dict[str, Any], ...]:
    return tuple(json.loads(line) for line in path.read_text().splitlines() if line)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _percentile(values: Sequence[float], quantile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return (
        ordered[lower] * (upper - position)
        + ordered[upper] * (position - lower)
    )


def _distribution(log_probabilities: Sequence[float]) -> tuple[float, ...]:
    return tuple(math.exp(value) for value in log_probabilities)


def _normalized_entropy(probabilities: Sequence[float]) -> float | None:
    if len(probabilities) <= 1:
        return None
    return -sum(
        probability * math.log(probability)
        for probability in probabilities
        if probability > 0
    ) / math.log(len(probabilities))


def _normalized_jsd(
    first: Sequence[float],
    second: Sequence[float],
) -> float:
    midpoint = tuple((left + right) / 2 for left, right in zip(first, second))

    def kl(left: Sequence[float], right: Sequence[float]) -> float:
        return sum(
            value * math.log(value / reference)
            for value, reference in zip(left, right)
            if value > 0
        )

    value = (kl(first, midpoint) + kl(second, midpoint)) / (2 * math.log(2))
    return min(1.0, max(0.0, value))


def _kendall_tau_b(
    first: Sequence[int],
    second: Sequence[int],
) -> float | None:
    concordant = 0
    discordant = 0
    first_only_ties = 0
    second_only_ties = 0
    for left in range(len(first)):
        for right in range(left + 1, len(first)):
            first_sign = (first[left] > first[right]) - (
                first[left] < first[right]
            )
            second_sign = (second[left] > second[right]) - (
                second[left] < second[right]
            )
            if first_sign == 0 and second_sign == 0:
                continue
            if first_sign == 0:
                first_only_ties += 1
            elif second_sign == 0:
                second_only_ties += 1
            elif first_sign == second_sign:
                concordant += 1
            else:
                discordant += 1
    denominator = math.sqrt(
        (concordant + discordant + first_only_ties)
        * (concordant + discordant + second_only_ties)
    )
    if denominator == 0:
        return None
    return (concordant - discordant) / denominator


def _proposal_rows(
    artifact_dir: Path,
) -> dict[tuple[str, tuple[int, ...]], dict[str, Any]]:
    result: dict[tuple[str, tuple[int, ...]], dict[str, Any]] = {}
    for record in _read_jsonl(artifact_dir / "proposal_rows.jsonl"):
        behavior = record["behavior"]
        metadata = record["provider_result"]["metadata"]
        key = (behavior["task_fingerprint"], tuple(behavior["state"]))
        result[key] = {
            "actions": tuple(
                (item["left"], item["right"], item["operator"])
                for item in behavior["actions"]
            ),
            "logp": tuple(behavior["prior_logp"]),
            "output_schema_digest": metadata["output_schema_digest"],
            "provider_payload": metadata["provider_payload"],
            "provider_payload_digest": metadata["provider_payload_digest"],
            "scores": tuple(behavior["raw_scores"]),
            "system_instruction_digest": metadata["system_instruction_digest"],
        }
    return result


def _snapshot_structure(
    rows: Mapping[tuple[str, tuple[int, ...]], Mapping[str, Any]],
) -> dict[str, Any]:
    scores = [score for row in rows.values() for score in row["scores"]]
    entropies: list[float] = []
    top_masses: list[float] = []
    for row in rows.values():
        probabilities = _distribution(row["logp"])
        entropy = _normalized_entropy(probabilities)
        if entropy is not None:
            entropies.append(entropy)
        top_masses.append(max(probabilities))
    return {
        "actions": len(scores),
        "all_tied_states": sum(
            len(set(row["scores"])) == 1 for row in rows.values()
        ),
        "distinct_scores": len(set(scores)),
        "entropy_defined_states": len(entropies),
        "entropy_mean": statistics.fmean(entropies),
        "entropy_median": statistics.median(entropies),
        "states": len(rows),
        "states_with_thousand": sum(
            1000 in row["scores"] for row in rows.values()
        ),
        "states_with_zero": sum(0 in row["scores"] for row in rows.values()),
        "thousand_scores": scores.count(1000),
        "top_mass_mean": statistics.fmean(top_masses),
        "top_mass_median": statistics.median(top_masses),
        "top_mass_p75": _percentile(top_masses, 0.75),
        "top_tied_states": sum(
            sum(score == max(row["scores"]) for score in row["scores"]) > 1
            for row in rows.values()
        ),
        "zero_scores": scores.count(0),
    }


def _latency(artifact_dir: Path) -> dict[str, Any]:
    values = [
        record["latency_ms"] / 1000
        for record in _read_jsonl(artifact_dir / "provider_attempts.jsonl")
        if record.get("event") == "RESPONSE_RECEIVED"
    ]
    return {
        "count": len(values),
        "max_s": max(values),
        "mean_s": statistics.fmean(values),
        "median_s": statistics.median(values),
        "p95_s": _percentile(values, 0.95),
        "sum_s": sum(values),
    }


def _paired_row(
    first: Mapping[str, Any],
    second: Mapping[str, Any],
) -> dict[str, Any]:
    first_top = {
        index
        for index, score in enumerate(first["scores"])
        if score == max(first["scores"])
    }
    second_top = {
        index
        for index, score in enumerate(second["scores"])
        if score == max(second["scores"])
    }
    first_probability = _distribution(first["logp"])
    second_probability = _distribution(second["logp"])
    first_entropy = _normalized_entropy(first_probability)
    second_entropy = _normalized_entropy(second_probability)
    return {
        "both_unique": len(first_top) == len(second_top) == 1,
        "entropy_delta_second_minus_first": (
            None
            if first_entropy is None or second_entropy is None
            else second_entropy - first_entropy
        ),
        "jsd": _normalized_jsd(first_probability, second_probability),
        "tau_b": _kendall_tau_b(first["scores"], second["scores"]),
        "top_jaccard": len(first_top & second_top) / len(first_top | second_top),
        "top_set_equal": first_top == second_top,
        "top_mass_delta_second_minus_first": (
            max(second_probability) - max(first_probability)
        ),
        "top_overlap": bool(first_top & second_top),
        "unique_agree": (
            len(first_top) == len(second_top) == 1 and first_top == second_top
        ),
    }


def _aggregate_pair(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    unique = [row for row in rows if row["both_unique"]]
    tau = [row["tau_b"] for row in rows if row["tau_b"] is not None]
    entropy = [
        row["entropy_delta_second_minus_first"]
        for row in rows
        if row["entropy_delta_second_minus_first"] is not None
    ]
    return {
        "both_unique_states": len(unique),
        "entropy_delta_defined_states": len(entropy),
        "entropy_delta_mean": statistics.fmean(entropy),
        "jsd_mean": statistics.fmean(row["jsd"] for row in rows),
        "jsd_median": statistics.median(row["jsd"] for row in rows),
        "states": len(rows),
        "tau_b_defined_states": len(tau),
        "tau_b_mean": statistics.fmean(tau),
        "tau_b_median": statistics.median(tau),
        "top_jaccard_mean": statistics.fmean(
            row["top_jaccard"] for row in rows
        ),
        "top_set_equal_rate": sum(row["top_set_equal"] for row in rows) / len(rows),
        "top_set_equal_states": sum(row["top_set_equal"] for row in rows),
        "top_mass_delta_mean": statistics.fmean(
            row["top_mass_delta_second_minus_first"] for row in rows
        ),
        "top_overlap_rate": sum(row["top_overlap"] for row in rows) / len(rows),
        "unique_top_agree_states": sum(row["unique_agree"] for row in unique),
        "unique_top_agreement_rate": (
            None
            if not unique
            else sum(row["unique_agree"] for row in unique) / len(unique)
        ),
    }


def _search_aggregate(artifact_dir: Path) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in _read_jsonl(artifact_dir / "search_records.jsonl"):
        grouped.setdefault(record["method"], []).append(record)
    return {
        method: {
            "edge_selections": sum(
                row["usage"]["usage"]["edge_selections"] for row in rows
            ),
            "exact_success_rows": sum(row["exact_success_any"] for row in rows),
            "proposal_batch_calls": sum(
                row["usage"]["usage"]["proposal_batch_calls"] for row in rows
            ),
            "proposal_action_scores": sum(
                row["usage"]["usage"]["proposal_action_scores"] for row in rows
            ),
            "rows": len(rows),
            "selection_action_scores": sum(
                row["usage"]["usage"]["selection_action_scores"] for row in rows
            ),
            "transitions": sum(
                row["usage"]["usage"]["transitions"] for row in rows
            ),
            "verifier_calls": sum(
                row["usage"]["usage"]["verifier_calls"] for row in rows
            ),
        }
        for method, rows in sorted(grouped.items())
    }


def compare(anthropic_dir: Path, openai_dir: Path) -> dict[str, Any]:
    anthropic_summary = validate_anthropic_artifact(anthropic_dir)
    openai_summary = validate_openai_artifact(openai_dir)
    anthropic = _proposal_rows(anthropic_dir)
    openai = _proposal_rows(openai_dir)
    if set(anthropic) != set(openai):
        raise AssertionError("provider snapshots have different state identities")
    if any(anthropic[key]["actions"] != openai[key]["actions"] for key in anthropic):
        raise AssertionError("provider snapshots have different legal-action identities")

    paired_by_task: dict[str, list[dict[str, Any]]] = {}
    all_pairs: list[dict[str, Any]] = []
    for key in sorted(anthropic):
        row = _paired_row(anthropic[key], openai[key])
        all_pairs.append(row)
        paired_by_task.setdefault(key[0], []).append(row)
    per_task = {
        task: _aggregate_pair(rows) for task, rows in paired_by_task.items()
    }
    macro_fields = (
        "entropy_delta_mean",
        "jsd_mean",
        "tau_b_mean",
        "top_jaccard_mean",
        "top_mass_delta_mean",
        "top_overlap_rate",
        "top_set_equal_rate",
        "unique_top_agreement_rate",
    )
    equal_task_macro = {
        field: statistics.fmean(value[field] for value in per_task.values())
        for field in macro_fields
    }

    return {
        "claim_boundary": {
            "development_observation_only": True,
            "effectiveness_comparison": False,
            "provider_or_model_superiority": False,
            "qmc_included": False,
        },
        "comparability_gate": {
            "legal_action_identity_equal": True,
            "normalization_equal": (
                anthropic_summary["provider"]["normalization_version"]
                == openai_summary["provider"]["normalization_version"]
            ),
            "output_schema_digest_equal": all(
                anthropic[key]["output_schema_digest"]
                == openai[key]["output_schema_digest"]
                for key in anthropic
            ),
            "provider_payload_digest_equal": all(
                anthropic[key]["provider_payload_digest"]
                == openai[key]["provider_payload_digest"]
                for key in anthropic
            ),
            "provider_payload_equal": all(
                anthropic[key]["provider_payload"]
                == openai[key]["provider_payload"]
                for key in anthropic
            ),
            "state_identity_equal": True,
            "states": len(anthropic),
            "system_instruction_digest_equal": all(
                anthropic[key]["system_instruction_digest"]
                == openai[key]["system_instruction_digest"]
                for key in anthropic
            ),
        },
        "first_anthropic": {
            "behavior_digest": anthropic_summary["proposal_behavior_digest"],
            "latency": _latency(anthropic_dir),
            "manifest_sha256": _file_sha256(anthropic_dir / "manifest.json"),
            "provider": anthropic_summary["provider"],
            "search": _search_aggregate(anthropic_dir),
            "structure": _snapshot_structure(anthropic),
            "usage": anthropic_summary["physical_provider_usage"],
        },
        "paired": {
            "equal_task_macro": equal_task_macro,
            "per_task": per_task,
            "pooled": _aggregate_pair(all_pairs),
        },
        "schema_version": "qmc-bmgs-countdown-provider-observation/v1",
        "second_openai": {
            "behavior_digest": openai_summary["proposal_behavior_digest"],
            "latency": _latency(openai_dir),
            "manifest_sha256": _file_sha256(openai_dir / "manifest.json"),
            "provider": openai_summary["provider"],
            "search": _search_aggregate(openai_dir),
            "structure": _snapshot_structure(openai),
            "usage": openai_summary["physical_provider_usage"],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--anthropic-dir", type=Path, required=True)
    parser.add_argument("--openai-dir", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            compare(args.anthropic_dir, args.openai_dir),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
