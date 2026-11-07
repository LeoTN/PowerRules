from datetime import date, datetime, time
from pathlib import Path

import pytest

from powerrules.actions.command import DEFAULT_COMMAND_TIMEOUT_SECONDS
from powerrules.conditions.command import CommandCondition
from powerrules.conditions.datetime import (
    DateTimeCondition,
    DateTimeRange,
    Month,
    TimeRange,
    Weekday,
)
from powerrules.conditions.matcher import MatchType
from powerrules.conditions.operators import AndCondition, NotCondition, OrCondition
from powerrules.conditions.process import ProcessCondition
from powerrules.conditions.window import WindowCondition
from powerrules.config.models import (
    ConditionConfiguration,
    DateRangeConfiguration,
    DateTimeRangeConfiguration,
    MatchConfiguration,
    RuleConfiguration,
    RuleSetConfiguration,
    TimeRangeConfiguration,
)
from powerrules.engine.exceptions import ConfigurationError
from powerrules.engine.models import RuleSet
from powerrules.providers.command import CommandResult, Shell
from tests.factories import (
    build_command_action,
    build_command_condition,
    build_datetime_condition,
    build_rule,
    make_action_configuration,
    make_clock_provider,
    make_command_condition_configuration,
    make_command_provider,
    make_configuration_builder,
    make_datetime_condition_configuration,
    make_files_verifier,
    make_process_condition_configuration,
    make_process_provider,
    make_rule_configuration,
    make_window_condition_configuration,
    make_window_provider,
)
from tests.helpers import (
    BACKUP_SCRIPT_NAME,
    DEFAULT_BASE_DIRECTORY,
    DEFAULT_NOW_SATURDAY_NOON,
    SCRIPT_DIRECTORY_NAME,
)

################
# Rule set tests
################


def test_builder_builds_rule_set() -> None:
    rule_set = make_configuration_builder().build(
        RuleSetConfiguration(rules=[make_rule_configuration()])
    )

    assert isinstance(rule_set, RuleSet)
    assert len(rule_set.rules) == 1


def test_builder_builds_empty_rule_set() -> None:
    rule_set = make_configuration_builder().build(RuleSetConfiguration(rules=[]))

    assert rule_set.rules == ()


def test_builder_preserves_rule_properties() -> None:
    rule_set = make_configuration_builder().build(
        RuleSetConfiguration(
            rules=[make_rule_configuration(name="Disabled rule", enabled=False)]
        )
    )

    assert rule_set.rules[0].name == "Disabled rule"
    assert rule_set.rules[0].enabled is False


def test_builder_preserves_rule_order() -> None:
    rule_set = make_configuration_builder().build(
        RuleSetConfiguration(
            rules=[
                make_rule_configuration(name="First test rule"),
                make_rule_configuration(name="Second test rule"),
            ]
        )
    )

    assert [rule.name for rule in rule_set.rules] == [
        "First test rule",
        "Second test rule",
    ]


#########################
# Process condition tests
#########################


def test_builder_builds_process_condition() -> None:
    process_provider = make_process_provider(["backup.exe"])

    rule = build_rule(
        make_process_condition_configuration(name="backup.exe", exists=True),
        builder=make_configuration_builder(process_provider=process_provider),
    )

    assert isinstance(rule.condition, ProcessCondition)
    assert rule.condition.process_name == "backup.exe"
    assert rule.condition.expected_exists is True
    assert rule.condition.process_provider is process_provider
    assert rule.condition.matcher.match_type is MatchType.EXACT
    assert rule.condition.matcher.case_sensitive is True
    assert rule.condition.evaluate() is True


def test_builder_passes_match_configuration_to_process_condition() -> None:
    rule = build_rule(
        make_process_condition_configuration(
            name="BACKUP.*",
            exists=True,
            match=MatchConfiguration(type=MatchType.REGEX, case_sensitive=False),
        ),
        builder=make_configuration_builder(
            process_provider=make_process_provider(["backup.exe"])
        ),
    )

    assert isinstance(rule.condition, ProcessCondition)
    assert rule.condition.matcher.match_type is MatchType.REGEX
    assert rule.condition.matcher.case_sensitive is False
    assert rule.condition.evaluate() is True


