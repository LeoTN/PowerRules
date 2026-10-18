from pathlib import Path
from unittest.mock import Mock

import pytest

from powerrules.actions.command import CommandAction
from powerrules.engine.exceptions import ActionExecutionError, FileIntegrityError
from powerrules.providers.command import CommandRequest, CommandResult
from tests.mocks import make_command_provider

TRUSTED_FILES = (Path("scripts") / "backup.sh",)


def _make_action(
    command_provider: Mock,
    *,
    trusted_files: tuple[Path, ...] = TRUSTED_FILES,
    files_verifier: Mock | None = None,
    continue_on_error: bool = False,
) -> CommandAction:
    return CommandAction(
        command_provider,
        "echo test",
        Path("work"),
        name="Test action",
        rule_name="Test rule",
        trusted_files=trusted_files,
        files_verifier=files_verifier,
        continue_on_error=continue_on_error,
    )


def test_command_action_verifies_trusted_files_before_running_the_command() -> None:
    calls: list[str] = []
    command_provider = make_command_provider()

    def run(_request: CommandRequest) -> CommandResult:
        calls.append("run")

        return CommandResult(exit_code=0)

    command_provider.run.side_effect = run
    files_verifier = Mock(side_effect=lambda _files: calls.append("verify"))

    _make_action(command_provider, files_verifier=files_verifier).execute()

    assert calls == ["verify", "run"]
    files_verifier.assert_called_once_with(TRUSTED_FILES)


def test_command_action_verifies_trusted_files_on_every_execution() -> None:
    files_verifier = Mock()
    action = _make_action(make_command_provider(), files_verifier=files_verifier)

    action.execute()
    action.execute()

    assert files_verifier.call_count == 2


def test_command_action_stores_trusted_files_as_tuple() -> None:
    action = CommandAction(
        make_command_provider(),
        "echo test",
        Path("work"),
        name="Test action",
        rule_name="Test rule",
        trusted_files=[Path("a.sh"), Path("b.sh")],
    )

    assert action.trusted_files == (Path("a.sh"), Path("b.sh"))


def test_command_action_does_not_verify_without_trusted_files() -> None:
    files_verifier = Mock()
    command_provider = make_command_provider()

    _make_action(
        command_provider, trusted_files=(), files_verifier=files_verifier
    ).execute()

    files_verifier.assert_not_called()
    command_provider.run.assert_called_once()


def test_command_action_runs_without_verifier() -> None:
    command_provider = make_command_provider()

    _make_action(command_provider, files_verifier=None).execute()

    command_provider.run.assert_called_once()


def test_command_action_does_not_run_command_when_verification_fails() -> None:
    command_provider = make_command_provider()
    files_verifier = Mock(side_effect=FileIntegrityError("Test file was modified"))

    with pytest.raises(FileIntegrityError, match="Test file was modified"):
        _make_action(command_provider, files_verifier=files_verifier).execute()

    command_provider.run.assert_not_called()


def test_command_action_never_skips_failed_verification_with_continue_on_error() -> (
    None
):
    command_provider = make_command_provider()
    files_verifier = Mock(side_effect=FileIntegrityError("Test file was modified"))
    action = _make_action(
        command_provider, files_verifier=files_verifier, continue_on_error=True
    )

    with pytest.raises(FileIntegrityError):
        action.execute()

    command_provider.run.assert_not_called()


def test_command_action_still_continues_on_command_error_after_verification() -> None:
    files_verifier = Mock()
    action = _make_action(
        make_command_provider(CommandResult(exit_code=1)),
        files_verifier=files_verifier,
        continue_on_error=True,
    )

    action.execute()

    files_verifier.assert_called_once()


def test_failed_command_after_verification_is_an_action_execution_error() -> None:
    action = _make_action(
        make_command_provider(CommandResult(exit_code=1)), files_verifier=Mock()
    )

    with pytest.raises(ActionExecutionError):
        action.execute()
