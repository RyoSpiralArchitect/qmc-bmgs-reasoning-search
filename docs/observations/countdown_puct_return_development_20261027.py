#!/usr/bin/env python3
"""Read-only, stdlib-only saved-event check of the sealed deterministic PUCT-return study.

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
OUT = "artifacts/work/puct-return-development-20261027-a"
PLAN = "docs/preregistrations/countdown_search_value_puct_return_20261027.plan.json"
HEAD = "369221b73d91099a21c6ba67e6f2ede2b0857e26"
DIGEST = "722dcf39711678e7c14dc06d1bcf024e8999c4b26f494fb6c20b0e025e1791df"
METHODS = ("puct-dense16", "puct")
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


def puct_scores(logp, means, visits):
    assert len(logp) == len(means) == len(visits) > 0
    assert all(type(n) is int and n >= 0 for n in visits)
    probabilities = [math.exp(lp) for lp in logp]
    scale = math.sqrt(1.0 + sum(visits))
    bonuses = [1.0 * p * scale / (1.0 + n) for p, n in zip(probabilities, visits)]
    return probabilities, bonuses, [q + b for q, b in zip(means, bonuses)]


def backup(before, value):
    count = before["visits"] + 1
    delta = value - before["mean"]
    mean = before["mean"] + delta / count
    return dict(visits=count, mean=mean, m2=before["m2"] + delta * (value - mean))


def terminal_error(payload):
    v = payload["verification"]
    assert type(v["success"]) is bool and v["source_use_exact"] is True
    assert type(v["target"]) is int and type(v["final_value"]) is int
    state = list(payload["states"][0])
    assert len(payload["actions"]) == len(v["steps"]) == len(state) - 1
    for i, action in enumerate(payload["actions"]):
        a, b, op = action["left"], action["right"], action["operator"]
        assert type(a) is int and type(b) is int and a > 0 and b > 0
        remaining = list(state)
        remaining.remove(a)
        remaining.remove(b)
        if op == "+":
            value = a + b
        elif op == "-":
            assert a > b
            value = a - b
        elif op == "*":
            value = a * b
        else:
            assert op == "/" and a % b == 0
            value = a // b
        step = v["steps"][i]
        equal(action, step["action"])
        equal(state, step["state_before"])
        state = sorted(remaining + [value])
        equal(state, step["state_after"])
        equal(state, payload["states"][i + 1])
        assert step["result"] == value
    assert state == [v["final_value"]] == v["final_state"]
    error = abs(v["final_value"] - v["target"])
    assert v["success"] == (error == 0)
    return error


def scan(raw, method):
    assert method in METHODS
    usage = Counter({a: 0 for a in AXES})
    proposal_counts = Counter({k: 0 for k in PROPOSAL})
    proposals, posterior, trajectories = {}, {}, {}
    terminal_errors, choices, materials = [], [], []
    seen_states, terminals, root_choices = set(), Counter(), Counter()
    first_hit, exact_count, revisits, charge_index = None, 0, 0, 0
    last_terminal = None
    nonexact_positive_backups = 0
    events = raw["search_record"]["events"]
    for event in events:
        charge = event["charge"]
        if charge is not None:
            assert charge["charge_index"] == charge_index
            charge_index += 1
            assert set(charge["delta"]) == set(AXES)
            assert all(type(x) is int and x >= 0 for x in charge["delta"].values())
            usage.update(charge["delta"])
            equal(dict(usage), charge["usage_after"])
        k, p = event["kind"], event["payload"]
        if k == "proposal_materialized":
            row = p["proposal"]
            state = tuple(row["state"])
            assert state not in proposals
            proposals[state] = row
            proposal_counts["materialized_rows"] += 1
            proposal_counts["root_action_evaluations"] += len(row["action_order"])
            proposal_counts["internal_transition_evaluations"] += row[
                "internal_transition_evaluations"
            ]
        elif k == "selection_committed":
            state = tuple(p["state"])
            revisits += state in seen_states
            seen_states.add(state)
            proposal = proposals[state]
            histories = [
                posterior.get((state, i), dict(mean=0.0, visits=0, m2=0.0))
                for i in range(len(proposal["prior_logp"]))
            ]
            means = [h["mean"] for h in histories]
            visits = [h["visits"] for h in histories]
            probabilities, bonuses, scores = puct_scores(
                proposal["prior_logp"], means, visits
            )
            equal(scores, p["selection_values"])
            chosen = argmax(scores)
            assert chosen == p["action_index"] and p["selected_value"] == scores[chosen]
            equal(p["action"], proposal["action_order"][chosen])
            assert p["point_digest"] is None
            if method == "puct" and not exact_count:
                assert all(q == 0.0 for q in means)
            projection = {
                x: p[x] for x in ("state", "trajectory_index", "depth", "action")
            }
            choices.append(projection)
            trajectories.setdefault(p["trajectory_index"], []).append((state, chosen))
            if p["depth"] == 0:
                root_choices[chosen] += 1
            materials.append(
                dict(
                    **projection,
                    action_index=chosen,
                    current_means=means,
                    current_visits=visits,
                    prior_probabilities=probabilities,
                    exploration_bonus=bonuses,
                    selected_scores=scores,
                    before_first_exact=not bool(exact_count),
                    passive_mean_off_action_index=argmax(bonuses),
                )
            )
        elif k == "terminal_verified":
            error = terminal_error(p)
            terminal_errors.append(error)
            exact_count += error == 0
            terminals[digest(p["actions"])] += 1
            if error == 0 and first_hit is None:
                first_hit = dict(usage)
            last_terminal = (p["trajectory_index"], error)
        elif k == "trajectory_backed_up":
            assert (
                last_terminal is not None and last_terminal[0] == p["trajectory_index"]
            )
            error = last_terminal[1]
            value = (
                float(Fraction(16, 16 + error))
                if method == "puct-dense16"
                else float(error == 0)
            )
            value = max(math.ulp(0.0), value) if method == "puct-dense16" else value
            assert (
                p["terminal_value"] == value
                and p["discount"] == 1.0
                and p["order"] == "leaf_to_root"
            )
            if method == "puct-dense16":
                assert p["terminal_absolute_error"] == error
                # The frozen evidence contract encodes exact hits as 1/1 while
                # retaining scale=16; non-exact returns use 16/(16+error).
                assert p["terminal_value_scale"] == 16
                assert p["terminal_value_numerator"] == (1 if error == 0 else 16)
                assert p["terminal_value_denominator"] == (
                    1 if error == 0 else 16 + error
                )
                nonexact_positive_backups += error > 0 and value > 0.0
            update_keys = [(tuple(u["state"]), u["action_index"]) for u in p["updates"]]
            equal(update_keys, list(reversed(trajectories[p["trajectory_index"]])))
            for u, key in zip(p["updates"], update_keys):
                before = posterior.get(key, dict(mean=0.0, visits=0, m2=0.0))
                equal(before, u["before"])
                expected = backup(before, value)
                equal(expected, u["after"])
                posterior[key] = expected
        else:
            assert k in ("budget_stopped", "search_finished"), k
    assert events[-1]["kind"] == "search_finished"
    finish, summary = events[-1]["payload"]["summary"], raw["summary"]
    equal(dict(usage), finish["ledger_usage"])
    equal(dict(usage), summary["actual_work"])
    assert usage["generated_perturbation_coordinates"] == 0
    assert usage["edge_selections"] == usage["transitions"] == len(choices)
    assert usage["verifier_calls"] == len(terminal_errors)
    assert finish["budget_valid"] is True
    assert finish["stop_reason"] in ("primary_budget_blocked", "method_complete")
    assert finish["terminal_count"] == len(terminal_errors)
    assert finish["success_any"] == (exact_count > 0)
    assert finish["exact_terminal_count"] == exact_count
    limits = raw["run_identity"]["search_run_identity"]["work_limits"]
    equal(limits, {a: 512 if a == "legal_action_scores" else 100000 for a in AXES})
    unspent = {a: limits[a] - usage[a] for a in AXES}
    assert all(v >= 0 for v in unspent.values())
    assert all(usage[a] < limits[a] for a in AXES if a != "legal_action_scores")
    equal(unspent, summary["unspent_work"])
    for name in PROPOSAL:
        if name != "completion_legal_action_evaluations":
            assert summary["proposal_work"][name] == proposal_counts[name]
    assert proposal_counts["materialized_rows"] == usage["proposal_state_evaluations"]
    assert proposal_counts["root_action_evaluations"] == usage["proposal_action_scores"]
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
        selection_count=len(choices),
        stop_reason=finish["stop_reason"],
        proposal_work=dict(proposal_counts),
    )
    for name in ("minimum_terminal_error", "missing_terminal", "first_exact_work"):
        equal(metrics[name], summary[name])
    equal(metrics["censored_at_work"], summary["no_exact_observation_censored_at_work"])
    extra = dict(
        exact_terminal_count=exact_count,
        unique_terminal_action_sequences=len(terminals),
        repeated_terminal_observations=len(terminal_errors) - len(terminals),
        maximum_terminal_sequence_multiplicity=max(terminals.values(), default=0),
        root_selected_action_counts={
            str(k): v for k, v in sorted(root_choices.items())
        },
        unique_root_selected_actions=len(root_choices),
        nonexact_positive_backups=nonexact_positive_backups,
        passive_mean_off_flips=sum(
            x["action_index"] != x["passive_mean_off_action_index"] for x in materials
        ),
        pre_first_exact_passive_mean_off_flips=sum(
            x["before_first_exact"]
            and x["action_index"] != x["passive_mean_off_action_index"]
            for x in materials
        ),
        pre_first_exact_selections=sum(x["before_first_exact"] for x in materials),
        selected_not_max_prior=sum(
            x["action_index"] != argmax(x["prior_probabilities"]) for x in materials
        ),
        selected_q_exceeds_bonus=sum(
            x["current_means"][x["action_index"]]
            > x["exploration_bonus"][x["action_index"]]
            for x in materials
        ),
        terminal_errors=terminal_errors,
        choice_sequence_digest=digest(choices),
        first_trajectory_digest=digest(
            [x for x in choices if x["trajectory_index"] == 0]
        ),
        revisit_definition="repeated_states_in_ordinary_selection_committed",
    )
    return metrics, extra, choices, materials


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
    lc, rc = left[2], right[2]
    lm, rm = left[3], right[3]
    mismatch = next(
        (i for i, (a, b) in enumerate(zip(lc, rc)) if a != b), min(len(lc), len(rc))
    )
    divergence = (
        None
        if mismatch == min(len(lc), len(rc))
        else dict(
            selection_index=mismatch,
            dense16=lm[mismatch],
            binary=rm[mismatch],
            same_state=lc[mismatch]["state"] == rc[mismatch]["state"],
        )
    )
    return dict(
        same_action_sequence=lc == rc,
        common_action_prefix_length=mismatch,
        same_first_trajectory=[r for r in lc if r["trajectory_index"] == 0]
        == [r for r in rc if r["trajectory_index"] == 0],
        first_choice_divergence=divergence,
        one_sequence_ends_at_common_prefix=mismatch == min(len(lc), len(rc))
        and len(lc) != len(rc),
        action_sequence_lengths=[len(lc), len(rc)],
        action_sequence_digests=[digest(lc), digest(rc)],
        passive_same_history_mean_off_choice_flips=[
            left[1]["passive_mean_off_flips"],
            right[1]["passive_mean_off_flips"],
        ],
        pre_first_exact_passive_mean_off_choice_flips=[
            left[1]["pre_first_exact_passive_mean_off_flips"],
            right[1]["pre_first_exact_passive_mean_off_flips"],
        ],
        binary_pre_first_exact_all_means_zero=True,
        passive_flip_is_not_counterfactual_rollout=True,
        stochastic_pairing_applicable=False,
    )


def main():
    plan, commit, summary = (
        read(PLAN),
        read(OUT + "/COMMIT.json"),
        read(OUT + "/summary.json"),
    )
    assert plan["deterministic_digest"] == DIGEST
    assert commit["candidate_commit"] == summary["candidate_commit"] == HEAD
    assert commit["plan_digest"] == summary["plan_digest"] == DIGEST
    assert summary["status"] == "ALL_CELLS_REPLAYED_PRIOR_TILT_ANALYSIS_COMPLETE"
    assert (
        summary["replayed_cells"] == 1024 and summary["cross_budget_prefix_pairs"] == 0
    )
    equal(ref(OUT + "/COMMIT.json"), summary["commit"])
    cohort = read(commit["cohort"]["path"], commit["cohort"])
    assert len(cohort["tasks"]) == 512
    reduction = summary["reduction"]
    assert reduction["schema_version"] == "puct_return_source_reduction/v1"
    assert reduction["source_count"] == 512 and reduction["cell_count"] == 1024
    assert (
        reduction["stochastic_roots"] == []
        and reduction["deterministic_rows_are_not_seed_replicates"] is True
    )
    expected = {(s, m, 0) for s in range(512) for m in METHODS}
    found, extras, cache, pair_results = {}, {}, {}, {}
    for i, row in enumerate(commit["cells"]):
        key = tuple(row["key"])
        assert key in expected and key not in found and row["index"] == i
        equal(row["key"], plan["coordinates"][i])
        raw = read(row["file"]["path"], row["file"])
        assert raw["schema_version"] == "countdown_puct_return_cell/v1"
        assert (
            raw["run_identity"]["spec"]["method"] == key[1]
            and raw["run_identity"]["root_seed"] == 0
        )
        result = scan(raw, key[1])
        found[key], extras[key] = result[:2]
        equal(dict(key=list(key), metrics=result[0]), reduction["cells"][i])
        cache[key[1]] = result
        if len(cache) == 2:
            pair_results[key[0]] = check_pair(
                cache.pop(METHODS[0]), cache.pop(METHODS[1])
            )
    assert set(found) == expected and not cache
    assert len(pair_results) == len(summary["paired_choice_diagnostics"]) == 512
    for row in summary["paired_choice_diagnostics"]:
        assert row["root_seed"] == 0
        equal(
            pair_results[row["source_slot"]],
            {k: v for k, v in row.items() if k not in ("source_slot", "root_seed")},
        )
    for method, actual in reduction["methods"].items():
        assert (
            method in METHODS
            and actual["source_count"] == 512
            and actual["rows_per_source"] == 1
        )
        equal(
            sum_metrics([found[(s, method, 0)] for s in range(512)]),
            {
                k: v
                for k, v in actual.items()
                if k not in ("by_source", "source_count", "rows_per_source")
            },
        )
        assert len(actual["by_source"]) == 512
        for s, row in enumerate(actual["by_source"]):
            equal(row, dict(source_slot=s, **sum_metrics([found[(s, method, 0)]])))
    assert len(reduction["contrasts"]) == 1
    c = reduction["contrasts"][0]
    assert c["contrast"] == "puct-dense16-minus-puct"
    paired = [
        (found[(s, METHODS[0], 0)], found[(s, METHODS[1], 0)]) for s in range(512)
    ]
    values = [Fraction(int(a["success"]) - int(b["success"])) for a, b in paired]
    equal(moments(values, True), c["source_moments"])
    equal(c["source_moments"], reduction["primary"])
    equal(differences(paired), {k: c[k] for k in differences([])})
    assert len(c["by_source"]) == len(c["leave_one_source_out"]) == 512
    for s in range(512):
        equal(c["by_source"][s], dict(source_slot=s, **differences([paired[s]])))
        rest = paired[:s] + paired[s + 1 :]
        d = differences(rest)
        equal(
            c["leave_one_source_out"][s],
            dict(omitted=s, **d, mean_rational=rat(Fraction(d["net"], 511))),
        )
    details = {}
    for method in METHODS:
        keys = [(s, method, 0) for s in range(512)]
        details[method] = dict(
            first_exact_primary_scores=sorted(
                found[k]["first_exact_work"]["legal_action_scores"]
                for k in keys
                if found[k]["success"]
            ),
            no_hit_censoring_primary_scores=sorted(
                found[k]["censored_at_work"]["legal_action_scores"]
                for k in keys
                if not found[k]["success"]
            ),
            stop_reasons=dict(Counter(found[k]["stop_reason"] for k in keys)),
            selection_count=sum(found[k]["selection_count"] for k in keys),
            **{
                field: sum(extras[k][field] for k in keys)
                for field in (
                    "exact_terminal_count",
                    "unique_terminal_action_sequences",
                    "repeated_terminal_observations",
                    "nonexact_positive_backups",
                    "passive_mean_off_flips",
                    "pre_first_exact_passive_mean_off_flips",
                    "pre_first_exact_selections",
                    "selected_not_max_prior",
                    "selected_q_exceeds_bonus",
                )
            },
        )
    cases = {}
    for category in ("gain", "loss", "both_success", "neither"):
        cases[category] = [
            dict(source_slot=s, dense16=a, binary=b)
            for s, (a, b) in enumerate(paired)
            if category
            == (
                "both_success"
                if a["success"] and b["success"]
                else "gain"
                if a["success"]
                else "loss"
                if b["success"]
                else "neither"
            )
        ]
    result = dict(
        schema_version="puct_return_saved_event_diagnostics/v1",
        candidate_commit=HEAD,
        plan_digest=DIGEST,
        verification="all_saved_event_reductions_backup_updates_and_pair_diagnostics_match",
        independent_implementation=True,
        independent_reviewer=False,
        generative_replay=False,
        counterfactual_rollout=False,
        proposal_completion_action_count="carried_from_generatively_authenticated_raw_not_independently_reenumerated",
        observed_analysis_status=summary["status"],
        known_analysis_status_label_uses_old_study_name=True,
        source_refs=[
            ref(PLAN),
            ref(OUT + "/COMMIT.json"),
            ref(OUT + "/summary.json"),
            ref(str(Path(__file__).relative_to(ROOT))),
        ],
        reduction=reduction,
        paired_choice_diagnostics=summary["paired_choice_diagnostics"],
        method_details=details,
        primary_outcome_cases=cases,
        additional_cell_diagnostics=[dict(key=list(k), **extras[k]) for k in found],
        winner=None,
        scientific_decision=None,
    )
    result["deterministic_digest"] = digest(result)
    sys.stdout.buffer.write(canonical(result) + b"\n")


if __name__ == "__main__":
    main()
