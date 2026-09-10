"""Outcome-ordered 2 x 2 reduction, without input admission or run authority.

The independent IO wrapper first establishes provenance, all-cell replay and
96 exact prefixes. This pure kernel never certifies its own input integrity.
"""

from __future__ import annotations

from collections import Counter
from fractions import Fraction
from itertools import product
from types import SimpleNamespace
from typing import NamedTuple

from qmc_bmgs.experiments import countdown_thompson_dense_scale_analysis as prior
from qmc_bmgs.substrate.trace import canonical_json, sha256_json


DOMAIN = "qmc-bmgs-countdown-thompson-feedback-budget/v1"
BUDGETS, SCALES, SEEDS = (256, 512), (0, 16), (8192, 8193, 8194, 8195)
ARMS = ((256, 0), (256, 16), (512, 0), (512, 16))
ARM_NAMES = ("Y0_256", "Y16_256", "Y0_512", "Y16_512")
AXES = (
    "proposal_state_evaluations",
    "proposal_action_scores",
    "legal_action_scores",
    "generated_perturbation_coordinates",
    "edge_selections",
    "transitions",
    "verifier_calls",
)
STAGES = (
    "qualification_and_provenance",
    "all_cell_identity_budget_and_two_stage_replay",
    "96_full_event_budget_prefixes",
    "outcome_redacted_common_prefix_mechanism",
    "terminal_error_reductions",
    "exact_success_and_fixed_screen",
)


def require(value, message):
    if not value:
        raise ValueError(message)


def ratio(numerator, denominator):
    value = Fraction(numerator, denominator)
    return dict(numerator=value.numerator, denominator=value.denominator)


def sign(value):
    return (value > 0) - (value < 0)


class SelectionTiming(NamedTuple):
    coordinate: tuple[int, int]
    index: int
    before: tuple[int, ...]
    after: tuple[int, ...]


class OpportunityView(NamedTuple):
    selections: tuple[SelectionTiming, ...]
    terminals: tuple[tuple[int, int], ...]
    backups: tuple[tuple[int, int], ...]


def project_opportunity(trace: dict, limits: dict) -> OpportunityView:
    """Timing/charge allowlist. Never dereference verification or summary fields."""
    usage = dict.fromkeys(AXES, 0)
    selections, terminals, backups = [], [], []
    for event in trace["events"]:
        before = tuple(limits[a] - usage[a] for a in AXES)
        if event["charge"] is not None:
            usage = {a: event["charge"]["usage_after"][a] for a in AXES}
        kind = event["kind"]
        if kind == "selection_committed":
            p = event["payload"]
            selections.append(
                SelectionTiming(
                    (p["trajectory_index"], p["depth"]),
                    event["index"],
                    before,
                    tuple(limits[a] - usage[a] for a in AXES),
                )
            )
        elif kind in ("terminal_verified", "trajectory_backed_up"):
            p = event["payload"]
            (terminals if kind == "terminal_verified" else backups).append(
                (p["trajectory_index"], event["index"])
            )
    return OpportunityView(tuple(selections), tuple(terminals), tuple(backups))


def opportunity(view: OpportunityView, index: int) -> dict:
    ids = [trajectory for trajectory, event in view.terminals if event > index]
    return dict(
        completed_terminal_count=len(ids),
        terminal_trajectory_ids=ids,
        bin="2+" if len(ids) >= 2 else str(len(ids)),
    )


