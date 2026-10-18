import logging
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from powerrules.application.runtime import PlatformProviders, PowerRulesRuntime
from powerrules.application.trust import trust_policy
from powerrules.engine.exceptions import FileIntegrityError, PolicyNotTrustedError
from powerrules.engine.rule_engine import RuleEngine
from powerrules.trust.checker import PolicyTrustChecker
from powerrules.trust.store import TrustStore
from tests.mocks import (
    make_clock_provider,
    make_command_provider,
    make_process_provider,
    make_window_provider,
)

NOW = datetime(2026, 10, 17, 12, 0)

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


@pytest.fixture
def command_provider() -> Iterator[Mock]:
    provider = make_command_provider()
    providers = PlatformProviders(
        clock=make_clock_provider(NOW),
        process=make_process_provider(),
        window=make_window_provider(),
        command=provider,
    )

    with patch(
        "powerrules.application.runtime.get_platform_providers",
        return_value=providers,
    ):
        yield provider


@pytest.fixture
def store(tmp_path: Path) -> TrustStore:
    return TrustStore(tmp_path / "store" / "trust.json")


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    directory = tmp_path / "workspace"
    (directory / "scripts").mkdir(parents=True)

    for name in ("backup.sh", "disabled.sh"):
        (directory / "scripts" / name).write_text(f"echo {name}", encoding="utf-8")

    return directory.resolve()


def _write_policy(workspace: Path, content: str = POLICY) -> Path:
    policy = workspace / "powerrules.yaml"
    policy.write_text(content, encoding="utf-8")

    return policy


def _trust(store: TrustStore, policy: Path) -> None:
    trust_policy(policy, store, make_clock_provider(NOW))


def _build_engine(
    store: TrustStore, policy: Path, *, require_trust: bool = True
) -> RuleEngine:
    runtime = PowerRulesRuntime(
        trust_checker=PolicyTrustChecker(store, require_trust=require_trust)
    )

    return runtime._build_rule_engine(policy)


def _get_commands(command_provider: Mock) -> list[str]:
    return [call.args[0].command for call in command_provider.run.call_args_list]


@pytest.mark.usefixtures("command_provider")
def test_trusted_policy_runs_all_actions(
    store: TrustStore, workspace: Path, command_provider: Mock
) -> None:
    policy = _write_policy(workspace)
    _trust(store, policy)

    result = _build_engine(store, policy).evaluate()

    assert result.action_triggered is True
    assert _get_commands(command_provider) == ["backup", "last"]


def test_untrusted_policy_is_rejected_when_loading(
    store: TrustStore, workspace: Path, command_provider: Mock
) -> None:
    policy = _write_policy(workspace)

    with pytest.raises(PolicyNotTrustedError):
        _build_engine(store, policy)

    command_provider.run.assert_not_called()


def test_modified_policy_is_rejected_when_loading(
    store: TrustStore, workspace: Path
) -> None:
    policy = _write_policy(workspace)
    _trust(store, policy)
    policy.write_text(POLICY + "\n# changed\n", encoding="utf-8")

    with pytest.raises(PolicyNotTrustedError):
        _build_engine(store, policy)


def test_modified_trusted_file_is_rejected_when_loading(
    store: TrustStore, workspace: Path
) -> None:
    policy = _write_policy(workspace)
    _trust(store, policy)
    (workspace / "scripts" / "backup.sh").write_text("echo changed", encoding="utf-8")

    with pytest.raises(PolicyNotTrustedError):
        _build_engine(store, policy)


def test_trusted_file_of_disabled_rule_is_checked_when_loading(
    store: TrustStore, workspace: Path
) -> None:
    policy = _write_policy(workspace, POLICY_WITH_DISABLED_RULE)
    _trust(store, policy)
    (workspace / "scripts" / "disabled.sh").write_text("echo changed", encoding="utf-8")

    with pytest.raises(PolicyNotTrustedError):
        _build_engine(store, policy)


def test_file_modified_after_loading_prevents_the_action_from_running(
    store: TrustStore, workspace: Path, command_provider: Mock
) -> None:
    policy = _write_policy(workspace)
    _trust(store, policy)
    engine = _build_engine(store, policy)

    # The policy was loaded and approved, the file changes afterwards
    (workspace / "scripts" / "backup.sh").write_text("echo changed", encoding="utf-8")

    with pytest.raises(FileIntegrityError, match="was modified since it was trusted"):
        engine.evaluate()

    # The remaining actions are skipped as well
    command_provider.run.assert_not_called()


def test_file_modified_after_loading_is_not_ignored_by_continue_on_error(
    store: TrustStore, workspace: Path, command_provider: Mock
) -> None:
    policy = _write_policy(workspace, POLICY_WITH_CONTINUE_ON_ERROR)
    _trust(store, policy)
    engine = _build_engine(store, policy)
    (workspace / "scripts" / "backup.sh").write_text("echo changed", encoding="utf-8")

    with pytest.raises(FileIntegrityError):
        engine.evaluate()

    command_provider.run.assert_not_called()


def test_link_pointed_to_another_file_after_loading_is_detected(
    store: TrustStore, workspace: Path, command_provider: Mock
) -> None:
    other = workspace / "scripts" / "disabled.sh"
    script = workspace / "scripts" / "backup.sh"
    script.unlink()

    try:
        script.symlink_to(other.parent / "original.sh")
    except (OSError, NotImplementedError):
        pytest.skip("Symbolic links are not available")

    (other.parent / "original.sh").write_text("echo original", encoding="utf-8")
    policy = _write_policy(workspace)
    _trust(store, policy)
    engine = _build_engine(store, policy)

    script.unlink()
    script.symlink_to(other)

    with pytest.raises(FileIntegrityError, match="is not trusted yet"):
        engine.evaluate()

    command_provider.run.assert_not_called()


def test_untrusted_policy_runs_with_warning_if_trust_is_not_required(
    store: TrustStore,
    workspace: Path,
    command_provider: Mock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    policy = _write_policy(workspace)

    with caplog.at_level(logging.WARNING):
        engine = _build_engine(store, policy, require_trust=False)
        engine.evaluate()

    assert "not trusted" in caplog.text
    assert _get_commands(command_provider) == ["backup", "last"]


def test_trust_removed_while_running_stops_actions_with_trusted_files(
    store: TrustStore, workspace: Path, command_provider: Mock
) -> None:
    policy = _write_policy(workspace)
    _trust(store, policy)
    engine = _build_engine(store, policy)

    store.untrust(policy)

    with pytest.raises(FileIntegrityError, match="is not trusted yet"):
        engine.evaluate()

    command_provider.run.assert_not_called()
