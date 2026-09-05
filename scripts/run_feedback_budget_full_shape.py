#!/usr/bin/env python3
"""Run, save, and independently analyze the fixed 192-cell public fixture."""

from __future__ import annotations

import argparse
import importlib.machinery
import importlib.util
from itertools import product
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = "scripts/run_feedback_budget_full_shape.py"
PUBLICATION = "scripts/feedback_budget_fixture_publication.py"
MANIFEST = "docs/fixtures/countdown_feedback_budget_v6_full_shape.json"
QUALIFICATION = "docs/qualifications/countdown_feedback_budget_v6_public_20260905.json"
QUALIFICATION_SHA256 = (
    "ee8cb216499f678c05c836d77443196c853cbc5dfb184c73448745e07e6dfa53"
)
DOMAIN = "qmc-bmgs-feedback-budget-nondiagnostic-full-shape/v1"
FIXTURE_ID = "feedback_budget_nondiagnostic_full_shape_192/v1"


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load fixed fixture implementation")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


q = _load("feedback_budget_public_qualification", "scripts/qualify_feedback_budget.py")
pub = _load("feedback_budget_fixture_publication", PUBLICATION)
core = q.core
canonical, sha, require = q.canonical, q.sha, q.require


def fixture_manifest() -> dict:
    """Materialize only the already-fixed public fixture identities and schedule."""
    public = q.public_manifest()
    tasks = public["full_shape_tasks"]
    cells = []
    for slot, budget, scale, seed in product(range(12), q.BUDGETS, q.SCALES, q.SEEDS):
        task = tasks[slot]
        key = dict(
            schema_version=DOMAIN + "/cell-key",
            fixture_id=FIXTURE_ID,
            task_slot=slot,
            task_fingerprint=task["task_fingerprint"],
            source_multiset_fingerprint=task["source_multiset_fingerprint"],
            budget=budget,
            scale=scale,
            seed=seed,
            budget_spec_digest=q.sha256_json(q.profile(budget).to_dict()),
            method_spec_digest=q.sha256_json(q.method(scale).to_dict()),
            proposal_spec_digest=q.sha256_json(q.PROPOSAL.to_dict()),
        )
        cells.append(
            dict(cell_index=len(cells), cell_id=q.sha256_json(key), cell_key=key)
        )
    return core.with_digest(
        dict(
            schema_version=DOMAIN + "/manifest",
            fixture_id=FIXTURE_ID,
            public_identity_manifest_digest=public["deterministic_digest"],
            tasks=tasks,
            task_count=12,
            cell_count=192,
            cells=cells,
            schedule_digest=q.sha256_json(cells),
            budget_prefix_check_count=96,
            qualification_receipt_file_sha256=QUALIFICATION_SHA256,
            development_execution_authorized=False,
        )
    )


def arguments(cell: dict) -> dict:
    require(
        type(cell) is dict and type(cell.get("cell_index")) is int,
        "plain indexed public cell required",
    )
    index = cell["cell_index"]
    require(0 <= index < 192, "cell index outside public schedule")
    expected = fixture_manifest()["cells"][index]
    require(canonical(cell) == canonical(expected), "public cell identity differs")
    key = expected["cell_key"]
    return dict(
        task=q.CountdownTask((1, 2, 3, 4, 5, 6), key["task_slot"] + 1),
        proposal=q.PROPOSAL,
        method=q.method(key["scale"]),
        budget_profile=q.profile(key["budget"]),
        exploration_seed=key["seed"],
    )


def build_record(cell: dict) -> dict:
    result = q.run_countdown_track_a_search(**arguments(cell))
    return core.with_digest(
        dict(schema_version=DOMAIN + "/record", **cell, search_record=result.record)
    )


def validate_envelopes(rows: list[dict]) -> None:
    require(
        type(rows) is list and len(rows) == 192, "exactly 192 public records required"
    )
    for row, cell in zip(rows, fixture_manifest()["cells"]):
        require(
            type(row) is dict
            and set(row)
            == {
                "schema_version",
                "cell_index",
                "cell_id",
                "cell_key",
                "search_record",
                "deterministic_digest",
            },
            "public record fields differ",
        )
        core.require_digest(row)
        require(
            row["schema_version"] == DOMAIN + "/record", "public record domain differs"
        )
        require(
            canonical({k: row[k] for k in cell}) == canonical(cell),
            "public schedule differs",
        )
        record = row["search_record"]
        require(type(record) is dict, "search record must be an object")
        require(
            canonical(record.get("run_identity"))
            == canonical(q.build_search_run_identity(**arguments(cell))),
            "public run identity differs",
        )


