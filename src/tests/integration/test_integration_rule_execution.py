from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from powerrules.actions.command import (
    ACTION_NAME_ENVIRONMENT_VARIABLE,
    RULE_NAME_ENVIRONMENT_VARIABLE,
)
from powerrules.engine.exceptions import (
    ActionExecutionError,
    ConditionEvaluationError,
    ConditionEvaluationProviderNotAvailableError,
)
from powerrules.platform.command import SubprocessCommandProvider
from powerrules.providers.command import CommandResult, Shell
from tests.factories import build_rule_engine_from_policy, make_command_provider
from tests.helpers import (
    BACKUP_SCRIPT_NAME,
    SCRIPT_DIRECTORY_NAME,
    get_commands,
    posix_only,
)

BACKUP_POLICY = """
rules:
  - name: "Shutdown after backup"
    conditions:
      and:
        - process:
            name: "backup.exe"
            exists: false
        - datetime:
            between:
              start: "23:00"
              end: "6:00"
    actions:
      - name: "Shutdown"
        run: "shutdown /s /t 0"
"""


#######################
# Matching and ordering
#######################


def test_rule_execution_runs_commands_of_matching_rule(tmp_path: Path) -> None:
    command_provider = make_command_provider()
    engine = build_rule_engine_from_policy(
        tmp_path,
        BACKUP_POLICY,
        now=datetime(2026, 8, 22, 1, 30),
        command_provider=command_provider,
    )

    result = engine.evaluate()

    assert result.matched_rule is not None
    assert result.matched_rule.name == "Shutdown after backup"
    assert result.action_triggered is True
    command_provider.run.assert_called_once()

    request = command_provider.run.call_args.args[0]
    assert request.command == "shutdown /s /t 0"
    assert request.working_directory == tmp_path
    assert request.environment == {
        RULE_NAME_ENVIRONMENT_VARIABLE: "Shutdown after backup",
        ACTION_NAME_ENVIRONMENT_VARIABLE: "Shutdown",
    }


def test_rule_execution_returns_no_match_outside_of_time_range(
    tmp_path: Path,
) -> None:
    command_provider = make_command_provider()
    engine = build_rule_engine_from_policy(
        tmp_path,
        BACKUP_POLICY,
        now=datetime(2026, 8, 22, 22, 30),
        command_provider=command_provider,
    )

    result = engine.evaluate()

    assert result.matched_rule is None
    assert result.action_triggered is False
    command_provider.run.assert_not_called()


def test_rule_execution_returns_no_match_while_process_is_running(
    tmp_path: Path,
) -> None:
    command_provider = make_command_provider()
    engine = build_rule_engine_from_policy(
        tmp_path,
        BACKUP_POLICY,
        now=datetime(2026, 8, 22, 1, 30),
        process_names=("explorer.exe", "backup.exe"),
        command_provider=command_provider,
    )

    assert engine.evaluate().matched_rule is None
    command_provider.run.assert_not_called()


def test_rule_execution_uses_first_matching_rule(tmp_path: Path) -> None:
    command_provider = make_command_provider()
    engine = build_rule_engine_from_policy(
        tmp_path,
        """
rules:
  - name: "Sleep"
    conditions:
      datetime:
        between:
          start: "22:00"
          end: "0:00"
    actions:
      - run: "echo sleep"

  - name: "Shutdown"
    conditions:
      datetime:
        between:
          start: "23:00"
          end: "6:00"
    actions:
      - run: "echo shutdown"
""",
        now=datetime(2026, 8, 22, 23, 30),
        command_provider=command_provider,
    )

    result = engine.evaluate()

    assert result.matched_rule is not None
    assert result.matched_rule.name == "Sleep"
    assert get_commands(command_provider) == ["echo sleep"]


def test_rule_execution_skips_disabled_rule(tmp_path: Path) -> None:
    command_provider = make_command_provider()
    engine = build_rule_engine_from_policy(
        tmp_path,
        """
rules:
  - name: "Disabled rule"
    enabled: false
    conditions:
      datetime:
        weekday: [Saturday]
    actions:
      - run: "echo disabled"

  - name: "Enabled rule"
    conditions:
      datetime:
        weekday: [Saturday]
    actions:
      - run: "echo enabled"
""",
        command_provider=command_provider,
    )

    result = engine.evaluate()

    assert result.matched_rule is not None
    assert result.matched_rule.name == "Enabled rule"
    assert get_commands(command_provider) == ["echo enabled"]


