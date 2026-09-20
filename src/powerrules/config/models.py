import re
from datetime import date, datetime, time
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    StrictBool,
    Tag,
    field_validator,
    model_validator,
)

from powerrules.conditions.datetime import Weekday
from powerrules.conditions.matcher import MatchType

_DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_DATETIME_PATTERN = re.compile(r"(?P<date>[0-9]{4}-[0-9]{2}-[0-9]{2})[ T](?P<time>.+)")
_TIMEZONE_SUFFIX_PATTERN = re.compile(r"(?:[Zz]|[+-][0-9]{2}(?::?[0-9]{2})?)$")


class MatchConfiguration(BaseModel):
    """Configuration for a match configuration."""

    model_config = ConfigDict(extra="forbid")

    type: MatchType = MatchType.EXACT
    case_sensitive: bool = True


class ProcessConditionConfiguration(BaseModel):
    """Configuration for a process condition."""

    model_config = ConfigDict(extra="forbid")

    name: str
    exists: StrictBool
    match: MatchConfiguration = Field(default_factory=MatchConfiguration)


def _get_value_kind(value: object) -> Literal["date", "time", "datetime"] | None:
    """Determine which kind of range boundary a raw configured value looks like.

    Args:
        value: Raw configured 'start' or 'end' value.

    Returns:
        The kind of the value, or None if the value is missing.
    """
    if value is None:
        return None

    # A datetime is also a date, so it has to be checked first
    if isinstance(value, datetime):
        return "datetime"

    if isinstance(value, date):
        return "date"

    # Only absolute values contain a dash, a time of day never does
    if isinstance(value, str) and "-" in value:
        # A date with a time is separated by a space or a "T"
        return "datetime" if " " in value or "T" in value else "date"

    # Everything else is validated (and rejected if invalid) as a time of day
    return "time"


def _get_between_tag(value: object) -> Literal["date", "time", "datetime"] | None:
    """Determine which 'between' variant a configured value belongs to.

    Args:
        value: Raw configured value or an already built configuration object.

    Returns:
        The tag of the matching variant, or None if 'start' and 'end' are of
        different kinds or the value is not a mapping.

    """
    if isinstance(value, DateRangeConfiguration):
        return "date"

    if isinstance(value, TimeRangeConfiguration):
        return "time"

    if isinstance(value, DateTimeRangeConfiguration):
        return "datetime"

    if not isinstance(value, dict):
        return None

    kinds: set[Literal["date", "time", "datetime"]] = {
        kind
        for kind in (
            _get_value_kind(value.get("start")),
            _get_value_kind(value.get("end")),
        )
        if kind is not None
    }

    # A missing boundary is reported by the selected variant, mixed kinds are not
    return kinds.pop() if len(kinds) == 1 else None


class DateRangeConfiguration(BaseModel):
    """Configuration for an absolute date range. The start date is inclusive and the end date is exclusive."""

    model_config = ConfigDict(extra="forbid")

    start: date
    end: date

    @field_validator("start", "end", mode="before")
    @classmethod
    def validate_date(cls, value: object) -> date:
        """Validate and parse a configured date value.

        Args:
            value: Value to validate and parse.

        Returns:
            Parsed date value.
        """
        return _parse_date(value)

    @model_validator(mode="after")
    def validate_order(self) -> "DateRangeConfiguration":
        """Validate that the range ends after it starts.

        Returns:
            The validated configuration.

        Raises:
            ValueError: If the end date is not after the start date.
        """
        if self.start >= self.end:
            raise ValueError("'end' must be after 'start' (the end is exclusive)")

        return self


class TimeRangeConfiguration(BaseModel):
    """Configuration for a time range. The start time is inclusive and the end time is exclusive."""

    model_config = ConfigDict(extra="forbid")

    start: time
    end: time

    @field_validator("start", "end", mode="before")
    @classmethod
    def validate_time(cls, value: object) -> time:
        """Validate and parse a configured time value.

        Args:
            value: Value to validate and parse.

        Returns:
            Parsed time value.
        """
        return _parse_time(value)


