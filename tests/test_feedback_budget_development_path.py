"""New-domain public-path checks; synthetic storage is not execution evidence."""

from __future__ import annotations

import copy
import importlib.util
from itertools import product
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "feedback_budget_development_path_tested",
    ROOT / "scripts/run_feedback_budget_development_fixture.py",
)
assert SPEC is not None and SPEC.loader is not None
R = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(R)
K, A, P = R.k, R.analysis, R.pub


def rehash(value):
    return K.core.with_digest(
        {key: item for key, item in value.items() if key != "deterministic_digest"}
    )


def fake_binding(inputs):
    return K.binding(inputs, {"execution_revision": "f" * 40}, {}, {})


def fake_rows(inputs, binding):
    return [
        K.core.with_digest(
            dict(
                schema_version=K.DOMAIN + "/record",
                **cell,
                run_binding_digest=binding["deterministic_digest"],
                search_record={
                    "run_identity": K.q.build_search_run_identity(
                        **inputs.arguments(cell)
                    )
                },
            )
        )
        for cell in inputs.cells
    ]


class KernelIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = K.public_inputs()
        cls.binding = fake_binding(cls.inputs)
        cls.rows = fake_rows(cls.inputs, cls.binding)

    def test_fixed_inputs_never_generate_or_search(self):
        with patch.object(
            K.q, "run_countdown_track_a_search", side_effect=AssertionError("search")
        ):
            manifest = K.public_inputs().manifest
        self.assertEqual(manifest["tasks"], K.q.public_manifest()["full_shape_tasks"])
        self.assertEqual(manifest["source_multiset_count"], 1)
        self.assertEqual(
            (len(manifest["cells"]), len({c["cell_id"] for c in manifest["cells"]})),
            (192, 192),
        )
        self.assertEqual(manifest["schedule_digest"], K.digest(manifest["cells"]))
        self.assertFalse(manifest["development_execution_authorized"])

    def test_all_cell_keys_bind_contract_task_set_specs_and_fixture_mode(self):
        m = self.inputs.manifest
        for cell, coord in zip(self.inputs.cells, K.COORDINATES):
            key = cell["cell_key"]
            self.assertEqual(
                tuple(key[f] for f in ("task_slot", "budget", "scale", "seed")), coord
            )
            self.assertEqual(key["schema_version"], K.DOMAIN + "/cell-key")
            self.assertEqual(key["execution_mode"], K.MODE)
            self.assertEqual(key["contract_digest"], m["contract_digest"])
            self.assertEqual(key["task_set_digest"], K.digest(m["tasks"]))
            self.assertEqual(
                key["budget_spec_digest"], K.digest(K.q.profile(coord[1]).to_dict())
            )
            self.assertEqual(
                key["method_spec_digest"], K.digest(K.q.method(coord[2]).to_dict())
            )
            self.assertEqual(
                key["proposal_spec_digest"], K.digest(K.q.PROPOSAL.to_dict())
            )

    def test_fixture_accessors_do_not_alias_mutable_inputs(self):
        changed = self.inputs.manifest
        changed["tasks"][0]["target"] = 999
        changed["cells"][0]["cell_key"]["scale"] = 64
        self.assertEqual(self.inputs.arguments(self.inputs.cells[0])["task"].target, 1)
        with self.assertRaises(AttributeError):
            self.inputs._raw = K.canonical(changed)

    def test_rehashed_alternate_manifest_is_not_admitted(self):
        mutations = [
            lambda m: m.update(development_execution_authorized=True),
            lambda m: m.update(execution_mode="authorized_development"),
            lambda m: m.update(schema_version=K.DOMAIN + "/cohort"),
            lambda m: m["tasks"][0].update(target=999),
            lambda m: m["cells"].reverse(),
            lambda m: m.update(unknown=True),
        ]
        for mutate in mutations:
            value = self.inputs.manifest
            mutate(value)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                K.FixtureInputs(K.canonical(rehash(value)))

    def test_candidates_and_old_authorizations_cannot_be_loaded(self):
        candidates = [
            K.contract.build_contract(),
            K.contract.build_schedule_candidate(K.contract.synthetic_identities()),
        ]
        for path in (
            "countdown_track_a_canary_v2_execution_authorization.json",
            "countdown_thompson_diagnostic_v1_execution_authorization.json",
            "countdown_thompson_dense_scale_v5_execution_authorization.json",
        ):
            candidates.append(
                K.core.parse_canonical(
                    (ROOT / "docs/preregistrations" / path).read_bytes()
                )
            )
        for value in candidates:
            with self.assertRaises(ValueError):
                K.FixtureInputs(K.canonical(value))

    def test_old_384_runner_rejects_new_manifest_binding_and_records(self):
        from qmc_bmgs.experiments import countdown_thompson_dense_scale_runner as old

        for value in (self.inputs.manifest, self.binding, self.rows[0]):
            for fixture in (False, True):
                with self.assertRaises(ValueError):
                    old.validate_authorization(K.canonical(value), fixture=fixture)

    def test_noncanonical_or_duplicate_json_cannot_be_loaded(self):
        for raw in (b'{"a":1,"a":1}\n', b'{"x":NaN}\n', b"{}", b"{}\n "):
            with self.assertRaises(ValueError):
                K.FixtureInputs(raw)

    def test_cell_numeric_alias_domain_and_identity_rejected_before_search(self):
        for field, value in (
            ("cell_index", True),
            ("cell_index", -1),
            ("cell_index", 192),
            ("cell_id", "a" * 64),
        ):
            cell = self.inputs.cells[0]
            cell[field] = value
            with (
                patch.object(K.q, "run_countdown_track_a_search") as search,
                self.assertRaises(ValueError),
            ):
                K.record(self.inputs, cell, self.binding)
            search.assert_not_called()

    def rejects_before_replay(self, rows, binding=None):
        with (
            patch.object(K.q, "replay_countdown_track_a_search_bytes") as replay,
            self.assertRaises(ValueError),
        ):
            K.replay_matrix(self.inputs, rows, binding or self.binding)
        replay.assert_not_called()

    def test_missing_duplicate_and_reordered_final_cell_rejected_before_any_replay(
        self,
    ):
        self.rejects_before_replay(self.rows[:-1])
        self.rejects_before_replay(self.rows + [self.rows[0]])
        self.rejects_before_replay(self.rows[:-1] + [self.rows[0]])
        rows = list(self.rows)
        rows[-1], rows[-2] = rows[-2], rows[-1]
        self.rejects_before_replay(rows)

    def test_every_outer_and_run_identity_field_rehashed_tamper_rejected(self):
        mutations = [
            lambda r: r.update(schema_version="old/public/record"),
            lambda r: r.update(cell_index=True),
            lambda r: r.update(unexpected=True),
            lambda r: r.update(run_binding_digest="a" * 64),
            lambda r: r["cell_key"].update(budget=256),
            lambda r: r["search_record"]["run_identity"].update(exploration_seed=0),
            lambda r: r["cell_key"].update(execution_mode="authorized_development"),
        ]
        for mutate in mutations:
            rows = copy.deepcopy(self.rows)
            mutate(rows[-1])
            rows[-1] = rehash(rows[-1])
            self.rejects_before_replay(rows)

    def test_binding_cannot_self_promote_rekey_schedule_or_add_fields(self):
        for field, value in (
            ("schema_version", "old384"),
            ("development_execution_authorized", True),
            ("expected_cell_count", True),
            ("schedule_digest", "a" * 64),
            ("execution_mode", "authorized_development"),
            ("unknown", False),
        ):
            binding = rehash({**self.binding, field: value})
            self.rejects_before_replay(self.rows, binding)

    def test_source_change_rebinds_all_records(self):
        binding = K.binding(self.inputs, {"execution_revision": "e" * 40}, {}, {})
        self.assertNotEqual(
            binding["deterministic_digest"], self.binding["deterministic_digest"]
        )
        self.rejects_before_replay(self.rows, binding)

    def test_fixture_cli_has_no_development_or_override_options(self):
        for flag in (
            "--run",
            "--authorize",
            "--authorization",
            "--generate",
            "--cohort",
            "--task",
            "--seed",
            "--resume",
        ):
            process = subprocess.run(
                [sys.executable, "-P", "-B", str(ROOT / R.SCRIPT), flag],
                cwd="/tmp",
                capture_output=True,
                env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
            )
            self.assertNotEqual(process.returncode, 0, flag)


