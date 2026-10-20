"""Plain helper functions and constants which are shared by the tests.

Mocked objects and other test objects are created in "tests.factories", fixtures are defined in the "conftest.py" files.
This module must not import "tests.factories", because "tests.factories" imports this module.
"""

import logging
import os
import shutil
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Literal
from unittest.mock import Mock

import pytest
import typer
from rich.text import Text
from typer.testing import CliRunner, Result

from powerrules.cli.app import app
from powerrules.cli.errors import handle_cli_error
from powerrules.trust.report import TrustReport
from powerrules.trust.store import (
    TrustStatus,
    TrustStore,
    compute_digest,
    compute_trusted_file_digests,
)

# A Saturday, several tests depend on the weekday
DEFAULT_NOW_SATURDAY_NOON = datetime(2026, 8, 22, 12, 0)
# The time at which policies are trusted in the trust tests
TRUSTED_AT = datetime(2026, 10, 17, 12)
DEFAULT_BASE_DIRECTORY = Path("policies")
# Working directory of actions which are created without an explicit one
DEFAULT_WORKING_DIRECTORY = Path("work")
DEFAULT_POLICY_FILE_NAME = "powerrules.yaml"
# Default location of the log file, relative to the directory in which the CLI runs
DEFAULT_LOG_FILE_NAME = "powerrules.log"
# The smallest policy which is valid, only used as a file content
EMPTY_POLICY_CONTENT = b"rules: []\n"
# The scripts lie in this directory next to the policy. "BACKUP_SCRIPT_POLICY" trusts the backup script
SCRIPT_DIRECTORY_NAME = "scripts"
BACKUP_SCRIPT_NAME = "backup.sh"
# Relative to the directory of the policy, written with a forward slash like in a policy
BACKUP_SCRIPT_RELATIVE_PATH = f"{SCRIPT_DIRECTORY_NAME}/{BACKUP_SCRIPT_NAME}"

posix_only = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("sh") is None,
    reason="Requires a POSIX shell",
)
windows_only = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Requires Windows",
)


#####################
# File system helpers
#####################


