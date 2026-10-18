import re
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from typer.testing import CliRunner

from powerrules.application.runtime import PlatformProviders
from powerrules.cli.app import app
from powerrules.cli.errors import EXIT_POLICY_ERROR, EXIT_POLICY_TRUST_ERROR
from powerrules.trust.store import TrustStore
from tests.mocks import (
    make_clock_provider,
    make_command_provider,
    make_process_provider,
    make_window_provider,
)

runner = CliRunner()

POLICY = """
rules:
  - name: "Test rule"
    conditions:
      process:
        name: "backup.exe"
        exists: false
    actions:
      - name: "Backup"
        run: "echo test"
        trusted_files:
          - backup.sh
"""


@pytest.fixture
def command_provider() -> Iterator[Mock]:
    """Replace the providers of the runtime, so no command is run for real."""
    provider = make_command_provider()
    providers = PlatformProviders(
        clock=make_clock_provider(datetime(2026, 10, 17, 12, 0)),
        process=make_process_provider(),
        window=make_window_provider(),
        command=provider,
    )

    with patch(
        "powerrules.application.runtime.get_platform_providers",
        return_value=providers,
    ):
        yield provider


def _write_policy(directory: Path, *, create_script: bool = True) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    policy_file = directory / "powerrules.yaml"
    policy_file.write_text(POLICY, encoding="utf-8")

    if create_script:
        (directory / "backup.sh").write_text("echo backup", encoding="utf-8")

    return policy_file


def _trust(policy_file: Path) -> None:
    result = runner.invoke(app, ["trust", "add", "--policy", str(policy_file)])

    assert result.exit_code == 0, result.output


def _get_row(output: str, path: Path) -> str:
    """Return the line of the table which shows the path."""
    return next(line for line in output.splitlines() if str(path) in line)


def _read_log(tmp_path: Path) -> str:
    # The CLI tests run in the temporary directory, which is also the default location of the log file
    return (tmp_path / "powerrules.log").read_text(encoding="utf-8")


#############
# Group tests
#############


def test_cli_trust_displays_help() -> None:
    result = runner.invoke(app, ["trust", "--help"])

    assert result.exit_code == 0
    assert "Manage which policies are trusted." in result.stdout

    for command in ("add", "remove", "list"):
        assert command in result.stdout


#################
# trust add tests
#################


def test_cli_trust_add_trusts_policy_and_shows_table(tmp_path: Path) -> None:
    policy_file = _write_policy(tmp_path)

    result = runner.invoke(app, ["trust", "add", "--policy", str(policy_file)])

    assert result.exit_code == 0
    assert f"Policy '{policy_file}' is now trusted" in result.stdout
    assert "Trust status" in result.stdout
    assert "Trusted at" in result.stdout
    assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", result.stdout)
    assert str(policy_file.resolve()) in result.stdout
    assert str((tmp_path / "backup.sh").resolve()) in result.stdout
    assert TrustStore().get_entry(policy_file) is not None


def test_cli_trust_add_writes_status_only_to_the_log_file(tmp_path: Path) -> None:
    policy_file = _write_policy(tmp_path)

    result = runner.invoke(app, ["trust", "add", "--policy", str(policy_file)])

    message = f"Policy '{policy_file.resolve()}' is trusted"

    assert message not in result.output
    assert message in _read_log(tmp_path)


def test_cli_trust_add_uses_default_policy_in_current_directory(
    tmp_path: Path,
) -> None:
    _write_policy(tmp_path)

    result = runner.invoke(app, ["trust", "add"])

    assert result.exit_code == 0
    assert TrustStore().get_entry(tmp_path / "powerrules.yaml") is not None


def test_cli_trust_add_trusts_the_current_content_again(tmp_path: Path) -> None:
    policy_file = _write_policy(tmp_path)
    _trust(policy_file)
    script = tmp_path / "backup.sh"
    script.write_text("echo changed", encoding="utf-8")

    result = runner.invoke(app, ["trust", "add", "--policy", str(policy_file)])

    assert result.exit_code == 0
    assert "modified" not in result.stdout


def test_cli_trust_add_rejects_missing_policy(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["trust", "add", "--policy", str(tmp_path / "missing.yaml")]
    )

    assert result.exit_code == EXIT_POLICY_ERROR
    assert "Policy file not found" in result.output


def test_cli_trust_add_does_not_trust_invalid_policy(tmp_path: Path) -> None:
    policy_file = tmp_path / "powerrules.yaml"
    policy_file.write_text('rules:\n  - name: "Invalid"\n', encoding="utf-8")

    result = runner.invoke(app, ["trust", "add", "--policy", str(policy_file)])

    assert result.exit_code == EXIT_POLICY_ERROR
    assert "Policy validation failed" in result.output
    assert TrustStore().get_entry(policy_file) is None


