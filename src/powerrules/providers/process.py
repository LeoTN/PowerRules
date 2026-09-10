from typing import Protocol


class ProcessProvider(Protocol):
    def get_process_names(self) -> tuple[str, ...]:
        """Return a list of all currently existing process names."""
        ...
