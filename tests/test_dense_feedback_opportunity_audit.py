"""Synthetic-only tests: never open the retained experiment or execute search."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts/audit_dense_feedback_opportunity.py"
)
SPEC = importlib.util.spec_from_file_location(
    "dense_feedback_opportunity_audit_tested", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
AUDIT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = AUDIT
with patch(
    "subprocess.check_output",
    side_effect=AssertionError("import must not run subprocesses"),
):
    SPEC.loader.exec_module(AUDIT)

AXES = (
    "proposal_state_evaluations",
    "proposal_action_scores",
    "legal_action_scores",
    "generated_perturbation_coordinates",
    "edge_selections",
    "transitions",
    "verifier_calls",
)
ACTIONS = [
    {"left": 1, "operator": "+", "right": 2},
    {"left": 1, "operator": "*", "right": 2},
]


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _vector(**values: int) -> dict[str, int]:
    return {axis: values.get(axis, 0) for axis in AXES}


def _resign(trace: dict, *, renumber: bool = False) -> dict:
    """Repair only hashes, preserving intentional semantic/receipt corruption."""
    previous = "0" * 64
    for index, event in enumerate(trace["events"]):
        if renumber:
            event["index"] = index
        event["previous_event_digest"] = previous
        core = {key: value for key, value in event.items() if key != "event_digest"}
        event["event_digest"] = _digest(core)
        previous = event["event_digest"]
    trace["event_count"] = len(trace["events"])
    trace["final_event_digest"] = previous
    trace["deterministic_digest"] = _digest(
        {key: value for key, value in trace.items() if key != "deterministic_digest"}
    )
    return trace


def _close_receipts(trace: dict) -> dict:
    """Close synthetic accounting without interpreting search or terminal logic."""
    usage, count = _vector(), 0
    for event in trace["events"]:
        charge = event["charge"]
        if charge is not None:
            usage = {axis: usage[axis] + charge["delta"][axis] for axis in AXES}
            charge.update(charge_index=count, usage_after=dict(usage))
            count += 1
    ledger = trace["ledger_snapshot"]
    remaining = {axis: ledger["limits"][axis] - usage[axis] for axis in AXES}
    ledger.update(
        usage=usage,
        remaining=remaining,
        charge_count=count,
        exhausted_axes=[axis for axis in AXES if remaining[axis] == 0],
    )
    stop = trace["events"][-1]["payload"]["summary"]
    stop.update(
        ledger_usage=dict(usage),
        terminal_count=sum(
            event["kind"] == "terminal_verified" for event in trace["events"]
        ),
        stop_attempted_charge=_vector(
            legal_action_scores=remaining["legal_action_scores"] + 1
        ),
    )
    return _resign(trace, renumber=True)


def _trace(
    *,
    scale: int = 0,
    prefix_error: int = 9,
    suffix_error: int = 12,
    complete_suffix: bool = True,
    trajectory_ids: tuple[int, ...] = (0, 1),
    divergent: bool = True,
) -> dict:
    """Tiny structural fixture, not a generated Countdown search result."""
    events = []

    def append(kind: str, payload: dict, delta: dict | None = None) -> None:
        events.append(
            {
                "index": len(events),
                "kind": kind,
                "payload": payload,
                "charge": None if delta is None else {"delta": delta},
            }
        )

    final_position = len(trajectory_ids) - 1
    for position, trajectory in enumerate(trajectory_ids):
        for depth in range(2 if position < final_position or complete_suffix else 1):
            chosen = int(
                position == final_position and depth == 0 and scale > 0 and divergent
            )
            append("proposal_materialized", {"proposal": {"state": [1, 2, 3]}})
            append(
                "selection_committed",
                {
                    "trajectory_index": trajectory,
                    "depth": depth,
                    "state": [1, 2, 3] if depth == 0 else [2, 3],
                    "child_state": [2, 3] if depth == 0 else [5],
                    "action_index": chosen,
                    "action": ACTIONS[chosen],
                    "selection_values": [1.0, 2.0] if chosen else [2.0, 1.0],
                },
                _vector(
                    proposal_state_evaluations=1,
                    proposal_action_scores=2,
                    legal_action_scores=2,
                    generated_perturbation_coordinates=2,
                    edge_selections=1,
                    transitions=1,
                ),
            )
        if position == final_position and not complete_suffix:
            break
        error = prefix_error if position < final_position else suffix_error
        append(
            "terminal_verified",
            {
                "trajectory_index": trajectory,
                "observation_index": position,
                "verification": {
                    "final_value": 20 + error,
                    "target": 20,
                    "success": error == 0,
                },
            },
            _vector(verifier_calls=1),
        )
        append(
            "trajectory_backed_up",
            {
                "trajectory_index": trajectory,
                "terminal_value": 1.0
                if error == 0
                else (scale / (scale + error) if scale else 0.0),
            },
        )
    append(
        "search_finished",
        {
            "summary": {
                "stop_reason": "primary_budget_blocked",
                "stop_blocked_axes": ["legal_action_scores"],
                "incomplete_trajectory_count": 1,
            }
        },
    )
    limits = dict.fromkeys(AXES, 100)
    limits["legal_action_scores"] = 4 * len(trajectory_ids)
    return _close_receipts({"events": events, "ledger_snapshot": {"limits": limits}})


def _pair_fixture(**kwargs: object) -> tuple[dict, dict, dict]:
    baseline = AUDIT.scan_trace(_trace(scale=0, **kwargs))
    scaled = AUDIT.scan_trace(_trace(scale=16, **kwargs))
    trajectory_ids = kwargs.get("trajectory_ids", (0, 1))
    last = trajectory_ids[-1]
    left = baseline["selections"][last, 0]["payload"]
    right = scaled["selections"][last, 0]["payload"]
    pair = {
        "task_fingerprint": "synthetic-task",
        "exploration_seed": 7168,
        "positive_scale": 16,
        "baseline_cell_id": "synthetic-baseline",
        "scaled_cell_id": "synthetic-scaled",
        "feedback_informed": True,
        "stop_reason": "recorded_action_divergence",
        "shared_prefix_backup_values": [
            {
                "trajectory_index": trajectory,
                "baseline_applied_value": baseline["backups"][trajectory]["payload"][
                    "terminal_value"
                ],
                "scaled_applied_value": scaled["backups"][trajectory]["payload"][
                    "terminal_value"
                ],
            }
            for trajectory in trajectory_ids[:-1]
        ],
        "first_action_divergence": {
            "trajectory_index": last,
            "depth": 0,
            "state": left["state"],
            "baseline_action_index": left["action_index"],
            "scaled_action_index": right["action_index"],
            "baseline_action": left["action"],
            "scaled_action": right["action"],
            "baseline_scores": left["selection_values"],
            "scaled_scores": right["selection_values"],
        },
    }
    return pair, baseline, scaled


class PureHelperTests(unittest.TestCase):
    def test_axis_contract_and_plain_integer_rejections(self) -> None:
        self.assertEqual(tuple(AUDIT.AXES), AXES)
        self.assertEqual(AUDIT.integer(0), 0)
        for value in (True, False, -1, 1.0, "1", None):
            with self.subTest(value=value), self.assertRaises(AUDIT.AuditError):
                AUDIT.integer(value)

    def test_work_vector_rejects_bool_missing_and_extra_axes(self) -> None:
        for value in (_vector(legal_action_scores=True), {}, {**_vector(), "extra": 0}):
            with self.subTest(value=value), self.assertRaises(AUDIT.AuditError):
                AUDIT.vector(value)

    def test_binary64_rationals_and_nonfinite_rejection(self) -> None:
        self.assertEqual(
            AUDIT.rational(AUDIT.finite(0.5) - AUDIT.finite(0.25)),
            {"numerator": 1, "denominator": 4},
        )
        for value in (True, 1, float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value), self.assertRaises(AUDIT.AuditError):
                AUDIT.finite(value)

    def test_strict_json_requires_canonical_bytes_and_one_newline(self) -> None:
        self.assertEqual(AUDIT.strict_json(b'{"a":1,"b":2}\n'), {"a": 1, "b": 2})
        for raw in (b'{"b":2,"a":1}\n', b'{"a": 1}\n', b'{"a":1}', b'{"a":1}\n\n'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                AUDIT.strict_json(raw)

    def test_parse_json_allows_pretty_but_rejects_duplicate_keys(self) -> None:
        self.assertEqual(AUDIT.parse_json(b'{\n  "a": 1\n}\n'), {"a": 1})
        for raw in (b'{"a":1,"a":2}\n', b'{"outer":{"a":1,"a":2}}\n'):
            for parser in (AUDIT.parse_json, AUDIT.strict_json):
                with (
                    self.subTest(raw=raw, parser=parser.__name__),
                    self.assertRaises(ValueError),
                ):
                    parser(raw)

    def test_json_nonfinite_literals_and_overflow_fail_closed(self) -> None:
        for token in (b"NaN", b"Infinity", b"-Infinity", b"1e999", b"-1e999"):
            for parser in (AUDIT.parse_json, AUDIT.strict_json):
                with (
                    self.subTest(token=token, parser=parser.__name__),
                    self.assertRaises(ValueError),
                ):
                    parser(b'{"value":' + token + b"}\n")

    def test_suffix_categories_and_worse_is_not_cumulative_loss(self) -> None:
        cases = [
            ([9], [], "no_completed_terminal", None),
            ([], [3], "no_prefix_terminal", None),
            ([9], [0], "exact_hit", 9),
            ([9], [3], "improved_nonexact", 6),
            ([9], [9], "tied", 0),
            ([9], [12], "worse", 0),
        ]
        for prefix, suffix, category, gain in cases:
            with self.subTest(prefix=prefix, suffix=suffix):
                result = AUDIT.suffix_outcome(prefix, suffix)
                self.assertEqual(result["category"], category)
                self.assertEqual(result["cumulative_best_gain"], gain)

    def test_opportunity_uses_event_order_not_trajectory_arithmetic(self) -> None:
        view = {
            "terminals": [
                {"event_index": 7, "trajectory_index": 3},
                {"event_index": 23, "trajectory_index": 11},
                {"event_index": 41, "trajectory_index": 19},
            ]
        }
        self.assertEqual(
            AUDIT.opportunity(view, 7),
            {
                "completed_terminal_count": 2,
                "bin": "2+",
                "terminal_trajectory_ids": [11, 19],
            },
        )
        self.assertEqual(AUDIT.opportunity(view, 23)["bin"], "1")
        self.assertEqual(AUDIT.opportunity(view, 41)["bin"], "0")


class SyntheticTraceTests(unittest.TestCase):
    def assert_invalid(self, trace: dict) -> None:
        with self.assertRaises(AUDIT.AuditError):
            AUDIT.scan_trace(trace)

    def test_valid_trace_closes_receipts_and_prepaid_divergence_step(self) -> None:
        view = AUDIT.scan_trace(_trace())
        selected = view["selections"][1, 0]
        self.assertEqual(selected["event_index"], 7)
        self.assertEqual(
            selected["remaining_before_step_charge"]["legal_action_scores"], 4
        )
        self.assertEqual(
            selected["remaining_after_step_charge"]["legal_action_scores"], 2
        )
        self.assertEqual(view["stop"]["completed_terminal_count"], 2)

    def test_noncontiguous_synthetic_trajectory_ids_are_preserved(self) -> None:
        view = AUDIT.scan_trace(_trace(trajectory_ids=(3, 11)))
        self.assertEqual([t["trajectory_index"] for t in view["terminals"]], [3, 11])
        self.assertEqual(
            AUDIT.opportunity(view, view["selections"][11, 0]["event_index"])[
                "terminal_trajectory_ids"
            ],
            [11],
        )

    def test_blocked_atomic_step_can_leave_positive_primary_headroom(self) -> None:
        view = AUDIT.scan_trace(_trace(complete_suffix=False))
        self.assertEqual(view["stop"]["final_remaining"]["legal_action_scores"], 2)
        self.assertEqual(view["stop"]["blocked_axes"], ["legal_action_scores"])
        self.assertNotIn("legal_action_scores", view["stop"]["exhausted_axes"])

    def test_event_index_gap_rejected_even_with_reclosed_hashes(self) -> None:
        trace = _trace()
        trace["events"][3]["index"] += 1
        self.assert_invalid(_resign(trace))

    def test_event_index_bool_rejected(self) -> None:
        trace = _trace()
        trace["events"][1]["index"] = True
        self.assert_invalid(_resign(trace))

    def test_event_digest_tamper_rejected_with_valid_outer_digest(self) -> None:
        trace = _trace()
        trace["events"][1]["payload"]["depth"] = 99
        trace["deterministic_digest"] = _digest(
            {k: v for k, v in trace.items() if k != "deterministic_digest"}
        )
        self.assert_invalid(trace)

    def test_hash_chain_link_tamper_rejected(self) -> None:
        trace = _trace()
        event = trace["events"][1]
        event["previous_event_digest"] = "f" * 64
        event["event_digest"] = _digest(
            {k: v for k, v in event.items() if k != "event_digest"}
        )
        trace["deterministic_digest"] = _digest(
            {k: v for k, v in trace.items() if k != "deterministic_digest"}
        )
        self.assert_invalid(trace)

    def test_charge_arithmetic_and_charge_index_tampering(self) -> None:
        for field, value in (
            ("charge_index", 4),
            ("charge_index", False),
            ("usage_after", _vector()),
        ):
            trace = _trace()
            trace["events"][1]["charge"][field] = value
            with self.subTest(field=field, value=value):
                self.assert_invalid(_resign(trace))

    def test_charge_axis_bool_rejected(self) -> None:
        trace = _trace()
        trace["events"][1]["charge"]["delta"]["edge_selections"] = True
        self.assert_invalid(_resign(trace))

    def test_ledger_remaining_charge_count_and_exhausted_axes_tampering(self) -> None:
        for field, value in (
            ("remaining", _vector()),
            ("charge_count", 99),
            ("exhausted_axes", []),
        ):
            trace = _trace()
            trace["ledger_snapshot"][field] = value
            with self.subTest(field=field):
                self.assert_invalid(_resign(trace))

    def test_terminal_requires_verifier_only_receipt(self) -> None:
        trace = _trace(complete_suffix=False)
        trace["events"][4]["charge"]["delta"] = _vector(proposal_state_evaluations=1)
        self.assert_invalid(_close_receipts(trace))

    def test_backup_must_be_uncharged(self) -> None:
        trace = _trace()
        trace["events"][5]["charge"] = {"delta": _vector(proposal_state_evaluations=1)}
        self.assert_invalid(_close_receipts(trace))

    def test_backup_must_immediately_follow_its_terminal(self) -> None:
        trace = _trace()
        trace["events"].insert(
            5, {"kind": "proposal_materialized", "payload": {}, "charge": None}
        )
        self.assert_invalid(_resign(trace, renumber=True))

    def test_missing_backup_and_duplicate_selection_coordinate_rejected(self) -> None:
        trace = _trace()
        del trace["events"][5]
        self.assert_invalid(_resign(trace, renumber=True))
        trace = _trace()
        trace["events"][3]["payload"]["depth"] = 0
        self.assert_invalid(_resign(trace))

    def test_terminal_arithmetic_and_summary_count_reject_bool(self) -> None:
        trace = _trace(complete_suffix=False)
        trace["events"][4]["payload"]["verification"]["final_value"] = True
        self.assert_invalid(_resign(trace))
        trace = _trace(complete_suffix=False)
        trace["events"][-1]["payload"]["summary"]["terminal_count"] = True
        self.assert_invalid(_resign(trace))


class PairWindowTests(unittest.TestCase):
    def test_all_preceding_backup_support_survives_without_input_mutation(self) -> None:
        pair, baseline, scaled = _pair_fixture(trajectory_ids=(0, 1, 2))
        before = copy.deepcopy((pair, baseline, scaled))
        row = AUDIT.pair_row(pair, baseline, scaled)
        self.assertEqual(len(row["shared_prefix_backup_values"]), 2)
        self.assertEqual(
            row["shared_prefix_backup_values"], pair["shared_prefix_backup_values"]
        )
        self.assertEqual(
            [item["trajectory_index"] for item in row["shared_prefix_backup_values"]],
            [0, 1],
        )
        self.assertEqual(row["first_scale_dependent_backup"]["trajectory_index"], 0)
        self.assertEqual((pair, baseline, scaled), before)

    def test_completed_divergence_is_not_global_incomplete_tail(self) -> None:
        pair, baseline, scaled = _pair_fixture()
        row = AUDIT.pair_row(pair, baseline, scaled)
        window = row["divergence_window"]["scaled"]
        self.assertTrue(window["diverged_trajectory_completed"])
        self.assertEqual(row["scaled_stop"]["global_incomplete_trajectory_count"], 1)
        self.assertEqual(window["opportunity"]["completed_terminal_count"], 1)
        self.assertEqual(window["observed_conversion"]["category"], "worse")
        self.assertEqual(window["observed_conversion"]["cumulative_best_gain"], 0)
        self.assertEqual(row["final_minimum_error_comparison"], "tie")

    def test_incomplete_diverged_trajectory_has_no_imputed_terminal(self) -> None:
        pair, baseline, scaled = _pair_fixture(complete_suffix=False)
        row = AUDIT.pair_row(pair, baseline, scaled)
        window = row["divergence_window"]["scaled"]
        self.assertFalse(window["diverged_trajectory_completed"])
        self.assertEqual(row["opportunity_bin"], "0")
        self.assertEqual(
            window["observed_conversion"]["category"], "no_completed_terminal"
        )
        self.assertIsNone(
            window["observed_conversion"]["observed_suffix_minimum_error"]
        )

    def test_no_divergence_is_not_zero_opportunity_divergence(self) -> None:
        pair, baseline, scaled = _pair_fixture(divergent=False)
        pair.update(
            first_action_divergence=None,
            feedback_informed=False,
            stop_reason="trace_end_without_action_divergence",
        )
        row = AUDIT.pair_row(pair, baseline, scaled)
        self.assertEqual(row["opportunity_bin"], "no_divergence")
        self.assertIsNone(row["divergence_window"])
        self.assertIsNotNone(row["first_scale_dependent_backup"])

    def test_noncontiguous_ids_and_exact_score_margins(self) -> None:
        pair, baseline, scaled = _pair_fixture(trajectory_ids=(3, 11), suffix_error=0)
        row = AUDIT.pair_row(pair, baseline, scaled)
        self.assertEqual(
            row["divergence_window"]["scaled"]["opportunity"][
                "terminal_trajectory_ids"
            ],
            [11],
        )
        self.assertEqual(
            row["divergence_window"]["scaled_selected_over_baseline_action_margin"],
            {"numerator": 1, "denominator": 1},
        )
        self.assertEqual(
            row["divergence_window"]["scaled"]["observed_conversion"]["category"],
            "exact_hit",
        )

    def test_prefix_mismatch_and_frozen_divergence_mismatch_fail_closed(self) -> None:
        pair, baseline, scaled = _pair_fixture()
        scaled["terminals"][0]["error"] += 1
        with self.assertRaises(AUDIT.AuditError):
            AUDIT.pair_row(pair, baseline, scaled)
        pair, baseline, scaled = _pair_fixture()
        pair["first_action_divergence"]["state"] = [99]
        with self.assertRaises(AUDIT.AuditError):
            AUDIT.pair_row(pair, baseline, scaled)


class PairDenominatorTests(unittest.TestCase):
    def test_all_336_rows_preserve_bins_incompleteness_and_error_denominators(
        self,
    ) -> None:
        bins = ("no_divergence", "0", "1", "2+")
        comparisons = ("win", "tie", "loss")
        rows = []
        for scale in AUDIT.SCALES[1:]:
            for index in range(48):
                bucket = bins[index % 4]
                category = (
                    "no_completed_terminal"
                    if bucket == "0"
                    else "improved_nonexact"
                    if bucket == "1"
                    else "worse"
                )
                rows.append(
                    {
                        "positive_scale": scale,
                        "task_fingerprint": f"synthetic-task-{index // 4}",
                        "opportunity_bin": bucket,
                        "final_minimum_error_comparison": comparisons[index % 3],
                        "new_exact_success": index == 6,
                        "lost_exact_success": index == 11,
                        "divergence_window": None
                        if bucket == "no_divergence"
                        else {
                            "scaled": {
                                "diverged_trajectory_completed": bucket != "0",
                                "observed_conversion": {"category": category},
                            }
                        },
                    }
                )
        before = copy.deepcopy(rows)
        result = AUDIT.reduce_pairs(rows)
        self.assertEqual(len(rows), 336)
        self.assertEqual([item["scale"] for item in result], list(AUDIT.SCALES[1:]))
        for item in result:
            with self.subTest(scale=item["scale"]):
                self.assertEqual(item["pair_count"], 48)
                self.assertEqual(item["divergent_pair_count"], 36)
                self.assertEqual(item["divergent_unique_task_count"], 12)
                self.assertEqual(item["incomplete_diverged_trajectory_count"], 12)
                self.assertEqual(item["new_exact_success_count"], 1)
                self.assertEqual(item["lost_exact_success_count"], 1)
                self.assertEqual(item["new_exact_unique_task_count"], 1)
                cross = item["opportunity_by_final_error_comparison"]
                self.assertEqual(
                    [cell["opportunity_bin"] for cell in cross], list(bins)
                )
                self.assertEqual(sum(cell["pair_count"] for cell in cross), 48)
                self.assertEqual([cell["pair_count"] for cell in cross], [12] * 4)
                for comparison in comparisons:
                    self.assertEqual(sum(cell[comparison] for cell in cross), 16)
                for cell in cross:
                    self.assertEqual(
                        sum(cell[key] for key in comparisons), cell["pair_count"]
                    )
                self.assertEqual(
                    sum(item["scaled_suffix_conversion_counts"].values()), 36
                )
        self.assertEqual(rows, before)
        with self.assertRaises(AUDIT.AuditError):
            AUDIT.reduce_pairs(rows[:-1])


class FileBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(prefix="dense-audit-test-")
        self.addCleanup(self.directory.cleanup)
        # macOS /var is a symlink; pass the actual canonical temporary directory.
        self.root = Path(self.directory.name).resolve()

    def fixture(self, name: str = "input.json", raw: bytes = b"{}\n") -> Path:
        path = self.root / name
        path.write_bytes(raw)
        return path

    def test_snapshot_hash_size_and_generation(self) -> None:
        path = self.fixture()
        item = AUDIT.snapshot(
            path, expected_sha=hashlib.sha256(b"{}\n").hexdigest(), expected_size=3
        )
        self.assertEqual(item.raw, b"{}\n")
        item.revalidate()
        for options in ({"expected_size": 4}, {"expected_sha": "0" * 64}):
            with self.subTest(options=options), self.assertRaises(AUDIT.AuditError):
                AUDIT.snapshot(path, **options)

    def test_snapshot_rejects_empty_directory_symlink_and_hardlink(self) -> None:
        empty = self.fixture("empty", b"")
        directory = self.root / "directory"
        directory.mkdir()
        target = self.fixture("target")
        symlink = self.root / "symlink"
        symlink.symlink_to(target)
        hardlink = self.root / "hardlink"
        os.link(target, hardlink)
        for path in (empty, directory, symlink, hardlink, target):
            with (
                self.subTest(path=path.name),
                self.assertRaises((AUDIT.AuditError, OSError)),
            ):
                AUDIT.snapshot(path)

    def test_snapshot_rejects_symlink_ancestor(self) -> None:
        actual = self.root / "actual"
        actual.mkdir()
        (actual / "input").write_bytes(b"x")
        alias = self.root / "alias"
        alias.symlink_to(actual, target_is_directory=True)
        with self.assertRaises((AUDIT.AuditError, OSError)):
            AUDIT.snapshot(alias / "input")

    def test_snapshot_revalidation_rejects_same_bytes_new_inode(self) -> None:
        path = self.fixture()
        item = AUDIT.snapshot(path)
        replacement = self.fixture("replacement")
        os.replace(replacement, path)
        with self.assertRaises(AUDIT.AuditError):
            item.revalidate()

    def test_snapshot_revalidation_rejects_same_size_changed_bytes(self) -> None:
        path = self.fixture()
        item = AUDIT.snapshot(path)
        path.write_bytes(b"[]\n")
        with self.assertRaises(AUDIT.AuditError):
            item.revalidate()

    def test_publish_exclusive_creation_and_readback(self) -> None:
        output = self.root / "audit.json"
        revalidate = Mock()
        AUDIT.publish(output, b'{"status":"synthetic"}\n', revalidate)
        self.assertEqual(output.read_bytes(), b'{"status":"synthetic"}\n')
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
        self.assertEqual(output.stat().st_nlink, 1)
        self.assertEqual(revalidate.call_count, 2)

    def test_publish_never_overwrites_existing_file_or_symlink(self) -> None:
        target = self.fixture("existing", b"keep")
        alias = self.root / "alias"
        alias.symlink_to(target)
        for path in (target, alias):
            with self.subTest(path=path.name), self.assertRaises(OSError):
                AUDIT.publish(path, b"replacement", lambda: None)
            self.assertEqual(target.read_bytes(), b"keep")

    def test_publish_revalidation_race_preserves_newly_occupied_slot(self) -> None:
        output = self.root / "audit.json"

        def occupy() -> None:
            output.write_bytes(b"other owner")

        with self.assertRaises(OSError):
            AUDIT.publish(output, b"our receipt", occupy)
        self.assertEqual(output.read_bytes(), b"other owner")

    def test_publish_postcreation_failure_retains_uncertain_slot(self) -> None:
        output = self.root / "audit.json"
        callback = Mock(side_effect=[None, AUDIT.AuditError("changed input")])
        with self.assertRaises(AUDIT.PublicationUncertain):
            AUDIT.publish(output, b"retained receipt", callback)
        self.assertEqual(output.read_bytes(), b"retained receipt")
        with self.assertRaises(OSError):
            AUDIT.publish(output, b"retry forbidden", lambda: None)
        self.assertEqual(output.read_bytes(), b"retained receipt")

    def test_publish_precreation_failure_leaves_no_output(self) -> None:
        output = self.root / "audit.json"
        with self.assertRaises(AUDIT.AuditError):
            AUDIT.publish(
                output, b"unused", Mock(side_effect=AUDIT.AuditError("invalid input"))
            )
        self.assertFalse(output.exists())

    def test_output_location_rejects_protected_descendants_but_allows_sibling(
        self,
    ) -> None:
        protected = self.root / "protected"
        nested = protected / "nested"
        nested.mkdir(parents=True)
        for output in (protected / "audit.json", nested / "audit.json"):
            with self.subTest(output=output), self.assertRaises(AUDIT.AuditError):
                AUDIT.output_location(output, (protected,))
        AUDIT.output_location(self.root / "allowed.json", (protected,))


if __name__ == "__main__":
    unittest.main()
