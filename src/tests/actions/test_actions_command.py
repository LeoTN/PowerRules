import logging
from collections.abc import Collection, Mapping
from pathlib import Path
from unittest.mock import Mock

import pytest

from powerrules.actions.command import (
    ACTION_NAME_ENVIRONMENT_VARIABLE,
    DEFAULT_ACTION_TIMEOUT_SECONDS,
    RULE_NAME_ENVIRONMENT_VARIABLE,
    CommandAction,
)
from powerrules.engine.exceptions import ActionExecutionError
from powerrules.providers.command import CommandRequest, CommandResult, Shell
from tests.mocks import make_command_provider

LOGGER_NAME = "powerrules.actions.command"
WORKING_DIRECTORY = Path("work")

# Failing outcomes of the command provider and the message of the resulting error
FAILURE_CASES = [
    pytest.param(
        CommandResult(exit_code=1),
        None,
        "Action 'Test action' returned exit code 1, expected one of: 0",
        id="exit-code",
    ),
    pytest.param(
        None,
        TimeoutError("Test timeout"),
        "Action 'Test action' timed out after 5 seconds",
        id="timeout",
    ),
    pytest.param(
        None,
        FileNotFoundError("Test shell missing"),
        "Action 'Test action' could not be started: Test shell missing",
        id="not-started",
    ),
]


def _make_action(
    command_provider: Mock,
    *,
    command: str = "echo test",
    shell: Shell | None = None,
    environment: Mapping[str, str] | None = None,
    timeout: float | None = DEFAULT_ACTION_TIMEOUT_SECONDS,
    success_exit_codes: Collection[int] = (0,),
    wait: bool = True,
    continue_on_error: bool = False,
) -> CommandAction:
    """Create an action with fixed names and the given options."""
    return CommandAction(
        command_provider,
        command,
        WORKING_DIRECTORY,
        name="Test action",
        rule_name="Test rule",
        shell=shell,
        environment=environment,
        timeout=timeout,
        success_exit_codes=success_exit_codes,
        wait=wait,
        continue_on_error=continue_on_error,
    )


def _get_logged(caplog: pytest.LogCaptureFixture) -> list[tuple[int, str]]:
    """Return level and message of all records which were logged by the action."""
    return [
        (record.levelno, record.getMessage())
        for record in caplog.records
        if record.name == LOGGER_NAME
    ]


###############
# Request tests
###############


def test_command_action_runs_command_with_default_request() -> None:
    command_provider = make_command_provider()

    _make_action(command_provider).execute()

    command_provider.run.assert_called_once_with(
        CommandRequest(
            command="echo test",
            working_directory=WORKING_DIRECTORY,
            environment={
                RULE_NAME_ENVIRONMENT_VARIABLE: "Test rule",
                ACTION_NAME_ENVIRONMENT_VARIABLE: "Test action",
            },
            timeout=DEFAULT_ACTION_TIMEOUT_SECONDS,
            wait=True,
            shell=None,
        )
    )


@pytest.mark.parametrize(
    ("shell", "timeout"),
    [
        (Shell.BASH, 5),
        (Shell.POWERSHELL, 2.5),
        (Shell.CMD, None),
    ],
)
def test_command_action_passes_shell_and_timeout_to_provider(
    shell: Shell,
    timeout: float | None,
) -> None:
    command_provider = make_command_provider()

    _make_action(command_provider, shell=shell, timeout=timeout).execute()

    request = command_provider.run.call_args.args[0]
    assert request.shell is shell
    assert request.timeout == timeout


def test_command_action_adds_configured_environment_to_request() -> None:
    command_provider = make_command_provider()

    _make_action(command_provider, environment={"CUSTOM": "value"}).execute()

    assert command_provider.run.call_args.args[0].environment == {
        "CUSTOM": "value",
        RULE_NAME_ENVIRONMENT_VARIABLE: "Test rule",
        ACTION_NAME_ENVIRONMENT_VARIABLE: "Test action",
    }


