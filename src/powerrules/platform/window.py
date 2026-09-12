import typer


class PyWinCtlWindowProvider:
    """Provide window information using PyWinCtl."""

    def __init__(self):
        self.is_available = False
        self._pywinctl = None

        try:
            import pywinctl

            self.is_available = True
            self._pywinctl = pywinctl

        # This exception is common on headless systems (e.g. Ubuntu Server)
        except Exception:
            typer.echo(
                "[WARNING] Failed to load window provider. Window conditions will not be available",
                err=True,
            )

    def get_window_titles(self) -> tuple[str, ...]:
        """Return a list of all currently open window titles.

        Returns:
            A tuple of window titles.

        Raises:
            RuntimeError: If the window provider is not available.
        """
        if not self.is_available or self._pywinctl is None:
            raise RuntimeError("Window provider is not available")

        return tuple(window.title for window in self._pywinctl.getAllWindows())