def write_file(
    path: Path,
    content: str = "content",
) -> Path:
    """Write a UTF-8 text file and create the missing parent directories.

    Args:
        path: Path of the file.
        content: Text which is written.

    Returns:
        The given path, unchanged (symbolic links are not resolved).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

    return path


def write_resolved_file(
    path: Path,
    content: str = "content",
) -> Path:
    """Write a UTF-8 text file and create the missing parent directories.

    Args:
        path: Path of the file.
        content: Text which is written.

    Returns:
        The path of the file with all symbolic links resolved.
    """
    return write_file(path, content).resolve()


def write_policy(
    directory: Path,
    content: str,
    *,
    file_name: str = DEFAULT_POLICY_FILE_NAME,
) -> Path:
    """Write a policy file into a directory.

    Args:
        directory: Directory of the policy. It is created if it does not exist.
        content: YAML content of the policy.
        file_name: Name of the policy file.

    Returns:
        The path of the policy file.
    """
    return write_file(directory / file_name, content)


SCRIPT_DIRECTORY_NAME = "scripts"


def write_workspace_scripts(directory: Path) -> Path:
    """Write the scripts "scripts/backup.sh" and "scripts/disabled.sh" into a directory.

    Args:
        directory: Directory which receives the "scripts" folder. It is created if it does not exist.

    Returns:
        The directory with all symbolic links resolved.
    """
    for name in (BACKUP_SCRIPT_NAME, "disabled.sh"):
        write_file(directory / SCRIPT_DIRECTORY_NAME / name, f"echo {name}")

    return directory.resolve()


def create_symlink(
    link: Path,
    target: Path,
) -> None:
    """Create a symbolic link, or skip the test if the platform or the user does not allow it.

    Args:
        link: Path of the link which is created.
        target: Path which the link points to.
    """
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("Symbolic links are not available")


def lowercase_normcase(path: str | os.PathLike[str]) -> str:
    """Simulate the case-insensitive path normalization of Windows.

    Args:
        path: Path which is normalized.

    Returns:
        The lowercase path.
    """
    return os.fspath(path).lower()


#############
# Policy data
#############

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


def make_policy_yaml(
    *,
    rule_name: str = "Test rule",
    command: str = "echo test",
    action_name: str | None = None,
    trusted_files: Sequence[str] = (),
) -> str:
    """Create a valid policy with a single rule and a single action.

    Args:
        rule_name: Name of the rule.
        command: Command of the action.
        action_name: Name of the action. Unnamed if None.
        trusted_files: Trusted files of the action.

    Returns:
        The YAML content of the policy.
    """
    lines = [
        "rules:",
        f'  - name: "{rule_name}"',
        "    conditions:",
        "      process:",
        '        name: "backup.exe"',
        "        exists: false",
        "    actions:",
        f'      - run: "{command}"',
    ]

    if action_name is not None:
        lines.append(f'        name: "{action_name}"')

    if trusted_files:
        lines.append("        trusted_files:")
        lines.extend(f"          - {file}" for file in trusted_files)

    return "\n".join(lines) + "\n"


# A valid policy whose only action trusts the script "backup.sh"
BACKUP_SCRIPT_POLICY = make_policy_yaml(
    action_name="Backup", trusted_files=[BACKUP_SCRIPT_RELATIVE_PATH]
)


def make_rule_data(**overrides: object) -> dict[str, object]:
    """Create the raw data of a valid rule, as it is passed to the validation of the configuration.

    Args:
        **overrides: Fields which replace the defaults.

    Returns:
        The raw rule data.
    """
    rule: dict[str, object] = {
        "name": "Test rule",
        "conditions": {"process": {"name": "backup.exe", "exists": False}},
        "actions": [{"run": "echo test"}],
    }

    return {**rule, **overrides}


def make_trusted_files_rule_data(
    name: str,
    files: list[str],
    *,
    enabled: bool = True,
) -> dict[str, object]:
    """Create the raw data of a rule whose action has the given trusted files.

    Args:
        name: Name of the rule.
        files: Configured trusted files of the action.
        enabled: Whether the rule is enabled.

    Returns:
        The raw rule data.
    """
    return make_rule_data(
        name=name,
        enabled=enabled,
        actions=[{"run": "echo test", "trusted_files": files}],
    )


def write_backup_script_policy(
    directory: Path,
    *,
    create_script: bool = True,
) -> Path:
    """Write "BACKUP_SCRIPT_POLICY" and, optionally, the scripts which it trusts, into a directory.

    Args:
        directory: Directory of the policy and the scripts. It is created if it does not exist.
        create_script: Whether the trusted scripts are written as well.

    Returns:
        The path of the policy file.
    """
    policy_file = write_policy(directory, BACKUP_SCRIPT_POLICY)

    if create_script:
        write_workspace_scripts(directory)

    return policy_file


###############
# Trust helpers
###############


def trust_current_content(
    trust_store: TrustStore,
    policy: Path,
    *files: Path,
) -> None:
    """Trust the current content of a policy and of the given files.

    Args:
        trust_store: Store in which the trust is saved.
        policy: Path of the policy file with all symbolic links resolved.
        *files: Trusted files of the policy.
    """
    trust_store.trust(
        policy,
        compute_digest(policy.read_bytes()),
        TRUSTED_AT,
        compute_trusted_file_digests(policy.parent, files),
    )


def corrupt_trust_store(trust_store: TrustStore) -> None:
    """Replace the content of a trust store by invalid JSON, so it cannot be read anymore.

    Args:
        trust_store: Store which is corrupted. Its directory is created if it does not exist.
    """
    trust_store.path.parent.mkdir(parents=True, exist_ok=True)
    trust_store.path.write_text("not json", encoding="utf-8")


def get_trust_statuses(report: TrustReport) -> list[TrustStatus]:
    """Return the statuses of all entries of a trust report.

    Args:
        report: Report whose entries are inspected.

    Returns:
        The statuses in the order of the entries.
    """
    return [entry.status for entry in report.entries]


def trust_policy_via_cli(policy_file: Path) -> None:
    """Trust a policy with the command "trust add" and make sure that it succeeds.

    Args:
        policy_file: Path of the policy file.
    """
    result = CliRunner().invoke(app, ["trust", "add", "--policy", str(policy_file)])

    assert result.exit_code == 0, result.output


####################
# Inspection helpers
####################


def get_log_records(
    caplog: pytest.LogCaptureFixture,
    logger_name: str | None = None,
    *,
    min_level: int = logging.NOTSET,
) -> list[logging.LogRecord]:
    """Return the captured log records, optionally filtered.

    Args:
        caplog: The "caplog" fixture of the test.
        logger_name: Only records of this logger. None returns the records of all loggers.
        min_level: Only records of at least this level.

    Returns:
        The matching records in the order in which they were logged.
    """
    return [
        record
        for record in caplog.records
        if (logger_name is None or record.name == logger_name)
        and record.levelno >= min_level
    ]


def get_log_entries(
    caplog: pytest.LogCaptureFixture,
    logger_name: str | None = None,
    *,
    min_level: int = logging.NOTSET,
) -> list[tuple[int, str]]:
    """Return level and message of the captured log records, optionally filtered.

    Args:
        caplog: The "caplog" fixture of the test.
        logger_name: Only records of this logger. None returns the records of all loggers.
        min_level: Only records of at least this level.

    Returns:
        Pairs of level and formatted message in the order in which they were logged.
    """
    return [
        (record.levelno, record.getMessage())
        for record in get_log_records(caplog, logger_name, min_level=min_level)
    ]


def get_log_messages(
    caplog: pytest.LogCaptureFixture,
    logger_name: str | None = None,
    *,
    min_level: int = logging.NOTSET,
) -> list[str]:
    """Return the formatted messages of the captured log records, optionally filtered.

    Args:
        caplog: The "caplog" fixture of the test.
        logger_name: Only records of this logger. None returns the records of all loggers.
        min_level: Only records of at least this level.

    Returns:
        The messages in the order in which they were logged.
    """
    return [
        message
        for _, message in get_log_entries(caplog, logger_name, min_level=min_level)
    ]


def get_commands(command_provider: Mock) -> list[str]:
    """Return the commands of all requests in the order in which they were run.

    Args:
        command_provider: Mocked command provider, see "make_command_provider()".

    Returns:
        The commands of the requests.
    """
    return [call.args[0].command for call in command_provider.run.call_args_list]


def get_table_row(
    output: str,
    path: Path,
) -> str:
    """Return the line of a printed table which shows the path.

    Args:
        output: Console output which contains the table.
        path: Path which is searched.

    Returns:
        The first line which contains the path.

    Raises:
        StopIteration: If no line contains the path.
    """
    return next(line for line in output.splitlines() if str(path) in line)


def get_plain_output(
    result: Result,
    source: Literal["stdout", "output"] = "stdout",
) -> str:
    """Return the plain output stripped from all formatting and control characters for easier assertion.

    Args:
        result: Result from an invoked CLI command.
        source: The output source to use.
    Returns:
        The plain output.
    """

    return Text.from_ansi(getattr(result, source)).plain


def read_log_file(
    directory: Path,
    *,
    file_name: str = DEFAULT_LOG_FILE_NAME,
) -> str:
    """Read the log file which the CLI wrote into a directory.

    The CLI tests run in a temporary directory, which is also the default location of the log file.

    Args:
        directory: Directory which contains the log file.
        file_name: Name of the log file.

    Returns:
        The content of the log file.
    """
    return (directory / file_name).read_text(encoding="utf-8")


def get_cli_exit(error: Exception) -> typer.Exit:
    """Handle an error with the error handler of the CLI and return the exit which it raises.

    Args:
        error: Error which is handled.

    Returns:
        The raised exit, so the test can inspect its exit code.
    """
    with pytest.raises(typer.Exit) as exc_info:
        handle_cli_error(error)

    return exc_info.value
