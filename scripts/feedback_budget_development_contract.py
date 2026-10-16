#!/usr/bin/env python3
"""Build the outcome-blind v6 contract and identity-only schedule candidates.

No cohort generator, solver, search runner, publisher, or authorization loader is
exposed. Synthetic identity hashes exercise the future schedule without creating
any new Countdown task or establishing solvability, provenance, or run authority.
"""

from __future__ import annotations

import argparse
import importlib.util
from itertools import product
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "feedback_budget_contract_public_helpers",
    ROOT / "scripts/qualify_feedback_budget.py",
)
assert SPEC is not None and SPEC.loader is not None
q = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(q)
core, canonical, digest = q.core, q.canonical, q.sha256_json
DOMAIN = "qmc-bmgs-countdown-thompson-feedback-budget/v1"
EXPERIMENT_ID = "feedback_budget_development_12_seed_26090401/v1"
V5 = "docs/preregistrations/countdown_thompson_dense_scale_v5/preregistration.json"
PUBLIC = "docs/fixtures/countdown_feedback_budget_v6_public.json"
QUALIFICATION = (
    "docs/qualifications/countdown_feedback_budget_v6_public_revalidated_20260905.json"
)
COMMIT = (
    "docs/qualifications/countdown_feedback_budget_v6_full_shape_20260905.commit.json"
)
SUMMARY = (
    "docs/qualifications/countdown_feedback_budget_v6_full_shape_20260905.summary.json"
)
PINNED_FILES = {
    q.DESIGN: q.DESIGN_SHA256,
    V5: "bc68216a2f3e4809fd65914cd7a663d9d8f4ff74c3299de5e1ac36a04eecb547",
    PUBLIC: "3b32267f96339416a164fbe3e9046247286c360c08c10105d4971af42fef9a4b",
    QUALIFICATION: "cd53c88191c130d1ae457b9664988939eae4ae8047bd9f37d9afed29f594532c",
    COMMIT: "16ce27faf77cdeb8c96939428ed5eeb5c1a2f55eeb5b0b4bbfb9da513b679110",
    SUMMARY: "311701c63f87d04d956214554c38bcae612d5100225113b30b264450f4299011",
}
COHORTS = (
    ("historical_2", 2, 2),
    ("canary_12", 12, 12),
    ("locked_128", 128, 128),
    ("diagnostic_12", 12, 12),
    ("dense_scale_development_12", 12, 12),
    ("public_feedback_budget_fixtures", 13, 1),
)
ARMS = ((256, 0), (256, 16), (512, 0), (512, 16))
IDENTITY_FIELDS = {"task_slot", "task_fingerprint", "source_multiset_fingerprint"}


class ContractError(ValueError):
    """A fixed input, identity boundary, or candidate schedule is inconsistent."""


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ContractError(reason)


def _read_inputs(root: Path) -> tuple[dict, list]:
    values, snapshots = {}, []
    for relative, expected_hash in PINNED_FILES.items():
        snapshot = core.FileSnapshot.capture(root / relative)
        require(
            q.sha(snapshot.raw) == expected_hash, f"pinned input changed: {relative}"
        )
        if relative != q.DESIGN:
            values[relative] = core.parse_canonical(snapshot.raw)
            core.require_digest(values[relative])
        snapshots.append(snapshot)
    require(
        canonical(values[PUBLIC]) == canonical(q.public_manifest()),
        "public identity reconstruction differs",
    )
    require(
        values[V5]["deterministic_digest"]
        == "49f820692aa4f3551ca5634bdc89efe225fe05d1dc8acb8e814f231f3eea222f",
        "historical v5 seal changed",
    )
    require(
        values[SUMMARY]["execution_commit_digest"]
        == values[COMMIT]["deterministic_digest"],
        "public summary/commit binding differs",
    )
    # The current factories must describe exactly the already-qualified factors,
    # not merely keep the same friendly profile/method labels.
    for row in values[QUALIFICATION]["analysis"]["trace_receipts"]:
        if row["legacy"]:
            continue
        require(
            canonical(row["profile_spec"])
            == canonical(q.profile(row["budget"]).to_dict())
            and canonical(row["method_spec"])
            == canonical(q.method(row["scale"]).to_dict()),
            "qualified component spec changed",
        )
    return values, snapshots


