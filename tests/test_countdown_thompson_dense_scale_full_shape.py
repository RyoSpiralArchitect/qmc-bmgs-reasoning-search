"""Clean-checkout end-to-end fixture with explicit sealed-access tripwires."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
_GUARDED_ENTRYPOINT = r"""
import importlib
import os
import sys

def audit(event, args):
    if event == "open" and args and isinstance(args[0], (str, bytes, os.PathLike)):
        path = os.fsdecode(args[0]).replace("\\", "/")
        if "/docs/preregistrations/" in path or path.startswith("docs/preregistrations/"):
            raise AssertionError("full-shape fixture must not open any sealed bundle")

sys.addaudithook(audit)
from qmc_bmgs.experiments import countdown_thompson_dense_scale_core as core

def forbidden(*args, **kwargs):
    raise AssertionError("production input/planning path forbidden in fixture")

core.load_production_inputs = forbidden
original_run = core.run_countdown_track_a_search
original_replay = core.replay_countdown_track_a_search_bytes

def assert_public(task):
    assert task.inputs == (1, 2, 3, 4, 5, 6)
    assert task.target in (*range(1, 13), 720)

def run(task, **kwargs):
    assert_public(task)
    return original_run(task, **kwargs)

def replay(payload, **kwargs):
    assert_public(kwargs["task"])
    return original_replay(payload, **kwargs)

core.run_countdown_track_a_search = run
core.replay_countdown_track_a_search_bytes = replay
from qmc_bmgs.experiments import countdown_thompson_dense_scale_runner as runner
runner.plan_execution = forbidden
runner.run_execution = forbidden
from qmc_bmgs.experiments import countdown_thompson_dense_scale_publication as publication
original_summary = publication.publish_dense_scale_fixture_summary

def debug_summary(*args, **kwargs):
    try:
        return original_summary(*args, **kwargs)
    except BaseException:
        # Public-fixture diagnostic only. Production CLI remains outcome-quiet.
        import traceback
        traceback.print_exc()
        raise

publication.publish_dense_scale_fixture_summary = debug_summary
module = importlib.import_module(sys.argv[1])
raise SystemExit(module.main(sys.argv[2:]))
"""


class DenseScaleFullShapeTests(unittest.TestCase):
    def test_clean_source_384_fixture_and_descendant_analysis(self):
        # The exact summary writer deliberately compares every lexical ancestor
        # generation. Keep this long barrier outside the busy shared OS temp
        # namespace; unrelated sibling churn there must still fail closed.
        with tempfile.TemporaryDirectory(
            prefix=".qmc-dense-full-shape-", dir=ROOT.parent
        ) as temporary:
            root = Path(temporary).resolve()
            checkout = root / "checkout"
            subprocess.run(
                ["git", "clone", "--quiet", "--shared", str(ROOT), str(checkout)],
                check=True,
                capture_output=True,
            )
            original_head = subprocess.check_output(
                ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True
            ).strip()
            for name in ("raw", "authority"):
                (root / name).mkdir()
            artifact = root / "raw" / "fixture.commit.json"
            authorization = root / "authority" / "fixture-authorization.json"

            def invoke(module, *args):
                with tempfile.TemporaryDirectory(prefix="qmc-dense-import-") as cache:
                    cache_path = Path(cache).resolve()
                    os.chmod(cache_path, 0o700)
                    env = os.environ.copy()
                    env["PYTHONPATH"] = str(checkout / "src")
                    env["PYTHONPYCACHEPREFIX"] = str(cache_path)
                    result = subprocess.run(
                        [
                            sys.executable,
                            "-P",
                            "-B",
                            "-c",
                            _GUARDED_ENTRYPOINT,
                            "qmc_bmgs.experiments." + module,
                            *map(str, args),
                        ],
                        cwd=checkout,
                        env=env,
                        text=True,
                        capture_output=True,
                        timeout=240,
                    )
                    self.assertEqual(
                        result.returncode,
                        0,
                        result.stdout[-5000:] + result.stderr[-5000:],
                    )
                    return json.loads(result.stdout)

            committed = invoke(
                "countdown_thompson_dense_scale_runner",
                "--full-shape-fixture",
                "--output",
                artifact,
                "--authorization-out",
                authorization,
                "--repository-root",
                checkout,
            )
            self.assertEqual(committed["status"], "COMMITTED")
            self.assertEqual(committed["authorization_revision"], original_head)
            self.assertNotIn("decision", committed)
            external = json.loads(authorization.read_bytes())
            self.assertEqual(external["cell_count"], 384)
            self.assertIsNone(external["dense_scale_seal_digest"])
            self.assertIsNone(external["preregistration_file_sha256"])
            self.assertNotIn("decision", external)

            # An empty descendant changes current HEAD without changing any
            # reviewed source. It is a test-only commit in a disposable clone.
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(checkout),
                    "-c",
                    "user.name=Fixture Test",
                    "-c",
                    "user.email=fixture@example.invalid",
                    "commit",
                    "--quiet",
                    "--allow-empty",
                    "-m",
                    "Test later independent analysis epoch",
                ],
                check=True,
                capture_output=True,
            )
            # The same raw parent is deliberate: own summary publication may
            # change directory mtime, but no reserved artifact identity may move.
            summary_path = root / "raw" / "fixture.summary.json"
            summary = invoke(
                "countdown_thompson_dense_scale_analysis",
                "--analyze-full-shape-fixture",
                artifact,
                "--authorization-file",
                authorization,
                "--authorization-digest",
                committed["authorization_digest"],
                "--authorization-revision",
                original_head,
                "--output",
                summary_path,
                "--repository-root",
                checkout,
            )
            self.assertEqual(json.loads(summary_path.read_bytes()), summary)
            self.assertNotIn("decision", summary)
            self.assertNotIn("selected_scale", summary)
            raw = json.dumps(summary)
            self.assertNotIn("READY_TO_PREREGISTER_SOURCE_DISJOINT_CONFIRMATION", raw)
            self.assertNotIn("STOP_REPAIR_NO_LOCKED_128_RUN", raw)
            self.assertEqual(
                subprocess.check_output(
                    ["git", "-C", str(checkout), "status", "--porcelain"]
                ),
                b"",
            )


if __name__ == "__main__":
    unittest.main()
