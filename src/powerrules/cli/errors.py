import logging
from collections.abc import Callable
from functools import wraps
from typing import Any, NoReturn, TypeVar

import typer
import yaml
from pydantic import ValidationError

from powerrules.engine.exceptions import (
    ActionExecutionError,
    ConditionEvaluationError,
)

logger = logging.getLogger(__name__)

EXIT_RUNTIME_ERROR = 1
EXIT_POLICY_ERROR = 2

ReturnType = TypeVar("ReturnType")


def handle_cli_error(error: Exception) -> NoReturn:
    """Handle a command execution error.

    Args:
        error: Exception raised during command execution.

    Raises:
        typer.Exit: Always raised after logging the error.
    """
    # The policy file type is currently the only type being used in CLI commands
    if isinstance(error, FileNotFoundError):
        logger.error(f"Policy file not found: {error.filename}")
        raise typer.Exit(code=EXIT_POLICY_ERROR)

    if isinstance(error, yaml.YAMLError):
        logger.error("Failed to parse policy file")
        raise typer.Exit(code=EXIT_POLICY_ERROR)

    if isinstance(error, ValidationError):
        logger.error("Policy validation failed")

        # Output the cryptic Pydantic errors anyway. This should be reworked in the future for a nicer output
        for validation_error in error.errors():
            location = ".".join(str(item) for item in validation_error["loc"])
            message = validation_error["msg"]

            logger.error(f"{location}: {message}")

        raise typer.Exit(code=EXIT_POLICY_ERROR)

    # The existing error messages for conditions and actions
    if isinstance(error, ConditionEvaluationError):
        logger.error(f"Failed to evaluate condition: {error}")
        raise typer.Exit(code=EXIT_RUNTIME_ERROR)

    if isinstance(error, ActionExecutionError):
        logger.error(f"Failed to execute action: {error}")
        raise typer.Exit(code=EXIT_RUNTIME_ERROR)

    if isinstance(error, ValueError):
        logger.error(str(error))
        raise typer.Exit(code=EXIT_RUNTIME_ERROR)

    # Include a stack trace here since this is an unexpected, unclassified error
    logger.error(f"Unexpected error: {error}", exc_info=True)  # noqa: LOG014
    raise typer.Exit(code=EXIT_RUNTIME_ERROR)


def cli_command(
    function: Callable[..., ReturnType],
) -> Callable[..., ReturnType]:
    """Wrap a CLI command with centralized error handling.

    Args:
        function: CLI command function.

    Returns:
        Wrapped CLI command function.
    """

    @wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> ReturnType:
        try:
            return function(*args, **kwargs)
        except typer.Exit:
            raise
        except Exception as e:  # noqa: BLE001 (blind catch is intentional)
            # Handle errors which result from CLI commands. This avoids tracebacks and instead shows a readable error message
            handle_cli_error(e)

    return wrapper
