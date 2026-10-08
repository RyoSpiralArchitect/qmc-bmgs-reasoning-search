"""Projection fixtures and MOCK wiring, not actual E3 numerical reconstruction."""

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
    "receiver_e3_replay_tested",
    ROOT / "scripts/replay_feedback_budget_receiver_e3_public.py",
)
assert SPEC is not None and SPEC.loader is not None
P = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = P
SPEC.loader.exec_module(P)
E, V, R, B, C, S = P.E, P.V, P.R, P.B, P.C, P.S


def read(path):
    return P.parse((ROOT / path).read_bytes())


class ReceiverE3PublicReplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prior = read(P.PRIOR)
        cls.source = dict(environment_source=cls.prior["source"])
        cls.environment = cls.prior["environment"]
        cls.historical = cls.prior["historical_source_receipts"]
        # Genuine PUBLIC manifest only. No baseline, archive replay or sealed load.
        cls.inputs = R.load_inputs(S.PUBLIC)
        cls.values = {path: read(path) for path, _ in V.ANCHORS}
        cls.receipts = {}
        for label in P.LABELS:
            output = V.PUBLIC_SPECS[label][0]
            cls.values[str(output / "STARTED.json")] = read(output / "STARTED.json")
            cls.receipts[label] = read(output / "RECEIPT.json")
        cls.fence = C.FENCE.read_bytes()

    def projection(self, label, receipt=None):
        output, commit, _, _, _ = V.PUBLIC_SPECS[label]
        receiver = (
            V.historical_receiver_reference(self.values, self.historical)
            if label == "receiver_v2_public"
            else None
        )
        return P.historical_summary(
            label,
            self.inputs.manifest,
            self.environment,
            self.values[str(output / "STARTED.json")]["binding"],
            self.values[commit],
            receipt or self.receipts[label],
            self.historical,
            receiver,
            self.fence if receiver else None,
        )

    def test_two_entire_historical_summary_projections_match_saved_bytes(self):
        for label in P.LABELS:
            with self.subTest(label=label):
                saved = ROOT / V.PUBLIC_SPECS[label][2]
                self.assertEqual(
                    P.canonical(self.projection(label)), saved.read_bytes()
                )

    def test_projection_uses_fresh_numerics_not_a_saved_summary_template(self):
        for label in P.LABELS:
            for key in ("integrity", "reduction"):
                receipt = copy.deepcopy(self.receipts[label])
                receipt[key] = {"different_fresh_result": True}
                receipt = P.digested(B.without_digest(receipt))
                projected = self.projection(label, receipt)
                self.assertEqual(projected[key], receipt[key])
                self.assertNotEqual(projected, self.projection(label))
        self.assertNotIn("summary", inspect.signature(P.historical_summary).parameters)

    def test_historical_flags_never_elevate_current_authority(self):
        self.assertTrue(
            self.projection("receiver_v2_public")["public_coordinator_qualified"]
        )
        for label in P.LABELS:
            self.assertTrue(self.projection(label)["authorization_consumed"])
        ceiling = P.ceiling()
        for key in (
            "current_receiver_admitted",
            "new_coordinator_qualified",
            "certificate_issued",
            "candidate_issued",
            "acceptance_order_reconstructed",
            "replication_execution_authorized",
        ):
            self.assertIs(ceiling[key], False)
        self.assertEqual(ceiling["new_public_attempts"], 0)

    def test_summary_projection_is_fixed_public_only(self):
        with self.assertRaises(Exception):
            self.projection("invented")
        original = self.values[str(B.PUBLIC_OUTPUT / "STARTED.json")]["binding"]
        for mode in (S.REPLICATION, None, True):
            with self.assertRaisesRegex(Exception, "PUBLIC manifest"):
                P.historical_summary(
                    "original_public",
                    {"execution_mode": mode},
                    {},
                    original,
                    {},
                    {},
                    {},
                    None,
                    None,
                )

    def test_complete_nonlocation_historical_authorizations_match(self):
        for label in P.LABELS:
            output = V.PUBLIC_SPECS[label][0]
            binding = self.values[str(output / "STARTED.json")]["binding"]
            P.historical_authorization(
                label,
                self.inputs,
                self.environment,
                self.values,
                self.historical,
                binding,
            )

    def test_authorization_rejects_all_environment_fields_and_extra_fields(self):
        output = B.PUBLIC_OUTPUT
        for field in (*E.ENV_FIELDS, "attempt_id", "candidate_is_execution_authority"):
            binding = copy.deepcopy(
                self.values[str(output / "STARTED.json")]["binding"]
            )
            binding["authorization"][field] = {"changed": True}
            with (
                self.subTest(field=field),
                self.assertRaisesRegex(Exception, "whole historical"),
            ):
                P.historical_authorization(
                    "original_public",
                    self.inputs,
                    self.environment,
                    self.values,
                    self.historical,
                    binding,
                )

    def test_v2_authorization_rejects_historical_attempt_and_receiver_substitution(
        self,
    ):
        for field in ("attempt_id", "receiver_admission", "coordinator_source"):
            binding = copy.deepcopy(
                self.values[str(C.PUBLIC_OUTPUT / "STARTED.json")]["binding"]
            )
            binding["authorization"][field] = {"changed": True}
            with self.assertRaisesRegex(Exception, "whole historical"):
                P.historical_authorization(
                    "receiver_v2_public",
                    self.inputs,
                    self.environment,
                    self.values,
                    self.historical,
                    binding,
                )

    def test_fake_inputs_rejected_before_candidate_or_numerical_call(self):
        with (
            patch.object(R, "candidate") as candidate,
            patch.object(R, "reduce_rows") as reduce,
        ):
            with self.assertRaisesRegex(Exception, "fixed PUBLIC inputs"):
                P.historical_authorization(
                    "original_public", SimpleNamespace(), {}, {}, {}, {}
                )
            with self.assertRaisesRegex(Exception, "genuine fixed PUBLIC inputs"):
                P.replay_one(
                    "original_public", None, SimpleNamespace(), {}, {}, P.initial_work()
                )
        candidate.assert_not_called()
        reduce.assert_not_called()

    def test_pinned_git_bytes_before_parse(self):
        item = SimpleNamespace(raw=b"{}\n")
        evidence = SimpleNamespace(file=Mock(return_value=item))
        with (
            patch.object(R, "reviewed_file") as reviewed,
            patch.object(P, "parse") as parse,
        ):
            with self.assertRaisesRegex(Exception, "pinned E3 observation bytes"):
                P.prior_observation(evidence, self.source)
        reviewed.assert_called_once_with(item, P.BASE)
        parse.assert_not_called()

    def test_git_failure_prevents_prior_parse(self):
        evidence = SimpleNamespace(file=Mock(return_value=SimpleNamespace(raw=b"{}\n")))
        with (
            patch.object(R, "reviewed_file", side_effect=ValueError("Git drift")),
            patch.object(P, "parse") as parse,
        ):
            with self.assertRaisesRegex(Exception, "Git drift"):
                P.prior_observation(evidence, self.source)
        parse.assert_not_called()

    def test_pinned_prior_exact_and_source_linkage(self):
        evidence = SimpleNamespace(
            file=Mock(return_value=SimpleNamespace(raw=(ROOT / P.PRIOR).read_bytes()))
        )
        with patch.object(R, "reviewed_file"):
            self.assertEqual(P.prior_observation(evidence, self.source), self.prior)
            with self.assertRaisesRegex(Exception, "pinned E3 source differs"):
                P.prior_observation(evidence, {"environment_source": {}})

    def test_source_registry_is_exact_three_files(self):
        files = {key: {} for key in P.SOURCE_FILES}
        P.closed_source(files)
        for altered in ({P.SCRIPT: {}}, {**files, "extra": {}}):
            with self.assertRaisesRegex(Exception, "exact replay source closure"):
                P.closed_source(altered)

    def test_attest_pins_environment_source_and_revalidates_three_files(self):
        snapshots = []

        def capture(path):
            item = SimpleNamespace(raw=str(path).encode(), revalidate=Mock())
            snapshots.append(item)
            return item

        with (
            patch.object(R, "oid", side_effect=lambda x: x),
            patch.object(P.core, "git_head", return_value=P.BASE),
            patch.object(P.core, "require_ancestor") as ancestor,
            patch.object(R.public, "_origin") as origin,
            patch.object(E, "attest", return_value=self.prior["source"]) as old,
            patch.object(R, "snapshot_file", side_effect=capture),
            patch.object(R, "reviewed_file") as reviewed,
        ):
            result = P.attest("a" * 40)
        self.assertEqual(set(result["files"]), set(P.SOURCE_FILES))
        self.assertEqual(len(snapshots), 3)
        for item in snapshots:
            item.revalidate.assert_called_once_with()
        self.assertEqual(reviewed.call_count, 3)
        self.assertEqual(ancestor.call_count, 2)
        origin.assert_called_once_with(E, P.ENVIRONMENT_SCRIPT)
        old.assert_called_once_with(P.ENVIRONMENT_REVISION)

    def test_each_fresh_metadata_closure_matches_pinned_e3(self):
        for changed in (
            None,
            "historical_source_receipts",
            "reviewed_anchors",
            "sealed_metadata",
            "public_archive_hash_closures",
            "location_correspondence",
        ):
            prior = copy.deepcopy(self.prior)
            if changed:
                prior[changed] = {"different": True}
            evidence = SimpleNamespace(
                values={}, anchors=self.prior["reviewed_anchors"]
            )
            e2 = {"location_correspondence": {"current_locations": {}}}
            with (
                patch.object(P, "prior_observation", return_value=prior),
                patch.object(E, "prior_observation", return_value=e2),
                patch.object(V, "historical_sources", return_value=self.historical),
                patch.object(
                    E,
                    "inspect_metadata",
                    return_value=(
                        self.prior["sealed_metadata"],
                        self.prior["public_archive_hash_closures"],
                    ),
                ),
                patch.object(V, "recorded_chains", return_value=[]),
                patch.object(
                    E,
                    "correspondence",
                    return_value=self.prior["location_correspondence"],
                ),
            ):
                if changed:
                    with (
                        self.subTest(changed=changed),
                        self.assertRaisesRegex(Exception, changed),
                    ):
                        P.inspect_metadata(evidence, self.source, P.BASE, {})
                else:
                    P.inspect_metadata(evidence, self.source, P.BASE, {})

    def test_fixed_archive_requires_unique_real_read_only_capture(self):
        for label, items in (
            ("invented", []),
            ("original_public", []),
            ("original_public", [SimpleNamespace(path=B.PUBLIC_OUTPUT, names=S.NAMES)]),
        ):
            with self.assertRaises(Exception):
                P.archive_for(SimpleNamespace(archives=items), label)

    def wiring(
        self,
        label="original_public",
        *,
        reducer=None,
        summary_change=False,
        receipt_change=False,
    ):
        """MOCK numerical results; never evidence that one trace was replayed."""
        stack = ExitStack()
        self.addCleanup(stack.close)
        work = P.initial_work()
        values = copy.deepcopy(self.values)
        if summary_change:
            values[V.PUBLIC_SPECS[label][2]]["extra"] = True
        raw = {name: b'{"mock":true}\n' for name in S.base.CELL_NAMES}
        raw["RECEIPT.json"] = P.canonical(self.receipts[label])
        if receipt_change:
            raw["RECEIPT.json"] += b" "
        archive = SimpleNamespace(raw=raw, revalidate=Mock())
        evidence = SimpleNamespace(
            values=values,
            snapshots=[
                SimpleNamespace(path=C.FENCE, raw=self.fence, revalidate=Mock())
            ],
        )

        def complete(inputs, rows, binding, observer):
            self.assertIs(inputs, self.inputs)
            self.assertEqual(len(rows), 1024)
            for stage in R.analysis.STAGES[1:]:
                observer(stage)
            return self.receipts[label]

        stack.enter_context(patch.object(P, "archive_for", return_value=archive))
        stack.enter_context(patch.object(P, "progress"))
        reduce = stack.enter_context(
            patch.object(R, "reduce_rows", side_effect=reducer or complete)
        )
        return work, evidence, archive, reduce

    def execute_fixture(self, label, work, evidence):
        return P.replay_one(
            label, evidence, self.inputs, self.environment, self.historical, work
        )

    def test_complete_wiring_reduces_both_archives_without_deduplication(self):
        # Two separate genuine replay_one calls and two separate reducer calls.
        calls = []
        for label in P.LABELS:
            work, evidence, archive, reduce = self.wiring(label)
            result = self.execute_fixture(label, work, evidence)
            reduce.assert_called_once()
            calls.append(reduce.call_args)
            row = next(r for r in work["public_archives"] if r["label"] == label)
            self.assertEqual(row["replayed_traces_completed"], 1024)
            self.assertEqual(row["budget_prefix_comparisons_completed"], 512)
            self.assertTrue(row["receipt_reproduced"] and row["summary_reproduced"])
            self.assertFalse(result["current_receiver_admitted"])
            self.assertFalse(result["new_coordinator_qualified"])
            self.assertEqual(archive.revalidate.call_count, 2)
        self.assertNotEqual(calls[0].args[2], calls[1].args[2])

    def test_replay_entry_partial_counts_unknown(self):
        def fail(inputs, rows, binding, observer):
            observer(R.analysis.STAGES[1])
            raise KeyboardInterrupt("partial numerical work")

        work, evidence, _, _ = self.wiring(reducer=fail)
        with self.assertRaises(KeyboardInterrupt):
            self.execute_fixture("original_public", work, evidence)
        self.assertIsNone(work["public_archives"][0]["replayed_traces_completed"])
        self.assertIsNone(
            work["public_archives"][0]["budget_prefix_comparisons_completed"]
        )
        self.assertEqual(work["public_archives"][1]["replayed_traces_completed"], 0)

    def test_reduction_failure_retains_all_replay_and_prefix_counts(self):
        def fail(inputs, rows, binding, observer):
            for stage in R.analysis.STAGES[1:3]:
                observer(stage)
            raise ValueError("reduction failed")

        work, evidence, _, _ = self.wiring(reducer=fail)
        with self.assertRaisesRegex(Exception, "reduction failed"):
            self.execute_fixture("original_public", work, evidence)
        row = work["public_archives"][0]
        self.assertEqual(row["replayed_traces_completed"], 1024)
        self.assertEqual(row["budget_prefix_comparisons_completed"], 512)
        self.assertFalse(row["receipt_reproduced"] or row["summary_reproduced"])

    def test_out_of_order_missing_or_duplicate_stages_rejected(self):
        for stages in (
            R.analysis.STAGES[2:],
            R.analysis.STAGES[1:2],
            (R.analysis.STAGES[1], R.analysis.STAGES[1]),
        ):

            def bad(inputs, rows, binding, observer):
                for stage in stages:
                    observer(stage)
                return self.receipts["original_public"]

            work, evidence, _, _ = self.wiring(reducer=bad)
            with (
                self.subTest(stages=stages),
                self.assertRaisesRegex(Exception, "stage"),
            ):
                self.execute_fixture("original_public", work, evidence)

    def test_receipt_whole_bytes_mismatch_cannot_complete(self):
        work, evidence, _, _ = self.wiring(receipt_change=True)
        with self.assertRaisesRegex(Exception, "complete retained PUBLIC receipt"):
            self.execute_fixture("original_public", work, evidence)
        row = work["public_archives"][0]
        self.assertEqual(row["replayed_traces_completed"], 1024)
        self.assertFalse(row["receipt_reproduced"] or row["summary_reproduced"])

    def test_summary_whole_bytes_mismatch_preserves_receipt_completion(self):
        work, evidence, _, _ = self.wiring(summary_change=True)
        with self.assertRaisesRegex(Exception, "complete historical PUBLIC summary"):
            self.execute_fixture("original_public", work, evidence)
        row = work["public_archives"][0]
        self.assertTrue(row["receipt_reproduced"])
        self.assertFalse(row["summary_reproduced"])

    def test_second_invocation_is_not_an_automatic_retry(self):
        work, evidence, _, reduce = self.wiring()
        self.execute_fixture("original_public", work, evidence)
        with self.assertRaisesRegex(Exception, "no automatic replay retry"):
            self.execute_fixture("original_public", work, evidence)
        reduce.assert_called_once()

    def test_final_archive_change_retains_numerical_completion_but_rejects(self):
        work, evidence, archive, _ = self.wiring()
        archive.revalidate.side_effect = [None, ValueError("archive changed")]
        with self.assertRaisesRegex(Exception, "archive changed"):
            self.execute_fixture("original_public", work, evidence)
        self.assertTrue(work["public_archives"][0]["summary_reproduced"])
        receipt = P.failure_receipt(
            P.ReplayFailure(ValueError("archive changed"), "original_public", work)
        )
        self.assertEqual(
            receipt["claim_ceiling"]["reconstruction_status"], "FAILED_INCOMPLETE"
        )

    def operation(self, **failures):
        """MOCK top-level ordering only. No actual numerical qualification."""
        stack, events = ExitStack(), []
        self.addCleanup(stack.close)
        evidence = SimpleNamespace(
            values={B.ORIGINAL_CANDIDATE: self.values[B.ORIGINAL_CANDIDATE]},
            anchors=self.prior["reviewed_anchors"],
        )
        source = {**self.source, "implementation_revision": "a" * 40}

        def action(name, result=None):
            def run(*args):
                events.append(name)
                if name in failures:
                    raise failures[name]
                return result

            return run

        def replay(label, evidence, inputs, environment, historical, work):
            events.append(label)
            if label in failures:
                raise failures[label]
            row = next(row for row in work["public_archives"] if row["label"] == label)
            row.update(
                stage="MOCK_COMPLETED_NOT_EVIDENCE",
                replayed_traces_completed=1024,
                budget_prefix_comparisons_completed=512,
                receipt_reproduced=True,
                summary_reproduced=True,
            )
            return {"label": label, "mock": True}

        patches = (
            (P, "_guard", action("guard")),
            (C, "unused", action("unused")),
            (P.core, "git_head", action("head", P.BASE)),
            (E, "current_locations", action("locations", {})),
            (P, "attest", action("attest", source)),
            (V, "Evidence", action("evidence", evidence)),
            (
                P,
                "inspect_metadata",
                action(
                    "metadata",
                    (
                        self.prior,
                        self.historical,
                        self.prior["sealed_metadata"],
                        self.prior["public_archive_hash_closures"],
                        self.prior["location_correspondence"],
                    ),
                ),
            ),
            (P, "stable_state", action("state")),
            (R, "environment", action("environment", self.environment)),
            (E, "revalidate", action("revalidate")),
            (R, "load_inputs", action("inputs", self.inputs)),
            (P, "replay_one", replay),
            (P, "progress", action("progress")),
        )
        mocks = {
            name: stack.enter_context(patch.object(module, name, side_effect=run))
            for module, name, run in patches
        }
        return events, mocks

    def test_top_level_fresh_environment_and_both_replays_in_order(self):
        events, mocks = self.operation()
        result = P.reconstruct("a" * 40)
        for earlier, later in (
            ("metadata", "environment"),
            ("state", "environment"),
            ("environment", "inputs"),
            ("inputs", "original_public"),
            ("original_public", "receiver_v2_public"),
        ):
            self.assertLess(events.index(earlier), events.index(later))
        mocks["environment"].assert_called_once_with(B.ORIGINAL_SOURCE)
        mocks["load_inputs"].assert_called_once_with(S.PUBLIC)
        self.assertEqual(
            [call.args[0] for call in mocks["replay_one"].call_args_list],
            list(P.LABELS),
        )
        self.assertEqual(mocks["revalidate"].call_count, 2)
        self.assertEqual(result["public_traces_replayed"], 2048)
        self.assertEqual(result["budget_prefix_comparisons"], 1024)
        self.assertEqual(result["work"]["baseline_traces_completed"], 32)

    def test_pre_numerical_failures_do_not_start_environment_or_replay(self):
        for step in ("unused", "locations", "attest", "metadata", "state"):
            events, mocks = self.operation(**{step: ValueError(step)})
            with self.subTest(step=step), self.assertRaises(P.ReplayFailure) as caught:
                P.reconstruct("a" * 40)
            value = P.failure_receipt(caught.exception)
            self.assertEqual(value["work"]["baseline_traces_completed"], 0)
            self.assertNotIn("environment", events)
            mocks["replay_one"].assert_not_called()

    def test_occupied_claim_retains_consumed_state(self):
        error = S.ExecutionFailure("AUTHORIZATION_ALREADY_SPENT", True, "occupied")
        self.operation(unused=error)
        with self.assertRaises(P.ReplayFailure) as caught:
            P.reconstruct("a" * 40)
        receipt = P.failure_receipt(caught.exception)
        self.assertIs(receipt["authorization_consumed"], True)
        self.assertFalse(receipt["execution_dispatch_entered"])

    def test_environment_interruption_retains_unknown_partial_extent(self):
        events, _ = self.operation(environment=KeyboardInterrupt("partial"))
        with self.assertRaises(P.ReplayFailure) as caught:
            P.reconstruct("a" * 40)
        self.assertIsNone(
            P.failure_receipt(caught.exception)["work"]["baseline_traces_completed"]
        )
        self.assertNotIn("inputs", events)

    def test_second_archive_failure_retains_first_and_no_new_authority(self):
        self.operation(receiver_v2_public=ValueError("second failed"))
        with self.assertRaises(P.ReplayFailure) as caught:
            P.reconstruct("a" * 40)
        value = P.failure_receipt(caught.exception)
        self.assertEqual(value["phase"], "receiver_v2_public")
        self.assertEqual(value["work"]["baseline_traces_completed"], 32)
        self.assertTrue(value["work"]["public_archives"][0]["summary_reproduced"])
        self.assertFalse(value["work"]["public_archives"][1]["summary_reproduced"])
        self.assertFalse(value["automatic_retry_allowed"])

    def test_final_revalidation_failure_retains_both_completed_replays(self):
        _, mocks = self.operation()
        mocks["revalidate"].side_effect = [None, ValueError("late source drift")]
        with self.assertRaises(P.ReplayFailure) as caught:
            P.reconstruct("a" * 40)
        value = P.failure_receipt(caught.exception)
        self.assertEqual(value["phase"], "final_source_runtime_evidence_revalidation")
        self.assertTrue(
            all(r["summary_reproduced"] for r in value["work"]["public_archives"])
        )
        self.assertFalse(value["claim_ceiling"]["current_receiver_admitted"])

    def test_stable_state_brackets_source_and_genuine_input_revalidation(self):
        events, source = [], {"implementation_revision": "a" * 40}
        with (
            patch.object(P, "_guard"),
            patch.object(
                E, "stable_state", side_effect=lambda *a: events.append("state")
            ),
            patch.object(
                P, "attest", side_effect=lambda *a: (events.append("source"), source)[1]
            ),
            patch.object(
                R.Inputs, "revalidate", side_effect=lambda: events.append("inputs")
            ),
        ):
            P.stable_state(None, source, P.BASE, {}, self.inputs)
        self.assertEqual(events, ["state", "source", "inputs", "state"])

    def test_stable_state_propagates_identity_head_and_source_drift(self):
        source = {"implementation_revision": "a" * 40}
        for message in ("HEAD changed", "identity changed", "dirty source"):
            with (
                patch.object(P, "_guard"),
                patch.object(E, "stable_state", side_effect=ValueError(message)),
            ):
                with self.assertRaisesRegex(Exception, message):
                    P.stable_state(None, source, P.BASE, {})
        with (
            patch.object(P, "_guard"),
            patch.object(E, "stable_state"),
            patch.object(P, "attest", return_value={}),
        ):
            with self.assertRaisesRegex(Exception, "replay source changed"):
                P.stable_state(None, source, P.BASE, {})

    def test_callable_substitutions_cannot_qualify_an_actual_operation(self):
        P._guard()
        for module, name in (
            (R, "environment"),
            (R, "load_inputs"),
            (R, "candidate"),
            (R, "reduce_rows"),
            (R, "replay"),
            (E, "correspondence"),
            (R.q, "replay_countdown_track_a_search_bytes"),
            (R.analysis, "reduce_matrix"),
        ):
            with self.subTest(name=name), patch.object(module, name, return_value={}):
                with self.assertRaisesRegex(Exception, "dependency substituted"):
                    P._guard()

    def test_failure_work_snapshot_and_delivery_boundary(self):
        work = P.initial_work()
        work["baseline_traces_completed"] = 32
        error = P.ReplayFailure(ValueError("late failure"), "original_public", work)
        work["baseline_traces_completed"] = 0
        self.assertEqual(
            P.failure_receipt(error)["work"]["baseline_traces_completed"], 32
        )
        result = {"work": error.work}
        delivered = P.failure_receipt(OSError("stdout closed"), result)
        self.assertEqual(delivered["phase"], "result_delivery")
        self.assertEqual(delivered["work"], error.work)
        self.assertIsNone(delivered["authorization_consumed"])
        self.assertFalse(delivered["new_effects_attempted"])

    def test_no_admission_publication_sealed_regeneration_or_effectful_api(self):
        tree = ast.parse((ROOT / P.SCRIPT).read_text())
        calls = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        forbidden = {
            "fsync",
            "consume",
            "publish",
            "prepare",
            "admit",
            "run",
            "analyze",
            "analyze_and_save",
            "inspect_transport",
            "certificate_projection",
            "candidate_projection",
            "_cohort",
            "load_seal",
            "unlink",
            "chmod",
            "__new__",
            "__setattr__",
            "Transport",
            "Proof",
            "Admitted",
        }
        self.assertFalse(calls & forbidden)
        self.assertEqual(
            list(inspect.signature(P.reconstruct).parameters), ["revision"]
        )
        self.assertEqual(
            [
                node.args[0].attr
                for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "load_inputs"
            ],
            ["PUBLIC"],
        )

    def test_cli_outside_checkout_static_only_and_rejects_overrides(self):
        with tempfile.TemporaryDirectory(prefix="qmc-e3-replay-cli-") as temporary:
            env = {
                **os.environ,
                "PYTHONPATH": str(ROOT / "src"),
                "PYTHONPYCACHEPREFIX": temporary,
            }
            command = [sys.executable, "-P", "-B", str(ROOT / P.SCRIPT)]
            result = subprocess.run(
                command + ["--self-test"],
                cwd="/tmp",
                env=env,
                capture_output=True,
                check=True,
            )
            value = P.parse(result.stdout)
            self.assertEqual(value["status"], "STATIC_SELF_TEST_ONLY")
            self.assertEqual(value["work"], P.initial_work())
            self.assertEqual(
                value["claim_ceiling"]["reconstruction_status"], "NOT_PERFORMED"
            )
            for args in (
                ["--replay"],
                ["--run"],
                ["--self-test", "--implementation-revision", P.BASE],
                ["--self-test", "--archive", "other"],
                ["--self-test", "--device", "16777235"],
                ["--self-test", "--confirmed-digest", "a" * 64],
                ["--self-test", "--resume"],
            ):
                result = subprocess.run(
                    command + args, cwd="/tmp", env=env, capture_output=True
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, b"")


if __name__ == "__main__":
    unittest.main()
