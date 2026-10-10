"""E4 boundary fixtures and MOCK wiring; not actual numerical reconstruction."""

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
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "receiver_e4_tested", ROOT / "scripts/reconstruct_feedback_budget_receiver_e4.py"
)
assert SPEC is not None and SPEC.loader is not None
N = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = N
SPEC.loader.exec_module(N)
P, E, V, B, R, S, M = N.P, N.E, N.V, N.B, N.R, N.S, N.M


def read(path):
    return N.parse((ROOT / path).read_bytes())


class ReceiverE4(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prior = read(N.PRIOR)
        cls.source = dict(previous_replay_source=cls.prior["source"])
        cls.environment = cls.prior["environment"]
        cls.historical = cls.prior["historical_source_receipts"]
        cls.e2 = read(E.PRIOR)["location_correspondence"]["current_locations"]
        cls.e3 = cls.prior["location_correspondence"]["current_locations"]
        cls.chains = cls.prior["location_correspondence"]["original_chains"]
        cls.locations = copy.deepcopy(cls.e3)
        for location in cls.locations.values():
            for pair in location["identities"]:
                pair[0] = N.CURRENT_DEVICE
        cls.seal_raw = {name: (M.COHORT_PATH / name).read_bytes() for name in M.NAMES}
        cls.seal = N.parse(cls.seal_raw["preregistration.json"])
        cls.original = read(B.ORIGINAL_CANDIDATE)
        cls.original_summary = read(B.PUBLIC_SUMMARY)
        cls.reference = N.generation_reference(cls.original_summary)
        # Genuine PUBLIC input metadata only, no sealed admission or numerics.
        cls.inputs = R.load_inputs(S.PUBLIC)
        cls.values = {path: read(path) for path, _ in V.ANCHORS}
        cls.receipts = {}
        for label in N.LABELS:
            output = V.PUBLIC_SPECS[label][0]
            cls.values[str(output / "STARTED.json")] = read(output / "STARTED.json")
            cls.receipts[label] = read(output / "RECEIPT.json")

    def mapping(self, **changes):
        args = dict(
            chains=self.chains,
            e2_locations=self.e2,
            e3_locations=self.e3,
            locations=self.locations,
        )
        args.update(changes)
        return N.correspondence(**args)

    def test_direct_23_chains_retain_four_separate_historical_epochs(self):
        result = self.mapping()
        self.assertEqual(result["current_epoch"], "E4")
        self.assertEqual(
            {key: row["chain_count"] for key, row in result["epochs"].items()},
            {
                "original_v7": 3,
                "receiver_20260921": 8,
                "E2_observation": 6,
                "E3_observation": 6,
            },
        )
        self.assertEqual(len(result["prior_observation_chains"]), 12)
        self.assertFalse(result["repeated_device_number_is_epoch_identity"])
        self.assertFalse(result["current_receiver_admitted"])
        for row in result["prior_observation_chains"]:
            path = E.PRIOR if row["historical_epoch"] == "E2_observation" else N.PRIOR
            self.assertEqual(row["owner"]["path"], path)
        self.assertEqual(
            result["epochs"]["E2_observation"]["historical_device"],
            result["epochs"]["E2_observation"]["observed_device"],
        )

    def test_all_current_devices_exact_not_an_allowlist(self):
        for device in (16777231, 16777232, 16777233, 16777235, True, 16777234.0):
            locations = copy.deepcopy(self.locations)
            for location in locations.values():
                for pair in location["identities"]:
                    pair[0] = device
            with self.subTest(device=device), self.assertRaises(Exception):
                self.mapping(locations=locations)

    def test_current_capture_closes_every_role_before_comparison(self):
        with patch.object(V, "current_locations", return_value=self.locations):
            self.assertEqual(N.current_locations(), self.locations)
        for role in V.LOCATIONS:
            locations = copy.deepcopy(self.locations)
            del locations[role]
            with patch.object(V, "current_locations", return_value=locations):
                with self.assertRaisesRegex(Exception, "exact six"):
                    N.current_locations()

    def test_missing_extra_roles_and_incomplete_component_chains_rejected(self):
        for field, value in (
            ("locations", self.locations),
            ("e2_locations", self.e2),
            ("e3_locations", self.e3),
        ):
            for role in V.LOCATIONS:
                missing = copy.deepcopy(value)
                del missing[role]
                truncated = copy.deepcopy(value)
                truncated[role]["identities"].pop()
                extra = {**value, "invented": {}}
                for changed in (missing, truncated, extra):
                    with (
                        self.subTest(field=field, role=role),
                        self.assertRaises(Exception),
                    ):
                        self.mapping(**{field: changed})

    def test_every_original_owner_epoch_and_order_is_bound(self):
        for index in range(11):
            for field in ("owner", "historical_epoch", "label"):
                changed = copy.deepcopy(self.chains)
                changed[index][field] = "substituted"
                with (
                    self.subTest(index=index, field=field),
                    self.assertRaises(Exception),
                ):
                    self.mapping(chains=changed)
        for changed in (
            self.chains[::-1],
            self.chains[:-1],
            self.chains + self.chains[:1],
        ):
            with self.assertRaises(Exception):
                self.mapping(chains=changed)

    def test_every_original_and_observed_inode_path_and_device_is_bound(self):
        for index in range(11):
            changed = copy.deepcopy(self.chains)
            changed[index]["historical"]["identities"][-1][1] += 1
            with self.assertRaisesRegex(Exception, "inode|shared prefix"):
                self.mapping(chains=changed)
        for field, base in (
            ("e2_locations", self.e2),
            ("e3_locations", self.e3),
            ("locations", self.locations),
        ):
            for role in V.LOCATIONS:
                for mutation in ("inode", "device", "path"):
                    changed = copy.deepcopy(base)
                    if mutation == "inode":
                        changed[role]["identities"][-1][1] += 1
                    elif mutation == "device":
                        changed[role]["identities"][0][0] += 2
                    else:
                        changed[role]["path"] += "-alternate"
                    with self.subTest(field=field, role=role, mutation=mutation):
                        with self.assertRaises(Exception):
                            self.mapping(**{field: changed})

    def test_pinned_reviewed_bytes_before_parsing(self):
        evidence = SimpleNamespace(file=Mock(return_value=SimpleNamespace(raw=b"{}\n")))
        with (
            patch.object(R, "reviewed_file") as reviewed,
            patch.object(N, "parse") as parse,
        ):
            with self.assertRaisesRegex(
                Exception, "pinned E3 PUBLIC observation bytes"
            ):
                N.prior_observation(evidence, self.source)
        reviewed.assert_called_once()
        parse.assert_not_called()

    def test_git_failure_prevents_prior_parsing(self):
        evidence = SimpleNamespace(file=Mock(return_value=SimpleNamespace(raw=b"{}\n")))
        with (
            patch.object(R, "reviewed_file", side_effect=ValueError("Git drift")),
            patch.object(N, "parse") as parse,
        ):
            with self.assertRaisesRegex(Exception, "Git drift"):
                N.prior_observation(evidence, self.source)
        parse.assert_not_called()

    def test_prior_full_bytes_and_source_link_match(self):
        evidence = SimpleNamespace(
            file=Mock(return_value=SimpleNamespace(raw=(ROOT / N.PRIOR).read_bytes()))
        )
        with patch.object(R, "reviewed_file"):
            self.assertEqual(N.prior_observation(evidence, self.source), self.prior)
            with self.assertRaisesRegex(Exception, "pinned E3 source"):
                N.prior_observation(evidence, {"previous_replay_source": {}})

    def test_source_closure_exactly_three_new_files(self):
        N.closed_source({key: {} for key in N.SOURCE_FILES})
        for files in (
            {N.SCRIPT: {}},
            {**{key: {} for key in N.SOURCE_FILES}, "extra": {}},
        ):
            with self.assertRaisesRegex(Exception, "exact E4 source closure"):
                N.closed_source(files)

    def test_attestation_pins_previous_source_and_each_new_file(self):
        snapshots = []

        def capture(path):
            item = SimpleNamespace(raw=str(path).encode(), revalidate=Mock())
            snapshots.append(item)
            return item

        with (
            patch.object(R, "oid", side_effect=lambda x: x),
            patch.object(N.core, "git_head", return_value=N.BASE),
            patch.object(N.core, "require_ancestor") as ancestor,
            patch.object(R.public, "_origin") as origin,
            patch.object(P, "attest", return_value=self.prior["source"]) as old,
            patch.object(R, "snapshot_file", side_effect=capture),
            patch.object(R, "reviewed_file") as reviewed,
        ):
            result = N.attest("a" * 40)
        self.assertEqual(set(result["files"]), set(N.SOURCE_FILES))
        self.assertEqual(reviewed.call_count, 3)
        self.assertEqual(ancestor.call_count, 2)
        origin.assert_called_once_with(P, N.PREVIOUS_SCRIPT)
        old.assert_called_once_with(N.PREVIOUS_REVISION)
        for item in snapshots:
            item.revalidate.assert_called_once_with()

    def test_fresh_metadata_closures_match_both_e3_observations(self):
        env_prior = read(P.PRIOR)
        for which in ("public", "environment"):
            for key in (
                "historical_source_receipts",
                "reviewed_anchors",
                "sealed_metadata",
                "public_archive_hash_closures",
                "environment",
                "location_correspondence",
            ):
                pub, env = copy.deepcopy(self.prior), copy.deepcopy(env_prior)
                (pub if which == "public" else env)[key] = {"changed": True}
                evidence = SimpleNamespace(
                    values={}, anchors=self.prior["reviewed_anchors"]
                )
                with (
                    patch.object(N, "prior_observation", return_value=pub),
                    patch.object(P, "prior_observation", return_value=env),
                    patch.object(E, "prior_observation", return_value=read(E.PRIOR)),
                    patch.object(V, "historical_sources", return_value=self.historical),
                    patch.object(
                        E,
                        "inspect_metadata",
                        return_value=(
                            self.prior["sealed_metadata"],
                            self.prior["public_archive_hash_closures"],
                        ),
                    ),
                    patch.object(V, "recorded_chains", return_value=self.chains),
                    self.subTest(which=which, key=key),
                    self.assertRaises(Exception),
                ):
                    N.inspect_metadata(evidence, self.source, N.BASE, self.locations)

    def test_original_generation_reference_is_exact_sealed_reference(self):
        self.assertEqual(self.reference, self.seal["generation_qualification"])
        for summary in (
            read(N.C.SUMMARY_MIRROR),
            {**self.original_summary, "output_path": str(N.C.PUBLIC_OUTPUT)},
        ):
            with self.assertRaisesRegex(Exception, "original v7 PUBLIC"):
                N.generation_reference(summary)

    def test_genuine_cohort_capture_only(self):
        for items in ([], [SimpleNamespace(path=M.COHORT_PATH, names=M.NAMES)]):
            with self.assertRaisesRegex(Exception, "unique captured read-only"):
                N.cohort_archive(SimpleNamespace(archives=items))
        actual = V.ReadOnlyArchive.capture(M.COHORT_PATH, M.NAMES)
        self.assertIs(N.cohort_archive(SimpleNamespace(archives=[actual])), actual)
        with self.assertRaisesRegex(Exception, "unique captured read-only"):
            N.cohort_archive(SimpleNamespace(archives=[actual, actual]))

    def seal_wiring(self, *, generated=None, raw=None, original=None):
        """Real pure projections, MOCK cohort generation and context validation."""
        stack = ExitStack()
        self.addCleanup(stack.close)
        archive = SimpleNamespace(
            raw=copy.deepcopy(raw or self.seal_raw), revalidate=Mock()
        )
        evidence = SimpleNamespace(
            values={B.ORIGINAL_CANDIDATE: original or self.original}
        )
        stack.enter_context(patch.object(N, "cohort_archive", return_value=archive))
        generator = stack.enter_context(
            patch.object(
                M,
                "_cohort",
                return_value=copy.deepcopy(
                    self.seal["cohort"] if generated is None else generated
                ),
            )
        )
        context = stack.enter_context(patch.object(M, "revalidate_context"))
        stack.enter_context(patch.object(N, "progress"))
        return evidence, archive, generator, context, N.initial_work()

    def run_seal_fixture(self, evidence, work, reference=None, environment=None):
        return N.reconstruct_seal(
            evidence,
            self.environment if environment is None else environment,
            self.reference if reference is None else reference,
            work,
        )

    def test_whole_cohort_seal_transaction_and_input_projection_fixture(self):
        evidence, archive, generator, context, work = self.seal_wiring()
        result = self.run_seal_fixture(evidence, work)
        generator.assert_called_once_with(
            self.seal["contract"], self.environment["authorities"]
        )
        self.assertEqual(context.call_count, 2)
        self.assertEqual(archive.revalidate.call_count, 3)
        self.assertEqual(
            (
                result["accepted_sources"],
                result["examined_attempts"],
                result["rejected_attempts"],
            ),
            (64, 102, 38),
        )
        self.assertEqual(
            result["input_projection"]["deterministic_digest"],
            self.original["input_manifest_digest"],
        )
        self.assertTrue(work["sealed_cohort"]["complete_input_projection_reproduced"])
        for name in M.NAMES:
            self.assertEqual(
                result["sealed_files"][name], N.reference(self.seal_raw[name])
            )
        self.assertFalse(
            result["new_cohort_published"] or result["current_receiver_admitted"]
        )
        self.assertEqual(result["replication_policy_search_calls"], 0)

    def test_original_reference_cannot_be_replaced_before_generation(self):
        for key in self.reference:
            changed = {
                **self.reference,
                key: "0" * 64 if "path" not in key else "/alternate",
            }
            evidence, _, generator, _, work = self.seal_wiring()
            with self.subTest(key=key), self.assertRaises(Exception):
                self.run_seal_fixture(evidence, work, reference=changed)
            generator.assert_not_called()

    def test_changed_contract_context_or_saved_cohort_fails_before_generation(self):
        for field in ("contract", "admission_context", "cohort"):
            changed = copy.deepcopy(self.seal)
            changed[field] = {"substituted": True}
            raw = {**self.seal_raw, "preregistration.json": N.canonical(changed)}
            evidence, _, generator, _, work = self.seal_wiring(raw=raw)
            with self.subTest(field=field), self.assertRaises(Exception):
                self.run_seal_fixture(evidence, work)
            generator.assert_not_called()

    def test_original_input_digest_and_fields_cannot_be_replaced(self):
        for key in (
            "contract_digest",
            "schedule_digest",
            "cohort_seal",
            "input_manifest_digest",
        ):
            original = {**self.original, key: "substituted"}
            evidence, _, generator, _, work = self.seal_wiring(original=original)
            with self.assertRaisesRegex(Exception, "original input"):
                self.run_seal_fixture(evidence, work)
            generator.assert_not_called()

    def test_generation_interruption_counts_unknown_no_completion(self):
        evidence, _, generator, _, work = self.seal_wiring()
        generator.side_effect = KeyboardInterrupt("partial solver computation")
        with self.assertRaises(KeyboardInterrupt):
            self.run_seal_fixture(evidence, work)
        row = work["sealed_cohort"]
        for key in (
            "accepted_sources_completed",
            "examined_attempts_completed",
            "rejected_attempts_completed",
        ):
            self.assertIsNone(row[key])
        self.assertFalse(row["cohort_reproduced"])

    def test_changed_full_task_rejection_log_and_manifest_cannot_pass(self):
        for mutation in ("task_order", "rejection_order", "reason", "attempt", "extra"):
            generated = copy.deepcopy(self.seal["cohort"])
            if mutation == "task_order":
                generated["tasks"].reverse()
            elif mutation == "rejection_order":
                generated["generation_manifest"]["rejection_log"].reverse()
            elif mutation == "reason":
                generated["generation_manifest"]["rejection_log"][0]["reason"] = (
                    "substituted"
                )
            elif mutation == "attempt":
                generated["generation_manifest"]["rejection_log"][0]["attempt"] += 1
            else:
                generated["extra"] = True
            evidence, _, _, _, work = self.seal_wiring(generated=generated)
            with (
                self.subTest(mutation=mutation),
                self.assertRaisesRegex(Exception, "acceptance/rejection"),
            ):
                self.run_seal_fixture(evidence, work)
            row = work["sealed_cohort"]
            self.assertEqual(row["accepted_sources_completed"], 64)
            self.assertEqual(row["examined_attempts_completed"], 102)
            self.assertEqual(row["rejected_attempts_completed"], 38)
            self.assertFalse(
                row["cohort_reproduced"] or row["complete_seal_reproduced"]
            )

    def test_full_seal_difference_after_generation_preserves_cohort_completion(self):
        evidence, _, _, _, work = self.seal_wiring()
        original_seal = M._seal
        calls = []

        def altered(*args):
            calls.append(args)
            value = original_seal(*args)
            if len(calls) == 2:
                value["cells"][0]["cell_id"] = "0" * 64
            return value

        with patch.object(M, "_seal", side_effect=altered):
            with self.assertRaisesRegex(Exception, "complete original sealed bytes"):
                self.run_seal_fixture(evidence, work)
        self.assertTrue(work["sealed_cohort"]["cohort_reproduced"])
        self.assertFalse(work["sealed_cohort"]["complete_seal_reproduced"])

    def test_transaction_bytes_not_just_preregistration_are_compared(self):
        for name in ("STARTED.json", "SEALED.json"):
            changed = N.parse(self.seal_raw[name])
            changed["extra"] = True
            raw = {**self.seal_raw, name: N.canonical(changed)}
            evidence, _, generator, _, work = self.seal_wiring(raw=raw)
            with self.assertRaisesRegex(
                Exception, "complete original seal transaction"
            ):
                self.run_seal_fixture(evidence, work)
            generator.assert_called_once()
            self.assertTrue(work["sealed_cohort"]["cohort_reproduced"])
            self.assertFalse(work["sealed_cohort"]["complete_seal_reproduced"])

    def test_full_input_difference_after_seal_preserves_prior_completion(self):
        evidence, _, _, _, work = self.seal_wiring()
        original_projection = B.input_projection
        calls = []

        def altered(value):
            calls.append(value)
            result = original_projection(value)
            if len(calls) == 2:
                result["extra"] = True
            return result

        with patch.object(B, "input_projection", side_effect=altered):
            with self.assertRaisesRegex(Exception, "complete original input"):
                self.run_seal_fixture(evidence, work)
        self.assertTrue(work["sealed_cohort"]["complete_seal_reproduced"])
        self.assertFalse(work["sealed_cohort"]["complete_input_projection_reproduced"])

    def test_after_cohort_completion_archive_or_context_drift_rejects(self):
        for component in ("archive", "context"):
            evidence, archive, _, context, work = self.seal_wiring()
            if component == "archive":
                archive.revalidate.side_effect = [
                    None,
                    None,
                    ValueError("final archive drift"),
                ]
            else:
                context.side_effect = [None, ValueError("final context drift")]
            with self.assertRaisesRegex(Exception, "final"):
                self.run_seal_fixture(evidence, work)
            self.assertTrue(
                work["sealed_cohort"]["complete_input_projection_reproduced"]
            )

    def test_cohort_retry_not_allowed_in_same_operation(self):
        evidence, _, generator, _, work = self.seal_wiring()
        self.run_seal_fixture(evidence, work)
        with self.assertRaisesRegex(Exception, "no automatic cohort"):
            self.run_seal_fixture(evidence, work)
        generator.assert_called_once()

    def public_wiring(self, label, *, reducer=None, changed=None):
        """MOCK archived replay result; real whole summary projections."""
        stack = ExitStack()
        self.addCleanup(stack.close)
        work, values = N.initial_work(), copy.deepcopy(self.values)
        raw = {name: b'{"mock":true}\n' for name in S.base.CELL_NAMES}
        raw["RECEIPT.json"] = N.canonical(self.receipts[label])
        if changed == "receipt":
            raw["RECEIPT.json"] += b" "
        if changed == "summary":
            values[V.PUBLIC_SPECS[label][2]]["extra"] = True
        archive = SimpleNamespace(raw=raw, revalidate=Mock())
        evidence = SimpleNamespace(
            values=values,
            snapshots=[
                SimpleNamespace(
                    path=N.C.FENCE, raw=N.C.FENCE.read_bytes(), revalidate=Mock()
                )
            ],
        )

        def complete(inputs, rows, binding, observer):
            self.assertIs(inputs, self.inputs)
            self.assertEqual(len(rows), 1024)
            for stage in R.analysis.STAGES[1:]:
                observer(stage)
            return self.receipts[label]

        stack.enter_context(patch.object(N, "archive_for", return_value=archive))
        stack.enter_context(patch.object(N, "progress"))
        reduce = stack.enter_context(
            patch.object(R, "reduce_rows", side_effect=reducer or complete)
        )
        return work, evidence, archive, reduce

    def run_public_fixture(self, label, work, evidence):
        return N.replay_one(
            label, evidence, self.inputs, self.environment, self.historical, work
        )

    def test_separate_public_dispatch_and_fresh_original_reference(self):
        bindings = []
        for label in N.LABELS:
            work, evidence, archive, reduce = self.public_wiring(label)
            result = self.run_public_fixture(label, work, evidence)
            reduce.assert_called_once()
            bindings.append(reduce.call_args.args[2])
            self.assertEqual(archive.revalidate.call_count, 2)
            self.assertEqual(
                result["original_generation_reference"],
                self.reference if label == "original_public" else None,
            )
            self.assertFalse(result["new_coordinator_qualified"])
        self.assertNotEqual(bindings[0], bindings[1])

    def test_public_partial_counts_unknown_but_later_counts_retained(self):
        for later in (False, True):

            def fail(inputs, rows, binding, observer):
                observer(R.analysis.STAGES[1])
                if later:
                    observer(R.analysis.STAGES[2])
                raise ValueError("replay or reduction failed")

            work, evidence, _, _ = self.public_wiring("original_public", reducer=fail)
            with self.assertRaisesRegex(Exception, "failed"):
                self.run_public_fixture("original_public", work, evidence)
            row = work["public_archives"][0]
            self.assertEqual(row["replayed_traces_completed"], 1024 if later else None)
            self.assertEqual(
                row["budget_prefix_comparisons_completed"], 512 if later else None
            )
            self.assertFalse(row["receipt_reproduced"])
            self.assertEqual(work["public_archives"][1]["replayed_traces_completed"], 0)

    def test_public_whole_receipt_and_summary_equality_required(self):
        for changed in ("receipt", "summary"):
            work, evidence, _, _ = self.public_wiring(
                "original_public", changed=changed
            )
            with self.assertRaisesRegex(Exception, "complete"):
                self.run_public_fixture("original_public", work, evidence)
            row = work["public_archives"][0]
            self.assertEqual(row["replayed_traces_completed"], 1024)
            self.assertEqual(row["receipt_reproduced"], changed == "summary")
            self.assertFalse(row["summary_reproduced"])

    def test_public_order_missing_or_duplicate_stages_rejected(self):
        for stages in (
            R.analysis.STAGES[2:],
            R.analysis.STAGES[1:2],
            (R.analysis.STAGES[1], R.analysis.STAGES[1]),
        ):

            def bad(inputs, rows, binding, observer):
                for stage in stages:
                    observer(stage)
                return self.receipts["original_public"]

            work, evidence, _, _ = self.public_wiring("original_public", reducer=bad)
            with self.assertRaisesRegex(Exception, "stage"):
                self.run_public_fixture("original_public", work, evidence)

    def test_fabricated_public_inputs_rejected_before_reducer(self):
        with patch.object(R, "reduce_rows") as reduce:
            with self.assertRaisesRegex(Exception, "genuine fixed PUBLIC"):
                N.replay_one(
                    "original_public", None, SimpleNamespace(), {}, {}, N.initial_work()
                )
        reduce.assert_not_called()

    def operation(self, **failures):
        """MOCK top-level order and accounting; no genuine numerical work."""
        stack, events = ExitStack(), []
        self.addCleanup(stack.close)
        source = {**self.source, "implementation_revision": "a" * 40}
        evidence = SimpleNamespace(
            values={B.ORIGINAL_CANDIDATE: self.original},
            anchors=self.prior["reviewed_anchors"],
        )

        def action(name, result=None):
            def call(*args):
                events.append(name)
                if name in failures:
                    raise failures[name]
                return result

            return call

        def replay(label, evidence, inputs, env, hist, work):
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
            return dict(
                label=label,
                original_generation_reference=self.reference
                if label == "original_public"
                else None,
            )

        def seal(evidence, env, reference, work):
            self.assertEqual(reference, self.reference)
            events.append("sealed")
            if "sealed" in failures:
                raise failures["sealed"]
            work["sealed_cohort"].update(
                stage="MOCK_COMPLETED_NOT_EVIDENCE",
                accepted_sources_completed=64,
                examined_attempts_completed=102,
                rejected_attempts_completed=38,
                cohort_reproduced=True,
                complete_seal_reproduced=True,
                complete_input_projection_reproduced=True,
            )
            return {"mock": True}

        for module, name, side, result in (
            (N, "_guard", action("guard"), None),
            (N.C, "unused", action("unused"), None),
            (N.core, "git_head", None, N.BASE),
            (N, "current_locations", action("locations", self.locations), None),
            (N, "attest", action("source", source), None),
            (V, "Evidence", None, evidence),
            (
                N,
                "inspect_metadata",
                action(
                    "metadata",
                    (
                        self.prior,
                        self.historical,
                        self.prior["sealed_metadata"],
                        self.prior["public_archive_hash_closures"],
                        self.mapping(),
                    ),
                ),
                None,
            ),
            (N, "stable_state", action("stable"), None),
            (N, "progress", None, None),
            (R, "environment", action("environment", self.environment), None),
            (N, "revalidate", action("revalidate"), None),
            (R, "load_inputs", action("inputs", self.inputs), None),
            (N, "replay_one", replay, None),
            (N, "reconstruct_seal", seal, None),
        ):
            stack.enter_context(
                patch.object(module, name, side_effect=side, return_value=result)
            )
        return events

    def test_whole_operation_requires_environment_public_public_then_original_cohort(
        self,
    ):
        events = self.operation()
        result = N.reconstruct("a" * 40)
        numerical = [
            e for e in events if e in ("environment", "inputs", *N.LABELS, "sealed")
        ]
        self.assertEqual(numerical, ["environment", "inputs", *N.LABELS, "sealed"])
        self.assertEqual(result["status"], N.STATUS)
        self.assertTrue(result["acceptance_order_reconstructed"])
        self.assertFalse(result["sealed_metadata"]["acceptance_order_reconstructed"])
        self.assertFalse(result["claim_ceiling"]["current_receiver_admitted"])

    def test_top_level_stops_before_later_phases_and_keeps_completed_counts(self):
        for failed in (
            "metadata",
            "environment",
            "original_public",
            "receiver_v2_public",
            "sealed",
        ):
            events = self.operation(**{failed: ValueError("injected " + failed)})
            with self.assertRaises(N.ReconstructionFailure) as caught:
                N.reconstruct("a" * 40)
            self.assertEqual(events[-1], failed)
            work = caught.exception.work
            baseline = (
                0 if failed == "metadata" else None if failed == "environment" else 32
            )
            self.assertEqual(work["baseline_traces_completed"], baseline)
            if failed in ("receiver_v2_public", "sealed"):
                self.assertEqual(
                    work["public_archives"][0]["replayed_traces_completed"], 1024
                )
            if failed == "sealed":
                self.assertEqual(
                    work["public_archives"][1]["replayed_traces_completed"], 1024
                )

    def test_stable_state_rejects_head_dirty_source_locations_and_fake_inputs(self):
        source = {**self.source, "implementation_revision": "a" * 40}
        for failure in ("head", "dirty", "source", "locations", "inputs"):
            evidence = SimpleNamespace(revalidate=Mock())
            with (
                patch.object(N, "_guard"),
                patch.object(
                    N.core,
                    "git_head",
                    return_value="b" * 40 if failure == "head" else N.BASE,
                ),
                patch.object(
                    N.core,
                    "git_bytes",
                    return_value=b"dirty" if failure == "dirty" else b"",
                ),
                patch.object(
                    N,
                    "current_locations",
                    return_value={} if failure == "locations" else self.locations,
                ),
                patch.object(N.C, "unused"),
                patch.object(
                    N, "attest", return_value={} if failure == "source" else source
                ),
                self.subTest(failure=failure),
                self.assertRaises(Exception),
            ):
                N.stable_state(
                    evidence,
                    source,
                    N.BASE,
                    self.locations,
                    SimpleNamespace() if failure == "inputs" else self.inputs,
                )

    def test_completed_baseline_retained_if_historical_environment_compare_fails(self):
        self.operation()
        with patch.object(
            E, "compare_environment", side_effect=ValueError("historical mismatch")
        ):
            with self.assertRaises(N.ReconstructionFailure) as caught:
                N.reconstruct("a" * 40)
        self.assertEqual(caught.exception.work["baseline_traces_completed"], 32)
        self.assertEqual(
            caught.exception.work["public_archives"][0]["replayed_traces_completed"], 0
        )

    def test_final_revalidation_failure_retains_all_completed_phases(self):
        self.operation()
        with patch.object(
            N, "revalidate", side_effect=[None, None, ValueError("final source drift")]
        ):
            with self.assertRaises(N.ReconstructionFailure) as caught:
                N.reconstruct("a" * 40)
        work = caught.exception.work
        self.assertEqual(
            caught.exception.phase, "final_source_runtime_evidence_revalidation"
        )
        self.assertEqual(work["baseline_traces_completed"], 32)
        self.assertEqual(
            [row["replayed_traces_completed"] for row in work["public_archives"]],
            [1024, 1024],
        )
        self.assertTrue(work["sealed_cohort"]["complete_input_projection_reproduced"])
        self.assertEqual(work["sealed_cohort"]["accepted_sources_completed"], 64)
        self.assertFalse(
            N.failure_receipt(caught.exception)["claim_ceiling"][
                "current_receiver_admitted"
            ]
        )

    def verification_wiring(self, *, change=None):
        """Saved comparator plus MOCK fresh full operation, not verification evidence."""
        stack = ExitStack()
        self.addCleanup(stack.close)
        source = {**self.source, "implementation_revision": "a" * 40}
        result = N.digested(
            dict(
                schema_version=N.DOMAIN + "/observation",
                status=N.STATUS,
                source=source,
                reconstruction_head=N.BASE,
                location_correspondence={"current_locations": self.locations},
                work=N.initial_work(),
                full_projection={"otherwise_unchecked_field": 1},
            )
        )
        expected = copy.deepcopy(result)
        if change == "field":
            expected["full_projection"]["otherwise_unchecked_field"] = 2
        elif change == "head":
            expected["reconstruction_head"] = "b" * 40
        elif change == "source":
            expected["source"] = {}
        elif change == "status":
            expected["status"] = "PARTIAL"
        expected = N.digested(B.without_digest(expected))
        saved = SimpleNamespace(raw=N.canonical(expected), revalidate=Mock())
        stack.enter_context(patch.object(N, "_guard"))
        stack.enter_context(patch.object(N.core, "git_head", return_value=N.BASE))
        stack.enter_context(patch.object(N.core, "git_bytes", return_value=b""))
        stack.enter_context(patch.object(R, "snapshot_file", return_value=saved))
        stack.enter_context(patch.object(N, "attest", return_value=source))
        stack.enter_context(
            patch.object(N, "current_locations", return_value=self.locations)
        )
        stack.enter_context(patch.object(N.C, "unused"))
        recompute = stack.enter_context(
            patch.object(N, "reconstruct", return_value=result)
        )
        return result, saved, recompute

    def test_saved_verification_recomputes_whole_operation_not_reference_only(self):
        result, saved, recompute = self.verification_wiring()
        verification = N.verify_saved("a" * 40)
        recompute.assert_called_once_with("a" * 40)
        self.assertEqual(saved.revalidate.call_count, 2)
        self.assertTrue(verification["complete_canonical_observation_byte_identical"])
        self.assertFalse(verification["algorithmically_independent_implementation"])
        self.assertEqual(
            verification["independently_reconstructed_observation"],
            N.reference(N.canonical(result)),
        )

    def test_verification_compares_even_unselected_full_result_field(self):
        result, _, recompute = self.verification_wiring(change="field")
        with self.assertRaises(N.ReconstructionFailure) as caught:
            N.verify_saved("a" * 40)
        recompute.assert_called_once()
        self.assertEqual(caught.exception.phase, "whole_result_byte_comparison")
        self.assertEqual(caught.exception.work, result["work"])

    def test_verification_rejects_stale_partial_or_other_source_before_recompute(self):
        for change in ("head", "source", "status"):
            _, _, recompute = self.verification_wiring(change=change)
            with self.assertRaises(N.ReconstructionFailure):
                N.verify_saved("a" * 40)
            recompute.assert_not_called()

    def test_verification_preserves_partial_reconstruction_failure(self):
        _, _, recompute = self.verification_wiring()
        work = N.initial_work()
        work["sealed_cohort"]["accepted_sources_completed"] = None
        original = N.ReconstructionFailure(ValueError("partial"), "sealed", work)
        recompute.side_effect = original
        with self.assertRaises(N.ReconstructionFailure) as caught:
            N.verify_saved("a" * 40)
        self.assertIs(caught.exception, original)

    def test_verification_snapshot_drift_after_recompute_rejects(self):
        result, saved, recompute = self.verification_wiring()
        saved.revalidate.side_effect = [None, ValueError("saved bytes changed")]
        with self.assertRaises(N.ReconstructionFailure) as caught:
            N.verify_saved("a" * 40)
        recompute.assert_called_once()
        self.assertEqual(caught.exception.work, result["work"])

    def test_verification_final_source_location_and_dirty_drift_rejects(self):
        for failure in ("source", "locations", "dirty"):
            result, _, recompute = self.verification_wiring()
            with ExitStack() as stack:
                if failure == "source":
                    stack.enter_context(
                        patch.object(N, "attest", side_effect=[result["source"], {}])
                    )
                elif failure == "locations":
                    stack.enter_context(
                        patch.object(N, "current_locations", return_value={})
                    )
                else:
                    stack.enter_context(
                        patch.object(N.core, "git_bytes", return_value=b"dirty")
                    )
                with self.assertRaises(N.ReconstructionFailure) as caught:
                    N.verify_saved("a" * 40)
            recompute.assert_called_once()
            self.assertEqual(caught.exception.work, result["work"])

    def test_both_numerical_cli_modes_require_immutable_revision(self):
        environment = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
        for mode in ("--reconstruct", "--verify-saved"):
            result = subprocess.run(
                [sys.executable, "-P", "-B", str(ROOT / N.SCRIPT), mode],
                cwd="/tmp",
                env=environment,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn(b"full immutable implementation revision", result.stderr)

    def test_failure_delivery_keeps_completed_work_and_no_authority(self):
        work = N.initial_work()
        work["sealed_cohort"]["accepted_sources_completed"] = 64
        receipt = N.failure_receipt(OSError("stdout closed"), {"work": work})
        self.assertEqual(receipt["phase"], "result_delivery")
        self.assertEqual(receipt["work"], work)
        self.assertFalse(receipt["automatic_retry_allowed"])
        self.assertFalse(receipt["claim_ceiling"]["current_receiver_admitted"])
        for consumed in (False, True):
            failure = S.ExecutionFailure("KNOWN_STATE", consumed, "known state")
            receipt = N.failure_receipt(N.ReconstructionFailure(failure, "scope", work))
            self.assertIs(receipt["authorization_consumed"], consumed)

    def test_selected_callable_substitutions_rejected(self):
        for module, name, _ in N._DEPENDENCIES:
            with patch.object(module, name, Mock()):
                with self.subTest(name=name), self.assertRaises(Exception):
                    N._guard()

    def test_no_old_admission_publication_or_sealed_loader_calls(self):
        tree = ast.parse((ROOT / N.SCRIPT).read_text())
        forbidden = {
            "admit",
            "analyze",
            "inspect_transport",
            "qualified_public",
            "load_seal",
            "seal_cohort",
            "verify_generation_reference",
            "verify_original_seal",
            "certificate_projection",
            "atomic_write",
            "fsync",
            "unlink",
            "mkdir",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                self.assertNotIn(node.func.attr, forbidden)
        self.assertEqual(
            tuple(inspect.signature(N.reconstruct).parameters), ("revision",)
        )
        self.assertEqual(
            tuple(inspect.signature(N.verify_saved).parameters), ("revision",)
        )
        self.assertNotIn("calibrations", inspect.getsource(N.reconstruct_seal))

    def test_static_cli_from_outside_and_no_path_device_or_proof_overrides(self):
        environment = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
        command = [sys.executable, "-P", "-B", str(ROOT / N.SCRIPT)]
        completed = subprocess.run(
            command + ["--self-test"],
            cwd="/tmp",
            env=environment,
            capture_output=True,
            check=True,
        )
        value = N.parse(completed.stdout)
        self.assertEqual(value["status"], "STATIC_SELF_TEST_ONLY")
        self.assertEqual(
            value["work"]["sealed_cohort"]["accepted_sources_completed"], 0
        )
        for extra in (
            ["--path", "/tmp"],
            ["--device", "16777234"],
            ["--proof", "saved"],
            ["--self-test", "--implementation-revision", "a" * 40],
        ):
            args = extra if "--self-test" in extra else ["--self-test", *extra]
            result = subprocess.run(
                command + args,
                cwd="/tmp",
                env=environment,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
