import pytest

from powerrules.conditions.matcher import MatchType, StringMatcher


@pytest.mark.parametrize(
    ("pattern", "match_type", "case_sensitive", "matching_value", "non_matching_value"),
    [
        ("test", MatchType.EXACT, True, "test", "TEST"),
        ("test", MatchType.EXACT, False, "test", "other"),
        ("test", MatchType.REGEX, True, "test", "TEST"),
        ("test", MatchType.REGEX, False, "test", "other"),
        ("^test$", MatchType.REGEX, True, "test", "TEST"),
        ("^test$", MatchType.REGEX, False, "test", "other"),
    ],
)
def test_string_matcher_matches_according_to_configuration(
    pattern: str,
    match_type: MatchType,
    case_sensitive: bool,
    matching_value: str,
    non_matching_value: str,
) -> None:
    matcher = StringMatcher(
        pattern=pattern,
        match_type=match_type,
        case_sensitive=case_sensitive,
    )

    assert matcher.matches(matching_value) is True
    assert matcher.matches(non_matching_value) is False
