from dataclasses import dataclass
from datetime import datetime, time, timedelta
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


class Month(StrEnum):
    """Represent all months."""

    JANUARY = "January"
    FEBRUARY = "February"
    MARCH = "March"
    APRIL = "April"
    MAY = "May"
    JUNE = "June"
    JULY = "July"
    AUGUST = "August"
    SEPTEMBER = "September"
    OCTOBER = "October"
    NOVEMBER = "November"
    DECEMBER = "December"


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


@dataclass(frozen=True)
class DateTimeRange:
    """Represents an absolute range between two points in time without timezone."""

    start: datetime
    end: datetime

    def contains(self, current_datetime: datetime) -> bool:
        """Return whether the given datetime is within the range.

        The start is inclusive and the end is exclusive.

        Args:
            current_datetime: Datetime to check.

        Returns:
            True if the datetime is within the range, otherwise False.
        """
        return self.start <= current_datetime < self.end


class DateTimeCondition:
    def __init__(
        self,
        clock_provider: ClockProvider,
        *,
        time_range: TimeRange | None = None,
        datetime_range: DateTimeRange | None = None,
        weekdays: frozenset[Weekday] | None = None,
        months: frozenset[Month] | None = None,
    ):
        # This is usually verified by Pydantic
        if (
            time_range is None
            and datetime_range is None
            and weekdays is None
            and months is None
        ):
            raise ValueError(
                "A datetime condition requires at least one criterion of 'time_range', 'datetime_range', 'weekdays' or 'months'"
            )

        # This shouldn't happen because Pydantic only allows one of them. Combining both of them is technically possible, but could lead to unexpected behavior
        if time_range is not None and datetime_range is not None:
            raise ValueError(
                "A datetime condition cannot define both 'time_range' and 'datetime_range'"
            )

        self.clock_provider = clock_provider
        self.time_range = time_range
        self.datetime_range = datetime_range
        self.weekdays = weekdays
        self.months = months

    def evaluate(self) -> bool:
        """Evaluate the configured date, time, weekday and month criteria.

        If the time range crosses midnight, the weekday and the month refer to the day on which the range starts.
        For example, with the range 23:00-1:30 and the weekday Monday, the condition matches from Monday 23:00 until Tuesday 1:30.
        With the month December, the condition matches from December 31 23:00 until January 1 1:30.

        For an absolute datetime range, the weekday and the month refer to the current day.

        Returns:
            True if the current date, time, weekday and month match the condition, otherwise False.
        """

        current_datetime = self.clock_provider.now()
        reference_datetime = current_datetime

        # Check each configured criterion, return False if any are not satisfied
        if self.time_range is not None:
            if not self.time_range.contains(current_datetime.time()):
                return False

            # When crossing midnight, the weekday refers to the day on which the range starts
            # For example, with the range 23:00-1:30 and the weekday Monday, the condition matches from Monday 23:00 until midnight (0:00) as usual.
            # When crossing midnight, the weekday is technically Tueday, but will be treated as Monday to match until 1:30 on Tuesday
            if (
                # The time range crosses midnight and the current time is before the end of the range
                self.time_range.start > self.time_range.end
                and current_datetime.time() < self.time_range.end
            ):
                reference_datetime = current_datetime - timedelta(days=1)

        if self.datetime_range is not None and not self.datetime_range.contains(
            current_datetime
        ):
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
            )[reference_datetime.weekday()]

            if current_weekday not in self.weekdays:
                return False

        if self.months is not None:
            # The enum members are defined in calendar order, so the month number is the position
            current_month = tuple(Month)[reference_datetime.month - 1]

            if current_month not in self.months:
                return False

        # All configured criteria are satisfied
        return True
