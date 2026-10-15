"""Synthetic coordinator boundaries and isolated ledger reads; no actual run."""

from __future__ import annotations

from contextlib import ExitStack
import copy
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "e4_execution_tested", ROOT / "scripts/feedback_budget_receiver_e4_execution.py"
)
C = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = C
spec.loader.exec_module(C)
S, R, G = C.S, C.R, C.G
REV = "f" * 40


def rehash(value):
    return C.digested(C.B.without_digest(value))


def snap(path, raw):
    return SimpleNamespace(path=Path(path), raw=raw, revalidate=Mock())


def fixture(mode=None):
    mode = S.PUBLIC if mode is None else mode
    source = C.digested(
        dict(schema_version=C.DOMAIN + "/source", implementation_revision=REV, files={})
    )
    env = {
        key: {"fixture": key}
        for key in ("source", "runtime", "baseline", "authorities", "admission_proof")
    }
    public = R.load_inputs(S.PUBLIC)
    value = public.manifest
    sealed = SimpleNamespace(
        manifest=rehash(
            {
                **value,
                "execution_mode": S.REPLICATION,
                "experiment_id": S.REPLICATION_ID,
                "source_multiset_count": 64,
            }
        ),
        cells=public.cells,
    )
    history = SimpleNamespace(
        source=source,
        head=REV,
        environment=env,
        work=G.N.initial_work(),
        reference={"fixture": "issued-certificate"},
        revalidate=Mock(),
        inputs=Mock(side_effect=lambda mode: public if mode == S.PUBLIC else sealed),
        historical_claims=lambda: {
            S.LEDGER / ("old" + str(i) + ".json"): snap(
                S.LEDGER / ("old" + str(i) + ".json"), b"{}\n"
            )
            for i in range(3)
        },
    )
    parent = C.digested(
        dict(
            schema_version=S.DOMAIN + "/output-parent",
            path=str(C.PUBLIC_OUTPUT.parent),
            identities=[[1, 2]],
        )
    )
    qualification = (
        None if mode == S.PUBLIC else {"fixture": "new-public-qualification"}
    )
    with patch.object(S, "parent_binding", return_value=parent):
        auth = C.candidate(history, mode, qualification)
    claim = S.claim_value(auth, REV, REV, "0" * 64)
    authorization = snap(C.authorization_for(mode), C.canonical(auth))
    raw = snap(C.raw_authorization_for(mode), C.canonical(auth))
    state = C._Session(
        history,
        mode,
        "BEFORE",
        reviewed=REV,
        auth=auth,
        authorization=authorization,
        raw_authorization=raw,
        qualification=qualification,
    )
    binding = C.run_binding(state, claim)
    receipt = C.digested(
        dict(
            integrity={"replayed_trace_count": 1024, "budget_prefix_check_count": 512},
            reduction={"exact_success": {"screen_conjunction": False}},
            replication_cells_executed=0 if mode == S.PUBLIC else 1024,
            scientific_decision=None
            if mode == S.PUBLIC
            else "STOP_REPAIR_REPLICATION_SCREEN_NOT_MET",
        )
    )
    publication = SimpleNamespace(
        binding=binding,
        rows=[],
        receipt=receipt,
        commit=C.digested({"fixture": "committed"}),
        revalidate=Mock(),
    )
    claimed = snap(S.claim_path(auth), C.canonical(claim))
    fence = (
        snap(C.FENCE, C.canonical(C.fence_value(auth, REV, REV)))
        if mode == S.PUBLIC
        else None
    )
    saved = C._Saved(mode, publication, authorization, raw, claimed, fence)
    return SimpleNamespace(
        mode=mode,
        state=state,
        history=history,
        source=source,
        parent=parent,
        auth=auth,
        claim=claim,
        claim_snapshot=claimed,
        fence=fence,
        publication=publication,
        receipt=receipt,
        saved=saved,
        binding=binding,
        public=public,
        sealed=sealed,
    )