########################
# Window condition tests
########################


def test_builder_builds_window_condition() -> None:
    window_provider = make_window_provider(["My window title"])

    rule = build_rule(
        make_window_condition_configuration("My window title"),
        builder=make_configuration_builder(window_provider=window_provider),
    )

    assert isinstance(rule.condition, WindowCondition)
    assert rule.condition.window_title == "My window title"
    assert rule.condition.expected_exists is True
    assert rule.condition.window_provider is window_provider
    assert rule.condition.matcher.match_type is MatchType.EXACT
    assert rule.condition.evaluate() is True


def test_builder_passes_match_configuration_to_window_condition() -> None:
    rule = build_rule(
        make_window_condition_configuration(
            "my .* title",
            match=MatchConfiguration(type=MatchType.REGEX, case_sensitive=False),
        ),
        builder=make_configuration_builder(
            window_provider=make_window_provider(["My Window Title"])
        ),
    )

    assert isinstance(rule.condition, WindowCondition)
    assert rule.condition.matcher.match_type is MatchType.REGEX
    assert rule.condition.matcher.case_sensitive is False
    assert rule.condition.evaluate() is True


##########################
# Datetime condition tests
##########################


def test_builder_builds_time_range_condition() -> None:
    clock_provider = make_clock_provider(DEFAULT_NOW_SATURDAY_NOON)

    condition = build_datetime_condition(
        clock_provider,
        between=TimeRangeConfiguration(start=time(22, 0), end=time(6, 0)),
    )

    assert condition.clock_provider is clock_provider
    assert condition.time_range == TimeRange(start=time(22, 0), end=time(6, 0))
    assert condition.datetime_range is None
    assert condition.weekdays is None
    assert condition.months is None


def test_builder_builds_weekday_condition() -> None:
    condition = build_datetime_condition(
        make_clock_provider(DEFAULT_NOW_SATURDAY_NOON),
        weekday=[Weekday.SATURDAY, Weekday.SUNDAY],
    )

    assert condition.weekdays == frozenset({Weekday.SATURDAY, Weekday.SUNDAY})
    assert condition.time_range is None
    assert condition.datetime_range is None
    assert condition.months is None


def test_builder_builds_time_range_with_weekday_condition() -> None:
    condition = build_datetime_condition(
        make_clock_provider(DEFAULT_NOW_SATURDAY_NOON),
        between=TimeRangeConfiguration(start=time(23, 0), end=time(1, 30)),
        weekday=[Weekday.MONDAY],
    )

    assert condition.time_range == TimeRange(start=time(23, 0), end=time(1, 30))
    assert condition.weekdays == frozenset({Weekday.MONDAY})


# The date range starts at midnight of the start date and ends (exclusive) at midnight of the end date
def test_builder_converts_date_range_to_datetime_range() -> None:
    clock_provider = make_clock_provider(datetime(2026, 8, 21, 12, 0))

    condition = build_datetime_condition(
        clock_provider,
        between=DateRangeConfiguration(start=date(2026, 8, 21), end=date(2026, 8, 22)),
    )

    assert condition.datetime_range == DateTimeRange(
        start=datetime(2026, 8, 21, 0, 0),
        end=datetime(2026, 8, 22, 0, 0),
    )
    assert condition.time_range is None
    assert condition.weekdays is None
    assert condition.evaluate() is True

    # The built condition does not match the end date anymore
    clock_provider.now.return_value = datetime(2026, 8, 22, 0, 0)

    assert condition.evaluate() is False