def test_rule_execution_with_not_and_or_conditions(tmp_path: Path) -> None:
    policy = """
rules:
  - name: "Nested rule"
    conditions:
      and:
        - not:
            process:
              name: "backup.exe"
              exists: true
        - or:
            - datetime:
                weekday: [Monday]
            - datetime:
                weekday: [Saturday]
    actions:
      - run: "echo nested"
"""
    command_provider = make_command_provider()

    # 2026-08-22 is a Saturday
    assert (
        build_rule_engine_from_policy(
            tmp_path, policy, command_provider=command_provider
        )
        .evaluate()
        .matched_rule
        is not None
    )

    assert (
        build_rule_engine_from_policy(tmp_path, policy, process_names=("backup.exe",))
        .evaluate()
        .matched_rule
        is None
    )
    assert (
        build_rule_engine_from_policy(
            tmp_path, policy, now=datetime(2026, 8, 21, 12, 0)
        )
        .evaluate()
        .matched_rule
        is None
    )


################################
# Date and time based conditions
################################


@pytest.mark.parametrize(
    ("current_datetime", "expected_match"),
    [
        (datetime(2026, 8, 20, 23, 59, 59), False),
        # The start date is included
        (datetime(2026, 8, 21, 0, 0), True),
        (datetime(2026, 8, 21, 12, 0), True),
        (datetime(2026, 8, 21, 23, 59, 59), True),
        # The end date is excluded
        (datetime(2026, 8, 22, 0, 0), False),
    ],
)
def test_rule_execution_with_date_range(
    tmp_path: Path,
    current_datetime: datetime,
    expected_match: bool,
) -> None:
    command_provider = make_command_provider()
    engine = build_rule_engine_from_policy(
        tmp_path,
        """
rules:
  - name: "Run on a date"
    conditions:
      datetime:
        between:
          start: "2026-08-21"
          end: "2026-08-22"
    actions:
      - run: "echo test"
""",
        now=current_datetime,
        command_provider=command_provider,
    )

    result = engine.evaluate()

    assert (result.matched_rule is not None) is expected_match
    assert command_provider.run.call_count == int(expected_match)


# For an absolute range the weekday refers to the current day, not to the day on which the range starts
@pytest.mark.parametrize(
    ("current_datetime", "expected_match"),
    [
        # Friday evening is within the range, but not on a Saturday
        (datetime(2026, 8, 21, 22, 0), False),
        # Saturday night is within the range and on a Saturday
        (datetime(2026, 8, 22, 1, 0), True),
        # Saturday afternoon is on a Saturday, but outside of the range
        (datetime(2026, 8, 22, 12, 0), False),
    ],
)
def test_rule_execution_with_datetime_range_and_weekday(
    tmp_path: Path,
    current_datetime: datetime,
    expected_match: bool,
) -> None:
    command_provider = make_command_provider()
    engine = build_rule_engine_from_policy(
        tmp_path,
        """
rules:
  - name: "Run on Saturday night"
    conditions:
      datetime:
        between:
          start: "2026-08-21 18:00"
          end: "2026-08-22 6:00"
        weekday:
          - "Saturday"
    actions:
      - run: "echo test"
""",
        now=current_datetime,
        command_provider=command_provider,
    )

    result = engine.evaluate()

    assert (result.matched_rule is not None) is expected_match
    assert command_provider.run.call_count == int(expected_match)


# For a time range crossing midnight the weekday and month refer to the day on which the range starts
@pytest.mark.parametrize(
    ("current_datetime", "expected_match"),
    [
        (datetime(2026, 12, 31, 23, 30), True),
        (datetime(2027, 1, 1, 1, 0), True),
        (datetime(2027, 1, 1, 23, 30), False),
    ],
)
def test_rule_execution_with_time_range_crossing_midnight_and_month(
    tmp_path: Path,
    current_datetime: datetime,
    expected_match: bool,
) -> None:
    engine = build_rule_engine_from_policy(
        tmp_path,
        """
rules:
  - name: "Run at the end of the year"
    conditions:
      datetime:
        between:
          start: "23"
          end: "1:30"
        month: [December]
    actions:
      - run: "echo test"
""",
        now=current_datetime,
    )

    assert (engine.evaluate().matched_rule is not None) is expected_match


##########################
# Process and window rules
##########################


