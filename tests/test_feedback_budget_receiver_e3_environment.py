"""Synthetic fixed-E3 boundaries; not actual reconstruction or admission."""

from __future__ import annotations

import ast
from contextlib import ExitStack
import copy
import importlib.util
import inspect
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "receiver_e3_tested",
    ROOT / "scripts/check_feedback_budget_receiver_e3_environment.py",
)
assert SPEC is not None and SPEC.loader is not None
E = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = E
SPEC.loader.exec_module(E)
V, R, B, C, S = E.V, E.R, E.B, E.C, E.S


def read(relative):
    return E.parse((ROOT / relative).read_bytes())


class ReceiverE3Boundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prior = read(E.PRIOR)
        cls.original = read(B.ORIGINAL_CANDIDATE)

    def fixture(self):
        prior = copy.deepcopy(self.prior)
        old = prior["location_correspondence"]["current_locations"]
        now = copy.deepcopy(old)
        for row in now.values():
            for pair in row["identities"]:
                pair[0] = E.CURRENT_DEVICE
        return SimpleNamespace(
            prior=prior,
            old=old,
            now=now,
            chains=prior["location_correspondence"]["chains"],
        )

    def mapping(self, f):
        return E.correspondence(f.chains, f.old, f.now)

    def environment(self):
        return copy.deepcopy({k: self.original[k] for k in E.ENV_FIELDS})

    def test_direct_seventeen_chains_and_bundle_observation_only(self):
        f = self.fixture()
        result = self.mapping(f)
        self.assertEqual(
            [r["chain_count"] for r in result["epochs"].values()], [6, 3, 8]
        )
        self.assertEqual(len(result["original_chains"]), 11)
        self.assertEqual(len(result["prior_observation_chains"]), 6)
        bundle = next(
            r
            for r in result["prior_observation_chains"]
            if r["role"] == "old_bridge_bundle_current_only"
        )
        self.assertEqual(bundle["owner"]["path"], E.PRIOR)
        self.assertFalse(result["current_receiver_admitted"])
        self.assertFalse(result["physical_disk_identity_proven"])

    def test_old_e2_rule_still_rejects_e3(self):
        f = self.fixture()
        self.assertEqual(V.CURRENT_DEVICE, 16777234)
        V.correspondence(f.chains, f.old)
        with self.assertRaisesRegex(Exception, "exact epoch device"):
            V.correspondence(f.chains, f.now)

    def test_original_registry_missing_extra_reordered_and_relabelled(self):
        for change in (
            lambda f: f.chains.pop(),
            lambda f: f.chains.append(copy.deepcopy(f.chains[0])),
            lambda f: f.chains.reverse(),
            lambda f: f.chains[0].update(label="bundle-original"),
            lambda f: f.chains[0]["owner"].update(path="unreviewed"),
            lambda f: f.chains[0].update(historical_epoch="E2_observation"),
        ):
            with self.subTest(change=change):
                f = self.fixture()
                change(f)
                with self.assertRaises(Exception):
                    self.mapping(f)

    def test_closed_roles_for_both_observed_epochs(self):
        for which in ("old", "now"):
            for extra in (False, True):
                f = self.fixture()
                target = getattr(f, which)
                if extra:
                    target["invented"] = copy.deepcopy(target["cohort"])
                else:
                    del target["cohort"]
                with self.assertRaisesRegex(Exception, "six location roles"):
                    self.mapping(f)

    def test_exact_e3_device_no_wildcard_or_future_epoch(self):
        for device in (16777234, 16777233, 16777231, 16777235, True, 16777232.0):
            f = self.fixture()
            f.now["cohort"]["identities"][-1][0] = device
            with self.subTest(device=device), self.assertRaises(Exception):
                self.mapping(f)

    def test_prior_e2_device_must_remain_exact(self):
        f = self.fixture()
        f.old["cohort"]["identities"][-1][0] = E.CURRENT_DEVICE
        with self.assertRaisesRegex(Exception, "exact epoch device"):
            self.mapping(f)

    def test_original_epochs_checked_directly_not_via_e2(self):
        for index in (0, 3):
            f = self.fixture()
            f.chains[index]["historical"]["identities"][-1][1] += 1
            with self.assertRaisesRegex(Exception, "historical inode differs"):
                self.mapping(f)

    def test_e2_observational_inode_checked_for_all_six_roles(self):
        for role in V.LOCATIONS:
            f = self.fixture()
            f.old[role]["identities"][-1][1] += 1
            with self.subTest(role=role), self.assertRaises(Exception):
                self.mapping(f)

    def test_current_and_historical_shared_prefixes_checked(self):
        for which in ("old", "now"):
            f = self.fixture()
            getattr(f, which)["cohort"]["identities"][0][1] += 1
            with self.assertRaisesRegex(Exception, "shared prefix"):
                self.mapping(f)

    def test_full_path_component_plain_type_and_closed_schema(self):
        for change in (
            lambda r: r.update(path=r["path"] + "/"),
            lambda r: r["identities"].pop(),
            lambda r: r["identities"][-1].__setitem__(1, True),
            lambda r: r["identities"][-1].__setitem__(1, 1.0),
            lambda r: r.update(accepted=True),
        ):
            f = self.fixture()
            change(f.now["cohort"])
            with self.assertRaises(Exception):
                self.mapping(f)

    def test_mapping_is_detached_comparator_not_mutable_proof(self):
        f = self.fixture()
        result = self.mapping(f)
        f.now["cohort"]["identities"][-1][1] += 1
        self.assertNotEqual(f.now, result["current_locations"])
        self.assertFalse(hasattr(E, "admit"))
        self.assertFalse(hasattr(E, "run"))

    def prior_read(self, raw=None, source=None):
        item = SimpleNamespace(raw=raw or (ROOT / E.PRIOR).read_bytes())
        evidence = SimpleNamespace(file=Mock(return_value=item))
        source = source or {"frozen_inspector_source": self.prior["source"]}
        return evidence, item, source

    def test_prior_git_and_bytes_authenticated_before_parse(self):
        evidence, item, source = self.prior_read(b"{}\n")
        with (
            patch.object(R, "reviewed_file") as reviewed,
            patch.object(V, "inspection_shape") as parser,
        ):
            with self.assertRaisesRegex(Exception, "pinned E2 observation bytes"):
                E.prior_observation(evidence, source)
            reviewed.assert_called_once_with(item, E.BASE)
            parser.assert_not_called()

    def test_prior_git_failure_prevents_parse(self):
        evidence, _, source = self.prior_read()
        with (
            patch.object(R, "reviewed_file", side_effect=ValueError("Git drift")),
            patch.object(V, "inspection_shape") as parser,
        ):
            with self.assertRaisesRegex(Exception, "Git drift"):
                E.prior_observation(evidence, source)
            parser.assert_not_called()

    def test_prior_exact_receipt_and_source_linkage(self):
        evidence, _, source = self.prior_read()
        with patch.object(R, "reviewed_file"):
            self.assertEqual(E.prior_observation(evidence, source), self.prior)
            source = copy.deepcopy(source)
            source["frozen_inspector_source"]["implementation_revision"] = "0" * 40
            with self.assertRaisesRegex(Exception, "observation source differs"):
                E.prior_observation(evidence, source)

    def test_exact_three_file_source_closure(self):
        files = {k: {} for k in E.SOURCE_FILES}
        E.closed_source(files)
        for changed in ({E.SCRIPT: {}}, {**files, "extra": {}}):
            with self.assertRaisesRegex(Exception, "exact E3 source closure"):
                E.closed_source(changed)

    def test_attest_revalidates_each_new_source_and_pins_old(self):
        snapshots = []

        def snapshot(path):
            value = SimpleNamespace(raw=str(path).encode(), revalidate=Mock())
            snapshots.append(value)
            return value

        with (
            patch.object(R, "oid", side_effect=lambda x: x),
            patch.object(E.core, "git_head", return_value=E.BASE),
            patch.object(E.core, "require_ancestor") as ancestor,
            patch.object(R.public, "_origin") as origin,
            patch.object(V, "attest", return_value=self.prior["source"]) as old,
            patch.object(R, "snapshot_file", side_effect=snapshot),
            patch.object(R, "reviewed_file") as reviewed,
        ):
            result = E.attest("a" * 40)
        self.assertEqual(set(result["files"]), set(E.SOURCE_FILES))
        self.assertEqual(len(snapshots), 3)
        for item in snapshots:
            item.revalidate.assert_called_once_with()
        self.assertEqual(reviewed.call_count, 3)
        self.assertEqual(ancestor.call_count, 2)
        origin.assert_called_once_with(V, E.INSPECTOR)
        old.assert_called_once_with(E.INSPECTOR_REVISION)

    def test_entire_five_field_environment_compared(self):
        env = self.environment()
        E.compare_environment(env, self.original)
        for key in E.ENV_FIELDS:
            altered = copy.deepcopy(env)
            altered[key] = {"looks_valid": True}
            with self.subTest(key=key), self.assertRaises(Exception):
                E.compare_environment(altered, self.original)
        for altered in (
            {k: v for k, v in env.items() if k != "authorities"},
            {**env, "external_qualification": True},
        ):
            with self.assertRaisesRegex(Exception, "five-field"):
                E.compare_environment(altered, self.original)

    def test_all_fresh_metadata_closures_compared_to_pinned_observation(self):
        prior = copy.deepcopy(self.prior)
        evidence = SimpleNamespace(anchor=Mock(), anchors=prior["reviewed_anchors"])
        sources = prior["historical_source_receipts"]
        for key in (
            None,
            "historical_source_receipts",
            "reviewed_anchors",
            "public_archive_hash_closures",
            "sealed_metadata",
        ):
            expected = copy.deepcopy(prior)
            if key is not None:
                expected[key] = {"changed": True}
            with (
                patch.object(E.core, "require_ancestor"),
                patch.object(
                    V, "inspect_metadata", return_value=prior["sealed_metadata"]
                ),
                patch.object(
                    V,
                    "inspect_public",
                    side_effect=prior["public_archive_hash_closures"],
                ),
            ):
                if key is None:
                    E.inspect_metadata(evidence, sources, expected, E.BASE)
                else:
                    with self.subTest(key=key), self.assertRaisesRegex(Exception, key):
                        E.inspect_metadata(evidence, sources, expected, E.BASE)

    def test_baseline_plain_completion_not_bool_or_float(self):
        for count in (True, 32.0, 0, 31):
            env = self.environment()
            env["baseline"]["reproduced_trace_count"] = count
            # Even if caller fixtures have matching changed fields, completion is strict.
            original = {**self.original, **env}
            with self.assertRaises(Exception):
                E.compare_environment(env, original)

    def operation(self, **overrides):
        """MOCK wiring only: never present this fixture as an actual receipt."""
        f = self.fixture()
        events, stack = [], ExitStack()
        self.addCleanup(stack.close)
        evidence = SimpleNamespace(
            values={B.ORIGINAL_CANDIDATE: self.original},
            anchors=f.prior["reviewed_anchors"],
        )
        env = self.environment()

        def watch(name, value):
            def run(*args):
                events.append(name)
                if name in overrides:
                    raise overrides[name]
                return value

            return run

        patches = (
            (E, "_guard", watch("guard", None)),
            (C, "unused", watch("unused", None)),
            (E.core, "git_head", watch("head", E.BASE)),
            (E, "current_locations", watch("locations", f.now)),
            (E, "attest", watch("attest", {"mock": True})),
            (V, "Evidence", watch("capture", evidence)),
            (E, "prior_observation", watch("prior", f.prior)),
            (
                V,
                "historical_sources",
                watch("history", f.prior["historical_source_receipts"]),
            ),
            (
                E,
                "inspect_metadata",
                watch(
                    "metadata",
                    (
                        f.prior["sealed_metadata"],
                        f.prior["public_archive_hash_closures"],
                    ),
                ),
            ),
            (V, "recorded_chains", watch("chains", f.chains)),
            (E, "stable_state", watch("stable", None)),
            (R, "environment", watch("environment", env)),
            (E, "revalidate", watch("revalidate", None)),
        )
        mocks = {
            name: stack.enter_context(patch.object(module, name, side_effect=action))
            for module, name, action in patches
        }
        return events, mocks, env

    def test_actual_entry_order_calls_frozen_environment_once(self):
        events, mocks, env = self.operation()
        result = E.check_environment("a" * 40)
        self.assertLess(events.index("metadata"), events.index("environment"))
        self.assertLess(events.index("stable"), events.index("environment"))
        self.assertLess(events.index("environment"), events.index("revalidate"))
        mocks["environment"].assert_called_once_with(B.ORIGINAL_SOURCE)
        self.assertEqual(result["environment"], env)
        self.assertEqual(result["baseline_traces_recomputed"], 32)
        self.assertEqual(result["claim_ceiling"], E.claim_ceiling())

    def test_occupied_scope_preserves_consumption_and_stops_before_source(self):
        error = S.ExecutionFailure("AUTHORIZATION_ALREADY_SPENT", True, "occupied")
        events, mocks, _ = self.operation(unused=error)
        with self.assertRaises(E.PreflightFailure) as caught:
            E.check_environment("a" * 40)
        value = E.failure_receipt(caught.exception)
        self.assertIs(value["authorization_consumed"], True)
        self.assertEqual(value["baseline_traces_completed"], 0)
        mocks["attest"].assert_not_called()
        self.assertNotIn("environment", events)

    def test_metadata_rejection_prevents_numerical_work(self):
        events, _, _ = self.operation(metadata=ValueError("broken archive"))
        with self.assertRaises(E.PreflightFailure) as caught:
            E.check_environment("a" * 40)
        value = E.failure_receipt(caught.exception)
        self.assertEqual(value["phase"], "historical_metadata")
        self.assertEqual(value["baseline_traces_completed"], 0)
        self.assertNotIn("environment", events)

    def test_endpoint_rejection_prevents_source_and_numerical_work(self):
        events, _, _ = self.operation(locations=ValueError("new endpoint"))
        with self.assertRaises(E.PreflightFailure):
            E.check_environment("a" * 40)
        self.assertNotIn("attest", events)
        self.assertNotIn("environment", events)

    def test_environment_partial_work_is_unknown_not_zero(self):
        _, _, _ = self.operation(environment=KeyboardInterrupt("partial"))
        with self.assertRaises(E.PreflightFailure) as caught:
            E.check_environment("a" * 40)
        value = E.failure_receipt(caught.exception)
        self.assertEqual(value["phase"], "genuine_environment")
        self.assertIsNone(value["baseline_traces_completed"])
        self.assertTrue(value["baseline_work_extent_unknown"])

    def test_final_failure_retains_completed_baseline_but_no_authority(self):
        _, _, _ = self.operation(revalidate=ValueError("late source drift"))
        with self.assertRaises(E.PreflightFailure) as caught:
            E.check_environment("a" * 40)
        value = E.failure_receipt(caught.exception)
        self.assertEqual(value["baseline_traces_completed"], 32)
        self.assertFalse(value["claim_ceiling"]["current_receiver_admitted"])
        self.assertIsNone(value["authorization_consumed"])
        self.assertFalse(value["automatic_retry_allowed"])

    def test_final_whole_environment_mismatch_cannot_succeed(self):
        events, _, env = self.operation()
        env["runtime"] = {"forged": True}
        with self.assertRaises(E.PreflightFailure) as caught:
            E.check_environment("a" * 40)
        self.assertIn("whole genuine environment", str(caught.exception))
        self.assertNotIn("revalidate", events)

    def test_evidence_brackets_expensive_source_and_environment_revalidation(self):
        events = []

        def mark(name, value=None):
            return lambda *args: (events.append(name), value)[1]

        source = {"implementation_revision": "a" * 40}
        historical = {"mock": True}
        with (
            patch.object(E, "stable_state", side_effect=mark("state")),
            patch.object(E, "attest", side_effect=mark("source", source)),
            patch.object(
                V, "historical_sources", side_effect=mark("history", historical)
            ),
            patch.object(R, "check_environment", side_effect=mark("environment")),
        ):
            E.revalidate(None, source, historical, {}, E.BASE, {})
        self.assertEqual(events, ["state", "source", "history", "environment", "state"])

    def test_stable_state_rejects_head_or_identity_drift(self):
        f = self.fixture()
        evidence = SimpleNamespace(revalidate=Mock())
        with (
            patch.object(E, "_guard"),
            patch.object(C, "unused"),
            patch.object(E.core, "git_head", return_value="a" * 40),
        ):
            with self.assertRaisesRegex(Exception, "HEAD changed"):
                E.stable_state(evidence, E.BASE, f.now)
        with (
            patch.object(E, "_guard"),
            patch.object(C, "unused"),
            patch.object(E.core, "git_head", return_value=E.BASE),
            patch.object(E, "current_locations", return_value=f.old),
        ):
            with self.assertRaisesRegex(Exception, "identity changed"):
                E.stable_state(evidence, E.BASE, f.now)

    def test_stable_state_catches_change_during_evidence_reads(self):
        f = self.fixture()
        evidence = SimpleNamespace(revalidate=Mock())
        for dirty, heads in (
            (b" M protected.py\n", [E.BASE]),
            (b"", [E.BASE, "a" * 40]),
        ):
            with (
                patch.object(E, "_guard"),
                patch.object(C, "unused"),
                patch.object(E.core, "git_head", side_effect=heads),
                patch.object(E.core, "git_bytes", return_value=dirty),
                patch.object(E, "current_locations", return_value=f.now),
            ):
                with self.assertRaisesRegex(Exception, "remain clean|HEAD changed"):
                    E.stable_state(evidence, E.BASE, f.now)

    def test_dependency_substitution_detected(self):
        E._guard()
        for module, name in (
            (R, "environment"),
            (V, "inspect_metadata"),
            (R.public, "qualify_baseline"),
            (R.public.q, "run_matrix"),
        ):
            with self.subTest(name=name), patch.object(module, name, return_value={}):
                with self.assertRaisesRegex(Exception, "dependency substituted"):
                    E._guard()

    def test_failure_delivery_and_unknown_effects_remain_separate(self):
        value = E.failure_receipt(OSError("stdout closed"), {"completed": True})
        self.assertEqual(value["baseline_traces_completed"], 32)
        self.assertEqual(value["phase"], "result_delivery")
        self.assertIsNone(value["authorization_consumed"])
        self.assertFalse(value["execution_dispatch_entered"])
        self.assertFalse(value["new_effects_attempted"])
        self.assertTrue(value["retain_evidence"])
        self.assertEqual(
            value["claim_ceiling"]["reconstruction_status"], "FAILED_INCOMPLETE"
        )

    def test_no_effectful_or_saved_public_replay_calls(self):
        tree = ast.parse((ROOT / E.SCRIPT).read_text())
        forbidden = {
            "fsync",
            "consume",
            "publish",
            "prepare",
            "admit",
            "run",
            "reconstruct",
            "inspect_transport",
            "reduce_rows",
            "replay",
            "_cohort",
            "certificate_projection",
            "candidate_projection",
            "load_inputs",
            "analyze",
            "analyze_and_save",
            "unlink",
            "chmod",
        }
        calls = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        self.assertFalse(calls & forbidden)
        self.assertEqual(
            list(inspect.signature(E.check_environment).parameters), ["revision"]
        )
        self.assertFalse(hasattr(E, "observation_shape"))

    def test_fresh_cli_outside_checkout_static_and_rejects_effect_inputs(self):
        with tempfile.TemporaryDirectory(prefix="qmc-e3-cli-") as temporary:
            env = {
                **os.environ,
                "PYTHONPATH": str(ROOT / "src"),
                "PYTHONPYCACHEPREFIX": temporary,
            }
            command = [sys.executable, "-P", "-B", str(ROOT / E.SCRIPT)]
            result = subprocess.run(
                command + ["--self-test"],
                cwd="/tmp",
                env=env,
                capture_output=True,
                check=True,
            )
            value = E.parse(result.stdout)
            self.assertEqual(value["status"], "STATIC_SELF_TEST_ONLY")
            self.assertEqual(value["baseline_traces_recomputed"], 0)
            self.assertEqual(
                value["claim_ceiling"]["reconstruction_status"], "NOT_PERFORMED"
            )
            for args in (
                ["--run"],
                ["--check-environment"],
                ["--self-test", "--implementation-revision", E.BASE],
                ["--self-test", "--device", "16777235"],
                ["--self-test", "--confirmed-digest", V.CANDIDATE_DIGEST],
            ):
                result = subprocess.run(
                    command + args, cwd="/tmp", env=env, capture_output=True
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, b"")


if __name__ == "__main__":
    unittest.main()
