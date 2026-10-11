import ctypes
import os
import shutil
import subprocess
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path
from unittest.mock import Mock, patch

import psutil
import pytest

from powerrules.platform.command import (
    SubprocessCommandProvider,
    _decode_output,
    _get_output_encoding,
    _terminate_process_tree,
    build_shell_arguments,
)
from powerrules.providers.command import CommandRequest, CommandResult, Shell

MODULE = "powerrules.platform.command"

posix_only = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("sh") is None,
    reason="Requires a POSIX shell",
)
windows_only = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Requires Windows",
)


@pytest.fixture
def popen() -> Iterator[Mock]:
    """Replace "subprocess.Popen" and report every shell as installed."""
    with (
        patch(f"{MODULE}.subprocess.Popen") as mock_popen,
        patch(f"{MODULE}.shutil.which", return_value="/usr/bin/shell"),
    ):
        process = mock_popen.return_value.__enter__.return_value
        process.communicate.return_value = (b"", b"")
        process.returncode = 0

        yield mock_popen


@pytest.fixture
def process(popen: Mock) -> Mock:
    """The process which is waited for in a "with" block."""
    return popen.return_value.__enter__.return_value


@pytest.fixture
def clear_encoding_cache() -> Iterator[None]:
    _get_output_encoding.cache_clear()
    yield
    _get_output_encoding.cache_clear()


def _make_request(
    working_directory: Path,
    command: str = "echo test",
    *,
    environment: Mapping[str, str] | None = None,
    timeout: float | None = None,
    wait: bool = True,
    shell: Shell | None = None,
) -> CommandRequest:
    """Create a request with the given options."""
    return CommandRequest(
        command=command,
        working_directory=working_directory,
        environment=environment if environment is not None else {},
        timeout=timeout,
        wait=wait,
        shell=shell,
    )


#############################
# build_shell_arguments tests
#############################


def test_build_shell_arguments_for_sh() -> None:
    assert build_shell_arguments(Shell.SH, "echo test") == [
        "sh",
        "-e",
        "-c",
        "echo test",
    ]


def test_build_shell_arguments_for_bash() -> None:
    assert build_shell_arguments(Shell.BASH, "echo test") == [
        "bash",
        "--noprofile",
        "--norc",
        "-eo",
        "pipefail",
        "-c",
        "echo test",
    ]


# "cmd" gets a single string, because a list would escape its quotes with backslashes
def test_build_shell_arguments_for_cmd_keeps_inner_quotes() -> None:
    assert build_shell_arguments(Shell.CMD, 'echo "a b"') == (
        'cmd.exe /d /s /c "echo "a b""'
    )


@pytest.mark.parametrize("shell", [Shell.POWERSHELL, Shell.PWSH])
@pytest.mark.parametrize(
    ("platform_name", "expects_execution_policy"),
    [
        ("win32", True),
        ("linux", False),
        ("darwin", False),
    ],
)
def test_build_shell_arguments_for_powershell(
    shell: Shell,
    platform_name: str,
    expects_execution_policy: bool,
) -> None:
    with patch(f"{MODULE}.sys.platform", platform_name):
        arguments = build_shell_arguments(shell, "echo test # comment")

    expected_prefix = [
        shell.value,
        "-NoProfile",
        "-NonInteractive",
        *(["-ExecutionPolicy", "Bypass"] if expects_execution_policy else []),
        "-Command",
    ]

    assert isinstance(arguments, list)
    assert arguments[:-1] == expected_prefix

    # The command is on its own line, so a comment cannot swallow the exit code suffix
    script_lines = arguments[-1].split("\n")
    assert len(script_lines) == 3
    assert script_lines[0] == "$ErrorActionPreference = 'Stop'"
    assert script_lines[1] == "echo test # comment"
    assert script_lines[2].startswith("if ((Test-Path")
    assert script_lines[2].endswith("exit $LASTEXITCODE }")


#######################
# Output decoding tests
#######################


