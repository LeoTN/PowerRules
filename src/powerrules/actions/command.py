import logging
from collections.abc import Collection, Mapping, Sequence
from pathlib import Path

from powerrules.commands.runner import CommandRunner, FilesVerifier
from powerrules.conditions.matcher import StringMatcher
from powerrules.engine.exceptions import ActionExecutionError
from powerrules.providers.command import CommandProvider, CommandResult, Shell

logger = logging.getLogger(__name__)

# Time in seconds a command may run before it is terminated
DEFAULT_COMMAND_TIMEOUT_SECONDS = 60

# Variables with this prefix are set by PowerRules for the started command
RESERVED_ENVIRONMENT_PREFIX = "POWERRULES_"

# Variables which PowerRules sets for the started command, the prefix is reserved in the configuration
RULE_NAME_ENVIRONMENT_VARIABLE = "POWERRULES_RULE_NAME"
ACTION_NAME_ENVIRONMENT_VARIABLE = "POWERRULES_ACTION_NAME"


class CommandAction:
    def __init__(
        self,
        command_provider: CommandProvider,
        command: str,
        working_directory: Path,
        *,
        name: str,
        rule_name: str,
        shell: Shell | None = None,
        environment: Mapping[str, str] | None = None,
        timeout: float | None = DEFAULT_COMMAND_TIMEOUT_SECONDS,
        success_exit_codes: Collection[int] = (0,),
        wait: bool = True,
        continue_on_error: bool = False,
        trusted_files: Sequence[Path] = (),
        files_verifier: FilesVerifier | None = None,
        stdout_matcher: StringMatcher | None = None,
        stderr_matcher: StringMatcher | None = None,
    ):
        """Create an action which runs a command in a shell.

        Args:
            command_provider: Provider which runs the command.
            command: Command to run.
            working_directory: Directory the command is run in.
            name: Name of the action, used in log messages.
            rule_name: Name of the rule the action belongs to, passed to the command.
            shell: Shell to run the command with. None uses the default shell of the platform.
            environment: Additional environment variables for the command.
            timeout: Maximum run time in seconds, None for no time limit.
            success_exit_codes: Exit codes which count as success.
            wait: Whether to wait for the command to finish. If False, the timeout, the exit codes and the outputs are ignored.
            continue_on_error: Whether a failure is only logged instead of raised.
            trusted_files: Absolute paths of the files the command depends on, they are verified before every run.
            files_verifier: Called with the trusted files before every run, it raises an error if they must not be used.
                None skips the verification.
            stdout_matcher: Expectation for stdout. A different output counts as a failure. None accepts any output.
            stderr_matcher: Expectation for stderr. A different output counts as a failure. None accepts any output.
        """
        self.command_provider = command_provider
        self.command = command
        self.working_directory = working_directory
        self.name = name
        self.rule_name = rule_name
        self.shell = shell
        self.environment = dict(environment) if environment is not None else {}
        self.timeout = timeout
        self.success_exit_codes = frozenset(success_exit_codes)
        self.wait = wait
        self.continue_on_error = continue_on_error
        self.trusted_files = tuple(trusted_files)
        self.files_verifier = files_verifier
        self.stdout_matcher = stdout_matcher
        self.stderr_matcher = stderr_matcher
        self.runner = CommandRunner(
            command_provider=command_provider,
            command=command,
            working_directory=working_directory,
            timeout=timeout,
            shell=shell,
            # The variables of PowerRules come last, the configuration cannot define them
            environment={
                **self.environment,
                RULE_NAME_ENVIRONMENT_VARIABLE: rule_name,
                ACTION_NAME_ENVIRONMENT_VARIABLE: name,
            },
            success_exit_codes=self.success_exit_codes,
            wait=wait,
            stdout_matcher=stdout_matcher,
            stderr_matcher=stderr_matcher,
            trusted_files=self.trusted_files,
            files_verifier=files_verifier,
        )

    def execute(self) -> None:
        """Run the command.

        The trusted files are verified first. If the action is configured with "continue_on_error",
        a failure of the command is only logged as a warning.

        Raises:
            FileIntegrityError: If trust is required and a trusted file cannot be read, is not trusted yet or was modified.
            ActionExecutionError: If the command cannot be started, exceeds the timeout, finishes with an exit code
                which does not count as success or produces an unexpected output.
        """
        logger.info(f"Running action '{self.name}'")
        # The command is only logged on debug level, because it might contain secrets
        logger.debug(f"Command of action '{self.name}': {self.command.strip()}")

        try:
            self._run_command()
        except ActionExecutionError as e:
            # A failed integrity check is no ActionExecutionError: "continue_on_error" must never skip it
            if not self.continue_on_error:
                raise

            logger.warning(
                f"{e} (continue_on_error is set, continuing with the remaining actions)"
            )

    def _run_command(self) -> None:
        """Run the command and check its result.

        Raises:
            FileIntegrityError: If trust is required and a trusted file cannot be read, is not trusted yet or was modified.
            ActionExecutionError: If the command cannot be started, exceeds the timeout,
                finishes with an exit code which does not count as success or produces an unexpected output.
        """
        # TimeoutError is a subclass of OSError, so it has to be handled first
        try:
            outcome = self.runner.run()
        except TimeoutError as e:
            raise ActionExecutionError(
                f"Action '{self.name}' timed out after {self.timeout:g} seconds"
            ) from e
        except OSError as e:
            raise ActionExecutionError(
                f"Action '{self.name}' could not be started: {e}"
            ) from e

        if not self.wait:
            logger.info(f"Started action '{self.name}' in the background")
            return

        self._log_output(outcome.result, failed=not outcome.matched)

        if not outcome.exit_code_matched:
            expected_exit_codes = ", ".join(
                str(exit_code) for exit_code in sorted(self.success_exit_codes)
            )

            raise ActionExecutionError(
                f"Action '{self.name}' returned exit code {outcome.result.exit_code}, expected one of: {expected_exit_codes}"
            )

        # The message names only the stream, the output itself might contain secrets
        for stream, is_matched in (
            ("stdout", outcome.stdout_matched),
            ("stderr", outcome.stderr_matched),
        ):
            if not is_matched:
                raise ActionExecutionError(
                    f"Action '{self.name}' produced an unexpected output on {stream}"
                )

        logger.info(
            f"Action '{self.name}' finished with exit code {outcome.result.exit_code}"
        )

    def _log_output(self, result: CommandResult, failed: bool) -> None:
        """Log the output of the command.

        Args:
            result: Result of the command.
            failed: Whether the command failed. The error output of a failed command is logged as an error,
                otherwise on debug level, because many programs write their progress to it.
        """
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if stdout:
            logger.debug(f"Output of action '{self.name}' (stdout):\n{stdout}")

        if stderr:
            logger.log(
                logging.ERROR if failed else logging.DEBUG,
                f"Output of action '{self.name}' (stderr):\n{stderr}",
            )