def test_builder_builds_datetime_range_condition() -> None:
    condition = build_datetime_condition(
        make_clock_provider(datetime(2026, 8, 21, 23, 0)),
        between=DateTimeRangeConfiguration(
            start=datetime(2026, 8, 21, 18, 0),
            end=datetime(2026, 8, 22, 6, 0),
        ),
    )

    assert condition.datetime_range == DateTimeRange(
        start=datetime(2026, 8, 21, 18, 0),
        end=datetime(2026, 8, 22, 6, 0),
    )
    assert condition.time_range is None
    assert condition.weekdays is None
    assert condition.evaluate() is True


def test_builder_builds_date_range_with_weekday_condition() -> None:
    condition = build_datetime_condition(
        make_clock_provider(datetime(2026, 8, 21, 12, 0)),
        between=DateRangeConfiguration(start=date(2026, 8, 21), end=date(2026, 8, 22)),
        weekday=[Weekday.FRIDAY],
    )

    assert condition.datetime_range == DateTimeRange(
        start=datetime(2026, 8, 21, 0, 0),
        end=datetime(2026, 8, 22, 0, 0),
    )
    assert condition.weekdays == frozenset({Weekday.FRIDAY})
    assert condition.time_range is None
    assert condition.evaluate() is True


def test_builder_builds_month_condition() -> None:
    clock_provider = make_clock_provider(datetime(2026, 8, 21, 12, 0))

    condition = build_datetime_condition(
        clock_provider,
        month=[Month.AUGUST, Month.SEPTEMBER],
    )

    assert condition.months == frozenset({Month.AUGUST, Month.SEPTEMBER})
    assert condition.time_range is None
    assert condition.datetime_range is None
    assert condition.weekdays is None
    assert condition.evaluate() is True

    clock_provider.now.return_value = datetime(2026, 10, 1, 12, 0)

    assert condition.evaluate() is False


def test_builder_builds_month_with_other_criteria() -> None:
    condition = build_datetime_condition(
        make_clock_provider(datetime(2026, 8, 21, 23, 0)),
        between=TimeRangeConfiguration(start=time(22, 0), end=time(6, 0)),
        weekday=[Weekday.FRIDAY],
        month=[Month.AUGUST],
    )

    assert condition.time_range == TimeRange(start=time(22, 0), end=time(6, 0))
    assert condition.weekdays == frozenset({Weekday.FRIDAY})
    assert condition.months == frozenset({Month.AUGUST})
    assert condition.datetime_range is None
    assert condition.evaluate() is True


#########################
# Logical condition tests
#########################


def test_builder_builds_nested_conditions() -> None:
    rule = build_rule(
        ConditionConfiguration(
            and_conditions=[
                make_process_condition_configuration(name="backup.exe", exists=False),
                ConditionConfiguration(
                    or_conditions=[
                        make_datetime_condition_configuration(
                            between=TimeRangeConfiguration(
                                start=time(23, 0), end=time(0, 0)
                            )
                        ),
                        make_process_condition_configuration(
                            name="maintenance.exe", exists=True
                        ),
                    ]
                ),
            ]
        )
    )

    assert isinstance(rule.condition, AndCondition)
    assert isinstance(rule.condition.conditions[0], ProcessCondition)
    assert isinstance(rule.condition.conditions[1], OrCondition)
    assert isinstance(rule.condition.conditions[1].conditions[0], DateTimeCondition)
    assert isinstance(rule.condition.conditions[1].conditions[1], ProcessCondition)


def test_builder_builds_not_condition() -> None:
    rule = build_rule(
        ConditionConfiguration(not_condition=make_process_condition_configuration())
    )

    assert isinstance(rule.condition, NotCondition)
    assert isinstance(rule.condition.condition, ProcessCondition)


# Not reachable through the validated configuration, but the builder must not return nothing
def test_builder_raises_for_configuration_without_condition() -> None:
    # The validation of Pydantic already rejects this configuration, so it is assembled without validation
    configuration = RuleSetConfiguration.model_construct(
        rules=[
            RuleConfiguration.model_construct(
                name="Test rule",
                enabled=True,
                conditions=ConditionConfiguration.model_construct(),
                actions=[make_action_configuration()],
            )
        ]
    )

    with pytest.raises(ConfigurationError, match="does not contain a condition"):
        make_configuration_builder().build(configuration)


