"""Reusable provider-neutral substrate for the Track A search benchmark."""

from qmc_bmgs.substrate.budget import (
    TRACK_A_WORK_AXES,
    TrackABudgetExceeded,
    TrackAChargeReceipt,
    TrackAWorkBudget,
    TrackAWorkLedger,
)
from qmc_bmgs.substrate.perturbations import (
    LazyNormalSource,
    PerturbationDraw,
    TrackARunPoisoned,
    build_perturbation_run_identity,
    generate_perturbation_point,
    perturbation_run_identity_digest,
    replay_perturbation_trace,
    replay_perturbation_trace_bytes,
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
    "TraceEventReservation",
    "TraceValidationError",
    "TrackABudgetExceeded",
    "TrackAChargeReceipt",
    "TrackAWorkBudget",
    "TrackAWorkLedger",
    "TrackARunPoisoned",
    "build_perturbation_run_identity",
    "canonical_trace_bytes",
    "generate_perturbation_point",
    "perturbation_run_identity_digest",
    "replay_perturbation_trace",
    "replay_perturbation_trace_bytes",
    "validate_trace",
    "validate_trace_bytes",
]
