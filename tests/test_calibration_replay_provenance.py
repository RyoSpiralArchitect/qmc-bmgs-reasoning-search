from __future__ import annotations

import contextlib
import io
import os
import unittest
from pathlib import Path
from unittest import mock

from qmc_bmgs.experiments import countdown_calibration_grid as calibration


class CalibrationReplayProvenanceTests(unittest.TestCase):
    def test_replay_requires_both_original_source_directories(self) -> None:
        cases = (
            ["--replay", "artifact"],
            ["--replay", "artifact", "--anthropic-dir", "anthropic"],
            ["--replay", "artifact", "--openai-dir", "openai"],
        )
        for argv in cases:
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    calibration.main(argv)
                self.assertEqual(caught.exception.code, 2)

    def test_search_only_rejects_source_directories(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                calibration.main(
                    [
                        "--replay-search-only",
                        "artifact",
                        "--anthropic-dir",
                        "anthropic",
                    ]
                )
        self.assertEqual(caught.exception.code, 2)

    def test_replay_matches_fresh_source_receipt_to_artifact(self) -> None:
        receipt = {"mode": "fresh", "providers": {"anthropic": {}, "openai": {}}}
        summary = {"source_validation": receipt}
        with (
            mock.patch.object(
                calibration,
                "_deny_network",
                return_value=contextlib.nullcontext(),
            ) as deny_network,
            mock.patch.object(
                calibration,
                "_validate_sources_without_mutation",
                return_value=receipt,
            ) as validate_sources,
            mock.patch.object(
                calibration,
                "validate_artifact",
                return_value=summary,
            ) as validate_artifact,
        ):
            observed = calibration._replay_with_source_revalidation(
                artifact_dir=Path("artifact"),
                anthropic_dir=Path("anthropic"),
                openai_dir=Path("openai"),
            )

        self.assertIs(observed, summary)
        deny_network.assert_called_once_with()
        validate_sources.assert_called_once_with(
            {
                "anthropic": Path("anthropic"),
                "openai": Path("openai"),
            }
        )
        validate_artifact.assert_called_once_with(
            Path("artifact"),
            require_replay_match=True,
        )

    def test_replay_rejects_fresh_source_receipt_mismatch(self) -> None:
        with (
            mock.patch.object(
                calibration,
                "_deny_network",
                return_value=contextlib.nullcontext(),
            ),
            mock.patch.object(
                calibration,
                "_validate_sources_without_mutation",
                return_value={"mode": "fresh"},
            ),
            mock.patch.object(
                calibration,
                "validate_artifact",
                return_value={"source_validation": {"mode": "frozen"}},
            ),
        ):
            with self.assertRaisesRegex(
                AssertionError,
                "fresh source validation receipt does not match",
            ):
                calibration._replay_with_source_revalidation(
                    artifact_dir=Path("artifact"),
                    anthropic_dir=Path("anthropic"),
                    openai_dir=Path("openai"),
                )

    def test_search_only_does_not_invoke_source_validation(self) -> None:
        summary = {
            "decision": {},
            "deterministic_digest": "digest",
            "pairing_gate": {},
        }
        with (
            mock.patch.dict(
                os.environ,
                {"ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": ""},
            ),
            mock.patch.object(
                calibration,
                "_replay_search_bytes_only",
                return_value=summary,
            ) as replay_search_only,
            mock.patch.object(
                calibration,
                "_validate_sources_without_mutation",
            ) as validate_sources,
            mock.patch.object(calibration, "_print_summary") as print_summary,
        ):
            calibration.main(["--replay-search-only", "artifact"])

        replay_search_only.assert_called_once_with(Path("artifact"))
        validate_sources.assert_not_called()
        print_summary.assert_called_once_with(
            summary,
            replay_provenance={
                "mode": "self_contained_search_bytes_only",
                "original_source_artifacts_revalidated": False,
            },
        )


if __name__ == "__main__":
    unittest.main()