def compare_pair(low: dict, high: dict, cell: dict) -> dict:
    """Called only after both complete records independently replayed."""
    lo, hi = q.accepted_events(low), q.accepted_events(high)
    require(
        canonical(lo) == canonical(hi[: len(lo)]), "full accepted-event prefix differs"
    )
    low_terms = [e for e in lo if e["kind"] == "terminal_verified"]
    high_terms = [e for e in hi if e["kind"] == "terminal_verified"]
    continuation = [e for e in hi[len(lo) :] if e["kind"] == "terminal_verified"]
    require(
        len(high_terms) >= len(low_terms) + 1 and len(high_terms) >= 3,
        "completion guarantee violated",
    )
    require(
        bool(continuation)
        and continuation[0]["payload"]["trajectory_index"] == len(low_terms),
        "current-next low trajectory did not complete first",
    )
    target = cell["cell_key"]["task_slot"] + 1
    low_error = min(
        abs(target - e["payload"]["verification"]["final_value"]) for e in low_terms
    )
    high_error = min(
        abs(target - e["payload"]["verification"]["final_value"]) for e in high_terms
    )
    low_success = any(e["payload"]["verification"]["success"] for e in low_terms)
    high_success = any(e["payload"]["verification"]["success"] for e in high_terms)
    require(
        high_error <= low_error and (not low_success or high_success),
        "terminal outcome contradicts prefix",
    )
    key = cell["cell_key"]
    return dict(
        task_slot=key["task_slot"],
        task_fingerprint=key["task_fingerprint"],
        source_multiset_fingerprint=key["source_multiset_fingerprint"],
        scale=key["scale"],
        seed=key["seed"],
        low_cell_id=cell["cell_id"],
        low_event_count=len(lo),
        high_event_count=len(hi),
        prefix_digest=q.sha256_json(lo),
        low_terminal_count=len(low_terms),
        high_terminal_count=len(high_terms),
        added_terminal_count=len(continuation),
        current_next_trajectory=len(low_terms),
        current_next_completed_first=True,
        exact_success_nondecreasing=True,
        minimum_error_nonincreasing=True,
        status="EXACT_PREFIX_AND_COMPLETION_PASS",
    )


def analyze_rows(rows: list[dict]) -> dict:
    validate_envelopes(rows)
    cells = fixture_manifest()["cells"]
    receipts, records = [], {}
    for row, cell in zip(rows, cells):
        args = arguments(cell)
        raw = canonical(row["search_record"])
        identity = q.sha256_json(q.build_search_run_identity(**args))
        replayed = q.replay_countdown_track_a_search_bytes(
            raw, **args, expected_run_identity_digest=identity
        )
        require(raw == replayed, "replay bytes differ")
        record = q.validate_trace_bytes(replayed)
        evidence = q.validate_budget(record, args["budget_profile"])
        key = cell["cell_key"]
        records[key["task_slot"], key["budget"], key["scale"], key["seed"]] = record
        receipts.append(
            dict(
                cell_index=cell["cell_index"],
                cell_id=cell["cell_id"],
                record_digest=row["deterministic_digest"],
                search_run_identity_digest=identity,
                trace_sha256=sha(raw),
                trace_byte_count=len(raw),
                budget_evidence=evidence,
                replay={"stage1_generative": "PASS", "stage2_byte_identical": "PASS"},
            )
        )
    pairs = []
    for cell in cells:
        k = cell["cell_key"]
        if k["budget"] == 256:
            key = k["task_slot"], k["scale"], k["seed"]
            pairs.append(
                compare_pair(
                    records[key[0], 256, key[1], key[2]],
                    records[key[0], 512, key[1], key[2]],
                    cell,
                )
            )
    require(len(pairs) == 96, "96 budget pairs required")
    return core.with_digest(
        dict(
            schema_version=DOMAIN + "/integrity-analysis",
            status="PUBLIC_FULL_SHAPE_INTEGRITY_PASS",
            fixture_manifest_digest=fixture_manifest()["deterministic_digest"],
            cell_count=192,
            task_count=12,
            source_multiset_count=1,
            replayed_trace_count=192,
            budget_prefix_check_count=96,
            cell_receipts=receipts,
            budget_prefix_checks=pairs,
            provider_calls=0,
            development_cells_executed=0,
            development_execution_authorized=False,
            scientific_decision=None,
        )
    )


