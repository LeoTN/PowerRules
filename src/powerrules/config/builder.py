from datetime import datetime, time
from pathlib import Path

from powerrules.actions.command import CommandAction
from powerrules.conditions.base import Condition
from powerrules.conditions.datetime import DateTimeCondition, DateTimeRange, TimeRange
from powerrules.conditions.operators import AndCondition, NotCondition, OrCondition
from powerrules.conditions.process import ProcessCondition
from powerrules.conditions.window import WindowCondition
from powerrules.config.models import (
    ActionConfiguration,
    ConditionConfiguration,
    DateRangeConfiguration,
    DateTimeConditionConfiguration,
    DateTimeRangeConfiguration,
    ProcessConditionConfiguration,
    RuleConfiguration,
    RuleSetConfiguration,
    TimeRangeConfiguration,
    WindowConditionConfiguration,
)
from powerrules.engine.exceptions import ConfigurationError
from powerrules.engine.models import Rule, RuleSet
from powerrules.providers.clock import ClockProvider
from powerrules.providers.command import CommandProvider
from powerrules.providers.process import ProcessProvider
from powerrules.providers.window import WindowProvider


class ConfigurationBuilder:
    def __init__(
        self,
        clock_provider: ClockProvider,
        process_provider: ProcessProvider,
        command_provider: CommandProvider,
        window_provider: WindowProvider,
        base_directory: Path,
    ):
        """Create a builder for the rules of one policy.

        Args:
            clock_provider: Provider for the current date and time.
            process_provider: Provider for the existing processes.
            command_provider: Provider which runs the commands of the actions.
            window_provider: Provider for the existing windows.
            base_directory: Directory of the policy file. Commands run there by default,
                and relative working directories of actions are resolved against it.
        """
        self.clock_provider = clock_provider
        self.process_provider = process_provider
        self.command_provider = command_provider
        self.window_provider = window_provider
        self.base_directory = base_directory

    def build(self, configuration: RuleSetConfiguration) -> RuleSet:
        """Build a rule set from the validated configuration. This allows the rule engine to process the rules.

        NOTE: The builder dos NOT validate the configuration. This needs to be done in advance.

        Args:
            configuration: Validated (with Pydantic) PowerRules configuration.

        Returns:
            The executable rule set.
        """
        rules = tuple(
            self._build_rule(rule_configuration)
            for rule_configuration in configuration.rules
        )

        return RuleSet(rules=rules)

    def _build_rule(self, rule_configuration: RuleConfiguration) -> Rule:
        """Build a domain rule  (which can be processed by the rule engine) from its configuration.

        Args:
            rule_configuration: Configuration of the rule.

        Returns:
            The executable rule.
        """
        action_count = len(rule_configuration.actions)

        return Rule(
            name=rule_configuration.name,
            enabled=rule_configuration.enabled,
            condition=self._build_condition(rule_configuration.conditions),
            actions=tuple(
                self._build_action(
                    action_configuration,
                    rule_name=rule_configuration.name,
                    position=position,
                    action_count=action_count,
                )
                for position, action_configuration in enumerate(
                    rule_configuration.actions, start=1
                )
            ),
        )

    def _build_condition(
        self,
        condition_configuration: ConditionConfiguration,
    ) -> Condition:
        """Build a condition from its configuration.

        Args:
            condition_configuration: Configuration of the condition.

        Returns:
            The executable condition.
        """
        if condition_configuration.and_conditions is not None:
            return AndCondition(
                conditions=tuple(
                    self._build_condition(condition)
                    for condition in condition_configuration.and_conditions
                )
            )

        if condition_configuration.or_conditions is not None:
            return OrCondition(
                conditions=tuple(
                    self._build_condition(condition)
                    for condition in condition_configuration.or_conditions
                )
            )

        if condition_configuration.not_condition is not None:
            return NotCondition(
                condition=self._build_condition(condition_configuration.not_condition)
            )

        if condition_configuration.process is not None:
            return self._build_process_condition(condition_configuration.process)

        if condition_configuration.datetime is not None:
            return self._build_datetime_condition(condition_configuration.datetime)

        if condition_configuration.window is not None:
            return self._build_window_condition(condition_configuration.window)

        raise ConfigurationError("Condition configuration does not contain a condition")

    def _build_process_condition(
        self,
        configuration: ProcessConditionConfiguration,
    ) -> ProcessCondition:
        """Build a process condition.

        Args:
            configuration: Process condition configuration.

        Returns:
            The executable process condition.
        """
        return ProcessCondition(
            process_name=configuration.name,
            expected_exists=configuration.exists,
            process_provider=self.process_provider,
            match_type=configuration.match.type,
            case_sensitive=configuration.match.case_sensitive,
        )

    def _build_datetime_condition(
        self,
        configuration: DateTimeConditionConfiguration,
    ) -> DateTimeCondition:
        """Build a datetime condition from its configuration.

        A date range is converted to a datetime range, which starts at the
        beginning of the start day and ends at the beginning of the end day (the start is inclusive and the end is exclusive).

        Example: A date range of 2026-08-21 to 2026-08-22 is converted to a datetime range of 2026-08-21 00:00:00 to 2026-08-22 00:00:00.

        Args:
            configuration: DateTime condition configuration.

        Returns:
            The executable datetime condition.
        """
        time_range: TimeRange | None = None
        datetime_range: DateTimeRange | None = None

        # The correct configuration model is used depending on the detected type (date, time or datetime range)
        match configuration.between:
            # The date range is converted to a date time range
            case DateRangeConfiguration(start=start, end=end):
                datetime_range = DateTimeRange(
                    start=datetime.combine(start, time.min),
                    end=datetime.combine(end, time.min),
                )
            case TimeRangeConfiguration(start=start, end=end):
                time_range = TimeRange(start=start, end=end)
            case DateTimeRangeConfiguration(start=start, end=end):
                datetime_range = DateTimeRange(start=start, end=end)

        weekdays = (
            frozenset(configuration.weekday)
            if configuration.weekday is not None
            else None
        )
        months = (
            frozenset(configuration.month) if configuration.month is not None else None
        )

        return DateTimeCondition(
            clock_provider=self.clock_provider,
            time_range=time_range,
            datetime_range=datetime_range,
            weekdays=weekdays,
            months=months,
        )

    def _build_window_condition(
        self, configuration: WindowConditionConfiguration
    ) -> WindowCondition:
        """Build a window condition from its configuration.

        Args:
            configuration: Window condition configuration.

        Returns:
            The executable window condition.
        """
        return WindowCondition(
            window_title=configuration.title,
            expected_exists=configuration.exists,
            window_provider=self.window_provider,
            match_type=configuration.match.type,
            case_sensitive=configuration.match.case_sensitive,
        )

    def _build_action(
        self,
        configuration: ActionConfiguration,
        rule_name: str,
        position: int,
        action_count: int,
    ) -> CommandAction:
        """Build an action from its configuration.

        Args:
            configuration: Configuration of the action.
            rule_name: Name of the rule the action belongs to.
            position: Position of the action within its rule, starting at 1.
            action_count: Number of actions of the rule.

        Returns:
            The executable action.
        """
        # An absolute working directory replaces the base directory when the paths are joined
        working_directory = (
            self.base_directory / configuration.working_directory
            if configuration.working_directory is not None
            else self.base_directory
        )

        return CommandAction(
            command_provider=self.command_provider,
            command=configuration.run,
            working_directory=working_directory,
            name=(
                configuration.name
                if configuration.name is not None
                else f"Action {position} of {action_count}"
            ),
            rule_name=rule_name,
            shell=configuration.shell,
            environment=configuration.env,
            timeout=configuration.timeout,
            success_exit_codes=configuration.success_exit_codes,
            wait=configuration.wait,
            continue_on_error=configuration.continue_on_error,
        )
