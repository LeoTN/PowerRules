import logging
from collections.abc import Collection, Mapping, Sequence
from pathlib import Path

from powerrules.commands.runner import CommandRunner, FilesVerifier
from powerrules.conditions.matcher import StringMatcher
from powerrules.engine.exceptions import ConditionEvaluationError
from powerrules.providers.command import CommandProvider, CommandResult, Shell

logger = logging.getLogger(__name__)


class CommandCondition:
    """Match depending on the result of a command."""

    def __init__(
        self,
        command_provider: CommandProvider,
        command: str,
        working_directory: Path,
        *,
        rule_name: str,
        timeout: float | None,
        shell: Shell | None = None,
        environment: Mapping[str, str] | None = None,
        success_exit_codes: Collection[int] = (0,),
        stdout_matcher: StringMatcher | None = None,
        stderr_matcher: StringMatcher | None = None,
        trusted_files: Sequence[Path] = (),
        files_verifier: FilesVerifier | None = None,
    ):
        """Create a condition which matches depending on the result of a command.

        The condition matches if the exit code counts as success and the configured outputs match.
        Unlike actions, the command does not receive the "POWERRULES_*" variables.

        Args:
            command_provider: Provider which runs the command.
            command: Command to run.
            working_directory: Directory the command is run in.
            rule_name: Name of the rule the condition belongs to, used in messages.
            timeout: Maximum run time in seconds, None for no time limit.
            shell: Shell to run the command with. None uses the default shell of the platform.
            environment: Additional environment variables for the command.
            success_exit_codes: Exit codes which count as success.
            stdout_matcher: Expectation for stdout, compared after the output was stripped. None accepts any output.
            stderr_matcher: Expectation for stderr, compared after the output was stripped. None accepts any output.
            trusted_files: Absolute paths of the files the command depends on, they are verified before every run.
            files_verifier: Called with the trusted files before every run, it raises an error if they must not be used.
                None skips the verification.
        """
        self.rule_name = rule_name
        self.runner = CommandRunner(
            command_provider=command_provider,
            command=command,
            working_directory=working_directory,
            timeout=timeout,
            shell=shell,
            environment=environment,
            success_exit_codes=success_exit_codes,
            stdout_matcher=stdout_matcher,
            stderr_matcher=stderr_matcher,
            trusted_files=trusted_files,
            files_verifier=files_verifier,
        )

    def evaluate(self) -> bool:
        """Run the command and evaluate whether its result matches the expectations.

        A command with an unexpected exit code or output is no error, the condition simply does not match.

        Returns:
            True if the exit code and all configured outputs match, otherwise False.

        Raises:
            FileIntegrityError: If trust is required and a trusted file cannot be read, is not trusted yet or was modified.
            ConditionEvaluationError: If the command cannot be started or exceeds the timeout.
        """
        # The command is only logged on debug level, because it might contain secrets
        logger.debug(
            f"Command of command condition of rule '{self.rule_name}': {self.runner.command.strip()}"
        )

        # TimeoutError is a subclass of OSError, so it has to be handled first
        try:
            outcome = self.runner.run()
        except TimeoutError as e:
            raise ConditionEvaluationError(
                f"Command condition of rule '{self.rule_name}' timed out after {self.runner.timeout:g} seconds"
            ) from e
        except OSError as e:
            raise ConditionEvaluationError(
                f"Command condition of rule '{self.rule_name}' could not be started: {e}"
            ) from e

        self._log_output(outcome.result)
        logger.debug(
            f"Command condition of rule '{self.rule_name}' finished with exit code {outcome.result.exit_code} "
            f"(expected one of: {self.runner.describe_success_exit_codes()}), "
            f"matched: exit code {outcome.exit_code_matched}, stdout {outcome.stdout_matched}, stderr {outcome.stderr_matched}"
        )

        return outcome.matched

    def _log_output(self, result: CommandResult) -> None:
        """Log the output of the command on debug level.

        A condition which does not match is no failure, so the error output is never logged as an error.

        Args:
            result: Result of the command.
        """
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if stdout:
            logger.debug(
                f"Output of command condition of rule '{self.rule_name}' (stdout):\n{stdout}"
            )

        if stderr:
            logger.debug(
                f"Output of command condition of rule '{self.rule_name}' (stderr):\n{stderr}"
            )
