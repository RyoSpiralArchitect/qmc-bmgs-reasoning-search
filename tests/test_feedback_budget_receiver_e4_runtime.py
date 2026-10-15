"""Explicit MOCK reconstruction/issuance fixtures; no real numerical operation."""

from __future__ import annotations

from contextlib import ExitStack
import copy
import importlib.util
import os
from pathlib import Path
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "e4_runtime_tested", ROOT / "scripts/feedback_budget_receiver_e4_runtime.py"
)
G = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = G
spec.loader.exec_module(G)


def snapshot(path, raw):
    return SimpleNamespace(
        path=Path(path),
        raw=raw,
        revalidate=Mock(),
        generation=(1, 2, stat.S_IFREG | 0o600, 1, os.geteuid(), 20, len(raw), 10, 10),
    )


def bundle_fixture():
    locations = {"persistent_locations": {"output_parent": {"components": []}}}
    publisher = {"certifier": {"frozen_reconstruction": {}}}
    source = {"publisher_source": publisher}
    certificate = dict.fromkeys(set(G.K.CERTIFICATE_KEYS) - {"deterministic_digest"})
    certificate["receiver_identity"] = {
        "persistent_locations": locations["persistent_locations"]
    }
    certificate = G.digested(certificate)
    verification = G.digested({"publisher_source": publisher})
    payload = {
        "certificate.json": G.canonical(certificate),
        "verification.json": G.canonical(verification),
    }
    commit = G.digested(
        dict(
            payloads={name: G.N.reference(raw) for name, raw in payload.items()},
            bundle_location=dict(
                path=str(G.P.BUNDLE),
                persistent_components=[dict(volume_uuid="fixture-volume", inode=2)],
            ),
        )
    )
    payload["COMMIT.json"] = G.canonical(commit)
    operation = dict(
        publisher_source=publisher,
        certificate_issued=True,
        execution_dispatch_entered=False,
        claim_ceiling=G.K.ceiling(),
        **{
            key: G.N.reference(payload[name])
            for key, name in zip(
                ("certificate", "verification", "commit"), G.P.NAMES, strict=True
            )
        },
    )
    data = {
        G.PREFIX + suffix: payload[name]
        for name, suffix in zip(
            G.P.NAMES,
            ("certificate.json", "verification.json", "commit.json"),
            strict=True,
        )
    }
    data[G.OPERATIONS] = G.canonical(G.digested(dict(issuance_operation=operation)))
    pins = {name: (len(raw), G.sha(raw)) for name, raw in data.items()}
    events, rows = [], {}

    def read(path, expected=None):
        events.append(("read", str(path)))
        relative = str(Path(path).relative_to(ROOT))
        raw = (
            payload[Path(path).name]
            if Path(path).parent == G.P.BUNDLE
            else data[relative]
        )
        if expected is not None:
            G.require(raw == expected, "fixture bytes differ")
        result = snapshot(path, raw)
        rows[str(path)] = result
        return result

    evidence = SimpleNamespace(
        file=Mock(side_effect=read),
        archive=Mock(return_value=SimpleNamespace(raw=payload)),
    )
    parent = SimpleNamespace(
        descriptor=9, component_identities=((1, 2),), assert_path=Mock(), close=Mock()
    )
    return SimpleNamespace(
        data=data,
        pins=pins,
        source=source,
        certificate=certificate,
        locations=locations,
        payload=payload,
        evidence=evidence,
        parent=parent,
        events=events,
        rows=rows,
    )


def issued_patches(f):
    stack = ExitStack()
    for target, name, value in (
        (G, "PINS", f.pins),
        (G.R, "reviewed_file", Mock()),
        (G.K, "historical", Mock(return_value={})),
        (G.K, "_projection", Mock(return_value=f.certificate)),
        (G.K, "_volume_uuid", Mock(return_value="fixture-volume")),
        (G.M._PinnedParent, "open", Mock(return_value=f.parent)),
    ):
        stack.enter_context(patch.object(target, name, value))
    return stack


