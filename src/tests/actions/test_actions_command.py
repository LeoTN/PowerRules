import logging
from pathlib import Path

import pytest

from powerrules.actions.command import (
    ACTION_NAME_ENVIRONMENT_VARIABLE,
    DEFAULT_ACTION_TIMEOUT_SECONDS,
    RULE_NAME_ENVIRONMENT_VARIABLE,
)
from powerrules.conditions.matcher import MatchType, StringMatcher
from powerrules.engine.exceptions import ActionExecutionError, FileIntegrityError
from powerrules.providers.command import CommandRequest, CommandResult, Shell
from tests.factories import (
    make_command_action,
    make_command_provider,
    make_files_verifier,
)
from tests.helpers import (
    BACKUP_SCRIPT_NAME,
    DEFAULT_WORKING_DIRECTORY,
    SCRIPT_DIRECTORY_NAME,
    get_log_entries,
)

LOGGER_NAME = "powerrules.actions.command"

# Failing outcomes of the command provider and the message of the resulting error
FAILURE_CASES = [
    pytest.param(
        CommandResult(exit_code=1),
        None,
        "Action 'Test action' returned exit code 1, expected one of: 0",
        id="exit-code",
    ),
    # TimeoutError is a subclass of OSError and must not be reported as a start failure
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

TRUSTED_FILES = (Path(SCRIPT_DIRECTORY_NAME) / BACKUP_SCRIPT_NAME,)

###############
# Request tests
###############


def test_command_action_runs_command_with_default_request() -> None:
    command_provider = make_command_provider()

    make_command_action(command_provider).execute()

    command_provider.run.assert_called_once_with(
        CommandRequest(
            command="echo test",
            working_directory=DEFAULT_WORKING_DIRECTORY,
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

    make_command_action(command_provider, shell=shell, timeout=timeout).execute()

    request = command_provider.run.call_args.args[0]
    assert request.shell is shell
    assert request.timeout == timeout


def test_command_action_adds_configured_environment_to_request() -> None:
    command_provider = make_command_provider()

    make_command_action(command_provider, environment={"CUSTOM": "value"}).execute()

    assert command_provider.run.call_args.args[0].environment == {
        "CUSTOM": "value",
        RULE_NAME_ENVIRONMENT_VARIABLE: "Test rule",
        ACTION_NAME_ENVIRONMENT_VARIABLE: "Test action",
    }


# The configuration forbids the reserved prefix, but the action must not depend on that
def test_command_action_overrides_reserved_environment_variables() -> None:
    command_provider = make_command_provider()

    make_command_action(
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

    action = make_command_action(
        command_provider, environment=environment, success_exit_codes=[0, 0, 3]
    )
    environment["CUSTOM"] = "changed"

    action.execute()

    assert action.name == "Test action"
    assert action.success_exit_codes == frozenset({0, 3})
    assert command_provider.run.call_args.args[0].environment["CUSTOM"] == "value"


#################
# Exit code tests
#################


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

    make_command_action(
        command_provider, success_exit_codes=success_exit_codes
    ).execute()

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
    action = make_command_action(
        command_provider, success_exit_codes=success_exit_codes
    )

    with pytest.raises(ActionExecutionError, match="returned exit code"):
        action.execute()


def test_command_action_lists_sorted_success_exit_codes_in_error() -> None:
    command_provider = make_command_provider(CommandResult(exit_code=2))
    action = make_command_action(command_provider, success_exit_codes=(3, 0))

    with pytest.raises(ActionExecutionError) as exc_info:
        action.execute()

    assert str(exc_info.value) == (
        "Action 'Test action' returned exit code 2, expected one of: 0, 3"
    )


##########################
# Output expectation tests
##########################


def test_command_action_accepts_expected_output() -> None:
    command_provider = make_command_provider(
        CommandResult(exit_code=0, stdout="  active\n", stderr="a warning\n")
    )
    action = make_command_action(
        command_provider,
        stdout_matcher=StringMatcher("active"),
        stderr_matcher=StringMatcher("warning", MatchType.CONTAINS),
    )

    # The output is stripped before it is compared
    action.execute()

    command_provider.run.assert_called_once()


@pytest.mark.parametrize(
    ("stream", "result"),
    [
        ("stdout", CommandResult(exit_code=0, stdout="inactive secret\n")),
        ("stderr", CommandResult(exit_code=0, stderr="inactive secret\n")),
    ],
)
def test_command_action_rejects_unexpected_output(
    stream: str,
    result: CommandResult,
) -> None:
    action = make_command_action(
        make_command_provider(result),
        stdout_matcher=StringMatcher("active") if stream == "stdout" else None,
        stderr_matcher=StringMatcher("active") if stream == "stderr" else None,
    )

    with pytest.raises(ActionExecutionError) as exc_info:
        action.execute()

    # The message names the stream, but never the output which might contain secrets
    assert str(exc_info.value) == (
        f"Action 'Test action' produced an unexpected output on {stream}"
    )
    assert "secret" not in str(exc_info.value)


def test_command_action_reports_exit_code_before_unexpected_output() -> None:
    action = make_command_action(
        make_command_provider(CommandResult(exit_code=1, stdout="inactive")),
        stdout_matcher=StringMatcher("active"),
    )

    with pytest.raises(ActionExecutionError, match="returned exit code 1"):
        action.execute()


def test_command_action_continues_on_unexpected_output_when_configured(
    caplog: pytest.LogCaptureFixture,
) -> None:
    action = make_command_action(
        make_command_provider(CommandResult(exit_code=0, stdout="inactive")),
        stdout_matcher=StringMatcher("active"),
        continue_on_error=True,
    )

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        action.execute()

    assert (
        logging.WARNING,
        "Action 'Test action' produced an unexpected output on stdout (continue_on_error is set, continuing with the remaining actions)",
    ) in get_log_entries(caplog, LOGGER_NAME)


def test_command_action_logs_error_output_as_error_after_unexpected_output(
    caplog: pytest.LogCaptureFixture,
) -> None:
    action = make_command_action(
        make_command_provider(
            CommandResult(exit_code=0, stdout="inactive", stderr="err\n")
        ),
        stdout_matcher=StringMatcher("active"),
    )

    with (
        caplog.at_level(logging.DEBUG, logger=LOGGER_NAME),
        pytest.raises(ActionExecutionError),
    ):
        action.execute()

    assert (
        logging.ERROR,
        "Output of action 'Test action' (stderr):\nerr",
    ) in get_log_entries(caplog, LOGGER_NAME)


def test_command_action_does_not_compare_output_when_not_waiting() -> None:
    command_provider = make_command_provider(CommandResult(exit_code=None))
    action = make_command_action(
        command_provider,
        wait=False,
        stdout_matcher=StringMatcher("active"),
        stderr_matcher=StringMatcher("active"),
    )

    action.execute()

    command_provider.run.assert_called_once()


######################
# Error handling tests
######################


@pytest.mark.parametrize(("result", "error", "message"), FAILURE_CASES)
def test_command_action_raises_action_execution_error(
    result: CommandResult | None,
    error: Exception | None,
    message: str,
) -> None:
    action = make_command_action(make_command_provider(result, error=error), timeout=5)

    with pytest.raises(ActionExecutionError) as exc_info:
        action.execute()

    assert str(exc_info.value) == message


@pytest.mark.parametrize(
    "error",
    [TimeoutError("Test timeout"), PermissionError("Test permission")],
)
def test_command_action_chains_original_error(error: OSError) -> None:
    action = make_command_action(make_command_provider(error=error), timeout=5)

    with pytest.raises(ActionExecutionError) as exc_info:
        action.execute()

    assert exc_info.value.__cause__ is error


def test_command_action_does_not_wrap_unexpected_errors() -> None:
    action = make_command_action(
        make_command_provider(error=RuntimeError("Test failure"))
    )

    with pytest.raises(RuntimeError, match="Test failure"):
        action.execute()


@pytest.mark.parametrize(("result", "error", "message"), FAILURE_CASES)
def test_command_action_continues_on_error_when_configured(
    caplog: pytest.LogCaptureFixture,
    result: CommandResult | None,
    error: Exception | None,
    message: str,
) -> None:
    action = make_command_action(
        make_command_provider(result, error=error),
        timeout=5,
        continue_on_error=True,
    )

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        action.execute()

    assert (
        logging.WARNING,
        f"{message} (continue_on_error is set, continuing with the remaining actions)",
    ) in get_log_entries(caplog, LOGGER_NAME)


######################
# Background run tests
######################


def test_command_action_does_not_check_result_when_not_waiting(
    caplog: pytest.LogCaptureFixture,
) -> None:
    command_provider = make_command_provider(CommandResult(exit_code=None))
    action = make_command_action(command_provider, wait=False, success_exit_codes=(5,))

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        action.execute()

    assert command_provider.run.call_args.args[0].wait is False
    assert (
        logging.INFO,
        "Started action 'Test action' in the background",
    ) in get_log_entries(caplog, LOGGER_NAME)


def test_command_action_reports_start_failure_when_not_waiting() -> None:
    action = make_command_action(
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
    action = make_command_action(make_command_provider(CommandResult(exit_code=0)))

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        action.execute()

    assert get_log_entries(caplog, LOGGER_NAME) == [
        (logging.INFO, "Running action 'Test action'"),
        (logging.INFO, "Action 'Test action' finished with exit code 0"),
    ]


def test_command_action_logs_command_only_on_debug_level(
    caplog: pytest.LogCaptureFixture,
) -> None:
    action = make_command_action(command="  echo secret  ")

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        action.execute()

    assert "secret" not in caplog.text

    caplog.clear()

    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        action.execute()

    assert (
        logging.DEBUG,
        "Command of action 'Test action': echo secret",
    ) in get_log_entries(caplog, LOGGER_NAME)


def test_command_action_logs_output_on_debug_level_after_success(
    caplog: pytest.LogCaptureFixture,
) -> None:
    action = make_command_action(
        make_command_provider(
            CommandResult(exit_code=0, stdout=" out \n", stderr=" err\n")
        )
    )

    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        action.execute()

    logged = get_log_entries(caplog, LOGGER_NAME)
    assert (logging.DEBUG, "Output of action 'Test action' (stdout):\nout") in logged
    assert (logging.DEBUG, "Output of action 'Test action' (stderr):\nerr") in logged
    assert not any(level >= logging.WARNING for level, _ in logged)


def test_command_action_logs_error_output_as_error_after_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    action = make_command_action(
        make_command_provider(
            CommandResult(exit_code=1, stdout="out\n", stderr="err\n")
        )
    )

    with (
        caplog.at_level(logging.DEBUG, logger=LOGGER_NAME),
        pytest.raises(ActionExecutionError),
    ):
        action.execute()

    logged = get_log_entries(caplog, LOGGER_NAME)
    assert (logging.DEBUG, "Output of action 'Test action' (stdout):\nout") in logged
    assert (logging.ERROR, "Output of action 'Test action' (stderr):\nerr") in logged


def test_command_action_does_not_log_empty_output(
    caplog: pytest.LogCaptureFixture,
) -> None:
    action = make_command_action(
        make_command_provider(CommandResult(exit_code=0, stdout="  \n", stderr=""))
    )

    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        action.execute()

    assert "Output of action" not in caplog.text


#####################
# Trusted files tests
#####################


def test_command_action_verifies_trusted_files_before_running_the_command() -> None:
    calls: list[str] = []
    command_provider = make_command_provider()

    def run(_request: CommandRequest) -> CommandResult:
        calls.append("run")

        return CommandResult(exit_code=0)

    command_provider.run.side_effect = run
    files_verifier = make_files_verifier()
    files_verifier.side_effect = lambda _files: calls.append("verify")

    make_command_action(
        command_provider, trusted_files=TRUSTED_FILES, files_verifier=files_verifier
    ).execute()

    assert calls == ["verify", "run"]
    files_verifier.assert_called_once_with(TRUSTED_FILES)


def test_command_action_verifies_trusted_files_on_every_execution() -> None:
    files_verifier = make_files_verifier()
    action = make_command_action(
        trusted_files=TRUSTED_FILES, files_verifier=files_verifier
    )

    action.execute()
    action.execute()

    assert files_verifier.call_count == 2


def test_command_action_stores_trusted_files_as_tuple() -> None:
    action = make_command_action(trusted_files=[Path("a.sh"), Path("b.sh")])

    assert action.trusted_files == (Path("a.sh"), Path("b.sh"))


def test_command_action_does_not_verify_without_trusted_files() -> None:
    files_verifier = make_files_verifier()
    command_provider = make_command_provider()

    make_command_action(command_provider, files_verifier=files_verifier).execute()

    files_verifier.assert_not_called()
    command_provider.run.assert_called_once()


def test_command_action_runs_without_verifier() -> None:
    command_provider = make_command_provider()

    make_command_action(command_provider, trusted_files=TRUSTED_FILES).execute()

    command_provider.run.assert_called_once()


# "continue_on_error" must never skip a failed integrity check
@pytest.mark.parametrize("continue_on_error", [False, True])
def test_command_action_does_not_run_command_when_verification_fails(
    continue_on_error: bool,
) -> None:
    command_provider = make_command_provider()
    action = make_command_action(
        command_provider,
        trusted_files=TRUSTED_FILES,
        files_verifier=make_files_verifier(
            error=FileIntegrityError("Test file was modified")
        ),
        continue_on_error=continue_on_error,
    )

    with pytest.raises(FileIntegrityError, match="Test file was modified"):
        action.execute()

    command_provider.run.assert_not_called()


def test_command_action_still_continues_on_command_error_after_verification() -> None:
    files_verifier = make_files_verifier()
    action = make_command_action(
        make_command_provider(CommandResult(exit_code=1)),
        trusted_files=TRUSTED_FILES,
        files_verifier=files_verifier,
        continue_on_error=True,
    )

    action.execute()

    files_verifier.assert_called_once()


def test_failed_command_after_verification_is_an_action_execution_error() -> None:
    action = make_command_action(
        make_command_provider(CommandResult(exit_code=1)),
        trusted_files=TRUSTED_FILES,
        files_verifier=make_files_verifier(),
    )

    with pytest.raises(ActionExecutionError):
        action.execute()