class DateTimeRangeConfiguration(BaseModel):
    """Configuration for an absolute datetime range without timezone. The start datetime is inclusive and the end datetime is exclusive."""

    model_config = ConfigDict(extra="forbid")

    start: datetime
    end: datetime

    @field_validator("start", "end", mode="before")
    @classmethod
    def validate_datetime(cls, value: object) -> datetime:
        """Validate and parse a configured datetime value.

        Args:
            value: Value to validate and parse.

        Returns:
            Parsed datetime value.
        """
        return _parse_datetime(value)

    @model_validator(mode="after")
    def validate_order(self) -> "DateTimeRangeConfiguration":
        """Validate that the range ends after it starts.

        Returns:
            The validated configuration.

        Raises:
            ValueError: If the end is not after the start.
        """
        if self.start >= self.end:
            raise ValueError("'end' must be after 'start' (the end is exclusive)")

        return self


# Dynamicly decide which variant of 'between' to use
BetweenConfiguration = Annotated[
    Annotated[DateRangeConfiguration, Tag("date")]
    | Annotated[TimeRangeConfiguration, Tag("time")]
    | Annotated[DateTimeRangeConfiguration, Tag("datetime")],
    Discriminator(
        _get_between_tag,
        custom_error_type="invalid_between",
        custom_error_message="'between' must define 'start' and 'end' either both as absolute date, both as time of day or both as absolute date with time",
    ),
]


class DateTimeConditionConfiguration(BaseModel):
    """Configuration for a datetime condition."""

    model_config = ConfigDict(extra="forbid")

    between: BetweenConfiguration | None = None
    weekday: list[Weekday] | None = None

    @model_validator(mode="after")
    def validate_criteria(self) -> "DateTimeConditionConfiguration":
        """Validate that at least one datetime criterion is configured."""
        if self.between is None and self.weekday is None:
            raise ValueError(
                "A datetime condition must define at least one criterion of 'between' or 'weekday'"
            )

        return self

    @field_validator("weekday")
    @classmethod
    def validate_weekday_not_empty(
        cls, value: list[Weekday] | None
    ) -> list[Weekday] | None:
        """Validate that the configured weekday list is not empty."""
        if value is not None and len(value) == 0:
            raise ValueError("The 'weekday' list must contain at least one weekday")

        return value


class WindowConditionConfiguration(BaseModel):
    """Configuration for a window condition."""

    model_config = ConfigDict(extra="forbid")

    title: str
    exists: StrictBool
    match: MatchConfiguration = Field(default_factory=MatchConfiguration)


class ConditionConfiguration(BaseModel):
    """Configuration for a condition tree."""

    model_config = ConfigDict(
        extra="forbid",
        validate_by_name=True,
    )

    and_conditions: list["ConditionConfiguration"] | None = Field(
        default=None,
        validation_alias="and",
        serialization_alias="and",
    )
    or_conditions: list["ConditionConfiguration"] | None = Field(
        default=None,
        validation_alias="or",
        serialization_alias="or",
    )
    not_condition: "ConditionConfiguration | None" = Field(
        default=None,
        validation_alias="not",
        serialization_alias="not",
    )
    process: ProcessConditionConfiguration | None = None
    datetime: DateTimeConditionConfiguration | None = None
    window: WindowConditionConfiguration | None = None

    @model_validator(mode="after")
    def validate_variant(self) -> "ConditionConfiguration":
        configured_variants = sum(
            value is not None
            for value in (
                self.and_conditions,
                self.or_conditions,
                self.not_condition,
                self.process,
                self.datetime,
                self.window,
            )
        )

        if configured_variants != 1:
            raise ValueError(
                "A condition must define exactly one of 'and', 'or', 'not', 'process', 'datetime' or 'window'"
            )

        if self.and_conditions is not None and len(self.and_conditions) < 2:
            raise ValueError("An 'and' condition must contain at least two conditions")

        if self.or_conditions is not None and len(self.or_conditions) < 2:
            raise ValueError("An 'or' condition must contain at least two conditions")

        return self


