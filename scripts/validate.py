#!/usr/bin/env python3
"""Run the repository's download-free validation surface."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def _run(command: list[str], *, temporary_root: Path, cwd: Path = ROOT) -> None:
    print("+", " ".join(command), flush=True)
    environment = os.environ.copy()
    # Whole-path publication generations include temporary-root ancestors.
    # Unrelated users of the shared OS temp namespace must not perturb the
    # intended fault injection of a repository test.
    environment["TMPDIR"] = str(temporary_root)
    environment["PYTHONPATH"] = str(SRC)
    environment.setdefault("PYTHONPYCACHEPREFIX", "/tmp/qmc_bmgs_pycache")
    subprocess.run(command, cwd=cwd, env=environment, check=True)


def _validate(temporary_root: Path) -> None:
    def run(command: list[str], *, cwd: Path = ROOT) -> None:
        _run(command, temporary_root=temporary_root, cwd=cwd)

    run(
        [
            sys.executable,
            "-m",
            "compileall",
            "-q",
            "src",
            "tests",
            "scripts",
        ]
    )
    if shutil.which("ruff") is None:
        print("ruff unavailable: lint check skipped", flush=True)
    else:
        run(["ruff", "check", "."])
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])
    run([sys.executable, "scripts/verify_artifacts.py"])

    # Catch accidental sibling-import or source-relative assumptions by invoking
    # every CLI module from outside the repository.
    outside = Path("/tmp")
    for module in (
        "qmc_bmgs.policy",
        "qmc_bmgs.anthropic_countdown",
        "qmc_bmgs.openai_countdown",
        "qmc_bmgs.benchmarks.role_lock",
        "qmc_bmgs.benchmarks.countdown",
        "qmc_bmgs.experiments.d4_noise_sweep",
        "qmc_bmgs.experiments.channel_ablation",
        "qmc_bmgs.experiments.fixed_verifier_budget",
        "qmc_bmgs.experiments.two_phase_sampler",
        "qmc_bmgs.experiments.two_phase_validation",
        "qmc_bmgs.experiments.credit_assignment",
        "qmc_bmgs.experiments.countdown_anthropic_dev",
        "qmc_bmgs.experiments.countdown_openai_dev",
        "qmc_bmgs.experiments.countdown_thompson_source_ablation",
        "qmc_bmgs.experiments.countdown_calibration_grid",
        "qmc_bmgs.experiments.countdown_track_a_substrate",
        "qmc_bmgs.experiments.countdown_track_a_search",
        "qmc_bmgs.experiments.countdown_track_a_canary_manifest",
        "qmc_bmgs.experiments.countdown_track_a_canary_runner",
        "qmc_bmgs.experiments.countdown_track_a_canary_analysis",
        "qmc_bmgs.experiments.countdown_thompson_diagnostic_runner",
        "qmc_bmgs.experiments.countdown_thompson_diagnostic_analysis",
        "qmc_bmgs.experiments.countdown_thompson_regular_file_publication_v2",
        "qmc_bmgs.experiments.countdown_thompson_posthoc_mechanism",
        "qmc_bmgs.experiments.countdown_thompson_selection_margin",
        "qmc_bmgs.experiments.countdown_thompson_dense_scale_manifest",
        "qmc_bmgs.experiments.countdown_thompson_dense_scale_runner",
        "qmc_bmgs.experiments.countdown_thompson_dense_scale_analysis",
    ):
        command = [sys.executable, "-m", module, "--self-test"]
        if module == "qmc_bmgs.experiments.countdown_thompson_dense_scale_manifest":
            command.extend(["--repository-root", str(ROOT)])
        run(command, cwd=outside)
    run(
        [
            sys.executable,
            "-m",
            "qmc_bmgs.experiments.countdown_thompson_dense_scale_manifest",
            "--verify",
            str(ROOT / "docs/preregistrations/countdown_thompson_dense_scale_v5"),
            "--repository-root",
            str(ROOT),
        ],
        cwd=outside,
    )
    print("repository validation: PASS")


def main() -> None:
    # A sibling stays outside the checked source tree and shared OS temp root.
    with tempfile.TemporaryDirectory(
        prefix=".qmc-bmgs-validation-", dir=ROOT.parent
    ) as temporary:
        _validate(Path(temporary).resolve())


if __name__ == "__main__":
    main()