@pytest.mark.parametrize(
    ("process_names", "expected_match"),
    [
        (("Firefox.EXE",), True),
        (("chrome.exe", "firefox.exe"), True),
        (("firefox.exe.bak",), False),
        ((), False),
    ],
)
def test_rule_execution_with_regex_process_condition(
    tmp_path: Path,
    process_names: tuple[str, ...],
    expected_match: bool,
) -> None:
    engine = build_rule_engine_from_policy(
        tmp_path,
        """
rules:
  - name: "Firefox is running"
    conditions:
      process:
        name: "fire.*\\\\.exe"
        exists: true
        match:
          type: regex
          case_sensitive: false
    actions:
      - run: "echo test"
""",
        process_names=process_names,
    )

    assert (engine.evaluate().matched_rule is not None) is expected_match


def test_rule_execution_with_window_condition(tmp_path: Path) -> None:
    policy = """
rules:
  - name: "Firefox window exists"
    conditions:
      window:
        title: "Mozilla Firefox"
        exists: true
    actions:
      - run: "echo test"
"""

    assert (
        build_rule_engine_from_policy(
            tmp_path, policy, window_titles=("Mozilla Firefox",)
        )
        .evaluate()
        .matched_rule
        is not None
    )
    assert (
        build_rule_engine_from_policy(tmp_path, policy, window_titles=("Other",))
        .evaluate()
        .matched_rule
        is None
    )


def test_rule_execution_fails_when_window_provider_is_not_available(
    tmp_path: Path,
) -> None:
    command_provider = make_command_provider()
    engine = build_rule_engine_from_policy(
        tmp_path,
        """
rules:
  - name: "Firefox window exists"
    conditions:
      window:
        title: "Mozilla Firefox"
        exists: true
    actions:
      - run: "echo test"
""",
        window_available=False,
        command_provider=command_provider,
    )

    with pytest.raises(ConditionEvaluationProviderNotAvailableError):
        engine.evaluate()

    command_provider.run.assert_not_called()


def test_rule_execution_fails_when_condition_cannot_be_evaluated(
    tmp_path: Path,
) -> None:
    command_provider = make_command_provider()
    engine = build_rule_engine_from_policy(
        tmp_path,
        BACKUP_POLICY,
        now=datetime(2026, 8, 22, 1, 30),
        process_error=OSError("Test failure"),
        command_provider=command_provider,
    )

    with pytest.raises(
        ConditionEvaluationError,
        match="Failed to determine whether process 'backup.exe' exists",
    ):
        engine.evaluate()

    command_provider.run.assert_not_called()


##################
# Action execution
##################


def test_rule_execution_runs_multiple_actions_in_order(tmp_path: Path) -> None:
    command_provider = make_command_provider()
    engine = build_rule_engine_from_policy(
        tmp_path,
        """
rules:
  - name: "Multiple actions"
    conditions:
      datetime:
        weekday: [Saturday]
    actions:
      - name: "Cleanup"
        run: "echo cleanup"
      - run: "echo backup"
      - name: "Shutdown"
        run: "echo shutdown"
""",
        command_provider=command_provider,
    )

    engine.evaluate()

    assert get_commands(command_provider) == [
        "echo cleanup",
        "echo backup",
        "echo shutdown",
    ]
    assert [
        call.args[0].environment[ACTION_NAME_ENVIRONMENT_VARIABLE]
        for call in command_provider.run.call_args_list
    ] == ["Cleanup", "Action 2 of 3", "Shutdown"]


def test_rule_execution_passes_action_options_to_command_provider(
    tmp_path: Path,
) -> None:
    command_provider = make_command_provider()
    engine = build_rule_engine_from_policy(
        tmp_path,
        f"""
rules:
  - name: "Options rule"
    conditions:
      datetime:
        weekday: [Saturday]
    actions:
      - run: "{BACKUP_SCRIPT_NAME}"
        shell: bash
        working_directory: scripts
        env:
          RETRIES: 3
          VERBOSE: true
        timeout: 5
""",
        command_provider=command_provider,
    )

    engine.evaluate()

    request = command_provider.run.call_args.args[0]
    assert request.command == BACKUP_SCRIPT_NAME
    assert request.shell is Shell.BASH
    assert request.working_directory == tmp_path / SCRIPT_DIRECTORY_NAME
    assert request.environment == {
        "RETRIES": "3",
        "VERBOSE": "true",
        RULE_NAME_ENVIRONMENT_VARIABLE: "Options rule",
        ACTION_NAME_ENVIRONMENT_VARIABLE: "Action 1 of 1",
    }
    assert request.timeout == 5
    assert request.wait is True


