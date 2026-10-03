"""Synthetic D1 rejection boundaries; none is replay, admission or execution.

T11/T15/T17-T20 deliberately test only the implemented boundary around deferred
operations. See the policy table; these are not future integration qualifications.
"""

from __future__ import annotations

from contextlib import ExitStack
import copy
import importlib.util
import inspect
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
SPEC = importlib.util.spec_from_file_location(
    "successor_inspection_tested",
    ROOT / "scripts/inspect_feedback_budget_receiver_successor.py",
)
assert SPEC is not None and SPEC.loader is not None
V = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = V
SPEC.loader.exec_module(V)
P, C, B, R, S = V.P, V.C, V.B, V.R, V.S


def rehash(value):
    return V.digested(B.without_digest(value))


def snap(path, raw):
    return SimpleNamespace(path=Path(path), raw=raw, revalidate=Mock())


def read(path):
    return V.parse(Path(path).read_bytes())


def fixture():
    values = {path: read(ROOT / path) for path, _ in V.ANCHORS}
    for output, *_ in V.PUBLIC_SPECS.values():
        values[str(output / "STARTED.json")] = read(output / "STARTED.json")
    chains = V.recorded_chains(values)
    locations = {}
    for record, spec in zip(chains, V.REGISTRY):
        locations[spec[-1]] = copy.deepcopy(record["historical"])
        for pair in locations[spec[-1]]["identities"]:
            pair[0] = V.CURRENT_DEVICE
    # Only current-only synthetic bundle location: never a historical record.
    bundle = copy.deepcopy(locations["output_parent"])
    bundle["path"] = str(B.BUNDLE)
    bundle["identities"].append([V.CURRENT_DEVICE, 999999])
    locations["old_bridge_bundle_current_only"] = bundle
    sources = dict(
        original=values[B.ORIGINAL_CANDIDATE]["source"],
        coordinator=values[C.REPLICATION_AUTH]["coordinator_source"],
        preparer=values[V.VERIFICATION]["operator_source"],
    )
    return SimpleNamespace(
        values=values, chains=chains, locations=locations, sources=sources
    )


class InspectionBoundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved = fixture()

    def f(self):
        return copy.deepcopy(self.saved)

    def temporary(self):
        context = tempfile.TemporaryDirectory(
            prefix="qmc-readonly-test-", dir=Path.home()
        )
        self.addCleanup(context.cleanup)
        path = Path(context.name)
        path.chmod(0o700)
        return path

    def receipt(self):
        f = self.f()
        source = V.digested(
            dict(
                schema_version=V.DOMAIN + "/source",
                design_revision=V.DESIGN_REVISION,
                files={
                    path: dict(byte_count=1, sha256="0" * 64) for path in V.SOURCE_FILES
                },
                implementation_revision="f" * 40,
            )
        )
        rows = [
            dict(
                label=label,
                closed_file_count=1027,
                cell_count=1024,
                total_file_bytes=1024,
                inventory_sha256="0" * 64,
                commit_digest="1" * 64,
                summary_digest="2" * 64,
                numerical_replay_performed=False,
            )
            for label in V.PUBLIC_SPECS
        ]
        # A schema-only synthetic comparator, NOT a genuine inspection receipt.
        return V.inspection_receipt(
            source,
            f.sources,
            "f" * 40,
            {
                p: dict(
                    reviewed_revision=r,
                    byte_count=1,
                    sha256="0" * 64,
                    deterministic_digest=f.values[p]["deterministic_digest"],
                )
                for p, r in V.ANCHORS
            },
            V.correspondence(f.chains, f.locations),
            rows,
            dict(
                seal_digest="0" * 64,
                input_manifest_digest="1" * 64,
                schedule_digest="2" * 64,
                task_count=64,
                source_multiset_count=64,
                cell_count=1024,
                acceptance_order_reconstructed=False,
            ),
        )

    def public(self, f, label="receiver_v2_public"):
        output, commit_path, summary_path, *_ = V.PUBLIC_SPECS[label]
        started = f.values[str(output / "STARTED.json")]
        return (
            started["binding"],
            f.values[summary_path],
            read(output / "RECEIPT.json"),
            f.values[commit_path],
        )

    def check_science(self, f, seal=None):
        value = f.values[B.SEAL_MIRROR + "/preregistration.json"]
        return V.scientific_projection(
            f.values[B.ORIGINAL_CANDIDATE],
            f.values[B.CANDIDATE],
            f.values[C.REPLICATION_AUTH],
            seal or value,
            self.saved.values[B.SEAL_MIRROR + "/preregistration.json"],
            f.values[B.PUBLIC_SUMMARY],
        )

    def test_T01_exact_metadata_is_not_reconstruction_or_authority(self):
        f = self.f()
        value = V.correspondence(f.chains, f.locations)
        self.assertEqual([e["chain_count"] for e in value["epochs"].values()], [3, 8])
        for field in (
            "physical_disk_identity_proven",
            "reboot_causality_proven",
            "current_receiver_admitted",
        ):
            self.assertIs(value[field], False)
        self.assertEqual(
            V.inspection_shape(V.canonical(self.receipt()))["claim_ceiling"],
            V.claim_ceiling(),
        )

    def test_T02_cannot_merge_historical_epochs(self):
        f = self.f()
        for record in f.chains:
            record["historical_epoch"] = "original_v7"
            for pair in record["historical"]["identities"]:
                pair[0] = V.EPOCH_DEVICES["original_v7"]
        with self.assertRaisesRegex(ValueError, "registry"):
            V.correspondence(f.chains, f.locations)

    def test_T03_output_parent_alone_or_missing_chain_rejected(self):
        for index in range(11):
            f = self.f()
            f.chains.pop(index)
            with self.subTest(index=index), self.assertRaises(ValueError):
                V.correspondence(f.chains, f.locations)
        f = self.f()
        with self.assertRaises(ValueError):
            V.correspondence(f.chains, {"output_parent": f.locations["output_parent"]})

    def test_T04_inode_prefix_and_current_device_changes_rejected(self):
        mutations = (
            lambda f: f.chains[0]["historical"]["identities"][-1].__setitem__(1, 444),
            lambda f: f.locations["cohort"]["identities"][0].__setitem__(1, 555),
            lambda f: f.locations["ledger"]["identities"][-1].__setitem__(0, 999),
            lambda f: f.locations["old_bridge_bundle_current_only"]["identities"][
                0
            ].__setitem__(1, 777),
        )
        for mutate in mutations:
            f = self.f()
            mutate(f)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                V.correspondence(f.chains, f.locations)

    def test_T05_unknown_duplicate_reordered_owner_and_numeric_alias_rejected(self):
        mutations = (
            lambda f: f.chains[0].__setitem__("historical_epoch", "future"),
            lambda f: f.chains[0].__setitem__("label", "unknown"),
            lambda f: f.chains.__setitem__(1, copy.deepcopy(f.chains[0])),
            lambda f: f.chains.reverse(),
            lambda f: f.chains[0]["owner"].__setitem__("json_pointer", "/invented"),
            lambda f: f.chains[0]["owner"].__setitem__("reviewed_revision", "0" * 40),
            lambda f: f.chains[0].__setitem__("extra", False),
            lambda f: f.chains[0]["historical"]["identities"][0].__setitem__(1, True),
            lambda f: f.chains[0]["historical"]["identities"][0].__setitem__(
                0, float(V.EPOCH_DEVICES["original_v7"])
            ),
            lambda f: f.locations["cohort"]["identities"][0].__setitem__(
                0, float(V.CURRENT_DEVICE)
            ),
            lambda f: f.chains[0]["historical"]["identities"].pop(),
            lambda f: f.chains[0]["historical"].__setitem__(
                "path", str(B.OUTPUT.parent) + "/."
            ),
        )
        for mutate in mutations:
            f = self.f()
            mutate(f)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                V.correspondence(f.chains, f.locations)

    def test_T06_no_invented_historical_bundle_chain(self):
        f = self.f()
        f.chains.append(
            dict(
                label="bundle",
                historical_epoch="receiver_20260921",
                historical=f.locations["old_bridge_bundle_current_only"],
            )
        )
        with self.assertRaises(ValueError):
            V.correspondence(f.chains, f.locations)

    def test_T07_started_hash_checked_before_target_access(self):
        f = self.f()
        output, commit_path, *_ = V.PUBLIC_SPECS["receiver_v2_public"]
        started = f.values[str(output / "STARTED.json")]
        started["binding"]["authorization_path"] = "/untrusted/never-open-this"
        evidence = V.Evidence()
        evidence.values = f.values
        evidence.archive = Mock(
            return_value=SimpleNamespace(
                raw={
                    "STARTED.json": V.canonical(rehash(started)),
                    "COMMIT.json": V.canonical(f.values[commit_path]),
                }
            )
        )
        evidence.file = Mock(
            side_effect=AssertionError("must authenticate before target access")
        )
        with self.assertRaisesRegex(ValueError, "before reference access"):
            V.inspect_public(evidence, "receiver_v2_public", f.sources)
        evidence.file.assert_not_called()

    def test_T08_readonly_archive_rejects_missing_extra_symlink_hardlink(self):
        for mode in ("missing", "extra", "symlink", "hardlink"):
            parent = self.temporary()
            (parent / "a").write_bytes(b"a")
            (parent / "b").write_bytes(b"b")
            (parent / "a").chmod(0o600)
            (parent / "b").chmod(0o600)
            if mode == "missing":
                (parent / "b").unlink()
            elif mode == "extra":
                (parent / "c").write_bytes(b"c")
            else:
                (parent / "b").unlink()
                if mode == "symlink":
                    (parent / "b").symlink_to(parent / "a")
                else:
                    os.link(parent / "a", parent / "b")
            with (
                self.subTest(mode=mode),
                self.assertRaises((ValueError, RuntimeError, OSError)),
            ):
                V.ReadOnlyArchive.capture(parent, {"a", "b"})

    def test_T08_revalidation_rejects_bytes_and_same_byte_generation_change(self):
        for same_bytes in (False, True):
            parent = self.temporary()
            path = parent / "a"
            path.write_bytes(b"a")
            path.chmod(0o600)
            archive = V.ReadOnlyArchive.capture(parent, {"a"})
            if same_bytes:
                observed = path.stat()
                os.utime(
                    path, ns=(observed.st_atime_ns, observed.st_mtime_ns + 1_000_000)
                )
            else:
                path.write_bytes(b"changed")
            with (
                self.subTest(same_bytes=same_bytes),
                self.assertRaises((ValueError, RuntimeError)),
            ):
                archive.revalidate()

    def test_archive_is_read_only_without_fsync_or_old_archive(self):
        parent = self.temporary()
        (parent / "a").write_bytes(b"a")
        (parent / "a").chmod(0o600)
        with (
            patch.object(os, "fsync", side_effect=AssertionError("no fsync")) as fsync,
            patch.object(
                S.mechanics,
                "_forward_sync_exact_regular_file_at",
                side_effect=AssertionError("no forward sync"),
            ) as forward,
            patch.object(
                B,
                "Archive",
                side_effect=AssertionError("old observer has durability effects"),
            ),
        ):
            archive = V.ReadOnlyArchive.capture(parent, {"a"})
            archive.revalidate()
            self.assertEqual(dict(archive.raw), {"a": b"a"})
            fsync.assert_not_called()
            forward.assert_not_called()

    def test_T09_public_source_review_auth_claim_and_summary_linkage(self):
        for mutation in ("review", "source", "authorization", "claim", "summary"):
            f = self.f()
            binding, summary, receipt, commit = self.public(f)
            if mutation == "review":
                binding["reviewed_revision"] = "0" * 40
                binding["claim"] = S.claim_value(
                    binding["authorization"],
                    binding["reviewed_revision"],
                    binding["execution_head_revision"],
                    binding["claim"]["owner_nonce"],
                )
            elif mutation == "source":
                binding["authorization"]["coordinator_source"][
                    "implementation_revision"
                ] = "0" * 40
            elif mutation == "authorization":
                binding["authorization_path"] = "/untrusted/authorization"
            elif mutation == "claim":
                binding["claim"]["owner_nonce"] = "0" * 64
            else:
                summary["source_multiset_count"] = 64
            with (
                self.subTest(mutation=mutation),
                self.assertRaises((ValueError, RuntimeError)),
            ):
                V.public_linkage(
                    "receiver_v2_public",
                    rehash(binding),
                    summary,
                    receipt,
                    commit,
                    f.values,
                    f.sources,
                )

    def test_T09_fixed_fence_rejected_before_cell_loop(self):
        f = self.f()
        output, commit_path, *_ = V.PUBLIC_SPECS["receiver_v2_public"]
        evidence = V.Evidence()
        evidence.values = f.values
        evidence.archive = Mock(
            return_value=SimpleNamespace(
                raw={
                    name: (output / name).read_bytes()
                    for name in ("STARTED.json", "COMMIT.json", "RECEIPT.json")
                }
            )
        )

        def file(path, expected=None):
            if path == C.FENCE:
                raise ValueError("synthetic mismatched fence")
            return snap(path, expected)

        evidence.file = Mock(side_effect=file)
        with self.assertRaisesRegex(ValueError, "mismatched fence"):
            V.inspect_public(evidence, "receiver_v2_public", f.sources)
        self.assertIn(C.FENCE, [call.args[0] for call in evidence.file.call_args_list])

    def test_T10_rehashed_unreviewed_artifact_fails_real_git_byte_check(self):
        for relative, revision in (
            (B.CERTIFICATE, C.BRIDGE_REVIEWED),
            (C.REPLICATION_AUTH, V.EVIDENCE_REVIEW),
        ):
            altered = copy.deepcopy(self.saved.values[relative])
            altered["extra_unreviewed_field"] = "self-consistent hash is insufficient"
            item = snap(ROOT / relative, V.canonical(rehash(altered)))
            evidence = V.Evidence()
            with (
                patch.object(R, "snapshot_file", return_value=item),
                self.assertRaisesRegex(
                    (ValueError, RuntimeError), "reviewed Git bytes"
                ),
            ):
                evidence.anchor(relative, revision)
            self.assertNotIn(relative, evidence.values)

    def test_T11_hash_or_environment_claim_cannot_become_reconstruction(self):
        for field in (
            "numerical_replay_performed",
            "environment_requalified",
            "acceptance_order_reconstructed",
            "certificate_issued",
            "current_receiver_admitted",
        ):
            value = self.receipt()
            value["claim_ceiling"][field] = True
            with self.subTest(field=field), self.assertRaises(ValueError):
                V.inspection_shape(V.canonical(rehash(value)))
        for name in (
            "environment",
            "reconstruct",
            "verify_original_seal",
            "Proof",
            "VerifiedInputs",
        ):
            self.assertFalse(hasattr(V, name))

    def test_T12_original_generation_qualifier_cannot_be_replaced(self):
        f = self.f()
        self.check_science(f)
        seal = copy.deepcopy(f.values[B.SEAL_MIRROR + "/preregistration.json"])
        seal["generation_qualification"] = f.values[C.REPLICATION_AUTH][
            "connector_qualification"
        ]
        with self.assertRaisesRegex(ValueError, "scientific projection"):
            self.check_science(f, rehash(seal))

    def test_T13_full_scientific_fields_order_budget_seed_schedule_thresholds(self):
        for field in (
            "schedule_digest",
            "input_manifest_digest",
            "contract_digest",
            "cohort_seal",
            "baseline",
            "runtime",
            "expected_cell_count",
        ):
            f = self.f()
            f.values[C.REPLICATION_AUTH][field] = None
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.check_science(f)
        for field in (
            "cells",
            "cohort",
            "contract",
            "budget_prefix_pairs",
            "four_cell_blocks",
        ):
            f = self.f()
            seal = copy.deepcopy(f.values[B.SEAL_MIRROR + "/preregistration.json"])
            if field == "cells":
                seal[field].reverse()
            else:
                seal[field] = {
                    "changed": "tasks, rejection order, budget, seed or threshold"
                }
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.check_science(f, rehash(seal))

    def test_T14_no_forged_admission_or_proof_callback_interface(self):
        self.assertEqual(list(inspect.signature(V.inspect).parameters), ["revision"])
        with self.assertRaises(TypeError):
            V.inspect("f" * 40, proof=object(), observe=Mock())
        for name in (
            "Admitted",
            "Inputs",
            "Proof",
            "run",
            "admit",
            "prepare",
            "publish",
            "consume",
        ):
            self.assertFalse(hasattr(V, name))
        with (
            patch.object(C, "attest", return_value={}),
            self.assertRaisesRegex(ValueError, "substituted"),
        ):
            V.inspect("f" * 40)

    def test_T15_static_or_old_public_does_not_qualify_successor(self):
        self.assertEqual(
            V.self_test()["claim_ceiling"]["execution_qualification"],
            "NOT_QUALIFIED_FOR_EXECUTION",
        )
        value = self.receipt()
        value["claim_ceiling"]["execution_qualification"] = "PUBLIC_QUALIFIED"
        with self.assertRaises(ValueError):
            V.inspection_shape(V.canonical(rehash(value)))
        value = self.receipt()
        value["public_archive_hash_closures"][0]["numerical_replay_performed"] = True
        with self.assertRaises(ValueError):
            V.inspection_shape(V.canonical(rehash(value)))

    def test_T16_occupied_slots_including_dangling_symlinks_reject_early(self):
        for slot in ("claim", "output", "summary"):
            for dangling in (False, True):
                parent = self.temporary()
                paths = {name: parent / name for name in ("claim", "output", "summary")}
                path = paths[slot]
                if dangling:
                    path.symlink_to(parent / "missing")
                else:
                    path.write_bytes(b"must retain")
                with (
                    patch.object(B, "fixed_claim", return_value=paths["claim"]),
                    patch.object(B, "OUTPUT", paths["output"]),
                    patch.object(C, "REPLICATION_SUMMARY", paths["summary"]),
                    patch.object(
                        V,
                        "attest",
                        side_effect=AssertionError("must reject before source work"),
                    ) as attestor,
                    self.subTest(slot=slot, dangling=dangling),
                    self.assertRaises((ValueError, S.ExecutionFailure)),
                ):
                    V.inspect("f" * 40)
                attestor.assert_not_called()
                self.assertTrue(os.path.lexists(path))

    def replication_binding(self):
        auth = copy.deepcopy(self.saved.values[C.REPLICATION_AUTH])
        revision = V.EVIDENCE_REVIEW
        return V.digested(
            dict(
                schema_version=S.DOMAIN + "/run-binding",
                execution_mode=S.REPLICATION,
                experiment_id=S.REPLICATION_ID,
                input_manifest_digest=auth["input_manifest_digest"],
                authorization=auth,
                authorization_path=str(ROOT / C.REPLICATION_AUTH),
                reviewed_revision=revision,
                execution_head_revision=revision,
                claim=S.claim_value(auth, revision, revision, "a" * 64),
                replication_execution_authorized=True,
            )
        )

    def test_T17_exact_existing_claim_not_perpetual_absence(self):
        binding = self.replication_binding()
        evidence = V.Evidence()
        item = snap(B.fixed_claim(), V.canonical(binding["claim"]))
        with (
            patch.object(R, "snapshot_file", return_value=item),
            patch.object(
                C,
                "unused",
                side_effect=AssertionError(
                    "persisted analysis must not require absence"
                ),
            ) as unused,
        ):
            result = V.persisted_claim(
                evidence, binding, S.REPLICATION, B.OUTPUT, ROOT / C.REPLICATION_AUTH
            )
            self.assertEqual(result.raw, item.raw)
            unused.assert_not_called()
        item.raw = b"wrong claim\n"
        with (
            patch.object(R, "snapshot_file", return_value=item),
            self.assertRaises(ValueError),
        ):
            V.persisted_claim(
                V.Evidence(),
                binding,
                S.REPLICATION,
                B.OUTPUT,
                ROOT / C.REPLICATION_AUTH,
            )

    def test_T18_head_source_and_current_identity_drift_rejected(self):
        f = self.f()
        source = dict(implementation_revision="f" * 40)
        for fault in (
            "head",
            "source",
            "historical_source",
            "device",
            "inode",
            "evidence",
        ):
            now = copy.deepcopy(f.locations)
            if fault in ("device", "inode"):
                now["ledger"]["identities"][-1][0 if fault == "device" else 1] += 1
            evidence = SimpleNamespace(
                revalidate=Mock(
                    side_effect=ValueError("changed evidence")
                    if fault == "evidence"
                    else None
                )
            )
            with (
                patch.object(V, "_guard"),
                patch.object(
                    V.core,
                    "git_head",
                    return_value="e" * 40 if fault == "head" else "f" * 40,
                ),
                patch.object(
                    V, "attest", return_value={} if fault == "source" else source
                ),
                patch.object(
                    V,
                    "historical_sources",
                    return_value={} if fault == "historical_source" else f.sources,
                ),
                patch.object(V, "current_locations", return_value=now),
                patch.object(C, "unused") as unused,
                self.subTest(fault=fault),
                self.assertRaises(ValueError),
            ):
                V.revalidate(evidence, source, f.sources, "f" * 40, f.locations)
            unused.assert_not_called()

    def test_T19_partial_or_uncertain_effect_state_never_becomes_not_run(self):
        for consumed in (True, None):
            value = V.failure_receipt(
                S.ExecutionFailure("UNCERTAIN", consumed, "retain")
            )
            self.assertIs(value["authorization_consumed"], consumed)
            self.assertTrue(value["retain_evidence"])
            self.assertFalse(value["automatic_retry_allowed"])
        self.assertIsNone(
            V.failure_receipt(OSError("delivery failed"))["authorization_consumed"]
        )

    def test_T19_cli_delivery_failure_preserves_unknown_consumption(self):
        error_sink = io.BytesIO()
        with (
            patch.object(
                sys,
                "argv",
                [V.SCRIPT, "--inspect", "--implementation-revision", "f" * 40],
            ),
            patch.object(V, "inspect", return_value=self.receipt()),
            patch.object(
                sys,
                "stdout",
                SimpleNamespace(
                    buffer=SimpleNamespace(write=Mock(side_effect=OSError("delivery")))
                ),
            ),
            patch.object(sys, "stderr", SimpleNamespace(buffer=error_sink)),
            self.assertRaises(SystemExit),
        ):
            V.main()
        self.assertIsNone(V.parse(error_sink.getvalue())["authorization_consumed"])

    def test_T20_cli_rejects_old_digest_continue_and_all_effectful_operations(self):
        for extra in (
            ["--run"],
            ["--prepare"],
            ["--publish"],
            ["--confirm-digest", V.CANDIDATE_DIGEST],
            ["--public"],
            ["--continue"],
            ["--output", "/tmp/no"],
        ):
            with (
                patch.object(
                    sys,
                    "argv",
                    [
                        V.SCRIPT,
                        "--inspect",
                        "--implementation-revision",
                        "f" * 40,
                        *extra,
                    ],
                ),
                patch.object(sys, "stderr", io.StringIO()),
                patch.object(V, "inspect") as operation,
                self.subTest(extra=extra),
                self.assertRaises(SystemExit),
            ):
                V.main()
            operation.assert_not_called()

    def test_T21_closed_new_source_requires_all_three_files(self):
        files = {name: {} for name in V.SOURCE_FILES}
        V.closed_source(files)
        for name in V.SOURCE_FILES:
            with self.subTest(name=name), self.assertRaises(ValueError):
                V.closed_source({k: v for k, v in files.items() if k != name})
        with self.assertRaises(ValueError):
            V.closed_source({**files, "scripts/unreviewed.py": {}})
        with (
            patch.object(V, "SOURCE_FILES", (V.SCRIPT, V.POLICY)),
            self.assertRaises(ValueError),
        ):
            V.closed_source(files)

    def test_T22_persisted_mode_and_study_cannot_cross_public_replication(self):
        f = self.f()
        binding, *_ = self.public(f)
        with self.assertRaises(ValueError):
            V.binding_for_mode(
                binding, S.REPLICATION, B.OUTPUT, ROOT / C.REPLICATION_AUTH
            )
        replication = self.replication_binding()
        V.binding_for_mode(
            replication, S.REPLICATION, B.OUTPUT, ROOT / C.REPLICATION_AUTH
        )
        for key, wrong in (
            ("execution_mode", S.PUBLIC),
            ("experiment_id", S.PUBLIC_ID),
            ("authorization_path", str(ROOT / C.PUBLIC_AUTH)),
        ):
            altered = copy.deepcopy(replication)
            altered[key] = wrong
            with self.subTest(key=key), self.assertRaises(ValueError):
                V.binding_for_mode(
                    rehash(altered), S.REPLICATION, B.OUTPUT, ROOT / C.REPLICATION_AUTH
                )

    def test_source_revision_aliases_rejected(self):
        for value in ("HEAD", "main", "f" * 7, "F" * 40, None, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                V.attest(value)

    def test_receipt_rejects_unknown_fields_bool_count_and_false_absence(self):
        mutations = (
            lambda v: v.__setitem__("certificate", {}),
            lambda v: v.__setitem__("original_study_slot_absent_at_inspection", 1),
            lambda v: v["claim_ceiling"].__setitem__("replication_search_calls", False),
            lambda v: v["public_archive_hash_closures"][0].__setitem__(
                "cell_count", 1024.0
            ),
            lambda v: v["location_correspondence"].__setitem__(
                "physical_disk_identity_proven", True
            ),
        )
        for mutate in mutations:
            value = self.receipt()
            mutate(value)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                V.inspection_shape(V.canonical(rehash(value)))

    def test_actual_operation_wiring_uses_no_replay_or_effects_synthetic_only(self):
        # Deliberately mocked observation plumbing, not a real inspection receipt.
        f = self.f()
        template = self.receipt()
        source = template["source"]
        evidence = SimpleNamespace(
            values=f.values, anchors=template["reviewed_anchors"], anchor=Mock()
        )
        forbidden = []
        with ExitStack() as stack:
            for module, name in (
                (B, "admit"),
                (B, "reconstruct"),
                (C, "admit"),
                (C, "run"),
                (C, "analyze"),
                (C, "qualified_public"),
                (S, "consume"),
                (S, "publish"),
                (C.F, "consume"),
                (R, "environment"),
                (R, "record"),
                (R, "reduce_rows"),
                (B.M, "_cohort"),
                (S, "inspect_claim"),
                (C.F, "inspect"),
            ):
                forbidden.append(
                    stack.enter_context(
                        patch.object(
                            module,
                            name,
                            side_effect=AssertionError("forbidden " + name),
                        )
                    )
                )
            for module, name, value in (
                (V, "_guard", None),
                (C, "unused", None),
                (V, "attest", source),
                (V, "historical_sources", f.sources),
                (V, "Evidence", evidence),
                (V.core, "git_head", "f" * 40),
                (V.core, "require_ancestor", None),
                (V, "inspect_metadata", template["sealed_metadata"]),
                (V, "current_locations", f.locations),
                (V, "revalidate", None),
            ):
                stack.enter_context(patch.object(module, name, return_value=value))
            rows = self.receipt()["public_archive_hash_closures"]
            stack.enter_context(patch.object(V, "inspect_public", side_effect=rows))
            result = V.inspect("f" * 40)
            self.assertEqual(result["claim_ceiling"], V.claim_ceiling())
            self.assertEqual(evidence.anchor.call_count, 16)
            self.assertEqual(C.unused.call_count, 1)
            V.revalidate.assert_called_once()
            for operation in forbidden:
                operation.assert_not_called()

    def test_outside_checkout_static_cli_no_authority(self):
        process = subprocess.run(
            [sys.executable, "-P", "-B", str(ROOT / V.SCRIPT), "--self-test"],
            cwd=Path.home(),
            env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
            capture_output=True,
            check=True,
        )
        value = V.parse(process.stdout)
        self.assertEqual(value["status"], "STATIC_SELF_TEST_ONLY")
        self.assertEqual(value["claim_ceiling"], V.claim_ceiling())


if __name__ == "__main__":
    unittest.main()
