from datetime import datetime


class SystemClockProvider:
    def now(self) -> datetime:
        """Return the current system date and time."""
        return datetime.now()  # noqa: DTZ005 (naive time is used intentionally)