def test_rule_execution_starts_background_action_without_waiting(
    tmp_path: Path,
) -> None:
    command_provider = make_command_provider(CommandResult(exit_code=None))
    engine = build_rule_engine_from_policy(
        tmp_path,
        """
rules:
  - name: "Background rule"
    conditions:
      datetime:
        weekday: [Saturday]
    actions:
      - run: "long-running-task"
        wait: false
""",
        command_provider=command_provider,
    )

    result = engine.evaluate()

    assert result.action_triggered is True
    assert command_provider.run.call_args.args[0].wait is False


def test_rule_execution_accepts_configured_success_exit_codes(
    tmp_path: Path,
) -> None:
    engine = build_rule_engine_from_policy(
        tmp_path,
        """
rules:
  - name: "Exit code rule"
    conditions:
      datetime:
        weekday: [Saturday]
    actions:
      - run: "robocopy"
        success_exit_codes: [0, 1, 2]
""",
        command_provider=make_command_provider(CommandResult(exit_code=1)),
    )

    assert engine.evaluate().action_triggered is True


FAILING_ACTIONS_POLICY = """
rules:
  - name: "Failing rule"
    conditions:
      datetime:
        weekday: [Saturday]
    actions:
      - name: "Failing"
        run: "echo failing"
        timeout: 5
      - name: "Last"
        run: "echo last"
"""


def test_rule_execution_skips_remaining_actions_after_failed_action(
    tmp_path: Path,
) -> None:
    command_provider = make_command_provider(CommandResult(exit_code=1))
    engine = build_rule_engine_from_policy(
        tmp_path, FAILING_ACTIONS_POLICY, command_provider=command_provider
    )

    with pytest.raises(
        ActionExecutionError,
        match="Action 'Failing' returned exit code 1, expected one of: 0",
    ):
        engine.evaluate()

    assert get_commands(command_provider) == ["echo failing"]


def test_rule_execution_reports_timeout_of_action(tmp_path: Path) -> None:
    command_provider = make_command_provider(error=TimeoutError())
    engine = build_rule_engine_from_policy(
        tmp_path, FAILING_ACTIONS_POLICY, command_provider=command_provider
    )

    with pytest.raises(
        ActionExecutionError,
        match="Action 'Failing' timed out after 5 seconds",
    ):
        engine.evaluate()

    command_provider.run.assert_called_once()


def test_rule_execution_continues_after_failed_action_with_continue_on_error(
    tmp_path: Path,
) -> None:
    command_provider = make_command_provider()
    command_provider.run.side_effect = [
        CommandResult(exit_code=1),
        CommandResult(exit_code=0),
    ]
    engine = build_rule_engine_from_policy(
        tmp_path,
        """
rules:
  - name: "Tolerant rule"
    conditions:
      datetime:
        weekday: [Saturday]
    actions:
      - name: "Failing"
        run: "echo failing"
        continue_on_error: true
      - name: "Last"
        run: "echo last"
""",
        command_provider=command_provider,
    )

    result = engine.evaluate()

    assert result.action_triggered is True
    assert get_commands(command_provider) == ["echo failing", "echo last"]


def test_rule_execution_dry_run_does_not_run_commands(tmp_path: Path) -> None:
    command_provider = make_command_provider()
    engine = build_rule_engine_from_policy(
        tmp_path,
        BACKUP_POLICY,
        now=datetime(2026, 8, 22, 1, 30),
        command_provider=command_provider,
    )

    result = engine.evaluate(dry_run=True)

    assert result.matched_rule is not None
    assert result.action_triggered is True
    command_provider.run.assert_not_called()


def test_rule_execution_does_not_repeat_commands_for_unchanged_match(
    tmp_path: Path,
) -> None:
    command_provider = make_command_provider()
    engine = build_rule_engine_from_policy(
        tmp_path,
        BACKUP_POLICY,
        now=datetime(2026, 8, 22, 1, 30),
        command_provider=command_provider,
    )

    first_result = engine.evaluate()
    second_result = engine.evaluate(previous_matched_rule=first_result.matched_rule)

    assert second_result.matched_rule is first_result.matched_rule
    assert second_result.action_triggered is False
    command_provider.run.assert_called_once()


COMMAND_CONDITION_POLICY = """
rules:
  - name: "Service is active"
    conditions:
      command:
        run: "systemctl is-active nginx"
        shell: bash
        working_directory: scripts
        env:
          RETRIES: 3
        timeout: 5
        stdout:
          value: "active"
    actions:
      - name: "Notify"
        run: "echo notify"
"""

CONDITION_COMMAND = "systemctl is-active nginx"


