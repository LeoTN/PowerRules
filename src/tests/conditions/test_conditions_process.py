import re

import pytest

from powerrules.conditions.matcher import MatchType
from powerrules.conditions.process import ProcessCondition
from powerrules.engine.exceptions import ConditionEvaluationError
from tests.mocks import make_process_provider


@pytest.mark.parametrize(
    ("process_name", "match_type", "case_sensitive", "existing_names", "is_found"),
    [
        # Exact matching
        ("test.exe", MatchType.EXACT, True, ("test.exe",), True),
        ("test.exe", MatchType.EXACT, True, ("TEST.exe",), False),
        ("test.exe", MatchType.EXACT, True, ("test.exe.bak",), False),
        ("TEST.exe", MatchType.EXACT, False, ("test.exe",), True),
        ("TEST.exe", MatchType.EXACT, False, ("other.exe",), False),
        # Regular expressions need to match the whole name
        (r".*\.exe", MatchType.REGEX, True, ("test.exe",), True),
        (r".*\.exe", MatchType.REGEX, True, ("test.EXE",), False),
        (r".*\.exe", MatchType.REGEX, False, ("test.EXE",), True),
        (r".*\.executable", MatchType.REGEX, True, ("test.exe",), False),
        (r"test", MatchType.REGEX, True, ("test.exe",), False),
        # The existing processes
        ("test.exe", MatchType.EXACT, True, (), False),
        ("test.exe", MatchType.EXACT, True, ("a.exe", "test.exe", "b.exe"), True),
        ("test.exe", MatchType.EXACT, True, ("a.exe", "b.exe"), False),
    ],
)
@pytest.mark.parametrize("expected_exists", [True, False])
def test_process_condition_compares_existing_processes_with_expectation(
    process_name: str,
    match_type: MatchType,
    case_sensitive: bool,
    existing_names: tuple[str, ...],
    is_found: bool,
    expected_exists: bool,
) -> None:
    condition = ProcessCondition(
        process_name=process_name,
        expected_exists=expected_exists,
        process_provider=make_process_provider(existing_names),
        match_type=match_type,
        case_sensitive=case_sensitive,
    )

    assert condition.evaluate() is (is_found is expected_exists)


def test_process_condition_uses_exact_case_sensitive_matching_by_default() -> None:
    condition = ProcessCondition(
        process_name="test.exe",
        expected_exists=True,
        process_provider=make_process_provider(["TEST.exe"]),
    )

    assert condition.matcher.match_type is MatchType.EXACT
    assert condition.matcher.case_sensitive is True
    assert condition.evaluate() is False


def test_process_condition_keeps_its_configuration() -> None:
    process_provider = make_process_provider()

    condition = ProcessCondition(
        process_name="test.exe",
        expected_exists=False,
        process_provider=process_provider,
    )

    assert condition.process_name == "test.exe"
    assert condition.expected_exists is False
    assert condition.process_provider is process_provider


# The processes change over time, so every evaluation has to ask the provider again
def test_process_condition_queries_provider_on_every_evaluation() -> None:
    process_provider = make_process_provider(["test.exe"])
    condition = ProcessCondition(
        process_name="test.exe",
        expected_exists=True,
        process_provider=process_provider,
    )

    assert condition.evaluate() is True

    process_provider.get_process_names.return_value = ()

    assert condition.evaluate() is False
    assert process_provider.get_process_names.call_count == 2


def test_process_condition_raises_evaluation_error() -> None:
    original_error = OSError("Test OSError")
    condition = ProcessCondition(
        process_name="test.exe",
        expected_exists=True,
        process_provider=make_process_provider(error=original_error),
    )

    with pytest.raises(ConditionEvaluationError) as exc_info:
        condition.evaluate()

    assert str(exc_info.value) == (
        "Failed to determine whether process 'test.exe' exists"
    )
    assert exc_info.value.__cause__ is original_error


def test_process_condition_rejects_invalid_regular_expression() -> None:
    with pytest.raises(re.error):
        ProcessCondition(
            process_name="(unclosed",
            expected_exists=True,
            process_provider=make_process_provider(),
            match_type=MatchType.REGEX,
        )
