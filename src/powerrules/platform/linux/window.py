import ctypes
import logging
import os
import struct
from collections.abc import Iterable
from functools import cache
from types import TracebackType
from typing import Self

logger = logging.getLogger(__name__)

_LIBXCB_NAME = "libxcb.so.1"

# Predefined atoms of the X11 core protocol
_ATOM_STRING = 31
_ATOM_WINDOW = 33
_ATOM_WM_NAME = 39

# Maximum property length in 32-bit units (4 MiB), which is far more than a window list or a title needs
_MAX_PROPERTY_LENGTH = 1 << 20


class _ScreenIterator(ctypes.Structure):
    """Layout of "xcb_screen_iterator_t"."""

    _fields_ = (
        ("data", ctypes.c_void_p),
        ("rem", ctypes.c_int),
        ("index", ctypes.c_int),
    )


class _Cookie(ctypes.Structure):
    """Layout of the request cookies (e.g. "xcb_get_property_cookie_t")."""

    _fields_ = (("sequence", ctypes.c_uint),)


class _InternAtomReply(ctypes.Structure):
    """Layout of "xcb_intern_atom_reply_t"."""

    _fields_ = (
        ("response_type", ctypes.c_uint8),
        ("pad0", ctypes.c_uint8),
        ("sequence", ctypes.c_uint16),
        ("length", ctypes.c_uint32),
        ("atom", ctypes.c_uint32),
    )


class _GetPropertyReply(ctypes.Structure):
    """Layout of "xcb_get_property_reply_t"."""

    _fields_ = (
        ("response_type", ctypes.c_uint8),
        ("format", ctypes.c_uint8),
        ("sequence", ctypes.c_uint16),
        ("length", ctypes.c_uint32),
        ("type", ctypes.c_uint32),
        ("bytes_after", ctypes.c_uint32),
        ("value_len", ctypes.c_uint32),
        ("pad0", ctypes.c_uint8 * 12),
    )


@cache
def _load_libxcb() -> ctypes.CDLL:
    """Load libxcb with the required function signatures.

    Returns:
        The loaded library.

    Raises:
        OSError: If libxcb is not installed.
    """
    libxcb = ctypes.CDLL(_LIBXCB_NAME)

    libxcb.xcb_connect.argtypes = (ctypes.c_char_p, ctypes.POINTER(ctypes.c_int))
    libxcb.xcb_connect.restype = ctypes.c_void_p
    libxcb.xcb_connection_has_error.argtypes = (ctypes.c_void_p,)
    libxcb.xcb_connection_has_error.restype = ctypes.c_int
    libxcb.xcb_disconnect.argtypes = (ctypes.c_void_p,)
    libxcb.xcb_disconnect.restype = None
    libxcb.xcb_get_setup.argtypes = (ctypes.c_void_p,)
    libxcb.xcb_get_setup.restype = ctypes.c_void_p
    libxcb.xcb_setup_roots_iterator.argtypes = (ctypes.c_void_p,)
    libxcb.xcb_setup_roots_iterator.restype = _ScreenIterator
    libxcb.xcb_screen_next.argtypes = (ctypes.POINTER(_ScreenIterator),)
    libxcb.xcb_screen_next.restype = None
    libxcb.xcb_intern_atom.argtypes = (
        ctypes.c_void_p,
        ctypes.c_uint8,
        ctypes.c_uint16,
        ctypes.c_char_p,
    )
    libxcb.xcb_intern_atom.restype = _Cookie
    libxcb.xcb_intern_atom_reply.argtypes = (
        ctypes.c_void_p,
        _Cookie,
        ctypes.c_void_p,
    )
    libxcb.xcb_intern_atom_reply.restype = ctypes.POINTER(_InternAtomReply)
    libxcb.xcb_get_property.argtypes = (
        ctypes.c_void_p,
        ctypes.c_uint8,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_uint32,
    )
    libxcb.xcb_get_property.restype = _Cookie
    libxcb.xcb_get_property_reply.argtypes = (
        ctypes.c_void_p,
        _Cookie,
        ctypes.c_void_p,
    )
    libxcb.xcb_get_property_reply.restype = ctypes.POINTER(_GetPropertyReply)
    libxcb.xcb_get_property_value.argtypes = (ctypes.POINTER(_GetPropertyReply),)
    libxcb.xcb_get_property_value.restype = ctypes.c_void_p
    libxcb.xcb_get_property_value_length.argtypes = (ctypes.POINTER(_GetPropertyReply),)
    libxcb.xcb_get_property_value_length.restype = ctypes.c_int

    return libxcb


