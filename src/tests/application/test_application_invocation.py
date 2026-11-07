import shlex
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from powerrules.application.invocation import (
    build_trust_command,
    get_program_invocation,
    quote_argument,
)

MODULE = "powerrules.application.invocation"


######################
# quote_argument tests
######################


def test_quote_argument_keeps_simple_argument_on_posix() -> None:
    with patch(f"{MODULE}.sys.platform", "linux"):
        assert quote_argument("simple") == "simple"


def test_quote_argument_quotes_special_characters_on_posix() -> None:
    with patch(f"{MODULE}.sys.platform", "linux"):
        assert quote_argument("my policy; rm -rf") == "'my policy; rm -rf'"


def test_quote_argument_quotes_spaces_on_windows() -> None:
    with patch(f"{MODULE}.sys.platform", "win32"):
        assert quote_argument("my policy.yaml") == subprocess.list2cmdline(
            ["my policy.yaml"]
        )
        assert quote_argument("my policy.yaml") == '"my policy.yaml"'


def test_quote_argument_keeps_simple_argument_on_windows() -> None:
    with patch(f"{MODULE}.sys.platform", "win32"):
        assert quote_argument("policy.yaml") == "policy.yaml"


##############################
# get_program_invocation tests
##############################


def test_program_invocation_of_module_run_uses_python() -> None:
    with patch.object(sys, "argv", ["/package/powerrules/__main__.py"]):
        assert get_program_invocation() == (
            f"{quote_argument(Path(sys.executable).name)} -m powerrules"
        )


@pytest.mark.parametrize("program", ["", "-c"])
def test_program_invocation_falls_back_without_usable_program_name(
    program: str,
) -> None:
    with patch.object(sys, "argv", [program]):
        assert get_program_invocation() == "pwru"


def test_program_invocation_uses_name_found_in_path(tmp_path: Path) -> None:
    program = tmp_path / "pwru"
    program.write_text("", encoding="utf-8")

    with (
        patch.object(sys, "argv", [str(program)]),
        patch(f"{MODULE}.shutil.which", return_value=str(program)),
    ):
        assert get_program_invocation() == "pwru"


def test_program_invocation_uses_full_path_if_program_is_not_in_path(
    tmp_path: Path,
) -> None:
    program = tmp_path / "powerrules-linux-x86_64"
    program.write_text("", encoding="utf-8")

    with (
        patch.object(sys, "argv", [str(program)]),
        patch(f"{MODULE}.shutil.which", return_value=None),
    ):
        assert get_program_invocation() == quote_argument(str(program.resolve()))


def test_program_invocation_uses_full_path_if_another_program_is_found_first(
    tmp_path: Path,
) -> None:
    program = tmp_path / "bin" / "pwru"
    other = tmp_path / "other" / "pwru"

    for file in (program, other):
        file.parent.mkdir()
        file.write_text("", encoding="utf-8")

    with (
        patch.object(sys, "argv", [str(program)]),
        patch(f"{MODULE}.shutil.which", return_value=str(other)),
    ):
        assert get_program_invocation() == quote_argument(str(program.resolve()))


###########################
# build_trust_command tests
###########################


def test_build_trust_command_contains_program_and_quoted_policy() -> None:
    policy = Path("my policies") / "powerrules.yaml"

    with (
        patch(f"{MODULE}.get_program_invocation", return_value="pwru"),
        patch(f"{MODULE}.sys.platform", "linux"),
    ):
        assert build_trust_command(policy) == (
            f"pwru trust add --policy {shlex.quote(str(policy))}"
        )
