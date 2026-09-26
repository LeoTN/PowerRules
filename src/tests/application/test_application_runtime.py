import itertools
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
from tests.dummies import Dummy_Action, Dummy_Condition

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

    mock_engine.return_value.evaluate.assert_called_once_with(dry_run=False)


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


def test_runtime_run_continuously_threads_previous_matched_rule_between_evaluations() -> (
    None
):
    rule = Rule(
        name="Test rule",
        condition=Dummy_Condition(given_result=True),
        action=Dummy_Action(),
    )

    rule_engine = Mock()
    rule_engine.evaluate.side_effect = [
        RuleEvaluationResult(matched_rule=rule, action_triggered=True),
        RuleEvaluationResult(matched_rule=rule, action_triggered=False),
        RuleEvaluationResult(matched_rule=None, action_triggered=False),
        RuleEvaluationResult(matched_rule=rule, action_triggered=True),
    ]

    with (
        patch(
            "powerrules.application.runtime.PowerRulesRuntime._build_rule_engine",
            return_value=rule_engine,
        ),
        patch("powerrules.application.runtime.time.sleep") as sleep,
    ):
        results = list(
            itertools.islice(
                PowerRulesRuntime().run_continuously(
                    configuration_path=Path("powerrules.yaml"),
                ),
                4,
            )
        )

    assert [result.action_triggered for result in results] == [
        True,
        False,
        False,
        True,
    ]
    assert rule_engine.evaluate.call_count == 4
    # Sleep happens between evaluations, so consuming 4 results sleeps 3 times
    assert sleep.call_count == 3

    expected_previous_matched_rules = [None, rule, rule, None]
    actual_previous_matched_rules = [
        call.kwargs["previous_matched_rule"]
        for call in rule_engine.evaluate.call_args_list
    ]
    assert actual_previous_matched_rules == expected_previous_matched_rules
    assert all(
        call.kwargs["dry_run"] is False for call in rule_engine.evaluate.call_args_list
    )


def test_runtime_run_continuously_stops_after_match_when_enabled() -> None:
    rule = Rule(
        name="Test rule",
        condition=Dummy_Condition(given_result=True),
        action=Dummy_Action(),
    )

    rule_engine = Mock()
    rule_engine.evaluate.return_value = RuleEvaluationResult(
        matched_rule=rule, action_triggered=True
    )

    with (
        patch(
            "powerrules.application.runtime.PowerRulesRuntime._build_rule_engine",
            return_value=rule_engine,
        ),
        patch("powerrules.application.runtime.time.sleep") as sleep,
    ):
        results = list(
            PowerRulesRuntime().run_continuously(
                configuration_path=Path("powerrules.yaml"),
                stop_on_match=True,
            )
        )

    assert len(results) == 1
    rule_engine.evaluate.assert_called_once_with(
        previous_matched_rule=None,
        dry_run=False,
    )
    sleep.assert_not_called()


def test_runtime_run_continuously_does_not_stop_after_match_when_disabled() -> None:
    rule = Rule(
        name="Test rule",
        condition=Dummy_Condition(given_result=True),
        action=Dummy_Action(),
    )

    rule_engine = Mock()
    rule_engine.evaluate.side_effect = [
        RuleEvaluationResult(matched_rule=rule, action_triggered=True),
        RuleEvaluationResult(matched_rule=None, action_triggered=False),
        RuleEvaluationResult(matched_rule=rule, action_triggered=True),
    ]

    with (
        patch(
            "powerrules.application.runtime.PowerRulesRuntime._build_rule_engine",
            return_value=rule_engine,
        ),
        patch("powerrules.application.runtime.time.sleep") as sleep,
    ):
        results = list(
            itertools.islice(
                PowerRulesRuntime().run_continuously(
                    configuration_path=Path("powerrules.yaml"),
                    stop_on_match=False,
                ),
                3,
            )
        )

    assert len(results) == 3
    assert rule_engine.evaluate.call_count == 3
    assert sleep.call_count == 2

    expected_previous_matched_rules = [None, rule, None]
    actual_previous_matched_rules = [
        call.kwargs["previous_matched_rule"]
        for call in rule_engine.evaluate.call_args_list
    ]
    assert actual_previous_matched_rules == expected_previous_matched_rules


def test_runtime_run_continuously_uses_configured_evaluation_interval() -> None:
    rule_engine = Mock()
    rule_engine.evaluate.return_value = RuleEvaluationResult(matched_rule=None)

    with (
        patch(
            "powerrules.application.runtime.PowerRulesRuntime._build_rule_engine",
            return_value=rule_engine,
        ),
        patch("powerrules.application.runtime.time.sleep") as sleep,
    ):
        # Consuming two evaluations means the generator sleeps exactly once in between
        results = list(
            itertools.islice(
                PowerRulesRuntime().run_continuously(
                    configuration_path=Path("powerrules.yaml"),
                    evaluation_interval=30.0,
                ),
                2,
            )
        )

    assert len(results) == 2
    sleep.assert_called_once_with(30.0)


@pytest.mark.parametrize("evaluation_interval", [0, -1, -10.5])
def test_runtime_run_continuously_rejects_invalid_evaluation_interval(
    evaluation_interval: float,
) -> None:
    # The interval is validated eagerly, before any evaluation or iteration takes place
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
    rule_engine.evaluate.return_value = RuleEvaluationResult(matched_rule=None)

    build_rule_engine = Mock(return_value=rule_engine)

    with (
        patch(
            "powerrules.application.runtime.PowerRulesRuntime._build_rule_engine",
            new=build_rule_engine,
        ),
        patch("powerrules.application.runtime.time.sleep"),
    ):
        # Consume several evaluations to make sure the rule engine is still only built once
        results = list(
            itertools.islice(
                PowerRulesRuntime().run_continuously(
                    configuration_path=Path("powerrules.yaml"),
                ),
                3,
            )
        )

    assert len(results) == 3
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
