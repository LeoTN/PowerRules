from datetime import datetime, time

import pytest

from powerrules.conditions.datetime import (
    DateTimeCondition,
    DateTimeRange,
    Month,
    TimeRange,
    Weekday,
)
from tests.dummies import Dummy_ClockProvider

#################
# TimeRange tests
#################


def test_time_range_matches_time_inside_normal_range() -> None:
    time_range = TimeRange(
        start=time(10, 0),
        end=time(18, 0),
    )

    assert time_range.contains(time(12, 0)) is True


def test_time_range_does_not_match_time_before_normal_range() -> None:
    time_range = TimeRange(
        start=time(10, 0),
        end=time(18, 0),
    )

    assert time_range.contains(time(9, 59)) is False


def test_time_range_does_not_match_time_after_normal_range() -> None:
    time_range = TimeRange(
        start=time(10, 0),
        end=time(18, 0),
    )

    assert time_range.contains(time(18, 1)) is False


def test_time_range_includes_start_time() -> None:
    time_range = TimeRange(
        start=time(10, 0),
        end=time(18, 0),
    )

    assert time_range.contains(time(10, 0)) is True


def test_time_range_excludes_end_time() -> None:
    time_range = TimeRange(
        start=time(10, 0),
        end=time(18, 0),
    )

    assert time_range.contains(time(18, 0)) is False


def test_time_range_matches_time_before_midnight_when_crossing_midnight() -> None:
    time_range = TimeRange(
        start=time(22, 0),
        end=time(6, 0),
    )

    assert time_range.contains(time(23, 0)) is True


def test_time_range_matches_time_after_midnight_when_crossing_midnight() -> None:
    time_range = TimeRange(
        start=time(22, 0),
        end=time(6, 0),
    )

    assert time_range.contains(time(2, 0)) is True


def test_time_range_does_not_match_time_outside_midnight_range() -> None:
    time_range = TimeRange(
        start=time(22, 0),
        end=time(6, 0),
    )

    assert time_range.contains(time(12, 0)) is False


def test_time_range_excludes_end_time_when_crossing_midnight() -> None:
    time_range = TimeRange(
        start=time(22, 0),
        end=time(6, 0),
    )

    assert time_range.contains(time(6, 0)) is False


# Special case: start and end are equal, which means no time is in the range
def test_time_range_with_equal_start_and_end_matches_no_time() -> None:
    time_range = TimeRange(
        start=time(10, 0),
        end=time(10, 0),
    )

    assert time_range.contains(time(10, 0)) is False
    assert time_range.contains(time(12, 0)) is False


#####################
# DateTimeRange tests
#####################


@pytest.mark.parametrize(
    ("current_datetime", "expected"),
    [
        # Before the start of the range
        (datetime(2026, 8, 21, 17, 59, 59), False),
        # The start of the range is inclusive
        (datetime(2026, 8, 21, 18, 0), True),
        # The range crosses midnight between the two dates
        (datetime(2026, 8, 21, 23, 59, 59), True),
        (datetime(2026, 8, 22, 0, 0), True),
        (datetime(2026, 8, 22, 5, 59, 59), True),
        # The end of the range is exclusive
        (datetime(2026, 8, 22, 6, 0), False),
        # The date is taken into account, not only the time of day
        (datetime(2026, 8, 20, 22, 0), False),
        (datetime(2026, 8, 23, 1, 0), False),
    ],
)
def test_datetime_range_contains_datetime_at_boundaries(
    current_datetime: datetime,
    expected: bool,
) -> None:
    datetime_range = DateTimeRange(
        start=datetime(2026, 8, 21, 18, 0),
        end=datetime(2026, 8, 22, 6, 0),
    )

    assert datetime_range.contains(current_datetime) is expected


