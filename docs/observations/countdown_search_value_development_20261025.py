#!/usr/bin/env python3
"""Read-only, stdlib-only saved-event check of the sealed search-value study.

No engine/reducer import, generation, search, alternative rollout or replay.
All seven charged axes and terminal/choice reductions are recomputed. One
proposal-internal counter (completion action enumeration) is carried from the
already replay-authenticated raw record, not independently re-enumerated here.
Print deterministic JSON only; never write fixed evidence.
"""

from __future__ import annotations

from collections import Counter
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = "artifacts/work/search-value-development-20261025-a"
PLAN = "docs/preregistrations/countdown_search_value_development_20261025.plan.json"
HEAD = "db475199e65666f187782182fef4056917287b5f"
DIGEST = "db7a96cf89355d7dfa379d21573f1ce5967536294190bea3dadbd9b947a907e5"
METHODS = ("single16", "selection-mean-off", "greedy", "beam2", "puct")
ROOTS = tuple(range(131072, 131076))
AXES = (
    "edge_selections",
    "generated_perturbation_coordinates",
    "legal_action_scores",
    "proposal_action_scores",
    "proposal_state_evaluations",
    "transitions",
    "verifier_calls",
)
PROPOSAL = (
    "materialized_rows",
    "root_action_evaluations",
    "completion_legal_action_evaluations",
    "internal_transition_evaluations",
)


def canonical(v):
    return json.dumps(
        v, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode()


def digest(v):
    return hashlib.sha256(canonical(v)).hexdigest()


def duplicate_free(items):
    obj = {}
    for k, v in items:
        assert k not in obj, k
        obj[k] = v
    return obj


def path(name):
    p = Path(name)
    assert not p.is_absolute() and ".." not in p.parts
    target = ROOT
    for part in p.parts:
        target /= part
        assert not target.is_symlink(), name
    return target


def ref(name):
    data = path(name).read_bytes()
    return dict(
        path=name, byte_count=len(data), sha256=hashlib.sha256(data).hexdigest()
    )


def read(name, expected=None):
    if expected:
        assert ref(name) == {k: expected[k] for k in ("path", "byte_count", "sha256")}
    data = path(name).read_bytes()
    obj = json.loads(
        data,
        object_pairs_hook=duplicate_free,
        parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)),
    )
    assert data == canonical(obj) + b"\n", name
    if isinstance(obj, dict) and "deterministic_digest" in obj:
        assert (
            digest({k: v for k, v in obj.items() if k != "deterministic_digest"})
            == obj["deterministic_digest"]
        )
    return obj


def equal(a, b):
    assert canonical(a) == canonical(b), "saved/recomputed mismatch"


def rat(x):
    return None if x is None else [x.numerator, x.denominator]


def argmax(values):
    # Stable lowest-index tie break, independent of the engine implementation.
    return values.index(max(values))


