#!/usr/bin/env python3
"""v7 outcome-blind cohort sealing after NEW full connector qualification.

Sealing independently re-verifies the NEW connector PUBLIC experiment and
historical identity authorities. It is a separate digest-confirmed operation. No execution
authorization, search adapter, consumption registry or replication run is exposed.
"""

from __future__ import annotations

import argparse
from collections import Counter
import importlib.util
import os
from pathlib import Path
import secrets
import sys
from types import MappingProxyType


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = "scripts/feedback_budget_replication_admission.py"
PUBLIC_RUNNER = "scripts/run_feedback_budget_replication_fixture.py"
SPEC = importlib.util.spec_from_file_location(
    "feedback_budget_admission_public", ROOT / PUBLIC_RUNNER
)
assert SPEC is not None and SPEC.loader is not None
public = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = public
SPEC.loader.exec_module(public)
k, q, core = public.k, public.q, public.core
contract = k.contract
canonical, digest, require = k.canonical, k.digest, k.require
storage = public.pub.storage
mechanics = storage.mechanics
historical = core.manifest
DOMAIN = contract.DOMAIN
MODE = "sealed_replication_cohort"
BASE = "e5964e0905c5a80260589ab81dafed31353d0c8d"
# Keep the generation transaction outside the tracked source tree: STARTED
# must not itself dirty the source-qualified checkout. Promotion is separate.
COHORT_PATH = ROOT / "artifacts/work/feedback-budget-replication-cohort-v7"
PUBLIC_SUMMARY = "docs/qualifications/countdown_feedback_budget_v7_public_pipeline_20260913.summary.json"
PUBLIC_COMMIT = "docs/qualifications/countdown_feedback_budget_v7_public_pipeline_20260913.commit.json"
PUBLIC_PINS = {
    PUBLIC_SUMMARY: "0c2bef6632aae6410eae5db7423d13482e6775622cfcce355490bbff96105432",
    PUBLIC_COMMIT: "7d4594abca5a00a5be25168e807d48b8ade195c6c90c1155829edaae7d40bce9",
}
EXECUTION = "scripts/run_feedback_budget_replication_execution.py"
EXECUTION_STORAGE = "scripts/feedback_budget_replication_execution_storage.py"
EXECUTION_ANALYSIS = "scripts/feedback_budget_replication_execution_analysis.py"
FIXTURE_TESTS = (
    "tests/test_feedback_budget_replication_admission.py",
    "tests/test_feedback_budget_replication_execution.py",
)
_AUTHORITY_CACHE = None
NAMES = frozenset(("STARTED.json", "preregistration.json", "SEALED.json"))


def snapshot_file(path):
    return core.FileSnapshot.capture(path, byte_cap=public.pub.MAX_CONTROL_BYTES)


def source_receipt(revision=None):
    source = public.attest(revision)
    approved = source["execution_revision"]
    core.require_ancestor(ROOT, BASE, approved)
    public._origin(public, PUBLIC_RUNNER)
    require(
        Path(__file__).resolve() == ROOT / SCRIPT, "admission source origin differs"
    )
    files, snapshots = {}, []
    for relative in (
        SCRIPT,
        EXECUTION,
        EXECUTION_STORAGE,
        EXECUTION_ANALYSIS,
        *FIXTURE_TESTS,
        *PUBLIC_PINS,
    ):
        snapshot = snapshot_file(ROOT / relative)
        require(
            snapshot.raw
            == core._regular_git_blob(ROOT, approved, relative)
            == core._regular_git_blob(ROOT, core.git_head(ROOT), relative),
            "admission protected bytes differ",
        )
        if relative in PUBLIC_PINS:
            require(
                q.sha(snapshot.raw) == PUBLIC_PINS[relative],
                "public receipt bytes differ",
            )
        files[relative] = dict(byte_count=len(snapshot.raw), sha256=q.sha(snapshot.raw))
        snapshots.append(snapshot)
    for snapshot in snapshots:
        snapshot.revalidate()
    require(
        canonical(public.attest(approved)) == canonical(source),
        "source changed during admission attestation",
    )
    return core.with_digest(
        dict(
            schema_version=DOMAIN + "/admission-source",
            admission_revision=approved,
            public_path_source=source,
            admission_files=files,
        )
    )


