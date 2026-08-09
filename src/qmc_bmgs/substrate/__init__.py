"""Reusable provider-neutral substrate for the Track A search benchmark."""

from qmc_bmgs.substrate.budget import (
    TRACK_A_WORK_AXES,
    TrackABudgetExceeded,
    TrackAChargeReceipt,
    TrackAWorkBudget,
    TrackAWorkLedger,
)
from qmc_bmgs.substrate.countdown_search import (
    TrackABudgetProfile,
    TrackAMethodSpec,
    TrackASearchResult,
    build_search_run_identity,
    replay_countdown_track_a_search_bytes,
    run_countdown_track_a_search,
    search_run_identity_digest,
)
from qmc_bmgs.substrate.perturbations import (
    LazyNormalSource,
    PerturbationDraw,
    PerturbationDrawPlan,
    PreparedPerturbationDraw,
    TrackARunPoisoned,
    ValidatedStoredPerturbationMaterial,
    build_perturbation_run_identity,
    generate_perturbation_point,
    perturbation_run_identity_digest,
    replay_perturbation_trace,
    replay_perturbation_trace_bytes,
)
from qmc_bmgs.substrate.proposals import (
    TrackAProposalRow,
    TrackAProposalSpec,
    evaluate_track_a_proposal,
)
from qmc_bmgs.substrate.trace import (
    HashChainedTrace,
    TraceEventReservation,
    TraceValidationError,
    canonical_trace_bytes,
    validate_trace,
    validate_trace_bytes,
)

__all__ = [
    "TRACK_A_WORK_AXES",
    "HashChainedTrace",
    "LazyNormalSource",
    "PerturbationDraw",
    "PerturbationDrawPlan",
    "PreparedPerturbationDraw",
    "TraceEventReservation",
    "TraceValidationError",
    "TrackABudgetExceeded",
    "TrackABudgetProfile",
    "TrackAChargeReceipt",
    "TrackAMethodSpec",
    "TrackAProposalRow",
    "TrackAProposalSpec",
    "TrackASearchResult",
    "TrackAWorkBudget",
    "TrackAWorkLedger",
    "TrackARunPoisoned",
    "ValidatedStoredPerturbationMaterial",
    "build_perturbation_run_identity",
    "build_search_run_identity",
    "canonical_trace_bytes",
    "evaluate_track_a_proposal",
    "generate_perturbation_point",
    "perturbation_run_identity_digest",
    "replay_perturbation_trace",
    "replay_perturbation_trace_bytes",
    "replay_countdown_track_a_search_bytes",
    "run_countdown_track_a_search",
    "search_run_identity_digest",
    "validate_trace",
    "validate_trace_bytes",
]
