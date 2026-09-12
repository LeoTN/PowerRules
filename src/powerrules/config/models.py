from datetime import time
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)

from powerrules.conditions.datetime import Weekday
from powerrules.conditions.matcher import MatchType


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


class TimeRangeConfiguration(BaseModel):
    """Configuration for a datetime range."""

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


class DateTimeConditionConfiguration(BaseModel):
    """Configuration for a datetime condition."""

    model_config = ConfigDict(extra="forbid")

    between: TimeRangeConfiguration | None = None
    weekday: list[Weekday] | None = None

    @model_validator(mode="after")
    def validate_variant(self) -> "DateTimeConditionConfiguration":
        """Validate that exactly one datetime variant is configured.

        Returns:
            The validated configuration.

        Raises:
            ValueError: If zero or multiple variants are configured.
        """
        configured_variants = sum(
            value is not None
            for value in (
                self.between,
                self.weekday,
            )
        )

        if configured_variants != 1:
            raise ValueError(
                "A datetime condition must define exactly one of 'between' or 'weekday'"
            )

        return self


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
