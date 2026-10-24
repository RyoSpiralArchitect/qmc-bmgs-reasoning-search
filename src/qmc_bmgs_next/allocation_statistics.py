"""Predeclared source-cluster readout; not a population confirmation test.

Seeds are fixed within-source repeated blocks, never additional sampling units.
The approximate interval assumes exchangeable, sufficiently independent source
clusters under the accepted generation recipe. Unique identities do not prove
those assumptions. No outcome-selected resampling or parameter tuning occurs.
"""

from fractions import Fraction
import math


def uncertainty_contract():
    return {
        "primary": "weighted16_minus_single16",
        "estimand": "mean_source_success_difference_conditional_on_fixed_8_seeds",
        "sampling_unit": "source_multiset",
        "source_count": 256,
        "fixed_seeds_per_source": 8,
        "source_difference": "mean_seed(paired_success_difference)",
        "interval": "mean_plus_minus_2_times_sample_source_sd_over_sqrt_n",
        "nominal_level": "approximate_95_percent_model_based_not_exact_coverage",
        "assumptions": [
            "exchangeable_sufficiently_independent_accepted_source_clusters",
            "normal_approximation_for_the_mean_of_bounded_cluster_differences",
            "conditional_on_fixed_seed_set_generator_and_identity_exclusions",
        ],
        "minimum_clusters_for_interval": 64,
        "zero_variance": "null_interval_unresolved_not_zero_uncertainty",
        "practical_uplift": 0.02,
        "target_half_width": 0.05,
        "precision_scenarios": [
            {"source_sd": 0.2, "half_width_at_256_sources": 0.025},
            {"source_sd": 0.4, "half_width_at_256_sources": 0.05},
            {"source_sd": 0.6, "half_width_at_256_sources": 0.075},
        ],
        "sample_size_rationale": "fixed_256_source_precision_design_not_power_guarantee",
        "readout_order": [
            "insufficient_or_zero_variance_UNRESOLVED",
            "half_width_above_0.05_IMPRECISE",
            "lower_bound_above_0.02_PROMISING_FOR_FRESH_CONFIRMATION",
            "upper_bound_at_or_below_0.02_NO_PRACTICAL_UPLIFT_SIGNAL",
            "otherwise_UNRESOLVED",
        ],
        "secondary_comparisons": "descriptive_only_no_winner_selection",
        "sequential_extension": False,
        "default_promotion": False,
        "population_confirmation": False,
    }


def source_readout(blocks, source_count, seeds):
    """Compute from a complete, typed fixed matrix; retain exact rational moments."""
    if type(source_count) is not int or source_count < 1:
        raise ValueError("positive plain source count required")
    if (
        type(seeds) not in (tuple, list)
        or not seeds
        or any(type(s) is not int or s < 0 for s in seeds)
        or len(set(seeds)) != len(seeds)
    ):
        raise ValueError("distinct nonnegative plain seeds required")
    expected = {(s, seed) for s in range(source_count) for seed in seeds}
    observed = {}
    for row in blocks:
        slot, seed = row["task_slot"], row["seed"]
        if type(slot) is not int or type(seed) is not int:
            raise ValueError("plain source/seed coordinates required")
        key = (slot, seed)
        if key not in expected or key in observed:
            raise ValueError("duplicate/foreign source block")
        a = row["weighted16"]["success_any"]
        b = row["single16"]["success_any"]
        if type(a) is not bool or type(b) is not bool:
            raise ValueError("boolean terminal success required")
        observed[key] = int(a) - int(b)
    if set(observed) != expected:
        raise ValueError("complete source/seed matrix required")
    values = [
        Fraction(sum(observed[(s, seed)] for seed in seeds), len(seeds))
        for s in range(source_count)
    ]
    mean = sum(values, Fraction()) / source_count
    variance = (
        sum(((x - mean) ** 2 for x in values), Fraction()) / (source_count - 1)
        if source_count > 1
        else None
    )
    interval, half_width, status = None, None, "UNRESOLVED"
    reason = "insufficient_source_clusters"
    if source_count >= 64:
        if variance == 0:
            reason = "degenerate_source_variance"
        else:
            half_width = 2 * math.sqrt(float(variance) / source_count)
            # Do not clip to the feasible range: retain the actual model interval.
            interval = [float(mean) - half_width, float(mean) + half_width]
            if half_width > 0.05:
                status, reason = "IMPRECISE", "precision_target_not_met"
            elif interval[0] > 0.02:
                status = "PROMISING_FOR_FRESH_CONFIRMATION"
                reason = "model_interval_above_practical_threshold"
            elif interval[1] <= 0.02:
                status = "NO_PRACTICAL_UPLIFT_SIGNAL"
                reason = "model_interval_not_above_practical_threshold"
            else:
                reason = "model_interval_crosses_practical_threshold"

    def rational(value):
        return None if value is None else [value.numerator, value.denominator]

    return {
        "contract": uncertainty_contract(),
        "source_count": source_count,
        "fixed_seed_count": len(seeds),
        "repeated_block_count": len(blocks),
        "source_differences": [rational(x) for x in values],
        "mean_rational": rational(mean),
        "sample_source_variance_rational": rational(variance),
        "estimate": float(mean),
        "approximate_interval": interval,
        "half_width": half_width,
        "precision_target_met": None if half_width is None else half_width <= 0.05,
        "development_readout": status,
        "reason": reason,
        "winner": None,
        "scientific_decision": None,
    }