def scan(raw, method):
    usage = Counter({a: 0 for a in AXES})
    terminal_errors, choices, seen_states = [], [], set()
    first_hit, exact_count, revisits = None, 0, 0
    beam_selected_edges, beam_layers = 0, []
    proposals, draws, keyed, posterior = {}, {}, {}, {}
    proposal_counts = Counter()
    passive = []
    first_trajectory = []
    events = raw["search_record"]["events"]
    for event in events:
        charge = event["charge"]
        if charge is not None:
            assert set(charge["delta"]) == set(AXES)
            assert all(type(x) is int and x >= 0 for x in charge["delta"].values())
            usage.update(charge["delta"])
            equal(dict(usage), charge["usage_after"])
        k, p = event["kind"], event["payload"]
        if k == "proposal_materialized":
            row = p["proposal"]
            proposals[tuple(row["state"])] = row
            proposal_counts["materialized_rows"] += 1
            proposal_counts["root_action_evaluations"] += len(row["action_order"])
            proposal_counts["internal_transition_evaluations"] += row[
                "internal_transition_evaluations"
            ]
        elif k == "trajectory_backed_up":
            for u in p["updates"]:
                posterior[(tuple(u["state"]), u["action_index"])] = u["after"]
        elif k == "perturbation_draw":
            draws[p["point_digest"]] = p
            coord = (p["node_digest"], p["node_visit_index"])
            assert coord not in keyed
            keyed[coord] = digest(p)
        elif k == "selection_committed":
            state = tuple(p["state"])
            revisits += state in seen_states
            seen_states.add(state)
            projection = {
                x: p[x] for x in ("state", "trajectory_index", "depth", "action")
            }
            choices.append(projection)
            if not terminal_errors:
                first_trajectory.append(projection)
            if method in METHODS[:2]:
                row = proposals[state]
                priors = [math.exp(x) for x in row["prior_logp"]]
                histories = [posterior.get((state, i), {}) for i in range(len(priors))]
                means = [h.get("mean", 0.0) for h in histories]
                visits = [h.get("visits", 0) for h in histories]
                normals = draws[p["point_digest"]]["normals"]
                scale = math.sqrt(2 * math.log(len(priors))) if len(priors) > 1 else 1.0
                noise = [
                    1.0 / (scale * math.sqrt(n + 1.0)) * z
                    for n, z in zip(visits, normals)
                ]
                used = means if method == "single16" else [0.0] * len(priors)
                scores = [used[i] + priors[i] + noise[i] for i in range(len(priors))]
                alternate_mean = [0.0] * len(priors) if method == "single16" else means
                alternate = [
                    alternate_mean[i] + priors[i] + noise[i] for i in range(len(priors))
                ]
                equal(scores, p["selection_values"])
                assert argmax(scores) == p["action_index"]
                passive.append(
                    dict(
                        **projection,
                        action_index=p["action_index"],
                        current_means=means,
                        current_visits=visits,
                        used_mean_terms=used,
                        prior_terms=priors,
                        noise_terms=noise,
                        selected_scores=scores,
                        passive_alternative_action_index=argmax(alternate),
                    )
                )
        elif k == "beam_layer_selection_committed":
            assert method == "beam2" and p["beam_width"] == 2
            selected = p["selected"]
            assert len(selected) <= 2 and charge is not None
            assert charge["delta"]["edge_selections"] == len(selected)
            assert charge["delta"]["transitions"] == len(selected)
            beam_selected_edges += len(selected)
            beam_layers.append(p)
        elif k == "terminal_verified":
            v = p["verification"]
            assert type(v["success"]) is bool and v["source_use_exact"] is True
            assert type(v["final_value"]) is int and type(v["target"]) is int
            error = abs(v["final_value"] - v["target"])
            assert v["success"] == (error == 0)
            terminal_errors.append(error)
            exact_count += error == 0
            if error == 0 and first_hit is None:
                first_hit = dict(usage)
    assert events[-1]["kind"] == "search_finished"
    finish = events[-1]["payload"]["summary"]
    summary = raw["summary"]
    equal(dict(usage), finish["ledger_usage"])
    equal(dict(usage), summary["actual_work"])
    assert finish["budget_valid"] is True
    assert finish["stop_reason"] in ("primary_budget_blocked", "method_complete")
    assert finish["terminal_count"] == len(terminal_errors)
    assert finish["success_any"] == (exact_count > 0)
    assert finish["exact_terminal_count"] == exact_count
    limits = raw["run_identity"]["search_run_identity"]["work_limits"]
    assert limits == {a: 512 if a == "legal_action_scores" else 100000 for a in AXES}
    unspent = {a: limits[a] - usage[a] for a in AXES}
    assert all(v >= 0 for v in unspent.values())
    assert all(usage[a] < limits[a] for a in AXES if a != "legal_action_scores")
    equal(unspent, summary["unspent_work"])
    for name, n in proposal_counts.items():
        assert summary["proposal_work"][name] == n
    assert proposal_counts["materialized_rows"] == usage["proposal_state_evaluations"]
    assert proposal_counts["root_action_evaluations"] == usage["proposal_action_scores"]
    # This field requires internal proposal re-enumeration, outside this check.
    proposal_counts["completion_legal_action_evaluations"] = summary["proposal_work"][
        "completion_legal_action_evaluations"
    ]
    metrics = dict(
        success=exact_count > 0,
        minimum_terminal_error=min(terminal_errors, default=None),
        missing_terminal=not terminal_errors,
        budget_valid=True,
        actual_work=dict(usage),
        unspent_work=unspent,
        first_exact_work=first_hit,
        censored_at_work=None if exact_count else dict(usage),
        terminal_count=len(terminal_errors),
        revisit_count=revisits,
        selection_count=len(choices) + beam_selected_edges,
        stop_reason=finish["stop_reason"],
        proposal_work=dict(proposal_counts),
    )
    assert len(choices) + beam_selected_edges == usage["edge_selections"]
    # Preserve the sealed reducer's ordinary-selection revisit definition.
    # For beam, layered parent/child selections are recorded separately; its
    # zero ordinary-selection revisits do not mean zero repeated beam states.
    assert (not choices) if method == "beam2" else (not beam_layers)
    for name in ("minimum_terminal_error", "missing_terminal", "first_exact_work"):
        equal(metrics[name], summary[name])
    equal(metrics["censored_at_work"], summary["no_exact_observation_censored_at_work"])
    extra = dict(
        exact_terminal_count=exact_count,
        choice_sequence_digest=None if method == "beam2" else digest(choices),
        first_trajectory_digest=None if method == "beam2" else digest(first_trajectory),
        first_action=choices[0]["action"] if choices else None,
        first_trajectory_length=None if method == "beam2" else len(first_trajectory),
        ordinary_selection_event_count=len(choices),
        beam_layer_count=len(beam_layers),
        beam_selected_edge_count=beam_selected_edges,
        beam_layer_sequence_digest=digest(beam_layers) if method == "beam2" else None,
        revisit_definition="repeated_states_in_ordinary_selection_committed_only",
        passive_mean_toggle_flips=sum(
            x["action_index"] != x["passive_alternative_action_index"] for x in passive
        ),
        selected_not_max_prior=sum(
            x["action_index"] != argmax(x["prior_terms"]) for x in passive
        ),
        selected_not_max_mean=sum(
            x["action_index"] != argmax(x["current_means"]) for x in passive
        ),
        selected_noise_above_prior=sum(
            abs(x["noise_terms"][x["action_index"]])
            > x["prior_terms"][x["action_index"]]
            for x in passive
        ),
    )
    return metrics, extra, choices, passive, keyed


