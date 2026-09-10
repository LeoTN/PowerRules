from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from powerrules.config.loader import ConfigurationLoader


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
