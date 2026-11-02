#!/usr/bin/env python3
"""Read-only, stdlib-only saved-event check of the sealed root-only PUCT-QMC study.

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
OUT = "artifacts/work/puct-qmc-root-development-20261029-a"
PLAN = "docs/preregistrations/countdown_search_value_puct_qmc_root_20261029.plan.json"
HEAD = "bc405e6249434a16c53e716fb68b516fce0a2902"
DIGEST = "ecb21dfb8de2067c2783371d9747bec37f4a7d69e65556eae90eb5c5d1170b0b"
METHODS = ("puct-qmc", "puct-iid", "puct")
ROOTS = tuple(range(1048576, 1048580))
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


def puct_scores(logp, means, visits, uniforms=None):
    assert len(logp) == len(means) == len(visits) > 0
    assert all(type(n) is int and n >= 0 for n in visits)
    assert all(type(x) is float and math.isfinite(x) and x <= 0 for x in logp)
    assert all(type(x) is float and math.isfinite(x) and 0 <= x <= 1 for x in means)
    probabilities = [math.exp(lp) for lp in logp]
    scale = math.sqrt(1.0 + sum(visits))
    bonuses = [1.0 * p * scale / (1.0 + n) for p, n in zip(probabilities, visits)]
    if uniforms is None:
        multipliers = [1.0] * len(logp)
    else:
        assert len(uniforms) == len(logp)
        assert all(
            type(u) is float and math.isfinite(u) and 0 < u < 1 for u in uniforms
        )
        multipliers = [0.5 + u for u in uniforms]
    scores = [q + bonus * w for q, bonus, w in zip(means, bonuses, multipliers)]
    return probabilities, bonuses, multipliers, scores


def active_gate(method, trajectory, depth):
    assert method in METHODS
    assert all(type(v) is int and v >= 0 for v in (trajectory, depth))
    return method != "puct" and trajectory > 0 and depth == 0


def semantics(trajectory, depth):
    active = trajectory > 0 and depth == 0
    return dict(
        selection_rule_id="binary_puct_c1_first_trajectory_then_root_only_bonus_times_half_plus_uniform/v1",
        selection_phase="fixed_puct_anchor"
        if trajectory == 0
        else "root_bounded_bonus_variation"
        if active
        else "fixed_puct_nonroot",
        perturbation_depths=[0],
        perturbation_point_usage="original_uniform" if active else "not_generated",
        multiplier="0.5 + original_open_unit_uniform" if active else "one",
        binary_return_mean_unchanged=True,
        normal_material_used_in_selection=False,
        tie_break="lowest_canonical_action_index",
    )


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
    nodes, points, node_counts = {}, {}, Counter()
    unbilled, consumed = set(), set()
    terminal_errors, choices, materials, anchor = [], [], [], []
    seen_states, terminals, root_choices = set(), Counter(), Counter()
    first_hit, exact_count, revisits, charge_index = None, 0, 0, 0
    last_terminal = None
    root_state = None
    pending_points = set()
    previous = "0" * 64
    events = raw["search_record"]["events"]
    for index, event in enumerate(events):
        assert event["index"] == index and event["previous_event_digest"] == previous
        assert event["event_digest"] == digest(
            {k: v for k, v in event.items() if k != "event_digest"}
        )
        previous = event["event_digest"]
        charge = event["charge"]
        if charge is not None:
            assert charge["charge_index"] == charge_index
            charge_index += 1
            assert set(charge["delta"]) == set(AXES)
            assert all(type(x) is int and x >= 0 for x in charge["delta"].values())
            usage.update(charge["delta"])
            equal(dict(usage), charge["usage_after"])
        k, p = event["kind"], event["payload"]
        if k not in ("selection_committed", "terminal_verified"):
            assert charge is None
        if k == "proposal_materialized":
            row = p["proposal"]
            state = tuple(row["state"])
            assert state not in proposals
            proposals[state] = row
            unbilled.add(state)
            assert row["action_order_digest"] == digest(row["action_order"])
            assert len(row["action_order"]) == len(row["prior_logp"])
            proposal_counts["materialized_rows"] += 1
            proposal_counts["root_action_evaluations"] += len(row["action_order"])
            proposal_counts["internal_transition_evaluations"] += row[
                "internal_transition_evaluations"
            ]
        elif k == "node_materialized":
            assert method != "puct" and last_terminal is not None
            assert tuple(p["state"]) == root_state and not nodes
            node = p["node_digest"]
            assert node not in nodes
            assert p["source"] == ("sobol" if method == "puct-qmc" else "iid")
            equal(p["action_order"], proposals[tuple(p["state"])]["action_order"])
            assert p["action_count"] == len(p["action_order"])
            nodes[node] = p
        elif k == "perturbation_draw":
            node = p["node_digest"]
            assert method != "puct" and last_terminal is not None and node in nodes
            assert p["node_visit_index"] == node_counts[node]
            node_counts[node] += 1
            assert (
                len(p["uniforms"]) == len(p["normals"]) == nodes[node]["action_count"]
            )
            assert all(
                type(u) is float and 0 < u < 1 and math.isfinite(u)
                for u in p["uniforms"]
            )
            assert all(type(z) is float and math.isfinite(z) for z in p["normals"])
            assert p["point_digest"] not in points
            points[p["point_digest"]] = p
            pending_points.add(p["point_digest"])
            assert len(pending_points) == 1
        elif k == "selection_committed":
            state = tuple(p["state"])
            if root_state is None:
                assert p["trajectory_index"] == p["depth"] == 0
                root_state = state
            assert p["depth"] == len(root_state) - len(state)
            active = active_gate(method, p["trajectory_index"], p["depth"])
            if method != "puct":
                equal(
                    p["selection_semantics"],
                    semantics(p["trajectory_index"], p["depth"]),
                )
                assert (
                    p["event_schema_version"]
                    == "countdown_puct_root_bounded_bonus_selection/v1"
                )
            revisits += state in seen_states
            seen_states.add(state)
            proposal = proposals[state]
            n = len(proposal["prior_logp"])
            histories = [
                posterior.get((state, i), dict(mean=0.0, visits=0, m2=0.0))
                for i in range(n)
            ]
            means, visits = (
                [h["mean"] for h in histories],
                [h["visits"] for h in histories],
            )
            anchored = not active
            if anchored:
                assert p["point_digest"] is None and not pending_points
                uniforms = None
                if p["trajectory_index"] == 0:
                    assert not nodes and not points
            else:
                assert pending_points == {p["point_digest"]}
                pending_points.clear()
                assert state == root_state and p["depth"] == 0
                point = points[p["point_digest"]]
                assert p["point_digest"] not in consumed
                consumed.add(p["point_digest"])
                assert nodes[point["node_digest"]]["state"] == p["state"]
                uniforms = point["uniforms"]
            probabilities, bonuses, multipliers, scores = puct_scores(
                proposal["prior_logp"], means, visits, uniforms
            )
            equal(scores, p["selection_values"])
            assert p["selection_values_digest"] == digest(scores)
            chosen = argmax(scores)
            assert chosen == p["action_index"] and p["selected_value"] == scores[chosen]
            equal(p["action"], proposal["action_order"][chosen])
            equal(p["scored_action_indices"], list(range(n)))
            expected_charge = dict.fromkeys(AXES, 0)
            expected_charge.update(
                edge_selections=1,
                transitions=1,
                legal_action_scores=n,
                generated_perturbation_coordinates=0 if anchored else n,
                proposal_state_evaluations=int(state in unbilled),
                proposal_action_scores=n if state in unbilled else 0,
            )
            equal(expected_charge, charge["delta"])
            unbilled.discard(state)
            if not exact_count:
                assert all(q == 0.0 for q in means)
            projection = {
                x: p[x] for x in ("state", "trajectory_index", "depth", "action")
            }
            choices.append(projection)
            trajectories.setdefault(p["trajectory_index"], []).append((state, chosen))
            if p["depth"] == 0:
                root_choices[chosen] += 1
            if p["trajectory_index"] == 0:
                anchor.append(
                    dict(
                        kind=k,
                        **{
                            x: p[x] for x in ("state", "action", "child_state", "depth")
                        },
                    )
                )
            materials.append(
                dict(
                    **projection,
                    perturbation_active=active,
                    action_index=chosen,
                    current_means=means,
                    current_visits=visits,
                    prior_probabilities=probabilities,
                    unperturbed_bonus=bonuses,
                    original_uniforms=uniforms,
                    bonus_multipliers=multipliers,
                    selected_scores=scores,
                    before_first_exact=not bool(exact_count),
                    passive_unperturbed_action_index=argmax(
                        [q + b for q, b in zip(means, bonuses)]
                    ),
                )
            )
        elif k == "terminal_verified":
            expected_charge = dict.fromkeys(AXES, 0)
            expected_charge["verifier_calls"] = 1
            equal(expected_charge, charge["delta"])
            error = terminal_error(p)
            terminal_errors.append(error)
            exact_count += error == 0
            terminals[digest(p["actions"])] += 1
            if error == 0 and first_hit is None:
                first_hit = dict(usage)
            last_terminal = (p["trajectory_index"], error)
            if p["trajectory_index"] == 0:
                anchor.append(
                    dict(kind=k, actions=p["actions"], verification=p["verification"])
                )
        elif k == "trajectory_backed_up":
            assert (
                last_terminal is not None and last_terminal[0] == p["trajectory_index"]
            )
            value = float(last_terminal[1] == 0)
            assert type(p["terminal_value"]) is float and p["terminal_value"] == value
            assert p["discount"] == 1.0 and p["order"] == "leaf_to_root"
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
    assert not unbilled and not pending_points and consumed == set(points)
    assert len(nodes) <= 1
    assert len(points) == sum(x["perturbation_active"] for x in materials)
    assert previous == raw["search_record"]["final_event_digest"]
    assert (
        len(events) == raw["search_record"]["event_count"]
        and events[-1]["kind"] == "search_finished"
    )
    finish, summary = events[-1]["payload"]["summary"], raw["summary"]
    equal(dict(usage), finish["ledger_usage"])
    equal(dict(usage), summary["actual_work"])
    assert usage["generated_perturbation_coordinates"] == sum(
        len(p["uniforms"]) for p in points.values()
    )
    assert usage["edge_selections"] == usage["transitions"] == len(choices)
    assert usage["legal_action_scores"] == sum(
        len(p["selected_scores"]) for p in materials
    )
    assert usage["verifier_calls"] == len(terminal_errors)
    assert finish["selected_source_point_count"] == len(points)
    assert finish["budget_valid"] is True and finish["stop_reason"] in (
        "primary_budget_blocked",
        "method_complete",
    )
    assert finish["terminal_count"] == len(terminal_errors) and finish[
        "success_any"
    ] == (exact_count > 0)
    assert finish["exact_terminal_count"] == exact_count
    limits = raw["run_identity"]["search_run_identity"]["work_limits"]
    equal(limits, {a: 512 if a == "legal_action_scores" else 100000 for a in AXES})
    unspent = {a: limits[a] - usage[a] for a in AXES}
    assert all(v >= 0 for v in unspent.values())
    assert all(usage[a] < limits[a] for a in AXES if a != "legal_action_scores")
    equal(unspent, summary["unspent_work"])
    if finish["stop_reason"] == "primary_budget_blocked":
        assert finish["stop_blocked_axes"] == ["legal_action_scores"]
        assert (
            usage["legal_action_scores"]
            + finish["stop_attempted_charge"]["legal_action_scores"]
            > limits["legal_action_scores"]
        )
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
        passive_unperturbed_flips=sum(
            x["action_index"] != x["passive_unperturbed_action_index"]
            for x in materials
        ),
        pre_first_exact_passive_unperturbed_flips=sum(
            x["before_first_exact"]
            and x["action_index"] != x["passive_unperturbed_action_index"]
            for x in materials
        ),
        pre_first_exact_selections=sum(x["before_first_exact"] for x in materials),
        selected_not_max_prior=sum(
            x["action_index"] != argmax(x["prior_probabilities"]) for x in materials
        ),
        terminal_errors=terminal_errors,
        choice_sequence_digest=digest(choices),
        first_trajectory_digest=digest(anchor),
        anchor_selection_count=sum(x["trajectory_index"] == 0 for x in choices),
        perturbation_points=len(points),
        active_root_selections=sum(x["perturbation_active"] for x in materials),
        fixed_deep_selections=sum(x["depth"] > 0 for x in materials),
        fixed_post_anchor_deep_selections=sum(
            x["depth"] > 0 and x["trajectory_index"] > 0 for x in materials
        ),
        root_draw_indexes=[p["node_visit_index"] for p in points.values()],
        deep_passive_unperturbed_flips=sum(
            x["depth"] > 0
            and x["action_index"] != x["passive_unperturbed_action_index"]
            for x in materials
        ),
        inactive_material_zero=True,
        only_root_material_nodes=True,
        root_committed_indexes_contiguous=True,
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
    i = next(
        (j for j, (a, b) in enumerate(zip(lc, rc)) if a != b), min(len(lc), len(rc))
    )
    assert left[1]["first_trajectory_digest"] == right[1]["first_trajectory_digest"]
    if i < min(len(lc), len(rc)):
        assert (
            lc[i]["depth"] == rc[i]["depth"] == 0 and lc[i]["state"] == rc[i]["state"]
        )
    return dict(
        same_action_sequence=lc == rc,
        common_action_prefix_length=i,
        same_first_trajectory=True,
        first_choice_divergence=None
        if i == min(len(lc), len(rc))
        else dict(
            selection_index=i,
            qmc=left[3][i],
            iid=right[3][i],
            same_state=lc[i]["state"] == rc[i]["state"],
        ),
        one_sequence_ends_at_common_prefix=i == min(len(lc), len(rc))
        and len(lc) != len(rc),
        action_sequence_lengths=[len(lc), len(rc)],
        action_sequence_digests=[digest(lc), digest(rc)],
        passive_same_history_unperturbed_choice_flips=[
            left[1]["passive_unperturbed_flips"],
            right[1]["passive_unperturbed_flips"],
        ],
        fixed_nonroot_selection_scores_verified=True,
        active_perturbation_depths=[0],
        binary_pre_first_exact_all_means_zero=True,
        passive_flip_is_not_counterfactual_rollout=True,
        matched_root_labels_are_not_common_random_draws=True,
        whole_trajectory_common_random_numbers_claim=False,
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
    assert summary["status"] == "ALL_CELLS_REPLAYED_PUCT_QMC_ROOT_ANALYSIS_COMPLETE"
    assert (
        summary["replayed_cells"] == 4608
        and summary["cross_budget_prefix_pairs"] == 0
        and summary["matched_first_trajectory_sources"] == 512
    )
    equal(ref(OUT + "/COMMIT.json"), summary["commit"])
    cohort = read(commit["cohort"]["path"], commit["cohort"])
    assert len(cohort["tasks"]) == 512
    reduction = summary["reduction"]
    assert reduction["schema_version"] == "puct_qmc_root_source_reduction/v1"
    assert (
        reduction["source_count"] == 512
        and reduction["cell_count"] == 4608
        and reduction["stochastic_roots"] == list(ROOTS)
    )
    expected = {
        (s, m, r)
        for s in range(512)
        for m in METHODS
        for r in (ROOTS if m != "puct" else (0,))
    }
    found, extras, cache, pair_results, anchors = {}, {}, {}, {}, {}
    for i, row in enumerate(commit["cells"]):
        key = tuple(row["key"])
        assert key in expected and key not in found and row["index"] == i
        equal(row["key"], plan["coordinates"][i])
        raw = read(row["file"]["path"], row["file"])
        assert raw["schema_version"] == "countdown_puct_qmc_root_cell/v1"
        assert (
            raw["run_identity"]["spec"]["method"] == key[1]
            and raw["run_identity"]["root_seed"] == key[2]
        )
        result = scan(raw, key[1])
        found[key], extras[key] = result[:2]
        equal(dict(key=list(key), metrics=result[0]), reduction["cells"][i])
        anchor = result[1]["first_trajectory_digest"]
        assert anchors.setdefault(key[0], anchor) == anchor
        if key[1] != "puct":
            pairkey = (key[0], key[2])
            cache.setdefault(pairkey, {})[key[1]] = result
            if len(cache[pairkey]) == 2:
                item = cache.pop(pairkey)
                pair_results[pairkey] = check_pair(item["puct-qmc"], item["puct-iid"])
        assert len(cache) <= 1
    assert set(found) == expected and not cache and len(anchors) == 512
    assert len(pair_results) == len(summary["paired_choice_diagnostics"]) == 2048
    for row in summary["paired_choice_diagnostics"]:
        equal(
            pair_results[(row["source_slot"], row["root_seed"])],
            {k: v for k, v in row.items() if k not in ("source_slot", "root_seed")},
        )
    for method, actual in reduction["methods"].items():
        keys = [k for k in found if k[1] == method]
        assert (
            method in METHODS
            and actual["source_count"] == 512
            and actual["rows_per_source"] == (1 if method == "puct" else 4)
        )
        equal(
            sum_metrics([found[k] for k in keys]),
            {
                k: v
                for k, v in actual.items()
                if k not in ("by_source", "by_root", "source_count", "rows_per_source")
            },
        )
        assert len(actual["by_source"]) == 512
        for source, row in enumerate(actual["by_source"]):
            equal(
                row,
                dict(
                    source_slot=source,
                    **sum_metrics([found[k] for k in keys if k[0] == source]),
                ),
            )
        assert [x["root_seed"] for x in actual["by_root"]] == (
            [0] if method == "puct" else list(ROOTS)
        )
        for row in actual["by_root"]:
            equal(
                row,
                dict(
                    root_seed=row["root_seed"],
                    **sum_metrics([found[k] for k in keys if k[2] == row["root_seed"]]),
                ),
            )
    assert len(reduction["contrasts"]) == 3
    for c, (left, right) in zip(
        reduction["contrasts"],
        (("puct-qmc", "puct"), ("puct-qmc", "puct-iid"), ("puct-iid", "puct")),
    ):
        assert c["contrast"] == left + "-minus-" + right

        def paired(slots, roots):
            return [
                (
                    found[(s, left, r)],
                    found[(s, right, r if right == "puct-iid" else 0)],
                )
                for s in slots
                for r in roots
            ]

        allpairs = paired(range(512), ROOTS)
        values = [
            Fraction(
                sum(
                    int(a["success"]) - int(b["success"])
                    for a, b in paired((s,), ROOTS)
                ),
                4,
            )
            for s in range(512)
        ]
        equal(
            moments(values, left == "puct-qmc" and right == "puct"), c["source_moments"]
        )
        equal(differences(allpairs), {k: c[k] for k in differences([])})
        assert c["deterministic_baseline_rows_referenced_not_replicated"] == (
            right != "puct-iid"
        )
        for source in range(512):
            equal(
                c["by_source"][source],
                dict(source_slot=source, **differences(paired((source,), ROOTS))),
            )
            d = differences(paired([s for s in range(512) if s != source], ROOTS))
            equal(
                c["leave_one_source_out"][source],
                dict(
                    omitted=source, **d, mean_rational=rat(Fraction(d["net"], 511 * 4))
                ),
            )
        for j, root in enumerate(ROOTS):
            equal(
                c["by_root"][j],
                dict(root_seed=root, **differences(paired(range(512), (root,)))),
            )
            d = differences(paired(range(512), [r for r in ROOTS if r != root]))
            equal(
                c["leave_one_root_out"][j],
                dict(omitted=root, **d, mean_rational=rat(Fraction(d["net"], 512 * 3))),
            )
    equal(reduction["primary"], reduction["contrasts"][0]["source_moments"])
    details = {}
    for method in METHODS:
        keys = [k for k in found if k[1] == method]
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
            source_any_root_success_count=sum(
                any(found[k]["success"] for k in keys if k[0] == s) for s in range(512)
            ),
            source_all_roots_success_count=sum(
                all(found[k]["success"] for k in keys if k[0] == s) for s in range(512)
            ),
            **{
                field: sum(extras[k][field] for k in keys)
                for field in (
                    "exact_terminal_count",
                    "unique_terminal_action_sequences",
                    "repeated_terminal_observations",
                    "passive_unperturbed_flips",
                    "pre_first_exact_passive_unperturbed_flips",
                    "pre_first_exact_selections",
                    "selected_not_max_prior",
                    "anchor_selection_count",
                    "perturbation_points",
                    "active_root_selections",
                    "fixed_deep_selections",
                    "fixed_post_anchor_deep_selections",
                    "deep_passive_unperturbed_flips",
                )
            },
        )
    cases = {}
    for method in METHODS[:2]:
        categories = {k: [] for k in ("gain", "loss", "both_success", "neither")}
        for s in range(512):
            control = found[(s, "puct", 0)]
            for root in ROOTS:
                row = found[(s, method, root)]
                cat = (
                    "both_success"
                    if row["success"] and control["success"]
                    else "gain"
                    if row["success"]
                    else "loss"
                    if control["success"]
                    else "neither"
                )
                categories[cat].append(
                    dict(source_slot=s, root_seed=root, candidate=row, baseline=control)
                )
        cases[method] = categories
    result = dict(
        schema_version="puct_qmc_root_saved_event_diagnostics/v1",
        candidate_commit=HEAD,
        plan_digest=DIGEST,
        verification="all_saved_event_reductions_binary_backup_root_only_gate_contiguous_draws_fixed_deep_PUCT_pairs_and_anchors_match",
        no_inactive_planning_evidence="candidate_source_and_prior_generative_replay; saved_trace_checks_no_material_charge_or_index_advance",
        independent_implementation=True,
        independent_reviewer=False,
        generative_replay=False,
        counterfactual_rollout=False,
        proposal_completion_action_count="carried_from_generatively_authenticated_raw_not_independently_reenumerated",
        observed_analysis_status=summary["status"],
        source_refs=[
            ref(PLAN),
            ref(OUT + "/COMMIT.json"),
            ref(OUT + "/summary.json"),
            ref(str(Path(__file__).relative_to(ROOT))),
        ],
        reduction=reduction,
        paired_choice_diagnostics=summary["paired_choice_diagnostics"],
        method_details=details,
        matched_anchor_source_count=len(anchors),
        source_anchor_digests=[
            dict(source_slot=s, digest=h) for s, h in sorted(anchors.items())
        ],
        candidate_baseline_outcome_cases=cases,
        additional_cell_diagnostics=[dict(key=list(k), **extras[k]) for k in found],
        winner=None,
        scientific_decision=None,
    )
    result["deterministic_digest"] = digest(result)
    sys.stdout.buffer.write(canonical(result) + b"\n")


if __name__ == "__main__":
    main()
