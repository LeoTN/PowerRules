import re

import pytest

from powerrules.conditions.matcher import MatchType
from powerrules.conditions.window import WindowCondition
from powerrules.engine.exceptions import (
    ConditionEvaluationError,
    ConditionEvaluationProviderNotAvailableError,
)
from tests.mocks import make_window_provider


@pytest.mark.parametrize(
    ("window_title", "match_type", "case_sensitive", "existing_titles", "is_found"),
    [
        # Exact matching
        ("Test window title", MatchType.EXACT, True, ("Test window title",), True),
        ("Test window title", MatchType.EXACT, True, ("TEST WINDOW TITLE",), False),
        ("Test window title", MatchType.EXACT, True, ("Test window title 2",), False),
        ("TEST WINDOW TITLE", MatchType.EXACT, False, ("Test window title",), True),
        ("TEST WINDOW TITLE", MatchType.EXACT, False, ("Other",), False),
        # Regular expressions need to match the whole title
        ("Test.*title", MatchType.REGEX, True, ("Test window title",), True),
        ("Test.*title", MatchType.REGEX, True, ("test window title",), False),
        ("TEST.*TITLE", MatchType.REGEX, False, ("Test window title",), True),
        ("Test", MatchType.REGEX, True, ("Test window title",), False),
        # The existing windows
        ("Test window title", MatchType.EXACT, True, (), False),
        ("Test window title", MatchType.EXACT, True, ("A", "Test window title"), True),
        ("Test window title", MatchType.EXACT, True, ("A", "B"), False),
    ],
)
@pytest.mark.parametrize("expected_exists", [True, False])
def test_window_condition_compares_existing_windows_with_expectation(
    window_title: str,
    match_type: MatchType,
    case_sensitive: bool,
    existing_titles: tuple[str, ...],
    is_found: bool,
    expected_exists: bool,
) -> None:
    condition = WindowCondition(
        window_title=window_title,
        expected_exists=expected_exists,
        window_provider=make_window_provider(existing_titles),
        match_type=match_type,
        case_sensitive=case_sensitive,
    )

    assert condition.evaluate() is (is_found is expected_exists)


def test_window_condition_uses_exact_case_sensitive_matching_by_default() -> None:
    condition = WindowCondition(
        window_title="Test window title",
        expected_exists=True,
        window_provider=make_window_provider(["TEST WINDOW TITLE"]),
    )

    assert condition.matcher.match_type is MatchType.EXACT
    assert condition.matcher.case_sensitive is True
    assert condition.evaluate() is False


def test_window_condition_keeps_its_configuration() -> None:
    window_provider = make_window_provider()

    condition = WindowCondition(
        window_title="Test window title",
        expected_exists=False,
        window_provider=window_provider,
    )

    assert condition.window_title == "Test window title"
    assert condition.expected_exists is False
    assert condition.window_provider is window_provider


# The windows change over time, so every evaluation has to ask the provider again
def test_window_condition_queries_provider_on_every_evaluation() -> None:
    window_provider = make_window_provider(["Test window title"])
    condition = WindowCondition(
        window_title="Test window title",
        expected_exists=True,
        window_provider=window_provider,
    )

    assert condition.evaluate() is True

    window_provider.get_window_titles.return_value = ()

    assert condition.evaluate() is False
    assert window_provider.get_window_titles.call_count == 2


def test_window_condition_raises_evaluation_error() -> None:
    original_error = RuntimeError("Test window enumeration failure")
    condition = WindowCondition(
        window_title="Test window title",
        expected_exists=True,
        window_provider=make_window_provider(error=original_error),
    )

    with pytest.raises(ConditionEvaluationError) as exc_info:
        condition.evaluate()

    assert str(exc_info.value) == (
        "Failed to determine whether window 'Test window title' exists"
    )
    assert exc_info.value.__cause__ is original_error
    # The error of a failed enumeration is not the one of an unavailable provider
    assert not isinstance(exc_info.value, ConditionEvaluationProviderNotAvailableError)


@pytest.mark.parametrize("expected_exists", [True, False])
def test_window_condition_raises_when_provider_is_not_available(
    expected_exists: bool,
) -> None:
    window_provider = make_window_provider(["Test window title"], available=False)
    condition = WindowCondition(
        window_title="Test window title",
        expected_exists=expected_exists,
        window_provider=window_provider,
    )

    with pytest.raises(ConditionEvaluationProviderNotAvailableError) as exc_info:
        condition.evaluate()

    assert str(exc_info.value) == (
        "Window provider is not available, cannot evaluate window condition for 'Test window title'"
    )
    # The windows are not even queried
    window_provider.get_window_titles.assert_not_called()


def test_window_condition_rejects_invalid_regular_expression() -> None:
    with pytest.raises(re.error):
        WindowCondition(
            window_title="(unclosed",
            expected_exists=True,
            window_provider=make_window_provider(),
            match_type=MatchType.REGEX,
        )
