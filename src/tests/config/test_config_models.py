from datetime import UTC, date, datetime, time
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from powerrules.actions.command import DEFAULT_COMMAND_TIMEOUT_SECONDS
from powerrules.conditions.datetime import Month, Weekday
from powerrules.conditions.matcher import MatchType
from powerrules.config.models import (
    ActionConfiguration,
    CommandConditionConfiguration,
    ConditionConfiguration,
    DateRangeConfiguration,
    DateTimeConditionConfiguration,
    DateTimeRangeConfiguration,
    OutputMatchConfiguration,
    RuleConfiguration,
    RuleSetConfiguration,
    TimeRangeConfiguration,
)
from powerrules.providers.command import Shell
from tests.factories import (
    make_action_configuration,
    make_rule_data,
    make_trusted_files_rule_data,
)
from tests.helpers import BACKUP_SCRIPT_NAME, SCRIPT_DIRECTORY_NAME


def test_rule_set_configuration_accepts_valid_rule() -> None:
    configuration = RuleSetConfiguration.model_validate(
        {
            "rules": [
                {
                    "name": "Shutdown after backup test rule",
                    "conditions": {
                        "and": [
                            {
                                "process": {
                                    "name": "backup.exe",
                                    "exists": False,
                                }
                            },
                            {
                                "datetime": {
                                    "between": {
                                        "start": "23:00",
                                        "end": "6:00",
                                    }
                                }
                            },
                        ]
                    },
                    "actions": [{"run": "shutdown /s /t 0"}],
                }
            ]
        }
    )

    assert len(configuration.rules) == 1
    assert configuration.rules[0].name == "Shutdown after backup test rule"
    assert configuration.rules[0].enabled is True
    assert [action.run for action in configuration.rules[0].actions] == [
        "shutdown /s /t 0"
    ]


def test_rule_set_configuration_accepts_empty_rule_list() -> None:
    assert RuleSetConfiguration.model_validate({"rules": []}).rules == []


#################
# Condition tests
#################


def test_and_condition_requires_at_least_two_conditions() -> None:
    with pytest.raises(ValidationError, match="at least two conditions"):
        RuleSetConfiguration.model_validate(
            {
                "rules": [
                    make_rule_data(
                        conditions={
                            "and": [
                                {
                                    "process": {
                                        "name": "backup.exe",
                                        "exists": False,
                                    }
                                    # Missing second condition
                                }
                            ]
                        }
                    )
                ]
            }
        )


def test_or_condition_requires_at_least_two_conditions() -> None:
    with pytest.raises(ValidationError, match="at least two conditions"):
        RuleSetConfiguration.model_validate(
            {
                "rules": [
                    make_rule_data(
                        conditions={
                            "or": [{"process": {"name": "backup.exe", "exists": False}}]
                        }
                    )
                ]
            }
        )


def test_not_condition_accepts_single_condition() -> None:
    configuration = RuleSetConfiguration.model_validate(
        {
            "rules": [
                make_rule_data(
                    conditions={
                        "not": {
                            "process": {
                                "name": "backup.exe",
                                "exists": True,
                            }
                        }
                    }
                )
            ]
        }
    )

    assert configuration.rules[0].conditions.not_condition is not None


@pytest.mark.parametrize(
    "conditions",
    [
        {},
        {
            "process": {"name": "backup.exe", "exists": False},
            "datetime": {"weekday": ["Monday"]},
        },
    ],
)
def test_condition_must_define_exactly_one_variant(
    conditions: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match="must define exactly one of"):
        RuleConfiguration.model_validate(make_rule_data(conditions=conditions))


############
# Rule tests
############


def test_rule_configuration_keeps_actions_in_configured_order() -> None:
    rule = RuleConfiguration.model_validate(
        make_rule_data(actions=[{"run": "first"}, {"run": "second"}, {"run": "third"}])
    )

    assert [action.run for action in rule.actions] == ["first", "second", "third"]


def test_rule_configuration_rejects_empty_action_list() -> None:
    with pytest.raises(ValidationError, match="at least 1 item"):
        RuleConfiguration.model_validate(make_rule_data(actions=[]))


def test_rule_configuration_rejects_missing_actions() -> None:
    data = make_rule_data()
    del data["actions"]

    with pytest.raises(ValidationError, match="Field required"):
        RuleConfiguration.model_validate(data)


# Guards against the former single "action" with a type
def test_rule_configuration_rejects_former_single_action() -> None:
    data = make_rule_data(action={"type": "shutdown"})
    del data["actions"]

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        RuleConfiguration.model_validate(data)


def test_rule_configuration_rejects_non_boolean_enabled() -> None:
    with pytest.raises(ValidationError, match="valid boolean"):
        RuleConfiguration.model_validate(make_rule_data(enabled="false"))


#################################
# ActionConfiguration basic tests
#################################


def test_action_configuration_uses_defaults() -> None:
    action = make_action_configuration()

    assert action.run == "echo test"
    assert action.name is None
    assert action.shell is None
    assert action.working_directory is None
    assert action.env == {}
    assert action.timeout == DEFAULT_COMMAND_TIMEOUT_SECONDS
    assert action.success_exit_codes == [0]
    assert action.wait is True
    assert action.continue_on_error is False


def test_action_configuration_does_not_share_mutable_defaults() -> None:
    first_action = make_action_configuration()
    first_action.env["KEY"] = "value"
    first_action.success_exit_codes.append(1)

    second_action = make_action_configuration()

    assert second_action.env == {}
    assert second_action.success_exit_codes == [0]


