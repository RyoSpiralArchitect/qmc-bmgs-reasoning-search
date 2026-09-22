"""Synthetic boundary tests, NOT PUBLIC execution or replication qualification.

No search, real claim consumption, historical artifact mutation or numerical
workload occurs here. Mocked control-flow coverage is reported separately from
the one genuinely executed full-shape PUBLIC qualification.
"""

from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError
import importlib.util
import io
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "receiver_execution_tested", ROOT / "scripts/feedback_budget_receiver_execution.py"
)
assert SPEC is not None and SPEC.loader is not None
C = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = C
SPEC.loader.exec_module(C)
B, R, S, F = C.B, C.R, C.S, C.F
REVISION = "f" * 40


def rehash(value):
    return C.digested(B.without_digest(value))


def snapshot(path, raw):
    return SimpleNamespace(path=Path(path), raw=raw, revalidate=Mock())


def fixture(mode=None):
    """Synthetic authority metadata; only PUBLIC input definitions are real."""
    mode = S.PUBLIC if mode is None else mode
    inputs = R.load_inputs(S.PUBLIC)
    if mode == S.REPLICATION:
        manifest = inputs.manifest
        manifest.update(
            execution_mode=mode,
            experiment_id=S.REPLICATION_ID,
            source_multiset_count=64,
            cohort_seal={"deterministic_digest": "b" * 64},
        )
        inputs = SimpleNamespace(manifest=rehash(manifest), cells=[])
    env = {
        name: {"fixture": name}
        for name in ("source", "runtime", "baseline", "authorities", "admission_proof")
    }
    base = SimpleNamespace(
        proof=SimpleNamespace(
            source_raw=C.canonical({"deterministic_digest": "a" * 64}),
            environment_raw=C.canonical(env),
        ),
        snapshots=tuple(
            snapshot(ROOT / name, b"{}\n")
            for name in (B.CANDIDATE, B.CERTIFICATE, B.BUNDLE_COMMIT)
        ),
        inputs=inputs,
        revalidate=Mock(),
    )
    source = C.digested(
        {
            "schema_version": C.DOMAIN + "/source",
            "implementation_revision": REVISION,
            "receiver_source": {"deterministic_digest": "a" * 64},
            "files": {},
        }
    )
    parent = C.digested(
        {
            "schema_version": S.DOMAIN + "/output-parent",
            "path": str(C.output_for(mode).parent),
            "identities": [[1, 2]],
        }
    )
    qualification = None if mode == S.PUBLIC else {"fixture": "new-public-proof"}
    with patch.object(S, "parent_binding", return_value=parent):
        auth = C.candidate(mode, inputs, base, source, qualification)
    admitted = SimpleNamespace(
        auth=auth,
        base=base,
        inputs=inputs,
        snapshot=snapshot(C.authorization_for(mode), C.canonical(auth)),
        source_raw=C.canonical(source),
        reviewed=REVISION,
        head=REVISION,
        revalidate=Mock(),
    )
    claim = S.claim_value(auth, REVISION, REVISION, "0" * 64)
    binding = C.run_binding(admitted, claim)
    receipt = C.digested(
        {
            "integrity": {
                "replayed_trace_count": 1024,
                "budget_prefix_check_count": 512,
            },
            "reduction": {"exact_success": {"screen_conjunction": False}},
            "replication_cells_executed": 0 if mode == S.PUBLIC else 1024,
            "scientific_decision": None
            if mode == S.PUBLIC
            else "STOP_REPAIR_REPLICATION_SCREEN_NOT_MET",
        }
    )
    publication = SimpleNamespace(
        binding=binding,
        rows=[],
        receipt=receipt,
        commit=C.digested({"fixture": "closed-publication"}),
        revalidate=Mock(),
    )
    return SimpleNamespace(
        mode=mode,
        inputs=inputs,
        base=base,
        source=source,
        parent=parent,
        auth=auth,
        admitted=admitted,
        claim=claim,
        binding=binding,
        receipt=receipt,
        publication=publication,
        fence=snapshot(C.FENCE, b'{"fixture":"spent-fence"}\n'),
        claim_snapshot=snapshot(S.claim_path(auth), C.canonical(claim)),
    )