def _exclusions(values: dict) -> dict:
    old = values[V5]["cohort"]
    groups = [
        {
            "label": row["label"],
            "task_fingerprints": row["task_fingerprints"],
            "source_multiset_fingerprints": row["source_multiset_fingerprints"],
        }
        for row in old["exclusion_identity"]["cohorts"]
    ]
    groups.extend(
        [
            dict(
                label="dense_scale_development_12",
                task_fingerprints=sorted(t["task_fingerprint"] for t in old["tasks"]),
                source_multiset_fingerprints=sorted(
                    t["source_multiset_fingerprint"] for t in old["tasks"]
                ),
            ),
            dict(
                label="public_feedback_budget_fixtures",
                task_fingerprints=values[PUBLIC]["exclude_task_fingerprints"],
                source_multiset_fingerprints=values[PUBLIC][
                    "exclude_source_multiset_fingerprints"
                ],
            ),
        ]
    )
    require(len(groups) == len(COHORTS), "exclusion cohort count differs")
    tasks, sources = set(), set()
    for row, (label, task_count, source_count) in zip(groups, COHORTS):
        require(row["label"] == label, "exclusion cohort order differs")
        for field, count, seen in (
            ("task_fingerprints", task_count, tasks),
            ("source_multiset_fingerprints", source_count, sources),
        ):
            fingerprints = row[field]
            require(type(fingerprints) is list, "fingerprint list required")
            for value in fingerprints:
                core.require_sha256(value, field)
            require(
                fingerprints == sorted(set(fingerprints))
                and len(fingerprints) == count,
                "exclusion identity count/order differs",
            )
            require(not seen.intersection(fingerprints), "exclusion groups overlap")
            seen.update(fingerprints)
    require((len(tasks), len(sources)) == (179, 167), "exclusion union differs")
    return core.with_digest(
        dict(
            schema_version=DOMAIN + "/exclusion-identities",
            cohorts=groups,
            task_fingerprints=sorted(tasks),
            source_multiset_fingerprints=sorted(sources),
            task_fingerprint_count=len(tasks),
            source_multiset_fingerprint_count=len(sources),
            role="pinned_historical_and_public_identity_exclusions_only",
            locked_128_evaluation_authorized=False,
        )
    )


def build_contract(root: Path = ROOT) -> dict:
    values, snapshots = _read_inputs(root)
    require(
        (q.BUDGETS, q.SCALES, q.SEEDS)
        == ((256, 512), (0, 16), (8192, 8193, 8194, 8195)),
        "qualified factor schedule changed",
    )
    result = core.with_digest(
        dict(
            schema_version=DOMAIN + "/contract-candidate",
            experiment_id=EXPERIMENT_ID,
            status="CONTRACT_CANDIDATE_NO_COHORT_NO_AUTHORIZATION",
            input_file_sha256=dict(PINNED_FILES),
            frozen_design=dict(path=q.DESIGN, sha256=q.DESIGN_SHA256),
            exclusion_identities=_exclusions(values),
            generation_recipe=dict(
                function="generate_solvable_task_suite",
                generator="sha256-counter-mod/v1",
                count=12,
                seed=26090401,
                max_attempts=10000,
                input_count=6,
                input_min=1,
                input_max=10,
                target_min=100,
                target_max=999,
                acceptance="exhaustive_solvability_and_both_identity_exclusions_only",
                task_order="generator_acceptance_order",
                persist_solution_witnesses=False,
                hardness_selection_allowed=False,
            ),
            task_count=12,
            exploration_seeds=list(q.SEEDS),
            budgets=[
                dict(
                    budget=b,
                    spec=q.profile(b).to_dict(),
                    spec_digest=digest(q.profile(b).to_dict()),
                )
                for b in q.BUDGETS
            ],
            methods=[
                dict(
                    scale=s,
                    spec=q.method(s).to_dict(),
                    spec_digest=digest(q.method(s).to_dict()),
                )
                for s in q.SCALES
            ],
            proposal=dict(
                spec=q.PROPOSAL.to_dict(), spec_digest=digest(q.PROPOSAL.to_dict())
            ),
            planned_production_schemas={
                role: DOMAIN + "/" + role
                for role in (
                    "preregistration",
                    "cohort",
                    "cell-key",
                    "record",
                    "run-binding",
                    "authorization",
                    "publication",
                    "analysis",
                )
            },
            schedule_order="task_then_budget_then_scale_then_seed",
            planned_cell_count=192,
            planned_budget_prefix_count=96,
            planned_four_cell_block_count=48,
            arm_order=[dict(budget=b, scale=s) for b, s in ARMS],
            qualification_references=dict(
                public_32_receipt_digest=values[QUALIFICATION]["deterministic_digest"],
                public_192_summary_digest=values[SUMMARY]["deterministic_digest"],
                production_runner_qualified=False,
                production_analyzer_qualified=False,
                production_publication_qualified=False,
            ),
            runtime_requirement=values[QUALIFICATION]["runtime"],
            prior_stop="STOP_REPAIR_NO_LOCKED_128_RUN",
            prior_authorization_reusable=False,
            cohort_generated=False,
            cohort_sealed=False,
            development_execution_authorized=False,
            locked_128_evaluation_authorized=False,
        )
    )
    for snapshot in snapshots:
        snapshot.revalidate()
    return result


