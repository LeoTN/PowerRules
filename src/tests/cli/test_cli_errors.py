import logging

import pytest
import typer
import yaml
from pydantic import BaseModel, ValidationError

from powerrules.cli.errors import (
    EXIT_POLICY_ERROR,
    EXIT_RUNTIME_ERROR,
    cli_command,
    handle_cli_error,
)
from powerrules.engine.exceptions import ActionExecutionError, ConditionEvaluationError


class _InnerModel(BaseModel):
    enabled: bool


class _OuterModel(BaseModel):
    inner: _InnerModel


def _handle(error: Exception) -> typer.Exit:
    """Handle an error and return the exit which is raised."""
    with pytest.raises(typer.Exit) as exc_info:
        handle_cli_error(error)

    return exc_info.value


@pytest.fixture(autouse=True)
def _capture_debug_logs(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)


########################
# handle_cli_error tests
########################


def test_cli_error_handler_reports_missing_policy(
    caplog: pytest.LogCaptureFixture,
) -> None:
    error = FileNotFoundError(2, "File not found", "policy.yaml")

    assert _handle(error).exit_code == EXIT_POLICY_ERROR
    assert caplog.records[-1].levelname == "ERROR"
    assert "Policy file not found: policy.yaml" in caplog.text


def test_cli_error_handler_reports_unparsable_policy(
    caplog: pytest.LogCaptureFixture,
) -> None:
    assert _handle(yaml.YAMLError("Test YAML failure")).exit_code == EXIT_POLICY_ERROR
    assert "Failed to parse policy file" in caplog.text


def test_cli_error_handler_reports_all_validation_errors(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        _OuterModel.model_validate({"inner": {"enabled": "invalid"}})

    assert _handle(exc_info.value).exit_code == EXIT_POLICY_ERROR
    assert caplog.records[0].levelname == "ERROR"
    assert "Policy validation failed" in caplog.text
    # The location of the invalid value is included
    assert "inner.enabled: " in caplog.text


def test_cli_error_handler_reports_condition_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    error = ConditionEvaluationError("Test condition failed")

    assert _handle(error).exit_code == EXIT_RUNTIME_ERROR
    assert "Failed to evaluate condition: Test condition failed" in caplog.text


def test_cli_error_handler_reports_action_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    error = ActionExecutionError("Test action failed")

    assert _handle(error).exit_code == EXIT_RUNTIME_ERROR
    assert "Failed to execute action: Test action failed" in caplog.text


def test_cli_error_handler_reports_value_error_as_it_is(
    caplog: pytest.LogCaptureFixture,
) -> None:
    assert _handle(ValueError("Test value problem")).exit_code == EXIT_RUNTIME_ERROR
    assert caplog.records[-1].getMessage() == "Test value problem"


def test_cli_error_handler_reports_unexpected_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    assert _handle(RuntimeError("Test failure")).exit_code == EXIT_RUNTIME_ERROR
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
