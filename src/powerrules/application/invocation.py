import shlex
import shutil
import subprocess
import sys
from pathlib import Path

_FALLBACK_PROGRAM = "pwru"


def quote_argument(argument: str) -> str:
    """Quote an argument for the shell of the current platform.

    Args:
        argument: Argument which may contain spaces or special characters.

    Returns:
        The argument, quoted only if necessary.
    """
    if sys.platform == "win32":
        return subprocess.list2cmdline([argument])

    return shlex.quote(argument)


def get_program_invocation() -> str:
    """Return the command with which the user started PowerRules.

    This is the file name if it can be found in the PATH (e.g. "pwru" or "powerrules"),
    "python -m powerrules" for module runs, otherwise the full path (e.g. a standalone binary in the current directory).

    Returns:
        The command which starts PowerRules.
    """
    program = Path(sys.argv[0])

    if program.name == "__main__.py":
        return f"{quote_argument(Path(sys.executable).name)} -m powerrules"

    # Embedded interpreters or "python -c" do not provide a usable program name
    if program.name in ("", "-c"):
        return _FALLBACK_PROGRAM

    found = shutil.which(program.name)

    # Only use the short name if it really starts this program and not another one earlier in the PATH
    if found is not None and Path(found).resolve().parent == program.resolve().parent:
        return quote_argument(program.name)

    return quote_argument(str(program.resolve()))


def build_trust_command(policy_path: Path) -> str:
    """Build the command which trusts a specific policy.

    Args:
        policy_path: Path of the policy file.

    Returns:
        The command, ready to be pasted into a terminal.
    """
    return f"{get_program_invocation()} trust add --policy {quote_argument(str(policy_path))}"