class IdentityAndShapeTests(unittest.TestCase):
    def test_fixed_namespaces_never_replace_original_study(self):
        self.assertEqual(C.DOMAIN, B.DOMAIN + "/coordinator/v2")
        self.assertEqual(C.PUBLIC_ATTEMPT, "receiver_public_full_path_20260922_a/v1")
        self.assertEqual(C.output_for(S.REPLICATION), B.OUTPUT)
        self.assertEqual(C.RAW_AUTH, Path(str(C.PUBLIC_OUTPUT) + ".authorization.json"))
        self.assertEqual(C.PUBLIC_SUMMARY, Path(str(C.PUBLIC_OUTPUT) + ".summary.json"))
        self.assertEqual(
            C.FENCE,
            S.LEDGER
            / ("receiver-public-" + C.digest([C.DOMAIN, C.PUBLIC_ATTEMPT]) + ".json"),
        )
        self.assertNotEqual(C.FENCE, B.fixed_claim())
        self.assertNotEqual(C.PUBLIC_OUTPUT, B.PUBLIC_OUTPUT)
        self.assertNotEqual(
            C.authorization_for(S.PUBLIC), C.authorization_for(S.REPLICATION)
        )
        self.assertFalse(C.self_test()["replication_execution_authorized"])

    def test_invalid_modes_are_rejected(self):
        for function in (
            C.output_for,
            C.authorization_for,
            C.summary_for,
            C.attempt_for,
        ):
            for mode in ("public", None, True, S.PUBLIC + "/retry"):
                with (
                    self.subTest(function=function.__name__, mode=mode),
                    self.assertRaises(ValueError),
                ):
                    function(mode)

    def test_authentic_public_shape_has_one_source_and_no_search(self):
        with (
            patch.object(
                R.admission, "load_seal", side_effect=AssertionError("sealed loader")
            ),
            patch.object(
                R.q,
                "run_countdown_track_a_search",
                side_effect=AssertionError("search"),
            ),
        ):
            inputs = R.load_inputs(S.PUBLIC)
            inputs.revalidate()
        manifest = inputs.manifest
        self.assertIsInstance(inputs, R.Inputs)
        self.assertEqual(
            (
                manifest["task_count"],
                manifest["source_multiset_count"],
                len(inputs.cells),
            ),
            (64, 1, 1024),
        )
        self.assertEqual(
            {cell["cell_key"]["seed"] for cell in inputs.cells},
            {8192, 8193, 8194, 8195},
        )
        self.assertEqual(
            {cell["cell_key"]["budget"] for cell in inputs.cells}, {256, 512}
        )
        self.assertEqual({cell["cell_key"]["scale"] for cell in inputs.cells}, {0, 16})

    def test_new_auth_is_closed_and_explicit_digest_bound(self):
        f = fixture()
        self.assertEqual(
            C.auth_shape(C.canonical(f.auth), S.PUBLIC, f.auth["deterministic_digest"]),
            f.auth,
        )
        mutations = (
            lambda a: a.update(schema_version=B.DOMAIN + "/authorization-candidate"),
            lambda a: a.update(attempt_id=C.PUBLIC_ATTEMPT + "/retry"),
            lambda a: a.update(output_path=str(C.PUBLIC_OUTPUT) + "-retry"),
            lambda a: a.update(execution_mode=S.REPLICATION),
            lambda a: a.update(expected_cell_count=True),
            lambda a: a.update(candidate_is_execution_authority=True),
            lambda a: a.update(connector_qualification={}),
            lambda a: a.update(extra=True),
            lambda a: a.pop("coordinator_source"),
        )
        for mutate in mutations:
            auth = copy.deepcopy(f.auth)
            mutate(auth)
            auth = rehash(auth)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                C.auth_shape(C.canonical(auth), S.PUBLIC, auth["deterministic_digest"])
        with self.assertRaisesRegex(ValueError, "digest"):
            C.auth_shape(C.canonical(f.auth), S.PUBLIC, "0" * 64)

    def test_actual_old_receiver_candidate_is_not_v2_authority(self):
        raw = (ROOT / B.CANDIDATE).read_bytes()
        for mode in (S.PUBLIC, S.REPLICATION):
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, "domain"):
                C.auth_shape(raw, mode, C.BRIDGE_DIGEST)

    def test_source_attestation_closes_exact_five_files_and_original_bridge(self):
        expected = (C.SCRIPT, C.HELPER, C.TEST, C.HELPER_TEST, C.POLICY)
        self.assertEqual(C.SOURCE_FILES, expected)
        items = {
            ROOT / path: snapshot(ROOT / path, path.encode() + b"\n")
            for path in expected
        }
        with (
            patch.object(R, "oid", side_effect=lambda value: value),
            patch.object(C.core, "git_head", return_value=REVISION),
            patch.object(C.core, "require_ancestor"),
            patch.object(R.public, "_origin") as origins,
            patch.object(B, "attest", return_value={"fixture": "old-source"}) as old,
            patch.object(R, "snapshot_file", side_effect=lambda path: items[path]),
            patch.object(R, "reviewed_file") as reviewed,
        ):
            source = C.attest(REVISION)
        old.assert_called_once_with(C.BRIDGE_REVISION)
        self.assertEqual(set(source["files"]), set(expected))
        self.assertEqual(reviewed.call_count, 5)
        self.assertEqual(origins.call_count, 2)
        for item in items.values():
            item.revalidate.assert_called_once()


