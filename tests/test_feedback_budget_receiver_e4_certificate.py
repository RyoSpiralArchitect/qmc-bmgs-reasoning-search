"""Read-only certifier boundary tests. MOCK numerics are never scientific evidence."""

from __future__ import annotations

import ast
from contextlib import ExitStack
import copy
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import struct
import sys
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "e4_certificate_tested", ROOT / "scripts/feedback_budget_receiver_e4_certificate.py"
)
assert SPEC is not None and SPEC.loader is not None
K = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = K
SPEC.loader.exec_module(K)
N, E, V, C, B, R, S = K.N, K.E, K.V, K.C, K.B, K.R, K.S


def read(path):
    return K.parse((ROOT / path).read_bytes())


def rehash(value):
    value = copy.deepcopy(value)
    value.pop("deterministic_digest", None)
    return K.digested(value)


class ReceiverE4Certificate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old = read(K.historical_references()["observation"]["path"])
        cls.source = K.digested(
            dict(
                schema_version=K.DOMAIN + "/source",
                implementation_revision="a" * 40,
                design_revision=K.DESIGN_REVISION,
                files={
                    name: dict(byte_count=0, sha256=K.sha(b""))
                    for name in K.SOURCE_FILES
                },
                frozen_reconstruction=cls.old["source"],
            )
        )
        cls.screens = dict(original_public=False, receiver_v2_public=False)
        cls.template = K._projection(cls.old, cls.source, cls.screens)
        live = cls.old["location_correspondence"]["current_locations"]
        cls.locations = dict(
            live_locations=copy.deepcopy(live),
            persistent_locations=K._persistent_locations(live),
        )
        cls.values = {path: read(path) for path, _ in V.ANCHORS}
        # Genuine PUBLIC metadata only, not environment baseline or numerical replay.
        cls.inputs = R.load_inputs(S.PUBLIC)

    def test_static_self_test_has_no_science_or_issuance(self):
        result = K.self_test()
        self.assertEqual(result["status"], "STATIC_SELF_TEST_ONLY")
        self.assertEqual(result["work"], N.initial_work())
        self.assertIs(result["certificate_issued"], False)
        self.assertEqual(set(K.CERTIFICATE_KEYS), set(self.template))
        self.assertEqual(set(K.FRESH_KEYS + K.HISTORICAL_KEYS), set(self.old))
        self.assertEqual((len(K.FRESH_KEYS), len(K.HISTORICAL_KEYS)), (16, 7))

    def test_closed_exact_three_file_source(self):
        K.closed_source({name: {} for name in K.SOURCE_FILES})
        for files in (
            {},
            {K.SCRIPT: {}},
            dict.fromkeys((*K.SOURCE_FILES, "extra")),
            [],
        ):
            with self.subTest(files=files), self.assertRaises(Exception):
                K.closed_source(files)
        with patch.object(K, "SOURCE_FILES", (K.SCRIPT, K.TEST)):
            with self.assertRaisesRegex(Exception, "registry"):
                K.closed_source({name: {} for name in (K.SCRIPT, K.TEST, K.POLICY)})

    def attestation(self, *, head=None, frozen=None):
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(
            patch.object(K.core, "git_head", return_value=head or "b" * 40)
        )
        ancestor = stack.enter_context(patch.object(K.core, "require_ancestor"))
        stack.enter_context(patch.object(R, "oid", side_effect=lambda value: value))
        stack.enter_context(patch.object(R.public, "_origin"))
        stack.enter_context(
            patch.object(N, "attest", return_value=frozen or self.old["source"])
        )
        items = [
            SimpleNamespace(raw=(name + "\n").encode(), revalidate=Mock())
            for name in K.SOURCE_FILES
        ]
        capture = stack.enter_context(
            patch.object(R, "snapshot_file", side_effect=items)
        )
        reviewed = stack.enter_context(patch.object(R, "reviewed_file"))
        return ancestor, items, capture, reviewed

    def test_source_attestation_chains_all_three_new_files_and_frozen_source(self):
        ancestor, items, capture, reviewed = self.attestation()
        result = K.attest("a" * 40)
        self.assertEqual(result["design_revision"], K.DESIGN_REVISION)
        self.assertEqual(result["frozen_reconstruction"], self.old["source"])
        self.assertEqual(set(result["files"]), set(K.SOURCE_FILES))
        self.assertEqual(
            [c.args[0] for c in capture.call_args_list],
            [ROOT / p for p in K.SOURCE_FILES],
        )
        self.assertEqual(
            [c.args for c in reviewed.call_args_list],
            [(item, "a" * 40) for item in items],
        )
        self.assertEqual(
            [c.args[1:] for c in ancestor.call_args_list],
            [(K.DESIGN_REVISION, "a" * 40), ("a" * 40, "b" * 40)],
        )
        for item in items:
            item.revalidate.assert_called_once()

    def test_attestation_rejects_frozen_source_drift(self):
        frozen = dict(self.old["source"], deterministic_digest="0" * 64)
        _, _, capture, _ = self.attestation(frozen=frozen)
        with self.assertRaisesRegex(Exception, "frozen E4"):
            K.attest("a" * 40)
        capture.assert_not_called()

    def test_attestation_rejects_head_or_file_drift(self):
        _, items, _, _ = self.attestation()
        with patch.object(K.core, "git_head", side_effect=["b" * 40, "c" * 40]):
            with self.assertRaisesRegex(Exception, "HEAD changed"):
                K.attest("a" * 40)
        self.assertTrue(all(item.revalidate.called for item in items))

    def test_attestation_rejects_unreviewed_source_file(self):
        _, _, _, reviewed = self.attestation()
        reviewed.side_effect = ValueError("reviewed source differs")
        with self.assertRaisesRegex(Exception, "reviewed source differs"):
            K.attest("a" * 40)

    def test_attestation_revalidates_captured_source_generations(self):
        _, items, _, _ = self.attestation()
        items[-1].revalidate.side_effect = ValueError("source file replaced")
        with self.assertRaisesRegex(Exception, "source file replaced"):
            K.attest("a" * 40)

    def test_later_review_head_does_not_change_frozen_source_projection(self):
        self.attestation(head="b" * 40)
        first = K.attest("a" * 40)
        self.attestation(head="c" * 40)
        later = K.attest("a" * 40)
        self.assertEqual(K.canonical(first), K.canonical(later))
        self.assertNotIn("operation_head", first)

    def test_attestation_rejects_short_oid_and_wrong_origin(self):
        with self.assertRaises(Exception):
            K.attest("HEAD")
        self.attestation()
        with patch.object(K, "__file__", str(ROOT / "elsewhere.py")):
            with self.assertRaisesRegex(Exception, "origin"):
                K.attest("a" * 40)

    def test_historical_records_are_fixed_authenticated_metadata_only(self):
        evidence = V.Evidence()
        result = K.historical(evidence, self.old["source"])
        self.assertEqual(result, self.old)
        self.assertEqual(len(evidence.snapshots), 3)
        self.assertEqual(evidence.anchors, {})
        self.assertEqual(len(K._LIVE), 0)

    def test_all_pinned_records_checked_before_any_json_parse(self):
        for bad_label in K.PINS:
            refs = K.historical_references()
            items = {
                ROOT / ref["path"]: SimpleNamespace(
                    raw=(ROOT / ref["path"]).read_bytes(), revalidate=Mock()
                )
                for ref in refs.values()
            }
            items[ROOT / refs[bad_label]["path"]].raw += b" "
            evidence = SimpleNamespace(file=lambda path: items[path], revalidate=Mock())
            with patch.object(R, "reviewed_file"), patch.object(K, "parse") as parse:
                with self.assertRaisesRegex(Exception, "pinned E4 historical bytes"):
                    K.historical(evidence, self.old["source"])
                parse.assert_not_called()

    def test_historical_review_failure_precedes_parse(self):
        with (
            patch.object(R, "reviewed_file", side_effect=ValueError("not reviewed")),
            patch.object(K, "parse") as parse,
        ):
            with self.assertRaisesRegex(Exception, "not reviewed"):
                K.historical(V.Evidence(), self.old["source"])
            parse.assert_not_called()

    def test_historical_paths_cannot_redirect(self):
        refs = K.historical_references()
        refs["observation"]["path"] = "/caller/target.json"
        self.assertNotEqual(refs, K.historical_references())
        self.assertEqual(
            set(K.historical_references()),
            {"observation", "verification", "operations"},
        )
        self.assertTrue(
            all(
                ref["reviewed_revision"] == K.HISTORICAL_REVIEW
                for ref in K.historical_references().values()
            )
        )

    def test_template_is_not_a_capture_or_certificate_issue(self):
        raw = K.canonical(self.template)
        K._compare_certificate(raw, self.template)
        for supplied in (
            self.old,
            self.template,
            raw,
            SimpleNamespace(status="PASS"),
            lambda: raw,
        ):
            with self.subTest(supplied=type(supplied)), self.assertRaises(Exception):
                K._LiveCapture(supplied)
            with self.assertRaises(Exception):
                K.operation_receipt(supplied)
        self.assertEqual(len(K._LIVE), 0)

    def test_unregistered_object_and_subclass_cannot_supply_live_evidence(self):
        class Forged(K._LiveCapture):
            pass

        for value in (object.__new__(K._LiveCapture), object.__new__(Forged)):
            with self.assertRaisesRegex(Exception, "registered genuine"):
                K._state(value)

    def test_certificate_closed_top_level_missing_extra_and_old_domains(self):
        for key in K.CERTIFICATE_KEYS:
            wrong = copy.deepcopy(self.template)
            wrong.pop(key)
            with self.subTest(key=key), self.assertRaises(Exception):
                changed = wrong if key == "deterministic_digest" else rehash(wrong)
                K._compare_certificate(K.canonical(changed), self.template)
        for wrong in (
            dict(self.template, extra=True),
            dict(self.template, schema_version=N.DOMAIN + "/observation"),
            self.old,
        ):
            with self.assertRaises(Exception):
                K._compare_certificate(K.canonical(rehash(wrong)), self.template)

    def test_every_nested_object_has_no_ignored_extension_field(self):
        def paths(value, prefix=()):
            if type(value) is dict:
                yield prefix
                for key, child in value.items():
                    yield from paths(child, (*prefix, key))
            elif type(value) is list:
                for index, child in enumerate(value):
                    yield from paths(child, (*prefix, index))

        # Exact whole-byte comparison closes even inherited nested objects.
        for path in paths(self.template):
            wrong = copy.deepcopy(self.template)
            parent = wrong
            for key in path:
                parent = parent[key]
            parent["unreviewed_extension"] = 0
            with self.subTest(path=path), self.assertRaises(Exception):
                K._compare_certificate(K.canonical(rehash(wrong)), self.template)

    def test_bool_float_and_count_aliases_rejected_after_rehash(self):
        for path in (
            ("case", "historical_device"),
            ("study", "accepted_source_multisets"),
            ("reconstruction", "public_traces_replayed"),
            ("claim_ceiling", "new_public_attempts"),
            ("claim_ceiling", "replication_policy_search_calls"),
            ("claim_ceiling", "replication_cells_executed"),
        ):
            for alias in (True, False, float(self.template[path[0]][path[1]])):
                wrong = copy.deepcopy(self.template)
                wrong[path[0]][path[1]] = alias
                with self.subTest(path=path, alias=alias), self.assertRaises(Exception):
                    K._compare_certificate(K.canonical(rehash(wrong)), self.template)
        wrong = copy.deepcopy(self.template)
        wrong["claim_ceiling"]["current_receiver_admitted"] = 0
        with self.assertRaises(Exception):
            K._compare_certificate(K.canonical(rehash(wrong)), self.template)

    def test_noncanonical_duplicate_nonfinite_and_digest_mutations_rejected(self):
        raw = K.canonical(self.template)
        bad = (
            raw + b"\n",
            b" " + raw,
            raw.replace(b'"status":', b'"status":null,"status":', 1),
            raw.replace(b'"historical_device":16777234', b'"historical_device":NaN', 1),
            K.canonical(dict(self.template, deterministic_digest="0" * 64)),
        )
        for changed in bad:
            with self.subTest(prefix=changed[:40]), self.assertRaises(Exception):
                K._compare_certificate(changed, self.template)

    def test_all_23_chains_and_negative_results_preserved(self):
        mapping = self.template["historical_location_correspondence"]
        self.assertEqual(
            len(mapping["original_chains"]) + len(mapping["prior_observation_chains"]),
            23,
        )
        self.assertEqual(mapping, self.old["location_correspondence"])
        self.assertIs(mapping["repeated_device_number_is_epoch_identity"], False)
        self.assertEqual(
            self.template["reconstruction"]["historical_screen_conjunction"],
            self.screens,
        )
        wrong = copy.deepcopy(self.template)
        wrong["historical_location_correspondence"][
            "prior_observation_chains"
        ].reverse()
        with self.assertRaises(Exception):
            K._compare_certificate(K.canonical(rehash(wrong)), self.template)

    def test_negative_screen_or_epoch_owner_rewrite_rejected(self):
        for field in ("owner", "historical_epoch"):
            wrong = copy.deepcopy(self.template)
            wrong["historical_location_correspondence"]["prior_observation_chains"][0][
                field
            ] = "rewritten"
            with self.assertRaises(Exception):
                K._compare_certificate(K.canonical(rehash(wrong)), self.template)
        with self.assertRaises(Exception):
            K._projection(
                self.old,
                self.source,
                dict(original_public=True, receiver_v2_public=False),
            )

    def test_original_generation_identity_paths_and_no_hash_cycle(self):
        study = self.template["study"]
        self.assertEqual(
            study["original_generation_reference"],
            self.old["public_replays"][0]["original_generation_reference"],
        )
        self.assertEqual(study["fixed_replication_claim_path"], str(B.fixed_claim()))
        self.assertEqual(
            (study["output_path"], study["summary_path"]),
            (str(B.OUTPUT), str(C.REPLICATION_SUMMARY)),
        )
        self.assertNotIn("verification", self.template)
        self.assertNotIn("operation_head", self.template)
        self.assertNotIn("certificate_issued", self.template["claim_ceiling"])
        self.assertNotIn("authorization", self.template)
        self.assertEqual(
            self.template["historical_e4"]["reconstruction_head"], K.FROZEN_REVISION
        )

    def operation(self, **failures):
        """MOCK ordered wiring, never genuine baseline/PUBLIC/cohort work."""
        stack, events = ExitStack(), []
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(K, "_RECONSTRUCTION_STARTED", False))
        stack.enter_context(patch.object(K, "_guard"))
        stack.enter_context(patch.object(N, "progress"))
        evidence = SimpleNamespace(
            values=copy.deepcopy(self.values),
            anchors=copy.deepcopy(self.old["reviewed_anchors"]),
            revalidate=Mock(),
            file=Mock(),
        )

        def action(name, result=None):
            def call(*args):
                events.append(name)
                if name in failures:
                    raise failures[name]
                return copy.deepcopy(result) if type(result) is dict else result

            return call

        def replay(label, evidence, inputs, environment, history, work):
            self.assertIs(inputs, self.inputs)
            events.append(label)
            if label in failures:
                work["public_archives"][N.LABELS.index(label)][
                    "replayed_traces_completed"
                ] = None
                raise failures[label]
            index = N.LABELS.index(label)
            work["public_archives"][index] = copy.deepcopy(
                self.old["work"]["public_archives"][index]
            )
            return copy.deepcopy(self.old["public_replays"][index])

        def seal(evidence, environment, reference, work):
            events.append("seal")
            self.assertEqual(
                reference,
                self.old["public_replays"][0]["original_generation_reference"],
            )
            if "seal" in failures:
                work["sealed_cohort"]["examined_attempts_completed"] = None
                raise failures["seal"]
            work["sealed_cohort"] = copy.deepcopy(self.old["work"]["sealed_cohort"])
            return copy.deepcopy(self.old["original_sealed_reconstruction"])

        stack.enter_context(patch.object(C, "unused", side_effect=action("unused")))
        stack.enter_context(patch.object(K.core, "git_head", return_value="b" * 40))
        stack.enter_context(
            patch.object(K, "_capture_locations", return_value=self.locations)
        )
        stack.enter_context(
            patch.object(K, "attest", side_effect=action("source", self.source))
        )
        stack.enter_context(patch.object(V, "Evidence", return_value=evidence))
        history = stack.enter_context(
            patch.object(K, "historical", side_effect=action("historical", self.old))
        )
        metadata = stack.enter_context(
            patch.object(
                N,
                "inspect_metadata",
                side_effect=action(
                    "metadata",
                    (
                        self.old,
                        self.old["historical_source_receipts"],
                        self.old["sealed_metadata"],
                        self.old["public_archive_hash_closures"],
                        self.old["location_correspondence"],
                    ),
                ),
            )
        )
        stack.enter_context(patch.object(K, "_stable", side_effect=action("stable")))
        revalidate = stack.enter_context(
            patch.object(K, "_revalidate", side_effect=action("revalidate"))
        )
        environment = stack.enter_context(
            patch.object(
                R,
                "environment",
                side_effect=action("environment", self.old["environment"]),
            )
        )
        stack.enter_context(
            patch.object(
                E, "compare_environment", side_effect=action("environment_comparison")
            )
        )
        loader = stack.enter_context(
            patch.object(
                R, "load_inputs", side_effect=action("load_public", self.inputs)
            )
        )
        public = stack.enter_context(patch.object(N, "replay_one", side_effect=replay))
        sealed = stack.enter_context(
            patch.object(N, "reconstruct_seal", side_effect=seal)
        )
        return SimpleNamespace(
            events=events,
            evidence=evidence,
            history=history,
            metadata=metadata,
            revalidate=revalidate,
            environment=environment,
            loader=loader,
            public=public,
            sealed=sealed,
        )

    def test_ordered_genuine_calls_required_then_private_capture_registered(self):
        wiring = self.operation()
        capture = K.reconstruct("a" * 40)
        self.assertIs(type(capture), K._LiveCapture)
        self.assertEqual(capture.certificate_raw, K.canonical(self.template))
        self.assertEqual(
            [e for e in wiring.events if e not in ("revalidate", "stable")],
            [
                "unused",
                "source",
                "historical",
                "metadata",
                "environment",
                "environment_comparison",
                "load_public",
                "original_public",
                "receiver_v2_public",
                "seal",
            ],
        )
        wiring.environment.assert_called_once_with(B.ORIGINAL_SOURCE)
        wiring.loader.assert_called_once_with(S.PUBLIC)
        self.assertEqual(wiring.public.call_count, 2)
        wiring.sealed.assert_called_once()
        self.assertGreaterEqual(wiring.revalidate.call_count, 7)
        before = wiring.revalidate.call_count
        receipt = K.operation_receipt(capture)
        self.assertEqual(wiring.revalidate.call_count, before + 1)
        self.assertEqual(receipt["work"], self.old["work"])
        self.assertIs(receipt["certificate_issued"], False)

    def test_no_receipt_shortcut_if_environment_fails(self):
        wiring = self.operation(environment=ValueError("baseline failed"))
        with self.assertRaises(K.CertificateFailure) as caught:
            K.reconstruct("a" * 40)
        self.assertIsNone(caught.exception.work["baseline_traces_completed"])
        wiring.public.assert_not_called()
        wiring.sealed.assert_not_called()

    def test_original_unused_failure_stops_before_numerical_work(self):
        wiring = self.operation(unused=ValueError("original claim occupied"))
        with self.assertRaises(K.CertificateFailure) as caught:
            K.reconstruct("a" * 40)
        self.assertEqual(caught.exception.work, N.initial_work())
        wiring.environment.assert_not_called()
        wiring.public.assert_not_called()
        wiring.sealed.assert_not_called()

    def test_completed_baseline_retained_on_environment_comparison_failure(self):
        self.operation(environment_comparison=ValueError("environment differs"))
        with self.assertRaises(K.CertificateFailure) as caught:
            K.reconstruct("a" * 40)
        self.assertEqual(caught.exception.work["baseline_traces_completed"], 32)

    def test_separate_public_and_cohort_failures_retain_completed_work(self):
        for failure in (*N.LABELS, "seal"):
            wiring = self.operation(**{failure: ValueError("stage failed")})
            with (
                self.subTest(stage=failure),
                self.assertRaises(K.CertificateFailure) as caught,
            ):
                K.reconstruct("a" * 40)
            work = caught.exception.work
            self.assertEqual(work["baseline_traces_completed"], 32)
            if failure != "original_public":
                self.assertEqual(
                    work["public_archives"][0]["replayed_traces_completed"], 1024
                )
            if failure == "seal":
                self.assertEqual(
                    work["public_archives"][1]["replayed_traces_completed"], 1024
                )
                self.assertIsNone(work["sealed_cohort"]["examined_attempts_completed"])
            else:
                wiring.sealed.assert_not_called()

    def test_all_16_fresh_fields_compared_whole_not_selected_success_flags(self):
        for key in K.FRESH_KEYS:
            wiring = self.operation()
            old = copy.deepcopy(self.old)
            old[key] = {"changed": old[key]}
            wiring.history.side_effect = None
            wiring.history.return_value = old
            with self.subTest(key=key), self.assertRaises(K.CertificateFailure):
                K.reconstruct("a" * 40)

    def test_forged_loader_rejected_before_any_replay(self):
        wiring = self.operation()
        wiring.loader.side_effect = None
        wiring.loader.return_value = SimpleNamespace()
        with self.assertRaisesRegex(K.CertificateFailure, "genuine PUBLIC loader"):
            K.reconstruct("a" * 40)
        wiring.public.assert_not_called()

    def test_no_capture_on_final_revalidation_failure(self):
        wiring = self.operation()

        def final(*args):
            if "seal" in wiring.events:
                raise ValueError("final state drift")

        wiring.revalidate.side_effect = final
        count = len(K._LIVE)
        with self.assertRaises(K.CertificateFailure) as caught:
            K.reconstruct("a" * 40)
        self.assertEqual(caught.exception.work, self.old["work"])
        self.assertEqual(len(K._LIVE), count)

    def test_capture_revalidation_retains_evidence_not_just_result_bytes(self):
        wiring = self.operation()
        capture = K.reconstruct("a" * 40)
        wiring.revalidate.reset_mock()
        capture.revalidate()
        args = wiring.revalidate.call_args.args
        self.assertIs(args[0], wiring.evidence)
        self.assertIs(args[-1], self.inputs)
        self.assertEqual(args[4], "b" * 40)
        wiring.revalidate.side_effect = ValueError("current state differs")
        with self.assertRaisesRegex(Exception, "current state differs"):
            K.operation_receipt(capture)
        self.assertIs(type(capture.certificate_raw), bytes)
        with self.assertRaises(AttributeError):
            capture.certificate_raw = b"forged"

    def test_process_attempt_cannot_retry_or_resume(self):
        wiring = self.operation()
        capture = K.reconstruct("a" * 40)
        self.assertTrue(capture.certificate_raw)
        with self.assertRaisesRegex(K.CertificateFailure, "fresh process"):
            K.reconstruct("a" * 40)
        wiring.environment.assert_called_once()

    def test_stable_checks_both_new_and_old_sources_and_operation_head(self):
        with (
            patch.object(K, "_guard"),
            patch.object(K.core, "git_head", return_value="b" * 40),
            patch.object(K, "attest", return_value=self.source) as attest,
            patch.object(
                K, "_capture_locations", return_value=self.locations
            ) as locations,
            patch.object(C, "unused") as unused,
            patch.object(K.core, "git_bytes", return_value=b""),
            patch.object(N, "stable_state") as old,
        ):
            evidence = SimpleNamespace(revalidate=Mock())
            K._stable(evidence, self.source, "b" * 40, self.locations, self.inputs)
            self.assertEqual(attest.call_count, 2)
            # attest still chains N.attest(FROZEN_REVISION); its obsolete
            # device-number stability entry point must not be invoked.
            old.assert_not_called()
            self.assertEqual(locations.call_count, 2)
            self.assertEqual(unused.call_count, 2)
            self.assertEqual(evidence.revalidate.call_count, 2)

    def test_stable_rejects_new_source_or_head_drift(self):
        for head, source in (
            ("c" * 40, self.source),
            ("b" * 40, dict(self.source, files={})),
        ):
            with (
                patch.object(K, "_guard"),
                patch.object(K.core, "git_head", return_value=head),
                patch.object(K, "attest", return_value=source),
                patch.object(N, "stable_state"),
            ):
                with self.subTest(head=head), self.assertRaises(Exception):
                    K._stable(object(), self.source, "b" * 40, self.locations)

    def test_stable_does_not_bypass_original_unused_or_location_check(self):
        with (
            patch.object(K, "_guard"),
            patch.object(K.core, "git_head", return_value="b" * 40),
            patch.object(K, "attest", return_value=self.source),
            patch.object(
                C,
                "unused",
                side_effect=ValueError("original slot or location changed"),
            ),
            patch.object(K, "_capture_locations", return_value=self.locations),
        ):
            with self.assertRaisesRegex(Exception, "original slot"):
                K._stable(
                    SimpleNamespace(revalidate=Mock()),
                    self.source,
                    "b" * 40,
                    self.locations,
                )

    def test_revalidate_brackets_full_frozen_runtime_check(self):
        with (
            patch.object(K, "_stable") as stable,
            patch.object(
                V,
                "historical_sources",
                return_value=self.old["historical_source_receipts"],
            ) as history,
            patch.object(R, "check_environment") as runtime,
        ):
            evidence = object()
            K._revalidate(
                evidence,
                self.source,
                self.old["historical_source_receipts"],
                self.old["environment"],
                "b" * 40,
                self.locations,
                self.inputs,
            )
            self.assertEqual(stable.call_count, 2)
            history.assert_called_once_with()
            runtime.assert_called_once_with(self.old["environment"])

    def test_uuid_attribute_requires_complete_nonzero_value(self):
        raw = struct.pack("=I", 20) + uuid.UUID(K.DATA_VOLUME_UUID).bytes
        self.assertEqual(K._uuid_buffer(raw), K.DATA_VOLUME_UUID)
        for malformed in (
            raw[:-1],
            raw + b"x",
            bytes(20),
            struct.pack("=I", 19) + raw[4:],
            struct.pack("=I", 20) + bytes(16),
            bytearray(raw),
        ):
            with self.subTest(raw=malformed), self.assertRaises(Exception):
                K._uuid_buffer(malformed)

    def test_no_uuid_fallback_on_unsupported_platform_or_query_failure(self):
        with patch.object(K.sys, "platform", "linux"):
            with self.assertRaisesRegex(Exception, "requires macOS"):
                K._volume_uuid(1)
        library = SimpleNamespace(fgetattrlist=Mock(return_value=-1))
        with (
            patch.object(K.sys, "platform", "darwin"),
            patch.object(K.ctypes, "CDLL", return_value=library),
        ):
            with self.assertRaisesRegex(Exception, "no device-number fallback"):
                K._volume_uuid(1)

    def capture_fixture(self, *, device=100, wrong_uuid=False, drift=False):
        """Synthetic descriptor metadata; no host volume claim or reconstruction."""
        stack = ExitStack()
        self.addCleanup(stack.close)
        live = copy.deepcopy(self.locations["live_locations"])
        for location in live.values():
            for pair in location["identities"]:
                pair[0] = device
        after = copy.deepcopy(live)
        if drift:
            after["cohort"]["identities"][-1][0] += 1
        stack.enter_context(
            patch.object(V, "current_locations", side_effect=[live, after])
        )
        parents = []

        def opened(path):
            location = next(
                x for x in live.values() if Path(x["path"]).is_relative_to(path)
            )
            parent = SimpleNamespace(
                descriptor=0 if str(path) == "/" else 1,
                component_identities=tuple(
                    tuple(p) for p in location["identities"][: len(path.parts)]
                ),
                assert_path=Mock(),
                close=Mock(),
            )
            parents.append(parent)
            return parent

        stack.enter_context(
            patch.object(S.mechanics._PinnedParent, "open", side_effect=opened)
        )
        stack.enter_context(
            patch.object(
                K,
                "_volume_uuid",
                side_effect=lambda fd: (
                    "00000000-0000-0000-0000-000000000001"
                    if wrong_uuid
                    else K.ROOT_VOLUME_UUID
                    if fd == 0
                    else K.DATA_VOLUME_UUID
                ),
            )
        )
        return live, parents

    def test_persistent_capture_accepts_new_boot_local_number(self):
        live, parents = self.capture_fixture(device=16777229)
        captured = K._capture_locations()
        self.assertEqual(captured["live_locations"], live)
        self.assertEqual(
            captured["persistent_locations"], self.locations["persistent_locations"]
        )
        self.assertTrue(parents)
        for parent in parents:
            parent.assert_path.assert_called_once_with()
            parent.close.assert_called_once_with()

    def test_capture_rejects_same_inode_on_wrong_volume(self):
        _, parents = self.capture_fixture(wrong_uuid=True)
        with self.assertRaisesRegex(Exception, "volume UUID differs"):
            K._capture_locations()
        self.assertTrue(all(p.close.called for p in parents))

    def test_capture_rejects_device_change_during_observation(self):
        self.capture_fixture(drift=True)
        with self.assertRaisesRegex(Exception, "changed during UUID capture"):
            K._capture_locations()

    def test_uuid_read_failure_closes_descriptor_without_fallback(self):
        _, parents = self.capture_fixture()
        with patch.object(
            K, "_volume_uuid", side_effect=ValueError("UUID unavailable")
        ):
            with self.assertRaisesRegex(Exception, "UUID unavailable"):
                K._capture_locations()
        self.assertEqual(len(parents), 1)
        parents[0].close.assert_called_once_with()

    def test_device_changes_between_operations_do_not_rewrite_history(self):
        old_raw = K.canonical(self.old)
        migrated = copy.deepcopy(self.locations)
        for location in migrated["live_locations"].values():
            for pair in location["identities"]:
                pair[0] += 50
        returned = K._historical_locations(self.old, migrated)
        self.assertEqual(
            returned, self.old["location_correspondence"]["current_locations"]
        )
        self.assertEqual(K.canonical(self.old), old_raw)
        identity = self.template["receiver_identity"]
        self.assertNotIn("device", self.template["case"])
        self.assertEqual(self.template["case"]["historical_device"], 16777234)
        self.assertIs(identity["historical_volume_uuid_recorded"], False)
        self.assertIs(identity["historical_physical_volume_continuity_proven"], False)
        self.assertEqual(
            identity["persistent_locations"], migrated["persistent_locations"]
        )

    def test_migration_rejects_inode_path_uuid_role_or_type_drift(self):
        for kind in ("inode", "path", "uuid", "role", "type", "extra"):
            bad = copy.deepcopy(self.locations)
            live = bad["live_locations"]["cohort"]
            if kind == "inode":
                live["identities"][-1][1] += 1
            elif kind == "path":
                live["path"] += "-other"
            elif kind == "uuid":
                bad["persistent_locations"]["cohort"]["components"][-1][
                    "volume_uuid"
                ] = K.ROOT_VOLUME_UUID
            elif kind == "role":
                bad["live_locations"].pop("ledger")
            elif kind == "type":
                live["identities"][-1][0] = True
            else:
                live["unrecognized"] = True
            with self.subTest(kind=kind), self.assertRaises(Exception):
                K._historical_locations(self.old, bad)

    def test_stable_still_rejects_live_device_drift_with_unchanged_uuid(self):
        changed = copy.deepcopy(self.locations)
        changed["live_locations"]["cohort"]["identities"][-1][0] += 1
        with (
            patch.object(K, "_guard"),
            patch.object(K.core, "git_head", return_value="b" * 40),
            patch.object(K, "attest", return_value=self.source),
            patch.object(K, "_capture_locations", return_value=changed),
        ):
            with self.assertRaisesRegex(Exception, "identity changed during operation"):
                K._stable(
                    SimpleNamespace(revalidate=Mock()),
                    self.source,
                    "b" * 40,
                    self.locations,
                )

    def test_uuid_or_inode_failure_stops_before_numerics(self):
        wiring = self.operation()
        changed = copy.deepcopy(self.locations)
        changed["persistent_locations"]["cohort"]["components"][-1]["volume_uuid"] = (
            K.ROOT_VOLUME_UUID
        )
        with patch.object(K, "_capture_locations", return_value=changed):
            with self.assertRaisesRegex(K.CertificateFailure, "persistent receiver"):
                K.reconstruct("a" * 40)
        wiring.environment.assert_not_called()
        wiring.public.assert_not_called()
        wiring.sealed.assert_not_called()

    def test_current_identity_receipt_is_detached_and_not_certificate_authority(self):
        self.operation()
        capture = K.reconstruct("a" * 40)
        before = K.canonical(K._state(capture).locations)
        receipt = K.operation_receipt(capture)
        receipt["receiver_identity"]["live_locations"].clear()
        self.assertEqual(K.canonical(K._state(capture).locations), before)
        self.assertNotIn("live_locations", self.template["receiver_identity"])

    def test_source_owned_persistent_identity_is_part_of_full_proposal_comparison(self):
        altered = copy.deepcopy(self.template)
        altered["receiver_identity"]["persistent_locations"]["cohort"]["components"][
            -1
        ]["volume_uuid"] = K.ROOT_VOLUME_UUID
        with self.assertRaises(Exception):
            K._compare_certificate(K.canonical(rehash(altered)), self.template)

    def test_callable_guard_rejects_new_and_frozen_helper_substitution(self):
        K._guard()
        for module, name in (
            (K, "_projection"),
            (K, "historical"),
            (K, "_stable"),
            (K, "_capture_locations"),
            (K, "_volume_uuid"),
            (K, "_historical_locations"),
            (N, "replay_one"),
            (N, "reconstruct_seal"),
            (N, "correspondence"),
            (R, "load_inputs"),
            (C, "unused"),
            (K._LiveCapture, "revalidate"),
        ):
            with patch.object(module, name, Mock()), self.subTest(name=name):
                with self.assertRaises(Exception):
                    K._guard()

    def verification(self):
        wiring = self.operation()
        saved = SimpleNamespace(raw=K.canonical(self.template), revalidate=Mock())
        wiring.evidence.file.return_value = saved
        stack = ExitStack()
        self.addCleanup(stack.close)
        reviewed = stack.enter_context(patch.object(R, "reviewed_file"))
        ancestor = stack.enter_context(patch.object(K.core, "require_ancestor"))
        stack.enter_context(patch.object(R, "oid", side_effect=lambda value: value))
        return wiring, saved, reviewed, ancestor

    def test_verify_fixed_reviewed_proposal_reconstructs_everything_then_compares(self):
        wiring, saved, reviewed, ancestor = self.verification()
        result = K.verify_proposal("a" * 40, "c" * 40)
        reviewed.assert_called_once_with(saved, "c" * 40)
        wiring.evidence.file.assert_called_once_with(ROOT / K.PROPOSAL)
        self.assertEqual(
            [call.args[1:] for call in ancestor.call_args_list],
            [("a" * 40, "c" * 40), ("c" * 40, "b" * 40)],
        )
        self.assertEqual(wiring.public.call_count, 2)
        wiring.sealed.assert_called_once()
        self.assertEqual(result["work"], self.old["work"])
        self.assertEqual(result["operation_head"], "b" * 40)
        self.assertIs(result["algorithmically_independent_implementation"], False)
        self.assertIs(result["certificate_issued"], False)

    def test_proposal_review_failure_precedes_parsing_and_computation(self):
        wiring, _, reviewed, _ = self.verification()
        reviewed.side_effect = ValueError("proposal not reviewed")
        with patch.object(K, "_compare_certificate") as compare:
            with self.assertRaisesRegex(K.CertificateFailure, "not reviewed"):
                K.verify_proposal("a" * 40, "c" * 40)
            compare.assert_not_called()
        wiring.environment.assert_not_called()

    def test_rehashed_proposal_change_rejected_before_expensive_work(self):
        wiring, saved, _, _ = self.verification()
        wrong = copy.deepcopy(self.template)
        wrong["historical_e4"]["verification_method"] = "caller says PASS"
        saved.raw = K.canonical(rehash(wrong))
        with self.assertRaisesRegex(K.CertificateFailure, "entire canonical"):
            K.verify_proposal("a" * 40, "c" * 40)
        wiring.environment.assert_not_called()

    def test_correct_template_cannot_skip_failed_fresh_reconstruction(self):
        wiring, _, _, _ = self.verification()
        wiring.sealed.side_effect = ValueError("fresh original seal differs")
        with self.assertRaisesRegex(K.CertificateFailure, "fresh original seal"):
            K.verify_proposal("a" * 40, "c" * 40)

    def test_final_proposal_generation_drift_rejects_but_retains_work(self):
        _, saved, _, _ = self.verification()
        saved.revalidate.side_effect = ValueError("proposal replaced")
        with self.assertRaises(K.CertificateFailure) as caught:
            K.verify_proposal("a" * 40, "c" * 40)
        self.assertEqual(caught.exception.work, self.old["work"])

    def test_fresh_full_certificate_mismatch_rejected_even_after_valid_template(self):
        self.verification()
        altered = copy.deepcopy(self.template)
        altered["study"]["four_arm_block_count"] = 255
        with patch.object(
            K, "_projection", side_effect=[self.template, rehash(altered)]
        ):
            with self.assertRaisesRegex(
                K.CertificateFailure, "entire reconstructed certificate"
            ) as caught:
                K.verify_proposal("a" * 40, "c" * 40)
        self.assertEqual(caught.exception.work, self.old["work"])

    def test_proposal_reconstruction_head_change_rejected(self):
        self.verification()
        with patch.object(
            K.core, "git_head", side_effect=["b" * 40, "b" * 40, "d" * 40]
        ):
            with self.assertRaisesRegex(
                K.CertificateFailure, "reconstruction HEAD changed"
            ) as caught:
                K.verify_proposal("a" * 40, "c" * 40)
        self.assertEqual(caught.exception.work, self.old["work"])

    def test_source_review_nonancestor_rejected_before_computation(self):
        wiring, _, _, ancestor = self.verification()
        ancestor.side_effect = ValueError("not an ancestor")
        with self.assertRaisesRegex(K.CertificateFailure, "not an ancestor"):
            K.verify_proposal("a" * 40, "c" * 40)
        wiring.environment.assert_not_called()

    def test_no_external_receipt_path_or_callback_api(self):
        for name in (
            "publish",
            "prepare",
            "admit",
            "consume",
            "execute",
            "resume",
            "from_dict",
        ):
            self.assertFalse(hasattr(K, name))
        with self.assertRaises(TypeError):
            K.verify_proposal("a" * 40, "c" * 40, verified={"status": "PASS"})
        with self.assertRaises(TypeError):
            K.reconstruct("a" * 40, callback=lambda: self.template)

    def test_old_verifier_same_head_guard_remains_present(self):
        # Static regression plus immutable-source attestation; not a run of N.verify_saved.
        source = (ROOT / K.FROZEN_SCRIPT).read_bytes()
        ref = self.old["source"]["files"][K.FROZEN_SCRIPT]
        self.assertEqual(K.sha(source), ref["sha256"])
        self.assertIn(b'expected["reconstruction_head"] == head', source)

    def test_no_filesystem_publication_or_execution_calls_in_new_operator(self):
        tree = ast.parse((ROOT / K.SCRIPT).read_text())
        forbidden = {
            "prepare",
            "publish",
            "admit",
            "consume",
            "execute",
            "run_replication",
            "mkdir",
            "write_bytes",
            "write_text",
            "unlink",
            "rename",
            "replace",
            "fsync",
        }
        # The one permitted open is the already frozen read-only, component-wise
        # O_NOFOLLOW descriptor walker. Builtin/open-file and all other open
        # calls remain forbidden; do not broadly allow calls named `open`.
        open_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and (
                (isinstance(node.func, ast.Attribute) and node.func.attr == "open")
                or (isinstance(node.func, ast.Name) and node.func.id == "open")
            )
        ]
        self.assertEqual(len(open_calls), 1)
        self.assertEqual(
            ast.unparse(open_calls[0]), "S.mechanics._PinnedParent.open(prefix)"
        )
        calls = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        self.assertFalse(calls & forbidden)

    def test_failure_receipt_keeps_unknown_and_complete_counts_separate(self):
        for work in (N.initial_work(), self.old["work"], None):
            result = K.failure_receipt(
                ValueError("delivery failed"), work, "UNKNOWN_PARTIAL_OR_COMPLETE"
            )
            self.assertEqual(result["work"], work)
            self.assertIsNone(result["authorization_consumed"])
            self.assertIs(result["automatic_retry_allowed"], False)
            self.assertIs(result["certificate_issued"], False)

    def test_failure_receipt_preserves_known_consumption_without_inferring_absence(
        self,
    ):
        for consumed in (False, True):
            error = S.ExecutionFailure("KNOWN_STATE", consumed, "known failure state")
            result = K.failure_receipt(
                K.CertificateFailure(error, "scope", N.initial_work())
            )
            self.assertIs(result["authorization_consumed"], consumed)
            self.assertNotIn("original_study_slot_absent_at_completion", result)

    def test_cli_short_write_and_flush_failure_remain_uncertain(self):
        for short in (True, False):
            self.operation()
            stdout = SimpleNamespace(buffer=Mock())
            stdout.buffer.write.side_effect = lambda raw: len(raw) - int(short)
            if not short:
                stdout.buffer.flush.side_effect = OSError("flush failed")
            stderr = SimpleNamespace(buffer=io.BytesIO())
            with (
                patch.object(
                    sys,
                    "argv",
                    [K.SCRIPT, "--reconstruct", "--implementation-revision", "a" * 40],
                ),
                patch.object(sys, "stdout", stdout),
                patch.object(sys, "stderr", stderr),
            ):
                with self.assertRaises(SystemExit):
                    K.main()
            failure = K.parse(stderr.buffer.getvalue())
            self.assertEqual(failure["work"], self.old["work"])
            self.assertEqual(failure["result_delivery"], "UNKNOWN_PARTIAL_OR_COMPLETE")

    def test_cli_stdout_write_failure_keeps_completed_work_and_delivery_uncertainty(
        self,
    ):
        self.operation()
        stdout, stderr = (
            SimpleNamespace(buffer=Mock()),
            SimpleNamespace(buffer=io.BytesIO()),
        )
        stdout.buffer.write.side_effect = BrokenPipeError("stdout closed")
        with (
            patch.object(
                sys,
                "argv",
                [K.SCRIPT, "--reconstruct", "--implementation-revision", "a" * 40],
            ),
            patch.object(sys, "stdout", stdout),
            patch.object(sys, "stderr", stderr),
        ):
            with self.assertRaises(SystemExit):
                K.main()
        failure = K.parse(stderr.buffer.getvalue())
        self.assertEqual(failure["work"], self.old["work"])
        self.assertEqual(failure["result_delivery"], "UNKNOWN_PARTIAL_OR_COMPLETE")

    def test_cli_receipt_failure_reports_completed_stdout_not_publication(self):
        self.operation()
        stdout = SimpleNamespace(buffer=io.BytesIO())
        sink = io.BytesIO()
        calls = []

        def write(raw):
            calls.append(raw)
            if len(calls) == 1:
                raise OSError("operation receipt write failed")
            return sink.write(raw)

        stderr = SimpleNamespace(
            buffer=SimpleNamespace(write=write, flush=lambda: None)
        )
        with (
            patch.object(
                sys,
                "argv",
                [K.SCRIPT, "--reconstruct", "--implementation-revision", "a" * 40],
            ),
            patch.object(sys, "stdout", stdout),
            patch.object(sys, "stderr", stderr),
        ):
            with self.assertRaises(SystemExit):
                K.main()
        self.assertEqual(stdout.buffer.getvalue(), K.canonical(self.template))
        failure = K.parse(sink.getvalue())
        self.assertEqual(failure["result_delivery"], "COMPLETE_STDOUT_FLUSH")
        self.assertIs(failure["certificate_issued"], False)

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, "-P", "-B", str(ROOT / K.SCRIPT), *args],
            cwd="/tmp",
            env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
            capture_output=True,
            check=False,
        )

    def test_cli_static_self_test_works_outside_checkout(self):
        result = self.cli("--self-test")
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(K.parse(result.stdout)["status"], "STATIC_SELF_TEST_ONLY")
        self.assertEqual(result.stderr, b"")

    def test_cli_execution_publication_and_scope_overrides_do_not_exist(self):
        for flag in (
            "--publish",
            "--run",
            "--consume",
            "--resume",
            "--output",
            "--device",
            "--consent",
            "--verify",
        ):
            result = self.cli("--self-test", flag)
            self.assertEqual(result.returncode, 2, (flag, result.stderr))
            self.assertEqual(result.stdout, b"")

    def test_cli_rejects_missing_or_misplaced_revisions(self):
        for args in (
            ("--reconstruct",),
            ("--verify-proposal", "--implementation-revision", "a" * 40),
            ("--self-test", "--implementation-revision", "a" * 40),
            (
                "--reconstruct",
                "--implementation-revision",
                "a" * 40,
                "--reviewed-proposal-revision",
                "b" * 40,
            ),
        ):
            result = self.cli(*args)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, b"")


if __name__ == "__main__":
    unittest.main()
