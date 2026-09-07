#!/usr/bin/env python3
"""Reproduce the fixed public feedback/budget qualification and verify its evidence.

This script has no development-task input, cohort generator, or authorization path.
The existing package stays byte-identical; this wrapper binds its own Git bytes.
"""

from __future__ import annotations

import argparse
from itertools import product
from pathlib import Path
import sys
from typing import Callable

from qmc_bmgs.benchmarks.countdown import CountdownTask
from qmc_bmgs.experiments import countdown_thompson_dense_scale_core as core
from qmc_bmgs.substrate.budget import TRACK_A_WORK_AXES, TrackAWorkBudget
from qmc_bmgs.substrate.countdown_search import (
    TrackABudgetProfile,
    TrackAMethodSpec,
    build_search_run_identity,
    replay_countdown_track_a_search_bytes,
    run_countdown_track_a_search,
)
from qmc_bmgs.substrate.proposals import TrackAProposalSpec
from qmc_bmgs.substrate.perturbations import perturbation_runtime_metadata
from qmc_bmgs.substrate.trace import sha256_json, validate_trace_bytes


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = "scripts/qualify_feedback_budget.py"
DESIGN = "docs/strategy/countdown_thompson_feedback_budget_factorial_v6.md"
DESIGN_SHA256 = "7b3ebcc7d1b3c3a591b6f3baa574492085bc91c53ee3cccc9fe031d3d70ef01f"
FIXTURES = "docs/fixtures/countdown_feedback_budget_v6_public.json"
DESIGN_REVISION = "6a7b2a411444c610c5947bf9f3c85af38fd3787e"
DOMAIN = "qmc-bmgs-feedback-budget-public-qualification/v1"
SEEDS = (8192, 8193, 8194, 8195)
SCALES = (0, 16)
BUDGETS = (256, 512)
TASK = CountdownTask((1, 2, 3, 4, 5, 6), 720)
PROPOSAL = TrackAProposalSpec("greedy_rollout_target_error/v1")
canonical = core.canonical_bytes
sha = core.sha256_bytes


