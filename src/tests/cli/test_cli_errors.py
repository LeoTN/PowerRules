import pytest
import typer
from pydantic import ValidationError

from powerrules.cli.errors import (
    EXIT_POLICY_ERROR,
    EXIT_RUNTIME_ERROR,
    cli_command,
    handle_cli_error,
)
from powerrules.engine.exceptions import ConditionEvaluationError
from tests.dummies import Dummy_Model


def test_cli_error_handler_handles_missing_policy() -> None:
    error = FileNotFoundError(2, "File not found", "policy.yaml")

    with pytest.raises(typer.Exit) as exc_info:
        handle_cli_error(error)

    assert exc_info.value.exit_code == EXIT_POLICY_ERROR


def test_cli_error_handler_reports_missing_policy(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("DEBUG")
    error = FileNotFoundError(2, "File not found", "policy.yaml")

    with pytest.raises(typer.Exit):
        handle_cli_error(error)

    assert caplog.records[-1].levelname == "ERROR"
    assert "Policy file not found: policy.yaml" in caplog.text


def test_cli_error_handler_handles_validation_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("DEBUG")

    with pytest.raises(ValidationError) as exc_info:
        Dummy_Model.model_validate({"enabled": "invalid"})

    with pytest.raises(typer.Exit) as exit_info:
        handle_cli_error(exc_info.value)

    assert exit_info.value.exit_code == EXIT_POLICY_ERROR
    assert caplog.records[0].levelname == "ERROR"
    assert "Policy validation failed" in caplog.text
    assert "enabled" in caplog.text


def test_cli_error_handler_handles_condition_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("DEBUG")
    error = ConditionEvaluationError("Test condition failed")

    with pytest.raises(typer.Exit) as exc_info:
        handle_cli_error(error)

    assert exc_info.value.exit_code == EXIT_RUNTIME_ERROR
    # The message is wrapped by "handle_cli_error()"
    assert "Failed to evaluate condition: Test condition failed" in caplog.text


def test_cli_command_handles_command_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("DEBUG")

    @cli_command
    def failing_command() -> None:
        raise ConditionEvaluationError("Test condition failed")

    with pytest.raises(typer.Exit) as exc_info:
        failing_command()

    assert exc_info.value.exit_code == EXIT_RUNTIME_ERROR
    # The message is wrapped by "handle_cli_error()"
    assert "Failed to evaluate condition: Test condition failed" in caplog.text


def test_cli_command_does_not_intercept_typer_exit() -> None:
    @cli_command
    def exiting_command() -> None:
        raise typer.Exit(code=42)

    with pytest.raises(typer.Exit) as exc_info:
        exiting_command()

    assert exc_info.value.exit_code == 42
