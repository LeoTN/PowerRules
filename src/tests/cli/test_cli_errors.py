import pytest
import typer
import yaml
from pydantic import ValidationError

from powerrules.cli.errors import (
    EXIT_POLICY_ERROR,
    EXIT_POLICY_TRUST_ERROR,
    EXIT_RUNTIME_ERROR,
    cli_command,
)
from powerrules.engine.exceptions import (
    ActionExecutionError,
    ConditionEvaluationError,
    FileIntegrityError,
    PolicyNotTrustedError,
    TrustStoreError,
)
from tests.factories import make_validation_error
from tests.helpers import get_cli_exit

########################
# handle_cli_error tests
########################


def test_cli_error_handler_reports_unparsable_policy(
    caplog: pytest.LogCaptureFixture,
) -> None:
    assert (
        get_cli_exit(yaml.YAMLError("Test YAML failure")).exit_code == EXIT_POLICY_ERROR
    )
    assert "Failed to parse policy file" in caplog.text


def test_cli_error_handler_reports_all_validation_errors(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        raise make_validation_error()

    assert get_cli_exit(exc_info.value).exit_code == EXIT_POLICY_ERROR
    assert caplog.records[0].levelname == "ERROR"
    assert "Policy validation failed" in caplog.text
    # The location of the invalid value is included
    assert "inner.enabled: " in caplog.text


def test_cli_error_handler_reports_value_error_as_it_is(
    caplog: pytest.LogCaptureFixture,
) -> None:
    assert (
        get_cli_exit(ValueError("Test value problem")).exit_code == EXIT_RUNTIME_ERROR
    )
    assert caplog.records[-1].getMessage() == "Test value problem"


def test_cli_error_handler_reports_unexpected_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    assert get_cli_exit(RuntimeError("Test failure")).exit_code == EXIT_RUNTIME_ERROR
    assert caplog.records[-1].levelname == "ERROR"
    assert "Unexpected error: Test failure" in caplog.text


###################
# cli_command tests
###################


def test_cli_command_returns_result_of_command() -> None:
    @cli_command
    def command(first: int, second: int = 0) -> int:
        return first + second

    assert command(1, second=2) == 3


def test_cli_command_keeps_metadata_of_command() -> None:
    @cli_command
    def documented_command() -> None:
        """Test documentation."""

    assert documented_command.__name__ == "documented_command"
    assert documented_command.__doc__ == "Test documentation."


@pytest.mark.parametrize(
    ("error", "exit_code", "message"),
    [
        (
            ConditionEvaluationError("Test condition failed"),
            EXIT_RUNTIME_ERROR,
            "Failed to evaluate condition: Test condition failed",
        ),
        (
            ActionExecutionError("Test action failed"),
            EXIT_RUNTIME_ERROR,
            "Failed to execute action: Test action failed",
        ),
        (
            FileNotFoundError(2, "File not found", "policy.yaml"),
            EXIT_POLICY_ERROR,
            "Policy file not found: policy.yaml",
        ),
    ],
)
def test_cli_command_handles_command_exception(
    caplog: pytest.LogCaptureFixture,
    error: Exception,
    exit_code: int,
    message: str,
) -> None:
    @cli_command
    def failing_command() -> None:
        raise error

    with pytest.raises(typer.Exit) as exc_info:
        failing_command()

    assert exc_info.value.exit_code == exit_code
    # The message is wrapped by "handle_cli_error()"
    assert message in caplog.text


def test_cli_command_includes_stack_trace_for_unexpected_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    @cli_command
    def failing_command() -> None:
        raise RuntimeError("Test failure")

    with pytest.raises(typer.Exit):
        failing_command()

    exception_info = caplog.records[-1].exc_info

    assert exception_info is not None
    assert exception_info[0] is RuntimeError


def test_cli_command_does_not_intercept_typer_exit() -> None:
    @cli_command
    def exiting_command() -> None:
        raise typer.Exit(code=42)

    with pytest.raises(typer.Exit) as exc_info:
        exiting_command()

    assert exc_info.value.exit_code == 42


#############
# Trust tests
#############


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
    assert get_cli_exit(error).exit_code == exit_code
    assert caplog.records[-1].levelname == "ERROR"
    # The message already explains what to do, so it is not wrapped
    assert caplog.records[-1].getMessage() == str(error)
