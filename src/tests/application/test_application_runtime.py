from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from powerrules.application.runtime import (
    PlatformProviders,
    PowerRulesRuntime,
    get_platform_providers,
)
from powerrules.engine.exceptions import ConditionEvaluationError
from powerrules.engine.models import Rule, RuleEvaluationResult, RuleSet
from powerrules.platform.clock import SystemClockProvider
from powerrules.platform.linux.power import LinuxPowerProvider
from powerrules.platform.macos.power import MacOSPowerProvider
from powerrules.platform.process import PsUtilProcessProvider
from powerrules.platform.window import PyWinCtlWindowProvider
from powerrules.platform.windows.power import WindowsPowerProvider
from tests.dummies import Dummy_Action, Dummy_Condition, Dummy_StopEvaluation

#########################
# PowerRulesRuntime tests
#########################


def test_runtime_run_once_evaluates_configuration(
    tmp_path: Path,
) -> None:
    configuration_file = tmp_path / "powerrules.yaml"

    expected_result = RuleEvaluationResult(matched_rule=None)
    rule_set = RuleSet(rules=())

    # It does not really matter which platform provider is mocked here
    providers = PlatformProviders(
        clock=Mock(spec=SystemClockProvider),
        process=Mock(spec=PsUtilProcessProvider),
        window=Mock(spec=PyWinCtlWindowProvider),
        power=Mock(spec=WindowsPowerProvider),
    )

    with (
        patch(
            "powerrules.application.runtime.ConfigurationLoader",
        ) as mock_loader,
        patch(
            "powerrules.application.runtime.ConfigurationBuilder",
        ) as mock_builder,
        patch(
            "powerrules.application.runtime.RuleEngine",
        ) as mock_engine,
        patch(
            "powerrules.application.runtime.get_platform_providers",
            return_value=providers,
        ),
    ):
        mock_loader.return_value.load.return_value = "configuration"
        mock_builder.return_value.build.return_value = rule_set
        mock_engine.return_value.evaluate.return_value = expected_result

        result = PowerRulesRuntime().run_once(configuration_file)

    assert result is expected_result

    mock_loader.return_value.load.assert_called_once_with(
        configuration_file,
    )

    mock_builder.assert_called_once_with(
        clock_provider=providers.clock,
        process_provider=providers.process,
        window_provider=providers.window,
        power_provider=providers.power,
    )

    mock_builder.return_value.build.assert_called_once_with(
        "configuration",
    )

    mock_engine.assert_called_once_with(
        rule_set.rules,
    )

    mock_engine.return_value.evaluate.assert_called_once_with()


def test_runtime_run_once_propagates_condition_evaluation_error(
    tmp_path: Path,
) -> None:
    configuration_file = tmp_path / "powerrules.yaml"
    rule_set = RuleSet(rules=())

    original_error = ConditionEvaluationError("Test condition failed")

    with (
        patch("powerrules.application.runtime.ConfigurationLoader") as mock_loader,
        patch("powerrules.application.runtime.ConfigurationBuilder") as mock_builder,
        patch("powerrules.application.runtime.RuleEngine") as mock_engine,
    ):
        mock_loader.return_value.load.return_value = "configuration"
        mock_builder.return_value.build.return_value = rule_set
        mock_engine.return_value.evaluate.side_effect = original_error

        with pytest.raises(ConditionEvaluationError) as exc_info:
            PowerRulesRuntime().run_once(configuration_file)

    assert exc_info.value is original_error


