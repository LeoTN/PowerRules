from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol


class Shell(StrEnum):
    """Supported shells to run commands with."""

    SH = "sh"
    BASH = "bash"
    CMD = "cmd"
    POWERSHELL = "powershell"
    PWSH = "pwsh"


@dataclass(frozen=True)
class CommandRequest:
    """Describe a command which is run in a shell."""

    command: str
    working_directory: Path
    # Additional variables, they are added to the environment of the current process
    environment: Mapping[str, str]
    # None means that the command may run without a time limit
    timeout: float | None
    # False starts the command in the background without waiting for it
    wait: bool
    # None means that the provider uses the default shell of the platform
    shell: Shell | None = None


@dataclass(frozen=True)
class CommandResult:
    """Describe the outcome of a command."""

    # None if the command was started in the background
    exit_code: int | None
    stdout: str = ""
    stderr: str = ""


class CommandProvider(Protocol):
    def run(self, request: CommandRequest) -> CommandResult:
        """Run a command in a shell.

        A command which exits with a non-zero exit code is not an error here, the exit code is part of the result.

        Args:
            request: The command and the way it is run.

        Returns:
            The exit code and the output of the command.

        Raises:
            TimeoutError: If the command did not finish within the timeout. The command is terminated.
            OSError: If the command cannot be started (e.g. the shell or the working directory does not exist).
        """
        ...