def verified_authorities():
    """Verify old generation orders once per process; never the new 64-task recipe.

    Cached evidence is immutable and all fixed-input snapshots are revalidated.
    Admission separately reattests executing source/runtime on every context
    check. No search outcome or calibration/witness object is dereferenced.
    """
    global _AUTHORITY_CACHE
    candidate = contract.build_contract()
    if _AUTHORITY_CACHE is not None:
        raw, snapshots = _AUTHORITY_CACHE
        for item in snapshots:
            item.revalidate()
        value = core.parse_canonical(raw)
        require(
            value["contract_digest"] == candidate["deterministic_digest"],
            "cached identity authority contract differs",
        )
        return value
    base, values, snapshots = contract._context(ROOT)
    verified = historical.verify_countdown_thompson_dense_scale_bundle(
        (ROOT / contract.old.V5).parent, repository_root=ROOT
    )
    require(
        canonical(verified.payload) == canonical(values[contract.old.V5]),
        "verified historical v5 bytes differ",
    )
    old_values, old_snapshots = contract.old._read_inputs(ROOT)
    old_values[contract.old.V5] = verified.payload
    old_exclusions = contract.old._exclusions(old_values)
    require(
        canonical(old_exclusions) == canonical(base["exclusion_identities"]),
        "verified historical six-group exclusions differ",
    )
    # Reproduce the already consumed v6 cohort's acceptance order only. This is
    # identity/solvability verification, not rerunning its search or claim.
    suite = historical.generate_solvable_task_suite(
        12,
        26090401,
        max_attempts=10000,
        excluded_task_fingerprints=tuple(old_exclusions["task_fingerprints"]),
        excluded_source_multiset_fingerprints=tuple(
            old_exclusions["source_multiset_fingerprints"]
        ),
        excluded_identity_record_digest=old_exclusions["deterministic_digest"],
    )
    old_cohort = values[contract.V6]["cohort"]
    require(
        canonical([task.to_dict() for task in suite.tasks])
        == canonical(old_cohort["tasks"])
        and canonical(suite.generation_manifest)
        == canonical(old_cohort["generation_manifest"]),
        "historical v6 acceptance order differs",
    )
    exclusions = contract._exclusions(base, values)
    require(
        canonical(exclusions) == canonical(candidate["exclusion_identities"])
        and len(exclusions["task_fingerprints"]) == 243
        and len(exclusions["source_multiset_fingerprints"]) == 179,
        "verified eight-group exclusion closure differs",
    )
    snapshots = tuple([*snapshots, *old_snapshots])
    for item in snapshots:
        item.revalidate()
    value = core.with_digest(
        dict(
            schema_version=DOMAIN + "/verified-identity-authorities",
            contract_digest=candidate["deterministic_digest"],
            v5_seal_digest=verified.seal_digest,
            v6_seal_digest=values[contract.V6]["deterministic_digest"],
            v6_generation_manifest_digest=suite.generation_manifest[
                "generation_manifest_digest"
            ],
            exclusion_identities=exclusions,
            role="verified_identity_exclusions_only_not_execution_authority",
            historical_cohort_regeneration_counts={"v6": 12},
            new_replication_tasks_generated=0,
            locked_128_evaluation_authorized=False,
        )
    )
    _AUTHORITY_CACHE = (canonical(value), snapshots)
    return core.parse_canonical(canonical(value))


