from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.verify_artifacts import _strict_json, verify_manifest


class ArtifactStrictnessTests(unittest.TestCase):
    def test_strict_json_rejects_duplicate_keys(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "duplicate.json"
            path.write_text('{"value":1,"value":2}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                _strict_json(path)

    def test_manifest_rejects_non_object_json(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "manifest.json"
            path.write_text("[]\n", encoding="utf-8")
            with self.assertRaisesRegex(
                AssertionError,
                "manifest is not a JSON object",
            ):
                verify_manifest(path)

    def test_manifest_rejects_undeclared_extra_file(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            summary = directory / "summary.json"
            summary.write_text('{"data_quality":{"status":"PASS"}}\n', encoding="utf-8")
            payload = summary.read_bytes()
            manifest = {
                "artifact_id": "strictness_fixture",
                "files": {
                    "summary.json": {
                        "bytes": len(payload),
                        "sha256": hashlib.sha256(payload).hexdigest(),
                    }
                },
                "schema_version": "qmc-bmgs-artifact-manifest/v1",
            }
            path = directory / "manifest.json"
            path.write_text(
                json.dumps(manifest, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (directory / "undeclared.txt").write_text("extra\n", encoding="utf-8")
            with self.assertRaisesRegex(
                AssertionError,
                "artifact entry-set mismatch",
            ):
                verify_manifest(path)

    def test_manifest_rejects_undeclared_directory(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            payload = b'{"data_quality":{"status":"PASS"}}\n'
            (directory / "summary.json").write_bytes(payload)
            manifest = {
                "artifact_id": "strictness_fixture",
                "files": {
                    "summary.json": {
                        "bytes": len(payload),
                        "sha256": hashlib.sha256(payload).hexdigest(),
                    }
                },
                "schema_version": "qmc-bmgs-artifact-manifest/v1",
            }
            path = directory / "manifest.json"
            path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
            (directory / "undeclared").mkdir()

            with self.assertRaisesRegex(
                AssertionError,
                "artifact entry-set mismatch",
            ):
                verify_manifest(path)

    def test_manifest_rejects_declared_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            directory = root_path / "artifact"
            directory.mkdir()
            payload = b'{"data_quality":{"status":"PASS"}}\n'
            target = root_path / "outside-summary.json"
            target.write_bytes(payload)
            (directory / "summary.json").symlink_to(target)
            manifest = {
                "artifact_id": "strictness_fixture",
                "files": {
                    "summary.json": {
                        "bytes": len(payload),
                        "sha256": hashlib.sha256(payload).hexdigest(),
                    }
                },
                "schema_version": "qmc-bmgs-artifact-manifest/v1",
            }
            path = directory / "manifest.json"
            path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(
                AssertionError,
                "artifact is not a regular file",
            ):
                verify_manifest(path)


if __name__ == "__main__":
    unittest.main()
