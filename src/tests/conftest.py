import logging
from collections.abc import Iterator
from pathlib import Path
from typing import cast
from unittest.mock import Mock, patch

import pytest

from powerrules.application.runtime import PlatformProviders
from powerrules.trust.store import TrustStore
from tests.factories import make_platform_providers
from tests.helpers import write_workspace_scripts


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


@pytest.fixture(autouse=True)
def _reset_powerrules_logger() -> Iterator[None]:
    """Remove the handlers and the level which "configure_logging()" set, so no test depends on the one before.

    Without this, the file handlers stay open after a test and the level of the package logger leaks into other tests.
    """
    yield

    package_logger = logging.getLogger("powerrules")

    for handler in list(package_logger.handlers):
        handler.close()
        package_logger.removeHandler(handler)

    package_logger.setLevel(logging.NOTSET)


@pytest.fixture
def trust_store_path(tmp_path: Path) -> Path:
    """Path of a trust store file. Its directory does not exist yet on purpose."""
    return tmp_path / "store" / "trust.json"


@pytest.fixture
def trust_store(trust_store_path: Path) -> TrustStore:
    """A trust store in the temporary directory of the test."""
    return TrustStore(trust_store_path)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A directory with the scripts "scripts/backup.sh" and "scripts/test.sh", with all symbolic links resolved.

    The policy is not part of it. Tests write the policy they need with "write_policy()".
    """
    return write_workspace_scripts(tmp_path / "workspace")


@pytest.fixture
def patched_platform_providers() -> Iterator[PlatformProviders]:
    """Replace the providers of the runtime by mocks, so no command is run for real."""
    providers = make_platform_providers()

    with patch(
        "powerrules.application.runtime.get_platform_providers",
        return_value=providers,
    ):
        yield providers


@pytest.fixture
def command_provider(patched_platform_providers: PlatformProviders) -> Mock:
    """The mocked command provider of the patched platform providers."""
    return cast(Mock, patched_platform_providers.command)