def public_evidence():
    snapshots = {p: snapshot_file(ROOT / p) for p in PUBLIC_PINS}
    for path, item in snapshots.items():
        require(q.sha(item.raw) == PUBLIC_PINS[path], "public evidence bytes differ")
    summary, commit = (
        core.parse_canonical(snapshots[p].raw) for p in (PUBLIC_SUMMARY, PUBLIC_COMMIT)
    )
    for value in (summary, commit):
        core.require_digest(value)
    require(
        summary["execution_commit_digest"] == commit["deterministic_digest"],
        "public summary/COMMIT linkage differs",
    )
    require(
        summary["scientific_decision"] is None
        and summary["replication_execution_authorized"] is False
        and summary["public_pipeline_qualified"] is True
        and summary["public_source_multiset_count"] == 1
        and summary["integrity"]["cell_count"] == 1024,
        "public evidence was promoted",
    )
    require(
        canonical(public.attest(summary["source"]["execution_revision"]))
        == canonical(summary["source"]),
        "qualified public executable changed",
    )
    for item in snapshots.values():
        item.revalidate()
    return core.with_digest(
        dict(
            schema_version=DOMAIN + "/public-admission-reference",
            summary_digest=summary["deterministic_digest"],
            execution_commit_digest=commit["deterministic_digest"],
            file_sha256=dict(PUBLIC_PINS),
            role="fixed_public_pipeline_evidence_not_replication_evidence",
        )
    )


def context(revision=None):
    source, runtime = source_receipt(revision), public.runtime_receipt()
    authorities, evidence = verified_authorities(), public_evidence()
    require(
        canonical(source_receipt(source["admission_revision"])) == canonical(source),
        "admission source changed",
    )
    require(
        canonical(public.runtime_receipt()) == canonical(runtime),
        "admission runtime changed",
    )
    return core.with_digest(
        dict(
            schema_version=DOMAIN + "/admission-context",
            source=source,
            runtime=runtime,
            authorities=authorities,
            public_evidence=evidence,
            replication_execution_authorized=False,
        )
    )


def revalidate_context(value):
    require(
        canonical(context(value["source"]["admission_revision"])) == canonical(value),
        "admission context changed",
    )


def _tasks(rows, candidate):
    require(
        type(rows) is list and len(rows) == 64,
        "exactly 64 replication task rows required",
    )
    identities = []
    for slot, row in enumerate(rows):
        require(
            type(row) is dict and type(row.get("inputs")) is list,
            "closed task row required",
        )
        inputs, target = row["inputs"], row.get("target")
        require(
            len(inputs) == 6 and all(type(x) is int and 1 <= x <= 10 for x in inputs),
            "D6 input range differs",
        )
        require(
            type(target) is int and 100 <= target <= 999,
            "replication target range differs",
        )
        task = q.CountdownTask(tuple(inputs), target)
        require(
            canonical(row) == canonical(task.to_dict()),
            "task identity or fields differ",
        )
        identities.append(
            dict(
                task_slot=slot,
                task_fingerprint=task.task_fingerprint,
                source_multiset_fingerprint=task.source_multiset_fingerprint,
            )
        )
    # Both kinds of uniqueness and all eight exclusions, before any regeneration.
    contract._schedule(candidate, identities)
    return identities


def _cohort(candidate, authorities):
    exclusions = authorities["exclusion_identities"]
    require(
        canonical(exclusions) == canonical(candidate["exclusion_identities"]),
        "cohort exclusion authority differs",
    )
    suite = historical.generate_solvable_task_suite(
        64,
        26091301,
        max_attempts=10000,
        excluded_task_fingerprints=tuple(exclusions["task_fingerprints"]),
        excluded_source_multiset_fingerprints=tuple(
            exclusions["source_multiset_fingerprints"]
        ),
        excluded_identity_record_digest=exclusions["deterministic_digest"],
    )
    # Do not access suite.calibrations: witnesses/hardness never enter this layer.
    rows = [task.to_dict() for task in suite.tasks]
    _tasks(rows, candidate)
    result = core.with_digest(
        dict(
            schema_version=DOMAIN + "/cohort",
            experiment_id=contract.EXPERIMENT_ID,
            tasks=rows,
            task_set_digest=digest(rows),
            generation_recipe=candidate["generation_recipe"],
            generation_manifest=suite.generation_manifest,
            authority_digest=authorities["deterministic_digest"],
            exclusion_identity_digest=exclusions["deterministic_digest"],
            persisted_calibration_profile_count=0,
            persisted_solution_witness_count=0,
        )
    )
    _cohort_shape(result, candidate, authorities)
    return result


