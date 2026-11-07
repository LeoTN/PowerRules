import logging
from pathlib import Path

import pytest

from powerrules.application.logging import (
    FILE_ONLY_EXTRA,
    LogLevel,
    configure_logging,
)

logger = logging.getLogger("powerrules.test_file_only")


def test_file_only_messages_are_written_to_the_log_file_but_not_to_the_console(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    log_file = tmp_path / "test.log"
    configure_logging(LogLevel.INFO, log_file)

    logger.info("shown info")
    logger.info("hidden info", extra=FILE_ONLY_EXTRA)
    logger.warning("shown warning")
    logger.warning("hidden warning", extra=FILE_ONLY_EXTRA)

    captured = capsys.readouterr()
    log_content = log_file.read_text(encoding="utf-8")

    assert "shown info" in captured.out
    assert "shown warning" in captured.err
    assert "hidden info" not in captured.out + captured.err
    assert "hidden warning" not in captured.out + captured.err

    for message in ("shown info", "hidden info", "shown warning", "hidden warning"):
        assert message in log_content


def test_console_writes_each_message_to_exactly_one_stream(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging(LogLevel.INFO, tmp_path / "test.log")

    logger.info("an info message")
    logger.warning("a warning message")
    logger.error("an error message")

    captured = capsys.readouterr()

    assert captured.out.count("an info message") == 1
    assert "a warning message" not in captured.out
    assert "an error message" not in captured.out
    assert captured.err.count("a warning message") == 1
    assert captured.err.count("an error message") == 1
    assert "an info message" not in captured.err


def test_messages_without_marker_are_unaffected_by_the_filter(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging(LogLevel.DEBUG, tmp_path / "test.log")

    logger.debug("a debug message", extra={"unrelated": True})

    assert "a debug message" in capsys.readouterr().out
