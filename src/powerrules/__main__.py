import sys

from powerrules.application.launch import (
    is_launched_by_double_click_on_windows,
    show_double_click_hint,
)
from powerrules.cli.app import app

if __name__ == "__main__":
    # Without arguments, a double-click would only flash the help text and close the window
    if len(sys.argv) == 1 and is_launched_by_double_click_on_windows():
        show_double_click_hint()
        sys.exit(0)

    app()