class AdmissionTests(unittest.TestCase):
    def admission_patches(self, f, events):
        patches = (
            patch.object(R, "snapshot_file", return_value=f.admitted.snapshot),
            patch.object(R, "oid", side_effect=lambda value: value),
            patch.object(C.core, "git_head", return_value=REVISION),
            patch.object(C.core, "require_ancestor"),
            patch.object(R, "reviewed_file"),
            patch.object(
                C,
                "attest",
                side_effect=lambda revision: events.append("source") or f.source,
            ),
            patch.object(S, "parent_binding", return_value=f.parent),
            patch.object(
                B,
                "admit",
                side_effect=lambda *a, **k: events.append("genuine-v1-admit") or f.base,
            ),
        )
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def test_public_admission_uses_genuine_bridge_and_real_public_inputs(self):
        f, events = fixture(), []
        self.admission_patches(f, events)
        with (
            patch.object(
                R.admission, "load_seal", side_effect=AssertionError("sealed loader")
            ),
            patch.object(
                R.q,
                "run_countdown_track_a_search",
                side_effect=AssertionError("search"),
            ),
            patch.object(
                C,
                "qualified_public",
                side_effect=AssertionError("PUBLIC must not self-qualify"),
            ),
        ):
            admitted = C.admit(
                S.PUBLIC,
                f.admitted.snapshot.path,
                f.auth["deterministic_digest"],
                REVISION,
            )
        self.assertIsInstance(admitted.inputs, R.Inputs)
        self.assertEqual(admitted.inputs.manifest["source_multiset_count"], 1)
        self.assertLess(events.index("source"), events.index("genuine-v1-admit"))
        B.admit.assert_called_once_with(
            ROOT / B.CANDIDATE,
            ROOT / B.CERTIFICATE,
            C.BRIDGE_DIGEST,
            C.BRIDGE_REVIEWED,
            observe=unittest.mock.ANY,
        )
        with self.assertRaises(FrozenInstanceError):
            admitted.reviewed = "0" * 40

    def test_nonfixed_candidate_rejected_before_snapshot_or_source(self):
        with (
            patch.object(R, "snapshot_file") as read,
            self.assertRaisesRegex(ValueError, "fixed"),
        ):
            C.admit(S.PUBLIC, C.RAW_AUTH, "0" * 64, REVISION)
        read.assert_not_called()

    def test_unreviewed_candidate_rejected_before_source_or_bridge(self):
        f = fixture()
        self.admission_patches(f, [])
        R.reviewed_file.side_effect = ValueError("unreviewed")
        with self.assertRaisesRegex(ValueError, "unreviewed"):
            C.admit(
                S.PUBLIC,
                f.admitted.snapshot.path,
                f.auth["deterministic_digest"],
                REVISION,
            )
        C.attest.assert_not_called()
        B.admit.assert_not_called()

    def test_closed_replication_adapter_requires_new_public_before_bridge(self):
        f, events = fixture(S.REPLICATION), []
        self.admission_patches(f, events)
        qualification_check = Mock()
        with (
            patch.object(
                C,
                "qualified_public",
                side_effect=lambda *a: (
                    events.append("new-public-qualified")
                    or (f.auth["connector_qualification"], qualification_check)
                ),
            ),
            patch.object(
                R, "load_inputs", side_effect=AssertionError("no substitute loader")
            ),
        ):
            admitted = C.admit(
                S.REPLICATION,
                f.admitted.snapshot.path,
                f.auth["deterministic_digest"],
                REVISION,
            )
        self.assertIs(admitted.inputs, f.base.inputs)
        self.assertLess(
            events.index("new-public-qualified"), events.index("genuine-v1-admit")
        )
        qualification_check.assert_called_once()

    def test_bad_new_public_proof_stops_before_sealed_admission(self):
        f = fixture(S.REPLICATION)
        self.admission_patches(f, [])
        with (
            patch.object(
                C, "qualified_public", side_effect=ValueError("new PUBLIC missing")
            ),
            self.assertRaisesRegex(ValueError, "PUBLIC"),
        ):
            C.admit(
                S.REPLICATION,
                f.admitted.snapshot.path,
                f.auth["deterministic_digest"],
                REVISION,
            )
        B.admit.assert_not_called()