# A range from midnight to midnight is the result of a configured date range
@pytest.mark.parametrize(
    ("current_datetime", "expected"),
    [
        (datetime(2026, 8, 20, 23, 59, 59), False),
        (datetime(2026, 8, 21, 0, 0), True),
        (datetime(2026, 8, 21, 23, 59, 59), True),
        (datetime(2026, 8, 22, 0, 0), False),
    ],
)
def test_datetime_range_from_midnight_to_midnight_covers_exactly_one_day(
    current_datetime: datetime,
    expected: bool,
) -> None:
    datetime_range = DateTimeRange(
        start=datetime(2026, 8, 21, 0, 0),
        end=datetime(2026, 8, 22, 0, 0),
    )

    assert datetime_range.contains(current_datetime) is expected


#############################################
# DateTimeCondition tests (absolute datetimes)
#############################################


def test_datetime_condition_matches_current_datetime_in_datetime_range() -> None:
    condition = DateTimeCondition(
        clock_provider=Dummy_ClockProvider(datetime(2026, 8, 21, 23, 30)),
        datetime_range=DateTimeRange(
            start=datetime(2026, 8, 21, 18, 0),
            end=datetime(2026, 8, 22, 6, 0),
        ),
    )

    assert condition.evaluate() is True


def test_datetime_condition_does_not_match_current_datetime_outside_datetime_range() -> (
    None
):
    condition = DateTimeCondition(
        clock_provider=Dummy_ClockProvider(datetime(2026, 8, 21, 12, 0)),
        datetime_range=DateTimeRange(
            start=datetime(2026, 8, 21, 18, 0),
            end=datetime(2026, 8, 22, 6, 0),
        ),
    )

    assert condition.evaluate() is False


# For an absolute range the weekday refers to the current day, unlike for a time range crossing midnight
@pytest.mark.parametrize(
    ("current_datetime", "weekday", "expected"),
    [
        (datetime(2026, 8, 21, 22, 0), Weekday.FRIDAY, True),
        (datetime(2026, 8, 21, 22, 0), Weekday.SATURDAY, False),
        (datetime(2026, 8, 22, 1, 0), Weekday.SATURDAY, True),
        (datetime(2026, 8, 22, 1, 0), Weekday.FRIDAY, False),
    ],
)
def test_datetime_condition_uses_current_weekday_for_datetime_range(
    current_datetime: datetime,
    weekday: Weekday,
    expected: bool,
) -> None:
    condition = DateTimeCondition(
        clock_provider=Dummy_ClockProvider(current_datetime),
        datetime_range=DateTimeRange(
            start=datetime(2026, 8, 21, 18, 0),
            end=datetime(2026, 8, 22, 6, 0),
        ),
        weekdays=frozenset({weekday}),
    )

    assert condition.evaluate() is expected


def test_datetime_condition_does_not_match_configured_weekday_outside_datetime_range() -> (
    None
):
    # 2026-08-28 is a Friday as well, but it is not within the range
    condition = DateTimeCondition(
        clock_provider=Dummy_ClockProvider(datetime(2026, 8, 28, 22, 0)),
        datetime_range=DateTimeRange(
            start=datetime(2026, 8, 21, 18, 0),
            end=datetime(2026, 8, 22, 6, 0),
        ),
        weekdays=frozenset({Weekday.FRIDAY}),
    )

    assert condition.evaluate() is False


def test_datetime_condition_requires_at_least_one_criterion() -> None:
    with pytest.raises(ValueError, match="at least one"):
        DateTimeCondition(
            clock_provider=Dummy_ClockProvider(datetime(2026, 8, 21, 12, 0)),
        )


#########################
# DateTimeCondition tests
#########################


def test_datetime_condition_matches_current_time_in_range() -> None:
    clock_provider = Dummy_ClockProvider(
        datetime(2026, 8, 21, 23, 30),
    )

    condition = DateTimeCondition(
        time_range=TimeRange(
            start=time(22, 0),
            end=time(6, 0),
        ),
        clock_provider=clock_provider,
    )

    assert condition.evaluate() is True


def test_datetime_condition_does_not_match_current_time_outside_range() -> None:
    clock_provider = Dummy_ClockProvider(
        datetime(2026, 8, 21, 12, 0),
    )

    condition = DateTimeCondition(
        time_range=TimeRange(
            start=time(22, 0),
            end=time(6, 0),
        ),
        clock_provider=clock_provider,
    )

    assert condition.evaluate() is False


