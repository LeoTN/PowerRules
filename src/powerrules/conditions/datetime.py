from dataclasses import dataclass
from datetime import time
from enum import StrEnum

from powerrules.providers.clock import ClockProvider


class Weekday(StrEnum):
    """Represent all weekdays."""

    MONDAY = "Monday"
    TUESDAY = "Tuesday"
    WEDNESDAY = "Wednesday"
    THURSDAY = "Thursday"
    FRIDAY = "Friday"
    SATURDAY = "Saturday"
    SUNDAY = "Sunday"


@dataclass(frozen=True)
class TimeRange:
    """Represents a range of time within a day."""

    start: time
    end: time

    def contains(self, current_time: time) -> bool:
        """Return whether the given time is within the range.

        The start time is inclusive and the end time is exclusive (6:00 is in the range 23:00-7:00, but 7:00 is not).

        Ranges crossing midnight are supported.

        Args:
            current_time: Time to check.

        Returns:
            True if the time is within the range, otherwise False.
        """
        # The range does not cross midnight
        if self.start <= self.end:
            # Does the current_time fall within the range?
            return self.start <= current_time < self.end

        # The range crosses midnight (e.g., 23:00-7:00)
        # Does the current_time fall within the range?
        return current_time >= self.start or current_time < self.end


class DateTimeCondition:
    def __init__(
        self,
        clock_provider: ClockProvider,
        *,
        time_range: TimeRange | None = None,
        weekdays: frozenset[Weekday] | None = None,
    ):
        self.clock_provider = clock_provider
        self.time_range = time_range
        self.weekdays = weekdays

        # This is usually verified with Pydantic
        if self.time_range is None and self.weekdays is None:
            raise ValueError(
                "DateTimeCondition requires at least one criterion of time_range or weekdays to be specified"
            )

    def evaluate(self) -> bool:
        """Evaluate the configured date, time and weekday criteria.

        Returns:
            True if the current date, time and weekday match the current date, otherwise False.
        """
        current_datetime = self.clock_provider.now()

        # Check each configured criterion, return False if any are not satisfied
        if self.time_range is not None:
            if not self.time_range.contains(current_datetime.time()):
                return False

        if self.weekdays is not None:
            current_weekday = (
                Weekday.MONDAY,
                Weekday.TUESDAY,
                Weekday.WEDNESDAY,
                Weekday.THURSDAY,
                Weekday.FRIDAY,
                Weekday.SATURDAY,
                Weekday.SUNDAY,
            )[current_datetime.weekday()]

            if current_weekday not in self.weekdays:
                return False

        # All configured criteria are satisfied
        return True
