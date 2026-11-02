"""Two deterministic arms, one physical row each per source; no seed replication."""

from fractions import Fraction
import math

from qmc_bmgs.substrate.budget import TRACK_A_WORK_AXES
from qmc_bmgs.substrate.trace import sha256_json
from qmc_bmgs_next.puct_return import METHODS
from qmc_bmgs_next.search_value_study import (
    METRIC_FIELDS,
    PROPOSAL_COUNTERS,
    aggregate,
    contrast,
    event_metrics,
    rational,
    require,
    same,
    source_moments,
)

__all__ = [
    "coordinates",
    "validate_matrix",
    "reduce_matrix",
    "event_metrics",
    "pair_diagnostics",
    "choice_material",
    "source_moments",
    "PROPOSAL_COUNTERS",
]


def coordinates(count, seeds=(0,)):
    require(type(count) is int and count > 0, "positive plain source count required")
    require(
        type(seeds) in (list, tuple)
        and len(seeds) == 1
        and type(seeds[0]) is int
        and seeds[0] == 0,
        "one deterministic identity (0), not repeated stochastic roots",
    )
    return tuple(
        (slot, method, 0)
        for slot in range(count)
        for method in (METHODS if slot % 2 == 0 else METHODS[::-1])
    )


def work(value):
    require(
        type(value) is dict
        and set(value) == set(TRACK_A_WORK_AXES)
        and all(type(v) is int and v >= 0 for v in value.values()),
        "seven-axis nonnegative plain work required",
    )


def validate_matrix(rows, count, seeds, scores=512):
    expected = set(coordinates(count, seeds))
    require(type(rows) is list, "matrix rows must be a list")
    found = {}
    for row in rows:
        require(
            type(row) is dict and set(row) == {"key", "metrics"},
            "closed matrix row required",
        )
        k = row["key"]
        require(
            type(k) is list
            and len(k) == 3
            and type(k[0]) is int
            and type(k[1]) is str
            and type(k[2]) is int,
            "typed cell coordinate required",
        )
        key = tuple(k)
        require(
            key in expected and key not in found, "duplicate/foreign cell coordinate"
        )
        m = row["metrics"]
        require(
            type(m) is dict and set(m) == METRIC_FIELDS, "closed cell metrics required"
        )
        require(
            type(m["success"]) is bool
            and type(m["missing_terminal"]) is bool
            and m["budget_valid"] is True,
            "boolean success and valid budget required",
        )
        error = m["minimum_terminal_error"]
        require(
            error is None or (type(error) is int and error >= 0),
            "nonnegative error or null",
        )
        require(
            m["missing_terminal"] == (error is None), "missing terminal/error mismatch"
        )
        require(m["success"] == (error == 0), "success/error mismatch")
        for name in ("terminal_count", "revisit_count", "selection_count"):
            require(type(m[name]) is int and m[name] >= 0, "plain event count required")
        require(
            m["missing_terminal"] == (m["terminal_count"] == 0),
            "terminal count mismatch",
        )
        require(
            m["stop_reason"] in ("method_complete", "primary_budget_blocked"),
            "invalid stop",
        )
        for name in ("actual_work", "unspent_work"):
            work(m[name])
        for axis in TRACK_A_WORK_AXES:
            cap = scores if axis == "legal_action_scores" else 100000
            require(
                m["actual_work"][axis] + m["unspent_work"][axis] == cap,
                "work/cap closure",
            )
            require(
                axis == "legal_action_scores" or m["actual_work"][axis] < cap,
                "non-primary guard exhausted",
            )
        if m["success"]:
            work(m["first_exact_work"])
            require(m["censored_at_work"] is None, "successful cell cannot be censored")
            require(
                all(
                    m["first_exact_work"][a] <= m["actual_work"][a]
                    for a in TRACK_A_WORK_AXES
                ),
                "first exact exceeds stopping work",
            )
        else:
            require(
                m["first_exact_work"] is None
                and same(m["censored_at_work"], m["actual_work"]),
                "no-hit censoring mismatch",
            )
        p = m["proposal_work"]
        require(
            type(p) is dict
            and set(p) == set(PROPOSAL_COUNTERS)
            and all(type(v) is int and v >= 0 for v in p.values()),
            "proposal counters required",
        )
        found[key] = m
    require(set(found) == expected, "complete unique fixed matrix required")
    return found