def test_datetime_condition_matches_configured_weekday() -> None:
    clock_provider = Dummy_ClockProvider(datetime(2026, 8, 21, 12, 0))

    condition = DateTimeCondition(
        clock_provider=clock_provider,
        weekdays=frozenset({Weekday.FRIDAY}),
    )

    assert condition.evaluate() is True


def test_datetime_condition_does_not_match_unconfigured_weekday() -> None:
    clock_provider = Dummy_ClockProvider(datetime(2026, 8, 21, 12, 0))

    condition = DateTimeCondition(
        clock_provider=clock_provider,
        weekdays=frozenset({Weekday.MONDAY}),
    )

    assert condition.evaluate() is False


def test_datetime_condition_matches_one_of_multiple_weekdays() -> None:
    clock_provider = Dummy_ClockProvider(datetime(2026, 8, 21, 12, 0))

    condition = DateTimeCondition(
        clock_provider=clock_provider,
        weekdays=frozenset(
            {
                Weekday.MONDAY,
                Weekday.FRIDAY,
                Weekday.SUNDAY,
            }
        ),
    )

    assert condition.evaluate() is True


def test_datetime_condition_does_not_match_when_current_weekday_is_not_configured() -> (
    None
):
    clock_provider = Dummy_ClockProvider(datetime(2026, 8, 21, 12, 0))

    condition = DateTimeCondition(
        clock_provider=clock_provider,
        weekdays=frozenset(
            {
                Weekday.MONDAY,
                Weekday.TUESDAY,
            }
        ),
    )

    assert condition.evaluate() is False


def test_datetime_condition_matches_time_and_weekday() -> None:
    clock_provider = Dummy_ClockProvider(datetime(2026, 8, 21, 23, 30))

    condition = DateTimeCondition(
        clock_provider=clock_provider,
        time_range=TimeRange(
            start=time(22, 0),
            end=time(6, 0),
        ),
        weekdays=frozenset({Weekday.FRIDAY}),
    )

    assert condition.evaluate() is True


def test_datetime_condition_does_not_match_when_time_matches_but_weekday_does_not() -> (
    None
):
    clock_provider = Dummy_ClockProvider(datetime(2026, 8, 21, 23, 30))

    condition = DateTimeCondition(
        clock_provider=clock_provider,
        time_range=TimeRange(
            start=time(22, 0),
            end=time(6, 0),
        ),
        weekdays=frozenset({Weekday.MONDAY}),
    )

    assert condition.evaluate() is False


def test_datetime_condition_does_not_match_when_weekday_matches_but_time_does_not() -> (
    None
):
    clock_provider = Dummy_ClockProvider(datetime(2026, 8, 21, 12, 0))

    condition = DateTimeCondition(
        clock_provider=clock_provider,
        time_range=TimeRange(
            start=time(22, 0),
            end=time(6, 0),
        ),
        weekdays=frozenset({Weekday.FRIDAY}),
    )

    assert condition.evaluate() is False


# Special case: The time range crosses midnight, so the weekday refers to the day on which the range starts
def test_datetime_condition_uses_start_weekday_for_range_crossing_midnight() -> None:
    clock_provider = Dummy_ClockProvider(datetime(2026, 8, 21, 23, 30))

    condition = DateTimeCondition(
        clock_provider=clock_provider,
        time_range=TimeRange(
            start=time(22, 0),
            end=time(6, 0),
        ),
        weekdays=frozenset({Weekday.FRIDAY}),
    )

    # Friday 23:30 is at the start of the range
    assert condition.evaluate() is True

    # Saturday 01:00 belongs to the range which started on Friday
    clock_provider.now = lambda: datetime(2026, 8, 22, 1, 0)
    assert condition.evaluate() is True

    # Friday 01:00 belongs to the range which started on Thursday
    clock_provider.now = lambda: datetime(2026, 8, 21, 1, 0)
    assert condition.evaluate() is False


