import ctypes
import os
import platform
import sys
from ctypes import wintypes
from pathlib import Path

from rich.text import Text

from powerrules.application.logging import console


def is_launched_by_double_click_on_windows() -> bool:
    """Return whether the Windows executable was started by a double-click instead of from a terminal.

    A double-click opens a new console with only the executable attached to it.
    A Nuitka onefile executable consists of a bootstrap and a child process, so two processes are expected there.

    Returns:
        True if the executable owns its console, otherwise False.
    """
    # "__compiled__" is only defined in Nuitka builds, so development runs are never affected
    if platform.system() != "Windows" or "__compiled__" not in globals():
        return False

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetConsoleProcessList.argtypes = (wintypes.LPDWORD, wintypes.DWORD)
    kernel32.GetConsoleProcessList.restype = wintypes.DWORD

    # Only the number of attached processes is needed, not their IDs
    process_list = (wintypes.DWORD * 1)()
    attached_process_count = kernel32.GetConsoleProcessList(process_list, 1)
    expected_process_count = 2 if "NUITKA_ONEFILE_PARENT" in os.environ else 1

    return attached_process_count == expected_process_count


def show_double_click_hint() -> None:
    """Explain that PowerRules has to be started from a terminal and wait for a key press."""
    import msvcrt

    executable_name = Path(sys.argv[0]).name

    message = Text.assemble(
        "PowerRules is a command line tool and cannot be used by double-clicking it.\n\n",
        "Open a terminal (e.g. ",
        ("PowerShell", "#00A4EF"),
        "), go to the folder of this file and run:\n\n",
        (f".\\{executable_name}", "bright_yellow"),
        (" --help\n\n", "bright_black"),
        ("Press any key to close this window...", "bright_black"),
    )
    console.print(message)

    # Keeps the console window open, otherwise it closes before the hint can be read
    msvcrt.getch()