def _cohort_shape(cohort, candidate, authorities):
    """Close metadata/identity before the independent solver regeneration."""
    core.require_digest(cohort)
    rows = cohort["tasks"]
    _tasks(rows, candidate)
    exclusions = authorities["exclusion_identities"]
    generation = cohort["generation_manifest"]
    require(type(generation) is dict, "generation manifest object required")
    attempts, log = generation.get("attempt_count"), generation.get("rejection_log")
    require(
        type(attempts) is int and 64 <= attempts <= 10000, "generation attempts differ"
    )
    require(
        type(log) is list and len(log) == attempts - 64,
        "generation rejection count differs",
    )
    reasons = (
        "duplicate_full_task",
        "duplicate_source_multiset",
        "excluded_full_task",
        "excluded_source_multiset",
        "unsolvable",
    )
    counts, previous = Counter(), -1
    for row in log:
        require(
            type(row) is dict
            and set(row)
            == {"attempt", "reason", "task_fingerprint", "source_multiset_fingerprint"},
            "rejection fields differ",
        )
        attempt = row["attempt"]
        require(
            type(attempt) is int and previous < attempt < attempts - 1,
            "rejection attempt order differs",
        )
        require(row["reason"] in reasons, "rejection reason differs")
        for field in ("task_fingerprint", "source_multiset_fingerprint"):
            core.require_sha256(row[field], field)
        counts[row["reason"]] += 1
        previous = attempt
    expected = dict(
        accepted_count=64,
        accepted_task_pool_digest=digest(rows),
        attempt_count=attempts,
        conditioned_on_exhaustive_solvability=True,
        excluded_identity_record_digest=exclusions["deterministic_digest"],
        excluded_source_multiset_fingerprint_count=len(
            exclusions["source_multiset_fingerprints"]
        ),
        excluded_source_multiset_fingerprint_digest=digest(
            exclusions["source_multiset_fingerprints"]
        ),
        excluded_task_fingerprint_count=len(exclusions["task_fingerprints"]),
        excluded_task_fingerprint_digest=digest(exclusions["task_fingerprints"]),
        generator_id=candidate["generation_recipe"]["generator"],
        input_range_inclusive=[1, 10],
        max_attempts=10000,
        rejection_counts={reason: counts[reason] for reason in reasons},
        rejection_log=log,
        requested_count=64,
        seed=26091301,
        source_multisets_unique=True,
        target_range_inclusive=[100, 999],
    )
    expected["generation_manifest_digest"] = digest(expected)
    require(
        canonical(generation) == canonical(expected),
        "closed generation manifest differs",
    )
    expected = core.with_digest(
        dict(
            schema_version=DOMAIN + "/cohort",
            experiment_id=contract.EXPERIMENT_ID,
            tasks=rows,
            task_set_digest=digest(rows),
            generation_recipe=candidate["generation_recipe"],
            generation_manifest=generation,
            authority_digest=authorities["deterministic_digest"],
            exclusion_identity_digest=exclusions["deterministic_digest"],
            persisted_calibration_profile_count=0,
            persisted_solution_witness_count=0,
        )
    )
    require(canonical(cohort) == canonical(expected), "closed cohort fields differ")