class RunBoundaryTests(unittest.TestCase):
    def run_patches(self, f, events):
        f.admitted.inputs = SimpleNamespace(
            cells=[{"cell_index": 0}, {"cell_index": 1}]
        )
        patches = (
            patch.object(C, "unused", side_effect=lambda mode: events.append("unused")),
            patch.object(R, "snapshot_file", return_value=f.admitted.snapshot),
            patch.object(C.os.path, "lexists", return_value=False),
            patch.object(
                S,
                "descriptor_preflight",
                side_effect=lambda: events.append("descriptor"),
            ),
            patch.object(
                C,
                "admit",
                side_effect=lambda *a, **k: events.append("admitted") or f.admitted,
            ),
            patch.object(
                F,
                "consume",
                side_effect=lambda *a, **k: events.append("fence") or ({}, f.fence),
            ),
            patch.object(
                S,
                "consume",
                side_effect=lambda *a: (
                    events.append("claim") or (f.claim, f.claim_snapshot)
                ),
            ),
            patch.object(S, "parent_binding", return_value=f.parent),
            patch.object(
                R,
                "record",
                side_effect=lambda inputs, cell, binding: (
                    events.append("record") or {"cell_index": cell["cell_index"]}
                ),
            ),
            patch.object(
                R,
                "reduce_rows",
                side_effect=lambda *a, **k: events.append("reduce") or f.receipt,
            ),
        )
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def test_fixed_fence_precedes_storage_claim_and_shared_publication(self):
        f, events, emitted = fixture(), [], []
        self.run_patches(f, events)

        def publish(output, binding, action, check):
            events.append("publish")
            self.assertEqual(output, C.PUBLIC_OUTPUT)
            self.assertEqual(binding["execution_mode"], S.PUBLIC)
            self.assertFalse(binding["replication_execution_authorized"])
            check()
            receipt = action(lambda index, row: emitted.append((index, row)))
            check()
            return receipt

        with patch.object(S, "publish", side_effect=publish):
            result = C.run(
                S.PUBLIC,
                f.admitted.snapshot.path,
                f.auth["deterministic_digest"],
                REVISION,
            )
        self.assertEqual(
            events,
            [
                "unused",
                "descriptor",
                "admitted",
                "unused",
                "fence",
                "claim",
                "publish",
                "record",
                "record",
                "reduce",
            ],
        )
        self.assertEqual([index for index, _ in emitted], [0, 1])
        self.assertEqual(result, f.receipt)
        self.assertEqual(f.fence.revalidate.call_count, 2)
        self.assertEqual(f.claim_snapshot.revalidate.call_count, 2)

    def test_occupied_attempt_stops_before_admission_or_work(self):
        with (
            patch.object(
                C,
                "unused",
                side_effect=S.ExecutionFailure(
                    "AUTHORIZATION_ALREADY_SPENT", True, "occupied"
                ),
            ),
            patch.object(C, "admit") as admission,
            patch.object(S, "consume") as consume,
            patch.object(R, "record") as record,
            self.assertRaises(S.ExecutionFailure),
        ):
            C.run(S.PUBLIC, C.authorization_for(S.PUBLIC), "0" * 64, REVISION)
        admission.assert_not_called()
        consume.assert_not_called()
        record.assert_not_called()

    def test_occupied_summary_stops_before_any_admission_or_consumption(self):
        with (
            patch.object(F, "ensure_unused"),
            patch.object(
                C.os.path,
                "lexists",
                side_effect=lambda path: Path(path) == C.PUBLIC_SUMMARY,
            ),
            patch.object(C, "admit") as admission,
            patch.object(F, "consume") as fence,
            patch.object(S, "consume") as consume,
            self.assertRaisesRegex(ValueError, "summary occupied"),
        ):
            C.run(S.PUBLIC, C.authorization_for(S.PUBLIC), "0" * 64, REVISION)
        admission.assert_not_called()
        fence.assert_not_called()
        consume.assert_not_called()

    def test_orphan_candidate_claim_stops_before_admission_or_new_fence(self):
        f = fixture()
        with (
            patch.object(C, "unused"),
            patch.object(R, "snapshot_file", return_value=f.admitted.snapshot),
            patch.object(
                C.os.path,
                "lexists",
                side_effect=lambda path: Path(path) == S.claim_path(f.auth),
            ),
            patch.object(C, "admit") as admission,
            patch.object(F, "consume") as fence,
            patch.object(S, "consume") as consume,
            self.assertRaises(S.ExecutionFailure) as caught,
        ):
            C.run(
                S.PUBLIC,
                f.admitted.snapshot.path,
                f.auth["deterministic_digest"],
                REVISION,
            )
        self.assertEqual(caught.exception.status, "AUTHORIZATION_ALREADY_SPENT")
        self.assertTrue(caught.exception.authorization_consumed)
        admission.assert_not_called()
        fence.assert_not_called()
        consume.assert_not_called()

    def test_failed_storage_claim_after_fence_is_spent_not_run(self):
        f = fixture()
        self.run_patches(f, [])
        S.consume.side_effect = S.ExecutionFailure("NOT_RUN", False, "injected")
        with (
            patch.object(S, "publish") as publish,
            self.assertRaises(S.ExecutionFailure) as caught,
        ):
            C.run(
                S.PUBLIC,
                f.admitted.snapshot.path,
                f.auth["deterministic_digest"],
                REVISION,
            )
        self.assertEqual(caught.exception.status, "SPENT_NOT_RUN")
        self.assertTrue(caught.exception.authorization_consumed)
        publish.assert_not_called()

    def test_uncertain_storage_claim_remains_uncertain(self):
        f = fixture()
        self.run_patches(f, [])
        S.consume.side_effect = S.ExecutionFailure(
            "CONSUMPTION_UNCERTAIN", None, "injected"
        )
        with self.assertRaises(S.ExecutionFailure) as caught:
            C.run(
                S.PUBLIC,
                f.admitted.snapshot.path,
                f.auth["deterministic_digest"],
                REVISION,
            )
        self.assertEqual(caught.exception.status, "CONSUMPTION_UNCERTAIN")
        self.assertIsNone(caught.exception.authorization_consumed)

    def test_fence_failure_never_calls_storage_claim(self):
        f = fixture()
        self.run_patches(f, [])
        F.consume.side_effect = S.ExecutionFailure(
            "CONSUMPTION_UNCERTAIN", None, "fence"
        )
        with self.assertRaises(S.ExecutionFailure):
            C.run(
                S.PUBLIC,
                f.admitted.snapshot.path,
                f.auth["deterministic_digest"],
                REVISION,
            )
        S.consume.assert_not_called()

    def test_record_exception_retains_consumed_status(self):
        f = fixture()
        self.run_patches(f, [])
        R.record.side_effect = RuntimeError("injected before actual search")
        with (
            patch.object(
                S,
                "publish",
                side_effect=lambda output, binding, action, check: action(
                    lambda *a: None
                ),
            ),
            self.assertRaises(S.ExecutionFailure) as caught,
        ):
            C.run(
                S.PUBLIC,
                f.admitted.snapshot.path,
                f.auth["deterministic_digest"],
                REVISION,
            )
        self.assertEqual(caught.exception.status, "SPENT_NOT_RUN")
        self.assertTrue(caught.exception.authorization_consumed)