class IdentityAndIssuedTests(unittest.TestCase):
    def test_exact_five_file_closure_and_issued_review(self):
        self.assertEqual(len(set(G.SOURCE_FILES)), 5)
        self.assertEqual(G.ISSUED_REVIEW, "d41a49fb6eafe30005718d27b9fa4b926dce1cce")
        self.assertNotIn(G.PUBLISHER, G.SOURCE_FILES)

    def test_static_runtime_guard(self):
        G.guard()

    def test_live_attestation_rejects_cache_before_source_or_evidence_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "runtime.pyc"
            cache.write_bytes(b"synthetic existing cache")
            with (
                patch.object(sys, "pycache_prefix", directory),
                patch.object(G, "__cached__", str(cache)),
                patch.object(G.core, "git_head") as head,
                patch.object(G.R, "snapshot_file") as evidence,
                patch.object(G.P, "attest") as publisher,
            ):
                with self.assertRaisesRegex(Exception, "cache not absent"):
                    G.attest("f" * 40)
                head.assert_not_called()
                evidence.assert_not_called()
                publisher.assert_not_called()
            self.assertEqual(cache.read_bytes(), b"synthetic existing cache")

    def test_registered_history_cannot_be_supplied(self):
        with self.assertRaises(TypeError):
            G.History({"status": "PASS"})
        with self.assertRaises(Exception):
            G._state(object.__new__(G.History))

    def test_no_forged_sealed_adapter(self):
        with self.assertRaises(TypeError):
            G.SealedInputs({})
        with self.assertRaises(Exception):
            object.__new__(G.SealedInputs).manifest

    def test_own_property_substitution_rejected(self):
        with patch.object(G.History, "environment", property(lambda self: {})):
            with self.assertRaisesRegex(Exception, "dependency substituted"):
                G.guard()

    def test_frozen_numerical_substitution_rejected(self):
        with patch.object(G.N, "reconstruct_seal", Mock()):
            with self.assertRaisesRegex(Exception, "substitut"):
                G.guard()

    def test_fixed_pin_configuration_substitution_rejected(self):
        with patch.object(G, "PINS", {}):
            with self.assertRaisesRegex(Exception, "fixed configuration"):
                G.guard()

    def test_issued_bundle_exact_mock_fixture(self):
        f = bundle_fixture()
        with issued_patches(f):
            old, raw = G.issued(f.evidence, f.source, f.locations)
        self.assertEqual(old, {})
        self.assertEqual(raw, f.payload["certificate.json"])
        f.parent.close.assert_called_once()

    def test_every_review_pin_authenticated_before_any_parse(self):
        f = bundle_fixture()
        bad = dict(f.pins)
        bad[G.OPERATIONS] = (1, "0" * 64)
        with (
            issued_patches(f),
            patch.object(G, "PINS", bad),
            patch.object(
                G, "parse", Mock(side_effect=AssertionError("parsed early"))
            ) as parse,
        ):
            with self.assertRaisesRegex(Exception, "review pin"):
                G.issued(f.evidence, f.source, f.locations)
            parse.assert_not_called()

    def test_review_failure_does_not_open_raw_bundle(self):
        f = bundle_fixture()
        with (
            issued_patches(f),
            patch.object(G.R, "reviewed_file", side_effect=ValueError("unreviewed")),
        ):
            with self.assertRaisesRegex(ValueError, "unreviewed"):
                G.issued(f.evidence, f.source, f.locations)
        f.evidence.archive.assert_not_called()

    def test_raw_bundle_extra_or_changed_bytes_rejected(self):
        for update in ({"EXTRA": b"x"}, {"certificate.json": b"{}\n"}):
            with self.subTest(update=update):
                f = bundle_fixture()
                f.evidence.archive.return_value = SimpleNamespace(
                    raw={**f.payload, **update}
                )
                with issued_patches(f):
                    with self.assertRaisesRegex(Exception, "raw issued bundle differs"):
                        G.issued(f.evidence, f.source, f.locations)

    def test_persistent_receiver_and_bundle_mismatch_rejected(self):
        f = bundle_fixture()
        with (
            issued_patches(f),
            patch.object(G.K, "_volume_uuid", return_value="different"),
        ):
            with self.assertRaisesRegex(Exception, "persistent location"):
                G.issued(f.evidence, f.source, f.locations)

    def test_raw_payload_requires_private_mode(self):
        f = bundle_fixture()
        read = f.evidence.file.side_effect

        def bad(path, expected=None):
            item = read(path, expected)
            if Path(path).parent == G.P.BUNDLE:
                values = list(item.generation)
                values[2] = stat.S_IFREG | 0o644
                item.generation = tuple(values)
            return item

        f.evidence.file.side_effect = bad
        with issued_patches(f):
            with self.assertRaisesRegex(Exception, "private and owned"):
                G.issued(f.evidence, f.source, f.locations)

    def test_snapshot_only_metadata_has_no_numeric_work(self):
        source = {"publisher_source": {"certifier": {"frozen_reconstruction": {}}}}
        with ExitStack() as stack:
            for target, name, value in (
                (G, "guard", Mock()),
                (G, "clean", Mock()),
                (G, "attest", Mock(return_value=source)),
                (G, "issued", Mock(return_value=({}, b"{}\n"))),
                (G.K, "_capture_locations", Mock(return_value={})),
                (G.K, "_historical_locations", Mock(return_value={})),
                (G.N, "inspect_metadata", Mock(return_value=({}, {}, {}, [], {}))),
                (G.History, "revalidate", Mock()),
            ):
                stack.enter_context(patch.object(target, name, value))
            with (
                patch.object(G.R, "environment", Mock()) as environment,
                patch.object(G.C, "unused", Mock()) as unused,
            ):
                history = G.open_history("f" * 40)
                environment.assert_not_called()
                unused.assert_not_called()
                with self.assertRaisesRegex(Exception, "complete genuine"):
                    history.inputs(G.S.PUBLIC)


