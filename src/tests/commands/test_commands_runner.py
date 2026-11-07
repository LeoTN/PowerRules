import itertools
from pathlib import Path

import pytest

from powerrules.commands.runner import CommandRunnerResult
from powerrules.conditions.matcher import MatchType, StringMatcher
from powerrules.engine.exceptions import FileIntegrityError
from powerrules.providers.command import CommandRequest, CommandResult, Shell
from tests.factories import (
    make_command_provider,
    make_command_runner,
    make_files_verifier,
)
from tests.helpers import (
    BACKUP_SCRIPT_NAME,
    DEFAULT_WORKING_DIRECTORY,
    SCRIPT_DIRECTORY_NAME,
)

TRUSTED_FILES = (Path(SCRIPT_DIRECTORY_NAME) / BACKUP_SCRIPT_NAME,)

###########################
# CommandRunnerResult tests
###########################


@pytest.mark.parametrize(
    ("exit_code_matched", "stdout_matched", "stderr_matched"),
    list(itertools.product([True, False], repeat=3)),
)
def test_command_runner_result_matches_only_if_everything_matched(
    exit_code_matched: bool,
    stdout_matched: bool,
    stderr_matched: bool,
) -> None:
    result = CommandRunnerResult(
        CommandResult(exit_code=0), exit_code_matched, stdout_matched, stderr_matched
    )

    assert result.matched is (exit_code_matched and stdout_matched and stderr_matched)


def test_command_runner_result_is_immutable() -> None:
    result = CommandRunnerResult(CommandResult(exit_code=0), True, True, True)

    with pytest.raises(AttributeError):
        result.exit_code_matched = False  # type: ignore (ignore this Pylance error even though it is correct)


###############
# Request tests
###############


def test_command_runner_runs_command_with_given_request() -> None:
    command_provider = make_command_provider()

    make_command_runner(
        command_provider,
        command="echo secret",
        shell=Shell.BASH,
        environment={"KEY": "value"},
        timeout=5,
    ).run()

    command_provider.run.assert_called_once_with(
        CommandRequest(
            command="echo secret",
            working_directory=DEFAULT_WORKING_DIRECTORY,
            environment={"KEY": "value"},
            timeout=5,
            wait=True,
            shell=Shell.BASH,
        )
    )


def test_command_runner_returns_result_of_provider() -> None:
    result = CommandResult(exit_code=0, stdout="out", stderr="err")

    outcome = make_command_runner(make_command_provider(result)).run()

    assert outcome.result is result


def test_command_runner_copies_environment_and_exit_codes() -> None:
    environment = {"CUSTOM": "value"}
    command_provider = make_command_provider()

    runner = make_command_runner(
        command_provider, environment=environment, success_exit_codes=[0, 0, 3]
    )
    environment["CUSTOM"] = "changed"

    runner.run()

    assert runner.success_exit_codes == frozenset({0, 3})
    assert command_provider.run.call_args.args[0].environment == {"CUSTOM": "value"}


#################
# Exit code tests
#################


@pytest.mark.parametrize(
    ("exit_code", "success_exit_codes", "expected"),
    [
        (0, (0,), True),
        (3, (0, 3), True),
        (-1, (-1,), True),
        (1, (0,), False),
        (4, (0, 3), False),
        # No exit code at all is never a success for a command which is waited for
        (None, (0,), False),
    ],
)
def test_command_runner_compares_exit_code(
    exit_code: int | None,
    success_exit_codes: tuple[int, ...],
    expected: bool,
) -> None:
    runner = make_command_runner(
        make_command_provider(CommandResult(exit_code=exit_code)),
        success_exit_codes=success_exit_codes,
    )

    assert runner.run().exit_code_matched is expected


##############
# Output tests
##############


def test_command_runner_accepts_any_output_without_matchers() -> None:
    outcome = make_command_runner(
        make_command_provider(CommandResult(exit_code=0, stdout="a", stderr="b"))
    ).run()

    assert outcome.stdout_matched is True
    assert outcome.stderr_matched is True
    assert outcome.matched is True


def test_command_runner_compares_stripped_output() -> None:
    runner = make_command_runner(
        make_command_provider(
            CommandResult(exit_code=0, stdout="  active \n\n", stderr="\terr\r\n")
        ),
        stdout_matcher=StringMatcher("active"),
        stderr_matcher=StringMatcher("err"),
    )

    outcome = runner.run()

    assert outcome.stdout_matched is True
    assert outcome.stderr_matched is True


def test_command_runner_reports_which_stream_does_not_match() -> None:
    outcome = make_command_runner(
        make_command_provider(
            CommandResult(exit_code=0, stdout="inactive", stderr="err")
        ),
        stdout_matcher=StringMatcher("active"),
        stderr_matcher=StringMatcher("err"),
    ).run()

    assert outcome.exit_code_matched is True
    assert outcome.stdout_matched is False
    assert outcome.stderr_matched is True
    assert outcome.matched is False