def reduce_matrix(rows, count, seeds=(0,), scores=512):
    found = validate_matrix(rows, count, seeds, scores)

    def pairs(slots):
        return [(found[(s, METHODS[0], 0)], found[(s, METHODS[1], 0)]) for s in slots]

    values = [
        Fraction(int(a["success"]) - int(b["success"])) for a, b in pairs(range(count))
    ]
    methods = {
        method: dict(
            **aggregate([found[(s, method, 0)] for s in range(count)]),
            source_count=count,
            rows_per_source=1,
            by_source=[
                dict(source_slot=s, **aggregate([found[(s, method, 0)]]))
                for s in range(count)
            ],
        )
        for method in METHODS
    }
    primary = source_moments(values, primary=True)
    comparison = dict(
        contrast="puct-dense16-minus-puct",
        **contrast(pairs(range(count))),
        source_moments=primary,
        by_source=[dict(source_slot=s, **contrast(pairs((s,)))) for s in range(count)],
        leave_one_source_out=[
            dict(
                omitted=s,
                **contrast(pairs([i for i in range(count) if i != s])),
                mean_rational=rational(
                    (sum(values, Fraction()) - values[s]) / (count - 1)
                )
                if count > 1
                else None,
            )
            for s in range(count)
        ],
    )
    return dict(
        schema_version="puct_return_source_reduction/v1",
        source_count=count,
        cell_count=len(rows),
        methods=methods,
        primary=primary,
        contrasts=[comparison],
        cells=rows,
        stochastic_roots=[],
        deterministic_rows_are_not_seed_replicates=True,
        sensitivity_is_not_confidence_interval=True,
        proposal_internal_work_not_charged_or_equal_total_compute=True,
        winner=None,
        scientific_decision=None,
    )


def choice_material(record):
    """Saved-history PUCT decomposition, not a counterfactual trajectory."""
    proposals, posteriors, choices = {}, {}, []
    first_exact_seen = False
    method = record["run_identity"]["spec"]["method"]
    require(method in METHODS, "known deterministic method required")
    for e in record["search_record"]["events"]:
        p = e["payload"]
        if e["kind"] == "proposal_materialized":
            row = p["proposal"]
            proposals[tuple(row["state"])] = row
        elif e["kind"] == "terminal_verified":
            first_exact_seen |= p["verification"]["success"]
        elif e["kind"] == "trajectory_backed_up":
            for u in p["updates"]:
                posteriors[(tuple(u["state"]), u["action_index"])] = u["after"]
        elif e["kind"] == "selection_committed":
            state = tuple(p["state"])
            logp = proposals[state]["prior_logp"]
            means = [
                posteriors.get((state, i), {}).get("mean", 0.0)
                for i in range(len(logp))
            ]
            visits = [
                posteriors.get((state, i), {}).get("visits", 0)
                for i in range(len(logp))
            ]
            scale = math.sqrt(1.0 + sum(visits))
            bonus = [
                1.0 * math.exp(lp) * scale / (1.0 + n) for lp, n in zip(logp, visits)
            ]
            scores = [m + b for m, b in zip(means, bonus)]
            require(same(scores, p["selection_values"]), "saved PUCT scores mismatch")
            chosen = max(range(len(scores)), key=lambda i: (scores[i], -i))
            require(chosen == p["action_index"], "saved PUCT choice mismatch")
            require(p["point_digest"] is None, "deterministic PUCT has no perturbation")
            if method == "puct" and not first_exact_seen:
                require(
                    all(m == 0.0 for m in means),
                    "binary PUCT Q before first exact must be zero",
                )
            choices.append(
                dict(
                    state=list(state),
                    trajectory_index=p["trajectory_index"],
                    depth=p["depth"],
                    action_index=chosen,
                    action=p["action"],
                    current_means=means,
                    current_visits=visits,
                    prior_probabilities=[math.exp(lp) for lp in logp],
                    exploration_bonus=bonus,
                    selected_scores=scores,
                    before_first_exact=not first_exact_seen,
                    passive_mean_off_action_index=max(
                        range(len(bonus)), key=lambda i: (bonus[i], -i)
                    ),
                )
            )
    return choices


def pair_diagnostics(dense, binary):
    require(
        dense["run_identity"]["spec"]["method"] == METHODS[0]
        and binary["run_identity"]["spec"]["method"] == METHODS[1],
        "ordered dense/binary pair required",
    )
    left, right = choice_material(dense), choice_material(binary)

    def projection(row):
        return {k: row[k] for k in ("state", "trajectory_index", "depth", "action")}

    lc, rc = [projection(r) for r in left], [projection(r) for r in right]
    i = 0
    while i < min(len(left), len(right)) and same(lc[i], rc[i]):
        i += 1
    return dict(
        same_action_sequence=same(lc, rc),
        common_action_prefix_length=i,
        same_first_trajectory=same(
            [r for r in lc if r["trajectory_index"] == 0],
            [r for r in rc if r["trajectory_index"] == 0],
        ),
        first_choice_divergence=dict(
            selection_index=i,
            dense16=left[i],
            binary=right[i],
            same_state=same(left[i]["state"], right[i]["state"]),
        )
        if i < min(len(left), len(right))
        else None,
        one_sequence_ends_at_common_prefix=i == min(len(left), len(right))
        and len(left) != len(right),
        action_sequence_lengths=[len(left), len(right)],
        action_sequence_digests=[sha256_json(lc), sha256_json(rc)],
        passive_same_history_mean_off_choice_flips=[
            sum(r["action_index"] != r["passive_mean_off_action_index"] for r in rows)
            for rows in (left, right)
        ],
        pre_first_exact_passive_mean_off_choice_flips=[
            sum(
                r["before_first_exact"]
                and r["action_index"] != r["passive_mean_off_action_index"]
                for r in rows
            )
            for rows in (left, right)
        ],
        binary_pre_first_exact_all_means_zero=True,
        passive_flip_is_not_counterfactual_rollout=True,
        stochastic_pairing_applicable=False,
    )