def _module_origin(module, relative: str) -> None:
    spec = module.__spec__
    cache = module.__cached__
    require(
        type(spec.loader) is importlib.machinery.SourceFileLoader
        and Path(spec.origin) == ROOT / relative
        and Path(module.__file__) == ROOT / relative,
        "sibling module origin differs",
    )
    require(
        type(cache) is str
        and Path(cache).is_relative_to(Path(sys.pycache_prefix))
        and not os.path.lexists(cache),
        "sibling cached bytecode is not absent",
    )


def attest(revision: str | None = None) -> dict:
    source = q.attest(ROOT, revision)
    approved = source["qualification_revision"]
    head = core.git_head(ROOT)
    require(
        Path(__file__).resolve() == ROOT / SCRIPT, "full-shape script origin differs"
    )
    _module_origin(q, q.SCRIPT)
    _module_origin(pub, PUBLICATION)
    files, snapshots = {}, []
    for relative in (SCRIPT, PUBLICATION, MANIFEST, QUALIFICATION):
        snapshot = core.FileSnapshot.capture(ROOT / relative)
        require(
            snapshot.raw
            == core._regular_git_blob(ROOT, head, relative)
            == core._regular_git_blob(ROOT, approved, relative),
            "full-shape source bytes changed",
        )
        files[relative] = dict(byte_count=len(snapshot.raw), sha256=sha(snapshot.raw))
        snapshots.append(snapshot)
    require(
        snapshots[2].raw == canonical(fixture_manifest()), "full-shape manifest changed"
    )
    require(
        files[QUALIFICATION]["sha256"] == QUALIFICATION_SHA256,
        "prior qualification changed",
    )
    for snapshot in snapshots:
        snapshot.revalidate()
    return core.with_digest(
        dict(
            schema_version=DOMAIN + "/source",
            execution_revision=approved,
            public_qualification_source=source,
            full_shape_files=files,
        )
    )


def qualify_baseline() -> dict:
    snapshot = core.FileSnapshot.capture(ROOT / QUALIFICATION)
    require(
        sha(snapshot.raw) == QUALIFICATION_SHA256, "prior qualification bytes differ"
    )
    receipt = core.parse_canonical(snapshot.raw)
    core.require_digest(receipt)
    _, reproduced = q.run_matrix()
    require(
        canonical(reproduced) == canonical(receipt["analysis"]),
        "32-trace qualification drifted",
    )
    snapshot.revalidate()
    return dict(
        receipt_file_sha256=QUALIFICATION_SHA256,
        receipt_digest=receipt["deterministic_digest"],
        analysis_digest=reproduced["deterministic_digest"],
        reproduced_trace_count=32,
        status="PRIOR_PUBLIC_QUALIFICATION_REPRODUCED",
    )


def binding(source: dict, runtime: dict, qualification: dict) -> dict:
    manifest = fixture_manifest()
    return core.with_digest(
        dict(
            schema_version=DOMAIN + "/binding",
            fixture_id=FIXTURE_ID,
            expected_cell_count=192,
            source=source,
            runtime=runtime,
            qualification=qualification,
            fixture_manifest_digest=manifest["deterministic_digest"],
            schedule_digest=manifest["schedule_digest"],
            development_execution_authorized=False,
        )
    )


def _check_environment(source: dict, runtime: dict) -> None:
    require(
        canonical(attest(source["execution_revision"])) == canonical(source),
        "source changed",
    )
    require(canonical(q.runtime_receipt()) == canonical(runtime), "runtime changed")


