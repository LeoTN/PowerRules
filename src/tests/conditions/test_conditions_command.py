import logging
from pathlib import Path

import pytest

from powerrules.actions.command import (
    ACTION_NAME_ENVIRONMENT_VARIABLE,
    DEFAULT_COMMAND_TIMEOUT_SECONDS,
    RULE_NAME_ENVIRONMENT_VARIABLE,
)
from powerrules.conditions.matcher import MatchType, StringMatcher
from powerrules.engine.exceptions import (
    ConditionEvaluationError,
    ConditionEvaluationProviderNotAvailableError,
    FileIntegrityError,
)
from powerrules.providers.command import CommandRequest, CommandResult, Shell
from tests.factories import (
    make_command_condition,
    make_command_provider,
    make_files_verifier,
)
from tests.helpers import (
    BACKUP_SCRIPT_NAME,
    DEFAULT_WORKING_DIRECTORY,
    SCRIPT_DIRECTORY_NAME,
    get_log_entries,
)

LOGGER_NAME = "powerrules.conditions.command"
TRUSTED_FILES = (Path(SCRIPT_DIRECTORY_NAME) / BACKUP_SCRIPT_NAME,)

################
# Matching tests
################


def test_command_condition_matches_if_command_succeeds() -> None:
    condition = make_command_condition(
        make_command_provider(CommandResult(exit_code=0))
    )

    assert condition.evaluate() is True


@pytest.mark.parametrize(
    ("exit_code", "success_exit_codes", "expected"),
    [
        (0, (0,), True),
        (3, (0, 3), True),
        (1, (0,), False),
        (0, (3,), False),
        (None, (0,), False),
    ],
)
def test_command_condition_compares_exit_code(
    exit_code: int | None,
    success_exit_codes: tuple[int, ...],
    expected: bool,
) -> None:
    condition = make_command_condition(
        make_command_provider(CommandResult(exit_code=exit_code)),
        success_exit_codes=success_exit_codes,
    )

    assert condition.evaluate() is expected


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (CommandResult(exit_code=0, stdout="  active\n"), True),
        (CommandResult(exit_code=0, stdout="inactive"), False),
        (CommandResult(exit_code=1, stdout="active"), False),
    ],
)
def test_command_condition_compares_stdout(
    result: CommandResult, expected: bool
) -> None:
    condition = make_command_condition(
        make_command_provider(result), stdout_matcher=StringMatcher("active")
    )

    assert condition.evaluate() is expected


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (CommandResult(exit_code=0, stderr="Some Warning\n"), True),
        (CommandResult(exit_code=0, stderr="other"), False),
        (CommandResult(exit_code=0), False),
    ],
)
def test_command_condition_compares_stderr(
    result: CommandResult, expected: bool
) -> None:
    condition = make_command_condition(
        make_command_provider(result),
        stderr_matcher=StringMatcher("warning", MatchType.CONTAINS, False),
    )

    assert condition.evaluate() is expected


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (CommandResult(exit_code=0, stdout="ok", stderr="fine"), True),
        (CommandResult(exit_code=1, stdout="ok", stderr="fine"), False),
        (CommandResult(exit_code=0, stdout="no", stderr="fine"), False),
        (CommandResult(exit_code=0, stdout="ok", stderr="bad"), False),
    ],
)
def test_command_condition_requires_all_criteria_to_match(
    result: CommandResult, expected: bool
) -> None:
    condition = make_command_condition(
        make_command_provider(result),
        stdout_matcher=StringMatcher("ok"),
        stderr_matcher=StringMatcher("fine"),
    )

    assert condition.evaluate() is expected


###############
# Request tests
###############


def test_command_condition_runs_command_with_default_request() -> None:
    command_provider = make_command_provider()

    make_command_condition(command_provider).evaluate()

    command_provider.run.assert_called_once_with(
        CommandRequest(
            command="echo test",
            working_directory=DEFAULT_WORKING_DIRECTORY,
            environment={},
            timeout=DEFAULT_COMMAND_TIMEOUT_SECONDS,
            wait=True,
            shell=None,
        )
    )


def test_command_condition_passes_options_to_provider() -> None:
    command_provider = make_command_provider()

    make_command_condition(
        command_provider,
        shell=Shell.BASH,
        timeout=2.5,
        environment={"CUSTOM": "value"},
    ).evaluate()

    request = command_provider.run.call_args.args[0]

    assert request.shell is Shell.BASH
    assert request.timeout == 2.5
    assert request.environment == {"CUSTOM": "value"}


def test_command_condition_does_not_set_variables_of_actions() -> None:
    command_provider = make_command_provider()

    make_command_condition(command_provider).evaluate()

    environment = command_provider.run.call_args.args[0].environment

    assert RULE_NAME_ENVIRONMENT_VARIABLE not in environment
    assert ACTION_NAME_ENVIRONMENT_VARIABLE not in environment


# The command may return something else each time, so every evaluation has to run it again
def test_command_condition_runs_command_on_every_evaluation() -> None:
    command_provider = make_command_provider()
    condition = make_command_condition(command_provider)

    assert condition.evaluate() is True

    command_provider.run.return_value = CommandResult(exit_code=1)

    assert condition.evaluate() is False
    assert command_provider.run.call_count == 2