##############
# Action tests
##############


def test_builder_builds_command_action_with_defaults() -> None:
    command_provider = make_command_provider()

    action = build_command_action(
        builder=make_configuration_builder(command_provider=command_provider)
    )

    assert action.command_provider is command_provider
    assert action.command == "echo test"
    assert action.working_directory == DEFAULT_BASE_DIRECTORY
    assert action.name == "Action 1 of 1"
    assert action.rule_name == "Test rule"
    assert action.shell is None
    assert action.environment == {}
    assert action.timeout == DEFAULT_COMMAND_TIMEOUT_SECONDS
    assert action.success_exit_codes == frozenset({0})
    assert action.wait is True
    assert action.continue_on_error is False


def test_builder_passes_configured_action_options() -> None:
    action = build_command_action(
        make_action_configuration(
            run=BACKUP_SCRIPT_NAME,
            name="Backup",
            shell=Shell.BASH,
            working_directory=Path(SCRIPT_DIRECTORY_NAME),
            env={"KEY": "value"},
            timeout=5.5,
            success_exit_codes=[0, 2],
            continue_on_error=True,
        )
    )

    assert action.command == BACKUP_SCRIPT_NAME
    assert action.name == "Backup"
    assert action.shell is Shell.BASH
    assert action.working_directory == DEFAULT_BASE_DIRECTORY / SCRIPT_DIRECTORY_NAME
    assert action.environment == {"KEY": "value"}
    assert action.timeout == 5.5
    assert action.success_exit_codes == frozenset({0, 2})
    assert action.continue_on_error is True


def test_builder_builds_background_action() -> None:
    action = build_command_action(make_action_configuration(wait=False))

    assert action.wait is False


def test_builder_builds_action_without_time_limit() -> None:
    action = build_command_action(make_action_configuration(timeout=None))

    assert action.timeout is None


@pytest.mark.parametrize(
    ("working_directory", "expected"),
    [
        (Path(SCRIPT_DIRECTORY_NAME), DEFAULT_BASE_DIRECTORY / SCRIPT_DIRECTORY_NAME),
        (
            Path("scripts/nightly"),
            DEFAULT_BASE_DIRECTORY / SCRIPT_DIRECTORY_NAME / "nightly",
        ),
        (Path("../shared"), DEFAULT_BASE_DIRECTORY / ".." / "shared"),
    ],
)
def test_builder_resolves_relative_working_directory_against_base_directory(
    working_directory: Path,
    expected: Path,
) -> None:
    action = build_command_action(
        make_action_configuration(working_directory=working_directory)
    )

    assert action.working_directory == expected


def test_builder_keeps_absolute_working_directory(tmp_path: Path) -> None:
    absolute_directory = tmp_path / "other"

    action = build_command_action(
        make_action_configuration(working_directory=absolute_directory)
    )

    assert action.working_directory == absolute_directory


def test_builder_keeps_action_order_and_shares_command_provider() -> None:
    command_provider = make_command_provider()

    rule = build_rule(
        actions=[
            make_action_configuration(run="first"),
            make_action_configuration(run="second"),
            make_action_configuration(run="third"),
        ],
        builder=make_configuration_builder(command_provider=command_provider),
    )

    assert [action.command for action in rule.actions] == ["first", "second", "third"]  # type: ignore[attr-defined]
    assert all(action.command_provider is command_provider for action in rule.actions)  # type: ignore[attr-defined]


def test_builder_names_unnamed_actions_by_position() -> None:
    rule = build_rule(
        actions=[
            make_action_configuration(run="first"),
            make_action_configuration(run="second", name="Custom"),
            make_action_configuration(run="third"),
        ]
    )

    assert [action.name for action in rule.actions] == [
        "Action 1 of 3",
        "Custom",
        "Action 3 of 3",
    ]