def _seal(cohort, candidate, admission, pipeline):
    generation_reference_shape(pipeline)
    _tasks(cohort["tasks"], candidate)
    cells = []
    for slot, budget, scale, seed in k.COORDINATES:
        row = cohort["tasks"][slot]
        key = dict(
            schema_version=DOMAIN + "/cell-key",
            execution_mode=MODE,
            experiment_id=contract.EXPERIMENT_ID,
            contract_digest=candidate["deterministic_digest"],
            cohort_digest=cohort["deterministic_digest"],
            task_set_digest=cohort["task_set_digest"],
            task_slot=slot,
            task_fingerprint=row["task_fingerprint"],
            source_multiset_fingerprint=row["source_multiset_fingerprint"],
            budget=budget,
            scale=scale,
            seed=seed,
            budget_spec_digest=digest(q.profile(budget).to_dict()),
            method_spec_digest=digest(q.method(scale).to_dict()),
            proposal_spec_digest=digest(q.PROPOSAL.to_dict()),
        )
        cells.append(dict(cell_index=len(cells), cell_id=digest(key), cell_key=key))
    indexed = dict(zip(k.COORDINATES, (c["cell_id"] for c in cells)))
    return core.with_digest(
        dict(
            schema_version=DOMAIN + "/preregistration",
            execution_mode=MODE,
            experiment_id=contract.EXPERIMENT_ID,
            contract=candidate,
            cohort=cohort,
            admission_context=admission,
            generation_qualification=pipeline,
            cells=cells,
            schedule_digest=digest(cells),
            budget_prefix_pairs=[
                dict(
                    task_slot=t,
                    scale=s,
                    seed=r,
                    low_cell_id=indexed[t, 256, s, r],
                    high_cell_id=indexed[t, 512, s, r],
                )
                for t in range(64)
                for s in q.SCALES
                for r in q.SEEDS
            ],
            four_cell_blocks=[
                dict(
                    task_slot=t,
                    seed=r,
                    arm_cell_ids=[indexed[t, b, s, r] for b, s in k.ARMS],
                )
                for t in range(64)
                for r in q.SEEDS
            ],
            cell_count=1024,
            task_count=64,
            source_multiset_count=64,
            status="SEALED_COHORT_NOT_EXECUTION_AUTHORITY",
            replication_execution_authorized=False,
            locked_128_evaluation_authorized=False,
        )
    )


def validate_seal_bytes(raw):
    value = core.parse_canonical(raw)
    core.require_digest(value)
    require(
        value.get("schema_version") == DOMAIN + "/preregistration"
        and value.get("execution_mode") == MODE,
        "sealed replication domain required",
    )
    require(
        value.get("experiment_id") == contract.EXPERIMENT_ID,
        "replication experiment differs",
    )
    candidate = contract.build_contract()
    require(
        canonical(value.get("contract")) == canonical(candidate),
        "sealed contract differs",
    )
    cohort = value["cohort"]
    core.require_digest(cohort)
    _tasks(cohort["tasks"], candidate)
    admission = value["admission_context"]
    _cohort_shape(cohort, candidate, admission["authorities"])
    require(
        canonical(
            _seal(cohort, candidate, admission, value["generation_qualification"])
        )
        == raw,
        "closed preregistration differs",
    )
    # Authoritative source/runtime/old seals close BEFORE invoking the new recipe.
    revalidate_context(admission)
    pipeline, check_pipeline = verify_generation_reference(
        value["generation_qualification"], admission
    )
    expected = _seal(
        _cohort(candidate, admission["authorities"]), candidate, admission, pipeline
    )
    check_pipeline()
    require(
        canonical(expected) == raw,
        "cohort differs from exact generator acceptance order",
    )
    revalidate_context(admission)
    return expected


def _location(path):
    path = Path(path).absolute()
    require(
        path == COHORT_PATH and path.parent.resolve(strict=True) == path.parent,
        "only the fixed v7 cohort location is allowed",
    )
    return path


def _started(admission, nonce, pipeline):
    generation_reference_shape(pipeline)
    require(
        type(nonce) is str
        and len(nonce) == 64
        and all(c in "0123456789abcdef" for c in nonce),
        "seal nonce differs",
    )
    return core.with_digest(
        dict(
            schema_version=DOMAIN + "/cohort-started",
            experiment_id=contract.EXPERIMENT_ID,
            admission_context=admission,
            owner_nonce=nonce,
            generation_qualification=pipeline,
            status="COHORT_GENERATION_STARTED_NOT_EXECUTION_AUTHORITY",
            replication_execution_authorized=False,
        )
    )


