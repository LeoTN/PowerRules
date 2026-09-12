from typing import Protocol


class WindowProvider(Protocol):
    @property
    def is_available(self) -> bool:
        """Whether the provider is available on the current platform."""
        ...

    def get_window_titles(self) -> tuple[str, ...]:
        """Return a list of all currently open window titles."""
        ...