def pair_opportunity(pair: dict, left: OpportunityView, right: OpportunityView) -> dict:
    """Only frozen, outcome-redacted views enter this decision-pair extension."""
    require(
        type(left) is OpportunityView and type(right) is OpportunityView,
        "redacted timing views required",
    )
    support = pair["shared_prefix_backup_values"]
    different = [
        r
        for r in support
        if r["baseline_applied_value"].hex() != r["scaled_applied_value"].hex()
    ]
    first_backup = None
    if different:
        first = different[0]
        t = first["trajectory_index"]
        first_backup = dict(
            **first,
            baseline_opportunity=opportunity(left, dict(left.backups)[t]),
            scaled_opportunity=opportunity(right, dict(right.backups)[t]),
        )
    div = pair["first_action_divergence"]
    result = dict(
        first_scale_dependent_backup=first_backup,
        backup_state="differing_applied_backup"
        if different
        else "absent_scale_dependent_backup",
        divergence_window=None,
        opportunity_bin="no_divergence",
    )
    if div is None:
        return result
    require(
        pair["feedback_informed"] is bool(different), "feedback support flag differs"
    )
    coordinate = div["trajectory_index"], div["depth"]
    windows = {}
    for label, view in (("baseline", left), ("scaled", right)):
        selected = next(s for s in view.selections if s.coordinate == coordinate)
        require(
            all(
                dict(view.backups)[r["trajectory_index"]] < selected.index
                for r in support
            ),
            "common-prefix backup must precede divergence",
        )
        later = opportunity(view, selected.index)
        windows[label] = dict(
            selection_event_index=selected.index,
            remaining_before_step_charge=dict(zip(AXES, selected.before)),
            remaining_after_step_charge=dict(zip(AXES, selected.after)),
            opportunity=later,
            diverged_trajectory_completed=coordinate[0]
            in later["terminal_trajectory_ids"],
        )
    result.update(
        divergence_window=windows,
        opportunity_bin=windows["scaled"]["opportunity"]["bin"],
    )
    return result


def factorial(successes: list, informed: list) -> dict:
    """Exact finite-matrix arithmetic. No provenance claim or scientific decision."""
    require(
        type(successes) is list
        and type(informed) is list
        and len(successes) == len(informed) == 12,
        "twelve task clusters required",
    )
    task_rows, blocks, patterns = [], [], Counter()
    for slot, (seeds, support) in enumerate(zip(successes, informed)):
        require(
            type(seeds) is list
            and type(support) is list
            and len(seeds) == len(support) == 4,
            "four ordered seeds per task required",
        )
        counts, new, lost = [0] * 4, [0] * 2, [0] * 2
        for seed, bits, guarded in zip(SEEDS, seeds, support):
            require(
                type(bits) is list
                and len(bits) == 4
                and all(type(x) is int and x in (0, 1) for x in bits)
                and type(guarded) is bool,
                "plain binary arm values and boolean support required",
            )
            require(
                bits[2] >= bits[0] and bits[3] >= bits[1], "forbidden success pattern"
            )
            patterns["".join(map(str, bits))] += 1
            counts = [a + b for a, b in zip(counts, bits)]
            for j, offset in enumerate((0, 2)):
                new[j] += int(bits[offset] == 0 and bits[offset + 1] == 1)
                lost[j] += int(bits[offset] == 1 and bits[offset + 1] == 0)
            low, high = bits[1] - bits[0], bits[3] - bits[2]
            blocks.append(
                dict(
                    task_slot=slot,
                    seed=seed,
                    success_vector=bits,
                    low_uplift=low,
                    high_uplift=high,
                    interaction=high - low,
                    high_new_success_feedback_supported=guarded if high == 1 else None,
                )
            )
        low, high = counts[1] - counts[0], counts[3] - counts[2]
        task_rows.append(
            dict(
                task_slot=slot,
                seed_count=4,
                arm_success_counts=counts,
                new_success_counts=new,
                lost_success_counts=lost,
                low_uplift_numerator=low,
                high_uplift_numerator=high,
                interaction_numerator=high - low,
                low_uplift=ratio(low, 4),
                high_uplift=ratio(high, 4),
                interaction=ratio(high - low, 4),
            )
        )
    counts = [sum(r["arm_success_counts"][j] for r in task_rows) for j in range(4)]
    new = [sum(r["new_success_counts"][j] for r in task_rows) for j in range(2)]
    lost = [sum(r["lost_success_counts"][j] for r in task_rows) for j in range(2)]
    low, high = counts[1] - counts[0], counts[3] - counts[2]
    interaction = high - low
    loo = [
        dict(
            omitted_task_slot=r["task_slot"],
            block_count=44,
            interaction=ratio(interaction - r["interaction_numerator"], 44),
            high_uplift=ratio(high - r["high_uplift_numerator"], 44),
        )
        for r in task_rows
    ]
    gates = dict(
        interaction_at_least_two=interaction >= 2,
        high_uplift_at_least_two=high >= 2,
        low_uplift_nonnegative=low >= 0,
        no_high_budget_lost_success=lost[1] == 0,
        high_rescues_on_two_tasks=sum(r["new_success_counts"][1] > 0 for r in task_rows)
        >= 2,
        leave_one_task_out_strictly_positive=all(
            r["interaction"]["numerator"] > 0 and r["high_uplift"]["numerator"] > 0
            for r in loo
        ),
        all_high_new_successes_feedback_supported=all(
            r["high_new_success_feedback_supported"] is True
            for r in blocks
            if r["high_uplift"] == 1
        ),
    )
    return dict(
        arm_order=list(ARM_NAMES),
        arm_denominator=48,
        task_count=12,
        block_count=48,
        arm_success_counts=counts,
        blocks=blocks,
        task_rows=task_rows,
        new_success_counts=new,
        lost_success_counts=lost,
        net_success_counts=[low, high],
        low_uplift=ratio(low, 48),
        high_uplift=ratio(high, 48),
        interaction=ratio(interaction, 48),
        pattern_counts=[
            dict(
                pattern="".join(map(str, p)),
                count=patterns["".join(map(str, p))],
                forbidden_by_prefix=p[2] < p[0] or p[3] < p[1],
            )
            for p in product((0, 1), repeat=4)
        ],
        leave_one_task_out=loo,
        screen_components=gates,
        screen_conjunction=all(gates.values()),
        integrity_assessed_here=False,
        scientific_decision=None,
        execution_authorized=False,
    )


