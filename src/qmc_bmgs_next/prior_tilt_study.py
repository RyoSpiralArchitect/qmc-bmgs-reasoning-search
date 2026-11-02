"""Three-arm prior-tilt reductions; reuse the fixed source-level readout.

No new budget framework, policy run or cohort is generated here. The original
source moments, precision-first gates, seven-axis metrics and missingness are
reused; only the matrix and fixed-policy choice decomposition differ.
"""

from fractions import Fraction
import math

from qmc_bmgs.substrate.budget import TRACK_A_WORK_AXES
from qmc_bmgs.substrate.trace import sha256_json
from qmc_bmgs_next.prior_tilt import METHODS
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


def coordinates(count, seeds):
    require(type(count) is int and count > 0, "positive plain source count required")
    require(
        type(seeds) in (tuple, list)
        and len(seeds) > 0
        and all(type(s) is int and s > 0 for s in seeds)
        and len(set(seeds)) == len(seeds),
        "distinct positive plain root seeds required",
    )
    # Interleave the stochastic pair; rotate method groups by source, and reverse
    # pair order on odd source/seed positions. This schedule is outcome blind.
    rows = []
    for slot in range(count):
        groups = ["pair", "puct"]
        shift = slot % len(groups)
        for group in groups[shift:] + groups[:shift]:
            if group == "pair":
                for i, seed in enumerate(seeds):
                    pair = ["prior-tilt16", "prior-mean-off"]
                    for method in pair if (slot + i) % 2 == 0 else pair[::-1]:
                        rows.append((slot, method, seed))
            else:
                rows.append((slot, group, 0))
    return tuple(rows)


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


def reduce_matrix(rows, count, seeds, scores=512):
    found = validate_matrix(rows, count, seeds, scores)
    methods = {}
    for method in METHODS:
        keys = [k for k in coordinates(count, seeds) if k[1] == method]
        methods[method] = dict(
            **aggregate([found[k] for k in keys]),
            source_count=count,
            rows_per_source=len(seeds) if method in METHODS[:2] else 1,
            by_source=[
                dict(source_slot=s, **aggregate([found[k] for k in keys if k[0] == s]))
                for s in range(count)
            ],
            by_root=[
                dict(root_seed=r, **aggregate([found[k] for k in keys if k[2] == r]))
                for r in (seeds if method in METHODS[:2] else (0,))
            ],
        )
    comparisons = []
    for baseline in ("puct", "prior-mean-off"):

        def pairs(slots, roots):
            return [
                (
                    found[(s, "prior-tilt16", r)],
                    found[(s, baseline, r if baseline == "prior-mean-off" else 0)],
                )
                for s in slots
                for r in roots
            ]

        values = [
            Fraction(
                sum(
                    int(a["success"]) - int(b["success"]) for a, b in pairs((s,), seeds)
                ),
                len(seeds),
            )
            for s in range(count)
        ]
        comparisons.append(
            dict(
                contrast="prior-tilt16-minus-" + baseline,
                **contrast(pairs(range(count), seeds)),
                source_moments=source_moments(values, primary=baseline == "puct"),
                deterministic_baseline_rows_referenced_not_replicated=baseline
                != "prior-mean-off",
                by_source=[
                    dict(source_slot=s, **contrast(pairs((s,), seeds)))
                    for s in range(count)
                ],
                by_root=[
                    dict(root_seed=r, **contrast(pairs(range(count), (r,))))
                    for r in seeds
                ],
                leave_one_source_out=[
                    dict(
                        omitted=s,
                        **contrast(pairs([i for i in range(count) if i != s], seeds)),
                        mean_rational=rational(
                            (sum(values, Fraction()) - values[s]) / (count - 1)
                        )
                        if count > 1
                        else None,
                    )
                    for s in range(count)
                ],
                leave_one_root_out=[
                    dict(
                        omitted=r,
                        **contrast(pairs(range(count), [x for x in seeds if x != r])),
                        mean_rational=rational(
                            Fraction(
                                sum(
                                    int(a["success"]) - int(b["success"])
                                    for a, b in pairs(
                                        range(count), [x for x in seeds if x != r]
                                    )
                                ),
                                count * (len(seeds) - 1),
                            )
                        )
                        if len(seeds) > 1
                        else None,
                    )
                    for r in seeds
                ],
            )
        )
    return dict(
        schema_version="prior_tilt_source_reduction/v1",
        source_count=count,
        stochastic_roots=list(seeds),
        cell_count=len(rows),
        methods=methods,
        primary=comparisons[0]["source_moments"],
        contrasts=comparisons,
        cells=rows,
        sensitivity_is_not_confidence_interval=True,
        proposal_internal_work_not_charged_or_equal_total_compute=True,
        winner=None,
        scientific_decision=None,
    )


