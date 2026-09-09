#!/usr/bin/env python3
"""Outcome-blind cohort sealing and review-only authorization candidates.

Qualification re-verifies the saved PUBLIC experiment and historical identity
authorities. Sealing is a separate, digest-confirmed operation. No execution
authorization, search adapter, consumption registry or development run is exposed.
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
SCRIPT = "scripts/feedback_budget_development_admission.py"
PUBLIC_RUNNER = "scripts/run_feedback_budget_development_fixture.py"
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
DOMAIN = k.DOMAIN
MODE = "sealed_development_cohort"
BASE = "143b279c61e4962a9b0afaacbdf3c37eff6e34d0"
# Keep the generation transaction outside the tracked source tree: STARTED
# must not itself dirty the source-qualified checkout. Promotion is separate.
COHORT_PATH = ROOT / "artifacts/work/feedback-budget-development-cohort-v6"
PUBLIC_SUMMARY = "docs/qualifications/countdown_feedback_budget_v6_development_path_20260910.summary.json"
PUBLIC_COMMIT = "docs/qualifications/countdown_feedback_budget_v6_development_path_20260910.commit.json"
PUBLIC_PINS = {
    PUBLIC_SUMMARY: "9f1e216d2b24949e645e82e17f7244e56c8cd71d43bf42e2e69fbc66657afac2",
    PUBLIC_COMMIT: "e37125ed51a7d416e4160dc0a6aad256a5fe1a248a9137c7a23fb029a0bc9117",
}
NAMES = frozenset(("STARTED.json", "preregistration.json", "SEALED.json"))


def source_receipt(revision=None):
    source = public.attest(revision)
    approved = source["execution_revision"]
    core.require_ancestor(ROOT, BASE, approved)
    public._origin(public, PUBLIC_RUNNER)
    require(
        Path(__file__).resolve() == ROOT / SCRIPT, "admission source origin differs"
    )
    files, snapshots = {}, []
    for relative in (SCRIPT, *PUBLIC_PINS):
        snapshot = core.FileSnapshot.capture(ROOT / relative)
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
    """Regenerate the OLD authority chain, never the new 26090401 recipe."""
    candidate = contract.build_contract()
    snapshot = core.FileSnapshot.capture(ROOT / contract.V5)
    require(
        q.sha(snapshot.raw) == contract.PINNED_FILES[contract.V5], "v5 bytes differ"
    )
    verified = historical.verify_countdown_thompson_dense_scale_bundle(
        (ROOT / contract.V5).parent,
        repository_root=ROOT,
    )
    require(
        canonical(verified.payload) == snapshot.raw, "verified historical bytes differ"
    )
    # The old verifier recursively closes its complete diagnostic/canary/locked
    # identity authorities and generator acceptance order. No outcome is read.
    values, snapshots = contract._read_inputs(ROOT)
    values[contract.V5] = verified.payload
    exclusions = contract._exclusions(values)
    require(
        canonical(exclusions) == canonical(candidate["exclusion_identities"]),
        "verified exclusion union differs",
    )
    snapshot.revalidate()
    for item in snapshots:
        item.revalidate()
    return core.with_digest(
        dict(
            schema_version=DOMAIN + "/verified-identity-authorities",
            contract_digest=candidate["deterministic_digest"],
            v5_seal_digest=verified.seal_digest,
            v5_file_sha256=q.sha(snapshot.raw),
            diagnostic_authority=verified.payload["authority"],
            exclusion_identities=exclusions,
            role="verified_identity_exclusions_only_not_execution_authority",
            new_development_tasks_generated=0,
            locked_128_evaluation_authorized=False,
        )
    )


def public_evidence():
    snapshots = {p: core.FileSnapshot.capture(ROOT / p) for p in PUBLIC_PINS}
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
        and summary["development_execution_authorized"] is False,
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
            role="fixed_public_pipeline_evidence_not_development_evidence",
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
            development_execution_authorized=False,
        )
    )


def revalidate_context(value):
    require(
        canonical(context(value["source"]["admission_revision"])) == canonical(value),
        "admission context changed",
    )


def _tasks(rows, candidate):
    require(
        type(rows) is list and len(rows) == 12,
        "exactly 12 development task rows required",
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
            "development target range differs",
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
    # Both kinds of uniqueness and all six exclusions, before any regeneration.
    contract._schedule(candidate, identities)
    return identities


def _cohort(candidate, authorities):
    exclusions = authorities["exclusion_identities"]
    require(
        canonical(exclusions) == canonical(candidate["exclusion_identities"]),
        "cohort exclusion authority differs",
    )
    suite = historical.generate_solvable_task_suite(
        12,
        26090401,
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
        type(attempts) is int and 12 <= attempts <= 10000, "generation attempts differ"
    )
    require(
        type(log) is list and len(log) == attempts - 12,
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
        accepted_count=12,
        accepted_task_pool_digest=digest(rows),
        attempt_count=attempts,
        conditioned_on_exhaustive_solvability=True,
        excluded_identity_record_digest=exclusions["deterministic_digest"],
        excluded_source_multiset_fingerprint_count=167,
        excluded_source_multiset_fingerprint_digest=digest(
            exclusions["source_multiset_fingerprints"]
        ),
        excluded_task_fingerprint_count=179,
        excluded_task_fingerprint_digest=digest(exclusions["task_fingerprints"]),
        generator_id=candidate["generation_recipe"]["generator"],
        input_range_inclusive=[1, 10],
        max_attempts=10000,
        rejection_counts={reason: counts[reason] for reason in reasons},
        rejection_log=log,
        requested_count=12,
        seed=26090401,
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


def _seal(cohort, candidate, admission):
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
                for t in range(12)
                for s in q.SCALES
                for r in q.SEEDS
            ],
            four_cell_blocks=[
                dict(
                    task_slot=t,
                    seed=r,
                    arm_cell_ids=[indexed[t, b, s, r] for b, s in k.ARMS],
                )
                for t in range(12)
                for r in q.SEEDS
            ],
            cell_count=192,
            task_count=12,
            source_multiset_count=12,
            status="SEALED_COHORT_NOT_EXECUTION_AUTHORITY",
            development_execution_authorized=False,
            locked_128_evaluation_authorized=False,
        )
    )


def validate_seal_bytes(raw):
    value = core.parse_canonical(raw)
    core.require_digest(value)
    require(
        value.get("schema_version") == DOMAIN + "/preregistration"
        and value.get("execution_mode") == MODE,
        "sealed development domain required",
    )
    require(
        value.get("experiment_id") == contract.EXPERIMENT_ID,
        "development experiment differs",
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
        canonical(_seal(cohort, candidate, admission)) == raw,
        "closed preregistration differs",
    )
    # Authoritative source/runtime/old seals close BEFORE invoking the new recipe.
    revalidate_context(admission)
    expected = _seal(_cohort(candidate, admission["authorities"]), candidate, admission)
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
        "only the fixed v6 cohort location is allowed",
    )
    return path


def _started(admission, nonce):
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
            status="COHORT_GENERATION_STARTED_NOT_AUTHORIZED",
            development_execution_authorized=False,
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
            development_execution_authorized=False,
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
            canonical(_started(seal["admission_context"], started["owner_nonce"]))
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


def _publish_cohort(path, admission, build, check):
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
        started = _started(admission, secrets.token_hex(32))
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
                        development_execution_authorized=False,
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
                schema_version=DOMAIN + "/authorization-candidate",
                scope="REVIEW_ONLY_NOT_EXECUTABLE",
                experiment_id=contract.EXPERIMENT_ID,
                status="PENDING_REVIEW_AND_EXPLICIT_PERMISSION",
                seal_digest=value["deterministic_digest"],
                seal_path=str(sealed._path),
                seal_sha256=q.sha(canonical(value)),
                contract_digest=value["contract"]["deterministic_digest"],
                cohort_digest=value["cohort"]["deterministic_digest"],
                schedule_digest=value["schedule_digest"],
                expected_cell_count=192,
                admission_context=value["admission_context"],
                output_path=str(output),
                output_parent=binding,
                requires_exact_digest_confirmation=True,
                execution_adapter_qualified=False,
                authorization_consumption_implemented=False,
                development_execution_authorized=False,
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
    """Read-only domain negatives; no generator, solver or development search."""
    values = {
        "identity_only_contract": contract.build_contract(),
        "identity_only_schedule": contract.build_schedule_candidate(
            contract.synthetic_identities()
        ),
        "public_execution_fixture": k.fixture_manifest(),
        "old_v5_preregistration": core.parse_canonical(
            core.FileSnapshot.capture(ROOT / contract.V5).raw
        ),
        "public_analysis": core.parse_canonical(
            core.FileSnapshot.capture(ROOT / PUBLIC_SUMMARY).raw
        ),
    }
    for name in (
        "countdown_track_a_canary_v2",
        "countdown_thompson_diagnostic_v1",
        "countdown_thompson_dense_scale_v5",
    ):
        values["old_authorization_" + name] = core.parse_canonical(
            core.FileSnapshot.capture(
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
            raise ValueError(f"non-development input admitted: {label}")
    return dict(
        rejected_as_development_seals=rejected,
        new_development_tasks_generated=0,
        development_search_calls=0,
        development_execution_authorized=False,
    )


def qualify(output, summary_path, revision=None):
    publication = public.pub.inspect(public._output(output))
    snapshot = core.FileSnapshot.capture(public._output(summary_path))
    admission = context(revision)
    # Independent raw publication re-verification, NOT merely the tracked JSON.
    summary = public.verify(output, summary_path)
    require(
        summary["deterministic_digest"]
        == admission["public_evidence"]["summary_digest"],
        "independent public evidence differs",
    )
    checks = negative_checks()
    revalidate_context(admission)
    snapshot.revalidate()
    publication.revalidate()
    return core.with_digest(
        dict(
            schema_version=DOMAIN + "/admission-qualification",
            status="PUBLIC_REPLAY_AND_IDENTITY_ADMISSION_PREFLIGHT_PASS",
            admission_context=admission,
            public_run_path=str(public._output(output)),
            public_summary_path=str(public._output(summary_path)),
            independently_verified_public_summary_digest=summary[
                "deterministic_digest"
            ],
            public_cell_count=192,
            public_prefix_pair_count=96,
            negative_checks=checks,
            new_development_tasks_generated=0,
            development_cells_executed=0,
            positive_seal_roundtrip_qualified=False,
            authorization_consumption_implemented=False,
            development_execution_authorized=False,
            scientific_decision=None,
        )
    )


def verify_qualification(path, expected_digest):
    core.require_sha256(expected_digest, "reviewed qualification digest")
    snapshot = core.FileSnapshot.capture(path)
    value = core.parse_canonical(snapshot.raw)
    core.require_digest(value)
    require(
        value["deterministic_digest"] == expected_digest
        and value.get("schema_version") == DOMAIN + "/admission-qualification",
        "reviewed qualification differs",
    )
    expected = qualify(
        value["public_run_path"],
        value["public_summary_path"],
        value["admission_context"]["source"]["admission_revision"],
    )
    require(
        canonical(expected) == snapshot.raw,
        "qualification differs from fresh recomputation",
    )
    snapshot.revalidate()
    return expected


def seal_cohort(qualification_path, expected_digest):
    output = _location(COHORT_PATH)
    require(
        not os.path.lexists(output), "fixed cohort slot occupied; no retry or adoption"
    )
    snapshot = core.FileSnapshot.capture(qualification_path)
    qualification = verify_qualification(qualification_path, expected_digest)
    snapshot.revalidate()
    admission = qualification["admission_context"]
    candidate_contract = contract.build_contract()

    def check():
        snapshot.revalidate()
        revalidate_context(admission)

    def build():
        return _seal(
            _cohort(candidate_contract, admission["authorities"]),
            candidate_contract,
            admission,
        )

    # STARTED is durable before the sole new-generation call. The independent
    # --verify-seal operation subsequently repeats that exact recipe, not a search.
    return _publish_cohort(output, admission, build, check)


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--qualify", action="store_true")
    mode.add_argument("--verify-qualification", type=Path)
    mode.add_argument("--seal-cohort", action="store_true")
    mode.add_argument("--verify-seal", type=Path)
    mode.add_argument(
        "--candidate",
        type=Path,
        help="verified seal directory; candidate to stdout only",
    )
    parser.add_argument("--public-run", type=Path)
    parser.add_argument("--public-summary", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--qualification", type=Path)
    parser.add_argument("--expected-digest")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        supplied = {
            name
            for name in (
                "public_run",
                "public_summary",
                "receipt",
                "qualification",
                "expected_digest",
                "output",
            )
            if getattr(args, name) is not None
        }
        expected = (
            {"public_run", "public_summary", "receipt"}
            if args.qualify
            else {"expected_digest"}
            if args.verify_qualification
            else {"qualification", "expected_digest"}
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
        elif args.qualify:
            path = public._output(args.receipt)
            require(not os.path.lexists(path), "qualification receipt occupied")
            publication = public.pub.inspect(public._output(args.public_run))
            snapshot = core.FileSnapshot.capture(public._output(args.public_summary))
            result = qualify(args.public_run, args.public_summary)

            def check():
                revalidate_context(result["admission_context"])
                snapshot.revalidate()
                publication.revalidate()

            storage.publish_summary(path, result, check)
        elif args.verify_qualification:
            result = verify_qualification(
                args.verify_qualification, args.expected_digest
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
                    development_execution_authorized=False,
                )
            )
        sys.stdout.buffer.write(canonical(result))
        return 0
    except (ValueError, OSError, RuntimeError, KeyError, TypeError) as error:
        sys.stdout.buffer.write(
            canonical(
                dict(
                    status="INVALID_ADMISSION",
                    reason=str(error),
                    error_type=type(error).__name__,
                    development_execution_authorized=False,
                    scientific_decision=None,
                )
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