def test_builder_numbers_actions_per_rule() -> None:
    rule_set = make_configuration_builder().build(
        RuleSetConfiguration(
            rules=[
                make_rule_configuration(name="First rule"),
                make_rule_configuration(
                    name="Second rule",
                    actions=[
                        make_action_configuration(run="first"),
                        make_action_configuration(run="second"),
                    ],
                ),
            ]
        )
    )

    first_rule, second_rule = rule_set.rules

    assert [action.name for action in first_rule.actions] == ["Action 1 of 1"]
    assert [action.name for action in second_rule.actions] == [
        "Action 1 of 2",
        "Action 2 of 2",
    ]
    assert [action.rule_name for action in second_rule.actions] == [  # type: ignore[attr-defined]
        "Second rule",
        "Second rule",
    ]


def test_builder_builds_executable_action() -> None:
    command_provider = make_command_provider()

    action = build_command_action(
        make_action_configuration(env={"KEY": "value"}),
        builder=make_configuration_builder(command_provider=command_provider),
    )

    action.execute()

    command_provider.run.assert_called_once()

    request = command_provider.run.call_args.args[0]

    assert request.command == "echo test"
    assert request.working_directory == DEFAULT_BASE_DIRECTORY
    assert request.environment["KEY"] == "value"


#####################
# Trusted files tests
#####################


def test_builder_joins_trusted_files_with_base_directory_without_resolving_them(
    tmp_path: Path,
) -> None:
    absolute_file = tmp_path / "absolute.sh"

    action = build_command_action(
        make_action_configuration(trusted_files=["scripts/a.sh", str(absolute_file)])
    )

    # Symbolic links are resolved by the verifier on every check, not once here
    assert action.trusted_files == (
        DEFAULT_BASE_DIRECTORY / SCRIPT_DIRECTORY_NAME / "a.sh",
        absolute_file,
    )


def test_builder_passes_files_verifier_to_actions() -> None:
    files_verifier = make_files_verifier()

    action = build_command_action(
        make_action_configuration(trusted_files=["a.sh"]),
        builder=make_configuration_builder(files_verifier=files_verifier),
    )

    assert action.files_verifier is files_verifier


def test_builder_builds_actions_without_trusted_files() -> None:
    assert build_command_action().trusted_files == ()


#########################
# Command condition tests
#########################


def test_builder_builds_command_condition_with_defaults() -> None:
    command_provider = make_command_provider()

    condition = build_command_condition(
        builder=make_configuration_builder(command_provider=command_provider)
    )

    runner = condition.runner
    assert runner.command_provider is command_provider
    assert runner.command == "echo test"
    assert runner.working_directory == DEFAULT_BASE_DIRECTORY
    assert runner.timeout == DEFAULT_COMMAND_TIMEOUT_SECONDS
    assert runner.shell is None
    assert runner.environment == {}
    assert runner.success_exit_codes == frozenset({0})
    assert runner.wait is True
    assert runner.stdout_matcher is None
    assert runner.stderr_matcher is None
    assert runner.trusted_files == ()
    assert runner.files_verifier is None


def test_builder_passes_configured_command_condition_options() -> None:
    condition = build_command_condition(
        make_command_condition_configuration(
            run=BACKUP_SCRIPT_NAME,
            shell="bash",
            working_directory=SCRIPT_DIRECTORY_NAME,
            env={"KEY": "value"},
            timeout=5.5,
            success_exit_codes=[0, 2],
            trusted_files=["scripts/a.sh"],
        )
    )

    runner = condition.runner
    assert runner.command == BACKUP_SCRIPT_NAME
    assert runner.shell is Shell.BASH
    assert runner.working_directory == DEFAULT_BASE_DIRECTORY / SCRIPT_DIRECTORY_NAME
    assert runner.environment == {"KEY": "value"}
    assert runner.timeout == 5.5
    assert runner.success_exit_codes == frozenset({0, 2})
    assert runner.trusted_files == (
        DEFAULT_BASE_DIRECTORY / SCRIPT_DIRECTORY_NAME / "a.sh",
    )


