"""Three-arm bounded-bonus reductions; reuse the fixed source-level readout.

No new budget framework, policy run or cohort is generated here. The original
source moments, precision-first gates, seven-axis metrics and missingness are
reused; only the matrix and fixed-policy choice decomposition differ.
"""

from fractions import Fraction
import math

from qmc_bmgs.substrate.budget import TRACK_A_WORK_AXES
from qmc_bmgs.substrate.trace import sha256_json
from qmc_bmgs_next.puct_qmc_root import METHODS, perturbation_active
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
    "anchor_projection",
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
                    pair = ["puct-qmc", "puct-iid"]
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
    for left_method, baseline in (
        ("puct-qmc", "puct"),
        ("puct-qmc", "puct-iid"),
        ("puct-iid", "puct"),
    ):

        def pairs(slots, roots):
            return [
                (
                    found[(s, left_method, r)],
                    found[(s, baseline, r if baseline == "puct-iid" else 0)],
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
                contrast=left_method + "-minus-" + baseline,
                **contrast(pairs(range(count), seeds)),
                source_moments=source_moments(
                    values, primary=left_method == "puct-qmc" and baseline == "puct"
                ),
                deterministic_baseline_rows_referenced_not_replicated=baseline
                != "puct-iid",
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
        schema_version="puct_qmc_root_source_reduction/v1",
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


def anchor_projection(record):
    """Compact evidence shared with fixed PUCT, excluding method/stream identity."""
    return [
        dict(
            kind=e["kind"],
            **{
                k: e["payload"][k]
                for k in (
                    ("state", "action", "child_state", "depth")
                    if e["kind"] == "selection_committed"
                    else ("actions", "verification")
                )
            },
        )
        for e in record["search_record"]["events"]
        if e["kind"] in ("selection_committed", "terminal_verified")
        and e["payload"]["trajectory_index"] == 0
    ]


def choice_material(record):
    """Saved-history decomposition; the unperturbed alternative is not a rollout."""
    proposals, points, posteriors, choices = {}, {}, {}, []
    first_exact_seen = False
    method = record["run_identity"]["spec"]["method"]
    require(method in METHODS, "known hybrid/control method required")
    for e in record["search_record"]["events"]:
        p = e["payload"]
        if e["kind"] == "proposal_materialized":
            row = p["proposal"]
            proposals[tuple(row["state"])] = row
        elif e["kind"] == "perturbation_draw":
            points[p["point_digest"]] = p
        elif e["kind"] == "terminal_verified":
            first_exact_seen |= p["verification"]["success"]
        elif e["kind"] == "trajectory_backed_up":
            require(
                p["terminal_value"] in (0.0, 1.0), "binary terminal backup required"
            )
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
            bonus = [
                1.0 * math.exp(lp) * math.sqrt(1.0 + sum(visits)) / (1.0 + n)
                for lp, n in zip(logp, visits)
            ]
            anchored = method == "puct" or not perturbation_active(
                p["trajectory_index"], p["depth"]
            )
            if anchored:
                require(
                    p["point_digest"] is None, "fixed PUCT phase cannot draw material"
                )
                uniforms = None
                multipliers = [1.0] * len(logp)
            else:
                uniforms = points[p["point_digest"]]["uniforms"]
                require(
                    len(uniforms) == len(logp)
                    and all(type(u) is float and 0 < u < 1 for u in uniforms),
                    "open-unit action-matched material required",
                )
                multipliers = [0.5 + u for u in uniforms]
            score = [m + b * w for m, b, w in zip(means, bonus, multipliers)]
            require(
                same(score, p["selection_values"]), "saved bounded PUCT scores mismatch"
            )
            selected = max(range(len(score)), key=lambda i: (score[i], -i))
            require(selected == p["action_index"], "saved bounded PUCT choice mismatch")
            if not first_exact_seen:
                require(
                    all(m == 0.0 for m in means),
                    "binary Q before first exact must be zero",
                )
            unperturbed = [m + b for m, b in zip(means, bonus)]
            choices.append(
                dict(
                    perturbation_active=not anchored,
                    state=list(state),
                    trajectory_index=p["trajectory_index"],
                    depth=p["depth"],
                    action_index=selected,
                    action=p["action"],
                    current_means=means,
                    current_visits=visits,
                    prior_probabilities=[math.exp(lp) for lp in logp],
                    unperturbed_bonus=bonus,
                    original_uniforms=uniforms,
                    bonus_multipliers=multipliers,
                    selected_scores=score,
                    before_first_exact=not first_exact_seen,
                    passive_unperturbed_action_index=max(
                        range(len(score)), key=lambda i: (unperturbed[i], -i)
                    ),
                )
            )
    return choices


def pair_diagnostics(qmc, iid):
    require(
        qmc["run_identity"]["spec"]["method"] == METHODS[0]
        and iid["run_identity"]["spec"]["method"] == METHODS[1],
        "ordered QMC/IID pair required",
    )
    require(
        qmc["run_identity"]["root_seed"] == iid["run_identity"]["root_seed"],
        "matched root labels required",
    )
    left, right = choice_material(qmc), choice_material(iid)

    def projection(row):
        return {k: row[k] for k in ("state", "trajectory_index", "depth", "action")}

    lc, rc = [projection(r) for r in left], [projection(r) for r in right]
    i = 0
    while i < min(len(left), len(right)) and same(lc[i], rc[i]):
        i += 1
    require(
        same(anchor_projection(qmc), anchor_projection(iid)),
        "first PUCT trajectory differs",
    )
    if i < min(len(left), len(right)):
        require(
            left[i]["depth"] == right[i]["depth"] == 0
            and same(left[i]["state"], right[i]["state"]),
            "first root-only pair divergence must be at the same root state",
        )
    return dict(
        same_action_sequence=same(lc, rc),
        common_action_prefix_length=i,
        same_first_trajectory=True,
        first_choice_divergence=dict(
            selection_index=i,
            qmc=left[i],
            iid=right[i],
            same_state=same(left[i]["state"], right[i]["state"]),
        )
        if i < min(len(left), len(right))
        else None,
        one_sequence_ends_at_common_prefix=i == min(len(left), len(right))
        and len(left) != len(right),
        action_sequence_lengths=[len(left), len(right)],
        action_sequence_digests=[sha256_json(lc), sha256_json(rc)],
        passive_same_history_unperturbed_choice_flips=[
            sum(
                r["action_index"] != r["passive_unperturbed_action_index"] for r in rows
            )
            for rows in (left, right)
        ],
        fixed_nonroot_selection_scores_verified=True,
        active_perturbation_depths=[0],
        binary_pre_first_exact_all_means_zero=True,
        passive_flip_is_not_counterfactual_rollout=True,
        matched_root_labels_are_not_common_random_draws=True,
        whole_trajectory_common_random_numbers_claim=False,
    )