def _closed(started, seal):
    return core.with_digest(
        dict(
            schema_version=DOMAIN + "/cohort-sealed",
            status="COHORT_SEALED_NOT_AUTHORIZED",
            started_sha256=q.sha(canonical(started)),
            seal_sha256=q.sha(canonical(seal)),
            seal_byte_count=len(canonical(seal)),
            seal_digest=seal["deterministic_digest"],
            replication_execution_authorized=False,
        )
    )


class SealedInputs:
    """Detached bytes and exact directory generation; never an execution token."""

    __slots__ = ("_raw", "_generation", "_path")

    def __init__(self, *args):
        raise TypeError("use load_seal; raw constructors are not admission")

    def __setattr__(self, name, value):
        raise AttributeError("sealed inputs are immutable")

    @property
    def manifest(self):
        return core.parse_canonical(self._raw["preregistration.json"])

    def revalidate(self):
        parent = mechanics._PinnedParent.open(self._path)
        try:
            raw, generation = storage._observe(parent, NAMES)
            require(
                raw == dict(self._raw) and generation == self._generation,
                "sealed directory changed",
            )
        finally:
            parent.close()


def load_seal(path):
    path = _location(path)
    parent = mechanics._PinnedParent.open(path)
    try:
        raw, generation = storage._observe(parent, NAMES)
        # Transaction-content closure is a prerequisite to regeneration, not
        # merely a post-solver check. An uncertain/partial final marker must
        # never cause the fixed new recipe to run.
        seal = core.parse_canonical(raw["preregistration.json"])
        core.require_digest(seal)
        started = core.parse_canonical(raw["STARTED.json"])
        require(
            canonical(
                _started(
                    seal["admission_context"],
                    started["owner_nonce"],
                    seal["generation_qualification"],
                )
            )
            == raw["STARTED.json"],
            "cohort STARTED differs",
        )
        require(
            canonical(_closed(started, seal)) == raw["SEALED.json"],
            "cohort final seal differs",
        )
        validate_seal_bytes(raw["preregistration.json"])
        after, final_generation = storage._observe(parent, NAMES)
        require(
            raw == after and generation == final_generation,
            "cohort changed during verification",
        )
        value = object.__new__(SealedInputs)
        # The proxy contains only bytes; neither layer retains a writable alias.
        object.__setattr__(value, "_raw", MappingProxyType(raw))
        object.__setattr__(value, "_generation", generation)
        object.__setattr__(value, "_path", path)
        return value
    finally:
        parent.close()


def _publish_cohort(path, admission, build, check, pipeline):
    """Private storage primitive; callers must independently admit context first."""
    parent = storage._create_directory(path)
    owned, commit_attempted = [], False

    def create(name, value):
        try:
            item = mechanics._exclusive_create_exact(
                parent,
                name,
                canonical(value),
                max_bytes=storage.MAX_CONTROL_BYTES,
                hook=None,
            )
        except mechanics._CreateAfterOpenError as error:
            owned.append(error.owned)
            raise
        owned.append(item)

    try:
        started = _started(admission, secrets.token_hex(32), pipeline)
        create("STARTED.json", started)
        storage._observe(parent, ("STARTED.json",), owned=owned)
        check()
        seal = build()
        check()
        create("preregistration.json", seal)
        storage._observe(parent, ("STARTED.json", "preregistration.json"), owned=owned)
        check()
        commit_attempted = True
        create("SEALED.json", _closed(started, seal))
        storage._observe(parent, NAMES, owned=owned)
        check()
        storage._observe(parent, NAMES, owned=owned)
        return seal
    except BaseException as error:
        if commit_attempted:
            raise storage.PublicationUncertain(
                "cohort final seal uncertain; retain occupied directory"
            ) from error
        try:
            create(
                "FAILURE.json",
                core.with_digest(
                    dict(
                        schema_version=DOMAIN + "/cohort-failure",
                        status="COHORT_GENERATION_FAILED_RETAIN_DO_NOT_RETRY",
                        error_type=type(error).__name__,
                        replication_execution_authorized=False,
                    )
                ),
            )
        except BaseException:
            pass
        raise
    finally:
        for item in owned:
            item.close()
        parent.close()


