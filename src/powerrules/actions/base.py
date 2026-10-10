from typing import Protocol


class Action(Protocol):
    @property
    def name(self) -> str:
        """Human-readable name of the action, used in log messages."""
        ...

    def execute(self) -> None:
        """Execute the action.

        Raises:
            ActionExecutionError: If the action cannot be executed.
        """
        ...