def test_cli_trust_add_does_not_trust_policy_with_missing_file(tmp_path: Path) -> None:
    policy_file = _write_policy(tmp_path, create_script=False)

    result = runner.invoke(app, ["trust", "add", "--policy", str(policy_file)])

    assert result.exit_code == EXIT_POLICY_TRUST_ERROR
    assert "cannot be read" in result.output
    assert TrustStore().get_entry(policy_file) is None


####################
# trust remove tests
####################


def test_cli_trust_remove_removes_trust(tmp_path: Path) -> None:
    policy_file = _write_policy(tmp_path)
    _trust(policy_file)

    result = runner.invoke(app, ["trust", "remove", "--policy", str(policy_file)])

    assert result.exit_code == 0
    assert f"Policy '{policy_file}' is no longer trusted" in result.stdout
    assert TrustStore().get_entry(policy_file) is None


def test_cli_trust_remove_reports_policy_which_was_not_trusted(tmp_path: Path) -> None:
    policy_file = _write_policy(tmp_path)

    result = runner.invoke(app, ["trust", "remove", "--policy", str(policy_file)])

    assert result.exit_code == 0
    assert f"Policy '{policy_file}' was not trusted" in result.stdout


def test_cli_trust_remove_works_for_deleted_policy(tmp_path: Path) -> None:
    policy_file = _write_policy(tmp_path)
    _trust(policy_file)
    policy_file.unlink()

    result = runner.invoke(app, ["trust", "remove", "--policy", str(policy_file)])

    assert result.exit_code == 0
    assert "is no longer trusted" in result.stdout


##################
# trust list tests
##################


def test_cli_trust_list_reports_empty_store() -> None:
    result = runner.invoke(app, ["trust", "list"])

    assert result.exit_code == 0
    assert "No policies are trusted" in result.stdout
    assert "Trust status" not in result.stdout


def test_cli_trust_list_shows_current_status_of_every_policy(tmp_path: Path) -> None:
    unchanged = _write_policy(tmp_path / "a")
    modified = _write_policy(tmp_path / "b")
    deleted = _write_policy(tmp_path / "c")

    for policy_file in (unchanged, modified, deleted):
        _trust(policy_file)

    # The trust list has to show the status which is valid now, not the one of the time of trusting
    modified.write_text(POLICY + "\n# changed\n", encoding="utf-8")
    deleted.unlink()

    result = runner.invoke(app, ["trust", "list"])

    assert result.exit_code == 0
    assert "Trusted at" in result.stdout

    assert "trusted" in _get_row(result.stdout, unchanged.resolve())
    assert "modified" in _get_row(result.stdout, modified.resolve())
    assert "missing" in _get_row(result.stdout, deleted.resolve())
    # The files are listed below their policy
    assert "trusted" in _get_row(
        result.stdout, (tmp_path / "a" / "backup.sh").resolve()
    )


def test_cli_trust_list_shows_policies_sorted_by_path(tmp_path: Path) -> None:
    second = _write_policy(tmp_path / "b")
    first = _write_policy(tmp_path / "a")
    _trust(second)
    _trust(first)

    output = runner.invoke(app, ["trust", "list"]).stdout

    assert output.index(str(first.resolve())) < output.index(str(second.resolve()))


def test_cli_trust_list_reports_modified_file_below_trusted_policy(
    tmp_path: Path,
) -> None:
    policy_file = _write_policy(tmp_path)
    _trust(policy_file)
    (tmp_path / "backup.sh").write_text("echo changed", encoding="utf-8")

    result = runner.invoke(app, ["trust", "list"])

    assert "trusted" in _get_row(result.stdout, policy_file.resolve())
    assert "modified" in _get_row(result.stdout, (tmp_path / "backup.sh").resolve())


def test_cli_trust_list_reports_unusable_trust_store(isolated_home: Path) -> None:
    store_file = isolated_home / ".powerrules" / "trust.json"
    store_file.parent.mkdir()
    store_file.write_text("not json", encoding="utf-8")

    result = runner.invoke(app, ["trust", "list"])

    assert result.exit_code == 1
    assert "corrupted or has an unsupported format" in result.output


###############################
# policy validate and run tests
###############################