class QualificationError(ValueError):
    """A public qualification identity or integrity check failed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise QualificationError(message)


def profile(budget: int, *, legacy: bool = False) -> TrackABudgetProfile:
    require(type(budget) is int and budget in BUDGETS, "budget must be 256 or 512")
    require(type(legacy) is bool, "legacy must be a bool")
    require(not legacy or budget == 256, "legacy profile only has budget 256")
    values = (
        (87, 317, 256, 316, 86, 86, 18)
        if legacy
        else (172, 573, budget, 572, 171, 171, 35)
    )
    result = TrackABudgetProfile(
        profile_id="score256"
        if legacy
        else f"feedback_budget_score{budget}_common512_v1",
        primary_axis="legal_action_scores",
        budget=TrackAWorkBudget(**dict(zip(TRACK_A_WORK_AXES, values))),
    )
    if legacy:
        require(
            canonical(result.to_dict())
            == canonical(core.public_contract()["budget"]["profile"]["spec"]),
            "legacy score256 differs from the frozen public contract",
        )
    return result


def method(scale: int) -> TrackAMethodSpec:
    require(type(scale) is int and scale in SCALES, "scale must be 0 or 16")
    return TrackAMethodSpec.dimension_normalized_scaled_dense_thompson("iid", scale)


def arguments(budget: int, scale: int, seed: int, *, legacy: bool = False) -> dict:
    require(type(seed) is int and seed in SEEDS, "seed is outside the public schedule")
    return dict(
        task=TASK,
        proposal=PROPOSAL,
        method=method(scale),
        budget_profile=profile(budget, legacy=legacy),
        exploration_seed=seed,
    )


def schedule() -> list[dict]:
    return [
        dict(budget=b, scale=s, seed=r, legacy=False)
        for b, s, r in product(BUDGETS, SCALES, SEEDS)
    ] + [
        dict(budget=256, scale=s, seed=r, legacy=True)
        for s, r in product(SCALES, SEEDS)
    ]


def public_manifest() -> dict:
    """Fix public identities before future cohort generation; never run a solver."""
    full_shape = [
        CountdownTask(TASK.inputs, target).to_dict() for target in range(1, 13)
    ]
    tasks = [TASK.to_dict(), *full_shape]
    return core.with_digest(
        {
            "schema_version": "qmc-bmgs-feedback-budget-public-fixture-identities/v1",
            "qualification_task": TASK.to_dict(),
            "qualification_schedule": schedule(),
            "anchor_qualification_digest": core.FROZEN_AUTHORITY[
                "anchor_qualification_digest"
            ],
            "full_shape_fixture_id": "feedback_budget_nondiagnostic_full_shape_192/v1",
            "full_shape_tasks": full_shape,
            "full_shape_planned_cell_count": 192,
            "full_shape_schedule_order": "task_then_budget_then_scale_then_seed",
            "full_shape_budgets": list(BUDGETS),
            "full_shape_scales": list(SCALES),
            "full_shape_seeds": list(SEEDS),
            "exclude_task_fingerprints": sorted({t["task_fingerprint"] for t in tasks}),
            "exclude_source_multiset_fingerprints": sorted(
                {t["source_multiset_fingerprint"] for t in tasks}
            ),
            "development_execution_authorized": False,
        }
    )


def accepted_events(record: dict) -> list[dict]:
    events = record["events"]
    require(
        bool(events) and events[-1]["kind"] == "search_finished",
        "missing final summary",
    )
    require(
        all(e["kind"] != "search_finished" for e in events[:-1]),
        "early search_finished event",
    )
    return events[:-1]


def validate_budget(record: dict, expected_profile: TrackABudgetProfile) -> dict:
    accepted_events(record)
    summary = record["events"][-1]["payload"]["summary"]
    require(
        canonical(summary["budget_profile"]) == canonical(expected_profile.to_dict()),
        "summary budget profile mismatch",
    )
    require(summary["stop_reason"] == "primary_budget_blocked", "primary stop required")
    require(
        summary["stop_blocked_axes"] == ["legal_action_scores"],
        "sole primary block required",
    )
    require(summary["budget_valid"] is True, "invalid budget")
    require(summary["non_primary_exhausted_axes"] == [], "secondary guard exhausted")
    ledger = record["ledger_snapshot"]
    usage, remaining, limits = (
        ledger["usage"],
        ledger["remaining"],
        expected_profile.budget.to_dict(),
    )
    attempted = summary["stop_attempted_charge"]
    for vector in (usage, remaining, attempted):
        require(
            type(vector) is dict and set(vector) == set(TRACK_A_WORK_AXES),
            "work axes differ",
        )
        require(
            all(type(v) is int and v >= 0 for v in vector.values()),
            "invalid work amount",
        )
    require(
        canonical(summary["ledger_usage"]) == canonical(usage), "summary usage mismatch"
    )
    for axis in TRACK_A_WORK_AXES:
        require(
            remaining[axis] == limits[axis] - usage[axis],
            "budget overshoot or inconsistent remainder",
        )
        if axis != "legal_action_scores":
            require(remaining[axis] > 0, "secondary guard has no accepted headroom")
            require(
                usage[axis] + attempted[axis] <= limits[axis],
                "attempt also blocks secondary guard",
            )
    require(
        usage["legal_action_scores"] + attempted["legal_action_scores"]
        > limits["legal_action_scores"],
        "attempt does not block primary budget",
    )
    terminals = [e for e in record["events"] if e["kind"] == "terminal_verified"]
    require(
        type(summary["terminal_count"]) is int
        and len(terminals) == summary["terminal_count"],
        "terminal count mismatch",
    )
    require(
        len(terminals) >= (3 if limits["legal_action_scores"] == 512 else 1),
        "structural minimum terminal count violated",
    )
    return dict(
        usage=usage,
        remaining=remaining,
        attempted=attempted,
        stop_reason=summary["stop_reason"],
        stop_blocked_axes=summary["stop_blocked_axes"],
        terminal_count=len(terminals),
        zero_overshoot=True,
        secondary_guards_nonbinding=True,
    )


def validate_record(
    raw: bytes, budget: int, scale: int, seed: int, *, legacy: bool = False
) -> dict:
    args = arguments(budget, scale, seed, legacy=legacy)
    expected_id = sha256_json(build_search_run_identity(**args))
    replayed = replay_countdown_track_a_search_bytes(
        raw, **args, expected_run_identity_digest=expected_id
    )
    require(replayed == raw, "replay bytes differ")
    record = validate_trace_bytes(replayed)
    return dict(
        budget=budget,
        scale=scale,
        seed=seed,
        legacy=legacy,
        task_fingerprint=TASK.task_fingerprint,
        source_multiset_fingerprint=TASK.source_multiset_fingerprint,
        profile_spec=args["budget_profile"].to_dict(),
        method_spec=args["method"].to_dict(),
        run_identity_digest=expected_id,
        trace_sha256=sha(raw),
        trace_byte_count=len(raw),
        accepted_events_digest=sha256_json(accepted_events(record)),
        accepted_event_count=len(accepted_events(record)),
        budget_evidence=validate_budget(record, args["budget_profile"]),
        replay={"stage1_generative": "PASS", "stage2_byte_identical": "PASS"},
        provider_calls=0,
    )


def _compare_validated(
    low: dict, high: dict, scale: int, seed: int, *, legacy: bool
) -> dict:
    lo, hi = accepted_events(low), accepted_events(high)
    require(
        len(lo) <= len(hi) and canonical(lo) == canonical(hi[: len(lo)]),
        "full accepted-event prefix differs",
    )
    low_terms = [e for e in lo if e["kind"] == "terminal_verified"]
    high_terms = [e for e in hi if e["kind"] == "terminal_verified"]
    continuation = [e for e in hi[len(lo) :] if e["kind"] == "terminal_verified"]
    current = len(low_terms)
    completed = (
        bool(continuation) and continuation[0]["payload"]["trajectory_index"] == current
    )
    if legacy:
        require(canonical(lo) == canonical(hi), "legacy accepted events differ")
    else:
        require(
            len(high_terms) >= len(low_terms) + 1 and len(high_terms) >= 3,
            "budget extension terminal guarantee violated",
        )
        require(completed, "unfinished or current-next low trajectory did not complete")
    low_success = any(e["payload"]["verification"]["success"] for e in low_terms)
    high_success = any(e["payload"]["verification"]["success"] for e in high_terms)
    low_error = min(
        abs(TASK.target - e["payload"]["verification"]["final_value"])
        for e in low_terms
    )
    high_error = min(
        abs(TASK.target - e["payload"]["verification"]["final_value"])
        for e in high_terms
    )
    require(not low_success or high_success, "exact success contradicts prefix")
    require(high_error <= low_error, "minimum terminal error contradicts prefix")
    return dict(
        scale=scale,
        seed=seed,
        legacy_guard_comparison=legacy,
        low_event_count=len(lo),
        high_event_count=len(hi),
        exact_prefix_digest=sha256_json(lo),
        low_terminal_count=len(low_terms),
        high_terminal_count=len(high_terms),
        new_terminal_count=len(continuation),
        current_or_next_trajectory_index=current,
        current_or_next_completed_in_continuation=completed,
        exact_success_nondecreasing=True,
        minimum_error_nonincreasing=True,
        status="EXACT_ACCEPTED_EVENTS_EQUAL"
        if legacy
        else "EXACT_PREFIX_AND_COMPLETION_PASS",
    )


def compare_prefix(
    low_raw: bytes, high_raw: bytes, scale: int, seed: int, *, legacy: bool = False
) -> dict:
    validate_record(low_raw, 256, scale, seed, legacy=legacy)
    validate_record(high_raw, 256 if legacy else 512, scale, seed)
    return _compare_validated(
        validate_trace_bytes(low_raw),
        validate_trace_bytes(high_raw),
        scale,
        seed,
        legacy=legacy,
    )


def analyze_matrix(rows: list[dict]) -> dict:
    expected = schedule()
    require(
        type(rows) is list and len(rows) == len(expected),
        "exactly 24 public records required",
    )
    # Check every cell identity before the first replay; user evidence never
    # selects a task, profile, method or seed outside this public schedule.
    for row, cell in zip(rows, expected):
        require(
            type(row) is dict and set(row) == {*cell, "search_record"},
            "record fields differ",
        )
        require(
            canonical({k: row[k] for k in cell}) == canonical(cell),
            "public schedule identity differs",
        )
        record = row["search_record"]
        require(type(record) is dict, "search record must be an object")
        require(
            canonical(record.get("run_identity"))
            == canonical(build_search_run_identity(**arguments(**cell))),
            "public search run identity differs",
        )
    receipts, records = [], {}
    for row, cell in zip(rows, expected):
        receipts.append(validate_record(canonical(row["search_record"]), **cell))
        records[(cell["budget"], cell["scale"], cell["seed"], cell["legacy"])] = row[
            "search_record"
        ]
    pairs, legacy_pairs = [], []
    for scale, seed in product(SCALES, SEEDS):
        low = records[256, scale, seed, False]
        pairs.append(
            _compare_validated(
                low, records[512, scale, seed, False], scale, seed, legacy=False
            )
        )
        legacy_pairs.append(
            _compare_validated(
                records[256, scale, seed, True], low, scale, seed, legacy=True
            )
        )
    anchors = core.reproduce_anchor_qualification()
    return core.with_digest(
        {
            "schema_version": DOMAIN + "/analysis",
            "status": "PUBLIC_QUALIFICATION_PASS",
            "fixture_manifest_digest": public_manifest()["deterministic_digest"],
            "new_profile_trace_count": 16,
            "legacy_trace_count": 8,
            "anchor_trace_count": 8,
            "two_stage_replayed_trace_count": 32,
            "budget_prefix_checks": pairs,
            "legacy_guard_checks": legacy_pairs,
            "trace_receipts": receipts,
            "anchor_qualification": anchors,
            "full_shape_192_executed": False,
            "development_cells_executed": 0,
            "development_execution_authorized": False,
            "provider_calls": 0,
        }
    )


def run_matrix(
    on_record: Callable[[dict], None] | None = None,
) -> tuple[list[dict], dict]:
    rows = []
    for cell in schedule():
        result = run_countdown_track_a_search(**arguments(**cell))
        row = {**cell, "search_record": result.record}
        rows.append(row)
        if on_record is not None:
            on_record(row)
    return rows, analyze_matrix(rows)


def attest(root: Path, revision: str | None = None) -> dict:
    source = core.source_attestation(root, revision)
    approved = source["runner_revision"]
    head = core.git_head(root)
    core.require_ancestor(root, DESIGN_REVISION, approved)
    require(
        Path(__file__).resolve() == root / SCRIPT, "qualification script origin differs"
    )
    files = {}
    snapshots = []
    for relative in (SCRIPT, DESIGN, FIXTURES):
        snapshot = core.FileSnapshot.capture(root / relative)
        require(
            snapshot.raw
            == core._regular_git_blob(root, approved, relative)
            == core._regular_git_blob(root, head, relative),
            "qualification source bytes changed",
        )
        files[relative] = dict(byte_count=len(snapshot.raw), sha256=sha(snapshot.raw))
        snapshots.append(snapshot)
    require(files[DESIGN]["sha256"] == DESIGN_SHA256, "frozen design changed")
    require(
        snapshots[-1].raw == canonical(public_manifest()),
        "public fixture identities changed",
    )
    for snapshot in snapshots:
        snapshot.revalidate()
    return core.with_digest(
        {
            "schema_version": DOMAIN + "/source",
            "qualification_revision": approved,
            "package_source": source,
            "qualification_files": files,
        }
    )


def _output_directory(path: Path) -> Path:
    path = path.absolute()
    parent = ROOT / "artifacts/work"
    require(
        path.parent == parent and parent.resolve(strict=True) == parent,
        "output must be a new direct child of artifacts/work with no path aliases",
    )
    path.mkdir(mode=0o700)
    return path


def runtime_receipt() -> dict:
    # Clear cached conformance before observing the sealed numeric runtime.
    perturbation_runtime_metadata("iid", refresh_conformance=True)
    return core.runtime_qualification()


def qualify(output: Path) -> dict:
    source = attest(ROOT)
    runtime = runtime_receipt()
    output = _output_directory(output)
    try:
        with (output / "records.jsonl").open("xb") as stream:

            def retain(row: dict) -> None:
                stream.write(canonical(row))
                stream.flush()

            _, analysis = run_matrix(retain)
        raw = core.FileSnapshot.capture(output / "records.jsonl").raw
        require(
            attest(ROOT) == source and runtime_receipt() == runtime,
            "source or runtime changed during qualification",
        )
        receipt = core.with_digest(
            {
                "schema_version": DOMAIN + "/receipt",
                "status": "PUBLIC_QUALIFICATION_PASS",
                "source": source,
                "runtime": runtime,
                "analysis": analysis,
                "records_file": "records.jsonl",
                "records_byte_count": len(raw),
                "records_sha256": sha(raw),
                "raw_trace_persisted_count": 24,
                "anchor_raw_trace_persisted_count": 0,
                "development_execution_authorized": False,
            }
        )
        with (output / "receipt.json").open("xb") as stream:
            stream.write(canonical(receipt))
        return receipt
    except Exception as error:
        with (output / "failure.json").open("xb") as stream:
            stream.write(
                canonical(
                    {
                        "schema_version": DOMAIN + "/failure",
                        "status": "INVALID_PUBLIC_QUALIFICATION",
                        "error_type": type(error).__name__,
                        "reason": str(error),
                        "development_execution_authorized": False,
                    }
                )
            )
        raise


def verify(output: Path) -> dict:
    require(
        set(p.name for p in output.iterdir()) == {"records.jsonl", "receipt.json"},
        "public evidence file closure differs",
    )
    receipt_snapshot = core.FileSnapshot.capture(output / "receipt.json")
    record_snapshot = core.FileSnapshot.capture(output / "records.jsonl")
    receipt = core.parse_canonical(receipt_snapshot.raw)
    core.require_digest(receipt)
    require(
        receipt["schema_version"] == DOMAIN + "/receipt",
        "public receipt domain differs",
    )
    source = attest(ROOT, receipt["source"]["qualification_revision"])
    require(canonical(source) == canonical(receipt["source"]), "source receipt differs")
    runtime = runtime_receipt()
    # This first qualification binds the same host as well as numeric runtime;
    # independent verification means a separate process, not a different host.
    require(
        canonical(runtime) == canonical(receipt["runtime"]), "runtime receipt differs"
    )
    raw = record_snapshot.raw
    require(
        len(raw) == receipt["records_byte_count"]
        and sha(raw) == receipt["records_sha256"],
        "raw records digest differs",
    )
    rows = [core.parse_canonical(line) for line in raw.splitlines(keepends=True)]
    analysis = analyze_matrix(rows)
    expected = core.with_digest(
        {
            "schema_version": DOMAIN + "/receipt",
            "status": "PUBLIC_QUALIFICATION_PASS",
            "source": source,
            "runtime": runtime,
            "analysis": analysis,
            "records_file": "records.jsonl",
            "records_byte_count": len(raw),
            "records_sha256": sha(raw),
            "raw_trace_persisted_count": 24,
            "anchor_raw_trace_persisted_count": 0,
            "development_execution_authorized": False,
        }
    )
    require(
        canonical(expected) == canonical(receipt), "recomputed public receipt differs"
    )
    receipt_snapshot.revalidate()
    record_snapshot.revalidate()
    require(
        attest(ROOT, source["qualification_revision"]) == source
        and runtime_receipt() == runtime,
        "source/runtime changed during verification",
    )
    require(
        set(p.name for p in output.iterdir()) == {"records.jsonl", "receipt.json"},
        "public evidence file closure differs",
    )
    return expected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--manifest", action="store_true")
    modes.add_argument("--qualify", type=Path, metavar="NEW_OUTPUT_DIRECTORY")
    modes.add_argument("--verify", type=Path, metavar="EXISTING_OUTPUT_DIRECTORY")
    args = parser.parse_args()
    if args.manifest:
        sys.stdout.buffer.write(canonical(public_manifest()))
        return
    receipt = qualify(args.qualify) if args.qualify else verify(args.verify)
    print(
        core.canonical_bytes(
            {
                "status": "PUBLIC_QUALIFICATION_PASS"
                if args.qualify
                else "PUBLIC_QUALIFICATION_VERIFIED",
                "receipt_digest": receipt["deterministic_digest"],
                "two_stage_replayed_trace_count": 32,
                "prefix_checks": 8,
                "legacy_guard_checks": 8,
                "full_shape_192_executed": False,
                "development_cells_executed": 0,
                "development_execution_authorized": False,
            }
        ).decode(),
        end="",
    )


if __name__ == "__main__":
    main()
