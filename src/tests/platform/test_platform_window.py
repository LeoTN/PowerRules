from unittest.mock import patch

from powerrules.platform.window import PyWinCtlWindowProvider


def test_pywinctl_window_provider_is_not_available_when_import_fails() -> None:
    original_import = __import__

    def failing_import(
        name: str,
        globals: dict | None = None,
        locals: dict | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ):
        if name == "pywinctl":
            raise ImportError("Test import failure on non-supported platform")

        return original_import(name, globals, locals, fromlist, level)

    with patch("builtins.__import__", side_effect=failing_import):
        provider = PyWinCtlWindowProvider()

    assert provider.is_available is False