def test_runtime_run_continuously_executes_matching_rule_once() -> None:
    action = Dummy_Action()
    rule = Rule(
        name="Test rule",
        condition=Dummy_Condition(given_result=True),
        action=action,
    )

    rule_engine = Mock()
    rule_engine.find_match.side_effect = [
        rule,
        rule,
        None,
        rule,
    ]

    def stop_after_fourth_sleep(_: float) -> None:
        if sleep.call_count == 4:
            raise Dummy_StopEvaluation

    sleep = Mock(side_effect=stop_after_fourth_sleep)

    with (
        patch(
            "powerrules.application.runtime.PowerRulesRuntime._build_rule_engine",
            return_value=rule_engine,
        ),
        patch(
            "powerrules.application.runtime.time.sleep",
            new=sleep,
        ),
        pytest.raises(Dummy_StopEvaluation),
    ):
        PowerRulesRuntime().run_continuously(
            configuration_path=Path("powerrules.yaml"),
        )

    assert action.execution_count == 2
    assert rule_engine.find_match.call_count == 4
    assert sleep.call_count == 4


def test_runtime_run_continuously_stops_after_match_when_enabled() -> None:
    action = Dummy_Action()
    rule = Rule(
        name="Test rule",
        condition=Dummy_Condition(given_result=True),
        action=action,
    )

    rule_engine = Mock()
    rule_engine.find_match.return_value = rule

    sleep = Mock()

    with (
        patch(
            "powerrules.application.runtime.PowerRulesRuntime._build_rule_engine",
            return_value=rule_engine,
        ),
        patch(
            "powerrules.application.runtime.time.sleep",
            new=sleep,
        ),
    ):
        PowerRulesRuntime().run_continuously(
            configuration_path=Path("powerrules.yaml"),
            stop_on_match=True,
        )

    assert action.execution_count == 1
    assert rule_engine.find_match.call_count == 1
    sleep.assert_not_called()


def test_runtime_run_continuously_does_not_stop_after_match_when_disabled() -> None:
    action = Dummy_Action()
    rule = Rule(
        name="Test rule",
        condition=Dummy_Condition(given_result=True),
        action=action,
    )

    rule_engine = Mock()
    rule_engine.find_match.side_effect = [
        rule,
        None,
        rule,
    ]

    def stop_after_third_sleep(_: float) -> None:
        if sleep.call_count == 3:
            raise Dummy_StopEvaluation

    sleep = Mock(side_effect=stop_after_third_sleep)

    with (
        patch(
            "powerrules.application.runtime.PowerRulesRuntime._build_rule_engine",
            return_value=rule_engine,
        ),
        patch(
            "powerrules.application.runtime.time.sleep",
            new=sleep,
        ),
        pytest.raises(Dummy_StopEvaluation),
    ):
        PowerRulesRuntime().run_continuously(
            configuration_path=Path("powerrules.yaml"),
            stop_on_match=False,
        )

    assert action.execution_count == 2
    assert rule_engine.find_match.call_count == 3
    assert sleep.call_count == 3


def test_runtime_run_continuously_uses_configured_evaluation_interval() -> None:
    rule_engine = Mock()
    rule_engine.find_match.return_value = None

    def stop_after_first_sleep(_: float) -> None:
        raise Dummy_StopEvaluation

    sleep = Mock(side_effect=stop_after_first_sleep)

    with (
        patch(
            "powerrules.application.runtime.PowerRulesRuntime._build_rule_engine",
            return_value=rule_engine,
        ),
        patch(
            "powerrules.application.runtime.time.sleep",
            new=sleep,
        ),
        pytest.raises(Dummy_StopEvaluation),
    ):
        PowerRulesRuntime().run_continuously(
            configuration_path=Path("powerrules.yaml"),
            evaluation_interval=30.0,
        )

    sleep.assert_called_once_with(30.0)


@pytest.mark.parametrize("evaluation_interval", [0, -1, -10.5])
def test_runtime_run_continuously_rejects_invalid_evaluation_interval(
    evaluation_interval: float,
) -> None:
    with pytest.raises(
        ValueError,
        match="Evaluation interval must be greater than zero",
    ):
        PowerRulesRuntime().run_continuously(
            configuration_path=Path("powerrules.yaml"),
            evaluation_interval=evaluation_interval,
        )