class FactorialArithmeticTests(unittest.TestCase):
    def reduce(self, rows=None, support=None):
        return A.factorial(
            rows or [[[0, 0, 0, 0] for _ in range(4)] for _ in range(12)],
            support or [[True] * 4 for _ in range(12)],
        )

    def test_all_nine_legal_patterns_retain_all_sixteen_rows(self):
        for p in product((0, 1), repeat=4):
            rows = [[list(p) for _ in range(4)] for _ in range(12)]
            if p[2] < p[0] or p[3] < p[1]:
                with self.assertRaisesRegex(ValueError, "forbidden"):
                    self.reduce(rows)
                continue
            result = self.reduce(rows)
            self.assertEqual(result["arm_success_counts"], [48 * b for b in p])
            self.assertEqual(
                result["interaction"], A.ratio(p[3] - p[2] - p[1] + p[0], 1)
            )
            self.assertEqual(len(result["blocks"]), 48)
            self.assertEqual(len(result["task_rows"]), 12)
            self.assertEqual(len(result["leave_one_task_out"]), 12)
            self.assertEqual(
                sum(r["forbidden_by_prefix"] for r in result["pattern_counts"]), 7
            )
            self.assertEqual(sum(r["count"] for r in result["pattern_counts"]), 48)
            self.assertTrue(
                all(
                    r["count"] == 0
                    for r in result["pattern_counts"]
                    if r["forbidden_by_prefix"]
                )
            )

    def positive(self):
        rows = [[[0, 0, 0, 0] for _ in range(4)] for _ in range(12)]
        rows[0][0] = rows[1][0] = [0, 0, 0, 1]
        return rows

    def test_two_task_supported_rescues_pass_math_not_authority(self):
        result = self.reduce(self.positive())
        self.assertTrue(result["screen_conjunction"])
        self.assertEqual(result["interaction"], {"numerator": 1, "denominator": 24})
        self.assertIsNone(result["scientific_decision"])
        self.assertFalse(result["integrity_assessed_here"])
        self.assertFalse(result["execution_authorized"])
        self.assertEqual(result["leave_one_task_out"][0]["interaction"], A.ratio(1, 44))

    def test_unsupported_rescue_fails_even_when_all_numerical_gates_pass(self):
        support = [[True] * 4 for _ in range(12)]
        support[1][0] = False
        result = self.reduce(self.positive(), support)
        self.assertFalse(result["screen_conjunction"])
        self.assertFalse(
            result["screen_components"]["all_high_new_successes_feedback_supported"]
        )

    def test_single_task_rescues_fail_breadth_and_leave_one_out(self):
        rows = self.positive()
        rows[1][0] = [0, 0, 0, 0]
        rows[0][1] = [0, 0, 0, 1]
        result = self.reduce(rows)
        self.assertFalse(result["screen_components"]["high_rescues_on_two_tasks"])
        self.assertFalse(
            result["screen_components"]["leave_one_task_out_strictly_positive"]
        )

    def test_disappearing_harm_is_not_useful_high_uplift(self):
        result = self.reduce([[[1, 0, 1, 1] for _ in range(4)] for _ in range(12)])
        self.assertEqual(result["interaction"], A.ratio(1, 1))
        self.assertEqual(result["high_uplift"], A.ratio(0, 1))
        self.assertFalse(result["screen_conjunction"])

    def test_losses_stay_in_denominator_and_block_the_screen(self):
        rows = self.positive()
        rows[2][0] = [0, 0, 1, 0]
        result = self.reduce(rows)
        self.assertEqual(result["lost_success_counts"], [0, 1])
        self.assertEqual(result["net_success_counts"], [0, 1])
        self.assertEqual(result["arm_denominator"], 48)
        self.assertFalse(result["screen_conjunction"])

    def test_malformed_numeric_support_and_missingness_are_not_zero(self):
        for bit in (True, 1.0, -1, 2, None):
            rows = self.positive()
            rows[11][3][0] = bit
            with self.assertRaises(ValueError):
                self.reduce(rows)
        for rows, support in (
            (self.positive()[:-1], [[True] * 4] * 12),
            (self.positive(), [[1] * 4] * 12),
            (self.positive(), [[True] * 3] * 12),
        ):
            with self.assertRaises(ValueError):
                A.factorial(rows, support)