def test_action_configuration_accepts_all_options() -> None:
    action = make_action_configuration(
        run=BACKUP_SCRIPT_NAME,
        name="Backup",
        shell="bash",
        working_directory=SCRIPT_DIRECTORY_NAME,
        env={"KEY": "value"},
        timeout=2.5,
        success_exit_codes=[0, 3],
        wait=True,
        continue_on_error=True,
    )

    assert action.run == BACKUP_SCRIPT_NAME
    assert action.name == "Backup"
    assert action.shell is Shell.BASH
    assert action.working_directory == Path(SCRIPT_DIRECTORY_NAME)
    assert action.env == {"KEY": "value"}
    assert action.timeout == 2.5
    assert action.success_exit_codes == [0, 3]
    assert action.wait is True
    assert action.continue_on_error is True


def test_action_configuration_requires_run() -> None:
    with pytest.raises(ValidationError, match="Field required"):
        ActionConfiguration.model_validate({})


def test_action_configuration_rejects_former_type_field() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ActionConfiguration.model_validate({"type": "shutdown"})


def test_action_configuration_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        make_action_configuration(unknown=True)


def test_action_configuration_keeps_multiline_command_unchanged() -> None:
    command = "  echo one\necho two\n"

    assert make_action_configuration(run=command).run == command


################################
# ActionConfiguration text tests
################################


@pytest.mark.parametrize("field", ["run", "name"])
@pytest.mark.parametrize("value", ["", " ", "\n\t"])
def test_action_configuration_rejects_blank_text(field: str, value: str) -> None:
    with pytest.raises(ValidationError, match=f"The '{field}' value must not be blank"):
        make_action_configuration(**{field: value})


def test_action_configuration_accepts_explicit_none_name() -> None:
    assert make_action_configuration(name=None).name is None


@pytest.mark.parametrize("shell", list(Shell))
def test_action_configuration_accepts_every_shell(shell: Shell) -> None:
    assert make_action_configuration(shell=shell.value).shell is shell


@pytest.mark.parametrize("shell", ["zsh", "BASH", ""])
def test_action_configuration_rejects_unknown_shell(shell: str) -> None:
    with pytest.raises(ValidationError, match="Input should be"):
        make_action_configuration(shell=shell)


def test_action_configuration_converts_working_directory_to_path() -> None:
    action = make_action_configuration(working_directory="scripts/nightly")

    assert action.working_directory == Path("scripts/nightly")


@pytest.mark.parametrize("working_directory", ["", "  "])
def test_action_configuration_rejects_blank_working_directory(
    working_directory: str,
) -> None:
    with pytest.raises(
        ValidationError, match="The 'working_directory' value must not be blank"
    ):
        make_action_configuration(working_directory=working_directory)


###############################
# ActionConfiguration env tests
###############################


# YAML turns unquoted values into numbers and booleans, environment variables are always strings
def test_action_configuration_converts_environment_values_to_strings() -> None:
    action = make_action_configuration(
        env={
            "TEXT": "value",
            "INTEGER": 3,
            "FLOAT": 1.5,
            "TRUE": True,
            "FALSE": False,
        }
    )

    assert action.env == {
        "TEXT": "value",
        "INTEGER": "3",
        "FLOAT": "1.5",
        "TRUE": "true",
        "FALSE": "false",
    }


@pytest.mark.parametrize("name", ["", "A=B", "=A"])
def test_action_configuration_rejects_invalid_environment_names(name: str) -> None:
    with pytest.raises(ValidationError, match="Invalid environment variable name"):
        make_action_configuration(env={name: "value"})


@pytest.mark.parametrize(
    "name",
    ["POWERRULES_CUSTOM", "powerrules_custom", "PowerRules_Rule_Name"],
)
def test_action_configuration_rejects_reserved_environment_names(name: str) -> None:
    with pytest.raises(ValidationError, match="is reserved"):
        make_action_configuration(env={name: "value"})


@pytest.mark.parametrize("value", [None, ["a"], {"a": "b"}])
def test_action_configuration_rejects_unsupported_environment_values(
    value: object,
) -> None:
    with pytest.raises(ValidationError, match="valid string"):
        make_action_configuration(env={"KEY": value})


@pytest.mark.parametrize("env", ["KEY=value", ["KEY=value"]])
def test_action_configuration_rejects_environment_which_is_not_a_mapping(
    env: object,
) -> None:
    with pytest.raises(ValidationError, match="valid dictionary"):
        make_action_configuration(env=env)


def test_action_configuration_hides_environment_values_in_representation() -> None:
    action = make_action_configuration(env={"TOKEN": "super-secret"})

    assert "super-secret" not in repr(action)


###################################
# ActionConfiguration timeout tests
###################################


@pytest.mark.parametrize("timeout", [30, 2.5, 0.001, None])
def test_action_configuration_accepts_timeout(timeout: float | None) -> None:
    assert make_action_configuration(timeout=timeout).timeout == timeout


@pytest.mark.parametrize("timeout", [0, -1, -0.5, float("nan"), float("-inf")])
def test_action_configuration_rejects_non_positive_timeout(timeout: float) -> None:
    with pytest.raises(ValidationError, match="'timeout' must be greater than zero"):
        make_action_configuration(timeout=timeout)


@pytest.mark.parametrize("timeout", ["5", "none", [5]])
def test_action_configuration_rejects_non_numeric_timeout(timeout: object) -> None:
    with pytest.raises(ValidationError):
        make_action_configuration(timeout=timeout)


##############################################
# ActionConfiguration exit code and flag tests
##############################################