def _schedule(contract: dict, identities: object) -> dict:
    """Pure compilation after input closure; identities are NOT a verified cohort."""
    require(
        type(identities) is list and len(identities) == 12, "12 identity rows required"
    )
    seen_tasks, seen_sources = set(), set()
    excluded = contract["exclusion_identities"]
    for slot, row in enumerate(identities):
        require(
            type(row) is dict and set(row) == IDENTITY_FIELDS, "identity fields differ"
        )
        require(
            type(row["task_slot"]) is int and row["task_slot"] == slot,
            "task order differs",
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
            require(value not in forbidden, "candidate overlaps an excluded identity")
            seen.add(value)
    identity_digest = digest(identities)
    budget_digests = {row["budget"]: row["spec_digest"] for row in contract["budgets"]}
    method_digests = {row["scale"]: row["spec_digest"] for row in contract["methods"]}
    cells, indexed = [], {}
    for slot, budget, scale, seed in product(range(12), q.BUDGETS, q.SCALES, q.SEEDS):
        key = dict(
            schema_version=DOMAIN + "/candidate-cell-key",
            experiment_id=EXPERIMENT_ID,
            contract_digest=contract["deterministic_digest"],
            candidate_identity_digest=identity_digest,
            **identities[slot],
            budget=budget,
            scale=scale,
            seed=seed,
            budget_spec_digest=budget_digests[budget],
            method_spec_digest=method_digests[scale],
            proposal_spec_digest=contract["proposal"]["spec_digest"],
        )
        cell_id = digest(key)
        cells.append(dict(cell_index=len(cells), cell_id=cell_id, cell_key=key))
        indexed[slot, budget, scale, seed] = cell_id
    return core.with_digest(
        dict(
            schema_version=DOMAIN + "/schedule-candidate",
            experiment_id=EXPERIMENT_ID,
            status="IDENTITY_ONLY_SCHEDULE_CANDIDATE_NOT_EXECUTABLE",
            contract_digest=contract["deterministic_digest"],
            candidate_identities=identities,
            candidate_identity_digest=identity_digest,
            cells=cells,
            cell_count=len(cells),
            schedule_digest=digest(cells),
            budget_prefix_pairs=[
                dict(
                    task_slot=t,
                    scale=s,
                    seed=r,
                    low_cell_id=indexed[t, 256, s, r],
                    high_cell_id=indexed[t, 512, s, r],
                )
                for t, s, r in product(range(12), q.SCALES, q.SEEDS)
            ],
            four_cell_blocks=[
                dict(
                    task_slot=t,
                    seed=r,
                    arm_cell_ids=[indexed[t, b, s, r] for b, s in ARMS],
                )
                for t, r in product(range(12), q.SEEDS)
            ],
            solvability_verified=False,
            generation_order_verified=False,
            cohort_sealed=False,
            production_cell_keys_materialized=False,
            development_execution_authorized=False,
        )
    )


def build_schedule_candidate(identities: object, root: Path = ROOT) -> dict:
    return _schedule(build_contract(root), identities)


def validate_schedule_candidate(raw: bytes, root: Path = ROOT) -> dict:
    candidate = core.parse_canonical(raw)
    core.require_digest(candidate)
    require("candidate_identities" in candidate, "candidate identities missing")
    expected = build_schedule_candidate(candidate["candidate_identities"], root)
    require(canonical(expected) == raw, "candidate differs from exact regeneration")
    return expected


def synthetic_identities() -> list[dict]:
    """Hash labelled test strings; never construct inputs, targets, or solutions."""
    return [
        dict(
            task_slot=i,
            task_fingerprint=digest(["synthetic-v6-task", i]),
            source_multiset_fingerprint=digest(["synthetic-v6-source", i]),
        )
        for i in range(12)
    ]


def self_test() -> dict:
    candidate = build_schedule_candidate(synthetic_identities())
    require(
        canonical(validate_schedule_candidate(canonical(candidate)))
        == canonical(candidate),
        "synthetic regeneration differs",
    )
    require(
        len(candidate["cells"])
        == len({c["cell_id"] for c in candidate["cells"]})
        == 192,
        "synthetic cell closure differs",
    )
    require(
        len(candidate["budget_prefix_pairs"]) == 96
        and len(candidate["four_cell_blocks"]) == 48,
        "synthetic pair/block closure differs",
    )
    return dict(
        status="DEVELOPMENT_CONTRACT_SYNTHETIC_CHECKS_PASS_NOT_AUTHORIZED",
        contract_digest=candidate["contract_digest"],
        synthetic_schedule_digest=candidate["deterministic_digest"],
        synthetic_cell_count=192,
        synthetic_budget_prefix_pairs=96,
        synthetic_four_cell_blocks=48,
        new_development_tasks_generated=0,
        search_executions=0,
        provider_calls=0,
        development_execution_authorized=False,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--manifest", action="store_true")
    modes.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    sys.stdout.buffer.write(
        canonical(build_contract() if args.manifest else self_test())
    )


if __name__ == "__main__":
    main()
