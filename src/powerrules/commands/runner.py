from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from powerrules.conditions.matcher import StringMatcher
from powerrules.providers.command import (
    CommandProvider,
    CommandRequest,
    CommandResult,
    Shell,
)

# Verifies the given trusted files right before a command runs and raises an error if they must not be used
FilesVerifier = Callable[[Sequence[Path]], None]


@dataclass(frozen=True)
class CommandRunnerResult:
    """Describe the outcome of a command together with the result of the comparison with the expectations."""

    result: CommandResult
    exit_code_matched: bool
    # True if no output is expected
    stdout_matched: bool
    stderr_matched: bool

    @property
    def matched(self) -> bool:
        """Whether the exit code and all configured outputs matched."""
        return self.exit_code_matched and self.stdout_matched and self.stderr_matched


class CommandRunner:
    """Run a command and compare its exit code and output with the expectations.

    This is shared by actions and command conditions, which translate the result into their own semantics.
    """

    def __init__(
        self,
        command_provider: CommandProvider,
        command: str,
        working_directory: Path,
        *,
        timeout: float | None,
        shell: Shell | None = None,
        environment: Mapping[str, str] | None = None,
        success_exit_codes: Collection[int] = (0,),
        wait: bool = True,
        stdout_matcher: StringMatcher | None = None,
        stderr_matcher: StringMatcher | None = None,
        trusted_files: Sequence[Path] = (),
        files_verifier: FilesVerifier | None = None,
    ):
        """Create a runner for a command.

        Args:
            command_provider: Provider which runs the command.
            command: Command to run.
            working_directory: Directory the command is run in.
            timeout: Maximum run time in seconds, None for no time limit.
            shell: Shell to run the command with. None uses the default shell of the platform.
            environment: Additional environment variables for the command.
            success_exit_codes: Exit codes which count as success.
            wait: Whether to wait for the command to finish. If False, nothing is compared.
            stdout_matcher: Expectation for stdout, compared after the output was stripped. None accepts any output.
            stderr_matcher: Expectation for stderr, compared after the output was stripped. None accepts any output.
            trusted_files: Absolute paths of the files the command depends on, they are verified before every run.
            files_verifier: Called with the trusted files before every run, it raises an error if they must not be used.
                None skips the verification.
        """
        self.command_provider = command_provider
        self.command = command
        self.working_directory = working_directory
        self.timeout = timeout
        self.shell = shell
        self.environment = dict(environment) if environment is not None else {}
        self.success_exit_codes = frozenset(success_exit_codes)
        self.wait = wait
        self.stdout_matcher = stdout_matcher
        self.stderr_matcher = stderr_matcher
        self.trusted_files = tuple(trusted_files)
        self.files_verifier = files_verifier

    def run(self) -> CommandRunnerResult:
        """Verify the trusted files, run the command and compare the result with the expectations.

        A failed comparison is no error, it is part of the returned result.

        Returns:
            The result of the command and which expectations were met.

        Raises:
            FileIntegrityError: If trust is required and a trusted file cannot be read, is not trusted yet or was modified.
            TimeoutError: If the command did not finish within the timeout.
            OSError: If the command cannot be started.
        """
        if self.files_verifier is not None and self.trusted_files:
            self.files_verifier(self.trusted_files)

        result = self.command_provider.run(
            CommandRequest(
                command=self.command,
                working_directory=self.working_directory,
                environment=self.environment,
                timeout=self.timeout,
                wait=self.wait,
                shell=self.shell,
            )
        )

        # There is neither an exit code nor an output of a command which was started in the background
        if not self.wait:
            return CommandRunnerResult(result, True, True, True)

        return CommandRunnerResult(
            result=result,
            exit_code_matched=result.exit_code in self.success_exit_codes,
            stdout_matched=self._matches(self.stdout_matcher, result.stdout),
            stderr_matched=self._matches(self.stderr_matcher, result.stderr),
        )

    @staticmethod
    def _matches(matcher: StringMatcher | None, output: str) -> bool:
        """Return whether the stripped output matches the expectation, no expectation always matches."""
        return matcher is None or matcher.matches(output.strip())
