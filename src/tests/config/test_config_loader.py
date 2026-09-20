from datetime import date, datetime
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from powerrules.config.loader import ConfigurationLoader
from powerrules.config.models import DateRangeConfiguration, DateTimeRangeConfiguration


def test_configuration_loader_loads_valid_configuration(tmp_path: Path) -> None:
    configuration_file = tmp_path / "powerrules.yaml"
    configuration_file.write_text(
        """
rules:
  - name: "Shutdown after backup test rule"
    conditions:
      process:
        name: "backup.exe"
        exists: false
    action:
      type: shutdown
""",
        encoding="utf-8",
    )

    configuration = ConfigurationLoader().load(configuration_file)

    assert len(configuration.rules) == 1
    assert configuration.rules[0].name == "Shutdown after backup test rule"
    assert configuration.rules[0].enabled is True


def test_configuration_loader_loads_nested_conditions(tmp_path: Path) -> None:
    configuration_file = tmp_path / "powerrules.yaml"
    configuration_file.write_text(
        """
rules:
  - name: "Nested test rule"
    conditions:
      and:
        - process:
            name: "backup.exe"
            exists: false
        - or:
            - datetime:
                between:
                  start: "22"
                  end: "6"
            - process:
                name: "maintenance.exe"
                exists: true
    action:
      type: shutdown
""",
        encoding="utf-8",
    )

    configuration = ConfigurationLoader().load(configuration_file)

    condition = configuration.rules[0].conditions

    assert condition.and_conditions is not None
    assert len(condition.and_conditions) == 2
    assert condition.and_conditions[0].process is not None
    assert condition.and_conditions[1].or_conditions is not None
    assert len(condition.and_conditions[1].or_conditions) == 2


def test_configuration_loader_rejects_invalid_configuration(tmp_path: Path) -> None:
    configuration_file = tmp_path / "powerrules.yaml"
    configuration_file.write_text(
        """
rules:
  - name: "Invalid test rule"
    conditions:
      process:
        name: "backup.exe"
        exists: "false"
    action:
      type: shutdown
""",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        ConfigurationLoader().load(configuration_file)


def test_configuration_loader_rejects_invalid_yaml(tmp_path: Path) -> None:
    configuration_file = tmp_path / "powerrules.yaml"
    configuration_file.write_text(
        # The missing closing quote is intentional
        """
rules:
  - name: "Broken rule
    action:
      type: shutdown
""",
        encoding="utf-8",
    )

    with pytest.raises(yaml.YAMLError):
        ConfigurationLoader().load(configuration_file)


def test_configuration_loader_raises_for_missing_file(tmp_path: Path) -> None:
    configuration_file = tmp_path / "missing.yaml"

    with pytest.raises(FileNotFoundError):
        ConfigurationLoader().load(configuration_file)


def test_configuration_loader_loads_unquoted_absolute_dates(tmp_path: Path) -> None:
    configuration_file = tmp_path / "powerrules.yaml"
    configuration_file.write_text(
        # PyYAML converts these unquoted values into date and datetime objects on its own
        """
rules:
  - name: "Date test rule"
    conditions:
      datetime:
        between:
          start: 2026-08-21
          end: 2026-08-22
    action:
      type: shutdown

  - name: "Datetime test rule"
    conditions:
      datetime:
        between:
          start: 2026-08-21 18:00:00
          end: 2026-08-22 06:00:00
    action:
      type: shutdown
""",
        encoding="utf-8",
    )

    configuration = ConfigurationLoader().load(configuration_file)

    date_condition = configuration.rules[0].conditions.datetime
    datetime_condition = configuration.rules[1].conditions.datetime

    assert date_condition is not None
    assert datetime_condition is not None
    assert date_condition.between == DateRangeConfiguration(
        start=date(2026, 8, 21),
        end=date(2026, 8, 22),
    )
    assert datetime_condition.between == DateTimeRangeConfiguration(
        start=datetime(2026, 8, 21, 18, 0),
        end=datetime(2026, 8, 22, 6, 0),
    )


def test_configuration_loader_rejects_unquoted_timezone_aware_datetime(
    tmp_path: Path,
) -> None:
    configuration_file = tmp_path / "powerrules.yaml"
    configuration_file.write_text(
        """
rules:
  - name: "Timezone test rule"
    conditions:
      datetime:
        between:
          start: 2026-08-21 18:00:00Z
          end: 2026-08-22 06:00:00Z
    action:
      type: shutdown
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ValidationError,
        match="Timezone-aware datetimes are not supported",
    ):
        ConfigurationLoader().load(configuration_file)
