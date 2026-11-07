"""Central logging configuration for PowerRules."""

import logging
from collections.abc import Mapping
from enum import StrEnum
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import MappingProxyType
from typing import Final

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

# Shared Rich consoles, used both by the logging handlers below and for direct command output (e.g. "--version", "policy show").
# "file" is intentionally left unset so each console resolves the current sys.stdout/sys.stderr dynamically on every write
# instead of binding to a fixed stream captured at import/construction time
console = Console(width=200)
error_console = Console(stderr=True, width=200)

# Log records with this extra attribute are only written to the log file, not to the console
_FILE_ONLY_ATTRIBUTE = "file_only"
FILE_ONLY_EXTRA: Final[Mapping[str, object]] = MappingProxyType(
    {_FILE_ONLY_ATTRIBUTE: True}
)


def _is_below_warning(record: logging.LogRecord) -> bool:
    """Return whether a log record belongs to stdout, since "WARNING" and above are written to stderr."""
    return record.levelno < logging.WARNING


def _is_shown_on_console(record: logging.LogRecord) -> bool:
    """Return whether a log record is meant for the console (and not only for the log file)."""
    return not getattr(record, _FILE_ONLY_ATTRIBUTE, False)


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
        console=console,
        level=console_level_number,
        show_time=False,
        show_path=False,
        markup=False,
        rich_tracebacks=True,
    )
    # A handler level is only a lower limit, so the upper limit is a filter (otherwise warnings would appear on stdout and stderr)
    handler.addFilter(_is_below_warning)
    handler.addFilter(_is_shown_on_console)

    return handler


def _build_stderr_handler(console_level_number: int) -> logging.Handler:
    """Build the rich-formatted handler which writes "WARNING" and above to stderr."""
    handler = RichHandler(
        console=error_console,
        level=max(console_level_number, logging.WARNING),
        show_time=False,
        show_path=False,
        markup=False,
        rich_tracebacks=True,
    )
    handler.addFilter(_is_shown_on_console)

    return handler


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