def _suffix(prefix, suffix):
    first, later = min(prefix) if prefix else None, min(suffix) if suffix else None
    category = (
        "no_completed_terminal"
        if later is None
        else "no_prefix_terminal"
        if first is None
        else "exact_hit"
        if later == 0
        else "improved_nonexact"
        if later < first
        else "tied"
        if later == first
        else "worse"
    )
    return dict(
        common_prefix_minimum_error=first,
        observed_suffix_minimum_error=later,
        category=category,
        cumulative_best_gain=None
        if first is None or later is None
        else first - min(first, later),
    )


def reduce_matrix(inputs, records: dict, stage_observer=None) -> dict:
    """Pure ordered reduction. Independent caller must have closed all integrity."""
    observe = stage_observer or (lambda stage: None)
    coordinates = tuple(product(range(12), BUDGETS, SCALES, SEEDS))
    require(
        type(records) is dict and tuple(records) == coordinates,
        "192 ordered closed traces required",
    )
    cells = dict(zip(coordinates, inputs.cells))
    observe(STAGES[3])
    mechanisms, timings = {}, {}
    for coord, trace in records.items():
        cell, key = cells[coord], cells[coord]["cell_key"]
        selected = SimpleNamespace(
            cell_id=cell["cell_id"],
            task_fingerprint=key["task_fingerprint"],
            exploration_seed=key["seed"],
            terminal_value_scale=key["scale"],
        )
        mechanisms[coord] = prior.project_mechanism_cell(selected, trace)
        limits = inputs.arguments(cell)["budget_profile"].to_dict()["budget"]
        timings[coord] = project_opportunity(trace, limits)
    pairs, pair_map = [], {}
    for slot, budget, seed in product(range(12), BUDGETS, SEEDS):
        left, right = (slot, budget, 0, seed), (slot, budget, 16, seed)
        pair = prior.pair_mechanism_cells(mechanisms[left], mechanisms[right])
        row = dict(
            task_slot=slot,
            budget=budget,
            **pair,
            **pair_opportunity(pair, timings[left], timings[right]),
        )
        pairs.append(row)
        pair_map[slot, budget, seed] = row
    extensions = []
    for slot, seed in product(range(12), SEEDS):
        low, high = pair_map[slot, 256, seed], pair_map[slot, 512, seed]
        div = low["first_action_divergence"]
        if div is not None:
            require(
                canonical_json(div) == canonical_json(high["first_action_divergence"]),
                "high-budget divergence contradicts low prefix",
            )
        continuation = []
        for scale, label in ((0, "baseline"), (16, "scaled")):
            lo, hi = timings[slot, 256, scale, seed], timings[slot, 512, scale, seed]
            low_ids, high_ids = (
                [t for t, _ in lo.terminals],
                [t for t, _ in hi.terminals],
            )
            unfinished = div is not None and div["trajectory_index"] not in low_ids
            completed = div is not None and div["trajectory_index"] in high_ids
            require(
                not unfinished or completed,
                "unfinished divergent trajectory did not complete",
            )
            continuation.append(
                dict(
                    scale=scale,
                    added_terminal_count=len(high_ids) - len(low_ids),
                    added_trajectory_ids=high_ids[len(low_ids) :],
                    low_divergent_trajectory_unfinished=unfinished if div else None,
                    same_trajectory_completed_high=completed if div else None,
                )
            )
        extensions.append(
            dict(
                task_slot=slot,
                seed=seed,
                divergence_class="already_diverged_low"
                if div
                else "newly_diverged_high"
                if high["first_action_divergence"]
                else "no_divergence",
                low_divergence_coordinate=None
                if not div
                else {k: div[k] for k in ("trajectory_index", "depth")},
                observed_same_scale_continuations=continuation,
            )
        )
    mechanism = dict(
        pair_count=96,
        pairs=pairs,
        extensions=extensions,
        by_budget=[
            dict(
                budget=b,
                pair_count=48,
                divergent_pair_count=sum(
                    r["first_action_divergence"] is not None
                    for r in pairs
                    if r["budget"] == b
                ),
                opportunity_bins={
                    bucket: sum(
                        r["opportunity_bin"] == bucket
                        for r in pairs
                        if r["budget"] == b
                    )
                    for bucket in ("no_divergence", "0", "1", "2+")
                },
            )
            for b in BUDGETS
        ],
    )
    frozen_mechanism = canonical_json(mechanism)
    observe(STAGES[4])
    errors = {coord: prior._error_cell(trace) for coord, trace in records.items()}
    error_blocks, error_tasks, error_pairs = [], [], []
    for slot in range(12):
        task_values = []
        for seed in SEEDS:
            values = [errors[slot, b, s, seed]["minimum_error"] for b, s in ARMS]
            require(
                values[2] <= values[0] and values[3] <= values[1],
                "minimum error contradicts prefix",
            )
            contrasts = [sign(values[0] - values[1]), sign(values[2] - values[3])]
            interaction = contrasts[1] - contrasts[0]
            task_values.append(interaction)
            error_blocks.append(
                dict(
                    task_slot=slot,
                    seed=seed,
                    minimum_error_vector=values,
                    comparison_vector=[
                        "win" if v > 0 else "loss" if v < 0 else "tie"
                        for v in contrasts
                    ],
                    ordinal_error_interaction=interaction,
                )
            )
        error_tasks.append(
            dict(
                task_slot=slot,
                ordinal_error_interaction=ratio(sum(task_values), 4),
                mean_minimum_errors_by_arm=[
                    ratio(
                        sum(
                            errors[slot, b, s, seed]["minimum_error"] for seed in SEEDS
                        ),
                        4,
                    )
                    for b, s in ARMS
                ],
                by_budget=[
                    dict(
                        budget=b,
                        **{
                            label: sum(
                                r["comparison_vector"][j] == label
                                for r in error_blocks
                                if r["task_slot"] == slot
                            )
                            for label in ("win", "tie", "loss")
                        },
                    )
                    for j, b in enumerate(BUDGETS)
                ],
            )
        )
    for row in pairs:
        slot, budget, seed = row["task_slot"], row["budget"], row["exploration_seed"]
        conversion = dict(
            task_slot=slot, budget=budget, seed=seed, observed_conversion=None
        )
        if row["divergence_window"] is not None:
            outcomes, prefixes = {}, []
            for scale, label in ((0, "baseline"), (16, "scaled")):
                coord = slot, budget, scale, seed
                index = row["divergence_window"][label]["selection_event_index"]
                terms = list(zip(timings[coord].terminals, errors[coord]["errors"]))
                prefix = [(t, e) for ((t, i), e) in terms if i < index]
                suffix = [e for ((t, i), e) in terms if i > index]
                prefixes.append(prefix)
                outcomes[label] = _suffix([e for t, e in prefix], suffix)
            require(prefixes[0] == prefixes[1], "common-prefix terminal errors differ")
            conversion["observed_conversion"] = outcomes
        error_pairs.append(conversion)
    error_summary = dict(
        cell_count=192,
        cells=[
            dict(
                cell_id=cells[c]["cell_id"],
                task_slot=c[0],
                budget=c[1],
                scale=c[2],
                seed=c[3],
                **e,
            )
            for c, e in errors.items()
        ],
        blocks=error_blocks,
        task_rows=error_tasks,
        suffix_conversions=error_pairs,
        by_budget=[
            dict(
                budget=b,
                **{
                    label: sum(r["comparison_vector"][j] == label for r in error_blocks)
                    for label in ("win", "tie", "loss")
                },
            )
            for j, b in enumerate(BUDGETS)
        ],
        ordinal_error_interaction=ratio(
            sum(r["ordinal_error_interaction"] for r in error_blocks), 48
        ),
    )
    observe(STAGES[5])
    success_cells, successes = [], []
    for coord, trace in records.items():
        error = errors[coord]
        bits = [
            e["payload"]["verification"]["success"]
            for e in trace["events"]
            if e["kind"] == "terminal_verified"
        ]
        require(
            all(type(v) is bool for v in bits)
            and bits == [e == 0 for e in error["errors"]],
            "success/error vectors differ",
        )
        first = next((i for i, b in enumerate(bits) if b), None)
        success_cells.append(
            dict(
                cell_id=cells[coord]["cell_id"],
                success=any(bits),
                terminal_success_vector=bits,
                first_hit_observation_index=first,
                first_hit_trajectory=None
                if first is None
                else error["trajectories"][first],
            )
        )
    for slot in range(12):
        successes.append(
            [
                [int(errors[slot, b, s, seed]["minimum_error"] == 0) for b, s in ARMS]
                for seed in SEEDS
            ]
        )
    informed = [
        [pair_map[slot, 512, seed]["feedback_informed"] for seed in SEEDS]
        for slot in range(12)
    ]
    success_summary = factorial(successes, informed)
    success_summary["cells"] = success_cells
    require(
        canonical_json(mechanism) == frozen_mechanism,
        "mechanism changed during outcome reduction",
    )
    return dict(
        schema_version=DOMAIN + "/ordered-reduction",
        stage_order=list(STAGES),
        mechanism=mechanism,
        mechanism_digest=sha256_json(mechanism),
        terminal_errors=error_summary,
        exact_success=success_summary,
        scope="pure_reduction_of_replay_closed_inputs_no_admission_or_authority",
        scientific_decision=None,
        execution_authorized=False,
    )
