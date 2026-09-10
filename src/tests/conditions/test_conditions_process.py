from unittest.mock import patch

import pytest

from powerrules.conditions.matcher import MatchType
from powerrules.conditions.process import ProcessCondition
from powerrules.engine.exceptions import ConditionEvaluationError


def test_process_condition_matches_exact_existing_process_case_sensitive() -> None:
    with patch("powerrules.providers.process.ProcessProvider") as mock_provider:
        mock_provider.get_process_names.return_value = ["test.exe"]

        condition = ProcessCondition(
            process_name="test.exe",
            expected_exists=True,
            process_provider=mock_provider,
            match_type=MatchType.EXACT,
            case_sensitive=True,
        )

        assert condition.evaluate() is True


def test_process_condition_does_not_match_exact_existing_process_case_sensitive() -> (
    None
):
    with patch("powerrules.providers.process.ProcessProvider") as mock_provider:
        mock_provider.get_process_names.return_value = ["test.exe"]

        condition = ProcessCondition(
            process_name="test.exe",
            expected_exists=False,
            process_provider=mock_provider,
            match_type=MatchType.EXACT,
            case_sensitive=True,
        )

    assert condition.evaluate() is False


def test_process_condition_matches_exact_existing_process_case_insensitive() -> None:
    with patch("powerrules.providers.process.ProcessProvider") as mock_provider:
        mock_provider.get_process_names.return_value = ["test.exe"]

        condition = ProcessCondition(
            process_name="TEST.exe",
            expected_exists=True,
            process_provider=mock_provider,
            match_type=MatchType.EXACT,
            case_sensitive=False,
        )

        assert condition.evaluate() is True


def test_process_condition_does_not_match_exact_existing_process_case_insensitive() -> (
    None
):
    with patch("powerrules.providers.process.ProcessProvider") as mock_provider:
        mock_provider.get_process_names.return_value = ["test.exe"]

        condition = ProcessCondition(
            process_name="TEST.exe",
            expected_exists=False,
            process_provider=mock_provider,
            match_type=MatchType.EXACT,
            case_sensitive=False,
        )

    assert condition.evaluate() is False


def test_process_condition_matches_regex_existing_process_case_sensitive() -> None:
    with patch("powerrules.providers.process.ProcessProvider") as mock_provider:
        mock_provider.get_process_names.return_value = ["test.exe"]

        condition = ProcessCondition(
            process_name=".*\\.exe",
            expected_exists=True,
            process_provider=mock_provider,
            match_type=MatchType.REGEX,
            case_sensitive=True,
        )

        assert condition.evaluate() is True


def test_process_condition_does_not_match_regex_existing_process_case_sensitive() -> (
    None
):
    with patch("powerrules.providers.process.ProcessProvider") as mock_provider:
        mock_provider.get_process_names.return_value = ["test.exe"]

        condition = ProcessCondition(
            process_name=".*\\.executable",
            expected_exists=True,
            process_provider=mock_provider,
            match_type=MatchType.REGEX,
            case_sensitive=True,
        )

        assert condition.evaluate() is False


def test_process_condition_matches_regex_existing_process_case_insensitive() -> None:
    with patch("powerrules.providers.process.ProcessProvider") as mock_provider:
        mock_provider.get_process_names.return_value = ["test.exe"]

        condition = ProcessCondition(
            process_name=".*\\.exe",
            expected_exists=True,
            process_provider=mock_provider,
            match_type=MatchType.REGEX,
            case_sensitive=False,
        )

        assert condition.evaluate() is True


def test_process_condition_does_not_match_regex_existing_process_case_insensitive() -> (
    None
):
    with patch("powerrules.providers.process.ProcessProvider") as mock_provider:
        mock_provider.get_process_names.return_value = ["test.exe"]

        condition = ProcessCondition(
            process_name=".*\\.executable",
            expected_exists=True,
            process_provider=mock_provider,
            match_type=MatchType.REGEX,
            case_sensitive=False,
        )

        assert condition.evaluate() is False


def test_process_condition_raises_evaluation_error() -> None:
    with patch("powerrules.providers.process.ProcessProvider") as mock_provider:
        mock_provider.get_process_names.side_effect = OSError("Test OSError")

    condition = ProcessCondition(
        process_name="test.exe",
        expected_exists=True,
        process_provider=mock_provider,
        match_type=MatchType.EXACT,
        case_sensitive=False,
    )

    # Make sure the exception type is correct
    with pytest.raises(ConditionEvaluationError) as exc_info:
        condition.evaluate()

    # Make sure the exception message is used from the underlying exception
    assert str(exc_info.value) == (
        "Failed to determine whether process 'test.exe' exists"
    )