def test_runtime_run_continuously_builds_rule_engine_only_once() -> None:
    rule_engine = Mock()
    rule_engine.find_match.return_value = None

    def stop_after_first_sleep(_: float) -> None:
        raise Dummy_StopEvaluation

    sleep = Mock(side_effect=stop_after_first_sleep)
    build_rule_engine = Mock(return_value=rule_engine)

    with (
        patch(
            "powerrules.application.runtime.PowerRulesRuntime._build_rule_engine",
            new=build_rule_engine,
        ),
        patch(
            "powerrules.application.runtime.time.sleep",
            new=sleep,
        ),
        pytest.raises(Dummy_StopEvaluation),
    ):
        PowerRulesRuntime().run_continuously(
            configuration_path=Path("powerrules.yaml"),
        )

    build_rule_engine.assert_called_once_with(Path("powerrules.yaml"))


def test_runtime_builds_rule_engine_with_platform_providers(
    tmp_path: Path,
) -> None:
    configuration_file = tmp_path / "powerrules.yaml"
    rule_set = RuleSet(rules=())

    # It does not really matter which platform provider is mocked here
    providers = PlatformProviders(
        clock=Mock(spec=SystemClockProvider),
        process=Mock(spec=PsUtilProcessProvider),
        window=Mock(spec=PyWinCtlWindowProvider),
        power=Mock(spec=WindowsPowerProvider),
    )

    with (
        patch(
            "powerrules.application.runtime.ConfigurationLoader",
        ) as mock_loader,
        patch(
            "powerrules.application.runtime.ConfigurationBuilder",
        ) as mock_builder,
        patch(
            "powerrules.application.runtime.RuleEngine",
        ) as mock_engine,
        patch(
            "powerrules.application.runtime.get_platform_providers",
            return_value=providers,
        ),
    ):
        mock_loader.return_value.load.return_value = "configuration"
        mock_builder.return_value.build.return_value = rule_set

        PowerRulesRuntime._build_rule_engine(
            configuration_path=configuration_file,
        )

    mock_loader.return_value.load.assert_called_once_with(
        configuration_file,
    )

    mock_builder.assert_called_once_with(
        clock_provider=providers.clock,
        process_provider=providers.process,
        window_provider=providers.window,
        power_provider=providers.power,
    )

    mock_builder.return_value.build.assert_called_once_with(
        "configuration",
    )

    mock_engine.assert_called_once_with(
        rule_set.rules,
    )


##############################
# get_platform_providers tests
##############################


def test_get_platform_providers_returns_windows_providers() -> None:
    with patch(
        "powerrules.application.runtime.platform.system",
        return_value="Windows",
    ):
        providers = get_platform_providers()

    assert isinstance(providers, PlatformProviders)
    assert isinstance(providers.clock, SystemClockProvider)
    assert isinstance(providers.process, PsUtilProcessProvider)
    assert isinstance(providers.power, WindowsPowerProvider)


def test_get_platform_providers_returns_linux_providers() -> None:
    with patch(
        "powerrules.application.runtime.platform.system",
        return_value="Linux",
    ):
        providers = get_platform_providers()

    assert isinstance(providers, PlatformProviders)
    assert isinstance(providers.clock, SystemClockProvider)
    assert isinstance(providers.process, PsUtilProcessProvider)
    assert isinstance(providers.power, LinuxPowerProvider)


def test_get_platform_providers_returns_macos_providers() -> None:
    with patch(
        "powerrules.application.runtime.platform.system",
        return_value="Darwin",
    ):
        providers = get_platform_providers()

    assert isinstance(providers, PlatformProviders)
    assert isinstance(providers.clock, SystemClockProvider)
    assert isinstance(providers.process, PsUtilProcessProvider)
    assert isinstance(providers.power, MacOSPowerProvider)


def test_get_platform_providers_rejects_unsupported_platform() -> None:
    with (
        patch(
            "powerrules.application.runtime.platform.system",
            return_value="FreeBSD",
        ),
        pytest.raises(
            RuntimeError,
            match="Unsupported operating system: FreeBSD",
        ),
    ):
        get_platform_providers()