class AnalysisBoundaryTests(unittest.TestCase):
    def analysis_patches(self, f, events):
        patches = (
            patch.object(
                S,
                "inspect",
                side_effect=lambda output: (
                    events.append("publication") or f.publication
                ),
            ),
            patch.object(
                S,
                "inspect_claim",
                side_effect=lambda *a: events.append("claim") or f.claim_snapshot,
            ),
            patch.object(
                F,
                "inspect",
                side_effect=lambda *a, **k: events.append("fence") or f.fence,
            ),
            patch.object(
                C,
                "admit",
                side_effect=lambda *a, **k: events.append("admit") or f.admitted,
            ),
            patch.object(
                R,
                "reduce_rows",
                side_effect=lambda *a, **k: events.append("replay") or f.receipt,
            ),
            patch.object(
                C, "unused", side_effect=AssertionError("absence is not analysis")
            ),
            patch.object(
                B,
                "unused",
                side_effect=AssertionError("replication may already be spent"),
            ),
        )
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def test_analysis_authenticates_claim_then_fence_before_admission(self):
        f, events = fixture(), []
        self.analysis_patches(f, events)
        value, check = C.analyze(S.PUBLIC)
        check()
        self.assertEqual(events, ["publication", "claim", "fence", "admit", "replay"])
        self.assertEqual(
            (
                value["task_count"],
                value["source_multiset_count"],
                value["public_cells_executed"],
            ),
            (64, 1, 1024),
        )
        self.assertEqual(value["replication_cells_executed"], 0)
        self.assertIs(value["scientific_decision"], None)
        self.assertIs(value["replication_execution_authorized"], False)
        self.assertIs(value["production_adapter_executed"], False)
        self.assertIs(value["locked_128_evaluation_authorized"], False)
        self.assertIs(value["public_coordinator_qualified"], True)
        self.assertIs(value["reduction"]["exact_success"]["screen_conjunction"], False)

    def test_bad_claim_stops_before_fence_admission_and_replay(self):
        f = fixture()
        self.analysis_patches(f, [])
        S.inspect_claim.side_effect = ValueError("claim mismatch")
        with self.assertRaisesRegex(ValueError, "claim"):
            C.analyze(S.PUBLIC)
        F.inspect.assert_not_called()
        C.admit.assert_not_called()
        R.reduce_rows.assert_not_called()

    def test_bad_fence_stops_before_admission_and_replay(self):
        f = fixture()
        self.analysis_patches(f, [])
        F.inspect.side_effect = ValueError("fence mismatch")
        with self.assertRaisesRegex(ValueError, "fence"):
            C.analyze(S.PUBLIC)
        C.admit.assert_not_called()
        R.reduce_rows.assert_not_called()

    def test_analysis_rejects_different_reproduced_receipt(self):
        f = fixture()
        self.analysis_patches(f, [])
        R.reduce_rows.side_effect = None
        R.reduce_rows.return_value = rehash(
            {**f.receipt, "replication_cells_executed": 1}
        )
        with self.assertRaisesRegex(ValueError, "receipt"):
            C.analyze(S.PUBLIC)

    def test_saved_summary_must_reproduce_complete_bytes(self):
        saved = C.digested(
            {
                "schema_version": C.DOMAIN + "/analysis",
                "execution_mode": S.PUBLIC,
                "fixture": 1,
            }
        )
        item = snapshot(C.PUBLIC_SUMMARY, C.canonical(saved))
        check = Mock()
        with (
            patch.object(R, "snapshot_file", return_value=item),
            patch.object(C, "analyze", return_value=(saved, check)),
        ):
            self.assertEqual(C.verify(S.PUBLIC), saved)
        item.revalidate.assert_called_once()
        check.assert_called_once()
        changed = rehash({**saved, "fixture": 2})
        with (
            patch.object(R, "snapshot_file", return_value=item),
            patch.object(C, "analyze", return_value=(changed, check)),
            self.assertRaisesRegex(ValueError, "reproduce"),
        ):
            C.verify(S.PUBLIC)

    def test_summary_slot_is_never_overwritten(self):
        with (
            patch.object(C.os.path, "lexists", return_value=True),
            patch.object(C, "analyze") as analyze,
            self.assertRaisesRegex(ValueError, "occupied"),
        ):
            C.analyze_and_save(S.PUBLIC)
        analyze.assert_not_called()

    def test_public_qualification_does_not_require_replication_absence(self):
        f, events = fixture(), []
        self.analysis_patches(f, events)
        value, _ = C.analyze(S.PUBLIC)
        items = {
            ROOT / C.SUMMARY_MIRROR: snapshot(
                ROOT / C.SUMMARY_MIRROR, C.canonical(value)
            ),
            ROOT / C.COMMIT_MIRROR: snapshot(
                ROOT / C.COMMIT_MIRROR, C.canonical(f.publication.commit)
            ),
        }
        with (
            patch.object(R, "snapshot_file", side_effect=lambda path: items[path]),
            patch.object(R, "reviewed_file") as reviewed,
        ):
            reference, check = C.qualified_public(
                REVISION, f.source, lambda stage: None
            )
            check()
        self.assertEqual(reference["summary_digest"], value["deterministic_digest"])
        self.assertEqual(reference["source_digest"], f.source["deterministic_digest"])
        self.assertGreaterEqual(reviewed.call_count, 4)
        B.unused.assert_not_called()


