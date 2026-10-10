from datetime import date, datetime
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from powerrules.conditions.datetime import Month, Weekday
from powerrules.config.loader import ConfigurationLoader
from powerrules.config.models import DateRangeConfiguration, DateTimeRangeConfiguration
from powerrules.providers.command import Shell


def _write_policy(tmp_path: Path, content: str) -> Path:
    """Write a policy file into the temporary directory."""
    configuration_file = tmp_path / "powerrules.yaml"
    configuration_file.write_text(content, encoding="utf-8")

    return configuration_file


def test_configuration_loader_loads_valid_configuration(tmp_path: Path) -> None:
    configuration_file = _write_policy(
        tmp_path,
        """
rules:
  - name: "Shutdown after backup test rule"
    conditions:
      process:
        name: "backup.exe"
        exists: false
    actions:
      - run: "shutdown /s /t 0"
""",
    )

    configuration = ConfigurationLoader().load(configuration_file)

    assert len(configuration.rules) == 1
    assert configuration.rules[0].name == "Shutdown after backup test rule"
    assert configuration.rules[0].enabled is True
    assert [action.run for action in configuration.rules[0].actions] == [
        "shutdown /s /t 0"
    ]


def test_configuration_loader_loads_nested_conditions(tmp_path: Path) -> None:
    configuration_file = _write_policy(
        tmp_path,
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
    actions:
      - run: "echo test"
""",
    )

    configuration = ConfigurationLoader().load(configuration_file)

    condition = configuration.rules[0].conditions

    assert condition.and_conditions is not None
    assert len(condition.and_conditions) == 2
    assert condition.and_conditions[0].process is not None
    assert condition.and_conditions[1].or_conditions is not None
    assert len(condition.and_conditions[1].or_conditions) == 2


def test_configuration_loader_loads_multiple_actions_with_all_options(
    tmp_path: Path,
) -> None:
    configuration_file = _write_policy(
        tmp_path,
        """
rules:
  - name: "Action test rule"
    conditions:
      process:
        name: "backup.exe"
        exists: false
    actions:
      - name: "Backup"
        run: |
          echo one
          echo two
        shell: bash
        working_directory: scripts
        env:
          RETRIES: 3
          VERBOSE: true
          LABEL: nightly
        timeout: 120
        success_exit_codes: [0, 3]
        continue_on_error: true
      - run: "echo background"
        wait: false
""",
    )

    first_action, second_action = (
        ConfigurationLoader().load(configuration_file).rules[0].actions
    )

    assert first_action.name == "Backup"
    assert first_action.run == "echo one\necho two\n"
    assert first_action.shell is Shell.BASH
    assert first_action.working_directory == Path("scripts")
    # Unquoted YAML numbers and booleans are converted to strings
    assert first_action.env == {
        "RETRIES": "3",
        "VERBOSE": "true",
        "LABEL": "nightly",
    }
    assert first_action.timeout == 120
    assert first_action.success_exit_codes == [0, 3]
    assert first_action.continue_on_error is True

    assert second_action.name is None
    assert second_action.run == "echo background"
    assert second_action.wait is False


def test_configuration_loader_loads_null_timeout_as_no_time_limit(
    tmp_path: Path,
) -> None:
    configuration_file = _write_policy(
        tmp_path,
        """
rules:
  - name: "Timeout test rule"
    conditions:
      process:
        name: "backup.exe"
        exists: false
    actions:
      - run: "echo test"
        timeout: null
""",
    )

    configuration = ConfigurationLoader().load(configuration_file)

    assert configuration.rules[0].actions[0].timeout is None


def test_configuration_loader_rejects_invalid_configuration(tmp_path: Path) -> None:
    configuration_file = _write_policy(
        tmp_path,
        """
rules:
  - name: "Invalid test rule"
    conditions:
      process:
        name: "backup.exe"
        exists: "false"
    actions:
      - run: "echo test"
""",
    )

    with pytest.raises(ValidationError, match="valid boolean"):
        ConfigurationLoader().load(configuration_file)


def test_configuration_loader_rejects_former_action_format(tmp_path: Path) -> None:
    configuration_file = _write_policy(
        tmp_path,
        """
rules:
  - name: "Former format test rule"
    conditions:
      process:
        name: "backup.exe"
        exists: false
    action:
      type: shutdown
""",
    )

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ConfigurationLoader().load(configuration_file)


def test_configuration_loader_rejects_invalid_yaml(tmp_path: Path) -> None:
    configuration_file = _write_policy(
        tmp_path,
        # The missing closing quote is intentional
        """
rules:
  - name: "Broken rule
    actions:
      - run: "echo test"
""",
    )

    with pytest.raises(yaml.YAMLError):
        ConfigurationLoader().load(configuration_file)


def test_configuration_loader_raises_for_missing_file(tmp_path: Path) -> None:
    configuration_file = tmp_path / "missing.yaml"

    with pytest.raises(FileNotFoundError):
        ConfigurationLoader().load(configuration_file)


def test_configuration_loader_loads_unquoted_absolute_dates(tmp_path: Path) -> None:
    configuration_file = _write_policy(
        tmp_path,
        # PyYAML converts these unquoted values into date and datetime objects on its own
        """
rules:
  - name: "Date test rule"
    conditions:
      datetime:
        between:
          start: 2026-08-21
          end: 2026-08-22
    actions:
      - run: "echo test"

  - name: "Datetime test rule"
    conditions:
      datetime:
        between:
          start: 2026-08-21 18:00:00
          end: 2026-08-22 06:00:00
    actions:
      - run: "echo test"
""",
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
    configuration_file = _write_policy(
        tmp_path,
        """
rules:
  - name: "Timezone test rule"
    conditions:
      datetime:
        between:
          start: 2026-08-21 18:00:00Z
          end: 2026-08-22 06:00:00Z
    actions:
      - run: "echo test"
""",
    )

    with pytest.raises(
        ValidationError,
        match="Timezone-aware datetimes are not supported",
    ):
        ConfigurationLoader().load(configuration_file)


def test_configuration_loader_loads_weekday_and_month_regardless_of_case(
    tmp_path: Path,
) -> None:
    configuration_file = _write_policy(
        tmp_path,
        """
rules:
  - name: "Case test rule"
    conditions:
      datetime:
        weekday:
          - "saturday"
          - "SUNDAY"
        month:
          - "december"
          - "January"
    actions:
      - run: "echo test"
""",
    )

    configuration = ConfigurationLoader().load(configuration_file)

    condition = configuration.rules[0].conditions.datetime

    assert condition is not None
    assert condition.weekday == [Weekday.SATURDAY, Weekday.SUNDAY]
    assert condition.month == [Month.DECEMBER, Month.JANUARY]