@cache
def _load_libc() -> ctypes.CDLL:
    """Load the C library, which is required to free the replies allocated by libxcb."""
    libc = ctypes.CDLL(None)

    libc.free.argtypes = (ctypes.c_void_p,)
    libc.free.restype = None

    return libc


class _XcbConnection:
    """Context-managed connection to the X server which reads window properties via libxcb.

    Unlike Xlib, libxcb never terminates the process on errors. They are reported
    through return values (a missing reply or an error flag of the connection) instead.
    """

    def __init__(self) -> None:
        """Prepare the connection.

        Raises:
            OSError: If libxcb is not installed.
        """
        self._libxcb = _load_libxcb()
        self._libc = _load_libc()
        self._connection: int | None = None
        self._atoms: dict[str, int | None] = {}
        self.root_window = 0

    def __enter__(self) -> Self:
        """Connect to the X server given by the DISPLAY environment variable.

        Raises:
            OSError: If the connection to the X server fails.
        """
        screen_number = ctypes.c_int(0)
        connection = self._libxcb.xcb_connect(None, ctypes.byref(screen_number))

        try:
            # A failed connection is only reported by an error flag, but it still has to be disconnected
            if self._libxcb.xcb_connection_has_error(connection):
                raise OSError("Failed to connect to the X server")

            self.root_window = self._find_root_window(connection, screen_number.value)
        except Exception:
            self._libxcb.xcb_disconnect(connection)
            raise

        self._connection = connection

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Disconnect from the X server."""
        if self._connection is None:
            return

        self._libxcb.xcb_disconnect(self._connection)
        self._connection = None

    def intern_atom(self, name: str) -> int | None:
        """Look up an existing atom.

        Args:
            name: Name of the atom.

        Returns:
            The atom, or None if it does not exist or the request failed.
        """
        if name in self._atoms:
            return self._atoms[name]

        encoded_name = name.encode("ascii")
        # Only look up existing atoms, a missing one means that nobody uses the property
        cookie = self._libxcb.xcb_intern_atom(
            self._connection, 1, len(encoded_name), encoded_name
        )
        reply = self._libxcb.xcb_intern_atom_reply(self._connection, cookie, None)
        atom: int | None = None

        if reply:
            try:
                # The atom 0 (None) is returned for atoms which do not exist
                atom = reply.contents.atom or None
            finally:
                self._libc.free(reply)

        self._atoms[name] = atom

        return atom

    def get_property(
        self, window_id: int, property_atom: int, type_atom: int
    ) -> bytes | None:
        """Read a window property.

        Args:
            window_id: Window to read the property from.
            property_atom: Atom of the property.
            type_atom: Expected type of the property.

        Returns:
            The raw value of the property, or None if the property does not exist,
            has another type or the request failed (e.g. the window was closed meanwhile).
        """
        cookie = self._libxcb.xcb_get_property(
            self._connection,
            0,
            window_id,
            property_atom,
            type_atom,
            0,
            _MAX_PROPERTY_LENGTH,
        )
        reply = self._libxcb.xcb_get_property_reply(self._connection, cookie, None)

        if not reply:
            return None

        try:
            if reply.contents.type != type_atom:
                return None

            length = self._libxcb.xcb_get_property_value_length(reply)
            value = self._libxcb.xcb_get_property_value(reply)

            return ctypes.string_at(value, length)
        finally:
            self._libc.free(reply)

    def _find_root_window(self, connection: int, screen_number: int) -> int:
        """Find the root window of the screen given by the display name.

        Raises:
            OSError: If the screen does not exist.
        """
        setup = self._libxcb.xcb_get_setup(connection)
        screen_iterator = self._libxcb.xcb_setup_roots_iterator(setup)

        for _ in range(screen_number):
            self._libxcb.xcb_screen_next(ctypes.byref(screen_iterator))

        if screen_iterator.rem <= 0 or not screen_iterator.data:
            raise OSError(f"Failed to find the X screen {screen_number}")

        # The root window is the first member of "xcb_screen_t"
        return ctypes.c_uint32.from_address(screen_iterator.data).value


class LinuxWindowProvider:
    """Provide window information on Linux with X11 using libxcb."""

    def __init__(self) -> None:
        self._unavailable_warning_logged = False

    @property
    def is_available(self) -> bool:
        """Whether the provider is available on the current platform.

        The provider needs an X11 session with a window manager which provides the window list.
        Wayland sessions are not supported, because they do not allow listing windows.
        """
        unavailable_reason = self._get_unavailable_reason()

        if unavailable_reason is None:
            return True

        # This property is evaluated repeatedly, but the user only needs to be told once
        if not self._unavailable_warning_logged:
            logger.warning(
                f"{unavailable_reason}. Window conditions will not be available"
            )
            self._unavailable_warning_logged = True

        return False

    def get_window_titles(self) -> tuple[str, ...]:
        """Return the titles of all windows managed by the window manager.

        Minimized windows and windows on other desktops are included. Windows without a title are skipped.

        Returns:
            A tuple of window titles.

        Raises:
            OSError: If the connection to the X server fails.
            RuntimeError: If the window manager does not provide a window list.
        """
        with _XcbConnection() as connection:
            window_ids = self._read_window_ids(connection)

            if window_ids is None:
                raise RuntimeError("The window manager does not provide a window list")

            return self._select_window_titles(
                self._read_title(connection, window_id) for window_id in window_ids
            )

    @staticmethod
    def _select_window_titles(raw_titles: Iterable[str | None]) -> tuple[str, ...]:
        """Select the usable window titles.

        Args:
            raw_titles: Titles of all windows, None if a window has no readable title.

        Returns:
            The non-empty titles.
        """
        return tuple(title for title in raw_titles if title)

    @staticmethod
    def _get_unavailable_reason() -> str | None:
        """Return why the provider is unavailable, or None if it is available."""
        if os.environ.get("XDG_SESSION_TYPE", "").casefold() == "wayland":
            return "Listing windows is not possible in Wayland sessions"

        # This is the usual case on headless systems (e.g. Ubuntu Server)
        if not os.environ.get("DISPLAY"):
            return "No X11 display found"

        try:
            with _XcbConnection() as connection:
                if LinuxWindowProvider._read_window_ids(connection) is None:
                    return "The window manager does not provide a window list"
        except OSError as e:
            return f"Failed to access the X server: {e}"

        return None

    @staticmethod
    def _read_window_ids(connection: _XcbConnection) -> tuple[int, ...] | None:
        """Read the window list of the window manager (EWMH "_NET_CLIENT_LIST").

        Returns:
            The window IDs, or None if the window manager does not provide the list.
        """
        client_list_atom = connection.intern_atom("_NET_CLIENT_LIST")

        if client_list_atom is None:
            return None

        data = connection.get_property(
            connection.root_window, client_list_atom, _ATOM_WINDOW
        )

        if data is None:
            return None

        return struct.unpack(f"={len(data) // 4}I", data)

    @staticmethod
    def _read_title(connection: _XcbConnection, window_id: int) -> str | None:
        """Read the title of a window, or None if it has none or the window was closed meanwhile."""
        name_atom = connection.intern_atom("_NET_WM_NAME")
        utf8_atom = connection.intern_atom("UTF8_STRING")

        if name_atom is not None and utf8_atom is not None:
            data = connection.get_property(window_id, name_atom, utf8_atom)

            if data:
                return data.decode("utf-8", errors="replace")

        # Fallback for legacy applications which only set the ICCCM title (Latin-1 by definition)
        data = connection.get_property(window_id, _ATOM_WM_NAME, _ATOM_STRING)

        if data:
            return data.decode("latin-1")

        return None
