"""v7 admission fault tests; mocked repeated PUBLIC rows are not a real cohort.

No new arithmetic fixture is introduced. Positive storage/metadata exercises
repeat the already excluded target-720 PUBLIC definition and explicitly mock
the identity gate. Unmocked admission must reject those rows. No new generator,
solver, search, calibration or witness is invoked by this suite.
"""

from __future__ import annotations

import copy
import io
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "replication_admission_tested",
    ROOT / "scripts/feedback_budget_replication_admission.py",
)
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def rehash(value):
    return M.core.with_digest(
        {k: v for k, v in value.items() if k != "deterministic_digest"}
    )


def reference(root=ROOT / "artifacts/work"):
    return dict(
        summary_path=str(root / "synthetic-summary.json"),
        summary_sha256="1" * 64,
        summary_digest="2" * 64,
        output_path=str(root / "synthetic-output"),
        commit_digest="3" * 64,
        source_digest="4" * 64,
    )


class FakeSuite:
    def __init__(self, candidate):
        self.tasks = (M.q.TASK,) * 64
        x = candidate["exclusion_identities"]
        value = dict(
            accepted_count=64,
            accepted_task_pool_digest=M.digest([t.to_dict() for t in self.tasks]),
            attempt_count=64,
            conditioned_on_exhaustive_solvability=True,
            excluded_identity_record_digest=x["deterministic_digest"],
            excluded_source_multiset_fingerprint_count=179,
            excluded_source_multiset_fingerprint_digest=M.digest(
                x["source_multiset_fingerprints"]
            ),
            excluded_task_fingerprint_count=243,
            excluded_task_fingerprint_digest=M.digest(x["task_fingerprints"]),
            generator_id="sha256-counter-mod/v1",
            input_range_inclusive=[1, 10],
            max_attempts=10000,
            rejection_counts={
                name: 0
                for name in (
                    "duplicate_full_task",
                    "duplicate_source_multiset",
                    "excluded_full_task",
                    "excluded_source_multiset",
                    "unsolvable",
                )
            },
            rejection_log=[],
            requested_count=64,
            seed=26091301,
            source_multisets_unique=True,
            target_range_inclusive=[100, 999],
        )
        self.generation_manifest = {
            **value,
            "generation_manifest_digest": M.digest(value),
        }

    @property
    def calibrations(self):
        raise AssertionError("calibration/witness/hardness accessed")


class SyntheticSetup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = M.contract.build_contract()
        cls.authorities = rehash(
            dict(
                exclusion_identities=cls.contract["exclusion_identities"],
                synthetic_only=True,
            )
        )
        cls.context = dict(
            source={"admission_revision": "f" * 40},
            authorities=cls.authorities,
            synthetic_only=True,
        )
        cls.pipeline = reference()
        cls.suite = FakeSuite(cls.contract)
        # An intentionally impossible source-distinct cohort, under explicit
        # mocks, exercises structural metadata only. It is rejected without them.
        with (
            patch.object(M, "_tasks"),
            patch.object(
                M.historical, "generate_solvable_task_suite", return_value=cls.suite
            ),
        ):
            cls.cohort = M._cohort(cls.contract, cls.authorities)
            cls.seal = M._seal(cls.cohort, cls.contract, cls.context, cls.pipeline)