######################
# Error handling tests
######################


def test_command_condition_raises_evaluation_error_on_timeout() -> None:
    original_error = TimeoutError("Test timeout")
    condition = make_command_condition(
        make_command_provider(error=original_error), timeout=5
    )

    with pytest.raises(ConditionEvaluationError) as exc_info:
        condition.evaluate()

    assert str(exc_info.value) == (
        f"Command condition of rule '{condition.rule_name}' timed out after 5 seconds"
    )
    assert exc_info.value.__cause__ is original_error
    # A failed command is not the same as an unavailable provider
    assert not isinstance(exc_info.value, ConditionEvaluationProviderNotAvailableError)


@pytest.mark.parametrize(
    "error",
    [
        FileNotFoundError("Test shell missing"),
        PermissionError("Test permission"),
        NotADirectoryError("Test directory"),
    ],
)
def test_command_condition_raises_evaluation_error_if_command_cannot_be_started(
    error: OSError,
) -> None:
    condition = make_command_condition(make_command_provider(error=error))

    with pytest.raises(ConditionEvaluationError) as exc_info:
        condition.evaluate()

    assert str(exc_info.value) == (
        f"Command condition of rule '{condition.rule_name}' could not be started: {error}"
    )
    assert exc_info.value.__cause__ is error


def test_command_condition_does_not_wrap_unexpected_errors() -> None:
    condition = make_command_condition(
        make_command_provider(error=RuntimeError("Test failure"))
    )

    with pytest.raises(RuntimeError, match="Test failure"):
        condition.evaluate()


#####################
# Trusted files tests
#####################


def test_command_condition_verifies_trusted_files_before_running_the_command() -> None:
    calls: list[str] = []
    command_provider = make_command_provider()

    def run(_request: CommandRequest) -> CommandResult:
        calls.append("run")

        return CommandResult(exit_code=0)

    command_provider.run.side_effect = run
    files_verifier = make_files_verifier()
    files_verifier.side_effect = lambda _files: calls.append("verify")

    make_command_condition(
        command_provider, trusted_files=TRUSTED_FILES, files_verifier=files_verifier
    ).evaluate()

    assert calls == ["verify", "run"]
    files_verifier.assert_called_once_with(TRUSTED_FILES)


def test_command_condition_verifies_trusted_files_on_every_evaluation() -> None:
    files_verifier = make_files_verifier()
    condition = make_command_condition(
        trusted_files=TRUSTED_FILES, files_verifier=files_verifier
    )

    condition.evaluate()
    condition.evaluate()

    assert files_verifier.call_count == 2


# A file which was modified is no problem of the evaluation, it must never be hidden by it
def test_command_condition_does_not_wrap_failed_file_verification() -> None:
    command_provider = make_command_provider()
    error = FileIntegrityError("Test file was modified")
    condition = make_command_condition(
        command_provider,
        trusted_files=TRUSTED_FILES,
        files_verifier=make_files_verifier(error=error),
    )

    with pytest.raises(FileIntegrityError) as exc_info:
        condition.evaluate()

    assert exc_info.value is error
    assert not isinstance(exc_info.value, ConditionEvaluationError)
    command_provider.run.assert_not_called()


###############
# Logging tests
###############


def test_command_condition_logs_command_only_on_debug_level(
    caplog: pytest.LogCaptureFixture,
) -> None:
    condition = make_command_condition(command="  echo secret  ")

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        condition.evaluate()

    assert "secret" not in caplog.text

    caplog.clear()

    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        condition.evaluate()

    assert (
        logging.DEBUG,
        f"Command of command condition of rule '{condition.rule_name}': echo secret",
    ) in get_log_entries(caplog, LOGGER_NAME)


def test_command_condition_logs_output_only_on_debug_level(
    caplog: pytest.LogCaptureFixture,
) -> None:
    condition = make_command_condition(
        make_command_provider(
            CommandResult(exit_code=0, stdout=" out \n", stderr=" err\n")
        )
    )

    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        condition.evaluate()

    logged = get_log_entries(caplog, LOGGER_NAME)

    assert (
        logging.DEBUG,
        f"Output of command condition of rule '{condition.rule_name}' (stdout):\nout",
    ) in logged
    assert (
        logging.DEBUG,
        f"Output of command condition of rule '{condition.rule_name}' (stderr):\nerr",
    ) in logged
    assert all(level == logging.DEBUG for level, _ in logged)


# A condition which does not match is no failure, so nothing is logged as an error
def test_command_condition_does_not_log_errors_if_it_does_not_match(
    caplog: pytest.LogCaptureFixture,
) -> None:
    condition = make_command_condition(
        make_command_provider(CommandResult(exit_code=1, stdout="no", stderr="err")),
        stdout_matcher=StringMatcher("yes"),
    )

    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        assert condition.evaluate() is False

    assert not any(
        level >= logging.INFO for level, _ in get_log_entries(caplog, LOGGER_NAME)
    )


def test_command_condition_does_not_log_empty_output(
    caplog: pytest.LogCaptureFixture,
) -> None:
    condition = make_command_condition(
        make_command_provider(CommandResult(exit_code=0, stdout="  \n", stderr=""))
    )

    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        condition.evaluate()

    assert "Output of command condition" not in caplog.text
