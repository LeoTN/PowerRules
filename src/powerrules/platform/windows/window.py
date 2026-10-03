import ctypes
import logging
from ctypes import wintypes
from functools import cached_property

logger = logging.getLogger(__name__)

# Attribute of "DwmGetWindowAttribute" which reports whether a window is cloaked
_DWMWA_CLOAKED = 14

# Index of "GetUserObjectInformationW" which returns the flags of a window station
_UOI_FLAGS = 1
# Flag of an interactive window station. Windows services and scheduled tasks which run
# whether the user is logged on or not use a window station without this flag
_WSF_VISIBLE = 0x0001


class _UserObjectFlags(ctypes.Structure):
    """Layout of "USEROBJECTFLAGS"."""

    _fields_ = (
        ("fInherit", wintypes.BOOL),
        ("fReserved", wintypes.BOOL),
        ("dwFlags", wintypes.DWORD),
    )


class WindowsWindowProvider:
    """Provide window information on Windows using the Win32 API."""

    def __init__(self) -> None:
        self._unavailable_warning_logged = False

    @property
    def is_available(self) -> bool:
        """Whether the provider is available on the current platform.

        Window titles can only be read from an interactive desktop. A process without one
        (e.g. a Windows service) cannot see the windows of the user, so the provider reports itself as unavailable.
        """
        if self._is_interactive_session():
            return True

        # This property is evaluated repeatedly, but the user only needs to be told once
        if not self._unavailable_warning_logged:
            logger.warning(
                "Failed to find an interactive desktop, PowerRules might run as a Windows service. Window conditions will not be available"
            )
            self._unavailable_warning_logged = True

        return False

    def get_window_titles(self) -> tuple[str, ...]:
        """Return the titles of all visible top-level windows.

        Minimized windows are included. Windows without a title and cloaked windows
        (e.g. suspended UWP apps, windows on other virtual desktops) are skipped.

        Returns:
            A tuple of window titles.

        Raises:
            OSError: If the windows cannot be enumerated.
        """
        titles: list[str] = []

        def collect_title(window_handle: int, _parameter: int) -> bool:
            if not self._user32.IsWindowVisible(window_handle):
                return True

            if self._is_cloaked(window_handle):
                return True

            title = self._get_title(window_handle)

            if title:
                titles.append(title)

            # Continue the enumeration
            return True

        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
        )

        if not self._user32.EnumWindows(callback_type(collect_title), 0):
            raise ctypes.WinError(ctypes.get_last_error())

        return tuple(titles)

    @cached_property
    def _user32(self) -> "ctypes.WinDLL":
        """Load user32.dll with the required function signatures."""
        user32 = ctypes.WinDLL("user32", use_last_error=True)

        # The callback is passed as a plain function pointer
        user32.EnumWindows.argtypes = (ctypes.c_void_p, wintypes.LPARAM)
        user32.EnumWindows.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = (wintypes.HWND,)
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.GetProcessWindowStation.argtypes = ()
        user32.GetProcessWindowStation.restype = wintypes.HANDLE
        user32.GetUserObjectInformationW.argtypes = (
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.c_void_p,
        )
        user32.GetUserObjectInformationW.restype = wintypes.BOOL

        return user32

    @cached_property
    def _dwmapi(self) -> "ctypes.WinDLL":
        """Load dwmapi.dll with the required function signatures."""
        dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)

        dwmapi.DwmGetWindowAttribute.argtypes = (
            wintypes.HWND,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
        )
        # HRESULT as a plain integer, so a failure does not raise automatically
        dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long

        return dwmapi

    def _is_interactive_session(self) -> bool:
        """Return whether the process runs on an interactive window station.

        If the window station cannot be queried, the session is treated as not interactive.
        """
        # The handle of the process window station must not be closed
        window_station = self._user32.GetProcessWindowStation()
        flags = _UserObjectFlags()
        needed_length = wintypes.DWORD(0)

        if not self._user32.GetUserObjectInformationW(
            window_station,
            _UOI_FLAGS,
            ctypes.byref(flags),
            ctypes.sizeof(flags),
            ctypes.byref(needed_length),
        ):
            return False

        return bool(flags.dwFlags & _WSF_VISIBLE)

    def _is_cloaked(self, window_handle: int) -> bool:
        """Return whether the window is cloaked (visible according to Windows, but not shown to the user)."""
        cloaked = wintypes.DWORD(0)

        result = self._dwmapi.DwmGetWindowAttribute(
            window_handle,
            _DWMWA_CLOAKED,
            ctypes.byref(cloaked),
            ctypes.sizeof(cloaked),
        )

        # A failed call (non-zero HRESULT) is treated as "not cloaked"
        return result == 0 and cloaked.value != 0

    def _get_title(self, window_handle: int) -> str:
        """Return the title of the window, or an empty string if it has none."""
        length = self._user32.GetWindowTextLengthW(window_handle)

        if length == 0:
            return ""

        buffer = ctypes.create_unicode_buffer(length + 1)
        self._user32.GetWindowTextW(window_handle, buffer, length + 1)

        return buffer.value