@pytest.mark.parametrize("exit_codes", [[0], [0, 3], [-1], [255]])
def test_action_configuration_accepts_success_exit_codes(
    exit_codes: list[int],
) -> None:
    action = make_action_configuration(success_exit_codes=exit_codes)

    assert action.success_exit_codes == exit_codes


def test_action_configuration_rejects_empty_success_exit_codes() -> None:
    with pytest.raises(ValidationError, match="at least 1 item"):
        make_action_configuration(success_exit_codes=[])


@pytest.mark.parametrize("exit_codes", [["0"], [1.5], 0])
def test_action_configuration_rejects_invalid_success_exit_codes(
    exit_codes: object,
) -> None:
    with pytest.raises(ValidationError):
        make_action_configuration(success_exit_codes=exit_codes)


@pytest.mark.parametrize("field", ["wait", "continue_on_error"])
@pytest.mark.parametrize("value", ["true", "false", "yes", 1, 0])
def test_action_configuration_rejects_non_boolean_flags(
    field: str, value: object
) -> None:
    with pytest.raises(ValidationError, match="valid boolean"):
        make_action_configuration(**{field: value})


######################################
# ActionConfiguration background tests
######################################


def test_action_configuration_accepts_background_action_without_other_options() -> None:
    action = make_action_configuration(wait=False)

    assert action.wait is False


def test_action_configuration_accepts_waiting_action_with_all_waiting_options() -> None:
    action = make_action_configuration(wait=True, timeout=5, success_exit_codes=[0, 1])

    assert action.timeout == 5
    assert action.success_exit_codes == [0, 1]


