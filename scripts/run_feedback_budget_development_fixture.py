#!/usr/bin/env python3
"""Qualify the new execution/analysis/publication path on fixed public tasks.

No development cohort, authorization, resume, provider or arbitrary-task entry
point exists. Independent analysis rereads a complete durable publication.
"""

from __future__ import annotations

import argparse
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = "scripts/run_feedback_budget_development_fixture.py"
KERNEL = "scripts/feedback_budget_development_kernel.py"
ANALYSIS = "scripts/feedback_budget_development_analysis.py"
PUBLICATION = "scripts/feedback_budget_development_publication.py"
BASE_REVISION = "6a375be06c3d1da0fc3618f176264ca473291355"
SPEC = importlib.util.spec_from_file_location(
    "feedback_budget_development_kernel", ROOT / KERNEL
)
assert SPEC is not None and SPEC.loader is not None
k = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = k
SPEC.loader.exec_module(k)
analysis = k.load("feedback_budget_development_analysis", ANALYSIS)
pub = k.load("feedback_budget_development_publication", PUBLICATION)
q, core, canonical, require = k.q, k.core, k.canonical, k.require
DOMAIN = k.DOMAIN


def _origin(module, relative):
    spec, cache = module.__spec__, module.__cached__
    require(
        type(spec.loader) is importlib.machinery.SourceFileLoader
        and Path(spec.origin) == ROOT / relative
        and Path(module.__file__) == ROOT / relative,
        "sibling source origin differs",
    )
    require(
        type(cache) is str
        and Path(cache).is_relative_to(Path(sys.pycache_prefix))
        and not os.path.lexists(cache),
        "sibling bytecode cache not absent",
    )


def attest(revision=None):
    public_source = q.attest(ROOT, revision)
    approved, head = public_source["qualification_revision"], core.git_head(ROOT)
    core.require_ancestor(ROOT, BASE_REVISION, approved)
    require(Path(__file__).resolve() == ROOT / SCRIPT, "runner source origin differs")
    for module, path in (
        (k, KERNEL),
        (k.contract, k.CONTRACT),
        (q, q.SCRIPT),
        (analysis, ANALYSIS),
        (pub, PUBLICATION),
        (pub.storage, pub.STORAGE),
    ):
        _origin(module, path)
    paths = tuple(
        dict.fromkeys(
            (
                SCRIPT,
                KERNEL,
                ANALYSIS,
                PUBLICATION,
                k.CONTRACT,
                pub.STORAGE,
                k.FIXTURE,
                *k.contract.PINNED_FILES,
            )
        )
    )
    files, snapshots = {}, []
    for relative in paths:
        snapshot = core.FileSnapshot.capture(ROOT / relative)
        require(
            snapshot.raw
            == core._regular_git_blob(ROOT, approved, relative)
            == core._regular_git_blob(ROOT, head, relative),
            "development-path source bytes changed",
        )
        files[relative] = dict(byte_count=len(snapshot.raw), sha256=q.sha(snapshot.raw))
        if relative == k.FIXTURE:
            require(
                snapshot.raw == canonical(k.fixture_manifest()),
                "fixed public manifest changed",
            )
        snapshots.append(snapshot)
    for snapshot in snapshots:
        snapshot.revalidate()
    require(
        head == core.git_head(ROOT)
        and not core.git_bytes(ROOT, "status", "--porcelain", "--untracked-files=all"),
        "checkout changed during attestation",
    )
    require(
        canonical(q.attest(ROOT, approved)) == canonical(public_source),
        "protected search source changed",
    )
    return core.with_digest(
        dict(
            schema_version=DOMAIN + "/source",
            execution_revision=approved,
            public_qualification_source=public_source,
            development_path_files=files,
        )
    )


def qualify_baseline():
    path = k.contract.QUALIFICATION
    snapshot = core.FileSnapshot.capture(ROOT / path)
    require(
        q.sha(snapshot.raw) == k.contract.PINNED_FILES[path],
        "32-trace receipt bytes differ",
    )
    saved = core.parse_canonical(snapshot.raw)
    core.require_digest(saved)
    _, reproduced = q.run_matrix()
    require(
        canonical(reproduced) == canonical(saved["analysis"]),
        "32-trace public qualification drifted",
    )
    snapshot.revalidate()
    return core.with_digest(
        dict(
            schema_version=DOMAIN + "/baseline-qualification",
            receipt_file_sha256=q.sha(snapshot.raw),
            receipt_digest=saved["deterministic_digest"],
            reproduced_analysis_digest=reproduced["deterministic_digest"],
            reproduced_trace_count=32,
            status="PUBLIC_BASELINE_REPRODUCED",
        )
    )


def runtime_receipt():
    runtime = q.runtime_receipt()
    require(
        canonical(runtime)
        == canonical(k.contract.build_contract()["runtime_requirement"]),
        "frozen CPython/arm64/CPU binary64 runtime differs",
    )
    return runtime


def check_environment(source, runtime):
    require(
        canonical(attest(source["execution_revision"])) == canonical(source),
        "source changed",
    )
    require(canonical(runtime_receipt()) == canonical(runtime), "runtime changed")


def reduce_rows(inputs, rows, binding, stage_observer=None):
    observe = stage_observer or (lambda stage: None)
    observe(analysis.STAGES[1])
    records, integrity = k.replay_matrix(inputs, rows, binding)
    observe(analysis.STAGES[2])
    reduced = analysis.reduce_matrix(inputs, records, stage_observer=observe)
    return core.with_digest(
        dict(
            schema_version=DOMAIN + "/execution-receipt",
            status="DEVELOPMENT_PATH_FIXTURE_INTEGRITY_AND_REDUCTION_PASS",
            execution_mode=k.MODE,
            run_binding_digest=binding["deterministic_digest"],
            integrity=integrity,
            reduction=reduced,
            development_cells_executed=0,
            development_execution_authorized=False,
            scientific_decision=None,
        )
    )