def make_condition_provider(*outcomes: CommandResult | Exception) -> Mock:
    """Create a mocked command provider which returns the outcomes of the consecutive commands one after another."""
    command_provider = make_command_provider()
    command_provider.run.side_effect = list(outcomes)

    return command_provider


####################
# Command conditions
####################


def test_rule_execution_runs_command_condition_before_actions(tmp_path: Path) -> None:
    command_provider = make_condition_provider(
        CommandResult(exit_code=0, stdout="active\n"),
        CommandResult(exit_code=0),
    )
    engine = build_rule_engine_from_policy(
        tmp_path, COMMAND_CONDITION_POLICY, command_provider=command_provider
    )

    result = engine.evaluate()

    assert result.action_triggered is True
    assert get_commands(command_provider) == [CONDITION_COMMAND, "echo notify"]

    condition_request, action_request = (
        call.args[0] for call in command_provider.run.call_args_list
    )

    assert condition_request.shell is Shell.BASH
    assert condition_request.working_directory == tmp_path / SCRIPT_DIRECTORY_NAME
    assert condition_request.timeout == 5
    assert condition_request.wait is True
    # A condition does not receive the variables of an action
    assert condition_request.environment == {"RETRIES": "3"}
    assert action_request.environment == {
        RULE_NAME_ENVIRONMENT_VARIABLE: "Service is active",
        ACTION_NAME_ENVIRONMENT_VARIABLE: "Notify",
    }


@pytest.mark.parametrize(
    "outcome",
    [
        # The output does not match
        CommandResult(exit_code=0, stdout="inactive\n"),
        # The exit code does not count as success
        CommandResult(exit_code=3, stdout="active\n"),
    ],
)
def test_rule_execution_does_not_match_if_command_condition_does_not_match(
    tmp_path: Path, outcome: CommandResult
) -> None:
    command_provider = make_condition_provider(outcome)
    engine = build_rule_engine_from_policy(
        tmp_path, COMMAND_CONDITION_POLICY, command_provider=command_provider
    )

    result = engine.evaluate()

    # An unexpected result is no error, the actions simply do not run
    assert result.matched_rule is None
    assert get_commands(command_provider) == [CONDITION_COMMAND]


def test_rule_execution_compares_stripped_multi_line_output_of_command_condition(
    tmp_path: Path,
) -> None:
    command_provider = make_condition_provider(
        CommandResult(exit_code=0, stdout="line 1\nERROR here\nline 3\n\n"),
        CommandResult(exit_code=0),
    )
    engine = build_rule_engine_from_policy(
        tmp_path,
        """
rules:
  - name: "Error in output"
    conditions:
      command:
        run: "check"
        stdout:
          value: ".*error.*"
          match:
            type: regex
            case_sensitive: false
    actions:
      - run: "echo test"
""",
        command_provider=command_provider,
    )

    assert engine.evaluate().action_triggered is True


def test_rule_execution_accepts_configured_success_exit_codes_of_command_condition(
    tmp_path: Path,
) -> None:
    engine = build_rule_engine_from_policy(
        tmp_path,
        """
rules:
  - name: "Exit code rule"
    conditions:
      command:
        run: "check"
        success_exit_codes: [2]
    actions:
      - run: "echo test"
""",
        command_provider=make_condition_provider(
            CommandResult(exit_code=2), CommandResult(exit_code=0)
        ),
    )

    assert engine.evaluate().action_triggered is True


def test_rule_execution_negates_command_condition(tmp_path: Path) -> None:
    engine = build_rule_engine_from_policy(
        tmp_path,
        """
rules:
  - name: "Service is not running"
    conditions:
      not:
        command:
          run: "check"
    actions:
      - run: "echo test"
""",
        command_provider=make_condition_provider(
            CommandResult(exit_code=1), CommandResult(exit_code=0)
        ),
    )

    assert engine.evaluate().action_triggered is True


def test_rule_execution_does_not_run_command_condition_after_false_condition(
    tmp_path: Path,
) -> None:
    command_provider = make_command_provider()
    engine = build_rule_engine_from_policy(
        tmp_path,
        """
rules:
  - name: "Short circuit"
    conditions:
      and:
        - process:
            name: "backup.exe"
            exists: true
        - command:
            run: "check"
    actions:
      - run: "echo test"
""",
        command_provider=command_provider,
    )

    assert engine.evaluate().matched_rule is None
    command_provider.run.assert_not_called()


