from unittest.mock import patch

import pytest

from powerrules.conditions.matcher import MatchType
from powerrules.conditions.window import WindowCondition
from powerrules.engine.exceptions import (
    ConditionEvaluationError,
    ConditionEvaluationProviderNotAvailableError,
)


def test_window_condition_matches_exact_existing_window_case_sensitive() -> None:
    with patch("powerrules.providers.window.WindowProvider") as mock_provider:
        mock_provider.get_window_titles.return_value = ["Test window title"]

        condition = WindowCondition(
            window_title="Test window title",
            expected_exists=True,
            window_provider=mock_provider,
            match_type=MatchType.EXACT,
            case_sensitive=True,
        )

        assert condition.evaluate() is True


def test_window_condition_does_not_match_exact_existing_window_case_sensitive() -> None:
    with patch("powerrules.providers.window.WindowProvider") as mock_provider:
        mock_provider.get_window_titles.return_value = ["Test window title"]

        condition = WindowCondition(
            window_title="Test window title",
            expected_exists=False,
            window_provider=mock_provider,
            match_type=MatchType.EXACT,
            case_sensitive=True,
        )

    assert condition.evaluate() is False


def test_window_condition_matches_exact_existing_window_case_insensitive() -> None:
    with patch("powerrules.providers.window.WindowProvider") as mock_provider:
        mock_provider.get_window_titles.return_value = ["Test window title"]

        condition = WindowCondition(
            window_title="TEST WINDOW TITLE",
            expected_exists=True,
            window_provider=mock_provider,
            match_type=MatchType.EXACT,
            case_sensitive=False,
        )

        assert condition.evaluate() is True


def test_window_condition_does_not_match_exact_existing_window_case_insensitive() -> (
    None
):
    with patch("powerrules.providers.window.WindowProvider") as mock_provider:
        mock_provider.get_window_titles.return_value = ["Test window title"]

        condition = WindowCondition(
            window_title="TEST WINDOW TITLE",
            expected_exists=False,
            window_provider=mock_provider,
            match_type=MatchType.EXACT,
            case_sensitive=False,
        )

    assert condition.evaluate() is False


def test_window_condition_matches_regex_existing_window_case_sensitive() -> None:
    with patch("powerrules.providers.window.WindowProvider") as mock_provider:
        mock_provider.get_window_titles.return_value = ["Test window title"]

        condition = WindowCondition(
            window_title="Test.*title",
            expected_exists=True,
            window_provider=mock_provider,
            match_type=MatchType.REGEX,
            case_sensitive=True,
        )

        assert condition.evaluate() is True


def test_window_condition_does_not_match_regex_existing_window_case_sensitive() -> None:
    with patch("powerrules.providers.window.WindowProvider") as mock_provider:
        mock_provider.get_window_titles.return_value = ["Test window title"]

        condition = WindowCondition(
            window_title="Test.*title",
            expected_exists=False,
            window_provider=mock_provider,
            match_type=MatchType.REGEX,
            case_sensitive=True,
        )

    assert condition.evaluate() is False


def test_window_condition_matches_regex_existing_window_case_insensitive() -> None:
    with patch("powerrules.providers.window.WindowProvider") as mock_provider:
        mock_provider.get_window_titles.return_value = ["Test window title"]

        condition = WindowCondition(
            window_title="TEST.*TITLE",
            expected_exists=True,
            window_provider=mock_provider,
            match_type=MatchType.REGEX,
            case_sensitive=False,
        )

        assert condition.evaluate() is True


def test_window_condition_does_not_match_regex_existing_window_case_insensitive() -> (
    None
):
    with patch("powerrules.providers.window.WindowProvider") as mock_provider:
        mock_provider.get_window_titles.return_value = ["Test window title"]

        condition = WindowCondition(
            window_title="TEST.*TITLE",
            expected_exists=False,
            window_provider=mock_provider,
            match_type=MatchType.REGEX,
            case_sensitive=False,
        )

    assert condition.evaluate() is False


def test_window_condition_raises_evaluation_error() -> None:
    with patch("powerrules.providers.window.WindowProvider") as mock_provider:
        mock_provider.get_window_titles.side_effect = RuntimeError(
            "Test window enumeration failure"
        )
        mock_provider.is_available = True

        condition = WindowCondition(
            window_title="Test window title",
            expected_exists=True,
            window_provider=mock_provider,
        )

        # Make sure the exception type is correct
        with pytest.raises(ConditionEvaluationError) as exc_info:
            condition.evaluate()

        # Make sure the exception message is used from the underlying exception
        assert (
            str(exc_info.value)
            == "Failed to determine whether window 'Test window title' exists"
        )


def test_window_condition_raises_no_provider_error() -> None:
    with patch("powerrules.providers.window.WindowProvider") as mock_provider:
        mock_provider.is_available = False

    condition = WindowCondition(
        window_title="Test window title",
        expected_exists=True,
        window_provider=mock_provider,
    )

    with pytest.raises(ConditionEvaluationProviderNotAvailableError) as exc_info:
        condition.evaluate()

    assert (
        str(exc_info.value)
        == "Window provider is not available, cannot evaluate window condition for 'Test window title'"
    )
