import logging
from pathlib import Path
from unittest.mock import Mock

import pytest

from powerrules.engine.exceptions import FileIntegrityError, PolicyNotTrustedError
from powerrules.trust.store import TrustStore
from tests.factories import build_trusted_rule_engine, trust_policy_with_fixed_time
from tests.helpers import (
    BACKUP_SCRIPT_NAME,
    SCRIPT_DIRECTORY_NAME,
    TEST_SCRIPT_NAME,
    create_symlink,
    get_commands,
    modify_file,
    write_file,
    write_policy,
)

POLICY = f"""
rules:
  - name: "Test rule"
    conditions:
      process:
        name: "backup.exe"
        exists: false
    actions:
      - name: "Backup"
        run: "backup"
        trusted_files:
          - scripts/{BACKUP_SCRIPT_NAME}
      - name: "Last"
        run: "last"
"""

POLICY_WITH_CONTINUE_ON_ERROR = POLICY.replace(
    'run: "backup"', 'run: "backup"\n        continue_on_error: true'
)

POLICY_WITH_DISABLED_RULE = f"""
rules:
  - name: "Enabled rule"
    conditions:
      process:
        name: "backup.exe"
        exists: false
    actions:
      - run: "enabled"
        trusted_files:
          - scripts/{BACKUP_SCRIPT_NAME}

  - name: "Disabled rule"
    enabled: false
    conditions:
      process:
        name: "backup.exe"
        exists: false
    actions:
      - run: "disabled"
        trusted_files:
          - scripts/{TEST_SCRIPT_NAME}
"""
POLICY_WITH_COMMAND_CONDITION = f"""
rules:
  - name: "Test rule"
    conditions:
      command:
        run: "check"
        trusted_files:
          - scripts/{BACKUP_SCRIPT_NAME}
    actions:
      - name: "Last"
        run: "last"
"""


def test_trusted_policy_runs_all_actions(
    trust_store: TrustStore, workspace: Path, command_provider: Mock
) -> None:
    policy = write_policy(workspace, POLICY)
    trust_policy_with_fixed_time(trust_store, policy)

    result = build_trusted_rule_engine(trust_store, policy).evaluate()

    assert result.action_triggered is True
    assert get_commands(command_provider) == ["backup", "last"]


def test_untrusted_policy_is_rejected_when_loading(
    trust_store: TrustStore, workspace: Path, command_provider: Mock
) -> None:
    policy = write_policy(workspace, POLICY)

    with pytest.raises(PolicyNotTrustedError):
        build_trusted_rule_engine(trust_store, policy)

    command_provider.run.assert_not_called()


def test_modified_policy_is_rejected_when_loading(
    trust_store: TrustStore, workspace: Path
) -> None:
    policy = write_policy(workspace, POLICY)
    trust_policy_with_fixed_time(trust_store, policy)
    modify_file(policy)

    with pytest.raises(PolicyNotTrustedError):
        build_trusted_rule_engine(trust_store, policy)


def test_modified_trusted_file_is_rejected_when_loading(
    trust_store: TrustStore, workspace: Path
) -> None:
    policy = write_policy(workspace, POLICY)
    trust_policy_with_fixed_time(trust_store, policy)
    modify_file(workspace / SCRIPT_DIRECTORY_NAME / BACKUP_SCRIPT_NAME)

    with pytest.raises(PolicyNotTrustedError):
        build_trusted_rule_engine(trust_store, policy)


def test_trusted_file_of_disabled_rule_is_checked_when_loading(
    trust_store: TrustStore, workspace: Path
) -> None:
    policy = write_policy(workspace, POLICY_WITH_DISABLED_RULE)
    trust_policy_with_fixed_time(trust_store, policy)
    modify_file(workspace / SCRIPT_DIRECTORY_NAME / BACKUP_SCRIPT_NAME)

    with pytest.raises(PolicyNotTrustedError):
        build_trusted_rule_engine(trust_store, policy)


# A failure which is tolerated by "continue_on_error" must never hide a modified file
@pytest.mark.parametrize(
    "policy_content",
    [POLICY, POLICY_WITH_CONTINUE_ON_ERROR],
    ids=["default", "continue_on_error"],
)
def test_file_modified_after_loading_prevents_the_action_from_running(
    trust_store: TrustStore,
    workspace: Path,
    command_provider: Mock,
    policy_content: str,
) -> None:
    policy = write_policy(workspace, policy_content)
    trust_policy_with_fixed_time(trust_store, policy)
    engine = build_trusted_rule_engine(trust_store, policy)

    # The policy was loaded and approved, the file changes afterwards
    modify_file(workspace / SCRIPT_DIRECTORY_NAME / BACKUP_SCRIPT_NAME)

    with pytest.raises(FileIntegrityError, match="was modified since it was trusted"):
        engine.evaluate()

    # The remaining actions are skipped as well
    command_provider.run.assert_not_called()


def test_link_pointed_to_another_file_after_loading_is_detected(
    trust_store: TrustStore, workspace: Path, command_provider: Mock
) -> None:
    scripts = workspace / SCRIPT_DIRECTORY_NAME
    other = scripts / TEST_SCRIPT_NAME
    script = scripts / BACKUP_SCRIPT_NAME
    original = write_file(scripts / "original.sh", "echo original")
    script.unlink()
    create_symlink(script, original)
    policy = write_policy(workspace, POLICY)
    trust_policy_with_fixed_time(trust_store, policy)
    engine = build_trusted_rule_engine(trust_store, policy)

    script.unlink()
    create_symlink(script, other)

    with pytest.raises(FileIntegrityError, match="is not trusted yet"):
        engine.evaluate()

    command_provider.run.assert_not_called()


