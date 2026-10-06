import ctypes
import logging
import struct
from collections.abc import Iterator
from unittest.mock import Mock, patch

import pytest

from powerrules.platform.linux.window import (
    _ATOM_WM_NAME,
    LinuxWindowProvider,
    _XcbConnection,
)

MODULE = "powerrules.platform.linux.window"


@pytest.fixture
def libxcb() -> Iterator[Mock]:
    with patch(f"{MODULE}._load_libxcb") as load_libxcb:
        yield load_libxcb.return_value


@pytest.fixture
def libc() -> Iterator[Mock]:
    with patch(f"{MODULE}._load_libc") as load_libc:
        yield load_libc.return_value


@pytest.fixture
def xcb_connection(libxcb: Mock, libc: Mock) -> _XcbConnection:
    """A real connection object which talks to a mocked libxcb."""
    return _XcbConnection()


@pytest.fixture
def xcb_class() -> Iterator[Mock]:
    """Replace the connection class which is used by the provider."""
    with patch(f"{MODULE}._XcbConnection") as connection_class:
        yield connection_class


@pytest.fixture
def connection(xcb_class: Mock) -> Mock:
    return xcb_class.return_value.__enter__.return_value


@pytest.fixture
def x11_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.setenv("DISPLAY", ":0")


#########################
# _get_unavailable_reason
#########################


def test_linux_window_provider_reports_wayland_as_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XDG_SESSION_TYPE", "Wayland")

    assert "Wayland" in str(LinuxWindowProvider._get_unavailable_reason())


def test_linux_window_provider_reports_missing_display_as_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.delenv("DISPLAY", raising=False)

    assert LinuxWindowProvider._get_unavailable_reason() == "No X11 display found"


@pytest.mark.usefixtures("x11_environment")
def test_linux_window_provider_reports_x_server_failure_as_unavailable(
    xcb_class: Mock,
) -> None:
    xcb_class.return_value.__enter__.side_effect = OSError("Test connection failure")

    assert (
        LinuxWindowProvider._get_unavailable_reason()
        == "Failed to access the X server: Test connection failure"
    )


@pytest.mark.usefixtures("x11_environment", "xcb_class")
def test_linux_window_provider_reports_missing_window_list_as_unavailable() -> None:
    with patch.object(LinuxWindowProvider, "_read_window_ids", return_value=None):
        assert (
            LinuxWindowProvider._get_unavailable_reason()
            == "The window manager does not provide a window list"
        )


@pytest.mark.usefixtures("x11_environment", "xcb_class")
def test_linux_window_provider_has_no_unavailable_reason_on_x11() -> None:
    with patch.object(LinuxWindowProvider, "_read_window_ids", return_value=(1, 2)):
        assert LinuxWindowProvider._get_unavailable_reason() is None


####################
# is_available tests
####################


def test_linux_window_provider_is_available_without_unavailable_reason() -> None:
    with patch.object(
        LinuxWindowProvider, "_get_unavailable_reason", return_value=None
    ):
        assert LinuxWindowProvider().is_available is True


def test_linux_window_provider_logs_unavailable_warning_only_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = LinuxWindowProvider()

    with (
        patch.object(
            LinuxWindowProvider,
            "_get_unavailable_reason",
            return_value="No X11 display found",
        ),
        caplog.at_level(logging.WARNING),
    ):
        assert provider.is_available is False
        assert provider.is_available is False

    assert len(caplog.records) == 1
    assert (
        "No X11 display found. Window conditions will not be available" in caplog.text
    )


#########################
# get_window_titles tests
#########################


def test_linux_window_provider_returns_titles_of_all_windows(
    connection: Mock,
) -> None:
    titles = {1: "First window", 2: None, 3: "Third window", 4: ""}

    with (
        patch.object(
            LinuxWindowProvider, "_read_window_ids", return_value=(1, 2, 3, 4)
        ),
        patch.object(
            LinuxWindowProvider,
            "_read_title",
            side_effect=lambda _connection, window_id: titles[window_id],
        ),
    ):
        # Windows without a readable or with an empty title are skipped
        assert LinuxWindowProvider().get_window_titles() == (
            "First window",
            "Third window",
        )


@pytest.mark.usefixtures("xcb_class")
def test_linux_window_provider_raises_without_window_list() -> None:
    with (
        patch.object(LinuxWindowProvider, "_read_window_ids", return_value=None),
        pytest.raises(RuntimeError, match="does not provide a window list"),
    ):
        LinuxWindowProvider().get_window_titles()


def test_linux_window_provider_propagates_connection_error(xcb_class: Mock) -> None:
    xcb_class.return_value.__enter__.side_effect = OSError("Test connection failure")

    with pytest.raises(OSError, match="Test connection failure"):
        LinuxWindowProvider().get_window_titles()


##################
# _read_window_ids
##################


def test_linux_window_provider_reads_window_ids() -> None:
    connection = Mock()
    connection.get_property.return_value = struct.pack("=3I", 10, 20, 30)

    assert LinuxWindowProvider._read_window_ids(connection) == (10, 20, 30)


def test_linux_window_provider_read_window_ids_without_client_list_atom() -> None:
    connection = Mock()
    connection.intern_atom.return_value = None

    assert LinuxWindowProvider._read_window_ids(connection) is None
    connection.get_property.assert_not_called()


def test_linux_window_provider_read_window_ids_without_property() -> None:
    connection = Mock()
    connection.get_property.return_value = None

    assert LinuxWindowProvider._read_window_ids(connection) is None


#############
# _read_title
#############