def sum_metrics(rows):
    return dict(
        denominator=len(rows),
        successes=sum(x["success"] for x in rows),
        missing_terminal=sum(x["missing_terminal"] for x in rows),
        terminal_count=sum(x["terminal_count"] for x in rows),
        revisit_count=sum(x["revisit_count"] for x in rows),
        **{
            field: {a: sum(x[field][a] for x in rows) for a in keys}
            for field, keys in (
                ("actual_work", AXES),
                ("unspent_work", AXES),
                ("proposal_work", PROPOSAL),
            )
        },
    )


def differences(pairs):
    errors = Counter(dict(win=0, tie=0, loss=0, missing=0))
    gains = losses = 0
    for left, right in pairs:
        gains += left["success"] and not right["success"]
        losses += right["success"] and not left["success"]
        a, b = left["minimum_terminal_error"], right["minimum_terminal_error"]
        if a is None or b is None:
            errors["missing"] += 1
        else:
            errors["win" if a < b else "loss" if a > b else "tie"] += 1
    return dict(
        paired_description_count=len(pairs),
        gains=gains,
        losses=losses,
        net=gains - losses,
        minimum_error=dict(errors),
    )


def moments(values, primary):
    n = len(values)
    mean = sum(values, Fraction()) / n
    # Algebraically independent exact second-moment form.
    variance = (
        (sum(x * x for x in values) - n * mean * mean) / (n - 1) if n > 1 else None
    )
    half = 2 * math.sqrt(float(variance) / n) if n >= 64 and variance != 0 else None
    interval = None if half is None else [float(mean) - half, float(mean) + half]
    status, reason = "UNRESOLVED", "insufficient_source_clusters"
    if n >= 64:
        if variance == 0:
            reason = "degenerate_source_variance"
        elif half > 0.05:
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
        source_differences=[rat(x) for x in values],
        mean_rational=rat(mean),
        sample_source_variance_rational=rat(variance),
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


def check_pair(left, right):
    _, _, lc, ls, lm = left
    _, _, rc, rs, rm = right
    common = set(lm) & set(rm)
    assert all(lm[k] == rm[k] for k in common)
    mismatch = next(
        (i for i, (a, b) in enumerate(zip(lc, rc)) if a != b), min(len(lc), len(rc))
    )
    divergence = (
        None
        if mismatch == min(len(lc), len(rc))
        else dict(
            selection_index=mismatch,
            single16=ls[mismatch],
            mean_off=rs[mismatch],
            same_state=lc[mismatch]["state"] == rc[mismatch]["state"],
        )
    )
    return dict(
        common_material_coordinates=len(common),
        shared_material_all_equal=True,
        whole_trajectory_common_random_numbers_claim=False,
        same_action_sequence=lc == rc,
        common_action_prefix_length=mismatch,
        first_choice_divergence=divergence,
        one_sequence_ends_at_common_prefix=mismatch == min(len(lc), len(rc))
        and len(lc) != len(rc),
        action_sequence_lengths=[len(lc), len(rc)],
        action_sequence_digests=[digest(lc), digest(rc)],
        passive_same_history_mean_toggle_choice_flips=[
            left[1]["passive_mean_toggle_flips"],
            right[1]["passive_mean_toggle_flips"],
        ],
        passive_flip_is_not_counterfactual_rollout=True,
    )


