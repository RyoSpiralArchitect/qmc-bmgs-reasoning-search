from __future__ import annotations

import copy
import json
import math
import tempfile
import unittest
from pathlib import Path

from qmc_bmgs.experiments.countdown_calibration_adversarial_audit import (
    CONFIGURATIONS,
    CONFIG_BY_ID,
    FROZEN_SELECTED_CONFIG_ORACLE,
    IID_METHOD,
    METHODS,
    PROPOSAL_BEHAVIOR_DIGESTS,
    PROVIDERS,
    QMC_METHOD,
    RECORD_SCHEMA_VERSION,
    SEEDS,
    TASKS,
    AuditError,
    _exact_mcnemar,
    _normal_descriptive_interval,
    _record_digest,
    _strict_json,
    main as audit_main,
    audit_record_sets,
)


def _fixture_record(
    *,
    config_id: str,
    provider: str,
    task_fingerprint: str,
    seed: int,
    method: str,
) -> dict[str, object]:
    qmc = method == QMC_METHOD
    diagnostics = {
        "exact_terminal_count": 0,
        "first_exact_verifier": 9,
        "mean_chosen_prior_mass": 0.25,
        "mean_normalized_prior_rank": 0.25,
        "mean_prior_regret": 1.0,
        "noise_overrode_proposal_rate": 0.5,
        "positive_posterior_action_count": 0,
        "positive_posterior_update_count": 0,
        "root_jsd_from_proposal_prior": 0.01,
        "root_top_set_visit_fraction": 0.5,
        "root_unique_arms": 4 + int(qmc),
        "root_visit_entropy": 0.8 + 0.1 * int(qmc),
        "success_auc": 0.0,
        "success_by_verifier": [False] * 8,
        "top_set_retention": 0.5,
        "unique_edge_count": 20 + int(qmc),
        "unique_terminal_trace_count": 8,
    }
    task = {
        **TASKS[task_fingerprint],
        "task_fingerprint": task_fingerprint,
    }
    config = CONFIG_BY_ID[config_id]
    payload: dict[str, object] = {
        "bank_digest": f"bank-{task_fingerprint}-{seed}",
        "calibration_config": config,
        "claim_role": "offline_calibration_development_only",
        "diagnostics": diagnostics,
        "exact_success_any": False,
        "method": method,
        "method_config": {
            "posterior_sd_scale": config["posterior_sd_scale"],
            "prior_bonus": config["prior_bonus"],
            "selected_perturbation_source": "sobol" if qmc else "iid",
        },
        "proposal_behavior_digest": PROPOSAL_BEHAVIOR_DIGESTS[provider],
        "provider": provider,
        "schema_version": RECORD_SCHEMA_VERSION,
        "seed": seed,
        "task": task,
        "terminal_success": [False] * 8,
        "trajectory_digest": (
            f"trajectory-{task_fingerprint}-{seed}-{method}"
        ),
    }
    return {**payload, "deterministic_digest": _record_digest(payload)}


def _fixture_shards() -> dict[str, list[dict[str, object]]]:
    return {
        config_id: [
            _fixture_record(
                config_id=config_id,
                provider=provider,
                task_fingerprint=task_fingerprint,
                seed=seed,
                method=method,
            )
            for provider in PROVIDERS
            for task_fingerprint in TASKS
            for seed in SEEDS
            for method in METHODS
        ]
        for config_id, _, _ in CONFIGURATIONS
    }