def reconstruction_fixture():
    env = {
        name: {"fixture": name}
        for name in ("source", "runtime", "baseline", "authorities", "admission_proof")
    }
    projection = G.R.public_manifest()
    projection = G.digested(
        {
            **G.B.without_digest(projection),
            "execution_mode": G.S.REPLICATION,
            "experiment_id": G.S.REPLICATION_ID,
            "source_multiset_count": 64,
        }
    )
    sealed = {"input_projection": G.N.reference(G.canonical(projection))}
    source = {
        "implementation_revision": "f" * 40,
        "publisher_source": {"certifier": {"frozen_reconstruction": {}}},
    }
    inputs = G.R.load_inputs(G.S.PUBLIC)
    evidence = SimpleNamespace(
        anchors={}, values={G.B.ORIGINAL_CANDIDATE: {}}, snapshots=[]
    )
    for label in G.N.LABELS:
        evidence.values[G.V.PUBLIC_SPECS[label][2]] = {
            "reduction": {"exact_success": {"screen_conjunction": False}}
        }
    final_work = G.N.initial_work()
    final_work["baseline_traces_completed"] = 32
    replays = [
        dict(
            label=label,
            original_generation_reference={"original": True} if i == 0 else None,
        )
        for i, label in enumerate(G.N.LABELS)
    ]
    old = dict(
        source={},
        prior_public_observation=dict(G.N.PRIOR_REFERENCE),
        historical_source_receipts={},
        reviewed_anchors={},
        location_correspondence={},
        public_archive_hash_closures=[],
        sealed_metadata={},
        environment=env,
        work=final_work,
        public_replays=replays,
        public_traces_replayed=2048,
        budget_prefix_comparisons=1024,
        original_sealed_reconstruction=sealed,
        acceptance_order_reconstructed=True,
        original_study_identity=G.S.REPLICATION_ID,
        fixed_replication_claim_path=str(G.B.fixed_claim()),
    )
    certificate = G.digested(
        dict.fromkeys(set(G.K.CERTIFICATE_KEYS) - {"deterministic_digest"})
    )
    state = G._HistoryState(
        source,
        "f" * 40,
        {},
        evidence,
        old,
        {"environment": env},
        {},
        {},
        [],
        {},
        G.canonical(certificate),
        G.N.initial_work(),
    )
    history = object.__new__(G.History)
    G._HISTORIES[history] = state
    return SimpleNamespace(
        state=state,
        history=history,
        environment=env,
        projection=projection,
        sealed=sealed,
        inputs=inputs,
        replays=replays,
        certificate=certificate,
    )


