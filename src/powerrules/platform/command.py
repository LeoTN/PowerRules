import contextlib
import ctypes
import logging
import os
import shutil
import subprocess
import sys
from functools import cache
from pathlib import Path

import psutil

from powerrules.providers.command import CommandRequest, CommandResult, Shell

logger = logging.getLogger(__name__)

# Like the PowerShell of GitHub Actions: errors stop the command and the exit code of the last program is passed through
_POWERSHELL_PREFIX = "$ErrorActionPreference = 'Stop'"
_POWERSHELL_SUFFIX = (
    "if ((Test-Path -LiteralPath variable:\\LASTEXITCODE)) { exit $LASTEXITCODE }"
)


def build_shell_arguments(shell: Shell, command: str) -> str | list[str]:
    """Build the arguments which run a command in a shell.

    The options follow the shells of GitHub Actions: A command with several lines stops at the first failing line
    and the exit code of the command is passed through as the exit code of the shell.

    Args:
        shell: Shell to run the command with.
        command: Command to run.

    Returns:
        The arguments for the process. The command line of "cmd" is a single string, because
        Python would escape the quotes of an argument list with backslashes, which "cmd" does not understand.
    """
    match shell:
        case Shell.SH:
            return ["sh", "-e", "-c", command]
        case Shell.BASH:
            return ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", command]
        case Shell.CMD:
            # "/s" removes the outer quotes, all quotes inside of the command are kept
            return f'cmd.exe /d /s /c "{command}"'
        case Shell.POWERSHELL | Shell.PWSH:
            arguments = [shell.value, "-NoProfile", "-NonInteractive"]

            if sys.platform == "win32":
                # Unsigned scripts are blocked by default, the setting only applies to this process
                arguments += ["-ExecutionPolicy", "Bypass"]

            # The line breaks keep a comment at the end of the command from swallowing the suffix
            arguments += [
                "-Command",
                f"{_POWERSHELL_PREFIX}\n{command}\n{_POWERSHELL_SUFFIX}",
            ]

            return arguments


def _ensure_shell_is_available(shell: Shell) -> None:
    """Make sure that a shell can be started on the current system.

    Args:
        shell: Shell to check.

    Raises:
        FileNotFoundError: If the shell cannot be found in the PATH.
    """
    if shutil.which(shell.value) is None:
        raise FileNotFoundError(
            f"The shell '{shell.value}' was not found, make sure that it is installed and available in the PATH"
        )


@cache
def _get_output_encoding() -> str:
    """Return the encoding which the console programs use for their output."""
    if sys.platform == "win32":
        # Console programs write in the OEM code page (e.g. cp850), not in the ANSI one
        return f"cp{ctypes.windll.kernel32.GetOEMCP()}"

    return "utf-8"


def _decode_output(output: bytes) -> str:
    """Decode the output of a command, invalid bytes are replaced instead of raising an error."""
    return output.decode(_get_output_encoding(), errors="replace")


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    """Kill a process and all of its descendants.

    Killing only the shell would leave the programs started by it running.

    Args:
        process: Process whose tree is killed.
    """
    # The children are collected first, they cannot be found anymore once their parent is gone
    try:
        children = psutil.Process(process.pid).children(recursive=True)
    except psutil.NoSuchProcess:
        children = []

    for child in children:
        # Best effort: a process which already ended or cannot be accessed is skipped
        with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied):
            child.kill()

    process.kill()


class SubprocessCommandProvider:
    """Run commands in a shell on Windows, Linux and macOS."""

    def __init__(self, default_shell: Shell) -> None:
        """Create the provider.

        Args:
            default_shell: Shell for requests which do not define one.
        """
        self.default_shell = default_shell

    def run(self, request: CommandRequest) -> CommandResult:
        """Run a command in a shell.

        Args:
            request: The command and the way it is run.

        Returns:
            The exit code and the output of the command, or a result without exit code if it was started in the background.

        Raises:
            TimeoutError: If the command did not finish within the timeout. The command and its child processes are killed.
            OSError: If the command cannot be started (e.g. the shell is not installed or the working directory does not exist).
        """
        if not request.working_directory.is_dir():
            raise NotADirectoryError(
                f"Working directory '{request.working_directory}' does not exist or is not a directory"
            )

        shell = self.default_shell if request.shell is None else request.shell
        # Checked when the command runs and not when the policy is loaded, so a policy can contain rules for other platforms
        _ensure_shell_is_available(shell)
        arguments = build_shell_arguments(shell, request.command)
        # Merge the platform environment with the request environment variables, the request variables take precedence
        environment = {**os.environ, **request.environment}

        if not request.wait:
            self._start_in_background(arguments, request.working_directory, environment)

            return CommandResult(exit_code=None)

        return self._run_and_wait(
            arguments, request.working_directory, environment, request.timeout
        )

    @staticmethod
    def _run_and_wait(
        arguments: str | list[str],
        working_directory: Path,
        environment: dict[str, str],
        timeout: float | None,
    ) -> CommandResult:
        """Run a command and wait until it finishes.

        Raises:
            TimeoutError: If the command did not finish within the timeout.
            OSError: If the command cannot be started.
        """
        with subprocess.Popen(
            arguments,
            cwd=working_directory,
            env=environment,
            # A command which waits for an input would otherwise block until the timeout
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as process:
            try:
                stdout, stderr = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired as e:
                _terminate_process_tree(process)

                raise TimeoutError(
                    f"Command did not finish within {timeout:g} seconds"
                ) from e

        return CommandResult(
            exit_code=process.returncode,
            stdout=_decode_output(stdout),
            stderr=_decode_output(stderr),
        )

    @staticmethod
    def _start_in_background(
        arguments: str | list[str],
        working_directory: Path,
        environment: dict[str, str],
    ) -> None:
        """Start a command which keeps running independently of PowerRules.

        Raises:
            OSError: If the command cannot be started.
        """
        # The process is intentionally not waited for, so there is no output to read
        if sys.platform == "win32":
            # A hidden console of its own (CREATE_NO_WINDOW) instead of no console at all (DETACHED_PROCESS),
            # because PowerShell does not start without a console. The new process group and console keep
            # the command alive when PowerRules or its terminal ends
            process = subprocess.Popen(
                arguments,
                cwd=working_directory,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW
                | subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        else:
            process = subprocess.Popen(
                arguments,
                cwd=working_directory,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

        logger.debug(f"Started background command with process ID {process.pid}")