class ActualPublicKernelTests(unittest.TestCase):
    """Real public search/replay, not source-qualified publication evidence."""

    @classmethod
    def setUpClass(cls):
        cls.inputs = K.public_inputs()
        cls.binding = fake_binding(cls.inputs)
        cls.rows = [
            K.record(cls.inputs, cell, cls.binding) for cell in cls.inputs.cells
        ]
        cls.records, cls.integrity = K.replay_matrix(cls.inputs, cls.rows, cls.binding)
        cls.stages = []
        cls.reduced = A.reduce_matrix(cls.inputs, cls.records, cls.stages.append)

    def test_complete_replay_prefixes_and_unchanged_search_records(self):
        self.assertEqual(self.integrity["replayed_trace_count"], 192)
        self.assertEqual(len(self.integrity["budget_prefix_checks"]), 96)
        for p in self.integrity["budget_prefix_checks"]:
            self.assertGreaterEqual(
                p["high_terminal_count"], p["low_terminal_count"] + 1
            )
            self.assertTrue(p["current_next_completed_first"])
        self.assertEqual(self.stages, list(A.STAGES[3:]))

    def test_reduction_keeps_every_cell_pair_block_task_and_terminal(self):
        r = self.reduced
        self.assertEqual(len(r["mechanism"]["pairs"]), 96)
        self.assertEqual(len(r["mechanism"]["extensions"]), 48)
        self.assertEqual(len(r["terminal_errors"]["cells"]), 192)
        self.assertEqual(len(r["terminal_errors"]["blocks"]), 48)
        self.assertEqual(len(r["terminal_errors"]["task_rows"]), 12)
        self.assertEqual(len(r["exact_success"]["cells"]), 192)
        for error, success in zip(
            r["terminal_errors"]["cells"], r["exact_success"]["cells"]
        ):
            self.assertTrue(error["errors"])
            self.assertEqual(len(error["errors"]), len(error["values"]))
            self.assertEqual(
                len(error["errors"]), len(success["terminal_success_vector"])
            )
            hit = success["first_hit_observation_index"]
            self.assertEqual(
                hit, next((i for i, e in enumerate(error["errors"]) if e == 0), None)
            )
        self.assertEqual(r["mechanism_digest"], K.digest(r["mechanism"]))
        self.assertIsNone(r["scientific_decision"])

    def test_prefix_comparison_does_not_strip_payload_hash_or_charge(self):
        low, high = self.records[0, 256, 0, 8192], self.records[0, 512, 0, 8192]
        for field, value in (
            ("event_digest", "a" * 64),
            ("payload", {}),
            ("charge", None),
        ):
            altered = copy.deepcopy(low)
            event = next(
                e for e in altered["events"] if e["kind"] == "selection_committed"
            )
            event[field] = value
            with self.assertRaisesRegex(ValueError, "prefix"):
                K.prefix_pair(altered, high)

    def test_prefix_completion_guarantee_is_not_satisfied_by_equal_histories(self):
        low = self.records[0, 256, 0, 8192]
        with self.assertRaisesRegex(ValueError, "completion"):
            K.prefix_pair(low, low)

    def test_rehashed_lie_cannot_replace_two_stage_replay(self):
        rows = copy.deepcopy(self.rows)
        trace = rows[0]["search_record"]
        trace["events"][0]["payload"]["invented"] = True
        previous = "0" * 64
        for event in trace["events"]:
            event["previous_event_digest"] = previous
            event["event_digest"] = K.digest(
                {k: v for k, v in event.items() if k != "event_digest"}
            )
            previous = event["event_digest"]
        trace["final_event_digest"] = previous
        rows[0]["search_record"] = rehash(trace)
        rows[0] = rehash(rows[0])
        with self.assertRaises(ValueError):
            K.replay_matrix(self.inputs, rows, self.binding)

    def test_mechanism_projection_does_not_open_outcome_fields(self):
        class Unreadable:
            def __getitem__(self, key):
                raise AssertionError("outcome opened by mechanism")

        coord = (0, 512, 16, 8192)
        original = self.records[coord]
        poisoned = copy.deepcopy(original)
        poisoned["summary"] = Unreadable()
        for event in poisoned["events"]:
            if event["kind"] == "terminal_verified":
                event["payload"]["verification"] = Unreadable()
            elif event["kind"] == "search_finished":
                event["payload"] = Unreadable()
        cell = self.inputs.cells[list(K.COORDINATES).index(coord)]
        selected = A.SimpleNamespace(
            cell_id=cell["cell_id"],
            task_fingerprint=cell["cell_key"]["task_fingerprint"],
            exploration_seed=8192,
            terminal_value_scale=16,
        )
        self.assertEqual(
            A.prior.project_mechanism_cell(selected, original),
            A.prior.project_mechanism_cell(selected, poisoned),
        )
        limits = K.q.profile(512).to_dict()["budget"]
        self.assertEqual(
            A.project_opportunity(original, limits),
            A.project_opportunity(poisoned, limits),
        )

    def test_backup_support_and_divergence_timing_are_explicit(self):
        for row in self.reduced["mechanism"]["pairs"]:
            if row["first_action_divergence"] is None:
                self.assertEqual(row["opportunity_bin"], "no_divergence")
            else:
                different = any(
                    r["baseline_applied_value"].hex() != r["scaled_applied_value"].hex()
                    for r in row["shared_prefix_backup_values"]
                )
                self.assertIs(row["feedback_informed"], different)
                self.assertEqual(
                    row["first_scale_dependent_backup"] is not None, different
                )
                for window in row["divergence_window"].values():
                    self.assertGreater(
                        window["remaining_before_step_charge"]["legal_action_scores"],
                        window["remaining_after_step_charge"]["legal_action_scores"],
                    )
        for extension in self.reduced["mechanism"]["extensions"]:
            for continuation in extension["observed_same_scale_continuations"]:
                if continuation["low_divergent_trajectory_unfinished"]:
                    self.assertTrue(continuation["same_trajectory_completed_high"])

    def test_missing_record_invalidates_before_mechanism(self):
        rows = self.rows[:-1]
        with patch.object(A, "reduce_matrix") as reduce, self.assertRaises(ValueError):
            R.reduce_rows(self.inputs, rows, self.binding)
        reduce.assert_not_called()

    def test_missing_terminal_invalidates_instead_of_finite_only_reduction(self):
        trace = copy.deepcopy(self.records[0, 256, 0, 8192])
        trace["events"] = [
            e
            for e in trace["events"]
            if e["kind"] not in ("terminal_verified", "trajectory_backed_up")
        ]
        with self.assertRaisesRegex(ValueError, "terminal"):
            A.prior._error_cell(trace)


class NewDomainPublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binding = fake_binding(K.public_inputs())

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.output = self.root / "new192"

    def tearDown(self):
        self.temp.cleanup()

    def row(self, index):
        key = dict(
            schema_version=K.DOMAIN + "/cell-key",
            execution_mode=K.MODE,
            experiment_id=K.FIXTURE_ID,
            synthetic_index=index,
        )
        return K.core.with_digest(
            dict(
                schema_version=K.DOMAIN + "/record",
                cell_index=index,
                cell_id=K.digest(key),
                cell_key=key,
                run_binding_digest=self.binding["deterministic_digest"],
                search_record={"synthetic_not_replay_evidence": True},
            )
        )

    def receipt(self):
        return K.core.with_digest(
            dict(
                schema_version=K.DOMAIN + "/execution-receipt",
                execution_mode=K.MODE,
                run_binding_digest=self.binding["deterministic_digest"],
                development_execution_authorized=False,
                synthetic_only=True,
            )
        )

    def action(self, emit):
        for i in range(192):
            emit(i, self.row(i))
        return self.receipt()

    def publish(self, action=None, check=None, **kwargs):
        return P.publish(
            self.output,
            self.binding,
            action or self.action,
            check or (lambda: None),
            **kwargs,
        )

    def test_195_durable_files_start_first_commit_last_and_independent_storage_closure(
        self,
    ):
        events = []

        def hook(event, details):
            if event == "after_file_durable":
                events.append(details["name"])

        result = self.publish(_event_hook=hook)
        self.assertEqual(
            (len(events), events[0], events[-1]), (195, "STARTED.json", "COMMIT.json")
        )
        inspection = P.inspect(self.output)
        self.assertEqual(inspection.commit, result)
        self.assertEqual(inspection.binding, self.binding)
        self.assertEqual(inspection.rows, [self.row(i) for i in range(192)])
        self.assertEqual(inspection.receipt, self.receipt())
        inspection.revalidate()

    def test_existing_empty_or_complete_output_is_never_reused(self):
        self.output.mkdir()
        with self.assertRaises(FileExistsError):
            self.publish(lambda emit: self.fail("occupied output executed"))
        self.output = self.root / "complete"
        self.publish()
        before = (self.output / "COMMIT.json").read_bytes()
        with self.assertRaises(FileExistsError):
            self.publish(lambda emit: self.fail("committed output executed"))
        self.assertEqual(before, (self.output / "COMMIT.json").read_bytes())

    def test_preflight_failure_does_not_create_output_or_call_action(self):
        def fail():
            raise ValueError("preflight")

        with self.assertRaisesRegex(ValueError, "preflight"):
            self.publish(lambda emit: self.fail("action ran"), check=fail)
        self.assertFalse(self.output.exists())

    def test_partial_failure_is_retained_without_commit_or_resume(self):
        def action(emit):
            emit(0, self.row(0))
            raise ValueError("interrupted")

        with self.assertRaisesRegex(ValueError, "interrupted"):
            self.publish(action)
        self.assertEqual(
            set(p.name for p in self.output.iterdir()),
            {"STARTED.json", "cell-000.json", "FAILURE.json"},
        )
        self.assertEqual(
            P.parse((self.output / "FAILURE.json").read_bytes())["status"],
            "INVALID_ANALYSIS",
        )
        with self.assertRaises(ValueError):
            P.inspect(self.output)
        with self.assertRaises(FileExistsError):
            self.publish()

    def test_late_environment_failure_is_retained_as_invalid_not_scientific_stop(self):
        checks = []

        def check():
            checks.append(1)
            if len(checks) == 3:
                raise ValueError("source changed")

        with self.assertRaisesRegex(ValueError, "source changed"):
            self.publish(check=check)
        self.assertTrue((self.output / "cell-191.json").exists())
        self.assertFalse((self.output / "COMMIT.json").exists())
        self.assertTrue((self.output / "FAILURE.json").exists())

    def test_incomplete_or_out_of_order_matrix_cannot_commit(self):
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.publish(lambda emit: self.receipt())
        self.output = self.root / "wrong_order"
        with self.assertRaisesRegex(ValueError, "order"):
            self.publish(lambda emit: emit(1, self.row(1)))
        self.assertFalse((self.output / "COMMIT.json").exists())

    def test_old_or_promoted_binding_fails_before_directory_creation(self):
        for field, value in (
            ("schema_version", P.storage.DOMAIN + "/binding"),
            ("development_execution_authorized", True),
            ("execution_mode", "production"),
            ("unknown", True),
            ("expected_cell_count", True),
        ):
            with self.assertRaises(ValueError):
                P.publish(
                    self.output,
                    rehash({**self.binding, field: value}),
                    self.action,
                    lambda: None,
                )
            self.assertFalse(self.output.exists())

    def test_record_domains_binding_and_boolean_aliases_are_rejected(self):
        for field, value in (
            ("schema_version", P.storage.DOMAIN + "/record"),
            ("run_binding_digest", "a" * 64),
            ("cell_index", True),
            ("extra", True),
        ):
            row = rehash({**self.row(0), field: value})
            with self.assertRaises(ValueError):
                P.row_bytes(0, row, self.binding)

    def test_extra_entry_before_or_after_inspection_invalidates_closure(self):
        self.publish()
        inspected = P.inspect(self.output)
        (self.output / "late.json").write_bytes(b"{}\n")
        with self.assertRaisesRegex(ValueError, "closure"):
            inspected.revalidate()
        with self.assertRaisesRegex(ValueError, "closure"):
            P.inspect(self.output)

    def test_rehashed_cell_tamper_does_not_match_commit_bytes(self):
        self.publish()
        path = self.output / "cell-191.json"
        row = P.parse(path.read_bytes())
        row["search_record"]["changed"] = True
        path.write_bytes(K.canonical(rehash(row)))
        with self.assertRaisesRegex(ValueError, "commit"):
            P.inspect(self.output)

    def test_symlink_and_hardlink_cells_are_not_adopted(self):
        self.publish()
        path = self.output / "cell-000.json"
        saved = self.root / "cell"
        path.rename(saved)
        path.symlink_to(saved)
        with self.assertRaises((ValueError, P.mechanics.RegularFilePublicationV2Error)):
            P.inspect(self.output)
        path.unlink()
        os.link(saved, path)
        with self.assertRaises((ValueError, P.mechanics.RegularFilePublicationV2Error)):
            P.inspect(self.output)

    def test_old_public_inspector_rejects_new_domain_and_new_rejects_old(self):
        self.publish()
        with self.assertRaises(ValueError):
            P.storage.inspect(self.output)
        started = P.parse((self.output / "STARTED.json").read_bytes())
        started["schema_version"] = P.storage.DOMAIN + "/started"
        (self.output / "STARTED.json").write_bytes(K.canonical(rehash(started)))
        with self.assertRaisesRegex(ValueError, "domain"):
            P.inspect(self.output)

    def test_postcommit_uncertainty_never_writes_a_countermanding_failure(self):
        original = P.storage._observe

        def observe(parent, names, **kwargs):
            value = original(parent, names, **kwargs)
            if set(names) == P.COMPLETE_NAMES:
                raise OSError("uncertain postcommit closure")
            return value

        with (
            patch.object(P.storage, "_observe", side_effect=observe),
            self.assertRaises(P.PublicationUncertain),
        ):
            self.publish()
        self.assertTrue((self.output / "COMMIT.json").exists())
        self.assertFalse((self.output / "FAILURE.json").exists())

    def test_analysis_summary_cannot_claim_production_or_overwrite(self):
        value = K.core.with_digest(
            dict(
                schema_version=K.DOMAIN + "/analysis",
                execution_mode=K.MODE,
                scientific_decision=None,
                development_execution_authorized=False,
            )
        )
        path = self.root / "summary.json"
        P.publish_summary(path, value, lambda: None)
        with self.assertRaises(P.mechanics.RegularFilePublicationV2Error):
            P.publish_summary(path, value, lambda: None)
        for field, changed in (
            ("scientific_decision", "READY"),
            ("development_execution_authorized", True),
            ("execution_mode", "production"),
        ):
            with self.assertRaises(ValueError):
                P.publish_summary(
                    self.root / "other.json",
                    rehash({**value, field: changed}),
                    lambda: None,
                )

    def test_independent_analyzer_revalidates_closure_after_its_last_reduction(self):
        self.publish()

        def late_reduce(*args):
            (self.output / "late.json").write_bytes(b"{}\n")
            return self.receipt()

        with (
            patch.object(R, "_output", side_effect=lambda p: p),
            patch.object(R, "attest", return_value=self.binding["source"]),
            patch.object(R, "runtime_receipt", return_value={}),
            patch.object(R, "qualify_baseline", return_value={}),
            patch.object(R, "reduce_rows", side_effect=late_reduce),
            patch.object(R, "check_environment"),
            self.assertRaisesRegex(ValueError, "closure"),
        ):
            R.analyze(self.output)


if __name__ == "__main__":
    unittest.main()