def main():
    plan = read(PLAN)
    assert plan["deterministic_digest"] == DIGEST
    commit = read(OUT + "/COMMIT.json")
    summary = read(OUT + "/summary.json")
    cohort = read(commit["cohort"]["path"], commit["cohort"])
    assert commit["candidate_commit"] == summary["candidate_commit"] == HEAD
    assert summary["status"] == "ALL_CELLS_REPLAYED_SEARCH_VALUE_ANALYSIS_COMPLETE"
    assert (
        summary["replayed_cells"] == 1408 and summary["cross_budget_prefix_pairs"] == 0
    )
    assert summary["winner"] is None and summary["scientific_decision"] is None
    equal(ref(OUT + "/COMMIT.json"), summary["commit"])
    assert len(cohort["tasks"]) == 128
    reduction = summary["reduction"]
    assert reduction["source_count"] == 128 and reduction["cell_count"] == 1408
    assert reduction["stochastic_roots"] == list(ROOTS)
    assert len(reduction["cells"]) == len(commit["cells"]) == 1408
    expected = {
        (s, m, r)
        for s in range(128)
        for m in METHODS
        for r in (ROOTS if m in METHODS[:2] else (0,))
    }
    found, extras, cache, pair_results = {}, {}, {}, {}
    for index, row in enumerate(commit["cells"]):
        key = tuple(row["key"])
        assert key in expected and key not in found and row["index"] == index
        equal(row["key"], plan["coordinates"][index])
        raw = read(row["file"]["path"], row["file"])
        assert raw["run_identity"]["spec"]["method"] == key[1]
        assert raw["run_identity"]["root_seed"] == key[2]
        result = scan(raw, key[1])
        found[key], extras[key] = result[:2]
        equal(dict(key=list(key), metrics=found[key]), reduction["cells"][index])
        if key[1] in METHODS[:2]:
            cache[key] = result
            other = (key[0], METHODS[1 - METHODS.index(key[1])], key[2])
            if other in cache:
                a, b = (
                    (key[0], "single16", key[2]),
                    (key[0], "selection-mean-off", key[2]),
                )
                pair_results[(key[0], key[2])] = check_pair(cache.pop(a), cache.pop(b))
        assert len(cache) <= 1
    assert set(found) == expected and not cache
    assert len(pair_results) == len(summary["paired_choice_diagnostics"]) == 512
    for pair in summary["paired_choice_diagnostics"]:
        key = (pair["source_slot"], pair["root_seed"])
        equal(
            {k: v for k, v in pair.items() if k not in ("source_slot", "root_seed")},
            pair_results[key],
        )
    for method, actual in reduction["methods"].items():
        assert method in METHODS
        keys = [k for k in found if k[1] == method]
        equal(
            sum_metrics([found[k] for k in keys]),
            {
                k: v
                for k, v in actual.items()
                if k not in ("by_source", "by_root", "source_count", "rows_per_source")
            },
        )
        assert actual["source_count"] == 128 and actual["rows_per_source"] == (
            4 if method in METHODS[:2] else 1
        )
        for category, field, pos in (
            ("by_source", "source_slot", 0),
            ("by_root", "root_seed", 2),
        ):
            rows = actual[category]
            assert len(rows) == (128 if pos == 0 else 4 if method in METHODS[:2] else 1)
            for group in rows:
                equal(
                    sum_metrics([found[k] for k in keys if k[pos] == group[field]]),
                    {k: v for k, v in group.items() if k != field},
                )
    for c in reduction["contrasts"]:
        baseline = c["contrast"].removeprefix("single16-minus-")
        assert baseline in ("puct", "selection-mean-off", "greedy", "beam2")

        def group(slots, roots):
            return [
                (
                    found[(s, "single16", r)],
                    found[(s, baseline, r if baseline == "selection-mean-off" else 0)],
                )
                for s in slots
                for r in roots
            ]

        values = [
            Fraction(differences(group([s], ROOTS))["net"], 4) for s in range(128)
        ]
        equal(moments(values, baseline == "puct"), c["source_moments"])
        equal(differences(group(range(128), ROOTS)), {k: c[k] for k in differences([])})
        assert c["deterministic_baseline_rows_referenced_not_replicated"] == (
            baseline != "selection-mean-off"
        )
        for row in c["by_source"]:
            equal(
                differences(group([row["source_slot"]], ROOTS)),
                {k: v for k, v in row.items() if k != "source_slot"},
            )
        for row in c["by_root"]:
            equal(
                differences(group(range(128), [row["root_seed"]])),
                {k: v for k, v in row.items() if k != "root_seed"},
            )
        for category in ("leave_one_source_out", "leave_one_root_out"):
            for row in c[category]:
                slots = [
                    s
                    for s in range(128)
                    if category != "leave_one_source_out" or s != row["omitted"]
                ]
                roots = [
                    r
                    for r in ROOTS
                    if category != "leave_one_root_out" or r != row["omitted"]
                ]
                expected_row = differences(group(slots, roots))
                expected_row["mean_rational"] = rat(
                    Fraction(expected_row["net"], len(slots) * len(roots))
                )
                equal(expected_row, {k: v for k, v in row.items() if k != "omitted"})
    equal(reduction["primary"], reduction["contrasts"][0]["source_moments"])
    method_details = {}
    for method in METHODS:
        keys = [k for k in found if k[1] == method]
        hits = [
            found[k]["first_exact_work"]["legal_action_scores"]
            for k in keys
            if found[k]["success"]
        ]
        method_details[method] = dict(
            first_exact_primary_scores=sorted(hits),
            no_hit_censoring_primary_scores=sorted(
                found[k]["censored_at_work"]["legal_action_scores"]
                for k in keys
                if not found[k]["success"]
            ),
            sources_with_any_success=sum(
                any(found[k]["success"] for k in keys if k[0] == s) for s in range(128)
            ),
            successes_by_source_root=[
                dict(key=list(k), first_exact_work=found[k]["first_exact_work"])
                for k in keys
                if found[k]["success"]
            ],
            stop_reasons=dict(Counter(found[k]["stop_reason"] for k in keys)),
            selection_count=sum(found[k]["selection_count"] for k in keys),
            **{
                field: sum(extras[k][field] for k in keys)
                for field in (
                    "exact_terminal_count",
                    "passive_mean_toggle_flips",
                    "selected_not_max_prior",
                    "selected_not_max_mean",
                    "selected_noise_above_prior",
                )
            },
        )
    source_presence = []
    for s in range(128):
        single = [found[(s, "single16", r)]["success"] for r in ROOTS]
        source_presence.append(
            dict(
                source_slot=s,
                single_success_roots=sum(single),
                **{m: found[(s, m, 0)]["success"] for m in METHODS[2:]},
            )
        )
    cases = {}
    for outcome in ("gain", "loss"):
        cases[outcome] = [
            dict(
                source_slot=s,
                root_seed=r,
                single=found[(s, "single16", r)],
                puct=found[(s, "puct", 0)],
            )
            for s in range(128)
            for r in ROOTS
            if (
                found[(s, "single16", r)]["success"]
                and not found[(s, "puct", 0)]["success"]
                if outcome == "gain"
                else found[(s, "puct", 0)]["success"]
                and not found[(s, "single16", r)]["success"]
            )
        ]
    result = dict(
        schema_version="search_value_saved_event_diagnostics/v1",
        candidate_commit=HEAD,
        plan_digest=DIGEST,
        verification="all_saved_event_reductions_and_pair_diagnostics_match",
        independent_implementation=True,
        independent_reviewer=False,
        generative_replay=False,
        counterfactual_rollout=False,
        proposal_completion_action_count="carried_from_generatively_authenticated_raw_not_independently_reenumerated",
        source_refs=[
            ref(PLAN),
            ref(OUT + "/COMMIT.json"),
            ref(OUT + "/summary.json"),
            ref(str(Path(__file__).relative_to(ROOT))),
        ],
        reduction=reduction,
        paired_choice_diagnostics=summary["paired_choice_diagnostics"],
        method_details=method_details,
        source_presence=source_presence,
        primary_gain_loss_cases=cases,
        additional_cell_diagnostics=[dict(key=list(k), **extras[k]) for k in found],
        winner=None,
        scientific_decision=None,
    )
    result["deterministic_digest"] = digest(result)
    sys.stdout.buffer.write(canonical(result) + b"\n")


if __name__ == "__main__":
    main()