class CalibrationAdversarialAuditTests(unittest.TestCase):
    def test_normal_descriptive_interval_uses_paired_sample_se(self) -> None:
        observed = _normal_descriptive_interval([-1.0, 0.0, 1.0])
        radius = 1.959963984540054 / math.sqrt(3)
        self.assertEqual(observed["mean_qmc_minus_iid"], 0.0)
        self.assertEqual(observed["sample_sd"], 1.0)
        self.assertAlmostEqual(observed["normal_95_interval"][0], -radius)
        self.assertAlmostEqual(observed["normal_95_interval"][1], radius)

    def test_exact_mcnemar_uses_two_sided_binomial_tail(self) -> None:
        observed = _exact_mcnemar(
            iid_only=5,
            qmc_only=0,
            both_success=3,
            neither=120,
        )
        self.assertEqual(observed["discordant_total"], 5)
        self.assertEqual(observed["two_sided_exact_p"], 0.0625)
        tied = _exact_mcnemar(
            iid_only=0,
            qmc_only=0,
            both_success=4,
            neither=124,
        )
        self.assertEqual(tied["two_sided_exact_p"], 1.0)

    def test_full_layout_and_equal_kappa_invariants(self) -> None:
        shards = _fixture_shards()
        identity = {
            "artifact_locator": "fixture",
            "manifest_deterministic_digest": "fixture",
            "shards": {
                config_id: {
                    "filename": f"search_records_{config_id}.jsonl",
                    "sha256": f"fixture-{config_id}",
                }
                for config_id in shards
            },
        }
        report = audit_record_sets(
            shards,
            artifact_identity=identity,
            enforce_frozen_oracle=False,
        )
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["coverage"]["observed_records"], 9216)
        self.assertTrue(
            report["equal_kappa_invariants"]["all_invariants_pass"]
        )
        selected = next(
            row
            for row in report["paired_source_comparison"]["pooled_by_config"]
            if row["calibration_config"]["config_id"] == "prior_1__sd_1"
        )
        edge_delta = selected["summary"]["metric_deltas"][
            "unique_edge_count"
        ]["mean_qmc_minus_iid"]
        self.assertEqual(edge_delta, 1.0)
        self.assertFalse(
            selected["summary"]["sampler_inference"]["performed"]
        )
        self.assertNotIn(
            "normal_95_interval",
            selected["summary"]["metric_deltas"]["exact_success"],
        )
        self.assertNotIn("mcnemar_exact_success", selected["summary"])

        broken = copy.deepcopy(shards)
        broken["prior_0p1__sd_0p25"].pop()
        with self.assertRaisesRegex(AuditError, "coverage mismatch"):
            audit_record_sets(
                broken,
                artifact_identity=identity,
                enforce_frozen_oracle=False,
            )

    def test_selected_oracle_is_external_and_fixed(self) -> None:
        self.assertEqual(
            FROZEN_SELECTED_CONFIG_ORACLE["config"]["config_id"],
            "prior_1__sd_1",
        )
        self.assertEqual(
            FROZEN_SELECTED_CONFIG_ORACLE["shard_sha256"],
            "53d01ea7d2586b4d0d5430a4035ca28b6467f257517c8d2956775abbe2bd5e5a",
        )
        self.assertEqual(
            FROZEN_SELECTED_CONFIG_ORACLE["success_counts"]["all"],
            173,
        )
        self.assertEqual(
            FROZEN_SELECTED_CONFIG_ORACLE["success_counts"][IID_METHOD],
            95,
        )

    def test_strict_json_rejects_duplicates_and_non_finite_values(self) -> None:
        with self.assertRaisesRegex(AuditError, "duplicate JSON key"):
            _strict_json('{"value":1,"value":2}')
        with self.assertRaisesRegex(AuditError, "non-finite JSON constant"):
            _strict_json('{"value":NaN}')

    def test_cli_reports_array_manifest_as_invalid_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            artifact = root_path / "artifact"
            artifact.mkdir()
            (artifact / "manifest.json").write_text("[]\n", encoding="utf-8")
            output = root_path / "audit.json"

            result = audit_main(
                [
                    "--artifact-dir",
                    str(artifact),
                    "--output",
                    str(output),
                ]
            )

            self.assertEqual(result, 2)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "INVALID_ARTIFACT")
            self.assertIn("not a JSON object", report["error"])


if __name__ == "__main__":
    unittest.main()
