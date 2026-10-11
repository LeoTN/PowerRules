import platform
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from powerrules.config.builder import ConfigurationBuilder
from powerrules.config.loader import ConfigurationLoader
from powerrules.engine.models import Rule, RuleEvaluationResult
from powerrules.engine.rule_engine import RuleEngine
from powerrules.platform.clock import SystemClockProvider
from powerrules.platform.command import SubprocessCommandProvider
from powerrules.platform.linux.window import LinuxWindowProvider
from powerrules.platform.macos.window import MacOSWindowProvider
from powerrules.platform.process import PsUtilProcessProvider
from powerrules.platform.windows.window import WindowsWindowProvider
from powerrules.providers.clock import ClockProvider
from powerrules.providers.command import CommandProvider, Shell
from powerrules.providers.process import ProcessProvider
from powerrules.providers.window import WindowProvider


def describe_actions(rule: Rule) -> str:
    """Return a human-readable list of the actions of a rule.

    Args:
        rule: PowerRules rule whose actions are described.

    Returns:
        The quoted names of the actions separated by commas (e.g. "'Cleanup', 'Shutdown'").
    """
    return ", ".join(f"'{action.name}'" for action in rule.actions)


class PowerRulesRuntime:
    """Coordinate PowerRules configuration loading and rule evaluation and action execution."""

    def run_once(
        self,
        configuration_path: Path,
        dry_run: bool = False,
    ) -> RuleEvaluationResult:
        """Load and evaluate the configured policy once.

        The policy is loaded only for this evaluation.

        Args:
            configuration_path: Path to the PowerRules policy file.
            dry_run: If True, find the matching rule but do not execute its action.

        Returns:
            The result of the rule evaluation.

        Raises:
            ConditionEvaluationError: If a condition cannot be evaluated.
            ActionExecutionError: If a matching action cannot be executed.
        """
        rule_engine = self._build_rule_engine(configuration_path)

        return rule_engine.evaluate(dry_run=dry_run)

    def run_continuously(
        self,
        configuration_path: Path,
        evaluation_interval: float = 10.0,
        stop_on_match: bool = False,
        dry_run: bool = False,
    ) -> Iterator[RuleEvaluationResult]:
        """Load a policy once and continuously evaluate it, yielding each evaluation.

        The policy is loaded only once, before the first evaluation is yielded.
        Changes to the policy file are ignored until the process is restarted.

        The returned iterator yields the result of every evaluation, so the caller can react to matches (e.g. for logging) as they happen.
        If "stop_on_match" is True, the iterator stops right after yielding a result whose action was triggered.

        Args:
            configuration_path: Path to the PowerRules policy file.
            evaluation_interval: Delay between evaluations in seconds.
            stop_on_match: Stop the evaluation once a rule's action is triggered.
            dry_run: If True, find the matching rule but do not execute its action.

        Returns:
            An iterator yielding the result of every evaluation.

        Raises:
            ValueError: If the evaluation interval is less than or equal to zero.
                Raised immediately, before any evaluation takes place.
            ConditionEvaluationError: If a condition cannot be evaluated. Raised while iterating.
            ActionExecutionError: If a matching action cannot be executed. Raised while iterating.
        """
        if evaluation_interval <= 0:
            raise ValueError("Evaluation interval must be greater than zero")

        # The policy is loaded and validated as soon as this method is called, not deferred until the first iteration
        rule_engine = self._build_rule_engine(configuration_path)

        return self._evaluate_continuously(
            rule_engine=rule_engine,
            evaluation_interval=evaluation_interval,
            stop_on_match=stop_on_match,
            dry_run=dry_run,
        )

    @staticmethod
    def _evaluate_continuously(
        rule_engine: RuleEngine,
        evaluation_interval: float,
        stop_on_match: bool,
        dry_run: bool,
    ) -> Iterator[RuleEvaluationResult]:
        """Continuously evaluate a rule engine, yielding each evaluation.

        Args:
            rule_engine: The rule engine to evaluate.
            evaluation_interval: Delay between evaluations in seconds.
            stop_on_match: Stop the evaluation once a rule's action is triggered.
            dry_run: If True, report matching rules instead of executing their actions.

        Yields:
            The result of every evaluation.

        Raises:
            ConditionEvaluationError: If a condition cannot be evaluated.
            ActionExecutionError: If a matching action cannot be executed.
        """
        last_matched_rule: Rule | None = None

        while True:
            result = rule_engine.evaluate(
                previous_matched_rule=last_matched_rule,
                dry_run=dry_run,
            )
            last_matched_rule = result.matched_rule

            yield result

            if result.action_triggered and stop_on_match:
                return

            time.sleep(evaluation_interval)

    @staticmethod
    def _build_rule_engine(configuration_path: Path) -> RuleEngine:
        """Build a rule engine from a policy file.

        The policy is loaded and built exactly once per invocation.

        Args:
            configuration_path: Path to the PowerRules policy file.

        Returns:
            A configured rule engine.
        """
        configuration = ConfigurationLoader().load(configuration_path)

        # Fetch the correct providers for the current platform / OS
        providers = get_platform_providers()

        rule_set = ConfigurationBuilder(
            # Information about the current date and time
            clock_provider=providers.clock,
            # Information about processes
            process_provider=providers.process,
            # Information about windows (not the OS :D)
            window_provider=providers.window,
            # Runs the commands of the actions
            command_provider=providers.command,
            # Commands run in the directory of the policy by default, no matter where PowerRules was started
            base_directory=configuration_path.resolve().parent,
        ).build(configuration)

        return RuleEngine(rule_set.rules)


@dataclass(frozen=True)
class PlatformProviders:
    """Provide platform-specific system providers."""

    clock: ClockProvider
    process: ProcessProvider
    window: WindowProvider
    command: CommandProvider


def get_platform_providers() -> PlatformProviders:
    """Creates providers for interacting with the current operating system.

    Returns:
        Providers for the current platform.

    Raises:
        RuntimeError: If the current operating system is unsupported.
    """
    system_name = platform.system()

    if system_name == "Windows":
        return PlatformProviders(
            clock=SystemClockProvider(),
            process=PsUtilProcessProvider(),
            window=WindowsWindowProvider(),
            command=SubprocessCommandProvider(default_shell=Shell.POWERSHELL),
        )

    if system_name == "Linux":
        return PlatformProviders(
            clock=SystemClockProvider(),
            process=PsUtilProcessProvider(),
            window=LinuxWindowProvider(),
            command=SubprocessCommandProvider(default_shell=Shell.SH),
        )

    # MacOS
    if system_name == "Darwin":
        return PlatformProviders(
            clock=SystemClockProvider(),
            process=PsUtilProcessProvider(),
            window=MacOSWindowProvider(),
            command=SubprocessCommandProvider(default_shell=Shell.SH),
        )

    raise RuntimeError(f"Unsupported operating system: {system_name}")