def _build_title_connection(properties: dict[int, bytes | None]) -> Mock:
    """Build a connection which returns the given raw value for each property atom."""
    atoms = {"_NET_WM_NAME": 100, "UTF8_STRING": 101}
    connection = Mock()
    connection.intern_atom.side_effect = lambda name: atoms[name]
    connection.get_property.side_effect = lambda _window_id, property_atom, _type_atom: (
        properties.get(property_atom)
    )

    return connection


def test_linux_window_provider_reads_utf8_title() -> None:
    connection = _build_title_connection({100: "Täst Fenster".encode()})

    assert LinuxWindowProvider._read_title(connection, 1) == "Täst Fenster"


def test_linux_window_provider_falls_back_to_legacy_latin1_title() -> None:
    connection = _build_title_connection({_ATOM_WM_NAME: "Täst".encode("latin-1")})

    assert LinuxWindowProvider._read_title(connection, 1) == "Täst"


def test_linux_window_provider_read_title_returns_none_without_title() -> None:
    connection = _build_title_connection({})

    assert LinuxWindowProvider._read_title(connection, 1) is None


def test_linux_window_provider_replaces_invalid_utf8_bytes_in_title() -> None:
    connection = _build_title_connection({100: b"Test \xff title"})

    assert LinuxWindowProvider._read_title(connection, 1) == "Test \ufffd title"


######################
# _XcbConnection tests
######################


def test_xcb_connection_connects_and_disconnects(
    xcb_connection: _XcbConnection,
    libxcb: Mock,
) -> None:
    libxcb.xcb_connection_has_error.return_value = 0

    with (
        patch.object(_XcbConnection, "_find_root_window", return_value=42),
        xcb_connection as connection,
    ):
        assert connection.root_window == 42
        libxcb.xcb_disconnect.assert_not_called()

    libxcb.xcb_disconnect.assert_called_once_with(libxcb.xcb_connect.return_value)


def test_xcb_connection_disconnects_when_connection_fails(
    xcb_connection: _XcbConnection,
    libxcb: Mock,
) -> None:
    libxcb.xcb_connection_has_error.return_value = 1

    with (
        pytest.raises(OSError, match="Failed to connect to the X server"),
        xcb_connection,
    ):
        pass

    libxcb.xcb_disconnect.assert_called_once_with(libxcb.xcb_connect.return_value)


def test_xcb_connection_disconnects_when_root_window_lookup_fails(
    xcb_connection: _XcbConnection,
    libxcb: Mock,
) -> None:
    libxcb.xcb_connection_has_error.return_value = 0

    with (
        patch.object(
            _XcbConnection,
            "_find_root_window",
            side_effect=OSError("Failed to find the X screen 3"),
        ),
        pytest.raises(OSError, match="Failed to find the X screen"),
        xcb_connection,
    ):
        pass

    libxcb.xcb_disconnect.assert_called_once()


def test_xcb_connection_interns_atom_once_and_frees_reply(
    xcb_connection: _XcbConnection,
    libxcb: Mock,
    libc: Mock,
) -> None:
    reply = Mock()
    reply.contents.atom = 7
    libxcb.xcb_intern_atom_reply.return_value = reply

    assert xcb_connection.intern_atom("_NET_CLIENT_LIST") == 7
    # The second call is answered from the cache
    assert xcb_connection.intern_atom("_NET_CLIENT_LIST") == 7

    libxcb.xcb_intern_atom.assert_called_once()
    libc.free.assert_called_once_with(reply)


def test_xcb_connection_returns_none_for_unknown_atom(
    xcb_connection: _XcbConnection,
    libxcb: Mock,
) -> None:
    reply = Mock()
    # The atom 0 means that the atom does not exist
    reply.contents.atom = 0
    libxcb.xcb_intern_atom_reply.return_value = reply

    assert xcb_connection.intern_atom("_UNKNOWN") is None


def test_xcb_connection_returns_none_when_atom_request_fails(
    xcb_connection: _XcbConnection,
    libxcb: Mock,
    libc: Mock,
) -> None:
    libxcb.xcb_intern_atom_reply.return_value = None

    assert xcb_connection.intern_atom("_NET_CLIENT_LIST") is None
    libc.free.assert_not_called()


def test_xcb_connection_reads_property_value(
    xcb_connection: _XcbConnection,
    libxcb: Mock,
    libc: Mock,
) -> None:
    # The buffer has to stay alive while the address is read
    value = ctypes.create_string_buffer(b"abc")
    reply = Mock()
    reply.contents.type = 33
    libxcb.xcb_get_property_reply.return_value = reply
    libxcb.xcb_get_property_value_length.return_value = 3
    libxcb.xcb_get_property_value.return_value = ctypes.addressof(value)

    assert xcb_connection.get_property(1, 2, 33) == b"abc"
    libc.free.assert_called_once_with(reply)


def test_xcb_connection_returns_none_for_property_with_unexpected_type(
    xcb_connection: _XcbConnection,
    libxcb: Mock,
    libc: Mock,
) -> None:
    reply = Mock()
    reply.contents.type = 99
    libxcb.xcb_get_property_reply.return_value = reply

    assert xcb_connection.get_property(1, 2, 33) is None
    # The reply is freed even though it is not used
    libc.free.assert_called_once_with(reply)


def test_xcb_connection_returns_none_when_property_request_fails(
    xcb_connection: _XcbConnection,
    libxcb: Mock,
    libc: Mock,
) -> None:
    libxcb.xcb_get_property_reply.return_value = None

    assert xcb_connection.get_property(1, 2, 33) is None
    libc.free.assert_not_called()
