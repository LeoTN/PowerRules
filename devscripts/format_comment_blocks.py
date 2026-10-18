"""Align the hash borders around three-line Python comment headings.

A heading consists of a comment line between two borders of hash characters. Both borders get the width of the comment line
(without its indentation), for example:

    #########
    # Heading
    #########

Without "--fix", the files are only checked and the exit code is 1 if a file needs changes (like "ruff check").

Usage:
    poetry run python devscripts/format_comment_blocks.py [--fix] [PATH ...]
"""

import argparse
import io
import os
import re
import stat
import sys
import tempfile
import tokenize
from collections.abc import Iterator, Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXCLUDED_DIRECTORIES = frozenset(
    {
        ".git",
        ".hg",
        ".mypy_cache",
        ".nox",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        ".vscode",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "venv",
    }
)

EXIT_CHANGES_NEEDED = 1
EXIT_ERROR = 2

# A heading consists of an upper border, the heading itself and a lower border
HEADING_LINE_COUNT = 3
# Shorter comments (e.g. "#" or "##") are not treated as borders
MIN_BORDER_LENGTH = 3
BORDER_PATTERN = re.compile(r"(?P<indent>[ \t]*)(?P<hashes>#+)[ \t]*")
HEADING_PATTERN = re.compile(r"(?P<indent>[ \t]*)#[ \t]+\S.*")


def _split_line_ending(line: str) -> tuple[str, str]:
    """Split a line into its content and its original line ending."""
    content = line.rstrip("\r\n")

    return content, line[len(content) :]


def _split_lines(source: str) -> list[str]:
    """Split a source into lines which keep their original line endings.

    Only "\\n", "\\r\\n" and "\\r" end a line, like in the Python tokenizer. "str.splitlines()" also splits at form feeds
    or Unicode separators, which would shift the line numbers of the tokens.
    """
    return io.StringIO(source, newline="").readlines()


def _find_comment_lines(source: str) -> frozenset[int]:
    """Find all lines which contain a comment.

    A hash character within a string is no comment, so the source is tokenized instead of searched for hashes.

    Args:
        source: Python source code.

    Returns:
        The numbers of the lines with a comment (the first line is 1).

    Raises:
        ValueError: If the source cannot be tokenized.
    """
    try:
        # Universal newlines, so the line numbers match the lines of "_split_lines()"
        tokens = list(
            tokenize.generate_tokens(io.StringIO(source, newline=None).readline)
        )
    except (SyntaxError, tokenize.TokenError) as e:
        raise ValueError(f"Python source could not be tokenized: {e}") from e

    return frozenset(
        token.start[0] for token in tokens if token.type == tokenize.COMMENT
    )


def _get_heading_border(
    lines: Sequence[str],
    index: int,
    comment_lines: frozenset[int],
) -> str | None:
    """Return the border which fits to the heading that starts at a line.

    Args:
        lines: All lines of the source including their line endings.
        index: Index of the line which would be the upper border.
        comment_lines: Numbers of all lines which contain a comment.

    Returns:
        The border without a line ending, or None if the lines are no heading.
    """
    # The line numbers start with 1
    if not all(
        number in comment_lines
        for number in range(index + 1, index + 1 + HEADING_LINE_COUNT)
    ):
        return None

    top_line, heading_line, bottom_line = (
        _split_line_ending(line)[0]
        for line in lines[index : index + HEADING_LINE_COUNT]
    )
    top = BORDER_PATTERN.fullmatch(top_line)
    heading = HEADING_PATTERN.fullmatch(heading_line)
    bottom = BORDER_PATTERN.fullmatch(bottom_line)

    if top is None or heading is None or bottom is None:
        return None

    indent = heading["indent"]

    if top["indent"] != indent or bottom["indent"] != indent:
        return None

    if min(len(top["hashes"]), len(bottom["hashes"])) < MIN_BORDER_LENGTH:
        return None

    # The indentation and trailing whitespace do not count
    heading_width = len(heading_line.removeprefix(indent).rstrip(" \t"))

    return indent + "#" * heading_width


def format_source(source: str) -> str:
    """Align the borders of all comment headings of a Python source.

    The width of a border is the number of characters of the heading (without indentation), not its width on the screen.
    Headings which share a border line are not supported, only the first one is aligned.

    Args:
        source: Python source code.

    Returns:
        The source with aligned borders, which is the unchanged source if nothing has to be aligned.

    Raises:
        ValueError: If the source cannot be tokenized.
    """
    comment_lines = _find_comment_lines(source)
    lines = _split_lines(source)
    index = 0

    while index <= len(lines) - HEADING_LINE_COUNT:
        border = _get_heading_border(lines, index, comment_lines)

        if border is None:
            index += 1
            continue

        for border_index in (index, index + HEADING_LINE_COUNT - 1):
            lines[border_index] = border + _split_line_ending(lines[border_index])[1]

        # Skip the heading, so its lower border is not the upper border of the next one
        index += HEADING_LINE_COUNT

    return "".join(lines)