# The configuration forbids the reserved prefix, but the action must not depend on that
def test_command_action_overrides_reserved_environment_variables() -> None:
    command_provider = make_command_provider()

    _make_action(
        command_provider,
        environment={
            RULE_NAME_ENVIRONMENT_VARIABLE: "Spoofed rule",
            ACTION_NAME_ENVIRONMENT_VARIABLE: "Spoofed action",
        },
    ).execute()

    assert command_provider.run.call_args.args[0].environment == {
        RULE_NAME_ENVIRONMENT_VARIABLE: "Test rule",
        ACTION_NAME_ENVIRONMENT_VARIABLE: "Test action",
    }


def test_command_action_copies_environment_and_exit_codes() -> None:
    environment = {"CUSTOM": "value"}
    command_provider = make_command_provider()

    action = _make_action(
        command_provider, environment=environment, success_exit_codes=[0, 0, 3]
    )
    environment["CUSTOM"] = "changed"

    action.execute()

    assert action.name == "Test action"
    assert action.success_exit_codes == frozenset({0, 3})
    assert command_provider.run.call_args.args[0].environment["CUSTOM"] == "value"


##################
# Exit code tests
##################


@pytest.mark.parametrize(
    ("exit_code", "success_exit_codes"),
    [
        (0, (0,)),
        (3, (0, 3)),
        (3, (3,)),
        (-1, (-1,)),
    ],
)
def test_command_action_accepts_success_exit_codes(
    exit_code: int,
    success_exit_codes: tuple[int, ...],
) -> None:
    command_provider = make_command_provider(CommandResult(exit_code=exit_code))

    _make_action(command_provider, success_exit_codes=success_exit_codes).execute()

    command_provider.run.assert_called_once()


@pytest.mark.parametrize(
    ("exit_code", "success_exit_codes"),
    [
        (1, (0,)),
        (0, (1,)),
        (4, (0, 3)),
        # No exit code at all is never a success for a command which is waited for
        (None, (0,)),
    ],
)
def test_command_action_rejects_other_exit_codes(
    exit_code: int | None,
    success_exit_codes: tuple[int, ...],
) -> None:
    command_provider = make_command_provider(CommandResult(exit_code=exit_code))
    action = _make_action(command_provider, success_exit_codes=success_exit_codes)

    with pytest.raises(ActionExecutionError, match="returned exit code"):
        action.execute()


def test_command_action_lists_sorted_success_exit_codes_in_error() -> None:
    command_provider = make_command_provider(CommandResult(exit_code=2))
    action = _make_action(command_provider, success_exit_codes=(3, 0))

    with pytest.raises(ActionExecutionError) as exc_info:
        action.execute()

    assert str(exc_info.value) == (
        "Action 'Test action' returned exit code 2, expected one of: 0, 3"
    )


#######################
# Error handling tests
#######################


@pytest.mark.parametrize(("result", "error", "message"), FAILURE_CASES)
def test_command_action_raises_action_execution_error(
    result: CommandResult | None,
    error: Exception | None,
    message: str,
) -> None:
    action = _make_action(make_command_provider(result, error), timeout=5)

    with pytest.raises(ActionExecutionError) as exc_info:
        action.execute()

    assert str(exc_info.value) == message


@pytest.mark.parametrize(
    "error",
    [TimeoutError("Test timeout"), PermissionError("Test permission")],
)
def test_command_action_chains_original_error(error: OSError) -> None:
    action = _make_action(make_command_provider(error=error), timeout=5)

    with pytest.raises(ActionExecutionError) as exc_info:
        action.execute()

    assert exc_info.value.__cause__ is error


# TimeoutError is a subclass of OSError and must not be reported as a start failure
def test_command_action_reports_timeout_before_start_failure() -> None:
    action = _make_action(make_command_provider(error=TimeoutError()), timeout=5)

    with pytest.raises(ActionExecutionError, match="timed out"):
        action.execute()


