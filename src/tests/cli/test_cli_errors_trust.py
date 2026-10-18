import logging

import pytest
import typer

from powerrules.cli.errors import (
    EXIT_POLICY_ERROR,
    EXIT_POLICY_TRUST_ERROR,
    EXIT_RUNTIME_ERROR,
    handle_cli_error,
)
from powerrules.engine.exceptions import (
    FileIntegrityError,
    PolicyNotTrustedError,
    TrustStoreError,
)


@pytest.fixture(autouse=True)
def _capture_debug_logs(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)


def test_trust_exit_code_is_distinguishable_from_other_errors() -> None:
    assert len({EXIT_RUNTIME_ERROR, EXIT_POLICY_ERROR, EXIT_POLICY_TRUST_ERROR}) == 3


@pytest.mark.parametrize(
    ("error", "exit_code"),
    [
        (PolicyNotTrustedError("Test policy is not trusted"), EXIT_POLICY_TRUST_ERROR),
        (FileIntegrityError("Test file was modified"), EXIT_POLICY_TRUST_ERROR),
        (TrustStoreError("Test store is broken"), EXIT_RUNTIME_ERROR),
    ],
)
def test_cli_error_handler_reports_trust_errors_with_their_own_message(
    caplog: pytest.LogCaptureFixture,
    error: Exception,
    exit_code: int,
) -> None:
    with pytest.raises(typer.Exit) as exc_info:
        handle_cli_error(error)

    assert exc_info.value.exit_code == exit_code
    assert caplog.records[-1].levelname == "ERROR"
    # The message already explains what to do, so it is not wrapped
    assert caplog.records[-1].getMessage() == str(error)
