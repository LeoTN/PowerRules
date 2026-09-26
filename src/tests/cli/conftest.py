from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _run_cli_tests_in_tmp_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run every CLI test in an isolated temporary directory.

    This keeps files with a relative default path - currently the log file
    written by "configure_logging()" - out of the repository working directory.
    """
    monkeypatch.chdir(tmp_path)