class IdentityTests(SyntheticSetup):
    def test_domain_negatives_reject_before_context_generation_or_search(self):
        with (
            patch.object(M, "revalidate_context") as context,
            patch.object(M.historical, "generate_solvable_task_suite") as generator,
            patch.object(M.q, "run_countdown_track_a_search") as search,
        ):
            value = M.negative_checks()
        self.assertEqual(len(value["rejected_as_replication_seals"]), 8)
        self.assertEqual(value["new_replication_tasks_generated"], 0)
        context.assert_not_called()
        generator.assert_not_called()
        search.assert_not_called()

    def test_unmocked_repeated_public_rows_never_admit_the_synthetic_seal(self):
        with patch.object(M.historical, "generate_solvable_task_suite") as generator:
            with self.assertRaises(ValueError):
                M.validate_seal_bytes(M.canonical(self.seal))
        generator.assert_not_called()

    def test_fixed_new_generator_arguments_and_no_calibration_access(self):
        with (
            patch.object(M, "_tasks"),
            patch.object(
                M.historical, "generate_solvable_task_suite", return_value=self.suite
            ) as generator,
        ):
            result = M._cohort(self.contract, self.authorities)
        x = self.contract["exclusion_identities"]
        generator.assert_called_once_with(
            64,
            26091301,
            max_attempts=10000,
            excluded_task_fingerprints=tuple(x["task_fingerprints"]),
            excluded_source_multiset_fingerprints=tuple(
                x["source_multiset_fingerprints"]
            ),
            excluded_identity_record_digest=x["deterministic_digest"],
        )
        self.assertEqual(result["persisted_solution_witness_count"], 0)
        self.assertEqual(result["persisted_calibration_profile_count"], 0)

    def test_exact_1024_cells_512_pairs_256_blocks_not_public_keys(self):
        cells = self.seal["cells"]
        self.assertEqual(len(cells), 1024)
        self.assertEqual(len({c["cell_id"] for c in cells}), 1024)
        self.assertEqual(len(self.seal["budget_prefix_pairs"]), 512)
        self.assertEqual(len(self.seal["four_cell_blocks"]), 256)
        self.assertFalse(
            set(c["cell_id"] for c in cells)
            & set(c["cell_id"] for c in M.k.fixture_manifest()["cells"])
        )
        self.assertEqual(self.seal["generation_qualification"], self.pipeline)
        self.assertFalse(self.seal["replication_execution_authorized"])
        self.assertEqual(self.seal["cells"][-1]["cell_key"]["seed"], 8195)

    def test_closed_rows_plain_numbers_and_witness_reject_before_regeneration(self):
        mutations = (
            lambda x: x.update(target=True),
            lambda x: x.update(target=720.0),
            lambda x: x["inputs"].__setitem__(0, True),
            lambda x: x.update(task_fingerprint="0" * 64),
            lambda x: x.update(solution_witness="synthetic forbidden field"),
            lambda x: x.update(inputs=[1, 2, 3, 4, 5]),
        )
        for mutate in mutations:
            rows = copy.deepcopy(self.cohort["tasks"])
            mutate(rows[0])
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                M._tasks(rows, self.contract)

    def test_all_eight_identity_exclusion_groups_and_duplicate_sources(self):
        identities = M.contract.synthetic_identities()
        x = self.contract["exclusion_identities"]
        for group in x["cohorts"]:
            for field, collection in (
                ("task_fingerprint", "task_fingerprints"),
                ("source_multiset_fingerprint", "source_multiset_fingerprints"),
            ):
                changed = copy.deepcopy(identities)
                changed[0][field] = group[collection][0]
                with (
                    self.subTest(group=group, field=field),
                    self.assertRaises(ValueError),
                ):
                    M.contract._schedule(self.contract, changed)
        changed = copy.deepcopy(identities)
        changed[1]["source_multiset_fingerprint"] = changed[0][
            "source_multiset_fingerprint"
        ]
        with self.assertRaises(ValueError):
            M.contract._schedule(self.contract, changed)

    def test_rehashed_schedule_and_generation_mutations_fail_before_generator(self):
        variants = []
        for mutate in (
            lambda v: v["cells"][-1].update(cell_index=True),
            lambda v: v["cells"].pop(),
            lambda v: v["four_cell_blocks"].reverse(),
            lambda v: v["cohort"]["generation_recipe"].update(seed=0),
            lambda v: v["cohort"].update(unrecognized=True),
        ):
            value = copy.deepcopy(self.seal)
            mutate(value)
            value["cohort"] = rehash(value["cohort"])
            variants.append(rehash(value))
        for value in variants:
            with (
                self.subTest(value=value["deterministic_digest"]),
                patch.object(M, "_tasks"),
                patch.object(M.historical, "generate_solvable_task_suite") as generator,
                patch.object(M, "verify_generation_reference") as qualification,
                self.assertRaises(ValueError),
            ):
                M.validate_seal_bytes(M.canonical(value))
            generator.assert_not_called()
            qualification.assert_not_called()

    def test_context_then_new_pipeline_qualification_before_new_recipe(self):
        for gate in ("context", "pipeline"):
            with (
                patch.object(M, "_tasks"),
                patch.object(
                    M,
                    "revalidate_context",
                    side_effect=ValueError("context") if gate == "context" else None,
                ),
                patch.object(
                    M, "verify_generation_reference", side_effect=ValueError("pipeline")
                ) as qualifier,
                patch.object(M, "_cohort") as generator,
                self.assertRaisesRegex(ValueError, gate),
            ):
                M.validate_seal_bytes(M.canonical(self.seal))
            generator.assert_not_called()
            if gate == "context":
                qualifier.assert_not_called()

    def test_synthetic_full_reconstruction_requires_identical_generator_order(self):
        with (
            patch.object(M, "_tasks"),
            patch.object(M, "revalidate_context"),
            patch.object(
                M,
                "verify_generation_reference",
                return_value=(self.pipeline, lambda: None),
            ),
            patch.object(M, "_cohort", return_value=self.cohort) as generator,
        ):
            result = M.validate_seal_bytes(M.canonical(self.seal))
        self.assertEqual(result, self.seal)
        generator.assert_called_once()
        changed = rehash({**self.cohort, "task_set_digest": "0" * 64})
        with (
            patch.object(M, "_tasks"),
            patch.object(M, "revalidate_context"),
            patch.object(
                M,
                "verify_generation_reference",
                return_value=(self.pipeline, lambda: None),
            ),
            patch.object(M, "_cohort", return_value=changed),
            self.assertRaisesRegex(ValueError, "acceptance order"),
        ):
            M.validate_seal_bytes(M.canonical(self.seal))

    def test_historical_orders_verified_once_and_cached_snapshots_rechecked(self):
        base, values, _ = M.contract._context(ROOT)
        old = values[M.contract.V6]["cohort"]
        suite = SimpleNamespace(
            tasks=tuple(
                SimpleNamespace(to_dict=lambda row=row: row) for row in old["tasks"]
            ),
            generation_manifest=old["generation_manifest"],
        )
        v5 = SimpleNamespace(
            payload=values[M.contract.old.V5],
            seal_digest=values[M.contract.old.V5]["deterministic_digest"],
        )
        with (
            patch.object(M, "_AUTHORITY_CACHE", None),
            patch.object(
                M.historical,
                "verify_countdown_thompson_dense_scale_bundle",
                return_value=v5,
            ) as verify,
            patch.object(
                M.historical, "generate_solvable_task_suite", return_value=suite
            ) as generator,
        ):
            first = M.verified_authorities()
            second = M.verified_authorities()
            self.assertEqual(first, second)
            first["exclusion_identities"]["task_fingerprints"].clear()
            self.assertEqual(
                len(
                    M.verified_authorities()["exclusion_identities"][
                        "task_fingerprints"
                    ]
                ),
                243,
            )
            raw, snapshots = M._AUTHORITY_CACHE
            bomb = SimpleNamespace(
                revalidate=lambda: (_ for _ in ()).throw(ValueError("changed"))
            )
            M._AUTHORITY_CACHE = (raw, (*snapshots, bomb))
            with self.assertRaisesRegex(ValueError, "changed"):
                M.verified_authorities()
        verify.assert_called_once()
        self.assertEqual(generator.call_count, 1)
        self.assertEqual(generator.call_args.args, (12, 26090401))
        self.assertEqual(base["task_count"], 12)