def test_cli_policy_validate_shows_table_once_with_unknown_status(
    tmp_path: Path,
) -> None:
    policy_file = _write_policy(tmp_path)

    result = runner.invoke(app, ["policy", "validate", "--policy", str(policy_file)])

    assert result.exit_code == 0
    assert "Trust status" in result.stdout
    assert "unknown" in result.stdout
    assert "trust add --policy" in result.output
    # The messages of the single entries are only written to the log file
    assert "is not trusted yet" not in result.output
    assert "is not trusted yet" in _read_log(tmp_path)


def test_cli_policy_validate_shows_trusted_status(tmp_path: Path) -> None:
    policy_file = _write_policy(tmp_path)
    _trust(policy_file)

    result = runner.invoke(app, ["policy", "validate", "--policy", str(policy_file)])

    assert result.exit_code == 0
    assert "Trust status" in result.stdout
    assert "unknown" not in result.stdout
    assert "modified" not in result.stdout
    assert "is valid" in result.stdout


def test_cli_policy_validate_reports_modified_policy(tmp_path: Path) -> None:
    policy_file = _write_policy(tmp_path)
    _trust(policy_file)
    policy_file.write_text(POLICY + "\n# changed\n", encoding="utf-8")

    result = runner.invoke(app, ["policy", "validate", "--policy", str(policy_file)])

    assert result.exit_code == 0
    assert "modified" in _get_row(result.stdout, policy_file.resolve())


def test_cli_policy_run_rejects_untrusted_policy(
    tmp_path: Path, command_provider: Mock
) -> None:
    policy_file = _write_policy(tmp_path)

    result = runner.invoke(
        app, ["policy", "run", "--once", "--policy", str(policy_file)]
    )

    assert result.exit_code == EXIT_POLICY_TRUST_ERROR
    assert "trust add --policy" in result.output
    command_provider.run.assert_not_called()


def test_cli_policy_run_runs_trusted_policy(
    tmp_path: Path, command_provider: Mock
) -> None:
    policy_file = _write_policy(tmp_path)
    _trust(policy_file)

    result = runner.invoke(
        app, ["policy", "run", "--once", "--policy", str(policy_file)]
    )

    assert result.exit_code == 0
    command_provider.run.assert_called_once()


def test_cli_policy_run_rejects_modified_policy(
    tmp_path: Path, command_provider: Mock
) -> None:
    policy_file = _write_policy(tmp_path)
    _trust(policy_file)
    policy_file.write_text(POLICY + "\n# changed\n", encoding="utf-8")

    result = runner.invoke(
        app, ["policy", "run", "--once", "--policy", str(policy_file)]
    )

    assert result.exit_code == EXIT_POLICY_TRUST_ERROR
    assert "modified" in result.stdout
    command_provider.run.assert_not_called()


def test_cli_policy_run_rejects_modified_trusted_file(
    tmp_path: Path, command_provider: Mock
) -> None:
    policy_file = _write_policy(tmp_path)
    _trust(policy_file)
    (tmp_path / "backup.sh").write_text("echo changed", encoding="utf-8")

    result = runner.invoke(
        app, ["policy", "run", "--once", "--policy", str(policy_file)]
    )

    assert result.exit_code == EXIT_POLICY_TRUST_ERROR
    assert "modified" in _get_row(result.stdout, (tmp_path / "backup.sh").resolve())
    command_provider.run.assert_not_called()


def test_cli_policy_run_can_skip_trust_requirement(
    tmp_path: Path, command_provider: Mock
) -> None:
    policy_file = _write_policy(tmp_path)

    result = runner.invoke(
        app,
        ["policy", "run", "--once", "--no-require-trust", "--policy", str(policy_file)],
    )

    assert result.exit_code == 0
    assert "are not trusted" in result.output
    command_provider.run.assert_called_once()


def test_cli_policy_run_dry_run_does_not_require_trust(
    tmp_path: Path, command_provider: Mock
) -> None:
    policy_file = _write_policy(tmp_path)

    result = runner.invoke(
        app, ["policy", "run", "--once", "--dry-run", "--policy", str(policy_file)]
    )

    assert result.exit_code == 0
    assert "[DRY RUN] Rule 'Test rule' matched" in result.stdout
    assert "Trust status" in result.stdout
    command_provider.run.assert_not_called()


def test_cli_policy_run_does_not_run_policy_after_trust_was_removed(
    tmp_path: Path, command_provider: Mock
) -> None:
    policy_file = _write_policy(tmp_path)
    _trust(policy_file)
    runner.invoke(app, ["trust", "remove", "--policy", str(policy_file)])

    result = runner.invoke(
        app, ["policy", "run", "--once", "--policy", str(policy_file)]
    )

    assert result.exit_code == EXIT_POLICY_TRUST_ERROR
    command_provider.run.assert_not_called()