def test_command_action_does_not_wrap_unexpected_errors() -> None:
    action = _make_action(make_command_provider(error=RuntimeError("Test failure")))

    with pytest.raises(RuntimeError, match="Test failure"):
        action.execute()


@pytest.mark.parametrize(("result", "error", "message"), FAILURE_CASES)
def test_command_action_continues_on_error_when_configured(
    caplog: pytest.LogCaptureFixture,
    result: CommandResult | None,
    error: Exception | None,
    message: str,
) -> None:
    action = _make_action(
        make_command_provider(result, error),
        timeout=5,
        continue_on_error=True,
    )

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        action.execute()

    assert (
        logging.WARNING,
        f"{message} (continue_on_error is set, continuing with the remaining actions)",
    ) in _get_logged(caplog)


######################
# Background run tests
######################


def test_command_action_does_not_check_result_when_not_waiting(
    caplog: pytest.LogCaptureFixture,
) -> None:
    command_provider = make_command_provider(CommandResult(exit_code=None))
    action = _make_action(command_provider, wait=False, success_exit_codes=(5,))

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        action.execute()

    assert command_provider.run.call_args.args[0].wait is False
    assert (
        logging.INFO,
        "Started action 'Test action' in the background",
    ) in _get_logged(caplog)


def test_command_action_reports_start_failure_when_not_waiting() -> None:
    action = _make_action(
        make_command_provider(error=FileNotFoundError("Test shell missing")),
        wait=False,
    )

    with pytest.raises(ActionExecutionError, match="could not be started"):
        action.execute()


###############
# Logging tests
###############


def test_command_action_logs_start_and_finish_on_info_level(
    caplog: pytest.LogCaptureFixture,
) -> None:
    action = _make_action(make_command_provider(CommandResult(exit_code=0)))

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        action.execute()

    assert _get_logged(caplog) == [
        (logging.INFO, "Running action 'Test action'"),
        (logging.INFO, "Action 'Test action' finished with exit code 0"),
    ]


def test_command_action_logs_command_only_on_debug_level(
    caplog: pytest.LogCaptureFixture,
) -> None:
    action = _make_action(make_command_provider(), command="  echo secret  ")

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        action.execute()

    assert "secret" not in caplog.text

    caplog.clear()

    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        action.execute()

    assert (
        logging.DEBUG,
        "Command of action 'Test action': echo secret",
    ) in _get_logged(caplog)


def test_command_action_logs_output_on_debug_level_after_success(
    caplog: pytest.LogCaptureFixture,
) -> None:
    action = _make_action(
        make_command_provider(
            CommandResult(exit_code=0, stdout=" out \n", stderr=" err\n")
        )
    )

    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        action.execute()

    logged = _get_logged(caplog)
    assert (logging.DEBUG, "Output of action 'Test action' (stdout):\nout") in logged
    assert (logging.DEBUG, "Output of action 'Test action' (stderr):\nerr") in logged
    assert not any(level >= logging.WARNING for level, _ in logged)


def test_command_action_logs_error_output_as_error_after_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    action = _make_action(
        make_command_provider(
            CommandResult(exit_code=1, stdout="out\n", stderr="err\n")
        )
    )

    with (
        caplog.at_level(logging.DEBUG, logger=LOGGER_NAME),
        pytest.raises(ActionExecutionError),
    ):
        action.execute()

    logged = _get_logged(caplog)
    assert (logging.DEBUG, "Output of action 'Test action' (stdout):\nout") in logged
    assert (logging.ERROR, "Output of action 'Test action' (stderr):\nerr") in logged


def test_command_action_does_not_log_empty_output(
    caplog: pytest.LogCaptureFixture,
) -> None:
    action = _make_action(
        make_command_provider(CommandResult(exit_code=0, stdout="  \n", stderr=""))
    )

    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        action.execute()

    assert "Output of action" not in caplog.text