class StorageTests(SyntheticSetup):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.path = self.root / "cohort"
        self.location = patch.object(M, "COHORT_PATH", self.path)
        self.location.start()

    def tearDown(self):
        self.location.stop()
        self.temp.cleanup()

    def publish(self, build=None, check=lambda: None):
        return M._publish_cohort(
            self.path, self.context, build or (lambda: self.seal), check, self.pipeline
        )

    def test_started_before_build_complete_three_file_closure_last_seal(self):
        def build():
            self.assertEqual({p.name for p in self.path.iterdir()}, {"STARTED.json"})
            return self.seal

        self.publish(build)
        self.assertEqual({p.name for p in self.path.iterdir()}, M.NAMES)
        with patch.object(M, "validate_seal_bytes", return_value=self.seal):
            loaded = M.load_seal(self.path)
        self.assertEqual(loaded.manifest, self.seal)
        loaded.revalidate()
        with self.assertRaises(AttributeError):
            loaded._path = self.root

    def test_occupied_slot_never_adopted_or_resumed(self):
        self.path.mkdir(mode=0o700)

        def build():
            self.fail("generator called")

        with self.assertRaises((ValueError, OSError)):
            self.publish(build)
        self.assertEqual(list(self.path.iterdir()), [])

    def test_failed_build_retains_failure_and_no_final_seal(self):
        def fail():
            raise ValueError("synthetic generation failure")

        with self.assertRaisesRegex(ValueError, "synthetic"):
            self.publish(fail)
        self.assertEqual(
            {p.name for p in self.path.iterdir()}, {"STARTED.json", "FAILURE.json"}
        )
        with (
            patch.object(M, "validate_seal_bytes") as validate,
            self.assertRaises(ValueError),
        ):
            M.load_seal(self.path)
        validate.assert_not_called()

    def test_post_seal_uncertainty_does_not_countermand_final_marker(self):
        def check():
            if (self.path / "SEALED.json").exists():
                raise ValueError("late state change")

        with self.assertRaises(M.storage.PublicationUncertain):
            self.publish(check=check)
        self.assertTrue((self.path / "SEALED.json").exists())
        self.assertFalse((self.path / "FAILURE.json").exists())

    def test_transaction_linkage_rejected_before_regeneration(self):
        self.publish()
        final = self.path / "SEALED.json"
        value = M.core.parse_canonical(final.read_bytes())
        final.write_bytes(M.canonical(rehash({**value, "seal_digest": "0" * 64})))
        with (
            patch.object(M, "validate_seal_bytes") as validate,
            self.assertRaises(ValueError),
        ):
            M.load_seal(self.path)
        validate.assert_not_called()

    def test_symlink_hardlink_extra_entry_and_late_mutation_rejected(self):
        self.publish()
        with patch.object(M, "validate_seal_bytes", return_value=self.seal):
            loaded = M.load_seal(self.path)
        (self.path / "extra").write_bytes(b"synthetic")
        with self.assertRaises(ValueError):
            loaded.revalidate()
        (self.path / "extra").unlink()
        seal = self.path / "preregistration.json"
        raw = seal.read_bytes()
        alias = self.root / "alias"
        os.link(seal, alias)
        with (
            patch.object(M, "validate_seal_bytes") as validate,
            self.assertRaises((ValueError, M.mechanics.RegularFilePublicationV2Error)),
        ):
            M.load_seal(self.path)
        validate.assert_not_called()
        alias.unlink()
        seal.unlink()
        alias.write_bytes(raw)
        seal.symlink_to(alias)
        with (
            patch.object(M, "validate_seal_bytes") as validate,
            self.assertRaises((ValueError, M.mechanics.RegularFilePublicationV2Error)),
        ):
            M.load_seal(self.path)
        validate.assert_not_called()

    def test_wrong_generation_digest_or_occupied_slot_rejects_before_qualification(
        self,
    ):
        proof = self.root / "proof.json"
        proof.write_bytes(M.canonical(rehash({"synthetic_only": True})))
        with (
            patch.object(M.k, "load") as qualifier,
            self.assertRaisesRegex(ValueError, "digest"),
        ):
            M.seal_cohort(proof, "0" * 64)
        qualifier.assert_not_called()
        self.path.mkdir(mode=0o700)
        with (
            patch.object(M.k, "load") as qualifier,
            self.assertRaisesRegex(ValueError, "occupied"),
        ):
            M.seal_cohort(proof, "0" * 64)
        qualifier.assert_not_called()

    def test_sealing_requires_verified_new_connector_and_retains_reference(self):
        proof = self.root / "proof.json"
        saved = rehash({"synthetic_only": True})
        proof.write_bytes(M.canonical(saved))
        pipeline = {**self.pipeline, "summary_digest": saved["deterministic_digest"]}
        check = unittest.mock.Mock()
        connector = SimpleNamespace(
            qualified_public=unittest.mock.Mock(
                return_value=(pipeline, {"admission_proof": self.context}, check)
            )
        )
        with (
            patch.object(M.k, "load", return_value=connector),
            patch.object(M, "revalidate_context"),
            patch.object(M, "_tasks"),
            patch.object(M, "_cohort", return_value=self.cohort) as generator,
        ):
            value = M.seal_cohort(proof, saved["deterministic_digest"])
        self.assertEqual(value["generation_qualification"], pipeline)
        self.assertFalse(value["replication_execution_authorized"])
        generator.assert_called_once()
        self.assertGreater(check.call_count, 2)

    def test_admission_candidate_remains_distinct_nonexecutable_domain(self):
        self.publish()
        with patch.object(M, "validate_seal_bytes", return_value=self.seal):
            loaded = M.load_seal(self.path)
        with (
            patch.object(M, "revalidate_context"),
            patch.object(M.public, "_output", side_effect=lambda p: Path(p)),
        ):
            result = M.candidate(loaded, self.root / "out")
        self.assertEqual(result["schema_version"], M.DOMAIN + "/seal-review-candidate")
        self.assertFalse(result["replication_execution_authorized"])
        self.assertFalse(result["execution_adapter_qualified"])


