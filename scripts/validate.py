#!/usr/bin/env python3
"""Run the repository's download-free validation surface."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def _run(command: list[str], *, cwd: Path = ROOT) -> None:
    print("+", " ".join(command), flush=True)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(SRC)
    environment.setdefault("PYTHONPYCACHEPREFIX", "/tmp/qmc_bmgs_pycache")
    subprocess.run(command, cwd=cwd, env=environment, check=True)


def main() -> None:
    _run(
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
        _run(["ruff", "check", "."])
    _run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])
    _run([sys.executable, "scripts/verify_artifacts.py"])

    # Catch accidental sibling-import or source-relative assumptions by invoking
    # every CLI module from outside the repository.
    outside = Path("/tmp")
    for module in (
        "qmc_bmgs.policy",
        "qmc_bmgs.benchmarks.role_lock",
        "qmc_bmgs.experiments.d4_noise_sweep",
        "qmc_bmgs.experiments.channel_ablation",
    ):
        _run([sys.executable, "-m", module, "--self-test"], cwd=outside)
    print("repository validation: PASS")


if __name__ == "__main__":
    main()
