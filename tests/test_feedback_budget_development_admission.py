"""Synthetic sealing tests are not generated-cohort or execution evidence."""

from __future__ import annotations

import copy
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "feedback_budget_admission_tested",
    ROOT / "scripts/feedback_budget_development_admission.py",
)
assert SPEC is not None and SPEC.loader is not None
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def rehash(value):
    return M.core.with_digest(
        {k: v for k, v in value.items() if k != "deterministic_digest"}
    )


class FakeSuite:
    """Handwritten test rows, NOT output of the fixed recipe or solver."""

    def __init__(self, candidate):
        inputs = [(1, 1, 1, 1, 1, i) for i in range(1, 11)] + [
            (1, 1, 1, 1, 2, 2),
            (1, 1, 1, 1, 2, 3),
        ]
        # The all-ones and five-ones-plus-two sources are historical fixtures.
        inputs[:2] = [(2, 2, 2, 2, 2, 2), (2, 2, 2, 2, 2, 3)]
        self.tasks = tuple(M.q.CountdownTask(x, 123 + i) for i, x in enumerate(inputs))
        exclusions = candidate["exclusion_identities"]
        value = dict(
            accepted_count=12,
            accepted_task_pool_digest=M.digest([t.to_dict() for t in self.tasks]),
            attempt_count=12,
            conditioned_on_exhaustive_solvability=True,
            excluded_identity_record_digest=exclusions["deterministic_digest"],
            excluded_source_multiset_fingerprint_count=167,
            excluded_source_multiset_fingerprint_digest=M.digest(
                exclusions["source_multiset_fingerprints"]
            ),
            excluded_task_fingerprint_count=179,
            excluded_task_fingerprint_digest=M.digest(exclusions["task_fingerprints"]),
            generator_id="sha256-counter-mod/v1",
            input_range_inclusive=[1, 10],
            max_attempts=10000,
            rejection_counts={
                s: 0
                for s in (
                    "duplicate_full_task",
                    "duplicate_source_multiset",
                    "excluded_full_task",
                    "excluded_source_multiset",
                    "unsolvable",
                )
            },
            rejection_log=[],
            requested_count=12,
            seed=26090401,
            source_multisets_unique=True,
            target_range_inclusive=[100, 999],
        )
        self.generation_manifest = {
            **value,
            "generation_manifest_digest": M.digest(value),
        }

    @property
    def calibrations(self):
        raise AssertionError("calibration/witness/hardness must never be opened")


