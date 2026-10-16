import logging
from collections.abc import Callable, Collection, Mapping, Sequence
from pathlib import Path

from powerrules.engine.exceptions import ActionExecutionError
from powerrules.providers.command import (
    CommandProvider,
    CommandRequest,
    CommandResult,
    Shell,
)

logger = logging.getLogger(__name__)

# Verifies the given trusted files right before a command runs and raises an error if they must not be used
FilesVerifier = Callable[[Sequence[Path]], None]

# Time in seconds a command may run before it is terminated
DEFAULT_ACTION_TIMEOUT_SECONDS = 60

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
        timeout: float | None = DEFAULT_ACTION_TIMEOUT_SECONDS,
        success_exit_codes: Collection[int] = (0,),
        wait: bool = True,
        continue_on_error: bool = False,
        trusted_files: Sequence[Path] = (),
        files_verifier: FilesVerifier | None = None,
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
            wait: Whether to wait for the command to finish. If False, the timeout and the exit codes are ignored.
            continue_on_error: Whether a failure is only logged instead of raised.
            trusted_files: Absolute paths of the files the command depends on, they are verified before every run.
            files_verifier: Called with the trusted files before every run, it raises an error if they must not be used.
                None skips the verification.
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

    def execute(self) -> None:
        """Run the command.

        The trusted files are verified first. If the action is configured with "continue_on_error",
        a failure of the command is only logged as a warning.

        Raises:
            FileIntegrityError: If trust is required and a trusted file cannot be read, is not trusted yet or was modified.
            ActionExecutionError: If the command cannot be started, exceeds the timeout
                or finishes with an exit code which does not count as success.
        """
        # Outside of the try block on purpose: "continue_on_error" must never skip a failed integrity check
        if self.files_verifier is not None and self.trusted_files:
            self.files_verifier(self.trusted_files)

        logger.info(f"Running action '{self.name}'")
        # The command is only logged on debug level, because it might contain secrets
        logger.debug(f"Command of action '{self.name}': {self.command.strip()}")

        try:
            self._run_command()
        except ActionExecutionError as e:
            if not self.continue_on_error:
                raise

            logger.warning(
                f"{e} (continue_on_error is set, continuing with the remaining actions)"
            )

    def _run_command(self) -> None:
        """Run the command and check its result.

        Raises:
            ActionExecutionError: If the command cannot be started, exceeds the timeout
                or finishes with an exit code which does not count as success.
        """
        request = CommandRequest(
            command=self.command,
            working_directory=self.working_directory,
            # The variables of PowerRules come last, the configuration cannot define them
            environment={
                **self.environment,
                RULE_NAME_ENVIRONMENT_VARIABLE: self.rule_name,
                ACTION_NAME_ENVIRONMENT_VARIABLE: self.name,
            },
            timeout=self.timeout,
            wait=self.wait,
            shell=self.shell,
        )

        # TimeoutError is a subclass of OSError, so it has to be handled first
        try:
            result = self.command_provider.run(request)
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

        succeeded = result.exit_code in self.success_exit_codes
        self._log_output(result, failed=not succeeded)

        if not succeeded:
            expected_exit_codes = ", ".join(
                str(exit_code) for exit_code in sorted(self.success_exit_codes)
            )

            raise ActionExecutionError(
                f"Action '{self.name}' returned exit code {result.exit_code}, expected one of: {expected_exit_codes}"
            )

        logger.info(f"Action '{self.name}' finished with exit code {result.exit_code}")

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