class ActionConfiguration(BaseModel):
    """Configuration for an action."""

    model_config = ConfigDict(extra="forbid")

    type: Literal[
        "shutdown",
        "sleep",
        "hibernate",
        "reboot",
    ]


class RuleConfiguration(BaseModel):
    """Configuration for a single rule."""

    model_config = ConfigDict(extra="forbid")

    name: str
    enabled: StrictBool = True
    conditions: ConditionConfiguration
    action: ActionConfiguration


class RuleSetConfiguration(BaseModel):
    """PowerRules YAML configuration."""

    model_config = ConfigDict(extra="forbid")

    rules: list[RuleConfiguration]


def _parse_date(value: object) -> date:
    """Parse a supported date configuration value.

    The supported format is YYYY-MM-DD.

    Args:
        value: Value to parse.

    Returns:
        Parsed date value.

    Raises:
        ValueError: If the value is not a supported date format.
    """
    # A datetime is also a date, but a date without a time is required here
    if isinstance(value, datetime):
        raise ValueError("Date value must not contain a time")

    if isinstance(value, date):
        return value

    if not isinstance(value, str):
        raise ValueError("Date value must be a string")

    if not _DATE_PATTERN.fullmatch(value):
        raise ValueError(f"Invalid date format '{value}', expected YYYY-MM-DD")

    try:
        return date.fromisoformat(value)
    except ValueError as e:
        raise ValueError(f"Invalid date value '{value}'") from e


def _parse_time(value: object) -> time:
    """Parse a supported time configuration value.

    Supported formats are H, HH, H:MM, HH:MM, H:MM:SS, and HH:MM:SS.

    Args:
        value: Value to parse.

    Returns:
        Parsed time value.

    Raises:
        ValueError: If the value is not a supported time format.
    """
    if isinstance(value, time):
        return value

    if not isinstance(value, str):
        raise ValueError("Time value must be a string")

    parts = value.split(":")

    if not 1 <= len(parts) <= 3:
        raise ValueError(f"Invalid time format '{value}', expected H, H:MM, or H:MM:SS")

    if not all(part.isdigit() for part in parts):
        raise ValueError(f"Invalid time format '{value}', expected H, H:MM, or H:MM:SS")

    hour = parts[0]

    if not 1 <= len(hour) <= 2:
        raise ValueError(f"Invalid hour format '{hour}', expected H or HH")

    if len(parts) > 1 and len(parts[1]) != 2:
        raise ValueError(f"Invalid minute format '{parts[1]}', expected MM")

    if len(parts) > 2 and len(parts[2]) != 2:
        raise ValueError(f"Invalid second format '{parts[2]}', expected SS")

    try:
        return time(
            hour=int(hour),
            minute=int(parts[1]) if len(parts) > 1 else 0,
            second=int(parts[2]) if len(parts) > 2 else 0,
        )
    except ValueError as e:
        raise ValueError(f"Invalid time value '{value}'") from e


def _parse_datetime(value: object) -> datetime:
    """Parse a supported datetime configuration value.

    The supported format is YYYY-MM-DD followed by a space or a "T" and a time
    (H, HH, H:MM, HH:MM, H:MM:SS, or HH:MM:SS). Timezone information is not supported.

    Args:
        value: Value to parse.

    Returns:
        Parsed naive datetime value.

    Raises:
        ValueError: If the value is not a supported datetime format.
    """
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            raise ValueError(
                "Timezone-aware datetimes are not supported, use local time without timezone"
            )

        return value

    # A plain date does not contain the required time
    if isinstance(value, date):
        raise ValueError("Datetime value must contain a time")

    if not isinstance(value, str):
        raise ValueError("Datetime value must be a string")

    parts = _DATETIME_PATTERN.fullmatch(value)

    if parts is None:
        raise ValueError(
            f"Invalid datetime format '{value}', expected YYYY-MM-DD followed by H, H:MM, or H:MM:SS"
        )

    time_part = parts["time"]

    if _TIMEZONE_SUFFIX_PATTERN.search(time_part):
        raise ValueError(
            f"Timezone information is not supported in '{value}', use local time without offset"
        )

    return datetime.combine(_parse_date(parts["date"]), _parse_time(time_part))
