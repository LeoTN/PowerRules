from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_home(
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Give every test its own home directory, so the trust store of the real user is never read or written."""
    home = tmp_path_factory.mktemp("home")
    # "Path.home()" uses HOME on POSIX and USERPROFILE on Windows
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))

    return home
