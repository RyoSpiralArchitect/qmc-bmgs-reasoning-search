#!/usr/bin/env python3
"""Compile outcome-blind v7 contracts and identity-only schedules, never run search.

PUBLIC task definitions are a fixed single-source software fixture. They are
not generated replication tasks, a sealed cohort, qualification or authority.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
from itertools import product
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = "scripts/feedback_budget_replication_contract.py"
OLD_SCRIPT = "scripts/feedback_budget_development_contract.py"
CHECKER = "scripts/check_feedback_budget_confirmation_design.py"
HELPER_PINS = {
    OLD_SCRIPT: "733afc655937eada7f643d226fe472e76f894a1ec3c551d436343916850ce986",
    "scripts/qualify_feedback_budget.py": "af7cbc1a2b4a68012356de567d3866f1a359dca333908d18bb39f7fec3cc4ec0",
    CHECKER: "ae8fd2710dbd394dc45465a5ff81fb1a95ba6822fc7146cd050c144009b85ded",
}


def _load(name, relative):
    # Check helper file bytes before loading; production source/runtime
    # attestation remains a separate, explicitly unmet gate.
    for path, expected in HELPER_PINS.items():
        value = ROOT / path
        if (
            value.is_symlink()
            or hashlib.sha256(value.read_bytes()).hexdigest() != expected
        ):
            raise ValueError("fixed helper bytes changed: " + path)
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    if spec is None or spec.loader is None:
        raise ValueError("fixed helper unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


old = _load("replication_historical_contract", OLD_SCRIPT)
d = _load("replication_frozen_design", CHECKER)
q, core = old.q, old.core
canonical, digest, sha = old.canonical, old.digest, old.q.sha
DOMAIN = "qmc-bmgs-countdown-thompson-feedback-budget-confirmation/v1"
EXPERIMENT_ID = "feedback_budget_confirmation_64_seed_26091301/v1"
PUBLIC_DOMAIN = DOMAIN + "/public-full-shape"
PUBLIC_MODE = "nondiagnostic_replication_full_shape_fixture"
PUBLIC_ID = "feedback_budget_replication_public_1024/v1"
PUBLIC = "docs/fixtures/countdown_feedback_budget_v7_public.json"
PUBLIC_SHA256 = "38082634240650f3fbaf77875585419003fecfd310eaed3548346fa616782495"
V6 = "docs/preregistrations/countdown_thompson_feedback_budget_v6/preregistration.json"
V6_STARTED = "docs/preregistrations/countdown_thompson_feedback_budget_v6/STARTED.json"
V6_SEALED = "docs/preregistrations/countdown_thompson_feedback_budget_v6/SEALED.json"
V6_CANDIDATE = "docs/preregistrations/countdown_thompson_feedback_budget_v6_execution_authorization_candidate.json"
V6_SUMMARY = (
    "docs/results/countdown_feedback_budget_v6_development_20260910/summary.json"
)
V6_COMMIT = "docs/results/countdown_feedback_budget_v6_development_20260910/COMMIT.json"
ADDITIONAL_PINS = {
    **d.PINNED_HISTORY,
    d.DESIGN: d.DESIGN_SHA256,
    V6_STARTED: "c1e81461384861a8cb9bec08bc0055a597b0772c7222860fabfa41cc1c347535",
    V6_SEALED: "7dce1c6cbabdfb5f75653a33ed2233a0c4278b7463d08fe74902a77900605c53",
    V6_CANDIDATE: "c82c76681aa5cd1c019fd4a745fb74513e759029c65eb1d6816d5d3e319059ef",
}
IDENTITY_FIELDS = {"task_slot", "task_fingerprint", "source_multiset_fingerprint"}
ARMS = ((256, 0), (256, 16), (512, 0), (512, 16))
COHORTS = (
    *old.COHORTS,
    ("feedback_budget_development_12", 12, 12),
    ("replication_public_fixtures", 65, 1),
)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def copy(value):
    return core.parse_canonical(canonical({"value": value}))["value"]


def not_authority():
    return dict(
        replication_tasks_generated=0,
        cohort_generated=False,
        cohort_sealed=False,
        cohort_generation_authorized=False,
        replication_execution_authorized=False,
        locked_128_evaluation_authorized=False,
        prior_authorization_reusable=False,
        source_runtime_qualified=False,
        production_runner_qualified=False,
        production_analyzer_qualified=False,
        production_publication_qualified=False,
        production_admission_qualified=False,
        search_executions=0,
        provider_calls=0,
    )


def public_manifest():
    """Define fixed PUBLIC arithmetic inputs only; never generate/solve a cohort."""
    tasks = [
        q.CountdownTask((1, 2, 3, 4, 5, 6), target).to_dict() for target in range(1, 65)
    ]
    anchor = q.TASK.to_dict()
    all_tasks = [anchor, *tasks]
    return core.with_digest(
        dict(
            schema_version=DOMAIN + "/public-fixture-identities",
            qualification_task=anchor,
            qualification_schedule=q.schedule(),
            unchanged_anchor_qualification_digest=core.FROZEN_AUTHORITY[
                "anchor_qualification_digest"
            ],
            full_shape_fixture_id=PUBLIC_ID,
            full_shape_execution_mode=PUBLIC_MODE,
            full_shape_tasks=tasks,
            full_shape_task_count=64,
            full_shape_source_count=1,
            full_shape_planned_cell_count=1024,
            full_shape_budget_prefix_count=512,
            full_shape_four_arm_block_count=256,
            full_shape_schedule_order="task_then_budget_then_scale_then_seed",
            budgets=list(d.BUDGETS),
            scales=list(d.SCALES),
            exploration_seeds=list(d.SEEDS),
            exclude_task_fingerprints=sorted(
                {t["task_fingerprint"] for t in all_tasks}
            ),
            exclude_source_multiset_fingerprints=sorted(
                {t["source_multiset_fingerprint"] for t in all_tasks}
            ),
            fixture_tasks_are_independent_sources=False,
            fixture_solvability_assessed=False,
            fixture_is_replication_evidence=False,
            fixture_definition_count=65,
            **not_authority(),
        )
    )


def pinned_files():
    return {**old.PINNED_FILES, **ADDITIONAL_PINS, **HELPER_PINS, PUBLIC: PUBLIC_SHA256}


def _context(root):
    values, snapshots = {}, []
    for relative, expected in pinned_files().items():
        snapshot = core.FileSnapshot.capture(root / relative)
        require(sha(snapshot.raw) == expected, "fixed input changed: " + relative)
        if relative.endswith(".json"):
            values[relative] = core.parse_canonical(snapshot.raw)
            core.require_digest(values[relative])
        snapshots.append(snapshot)
    require(
        canonical(values[PUBLIC]) == canonical(public_manifest()),
        "PUBLIC fixture identity recipe differs",
    )
    base = old.build_contract(root)
    require(
        (d.TASK_COUNT, d.GENERATION_SEED, d.MAX_ATTEMPTS) == (64, 26091301, 10000),
        "fixed replication generation recipe differs",
    )
    require(
        (d.BUDGETS, d.SCALES, d.SEEDS) == (q.BUDGETS, q.SCALES, q.SEEDS),
        "qualified factors differ from the v7 design",
    )
    require(
        d.EXPERIMENT_ID == EXPERIMENT_ID and d.PRODUCTION_DOMAIN == DOMAIN,
        "replication design domain differs",
    )
    d.self_test()
    seal, started, closed = values[V6], values[V6_STARTED], values[V6_SEALED]
    require(
        canonical(seal["contract"]) == canonical(base), "v6 sealed contract differs"
    )
    require(
        canonical(started["admission_context"]) == canonical(seal["admission_context"]),
        "v6 STARTED context differs from its seal",
    )
    expected_closed = core.with_digest(
        dict(
            schema_version=old.DOMAIN + "/cohort-sealed",
            status="COHORT_SEALED_NOT_AUTHORIZED",
            started_sha256=ADDITIONAL_PINS[V6_STARTED],
            seal_sha256=ADDITIONAL_PINS[V6],
            seal_byte_count=len(canonical(seal)),
            seal_digest=seal["deterministic_digest"],
            development_execution_authorized=False,
        )
    )
    require(
        canonical(closed) == canonical(expected_closed),
        "v6 seal transaction linkage differs",
    )
    require(
        seal["experiment_id"] == old.EXPERIMENT_ID
        and seal["task_count"] == 12
        and seal["source_multiset_count"] == 12
        and seal["cell_count"] == 192,
        "v6 cohort shape differs",
    )
    require(
        values[V6_SUMMARY]["execution_commit_digest"]
        == values[V6_COMMIT]["deterministic_digest"],
        "v6 summary/COMMIT linkage differs",
    )
    require(
        values[V6_SUMMARY]["authorization_digest"]
        == values[V6_CANDIDATE]["deterministic_digest"],
        "v6 summary/candidate linkage differs",
    )
    require(
        values[V6_CANDIDATE]["cohort_seal"]["seal_sha256"] == ADDITIONAL_PINS[V6],
        "v6 candidate/seal linkage differs",
    )
    return base, values, snapshots


def _revalidate(snapshots):
    for snapshot in snapshots:
        snapshot.revalidate()


def _exclusions(base, values):
    groups = copy(base["exclusion_identities"]["cohorts"])
    cohort = values[V6]["cohort"]
    tasks = cohort["tasks"]
    require(
        type(tasks) is list and len(tasks) == 12,
        "all v6 development identities required",
    )
    require(digest(tasks) == cohort["task_set_digest"], "v6 task-set digest differs")
    for row in tasks:
        expected = q.CountdownTask(tuple(row["inputs"]), row["target"]).to_dict()
        require(
            canonical(row) == canonical(expected),
            "v6 task identity reconstruction differs",
        )
    groups.extend(
        [
            dict(
                label="feedback_budget_development_12",
                task_fingerprints=sorted(t["task_fingerprint"] for t in tasks),
                source_multiset_fingerprints=sorted(
                    t["source_multiset_fingerprint"] for t in tasks
                ),
            ),
            dict(
                label="replication_public_fixtures",
                task_fingerprints=values[PUBLIC]["exclude_task_fingerprints"],
                source_multiset_fingerprints=values[PUBLIC][
                    "exclude_source_multiset_fingerprints"
                ],
            ),
        ]
    )
    seen_tasks, seen_sources = set(), set()
    overlaps = {}
    require(len(groups) == len(COHORTS), "all eight exclusion groups required")
    for row, (label, task_count, source_count) in zip(groups, COHORTS):
        require(row["label"] == label, "exclusion group order differs")
        counts = {}
        for field, expected_count, seen in (
            ("task_fingerprints", task_count, seen_tasks),
            ("source_multiset_fingerprints", source_count, seen_sources),
        ):
            ids = row[field]
            require(type(ids) is list, "fingerprint list required")
            for value in ids:
                core.require_sha256(value, field)
            require(
                ids == sorted(set(ids)) and len(ids) == expected_count,
                "exclusion group identity count/order differs",
            )
            common = seen.intersection(ids)
            if label != "replication_public_fixtures":
                require(not common, "historical/development exclusion groups overlap")
            else:
                old_public = base["exclusion_identities"]["cohorts"][-1][field]
                require(
                    common == set(old_public),
                    "PUBLIC overlap must be exactly the old fixture identities",
                )
            counts[field] = len(common)
            seen.update(ids)
        overlaps[label] = counts
    require(
        (len(seen_tasks), len(seen_sources)) == (243, 179),
        "fixed exclusion union differs",
    )
    return core.with_digest(
        dict(
            schema_version=DOMAIN + "/exclusion-identities",
            cohorts=groups,
            task_fingerprints=sorted(seen_tasks),
            source_multiset_fingerprints=sorted(seen_sources),
            task_fingerprint_count=243,
            source_multiset_fingerprint_count=179,
            overlap_with_earlier_groups=overlaps,
            role="fixed_historical_development_and_PUBLIC_identity_exclusions_only",
            locked_128_evaluation_authorized=False,
            fixture_variant_closure_required_before_generation=True,
        )
    )


def _contract(base, values):
    return core.with_digest(
        dict(
            schema_version=DOMAIN + "/contract-candidate",
            experiment_id=EXPERIMENT_ID,
            status="REPLICATION_CONTRACT_CANDIDATE_NO_COHORT_NO_AUTHORIZATION",
            input_file_sha256=pinned_files(),
            frozen_design=dict(path=d.DESIGN, sha256=d.DESIGN_SHA256),
            historical_contract_digest=base["deterministic_digest"],
            historical_v6_seal_digest=values[V6]["deterministic_digest"],
            historical_v6_summary_digest=values[V6_SUMMARY]["deterministic_digest"],
            historical_v6_commit_digest=values[V6_COMMIT]["deterministic_digest"],
            historical_evidence_is_replication_evidence=False,
            exclusion_identities=_exclusions(base, values),
            generation_recipe={
                **base["generation_recipe"],
                "count": 64,
                "seed": 26091301,
            },
            task_count=64,
            exploration_seeds=list(d.SEEDS),
            budgets=base["budgets"],
            methods=base["methods"],
            proposal=base["proposal"],
            runtime_requirement=base["runtime_requirement"],
            arm_order=[dict(budget=b, scale=s) for b, s in ARMS],
            schedule_order="task_then_budget_then_scale_then_seed",
            planned_cell_count=1024,
            planned_budget_prefix_count=512,
            planned_four_cell_block_count=256,
            screen=dict(
                effect_floor=dict(numerator=1, denominator=24),
                minimum_effect_numerator=11,
                effect_denominator=256,
                rescued_task_fraction=dict(numerator=1, denominator=6),
                minimum_rescued_tasks=11,
                task_denominator=64,
                minimum_low_budget_uplift_numerator=0,
                maximum_high_budget_lost_exact_successes=0,
                leave_one_task_out_block_count=252,
                strictly_positive_leave_one_task_out_estimands=[
                    "high_budget_uplift",
                    "interaction",
                ],
                all_high_budget_rescues_require_prior_differing_applied_backup=True,
                pass_label="SOURCE_DISJOINT_REPLICATION_SCREEN_PASS",
                valid_failure_label="STOP_REPAIR_REPLICATION_SCREEN_NOT_MET",
                integrity_failure_label="INVALID_ANALYSIS",
                interpretation="finite_cohort_replication_engineering_screen_not_inference",
                production_screen_implemented=False,
            ),
            planned_production_schemas={
                role: DOMAIN + "/" + role
                for role in (
                    "cohort-started",
                    "cohort-sealed",
                    "preregistration",
                    "cohort",
                    "cell-key",
                    "record",
                    "run-binding",
                    "authorization-candidate",
                    "consumption",
                    "publication",
                    "analysis",
                )
            },
            public_fixture_manifest_digest=values[PUBLIC]["deterministic_digest"],
            qualification_plan=dict(
                component_new_profile_cells=16,
                component_legacy_guard_cells=8,
                unchanged_anchor_cells=8,
                component_cells_total=32,
                full_shape_fixture_id=PUBLIC_ID,
                full_shape_cells=1024,
                full_shape_budget_prefix_pairs=512,
                full_shape_four_arm_blocks=256,
                every_trace_requires_two_stage_replay=True,
                separate_saved_summary_verification_required=True,
                outcome_redacted_mechanism_before_terminal_reduction=True,
                sole_primary_budget_and_completion_checks_required=True,
                production_discrimination_and_duplicate_source_negative_tests_required=True,
                strict_identity_budget_prefix_and_canonical_json_negative_tests_required=True,
                one_shot_study_claim_and_publication_failure_tests_required=True,
                all_fixture_variants_must_precede_new_cohort_generation=True,
                historical_qualification_transfers_to_new_pipeline=False,
                actual_qualification_performed=False,
            ),
            missing_gates=[
                "review_exact_contract_and_PUBLIC_identities",
                "source_runtime_qualified_new_domain_runner_analyzer_publication_admission",
                "independent_1024_cell_PUBLIC_execution_analysis_and_saved_summary_verification",
                "complete_actual_fixture_variant_exclusion_closure",
                "separate_cohort_generation_permission_and_verified_64_task_seal",
                "exact_non_authorizing_candidate_review_and_explicit_one_run_permission",
            ],
            **not_authority(),
        )
    )


def build_contract(root=ROOT):
    base, values, snapshots = _context(root)
    result = _contract(base, values)
    _revalidate(snapshots)
    return result


def _identities(identities, contract):
    require(
        type(identities) is list and len(identities) == 64, "64 identity rows required"
    )
    seen_tasks, seen_sources = set(), set()
    excluded = contract["exclusion_identities"]
    for slot, row in enumerate(identities):
        require(
            type(row) is dict and set(row) == IDENTITY_FIELDS, "identity fields differ"
        )
        require(
            type(row["task_slot"]) is int and row["task_slot"] == slot,
            "identity order differs",
        )
        for field, seen, forbidden in (
            ("task_fingerprint", seen_tasks, excluded["task_fingerprints"]),
            (
                "source_multiset_fingerprint",
                seen_sources,
                excluded["source_multiset_fingerprints"],
            ),
        ):
            value = core.require_sha256(row[field], field)
            require(value not in seen, "duplicate candidate identity")
            require(value not in forbidden, "candidate overlaps excluded identity")
            seen.add(value)
    return copy(identities)


def _layout(contract, identities, public):
    budgets = {row["budget"]: row["spec_digest"] for row in contract["budgets"]}
    methods = {row["scale"]: row["spec_digest"] for row in contract["methods"]}
    identity_digest = digest(identities)
    cells, indexed = [], {}
    for t, b, s, r in product(range(64), d.BUDGETS, d.SCALES, d.SEEDS):
        key = dict(
            schema_version=PUBLIC_DOMAIN + "/cell-key"
            if public
            else DOMAIN + "/candidate-cell-key",
            contract_digest=contract["deterministic_digest"],
            candidate_identity_digest=identity_digest,
            **identities[t],
            budget=b,
            scale=s,
            seed=r,
            budget_spec_digest=budgets[b],
            method_spec_digest=methods[s],
            proposal_spec_digest=contract["proposal"]["spec_digest"],
        )
        if public:
            key.update(
                fixture_id=PUBLIC_ID,
                execution_mode=PUBLIC_MODE,
                public_fixture_manifest_digest=contract[
                    "public_fixture_manifest_digest"
                ],
            )
        else:
            key["experiment_id"] = EXPERIMENT_ID
        cell_id = digest(key)
        cells.append(dict(cell_index=len(cells), cell_id=cell_id, cell_key=key))
        indexed[t, b, s, r] = cell_id
    return dict(
        candidate_identities=identities,
        candidate_identity_digest=identity_digest,
        cells=cells,
        cell_count=1024,
        schedule_digest=digest(cells),
        budget_prefix_pairs=[
            dict(
                task_slot=t,
                scale=s,
                seed=r,
                low_cell_id=indexed[t, 256, s, r],
                high_cell_id=indexed[t, 512, s, r],
            )
            for t, s, r in product(range(64), d.SCALES, d.SEEDS)
        ],
        four_cell_blocks=[
            dict(
                task_slot=t, seed=r, arm_cell_ids=[indexed[t, b, s, r] for b, s in ARMS]
            )
            for t, r in product(range(64), d.SEEDS)
        ],
    )


def _schedule(contract, identities):
    identities = _identities(identities, contract)
    return core.with_digest(
        dict(
            schema_version=DOMAIN + "/schedule-candidate",
            experiment_id=EXPERIMENT_ID,
            status="IDENTITY_ONLY_REPLICATION_SCHEDULE_CANDIDATE_NOT_EXECUTABLE",
            contract_digest=contract["deterministic_digest"],
            **_layout(contract, identities, False),
            solvability_verified=False,
            generation_order_verified=False,
            production_cell_keys_materialized=False,
            **not_authority(),
        )
    )


def build_schedule_candidate(identities, root=ROOT):
    base, values, snapshots = _context(root)
    result = _schedule(_contract(base, values), identities)
    _revalidate(snapshots)
    return result


def validate_schedule_candidate(raw, root=ROOT):
    value = core.parse_canonical(raw)
    core.require_digest(value)
    require("candidate_identities" in value, "candidate identities missing")
    expected = build_schedule_candidate(value["candidate_identities"], root)
    require(canonical(expected) == raw, "candidate differs from exact regeneration")
    return expected


def build_public_schedule(root=ROOT):
    base, values, snapshots = _context(root)
    contract = _contract(base, values)
    tasks = values[PUBLIC]["full_shape_tasks"]
    identities = [
        dict(
            task_slot=i,
            task_fingerprint=t["task_fingerprint"],
            source_multiset_fingerprint=t["source_multiset_fingerprint"],
        )
        for i, t in enumerate(tasks)
    ]
    result = core.with_digest(
        dict(
            schema_version=PUBLIC_DOMAIN + "/manifest",
            fixture_id=PUBLIC_ID,
            execution_mode=PUBLIC_MODE,
            status="PUBLIC_FIXTURE_SCHEDULE_NOT_QUALIFICATION",
            contract_digest=contract["deterministic_digest"],
            public_fixture_manifest_digest=values[PUBLIC]["deterministic_digest"],
            tasks=tasks,
            task_count=64,
            source_multiset_count=1,
            **_layout(contract, identities, True),
            fixture_is_replication_evidence=False,
            actual_qualification_performed=False,
            **not_authority(),
        )
    )
    _revalidate(snapshots)
    return result


def validate_public_schedule(raw, root=ROOT):
    value = core.parse_canonical(raw)
    core.require_digest(value)
    expected = build_public_schedule(root)
    require(
        canonical(expected) == raw, "PUBLIC schedule differs from exact regeneration"
    )
    return expected


def synthetic_identities():
    return [
        dict(
            task_slot=i,
            task_fingerprint=digest(["synthetic-v7-task", i]),
            source_multiset_fingerprint=digest(["synthetic-v7-source", i]),
        )
        for i in range(64)
    ]


def self_test(root=ROOT):
    contract = build_contract(root)
    candidate = build_schedule_candidate(synthetic_identities(), root)
    public = build_public_schedule(root)
    validate_schedule_candidate(canonical(candidate), root)
    validate_public_schedule(canonical(public), root)
    for value in (candidate, public):
        require(
            len(value["cells"])
            == len({row["cell_id"] for row in value["cells"]})
            == 1024,
            "complete synthetic/PUBLIC cell shape differs",
        )
        require(
            len(value["budget_prefix_pairs"]) == 512
            and len(value["four_cell_blocks"]) == 256,
            "complete pair/block shape differs",
        )
    require(
        not {c["cell_id"] for c in candidate["cells"]}.intersection(
            c["cell_id"] for c in public["cells"]
        ),
        "PUBLIC and identity-only domains collided",
    )
    return core.with_digest(
        dict(
            schema_version=DOMAIN + "/contract-self-test",
            status="REPLICATION_CONTRACT_SYNTHETIC_PASS_NOT_AUTHORIZED",
            contract_digest=contract["deterministic_digest"],
            synthetic_candidate_digest=candidate["deterministic_digest"],
            public_schedule_digest=public["deterministic_digest"],
            synthetic_cell_count=1024,
            public_planned_cell_count=1024,
            synthetic_budget_prefix_pairs=512,
            synthetic_four_arm_blocks=256,
            excluded_full_task_count=243,
            excluded_source_multiset_count=179,
            public_fixture_definition_count=65,
            public_fixture_sources=1,
            actual_qualification_performed=False,
            **not_authority(),
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--manifest", action="store_true")
    modes.add_argument("--public-identities", action="store_true")
    modes.add_argument("--public-schedule", action="store_true")
    modes.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.manifest:
            result = build_contract()
        elif args.public_identities:
            result = public_manifest()
        elif args.public_schedule:
            result = build_public_schedule()
        else:
            result = self_test()
        sys.stdout.buffer.write(canonical(result))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        sys.stdout.buffer.write(
            canonical(dict(status="INVALID_REPLICATION_CONTRACT", reason=str(error)))
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