def checks(f):
    stack = ExitStack()
    for target, name, value in (
        (C, "guard", Mock()),
        (G, "clean", Mock()),
        (R, "reviewed_file", Mock()),
        (S, "parent_binding", Mock(return_value=f.parent)),
        (C, "original_unused", Mock()),
        (C, "public_unused", Mock()),
        (C, "exact_ledger", Mock()),
        (os.path, "lexists", Mock(return_value=False)),
    ):
        stack.enter_context(patch.object(target, name, value))
    return stack


class ShapeAndInterfaceTests(unittest.TestCase):
    def test_static_guard_and_separate_fixed_names(self):
        self.assertEqual(C.self_test()["new_public_attempts"], 0)
        self.assertNotEqual(C.FENCE, C.C.FENCE)
        self.assertEqual(C.output_for(S.REPLICATION), C.B.OUTPUT)
        self.assertEqual(C.summary_for(S.REPLICATION), C.C.REPLICATION_SUMMARY)

    def test_static_self_test_accepts_existing_cache_without_live_attestation(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "runtime.pyc"
            cache.write_bytes(b"synthetic existing cache")
            with patch.object(G, "__cached__", str(cache)):
                value = C.self_test()
            self.assertFalse(value["genuine_reconstruction_performed"])
            self.assertFalse(value["replication_execution_authorized"])
            self.assertEqual(value["new_public_attempts"], 0)
            self.assertEqual(cache.read_bytes(), b"synthetic existing cache")

    def test_static_guard_still_rejects_runtime_origin_substitution(self):
        with patch.object(G, "__file__", str(ROOT / "foreign.py")):
            with self.assertRaisesRegex(Exception, "runtime source origin"):
                C.guard()

    def test_candidate_roundtrip_both_modes(self):
        for mode in (S.PUBLIC, S.REPLICATION):
            f = fixture(mode)
            self.assertEqual(
                C.auth_shape(C.canonical(f.auth), mode, f.auth["deterministic_digest"]),
                f.auth,
            )

    def test_candidate_denominator_boolean_float_aliases(self):
        for value in (True, 1024.0, "1024", 512):
            f = fixture()
            auth = rehash({**f.auth, "expected_cell_count": value})
            with self.subTest(value=value), self.assertRaises(Exception):
                C.auth_shape(C.canonical(auth), S.PUBLIC, auth["deterministic_digest"])

    def test_closed_candidate_negative_mutations(self):
        f = fixture()
        for update in (
            {"unexpected": 1},
            {"output_path": "/tmp/elsewhere"},
            {"attempt_id": "retry"},
            {"candidate_is_execution_authority": True},
            {"requires_explicit_digest_confirmation": False},
            {"locked_128_evaluation_authorized": 0},
            {"execution_mode": S.REPLICATION},
            {"connector_qualification": {}},
            {"receiver_certificate": []},
        ):
            auth = rehash({**f.auth, **update})
            with self.subTest(update=update), self.assertRaises(Exception):
                C.auth_shape(C.canonical(auth), S.PUBLIC, auth["deterministic_digest"])

    def test_exact_digest_never_defaulted_by_run(self):
        for value in (None, "", "a", True, "A" * 64):
            with (
                self.subTest(value=value),
                patch.object(C, "_STARTED", False),
                patch.object(C, "guard"),
                patch.object(C, "session") as session,
            ):
                with self.assertRaises(Exception):
                    C.run(S.PUBLIC, REV, REV, value)
                session.assert_not_called()

    def test_duplicate_nonfinite_noncanonical_and_wrong_digest(self):
        f = fixture()
        for raw in (b'{"x":1,"x":2}\n', b'{"x":NaN}\n', b" {}\n", C.canonical(f.auth)):
            with self.subTest(raw=raw[:25]), self.assertRaises(Exception):
                C.auth_shape(raw, S.PUBLIC, "0" * 64)

    def test_runtime_and_dispatch_substitutions_reject(self):
        for module, name in (
            (G, "open_history"),
            (S, "consume"),
            (R, "record"),
            (C.F, "consume"),
            (C._Session, "check"),
        ):
            with self.subTest(name=name), patch.object(module, name, Mock()):
                with self.assertRaisesRegex(Exception, "substitut"):
                    C.guard()

    def test_path_or_attempt_configuration_substitution_rejects(self):
        for name, value in (
            ("PUBLIC_ATTEMPT", "retry"),
            ("FENCE", C.FENCE.with_name("foreign.json")),
        ):
            with self.subTest(name=name), patch.object(C, name, value):
                with self.assertRaisesRegex(Exception, "fixed configuration"):
                    C.guard()

    def test_run_exposes_no_proof_callback_or_path_parameters(self):
        for extra in (
            {"proof": {}},
            {"observe": lambda x: None},
            {"output_path": "/tmp/x"},
            {"skip_unused": True},
        ):
            with self.subTest(extra=extra), self.assertRaises(TypeError):
                C.run(S.PUBLIC, REV, REV, "a" * 64, **extra)

    def test_cli_self_test_from_outside_checkout(self):
        env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
        result = subprocess.run(
            [sys.executable, "-P", "-B", str(ROOT / C.SCRIPT), "--self-test"],
            cwd="/tmp",
            env=env,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertFalse(C.parse(result.stdout)["replication_execution_authorized"])

    def test_cli_has_no_production_or_override_mode(self):
        env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
        for args in (
            ("--run-replication",),
            ("--run-public",),
            ("--self",),
            ("--self-test", "--confirm-digest", "a" * 64),
            ("--inspect", "--output", "/tmp/x"),
        ):
            with self.subTest(args=args):
                result = subprocess.run(
                    [sys.executable, "-P", "-B", str(ROOT / C.SCRIPT), *args],
                    cwd="/tmp",
                    env=env,
                    capture_output=True,
                )
                self.assertEqual(result.returncode, 2)


class LifecycleTests(unittest.TestCase):
    def test_before_requires_exact_old_ledger_and_original_absence(self):
        f = fixture()
        with checks(f):
            f.state.check()
            C.original_unused.assert_called_once()
            C.public_unused.assert_called_once()
            self.assertEqual(len(C.exact_ledger.call_args.args[0]), 3)

    def test_fenced_then_claimed_exact_ledger_transition(self):
        f = fixture()
        with checks(f):
            f.state.phase, f.state.fence = "FENCED", f.fence
            f.state.check()
            self.assertEqual(len(C.exact_ledger.call_args.args[0]), 4)
            f.state.phase, f.state.claim = "CLAIMED", f.claim_snapshot
            f.state.check()
            self.assertEqual(len(C.exact_ledger.call_args.args[0]), 5)
            C.public_unused.assert_not_called()

    def test_consumed_public_requires_both_exact_claim_and_fence(self):
        for missing in ("claim", "fence"):
            f = fixture()
            f.state.phase, f.state.claim, f.state.fence = (
                "CLAIMED",
                f.claim_snapshot,
                f.fence,
            )
            setattr(f.state, missing, None)
            with self.subTest(missing=missing), checks(f), self.assertRaises(Exception):
                f.state.check()

    def test_consumed_claim_cannot_bind_a_different_candidate(self):
        f = fixture()
        f.state.phase, f.state.fence = "CLAIMED", f.fence
        changed = rehash({**f.claim, "authorization_digest": "1" * 64})
        f.state.claim = snap(f.claim_snapshot.path, C.canonical(changed))
        with checks(f), self.assertRaisesRegex(Exception, "owned claim linkage"):
            f.state.check()

    def test_saved_production_does_not_reapply_unused(self):
        f, p = fixture(S.REPLICATION), fixture()
        f.state.phase, f.state.saved, f.state.public_saved = "SAVED", f.saved, p.saved
        with checks(f):
            f.state.check()
            C.original_unused.assert_not_called()
            self.assertEqual(len(C.exact_ledger.call_args.args[0]), 6)

    def test_saved_public_accepts_only_exact_committed_original_context(self):
        f, original = fixture(), fixture(S.REPLICATION)
        f.state.phase, f.state.saved, f.state.original_saved = (
            "SAVED",
            f.saved,
            original.saved,
        )
        with checks(f):
            f.state.check()
            C.original_unused.assert_not_called()
            self.assertEqual(len(C.exact_ledger.call_args.args[0]), 6)
        f.state.phase = "BEFORE"
        with checks(f), self.assertRaisesRegex(Exception, "saved PUBLIC analysis"):
            f.state.check()

    def test_unknown_lifecycle_and_unowned_saved_state_reject(self):
        f = fixture()
        for phase in ("RELAXED", "SAVED"):
            f.state.phase = phase
            with self.subTest(phase=phase), checks(f), self.assertRaises(Exception):
                f.state.check()

    def test_source_evidence_drift_stops_before_ledger(self):
        f = fixture()
        f.history.revalidate.side_effect = ValueError("evidence drift")
        with checks(f), self.assertRaisesRegex(ValueError, "evidence drift"):
            f.state.check()

    def test_old_entrypoint_slot_never_adopted(self):
        f = fixture()
        with (
            checks(f),
            patch.object(
                os.path,
                "lexists",
                side_effect=lambda path: path == C.ORIGINAL_PREFLIGHT,
            ),
        ):
            with self.assertRaisesRegex(Exception, "old entrypoint"):
                f.state.check()


class RealLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="e4-ledger-test-")
        self.path = Path(self.temp.name) / "ledger"
        self.path.mkdir(mode=0o700)
        self.patch = patch.object(S, "LEDGER", self.path)
        self.patch.start()
        self.rows = {}
        for index in range(3):
            path = self.path / (str(index) + ".json")
            path.write_bytes(b"{}\n")
            path.chmod(0o600)
            self.rows[path] = C.core.FileSnapshot.capture(path)

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_exact_set_then_owned_addition(self):
        C.exact_ledger(self.rows)
        path = self.path / "fence.json"
        path.write_bytes(b"{}\n")
        path.chmod(0o600)
        with self.assertRaises(Exception):
            C.exact_ledger(self.rows)
        self.rows[path] = C.core.FileSnapshot.capture(path)
        C.exact_ledger(self.rows)

    def test_old_bytes_change_rejected(self):
        next(iter(self.rows)).write_bytes(b'{"changed":true}\n')
        with self.assertRaises(Exception):
            C.exact_ledger(self.rows)

    def test_same_bytes_replacement_not_adopted(self):
        path = next(iter(self.rows))
        other = self.path / "replacement"
        other.write_bytes(path.read_bytes())
        other.chmod(0o600)
        other.replace(path)
        with self.assertRaises(Exception):
            C.exact_ledger(self.rows)

    def test_extra_dangling_name_rejected(self):
        (self.path / "extra.json").symlink_to(self.path / "missing")
        with self.assertRaises(Exception):
            C.exact_ledger(self.rows)

    def test_nonprivate_ledger_rejected(self):
        self.path.chmod(0o755)
        with self.assertRaises(Exception):
            C.exact_ledger(self.rows)


def run_patches(f):
    stack = ExitStack()
    state = f.state
    state.check = Mock()
    C._CURRENT = state
    for target, name, value in (
        (C, "_STARTED", False),
        (C, "guard", Mock()),
        (C, "original_unused", Mock()),
        (C, "public_unused", Mock()),
        (S, "descriptor_preflight", Mock()),
        (C, "session", Mock(return_value=state)),
        (C, "reconstruct_and_admit", Mock(return_value=f.auth)),
        (G.N, "progress", Mock()),
        (C.F, "consume", Mock(return_value=({}, f.fence))),
        (S, "consume", Mock(return_value=(f.claim, f.claim_snapshot))),
        (
            R,
            "record",
            Mock(
                side_effect=lambda inputs, cell, binding: {
                    "cell_index": cell["cell_index"]
                }
            ),
        ),
        (R, "reduce_rows", Mock(return_value=f.receipt)),
    ):
        stack.enter_context(patch.object(target, name, value))
    return stack


class SharedExecutionTests(unittest.TestCase):
    def tearDown(self):
        C._CURRENT = None

    def test_both_modes_share_all_1024_ordered_emissions(self):
        for mode in (S.PUBLIC, S.REPLICATION):
            f, emitted = fixture(mode), []

            def publish(output, binding, action, check):
                check()
                action(lambda index, row: emitted.append(index))
                check()
                return f.publication.commit

            with (
                self.subTest(mode=mode),
                run_patches(f),
                patch.object(S, "publish", side_effect=publish),
            ):
                result = C.run(mode, REV, REV, f.auth["deterministic_digest"])
                self.assertEqual(emitted, list(range(1024)))
                self.assertEqual(R.record.call_count, 1024)
                self.assertTrue(result["effects"]["publication_committed"])
                self.assertTrue(result["effects"]["authorization_consumed"])
                self.assertEqual(C.F.consume.call_count, int(mode == S.PUBLIC))

    def test_first_fence_must_succeed_before_second_claim(self):
        f = fixture()
        with (
            run_patches(f),
            patch.object(
                C.F,
                "consume",
                side_effect=S.ExecutionFailure(
                    "CONSUMPTION_UNCERTAIN", None, "fence failed"
                ),
            ),
            patch.object(S, "publish") as publish,
        ):
            with self.assertRaises(S.ExecutionFailure):
                C.run(S.PUBLIC, REV, REV, f.auth["deterministic_digest"])
            S.consume.assert_not_called()
            publish.assert_not_called()
            self.assertIsNone(f.state.effects["fixed_attempt_consumed"])
            self.assertIs(f.state.effects["authorization_consumed"], False)

    def test_spent_fence_does_not_make_second_claim_successful(self):
        for outcome in (None, False):
            f = fixture()
            with (
                self.subTest(outcome=outcome),
                run_patches(f),
                patch.object(
                    S,
                    "consume",
                    side_effect=S.ExecutionFailure(
                        "CONSUMPTION_UNCERTAIN", outcome, "claim failed"
                    ),
                ),
                patch.object(S, "publish") as publish,
            ):
                with self.assertRaises(S.ExecutionFailure):
                    C.run(S.PUBLIC, REV, REV, f.auth["deterministic_digest"])
                self.assertIs(f.state.effects["fixed_attempt_consumed"], True)
                self.assertIs(f.state.effects["authorization_consumed"], outcome)
                publish.assert_not_called()

    def test_generic_claim_failure_retains_unknown(self):
        f = fixture()
        with run_patches(f), patch.object(S, "consume", side_effect=OSError("unknown")):
            with self.assertRaises(OSError):
                C.run(S.PUBLIC, REV, REV, f.auth["deterministic_digest"])
            self.assertIsNone(f.state.effects["authorization_consumed"])

    def test_returned_consumption_stays_true_if_later_linkage_fails(self):
        f = fixture()
        with (
            run_patches(f),
            patch.object(
                S,
                "consume",
                return_value=(f.claim, snap(f.claim_snapshot.path, b"{}\n")),
            ),
        ):
            with self.assertRaisesRegex(Exception, "returned owned claim"):
                C.run(S.PUBLIC, REV, REV, f.auth["deterministic_digest"])
            self.assertIs(f.state.effects["authorization_consumed"], True)

    def test_publication_failure_distinguishes_known_and_unknown(self):
        for status, expected in (
            ("SPENT_NOT_RUN", False),
            ("INVALID_ANALYSIS", False),
            ("PUBLICATION_UNCERTAIN", None),
        ):
            f = fixture()
            with (
                self.subTest(status=status),
                run_patches(f),
                patch.object(
                    S,
                    "publish",
                    side_effect=S.ExecutionFailure(status, True, "failure"),
                ),
            ):
                with self.assertRaises(S.ExecutionFailure):
                    C.run(S.PUBLIC, REV, REV, f.auth["deterministic_digest"])
                self.assertIs(f.state.effects["publication_committed"], expected)
                self.assertIs(f.state.effects["authorization_consumed"], True)

    def test_failure_after_commit_retains_true(self):
        f = fixture()

        def committed(*args):
            f.state.check.side_effect = ValueError("source drift after commit")
            return f.publication.commit

        with run_patches(f), patch.object(S, "publish", side_effect=committed):
            with self.assertRaisesRegex(ValueError, "source drift"):
                C.run(S.PUBLIC, REV, REV, f.auth["deterministic_digest"])
            self.assertIs(
                C.failure(ValueError("failed"))["effects"]["publication_committed"],
                True,
            )

    def test_same_process_retry_rejected_before_effect(self):
        f = fixture()
        with (
            run_patches(f),
            patch.object(S, "publish", return_value=f.publication.commit),
        ):
            C.run(S.PUBLIC, REV, REV, f.auth["deterministic_digest"])
            with self.assertRaisesRegex(Exception, "fresh process"):
                C.run(S.PUBLIC, REV, REV, f.auth["deterministic_digest"])
            self.assertEqual(S.consume.call_count, 1)

    def test_partial_work_survives_failure_receipt(self):
        f = fixture()
        f.history.work["baseline_traces_completed"] = 32
        f.history.work["public_archives"][0]["replayed_traces_completed"] = None
        C._CURRENT = f.state
        value = C.failure(ValueError("stopped"))
        self.assertEqual(value["work"]["baseline_traces_completed"], 32)
        self.assertIsNone(
            value["work"]["public_archives"][0]["replayed_traces_completed"]
        )
        self.assertFalse(value["automatic_retry_allowed"])

    def test_stdout_failure_retains_complete_operation(self):
        f = fixture()
        f.state.effects["publication_committed"] = True
        C._CURRENT = f.state
        complete = C.operation(f.state, "E4_EXECUTION_COMMITTED")

        class Short(io.BytesIO):
            def write(self, raw):
                return max(0, len(raw) - 1)

        stderr = io.BytesIO()
        argv = [
            C.SCRIPT,
            "--run-public",
            "--implementation-revision",
            REV,
            "--reviewed-revision",
            REV,
            "--confirm-digest",
            f.auth["deterministic_digest"],
        ]
        with (
            patch.object(sys, "argv", argv),
            patch.object(C, "run", return_value=complete),
            patch.object(sys, "stdout", SimpleNamespace(buffer=Short())),
            patch.object(sys, "stderr", SimpleNamespace(buffer=stderr)),
        ):
            with self.assertRaises(SystemExit):
                C.main()
        result = C.parse(stderr.getvalue())
        self.assertEqual(result["completed_operation"], complete)
        self.assertTrue(result["effects"]["publication_committed"])


class ReconstructionAndAnalysisTests(unittest.TestCase):
    def test_whole_candidate_reconstruction_compared(self):
        f = fixture()
        f.state.check = Mock()
        with (
            patch.object(G, "reconstruct") as reconstruct,
            patch.object(C, "candidate", return_value=f.auth),
        ):
            C.reconstruct_and_admit(f.state)
            reconstruct.assert_called_once_with(f.history)
        changed = rehash({**f.auth, "runtime": {"changed": True}})
        with (
            patch.object(G, "reconstruct"),
            patch.object(C, "candidate", return_value=changed),
        ):
            with self.assertRaisesRegex(Exception, "whole genuinely reconstructed"):
                C.reconstruct_and_admit(f.state)

    def test_production_requires_new_public_replay_gate(self):
        f = fixture(S.REPLICATION)
        f.state.check = Mock()
        with (
            patch.object(G, "reconstruct"),
            patch.object(
                C,
                "replay_public_qualification",
                side_effect=ValueError("no qualified PUBLIC"),
            ),
            patch.object(C, "candidate") as candidate,
        ):
            with self.assertRaisesRegex(ValueError, "no qualified PUBLIC"):
                C.reconstruct_and_admit(f.state)
            candidate.assert_not_called()

    def test_analysis_replays_and_compares_whole_saved_receipt(self):
        f = fixture()
        f.state.saved, f.state.phase, f.state.check = f.saved, "SAVED", Mock()
        with (
            patch.object(C, "reconstruct_and_admit"),
            patch.object(R, "reduce_rows", return_value=f.receipt),
        ):
            value = C._analyze(f.state)
            self.assertIsNone(value["scientific_decision"])
            self.assertEqual(value["source_multiset_count"], 1)
            self.assertFalse(value["replication_execution_authorized"])
            self.assertEqual(
                value["historical_screen_conjunction"],
                {"original_public": False, "receiver_v2_public": False},
            )
        changed = rehash({**f.receipt, "unused_field": True})
        with (
            patch.object(C, "reconstruct_and_admit"),
            patch.object(R, "reduce_rows", return_value=changed),
        ):
            with self.assertRaisesRegex(Exception, "whole saved execution receipt"):
                C._analyze(f.state)

    def test_public_analysis_reconstructs_consumed_original_candidate(self):
        f, original = fixture(), fixture(S.REPLICATION)
        f.state.saved, f.state.phase, f.state.check = f.saved, "SAVED", Mock()
        f.state.original_saved = original.saved
        summary = snap(
            ROOT / C.SUMMARY_MIRROR,
            C.canonical(C.analysis_value(f.history, f.saved, f.receipt)),
        )
        with (
            patch.object(C, "reconstruct_and_admit"),
            patch.object(R, "reduce_rows", return_value=f.receipt),
            patch.object(C, "reviewed_public_summary", return_value=summary),
            patch.object(C, "candidate", return_value=original.auth) as candidate,
        ):
            C._analyze(f.state)
            self.assertEqual(candidate.call_args.args[1], S.REPLICATION)
        with (
            patch.object(C, "reconstruct_and_admit"),
            patch.object(R, "reduce_rows", return_value=f.receipt),
            patch.object(C, "reviewed_public_summary", return_value=summary),
            patch.object(C, "candidate", return_value=f.auth),
        ):
            with self.assertRaisesRegex(Exception, "owned original candidate"):
                C._analyze(f.state)

    def test_saved_binding_entire_equality(self):
        f = fixture()
        f.state.saved, f.state.phase, f.state.check = f.saved, "SAVED", Mock()
        wrong = copy.deepcopy(f.binding)
        wrong["authorization_path"] = "/tmp/forged"
        f.publication.binding = rehash(wrong)
        with (
            patch.object(G, "reconstruct"),
            patch.object(C, "candidate", return_value=f.auth),
        ):
            with self.assertRaisesRegex(Exception, "complete admitted run binding"):
                C.reconstruct_and_admit(f.state)

    def test_verify_full_summary_not_selected_fields(self):
        f = fixture()
        value = C.analysis_value(f.history, f.saved, f.receipt)
        wrong = rehash({**value, "task_count": 63})
        f.state.check = Mock()
        f.history_state = SimpleNamespace(evidence=SimpleNamespace(snapshots=[]))
        with (
            patch.object(C, "begin"),
            patch.object(C, "session", return_value=f.state),
            patch.object(
                R,
                "snapshot_file",
                return_value=snap(C.PUBLIC_SUMMARY, C.canonical(wrong)),
            ),
            patch.object(G, "_state", return_value=f.history_state),
            patch.object(C, "_analyze", return_value=value),
        ):
            with self.assertRaisesRegex(Exception, "entire saved summary"):
                C.analyze(S.PUBLIC, REV, verify=True)

    def test_qualification_replays_before_whole_summary_comparison(self):
        f, p = fixture(S.REPLICATION), fixture()
        f.state.public_saved, f.state.check = p.saved, Mock()
        value = C.analysis_value(f.history, p.saved, p.receipt)
        summary = snap(ROOT / C.SUMMARY_MIRROR, C.canonical(value))
        with (
            patch.object(C, "candidate", return_value=p.auth),
            patch.object(C, "reviewed_public_summary", return_value=summary),
            patch.object(R, "reduce_rows", return_value=p.receipt) as replay,
        ):
            self.assertEqual(
                C.replay_public_qualification(f.state), C.qualification_reference(value)
            )
            replay.assert_called_once()
        changed = rehash({**value, "task_count": 63})
        with (
            patch.object(C, "candidate", return_value=p.auth),
            patch.object(
                C,
                "reviewed_public_summary",
                return_value=snap(summary.path, C.canonical(changed)),
            ),
            patch.object(R, "reduce_rows", return_value=p.receipt),
        ):
            with self.assertRaisesRegex(Exception, "whole reviewed PUBLIC summary"):
                C.replay_public_qualification(f.state)

    def test_qualification_requires_original_reviewed_mirrors_and_raw_copy(self):
        f, p = fixture(S.REPLICATION), fixture()
        value = C.analysis_value(f.history, p.saved, p.receipt)
        rows = {
            ROOT / C.SUMMARY_MIRROR: snap(ROOT / C.SUMMARY_MIRROR, C.canonical(value)),
            ROOT / C.COMMIT_MIRROR: snap(
                ROOT / C.COMMIT_MIRROR, C.canonical(p.publication.commit)
            ),
            C.PUBLIC_SUMMARY: snap(C.PUBLIC_SUMMARY, C.canonical(value)),
        }
        history_state = SimpleNamespace(evidence=SimpleNamespace(snapshots=[]))
        with (
            patch.object(R, "snapshot_file", side_effect=lambda path: rows[path]),
            patch.object(R, "reviewed_file") as reviewed,
            patch.object(G, "_state", return_value=history_state),
        ):
            C.reviewed_public_summary(f.state, REV, p.saved)
            self.assertEqual(reviewed.call_count, 2)
            self.assertTrue(all(rev == REV for _, rev in f.state.qualifier_snapshots))
            rows[C.PUBLIC_SUMMARY].raw = b"{}\n"
            with self.assertRaisesRegex(Exception, "raw PUBLIC summary"):
                C.reviewed_public_summary(f.state, REV, p.saved)


class SavedAdmissionTests(unittest.TestCase):
    def patches(self, f):
        stack = ExitStack()
        rows = {
            C.authorization_for(f.mode): f.state.authorization,
            C.raw_authorization_for(f.mode): f.state.raw_authorization,
            f.claim_snapshot.path: f.claim_snapshot,
        }
        if f.fence is not None:
            rows[C.FENCE] = f.fence
        for target, name, value in (
            (S, "inspect", Mock(return_value=f.publication)),
            (R, "oid", lambda x: x),
            (R, "snapshot_file", Mock(side_effect=lambda path: rows[path])),
            (R, "reviewed_file", Mock()),
            (C.core, "require_ancestor", Mock()),
        ):
            stack.enter_context(patch.object(target, name, value))
        return stack

    def test_exact_persisted_claim_and_fence(self):
        f = fixture()
        with self.patches(f):
            saved = C.load_saved(S.PUBLIC, f.source)
            self.assertEqual(saved.binding, f.binding)
            f.claim_snapshot.revalidate.assert_called_once()
            f.fence.revalidate.assert_called_once()

    def test_claim_or_fence_rehashed_drift_rejected(self):
        for field in ("claim_snapshot", "fence"):
            f = fixture()
            item = getattr(f, field)
            changed = C.parse(item.raw)
            changed["reviewed_revision"] = "a" * 40
            item.raw = C.canonical(rehash(changed))
            with (
                self.subTest(field=field),
                self.patches(f),
                self.assertRaises(Exception),
            ):
                C.load_saved(S.PUBLIC, f.source)

    def test_foreign_authorization_path_rejected_before_read(self):
        f = fixture()
        value = {**f.binding, "authorization_path": "/tmp/forged"}
        f.publication.binding = rehash(value)
        with self.patches(f):
            with self.assertRaisesRegex(
                Exception, "fixed persisted output/authorization"
            ):
                C.load_saved(S.PUBLIC, f.source)
            R.snapshot_file.assert_not_called()

    def test_saved_source_mismatch_is_not_admission(self):
        f = fixture()
        with (
            self.patches(f),
            self.assertRaisesRegex(Exception, "reviewed E4 source differs"),
        ):
            C.load_saved(S.PUBLIC, {**f.source, "extra": True})

    def test_public_saved_context_rejects_partial_original_before_reconstruction(self):
        f = fixture()
        with (
            patch.object(G, "open_history", return_value=f.history),
            patch.object(
                C, "load_saved", side_effect=[f.saved, ValueError("partial original")]
            ),
            patch.object(os.path, "lexists", return_value=True),
            patch.object(G, "reconstruct") as reconstruct,
        ):
            with self.assertRaisesRegex(ValueError, "partial original"):
                C.session(S.PUBLIC, REV, saved=True)
            reconstruct.assert_not_called()


if __name__ == "__main__":
    unittest.main()