# Even "timeout: null" is rejected, because it is configured explicitly
@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({"timeout": 5}, "'timeout' cannot be combined with 'wait: false'"),
        ({"timeout": None}, "'timeout' cannot be combined with 'wait: false'"),
        (
            {"success_exit_codes": [0]},
            "'success_exit_codes' cannot be combined with 'wait: false'",
        ),
        (
            {"stdout": {"value": "ok"}},
            "'stdout' cannot be combined with 'wait: false'",
        ),
        (
            {"stderr": {"value": "ok"}},
            "'stderr' cannot be combined with 'wait: false'",
        ),
        (
            {"timeout": 5, "success_exit_codes": [0]},
            "'success_exit_codes', 'timeout' cannot be combined with 'wait: false'",
        ),
        (
            {
                "timeout": 5,
                "success_exit_codes": [0],
                "stdout": {"value": "ok"},
                "stderr": {"value": "ok"},
            },
            "'stderr', 'stdout', 'success_exit_codes', 'timeout' cannot be combined with 'wait: false'",
        ),
    ],
)
def test_action_configuration_rejects_waiting_options_for_background_action(
    options: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        make_action_configuration(wait=False, **options)


####################
# Time parsing tests
####################


# Test the conversion of the dictionary with the custom parser method "_parse_time" to a time object
@pytest.mark.parametrize(
    ("start", "end", "expected_start", "expected_end"),
    [
        ("6", "12", time(6, 0), time(12, 0)),
        ("6:30", "12:30", time(6, 30), time(12, 30)),
        ("6:30:15", "12:30:15", time(6, 30, 15), time(12, 30, 15)),
    ],
)
def test_datetime_configuration_parses_time_formats(
    start: str,
    end: str,
    expected_start: time,
    expected_end: time,
) -> None:
    configuration = DateTimeConditionConfiguration.model_validate(
        {"between": {"start": start, "end": end}}
    )

    assert configuration.between is not None
    assert configuration.between.start == expected_start
    assert configuration.between.end == expected_end


@pytest.mark.parametrize(
    "start",
    [
        # The hour is out of range
        "25:00",
        # The minutes need two digits
        "7:1",
        # The seconds need two digits
        "7:12:3",
        # Too many components
        "7:12:34:56",
    ],
)
def test_datetime_configuration_rejects_invalid_time(start: str) -> None:
    with pytest.raises(ValidationError):
        DateTimeConditionConfiguration.model_validate(
            {"between": {"start": start, "end": "12:00"}}
        )


#########################
# Datetime criteria tests
#########################


def test_datetime_configuration_accepts_between_and_weekday() -> None:
    configuration = DateTimeConditionConfiguration.model_validate(
        {
            "between": {
                "start": "23",
                "end": "1:30",
            },
            "weekday": ["Monday"],
        }
    )

    assert configuration.between is not None
    assert configuration.between.start == time(23, 0)
    assert configuration.between.end == time(1, 30)
    assert configuration.weekday == [Weekday.MONDAY]


def test_datetime_configuration_accepts_weekday_only() -> None:
    configuration = DateTimeConditionConfiguration.model_validate(
        {"weekday": ["Saturday", "Sunday"]}
    )

    assert configuration.between is None
    assert configuration.weekday == [Weekday.SATURDAY, Weekday.SUNDAY]


def test_datetime_configuration_rejects_empty_configuration() -> None:
    with pytest.raises(
        ValidationError,
        match="at least one criterion of 'between', 'weekday' or 'month'",
    ):
        DateTimeConditionConfiguration.model_validate({})


@pytest.mark.parametrize(
    "configuration",
    [
        {"weekday": []},
        # A valid 'between' must not make up for an empty weekday list
        {"between": {"start": "22:00", "end": "6:00"}, "weekday": []},
    ],
)
def test_datetime_configuration_rejects_empty_weekday_list(
    configuration: dict[str, object],
) -> None:
    with pytest.raises(
        ValidationError,
        match="'weekday' list must contain at least one weekday",
    ):
        DateTimeConditionConfiguration.model_validate(configuration)


#################################
# Between variant selection tests
#################################


@pytest.mark.parametrize(
    ("between", "expected_type"),
    [
        ({"start": "23", "end": "1:30"}, TimeRangeConfiguration),
        ({"start": time(23, 0), "end": time(1, 30)}, TimeRangeConfiguration),
        ({"start": "2026-08-21", "end": "2026-08-22"}, DateRangeConfiguration),
        (
            {"start": "2026-08-21 18:00", "end": "2026-08-22 6:00"},
            DateTimeRangeConfiguration,
        ),
        (
            {"start": "2026-08-21T18:00", "end": "2026-08-22T6:00"},
            DateTimeRangeConfiguration,
        ),
    ],
)
def test_datetime_configuration_selects_between_variant_by_value_kind(
    between: dict[str, object],
    expected_type: type[BaseModel],
) -> None:
    configuration = DateTimeConditionConfiguration.model_validate({"between": between})

    assert type(configuration.between) is expected_type


@pytest.mark.parametrize(
    "between",
    [
        TimeRangeConfiguration(start=time(23, 0), end=time(1, 30)),
        DateRangeConfiguration(start=date(2026, 8, 21), end=date(2026, 8, 22)),
        DateTimeRangeConfiguration(
            start=datetime(2026, 8, 21, 18, 0),
            end=datetime(2026, 8, 22, 6, 0),
        ),
    ],
)
def test_datetime_configuration_accepts_already_built_between_objects(
    between: (
        TimeRangeConfiguration | DateRangeConfiguration | DateTimeRangeConfiguration
    ),
) -> None:
    configuration = DateTimeConditionConfiguration(between=between)

    assert configuration.between == between


@pytest.mark.parametrize(
    "between",
    [
        # Date and time of day
        {"start": "2026-08-21", "end": "18:00"},
        # Time of day and date with time
        {"start": "23", "end": "2026-08-22 6:00"},
        # Date and date with time
        {"start": "2026-08-21", "end": "2026-08-22 6:00"},
        # Native date and native datetime objects
        {"start": date(2026, 8, 21), "end": datetime(2026, 8, 22, 6, 0)},
        # No boundaries at all
        {},
        # Not a mapping
        "23:00",
        ["23", "1"],
    ],
)
def test_datetime_configuration_rejects_invalid_between_structure(
    between: object,
) -> None:
    with pytest.raises(
        ValidationError,
        match="'between' must define 'start' and 'end'",
    ):
        DateTimeConditionConfiguration.model_validate({"between": between})


@pytest.mark.parametrize(
    "between",
    [
        {"start": "2026-08-21"},
        {"end": "2026-08-22 6:00"},
        {"start": "23"},
    ],
)
def test_datetime_configuration_rejects_missing_between_boundary(
    between: dict[str, str],
) -> None:
    # The kind is derived from the boundary which is present, that variant reports the missing one
    with pytest.raises(ValidationError, match="Field required"):
        DateTimeConditionConfiguration.model_validate({"between": between})


def test_datetime_configuration_rejects_unknown_between_field() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        DateTimeConditionConfiguration.model_validate(
            {
                "between": {
                    "start": "2026-08-21",
                    "end": "2026-08-22",
                    # Unknown field
                    "timezone": "UTC",
                }
            }
        )


##################
# Date range tests
##################


def test_date_range_configuration_parses_iso_dates() -> None:
    configuration = DateTimeConditionConfiguration.model_validate(
        {
            "between": {
                "start": "2026-08-21",
                "end": "2026-08-22",
            }
        }
    )

    assert isinstance(configuration.between, DateRangeConfiguration)
    assert configuration.between.start == date(2026, 8, 21)
    assert configuration.between.end == date(2026, 8, 22)


def test_date_range_configuration_accepts_native_date_objects() -> None:
    configuration = DateTimeConditionConfiguration.model_validate(
        {
            "between": {
                "start": date(2026, 8, 21),
                "end": date(2026, 8, 22),
            }
        }
    )

    assert isinstance(configuration.between, DateRangeConfiguration)
    assert configuration.between.start == date(2026, 8, 21)
    assert configuration.between.end == date(2026, 8, 22)


def test_date_range_configuration_accepts_leap_day() -> None:
    configuration = DateTimeConditionConfiguration.model_validate(
        {
            "between": {
                "start": "2028-02-29",
                "end": "2028-03-01",
            }
        }
    )

    assert isinstance(configuration.between, DateRangeConfiguration)
    assert configuration.between.start == date(2028, 2, 29)


def test_date_range_configuration_can_be_combined_with_weekday() -> None:
    configuration = DateTimeConditionConfiguration.model_validate(
        {
            "between": {
                "start": "2026-12-20",
                "end": "2027-01-06",
            },
            "weekday": ["Saturday", "Sunday"],
        }
    )

    assert isinstance(configuration.between, DateRangeConfiguration)
    assert configuration.weekday == [Weekday.SATURDAY, Weekday.SUNDAY]


@pytest.mark.parametrize(
    ("invalid_date", "message"),
    [
        # Well-formed, but not an existing date
        ("2026-13-01", "Invalid date value"),
        ("2026-02-30", "Invalid date value"),
        ("2027-02-29", "Invalid date value"),
        # Not in the format YYYY-MM-DD
        ("2026-1-5", "Invalid date format"),
        ("26-12-24", "Invalid date format"),
        ("2026-12-2", "Invalid date format"),
    ],
)
def test_date_range_configuration_rejects_invalid_date(
    invalid_date: str,
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        DateTimeConditionConfiguration.model_validate(
            {
                "between": {
                    "start": invalid_date,
                    "end": "2030-01-01",
                }
            }
        )


@pytest.mark.parametrize(
    ("start", "end"),
    [
        # The end is exclusive, so equal dates would not match anything
        ("2026-08-21", "2026-08-21"),
        ("2026-08-22", "2026-08-21"),
    ],
)
def test_date_range_configuration_rejects_end_not_after_start(
    start: str,
    end: str,
) -> None:
    with pytest.raises(ValidationError, match="'end' must be after 'start'"):
        DateTimeConditionConfiguration.model_validate(
            {"between": {"start": start, "end": end}}
        )


def test_date_range_configuration_rejects_datetime_object() -> None:
    with pytest.raises(ValidationError, match="Date value must not contain a time"):
        DateRangeConfiguration.model_validate(
            {
                "start": datetime(2026, 8, 21, 18, 0),
                "end": datetime(2026, 8, 22, 6, 0),
            }
        )


def test_date_range_configuration_rejects_non_string_value() -> None:
    with pytest.raises(ValidationError, match="Date value must be a string"):
        DateRangeConfiguration.model_validate({"start": 20261224, "end": 20261226})


######################
# Datetime range tests
######################


def test_datetime_range_configuration_parses_datetimes() -> None:
    configuration = DateTimeConditionConfiguration.model_validate(
        {
            "between": {
                "start": "2026-08-21 18:00",
                "end": "2026-08-22 6:00",
            }
        }
    )

    assert isinstance(configuration.between, DateTimeRangeConfiguration)
    assert configuration.between.start == datetime(2026, 8, 21, 18, 0)
    assert configuration.between.end == datetime(2026, 8, 22, 6, 0)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-08-21 6", datetime(2026, 8, 21, 6, 0)),
        ("2026-08-21 6:30", datetime(2026, 8, 21, 6, 30)),
        ("2026-08-21 6:30:15", datetime(2026, 8, 21, 6, 30, 15)),
        ("2026-08-21T06:30:15", datetime(2026, 8, 21, 6, 30, 15)),
    ],
)
def test_datetime_range_configuration_parses_supported_time_formats(
    value: str,
    expected: datetime,
) -> None:
    configuration = DateTimeConditionConfiguration.model_validate(
        {
            "between": {
                "start": value,
                "end": "2030-01-01 0:00",
            }
        }
    )

    assert isinstance(configuration.between, DateTimeRangeConfiguration)
    assert configuration.between.start == expected


