"""Central logging configuration for PowerRules."""

import logging
import sys
from enum import StrEnum
from logging.handlers import RotatingFileHandler
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler

# Name of the top-level package logger. Module loggers created via
# "logging.getLogger(__name__)" are children of this logger and propagate into it
_LOGGER_NAME = "powerrules"

# Rotate the log file once it reaches this size, keeping this many backups
_LOG_FILE_MAX_BYTES = 10 * 1000 * 1000  # 10 MB
_LOG_FILE_BACKUP_COUNT = 5

# The log file stays plain text, without rich formatting
_FILE_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


class LogLevel(StrEnum):
    """Supported logging levels, matching the names used by the "logging" module."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


def configure_logging(
    console_level: LogLevel,
    log_file: Path,
    file_level: LogLevel | None = None,
) -> None:
    """Configure PowerRules logging.

    Messages below "WARNING" are written to stdout, "WARNING" and above to stderr, both formatted and colorized via "rich".
    All messages are additionally written to a rotating log file as plain text.

    Calling this function replaces any previously configured PowerRules log handlers,
    so it is safe to call multiple times within the same process (e.g. in tests).

    Args:
        console_level: Minimum level shown on the console (stdout/stderr).
        log_file: Path to the rotating log file. Its parent directory is created if missing.
        file_level: Minimum level written to the log file. Defaults to "console_level" if not set.
    """
    level_numbers = logging.getLevelNamesMapping()
    console_level_number = level_numbers[console_level]
    # Defaults to console_level if file_level is not set
    file_level_number = level_numbers[
        file_level if file_level is not None else console_level
    ]

    logger = logging.getLogger(_LOGGER_NAME)
    logger.handlers.clear()
    logger.setLevel(min(console_level_number, file_level_number))

    logger.addHandler(_build_stdout_handler(console_level_number))
    logger.addHandler(_build_stderr_handler(console_level_number))
    logger.addHandler(_build_file_handler(log_file, file_level_number))


def _build_stdout_handler(console_level_number: int) -> logging.Handler:
    """Build the rich-formatted handler which writes messages below "WARNING" to stdout."""
    handler = RichHandler(
        console=Console(file=sys.stdout, width=200),
        level=console_level_number,
        show_time=False,
        show_path=False,
        markup=False,
        rich_tracebacks=True,
    )
    handler.addFilter(lambda record: record.levelno < logging.WARNING)

    return handler


def _build_stderr_handler(console_level_number: int) -> logging.Handler:
    """Build the rich-formatted handler which writes "WARNING" and above to stderr."""
    return RichHandler(
        console=Console(file=sys.stderr, width=200),
        level=max(console_level_number, logging.WARNING),
        show_time=False,
        show_path=False,
        markup=False,
        rich_tracebacks=True,
    )


def _build_file_handler(log_file: Path, file_level_number: int) -> logging.Handler:
    """Build the rotating file handler."""
    log_file.parent.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(
        log_file,
        maxBytes=_LOG_FILE_MAX_BYTES,
        backupCount=_LOG_FILE_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setLevel(file_level_number)
    handler.setFormatter(logging.Formatter(_FILE_FORMAT))

    return handler
