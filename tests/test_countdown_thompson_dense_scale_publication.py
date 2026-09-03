"""Publication-only plumbing: no development tasks, searches or provider calls."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from qmc_bmgs.experiments import countdown_thompson_dense_scale_core as core
from qmc_bmgs.experiments import countdown_thompson_dense_scale_publication as pub
from qmc_bmgs.substrate.budget import TRACK_A_WORK_AXES


def _fixture_inputs(output: Path):
    frozen = core.public_fixture_inputs()
    binding = pub.capture_dense_parent_binding(output)
    qualification = core.anchor_qualification()  # fixed public receipt; no traces run
    runtime = core.with_digest({"schema_version": "publication-unit-runtime/v1"})
    build = core.with_digest(
        {"schema_version": "publication-unit-build/v1", "search_build_digest": "b" * 64}
    )
    auth = {name: "a" * 64 for name in pub._AUTH_FIELDS}
    payload = frozen.payload
    auth.update(
        {
            "schema_version": core.FIXTURE_AUTHORIZATION_SCHEMA_VERSION,
            "authorization_scope": core.FIXTURE_AUTHORIZATION_SCOPE,
            "bundle_id": core.FIXTURE_BUNDLE_ID,
            "cell_count": 384,
            "artifact_id": "fixture-artifact",
            "artifact_layout": pub.ARTIFACT_LAYOUT,
            "publication_backend": pub.PUBLICATION_BACKEND,
            "claim_boundary": core.FIXTURE_CLAIM_BOUNDARY,
            "dense_scale_seal_digest": None,
            "preregistration_file_sha256": None,
            "fixture_design_digest": frozen.design_digest,
            "schedule_digest": frozen.schedule_digest,
            "output_path": str(output),
            "output_path_digest": pub.mechanics.RegularFileLayoutV2.from_output_path(
                output
            ).output_path_digest,
            "output_parent_binding": binding,
            "output_parent_binding_digest": binding["deterministic_digest"],
            "publication_environment_requirements": {},
            "requires_explicit_digest_confirmation": True,
            "anchor_qualification": qualification,
            "anchor_qualification_digest": qualification["deterministic_digest"],
            "runtime_qualification": runtime,
            "runtime_qualification_digest": runtime["deterministic_digest"],
            "runner_build_attestation": build,
            "analysis_manifest_digest": payload["analysis"]["deterministic_digest"],
            "method_manifest_digest": payload["methods"]["deterministic_digest"],
            "budget_manifest_digest": payload["budget"]["deterministic_digest"],
            "proposal_manifest_digest": payload["proposal"]["deterministic_digest"],
            "runtime_binding_digest": payload["runtime_binding"][
                "deterministic_digest"
            ],
        }
    )
    auth.pop("deterministic_digest")
    auth = core.with_digest(auth)
    arguments = dict(
        authorization_raw=core.canonical_bytes(auth),
        schedule_raw=core.canonical_bytes(list(frozen.schedule)),
        task_sources_raw=core.canonical_bytes(frozen.task_sources),
        reviewed_authorization_revision="c" * 40,
        execution_head_revision="c" * 40,
    )
    return frozen, pub.make_dense_fixture_publication_inputs(**arguments), arguments


def _records(frozen, context):
    """Structurally closed dummy rows, not canonical search/replay evidence."""
    profile = frozen.budget.to_dict()
    primary = profile["primary_axis"]
    remaining = dict(profile["budget"])
    evidence = {
        "blocked_axes": [],
        "budget_valid": True,
        "non_primary_headroom": {
            axis: remaining[axis] for axis in TRACK_A_WORK_AXES if axis != primary
        },
        "primary_axis": primary,
        "primary_headroom": remaining[primary],
        "profile_spec": profile,
        "remaining": remaining,
        "stop_reason": "publication_unit_fixture_only",
        "usage": {axis: 0 for axis in TRACK_A_WORK_AXES},
    }
    result = []
    sources = frozen.task_sources
    for row in frozen.schedule:
        trace = {"publication_unit_fixture_only": True, "cell_id": row["cell_id"]}
        trace_raw = core.canonical_bytes(trace)
        trace_digest = core.sha256_bytes(trace_raw)
        result.append(
            core.with_digest(
                {
                    "schema_version": core.FIXTURE_RECORD_SCHEMA_VERSION,
                    "cell_id": row["cell_id"],
                    "cell_key": row["cell_key"],
                    "source_multiset_fingerprint": sources[
                        row["cell_key"]["task_fingerprint"]
                    ],
                    "run_binding_digest": context.run_binding_digest,
                    "search_record": trace,
                    "search_run_identity_digest": "e" * 64,
                    "search_trace_byte_count": len(trace_raw),
                    "search_trace_sha256": trace_digest,
                    "budget_evidence": evidence,
                    "provider_calls": 0,
                    "replay": {
                        "stage1_generative": "PASS",
                        "stage2_byte_identical": "PASS",
                        "replayed_sha256": trace_digest,
                    },
                }
            )
        )
    return result


def _redigest(record):
    record.pop("deterministic_digest", None)
    record.update(core.with_digest(record))


class DenseScalePublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dense-publication-unit-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.output = self.root / "fixture.commit.json"
        self.frozen, self.inputs, self.arguments = _fixture_inputs(self.output)
        self.layout = pub.mechanics.RegularFileLayoutV2.from_output_path(self.output)

    def publish(self, *, action=None, pre_started=None, pre_commit=None, hook=None):
        return pub.publish_dense_scale_fixture_v2r3(
            self.output,
            inputs=self.inputs,
            action=action
            or (
                lambda context: pub.DensePublicationBatchV2R3(
                    _records(self.frozen, context)
                )
            ),
            pre_started_check=pre_started or (lambda: None),
            pre_commit_check=pre_commit or (lambda: None),
            _event_hook=hook,
        )

    def verify(self):
        return pub.verify_dense_scale_fixture_v2r3(self.output, inputs=self.inputs)

    def test_384_commit_and_independent_immutable_byte_verification(self):
        calls = []

        def action(context):
            self.assertTrue((self.root / self.layout.started_name).exists())
            binding = context.run_binding
            self.assertEqual(set(binding), pub.RUN_BINDING_FIELDS)
            binding["execution_mode"] = "tampered returned copy"
            self.assertEqual(
                context.run_binding["execution_mode"], core.FIXTURE_EXECUTION_MODE
            )
            calls.append("action")
            return pub.DensePublicationBatchV2R3(_records(self.frozen, context))

        result = self.publish(
            action=action,
            pre_started=lambda: calls.append("pre"),
            pre_commit=lambda: calls.append("commit"),
        )
        self.assertEqual(calls, ["pre", "action", "commit"])
        self.assertEqual(result["status"], "COMMITTED")
        verified = self.verify()
        self.assertEqual(len(verified.records), 384)
        self.assertEqual(set(verified.run_manifest), pub.RUN_MANIFEST_FIELDS)
        self.assertEqual(verified.run_manifest_digest, result["run_manifest_digest"])
        self.assertEqual(
            verified.records[0]["run_binding_digest"],
            verified.run_manifest["run_binding_digest"],
        )
        modified = verified.records[0]
        modified["provider_calls"] = 1
        self.assertEqual(verified.records[0]["provider_calls"], 0)
        self.assertEqual(
            verified.payload_records_jsonl_bytes,
            b"".join(core.canonical_bytes(r) for r in verified.records),
        )

    def test_domain_crossings_rejected_before_any_output_access(self):
        with patch.object(
            pub.mechanics,
            "_open_bound_parent",
            side_effect=AssertionError("output opened"),
        ):
            with self.assertRaises(pub.DensePublicationNotRunError):
                pub.publish_dense_scale_v2r3(
                    self.output,
                    inputs=self.inputs,
                    action=lambda _: None,
                    pre_started_check=lambda: None,
                    pre_commit_check=lambda: None,
                )
            with self.assertRaises(pub.DensePublicationNotRunError):
                pub.verify_dense_scale_v2r3(self.output, inputs=self.inputs)
            with self.assertRaises(pub.DensePublicationNotRunError):
                pub.make_dense_publication_inputs(**self.arguments)
        self.assertFalse(any(self.root.iterdir()))

    def test_legacy_and_unknown_authorizations_refused_before_output(self):
        for schema in (
            "qmc-bmgs-countdown-thompson-diagnostic-execution-authorization/v2",
            "qmc-bmgs-countdown-track-a-canary-execution-authorization/v1",
            "unknown",
        ):
            auth = self.inputs.authorization
            auth["schema_version"] = schema
            _redigest(auth)
            with patch.object(
                pub.mechanics,
                "_open_bound_parent",
                side_effect=AssertionError("opened"),
            ):
                with self.assertRaises(pub.DensePublicationNotRunError):
                    pub.make_dense_fixture_publication_inputs(
                        **{
                            **self.arguments,
                            "authorization_raw": core.canonical_bytes(auth),
                        }
                    )

    def test_authorization_unknown_field_and_numeric_coercion_refused(self):
        for field, value in (
            ("extra", 1),
            ("cell_count", 384.0),
            ("cell_count", True),
            ("requires_explicit_digest_confirmation", 1),
        ):
            auth = self.inputs.authorization
            auth[field] = value
            _redigest(auth)
            with self.assertRaises(pub.DensePublicationNotRunError):
                pub.make_dense_fixture_publication_inputs(
                    **{
                        **self.arguments,
                        "authorization_raw": core.canonical_bytes(auth),
                    }
                )

    def test_fixture_source_epoch_and_fixed_design_are_not_overridable(self):
        with self.assertRaises(pub.DensePublicationNotRunError):
            pub.make_dense_fixture_publication_inputs(
                **{**self.arguments, "reviewed_authorization_revision": "d" * 40}
            )
        auth = self.inputs.authorization
        auth["fixture_design_digest"] = "d" * 64
        _redigest(auth)
        with self.assertRaises(pub.DensePublicationNotRunError):
            pub.make_dense_fixture_publication_inputs(
                **{**self.arguments, "authorization_raw": core.canonical_bytes(auth)}
            )

    def test_input_bytes_and_returned_views_are_immutable_snapshots(self):
        self.inputs.authorization["output_path"] = "/changed"
        self.inputs.schedule[0]["cell_key"]["bundle_id"] = "changed"
        self.assertEqual(self.inputs.authorization["output_path"], str(self.output))
        self.assertEqual(
            self.inputs.schedule[0]["cell_key"]["bundle_id"], core.FIXTURE_BUNDLE_ID
        )
        with self.assertRaises(pub.DensePublicationNotRunError):
            pub.make_dense_fixture_publication_inputs(
                **{
                    **self.arguments,
                    "schedule_raw": bytearray(self.arguments["schedule_raw"]),
                }
            )

    def test_spent_not_run_never_calls_action_or_allows_retry(self):
        def fail():
            raise RuntimeError("public qualification changed")

        def action(_):
            self.fail("action executed")

        with self.assertRaises(pub.DensePublicationNotRunError) as caught:
            self.publish(action=action, pre_started=fail)
        self.assertTrue(caught.exception.authorization_consumed)
        self.assertFalse(caught.exception.retry_permitted)
        observed = pub.inspect_dense_scale_fixture_v2r3(self.output, inputs=self.inputs)
        self.assertEqual(
            observed,
            {
                "status": "NOT_RUN",
                "authorization_consumed": True,
                "retry_permitted": False,
            },
        )
        with self.assertRaises(pub.DensePublicationAmbiguousError):
            self.publish(action=action)
        self.assertFalse((self.root / self.layout.started_name).exists())

    def test_post_started_action_errors_are_invalid_even_status_impersonation(self):
        for exception in (
            RuntimeError,
            pub.DensePublicationNotRunError,
            pub.DensePublicationAmbiguousError,
        ):
            with (
                self.subTest(exception=exception),
                tempfile.TemporaryDirectory(dir=self.root) as temp,
            ):
                output = Path(temp) / "fixture.json"
                _, inputs, _ = _fixture_inputs(output)

                def fail(_):
                    raise exception("caller-controlled failure")

                with self.assertRaises(pub.DensePublicationInvalidError):
                    pub.publish_dense_scale_fixture_v2r3(
                        output,
                        inputs=inputs,
                        action=fail,
                        pre_started_check=lambda: None,
                        pre_commit_check=lambda: None,
                    )
                self.assertEqual(
                    pub.inspect_dense_scale_fixture_v2r3(output, inputs=inputs)[
                        "status"
                    ],
                    "INVALID",
                )

    def test_precommit_failure_spends_authority_without_commit(self):
        def fail():
            raise RuntimeError("source closure changed before final commit")

        with self.assertRaises(pub.DensePublicationInvalidError):
            self.publish(pre_commit=fail)
        self.assertFalse(self.output.exists())
        self.assertTrue((self.root / self.layout.ready_name).exists())
        self.assertEqual(
            pub.inspect_dense_scale_fixture_v2r3(self.output, inputs=self.inputs)[
                "status"
            ],
            "INVALID",
        )

    def test_required_callbacks_cannot_be_omitted(self):
        with self.assertRaises(pub.DensePublicationNotRunError):
            pub.publish_dense_scale_fixture_v2r3(
                self.output,
                inputs=self.inputs,
                action=lambda _: None,
                pre_started_check=None,
                pre_commit_check=lambda: None,
            )
        self.assertFalse(any(self.root.iterdir()))

    def test_missing_extra_duplicate_reordered_wrong_domain_records_invalidate(self):
        mutations = {
            "missing": lambda records: records.pop(),
            "extra": lambda records: records.append(records[0]),
            "duplicate": lambda records: records.__setitem__(1, records[0]),
            "reordered": lambda records: records.reverse(),
            "domain": lambda records: records[0].__setitem__(
                "schema_version", core.RECORD_SCHEMA_VERSION
            ),
            "v2": lambda records: records[0]["cell_key"].__setitem__(
                "method_label", "thompson_dimnorm_iid_v2"
            ),
            "provider": lambda records: records[0].__setitem__("provider_calls", 1),
            "trace": lambda records: records[0].__setitem__(
                "search_trace_sha256", "f" * 64
            ),
            "replay": lambda records: records[0]["replay"].__setitem__(
                "stage2_byte_identical", "FAIL"
            ),
            "nonprimary": lambda records: records[0]["budget_evidence"].__setitem__(
                "blocked_axes", ["transitions"]
            ),
        }
        for name, mutate in mutations.items():
            with (
                self.subTest(name=name),
                tempfile.TemporaryDirectory(dir=self.root) as temp,
            ):
                output = Path(temp) / "fixture.json"
                frozen, inputs, _ = _fixture_inputs(output)

                def action(context):
                    records = _records(frozen, context)
                    mutate(records)
                    for record in records:
                        _redigest(record)
                    return pub.DensePublicationBatchV2R3(records)

                with self.assertRaises(pub.DensePublicationInvalidError):
                    pub.publish_dense_scale_fixture_v2r3(
                        output,
                        inputs=inputs,
                        action=action,
                        pre_started_check=lambda: None,
                        pre_commit_check=lambda: None,
                    )
                self.assertFalse(output.exists())

    def test_all_foreign_reserved_entries_are_ambiguous_and_retained(self):
        for field in self.layout.names:
            with (
                self.subTest(field=field),
                tempfile.TemporaryDirectory(dir=self.root) as temp,
            ):
                output = Path(temp) / "fixture.json"
                _, inputs, _ = _fixture_inputs(output)
                layout = pub.mechanics.RegularFileLayoutV2.from_output_path(output)
                foreign = output.parent / layout.names[field]
                foreign.write_bytes(b"foreign bytes")
                with self.assertRaises(pub.DensePublicationAmbiguousError):
                    pub.publish_dense_scale_fixture_v2r3(
                        output,
                        inputs=inputs,
                        action=lambda _: self.fail("action"),
                        pre_started_check=lambda: None,
                        pre_commit_check=lambda: None,
                    )
                self.assertEqual(foreign.read_bytes(), b"foreign bytes")
                self.assertEqual(list(output.parent.iterdir()), [foreign])

    def test_foreign_records_created_after_started_are_ambiguous_not_invalid(self):
        def hook(event, _details):
            if event == "after_started":
                (self.root / self.layout.records_name).write_bytes(b"foreign")

        with self.assertRaises(pub.DensePublicationAmbiguousError):
            self.publish(hook=hook)
        self.assertFalse((self.root / self.layout.invalid_name).exists())
        self.assertEqual(
            (self.root / self.layout.records_name).read_bytes(), b"foreign"
        )

    def test_foreign_commit_created_at_precommit_is_ambiguous(self):
        def callback():
            self.output.write_bytes(b"foreign commit")

        with self.assertRaises(pub.DensePublicationAmbiguousError):
            self.publish(pre_commit=callback)
        self.assertEqual(self.output.read_bytes(), b"foreign commit")
        self.assertFalse((self.root / self.layout.invalid_name).exists())

    def test_unknown_absence_is_ambiguous(self):
        original = pub.mechanics.os.stat

        def denied(path, *args, **kwargs):
            if path == self.layout.records_name:
                raise PermissionError("unobservable namespace")
            return original(path, *args, **kwargs)

        with (
            patch.object(pub.mechanics.os, "stat", side_effect=denied),
            self.assertRaises(pub.DensePublicationAmbiguousError),
        ):
            # Freeze occurred before mocking os.stat capability membership.
            parent = pub.mechanics._open_bound_parent(
                self.root, self.inputs.authorization["output_parent_binding"]
            )
            try:
                pub.mechanics._assert_name_absent(parent, self.layout.records_name)
            except pub.mechanics.RegularFilePublicationV2AmbiguousError as error:
                raise pub.DensePublicationAmbiguousError(str(error)) from error
            finally:
                parent.close()

    def test_two_stage_reader_rejects_canonical_and_same_byte_generation_mutation(self):
        self.publish()
        original = pub.mechanics._forward_sync_exact_regular_file_at
        mutated = False

        def mutate(parent, name):
            nonlocal mutated
            original(parent, name)
            if name == self.layout.records_name and not mutated:
                mutated = True
                path = self.root / name
                path.write_bytes(path.read_bytes())

        with patch.object(
            pub.mechanics, "_forward_sync_exact_regular_file_at", side_effect=mutate
        ):
            with self.assertRaises(pub.DensePublicationAmbiguousError):
                self.verify()

    def test_record_tampering_after_commit_cannot_be_verified(self):
        self.publish()
        path = self.root / self.layout.records_name
        raw = path.read_bytes()
        path.write_bytes(raw.replace(b'"provider_calls":0', b'"provider_calls":1', 1))
        with self.assertRaises(pub.DensePublicationAmbiguousError):
            self.verify()

    def test_execution_head_hint_reads_control_only_and_revalidates_identity(self):
        self.publish()
        original = pub.mechanics._read_bounded_regular_file_at
        opened = []

        def control_only(parent, name, **kwargs):
            opened.append(name)
            self.assertEqual(name, self.layout.manifest_name)
            return original(parent, name, **kwargs)

        auth = self.inputs.authorization
        with patch.object(
            pub.mechanics, "_read_bounded_regular_file_at", side_effect=control_only
        ):
            hint = pub.read_dense_scale_fixture_execution_head_hint(
                self.output,
                authorization_digest=auth["deterministic_digest"],
                expected_parent_binding=auth["output_parent_binding"],
            )
            self.assertEqual(hint.execution_head_revision, "c" * 40)
            hint.revalidate()
        self.assertGreaterEqual(len(opened), 2)
        path = self.root / self.layout.manifest_name
        path.write_bytes(path.read_bytes())
        with self.assertRaises(pub.DensePublicationAmbiguousError):
            hint.revalidate()

    def test_execution_head_hint_domain_and_external_authorization_are_required(self):
        self.publish()
        auth = self.inputs.authorization
        with self.assertRaises(pub.DensePublicationAmbiguousError):
            pub.read_dense_scale_execution_head_hint(
                self.output,
                authorization_digest=auth["deterministic_digest"],
                expected_parent_binding=auth["output_parent_binding"],
            )
        with self.assertRaises(pub.DensePublicationAmbiguousError):
            pub.read_dense_scale_fixture_execution_head_hint(
                self.output,
                authorization_digest="f" * 64,
                expected_parent_binding=auth["output_parent_binding"],
            )

    def test_foreign_symlink_and_fifo_are_not_opened_or_removed(self):
        for kind in ("symlink", "fifo"):
            with (
                self.subTest(kind=kind),
                tempfile.TemporaryDirectory(dir=self.root) as temp,
            ):
                output = Path(temp) / "fixture.json"
                _, inputs, _ = _fixture_inputs(output)
                layout = pub.mechanics.RegularFileLayoutV2.from_output_path(output)
                foreign = output.parent / layout.records_name
                if kind == "symlink":
                    foreign.symlink_to("missing-foreign-target")
                else:
                    os.mkfifo(foreign, 0o600)
                before = foreign.lstat()
                with self.assertRaises(pub.DensePublicationAmbiguousError):
                    pub.publish_dense_scale_fixture_v2r3(
                        output,
                        inputs=inputs,
                        action=lambda _: self.fail("action"),
                        pre_started_check=lambda: None,
                        pre_commit_check=lambda: None,
                    )
                self.assertEqual(foreign.lstat().st_ino, before.st_ino)

    def test_post_commit_hook_mutation_is_ambiguous_and_never_invalid(self):
        def hook(event, _details):
            if event == "after_commit":
                self.output.write_bytes(self.output.read_bytes())
                raise RuntimeError("observer interrupted after mutation")

        with self.assertRaises(pub.DensePublicationAmbiguousError):
            self.publish(hook=hook)
        self.assertFalse((self.root / self.layout.invalid_name).exists())

    def test_record_limit_rejects_before_serializing_later_records(self):
        with patch.object(pub, "MAX_RECORDS_BYTES", 128):
            with self.assertRaises(pub.DensePublicationInvalidError):
                self.publish()
        self.assertFalse(self.output.exists())

    def test_parent_binding_is_never_regenerated_from_live_state(self):
        changed = self.inputs.authorization
        changed["output_parent_binding_digest"] = "f" * 64
        _redigest(changed)
        with patch.object(
            pub.mechanics,
            "build_synthetic_parent_binding_v2",
            side_effect=AssertionError("regenerated"),
        ):
            with self.assertRaises(pub.DensePublicationNotRunError):
                pub.make_dense_fixture_publication_inputs(
                    **{
                        **self.arguments,
                        "authorization_raw": core.canonical_bytes(changed),
                    }
                )

    def test_callback_snapshot_collection_subclasses_rejected(self):
        class BadList(list):
            def __getitem__(self, key):
                raise AssertionError("collection magic executed")

        with self.assertRaises(pub.DensePublicationInvalidError):
            self.publish(action=lambda _: pub.DensePublicationBatchV2R3(BadList()))

    def _summary(self):
        summary = {key: None for key in pub.FIXTURE_SUMMARY_FIELDS}
        summary.update(
            {
                "schema_version": pub.FIXTURE_SUMMARY_SCHEMA_VERSION,
                "bundle_id": core.FIXTURE_BUNDLE_ID,
                "execution_mode": core.FIXTURE_EXECUTION_MODE,
                "cell_count": 384,
                "fixture_status": "FIXTURE_REPLAY_PASS",
                "fixture_reduction_digest": "a" * 64,
            }
        )
        summary.pop("deterministic_digest")
        return core.with_digest(summary)

    def test_summary_is_closed_no_overwrite_and_allows_same_raw_parent(self):
        self.publish()
        initial = self.verify()
        protected_temp = tempfile.TemporaryDirectory(prefix="dense-protected-source-")
        self.addCleanup(protected_temp.cleanup)
        protected = Path(protected_temp.name).resolve()
        output = self.root / "summary.json"
        calls = []

        def check():
            current = self.verify()
            self.assertEqual(initial.authority_generation, current.authority_generation)
            self.assertEqual(initial.records_jsonl_bytes, current.records_jsonl_bytes)
            calls.append("checked")

        summary = self._summary()
        pub.publish_dense_scale_fixture_summary(
            output,
            core.canonical_bytes(summary),
            artifact_path=self.output,
            protected_roots=(protected,),
            pre_publication_check=check,
            post_durability_check=check,
        )
        self.assertGreaterEqual(len(calls), 2)
        self.assertEqual(output.read_bytes(), core.canonical_bytes(summary))
        with self.assertRaises(pub.DensePublicationError):
            pub.publish_dense_scale_fixture_summary(
                output,
                core.canonical_bytes(summary),
                artifact_path=self.output,
                protected_roots=(protected,),
                pre_publication_check=check,
                post_durability_check=check,
            )
        self.assertEqual(output.read_bytes(), core.canonical_bytes(summary))

    def test_summary_domain_and_raw_namespace_collision_fail_before_callbacks(self):
        protected = self.root / "protected-source"
        protected.mkdir()
        summary = self._summary()
        for output in (self.output, self.root / self.layout.records_name):
            with self.assertRaises(pub.DensePublicationError):
                pub.publish_dense_scale_fixture_summary(
                    output,
                    core.canonical_bytes(summary),
                    artifact_path=self.output,
                    protected_roots=(protected,),
                    pre_publication_check=lambda: self.fail("callback"),
                    post_durability_check=lambda: None,
                )
        summary["decision"] = "STOP_REPAIR_NO_LOCKED_128_RUN"
        _redigest(summary)
        with self.assertRaises(pub.DensePublicationError):
            pub.publish_dense_scale_fixture_summary(
                self.root / "summary.json",
                core.canonical_bytes(summary),
                artifact_path=self.output,
                protected_roots=(protected,),
                pre_publication_check=lambda: self.fail("callback"),
                post_durability_check=lambda: None,
            )


if __name__ == "__main__":
    unittest.main()
