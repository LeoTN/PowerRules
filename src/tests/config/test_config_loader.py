from datetime import date, datetime
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from powerrules.conditions.datetime import Month, Weekday
from powerrules.conditions.matcher import MatchType
from powerrules.config.loader import ConfigurationLoader
from powerrules.config.models import DateRangeConfiguration, DateTimeRangeConfiguration
from powerrules.engine.exceptions import PolicyNotTrustedError
from powerrules.providers.command import Shell
from tests.factories import (
    make_policy_yaml,
    make_trust_checker,
)
from tests.helpers import (
    SCRIPT_DIRECTORY_NAME,
    create_symlink,
    write_policy,
)

POLICY_WITH_DUPLICATE_FILES = """
rules:
  - name: "Test rule"
    conditions:
      process:
        name: "backup.exe"
        exists: false
    actions:
      - run: "first"
        trusted_files:
          - scripts/a.sh
      - run: "second"
        trusted_files:
          - ./scripts/a.sh
          - b.sh
"""
POLICY_WITH_COMMAND_CONDITION = """
rules:
  - name: "Test rule"
    conditions:
      and:
        - command:
            run: "check.sh"
            shell: bash
            working_directory: scripts
            env:
              RETRIES: 3
            timeout: .inf
            success_exit_codes: [0, 2]
            stdout:
              value: "active"
              match:
                type: contains
            stderr:
              value: ".*error.*"
              match:
                type: regex
                case_sensitive: false
            trusted_files:
              - scripts/check.sh
        - process:
            name: "backup.exe"
            exists: false
    actions:
      - run: "echo test"
        trusted_files:
          - scripts/a.sh
"""


def test_configuration_loader_loads_valid_configuration(tmp_path: Path) -> None:
    configuration_file = write_policy(
        tmp_path,
        make_policy_yaml(
            rule_name="Shutdown after backup test rule",
            command="shutdown /s /t 0",
        ),
    )

    configuration = ConfigurationLoader().load(configuration_file)

    assert len(configuration.rules) == 1
    assert configuration.rules[0].name == "Shutdown after backup test rule"
    assert configuration.rules[0].enabled is True
    assert [action.run for action in configuration.rules[0].actions] == [
        "shutdown /s /t 0"
    ]


def test_configuration_loader_loads_nested_conditions(tmp_path: Path) -> None:
    configuration_file = write_policy(
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
    configuration_file = write_policy(
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
    assert first_action.working_directory == Path(SCRIPT_DIRECTORY_NAME)
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
    configuration_file = write_policy(
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
    configuration_file = write_policy(
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
    configuration_file = write_policy(
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
    configuration_file = write_policy(
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
    configuration_file = write_policy(
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
    configuration_file = write_policy(
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
    configuration_file = write_policy(
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


#####################
# Trusted files tests
#####################


def test_configuration_loader_loads_command_condition(tmp_path: Path) -> None:
    configuration_file = write_policy(tmp_path, POLICY_WITH_COMMAND_CONDITION)

    configuration = ConfigurationLoader().load(configuration_file)

    and_conditions = configuration.rules[0].conditions.and_conditions

    assert and_conditions is not None

    command = and_conditions[0].command

    assert command is not None
    assert command.run == "check.sh"
    assert command.shell is Shell.BASH
    assert command.working_directory == Path(SCRIPT_DIRECTORY_NAME)
    assert command.env == {"RETRIES": "3"}
    # The YAML value ".inf" means that there is no time limit
    assert command.timeout is None
    assert command.success_exit_codes == [0, 2]
    assert command.stdout is not None
    assert command.stdout.value == "active"
    assert command.stdout.match.type is MatchType.CONTAINS
    assert command.stderr is not None
    assert command.stderr.match.type is MatchType.REGEX
    assert command.stderr.match.case_sensitive is False
    assert command.trusted_files == [Path("scripts/check.sh")]


def test_loader_verifies_trusted_files_of_conditions_before_those_of_actions(
    tmp_path: Path,
) -> None:
    policy = write_policy(tmp_path, POLICY_WITH_COMMAND_CONDITION)
    checker = make_trust_checker()

    ConfigurationLoader(trust_checker=checker).load(policy)

    assert checker.verify.call_args.args[2] == (
        tmp_path.resolve() / SCRIPT_DIRECTORY_NAME / "check.sh",
        tmp_path.resolve() / SCRIPT_DIRECTORY_NAME / "a.sh",
    )


@pytest.mark.parametrize(
    ("policy_content", "expected"),
    [
        (POLICY_WITH_COMMAND_CONDITION, True),
        (POLICY_WITH_DUPLICATE_FILES, False),
    ],
)
def test_loader_tells_checker_whether_policy_contains_command_conditions(
    tmp_path: Path,
    policy_content: str,
    expected: bool,
) -> None:
    policy = write_policy(tmp_path, policy_content)
    checker = make_trust_checker()

    ConfigurationLoader(trust_checker=checker).load(policy)

    assert checker.verify.call_args.kwargs["has_command_conditions"] is expected


def test_loader_resolves_trusted_files_against_directory_of_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy = write_policy(tmp_path / "policies", POLICY_WITH_DUPLICATE_FILES)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    checker = make_trust_checker()

    ConfigurationLoader(trust_checker=checker).load(policy)

    files = checker.verify.call_args.args[2]

    assert all(file.is_relative_to((tmp_path / "policies").resolve()) for file in files)


def test_loader_resolves_symbolic_link_of_policy_before_verifying(
    tmp_path: Path,
) -> None:
    policy = write_policy(tmp_path / "real", POLICY_WITH_DUPLICATE_FILES)
    link = tmp_path / "link.yaml"

    create_symlink(link, policy)
    checker = make_trust_checker()

    ConfigurationLoader(trust_checker=checker).load(link)

    verify_arguments = checker.verify.call_args.args

    assert verify_arguments[0] == policy.resolve()
    # The files belong to the directory of the real policy
    assert verify_arguments[2][0].parent.parent == (tmp_path / "real").resolve()


def test_loader_does_not_verify_invalid_policy(tmp_path: Path) -> None:
    policy = write_policy(tmp_path, 'rules:\n  - name: "Invalid"\n')
    checker = make_trust_checker()

    with pytest.raises(ValidationError):
        ConfigurationLoader(trust_checker=checker).load(policy)

    checker.verify.assert_not_called()


def test_loader_propagates_trust_error(tmp_path: Path) -> None:
    policy = write_policy(tmp_path, POLICY_WITH_DUPLICATE_FILES)
    checker = make_trust_checker()
    checker.verify.side_effect = PolicyNotTrustedError("Test policy is not trusted")

    with pytest.raises(PolicyNotTrustedError, match="Test policy is not trusted"):
        ConfigurationLoader(trust_checker=checker).load(policy)


def test_loader_skips_trust_check_without_checker(tmp_path: Path) -> None:
    policy = write_policy(tmp_path, POLICY_WITH_DUPLICATE_FILES)

    assert len(ConfigurationLoader().load(policy).rules) == 1