class CliTests(unittest.TestCase):
    def test_public_only_strict_cli_rejects_production_and_namespace_overrides(self):
        cases = (
            ["--run-replication"],
            ["--prepare-replication"],
            ["--analyze-replication"],
            ["--run-public"],
            ["--prepare-public"],
            ["--self"],
            ["--self-test", "--output", "/tmp/other"],
            ["--self-test", "--attempt-id", "retry"],
            ["--self-test", "--implementation-revision", REVISION],
            ["--analyze-public", "--authorization", "other"],
            ["--self-test", "--verify-public"],
        )
        for args in cases:
            with (
                self.subTest(args=args),
                patch.object(sys, "argv", [C.SCRIPT, *args]),
                patch.object(sys, "stderr", io.StringIO()),
                patch.object(C, "run") as run,
                patch.object(C, "prepare_public") as prepare,
                self.assertRaises(SystemExit) as caught,
            ):
                C.main()
            self.assertEqual(caught.exception.code, 2)
            run.assert_not_called()
            prepare.assert_not_called()

    def test_public_cli_dispatch_never_selects_replication(self):
        f, buffer = fixture(), io.BytesIO()
        args = [
            C.SCRIPT,
            "--run-public",
            "--authorization",
            str(f.admitted.snapshot.path),
            "--confirm-digest",
            f.auth["deterministic_digest"],
            "--reviewed-revision",
            REVISION,
        ]
        with (
            patch.object(sys, "argv", args),
            patch.object(sys, "stdout", SimpleNamespace(buffer=buffer)),
            patch.object(B, "unused") as guard,
            patch.object(C, "run", return_value=f.publication.commit) as run,
        ):
            C.main()
        guard.assert_called_once()
        self.assertEqual(run.call_args.args[0], S.PUBLIC)
        value = C.parse(buffer.getvalue())
        self.assertEqual(value["status"], "PUBLIC_EXECUTION_COMMITTED")
        self.assertFalse(value["replication_execution_authorized"])
        self.assertEqual(value["replication_search_calls"], 0)

    def test_completed_run_stdout_failure_is_delivery_uncertain_and_spent(self):
        f = fixture()
        buffer = Mock()
        buffer.write.side_effect = [BrokenPipeError("injected stdout failure"), None]
        args = [
            C.SCRIPT,
            "--run-public",
            "--authorization",
            str(f.admitted.snapshot.path),
            "--confirm-digest",
            f.auth["deterministic_digest"],
            "--reviewed-revision",
            REVISION,
        ]
        with (
            patch.object(sys, "argv", args),
            patch.object(sys, "stdout", SimpleNamespace(buffer=buffer)),
            patch.object(sys, "stderr", io.StringIO()),
            patch.object(B, "unused"),
            patch.object(C, "run", return_value=f.publication.commit) as run,
            self.assertRaises(SystemExit),
        ):
            C.main()
        run.assert_called_once()
        value = C.parse(buffer.write.call_args_list[1].args[0])
        self.assertEqual(value["status"], "RESULT_DELIVERY_UNCERTAIN")
        self.assertTrue(value["authorization_consumed"])
        self.assertFalse(value["automatic_retry_allowed"])

    def test_completed_analysis_or_verify_delivery_failure_is_spent(self):
        value = {
            "deterministic_digest": "a" * 64,
            "public_cells_executed": 1024,
            "integrity": {
                "replayed_trace_count": 1024,
                "budget_prefix_check_count": 512,
            },
            "source_multiset_count": 1,
            "scientific_decision": None,
        }
        for flag, method in (
            ("--analyze-public", "analyze_and_save"),
            ("--verify-public", "verify"),
        ):
            buffer = Mock()
            buffer.write.side_effect = [
                BrokenPipeError("injected stdout failure"),
                None,
            ]
            with (
                self.subTest(flag=flag),
                patch.object(sys, "argv", [C.SCRIPT, flag]),
                patch.object(sys, "stdout", SimpleNamespace(buffer=buffer)),
                patch.object(sys, "stderr", io.StringIO()),
                patch.object(C, method, return_value=value) as operation,
                self.assertRaises(SystemExit),
            ):
                C.main()
            operation.assert_called_once()
            result = C.parse(buffer.write.call_args_list[1].args[0])
            self.assertEqual(result["status"], "RESULT_DELIVERY_UNCERTAIN")
            self.assertTrue(result["authorization_consumed"])
            self.assertFalse(result["automatic_retry_allowed"])

    def test_failed_analysis_or_verify_never_claims_unspent(self):
        for flag, method in (
            ("--analyze-public", "analyze_and_save"),
            ("--verify-public", "verify"),
        ):
            buffer = io.BytesIO()
            with (
                self.subTest(flag=flag),
                patch.object(sys, "argv", [C.SCRIPT, flag]),
                patch.object(sys, "stdout", SimpleNamespace(buffer=buffer)),
                patch.object(sys, "stderr", io.StringIO()),
                patch.object(
                    C, method, side_effect=ValueError("saved evidence failed")
                ),
                self.assertRaises(SystemExit),
            ):
                C.main()
            result = C.parse(buffer.getvalue())
            self.assertEqual(result["status"], "NOT_RUN_OR_ANALYSIS_FAILED")
            self.assertIsNone(result["authorization_consumed"])
            self.assertFalse(result["automatic_retry_allowed"])


if __name__ == "__main__":
    unittest.main()
