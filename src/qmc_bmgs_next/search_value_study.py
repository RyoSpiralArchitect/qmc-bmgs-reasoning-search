"""Complete-matrix, source-level reductions for the sealed search-value design.

This module never generates a cohort or executes a search. Terminal flags and
charges are read from already authenticated/replayed events, not accepted from
an aggregate saved summary. Choice diagnostics are passive, not counterfactual
rollouts. Fixed seeds are repetitions within sources, never extra sources.
"""

from __future__ import annotations

from fractions import Fraction
import math

from qmc_bmgs.substrate.budget import TRACK_A_WORK_AXES
from qmc_bmgs.substrate.trace import canonical_trace_bytes, sha256_json
from qmc_bmgs_next.search_value import METHODS


PROPOSAL_COUNTERS = (
    "materialized_rows",
    "root_action_evaluations",
    "completion_legal_action_evaluations",
    "internal_transition_evaluations",
)
METRIC_FIELDS = {
    "success",
    "minimum_terminal_error",
    "missing_terminal",
    "budget_valid",
    "actual_work",
    "unspent_work",
    "first_exact_work",
    "censored_at_work",
    "terminal_count",
    "revisit_count",
    "selection_count",
    "stop_reason",
    "proposal_work",
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def same(a, b):
    return canonical_trace_bytes(a) == canonical_trace_bytes(b)


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
        groups = ["pair", "greedy", "beam2", "puct"]
        shift = slot % len(groups)
        for group in groups[shift:] + groups[:shift]:
            if group == "pair":
                for i, seed in enumerate(seeds):
                    pair = ["single16", "selection-mean-off"]
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


def rational(value):
    return None if value is None else [value.numerator, value.denominator]


def source_moments(values, *, primary):
    require(
        type(values) is list and values and all(type(x) is Fraction for x in values),
        "nonempty exact rational source differences required",
    )
    require(all(-1 <= x <= 1 for x in values), "source difference outside [-1,1]")
    n = len(values)
    mean = sum(values, Fraction()) / n
    variance = (
        sum(((x - mean) ** 2 for x in values), Fraction()) / (n - 1) if n > 1 else None
    )
    interval = half = None
    status, reason = "UNRESOLVED", "insufficient_source_clusters"
    if n >= 64:
        if variance == 0:
            reason = "degenerate_source_variance"
        else:
            half = 2 * math.sqrt(float(variance) / n)
            interval = [float(mean) - half, float(mean) + half]
            if half > 0.05:
                status, reason = "IMPRECISE", "precision_target_not_met"
            elif interval[0] > 0.02:
                status, reason = (
                    "PROMISING_FOR_FRESH_CONFIRMATION",
                    "model_interval_above_practical_threshold",
                )
            elif interval[1] <= 0.02:
                status, reason = (
                    "NO_PRACTICAL_UPLIFT_SIGNAL",
                    "model_interval_not_above_practical_threshold",
                )
            else:
                reason = "model_interval_crosses_practical_threshold"
    return dict(
        source_count=n,
        source_differences=[rational(v) for v in values],
        mean_rational=rational(mean),
        sample_source_variance_rational=rational(variance),
        estimate=float(mean),
        approximate_interval=interval,
        half_width=half,
        precision_target_met=None if half is None else half <= 0.05,
        development_readout=status if primary else None,
        interval_reason=reason,
        use="predeclared_primary" if primary else "descriptive_only_no_promotion_gate",
        interval_type="approximate_model_interval_not_guaranteed_coverage",
        assumptions_not_established_by_identity_uniqueness=True,
        winner=None,
        scientific_decision=None,
    )


def contrast(pairs):
    errors = dict(win=0, tie=0, loss=0, missing=0)
    gain = loss = 0
    for a, b in pairs:
        gain += int(a["success"] and not b["success"])
        loss += int(b["success"] and not a["success"])
        x, y = a["minimum_terminal_error"], b["minimum_terminal_error"]
        k = (
            "missing"
            if x is None or y is None
            else "win"
            if x < y
            else "loss"
            if x > y
            else "tie"
        )
        errors[k] += 1
    return dict(
        paired_description_count=len(pairs),
        gains=gain,
        losses=loss,
        net=gain - loss,
        minimum_error=errors,
    )


def aggregate(metrics):
    return dict(
        denominator=len(metrics),
        successes=sum(m["success"] for m in metrics),
        missing_terminal=sum(m["missing_terminal"] for m in metrics),
        terminal_count=sum(m["terminal_count"] for m in metrics),
        revisit_count=sum(m["revisit_count"] for m in metrics),
        actual_work={
            a: sum(m["actual_work"][a] for m in metrics) for a in TRACK_A_WORK_AXES
        },
        unspent_work={
            a: sum(m["unspent_work"][a] for m in metrics) for a in TRACK_A_WORK_AXES
        },
        proposal_work={
            k: sum(m["proposal_work"][k] for m in metrics) for k in PROPOSAL_COUNTERS
        },
    )


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
    for baseline in ("puct", "selection-mean-off", "greedy", "beam2"):

        def pairs(slots, roots):
            return [
                (
                    found[(s, "single16", r)],
                    found[(s, baseline, r if baseline == "selection-mean-off" else 0)],
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
                contrast="single16-minus-" + baseline,
                **contrast(pairs(range(count), seeds)),
                source_moments=source_moments(values, primary=baseline == "puct"),
                deterministic_baseline_rows_referenced_not_replicated=baseline
                != "selection-mean-off",
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
        schema_version="search_value_source_reduction/v1",
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


def event_metrics(record):
    """Independent event reduction after generative authentication, not a replay."""
    usage = dict.fromkeys(TRACK_A_WORK_AXES, 0)
    first, errors, states = None, [], []
    success = False
    events = record["search_record"]["events"]
    for e in events:
        if e["charge"] is not None:
            delta = e["charge"]["delta"]
            work(delta)
            for axis in usage:
                usage[axis] += delta[axis]
            require(
                same(usage, e["charge"]["usage_after"]), "event charge discontinuity"
            )
        if e["kind"] == "selection_committed":
            states.append(tuple(e["payload"]["state"]))
        if e["kind"] == "terminal_verified":
            v = e["payload"]["verification"]
            require(
                type(v["success"]) is bool
                and v["source_use_exact"] is True
                and type(v["final_value"]) is int
                and type(v["target"]) is int
                and v["success"] == (v["final_value"] == v["target"]),
                "terminal flags disagree",
            )
            errors.append(abs(v["final_value"] - v["target"]))
            success |= v["success"]
            if first is None and v["success"]:
                first = dict(usage)
    require(events[-1]["kind"] == "search_finished", "missing final search event")
    finish = events[-1]["payload"]["summary"]
    require(finish["budget_valid"] is True, "non-primary budget guard bound")
    summary = record["summary"]
    error = min(errors) if errors else None
    require(
        same(finish["ledger_usage"], usage)
        and same(summary["actual_work"], usage)
        and finish["success_any"] is success
        and finish["terminal_count"] == len(errors)
        and summary["minimum_terminal_error"] == error
        and same(summary["first_exact_work"], first)
        and summary["missing_terminal"] is (not errors),
        "event/summary reduction mismatch",
    )
    limits = record["run_identity"]["search_run_identity"]["work_limits"]
    unspent = {a: limits[a] - usage[a] for a in usage}
    require(same(unspent, summary["unspent_work"]), "unspent work mismatch")
    return dict(
        success=success,
        minimum_terminal_error=error,
        missing_terminal=not errors,
        budget_valid=True,
        actual_work=usage,
        unspent_work=unspent,
        first_exact_work=first,
        censored_at_work=None if success else dict(usage),
        terminal_count=len(errors),
        revisit_count=len(states) - len(set(states)),
        selection_count=usage["edge_selections"],
        stop_reason=finish["stop_reason"],
        proposal_work={k: summary["proposal_work"][k] for k in PROPOSAL_COUNTERS},
    )


def choice_material(record):
    """Passive scores on the observed history; no alternative history is searched."""
    proposals, points, posteriors, material, selections = {}, {}, {}, {}, []
    method = record["run_identity"]["spec"]["method"]
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
            priors = [math.exp(x) for x in proposals[state]["prior_logp"]]
            means = [
                posteriors.get((state, i), {}).get("mean", 0.0)
                for i in range(len(priors))
            ]
            visits = [
                posteriors.get((state, i), {}).get("visits", 0)
                for i in range(len(priors))
            ]
            point = points[p["point_digest"]]
            normalizer = (
                math.sqrt(2 * math.log(len(priors))) if len(priors) > 1 else 1.0
            )
            noise = [
                1.0 / (normalizer * math.sqrt(n + 1.0)) * z
                for z, n in zip(point["normals"], visits)
            ]
            used = means if method == "single16" else [0.0] * len(means)
            scores = [m + pr + no for m, pr, no in zip(used, priors, noise)]
            require(
                same(scores, p["selection_values"]),
                "passive selection decomposition mismatch",
            )
            selected = max(range(len(scores)), key=lambda i: (scores[i], -i))
            require(selected == p["action_index"], "passive selected action mismatch")
            alternative = [
                m + pr + no
                for m, pr, no in zip(
                    [0.0] * len(means) if method == "single16" else means, priors, noise
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
                    prior_terms=priors,
                    noise_terms=noise,
                    selected_scores=scores,
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
            single16=left[i],
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