def test_command_runner_reports_stderr_which_does_not_match() -> None:
    outcome = make_command_runner(
        make_command_provider(CommandResult(exit_code=0, stderr="other")),
        stderr_matcher=StringMatcher("err"),
    ).run()

    assert outcome.stdout_matched is True
    assert outcome.stderr_matched is False
    assert outcome.matched is False


def test_command_runner_only_compares_configured_streams() -> None:
    outcome = make_command_runner(
        make_command_provider(CommandResult(exit_code=0, stdout="x", stderr="y")),
        stdout_matcher=StringMatcher("x"),
    ).run()

    assert outcome.stderr_matched is True
    assert outcome.matched is True


def test_command_runner_matches_multi_line_output_with_regular_expression() -> None:
    outcome = make_command_runner(
        make_command_provider(
            CommandResult(exit_code=0, stdout="line 1\nERROR here\nline 3\n")
        ),
        stdout_matcher=StringMatcher(
            ".*error.*", MatchType.REGEX, case_sensitive=False
        ),
    ).run()

    assert outcome.stdout_matched is True


def test_command_runner_reports_all_criteria_even_if_the_exit_code_does_not_match() -> (
    None
):
    outcome = make_command_runner(
        make_command_provider(CommandResult(exit_code=1, stdout="active")),
        stdout_matcher=StringMatcher("active"),
    ).run()

    assert outcome.exit_code_matched is False
    assert outcome.stdout_matched is True
    assert outcome.matched is False


######################
# Background run tests
######################


def test_command_runner_does_not_compare_anything_when_not_waiting() -> None:
    command_provider = make_command_provider(CommandResult(exit_code=None))

    outcome = make_command_runner(
        command_provider,
        wait=False,
        success_exit_codes=(5,),
        stdout_matcher=StringMatcher("never"),
        stderr_matcher=StringMatcher("never"),
    ).run()

    assert command_provider.run.call_args.args[0].wait is False
    assert outcome.exit_code_matched is True
    assert outcome.stdout_matched is True
    assert outcome.stderr_matched is True
    assert outcome.matched is True


#####################
# Trusted files tests
#####################


def test_command_runner_verifies_trusted_files_before_running_the_command() -> None:
    calls: list[str] = []
    command_provider = make_command_provider()

    def run(_request: CommandRequest) -> CommandResult:
        calls.append("run")

        return CommandResult(exit_code=0)

    command_provider.run.side_effect = run
    files_verifier = make_files_verifier()
    files_verifier.side_effect = lambda _files: calls.append("verify")

    make_command_runner(
        command_provider, trusted_files=TRUSTED_FILES, files_verifier=files_verifier
    ).run()

    assert calls == ["verify", "run"]
    files_verifier.assert_called_once_with(TRUSTED_FILES)


def test_command_runner_verifies_trusted_files_on_every_run() -> None:
    files_verifier = make_files_verifier()
    runner = make_command_runner(
        trusted_files=TRUSTED_FILES, files_verifier=files_verifier
    )

    runner.run()
    runner.run()

    assert files_verifier.call_count == 2


def test_command_runner_stores_trusted_files_as_tuple() -> None:
    runner = make_command_runner(trusted_files=[Path("a.sh"), Path("b.sh")])

    assert runner.trusted_files == (Path("a.sh"), Path("b.sh"))


def test_command_runner_does_not_verify_without_trusted_files() -> None:
    files_verifier = make_files_verifier()
    command_provider = make_command_provider()

    make_command_runner(command_provider, files_verifier=files_verifier).run()

    files_verifier.assert_not_called()
    command_provider.run.assert_called_once()


def test_command_runner_runs_without_verifier() -> None:
    command_provider = make_command_provider()

    make_command_runner(command_provider, trusted_files=TRUSTED_FILES).run()

    command_provider.run.assert_called_once()


def test_command_runner_does_not_run_command_when_verification_fails() -> None:
    command_provider = make_command_provider()
    error = FileIntegrityError("Test file was modified")
    runner = make_command_runner(
        command_provider,
        trusted_files=TRUSTED_FILES,
        files_verifier=make_files_verifier(error=error),
    )

    with pytest.raises(FileIntegrityError) as exc_info:
        runner.run()

    assert exc_info.value is error
    command_provider.run.assert_not_called()


######################
# Error handling tests
######################


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError("Test timeout"),
        FileNotFoundError("Test shell missing"),
        PermissionError("Test permission"),
        RuntimeError("Test failure"),
    ],
)
def test_command_runner_propagates_errors_of_provider_unchanged(
    error: Exception,
) -> None:
    runner = make_command_runner(make_command_provider(error=error))

    with pytest.raises(type(error)) as exc_info:
        runner.run()

    assert exc_info.value is error
