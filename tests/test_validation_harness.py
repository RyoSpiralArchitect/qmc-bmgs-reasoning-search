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
HOST_TEMP = Path("/private/tmp") if Path("/private/tmp").is_dir() else Path("/tmp")


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
        with tempfile.TemporaryDirectory(prefix=".qvt-", dir=HOST_TEMP) as temporary:
            parent = Path(temporary).resolve()
            checkout = parent / "checkout"
            checkout.mkdir()
            observed = []

            def fail(temporary_root):
                self.assertEqual(temporary_root.parent, parent)
                self.assertTrue(temporary_root.name.startswith(".qv-"))
                self.assertFalse(temporary_root.is_relative_to(checkout))
                self.assertTrue(temporary_root.is_dir())
                observed.append(temporary_root)
                raise RuntimeError("synthetic validation failure")

            with (
                patch.dict(os.environ, {validation.TEMP_PARENT_ENV: str(parent)}),
                patch.object(validation, "ROOT", checkout),
                patch.object(validation, "_probe_unix_socket_path") as probe,
                patch.object(validation, "_validate", side_effect=fail),
                self.assertRaisesRegex(RuntimeError, "synthetic validation failure"),
            ):
                validation.main()
            self.assertEqual(len(observed), 1)
            probe.assert_called_once_with(observed[0])
            self.assertFalse(observed[0].exists())

    def test_failed_preflight_cleans_private_namespace_without_running_validation(self):
        with tempfile.TemporaryDirectory(prefix=".qvt-", dir=HOST_TEMP) as temporary:
            parent = Path(temporary).resolve()
            observed = []

            def fail(temporary_root):
                observed.append(temporary_root)
                self.assertTrue(temporary_root.is_dir())
                raise RuntimeError("synthetic preflight failure")

            with (
                patch.dict(os.environ, {validation.TEMP_PARENT_ENV: str(parent)}),
                patch.object(validation, "_probe_unix_socket_path", side_effect=fail),
                patch.object(validation, "_validate") as validate,
                self.assertRaisesRegex(RuntimeError, "synthetic preflight failure"),
            ):
                validation.main()
            validate.assert_not_called()
            self.assertEqual(len(observed), 1)
            self.assertFalse(observed[0].exists())

    def test_default_parent_is_resolved_home(self):
        with tempfile.TemporaryDirectory(prefix=".qvt-", dir=HOST_TEMP) as temporary:
            home = Path(temporary).resolve()
            checkout = home / "checkout"
            checkout.mkdir()
            with (
                patch.dict(os.environ, {}, clear=True),
                patch.object(validation.Path, "home", return_value=home / "."),
                patch.object(validation, "ROOT", checkout),
            ):
                self.assertEqual(validation._temporary_parent(), home)

    def test_explicit_parent_is_resolved_outside_checkout(self):
        with tempfile.TemporaryDirectory(prefix=".qvt-", dir=HOST_TEMP) as temporary:
            root = Path(temporary).resolve()
            checkout = root / "checkout"
            checkout.mkdir()
            outside = root / "outside"
            outside.mkdir()
            alias = root / "parent-alias"
            alias.symlink_to(outside, target_is_directory=True)
            with (
                patch.dict(os.environ, {validation.TEMP_PARENT_ENV: str(alias)}),
                patch.object(validation.Path, "home", side_effect=AssertionError),
                patch.object(validation, "ROOT", checkout),
            ):
                # The real path is used; aliases cannot bypass the socket limit.
                self.assertEqual(validation._temporary_parent(), outside)

    def test_invalid_or_inside_checkout_parent_fails_before_validation(self):
        with tempfile.TemporaryDirectory(prefix=".qvt-", dir=HOST_TEMP) as temporary:
            root = Path(temporary).resolve()
            checkout = root / "checkout"
            checkout.mkdir()
            nested = checkout / "nested"
            nested.mkdir()
            alias = root / "inside-alias"
            alias.symlink_to(nested, target_is_directory=True)
            regular = root / "regular"
            regular.touch()
            for candidate in (checkout, nested, alias, root / "missing", regular, ""):
                with (
                    self.subTest(candidate=candidate),
                    patch.dict(
                        os.environ, {validation.TEMP_PARENT_ENV: str(candidate)}
                    ),
                    patch.object(validation, "ROOT", checkout),
                    patch.object(validation, "_probe_unix_socket_path") as probe,
                    patch.object(validation, "_validate") as validate,
                    self.assertRaisesRegex(RuntimeError, validation.TEMP_PARENT_ENV),
                ):
                    validation.main()
                probe.assert_not_called()
                validate.assert_not_called()

    def test_actual_short_socket_probe_cleans_its_namespace(self):
        # Use host-local test storage, not the user's real home or checkout parent.
        with tempfile.TemporaryDirectory(prefix=".qv-", dir=HOST_TEMP) as temporary:
            private = Path(temporary).resolve()
            validation._probe_unix_socket_path(private)
            self.assertEqual(list(private.iterdir()), [])

    def test_actual_long_socket_path_fails_clearly_and_cleans_its_namespace(self):
        with tempfile.TemporaryDirectory(prefix=".qv-", dir=HOST_TEMP) as temporary:
            private = Path(temporary).resolve() / ("long-parent-" + "x" * 120)
            private.mkdir()
            with self.assertRaisesRegex(
                RuntimeError, validation.TEMP_PARENT_ENV
            ) as error:
                validation._probe_unix_socket_path(private)
            self.assertIn(
                "Unix-socket validation preflight failed", str(error.exception)
            )
            self.assertIn(str(private), str(error.exception))
            self.assertIn("not skipped", str(error.exception))
            self.assertEqual(list(private.iterdir()), [])

    def test_unsupported_socket_probe_fails_clearly_and_cleans_its_namespace(self):
        with tempfile.TemporaryDirectory(prefix=".qv-", dir=HOST_TEMP) as temporary:
            private = Path(temporary).resolve()
            with (
                patch.object(
                    validation.socket, "socket", side_effect=OSError("unsupported")
                ),
                self.assertRaisesRegex(
                    RuntimeError, validation.TEMP_PARENT_ENV
                ) as error,
            ):
                validation._probe_unix_socket_path(private)
            self.assertIn("unsupported", str(error.exception))
            self.assertEqual(list(private.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