def run_rows(emit) -> dict:
    rows = []
    for cell in fixture_manifest()["cells"]:
        row = build_record(cell)
        emit(cell["cell_index"], row)
        rows.append(row)
    analysis = analyze_rows(rows)
    return core.with_digest(
        dict(
            schema_version=DOMAIN + "/receipt",
            fixture_id=FIXTURE_ID,
            status="PUBLIC_FULL_SHAPE_INTEGRITY_PASS",
            analysis=analysis,
            development_execution_authorized=False,
        )
    )


def _output(path: Path) -> Path:
    path = path.absolute()
    require(
        path.parent == ROOT / "artifacts/work"
        and path.parent.resolve(strict=True) == path.parent,
        "output must be a direct child of artifacts/work without aliases",
    )
    return path


def run(output: Path) -> dict:
    output = _output(output)
    require(not os.path.lexists(output), "public output directory already exists")
    source, runtime = attest(), q.runtime_receipt()
    qualification = qualify_baseline()
    inputs = binding(source, runtime, qualification)

    def check():
        _check_environment(source, runtime)

    return pub.publish(output, inputs, run_rows, check, check)


def analyze(output: Path) -> tuple[dict, object]:
    output = _output(output)
    publication = pub.inspect(output)
    inputs = publication.binding
    source = attest(inputs["source"]["execution_revision"])
    runtime = q.runtime_receipt()
    qualification = qualify_baseline()
    require(
        canonical(inputs) == canonical(binding(source, runtime, qualification)),
        "execution binding differs from independently checked inputs",
    )
    analysis = analyze_rows(publication.rows)
    expected_receipt = core.with_digest(
        dict(
            schema_version=DOMAIN + "/receipt",
            fixture_id=FIXTURE_ID,
            status="PUBLIC_FULL_SHAPE_INTEGRITY_PASS",
            analysis=analysis,
            development_execution_authorized=False,
        )
    )
    require(
        canonical(expected_receipt) == canonical(publication.receipt),
        "recomputed receipt differs",
    )
    publication.revalidate()
    _check_environment(source, runtime)
    summary = core.with_digest(
        dict(
            schema_version=DOMAIN + "/independent-summary",
            fixture_id=FIXTURE_ID,
            status="PUBLIC_FULL_SHAPE_INDEPENDENT_ANALYSIS_PASS",
            execution_commit_digest=publication.commit["deterministic_digest"],
            execution_receipt_digest=publication.receipt["deterministic_digest"],
            binding_digest=inputs["deterministic_digest"],
            source=source,
            runtime=runtime,
            qualification=qualification,
            analysis=analysis,
            development_execution_authorized=False,
            scientific_decision=None,
        )
    )
    return summary, publication


def analyze_and_save(output: Path, summary_path: Path) -> dict:
    summary_path = _output(summary_path)
    require(not os.path.lexists(summary_path), "summary already exists")
    summary, publication = analyze(output)

    def check():
        publication.revalidate()
        _check_environment(summary["source"], summary["runtime"])

    pub.publish_summary(summary_path, summary, check)
    return summary


def verify_summary(output: Path, summary_path: Path) -> dict:
    snapshot = core.FileSnapshot.capture(_output(summary_path))
    saved = core.parse_canonical(snapshot.raw)
    expected, publication = analyze(output)
    require(canonical(saved) == canonical(expected), "independent summary differs")
    snapshot.revalidate()
    publication.revalidate()
    return expected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--manifest", action="store_true")
    mode.add_argument("--run", type=Path)
    mode.add_argument("--analyze", type=Path)
    mode.add_argument("--verify", type=Path)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()
    if args.manifest:
        require(args.summary is None, "manifest does not take a summary")
        sys.stdout.buffer.write(canonical(fixture_manifest()))
        return
    if args.run:
        require(args.summary is None, "run does not take a summary")
        result = run(args.run)
    else:
        require(args.summary is not None, "analyze/verify requires a summary path")
        result = (
            analyze_and_save(args.analyze, args.summary)
            if args.analyze
            else verify_summary(args.verify, args.summary)
        )
    print(
        canonical(
            dict(
                status=result["status"],
                deterministic_digest=result["deterministic_digest"],
                public_cell_count=192,
                prefix_check_count=96,
                development_execution_authorized=False,
            )
        ).decode(),
        end="",
    )


if __name__ == "__main__":
    main()