def _is_python_file(path: Path) -> bool:
    """Return whether a path is a regular Python file.

    Symbolic links are skipped, because replacing them would turn them into regular files.
    """
    return path.name.endswith(".py") and path.is_file() and not path.is_symlink()


def _iter_python_files(path: Path) -> Iterator[Path]:
    """Yield the Python files of a file or a directory tree.

    Excluded directories (e.g. virtual environments) and symbolic links are skipped.

    Args:
        path: File or directory.
    """
    if path.is_file():
        if _is_python_file(path):
            yield path

        return

    # "os.walk()" does not follow symbolic links to directories by default
    for directory_name, directory_names, file_names in os.walk(path):
        # Changing the list in place keeps "os.walk()" from entering the excluded directories
        directory_names[:] = sorted(
            name for name in directory_names if name not in EXCLUDED_DIRECTORIES
        )

        for file_name in sorted(file_names):
            file_path = Path(directory_name) / file_name

            if _is_python_file(file_path):
                yield file_path


def _get_display_path(path: Path) -> Path:
    """Return the path relative to the repository, or the path itself if it is outside of it."""
    try:
        return path.resolve().relative_to(REPO_ROOT)
    except ValueError:
        return path


def _write_atomically(file_path: Path, content: bytes) -> None:
    """Replace a file atomically, so an interrupted run never leaves a half-written file.

    The permission bits of the file are kept.

    Args:
        file_path: File to replace.
        content: New content of the file.

    Raises:
        OSError: If the file cannot be written or replaced.
    """
    mode = stat.S_IMODE(file_path.stat().st_mode)
    # The temporary file is created next to the file, so it can replace the file atomically (the mode of "mkstemp" is 0600)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=file_path.parent, prefix=f".{file_path.name}.", suffix=".tmp"
    )
    temporary_path = Path(temporary_name)

    try:
        with os.fdopen(descriptor, "wb") as temporary_file:
            temporary_file.write(content)

        temporary_path.chmod(mode)
        temporary_path.replace(file_path)
    finally:
        # Nothing is left to remove after a successful replace
        temporary_path.unlink(missing_ok=True)


def _process_file(file_path: Path, fix: bool) -> bool:
    """Align the comment headings of a file.

    Args:
        file_path: Python file to process.
        fix: Whether the file is rewritten. Otherwise, it is only checked.

    Returns:
        True if the file needs changes (or was changed), otherwise False.

    Raises:
        OSError: If the file cannot be read or written.
        SyntaxError: If the encoding declaration of the file is invalid.
        ValueError: If the file cannot be decoded or tokenized.
    """
    content = file_path.read_bytes()
    encoding, _ = tokenize.detect_encoding(io.BytesIO(content).readline)
    source = content.decode(encoding)
    formatted_source = format_source(source)

    if formatted_source == source:
        return False

    if fix:
        _write_atomically(file_path, formatted_source.encode(encoding))

    return True


def main(argv: list[str] | None = None) -> int:
    """Parse the arguments, check or fix the files and return the process exit code."""
    parser = argparse.ArgumentParser(
        description="Align the hash borders around three-line Python comment headings"
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=[REPO_ROOT],
        help="files or directories to process (default: the whole repository)",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="rewrite the files instead of only reporting which ones need changes",
    )
    arguments = parser.parse_args(argv)

    for path in arguments.paths:
        if not path.exists():
            print(f"[ERROR] Path does not exist: {path}")

            return EXIT_ERROR

    scanned_count = 0
    changed_count = 0
    failed_count = 0

    for path in arguments.paths:
        for file_path in _iter_python_files(path):
            scanned_count += 1
            display_path = _get_display_path(file_path)

            try:
                needs_changes = _process_file(file_path, fix=arguments.fix)
            except (OSError, SyntaxError, ValueError) as e:
                failed_count += 1
                print(f"[ERROR] Could not process {display_path}: {str(e).rstrip('.')}")
                continue

            if not needs_changes:
                continue

            changed_count += 1
            action = "Updated" if arguments.fix else "Would update"
            print(f"[INFO] {action} {display_path}")

    print(f"[INFO] Scanned {scanned_count} Python files")

    if failed_count:
        print(f"[ERROR] Failed to process {failed_count} files")

        return EXIT_ERROR

    if changed_count == 0:
        print("[INFO] No comment blocks need formatting")

        return 0

    if arguments.fix:
        print(f"[INFO] Updated {changed_count} files")

        return 0

    print(
        f"[ERROR] Comment blocks need formatting in {changed_count} files, run with --fix to apply the changes"
    )

    return EXIT_CHANGES_NEEDED


if __name__ == "__main__":
    sys.exit(main())
