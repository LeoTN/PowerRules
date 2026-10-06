"""Run the checks of the CI locally: formatting, linting and tests.

Usage:
    poetry run python devscripts/run_checks.py
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# The formatter runs first, so the linter and the tests see the formatted code
CHECKS: dict[str, list[str]] = {
    "ruff format": [sys.executable, "-m", "ruff", "format", "."],
    "ruff check": [sys.executable, "-m", "ruff", "check", "."],
    "pytest": [sys.executable, "-m", "pytest"],
}


def main() -> None:
    """Run all checks and exit with an error code if at least one of them fails."""
    failed_checks: list[str] = []

    for name, command in CHECKS.items():
        print(f"[INFO] Running {name}...")

        result = subprocess.run(command, cwd=REPO_ROOT, check=False)

        if result.returncode != 0:
            failed_checks.append(name)

    if failed_checks:
        print(f"[ERROR] Failed checks: {', '.join(failed_checks)}")
        sys.exit(1)

    print("[INFO] All checks passed")


if __name__ == "__main__":
    main()
