from powerrules.actions.base import Action
from powerrules.actions.power import (
    HibernateAction,
    RebootAction,
    ShutdownAction,
    SleepAction,
)
from powerrules.conditions.base import Condition
from powerrules.conditions.datetime import DateTimeCondition, TimeRange
from powerrules.conditions.operators import AndCondition, NotCondition, OrCondition
from powerrules.conditions.process import ProcessCondition
from powerrules.conditions.window import WindowCondition
from powerrules.config.models import (
    ActionConfiguration,
    ConditionConfiguration,
    DateTimeConditionConfiguration,
    ProcessConditionConfiguration,
    RuleConfiguration,
    RuleSetConfiguration,
    WindowConditionConfiguration,
)
from powerrules.engine.exceptions import ConfigurationError
from powerrules.engine.models import Rule, RuleSet
from powerrules.providers.clock import ClockProvider
from powerrules.providers.power import PowerProvider
from powerrules.providers.process import ProcessProvider
from powerrules.providers.window import WindowProvider


class ConfigurationBuilder:
    def __init__(
        self,
        clock_provider: ClockProvider,
        process_provider: ProcessProvider,
        power_provider: PowerProvider,
        window_provider: WindowProvider,
    ):
        self.clock_provider = clock_provider
        self.process_provider = process_provider
        self.power_provider = power_provider
        self.window_provider = window_provider

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
        return Rule(
            name=rule_configuration.name,
            enabled=rule_configuration.enabled,
            condition=self._build_condition(rule_configuration.conditions),
            action=self._build_action(rule_configuration.action),
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

        Args:
            configuration: DateTime condition configuration.

        Returns:
            The executable datetime condition.
        """
        if configuration.between is not None:
            return DateTimeCondition(
                clock_provider=self.clock_provider,
                time_range=TimeRange(
                    start=configuration.between.start,
                    end=configuration.between.end,
                ),
            )

        if configuration.weekday is not None:
            return DateTimeCondition(
                clock_provider=self.clock_provider,
                weekdays=frozenset(configuration.weekday),
            )

        raise RuntimeError("Invalid datetime condition configuration")

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

    def _build_action(self, configuration: ActionConfiguration) -> Action:
        """Build an action from its configuration.

        Args:
            configuration: Action configuration.

        Returns:
            The executable action.
        """
        match configuration.type:
            case "shutdown":
                return ShutdownAction(self.power_provider)
            case "sleep":
                return SleepAction(self.power_provider)
            case "hibernate":
                return HibernateAction(self.power_provider)
            case "reboot":
                return RebootAction(self.power_provider)

        raise ConfigurationError(f"Unsupported action type '{configuration.type}'")