class SyntheticSetup:
    @classmethod
    def setUpClass(cls):
        cls.contract = M.contract.build_contract()
        cls.authorities = M.core.with_digest(
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
        cls.suite = FakeSuite(cls.contract)
        with patch.object(
            M.historical, "generate_solvable_task_suite", return_value=cls.suite
        ):
            cls.cohort = M._cohort(cls.contract, cls.authorities)
        cls.seal = M._seal(cls.cohort, cls.contract, cls.context)


class AdmissionIdentityTests(SyntheticSetup, unittest.TestCase):
    def test_verified_historical_chain_does_not_call_new_recipe(self):
        original = M.historical.generate_solvable_task_suite
        with patch.object(
            M.historical, "generate_solvable_task_suite", wraps=original
        ) as generator:
            value = M.verified_authorities()
        self.assertTrue(generator.call_args_list)
        self.assertEqual(
            {call.args[1] for call in generator.call_args_list}, {26082601}
        )
        self.assertEqual(
            value["v5_seal_digest"],
            "49f820692aa4f3551ca5634bdc89efe225fe05d1dc8acb8e814f231f3eea222f",
        )
        self.assertEqual(
            value["exclusion_identities"], self.contract["exclusion_identities"]
        )
        self.assertEqual(value["new_development_tasks_generated"], 0)

    def test_new_target_on_public_source_is_still_excluded(self):
        rows = copy.deepcopy(self.cohort["tasks"])
        rows[0] = M.q.CountdownTask((1, 2, 3, 4, 5, 6), 333).to_dict()
        with self.assertRaisesRegex(ValueError, "excluded"):
            M._tasks(rows, self.contract)

    def test_domain_negatives_do_not_reach_generator_search_or_context(self):
        with (
            patch.object(
                M.historical,
                "generate_solvable_task_suite",
                side_effect=AssertionError("generator"),
            ),
            patch.object(
                M.q,
                "run_countdown_track_a_search",
                side_effect=AssertionError("search"),
            ),
            patch.object(M, "context", side_effect=AssertionError("context")),
        ):
            result = M.negative_checks()
        self.assertEqual(len(result["rejected_as_development_seals"]), 8)
        self.assertEqual(result["new_development_tasks_generated"], 0)

    def test_fixed_generator_call_and_no_calibration_access(self):
        with patch.object(
            M.historical, "generate_solvable_task_suite", return_value=self.suite
        ) as generator:
            result = M._cohort(self.contract, self.authorities)
        x = self.contract["exclusion_identities"]
        generator.assert_called_once_with(
            12,
            26090401,
            max_attempts=10000,
            excluded_task_fingerprints=tuple(x["task_fingerprints"]),
            excluded_source_multiset_fingerprints=tuple(
                x["source_multiset_fingerprints"]
            ),
            excluded_identity_record_digest=x["deterministic_digest"],
        )
        self.assertEqual(result["tasks"], [t.to_dict() for t in self.suite.tasks])
        self.assertEqual(result["persisted_solution_witness_count"], 0)

    def test_synthetic_roundtrip_only_under_explicit_generator_context_mocks(self):
        stages = []
        with (
            patch.object(
                M, "revalidate_context", side_effect=lambda c: stages.append("context")
            ),
            patch.object(
                M.historical,
                "generate_solvable_task_suite",
                side_effect=lambda *a, **kw: (stages.append("generate"), self.suite)[1],
            ),
            patch.object(
                M.q,
                "run_countdown_track_a_search",
                side_effect=AssertionError("search"),
            ),
        ):
            result = M.validate_seal_bytes(M.canonical(self.seal))
        self.assertEqual(stages, ["context", "generate", "context"])
        self.assertEqual(M.canonical(result), M.canonical(self.seal))
        self.assertFalse(result["development_execution_authorized"])

    def test_all_cells_pairs_blocks_are_bound_and_separate_from_public(self):
        value = self.seal
        self.assertEqual(
            (
                len(value["cells"]),
                len(value["budget_prefix_pairs"]),
                len(value["four_cell_blocks"]),
            ),
            (192, 96, 48),
        )
        cells = {row["cell_id"]: row for row in value["cells"]}
        self.assertEqual(len(cells), 192)
        self.assertFalse(
            set(cells) & {c["cell_id"] for c in M.k.fixture_manifest()["cells"]}
        )
        for index, (coord, row) in enumerate(zip(M.k.COORDINATES, value["cells"])):
            key = row["cell_key"]
            self.assertEqual(
                tuple(key[k] for k in ("task_slot", "budget", "scale", "seed")), coord
            )
            self.assertEqual(row["cell_index"], index)
            self.assertEqual(row["cell_id"], M.digest(key))
            self.assertEqual(
                key["cohort_digest"], value["cohort"]["deterministic_digest"]
            )
            self.assertEqual(key["execution_mode"], M.MODE)
        paired, blocked = [], []
        for pair in value["budget_prefix_pairs"]:
            paired.extend((pair["low_cell_id"], pair["high_cell_id"]))
        for block in value["four_cell_blocks"]:
            blocked.extend(block["arm_cell_ids"])
            for arm, cell_id in zip(M.k.ARMS, block["arm_cell_ids"]):
                key = cells[cell_id]["cell_key"]
                self.assertEqual((key["budget"], key["scale"]), arm)
        self.assertEqual(sorted(paired), sorted(cells))
        self.assertEqual(sorted(blocked), sorted(cells))

    def reject_before_generator(self, value):
        with (
            patch.object(M.historical, "generate_solvable_task_suite") as generator,
            patch.object(M, "revalidate_context") as context,
            self.assertRaises((ValueError, KeyError, TypeError)),
        ):
            M.validate_seal_bytes(M.canonical(rehash(value)))
        generator.assert_not_called()
        context.assert_not_called()

    def test_rehashed_schedule_or_contract_mutations_rejected_before_generator(self):
        mutations = [
            lambda v: v["cells"].reverse(),
            lambda v: v["cells"].pop(),
            lambda v: v["cells"][191]["cell_key"].update(seed=8192),
            lambda v: v["budget_prefix_pairs"][0].update(scale=16),
            lambda v: v["four_cell_blocks"][0]["arm_cell_ids"].reverse(),
            lambda v: v.update(cell_count=192.0),
            lambda v: v.update(development_execution_authorized=True),
            lambda v: v.update(unknown=True),
            lambda v: v.update(execution_mode=M.k.MODE),
            lambda v: v["contract"].update(prior_authorization_reusable=True),
        ]
        for mutate in mutations:
            value = copy.deepcopy(self.seal)
            mutate(value)
            with self.subTest(mutate=mutate):
                self.reject_before_generator(value)

    def test_noncanonical_nonfinite_duplicate_json_rejected(self):
        for raw in (b'{"a":1,"a":1}\n', b'{"a":NaN}\n', b"{}", b"{}\n "):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                M.validate_seal_bytes(raw)

    def test_closed_task_rows_ranges_identities_and_witnesses(self):
        mutations = [
            lambda r: r[0].update(target=True),
            lambda r: r[0].update(target=99),
            lambda r: r[0]["inputs"].__setitem__(0, True),
            lambda r: r[0]["inputs"].__setitem__(0, 11),
            lambda r: r[0].update(task_fingerprint="f" * 64),
            lambda r: r[0].update(solution_witness={}),
            lambda r: r[0].update(max_steps=5.0),
            lambda r: r.__setitem__(1, r[0]),
            lambda r: r.pop(),
        ]
        for mutate in mutations:
            rows = copy.deepcopy(self.cohort["tasks"])
            mutate(rows)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                M._tasks(rows, self.contract)

    def test_source_duplicate_different_targets_is_rejected(self):
        rows = copy.deepcopy(self.cohort["tasks"])
        rows[1] = M.q.CountdownTask(tuple(rows[0]["inputs"]), 777).to_dict()
        with self.assertRaisesRegex(ValueError, "duplicate"):
            M._tasks(rows, self.contract)

    def test_all_six_exclusions_apply_to_each_identity_kind(self):
        rows = self.cohort["tasks"]
        for group in self.contract["exclusion_identities"]["cohorts"]:
            for field, list_key in (
                ("task_fingerprint", "task_fingerprints"),
                ("source_multiset_fingerprint", "source_multiset_fingerprints"),
            ):
                altered = copy.deepcopy(self.contract)
                altered["exclusion_identities"][list_key].append(rows[0][field])
                with (
                    self.subTest(group=group["label"], field=field),
                    self.assertRaisesRegex(ValueError, "excluded"),
                ):
                    M._tasks(rows, altered)

    def test_cohort_unknown_or_generation_recipe_mismatch_before_solver(self):
        for mutate in (
            lambda c: c.update(witness={}),
            lambda c: c.update(authority_digest="a" * 64),
            lambda c: c["generation_manifest"].update(seed=26090402),
            lambda c: c["generation_manifest"].update(requested_count=12.0),
            lambda c: c["generation_manifest"].update(calibration_profile={}),
            lambda c: c["generation_manifest"].update(attempt_count=13),
            lambda c: c.update(persisted_solution_witness_count=False),
        ):
            value = copy.deepcopy(self.seal)
            mutate(value["cohort"])
            value["cohort"] = rehash(value["cohort"])
            # Rekey the entire schedule too: hashes are not admission.
            value = M._seal(value["cohort"], self.contract, self.context)
            with self.subTest(mutate=mutate):
                self.reject_before_generator(value)

    def test_rekeyed_cohort_order_requires_exact_regeneration(self):
        cohort = copy.deepcopy(self.cohort)
        cohort["tasks"].reverse()
        cohort["task_set_digest"] = M.digest(cohort["tasks"])
        gen = cohort["generation_manifest"]
        gen["accepted_task_pool_digest"] = M.digest(cohort["tasks"])
        gen["generation_manifest_digest"] = M.digest(
            {k: v for k, v in gen.items() if k != "generation_manifest_digest"}
        )
        changed = M._seal(rehash(cohort), self.contract, self.context)
        with (
            patch.object(M, "revalidate_context"),
            patch.object(
                M.historical, "generate_solvable_task_suite", return_value=self.suite
            ) as generator,
            self.assertRaisesRegex(ValueError, "acceptance order"),
        ):
            M.validate_seal_bytes(M.canonical(changed))
        generator.assert_called_once()

    def test_failed_context_never_invokes_new_generator(self):
        with (
            patch.object(
                M, "revalidate_context", side_effect=ValueError("source/runtime")
            ),
            patch.object(M.historical, "generate_solvable_task_suite") as generator,
            self.assertRaises(ValueError),
        ):
            M.validate_seal_bytes(M.canonical(self.seal))
        generator.assert_not_called()

    def test_late_context_change_invalidates_regeneration(self):
        with (
            patch.object(
                M, "revalidate_context", side_effect=[None, ValueError("late context")]
            ),
            patch.object(
                M.historical, "generate_solvable_task_suite", return_value=self.suite
            ),
            self.assertRaisesRegex(ValueError, "late context"),
        ):
            M.validate_seal_bytes(M.canonical(self.seal))

    def test_public_and_old_adapters_reject_seal(self):
        from qmc_bmgs.experiments import countdown_thompson_dense_scale_runner as old

        raw = M.canonical(self.seal)
        for validate in (M.k.FixtureInputs, old.validate_authorization):
            with self.assertRaises(ValueError):
                validate(raw)


class AdmissionStorageTests(SyntheticSetup, unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(
            prefix="admission-", dir=os.environ.get("TMPDIR", str(Path.home()))
        )
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.path = self.root / "cohort"
        self.output = self.root / "run"
        self.addCleanup(patch.stopall)
        patch.object(M, "COHORT_PATH", self.path).start()
        patch.object(M, "revalidate_context").start()
        patch.object(
            M.historical, "generate_solvable_task_suite", return_value=self.suite
        ).start()

    def publish(self, build=None, check=None):
        return M._publish_cohort(
            self.path,
            self.context,
            build or (lambda: self.seal),
            check or (lambda: None),
        )

    def test_start_precedes_build_and_seal_is_last(self):
        def build():
            self.assertEqual({p.name for p in self.path.iterdir()}, {"STARTED.json"})
            return self.seal

        self.publish(build)
        self.assertEqual({p.name for p in self.path.iterdir()}, M.NAMES)
        sealed = M.load_seal(self.path)
        self.assertEqual(sealed.manifest, self.seal)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o700)
        self.assertTrue(
            all(p.stat().st_mode & 0o777 == 0o600 for p in self.path.iterdir())
        )

    def test_occupied_slot_not_adopted_or_resumed(self):
        self.publish()
        with (
            patch.object(M, "verify_qualification") as verify,
            self.assertRaisesRegex(ValueError, "occupied"),
        ):
            M.seal_cohort(self.root / "nonexistent", "f" * 64)
        verify.assert_not_called()

    def test_failed_build_retained_and_rejected(self):
        with self.assertRaisesRegex(ValueError, "solver failed"):
            self.publish(
                build=lambda: (_ for _ in ()).throw(ValueError("solver failed"))
            )
        self.assertEqual(
            {p.name for p in self.path.iterdir()}, {"STARTED.json", "FAILURE.json"}
        )
        with self.assertRaises(ValueError):
            M.load_seal(self.path)

    def test_final_marker_uncertainty_has_no_countermand_failure(self):
        original = M.mechanics._exclusive_create_exact

        def create(parent, name, *a, **kw):
            if name == "SEALED.json":
                raise OSError("uncertain final create")
            return original(parent, name, *a, **kw)

        with (
            patch.object(M.mechanics, "_exclusive_create_exact", side_effect=create),
            self.assertRaises(M.storage.PublicationUncertain),
        ):
            self.publish()
        self.assertFalse((self.path / "FAILURE.json").exists())
        self.assertTrue((self.path / "preregistration.json").exists())

    def test_late_entry_after_final_marker_is_uncertain(self):
        def check():
            if (self.path / "SEALED.json").exists():
                (self.path / "extra").touch()

        with self.assertRaises(M.storage.PublicationUncertain):
            self.publish(check=check)
        self.assertFalse((self.path / "FAILURE.json").exists())

    def test_loader_late_extra_file_rejected(self):
        self.publish()

        def generate(*a, **kw):
            (self.path / "extra").touch()
            return self.suite

        with (
            patch.object(
                M.historical, "generate_solvable_task_suite", side_effect=generate
            ),
            self.assertRaises(ValueError),
        ):
            M.load_seal(self.path)

    def test_partial_or_malformed_transaction_markers_never_generate(self):
        self.publish()
        for name in ("STARTED.json", "SEALED.json"):
            path = self.path / name
            original = path.read_bytes()
            for raw in (b"", b"{}\n", b"{malformed\n"):
                path.write_bytes(raw)
                with (
                    patch.object(
                        M.historical, "generate_solvable_task_suite"
                    ) as generator,
                    patch.object(M, "revalidate_context") as context,
                    self.subTest(name=name, raw=raw),
                    self.assertRaises((ValueError, KeyError, TypeError)),
                ):
                    M.load_seal(self.path)
                generator.assert_not_called()
                context.assert_not_called()
                path.write_bytes(original)

    def test_rehashed_marker_linkage_lies_never_generate(self):
        self.publish()
        for name, key, changed in (
            ("STARTED.json", "status", "fake"),
            ("STARTED.json", "admission_context", {}),
            ("SEALED.json", "seal_sha256", "f" * 64),
            ("SEALED.json", "started_sha256", "f" * 64),
            ("SEALED.json", "seal_byte_count", 1),
        ):
            path = self.path / name
            original = path.read_bytes()
            value = M.core.parse_canonical(original)
            value[key] = changed
            path.write_bytes(M.canonical(rehash(value)))
            with (
                patch.object(M.historical, "generate_solvable_task_suite") as generator,
                self.subTest(name=name, key=key),
                self.assertRaises(ValueError),
            ):
                M.load_seal(self.path)
            generator.assert_not_called()
            path.write_bytes(original)

    def test_symlink_hardlink_and_extra_files_rejected_before_generator(self):
        for kind in ("symlink", "hardlink", "extra"):
            self.path = self.root / kind
            with patch.object(M, "COHORT_PATH", self.path):
                self.publish()
                path = self.path / "preregistration.json"
                saved = self.root / (kind + "-saved")
                if kind != "extra":
                    path.rename(saved)
                    if kind == "symlink":
                        path.symlink_to(saved)
                    else:
                        os.link(saved, path)
                else:
                    (self.path / "extra").touch()
                with (
                    patch.object(
                        M.historical, "generate_solvable_task_suite"
                    ) as generator,
                    self.subTest(kind=kind),
                    self.assertRaises((ValueError, RuntimeError)),
                ):
                    M.load_seal(self.path)
                generator.assert_not_called()

    def test_snapshot_and_bytes_are_immutable_and_late_changes_rejected(self):
        self.publish()
        sealed = M.load_seal(self.path)
        with self.assertRaises(AttributeError):
            sealed._path = self.output
        with self.assertRaises(TypeError):
            sealed._raw["preregistration.json"] = b"{}\n"
        detached = sealed.manifest
        detached["development_execution_authorized"] = True
        self.assertFalse(sealed.manifest["development_execution_authorized"])
        (self.path / "extra").touch()
        with self.assertRaises(ValueError):
            sealed.revalidate()
        with self.assertRaises(TypeError):
            M.SealedInputs(b"{}\n")

    def test_review_candidate_has_no_authority_and_closes_all_bindings(self):
        self.publish()
        sealed = M.load_seal(self.path)
        with patch.object(M.public, "_output", side_effect=lambda p: Path(p)):
            value = M.candidate(sealed, self.output)
            self.assertEqual(
                M.validate_candidate(
                    M.canonical(value),
                    sealed,
                    self.output,
                    value["deterministic_digest"],
                ),
                value,
            )
            for field, changed in (
                ("expected_cell_count", 384),
                ("development_execution_authorized", True),
                ("seal_digest", "f" * 64),
                ("output_path", str(self.root / "other")),
                ("schema_version", M.DOMAIN + "/authorization"),
            ):
                bad = copy.deepcopy(value)
                bad[field] = changed
                bad = rehash(bad)
                with self.subTest(field=field), self.assertRaises(ValueError):
                    M.validate_candidate(
                        M.canonical(bad),
                        sealed,
                        self.output,
                        bad["deterministic_digest"],
                    )
            with self.assertRaises(ValueError):
                M.validate_candidate(M.canonical(value), sealed, self.output, "f" * 64)
        self.assertEqual(value["scope"], "REVIEW_ONLY_NOT_EXECUTABLE")
        self.assertFalse(value["development_execution_authorized"])
        self.assertFalse(value["authorization_consumption_implemented"])

    def test_candidate_last_context_check_cannot_hide_seal_mutation(self):
        self.publish()
        sealed = M.load_seal(self.path)
        calls = 0

        def check(c):
            nonlocal calls
            calls += 1
            if calls == 2:
                (self.path / "extra").touch()

        with (
            patch.object(M.public, "_output", side_effect=lambda p: Path(p)),
            patch.object(M, "revalidate_context", side_effect=check),
            self.assertRaises(ValueError),
        ):
            M.candidate(sealed, self.output)

    def test_candidate_does_not_accept_raw_or_public_inputs(self):
        for value in (self.seal, M.k.public_inputs(), object()):
            with self.assertRaises(ValueError):
                M.candidate(value, self.output)

    def test_wrong_qualification_digest_does_not_open_public_run(self):
        path = self.root / "receipt.json"
        path.write_bytes(
            M.canonical(
                M.core.with_digest(
                    dict(schema_version=M.DOMAIN + "/admission-qualification")
                )
            )
        )
        with patch.object(M, "qualify") as qualify, self.assertRaises(ValueError):
            M.verify_qualification(path, "f" * 64)
        qualify.assert_not_called()

    def test_qualifier_late_input_change_is_rejected(self):
        from unittest.mock import Mock

        publication, snapshot = Mock(), Mock()
        publication.revalidate.side_effect = ValueError("late public closure")
        context = {"public_evidence": {"summary_digest": "f" * 64}}
        with (
            patch.object(M.public, "_output", side_effect=lambda p: Path(p)),
            patch.object(M.public.pub, "inspect", return_value=publication),
            patch.object(M.core.FileSnapshot, "capture", return_value=snapshot),
            patch.object(M, "context", return_value=context),
            patch.object(
                M.public, "verify", return_value={"deterministic_digest": "f" * 64}
            ),
            patch.object(M, "negative_checks", return_value={}),
            self.assertRaisesRegex(ValueError, "late public closure"),
        ):
            M.qualify(self.path, self.output)
        snapshot.revalidate.assert_called_once()


class AdmissionCliTests(unittest.TestCase):
    def test_outside_checkout_selftest_and_no_ignored_overrides(self):
        environment = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
        script = ROOT / M.SCRIPT
        cohort = ROOT / "artifacts/work/feedback-budget-development-cohort-v6"
        before = cohort.stat() if cohort.exists() else None
        for args, code in (
            (["--self-test"], 0),
            (["--self-test", "--expected-digest", "f" * 64], 1),
            (["--self-t"], 2),
            (["--run"], 2),
            (["--seal-cohort"], 1),
        ):
            result = subprocess.run(
                [sys.executable, "-P", "-B", str(script), *args],
                cwd=Path.home(),
                env=environment,
                capture_output=True,
            )
            with self.subTest(args=args):
                self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        self.assertEqual(cohort.stat() if cohort.exists() else None, before)


if __name__ == "__main__":
    unittest.main()