class CliTests(unittest.TestCase):
    def test_completed_seal_stdout_failure_does_not_claim_invalid_admission(self):
        for failing in ("write", "flush"):
            stderr = io.StringIO()

            def fail(*args):
                raise BrokenPipeError("synthetic stdout closed")

            stream = SimpleNamespace(
                write=fail if failing == "write" else lambda *a: None,
                flush=fail if failing == "flush" else lambda: None,
            )
            with (
                patch.object(
                    sys,
                    "argv",
                    [
                        M.SCRIPT,
                        "--seal-cohort",
                        "--qualification",
                        "synthetic.json",
                        "--expected-digest",
                        "0" * 64,
                    ],
                ),
                patch.object(sys, "stdout", SimpleNamespace(buffer=stream)),
                patch.object(sys, "stderr", stderr),
                patch.object(
                    M, "seal_cohort", return_value={"synthetic_completed": True}
                ),
            ):
                self.assertEqual(M.main(), 1)
            result = M.core.parse_canonical(stderr.getvalue().encode())
            self.assertEqual(result["status"], "RESULT_DELIVERY_UNCERTAIN")
            self.assertTrue(result["cohort_generation_consumed"])
            self.assertFalse(result["replication_execution_authorized"])

    def test_uncertain_cohort_publication_remains_uncertain(self):
        stderr = io.StringIO()
        with (
            patch.object(
                sys,
                "argv",
                [
                    M.SCRIPT,
                    "--seal-cohort",
                    "--qualification",
                    "synthetic.json",
                    "--expected-digest",
                    "0" * 64,
                ],
            ),
            patch.object(sys, "stderr", stderr),
            patch.object(
                M, "seal_cohort", side_effect=M.storage.PublicationUncertain("retained")
            ),
        ):
            self.assertEqual(M.main(), 1)
        result = M.core.parse_canonical(stderr.getvalue().encode())
        self.assertEqual(result["status"], "PUBLICATION_UNCERTAIN")
        self.assertIsNone(result["cohort_generation_consumed"])

    def test_verified_seal_stdout_failure_keeps_known_generation_consumption(self):
        stderr = io.StringIO()

        def fail(*args):
            raise BrokenPipeError("synthetic stdout closed")

        stream = SimpleNamespace(write=fail, flush=lambda: None)
        with (
            patch.object(
                sys, "argv", [M.SCRIPT, "--verify-seal", "synthetic-directory"]
            ),
            patch.object(sys, "stdout", SimpleNamespace(buffer=stream)),
            patch.object(sys, "stderr", stderr),
            patch.object(
                M,
                "load_seal",
                return_value=SimpleNamespace(
                    manifest={"deterministic_digest": "0" * 64}
                ),
            ),
        ):
            self.assertEqual(M.main(), 1)
        result = M.core.parse_canonical(stderr.getvalue().encode())
        self.assertEqual(result["status"], "RESULT_DELIVERY_UNCERTAIN")
        self.assertTrue(result["cohort_generation_consumed"])
        self.assertFalse(result["replication_execution_authorized"])

    def test_outside_checkout_readonly_mode_and_no_ignored_overrides(self):
        for args, expected in (
            (("--self-test",), 0),
            (("--self-test", "--output", "x"), 1),
            (("--self-t",), 2),
            (("--self-test", "--seed", "1"), 2),
            (("--self-test", "--resume"), 2),
        ):
            result = subprocess.run(
                [sys.executable, "-P", "-B", str(ROOT / M.SCRIPT), *args],
                cwd="/tmp",
                env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
                capture_output=True,
            )
            self.assertEqual(
                result.returncode, expected, result.stderr or result.stdout
            )


if __name__ == "__main__":
    unittest.main()