def test_untrusted_policy_runs_with_warning_if_trust_is_not_required(
    trust_store: TrustStore,
    workspace: Path,
    command_provider: Mock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    policy = write_policy(workspace, POLICY)

    with caplog.at_level(logging.WARNING):
        engine = build_trusted_rule_engine(
            trust_store,
            policy,
            require_trust_for_actions=False,
            require_trust_for_conditions=False,
        )
        engine.evaluate()

    assert "not trusted" in caplog.text
    assert get_commands(command_provider) == ["backup", "last"]


def test_trust_removed_while_running_stops_actions_with_trusted_files(
    trust_store: TrustStore, workspace: Path, command_provider: Mock
) -> None:
    policy = write_policy(workspace, POLICY)
    trust_policy_with_fixed_time(trust_store, policy)
    engine = build_trusted_rule_engine(trust_store, policy)

    trust_store.untrust([policy])

    with pytest.raises(FileIntegrityError, match="is not trusted yet"):
        engine.evaluate()

    command_provider.run.assert_not_called()


#########################
# Command condition trust
#########################


def test_trusted_policy_with_command_condition_runs_condition_and_actions(
    trust_store: TrustStore, workspace: Path, command_provider: Mock
) -> None:
    policy = write_policy(workspace, POLICY_WITH_COMMAND_CONDITION)
    trust_policy_with_fixed_time(trust_store, policy)

    result = build_trusted_rule_engine(trust_store, policy).evaluate()

    assert result.action_triggered is True
    assert get_commands(command_provider) == ["check", "last"]


# The conditions of the policy are going to run, even if no action does
def test_untrusted_policy_with_command_condition_is_rejected_if_only_conditions_require_trust(
    trust_store: TrustStore, workspace: Path, command_provider: Mock
) -> None:
    policy = write_policy(workspace, POLICY_WITH_COMMAND_CONDITION)

    with pytest.raises(PolicyNotTrustedError):
        build_trusted_rule_engine(
            trust_store,
            policy,
            require_trust_for_actions=False,
            require_trust_for_conditions=True,
        )

    command_provider.run.assert_not_called()


def test_untrusted_policy_without_command_condition_only_warns_if_only_conditions_require_trust(
    trust_store: TrustStore,
    workspace: Path,
    command_provider: Mock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    policy = write_policy(workspace, POLICY)

    with caplog.at_level(logging.WARNING):
        engine = build_trusted_rule_engine(
            trust_store,
            policy,
            require_trust_for_actions=False,
            require_trust_for_conditions=True,
        )
        engine.evaluate()

    assert "not trusted" in caplog.text
    assert get_commands(command_provider) == ["backup", "last"]


def test_modified_file_of_command_condition_is_rejected_when_loading(
    trust_store: TrustStore, workspace: Path
) -> None:
    policy = write_policy(workspace, POLICY_WITH_COMMAND_CONDITION)
    trust_policy_with_fixed_time(trust_store, policy)
    modify_file(workspace / SCRIPT_DIRECTORY_NAME / BACKUP_SCRIPT_NAME)

    with pytest.raises(PolicyNotTrustedError):
        build_trusted_rule_engine(trust_store, policy)


# The error is no ConditionEvaluationError, so it is not hidden by the evaluation of the condition
def test_file_modified_after_loading_prevents_the_command_condition_from_running(
    trust_store: TrustStore, workspace: Path, command_provider: Mock
) -> None:
    policy = write_policy(workspace, POLICY_WITH_COMMAND_CONDITION)
    trust_policy_with_fixed_time(trust_store, policy)
    engine = build_trusted_rule_engine(trust_store, policy)

    modify_file(workspace / SCRIPT_DIRECTORY_NAME / BACKUP_SCRIPT_NAME)

    with pytest.raises(FileIntegrityError, match="was modified since it was trusted"):
        engine.evaluate()

    command_provider.run.assert_not_called()


def test_file_modified_after_loading_only_warns_if_conditions_do_not_require_trust(
    trust_store: TrustStore,
    workspace: Path,
    command_provider: Mock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    policy = write_policy(workspace, POLICY_WITH_COMMAND_CONDITION)
    trust_policy_with_fixed_time(trust_store, policy)
    engine = build_trusted_rule_engine(
        trust_store,
        policy,
        require_trust_for_actions=True,
        require_trust_for_conditions=False,
    )

    modify_file(workspace / SCRIPT_DIRECTORY_NAME / BACKUP_SCRIPT_NAME)

    with caplog.at_level(logging.WARNING):
        result = engine.evaluate()

    assert "was modified since it was trusted" in caplog.text
    assert result.action_triggered is True
    assert get_commands(command_provider) == ["check", "last"]


def test_trust_removed_while_running_stops_command_conditions_with_trusted_files(
    trust_store: TrustStore, workspace: Path, command_provider: Mock
) -> None:
    policy = write_policy(workspace, POLICY_WITH_COMMAND_CONDITION)
    trust_policy_with_fixed_time(trust_store, policy)
    engine = build_trusted_rule_engine(trust_store, policy)

    trust_store.untrust([policy])

    with pytest.raises(FileIntegrityError, match="is not trusted yet"):
        engine.evaluate()

    command_provider.run.assert_not_called()
