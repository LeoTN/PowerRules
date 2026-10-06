import ctypes
import logging
from collections.abc import Iterator
from typing import Any
from unittest.mock import Mock, patch

import pytest

from powerrules.platform.windows.window import (
    _DWMWA_CLOAKED,
    _WSF_VISIBLE,
    WindowsWindowProvider,
)


@pytest.fixture
def user32() -> Mock:
    return Mock()


@pytest.fixture
def dwmapi() -> Mock:
    return Mock()


@pytest.fixture
def provider(user32: Mock, dwmapi: Mock) -> WindowsWindowProvider:
    provider = WindowsWindowProvider()
    # cached_property stores its value in the instance dictionary, so this avoids loading the real DLLs
    provider.__dict__["_user32"] = user32
    provider.__dict__["_dwmapi"] = dwmapi

    return provider


@pytest.fixture
def win32_ctypes() -> Iterator[None]:
    """Provide the Windows-only parts of ctypes, so the tests also run on other platforms."""
    with (
        # The callback type is replaced by a decorator which returns the Python function itself
        patch.object(
            ctypes,
            "WINFUNCTYPE",
            create=True,
            new=lambda *_args: lambda function: function,
        ),
        patch.object(ctypes, "get_last_error", create=True, return_value=5),
        patch.object(
            ctypes,
            "WinError",
            create=True,
            return_value=OSError("Test enumeration failure"),
        ),
    ):
        yield


def _set_window_station_flags(user32: Mock, flags: int | None) -> None:
    """Simulate the flags of the window station. None simulates a failing query."""

    def get_information(
        _station: object,
        _index: int,
        flags_reference: Any,  # result of ctypes.byref(), its type is private
        _size: int,
        _needed_length: object,
    ) -> int:
        if flags is None:
            return 0

        # "_obj" is the structure which was wrapped by ctypes.byref()
        flags_reference._obj.dwFlags = flags

        return 1

    user32.GetUserObjectInformationW.side_effect = get_information


####################
# is_available tests
####################


def test_windows_window_provider_is_available_on_interactive_session(
    provider: WindowsWindowProvider,
    user32: Mock,
) -> None:
    _set_window_station_flags(user32, _WSF_VISIBLE)

    assert provider.is_available is True


def test_windows_window_provider_is_not_available_on_non_interactive_session(
    provider: WindowsWindowProvider,
    user32: Mock,
) -> None:
    _set_window_station_flags(user32, 0)

    assert provider.is_available is False


def test_windows_window_provider_is_not_available_when_window_station_query_fails(
    provider: WindowsWindowProvider,
    user32: Mock,
) -> None:
    _set_window_station_flags(user32, None)

    assert provider.is_available is False


def test_windows_window_provider_logs_unavailable_warning_only_once(
    provider: WindowsWindowProvider,
    user32: Mock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _set_window_station_flags(user32, 0)

    with caplog.at_level(logging.WARNING):
        assert provider.is_available is False
        assert provider.is_available is False

    assert len(caplog.records) == 1
    assert "interactive desktop" in caplog.text


#########################
# get_window_titles tests
#########################


@pytest.mark.usefixtures("win32_ctypes")
def test_windows_window_provider_skips_invisible_cloaked_and_untitled_windows(
    provider: WindowsWindowProvider,
    user32: Mock,
) -> None:
    handles = [1, 2, 3, 4, 5]
    titles = {1: "First window", 3: "Cloaked window", 4: "", 5: "Fifth window"}

    def enumerate_windows(callback, _parameter: int) -> int:
        for handle in handles:
            callback(handle, 0)

        return 1

    # Window 2 is invisible, window 3 is cloaked and window 4 has no title
    user32.IsWindowVisible.side_effect = lambda handle: handle != 2
    user32.EnumWindows.side_effect = enumerate_windows

    with (
        patch.object(provider, "_is_cloaked", side_effect=lambda handle: handle == 3),
        patch.object(provider, "_get_title", side_effect=lambda handle: titles[handle]),
    ):
        assert provider.get_window_titles() == ("First window", "Fifth window")


@pytest.mark.usefixtures("win32_ctypes")
def test_windows_window_provider_returns_empty_tuple_without_windows(
    provider: WindowsWindowProvider,
    user32: Mock,
) -> None:
    user32.EnumWindows.return_value = 1

    assert provider.get_window_titles() == ()


@pytest.mark.usefixtures("win32_ctypes")
def test_windows_window_provider_raises_when_enumeration_fails(
    provider: WindowsWindowProvider,
    user32: Mock,
) -> None:
    user32.EnumWindows.return_value = 0

    with pytest.raises(OSError, match="Test enumeration failure"):
        provider.get_window_titles()


###################
# _is_cloaked tests
###################


@pytest.mark.parametrize(
    ("hresult", "cloaked_value", "expected"),
    [
        # Cloaked window
        (0, 1, True),
        # Regular window
        (0, 0, False),
        # A failed call is treated as "not cloaked"
        (1, 1, False),
    ],
)
def test_windows_window_provider_detects_cloaked_windows(
    provider: WindowsWindowProvider,
    dwmapi: Mock,
    hresult: int,
    cloaked_value: int,
    expected: bool,
) -> None:
    def get_attribute(
        _handle: int,
        attribute: int,
        reference: Any,  # result of ctypes.byref(), its type is private
        _size: int,
    ) -> int:
        assert attribute == _DWMWA_CLOAKED

        reference._obj.value = cloaked_value

        return hresult

    dwmapi.DwmGetWindowAttribute.side_effect = get_attribute

    assert provider._is_cloaked(1) is expected


##################
# _get_title tests
##################


def test_windows_window_provider_reads_window_title(
    provider: WindowsWindowProvider,
    user32: Mock,
) -> None:
    def get_text(_handle: int, buffer: ctypes.Array, _size: int) -> int:
        buffer.value = "Test window title"  # type: ignore

        return len("Test window title")

    user32.GetWindowTextLengthW.return_value = len("Test window title")
    user32.GetWindowTextW.side_effect = get_text

    assert provider._get_title(1) == "Test window title"


def test_windows_window_provider_returns_empty_title_without_reading_text(
    provider: WindowsWindowProvider,
    user32: Mock,
) -> None:
    user32.GetWindowTextLengthW.return_value = 0

    assert provider._get_title(1) == ""
    user32.GetWindowTextW.assert_not_called()
