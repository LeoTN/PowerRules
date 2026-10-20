import logging
from pathlib import Path
from unittest.mock import Mock

import pytest

from powerrules.engine.exceptions import FileIntegrityError, PolicyNotTrustedError
from powerrules.trust.store import TrustStore
from tests.factories import build_trusted_rule_engine, trust_policy_with_fixed_time
from tests.helpers import create_symlink, get_commands, write_file, write_policy

POLICY = """
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
          - scripts/backup.sh
      - name: "Last"
        run: "last"
"""

POLICY_WITH_CONTINUE_ON_ERROR = POLICY.replace(
    'run: "backup"', 'run: "backup"\n        continue_on_error: true'
)

POLICY_WITH_DISABLED_RULE = """
rules:
  - name: "Enabled rule"
    conditions:
      process:
        name: "backup.exe"
        exists: false
    actions:
      - run: "enabled"
        trusted_files:
          - scripts/backup.sh

  - name: "Disabled rule"
    enabled: false
    conditions:
      process:
        name: "backup.exe"
        exists: false
    actions:
      - run: "disabled"
        trusted_files:
          - scripts/disabled.sh
"""


def _modify_script(
    workspace: Path,
    name: str = "backup.sh",
) -> None:
    """Change the content of a script of the workspace, so it no longer matches the trusted digest."""
    write_file(workspace / "scripts" / name, "echo changed")


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
    write_policy(workspace, POLICY + "\n# changed\n")

    with pytest.raises(PolicyNotTrustedError):
        build_trusted_rule_engine(trust_store, policy)


def test_modified_trusted_file_is_rejected_when_loading(
    trust_store: TrustStore, workspace: Path
) -> None:
    policy = write_policy(workspace, POLICY)
    trust_policy_with_fixed_time(trust_store, policy)
    _modify_script(workspace)

    with pytest.raises(PolicyNotTrustedError):
        build_trusted_rule_engine(trust_store, policy)


def test_trusted_file_of_disabled_rule_is_checked_when_loading(
    trust_store: TrustStore, workspace: Path
) -> None:
    policy = write_policy(workspace, POLICY_WITH_DISABLED_RULE)
    trust_policy_with_fixed_time(trust_store, policy)
    _modify_script(workspace, "disabled.sh")

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
    _modify_script(workspace)

    with pytest.raises(FileIntegrityError, match="was modified since it was trusted"):
        engine.evaluate()

    # The remaining actions are skipped as well
    command_provider.run.assert_not_called()


def test_link_pointed_to_another_file_after_loading_is_detected(
    trust_store: TrustStore, workspace: Path, command_provider: Mock
) -> None:
    scripts = workspace / "scripts"
    other = scripts / "disabled.sh"
    script = scripts / "backup.sh"
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
        engine = build_trusted_rule_engine(trust_store, policy, require_trust=False)
        engine.evaluate()

    assert "not trusted" in caplog.text
    assert get_commands(command_provider) == ["backup", "last"]


def test_trust_removed_while_running_stops_actions_with_trusted_files(
    trust_store: TrustStore, workspace: Path, command_provider: Mock
) -> None:
    policy = write_policy(workspace, POLICY)
    trust_policy_with_fixed_time(trust_store, policy)
    engine = build_trusted_rule_engine(trust_store, policy)

    trust_store.untrust(policy)

    with pytest.raises(FileIntegrityError, match="is not trusted yet"):
        engine.evaluate()

    command_provider.run.assert_not_called()
