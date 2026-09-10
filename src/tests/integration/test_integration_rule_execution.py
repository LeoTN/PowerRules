from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from powerrules.actions.power import ShutdownAction
from powerrules.config.builder import ConfigurationBuilder
from powerrules.config.loader import ConfigurationLoader
from powerrules.engine.models import Rule
from powerrules.engine.rule_engine import RuleEngine
from tests.dummies import (
    Dummy_ClockProvider,
    Dummy_PowerProvider,
)


def test_rule_execution_from_yaml_configuration(tmp_path: Path) -> None:
    configuration_file = tmp_path / "powerrules.yaml"
    configuration_file.write_text(
        """
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
    action:
      type: shutdown
""",
        encoding="utf-8",
    )

    clock_provider = Dummy_ClockProvider(datetime(2026, 8, 22, 1, 30))
    mock_process_provider = patch(
        "powerrules.providers.process.ProcessProvider"
    ).start()
    mock_window_provider = patch("powerrules.providers.window.WindowProvider").start()
    power_provider = Dummy_PowerProvider()

    configuration = ConfigurationLoader().load(configuration_file)

    rule_set = ConfigurationBuilder(
        clock_provider=clock_provider,
        process_provider=mock_process_provider,
        window_provider=mock_window_provider,
        power_provider=power_provider,
    ).build(configuration)

    result = RuleEngine(rule_set.rules).evaluate()

    assert result.matched_rule is not None
    assert result.matched_rule.name == "Shutdown after backup"
    assert isinstance(result.matched_rule, Rule)
    assert isinstance(result.matched_rule.action, ShutdownAction)
    assert power_provider.shutdown_count == 1


def test_rule_execution_from_yaml_configuration_returns_no_match(
    tmp_path: Path,
) -> None:
    configuration_file = tmp_path / "powerrules.yaml"
    configuration_file.write_text(
        """
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
    action:
      type: shutdown
""",
        encoding="utf-8",
    )

    clock_provider = Dummy_ClockProvider(datetime(2026, 8, 22, 22, 30))
    mock_process_provider = patch(
        "powerrules.providers.process.ProcessProvider"
    ).start()
    mock_window_provider = patch("powerrules.providers.window.WindowProvider").start()
    power_provider = Dummy_PowerProvider()

    configuration = ConfigurationLoader().load(configuration_file)

    rule_set = ConfigurationBuilder(
        clock_provider=clock_provider,
        process_provider=mock_process_provider,
        window_provider=mock_window_provider,
        power_provider=power_provider,
    ).build(configuration)

    result = RuleEngine(rule_set.rules).evaluate()

    assert result.matched_rule is None
    assert power_provider.shutdown_count == 0


def test_rule_execution_uses_first_matching_rule(tmp_path: Path) -> None:
    configuration_file = tmp_path / "powerrules.yaml"
    configuration_file.write_text(
        """
rules:
  - name: "Sleep"
    conditions:
      datetime:
        between:
          start: "22:00"
          end: "0:00"
    action:
      type: sleep

  - name: "Shutdown"
    conditions:
      datetime:
        between:
          start: "23:00"
          end: "6:00"
    action:
      type: shutdown
""",
        encoding="utf-8",
    )

    clock_provider = Dummy_ClockProvider(datetime(2026, 8, 22, 23, 30))
    mock_process_provider = patch(
        "powerrules.providers.process.ProcessProvider"
    ).start()
    mock_window_provider = patch("powerrules.providers.window.WindowProvider").start()
    power_provider = Dummy_PowerProvider()

    configuration = ConfigurationLoader().load(configuration_file)

    rule_set = ConfigurationBuilder(
        clock_provider=clock_provider,
        process_provider=mock_process_provider,
        window_provider=mock_window_provider,
        power_provider=power_provider,
    ).build(configuration)

    result = RuleEngine(rule_set.rules).evaluate()

    assert result.matched_rule is not None
    assert result.matched_rule.name == "Sleep"
    assert power_provider.sleep_count == 1
    assert power_provider.shutdown_count == 0
