"""Validation isolation is test infrastructure, not execution authority."""

from __future__ import annotations

import importlib.util
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "repository_validation", Path(__file__).resolve().parents[1] / "scripts/validate.py"
)
assert SPEC is not None and SPEC.loader is not None
validation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validation)


class ValidationHarnessTests(unittest.TestCase):
    def test_child_receives_private_temp_without_mutating_parent_environment(self):
        with (
            patch.dict(os.environ, {"TMPDIR": "/shared/temp"}),
            patch.object(validation.subprocess, "run") as run,
            redirect_stdout(io.StringIO()),
        ):
            private = Path("/private/test-namespace")
            validation._run(["python", "--version"], temporary_root=private)
            self.assertEqual(run.call_args.kwargs["env"]["TMPDIR"], str(private))
            self.assertEqual(
                run.call_args.kwargs["env"]["PYTHONPATH"], str(validation.SRC)
            )
            self.assertTrue(run.call_args.kwargs["check"])
            self.assertEqual(os.environ["TMPDIR"], "/shared/temp")

    def test_private_namespace_is_outside_checkout_and_cleaned_on_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary).resolve()
            checkout = parent / "checkout"
            checkout.mkdir()
            observed = []

            def fail(temporary_root):
                self.assertEqual(temporary_root.parent, parent)
                self.assertFalse(temporary_root.is_relative_to(checkout))
                self.assertTrue(temporary_root.is_dir())
                observed.append(temporary_root)
                raise RuntimeError("synthetic validation failure")

            with (
                patch.object(validation, "ROOT", checkout),
                patch.object(validation, "_validate", side_effect=fail),
                self.assertRaisesRegex(RuntimeError, "synthetic validation failure"),
            ):
                validation.main()
            self.assertEqual(len(observed), 1)
            self.assertFalse(observed[0].exists())


if __name__ == "__main__":
    unittest.main()