def test_rule_execution_uses_first_rule_with_matching_command_condition(
    tmp_path: Path,
) -> None:
    command_provider = make_condition_provider(
        CommandResult(exit_code=1),
        CommandResult(exit_code=0),
        CommandResult(exit_code=0),
    )
    engine = build_rule_engine_from_policy(
        tmp_path,
        """
rules:
  - name: "First"
    conditions:
      command:
        run: "check first"
    actions:
      - run: "echo first"

  - name: "Second"
    conditions:
      command:
        run: "check second"
    actions:
      - run: "echo second"
""",
        command_provider=command_provider,
    )

    result = engine.evaluate()

    assert result.matched_rule is not None
    assert result.matched_rule.name == "Second"
    assert get_commands(command_provider) == [
        "check first",
        "check second",
        "echo second",
    ]


# Conditions are evaluated in a dry run, only the actions are not executed
def test_rule_execution_dry_run_runs_command_condition_but_not_actions(
    tmp_path: Path,
) -> None:
    command_provider = make_condition_provider(
        CommandResult(exit_code=0, stdout="active\n")
    )
    engine = build_rule_engine_from_policy(
        tmp_path, COMMAND_CONDITION_POLICY, command_provider=command_provider
    )

    result = engine.evaluate(dry_run=True)

    assert result.action_triggered is True
    assert get_commands(command_provider) == [CONDITION_COMMAND]


def test_rule_execution_reports_timeout_of_command_condition(tmp_path: Path) -> None:
    command_provider = make_condition_provider(TimeoutError())
    engine = build_rule_engine_from_policy(
        tmp_path, COMMAND_CONDITION_POLICY, command_provider=command_provider
    )

    with pytest.raises(
        ConditionEvaluationError,
        match="Command of a command condition timed out after 5 seconds",
    ) as exc_info:
        engine.evaluate()

    assert isinstance(exc_info.value.__cause__, TimeoutError)
    assert get_commands(command_provider) == [CONDITION_COMMAND]


def test_rule_execution_reports_command_condition_which_cannot_be_started(
    tmp_path: Path,
) -> None:
    original_error = FileNotFoundError("Test shell missing")
    command_provider = make_condition_provider(original_error)
    engine = build_rule_engine_from_policy(
        tmp_path, COMMAND_CONDITION_POLICY, command_provider=command_provider
    )

    with pytest.raises(
        ConditionEvaluationError,
        match="Command of a command condition could not be started: Test shell missing",
    ) as exc_info:
        engine.evaluate()

    assert exc_info.value.__cause__ is original_error
    assert get_commands(command_provider) == [CONDITION_COMMAND]


#################################
# Tests with real child processes
#################################


@posix_only
def test_rule_execution_runs_real_command(tmp_path: Path) -> None:
    engine = build_rule_engine_from_policy(
        tmp_path,
        """
rules:
  - name: "Marker rule"
    conditions:
      datetime:
        weekday: [Saturday]
    actions:
      - run: 'echo "$POWERRULES_RULE_NAME" > marker.txt'
""",
        command_provider=SubprocessCommandProvider(Shell.SH),
    )

    result = engine.evaluate()

    assert result.action_triggered is True
    # The command ran in the directory of the policy
    assert (tmp_path / "marker.txt").read_text(encoding="utf-8") == "Marker rule\n"


@posix_only
def test_rule_execution_reports_exit_code_of_real_command(tmp_path: Path) -> None:
    engine = build_rule_engine_from_policy(
        tmp_path,
        """
rules:
  - name: "Failing rule"
    conditions:
      datetime:
        weekday: [Saturday]
    actions:
      - name: "Failing"
        run: "exit 3"
""",
        command_provider=SubprocessCommandProvider(Shell.SH),
    )

    with pytest.raises(ActionExecutionError, match="returned exit code 3"):
        engine.evaluate()


@posix_only
def test_rule_execution_runs_real_command_condition(tmp_path: Path) -> None:
    engine = build_rule_engine_from_policy(
        tmp_path,
        """
rules:
  - name: "Real condition"
    conditions:
      command:
        run: 'echo "ready"; echo "warning" >&2'
        stdout:
          value: "ready"
        stderr:
          value: "warn"
          match:
            type: contains
    actions:
      - run: 'echo "$POWERRULES_RULE_NAME" > marker.txt'
""",
        command_provider=SubprocessCommandProvider(Shell.SH),
    )

    assert engine.evaluate().action_triggered is True
    assert (tmp_path / "marker.txt").read_text(encoding="utf-8") == "Real condition\n"