@pytest.mark.usefixtures("clear_encoding_cache")
def test_get_output_encoding_uses_utf8_outside_of_windows() -> None:
    with patch(f"{MODULE}.sys.platform", "linux"):
        assert _get_output_encoding() == "utf-8"


@pytest.mark.usefixtures("clear_encoding_cache")
def test_get_output_encoding_uses_oem_code_page_on_windows() -> None:
    with (
        patch(f"{MODULE}.sys.platform", "win32"),
        patch.object(ctypes, "windll", create=True) as windll,
    ):
        windll.kernel32.GetOEMCP.return_value = 850

        assert _get_output_encoding() == "cp850"


def test_decode_output_uses_output_encoding() -> None:
    with patch(f"{MODULE}._get_output_encoding", return_value="cp850"):
        assert _decode_output(b"\x84") == "ä"


def test_decode_output_replaces_invalid_bytes() -> None:
    with patch(f"{MODULE}._get_output_encoding", return_value="utf-8"):
        assert _decode_output(b"test \xff") == "test \ufffd"


###############################
# _terminate_process_tree tests
###############################


def test_terminate_process_tree_kills_children_before_process() -> None:
    killed: list[str] = []
    first_child = Mock(kill=Mock(side_effect=lambda: killed.append("first child")))
    second_child = Mock(kill=Mock(side_effect=lambda: killed.append("second child")))
    process = Mock(pid=42, kill=Mock(side_effect=lambda: killed.append("process")))

    with patch(f"{MODULE}.psutil.Process") as process_class:
        process_class.return_value.children.return_value = [first_child, second_child]

        _terminate_process_tree(process)

    process_class.assert_called_once_with(42)
    process_class.return_value.children.assert_called_once_with(recursive=True)
    assert killed == ["first child", "second child", "process"]


def test_terminate_process_tree_kills_process_which_psutil_cannot_find() -> None:
    process = Mock(pid=42)

    with patch(f"{MODULE}.psutil.Process", side_effect=psutil.NoSuchProcess(42)):
        _terminate_process_tree(process)

    process.kill.assert_called_once_with()


@pytest.mark.parametrize("error", [psutil.NoSuchProcess(1), psutil.AccessDenied(1)])
def test_terminate_process_tree_skips_children_which_cannot_be_killed(
    error: psutil.Error,
) -> None:
    unkillable_child = Mock(kill=Mock(side_effect=error))
    other_child = Mock()
    process = Mock(pid=42)

    with patch(f"{MODULE}.psutil.Process") as process_class:
        process_class.return_value.children.return_value = [
            unkillable_child,
            other_child,
        ]

        _terminate_process_tree(process)

    other_child.kill.assert_called_once_with()
    process.kill.assert_called_once_with()


#################################
# SubprocessCommandProvider tests
#################################


def test_provider_runs_command_and_returns_result(
    popen: Mock,
    process: Mock,
    tmp_path: Path,
) -> None:
    process.communicate.return_value = (b"out", b"err")
    process.returncode = 3

    result = SubprocessCommandProvider(Shell.SH).run(_make_request(tmp_path, timeout=7))

    assert result == CommandResult(exit_code=3, stdout="out", stderr="err")
    process.communicate.assert_called_once_with(timeout=7)

    arguments = popen.call_args.args[0]
    kwargs = popen.call_args.kwargs
    assert arguments == ["sh", "-e", "-c", "echo test"]
    assert kwargs["cwd"] == tmp_path
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["stdout"] is subprocess.PIPE
    assert kwargs["stderr"] is subprocess.PIPE


def test_provider_passes_string_arguments_of_cmd_unchanged(
    popen: Mock,
    tmp_path: Path,
) -> None:
    SubprocessCommandProvider(Shell.SH).run(
        _make_request(tmp_path, "echo test", shell=Shell.CMD)
    )

    assert popen.call_args.args[0] == 'cmd.exe /d /s /c "echo test"'


