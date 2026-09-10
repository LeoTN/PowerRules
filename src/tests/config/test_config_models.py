from datetime import time

import pytest
from pydantic import ValidationError

from powerrules.config.models import (
    DateTimeConditionConfiguration,
    RuleSetConfiguration,
)


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
                    "action": {
                        "type": "shutdown",
                    },
                }
            ]
        }
    )

    assert len(configuration.rules) == 1
    assert configuration.rules[0].name == "Shutdown after backup test rule"
    assert configuration.rules[0].enabled is True


def test_and_condition_requires_at_least_two_conditions() -> None:
    with pytest.raises(ValidationError):
        RuleSetConfiguration.model_validate(
            {
                "rules": [
                    {
                        "name": "Invalid test rule",
                        "conditions": {
                            "and": [
                                {
                                    "process": {
                                        "name": "backup.exe",
                                        "exists": False,
                                    }
                                    # Missing second condition
                                }
                            ]
                        },
                        "action": {
                            "type": "shutdown",
                        },
                    }
                ]
            }
        )


def test_not_condition_accepts_single_condition() -> None:
    configuration = RuleSetConfiguration.model_validate(
        {
            "rules": [
                {
                    "name": "Test rule",
                    "conditions": {
                        "not": {
                            "process": {
                                "name": "backup.exe",
                                "exists": True,
                            }
                        }
                    },
                    "action": {
                        "type": "sleep",
                    },
                }
            ]
        }
    )

    assert configuration.rules[0].conditions.not_condition is not None


def test_invalid_action_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RuleSetConfiguration.model_validate(
            {
                "rules": [
                    {
                        "name": "Invalid test rule",
                        "conditions": {
                            "process": {
                                "name": "backup.exe",
                                "exists": False,
                            }
                        },
                        "action": {
                            # Unknown action type
                            "type": "power_off",
                        },
                    }
                ]
            }
        )


def test_unknown_action_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RuleSetConfiguration.model_validate(
            {
                "rules": [
                    {
                        "name": "Invalid test rule",
                        "conditions": {
                            "process": {
                                "name": "backup.exe",
                                "exists": False,
                            }
                        },
                        "action": {
                            "type": "shutdown",
                            # Unknown field
                            "unknown": True,
                        },
                    }
                ]
            }
        )


####################
# Time parsing tests
####################


def test_datetime_configuration_parses_hour_only() -> None:
    # Test the conversion of the dictionary with the custom parser method "_parse_time" to a time object
    configuration = DateTimeConditionConfiguration.model_validate(
        {
            "between": {
                "start": "6",
                "end": "12",
            }
        }
    )

    assert configuration.between is not None
    assert configuration.between.start == time(6, 0)
    assert configuration.between.end == time(12, 0)


def test_datetime_configuration_parses_hour_and_minute() -> None:
    configuration = DateTimeConditionConfiguration.model_validate(
        {
            "between": {
                "start": "6:30",
                "end": "12:30",
            }
        }
    )

    assert configuration.between is not None
    assert configuration.between.start == time(6, 30)
    assert configuration.between.end == time(12, 30)


def test_datetime_configuration_parses_hour_minute_and_second() -> None:
    configuration = DateTimeConditionConfiguration.model_validate(
        {
            "between": {
                "start": "6:30:15",
                "end": "12:30:15",
            }
        }
    )

    assert configuration.between is not None
    assert configuration.between.start == time(6, 30, 15)
    assert configuration.between.end == time(12, 30, 15)


def test_datetime_configuration_rejects_invalid_time() -> None:
    with pytest.raises(ValidationError):
        DateTimeConditionConfiguration.model_validate(
            {
                "between": {
                    "start": "25:00",
                    "end": "12:00",
                }
            }
        )


def test_datetime_configuration_rejects_invalid_time_format() -> None:
    with pytest.raises(ValidationError):
        DateTimeConditionConfiguration.model_validate(
            {
                "between": {
                    "start": "7:1",
                    "end": "12:00",
                }
            }
        )


def test_datetime_configuration_rejects_single_digit_seconds() -> None:
    with pytest.raises(ValidationError):
        DateTimeConditionConfiguration.model_validate(
            {
                "between": {
                    "start": "7:12:3",
                    "end": "12:00",
                }
            }
        )


def test_datetime_configuration_rejects_too_many_time_components() -> None:
    with pytest.raises(ValidationError):
        DateTimeConditionConfiguration.model_validate(
            {
                "between": {
                    "start": "7:12:34:56",
                    "end": "12:00",
                }
            }
        )
