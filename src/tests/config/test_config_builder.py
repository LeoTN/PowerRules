from datetime import date, datetime, time
from pathlib import Path

import pytest

from powerrules.actions.command import DEFAULT_ACTION_TIMEOUT_SECONDS, CommandAction
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
from powerrules.config.builder import ConfigurationBuilder
from powerrules.config.models import (
    ActionConfiguration,
    ConditionConfiguration,
    DateRangeConfiguration,
    DateTimeConditionConfiguration,
    DateTimeRangeConfiguration,
    MatchConfiguration,
    ProcessConditionConfiguration,
    RuleConfiguration,
    RuleSetConfiguration,
    TimeRangeConfiguration,
    WindowConditionConfiguration,
)
from powerrules.engine.exceptions import ConfigurationError
from powerrules.engine.models import Rule, RuleSet
from powerrules.providers.command import Shell
from tests.mocks import (
    make_clock_provider,
    make_command_provider,
    make_process_provider,
    make_window_provider,
)

BASE_DIRECTORY = Path("policies")
DEFAULT_NOW = datetime(2026, 8, 22, 12, 0)

BetweenConfiguration = (
    TimeRangeConfiguration | DateRangeConfiguration | DateTimeRangeConfiguration
)


def _make_builder(
    *,
    clock_provider: object | None = None,
    process_provider: object | None = None,
    window_provider: object | None = None,
    command_provider: object | None = None,
    base_directory: Path = BASE_DIRECTORY,
) -> ConfigurationBuilder:
    """Create a builder. Providers which are not given are replaced by mocks."""
    return ConfigurationBuilder(
        clock_provider=(
            clock_provider
            if clock_provider is not None
            else make_clock_provider(DEFAULT_NOW)
        ),
        process_provider=(
            process_provider
            if process_provider is not None
            else make_process_provider()
        ),
        command_provider=(
            command_provider
            if command_provider is not None
            else make_command_provider()
        ),
        window_provider=(
            window_provider if window_provider is not None else make_window_provider()
        ),
        base_directory=base_directory,
    )  # type: ignore[arg-type]


def _make_process_condition(
    name: str = "backup.exe",
    exists: bool = False,
    match: MatchConfiguration | None = None,
) -> ConditionConfiguration:
    """Create the configuration of a process condition."""
    return ConditionConfiguration(
        process=ProcessConditionConfiguration(
            name=name,
            exists=exists,
            match=match if match is not None else MatchConfiguration(),
        )
    )


def _make_datetime_condition(
    between: BetweenConfiguration | None = None,
    weekday: list[Weekday] | None = None,
    month: list[Month] | None = None,
) -> ConditionConfiguration:
    """Create the configuration of a datetime condition."""
    return ConditionConfiguration(
        datetime=DateTimeConditionConfiguration(
            between=between,
            weekday=weekday,
            month=month,
        )
    )


def _make_rule_configuration(
    name: str = "Test rule",
    conditions: ConditionConfiguration | None = None,
    actions: list[ActionConfiguration] | None = None,
    enabled: bool = True,
) -> RuleConfiguration:
    """Create the configuration of a rule with a process condition and a command action by default."""
    return RuleConfiguration(
        name=name,
        enabled=enabled,
        conditions=(
            conditions if conditions is not None else _make_process_condition()
        ),
        actions=(
            actions if actions is not None else [ActionConfiguration(run="echo test")]
        ),
    )


def _build_rule(
    conditions: ConditionConfiguration | None = None,
    *,
    actions: list[ActionConfiguration] | None = None,
    builder: ConfigurationBuilder | None = None,
) -> Rule:
    """Build a single rule from the given condition and actions."""
    builder = builder if builder is not None else _make_builder()
    configuration = RuleSetConfiguration(
        rules=[_make_rule_configuration(conditions=conditions, actions=actions)]
    )

    return builder.build(configuration).rules[0]


def _build_datetime_condition(
    clock_provider: object,
    *,
    between: BetweenConfiguration | None = None,
    weekday: list[Weekday] | None = None,
    month: list[Month] | None = None,
) -> DateTimeCondition:
    """Build a datetime condition which uses the given clock provider."""
    rule = _build_rule(
        _make_datetime_condition(between, weekday, month),
        builder=_make_builder(clock_provider=clock_provider),
    )

    assert isinstance(rule.condition, DateTimeCondition)

    return rule.condition


################
# Rule set tests
################


def test_builder_builds_rule_set() -> None:
    rule_set = _make_builder().build(
        RuleSetConfiguration(rules=[_make_rule_configuration()])
    )

    assert isinstance(rule_set, RuleSet)
    assert len(rule_set.rules) == 1


def test_builder_builds_empty_rule_set() -> None:
    assert _make_builder().build(RuleSetConfiguration(rules=[])).rules == ()


