import ctypes
import logging
from typing import Any
from unittest.mock import Mock, patch

import pytest

from powerrules.platform.macos.window import MacOSWindowProvider


@pytest.fixture
def core_foundation() -> Mock:
    return Mock()


@pytest.fixture
def core_graphics() -> Mock:
    return Mock()


@pytest.fixture
def provider(core_foundation: Mock, core_graphics: Mock) -> MacOSWindowProvider:
    provider = MacOSWindowProvider()
    # cached_property stores its value in the instance dictionary, so this avoids loading the real frameworks
    provider.__dict__["_core_foundation"] = core_foundation
    provider.__dict__["_core_graphics"] = core_graphics
    provider.__dict__["_layer_key"] = 1
    provider.__dict__["_name_key"] = 2

    return provider


####################
# is_available tests
####################


def test_macos_window_provider_is_available_with_screen_recording_permission(
    provider: MacOSWindowProvider,
    core_graphics: Mock,
) -> None:
    core_graphics.CGPreflightScreenCaptureAccess.return_value = True

    assert provider.is_available is True


def test_macos_window_provider_is_not_available_without_screen_recording_permission(
    provider: MacOSWindowProvider,
    core_graphics: Mock,
) -> None:
    core_graphics.CGPreflightScreenCaptureAccess.return_value = False

    assert provider.is_available is False


def test_macos_window_provider_logs_permission_warning_only_once(
    provider: MacOSWindowProvider,
    core_graphics: Mock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    core_graphics.CGPreflightScreenCaptureAccess.return_value = False

    with caplog.at_level(logging.WARNING):
        assert provider.is_available is False
        assert provider.is_available is False

    assert len(caplog.records) == 1
    assert "Screen recording permission is missing" in caplog.text


def test_macos_window_provider_is_available_on_macos_without_permission_check(
    provider: MacOSWindowProvider,
) -> None:
    # Before macOS 10.15 the permission function does not exist
    provider.__dict__["_core_graphics"] = Mock(spec=[])

    assert provider.is_available is True


#########################
# get_window_titles tests
#########################


def test_macos_window_provider_returns_titles_of_normal_windows(
    provider: MacOSWindowProvider,
    core_foundation: Mock,
    core_graphics: Mock,
) -> None:
    raw_windows = {
        100: (0, "Finder"),
        # A window on another layer, e.g. the menu bar
        101: (25, "Menu bar"),
        # A window without a title
        102: (0, None),
        103: (0, ""),
        104: (0, "Terminal"),
    }
    core_graphics.CGWindowListCopyWindowInfo.return_value = 99
    core_foundation.CFArrayGetCount.return_value = len(raw_windows)
    core_foundation.CFArrayGetValueAtIndex.side_effect = lambda _list, index: (
        100 + index
    )

    with patch.object(
        provider, "_read_window", side_effect=lambda info: raw_windows[info]
    ):
        assert provider.get_window_titles() == ("Finder", "Terminal")

    core_graphics.CGWindowListCopyWindowInfo.assert_called_once_with(0, 0)
    core_foundation.CFRelease.assert_called_once_with(99)


def test_macos_window_provider_raises_when_window_list_is_missing(
    provider: MacOSWindowProvider,
    core_foundation: Mock,
    core_graphics: Mock,
) -> None:
    core_graphics.CGWindowListCopyWindowInfo.return_value = None

    with pytest.raises(RuntimeError, match="Failed to retrieve the window list"):
        provider.get_window_titles()

    core_foundation.CFRelease.assert_not_called()


def test_macos_window_provider_releases_window_list_when_reading_fails(
    provider: MacOSWindowProvider,
    core_foundation: Mock,
    core_graphics: Mock,
) -> None:
    core_graphics.CGWindowListCopyWindowInfo.return_value = 99
    core_foundation.CFArrayGetCount.return_value = 1

    with (
        patch.object(
            provider, "_read_window", side_effect=RuntimeError("Test failure")
        ),
        pytest.raises(RuntimeError, match="Test failure"),
    ):
        provider.get_window_titles()

    core_foundation.CFRelease.assert_called_once_with(99)


###################
# _read_layer tests
###################


def test_macos_window_provider_reads_layer(
    provider: MacOSWindowProvider,
    core_foundation: Mock,
) -> None:
    def get_number(
        _number: int,
        _type: int,
        reference: Any,  # result of ctypes.byref(), its type is private
    ) -> bool:
        # "_obj" is the c_int32 which was wrapped by ctypes.byref()
        reference._obj.value = 25

        return True

    core_foundation.CFDictionaryGetValue.return_value = 123
    core_foundation.CFNumberGetValue.side_effect = get_number

    assert provider._read_layer(1) == 25


def test_macos_window_provider_read_layer_returns_none_without_layer(
    provider: MacOSWindowProvider,
    core_foundation: Mock,
) -> None:
    core_foundation.CFDictionaryGetValue.return_value = None

    assert provider._read_layer(1) is None
    core_foundation.CFNumberGetValue.assert_not_called()


def test_macos_window_provider_read_layer_returns_none_when_number_is_unreadable(
    provider: MacOSWindowProvider,
    core_foundation: Mock,
) -> None:
    core_foundation.CFDictionaryGetValue.return_value = 123
    core_foundation.CFNumberGetValue.return_value = False

    assert provider._read_layer(1) is None


###################
# _read_title tests
###################


@pytest.mark.parametrize("title", ["Finder", "Café – Ünïcode"])
def test_macos_window_provider_reads_title(
    provider: MacOSWindowProvider,
    core_foundation: Mock,
    title: str,
) -> None:
    def get_c_string(
        _string: int,
        buffer: ctypes.Array,
        _size: int,
        _encoding: int,
    ) -> bool:
        buffer.value = title.encode("utf-8")  # type: ignore

        return True

    core_foundation.CFDictionaryGetValue.return_value = 123
    core_foundation.CFStringGetLength.return_value = len(title)
    # Enough space for the UTF-8 representation of the title
    core_foundation.CFStringGetMaximumSizeForEncoding.return_value = len(title) * 4
    core_foundation.CFStringGetCString.side_effect = get_c_string

    assert provider._read_title(1) == title


def test_macos_window_provider_read_title_returns_none_without_title(
    provider: MacOSWindowProvider,
    core_foundation: Mock,
) -> None:
    core_foundation.CFDictionaryGetValue.return_value = None

    assert provider._read_title(1) is None
    core_foundation.CFStringGetCString.assert_not_called()


def test_macos_window_provider_read_title_returns_none_when_conversion_fails(
    provider: MacOSWindowProvider,
    core_foundation: Mock,
) -> None:
    core_foundation.CFDictionaryGetValue.return_value = 123
    core_foundation.CFStringGetLength.return_value = 4
    core_foundation.CFStringGetMaximumSizeForEncoding.return_value = 16
    core_foundation.CFStringGetCString.return_value = False

    assert provider._read_title(1) is None
