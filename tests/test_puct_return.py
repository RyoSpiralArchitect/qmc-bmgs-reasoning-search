"""Previously used, outcome-independent fixtures; no prospective cohort."""

import copy
import math
import unittest
from unittest.mock import patch

from qmc_bmgs.benchmarks.countdown import CountdownTask
from qmc_bmgs.substrate import countdown_search as core
from qmc_bmgs.substrate.budget import TRACK_A_WORK_AXES, TrackAWorkBudget
from qmc_bmgs.substrate.trace import (
    TraceValidationError,
    canonical_trace_bytes,
    sha256_json,
)
from qmc_bmgs_next import puct_return as P


TASK = CountdownTask((1, 1, 1, 1, 1, 1), 6)


def profile(scores=128, **guards):
    caps = dict.fromkeys(TRACK_A_WORK_AXES, 100000)
    caps.update(legal_action_scores=scores, **guards)
    return core.TrackABudgetProfile(
        "puct_return_fixture", "legal_action_scores", TrackAWorkBudget(**caps)
    )


def rehash(record):
    inner = record["search_record"]
    previous = "0" * 64
    for index, e in enumerate(inner["events"]):
        e["index"], e["previous_event_digest"] = index, previous
        e["event_digest"] = sha256_json(
            {k: v for k, v in e.items() if k != "event_digest"}
        )
        previous = e["event_digest"]
    inner["event_count"], inner["final_event_digest"] = len(inner["events"]), previous
    for value in (inner, record):
        value["deterministic_digest"] = sha256_json(
            {k: v for k, v in value.items() if k != "deterministic_digest"}
        )
    return canonical_trace_bytes(record)


class PuctReturnTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = {
            m: P.run_puct_return_cell(
                TASK, spec=P.PuctReturnSpec(m), budget_profile=profile()
            )
            for m in P.METHODS
        }

    def replay(self, payload, method=P.METHODS[0], **overrides):
        kwargs = dict(
            task=TASK,
            spec=P.PuctReturnSpec(method),
            budget_profile=profile(),
            root_seed=0,
            expected_run_identity_digest=self.results[method].record[
                "run_identity_digest"
            ],
        )
        return P.replay_puct_return_cell_bytes(payload, **(kwargs | overrides))

    def test_closed_methods_no_coefficient_or_scale_sweep(self):
        self.assertEqual(P.METHODS, ("puct-dense16", "puct"))
        for bad in ("prior-tilt16", "puct-dense32", "mean-off", True, None):
            with self.assertRaises(ValueError):
                P.PuctReturnSpec(bad)
        with self.assertRaises(TypeError):
            P.PuctReturnSpec("puct-dense16", scale=8)

    def test_nonzero_and_boolean_roots_rejected(self):
        for bad in (True, False, -1, 1, 0.0, "0"):
            with self.assertRaises(ValueError):
                P.run_puct_return_cell(
                    TASK,
                    spec=P.PuctReturnSpec("puct"),
                    budget_profile=profile(),
                    root_seed=bad,
                )

    def test_baseline_inner_bytes_equal_frozen_puct(self):
        expected = core.run_countdown_track_a_search(
            TASK,
            proposal=P.PROPOSAL,
            method=core.TrackAMethodSpec.puct(),
            budget_profile=profile(),
            exploration_seed=0,
        )
        self.assertEqual(
            expected.canonical_bytes,
            canonical_trace_bytes(self.results["puct"].record["search_record"]),
        )

    def test_both_cells_replay_all_bytes(self):
        for m, result in self.results.items():
            self.assertEqual(
                self.replay(result.canonical_bytes, m), result.canonical_bytes
            )

    def test_selector_and_backup_update_functions_are_inherited(self):
        self.assertIs(
            P._DenseSession._selection_values, core._SearchSession._selection_values
        )
        self.assertIs(
            P._DenseSession._preview_backup, core._SearchSession._preview_backup
        )
        self.assertIs(
            P._DenseSession._commit_backup, core._SearchSession._commit_backup
        )
        self.assertIs(P._DenseSession._run_adaptive, core._SearchSession._run_adaptive)
        self.assertIs(
            P._DenseSession._ordinary_step, core._SearchSession._ordinary_step
        )

    def test_no_random_source_or_perturbation_charge(self):
        with patch.object(
            core, "LazyNormalSource", side_effect=AssertionError("RNG forbidden")
        ):
            for m in P.METHODS:
                result = P.run_puct_return_cell(
                    TASK, spec=P.PuctReturnSpec(m), budget_profile=profile()
                )
                self.assertEqual(
                    result.summary["actual_work"]["generated_perturbation_coordinates"],
                    0,
                )
                self.assertFalse(
                    any(
                        e["kind"] == "perturbation_draw"
                        for e in result.record["search_record"]["events"]
                    )
                )

    def test_first_trajectory_and_all_its_charges_match(self):
        def trajectory(result):
            return [
                (e["payload"]["action"], e["charge"])
                for e in result.record["search_record"]["events"]
                if e["kind"] == "selection_committed"
                and e["payload"]["trajectory_index"] == 0
            ]

        self.assertEqual(
            trajectory(self.results[P.METHODS[0]]), trajectory(self.results["puct"])
        )

    def test_terminal_return_evidence_and_welford_updates(self):
        # Same historical all-ones source, deliberately unreachable target:
        # this contract fixture must exercise non-exact dense values.
        task = CountdownTask((1, 1, 1, 1, 1, 1), 999)
        record = P.run_puct_return_cell(
            task, spec=P.PuctReturnSpec(P.METHODS[0]), budget_profile=profile()
        ).record["search_record"]
        terminal = None
        nonexact = 0
        for e in record["events"]:
            p = e["payload"]
            if e["kind"] == "terminal_verified":
                terminal = p["verification"]
            elif e["kind"] == "trajectory_backed_up":
                error = abs(terminal["final_value"] - task.target)
                value = 16 / (16 + error)
                nonexact += error != 0
                self.assertEqual(p["terminal_value"], value)
                self.assertEqual(p["terminal_absolute_error"], error)
                self.assertEqual(p["terminal_value_scale"], 16)
                for u in p["updates"]:
                    a, b = u["before"], u["after"]
                    n = a["visits"] + 1
                    mean = a["mean"] + (value - a["mean"]) / n
                    self.assertEqual(
                        b,
                        dict(
                            visits=n,
                            mean=mean,
                            m2=a["m2"] + (value - a["mean"]) * (value - mean),
                        ),
                    )
        self.assertGreater(nonexact, 0)

    def test_binary_q_zero_until_first_success_implies_same_mean_off_prefix(self):
        class MeanOff(core._SearchSession):
            def _selection_values(self, node, normals, *, trajectory_index):
                scale = math.sqrt(1.0 + sum(p.visits for p in node.posteriors))
                return [
                    0.0 + 1.0 * math.exp(lp) * scale / (1.0 + p.visits)
                    for p, lp in zip(node.posteriors, node.row.prior_logp)
                ]

        def prefix(result):
            selected = []
            for e in result.record["events"]:
                p = e["payload"]
                if e["kind"] == "selection_committed":
                    selected.append((p["state"], p["action"], e["charge"]))
                if e["kind"] == "terminal_verified" and p["verification"]["success"]:
                    return selected, True
                if e["kind"] == "trajectory_backed_up":
                    self.assertTrue(all(u["after"]["mean"] == 0 for u in p["updates"]))
            return selected, False

        for task in (
            TASK,
            CountdownTask((1, 2, 3, 4, 5, 6), 720),
            CountdownTask((1, 1, 1, 1, 1, 1), 999),
        ):
            kwargs = dict(
                task=task,
                proposal=P.PROPOSAL,
                method=core.TrackAMethodSpec.puct(),
                budget_profile=profile(),
                exploration_seed=0,
            )
            self.assertEqual(
                prefix(core._SearchSession(**kwargs).run()),
                prefix(MeanOff(**kwargs).run()),
            )

    def test_insufficient_positive_score_budget_preserves_missingness(self):
        out = P.run_puct_return_cell(
            TASK, spec=P.PuctReturnSpec(P.METHODS[0]), budget_profile=profile(1)
        )
        self.assertTrue(out.summary["missing_terminal"])
        self.assertIsNone(out.summary["minimum_terminal_error"])
        self.assertIsNone(out.summary["first_exact_work"])

    def test_verifier_guard_prevents_uncharged_verification_and_backup(self):
        with patch.object(
            CountdownTask, "verify", side_effect=AssertionError("no permit")
        ):
            result = P._DenseSession(
                task=TASK,
                proposal=P.PROPOSAL,
                budget_profile=profile(verifier_calls=0),
                exploration_seed=0,
            ).run()
        self.assertFalse(result.summary["budget_valid"])
        self.assertEqual(result.summary["terminal_count"], 0)
        self.assertFalse(
            any(e["kind"] == "trajectory_backed_up" for e in result.record["events"])
        )

    def test_terminal_trace_failure_poisoned_without_posterior_commit(self):
        s = P._DenseSession(
            task=TASK, proposal=P.PROPOSAL, budget_profile=profile(), exploration_seed=0
        )
        append = s.trace.append_batch

        def fail_terminal(events, **kwargs):
            if any(k == "terminal_verified" for k, _ in events):
                raise RuntimeError("fixture commit failure")
            return append(events, **kwargs)

        with patch.object(s.trace, "append_batch", side_effect=fail_terminal):
            with self.assertRaises(RuntimeError):
                s.run()
        self.assertTrue(s._poisoned)
        self.assertEqual(s.terminals, [])
        self.assertTrue(
            all(p.visits == 0 for node in s.nodes.values() for p in node.posteriors)
        )

    def test_rehashed_wrong_selection_return_and_backups_rejected(self):
        for kind, field, value in (
            ("selection_committed", "selected_value", -9.0),
            ("trajectory_backed_up", "terminal_value", -1.0),
            ("trajectory_backed_up", "terminal_value_scale", 8),
            ("trajectory_backed_up", "updates", []),
        ):
            bad = copy.deepcopy(self.results[P.METHODS[0]].record)
            next(e for e in bad["search_record"]["events"] if e["kind"] == kind)[
                "payload"
            ][field] = value
            with self.subTest(field=field), self.assertRaises(TraceValidationError):
                self.replay(rehash(bad))

    def test_outer_forgery_wrong_identity_and_noncanonical_bytes_rejected(self):
        bad = copy.deepcopy(self.results[P.METHODS[0]].record)
        bad["summary"]["minimum_terminal_error"] = 999
        with self.assertRaises(TraceValidationError):
            self.replay(rehash(bad))
        for kwargs in (
            dict(expected_run_identity_digest="0" * 64),
            dict(spec=P.PuctReturnSpec("puct")),
        ):
            with self.assertRaises(TraceValidationError):
                self.replay(self.results[P.METHODS[0]].canonical_bytes, **kwargs)
        with self.assertRaises(TraceValidationError):
            self.replay(self.results[P.METHODS[0]].canonical_bytes + b" ")


if __name__ == "__main__":
    unittest.main()