def candidate(sealed, output):
    """Exact REVIEW candidate; no permission bit or execution loader exists."""
    require(type(sealed) is SealedInputs, "verified sealed inputs required")
    sealed.revalidate()
    value = sealed.manifest
    revalidate_context(value["admission_context"])
    output = public._output(output)
    require(not os.path.lexists(output), "candidate output already occupied")
    parent = mechanics._PinnedParent.open(output.parent)
    try:
        parent.assert_path()
        binding = core.with_digest(
            dict(
                schema_version=DOMAIN + "/candidate-output-parent",
                path=str(output.parent),
                component_identities=[list(x) for x in parent.component_identities],
            )
        )
        result = core.with_digest(
            dict(
                schema_version=DOMAIN + "/seal-review-candidate",
                scope="REVIEW_ONLY_NOT_EXECUTABLE",
                experiment_id=contract.EXPERIMENT_ID,
                status="PENDING_REVIEW_AND_EXPLICIT_PERMISSION",
                seal_digest=value["deterministic_digest"],
                seal_path=str(sealed._path),
                seal_sha256=q.sha(canonical(value)),
                contract_digest=value["contract"]["deterministic_digest"],
                cohort_digest=value["cohort"]["deterministic_digest"],
                schedule_digest=value["schedule_digest"],
                expected_cell_count=1024,
                admission_context=value["admission_context"],
                output_path=str(output),
                output_parent=binding,
                requires_exact_digest_confirmation=True,
                execution_adapter_qualified=False,
                authorization_consumption_implemented=False,
                replication_execution_authorized=False,
                locked_128_evaluation_authorized=False,
            )
        )
        revalidate_context(value["admission_context"])
        sealed.revalidate()
        parent.assert_path()
        require(not os.path.lexists(output), "candidate output became occupied")
        return result
    finally:
        parent.close()


def validate_candidate(raw, sealed, output, expected_digest):
    core.require_sha256(expected_digest, "reviewed candidate digest")
    value = core.parse_canonical(raw)
    core.require_digest(value)
    require(
        value["deterministic_digest"] == expected_digest,
        "reviewed candidate digest differs",
    )
    require(
        canonical(candidate(sealed, output)) == raw, "exact review candidate differs"
    )
    return value


def negative_checks():
    """Read-only domain negatives; no generator, solver or replication search."""
    values = {
        "identity_only_contract": contract.build_contract(),
        "identity_only_schedule": contract.build_schedule_candidate(
            contract.synthetic_identities()
        ),
        "public_execution_fixture": k.fixture_manifest(),
        "old_v5_preregistration": core.parse_canonical(
            snapshot_file(ROOT / contract.old.V5).raw
        ),
        "public_analysis": core.parse_canonical(
            snapshot_file(ROOT / PUBLIC_SUMMARY).raw
        ),
    }
    for name in (
        "countdown_track_a_canary_v2",
        "countdown_thompson_diagnostic_v1",
        "countdown_thompson_dense_scale_v5",
    ):
        values["old_authorization_" + name] = core.parse_canonical(
            snapshot_file(
                ROOT / f"docs/preregistrations/{name}_execution_authorization.json"
            ).raw
        )
    rejected = []
    for label, value in values.items():
        try:
            validate_seal_bytes(canonical(value))
        except ValueError:
            rejected.append(label)
        else:
            raise ValueError(f"non-replication input admitted: {label}")
    return dict(
        rejected_as_replication_seals=rejected,
        new_replication_tasks_generated=0,
        replication_search_calls=0,
        replication_execution_authorized=False,
    )


def generation_reference_shape(value):
    require(
        type(value) is dict
        and set(value)
        == {
            "summary_path",
            "summary_sha256",
            "summary_digest",
            "output_path",
            "commit_digest",
            "source_digest",
        },
        "complete connector qualification reference required",
    )
    for name in ("summary_sha256", "summary_digest", "commit_digest", "source_digest"):
        core.require_sha256(value[name], name)
    for name in ("summary_path", "output_path"):
        require(
            type(value[name]) is str and Path(value[name]).is_absolute(),
            "qualification paths must be absolute",
        )


