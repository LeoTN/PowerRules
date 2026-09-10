import platform
import time
from dataclasses import dataclass
from pathlib import Path

from powerrules.config.builder import ConfigurationBuilder
from powerrules.config.loader import ConfigurationLoader
from powerrules.engine.models import Rule, RuleEvaluationResult
from powerrules.engine.rule_engine import RuleEngine
from powerrules.platform.clock import SystemClockProvider
from powerrules.platform.linux.power import LinuxPowerProvider
from powerrules.platform.macos.power import MacOSPowerProvider
from powerrules.platform.process import PsUtilProcessProvider
from powerrules.platform.window import PyWinCtlWindowProvider
from powerrules.platform.windows.power import WindowsPowerProvider
from powerrules.providers.clock import ClockProvider
from powerrules.providers.power import PowerProvider
from powerrules.providers.process import ProcessProvider
from powerrules.providers.window import WindowProvider


class PowerRulesRuntime:
    """Coordinate PowerRules configuration loading and rule evaluation and action execution."""

    def run_once(self, configuration_path: Path) -> RuleEvaluationResult:
        """Load and evaluate the configured policy once.

        The policy is loaded only for this evaluation.

        Args:
            configuration_path: Path to the PowerRules policy file.

        Returns:
            The result of the rule evaluation.
        """
        rule_engine = self._build_rule_engine(configuration_path)

        return rule_engine.evaluate()

    def run_continuously(
        self,
        configuration_path: Path,
        evaluation_interval: float = 10.0,
        stop_on_match: bool = False,
    ) -> None:
        """Load a policy once and continuously evaluate it.

        The policy is loaded only once when the method starts.
        Changes to the policy file are ignored until the process is restarted.

        Args:
            configuration_path: Path to the PowerRules policy file.
            evaluation_interval: Delay between evaluations in seconds.
            stop_on_match: Stop the evaluation when a rule matches.

        Raises:
            ValueError: If the evaluation interval is less than or equal to zero.
            ConditionEvaluationError: If a condition cannot be evaluated.
            ActionExecutionError: If a matching action cannot be executed.
        """
        if evaluation_interval <= 0:
            raise ValueError("Evaluation interval must be greater than zero")

        rule_engine = self._build_rule_engine(configuration_path)
        last_matched_rule: Rule | None = None

        while True:
            matched_rule = rule_engine.find_match()

            if matched_rule is None:
                last_matched_rule = None

            elif matched_rule is not last_matched_rule:
                matched_rule.action.execute()
                last_matched_rule = matched_rule

                if stop_on_match:
                    break

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
            # Basically an API to interact with the power state of the OS
            power_provider=providers.power,
        ).build(configuration)

        return RuleEngine(rule_set.rules)


@dataclass(frozen=True)
class PlatformProviders:
    """Provide platform-specific system providers."""

    clock: ClockProvider
    process: ProcessProvider
    window: WindowProvider
    power: PowerProvider


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
            window=PyWinCtlWindowProvider(),
            power=WindowsPowerProvider(),
        )

    if system_name == "Linux":
        return PlatformProviders(
            clock=SystemClockProvider(),
            process=PsUtilProcessProvider(),
            window=PyWinCtlWindowProvider(),
            power=LinuxPowerProvider(),
        )

    # MacOS
    if system_name == "Darwin":
        return PlatformProviders(
            clock=SystemClockProvider(),
            process=PsUtilProcessProvider(),
            window=PyWinCtlWindowProvider(),
            power=MacOSPowerProvider(),
        )

    raise RuntimeError(f"Unsupported operating system: {system_name}")
