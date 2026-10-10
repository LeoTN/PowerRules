import shutil
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from powerrules.actions.command import (
    ACTION_NAME_ENVIRONMENT_VARIABLE,
    RULE_NAME_ENVIRONMENT_VARIABLE,
)
from powerrules.config.builder import ConfigurationBuilder
from powerrules.config.loader import ConfigurationLoader
from powerrules.engine.exceptions import (
    ActionExecutionError,
    ConditionEvaluationError,
    ConditionEvaluationProviderNotAvailableError,
)
from powerrules.engine.rule_engine import RuleEngine
from powerrules.platform.command import SubprocessCommandProvider
from powerrules.providers.command import CommandResult, Shell
from tests.mocks import (
    make_clock_provider,
    make_command_provider,
    make_process_provider,
    make_window_provider,
)

DEFAULT_NOW = datetime(2026, 8, 22, 12, 0)

posix_only = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("sh") is None,
    reason="Requires a POSIX shell",
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


def _build_engine(
    tmp_path: Path,
    policy: str,
    *,
    now: datetime = DEFAULT_NOW,
    process_names: tuple[str, ...] = (),
    process_error: Exception | None = None,
    window_titles: tuple[str, ...] = (),
    window_available: bool = True,
    command_provider: Mock | SubprocessCommandProvider | None = None,
) -> RuleEngine:
    """Load a policy from a file and build an engine with mocked providers."""
    policy_file = tmp_path / "powerrules.yaml"
    policy_file.write_text(policy, encoding="utf-8")

    rule_set = ConfigurationBuilder(
        clock_provider=make_clock_provider(now),
        process_provider=make_process_provider(process_names, error=process_error),
        window_provider=make_window_provider(window_titles, available=window_available),
        command_provider=(
            command_provider
            if command_provider is not None
            else make_command_provider()
        ),
        base_directory=tmp_path,
    ).build(ConfigurationLoader().load(policy_file))

    return RuleEngine(rule_set.rules)


def _get_commands(command_provider: Mock) -> list[str]:
    """Return the commands of all requests in the order in which they were run."""
    return [call.args[0].command for call in command_provider.run.call_args_list]


#######################
# Matching and ordering
#######################


def test_rule_execution_runs_commands_of_matching_rule(tmp_path: Path) -> None:
    command_provider = make_command_provider()
    engine = _build_engine(
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
    engine = _build_engine(
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
    engine = _build_engine(
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
    engine = _build_engine(
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
    assert _get_commands(command_provider) == ["echo sleep"]


def test_rule_execution_skips_disabled_rule(tmp_path: Path) -> None:
    command_provider = make_command_provider()
    engine = _build_engine(
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
    assert _get_commands(command_provider) == ["echo enabled"]


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
        _build_engine(tmp_path, policy, command_provider=command_provider)
        .evaluate()
        .matched_rule
        is not None
    )

    assert (
        _build_engine(tmp_path, policy, process_names=("backup.exe",))
        .evaluate()
        .matched_rule
        is None
    )
    assert (
        _build_engine(tmp_path, policy, now=datetime(2026, 8, 21, 12, 0))
        .evaluate()
        .matched_rule
        is None
    )


#################################
# Date and time based conditions
#################################


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
    engine = _build_engine(
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
    engine = _build_engine(
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
    engine = _build_engine(
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
    engine = _build_engine(
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
        _build_engine(tmp_path, policy, window_titles=("Mozilla Firefox",))
        .evaluate()
        .matched_rule
        is not None
    )
    assert (
        _build_engine(tmp_path, policy, window_titles=("Other",))
        .evaluate()
        .matched_rule
        is None
    )


def test_rule_execution_fails_when_window_provider_is_not_available(
    tmp_path: Path,
) -> None:
    command_provider = make_command_provider()
    engine = _build_engine(
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
    engine = _build_engine(
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
    engine = _build_engine(
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

    assert _get_commands(command_provider) == [
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
    engine = _build_engine(
        tmp_path,
        """
rules:
  - name: "Options rule"
    conditions:
      datetime:
        weekday: [Saturday]
    actions:
      - run: "backup.sh"
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
    assert request.command == "backup.sh"
    assert request.shell is Shell.BASH
    assert request.working_directory == tmp_path / "scripts"
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
    engine = _build_engine(
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
    engine = _build_engine(
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
    engine = _build_engine(
        tmp_path, FAILING_ACTIONS_POLICY, command_provider=command_provider
    )

    with pytest.raises(
        ActionExecutionError,
        match="Action 'Failing' returned exit code 1, expected one of: 0",
    ):
        engine.evaluate()

    assert _get_commands(command_provider) == ["echo failing"]


def test_rule_execution_reports_timeout_of_action(tmp_path: Path) -> None:
    command_provider = make_command_provider(error=TimeoutError())
    engine = _build_engine(
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
    engine = _build_engine(
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
    assert _get_commands(command_provider) == ["echo failing", "echo last"]


def test_rule_execution_dry_run_does_not_run_commands(tmp_path: Path) -> None:
    command_provider = make_command_provider()
    engine = _build_engine(
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
    engine = _build_engine(
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


#################################
# Tests with real child processes
#################################


@posix_only
def test_rule_execution_runs_real_command(tmp_path: Path) -> None:
    engine = _build_engine(
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
    engine = _build_engine(
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