def verify_generation_reference(reference, admission=None):
    generation_reference_shape(reference)
    connector = k.load("replication_generation_qualifier", EXECUTION)
    fresh, env, check = connector.qualified_public(reference["summary_path"])
    require(
        canonical(fresh) == canonical(reference), "generation qualification differs"
    )
    if admission is not None:
        require(
            canonical(env["admission_proof"]) == canonical(admission),
            "generation qualification admission context differs",
        )
    check()
    return fresh, check


def seal_cohort(qualification_path, expected_digest):
    output = _location(COHORT_PATH)
    require(
        not os.path.lexists(output), "fixed cohort slot occupied; no retry or adoption"
    )
    core.require_sha256(expected_digest, "explicit generation qualification digest")
    snapshot = snapshot_file(Path(qualification_path).absolute())
    saved = core.parse_canonical(snapshot.raw)
    core.require_digest(saved)
    require(
        saved["deterministic_digest"] == expected_digest,
        "explicit generation qualification digest differs",
    )
    # Only an actually replayed NEW connector PUBLIC result admits generation.
    # The previous PUBLIC path and admission-only preflight are insufficient.
    connector = k.load("replication_sealing_qualifier", EXECUTION)
    pipeline, env, check_pipeline = connector.qualified_public(snapshot.path)
    require(
        pipeline["summary_digest"] == expected_digest,
        "qualified pipeline digest differs",
    )
    snapshot.revalidate()
    admission = env["admission_proof"]
    candidate_contract = contract.build_contract()

    def check():
        snapshot.revalidate()
        check_pipeline()
        revalidate_context(admission)

    def build():
        return _seal(
            _cohort(candidate_contract, admission["authorities"]),
            candidate_contract,
            admission,
            pipeline,
        )

    return _publish_cohort(output, admission, build, check, pipeline)


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--seal-cohort", action="store_true")
    mode.add_argument("--verify-seal", type=Path)
    mode.add_argument(
        "--candidate",
        type=Path,
        help="verified seal directory; candidate to stdout only",
    )
    parser.add_argument("--qualification", type=Path)
    parser.add_argument("--expected-digest")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    completed = False
    try:
        supplied = {
            name
            for name in (
                "qualification",
                "expected_digest",
                "output",
            )
            if getattr(args, name) is not None
        }
        expected = (
            {"qualification", "expected_digest"}
            if args.seal_cohort
            else {"output"}
            if args.candidate
            else set()
        )
        require(supplied == expected, "mode arguments differ; no ignored overrides")
        if args.self_test:
            result = dict(
                status="ADMISSION_DOMAIN_NEGATIVES_PASS_NO_GENERATION",
                **negative_checks(),
            )
        elif args.seal_cohort:
            result = seal_cohort(args.qualification, args.expected_digest)
        else:
            sealed = load_seal(args.candidate or args.verify_seal)
            result = (
                candidate(sealed, args.output)
                if args.candidate
                else dict(
                    status="COHORT_VERIFIED_NOT_AUTHORIZED",
                    seal_digest=sealed.manifest["deterministic_digest"],
                    replication_execution_authorized=False,
                )
            )
        completed = True
        sys.stdout.buffer.write(canonical(result))
        sys.stdout.buffer.flush()
        return 0
    except BaseException as error:
        # A failed stdout delivery cannot undo a completed one-shot seal. Keep
        # physical/uncertain publication state separate from invalid admission.
        status = (
            "RESULT_DELIVERY_UNCERTAIN"
            if completed
            else "PUBLICATION_UNCERTAIN"
            if isinstance(error, storage.PublicationUncertain)
            else "INVALID_ADMISSION"
        )
        result = dict(
            status=status,
            reason=str(error),
            error_type=type(error).__name__,
            cohort_generation_consumed=(not args.self_test) if completed else None,
            replication_execution_authorized=False,
            scientific_decision=None,
        )
        print(canonical(result).decode(), end="", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