def reconstruction_patches(f):
    stack = ExitStack()
    for target, name, value in (
        (G.History, "revalidate", Mock()),
        (G.N, "progress", Mock()),
        (G.R, "environment", Mock(return_value=f.environment)),
        (G.K.E, "compare_environment", Mock()),
        (G.R, "load_inputs", Mock(return_value=f.inputs)),
        (G.N, "replay_one", Mock(side_effect=f.replays)),
        (G.N, "reconstruct_seal", Mock(return_value=f.sealed)),
        (G.K, "_projection", Mock(return_value=f.certificate)),
        (
            G.N,
            "cohort_archive",
            Mock(return_value=SimpleNamespace(raw={"preregistration.json": b"{}\n"})),
        ),
        (G.B, "input_projection", Mock(return_value=f.projection)),
    ):
        stack.enter_context(patch.object(target, name, value))
    return stack


class ReconstructionTests(unittest.TestCase):
    def test_mock_order_and_whole_certificate_before_adapter(self):
        f = reconstruction_fixture()
        with reconstruction_patches(f):
            self.assertIs(G.reconstruct(f.history), f.history)
            self.assertEqual(
                [call.args[0] for call in G.N.replay_one.call_args_list],
                list(G.N.LABELS),
            )
            G.N.reconstruct_seal.assert_called_once()
            self.assertEqual(f.history.environment, f.environment)
            self.assertIs(type(f.history.inputs(G.S.REPLICATION)), G.SealedInputs)
            self.assertEqual(f.history.inputs(G.S.REPLICATION).manifest, f.projection)
            with self.assertRaisesRegex(Exception, "no reconstruction retry"):
                G.reconstruct(f.history)

    def test_old_whole_field_difference_blocks_completion(self):
        f = reconstruction_fixture()
        f.state.old["reviewed_anchors"] = {"extra": True}
        with reconstruction_patches(f):
            with self.assertRaisesRegex(Exception, "fresh full evidence differs"):
                G.reconstruct(f.history)
        self.assertFalse(f.state.complete)
        with self.assertRaises(Exception):
            f.history.inputs(G.S.REPLICATION)

    def test_partial_failure_preserves_completed_baseline(self):
        f = reconstruction_fixture()
        with (
            reconstruction_patches(f),
            patch.object(G.N, "replay_one", side_effect=ValueError("replay failed")),
        ):
            with self.assertRaisesRegex(ValueError, "replay failed"):
                G.reconstruct(f.history)
            G.N.reconstruct_seal.assert_not_called()
        self.assertEqual(f.history.work["baseline_traces_completed"], 32)
        self.assertFalse(f.state.complete)
        self.assertTrue(f.state.attempted)

    def test_full_certificate_difference_blocks_adapter(self):
        f = reconstruction_fixture()
        changed = copy.deepcopy(f.certificate)
        changed["status"] = "forged"
        changed = G.digested(G.B.without_digest(changed))
        with (
            reconstruction_patches(f),
            patch.object(G.K, "_projection", return_value=changed),
        ):
            with self.assertRaisesRegex(Exception, "entire canonical"):
                G.reconstruct(f.history)
        self.assertFalse(f.state.complete)
        self.assertIsNone(f.state.sealed_inputs)

    def test_whole_projection_reference_required(self):
        f = reconstruction_fixture()
        f.sealed["input_projection"]["sha256"] = "0" * 64
        with reconstruction_patches(f):
            with self.assertRaisesRegex(Exception, "input adapter differs"):
                G.reconstruct(f.history)
        self.assertFalse(f.state.complete)

    def test_sealed_adapter_rejects_aliases_and_full_cell_drift(self):
        f = reconstruction_fixture()
        with reconstruction_patches(f):
            G.reconstruct(f.history)
        adapter = f.history.inputs(G.S.REPLICATION)
        cell = adapter.cells[0]
        for update in (
            {"cell_index": True},
            {"cell_index": -1},
            {"cell_index": 1024},
            {"cell_id": "f" * 64},
        ):
            with self.subTest(update=update):
                with self.assertRaises(Exception):
                    adapter.arguments({**cell, **update})
        changed = adapter.manifest
        changed["tasks"].clear()
        self.assertTrue(adapter.manifest["tasks"])


if __name__ == "__main__":
    unittest.main()
