import platform
from subprocess import CalledProcessError
from unittest.mock import Mock, patch

import pytest

from powerrules.platform.windows.power import WindowsPowerProvider

windows_only = pytest.mark.skipif(
    platform.system() != "Windows",
    reason="Requires the Windows API (ctypes.windll)",
)


def test_windows_power_provider_shutdown() -> None:
    with patch("powerrules.platform.windows.power.subprocess.run") as mock_run:
        provider = WindowsPowerProvider()

        provider.shutdown()

        mock_run.assert_called_once_with(
            ["shutdown.exe", "/s", "/t", "0"],
            check=True,
        )


def test_windows_power_provider_reboot() -> None:
    with patch("powerrules.platform.windows.power.subprocess.run") as mock_run:
        provider = WindowsPowerProvider()

        provider.reboot()

        mock_run.assert_called_once_with(
            ["shutdown.exe", "/r", "/t", "0"],
            check=True,
        )


@windows_only
def test_windows_power_provider_sleep() -> None:
    mock_suspend_state = Mock(return_value=1)

    with patch(
        "powerrules.platform.windows.power.ctypes.windll.powrprof.SetSuspendState",
        mock_suspend_state,
    ):
        provider = WindowsPowerProvider()

        provider.sleep()

        mock_suspend_state.assert_called_once_with(
            False,
            False,
            False,
        )


@windows_only
def test_windows_power_provider_hibernate() -> None:
    mock_suspend_state = Mock(return_value=1)

    with patch(
        "powerrules.platform.windows.power.ctypes.windll.powrprof.SetSuspendState",
        mock_suspend_state,
    ):
        provider = WindowsPowerProvider()

        provider.hibernate()

        mock_suspend_state.assert_called_once_with(
            True,
            False,
            False,
        )


@windows_only
def test_windows_power_provider_raises_when_suspend_state_fails() -> None:
    mock_suspend_state = Mock(return_value=0)

    with patch(
        "powerrules.platform.windows.power.ctypes.windll.powrprof.SetSuspendState",
        mock_suspend_state,
    ):
        provider = WindowsPowerProvider()

        with pytest.raises(
            OSError,
            match="Failed to change the Windows power state",
        ):
            provider.sleep()


def test_windows_power_provider_propagates_shutdown_error() -> None:
    original_error = CalledProcessError(
        returncode=1,
        cmd=["shutdown.exe", "/s", "/t", "0"],
    )

    with patch(
        "powerrules.platform.windows.power.subprocess.run",
        side_effect=original_error,
    ):
        provider = WindowsPowerProvider()

        with pytest.raises(CalledProcessError) as exc_info:
            provider.shutdown()

        assert exc_info.value is original_error


def test_windows_power_provider_propagates_reboot_error() -> None:
    original_error = CalledProcessError(
        returncode=1,
        cmd=["shutdown.exe", "/r", "/t", "0"],
    )

    with patch(
        "powerrules.platform.windows.power.subprocess.run",
        side_effect=original_error,
    ):
        provider = WindowsPowerProvider()

        with pytest.raises(CalledProcessError) as exc_info:
            provider.reboot()

        assert exc_info.value is original_error