def test_datetime_condition_raises_error_when_no_criteria_specified() -> None:
    clock_provider = Dummy_ClockProvider(datetime(2026, 8, 21, 12, 0))

    with pytest.raises(ValueError):
        DateTimeCondition(clock_provider=clock_provider)


@pytest.mark.parametrize(
    ("current_datetime", "expected"),
    [
        # Before the start of the range on the configured weekday
        (datetime(2026, 8, 21, 21, 59, 59), False),
        # The start of the range is inclusive
        (datetime(2026, 8, 21, 22, 0), True),
        (datetime(2026, 8, 21, 23, 59, 59), True),
        # After midnight, the range still belongs to the day on which it started
        (datetime(2026, 8, 22, 0, 0), True),
        (datetime(2026, 8, 22, 5, 59, 59), True),
        # The end of the range is exclusive
        (datetime(2026, 8, 22, 6, 0), False),
        # Saturday evening starts a new range for Saturday, not for Friday
        (datetime(2026, 8, 22, 22, 0), False),
        # Early Friday belongs to the range which started on Thursday
        (datetime(2026, 8, 21, 0, 0), False),
        (datetime(2026, 8, 21, 5, 59, 59), False),
    ],
)
def test_datetime_condition_uses_start_weekday_at_range_boundaries(
    current_datetime: datetime,
    expected: bool,
) -> None:
    condition = DateTimeCondition(
        clock_provider=Dummy_ClockProvider(current_datetime),
        time_range=TimeRange(
            start=time(22, 0),
            end=time(6, 0),
        ),
        weekdays=frozenset({Weekday.FRIDAY}),
    )

    assert condition.evaluate() is expected


# A range ending exactly at midnight does not reach into the next day
@pytest.mark.parametrize(
    ("current_datetime", "expected"),
    [
        (datetime(2026, 8, 21, 23, 59, 59), True),
        (datetime(2026, 8, 22, 0, 0), False),
    ],
)
def test_datetime_condition_range_ending_at_midnight_stays_within_start_day(
    current_datetime: datetime,
    expected: bool,
) -> None:
    condition = DateTimeCondition(
        clock_provider=Dummy_ClockProvider(current_datetime),
        time_range=TimeRange(
            start=time(22, 0),
            end=time(0, 0),
        ),
        weekdays=frozenset({Weekday.FRIDAY}),
    )

    assert condition.evaluate() is expected


# A range within one day must not shift the weekday
@pytest.mark.parametrize(
    ("weekday", "expected"),
    [
        (Weekday.FRIDAY, True),
        (Weekday.THURSDAY, False),
    ],
)
def test_datetime_condition_does_not_shift_weekday_for_range_within_one_day(
    weekday: Weekday,
    expected: bool,
) -> None:
    condition = DateTimeCondition(
        clock_provider=Dummy_ClockProvider(datetime(2026, 8, 21, 12, 0)),
        time_range=TimeRange(
            start=time(10, 0),
            end=time(18, 0),
        ),
        weekdays=frozenset({weekday}),
    )

    assert condition.evaluate() is expected


##################################
# DateTimeCondition tests (months)
##################################


def test_datetime_condition_matches_configured_month() -> None:
    condition = DateTimeCondition(
        clock_provider=Dummy_ClockProvider(datetime(2026, 8, 21, 12, 0)),
        months=frozenset({Month.AUGUST}),
    )

    assert condition.evaluate() is True


def test_datetime_condition_does_not_match_unconfigured_month() -> None:
    condition = DateTimeCondition(
        clock_provider=Dummy_ClockProvider(datetime(2026, 8, 21, 12, 0)),
        months=frozenset({Month.SEPTEMBER}),
    )

    assert condition.evaluate() is False


def test_datetime_condition_matches_one_of_multiple_months() -> None:
    condition = DateTimeCondition(
        clock_provider=Dummy_ClockProvider(datetime(2026, 8, 21, 12, 0)),
        months=frozenset({Month.JULY, Month.AUGUST, Month.SEPTEMBER}),
    )

    assert condition.evaluate() is True