@pytest.mark.parametrize(
    ("requested_shell", "expected_executable"),
    [
        (None, "sh"),
        (Shell.BASH, "bash"),
    ],
)
def test_provider_uses_default_shell_unless_request_defines_one(
    popen: Mock,
    tmp_path: Path,
    requested_shell: Shell | None,
    expected_executable: str,
) -> None:
    SubprocessCommandProvider(Shell.SH).run(
        _make_request(tmp_path, shell=requested_shell)
    )

    assert popen.call_args.args[0][0] == expected_executable


def test_provider_extends_environment_of_current_process(
    popen: Mock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POWERRULES_TEST_INHERITED", "inherited")
    monkeypatch.setenv("POWERRULES_TEST_OVERRIDDEN", "original")

    SubprocessCommandProvider(Shell.SH).run(
        _make_request(
            tmp_path,
            environment={
                "POWERRULES_TEST_OVERRIDDEN": "override",
                "POWERRULES_TEST_ADDED": "added",
            },
        )
    )

    environment = popen.call_args.kwargs["env"]
    assert environment["POWERRULES_TEST_INHERITED"] == "inherited"
    assert environment["POWERRULES_TEST_OVERRIDDEN"] == "override"
    assert environment["POWERRULES_TEST_ADDED"] == "added"
    # The environment of the current process itself stays untouched
    assert os.environ["POWERRULES_TEST_OVERRIDDEN"] == "original"
    assert "POWERRULES_TEST_ADDED" not in os.environ


@pytest.mark.parametrize("working_directory_is_file", [False, True])
def test_provider_rejects_invalid_working_directory(
    popen: Mock,
    tmp_path: Path,
    working_directory_is_file: bool,
) -> None:
    working_directory = tmp_path / "missing"

    if working_directory_is_file:
        working_directory = tmp_path / "file.txt"
        working_directory.write_text("", encoding="utf-8")

    with pytest.raises(
        NotADirectoryError, match="does not exist or is not a directory"
    ):
        SubprocessCommandProvider(Shell.SH).run(_make_request(working_directory))

    popen.assert_not_called()


def test_provider_rejects_shell_which_is_not_installed(
    popen: Mock,
    tmp_path: Path,
) -> None:
    with (
        patch(f"{MODULE}.shutil.which", return_value=None) as which,
        pytest.raises(FileNotFoundError, match="The shell 'bash' was not found"),
    ):
        SubprocessCommandProvider(Shell.SH).run(
            _make_request(tmp_path, shell=Shell.BASH)
        )

    which.assert_called_once_with("bash")
    popen.assert_not_called()


def test_provider_propagates_start_failure(popen: Mock, tmp_path: Path) -> None:
    popen.side_effect = PermissionError("Test permission")

    with pytest.raises(PermissionError, match="Test permission"):
        SubprocessCommandProvider(Shell.SH).run(_make_request(tmp_path))


def test_provider_kills_process_tree_and_raises_on_timeout(
    process: Mock,
    tmp_path: Path,
) -> None:
    timeout_error = subprocess.TimeoutExpired(cmd="echo test", timeout=1.5)
    process.communicate.side_effect = timeout_error

    with (
        patch(f"{MODULE}._terminate_process_tree") as terminate,
        pytest.raises(
            TimeoutError, match="Command did not finish within 1.5 seconds"
        ) as exc_info,
    ):
        SubprocessCommandProvider(Shell.SH).run(_make_request(tmp_path, timeout=1.5))

    terminate.assert_called_once_with(process)
    assert exc_info.value.__cause__ is timeout_error


######################################
# SubprocessCommandProvider background
######################################


def test_provider_starts_command_in_new_session_on_posix(
    popen: Mock,
    process: Mock,
    tmp_path: Path,
) -> None:
    with patch(f"{MODULE}.sys.platform", "linux"):
        result = SubprocessCommandProvider(Shell.SH).run(
            _make_request(tmp_path, wait=False)
        )

    assert result == CommandResult(exit_code=None)
    # Nothing is waited for
    popen.return_value.communicate.assert_not_called()
    process.communicate.assert_not_called()

    kwargs = popen.call_args.kwargs
    assert kwargs["cwd"] == tmp_path
    assert kwargs["start_new_session"] is True
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["stdout"] is subprocess.DEVNULL
    assert kwargs["stderr"] is subprocess.DEVNULL
    assert "creationflags" not in kwargs


def test_provider_starts_command_with_hidden_console_on_windows(
    popen: Mock,
    tmp_path: Path,
) -> None:
    no_window = 0x08000000
    new_process_group = 0x00000200

    with (
        patch(f"{MODULE}.sys.platform", "win32"),
        patch.object(subprocess, "CREATE_NO_WINDOW", no_window, create=True),
        patch.object(
            subprocess, "CREATE_NEW_PROCESS_GROUP", new_process_group, create=True
        ),
    ):
        result = SubprocessCommandProvider(Shell.SH).run(
            _make_request(tmp_path, wait=False)
        )

    assert result == CommandResult(exit_code=None)

    kwargs = popen.call_args.kwargs
    assert kwargs["creationflags"] == no_window | new_process_group
    assert kwargs["stdout"] is subprocess.DEVNULL
    assert "start_new_session" not in kwargs


def test_provider_propagates_start_failure_of_background_command(
    popen: Mock,
    tmp_path: Path,
) -> None:
    popen.side_effect = FileNotFoundError("Test shell missing")

    with pytest.raises(FileNotFoundError, match="Test shell missing"):
        SubprocessCommandProvider(Shell.SH).run(_make_request(tmp_path, wait=False))


#################################
# Tests with real child processes
#################################


@posix_only
def test_provider_runs_real_command_with_sh(tmp_path: Path) -> None:
    result = SubprocessCommandProvider(Shell.SH).run(
        _make_request(tmp_path, "echo hello; echo problem >&2; exit 3")
    )

    assert result == CommandResult(exit_code=3, stdout="hello\n", stderr="problem\n")


@posix_only
def test_provider_passes_environment_to_real_command(tmp_path: Path) -> None:
    result = SubprocessCommandProvider(Shell.SH).run(
        _make_request(
            tmp_path,
            'echo "$TEST_VARIABLE"',
            environment={"TEST_VARIABLE": "value"},
        )
    )

    assert result.stdout == "value\n"


@posix_only
def test_provider_runs_real_command_in_working_directory(tmp_path: Path) -> None:
    result = SubprocessCommandProvider(Shell.SH).run(_make_request(tmp_path, "pwd"))

    assert Path(result.stdout.strip()).resolve() == tmp_path.resolve()


# The option "-e" stops a command with several lines at the first failing line
@posix_only
def test_provider_stops_real_command_at_first_failing_line(tmp_path: Path) -> None:
    result = SubprocessCommandProvider(Shell.SH).run(
        _make_request(tmp_path, "false\necho not reached")
    )

    assert result.exit_code == 1
    assert result.stdout == ""


@posix_only
def test_provider_terminates_real_command_after_timeout(tmp_path: Path) -> None:
    with pytest.raises(TimeoutError, match="did not finish within 0.5 seconds"):
        SubprocessCommandProvider(Shell.SH).run(
            _make_request(tmp_path, "sleep 30", timeout=0.5)
        )


@windows_only
def test_provider_runs_real_command_with_cmd(tmp_path: Path) -> None:
    result = SubprocessCommandProvider(Shell.CMD).run(
        _make_request(tmp_path, "echo hello & exit /b 3")
    )

    assert result.exit_code == 3
    assert result.stdout.strip() == "hello"


@windows_only
def test_provider_runs_real_command_with_powershell(tmp_path: Path) -> None:
    result = SubprocessCommandProvider(Shell.POWERSHELL).run(
        _make_request(tmp_path, "Write-Output hello; exit 3")
    )

    assert result.exit_code == 3
    assert result.stdout.strip() == "hello"


# $ErrorActionPreference = 'Stop' aborts the command at the first error
@windows_only
def test_provider_stops_real_powershell_command_at_first_error(tmp_path: Path) -> None:
    result = SubprocessCommandProvider(Shell.POWERSHELL).run(
        _make_request(tmp_path, "Write-Error problem\nWrite-Output not-reached")
    )

    assert result.exit_code != 0
    assert "not-reached" not in result.stdout