def test_datetime_range_configuration_accepts_native_naive_datetime_objects() -> None:
    configuration = DateTimeConditionConfiguration.model_validate(
        {
            "between": {
                "start": datetime(2026, 8, 21, 18, 0),
                "end": datetime(2026, 8, 22, 6, 0),
            }
        }
    )

    assert isinstance(configuration.between, DateTimeRangeConfiguration)
    assert configuration.between.start == datetime(2026, 8, 21, 18, 0)
    assert configuration.between.end == datetime(2026, 8, 22, 6, 0)


@pytest.mark.parametrize(
    "value",
    [
        "2026-08-21 18:00Z",
        "2026-08-21 18:00+02:00",
        "2026-08-21T18:00:00-05:00",
        "2026-08-21 18:00:00+0200",
        "2026-08-21 18:00:00-05",
    ],
)
def test_datetime_range_configuration_rejects_timezone_in_string(value: str) -> None:
    with pytest.raises(ValidationError, match="Timezone information is not supported"):
        DateTimeConditionConfiguration.model_validate(
            {
                "between": {
                    "start": value,
                    "end": "2030-01-01 0:00",
                }
            }
        )


def test_datetime_range_configuration_rejects_timezone_aware_datetime_object() -> None:
    with pytest.raises(
        ValidationError,
        match="Timezone-aware datetimes are not supported",
    ):
        DateTimeConditionConfiguration.model_validate(
            {
                "between": {
                    "start": datetime(2026, 8, 21, 18, 0, tzinfo=UTC),
                    "end": datetime(2026, 8, 22, 6, 0, tzinfo=UTC),
                }
            }
        )