def _output(path):
    path = Path(path).absolute()
    require(
        path.parent == ROOT / "artifacts/work"
        and path.parent.resolve(strict=True) == path.parent,
        "output must be a direct child of artifacts/work without aliases",
    )
    return path


def run(output):
    output = _output(output)
    require(not os.path.lexists(output), "output directory already occupied")
    source, runtime = attest(), runtime_receipt()
    qualification, inputs = qualify_baseline(), k.public_inputs()
    binding = k.binding(inputs, source, runtime, qualification)

    def action(emit):
        rows = []
        for cell in inputs.cells:
            row = k.record(inputs, cell, binding)
            emit(cell["cell_index"], row)
            rows.append(row)
        return reduce_rows(inputs, rows, binding)

    return pub.publish(
        output, binding, action, lambda: check_environment(source, runtime)
    )


def analyze(output):
    publication = pub.inspect(_output(output))
    binding = publication.binding
    inputs = k.public_inputs()
    k.validate_binding(inputs, binding)
    source = attest(binding["source"]["execution_revision"])
    runtime, qualification = runtime_receipt(), qualify_baseline()
    require(
        canonical(binding)
        == canonical(k.binding(inputs, source, runtime, qualification)),
        "independently admitted run-binding differs",
    )
    receipt = reduce_rows(inputs, publication.rows, binding)
    require(
        canonical(receipt) == canonical(publication.receipt),
        "independently recomputed receipt differs",
    )
    publication.revalidate()
    check_environment(source, runtime)
    summary = core.with_digest(
        dict(
            schema_version=DOMAIN + "/analysis",
            status="DEVELOPMENT_PATH_FIXTURE_INDEPENDENT_ANALYSIS_PASS",
            execution_mode=k.MODE,
            experiment_id=k.FIXTURE_ID,
            execution_commit_digest=publication.commit["deterministic_digest"],
            execution_receipt_digest=receipt["deterministic_digest"],
            run_binding_digest=binding["deterministic_digest"],
            source=source,
            runtime=runtime,
            qualification=qualification,
            fixture_manifest_digest=inputs.manifest["deterministic_digest"],
            integrity=receipt["integrity"],
            reduction=receipt["reduction"],
            public_task_count=12,
            public_source_multiset_count=1,
            development_cells_executed=0,
            production_admission_implemented=False,
            development_execution_authorized=False,
            locked_128_evaluation_authorized=False,
            scientific_decision=None,
            claim_boundary="public single-source pipeline qualification only; no development or causal evidence",
        )
    )
    return summary, publication


def analyze_and_save(output, summary_path):
    summary_path = _output(summary_path)
    require(not os.path.lexists(summary_path), "summary already occupied")
    summary, publication = analyze(output)

    def check():
        publication.revalidate()
        check_environment(summary["source"], summary["runtime"])

    pub.publish_summary(summary_path, summary, check)
    return summary


def verify(output, summary_path):
    snapshot = core.FileSnapshot.capture(_output(summary_path))
    saved = core.parse_canonical(snapshot.raw)
    summary, publication = analyze(output)
    require(canonical(saved) == canonical(summary), "saved independent summary differs")
    snapshot.revalidate()
    publication.revalidate()
    return summary


def self_test():
    inputs = k.public_inputs()
    require(len(inputs.cells) == 192, "fixture shape differs")
    zero = [[[0, 0, 0, 0] for _ in range(4)] for _ in range(12)]
    reduced = analysis.factorial(zero, [[False] * 4 for _ in range(12)])
    require(
        reduced["screen_conjunction"] is False and len(reduced["pattern_counts"]) == 16,
        "synthetic null screen differs",
    )
    return dict(
        status="DEVELOPMENT_PATH_PREFLIGHT_NO_SEARCH_PASS",
        fixture_manifest_digest=inputs.manifest["deterministic_digest"],
        cell_count=192,
        production_admission_implemented=False,
        search_calls=0,
        development_cells_executed=0,
        development_execution_authorized=False,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--manifest", action="store_true")
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--run-public", type=Path)
    mode.add_argument("--analyze-public", type=Path)
    mode.add_argument("--verify-public", type=Path)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()
    try:
        if args.manifest or args.self_test:
            require(args.summary is None, "preflight does not take summary")
            result = k.fixture_manifest() if args.manifest else self_test()
        elif args.run_public:
            require(args.summary is None, "execution does not take summary")
            result = run(args.run_public)
        else:
            require(
                args.summary is not None, "independent analysis requires summary path"
            )
            result = (
                analyze_and_save(args.analyze_public, args.summary)
                if args.analyze_public
                else verify(args.verify_public, args.summary)
            )
        if not (args.manifest or args.self_test):
            result = dict(
                status=result["status"],
                deterministic_digest=result["deterministic_digest"],
                public_cell_count=192,
                budget_prefix_check_count=96,
                development_cells_executed=0,
                development_execution_authorized=False,
            )
        sys.stdout.buffer.write(canonical(result))
        return 0
    except (ValueError, OSError, RuntimeError, KeyError, TypeError) as error:
        sys.stdout.buffer.write(
            canonical(
                dict(
                    status="INVALID_ANALYSIS",
                    error_type=type(error).__name__,
                    reason=str(error),
                    scientific_decision=None,
                    development_execution_authorized=False,
                )
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