def test_builder_preserves_rule_properties() -> None:
    rule_set = _make_builder().build(
        RuleSetConfiguration(
            rules=[_make_rule_configuration(name="Disabled rule", enabled=False)]
        )
    )

    assert rule_set.rules[0].name == "Disabled rule"
    assert rule_set.rules[0].enabled is False


def test_builder_preserves_rule_order() -> None:
    rule_set = _make_builder().build(
        RuleSetConfiguration(
            rules=[
                _make_rule_configuration(name="First test rule"),
                _make_rule_configuration(name="Second test rule"),
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

    rule = _build_rule(
        _make_process_condition(name="backup.exe", exists=True),
        builder=_make_builder(process_provider=process_provider),
    )

    assert isinstance(rule.condition, ProcessCondition)
    assert rule.condition.process_name == "backup.exe"
    assert rule.condition.expected_exists is True
    assert rule.condition.process_provider is process_provider
    assert rule.condition.matcher.match_type is MatchType.EXACT
    assert rule.condition.matcher.case_sensitive is True
    assert rule.condition.evaluate() is True


def test_builder_passes_match_configuration_to_process_condition() -> None:
    rule = _build_rule(
        _make_process_condition(
            name="BACKUP.*",
            exists=True,
            match=MatchConfiguration(type=MatchType.REGEX, case_sensitive=False),
        ),
        builder=_make_builder(process_provider=make_process_provider(["backup.exe"])),
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

    rule = _build_rule(
        ConditionConfiguration(
            window=WindowConditionConfiguration(title="My window title", exists=True)
        ),
        builder=_make_builder(window_provider=window_provider),
    )

    assert isinstance(rule.condition, WindowCondition)
    assert rule.condition.window_title == "My window title"
    assert rule.condition.expected_exists is True
    assert rule.condition.window_provider is window_provider
    assert rule.condition.matcher.match_type is MatchType.EXACT
    assert rule.condition.evaluate() is True


def test_builder_passes_match_configuration_to_window_condition() -> None:
    rule = _build_rule(
        ConditionConfiguration(
            window=WindowConditionConfiguration(
                title="my .* title",
                exists=True,
                match=MatchConfiguration(type=MatchType.REGEX, case_sensitive=False),
            )
        ),
        builder=_make_builder(
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
    clock_provider = make_clock_provider(DEFAULT_NOW)

    condition = _build_datetime_condition(
        clock_provider,
        between=TimeRangeConfiguration(start=time(22, 0), end=time(6, 0)),
    )

    assert condition.clock_provider is clock_provider
    assert condition.time_range == TimeRange(start=time(22, 0), end=time(6, 0))
    assert condition.datetime_range is None
    assert condition.weekdays is None
    assert condition.months is None


def test_builder_builds_weekday_condition() -> None:
    condition = _build_datetime_condition(
        make_clock_provider(DEFAULT_NOW),
        weekday=[Weekday.SATURDAY, Weekday.SUNDAY],
    )

    assert condition.weekdays == frozenset({Weekday.SATURDAY, Weekday.SUNDAY})
    assert condition.time_range is None
    assert condition.datetime_range is None
    assert condition.months is None


def test_builder_builds_time_range_with_weekday_condition() -> None:
    condition = _build_datetime_condition(
        make_clock_provider(DEFAULT_NOW),
        between=TimeRangeConfiguration(start=time(23, 0), end=time(1, 30)),
        weekday=[Weekday.MONDAY],
    )

    assert condition.time_range == TimeRange(start=time(23, 0), end=time(1, 30))
    assert condition.weekdays == frozenset({Weekday.MONDAY})


# The date range starts at midnight of the start date and ends (exclusive) at midnight of the end date
def test_builder_converts_date_range_to_datetime_range() -> None:
    clock_provider = make_clock_provider(datetime(2026, 8, 21, 12, 0))

    condition = _build_datetime_condition(
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
    condition = _build_datetime_condition(
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
    condition = _build_datetime_condition(
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

    condition = _build_datetime_condition(
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
    condition = _build_datetime_condition(
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
    rule = _build_rule(
        ConditionConfiguration(
            and_conditions=[
                _make_process_condition(name="backup.exe", exists=False),
                ConditionConfiguration(
                    or_conditions=[
                        _make_datetime_condition(
                            between=TimeRangeConfiguration(
                                start=time(23, 0), end=time(0, 0)
                            )
                        ),
                        _make_process_condition(name="maintenance.exe", exists=True),
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
    rule = _build_rule(ConditionConfiguration(not_condition=_make_process_condition()))

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
                actions=[ActionConfiguration(run="echo test")],
            )
        ]
    )

    with pytest.raises(ConfigurationError, match="does not contain a condition"):
        _make_builder().build(configuration)


##############
# Action tests
##############


def test_builder_builds_command_action_with_defaults() -> None:
    command_provider = make_command_provider()

    rule = _build_rule(
        actions=[ActionConfiguration(run="echo test")],
        builder=_make_builder(command_provider=command_provider),
    )

    assert len(rule.actions) == 1

    action = rule.actions[0]

    assert isinstance(action, CommandAction)
    assert action.command_provider is command_provider
    assert action.command == "echo test"
    assert action.working_directory == BASE_DIRECTORY
    assert action.name == "Action 1 of 1"
    assert action.rule_name == "Test rule"
    assert action.shell is None
    assert action.environment == {}
    assert action.timeout == DEFAULT_ACTION_TIMEOUT_SECONDS
    assert action.success_exit_codes == frozenset({0})
    assert action.wait is True
    assert action.continue_on_error is False


def test_builder_passes_configured_action_options() -> None:
    rule = _build_rule(
        actions=[
            ActionConfiguration(
                run="backup.sh",
                name="Backup",
                shell=Shell.BASH,
                working_directory=Path("scripts"),
                env={"KEY": "value"},
                timeout=5.5,
                success_exit_codes=[0, 2],
                continue_on_error=True,
            )
        ]
    )

    action = rule.actions[0]

    assert isinstance(action, CommandAction)
    assert action.command == "backup.sh"
    assert action.name == "Backup"
    assert action.shell is Shell.BASH
    assert action.working_directory == BASE_DIRECTORY / "scripts"
    assert action.environment == {"KEY": "value"}
    assert action.timeout == 5.5
    assert action.success_exit_codes == frozenset({0, 2})
    assert action.continue_on_error is True


def test_builder_builds_background_action() -> None:
    rule = _build_rule(actions=[ActionConfiguration(run="echo test", wait=False)])

    action = rule.actions[0]

    assert isinstance(action, CommandAction)
    assert action.wait is False


def test_builder_builds_action_without_time_limit() -> None:
    rule = _build_rule(actions=[ActionConfiguration(run="echo test", timeout=None)])

    action = rule.actions[0]

    assert isinstance(action, CommandAction)
    assert action.timeout is None


@pytest.mark.parametrize(
    ("working_directory", "expected"),
    [
        (Path("scripts"), BASE_DIRECTORY / "scripts"),
        (Path("scripts/nightly"), BASE_DIRECTORY / "scripts" / "nightly"),
        (Path("../shared"), BASE_DIRECTORY / ".." / "shared"),
    ],
)
def test_builder_resolves_relative_working_directory_against_base_directory(
    working_directory: Path,
    expected: Path,
) -> None:
    rule = _build_rule(
        actions=[
            ActionConfiguration(run="echo test", working_directory=working_directory)
        ]
    )

    action = rule.actions[0]

    assert isinstance(action, CommandAction)
    assert action.working_directory == expected


def test_builder_keeps_absolute_working_directory(tmp_path: Path) -> None:
    absolute_directory = tmp_path / "other"

    rule = _build_rule(
        actions=[
            ActionConfiguration(run="echo test", working_directory=absolute_directory)
        ]
    )

    action = rule.actions[0]

    assert isinstance(action, CommandAction)
    assert action.working_directory == absolute_directory


def test_builder_keeps_action_order_and_shares_command_provider() -> None:
    command_provider = make_command_provider()

    rule = _build_rule(
        actions=[
            ActionConfiguration(run="first"),
            ActionConfiguration(run="second"),
            ActionConfiguration(run="third"),
        ],
        builder=_make_builder(command_provider=command_provider),
    )

    assert [action.command for action in rule.actions] == ["first", "second", "third"]  # type: ignore[attr-defined]
    assert all(action.command_provider is command_provider for action in rule.actions)  # type: ignore[attr-defined]


def test_builder_names_unnamed_actions_by_position() -> None:
    rule = _build_rule(
        actions=[
            ActionConfiguration(run="first"),
            ActionConfiguration(run="second", name="Custom"),
            ActionConfiguration(run="third"),
        ]
    )

    assert [action.name for action in rule.actions] == [
        "Action 1 of 3",
        "Custom",
        "Action 3 of 3",
    ]


def test_builder_numbers_actions_per_rule() -> None:
    rule_set = _make_builder().build(
        RuleSetConfiguration(
            rules=[
                _make_rule_configuration(
                    name="First rule",
                    actions=[ActionConfiguration(run="echo test")],
                ),
                _make_rule_configuration(
                    name="Second rule",
                    actions=[
                        ActionConfiguration(run="first"),
                        ActionConfiguration(run="second"),
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

    rule = _build_rule(
        actions=[ActionConfiguration(run="echo test", env={"KEY": "value"})],
        builder=_make_builder(command_provider=command_provider),
    )

    rule.actions[0].execute()

    command_provider.run.assert_called_once()

    request = command_provider.run.call_args.args[0]

    assert request.command == "echo test"
    assert request.working_directory == BASE_DIRECTORY
    assert request.environment["KEY"] == "value"