@pytest.mark.parametrize(
    ("value", "message"),
    [
        # The date part is validated by the date parser
        ("2026-02-30 10:00", "Invalid date value"),
        # The time part is validated by the existing time parser
        ("2026-08-21 25:00", "Invalid time value"),
        ("2026-08-21 7:1", "Invalid minute format"),
        # No time given at all
        ("2026-08-21 ", "Invalid datetime format"),
    ],
)
def test_datetime_range_configuration_rejects_invalid_datetime(
    value: str,
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        DateTimeConditionConfiguration.model_validate(
            {
                "between": {
                    "start": value,
                    "end": "2030-01-01 0:00",
                }
            }
        )


@pytest.mark.parametrize(
    ("start", "end"),
    [
        # The end is exclusive, so equal datetimes would not match anything
        ("2026-08-21 18:00", "2026-08-21 18:00"),
        ("2026-08-22 6:00", "2026-08-21 18:00"),
    ],
)
def test_datetime_range_configuration_rejects_end_not_after_start(
    start: str,
    end: str,
) -> None:
    with pytest.raises(ValidationError, match="'end' must be after 'start'"):
        DateTimeConditionConfiguration.model_validate(
            {"between": {"start": start, "end": end}}
        )


def test_datetime_range_configuration_rejects_date_object() -> None:
    with pytest.raises(ValidationError, match="Datetime value must contain a time"):
        DateTimeRangeConfiguration.model_validate(
            {
                "start": date(2026, 8, 21),
                "end": date(2026, 8, 22),
            }
        )


def test_datetime_range_configuration_rejects_non_string_value() -> None:
    with pytest.raises(ValidationError, match="Datetime value must be a string"):
        DateTimeRangeConfiguration.model_validate({"start": 5, "end": 6})


#############
# Month tests
#############


def test_datetime_configuration_accepts_month_only() -> None:
    configuration = DateTimeConditionConfiguration.model_validate(
        {"month": ["June", "July"]}
    )

    assert configuration.between is None
    assert configuration.weekday is None
    assert configuration.month == [Month.JUNE, Month.JULY]


def test_datetime_configuration_accepts_none_month() -> None:
    configuration = DateTimeConditionConfiguration.model_validate(
        {"month": None, "weekday": ["Monday"]}
    )

    assert configuration.month is None


def test_datetime_configuration_accepts_between_weekday_and_month() -> None:
    configuration = DateTimeConditionConfiguration.model_validate(
        {
            "between": {
                "start": "22",
                "end": "6",
            },
            "weekday": ["Saturday", "Sunday"],
            "month": ["December"],
        }
    )

    assert isinstance(configuration.between, TimeRangeConfiguration)
    assert configuration.weekday == [Weekday.SATURDAY, Weekday.SUNDAY]
    assert configuration.month == [Month.DECEMBER]


@pytest.mark.parametrize("month", list(Month))
def test_datetime_configuration_parses_every_month_name_regardless_of_case(
    month: Month,
) -> None:
    for name in (month.value, month.value.lower(), month.value.upper()):
        configuration = DateTimeConditionConfiguration.model_validate({"month": [name]})

        assert configuration.month == [month]


def test_datetime_configuration_parses_mixed_case_month_list() -> None:
    configuration = DateTimeConditionConfiguration.model_validate(
        {"month": ["june", "JULY", "August", "sEpTeMbEr"]}
    )

    assert configuration.month == [
        Month.JUNE,
        Month.JULY,
        Month.AUGUST,
        Month.SEPTEMBER,
    ]


def test_datetime_configuration_rejects_empty_month_list() -> None:
    with pytest.raises(
        ValidationError,
        match="'month' list must contain at least one month",
    ):
        DateTimeConditionConfiguration.model_validate({"month": []})


# Names have to be complete English month names, only the case is ignored
@pytest.mark.parametrize("invalid_month", ["Jun", "Marchh", "", "13", "März", 5, None])
def test_datetime_configuration_rejects_unknown_month(invalid_month: object) -> None:
    with pytest.raises(ValidationError, match="Input should be"):
        DateTimeConditionConfiguration.model_validate({"month": [invalid_month]})


@pytest.mark.parametrize("month", ["June", "june"])
def test_datetime_configuration_rejects_month_which_is_not_a_list(month: str) -> None:
    with pytest.raises(ValidationError, match="valid list"):
        DateTimeConditionConfiguration.model_validate({"month": month})


###############
# Weekday tests
###############


@pytest.mark.parametrize("weekday", list(Weekday))
def test_datetime_configuration_parses_every_weekday_name_regardless_of_case(
    weekday: Weekday,
) -> None:
    for name in (weekday.value, weekday.value.lower(), weekday.value.upper()):
        configuration = DateTimeConditionConfiguration.model_validate(
            {"weekday": [name]}
        )

        assert configuration.weekday == [weekday]


def test_datetime_configuration_parses_mixed_case_weekday_list() -> None:
    configuration = DateTimeConditionConfiguration.model_validate(
        {"weekday": ["monday", "FRIDAY", "Sunday", "sAtUrDaY"]}
    )

    assert configuration.weekday == [
        Weekday.MONDAY,
        Weekday.FRIDAY,
        Weekday.SUNDAY,
        Weekday.SATURDAY,
    ]


def test_datetime_configuration_parses_weekday_and_month_regardless_of_case() -> None:
    configuration = DateTimeConditionConfiguration.model_validate(
        {
            "weekday": ["saturday", "SUNDAY"],
            "month": ["december"],
        }
    )

    assert configuration.weekday == [Weekday.SATURDAY, Weekday.SUNDAY]
    assert configuration.month == [Month.DECEMBER]


# Names have to be complete English weekday names, only the case is ignored
@pytest.mark.parametrize(
    "invalid_weekday", ["Mon", "Mondayy", "Funday", "", "1", "Montag", 5, None]
)
def test_datetime_configuration_rejects_unknown_weekday_names(
    invalid_weekday: object,
) -> None:
    with pytest.raises(ValidationError, match="Input should be"):
        DateTimeConditionConfiguration.model_validate({"weekday": [invalid_weekday]})


@pytest.mark.parametrize("weekday", ["Monday", "monday"])
def test_datetime_configuration_rejects_weekday_which_is_not_a_list(
    weekday: str,
) -> None:
    with pytest.raises(ValidationError, match="valid list"):
        DateTimeConditionConfiguration.model_validate({"weekday": weekday})


#####################
# Trusted files tests
#####################


def test_action_configuration_has_no_trusted_files_by_default() -> None:
    assert make_action_configuration().trusted_files == []


def test_action_configuration_does_not_share_trusted_files_between_instances() -> None:
    first = make_action_configuration()
    first.trusted_files.append(Path("a.sh"))

    assert make_action_configuration().trusted_files == []


def test_action_configuration_converts_trusted_files_to_paths() -> None:
    action = make_action_configuration(trusted_files=["scripts/a.sh", "/opt/b.sh"])

    assert action.trusted_files == [Path("scripts/a.sh"), Path("/opt/b.sh")]


@pytest.mark.parametrize("files", [[""], ["   "], ["a.sh", ""], ["a.sh", " \t"]])
def test_action_configuration_rejects_blank_trusted_file(files: list[str]) -> None:
    with pytest.raises(
        ValidationError, match="'trusted_files' entries must not be blank"
    ):
        make_action_configuration(trusted_files=files)


@pytest.mark.parametrize("files", ["a.sh", {"a": "b"}])
def test_action_configuration_rejects_trusted_files_which_are_not_a_list(
    files: object,
) -> None:
    with pytest.raises(ValidationError, match="valid list"):
        make_action_configuration(trusted_files=files)


def test_rule_set_returns_trusted_files_of_all_rules_including_disabled_ones() -> None:
    configuration = RuleSetConfiguration.model_validate(
        {
            "rules": [
                make_trusted_files_rule_data("First", ["a.sh", "b.sh"]),
                make_trusted_files_rule_data(
                    "Disabled", ["b.sh", "c.sh"], enabled=False
                ),
            ]
        }
    )

    # Duplicates are removed later by "resolve_trusted_files()"
    assert configuration.get_trusted_files() == (
        Path("a.sh"),
        Path("b.sh"),
        Path("b.sh"),
        Path("c.sh"),
    )


def test_rule_set_without_trusted_files_returns_empty_tuple() -> None:
    configuration = RuleSetConfiguration.model_validate(
        {"rules": [make_trusted_files_rule_data("First", [])]}
    )

    assert configuration.get_trusted_files() == ()


##########################
# Output expectation tests
##########################


def test_output_match_configuration_matches_exactly_and_case_sensitive_by_default() -> (
    None
):
    output = OutputMatchConfiguration.model_validate({"value": "active"})

    assert output.value == "active"
    assert output.match.type is MatchType.EXACT
    assert output.match.case_sensitive is True


def test_output_match_configuration_accepts_match_options() -> None:
    output = OutputMatchConfiguration.model_validate(
        {"value": ".*error.*", "match": {"type": "regex", "case_sensitive": False}}
    )

    assert output.match.type is MatchType.REGEX
    assert output.match.case_sensitive is False


def test_output_match_configuration_accepts_contains_match() -> None:
    output = OutputMatchConfiguration.model_validate(
        {"value": "active", "match": {"type": "contains"}}
    )

    assert output.match.type is MatchType.CONTAINS


# An empty text is valid: It matches an output which is empty after it was stripped
def test_output_match_configuration_accepts_empty_value() -> None:
    assert OutputMatchConfiguration.model_validate({"value": ""}).value == ""


def test_output_match_configuration_requires_value() -> None:
    with pytest.raises(ValidationError, match="Field required"):
        OutputMatchConfiguration.model_validate({"match": {"type": "regex"}})


@pytest.mark.parametrize("value", [5, None, ["a"]])
def test_output_match_configuration_rejects_non_string_value(value: object) -> None:
    with pytest.raises(ValidationError, match="valid string"):
        OutputMatchConfiguration.model_validate({"value": value})


def test_output_match_configuration_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        OutputMatchConfiguration.model_validate({"value": "ok", "unknown": True})


def test_action_configuration_accepts_output_expectations() -> None:
    action = make_action_configuration(
        stdout={"value": "active", "match": {"type": "contains"}},
        stderr={"value": ""},
    )

    assert action.stdout is not None
    assert action.stdout.match.type is MatchType.CONTAINS
    assert action.stderr is not None
    assert action.stderr.value == ""


def test_action_configuration_has_no_output_expectations_by_default() -> None:
    action = make_action_configuration()

    assert action.stdout is None
    assert action.stderr is None


#####################################
# CommandConditionConfiguration tests
#####################################


def test_command_condition_configuration_uses_defaults() -> None:
    command = CommandConditionConfiguration.model_validate({"run": "echo test"})

    assert command.run == "echo test"
    assert command.shell is None
    assert command.working_directory is None
    assert command.env == {}
    assert command.timeout == DEFAULT_COMMAND_TIMEOUT_SECONDS
    assert command.success_exit_codes == [0]
    assert command.stdout is None
    assert command.stderr is None
    assert command.trusted_files == []


def test_command_condition_configuration_accepts_all_options() -> None:
    command = CommandConditionConfiguration.model_validate(
        {
            "run": "systemctl is-active nginx",
            "shell": "bash",
            "working_directory": "scripts",
            "env": {"RETRIES": 3},
            "timeout": 5,
            "success_exit_codes": [0, 3],
            "stdout": {"value": "active", "match": {"type": "contains"}},
            "stderr": {"value": ".*error.*", "match": {"type": "regex"}},
            "trusted_files": ["scripts/check.sh"],
        }
    )

    assert command.shell is Shell.BASH
    assert command.working_directory == Path("scripts")
    assert command.env == {"RETRIES": "3"}
    assert command.timeout == 5
    assert command.success_exit_codes == [0, 3]
    assert command.stdout is not None
    assert command.stdout.value == "active"
    assert command.stderr is not None
    assert command.stderr.match.type is MatchType.REGEX
    assert command.trusted_files == [Path("scripts/check.sh")]


def test_command_condition_configuration_requires_run() -> None:
    with pytest.raises(ValidationError, match="Field required"):
        CommandConditionConfiguration.model_validate({})


@pytest.mark.parametrize("value", ["", " ", "\n\t"])
def test_command_condition_configuration_rejects_blank_run(value: str) -> None:
    with pytest.raises(ValidationError, match="The 'run' value must not be blank"):
        CommandConditionConfiguration.model_validate({"run": value})


# A condition has no name, does not run in the background and has nothing to continue after an error
@pytest.mark.parametrize(
    "option",
    [
        {"name": "Check"},
        {"wait": False},
        {"continue_on_error": True},
    ],
)
def test_command_condition_configuration_rejects_action_only_options(
    option: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CommandConditionConfiguration.model_validate({"run": "echo test", **option})


@pytest.mark.parametrize(
    ("option", "message"),
    [
        ({"env": {"POWERRULES_CUSTOM": "value"}}, "is reserved"),
        ({"env": {"A=B": "value"}}, "Invalid environment variable name"),
        ({"working_directory": " "}, "must not be blank"),
        ({"timeout": 0}, "'timeout' must be greater than zero"),
        ({"success_exit_codes": []}, "at least 1 item"),
        ({"trusted_files": [" "]}, "'trusted_files' entries must not be blank"),
    ],
)
def test_command_condition_configuration_validates_shared_options(
    option: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        CommandConditionConfiguration.model_validate({"run": "echo test", **option})


# YAML ".inf" is a float which cannot be passed on as a wait time, so it means "no time limit"
def test_timeout_infinity_is_normalized_to_no_time_limit() -> None:
    action = make_action_configuration(timeout=float("inf"))
    command = CommandConditionConfiguration.model_validate(
        {"run": "echo test", "timeout": float("inf")}
    )

    assert action.timeout is None
    assert command.timeout is None


#################################
# Command condition variant tests
#################################


def test_condition_configuration_accepts_command_condition() -> None:
    condition = ConditionConfiguration.model_validate({"command": {"run": "echo test"}})

    assert condition.command is not None
    assert condition.command.run == "echo test"


def test_condition_configuration_rejects_command_combined_with_other_variant() -> None:
    with pytest.raises(ValidationError, match="must define exactly one of"):
        ConditionConfiguration.model_validate(
            {
                "command": {"run": "echo test"},
                "process": {"name": "backup.exe", "exists": False},
            }
        )


def test_condition_configuration_names_command_as_variant_in_error() -> None:
    with pytest.raises(ValidationError, match="or 'command'"):
        ConditionConfiguration.model_validate({})


def test_condition_configuration_rejects_unknown_command_field() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ConditionConfiguration.model_validate(
            {"command": {"run": "echo test", "unknown": True}}
        )


def test_condition_configuration_returns_trusted_files_of_nested_command_conditions() -> (
    None
):
    condition = ConditionConfiguration.model_validate(
        {
            "and": [
                {"command": {"run": "a", "trusted_files": ["a.sh", "b.sh"]}},
                {
                    "or": [
                        {"not": {"command": {"run": "c", "trusted_files": ["c.sh"]}}},
                        {"process": {"name": "backup.exe", "exists": False}},
                    ]
                },
            ]
        }
    )

    # Duplicates are not removed here, see "resolve_trusted_files()"
    assert condition.get_trusted_files() == (Path("a.sh"), Path("b.sh"), Path("c.sh"))


def test_condition_configuration_without_command_condition_has_no_trusted_files() -> (
    None
):
    condition = ConditionConfiguration.model_validate(
        {"process": {"name": "backup.exe", "exists": False}}
    )

    assert condition.get_trusted_files() == ()


PROCESS_CONDITION_DATA = {"process": {"name": "backup.exe", "exists": False}}


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({"command": {"run": "a"}}, True),
        (PROCESS_CONDITION_DATA, False),
        ({"not": {"command": {"run": "a"}}}, True),
        (
            {
                "and": [
                    PROCESS_CONDITION_DATA,
                    {
                        "or": [
                            {"datetime": {"weekday": ["Monday"]}},
                            {"command": {"run": "a"}},
                        ]
                    },
                ]
            },
            True,
        ),
        (
            {
                "and": [
                    PROCESS_CONDITION_DATA,
                    {"window": {"title": "Firefox", "exists": True}},
                ]
            },
            False,
        ),
    ],
)
def test_condition_configuration_detects_command_conditions(
    data: dict[str, object],
    expected: bool,
) -> None:
    assert ConditionConfiguration.model_validate(data).has_command_condition() is (
        expected
    )


def test_rule_set_returns_trusted_files_of_conditions_before_those_of_actions() -> None:
    configuration = RuleSetConfiguration.model_validate(
        {
            "rules": [
                make_rule_data(
                    name="First",
                    conditions={
                        "command": {"run": "check", "trusted_files": ["c1.sh"]}
                    },
                    actions=[{"run": "echo test", "trusted_files": ["a1.sh"]}],
                ),
                make_rule_data(
                    name="Disabled",
                    enabled=False,
                    conditions={
                        "command": {"run": "check", "trusted_files": ["c2.sh"]}
                    },
                    actions=[{"run": "echo test", "trusted_files": ["a2.sh"]}],
                ),
            ]
        }
    )

    assert configuration.get_trusted_files() == (
        Path("c1.sh"),
        Path("a1.sh"),
        Path("c2.sh"),
        Path("a2.sh"),
    )


@pytest.mark.parametrize(
    ("rules", "expected"),
    [
        ([], False),
        ([make_rule_data()], False),
        ([make_rule_data(conditions={"command": {"run": "check"}})], True),
        # Disabled rules count as well, their files are trusted too
        (
            [
                make_rule_data(),
                make_rule_data(enabled=False, conditions={"command": {"run": "check"}}),
            ],
            True,
        ),
    ],
)
def test_rule_set_detects_command_conditions(
    rules: list[dict[str, object]],
    expected: bool,
) -> None:
    configuration = RuleSetConfiguration.model_validate({"rules": rules})

    assert configuration.has_command_condition() is expected