@pytest.mark.parametrize(
    ("current_datetime", "expected"),
    [
        # The last moment of the previous month
        (datetime(2026, 7, 31, 23, 59, 59), False),
        # The first moment of the month
        (datetime(2026, 8, 1, 0, 0), True),
        # The last moment of the month
        (datetime(2026, 8, 31, 23, 59, 59), True),
        # The first moment of the next month
        (datetime(2026, 9, 1, 0, 0), False),
    ],
)
def test_datetime_condition_month_boundaries(
    current_datetime: datetime,
    expected: bool,
) -> None:
    condition = DateTimeCondition(
        clock_provider=Dummy_ClockProvider(current_datetime),
        months=frozenset({Month.AUGUST}),
    )

    assert condition.evaluate() is expected


# Every month number has to be mapped to the correct month
@pytest.mark.parametrize(("month_number", "month"), list(enumerate(Month, start=1)))
def test_datetime_condition_maps_every_month_number_to_its_month(
    month_number: int,
    month: Month,
) -> None:
    clock_provider = Dummy_ClockProvider(datetime(2026, month_number, 15, 12, 0))

    matching_condition = DateTimeCondition(
        clock_provider=clock_provider,
        months=frozenset({month}),
    )
    other_months_condition = DateTimeCondition(
        clock_provider=clock_provider,
        months=frozenset(set(Month) - {month}),
    )

    assert matching_condition.evaluate() is True
    assert other_months_condition.evaluate() is False


# 2026-08-21 is a Friday
@pytest.mark.parametrize(
    ("weekday", "month", "expected"),
    [
        (Weekday.FRIDAY, Month.AUGUST, True),
        (Weekday.FRIDAY, Month.SEPTEMBER, False),
        (Weekday.SATURDAY, Month.AUGUST, False),
    ],
)
def test_datetime_condition_requires_weekday_and_month_to_match(
    weekday: Weekday,
    month: Month,
    expected: bool,
) -> None:
    condition = DateTimeCondition(
        clock_provider=Dummy_ClockProvider(datetime(2026, 8, 21, 12, 0)),
        weekdays=frozenset({weekday}),
        months=frozenset({month}),
    )

    assert condition.evaluate() is expected


# For a time range crossing midnight the month refers to the day on which the range starts
@pytest.mark.parametrize(
    ("current_datetime", "expected"),
    [
        # Start of the range on the last day of December
        (datetime(2026, 12, 31, 23, 30), True),
        # After midnight the range still belongs to December 31
        (datetime(2027, 1, 1, 1, 0), True),
        # After midnight the range belongs to November 30 (the range started in November)
        (datetime(2026, 12, 1, 0, 30), False),
        # Range which starts on the first day of December
        (datetime(2026, 12, 1, 23, 30), True),
        # Range which starts on the first day of January
        (datetime(2027, 1, 1, 23, 30), False),
    ],
)
def test_datetime_condition_uses_start_month_for_range_crossing_midnight(
    current_datetime: datetime,
    expected: bool,
) -> None:
    condition = DateTimeCondition(
        clock_provider=Dummy_ClockProvider(current_datetime),
        time_range=TimeRange(
            start=time(23, 0),
            end=time(1, 30),
        ),
        months=frozenset({Month.DECEMBER}),
    )

    assert condition.evaluate() is expected


# For an absolute range the month refers to the current day
@pytest.mark.parametrize(
    ("current_datetime", "expected"),
    [
        (datetime(2026, 11, 30, 23, 30), False),
        (datetime(2026, 12, 1, 1, 0), True),
    ],
)
def test_datetime_condition_uses_current_month_for_datetime_range(
    current_datetime: datetime,
    expected: bool,
) -> None:
    condition = DateTimeCondition(
        clock_provider=Dummy_ClockProvider(current_datetime),
        datetime_range=DateTimeRange(
            start=datetime(2026, 11, 30, 23, 0),
            end=datetime(2026, 12, 1, 2, 0),
        ),
        months=frozenset({Month.DECEMBER}),
    )

    assert condition.evaluate() is expected