def choice_material(record):
    """Independent saved-score decomposition, not an alternative rollout."""
    proposals, points, posteriors, material, selections = {}, {}, {}, {}, []
    mean_on = record["run_identity"]["spec"]["method"] == METHODS[0]
    for e in record["search_record"]["events"]:
        p = e["payload"]
        if e["kind"] == "proposal_materialized":
            row = p["proposal"]
            proposals[tuple(row["state"])] = row
        elif e["kind"] == "perturbation_draw":
            points[p["point_digest"]] = p
            material[(p["node_digest"], p["node_visit_index"])] = p
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
            uniforms = points[p["point_digest"]]["uniforms"]
            require(
                all(type(u) is float and 0 < u < 1 for u in uniforms),
                "open-unit material required",
            )
            noise = [-math.log(-math.log(u)) for u in uniforms]
            used = means if mean_on else [0.0] * len(means)
            score = [lp + m + g for lp, m, g in zip(logp, used, noise)]
            require(same(score, p["selection_values"]), "saved Gumbel scores mismatch")
            selected = max(range(len(score)), key=lambda i: (score[i], -i))
            require(selected == p["action_index"], "selected action mismatch")
            alternative = [
                lp + m + g
                for lp, m, g in zip(
                    logp, [0.0] * len(means) if mean_on else means, noise
                )
            ]
            selections.append(
                dict(
                    state=list(state),
                    trajectory_index=p["trajectory_index"],
                    depth=p["depth"],
                    action_index=selected,
                    action=p["action"],
                    current_means=means,
                    current_visits=visits,
                    used_mean_terms=used,
                    prior_terms=list(logp),
                    prior_terms_are_log_probabilities=True,
                    noise_terms=noise,
                    selected_scores=score,
                    passive_alternative_action_index=max(
                        range(len(alternative)), key=lambda i: (alternative[i], -i)
                    ),
                )
            )
    return selections, material


def pair_diagnostics(single, mean_off):
    left, lm = choice_material(single)
    right, rm = choice_material(mean_off)
    common = lm.keys() & rm.keys()
    require(
        all(same(lm[k], rm[k]) for k in common),
        "shared coordinate perturbation material drift",
    )

    def projection(row):
        return {k: row[k] for k in ("state", "trajectory_index", "depth", "action")}

    lchoices, rchoices = [projection(r) for r in left], [projection(r) for r in right]
    i = 0
    while i < min(len(left), len(right)) and same(lchoices[i], rchoices[i]):
        i += 1
    divergence = None
    if i < min(len(left), len(right)):
        divergence = dict(
            selection_index=i,
            prior_tilt16=left[i],
            mean_off=right[i],
            same_state=same(left[i]["state"], right[i]["state"]),
        )
    return dict(
        common_material_coordinates=len(common),
        shared_material_all_equal=True,
        whole_trajectory_common_random_numbers_claim=False,
        same_action_sequence=same(lchoices, rchoices),
        common_action_prefix_length=i,
        first_choice_divergence=divergence,
        one_sequence_ends_at_common_prefix=i == min(len(left), len(right))
        and len(left) != len(right),
        action_sequence_lengths=[len(left), len(right)],
        action_sequence_digests=[sha256_json(lchoices), sha256_json(rchoices)],
        passive_same_history_mean_toggle_choice_flips=[
            sum(
                r["action_index"] != r["passive_alternative_action_index"] for r in rows
            )
            for rows in (left, right)
        ],
        passive_flip_is_not_counterfactual_rollout=True,
    )
