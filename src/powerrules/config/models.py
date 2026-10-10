import re
from datetime import date, datetime, time
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    Tag,
    ValidationInfo,
    field_validator,
    model_validator,
)

from powerrules.actions.command import (
    DEFAULT_ACTION_TIMEOUT_SECONDS,
    RESERVED_ENVIRONMENT_PREFIX,
)
from powerrules.conditions.datetime import Month, Weekday
from powerrules.conditions.matcher import MatchType
from powerrules.providers.command import Shell

EnumType = TypeVar("EnumType", bound=StrEnum)

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
    month: list[Month] | None = None

    @field_validator("weekday", "month", mode="before")
    @classmethod
    def validate_names_case_insensitive(
        cls,
        value: object,
        info: ValidationInfo,
    ) -> object:
        """Match the configured weekday or month names regardless of their case.

        Args:
            value: Configured weekday or month names.
            info: Validation information containing the name of the field.

        Returns:
            The value with all matching names replaced by their weekday or month.
            Anything else is returned unchanged, so it is rejected by the regular validation.
        """
        if not isinstance(value, list):
            return value

        enum_type = Weekday if info.field_name == "weekday" else Month

        return [_match_enum_case_insensitive(enum_type, item) for item in value]

    @field_validator("weekday", "month")
    @classmethod
    def validate_list_not_empty(
        cls,
        value: list[Weekday] | list[Month] | None,
        info: ValidationInfo,
    ) -> list[Weekday] | list[Month] | None:
        """Validate that a configured weekday or month list is not empty.

        Args:
            value: Configured weekdays or months, or None if not configured.
            info: Validation information containing the name of the field.

        Returns:
            The validated list.

        Raises:
            ValueError: If the list is empty.
        """
        if value is not None and len(value) == 0:
            raise ValueError(
                f"The '{info.field_name}' list must contain at least one {info.field_name}"
            )

        return value

    @model_validator(mode="after")
    def validate_criteria(self) -> "DateTimeConditionConfiguration":
        """Validate that at least one datetime criterion is configured.

        Returns:
            The validated configuration.

        Raises:
            ValueError: If none of 'between', 'weekday' and 'month' is configured.
        """
        if self.between is None and self.weekday is None and self.month is None:
            raise ValueError(
                "A datetime condition must define at least one criterion of 'between', 'weekday' or 'month'"
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
    """Configuration for an action which runs a command.

    Unset optional values fall back to their defaults when the action is built.
    For example, the default shell depends on the operating system.
    """

    model_config = ConfigDict(extra="forbid")

    run: str
    name: str | None = None
    shell: Shell | None = None
    working_directory: Path | None = None
    # The values may be secrets, so they are excluded from the representation of the model
    env: dict[str, str] = Field(default_factory=dict, repr=False)
    # None means that the command may run without a time limit
    timeout: StrictInt | StrictFloat | None = DEFAULT_ACTION_TIMEOUT_SECONDS
    success_exit_codes: list[StrictInt] = Field(
        default_factory=lambda: [0], min_length=1
    )
    wait: StrictBool = True
    continue_on_error: StrictBool = False

    @field_validator("run", "name")
    @classmethod
    def validate_not_blank(cls, value: str | None, info: ValidationInfo) -> str | None:
        """Validate that a configured text is not empty or whitespace only.

        Args:
            value: Configured text, or None if not configured.
            info: Validation information containing the name of the field.

        Returns:
            The validated text.

        Raises:
            ValueError: If the text is blank.
        """
        if value is not None and not value.strip():
            raise ValueError(f"The '{info.field_name}' value must not be blank")

        return value

    @field_validator("working_directory", mode="before")
    @classmethod
    def validate_working_directory_not_blank(cls, value: object) -> object:
        """Validate that a configured working directory is not blank.

        An empty string would otherwise silently become the current directory.

        Args:
            value: Configured working directory.

        Returns:
            The unchanged value, so the regular validation converts it to a path.

        Raises:
            ValueError: If the working directory is a blank string.
        """
        if isinstance(value, str) and not value.strip():
            raise ValueError("The 'working_directory' value must not be blank")

        return value

    @field_validator("env", mode="before")
    @classmethod
    def convert_environment_values_to_strings(cls, value: object) -> object:
        """Convert numbers and booleans of the environment variables to strings.

        YAML turns an unquoted value like 1 or true into a number or boolean, but environment variables are always strings.

        Args:
            value: Configured environment variables.

        Returns:
            The variables with converted values. Anything else is returned unchanged, so it is rejected by the regular validation.
        """
        if not isinstance(value, dict):
            return value

        return {
            variable_name: _convert_environment_value(variable_value)
            for variable_name, variable_value in value.items()
        }

    @field_validator("env")
    @classmethod
    def validate_environment_names(cls, value: dict[str, str]) -> dict[str, str]:
        """Validate the names of the environment variables.

        Args:
            value: Configured environment variables.

        Returns:
            The validated environment variables.

        Raises:
            ValueError: If a name is empty, contains "=" or uses the reserved prefix.
        """
        for variable_name in value:
            if not variable_name or "=" in variable_name:
                raise ValueError(
                    f"Invalid environment variable name '{variable_name}', it must not be empty or contain '='"
                )

            # Environment variable names are case-insensitive on Windows
            if variable_name.upper().startswith(RESERVED_ENVIRONMENT_PREFIX):
                raise ValueError(
                    f"The environment variable '{variable_name}' is reserved, names starting with '{RESERVED_ENVIRONMENT_PREFIX}' are set by PowerRules"
                )

        return value

    @field_validator("timeout")
    @classmethod
    def validate_timeout(cls, value: float | None) -> float | None:
        """Validate that the timeout is positive.

        Args:
            value: Configured timeout in seconds, or None for no time limit.

        Returns:
            The validated timeout.

        Raises:
            ValueError: If the timeout is not greater than zero.
        """
        # "not value > 0" also rejects NaN
        if value is not None and not value > 0:
            raise ValueError(
                "'timeout' must be greater than zero (use null for no time limit)"
            )

        return value

    @model_validator(mode="after")
    def validate_background_options(self) -> "ActionConfiguration":
        """Validate that options which need a finished command are not combined with 'wait: false'.

        Without waiting there is neither an exit code nor a point in time at which the timeout could apply.
        Only explicitly configured options are rejected, not the defaults.

        Returns:
            The validated configuration.

        Raises:
            ValueError: If 'timeout' or 'success_exit_codes' is configured together with 'wait: false'.
        """
        if self.wait:
            return self

        conflicting_options = sorted(
            {"timeout", "success_exit_codes"} & self.model_fields_set
        )

        if conflicting_options:
            option_names = ", ".join(f"'{name}'" for name in conflicting_options)

            raise ValueError(
                f"{option_names} cannot be combined with 'wait: false' because the command is not waited for"
            )

        return self


class RuleConfiguration(BaseModel):
    """Configuration for a single rule."""

    model_config = ConfigDict(extra="forbid")

    name: str
    enabled: StrictBool = True
    conditions: ConditionConfiguration
    actions: list[ActionConfiguration] = Field(min_length=1)


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


def _match_enum_case_insensitive(enum_type: type[EnumType], value: object) -> object:
    """Find the enum member whose value matches the given value regardless of case.

    Args:
        enum_type: Enum whose members are compared.
        value: Value to match.

    Returns:
        The matching enum member. If nothing matches, the value is returned
        unchanged, so the regular validation reports the error including the valid values.
    """
    if not isinstance(value, str):
        return value

    for member in enum_type:
        if member.value.casefold() == value.casefold():
            return member

    return value


def _convert_environment_value(value: object) -> object:
    """Convert a number or boolean of an environment variable to its string form.

    Booleans use the YAML spelling ("true" and "false") instead of the Python one.

    Args:
        value: Configured value of an environment variable.

    Returns:
        The converted string, or the unchanged value if it is neither a number nor a boolean.
    """
    # A bool is also an int, so it has to be checked first
    if isinstance(value, bool):
        return "true" if value else "false"

    if isinstance(value, int | float):
        return str(value)

    return value
