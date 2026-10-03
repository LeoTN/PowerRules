import ctypes
import logging
from collections.abc import Iterable
from functools import cached_property

logger = logging.getLogger(__name__)

_CORE_FOUNDATION_PATH = (
    "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
)
_CORE_GRAPHICS_PATH = "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"

# CoreGraphics constants: Include all windows (also minimized ones or windows on other spaces)
_WINDOW_LIST_OPTION_ALL = 0
_NULL_WINDOW_ID = 0
# Normal application windows are on layer 0, the menu bar, the dock and overlays use other layers
_NORMAL_WINDOW_LAYER = 0

# CoreFoundation constants
_STRING_ENCODING_UTF8 = 0x08000100
_NUMBER_TYPE_SINT32 = 3


class MacOSWindowProvider:
    """Provide window information on macOS using the CoreGraphics API."""

    def __init__(self) -> None:
        self._permission_warning_logged = False

    @property
    def is_available(self) -> bool:
        """Whether the provider is available on the current platform.

        Window titles of other applications are only readable with the screen recording permission.
        Without it, all titles would be empty, so the provider reports itself as unavailable.
        """
        if self._has_screen_recording_access():
            return True

        # This property is evaluated repeatedly, but the user only needs to be told once
        if not self._permission_warning_logged:
            logger.warning(
                "Screen recording permission is missing, window titles cannot be read. Window conditions will not be available"
            )
            self._permission_warning_logged = True

        return False

    def get_window_titles(self) -> tuple[str, ...]:
        """Return the titles of all normal application windows.

        Minimized windows and windows on other spaces are included. Windows without a title are skipped.

        Returns:
            A tuple of window titles.

        Raises:
            RuntimeError: If the window list cannot be retrieved.
        """
        window_list = self._core_graphics.CGWindowListCopyWindowInfo(
            _WINDOW_LIST_OPTION_ALL, _NULL_WINDOW_ID
        )

        if not window_list:
            raise RuntimeError("Failed to retrieve the window list")

        try:
            window_count = self._core_foundation.CFArrayGetCount(window_list)

            raw_windows = [
                self._read_window(
                    self._core_foundation.CFArrayGetValueAtIndex(window_list, index)
                )
                for index in range(window_count)
            ]
        finally:
            # The window list was created by a "Copy" function, so it has to be released
            self._core_foundation.CFRelease(window_list)

        return self._select_window_titles(raw_windows)

    @staticmethod
    def _select_window_titles(
        raw_windows: Iterable[tuple[int | None, str | None]],
    ) -> tuple[str, ...]:
        """Select the titles of normal application windows.

        Args:
            raw_windows: Pairs of window layer and window title. Both are None if CoreGraphics does not provide them.

        Returns:
            The non-empty titles of all windows on the normal window layer.
        """
        return tuple(
            title
            for layer, title in raw_windows
            if layer == _NORMAL_WINDOW_LAYER and title
        )

    @cached_property
    def _core_foundation(self) -> ctypes.CDLL:
        """Load CoreFoundation with the required function signatures."""
        core_foundation = ctypes.CDLL(_CORE_FOUNDATION_PATH)

        # CFTypeRef values are handled as plain pointers, CFIndex is a "long"
        core_foundation.CFArrayGetCount.argtypes = (ctypes.c_void_p,)
        core_foundation.CFArrayGetCount.restype = ctypes.c_long
        core_foundation.CFArrayGetValueAtIndex.argtypes = (
            ctypes.c_void_p,
            ctypes.c_long,
        )
        core_foundation.CFArrayGetValueAtIndex.restype = ctypes.c_void_p
        core_foundation.CFDictionaryGetValue.argtypes = (
            ctypes.c_void_p,
            ctypes.c_void_p,
        )
        core_foundation.CFDictionaryGetValue.restype = ctypes.c_void_p
        core_foundation.CFStringCreateWithCString.argtypes = (
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_uint32,
        )
        core_foundation.CFStringCreateWithCString.restype = ctypes.c_void_p
        core_foundation.CFStringGetLength.argtypes = (ctypes.c_void_p,)
        core_foundation.CFStringGetLength.restype = ctypes.c_long
        core_foundation.CFStringGetMaximumSizeForEncoding.argtypes = (
            ctypes.c_long,
            ctypes.c_uint32,
        )
        core_foundation.CFStringGetMaximumSizeForEncoding.restype = ctypes.c_long
        core_foundation.CFStringGetCString.argtypes = (
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_long,
            ctypes.c_uint32,
        )
        core_foundation.CFStringGetCString.restype = ctypes.c_bool
        core_foundation.CFNumberGetValue.argtypes = (
            ctypes.c_void_p,
            ctypes.c_long,
            ctypes.c_void_p,
        )
        core_foundation.CFNumberGetValue.restype = ctypes.c_bool
        core_foundation.CFRelease.argtypes = (ctypes.c_void_p,)
        core_foundation.CFRelease.restype = None

        return core_foundation

    @cached_property
    def _core_graphics(self) -> ctypes.CDLL:
        """Load CoreGraphics with the required function signatures."""
        core_graphics = ctypes.CDLL(_CORE_GRAPHICS_PATH)

        core_graphics.CGWindowListCopyWindowInfo.argtypes = (
            ctypes.c_uint32,
            ctypes.c_uint32,
        )
        core_graphics.CGWindowListCopyWindowInfo.restype = ctypes.c_void_p

        # The permission was introduced with macOS 10.15, the function does not exist before
        if hasattr(core_graphics, "CGPreflightScreenCaptureAccess"):
            core_graphics.CGPreflightScreenCaptureAccess.restype = ctypes.c_bool

        return core_graphics

    # The values of the dictionary keys are identical to their names. The keys are constants for the whole
    # process lifetime, so they are created once and intentionally never released
    @cached_property
    def _layer_key(self) -> int:
        """CoreFoundation string for the "kCGWindowLayer" key."""
        return self._create_string("kCGWindowLayer")

    @cached_property
    def _name_key(self) -> int:
        """CoreFoundation string for the "kCGWindowName" key."""
        return self._create_string("kCGWindowName")

    def _create_string(self, text: str) -> int:
        """Create a CoreFoundation string from an ASCII text."""
        return self._core_foundation.CFStringCreateWithCString(
            None, text.encode("ascii"), _STRING_ENCODING_UTF8
        )

    def _has_screen_recording_access(self) -> bool:
        """Return whether the screen recording permission is granted (without asking the user for it)."""
        if not hasattr(self._core_graphics, "CGPreflightScreenCaptureAccess"):
            return True

        return bool(self._core_graphics.CGPreflightScreenCaptureAccess())

    def _read_window(self, window_info: int) -> tuple[int | None, str | None]:
        """Read the layer and the title of a window from its CoreGraphics dictionary."""
        return (self._read_layer(window_info), self._read_title(window_info))

    def _read_layer(self, window_info: int) -> int | None:
        """Read the window layer, or None if it is missing."""
        number = self._core_foundation.CFDictionaryGetValue(
            window_info, self._layer_key
        )

        if not number:
            return None

        layer = ctypes.c_int32()

        if not self._core_foundation.CFNumberGetValue(
            number, _NUMBER_TYPE_SINT32, ctypes.byref(layer)
        ):
            return None

        return layer.value

    def _read_title(self, window_info: int) -> str | None:
        """Read the window title, or None if it is missing."""
        string = self._core_foundation.CFDictionaryGetValue(window_info, self._name_key)

        if not string:
            return None

        length = self._core_foundation.CFStringGetLength(string)
        # One additional byte for the terminating null character
        buffer_size = (
            self._core_foundation.CFStringGetMaximumSizeForEncoding(
                length, _STRING_ENCODING_UTF8
            )
            + 1
        )
        buffer = ctypes.create_string_buffer(buffer_size)

        if not self._core_foundation.CFStringGetCString(
            string, buffer, buffer_size, _STRING_ENCODING_UTF8
        ):
            return None

        return buffer.value.decode("utf-8")
