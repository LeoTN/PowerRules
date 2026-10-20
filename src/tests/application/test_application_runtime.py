import itertools
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from powerrules.application.runtime import (
    PlatformProviders,
    PowerRulesRuntime,
    get_platform_providers,
)
from powerrules.engine.exceptions import ConditionEvaluationError
from powerrules.engine.models import RuleEvaluationResult, RuleSet
from powerrules.platform.clock import SystemClockProvider
from powerrules.platform.command import SubprocessCommandProvider
from powerrules.platform.process import PsUtilProcessProvider
from powerrules.providers.command import Shell
from tests.factories import make_rule, make_rule_engine_mock, make_trust_checker


@dataclass(frozen=True)
class _BuildMocks:
    """The mocked collaborators of "PowerRulesRuntime._build_rule_engine()"."""

    loader: Mock
    builder: Mock
    engine: Mock
    rule_set: RuleSet


@pytest.fixture
def build_mocks() -> Iterator[_BuildMocks]:
    """Replace the loader, the builder and the engine, so only the wiring of the runtime is tested."""
    rule_set = RuleSet(rules=())

    with (
        patch("powerrules.application.runtime.ConfigurationLoader") as loader,
        patch("powerrules.application.runtime.ConfigurationBuilder") as builder,
        patch("powerrules.application.runtime.RuleEngine") as engine,
    ):
        loader.return_value.load.return_value = "configuration"
        builder.return_value.build.return_value = rule_set

        yield _BuildMocks(loader, builder, engine, rule_set)


#########################
# PowerRulesRuntime tests
#########################


@pytest.mark.usefixtures("patched_platform_providers")
def test_runtime_run_once_evaluates_configuration(
    tmp_path: Path,
    build_mocks: _BuildMocks,
) -> None:
    expected_result = RuleEvaluationResult(matched_rule=None)
    build_mocks.engine.return_value.evaluate.return_value = expected_result

    result = PowerRulesRuntime().run_once(tmp_path / "powerrules.yaml")

    assert result is expected_result
    build_mocks.engine.return_value.evaluate.assert_called_once_with(dry_run=False)


@pytest.mark.usefixtures("patched_platform_providers")
def test_runtime_run_once_propagates_condition_evaluation_error(
    tmp_path: Path,
    build_mocks: _BuildMocks,
) -> None:
    original_error = ConditionEvaluationError("Test condition failed")
    build_mocks.engine.return_value.evaluate.side_effect = original_error

    with pytest.raises(ConditionEvaluationError) as exc_info:
        PowerRulesRuntime().run_once(tmp_path / "powerrules.yaml")

    assert exc_info.value is original_error


def test_runtime_builds_rule_engine_with_platform_providers(
    tmp_path: Path,
    patched_platform_providers: PlatformProviders,
    build_mocks: _BuildMocks,
) -> None:
    providers = patched_platform_providers
    configuration_file = tmp_path / "powerrules.yaml"

    PowerRulesRuntime()._build_rule_engine(configuration_path=configuration_file)

    build_mocks.loader.return_value.load.assert_called_once_with(configuration_file)
    build_mocks.builder.assert_called_once_with(
        clock_provider=providers.clock,
        process_provider=providers.process,
        window_provider=providers.window,
        command_provider=providers.command,
        base_directory=configuration_file.parent,
        files_verifier=None,
    )
    build_mocks.builder.return_value.build.assert_called_once_with("configuration")
    build_mocks.engine.assert_called_once_with(build_mocks.rule_set.rules)


@pytest.mark.usefixtures("patched_platform_providers")
def test_runtime_passes_files_verifier_of_trust_checker_to_builder(
    tmp_path: Path,
    build_mocks: _BuildMocks,
) -> None:
    trust_checker = make_trust_checker()
    configuration_file = tmp_path / "powerrules.yaml"

    PowerRulesRuntime(trust_checker=trust_checker)._build_rule_engine(
        configuration_path=configuration_file
    )

    files_verifier = build_mocks.builder.call_args.kwargs["files_verifier"]

    assert files_verifier.func == trust_checker.verify_files
    assert files_verifier.args == (configuration_file.resolve(),)


def test_runtime_run_continuously_threads_previous_matched_rule_between_evaluations() -> (
    None
):
    rule = make_rule()
    rule_engine = make_rule_engine_mock(
        results=[
            RuleEvaluationResult(matched_rule=rule, action_triggered=True),
            RuleEvaluationResult(matched_rule=rule, action_triggered=False),
            RuleEvaluationResult(matched_rule=None, action_triggered=False),
            RuleEvaluationResult(matched_rule=rule, action_triggered=True),
        ]
    )

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
    rule = make_rule()
    rule_engine = make_rule_engine_mock(
        result=RuleEvaluationResult(matched_rule=rule, action_triggered=True)
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
    rule = make_rule()
    rule_engine = make_rule_engine_mock(
        results=[
            RuleEvaluationResult(matched_rule=rule, action_triggered=True),
            RuleEvaluationResult(matched_rule=None, action_triggered=False),
            RuleEvaluationResult(matched_rule=rule, action_triggered=True),
        ]
    )

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
    rule_engine = make_rule_engine_mock()

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
    rule_engine = make_rule_engine_mock()

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
    assert isinstance(providers.command, SubprocessCommandProvider)
    assert providers.command.default_shell is Shell.POWERSHELL


def test_get_platform_providers_returns_linux_providers() -> None:
    with patch(
        "powerrules.application.runtime.platform.system",
        return_value="Linux",
    ):
        providers = get_platform_providers()

    assert isinstance(providers, PlatformProviders)
    assert isinstance(providers.clock, SystemClockProvider)
    assert isinstance(providers.process, PsUtilProcessProvider)
    assert isinstance(providers.command, SubprocessCommandProvider)
    assert providers.command.default_shell is Shell.SH


def test_get_platform_providers_returns_macos_providers() -> None:
    with patch(
        "powerrules.application.runtime.platform.system",
        return_value="Darwin",
    ):
        providers = get_platform_providers()

    assert isinstance(providers, PlatformProviders)
    assert isinstance(providers.clock, SystemClockProvider)
    assert isinstance(providers.process, PsUtilProcessProvider)
    assert isinstance(providers.command, SubprocessCommandProvider)
    assert providers.command.default_shell is Shell.SH


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
