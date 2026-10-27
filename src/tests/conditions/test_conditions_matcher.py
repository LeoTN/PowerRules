import re

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
        ("test", MatchType.CONTAINS, True, "test", "TEST"),
        ("test", MatchType.CONTAINS, False, "test", "other"),
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


@pytest.mark.parametrize(
    ("pattern", "case_sensitive", "value", "expected"),
    [
        ("active", True, "active", True),
        ("active", True, "service is active (running)", True),
        ("active", True, "ACTIVE", False),
        ("active", False, "Service is ACTIVE", True),
        # A part of a word is enough
        ("active", True, "inactive", True),
        ("active", True, "stopped", False),
        # The text is found across line breaks, too
        ("one\ntwo", True, "zero\none\ntwo\nthree", True),
        # An empty text is contained in every value
        ("", True, "anything", True),
        # Case folding is used instead of lowercasing
        ("Straße", False, "STRASSE here", True),
    ],
)
def test_string_matcher_contains_checks_for_a_part_of_the_value(
    pattern: str,
    case_sensitive: bool,
    value: str,
    expected: bool,
) -> None:
    matcher = StringMatcher(pattern, MatchType.CONTAINS, case_sensitive)

    assert matcher.matches(value) is expected


def test_string_matcher_contains_treats_pattern_as_plain_text() -> None:
    # The text would be an invalid regular expression
    matcher = StringMatcher("(unclosed", MatchType.CONTAINS)

    assert matcher.matches("a (unclosed b") is True
    assert matcher.matches("a b") is False


@pytest.mark.parametrize(
    ("pattern", "case_sensitive", "value", "expected"),
    [
        # "." matches line breaks, so a pattern works on multi-line output
        (".*error.*", True, "first\nerror\nlast", True),
        ("first.*last", True, "first\nerror\nlast", True),
        # The whole value has to match
        ("error", True, "first\nerror\nlast", False),
        (".*ERROR.*", False, "first\nerror\nlast", True),
        (".*ERROR.*", True, "first\nerror\nlast", False),
    ],
)
def test_string_matcher_regex_matches_across_line_breaks(
    pattern: str,
    case_sensitive: bool,
    value: str,
    expected: bool,
) -> None:
    matcher = StringMatcher(pattern, MatchType.REGEX, case_sensitive)

    assert matcher.matches(value) is expected


def test_string_matcher_rejects_invalid_regular_expression() -> None:
    with pytest.raises(re.error):
        StringMatcher("(unclosed", MatchType.REGEX)