def test_builder_builds_command_condition_without_time_limit() -> None:
    condition = build_command_condition(
        make_command_condition_configuration(timeout=None)
    )

    assert condition.runner.timeout is None


def test_builder_keeps_absolute_working_directory_of_command_condition(
    tmp_path: Path,
) -> None:
    condition = build_command_condition(
        make_command_condition_configuration(working_directory=str(tmp_path / "other"))
    )

    assert condition.runner.working_directory == tmp_path / "other"


def test_builder_builds_output_matchers_of_command_condition() -> None:
    condition = build_command_condition(
        make_command_condition_configuration(
            stdout={
                "value": "active",
                "match": {"type": "contains", "case_sensitive": False},
            },
            stderr={"value": ".*error.*", "match": {"type": "regex"}},
        )
    )

    stdout_matcher = condition.runner.stdout_matcher
    stderr_matcher = condition.runner.stderr_matcher

    assert stdout_matcher is not None
    assert stdout_matcher.pattern == "active"
    assert stdout_matcher.match_type is MatchType.CONTAINS
    assert stdout_matcher.case_sensitive is False
    assert stdout_matcher.matches("Service is ACTIVE") is True

    assert stderr_matcher is not None
    assert stderr_matcher.match_type is MatchType.REGEX
    assert stderr_matcher.case_sensitive is True
    assert stderr_matcher.matches("an error\nhappened") is True


def test_builder_passes_condition_files_verifier_to_command_conditions_only() -> None:
    files_verifier = make_files_verifier()
    condition_files_verifier = make_files_verifier()
    builder = make_configuration_builder(
        files_verifier=files_verifier,
        condition_files_verifier=condition_files_verifier,
    )

    condition = build_command_condition(
        make_command_condition_configuration(trusted_files=["a.sh"]), builder=builder
    )
    action = build_command_action(
        make_action_configuration(trusted_files=["a.sh"]), builder=builder
    )

    assert condition.runner.files_verifier is condition_files_verifier
    assert action.files_verifier is files_verifier


@pytest.mark.parametrize(("exit_code", "expected"), [(0, True), (1, False)])
def test_builder_builds_executable_command_condition(
    exit_code: int,
    expected: bool,
) -> None:
    command_provider = make_command_provider(CommandResult(exit_code=exit_code))

    condition = build_command_condition(
        make_command_condition_configuration(env={"KEY": "value"}),
        builder=make_configuration_builder(command_provider=command_provider),
    )

    assert condition.evaluate() is expected

    request = command_provider.run.call_args.args[0]

    assert request.command == "echo test"
    assert request.working_directory == DEFAULT_BASE_DIRECTORY
    # A condition does not receive the variables of an action
    assert request.environment == {"KEY": "value"}


def test_builder_builds_command_condition_within_logical_conditions() -> None:
    rule = build_rule(
        ConditionConfiguration(
            and_conditions=[
                make_process_condition_configuration(name="backup.exe", exists=False),
                ConditionConfiguration(
                    not_condition=make_command_condition_configuration()
                ),
            ]
        )
    )

    assert isinstance(rule.condition, AndCondition)
    assert isinstance(rule.condition.conditions[1], NotCondition)
    assert isinstance(rule.condition.conditions[1].condition, CommandCondition)


def test_builder_builds_output_matchers_of_actions() -> None:
    action = build_command_action(
        make_action_configuration(
            stdout={"value": "ok", "match": {"type": "contains"}},
            stderr={"value": "", "match": {"case_sensitive": False}},
        )
    )

    assert action.stdout_matcher is not None
    assert action.stdout_matcher.pattern == "ok"
    assert action.stdout_matcher.match_type is MatchType.CONTAINS
    assert action.stderr_matcher is not None
    assert action.stderr_matcher.case_sensitive is False


def test_builder_builds_actions_without_output_matchers_by_default() -> None:
    action = build_command_action()

    assert action.stdout_matcher is None
    assert action.stderr_matcher is None
